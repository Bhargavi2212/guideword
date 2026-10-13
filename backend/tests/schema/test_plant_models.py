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
        ("safeguards", "layer_type"),
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


def test_planned_work_times_load_as_datetimes() -> None:
    plant = Plant.model_validate(_example())
    work = plant.planned_work[0]
    assert work.start is not None and work.end is not None
    assert work.end > work.start
