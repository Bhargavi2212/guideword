"""Generate `results.md` from the run records (Phase 6 spec 6.5, P6-11). Bhargavi runs it.

  python scripts/heldout_results.py --out bench/heldout

Refuses while any row of either grader's sheets has no score. The file is generated, never edited
by hand. No call, no cost.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.heldout_results import ResultsRefused, render_results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        text = render_results(args.out)
    except ResultsRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    target = args.out / "results.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
