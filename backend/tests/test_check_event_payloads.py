"""scripts/check_event_payloads.py (Phase 5 plan Q7, J7): every stored event parses."""

import json
import sqlite3
from pathlib import Path

import check_event_payloads
import pytest

from guideword.runs.db import make_session_factory

RUN = "run:aaaaaaaaaaaaaaaa"
T = "2026-10-13T10:00:00Z"


def _store(path: Path, events: list[dict[str, object]]) -> Path:
    make_session_factory(f"sqlite:///{path.as_posix()}")
    with sqlite3.connect(path) as db:
        for seq, event in enumerate(events, start=1):
            record = {"run_id": RUN, "seq": seq, "time": T, **event}
            db.execute(
                "insert into events (run_id, seq, type, record) values (?, ?, ?, ?)",
                (RUN, seq, event["type"], json.dumps(record)),
            )
    return path


def test_every_shape_is_reported_and_a_bad_one_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store(
        tmp_path / "s.db",
        [
            {"type": "step_started", "payload": {"step": "analysis"}},
            {"type": "step_started", "payload": {"step": "severity"}},
            # a legacy model_call without its model ID: no legacy model accepts it
            {"type": "model_call", "payload": {"model_call_id": "mc:x", "job": "j"}},
        ],
    )
    report = check_event_payloads.check(store)
    assert [(r.type, r.count, r.ok) for r in report] == [
        ("model_call", 1, False),
        ("step_started", 1, True),
        ("step_started", 1, True),
    ]
    failed = next(r for r in report if not r.ok)
    assert failed.source_run_id == RUN and "model_id" in (failed.error or "")
    assert check_event_payloads.main(["--store", str(store)]) == 1
    out = capsys.readouterr().out
    assert "3 shapes" in out and "1 failed" in out


def test_a_store_whose_events_all_parse_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = _store(tmp_path / "s.db", [{"type": "step_started", "payload": {"step": "x"}}])
    assert check_event_payloads.main(["--store", str(store)]) == 0
    assert "1 shapes, 1 events, 0 failed" in capsys.readouterr().out


def test_the_store_is_opened_read_only(tmp_path: Path) -> None:
    store = _store(tmp_path / "s.db", [{"type": "step_started", "payload": {"step": "x"}}])
    with check_event_payloads.read_only(store) as db, pytest.raises(sqlite3.OperationalError):
        db.execute("create table x (a)")
