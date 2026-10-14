"""Plant loading, plant facts and the plant store (spec 1.1, plan P3, P10, P11, Q3)."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.plants import (
    NOT_STATED,
    PlantRepository,
    load_plant,
    not_stated_issues,
    plant_facts,
)
from guideword.schema import ids
from guideword.schema.enums import PlantStatus, SectionKind, SectionType
from guideword.schema.plant import Plant
from guideword.schema.records import PlantFact, Section

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
DEV_CASES = sorted((REPO / "cases" / "dev").glob("case_*.json"))


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


def _facts(data: dict[str, Any]) -> dict[str, PlantFact]:
    plant = Plant.model_validate(data)
    return {f.id: f for f in plant_facts(plant, "plant:test:0")}


@pytest.fixture
def repo(tmp_path: Path) -> PlantRepository:
    return PlantRepository(make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}"))


# --- load_plant ---------------------------------------------------------------------------------


def test_example_loads_with_status_uploaded(ref: ReferenceSet) -> None:
    data = _example()
    record, report = load_plant(data, ref)
    assert report.ok
    assert record is not None
    assert record.status == PlantStatus.UPLOADED
    assert record.plant_id == "example_mixing_unit"


def test_plant_with_an_error_gives_no_record(ref: ReferenceSet) -> None:
    data = _example()
    data["equipment"][0]["location_id"] = "NOWHERE"
    record, report = load_plant(data, ref)
    assert record is None
    assert not report.ok


def test_record_id_ignores_schema_defaults(ref: ReferenceSet) -> None:
    """P11: the hash is over the JSON as uploaded, not the parsed model with its defaults."""
    data = _example()
    record, _ = load_plant(data, ref)
    assert record is not None
    assert record.id == f"plant:{data['plant_id']}:{ids.h(data)}"
    with_defaults = Plant.model_validate(data).model_dump(mode="json")
    assert ids.h(with_defaults) != ids.h(data)


def test_changed_value_gives_a_new_record_id(ref: ReferenceSet) -> None:
    data = _example()
    changed = copy.deepcopy(data)
    changed["equipment"][0]["volume_m3"] = 1.5
    first, _ = load_plant(data, ref)
    second, _ = load_plant(changed, ref)
    assert first is not None and second is not None
    assert first.id != second.id


# --- plant facts --------------------------------------------------------------------------------


def test_example_facts_include_assumed_design_pressure_and_operating_limit() -> None:
    facts = _facts(_example())
    assert facts["MX-1.design_pressure_kpa"].source == "assumed"
    assert facts["MX-1.design_pressure_kpa"].value == 350
    trip = facts["MX-1.operating.temperature.trip_high"]
    assert trip.value == 60


def test_each_non_null_operating_limit_is_its_own_fact() -> None:
    facts = _facts(_example())
    operating = sorted(f for f in facts if ".operating." in f)
    assert operating == [
        "MX-1.operating.temperature.alarm_high",
        "MX-1.operating.temperature.design_max",
        "MX-1.operating.temperature.normal",
        "MX-1.operating.temperature.trip_high",
    ]


def test_value_object_is_one_fact_at_its_parent_field() -> None:
    data = _example()
    data["equipment"][2]["heat_sources"] = [{"medium": "steam", "via_line_id": "L-STM"}]
    facts = _facts(data)
    assert facts["PSV-1.discharge"].value == {
        "kind": "atmosphere",
        "location_id": "ROOF",
        "elevation_m": 12,
    }
    assert data["equipment"][2]["id"] == "MX-1"
    assert facts["MX-1.heat_sources"].value == [
        {"medium": "steam", "via_line_id": "L-STM", "isolating_valve_ids": []}
    ]
    assert not any(f.startswith("PSV-1.discharge.") for f in facts)


def test_false_boolean_is_a_fact_and_empty_list_is_not() -> None:
    facts = _facts(_example())
    assert facts["SIH.combustible_dust"].value is False
    assert "PSV-1.inlet_valve_ids" not in facts
    assert "W-1.equipment_ids" not in facts


def test_ids_notes_and_plant_level_fields_are_not_facts() -> None:
    data = _example()
    data["equipment"][0]["notes"] = [{"text": "as written", "source": "pkg"}]
    facts = _facts(data)
    assert not any(f.endswith((".id", ".notes")) for f in facts)
    assert not any(f.startswith((f"{data['plant_id']}.", "provenance.")) for f in facts)
    assert not any(f.endswith((".plant_id", ".schema_version")) for f in facts)


def test_steps_list_chemical_source_and_operating_instruments_are_not_facts() -> None:
    """Q3: but a procedure step is a plant object, so its own fields are facts."""
    facts = _facts(_example())
    assert "P-CHARGE.steps" not in facts
    assert "SIH.source" not in facts
    assert not any("instrument_id" in f for f in facts)
    assert facts["P-CHARGE-1.text"].value == "Select tote by label"
    assert facts["P-CHARGE-1.equipment_ids"].value == ["TOTE-1"]
    assert facts["P-CHARGE.kind"].value == "charging"


def test_source_order_fact_then_object_then_chemical_source() -> None:
    data = _example()
    data["provenance"]["SIH.name"] = "data sheet p. 2"
    data["provenance"]["TOTE-1"] = "drawing D-1"
    facts = _facts(data)
    assert facts["SIH.name"].source == "data sheet p. 2"
    assert facts["TOTE-1.type"].source == "drawing D-1"
    assert facts["KOH.physical_form"].source == "SDS"


def test_fact_without_provenance_is_not_stated_and_warned() -> None:
    facts = _facts(_example())
    p1 = facts["P-1.type"]
    assert p1.source == NOT_STATED
    issues = not_stated_issues(list(facts.values()))
    stated = [f for f in facts.values() if f.source != NOT_STATED]
    assert len(issues) == len(facts) - len(stated)
    issue = next(i for i in issues if i.object_id == "P-1" and "type" in i.message)
    assert issue.code == "source_not_stated"
    assert "P-1.type" in issue.message
    trip = next(i for i in issues if "trip_high" in i.message)
    assert trip.object_id == "MX-1"


def test_facts_carry_the_plant_record_id() -> None:
    plant = Plant.model_validate(_example())
    facts = plant_facts(plant, "plant:example_mixing_unit:abc")
    assert {f.plant_record_id for f in facts} == {"plant:example_mixing_unit:abc"}
    assert [f.id for f in facts] == sorted(f.id for f in facts)


@pytest.mark.parametrize("path", DEV_CASES, ids=[p.stem for p in DEV_CASES])
def test_each_dev_case_loads_with_no_errors(path: Path, ref: ReferenceSet) -> None:
    record, report = load_plant(json.loads(path.read_text(encoding="utf-8")), ref)
    assert report.errors == []
    assert record is not None
    assert plant_facts(record.plant_file, record.id)


def test_there_are_five_dev_cases() -> None:
    assert [p.stem for p in DEV_CASES] == ["case_d", "case_e", "case_f", "case_g", "case_h"]


# --- the plant store ----------------------------------------------------------------------------


def _stored(repo: PlantRepository, ref: ReferenceSet, data: dict[str, Any]) -> str:
    record, _ = load_plant(data, ref)
    assert record is not None
    repo.add(record, data, plant_facts(record.plant_file, record.id))
    return record.id


def test_same_file_twice_is_one_row(repo: PlantRepository, ref: ReferenceSet) -> None:
    first = _stored(repo, ref, _example())
    second = _stored(repo, ref, _example())
    assert first == second
    assert [p.id for p in repo.records()] == [first]


def test_get_reads_back_the_record_raw_file_and_facts(
    repo: PlantRepository, ref: ReferenceSet
) -> None:
    data = _example()
    record_id = _stored(repo, ref, data)
    stored = repo.get(record_id)
    assert stored is not None
    assert stored.record.id == record_id
    assert stored.record.status == PlantStatus.UPLOADED
    assert stored.raw == data
    assert stored.facts == plant_facts(stored.record.plant_file, record_id)
    assert stored.sections == []
    assert repo.get("plant:nothing:0") is None


def test_list_is_sorted_by_record_id(repo: PlantRepository, ref: ReferenceSet) -> None:
    ids_ = [_stored(repo, ref, json.loads(p.read_text(encoding="utf-8"))) for p in DEV_CASES]
    assert [p.id for p in repo.records()] == sorted(ids_)


def _section(record_id: str, object_id: str) -> Section:
    return Section(
        id=ids.section_id(object_id),
        plant_record_id=record_id,
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name=f"{object_id} (mixer)",
        object_ids=[object_id],
        drawn_by="rule",
    )


def test_set_sections_replaces_the_set_and_status(repo: PlantRepository, ref: ReferenceSet) -> None:
    record_id = _stored(repo, ref, _example())
    repo.set_sections(record_id, [_section(record_id, "MX-1")], PlantStatus.SECTIONS_PROPOSED)
    repo.set_sections(record_id, [_section(record_id, "TOTE-1")], PlantStatus.SECTIONS_PROPOSED)
    stored = repo.get(record_id)
    assert stored is not None
    assert [s.id for s in stored.sections] == ["S-TOTE-1"]
    assert stored.record.status == PlantStatus.SECTIONS_PROPOSED
    assert stored.record.confirmed_section_ids == []


def test_confirm_sets_the_confirmed_ids_and_a_new_set_clears_them(
    repo: PlantRepository, ref: ReferenceSet
) -> None:
    record_id = _stored(repo, ref, _example())
    sections = [_section(record_id, "MX-1"), _section(record_id, "TOTE-1")]
    repo.confirm(record_id, sections)
    stored = repo.get(record_id)
    assert stored is not None
    assert stored.record.status == PlantStatus.SECTIONS_CONFIRMED
    assert stored.record.confirmed_section_ids == ["S-MX-1", "S-TOTE-1"]
    assert stored.sections == sections
    repo.set_sections(record_id, sections[:1], PlantStatus.SECTIONS_PROPOSED)
    again = repo.get(record_id)
    assert again is not None
    assert again.record.confirmed_section_ids == []


def test_re_adding_a_stored_plant_keeps_its_status(
    repo: PlantRepository, ref: ReferenceSet
) -> None:
    record_id = _stored(repo, ref, _example())
    repo.confirm(record_id, [_section(record_id, "MX-1")])
    _stored(repo, ref, _example())
    stored = repo.get(record_id)
    assert stored is not None
    assert stored.record.status == PlantStatus.SECTIONS_CONFIRMED
