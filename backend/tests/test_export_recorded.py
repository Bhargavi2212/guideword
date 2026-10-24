"""The recorded run's export and loader (deploy plan D1): the site serves the run as stored,
labelled recorded, with no page text and no key; the store it came from never changes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import export_recorded
import make_fixtures
import pytest
from sqlalchemy.orm import Session, sessionmaker

from guideword.api.live import LiveRuns
from guideword.config import load_config
from guideword.gateway.client import Gateway
from guideword.reference import load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.recorded import load_recorded
from guideword.schema.enums import BudgetUse
from guideword.schema.records import SpendEntry

NOW = datetime(2026, 10, 24, tzinfo=UTC)


def no_gateway(sessions: sessionmaker[Session], use: BudgetUse) -> Gateway:
    raise AssertionError("a recorded run is only read")


def _live(sessions: sessionmaker[Session]) -> LiveRuns:
    return LiveRuns(
        sessions,
        config=load_config(global_budget_usd=25.0),
        ref=load_reference_set(),
        gateway_factory=no_gateway,
        clock=lambda: NOW,
    )


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, list[SpendEntry]]:
    """The fixture generator's $0 fake runs in a store, the main run's ID and its ledger."""
    work = tmp_path_factory.mktemp("recorded")
    generator = make_fixtures.Generator(work)
    try:
        served = generator.build()
    finally:
        generator.client.close()
    ledger = [
        SpendEntry.model_validate_json(line)
        for line in (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return work / "fixtures.db", served["run_detail.json"]["run"]["id"], ledger


@pytest.fixture(scope="module")
def exported(
    source: tuple[Path, str, list[SpendEntry]], tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, Any]:
    store, run_id, ledger = source
    out = tmp_path_factory.mktemp("export")
    report = export_recorded.export(store, run_id, out, ledger=ledger, secrets=[])
    return out, report


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_loaded_copy_serves_the_run_as_its_store_does(
    source: tuple[Path, str, list[SpendEntry]], exported: tuple[Path, Any]
) -> None:
    store, run_id, _ = source
    out, _ = exported
    stored = _live(make_session_factory(f"sqlite:///{store.as_posix()}"))
    loaded = _live(load_recorded(out))
    assert loaded.shortlist(run_id) == stored.shortlist(run_id)
    assert loaded.events(run_id) == stored.events(run_id)
    assert loaded.runs.findings(run_id) == stored.runs.findings(run_id)
    for item in stored.shortlist(run_id):
        assert loaded.record(run_id, item.target_id) == stored.record(run_id, item.target_id)


def test_the_copy_is_labelled_recorded_with_the_ledger_cost_and_a_note(
    source: tuple[Path, str, list[SpendEntry]], exported: tuple[Path, Any]
) -> None:
    store, run_id, ledger = source
    out, _ = exported
    run = _live(load_recorded(out)).get(run_id)
    paid = sum(e.cost_usd for e in ledger if e.kind == "model" and e.purpose.endswith(run_id))
    assert run.label.kind == "recorded"
    assert run.label.cost_usd == pytest.approx(paid)
    assert run.label.recorded_at is not None
    # the fake run's records match its ledger: no note (the WG run's do not, so it has one)
    assert run.label.note is None


def test_a_record_under_its_ledger_gets_the_spend_note() -> None:
    note = export_recorded.spend_note(stored_usd=0.8882, ledger_usd=0.8965)
    assert note == "record $0.0083 under ledger, run stored before the 2026-10-22 fix"
    assert export_recorded.spend_note(stored_usd=0.5, ledger_usd=0.5) is None


def test_the_source_store_is_unchanged(
    source: tuple[Path, str, list[SpendEntry]], tmp_path: Path
) -> None:
    store, run_id, ledger = source
    before = _hash(store)
    export_recorded.export(store, run_id, tmp_path, ledger=ledger, secrets=[])
    assert _hash(store) == before


def test_the_export_keeps_no_page_text(exported: tuple[Path, Any]) -> None:
    out, _ = exported
    assert not (out / "response_cache.json").exists()
    assert not (out / "spend_ledger.json").exists()
    calls = json.loads((out / "model_calls.json").read_text(encoding="utf-8"))["rows"]
    judges = [c for c in calls if c["record"]["job"] == "precedent_judge"]
    assert judges and all(c["record"]["reasoning_text"] is None for c in judges)


def test_the_export_keeps_an_engineer_override_with_its_reason(
    source: tuple[Path, str, list[SpendEntry]], exported: tuple[Path, Any]
) -> None:
    _, run_id, _ = source
    out, _ = exported
    overrides = _live(load_recorded(out)).runs.overrides(run_id)
    assert overrides and overrides[0].action == "change_severity" and overrides[0].reason


def test_the_export_refuses_a_configured_key(
    source: tuple[Path, str, list[SpendEntry]], tmp_path: Path
) -> None:
    store, run_id, ledger = source
    with pytest.raises(ValueError, match="key"):
        # "Mock" appears in the run's records; a key that matched would be refused the same way
        export_recorded.export(store, run_id, tmp_path, ledger=ledger, secrets=["Mock reviewer"])
    assert list(tmp_path.iterdir()) == []


def test_the_report_gives_the_size_and_the_load_time(exported: tuple[Path, Any]) -> None:
    out, report = exported
    assert report.bytes == sum(p.stat().st_size for p in out.glob("*.json"))
    assert report.load_seconds >= 0 and report.rows > 0
