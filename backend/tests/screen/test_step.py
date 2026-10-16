"""The whole-plant pass, `plant_screen` (spec 2b.1; R50; plan Q4–Q7, G11, G17, C1). Fake
transport only: one Ultra call, validated like any answer; bad hypotheses are dropped and the
rest stand; each survivor is stored once with its question links."""

import json
import logging
import re
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
from guideword.schema.enums import EventType, RunStatus

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
CASE_G = REPO / "cases" / "dev" / "case_g.json"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


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
    }


GOOD_1 = hyp(1, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "SIH"])
GOOD_2 = hyp(2, ["BLDG-1"], "external", "C22")


class World:
    def __init__(
        self, tmp_path: Path, ref: ReferenceSet, config: Config, plant_file: Path = EXAMPLE
    ) -> None:
        self.sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)
        self.ref, self.config, self.tmp = ref, config, tmp_path
        self.record = prepare_plant(
            self.plants, json.loads(plant_file.read_text(encoding="utf-8")), ref
        )

    def screen(self, answer: Any, cap: float = 1.0) -> tuple[str, Any]:
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
        run = start_case(self.plants, self.runs, self.ref, self.config, self.record.id, cap)
        advance(
            self.runs, run.id, steppers_for(gateway, self.config, self.ref, self.record.plant_file)
        )
        return run.id, transport

    def events(self, run_id: str, kind: EventType) -> list[dict[str, Any]]:
        return [e.payload for e in self.runs.events(run_id) if e.type == kind]


@pytest.fixture
def world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
    return World(tmp_path, ref, config)


def test_the_screen_is_the_first_step_and_stores_its_hypotheses_with_links(world: World) -> None:
    run_id, transport = world.screen({"hypotheses": [GOOD_1, GOOD_2]})
    assert [job for job, _ in transport.sent] == ["plant_screen"]
    stored = world.runs.hypotheses(run_id)
    assert [h.rank for h in stored] == [1, 2]
    assert "pair:KOH:SIH" in stored[0].question_ids
    assert stored[1].question_ids == []  # external: plant-wide
    assert world.runs.get(run_id).step == "analysis"  # type: ignore[union-attr]
    added = world.events(run_id, EventType.HYPOTHESIS_ADDED)
    assert [a["hypothesis_id"] for a in added] == [h.id for h in stored]


def test_one_call_per_run_counted_against_the_cap(world: World) -> None:
    run_id, transport = world.screen({"hypotheses": [GOOD_1]})
    calls = [c for c in world.runs.model_calls(run_id) if c.job == "plant_screen"]
    assert len(calls) == len(transport.sent) == 1
    run = world.runs.get(run_id)
    assert run is not None and calls[0].cap_cost_usd > 0
    assert run.cap_spent_usd == pytest.approx(calls[0].cap_cost_usd)
    assert world.runs.hypotheses(run_id)[0].model_call_id == calls[0].id


def test_unknown_id_is_retried_then_dropped_and_the_rest_stand(world: World) -> None:
    bad = hyp(2, ["TANK-9"], "tank", "C21")
    run_id, transport = world.screen({"hypotheses": [GOOD_1, bad]})
    assert len(transport.sent) == 2  # the retry with the error, then kept what is valid
    assert "TANK-9" in transport.sent[1][1]["messages"][-1]["content"]
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1]
    [dropped] = world.events(run_id, EventType.HYPOTHESIS_DROPPED)
    assert dropped["rank"] == 2 and "TANK-9" in dropped["reason"]


def test_failing_components_must_fit_the_type_over_the_whole_plant(world: World) -> None:
    pump_as_loop = hyp(2, ["P-1"], "control_loop", "C01")
    run_id, _ = world.screen({"hypotheses": [GOOD_1, pump_as_loop]})
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1]
    [dropped] = world.events(run_id, EventType.HYPOTHESIS_DROPPED)
    assert "cannot fail as a control_loop" in dropped["reason"]


def test_library_cause_type_must_match(world: World) -> None:
    wrong_type = hyp(2, ["P-1"], "pump", "C01")
    run_id, _ = world.screen({"hypotheses": [GOOD_1, wrong_type]})
    [dropped] = world.events(run_id, EventType.HYPOTHESIS_DROPPED)
    assert "C01" in dropped["reason"] and "control_loop" in dropped["reason"]


def test_an_unknown_chemical_is_dropped_with_its_hypothesis(world: World) -> None:
    bad = hyp(2, ["P-CHARGE-1"], "operator", "C14", chemicals=["KOH", "ACID-X"])
    run_id, _ = world.screen({"hypotheses": [GOOD_1, bad]})
    [dropped] = world.events(run_id, EventType.HYPOTHESIS_DROPPED)
    assert "ACID-X" in dropped["reason"]


def test_zero_survivors_leave_the_run_going_with_no_hypotheses_logged(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        run_id, _ = world.screen({"hypotheses": [hyp(1, ["TANK-9"], "tank", "C21")]})
    assert world.runs.hypotheses(run_id) == []
    run = world.runs.get(run_id)
    assert run is not None and run.status == RunStatus.RUNNING and run.step == "analysis"
    assert any("no hypotheses" in r.message for r in caplog.records)


def test_at_most_max_hypotheses(world: World, config: Config) -> None:
    most = config.caps.run.plant_screen_max_hypotheses
    many = [
        hyp(i, ["BLDG-1"], "external", "C22") | {"mechanism": f"m{i}"} for i in range(1, most + 2)
    ]
    run_id, transport = world.screen({"hypotheses": many})
    assert len(transport.sent) == 2
    assert world.runs.hypotheses(run_id) == []


def test_ranks_unique_one_to_n_and_no_duplicate_ids_or_the_answer_is_retried(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    (tmp_path / "gap").mkdir()
    gap = World(tmp_path / "gap", ref, config)
    run_id, transport = gap.screen({"hypotheses": [GOOD_1, GOOD_2 | {"rank": 3}]})
    assert len(transport.sent) == 2 and gap.runs.hypotheses(run_id) == []
    (tmp_path / "twice").mkdir()
    twice = World(tmp_path / "twice", ref, config)
    run_id, _ = twice.screen({"hypotheses": [GOOD_1, GOOD_1 | {"rank": 1}]})
    assert twice.runs.hypotheses(run_id) == []


def test_input_holds_the_plant_and_no_case_package_or_key_text(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """G17: the plant record without its plant ID, provenance or any source path, which on a
    dev case name the case file; the notes' own words stay."""
    g = World(tmp_path, ref, config, CASE_G)
    _, transport = g.screen({"hypotheses": []})
    content = transport.sent[0][1]["messages"][0]["content"]
    match = re.search(r"<plant>\s*(.*?)\s*</plant>", content, re.S)
    assert match is not None
    plant = json.loads(match.group(1))
    assert "case_g" not in content and "cases/dev" not in content and ".md" not in content
    assert "plant_id" not in plant and "provenance" not in plant
    note = next(n for e in plant["equipment"] for n in e.get("notes", []))
    assert set(note) == {"text"}
    assert "P-G-CHARGE-2" in content and "KOH-EMULSIFIER" in content
    causes = json.loads(re.search(r"<causes>\s*(.*?)\s*</causes>", content, re.S).group(1))  # type: ignore[union-attr]
    assert causes and "C10" not in {c["id"] for c in causes}  # R46-filtered (Q7)


def test_hypothesis_events_record_what_was_added_and_dropped(world: World) -> None:
    run_id, _ = world.screen({"hypotheses": [GOOD_1, hyp(2, ["TANK-9"], "tank", "C21")]})
    assert [a["rank"] for a in world.events(run_id, EventType.HYPOTHESIS_ADDED)] == [1]
    assert [d["rank"] for d in world.events(run_id, EventType.HYPOTHESIS_DROPPED)] == [2]


def test_a_hypothesis_is_stored_once_and_never_rewritten(world: World) -> None:
    from guideword.runs.store import EMITTED_EVENT_TYPES  # noqa: PLC0415

    assert {EventType.HYPOTHESIS_ADDED, EventType.HYPOTHESIS_DROPPED} <= EMITTED_EVENT_TYPES
    run_id, _ = world.screen({"hypotheses": [GOOD_1]})
    [stored] = world.runs.hypotheses(run_id)
    with pytest.raises(ValueError, match="already stored"), world.runs.step(run_id) as writer:
        writer.add_hypothesis(stored.model_copy(update={"reason": "changed"}))
    assert world.runs.hypotheses(run_id) == [stored]


# --- B (Q6 amended, R50 review): after the retry, the attempt with more valid hypotheses ------


def two_attempts(world: World, first: Any, second: Any) -> tuple[str, Any]:
    """The first request gets `first`; the retry (it carries the error) gets `second`."""

    def script(job: str, request: dict[str, Any]) -> Any:
        return reply(second if len(request["messages"]) > 2 else first)

    gateway, transport = fake_gateway(
        world.config,
        script,
        sessions=world.sessions,
        ledger_path=world.tmp / "l.jsonl",
        clock=lambda: NOW,
    )
    run = start_case(world.plants, world.runs, world.ref, world.config, world.record.id, 1.0)
    advance(
        world.runs,
        run.id,
        steppers_for(gateway, world.config, world.ref, world.record.plant_file),
    )
    return run.id, transport


BAD_2 = hyp(2, ["TANK-9"], "tank", "C21")
BAD_3 = hyp(3, ["TANK-9"], "tank", "C21") | {"mechanism": "another"}


def test_a_worse_retry_does_not_replace_a_better_first_attempt(world: World) -> None:
    first = {"hypotheses": [GOOD_1, GOOD_2, BAD_3]}  # two valid
    second = {"hypotheses": [GOOD_1, BAD_2]}  # one valid
    run_id, transport = two_attempts(world, first, second)
    assert len(transport.sent) == 2
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1, 2]
    assert [d["rank"] for d in world.events(run_id, EventType.HYPOTHESIS_DROPPED)] == [3]


def test_a_better_retry_is_kept(world: World) -> None:
    first = {"hypotheses": [GOOD_1, BAD_2]}
    second = {"hypotheses": [GOOD_1, GOOD_2]}
    run_id, _ = two_attempts(world, first, second)
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1, 2]
    assert world.events(run_id, EventType.HYPOTHESIS_DROPPED) == []


def test_a_tie_keeps_the_first_attempt(world: World) -> None:
    first = {"hypotheses": [GOOD_1, BAD_2]}  # one valid, one dropped
    second = {"hypotheses": [GOOD_2 | {"rank": 1}]}  # one valid
    run_id, _ = two_attempts(world, first, second)
    [kept] = world.runs.hypotheses(run_id)
    assert kept.component_ids == GOOD_1["component_ids"]
    assert [d["rank"] for d in world.events(run_id, EventType.HYPOTHESIS_DROPPED)] == [2]


def test_an_attempt_invalid_as_a_whole_is_never_chosen(world: World) -> None:
    first = {"hypotheses": [GOOD_1, GOOD_2 | {"rank": 3}]}  # ranks 1, 3: invalid as a whole
    second = {"hypotheses": [GOOD_1, BAD_2]}
    run_id, _ = two_attempts(world, first, second)
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1]
