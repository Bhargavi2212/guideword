"""Coverage counts (spec 1.5): one line per list, `sections` first, every list always shown.

A question is checked only when it is `answered` or `not_credible`; `failed` never counts as
checked. Unsure is shown separately: answered questions with at least one unsure finding.
On the `sections` line, a section is checked when every question in it is (a section with no
questions is checked), unsure when one of its answered questions is unsure, and failed when
one of its questions failed (Q6). The `GET /runs/{id}/coverage` wrapper is Phase 2.
"""

from collections.abc import Iterable

from guideword.api.models import CoverageList
from guideword.schema.enums import Confidence, QuestionKind, QuestionStatus
from guideword.schema.records import Finding, Question, Section

CHECKED = {QuestionStatus.ANSWERED, QuestionStatus.NOT_CREDIBLE}
SECTIONS = "sections"


def coverage(
    sections: list[Section], questions: list[Question], findings: Iterable[Finding] = ()
) -> tuple[list[CoverageList], list[str]]:
    """The coverage lines and the failed question IDs (in question order)."""
    unsure_ids = {f.question_id for f in findings if f.confidence == Confidence.UNSURE}

    def unsure(q: Question) -> bool:
        return q.status == QuestionStatus.ANSWERED and q.id in unsure_ids

    by_section: dict[str, list[Question]] = {s.id: [] for s in sections}
    for q in questions:
        if q.section_id in by_section:
            by_section[q.section_id].append(q)
    lines = [
        CoverageList(
            list=SECTIONS,
            total=len(sections),
            checked=sum(1 for qs in by_section.values() if all(q.status in CHECKED for q in qs)),
            unsure=sum(1 for qs in by_section.values() if any(unsure(q) for q in qs)),
            failed=sum(
                1
                for qs in by_section.values()
                if any(q.status == QuestionStatus.FAILED for q in qs)
            ),
        )
    ]
    for kind in QuestionKind:
        listed = [q for q in questions if q.kind == kind]
        lines.append(
            CoverageList(
                list=kind.value,
                total=len(listed),
                checked=sum(1 for q in listed if q.status in CHECKED),
                unsure=sum(1 for q in listed if unsure(q)),
                failed=sum(1 for q in listed if q.status == QuestionStatus.FAILED),
            )
        )
    failed_ids = [q.id for q in questions if q.status == QuestionStatus.FAILED]
    return lines, failed_ids
