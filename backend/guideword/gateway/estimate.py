"""The agreed cost estimate (spec 0.3, revised 2026-10-13): an upper bound on billed calls.

Input tokens = ceil(text characters / 2.5 + tool-schema and tool-call characters / 1.25)
+ 32 per request; output tokens = the requested max_tokens. English text bills at about
2.9 characters per token, tool schemas render at about twice their JSON size, and each
request adds a chat-template wrapper of about 15 tokens. This is an estimating rule, not a
budget: every limit lives in config/caps.yaml.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from guideword.config import TierModel

TEXT_CHARS_PER_TOKEN = 2.5
TOOL_CHARS_PER_TOKEN = 1.25
REQUEST_OVERHEAD_TOKENS = 32


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
