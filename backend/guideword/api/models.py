"""Request and response models for the API contract (PROJECT.md §11 "API contract").

Frozen with `contract-v1`; change only through contract/... Every run-related response
carries `label`. Records come from `schema/records.py`.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guideword.schema.enums import OverrideAction, PlantStatus, RunStatus, ShortlistTier
from guideword.schema.records import (
    Chain,
    Event,
    Evidence,
    Finding,
    Hypothesis,
    LopaRecord,
    ModelCall,
    Override,
    PlantFact,
    Question,
    Recommendation,
    Run,
    RunLabel,
    Section,
    ToolCall,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _RunResponse(_Model):
    """Every run-related response carries the run's label, shown on screen."""

    label: RunLabel


# --- errors and simple results ------------------------------------------------------------


class ErrorBody(_Model):
    """401, 403, 404, 409 and 501 bodies. `phase` names the phase that will build a 501 route."""

    detail: str
    phase: int | None = None


class Accepted(_Model):
    accepted: bool


class Issue(_Model):
    """A plant validation error or warning (schema/validate.py), naming the offending ID."""

    code: str
    object_id: str | None
    message: str


# --- plants -----------------------------------------------------------------------------------


class PlantSummary(_Model):
    plant_record_id: str
    plant_id: str
    status: PlantStatus


class PlantList(_Model):
    plants: list[PlantSummary]


class PlantUploadResult(_Model):
    plant_record_id: str | None
    ok: bool
    errors: list[Issue]
    warnings: list[Issue]


class PlantDetail(_Model):
    plant_record_id: str
    plant_id: str
    status: PlantStatus
    facts: list[PlantFact]
    warnings: list[Issue]
    sections: list[Section]


class SectionSuggestion(_Model):
    """A Super suggestion on the rule-drawn cut, always with its reason."""

    kind: Literal["split", "merge", "purpose"]
    section_ids: list[str]
    purpose: str | None = None
    reason: str


class RejectedSuggestion(_Model):
    """A Super suggestion that code refused, with code's reason (contract v1.3, R23)."""

    suggestion: SectionSuggestion
    reason: str


class SectionProposal(_Model):
    plant_record_id: str
    sections: list[Section]
    suggestions: list[SectionSuggestion]
    # additive in contract v1.3 (R23): what code refused and why, shown to the engineer
    rejected: list[RejectedSuggestion] = Field(default_factory=list)


class ConfirmSectionsRequest(_Model):
    sections: list[Section]


class ConfirmSectionsResult(_Model):
    plant_record_id: str
    status: PlantStatus
    section_ids: list[str]


# --- runs -------------------------------------------------------------------------------------


class RunList(_Model):
    runs: list[Run]


class StartRunRequest(_Model):
    # the plant record ID
    plant_id: str
    spend_cap_usd: Annotated[float, Field(gt=0)]
    mode: Literal["full", "sample"]


class StartRunResult(_RunResponse):
    run_id: str
    estimated_cost_usd: float


class RunStatusResult(_RunResponse):
    run_id: str
    status: RunStatus


class RunCounts(_Model):
    questions_total: int
    questions_open: int
    questions_checked: int
    questions_failed: int
    questions_unsure: int
    findings: int
    chains: int


class RunDetail(_RunResponse):
    run: Run
    counts: RunCounts


class EventsPage(_RunResponse):
    run_id: str
    events: list[Event]
    # poll again with ?after=next_after
    next_after: int


class RunSections(_RunResponse):
    run_id: str
    sections: list[Section]


class QuestionList(_RunResponse):
    run_id: str
    questions: list[Question]


class AddQuestionRequest(_Model):
    section_id: str
    text: Annotated[str, Field(min_length=1)]


class QuestionCreated(_RunResponse):
    question: Question


class ShortlistItem(_Model):
    rank: int
    target_id: str
    # "hypothesis": an unconfirmed hypothesis, a line with no finding of its own (R50)
    target_kind: Literal["finding", "chain", "hypothesis"]
    gap: float | None
    multi_failure: bool
    unsure: bool
    finding: Finding | None = None
    chain: Chain | None = None
    lopa: LopaRecord | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    # R50 (contract v1.2): the line's tier and, on confirmed and unconfirmed lines, its hypothesis
    tier: ShortlistTier = ShortlistTier.ALSO_FOUND
    hypothesis_id: str | None = None
    hypothesis_rank: int | None = None
    hypothesis: Hypothesis | None = None
    # computed when the list is read: the findings supporting the hypothesis
    support_finding_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hypothesis_fields_agree(self) -> "ShortlistItem":
        if self.target_kind == "hypothesis" and self.hypothesis is None:
            raise ValueError("a hypothesis line carries its hypothesis")
        if self.hypothesis is not None and (
            self.hypothesis_id != self.hypothesis.id or self.hypothesis_rank != self.hypothesis.rank
        ):
            raise ValueError("hypothesis_id and hypothesis_rank must match the hypothesis")
        return self


class Shortlist(_RunResponse):
    run_id: str
    items: list[ShortlistItem]


class WorksheetRow(_Model):
    """One worksheet row; the columns are the Excel export's (PROJECT.md §5 Step 8)."""

    row_id: str
    section: str
    design_intent: str | None
    guideword: str | None
    parameter: str | None
    deviation: str
    causes: str
    consequences: str
    existing_safeguards: str
    severity: str | None
    likelihood: str | None
    risk: str | None
    lopa_gap: str | None
    recommendation: str | None
    action_owner: str | None
    origin: str
    evidence: str | None
    status: str
    record_ids: list[str]
    override_state: Literal["none", "accepted", "rejected", "edited"]


class Worksheet(_RunResponse):
    run_id: str
    rows: list[WorksheetRow]


class CoverageList(_Model):
    # a question kind, or "sections"
    list: str
    total: int
    checked: int
    unsure: int
    failed: int


class Coverage(_RunResponse):
    run_id: str
    lists: list[CoverageList]
    failed_question_ids: list[str]


class RecordDetail(_RunResponse):
    run_id: str
    record_id: str
    record_kind: str
    record: dict[str, Any]
    parent_ids: list[str]
    model_calls: list[ModelCall]
    tool_calls: list[ToolCall]


class OverrideRequest(_Model):
    target_id: str
    action: OverrideAction
    new_value: Any
    reason: Annotated[str, Field(min_length=1)]
    # display name
    by: Annotated[str, Field(min_length=1)]


class OverrideResult(_RunResponse):
    override: Override
    # mock runs echo the override without storing it
    stored: bool


class RunDump(_RunResponse):
    run: Run
    sections: list[Section]
    questions: list[Question]
    findings: list[Finding]
    # R50 (contract v1.2)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    chains: list[Chain]
    lopa_records: list[LopaRecord]
    recommendations: list[Recommendation]
    evidence: list[Evidence]
    overrides: list[Override]
    events: list[Event]


class DemoResponse(_RunResponse):
    plant: PlantDetail
    run: RunDetail
    shortlist: Shortlist


# --- budget -----------------------------------------------------------------------------------


class EnvironmentBudget(_Model):
    environment: str
    allowance_usd: float
    spent_usd: float
    remaining_usd: float


class ModelSpend(_Model):
    model: str
    spent_usd: float


class Budget(_Model):
    environments: list[EnvironmentBudget]
    by_model: list[ModelSpend]
    live_run_available: bool
    message: str | None = None


# Response model -> fixture file name in contract/fixtures/ (spec 0.8).
RESPONSE_FIXTURES: dict[type[BaseModel], str] = {
    PlantList: "plant_list.json",
    PlantUploadResult: "plant_upload_result.json",
    PlantDetail: "plant_detail.json",
    SectionProposal: "section_proposal.json",
    ConfirmSectionsResult: "confirm_sections_result.json",
    RunList: "run_list.json",
    StartRunResult: "start_run_result.json",
    RunStatusResult: "run_status_result.json",
    RunDetail: "run_detail.json",
    EventsPage: "events_page.json",
    RunSections: "run_sections.json",
    QuestionList: "question_list.json",
    QuestionCreated: "question_created.json",
    Shortlist: "shortlist.json",
    Worksheet: "worksheet.json",
    Coverage: "coverage.json",
    RecordDetail: "record_detail.json",
    OverrideResult: "override_result.json",
    RunDump: "run_dump.json",
    DemoResponse: "demo_response.json",
    Budget: "budget.json",
    Accepted: "accepted.json",
}
