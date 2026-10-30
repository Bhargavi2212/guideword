"""The plant record in each holistic pass's order (Phase 9 spec 9.3): the same objects, read in
a different order per pass, made by code from the pass number alone."""

import json
from pathlib import Path
from typing import Any

from guideword.schema.plant import Plant
from guideword.screen.orders import ORDERS, plant_in_order
from guideword.screen.schema import plant_for_screen
from guideword.screen.step import check_plant_sent

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"


def _data() -> dict[str, Any]:
    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    return plant_for_screen(plant)


def _ids(data: dict[str, Any], key: str) -> list[str]:
    return [o["id"] for o in data[key]]


def test_pass_one_is_the_record_as_stored() -> None:
    data = _data()
    assert plant_in_order(data, 1) == data


def test_pass_two_reverses_every_object_list_and_keeps_every_object() -> None:
    data = _data()
    second = plant_in_order(data, 2)
    for key, value in data.items():
        if isinstance(value, list) and value:
            assert second[key] == list(reversed(value)), key
        else:
            assert second[key] == value, key
    assert sorted(_ids(second, "equipment")) == sorted(_ids(data, "equipment"))


def test_pass_three_rotates_every_list_by_half() -> None:
    data = _data()
    third = plant_in_order(data, 3)
    equipment = _ids(data, "equipment")  # TOTE-1, P-1, MX-1
    half = len(equipment) // 2
    assert _ids(third, "equipment") == equipment[half:] + equipment[:half]
    assert sorted(_ids(third, "valves")) == sorted(_ids(data, "valves"))


def test_the_orders_cycle_after_three_and_are_deterministic() -> None:
    data = _data()
    assert len(ORDERS) == 3
    assert plant_in_order(data, 4) == plant_in_order(data, 1)
    assert plant_in_order(data, 5) == plant_in_order(data, 2)
    assert plant_in_order(data, 2) == plant_in_order(data, 2)


def test_a_reordered_record_never_changes_what_is_inside_an_object() -> None:
    data = _data()
    for n in (1, 2, 3):
        reordered = plant_in_order(data, n)
        by_id = {o["id"]: o for o in reordered["equipment"]}
        assert by_id == {o["id"]: o for o in data["equipment"]}
        assert reordered["schema_version"] == data["schema_version"]


def test_every_order_still_sends_the_whole_plant() -> None:
    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    data = plant_for_screen(plant)
    for n in (1, 2, 3):
        block = json.dumps(plant_in_order(data, n))
        messages = [{"role": "system", "content": f"<plant>\n{block}\n</plant>"}]
        check_plant_sent(messages, plant)


def test_a_pass_number_below_one_is_refused() -> None:
    try:
        plant_in_order(_data(), 0)
    except ValueError as error:
        assert "pass" in str(error)
    else:
        raise AssertionError("pass 0 was accepted")
