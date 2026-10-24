"""A recorded run, loaded from its committed export into an in-memory store (deploy plan D1).

`cases/demo/recorded/<name>/` holds one JSON file per table, written by
`scripts/export_recorded.py`: every stored row of the run and its plant, and nothing else (no
response cache, no ledger). The deployed site reads the run from this store; nothing writes it.
"""

import json
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


def load_recorded(directory: Path) -> sessionmaker[Session]:
    """An in-memory store holding the export's rows. Raises FileNotFoundError on a missing
    table file and ValueError on a file that names another table."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    with engine.begin() as connection:
        for name in exported_tables():
            data: dict[str, Any] = json.loads(
                (directory / f"{name}.json").read_text(encoding="utf-8")
            )
            if data.get("table") != name:
                raise ValueError(f"{name}.json holds table {data.get('table')}")
            if data["rows"]:
                connection.execute(tables[name].insert(), data["rows"])
    return sessionmaker(engine, expire_on_commit=False)
