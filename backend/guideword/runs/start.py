"""Starting a run (spec 2.1; PROJECT.md §11 "Run" ID rule).

A run starts from a snapshot of the plant's confirmed sections. Its ID is built from its
inputs (never the spend cap), so identical inputs resume an unfinished run, a finished,
cancelled or failed one is followed by attempt `:n`, and a `stopped_cap` run resumes only
with a higher cap. Setup builds the question list with the Phase 1 builder.
"""

import math
from dataclasses import dataclass
from typing import Any

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository, base_run_id
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, PlantStatus, QuestionStatus, RunLabelKind, RunStatus
from guideword.schema.records import Run, RunLabel

FULL = "full"
# the whole-plant pass comes before any dispatch (R50)
FIRST_STEP = "plant_screen"
# statuses a new start with identical inputs picks up again
RESUMABLE = {RunStatus.STOPPED_CAP, RunStatus.STOPPED_BUDGET}
ANALYSIS = "analysis"
# the steps after the analysis (Phase 3 adds the post-analysis steps, spec 3.6); a resume
# from one of them with questions open goes back
AFTER_ANALYSIS = frozenset(
    {"severity", "chains", "chain_severity", "lopa", "recommendations", "evidence", "ranked"}
)


@dataclass(frozen=True)
class RunSettings:
    """The configured inputs of a run (the routing jobs, the caps that change answers, and
    the prompt versions); they are hashed into the run ID."""

    routing_config: dict[str, str]
    caps: dict[str, Any]
    prompt_versions: dict[str, str]


class PlantNotFound(LookupError):
    pass


class SectionsNotConfirmed(ValueError):
    def __init__(self) -> None:
        super().__init__("sections not confirmed")


class StartMismatch(ValueError):
    """A resume names a use or post cap other than the run's own: both are fixed when the run
    starts (contract v1.9, Q4, Q12). The message names the stored value."""


class ModeNotBuilt(ValueError):
    """Decision R21: only `full` runs exist until Phase 7."""

    def __init__(self, mode: str) -> None:
        super().__init__(f"{mode} mode is built in Phase 7")


def start_run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    *,
    plant_record_id: str,
    spend_cap_usd: float,
    mode: str,
    use: BudgetUse,
    post_spend_cap_usd: float,
) -> Run:
    """Start, resume or re-attempt the run for these inputs. Raises `ids.CapReachedError`,
    or `StartMismatch` when a resume names another use or post cap. `use` and
    `post_spend_cap_usd` (P3-2) are stored on a new run and fixed from then on; neither is
    an input of the run ID. A run stored without a use takes the one given (Q4)."""
    if mode != FULL:
        raise ModeNotBuilt(mode)
    stored = plants.get(plant_record_id)
    if stored is None:
        raise PlantNotFound(f"no plant {plant_record_id}")
    if stored.record.status != PlantStatus.SECTIONS_CONFIRMED:
        raise SectionsNotConfirmed()
    confirmed = set(stored.record.confirmed_section_ids)
    sections = [s for s in stored.sections if s.id in confirmed]

    inputs: dict[str, object] = {
        "plant_id": plant_record_id,
        "section_snapshot": [s.id for s in sections],
        "reference_versions": dict(ref.versions),
        "routing_config": dict(settings.routing_config),
        "caps": dict(settings.caps),
        "prompt_versions": dict(settings.prompt_versions),
        "mode": mode,
    }
    base = base_run_id(ids.run_id(inputs, [], spend_cap_usd=spend_cap_usd))
    run_id = ids.run_id(inputs, runs.attempts(base), spend_cap_usd=spend_cap_usd)

    existing = runs.get(run_id)
    if existing is not None:
        _check_fixed(existing, use, post_spend_cap_usd)
        if existing.use is None:
            with runs.step(run_id) as writer:
                writer.set_use(use)
            existing = existing.model_copy(update={"use": use})
        if existing.status in RESUMABLE:
            with runs.step(run_id) as writer:
                if existing.status == RunStatus.STOPPED_CAP:
                    writer.set_spend_cap(spend_cap_usd)
                    # R38: the analysis ended at the severity reserve with questions open and
                    # the run stopped after it; with more cap it goes back to the analysis, and
                    # severity then rates only the new findings (case E run 1)
                    past_analysis = existing.step in AFTER_ANALYSIS
                    if past_analysis and any(
                        q.status == QuestionStatus.OPEN for q in writer.questions()
                    ):
                        writer.set_step(ANALYSIS)
                writer.set_status(RunStatus.RUNNING)
            resumed = runs.get(run_id)
            if resumed is None:
                raise LookupError(f"run {run_id} disappeared while resuming")
            return resumed
        return existing

    attempt = 1 if run_id == base else int(run_id.rsplit(":", 1)[1])
    run = Run(
        id=run_id,
        plant_record_id=plant_record_id,
        attempt=attempt,
        section_snapshot=[s.id for s in sections],
        status=RunStatus.RUNNING,
        step=FIRST_STEP,
        mode="full",
        spend_cap_usd=spend_cap_usd,
        post_spend_cap_usd=post_spend_cap_usd,
        use=use,
        reference_versions=dict(ref.versions),
        routing_config=dict(settings.routing_config),
        caps=dict(settings.caps),
        prompt_versions=dict(settings.prompt_versions),
        label=RunLabel(kind=RunLabelKind.LIVE),
    )
    # setup: validate the snapshot (done above) and build the question list
    questions = build_questions(stored.record.plant_file, sections, ref, run.id)
    runs.create(
        run,
        sections,
        questions,
        {"attempt": attempt, "questions": len(questions), "sections": len(sections)},
    )
    return run


def _check_fixed(run: Run, use: BudgetUse, post_spend_cap_usd: float) -> None:
    """A run's use and post cap are fixed when it starts; never loosened silently."""
    if run.use is not None and run.use != use:
        raise StartMismatch(
            f"run {run.id} spends use {run.use.value}; a resume naming {use.value} is refused"
        )
    if not math.isclose(run.post_spend_cap_usd, post_spend_cap_usd):
        raise StartMismatch(
            f"run {run.id} has post cap ${run.post_spend_cap_usd}; a resume naming "
            f"${post_spend_cap_usd} is refused"
        )
