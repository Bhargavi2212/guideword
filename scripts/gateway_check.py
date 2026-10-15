"""Live check of the real gateway (spec 2.2). Bhargavi runs it; tests use a fake transport.

  python scripts/gateway_check.py

One schema call per tier through the gateway, plus the specialist path on Lightning: tool
calling together with strict json_schema and reasoning off (the smoke test tried tool calls
and structured output separately, never together). Use `development`, phase 2; every call
passes the budget guard. The results go to docs/gateway-check.md; the decision on
`tools_with_schema` (R34) is written from that file afterwards, never by this script.
"""

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused, Gateway, GatewayResult
from guideword.gateway.ledgers import LaptopLedger, Ledger
from guideword.gateway.transport import OpenAITransport, ToolCallRequest, Transport
from guideword.logs import configure
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse, Tier
from guideword.settings import Settings
from pydantic import BaseModel

PROMPT_VERSION = "gateway-check/v1"
JOB = "specialist_bulk"
OUT = Path(__file__).resolve().parents[1] / "docs" / "gateway-check.md"
ASK = [{"role": "user", "content": "Is water wet? Answer in the schema, one short reason."}]
TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_unit",
        "description": "Look up the unit of a process quantity.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
}
TOOL_ASK = [
    {
        "role": "user",
        "content": "Use the lookup_unit tool for 'pressure', then answer in the schema "
        "with the unit as the reason.",
    }
]


class Verdict(BaseModel):
    verdict: str
    reason: str


@dataclass(frozen=True)
class Row:
    check: str
    tier: str
    outcome: str
    detail: str
    tokens: str
    cost_usd: float
    latency_ms: float
    cached: bool = False


def _row(check: str, result: GatewayResult, detail: str) -> Row:
    tokens = " + ".join(f"{c.input_tokens}/{c.output_tokens}" for c in result.model_calls) or "-"
    latency = sum(c.latency_ms for c in result.model_calls)
    return Row(
        check,
        str(result.tier),
        result.outcome,
        detail,
        tokens,
        result.cost_usd,
        latency,
        result.cache_hit,
    )


def _after_tool(call: ToolCallRequest) -> list[dict[str, Any]]:
    """The conversation after the tool ran: the model's call, then the tool's result."""
    return [
        *TOOL_ASK,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call.call_id,
            "content": json.dumps({"unit": "kPa gauge"}),
        },
    ]


def _tool_row(check: str, result: GatewayResult) -> Row:
    if not result.tool_calls:
        return _row(check, result, "no tool call: " + (result.content or "")[:60])
    call = result.tool_calls[0]
    return _row(check, result, f"{call.name} {call.arguments} valid={_valid_json(call.arguments)}")


def run_checks(gateway: Gateway, run_id: str) -> list[Row]:
    from guideword.gateway.client import RunBudget  # noqa: PLC0415

    budget = RunBudget(run_id, 0.0, gateway.config.caps.run.run_spend_cap_usd)
    common: dict[str, Any] = {"job": JOB, "prompt_version": PROMPT_VERSION, "run": budget}
    rows = []
    for tier in Tier:
        result = gateway.call(messages=ASK, schema=Verdict, tier=tier, **common)
        rows.append(_row("schema", result, result.error or (result.content or "")[:80]))

    # one request: tools and the answer schema together (tools_with_schema: true)
    first = gateway.call(
        messages=TOOL_ASK,
        schema=Verdict,
        tools=[TOOL],
        tool_choice="auto",
        tier=Tier.LIGHTNING,
        **common,
    )
    rows.append(_tool_row("tools + schema: tool call", first))
    if first.tool_calls:
        second = gateway.call(
            messages=_after_tool(first.tool_calls[0]),
            schema=Verdict,
            tools=[TOOL],
            tier=Tier.LIGHTNING,
            **common,
        )
        rows.append(
            _row("tools + schema: answer", second, second.error or (second.content or "")[:80])
        )

    # two requests: the tool call without a schema, then the answer in it (tools_with_schema: false)
    tool_only = gateway.call(
        messages=TOOL_ASK, tools=[TOOL], tool_choice="auto", tier=Tier.LIGHTNING, **common
    )
    rows.append(_tool_row("two calls: tool call", tool_only))
    if tool_only.tool_calls:
        answer = gateway.call(
            messages=_after_tool(tool_only.tool_calls[0]),
            schema=Verdict,
            tier=Tier.LIGHTNING,
            **common,
        )
        rows.append(_row("two calls: answer", answer, answer.error or (answer.content or "")[:80]))
    return rows


def _valid_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _works(rows: Sequence[Row], prefix: str) -> bool:
    path = [r for r in rows if r.check.startswith(prefix)]
    return len(path) == 2 and all(r.outcome == "ok" for r in path)


def render(rows: Sequence[Row], when: datetime) -> str:
    lines = [
        "# Gateway check (spec 2.2)",
        "",
        f"Run {when:%Y-%m-%d %H:%M} UTC by Bhargavi with `python scripts/gateway_check.py` "
        "(use `development`, phase 2). Generated by the script; not edited by hand. A cached "
        "row was paid for on an earlier run and costs nothing now.",
        "",
        "| Check | Tier | Outcome | Detail | Tokens in/out | Cost (USD) | Cached | Latency (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r.check} | {r.tier} | {r.outcome} | {detail} | {r.tokens} "
            f"| {r.cost_usd:.5f} | {'yes' if r.cached else 'no'} | {r.latency_ms:.0f} |"
        )
    total = sum(r.cost_usd for r in rows)
    combined = _works(rows, "tools + schema")
    two_calls = _works(rows, "two calls")
    lines += [
        "",
        f"**Paid this run:** ${total:.5f}.",
        f"**Tools with schema on Lightning:** {'works' if combined else 'does not work'} "
        f"(`tools_with_schema: {'true' if combined else 'false'}` for Lightning, decision R34).",
        f"**Two calls on Lightning (tool, then the schema answer):** "
        f"{'works' if two_calls else 'does not work'}.",
        "",
    ]
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    out: Path = OUT,
) -> int:
    configure()
    settings = settings if settings is not None else Settings()
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    sessions = make_session_factory(settings.database_url)
    gateway = Gateway(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else LaptopLedger(),
        use=BudgetUse.DEVELOPMENT,
        phase="2",
        clock=lambda: datetime.now(UTC),
    )
    try:
        rows = run_checks(gateway, "run:gateway-check")
    except BudgetRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    out.write_text(render(rows, datetime.now(UTC)), encoding="utf-8", newline="\n")
    for r in rows:
        print(f"{r.check:<28} {r.tier:<10} {r.outcome:<10} ${r.cost_usd:.5f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
