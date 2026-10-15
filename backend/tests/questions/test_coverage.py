"""Coverage counts (spec 1.5; plan Q6)."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from guideword.api.models import CoverageList
from guideword.questions.build import build_questions
from guideword.questions.coverage import coverage
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    QuestionKind,
    QuestionStatus,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Question, Section
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
LISTS = ["sections", *(k.value for k in QuestionKind)]


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture
def built(ref: ReferenceSet) -> tuple[list[Section], list[Question]]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, "plant:example_mixing_unit:0")
    return sections, build_questions(plant, sections, ref, RUN)


def _lines(result: list[CoverageList]) -> dict[str, CoverageList]:
    return {line.list: line for line in result}


def _with(question: Question, status: QuestionStatus) -> Question:
    reason = "not credible: no path" if status == QuestionStatus.NOT_CREDIBLE else None
    return Question.model_validate(
        {**question.model_dump(), "status": status, "not_credible_reason": reason}
    )


def _finding(question: Question, confidence: Confidence, n: int = 0) -> Finding:
    return Finding(
        id=f"f:{question.id}:{n}",
        run_id=RUN,
        question_id=question.id,
        tier=Tier.SUPER,
        cause_id="C1",
        failing_component_type=FailingComponentType.PUMP,
        failing_component_ids=["P-1"],
        consequence="example",
        adequacy=Adequacy.UNKNOWN,
        confidence=confidence,
    )


def _mark(questions: list[Question], marks: dict[str, QuestionStatus]) -> list[Question]:
    return [_with(q, marks[q.id]) if q.id in marks else q for q in questions]


def test_fresh_list_is_zero_of_n_per_list(built: tuple[list[Section], list[Question]]) -> None:
    sections, questions = built
    result, failed = coverage(sections, questions)
    assert [line.list for line in result] == LISTS
    totals = {line.list: line.total for line in result}
    counts = Counter(q.kind.value for q in questions)
    assert totals == {"sections": 9, **{k: counts[k] for k in LISTS[1:]}}
    assert totals["matrix"] == 79 and totals["procedure_step"] == 10
    # on a fresh list nothing is checked; sections with no questions count as checked
    for line in result[1:]:
        assert (line.checked, line.unsure, line.failed) == (0, 0, 0)
    assert failed == []


def test_every_list_appears_even_when_empty() -> None:
    result, failed = coverage([], [])
    assert [(line.list, line.total, line.checked) for line in result] == [(n, 0, 0) for n in LISTS]
    assert failed == []


def test_answered_and_not_credible_check_failed_does_not(
    built: tuple[list[Section], list[Question]],
) -> None:
    sections, questions = built
    marked = _mark(
        questions,
        {
            "m:S-MX-1:more:pressure": QuestionStatus.ANSWERED,
            "m:S-MX-1:less:pressure": QuestionStatus.NOT_CREDIBLE,
            "m:S-MX-1:no:mixing": QuestionStatus.FAILED,
            "pair:KOH:SIH": QuestionStatus.ANSWERED,
        },
    )
    lines = _lines(coverage(sections, marked)[0])
    assert (lines["matrix"].checked, lines["matrix"].failed) == (2, 1)
    assert (lines["chemical_pair"].checked, lines["chemical_pair"].failed) == (1, 0)
    assert lines["relief_discharge"].checked == 0


def test_failed_ids_returned(built: tuple[list[Section], list[Question]]) -> None:
    sections, questions = built
    marked = _mark(
        questions,
        {"relief:PSV-1": QuestionStatus.FAILED, "m:S-P-1:no:flow": QuestionStatus.FAILED},
    )
    _, failed = coverage(sections, marked)
    assert failed == ["m:S-P-1:no:flow", "relief:PSV-1"]


def test_unsure_counts_answered_questions_with_an_unsure_finding(
    built: tuple[list[Section], list[Question]],
) -> None:
    sections, questions = built
    by_id = {q.id: q for q in questions}
    marked = _mark(
        questions,
        {
            "pair:KOH:SIH": QuestionStatus.ANSWERED,
            "env:KOH:water": QuestionStatus.ANSWERED,
            "env:SIH:air": QuestionStatus.OPEN,
        },
    )
    findings = [
        # one answered question with an unsure finding among sure ones counts once
        _finding(by_id["pair:KOH:SIH"], Confidence.SURE, 0),
        _finding(by_id["pair:KOH:SIH"], Confidence.UNSURE, 1),
        _finding(by_id["pair:KOH:SIH"], Confidence.UNSURE, 2),
        # answered and sure: not unsure
        _finding(by_id["env:KOH:water"], Confidence.SURE),
        # not answered: not unsure
        _finding(by_id["env:SIH:air"], Confidence.UNSURE),
    ]
    lines = _lines(coverage(sections, marked, findings)[0])
    assert lines["chemical_pair"].unsure == 1
    assert lines["chemical_environment"].unsure == 0
    # unsure is shown separately: the question still counts as checked
    assert lines["chemical_pair"].checked == 1


def test_section_checked_only_when_all_its_questions_are(
    built: tuple[list[Section], list[Question]],
) -> None:
    sections, questions = built
    s_p1 = [q for q in questions if q.section_id == "S-P-1"]
    assert len(s_p1) == 7
    all_but_one = {q.id: QuestionStatus.ANSWERED for q in s_p1[1:]}
    before = _lines(coverage(sections, _mark(questions, all_but_one))[0])["sections"]
    everything = {q.id: QuestionStatus.ANSWERED for q in s_p1}
    after = _lines(coverage(sections, _mark(questions, everything))[0])["sections"]
    assert after.checked == before.checked + 1


def test_section_with_no_questions_is_checked(
    built: tuple[list[Section], list[Question]],
) -> None:
    sections, questions = built
    empty = Section(
        id="S-T-9",
        plant_record_id="plant:example_mixing_unit:0",
        kind=sections[0].kind,
        section_type=sections[0].section_type,
        name="T-9 (tank)",
        object_ids=["T-9"],
        drawn_by="rule",
    )
    without = _lines(coverage(sections, questions)[0])["sections"]
    with_empty = _lines(coverage([*sections, empty], questions)[0])["sections"]
    assert (with_empty.total, with_empty.checked) == (without.total + 1, without.checked + 1)


def test_sections_line_unsure_and_failed(built: tuple[list[Section], list[Question]]) -> None:
    """Q6: sections with at least one unsure answered question, and with at least one failed."""
    sections, questions = built
    by_id = {q.id: q for q in questions}
    marked = _mark(
        questions,
        {
            "m:S-MX-1:more:pressure": QuestionStatus.ANSWERED,
            "m:S-MX-1:less:pressure": QuestionStatus.ANSWERED,
            "m:S-P-1:no:flow": QuestionStatus.FAILED,
            "m:S-P-1:more:pressure": QuestionStatus.FAILED,
            "m:S-TOTE-1:more:level": QuestionStatus.FAILED,
        },
    )
    findings = [
        _finding(by_id["m:S-MX-1:more:pressure"], Confidence.UNSURE),
        _finding(by_id["m:S-MX-1:less:pressure"], Confidence.UNSURE),
    ]
    line = _lines(coverage(sections, marked, findings)[0])["sections"]
    assert (line.unsure, line.failed) == (1, 2)


def test_coverage_leaves_its_input_whole(built: tuple[list[Section], list[Question]]) -> None:
    sections, questions = built
    copy = list(questions)
    coverage(sections, questions)
    assert questions == copy
    assert all(ids.parse_question_id(q.id) for q in questions)
