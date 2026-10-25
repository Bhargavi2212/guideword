"""Re-attach a stored run's calculation cards under the current attach rule (review plan R2).

  python scripts/reattach_calculations.py run:76f8ee0b5d1f078e --store guideword-demo.db
      --commit <sha>

Code only and $0: no model call, no search, no key read. It writes the demo store only and
refuses `guideword.db`, which stays untouched (C8). The run's cards the rule no longer gives
are superseded, the ones it now gives are added, and one `calculations_reattached` event names
both, with today's date and the commit given. Bhargavi runs it, then re-exports the run.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from guideword.config import load_config
from guideword.evidence.reattach import ReattachRefused, reattach
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[1]
SOURCE = "guideword.db"


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--commit", required=True, help="the commit whose rule is applied")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> int:
    args = _arguments(argv)
    if args.store.name == SOURCE:
        raise SystemExit(f"refused: {SOURCE} is the source store and is never written (C8)")
    if not args.store.exists():
        raise SystemExit(f"no store {args.store}")
    sessions = make_session_factory(f"sqlite:///{args.store.resolve().as_posix()}")
    runs = RunRepository(sessions, clock)
    run = runs.get(args.run_id)
    if run is None:
        raise SystemExit(f"no run {args.run_id} in {args.store}")
    plant = PlantRepository(sessions).get(run.plant_record_id)
    if plant is None:
        raise SystemExit(f"no plant {run.plant_record_id} for {args.run_id}")
    config = load_config(global_budget_usd=Settings().global_budget_usd)
    try:
        done = reattach(
            runs,
            args.run_id,
            plant.record.plant_file,
            config,
            commit=args.commit,
            today=clock().date(),
        )
    except ReattachRefused as refused:
        raise SystemExit(f"refused: {refused}") from refused
    if not done.superseded_ids and not done.added_ids:
        print(f"{args.run_id}: nothing to re-attach")
        return 0
    print(f"{args.run_id}: superseded {len(done.superseded_ids)}, added {len(done.added_ids)}")
    for record_id in done.superseded_ids:
        print(f"  superseded {record_id}")
    for record_id in done.added_ids:
        print(f"  added      {record_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
