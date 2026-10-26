"""Run test #5A (spec 2.10; plan R9). Bhargavi runs it; tests use a fake transport.

  python scripts/run_test5a.py --case d --use test_5

One Ultra call per case with the dev package from cases/dev/source/ and the 5A prompt.
Writes the ranked hazards to bench/test5/5a/case_<letter>.json and the raw call to
bench/test5/raw/5a/. Every call passes the gateway's budget guard and writes a ledger line;
a re-run of the same case is served from the response cache.

Phase 6 (spec 6.3): `--source-dir` and `--out` name the package folder and the output root,
`--baseline b` runs baseline B (`baseline_plain`, no checklist). `--use benchmark` needs
`--store` and `--ledger` and runs only from a clean `phase6-freeze*` worktree, never on
`guideword.db` or `guideword-demo.db` (`guideword/bench/freeze.py`).
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import guideword
from guideword.bench.freeze import FreezeRefused, require_benchmark
from guideword.bench.test5a import BASELINE_A, BASELINE_B, run_baseline
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.ledgers import LaptopLedger, Ledger, ledger_for
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[1]
# the spend counts against phase_caps_usd of the phase given by --phase (plan Q15)
DEFAULT_PHASE = "3"
SOURCE = REPO / "cases" / "dev" / "source"
OUT = REPO / "bench" / "test5"
USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.TEST_5.value, BudgetUse.BENCHMARK.value)
BASELINES = {"a": BASELINE_A, "b": BASELINE_B}


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", required=True, help="a case letter, e.g. d")
    parser.add_argument("--use", choices=USES, required=True)
    parser.add_argument(
        "--phase", default=DEFAULT_PHASE, help="the phase whose cap the spend counts against"
    )
    parser.add_argument("--baseline", choices=sorted(BASELINES), default="a")
    parser.add_argument("--source-dir", type=Path, help="the package folder")
    parser.add_argument("--out", type=Path, help="the output root")
    parser.add_argument("--store", type=Path, help="the store (required with --use benchmark)")
    parser.add_argument("--ledger", type=Path, help="the ledger (required with --use benchmark)")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
    source_dir: Path = SOURCE,
    out_root: Path = OUT,
) -> int:
    args = _arguments(argv)
    configure()
    store: Path | None = args.store
    if args.use == BudgetUse.BENCHMARK.value:
        if args.store is None or args.ledger is None:
            print("refused: --use benchmark needs --store and --ledger", file=sys.stderr)
            return 1
        try:
            require_benchmark(
                REPO,
                store=args.store,
                ledger=args.ledger,
                package_file=Path(guideword.__file__),
                script_file=Path(__file__),
            )
        except FreezeRefused as refused:
            print(f"refused: {refused}", file=sys.stderr)
            return 1
        ledger = LaptopLedger(args.ledger)
    source_dir = args.source_dir if args.source_dir is not None else source_dir
    out_root = args.out if args.out is not None else out_root
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    sessions = make_session_factory(
        settings.database_url if store is None else f"sqlite:///{store.resolve().as_posix()}"
    )
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else ledger_for(settings, sessions),
        use=BudgetUse(args.use),
        phase=args.phase,
        clock=clock if clock is not None else (lambda: datetime.now(UTC)),
    )
    for letter in args.case:
        try:
            record = run_baseline(
                gateway,
                config,
                letter,
                baseline=BASELINES[args.baseline],
                source_dir=source_dir,
                out_root=out_root,
            )
        except (BudgetRefused, LookupError) as refused:
            print(f"case_{letter}: refused: {refused}", file=sys.stderr)
            return 1
        cached = " (cached)" if record["cache_hit"] else ""
        print(
            f"case_{letter}: {record['outcome']}, {len(record['hazards'])} hazards, "
            f"${record['cost_usd']:.4f}{cached}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
