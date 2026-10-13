"""scripts/live_call.py (spec 0.3), with fake clients only: nothing here can call a paid API."""

import json
import math
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import live_call
import pytest
from pydantic import SecretStr

from guideword.config import Config, load_config
from guideword.schema.enums import Tier
from guideword.settings import Settings

KEY = "nb-live-test-key-1234567890"
TAVILY_KEY = "tv-live-test-key-0987654321"
PROMPT = "SECRET-PROMPT-TEXT please reply OK"
NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)


class FakeCompletions:
    def __init__(self, prompt_tokens: int = 100, completion_tokens: int = 20) -> None:
        self.calls: list[dict[str, Any]] = []
        self.usage = SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        self.fail_with: Exception | None = None

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.fail_with is not None:
            raise self.fail_with
        return SimpleNamespace(usage=self.usage, choices=[], model=kwargs["model"])


class FakeOpenAI:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        self.models = SimpleNamespace(
            list=lambda: SimpleNamespace(data=[SimpleNamespace(id="nvidia/model-a")])
        )


class FakeTavily:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"results": [{"url": "https://example.org", "content": "x"}]}


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _settings(nebius: str = KEY, tavily: str = TAVILY_KEY) -> Settings:
    return Settings(
        _env_file=None,
        nebius_api_key=SecretStr(nebius),
        tavily_api_key=SecretStr(tavily),
        global_budget_usd=25.0,
    )


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


@pytest.fixture
def fake() -> FakeOpenAI:
    return FakeOpenAI()


@pytest.fixture
def caller(config: Config, ledger_path: Path, fake: FakeOpenAI) -> Iterator[live_call.LiveCaller]:
    yield live_call.LiveCaller(
        settings=_settings(),
        config=config,
        ledger=live_call.Ledger(ledger_path),
        clock=lambda: NOW,
        openai_client=fake,
        tavily_client=FakeTavily(),
    )


def _chat(caller: live_call.LiveCaller, **overrides: Any) -> Any:
    args: dict[str, Any] = {
        "tier": Tier.ULTRA,
        "messages": [{"role": "user", "content": PROMPT}],
        "phase": "0",
        "use": "development",
        "purpose": "unit test",
        "max_tokens": 50,
    }
    args.update(overrides)
    return caller.chat(**args)


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- estimate -------------------------------------------------------------------------------


def test_estimate_matches_hand_computed_example(config: Config) -> None:
    messages = [{"role": "user", "content": "x" * 700}]
    estimate = live_call.estimate_cost(config.models.tiers[Tier.ULTRA], messages, None, 100)
    # 700 chars / 3.5 = 200 input tokens; output = max_tokens = 100
    assert (estimate.input_tokens, estimate.output_tokens) == (200, 100)
    assert estimate.cost_usd == pytest.approx(200 * 1.00 / 1e6 + 100 * 3.00 / 1e6)


def test_estimate_counts_tool_schemas(config: Config) -> None:
    tool = {"type": "function", "function": {"name": "lookup_unit", "parameters": {}}}
    chars = 10 + len(json.dumps(tool, separators=(",", ":")))
    estimate = live_call.estimate_cost(
        config.models.tiers[Tier.LIGHTNING], [{"role": "user", "content": "y" * 10}], [tool], 32
    )
    assert estimate.input_tokens == math.ceil(chars / 3.5)


# --- refusals before sending ------------------------------------------------------------------


def test_call_over_phase_cap_is_refused(
    caller: live_call.LiveCaller, fake: FakeOpenAI, ledger_path: Path
) -> None:
    with pytest.raises(live_call.Refused, match="phase 0"):
        _chat(caller, max_tokens=300_000)  # 300k output tokens on ultra = $0.90 > $0.65
    assert fake.completions.calls == []
    assert _lines(ledger_path) == []


def test_call_over_use_allowance_is_refused(caller: live_call.LiveCaller, fake: FakeOpenAI) -> None:
    caller.record_opening_balance(4.99, use="development")
    with pytest.raises(live_call.Refused, match="development"):
        _chat(caller, max_tokens=10_000)  # $0.03 > $0.01 left of development's $5
    assert fake.completions.calls == []


def test_call_over_laptop_allowance_is_refused(
    caller: live_call.LiveCaller, fake: FakeOpenAI
) -> None:
    # past spend leaves $0.40 on the laptop while development still has $1.00
    caller.record_opening_balance(4.0, use="development")
    caller.record_opening_balance(4.6, use="test_5")
    caller.record_opening_balance(8.0, use="benchmark")
    caller.record_opening_balance(2.0, use="video")
    with pytest.raises(live_call.Refused, match="laptop"):
        _chat(caller, max_tokens=150_000)  # $0.45: under the phase cap and development's $1.00
    assert fake.completions.calls == []


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"use": None}, "use"),
        ({"use": "holiday"}, "use"),
        ({"use": "judging"}, "hosted"),
        ({"phase": "1"}, "phase 1"),
    ],
)
def test_call_without_a_valid_use_or_phase_cap_is_refused(
    caller: live_call.LiveCaller, fake: FakeOpenAI, overrides: dict[str, Any], match: str
) -> None:
    with pytest.raises(live_call.Refused, match=match):
        _chat(caller, **overrides)
    assert fake.completions.calls == []


def test_missing_key_is_refused_without_naming_a_value(config: Config, ledger_path: Path) -> None:
    fake = FakeOpenAI()
    caller = live_call.LiveCaller(
        settings=_settings(nebius=""),
        config=config,
        ledger=live_call.Ledger(ledger_path),
        clock=lambda: NOW,
        openai_client=fake,
    )
    with pytest.raises(live_call.MissingKey, match="NEBIUS_API_KEY"):
        _chat(caller)
    assert fake.completions.calls == []


def test_parallel_calls_cannot_overshoot_the_cap_together(
    caller: live_call.LiveCaller, fake: FakeOpenAI
) -> None:
    """Each in-flight call holds its estimate, so concurrent calls see each other."""
    release = threading.Event()
    refused = threading.Event()
    original = fake.completions.create

    def held_create(**kwargs: Any) -> Any:
        release.wait(timeout=5)  # keep the call in flight until the third one has been refused
        return original(**kwargs)

    fake.completions.create = held_create  # type: ignore[method-assign]
    results: list[str] = []
    lock = threading.Lock()

    def one_call() -> None:
        try:
            _chat(caller, max_tokens=80_000)  # $0.24 each; three would be $0.72 > $0.65
            outcome = "sent"
        except live_call.Refused:
            outcome = "refused"
            refused.set()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=one_call) for _ in range(3)]
    for t in threads:
        t.start()
    assert refused.wait(timeout=5), "no call was refused while two were in flight"
    release.set()
    for t in threads:
        t.join(timeout=5)
    assert sorted(results) == ["refused", "sent", "sent"]


# --- after sending ------------------------------------------------------------------------------


def test_success_appends_real_cost(
    caller: live_call.LiveCaller, fake: FakeOpenAI, ledger_path: Path
) -> None:
    _chat(caller)
    assert len(fake.completions.calls) == 1
    assert fake.completions.calls[0]["model"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
    [line] = _lines(ledger_path)
    assert line["kind"] == "model"
    assert line["environment"] == "laptop"
    assert line["phase"] == "0"
    assert line["use"] == "development"
    assert (line["input_tokens"], line["output_tokens"]) == (100, 20)
    assert line["cost_usd"] == pytest.approx(100 * 1.00 / 1e6 + 20 * 3.00 / 1e6)
    assert line["ts"].startswith("2026-10-13T18:00:00")


def test_failure_appends_nothing_and_is_not_retried(
    caller: live_call.LiveCaller, fake: FakeOpenAI, ledger_path: Path
) -> None:
    fake.completions.fail_with = RuntimeError("server error")
    with pytest.raises(RuntimeError, match="server error"):
        _chat(caller)
    assert len(fake.completions.calls) == 1
    assert _lines(ledger_path) == []


def test_failed_call_releases_its_hold(caller: live_call.LiveCaller, fake: FakeOpenAI) -> None:
    fake.completions.fail_with = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _chat(caller, max_tokens=150_000)  # $0.45 held, then released
    fake.completions.fail_with = None
    _chat(caller, max_tokens=150_000)  # would be refused if the first hold had leaked


def test_ledger_never_holds_prompt_text_or_key(
    caller: live_call.LiveCaller, ledger_path: Path
) -> None:
    _chat(caller)
    caller.tavily_search(
        "how does water react with sodium metal",
        phase="0",
        use="development",
        purpose="unit test",
        max_results=3,
    )
    text = ledger_path.read_text(encoding="utf-8")
    assert "SECRET-PROMPT-TEXT" not in text
    assert "sodium" not in text
    assert KEY not in text
    assert TAVILY_KEY not in text


def test_tavily_call_records_searches_at_zero_cost(
    caller: live_call.LiveCaller, ledger_path: Path
) -> None:
    caller.tavily_search(
        "water and sodium", phase="0", use="development", purpose="T10", max_results=3
    )
    [line] = _lines(ledger_path)
    assert (line["kind"], line["searches"], line["cost_usd"], line["model"]) == (
        "tavily",
        1,
        0.0,
        None,
    )


def test_opening_balance_counts_toward_laptop_and_use(
    caller: live_call.LiveCaller, ledger_path: Path
) -> None:
    caller.record_opening_balance(1.25, use="development")
    [line] = _lines(ledger_path)
    assert (line["kind"], line["use"], line["cost_usd"]) == ("opening_balance", "development", 1.25)
    assert caller.ledger.spent(use="development") == pytest.approx(1.25)
    assert caller.ledger.spent() == pytest.approx(1.25)


def test_opening_balance_is_not_phase_spend(caller: live_call.LiveCaller) -> None:
    caller.record_opening_balance(3.00, use="development")
    _chat(caller)  # $3 of earlier spend must not use up phase 0's $0.65


def test_list_models_is_free(caller: live_call.LiveCaller, ledger_path: Path) -> None:
    assert caller.list_models() == ["nvidia/model-a"]
    assert _lines(ledger_path) == []


def test_default_openai_client_never_retries() -> None:
    client = live_call.openai_client(_settings())
    assert client.max_retries == 0
