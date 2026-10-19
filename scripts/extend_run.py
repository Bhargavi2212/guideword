"""Extend a finished run with the post-analysis steps (spec 3.6; P3-1b). Bhargavi runs it; tests
use a fake transport.

  python scripts/extend_run.py <run_id> --post-cap 0.30 --phase 3 --use development --name case_e

Refuses a run that has not finished or whose chains step has run. Otherwise sets the run's
post-analysis allowance, moves it to the chains step, drives it to a terminal status and
writes the shortlist, chains, LOPA records and recommendations to bench/phase3/<name>.json.
The analysis is not run again and no earlier record changes. A run whose records fail to
load on this code is skipped, and the reason is printed and written to the same file; old
records are never patched. Live calls need the keys set; every call passes the budget guard.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import Ledger, ledger_for
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.reference import load_reference_set
from guideword.runs.case import case_report, drive, steppers_for
from guideword.runs.db import make_session_factory
from guideword.runs.extend import ExtendRefused, extend
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings
from pydantic import ValidationError

# the spend counts against phase_caps_usd of the phase given by --phase (plan Q15)
DEFAULT_PHASE = "3"
OUT = Path(__file__).resolve().parents[1] / "bench" / "phase3"
# plan Q16: extensions spend on use development
USES = (BudgetUse.DEVELOPMENT.value,)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="the finished run to extend")
    parser.add_argument(
        "--post-cap", type=float, help="post-analysis allowance in USD (default: caps.yaml)"
    )
    parser.add_argument(
        "--phase", default=DEFAULT_PHASE, help="the phase whose cap the spend counts against"
    )
    parser.add_argument("--use", choices=USES, default=BudgetUse.DEVELOPMENT.value)
    parser.add_argument("--name", help="the report's file name (default: the plant ID)")
    return parser.parse_args(argv)


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def _check_records_load(runs: RunRepository, run_id: str) -> None:
    """Read every record of the run on this code; raises ValidationError or LookupError."""
    if runs.get(run_id) is None:
        raise LookupError(f"no run {run_id}")
    runs.questions(run_id)
    runs.findings(run_id)
    runs.hypotheses(run_id)
    runs.steps(run_id)
    runs.model_calls(run_id)
    runs.tool_calls(run_id)
    runs.events(run_id)
    runs.sections(run_id)


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
    out_dir: Path = OUT,
) -> int:
    args = _arguments(argv)
    configure()
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    clock = clock if clock is not None else (lambda: datetime.now(UTC))
    ref = load_reference_set()
    sessions = make_session_factory(settings.database_url)
    plants = PlantRepository(sessions)
    runs = RunRepository(sessions, clock)
    try:
        _check_records_load(runs, args.run_id)
    except (ValidationError, LookupError) as broken:
        reason = str(broken).replace("\n", " ")[:500]
        print(f"skipped {args.run_id}: its records do not load: {reason}", file=sys.stderr)
        name = args.name or args.run_id.replace(":", "_")
        _write(
            out_dir / f"{name}.json", {"run_id": args.run_id, "status": "skipped", "reason": reason}
        )
        return 1
    run = runs.get(args.run_id)
    assert run is not None  # checked above
    stored = plants.get(run.plant_record_id)
    if stored is None:
        print(f"refused: no plant {run.plant_record_id} for run {run.id}", file=sys.stderr)
        return 1
    post_cap = args.post_cap if args.post_cap is not None else config.caps.run.post_spend_cap_usd
    try:
        extend(runs, run.id, post_cap, config)
    except ExtendRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else ledger_for(settings, sessions),
        use=BudgetUse(args.use),
        phase=args.phase,
        clock=clock,
    )
    plant = stored.record.plant_file
    drive(runs, run.id, steppers_for(gateway, config, ref, plant))
    name = args.name or plant.plant_id
    report = case_report(runs, run.id, plant, ref, config.caps, name)
    path = out_dir / f"{name}.json"
    _write(path, report)
    print(f"run {report['run_id']}: {report['status']}")
    print(
        f"post-analysis: counted ${report['post_spent_usd']:.4f} of "
        f"${report['post_spend_cap_usd']:.2f}; {len(report['chains'])} chains "
        f"({len(report['chains_rejected'])} rejected), {len(report['lopa'])} LOPA records, "
        f"{len(report['recommendations'])} recommendations"
    )
    for hit in report["cap_hits"]:
        print(f"cap reached: {hit.get('reason')}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
