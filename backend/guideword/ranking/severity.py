"""The severity and ranked steps (spec 2.6; plan R10, R24, R38).

After `finish`, each `advance` sends one batch of scenarios without a severity to Ultra (job
`severity_reason`), one finding per scenario (R48: cause, components and section), and fills
the severity of every finding in each scenario once (R10); the severity call's record lists
the findings it rated. A finding the answer leaves out, or a batch whose answer stays
invalid, is marked "not assessed" so the step never loops. A cap refusal stops the run and
leaves the rest without severity (R24). The ranked step ends the run: `finished`, or
`stopped_cap` when the analysis ended at the severity reserve with questions still open (R38).
"""

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.prompts import Prompt, load_prompt, render
from guideword.ranking.rank import cause_key
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import EventType, QuestionStatus, RunStatus, SeverityClass, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding, Question, Run

JOB = "severity_reason"
ASK = "Give the severity of every finding in the batch, in the required JSON schema."
NOT_ASSESSED = "not assessed"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(_Strict):
    finding_id: str
    severity_class: SeverityClass
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class SeverityAnswer(_Strict):
    severities: list[Severity]


def needs_severity(findings: list[Finding]) -> list[Finding]:
    """Findings with no severity and no "not assessed" mark, in ID order."""
    return sorted((f for f in findings if not _done(f)), key=lambda f: f.id)


def _done(finding: Finding) -> bool:
    return finding.severity_class is not None or finding.severity_reason is not None


def scenario_key(finding: Finding, section_of: Mapping[str, str | None]) -> str:
    """R48: one scenario per cause (library ID, or the normalised outside-library text), sorted
    failing components and section; its findings differ only in the question that found it."""
    components = sorted(finding.failing_component_ids)
    return ids.h([cause_key(finding), components, section_of.get(finding.question_id) or ""])


def scenarios(
    findings: Sequence[Finding], questions: Sequence[Question]
) -> dict[str, list[Finding]]:
    """The findings grouped by scenario, each group in ID order."""
    section_of = {q.id: q.section_id for q in questions}
    groups: dict[str, list[Finding]] = {}
    for finding in sorted(findings, key=lambda f: f.id):
        groups.setdefault(scenario_key(finding, section_of), []).append(finding)
    return groups


def unrated_scenarios(
    findings: Sequence[Finding], questions: Sequence[Question]
) -> list[list[Finding]]:
    """Scenarios none of whose findings is rated or marked, ordered by their first finding."""
    groups = scenarios(findings, questions).values()
    return sorted(
        (members for members in groups if not any(_done(f) for f in members)),
        key=lambda members: members[0].id,
    )


class SeverityStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt("severity", config)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        findings = writer.findings()
        questions = writer.questions()
        for members in scenarios(findings, questions).values():
            _copy_within(writer, members)
        todo = unrated_scenarios(findings, questions)
        if not todo:
            return StepResult(next_step="ranked")
        batch = todo[: self.config.caps.run.severity_batch_size]
        # one finding per scenario is rated; its rating is copied to the whole scenario (R48)
        sent = [members[0] for members in batch]
        wanted = {f.id for f in sent}
        filled_ids = sorted(f.id for members in batch for f in members)

        def validator(value: Any) -> None:
            if not isinstance(value, SeverityAnswer):
                raise ValueError("not a severity answer")
            counts = Counter(s.finding_id for s in value.severities)
            for finding_id, n in counts.items():
                if finding_id not in wanted:
                    raise ValueError(f"{finding_id} is not in this batch")
                if n > 1:
                    raise ValueError(f"{finding_id} is rated more than once")

        by_id = {q.id: q for q in questions}
        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=severity_messages(self.prompt, sent, by_id, self.ref, self.plant),
                schema=SeverityAnswer,
                validator=validator,
                run=RunBudget(run.id, writer.run.cap_spent_usd, run.spend_cap_usd),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": filled_ids}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_spent(result.cost_usd, cap_usd=result.cap_cost_usd)
        rated: dict[str, Severity] = {}
        if result.outcome == "ok" and isinstance(result.value, SeverityAnswer):
            rated = {s.finding_id: s for s in result.value.severities}
        for members in batch:
            given = rated.get(members[0].id)
            update: dict[str, Any]
            if given is not None:
                update = {"severity_class": given.severity_class, "severity_reason": given.reason}
            else:
                why = (
                    result.error or result.outcome
                    if not rated
                    else "left out of the severity answer"
                )
                update = {"severity_reason": f"{NOT_ASSESSED}: {why}"[:300]}
            for finding in members:
                writer.fill_severity(finding.model_copy(update=update))
        return StepResult()


def _copy_within(writer: StepWriter, members: list[Finding]) -> None:
    """A finding added to a scenario already rated takes that rating, with no call (R48)."""
    source = next((f for f in members if f.severity_class is not None), None)
    if source is None:
        source = next((f for f in members if _done(f)), None)
    if source is None:
        return
    for finding in members:
        if not _done(finding):
            reason = f"same scenario as {source.id}: {source.severity_reason}"[:300]
            writer.fill_severity(
                finding.model_copy(
                    update={"severity_class": source.severity_class, "severity_reason": reason}
                )
            )


def severity_messages(
    prompt: Prompt,
    batch: list[Finding],
    questions: dict[str, Question],
    ref: ReferenceSet,
    plant: Plant,
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}
    findings = [
        {
            "finding_id": f.id,
            "question": questions[f.question_id].text
            if f.question_id in questions
            else f.question_id,
            "cause": f.cause_text
            if f.cause_id == OUTSIDE_LIBRARY
            else causes.get(f.cause_id, f.cause_id),
            "failing_component_ids": f.failing_component_ids,
            "consequence": f.consequence,
            "safeguard_ids": f.safeguard_ids,
            "adequacy": f.adequacy.value,
        }
        for f in batch
    ]
    classes = [
        {"severity_class": c.severity_class.value, "name": c.name, "definition": c.definition}
        for c in sorted(ref.severity_classes, key=lambda c: c.severity_class)
    ]
    context = {
        "locations": [
            loc.model_dump(mode="json", exclude_none=True)
            for loc in sorted(plant.locations, key=lambda x: x.id)
        ],
        "chemicals": [
            {
                k: v
                for k, v in {
                    "id": c.id,
                    "name": c.name,
                    "physical_form": c.physical_form,
                    "flash_point_c": c.flash_point_c,
                }.items()
                if v is not None
            }
            for c in sorted(plant.chemicals, key=lambda c: c.id)
        ],
    }
    system = render(
        prompt.body,
        {
            "severity_classes": json.dumps(classes, indent=1),
            "findings": json.dumps(findings, indent=1, ensure_ascii=False),
            "context": json.dumps(context, indent=1, ensure_ascii=False, default=str),
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]


@dataclass(frozen=True)
class SeverityReserve:
    """What the severity step will need, in place of a fixed reserve (case D dev run): one
    call per batch of the scenarios still to rate (R48: `unrated` counts scenarios). Each call
    is estimated with the agreed rule for its input and `severity_output_tokens_estimate`
    output tokens (its expected output), except one at the `max_tokens` ceiling: the gateway
    checks every call at its ceiling, so the last call must fit as the guard estimates it."""

    usd: float
    unrated: int
    calls: int
    per_call_usd: float
    ceiling_call_usd: float = 0.0


def severity_reserve(
    findings: list[Finding],
    questions: list[Question],
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> SeverityReserve:
    todo = [members[0] for members in unrated_scenarios(findings, questions)]
    if not todo:
        return SeverityReserve(0.0, 0, 0, 0.0)
    size = config.caps.run.severity_batch_size
    calls = math.ceil(len(todo) / size)
    prompt = load_prompt("severity", config)
    messages = severity_messages(prompt, todo[:size], {q.id: q for q in questions}, ref, plant)
    prices = config.models.tiers[Tier(config.routing.jobs[JOB])]
    run_caps = config.caps.run
    per_call = estimate_cost(prices, messages, None, run_caps.severity_output_tokens_estimate)
    ceiling = estimate_cost(prices, messages, None, run_caps.max_tokens[JOB])
    usd = (calls - 1) * per_call.cost_usd + ceiling.cost_usd
    return SeverityReserve(usd, len(todo), calls, per_call.cost_usd, ceiling.cost_usd)


class RankedStepper:
    """The last step: the ranking is computed on demand (R11), so this only ends the run."""

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        open_count = sum(1 for q in writer.questions() if q.status == QuestionStatus.OPEN)
        if open_count:
            # R38: the analysis ended at the severity reserve with questions still open
            writer.emit(EventType.CAP_HIT, {"reason": "questions left open", "open": open_count})
            return StepResult(status=RunStatus.STOPPED_CAP)
        return StepResult(status=RunStatus.FINISHED)
