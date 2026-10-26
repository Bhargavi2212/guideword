"""Re-attaching a stored run's calculation cards under the approved rule (review plan R2, Q5).

Run on the WG run as it was recorded, before its re-attach: the committed export holds the
re-attached run (R5), and `_before_reattach` rebuilds the export as it was, exactly, from it. A
re-attach only appends records and moves the cards it supersedes to `superseded_records`, so
undoing it is mechanical; `test_the_rebuilt_export_is_the_one_recorded` checks the rebuilt
files against the export as committed before R5. Code only and $0: no model call, no search.
The cards the rule no longer gives are superseded, the ones it now gives are added, and one
`calculations_reattached` event, written last, names both.
"""

import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import export_recorded
import pytest
import reattach_calculations
from sqlalchemy.orm import Session, sessionmaker

from guideword.config import load_config
from guideword.evidence.reattach import STEP_REASON, ReattachRefused, reattach
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


# the last commit whose WG export is the run as recorded, before its re-attach
RECORDED_COMMIT = "0478505"
REATTACHED = "calculations_reattached"


def _table(folder: Path, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads((folder / f"{name}.json").read_text("utf-8"))["rows"]
    return rows


def _put(folder: Path, name: str, rows: list[dict[str, Any]]) -> None:
    text = json.dumps({"table": name, "rows": rows}, indent=1, ensure_ascii=False, default=str)
    (folder / f"{name}.json").write_text(text + "\n", encoding="utf-8", newline="\n")


def _before_reattach(out: Path) -> Path:
    """The WG export as recorded, rebuilt from the committed (re-attached) one."""
    shutil.copytree(WG_EXPORT, out)
    events = _table(out, "events")
    first = next(
        n
        for n, e in enumerate(events)
        if e["type"] == REATTACHED
        or (e["type"] == "agent_decision" and e["record"]["payload"].get("reason") == STEP_REASON)
    )
    [event] = [e for e in events if e["type"] == REATTACHED]
    payload, seq = event["record"]["payload"], event["seq"]
    steps = {
        e["record"]["payload"]["step_id"] for e in events[first:] if e["type"] == "agent_decision"
    }
    _put(out, "events", events[:first])
    _put(out, "agent_steps", [r for r in _table(out, "agent_steps") if r["id"] not in steps])
    _put(
        out,
        "tool_calls",
        [r for r in _table(out, "tool_calls") if r["record"]["agent_step_id"] not in steps],
    )
    superseded = _table(out, "superseded_records")
    back = [
        {k: r[k] for k in ("run_id", "id", "position", "record")}
        for r in superseded
        if r["superseded_seq"] == seq and r["kind"] == "evidence"
    ]
    kept = [r for r in _table(out, "evidence") if r["id"] not in payload["added_ids"]]
    # the export orders rows by primary key
    _put(out, "evidence", sorted([*kept, *back], key=lambda r: (r["run_id"], r["id"])))
    _put(out, "superseded_records", [r for r in superseded if r["superseded_seq"] != seq])
    runs = _table(out, "runs")
    label = runs[0]["record"]["label"]
    label["note"] = label["note"].split("; calculations re-attached")[0]
    _put(out, "runs", runs)
    return out


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _before_reattach(tmp_path_factory.mktemp("wg") / "williams_geismar")


@pytest.fixture
def store(recorded: Path) -> tuple[sessionmaker[Session], RunRepository]:
    sessions = load_recorded(recorded)
    return sessions, RunRepository(sessions, clock=lambda: NOW)


def test_the_rebuilt_export_is_the_one_recorded(recorded: Path) -> None:
    """Every file equals the WG export as committed before R5 re-exported it."""
    for path in sorted(recorded.glob("*.json")):
        relative = (WG_EXPORT / path.name).relative_to(ROOT).as_posix()
        committed = subprocess.run(
            ["git", "show", f"{RECORDED_COMMIT}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert path.read_bytes() == committed, path.name


def test_the_committed_export_is_the_re_attached_run() -> None:
    """R5: the site serves the run after its re-attach, which a second pass leaves alone."""
    sessions = load_recorded(WG_EXPORT)
    runs = RunRepository(sessions, clock=lambda: NOW)
    assert runs.events(WG_RUN)[-1].type == EventType.CALCULATIONS_REATTACHED
    assert _run((sessions, runs)) == []


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
