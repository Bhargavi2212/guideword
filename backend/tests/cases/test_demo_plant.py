"""The Williams Geismar demo plant (spec 3.7; plan PR 7).

Cowork wrote `cases/demo/williams_geismar.json`; it is read here, never edited. Validation
warnings are reported in the pull request, not fixed here, and no plant fact is added.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import EquipmentType, ValvePosition
from guideword.schema.plant import Plant
from guideword.schema.validate import validate_plant

PLANT_FILE = Path(__file__).resolve().parents[3] / "cases" / "demo" / "williams_geismar.json"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(PLANT_FILE.read_text(encoding="utf-8"))
    return loaded


def test_demo_plant_validates_with_no_errors(data: dict[str, Any], ref: ReferenceSet) -> None:
    report = validate_plant(data, ref)
    assert report.errors == [], [f"{e.code} {e.object_id}: {e.message}" for e in report.errors]
    assert report.plant is not None


def test_demo_plant_has_the_reboiler_its_heat_source_and_a_relief_device_with_a_closed_inlet_valve(
    data: dict[str, Any],
) -> None:
    plant = Plant.model_validate(data)
    equipment = {e.id: e for e in plant.equipment}
    valves = {v.id: v for v in plant.valves}
    lines = {line.id for line in plant.lines}

    # the reboiler: a heat exchanger with a heat source on a line of the plant, whose
    # isolating valves are plant valves
    reboilers = [
        e for e in plant.equipment if e.type == EquipmentType.HEAT_EXCHANGER and e.heat_sources
    ]
    assert reboilers, "no heat exchanger with a heat source"
    for reboiler in reboilers:
        for source in reboiler.heat_sources:
            assert source.via_line_id in lines
            assert source.isolating_valve_ids
            assert set(source.isolating_valve_ids) <= set(valves)

    # a relief device protecting a reboiler, with an inlet valve normally closed
    isolated = [
        device
        for device in plant.relief_devices
        if device.protects_id in {r.id for r in reboilers}
        and any(
            valve_id in valves and valves[valve_id].normal_position == ValvePosition.CLOSED
            for valve_id in device.inlet_valve_ids
        )
    ]
    assert isolated, "no relief device on a reboiler with a closed inlet valve"
    for device in isolated:
        assert equipment[device.protects_id].heat_sources
