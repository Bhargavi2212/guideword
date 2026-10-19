"""LOPA hand-worked example 1 (spec 3.2 acceptance; plan PR 4, Q21).

Cowork worked `fixtures/example_1.json` from the reference tables and the §9 example plant
before the engine existed. Every checked value in it is matched here, with a relative
tolerance of 1e-9; the fixture is read, never edited.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config
from guideword.lopa.candidates import candidates, line_scenario
from guideword.lopa.credit import LayerArgument
from guideword.lopa.engine import CODE_ONLY_FLAG, MODIFIER_REASON, lopa_record
from guideword.ranking.likelihood import band_for, likelihood
from guideword.reference import ReferenceSet
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
from guideword.schema.records import Finding, LopaRecord, Section

REPO = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "example_1.json"
RUN = "run:test"
TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def plant(example: dict[str, Any]) -> Plant:
    return Plant.model_validate_json((REPO / example["plant_file"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lead(example: dict[str, Any]) -> Finding:
    lead = example["scenario"]["lead_finding"]
    return Finding(
        id=ids.finding_id(
            lead["question_id"],
            Tier.ULTRA.value,
            lead["failing_component_ids"],
            cause_id=lead["cause_id"],
        ),
        run_id=RUN,
        question_id=lead["question_id"],
        tier=Tier.ULTRA,
        cause_id=lead["cause_id"],
        failing_component_type=FailingComponentType(lead["failing_component_type"]),
        failing_component_ids=lead["failing_component_ids"],
        consequence=lead["consequence"],
        adequacy=Adequacy.UNKNOWN,
        severity_class=SeverityClass(lead["severity_class"]),
        severity_reason="an input in the fixture",
        confidence=Confidence.SURE,
    )


@pytest.fixture(scope="module")
def mx_section(example: dict[str, Any]) -> Section:
    lead = example["scenario"]["lead_finding"]
    return Section(
        id=lead["section_id"],
        plant_record_id="plant:example",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name=lead["section_id"],
        object_ids=lead["section_object_ids"],
        drawn_by="rule",
    )


def _variant(example: dict[str, Any], letter: str) -> dict[str, Any]:
    variant: dict[str, Any] = next(
        v for v in example["variants"] if v["name"].startswith(f"{letter}:")
    )
    return variant


def _arguments(variant: dict[str, Any]) -> dict[str, LayerArgument] | None:
    given = variant["argument_input"]
    if given is None:
        return None
    return {
        layer_id: LayerArgument(applies=a["applies"], reason=f"fixture says {a['applies']}")
        for layer_id, a in given.items()
    }


def _check_common(
    record: LopaRecord,
    example: dict[str, Any],
    plant: Plant,
    lead: Finding,
    mx_section: Section,
    ref: ReferenceSet,
    config: Config,
) -> None:
    step_1 = example["step_1_initiating_frequency"]
    step_2 = example["step_2_candidate_layers"]
    scenario = line_scenario(lead, mx_section)
    assert [layer.id for layer in candidates(scenario, plant)] == step_2["candidates"]
    for excluded in step_2["excluded"]:
        assert excluded["id"] not in step_2["candidates"]
        assert excluded["id"] not in [layer.layer_id for layer in record.layers]
    # the initiating frequency and its screening band, from the same likelihood()
    screened = likelihood(lead, plant, ref, config.caps)
    assert (
        record.initiating_event_id == step_1["initiating_event_id"] == screened.initiating_event_id
    )
    assert record.initiating_frequency_per_year == pytest.approx(
        step_1["initiating_frequency_per_year"], rel=TOLERANCE
    )
    assert screened.likelihood_class == step_1["screening_likelihood_class"]
    assert band_for(step_1["initiating_frequency_per_year"], ref) == screened.likelihood_class
    assert screened.flags == tuple(step_1["flags"])
    # severity is an input; the record's ID is built from the lead finding
    assert record.id == ids.lopa_id(lead.id)
    assert record.target_id == lead.id
    assert record.severity_class == example["scenario"]["lead_finding"]["severity_class"]
    # P3-3: no modifier applied; every kind in modifiers.csv listed, once, with the reason
    kinds = ["ignition_probability", "explosion_given_ignition", "vulnerability", "time_at_risk"]
    assert record.modifiers == []
    assert [m.kind for m in record.modifiers_not_applied] == kinds
    assert {m.reason for m in record.modifiers_not_applied} == {MODIFIER_REASON}
    assert MODIFIER_REASON == "no plant fact or rule"
    # the PFDs a credited layer would get (step 3)
    for layer_id, credit in example["step_3_credit_per_layer"].items():
        layer = next(layer for layer in record.layers if layer.layer_id == layer_id)
        if layer.credited:
            assert layer.pfd == pytest.approx(credit["pfd_if_credited"], rel=TOLERANCE)


def _check_variant(record: LopaRecord, variant: dict[str, Any]) -> None:
    assert [layer.layer_id for layer in record.layers] == [
        expected["layer_id"] for expected in variant["expected_layers"]
    ]
    for layer, expected in zip(record.layers, variant["expected_layers"], strict=True):
        assert layer.credited is expected["credited"]
        if expected["credited"]:
            assert layer.pfd == pytest.approx(expected["pfd"], rel=TOLERANCE)
        else:
            # M2: a refused layer has no PFD
            assert layer.pfd is None
        if "reason" in expected:
            assert layer.reason == expected["reason"]
        if "reason_starts_with" in expected:
            assert layer.reason.startswith(expected["reason_starts_with"])
    numbers = variant["expected"]
    assert record.complete is numbers["complete"]
    assert record.mitigated_frequency_per_year == pytest.approx(
        numbers["mitigated_frequency_per_year"], rel=TOLERANCE
    )
    assert record.tolerable_per_year == pytest.approx(numbers["tolerable_per_year"], rel=TOLERANCE)
    assert record.gap == pytest.approx(numbers["gap"], rel=TOLERANCE)
    if "recommendation_eligible" in numbers:
        eligible = record.complete and record.gap is not None and record.gap > 1
        assert eligible is numbers["recommendation_eligible"]
    if "flags_include" in numbers:
        assert numbers["flags_include"] in record.flags


def _record(
    example: dict[str, Any],
    letter: str,
    plant: Plant,
    lead: Finding,
    mx_section: Section,
    ref: ReferenceSet,
    config: Config,
) -> tuple[LopaRecord, dict[str, Any]]:
    variant = _variant(example, letter)
    record = lopa_record(
        line_scenario(lead, mx_section),
        run_id=RUN,
        plant=plant,
        ref=ref,
        caps=config.caps,
        arguments=_arguments(variant),
        model_call_id=None if variant["argument_input"] is None else "mc:example",
    )
    assert isinstance(record, LopaRecord)
    _check_common(record, example, plant, lead, mx_section, ref, config)
    return record, variant


def test_example_1_variant_a_both_layers_apply_gap_10(
    example: dict[str, Any],
    plant: Plant,
    lead: Finding,
    mx_section: Section,
    ref: ReferenceSet,
    config: Config,
) -> None:
    record, variant = _record(example, "A", plant, lead, mx_section, ref, config)
    _check_variant(record, variant)
    assert record.gap == pytest.approx(10.0, rel=TOLERANCE)
    assert record.flags == []
    assert record.model_call_id == "mc:example"
    assert all(layer.applies is True for layer in record.layers)


def test_example_1_variant_b_relief_does_not_apply_gap_1000(
    example: dict[str, Any],
    plant: Plant,
    lead: Finding,
    mx_section: Section,
    ref: ReferenceSet,
    config: Config,
) -> None:
    record, variant = _record(example, "B", plant, lead, mx_section, ref, config)
    _check_variant(record, variant)
    assert record.gap == pytest.approx(1000.0, rel=TOLERANCE)
    psv = next(layer for layer in record.layers if layer.layer_id == "PSV-1")
    assert (psv.applies, psv.argument) == (False, "fixture says False")
    assert psv.reason == "does not apply: fixture says False"


def test_example_1_variant_c_code_only_gap_10000(
    example: dict[str, Any],
    plant: Plant,
    lead: Finding,
    mx_section: Section,
    ref: ReferenceSet,
    config: Config,
) -> None:
    record, variant = _record(example, "C", plant, lead, mx_section, ref, config)
    _check_variant(record, variant)
    assert record.gap == pytest.approx(10000.0, rel=TOLERANCE)
    assert record.flags == [CODE_ONLY_FLAG]
    assert CODE_ONLY_FLAG == "code-only LOPA: layers not argued"
    assert record.model_call_id is None
    assert all(layer.applies is None and layer.argument is None for layer in record.layers)
