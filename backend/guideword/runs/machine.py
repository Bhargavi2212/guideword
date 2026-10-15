"""The run state machine (spec 2.1; decision R24).

`advance` performs exactly one step of the run's current phase (`analysis`, `severity`,
`ranked`) through the stepper for that phase, and saves everything the step wrote before
returning. A step that raises saves nothing, so the next `advance` redoes it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from guideword.runs.store import RunRepository, StepWriter
from guideword.schema.enums import EventType, RunStatus
from guideword.schema.records import Run

ENDED = {RunStatus.FINISHED, RunStatus.FAILED, RunStatus.CANCELLED}


@dataclass(frozen=True)
class StepResult:
    """What a step decided: the run's next status, and the next phase if it moves on."""

    status: RunStatus = RunStatus.RUNNING
    next_step: str | None = None


class Stepper(Protocol):
    def __call__(self, run: Run, writer: StepWriter) -> StepResult: ...


def advance(runs: RunRepository, run_id: str, steppers: Mapping[str, Stepper]) -> RunStatus:
    """Run one step if the run is running; return its status afterwards."""
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if run.status != RunStatus.RUNNING:
        return run.status
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
            {"step": run.step, "status": writer.run.status, "next_step": writer.run.step},
        )
        if writer.run.status == RunStatus.FINISHED:
            writer.emit(EventType.RUN_FINISHED, {"spent_usd": writer.run.spent_usd})
        elif writer.run.status == RunStatus.FAILED:
            writer.emit(EventType.RUN_FAILED, {"step": run.step})
        return writer.run.status


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
