"""The runner's Guideword configuration on a fake run (Phase 6 spec 6.4, P6-6; plan G14;
acceptance 2, 3): use `benchmark`, the benchmark's caps, the `started` line before the run is
driven, a finished run never started again, a capped run recorded with its ranked list."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.runner import Case, GuidewordParts, guideword_config
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.fake import FakeTransport, Script, catalog_for
from guideword.gateway.ledgers import LaptopLedger
from guideword.reference import load_reference_set
from guideword.reference.precedents import PrecedentIndex
from guideword.runs.case import evidence_tools
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, EventType
from guideword.tools.web import NoKeySearch

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


class World:
    def __init__(self, tmp_path: Path, config: Config, script: Script) -> None:
        sessions = make_session_factory(f"sqlite:///{(tmp_path / 'benchmark.db').as_posix()}")
        self.transport = FakeTransport(script, catalog_for(config))
        cache = ResponseCache(sessions)
        ledger = LaptopLedger(tmp_path / "ledger.jsonl")
        clock = lambda: NOW  # noqa: E731
        gateway = Gateway(
            config=config,
            transport=self.transport,
            cache=cache,
            ledger=ledger,
            use=BudgetUse.BENCHMARK,
            phase="6",
            clock=clock,
        )
        tools = evidence_tools(
            config=config,
            cache=cache,
            ledger=ledger,
            use=BudgetUse.BENCHMARK,
            phase="6",
            clock=clock,
            search=NoKeySearch(),
            index=PrecedentIndex((), "benchmark-evidence-off"),
        )
        self.runs = RunRepository(sessions, clock)
        self.parts = GuidewordParts(
            PlantRepository(sessions), self.runs, load_reference_set(), config, gateway, tools
        )
        self.out = tmp_path / "out"
        folder = tmp_path / "heldout"
        folder.mkdir()
        (folder / "case_k_unit.md").write_text("package", encoding="utf-8")
        (folder / "case_k.json").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        self.case = Case("k", folder / "case_k_unit.md", folder / "case_k.json")
        self.marked: list[tuple[str, int]] = []

    def mark(self, run_id: str) -> None:
        # how many calls had been sent when the line was written
        self.marked.append((run_id, len(self.transport.sent)))

    def run(self, started: str | None = None) -> dict[str, Any]:
        return guideword_config(self.parts, self.out)(self.case, started, self.mark)


def test_a_new_case_starts_marks_then_drives_a_benchmark_run(
    tmp_path: Path, config: Config, script: Script
) -> None:
    world = World(tmp_path, config, script)
    result = world.run()
    [(run_id, sent_before)] = world.marked
    assert sent_before == 0 and len(world.transport.sent) > 0  # marked before any call
    assert result["run_id"] == run_id and result["status"] == "finished"
    run = world.runs.get(run_id)
    assert run is not None and run.use == BudgetUse.BENCHMARK
    bench = config.caps.benchmark
    assert (run.spend_cap_usd, run.post_spend_cap_usd) == (bench.run_cap_usd, bench.post_cap_usd)
    report = json.loads((world.out / "case_k" / "guideword.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run_id and report["hybrid"]


def test_evidence_is_off_and_says_use_benchmark(
    tmp_path: Path, config: Config, script: Script
) -> None:
    """Acceptance 3: the evidence step records why it made no call."""
    world = World(tmp_path, config, script)
    run_id = world.run()["run_id"]
    summaries = [
        e.payload
        for e in world.runs.events(run_id)
        if e.type == EventType.STEP_FINISHED and e.payload.get("step") == "evidence"
    ]
    assert summaries and all(s.get("reason") == "use benchmark" for s in summaries)
    assert not world.runs.evidence(run_id)


def test_a_finished_run_is_reported_as_it_stands_and_never_started_again(
    tmp_path: Path, config: Config, script: Script
) -> None:
    world = World(tmp_path, config, script)
    first = world.run()
    sent = len(world.transport.sent)
    again = world.run(started=first["run_id"])
    assert again["run_id"] == first["run_id"] and again["status"] == "finished"
    assert len(world.transport.sent) == sent  # no call, no new attempt
    assert len(world.marked) == 1


def test_a_run_stopped_at_its_cap_keeps_its_ranked_list_and_open_questions(
    tmp_path: Path, config: Config, capped_script: Script
) -> None:
    """P6-6, G14: counted as a miss later, but recorded with its status and partial list."""
    low = config.caps.benchmark.model_copy(update={"run_cap_usd": 0.08})
    capped = config.model_copy(update={"caps": config.caps.model_copy(update={"benchmark": low})})
    world = World(tmp_path, capped, capped_script)
    result = world.run()
    assert result["status"] == "stopped_cap"
    assert result["questions_open"] > 0
    report = json.loads((world.out / "case_k" / "guideword.json").read_text(encoding="utf-8"))
    assert report["status"] == "stopped_cap" and report["ranked"]
