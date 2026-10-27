"""`results.md`, generated from the run records (Phase 6 spec 6.5, P6-6, P6-11; acceptance 8).
A synthetic output folder: two cases run, one excluded, one not run under the stop rule."""

import csv
import json
from pathlib import Path

import pytest

from guideword.bench.blind import COLUMNS, LABELS, blind_order
from guideword.bench.heldout_results import ResultsRefused, render_results

FREEZE = {"freeze_tag": "phase6-freeze", "freeze_commit": "a" * 40}


def _sheet(path: Path, case: str, scores: dict[str, list[str]]) -> None:
    """`scores[config]` lists the score of ranks 1, 2, ... for that configuration."""
    path.parent.mkdir(parents=True, exist_ok=True)
    order = dict(zip(blind_order(case), LABELS, strict=True))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        for config, marks in scores.items():
            for rank, score in enumerate(marks, start=1):
                writer.writerow(
                    {
                        "case": case,
                        "label": order[config],
                        "rank": rank,
                        "text": "t",
                        "equipment": "",
                        "score": score,
                        "reason": "r" if score else "",
                    }
                )


def _out(tmp_path: Path, *, grader2_differs: bool = False, unscored: bool = False) -> Path:
    out = tmp_path / "heldout"
    out.mkdir()
    with (out / "probe_judgement.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["case", "recognised_by_probe", "excluded", "reason"])
        writer.writerows(
            [
                ["k", "no", "no", "nothing named"],
                ["l", "no", "no", "nothing named"],
                ["m", "yes", "yes", "the probe named the site"],
                ["n", "no", "no", "nothing named"],
            ]
        )
    lines = []
    for case, status in (("k", "finished"), ("l", "stopped_cap")):
        for config in ("baseline_a", "baseline_b"):
            lines.append(
                {
                    "case": case,
                    "config": config,
                    "state": "done",
                    "status": "ok",
                    "cost_usd": 0.02,
                    "seconds": 9.0,
                }
                | FREEZE
            )
        lines.append(
            {"case": case, "config": "guideword", "state": "started", "run_id": f"run:{case}"}
            | FREEZE
        )
        lines.append(
            {
                "case": case,
                "config": "guideword",
                "state": "done",
                "run_id": f"run:{case}",
                "status": status,
                "cost_usd": 1.0,
                "seconds": 600.0,
                "questions_open": 0 if status == "finished" else 40,
            }
            | FREEZE
        )
        report = {
            "coverage": [{"list": "matrix", "checked": 90, "total": 100, "unsure": 3, "failed": 0}]
        }
        (out / f"case_{case}").mkdir()
        (out / f"case_{case}" / "guideword.json").write_text(json.dumps(report), encoding="utf-8")
    (out / "runs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    auto = {
        "k": {"baseline_a": None, "baseline_b": 7, "guideword": 2, "guideword_found_anywhere": 2},
        "l": {
            "baseline_a": None,
            "baseline_b": None,
            "guideword": None,
            "guideword_found_anywhere": 31,
        },
    }
    (out / "auto_scores.json").write_text(json.dumps(auto), encoding="utf-8")
    # k: Guideword hit at 2, A miss, B partial at 1; l: Guideword "hit" at 1 but its run stopped
    k = {
        "guideword": ["miss", "hit"],
        "baseline_a": ["miss", "miss"],
        "baseline_b": ["partial", "miss"],
    }
    lb = {
        "guideword": ["hit", "miss"],
        "baseline_a": ["miss", "miss"],
        "baseline_b": ["miss", "miss"],
    }
    if unscored:
        lb["baseline_b"] = ["miss", ""]
    for grader in ("sheets", "sheets_grader2"):
        second = grader == "sheets_grader2" and grader2_differs
        _sheet(out / grader / "k.csv", "k", k | ({"baseline_a": ["hit", "miss"]} if second else {}))
        _sheet(out / grader / "l.csv", "l", lb)
    mapping = {c: dict(zip(LABELS, blind_order(c), strict=True)) for c in ("k", "l")}
    (out / "blind_map.json").write_text(json.dumps(mapping), encoding="utf-8")
    return out


def test_the_headline_counts_top_3_hits_as_x_of_n_with_wilson_intervals(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "| Guideword | 1 of 2 |" in text  # k hit; l's run stopped, so a miss (P6-6)
    assert "| Baseline A (5A, checklist) | 0 of 2 |" in text
    assert "| Baseline B (one prompt) | 0 of 2 |" in text  # a partial never counts
    assert "0.09 to 0.91" in text  # Wilson 1 of 2


def test_a_stopped_run_counts_as_a_miss_and_is_listed(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "stopped at cap: 40 questions open" in text


def test_excluded_and_unrun_cases_are_listed_with_their_reasons(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "m: the probe named the site" in text
    assert "n: not run (stop rule)" in text


def test_percentages_never_appear(tmp_path: Path) -> None:
    assert "%" not in render_results(_out(tmp_path))


def test_the_paired_test_states_what_it_can_detect(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "at least 6 discordant cases, all one way" in text
    assert "no difference is claimed" in text


def test_the_automatic_score_and_found_anywhere_are_shown_but_not_the_headline(
    tmp_path: Path,
) -> None:
    text = render_results(_out(tmp_path))
    assert "## Automatic score (not the headline)" in text
    assert "| l | missed | missed | missed | 31 |" in text


def test_grader_agreement_and_disagreements_are_listed(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path, grader2_differs=True))
    assert "Graders agree on 5 of 6" in text
    assert "k, Baseline A (5A, checklist): Bhargavi miss, second grader hit" in text


def test_results_refuse_while_any_sheet_row_is_unscored(tmp_path: Path) -> None:
    with pytest.raises(ResultsRefused, match="l.csv"):
        render_results(_out(tmp_path, unscored=True))


def test_dev_results_link_bench_test5_results_md_as_recorded(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "[bench/test5/results.md](../../bench/test5/results.md)" in text
    assert "development" in text and "never pooled" in text


def test_the_freeze_coverage_and_total_paid_are_stated(tmp_path: Path) -> None:
    text = render_results(_out(tmp_path))
    assert "phase6-freeze" in text and "a" * 40 in text
    assert "90 / 100 checked, 3 unsure" in text
    assert "Total paid: $2.08" in text
