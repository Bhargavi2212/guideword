"""The run store's tables (PROJECT.md §11 "Storage schema").

Links are foreign keys; large payloads are JSON columns holding the validated record.
Tables are created with `metadata.create_all`; there is no migration tool.
"""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class PlantRow(Base):
    __tablename__ = "plants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    plant_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
    # the plant file exactly as uploaded; the record ID is its hash
    plant_file: Mapped[dict[str, Any]] = mapped_column(JSON)
    confirmed_section_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class PlantFactRow(Base):
    __tablename__ = "plant_facts"

    plant_record_id: Mapped[str] = mapped_column(ForeignKey("plants.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String)


class SectionRow(Base):
    __tablename__ = "sections"

    plant_record_id: Mapped[str] = mapped_column(ForeignKey("plants.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # the order the set was stored in, so it reads back identical
    position: Mapped[int] = mapped_column(Integer)
    # the Section record
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # the run ID without its attempt suffix: every attempt with the same inputs shares it
    base_id: Mapped[str] = mapped_column(String, index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    plant_record_id: Mapped[str] = mapped_column(ForeignKey("plants.id"), index=True)
    status: Mapped[str] = mapped_column(String)
    # the Run record
    record: Mapped[dict[str, Any]] = mapped_column(JSON)
    # the full Section records of the snapshot, frozen when the run started
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class RunRecordRow(Base):
    """A record belonging to a run, keyed by (run ID, record ID)."""

    __abstract__ = True

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # the order records were written in, so they read back in that order
    position: Mapped[int] = mapped_column(Integer)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


class QuestionRow(RunRecordRow):
    __tablename__ = "questions"


class FindingRow(RunRecordRow):
    __tablename__ = "findings"


class HypothesisRow(RunRecordRow):
    """The whole-plant pass's hypotheses (R50); written once, never updated."""

    __tablename__ = "hypotheses"


class AgentStepRow(RunRecordRow):
    __tablename__ = "agent_steps"


class ModelCallRow(RunRecordRow):
    __tablename__ = "model_calls"


class ToolCallRow(RunRecordRow):
    __tablename__ = "tool_calls"


# Phase 3 fills these; they exist now so no migration step is needed then.
class ChainRow(RunRecordRow):
    __tablename__ = "chains"


class LopaRecordRow(RunRecordRow):
    __tablename__ = "lopa_records"


class RecommendationRow(RunRecordRow):
    __tablename__ = "recommendations"


class EvidenceRow(RunRecordRow):
    __tablename__ = "evidence"


class OverrideRow(RunRecordRow):
    __tablename__ = "overrides"


class SupersededRow(Base):
    """A post-analysis record a re-run from `chains` replaced (connector/v2 plan, Q1): copied
    here verbatim with the pass it belonged to (the `seq` of that pass's `run_extended` event)
    and the pass that replaced it. Never changed or removed."""

    __tablename__ = "superseded_records"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    pass_seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    superseded_seq: Mapped[int] = mapped_column(Integer)
    # the record's place in its live table, so the superseded list reads back in order
    position: Mapped[int] = mapped_column(Integer)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventRow(Base):
    """Append-only; an event is identified by (run ID, seq)."""

    __tablename__ = "events"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


class ResponseCacheRow(Base):
    """One model response per cache key (decision R15); the gateway reads and writes it."""

    __tablename__ = "response_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    response: Mapped[dict[str, Any]] = mapped_column(JSON)


class SpendLedgerRow(Base):
    """The hosted ledger (PROJECT.md §11); keyed by the hash of the entry."""

    __tablename__ = "spend_ledger"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    environment: Mapped[str] = mapped_column(String, index=True)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """An engine for `database_url` with the tables created, and its session factory."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
