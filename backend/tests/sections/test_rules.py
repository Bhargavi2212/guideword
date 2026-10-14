"""The rule-drawn first section cut (spec 1.2, plan P8)."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.schema.enums import SectionKind, SectionType
from guideword.schema.plant import Plant
from guideword.schema.records import Section
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
DEV_CASES = sorted((REPO / "cases" / "dev").glob("case_*.json"))
RECORD = "plant:example_mixing_unit:0"


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


def _cut(data: dict[str, Any]) -> dict[str, Section]:
    sections = rule_cut(Plant.model_validate(data), RECORD)
    return {s.id: s for s in sections}


def _line(data: dict[str, Any], line_id: str) -> dict[str, Any]:
    line: dict[str, Any] = next(x for x in data["lines"] if x["id"] == line_id)
    return line


def test_example_cut_is_exactly_nine_sections() -> None:
    """Hand-checked: 3 equipment, L-12 split at pump P-1, L-STM split at control valve TV-1."""
    cut = _cut(_example())
    expected: dict[str, tuple[SectionKind, SectionType | None, list[str]]] = {
        "S-MX-1": (SectionKind.EQUIPMENT, SectionType.MIXER, ["MX-1"]),
        "S-P-1": (SectionKind.EQUIPMENT, SectionType.PUMP, ["P-1"]),
        "S-TOTE-1": (SectionKind.EQUIPMENT, SectionType.TANK, ["TOTE-1"]),
        "S-L-12": (SectionKind.LINE, SectionType.PIPE, ["L-12"]),
        "S-L-12~P-1": (SectionKind.LINE, SectionType.PIPE, ["L-12", "P-1", "HV-12"]),
        "S-L-STM": (SectionKind.LINE, SectionType.PIPE, ["L-STM", "XV-STM"]),
        "S-L-STM~TV-1": (SectionKind.LINE, SectionType.PIPE, ["L-STM", "TV-1"]),
        "S-P-CHARGE": (SectionKind.PROCEDURE, SectionType.PROCEDURE, ["P-CHARGE"]),
        "S-W-1": (SectionKind.PLANNED_WORK, None, ["W-1"]),
    }
    assert {i: (s.kind, s.section_type, s.object_ids) for i, s in cut.items()} == expected
    for section in cut.values():
        assert section.drawn_by == "rule"
        assert section.plant_record_id == RECORD
        assert section.purpose is None
        assert section.suggestion_reason is None
        assert not section.flagged_no_flow


def test_cut_is_sorted_by_section_id() -> None:
    sections = rule_cut(Plant.model_validate(_example()), RECORD)
    assert [s.id for s in sections] == sorted(s.id for s in sections)


def test_section_names() -> None:
    data = _example()
    _line(data, "L-STM")["no_flow"] = ["standby"]
    cut = _cut(data)
    assert cut["S-MX-1"].name == "MX-1 (mixer)"
    assert cut["S-L-12"].name == "L-12 (pipe)"
    assert cut["S-L-12~P-1"].name == "L-12 from P-1 (pipe)"
    assert cut["S-L-STM"].name == "L-STM (no-flow line)"
    assert cut["S-P-CHARGE"].name == "P-CHARGE (procedure: charging)"
    assert cut["S-W-1"].name == "W-1 (hot_work)"


def test_no_flow_line_with_a_pump_is_one_flagged_section() -> None:
    data = _example()
    _line(data, "L-12")["no_flow"] = ["normally_closed"]
    cut = _cut(data)
    section = cut["S-L-12"]
    assert section.kind == SectionKind.NO_FLOW_LINE
    assert section.section_type == SectionType.PIPE
    assert section.flagged_no_flow
    assert section.object_ids == ["L-12", "P-1", "HV-12"]
    assert not any(i.startswith("S-L-12~") for i in cut)


def test_first_component_split_point_leaves_an_empty_first_part() -> None:
    data = _example()
    _line(data, "L-STM")["components"] = ["TV-1", "XV-STM"]
    cut = _cut(data)
    assert cut["S-L-STM"].object_ids == ["L-STM"]
    assert cut["S-L-STM~TV-1"].object_ids == ["L-STM", "TV-1", "XV-STM"]


def test_line_without_split_points_is_one_section() -> None:
    data = _example()
    _line(data, "L-STM")["components"] = ["XV-STM"]
    cut = _cut(data)
    assert cut["S-L-STM"].object_ids == ["L-STM", "XV-STM"]
    assert not any(i.startswith("S-L-STM~") for i in cut)


def test_compressor_and_heat_exchanger_are_split_points_and_other_valves_are_not() -> None:
    data = _example()
    data["equipment"] += [
        {"id": "K-1", "type": "compressor", "location_id": "BLDG-1"},
        {"id": "E-1", "type": "heat_exchanger", "location_id": "BLDG-1"},
    ]
    data["valves"] += [
        {"id": "CV-9", "kind": "check", "on_line_id": "L-12"},
        {"id": "BV-9", "kind": "block", "on_line_id": "L-12"},
    ]
    _line(data, "L-12")["components"] = ["CV-9", "K-1", "BV-9", "E-1", "HV-12"]
    cut = _cut(data)
    assert cut["S-L-12"].object_ids == ["L-12", "CV-9"]
    assert cut["S-L-12~K-1"].object_ids == ["L-12", "K-1", "BV-9"]
    assert cut["S-L-12~E-1"].object_ids == ["L-12", "E-1", "HV-12"]


def test_every_plant_object_covered_and_nothing_else() -> None:
    data = _example()
    plant = Plant.model_validate(data)
    cut = rule_cut(plant, RECORD)
    covered = {s.object_ids[0] for s in cut}
    sectioned = (
        {e.id for e in plant.equipment}
        | {line.id for line in plant.lines}
        | {p.id for p in plant.procedures}
        | {w.id for w in plant.planned_work}
    )
    assert covered == sectioned
    unsectioned = (
        {x.id for x in plant.valves}
        | {x.id for x in plant.utilities}
        | {x.id for x in plant.locations}
        | {x.id for x in plant.instruments}
        | {x.id for x in plant.safeguards}
        | {x.id for x in plant.relief_devices}
        | {x.id for x in plant.chemicals}
    )
    assert not {f"S-{i}" for i in unsectioned} & {s.id for s in cut}


def test_section_ids_parse_and_are_unique() -> None:
    sections = rule_cut(Plant.model_validate(_example()), RECORD)
    ids_ = [s.id for s in sections]
    assert len(ids_) == len(set(ids_))
    for section in sections:
        Section.model_validate(section.model_dump())


def test_planned_work_section_has_no_type() -> None:
    cut = _cut(_example())
    assert cut["S-W-1"].section_type is None


@pytest.mark.parametrize("path", DEV_CASES, ids=[p.stem for p in DEV_CASES])
def test_each_dev_case_cuts_with_unique_valid_ids(path: Path) -> None:
    plant = Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))
    sections = rule_cut(plant, f"plant:{plant.plant_id}:0")
    assert len({s.id for s in sections}) == len(sections)
    assert len(sections) >= len(plant.equipment) + len(plant.lines)
