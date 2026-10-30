"""Lint benchmark case packages (Phase 9 spec 9.0). The case writer runs it.

  python scripts/case_lint.py <package.md> [<package.md> ...]

Prints one line per flag, `<file>:<line>: <kind>: <text>`, for years, company-like names,
"Town, Region" places and the terms of `reference/case_lint_terms.csv` (outcome, hint,
investigator). Exit code 1 when anything is flagged. It never edits a file and never prints a
line of the package beyond the flagged text. No call, no cost.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.caselint import lint_file, load_lint_terms


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", type=Path, nargs="+", help="case packages (Markdown)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    terms = load_lint_terms()
    flagged = 0
    for path in args.files:
        for flag in lint_file(path, terms):
            print(f"{path}:{flag.line}: {flag.kind}: {flag.text}")
            flagged += 1
    print(f"{len(args.files)} files, {flagged} flags")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
