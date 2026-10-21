"""Extending a finished run in place with the post-analysis steps (spec 3.6; P3-1b; plan PR 5,
G8, G11).

A finished run whose chains step has not run gets, in one write: its `post_spend_cap_usd`,
step `chains`, status `running`, and a `run_extended` event listing the post-analysis
settings with their source (the run's stored caps, or the current config for a key they
lack), the routing of the four jobs, their `max_tokens` and the prompt versions used. No
hashed field (`caps`, `prompt_versions`, `routing_config`, ...) and no earlier record is
touched, so the stored inputs still rebuild the run ID. The run is then driven as any other.

A run that stopped at the post cap (its last cap stop came from a post-analysis step) resumes
the same way with a higher post cap (Bhargavi, 2026-10-20): `post_spend_cap_usd` is not
hashed, so the run ID stays; it goes on from the step it stopped at, so a finished step is
not run again and a call already made is read from the cache at $0.
"""

from guideword.config import Config
from guideword.runs.machine import POST_CAP
from guideword.runs.post_budget import POST_JOBS, POST_PROMPTS, post_settings
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, RunStatus
from guideword.schema.records import Run

FIRST_POST_STEP = "chains"


class ExtendRefused(ValueError):
    """The run cannot be extended: it has not finished, it has been already, or it stopped
    at the analysis cap or at a post cap no lower than the one given."""


def already_extended(runs: RunRepository, run_id: str) -> bool:
    """A `chains` step has finished in this run (extended, or started on Phase 3 code)."""
    return any(
        e.type == EventType.STEP_FINISHED and e.payload.get("step") == FIRST_POST_STEP
        for e in runs.events(run_id)
    )


def stopped_at_post_cap(runs: RunRepository, run: Run) -> bool:
    """The run is `stopped_cap` and its last cap stop was a post-analysis step's."""
    if run.status != RunStatus.STOPPED_CAP:
        return False
    hits = [e for e in runs.events(run.id) if e.type == EventType.CAP_HIT]
    return bool(hits) and hits[-1].payload.get("cap") == POST_CAP


def extend(runs: RunRepository, run_id: str, post_cap_usd: float, config: Config) -> Run:
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    resume = stopped_at_post_cap(runs, run)
    if resume:
        if post_cap_usd <= run.post_spend_cap_usd:
            raise ExtendRefused(
                f"run {run_id} stopped at its post cap ${run.post_spend_cap_usd:.2f}; "
                "give a higher --post-cap to resume it"
            )
    elif run.status == RunStatus.STOPPED_CAP:
        raise ExtendRefused(
            f"run {run_id} stopped at its analysis cap; resume it with a higher spend cap"
        )
    elif run.status != RunStatus.FINISHED:
        raise ExtendRefused(f"run {run_id} is {run.status}, not finished")
    elif already_extended(runs, run_id):
        raise ExtendRefused(f"run {run_id} already has its chains step done")
    with runs.step(run_id) as writer:
        writer.set_post_spend_cap(post_cap_usd)
        if not resume:
            writer.set_step(FIRST_POST_STEP)
        writer.set_status(RunStatus.RUNNING)
        writer.emit(
            EventType.RUN_EXTENDED,
            {
                "post_spend_cap_usd": post_cap_usd,
                "resumed_after_post_cap": resume,
                "step": writer.run.step,
                "settings": post_settings(run, config),
                "jobs": {job: str(config.routing.jobs[job]) for job in sorted(POST_JOBS)},
                "max_tokens": {job: config.caps.run.max_tokens[job] for job in sorted(POST_JOBS)},
                "prompt_versions": {
                    name: config.routing.prompts[name] for name in sorted(POST_PROMPTS)
                },
            },
        )
    extended = runs.get(run_id)
    if extended is None:
        raise LookupError(f"run {run_id} disappeared while extending")
    return extended
