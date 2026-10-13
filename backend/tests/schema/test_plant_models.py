"""Plant file models (PROJECT.md §9, spec 0.5)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from guideword.schema.plant import Plant

FIXTURE = Path(__file__).parent / "fixtures" / "example_mixing_unit.json"


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def test_example_loads() -> None:
    plant = Plant.model_validate(_example())
    assert plant.plant_id == "example_mixing_unit"
    assert [u.id for u in plant.utilities] == ["UT-STEAM"]
    assert plant.chemicals[0].epa_groups == [105]


def test_round_trip_load_dump_load_is_identical() -> None:
    first = Plant.model_validate(_example())
    second = Plant.model_validate(json.loads(first.model_dump_json()))
    assert first == second


def test_unknown_field_is_rejected() -> None:
    data = _example()
    data["equipment"][0]["colour"] = "blue"
    with pytest.raises(ValidationError, match="colour"):
        Plant.model_validate(data)


def test_unknown_top_level_block_is_rejected() -> None:
    data = _example()
    data["pipes"] = []
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_old_single_point_vapour_pressure_is_gone() -> None:
    data = _example()
    data["chemicals"][0]["vapor_pressure_kpaa"] = 3.0
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_vapour_pressure_points_load() -> None:
    data = _example()
    data["chemicals"][0]["vapor_pressure_points"] = [
        {"temp_c": 20, "pressure_kpaa": 2.3},
        {"temp_c": 80, "pressure_kpaa": 47.4},
    ]
    plant = Plant.model_validate(data)
    assert plant.chemicals[0].vapor_pressure_points[1].pressure_kpaa == 47.4


@pytest.mark.parametrize("bad", ["MX.1", "MX:1", "MX~1", "MX+1", "-MX", "", "MX 1"])
def test_reserved_characters_rejected_in_object_ids(bad: str) -> None:
    data = _example()
    data["equipment"][0]["id"] = bad
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_reserved_characters_rejected_in_procedure_step_ids() -> None:
    data = _example()
    data["procedures"][0]["steps"][0]["id"] = "P-CHARGE.1"
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_reserved_characters_rejected_in_plant_id() -> None:
    data = _example()
    data["plant_id"] = "example:unit"
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


@pytest.mark.parametrize(
    "block, index, field, value",
    [
        ("equipment", 0, "type", "boiler"),
        ("valves", 0, "fail_position", "half"),
        ("lines", 0, "no_flow", "sometimes"),
        ("utilities", 0, "kind", "hydrogen"),
        ("relief_devices", 0, "kind", "valve"),
    ],
)
def test_enum_fields_reject_unknown_values(block: str, index: int, field: str, value: str) -> None:
    data = _example()
    data[block][index][field] = value
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


@pytest.mark.parametrize(
    "block, field",
    [
        ("equipment", "type"),
        ("lines", "from_id"),
        ("chemicals", "name"),
        ("procedures", "steps"),
        # safeguards.layer_type became optional on 2026-10-13 (survey decision A5)
        ("relief_devices", "protects_id"),
        ("utilities", "kind"),
    ],
)
def test_required_fields(block: str, field: str) -> None:
    data = _example()
    del data[block][0][field]
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_operating_rows_have_no_id() -> None:
    data = _example()
    data["operating"][0]["id"] = "OP-1"
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_fixture_is_the_project_md_example() -> None:
    project = Path(__file__).resolve().parents[3] / "PROJECT.md"
    text = project.read_text(encoding="utf-8")
    block = text.split("```json\n", 1)[1].split("```", 1)[0]
    assert json.loads(block) == _example()


# --- survey decisions (2026-10-13) --------------------------------------------------------


def test_no_flow_is_a_list_and_empty_means_flowing() -> None:
    plant = Plant.model_validate(_example())
    assert plant.lines[0].no_flow == []
    data = _example()
    data["lines"][0]["no_flow"] = ["normally_closed", "startup_only"]
    assert [v.value for v in Plant.model_validate(data).lines[0].no_flow] == [
        "normally_closed",
        "startup_only",
    ]


@pytest.mark.parametrize("bad", ["none", ["none"], "normally_closed", ["sometimes"]])
def test_no_flow_rejects_none_and_single_strings(bad: object) -> None:
    data = _example()
    data["lines"][0]["no_flow"] = bad
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_line_endpoint_may_be_a_location() -> None:
    # The model holds the reference; validate.py checks its kind (equipment, utility, location).
    data = _example()
    data["lines"][0]["from_id"] = "ROOF"
    assert Plant.model_validate(data).lines[0].from_id == "ROOF"


def test_planned_work_line_ids() -> None:
    data = _example()
    data["planned_work"][0]["line_ids"] = ["L-12"]
    assert Plant.model_validate(data).planned_work[0].line_ids == ["L-12"]


def test_equipment_injection_points_hold_chemical_id_only() -> None:
    data = _example()
    data["equipment"][2]["injection_points"] = [{"chemical_id": "KOH"}]
    assert Plant.model_validate(data).equipment[2].injection_points[0].chemical_id == "KOH"
    data["equipment"][2]["injection_points"] = [{"chemical_id": "KOH", "at_component_id": "P-1"}]
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_safeguard_without_layer_type() -> None:
    data = _example()
    data["safeguards"].append(
        {"id": "SG-GAS", "description": "Hydrocarbon gas detectors", "protects_id": "BLDG-1"}
    )
    safeguard = Plant.model_validate(data).safeguards[-1]
    assert safeguard.layer_type is None
    assert safeguard.description == "Hydrocarbon gas detectors"


def test_location_description_distance_and_offsite() -> None:
    data = _example()
    data["locations"].append(
        {"id": "HOUSES", "description": "residential area", "distance_m": 1000, "offsite": True}
    )
    location = Plant.model_validate(data).locations[-1]
    assert (location.distance_m, location.offsite) == (1000, True)


OBJECT_BLOCKS = [
    "locations",
    "utilities",
    "equipment",
    "instruments",
    "logic_solvers",
    "valves",
    "lines",
    "control_loops",
    "safeguards",
    "relief_devices",
    "chemicals",
    "procedures",
    "planned_work",
]


@pytest.mark.parametrize("block", OBJECT_BLOCKS)
def test_notes_on_every_plant_object(block: str) -> None:
    data = _example()
    note = {"text": "last used 14 months ago", "source": "case_d_c4_unit.md"}
    data[block][0]["notes"] = [note]
    obj = getattr(Plant.model_validate(data), block)[0]
    assert obj.notes[0].text == "last used 14 months ago"
    assert obj.notes[0].source == "case_d_c4_unit.md"


def test_notes_on_procedure_steps_and_the_plant() -> None:
    data = _example()
    note = {"text": "labelled by hand", "source": "case_g_batch_plant.md"}
    data["procedures"][0]["steps"][0]["notes"] = [note]
    data["notes"] = [note]
    plant = Plant.model_validate(data)
    assert plant.notes[0].text == "labelled by hand"
    assert plant.procedures[0].steps[0].notes[0].source == "case_g_batch_plant.md"


@pytest.mark.parametrize(
    "note",
    [
        {"text": "words"},  # no source
        {"source": "pkg.md"},  # no text
        {"text": "", "source": "pkg.md"},  # empty text
        {"text": "words", "source": ""},  # empty source
        {"text": "words", "source": "pkg.md", "comment": "x"},  # no extra fields
    ],
)
def test_note_needs_text_and_source_only(note: dict[str, str]) -> None:
    data = _example()
    data["equipment"][0]["notes"] = [note]
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_value_objects_carry_no_notes() -> None:
    data = _example()
    data["operating"][0]["notes"] = [{"text": "words", "source": "pkg.md"}]
    with pytest.raises(ValidationError):
        Plant.model_validate(data)


def test_planned_work_times_load_as_datetimes() -> None:
    plant = Plant.model_validate(_example())
    work = plant.planned_work[0]
    assert work.start is not None and work.end is not None
    assert work.end > work.start
