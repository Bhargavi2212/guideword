"""Overrides, checked when made and applied on read (spec 3.5; Phase 3 plan PR 6, Q14, Q17, G1,
G2, G6). The records themselves are never changed; a view applies the engineer's overrides."""

from typing import Any

import pytest

from guideword.config import Config
from guideword.reference import ReferenceSet
from guideword.review.overrides import (
    ENGINEER_ASSERTS_MANAGED,
    OverrideRefused,
    RunRecords,
    check_override,
    effective_finding,
    effective_lopa,
    effective_question,
    effective_recommendation,
    new_override,
    override_state,
)
from guideword.schema import ids
from guideword.schema.enums import (
    OverrideAction,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    SeverityClass,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Question, Recommendation, Section

from .conftest import NOW, RUN, override, record_for

TOLERANCE = 1e-9


def _records(
    example: dict[str, Any],
    letter: str,
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
    **more: Any,
) -> RunRecords:
    record = record_for(
        example, letter, lead=lead, section=section, plant=plant, ref=ref, config=config
    )
    return RunRecords(
        findings=[lead],
        chains=[],
        lopa_records=[record],
        recommendations=more.get("recommendations", []),
        questions=more.get("questions", []),
        sections=[section],
        overrides=more.get("overrides", []),
    )


def _row_pfd(ref: ReferenceSet, row_id: str) -> float:
    return next(r.pfd for r in ref.protection_layers if r.id == row_id)


def _tolerable(ref: ReferenceSet, severity: SeverityClass) -> float:
    return next(
        t.tolerable_per_year for t in ref.tolerable_frequencies if t.severity_class == severity
    )


# --- change_credit (G1) -----------------------------------------------------------------------


def test_change_credit_uses_the_layers_row_pfd(
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    """Variant A credits both layers (gap 10); the engineer removes SG-TRIP's credit, then
    gives it back: the row's pfd, never a number of the engineer's."""
    records = _records(example, "A", lead, section, plant, ref, config)
    record = records.lopa_records[0]
    assert record.gap == pytest.approx(10.0, rel=TOLERANCE)
    off = override(
        record.id, OverrideAction.CHANGE_CREDIT, {"layer_id": "SG-TRIP", "credited": False}
    )
    view = effective_lopa(record, [off], lead.severity_class, plant, ref)
    trip = next(layer for layer in view.layers if layer.layer_id == "SG-TRIP")
    assert trip.credited is False and trip.pfd is None and off.id in trip.reason
    assert view.gap == pytest.approx(100.0, rel=TOLERANCE)
    on = override(
        record.id,
        OverrideAction.CHANGE_CREDIT,
        {"layer_id": "SG-TRIP", "credited": True},
        replaces=off.id,
    )
    again = effective_lopa(record, [off, on], lead.severity_class, plant, ref)
    trip = next(layer for layer in again.layers if layer.layer_id == "SG-TRIP")
    assert trip.credited is True and trip.pfd == _row_pfd(ref, "IPL-SIS-SIL1")
    assert on.id in trip.reason
    assert again.gap == pytest.approx(10.0, rel=TOLERANCE)
    # the stored record is not touched
    assert record.gap == pytest.approx(10.0, rel=TOLERANCE)


def test_change_credit_on_a_relief_device_uses_the_full_pfd_and_records_the_assertion(
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    """Variant B: Ultra says PSV-1 does not apply (gap 1000); the engineer credits it."""
    records = _records(example, "B", lead, section, plant, ref, config)
    record = records.lopa_records[0]
    assert record.gap == pytest.approx(1000.0, rel=TOLERANCE)
    given = override(
        record.id,
        OverrideAction.CHANGE_CREDIT,
        {"layer_id": "PSV-1", "credited": True},
        reason="the relief is sized for this case",
    )
    view = effective_lopa(record, [given], lead.severity_class, plant, ref)
    psv = next(layer for layer in view.layers if layer.layer_id == "PSV-1")
    assert psv.credited is True and psv.pfd == _row_pfd(ref, "IPL-PRV")
    assert ENGINEER_ASSERTS_MANAGED in psv.reason and given.id in psv.reason
    # Ultra's own yes or no and reason stay as they were
    original = next(layer for layer in record.layers if layer.layer_id == "PSV-1")
    assert (psv.applies, psv.argument) == (original.applies, original.argument)
    assert view.gap == pytest.approx(10.0, rel=TOLERANCE)
    # the override keeps only the engineer's own reason
    assert given.reason == "the relief is sized for this case"


def test_change_credit_on_a_layer_without_a_row_is_422(
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    no_kind = plant.model_copy(
        update={
            "relief_devices": [
                d.model_copy(update={"kind": None}) if d.id == "PSV-1" else d
                for d in plant.relief_devices
            ]
        }
    )
    records = _records(example, "A", lead, section, no_kind, ref, config)
    record = records.lopa_records[0]
    request = (record.id, OverrideAction.CHANGE_CREDIT, {"layer_id": "PSV-1", "credited": True})
    with pytest.raises(OverrideRefused, match="no protection_layers row") as refused:
        check_override(*request, records, no_kind, ref)
    assert refused.value.status == 422


# --- change_severity --------------------------------------------------------------------------


def test_change_severity_recomputes_tolerable_and_gap(
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    records = _records(example, "A", lead, section, plant, ref, config)
    record = records.lopa_records[0]
    raised = override(lead.id, OverrideAction.CHANGE_SEVERITY, {"severity_class": "S5"})
    finding = effective_finding(lead, [raised])
    assert finding.severity_class == SeverityClass.S5
    assert lead.severity_class == SeverityClass.S4  # the record is unchanged
    view = effective_lopa(record, [], finding.severity_class, plant, ref)
    tolerable = _tolerable(ref, SeverityClass.S5)
    assert view.severity_class == SeverityClass.S5
    assert view.tolerable_per_year == tolerable
    assert record.mitigated_frequency_per_year is not None
    assert view.gap == pytest.approx(record.mitigated_frequency_per_year / tolerable, rel=TOLERANCE)


# --- the other actions ------------------------------------------------------------------------


def test_edit_and_answer_apply_on_read_and_records_stay(lead: Finding) -> None:
    edit = override(lead.id, OverrideAction.EDIT, {"consequence": "the batch boils over"})
    assert effective_finding(lead, [edit]).consequence == "the batch boils over"
    assert lead.consequence != "the batch boils over"
    rec = Recommendation(
        id=ids.recommendation_id(lead.id, "add a trip"),
        run_id=RUN,
        target_id=lead.id,
        action="add a trip",
        reason="r",
        model_call_id="mc:r",
    )
    changed = override(rec.id, OverrideAction.EDIT, {"action": "add an independent trip"})
    assert effective_recommendation(rec, [changed]).action == "add an independent trip"
    question = Question(
        id=ids.engineer_question_id("S-MX-1", "What if the lid is left open?"),
        run_id=RUN,
        kind=QuestionKind.ENGINEER,
        origin=QuestionOrigin.ENGINEER,
        status=QuestionStatus.OPEN,
        section_id="S-MX-1",
        text="What if the lid is left open?",
    )
    answered = override(question.id, OverrideAction.ANSWER, {"text": "vapour reaches the hall"})
    assert effective_question(question, [answered]).status == QuestionStatus.ANSWERED
    assert question.status == QuestionStatus.OPEN


def test_answered_engineer_question_counts_as_checked_on_read() -> None:
    from guideword.questions.coverage import coverage  # noqa: PLC0415

    question = Question(
        id=ids.engineer_question_id("S-MX-1", "What if?"),
        run_id=RUN,
        kind=QuestionKind.ENGINEER,
        origin=QuestionOrigin.ENGINEER,
        status=QuestionStatus.OPEN,
        section_id="S-MX-1",
        text="What if?",
    )
    answered = override(question.id, OverrideAction.ANSWER, {"text": "nothing"})
    lines, _ = coverage([], [effective_question(question, [answered])], [])
    engineer = next(line for line in lines if line.list == QuestionKind.ENGINEER.value)
    assert (engineer.total, engineer.checked) == (1, 1)


def test_a_rejected_row_stays_listed_as_rejected(lead: Finding) -> None:
    rejected = override(lead.id, OverrideAction.REJECT, None)
    assert override_state([rejected]) == "rejected"
    # nothing is removed: the finding is still there, unchanged
    assert effective_finding(lead, [rejected]) == lead
    accepted = override(lead.id, OverrideAction.ACCEPT, None, replaces=rejected.id)
    assert override_state([rejected, accepted]) == "accepted"
    assert override_state([]) == "none"


# --- checked when made (G2, Q17) ----------------------------------------------------------------


def test_an_override_replaces_the_latest_on_its_target(
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    records = _records(example, "A", lead, section, plant, ref, config)
    first = new_override(
        RUN, lead.id, OverrideAction.ACCEPT, None, "fine", "Bhargavi", NOW, records, plant, ref
    )
    assert first.replaces is None
    records = records.model_copy(update={"overrides": [first]})
    second = new_override(
        RUN, lead.id, OverrideAction.REJECT, None, "no", "Bhargavi", NOW, records, plant, ref
    )
    assert second.replaces == first.id
    assert second.id == ids.override_id(lead.id, OverrideAction.REJECT, None, replaces=first.id)


@pytest.mark.parametrize(
    ("target", "action", "value", "status"),
    [
        ("f:none", OverrideAction.ACCEPT, None, 404),
        ("lopa", OverrideAction.CHANGE_CREDIT, {"layer_id": "NOPE", "credited": True}, 422),
        ("section", OverrideAction.CHANGE_SEVERITY, {"severity_class": "S5"}, 422),
        ("finding", OverrideAction.EDIT, {"action": "x"}, 422),
        ("finding", OverrideAction.EDIT, {"purpose": "x"}, 422),
        ("finding", OverrideAction.ANSWER, {"text": "x"}, 422),
        ("finding", OverrideAction.CHANGE_CREDIT, {"layer_id": "SG-TRIP", "credited": True}, 422),
    ],
)
def test_overrides_that_do_not_fit_their_target_are_refused(
    target: str,
    action: OverrideAction,
    value: Any,
    status: int,
    example: dict[str, Any],
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> None:
    records = _records(example, "A", lead, section, plant, ref, config)
    target_id = {
        "lopa": records.lopa_records[0].id,
        "section": section.id,
        "finding": lead.id,
    }.get(target, target)
    with pytest.raises(OverrideRefused) as refused:
        check_override(target_id, action, value, records, plant, ref)
    assert refused.value.status == status
