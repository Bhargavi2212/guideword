"""Export the legacy event fixtures from the run store (Phase 5 plan Q3, Q7, H2). No calls.

  python scripts/export_legacy_events.py            # reads guideword.db, read-only
  python scripts/export_legacy_events.py --store other.db

Events stored before contract v1.9 carry no `payload_schema` stamp. The frontend must show
them (the WG replay), so a few are committed, picked by code: the first event of each shape
(type; the step, for step events; and the sorted payload keys) of one run per era, each run
whose ledger lines all fall in that phase:

- `legacy/events_phase2.json`: case D, `run:e4f544ce3e94a468`;
- `legacy/events_phase3.json`: the first WG run, `run:4e6842d31fbdee3b`;
- `legacy/events_phase4.json`: the final WG run, `run:76f8ee0b5d1f078e`;
- `legacy/events_other_shapes.json`: every remaining shape in the store, each event naming
  its own source run (no era is claimed for them).

Each file names its source run and lists every event type that run holds, and holds one event
of each. They live in `contract/fixtures/legacy/`, apart from the mock fixtures, because they
are real records of dev case D and the WG demo plant. The store is opened with SQLite
`mode=ro` (plan H15).
"""

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "guideword.db"
OUT = REPO / "contract" / "fixtures" / "legacy"
ERAS = {
    "events_phase2.json": ("2", "run:e4f544ce3e94a468"),
    "events_phase3.json": ("3", "run:4e6842d31fbdee3b"),
    "events_phase4.json": ("4", "run:76f8ee0b5d1f078e"),
}
OTHER = "events_other_shapes.json"
STEP_EVENTS = ("step_started", "step_finished")


@contextmanager
def read_only(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        yield db


def shape(event: dict[str, Any]) -> tuple[str, str | None, tuple[str, ...]]:
    payload = event["payload"]
    step = payload.get("step") if event["type"] in STEP_EVENTS else None
    return event["type"], step, tuple(sorted(payload))


def run_events(db: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = db.execute("select record from events where run_id = ? order by seq", (run_id,))
    return [json.loads(record) for (record,) in rows]


def first_of_each_shape(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None, tuple[str, ...]]] = set()
    picked = []
    for event in events:
        if event.get("payload_schema") is not None:
            continue  # a v1.9 event is not legacy
        key = shape(event)
        if key not in seen:
            seen.add(key)
            picked.append(event)
    return picked


def build(store: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    covered: set[tuple[str, str | None, tuple[str, ...]]] = set()
    with read_only(store) as db:
        for name, (phase, run_id) in ERAS.items():
            events = run_events(db, run_id)
            if not events:
                raise LookupError(f"no events for {run_id} in {store}")
            picked = first_of_each_shape(events)
            covered |= {shape(e) for e in picked}
            files[name] = {
                "source_run_id": run_id,
                "phase": phase,
                "types": sorted({e["type"] for e in events}),
                "events": picked,
            }
        others = []
        run_ids = [r for (r,) in db.execute("select id from runs order by id")]
        for run_id in run_ids:
            for event in first_of_each_shape(run_events(db, run_id)):
                key = shape(event)
                if key not in covered:
                    covered.add(key)
                    others.append({"source_run_id": run_id, "event": event})
        files[OTHER] = {"events": others}
    return files


def render(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None, *, out_dir: Path = OUT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE)
    args = parser.parse_args(argv)
    if not args.store.is_file():
        print(f"no store at {args.store}", file=sys.stderr)
        return 1
    files = build(args.store)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (out_dir / name).write_text(render(value), encoding="utf-8", newline="\n")
        print(f"wrote {name}: {len(value['events'])} events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
