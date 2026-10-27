"""Blind sheets and the second grader's packets (Phase 6 spec P6-10; plan G8; acceptance 7).
Synthetic lines and keys only."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.blind import (
    LABELS,
    blind_order,
    substitute_keys,
    undo,
    write_case_sheets,
)
from guideword.bench.heldout_scoring import Line
from guideword.bench.runner import CONFIGS

SECRET = "SENTINEL-secret"
FINDING = "f:m:S-EA-425B:more:pressure:super:C22:e53bce019995581b"
CHAIN = "ch:HV-B-SIN.normal_position+f:proc:P-REB-START-2:early:super:C16:126a45a4b13afa1b"


@pytest.mark.parametrize(
    "text",
    [
        f"Shell overpressure, see {FINDING}.",
        f"Linked to {CHAIN} and proc:P-REB-START-2:early (step) with HV-B-SIN.normal_position",
        "pair:PROPANE:WATER and env:C4-HEAVIES:water, then relief:PSV-1 and work:W-1:EA-425B",
        "no keys here at all",
    ],
)
def test_undoing_every_substitution_gives_back_the_stored_text(text: str) -> None:
    shown = substitute_keys(text)
    assert undo(shown) == text


def test_record_keys_become_tag_or_step_names() -> None:
    shown = substitute_keys(f"see {FINDING} and proc:P-REB-START-2:early; HV-B-SIN.normal_position")
    assert shown.text == (
        "see EA-425B more pressure and P-REB-START-2 early; HV-B-SIN normal position"
    )
    assert "f:" not in shown.text and "proc:" not in shown.text


def test_a_chain_key_becomes_its_named_parts() -> None:
    assert substitute_keys(CHAIN).text == "HV-B-SIN normal position and P-REB-START-2 early"


def test_the_xyz_order_is_fixed_by_h_case_id() -> None:
    first = blind_order("k")
    assert sorted(first) == sorted(CONFIGS) and first == blind_order("k")
    # the order differs between cases, so a label can't be learnt across sheets
    orders = {tuple(blind_order(x)) for x in "klmnpqrs"}
    assert len(orders) > 1


def _lines() -> dict[str, list[Line]]:
    return {
        "baseline_a": [Line(r, f"tank hazard {r}", ["T-1"]) for r in range(1, 13)],
        "baseline_b": [Line(r, f"pump hazard {r}", ["T-2"]) for r in range(1, 4)],
        "guideword": [
            Line(1, f"Valve closed — overpressure via {FINDING}", ["EA-425B"]),
            *[Line(r, f"valve line {r}", ["V-1"]) for r in range(2, 15)],
        ],
    }


def _key() -> dict[str, Any]:
    return {
        "root_cause": "The valve was left closed.",
        "component_ids": ["V-1"],
        "missed_by_original_review": "The startup step.",
        "match_phrases": [SECRET],
        "source": {"reference": SECRET},
        "consequence": SECRET,
        "cause_ids": [SECRET],
    }


def test_sheets_hold_each_configs_top_10_under_its_label_and_nothing_that_tells_them_apart(
    tmp_path: Path,
) -> None:
    write_case_sheets("k", _lines(), _key(), tmp_path)
    with (tmp_path / "sheets" / "k.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["case", "label", "rank", "text", "equipment", "score", "reason"]
    mapping = json.loads((tmp_path / "blind_map.json").read_text(encoding="utf-8"))["k"]
    assert sorted(mapping) == list(LABELS) and sorted(mapping.values()) == sorted(CONFIGS)
    by_label = {lab: [r for r in rows if r["label"] == lab] for lab in LABELS}
    sizes = {mapping[lab]: len(rs) for lab, rs in by_label.items()}
    assert sizes == {"baseline_a": 10, "baseline_b": 3, "guideword": 10}
    for row in rows:
        lowered = row["text"].lower()
        assert "f:" not in row["text"] and "ch:" not in row["text"]
        for word in ("guideword", "baseline", "5a", "confirmed", "also found", "hypothesis"):
            assert word not in lowered
        assert row["score"] == "" and row["reason"] == ""


def test_the_second_graders_packet_holds_only_the_three_key_fields_and_the_lists(
    tmp_path: Path,
) -> None:
    write_case_sheets("k", _lines(), _key(), tmp_path)
    packet = (tmp_path / "grader2" / "k.md").read_text(encoding="utf-8")
    assert "The valve was left closed." in packet and "The startup step." in packet
    assert "V-1" in packet and SECRET not in packet
    for label in LABELS:
        assert f"## List {label}" in packet
    assert (tmp_path / "sheets_grader2" / "k.csv").is_file()


def test_regenerating_gives_the_same_files(tmp_path: Path) -> None:
    write_case_sheets("k", _lines(), _key(), tmp_path / "one")
    write_case_sheets("k", _lines(), _key(), tmp_path / "two")
    for name in ("sheets/k.csv", "sheets_grader2/k.csv", "grader2/k.md", "blind_map.json"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_a_filled_sheet_is_never_overwritten(tmp_path: Path) -> None:
    write_case_sheets("k", _lines(), _key(), tmp_path)
    sheet = tmp_path / "sheets" / "k.csv"
    sheet.write_text(sheet.read_text(encoding="utf-8") + "filled", encoding="utf-8")
    with pytest.raises(FileExistsError, match="k.csv"):
        write_case_sheets("k", _lines(), _key(), tmp_path)
