"""Run the memorisation probe on the held-out cases (Phase 6 spec 6.2, P6-5). Bhargavi runs it.

  python scripts/probe_heldout.py <held-out folder> --store guideword-benchmark.db
      --ledger D:\\Hackathon\\guideword\\guideword\\budget\\ledger.jsonl
      --out bench/heldout --phase 6

One Ultra call per case (`prompts/probe/`), in case-letter order, every case in the folder
unless `--case` names some. Use `benchmark`, booked to the phase given. Runs only from a clean
`phase6-freeze*` worktree with the package imported from it, with the main checkout's ledger,
and never on `guideword.db` or `guideword-demo.db` (`guideword/bench/freeze.py`). Writes each
answer to `<out>/probe/`, the raw call to `<out>/raw/probe/`, and the freeze tag and commit to
`<out>/probe/freeze.json`. A re-run of a case is served from the store's cache at $0.
"""

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import guideword
from guideword.bench.freeze import FreezeRefused, require_benchmark
from guideword.bench.probe import run_probe
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = re.compile(r"^case_([a-z])_.+\.md$", re.IGNORECASE)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="the held-out folder")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True, help="the main checkout's ledger")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--phase", required=True, help="the phase whose cap the spend counts against"
    )
    parser.add_argument("--case", action="append", help="a case letter; default: every case")
    return parser.parse_args(argv)


def case_letters(folder: Path) -> list[str]:
    """The case letters of the folder's packages, in letter order (P6-8)."""
    found = {m.group(1).lower() for p in folder.rglob("case_*.md") if (m := _PACKAGE.match(p.name))}
    return sorted(found)


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
    except FreezeRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    sessions = make_session_factory(f"sqlite:///{args.store.resolve().as_posix()}")
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=LaptopLedger(args.ledger),
        use=BudgetUse.BENCHMARK,
        phase=args.phase,
        clock=clock if clock is not None else (lambda: datetime.now(UTC)),
    )
    out: Path = args.out
    (out / "probe").mkdir(parents=True, exist_ok=True)
    (out / "probe" / "freeze.json").write_text(
        f'{{"tag": "{freeze.tag}", "commit": "{freeze.commit}"}}\n', encoding="utf-8"
    )
    for letter in args.case or case_letters(args.folder):
        try:
            record = run_probe(gateway, config, letter, source_dir=args.folder, out_root=out)
        except (BudgetRefused, LookupError, ValueError) as refused:
            print(f"case_{letter}: refused: {refused}", file=sys.stderr)
            return 1
        cached = " (cached)" if record["cache_hit"] else ""
        print(f"case_{letter}: {record['outcome']}, ${record['cost_usd']:.4f}{cached}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
