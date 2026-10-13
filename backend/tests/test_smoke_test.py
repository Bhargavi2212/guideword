"""scripts/smoke_test.py (spec 0.4), against a scripted fake client: no paid calls."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import live_call
import pytest
import smoke_test
from pydantic import SecretStr

from guideword.config import Config, load_config
from guideword.schema.enums import Tier
from guideword.settings import Settings

KEY = "nb-smoke-test-key-1234567890"
TAVILY_KEY = "tv-smoke-test-key-0987654321"
NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
EXPECTED = {
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "lightning": "nvidia/Nemotron-3_5-Lightning",
    "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
}
# Paid model calls in one full run: T2 4, T3 4, T4 4, T5 4, T6 2, T7 4x2, T8 1, T9 5,
# T11 2, T12 2, T13 3, T14 1.
FULL_RUN_MODEL_CALLS = 40
BANNED_WORDS = ("accident", "explosion", "csb", "hazop", "plant", "reactor", "incident")


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _dumpable(**fields: Any) -> SimpleNamespace:
    """A stand-in for an OpenAI response object: attributes plus model_dump()."""
    return SimpleNamespace(**fields, model_dump=lambda: {k: _plain(v) for k, v in fields.items()})


def _tool_call(name: str, arguments: str) -> SimpleNamespace:
    function = _dumpable(name=name, arguments=arguments)
    return _dumpable(id=f"call_{name}", type="function", function=function)


def _response(
    content: str | None,
    *,
    finish: str = "stop",
    reasoning: str | None = None,
    tool_calls: list[SimpleNamespace] | None = None,
    prompt_tokens: int = 50,
    completion_tokens: int = 10,
) -> SimpleNamespace:
    message = _dumpable(content=content, reasoning_content=reasoning, tool_calls=tool_calls)
    choice = _dumpable(message=message, finish_reason=finish, index=0)
    usage = _dumpable(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return _dumpable(id="resp", choices=[choice], usage=usage)


class ScriptedCompletions:
    """Answers each request the way a working model would."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.override: Any = None

    def create(self, **kwargs: Any) -> Any:
        with self.lock:
            self.calls.append(kwargs)
        if self.override is not None:
            result = self.override(kwargs)
            if result is not None:
                if isinstance(result, Exception):
                    raise result
                return result
        messages = kwargs["messages"]
        if any(m.get("role") == "tool" for m in messages):
            return _response("The unit is kPa.")
        if kwargs.get("tools"):
            name = "count_items" if kwargs.get("tool_choice") == "required" else "lookup_unit"
            return _response(
                None, finish="tool_calls", tool_calls=[_tool_call(name, '{"name": "pressure"}')]
            )
        if kwargs["max_tokens"] == 32:
            return _response('{"verdict": "y', finish="length", reasoning="thinking...")
        if kwargs.get("response_format"):
            return _response('{"verdict": "yes", "reason": "Water wets most surfaces."}')
        return _response("OK", reasoning="The user wants OK.")


class FakeOpenAI:
    def __init__(self, model_ids: list[str] | None = None) -> None:
        self.completions = ScriptedCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        ids = list(EXPECTED.values()) if model_ids is None else model_ids
        entries = [_dumpable(id=i, object="model", owned_by="nvidia") for i in ids]
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=entries))


class FakeTavily:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "query": kwargs["query"],
            "results": [{"url": "https://example.org", "content": "x"}],
        }


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _caller(config: Config, tmp_path: Path, fake: FakeOpenAI) -> live_call.LiveCaller:
    settings = Settings(
        _env_file=None,
        nebius_api_key=SecretStr(KEY),
        tavily_api_key=SecretStr(TAVILY_KEY),
        global_budget_usd=25.0,
    )
    return live_call.LiveCaller(
        settings=settings,
        config=config,
        ledger=live_call.Ledger(tmp_path / "ledger.jsonl"),
        clock=lambda: NOW,
        openai_client=fake,
        tavily_client=FakeTavily(),
        script="smoke_test.py",
    )


def _runner(caller: live_call.LiveCaller, out: Path) -> smoke_test.SmokeRunner:
    ticks = iter(range(1, 1_000_000))
    lock = threading.Lock()

    def timer() -> float:
        with lock:
            return next(ticks) * 0.1

    return smoke_test.SmokeRunner(
        caller, out_dir=out, phase="0", use="development", timer=timer, filler_chars=3_500
    )


def _ledger(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "ledger.jsonl"
    return (
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )


def _by(results: list[smoke_test.Result], test: str, tier: str) -> smoke_test.Result:
    [match] = [r for r in results if r.test == test and r.tier == tier]
    return match


# --- a full run -------------------------------------------------------------------------------


def test_full_run_goes_through_live_call(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    caller = _caller(config, tmp_path, fake)
    out = tmp_path / "smoke"
    runner = _runner(caller, out)
    results = runner.run()
    assert runner.status == "complete"
    assert len(fake.completions.calls) == FULL_RUN_MODEL_CALLS
    lines = _ledger(tmp_path)
    assert sum(1 for x in lines if x["kind"] == "model") == FULL_RUN_MODEL_CALLS
    assert sum(1 for x in lines if x["kind"] == "tavily") == 1
    assert all(x["phase"] == "0" and x["use"] == "development" for x in lines)
    assert all(x["script"] == "smoke_test.py" for x in lines)
    tests = {r.test for r in results}
    assert {f"T{n}" for n in range(1, 15)} <= {t.split("-")[0] for t in tests}
    assert all(r.status == "pass" for r in results), [r for r in results if r.status != "pass"]
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "complete"
    assert summary["model_ids"] == EXPECTED
    assert summary["spent_usd"] > 0


def test_each_test_uses_its_spec_settings(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    _runner(_caller(config, tmp_path, fake), tmp_path / "smoke").run()
    calls = fake.completions.calls
    reasoning_off = [c for c in calls if c.get("extra_body", {}).get("chat_template_kwargs")]
    assert {c["model"] for c in reasoning_off} >= set(EXPECTED.values())  # T5 on all four
    budgets = [c for c in calls if "reasoning_budget" in c.get("extra_body", {})]
    assert {c["model"] for c in budgets} == {EXPECTED["ultra"], EXPECTED["super"]}  # T6
    strict = [c for c in calls if c.get("response_format", {}).get("type") == "json_schema"]
    assert all(c["response_format"]["json_schema"]["strict"] is True for c in strict)
    required = [c for c in calls if c.get("tool_choice") == "required"]
    assert [c["model"] for c in required] == [EXPECTED["ultra"]]  # T12
    assert any(c["max_tokens"] == 32 and c["model"] == EXPECTED["lightning"] for c in calls)  # T8


def test_prompts_are_harmless(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    tavily = FakeTavily()
    caller = _caller(config, tmp_path, fake)
    caller._tavily = tavily  # noqa: SLF001 - check the one search query too
    _runner(caller, tmp_path / "smoke").run()
    texts = [str(m.get("content") or "") for c in fake.completions.calls for m in c["messages"]]
    texts += [c["query"] for c in tavily.calls]
    for text in texts:
        assert not any(word in text.lower() for word in BANNED_WORDS), text[:80]


def test_t14_filler_is_about_100k_tokens(config: Config) -> None:
    messages = smoke_test.filler_messages(smoke_test.DEFAULT_FILLER_CHARS)
    estimate = live_call.estimate_cost(config.models.tiers[Tier.ULTRA], messages, None, 50)
    assert 95_000 <= estimate.input_tokens <= 105_000
    assert estimate.cost_usd == pytest.approx(0.10, abs=0.01)


# --- spec acceptance ------------------------------------------------------------------------------


def test_saved_responses_have_no_keys(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    fake.completions.override = lambda kw: _response(f"leaked {KEY}")
    out = tmp_path / "smoke"
    runner = _runner(_caller(config, tmp_path, fake), out)
    runner.run()
    assert runner.status == "stopped"
    assert "key" in runner.results[-1].notes.lower()
    for path in out.rglob("*.json"):
        assert KEY not in path.read_text(encoding="utf-8")


def test_every_raw_response_is_kept(config: Config, tmp_path: Path) -> None:
    out = tmp_path / "smoke"
    _runner(_caller(config, tmp_path, FakeOpenAI()), out).run()
    raw = {p.name for p in out.glob("T*.json")} - {"T1-models.json", "T10-tavily.json"}
    assert len(raw) == FULL_RUN_MODEL_CALLS  # one file per paid call, none overwritten
    assert {"T2-ultra.json", "T2-nano.json", "T7-call-super.json", "T9-5-lightning.json"} <= raw


def test_saved_responses_hold_no_headers(config: Config, tmp_path: Path) -> None:
    out = tmp_path / "smoke"
    _runner(_caller(config, tmp_path, FakeOpenAI()), out).run()
    for path in out.glob("T*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert "authorization" not in text and "bearer" not in text


def test_t8_length_is_detected_and_never_parsed(config: Config, tmp_path: Path) -> None:
    results = _runner(_caller(config, tmp_path, FakeOpenAI()), tmp_path / "smoke").run()
    t8 = _by(results, "T8", "lightning")
    assert t8.status == "pass"
    assert t8.finish_reason == "length"
    assert "not parsed" in t8.notes


def test_truncated_json_answer_is_a_failure_not_a_parse(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()

    def truncate_t3(kw: dict[str, Any]) -> Any:
        fmt = kw.get("response_format", {})
        if fmt.get("type") == "json_schema" and kw["model"] == EXPECTED["super"]:
            return _response('{"verdict": "ye', finish="length")
        return None

    fake.completions.override = truncate_t3
    results = _runner(_caller(config, tmp_path, fake), tmp_path / "smoke").run()
    t3 = _by(results, "T3", "super")
    assert t3.status == "fail"
    assert "truncated" in t3.notes


def test_stops_on_refusal(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    caller = _caller(config, tmp_path, fake)
    caller.ledger.append(
        live_call.SpendEntry(
            ts=NOW,
            kind="model",
            environment="laptop",
            phase="0",
            use="development",
            cost_usd=0.649,
            script="smoke_test.py",
            purpose="earlier run",
        )
    )
    runner = _runner(caller, tmp_path / "smoke")
    results = runner.run()
    assert runner.status == "stopped"
    assert results[-1].status == "refused"
    assert fake.completions.calls == []


def test_rejected_feature_is_recorded_and_the_run_continues(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI()
    request = httpx.Request("POST", "https://api.tokenfactory.nebius.com/v1/chat/completions")

    def reject_json_schema(kw: dict[str, Any]) -> Any:
        if (
            kw.get("response_format", {}).get("type") == "json_schema"
            and kw["model"] == EXPECTED["nano"]
        ):
            return live_call.openai.BadRequestError(
                "json_schema not supported",
                response=httpx.Response(400, request=request),
                body=None,
            )
        return None

    fake.completions.override = reject_json_schema
    runner = _runner(_caller(config, tmp_path, fake), tmp_path / "smoke")
    results = runner.run()
    assert runner.status == "complete"
    rejected = _by(results, "T3", "nano")
    assert rejected.status == "rejected"
    assert "400" in rejected.notes
    assert _by(results, "T4", "nano").status == "pass"


def test_tier_missing_from_catalog_is_skipped(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI(model_ids=[EXPECTED["ultra"], EXPECTED["super"], EXPECTED["lightning"]])
    results = _runner(_caller(config, tmp_path, fake), tmp_path / "smoke").run()
    assert _by(results, "T1", "nano").status == "fail"
    assert _by(results, "T2", "nano").status == "skipped"
    assert all(c["model"] != EXPECTED["nano"] for c in fake.completions.calls)


def test_case_insensitive_catalog_match_is_used(config: Config, tmp_path: Path) -> None:
    fake = FakeOpenAI(
        model_ids=[
            EXPECTED["ultra"],
            EXPECTED["super"].upper(),
            EXPECTED["lightning"],
            EXPECTED["nano"],
        ]
    )
    out = tmp_path / "smoke"
    _runner(_caller(config, tmp_path, fake), out).run()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model_ids"]["super"] == EXPECTED["super"].upper()
    assert "case" in _by([smoke_test.Result(**r) for r in summary["results"]], "T1", "super").notes


def test_parallel_tests_record_every_call(config: Config, tmp_path: Path) -> None:
    results = _runner(_caller(config, tmp_path, FakeOpenAI()), tmp_path / "smoke").run()
    assert len([r for r in results if r.test.startswith("T9")]) == 5
    assert len([r for r in results if r.test.startswith("T13")]) == 3
