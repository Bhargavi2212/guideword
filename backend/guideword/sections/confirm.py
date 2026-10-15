"""Checks on a confirmed section set (spec 1.3; plan P6, Q1, Q9).

The engineer may rename, regroup, split and merge, but can never silently drop a plant
object or a stretch of line the rule cut drew. Each issue names the section or plant object
it is about; the message does not repeat that ID.
"""

from collections import Counter
from collections.abc import Collection, Mapping

from guideword.schema import ids
from guideword.schema.enums import SectionKind, SectionType
from guideword.schema.plant import Equipment, Line, Plant
from guideword.schema.records import Section
from guideword.schema.validate import Issue

LINE_KINDS = {SectionKind.LINE, SectionKind.NO_FLOW_LINE}


def check_confirmed(plant: Plant, plant_record_id: str, sections: list[Section]) -> list[Issue]:
    issues: list[Issue] = []

    def issue(code: str, object_id: str, message: str) -> None:
        issues.append(Issue(code, object_id, message))

    equipment = {e.id: e for e in plant.equipment}
    lines = {line.id: line for line in plant.lines}
    procedures = {p.id for p in plant.procedures}
    jobs = {w.id for w in plant.planned_work}
    components = {c for line in plant.lines for c in line.components}
    known = equipment.keys() | lines.keys() | procedures | jobs | components

    # each section on its own
    counts = Counter(s.id for s in sections)
    for section_id, n in counts.items():
        if n > 1:
            issue("duplicate_section_id", section_id, f"used by {n} sections")
    for s in sections:
        if s.plant_record_id != plant_record_id:
            issue("section_of_other_plant", s.id, f"belongs to {s.plant_record_id}")
            continue
        problem = _id_problem(s, lines.keys())
        if problem is not None:
            issue(*problem)
        if s.drawn_by == "engineer":
            unknown = [o for o in s.object_ids if o not in known]
            if unknown:
                issue(
                    "engineer_section_unknown_object",
                    s.id,
                    f"covers {', '.join(unknown)}, not in the plant; upload a new plant file "
                    "for a new procedure or job",
                )
                continue
        if s.kind != SectionKind.PLANNED_WORK and s.section_type is None:
            issue("section_type_missing", s.id, f"a {s.kind.value} section needs a section type")
            continue
        if not _fits(s, equipment, lines, procedures, jobs):
            issue(
                "section_objects_do_not_fit",
                s.id,
                f"its objects do not fit a {s.kind.value} section of type {s.section_type}",
            )

    own = [s for s in sections if s.plant_record_id == plant_record_id]
    covered = {o for s in own for o in s.object_ids}

    # every equipment item, line, procedure and job is in a section
    missing = [*equipment, *lines, *sorted(procedures), *sorted(jobs)]
    for object_id in missing:
        if object_id not in covered:
            issue("object_not_in_section", object_id, "is in no section")

    # no-flow lines keep their own flagged section
    for line in plant.lines:
        if (
            line.no_flow
            and line.id in covered
            and not any(
                s.kind == SectionKind.NO_FLOW_LINE and s.flagged_no_flow and line.id in s.object_ids
                for s in own
            )
        ):
            issue(
                "no_flow_line_not_own_section", line.id, "a no-flow line is its own flagged section"
            )

    # nothing the rule cut drew is dropped (Q9)
    for e in plant.equipment:
        if e.id in covered and not any(
            s.kind == SectionKind.EQUIPMENT
            and s.section_type == SectionType(e.type.value)
            and e.id in s.object_ids
            for s in own
        ):
            issue(
                "equipment_not_in_own_section", e.id, f"is in no {e.type.value} equipment section"
            )
    for line in plant.lines:
        if line.id not in covered:
            continue
        line_sections = [s for s in own if s.kind in LINE_KINDS and line.id in s.object_ids]
        for component in line.components:
            if not any(component in s.object_ids for s in line_sections):
                issue(
                    "line_component_not_in_line_section",
                    component,
                    f"is in no section of line {line.id}",
                )
        if not any(s.id == ids.section_id(line.id) for s in line_sections):
            issue(
                "line_first_part_missing",
                line.id,
                f"has no section {ids.section_id(line.id)} for the stretch before its first split",
            )
    return issues


def _id_problem(s: Section, line_ids: Collection[str]) -> tuple[str, str, str] | None:
    """A section ID that does not match its section (engineer ID, rule or split form)."""
    if s.id.startswith("S~eng~") or s.drawn_by == "engineer":
        try:
            expected: str | None = ids.engineer_section_id(s.object_ids)
        except ValueError:
            expected = None
        if s.drawn_by != "engineer" or s.id != expected:
            return (
                "engineer_section_id_mismatch",
                s.id,
                f"an engineer-added section's ID is {expected}",
            )
        return None
    head, _, tail = s.id.removeprefix("S-").partition("~")
    if head not in s.object_ids or (tail and (head not in line_ids or tail not in s.object_ids)):
        return ("invalid_section_id", s.id, "does not name an object in the section")
    return None


def _fits(
    s: Section,
    equipment: Mapping[str, Equipment],
    lines: Mapping[str, Line],
    procedures: set[str],
    jobs: set[str],
) -> bool:
    """Q1: a section's objects fit its kind and type."""
    objects = s.object_ids
    if not objects:
        return False
    if s.kind == SectionKind.EQUIPMENT:
        return all(
            o in equipment and SectionType(equipment[o].type.value) == s.section_type
            for o in objects
        )
    if s.kind in LINE_KINDS:
        held = [o for o in objects if o in lines]
        if len(held) != 1 or s.section_type != SectionType.PIPE:
            return False
        line = lines[held[0]]
        flagged = s.kind == SectionKind.NO_FLOW_LINE
        return (
            bool(line.no_flow) == flagged
            and s.flagged_no_flow == flagged
            and all(o in line.components for o in objects if o != line.id)
        )
    if s.kind == SectionKind.PROCEDURE:
        return (
            len(objects) == 1
            and objects[0] in procedures
            and s.section_type == SectionType.PROCEDURE
        )
    return len(objects) == 1 and objects[0] in jobs and s.section_type is None
