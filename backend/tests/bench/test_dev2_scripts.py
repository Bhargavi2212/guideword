"""The two case scripts end to end on a synthetic folder (Phase 9 spec 9.0): lint, then the
folder check, which refuses until every problem is fixed and never prints a key's value."""

import json
from pathlib import Path
from typing import Any

import case_lint
import dev2_check
import pytest

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
SECRET = "SENTINEL-root-cause"
PACKAGE = "# Plant 01: mixing unit\n\n## Data package\n- MX-1 mixer, 350 kPa gauge\n## Task\n"


def _key() -> dict[str, Any]:
    return {
        "case_id": "case_01",
        "root_cause": SECRET,
        "component_ids": ["MX-1"],
        "cause_ids": ["C15"],
        "match_phrases": [SECRET],
        "consequence": "a release",
        "missed_by_original_review": "the step",
        "multi_failure": False,
        "source": {"kind": "public investigation report", "reference": "r", "pages": "1"},
        "reference_mechanism": SECRET,
        "report_year": 2015,
        "process_class": "batch_reactor",
        "operating_mode": "startup",
        "mechanism_class": "runaway_reaction",
        "contamination": {"flagged": False, "reason": ""},
        "second_check": {"three_mechanisms_fit": True, "by": "a second person"},
    }


def _folder(tmp_path: Path, package: str = PACKAGE) -> Path:
    root = tmp_path / "dev2"
    for sub in ("cases", "keys", "plants"):
        (root / sub).mkdir(parents=True)
    (root / "cases" / "case_01_mixing-unit.md").write_text(package, encoding="utf-8")
    (root / "keys" / "case_01.json").write_text(json.dumps(_key()), encoding="utf-8")
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["plant_id"] = "case_01"
    (root / "plants" / "case_01.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def test_lint_prints_each_flag_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "case_01_x.md"
    path.write_text("Built in 2011 by Acme Chemicals Inc.\nclean line\n", encoding="utf-8")
    assert case_lint.main([str(path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"{path}:1: year: 2011"
    assert out[1] == f"{path}:1: company: Acme Chemicals Inc"
    assert out[-1] == "1 files, 2 flags"
    assert "clean line" not in "\n".join(out)


def test_lint_passes_a_clean_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "case_01_x.md"
    path.write_text(PACKAGE, encoding="utf-8")
    assert case_lint.main([str(path)]) == 0
    assert capsys.readouterr().out.strip() == "1 files, 0 flags"


def test_the_check_passes_a_complete_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert dev2_check.main([str(_folder(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert "counts: packages 1, keys 1, plants 1, complete 1" in out
    assert out.strip().endswith("1 development cases ready")


def test_the_check_stops_on_a_problem_and_never_prints_a_key_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _folder(tmp_path, PACKAGE.replace("mixer", "mixer, rebuilt after the explosion"))
    (root / "plants" / "case_01.json").unlink()
    assert dev2_check.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "case_01: no plant file" in out
    assert "STOP: 1 problems" in out
    assert SECRET not in out
