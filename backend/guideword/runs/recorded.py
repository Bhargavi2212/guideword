"""Recorded runs, loaded from their committed exports into one in-memory store (deploy plan
D1; several exports, review plan R0).

`cases/demo/recorded/<name>/` holds one JSON file per table, written by
`scripts/export_recorded.py`: every stored row of the run and its plant, and nothing else (no
response cache, no ledger). The deployed site reads the runs from this store; nothing writes it.
A row two exports share (by primary key) is loaded once; two exports that disagree on it are
refused.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from guideword.runs.db import Base

# what an export never carries: other runs' cached responses, and the spend ledger
NOT_EXPORTED = frozenset({"response_cache", "spend_ledger"})


def exported_tables() -> list[str]:
    """The tables an export writes, in the order their rows can be inserted."""
    return [t.name for t in Base.metadata.sorted_tables if t.name not in NOT_EXPORTED]


def load_recorded(directories: Path | Sequence[Path]) -> sessionmaker[Session]:
    """An in-memory store holding the exports' rows. Raises FileNotFoundError on a missing
    table file, and ValueError on a file that names another table or on two exports that
    disagree on a shared row."""
    dirs = [directories] if isinstance(directories, Path) else list(directories)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    with engine.begin() as connection:
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
    return sessionmaker(engine, expire_on_commit=False)
