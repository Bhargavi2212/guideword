"""Report kill test #4 for test #5 (spec 2.10; plan R37). No calls; no re-scoring.

  python scripts/kill4.py

Reads the run files `run-<id>.jsonl` that Bhargavi copied into bench/test5/kill4/, skips dry
runs (every row `dry-model`), and writes bench/test5/kill4/summary.json from the latest real
run: Ultra's recorded ranks (the #4 configuration; a recognised case excluded), Nano's apart,
and the hand review from PROJECT.md §20. results.md shows the ranks as automatic, older
match rule, not hand or grader scores.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.kill4 import is_dry_run, load_run, summarise

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "bench" / "test5" / "kill4"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    real, dry = [], []
    for path in sorted(args.dir.glob("run-*.jsonl")):
        run = path.stem.removeprefix("run-")
        rows = load_run(path)
        if is_dry_run(rows):
            dry.append(run)
            print(f"skipped dry run {run}")
        else:
            real.append((run, rows))
    if not real:
        print(f"no real run file in {args.dir}", file=sys.stderr)
        return 1
    run, rows = real[-1]
    summary = summarise(rows, run=run) | {"skipped_dry_runs": dry}
    path = args.dir / "summary.json"
    path.write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"run {run}: Ultra top 3 on {summary['ultra_top3_unrecognised']} unrecognised cases")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
