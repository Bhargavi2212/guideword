"""Record models (PROJECT.md §11 record table). Frozen at G1; change only through contract/...

Every record carries the IDs of what it came from, and every ID has its §11 form (built in
`schema/ids.py`). Model output is never edited in place: engineer changes are Overrides.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Agent,
    AgentTool,
    BudgetUse,
    Confidence,
    Environment,
    EventType,
    EvidenceKind,
    FailingComponentType,
    OverrideAction,
    PlantStatus,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    RunLabelKind,
    RunStatus,
    SectionKind,
    SectionType,
    SeverityClass,
    Tier,
    Verdict,
)
from guideword.schema.events import PayloadSchema
from guideword.schema.plant import Plant

OUTSIDE_LIBRARY = "outside_library"
_PLANT_ID = re.compile(ids.PLANT_ID_PATTERN)


def _prefixed(prefix: str) -> AfterValidator:
    def check(value: str) -> str:
        if not value.startswith(prefix) or len(value) == len(prefix):
            raise ValueError(f"ID must start with {prefix!r}: {value!r}")
        return value

    return AfterValidator(check)


def _question_id(value: str) -> str:
    ids.parse_question_id(value)
    return value


def _fact_id(value: str) -> str:
    ids.parse_fact_id(value)
    return value


def _section_id(value: str) -> str:
    if value.startswith("S~eng~") and len(value) > len("S~eng~"):
        return value
    if value.startswith("S-"):
        parts = value[2:].split("~")
        if 1 <= len(parts) <= 2 and all(_PLANT_ID.fullmatch(p) for p in parts):
            return value
    raise ValueError(f"not a section ID: {value!r}")


PlantRecordId = Annotated[str, _prefixed("plant:")]
RunId = Annotated[str, _prefixed("run:")]
QuestionId = Annotated[str, AfterValidator(_question_id)]
FactId = Annotated[str, AfterValidator(_fact_id)]
SectionId = Annotated[str, AfterValidator(_section_id)]
FindingId = Annotated[str, _prefixed("f:")]
StepId = Annotated[str, _prefixed("step:")]
Probability = Annotated[float, Field(gt=0, le=1)]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunLabel(_Record):
    kind: RunLabelKind
    recorded_at: datetime | None = None
    cost_usd: float | None = None
    # contract v1.10: what the label must say about its figures, as code wrote it (e.g. a
    # recorded run's spend note); shown beside the run's spend. Left out when empty, so labels
    # without one read as before
    note: Annotated[str | None, Field(exclude_if=lambda v: v is None)] = None


class PlantRecord(_Record):
    id: PlantRecordId
    plant_id: str
    plant_file: Plant
    status: PlantStatus
    confirmed_section_ids: list[SectionId] = Field(default_factory=list)


class Run(_Record):
    id: RunId
    plant_record_id: PlantRecordId
    attempt: Annotated[int, Field(ge=1)]
    section_snapshot: list[SectionId]
    status: RunStatus
    step: str
    mode: Literal["full", "sample"]
    spend_cap_usd: Annotated[float, Field(gt=0)]
    # money actually paid, from the call records ($0 on a full cache replay)
    spent_usd: Annotated[float, Field(ge=0)] = 0.0
    # counted against the cap: paid calls plus cache hits at their stored cost (R45)
    cap_spent_usd: Annotated[float, Field(ge=0)] = 0.0
    # the post-analysis steps' own allowance (P3-2, contract v1.4); like spend_cap_usd, not
    # hashed into the run ID, so a finished run can be extended in place
    post_spend_cap_usd: Annotated[float, Field(ge=0)] = 0.0
    # contract v1.9: the budget use the run spends, fixed when it starts; not hashed. Null on a
    # run stored before v1.9 until a resume or advance names one (Q4)
    use: BudgetUse | None = None
    reference_versions: dict[str, str]
    routing_config: dict[str, str]
    caps: dict[str, Any]
    prompt_versions: dict[str, str]
    label: RunLabel

    def inputs(self) -> dict[str, object]:
        """The stored inputs the run ID is built from (spend_cap_usd is not one of them)."""
        return {
            "plant_id": self.plant_record_id,
            "section_snapshot": list(self.section_snapshot),
            "reference_versions": dict(self.reference_versions),
            "routing_config": dict(self.routing_config),
            "caps": dict(self.caps),
            "prompt_versions": dict(self.prompt_versions),
            "mode": self.mode,
        }

    @model_validator(mode="after")
    def _id_matches_inputs(self) -> "Run":
        base = ids.run_id(self.inputs(), [], spend_cap_usd=self.spend_cap_usd)
        expected = base if self.attempt == 1 else f"{base}:{self.attempt}"
        if self.id != expected:
            raise ValueError(f"run ID {self.id} does not match its stored inputs ({expected})")
        return self


class PlantFact(_Record):
    id: FactId
    plant_record_id: PlantRecordId
    value: Any
    # a source reference, or "assumed"
    source: str


class Section(_Record):
    id: SectionId
    # sections belong to the plant; a run keeps a snapshot of confirmed section IDs
    plant_record_id: PlantRecordId
    kind: SectionKind
    # None for planned-work sections, which get only work: questions
    section_type: SectionType | None
    name: str
    purpose: str | None = None
    object_ids: list[str]
    flagged_no_flow: bool = False
    drawn_by: Literal["rule", "suggestion", "engineer"]
    suggestion_reason: str | None = None


class Question(_Record):
    id: QuestionId
    run_id: RunId
    kind: QuestionKind
    origin: QuestionOrigin
    status: QuestionStatus
    section_id: SectionId | None = None
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    attempts: Annotated[int, Field(ge=0)] = 0
    # a not-credible answer is a question status with its reason, and needs no finding
    not_credible_reason: str | None = None
    # the call that marked it not credible, or that added an ai: question
    model_call_id: str | None = None

    @model_validator(mode="after")
    def _not_credible_needs_reason(self) -> "Question":
        if self.status == QuestionStatus.NOT_CREDIBLE and not self.not_credible_reason:
            raise ValueError("a not_credible question needs its not_credible_reason")
        return self


class Finding(_Record):
    id: FindingId
    run_id: RunId
    question_id: QuestionId
    tier: Tier
    # a causes.csv ID, or "outside_library" with cause_text
    cause_id: str
    cause_text: str | None = None
    failing_component_type: FailingComponentType
    failing_component_ids: Annotated[list[str], Field(min_length=1)]
    consequence: str
    safeguard_ids: list[str] = Field(default_factory=list)
    adequacy: Adequacy
    severity_class: SeverityClass | None = None
    severity_reason: str | None = None
    confidence: Confidence
    model_call_id: str | None = None

    @model_validator(mode="after")
    def _outside_library_needs_text(self) -> "Finding":
        if self.cause_id == OUTSIDE_LIBRARY and not self.cause_text:
            raise ValueError("an outside-library cause needs cause_text")
        return self


class AgentStep(_Record):
    id: StepId
    run_id: RunId
    # the previous step ID, or the run ID for the first step
    previous_id: str
    agent: Agent
    tool: AgentTool
    arguments: dict[str, Any]
    reason: str
    model_call_id: str | None = None


class ModelCall(_Record):
    """Stored per (run_id, id): a cached response reused by another run is a second record."""

    id: Annotated[str, _prefixed("mc:")]
    run_id: RunId
    model_id: str
    prompt_version: str
    # the routing job (config/routing.yaml) that made the call
    job: str
    cache_hit: bool
    outcome: Literal["ok", "invalid", "truncated", "error"]
    finish_reason: str | None = None
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    latency_ms: Annotated[float, Field(ge=0)]
    cost_usd: Annotated[float, Field(ge=0)]
    # counted against the run cap (R45): cost_usd on a paid call, the cached response's
    # stored cost on a cache hit; a record without it is a paid call's cost_usd
    cap_cost_usd: Annotated[float, Field(ge=0)] = 0.0
    # retries of the same input are attempts inside one record
    attempts: Annotated[int, Field(ge=1)] = 1
    raw_response: str
    reasoning_text: str | None = None
    # contract v1.9: the tier that served the call, set by the gateway when it builds the
    # record (after any fallback); null on calls stored before it. Never part of an ID or hash.
    tier: Tier | None = None
    record_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _paid_cap_cost_defaults_to_cost(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cap_cost_usd" not in data and not data.get("cache_hit"):
            return {**data, "cap_cost_usd": data.get("cost_usd", 0.0)}
        return data

    @model_validator(mode="after")
    def _cache_hit_costs_nothing(self) -> "ModelCall":
        if self.cache_hit and self.cost_usd != 0:
            raise ValueError("a cache hit costs nothing: cost_usd must be 0")
        if not self.cache_hit and self.cap_cost_usd != self.cost_usd:
            raise ValueError(
                "a paid call counts its cost against the cap: cap_cost_usd == cost_usd"
            )
        return self


class ToolCall(_Record):
    id: Annotated[str, _prefixed("tc:")]
    run_id: RunId
    agent_step_id: StepId
    tool: str
    arguments: dict[str, Any]
    result: Any
    # set when code refused the call (bad arguments, a cap, or finish with open questions)
    refused_reason: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)


class Hypothesis(_Record):
    """One hypothesis of the whole-plant pass (R50), as validated. Immutable: its question
    links are set when it is created; whether findings support it is computed when read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, _prefixed("h:")]
    run_id: RunId
    rank: Annotated[int, Field(ge=1)]
    mechanism: str
    component_ids: Annotated[list[str], Field(min_length=1)]
    # plant chemicals the hypothesis is about (C1); links reach pair and environment questions
    chemical_ids: list[str] = Field(default_factory=list)
    failing_component_type: FailingComponentType
    # a causes.csv ID, or "outside_library" with cause_text
    cause_id: str
    cause_text: str | None = None
    consequence: str
    reason: str
    question_ids: list[QuestionId] = Field(default_factory=list)
    model_call_id: str | None = None

    @model_validator(mode="after")
    def _outside_library_needs_text(self) -> "Hypothesis":
        if self.cause_id == OUTSIDE_LIBRARY and not self.cause_text:
            raise ValueError("an outside-library cause needs cause_text")
        return self


class Chain(_Record):
    id: Annotated[str, _prefixed("ch:")]
    run_id: RunId
    # finding IDs or plant fact IDs; any other link rejects the chain
    links: Annotated[list[str], Field(min_length=2)]
    description: str
    reason: str
    # chains are never ranked down for needing two failures
    multi_failure: Literal[True] = True
    # misused terms or more than two independent failures, flagged for the engineer
    flags: list[str] = Field(default_factory=list)
    model_call_id: str | None = None
    # from the chain severity step (contract v1.4), mirroring Finding
    severity_class: SeverityClass | None = None
    severity_reason: str | None = None


class LayerCredit(_Record):
    # a safeguard ID or a relief device ID
    layer_id: str
    layer_type: str | None = None
    credited: bool
    # set only on a credited layer
    pfd: Probability | None = None
    # code's reason for the credit decision
    reason: str
    # Ultra's argument (contract v1.4): applies to this scenario, and why; null when not argued
    applies: bool | None = None
    argument: str | None = None


class AppliedModifier(_Record):
    modifier_id: str
    value: Probability


class ModifierNotApplied(_Record):
    """A modifier kind of modifiers.csv the record did not apply, and why (P3-3)."""

    kind: str
    reason: str


class LopaRecord(_Record):
    id: Annotated[str, _prefixed("lopa:")]
    run_id: RunId
    # a finding or chain ID
    target_id: str
    severity_class: SeverityClass
    complete: bool
    # names the plant fact a non-yearly frequency needed when it is missing
    missing_fact_ids: list[str] = Field(default_factory=list)
    initiating_event_id: str | None = None
    initiating_frequency_per_year: Annotated[float, Field(gt=0)] | None = None
    frequency_assumed: bool = False
    modifiers: list[AppliedModifier] = Field(default_factory=list)
    layers: list[LayerCredit] = Field(default_factory=list)
    mitigated_frequency_per_year: Annotated[float, Field(ge=0)] | None = None
    tolerable_per_year: Annotated[float, Field(gt=0)]
    gap: Annotated[float, Field(ge=0)] | None = None
    # contract v1.4: the call that argued the layers (null on code-only LOPA), the record's
    # flags ("frequency assumed", "code-only LOPA: layers not argued", ...) and the modifier
    # kinds not applied (P3-3)
    model_call_id: str | None = None
    flags: list[str] = Field(default_factory=list)
    modifiers_not_applied: list[ModifierNotApplied] = Field(default_factory=list)

    @model_validator(mode="after")
    def _complete_or_names_missing_facts(self) -> "LopaRecord":
        numbers = (self.initiating_frequency_per_year, self.mitigated_frequency_per_year, self.gap)
        if self.complete and any(n is None for n in numbers):
            raise ValueError("a complete LOPA record has its frequencies and gap")
        if not self.complete and not self.missing_fact_ids:
            raise ValueError("an incomplete LOPA record names the missing fact IDs")
        return self


class Recommendation(_Record):
    id: Annotated[str, _prefixed("rec:")]
    run_id: RunId
    # a finding or chain ID
    target_id: str
    action: str
    reason: str
    model_call_id: str | None = None


class Evidence(_Record):
    id: Annotated[str, _prefixed("ev:")]
    run_id: RunId
    target_id: str
    kind: EvidenceKind
    verdict: Verdict
    summary: str
    tool_call_id: str | None = None
    # plant facts a calculation used
    fact_ids: list[FactId] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    # contract v1.8: the call that judged a precedent; the facts a skipped calculation lacked;
    # what the card must show the engineer, as code wrote it
    model_call_id: str | None = None
    missing_fact_ids: list[FactId] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class Override(_Record):
    id: Annotated[str, _prefixed("ov:")]
    run_id: RunId
    target_id: str
    action: OverrideAction
    new_value: Any
    reason: str
    # display name
    by: str
    at: datetime
    replaces: str | None = None


class Event(_Record):
    """Identified by (run_id, seq); events are a log, not part of the replay comparison."""

    run_id: RunId
    seq: Annotated[int, Field(ge=1)]
    type: EventType
    payload: dict[str, Any]
    time: datetime
    # contract v1.9: "v1.9" on every event the code writes, set only by the event writer;
    # null on events stored before it. It alone chooses the payload's model.
    payload_schema: PayloadSchema | None = None
    # a live run writes an event whose payload fails its model as given, flagged with the
    # error (Bhargavi, 2026-10-23); tests raise instead
    payload_invalid: bool = False
    payload_error: str | None = None


class SpendEntry(_Record):
    """One ledger line (budget/ledger.jsonl on the laptop, the spend_ledger table hosted)."""

    ts: datetime
    kind: Literal["model", "tavily", "opening_balance"]
    environment: Environment
    phase: str
    use: BudgetUse
    model: str | None = None
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None
    searches: Annotated[int, Field(ge=0)] | None = None
    cost_usd: Annotated[float, Field(ge=0)]
    script: str
    purpose: str


RECORD_MODELS: list[type[BaseModel]] = [
    PlantRecord,
    Run,
    PlantFact,
    Section,
    Question,
    Finding,
    Hypothesis,
    AgentStep,
    ModelCall,
    ToolCall,
    Chain,
    LopaRecord,
    Recommendation,
    Evidence,
    Override,
    Event,
    SpendEntry,
]
