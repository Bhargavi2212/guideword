"""Parse every stored event with the contract's event models (Phase 5 plan Q7, J7). No calls.

  python scripts/check_event_payloads.py              # guideword.db, opened read-only
  python scripts/check_event_payloads.py --store other.db

Every event in the store is parsed as the API serves it: the model is chosen by its type and
its `payload_schema` stamp (contract v1.9), so an event stored before v1.9 meets its type's
legacy model. The report lists each payload shape (type; the step, for step events; the
sorted payload keys) with how many events have it, the run its first one came from, the model
that parsed it, and pass or the first error. Exits 1 if any event fails. Bhargavi records the
result in docs/decisions.md.
"""

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guideword.schema.events import ApiEvent
from pydantic import TypeAdapter, ValidationError

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "guideword.db"
STEP_EVENTS = ("step_started", "step_finished")
ADAPTER: TypeAdapter[Any] = TypeAdapter(ApiEvent)


@dataclass
class Shape:
    type: str
    step: str | None
    keys: tuple[str, ...]
    source_run_id: str
    count: int = 0
    model: str = ""
    ok: bool = True
    error: str | None = None


@contextmanager
def read_only(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        yield db


def _short(error: ValidationError) -> str:
    """Each error as `field: message`, without the union's long name."""
    parts = [f"{'.'.join(str(p) for p in e['loc'][1:]) or '-'}: {e['msg']}" for e in error.errors()]
    return "; ".join(parts)[:300]


def check(store: Path) -> list[Shape]:
    shapes: dict[tuple[str, str | None, tuple[str, ...]], Shape] = {}
    with read_only(store) as db:
        rows = db.execute("select run_id, record from events order by run_id, seq")
        for run_id, record in rows:
            event = json.loads(record)
            payload = event.get("payload", {})
            step = payload.get("step") if event["type"] in STEP_EVENTS else None
            key = (event["type"], step, tuple(sorted(payload)))
            shape = shapes.setdefault(key, Shape(key[0], key[1], key[2], run_id))
            shape.count += 1
            try:
                parsed = ADAPTER.validate_python(event)
            except ValidationError as error:
                if shape.ok:
                    shape.ok, shape.error = False, _short(error)
                continue
            shape.model = shape.model or type(parsed).__name__
    return sorted(shapes.values(), key=lambda s: (s.type, s.step or "", s.keys))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE)
    args = parser.parse_args(argv)
    if not args.store.is_file():
        print(f"no store at {args.store}", file=sys.stderr)
        return 1
    report = check(args.store)
    for shape in report:
        where = f"{shape.type}" + (f" @{shape.step}" if shape.step else "")
        verdict = "ok" if shape.ok else f"FAILED: {shape.error}"
        print(
            f"{where:40} {shape.count:6} from {shape.source_run_id:24} "
            f"{shape.model or '-':32} {verdict}"
        )
    failed = sum(1 for s in report if not s.ok)
    events = sum(s.count for s in report)
    print(f"{len(report)} shapes, {events} events, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
