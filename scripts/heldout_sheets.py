"""Write the blind sheets and the second grader's packets (Phase 6 spec P6-10, P6-3 step 6).

  python scripts/heldout_sheets.py --keys <held-out folder>/keys/answer_keys.json
      --out bench/heldout

For every case run: `<out>/sheets/<case>.csv` for Bhargavi and `<out>/sheets_grader2/<case>.csv`
for the second grader, each configuration's top 10 under a label fixed by `h(case_id)`, with
record keys turned into names; `<out>/grader2/<case>.md`, the packet with only the key's
`root_cause`, `component_ids` and `missed_by_original_review`; and `<out>/blind_map.json`, which
is opened only after grading. A sheet is written once and never overwritten. No call, no cost.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.blind import write_case_sheets
from guideword.bench.heldout_keys import KeyFieldsMissing, load_heldout_keys

from heldout_score import lines_of, run_cases


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        keys = load_heldout_keys(args.keys)
    except KeyFieldsMissing as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    for case in run_cases(args.out):
        try:
            write_case_sheets(case, lines_of(args.out, case), keys[case].model_dump(), args.out)
        except FileExistsError as refused:
            print(f"refused: {refused}", file=sys.stderr)
            return 1
        print(f"case {case}: sheets and packet written")
    print("grade blind; open blind_map.json only when every row is scored")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
