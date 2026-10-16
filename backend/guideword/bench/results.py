"""Test #5 per case: the automatic score, the hand-score sheet and the results table (spec
2.10; plan R26c, R35, R38).

Everything here is read from the run outputs under `bench/test5/`: the 5B reports written by
`run_case.py`, the 5A records, `scores.json`, and the sheets Bhargavi fills. Nothing is typed
into the table, and a score that is not in a sheet is shown as "not scored".
"""

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from guideword.bench.scoring import TOP_10, bucket, first_match

SCORES = "scores.json"
HAND_SCORES = "hand_scores.csv"
HAND_FIELDS = ["case", "config", "rank", "text", "question_id", "component_ids", "score", "reason"]
HAND_VALUES = {"hit", "partial", "miss"}
KILL4_SUMMARY = Path("kill4") / "summary.json"
FOUR_TIER_SUMMARY = Path("four_tier") / "summary.json"
FINISHED = "finished"
OK = "ok"
CONFIGS = {"5b": "5B", "5a": "5A"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _5b(root: Path, letter: str) -> Any:
    return _read(root / "5b" / f"case_{letter}.json")


def _5a(root: Path, letter: str) -> Any:
    return _read(root / "5a" / f"case_{letter}.json")


def _lines(config: str, record: Any) -> list[dict[str, Any]]:
    """The ranked lines in the agent's own words, with the IDs for the hand sheet."""
    if config == "5b":
        return [
            {
                "rank": r["rank"],
                "text": r["text"],
                "question_id": r["question_id"],
                "component_ids": " ".join(r["failing_component_ids"]),
            }
            for r in record["ranked"]
        ]
    return [
        {"rank": h["rank"], "text": h["hazard"], "question_id": "", "component_ids": ""}
        for h in record["hazards"]
    ]


def _scored(record: Any, config: str, groups: Sequence[Sequence[str]]) -> dict[str, Any]:
    if record is None:
        return {"status": "not run", "scored": False}
    status = record["status"] if config == "5b" else record["outcome"]
    if status != (FINISHED if config == "5b" else OK):
        # R38: a run stopped by a cap is reported, not scored, until Bhargavi decides
        return {"status": status, "scored": False}
    lines = _lines(config, record)
    rank = first_match([line["text"] for line in lines], groups)
    result: dict[str, Any] = {
        "status": status,
        "scored": True,
        "rank": rank,
        "bucket": bucket(rank),
    }
    result["line"] = lines[rank - 1]["text"] if rank is not None else None
    return result


def score_case(letter: str, groups: Sequence[Sequence[str]], root: Path) -> dict[str, Any]:
    return {
        "5b": _scored(_5b(root, letter), "5b", groups),
        "5a": _scored(_5a(root, letter), "5a", groups),
    }


def _hand_rows(root: Path) -> list[dict[str, str]]:
    path = root / HAND_SCORES
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["score"] and row["score"] not in HAND_VALUES:
            raise ValueError(
                f"{HAND_SCORES}: case {row['case']} {row['config']} rank {row['rank']} has score "
                f"{row['score']!r}; use one of {sorted(HAND_VALUES)}"
            )
    return rows


def update_hand_sheet(root: Path, letters: Iterable[str]) -> list[tuple[str, str, int]]:
    """Add a blank row for each top-10 line not in the sheet. A row with a score is never
    changed; when its line has changed since, it is returned as stale for Bhargavi."""
    rows = {(r["case"], r["config"], int(r["rank"])): r for r in _hand_rows(root)}
    stale = []
    for letter in letters:
        for config, record in (("5a", _5a(root, letter)), ("5b", _5b(root, letter))):
            if record is None:
                continue
            for line in _lines(config, record)[:TOP_10]:
                key = (letter, config, int(line["rank"]))
                existing = rows.get(key)
                fresh = {"case": letter, "config": config, **line, "score": "", "reason": ""}
                fresh["rank"] = str(line["rank"])
                if existing is not None and existing["score"]:
                    if existing["text"] != line["text"]:
                        stale.append(key)
                    continue
                rows[key] = fresh
    path = root / HAND_SCORES
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HAND_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[k] for k in sorted(rows))
    return stale


def _hand(rows: list[dict[str, str]]) -> str:
    scored = sorted((int(r["rank"]), r["score"]) for r in rows if r["score"])
    hit = next((rank for rank, score in scored if score == "hit"), None)
    if hit is not None:
        return f"hit at {hit} ({bucket(hit)})"
    if not scored:
        return "not scored"
    if len(scored) < len(rows):
        return f"not scored ({len(scored)} of {len(rows)})"
    partial = next((rank for rank, score in scored if score == "partial"), None)
    return f"partial at {partial}" if partial is not None else "missed"


def _summary(root: Path, path: Path, title: str, missing: str) -> list[str]:
    data = _read(root / path)
    lines = ["", f"## {title}", ""]
    if data is None:
        return [*lines, missing]
    return [*lines, "```json", json.dumps(data, indent=1, ensure_ascii=False), "```"]


def render_results(root: Path) -> str:
    scores: dict[str, Any] = _read(root / SCORES) or {}
    hand = _hand_rows(root)
    out = [
        "# Test #5 results",
        "",
        "Generated by scripts/test5_results.py from the run outputs under bench/test5/; "
        "never edited by hand. Hand scores come from hand_scores.csv.",
        "",
        "| Case | Config | Status | Auto rank | Auto | Hand | Cost (USD) | Time (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total = 0.0
    for letter in sorted(scores):
        for config, label in CONFIGS.items():
            score = scores[letter][config]
            record = _5b(root, letter) if config == "5b" else _5a(root, letter)
            if score["scored"]:
                rank = "-" if score["rank"] is None else str(score["rank"])
                auto = score["bucket"]
            else:
                rank, auto = "-", "not scored"
            rows = [r for r in hand if r["case"] == letter and r["config"] == config]
            cost = record.get("spent_usd", record.get("cost_usd")) if record else None
            seconds = record.get("seconds") if record else None
            total += cost or 0.0
            out.append(
                f"| case_{letter} | {label} | {score['status']} | {rank} | {auto} | "
                f"{_hand(rows)} | {'-' if cost is None else f'{cost:.4f}'} | "
                f"{'-' if seconds is None else f'{seconds:.0f}'} |"
            )
    out += ["", f"**Paid for these runs:** ${total:.4f}."]
    out += _summary(
        root, KILL4_SUMMARY, "Kill test #4", "Not reported yet (scripts/kill4.py, PR 12b)."
    )
    out += _summary(
        root, FOUR_TIER_SUMMARY, "Four-tier comparison", "Not run yet (four_tier, PR 12b)."
    )
    return "\n".join(out) + "\n"
