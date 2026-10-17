"""Live runs behind the run endpoints (spec 2.8; plan PR 10). Every number comes from the run
store; nothing here calls a model except through the gateway the steppers are given."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from guideword.api import models as api
from guideword.config import Config
from guideword.gateway.client import Gateway
from guideword.questions.coverage import SECTIONS, coverage
from guideword.reference import ReferenceSet
from guideword.runs.case import start_case, steppers_for
from guideword.runs.estimate import run_upper_bound
from guideword.runs.machine import Stepper, advance
from guideword.runs.plants import PlantRepository
from guideword.runs.store import Clock, RunRepository
from guideword.schema import ids
from guideword.schema.enums import QuestionKind, QuestionOrigin, QuestionStatus, RunStatus
from guideword.schema.records import Question, Run

GatewayFactory = Callable[[sessionmaker[Session]], Gateway]


class RunNotFound(LookupError):
    pass


class RunEnded(ValueError):
    pass


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
    ) -> None:
        self.sessions = sessions
        self.config = config
        self.ref = ref
        self.plants = PlantRepository(sessions)
        self.runs = RunRepository(sessions, clock)
        self._factory = gateway_factory
        self._gateway: Gateway | None = None

    def gateway(self) -> Gateway:
        if self._gateway is None:
            self._gateway = self._factory(self.sessions)
        return self._gateway

    def get(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise RunNotFound(f"no run {run_id}")
        return run

    def _steppers(self, run: Run) -> dict[str, Stepper]:
        stored = self.plants.get(run.plant_record_id)
        if stored is None:
            raise RunNotFound(f"no plant {run.plant_record_id} for run {run.id}")
        return steppers_for(self.gateway(), self.config, self.ref, stored.record.plant_file)

    # --- start, cancel, advance -------------------------------------------------------------

    def start(self, plant_record_id: str, spend_cap_usd: float, mode: str) -> tuple[Run, float]:
        """Start (or resume) the run; its upper-bound cost (R20). Raises PlantNotFound,
        SectionsNotConfirmed, ModeNotBuilt (R21) or CapReachedError."""
        run = start_case(
            self.plants, self.runs, self.ref, self.config, plant_record_id, spend_cap_usd, mode
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
            gateway=self.gateway(),
        )
        return run, estimate

    def cancel(self, run_id: str) -> Run:
        run = self.get(run_id)
        if run.status in ids.ENDED_RUN_STATUSES:
            raise RunEnded(f"run {run_id} has already ended ({run.status.value})")
        with self.runs.step(run_id) as writer:
            writer.set_status(RunStatus.CANCELLED)
        return self.get(run_id)

    def advance_once(self, run_id: str) -> RunStatus:
        run = self.get(run_id)
        return advance(self.runs, run_id, self._steppers(run))

    def drive(self, run_id: str) -> RunStatus:
        """Advance until the run is no longer running (the in-process loop, laptop)."""
        status = self.get(run_id).status
        while status == RunStatus.RUNNING:
            status = self.advance_once(run_id)
        return status

    # --- reads --------------------------------------------------------------------------------

    def counts(self, run_id: str) -> api.RunCounts:
        sections = self.runs.sections(run_id)
        questions = self.runs.questions(run_id)
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
            chains=0,
        )

    def coverage(self, run_id: str) -> tuple[list[api.CoverageList], list[str]]:
        return coverage(
            self.runs.sections(run_id), self.runs.questions(run_id), self.runs.findings(run_id)
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
        if record_id in calls:
            found = Record("model_call", calls[record_id].model_dump(mode="json"), [], [record_id])
        if found is None:
            raise RunNotFound(f"no record {record_id} in run {run_id}")
        model_calls = [calls[i] for i in found.model_call_ids if i in calls]
        tool_calls = [
            t for t in self.runs.tool_calls(run_id) if t.agent_step_id in set(found.parent_ids)
        ]
        return found, model_calls, tool_calls
