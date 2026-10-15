"""The specialist answer schema and the answer checks (spec 2.4; plan R7, R8, R40, R41).

The schema is sent as strict `json_schema`, so every field is required (nullable where
optional) and no others are allowed. Code then checks the answer against the batch and the
agent's context; any failure raises `ValueError`, which the gateway turns into one retry
with the error appended, then `invalid`. The model never writes an ID: code builds them.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import Adequacy, Confidence, FailingComponentType, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Question, Section
from guideword.specialists.causes import valid_cause_ids
from guideword.specialists.context import SpecialistContext

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Text200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
OPERATOR = FailingComponentType.OPERATOR


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NotCredible(_Strict):
    reason: Text300


class FindingAnswer(_Strict):
    cause_id: str
    cause_text: Text200 | None
    failing_component_type: FailingComponentType
    failing_component_ids: Annotated[list[str], Field(min_length=1)]
    consequence: Text300
    safeguard_ids: list[str]
    adequacy: Adequacy
    confidence: Confidence
    reason: Text300


class QuestionAnswer(_Strict):
    question_id: str
    not_credible: NotCredible | None
    findings: list[FindingAnswer]


class AddedQuestion(_Strict):
    section_id: str
    text: Text200


class BatchAnswer(_Strict):
    answers: list[QuestionAnswer]
    added_questions: list[AddedQuestion]


def finding_id(question_id: str, tier: Tier, finding: FindingAnswer) -> str:
    if finding.cause_id == OUTSIDE_LIBRARY:
        return ids.finding_id(
            question_id,
            tier.value,
            finding.failing_component_ids,
            cause_text=finding.cause_text or "",
        )
    return ids.finding_id(
        question_id, tier.value, finding.failing_component_ids, cause_id=finding.cause_id
    )


def check_answer(
    answer: BatchAnswer,
    *,
    questions: Sequence[Question],
    context: SpecialistContext,
    sections: Mapping[str, Section],
    plant: Plant,
    ref: ReferenceSet,
    tier: Tier,
) -> None:
    """Raise ValueError naming the first problem; a missing question is not one (it is
    retried alone afterwards)."""
    batch = {q.id: q for q in questions}
    counts = Counter(a.question_id for a in answer.answers)
    for question_id, n in counts.items():
        if question_id not in batch:
            raise ValueError(f"{question_id} is not in this batch")
        if n > 1:
            raise ValueError(f"{question_id} is answered more than once")
    cause_types = {c.id: c.failing_component_type for c in ref.causes}
    for item in answer.answers:
        question = batch[item.question_id]
        if (item.not_credible is None) == (not item.findings):
            raise ValueError(
                f"{item.question_id}: give either not_credible or at least one finding"
            )
        valid = valid_cause_ids(question, sections, plant, ref)
        seen: set[str] = set()
        for finding in item.findings:
            _check_finding(item.question_id, finding, valid, cause_types, context)
            fid = finding_id(item.question_id, tier, finding)
            if fid in seen:
                raise ValueError(
                    f"{item.question_id}: the same finding twice (cause {finding.cause_id} on "
                    f"{', '.join(sorted(finding.failing_component_ids))}); merge them into one"
                )
            seen.add(fid)
    batch_sections = {q.section_id for q in questions if q.section_id is not None}
    for added in answer.added_questions:
        if added.section_id not in batch_sections:
            raise ValueError(
                f"added question names section {added.section_id}, not a section of this batch"
            )


def _check_finding(
    question_id: str,
    finding: FindingAnswer,
    valid: set[str],
    cause_types: Mapping[str, str],
    context: SpecialistContext,
) -> None:
    if finding.cause_id == OUTSIDE_LIBRARY:
        if not finding.cause_text:
            raise ValueError(f"{question_id}: an outside_library cause needs its cause_text")
    else:
        if finding.cause_id not in valid:
            raise ValueError(
                f"{question_id}: {finding.cause_id} is not a valid cause for this question"
            )
        if cause_types[finding.cause_id] != finding.failing_component_type:
            raise ValueError(
                f"{question_id}: {finding.cause_id} fails a {cause_types[finding.cause_id]}, "
                f"not a {finding.failing_component_type}"
            )
    unknown = [c for c in finding.failing_component_ids if c not in context.citable_ids]
    if unknown:
        raise ValueError(f"{question_id}: {', '.join(unknown)} not in this agent's context")
    if finding.failing_component_type == OPERATOR and not (
        set(finding.failing_component_ids) & context.packet_ids
    ):
        raise ValueError(
            f"{question_id}: an operator cause must name a procedure step or planned job from "
            "the context's procedure_steps or planned_jobs"
        )
    not_guards = [s for s in finding.safeguard_ids if s not in context.safeguard_ids]
    if not_guards:
        raise ValueError(
            f"{question_id}: {', '.join(not_guards)} is not a safeguard in this context"
        )
