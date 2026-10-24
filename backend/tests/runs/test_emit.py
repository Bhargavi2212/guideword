"""The event writer (contract v1.9, Q1): the one place that stamps and checks a payload."""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from guideword.reference import ReferenceSet
from guideword.runs import store
from guideword.runs.plants import PlantRepository
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, EventType
from guideword.schema.events import SCHEMA_V1_9

PACKAGE = Path(__file__).resolve().parents[2] / "guideword"
Upload = Callable[..., str]


@pytest.fixture
def run_id(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> str:
    run = start_run(
        plants,
        runs,
        ref,
        settings,
        plant_record_id=upload(),
        spend_cap_usd=1.0,
        mode="full",
        use=BudgetUse.DEVELOPMENT,
        post_spend_cap_usd=0.0,
    )
    return run.id


def _emit(runs: RunRepository, run_id: str, payload: dict[str, Any]) -> None:
    with runs.step(run_id) as writer:
        writer.emit(EventType.STEP_STARTED, payload)


def test_every_written_event_carries_the_v1_9_stamp(runs: RunRepository, run_id: str) -> None:
    _emit(runs, run_id, {"step": "analysis"})
    assert [e.payload_schema for e in runs.events(run_id)] == [SCHEMA_V1_9, SCHEMA_V1_9]


def test_in_tests_an_invalid_payload_raises(runs: RunRepository, run_id: str) -> None:
    with pytest.raises(ValidationError):
        _emit(runs, run_id, {"step": "analysis", "unknown": 1})
    assert [e.type for e in runs.events(run_id)] == [EventType.RUN_STARTED]


def test_in_a_live_run_an_invalid_payload_is_written_with_its_flag(
    runs: RunRepository, run_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bhargavi, 2026-10-23: a live run never raises on its own event; the event is written
    as given, flagged, with the error, and the run carries on."""
    monkeypatch.setattr(store, "STRICT_PAYLOADS", False)
    _emit(runs, run_id, {"step": "analysis", "unknown": 1})
    event = runs.events(run_id)[-1]
    assert event.payload == {"step": "analysis", "unknown": 1}
    assert event.payload_schema == SCHEMA_V1_9
    assert event.payload_invalid is True
    assert event.payload_error and "unknown" in event.payload_error


def test_no_call_site_sets_payload_schema() -> None:
    """Only the event writer passes `payload_schema=` (Q1)."""
    setters = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "payload_schema":
                setters.append(path.relative_to(PACKAGE).as_posix())
    assert setters == ["runs/store.py"]
