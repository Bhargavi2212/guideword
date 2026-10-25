"""Export one run, as stored, for the deployed site (deploy plan D1). No calls; Bhargavi runs it.

  python scripts/export_recorded.py run:76f8ee0b5d1f078e
      --store guideword-demo.db --out cases/demo/recorded/williams_geismar

The store is opened with SQLite `mode=ro` (plan H15) and never changes. The demo store is the
default (decision C8): the engineer's overrides are made there, so the site shows them. Every
stored row of the run and of its plant is written, one JSON file per table, with three changes
to the copy only:

- the run's label reads `recorded`, recorded at its last event, at the cost its ledger lines
  give (the authority for runs recorded before the refused-retry fix, #103, merged 2026-10-23
  01:32 EDT), with a note when its records fall under that (deploy plan §0.3);
- the precedent judge's `reasoning_text` is left out: the model may have quoted a web page there,
  and the repo is public (§0.4). No response cache is exported, so no page text is;
- nothing is written if a configured API key appears anywhere in the export.

The report gives the export's size and how long it takes to load (§0.5).
"""

import argparse
import json
import math
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guideword.gateway.ledgers import LaptopLedger
from guideword.runs.db import Base
from guideword.runs.machine import SPEND_TOLERANCE_USD, ledger_spent
from guideword.runs.recorded import exported_tables, load_recorded
from guideword.schema.records import SpendEntry
from guideword.settings import Settings
from sqlalchemy import create_engine, select

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "guideword-demo.db"
LEDGER = REPO / "budget" / "ledger.jsonl"
JUDGE = "precedent_judge"


@dataclass(frozen=True)
class Report:
    files: int
    rows: int
    bytes: int
    load_seconds: float


def spend_note(*, stored_usd: float, ledger_usd: float) -> str | None:
    """The label's note when a run's records fall under its ledger lines (deploy plan §0.3)."""
    under = ledger_usd - stored_usd
    if under <= SPEND_TOLERANCE_USD or math.isclose(stored_usd, ledger_usd):
        return None
    return (
        f"record ${under:.4f} under ledger: run recorded on code before the refused-retry fix "
        "(#103)"
    )


def _rows(store: Path, run_id: str) -> dict[str, list[dict[str, Any]]]:
    engine = create_engine(
        f"sqlite:///file:{store.resolve().as_posix()}?mode=ro&uri=true",
        connect_args={"check_same_thread": False},
    )
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    out: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as connection:
        run_row = (
            connection.execute(select(tables["runs"]).where(tables["runs"].c.id == run_id))
            .mappings()
            .first()
        )
        if run_row is None:
            raise LookupError(f"no run {run_id} in {store}")
        plant_id = run_row["plant_record_id"]
        for name in exported_tables():
            table = tables[name]
            if name == "runs":
                where = table.c.id == run_id
            elif name == "plants":
                where = table.c.id == plant_id
            elif "run_id" in table.c:
                where = table.c.run_id == run_id
            else:
                where = table.c.plant_record_id == plant_id
            keys = list(table.primary_key.columns)
            query = select(table).where(where).order_by(*keys)
            out[name] = [dict(row) for row in connection.execute(query).mappings()]
    engine.dispose()
    return out


def export(
    store: Path,
    run_id: str,
    out_dir: Path,
    *,
    ledger: Sequence[SpendEntry],
    secrets: Sequence[str],
) -> Report:
    rows = _rows(store, run_id)
    [run] = rows["runs"]
    record = dict(run["record"])
    events = rows["events"]
    paid = ledger_spent(ledger, run_id)
    cost = paid if paid is not None else float(record["spent_usd"])
    label: dict[str, Any] = {
        "kind": "recorded",
        "recorded_at": events[-1]["record"]["time"] if events else None,
        "cost_usd": cost,
    }
    note = spend_note(stored_usd=float(record["spent_usd"]), ledger_usd=cost)
    if note is not None:
        label["note"] = note
    record["label"] = label
    rows["runs"] = [{**run, "record": record}]
    rows["model_calls"] = [
        {**row, "record": {**row["record"], "reasoning_text": None}}
        if row["record"].get("job") == JUDGE
        else row
        for row in rows["model_calls"]
    ]
    files = {
        f"{name}.json": json.dumps(
            {"table": name, "rows": table_rows}, indent=1, ensure_ascii=False, default=str
        )
        + "\n"
        for name, table_rows in rows.items()
    }
    live = [s for s in secrets if s]
    for name, text in files.items():
        if any(secret in text for secret in live):
            raise ValueError(f"{name} holds a configured API key; nothing was written")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    started = time.perf_counter()
    load_recorded(out_dir)
    return Report(
        files=len(files),
        rows=sum(len(r) for r in rows.values()),
        bytes=sum((out_dir / name).stat().st_size for name in files),
        load_seconds=time.perf_counter() - started,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id")
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.store.is_file():
        print(f"no store at {args.store}", file=sys.stderr)
        return 1
    settings = Settings()
    secrets = [
        settings.nebius_api_key.get_secret_value(),
        settings.tavily_api_key.get_secret_value(),
    ]
    entries = LaptopLedger(args.ledger).entries() if args.ledger.is_file() else []
    # written to a scratch folder first, so a refusal leaves the committed export untouched
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        try:
            report = export(args.store, args.run_id, Path(scratch), ledger=entries, secrets=secrets)
        except (LookupError, ValueError) as refused:
            print(f"refused: {refused}", file=sys.stderr)
            return 1
        args.out.mkdir(parents=True, exist_ok=True)
        for old in args.out.glob("*.json"):
            old.unlink()
        for path in Path(scratch).glob("*.json"):
            (args.out / path.name).write_bytes(path.read_bytes())
    print(
        f"wrote {report.files} files, {report.rows} rows, {report.bytes / 1e6:.2f} MB; "
        f"loads in {report.load_seconds:.2f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
