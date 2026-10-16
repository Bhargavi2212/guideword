"""The risk-matrix ranking (spec 2.6; plan R11, R28): code only, computed on demand.

Rated findings come first: by rating (very_high to low), then severity (S5 to S1), then
initiating frequency (higher first), then finding ID. Unrated findings follow in the same
order without the rating, each saying what is missing. Nothing is stored; the same findings
always give the same list.

`fold` (R48) shows the list one line per cause and failing components: the first, worst-ranked
finding of each, with the others folded underneath, so one cause found from many questions
takes one place in the top N. The scorer and the hand sheet read the folded list.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from guideword.config import CapsConfig
from guideword.ranking.likelihood import Likelihood, likelihood
from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import Confidence, RiskRating, SeverityClass, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding

RATING_ORDER = [RiskRating.VERY_HIGH, RiskRating.HIGH, RiskRating.MEDIUM, RiskRating.LOW]
SEVERITY_ORDER = [
    SeverityClass.S5,
    SeverityClass.S4,
    SeverityClass.S3,
    SeverityClass.S2,
    SeverityClass.S1,
]


@dataclass(frozen=True)
class RankedFinding:
    rank: int
    finding: Finding
    likelihood: Likelihood
    rating: RiskRating | None
    # why it has no rating: "no severity", "no likelihood", or both
    unrated_reason: str | None
    missing_fact_ids: tuple[str, ...]
    # an earlier unsure finding names the Ultra re-answer of the same question (R28)
    superseded_by: str | None


@dataclass(frozen=True)
class FoldedLine:
    rank: int
    worst: RankedFinding
    # the other findings of the same cause and components, in rank order
    folded: tuple[RankedFinding, ...]


def cause_key(finding: Finding) -> str:
    """The cause as one value: the library ID, or the normalised outside-library text."""
    if finding.cause_id == OUTSIDE_LIBRARY:
        return "outside:" + ids.normalise_text(finding.cause_text or "")
    return finding.cause_id


def fold(ranked: Sequence[RankedFinding]) -> list[FoldedLine]:
    groups: dict[tuple[str, tuple[str, ...]], list[RankedFinding]] = {}
    for row in ranked:
        key = (cause_key(row.finding), tuple(sorted(row.finding.failing_component_ids)))
        groups.setdefault(key, []).append(row)
    return [
        FoldedLine(position, members[0], tuple(members[1:]))
        for position, members in enumerate(groups.values(), start=1)
    ]


def _key(
    finding: Finding, found: Likelihood, rating: RiskRating | None
) -> tuple[int, int, float, str]:
    rating_pos = RATING_ORDER.index(rating) if rating is not None else len(RATING_ORDER)
    severity = finding.severity_class
    severity_pos = SEVERITY_ORDER.index(severity) if severity is not None else len(SEVERITY_ORDER)
    frequency = found.frequency_per_year if found.frequency_per_year is not None else -1.0
    return (rating_pos, severity_pos, -frequency, finding.id)


def rank_findings(
    findings: Sequence[Finding], plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[RankedFinding]:
    matrix = {(r.severity_class, r.likelihood_class): r.rating for r in ref.risk_matrix}
    reanswers: dict[str, str] = {}
    for finding in sorted(findings, key=lambda f: f.id):
        if finding.tier == Tier.ULTRA:
            reanswers.setdefault(finding.question_id, finding.id)
    rows = []
    for finding in findings:
        found = likelihood(finding, plant, ref, caps)
        rating = None
        if finding.severity_class is not None and found.likelihood_class is not None:
            rating = matrix[(finding.severity_class, found.likelihood_class)]
        missing = []
        if finding.severity_class is None:
            missing.append("no severity")
        if found.likelihood_class is None:
            missing.append("no likelihood")
        superseded = None
        if finding.tier != Tier.ULTRA and finding.confidence == Confidence.UNSURE:
            superseded = reanswers.get(finding.question_id)
        rows.append((_key(finding, found, rating), finding, found, rating, missing, superseded))
    rows.sort(key=lambda r: r[0])
    return [
        RankedFinding(
            rank=position,
            finding=finding,
            likelihood=found,
            rating=rating,
            unrated_reason=" and ".join(missing) or None,
            missing_fact_ids=found.missing_fact_ids,
            superseded_by=superseded,
        )
        for position, (_, finding, found, rating, missing, superseded) in enumerate(rows, start=1)
    ]
