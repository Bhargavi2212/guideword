"""The run state machine (spec 2.1; decision R24).

`advance` performs exactly one step of the run's current phase (`analysis`, `severity`,
`ranked`) through the stepper for that phase, and saves everything the step wrote before
returning. A step that raises saves nothing, so the next `advance` redoes it. When a run
stops, both spend figures are checked against its call records (R45).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from guideword.gateway.client import BudgetRefused
from guideword.logs import get_logger
from guideword.runs.post_budget import POST_JOBS
from guideword.runs.store import RunRepository, StepWriter
from guideword.schema.enums import BudgetUse, EventType, RunStatus
from guideword.schema.records import Run, SpendEntry

ENDED = {RunStatus.FINISHED, RunStatus.FAILED, RunStatus.CANCELLED}
# float sums in a different order differ in the last places; a real mismatch is far larger
SPEND_TOLERANCE_USD = 1e-9
# the `cap` a post-analysis step's cap stop records, so extension can resume it
POST_CAP = "post"
# contract v1.9: `cap_hit.cap` for a stop at the run's (analysis) spend cap or step limit
ANALYSIS_CAP = "analysis"

log = get_logger(__name__)


@dataclass(frozen=True)
class StepResult:
    """What a step decided: the run's next status, and the next phase if it moves on.
    `summary` is added to the step's `step_finished` event (Phase 3: what a post-analysis
    step left out, such as the connector's rejected chains)."""

    status: RunStatus = RunStatus.RUNNING
    next_step: str | None = None
    summary: Mapping[str, Any] = field(default_factory=dict)


class Stepper(Protocol):
    def __call__(self, run: Run, writer: StepWriter) -> StepResult: ...


class Steppers(dict[str, Stepper]):
    """A run's steps built on one gateway; `use` is that gateway's budget use (B2, plan H5)."""

    def __init__(self, steps: Mapping[str, Stepper], *, use: BudgetUse) -> None:
        super().__init__(steps)
        self.use = use


class GatewayUseMismatch(RuntimeError):
    """The steps were built on a gateway of another use than the run's (B2, plan H5): the
    run would be billed to the wrong allowance. Nothing is stepped."""


def advance(runs: RunRepository, run_id: str, steppers: Mapping[str, Stepper]) -> RunStatus:
    """Run one step if the run is running; return its status afterwards."""
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if run.status != RunStatus.RUNNING:
        return run.status
    gateway_use = getattr(steppers, "use", None)
    if gateway_use is not None and run.use != gateway_use:
        held = "no use" if run.use is None else f"use {run.use.value}"
        raise GatewayUseMismatch(
            f"run {run_id} has {held}; its steps were built on a gateway of use {gateway_use.value}"
        )
    stepper = steppers[run.step]
    with runs.step(run_id) as writer:
        writer.emit(EventType.STEP_STARTED, {"step": run.step})
        result = stepper(writer.run, writer)
        if result.next_step is not None:
            writer.set_step(result.next_step)
        if result.status != RunStatus.RUNNING:
            writer.set_status(result.status)
        writer.emit(
            EventType.STEP_FINISHED,
            {
                **dict(result.summary),
                "step": run.step,
                "status": writer.run.status,
                "next_step": writer.run.step,
            },
        )
        if writer.run.status != RunStatus.RUNNING:
            spend_matches_records(writer)
        if writer.run.status == RunStatus.FINISHED:
            writer.emit(EventType.RUN_FINISHED, {"spent_usd": writer.run.spent_usd})
        elif writer.run.status == RunStatus.FAILED:
            writer.emit(EventType.RUN_FAILED, {"step": run.step})
        return writer.run.status


def spend_matches_records(writer: StepWriter) -> bool:
    """R45: `spent_usd` is the sum of the call records' `cost_usd` and `cap_spent_usd` the sum
    of the analysis calls' `cap_cost_usd` (post-analysis calls count against the post cap
    only). A mismatch is logged as an error; the run's status stands."""
    calls = writer.model_calls()
    # a superseded pass's calls were paid too (connector/v2 plan, Q1)
    paid = sum(c.cost_usd for c in [*calls, *writer.superseded_model_calls()])
    counted = sum(c.cap_cost_usd for c in calls if c.job not in POST_JOBS)
    run = writer.run
    ok = math.isclose(run.spent_usd, paid, abs_tol=SPEND_TOLERANCE_USD) and math.isclose(
        run.cap_spent_usd, counted, abs_tol=SPEND_TOLERANCE_USD
    )
    if not ok:
        log.error(
            "run spend does not match its call records",
            extra={
                "context": {
                    "run_id": run.id,
                    "spent_usd": run.spent_usd,
                    "records_cost_usd": paid,
                    "cap_spent_usd": run.cap_spent_usd,
                    "records_cap_cost_usd": counted,
                }
            },
        )
    return ok


def record_attempts(writer: StepWriter, refused: BudgetRefused, *, post: bool = False) -> None:
    """Write the calls a refusal carries, and their spend (bug fix, 2026-10-22): they were
    sent or served before the refusal. A post-analysis call never counts against the analysis
    cap."""
    for call in refused.attempts:
        writer.add_model_call(call)
    if post:
        writer.add_post_spent(refused.cost_usd)
    else:
        writer.add_spent(refused.cost_usd, cap_usd=refused.cap_cost_usd)
    refused.attempts, refused.cost_usd, refused.cap_cost_usd = [], 0.0, 0.0


def ledger_spent(entries: Sequence[SpendEntry], run_id: str) -> float | None:
    """What the ledger says a run paid: its model lines (purpose `<job> <run ID>`); None when
    the ledger has none for it."""
    mine = [
        e.cost_usd
        for e in entries
        if e.kind == "model" and e.purpose.split() and e.purpose.split()[-1] == run_id
    ]
    return sum(mine) if mine else None


def spend_check(run: Run, entries: Sequence[SpendEntry]) -> dict[str, Any]:
    """Beside R45 (bug fix, 2026-10-22): the run's spend against its ledger lines, where the
    ledger has them. Runs stored before the fix can fall short of their ledger: for them the
    ledger is the authority for spend. A mismatch is logged as an error."""
    ledgered = ledger_spent(entries, run.id)
    matches = ledgered is None or math.isclose(run.spent_usd, ledgered, abs_tol=SPEND_TOLERANCE_USD)
    if not matches:
        log.error(
            "run spend does not match its ledger lines",
            extra={
                "context": {"run_id": run.id, "spent_usd": run.spent_usd, "ledger_usd": ledgered}
            },
        )
    return {"spent_usd": run.spent_usd, "ledger_usd": ledgered, "matches": matches}


def stop_for_refusal(
    writer: StepWriter, refused: BudgetRefused, *, cap: str | None = None
) -> StepResult:
    """A gateway refusal ends the run with its status (`stopped_cap` or `stopped_budget`).
    A post-analysis step passes `cap=POST_CAP`: its `stopped_cap` is the post cap, and the
    event says so, so extension can resume the run with a higher post cap. The calls the
    refusal carries are recorded first."""
    record_attempts(writer, refused, post=cap == POST_CAP)
    # contract v1.9: `cap` is always present; null for a budget or allowance stop (plan J4)
    payload: dict[str, Any] = {
        "reason": str(refused),
        "status": refused.status,
        "cap": (cap or ANALYSIS_CAP) if refused.status == RunStatus.STOPPED_CAP else None,
    }
    writer.emit(EventType.CAP_HIT, payload)
    return StepResult(status=refused.status)


def cancel(runs: RunRepository, run_id: str) -> RunStatus:
    """Cancel a run that has not ended; the next `advance` then does nothing."""
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if run.status in ENDED:
        return run.status
    with runs.step(run_id) as writer:
        writer.set_status(RunStatus.CANCELLED)
    return RunStatus.CANCELLED
