"""Run test #5A (spec 2.10; plan R9). Bhargavi runs it; tests use a fake transport.

  python scripts/run_test5a.py --case d --use test_5

One Ultra call per case with the dev package from cases/dev/source/ and the 5A prompt.
Writes the ranked hazards to bench/test5/5a/case_<letter>.json and the raw call to
bench/test5/raw/5a/. Every call passes the gateway's budget guard and writes a ledger line;
a re-run of the same case is served from the response cache.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from guideword.bench.test5a import run_5a
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.ledgers import Ledger, ledger_for
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
USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.TEST_5.value)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", required=True, help="a case letter, e.g. d")
    parser.add_argument("--use", choices=USES, required=True)
    parser.add_argument(
        "--phase", default=DEFAULT_PHASE, help="the phase whose cap the spend counts against"
    )
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
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    sessions = make_session_factory(settings.database_url)
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
            record = run_5a(gateway, config, letter, source_dir=source_dir, out_root=out_root)
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
