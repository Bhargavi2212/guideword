"""The `retry_failed` step: a finished run's failed questions, each asked alone (demo-fixes plan,
approved 2026-10-21).

`extend_run.py --retry-failed` moves a finished run here. Each step asks one failed question
alone, at hard, to its own specialist (`agent_for`), as the orchestrator's dispatch would, and
writes its answer before returning; no orchestrator call is made. A question answered now
becomes `answered` with its findings; one that fails again stays `failed`. When every failed
question of this pass has been asked, the run goes to `severity`, which rates only the new
findings, and then the post-analysis steps from `chains`. The spend counts against the
analysis cap, which the extension raised by `--retry-cap`.
"""

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.store import StepWriter
from guideword.schema.enums import QuestionStatus
from guideword.schema.plant import Plant
from guideword.schema.records import Run
from guideword.specialists.routing import agent_for
from guideword.specialists.run import apply_batch, run_batch

STEP = "retry_failed"
NEXT = "severity"
# the agent step a retry follows when the run has none yet (code-built, never a counter)
NO_STEP = "step:0000000000000000"


class RetryFailedStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        asked = {s["question_id"] for s in writer.step_summaries(STEP) if "question_id" in s}
        questions = writer.questions()
        todo = [q for q in questions if q.status == QuestionStatus.FAILED and q.id not in asked]
        if not todo:
            return StepResult(next_step=NEXT)
        question = todo[0]
        sections = {s.id: s for s in writer.sections()}
        steps = writer.steps()
        try:
            outcome = run_batch(
                self.gateway,
                plant=self.plant,
                ref=self.ref,
                config=self.config,
                sections=sections,
                questions=[question],
                agent=agent_for(question, sections),
                budget=RunBudget(run.id, writer.run.cap_spent_usd, writer.run.spend_cap_usd),
                previous_step_id=steps[-1].id if steps else NO_STEP,
                ai_remaining=0,
                existing_question_ids={q.id for q in questions},
                level="hard",
                retry_missing=False,
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        apply_batch(writer, outcome)
        return StepResult(
            summary={
                "question_id": question.id,
                # not "status": the machine's own step_finished field would overwrite it
                "outcome": outcome.status,
                "error": outcome.error,
                "findings": len(outcome.findings),
            }
        )
