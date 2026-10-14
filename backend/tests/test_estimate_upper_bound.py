"""The pre-send estimate is an upper bound on every billed smoke call (spec 0.3, 2026-10-13).

Replays docs/smoke/summary.json (committed; billed by Token Factory on 2026-10-13) against
the exact prompts in scripts/smoke_test.py. No network. T7 rows are two calls each and are
left out, as their single row has no single estimate.
"""

import json
from pathlib import Path
from typing import Any

import live_call
import pytest
import smoke_test as s

from guideword.config import load_config
from guideword.schema.enums import Tier

SUMMARY = Path(__file__).resolve().parents[2] / "docs" / "smoke" / "summary.json"
VERDICT = [{"role": "user", "content": s.VERDICT_QUESTION}]
JSON_OBJECT = [{"role": "user", "content": s.JSON_OBJECT_PROMPT}]
TOOLS = [{"role": "user", "content": s.TOOL_PROMPT}]
REQUESTS: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]] | None, int]] = {
    "T2": (s.OK_PROMPT, None, 400),
    "T3": (VERDICT, None, 400),
    "T4": (JSON_OBJECT, None, 400),
    "T5": (s.OK_PROMPT, None, 400),
    "T6": (s.OK_PROMPT, None, 400),
    "T8": (s.OK_PROMPT, None, 32),
    "T9": (s.OK_PROMPT, None, 400),
    "T11": (VERDICT, None, 400),
    "T12": (TOOLS, [s.LOOKUP_UNIT, s.COUNT_ITEMS], 1000),
    "T13": (s.OK_PROMPT, None, 400),
    "T14": (s.filler_messages(s.DEFAULT_FILLER_CHARS), None, 50),
}


def _billed() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(SUMMARY.read_text(encoding="utf-8"))["results"]
    return [r for r in rows if r["test"].split("-")[0] in REQUESTS and r["input_tokens"]]


BILLED = _billed()


def test_replay_covers_the_smoke_run() -> None:
    assert len(BILLED) == 32


@pytest.mark.parametrize("row", BILLED, ids=lambda r: f"{r['test']}-{r['tier']}")
def test_estimate_is_at_least_the_billed_input(row: dict[str, Any]) -> None:
    messages, tools, max_tokens = REQUESTS[row["test"].split("-")[0]]
    config = load_config(global_budget_usd=25.0)
    prices = config.models.tiers[Tier(row["tier"])]
    estimate = live_call.estimate_cost(prices, messages, tools, max_tokens)
    assert estimate.input_tokens >= row["input_tokens"]
    billed = live_call.cost_usd(prices, row["input_tokens"], row["output_tokens"])
    assert estimate.cost_usd >= billed
