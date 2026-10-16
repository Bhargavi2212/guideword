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
"""

from collections.abc import Sequence
from dataclasses import dataclass

from guideword.ranking.rank import RankedFinding, fold
from guideword.schema.enums import ShortlistTier
from guideword.schema.records import Finding, Hypothesis, Question
from guideword.screen.link import support

UNCONFIRMED_FLAG = "not confirmed by the checks — engineer to review"


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
    code_order: bool = False,
) -> list[TieredLine]:
    position = {r.finding.id: i for i, r in enumerate(ranked)}
    by_id = {r.finding.id: r for r in ranked}
    supported: dict[str, list[str]] = {}
    for h in sorted(hypotheses, key=lambda h: (h.rank, h.id)):
        ids_ = sorted(
            (f.id for f in support(h, findings, questions) if f.id in by_id),
            key=position.__getitem__,
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
