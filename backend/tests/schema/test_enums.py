"""Every enum matches the spec 0.5 table exactly (frozen at G1)."""

from enum import StrEnum

import pytest

from guideword.schema import enums as e

EQUIPMENT = {
    "tank",
    "vessel",
    "column",
    "reactor",
    "heat_exchanger",
    "pump",
    "compressor",
    "dryer",
    "mixer",
    "solids_handler",
    "other",
}

EXPECTED: list[tuple[type[StrEnum], set[str]]] = [
    (e.EquipmentType, EQUIPMENT),
    (e.SectionType, EQUIPMENT | {"pipe", "procedure"}),
    (e.SectionKind, {"equipment", "line", "no_flow_line", "procedure", "planned_work"}),
    (e.InstrumentKind, {"sensor", "switch", "analyser"}),
    (e.ControlSystem, {"bpcs", "sis", "standalone"}),
    (
        e.UtilityKind,
        {"steam", "cooling_water", "nitrogen", "instrument_air", "power", "other"},
    ),
    (e.ValveKind, {"control", "block", "check", "manual", "relief_isolation"}),
    (e.ValvePosition, {"open", "closed"}),
    (e.FailPosition, {"open", "closed", "last"}),
    # no_flow is a list; an empty list means flowing, so there is no "none" value.
    (e.NoFlow, {"normally_closed", "dead_leg", "standby", "startup_only"}),
    (e.OperatingParameter, {"pressure", "temperature", "level", "flow"}),
    (e.ReliefKind, {"prv", "rupture_disk", "prv_with_disk", "vent"}),
    (e.DischargeKind, {"atmosphere", "flare", "scrubber", "vessel", "header"}),
    (e.PhysicalForm, {"gas", "liquid", "solid", "dust"}),
    (
        e.ProcedureKind,
        {
            "start_up",
            "shutdown",
            "charging",
            "transfer",
            "cleaning",
            "maintenance",
            "emergency",
            "other",
        },
    ),
    (e.WorkType, {"hot_work", "confined_space", "line_break", "lifting", "other"}),
    (
        e.Guideword,
        {
            "no",
            "more",
            "less",
            "reverse",
            "other_than",
            "as_well_as",
            "part_of",
            "early",
            "late",
            "before",
            "after",
            "skipped",
            "wrong",
            "out_of_order",
        },
    ),
    (
        e.HazopParameter,
        {
            "flow",
            "pressure",
            "temperature",
            "level",
            "composition",
            "reaction",
            "mixing",
            "phase",
            "time",
        },
    ),
    (
        e.QuestionKind,
        {
            "matrix",
            "chemical_pair",
            "chemical_environment",
            "no_flow_line",
            "procedure_step",
            "planned_work",
            "dust",
            "relief_discharge",
            "added_by_ai",
            "engineer",
        },
    ),
    (e.QuestionOrigin, {"matrix", "cross_list", "added_by_ai", "engineer"}),
    (e.QuestionStatus, {"open", "answered", "not_credible", "failed"}),
    (
        e.FailingComponentType,
        {
            "control_loop",
            "pump",
            "compressor",
            "check_valve",
            "regulator",
            "relief_device",
            "exchanger_tube",
            "interlock",
            "operator",
            "hose",
            "pipe",
            "tank",
            "external",
            "solids_handler",
            "utility_cooling",
            "utility_power",
        },
    ),
    (e.Confidence, {"sure", "unsure"}),
    (e.Adequacy, {"adequate", "inadequate", "unknown"}),
    (e.SeverityClass, {"S1", "S2", "S3", "S4", "S5"}),
    (e.LikelihoodClass, {"L1", "L2", "L3", "L4", "L5"}),
    (e.RiskRating, {"low", "medium", "high", "very_high"}),
    (e.PlantStatus, {"uploaded", "sections_proposed", "sections_confirmed"}),
    (
        e.RunStatus,
        {
            "draft",
            "running",
            "finished",
            "stopped_cap",
            "stopped_budget",
            "failed",
            "cancelled",
        },
    ),
    (e.RunLabelKind, {"live", "recorded", "mock"}),
    (
        e.OverrideAction,
        {"accept", "reject", "edit", "change_credit", "change_severity", "answer"},
    ),
    (
        e.BudgetUse,
        {
            "development",
            "test_5",
            "benchmark",
            "video",
            "demo_recording",
            "judging",
            "buffer",
        },
    ),
    (e.EvidenceKind, {"calculation", "precedent", "simulation"}),
    (e.Verdict, {"confirmed", "contradicted", "none"}),
    (
        e.Agent,
        {
            "orchestrator",
            "process",
            "chemistry",
            "piping",
            "procedures",
            "maintenance",
            "dust",
            "connector",
        },
    ),
    (
        e.EventType,
        {
            "run_started",
            "step_started",
            "step_finished",
            "agent_decision",
            "dispatch",
            "model_call",
            "tool_call",
            "finding_added",
            "chain_added",
            "lopa_done",
            "evidence_added",
            "coverage_updated",
            "cap_hit",
            "run_finished",
            "run_failed",
            "hypothesis_added",
            "hypothesis_dropped",
        },
    ),
    (e.ShortlistTier, {"confirmed", "also_found", "unconfirmed"}),
    (e.Environment, {"laptop", "hosted"}),
    (e.Tier, {"ultra", "super", "lightning", "nano"}),
    (
        e.AgentTool,
        {
            "check_coverage",
            "dispatch_specialist",
            "web_research",
            "search_precedent",
            "reactivity_lookup",
            "physics_calc",
            "propose_chains",
            "run_lopa",
            "run_simulation",
            "finish",
            "answer",
        },
    ),
]


@pytest.mark.parametrize("enum, values", EXPECTED, ids=lambda x: getattr(x, "__name__", ""))
def test_enum_values_match_spec(enum: type[StrEnum], values: set[str]) -> None:
    assert {m.value for m in enum} == values


def test_every_enum_in_module_is_checked() -> None:
    checked = {enum for enum, _ in EXPECTED}
    defined = {
        obj
        for obj in vars(e).values()
        if isinstance(obj, type) and issubclass(obj, StrEnum) and obj is not StrEnum
    }
    assert defined == checked


def test_operating_limit_fields() -> None:
    assert e.OPERATING_LIMITS == (
        "normal",
        "alarm_low",
        "alarm_high",
        "trip_low",
        "trip_high",
        "design_min",
        "design_max",
    )
