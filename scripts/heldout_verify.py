"""Check the held-out folder against its seals before anyone reads it (Phase 6 spec 6.1).

  python scripts/heldout_verify.py D:\\Hackathon\\guideword\\guideword-heldout
      --frozen-out bench/heldout-frozen.txt [--only k,l,m,n,p] [--seal-info]

Bhargavi runs it; Claude Code never does on the real folder (CLAUDE.md §5). It prints file names,
counts and the keys' field names only, never a line of any file. Exit code 1 on any missing,
unlisted or changed file, any line of SEALS.txt that isn't a seal, or any plant file that doesn't
validate; the frozen hashes are written only when everything passes. Any mismatch stops Phase 6
until Bhargavi decides (P6-1). No call, no cost.

`--only` (decisions 2026-10-28) limits the plant-file check and `--frozen-out` to the cases it
names; the seal check still covers every sealed file. Each named case needs a package and a
valid plant file; the other plant files are listed, never checked or frozen.
"""

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from guideword.bench.heldout import (
    SEALS_FILE,
    case_files,
    check_seals,
    classify,
    frozen_lines,
    inventory,
    plant_files,
    seal_info,
    validate_plants,
)
from guideword.reference import load_reference_set

_CASE = re.compile(r"^case_([a-z])", re.IGNORECASE)


def _letter(path: str) -> str:
    match = _CASE.match(PurePosixPath(path).name)
    return match.group(1).lower() if match else path


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="the held-out folder")
    parser.add_argument("--frozen-out", type=Path, help="where to write the plant files' hashes")
    parser.add_argument(
        "--seal-info", action="store_true", help="print SEALS.txt's size and time (P6-1)"
    )
    parser.add_argument(
        "--only", help="comma-separated case letters: check and freeze only their plant files"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    folder: Path = args.folder
    if args.seal_info:
        size, when = seal_info(folder)
        print(f"{SEALS_FILE}: {size} bytes, modified {when}")
    check = check_seals(folder)
    print(f"seals: {check.ok} of {check.listed} files match")
    for number in check.bad_lines:
        print(f"not a seal: {SEALS_FILE} line {number}")
    for path in check.missing:
        print(f"missing: {path}")
    for path in check.unlisted:
        print(f"unlisted: {path}")
    for path in check.mismatched:
        print(f"mismatch: {path}")
    for path in check.unsealed_plants:
        print(f"new plant file (frozen separately): {path}")
    for path in check.unsealed_other:
        print(f"not a case file (not sealed, not checked): {path}")
    present = [p for p in case_files(folder) if p not in check.unsealed_other]
    found = inventory(folder, dict.fromkeys(present, ""))
    print("inventory: " + ", ".join(f"{k} {n}" for k, n in found.counts.items()))
    for path in found.unclassified:
        print(f"unclassified: {path}")
    print("key fields: " + (", ".join(found.key_fields) or "none"))
    plants = plant_files(dict.fromkeys(present, ""))
    letters = {_letter(p) for p in present if classify(p) == "package"}
    unknown: list[str] = []
    if args.only is not None:
        only = {x.strip().lower() for x in args.only.split(",") if x.strip()}
        unknown = sorted(only - letters)
        for letter in unknown:
            print(f"no package for case {letter}")
        for path in plants:
            if _letter(path) not in only:
                print(f"not in --only (not checked, not frozen): {path}")
        plants = [p for p in plants if _letter(p) in only]
        letters &= only
    invalid = 0
    for path, issues in validate_plants(folder, plants, load_reference_set()).items():
        print(f"{path}: {'valid' if not issues else f'{len(issues)} errors'}")
        for issue in issues:
            print(f"{path}: {issue.code}: {issue.message}")
        invalid += bool(issues)
    # every package (each named one, with --only) needs its plant file before freezing (P6-12)
    without = sorted(letters - {_letter(p) for p in plants})
    if not plants:
        print("no plant files yet: convert the packages (P6-12) before freezing")
    else:
        for letter in without:
            print(f"no plant file for case {letter}")
    if not check.passed or invalid or unknown:
        print("STOP: Phase 6 waits on Bhargavi's decision (P6-1, P6-12); nothing was written")
        return 1
    if args.frozen_out is not None and (not plants or without):
        print("STOP: every package needs a valid plant file before freezing; nothing was written")
        return 1
    if args.frozen_out is not None:
        args.frozen_out.write_text(frozen_lines(folder, plants), encoding="utf-8", newline="\n")
        print(f"wrote the hashes of {len(plants)} plant files to {args.frozen_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
