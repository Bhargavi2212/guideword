"""Extend a finished run with the post-analysis steps (spec 3.6; P3-1b). Bhargavi runs it; tests
use a fake transport.

  python scripts/extend_run.py <run_id> --post-cap 0.30 --phase 3 --use development --name case_e

With --rerun-from chains, re-runs the four post steps of a run whose chains step has run
(connector/v2 plan): the old chains, LOPA records, recommendations and post-step calls are
copied to superseded_records and cleared in one transaction; unchanged requests come from the
cache at $0; the run ID stays.

With --retry-failed (demo-fixes plan), asks each failed question of a finished run alone,
then rates only the new findings and runs the post steps from chains; the analysis cap is
raised by --retry-cap and no orchestrator call is made. --out-dir sets where the report goes.

Refuses a run that has not finished or whose chains step has run, unless it stopped at its
post cap and --post-cap is higher: then it resumes from the step it stopped at, with the
same run ID (Bhargavi, 2026-10-20). Otherwise sets the run's
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
from guideword.runs.case import case_report, drive, evidence_tools, steppers_for
from guideword.runs.db import make_session_factory
from guideword.runs.extend import RERUN_FROM, ExtendRefused, extend
from guideword.runs.machine import spend_check
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings
from guideword.tools.web import NoKeySearch, SearchClient, live_search
from pydantic import ValidationError

# the spend counts against phase_caps_usd of the phase given by --phase (plan Q15)
DEFAULT_PHASE = "3"
OUT = Path(__file__).resolve().parents[1] / "bench" / "phase3"
# plan Q16: extensions spend on use development; Phase 4 plan Q7, G7: or video, to add or
# re-run evidence on the final demo run
USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.VIDEO.value)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="the finished run to extend, or one stopped at its post cap")
    parser.add_argument(
        "--post-cap", type=float, help="post-analysis allowance in USD (default: caps.yaml)"
    )
    parser.add_argument(
        "--phase", default=DEFAULT_PHASE, help="the phase whose cap the spend counts against"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="ask each failed question alone, then severity and the post steps from chains",
    )
    parser.add_argument(
        "--retry-cap",
        type=float,
        default=0.30,
        help="USD added to the analysis cap for --retry-failed (default 0.30)",
    )
    parser.add_argument(
        "--out-dir", type=Path, help="where the report goes (default: bench/phase3/)"
    )
    # B2 (Q9, Q13): no default; a run's use is fixed when it starts
    parser.add_argument("--use", choices=USES, required=True)
    parser.add_argument("--name", help="the report's file name (default: the plant ID)")
    parser.add_argument(
        "--rerun-from",
        choices=RERUN_FROM,
        help="re-run the post steps from this one; the old records are superseded, not deleted",
    )
    parser.add_argument(
        "--evidence",
        action="store_true",
        help="add the evidence step to a finished, extended run whose pass had none (same ID)",
    )
    parser.add_argument(
        "--no-evidence", action="store_true", help="skip the evidence step in this pass"
    )
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


def _search(
    search: SearchClient | None, transport: Transport | None, settings: Settings
) -> SearchClient:
    """The web search: the one given; with an injected (fake) transport and none given, one
    that fails without sending, so a test never pairs with the live Tavily client; else live."""
    if search is not None:
        return search
    if transport is not None:
        return NoKeySearch()
    return live_search(settings.tavily_api_key.get_secret_value())


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
    out_dir: Path = OUT,
    search: SearchClient | None = None,
) -> int:
    args = _arguments(argv)
    out_dir = args.out_dir or out_dir
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
        extend(
            runs,
            run.id,
            post_cap,
            config,
            use=BudgetUse(args.use),
            rerun_from=args.rerun_from,
            retry_failed=args.retry_failed,
            retry_cap_usd=args.retry_cap,
            evidence_only=args.evidence,
        )
    except ExtendRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    ledger = ledger if ledger is not None else ledger_for(settings, sessions)
    cache = ResponseCache(sessions)
    use = BudgetUse(args.use)
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=cache,
        ledger=ledger,
        use=use,
        phase=args.phase,
        clock=clock,
    )
    tools = evidence_tools(
        config=config,
        cache=cache,
        ledger=ledger,
        use=use,
        phase=args.phase,
        clock=clock,
        search=_search(search, transport, settings),
        enabled=not args.no_evidence,
    )
    plant = stored.record.plant_file
    drive(runs, run.id, steppers_for(gateway, config, ref, plant, evidence=tools))
    name = args.name or plant.plant_id
    report = case_report(runs, run.id, plant, ref, config.caps, name)
    # beside R45 (bug fix, 2026-10-22): the run's spend against its own ledger lines
    finished = runs.get(run.id)
    if finished is not None:
        report["spend_check"] = spend_check(finished, ledger.entries())
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
    check = report.get("spend_check")
    if check is not None and check["ledger_usd"] is not None:
        verdict = "matches" if check["matches"] else "DOES NOT MATCH"
        print(
            f"spend check: records ${check['spent_usd']:.4f}, ledger ${check['ledger_usd']:.4f}"
            f" ({verdict})"
        )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
