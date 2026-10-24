"""scripts/copy_store.py (Phase 5 plan G8, G9, H15): the record is copied, never written."""

import hashlib
import sqlite3
from pathlib import Path

import copy_store
import pytest

from guideword.runs.db import make_session_factory


def _store(path: Path) -> Path:
    """A run store with every table, and a row in two of them."""
    make_session_factory(f"sqlite:///{path.as_posix()}")
    with sqlite3.connect(path) as db:
        db.execute(
            "insert into runs (id, base_id, attempt, plant_record_id, status, record, sections)"
            " values (?, ?, ?, ?, ?, ?, ?)",
            (
                "run:aaaaaaaaaaaaaaaa",
                "run:aaaaaaaaaaaaaaaa",
                1,
                "plant:p:bbbbbbbbbbbbbbbb",
                "finished",
                '{"id": "run:aaaaaaaaaaaaaaaa"}',
                "[]",
            ),
        )
        db.execute(
            "insert into events (run_id, seq, type, record) values (?, ?, ?, ?)",
            ("run:aaaaaaaaaaaaaaaa", 1, "run_started", '{"seq": 1}'),
        )
    return path


def _tables(path: Path) -> dict[str, list[tuple[object, ...]]]:
    with sqlite3.connect(path) as db:
        names = [
            r[0]
            for r in db.execute("select name from sqlite_master where type = 'table' order by name")
        ]
        return {n: sorted(db.execute(f'select * from "{n}"').fetchall(), key=repr) for n in names}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_copy_store_copies_every_table(tmp_path: Path) -> None:
    source = _store(tmp_path / "guideword.db")
    target = tmp_path / "guideword-demo.db"
    copy_store.copy_store(source, target)
    copied = _tables(target)
    assert copied == _tables(source)
    assert {"runs", "events", "overrides", "spend_ledger"} <= set(copied)
    assert len(copied["runs"]) == 1


def test_copy_store_leaves_the_source_unchanged(tmp_path: Path) -> None:
    source = _store(tmp_path / "guideword.db")
    before, mtime = _hash(source), source.stat().st_mtime_ns
    copy_store.copy_store(source, tmp_path / "guideword-scratch.db")
    assert _hash(source) == before
    assert source.stat().st_mtime_ns == mtime


def test_copy_store_opens_the_source_read_only(tmp_path: Path) -> None:
    """The source connection refuses writes (SQLite `mode=ro`), so nothing can change it."""
    source = _store(tmp_path / "guideword.db")
    with copy_store.read_only(source) as db, pytest.raises(sqlite3.OperationalError):
        db.execute("create table x (a)")


def test_copy_store_refuses_to_overwrite(tmp_path: Path) -> None:
    source = _store(tmp_path / "guideword.db")
    target = tmp_path / "guideword-demo.db"
    target.write_bytes(b"an existing store")
    with pytest.raises(FileExistsError, match="guideword-demo.db"):
        copy_store.copy_store(source, target)
    assert target.read_bytes() == b"an existing store"


def test_copy_store_refuses_a_missing_source(tmp_path: Path) -> None:
    target = tmp_path / "guideword-demo.db"
    with pytest.raises(FileNotFoundError, match="guideword.db"):
        copy_store.copy_store(tmp_path / "guideword.db", target)
    assert not target.exists()


def test_copy_store_refuses_the_source_as_its_target(tmp_path: Path) -> None:
    source = _store(tmp_path / "guideword.db")
    before = _hash(source)
    with pytest.raises(FileExistsError):
        copy_store.copy_store(source, source)
    assert _hash(source) == before


def test_main_copies_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _store(tmp_path / "guideword.db")
    target = tmp_path / "guideword-demo.db"
    assert copy_store.main([str(source), str(target)]) == 0
    assert _tables(target) == _tables(source)
    assert "guideword-demo.db" in capsys.readouterr().out


def test_main_refuses_an_existing_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _store(tmp_path / "guideword.db")
    target = tmp_path / "guideword-demo.db"
    target.write_bytes(b"x")
    assert copy_store.main([str(source), str(target)]) == 1
    assert "already exists" in capsys.readouterr().err
