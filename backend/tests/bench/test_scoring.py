"""The test #5 automatic score (spec 2.10; plan R26a, R26c). A synthetic key of the dev key's
shape is written to `tmp_path`; the real key file is never read by tests."""

import json
from pathlib import Path

import pytest

from guideword.bench.scoring import (
    bucket,
    case_letter,
    first_match,
    line_matches,
    load_keys,
)

GROUPS = [["chlorine", "cl2"], ["dead leg", "stagnant"]]


def write_key(tmp_path: Path) -> Path:
    key = {
        "_note": "synthetic key for tests",
        "case_d_c4_unit": {
            "source": "s",
            "actual_event": "e",
            "match": [["valve"], ["closed"]],
            "memorization_markers": ["m"],
        },
        "case_g_batch_plant": {
            "source": "s",
            "actual_event": "e",
            "match": GROUPS,
            "memorization_markers": [],
        },
    }
    path = tmp_path / "answer_keys.json"
    path.write_text(json.dumps(key), encoding="utf-8")
    return path


def test_score_matches_every_phrase_group_in_one_line_after_normalising() -> None:
    assert line_matches("Chlorine trapped in a DEAD-LEG — rupture", GROUPS)
    assert line_matches("cl2 in a stagnant section", GROUPS)
    # a Unicode dash and a non-breaking space are normalised too
    assert line_matches("chlorine in a dead‑leg", GROUPS)
    assert line_matches("chlorine in a dead leg", GROUPS)
    # every group must be met in the same line
    assert not line_matches("chlorine release from a flange", GROUPS)
    assert not line_matches("water in a dead leg", GROUPS)


def test_rank_of_first_match_top3_top10_missed() -> None:
    lines = ["pump trips", "chlorine in a dead leg", "chlorine in a stagnant pipe"]
    assert first_match(lines, GROUPS) == 2
    assert first_match(["nothing"] * 12, GROUPS) is None
    assert (bucket(1), bucket(3), bucket(4), bucket(10), bucket(11), bucket(None)) == (
        "top3",
        "top3",
        "top10",
        "top10",
        "missed",
        "missed",
    )


def test_key_entries_map_to_cases_by_letter_and_note_is_skipped(tmp_path: Path) -> None:
    keys = load_keys(write_key(tmp_path))
    assert keys == {"d": [["valve"], ["closed"]], "g": GROUPS}
    assert case_letter("case_g_batch_plant") == "g"
    assert case_letter("case_g") == "g"
    with pytest.raises(ValueError):
        case_letter("plant_g")


def test_a_key_entry_without_match_groups_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "k.json"
    path.write_text(json.dumps({"case_d_x": {"match": []}}), encoding="utf-8")
    with pytest.raises(ValueError, match="case_d_x"):
        load_keys(path)
