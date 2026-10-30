"""The post-analysis lines, pure code (spec 3.2-3.4; plan PR 5, Q10, Q11, Q12, G17; Bhargavi
2026-10-19 on PR 4 choice 4).

**Which lines get LOPA** (`lopa_plan`), in the R50 display order:

- the top `lopa_top_n` lines with a lead finding, across the confirmed and also-found tiers,
  get **full** LOPA (Ultra argues the layers), and so does every chain with a severity;
- every other S4-S5 line of those two tiers gets **code-only** LOPA (Q10);
- the rest get none, with the reason: no severity (Q11), S1-S3 outside the top N, or
  unconfirmed (no finding to analyse). A confirmed line whose lead finding is shown under a
  higher line is listed with that reason, so no target is analysed twice.

**A chain's tier** is the tier of its highest member line: the first line in display order
that shows one of its finding links, as lead or folded (spec 3.1, 6.3).

**The shortlist** (`shortlist`, spec 3.3; Phase 8): tier first (R50). The confirmed tier keeps
its display order, the hypothesis rank with each chain at its member line (Phase 8, decisions
2026-10-29: the gap sort was hiding the whole-plant pass's own order on every held-out case).
Within the other tiers, complete LOPA by gap (largest first), then incomplete LOPA (flagged),
then lines with no LOPA, each in display order. Gap never crosses tiers. No line is ever
dropped: a line with no LOPA keeps its reason, and an S4-S5 line with no LOPA is flagged on its
card.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from guideword.config import CapsConfig
from guideword.lopa.candidates import Scenario, chain_scenario, line_scenario
from guideword.lopa.engine import NO_SEVERITY, NoLopa, lopa_record
from guideword.ranking.rank import rank_findings
from guideword.ranking.tiers import (
    UNCONFIRMED_FLAG,
    TieredLine,
    lead_prefers_own_section,
    tiered,
)
from guideword.reference import ReferenceSet
from guideword.runs.store import StepWriter
from guideword.schema.enums import EventType, SeverityClass, ShortlistTier
from guideword.schema.plant import Plant
from guideword.schema.records import (
    OUTSIDE_LIBRARY,
    Chain,
    Finding,
    Hypothesis,
    LopaRecord,
    ModelCall,
    Question,
    Recommendation,
    Section,
)

Kind = Literal["full", "code_only", "none"]
FULL: Kind = "full"
CODE_ONLY: Kind = "code_only"
NONE: Kind = "none"
TargetKind = Literal["finding", "chain", "hypothesis"]

HIGH_SEVERITY = frozenset({SeverityClass.S4, SeverityClass.S5})
TIER_ORDER = (ShortlistTier.CONFIRMED, ShortlistTier.ALSO_FOUND, ShortlistTier.UNCONFIRMED)
HIGH_SEVERITY_NO_LOPA = "S4–S5 with no LOPA — engineer to review"
INCOMPLETE_LOPA = "incomplete LOPA: gap unknown"
# target-handles plan (Bhargavi, 2026-10-21): an unrated chain is never just missing
NO_SEVERITY_NO_LOPA = "no severity — no LOPA"
UNCONFIRMED_NO_LOPA = "unconfirmed: no finding to analyse"
SHOWN_ELSEWHERE = "its lead finding is shown under a higher line"
NOT_REACHED = "LOPA not done: the run stopped before it"
RECOMMENDATION_JOB = "recommendation"
NO_RECOMMENDATION_FAILED = "no recommendation: the call failed"
NO_RECOMMENDATION_LEFT_OUT = "no recommendation: left out of the answer"
NO_RECOMMENDATION_NOT_REACHED = "no recommendation: not reached"


def cause_words(finding: Finding, causes: Mapping[str, str]) -> str:
    """The cause as the engineer reads it: the library text, or the outside-library text."""
    if finding.cause_id == OUTSIDE_LIBRARY:
        return finding.cause_text or ""
    return causes.get(finding.cause_id, finding.cause_id)


def display_lines(
    findings: Sequence[Finding],
    hypotheses: Sequence[Hypothesis],
    questions: Sequence[Question],
    sections: Sequence[Section],
    plant: Plant,
    ref: ReferenceSet,
    caps: CapsConfig,
    *,
    prefer_own_section: bool = False,
) -> list[TieredLine]:
    """The R50 tiered list, as the run shows it; `prefer_own_section` is the run's lead
    tie-break (`ranking.tiers.lead_prefers_own_section`)."""
    ranked = rank_findings(findings, plant, ref, caps)
    return tiered(
        ranked,
        hypotheses,
        findings,
        questions,
        sections=sections,
        prefer_own_section=prefer_own_section,
    )


def writer_lead_rule(writer: StepWriter) -> bool:
    """The lead tie-break for the run a step is writing."""
    return lead_prefers_own_section(
        writer.run.caps, writer.committed_events(EventType.RUN_EXTENDED)
    )


def section_for(
    finding: Finding, questions: Mapping[str, Question], sections: Mapping[str, Section]
) -> Section | None:
    """The section of the finding's question; None for a pair or environment question."""
    question = questions.get(finding.question_id)
    if question is None or question.section_id is None:
        return None
    return sections.get(question.section_id)


@dataclass(frozen=True)
class Planned:
    target_id: str
    target_kind: TargetKind
    tier: ShortlistTier
    # the line's place in the display order (a chain: its highest member line's)
    position: int
    kind: Kind
    scenario: Scenario | None
    # why the line gets no LOPA (kind "none")
    reason: str | None
    severity_class: SeverityClass | None
    line: TieredLine | None = None
    chain: Chain | None = None


def chain_tier(chain: Chain, lines: Sequence[TieredLine]) -> tuple[ShortlistTier, int]:
    links = set(chain.links)
    for position, line in enumerate(lines, start=1):
        if line.lead is None:
            continue
        members = {line.lead.finding.id, *(r.finding.id for r in line.folded)}
        if members & links:
            return line.tier, position
    return ShortlistTier.ALSO_FOUND, len(lines) + 1


def lopa_plan(
    lines: Sequence[TieredLine],
    chains: Sequence[Chain],
    findings: Sequence[Finding],
    questions: Sequence[Question],
    sections: Sequence[Section],
    *,
    top_n: int,
) -> list[Planned]:
    by_question = {q.id: q for q in questions}
    by_section = {s.id: s for s in sections}
    by_finding = {f.id: f for f in findings}
    plan: list[Planned] = []
    seen: set[str] = set()
    counted = 0
    for position, line in enumerate(lines, start=1):
        h = line.hypothesis
        if line.lead is None:
            reason = UNCONFIRMED_NO_LOPA
            plan.append(
                Planned(
                    h.id if h else "",
                    "hypothesis",
                    line.tier,
                    position,
                    NONE,
                    None,
                    reason,
                    None,
                    line,
                )
            )
            continue
        lead = line.lead.finding
        if lead.id in seen:
            plan.append(
                Planned(
                    h.id if h else lead.id,
                    "hypothesis",
                    line.tier,
                    position,
                    NONE,
                    None,
                    SHOWN_ELSEWHERE,
                    lead.severity_class,
                    line,
                )
            )
            continue
        seen.add(lead.id)
        severity = lead.severity_class
        kind: Kind
        reason_text: str | None = None
        if severity is None:
            kind, reason_text = NONE, NO_SEVERITY
        elif counted < top_n:
            kind = FULL
        elif severity in HIGH_SEVERITY:
            kind = CODE_ONLY
        else:
            kind, reason_text = NONE, f"{severity} outside the top {top_n}: no LOPA"
        counted += 1
        scenario = (
            line_scenario(lead, section_for(lead, by_question, by_section))
            if kind != NONE
            else None
        )
        plan.append(
            Planned(
                lead.id, "finding", line.tier, position, kind, scenario, reason_text, severity, line
            )
        )
    for chain in chains:
        tier, position = chain_tier(chain, lines)
        if chain.severity_class is None:
            plan.append(
                Planned(
                    chain.id, "chain", tier, position, NONE, None, NO_SEVERITY, None, chain=chain
                )
            )
            continue
        links = [
            (by_finding[link], section_for(by_finding[link], by_question, by_section))
            for link in chain.links
            if link in by_finding
        ]
        plan.append(
            Planned(
                chain.id,
                "chain",
                tier,
                position,
                FULL,
                chain_scenario(chain, links),
                None,
                chain.severity_class,
                chain=chain,
            )
        )
    return plan


@dataclass(frozen=True)
class ShortlistLine:
    planned: Planned
    lopa: LopaRecord | None
    no_lopa_reason: str | None
    flags: tuple[str, ...]
    recommendations: tuple[Recommendation, ...]

    @property
    def target_id(self) -> str:
        return self.planned.target_id

    @property
    def eligible(self) -> bool:
        """Q12: a complete LOPA with a gap above 1 gets a recommendation."""
        return (
            self.lopa is not None
            and self.lopa.complete
            and self.lopa.gap is not None
            and self.lopa.gap > 1
        )


def _no_lopa_reason(
    planned: Planned, run_id: str, plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> str:
    if planned.scenario is None:
        return planned.reason or NO_SEVERITY
    found = lopa_record(
        planned.scenario, run_id=run_id, plant=plant, ref=ref, caps=caps, arguments=None
    )
    return found.reason if isinstance(found, NoLopa) else NOT_REACHED


def _recommendation_flag(target_id: str, calls: Sequence[ModelCall]) -> str:
    about = [c for c in calls if c.job == RECOMMENDATION_JOB and target_id in c.record_ids]
    if not about:
        return NO_RECOMMENDATION_NOT_REACHED
    return NO_RECOMMENDATION_FAILED if about[-1].outcome != "ok" else NO_RECOMMENDATION_LEFT_OUT


def shortlist(
    plan: Sequence[Planned],
    records: Sequence[LopaRecord],
    recommendations: Sequence[Recommendation],
    calls: Sequence[ModelCall],
    *,
    run_id: str,
    plant: Plant,
    ref: ReferenceSet,
    caps: CapsConfig,
) -> list[ShortlistLine]:
    by_target = {r.target_id: r for r in records}
    recs: dict[str, list[Recommendation]] = {}
    for rec in recommendations:
        recs.setdefault(rec.target_id, []).append(rec)
    items: list[ShortlistLine] = []
    for planned in plan:
        record = by_target.get(planned.target_id) if planned.target_kind != "hypothesis" else None
        reason = None if record is not None else _no_lopa_reason(planned, run_id, plant, ref, caps)
        flags: list[str] = []
        if planned.tier == ShortlistTier.UNCONFIRMED:
            flags.append(UNCONFIRMED_FLAG)
        if record is None and planned.severity_class in HIGH_SEVERITY:
            flags.append(HIGH_SEVERITY_NO_LOPA)
        if record is not None and not record.complete:
            flags.append(INCOMPLETE_LOPA)
        if planned.target_kind == "chain" and planned.severity_class is None:
            flags.append(NO_SEVERITY_NO_LOPA)
        mine = tuple(recs.get(planned.target_id, ()))
        item = ShortlistLine(planned, record, reason, tuple(flags), mine)
        if item.eligible and not mine:
            flag = _recommendation_flag(planned.target_id, calls)
            item = ShortlistLine(planned, record, reason, (*item.flags, flag), mine)
        items.append(item)
    return sorted(items, key=_order)


def _order(item: ShortlistLine) -> tuple[int, int, float, int, str]:
    tier = TIER_ORDER.index(item.planned.tier)
    if item.planned.tier == ShortlistTier.CONFIRMED:
        # Phase 8: the model's order (R50), never the gap; a chain follows the line it hangs on
        return (
            tier,
            0,
            0.0,
            item.planned.position,
            f"{int(item.planned.target_kind == 'chain')}{item.target_id}",
        )
    record = item.lopa
    if record is not None and record.complete and record.gap is not None:
        bucket, gap = 0, record.gap
    elif record is not None:
        bucket, gap = 1, 0.0
    else:
        bucket, gap = 2, 0.0
    return (tier, bucket, -gap, item.planned.position, item.target_id)
