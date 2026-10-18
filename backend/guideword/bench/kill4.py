"""Kill test #4, reported and never re-scored (spec 2.10; plan R26b, R37).

The results JSONL holds no answer-key text (R26b); its `score.rank` is the rank of the real
accident recorded by the kill test's own, older automatic match rule, or null when it was not in
the top 10. This module copies those ranks as recorded. The #4 configuration is Ultra; a case
Ultra recognised (`recognized_incident`) is excluded (case H). Nano's rows are kept apart as not
the #4 configuration. The answers and the models' incident guesses (`probe`) are never carried
into the summary. The hand review is quoted from PROJECT.md §20.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ULTRA_MARK = "Ultra"
DRY_MODEL = "dry-model"
TOP_3 = 3
AUTOMATIC_LABEL = "automatic, older match rule (not hand/grader-scored)"
HAND_REVIEW = (
    "Ultra: real cause in top 3 on 2 of 4 unrecognised cases (3 counting the under-ranked "
    "dead leg); missed the chemical pair. Nano 0 of 5. (PROJECT.md §20, Bhargavi's hand review)"
)


def load_run(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def is_dry_run(rows: Sequence[dict[str, Any]]) -> bool:
    return bool(rows) and all(r.get("model") == DRY_MODEL for r in rows)


def _line(r: dict[str, Any], excluded: bool) -> dict[str, Any]:
    return {
        "case": r["case"],
        "rank": (r.get("score") or {}).get("rank"),
        "recognised": bool(r.get("recognized_incident")),
        "excluded": excluded,
        "finish_reason": r.get("finish_reason"),
    }


def summarise(rows: Sequence[dict[str, Any]], *, run: str) -> dict[str, Any]:
    ultra = [
        _line(r, excluded=bool(r.get("recognized_incident")))
        for r in rows
        if ULTRA_MARK in str(r.get("model"))
    ]
    others = [_line(r, excluded=False) for r in rows if ULTRA_MARK not in str(r.get("model"))]
    counted = [u for u in ultra if not u["excluded"]]
    top3 = sum(1 for u in counted if u["rank"] is not None and u["rank"] <= TOP_3)
    return {
        "run": run,
        "label": AUTOMATIC_LABEL,
        "ultra": sorted(ultra, key=lambda u: u["case"]),
        "ultra_top3_unrecognised": f"{top3} of {len(counted)}",
        "nano_not_the_4_configuration": sorted(others, key=lambda u: u["case"]),
        "hand_review": HAND_REVIEW,
    }
