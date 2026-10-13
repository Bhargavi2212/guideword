"""Phase 0 smoke test (spec 0.4): what each Nemotron tier on Token Factory actually supports.

Written by Claude Code, run by Bhargavi. Every paid call goes through live_call.LiveCaller,
so the phase cap, the use allowance, the ledger and the no-retry rule all apply. Prompts are
short, fixed and harmless: no plant or accident content. The run stops at the first refusal.
Raw responses go to docs/smoke/ (checked for keys first); a summary goes to
docs/smoke/summary.json for docs/smoke-test-results.md.

Run from the repo root, venv active, keys in .env:
  python scripts/smoke_test.py --phase 0 --use development
"""

import argparse
import json
import re
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from guideword.logs import configure
from guideword.schema.enums import Tier
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from live_call import CallFailed, LiveCaller, MissingKey, Refused, cost_usd, default_caller

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "smoke"
TIERS = (Tier.ULTRA, Tier.SUPER, Tier.LIGHTNING, Tier.NANO)
# T14: about 100k input tokens at the 3.5 characters-per-token estimate.
DEFAULT_FILLER_CHARS = 350_000
LIST_FIELDS_SEEN_ALWAYS = {"id", "object", "created", "owned_by"}

OK_PROMPT = [{"role": "user", "content": "Reply with the word OK."}]
VERDICT_QUESTION = "Is water wet? Answer yes or no, with a short reason."
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["yes", "no"]},
        "reason": {"type": "string", "maxLength": 200},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}
JSON_SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "verdict", "strict": True, "schema": VERDICT_SCHEMA},
}
JSON_OBJECT_PROMPT = (
    f"{VERDICT_QUESTION} Reply with only a JSON object with two keys: "
    '"verdict" ("yes" or "no") and "reason" (a string of at most 200 characters).'
)
REASONING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
REASONING_BUDGET = {"reasoning_budget": 512}
LOOKUP_UNIT = {
    "type": "function",
    "function": {
        "name": "lookup_unit",
        "description": "Return the measurement unit for a quantity name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
}
COUNT_ITEMS = {
    "type": "function",
    "function": {
        "name": "count_items",
        "description": "Count the items in a comma-separated list.",
        "parameters": {
            "type": "object",
            "properties": {"items": {"type": "string"}},
            "required": ["items"],
        },
    },
}
TOOL_PROMPT = "What unit is pressure measured in? Use the lookup_unit tool, then answer."
TOOL_RESULT = "kPa"
TAVILY_QUERY = "how does water react with sodium metal"
THINK_BLOCK = re.compile(r"^\s*<think>.*?</think>\s*", re.S)

Status = Literal["pass", "fail", "rejected", "skipped", "refused"]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["yes", "no"]
    reason: str = Field(max_length=200)


class KeyLeak(RuntimeError):
    """A response contained a key; it is not saved and the run stops."""


@dataclass
class Result:
    test: str
    tier: str
    model: str
    status: Status
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    finish_reason: str | None = None
    reasoning: str | None = None
    notes: str = ""


@dataclass
class Reply:
    """What one call returned, reduced to what the tests check."""

    content: str
    finish_reason: str | None
    reasoning: str
    tool_calls: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


def filler_messages(chars: int) -> list[dict[str, Any]]:
    line = "Filler line {:06d}: the cat sat on the mat and looked at the sky.\n"
    text = "".join(line.format(i) for i in range(chars // len(line.format(0)) + 1))[:chars]
    return [
        {
            "role": "user",
            "content": "Below is filler text with no task in it. Reply with the word OK.\n\n"
            + text,
        }
    ]


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _reasoning_location(message: Any, content: str) -> str:
    if getattr(message, "reasoning_content", None):
        return "reasoning_content"
    if "<think>" in content:
        return "think_tags"
    return "none"


class SmokeRunner:
    def __init__(
        self,
        caller: LiveCaller,
        *,
        out_dir: Path = DEFAULT_OUT,
        phase: str,
        use: str,
        timer: Callable[[], float] = time.perf_counter,
        filler_chars: int = DEFAULT_FILLER_CHARS,
    ) -> None:
        self.caller = caller
        self.out_dir = out_dir
        self.phase = phase
        self.use = use
        self.timer = timer
        self.filler_chars = filler_chars
        self.results: list[Result] = []
        self.model_ids: dict[Tier, str] = {}
        self.status = "not started"
        self._lock = threading.Lock()
        self._secrets = [
            s
            for s in (
                caller.settings.nebius_api_key.get_secret_value(),
                caller.settings.tavily_api_key.get_secret_value(),
            )
            if s
        ]

    # --- plumbing ---------------------------------------------------------------------------

    def _add(self, result: Result) -> Result:
        with self._lock:
            self.results.append(result)
        return result

    def _save(self, name: str, payload: Any) -> None:
        text = json.dumps(
            _plain(payload), indent=2, sort_keys=True, ensure_ascii=False, default=str
        )
        if any(secret in text for secret in self._secrets):
            raise KeyLeak(f"{name}: response contains a key; not saved, run stopped")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{name}.json").write_bytes((text + "\n").encode("utf-8"))

    def _send(
        self,
        name: str,
        tier: Tier,
        messages: Sequence[dict[str, Any]],
        max_tokens: int,
        **request: Any,
    ) -> Reply:
        """One paid call through LiveCaller. Refused, MissingKey and KeyLeak propagate."""
        prices = self.caller.config.models.tiers[tier]
        start = self.timer()
        response = self.caller.chat(
            tier=tier,
            model_id=self.model_ids[tier],
            messages=messages,
            phase=self.phase,
            use=self.use,
            purpose=f"smoke {name}",
            max_tokens=max_tokens,
            **request,
        )
        latency_ms = (self.timer() - start) * 1000
        self._save(f"{name}-{tier.value}", response)
        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return Reply(
            content=content,
            finish_reason=choice.finish_reason,
            reasoning=_reasoning_location(message, content),
            tool_calls=[_plain(c) for c in (message.tool_calls or [])],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(prices, input_tokens, output_tokens),
            latency_ms=latency_ms,
        )

    def _result(self, name: str, tier: Tier, reply: Reply, status: Status, notes: str) -> Result:
        return self._add(
            Result(
                test=name,
                tier=tier.value,
                model=self.model_ids[tier],
                status=status,
                latency_ms=round(reply.latency_ms, 1),
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                cost_usd=reply.cost_usd,
                finish_reason=reply.finish_reason,
                reasoning=reply.reasoning,
                notes=notes,
            )
        )

    def _attempt(
        self,
        name: str,
        tier: Tier,
        judge: Callable[[Reply], tuple[Status, str]],
        messages: Sequence[dict[str, Any]],
        max_tokens: int,
        **request: Any,
    ) -> Reply | None:
        """Send one call and record it; a rejected or missing model is recorded, not raised."""
        if tier not in self.model_ids:
            self._add(
                Result(name, tier.value, "", "skipped", notes="model not in the catalog (T1)")
            )
            return None
        try:
            reply = self._send(name, tier, messages, max_tokens, **request)
        except CallFailed as error:
            self._add(Result(name, tier.value, self.model_ids[tier], "rejected", notes=str(error)))
            return None
        status, notes = judge(reply)
        self._result(name, tier, reply, status, notes)
        return reply

    # --- judges ---------------------------------------------------------------------------

    @staticmethod
    def _ok(reply: Reply) -> tuple[Status, str]:
        if reply.finish_reason == "length":
            return "fail", "truncated at max_tokens"
        if "ok" in THINK_BLOCK.sub("", reply.content).lower():
            return "pass", ""
        return "fail", "did not reply OK"

    @staticmethod
    def _verdict(reply: Reply) -> tuple[Status, str]:
        if reply.finish_reason == "length":
            return "fail", "truncated at max_tokens; not parsed"
        try:
            Verdict.model_validate_json(THINK_BLOCK.sub("", reply.content).strip())
        except ValidationError as error:
            return "fail", f"invalid JSON for the schema: {error.error_count()} error(s)"
        return "pass", "valid JSON for the schema"

    # --- the tests ------------------------------------------------------------------------

    def t1_models(self) -> None:
        entries = self.caller.model_list()
        self._save("T1-models", entries)
        ids = [str(e.get("id")) for e in entries]
        extra = sorted({k for e in entries for k in e} - LIST_FIELDS_SEEN_ALWAYS)
        for tier in TIERS:
            expected = self.caller.config.models.tiers[tier].expected_id
            found = next((i for i in ids if i == expected), None)
            note = "exact ID"
            if found is None:
                found = next((i for i in ids if i.lower() == expected.lower()), None)
                note = "matched ignoring case"
            if found is None:
                self._add(
                    Result("T1", tier.value, expected, "fail", notes="expected ID not listed")
                )
                continue
            self.model_ids[tier] = found
            fields = f"; extra fields: {', '.join(extra)}" if extra else "; no prices or limits"
            self._add(Result("T1", tier.value, found, "pass", notes=note + fields))

    def t2_plain(self) -> dict[Tier, int]:
        tokens: dict[Tier, int] = {}
        for tier in TIERS:
            reply = self._attempt("T2", tier, self._ok, OK_PROMPT, 400)
            if reply is not None:
                tokens[tier] = reply.output_tokens
        return tokens

    def t3_json_schema(self) -> None:
        messages = [{"role": "user", "content": VERDICT_QUESTION}]
        for tier in TIERS:
            self._attempt(
                "T3", tier, self._verdict, messages, 400, response_format=JSON_SCHEMA_FORMAT
            )

    def t4_json_object(self) -> None:
        messages = [{"role": "user", "content": JSON_OBJECT_PROMPT}]
        for tier in TIERS:
            self._attempt(
                "T4", tier, self._verdict, messages, 400, response_format={"type": "json_object"}
            )

    def _versus_t2(self, t2: dict[Tier, int], tier: Tier) -> Callable[[Reply], tuple[Status, str]]:
        def judge(reply: Reply) -> tuple[Status, str]:
            status, notes = self._ok(reply)
            base = t2.get(tier)
            comparison = f"output tokens {reply.output_tokens} vs T2 {base}"
            return status, f"{notes}; {comparison}".lstrip("; ")

        return judge

    def t5_reasoning_off(self, t2: dict[Tier, int]) -> None:
        for tier in TIERS:
            self._attempt(
                "T5", tier, self._versus_t2(t2, tier), OK_PROMPT, 400, extra_body=REASONING_OFF
            )

    def t6_reasoning_budget(self, t2: dict[Tier, int]) -> None:
        for tier in (Tier.ULTRA, Tier.SUPER):
            self._attempt(
                "T6", tier, self._versus_t2(t2, tier), OK_PROMPT, 400, extra_body=REASONING_BUDGET
            )

    def t7_tool_calling(self) -> None:
        messages: list[dict[str, Any]] = [{"role": "user", "content": TOOL_PROMPT}]
        for tier in TIERS:
            if tier not in self.model_ids:
                self._add(
                    Result("T7", tier.value, "", "skipped", notes="model not in the catalog (T1)")
                )
                continue
            try:
                first = self._send("T7-call", tier, messages, 400, tools=[LOOKUP_UNIT])
                if not first.tool_calls:
                    self._result("T7", tier, first, "fail", "no tool_calls returned")
                    continue
                call = first.tool_calls[0]
                try:
                    json.loads(call["function"]["arguments"])
                    args_ok = "arguments valid JSON"
                except (KeyError, TypeError, ValueError):
                    args_ok = "arguments NOT valid JSON"
                follow_up = [
                    *messages,
                    {"role": "assistant", "content": first.content or None, "tool_calls": [call]},
                    {"role": "tool", "tool_call_id": call.get("id"), "content": TOOL_RESULT},
                ]
                second = self._send("T7-result", tier, follow_up, 400, tools=[LOOKUP_UNIT])
            except CallFailed as error:
                self._add(
                    Result("T7", tier.value, self.model_ids[tier], "rejected", notes=str(error))
                )
                continue
            used = TOOL_RESULT.lower() in THINK_BLOCK.sub("", second.content).lower()
            combined = Reply(
                content=second.content,
                finish_reason=second.finish_reason,
                reasoning=first.reasoning,
                tool_calls=first.tool_calls,
                input_tokens=first.input_tokens + second.input_tokens,
                output_tokens=first.output_tokens + second.output_tokens,
                cost_usd=first.cost_usd + second.cost_usd,
                latency_ms=first.latency_ms + second.latency_ms,
            )
            status: Status = "pass" if used and args_ok.endswith("valid JSON") else "fail"
            note = f"tool {call['function'].get('name')}; {args_ok}; follow-up used result: {used}"
            self._result("T7", tier, combined, status, note)

    def t8_truncation(self) -> None:
        def judge(reply: Reply) -> tuple[Status, str]:
            if reply.finish_reason == "length":
                return "pass", "finish_reason=length detected; not parsed"
            return "fail", f"expected length, got {reply.finish_reason}"

        self._attempt("T8", Tier.LIGHTNING, judge, OK_PROMPT, 32)

    def _parallel(self, prefix: str, tier: Tier, count: int) -> None:
        errors: list[BaseException] = []

        def one(index: int) -> None:
            try:
                self._attempt(f"{prefix}-{index}", tier, self._ok, OK_PROMPT, 400)
            except (Refused, MissingKey, KeyLeak) as error:
                errors.append(error)

        threads = [threading.Thread(target=one, args=(i,)) for i in range(1, count + 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if errors:
            raise errors[0]

    def t9_concurrency_lightning(self) -> None:
        self._parallel("T9", Tier.LIGHTNING, 5)

    def t10_tavily(self) -> None:
        start = self.timer()
        try:
            result = self.caller.tavily_search(
                TAVILY_QUERY, phase=self.phase, use=self.use, purpose="smoke T10", max_results=3
            )
        except CallFailed as error:
            self._add(Result("T10", "tavily", "tavily", "rejected", notes=str(error)))
            return
        latency_ms = (self.timer() - start) * 1000
        self._save("T10-tavily", result)
        results = result.get("results", []) if isinstance(result, dict) else []
        keys = sorted(result) if isinstance(result, dict) else []
        status: Status = "pass" if results else "fail"
        note = f"{len(results)} results; top-level keys: {', '.join(keys)}"
        self._add(
            Result("T10", "tavily", "tavily", status, latency_ms=round(latency_ms, 1), notes=note)
        )

    def t11_bulk_path(self) -> None:
        messages = [{"role": "user", "content": VERDICT_QUESTION}]
        for tier in (Tier.LIGHTNING, Tier.NANO):
            self._attempt(
                "T11",
                tier,
                self._verdict,
                messages,
                400,
                response_format=JSON_SCHEMA_FORMAT,
                extra_body=REASONING_OFF,
            )

    def t12_orchestrator_path(self) -> None:
        messages = [{"role": "user", "content": TOOL_PROMPT}]

        def judge(reply: Reply) -> tuple[Status, str]:
            if not reply.tool_calls:
                return "fail", "no tool_calls returned"
            call = reply.tool_calls[0]["function"]
            try:
                json.loads(call["arguments"])
            except (KeyError, TypeError, ValueError):
                return "fail", f"chose {call.get('name')}; arguments NOT valid JSON"
            return "pass", f"chose {call.get('name')}; arguments valid JSON"

        for choice in ("auto", "required"):
            self._attempt(
                f"T12-{choice}",
                Tier.ULTRA,
                judge,
                messages,
                1000,
                tools=[LOOKUP_UNIT, COUNT_ITEMS],
                tool_choice=choice,
            )

    def t13_concurrency_ultra(self) -> None:
        self._parallel("T13", Tier.ULTRA, 3)

    def t14_long_input(self) -> None:
        def judge(reply: Reply) -> tuple[Status, str]:
            note = f"accepted; real input tokens {reply.input_tokens}; cost ${reply.cost_usd:.4f}"
            return "pass", note

        self._attempt("T14", Tier.ULTRA, judge, filler_messages(self.filler_chars), 50)

    # --- the run ----------------------------------------------------------------------------

    def run(self) -> list[Result]:
        self.status = "running"
        try:
            self.t1_models()
            t2 = self.t2_plain()
            self.t3_json_schema()
            self.t4_json_object()
            self.t5_reasoning_off(t2)
            self.t6_reasoning_budget(t2)
            self.t7_tool_calling()
            self.t8_truncation()
            self.t9_concurrency_lightning()
            self.t10_tavily()
            self.t11_bulk_path()
            self.t12_orchestrator_path()
            self.t13_concurrency_ultra()
            self.t14_long_input()
            self.status = "complete"
        except (Refused, MissingKey) as error:
            self._add(Result("stop", "-", "-", "refused", notes=str(error)))
            self.status = "stopped"
        except KeyLeak as error:
            self._add(Result("stop", "-", "-", "refused", notes=str(error)))
            self.status = "stopped"
        except CallFailed as error:
            self._add(Result("stop", "-", "-", "rejected", notes=f"T1 model list failed: {error}"))
            self.status = "stopped"
        finally:
            self._write_summary()
        return self.results

    def _write_summary(self) -> None:
        summary = {
            "status": self.status,
            "run_at": self.caller.clock().isoformat(),
            "phase": self.phase,
            "use": self.use,
            "model_ids": {tier.value: model for tier, model in self.model_ids.items()},
            "spent_usd": sum(r.cost_usd or 0.0 for r in self.results),
            "results": [asdict(r) for r in self.results],
        }
        self._save("summary", summary)


def markdown_table(results: Sequence[Result]) -> str:
    lines = [
        "| Test | Tier | Status | Finish | Reasoning | Tokens in/out | Cost | Latency ms | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        tokens = f"{r.input_tokens}/{r.output_tokens}" if r.input_tokens is not None else ""
        cost = f"${r.cost_usd:.5f}" if r.cost_usd is not None else ""
        lines.append(
            f"| {r.test} | {r.tier} | {r.status} | {r.finish_reason or ''} | {r.reasoning or ''} "
            f"| {tokens} | {cost} | {r.latency_ms or ''} | {r.notes} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    configure()
    parser = argparse.ArgumentParser(description="Phase 0 smoke test (spec 0.4)")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--use", required=True)
    args = parser.parse_args(argv)
    runner = SmokeRunner(default_caller(script=Path(__file__).name), phase=args.phase, use=args.use)
    results = runner.run()
    print(markdown_table(results))
    print(
        f"\nstatus: {runner.status}; spent this run: ${sum(r.cost_usd or 0 for r in results):.4f}"
    )
    print(f"raw responses and summary.json in {runner.out_dir}")
    return 0 if runner.status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
