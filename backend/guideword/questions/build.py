"""The question builder (spec 1.4; PROJECT.md §5 Step 3): complete by construction.

Code builds every question from the plant file, the section set and the reference tables.
The output is pure and deterministic: sorted by list (QuestionKind order), then by ID, and
every question starts `open`. Nothing here removes a question.
"""

from itertools import combinations

from guideword.questions import text
from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import (
    EquipmentType,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    SectionKind,
)
from guideword.schema.plant import PlannedWork, Plant
from guideword.schema.records import Question, Section

MATRIX_KINDS = {SectionKind.EQUIPMENT, SectionKind.LINE, SectionKind.NO_FLOW_LINE}
DUST_TYPES = {EquipmentType.SOLIDS_HANDLER, EquipmentType.DRYER}
LIST_ORDER = list(QuestionKind)


def build_questions(
    plant: Plant, sections: list[Section], ref: ReferenceSet, run_id: str
) -> list[Question]:
    questions: list[Question] = []

    def add(question_id: str, kind: QuestionKind, section_id: str | None, body: str) -> None:
        origin = QuestionOrigin.MATRIX if kind == QuestionKind.MATRIX else QuestionOrigin.CROSS_LIST
        questions.append(
            Question(
                id=question_id,
                run_id=run_id,
                kind=kind,
                origin=origin,
                status=QuestionStatus.OPEN,
                section_id=section_id,
                text=body,
            )
        )

    def section_of(object_id: str, kinds: set[SectionKind]) -> str | None:
        """The lowest-ID section of one of `kinds` that contains the object (Q5)."""
        found = [s.id for s in sections if s.kind in kinds and object_id in s.object_ids]
        return min(found) if found else None

    # 1. guideword x parameter matrix, filtered by section type
    for section in sections:
        if section.kind not in MATRIX_KINDS or section.section_type is None:
            continue
        for row in ref.applicability:
            if row.section_type == section.section_type:
                add(
                    ids.matrix_question_id(section.id, row.guideword, row.parameter),
                    QuestionKind.MATRIX,
                    section.id,
                    text.matrix(section.id, section.section_type, row.guideword, row.parameter),
                )

    # 2. every chemical pair, and every chemical with water, air and heat
    chemicals = sorted(plant.chemicals, key=lambda c: c.id)
    for a, b in combinations(chemicals, 2):
        add(
            ids.pair_question_id(a.id, b.id),
            QuestionKind.CHEMICAL_PAIR,
            None,
            text.chemical_pair(a.id, a.name, b.id, b.name),
        )
    for chemical in chemicals:
        for environment in ids.ENVIRONMENT_KINDS:
            add(
                ids.environment_question_id(chemical.id, environment),
                QuestionKind.CHEMICAL_ENVIRONMENT,
                None,
                text.chemical_environment(chemical.id, chemical.name, environment),
            )

    # 3. every no-flow line
    line_kinds = {SectionKind.LINE, SectionKind.NO_FLOW_LINE}
    for line in plant.lines:
        if line.no_flow:
            add(
                ids.no_flow_question_id(line.id),
                QuestionKind.NO_FLOW_LINE,
                section_of(line.id, line_kinds),
                text.no_flow_line(line.id, [n.value for n in line.no_flow]),
            )

    # 4. every procedure step x the procedure guidewords
    for procedure in plant.procedures:
        section_id = section_of(procedure.id, {SectionKind.PROCEDURE})
        for step in procedure.steps:
            for guideword in ref.procedure_guidewords:
                add(
                    ids.procedure_question_id(step.id, guideword),
                    QuestionKind.PROCEDURE_STEP,
                    section_id,
                    text.procedure_step(step.id, procedure.id, procedure.kind.value, guideword),
                )

    # 5. every planned job x what is within reach (the job itself when nothing is)
    for job in plant.planned_work:
        section_id = section_of(job.id, {SectionKind.PLANNED_WORK})
        for target in within_reach(plant, job) or [job.id]:
            add(
                ids.work_question_id(job.id, target),
                QuestionKind.PLANNED_WORK,
                section_id,
                text.planned_work(job.id, job.type.value, target),
            )

    # 6. dust and ignition, each equipment item once
    dusty = {c.id for c in plant.chemicals if c.combustible_dust}
    for equipment in plant.equipment:
        if equipment.type in DUST_TYPES or dusty & set(equipment.contents):
            add(
                ids.dust_question_id(equipment.id),
                QuestionKind.DUST,
                section_of(equipment.id, {SectionKind.EQUIPMENT}),
                text.dust(equipment.id, equipment.type.value),
            )

    # 7. every relief device x where it discharges
    for device in plant.relief_devices:
        add(
            ids.relief_question_id(device.id),
            QuestionKind.RELIEF_DISCHARGE,
            section_of(device.protects_id, {SectionKind.EQUIPMENT}),
            text.relief_discharge(device.id, device.protects_id),
        )

    return sorted(questions, key=lambda q: (LIST_ORDER.index(q.kind), q.id))


def within_reach(plant: Plant, job: PlannedWork) -> list[str]:
    """Everything within reach of a planned job, sorted; empty when nothing is.

    Its listed equipment and lines; at its location: every equipment item, every line with an
    endpoint there (an equipment item or utility located there, or the location itself), every
    relief device discharging there (P9), and every other job whose window overlaps (Q4). A
    job without a location shares a location with no other job (P4).
    """
    reach = set(job.equipment_ids) | set(job.line_ids)
    location = job.location_id
    if location is not None:
        equipment_there = {e.id for e in plant.equipment if e.location_id == location}
        # a line endpoint is "there" when it is the location itself or located there
        there = (
            {location}
            | equipment_there
            | {u.id for u in plant.utilities if u.location_id == location}
        )
        reach |= equipment_there
        reach |= {line.id for line in plant.lines if {line.from_id, line.to_id} & there}
        reach |= {
            d.id
            for d in plant.relief_devices
            if d.discharge is not None and d.discharge.location_id == location
        }
        reach |= {
            other.id
            for other in plant.planned_work
            if other.id != job.id and other.location_id == location and _overlap(job, other)
        }
    return sorted(reach)


def _overlap(a: PlannedWork, b: PlannedWork) -> bool:
    """Touching windows overlap; a missing time or mixed time zones cannot rule it out (Q4)."""
    if a.start is None or a.end is None or b.start is None or b.end is None:
        return True
    try:
        return a.start <= b.end and b.start <= a.end
    except TypeError:
        # comparing a time with a zone to one without
        return True
