"""The HAZOP worksheet (spec 3.5; PROJECT.md §5 Step 8; Phase 3 plan PR 6, Q14, G15).

One row per finding, unfolded, in display order, then one row per question with no finding
(not credible, failed, open, or an engineer's question answered by override), with its
status. Overrides apply on read. On a folded line every member shows the line's LOPA gap and
recommendation, marked "(scenario)" (Q14). `status` is the question's status, as the contract
fixtures show it; the engineer's override state is in `override_state`.

Origin is the question's origin (G15: matrix; cross-list for pair, environment, no-flow,
procedure, planned-work, dust and relief questions; added by AI; engineer). Existing
safeguards are the finding's `safeguard_ids`, each with its description. Evidence is empty
until Phase 4.
"""

from collections.abc import Mapping, Sequence

from guideword.api import models as api
from guideword.config import CapsConfig
from guideword.lopa.lines import ShortlistLine, cause_words
from guideword.ranking.rank import RankedFinding, rank_findings
from guideword.reference import ReferenceSet
from guideword.review.display import gap_text
from guideword.review.overrides import (
    effective_finding,
    effective_question,
    effective_recommendation,
    effective_section,
    on_target,
    override_state,
)
from guideword.review.shortlist import RunView, shortlist_lines
from guideword.schema import ids
from guideword.schema.enums import Confidence, OverrideAction, QuestionKind, QuestionStatus
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding, Override, Question, Section

SCENARIO_MARK = " (scenario)"
STATUS_TEXT = {
    QuestionStatus.ANSWERED: "answered",
    QuestionStatus.NOT_CREDIBLE: "not credible",
    QuestionStatus.FAILED: "failed",
    QuestionStatus.OPEN: "open",
}


def _guideword_parameter(question: Question | None) -> tuple[str | None, str | None]:
    if question is None or question.kind != QuestionKind.MATRIX:
        return None, None
    _, guideword, parameter = ids.parse_question_id(question.id).parts
    return guideword, parameter


def _safeguards(finding: Finding, plant: Plant) -> str:
    described = {g.id: g.description for g in plant.safeguards}
    return "; ".join(
        f"{sid}: {described[sid]}" if described.get(sid) else sid for sid in finding.safeguard_ids
    )


def _causes(finding: Finding, causes: Mapping[str, str]) -> str:
    words = cause_words(finding, causes)
    label = words if finding.cause_id == OUTSIDE_LIBRARY else f"{finding.cause_id} {words}"
    return f"{label} ({', '.join(finding.failing_component_ids)})"


def _line_of(lines: Sequence[ShortlistLine]) -> dict[str, tuple[ShortlistLine, bool]]:
    """Each finding's shortlist line, and whether that line folds more than one finding."""
    out: dict[str, tuple[ShortlistLine, bool]] = {}
    for line in lines:
        tiered = line.planned.line
        if line.planned.target_kind == "chain" or tiered is None or tiered.lead is None:
            continue
        members = [tiered.lead.finding.id, *(r.finding.id for r in tiered.folded)]
        for member in members:
            out.setdefault(member, (line, len(members) > 1))
    return out


def _recommendation_text(line: ShortlistLine, overrides: Sequence[Override]) -> str | None:
    shown = []
    for rec in line.recommendations:
        text = effective_recommendation(rec, overrides).action
        if override_state(on_target(overrides, rec.id)) == "rejected":
            text = f"{text} (rejected)"
        shown.append(text)
    return "; ".join(shown) or None


def _status(question: Question | None, unsure: bool) -> str:
    if question is None:
        return "answered"
    text = STATUS_TEXT[question.status]
    return f"{text} (unsure)" if unsure and question.status == QuestionStatus.ANSWERED else text


def _finding_row(
    finding: Finding,
    view: RunView,
    plant: Plant,
    ranked: Mapping[str, RankedFinding],
    lines: Mapping[str, tuple[ShortlistLine, bool]],
    questions: Mapping[str, Question],
    sections: Mapping[str, Section],
    causes: Mapping[str, str],
) -> api.WorksheetRow:
    overrides = view.records.overrides
    shown = effective_finding(finding, overrides)
    question = questions.get(finding.question_id)
    section = sections.get(question.section_id) if question and question.section_id else None
    guideword, parameter = _guideword_parameter(question)
    found = ranked.get(finding.id)
    chain = on_target(overrides, finding.id)
    record_ids = [finding.id]
    lopa_gap = recommendation = None
    if finding.id in lines:
        line, folded = lines[finding.id]
        mark = SCENARIO_MARK if folded else ""
        if line.lopa is not None:
            lopa_gap = gap_text(line.lopa) + mark
            record_ids.append(line.lopa.id)
        elif line.no_lopa_reason is not None:
            lopa_gap = f"no LOPA: {line.no_lopa_reason}{mark}"
        text = _recommendation_text(line, overrides)
        recommendation = text + mark if text is not None else None
        record_ids += [r.id for r in line.recommendations]
    record_ids += [o.id for o in chain]
    return api.WorksheetRow(
        row_id=finding.id,
        section=section.id if section else (question.kind.value if question else ""),
        design_intent=effective_section(section, overrides).purpose if section else None,
        guideword=guideword,
        parameter=parameter,
        deviation=question.text if question else finding.question_id,
        causes=_causes(finding, causes),
        consequences=shown.consequence,
        existing_safeguards=_safeguards(finding, plant),
        severity=shown.severity_class.value if shown.severity_class else None,
        likelihood=(
            found.likelihood.likelihood_class.value
            if found and found.likelihood.likelihood_class
            else None
        ),
        risk=found.rating.value if found and found.rating else None,
        lopa_gap=lopa_gap,
        recommendation=recommendation,
        action_owner=None,
        origin=question.origin.value if question else "",
        evidence=None,
        status=_status(question, finding.confidence == Confidence.UNSURE),
        record_ids=record_ids,
        override_state=override_state(chain),
    )


def _question_row(
    question: Question, view: RunView, sections: Mapping[str, Section]
) -> api.WorksheetRow:
    overrides = view.records.overrides
    shown = effective_question(question, overrides)
    section = sections.get(question.section_id) if question.section_id else None
    guideword, parameter = _guideword_parameter(question)
    chain = on_target(overrides, question.id)
    answers = [o.new_value["text"] for o in chain if o.action == OverrideAction.ANSWER]
    return api.WorksheetRow(
        row_id=question.id,
        section=section.id if section else question.kind.value,
        design_intent=effective_section(section, overrides).purpose if section else None,
        guideword=guideword,
        parameter=parameter,
        deviation=question.text,
        causes=question.not_credible_reason or "",
        consequences=answers[-1] if answers else "",
        existing_safeguards="",
        severity=None,
        likelihood=None,
        risk=None,
        lopa_gap=None,
        recommendation=None,
        action_owner=None,
        origin=question.origin.value,
        evidence=None,
        status=_status(shown, False),
        record_ids=[question.id, *(o.id for o in chain)],
        override_state=override_state(chain),
    )


def worksheet_rows(
    view: RunView, plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[api.WorksheetRow]:
    records = view.records
    overrides = records.overrides
    lines = shortlist_lines(view, plant, ref, caps)
    line_of = _line_of(lines)
    shown = [effective_finding(f, overrides) for f in records.findings]
    ranked = {r.finding.id: r for r in rank_findings(shown, plant, ref, caps)}
    questions = {q.id: q for q in records.questions}
    sections = {s.id: s for s in records.sections}
    causes = {c.id: c.cause for c in ref.causes}
    # display order: the shortlist's lines, each lead then its folded findings, then the rest
    order = list(dict.fromkeys([*line_of, *(r.finding.id for r in ranked.values())]))
    by_id = {f.id: f for f in records.findings}
    rows = [
        _finding_row(by_id[fid], view, plant, ranked, line_of, questions, sections, causes)
        for fid in order
        if fid in by_id
    ]
    with_findings = {f.question_id for f in records.findings}
    rows += [
        _question_row(q, view, sections) for q in records.questions if q.id not in with_findings
    ]
    return rows
