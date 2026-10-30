"""Check a development-case folder before anything reads it (Phase 9 spec 9.0).

  python scripts/dev2_check.py <folder>

The folder holds `cases/` (packages), `keys/` and `plants/`, numbered `case_<nn>`. Prints the
counts, then every problem by case: a part missing, a key lacking a field (named, never its
value), a case ID that does not match its file, key components that are not plant IDs
(counted, never named), a plant file that does not validate, a package the lint flags. Exit
code 1 on any problem. No call, no cost.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.caselint import load_lint_terms
from guideword.bench.dev2 import check_folder
from guideword.reference import load_reference_set


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="the development-case folder")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    report = check_folder(args.folder, load_reference_set(), load_lint_terms())
    print("counts: " + ", ".join(f"{k} {n}" for k, n in report.counts.items()))
    for problem in report.problems:
        print(problem)
    if report.problems:
        print(
            f"STOP: {len(report.problems)} problems; nothing reads this folder until they are fixed"
        )
        return 1
    print(f"{len(report.cases)} development cases ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
