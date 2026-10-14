"""Dev cases D-H as plant files (spec 0.7)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.validate import validate_plant

DEV = Path(__file__).resolve().parents[3] / "cases" / "dev"
CASES = {
    "case_d": "case_d_c4_unit.md",
    "case_e": "case_e_fcc_shutdown.md",
    "case_f": "case_f_pulp_mill_area.md",
    "case_g": "case_g_batch_plant.md",
    "case_h": "case_h_corn_mill.md",
}
REPORT = DEV / "conversion-report.md"
TICKED = re.compile(r"^- \[x\] `([^`]+)`", re.M | re.I)


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _plant(case: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DEV / f"{case}.json").read_text(encoding="utf-8"))
    return data


def _ticked() -> set[str]:
    return set(TICKED.findall(REPORT.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", sorted(CASES))
def test_case_validates_with_no_errors(case: str, ref: ReferenceSet) -> None:
    report = validate_plant(_plant(case), ref)
    assert report.errors == [], [f"{e.code} {e.object_id}: {e.message}" for e in report.errors]


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_assumed_value_is_ticked_in_the_report(case: str) -> None:
    assumed = {key for key, source in _plant(case)["provenance"].items() if source == "assumed"}
    assert assumed <= _ticked(), f"assumed but not ticked: {sorted(assumed - _ticked())}"


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_other_fact_cites_its_package(case: str) -> None:
    sources = set(_plant(case)["provenance"].values()) - {"assumed"}
    assert sources == {f"cases/dev/source/{CASES[case]}"}


@pytest.mark.parametrize("case", sorted(CASES))
def test_notes_quote_the_package_verbatim(case: str) -> None:
    """A note is the package's exact words: every note text appears in the package file."""
    package = (DEV / "source" / CASES[case]).read_text(encoding="utf-8")
    flat = " ".join(package.split())
    notes: list[dict[str, str]] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            notes.extend(node.get("notes", []))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(_plant(case))
    assert notes, "each case keeps the package words it cannot otherwise hold"
    for note in notes:
        assert note["source"] == f"cases/dev/source/{CASES[case]}"
        assert " ".join(note["text"].split()) in flat, note["text"]


def test_report_has_a_section_per_case() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for case in CASES:
        assert f"## {case}" in text
