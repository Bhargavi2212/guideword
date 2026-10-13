"""Plant validation: errors 1-9 and warnings 1-8 (spec 0.5), each naming the offending ID."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.validate import Issue, ValidationReport, validate_plant

FIXTURE = Path(__file__).parent / "fixtures" / "example_mixing_unit.json"
BASE: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _data() -> dict[str, Any]:
    return copy.deepcopy(BASE)


def _codes(issues: list[Issue]) -> list[tuple[str, str | None]]:
    return [(i.code, i.object_id) for i in issues]


def _only_error(report: ValidationReport, code: str, object_id: str) -> Issue:
    assert _codes(report.errors) == [(code, object_id)], report.errors
    issue = report.errors[0]
    assert object_id in issue.message
    return issue


def _new_warnings(
    report: ValidationReport, baseline: ValidationReport
) -> list[tuple[str, str | None]]:
    before = _codes(baseline.warnings)
    return [c for c in _codes(report.warnings) if c not in before]


# --- the example ---------------------------------------------------------------------------


def test_example_validates_with_no_errors(ref: ReferenceSet) -> None:
    report = validate_plant(_data(), ref)
    assert report.errors == []
    assert report.plant is not None
    assert report.ok


def test_example_warnings_are_the_known_gaps(ref: ReferenceSet) -> None:
    report = validate_plant(_data(), ref)
    assert sorted(_codes(report.warnings)) == sorted(
        [
            ("missing_design_limits", "TOTE-1"),  # tank with no design pressure or temperature
            ("safeguard_components_missing", "SG-VENT"),  # active layer, no component IDs
            ("line_without_contents", "L-STM"),
        ]
    )


# --- errors ----------------------------------------------------------------------------------


def test_error_1_duplicate_id(ref: ReferenceSet) -> None:
    data = _data()
    data["valves"][2]["id"] = "P-1"  # also an equipment ID
    report = validate_plant(data, ref)
    assert ("duplicate_id", "P-1") in _codes(report.errors)


def test_error_1_duplicate_step_id(ref: ReferenceSet) -> None:
    data = _data()
    data["procedures"][0]["steps"][1]["id"] = "P-CHARGE-1"
    _only_error(validate_plant(data, ref), "duplicate_id", "P-CHARGE-1")


@pytest.mark.parametrize(
    "path, value, object_id",
    [
        (("equipment", 0, "location_id"), "NOWHERE", "TOTE-1"),
        (("equipment", 0, "contents"), ["WATER"], "TOTE-1"),
        (("utilities", 0, "location_id"), "MX-1", "UT-STEAM"),  # wrong kind
        (("instruments", 0, "on_id"), "BLDG-1", "TT-1"),  # a location, not equipment or line
        (("valves", 0, "on_line_id"), "MX-1", "TV-1"),
        (("lines", 0, "from_id"), "TS-2", "L-12"),  # an instrument
        (("lines", 0, "components"), ["P-1", "HV-12", "TT-1"], "L-12"),
        (("lines", 0, "contents"), ["NOPE"], "L-12"),
        (("control_loops", 0, "sensor_id"), "TV-1", "TIC-1"),
        (("control_loops", 0, "controller_id"), "TT-1", "TIC-1"),
        (("control_loops", 0, "final_element_id"), "TT-1", "TIC-1"),
        (("safeguards", 0, "protects_id"), "TT-1", "SG-TRIP"),
        (("safeguards", 0, "component_ids"), ["TS-2", "BLDG-1"], "SG-TRIP"),
        (("relief_devices", 0, "protects_id"), "NOPE", "PSV-1"),
        (("relief_devices", 0, "inlet_valve_ids"), ["P-1"], "PSV-1"),
        (("planned_work", 0, "location_id"), "MX-1", "W-1"),
        (("planned_work", 0, "equipment_ids"), ["L-12"], "W-1"),
        (("planned_work", 0, "line_ids"), ["MX-1"], "W-1"),
    ],
)
def test_error_2_bad_reference(
    ref: ReferenceSet, path: tuple[Any, ...], value: Any, object_id: str
) -> None:
    data = _data()
    block, index, field = path
    data[block][index][field] = value
    _only_error(validate_plant(data, ref), "bad_reference", object_id)


def test_error_2_line_endpoint_may_be_equipment_utility_or_location(ref: ReferenceSet) -> None:
    data = _data()
    data["lines"][0]["from_id"] = "ROOF"
    assert validate_plant(data, ref).errors == []


def test_error_2_heat_source_references(ref: ReferenceSet) -> None:
    data = _data()
    data["equipment"][2]["heat_sources"][0]["via_line_id"] = "MX-1"
    _only_error(validate_plant(data, ref), "bad_reference", "MX-1")


def test_error_2_equipment_injection_point(ref: ReferenceSet) -> None:
    data = _data()
    data["equipment"][2]["injection_points"] = [{"chemical_id": "TBC"}]
    _only_error(validate_plant(data, ref), "bad_reference", "MX-1")


def test_error_2_line_injection_point_must_be_on_the_line(ref: ReferenceSet) -> None:
    data = _data()
    data["lines"][0]["injection_points"] = [{"chemical_id": "KOH", "at_component_id": "TV-1"}]
    _only_error(validate_plant(data, ref), "bad_reference", "L-12")


def test_error_2_operating_references(ref: ReferenceSet) -> None:
    data = _data()
    data["operating"][0]["trip_instrument_id"] = "TV-1"
    _only_error(validate_plant(data, ref), "bad_reference", "MX-1")


def test_error_2_procedure_step_references(ref: ReferenceSet) -> None:
    data = _data()
    data["procedures"][0]["steps"][1]["valve_ids"] = ["P-1"]
    _only_error(validate_plant(data, ref), "bad_reference", "P-CHARGE-2")


def test_error_2_relief_discharge_location(ref: ReferenceSet) -> None:
    data = _data()
    data["relief_devices"][0]["discharge"]["location_id"] = "MX-1"
    _only_error(validate_plant(data, ref), "bad_reference", "PSV-1")


@pytest.mark.parametrize(
    "block, index, field, value, object_id",
    [
        ("safeguards", 0, "layer_type", "IPL-MAGIC", "SG-TRIP"),
        ("chemicals", 1, "epa_groups", [10, 999], "KOH"),
        ("chemicals", 0, "cameo_groups", [58, 15], "SIH"),  # CAMEO has no group 15
    ],
)
def test_error_3_unknown_reference_table_value(
    ref: ReferenceSet, block: str, index: int, field: str, value: Any, object_id: str
) -> None:
    data = _data()
    data[block][index][field] = value
    _only_error(validate_plant(data, ref), "unknown_reference_value", object_id)


def test_error_3_safeguard_without_layer_type_is_allowed(ref: ReferenceSet) -> None:
    data = _data()
    data["safeguards"].append(
        {"id": "SG-GAS", "description": "gas detectors", "protects_id": "BLDG-1"}
    )
    assert validate_plant(data, ref).errors == []


def test_error_4_duplicate_operating_row(ref: ReferenceSet) -> None:
    data = _data()
    data["operating"].append({"target_id": "MX-1", "parameter": "temperature", "normal": 30})
    _only_error(validate_plant(data, ref), "duplicate_operating_row", "MX-1")


def test_error_5_work_ends_before_it_starts(ref: ReferenceSet) -> None:
    data = _data()
    data["planned_work"][0]["end"] = "2026-10-19T16:00:00"
    _only_error(validate_plant(data, ref), "work_ends_before_start", "W-1")


@pytest.mark.parametrize(
    "key, object_id",
    [
        ("NOPE", "NOPE"),
        ("MX-1.colour", "MX-1"),
        ("MX-1.operating.pressure.trip_high", "MX-1"),  # no pressure row
        ("MX-1.operating.temperature.alarm_low", "MX-1"),  # limit not set
        ("PSV-1.discharge.location_id", "PSV-1"),  # value objects are cited by the parent field
    ],
)
def test_error_6_bad_provenance_key(ref: ReferenceSet, key: str, object_id: str) -> None:
    data = _data()
    data["provenance"][key] = "assumed"
    _only_error(validate_plant(data, ref), "bad_provenance_key", object_id)


@pytest.mark.parametrize(
    "key",
    ["MX-1", "MX-1.design_pressure_kpa", "MX-1.operating.temperature.trip_high", "PSV-1.discharge"],
)
def test_error_6_good_provenance_keys(ref: ReferenceSet, key: str) -> None:
    data = _data()
    data["provenance"][key] = "assumed"
    assert validate_plant(data, ref).errors == []


def test_error_7_unknown_field(ref: ReferenceSet) -> None:
    data = _data()
    data["valves"][1]["colour"] = "red"
    report = validate_plant(data, ref)
    _only_error(report, "unknown_field", "XV-STM")
    assert report.plant is None


def test_error_8_bad_object_id(ref: ReferenceSet) -> None:
    data = _data()
    data["locations"][1]["id"] = "ROOF.1"
    report = validate_plant(data, ref)
    _only_error(report, "bad_id_pattern", "ROOF.1")


def test_other_schema_errors_are_reported_with_the_object(ref: ReferenceSet) -> None:
    data = _data()
    data["equipment"][0]["type"] = "boiler"
    _only_error(validate_plant(data, ref), "invalid_value", "TOTE-1")


def test_error_9_valve_not_listed_on_its_line(ref: ReferenceSet) -> None:
    data = _data()
    data["lines"][1]["components"] = ["XV-STM"]  # TV-1 says it is on L-STM
    _only_error(validate_plant(data, ref), "valve_not_on_line", "TV-1")


# --- warnings ------------------------------------------------------------------------------


@pytest.fixture
def baseline(ref: ReferenceSet) -> ValidationReport:
    return validate_plant(_data(), ref)


def test_warning_1_missing_design_limits(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    del data["equipment"][2]["design_temp_c"]
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("missing_design_limits", "MX-1")]


def test_warning_1_not_for_pumps(ref: ReferenceSet, baseline: ValidationReport) -> None:
    assert ("missing_design_limits", "P-1") not in _codes(baseline.warnings)


def test_warning_2_missing_fail_position(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    del data["valves"][0]["fail_position"]
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("missing_fail_position", "TV-1")]


def test_warning_3_chemical_without_groups(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    data["chemicals"][1]["epa_groups"] = []
    data["chemicals"][1]["cameo_groups"] = []
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("chemical_without_groups", "KOH")]


def test_warning_4_relief_without_discharge(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    del data["relief_devices"][0]["discharge"]
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("relief_without_discharge", "PSV-1")]


def test_warning_5_procedure_without_steps(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    data["procedures"][0]["steps"] = []
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("procedure_without_steps", "P-CHARGE")]


def test_warning_6_active_safeguard_without_components(
    ref: ReferenceSet, baseline: ValidationReport
) -> None:
    data = _data()
    data["safeguards"][0]["component_ids"] = []
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("safeguard_components_missing", "SG-TRIP")]


def test_warning_6_not_for_safeguards_without_layer_type(
    ref: ReferenceSet, baseline: ValidationReport
) -> None:
    data = _data()
    data["safeguards"].append({"id": "SG-PPE", "description": "goggles"})
    assert _new_warnings(validate_plant(data, ref), baseline) == []


def test_warning_7_line_without_contents(ref: ReferenceSet, baseline: ValidationReport) -> None:
    data = _data()
    data["lines"][0]["contents"] = []
    report = validate_plant(data, ref)
    assert _new_warnings(report, baseline) == [("line_without_contents", "L-12")]


def test_warning_8_operating_limits_out_of_order(
    ref: ReferenceSet, baseline: ValidationReport
) -> None:
    data = _data()
    data["operating"][0]["trip_high"] = 90  # above design_max 80: a real hazard, loads anyway
    report = validate_plant(data, ref)
    assert report.errors == []
    assert _new_warnings(report, baseline) == [("operating_limits_out_of_order", "MX-1")]


def test_optional_lopa_multipliers_give_no_warning(
    ref: ReferenceSet, baseline: ValidationReport
) -> None:
    # lines.length_m and planned_work.lifts_per_year are absent in the example.
    assert "length_m" not in BASE["lines"][0]
    assert "lifts_per_year" not in BASE["planned_work"][0]
    assert not any("length_m" in w.message or "lifts" in w.message for w in baseline.warnings)
