"""Changes and impairments in the whole-plant pass's links (Phase 9 spec 9.2): a hypothesis
that names a change reaches the questions of the change's objects; one that names an
impairment reaches what the impaired safeguard protects; a change can fail as an operator."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.screen.link import question_links
from guideword.screen.schema import fitting
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:0123456789abcdef"
CHANGE: dict[str, Any] = {
    "id": "CH-1",
    "description": "HV-12 added on L-12 so MX-1 can be isolated for cleaning",
    "object_ids": ["HV-12"],
    "hazard_review_done": False,
    "source": "pkg",
}
IMPAIRMENT: dict[str, Any] = {
    "id": "IMP-1",
    "safeguard_id": "SG-TRIP",
    "state": "bypassed",
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


def test_a_hypothesis_naming_a_change_links_its_objects_questions(ref: ReferenceSet) -> None:
    plant, sections, questions = world(ref, changes=[CHANGE])
    links = question_links(["CH-1"], [], "operator", plant, sections, questions)
    # HV-12 sits on L-12: the line's questions, and the change's own question
    assert "m:S-L-12:no:flow" in links
    assert "chg:CH-1" in links
    assert not any(q.startswith("m:S-TOTE-1") for q in links)


def test_a_hypothesis_naming_an_impairment_links_what_the_safeguard_protects(
    ref: ReferenceSet,
) -> None:
    plant, sections, questions = world(ref, impairments=[IMPAIRMENT])
    links = question_links(["IMP-1"], [], "interlock", plant, sections, questions)
    # SG-TRIP protects MX-1 and acts through XV-STM on L-STM
    assert "m:S-MX-1:more:temperature" in links
    assert any(q.startswith("m:S-L-STM:") for q in links)
    assert not any(q.startswith("m:S-TOTE-1") for q in links)


def test_a_change_can_fail_as_an_operator_and_an_impairment_as_nothing(ref: ReferenceSet) -> None:
    plant, _, _ = world(ref, changes=[CHANGE], impairments=[IMPAIRMENT])
    listed = fitting(plant)
    assert "CH-1" in listed["operator"]
    assert all("IMP-1" not in ids for ids in listed.values())
