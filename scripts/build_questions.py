"""Print a plant file's rule-drawn section cut and its question counts per list (spec 1.6).

Run from the repo root:  python scripts/build_questions.py cases/dev/case_g.json
No live calls. Exit code 1 when the plant file has validation errors.
"""

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from guideword.questions.build import build_questions
from guideword.questions.coverage import coverage
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.plants import load_plant
from guideword.schema.records import Section
from guideword.sections.rules import rule_cut

# Run IDs arrive in Phase 2; counts do not depend on them.
RUN_ID = "run:cli"


def cut_and_counts(
    data: Mapping[str, Any], ref: ReferenceSet
) -> tuple[list[Section], dict[str, int]] | None:
    """Upload, rule cut, build questions, coverage; None when the plant has errors."""
    record, _ = load_plant(data, ref)
    if record is None:
        return None
    sections = rule_cut(record.plant_file, record.id)
    questions = build_questions(record.plant_file, sections, ref, RUN_ID)
    lines, _ = coverage(sections, questions)
    return sections, {line.list: line.total for line in lines}


def counts(data: Mapping[str, Any], ref: ReferenceSet) -> dict[str, int] | None:
    result = cut_and_counts(data, ref)
    return None if result is None else result[1]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/build_questions.py <plant file>")
        return 2
    path = Path(argv[0])
    data = json.loads(path.read_text(encoding="utf-8"))
    ref = load_reference_set()
    result = cut_and_counts(data, ref)
    if result is None:
        _, report = load_plant(data, ref)
        print(f"{path}: {len(report.errors)} validation errors")
        for issue in report.errors:
            print(f"  {issue.code} {issue.object_id}: {issue.message}")
        return 1
    sections, totals = result
    print(f"{path}: {len(sections)} sections")
    for s in sections:
        flag = "  [no-flow]" if s.flagged_no_flow else ""
        print(f"  {s.id:<40} {s.kind.value:<13} {s.section_type or '-':<15} {s.name}{flag}")
    print()
    print(f"{'list':<22}{'count':>6}")
    for name, total in totals.items():
        print(f"{name:<22}{total:>6}")
    print(f"{'questions':<22}{sum(v for k, v in totals.items() if k != 'sections'):>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
