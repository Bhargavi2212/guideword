"""Run one plant file end to end (spec 2.9). Bhargavi runs it; tests use a fake transport.

  python scripts/run_case.py cases/dev/case_g.json --use test_5 --cap 0.85

Uploads the plant, confirms the rule cut (no suggestions), starts the run and advances it
until it stops. Prints the coverage lines and the top 10 ranked findings, and writes the
full ranked list to bench/test5/5b/<case>.json (R11). Every call passes the gateway's
budget guard; live calls need the keys set. The run store is `settings.database_url`
(guideword.db by default): keep it between runs, since it holds the response cache, and a
re-run after a code change then costs nothing.
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
from guideword.runs.case import (
    InvalidPlant,
    case_report,
    drive,
    prepare_plant,
    start_case,
    steppers_for,
)
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.start import ModeNotBuilt
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings

# the spend counts against phase_caps_usd of the phase given by --phase (plan Q15)
DEFAULT_PHASE = "3"
TOP = 10
REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "bench" / "test5" / "5b"
# demo-fixes plan: a demo plant's report never lands among test #5's results
DEMO_PLANTS = REPO / "cases" / "demo"
DEMO_OUT = REPO / "bench" / "demo"


def default_out_dir(plant: Path) -> Path:
    """`bench/demo/` for a plant under `cases/demo/`, else test #5's `bench/test5/5b/`."""
    return DEMO_OUT if plant.resolve().is_relative_to(DEMO_PLANTS.resolve()) else OUT


USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.TEST_5.value)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plant", type=Path, help="the plant file")
    parser.add_argument("--mode", choices=("full", "sample"), default="full")
    parser.add_argument("--use", choices=USES, default=BudgetUse.DEVELOPMENT.value)
    parser.add_argument("--cap", type=float, help="run spend cap in USD (default: caps.yaml)")
    parser.add_argument(
        "--post-cap",
        type=float,
        help="the post-analysis allowance in USD (P3-2; default: caps.yaml, Q20)",
    )
    parser.add_argument(
        "--phase", default=DEFAULT_PHASE, help="the phase whose cap the spend counts against"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="where the report goes (default: bench/demo/ for cases/demo/, else bench/test5/5b/)",
    )
    return parser.parse_args(argv)


def _print_report(report: dict[str, Any]) -> None:
    print(f"run {report['run_id']}: {report['status']}")
    print(
        f"paid ${report['spent_usd']:.4f}; counted against the cap "
        f"${report['cap_spent_usd']:.4f} of ${report['spend_cap_usd']:.2f}"
    )
    if report["status"] == "stopped_cap":
        for hit in report["cap_hits"]:
            print(f"cap reached: {hit.get('reason')}")
        print(f"{report['unrated']} findings unrated")
    if report["open_questions"]:
        print(f"{report['open_questions']} questions left open")
    dropped = report["dropped"]
    print(
        f"dropped {dropped['total']} steps and jobs from batches ({dropped['distinct']} distinct)"
    )
    print("coverage (list: checked / total, unsure, failed)")
    for line in report["coverage"]:
        print(
            f"  {line['list']:<16} {line['checked']:>4} / {line['total']:<4} "
            f"unsure {line['unsure']:<3} failed {line['failed']}"
        )
    dismissed = sum(line["not_credible"] for line in report["not_credible"])
    checked = sum(line["checked"] for line in report["not_credible"])
    print(
        f"of {checked} questions checked: answered {checked - dismissed}, not credible {dismissed}"
    )
    priority = report["priority"]
    print(
        f"{priority['linked_answered_before_first_unlinked']} of "
        f"{priority['linked_questions']} questions linked to the whole-plant hazards answered "
        "before the first unlinked dispatch"
    )
    print(f"top {TOP}: confirmed, also found, unconfirmed (R50); one line per cause (R48)")
    for line in report["hybrid"][:TOP]:
        if line["tier"] == "unconfirmed":
            rating = "unconfirmed"
        else:
            rating = line["rating"] or f"unrated ({line.get('unrated_reason')})"
        more = f" (+{line['folded_count']} folded)" if line["folded_count"] else ""
        hyp = f" #{line['hypothesis_rank']}" if line["hypothesis_rank"] else ""
        print(
            f"  {line['rank']}. [{line['tier']}{hyp}] {rating} {line['severity_class'] or '-'} "
            f"{line['likelihood_class'] or '-'} {line['text']} "
            f"[{line['finding_id'] or line['hypothesis_id']}]{more}"
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
    out_dir: Path | None = None,
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
    raw = json.loads(args.plant.read_text(encoding="utf-8"))
    try:
        record = prepare_plant(plants, raw, ref)
    except InvalidPlant as invalid:
        print(f"the plant file does not validate: {invalid}", file=sys.stderr)
        return 1
    cap = args.cap if args.cap is not None else config.caps.run.run_spend_cap_usd
    try:
        run = start_case(
            plants, runs, ref, config, record.id, cap, args.mode, post_spend_cap_usd=args.post_cap
        )
    except (ModeNotBuilt, ids.CapReachedError) as refused:
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
    drive(runs, run.id, steppers_for(gateway, config, ref, record.plant_file))
    case = args.plant.stem
    report = case_report(runs, run.id, record.plant_file, ref, config.caps, case)
    target = args.out_dir or out_dir or default_out_dir(args.plant)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{case}.json"
    path.write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    _print_report(report)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
