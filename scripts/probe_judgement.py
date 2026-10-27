"""Show each probe's answer beside only its key's source, and write the judgement file (Phase 6
spec P6-3 step 3b, P6-5; plan G7). Bhargavi runs it, after the probe and before any run.

  python scripts/probe_judgement.py --probe-dir bench/heldout/probe
      --keys <held-out folder>/keys/answer_keys.json --csv bench/heldout/probe_judgement.csv

Each key record is read for its `case_id` and `source` only; every other field is dropped
unread. Prints, per case, what the probe named and the key's source; writes
`probe_judgement.csv` once (case, the probe's own yes/no, and empty `excluded` and `reason`
columns for Bhargavi). Exclude a case when the probe names the company, the site or the accident
correctly, whatever its own yes/no says. No call, no cost.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.probe import JudgementRefused, judgement_rows, write_judgement

NAMES = ("company", "site", "year", "accident_name")


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    rows = judgement_rows(args.probe_dir, args.keys)
    for row in rows:
        if row.probe is None:
            said = "the probe failed"
        else:
            named = ", ".join(f"{n}: {row.probe[n]}" for n in NAMES if row.probe.get(n))
            recognised = "yes" if row.probe["recognised"] else "no"
            said = f"recognised: {recognised}; {named or 'named nothing'}"
        print(f"case {row.case}: {said}")
        source = row.source if isinstance(row.source, str) else json.dumps(row.source)
        print(f"  key source: {source if row.source is not None else '(no key)'}")
    try:
        write_judgement(rows, args.csv)
    except JudgementRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(f"wrote {args.csv}: fill 'excluded' (yes/no) and 'reason' for every case")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
