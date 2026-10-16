"""One case end to end (spec 2.9), shared by `scripts/run_case.py` and the replay test: store
the plant, confirm the rule cut (no suggestions), start the run, advance it until it stops,
and report what it found. The report is computed from the run's records (R11); nothing in
it is typed or stored elsewhere.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from guideword.config import CapsConfig, Config
from guideword.gateway.client import Gateway
from guideword.orchestrator.loop import OrchestratorStepper
from guideword.questions.coverage import coverage
from guideword.ranking.rank import rank_findings
from guideword.ranking.severity import RankedStepper, SeverityStepper
from guideword.reference import ReferenceSet
from guideword.runs.machine import Stepper, advance
from guideword.runs.plants import PlantRepository, load_plant, plant_facts
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, QuestionKind, QuestionStatus, RunStatus
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding, PlantRecord, Question, Run
from guideword.schema.validate import Issue
from guideword.sections.rules import rule_cut

DASH = " — "


class InvalidPlant(ValueError):
    def __init__(self, errors: Sequence[Issue]) -> None:
        super().__init__("; ".join(f"{e.object_id or '-'}: {e.message}" for e in errors))
        self.errors = list(errors)


def prepare_plant(
    plants: PlantRepository, raw: Mapping[str, Any], ref: ReferenceSet
) -> PlantRecord:
    """Store the plant (once) and confirm its rule cut. Raises `InvalidPlant`."""
    record, report = load_plant(raw, ref)
    if record is None:
        raise InvalidPlant(report.errors)
    plants.add(record, raw, plant_facts(record.plant_file, record.id))
    plants.confirm(record.id, rule_cut(record.plant_file, record.id))
    return record


def run_settings(config: Config) -> RunSettings:
    return RunSettings(
        dict(config.routing.jobs), config.caps.run_input_caps(), dict(config.routing.prompts)
    )


def start_case(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    config: Config,
    plant_record_id: str,
    spend_cap_usd: float,
    mode: str = "full",
) -> Run:
    return start_run(
        plants,
        runs,
        ref,
        run_settings(config),
        plant_record_id=plant_record_id,
        spend_cap_usd=spend_cap_usd,
        mode=mode,
    )


def steppers_for(
    gateway: Gateway, config: Config, ref: ReferenceSet, plant: Plant
) -> dict[str, Stepper]:
    return {
        "analysis": OrchestratorStepper(gateway, config=config, ref=ref, plant=plant),
        "severity": SeverityStepper(gateway, config=config, ref=ref, plant=plant),
        "ranked": RankedStepper(),
    }


def drive(runs: RunRepository, run_id: str, steppers: Mapping[str, Stepper]) -> RunStatus:
    """Advance until the run is no longer running. It ends because every step is bounded: the
    orchestrator's step cap, severity's batches, and the gateway's caps."""
    status = RunStatus.RUNNING
    while status == RunStatus.RUNNING:
        status = advance(runs, run_id, steppers)
    return status


def _text(finding: Finding, causes: Mapping[str, str]) -> str:
    """The agent's own words, as the scorer reads them: `<cause> — <consequence>` (R26c)."""
    cause = (
        finding.cause_text or ""
        if finding.cause_id == OUTSIDE_LIBRARY
        else causes.get(finding.cause_id, finding.cause_id)
    )
    return f"{cause}{DASH}{finding.consequence}"


def ranked_lines(
    findings: Sequence[Finding], plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}
    return [
        {
            "rank": r.rank,
            "finding_id": r.finding.id,
            "question_id": r.finding.question_id,
            "failing_component_ids": list(r.finding.failing_component_ids),
            "text": _text(r.finding, causes),
            "cause_id": r.finding.cause_id,
            "severity_class": r.finding.severity_class,
            "severity_reason": r.finding.severity_reason,
            "likelihood_class": r.likelihood.likelihood_class,
            "frequency_per_year": r.likelihood.frequency_per_year,
            "frequency_assumed": r.likelihood.assumed,
            "initiating_event_id": r.likelihood.initiating_event_id,
            "rating": r.rating,
            "unrated_reason": r.unrated_reason,
            "missing_fact_ids": list(r.missing_fact_ids),
            "note": r.likelihood.note,
            "superseded_by": r.superseded_by,
            "tier": r.finding.tier,
            "confidence": r.finding.confidence,
        }
        for r in rank_findings(findings, plant, ref, caps)
    ]


def not_credible_counts(questions: Sequence[Question]) -> list[dict[str, Any]]:
    """Per list, how the checked questions split: answered, or dismissed as not credible.
    Coverage counts both as checked, so this keeps the dismissed ones visible."""
    rows = []
    for kind in QuestionKind:
        listed = [q for q in questions if q.kind == kind]
        answered = sum(1 for q in listed if q.status == QuestionStatus.ANSWERED)
        dismissed = sum(1 for q in listed if q.status == QuestionStatus.NOT_CREDIBLE)
        rows.append(
            {
                "list": kind.value,
                "checked": answered + dismissed,
                "answered": answered,
                "not_credible": dismissed,
            }
        )
    return rows


def case_report(
    runs: RunRepository, run_id: str, plant: Plant, ref: ReferenceSet, caps: CapsConfig, case: str
) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    questions = runs.questions(run_id)
    findings = runs.findings(run_id)
    events = runs.events(run_id)
    lines, failed = coverage(runs.sections(run_id), questions, findings)
    dropped = [
        i for e in events if e.type == EventType.DISPATCH for i in e.payload.get("dropped_ids", [])
    ]
    ranked = ranked_lines(findings, plant, ref, caps)
    return {
        "case": case,
        "run_id": run.id,
        "plant_record_id": run.plant_record_id,
        "status": run.status.value,
        "spend_cap_usd": run.spend_cap_usd,
        "spent_usd": run.spent_usd,
        "cap_spent_usd": run.cap_spent_usd,
        "seconds": (events[-1].time - events[0].time).total_seconds() if events else 0.0,
        "coverage": [line.model_dump(mode="json") for line in lines],
        "failed_question_ids": failed,
        "not_credible": not_credible_counts(questions),
        "open_questions": sum(1 for q in questions if q.status == QuestionStatus.OPEN),
        "cap_hits": [e.payload for e in events if e.type == EventType.CAP_HIT],
        # R43: steps and jobs dropped to fit a specialist batch
        "dropped": {"total": len(dropped), "distinct": len(set(dropped))},
        "unrated": sum(1 for r in ranked if r["rating"] is None),
        "ranked": ranked,
    }
