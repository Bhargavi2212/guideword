"""An impaired layer gets no LOPA credit (Phase 9 spec 9.2): the plant's `impairments` block
names a safeguard or relief device that is bypassed, defeated, overdue or removed, and that is
the first rule code applies, before "not argued", Ultra's argument and every other rule."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.lopa.candidates import line_scenario
from guideword.lopa.credit import LayerArgument, credit
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    SectionKind,
    SectionType,
    SeverityClass,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Section

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
YES = LayerArgument(applies=True, reason="it acts on this deviation")


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _plant(*impairments: dict[str, Any]) -> Plant:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["impairments"] = [{"source": "pkg", **i} for i in impairments]
    return Plant.model_validate(data)


def _finding() -> Finding:
    question = "m:S-MX-1:more:temperature"
    return Finding(
        id=ids.finding_id(question, Tier.ULTRA.value, ["TIC-1"], cause_id="C01"),
        run_id=RUN,
        question_id=question,
        tier=Tier.ULTRA,
        cause_id="C01",
        failing_component_type=FailingComponentType.CONTROL_LOOP,
        failing_component_ids=["TIC-1"],
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        severity_class=SeverityClass.S4,
        severity_reason="test",
        confidence=Confidence.SURE,
    )


def _section() -> Section:
    return Section(
        id="S-MX-1",
        plant_record_id="plant:example",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name="S-MX-1",
        object_ids=["MX-1"],
        drawn_by="rule",
    )


def test_an_unimpaired_independent_layer_is_still_credited(ref: ReferenceSet) -> None:
    plant = _plant()
    guard = next(g for g in plant.safeguards if g.id == "SG-TRIP")
    layer = credit(guard, line_scenario(_finding(), _section()), plant, ref, YES)
    assert layer.credited is True and layer.pfd is not None


def test_a_bypassed_safeguard_gets_no_credit_with_the_impairment_as_reason(
    ref: ReferenceSet,
) -> None:
    plant = _plant({"id": "IMP-1", "safeguard_id": "SG-TRIP", "state": "bypassed"})
    guard = next(g for g in plant.safeguards if g.id == "SG-TRIP")
    layer = credit(guard, line_scenario(_finding(), _section()), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — impaired: IMP-1 (bypassed)"
    assert layer.layer_type == "IPL-SIS-SIL1"
    # Ultra's argument is kept apart from code's reason
    assert layer.applies is True and layer.argument == YES.reason


def test_the_impairment_comes_before_not_argued(ref: ReferenceSet) -> None:
    plant = _plant({"id": "IMP-1", "safeguard_id": "SG-TRIP", "state": "overdue_test"})
    guard = next(g for g in plant.safeguards if g.id == "SG-TRIP")
    layer = credit(guard, line_scenario(_finding(), _section()), plant, ref, None)
    assert layer.credited is False
    assert layer.reason == "no credit — impaired: IMP-1 (overdue_test)"
    assert layer.applies is None


def test_a_removed_relief_device_gets_no_credit(ref: ReferenceSet) -> None:
    plant = _plant({"id": "IMP-2", "safeguard_id": "PSV-1", "state": "removed"})
    device = plant.relief_devices[0]
    layer = credit(device, line_scenario(_finding(), _section()), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — impaired: IMP-2 (removed)"


def test_two_impairments_on_one_layer_are_both_named(ref: ReferenceSet) -> None:
    plant = _plant(
        {"id": "IMP-1", "safeguard_id": "SG-TRIP", "state": "bypassed"},
        {"id": "IMP-3", "safeguard_id": "SG-TRIP", "state": "overdue_test"},
    )
    guard = next(g for g in plant.safeguards if g.id == "SG-TRIP")
    layer = credit(guard, line_scenario(_finding(), _section()), plant, ref, YES)
    assert layer.reason == "no credit — impaired: IMP-1 (bypassed), IMP-3 (overdue_test)"
