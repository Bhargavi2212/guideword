"""Links and support between whole-plant hypotheses and the pipeline (spec 2b.2; R50, plan C1,
A, B, Q8). Code only: question links are set when a hypothesis is made; support is computed
from the current findings whenever it is read."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Hypothesis, Question, Section
from guideword.screen.link import question_links, support, supports
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
CASE_G = REPO / "cases" / "dev" / "case_g.json"
RUN = "run:0123456789abcdef"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def world(
    path: Path, ref: ReferenceSet, **extra: Any
) -> tuple[Plant, list[Section], list[Question]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in extra.items():
        data[key] = [*data.get(key, []), *value]
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, "plant:x:0")
    return plant, sections, build_questions(plant, sections, ref, RUN)


def hypothesis(
    components: list[str],
    kind: str,
    cause: str = "C14",
    chemicals: list[str] | None = None,
    links: list[str] | None = None,
    cause_text: str | None = None,
) -> Hypothesis:
    return Hypothesis(
        id=ids.hypothesis_id(1, "test", components),
        run_id=RUN,
        rank=1,
        mechanism="test",
        component_ids=components,
        chemical_ids=chemicals or [],
        failing_component_type=kind,
        cause_id=cause,
        cause_text=cause_text,
        consequence="a release",
        reason="test",
        question_ids=links or [],
    )


def finding(
    question: str, components: list[str], kind: str, cause: str = "C14", text: str | None = None
) -> Finding:
    outside = cause == "outside_library"
    return Finding(
        id=ids.finding_id(
            question,
            "lightning",
            components,
            cause_id=None if outside else cause,
            cause_text=text if outside else None,
        ),
        run_id=RUN,
        question_id=question,
        tier="lightning",
        cause_id=cause,
        cause_text=text,
        failing_component_type=kind,
        failing_component_ids=components,
        consequence="a release",
        adequacy="unknown",
        confidence="sure",
    )


def links_for(
    plant: Plant, sections: list[Section], questions: list[Question], h: Hypothesis
) -> list[str]:
    return question_links(
        h.component_ids, h.chemical_ids, h.failing_component_type, plant, sections, questions
    )


def test_pair_hypothesis_links_the_pair_question(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["P-CHARGE-1"], "operator", chemicals=["KOH", "SIH"])
    linked = links_for(plant, sections, questions, h)
    assert "pair:KOH:SIH" in linked
    assert {"env:KOH:water", "env:SIH:heat"} <= set(linked)
    assert any(q.startswith("proc:P-CHARGE-1:") for q in linked)


def test_links_through_the_equipment_and_valves_of_a_step(ref: ReferenceSet) -> None:
    """The reverse of R40: a step names the equipment and valves it acts on."""
    plant, sections, questions = world(EXAMPLE, ref)
    linked = set(links_for(plant, sections, questions, hypothesis(["P-CHARGE-2"], "operator")))
    by_section = {s.id: set(s.object_ids) for s in sections}
    # P-1 and HV-12, and HV-12's line (G16: a valve reaches the section of its line)
    hv12_line = next(v.on_line_id for v in plant.valves if v.id == "HV-12")
    reach = {"P-1", "HV-12", hv12_line}
    on_p1 = {q.id for q in questions if q.section_id and reach & by_section[q.section_id]}
    assert on_p1 and on_p1 <= linked
    unrelated = {q.id for q in questions if q.section_id and not reach & by_section[q.section_id]}
    assert not {q for q in unrelated if not q.startswith(("proc:", "work:"))} & linked


def test_links_are_deterministic(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["P-CHARGE-1"], "operator", chemicals=["KOH", "SIH"])
    first = links_for(plant, sections, questions, h)
    assert (
        first
        == sorted(first)
        == links_for(plant, list(reversed(sections)), list(reversed(questions)), h)
    )


def test_same_pair_same_cause_supports_a_different_cause_does_not(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["P-CHARGE-1"], "operator", chemicals=["KOH", "SIH"])
    h = h.model_copy(update={"question_ids": links_for(plant, sections, questions, h)})
    by_id = {q.id: q for q in questions}
    same = finding("pair:KOH:SIH", ["P-CHARGE-2"], "operator", "C14")
    other = finding("pair:KOH:SIH", ["P-CHARGE-2"], "operator", "C15")
    assert supports(h, same, by_id)
    assert not supports(h, other, by_id)


def test_outside_library_support_needs_the_same_type(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(
        ["P-CHARGE-1"],
        "operator",
        cause="outside_library",
        chemicals=["KOH", "SIH"],
        cause_text="wrong tote",
    )
    h = h.model_copy(update={"question_ids": links_for(plant, sections, questions, h)})
    by_id = {q.id: q for q in questions}
    assert supports(
        h, finding("pair:KOH:SIH", ["P-CHARGE-1"], "operator", "outside_library", "anything"), by_id
    )
    assert not supports(
        h, finding("pair:KOH:SIH", ["TOTE-1"], "tank", "outside_library", "anything"), by_id
    )


def test_component_overlap_is_required_for_section_questions(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["TIC-1"], "control_loop", cause="C01")
    h = h.model_copy(update={"question_ids": links_for(plant, sections, questions, h)})
    by_id = {q.id: q for q in questions}
    section_q = next(q for q in h.question_ids if q.startswith("m:"))
    assert supports(h, finding(section_q, ["TIC-1"], "control_loop", "C01"), by_id)
    assert not supports(h, finding(section_q, ["TV-1"], "control_loop", "C01"), by_id)


def test_a_finding_on_an_unlinked_question_does_not_support(ref: ReferenceSet) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["TIC-1"], "control_loop", cause="C01")
    h = h.model_copy(update={"question_ids": links_for(plant, sections, questions, h)})
    unlinked = next(q.id for q in questions if q.id not in h.question_ids and q.id.startswith("m:"))
    assert not supports(
        h, finding(unlinked, ["TIC-1"], "control_loop", "C01"), {q.id: q for q in questions}
    )


def test_external_hypothesis_links_nothing_and_needs_the_same_cause_on_the_same_location(
    ref: ReferenceSet,
) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["BLDG-1"], "external", cause="C22")
    assert links_for(plant, sections, questions, h) == []
    by_id = {q.id: q for q in questions}
    anywhere = next(q.id for q in questions if q.id.startswith("m:"))
    assert supports(h, finding(anywhere, ["BLDG-1"], "external", "C22"), by_id)
    assert not supports(h, finding(anywhere, ["ROOF"], "external", "C22"), by_id)
    assert not supports(h, finding(anywhere, ["BLDG-1"], "external", "C23"), by_id)


def test_utility_hypothesis_same_for_the_same_utility(ref: ReferenceSet) -> None:
    plant, sections, questions = world(
        EXAMPLE, ref, utilities=[{"id": "UT-CW", "kind": "cooling_water"}]
    )
    h = hypothesis(["UT-CW"], "utility_cooling", cause="C07")
    assert links_for(plant, sections, questions, h) == []
    by_id = {q.id: q for q in questions}
    anywhere = next(q.id for q in questions if q.id.startswith("m:"))
    assert supports(h, finding(anywhere, ["UT-CW"], "utility_cooling", "C07"), by_id)
    assert not supports(h, finding(anywhere, ["UT-STEAM"], "utility_cooling", "C07"), by_id)


def test_support_follows_the_current_findings_and_the_record_never_changes(
    ref: ReferenceSet,
) -> None:
    plant, sections, questions = world(EXAMPLE, ref)
    h = hypothesis(["P-CHARGE-1"], "operator", chemicals=["KOH", "SIH"])
    h = h.model_copy(update={"question_ids": links_for(plant, sections, questions, h)})
    before = h.model_dump()
    one = finding("pair:KOH:SIH", ["P-CHARGE-1"], "operator", "C14")
    assert support(h, [], questions) == []
    assert support(h, [one], questions) == [one]
    assert h.model_dump() == before


def test_case_g_shape_c14_on_a_step_with_its_chemicals_links_and_is_supported_by_the_pair(
    ref: ReferenceSet,
) -> None:
    """C1: C14 on a charging step with chemicals KOH-EMULSIFIER and SIH links the pair question
    and is supported by a C14 finding on it."""
    plant, sections, questions = world(CASE_G, ref)
    assert {"KOH-EMULSIFIER", "SIH"} <= {c.id for c in plant.chemicals}
    assert "P-G-CHARGE-2" in {s.id for p in plant.procedures for s in p.steps}
    h = hypothesis(["P-G-CHARGE-2"], "operator", chemicals=["KOH-EMULSIFIER", "SIH"])
    linked = links_for(plant, sections, questions, h)
    assert "pair:KOH-EMULSIFIER:SIH" in linked
    h = h.model_copy(update={"question_ids": linked})
    pair = finding("pair:KOH-EMULSIFIER:SIH", ["P-G-CHARGE-2"], "operator", "C14")
    assert support(h, [pair], questions) == [pair]


def test_a_control_loop_reaches_the_sections_of_what_it_acts_on(ref: ReferenceSet) -> None:
    """G16: sections list equipment and lines only, so a loop, instrument, valve or relief
    device reaches a section through what it is attached to."""
    plant, sections, questions = world(EXAMPLE, ref)
    loop = plant.control_loops[0]
    linked = set(
        links_for(plant, sections, questions, hypothesis([loop.id], "control_loop", "C01"))
    )
    acts_on = {s.id for s in sections if loop.acts_on_id in s.object_ids}
    assert acts_on and {q.id for q in questions if q.section_id in acts_on} <= linked
