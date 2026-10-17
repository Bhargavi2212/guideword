"""Score test #5 automatically (spec 2.10; plan R26a, R26c, R38). No calls.

  python scripts/score_test5.py --case d

Reads the case's key from cases/dev/keys/answer_keys.json (only when Bhargavi runs it; tests
pass a synthetic file), the 5B report from bench/test5/5b/ and the 5A record from
bench/test5/5a/, and reports the rank of the first line that matches every phrase group:
top 3, top 10 or missed. Only the agent's own words are matched, never IDs. A 5B run that
stopped at a cap is reported, not scored. Writes bench/test5/scores.json and adds the top 10
of each to bench/test5/hand_scores.csv for the hand score; filled scores are never changed.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.results import (
    CONFIGS,
    HAND_SCORES,
    NOT_IN_RUN,
    SCORES,
    score_case,
    update_hand_sheet,
)
from guideword.bench.scoring import load_keys

REPO = Path(__file__).resolve().parents[1]
DEFAULT_KEYS = REPO / "cases" / "dev" / "keys" / "answer_keys.json"
DEFAULT_ROOT = REPO / "bench" / "test5"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", required=True, help="a case letter, e.g. d")
    parser.add_argument("--keys", type=Path, default=DEFAULT_KEYS)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    keys = load_keys(args.keys)
    missing = [c for c in args.case if c not in keys]
    if missing:
        print(f"the key has no case {', '.join(missing)}", file=sys.stderr)
        return 1
    path = args.root / SCORES
    scores = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for letter in args.case:
        scores[letter] = score_case(letter, keys[letter], args.root)
        for config, label in CONFIGS.items():
            result = scores[letter][config]
            if result["status"] == NOT_IN_RUN:
                continue  # a hybrid run has no legacy 5B, an older one no hybrid views (R50)
            if not result["scored"]:
                print(f"case_{letter} {label}: not scored ({result['status']})")
            elif result["rank"] is None:
                print(f"case_{letter} {label}: missed")
            else:
                print(f"case_{letter} {label}: rank {result['rank']} ({result['bucket']})")
    args.root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scores, indent=1, sort_keys=True) + "\n", "utf-8", newline="\n")
    for letter, config, rank in update_hand_sheet(args.root, args.case):
        print(
            f"hand score kept for case_{letter} {config} rank {rank}, "
            "but that line has changed since: check it"
        )
    print(f"wrote {path} and {args.root / HAND_SCORES}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
