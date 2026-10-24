"""The legacy event fixtures (Phase 5 plan Q3, Q7, H2): real events stored before contract
v1.9, picked by `scripts/export_legacy_events.py`, and the stamp that alone chooses a model."""

import json
from pathlib import Path
from typing import Any

import export_legacy_events
import pytest
from pydantic import TypeAdapter

from guideword.schema.events import ApiEvent

FIXTURES = Path(__file__).resolve().parents[3] / "contract" / "fixtures"
LEGACY = FIXTURES / "legacy"
ADAPTER: TypeAdapter[Any] = TypeAdapter(ApiEvent)


def _load(name: str) -> Any:
    return json.loads((LEGACY / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", list(export_legacy_events.ERAS))
def test_each_era_file_names_its_source_and_holds_each_type_of_that_run(name: str) -> None:
    data = _load(name)
    phase, run_id = export_legacy_events.ERAS[name]
    assert (data["source_run_id"], data["phase"]) == (run_id, phase)
    events = data["events"]
    assert {e["type"] for e in events} == set(data["types"])
    assert all(e["run_id"] == run_id for e in events)
    shapes = [export_legacy_events.shape(e) for e in events]
    assert len(shapes) == len(set(shapes)), "one event per shape"


def test_the_other_shapes_name_their_own_source_runs() -> None:
    entries = _load(export_legacy_events.OTHER)["events"]
    assert entries
    for entry in entries:
        assert entry["event"]["run_id"] == entry["source_run_id"]


def _all_legacy() -> list[dict[str, Any]]:
    events = [e for name in export_legacy_events.ERAS for e in _load(name)["events"]]
    return events + [x["event"] for x in _load(export_legacy_events.OTHER)["events"]]


def test_every_legacy_event_parses_with_its_types_legacy_model() -> None:
    for event in _all_legacy():
        assert "payload_schema" not in event
        parsed = ADAPTER.validate_python(event)
        assert type(parsed).__name__.endswith("EventLegacy"), (event["type"], event["seq"])


def test_the_stamp_alone_chooses_the_model() -> None:
    """The same event types, stamped v1.9 by the generator, parse with the v1.9 models; a
    legacy payload stamped v1.9 is held to the v1.9 model, never to its legacy one."""
    generated = json.loads((FIXTURES / "events_page.json").read_text(encoding="utf-8"))
    for event in generated["events"]:
        assert type(ADAPTER.validate_python(event)).__name__.endswith("EventV19")
    cap_hits = [e for e in _all_legacy() if e["type"] == "cap_hit" and "cap" not in e["payload"]]
    assert cap_hits
    stamped = cap_hits[0] | {"payload_schema": "v1.9"}
    with pytest.raises(ValueError, match="cap"):
        ADAPTER.validate_python(stamped)
