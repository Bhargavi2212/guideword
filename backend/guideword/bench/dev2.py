"""The development-case set, `cases/dev2/` (Phase 9 spec 9.0).

Fifty cases in the held-out format, numbered `case_<nn>`, written by a separate case-writer
session from `docs/case-writing-v2.md` and labelled **development**: for ablations and tuning,
never evidence (Bhargavi, answer 9). Layout: `cases/case_<nn>_<short-name>.md` (the package),
`keys/case_<nn>.json` (the key: the template's fields plus the protocol's, V2_FIELDS) and
`plants/case_<nn>.json` (the plant file).

`check_folder` reports every problem by case number: a case with a part missing, a key that
lacks a field (named, never its value), a key `case_id` or plant `plant_id` that does not match
the file, key components that are not plant IDs (counted, never named), a plant file that does
not validate (by object ID and field), a package the lint flags (by line). `load_dev2` gives the
complete cases and refuses an incomplete folder.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guideword.bench.caselint import LintTerm, lint_text
from guideword.bench.heldout_keys import FIELDS
from guideword.reference import ReferenceSet
from guideword.schema.validate import validate_plant

LABEL = "development"
V2_FIELDS = (
    "reference_mechanism",
    "report_year",
    "process_class",
    "operating_mode",
    "mechanism_class",
    "contamination",
    "second_check",
)
_PACKAGE = re.compile(r"^case_(\d{2,3})_[a-z0-9-]+\.md$")
_JSON = re.compile(r"^case_(\d{2,3})\.json$")


@dataclass(frozen=True)
class Dev2Case:
    number: str
    package: Path
    key: Path
    plant: Path
    label: str = LABEL

    @property
    def case_id(self) -> str:
        return f"case_{self.number}"


@dataclass(frozen=True)
class Dev2Report:
    cases: list[Dev2Case]
    problems: list[str]
    counts: dict[str, int] = field(default_factory=dict)


def _numbered(folder: Path, pattern: re.Pattern[str]) -> tuple[dict[str, Path], list[str]]:
    found: dict[str, Path] = {}
    odd: list[str] = []
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not path.is_file() or path.name == ".gitkeep":
            continue
        match = pattern.match(path.name)
        if match is None:
            odd.append(path.as_posix())
        else:
            found[match.group(1)] = path
    return found, odd


def _parts(root: Path) -> tuple[dict[str, Path], dict[str, Path], dict[str, Path], list[str]]:
    packages, odd1 = _numbered(root / "cases", _PACKAGE)
    keys, odd2 = _numbered(root / "keys", _JSON)
    plants, odd3 = _numbered(root / "plants", _JSON)
    odd = [f"{Path(p).relative_to(root).as_posix()}: not a case file" for p in odd1 + odd2 + odd3]
    return packages, keys, plants, odd


def _pair(root: Path) -> tuple[list[Dev2Case], list[str], dict[str, int]]:
    packages, keys, plants, problems = _parts(root)
    cases: list[Dev2Case] = []
    for number in sorted(set(packages) | set(keys) | set(plants)):
        missing = [
            name
            for name, part in (("package", packages), ("key", keys), ("plant file", plants))
            if number not in part
        ]
        problems += [f"case_{number}: no {name}" for name in missing]
        if not missing:
            cases.append(Dev2Case(number, packages[number], keys[number], plants[number]))
    counts = {
        "packages": len(packages),
        "keys": len(keys),
        "plants": len(plants),
        "complete": len(cases),
    }
    return cases, problems, counts


def plant_ids(data: Mapping[str, Any]) -> set[str]:
    """Every object ID in a plant record, procedure steps included."""
    found: set[str] = set()
    for value in data.values():
        if isinstance(value, list):
            for obj in value:
                if isinstance(obj, Mapping):
                    if isinstance(obj.get("id"), str):
                        found.add(obj["id"])
                    for step in obj.get("steps") or []:
                        if isinstance(step, Mapping) and isinstance(step.get("id"), str):
                            found.add(step["id"])
    return found


def _check_case(case: Dev2Case, ref: ReferenceSet, terms: Sequence[LintTerm]) -> list[str]:
    problems: list[str] = []
    for flag in lint_text(case.package.read_text(encoding="utf-8"), terms):
        problems.append(f"{case.case_id}: package line {flag.line}: {flag.kind}: {flag.text}")
    record = json.loads(case.key.read_text(encoding="utf-8"))
    if not isinstance(record, Mapping):
        return [*problems, f"{case.case_id}: key is not one record"]
    lacking = sorted(f for f in (*FIELDS, *V2_FIELDS) if f not in record)
    if lacking:
        problems.append(f"{case.case_id}: key lacks {', '.join(lacking)}")
    if record.get("case_id") != case.case_id:
        problems.append(
            f"{case.case_id}: key case_id is {record.get('case_id')}, not {case.case_id}"
        )
    data = json.loads(case.plant.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        return [*problems, f"{case.case_id}: plant file is not one record"]
    if data.get("plant_id") != case.case_id:
        problems.append(f"{case.case_id}: plant_id is {data.get('plant_id')}, not {case.case_id}")
    ids = plant_ids(data)
    components = record.get("component_ids")
    if isinstance(components, list):
        outside = sum(1 for c in components if c not in ids)
        if outside:
            problems.append(f"{case.case_id}: {outside} key components are not plant IDs")
    for issue in validate_plant(data, ref).errors:
        problems.append(f"{case.case_id}: plant: {issue.code}: {issue.message}")
    return problems


def check_folder(root: Path, ref: ReferenceSet, terms: Sequence[LintTerm]) -> Dev2Report:
    cases, problems, counts = _pair(root)
    for case in cases:
        problems += _check_case(case, ref, terms)
    return Dev2Report(cases, problems, counts)


def load_dev2(root: Path) -> list[Dev2Case]:
    """The complete cases, labelled development; raises on a folder with a part missing."""
    cases, problems, _ = _pair(root)
    if problems:
        raise ValueError("; ".join(problems))
    return cases
