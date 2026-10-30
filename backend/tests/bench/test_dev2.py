"""The development-case set (Phase 9 spec 9.0): a folder of packages, keys and plant files,
numbered `case_<nn>`, labelled development, checked before anything reads it."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.caselint import LintTerm
from guideword.bench.dev2 import V2_FIELDS, Dev2Case, check_folder, load_dev2
from guideword.reference import ReferenceSet, load_reference_set

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
TERMS = (LintTerm(term="explosion", kind="outcome", source="s"),)
PACKAGE = "# Plant 01: mixing unit\n\n## Data package\n- MX-1 mixer, 350 kPa gauge\n## Task\n"
SECRET = "SENTINEL-root-cause"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def key(case_id: str = "case_01", **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_id": case_id,
        "root_cause": SECRET,
        "component_ids": ["MX-1"],
        "cause_ids": ["C15"],
        "match_phrases": ["left closed"],
        "consequence": "a release",
        "missed_by_original_review": "the step",
        "multi_failure": False,
        "source": {"kind": "public investigation report", "reference": "r", "pages": "1"},
        "reference_mechanism": "A then B then C.",
        "report_year": 2015,
        "process_class": "batch_reactor",
        "operating_mode": "startup",
        "mechanism_class": "runaway_reaction",
        "contamination": {"flagged": False, "reason": ""},
        "second_check": {"three_mechanisms_fit": True, "by": "a second person"},
    }
    record.update(overrides)
    return record


def plant(case_id: str = "case_01") -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["plant_id"] = case_id
    return data


def folder(
    tmp_path: Path,
    *,
    package: str | None = PACKAGE,
    key_record: dict[str, Any] | None = None,
    plant_data: dict[str, Any] | None = None,
) -> Path:
    root = tmp_path / "dev2"
    for sub in ("cases", "keys", "plants"):
        (root / sub).mkdir(parents=True)
    if package is not None:
        (root / "cases" / "case_01_mixing-unit.md").write_text(package, encoding="utf-8")
    record = key() if key_record is None else key_record
    (root / "keys" / "case_01.json").write_text(json.dumps(record), encoding="utf-8")
    data = plant() if plant_data is None else plant_data
    (root / "plants" / "case_01.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def test_a_complete_case_passes_and_counts(tmp_path: Path, ref: ReferenceSet) -> None:
    report = check_folder(folder(tmp_path), ref, TERMS)
    assert report.problems == []
    assert report.counts == {"packages": 1, "keys": 1, "plants": 1, "complete": 1}
    assert [c.number for c in report.cases] == ["01"]


def test_a_package_without_a_plant_file_or_key_is_a_problem(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    root = folder(tmp_path)
    (root / "plants" / "case_01.json").unlink()
    (root / "keys" / "case_01.json").unlink()
    report = check_folder(root, ref, TERMS)
    assert report.problems == ["case_01: no key", "case_01: no plant file"]
    assert report.counts["complete"] == 0


def test_a_key_or_plant_without_a_package_is_a_problem(tmp_path: Path, ref: ReferenceSet) -> None:
    report = check_folder(folder(tmp_path, package=None), ref, TERMS)
    assert "case_01: no package" in report.problems


def test_a_key_missing_a_field_names_the_field_never_a_value(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    record = key()
    del record["reference_mechanism"]
    del record["match_phrases"]
    report = check_folder(folder(tmp_path, key_record=record), ref, TERMS)
    assert report.problems == ["case_01: key lacks match_phrases, reference_mechanism"]
    assert SECRET not in " ".join(report.problems)


def test_the_v2_fields_are_the_protocols(tmp_path: Path) -> None:
    assert V2_FIELDS == (
        "reference_mechanism",
        "report_year",
        "process_class",
        "operating_mode",
        "mechanism_class",
        "contamination",
        "second_check",
    )


def test_a_key_component_not_in_the_plant_is_counted_not_named(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    record = key(component_ids=["MX-1", "V-99", "V-98"])
    report = check_folder(folder(tmp_path, key_record=record), ref, TERMS)
    assert report.problems == ["case_01: 2 key components are not plant IDs"]
    assert "V-99" not in " ".join(report.problems)


def test_a_case_id_that_does_not_match_its_file_is_a_problem(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    report = check_folder(
        folder(tmp_path, key_record=key("case_02"), plant_data=plant("case_03")), ref, TERMS
    )
    assert report.problems == [
        "case_01: key case_id is case_02, not case_01",
        "case_01: plant_id is case_03, not case_01",
    ]


def test_a_plant_that_does_not_validate_is_listed_by_id_and_field(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    data = plant()
    data["equipment"][0]["location_id"] = "LOC-NOWHERE"
    report = check_folder(folder(tmp_path, plant_data=data), ref, TERMS)
    assert len(report.problems) == 1
    assert report.problems[0].startswith("case_01: plant: ")
    assert "LOC-NOWHERE" in report.problems[0]


def test_a_package_that_fails_lint_is_a_problem_with_its_line(
    tmp_path: Path, ref: ReferenceSet
) -> None:
    text = PACKAGE.replace("- MX-1 mixer", "- MX-1 mixer, rebuilt after an explosion in 2011")
    report = check_folder(folder(tmp_path, package=text), ref, TERMS)
    # flags come in line order, then by position in the line
    assert report.problems == [
        "case_01: package line 4: outcome: explosion",
        "case_01: package line 4: year: 2011",
    ]


def test_cases_load_with_the_development_label(tmp_path: Path) -> None:
    cases = load_dev2(folder(tmp_path))
    assert len(cases) == 1
    case = cases[0]
    assert isinstance(case, Dev2Case)
    assert case.label == "development"
    assert case.case_id == "case_01"
    assert case.package.name == "case_01_mixing-unit.md"
    assert case.key.name == "case_01.json" and case.plant.name == "case_01.json"


def test_loading_refuses_an_incomplete_folder(tmp_path: Path) -> None:
    root = folder(tmp_path)
    (root / "plants" / "case_01.json").unlink()
    with pytest.raises(ValueError, match="case_01: no plant file"):
        load_dev2(root)


def test_a_file_that_fits_no_pattern_is_reported(tmp_path: Path, ref: ReferenceSet) -> None:
    root = folder(tmp_path)
    (root / "cases" / "notes.md").write_text("x", encoding="utf-8")
    report = check_folder(root, ref, TERMS)
    assert report.problems == ["cases/notes.md: not a case file"]
