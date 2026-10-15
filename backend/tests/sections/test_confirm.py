"""The confirmed-section checks (spec 1.3; plan P6, Q1, Q9)."""

import json
from pathlib import Path
from typing import Any

from guideword.api.models import SectionSuggestion
from guideword.schema import ids
from guideword.schema.enums import SectionKind, SectionType
from guideword.schema.plant import Plant
from guideword.schema.records import Section
from guideword.sections.confirm import check_confirmed
from guideword.sections.rules import rule_cut
from guideword.sections.suggest import apply, check_suggestions

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RECORD = "plant:example_mixing_unit:0"


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


def _plant(data: dict[str, Any] | None = None) -> Plant:
    return Plant.model_validate(data if data is not None else _example())


def _cut(plant: Plant) -> list[Section]:
    return rule_cut(plant, RECORD)


def _issues(plant: Plant, sections: list[Section]) -> list[tuple[str, str | None]]:
    return [(i.code, i.object_id) for i in check_confirmed(plant, RECORD, sections)]


def _without(sections: list[Section], *section_ids: str) -> list[Section]:
    return [s for s in sections if s.id not in section_ids]


def _replace(sections: list[Section], section_id: str, **changes: Any) -> list[Section]:
    return [
        Section.model_validate({**s.model_dump(), **changes}) if s.id == section_id else s
        for s in sections
    ]


def _engineer(
    object_ids: list[str],
    kind: SectionKind,
    section_type: SectionType | None,
    section_id: str | None = None,
) -> Section:
    return Section(
        id=section_id or ids.engineer_section_id(object_ids),
        plant_record_id=RECORD,
        kind=kind,
        section_type=section_type,
        name="engineer section",
        object_ids=object_ids,
        flagged_no_flow=kind == SectionKind.NO_FLOW_LINE,
        drawn_by="engineer",
    )


def test_the_rule_cut_passes() -> None:
    plant = _plant()
    assert _issues(plant, _cut(plant)) == []


def test_every_dev_case_rule_cut_passes() -> None:
    for path in sorted((REPO / "cases" / "dev").glob("case_*.json")):
        plant = Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))
        assert check_confirmed(plant, RECORD, rule_cut(plant, RECORD)) == [], path.stem


# --- the spec's rules -------------------------------------------------------------------------


def test_object_in_no_section() -> None:
    plant = _plant()
    sections = _without(_cut(plant), "S-P-CHARGE", "S-W-1")
    assert _issues(plant, sections) == [
        ("object_not_in_section", "P-CHARGE"),
        ("object_not_in_section", "W-1"),
    ]


def test_no_flow_line_not_its_own_flagged_section() -> None:
    data = _example()
    data["lines"][0]["no_flow"] = ["dead_leg"]
    plant = _plant(data)
    sections = _replace(_cut(plant), "S-L-12", kind=SectionKind.LINE, flagged_no_flow=False)
    assert ("no_flow_line_not_own_section", "L-12") in _issues(plant, sections)


def test_invalid_section_id() -> None:
    plant = _plant()
    sections = _replace(_cut(plant), "S-TOTE-1", id="S-XX-1")
    assert _issues(plant, sections) == [("invalid_section_id", "S-XX-1")]


def test_duplicate_section_id() -> None:
    plant = _plant()
    sections = _cut(plant)
    assert _issues(plant, [*sections, sections[0]]) == [("duplicate_section_id", sections[0].id)]


def test_engineer_section_id_must_match_its_objects() -> None:
    plant = _plant()
    wrong = _engineer(["MX-1"], SectionKind.EQUIPMENT, SectionType.MIXER, "S~eng~0000000000000000")
    assert _issues(plant, [*_cut(plant), wrong]) == [
        ("engineer_section_id_mismatch", "S~eng~0000000000000000")
    ]


def test_section_type_missing() -> None:
    plant = _plant()
    sections = _replace(_cut(plant), "S-TOTE-1", section_type=None)
    assert ("section_type_missing", "S-TOTE-1") in _issues(plant, sections)


def test_section_of_another_plant() -> None:
    plant = _plant()
    sections = _replace(_cut(plant), "S-MX-1", plant_record_id="plant:other:0")
    # a section of another plant covers nothing in this one
    assert _issues(plant, sections) == [
        ("section_of_other_plant", "S-MX-1"),
        ("object_not_in_section", "MX-1"),
    ]


def test_engineer_section_must_regroup_existing_objects() -> None:
    """P6: a new procedure or job means uploading a new plant file."""
    plant = _plant()
    extra = _engineer(["MX-1", "GHOST-1"], SectionKind.EQUIPMENT, SectionType.MIXER)
    assert _issues(plant, [*_cut(plant), extra]) == [("engineer_section_unknown_object", extra.id)]


# --- Q1: objects fit the kind and type --------------------------------------------------------


def test_equipment_section_with_mixed_types_is_refused() -> None:
    plant = _plant()
    mixed = _engineer(["MX-1", "TOTE-1"], SectionKind.EQUIPMENT, SectionType.MIXER)
    assert _issues(plant, [*_cut(plant), mixed]) == [("section_objects_do_not_fit", mixed.id)]


def test_same_type_equipment_merge_is_accepted() -> None:
    data = _example()
    data["equipment"].append({"id": "P-2", "type": "pump", "location_id": "BLDG-1"})
    plant = _plant(data)
    pumps = _engineer(["P-1", "P-2"], SectionKind.EQUIPMENT, SectionType.PUMP)
    assert _issues(plant, [*_without(_cut(plant), "S-P-1", "S-P-2"), pumps]) == []


def test_line_section_with_two_lines_is_refused() -> None:
    plant = _plant()
    both = _engineer(["L-12", "L-STM"], SectionKind.LINE, SectionType.PIPE)
    assert _issues(plant, [*_cut(plant), both]) == [("section_objects_do_not_fit", both.id)]


def test_line_section_with_a_foreign_component_is_refused() -> None:
    plant = _plant()
    foreign = _engineer(["L-12", "TV-1"], SectionKind.LINE, SectionType.PIPE)
    assert _issues(plant, [*_cut(plant), foreign]) == [("section_objects_do_not_fit", foreign.id)]


def test_procedure_section_with_two_objects_is_refused() -> None:
    data = _example()
    data["procedures"].append(
        {"id": "P-DRAIN", "kind": "cleaning", "steps": [{"id": "P-DRAIN-1", "text": "Drain"}]}
    )
    plant = _plant(data)
    both = _engineer(["P-CHARGE", "P-DRAIN"], SectionKind.PROCEDURE, SectionType.PROCEDURE)
    assert _issues(plant, [*_cut(plant), both]) == [("section_objects_do_not_fit", both.id)]


def test_planned_work_section_with_two_objects_is_refused() -> None:
    data = _example()
    data["planned_work"].append({"id": "W-2", "type": "lifting", "location_id": "ROOF"})
    plant = _plant(data)
    both = _engineer(["W-1", "W-2"], SectionKind.PLANNED_WORK, None)
    assert _issues(plant, [*_cut(plant), both]) == [("section_objects_do_not_fit", both.id)]


def test_equipment_section_holding_a_line_is_refused() -> None:
    plant = _plant()
    sections = _replace(_cut(plant), "S-MX-1", object_ids=["MX-1", "L-12"])
    assert _issues(plant, sections) == [("section_objects_do_not_fit", "S-MX-1")]


def test_flowing_line_flagged_as_no_flow_is_refused() -> None:
    plant = _plant()
    sections = _replace(_cut(plant), "S-L-STM~TV-1", flagged_no_flow=True)
    assert _issues(plant, sections) == [("section_objects_do_not_fit", "S-L-STM~TV-1")]


# --- Q9: nothing the rule cut drew is dropped -------------------------------------------------


def _split(plant: Plant) -> list[Section]:
    sections = _cut(plant)
    split = SectionSuggestion(
        kind="split", section_ids=["S-L-12~P-1", "S-L-12~HV-12"], reason="new part"
    )
    valid, rejected = check_suggestions(plant, sections, [split])
    assert rejected == []
    return apply(sections, valid)


def test_valid_split_passes() -> None:
    plant = _plant()
    assert _issues(plant, _split(plant)) == []


def test_dropped_empty_first_part_fails() -> None:
    plant = _plant()
    assert _issues(plant, _without(_cut(plant), "S-L-12")) == [("line_first_part_missing", "L-12")]


def test_dropped_equipment_section_fails() -> None:
    """P-1 is still in the line part S-L-12~P-1, but not in an equipment section."""
    plant = _plant()
    assert _issues(plant, _without(_cut(plant), "S-P-1")) == [
        ("equipment_not_in_own_section", "P-1")
    ]


def test_dropped_later_part_fails() -> None:
    plant = _plant()
    assert _issues(plant, _without(_cut(plant), "S-L-12~P-1")) == [
        ("line_component_not_in_line_section", "P-1"),
        ("line_component_not_in_line_section", "HV-12"),
    ]


def test_merge_of_two_parts_of_one_line_passes() -> None:
    plant = _plant()
    sections = _cut(plant)
    merge = SectionSuggestion(kind="merge", section_ids=["S-L-12", "S-L-12~P-1"], reason="one")
    valid, _ = check_suggestions(plant, sections, [merge])
    merged = apply(sections, valid)
    assert "S-L-12~P-1" not in {s.id for s in merged}
    assert _issues(plant, merged) == []


def test_issue_messages_do_not_repeat_the_object_id() -> None:
    plant = _plant()
    for issue in check_confirmed(plant, RECORD, _without(_cut(plant), "S-L-12", "S-P-1")):
        assert issue.message
        assert not issue.message.startswith(f"{issue.object_id}:")
