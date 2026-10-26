"""Check a later freeze tag changes only the benchmark tooling (Phase 6 spec P6-2; plan G2).

  python scripts/check_freeze_diff.py phase6-freeze-2

A post-freeze tooling fix needs a new `phase6-freeze*` tag, and the tag counts only when every
path it changes compared with `phase6-freeze` is under `backend/guideword/bench/` or `scripts/`:
never the pipeline, its API (`api/`) or its exports (`export/`). Prints each path that isn't
allowed; exit code 1 if there is any. No call, no cost.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.freeze import ALLOWED_AFTER_FREEZE, FREEZE_TAG, FreezeRefused, freeze_diff

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("new_tag")
    parser.add_argument("--base", default=FREEZE_TAG)
    args = parser.parse_args(argv)
    try:
        refused = freeze_diff(root, args.new_tag, args.base)
    except FreezeRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    if refused:
        print(f"{args.new_tag} changes paths outside {', '.join(ALLOWED_AFTER_FREEZE)}:")
        for path in refused:
            print(f"  {path}")
        return 1
    print(f"{args.new_tag}: only benchmark tooling changed since {args.base}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
