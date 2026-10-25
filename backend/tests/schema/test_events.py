"""Event payloads (contract v1.9, Phase 5 plan B1, Q1, Q6): stamped once, chosen by the stamp."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from guideword.api.models import CoverageList
from guideword.schema.enums import EventType
from guideword.schema.events import (
    LEGACY,
    SCHEMA_V1_9,
    V1_9,
    CoverageLine,
    validate_payload,
)
from guideword.schema.records import Event

T = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
RUN = "run:aaaaaaaaaaaaaaaa"


def test_every_event_type_has_a_v1_9_model() -> None:
    assert set(V1_9) == set(EventType)


def test_every_stored_type_has_a_legacy_model() -> None:
    """`run_failed` and `hypothesis_dropped` were never stored before v1.9 (checked on
    guideword.db, 2026-10-23), so they have none; nor has `calculations_reattached`, new in
    contract v1.11."""
    assert set(EventType) - set(LEGACY) == {
        EventType.RUN_FAILED,
        EventType.HYPOTHESIS_DROPPED,
        EventType.CALCULATIONS_REATTACHED,
    }


def test_a_v1_9_payload_with_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_payload(EventType.STEP_STARTED, {"step": "analysis", "extra": 1}, SCHEMA_V1_9)
    bare = {"step": "lopa", "status": "running", "next_step": "recommendations"}
    with pytest.raises(ValidationError):
        validate_payload(EventType.STEP_FINISHED, bare | {"junk": 1}, SCHEMA_V1_9)


def test_the_model_is_chosen_by_the_stamp_alone() -> None:
    """A legacy-shaped payload passes unstamped and fails stamped: no fallback either way."""
    legacy = {"reason": "admission", "detail": "the first batch does not fit"}
    validate_payload(EventType.CAP_HIT, legacy, None)
    with pytest.raises(ValidationError):
        validate_payload(EventType.CAP_HIT, legacy, SCHEMA_V1_9)


def test_legacy_models_allow_extra_fields() -> None:
    parsed = validate_payload(EventType.STEP_STARTED, {"step": "analysis", "old": 1}, None)
    assert parsed.model_extra == {"old": 1}


def test_an_unstamped_type_with_no_legacy_model_is_refused() -> None:
    with pytest.raises(ValueError, match="legacy"):
        validate_payload(EventType.RUN_FAILED, {"step": "analysis"}, None)


def test_step_finished_picks_its_steps_model() -> None:
    base = {"status": "running", "next_step": "x"}
    off = validate_payload(
        EventType.STEP_FINISHED,
        base | {"step": "evidence", "evidence": "off", "reason": "no lines"},
        SCHEMA_V1_9,
    )
    assert type(off).__name__ == "EvidenceOff"
    with pytest.raises(ValidationError):
        # an evidence summary on another step's name
        validate_payload(
            EventType.STEP_FINISHED,
            base | {"step": "lopa", "evidence": "off", "reason": "no lines"},
            SCHEMA_V1_9,
        )


def test_cap_hit_always_names_its_cap() -> None:
    with pytest.raises(ValidationError):
        validate_payload(EventType.CAP_HIT, {"reason": "questions left open", "open": 1}, "v1.9")
    validate_payload(
        EventType.CAP_HIT, {"reason": "questions left open", "open": 1, "cap": None}, "v1.9"
    )


def test_model_call_tier_and_source_come_together() -> None:
    call = {
        "model_call_id": "mc:x",
        "job": "specialist_bulk",
        "model_id": "m",
        "cache_hit": False,
        "outcome": "ok",
        "cost_usd": 0.0,
        "cap_cost_usd": 0.0,
    }
    validate_payload(EventType.MODEL_CALL, call | {"tier": None, "tier_source": None}, "v1.9")
    with pytest.raises(ValidationError):
        validate_payload(
            EventType.MODEL_CALL, call | {"tier": "lightning", "tier_source": None}, "v1.9"
        )


def test_the_coverage_line_mirrors_the_api_coverage_list() -> None:
    assert list(CoverageLine.model_fields) == list(CoverageList.model_fields)


def test_an_event_stored_before_v1_9_reads_unstamped_and_valid() -> None:
    event = Event.model_validate(
        {"run_id": RUN, "seq": 1, "type": "step_started", "payload": {"step": "x"}, "time": T}
    )
    assert (event.payload_schema, event.payload_invalid, event.payload_error) == (
        None,
        False,
        None,
    )


# --- contract v1.11: the calculations re-attached on a stored run (review plan Q5, R0) -----------

REATTACHED = {
    "date": "2026-10-26",
    "commit": "892f0fb",
    "superseded_ids": ["ev:f:a:calculation:blocked_in_heating-EA-425B"],
    "added_ids": ["ev:f:b:calculation:blocked_in_heating-EA-425B"],
}


def test_calculations_reattached_names_its_date_commit_and_records() -> None:
    parsed = validate_payload(EventType.CALCULATIONS_REATTACHED, REATTACHED, SCHEMA_V1_9)
    assert parsed.model_dump(mode="json") == REATTACHED


@pytest.mark.parametrize(
    "change",
    [
        {"date": "26 Oct 2026"},
        {"commit": "not-a-commit"},
        {"commit": "89"},
        {"superseded_ids": [], "added_ids": []},
        {"text": "calculations re-attached"},
    ],
)
def test_calculations_reattached_refuses_a_bad_payload(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_payload(EventType.CALCULATIONS_REATTACHED, REATTACHED | change, SCHEMA_V1_9)


def test_calculations_reattached_may_only_add_or_only_supersede() -> None:
    for side in ("superseded_ids", "added_ids"):
        validate_payload(EventType.CALCULATIONS_REATTACHED, REATTACHED | {side: []}, SCHEMA_V1_9)
