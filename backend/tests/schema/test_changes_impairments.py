"""The `changes` and `impairments` plant blocks (Phase 9 spec 9.2; answer 6): optional and
empty by default, so every existing plant file still validates; every value from a stated
record (`source` required); every reference checked like any other."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.plant import PLANT_MODELS, Change, Impairment, Plant
from guideword.schema.validate import Issue, validate_plant
from guideword.screen.schema import plant_for_screen

FIXTURE = Path(__file__).parent / "fixtures" / "example_mixing_unit.json"
BASE: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHANGE: dict[str, Any] = {
    "id": "CH-1",
    "description": "HV-12 added on L-12 so MX-1 can be isolated for cleaning",
    "object_ids": ["HV-12", "L-12"],
    "date": "2026-03-01T00:00:00Z",
    "hazard_review_done": False,
    "source": "pkg",
}
IMPAIRMENT: dict[str, Any] = {
    "id": "IMP-1",
    "safeguard_id": "SG-TRIP",
    "state": "bypassed",
    "since": "2026-04-01T00:00:00Z",
    "description": "trip bypassed since commissioning",
    "source": "pkg",
}


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _data(**blocks: list[dict[str, Any]]) -> dict[str, Any]:
    data = copy.deepcopy(BASE)
    data.update(blocks)
    return data


def _codes(issues: list[Issue]) -> list[tuple[str, str | None]]:
    return [(i.code, i.object_id) for i in issues]


def test_the_example_validates_with_the_blocks_absent_and_empty(ref: ReferenceSet) -> None:
    plant = Plant.model_validate(_data())
    assert plant.changes == [] and plant.impairments == []
    assert validate_plant(_data(), ref).errors == []
    assert validate_plant(_data(changes=[], impairments=[]), ref).errors == []


def test_a_change_and_an_impairment_validate_and_read_back(ref: ReferenceSet) -> None:
    report = validate_plant(_data(changes=[CHANGE], impairments=[IMPAIRMENT]), ref)
    assert report.errors == []
    assert report.plant is not None
    change = report.plant.changes[0]
    assert isinstance(change, Change)
    assert change.object_ids == ["HV-12", "L-12"] and change.hazard_review_done is False
    assert change.date is not None and change.date.year == 2026
    impairment = report.plant.impairments[0]
    assert isinstance(impairment, Impairment)
    assert impairment.safeguard_id == "SG-TRIP" and impairment.state == "bypassed"


@pytest.mark.parametrize("block, record", [("changes", CHANGE), ("impairments", IMPAIRMENT)])
def test_a_record_without_a_source_is_refused(
    ref: ReferenceSet, block: str, record: dict[str, Any]
) -> None:
    bare = {k: v for k, v in record.items() if k != "source"}
    report = validate_plant(_data(**{block: [bare]}), ref)
    assert not report.ok
    assert any("source" in issue.message for issue in report.errors)


def test_an_impairment_state_is_one_of_the_enum(ref: ReferenceSet) -> None:
    report = validate_plant(_data(impairments=[{**IMPAIRMENT, "state": "wobbly"}]), ref)
    assert not report.ok
    assert any("state" in issue.message for issue in report.errors)


def test_a_change_object_that_is_not_in_the_plant_is_a_bad_reference(ref: ReferenceSet) -> None:
    report = validate_plant(_data(changes=[{**CHANGE, "object_ids": ["HV-12", "NOPE"]}]), ref)
    assert _codes(report.errors) == [("bad_reference", "CH-1")]
    assert "NOPE" in report.errors[0].message


def test_a_change_may_name_any_kind_of_plant_object(ref: ReferenceSet) -> None:
    objects = ["MX-1", "L-12", "HV-12", "TT-1", "TIC-1", "SG-TRIP", "PSV-1", "P-CHARGE-1", "W-1"]
    report = validate_plant(_data(changes=[{**CHANGE, "object_ids": objects}]), ref)
    assert report.errors == []


def test_an_impairment_names_a_safeguard_or_a_relief_device(ref: ReferenceSet) -> None:
    report = validate_plant(_data(impairments=[{**IMPAIRMENT, "safeguard_id": "MX-1"}]), ref)
    assert _codes(report.errors) == [("bad_reference", "IMP-1")]
    assert "MX-1" in report.errors[0].message
    on_relief = validate_plant(_data(impairments=[{**IMPAIRMENT, "safeguard_id": "PSV-1"}]), ref)
    assert on_relief.errors == []


def test_a_change_or_impairment_id_is_a_plant_id_like_any_other(ref: ReferenceSet) -> None:
    report = validate_plant(_data(changes=[{**CHANGE, "id": "MX-1"}]), ref)
    assert ("duplicate_id", "MX-1") in _codes(report.errors)
    bad = validate_plant(_data(impairments=[{**IMPAIRMENT, "id": "IMP.1"}]), ref)
    assert not bad.ok


def test_the_blocks_are_plant_models() -> None:
    assert Change in PLANT_MODELS and Impairment in PLANT_MODELS


def test_the_whole_plant_pass_sees_both_blocks_without_their_sources() -> None:
    plant = Plant.model_validate(_data(changes=[CHANGE], impairments=[IMPAIRMENT]))
    seen = plant_for_screen(plant)
    assert [c["id"] for c in seen["changes"]] == ["CH-1"]
    assert [i["id"] for i in seen["impairments"]] == ["IMP-1"]
    assert "source" not in seen["changes"][0] and "source" not in seen["impairments"][0]
    assert seen["changes"][0]["hazard_review_done"] is False
    assert seen["impairments"][0]["state"] == "bypassed"
