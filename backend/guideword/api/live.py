"""Live runs behind the run endpoints (spec 2.8; plan PR 10; Phase 3 plan PR 6). Every number
comes from the run store; nothing here calls a model except through the gateway the steppers
are given. The review reads (shortlist, worksheet, coverage, counts) apply the engineer's
overrides on read; the run dump serves the records as stored."""

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from guideword.api import models as api
from guideword.config import Config
from guideword.evidence.step import EvidenceTools
from guideword.gateway.client import Gateway
from guideword.questions.coverage import SECTIONS, coverage
from guideword.ranking.tiers import lead_prefers_own_section
from guideword.reference import ReferenceSet
from guideword.review.overrides import RunRecords, effective_question, new_override
from guideword.review.shortlist import RunView, shortlist_items
from guideword.review.worksheet import worksheet_rows
from guideword.runs.case import is_pre_r50, start_case, steppers_for
from guideword.runs.estimate import run_upper_bound
from guideword.runs.machine import Stepper, advance
from guideword.runs.plants import PlantRepository
from guideword.runs.store import Clock, RunRepository
from guideword.schema import ids
from guideword.schema.enums import (
    BudgetUse,
    EventType,
    OverrideAction,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    RunStatus,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Override, Question, Run
from guideword.specialists.run import JOB_FOR_LEVEL

# B2 (plan G5): one gateway, and one set of evidence tools, per budget use; a run is driven
# with those of its own recorded use
GatewayFactory = Callable[[sessionmaker[Session], BudgetUse], Gateway]
# Phase 4: the evidence step's tools for the API's runs (None: evidence off)
EvidenceFactory = Callable[[sessionmaker[Session], BudgetUse], EvidenceTools]


class RunNotFound(LookupError):
    pass


class RunEnded(ValueError):
    pass


# contract v1.9 (C3): the stored events whose tier is added on read
INFERRED_TIER_TYPES = frozenset({EventType.MODEL_CALL, EventType.DISPATCH})
INFERRED = "inferred"


class UseMismatch(ValueError):
    """An advance names no use for a run that has none, or a use other than the run's (contract
    v1.9, Q4). The message names the stored value."""


@dataclass(frozen=True)
class Record:
    kind: str
    record: dict[str, Any]
    parent_ids: list[str]
    model_call_ids: list[str]


class LiveRuns:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        config: Config,
        ref: ReferenceSet,
        gateway_factory: GatewayFactory,
        clock: Clock,
        evidence_factory: EvidenceFactory | None = None,
    ) -> None:
        self.sessions = sessions
        self.config = config
        self.ref = ref
        self.plants = PlantRepository(sessions)
        self.runs = RunRepository(sessions, clock)
        self._factory = gateway_factory
        self._gateways: dict[BudgetUse, Gateway] = {}
        self._evidence_factory = evidence_factory
        self._evidence: dict[BudgetUse, EvidenceTools] = {}
        # B2: the runs being driven now; a second drive of one returns at once (P5-2)
        self._driving: set[str] = set()
        self._driving_lock = threading.Lock()

    def gateway(self, use: BudgetUse) -> Gateway:
        if use not in self._gateways:
            self._gateways[use] = self._factory(self.sessions, use)
        return self._gateways[use]

    def get(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise RunNotFound(f"no run {run_id}")
        return run

    def plant_of(self, run: Run) -> Plant:
        stored = self.plants.get(run.plant_record_id)
        if stored is None:
            raise RunNotFound(f"no plant {run.plant_record_id} for run {run.id}")
        return stored.record.plant_file

    def evidence(self, use: BudgetUse) -> EvidenceTools | None:
        if self._evidence_factory is None:
            return None
        if use not in self._evidence:
            self._evidence[use] = self._evidence_factory(self.sessions, use)
        return self._evidence[use]

    def _steppers(self, run: Run) -> Mapping[str, Stepper]:
        """The run's steps, on the gateway of its own use (B2). A run stored without a use
        names one before it can be driven (Q4)."""
        if run.use is None:
            raise UseMismatch(f"run {run.id} has no use yet: name one on its next advance")
        return steppers_for(
            self.gateway(run.use),
            self.config,
            self.ref,
            self.plant_of(run),
            evidence=self.evidence(run.use),
        )

    # --- start, cancel, advance -------------------------------------------------------------

    def start(
        self,
        plant_record_id: str,
        spend_cap_usd: float,
        mode: str,
        *,
        use: BudgetUse,
        post_spend_cap_usd: float,
    ) -> tuple[Run, float]:
        """Start (or resume) the run; its upper-bound cost (R20). Raises PlantNotFound,
        SectionsNotConfirmed, ModeNotBuilt (R21), CapReachedError or StartMismatch."""
        run = start_case(
            self.plants,
            self.runs,
            self.ref,
            self.config,
            plant_record_id,
            spend_cap_usd,
            mode,
            use=use,
            post_spend_cap_usd=post_spend_cap_usd,
        )
        stored = self.plants.get(plant_record_id)
        assert stored is not None  # start_case found it
        estimate = run_upper_bound(
            run,
            plant=stored.record.plant_file,
            sections=self.runs.sections(run.id),
            questions=self.runs.questions(run.id),
            ref=self.ref,
            config=self.config,
            gateway=self.gateway(use),
        )
        return run, estimate

    def cancel(self, run_id: str) -> Run:
        run = self.get(run_id)
        if run.status in ids.ENDED_RUN_STATUSES:
            raise RunEnded(f"run {run_id} has already ended ({run.status.value})")
        with self.runs.step(run_id) as writer:
            writer.set_status(RunStatus.CANCELLED)
        return self.get(run_id)

    def name_use(self, run_id: str, use: BudgetUse | None) -> Run:
        """Contract v1.9 (Q4): an advance may name the run's use. A run with no use must name
        one, and keeps it; a use other than the run's is refused. Raises UseMismatch."""
        run = self.get(run_id)
        if run.use is None:
            if use is None:
                raise UseMismatch(f"run {run_id} has no use yet: name one on this advance")
            with self.runs.step(run_id) as writer:
                writer.set_use(use)
            return self.get(run_id)
        if use is not None and use != run.use:
            raise UseMismatch(
                f"run {run_id} spends use {run.use.value}; an advance naming {use.value} is refused"
            )
        return run

    def advance_once(self, run_id: str) -> RunStatus:
        run = self.get(run_id)
        return advance(self.runs, run_id, self._steppers(run))

    def step_once(self, run_id: str) -> RunStatus | None:
        """One step, unless the run is being driven now (then None: its driver goes on)."""
        with self._driving_lock:
            if run_id in self._driving:
                return None
            self._driving.add(run_id)
        try:
            return self.advance_once(run_id)
        finally:
            with self._driving_lock:
                self._driving.discard(run_id)

    def drive(self, run_id: str) -> RunStatus:
        """Advance until the run is no longer running (the in-process loop, laptop). One driver
        per run (P5-2): a drive of a run already being driven returns its status at once, so a
        second start or an advance never drives a run twice."""
        with self._driving_lock:
            if run_id in self._driving:
                return self.get(run_id).status
            self._driving.add(run_id)
        try:
            status = self.get(run_id).status
            while status == RunStatus.RUNNING:
                status = self.advance_once(run_id)
            return status
        finally:
            with self._driving_lock:
                self._driving.discard(run_id)

    # --- reads --------------------------------------------------------------------------------

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        """The run's events after `after`, as served. An event stored before v1.9 (no stamp)
        that is a `model_call` or `dispatch` gets its tier on read, labelled "inferred" and
        never written back (C3): a call's from its model ID against models.yaml, a dispatch's
        from its run's own routing config (plan H14); none found reads null ("unknown")."""
        run = self.get(run_id)
        by_model = {t.expected_id: str(tier) for tier, t in self.config.models.tiers.items()}
        served = []
        for event in self.runs.events(run_id, after):
            dumped = event.model_dump(mode="json")
            if event.payload_schema is None and event.type in INFERRED_TIER_TYPES:
                payload = dict(event.payload)
                if event.type == EventType.MODEL_CALL:
                    tier = by_model.get(str(payload.get("model_id")))
                else:
                    job = JOB_FOR_LEVEL.get(str(payload.get("level")))
                    tier = run.routing_config.get(job) if job is not None else None
                payload["tier"] = tier
                payload["tier_source"] = INFERRED if tier is not None else None
                dumped["payload"] = payload
            served.append(dumped)
        return served

    def records_of(self, run_id: str) -> RunRecords:
        return RunRecords(
            findings=self.runs.findings(run_id),
            chains=self.runs.chains(run_id),
            lopa_records=self.runs.lopa_records(run_id),
            recommendations=self.runs.recommendations(run_id),
            questions=self.runs.questions(run_id),
            sections=self.runs.sections(run_id),
            overrides=self.runs.overrides(run_id),
            evidence=self.runs.evidence(run_id),
        )

    def questions_seen(self, run_id: str) -> list[Question]:
        """The questions as seen: an engineer's question answered by override is checked."""
        overrides = self.runs.overrides(run_id)
        return [effective_question(q, overrides) for q in self.runs.questions(run_id)]

    def view(self, run_id: str) -> RunView:
        run = self.get(run_id)
        return RunView(
            run_id=run.id,
            # G8: the run's own lopa_top_n
            top_n=int(run.caps.get("lopa_top_n", self.config.caps.run.lopa_top_n)),
            pre_r50=is_pre_r50(run),
            records=self.records_of(run_id),
            hypotheses=self.runs.hypotheses(run_id),
            model_calls=self.runs.model_calls(run_id),
            prefer_own_section=lead_prefers_own_section(run.caps, self.runs.events(run_id)),
        )

    def shortlist(self, run_id: str) -> list[api.ShortlistItem]:
        run = self.get(run_id)
        return shortlist_items(self.view(run_id), self.plant_of(run), self.ref, self.config.caps)

    def worksheet(self, run_id: str) -> list[api.WorksheetRow]:
        run = self.get(run_id)
        return worksheet_rows(self.view(run_id), self.plant_of(run), self.ref, self.config.caps)

    def add_override(self, run_id: str, request: api.OverrideRequest, at: datetime) -> Override:
        """Check and store an override (raises OverrideRefused, 404 or 422)."""
        run = self.get(run_id)
        override = new_override(
            run.id,
            request.target_id,
            OverrideAction(request.action),
            request.new_value,
            request.reason,
            request.by,
            at,
            self.records_of(run_id),
            self.plant_of(run),
            self.ref,
        )
        with self.runs.step(run_id) as writer:
            writer.add_override(override)
        return override

    def dump(self, run_id: str) -> api.RunDump:
        """Every record of the run as stored (overrides alongside, not applied)."""
        run = self.get(run_id)
        return api.RunDump(
            run=run,
            sections=self.runs.sections(run_id),
            questions=self.runs.questions(run_id),
            findings=self.runs.findings(run_id),
            hypotheses=self.runs.hypotheses(run_id),
            chains=self.runs.chains(run_id),
            lopa_records=self.runs.lopa_records(run_id),
            recommendations=self.runs.recommendations(run_id),
            evidence=self.runs.evidence(run_id),
            overrides=self.runs.overrides(run_id),
            # dicts, validated into the typed events (contract v1.9)
            events=self.events(run_id),  # type: ignore[arg-type]
            # contract v1.7: what re-runs from `chains` replaced, marked as superseded
            superseded=[
                api.SupersededRecord(
                    kind=s.kind,  # type: ignore[arg-type]  # one of SUPERSEDED_TABLES' kinds
                    pass_seq=s.pass_seq,
                    superseded_seq=s.superseded_seq,
                    record=s.record,
                )
                for s in self.runs.superseded(run_id)
            ],
            label=run.label,
        )

    def counts(self, run_id: str) -> api.RunCounts:
        sections = self.runs.sections(run_id)
        questions = self.questions_seen(run_id)
        findings = self.runs.findings(run_id)
        lines, failed = coverage(sections, questions, findings)
        # the `sections` line counts sections, not questions
        per_kind = [line for line in lines if line.list != SECTIONS]
        done = (QuestionStatus.ANSWERED, QuestionStatus.NOT_CREDIBLE)
        return api.RunCounts(
            questions_total=len(questions),
            questions_open=sum(1 for q in questions if q.status == QuestionStatus.OPEN),
            questions_checked=sum(1 for q in questions if q.status in done),
            questions_failed=len(failed),
            questions_unsure=sum(line.unsure for line in per_kind),
            findings=len(findings),
            chains=len(self.runs.chains(run_id)),
        )

    def coverage(self, run_id: str) -> tuple[list[api.CoverageList], list[str]]:
        return coverage(
            self.runs.sections(run_id), self.questions_seen(run_id), self.runs.findings(run_id)
        )

    def add_question(self, run_id: str, section_id: str, text: str) -> Question:
        """An engineer's question, open; the same text on the same section is one question."""
        run = self.get(run_id)
        if section_id not in {s.id for s in self.runs.sections(run_id)}:
            raise RunNotFound(f"no section {section_id} in run {run_id}")
        question_id = ids.engineer_question_id(section_id, text)
        existing = next((q for q in self.runs.questions(run_id) if q.id == question_id), None)
        if existing is not None:
            return existing
        question = Question(
            id=question_id,
            run_id=run.id,
            kind=QuestionKind.ENGINEER,
            origin=QuestionOrigin.ENGINEER,
            status=QuestionStatus.OPEN,
            section_id=section_id,
            text=text,
        )
        with self.runs.step(run_id) as writer:
            writer.put_question(question)
        return question

    def record(self, run_id: str, record_id: str) -> tuple[Record, list[Any], list[Any]]:
        """A record with its parents and the model and tool calls that made it."""
        self.get(run_id)
        calls = {c.id: c for c in self.runs.model_calls(run_id)}
        found: Record | None = None
        for finding in self.runs.findings(run_id):
            if finding.id == record_id:
                made = [finding.model_call_id] if finding.model_call_id else []
                found = Record(
                    "finding", finding.model_dump(mode="json"), [finding.question_id], made
                )
        for hypothesis in self.runs.hypotheses(run_id):
            if hypothesis.id == record_id:
                made = [hypothesis.model_call_id] if hypothesis.model_call_id else []
                found = Record("hypothesis", hypothesis.model_dump(mode="json"), made, made)
        for question in self.runs.questions(run_id):
            if question.id == record_id:
                parents = [question.section_id] if question.section_id else []
                found = Record("question", question.model_dump(mode="json"), parents, [])
        for section in self.runs.sections(run_id):
            if section.id == record_id:
                found = Record("section", section.model_dump(mode="json"), [], [])
        # G5: chains, LOPA records, recommendations and overrides, with what they came from
        for chain in self.runs.chains(run_id):
            if chain.id == record_id:
                made = [chain.model_call_id] if chain.model_call_id else []
                found = Record("chain", chain.model_dump(mode="json"), list(chain.links), made)
        for lopa in self.runs.lopa_records(run_id):
            if lopa.id == record_id:
                made = [lopa.model_call_id] if lopa.model_call_id else []
                found = Record("lopa", lopa.model_dump(mode="json"), [lopa.target_id], made)
        for rec in self.runs.recommendations(run_id):
            if rec.id == record_id:
                made = [rec.model_call_id] if rec.model_call_id else []
                found = Record("recommendation", rec.model_dump(mode="json"), [rec.target_id], made)
        for override in self.runs.overrides(run_id):
            if override.id == record_id:
                dumped = override.model_dump(mode="json")
                found = Record("override", dumped, [override.target_id], [])
        # Phase 4: evidence with its target and tool call, and the evidence agent's steps
        for evidence in self.runs.evidence(run_id):
            if evidence.id == record_id:
                parents = [evidence.target_id]
                if evidence.tool_call_id:
                    parents.append(evidence.tool_call_id)
                made = [evidence.model_call_id] if evidence.model_call_id else []
                found = Record("evidence", evidence.model_dump(mode="json"), parents, made)
        for step in self.runs.steps(run_id):
            if step.id == record_id:
                made = [step.model_call_id] if step.model_call_id else []
                found = Record("agent_step", step.model_dump(mode="json"), [step.previous_id], made)
        if record_id in calls:
            found = Record("model_call", calls[record_id].model_dump(mode="json"), [], [record_id])
        if found is None:
            raise RunNotFound(f"no record {record_id} in run {run_id}")
        model_calls = [calls[i] for i in found.model_call_ids if i in calls]
        # an agent step's own tool calls; else a parent step's, or a tool call named as a parent
        steps = {record_id} if found.kind == "agent_step" else set(found.parent_ids)
        tool_calls = [
            t
            for t in self.runs.tool_calls(run_id)
            if t.agent_step_id in steps or t.id in found.parent_ids
        ]
        return found, model_calls, tool_calls
