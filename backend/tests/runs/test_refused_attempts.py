"""A refusal's attempts are recorded, and the ledger check beside R45 (bug fix, 2026-10-22)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from guideword.gateway.client import BudgetRefused
from guideword.reference import ReferenceSet
from guideword.runs.machine import POST_CAP, ledger_spent, stop_for_refusal
from guideword.runs.plants import PlantRepository
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, Environment, RunStatus
from guideword.schema.records import ModelCall, SpendEntry

T = datetime(2026, 10, 22, tzinfo=UTC)


def _call(run_id: str, call_id: str, cost: float, job: str = "specialist_bulk") -> ModelCall:
    return ModelCall(
        id=call_id,
        run_id=run_id,
        model_id="m",
        prompt_version="p/v1",
        job=job,
        cache_hit=False,
        outcome="invalid",
        input_tokens=1,
        output_tokens=1,
        latency_ms=0.0,
        cost_usd=cost,
        raw_response="not json",
    )


def _entry(purpose: str, cost: float) -> SpendEntry:
    return SpendEntry(
        ts=T,
        kind="model",
        environment=Environment.LAPTOP,
        phase="4",
        use=BudgetUse.DEVELOPMENT,
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=cost,
        script="gateway",
        purpose=purpose,
    )


def test_ledger_spent_sums_the_runs_own_lines() -> None:
    entries = [
        _entry("specialist_bulk run:aaaaaaaaaaaaaaaa", 0.25),
        _entry("severity_reason run:aaaaaaaaaaaaaaaa", 0.5),
        _entry("specialist_bulk run:aaaaaaaaaaaaaaaa:2", 9.0),
        _entry("smoke test", 1.0),
    ]
    assert ledger_spent(entries, "run:aaaaaaaaaaaaaaaa") == 0.75
    assert ledger_spent(entries, "run:bbbbbbbbbbbbbbbb") is None


def test_stop_for_refusal_records_the_attempts_and_their_spend(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Callable[..., str],
) -> None:
    run_record = start_run(
        plants, runs, ref, settings, plant_record_id=upload(), spend_cap_usd=1.0, mode="full"
    )
    refused = BudgetRefused("limit", RunStatus.STOPPED_CAP)
    refused.attempts = [_call(run_record.id, "mc:0123456789abcdef", 0.01)]
    refused.cost_usd, refused.cap_cost_usd = 0.01, 0.01
    with runs.step(run_record.id) as writer:
        stop_for_refusal(writer, refused)
        assert [c.id for c in writer.model_calls()] == ["mc:0123456789abcdef"]
        assert writer.run.spent_usd == pytest.approx(0.01)
        assert writer.run.cap_spent_usd == pytest.approx(0.01)
    post = BudgetRefused("limit", RunStatus.STOPPED_CAP)
    post.attempts = [_call(run_record.id, "mc:1123456789abcdef", 0.02, job="recommendation")]
    post.cost_usd, post.cap_cost_usd = 0.02, 0.02
    with runs.step(run_record.id) as writer:
        stop_for_refusal(writer, post, cap=POST_CAP)
        # a post-analysis call never counts against the analysis cap
        assert writer.run.spent_usd == pytest.approx(0.03)
        assert writer.run.cap_spent_usd == pytest.approx(0.01)


def test_spend_check_compares_a_runs_spend_with_its_ledger_lines() -> None:
    from guideword.runs.machine import spend_check
    from guideword.schema.records import Run

    run = Run.model_construct(id="run:aaaaaaaaaaaaaaaa", spent_usd=0.888)
    lines = [_entry("specialist_bulk run:aaaaaaaaaaaaaaaa", 0.888)]
    assert spend_check(run, lines) == {"spent_usd": 0.888, "ledger_usd": 0.888, "matches": True}
    # the WG final run before the fix: $0.8882 in records, $0.8965 in the ledger
    short = Run.model_construct(id="run:aaaaaaaaaaaaaaaa", spent_usd=0.8882)
    gap = [_entry("specialist_bulk run:aaaaaaaaaaaaaaaa", 0.8965)]
    assert spend_check(short, gap)["matches"] is False
    # a run the ledger has no lines for (another environment's ledger) is not compared
    assert spend_check(run, [])["matches"] is True and spend_check(run, [])["ledger_usd"] is None
