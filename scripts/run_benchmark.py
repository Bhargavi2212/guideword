"""Run the held-out benchmark (Phase 6 spec 6.4). Bhargavi runs it, from the freeze worktree.

  python scripts/run_benchmark.py <held-out folder> --store guideword-benchmark.db
      --ledger D:\\Hackathon\\guideword\\guideword\\budget\\ledger.jsonl
      --frozen D:\\Hackathon\\guideword\\guideword\\bench\\heldout-frozen.txt
      --judgement bench/heldout/probe_judgement.csv --out bench/heldout --phase 6

Every case in letter order, skipping excluded ones: baseline A, baseline B, then Guideword (use
`benchmark`, the run and post caps of `caps.yaml`'s `benchmark:` block, evidence off). Before a
case starts, the stop rule: under `stop_below_usd` left of the benchmark allowance, no further
case starts and the unrun cases are listed. Each configuration's line goes to `<out>/runs.jsonl`
(a Guideword run's `started` line before it is driven), each result under `<out>/case_<x>/`;
a case already run is never run again, and a crashed one resumes its own run at $0. After each
case the store's SHA-256 is printed, for the private repo (G1).

It refuses to start unless it runs from a clean `phase6-freeze*` checkout with the package
imported from it, the ledger is the main checkout's, the store is not `guideword.db` or
`guideword-demo.db`, every frozen plant file matches `--frozen`, and every case it runs has a
judgement row. A case with no frozen plant file is listed as "not converted: not run", never an
error (decisions 2026-10-28).
"""

import argparse
import hashlib
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import guideword
from guideword.api.live import LiveRuns
from guideword.bench.freeze import FreezeRefused, require_benchmark
from guideword.bench.probe import JudgementRefused, read_judgement
from guideword.bench.runner import (
    Case,
    GuidewordParts,
    RunnerRefused,
    baseline_config,
    benchmark_remaining,
    converted_cases,
    guideword_config,
    run_benchmark,
)
from guideword.bench.test5a import BASELINE_A, BASELINE_B
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.reference import load_reference_set
from guideword.reference.precedents import PrecedentIndex
from guideword.runs.case import evidence_tools
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings
from guideword.tools.web import NoKeySearch

ROOT = Path(__file__).resolve().parents[1]
# evidence is off for use benchmark (P4-7), so the precedent index is never read
NO_INDEX = PrecedentIndex((), "benchmark-evidence-off")


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="the held-out folder")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True, help="the main checkout's ledger")
    parser.add_argument("--frozen", type=Path, required=True, help="bench/heldout-frozen.txt")
    parser.add_argument("--judgement", type=Path, required=True, help="probe_judgement.csv")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--phase", required=True, help="the phase whose cap the spend counts against"
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    clock: Callable[[], datetime] | None = None,
    root: Path = ROOT,
) -> int:
    args = _arguments(argv)
    configure()
    try:
        freeze = require_benchmark(
            root,
            store=args.store,
            ledger=args.ledger,
            package_file=Path(guideword.__file__),
            script_file=Path(__file__),
        )
        found = converted_cases(args.folder, args.frozen)
        cases = found.cases
        judgement = read_judgement(args.judgement)
    except (FreezeRefused, RunnerRefused, JudgementRefused) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    clock = clock if clock is not None else (lambda: datetime.now(UTC))
    sessions = make_session_factory(f"sqlite:///{args.store.resolve().as_posix()}")
    cache = ResponseCache(sessions)
    ledger = LaptopLedger(args.ledger)
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=cache,
        ledger=ledger,
        use=BudgetUse.BENCHMARK,
        phase=args.phase,
        clock=clock,
    )
    tools = evidence_tools(
        config=config,
        cache=cache,
        ledger=ledger,
        use=BudgetUse.BENCHMARK,
        phase=args.phase,
        clock=clock,
        search=NoKeySearch(),
        index=NO_INDEX,
    )
    ref = load_reference_set()
    live = LiveRuns(
        sessions, config=config, ref=ref, gateway_factory=lambda s, u: gateway, clock=clock
    )
    parts = GuidewordParts(
        PlantRepository(sessions),
        RunRepository(sessions, clock),
        ref,
        config,
        gateway,
        tools,
        shortlist_of=lambda run_id: [i.model_dump(mode="json") for i in live.shortlist(run_id)],
    )
    out: Path = args.out
    allowance = config.caps.uses[BudgetUse.BENCHMARK].allowance_usd

    def store_hash(case: Case) -> None:
        digest = hashlib.sha256(args.store.read_bytes()).hexdigest()
        print(f"case {case.letter}: done; store SHA-256 {digest}")

    try:
        summary = run_benchmark(
            cases,
            judgement=judgement,
            configs={
                "baseline_a": baseline_config(gateway, config, BASELINE_A, out),
                "baseline_b": baseline_config(gateway, config, BASELINE_B, out),
                "guideword": guideword_config(parts, out),
            },
            lines_path=out / "runs.jsonl",
            remaining=lambda: benchmark_remaining(ledger.entries(), allowance),
            stop_below_usd=config.caps.benchmark.stop_below_usd,
            freeze=freeze,
            after_case=store_hash,
            not_converted=found.not_converted,
        )
    except RunnerRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(f"freeze: {freeze.tag} at {freeze.commit}")
    print(f"run: {', '.join(summary.run) or 'none'}")
    print(f"excluded by the probe: {', '.join(summary.excluded) or 'none'}")
    if summary.already_done:
        print(f"already run (not run again): {', '.join(summary.already_done)}")
    if summary.not_converted:
        print(f"not converted (not run): {', '.join(summary.not_converted)}")
    if summary.unrun:
        left = summary.stopped_with_usd or 0.0
        print(f"not run (stop rule, ${left:.2f} left): {', '.join(summary.unrun)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
