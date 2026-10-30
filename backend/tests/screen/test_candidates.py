"""Candidates across the holistic passes (Phase 9 spec 9.3): hypotheses with the same cause and
a shared component are one candidate; its agreement counts passes; the holistic order fuses the
passes' ranks by reciprocal rank fusion. Code only, deterministic, content-keyed IDs."""

from typing import Any

import pytest

from guideword.schema import ids
from guideword.schema.records import Hypothesis
from guideword.screen.candidates import Candidate, candidates, ordered, rrf_scores

RUN = "run:0123456789abcdef"


def hyp(
    rank: int,
    components: list[str],
    cause: str = "C14",
    *,
    pass_number: int = 1,
    mechanism: str | None = None,
    cause_text: str | None = None,
    kind: str = "operator",
) -> Hypothesis:
    text = mechanism or f"mechanism {cause} {components[0]}"
    return Hypothesis(
        id=ids.hypothesis_id(rank, text, components, pass_number=pass_number),
        run_id=RUN,
        rank=rank,
        mechanism=text,
        component_ids=components,
        failing_component_type=kind,  # type: ignore[arg-type]
        cause_id=cause,
        cause_text=cause_text,
        consequence="a consequence",
        reason="a reason",
        pass_number=pass_number,
    )


def test_same_cause_and_a_shared_component_is_one_candidate() -> None:
    a = hyp(1, ["MX-1", "P-1"], pass_number=1)
    b = hyp(2, ["P-1"], pass_number=2)
    found = candidates([a, b])
    assert len(found) == 1
    assert found[0].members == (a, b)
    assert found[0].representative is a


def test_same_cause_without_a_shared_component_is_two_candidates() -> None:
    a = hyp(1, ["MX-1"], pass_number=1)
    b = hyp(1, ["P-1"], pass_number=2)
    assert len(candidates([a, b])) == 2


def test_a_shared_component_with_a_different_cause_is_two_candidates() -> None:
    a = hyp(1, ["MX-1"], "C14", pass_number=1)
    b = hyp(1, ["MX-1"], "C22", pass_number=2, kind="external")
    assert len(candidates([a, b])) == 2


def test_outside_library_causes_group_by_their_normalised_text() -> None:
    a = hyp(1, ["MX-1"], "outside_library", pass_number=1, cause_text="Wrong  tote — charged")
    b = hyp(1, ["MX-1"], "outside_library", pass_number=2, cause_text="wrong tote - charged")
    c = hyp(2, ["MX-1"], "outside_library", pass_number=2, cause_text="valve left open")
    found = candidates([a, b, c])
    assert [len(x.members) for x in found] == [2, 1]


def test_grouping_is_transitive_and_ignores_input_order() -> None:
    a = hyp(1, ["MX-1"], pass_number=1)
    b = hyp(1, ["MX-1", "P-1"], pass_number=2)
    c = hyp(1, ["P-1"], pass_number=3)
    forward = candidates([a, b, c])
    backward = candidates([c, b, a])
    assert len(forward) == 1 and forward[0].members == (a, b, c)
    assert [x.id for x in forward] == [x.id for x in backward]
    assert forward[0].representative is a


def test_the_candidate_id_is_built_from_its_members() -> None:
    a = hyp(1, ["MX-1"], pass_number=1)
    b = hyp(2, ["MX-1"], pass_number=2)
    one = candidates([a, b])[0]
    assert one.id == ids.candidate_id([a.id, b.id]) == ids.candidate_id([b.id, a.id])
    assert one.id.startswith("cand:")
    assert candidates([a])[0].id != one.id


def test_agreement_counts_passes_not_hypotheses() -> None:
    a = hyp(1, ["MX-1"], pass_number=1)
    also_a = hyp(5, ["MX-1", "P-1"], pass_number=1)  # the same pass names it twice
    b = hyp(3, ["MX-1"], pass_number=3)
    one = candidates([a, also_a, b])[0]
    assert one.passes_named == 2
    assert one.agreement(3) == "named in 2 of 3 passes"
    assert one.best_rank_by_pass == {1: 1, 3: 3}


def test_rrf_matches_a_hand_computed_example() -> None:
    # A: ranks 1 and 3; B: ranks 2 and 1; C: rank 3 once. k = 60.
    scores = rrf_scores({"A": [1, 3], "B": [2, 1], "C": [3]}, k=60)
    assert scores["A"] == pytest.approx(1 / 61 + 1 / 63)
    assert scores["B"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["C"] == pytest.approx(1 / 63)
    assert sorted(scores, key=lambda x: -scores[x]) == ["B", "A", "C"]


def test_the_holistic_order_is_the_fused_order_with_ties_by_pass_rank_and_id() -> None:
    a1, a2 = hyp(1, ["MX-1"], pass_number=1), hyp(3, ["MX-1"], pass_number=2)
    b1, b2 = (
        hyp(2, ["P-1"], "C21", pass_number=1, kind="tank"),
        hyp(1, ["P-1"], "C21", pass_number=2, kind="tank"),
    )
    c1 = hyp(3, ["TOTE-1"], "C22", pass_number=1, kind="external")
    found = candidates([a1, b1, c1, b2, a2], rrf_k=60)
    assert [x.representative.id for x in found] == [b1.id, a1.id, c1.id]
    # two candidates with equal scores: the earlier pass, then the better rank, then the ID
    d = hyp(1, ["L-12"], "C20", pass_number=1, kind="pipe")
    e = hyp(1, ["L-STM"], "C20", pass_number=2, kind="pipe")
    tied = candidates([e, d], rrf_k=60)
    assert [x.representative.id for x in tied] == [d.id, e.id]


def test_a_single_pass_run_orders_exactly_as_the_rank() -> None:
    hs = [
        hyp(3, ["TOTE-1"], "C22", kind="external"),
        hyp(1, ["MX-1"]),
        hyp(2, ["P-1"], "C21", kind="tank"),
    ]
    assert [h.rank for h in ordered(hs)] == [1, 2, 3]
    assert ordered([]) == []


def test_ordered_gives_one_representative_per_candidate() -> None:
    a1, a2 = hyp(1, ["MX-1"], pass_number=1), hyp(2, ["MX-1"], pass_number=2)
    b2 = hyp(1, ["P-1"], "C21", pass_number=2, kind="tank")
    reps = ordered([a1, a2, b2])
    assert [h.id for h in reps] == [a1.id, b2.id]
    assert all(isinstance(h, Hypothesis) for h in reps)


def test_candidates_are_frozen_and_carry_their_members_by_pass() -> None:
    a = hyp(1, ["MX-1"], pass_number=2)
    one = candidates([a])[0]
    assert isinstance(one, Candidate)
    with pytest.raises(AttributeError):
        one.id = "x"  # type: ignore[misc]
    seen: dict[str, Any] = {"members": [m.pass_number for m in one.members]}
    assert seen == {"members": [2]}
