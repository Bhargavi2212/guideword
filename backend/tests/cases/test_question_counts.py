"""Question counts on dev cases D-H equal the independently computed expected counts (spec 1.6).

`cases/dev/expected_counts.json` is Cowork's, computed outside this package from the plant
files with the rule cut; it is never edited to match the builder. If a count disagrees, stop
and ask: do not change either side to match.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from build_questions import counts

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import QuestionKind

REPO = Path(__file__).resolve().parents[3]
DEV = REPO / "cases" / "dev"
EXPECTED = DEV / "expected_counts.json"
CASES = ["case_d", "case_e", "case_f", "case_g", "case_h"]
LISTS = ["sections", *(k.value for k in QuestionKind)]


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def expected() -> dict[str, dict[str, int]]:
    assert EXPECTED.exists(), f"{EXPECTED} is missing; Bhargavi commits Cowork's expected counts"
    data: dict[str, dict[str, int]] = json.loads(EXPECTED.read_text(encoding="utf-8"))
    return data


def _plant(case: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DEV / f"{case}.json").read_text(encoding="utf-8"))
    return data


def test_expected_counts_cover_every_case_and_list(expected: dict[str, dict[str, int]]) -> None:
    assert sorted(expected) == CASES
    for case, lists in expected.items():
        assert sorted(lists) == sorted(LISTS), case


@pytest.mark.parametrize("case", CASES)
def test_every_list_count_matches(
    case: str, ref: ReferenceSet, expected: dict[str, dict[str, int]]
) -> None:
    """Upload -> rule cut -> build questions -> coverage, then compare every list."""
    assert counts(_plant(case), ref) == expected[case]


def test_build_questions_cli_runs_on_case_g(expected: dict[str, dict[str, int]]) -> None:
    script = REPO / "scripts" / "build_questions.py"
    result = subprocess.run(
        [sys.executable, str(script), str(DEV / "case_g.json")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "S-" in out
    for name, total in expected["case_g"].items():
        assert f"{name:<22}{total:>6}" in out, name


def test_cli_refuses_a_plant_with_errors(tmp_path: Path) -> None:
    data = _plant("case_g")
    data["equipment"][0]["location_id"] = "NOWHERE"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_questions.py"), str(bad)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 1
    assert "bad_reference" in result.stdout
