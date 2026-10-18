"""Kill test #4 reported, never re-scored (spec 2.10; plan R26b, R37). Synthetic files with the
real file's fields; the real results are only read when Bhargavi runs the script."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.kill4 import (
    AUTOMATIC_LABEL,
    HAND_REVIEW,
    is_dry_run,
    load_run,
    summarise,
)

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def row(model: str, case: str, rank: int | None, recognised: bool) -> dict[str, Any]:
    return {
        "answer": "SECRET-ANSWER-TEXT",
        "case": case,
        "finish_reason": "stop",
        "model": model,
        "probe": "SECRET-PROBE-TEXT",
        "recognized_incident": recognised,
        "score": {"top10_found": 10, "rank": rank, "in_worksheet": rank is not None},
        "seconds": 1.0,
        "usage": {},
    }


def write(tmp_path: Path, name: str, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


REAL = [
    row(ULTRA, "case_d_c4_unit", 1, False),
    row(ULTRA, "case_g_batch_plant", None, False),
    row(ULTRA, "case_h_corn_mill", 1, True),
    row(NANO, "case_d_c4_unit", None, True),
]


def test_kill4_reports_recorded_ultra_ranks_without_rescoring(tmp_path: Path) -> None:
    summary = summarise(load_run(write(tmp_path, "run-1.jsonl", REAL)), run="1")
    ultra = {r["case"]: r for r in summary["ultra"]}
    assert ultra["case_d_c4_unit"]["rank"] == 1 and not ultra["case_d_c4_unit"]["excluded"]
    assert ultra["case_g_batch_plant"]["rank"] is None
    assert ultra["case_h_corn_mill"]["excluded"] is True  # recognised by Ultra (R37)
    assert summary["ultra_top3_unrecognised"] == "1 of 2"
    assert [r["case"] for r in summary["nano_not_the_4_configuration"]] == ["case_d_c4_unit"]
    assert summary["label"] == AUTOMATIC_LABEL and summary["hand_review"] == HAND_REVIEW


def test_no_answer_or_probe_text_is_carried(tmp_path: Path) -> None:
    summary = summarise(load_run(write(tmp_path, "run-1.jsonl", REAL)), run="1")
    text = json.dumps(summary)
    assert "SECRET-ANSWER-TEXT" not in text and "SECRET-PROBE-TEXT" not in text


def test_a_dry_run_is_recognised_and_skipped(tmp_path: Path) -> None:
    dry = load_run(write(tmp_path, "run-2.jsonl", [row("dry-model", "case_d_c4_unit", 1, False)]))
    assert is_dry_run(dry) and not is_dry_run(load_run(write(tmp_path, "run-1.jsonl", REAL)))


def test_the_script_reports_the_real_run_and_skips_dry_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import kill4  # noqa: PLC0415

    folder = tmp_path / "kill4"
    folder.mkdir()
    write(folder, "run-20261009-215148.jsonl", REAL)
    write(folder, "run-20261009-215138.jsonl", [row("dry-model", "case_d_c4_unit", 1, False)])
    assert kill4.main(["--dir", str(folder)]) == 0
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["run"] == "20261009-215148"
    assert summary["skipped_dry_runs"] == ["20261009-215138"]
    assert "skipped dry run 20261009-215138" in capsys.readouterr().out


def test_the_results_table_labels_the_ranks_as_automatic(tmp_path: Path) -> None:
    from guideword.bench.results import render_results  # noqa: PLC0415

    root = tmp_path / "test5"
    (root / "kill4").mkdir(parents=True)
    summary = summarise(load_run(write(tmp_path, "run-1.jsonl", REAL)), run="1")
    (root / "kill4" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    text = render_results(root)
    assert AUTOMATIC_LABEL in text and HAND_REVIEW in text
    assert "| case_h_corn_mill | 1 | yes (excluded) |" in text
    assert "| case_g_batch_plant | not in top 10 | no |" in text
