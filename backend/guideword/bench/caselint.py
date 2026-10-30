"""Case lint (Phase 9 spec 9.0): what a "before the accident" package must not say.

A benchmark package describes the plant as it stood before the accident, with neutral identities
and no hints (`docs/case-template.md` section 2). This lint flags, by line, the things that give
a case away or date it: a **year**, a **company**-like name, a **place** written as "Town,
Region", and the terms of `reference/case_lint_terms.csv`, which come in three kinds:
`outcome` (what happened), `hint` (words that point at the answer) and `investigator` (the
language and the names of investigating bodies). Word lists and patterns only; no model.
Shown to the case writer for the second-person check; it never edits a file.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field

from guideword.reference.loader import DEFAULT_REFERENCE_DIR, _read, _unique
from guideword.reference.tables import Source, _Row

LINT_TERMS = "case_lint_terms.csv"
LINT_HEADER = ("term", "kind", "source")
TermKind = Literal["outcome", "hint", "investigator"]
FlagKind = Literal["year", "company", "place", "outcome", "hint", "investigator"]

# a year needs a date context: a preposition or a month before it, or punctuation or the line's
# end after it; "design pressure 1950 kPa" is a value, not a year
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_YEAR = re.compile(
    rf"\b(?:in|of|since|from|until|by|before|after|during|year|early|late|mid|circa"
    rf"|(?:\d{{1,2}} )?(?:{_MONTHS})\.?) +(19[5-9]\d|20[0-4]\d)(?![\w.,/-])"
    r"|(?<![\w.,/-])(19[5-9]\d|20[0-4]\d)(?=[.,;:)]|$)"
)
_SUFFIXES = (
    "Inc|Ltd|LLC|LP|Corp|Corporation|Company|Co|GmbH|AG|SA|SpA|BV|NV|Plc|Pty|Refinery|"
    "Chemicals|Chemical|Industries|Petroleum|Polymers|Energy|Olefins"
)
_COMPANY = re.compile(rf"\b((?:[A-Z][A-Za-z&'.-]+ )+(?:{_SUFFIXES}))\b\.?")
# "Geismar, Louisiana": two capitalised words joined by a comma, not at a line start
_PLACE = re.compile(r"(?<=[a-z] )([A-Z][a-z]+(?: [A-Z][a-z]+)?, [A-Z][a-z]+(?: [A-Z][a-z]+)?)\b")


class LintTerm(_Row):
    term: str = Field(min_length=1)
    kind: TermKind
    source: Source


@dataclass(frozen=True)
class Flag:
    line: int
    kind: FlagKind
    text: str


def load_lint_terms(directory: Path | None = None) -> tuple[LintTerm, ...]:
    """The shipped terms, loaded outside the ReferenceSet (they are not part of a run)."""
    root = directory if directory is not None else DEFAULT_REFERENCE_DIR
    rows, _ = _read(root, LINT_TERMS, LintTerm, LINT_HEADER)
    _unique(LINT_TERMS, [row.term.casefold() for row in rows])
    return rows


def _term_pattern(term: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in term.split())
    return re.compile(rf"(?<![\w-]){words}(?![\w-])", re.IGNORECASE)


def lint_text(text: str, terms: Sequence[LintTerm]) -> list[Flag]:
    """Every flag in the text, in line order, then by position; a clean text gives []."""
    patterns = [(t.kind, _term_pattern(t.term)) for t in terms]
    flags: list[tuple[int, int, Flag]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _YEAR.finditer(line):
            group = 1 if match.group(1) else 2
            flags.append((number, match.start(group), Flag(number, "year", match.group(group))))
        for match in _COMPANY.finditer(line):
            flags.append((number, match.start(), Flag(number, "company", match.group(1))))
        for match in _PLACE.finditer(line):
            flags.append((number, match.start(), Flag(number, "place", match.group(1))))
        for kind, pattern in patterns:
            for match in pattern.finditer(line):
                flags.append((number, match.start(), Flag(number, kind, match.group(0))))
    return [flag for _, _, flag in sorted(flags, key=lambda x: (x[0], x[1], x[2].kind))]


def lint_file(path: Path, terms: Sequence[LintTerm]) -> list[Flag]:
    return lint_text(path.read_text(encoding="utf-8"), terms)
