"""The specialist answer schema, cause validity and the answer checks (spec 2.4; plan R7, R8,
R40, R41)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import Agent, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.causes import valid_cause_ids
from guideword.specialists.context import build_context
from guideword.specialists.schema import BatchAnswer, check_answer

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def world(ref: ReferenceSet) -> tuple[Plant, dict[str, Section], dict[str, Question]]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["chemicals"].append({"id": "FLOUR", "name": "flour", "combustible_dust": True})
    data["equipment"].append(
        {"id": "D-1", "type": "dryer", "location_id": "BLDG-1", "contents": ["FLOUR"]}
    )
    data["lines"][0]["no_flow"] = ["standby"]
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, "plant:x:0")
    questions = build_questions(plant, sections, ref, "run:test")
    return plant, {s.id: s for s in sections}, {q.id: q for q in questions}


# --- cause validity (R7) ----------------------------------------------------------------------


def _valid(world: Any, ref: ReferenceSet, question_id: str) -> set[str]:
    plant, sections, questions = world
    return valid_cause_ids(questions[question_id], sections, plant, ref)


def test_matrix_question_uses_its_section_type(world: Any, ref: ReferenceSet) -> None:
    valid = _valid(world, ref, "m:S-MX-1:more:pressure")
    expected = {c.id for c in ref.causes if "mixer" in c.applies_to}
    assert valid == expected
    assert "C14" in valid and "C04" not in valid  # C04 applies to pumps and pipes


def test_no_flow_relief_and_dust_use_their_section_type(world: Any, ref: ReferenceSet) -> None:
    assert _valid(world, ref, "nf:L-12") == {c.id for c in ref.causes if "pipe" in c.applies_to}
    assert _valid(world, ref, "relief:PSV-1") == {
        c.id for c in ref.causes if "mixer" in c.applies_to
    }
    assert _valid(world, ref, "dust:D-1") == {c.id for c in ref.causes if "dryer" in c.applies_to}


def test_pair_and_environment_questions_accept_any_library_cause(
    world: Any, ref: ReferenceSet
) -> None:
    every = {c.id for c in ref.causes}
    assert _valid(world, ref, "pair:KOH:SIH") == every
    assert _valid(world, ref, "env:SIH:water") == every


def test_procedure_step_questions_use_procedure_causes(world: Any, ref: ReferenceSet) -> None:
    assert _valid(world, ref, "proc:P-CHARGE-1:skipped") == {
        c.id for c in ref.causes if "procedure" in c.applies_to
    }


def test_work_questions_use_planned_work_or_the_targets_type(world: Any, ref: ReferenceSet) -> None:
    """W-1's target is PSV-1, which protects the mixer MX-1."""
    assert _valid(world, ref, "work:W-1:PSV-1") == {
        c.id for c in ref.causes if {"planned_work", "mixer"} & set(c.applies_to)
    }


# --- the schema -----------------------------------------------------------------------------


def _finding(**changes: Any) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "cause_id": "C01",
        "cause_text": None,
        "failing_component_type": "control_loop",
        "failing_component_ids": ["TIC-1"],
        "consequence": "steam keeps heating the mixer",
        "safeguard_ids": ["SG-TRIP"],
        "adequacy": "unknown",
        "confidence": "sure",
        "reason": "TV-1 fails open (TIC-1)",
    }
    finding.update(changes)
    return finding


def _answer(*answers: dict[str, Any], added: list[dict[str, Any]] | None = None) -> BatchAnswer:
    return BatchAnswer.model_validate({"answers": list(answers), "added_questions": added or []})


def _one(
    question_id: str, *findings: dict[str, Any], not_credible: str | None = None
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "not_credible": {"reason": not_credible} if not_credible else None,
        "findings": list(findings),
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"consequence": "x" * 301},
        {"reason": ""},
        {"cause_text": "y" * 201},
        {"failing_component_ids": []},
        {"failing_component_type": "gremlin"},
        {"adequacy": "fine"},
        {"confidence": "maybe"},
    ],
)
def test_schema_caps_and_enums(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _answer(_one("m:S-MX-1:more:pressure", _finding(**bad)))


def test_schema_fields_are_all_required_for_strict_output() -> None:
    schema = BatchAnswer.model_json_schema()
    finding = schema["$defs"]["FindingAnswer"]
    assert set(finding["required"]) == set(finding["properties"])
    assert finding.get("additionalProperties") is False


# --- the answer checks --------------------------------------------------------------------------


def _check(
    world: Any, ref: ReferenceSet, agent: Agent, batch: list[str], answer: BatchAnswer
) -> None:
    plant, sections, questions = world
    qs = [questions[q] for q in batch]
    ctx = build_context(agent, plant, sections, qs)
    check_answer(
        answer,
        questions=qs,
        context=ctx,
        sections=sections,
        plant=plant,
        ref=ref,
        tier=Tier.LIGHTNING,
    )


MX = "m:S-MX-1:more:pressure"


def test_a_good_answer_passes(world: Any, ref: ReferenceSet) -> None:
    _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding())))


def test_unknown_question_id_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="not in this batch"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one("m:S-MX-1:less:pressure", _finding())))


def test_duplicate_question_id_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="more than once"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding()), _one(MX, _finding())))


def test_a_missing_question_is_not_an_error(world: Any, ref: ReferenceSet) -> None:
    """It is retried alone afterwards (spec 2.4)."""
    _check(world, ref, Agent.PROCESS, [MX, "m:S-MX-1:less:pressure"], _answer(_one(MX, _finding())))


def test_both_or_neither_not_credible_and_findings_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="either"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding(), not_credible="no")))
    with pytest.raises(ValueError, match="either"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX)))


def test_not_credible_alone_passes(world: Any, ref: ReferenceSet) -> None:
    _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, not_credible="the mixer is vented")))


def test_component_not_in_context_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="not in this agent's context"):
        _check(
            world,
            ref,
            Agent.PROCESS,
            [MX],
            _answer(_one(MX, _finding(failing_component_ids=["D-1"]))),
        )


def test_cause_not_valid_for_the_question_invalid(world: Any, ref: ReferenceSet) -> None:
    """C04 (pump stops) does not apply to a mixer section."""
    bad = _finding(cause_id="C04", failing_component_type="pump", failing_component_ids=["P-1"])
    with pytest.raises(ValueError, match="C04 is not a valid cause"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, bad)))


def test_unknown_cause_id_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="C99 is not a valid cause"):
        _check(world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding(cause_id="C99"))))


def test_library_cause_keeps_its_failing_component_type(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="C01 fails a control_loop"):
        _check(
            world,
            ref,
            Agent.PROCESS,
            [MX],
            _answer(_one(MX, _finding(failing_component_type="pump"))),
        )


def test_outside_library_needs_its_cause_text(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="cause_text"):
        _check(
            world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding(cause_id="outside_library")))
        )
    _check(
        world,
        ref,
        Agent.PROCESS,
        [MX],
        _answer(_one(MX, _finding(cause_id="outside_library", cause_text="steam trap blocked"))),
    )


def test_safeguard_not_in_context_invalid(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="not a safeguard"):
        _check(
            world, ref, Agent.PROCESS, [MX], _answer(_one(MX, _finding(safeguard_ids=["TIC-1"])))
        )


def test_duplicate_finding_id_invalid(world: Any, ref: ReferenceSet) -> None:
    """R8: two findings with the same cause and components in one answer."""
    with pytest.raises(ValueError, match="same finding twice"):
        _check(
            world,
            ref,
            Agent.PROCESS,
            [MX],
            _answer(_one(MX, _finding(), _finding(consequence="other"))),
        )


def test_operator_cause_naming_a_step_outside_the_packet_is_invalid(
    world: Any, ref: ReferenceSet
) -> None:
    """R40, R41: an operator cause must name a step or job from this agent's packet."""
    operator = {"cause_id": "C14", "failing_component_type": "operator"}
    with pytest.raises(ValueError, match="procedure step or planned job"):
        _check(
            world,
            ref,
            Agent.PROCESS,
            [MX],
            _answer(_one(MX, _finding(**operator, failing_component_ids=["MX-1"]))),
        )
    # P-CHARGE-2 is in the process agent's packet for S-MX-1
    _check(
        world,
        ref,
        Agent.PROCESS,
        [MX],
        _answer(_one(MX, _finding(**operator, failing_component_ids=["P-CHARGE-2"]))),
    )


def test_chemistry_operator_cause_through_the_charging_step(world: Any, ref: ReferenceSet) -> None:
    pair = "pair:KOH:SIH"
    finding = _finding(
        cause_id="C14",
        failing_component_type="operator",
        failing_component_ids=["P-CHARGE-1"],
        safeguard_ids=[],
    )
    _check(world, ref, Agent.CHEMISTRY, [pair], _answer(_one(pair, finding)))


def test_added_question_section_must_be_in_the_batch(world: Any, ref: ReferenceSet) -> None:
    with pytest.raises(ValueError, match="S-TOTE-1"):
        _check(
            world,
            ref,
            Agent.PROCESS,
            [MX],
            _answer(_one(MX, _finding()), added=[{"section_id": "S-TOTE-1", "text": "what if"}]),
        )
