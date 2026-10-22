"""The run summary's priority lines (spec 2b.3, G15; relabelled 2026-10-22, Bhargavi).

The first number keeps its definition, which earlier reports carry (G2b E/F, Phase 3): the
dispatches' `linked_answered` counts up to and including the first dispatch that sent any
unlinked question. The second counts the checked linked questions whose answering dispatch
sent no unlinked question; a question's answering dispatch is the last first-answer dispatch
that sent it, since an answered question is never sent again."""

from datetime import UTC, datetime
from typing import Any

from guideword.runs.case import priority_summary
from guideword.schema.enums import EventType, QuestionStatus
from guideword.schema.records import Event, Hypothesis, Question

RUN = "run:0123456789abcdef"
T = datetime(2026, 10, 22, tzinfo=UTC)


def _dispatch(
    seq: int,
    sent: list[str],
    *,
    linked_answered: int,
    unlinked: int,
    level: str = "bulk",
    deferred: list[str] | None = None,
) -> Event:
    payload: dict[str, Any] = {
        "agent": "process",
        "level": level,
        "priority": True,
        "question_ids": sent,
        "linked_answered": linked_answered,
        "unlinked_sent": unlinked,
        "deferred_at_admission": [{"question_ids": deferred}] if deferred else [],
    }
    return Event(run_id=RUN, seq=seq, type=EventType.DISPATCH, payload=payload, time=T)


def _hypothesis(question_ids: list[str]) -> Hypothesis:
    return Hypothesis.model_construct(id="h:1:0123456789abcdef", question_ids=question_ids)


def _questions(statuses: dict[str, QuestionStatus]) -> list[Question]:
    return [Question.model_construct(id=q, status=s) for q, s in statuses.items()]


ANSWERED = QuestionStatus.ANSWERED


def test_a_priority_dispatch_that_sends_linked_then_unlinked_questions() -> None:
    """As on the final WG run: the first priority dispatch sends linked questions followed by
    unlinked ones, and the next sends linked ones only."""
    events = [
        _dispatch(1, ["L1", "L2", "U1", "U2"], linked_answered=2, unlinked=2),
        _dispatch(2, ["L3", "L4", "L5"], linked_answered=3, unlinked=0),
    ]
    statuses = {q: ANSWERED for q in ("L1", "L2", "L3", "L4", "L5", "U1", "U2")}
    summary = priority_summary(
        events, [_hypothesis(["L1", "L2", "L3", "L4", "L5"])], _questions(statuses)
    )
    assert summary == {
        "linked_questions": 5,
        # unchanged: up to and including the first dispatch that sent an unlinked question
        "linked_answered_before_first_unlinked": 2,
        # L1 and L2 were answered in the mixed dispatch; L3-L5 in the linked-only one
        "linked_answered_in_linked_only_dispatches": 3,
    }


def test_a_question_retried_at_hard_counts_once_in_the_dispatch_that_answered_it() -> None:
    """A batch re-asked one question at a time counts all its questions in `linked_answered`
    when any one is answered (the over-count found on the WG run); the failed ones are sent
    again at hard. The second line counts each question once, where it was answered."""
    events = [
        _dispatch(1, ["L1", "L2"], linked_answered=2, unlinked=0),
        _dispatch(2, ["L2"], linked_answered=1, unlinked=0, level="hard"),
        _dispatch(3, ["L3", "U1"], linked_answered=1, unlinked=1, level="hard"),
    ]
    statuses = {"L1": ANSWERED, "L2": ANSWERED, "L3": ANSWERED, "U1": ANSWERED}
    summary = priority_summary(events, [_hypothesis(["L1", "L2", "L3"])], _questions(statuses))
    assert summary["linked_answered_in_linked_only_dispatches"] == 2
    assert summary["linked_answered_before_first_unlinked"] == 4  # the stored counts, summed


def test_unsure_re_answers_deferred_batches_and_unchecked_questions_do_not_count() -> None:
    events = [
        _dispatch(1, ["L1", "L2"], linked_answered=1, unlinked=0, deferred=["L2"]),
        _dispatch(2, ["L1"], linked_answered=0, unlinked=0, level="unsure"),
        _dispatch(3, ["L2", "U1"], linked_answered=1, unlinked=1, level="hard"),
        _dispatch(4, ["L3"], linked_answered=0, unlinked=0),
    ]
    statuses = {
        "L1": ANSWERED,
        "L2": ANSWERED,
        "L3": QuestionStatus.FAILED,
        "U1": ANSWERED,
    }
    summary = priority_summary(events, [_hypothesis(["L1", "L2", "L3"])], _questions(statuses))
    # L1: answered in dispatch 1 (the unsure re-answer doesn't move it); L2 was deferred in
    # dispatch 1 and answered in the mixed dispatch 3; L3 failed
    assert summary["linked_answered_in_linked_only_dispatches"] == 1


def test_non_dispatch_events_are_ignored_and_seq_order_is_used() -> None:
    events = [
        Event(run_id=RUN, seq=1, type=EventType.STEP_STARTED, payload={"step": "analysis"}, time=T),
        _dispatch(3, ["L2"], linked_answered=1, unlinked=0),
        _dispatch(2, ["L1", "U1"], linked_answered=1, unlinked=1),
    ]
    statuses = {"L1": ANSWERED, "L2": ANSWERED, "U1": ANSWERED}
    summary = priority_summary(events, [_hypothesis(["L1", "L2"])], _questions(statuses))
    assert summary["linked_answered_before_first_unlinked"] == 1
    assert summary["linked_answered_in_linked_only_dispatches"] == 1
