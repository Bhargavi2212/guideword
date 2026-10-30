"""Candidates across the holistic passes (Phase 9 spec 9.3). Code only, deterministic.

Each pass proposes its own ranked hypotheses. Two hypotheses are the **same candidate** when
they share a cause (a library cause ID, or an outside-library cause with the same normalised
text) and at least one component; the relation is transitive, so a candidate is a connected
group. Its **representative** is the member of the earliest pass with the best rank (then the
lowest ID); its **agreement** is how many passes named it, out of how many ran, shown as words
and never as a probability (Xiong et al. 2024). The **holistic order** fuses the passes' ranks
by reciprocal rank fusion (Cormack et al. 2009), one rank per pass (the best, when a pass named
the candidate twice), ties broken by the representative's pass, rank and ID. A candidate's ID
is built from its members' IDs.

`ordered` gives the representatives in holistic order: on a one-pass run that is the rank
order, so every reader of the hypothesis list behaves as before.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from guideword.schema import ids
from guideword.schema.records import OUTSIDE_LIBRARY, Hypothesis

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class Candidate:
    id: str
    representative: Hypothesis
    # every member, by pass then rank then ID
    members: tuple[Hypothesis, ...]
    # the best rank each pass gave it
    best_rank_by_pass: Mapping[int, int]
    score: float

    @property
    def passes_named(self) -> int:
        return len(self.best_rank_by_pass)

    def agreement(self, passes_run: int) -> str:
        return f"named in {self.passes_named} of {passes_run} passes"


def cause_key(hypothesis: Hypothesis) -> str:
    """What two hypotheses must share to be one cause: the library ID, or the normalised
    outside-library text."""
    if hypothesis.cause_id == OUTSIDE_LIBRARY:
        return f"{OUTSIDE_LIBRARY}:{ids.normalise_text(hypothesis.cause_text or '')}"
    return hypothesis.cause_id


def _sort_key(h: Hypothesis) -> tuple[int, int, str]:
    return (h.pass_number, h.rank, h.id)


def _groups(hypotheses: Sequence[Hypothesis]) -> list[list[Hypothesis]]:
    """Connected groups under "same cause and a shared component", in a stable order."""
    members = sorted(hypotheses, key=_sort_key)
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i, a in enumerate(members):
        for j in range(i + 1, len(members)):
            b = members[j]
            if cause_key(a) == cause_key(b) and set(a.component_ids) & set(b.component_ids):
                union(i, j)
    grouped: dict[int, list[Hypothesis]] = {}
    for i, h in enumerate(members):
        grouped.setdefault(find(i), []).append(h)
    return [grouped[root] for root in sorted(grouped)]


def rrf_scores(
    ranks_by_item: Mapping[str, Iterable[int]], k: int = DEFAULT_RRF_K
) -> dict[str, float]:
    """Reciprocal rank fusion: each listing adds 1 / (k + rank)."""
    if k < 1:
        raise ValueError("the RRF constant is at least 1")
    return {item: sum(1.0 / (k + rank) for rank in ranks) for item, ranks in ranks_by_item.items()}


def candidates(hypotheses: Sequence[Hypothesis], *, rrf_k: int = DEFAULT_RRF_K) -> list[Candidate]:
    """The candidates in holistic order."""
    found: list[Candidate] = []
    for group in _groups(hypotheses):
        best: dict[int, int] = {}
        for h in group:
            best[h.pass_number] = min(best.get(h.pass_number, h.rank), h.rank)
        score = rrf_scores({"c": best.values()}, rrf_k)["c"]
        found.append(
            Candidate(
                id=ids.candidate_id([h.id for h in group]),
                representative=group[0],
                members=tuple(group),
                best_rank_by_pass=dict(sorted(best.items())),
                score=score,
            )
        )
    return sorted(found, key=lambda c: (-c.score, _sort_key(c.representative)))


def ordered(hypotheses: Sequence[Hypothesis], *, rrf_k: int = DEFAULT_RRF_K) -> list[Hypothesis]:
    """One representative per candidate, in holistic order; the rank order on a one-pass run."""
    return [c.representative for c in candidates(hypotheses, rrf_k=rrf_k)]


def position_of(hypotheses: Sequence[Hypothesis], *, rrf_k: int = DEFAULT_RRF_K) -> dict[str, int]:
    """Each hypothesis ID's 1-based place in the holistic order (members share their
    candidate's place)."""
    places: dict[str, int] = {}
    for place, candidate in enumerate(candidates(hypotheses, rrf_k=rrf_k), start=1):
        for member in candidate.members:
            places[member.id] = place
    return places
