"""Extending a run in place with the post-analysis steps (spec 3.6; P3-1b; plan PR 5, G8, G11;
connector/v2 plan, approved 2026-10-21).

A finished run whose chains step has not run gets, in one write: its `post_spend_cap_usd`,
step `chains`, status `running`, and a `run_extended` event (`post_pass`) listing the
post-analysis settings with their source (the run's stored caps, or the current config for a
key they lack), the routing of the four jobs, their `max_tokens` and the prompt versions used.
No hashed field (`caps`, `prompt_versions`, `routing_config`, ...) and no earlier record is
touched, so the stored inputs still rebuild the run ID. The run is then driven as any other.
A new run records the same event when its chains step first runs, since the post-step
prompts and caps are not hashed into its ID (connector/v2 plan, Q5).

A run that stopped at the post cap (its last cap stop came from a post-analysis step) resumes
the same way with a higher post cap (Bhargavi, 2026-10-20): `post_spend_cap_usd` is not
hashed, so the run ID stays; it goes on from the step it stopped at, so a finished step is
not run again and a call already made is read from the cache at $0.

`rerun_from="chains"` re-runs the four post steps of a run whose chains step has run, and
that is finished or stopped at its post cap (connector/v2 plan): in one transaction, every
chain, LOPA record, recommendation and post-job model call is copied verbatim into
`superseded_records` and cleared from the live tables, and the `run_extended` event lists
their IDs. Nothing is deleted from the record. It is refused while an override names a post
record (Q3). The re-run's post cap counts the new pass only (Q2).

`retry_failed=True` (demo-fixes plan, approved 2026-10-21) takes a finished run with failed
questions: in one transaction, its analysis cap is raised by `retry_cap_usd` (not hashed, so
the run ID stays), its post records are superseded as for a re-run, and it moves to the
`retry_failed` step, which asks each failed question alone; then severity rates only the new
findings and the post steps run from `chains`. No orchestrator call is made.
"""

from typing import Any

from guideword.config import Config
from guideword.runs.machine import POST_CAP
from guideword.runs.post_budget import POST_JOBS, POST_PROMPTS, post_settings
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, QuestionStatus, RunStatus
from guideword.schema.records import Run

FIRST_POST_STEP = "chains"
RETRY_STEP = "retry_failed"
RERUN_FROM = ("chains",)
# record ID prefixes of the post-analysis records an override can name
POST_RECORD_PREFIXES = ("ch:", "lopa:", "rec:")


class ExtendRefused(ValueError):
    """The run cannot be extended: it has not finished, it has been already, or it stopped
    at the analysis cap or at a post cap no lower than the one given; or it cannot be re-run."""


def post_pass(run: Run, config: Config, post_cap_usd: float) -> dict[str, Any]:
    """What a post-analysis pass ran with: recorded on its `run_extended` event."""
    return {
        "post_spend_cap_usd": post_cap_usd,
        "settings": post_settings(run, config),
        "jobs": {job: str(config.routing.jobs[job]) for job in sorted(POST_JOBS)},
        "max_tokens": {job: config.caps.run.max_tokens[job] for job in sorted(POST_JOBS)},
        "prompt_versions": {name: config.routing.prompts[name] for name in sorted(POST_PROMPTS)},
    }


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


def current_pass_seq(runs: RunRepository, run_id: str) -> int:
    """The `seq` of the `run_extended` event that began the run's current post pass."""
    passes = [e.seq for e in runs.events(run_id) if e.type == EventType.RUN_EXTENDED]
    if passes:
        return passes[-1]
    # a run whose chains step ran before new runs recorded the event: that step's start
    return next(
        e.seq
        for e in runs.events(run_id)
        if e.type == EventType.STEP_STARTED and e.payload.get("step") == FIRST_POST_STEP
    )


def _check_rerun(runs: RunRepository, run: Run, rerun_from: str) -> None:
    if rerun_from not in RERUN_FROM:
        raise ExtendRefused(f"a re-run starts from {', '.join(RERUN_FROM)}, not {rerun_from}")
    if run.status != RunStatus.FINISHED and not stopped_at_post_cap(runs, run):
        raise ExtendRefused(f"run {run.id} is {run.status}, not finished")
    if not already_extended(runs, run.id):
        raise ExtendRefused(f"run {run.id}: its chains step has not run; extend it first")
    named = sorted(
        o.id for o in runs.overrides(run.id) if o.target_id.startswith(POST_RECORD_PREFIXES)
    )
    if named:
        raise ExtendRefused(
            f"run {run.id}: an override names a post-analysis record ({', '.join(named)})"
        )


def _check_retry(runs: RunRepository, run: Run) -> list[str]:
    if run.status != RunStatus.FINISHED:
        raise ExtendRefused(f"run {run.id} is {run.status}, not finished")
    failed = [q.id for q in runs.questions(run.id) if q.status == QuestionStatus.FAILED]
    if not failed:
        raise ExtendRefused(f"run {run.id} has no failed question to retry")
    named = sorted(
        o.id for o in runs.overrides(run.id) if o.target_id.startswith(POST_RECORD_PREFIXES)
    )
    if named:
        raise ExtendRefused(
            f"run {run.id}: an override names a post-analysis record ({', '.join(named)})"
        )
    return failed


def extend(
    runs: RunRepository,
    run_id: str,
    post_cap_usd: float,
    config: Config,
    *,
    rerun_from: str | None = None,
    retry_failed: bool = False,
    retry_cap_usd: float = 0.0,
) -> Run:
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if retry_failed:
        return _retry(runs, run, post_cap_usd, retry_cap_usd, config)
    resume = False
    if rerun_from is not None:
        _check_rerun(runs, run, rerun_from)
        pass_seq = current_pass_seq(runs, run_id)
    else:
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
        payload = {
            **post_pass(run, config, post_cap_usd),
            "resumed_after_post_cap": resume,
            "step": writer.run.step,
        }
        if rerun_from is None:
            writer.emit(EventType.RUN_EXTENDED, payload)
        else:
            # the event lists every record it supersedes; the copy names the event's seq
            superseded = writer.post_record_ids(POST_JOBS)
            event = writer.emit(
                EventType.RUN_EXTENDED,
                {
                    **payload,
                    "rerun_from": rerun_from,
                    "superseded_pass_seq": pass_seq,
                    "superseded_ids": superseded,
                },
            )
            copied = writer.supersede_post_records(pass_seq, event.seq, POST_JOBS)
            if copied != superseded:  # one transaction: nothing can change in between
                raise RuntimeError(f"run {run_id}: the superseded records changed while copying")
    extended = runs.get(run_id)
    if extended is None:
        raise LookupError(f"run {run_id} disappeared while extending")
    return extended


def _retry(
    runs: RunRepository, run: Run, post_cap_usd: float, retry_cap_usd: float, config: Config
) -> Run:
    failed = _check_retry(runs, run)
    had_post_pass = already_extended(runs, run.id)
    pass_seq = current_pass_seq(runs, run.id) if had_post_pass else None
    with runs.step(run.id) as writer:
        writer.set_spend_cap(run.spend_cap_usd + retry_cap_usd)
        writer.set_post_spend_cap(post_cap_usd)
        writer.set_step(RETRY_STEP)
        writer.set_status(RunStatus.RUNNING)
        superseded = writer.post_record_ids(POST_JOBS)
        event = writer.emit(
            EventType.RUN_EXTENDED,
            {
                **post_pass(run, config, post_cap_usd),
                "resumed_after_post_cap": False,
                "step": RETRY_STEP,
                "rerun_from": RETRY_STEP,
                "retry_failed": failed,
                "retry_cap_usd": retry_cap_usd,
                "superseded_pass_seq": pass_seq,
                "superseded_ids": superseded,
            },
        )
        if pass_seq is not None:
            copied = writer.supersede_post_records(pass_seq, event.seq, POST_JOBS)
            if copied != superseded:  # one transaction: nothing can change in between
                raise RuntimeError(f"run {run.id}: the superseded records changed while copying")
    extended = runs.get(run.id)
    if extended is None:
        raise LookupError(f"run {run.id} disappeared while extending")
    return extended
