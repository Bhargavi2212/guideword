"""The held-out keys and the automatic score (Phase 6 spec P6-9, 6.5; acceptance 5, 6). Every
key and line here is synthetic: no held-out key is ever read in this repo (CLAUDE.md §5)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.heldout_keys import KeyFieldsMissing, load_heldout_keys
from guideword.bench.heldout_scoring import (
    Line,
    baseline_lines,
    first_auto_match,
    guideword_lines,
    line_auto_matches,
    read_renames,
)

ROOT = Path(__file__).resolve().parents[3]


def _template_key() -> dict[str, Any]:
    """The example key in `docs/case-template.md` §4, read from the doc itself."""
    text = (ROOT / "docs" / "case-template.md").read_text(encoding="utf-8")
    section = text.split("## 4. The answer key", 1)[1]
    block = re.search(r"```json\n(.*?)\n```", section, re.S)
    assert block is not None
    key: dict[str, Any] = json.loads(block.group(1))
    return key


def _keys(tmp_path: Path, keys: Any) -> Path:
    path = tmp_path / "answer_keys.json"
    path.write_text(json.dumps(keys), encoding="utf-8")
    return path


# --- acceptance 5: the key loader ------------------------------------------------------------


def test_the_template_example_key_loads(tmp_path: Path) -> None:
    keys = load_heldout_keys(_keys(tmp_path, [_template_key()]))
    key = keys["k"]
    assert key.component_ids == ["V-1", "L-1"]
    assert key.match_phrases == ["left closed", "isolated from its relief"]


def test_keys_may_also_be_a_mapping_of_cases(tmp_path: Path) -> None:
    key = _template_key()
    keys = load_heldout_keys(
        _keys(tmp_path, {"case_k": key, "case_l": key | {"case_id": "case_l"}})
    )
    assert sorted(keys) == ["k", "l"]


def test_a_key_missing_a_field_is_refused_naming_only_the_field(tmp_path: Path) -> None:
    key = _template_key()
    del key["match_phrases"]
    key["root_cause"] = "SENTINEL-secret-root-cause"
    with pytest.raises(KeyFieldsMissing) as refused:
        load_heldout_keys(_keys(tmp_path, [key]))
    message = str(refused.value)
    assert "match_phrases" in message and "root_cause" in message
    assert "SENTINEL" not in message


# --- acceptance 6: the automatic match -------------------------------------------------------


def _line(text: str, components: list[str], rank: int = 1) -> Line:
    return Line(rank=rank, text=text, components=components)


KEY_COMPONENTS = ["V-1", "L-1"]
PHRASES = ["left closed", "isolated from its relief"]


def test_a_line_with_a_key_component_and_a_phrase_matches() -> None:
    assert line_auto_matches(
        _line("V-1 was left closed after work", ["V-1"]), KEY_COMPONENTS, PHRASES
    )


def test_a_component_without_a_phrase_doesnt() -> None:
    assert not line_auto_matches(_line("V-1 leaks", ["V-1"]), KEY_COMPONENTS, PHRASES)


def test_a_phrase_without_a_component_doesnt() -> None:
    assert not line_auto_matches(_line("left closed", ["P-9"]), KEY_COMPONENTS, PHRASES)


@pytest.mark.parametrize(
    "text", ["isolated-from its relief", "Isolated from its relief", "isolated–from its relief"]
)
def test_hyphen_case_and_unicode_dash_variants_match(text: str) -> None:
    phrases = ["isolated from its relief", "isolated-from its relief"]
    assert line_auto_matches(_line(text, ["L-1"]), KEY_COMPONENTS, phrases)


def test_found_anywhere_is_the_first_rank_in_the_full_list() -> None:
    lines = [
        _line("unrelated", ["P-9"], 1),
        _line("V-1 leaks", ["V-1"], 2),
        *[_line("noise", ["P-9"], r) for r in range(3, 14)],
        _line("L-1 was isolated from its relief", ["L-1"], 14),
        _line("V-1 left closed", ["V-1"], 15),
    ]
    assert first_auto_match(lines, KEY_COMPONENTS, PHRASES) == 14
    assert first_auto_match(lines[:10], KEY_COMPONENTS, PHRASES) is None


# --- the lines each configuration is scored on -----------------------------------------------


def test_a_renamed_id_matches_through_the_fixes_map(tmp_path: Path) -> None:
    fixes = tmp_path / "fixes.md"
    fixes.write_text(
        "# Fixes\n\n- rename: V-1 -> V-01\n- field: tank.size -> tank.volume_m3\n", encoding="utf-8"
    )
    renames = read_renames(fixes)
    assert renames == {"V-1": "V-01"}
    components = [renames.get(c, c) for c in KEY_COMPONENTS]
    assert line_auto_matches(_line("V-01 left closed", ["V-01"]), components, PHRASES)


def test_a_renamed_name_with_spaces_is_read_whole(tmp_path: Path) -> None:
    """A package may name a part in words ("Tank A"); its plant ID can't hold a space, so the
    conversion renames it, and the key still says "Tank A" (2026-10-28)."""
    fixes = tmp_path / "fixes.md"
    fixes.write_text(
        "- rename: Tank A -> TANK-A\n"
        "-  rename:  Feed  Pump 2-B   ->   FEED-PUMP-2-B  \n"
        "- rename: V-1 -> V-01\n"
        "- rename: no target ->\n"
        "- rename: two words -> TWO WORDS\n",
        encoding="utf-8",
    )
    assert read_renames(fixes) == {
        "Tank A": "TANK-A",
        "Feed  Pump 2-B": "FEED-PUMP-2-B",
        "V-1": "V-01",
    }


def _shortlist() -> dict[str, Any]:
    finding = {
        "id": "f:m:S-T-1:no:flow:lightning:C15:aaaaaaaaaaaaaaaa",
        "cause_id": "C15",
        "cause_text": None,
        "consequence": "the tank is isolated from its relief",
        "failing_component_ids": ["V-1"],
    }
    return {
        "items": [
            {"rank": 1, "target_id": finding["id"], "target_kind": "finding", "finding": finding},
            {
                "rank": 2,
                "target_id": "ch:L-1.no_flow+f:m:S-T-1:no:flow:lightning:C15:aaaaaaaaaaaaaaaa",
                "target_kind": "chain",
                "chain": {
                    "links": ["L-1.no_flow", finding["id"]],
                    "description": "The line stays left closed after the outage",
                },
            },
            {
                "rank": 3,
                "target_id": "hyp:x",
                "target_kind": "hypothesis",
                "hypothesis": {
                    "mechanism": "Valve left closed",
                    "consequence": "overpressure",
                    "component_ids": ["V-9"],
                },
            },
        ],
        "finding_components": {finding["id"]: ["V-1"]},
    }


def test_guideword_lines_read_findings_chains_and_hypotheses() -> None:
    lines = guideword_lines(_shortlist(), causes={"C15": "Valve closed in error"})
    assert [line.rank for line in lines] == [1, 2, 3]
    assert lines[0].text == "Valve closed in error — the tank is isolated from its relief"
    assert lines[0].components == ["V-1"]
    # a chain names its fact links' objects and its finding links' failing components
    assert lines[1].components == ["L-1", "V-1"]
    assert lines[2].components == ["V-9"]


def test_baseline_lines_name_their_equipment_and_text() -> None:
    record = {
        "hazards": [
            {"rank": 1, "hazard": "V-1 left closed", "equipment": ["Tank T-1"], "reason": "r"}
        ]
    }
    [line] = baseline_lines(record)
    assert line.text == "V-1 left closed" and line.components == ["Tank T-1"]
    # a baseline names a component in its equipment or its text
    assert line_auto_matches(line, ["V-1"], ["left closed"])


def test_a_keys_folder_of_one_file_per_case_loads(tmp_path: Path) -> None:
    folder = tmp_path / "keys"
    folder.mkdir()
    for x in "kl":
        key = _template_key() | {"case_id": f"case_{x}"}
        (folder / f"case_{x}.json").write_text(json.dumps(key), encoding="utf-8")
    assert sorted(load_heldout_keys(folder)) == ["k", "l"]
