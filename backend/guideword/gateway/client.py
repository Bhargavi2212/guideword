"""The model gateway: every Token Factory call goes through `Gateway.call` (spec 2.2).

In order: route (job → tier → live model ID, with fallback), cache, budget guard, send (per
tier concurrency, bounded retries of 429 and 5xx), validate (JSON rules), log (a ModelCall
record when there is a run, and a ledger line for every call that was paid for).

Refusals raise `BudgetRefused` before anything is sent; its `status` says whether the run
stops at its cap (`stopped_cap`) or because an allowance is spent (`stopped_budget`).
"""

import json
import re
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from collections.abc import Set as AbstractSet
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from guideword.config import Config, TierModel
from guideword.gateway.cache import Cached, ResponseCache
from guideword.gateway.catalog import Catalog
from guideword.gateway.estimate import cost_usd, estimate_cost
from guideword.gateway.ledgers import Ledger
from guideword.gateway.transport import Reply, ToolCallRequest, Transport, TransportError
from guideword.logs import get_logger
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, RunStatus, Tier
from guideword.schema.records import ModelCall, SpendEntry

log = get_logger(__name__)

Outcome = Literal["ok", "invalid", "truncated", "error"]
Validator = Callable[[Any], None]
SCRIPT = "gateway"
_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.S)


class RepeatedRequest(RuntimeError):
    """This exact request was already made in this run: its answer is stored, and sending it
    again would only repeat that answer and overwrite its record. Found in the case D dev run."""


class TierMismatch(RuntimeError):
    """A call record's tier does not serve its model ID in models.yaml (contract v1.9)."""


class BudgetRefused(RuntimeError):
    """A request was refused before sending. `attempts` are the call's earlier attempts that
    were sent (or served from the cache) before it, with what they cost: a validation retry
    refused after a paid first attempt (bug fix, 2026-10-22). The caller records them, so the
    run's spend matches the ledger. Callers that pass a refusal on add their own earlier
    records to it the same way."""

    def __init__(self, message: str, status: RunStatus) -> None:
        super().__init__(message)
        self.status = status
        self.attempts: list[ModelCall] = []
        self.cost_usd = 0.0
        self.cap_cost_usd = 0.0

    def carry(self, calls: Sequence[ModelCall], cost_usd: float, cap_cost_usd: float) -> None:
        """Put records made before this refusal ahead of the ones it already carries."""
        self.attempts = [*calls, *self.attempts]
        self.cost_usd += cost_usd
        self.cap_cost_usd += cap_cost_usd


@dataclass(frozen=True)
class RunBudget:
    """The run a call belongs to: its ID, what it has counted against its cap (paid calls plus
    cache hits at their stored cost, R45), and the limit for this phase (the spend cap, or the
    cap minus the severity reserve during analysis, R38)."""

    run_id: str
    cap_spent_usd: float
    limit_usd: float
    # a batch's own budget (R13 as amended): calls are checked against this slice alone, never
    # against other batches in flight, so a refusal never depends on thread timing
    slice_id: str | None = None

    @property
    def hold_key(self) -> str:
        return self.run_id if self.slice_id is None else f"{self.run_id}#{self.slice_id}"


@dataclass
class GatewayResult:
    outcome: Outcome
    tier: Tier
    model_id: str
    # the parsed answer (a schema instance), when a schema was given and it validated
    value: Any = None
    content: str | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    error: str | None = None
    # money actually paid
    cost_usd: float = 0.0
    # counted against the run cap: paid cost plus cache hits at their stored cost (R45)
    cap_cost_usd: float = 0.0
    cache_hit: bool = False
    fell_back_from: tuple[Tier, ...] = ()
    # one record per request sent or served from cache (a validation retry is a second one)
    model_calls: list[ModelCall] = field(default_factory=list)


@dataclass(frozen=True)
class _Sent:
    reply: Reply | None
    cache_hit: bool
    attempts: int
    latency_ms: float
    cost_usd: float
    error: str | None
    cap_cost_usd: float = 0.0


class Gateway:
    def __init__(
        self,
        *,
        config: Config,
        transport: Transport,
        cache: ResponseCache,
        ledger: Ledger,
        use: BudgetUse,
        phase: str,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None] = time.sleep,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.config = config
        self.use = BudgetUse(use)
        self.phase = phase
        self._transport = transport
        self._cache = cache
        self._ledger = ledger
        self._clock = clock
        self._sleep = sleep
        self._timer = timer
        self.catalog = Catalog(transport, config, clock)
        self._semaphores = {
            tier: threading.BoundedSemaphore(n) for tier, n in config.caps.concurrency.items()
        }
        self._holds: dict[int, tuple[str | None, float]] = {}  # token -> (hold key, amount)
        self._hold_lock = threading.Lock()
        self._next_hold = 0

    # --- the call ---------------------------------------------------------------------------

    def call(
        self,
        *,
        job: str,
        prompt_version: str,
        messages: Sequence[dict[str, Any]],
        schema: type[BaseModel] | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        tier: Tier | None = None,
        run: RunBudget | None = None,
        validator: Validator | None = None,
        made: AbstractSet[str] = frozenset(),
    ) -> GatewayResult:
        """One logical call: a schema answer that fails validation is retried once with the
        error appended (a new request, so a new record), then marked invalid. A request whose
        model call ID is in `made` (this run's records) raises `RepeatedRequest` before the
        cache is read or anything is sent."""
        wanted = tier if tier is not None else self.config.routing.jobs[job]
        resolved = self.catalog.resolve(Tier(wanted))
        result = GatewayResult(
            outcome="error",
            tier=resolved.tier,
            model_id=resolved.model_id,
            fell_back_from=resolved.fell_back_from,
        )
        conversation = list(messages)
        spent_so_far = run.cap_spent_usd if run is not None else 0.0
        for attempt in (1, 2):
            budget = (
                RunBudget(run.run_id, spent_so_far, run.limit_usd, run.slice_id)
                if run is not None
                else None
            )
            request = self._request(
                job, resolved.tier, resolved.model_id, conversation, schema, tools, tool_choice
            )
            call_id = ids.model_call_id(resolved.model_id, prompt_version, _exact_input(request))
            if call_id in made:
                raise RepeatedRequest(f"{call_id} was already made in this run")
            try:
                sent = self._send_once(
                    job, prompt_version, resolved.tier, resolved.model_id, request, tools, budget
                )
            except BudgetRefused as refused:
                # the attempts already made were paid (or counted): they travel with it
                refused.carry(result.model_calls, result.cost_usd, result.cap_cost_usd)
                raise
            spent_so_far += sent.cap_cost_usd
            result.cost_usd += sent.cost_usd
            result.cap_cost_usd += sent.cap_cost_usd
            result.cache_hit = sent.cache_hit
            outcome, value, content, error = self._validate(sent, schema, tools, validator)
            if run is not None:
                result.model_calls.append(
                    self._record(
                        job,
                        prompt_version,
                        resolved.tier,
                        resolved.model_id,
                        request,
                        sent,
                        outcome,
                        run.run_id,
                    )
                )
            result.outcome, result.value, result.content, result.error = (
                outcome,
                value,
                content,
                error,
            )
            result.tool_calls = sent.reply.tool_calls if sent.reply is not None else ()
            if outcome != "invalid" or attempt == 2 or sent.reply is None:
                break
            conversation = [
                *conversation,
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": f"Your answer was not valid: {error}. "
                    "Answer again, only in the required JSON schema.",
                },
            ]
        return result

    # --- request ---------------------------------------------------------------------------

    def _request(
        self,
        job: str,
        tier: Tier,
        model_id: str,
        messages: Sequence[dict[str, Any]],
        schema: type[BaseModel] | None,
        tools: Sequence[dict[str, Any]] | None,
        tool_choice: str | None,
    ) -> dict[str, Any]:
        settings = self.config.models.tiers[tier].request
        max_tokens = self.config.caps.run.max_tokens.get(job)
        if max_tokens is None:
            raise KeyError(f"caps.yaml has no max_tokens for job {job}")
        request: dict[str, Any] = {
            "model": model_id,
            "messages": list(messages),
            "max_tokens": max_tokens,
        }
        if schema is not None:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        if tools:
            request["tools"] = list(tools)
            if tool_choice is not None:
                request["tool_choice"] = tool_choice
        if not settings.reasoning:
            request["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        return request

    # --- cache, guard, send ----------------------------------------------------------------

    def _send_once(
        self,
        job: str,
        prompt_version: str,
        tier: Tier,
        model_id: str,
        request: dict[str, Any],
        tools: Sequence[dict[str, Any]] | None,
        run: RunBudget | None,
    ) -> _Sent:
        key = ids.cache_key(model_id, prompt_version, _exact_input(request))
        prices = self.config.models.tiers[tier]
        cached = self._cache.get(key)
        if cached is not None:
            return _Sent(
                cached.reply, True, 1, 0.0, 0.0, None, self._stored_cost(key, cached, prices)
            )
        estimate = estimate_cost(prices, request["messages"], tools, request["max_tokens"])
        with self._hold(run, estimate.cost_usd):
            started = self._timer()
            reply, attempts, error = self._send_with_retries(job, tier, request)
            latency_ms = (self._timer() - started) * 1000
            if reply is None:
                return _Sent(None, False, attempts, latency_ms, 0.0, error)
            cost = cost_usd(prices, reply.input_tokens, reply.output_tokens)
            self._cache.put(key, model_id, prompt_version, reply, cost)
            self._ledger.append(
                SpendEntry(
                    ts=self._clock(),
                    kind="model",
                    environment=self._ledger.environment,
                    phase=self.phase,
                    use=self.use,
                    model=model_id,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                    cost_usd=cost,
                    script=SCRIPT,
                    purpose=job if run is None else f"{job} {run.run_id}",
                )
            )
            return _Sent(reply, False, attempts, latency_ms, cost, None, cost)

    def _stored_cost(self, key: str, cached: Cached, prices: TierModel) -> float:
        """What a cache hit counts against the run cap: the cost stored with the entry. An
        entry written before R45 has none: it is worked out once from the entry's tokens and
        stored, so every later hit reads the same figure."""
        if cached.cost_usd is not None:
            return cached.cost_usd
        if not cached.has_tokens:
            log.warning(
                "cached response has no stored cost and no token counts",
                extra={"context": {"cache_key": key}},
            )
            return 0.0
        cost = cost_usd(prices, cached.reply.input_tokens, cached.reply.output_tokens)
        self._cache.store_cost(key, cost)
        log.info("cache cost backfill", extra={"context": {"cache_key": key, "cost_usd": cost}})
        return cost

    def _send_with_retries(
        self, job: str, tier: Tier, request: dict[str, Any]
    ) -> tuple[Reply | None, int, str | None]:
        caps = self.config.caps.gateway
        last_error = "not sent"
        for attempt in range(1, caps.max_attempts + 1):
            try:
                with self._semaphores[tier]:
                    return self._transport.send(job, request), attempt, None
            except TransportError as error:
                last_error = f"{error} (status {error.status})"
                log.warning(
                    "model call failed",
                    extra={
                        "context": {
                            "job": job,
                            "tier": tier,
                            "attempt": attempt,
                            "status": error.status,
                        }
                    },
                )
                if not error.retriable or attempt == caps.max_attempts:
                    return None, attempt, last_error
                self._sleep(caps.backoff_seconds[attempt - 1])
        return None, caps.max_attempts, last_error

    @contextmanager
    def _hold(self, run: RunBudget | None, amount: float) -> Iterator[None]:
        """Check every limit with in-flight holds included, then hold `amount` until done."""
        caps = self.config.caps
        environment = self._ledger.environment
        with self._hold_lock:
            held_all = sum(a for _, a in self._holds.values())
            if run is not None:
                held_run = sum(a for key, a in self._holds.values() if key == run.hold_key)
                if run.cap_spent_usd + held_run + amount > run.limit_usd:
                    raise BudgetRefused(
                        f"run {run.run_id} limit ${run.limit_usd:.2f} would be exceeded",
                        RunStatus.STOPPED_CAP,
                    )
            if self.phase not in caps.phase_caps_usd:
                raise BudgetRefused(
                    f"phase {self.phase} has no live-call cap in caps.yaml",
                    RunStatus.STOPPED_BUDGET,
                )
            phase_cap = caps.phase_caps_usd[self.phase]
            if self._ledger.spent(phase=self.phase) + held_all + amount > phase_cap:
                raise BudgetRefused(
                    f"phase {self.phase} cap ${phase_cap:.2f} would be exceeded",
                    RunStatus.STOPPED_BUDGET,
                )
            if caps.environment_of(self.use) != environment:
                raise BudgetRefused(
                    f"use {self.use} belongs to the {caps.environment_of(self.use)} allowance, "
                    f"not {environment}",
                    RunStatus.STOPPED_BUDGET,
                )
            use_cap = caps.uses[self.use].allowance_usd
            if self._ledger.spent(use=self.use) + held_all + amount > use_cap:
                raise BudgetRefused(
                    f"use {self.use} allowance ${use_cap:.2f} would be exceeded",
                    RunStatus.STOPPED_BUDGET,
                )
            env_cap = caps.environment_allowance(environment)
            if self._ledger.spent() + held_all + amount > env_cap:
                raise BudgetRefused(
                    f"{environment} allowance ${env_cap:.2f} would be exceeded",
                    RunStatus.STOPPED_BUDGET,
                )
            token = self._next_hold
            self._next_hold += 1
            self._holds[token] = (run.hold_key if run is not None else None, amount)
        try:
            yield
        finally:
            with self._hold_lock:
                del self._holds[token]

    # --- validate and record ---------------------------------------------------------------

    def _validate(
        self,
        sent: _Sent,
        schema: type[BaseModel] | None,
        tools: Sequence[dict[str, Any]] | None,
        validator: Validator | None,
    ) -> tuple[Outcome, Any, str | None, str | None]:
        reply = sent.reply
        if reply is None:
            return "error", None, None, sent.error
        if reply.finish_reason == "length":
            return "truncated", None, reply.content, "cut off at the token limit; not parsed"
        content = _THINK.sub("", reply.content or "", count=1) if reply.content else reply.content
        if tools and reply.tool_calls:
            return "ok", None, content, None
        if schema is None:
            return "ok", None, content, None
        try:
            value = schema.model_validate(json.loads(content or ""))
            if validator is not None:
                validator(value)
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            return "invalid", None, content, _short(error)
        return "ok", value, content, None

    def _record(
        self,
        job: str,
        prompt_version: str,
        tier: Tier,
        model_id: str,
        request: dict[str, Any],
        sent: _Sent,
        outcome: Outcome,
        run_id: str,
    ) -> ModelCall:
        expected = self.config.models.tiers[tier].expected_id
        if model_id != expected:
            raise TierMismatch(
                f"tier {tier} serves {expected} in models.yaml, not the served {model_id}"
            )
        reply = sent.reply
        return ModelCall(
            id=ids.model_call_id(model_id, prompt_version, _exact_input(request)),
            run_id=run_id,
            model_id=model_id,
            prompt_version=prompt_version,
            job=job,
            cache_hit=sent.cache_hit,
            outcome=outcome,
            finish_reason=reply.finish_reason if reply is not None else None,
            input_tokens=reply.input_tokens if reply is not None else 0,
            output_tokens=reply.output_tokens if reply is not None else 0,
            latency_ms=sent.latency_ms,
            cost_usd=sent.cost_usd,
            cap_cost_usd=sent.cap_cost_usd,
            attempts=sent.attempts,
            raw_response=json.dumps(reply.raw if reply is not None else {"error": sent.error}),
            reasoning_text=reply.reasoning if reply is not None else None,
            tier=tier,
        )


def _exact_input(request: dict[str, Any]) -> dict[str, Any]:
    """Everything that shapes the answer except the model ID, which the key holds apart (R14)."""
    return {k: v for k, v in request.items() if k != "model"}


def _short(error: Exception) -> str:
    text = str(error).replace("\n", " ")
    return text if len(text) <= 300 else text[:297] + "..."
