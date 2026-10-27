"""Blind sheets for the human score, and the second grader's packets (Phase 6 spec P6-10; plan G8;
acceptance 7).

**A sheet per case**, `<out>/sheets/<case>.csv` (`case,label,rank,text,equipment,score,reason`):
each configuration's top 10 lines under a label X, Y or Z, every line rendered the same way:
plain text and the equipment's tags. The labels' order is fixed by `h(case_id)`, so it differs
from case to case and can't be learnt; the mapping goes to `<out>/blind_map.json`, opened only
after grading. A sheet is written once and never overwritten.

**Record keys become names** in a line's text, so nothing tells Guideword's lines apart: a finding
or question key becomes its object and words (`f:m:S-EA-425B:more:pressure:…` → `EA-425B more
pressure`), a step key the step and its word, a chain key its named parts, a fact ID its object and
field (`HV-B-SIN.normal_position` → `HV-B-SIN normal position`). Each substitution keeps the
text it replaced, so undoing every one gives back the stored text exactly (tested).

**The second grader** (a fresh Claude session) gets `<out>/grader2/<case>.md`: only the key's
`root_cause`, `component_ids` and `missed_by_original_review`, and the three blind lists; and an
empty sheet of its own in `<out>/sheets_grader2/`.
"""

import csv
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guideword.bench.heldout_scoring import Line
from guideword.bench.runner import CONFIGS
from guideword.schema import ids

LABELS = ("X", "Y", "Z")
TOP = 10
COLUMNS = ("case", "label", "rank", "text", "equipment", "score", "reason")
PACKET_FIELDS = ("root_cause", "component_ids", "missed_by_original_review")

# a record key: its prefix, then everything up to a space or closing punctuation
_KEY = re.compile(
    r"\b(f|m|proc|pair|env|relief|work|eng|ch|hyp|ev|lopa|rec):[^\s,;()\[\]]*[^\s,;.()\[\]]"
)
# a fact ID: an object ID, a dot, a snake_case field (and nested fields)
_FACT = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\.([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)\b")
_HASH = re.compile(r"^[0-9a-f]{16}$|^C\d+$|^(super|ultra|lightning|nano)$")


@dataclass(frozen=True)
class Shown:
    """A line's text with its keys named, and each substitution's span and original text."""

    text: str
    swaps: tuple[tuple[int, int, str], ...]


def _question_words(parts: Sequence[str]) -> str:
    kind, rest = parts[0], [p for p in parts[1:] if not _HASH.match(p)]
    if kind in ("f", "m") and rest and rest[0].startswith("S-"):
        return " ".join([rest[0].removeprefix("S-"), *rest[1:]]).replace("~", " ").replace("_", " ")
    if kind == "f":
        return _question_words(rest) if rest else "a finding"
    if kind == "pair" and len(rest) >= 2:
        return f"{rest[0]} and {rest[1]}"
    if kind == "env" and len(rest) >= 2:
        return f"{rest[0]} with {rest[1]}"
    if kind == "relief" and rest:
        return f"{rest[0]} relief"
    return " ".join(rest).replace("_", " ") or kind


def _name(key: str) -> str:
    if key.startswith("ch:"):
        return " and ".join(_name(link) for link in key[3:].split("+"))
    fact = _FACT.fullmatch(key)
    if fact is not None:
        return f"{fact.group(1)} {fact.group(2).replace('.', ' ').replace('_', ' ')}"
    parts = key.split(":")
    if parts[0] == "f" and len(parts) > 1:
        return _question_words(parts[1:])
    return _question_words(parts)


def substitute_keys(text: str) -> Shown:
    out: list[str] = []
    swaps: list[tuple[int, int, str]] = []
    at = 0
    length = 0
    matches = sorted(
        [*_KEY.finditer(text), *_FACT.finditer(text)], key=lambda m: (m.start(), -m.end())
    )
    for match in matches:
        if match.start() < at:
            continue  # inside a key already named
        out.append(text[at : match.start()])
        length += match.start() - at
        named = _name(match.group(0))
        swaps.append((length, length + len(named), match.group(0)))
        out.append(named)
        length += len(named)
        at = match.end()
    out.append(text[at:])
    return Shown("".join(out), tuple(swaps))


def undo(shown: Shown) -> str:
    """The stored text: every substitution reversed."""
    text = shown.text
    for start, end, original in reversed(shown.swaps):
        text = text[:start] + original + text[end:]
    return text


def blind_order(case: str) -> list[str]:
    """The configurations in label order X, Y, Z for this case, fixed by `h(case_id)`."""
    return sorted(CONFIGS, key=lambda name: ids.h({"case": case, "config": name}))


def _rows(case: str, lines: Mapping[str, Sequence[Line]]) -> list[dict[str, str]]:
    rows = []
    for label, name in zip(LABELS, blind_order(case), strict=True):
        for line in list(lines.get(name, []))[:TOP]:
            rows.append(
                {
                    "case": case,
                    "label": label,
                    "rank": str(line.rank),
                    "text": substitute_keys(line.text).text,
                    "equipment": ", ".join(line.components),
                    "score": "",
                    "reason": "",
                }
            )
    return rows


def _write_sheet(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    if path.exists():
        raise FileExistsError(f"{path.name} exists; a sheet is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _packet(case: str, rows: Sequence[Mapping[str, str]], key: Mapping[str, Any]) -> str:
    parts = [f"# Case {case.upper()}: second grader", "", "## The answer key (these fields only)"]
    for name in PACKET_FIELDS:
        value = key[name]
        shown = ", ".join(value) if isinstance(value, list) else str(value)
        parts.append(f"- **{name}**: {shown}")
    for label in LABELS:
        parts += ["", f"## List {label}", ""]
        parts += [
            f"{r['rank']}. {r['text']} (equipment: {r['equipment'] or '—'})"
            for r in rows
            if r["label"] == label
        ]
    return "\n".join(parts) + "\n"


def write_case_sheets(
    case: str, lines: Mapping[str, Sequence[Line]], key: Mapping[str, Any], out: Path
) -> None:
    rows = _rows(case, lines)
    _write_sheet(out / "sheets" / f"{case}.csv", rows)
    _write_sheet(out / "sheets_grader2" / f"{case}.csv", rows)
    packet = out / "grader2" / f"{case}.md"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(_packet(case, rows, key), encoding="utf-8", newline="\n")
    mapping_path = out / "blind_map.json"
    mapping: dict[str, dict[str, str]] = (
        json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.is_file() else {}
    )
    mapping[case] = dict(zip(LABELS, blind_order(case), strict=True))
    mapping_path.write_text(
        json.dumps(mapping, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
