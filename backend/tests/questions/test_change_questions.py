"""The `change` question kind (Phase 9 spec 9.2): one question per recent change, built by code,
in the lowest section that holds one of the change's objects, counted in coverage, routed to
the maintenance specialist with the change in its packet and citable as an operator."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.questions.build import build_questions
from guideword.questions.coverage import coverage
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import Agent, QuestionKind
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.causes import valid_cause_ids
from guideword.specialists.context import build_context
from guideword.specialists.routing import agent_for

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
CHANGE: dict[str, Any] = {
    "id": "CH-1",
    "description": "HV-12 added on L-12 so MX-1 can be isolated for cleaning",
    "object_ids": ["HV-12", "L-12"],
    "hazard_review_done": False,
    "source": "pkg",
}
IMPAIRMENT: dict[str, Any] = {
    "id": "IMP-1",
    "safeguard_id": "SG-TRIP",
    "state": "bypassed",
    "description": "trip bypassed since commissioning",
    "source": "pkg",
}


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def world(ref: ReferenceSet, **extra: Any) -> tuple[Plant, list[Section], list[Question]]:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for key, value in extra.items():
        data[key] = [*data.get(key, []), *value]
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, "plant:x:0")
    return plant, sections, build_questions(plant, sections, ref, RUN)


def test_the_change_question_id_round_trips() -> None:
    assert ids.change_question_id("CH-1") == "chg:CH-1"
    parsed = ids.parse_question_id("chg:CH-1")
    assert parsed.kind == QuestionKind.CHANGE and parsed.parts == ("CH-1",)


def test_one_question_per_change_in_the_lowest_section_holding_one_of_its_objects(
    ref: ReferenceSet,
) -> None:
    plant, sections, questions = world(ref, changes=[CHANGE])
    changes = [q for q in questions if q.kind == QuestionKind.CHANGE]
    assert [q.id for q in changes] == ["chg:CH-1"]
    holding = sorted(s.id for s in sections if set(s.object_ids) & set(CHANGE["object_ids"]))
    assert holding and changes[0].section_id == holding[0] == "S-L-12"
    assert changes[0].status.value == "open" and changes[0].origin.value == "cross_list"


def test_a_change_on_an_unsectioned_object_has_no_section(ref: ReferenceSet) -> None:
    _, _, questions = world(ref, changes=[{**CHANGE, "object_ids": ["BLDG-1"]}])
    change = next(q for q in questions if q.kind == QuestionKind.CHANGE)
    assert change.section_id is None


def test_the_text_names_the_id_and_never_the_description(ref: ReferenceSet) -> None:
    _, _, questions = world(ref, changes=[CHANGE])
    change = next(q for q in questions if q.kind == QuestionKind.CHANGE)
    assert change.text.startswith("Change CH-1:")
    assert "cleaning" not in change.text and "HV-12" not in change.text


def test_change_questions_have_their_own_coverage_line(ref: ReferenceSet) -> None:
    _, sections, questions = world(ref, changes=[CHANGE])
    lines, _ = coverage(sections, questions)
    line = next(x for x in lines if x.list == "change")
    assert (line.total, line.checked, line.failed) == (1, 0, 0)
    assert [x.list for x in lines].index("change") == [x.list for x in lines].index(
        "planned_work"
    ) + 1


def test_change_questions_go_to_the_maintenance_specialist_with_change_causes(
    ref: ReferenceSet,
) -> None:
    plant, sections, questions = world(ref, changes=[CHANGE])
    by_id = {s.id: s for s in sections}
    change = next(q for q in questions if q.kind == QuestionKind.CHANGE)
    assert agent_for(change, by_id) == Agent.MAINTENANCE
    valid = valid_cause_ids(change, by_id, plant, ref)
    assert "C29" in valid  # a process change made without a hazard review
    assert valid < {c.id for c in ref.causes}


def test_the_maintenance_packet_carries_the_change_and_it_is_citable(ref: ReferenceSet) -> None:
    plant, sections, questions = world(ref, changes=[CHANGE])
    by_id = {s.id: s for s in sections}
    change = next(q for q in questions if q.kind == QuestionKind.CHANGE)
    context = build_context(Agent.MAINTENANCE, plant, by_id, [change])
    assert [c["id"] for c in context.data["changes"]] == ["CH-1"]
    assert context.data["changes"][0]["hazard_review_done"] is False
    assert "source" not in context.data["changes"][0]
    assert "CH-1" in context.packet_ids and "CH-1" in context.citable_ids
    assert "L-12" in [line["id"] for line in context.data["lines"]]
    assert "HV-12" in context.citable_ids


def test_a_packet_without_changes_has_no_changes_key(ref: ReferenceSet) -> None:
    plant, sections, questions = world(ref)
    by_id = {s.id: s for s in sections}
    work = next(q for q in questions if q.kind == QuestionKind.PLANNED_WORK)
    context = build_context(Agent.MAINTENANCE, plant, by_id, [work])
    assert "changes" not in context.data


def test_an_impaired_safeguard_is_shown_impaired_in_every_context(ref: ReferenceSet) -> None:
    plant, sections, questions = world(ref, impairments=[IMPAIRMENT])
    by_id = {s.id: s for s in sections}
    question = next(q for q in questions if q.id == "m:S-MX-1:more:temperature")
    context = build_context(Agent.PROCESS, plant, by_id, [question])
    guard = next(g for g in context.data["safeguards"] if g["id"] == "SG-TRIP")
    assert guard["impairments"] == [
        {"id": "IMP-1", "state": "bypassed", "description": "trip bypassed since commissioning"}
    ]
    clean = next(g for g in context.data["safeguards"] if g["id"] != "SG-TRIP")
    assert "impairments" not in clean
