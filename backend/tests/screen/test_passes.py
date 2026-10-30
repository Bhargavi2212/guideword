"""Several holistic passes (Phase 9 spec 9.3): `credibility.holistic_passes` calls, each on the
plant in a different order with its own request marker; every pass's survivors are stored with
their pass number; a run stored without the block reads as one pass; a cap refusal after the
first pass keeps what was done and the run goes on. Fake transport only."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.fake import fake_gateway, reply
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.case import prepare_plant, start_case, steppers_for
from guideword.runs.db import make_session_factory
from guideword.runs.machine import advance
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, EventType, RunLabelKind, RunStatus
from guideword.schema.records import Run, RunLabel
from guideword.screen.step import passes_of

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
CARD: dict[str, Any] = {
    "initiating_event": "test",
    "enabling_condition": "test",
    "propagation": "test",
    "consequence_magnitude": None,
    "operating_mode": "normal",
    "mechanism_class": "other",
    "fact_ids": [],
}


def hyp(rank: int, components: list[str], kind: str, cause: str, **extra: Any) -> dict[str, Any]:
    return {
        "rank": rank,
        "mechanism": f"mechanism {rank}",
        "component_ids": components,
        "chemical_ids": extra.get("chemicals", []),
        "failing_component_type": kind,
        "cause_id": cause,
        "cause_text": extra.get("cause_text"),
        "consequence": f"consequence {rank}",
        "reason": f"reason {rank}",
        **CARD,
    }


GOOD_1 = hyp(1, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "SIH"])
GOOD_2 = hyp(2, ["BLDG-1"], "external", "C22")


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    config = load_config(global_budget_usd=25.0)
    run = config.caps.run.model_copy(update={"plant_screen_min_valid": 0})
    return config.model_copy(update={"caps": config.caps.model_copy(update={"run": run})})


def with_passes(config: Config, passes: int) -> Config:
    credibility = config.caps.credibility.model_copy(update={"holistic_passes": passes})
    return config.model_copy(
        update={"caps": config.caps.model_copy(update={"credibility": credibility})}
    )


class World:
    def __init__(self, tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
        self.sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)
        self.ref, self.config, self.tmp = ref, config, tmp_path
        self.record = prepare_plant(
            self.plants, json.loads(EXAMPLE.read_text(encoding="utf-8")), ref
        )

    def screen(
        self, answers: list[Any], *, cap: float = 1.0, output_tokens: int = 50
    ) -> tuple[str, Any]:
        """One answer per call, in order (the last repeats)."""
        calls: list[int] = []

        def script(job: str, request: dict[str, Any]) -> Any:
            assert job == "plant_screen", job
            calls.append(1)
            answer = answers[min(len(calls) - 1, len(answers) - 1)]
            return reply(answer, output_tokens=output_tokens)

        gateway, transport = fake_gateway(
            self.config,
            script,
            sessions=self.sessions,
            ledger_path=self.tmp / "l.jsonl",
            clock=lambda: NOW,
        )
        run = start_case(
            self.plants,
            self.runs,
            self.ref,
            self.config,
            self.record.id,
            cap,
            use=BudgetUse.DEVELOPMENT,
        )
        advance(
            self.runs, run.id, steppers_for(gateway, self.config, self.ref, self.record.plant_file)
        )
        return run.id, transport

    def marker(self, transport: Any, index: int) -> str:
        return str(transport.sent[index][1]["messages"][0]["content"]).splitlines()[0]

    def plant_block(self, transport: Any, index: int) -> dict[str, Any]:
        system = str(transport.sent[index][1]["messages"][0]["content"])
        block = system.split("<plant>")[1].split("</plant>")[0]
        loaded: dict[str, Any] = json.loads(block)
        return loaded


def test_the_shipped_config_asks_for_three_passes(config: Config) -> None:
    assert config.caps.credibility.holistic_passes == 3


def test_three_passes_make_three_calls_with_distinct_markers_and_orders(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref, config)
    run_id, transport = world.screen([{"hypotheses": [GOOD_1, GOOD_2]}])
    assert [job for job, _ in transport.sent] == ["plant_screen"] * 3
    markers = [world.marker(transport, i) for i in range(3)]
    base = ":".join(run_id.split(":")[:2])
    assert markers == [
        f"Request marker: {base}",
        f"Request marker: {base}:pass2",
        f"Request marker: {base}:pass3",
    ]
    blocks = [world.plant_block(transport, i) for i in range(3)]
    first = [e["id"] for e in blocks[0]["equipment"]]
    assert [e["id"] for e in blocks[1]["equipment"]] == list(reversed(first))
    assert [e["id"] for e in blocks[2]["equipment"]] != first
    assert sorted(e["id"] for e in blocks[2]["equipment"]) == sorted(first)
    assert world.runs.get(run_id).step == "analysis"  # type: ignore[union-attr]


def test_each_pass_stores_its_survivors_with_its_pass_number(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref, config)
    run_id, _ = world.screen([{"hypotheses": [GOOD_1, GOOD_2]}])
    stored = sorted(world.runs.hypotheses(run_id), key=lambda h: (h.pass_number, h.rank))
    assert [(h.pass_number, h.rank) for h in stored] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
        (3, 1),
        (3, 2),
    ]
    assert stored[0].id.startswith("h:1:") and ":p" not in stored[0].id
    assert stored[2].id.startswith("h:1:p2:") and stored[4].id.startswith("h:1:p3:")
    assert len({h.id for h in stored}) == 6
    added = [e for e in world.runs.events(run_id) if e.type == EventType.HYPOTHESIS_ADDED]
    assert len(added) == 6


def test_a_pass_with_no_valid_hypothesis_does_not_stop_the_others(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref, config)
    bad = hyp(1, ["TANK-9"], "tank", "C21")
    run_id, transport = world.screen(
        [
            {"hypotheses": [GOOD_1]},
            {"hypotheses": [bad]},
            {"hypotheses": [bad]},
            {"hypotheses": [GOOD_2]},
        ]
    )
    stored = sorted(world.runs.hypotheses(run_id), key=lambda h: (h.pass_number, h.rank))
    assert [(h.pass_number, h.rank) for h in stored] == [(1, 1), (3, 2)]
    # pass 2: the bad answer, its one retry, nothing kept
    assert len(transport.sent) == 4


def test_a_run_stored_without_the_block_reads_as_one_pass(config: Config) -> None:
    run = Run(
        id="run:0123456789abcdef",
        plant_record_id="plant:x:0123456789abcdef",
        attempt=1,
        section_snapshot=[],
        status=RunStatus.RUNNING,
        step="plant_screen",
        mode="full",
        spend_cap_usd=1.0,
        spent_usd=0.0,
        cap_spent_usd=0.0,
        post_spend_cap_usd=0.3,
        reference_versions={},
        routing_config={},
        caps={},
        prompt_versions={},
        label=RunLabel(kind=RunLabelKind.LIVE),
    )
    assert passes_of(run, config) == 1
    stored = run.model_copy(update={"caps": {"credibility": {"holistic_passes": 2}}})
    assert passes_of(stored, config) == 2


def test_one_pass_makes_one_call_as_before(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref, with_passes(config, 1))
    run_id, transport = world.screen([{"hypotheses": [GOOD_1, GOOD_2]}])
    assert len(transport.sent) == 1
    assert [h.pass_number for h in world.runs.hypotheses(run_id)] == [1, 1]


def test_a_cap_refusal_after_the_first_pass_keeps_it_and_the_run_goes_on(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """The first call's real spend leaves too little for the second's estimate."""
    world = World(tmp_path, ref, config)
    run_id, transport = world.screen(
        [{"hypotheses": [GOOD_1, GOOD_2]}], cap=0.06, output_tokens=12000
    )
    assert len(transport.sent) == 1
    stored = world.runs.hypotheses(run_id)
    assert [(h.pass_number, h.rank) for h in stored] == [(1, 1), (1, 2)]
    run = world.runs.get(run_id)
    assert run is not None and run.step == "analysis" and run.status == RunStatus.RUNNING
    notes = [
        e.payload["reason"]
        for e in world.runs.events(run_id)
        if e.type == EventType.HYPOTHESIS_DROPPED and e.payload.get("rank") is None
    ]
    assert notes == ["screen stopped at the cap after pass 1 of 3"]
