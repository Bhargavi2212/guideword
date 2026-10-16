"""Write bench/test5/results.md from the test #5 outputs (spec 2.10; plan R35). No calls.

  python scripts/test5_results.py

The table is generated from the 5B reports, the 5A records, scores.json and
hand_scores.csv; it is never typed, and a hand score not in the sheet shows "not scored".
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.results import render_results

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "bench" / "test5"
RESULTS = "results.md"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    try:
        text = render_results(args.root)
    except ValueError as invalid:
        print(f"refused: {invalid}", file=sys.stderr)
        return 1
    path = args.root / RESULTS
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
