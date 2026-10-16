"""The test #5 automatic score (spec 2.10; plan R26a, R26c).

A ranked line matches the case's key when every phrase group has at least one of its
phrases in that line. Text is compared after `ids.normalise_text` (NFC, Unicode dashes to
`-`, non-breaking spaces, whitespace, case) with hyphens then read as spaces, so "dead-leg"
and "dead leg" are the same. Only the agent's own words are passed in; IDs never are.
"""

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from guideword.schema import ids

NOTE = "_note"
TOP_3 = 3
TOP_10 = 10
Bucket = Literal["top3", "top10", "missed"]
_CASE = re.compile(r"^case_([a-z])(?:_|$)")


def case_letter(name: str) -> str:
    """`case_g_batch_plant` and `case_g` are both case `g`."""
    match = _CASE.match(name)
    if match is None:
        raise ValueError(f"{name} is not a case name (case_<letter>...)")
    return match.group(1)


def load_keys(path: Path) -> dict[str, list[list[str]]]:
    """The match groups per case letter; the `_note` entry is skipped."""
    data = json.loads(path.read_text(encoding="utf-8"))
    keys: dict[str, list[list[str]]] = {}
    for name, entry in data.items():
        if name == NOTE:
            continue
        groups = entry.get("match")
        if not groups or not all(isinstance(g, list) and g for g in groups):
            raise ValueError(f"{name} has no match groups")
        keys[case_letter(name)] = [[str(p) for p in g] for g in groups]
    return keys


def _norm(text: str) -> str:
    return " ".join(ids.normalise_text(text).replace("-", " ").split())


def line_matches(line: str, groups: Sequence[Sequence[str]]) -> bool:
    text = _norm(line)
    return all(any(_norm(phrase) in text for phrase in group) for group in groups)


def first_match(lines: Sequence[str], groups: Sequence[Sequence[str]]) -> int | None:
    """The 1-based rank of the first matching line."""
    return next((i for i, line in enumerate(lines, start=1) if line_matches(line, groups)), None)


def bucket(rank: int | None) -> Bucket:
    if rank is not None and rank <= TOP_3:
        return "top3"
    if rank is not None and rank <= TOP_10:
        return "top10"
    return "missed"
