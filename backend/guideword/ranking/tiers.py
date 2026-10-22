"""The tiered list (spec 2b.4; R50; plan G1, G2, G4, Q1), computed on demand like `rank.py`.

1. **Confirmed:** hypotheses that at least one finding supports, in hypothesis rank order (the
   one place a model's order is used, CLAUDE.md §3). Each line shows its lead scenario, the
   supporting finding first in the spec 2.6 code order (G1); the other supporting findings
   fold under it. A finding that supports several hypotheses is shown only under the highest-
   ranked one; a hypothesis whose support is all shown higher stays a confirmed line and names
   where its support is shown (G2).
2. **Also found:** every finding not shown under a confirmed line, folded and ordered as now
   (R48, spec 2.6).
3. **Unconfirmed:** hypotheses no finding supports, in rank order, flagged for the engineer.

`code_order=True` keeps the same lines but orders tier 1 by its leads' place in the code order
and tier 3 by hypothesis ID (G4), so the model's ordering can be compared with code's.

**The lead's tie-break** (`prefer_own_section`; lead tie-break plan, approved 2026-10-21): among
supporting findings that tie on rating, severity, frequency and protection, one whose
question's section contains a hypothesis component comes first; then the finding ID, as
before. Nothing else moves: ownership, the fold and the global rank are unchanged. It is
gated by `ranking.lead_prefers_own_section`, read per run (`lead_prefers_own_section`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from guideword.ranking.rank import RankedFinding, fold, rank_prefix
from guideword.schema.enums import EventType, ShortlistTier
from guideword.schema.records import Event, Finding, Hypothesis, Question, Section
from guideword.screen.link import support

UNCONFIRMED_FLAG = "not confirmed by the checks — engineer to review"
LEAD_SETTING = "lead_prefers_own_section"


def lead_prefers_own_section(caps: Mapping[str, object], events: Sequence[Event]) -> bool:
    """The run's tie-break setting: from its latest `run_extended` event that records the
    ranking settings (a re-run takes the current rule), else from its stored, hashed caps.
    Runs stored without it read as before (False)."""
    for event in reversed(events):
        if event.type == EventType.RUN_EXTENDED and "ranking" in event.payload:
            ranking = event.payload["ranking"]
            return bool(ranking.get(LEAD_SETTING, False)) if isinstance(ranking, dict) else False
    stored = caps.get("ranking")
    return bool(stored.get(LEAD_SETTING, False)) if isinstance(stored, dict) else False


@dataclass(frozen=True)
class TieredLine:
    tier: ShortlistTier
    hypothesis: Hypothesis | None
    # confirmed: the lead scenario; also found: the worst of the fold; unconfirmed: none
    lead: RankedFinding | None
    # findings shown under this line, in code order (not the lead)
    folded: tuple[RankedFinding, ...]
    # confirmed: every supporting finding ID, and those shown under a higher line instead
    support_ids: tuple[str, ...] = ()
    shown_under: tuple[str, ...] = ()

    @property
    def shown_elsewhere(self) -> bool:
        """The lead is shown under a higher confirmed line (G2)."""
        return self.lead is not None and self.lead.finding.id in self.shown_under


def tiered(
    ranked: Sequence[RankedFinding],
    hypotheses: Sequence[Hypothesis],
    findings: Sequence[Finding],
    questions: Sequence[Question],
    *,
    sections: Sequence[Section],
    code_order: bool = False,
    prefer_own_section: bool = False,
) -> list[TieredLine]:
    position = {r.finding.id: i for i, r in enumerate(ranked)}
    by_id = {r.finding.id: r for r in ranked}
    by_question = {q.id: q for q in questions}
    by_section = {s.id: s for s in sections}

    def own_section(h: Hypothesis, finding_id: str) -> bool:
        question = by_question.get(by_id[finding_id].finding.question_id)
        section = by_section.get(question.section_id) if question and question.section_id else None
        return section is not None and bool(set(section.object_ids) & set(h.component_ids))

    supported: dict[str, list[str]] = {}
    for h in sorted(hypotheses, key=lambda h: (h.rank, h.id)):
        ids_ = sorted(
            (f.id for f in support(h, findings, questions, sections) if f.id in by_id),
            key=position.__getitem__,
        )
        if prefer_own_section:
            # ties only: the ranking key without the ID, then own section first, then the ID
            ids_.sort(
                key=lambda i, h=h: (rank_prefix(by_id[i]), 0 if own_section(h, i) else 1, i)  # type: ignore[misc]
            )
        supported[h.id] = ids_
    confirmed = [h for h in sorted(hypotheses, key=lambda h: (h.rank, h.id)) if supported[h.id]]
    owner: dict[str, str] = {}
    for h in confirmed:
        for finding_id in supported[h.id]:
            owner.setdefault(finding_id, h.id)

    tier1 = []
    for h in confirmed:
        support_ids = supported[h.id]
        lead = by_id[support_ids[0]]
        here = [by_id[i] for i in support_ids[1:] if owner[i] == h.id]
        elsewhere = tuple(i for i in support_ids if owner[i] != h.id)
        tier1.append(
            TieredLine(ShortlistTier.CONFIRMED, h, lead, tuple(here), tuple(support_ids), elsewhere)
        )
    if code_order:
        tier1.sort(key=lambda line: (position[line.lead.finding.id], line.hypothesis.id))  # type: ignore[union-attr]

    rest = [r for r in ranked if r.finding.id not in owner]
    tier2 = [
        TieredLine(ShortlistTier.ALSO_FOUND, None, line.worst, line.folded) for line in fold(rest)
    ]

    unconfirmed = [h for h in hypotheses if not supported.get(h.id)]
    unconfirmed.sort(key=(lambda h: h.id) if code_order else (lambda h: (h.rank, h.id)))
    tier3 = [TieredLine(ShortlistTier.UNCONFIRMED, h, None, ()) for h in unconfirmed]
    return [*tier1, *tier2, *tier3]
