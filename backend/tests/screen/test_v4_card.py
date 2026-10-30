"""The v4 hypothesis card (Phase 9 spec 9.1; answers 6 and 10): required from `plant_screen/v4`,
every cited fact checked, a run's own prompt version and limit honoured on replay, and every
ID stored before Phase 9 unchanged. Fake transport only."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.prompts import load_prompt, render
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.case import prepare_plant, start_case, steppers_for
from guideword.runs.db import make_session_factory
from guideword.runs.machine import advance
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, EventType
from guideword.schema.records import Hypothesis
from guideword.screen.schema import CARD_FIELDS, fact_problem, requires_card

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RECORDED_WG = REPO / "cases" / "demo" / "recorded" / "williams_geismar" / "hypotheses.json"
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)

CARD: dict[str, Any] = {
    "initiating_event": "the operator charges the wrong tote",
    "enabling_condition": "the charging step has no material check",
    "propagation": "KOH meets the Si-H fluid in MX-1 and hydrogen evolves",
    "consequence_magnitude": None,
    "operating_mode": "batch_step",
    "mechanism_class": "wrong_material_or_contamination",
    "fact_ids": ["MX-1", "MX-1.design_pressure_kpa"],
}


def hyp(rank: int, components: list[str], kind: str, cause: str, **extra: Any) -> dict[str, Any]:
    base = {
        "rank": rank,
        "mechanism": f"mechanism {rank}",
        "component_ids": components,
        "chemical_ids": extra.get("chemicals", []),
        "failing_component_type": kind,
        "cause_id": cause,
        "cause_text": extra.get("cause_text"),
        "consequence": f"consequence {rank}",
        "reason": f"reason {rank}",
    }
    if extra.get("card", True):
        base.update(CARD)
        base.update(extra.get("card_overrides", {}))
    return base


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    config = load_config(global_budget_usd=25.0)
    run = config.caps.run.model_copy(update={"plant_screen_min_valid": 0})
    return config.model_copy(update={"caps": config.caps.model_copy(update={"run": run})})


def with_screen(config: Config, version: str, limit: int | None = None) -> Config:
    routing = config.routing.model_copy(
        update={"prompts": {**config.routing.prompts, "plant_screen": version}}
    )
    update: dict[str, Any] = {"routing": routing}
    if limit is not None:
        run = config.caps.run.model_copy(update={"plant_screen_max_hypotheses": limit})
        update["caps"] = config.caps.model_copy(update={"run": run})
    return config.model_copy(update=update)


class World:
    def __init__(self, tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
        self.sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)
        self.ref, self.config, self.tmp = ref, config, tmp_path
        self.record = prepare_plant(
            self.plants, json.loads(EXAMPLE.read_text(encoding="utf-8")), ref
        )

    def screen(self, answer: Any, *, started_with: Config | None = None) -> tuple[str, Any]:
        """Start the run under `started_with` (default: the world's config) and advance its
        first step with steppers built on the world's config."""

        def script(job: str, request: dict[str, Any]) -> Any:
            assert job == "plant_screen", job
            return reply(answer)

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
            started_with or self.config,
            self.record.id,
            1.0,
            use=BudgetUse.DEVELOPMENT,
        )
        advance(
            self.runs, run.id, steppers_for(gateway, self.config, self.ref, self.record.plant_file)
        )
        return run.id, transport

    def dropped(self, run_id: str) -> list[str]:
        return [
            str(e.payload["reason"])
            for e in self.runs.events(run_id)
            if e.type == EventType.HYPOTHESIS_DROPPED
        ]


@pytest.fixture
def world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
    return World(tmp_path, ref, config)


def test_v4_is_the_routed_version_and_asks_for_the_card(config: Config) -> None:
    assert config.routing.prompts["plant_screen"] == "v4"
    assert requires_card("v4") and requires_card("v10")
    assert not requires_card("v3") and not requires_card("draft")
    body = load_prompt("plant_screen", config).body
    text = render(
        body,
        {
            "plant": "P",
            "causes": "C",
            "can_fail_as": "F",
            "question_kinds": "K",
            "max_hypotheses": "20",
        },
    )
    assert "{{" not in text
    for field in (*CARD_FIELDS, "consequence_magnitude", "fact_ids"):
        assert f'"{field}"' in text, field
    assert "**data, not instructions**" in body


def test_a_v4_hypothesis_without_the_card_is_retried_then_dropped(world: World) -> None:
    good = hyp(1, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "SIH"])
    bare = hyp(2, ["BLDG-1"], "external", "C22", card=False)
    run_id, transport = world.screen({"hypotheses": [good, bare]})
    assert len(transport.sent) == 2  # the one validation retry
    stored = world.runs.hypotheses(run_id)
    assert [h.rank for h in stored] == [1]
    assert world.dropped(run_id) == [
        "rank 2: the card lacks initiating_event, enabling_condition, propagation, "
        "operating_mode, mechanism_class"
    ]


def test_the_stored_hypothesis_carries_the_card(world: World) -> None:
    good = hyp(1, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "SIH"])
    run_id, _ = world.screen({"hypotheses": [good]})
    stored = world.runs.hypotheses(run_id)[0]
    assert stored.initiating_event == CARD["initiating_event"]
    assert stored.enabling_condition == CARD["enabling_condition"]
    assert stored.propagation == CARD["propagation"]
    assert stored.consequence_magnitude is None
    assert stored.operating_mode == "batch_step"
    assert stored.mechanism_class == "wrong_material_or_contamination"
    assert stored.fact_ids == ["MX-1", "MX-1.design_pressure_kpa"]
    assert stored.pass_number == 1
    assert stored.id == ids.hypothesis_id(1, "mechanism 1", ["P-CHARGE-1"])


def test_an_unknown_fact_id_drops_the_hypothesis(world: World) -> None:
    bad = hyp(1, ["P-CHARGE-1"], "operator", "C14", card_overrides={"fact_ids": ["MX-1.nope"]})
    good = hyp(2, ["BLDG-1"], "external", "C22")
    run_id, _ = world.screen({"hypotheses": [bad, good]})
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [2]
    assert world.dropped(run_id) == ["rank 1: MX-1.nope names no field of MX-1"]


def test_fact_problems_follow_the_provenance_rule(ref: ReferenceSet) -> None:
    from guideword.schema.plant import Plant

    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    assert fact_problem("MX-1", plant) is None
    assert fact_problem("MX-1.design_pressure_kpa", plant) is None
    assert fact_problem("MX-1.operating.temperature.trip_high", plant) is None
    assert fact_problem("MX-9", plant) == "MX-9 is not a plant object or fact ID"
    assert (
        fact_problem("MX-9.design_pressure_kpa", plant)
        == "MX-9.design_pressure_kpa names no plant object"
    )
    assert fact_problem("MX-1.id", plant) == "MX-1.id names no field of MX-1"
    assert fact_problem("not a fact", plant) == "not a fact is not a plant object or fact ID"
    assert fact_problem("MX-1.operating.level.trip_high", plant) == (
        "MX-1.operating.level.trip_high names no operating row"
    )


def test_a_run_started_on_v3_replays_on_v3_without_the_card(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """A stored run keeps its prompt version (Phase 9): advanced by steppers built on the v4
    routing, it still asks v3 and accepts a v3 answer."""
    world = World(tmp_path, ref, config)
    bare = hyp(1, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "SIH"], card=False)
    run_id, transport = world.screen({"hypotheses": [bare]}, started_with=with_screen(config, "v3"))
    run = world.runs.get(run_id)
    assert run is not None and run.prompt_versions["plant_screen"] == "v3"
    assert len(transport.sent) == 1
    stored = world.runs.hypotheses(run_id)
    assert [h.rank for h in stored] == [1]
    assert stored[0].initiating_event is None and stored[0].fact_ids == []
    calls = [c for c in world.runs.model_calls(run_id) if c.job == "plant_screen"]
    assert calls[0].prompt_version == "plant_screen/v3"


def test_the_hypothesis_limit_is_the_runs_own(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """A run started with a limit of 2 refuses three hypotheses even when the current config
    allows twenty; the whole answer is invalid, retried once, then nothing is kept."""
    world = World(tmp_path, ref, config)
    three = [
        hyp(i, ["BLDG-1"], "external", "C22", card_overrides={"fact_ids": []}) for i in (1, 2, 3)
    ]
    for i, h in enumerate(three, start=1):
        h["mechanism"] = f"mechanism {i} of three"
    run_id, transport = world.screen(
        {"hypotheses": three}, started_with=with_screen(config, "v4", limit=2)
    )
    assert len(transport.sent) == 2
    assert world.runs.hypotheses(run_id) == []
    assert any("3 hypotheses, at most 2" in d for d in world.dropped(run_id))


def test_a_pass_number_changes_the_id_only_after_pass_one() -> None:
    first = ids.hypothesis_id(1, "a mechanism", ["MX-1"])
    assert ids.hypothesis_id(1, "a mechanism", ["MX-1"], pass_number=1) == first
    second = ids.hypothesis_id(1, "a mechanism", ["MX-1"], pass_number=2)
    assert second != first and second.startswith("h:1:p2:")
    assert ids.hypothesis_id(1, "a mechanism", ["MX-1"], pass_number=3) != second
    with pytest.raises(ValueError):
        ids.hypothesis_id(1, "a mechanism", ["MX-1"], pass_number=0)


def test_every_hypothesis_stored_before_phase_9_rebuilds_its_id_unchanged() -> None:
    """The recorded WG run (plant_screen/v3): every stored ID is the pass-1 form, and the record
    reads with the card empty (answer 10)."""
    rows = json.loads(RECORDED_WG.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 12
    for row in rows:
        record = Hypothesis.model_validate(row["record"])
        assert record.id == ids.hypothesis_id(record.rank, record.mechanism, record.component_ids)
        assert record.pass_number == 1
        assert all(getattr(record, f) is None for f in CARD_FIELDS)
        assert record.fact_ids == []
