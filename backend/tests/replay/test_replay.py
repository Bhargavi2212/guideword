"""Replay fixtures (spec 2.9; plan R30, R45): a run exported to `bench/replay/<case>/` replays
through a gateway that serves only those fixtures and fails on a miss, and gives the same
ranked list. Until a live case is committed, the fixture set is made here by the fake
gateway on the §9 example."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.fake import fake_gateway
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.replay import (
    MANIFEST,
    ReplayMiss,
    ReplayTransport,
    export_replay,
    load_replay,
)
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.case import drive, prepare_plant, ranked_lines, start_case, steppers_for
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, RunStatus
from guideword.schema.records import ToolCall
from guideword.tools.web import FakeSearch, ReplaySearch, WebSearch

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


class Store:
    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.dir = path
        self.sessions = make_session_factory(f"sqlite:///{(path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)


def original_run(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any, cap: float = 1.0
) -> tuple[Store, str]:
    store = Store(tmp_path / "original")
    gateway, _ = fake_gateway(
        config,
        script,
        sessions=store.sessions,
        ledger_path=store.dir / "l.jsonl",
        clock=lambda: NOW,
    )
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    record = prepare_plant(store.plants, raw, ref)
    run = start_case(store.plants, store.runs, ref, config, record.id, cap)
    drive(store.runs, run.id, steppers_for(gateway, config, ref, record.plant_file))
    return store, run.id


def replay(
    fixtures: Path, tmp_path: Path, ref: ReferenceSet, config: Config, cap: float = 1.0
) -> tuple[Store, str, RunStatus]:
    store = Store(tmp_path / "replayed")
    manifest = load_replay(fixtures, store.sessions)
    gateway = Gateway(
        config=config,
        transport=ReplayTransport(manifest),
        cache=ResponseCache(store.sessions),
        ledger=LaptopLedger(store.dir / "l.jsonl"),
        use=BudgetUse.DEVELOPMENT,
        phase="2",
        clock=lambda: NOW,
    )
    raw = json.loads((REPO / manifest.plant_file).read_text(encoding="utf-8"))
    record = prepare_plant(store.plants, raw, ref)
    run = start_case(store.plants, store.runs, ref, config, record.id, cap)
    status = drive(store.runs, run.id, steppers_for(gateway, config, ref, record.plant_file))
    return store, run.id, status


def export(store: Store, run_id: str, out: Path, ref: ReferenceSet, config: Config) -> Path:
    plant = prepare_plant(store.plants, json.loads(EXAMPLE.read_text(encoding="utf-8")), ref)
    return export_replay(
        store.runs,
        ResponseCache(store.sessions),
        run_id,
        out,
        plant=plant.plant_file,
        plant_file=EXAMPLE.relative_to(REPO).as_posix(),
        ref=ref,
        caps=config.caps,
        secrets=["sk-not-a-real-key-0123456789"],
    )


def test_a_replayed_run_gives_the_same_ranked_list_with_no_miss(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any
) -> None:
    store, run_id = original_run(tmp_path, ref, config, script)
    fixtures = export(store, run_id, tmp_path / "bench" / "replay" / "example", ref, config)
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id and manifest["status"] == "finished"
    assert manifest["ranked"]

    again, replayed_id, status = replay(fixtures, tmp_path, ref, config)
    assert replayed_id == run_id  # same inputs: the same run
    assert status == RunStatus.FINISHED
    plant = prepare_plant(again.plants, json.loads(EXAMPLE.read_text(encoding="utf-8")), ref)
    lines = ranked_lines(again.runs.findings(replayed_id), plant.plant_file, ref, config.caps)
    assert [[r["finding_id"], r["rating"], r["frequency_per_year"]] for r in lines] == manifest[
        "ranked"
    ]
    replayed = again.runs.get(replayed_id)
    assert replayed is not None
    assert replayed.spent_usd == 0.0
    assert replayed.cap_spent_usd == pytest.approx(manifest["cap_spent_usd"])
    assert not (again.dir / "l.jsonl").exists()  # a replay writes no ledger lines


def test_export_writes_one_file_per_response_the_run_used_and_a_manifest(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any
) -> None:
    store, run_id = original_run(tmp_path, ref, config, script)
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    keys = sorted({c.id.removeprefix("mc:") for c in store.runs.model_calls(run_id)})
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["keys"] == keys
    assert sorted(p.stem for p in fixtures.glob("*.json") if p.name != MANIFEST) == keys
    one = json.loads((fixtures / f"{keys[0]}.json").read_text(encoding="utf-8"))
    assert set(one) == {"key", "model_id", "prompt_version", "response"}
    assert "cost_usd" in one["response"]  # the stored cost travels with the response (R45)
    assert manifest["plant_file"] == "backend/tests/schema/fixtures/example_mixing_unit.json"


def test_a_missing_fixture_fails_the_replay_instead_of_calling_out(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any
) -> None:
    store, run_id = original_run(tmp_path, ref, config, script)
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    (fixtures / f"{manifest['keys'][-1]}.json").unlink()
    with pytest.raises(ReplayMiss):
        replay(fixtures, tmp_path, ref, config)


def test_a_capped_run_replays_to_the_same_stop(
    tmp_path: Path, ref: ReferenceSet, config: Config, capped_script: Any
) -> None:
    store, run_id = original_run(tmp_path, ref, config, capped_script, cap=0.08)
    assert store.runs.get(run_id).status == RunStatus.STOPPED_CAP  # type: ignore[union-attr]
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    _, _, status = replay(fixtures, tmp_path, ref, config, cap=0.08)
    assert status == RunStatus.STOPPED_CAP


def test_export_refuses_a_response_holding_a_key_and_writes_nothing(
    tmp_path: Path, ref: ReferenceSet, config: Config, script_factory: Any
) -> None:
    store, run_id = original_run(
        tmp_path, ref, config, script_factory(secret="sk-not-a-real-key-0123456789")
    )
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="key"):
        export(store, run_id, out, ref, config)
    assert not out.exists() or list(out.iterdir()) == []


def test_replay_transport_lists_the_recorded_models_and_never_sends(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any
) -> None:
    store, run_id = original_run(tmp_path, ref, config, script)
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    manifest = load_replay(fixtures, Store(tmp_path / "x").sessions)
    transport = ReplayTransport(manifest)
    assert {m["id"] for m in transport.models()} == set(manifest.models)
    with pytest.raises(ReplayMiss):
        transport.send("orchestrator", {"model": "m", "messages": []})


def test_replay_reproduces_hypotheses_links_tiers_and_stop_point(
    tmp_path: Path, ref: ReferenceSet, config: Config, script_factory: Any
) -> None:
    """G10: the manifest carries the hypotheses with their links and the hybrid tiered lines,
    and a replay gives the same, stopping where the original stopped."""
    from guideword.ranking.rank import rank_findings  # noqa: PLC0415
    from guideword.ranking.tiers import tiered  # noqa: PLC0415

    plant_raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    location = plant_raw["locations"][0]["id"]
    screen = [
        {
            "rank": rank,
            "mechanism": mechanism,
            "component_ids": components,
            "chemical_ids": [],
            "failing_component_type": kind,
            "cause_id": cause,
            "cause_text": text,
            "consequence": "a release",
            "reason": "test",
        }
        for rank, mechanism, components, kind, cause, text in [
            (
                1,
                "something outside hits it",
                [location],
                "external",
                "outside_library",
                "something outside",
            ),
            (2, "the tote overheats", ["TOTE-1"], "tank", "outside_library", "a hot day"),
        ]
    ]
    store, run_id = original_run(tmp_path, ref, config, script_factory(screen_hypotheses=screen))
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    assert [h[1] for h in manifest["hypotheses"]] == [1, 2]
    assert {t[0] for t in manifest["tiered"]} >= {"confirmed", "also_found"}
    assert manifest["step"] == store.runs.get(run_id).step  # type: ignore[union-attr]

    again, replayed_id, status = replay(fixtures, tmp_path, ref, config)
    assert status.value == manifest["status"]
    assert again.runs.get(replayed_id).step == manifest["step"]  # type: ignore[union-attr]
    hypotheses = again.runs.hypotheses(replayed_id)
    assert [[h.id, h.rank, h.question_ids] for h in hypotheses] == manifest["hypotheses"]
    plant = prepare_plant(again.plants, plant_raw, ref).plant_file
    findings = again.runs.findings(replayed_id)
    lines = tiered(
        rank_findings(findings, plant, ref, config.caps),
        hypotheses,
        findings,
        again.runs.questions(replayed_id),
        sections=again.runs.sections(replayed_id),
    )
    assert [
        [
            line.tier.value,
            line.hypothesis.id if line.hypothesis else None,
            line.lead.finding.id if line.lead else None,
        ]
        for line in lines
    ] == manifest["tiered"]


def test_export_carries_the_runs_web_searches_and_a_replay_serves_them(
    tmp_path: Path, ref: ReferenceSet, config: Config, script: Any
) -> None:
    """Phase 4 plan G18: a `web_research` tool call names its cache key, the export writes
    the search with the model responses, and a replay serves it from the fixtures."""
    store, run_id = original_run(tmp_path, ref, config, script)
    web = WebSearch(
        client=FakeSearch(lambda q, n: {"results": [{"title": "t", "url": "https://m.invalid/1"}]}),
        cache=ResponseCache(store.sessions),
        ledger=LaptopLedger(store.dir / "l.jsonl"),
        config=config,
        use=BudgetUse.DEVELOPMENT,
        phase="4",
        clock=lambda: NOW,
    )
    found = web.search("mock query", 5)
    step = ids.agent_step_id(run_id, "evidence", "web_research", {"query": "mock query"})
    with store.runs.step(run_id) as writer:
        writer.add_tool_call(
            ToolCall(
                id=ids.tool_call_id(step, "web_research", {"query": "mock query"}),
                run_id=run_id,
                agent_step_id=step,
                tool="web_research",
                arguments={"query": "mock query", "max_results": 5},
                result={"cache_key": found.cache_key},
            )
        )
    fixtures = export(store, run_id, tmp_path / "out", ref, config)
    manifest = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    assert found.cache_key in manifest["keys"]
    assert (fixtures / f"{found.cache_key}.json").exists()
    replayed = Store(tmp_path / "replayed")
    load_replay(fixtures, replayed.sessions)
    served = WebSearch(
        client=ReplaySearch(),
        cache=ResponseCache(replayed.sessions),
        ledger=LaptopLedger(replayed.dir / "l.jsonl"),
        config=config,
        use=BudgetUse.DEVELOPMENT,
        phase="4",
        clock=lambda: NOW,
    ).search("mock query", 5)
    assert served.cache_hit and served.hits == found.hits
