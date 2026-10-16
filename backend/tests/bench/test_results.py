"""Test #5 scoring per case, the hand-score sheet and the results table (spec 2.10; plan
R26c, R35, R38). Everything is read from the run outputs; a missing score is never filled."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.results import (
    HAND_SCORES,
    SCORES,
    render_results,
    score_case,
    update_hand_sheet,
)

GROUPS = [["chlorine"], ["dead leg"]]


def line(rank: int, text: str, question_id: str = "q:x", component: str = "L-1") -> dict[str, Any]:
    return {
        "rank": rank,
        "text": text,
        "question_id": question_id,
        "failing_component_ids": [component],
        "finding_id": f"f:{rank}",
    }


def write_5b(
    root: Path, letter: str, ranked: list[dict[str, Any]], status: str = "finished"
) -> None:
    (root / "5b").mkdir(parents=True, exist_ok=True)
    report = {
        "case": f"case_{letter}",
        "run_id": "run:abc",
        "status": status,
        "spent_usd": 0.31,
        "cap_spent_usd": 0.31,
        "seconds": 120.0,
        "ranked": ranked,
    }
    (root / "5b" / f"case_{letter}.json").write_text(json.dumps(report), encoding="utf-8")


def write_5a(root: Path, letter: str, texts: list[str], outcome: str = "ok") -> None:
    (root / "5a").mkdir(parents=True, exist_ok=True)
    record = {
        "case": f"case_{letter}",
        "outcome": outcome,
        "cost_usd": 0.04,
        "seconds": 30.0,
        "hazards": [
            {"rank": i, "hazard": t, "equipment": [], "reason": "r"}
            for i, t in enumerate(texts, start=1)
        ],
    }
    (root / "5a" / f"case_{letter}.json").write_text(json.dumps(record), encoding="utf-8")


def test_5b_and_5a_are_scored_on_their_own_words(tmp_path: Path) -> None:
    write_5b(
        tmp_path, "g", [line(1, "pump trips — no flow"), line(2, "chlorine — dead leg rupture")]
    )
    write_5a(tmp_path, "g", ["a", "b", "c", "chlorine sits in a dead-leg"])
    scored = score_case("g", GROUPS, tmp_path)
    assert scored["5b"] == {
        "status": "finished",
        "scored": True,
        "rank": 2,
        "bucket": "top3",
        "line": "chlorine — dead leg rupture",
    }
    assert scored["5a"]["rank"] == 4 and scored["5a"]["bucket"] == "top10"


def test_ids_are_never_matched(tmp_path: Path) -> None:
    """A line whose only hit is in its IDs does not match (R26c)."""
    write_5b(
        tmp_path,
        "g",
        [line(1, "valve left open — release", "pair:CHLORINE-X:SIH", "DEAD-LEG-1")],
    )
    assert score_case("g", GROUPS, tmp_path)["5b"]["bucket"] == "missed"


def test_a_run_stopped_at_a_cap_is_reported_not_scored(tmp_path: Path) -> None:
    write_5b(tmp_path, "d", [line(1, "chlorine — dead leg")], status="stopped_cap")
    scored = score_case("d", GROUPS, tmp_path)["5b"]
    assert scored["scored"] is False and scored["status"] == "stopped_cap"
    assert "rank" not in scored


def test_a_configuration_not_run_says_so(tmp_path: Path) -> None:
    write_5a(tmp_path, "e", [], outcome="invalid")
    scored = score_case("e", GROUPS, tmp_path)
    assert scored["5b"] == {"status": "not run", "scored": False}
    assert scored["5a"]["scored"] is False and scored["5a"]["status"] == "invalid"


def _rows(root: Path) -> list[dict[str, str]]:
    with (root / HAND_SCORES).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_hand_sheet_lists_the_top_10_with_ids_for_5b_and_keeps_filled_scores(
    tmp_path: Path,
) -> None:
    write_5b(tmp_path, "g", [line(i, f"line {i}") for i in range(1, 13)])
    write_5a(tmp_path, "g", ["h1", "h2"])
    assert update_hand_sheet(tmp_path, ["g"]) == []
    rows = _rows(tmp_path)
    assert [(r["config"], r["rank"]) for r in rows] == [("5a", "1"), ("5a", "2")] + [
        ("5b", str(i)) for i in range(1, 11)
    ]
    first_5b = rows[2]
    assert (first_5b["text"], first_5b["question_id"], first_5b["component_ids"]) == (
        "line 1",
        "q:x",
        "L-1",
    )
    assert all(r["score"] == "" for r in rows)

    # Bhargavi scores a line; a re-run changes another line and the scored one
    rows[2]["score"], rows[2]["reason"] = "hit", "names the cause"
    with (tmp_path / HAND_SCORES).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_5b(
        tmp_path, "g", [line(1, "line 1 changed"), *[line(i, f"new {i}") for i in range(2, 11)]]
    )
    stale = update_hand_sheet(tmp_path, ["g"])
    after = {(r["config"], r["rank"]): r for r in _rows(tmp_path)}
    assert after[("5b", "1")]["score"] == "hit"  # never overwritten
    assert after[("5b", "1")]["text"] == "line 1"
    assert stale == [("g", "5b", 1)]
    assert after[("5b", "2")]["text"] == "new 2"


def _results(tmp_path: Path, hand: list[dict[str, str]] | None = None) -> str:
    write_5b(tmp_path, "g", [line(1, "pump trips"), line(2, "chlorine — dead leg")])
    write_5a(tmp_path, "g", ["nothing"])
    scores = {"g": score_case("g", GROUPS, tmp_path)}
    (tmp_path / SCORES).write_text(json.dumps(scores), encoding="utf-8")
    update_hand_sheet(tmp_path, ["g"])
    if hand is not None:
        rows = _rows(tmp_path)
        for row in rows:
            for fill in hand:
                if (row["config"], row["rank"]) == (fill["config"], fill["rank"]):
                    row.update(fill)
        with (tmp_path / HAND_SCORES).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return render_results(tmp_path)


def test_results_table_generated_from_records(tmp_path: Path) -> None:
    text = _results(tmp_path)
    assert "| case_g | 5B | finished | 2 | top3 | not scored | 0.3100 | 120 |" in text
    assert "| case_g | 5A | ok | - | missed | not scored | 0.0400 | 30 |" in text
    assert "Kill test #4" in text and "Four-tier comparison" in text
    assert "Generated by scripts/test5_results.py" in text


def test_results_read_hand_scores_and_never_invent_them(tmp_path: Path) -> None:
    text = _results(
        tmp_path,
        hand=[
            {"config": "5b", "rank": "1", "score": "miss"},
            {"config": "5b", "rank": "2", "score": "hit", "reason": "the cause"},
        ],
    )
    assert "| case_g | 5B | finished | 2 | top3 | hit at 2 (top3) |" in text
    assert "| case_g | 5A | ok | - | missed | not scored |" in text


def test_an_unknown_hand_score_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="good"):
        _results(tmp_path, hand=[{"config": "5b", "rank": "1", "score": "good"}])
