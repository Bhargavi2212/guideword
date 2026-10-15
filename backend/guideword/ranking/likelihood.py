"""Likelihood, by code only (spec 2.6; PROJECT.md §5 Step 6; plan R12).

A library cause's initiating event gives the frequency: `per_year` directly; `per_metre_year`
times the failing line's `length_m`; `per_lift` times the job's `lifts_per_year`. A missing
fact leaves the finding unrated and names the fact. `per_opportunity` has no demand rate in
the plant file, so it is unrated in this phase. An outside-library cause gets the highest
frequency among library causes of the same failing-component type (converted the same way),
or the configured default, flagged "frequency assumed". The band is the one that holds the
frequency, including its upper edge.
"""

from dataclasses import dataclass

from guideword.config import CapsConfig
from guideword.reference import ReferenceSet
from guideword.reference.tables import InitiatingEventRow
from guideword.schema import ids
from guideword.schema.enums import LikelihoodClass, QuestionKind
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding

PER_YEAR = "per_year"
PER_METRE_YEAR = "per_metre_year"
PER_LIFT = "per_lift"
PER_OPPORTUNITY = "per_opportunity"


@dataclass(frozen=True)
class Likelihood:
    frequency_per_year: float | None
    likelihood_class: LikelihoodClass | None
    initiating_event_id: str | None = None
    missing_fact_ids: tuple[str, ...] = ()
    # an outside-library cause's frequency, or the default: "frequency assumed"
    assumed: bool = False
    note: str | None = None


def band_for(frequency: float, ref: ReferenceSet) -> LikelihoodClass:
    """The band holding `frequency`: min < f <= max; the top band has no upper limit."""
    for band in sorted(ref.likelihood_classes, key=lambda b: b.min_per_year):
        if frequency > band.min_per_year and (
            band.max_per_year is None or frequency <= band.max_per_year
        ):
            return band.likelihood_class
        if band.min_per_year == 0 and frequency <= (band.max_per_year or 0):
            return band.likelihood_class
    raise ValueError(f"no likelihood band holds {frequency} per year")


def _job_for(finding: Finding, plant: Plant) -> str | None:
    jobs = {w.id for w in plant.planned_work}
    parsed = ids.parse_question_id(finding.question_id)
    if parsed.kind == QuestionKind.PLANNED_WORK and parsed.parts[0] in jobs:
        return parsed.parts[0]
    return next((c for c in finding.failing_component_ids if c in jobs), None)


def _convert(
    event: InitiatingEventRow, finding: Finding, plant: Plant
) -> tuple[float | None, tuple[str, ...], str | None]:
    """(frequency per year, missing fact IDs, note)."""
    if event.unit == PER_YEAR:
        return event.frequency, (), None
    if event.unit == PER_METRE_YEAR:
        lines = {line.id: line for line in plant.lines}
        failing = [lines[c] for c in finding.failing_component_ids if c in lines]
        if not failing:
            return None, (), "a per_metre_year cause names no line, so no length applies"
        missing = tuple(
            ids.fact_id(line.id, "length_m") for line in failing if line.length_m is None
        )
        if missing:
            return None, missing, None
        return event.frequency * sum(line.length_m or 0 for line in failing), (), None
    if event.unit == PER_LIFT:
        job_id = _job_for(finding, plant)
        if job_id is None:
            return None, (), "a per_lift cause names no planned job, so no lift count applies"
        job = next(w for w in plant.planned_work if w.id == job_id)
        if job.lifts_per_year is None:
            return None, (ids.fact_id(job.id, "lifts_per_year"),), None
        return event.frequency * job.lifts_per_year, (), None
    return None, (), f"{event.id} is {PER_OPPORTUNITY}: the plant file has no demand rate"


def likelihood(finding: Finding, plant: Plant, ref: ReferenceSet, caps: CapsConfig) -> Likelihood:
    events = {e.id: e for e in ref.initiating_events}
    if finding.cause_id != OUTSIDE_LIBRARY:
        cause = next((c for c in ref.causes if c.id == finding.cause_id), None)
        if cause is None:
            return Likelihood(None, None, note=f"{finding.cause_id} is not in the cause library")
        event = events[cause.initiating_event_id]
        frequency, missing, note = _convert(event, finding, plant)
        band = band_for(frequency, ref) if frequency is not None else None
        return Likelihood(frequency, band, event.id, missing, False, note)

    # outside library: the highest converted frequency among library causes of the same type
    best: tuple[float, str] | None = None
    for cause in ref.causes:
        if cause.failing_component_type != finding.failing_component_type:
            continue
        event = events[cause.initiating_event_id]
        frequency, _, _ = _convert(event, finding, plant)
        if frequency is not None and (best is None or frequency > best[0]):
            best = (frequency, event.id)
    if best is None:
        default = caps.ranking.outside_library_default_frequency_per_year
        return Likelihood(
            default, band_for(default, ref), None, (), True, "frequency assumed (default)"
        )
    return Likelihood(best[0], band_for(best[0], ref), best[1], (), True, "frequency assumed")
