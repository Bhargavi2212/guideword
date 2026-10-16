"""The gateway (spec 2.2; plan R13, R14, R17, R31, R34): fake transport only, no network."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from guideword.config import Config, load_config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.gateway.fake import FakeTransport, catalog_for, fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import ToolCallRequest, TransportError
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse, Environment, RunStatus, Tier
from guideword.schema.records import SpendEntry

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
MESSAGES = [{"role": "user", "content": "Is the sky blue? Answer yes or no."}]


class Verdict(BaseModel):
    verdict: str
    reason: str


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture
def sessions(tmp_path: Path) -> Any:
    return make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


Build = Callable[..., tuple[Gateway, FakeTransport]]


@pytest.fixture
def build(config: Config, sessions: Any, ledger_path: Path) -> Build:
    def _build(
        script: Callable[[str, dict[str, Any]], Any], **kwargs: Any
    ) -> tuple[Gateway, FakeTransport]:
        return fake_gateway(
            config, script, sessions=sessions, ledger_path=ledger_path, clock=lambda: NOW, **kwargs
        )

    return _build


def _ok(job: str, request: dict[str, Any]) -> Any:
    return reply({"verdict": "yes", "reason": "it is"})


def _call(gateway: Gateway, **kwargs: Any) -> Any:
    args: dict[str, Any] = {
        "job": "specialist_bulk",
        "prompt_version": "test/v1",
        "messages": MESSAGES,
        "schema": Verdict,
    }
    args.update(kwargs)
    return gateway.call(**args)


# --- route ------------------------------------------------------------------------------------


def test_routes_job_to_its_tier_and_model(build: Build, config: Config) -> None:
    gateway, transport = build(_ok)
    result = _call(gateway)
    assert (result.tier, result.model_id) == (
        Tier.LIGHTNING,
        config.models.tiers[Tier.LIGHTNING].expected_id,
    )
    assert transport.sent[0][1]["model"] == result.model_id


def test_missing_tier_falls_back_and_logs(
    build: Build, config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    models = [
        m for m in catalog_for(config) if m["id"] != config.models.tiers[Tier.LIGHTNING].expected_id
    ]
    gateway, _ = build(_ok, models=models)
    result = _call(gateway)
    assert (result.tier, result.fell_back_from) == (Tier.SUPER, (Tier.LIGHTNING,))
    assert any(r.getMessage() == "model tier fell back" for r in caplog.records)


def test_past_shutdown_date_counts_as_missing(build: Build, config: Config) -> None:
    gateway, _ = build(_ok, models=catalog_for(config, lightning="2026-10-01"))
    assert _call(gateway).tier == Tier.SUPER
    later, _ = build(_ok, models=catalog_for(config, lightning="2026-12-01"))
    assert _call(later).tier == Tier.LIGHTNING


def test_model_list_fetched_once(build: Build) -> None:
    gateway, transport = build(_ok)
    _call(gateway)
    _call(gateway, messages=[{"role": "user", "content": "again"}])
    assert transport.model_list_calls == 1


def test_tier_override_for_the_four_tier_sample(build: Build) -> None:
    gateway, _ = build(_ok)
    assert _call(gateway, tier=Tier.NANO).tier == Tier.NANO


# --- request settings -------------------------------------------------------------------------


def test_request_carries_schema_max_tokens_and_reasoning_off(build: Build, config: Config) -> None:
    gateway, transport = build(_ok)
    _call(gateway)
    request = transport.sent[0][1]
    assert request["max_tokens"] == config.caps.run.max_tokens["specialist_bulk"]
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_reasoning_tiers_send_no_thinking_switch(build: Build) -> None:
    gateway, transport = build(_ok)
    _call(gateway, job="orchestrator")
    assert "extra_body" not in transport.sent[0][1]


def test_unknown_job_max_tokens_is_refused_before_sending(build: Build) -> None:
    gateway, transport = build(_ok)
    with pytest.raises(KeyError):
        _call(gateway, job="connector")
    assert transport.sent == []


# --- cache ------------------------------------------------------------------------------------


def test_second_identical_call_costs_zero_and_is_a_hit(build: Build, ledger_path: Path) -> None:
    gateway, transport = build(_ok)
    run = RunBudget("run:test", 0.0, 1.0)
    first = _call(gateway, run=run)
    second = _call(gateway, run=run)
    assert len(transport.sent) == 1
    assert (first.cache_hit, second.cache_hit) == (False, True)
    assert second.cost_usd == 0 and second.model_calls[0].cost_usd == 0
    assert second.model_calls[0].cache_hit is True
    assert second.value == first.value
    assert len(LaptopLedger(ledger_path).entries()) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"prompt_version": "test/v2"},
        {"messages": [{"role": "user", "content": "Is the sky blue? Answer yes or no!"}]},
        {"job": "specialist_hard"},
    ],
)
def test_prompt_version_or_one_character_or_max_tokens_change_misses(
    build: Build, change: dict[str, Any]
) -> None:
    """`specialist_hard` routes to another tier with other max_tokens and reasoning (R14)."""
    gateway, transport = build(_ok)
    _call(gateway)
    _call(gateway, **change)
    assert len(transport.sent) == 2


def test_crash_after_a_call_repeats_no_call(build: Build, sessions: Any) -> None:
    """Moved from PR 1: a step that pays for a call and then fails; the retry is a cache hit."""
    from guideword.runs.machine import StepResult, advance  # noqa: PLC0415
    from guideword.runs.store import RunRepository, StepWriter  # noqa: PLC0415

    gateway, transport = build(_ok)
    runs = RunRepository(sessions, lambda: NOW)
    run_id = _make_run(runs)
    attempts: list[int] = []

    def stepper(run: Any, writer: StepWriter) -> StepResult:
        result = _call(gateway, run=RunBudget(run.id, run.spent_usd, run.spend_cap_usd))
        for call in result.model_calls:
            writer.add_model_call(call)
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("process killed after the call")
        return StepResult()

    with pytest.raises(RuntimeError):
        advance(runs, run_id, {"analysis": stepper})
    advance(runs, run_id, {"analysis": stepper})
    assert len(transport.sent) == 1
    assert [c.cache_hit for c in runs.model_calls(run_id)] == [True]


def test_refusal_stops_the_run_with_cap_hit(build: Build, sessions: Any) -> None:
    """Over the run cap: refused, nothing sent, the run is stopped_cap with a cap_hit event."""
    from guideword.runs.machine import advance, stop_for_refusal  # noqa: PLC0415
    from guideword.runs.store import RunRepository, StepWriter  # noqa: PLC0415
    from guideword.schema.enums import EventType  # noqa: PLC0415

    gateway, transport = build(_ok)
    runs = RunRepository(sessions, lambda: NOW)
    run_id = _make_run(runs)

    def stepper(run: Any, writer: StepWriter) -> Any:
        try:
            _call(gateway, run=RunBudget(run.id, run.spent_usd, 0.0001))
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        raise AssertionError("the call should have been refused")

    assert advance(runs, run_id, {"analysis": stepper}) == RunStatus.STOPPED_CAP
    assert transport.sent == []
    assert EventType.CAP_HIT in [e.type for e in runs.events(run_id)]


def test_fallback_is_on_the_model_call_event(build: Build, config: Config, sessions: Any) -> None:
    from guideword.runs.machine import StepResult, advance  # noqa: PLC0415
    from guideword.runs.store import RunRepository, StepWriter  # noqa: PLC0415
    from guideword.schema.enums import EventType  # noqa: PLC0415

    models = [
        m for m in catalog_for(config) if m["id"] != config.models.tiers[Tier.LIGHTNING].expected_id
    ]
    gateway, _ = build(_ok, models=models)
    runs = RunRepository(sessions, lambda: NOW)
    run_id = _make_run(runs)

    def stepper(run: Any, writer: StepWriter) -> StepResult:
        result = _call(gateway, run=RunBudget(run.id, run.spent_usd, run.spend_cap_usd))
        for call in result.model_calls:
            writer.add_model_call(call, fell_back_from=result.fell_back_from)
        return StepResult()

    advance(runs, run_id, {"analysis": stepper})
    event = next(e for e in runs.events(run_id) if e.type == EventType.MODEL_CALL)
    assert event.payload["fell_back_from"] == ["lightning"]


def _make_run(runs: Any) -> str:
    """A run row for the crash test, without a plant (the store does not need one here)."""
    from guideword.runs.db import PlantRow, RunRow  # noqa: PLC0415
    from guideword.schema import ids  # noqa: PLC0415
    from guideword.schema.enums import RunLabelKind  # noqa: PLC0415
    from guideword.schema.records import Run, RunLabel  # noqa: PLC0415

    inputs = {
        "plant_id": "plant:x:0",
        "section_snapshot": [],
        "reference_versions": {},
        "routing_config": {},
        "caps": {},
        "prompt_versions": {},
        "mode": "full",
    }
    run = Run(
        id=ids.run_id(inputs, [], spend_cap_usd=1.0),
        plant_record_id="plant:x:0",
        attempt=1,
        section_snapshot=[],
        status=RunStatus.RUNNING,
        step="analysis",
        mode="full",
        spend_cap_usd=1.0,
        reference_versions={},
        routing_config={},
        caps={},
        prompt_versions={},
        label=RunLabel(kind=RunLabelKind.LIVE),
    )
    with runs._sessions.begin() as session:  # noqa: SLF001
        session.add(
            PlantRow(id="plant:x:0", plant_id="x", status="sections_confirmed", plant_file={})
        )
        session.add(
            RunRow(
                id=run.id,
                base_id=run.id,
                attempt=1,
                plant_record_id="plant:x:0",
                status=run.status.value,
                record=run.model_dump(mode="json"),
                sections=[],
            )
        )
    return run.id


# --- budget guard -----------------------------------------------------------------------------


def test_over_run_cap_refused_run_stopped_cap_nothing_sent(build: Build) -> None:
    gateway, transport = build(_ok)
    with pytest.raises(BudgetRefused) as refused:
        _call(gateway, run=RunBudget("run:test", 0.0, 0.0001))
    assert refused.value.status == RunStatus.STOPPED_CAP
    assert transport.sent == []


def _spend(ledger_path: Path, use: BudgetUse, amount: float, phase: str = "2") -> None:
    LaptopLedger(ledger_path).append(
        SpendEntry(
            ts=NOW,
            kind="model",
            environment=Environment.LAPTOP,
            phase=phase,
            use=use,
            cost_usd=amount,
            script="test",
            purpose="earlier spend",
        )
    )


def test_over_use_or_environment_allowance_refused_stopped_budget(
    build: Build, ledger_path: Path
) -> None:
    _spend(ledger_path, BudgetUse.DEVELOPMENT, 5.0, phase="0")
    gateway, transport = build(_ok)
    with pytest.raises(BudgetRefused) as refused:
        _call(gateway)
    assert refused.value.status == RunStatus.STOPPED_BUDGET
    assert "development" in str(refused.value)
    assert transport.sent == []


def test_over_the_laptop_allowance_refused(build: Build, ledger_path: Path) -> None:
    """Uses sum to the laptop allowance, so only spend booked outside the laptop's own uses
    can reach it first; the check still has to hold on its own."""
    _spend(ledger_path, BudgetUse.JUDGING, 18.9999, phase="7")
    gateway, transport = build(_ok)
    with pytest.raises(BudgetRefused, match="laptop allowance") as refused:
        _call(gateway)
    assert refused.value.status == RunStatus.STOPPED_BUDGET
    assert transport.sent == []


def test_over_phase_cap_refused(build: Build, ledger_path: Path) -> None:
    """R17: the gateway also enforces the phase cap."""
    _spend(ledger_path, BudgetUse.TEST_5, 4.0)
    _spend(ledger_path, BudgetUse.DEVELOPMENT, 0.99999)
    gateway, transport = build(_ok)
    with pytest.raises(BudgetRefused, match="phase 2 cap"):
        _call(gateway)
    assert transport.sent == []


def test_phase_without_a_cap_cannot_call(build: Build) -> None:
    gateway, transport = build(_ok, phase="9")
    with pytest.raises(BudgetRefused, match="no live-call cap"):
        _call(gateway)
    assert transport.sent == []


def test_use_of_the_other_environment_is_refused(build: Build) -> None:
    """A judging (hosted) call on the laptop ledger never sends."""
    gateway, transport = build(_ok, use=BudgetUse.JUDGING)
    with pytest.raises(BudgetRefused, match="hosted"):
        _call(gateway)
    assert transport.sent == []


def test_holds_count_calls_in_flight(build: Build) -> None:
    """Two parallel calls whose estimates together pass the run limit: one is refused."""
    release = threading.Event()
    started = threading.Event()

    def slow(job: str, request: dict[str, Any]) -> Any:
        started.set()
        release.wait(5)
        return reply({"verdict": "yes", "reason": "r"})

    gateway, _ = build(slow)
    one = _call  # the estimate of one Lightning call with these messages
    limit = 0.0025  # above one estimate (~0.0015), below two
    errors: list[BaseException] = []

    def first() -> None:
        try:
            one(gateway, run=RunBudget("run:test", 0.0, limit))
        except BaseException as error:  # noqa: BLE001 - collected for the assert
            errors.append(error)

    thread = threading.Thread(target=first)
    thread.start()
    assert started.wait(5)
    with pytest.raises(BudgetRefused):
        _call(
            gateway,
            run=RunBudget("run:test", 0.0, limit),
            messages=[{"role": "user", "content": "x"}],
        )
    release.set()
    thread.join(5)
    assert errors == []


# --- retries ----------------------------------------------------------------------------------


def test_429_then_success_is_one_model_call_with_attempts_2(build: Build) -> None:
    calls: list[int] = []
    waits: list[float] = []

    def flaky(job: str, request: dict[str, Any]) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise TransportError("rate limited", 429)
        return reply({"verdict": "yes", "reason": "r"})

    gateway, _ = build(flaky, sleep=waits.append)
    result = _call(gateway, run=RunBudget("run:test", 0.0, 1.0))
    assert result.outcome == "ok"
    assert [c.attempts for c in result.model_calls] == [2]
    assert waits == [1.0]


def test_three_5xx_is_outcome_error(build: Build, ledger_path: Path) -> None:
    def down(job: str, request: dict[str, Any]) -> Any:
        raise TransportError("server error", 503)

    waits: list[float] = []
    gateway, transport = build(down, sleep=waits.append)
    result = _call(gateway, run=RunBudget("run:test", 0.0, 1.0))
    assert result.outcome == "error"
    assert len(transport.sent) == 3
    assert waits == [1.0, 2.0]
    assert result.model_calls[0].attempts == 3
    assert LaptopLedger(ledger_path).entries() == []


def test_a_400_is_not_retried(build: Build) -> None:
    def bad(job: str, request: dict[str, Any]) -> Any:
        raise TransportError("bad request", 400)

    gateway, transport = build(bad)
    assert _call(gateway).outcome == "error"
    assert len(transport.sent) == 1


def test_no_real_sleep(build: Build) -> None:
    """The waits go through the injected sleeper; tests never sleep."""
    waits: list[float] = []

    def down(job: str, request: dict[str, Any]) -> Any:
        raise TransportError("server error", 500)

    gateway, _ = build(down, sleep=waits.append)
    _call(gateway)
    assert waits == [1.0, 2.0]


# --- validation -------------------------------------------------------------------------------


def test_length_is_truncated_and_not_parsed(build: Build) -> None:
    gateway, transport = build(lambda j, r: reply('{"verdict": "ye', finish_reason="length"))
    result = _call(gateway, run=RunBudget("run:test", 0.0, 1.0))
    assert (result.outcome, result.value) == ("truncated", None)
    assert len(transport.sent) == 1
    assert result.model_calls[0].outcome == "truncated"


def test_think_block_stripped_reasoning_logged(build: Build) -> None:
    gateway, _ = build(
        lambda j, r: reply(
            '<think>let me see</think>{"verdict": "yes", "reason": "r"}', reasoning="side text"
        )
    )
    result = _call(gateway, run=RunBudget("run:test", 0.0, 1.0))
    assert result.outcome == "ok"
    assert result.value == Verdict(verdict="yes", reason="r")
    assert result.model_calls[0].reasoning_text == "side text"


def test_invalid_json_retried_once_with_the_error_then_invalid(build: Build) -> None:
    gateway, transport = build(lambda j, r: reply("not json"))
    result = _call(gateway, run=RunBudget("run:test", 0.0, 1.0))
    assert result.outcome == "invalid"
    assert len(transport.sent) == 2
    retry_messages = transport.sent[1][1]["messages"]
    assert "not valid" in retry_messages[-1]["content"]
    assert [c.outcome for c in result.model_calls] == ["invalid", "invalid"]
    assert result.model_calls[0].id != result.model_calls[1].id


def test_invalid_then_valid_is_ok(build: Build) -> None:
    answers = iter([reply("not json"), reply({"verdict": "no", "reason": "r"})])
    gateway, _ = build(lambda j, r: next(answers))
    result = _call(gateway)
    assert (result.outcome, result.value) == ("ok", Verdict(verdict="no", reason="r"))


def test_unknown_id_is_invalid(build: Build) -> None:
    def only_known(value: Verdict) -> None:
        if value.verdict not in {"yes", "no"}:
            raise ValueError(f"unknown ID {value.verdict}")

    gateway, _ = build(lambda j, r: reply({"verdict": "Q-999", "reason": "r"}))
    result = _call(gateway, validator=only_known)
    assert result.outcome == "invalid"
    assert "unknown ID Q-999" in (result.error or "")


def test_tool_calls_are_returned(build: Build) -> None:
    call = ToolCallRequest(call_id="c1", name="check_coverage", arguments="{}")
    gateway, transport = build(lambda j, r: reply(tool_calls=(call,)))
    tools = [
        {
            "type": "function",
            "function": {"name": "check_coverage", "parameters": {"type": "object"}},
        }
    ]
    result = gateway.call(
        job="orchestrator",
        prompt_version="orchestrator/v1",
        messages=MESSAGES,
        tools=tools,
        tool_choice="required",
    )
    assert result.outcome == "ok"
    assert result.tool_calls == (call,)
    assert transport.sent[0][1]["tool_choice"] == "required"


# --- ledger -----------------------------------------------------------------------------------


def test_ledger_line_after_every_non_cached_call_with_job_use_phase(
    build: Build, ledger_path: Path
) -> None:
    gateway, _ = build(_ok, use=BudgetUse.TEST_5)
    _call(gateway, run=RunBudget("run:abc", 0.0, 1.0))
    _call(gateway, run=RunBudget("run:abc", 0.0, 1.0))
    entries = LaptopLedger(ledger_path).entries()
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.use, entry.phase, entry.script) == (BudgetUse.TEST_5, "2", "gateway")
    assert entry.purpose == "specialist_bulk run:abc"
    assert entry.cost_usd > 0


def test_real_cost_comes_from_usage(build: Build, config: Config) -> None:
    gateway, _ = build(
        lambda j, r: reply({"verdict": "y", "reason": "r"}, input_tokens=1000, output_tokens=500)
    )
    result = _call(gateway)
    prices = config.models.tiers[Tier.LIGHTNING]
    assert result.cost_usd == pytest.approx(
        (1000 * prices.input_usd_per_1m + 500 * prices.output_usd_per_1m) / 1e6
    )


def test_a_request_already_made_in_the_run_is_refused_before_cache_or_send(
    build: Build,
) -> None:
    """The backstop: the same request twice in one run could only repeat the stored answer and
    would overwrite its record, so the gateway refuses it before looking anything up."""
    from guideword.gateway.client import RepeatedRequest  # noqa: PLC0415

    gateway, transport = build(_ok)
    run = RunBudget("run:0123456789abcdef", 0.0, 1.0)
    first = _call(gateway, run=run)
    made = frozenset(c.id for c in first.model_calls)
    with pytest.raises(RepeatedRequest, match=next(iter(made))):
        _call(gateway, run=run, made=made)
    assert len(transport.sent) == 1
    # a different request in the same run goes through
    other = _call(gateway, run=run, made=made, messages=[{"role": "user", "content": "Other?"}])
    assert other.outcome == "ok"
