"""Likelihood, by code only (spec 2.6; PROJECT.md §5 Step 6; plan R12).

A library cause's initiating event gives the frequency: `per_year` directly; `per_metre_year`
times the failing line's `length_m`; `per_lift` times the job's `lifts_per_year`. A missing
fact leaves the finding unrated and names the fact. `per_opportunity` has no demand rate in
the plant file, so it is unrated in this phase. An outside-library cause gets the highest
frequency among library causes of the same failing-component type (converted the same way),
or the configured default, flagged "frequency assumed". The band is the one that holds the
frequency, including its upper edge.

Phase 3 (P3-4, P3-5): a cause on the small piping-leak event uses the large-leak event on each
failing line whose `size_mm` is above `ranking.pipe_leak_large_above_mm`; a line with no size
stays on the small event, flagged. A cause on the monthly human-error event is flagged "task
frequency assumed". Screening and LOPA both read this one function, so they always agree.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from guideword.config import CapsConfig
from guideword.reference import ReferenceSet
from guideword.reference.tables import InitiatingEventRow
from guideword.schema import ids
from guideword.schema.enums import LikelihoodClass, QuestionKind
from guideword.schema.plant import Line, Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding

PER_YEAR = "per_year"
PER_METRE_YEAR = "per_metre_year"
PER_LIFT = "per_lift"
PER_OPPORTUNITY = "per_opportunity"

# initiating_events.csv rows the P3-4 and P3-5 rules name; their frequencies come from the table
PIPE_LEAK_SMALL_EVENT = "IE-PIPE-LEAK-S"
PIPE_LEAK_LARGE_EVENT = "IE-PIPE-LEAK-L"
HUMAN_ERROR_MONTHLY_EVENT = "IE-HE-MONTHLY"
TASK_FREQUENCY_FLAG = "task frequency assumed — engineer to confirm"


@dataclass(frozen=True)
class Likelihood:
    frequency_per_year: float | None
    likelihood_class: LikelihoodClass | None
    initiating_event_id: str | None = None
    missing_fact_ids: tuple[str, ...] = ()
    # an outside-library cause's frequency, or the default: "frequency assumed"
    assumed: bool = False
    note: str | None = None
    # assumptions the engineer should confirm (P3-4, P3-5), shown in screening and LOPA
    flags: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class _Converted:
    frequency: float | None
    missing: tuple[str, ...] = ()
    note: str | None = None
    # the event actually used, when the size rule changed it
    event_id: str | None = None
    flags: tuple[str, ...] = ()


def _line_event(
    line: Line,
    event: InitiatingEventRow,
    events: Mapping[str, InitiatingEventRow],
    caps: CapsConfig,
) -> tuple[InitiatingEventRow, str | None]:
    """P3-4: the leak event for one line, and the flag when its size is assumed."""
    if event.id != PIPE_LEAK_SMALL_EVENT:
        return event, None
    threshold = caps.ranking.pipe_leak_large_above_mm
    if line.size_mm is None:
        return event, f"size assumed ≤ {threshold:g} mm ({ids.fact_id(line.id, 'size_mm')})"
    if line.size_mm > threshold:
        return events[PIPE_LEAK_LARGE_EVENT], None
    return event, None


def _per_metre(
    event: InitiatingEventRow,
    finding: Finding,
    plant: Plant,
    events: Mapping[str, InitiatingEventRow],
    caps: CapsConfig,
) -> _Converted:
    lines = {line.id: line for line in plant.lines}
    failing = [lines[c] for c in finding.failing_component_ids if c in lines]
    if not failing:
        return _Converted(None, note="a per_metre_year cause names no line, so no length applies")
    chosen = [_line_event(line, event, events, caps) for line in failing]
    flags = tuple(flag for _, flag in chosen if flag is not None)
    used = {e.id for e, _ in chosen}
    # one event for every line names it; mixed sizes name the cause's own event, flagged
    event_id = next(iter(used)) if len(used) == 1 else event.id
    if len(used) > 1:
        split = ", ".join(f"{line.id} {e.id}" for line, (e, _) in zip(failing, chosen, strict=True))
        flags = (*flags, f"lines use different leak events: {split}")
    missing = tuple(ids.fact_id(line.id, "length_m") for line in failing if line.length_m is None)
    if missing:
        return _Converted(None, missing, event_id=event_id, flags=flags)
    frequency = sum(
        e.frequency * (line.length_m or 0) for line, (e, _) in zip(failing, chosen, strict=True)
    )
    return _Converted(frequency, event_id=event_id, flags=flags)


def _convert(
    event: InitiatingEventRow,
    finding: Finding,
    plant: Plant,
    events: Mapping[str, InitiatingEventRow],
    caps: CapsConfig,
) -> _Converted:
    if event.unit == PER_YEAR:
        flags = (TASK_FREQUENCY_FLAG,) if event.id == HUMAN_ERROR_MONTHLY_EVENT else ()
        return _Converted(event.frequency, flags=flags)
    if event.unit == PER_METRE_YEAR:
        return _per_metre(event, finding, plant, events, caps)
    if event.unit == PER_LIFT:
        job_id = _job_for(finding, plant)
        if job_id is None:
            return _Converted(
                None, note="a per_lift cause names no planned job, so no lift count applies"
            )
        job = next(w for w in plant.planned_work if w.id == job_id)
        if job.lifts_per_year is None:
            return _Converted(None, (ids.fact_id(job.id, "lifts_per_year"),))
        return _Converted(event.frequency * job.lifts_per_year)
    return _Converted(
        None, note=f"{event.id} is {PER_OPPORTUNITY}: the plant file has no demand rate"
    )


def likelihood(finding: Finding, plant: Plant, ref: ReferenceSet, caps: CapsConfig) -> Likelihood:
    events = {e.id: e for e in ref.initiating_events}
    if finding.cause_id != OUTSIDE_LIBRARY:
        cause = next((c for c in ref.causes if c.id == finding.cause_id), None)
        if cause is None:
            return Likelihood(None, None, note=f"{finding.cause_id} is not in the cause library")
        event = events[cause.initiating_event_id]
        got = _convert(event, finding, plant, events, caps)
        band = band_for(got.frequency, ref) if got.frequency is not None else None
        return Likelihood(
            got.frequency, band, got.event_id or event.id, got.missing, False, got.note, got.flags
        )

    # outside library: the highest converted frequency among library causes of the same type
    best: tuple[float, str, tuple[str, ...]] | None = None
    for cause in ref.causes:
        if cause.failing_component_type != finding.failing_component_type:
            continue
        event = events[cause.initiating_event_id]
        got = _convert(event, finding, plant, events, caps)
        if got.frequency is not None and (best is None or got.frequency > best[0]):
            best = (got.frequency, got.event_id or event.id, got.flags)
    if best is None:
        default = caps.ranking.outside_library_default_frequency_per_year
        return Likelihood(
            default, band_for(default, ref), None, (), True, "frequency assumed (default)"
        )
    return Likelihood(
        best[0], band_for(best[0], ref), best[1], (), True, "frequency assumed", best[2]
    )
