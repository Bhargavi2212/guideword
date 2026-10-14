"""The run store's tables (PROJECT.md §11 "Storage schema"); Phase 1 creates only these three.

Links are foreign keys; large payloads are JSON columns. Later phases add their tables.
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


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    """An engine for `database_url` with the tables created, and its session factory."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
