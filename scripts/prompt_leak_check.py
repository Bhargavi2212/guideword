"""Check that a prompt's new lines carry no answer key's words. No calls.

  python scripts/prompt_leak_check.py --prompt prompts/plant_screen/v1.md `
      --baseline prompts/test5a/v1.md --keys cases/dev/keys/answer_keys.json

Only Bhargavi runs it on a real key; Claude Code wrote it against the key formats alone (the
dev key's `match`, `memorization_markers`, `actual_event`, `source`; the held-out template's
`match_phrases`, `component_ids`, `cause_ids`, `root_cause`, `consequence`,
`missed_by_original_review`) and never read a key.

The lines checked are the prompt's lines that are not in the baseline. Per case:
- **fail**: a key ID as a whole token, a memorisation marker, or a key phrase of two or more
  words, in a checked line;
- **review**: a one-word key phrase, or a distinctive word (five letters or more, not a
  common word) of the key's prose, in a checked line.

The output gives counts and prompt line numbers only, so it can be shared without showing the
key; `--show` also prints the matched terms. Exit code 1 when any case has a fail.
"""

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from guideword.schema import ids

PHRASE_FIELDS = ("match_phrases",)
MARKER_FIELDS = ("memorization_markers",)
ID_FIELDS = ("component_ids", "cause_ids")
PROSE_FIELDS = ("actual_event", "root_cause", "consequence", "missed_by_original_review", "source")
COMMON = frozenset(
    [
        "about", "above", "after", "again", "against", "along", "among", "another", "around",
        "based", "being", "below", "between", "cause", "caused", "causes", "could", "during",
        "every", "first", "found", "given", "having", "hazard", "hazards", "inside", "later",
        "least", "might", "never", "other", "plant", "should", "since", "their", "there",
        "these", "those", "three", "through", "under", "until", "using", "where", "which",
        "while", "whole", "would",
    ]
)  # fmt: skip


def _norm(text: str) -> str:
    return " ".join(ids.normalise_text(text).replace("-", " ").split())


def _has(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_norm(term))}(?![a-z0-9])", text) is not None


def _has_id(line: str, key_id: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_-]){re.escape(key_id)}(?![A-Za-z0-9_-])"
    return re.search(pattern, line, re.IGNORECASE) is not None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


def load_cases(path: Path) -> dict[str, dict[str, Any]]:
    """Either key shape: an object of cases (dev, `_note` skipped) or a list of objects with a
    `case_id` (held-out template)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(entry["case_id"]): entry for entry in data}
    return {name: entry for name, entry in data.items() if not name.startswith("_")}


def terms(entry: dict[str, Any]) -> dict[str, list[str]]:
    phrases = [p for g in entry.get("match", []) for p in _strings(g)]
    phrases += [p for f in PHRASE_FIELDS for p in _strings(entry.get(f))]
    prose = " ".join(s for f in PROSE_FIELDS for s in _strings(entry.get(f)))
    words = sorted(
        {w for w in re.findall(r"[a-z0-9]+", _norm(prose)) if len(w) >= 5 and w not in COMMON}
    )
    return {
        "fail_phrase": [p for p in phrases if len(_norm(p).split()) >= 2],
        "marker": [m for f in MARKER_FIELDS for m in _strings(entry.get(f))],
        "id": [i for f in ID_FIELDS for i in _strings(entry.get(f))],
        "review_phrase": [p for p in phrases if len(_norm(p).split()) == 1],
        "word": words,
    }


def added_lines(prompt: str, baseline: str) -> list[tuple[int, str]]:
    seen = {line.strip() for line in baseline.splitlines()}
    return [
        (number, line)
        for number, line in enumerate(prompt.splitlines(), start=1)
        if line.strip() and line.strip() not in seen
    ]


def check(
    lines: Iterable[tuple[int, str]], entry: dict[str, Any]
) -> dict[str, list[tuple[int, str]]]:
    """(line number, term) hits per level."""
    found = terms(entry)
    hits: dict[str, list[tuple[int, str]]] = {"fail": [], "review": []}
    for number, line in lines:
        text = _norm(line)
        for term in found["fail_phrase"] + found["marker"]:
            if _has(text, term):
                hits["fail"].append((number, term))
        hits["fail"] += [(number, i) for i in found["id"] if _has_id(line, i)]
        for term in sorted(set(found["review_phrase"]) | set(found["word"])):
            if _has(text, term):
                hits["review"].append((number, term))
    return hits


def _where(hits: Sequence[tuple[int, str]]) -> str:
    numbers = sorted({n for n, _ in hits})
    return f" (line {', '.join(map(str, numbers))})" if numbers else ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--show", action="store_true", help="also print the matched terms")
    args = parser.parse_args(argv)
    lines = added_lines(
        args.prompt.read_text(encoding="utf-8"), args.baseline.read_text(encoding="utf-8")
    )
    print(f"{args.prompt}: {len(lines)} lines not in {args.baseline.name} checked")
    failed = False
    for name, entry in sorted(load_cases(args.keys).items()):
        hits = check(lines, entry)
        failed = failed or bool(hits["fail"])
        print(
            f"  {name}: fail {len(hits['fail'])}{_where(hits['fail'])}, "
            f"review {len(hits['review'])}{_where(hits['review'])}"
        )
        if args.show:
            for level in ("fail", "review"):
                for number, term in hits[level]:
                    print(f"    {level} line {number}: {term}")
    print("FAIL: key words in the new lines" if failed else "no fail-level match")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
