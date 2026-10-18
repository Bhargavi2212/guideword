"""Run the four-tier comparison (spec 2.10; plan PR 12b, R27). Bhargavi runs it.

  python scripts/four_tier.py --use test_5 --cap 0.40

The same sample of 50 questions from cases D–H, each answered by its own specialist on every
tier, under one spend cap for the whole comparison; the gateway's caps and the use allowance
also apply. Writes bench/test5/four_tier/ (summary and each tier's answers), the raw calls to
bench/test5/raw/four_tier/, and the blank score sheet bench/test5/four_tier_scores.csv (good,
partial or wrong per question and tier), which keeps scores already filled. The run store
(`settings.database_url`) holds the response cache, so a re-run after a code change is free.
"""

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from guideword.bench.four_tier import load_cases, run_four_tier, sample, write_outputs
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import Ledger, ledger_for
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.reference import load_reference_set
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings

PHASE = "2"
REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "cases" / "dev"
OUT = REPO / "bench" / "test5"
USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.TEST_5.value)


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
    timer: Callable[[], float] = time.perf_counter,
    out_root: Path = OUT,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--use", choices=USES, default=BudgetUse.TEST_5.value)
    parser.add_argument("--cap", type=float, required=True, help="spend cap for the comparison")
    args = parser.parse_args(argv)
    configure()
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    ref = load_reference_set()
    sessions = make_session_factory(settings.database_url)
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else ledger_for(settings, sessions),
        use=BudgetUse(args.use),
        phase=PHASE,
        clock=clock if clock is not None else (lambda: datetime.now(UTC)),
    )
    picked = sample(load_cases(CASES), ref)
    result = run_four_tier(gateway, config, ref, picked, cap_usd=args.cap, timer=timer)
    write_outputs(result, out_root)
    for tier, r in result.tiers.items():
        print(
            f"{tier}: {r.valid}/{r.questions} valid, median {r.median_latency_s:.2f} s, "
            f"${r.cost_usd:.4f}"
        )
    if result.stopped:
        print(result.stopped)
    print(f"wrote {out_root / 'four_tier'} and {out_root / 'four_tier_scores.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
