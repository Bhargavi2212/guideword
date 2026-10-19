"""LOPA hand-worked example 2: the Williams Geismar reboiler (spec 3.2 acceptance; plan PR 7).

Cowork worked `fixtures/example_2.json` from the reference tables and
`cases/demo/williams_geismar.json` before the engine existed. Every value it gives for
variants A, B, C and E is matched here, through the same engine as example 1, with a relative
tolerance of 1e-9; the fixture is read, never edited. Its open points are followed: the
closed-valve reason names the first closed valve in `inlet_valve_ids` order, and "does not
apply" is decided before the inlet-valve rule.

Variant D (an engineer's `change_credit` override, G1) is applied by PR 6's override views,
so it is not tested here; it is left for PR 6.
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
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "example_2.json"
RUN = "run:test"
TOLERANCE = 1e-9
# the variants the engine alone decides; D needs PR 6's override views
ENGINE_VARIANTS = ["A", "B", "C", "E"]
MODIFIER_KINDS = [
    "ignition_probability",
    "explosion_given_ignition",
    "vulnerability",
    "time_at_risk",
]


@pytest.fixture(scope="module")
def example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def plant(example: dict[str, Any]) -> Plant:
    return Plant.model_validate_json((REPO / example["plant_file"]).read_text(encoding="utf-8"))


def _variant(example: dict[str, Any], letter: str) -> dict[str, Any]:
    variant: dict[str, Any] = next(
        v for v in example["variants"] if v["name"].startswith(f"{letter}:")
    )
    return variant


def _scenario_given(example: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    """The lead finding's facts: the fixture's lead, with a variant's `scenario_override`."""
    lead: dict[str, Any] = dict(example["scenario"]["lead_finding"])
    lead.update(variant.get("scenario_override", {}))
    return lead


def _lead(given: dict[str, Any]) -> Finding:
    return Finding(
        id=ids.finding_id(
            given["question_id"],
            Tier.ULTRA.value,
            given["failing_component_ids"],
            cause_id=given["cause_id"],
        ),
        run_id=RUN,
        question_id=given["question_id"],
        tier=Tier.ULTRA,
        cause_id=given["cause_id"],
        failing_component_type=FailingComponentType(given["failing_component_type"]),
        failing_component_ids=given["failing_component_ids"],
        consequence=given["consequence"],
        adequacy=Adequacy.UNKNOWN,
        severity_class=SeverityClass(given["severity_class"]),
        severity_reason="an input in the fixture",
        confidence=Confidence.SURE,
    )


def _section(given: dict[str, Any]) -> Section:
    return Section(
        id=given["section_id"],
        plant_record_id="plant:williams_geismar",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.HEAT_EXCHANGER,
        name=given["section_id"],
        object_ids=given["section_object_ids"],
        drawn_by="rule",
    )


def _arguments(variant: dict[str, Any]) -> dict[str, LayerArgument] | None:
    given = variant["argument_input"]
    if given is None:
        return None
    return {
        layer_id: LayerArgument(applies=a["applies"], reason=f"fixture says {a['applies']}")
        for layer_id, a in given.items()
    }


def test_example_2_variant_d_is_the_only_one_left_for_pr_6(example: dict[str, Any]) -> None:
    letters = [v["name"].split(":", 1)[0] for v in example["variants"]]
    assert sorted(set(letters) - set(ENGINE_VARIANTS)) == ["D"]
    assert "override" in _variant(example, "D")


@pytest.mark.parametrize("letter", ENGINE_VARIANTS)
def test_example_2_matches_the_hand_worked_numbers_exactly(
    letter: str,
    example: dict[str, Any],
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    variant = _variant(example, letter)
    given = _scenario_given(example, variant)
    lead = _lead(given)
    scenario = line_scenario(lead, _section(given))

    # step 2: candidates and exclusions, chosen by code
    step_2 = example["step_2_candidate_layers"]
    expected_candidates = variant.get("candidates", step_2["candidates"])
    assert [layer.id for layer in candidates(scenario, plant)] == expected_candidates
    if "candidates" not in variant:
        for excluded in step_2["excluded"]:
            assert excluded["id"] not in expected_candidates

    record = lopa_record(
        scenario,
        run_id=RUN,
        plant=plant,
        ref=ref,
        caps=config.caps,
        arguments=_arguments(variant),
        model_call_id=None if variant["argument_input"] is None else "mc:example",
    )
    assert isinstance(record, LopaRecord)

    # step 1: the initiating frequency, from the same likelihood() as screening
    step_1 = example["step_1_initiating_frequency"]
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

    # the record's identity and severity input
    assert record.id == ids.lopa_id(lead.id)
    assert record.target_id == lead.id
    assert record.severity_class == given["severity_class"]

    # P3-3: no modifier applied; every kind listed once, with the reason
    assert record.modifiers == []
    assert [m.kind for m in record.modifiers_not_applied] == MODIFIER_KINDS
    assert {m.reason for m in record.modifiers_not_applied} == {MODIFIER_REASON}

    # step 3: each layer credited or not, with its reason; a refused layer has no PFD (M2)
    assert [layer.layer_id for layer in record.layers] == [
        expected["layer_id"] for expected in variant["expected_layers"]
    ]
    for layer, expected in zip(record.layers, variant["expected_layers"], strict=True):
        assert layer.credited is expected["credited"]
        if expected["credited"]:
            assert layer.pfd == pytest.approx(expected["pfd"], rel=TOLERANCE)
        else:
            assert layer.pfd is None
        if "reason" in expected:
            assert layer.reason == expected["reason"]
        if "reason_starts_with" in expected:
            assert layer.reason.startswith(expected["reason_starts_with"])
        if "reason_contains" in expected:
            assert expected["reason_contains"] in layer.reason
    for layer_id, credit in example["step_3_credit_per_layer"].items():
        if layer_id in [layer.layer_id for layer in record.layers]:
            layer = next(layer for layer in record.layers if layer.layer_id == layer_id)
            assert layer.credited is (credit["pfd_if_credited"] is not None)

    # the numbers, and the gap shown
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
    for flag in numbers.get("flags_include", []):
        assert flag in record.flags
    if variant["argument_input"] is None:
        assert CODE_ONLY_FLAG in record.flags
        assert record.model_call_id is None
    else:
        assert record.model_call_id == "mc:example"
