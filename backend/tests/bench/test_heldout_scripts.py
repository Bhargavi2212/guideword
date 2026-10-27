"""The scoring scripts end to end on a synthetic output folder (Phase 6 spec 6.5; P6-3 steps 5-6):
auto-score, blind sheets, then results, which refuse until every row is scored."""

import csv
import json
from pathlib import Path
from typing import Any

import heldout_results
import heldout_score
import heldout_sheets

SECRET = "SENTINEL-secret"
FREEZE = {"freeze_tag": "phase6-freeze", "freeze_commit": "b" * 40}


def _key() -> dict[str, Any]:
    return {
        "case_id": "case_k",
        "root_cause": "The valve was left closed.",
        "component_ids": ["V-1"],
        "cause_ids": ["C15"],
        "match_phrases": ["left closed"],
        "consequence": SECRET,
        "missed_by_original_review": "The startup step.",
        "multi_failure": False,
        "source": {"reference": SECRET},
    }


def _out(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "heldout"
    case = out / "case_k"
    (case / "5a").mkdir(parents=True)
    (case / "baseline_b").mkdir()
    finding = {
        "id": "f:m:S-T-1:no:flow:lightning:C15:aaaaaaaaaaaaaaaa",
        "cause_id": "outside_library",
        "cause_text": "V-1 left closed after the outage",
        "consequence": "the tank overpressures",
        "failing_component_ids": ["V-1"],
    }
    shortlist = {
        "run_id": "run:k",
        "items": [
            {
                "rank": 1,
                "target_id": "f:x",
                "target_kind": "finding",
                "finding": finding | {"cause_text": "pump trips", "failing_component_ids": ["P-1"]},
            },
            {"rank": 2, "target_id": finding["id"], "target_kind": "finding", "finding": finding},
        ],
        "finding_components": {finding["id"]: ["V-1"]},
    }
    (case / "shortlist.json").write_text(json.dumps(shortlist), encoding="utf-8")
    hazards = {
        "hazards": [{"rank": 1, "hazard": "the pump trips", "equipment": ["P-1"], "reason": "r"}]
    }
    (case / "5a" / "case_k.json").write_text(json.dumps(hazards), encoding="utf-8")
    (case / "baseline_b" / "case_k.json").write_text(json.dumps(hazards), encoding="utf-8")
    report = {"coverage": [{"list": "matrix", "checked": 9, "total": 10, "unsure": 1, "failed": 0}]}
    (case / "guideword.json").write_text(json.dumps(report), encoding="utf-8")
    lines = [
        {
            "case": "k",
            "config": c,
            "state": "done",
            "status": s,
            "cost_usd": 0.5,
            "seconds": 1.0,
            "questions_open": 0,
        }
        | FREEZE
        for c, s in (("baseline_a", "ok"), ("baseline_b", "ok"), ("guideword", "finished"))
    ]
    (out / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    with (out / "probe_judgement.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("case,recognised_by_probe,excluded,reason\nk,no,no,nothing named\n")
    keys = tmp_path / "answer_keys.json"
    keys.write_text(json.dumps([_key()]), encoding="utf-8")
    return out, keys


def _fill(path: Path) -> None:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["score"], row["reason"] = (
            ("hit", "names the valve") if "left closed" in row["text"] else ("miss", "other")
        )
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_score_then_sheets_then_results(tmp_path: Path, capsys: Any) -> None:
    out, keys = _out(tmp_path)
    assert heldout_score.main(["--keys", str(keys), "--out", str(out)]) == 0
    auto = json.loads((out / "auto_scores.json").read_text(encoding="utf-8"))
    assert auto == {
        "k": {"baseline_a": None, "baseline_b": None, "guideword": 2, "guideword_found_anywhere": 2}
    }
    assert heldout_sheets.main(["--keys", str(keys), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert SECRET not in printed
    assert SECRET not in (out / "grader2" / "k.md").read_text(encoding="utf-8")
    # results refuse until both graders have scored every row
    assert heldout_results.main(["--out", str(out)]) == 1
    _fill(out / "sheets" / "k.csv")
    assert heldout_results.main(["--out", str(out)]) == 1
    _fill(out / "sheets_grader2" / "k.csv")
    assert heldout_results.main(["--out", str(out)]) == 0
    results = (out / "results.md").read_text(encoding="utf-8")
    assert "| Guideword | 1 of 1 |" in results and "Graders agree on 3 of 3" in results


def test_a_key_missing_a_field_stops_the_score_naming_fields_only(
    tmp_path: Path, capsys: Any
) -> None:
    out, keys = _out(tmp_path)
    key = _key()
    del key["match_phrases"]
    keys.write_text(json.dumps([key]), encoding="utf-8")
    assert heldout_score.main(["--keys", str(keys), "--out", str(out)]) == 1
    err = capsys.readouterr().err
    assert "match_phrases" in err and SECRET not in err
