"""The run store: runs and every record they produce, plus the append-only event log.

Every write of a step goes through one `StepWriter`, which is one transaction: a step either
saves all its records and events or none of them, so a crashed run resumes from its last
saved step (spec 2.1). Records are stored as validated JSON and read back unchanged.
"""

from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from guideword.runs.db import (
    AgentStepRow,
    ChainRow,
    EventRow,
    EvidenceRow,
    FindingRow,
    HypothesisRow,
    LopaRecordRow,
    ModelCallRow,
    OverrideRow,
    QuestionRow,
    RecommendationRow,
    RunRecordRow,
    RunRow,
    SupersededRow,
    ToolCallRow,
)
from guideword.schema import ids
from guideword.schema.enums import EventType, RunStatus
from guideword.schema.records import (
    AgentStep,
    Chain,
    Event,
    Evidence,
    Finding,
    Hypothesis,
    LopaRecord,
    ModelCall,
    Override,
    Question,
    Recommendation,
    Run,
    Section,
    ToolCall,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Superseded:
    """One record a re-run from `chains` replaced (connector/v2 plan, Q1)."""

    kind: str
    pass_seq: int
    superseded_seq: int
    record: dict[str, Any]


# what a re-run from `chains` supersedes: kind -> live table (model calls: the post jobs only)
SUPERSEDED_TABLES: dict[str, type[RunRecordRow]] = {
    "chain": ChainRow,
    "lopa": LopaRecordRow,
    "recommendation": RecommendationRow,
    "model_call": ModelCallRow,
}

# The event types this store emits (decision R32). Phase 3 adds chain_added, lopa_done and
# run_extended with the post-analysis steps (plan G11); Phase 4 adds evidence_added.
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
        EventType.HYPOTHESIS_ADDED,
        EventType.HYPOTHESIS_DROPPED,
        EventType.CHAIN_ADDED,
        EventType.LOPA_DONE,
        EventType.RUN_EXTENDED,
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

    def set_post_spend_cap(self, post_spend_cap_usd: float) -> None:
        """P3-2: the post-analysis allowance; not hashed, so the run ID does not change."""
        self._update(post_spend_cap_usd=post_spend_cap_usd)

    def add_spent(self, usd: float, *, cap_usd: float) -> None:
        """`usd` is money actually paid; `cap_usd` is what counts against the cap: the paid
        cost plus cache hits at their stored cost (R45)."""
        self._update(
            spent_usd=self.run.spent_usd + usd, cap_spent_usd=self.run.cap_spent_usd + cap_usd
        )

    def add_post_spent(self, usd: float) -> None:
        """A post-analysis call: `usd` is money actually paid. It never counts against the
        analysis cap (Bhargavi, 2026-10-20); the post cap reads the post jobs' call records
        (Q19), and the phase cap and use allowance read the ledger."""
        self._update(spent_usd=self.run.spent_usd + usd)

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

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store a hypothesis of the whole-plant pass, once (R50: it is never edited)."""
        if hypothesis.id in self._new.get(HypothesisRow, {}) or (
            self._session.get(HypothesisRow, (self.run.id, hypothesis.id)) is not None
        ):
            raise ValueError(f"hypothesis {hypothesis.id} is already stored in run {self.run.id}")
        self._put(HypothesisRow, hypothesis)
        self.emit(
            EventType.HYPOTHESIS_ADDED,
            {"hypothesis_id": hypothesis.id, "rank": hypothesis.rank},
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

    def add_chain(self, chain: Chain) -> None:
        """Store a validated chain of the connector, once, with its event (plan G11)."""
        self._refuse_repeat(ChainRow, chain.id, "chain")
        self._put(ChainRow, chain)
        self.emit(EventType.CHAIN_ADDED, {"chain_id": chain.id, "links": len(chain.links)})

    def fill_chain_severity(self, chain: Chain) -> None:
        """The one-time chain severity fill, as `fill_severity` for findings (R10)."""
        stored = {c.id: c for c in self.chains()}.get(chain.id)
        if stored is None:
            raise LookupError(f"no chain {chain.id} in this run")
        if stored.severity_class is not None or stored.severity_reason is not None:
            raise ValueError(f"{chain.id} already has a severity; it is never overwritten")
        self._put(ChainRow, chain)

    def add_lopa(self, record: LopaRecord, *, full: bool) -> None:
        """Store a LOPA record, once; its event says whether Ultra argued the layers."""
        self._refuse_repeat(LopaRecordRow, record.id, "LOPA record")
        self._put(LopaRecordRow, record)
        self.emit(
            EventType.LOPA_DONE,
            {
                "lopa_id": record.id,
                "complete": record.complete,
                "kind": "full" if full else "code_only",
            },
        )

    def add_recommendation(self, recommendation: Recommendation) -> None:
        """Store a recommendation, once; its event is its call's `model_call` event."""
        self._refuse_repeat(RecommendationRow, recommendation.id, "recommendation")
        self._put(RecommendationRow, recommendation)

    def add_override(self, override: Override) -> None:
        """Store an engineer's override (spec 3.5); records are never edited, views apply it."""
        self._refuse_repeat(OverrideRow, override.id, "override")
        self._put(OverrideRow, override)

    def has_event(self, type: EventType) -> bool:
        """An event of this type was written by an earlier, committed step of the run."""
        found = self._session.scalar(
            select(func.count())
            .select_from(EventRow)
            .where(EventRow.run_id == self.run.id, EventRow.type == type.value)
        )
        return bool(found)

    def step_summaries(self, step: str) -> list[dict[str, Any]]:
        """The payloads of the committed `step_finished` events for `step` in the run's current
        post pass (after its latest `run_extended` event), in order: a re-run from `chains`
        starts its counts afresh."""
        since = self._session.scalar(
            select(func.max(EventRow.seq)).where(
                EventRow.run_id == self.run.id, EventRow.type == EventType.RUN_EXTENDED.value
            )
        )
        rows = self._session.scalars(
            select(EventRow)
            .where(
                EventRow.run_id == self.run.id,
                EventRow.type == EventType.STEP_FINISHED.value,
                EventRow.seq > int(since or 0),
            )
            .order_by(EventRow.seq)
        ).all()
        payloads = [Event.model_validate(r.record).payload for r in rows]
        return [p for p in payloads if p.get("step") == step]

    def supersede_post_records(
        self, pass_seq: int, superseded_seq: int, post_jobs: Collection[str]
    ) -> list[str]:
        """Copy every chain, LOPA record, recommendation and post-job model call into
        `superseded_records`, verbatim, then clear them from the live tables, in this one
        transaction (connector/v2 plan, Q1). Returns the superseded record IDs."""
        rows = self._post_rows(post_jobs)
        for kind, row in rows:
            self._session.add(
                SupersededRow(
                    run_id=self.run.id,
                    kind=kind,
                    id=row.id,
                    pass_seq=pass_seq,
                    superseded_seq=superseded_seq,
                    position=row.position,
                    record=dict(row.record),
                )
            )
        self._clear_post_records([row for _, row in rows])
        return [row.id for _, row in rows]

    def post_record_ids(self, post_jobs: Collection[str]) -> list[str]:
        """The IDs `supersede_post_records` would copy, in the same order."""
        return [row.id for _, row in self._post_rows(post_jobs)]

    def _post_rows(self, post_jobs: Collection[str]) -> list[tuple[str, RunRecordRow]]:
        out: list[tuple[str, RunRecordRow]] = []
        for kind, table in SUPERSEDED_TABLES.items():
            stored = self._session.scalars(
                select(table).where(table.run_id == self.run.id).order_by(table.position)
            ).all()
            for row in stored:
                if kind == "model_call" and row.record.get("job") not in post_jobs:
                    continue
                out.append((kind, row))
        return out

    def _clear_post_records(self, rows: Sequence[RunRecordRow]) -> None:
        for row in rows:
            self._session.delete(row)
        self._stored_count.clear()

    def superseded_model_calls(self) -> list[ModelCall]:
        """The model calls of superseded passes: their spend still counts (R45)."""
        rows = self._session.scalars(
            select(SupersededRow).where(
                SupersededRow.run_id == self.run.id, SupersededRow.kind == "model_call"
            )
        ).all()
        return [ModelCall.model_validate(r.record) for r in rows]

    def _refuse_repeat(self, table: type[RunRecordRow], record_id: str, kind: str) -> None:
        if record_id in self._new.get(table, {}) or (
            self._session.get(table, (self.run.id, record_id)) is not None
        ):
            raise ValueError(f"{kind} {record_id} is already stored in run {self.run.id}")

    def add_step(self, step: AgentStep) -> None:
        self._put(AgentStepRow, step)
        self.emit(
            EventType.AGENT_DECISION,
            {"step_id": step.id, "agent": step.agent, "tool": step.tool, "reason": step.reason},
        )

    def add_model_call(self, call: ModelCall, *, fell_back_from: Sequence[str] = ()) -> None:
        """`fell_back_from` names the tiers skipped because they left the catalog. A second
        record with the same ID in one run is refused: it would overwrite the first."""
        if call.id in self._new.get(ModelCallRow, {}) or (
            self._session.get(ModelCallRow, (self.run.id, call.id)) is not None
        ):
            raise ValueError(f"model call {call.id} is already recorded in run {self.run.id}")
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

    def hypotheses(self) -> list[Hypothesis]:
        return self._records(HypothesisRow, Hypothesis)

    def steps(self) -> list[AgentStep]:
        return self._records(AgentStepRow, AgentStep)

    def tool_calls(self) -> list[ToolCall]:
        return self._records(ToolCallRow, ToolCall)

    def model_calls(self) -> list[ModelCall]:
        return self._records(ModelCallRow, ModelCall)

    def chains(self) -> list[Chain]:
        return self._records(ChainRow, Chain)

    def lopa_records(self) -> list[LopaRecord]:
        return self._records(LopaRecordRow, LopaRecord)

    def recommendations(self) -> list[Recommendation]:
        return self._records(RecommendationRow, Recommendation)

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

    def hypotheses(self, run_id: str) -> list[Hypothesis]:
        return self._read(HypothesisRow, run_id, Hypothesis)

    def steps(self, run_id: str) -> list[AgentStep]:
        return self._read(AgentStepRow, run_id, AgentStep)

    def model_calls(self, run_id: str) -> list[ModelCall]:
        return self._read(ModelCallRow, run_id, ModelCall)

    def tool_calls(self, run_id: str) -> list[ToolCall]:
        return self._read(ToolCallRow, run_id, ToolCall)

    def chains(self, run_id: str) -> list[Chain]:
        return self._read(ChainRow, run_id, Chain)

    def lopa_records(self, run_id: str) -> list[LopaRecord]:
        return self._read(LopaRecordRow, run_id, LopaRecord)

    def recommendations(self, run_id: str) -> list[Recommendation]:
        return self._read(RecommendationRow, run_id, Recommendation)

    def overrides(self, run_id: str) -> list[Override]:
        return self._read(OverrideRow, run_id, Override)

    def superseded(self, run_id: str) -> list[Superseded]:
        """Every record re-runs replaced, oldest pass first, in each kind's table order."""
        order = list(SUPERSEDED_TABLES)
        with self._sessions() as session:
            rows = session.scalars(
                select(SupersededRow).where(SupersededRow.run_id == run_id)
            ).all()
            rows = sorted(rows, key=lambda r: (r.pass_seq, order.index(r.kind), r.position))
            return [Superseded(r.kind, r.pass_seq, r.superseded_seq, dict(r.record)) for r in rows]

    def evidence(self, run_id: str) -> list[Evidence]:
        return self._read(EvidenceRow, run_id, Evidence)

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
