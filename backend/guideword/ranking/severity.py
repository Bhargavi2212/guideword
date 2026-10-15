"""The severity and ranked steps (spec 2.6; plan R10, R24, R38).

After `finish`, each `advance` sends one batch of findings without a severity to Ultra (job
`severity_reason`) and fills each finding's severity once (R10); the severity call's record
lists the findings it rated. A finding the answer leaves out, or a batch whose answer stays
invalid, is marked "not assessed" so the step never loops. A cap refusal stops the run and
leaves the rest without severity (R24). The ranked step ends the run: `finished`, or
`stopped_cap` when the analysis ended at the severity reserve with questions still open (R38).
"""

import json
from collections import Counter
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.gateway.prompts import load_prompt, render
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.store import StepWriter
from guideword.schema.enums import EventType, QuestionStatus, RunStatus, SeverityClass
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
    return sorted(
        (f for f in findings if f.severity_class is None and f.severity_reason is None),
        key=lambda f: f.id,
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
        todo = needs_severity(writer.findings())
        if not todo:
            return StepResult(next_step="ranked")
        batch = todo[: self.config.caps.run.severity_batch_size]
        questions = {q.id: q for q in writer.questions()}
        wanted = {f.id for f in batch}

        def validator(value: Any) -> None:
            if not isinstance(value, SeverityAnswer):
                raise ValueError("not a severity answer")
            counts = Counter(s.finding_id for s in value.severities)
            for finding_id, n in counts.items():
                if finding_id not in wanted:
                    raise ValueError(f"{finding_id} is not in this batch")
                if n > 1:
                    raise ValueError(f"{finding_id} is rated more than once")

        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=self._messages(batch, questions),
                schema=SeverityAnswer,
                validator=validator,
                run=RunBudget(run.id, writer.run.spent_usd, run.spend_cap_usd),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": sorted(wanted)}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_spent(result.cost_usd)
        rated: dict[str, Severity] = {}
        if result.outcome == "ok" and isinstance(result.value, SeverityAnswer):
            rated = {s.finding_id: s for s in result.value.severities}
        for finding in batch:
            given = rated.get(finding.id)
            if given is not None:
                filled = finding.model_copy(
                    update={"severity_class": given.severity_class, "severity_reason": given.reason}
                )
            else:
                why = (
                    result.error or result.outcome
                    if not rated
                    else "left out of the severity answer"
                )
                filled = finding.model_copy(
                    update={"severity_reason": f"{NOT_ASSESSED}: {why}"[:300]}
                )
            writer.fill_severity(filled)
        return StepResult()

    def _messages(
        self, batch: list[Finding], questions: dict[str, Question]
    ) -> list[dict[str, Any]]:
        causes = {c.id: c.cause for c in self.ref.causes}
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
            for c in sorted(self.ref.severity_classes, key=lambda c: c.severity_class)
        ]
        context = {
            "locations": [
                loc.model_dump(mode="json", exclude_none=True)
                for loc in sorted(self.plant.locations, key=lambda x: x.id)
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
                for c in sorted(self.plant.chemicals, key=lambda c: c.id)
            ],
        }
        system = render(
            self.prompt.body,
            {
                "severity_classes": json.dumps(classes, indent=1),
                "findings": json.dumps(findings, indent=1, ensure_ascii=False),
                "context": json.dumps(context, indent=1, ensure_ascii=False, default=str),
            },
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]


class RankedStepper:
    """The last step: the ranking is computed on demand (R11), so this only ends the run."""

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        open_count = sum(1 for q in writer.questions() if q.status == QuestionStatus.OPEN)
        if open_count:
            # R38: the analysis ended at the severity reserve with questions still open
            writer.emit(EventType.CAP_HIT, {"reason": "questions left open", "open": open_count})
            return StepResult(status=RunStatus.STOPPED_CAP)
        return StepResult(status=RunStatus.FINISHED)
