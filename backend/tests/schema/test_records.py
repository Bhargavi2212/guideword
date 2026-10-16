"""Record models (PROJECT.md §11 record table, spec 0.5)."""

import copy
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from guideword.schema import ids
from guideword.schema import records as r
from guideword.schema.enums import RunStatus

Q = "m:S-MX-1:more:temperature"
F = f"f:{Q}:lightning:C01:0123456789abcdef"
PLANT = "plant:example_mixing_unit:0123456789abcdef"
RUN_INPUTS: dict[str, Any] = {
    "plant_id": PLANT,
    "section_snapshot": ["S-MX-1", "S-L-12"],
    "reference_versions": {"causes.csv": "ab"},
    "routing_config": {"orchestrator": "ultra"},
    "caps": {"run_spend_cap_usd": 1.0, "orchestrator_max_steps": 60},
    "prompt_versions": {"process": "v1"},
    "mode": "full",
}
RUN = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
STEP = "step:0123456789abcdef"
TS = "2026-10-13T12:00:00Z"

SAMPLES: dict[type[BaseModel], dict[str, Any]] = {
    r.PlantRecord: {
        "id": PLANT,
        "plant_id": "example_mixing_unit",
        "plant_file": {"plant_id": "example_mixing_unit", "schema_version": "1.0"},
        "status": "sections_confirmed",
        "confirmed_section_ids": ["S-MX-1"],
    },
    r.Run: {
        "id": RUN,
        "plant_record_id": PLANT,
        "attempt": 1,
        "section_snapshot": ["S-MX-1", "S-L-12"],
        "status": "running",
        "step": "questions",
        "mode": "full",
        "spend_cap_usd": 1.0,
        "spent_usd": 0.12,
        "reference_versions": {"causes.csv": "ab"},
        "routing_config": {"orchestrator": "ultra"},
        "caps": {"run_spend_cap_usd": 1.0, "orchestrator_max_steps": 60},
        "prompt_versions": {"process": "v1"},
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
        "plant_record_id": PLANT,
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
        "run_id": RUN,
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
    r.Hypothesis: {
        "id": "h:1:0123456789abcdef",
        "run_id": RUN,
        "rank": 1,
        "mechanism": "Wrong material charged into the mixer reacts and releases gas",
        "component_ids": ["P-CHARGE-1"],
        "chemical_ids": ["KOH", "SIH"],
        "failing_component_type": "operator",
        "cause_id": "C14",
        "consequence": "Flammable gas builds up in the building and ignites",
        "reason": "The charging step adds KOH to a vessel that can hold SIH",
        "question_ids": ["pair:KOH:SIH"],
        "model_call_id": "mc:0123456789abcdef",
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
        "job": "specialist_bulk",
        "cache_hit": False,
        "outcome": "ok",
        "finish_reason": "stop",
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
        "fact_ids": ["MX-1.volume_m3", "MX-1.operating.temperature.design_max"],
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
        (r.Hypothesis, "hyp-1"),
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


def test_findings_no_longer_carry_not_credible_reasons() -> None:
    data = {**_sample(r.Finding), "not_credible_reason": "No heat source can reach this tank"}
    with pytest.raises(ValidationError):
        r.Finding.model_validate(data)


# --- review changes 2026-10-13 ------------------------------------------------------------


def test_question_can_be_not_credible_with_a_reason_and_no_finding() -> None:
    data = {
        **_sample(r.Question),
        "status": "not_credible",
        "not_credible_reason": "No heat source can reach this tank",
        "model_call_id": "mc:0123456789abcdef",
    }
    question = r.Question.model_validate(data)
    assert question.status == "not_credible"
    assert question.not_credible_reason == "No heat source can reach this tank"


def test_not_credible_question_needs_its_reason() -> None:
    with pytest.raises(ValidationError, match="reason"):
        r.Question.model_validate({**_sample(r.Question), "status": "not_credible"})


def test_ai_question_records_the_call_that_added_it() -> None:
    data = {
        **_sample(r.Question),
        "id": ids.added_by_ai_question_id("S-MX-1", "Static from the tote"),
        "kind": "added_by_ai",
        "origin": "added_by_ai",
        "model_call_id": "mc:0123456789abcdef",
    }
    assert r.Question.model_validate(data).model_call_id == "mc:0123456789abcdef"


def test_finding_tier_is_a_tier() -> None:
    assert r.Finding.model_validate(_sample(r.Finding)).tier == "lightning"
    with pytest.raises(ValidationError):
        r.Finding.model_validate({**_sample(r.Finding), "tier": "giant"})


def test_finding_needs_its_run() -> None:
    with pytest.raises(ValidationError):
        r.Finding.model_validate({k: v for k, v in _sample(r.Finding).items() if k != "run_id"})


def test_two_runs_sharing_one_cached_response_give_two_records() -> None:
    other_inputs = {**RUN_INPUTS, "mode": "sample"}
    other_run = ids.run_id(other_inputs, [], spend_cap_usd=1.0)
    paid = r.ModelCall.model_validate(_sample(r.ModelCall))
    cached = r.ModelCall.model_validate(
        {**_sample(r.ModelCall), "run_id": other_run, "cache_hit": True, "cost_usd": 0.0}
    )
    assert paid.id == cached.id  # same cache key
    assert {(paid.run_id, paid.id), (cached.run_id, cached.id)} == {
        (RUN, paid.id),
        (other_run, paid.id),
    }
    assert (paid.cache_hit, paid.cost_usd) == (False, 0.0001)
    assert (cached.cache_hit, cached.cost_usd) == (True, 0.0)


def test_cache_hit_costs_nothing() -> None:
    with pytest.raises(ValidationError, match="cache"):
        r.ModelCall.model_validate({**_sample(r.ModelCall), "cache_hit": True})


def test_model_call_needs_its_run() -> None:
    data = {k: v for k, v in _sample(r.ModelCall).items() if k != "run_id"}
    with pytest.raises(ValidationError):
        r.ModelCall.model_validate(data)


@pytest.mark.parametrize("outcome", ["ok", "invalid", "truncated", "error"])
def test_model_call_outcomes(outcome: str) -> None:
    assert (
        r.ModelCall.model_validate({**_sample(r.ModelCall), "outcome": outcome}).outcome == outcome
    )


def test_model_call_rejects_unknown_outcome() -> None:
    with pytest.raises(ValidationError):
        r.ModelCall.model_validate({**_sample(r.ModelCall), "outcome": "partial"})


def test_run_id_rebuilt_from_stored_inputs_equals_its_id() -> None:
    run = r.Run.model_validate(_sample(r.Run))
    assert ids.run_id(run.inputs(), [], spend_cap_usd=run.spend_cap_usd) == run.id


def test_later_attempt_id_rebuilt_from_stored_inputs() -> None:
    attempt_2 = ids.run_id(RUN_INPUTS, [ids.Attempt(RunStatus.CANCELLED, 1.0)], spend_cap_usd=1.0)
    run = r.Run.model_validate({**_sample(r.Run), "id": attempt_2, "attempt": 2})
    assert run.id == f"{ids.run_id(run.inputs(), [], spend_cap_usd=1.0)}:2"


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "sample"},
        {"caps": {"run_spend_cap_usd": 2.0}},
        {"prompt_versions": {"process": "v2"}},
        {"attempt": 2},
    ],
)
def test_run_id_must_match_its_stored_inputs(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="run ID"):
        r.Run.model_validate({**_sample(r.Run), **change})


def test_section_belongs_to_a_plant_record() -> None:
    data = {k: v for k, v in _sample(r.Section).items() if k != "plant_record_id"}
    with pytest.raises(ValidationError):
        r.Section.model_validate(data)


def test_refused_tool_call_keeps_its_reason() -> None:
    data = {
        **_sample(r.ToolCall),
        "tool": "finish",
        "result": None,
        "refused_reason": "3 questions are still open",
    }
    assert r.ToolCall.model_validate(data).refused_reason == "3 questions are still open"


@pytest.mark.parametrize("tool", ["check_coverage", "finish", "answer", "run_lopa"])
def test_agent_step_tool_is_a_section_5_tool_or_answer(tool: str) -> None:
    assert r.AgentStep.model_validate({**_sample(r.AgentStep), "tool": tool}).tool == tool


def test_agent_step_rejects_unknown_tool() -> None:
    with pytest.raises(ValidationError):
        r.AgentStep.model_validate({**_sample(r.AgentStep), "tool": "delete_question"})


def test_evidence_fact_ids_are_fact_ids() -> None:
    with pytest.raises(ValidationError):
        r.Evidence.model_validate({**_sample(r.Evidence), "fact_ids": ["MX-1"]})


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


# --- cap spend (R45) ---------------------------------------------------------------------------


def test_paid_call_counts_its_cost_against_the_cap() -> None:
    call = r.ModelCall.model_validate(_sample(r.ModelCall))
    assert (call.cost_usd, call.cap_cost_usd) == (0.0001, 0.0001)


def test_paid_call_cap_cost_must_equal_its_cost() -> None:
    with pytest.raises(ValidationError, match="cap_cost_usd"):
        r.ModelCall.model_validate({**_sample(r.ModelCall), "cap_cost_usd": 0.5})


def test_cache_hit_counts_its_stored_cost_against_the_cap() -> None:
    cached = r.ModelCall.model_validate(
        {**_sample(r.ModelCall), "cache_hit": True, "cost_usd": 0.0, "cap_cost_usd": 0.0001}
    )
    assert (cached.cost_usd, cached.cap_cost_usd) == (0.0, 0.0001)


def test_cap_cost_is_never_negative() -> None:
    with pytest.raises(ValidationError):
        r.ModelCall.model_validate(
            {**_sample(r.ModelCall), "cache_hit": True, "cost_usd": 0.0, "cap_cost_usd": -1.0}
        )


def test_run_cap_spent_defaults_to_zero_and_is_never_negative() -> None:
    assert r.Run.model_validate(_sample(r.Run)).cap_spent_usd == 0.0
    with pytest.raises(ValidationError):
        r.Run.model_validate({**_sample(r.Run), "cap_spent_usd": -0.01})


# --- R50: hypotheses (contract v1.2) ------------------------------------------------------------


def test_hypothesis_needs_components_and_a_type() -> None:
    sample = _sample(r.Hypothesis)
    with pytest.raises(ValidationError):
        r.Hypothesis.model_validate({**sample, "component_ids": []})
    with pytest.raises(ValidationError):
        r.Hypothesis.model_validate(
            {k: v for k, v in sample.items() if k != "failing_component_type"}
        )


def test_outside_library_hypothesis_needs_its_cause_text() -> None:
    sample = _sample(r.Hypothesis)
    with pytest.raises(ValidationError, match="cause_text"):
        r.Hypothesis.model_validate({**sample, "cause_id": "outside_library"})
    ok = r.Hypothesis.model_validate(
        {**sample, "cause_id": "outside_library", "cause_text": "valve left open"}
    )
    assert ok.cause_text == "valve left open"


def test_hypothesis_chemicals_and_links_default_empty() -> None:
    sample = {
        k: v for k, v in _sample(r.Hypothesis).items() if k not in ("chemical_ids", "question_ids")
    }
    hypothesis = r.Hypothesis.model_validate(sample)
    assert (hypothesis.chemical_ids, hypothesis.question_ids) == ([], [])


def test_hypothesis_is_immutable() -> None:
    hypothesis = r.Hypothesis.model_validate(_sample(r.Hypothesis))
    with pytest.raises(ValidationError):
        hypothesis.rank = 2  # type: ignore[misc]


def test_hypothesis_rank_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        r.Hypothesis.model_validate({**_sample(r.Hypothesis), "rank": 0})
