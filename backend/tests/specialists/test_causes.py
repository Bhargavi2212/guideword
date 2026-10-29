"""The three cause rows added after the held-out benchmark (Phase 7 spec 7.1, 7.2): slow and
hidden failures the library did not name. Each is offered the way the older rows are (R7, R46):
only where the batch's questions fit its `applies_to`, and only when the context holds an ID
that can fail as its type."""

import json
from pathlib import Path

import pytest

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import Agent, QuestionKind
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.causes import offered_cause_ids
from guideword.specialists.context import SpecialistContext

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
CORROSION, PASSING_VALVE, UNREVIEWED_CHANGE = "C27", "C28", "C29"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def world(ref: ReferenceSet) -> tuple[Plant, dict[str, Section], dict[str, Question]]:
    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    sections = rule_cut(plant, "plant:x:0")
    return (
        plant,
        {s.id: s for s in sections},
        {q.id: q for q in build_questions(plant, sections, ref, "run:test")},
    )


def _context(
    citable: frozenset[str] = frozenset(), packet: frozenset[str] = frozenset()
) -> SpecialistContext:
    return SpecialistContext(
        agent=Agent.PIPING,
        data={},
        citable_ids=citable,
        safeguard_ids=frozenset(),
        packet_ids=packet,
    )


def _offered(
    world: tuple[Plant, dict[str, Section], dict[str, Question]],
    ref: ReferenceSet,
    question_ids: list[str],
    context: SpecialistContext,
) -> set[str]:
    plant, sections, questions = world
    return offered_cause_ids([questions[q] for q in question_ids], sections, plant, ref, context)


def test_the_three_rows_exist_with_their_types(ref: ReferenceSet) -> None:
    rows = {c.id: c for c in ref.causes}
    assert rows[CORROSION].failing_component_type == "pipe"
    assert rows[PASSING_VALVE].failing_component_type == "control_loop"
    assert rows[UNREVIEWED_CHANGE].failing_component_type == "operator"
    assert "pipe" in rows[CORROSION].applies_to
    assert {"heat_exchanger", "column", "pipe"} <= set(rows[PASSING_VALVE].applies_to)
    assert {"reactor", "procedure", "pipe"} <= set(rows[UNREVIEWED_CHANGE].applies_to)


def test_corrosion_is_offered_on_a_line_batch_with_a_citable_line(world, ref) -> None:  # type: ignore[no-untyped-def]
    line_question = "m:S-L-12:as_well_as:composition"
    assert CORROSION in _offered(world, ref, [line_question], _context(citable=frozenset({"L-12"})))
    # a line section whose context cites no line cannot support it (R46)
    assert CORROSION not in _offered(
        world, ref, [line_question], _context(citable=frozenset({"MX-1"}))
    )
    # a mixer section is not a pipe (R7)
    assert CORROSION not in _offered(
        world,
        ref,
        ["m:S-MX-1:as_well_as:composition"],
        _context(citable=frozenset({"L-12", "MX-1"})),
    )


def test_passing_control_valve_is_offered_only_with_a_citable_loop(world, ref) -> None:  # type: ignore[no-untyped-def]
    mixer_question = "m:S-MX-1:as_well_as:composition"
    for loop_part in ("TV-1", "TIC-1", "TT-1"):
        assert PASSING_VALVE in _offered(
            world, ref, [mixer_question], _context(citable=frozenset({loop_part}))
        )
    # a manual or block valve is not a control loop: the row cannot name it (see spec, not in scope)
    assert PASSING_VALVE not in _offered(
        world, ref, [mixer_question], _context(citable=frozenset({"HV-12", "XV-STM", "MX-1"}))
    )


def test_unreviewed_change_is_offered_on_procedure_and_equipment_batches(world, ref) -> None:  # type: ignore[no-untyped-def]
    packet = _context(packet=frozenset({"P-CHARGE-1"}))
    assert UNREVIEWED_CHANGE in _offered(world, ref, ["proc:P-CHARGE-1:early"], packet)
    assert UNREVIEWED_CHANGE in _offered(world, ref, ["m:S-MX-1:as_well_as:composition"], packet)
    assert UNREVIEWED_CHANGE in _offered(world, ref, ["m:S-L-12:as_well_as:composition"], packet)
    # an operator cause names a step or job: with no packet there is nothing it may name (R40)
    assert UNREVIEWED_CHANGE not in _offered(
        world, ref, ["proc:P-CHARGE-1:early"], _context(citable=frozenset({"MX-1"}))
    )


def test_new_causes_follow_r46_like_the_old_ones(world, ref) -> None:  # type: ignore[no-untyped-def]
    _, _, questions = world
    one_of_each = [
        next(q.id for q in questions.values() if q.kind == kind)
        for kind in (QuestionKind.MATRIX, QuestionKind.PROCEDURE_STEP, QuestionKind.CHEMICAL_PAIR)
    ]
    assert _offered(world, ref, one_of_each, _context()) == set()
