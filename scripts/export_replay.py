"""Write a run's model responses as replay fixtures (spec 2.9). Bhargavi runs it; no calls.

  python scripts/export_replay.py run:<hash> cases/dev/case_g.json

Writes bench/replay/<case>/<cache key>.json for every response the run used, plus a
manifest with the run's ranked list, from the run store in `settings.database_url`. The
fixtures hold no keys and no headers; nothing is written if a response holds a configured
API key. The replay test runs the case from them through a gateway that fails on a miss.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.replay import export_replay
from guideword.logs import configure
from guideword.reference import load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.plants import load_plant
from guideword.runs.store import RunRepository
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "bench" / "replay"


def main(
    argv: Sequence[str] | None = None,
    *,
    config: Config | None = None,
    settings: Settings | None = None,
    out_root: Path = OUT,
    repo: Path = REPO,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id")
    parser.add_argument("plant", type=Path, help="the plant file the run was started from")
    args = parser.parse_args(argv)
    configure()
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    ref = load_reference_set()
    sessions = make_session_factory(settings.database_url)
    runs = RunRepository(sessions, lambda: datetime.now(UTC))
    run = runs.get(args.run_id)
    if run is None:
        print(f"no run {args.run_id} in {settings.database_url}", file=sys.stderr)
        return 1
    plant_path = args.plant.resolve()
    record, report = load_plant(json.loads(plant_path.read_text(encoding="utf-8")), ref)
    if record is None or record.id != run.plant_record_id:
        print(f"{args.plant} is not the plant run {run.id} was started from", file=sys.stderr)
        return 1
    if not plant_path.is_relative_to(repo.resolve()):
        print(f"{args.plant} must be inside the repo, so the replay can find it", file=sys.stderr)
        return 1
    case = plant_path.stem
    try:
        out = export_replay(
            runs,
            ResponseCache(sessions),
            run.id,
            out_root / case,
            plant=record.plant_file,
            plant_file=plant_path.relative_to(repo.resolve()).as_posix(),
            ref=ref,
            caps=config.caps,
            secrets=[
                settings.nebius_api_key.get_secret_value(),
                settings.tavily_api_key.get_secret_value(),
            ],
            case=case,
        )
    except (LookupError, ValueError) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(f"wrote {len(list(out.glob('*.json')))} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
