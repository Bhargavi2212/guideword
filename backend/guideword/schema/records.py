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
    Verdict,
)
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
    spent_usd: Annotated[float, Field(ge=0)] = 0.0
    reference_versions: dict[str, str]
    routing_config: dict[str, str]
    label: RunLabel


class PlantFact(_Record):
    id: FactId
    plant_record_id: PlantRecordId
    value: Any
    # a source reference, or "assumed"
    source: str


class Section(_Record):
    id: SectionId
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


class Finding(_Record):
    id: FindingId
    question_id: QuestionId
    tier: str
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
    not_credible_reason: str | None = None
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
    tool: str
    arguments: dict[str, Any]
    reason: str
    model_call_id: str | None = None


class ModelCall(_Record):
    id: Annotated[str, _prefixed("mc:")]
    run_id: RunId | None = None
    model_id: str
    prompt_version: str
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    latency_ms: Annotated[float, Field(ge=0)]
    cost_usd: Annotated[float, Field(ge=0)]
    # retries of the same input are attempts inside one record
    attempts: Annotated[int, Field(ge=1)] = 1
    raw_response: str
    reasoning_text: str | None = None
    record_ids: list[str] = Field(default_factory=list)


class ToolCall(_Record):
    id: Annotated[str, _prefixed("tc:")]
    run_id: RunId
    agent_step_id: StepId
    tool: str
    arguments: dict[str, Any]
    result: Any
    source_urls: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)


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


class LayerCredit(_Record):
    # a safeguard ID or a relief device ID
    layer_id: str
    layer_type: str | None = None
    credited: bool
    pfd: Probability | None = None
    reason: str


class AppliedModifier(_Record):
    modifier_id: str
    value: Probability


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
    sources: list[str] = Field(default_factory=list)


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
