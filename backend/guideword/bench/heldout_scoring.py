"""The held-out automatic score (Phase 6 spec P6-9; acceptance 6).

Supersedes R26's "IDs are never matched" for held-out keys only: the template defines the key's
`component_ids` as plant-file IDs. A line **auto-matches** when it names at least one of the
key's components **and** contains at least one of its `match_phrases`, after the test #5
normalisation (NFC, dashes, case, whitespace; hyphens read as spaces). A Guideword line names
its failing components, a chain its links' objects and failing components, a hypothesis its
components; a baseline line its `equipment` or, as written, its text. Any ID renamed under
P6-12 is applied to the key through `fixes.md`, one rename per line: `- rename: OLD -> NEW`.

Reported as "automatic", never the headline. Also: **found anywhere**, the first matching rank
in Guideword's full list, beside the top-10 result (the coverage claim).

**Guideword's list** is the final shortlist the product shows (findings, chains and
hypotheses, in the server's order), written by the runner as `shortlist.json` with each
finding's failing components; this is where a chain link can name a key component (P6-9).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guideword.bench.scoring import _norm

DASH = " — "
# the old name is the key's, as written, and may hold spaces ("Tank A"); the new one is a plant ID
_RENAME = re.compile(r"^\s*-\s*rename:\s*(\S(?:.*?\S)?)\s*->\s*(\S+)\s*$")


@dataclass(frozen=True)
class Line:
    rank: int
    text: str
    components: list[str]


def read_renames(fixes: Path) -> dict[str, str]:
    """`fixes.md`'s ID renames, old -> new; any other kind of fix is not an ID rename."""
    if not fixes.is_file():
        return {}
    renames: dict[str, str] = {}
    for line in fixes.read_text(encoding="utf-8").splitlines():
        match = _RENAME.match(line)
        if match is not None:
            renames[match.group(1)] = match.group(2)
    return renames


def _object(link: str) -> str:
    return link.split(".", 1)[0]


def guideword_lines(shortlist: Mapping[str, Any], causes: Mapping[str, str]) -> list[Line]:
    """Each shortlist item as a line: its words and the components it names."""
    failing: Mapping[str, list[str]] = shortlist.get("finding_components", {})
    lines: list[Line] = []
    for item in shortlist["items"]:
        kind = item["target_kind"]
        if kind == "finding":
            f = item["finding"]
            cause = f.get("cause_text") or causes.get(f["cause_id"], f["cause_id"])
            text, components = f"{cause}{DASH}{f['consequence']}", list(f["failing_component_ids"])
        elif kind == "chain":
            chain = item["chain"]
            text = chain.get("description") or ""
            components = []
            for link in chain["links"]:
                named = failing.get(link) if link.startswith("f:") else [_object(link)]
                components += [c for c in named or [] if c not in components]
        else:
            h = item["hypothesis"]
            text, components = f"{h['mechanism']}{DASH}{h['consequence']}", list(h["component_ids"])
        lines.append(Line(item["rank"], text, components))
    return lines


def baseline_lines(record: Mapping[str, Any]) -> list[Line]:
    return [Line(h["rank"], h["hazard"], list(h["equipment"])) for h in record["hazards"]]


def _names(line: Line, component: str) -> bool:
    if component in line.components:
        return True
    pattern = rf"(?<![\w-]){re.escape(component)}(?![\w-])"
    texts = [line.text, *line.components]
    return any(re.search(pattern, t, re.IGNORECASE) for t in texts)


def line_auto_matches(line: Line, components: Sequence[str], phrases: Sequence[str]) -> bool:
    text = _norm(line.text)
    return any(_names(line, c) for c in components) and any(_norm(p) in text for p in phrases)


def first_auto_match(
    lines: Sequence[Line], components: Sequence[str], phrases: Sequence[str]
) -> int | None:
    return next((x.rank for x in lines if line_auto_matches(x, components, phrases)), None)
