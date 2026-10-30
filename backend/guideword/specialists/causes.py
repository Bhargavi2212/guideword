"""Which cause-library rows are valid for a question (decision R7): checked only against what
the question is about.

Matrix, `nf:`, `relief:` and `dust:` questions (and added or engineer ones) use their
section's type; a planned-work section counts as `planned_work`. `pair:` and `env:` have no
section and accept any library cause. `work:` accepts `planned_work` or the target's own
section type. `proc:` accepts `procedure`. `outside_library` (with its cause text) is always
allowed and is checked elsewhere.

What a cause may name (R46, the PROJECT.md §5 mapping made exact after the case D dev run):
each failing-component type fits only some plant objects. A cause is offered to a batch only
if its context holds at least one ID that fits, and the answer check requires every failing
component of a finding to fit its type. A regulator has no plant object kind, so C10 is never
offered (outside_library stays open).
"""

from collections.abc import Mapping, Sequence

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import (
    EquipmentType,
    FailingComponentType,
    QuestionKind,
    SectionKind,
    UtilityKind,
    ValveKind,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.specialists.context import SpecialistContext

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
    elif question.kind == QuestionKind.CHANGE:
        # Phase 9 (spec 9.2): the causes of work and procedures, plus those of the changed objects
        change_id = ids.parse_question_id(question.id).parts[0]
        objects = next((c.object_ids for c in plant.changes if c.id == change_id), [])
        types = {PLANNED_WORK, PROCEDURE}.union(*(_target_types(o, plant) for o in objects))
    else:
        section = sections.get(question.section_id) if question.section_id else None
        if section is None:
            return {c.id for c in ref.causes}
        types = {_section_type(section)}
    return {c.id for c in ref.causes if types & set(c.applies_to)}


T = FailingComponentType
_EQUIPMENT = {
    T.PUMP: EquipmentType.PUMP,
    T.COMPRESSOR: EquipmentType.COMPRESSOR,
    T.EXCHANGER_TUBE: EquipmentType.HEAT_EXCHANGER,
    T.TANK: EquipmentType.TANK,
    T.SOLIDS_HANDLER: EquipmentType.SOLIDS_HANDLER,
}
_UTILITY = {T.UTILITY_COOLING: UtilityKind.COOLING_WATER, T.UTILITY_POWER: UtilityKind.POWER}


def fitting_ids(component_type: str, plant: Plant) -> frozenset[str]:
    """The plant IDs that can fail as `component_type` (operator causes: see `can_fail_as`)."""
    kind = T(component_type)
    if kind in _EQUIPMENT:
        return frozenset(e.id for e in plant.equipment if e.type == _EQUIPMENT[kind])
    if kind in _UTILITY:
        return frozenset(u.id for u in plant.utilities if u.kind == _UTILITY[kind])
    if kind == T.CONTROL_LOOP:
        return frozenset(
            [c.id for c in plant.control_loops]
            + [i.id for i in plant.instruments]
            + [v.id for v in plant.valves if v.kind == ValveKind.CONTROL]
        )
    if kind == T.INTERLOCK:
        return frozenset([s.id for s in plant.logic_solvers] + [i.id for i in plant.instruments])
    if kind == T.CHECK_VALVE:
        return frozenset(v.id for v in plant.valves if v.kind == ValveKind.CHECK)
    if kind == T.RELIEF_DEVICE:
        return frozenset(r.id for r in plant.relief_devices)
    if kind == T.PIPE:
        return frozenset(line.id for line in plant.lines)
    if kind == T.HOSE:
        return frozenset(line.id for line in plant.lines if line.is_hose)
    if kind == T.EXTERNAL:
        return frozenset(loc.id for loc in plant.locations)
    # a regulator has no plant object kind; operator causes name the agent's steps and jobs
    return frozenset()


def can_fail_as(component_type: str, context: SpecialistContext, plant: Plant) -> frozenset[str]:
    """The IDs in this context a finding of `component_type` may name."""
    if T(component_type) == T.OPERATOR:
        return context.packet_ids
    return fitting_ids(component_type, plant) & context.citable_ids


def offered_cause_ids(
    questions: Sequence[Question],
    sections: Mapping[str, Section],
    plant: Plant,
    ref: ReferenceSet,
    context: SpecialistContext,
) -> set[str]:
    """The library causes valid for the batch (R7) that its context can support (R46)."""
    valid = set().union(*(valid_cause_ids(q, sections, plant, ref) for q in questions))
    return {
        c.id
        for c in ref.causes
        if c.id in valid and can_fail_as(c.failing_component_type, context, plant)
    }
