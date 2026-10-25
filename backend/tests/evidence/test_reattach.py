"""Re-attaching a stored run's calculation cards under the approved rule (review plan R2, Q5).

Run on the committed WG export, loaded into memory: its cards came from Phase 4's rule. Code only
and $0: no model call, no search. The cards the rule no longer gives are superseded, the ones it
now gives are added, and one `calculations_reattached` event, written last, names both.
"""

import json
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import export_recorded
import pytest
import reattach_calculations
from sqlalchemy.orm import Session, sessionmaker

from guideword.config import load_config
from guideword.evidence.reattach import ReattachRefused, reattach
from guideword.runs.plants import PlantRepository
from guideword.runs.recorded import load_recorded
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, EvidenceKind, RunStatus

ROOT = Path(__file__).resolve().parents[3]
WG_EXPORT = ROOT / "cases" / "demo" / "recorded" / "williams_geismar"
WG_RUN = json.loads((WG_EXPORT / "runs.json").read_text(encoding="utf-8"))["rows"][0]["id"]
NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
COMMIT = "76586aa"
BLOCKED = "calculation:blocked_in_heating-"


@pytest.fixture
def store() -> tuple[sessionmaker[Session], RunRepository]:
    sessions = load_recorded(WG_EXPORT)
    return sessions, RunRepository(sessions, clock=lambda: NOW)


def _run(store: tuple[sessionmaker[Session], RunRepository]) -> list[str]:
    sessions, runs = store
    run = runs.get(WG_RUN)
    assert run is not None
    plant = PlantRepository(sessions).get(run.plant_record_id)
    assert plant is not None
    done = reattach(
        runs,
        WG_RUN,
        plant.record.plant_file,
        load_config(global_budget_usd=25.0),
        commit=COMMIT,
        today=NOW.date(),
    )
    return [*done.superseded_ids, *done.added_ids]


def _blocked(runs: RunRepository) -> set[tuple[str, str]]:
    return {
        (e.target_id[:30], e.id.rsplit(BLOCKED, 1)[1])
        for e in runs.evidence(WG_RUN)
        if BLOCKED in e.id
    }


def test_the_wg_cards_follow_the_approved_table(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    before = _blocked(runs)
    _run(store)
    after = _blocked(runs)
    gone = {key for key in before - after}
    added = {key for key in after - before}
    # #1 the fire, #3 the EA-425A chain, #5 the EA-425A flow line lose theirs
    assert gone == {
        ("f:m:S-EA-425B:more:temperature", "EA-425B"),
        ("ch:HV-A-SIN.normal_position+HV", "EA-425B"),
        ("f:m:S-EA-425A:more:flow:super:", "EA-425A"),
    }
    # #2 gains EA-425A's "not blocked in"; #4 gains both reboilers
    assert added == {
        ("ch:EA-425B.design_pressure_kpa", "EA-425A"),
        ("f:proc:P-REB-START-2:early:sup", "EA-425A"),
        ("f:proc:P-REB-START-2:early:sup", "EA-425B"),
    }
    assert ("ch:EA-425B.design_pressure_kpa", "EA-425B") in after  # kept, unchanged


def test_it_makes_no_model_call_and_leaves_precedents_and_matrix_cards_alone(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    calls = runs.model_calls(WG_RUN)
    others = {e.id: e for e in runs.evidence(WG_RUN) if BLOCKED not in e.id}
    _run(store)
    assert runs.model_calls(WG_RUN) == calls
    assert {e.id: e for e in runs.evidence(WG_RUN) if BLOCKED not in e.id} == others
    run = runs.get(WG_RUN)
    assert run is not None and run.status == "finished"


def test_one_event_written_last_names_what_changed(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    changed = _run(store)
    events = runs.events(WG_RUN)
    last = events[-1]
    assert last.type == EventType.CALCULATIONS_REATTACHED
    assert last.payload["date"] == "2026-10-26" and last.payload["commit"] == COMMIT
    assert [*last.payload["superseded_ids"], *last.payload["added_ids"]] == changed
    assert sum(e.type == EventType.CALCULATIONS_REATTACHED for e in events) == 1


def test_the_superseded_cards_are_kept_verbatim_with_the_events_seq(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    old = {e.id: e for e in runs.evidence(WG_RUN)}
    _run(store)
    event = runs.events(WG_RUN)[-1]
    kept = [s for s in runs.superseded(WG_RUN) if s.superseded_seq == event.seq]
    assert sorted(s.record["id"] for s in kept) == sorted(event.payload["superseded_ids"])
    for s in kept:
        assert s.kind == "evidence" and s.pass_seq < s.superseded_seq
        assert s.record == old[s.record["id"]].model_dump(mode="json")


def test_each_added_card_names_its_tool_call_and_step(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    _run(store)
    added = runs.events(WG_RUN)[-1].payload["added_ids"]
    calls = {c.id: c for c in runs.tool_calls(WG_RUN)}
    steps = {s.id: s for s in runs.steps(WG_RUN)}
    for record in runs.evidence(WG_RUN):
        if record.id in added:
            assert record.kind == EvidenceKind.CALCULATION
            call = calls[record.tool_call_id]
            assert call.tool == "physics_calc" and record.id in call.record_ids
            assert steps[call.agent_step_id].agent == "evidence"


def test_a_second_run_changes_nothing(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    _, runs = store
    _run(store)
    events = len(runs.events(WG_RUN))
    assert _run(store) == []
    assert len(runs.events(WG_RUN)) == events


def test_afterwards_every_calculation_card_on_the_top_five_names_its_via(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    from guideword.api.live import LiveRuns
    from guideword.reference import load_reference_set

    def no_gateway(*_: object) -> None:
        raise AssertionError("a re-attached run is only read")

    sessions, runs = store
    _run(store)
    live = LiveRuns(
        sessions,
        config=load_config(global_budget_usd=25.0),
        ref=load_reference_set(),
        gateway_factory=no_gateway,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    cards = [e for item in live.shortlist(WG_RUN)[:5] for e in item.evidence]
    calcs = [e for e in cards if e.kind == EvidenceKind.CALCULATION]
    assert calcs and all(e.via_ids for e in calcs)


def test_the_export_notes_the_reattach_and_keeps_the_recording_time(
    store: tuple[sessionmaker[Session], RunRepository], tmp_path: Path
) -> None:
    sessions, runs = store
    recorded_at = runs.events(WG_RUN)[-1].time
    _run(store)
    db = tmp_path / "demo.db"
    with sessions() as session:
        raw = session.connection().connection.driver_connection
        assert isinstance(raw, sqlite3.Connection)
        target = sqlite3.connect(db)
        raw.backup(target)
        target.close()
    out = tmp_path / "out"
    export_recorded.export(db, WG_RUN, out, ledger=[], secrets=[])
    label = json.loads((out / "runs.json").read_text(encoding="utf-8"))["rows"][0]["record"][
        "label"
    ]
    assert label["note"].endswith(f"calculations re-attached 2026-10-26 ({COMMIT})")
    assert datetime.fromisoformat(label["recorded_at"]) == recorded_at


# --- the script ------------------------------------------------------------------------------


def test_the_script_refuses_the_source_store(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="guideword.db"):
        reattach_calculations.main(
            [WG_RUN, "--store", str(ROOT / "guideword.db"), "--commit", COMMIT]
        )


def test_the_script_needs_a_commit() -> None:
    with pytest.raises(SystemExit):
        reattach_calculations.main([WG_RUN, "--store", "x.db"])


def test_a_run_that_is_not_finished_is_refused(
    store: tuple[sessionmaker[Session], RunRepository],
) -> None:
    sessions, runs = store
    with runs.step(WG_RUN) as writer:
        writer.set_status(RunStatus.RUNNING)
    plant = PlantRepository(sessions).get(runs.get(WG_RUN).plant_record_id)  # type: ignore[union-attr]
    assert plant is not None
    with pytest.raises(ReattachRefused, match="finished"):
        reattach(
            runs,
            WG_RUN,
            plant.record.plant_file,
            load_config(global_budget_usd=25.0),
            commit=COMMIT,
            today=date(2026, 10, 26),
        )
    assert Counter(e.type for e in runs.events(WG_RUN))[EventType.CALCULATIONS_REATTACHED] == 0
