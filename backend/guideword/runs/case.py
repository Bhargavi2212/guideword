"""One case end to end (spec 2.9), shared by `scripts/run_case.py` and the replay test: store
the plant, confirm the rule cut (no suggestions), start the run, advance it until it stops,
and report what it found. The report is computed from the run's records (R11); nothing in
it is typed or stored elsewhere.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from guideword.chains.connector import ConnectorStepper
from guideword.chains.severity import ChainSeverityStepper
from guideword.config import CapsConfig, Config
from guideword.evidence.step import EvidenceStepper, EvidenceTools
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import Ledger
from guideword.lopa.engine import CODE_ONLY_FLAG
from guideword.lopa.lines import NONE, ShortlistLine, display_lines, lopa_plan, shortlist
from guideword.lopa.step import LopaStepper
from guideword.orchestrator.loop import OrchestratorStepper
from guideword.questions.coverage import coverage
from guideword.ranking.rank import RankedFinding, fold, rank_findings
from guideword.ranking.severity import RankedStepper, SeverityStepper
from guideword.ranking.tiers import (
    UNCONFIRMED_FLAG,
    TieredLine,
    lead_prefers_own_section,
    tiered,
)
from guideword.recommend.step import RecommendationStepper
from guideword.reference import ReferenceSet
from guideword.reference.precedents import load_precedent_index
from guideword.runs.machine import Stepper, advance
from guideword.runs.plants import PlantRepository, load_plant, plant_facts
from guideword.runs.post_budget import (
    POST_HASH_FREE_CAPS,
    POST_JOBS,
    POST_PROMPTS,
    post_spent,
)
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import (
    BudgetUse,
    EventType,
    QuestionKind,
    QuestionStatus,
    RunStatus,
    ShortlistTier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import (
    OUTSIDE_LIBRARY,
    Event,
    Finding,
    Hypothesis,
    PlantRecord,
    Question,
    Run,
    Section,
)
from guideword.schema.validate import Issue
from guideword.screen.step import PlantScreenStepper
from guideword.sections.rules import rule_cut
from guideword.specialists.retry_step import RetryFailedStepper
from guideword.tools.web import SearchClient, WebSearch

DASH = " — "
# G10: a run from before R50 has no whole-plant pass, so every line is "also found"
PRE_R50_LABEL = "pre-R50 run"


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
    """A new run's hashed inputs. The post-step prompts and caps are left out (connector/v2
    plan, Q5), and so are the post-step jobs' routing and `max_tokens` (Phase 4 plan, Q3):
    they are recorded on the run's `run_extended` event, so changing one never moves a run ID.
    The evidence settings are outside the hashed caps altogether (P4-9). The hash covers what a
    run stores, so older runs (D–G store `lopa_top_n` and the post jobs) keep their IDs."""
    caps = {k: v for k, v in config.caps.run_input_caps().items() if k not in POST_HASH_FREE_CAPS}
    caps["max_tokens"] = {k: v for k, v in caps["max_tokens"].items() if k not in POST_JOBS}
    prompts = {k: v for k, v in config.routing.prompts.items() if k not in POST_PROMPTS}
    jobs: dict[str, str] = {k: v for k, v in config.routing.jobs.items() if k not in POST_JOBS}
    return RunSettings(jobs, caps, prompts)


def start_case(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    config: Config,
    plant_record_id: str,
    spend_cap_usd: float,
    mode: str = "full",
    *,
    post_spend_cap_usd: float | None = None,
) -> Run:
    """`post_spend_cap_usd` defaults to `run.post_spend_cap_usd` in caps.yaml (Q20)."""
    post = (
        post_spend_cap_usd if post_spend_cap_usd is not None else config.caps.run.post_spend_cap_usd
    )
    return start_run(
        plants,
        runs,
        ref,
        run_settings(config),
        plant_record_id=plant_record_id,
        spend_cap_usd=spend_cap_usd,
        mode=mode,
        post_spend_cap_usd=post,
    )


def evidence_tools(
    *,
    config: Config,
    cache: ResponseCache,
    ledger: Ledger,
    use: BudgetUse,
    phase: str,
    clock: Callable[[], datetime],
    search: SearchClient,
    enabled: bool = True,
) -> EvidenceTools:
    """The evidence step's tools for a run: a web search on the run's own cache and ledger (the
    gateway's), and the precedent index (Phase 4 plan PR 5b)."""
    web = WebSearch(
        client=search,
        cache=cache,
        ledger=ledger,
        config=config,
        use=use,
        phase=phase,
        clock=clock,
    )
    return EvidenceTools(web=web, index=load_precedent_index(), enabled=enabled)


def steppers_for(
    gateway: Gateway,
    config: Config,
    ref: ReferenceSet,
    plant: Plant,
    *,
    evidence: EvidenceTools | None = None,
) -> dict[str, Stepper]:
    """`evidence`: the web search and precedent index the evidence step uses. Without them the
    step records "evidence off" and moves on (a test or a replay that doesn't ask for it)."""
    return {
        "plant_screen": PlantScreenStepper(gateway, config=config, ref=ref, plant=plant),
        "analysis": OrchestratorStepper(gateway, config=config, ref=ref, plant=plant),
        "severity": SeverityStepper(gateway, config=config, ref=ref, plant=plant),
        # demo-fixes plan: a finished run's failed questions, each asked alone, then severity
        "retry_failed": RetryFailedStepper(gateway, config=config, ref=ref, plant=plant),
        # Phase 3 (spec 3.6): the post-analysis steps, then ranked ends the run
        "chains": ConnectorStepper(gateway, config=config, ref=ref, plant=plant),
        "chain_severity": ChainSeverityStepper(gateway, config=config, ref=ref, plant=plant),
        "lopa": LopaStepper(gateway, config=config, ref=ref, plant=plant),
        "recommendations": RecommendationStepper(gateway, config=config, ref=ref, plant=plant),
        # Phase 4 (spec 4.4): evidence on the top lines, then ranked ends the run
        "evidence": EvidenceStepper(gateway, config=config, ref=ref, plant=plant, tools=evidence),
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


def _line(r: RankedFinding, causes: Mapping[str, str], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
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
        # P3-4/5 assumptions (G12), shown in screening as in LOPA
        "likelihood_flags": list(r.likelihood.flags),
        "superseded_by": r.superseded_by,
        "tier": r.finding.tier,
        "confidence": r.finding.confidence,
    }


def folded_lines(
    findings: Sequence[Finding], plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[dict[str, Any]]:
    """R48: one line per cause and failing components, its worst finding shown; the scorer
    and the hand sheet read these."""
    causes = {c.id: c.cause for c in ref.causes}
    return [
        _line(line.worst, causes, line.rank)
        | {
            "folded_count": len(line.folded),
            "folded_finding_ids": [r.finding.id for r in line.folded],
        }
        for line in fold(rank_findings(findings, plant, ref, caps))
    ]


def _hypothesis_text(h: Hypothesis) -> str:
    """The whole-plant pass's own words: `<mechanism> — <consequence>` (plan C3, G13)."""
    return f"{h.mechanism}{DASH}{h.consequence}"


def _tiered_line(line: TieredLine, rank: int, causes: Mapping[str, str]) -> dict[str, Any]:
    """A displayed line (R50). The scorer reads `text`: on hypothesis lines the hypothesis's
    words only; the hand sheet reads `sheet_text`, which also shows the lead finding (C3)."""
    h = line.hypothesis
    row: dict[str, Any] = (
        _line(line.lead, causes, rank)
        if line.lead is not None
        else {
            "rank": rank,
            "finding_id": None,
            "question_id": "",
            "failing_component_ids": list(h.component_ids) if h else [],
            "rating": None,
            "severity_class": None,
            "likelihood_class": None,
        }
    )
    lead_text = _text(line.lead.finding, causes) if line.lead is not None else None
    text = _hypothesis_text(h) if h is not None else (lead_text or "")
    row |= {
        "tier": line.tier.value,
        "text": text,
        "sheet_text": f"{text} | finding: {lead_text}" if h is not None and lead_text else text,
        "lead_text": lead_text,
        "hypothesis_id": h.id if h else None,
        "hypothesis_rank": h.rank if h else None,
        "support_finding_ids": list(line.support_ids),
        "shown_under": list(line.shown_under),
        "folded_count": len(line.folded),
        "folded_finding_ids": [r.finding.id for r in line.folded],
    }
    if line.tier == ShortlistTier.UNCONFIRMED:
        row["flag"] = UNCONFIRMED_FLAG
    return row


def tiered_lines(
    findings: Sequence[Finding],
    hypotheses: Sequence[Hypothesis],
    questions: Sequence[Question],
    plant: Plant,
    ref: ReferenceSet,
    caps: CapsConfig,
    *,
    sections: Sequence[Section],
    code_order: bool = False,
    prefer_own_section: bool = False,
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}
    ranked = rank_findings(findings, plant, ref, caps)
    lines = tiered(
        ranked,
        hypotheses,
        findings,
        questions,
        sections=sections,
        code_order=code_order,
        prefer_own_section=prefer_own_section,
    )
    return [_tiered_line(line, rank, causes) for rank, line in enumerate(lines, start=1)]


def plant_screen_lines(hypotheses: Sequence[Hypothesis]) -> list[dict[str, Any]]:
    """The whole-plant pass's own ranked list, as config `5a-plant` (spec 2b.4)."""
    return [
        {
            "rank": h.rank,
            "text": _hypothesis_text(h),
            "sheet_text": _hypothesis_text(h),
            "hypothesis_id": h.id,
            "question_id": "",
            "failing_component_ids": list(h.component_ids),
        }
        for h in sorted(hypotheses, key=lambda h: h.rank)
    ]


def ranked_lines(
    findings: Sequence[Finding], plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}
    return [_line(r, causes, r.rank) for r in rank_findings(findings, plant, ref, caps)]


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


def priority_summary(events: Sequence[Event], hypotheses: Sequence[Hypothesis]) -> dict[str, int]:
    """The run summary line of spec 2b.3 (G15): how many linked questions were answered
    before the first dispatch that sent an unlinked one. Code does not force the order; it
    reports it. A dispatch's batches run together, so that dispatch's linked answers count."""
    answered = 0
    for event in sorted(events, key=lambda e: e.seq):
        if event.type != EventType.DISPATCH:
            continue
        answered += int(event.payload.get("linked_answered", 0))
        if event.payload.get("unlinked_sent", 0):
            break
    return {
        "linked_questions": len({q for h in hypotheses for q in h.question_ids}),
        "linked_answered_before_first_unlinked": answered,
    }


def is_pre_r50(run: Run) -> bool:
    """G10: a run started before R50 has no whole-plant prompt among its inputs."""
    return "plant_screen" not in run.prompt_versions


def _shortlist_row(item: ShortlistLine, rank: int, pre_r50: bool) -> dict[str, Any]:
    planned, record = item.planned, item.lopa
    kind = None
    if record is not None:
        kind = "code_only" if CODE_ONLY_FLAG in record.flags else "full"
    return {
        "rank": rank,
        "target_id": planned.target_id,
        "target_kind": planned.target_kind,
        "tier": planned.tier.value,
        "position": planned.position,
        "severity_class": planned.severity_class.value if planned.severity_class else None,
        "lopa_id": record.id if record else None,
        "lopa": kind,
        "complete": record.complete if record else None,
        "gap": record.gap if record else None,
        "no_lopa_reason": item.no_lopa_reason,
        "flags": [*item.flags, *([PRE_R50_LABEL] if pre_r50 else [])],
        "recommendation_ids": [r.id for r in item.recommendations],
    }


def post_report(
    runs: RunRepository, run: Run, plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> dict[str, Any]:
    """The Phase 3 part of the report (plan PR 5): the shortlist, chains, LOPA records and
    recommendations, all computed from the run's records, and what the connector left out."""
    findings = runs.findings(run.id)
    questions = runs.questions(run.id)
    sections = runs.sections(run.id)
    chains = runs.chains(run.id)
    records = runs.lopa_records(run.id)
    recommendations = runs.recommendations(run.id)
    calls = runs.model_calls(run.id)
    lead_rule = lead_prefers_own_section(run.caps, runs.events(run.id))
    lines = display_lines(
        findings,
        runs.hypotheses(run.id),
        questions,
        sections,
        plant,
        ref,
        caps,
        prefer_own_section=lead_rule,
    )
    # G8: the run's own lopa_top_n
    top_n = int(run.caps.get("lopa_top_n", caps.run.lopa_top_n))
    plan = lopa_plan(lines, chains, findings, questions, sections, top_n=top_n)
    items = shortlist(
        plan, records, recommendations, calls, run_id=run.id, plant=plant, ref=ref, caps=caps
    )
    pre_r50 = is_pre_r50(run)
    finished = [
        e.payload
        for e in runs.events(run.id)
        if e.type == EventType.STEP_FINISHED and e.payload.get("step") == "chains"
    ]
    connector = finished[-1] if finished else {}
    return {
        "pre_r50": pre_r50,
        "post_spend_cap_usd": run.post_spend_cap_usd,
        "post_spent_usd": post_spent(calls),
        "shortlist": [_shortlist_row(item, i, pre_r50) for i, item in enumerate(items, start=1)],
        "chains": [c.model_dump(mode="json") for c in chains],
        "chains_rejected": list(connector.get("rejected", [])),
        "connector": connector.get("connector"),
        "lopa": [r.model_dump(mode="json") for r in records],
        "lopa_none": [
            {"target_id": p.target_id, "reason": p.reason} for p in plan if p.kind == NONE
        ],
        "recommendations": [r.model_dump(mode="json") for r in recommendations],
    }


def case_report(
    runs: RunRepository, run_id: str, plant: Plant, ref: ReferenceSet, caps: CapsConfig, case: str
) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    questions = runs.questions(run_id)
    findings = runs.findings(run_id)
    hypotheses = runs.hypotheses(run_id)
    events = runs.events(run_id)
    sections = runs.sections(run_id)
    lines, failed = coverage(sections, questions, findings)
    dropped = [
        i for e in events if e.type == EventType.DISPATCH for i in e.payload.get("dropped_ids", [])
    ]
    ranked = ranked_lines(findings, plant, ref, caps)
    folded = folded_lines(findings, plant, ref, caps)
    # the run's lead tie-break (lead tie-break plan): off for runs stored without it
    lead_rule = lead_prefers_own_section(run.caps, events)
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
        "folded": folded,
        # R50: the displayed tiered list (scored), and three views of the same run at $0
        "hypotheses": [h.model_dump(mode="json") for h in hypotheses],
        "hybrid": tiered_lines(
            findings,
            hypotheses,
            questions,
            plant,
            ref,
            caps,
            sections=sections,
            prefer_own_section=lead_rule,
        ),
        "hybrid-codeorder": tiered_lines(
            findings,
            hypotheses,
            questions,
            plant,
            ref,
            caps,
            sections=sections,
            code_order=True,
            prefer_own_section=lead_rule,
        ),
        "5a-plant": plant_screen_lines(hypotheses),
        "5b-from-hybrid": folded,
        "priority": priority_summary(events, hypotheses),
    } | post_report(runs, run, plant, ref, caps)
