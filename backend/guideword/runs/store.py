"""The run store: runs and every record they produce, plus the append-only event log.

Every write of a step goes through one `StepWriter`, which is one transaction: a step either
saves all its records and events or none of them, so a crashed run resumes from its last
saved step (spec 2.1). Records are stored as validated JSON and read back unchanged.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from guideword.runs.db import (
    AgentStepRow,
    EventRow,
    FindingRow,
    ModelCallRow,
    QuestionRow,
    RunRecordRow,
    RunRow,
    ToolCallRow,
)
from guideword.schema import ids
from guideword.schema.enums import EventType, RunStatus
from guideword.schema.records import (
    AgentStep,
    Event,
    Finding,
    ModelCall,
    Question,
    Run,
    Section,
    ToolCall,
)

Clock = Callable[[], datetime]

# The event types this store emits. Phase 3 and 4 add chain_added, lopa_done and
# evidence_added with their tools (decision R32).
EMITTED_EVENT_TYPES = frozenset(
    {
        EventType.RUN_STARTED,
        EventType.STEP_STARTED,
        EventType.STEP_FINISHED,
        EventType.AGENT_DECISION,
        EventType.DISPATCH,
        EventType.MODEL_CALL,
        EventType.TOOL_CALL,
        EventType.FINDING_ADDED,
        EventType.COVERAGE_UPDATED,
        EventType.CAP_HIT,
        EventType.RUN_FINISHED,
        EventType.RUN_FAILED,
    }
)


def base_run_id(run_id: str) -> str:
    """`run:<h>` for `run:<h>` and `run:<h>:<n>`."""
    return ":".join(run_id.split(":")[:2])


class StepWriter:
    """The writes of one step, in one transaction. Events get the next `seq` of the run.

    Nothing is written to the database until the step commits (autoflush is off, new rows
    wait in the session), so a step holds no write lock while it makes model calls and the
    cache can commit each response on its own. The read helpers include the pending writes.
    """

    def __init__(self, session: Session, run_row: RunRow, clock: Clock) -> None:
        session.autoflush = False
        self._session = session
        self._row = run_row
        self._clock = clock
        self.run = Run.model_validate(run_row.record)
        latest = session.scalar(select(func.max(EventRow.seq)).where(EventRow.run_id == run_row.id))
        self._seq = int(latest or 0)
        # rows added in this step and not yet written, by table, in the order added
        self._new: dict[type[RunRecordRow], dict[str, RunRecordRow]] = {}
        self._stored_count: dict[type[RunRecordRow], int] = {}

    # --- the run ---------------------------------------------------------------------------

    def set_status(self, status: RunStatus) -> None:
        self._update(status=status)

    def set_step(self, step: str) -> None:
        self._update(step=step)

    def set_spend_cap(self, spend_cap_usd: float) -> None:
        self._update(spend_cap_usd=spend_cap_usd)

    def add_spent(self, usd: float, *, cap_usd: float) -> None:
        """`usd` is money actually paid; `cap_usd` is what counts against the cap: the paid
        cost plus cache hits at their stored cost (R45)."""
        self._update(
            spent_usd=self.run.spent_usd + usd, cap_spent_usd=self.run.cap_spent_usd + cap_usd
        )

    def _update(self, **changes: Any) -> None:
        self.run = self.run.model_copy(update=changes)
        self._row.status = self.run.status.value
        self._row.record = self.run.model_dump(mode="json")

    # --- events ----------------------------------------------------------------------------

    def emit(self, type: EventType, payload: dict[str, Any]) -> Event:
        if type not in EMITTED_EVENT_TYPES:
            raise ValueError(f"event type {type} is not emitted in this phase")
        self._seq += 1
        event = Event(
            run_id=self.run.id, seq=self._seq, type=type, payload=payload, time=self._clock()
        )
        self._session.add(
            EventRow(
                run_id=self.run.id,
                seq=event.seq,
                type=type.value,
                record=event.model_dump(mode="json"),
            )
        )
        return event

    # --- records (each with its event) -----------------------------------------------------

    def put_question(self, question: Question) -> None:
        """Add a question or store its new status; a question is never removed."""
        self._put(QuestionRow, question)

    def add_finding(self, finding: Finding) -> None:
        self._put(FindingRow, finding)
        self.emit(
            EventType.FINDING_ADDED,
            {"finding_id": finding.id, "question_id": finding.question_id, "tier": finding.tier},
        )

    def fill_severity(self, finding: Finding) -> None:
        """The one-time severity fill (R10): the stored finding gains its severity and reason.
        Its event is the severity call's `model_call` event, whose record lists the findings."""
        stored = {f.id: f for f in self.findings()}.get(finding.id)
        if stored is None:
            raise LookupError(f"no finding {finding.id} in this run")
        if stored.severity_class is not None:
            raise ValueError(f"{finding.id} already has a severity; it is never overwritten")
        self._put(FindingRow, finding)

    def add_step(self, step: AgentStep) -> None:
        self._put(AgentStepRow, step)
        self.emit(
            EventType.AGENT_DECISION,
            {"step_id": step.id, "agent": step.agent, "tool": step.tool, "reason": step.reason},
        )

    def add_model_call(self, call: ModelCall, *, fell_back_from: Sequence[str] = ()) -> None:
        """`fell_back_from` names the tiers skipped because they left the catalog."""
        self._put(ModelCallRow, call)
        payload: dict[str, Any] = {
            "model_call_id": call.id,
            "job": call.job,
            "model_id": call.model_id,
            "cache_hit": call.cache_hit,
            "outcome": call.outcome,
            "cost_usd": call.cost_usd,
            "cap_cost_usd": call.cap_cost_usd,
        }
        if fell_back_from:
            payload["fell_back_from"] = [str(t) for t in fell_back_from]
        self.emit(EventType.MODEL_CALL, payload)

    # --- reads within the step (stored rows plus this step's pending ones) ------------------

    def sections(self) -> list[Section]:
        """The run's own section snapshot (full records, frozen at start)."""
        return [Section.model_validate(s) for s in self._row.sections]

    def questions(self) -> list[Question]:
        return self._records(QuestionRow, Question)

    def findings(self) -> list[Finding]:
        return self._records(FindingRow, Finding)

    def steps(self) -> list[AgentStep]:
        return self._records(AgentStepRow, AgentStep)

    def tool_calls(self) -> list[ToolCall]:
        return self._records(ToolCallRow, ToolCall)

    def model_calls(self) -> list[ModelCall]:
        return self._records(ModelCallRow, ModelCall)

    def _records[R: BaseModel](self, table: type[RunRecordRow], model: type[R]) -> list[R]:
        stored = self._session.scalars(
            select(table).where(table.run_id == self.run.id).order_by(table.position)
        ).all()
        pending = list(self._new.get(table, {}).values())
        return [model.model_validate(r.record) for r in [*stored, *pending]]

    def _put(self, table: type[RunRecordRow], record: BaseModel) -> None:
        record_id: str = getattr(record, "id")  # noqa: B009
        dumped = record.model_dump(mode="json")
        new = self._new.setdefault(table, {})
        if record_id in new:
            new[record_id].record = dumped
            return
        row = self._session.get(table, (self.run.id, record_id))
        if row is not None:
            row.record = dumped
            return
        if table not in self._stored_count:
            self._stored_count[table] = int(
                self._session.scalar(
                    select(func.count()).select_from(table).where(table.run_id == self.run.id)
                )
                or 0
            )
        row = table(
            run_id=self.run.id,
            id=record_id,
            position=self._stored_count[table] + len(new),
            record=dumped,
        )
        new[record_id] = row
        self._session.add(row)

    def add_tool_call(self, call: ToolCall) -> None:
        self._put(ToolCallRow, call)
        self.emit(
            EventType.TOOL_CALL,
            {
                "tool_call_id": call.id,
                "tool": call.tool,
                "refused": call.refused_reason is not None,
            },
        )


class RunRepository:
    def __init__(self, sessions: sessionmaker[Session], clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    # --- writes ----------------------------------------------------------------------------

    def create(
        self,
        run: Run,
        sections: Sequence[Section],
        questions: Sequence[Question],
        started: dict[str, Any],
    ) -> None:
        """Store a new run with its section records and questions, and emit `run_started`."""
        with self._sessions.begin() as session:
            row = RunRow(
                id=run.id,
                base_id=base_run_id(run.id),
                attempt=run.attempt,
                plant_record_id=run.plant_record_id,
                status=run.status.value,
                record=run.model_dump(mode="json"),
                sections=[s.model_dump(mode="json") for s in sections],
            )
            session.add(row)
            session.flush()
            writer = StepWriter(session, row, self._clock)
            for question in questions:
                writer.put_question(question)
            writer.emit(EventType.RUN_STARTED, started)

    @contextmanager
    def step(self, run_id: str) -> Iterator[StepWriter]:
        """One transaction: everything written inside is saved together, or not at all."""
        with self._sessions.begin() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise LookupError(f"no run {run_id}")
            yield StepWriter(session, row, self._clock)

    # --- reads -----------------------------------------------------------------------------

    def get(self, run_id: str) -> Run | None:
        with self._sessions() as session:
            row = session.get(RunRow, run_id)
            return None if row is None else Run.model_validate(row.record)

    def records(self) -> list[Run]:
        with self._sessions() as session:
            rows = session.scalars(select(RunRow).order_by(RunRow.id)).all()
            return [Run.model_validate(r.record) for r in rows]

    def attempts(self, base_id: str) -> list[ids.Attempt]:
        """Earlier attempts with the same inputs, oldest first."""
        with self._sessions() as session:
            rows = session.scalars(
                select(RunRow).where(RunRow.base_id == base_id).order_by(RunRow.attempt)
            ).all()
            return [
                ids.Attempt(RunStatus(r.status), float(r.record["spend_cap_usd"])) for r in rows
            ]

    def sections(self, run_id: str) -> list[Section]:
        with self._sessions() as session:
            row = session.get(RunRow, run_id)
            return [] if row is None else [Section.model_validate(s) for s in row.sections]

    def questions(self, run_id: str) -> list[Question]:
        return self._read(QuestionRow, run_id, Question)

    def findings(self, run_id: str) -> list[Finding]:
        return self._read(FindingRow, run_id, Finding)

    def steps(self, run_id: str) -> list[AgentStep]:
        return self._read(AgentStepRow, run_id, AgentStep)

    def model_calls(self, run_id: str) -> list[ModelCall]:
        return self._read(ModelCallRow, run_id, ModelCall)

    def tool_calls(self, run_id: str) -> list[ToolCall]:
        return self._read(ToolCallRow, run_id, ToolCall)

    def events(self, run_id: str, after: int = 0) -> list[Event]:
        with self._sessions() as session:
            rows = session.scalars(
                select(EventRow)
                .where(EventRow.run_id == run_id, EventRow.seq > after)
                .order_by(EventRow.seq)
            ).all()
            return [Event.model_validate(r.record) for r in rows]

    def _read[R: BaseModel](
        self, table: type[RunRecordRow], run_id: str, model: type[R]
    ) -> list[R]:
        with self._sessions() as session:
            rows = session.scalars(
                select(table).where(table.run_id == run_id).order_by(table.position)
            ).all()
            return [model.model_validate(r.record) for r in rows]
