"""`scripts/prompt_leak_check.py`: does a prompt's new text carry an answer key's words?

Synthetic keys of both shapes (the dev key's `match` / `memorization_markers` / `actual_event`,
and the held-out template's `match_phrases` / `component_ids` / `root_cause`) are written to
`tmp_path`; no real key is read. Output names counts and prompt line numbers, never key text,
unless `--show` is given."""

import json
from pathlib import Path

import prompt_leak_check
import pytest

REPO = Path(__file__).resolve().parents[3]
BASELINE = "You review a plant.\nName the hazards.\nThe valve may be closed.\n"


def files(tmp_path: Path, added: str, key: dict[str, object]) -> list[str]:
    prompt = tmp_path / "new.md"
    prompt.write_text(BASELINE + added, encoding="utf-8")
    baseline = tmp_path / "old.md"
    baseline.write_text(BASELINE, encoding="utf-8")
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps(key), encoding="utf-8")
    return ["--prompt", str(prompt), "--baseline", str(baseline), "--keys", str(keys)]


DEV_KEY = {
    "_note": "synthetic",
    "case_k_unit": {
        "source": "a synthetic report title",
        "actual_event": "the quench drum overfilled after the bypass was opened",
        "match": [["quench drum"], ["overfill", "overfilled"]],
        "memorization_markers": ["zebrafield"],
    },
}
TEMPLATE_KEY = [
    {
        "case_id": "case_m",
        "root_cause": "a strainer blinded and starved the pump",
        "component_ids": ["P-7"],
        "cause_ids": ["C15"],
        "match_phrases": ["strainer blinded"],
        "consequence": "pump seal fire",
        "missed_by_original_review": "no check of strainer differential",
    }
]


def test_clean_prompt_passes_and_prints_no_key_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = prompt_leak_check.main(files(tmp_path, "Rank by severity.\n", DEV_KEY))
    out = capsys.readouterr().out
    assert code == 0
    assert "case_k_unit" in out and "fail 0" in out
    for secret in ("quench", "overfill", "zebrafield", "bypass", "synthetic report"):
        assert secret not in out


def test_a_multi_word_phrase_in_an_added_line_fails_with_its_line_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = prompt_leak_check.main(files(tmp_path, "Look at the Quench-Drum first.\n", DEV_KEY))
    out = capsys.readouterr().out
    assert code == 1
    assert "fail 1" in out and "line 4" in out
    assert "quench" not in out.lower()


def test_a_memorisation_marker_fails(tmp_path: Path) -> None:
    assert prompt_leak_check.main(files(tmp_path, "zebrafield\n", DEV_KEY)) == 1


def test_words_only_in_baseline_lines_are_not_checked(tmp_path: Path) -> None:
    key = {"case_k": {**DEV_KEY["case_k_unit"], "match": [["valve may be closed"]]}}  # type: ignore[dict-item]
    assert prompt_leak_check.main(files(tmp_path, "Rank by severity.\n", key)) == 0


def test_single_words_and_prose_words_are_for_review_not_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = prompt_leak_check.main(files(tmp_path, "An overfilled vessel; a bypass.\n", DEV_KEY))
    out = capsys.readouterr().out
    assert code == 0
    assert "review 2" in out  # "overfilled" (a one-word phrase) and "bypass" (prose)


def test_template_key_ids_match_as_whole_tokens_only(tmp_path: Path) -> None:
    assert prompt_leak_check.main(files(tmp_path, "Check P-7 now.\n", TEMPLATE_KEY)) == 1
    (tmp_path / "b").mkdir()
    assert (
        prompt_leak_check.main(files(tmp_path / "b", "Check P-70 and C150.\n", TEMPLATE_KEY)) == 0
    )


def test_show_prints_the_matched_terms(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = files(tmp_path, "the strainer blinded\n", TEMPLATE_KEY)
    assert prompt_leak_check.main([*args, "--show"]) == 1
    assert "strainer blinded" in capsys.readouterr().out


def test_runs_on_the_shipped_prompts(tmp_path: Path) -> None:
    """The real prompts, with a key that shares nothing with them."""
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({"case_z": {"match": [["qqqzzz xxyy"]]}}), encoding="utf-8")
    code = prompt_leak_check.main(
        [
            "--prompt",
            str(REPO / "prompts" / "plant_screen" / "v1.md"),
            "--baseline",
            str(REPO / "prompts" / "test5a" / "v1.md"),
            "--keys",
            str(keys),
        ]
    )
    assert code == 0
