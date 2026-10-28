"""Recorded runs, loaded from their committed exports into one in-memory store (deploy plan
D1; several exports, review plan R0).

`cases/demo/recorded/<name>/` holds one JSON file per table, written by
`scripts/export_recorded.py`: every stored row of the run and its plant, and nothing else (no
response cache, no ledger). The deployed site reads the runs from this store; nothing writes it.
A row two exports share (by primary key) is loaded once; two exports that disagree on it are
refused.

The API reads on several worker threads at once, and one SQLite connection shared by them fails
("bad parameter or other API misuse"; F6, 2026-10-28). So the rows are loaded once into a source
connection, and each pooled connection is its own in-memory copy of it (SQLite's backup API),
used by one thread at a time.
"""

import json
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from guideword.runs.db import Base

# what an export never carries: other runs' cached responses, and the spend ledger
NOT_EXPORTED = frozenset({"response_cache", "spend_ledger"})
# copies kept for reuse, and the most made on top of them while requests overlap; a request
# beyond that waits for a free copy (each is about 25 MB for the site's three runs)
POOL_SIZE = 4
MAX_OVERFLOW = 12


def exported_tables() -> list[str]:
    """The tables an export writes, in the order their rows can be inserted."""
    return [t.name for t in Base.metadata.sorted_tables if t.name not in NOT_EXPORTED]


def load_recorded(directories: Path | Sequence[Path]) -> sessionmaker[Session]:
    """An in-memory store holding the exports' rows. Raises FileNotFoundError on a missing
    table file, and ValueError on a file that names another table or on two exports that
    disagree on a shared row."""
    dirs = [directories] if isinstance(directories, Path) else list(directories)
    loader = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(loader)
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    with loader.begin() as connection:
        for name in exported_tables():
            keys = [c.name for c in tables[name].primary_key.columns]
            rows: dict[tuple[Any, ...], dict[str, Any]] = {}
            for directory in dirs:
                data: dict[str, Any] = json.loads(
                    (directory / f"{name}.json").read_text(encoding="utf-8")
                )
                if data.get("table") != name:
                    raise ValueError(f"{name}.json holds table {data.get('table')}")
                for row in data["rows"]:
                    key = tuple(row[k] for k in keys)
                    if key in rows and rows[key] != row:
                        raise ValueError(f"{name}: the exports disagree on the row {key}")
                    rows[key] = row
            if rows:
                connection.execute(tables[name].insert(), list(rows.values()))
    # held for the store's life: the source every copy is made from
    held = loader.raw_connection()
    if not isinstance(held.driver_connection, sqlite3.Connection):
        raise TypeError("the recorded store is not a sqlite3 connection")
    copying = threading.Lock()

    def copy() -> sqlite3.Connection:
        source = held.driver_connection
        assert isinstance(source, sqlite3.Connection)
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        with copying:
            source.backup(connection)
        return connection

    engine = create_engine(
        "sqlite://",
        creator=copy,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
    )
    return sessionmaker(engine, expire_on_commit=False)
