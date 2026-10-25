"""Event payloads (contract v1.9, Phase 5 plan B1).

Every event the code writes is stamped `payload_schema: "v1.9"` by the event writer, and
nowhere else. Its payload is checked against the v1.9 model of its type. Events stored before
v1.9 carry no stamp and are read with their type's legacy model. The model is chosen by the
stamp alone, never by trying one model and then another. A v1.9 model forbids unknown fields;
a payload with several shapes is a union whose member is picked by a tag computed from its
keys, so a payload that matches no tag fails instead of matching the nearest model.

Legacy models type only the fields every stored event of the type has (checked against
`guideword.db` on 2026-10-23) and allow the rest. They are the only models that allow extra
fields.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    PrivateAttr,
    Tag,
    TypeAdapter,
    create_model,
    field_serializer,
    model_validator,
)

from guideword.schema.enums import (
    Agent,
    AgentTool,
    EventType,
    EvidenceKind,
    RunStatus,
    Tier,
    Verdict,
)

PayloadSchema = Literal["v1.9"]
SCHEMA_V1_9: PayloadSchema = "v1.9"
TierSource = Literal["recorded", "inferred"]
# `cap_hit.cap`: which cap stopped the step; null for a budget or allowance stop (plan J4)
CapName = Literal["analysis", "post"]


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Legacy(BaseModel):
    model_config = ConfigDict(extra="allow")


def _tagged(choose: Callable[[Mapping[str, Any]], str], *members: tuple[type, str]) -> Any:
    """A union whose member is picked by `choose(payload)`; an unknown tag fails."""

    def tag(value: Any) -> str | None:
        if isinstance(value, Mapping):
            return choose(value)
        if isinstance(value, BaseModel):
            return choose(value.model_dump())
        return None

    tagged = tuple(Annotated[model, Tag(name)] for model, name in members)
    return Annotated[Union[tagged], Discriminator(tag)]  # noqa: UP007 - built at runtime


# --- the run and its steps ----------------------------------------------------------------------


class RunStarted(_Payload):
    attempt: int
    questions: int
    sections: int


class StepStarted(_Payload):
    step: str


class _StepFinished(_Payload):
    step: str
    status: RunStatus
    next_step: str


class StepFinishedBare(_StepFinished):
    """A step with no summary: every step that only moves on, and any step stopped by a cap."""


class ConnectorOutcome(_Payload):
    outcome: str
    error: str | None


class RejectedChain(_Payload):
    links: list[str]
    reason: str


class ChainsFinished(_StepFinished):
    step: Literal["chains"]
    connector: ConnectorOutcome
    scenarios: int
    left_out: int
    rejected: list[RejectedChain]


class ChainsFinishedNoScenarios(_StepFinished):
    """No scenario line fitted, so the connector was not called."""

    step: Literal["chains"]
    scenarios: Literal[0]
    left_out: int


class ChainSeverityFinished(_StepFinished):
    step: Literal["chain_severity"]
    sent: int
    answered: int
    missing: list[str]
    re_ask: bool
    sent_ids: list[str]
    missing_ids: list[str]
    outcome: str


class BlockList(_Payload):
    file: str
    version: str
    terms: int


class EvidenceOn(_StepFinished):
    step: Literal["evidence"]
    evidence: Literal["on"]
    lines: list[str]
    settings: dict[str, Any]
    block_list: BlockList | None
    precedent_index_version: str


class EvidenceOff(_StepFinished):
    step: Literal["evidence"]
    evidence: Literal["off"]
    reason: str


class RetryFailedFinished(_StepFinished):
    step: Literal["retry_failed"]
    question_id: str
    outcome: str
    error: str | None
    findings: int


STEP_BASE = frozenset(_StepFinished.model_fields)


def _step_tag(payload: Mapping[str, Any]) -> str:
    if not set(payload) - STEP_BASE:
        return "bare"
    step = payload.get("step")
    if step == "evidence":
        return f"evidence:{payload.get('evidence')}"
    if step == "chains" and "connector" not in payload:
        return "chains:no_scenarios"
    return str(step)


StepFinished = _tagged(
    _step_tag,
    (StepFinishedBare, "bare"),
    (ChainsFinished, "chains"),
    (ChainsFinishedNoScenarios, "chains:no_scenarios"),
    (ChainSeverityFinished, "chain_severity"),
    (EvidenceOn, "evidence:on"),
    (EvidenceOff, "evidence:off"),
    (RetryFailedFinished, "retry_failed"),
)


class RunFinished(_Payload):
    spent_usd: float


class RunFailed(_Payload):
    step: str


class _RunExtended(_Payload):
    post_spend_cap_usd: float
    settings: dict[str, Any]
    jobs: dict[str, str]
    max_tokens: dict[str, int]
    prompt_versions: dict[str, str]
    ranking: dict[str, bool]
    evidence_settings: dict[str, Any]
    resumed_after_post_cap: bool
    step: str


class RunExtendedPass(_RunExtended):
    """A new post-analysis pass, or a resume after the post cap."""


class RunExtendedRerun(_RunExtended):
    rerun_from: str
    superseded_pass_seq: int | None
    superseded_ids: list[str]


class RunExtendedEvidence(_RunExtended):
    evidence_only: Literal[True]


class RunExtendedRetry(_RunExtended):
    rerun_from: Literal["retry_failed"]
    retry_failed: list[str]
    retry_cap_usd: float
    superseded_pass_seq: int | None
    superseded_ids: list[str]


def _extended_tag(payload: Mapping[str, Any]) -> str:
    if "retry_failed" in payload:
        return "retry"
    if "rerun_from" in payload:
        return "rerun"
    if "evidence_only" in payload:
        return "evidence"
    return "pass"


RunExtended = _tagged(
    _extended_tag,
    (RunExtendedPass, "pass"),
    (RunExtendedRerun, "rerun"),
    (RunExtendedEvidence, "evidence"),
    (RunExtendedRetry, "retry"),
)


# --- the analysis -----------------------------------------------------------------------------


class AgentDecision(_Payload):
    step_id: str
    agent: Agent
    tool: AgentTool
    reason: str


class _Dispatch(_Payload):
    agent: Agent
    level: str
    question_ids: list[str]
    selected_by_code: bool
    priority: bool
    skipped: list[str]
    # the tier the dispatch's level routes to (P5-1)
    tier: Tier
    tier_source: Literal["recorded"]
    # each variant's own fields follow, in the order the orchestrator writes them


class Admission(_Payload):
    cap_spent_usd: float
    limit_usd: float
    slices_usd: list[float]


class DeferredBatch(_Payload):
    question_ids: list[str]
    slice_usd: float


class FailedBatch(_Payload):
    question_ids: list[str]
    status: Literal["failed"]
    reason: str | None


class DispatchNothingToSend(_Dispatch):
    """Every chosen question was already answered: stored results are used."""

    batches: Literal[0]


class DispatchNoRoom(_Dispatch):
    """Not even the first batch fits the spend left: the analysis ends."""

    batches: int
    admission: Admission
    deferred_at_admission: list[DeferredBatch]


class DispatchSent(_Dispatch):
    linked_answered: int
    linked_answered_count: Literal["checked_questions"]
    unlinked_sent: int
    batches: int
    dropped_ids: list[str]
    failed_batches: list[FailedBatch]
    admission: Admission
    deferred_at_admission: list[DeferredBatch]


def _dispatch_tag(payload: Mapping[str, Any]) -> str:
    if "linked_answered" in payload:
        return "sent"
    if "admission" in payload:
        return "no_room"
    return "nothing_to_send"


Dispatch = _tagged(
    _dispatch_tag,
    (DispatchNothingToSend, "nothing_to_send"),
    (DispatchNoRoom, "no_room"),
    (DispatchSent, "sent"),
)


class ModelCallEvent(_Payload):
    model_call_id: str
    job: str
    model_id: str
    cache_hit: bool
    outcome: Literal["ok", "invalid", "truncated", "error"]
    cost_usd: float
    cap_cost_usd: float
    # absent unless a tier fell back, and left out when served if so
    fell_back_from: Annotated[list[Tier] | None, Field(exclude_if=lambda v: v is None)] = None
    # the tier on the call's record (contract v1.9); null only when the record has none
    tier: Tier | None
    tier_source: Literal["recorded"] | None

    @model_validator(mode="after")
    def _source_with_tier(self) -> "ModelCallEvent":
        if (self.tier is None) != (self.tier_source is None):
            raise ValueError("tier and tier_source are set together")
        return self


class ToolCallEvent(_Payload):
    tool_call_id: str
    tool: str
    refused: bool


class FindingAdded(_Payload):
    finding_id: str
    question_id: str
    # the tier that answered the question
    tier: Tier


class CoverageLine(_Payload):
    # mirrors api.models.CoverageList (a test keeps the two equal)
    list: str
    total: int
    checked: int
    unsure: int
    failed: int


class CoverageUpdated(_Payload):
    lines: list[CoverageLine]


class _CapHit(_Payload):
    reason: str
    cap: CapName | None


class CapHitRefused(_CapHit):
    """The gateway refused a call: the run stops with this status."""

    status: RunStatus


class CapHitSteps(_CapHit):
    reason: Literal["orchestrator_max_steps"]
    limit: int


class CapHitReserve(_CapHit):
    """The analysis stops at the severity reserve (R38); severity runs next."""

    reason: Literal["severity reserve", "admission"]
    detail: str
    reserve_usd: float
    unrated: int
    severity_calls: int


class CapHitOpen(_CapHit):
    reason: Literal["questions left open"]
    open: int


def _cap_tag(payload: Mapping[str, Any]) -> str:
    if "status" in payload:
        return "refused"
    if "limit" in payload:
        return "steps"
    if "reserve_usd" in payload:
        return "reserve"
    return "open"


CapHit = _tagged(
    _cap_tag,
    (CapHitRefused, "refused"),
    (CapHitSteps, "steps"),
    (CapHitReserve, "reserve"),
    (CapHitOpen, "open"),
)


class HypothesisAdded(_Payload):
    hypothesis_id: str
    rank: int


class HypothesisDropped(_Payload):
    rank: int | None
    reason: str


# --- post-analysis records ------------------------------------------------------------------------


class ChainAdded(_Payload):
    chain_id: str
    links: int


class LopaDone(_Payload):
    lopa_id: str
    complete: bool
    kind: Literal["full", "code_only"]


class EvidenceAdded(_Payload):
    evidence_id: str
    target_id: str
    kind: EvidenceKind
    verdict: Verdict


class CalculationsReattached(_Payload):
    """Contract v1.11 (review plan Q5): a stored run's calculation cards re-attached under a
    changed rule, by code and at $0. The screen's text is built from these fields; none is
    stored as prose. A new type under the v1.9 stamp: adding a member changes no other model."""

    # the day it was done, and the commit whose rule did it
    date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{7,40}$")]
    superseded_ids: list[str]
    added_ids: list[str]

    @model_validator(mode="after")
    def _changes_something(self) -> "CalculationsReattached":
        if not self.superseded_ids and not self.added_ids:
            raise ValueError("a re-attach supersedes or adds at least one record")
        return self


V1_9: dict[EventType, Any] = {
    EventType.RUN_STARTED: RunStarted,
    EventType.STEP_STARTED: StepStarted,
    EventType.STEP_FINISHED: StepFinished,
    EventType.AGENT_DECISION: AgentDecision,
    EventType.DISPATCH: Dispatch,
    EventType.MODEL_CALL: ModelCallEvent,
    EventType.TOOL_CALL: ToolCallEvent,
    EventType.FINDING_ADDED: FindingAdded,
    EventType.CHAIN_ADDED: ChainAdded,
    EventType.LOPA_DONE: LopaDone,
    EventType.EVIDENCE_ADDED: EvidenceAdded,
    EventType.COVERAGE_UPDATED: CoverageUpdated,
    EventType.CAP_HIT: CapHit,
    EventType.RUN_FINISHED: RunFinished,
    EventType.RUN_FAILED: RunFailed,
    EventType.HYPOTHESIS_ADDED: HypothesisAdded,
    EventType.HYPOTHESIS_DROPPED: HypothesisDropped,
    EventType.RUN_EXTENDED: RunExtended,
    EventType.CALCULATIONS_REATTACHED: CalculationsReattached,
}


# --- legacy: events stored before v1.9 (no stamp) ------------------------------------------------


class LegacyRunStarted(_Legacy):
    attempt: int
    questions: int
    sections: int


class LegacyStepStarted(_Legacy):
    step: str


class LegacyStepFinished(_Legacy):
    step: str
    status: str
    next_step: str


class LegacyAgentDecision(_Legacy):
    step_id: str
    agent: str
    tool: str
    reason: str


class LegacyDispatch(_Legacy):
    agent: str
    level: str
    question_ids: list[str]
    selected_by_code: bool
    skipped: list[str]
    batches: int
    # added on read, from the run's own routing config (C3, plan H14); never stored
    tier: Tier | None = None
    tier_source: Literal["inferred"] | None = None


class LegacyModelCall(_Legacy):
    model_call_id: str
    job: str
    model_id: str
    cache_hit: bool
    outcome: str
    cost_usd: float
    cap_cost_usd: float
    # added on read, from the model ID against models.yaml (C3); never stored; null: unknown
    tier: Tier | None = None
    tier_source: Literal["inferred"] | None = None


class LegacyToolCall(_Legacy):
    tool_call_id: str
    tool: str
    refused: bool


class LegacyFindingAdded(_Legacy):
    finding_id: str
    question_id: str
    tier: str


class LegacyChainAdded(_Legacy):
    chain_id: str
    links: int


class LegacyLopaDone(_Legacy):
    lopa_id: str
    complete: bool
    kind: str


class LegacyEvidenceAdded(_Legacy):
    evidence_id: str
    target_id: str
    kind: str
    verdict: str


class LegacyCoverageUpdated(_Legacy):
    lines: list[dict[str, Any]]


class LegacyCapHit(_Legacy):
    reason: str


class LegacyRunFinished(_Legacy):
    spent_usd: float


class LegacyHypothesisAdded(_Legacy):
    hypothesis_id: str
    rank: int


class LegacyRunExtended(_Legacy):
    post_spend_cap_usd: float
    settings: dict[str, Any]
    jobs: dict[str, str]
    max_tokens: dict[str, int]
    prompt_versions: dict[str, str]
    resumed_after_post_cap: bool
    step: str


# `run_failed` and `hypothesis_dropped` were never stored before v1.9: no legacy model
LEGACY: dict[EventType, type[_Legacy]] = {
    EventType.RUN_STARTED: LegacyRunStarted,
    EventType.STEP_STARTED: LegacyStepStarted,
    EventType.STEP_FINISHED: LegacyStepFinished,
    EventType.AGENT_DECISION: LegacyAgentDecision,
    EventType.DISPATCH: LegacyDispatch,
    EventType.MODEL_CALL: LegacyModelCall,
    EventType.TOOL_CALL: LegacyToolCall,
    EventType.FINDING_ADDED: LegacyFindingAdded,
    EventType.CHAIN_ADDED: LegacyChainAdded,
    EventType.LOPA_DONE: LegacyLopaDone,
    EventType.EVIDENCE_ADDED: LegacyEvidenceAdded,
    EventType.COVERAGE_UPDATED: LegacyCoverageUpdated,
    EventType.CAP_HIT: LegacyCapHit,
    EventType.RUN_FINISHED: LegacyRunFinished,
    EventType.HYPOTHESIS_ADDED: LegacyHypothesisAdded,
    EventType.RUN_EXTENDED: LegacyRunExtended,
}

_V1_9_ADAPTERS = {t: TypeAdapter(m) for t, m in V1_9.items()}
_LEGACY_ADAPTERS = {t: TypeAdapter(m) for t, m in LEGACY.items()}


def payload_model(type: EventType, payload_schema: PayloadSchema | None) -> TypeAdapter[Any]:
    """The model for an event, chosen by its stamp alone. Raises KeyError for a type that has
    no model in that schema (an unstamped `run_failed` or `hypothesis_dropped`)."""
    if payload_schema == SCHEMA_V1_9:
        return _V1_9_ADAPTERS[type]
    return _LEGACY_ADAPTERS[type]


def validate_payload(
    type: EventType, payload: Mapping[str, Any], payload_schema: PayloadSchema | None
) -> Any:
    """Parse `payload` with the model its stamp names; raises on any mismatch."""
    try:
        adapter = payload_model(type, payload_schema)
    except KeyError as error:
        raise ValueError(f"no {payload_schema or 'legacy'} model for event type {type}") from error
    return adapter.validate_python(dict(payload))


# --- the API's events (contract v1.9): one typed event per type and stamp ------------------------


class _ApiEvent(BaseModel):
    """The fields every served event has, in the stored record's order. The payload is checked
    against its model and then served exactly as written (its own key order, nothing added),
    so a served event reads as stored."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    seq: int
    _written: dict[str, Any] | None = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def _keep_written(cls, data: Any, handler: Any) -> Any:
        event = handler(data)
        if isinstance(data, Mapping) and isinstance(data.get("payload"), Mapping):
            event._written = dict(data["payload"])
        return event

    @field_serializer("payload", check_fields=False)
    def _as_written(self, payload: Any) -> Any:
        if self._written is not None:
            return self._written
        return payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload


def _event_model(type: EventType, schema: str, payload: Any) -> type[BaseModel]:
    """An event of `type` whose payload model is chosen by its stamp (`schema`)."""
    camel = "".join(part.title() for part in type.value.split("_"))
    stamped = schema == SCHEMA_V1_9
    fields: dict[str, Any] = {
        "type": (Literal[type.value], ...),
        "payload": (payload, ...),
        "time": (datetime, ...),
        "payload_schema": (PayloadSchema, ...) if stamped else (None, None),
        "payload_invalid": (Literal[False], False),
        "payload_error": (None, None),
    }
    name = f"{camel}EventV19" if stamped else f"{camel}EventLegacy"
    return create_model(name, __base__=_ApiEvent, **fields)


class InvalidEvent(_ApiEvent):
    """An event a live run wrote although its payload failed its model (Bhargavi,
    2026-10-23): shown with its flag and the error, its payload as written."""

    type: EventType
    payload: dict[str, Any]
    time: datetime
    payload_schema: PayloadSchema
    payload_invalid: Literal[True]
    payload_error: str


def _api_event_tag(value: Any) -> str:
    get = value.get if isinstance(value, Mapping) else lambda k, d=None: getattr(value, k, d)
    if get("payload_invalid", False):
        return "invalid"
    kind = get("type")
    kind = kind.value if isinstance(kind, EventType) else str(kind)
    return f"{kind}:{'v1.9' if get('payload_schema') else 'legacy'}"


_API_MEMBERS: list[Any] = [Annotated[InvalidEvent, Tag("invalid")]]
for _type in EventType:
    _API_MEMBERS.append(
        Annotated[_event_model(_type, "v1.9", V1_9[_type]), Tag(f"{_type.value}:v1.9")]
    )
    if _type in LEGACY:
        _API_MEMBERS.append(
            Annotated[_event_model(_type, "legacy", LEGACY[_type]), Tag(f"{_type.value}:legacy")]
        )

# The events the API serves: the member is chosen by the event's type and stamp, or by its
# `payload_invalid` flag; never by trying one and then another. The type checker sees the
# members' common base; the union is built at run time.
if TYPE_CHECKING:
    type ApiEvent = _ApiEvent
else:
    ApiEvent = Annotated[Union[tuple(_API_MEMBERS)], Discriminator(_api_event_tag)]  # noqa: UP007
