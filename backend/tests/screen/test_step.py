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
from guideword.schema.enums import BudgetUse, EventType, RunStatus

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


def without_net(config: Config) -> Config:
    """The safety net (re-ask under `plant_screen_min_valid`) switched off, for tests of
    other behaviour; the net has its own tests with the shipped minimum."""
    run = config.caps.run.model_copy(update={"plant_screen_min_valid": 0})
    return config.model_copy(update={"caps": config.caps.model_copy(update={"run": run})})


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

    def events(self, run_id: str, kind: EventType) -> list[dict[str, Any]]:
        return [e.payload for e in self.runs.events(run_id) if e.type == kind]


@pytest.fixture
def world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
    return World(tmp_path, ref, without_net(config))


@pytest.fixture
def strict_world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
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


def test_a_hypothesis_may_name_any_real_plant_id_whatever_its_type(world: World) -> None:
    """G23: the failing type is not checked against the components of a hypothesis (it is for
    every finding); a mixer, which no failing type fits, can be named."""
    pump_as_loop = hyp(2, ["P-1"], "control_loop", "C01")
    mixer = hyp(3, ["MX-1"], "tank", "outside_library", cause_text="overheats")
    run_id, transport = world.screen({"hypotheses": [GOOD_1, pump_as_loop, mixer]})
    assert len(transport.sent) == 1
    assert [h.rank for h in world.runs.hypotheses(run_id)] == [1, 2, 3]
    assert world.events(run_id, EventType.HYPOTHESIS_DROPPED) == []


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
    gap = World(tmp_path / "gap", ref, without_net(config))
    run_id, transport = gap.screen({"hypotheses": [GOOD_1, GOOD_2 | {"rank": 3}]})
    assert len(transport.sent) == 2 and gap.runs.hypotheses(run_id) == []
    (tmp_path / "twice").mkdir()
    twice = World(tmp_path / "twice", ref, without_net(config))
    run_id, _ = twice.screen({"hypotheses": [GOOD_1, GOOD_1 | {"rank": 1}]})
    assert twice.runs.hypotheses(run_id) == []


def test_input_holds_the_plant_and_no_case_package_or_key_text(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """G17: the plant record without its plant ID, provenance or any source path, which on a
    dev case name the case file; the notes' own words stay."""
    g = World(tmp_path, ref, without_net(config), CASE_G)
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
    run = start_case(
        world.plants,
        world.runs,
        world.ref,
        world.config,
        world.record.id,
        1.0,
        use=BudgetUse.DEVELOPMENT,
    )
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


def test_a_request_without_the_whole_plant_is_refused_before_any_call(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard (R50 review): the rendered request must hold one <plant> block with every
    equipment and line ID; otherwise the step fails loudly and nothing is sent."""
    from guideword.screen import step  # noqa: PLC0415

    monkeypatch.setattr(step, "plant_for_screen", lambda plant: {"equipment": []})
    with pytest.raises(step.PlantNotSent, match="P-1"):
        world.screen({"hypotheses": [GOOD_1]})


def test_the_guard_passes_on_every_dev_plant(
    ref: ReferenceSet, config: Config, tmp_path: Path
) -> None:
    from guideword.schema.plant import Plant  # noqa: PLC0415
    from guideword.screen.step import PlantScreenStepper, check_plant_sent  # noqa: PLC0415

    gateway, _ = fake_gateway(
        config,
        lambda job, request: None,
        sessions=make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}"),
        ledger_path=tmp_path / "l.jsonl",
        clock=lambda: NOW,
    )
    for letter in "defgh":
        path = REPO / "cases" / "dev" / f"case_{letter}.json"
        plant = Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))
        stepper = PlantScreenStepper(gateway, config=config, ref=ref, plant=plant)
        check_plant_sent(stepper.messages(["matrix"]), plant)


# --- the run marker and the safety net (R50 review, after the cached-prefix answers) ---------


def many(n: int) -> list[dict[str, Any]]:
    """n valid hypotheses on the example plant, all different."""
    return [hyp(i, ["BLDG-1"], "external", "C22") | {"mechanism": f"m{i}"} for i in range(1, n + 1)]


def by_marker(
    world: World, first: Any, reask: Any, cap: float = 1.0, **reply_extra: Any
) -> tuple[str, Any]:
    def script(job: str, request: dict[str, Any]) -> Any:
        line = request["messages"][0]["content"].split("\n", 1)[0]
        return reply(reask if line.endswith(":reask") else first, **reply_extra)

    gateway, transport = fake_gateway(
        world.config,
        script,
        sessions=world.sessions,
        ledger_path=world.tmp / "l.jsonl",
        clock=lambda: NOW,
    )
    run = start_case(
        world.plants,
        world.runs,
        world.ref,
        world.config,
        world.record.id,
        cap,
        use=BudgetUse.DEVELOPMENT,
    )
    advance(
        world.runs, run.id, steppers_for(gateway, world.config, world.ref, world.record.plant_file)
    )
    return run.id, transport


def first_line(request: dict[str, Any]) -> str:
    return str(request["messages"][0]["content"]).split("\n", 1)[0]


def notes(world: World, run_id: str) -> list[str]:
    return [
        d["reason"] for d in world.events(run_id, EventType.HYPOTHESIS_DROPPED) if d["rank"] is None
    ]


def test_the_request_carries_the_run_marker_first_and_enough_valid_needs_no_reask(
    strict_world: World,
) -> None:
    run_id, transport = by_marker(strict_world, {"hypotheses": many(5)}, None)
    [(_, request)] = transport.sent
    assert first_line(request) == f"Request marker: {run_id}"
    assert len(strict_world.runs.hypotheses(run_id)) == 5 and notes(strict_world, run_id) == []


def test_under_the_minimum_a_fresh_reask_is_sent_and_a_better_answer_kept(
    strict_world: World,
) -> None:
    run_id, transport = by_marker(strict_world, {"hypotheses": many(2)}, {"hypotheses": many(6)})
    assert len(transport.sent) == 2
    reask = transport.sent[1][1]
    assert first_line(reask) == f"Request marker: {run_id}:reask"
    assert len(reask["messages"]) == 2  # a fresh conversation, not a continuation
    assert len(strict_world.runs.hypotheses(run_id)) == 6 and notes(strict_world, run_id) == []


def test_still_short_keeps_the_attempt_with_most_and_records_degraded(strict_world: World) -> None:
    run_id, _ = by_marker(strict_world, {"hypotheses": many(3)}, {"hypotheses": many(2)})
    assert len(strict_world.runs.hypotheses(run_id)) == 3
    assert notes(strict_world, run_id) == ["screen degraded: 3 kept"]


def test_nothing_valid_anywhere_keeps_zero_and_records_degenerate(strict_world: World) -> None:
    run_id, _ = by_marker(strict_world, {"hypotheses": []}, {"hypotheses": []})
    assert strict_world.runs.hypotheses(run_id) == []
    assert notes(strict_world, run_id) == ["screen degenerate: no valid hypothesis"]
    run = strict_world.runs.get(run_id)
    assert run is not None and run.step == "analysis"


def test_a_reask_refused_at_the_cap_is_recorded_and_the_run_goes_on(strict_world: World) -> None:
    """The first answer is billed near max_tokens, so the re-ask no longer fits the cap."""
    run_id, transport = by_marker(
        strict_world,
        {"hypotheses": many(2)},
        {"hypotheses": many(6)},
        cap=0.06,
        output_tokens=12000,
    )
    assert len(transport.sent) == 1
    assert "screen degenerate: re-ask refused at cap" in notes(strict_world, run_id)
    assert len(strict_world.runs.hypotheses(run_id)) == 2
    run = strict_world.runs.get(run_id)
    assert run is not None and run.status == RunStatus.RUNNING and run.step == "analysis"
