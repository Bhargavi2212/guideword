"""Record models (PROJECT.md §11 record table, spec 0.5)."""

import copy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from guideword.schema import records as r

Q = "m:S-MX-1:more:temperature"
F = f"f:{Q}:lightning:C01:0123456789abcdef"
RUN = "run:0123456789abcdef"
STEP = "step:0123456789abcdef"
TS = "2026-10-13T12:00:00Z"

SAMPLES: dict[type[BaseModel], dict[str, Any]] = {
    r.PlantRecord: {
        "id": "plant:example_mixing_unit:0123456789abcdef",
        "plant_id": "example_mixing_unit",
        "plant_file": {"plant_id": "example_mixing_unit", "schema_version": "1.0"},
        "status": "sections_confirmed",
        "confirmed_section_ids": ["S-MX-1"],
    },
    r.Run: {
        "id": RUN,
        "plant_record_id": "plant:example_mixing_unit:0123456789abcdef",
        "attempt": 1,
        "section_snapshot": ["S-MX-1", "S-L-12"],
        "status": "running",
        "step": "questions",
        "mode": "full",
        "spend_cap_usd": 1.0,
        "spent_usd": 0.12,
        "reference_versions": {"causes.csv": "ab"},
        "routing_config": {"orchestrator": "ultra"},
        "label": {"kind": "mock", "recorded_at": None, "cost_usd": 0.0},
    },
    r.PlantFact: {
        "id": "MX-1.design_pressure_kpa",
        "plant_record_id": "plant:example_mixing_unit:0123456789abcdef",
        "value": 350,
        "source": "assumed",
    },
    r.Section: {
        "id": "S-L-12~HV-12",
        "kind": "line",
        "section_type": "pipe",
        "name": "Tote to mixer",
        "object_ids": ["L-12"],
        "flagged_no_flow": False,
        "drawn_by": "rule",
    },
    r.Question: {
        "id": Q,
        "run_id": RUN,
        "kind": "matrix",
        "origin": "matrix",
        "status": "open",
        "section_id": "S-MX-1",
        "text": "More temperature in the mixer",
        "fact_ids": ["MX-1.design_temp_c"],
    },
    r.Finding: {
        "id": F,
        "question_id": Q,
        "tier": "lightning",
        "cause_id": "C01",
        "failing_component_type": "control_loop",
        "failing_component_ids": ["TV-1"],
        "consequence": "Steam valve fails open; mixer overheats",
        "safeguard_ids": ["SG-TRIP"],
        "adequacy": "adequate",
        "severity_class": "S3",
        "severity_reason": "Hot release inside an occupied building",
        "confidence": "sure",
    },
    r.AgentStep: {
        "id": STEP,
        "run_id": RUN,
        "previous_id": RUN,
        "agent": "orchestrator",
        "tool": "check_coverage",
        "arguments": {},
        "reason": "See what is still open",
    },
    r.ModelCall: {
        "id": "mc:0123456789abcdef",
        "run_id": RUN,
        "model_id": "nvidia/Nemotron-3_5-Lightning",
        "prompt_version": "process/v1",
        "input_tokens": 1200,
        "output_tokens": 300,
        "latency_ms": 900,
        "cost_usd": 0.0001,
        "attempts": 1,
        "raw_response": "{}",
    },
    r.ToolCall: {
        "id": f"tc:{STEP}:check_coverage:0123456789abcdef",
        "run_id": RUN,
        "agent_step_id": STEP,
        "tool": "check_coverage",
        "arguments": {},
        "result": {"open": 12},
    },
    r.Chain: {
        "id": f"ch:MX-1.design_pressure_kpa+{F}",
        "run_id": RUN,
        "links": [F, "MX-1.design_pressure_kpa"],
        "description": "Heat with no relief path",
        "reason": "Both links act on MX-1",
    },
    r.LopaRecord: {
        "id": f"lopa:{F}",
        "run_id": RUN,
        "target_id": F,
        "severity_class": "S3",
        "complete": True,
        "initiating_event_id": "IE-BPCS",
        "initiating_frequency_per_year": 0.1,
        "layers": [
            {
                "layer_id": "SG-TRIP",
                "layer_type": "IPL-SIS-SIL1",
                "credited": True,
                "pfd": 0.1,
                "reason": "Independent sensor, logic and final element",
            }
        ],
        "mitigated_frequency_per_year": 0.01,
        "tolerable_per_year": 0.0001,
        "gap": 100,
    },
    r.Recommendation: {
        "id": f"rec:{F}:0123456789abcdef",
        "run_id": RUN,
        "target_id": F,
        "action": "Add an independent high-temperature trip",
        "reason": "Gap of two orders of magnitude",
    },
    r.Evidence: {
        "id": f"ev:{F}:calculation:heat_up_rate",
        "run_id": RUN,
        "target_id": F,
        "kind": "calculation",
        "verdict": "confirmed",
        "summary": "Reaches design temperature in about 20 minutes",
    },
    r.Override: {
        "id": f"ov:{F}:0123456789abcdef",
        "run_id": RUN,
        "target_id": F,
        "action": "change_severity",
        "new_value": "S4",
        "reason": "Building is occupied on all shifts",
        "by": "Bhargavi",
        "at": TS,
    },
    r.Event: {"run_id": RUN, "seq": 1, "type": "run_started", "payload": {}, "time": TS},
    r.SpendEntry: {
        "ts": TS,
        "kind": "model",
        "environment": "laptop",
        "phase": "0",
        "use": "development",
        "model": "nvidia/Nemotron-3_5-Lightning",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.0001,
        "script": "smoke_test.py",
        "purpose": "T2",
    },
}


def _sample(model: type[BaseModel]) -> dict[str, Any]:
    return copy.deepcopy(SAMPLES[model])


def test_every_record_model_has_a_sample() -> None:
    assert set(SAMPLES) == set(r.RECORD_MODELS)


@pytest.mark.parametrize("model", list(SAMPLES), ids=lambda m: m.__name__)
def test_sample_validates_and_round_trips(model: type[BaseModel]) -> None:
    first = model.model_validate(_sample(model))
    assert model.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize("model", list(SAMPLES), ids=lambda m: m.__name__)
def test_unknown_fields_are_rejected(model: type[BaseModel]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**_sample(model), "surprise": 1})


@pytest.mark.parametrize(
    "model, bad_id",
    [
        (r.PlantRecord, "example_mixing_unit"),
        (r.Run, "0123456789abcdef"),
        (r.PlantFact, "MX-1"),
        (r.Section, "MX-1"),
        (r.Question, "q:1"),
        (r.Finding, "finding-1"),
        (r.AgentStep, "step-1"),
        (r.ModelCall, "call-1"),
        (r.ToolCall, "tool-1"),
        (r.Chain, "chain-1"),
        (r.LopaRecord, "lopa-1"),
        (r.Recommendation, "rec-1"),
        (r.Evidence, "ev-1"),
        (r.Override, "ov-1"),
    ],
    ids=lambda x: getattr(x, "__name__", str(x)),
)
def test_record_ids_have_their_section_11_form(model: type[BaseModel], bad_id: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**_sample(model), "id": bad_id})


def test_finding_needs_failing_components() -> None:
    with pytest.raises(ValidationError, match="failing_component_ids"):
        r.Finding.model_validate({**_sample(r.Finding), "failing_component_ids": []})


def test_outside_library_finding_needs_cause_text() -> None:
    data = {**_sample(r.Finding), "cause_id": "outside_library"}
    with pytest.raises(ValidationError):
        r.Finding.model_validate(data)
    data["cause_text"] = "Agitator seized"
    assert r.Finding.model_validate(data).cause_text == "Agitator seized"


def test_not_credible_finding_keeps_its_reason() -> None:
    data = {**_sample(r.Finding), "not_credible_reason": "No heat source can reach this tank"}
    assert r.Finding.model_validate(data).not_credible_reason


def test_chain_needs_two_links() -> None:
    with pytest.raises(ValidationError):
        r.Chain.model_validate({**_sample(r.Chain), "links": [F]})


def test_chain_is_labelled_multi_failure() -> None:
    assert r.Chain.model_validate(_sample(r.Chain)).multi_failure is True


def test_incomplete_lopa_names_the_missing_fact() -> None:
    data = {
        **_sample(r.LopaRecord),
        "complete": False,
        "initiating_frequency_per_year": None,
        "mitigated_frequency_per_year": None,
        "gap": None,
    }
    with pytest.raises(ValidationError):
        r.LopaRecord.model_validate(data)
    data["missing_fact_ids"] = ["L-12.length_m"]
    assert r.LopaRecord.model_validate(data).missing_fact_ids == ["L-12.length_m"]


def test_section_for_planned_work_has_no_type() -> None:
    data = {**_sample(r.Section), "id": "S-W-1", "kind": "planned_work", "section_type": None}
    assert r.Section.model_validate(data).section_type is None


def test_spend_entry_requires_a_known_use() -> None:
    with pytest.raises(ValidationError):
        r.SpendEntry.model_validate({**_sample(r.SpendEntry), "use": "fun"})
    with pytest.raises(ValidationError):
        r.SpendEntry.model_validate({k: v for k, v in _sample(r.SpendEntry).items() if k != "use"})


def test_event_seq_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        r.Event.model_validate({**_sample(r.Event), "seq": 0})


def test_run_label_kind_is_live_recorded_or_mock() -> None:
    data = _sample(r.Run)
    data["label"]["kind"] = "demo"
    with pytest.raises(ValidationError):
        r.Run.model_validate(data)
