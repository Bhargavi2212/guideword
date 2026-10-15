"""The rule-drawn first section cut (spec 1.2; PROJECT.md §5 Step 2 item 1).

One section per equipment item, line part, procedure and planned job. A line with an empty
`no_flow` is split at its split points (control valves, pumps, compressors and heat
exchangers); a line with a non-empty `no_flow` is one flagged section, never split. Every
other plant object gets no section.
"""

from guideword.schema import ids
from guideword.schema.enums import EquipmentType, SectionKind, SectionType, ValveKind
from guideword.schema.plant import Line, Plant
from guideword.schema.records import Section

SPLIT_EQUIPMENT_TYPES = {EquipmentType.PUMP, EquipmentType.COMPRESSOR, EquipmentType.HEAT_EXCHANGER}
SPLIT_VALVE_KINDS = {ValveKind.CONTROL}


def rule_cut(plant: Plant, plant_record_id: str) -> list[Section]:
    """The first cut, sorted by section ID; every section is `drawn_by: "rule"`."""
    split_points = {v.id for v in plant.valves if v.kind in SPLIT_VALVE_KINDS} | {
        e.id for e in plant.equipment if e.type in SPLIT_EQUIPMENT_TYPES
    }

    def section(
        section_id: str,
        kind: SectionKind,
        section_type: SectionType | None,
        name: str,
        object_ids: list[str],
        flagged_no_flow: bool = False,
    ) -> Section:
        return Section(
            id=section_id,
            plant_record_id=plant_record_id,
            kind=kind,
            section_type=section_type,
            name=name,
            object_ids=object_ids,
            flagged_no_flow=flagged_no_flow,
            drawn_by="rule",
        )

    sections = [
        section(
            ids.section_id(e.id),
            SectionKind.EQUIPMENT,
            SectionType(e.type.value),
            f"{e.id} ({e.type.value})",
            [e.id],
        )
        for e in plant.equipment
    ]
    for line in plant.lines:
        if line.no_flow:
            sections.append(
                section(
                    ids.section_id(line.id),
                    SectionKind.NO_FLOW_LINE,
                    SectionType.PIPE,
                    f"{line.id} (no-flow line)",
                    [line.id, *line.components],
                    flagged_no_flow=True,
                )
            )
            continue
        for first, components in _parts(line, split_points):
            if first is None:
                section_id, name = ids.section_id(line.id), f"{line.id} (pipe)"
            else:
                section_id = ids.split_section_id(line.id, first)
                name = f"{line.id} from {first} (pipe)"
            sections.append(
                section(
                    section_id, SectionKind.LINE, SectionType.PIPE, name, [line.id, *components]
                )
            )
    sections += [
        section(
            ids.section_id(p.id),
            SectionKind.PROCEDURE,
            SectionType.PROCEDURE,
            f"{p.id} (procedure: {p.kind.value})",
            [p.id],
        )
        for p in plant.procedures
    ]
    sections += [
        section(
            ids.section_id(w.id),
            SectionKind.PLANNED_WORK,
            None,
            f"{w.id} ({w.type.value})",
            [w.id],
        )
        for w in plant.planned_work
    ]
    return sorted(sections, key=lambda s: s.id)


def _parts(line: Line, split_points: set[str]) -> list[tuple[str | None, list[str]]]:
    """The line's parts in order: (split point or None for the first part, its components).

    The first part always exists, even with no components; each split point starts a part.
    """
    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    for component in line.components:
        if component in split_points:
            parts.append((component, [component]))
        else:
            parts[-1][1].append(component)
    return parts
