"""Which cause-library rows are valid for a question (decision R7): checked only against what
the question is about.

Matrix, `nf:`, `relief:` and `dust:` questions (and added or engineer ones) use their
section's type; a planned-work section counts as `planned_work`. `pair:` and `env:` have no
section and accept any library cause. `work:` accepts `planned_work` or the target's own
section type. `proc:` accepts `procedure`. `outside_library` (with its cause text) is always
allowed and is checked elsewhere.
"""

from collections.abc import Mapping

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import QuestionKind, SectionKind
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section

PLANNED_WORK = "planned_work"
PROCEDURE = "procedure"
PIPE = "pipe"


def _section_type(section: Section) -> str:
    if section.kind == SectionKind.PLANNED_WORK or section.section_type is None:
        return PLANNED_WORK
    return section.section_type.value


def _target_types(target: str, plant: Plant) -> set[str]:
    """The section type a `work:` target would have: equipment by type, a line as pipe, a
    relief device by the equipment it protects; another job adds nothing."""
    equipment = {e.id: e for e in plant.equipment}
    if target in equipment:
        return {equipment[target].type.value}
    if target in {line.id for line in plant.lines}:
        return {PIPE}
    for device in plant.relief_devices:
        if device.id == target and device.protects_id in equipment:
            return {equipment[device.protects_id].type.value}
    return set()


def valid_cause_ids(
    question: Question, sections: Mapping[str, Section], plant: Plant, ref: ReferenceSet
) -> set[str]:
    if question.kind in (QuestionKind.CHEMICAL_PAIR, QuestionKind.CHEMICAL_ENVIRONMENT):
        return {c.id for c in ref.causes}
    if question.kind == QuestionKind.PROCEDURE_STEP:
        types = {PROCEDURE}
    elif question.kind == QuestionKind.PLANNED_WORK:
        types = {PLANNED_WORK} | _target_types(ids.parse_question_id(question.id).parts[1], plant)
    else:
        section = sections.get(question.section_id) if question.section_id else None
        if section is None:
            return {c.id for c in ref.causes}
        types = {_section_type(section)}
    return {c.id for c in ref.causes if types & set(c.applies_to)}
