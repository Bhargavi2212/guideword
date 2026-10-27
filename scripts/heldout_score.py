"""The held-out automatic score (Phase 6 spec P6-9, P6-3 step 5). Bhargavi runs it, after the runs.

  python scripts/heldout_score.py --keys <held-out folder>/keys/answer_keys.json --out bench/heldout

For every case with all three configurations done in `<out>/runs.jsonl`: each configuration's first
line naming a key component and containing a key phrase (any ID renamed under P6-12 is applied
through `<out>/fixes.md`), and Guideword's found-anywhere rank in its full shortlist. Writes
`<out>/auto_scores.json`; prints case, configuration and rank only. No call, no cost.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from guideword.bench.heldout_keys import KeyFieldsMissing, load_heldout_keys
from guideword.bench.heldout_scoring import (
    Line,
    baseline_lines,
    first_auto_match,
    guideword_lines,
    read_renames,
)
from guideword.bench.runner import CONFIGS, read_lines
from guideword.bench.test5a import BASELINE_A, BASELINE_B
from guideword.reference import load_reference_set

FOLDERS = {"baseline_a": BASELINE_A.folder, "baseline_b": BASELINE_B.folder}


def run_cases(out: Path) -> list[str]:
    """Cases with every configuration done, in letter order."""
    done = {
        (x["case"], x["config"]) for x in read_lines(out / "runs.jsonl") if x["state"] == "done"
    }
    return sorted({c for c, _ in done if all((c, k) in done for k in CONFIGS)})


def lines_of(out: Path, case: str) -> dict[str, list[Line]]:
    causes = {c.id: c.cause for c in load_reference_set().causes}
    folder = out / f"case_{case}"
    shortlist = json.loads((folder / "shortlist.json").read_text(encoding="utf-8"))
    lines = {"guideword": guideword_lines(shortlist, causes)}
    for config, sub in FOLDERS.items():
        record = json.loads((folder / sub / f"case_{case}.json").read_text(encoding="utf-8"))
        lines[config] = baseline_lines(record)
    return lines


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
    renames = read_renames(args.out / "fixes.md")
    scores: dict[str, dict[str, int | None]] = {}
    for case in run_cases(args.out):
        if case not in keys:
            print(f"refused: no key for case {case}", file=sys.stderr)
            return 1
        key = keys[case]
        components = [renames.get(c, c) for c in key.component_ids]
        lines = lines_of(args.out, case)
        row: dict[str, int | None] = {
            config: first_auto_match(lines[config], components, key.match_phrases)
            for config in CONFIGS
        }
        row["guideword_found_anywhere"] = row["guideword"]
        scores[case] = row
        print(
            f"case {case}: "
            + ", ".join(f"{k} {v if v is not None else '-'}" for k, v in row.items())
        )
    target = args.out / "auto_scores.json"
    target.write_text(json.dumps(scores, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
