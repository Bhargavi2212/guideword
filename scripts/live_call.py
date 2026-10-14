"""The only code allowed to call Token Factory or Tavily until the Phase 2 gateway exists.

Bhargavi starts every live call. Each model call is estimated before sending (input =
ceil(text characters / 2.5 + tool-schema characters / 1.25) + 32, output = max_tokens; an
upper bound on every billed smoke call of 2026-10-13), refused
if it could push the phase cap, its use's allowance or the laptop allowance over the limit,
sent once with no retries, and recorded at its real cost in budget/ledger.jsonl (git-ignored;
no prompts, responses or keys). In-flight calls hold their estimate, so parallel calls
cannot overshoot a cap together.

CLI (from the repo root, venv active):
  python scripts/live_call.py opening-balance --usd <amount> --use development
  python scripts/live_call.py models
"""

import argparse
import json
import math
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openai
import tavily  # type: ignore[import-untyped]
from guideword.config import Config, TierModel, load_config
from guideword.logs import configure, get_logger
from guideword.schema.enums import BudgetUse, Environment, Tier
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

# The spec 0.3 estimating rule (revised 2026-10-13 from the smoke run), not a budget.
# English text bills at about 2.9 characters per token; tool schemas and tool calls are
# rendered into the prompt at about twice their JSON size; each request adds a chat-template
# wrapper of about 15 tokens.
TEXT_CHARS_PER_TOKEN = 2.5
TOOL_CHARS_PER_TOKEN = 1.25
REQUEST_OVERHEAD_TOKENS = 32
OPENING_BALANCE_PHASE = "opening_balance"
DEFAULT_LEDGER = Path(__file__).resolve().parents[1] / "budget" / "ledger.jsonl"
SCRIPT = Path(__file__).name

log = get_logger("guideword.live_call")

Clock = Callable[[], datetime]


class Refused(RuntimeError):
    """A call was refused before sending; nothing was spent."""


class MissingKey(RuntimeError):
    """A key is not set; names the setting, never a value."""


class CallFailed(RuntimeError):
    """The service rejected or failed the call. Nothing is recorded; nothing is retried."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# Errors the Tavily client raises; OSError covers network failures from requests.
TAVILY_ERRORS: tuple[type[Exception], ...] = (
    tavily.errors.UsageLimitExceededError,
    tavily.errors.BadRequestError,
    tavily.errors.ForbiddenError,
    tavily.errors.InvalidAPIKeyError,
    tavily.errors.TimeoutError,
    OSError,
)


@dataclass(frozen=True)
class Estimate:
    input_tokens: int
    output_tokens: int
    cost_usd: float


def cost_usd(prices: TierModel, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * prices.input_usd_per_1m + output_tokens * prices.output_usd_per_1m
    ) / 1_000_000


def estimate_cost(
    prices: TierModel,
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None,
    max_tokens: int,
) -> Estimate:
    """Upper-bound estimate: output tokens are the requested max_tokens."""
    text_chars = 0
    tool_chars = 0
    for message in messages:
        text_chars += len(str(message.get("content") or ""))
        if message.get("tool_calls"):
            tool_chars += len(json.dumps(message["tool_calls"], separators=(",", ":")))
    for tool in tools or ():
        tool_chars += len(json.dumps(tool, separators=(",", ":")))
    input_tokens = (
        math.ceil(text_chars / TEXT_CHARS_PER_TOKEN + tool_chars / TOOL_CHARS_PER_TOKEN)
        + REQUEST_OVERHEAD_TOKENS
    )
    return Estimate(input_tokens, max_tokens, cost_usd(prices, input_tokens, max_tokens))


class Ledger:
    """The laptop ledger: one SpendEntry per line. Every limit check reads it."""

    def __init__(self, path: Path = DEFAULT_LEDGER) -> None:
        self.path = path
        self._lock = threading.Lock()

    def entries(self) -> list[SpendEntry]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [SpendEntry.model_validate_json(line) for line in lines if line.strip()]

    def append(self, entry: SpendEntry) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(entry.model_dump_json() + "\n")

    def spent(self, *, phase: str | None = None, use: BudgetUse | str | None = None) -> float:
        """Laptop spend, optionally for one phase or one use."""
        return sum(
            e.cost_usd
            for e in self.entries()
            if e.environment == Environment.LAPTOP
            and (phase is None or e.phase == phase)
            and (use is None or e.use == use)
        )


class LiveCaller:
    def __init__(
        self,
        *,
        settings: Settings,
        config: Config,
        ledger: Ledger,
        clock: Clock = lambda: datetime.now(UTC),
        openai_client: Any | None = None,
        tavily_client: Any | None = None,
        script: str = SCRIPT,
    ) -> None:
        self.settings = settings
        self.config = config
        self.ledger = ledger
        self.clock = clock
        self.script = script
        self._openai = openai_client
        self._tavily = tavily_client
        self._holds: dict[int, tuple[str, str, float]] = {}
        self._hold_lock = threading.Lock()
        self._next_hold = 0

    # --- limits -----------------------------------------------------------------------------

    def _use(self, use: BudgetUse | str | None) -> BudgetUse:
        if use is None:
            raise Refused("every call needs a use (--use)")
        try:
            known = BudgetUse(use)
        except ValueError as error:
            raise Refused(f"unknown use {use!r}") from error
        environment = self.config.caps.environment_of(known)
        if environment != Environment.LAPTOP:
            raise Refused(f"use {known} belongs to the {environment} allowance, not the laptop")
        return known

    @contextmanager
    def _hold(self, phase: str, use: BudgetUse, amount: float) -> Iterator[None]:
        """Check every limit with in-flight holds included, then hold `amount` until done."""
        caps = self.config.caps
        if phase not in caps.phase_caps_usd:
            raise Refused(f"phase {phase} has no live-call cap in caps.yaml")
        with self._hold_lock:
            held = list(self._holds.values())
            held_phase = sum(a for p, _, a in held if p == phase)
            held_use = sum(a for _, u, a in held if u == use)
            held_all = sum(a for _, _, a in held)
            phase_cap = caps.phase_caps_usd[phase]
            if self.ledger.spent(phase=phase) + held_phase + amount > phase_cap:
                raise Refused(f"phase {phase} cap ${phase_cap:.2f} would be exceeded")
            use_cap = caps.uses[use].allowance_usd
            if self.ledger.spent(use=use) + held_use + amount > use_cap:
                raise Refused(f"use {use} allowance ${use_cap:.2f} would be exceeded")
            laptop_cap = caps.environment_allowance(Environment.LAPTOP)
            if self.ledger.spent() + held_all + amount > laptop_cap:
                raise Refused(f"laptop allowance ${laptop_cap:.2f} would be exceeded")
            token = self._next_hold
            self._next_hold += 1
            self._holds[token] = (phase, str(use), amount)
        try:
            yield
        finally:
            with self._hold_lock:
                del self._holds[token]

    def _record(self, **fields: Any) -> None:
        self.ledger.append(
            SpendEntry(
                ts=self.clock(),
                environment=Environment.LAPTOP,
                script=self.script,
                **fields,
            )
        )

    # --- clients --------------------------------------------------------------------------

    def _openai_client(self) -> Any:
        if not self.settings.nebius_api_key.get_secret_value():
            raise MissingKey("NEBIUS_API_KEY is not set")
        if self._openai is None:
            self._openai = openai_client(self.settings)
        return self._openai

    def _tavily_client(self) -> Any:
        if not self.settings.tavily_api_key.get_secret_value():
            raise MissingKey("TAVILY_API_KEY is not set")
        if self._tavily is None:
            self._tavily = tavily.TavilyClient(
                api_key=self.settings.tavily_api_key.get_secret_value()
            )
        return self._tavily

    # --- calls ----------------------------------------------------------------------------

    def chat(
        self,
        *,
        tier: Tier | str,
        messages: Sequence[dict[str, Any]],
        phase: str,
        use: BudgetUse | str | None,
        purpose: str,
        max_tokens: int,
        model_id: str | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **request: Any,
    ) -> Any:
        """One chat completion, sent once. `request` passes through (response_format,
        tool_choice, extra_body, ...)."""
        client = self._openai_client()
        known_use = self._use(use)
        prices = self.config.models.tiers[Tier(tier)]
        model = model_id or prices.expected_id
        estimate = estimate_cost(prices, messages, tools, max_tokens)
        with self._hold(phase, known_use, estimate.cost_usd):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": list(messages),
                "max_tokens": max_tokens,
                **request,
            }
            if tools:
                kwargs["tools"] = list(tools)
            try:
                response = client.chat.completions.create(**kwargs)
            except openai.APIStatusError as error:
                raise CallFailed(
                    f"{type(error).__name__}: status {error.status_code}: {error.message}",
                    status=error.status_code,
                ) from error
            except openai.APIError as error:
                raise CallFailed(f"{type(error).__name__}: {error.message}") from error
            usage = response.usage
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            self._record(
                kind="model",
                phase=phase,
                use=known_use,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd(prices, input_tokens, output_tokens),
                purpose=purpose,
            )
        return response

    def model_list(self) -> list[dict[str, Any]]:
        """GET /v1/models as returned (IDs and any prices or context lengths); free."""
        try:
            models = self._openai_client().models.list().data
        except openai.APIError as error:
            raise CallFailed(f"{type(error).__name__}: {error.message}") from error
        return [dict(model.model_dump()) for model in models]

    def list_models(self) -> list[str]:
        """The live model IDs; free, so not recorded."""
        return [str(entry["id"]) for entry in self.model_list()]

    def tavily_search(
        self,
        query: str,
        *,
        phase: str,
        use: BudgetUse | str | None,
        purpose: str,
        max_results: int,
    ) -> Any:
        """One Tavily search. Tavily credits are separate from the $25, so cost is 0."""
        client = self._tavily_client()
        known_use = self._use(use)
        with self._hold(phase, known_use, 0.0):
            try:
                result = client.search(query=query, max_results=max_results)
            except TAVILY_ERRORS as error:
                raise CallFailed(f"Tavily {type(error).__name__}: {error}") from error
            self._record(
                kind="tavily",
                phase=phase,
                use=known_use,
                searches=1,
                cost_usd=0.0,
                purpose=purpose,
            )
        return result

    def record_opening_balance(self, usd: float, *, use: BudgetUse | str) -> None:
        """Spend before this ledger existed (earlier kill tests), from the dashboard."""
        if usd < 0:
            raise ValueError("the opening balance cannot be negative")
        self._record(
            kind="opening_balance",
            phase=OPENING_BALANCE_PHASE,
            use=self._use(use),
            cost_usd=usd,
            purpose="opening balance from the Token Factory dashboard",
        )


def openai_client(settings: Settings) -> openai.OpenAI:
    """The Token Factory client. max_retries=0: a failed call is never retried here."""
    return openai.OpenAI(
        base_url=settings.nebius_base_url,
        api_key=settings.nebius_api_key.get_secret_value(),
        max_retries=0,
    )


def default_caller(script: str = SCRIPT) -> LiveCaller:
    settings = Settings()
    config = load_config(global_budget_usd=settings.global_budget_usd)
    return LiveCaller(settings=settings, config=config, ledger=Ledger(), script=script)


def main(argv: Sequence[str] | None = None) -> int:
    configure()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    opening = commands.add_parser("opening-balance", help="record spend from the dashboard")
    opening.add_argument("--usd", type=float, required=True)
    opening.add_argument("--use", required=True, choices=[u.value for u in BudgetUse])
    commands.add_parser("models", help="list the live model IDs (free)")
    args = parser.parse_args(argv)

    caller = default_caller()
    try:
        if args.command == "opening-balance":
            caller.record_opening_balance(args.usd, use=args.use)
            print(f"recorded opening balance ${args.usd:.2f} under {args.use}")
        else:
            for model_id in caller.list_models():
                print(model_id)
    except (Refused, MissingKey) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
