"""The precedent index, `reference/precedent_index.csv` (Phase 4 spec 4.2; plan PR 3, Q5).

Cowork builds it from CSB's public list of completed investigations, with a URL and a source on
every row; Claude Code never opens its rows (CLAUDE.md §5). It is loaded **outside** the
ReferenceSet, so it is not among a run's hashed reference versions (P4-9): its own version is
recorded on the evidence pass instead.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

from guideword.reference.loader import (
    DEFAULT_REFERENCE_DIR,
    ReferenceTableError,
    _read,
    _unique,
)
from guideword.reference.tables import Source, _Row, _split
from guideword.schema.ids import NO_PRECEDENT

PRECEDENT_INDEX = "precedent_index.csv"
PRECEDENT_HEADER = (
    "id",
    "title",
    "date",
    "country",
    "company",
    "location",
    "chemicals",
    "equipment_types",
    "mechanism_keywords",
    "summary",
    "url",
    "source",
)


def _text(value: object) -> object:
    return "" if value is None else value


def _words(value: object) -> object:
    return () if value is None else _split(value)


def _index_id(value: str) -> str:
    # the ID keys an evidence record (`ev:<target>:precedent:<id>`, plan G23)
    if value == NO_PRECEDENT or ":" in value:
        raise ValueError(f"{value!r} can't be a precedent ID")
    return value


def _https(value: str) -> str:
    if not value.startswith("https://"):
        raise ValueError(f"not an https URL: {value!r}")
    return value


Text = Annotated[str, BeforeValidator(_text)]
Words = Annotated[tuple[str, ...], BeforeValidator(_words)]


class PrecedentRow(_Row):
    id: Annotated[str, Field(min_length=1), AfterValidator(_index_id)]
    title: Annotated[str, Field(min_length=1)]
    date: Text = ""
    country: Text = ""
    company: Text = ""
    location: Text = ""
    chemicals: Words = ()
    equipment_types: Words = ()
    mechanism_keywords: Words = ()
    # empty on a title-only row (its source says so)
    summary: Text = ""
    url: Annotated[str, AfterValidator(_https)]
    source: Source


@dataclass(frozen=True)
class PrecedentIndex:
    rows: tuple[PrecedentRow, ...]
    # SHA-256 of the file bytes, recorded on the evidence pass event
    version: str


def load_precedent_index(directory: Path | None = None) -> PrecedentIndex:
    """Raises ReferenceTableError naming the file and the problem."""
    root = directory if directory is not None else DEFAULT_REFERENCE_DIR
    rows, version = _read(root, PRECEDENT_INDEX, PrecedentRow, PRECEDENT_HEADER)
    _unique(PRECEDENT_INDEX, [row.id for row in rows])
    return PrecedentIndex(rows, version)


__all__ = [
    "PRECEDENT_HEADER",
    "PRECEDENT_INDEX",
    "PrecedentIndex",
    "PrecedentRow",
    "ReferenceTableError",
    "load_precedent_index",
]
