"""A scripted fake model for whole runs: the orchestrator drains every open list at bulk and
then finishes, each specialist answers every question with one outside-library finding on
the first location in its context, and severity rates every finding S3."""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from guideword.config import load_config
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.fake import reply
from guideword.gateway.transport import Reply, ToolCallRequest

_BLOCK = r"<{0}>\s*(.*?)\s*</{0}>"
Script = Callable[[str, dict[str, Any]], Reply]


def block(request: dict[str, Any], name: str) -> Any:
    match = re.search(_BLOCK.format(name), request["messages"][0]["content"], re.S)
    assert match is not None, name
    return json.loads(match.group(1))


def _input_tokens(request: dict[str, Any]) -> int:
    """The request's own estimated input: a realistic bill never exceeds the estimate."""
    prices = next(iter(load_config(global_budget_usd=25.0).models.tiers.values()))
    return estimate_cost(prices, request["messages"], request.get("tools"), 0).input_tokens


def _specialist(
    request: dict[str, Any],
    not_credible_every: int = 0,
    tokens: tuple[int | None, int] = (100, 50),
) -> Reply:
    if tokens[0] is None:
        tokens = (_input_tokens(request), tokens[1])
    locations = block(request, "context").get("locations") or []
    if not locations:
        # nothing citable for an external cause: dismiss, so the answer stays valid
        return reply(
            {
                "answers": [
                    {
                        "question_id": q["id"],
                        "not_credible": {"reason": "no location"},
                        "findings": [],
                    }
                    for q in block(request, "questions")
                ],
                "added_questions": [],
            },
            input_tokens=tokens[0],
            output_tokens=tokens[1],
        )
    location = locations[0]["id"]

    def dismissed(i: int) -> bool:
        return not_credible_every > 0 and i % not_credible_every == 0

    return reply(
        {
            "answers": [
                {
                    "question_id": q["id"],
                    "not_credible": {"reason": "cannot happen here"},
                    "findings": [],
                }
                if dismissed(i)
                else {
                    "question_id": q["id"],
                    "not_credible": None,
                    "findings": [
                        {
                            "cause_id": "outside_library",
                            "cause_text": "something outside",
                            "failing_component_type": "external",
                            "failing_component_ids": [location],
                            "consequence": "a release",
                            "safeguard_ids": [],
                            "adequacy": "unknown",
                            "confidence": "sure",
                            "reason": "test",
                        }
                    ],
                }
                for i, q in enumerate(block(request, "questions"))
            ],
            "added_questions": [],
        },
        input_tokens=tokens[0],
        output_tokens=tokens[1],
    )


def make_script(
    orchestrator_output_tokens: int = 50,
    secret: str | None = None,
    not_credible_every: int = 0,
    specialist_tokens: tuple[int | None, int] = (100, 50),
    screen_hypotheses: list[dict[str, Any]] | None = None,
) -> Script:
    """`secret` puts that text into every severity reply (to test the export's key check);
    `not_credible_every` dismisses every n-th question of a batch as not credible."""

    def script(job: str, request: dict[str, Any]) -> Reply:
        if job == "plant_screen":
            return reply({"hypotheses": screen_hypotheses or []})
        if job == "orchestrator":
            view = block(request, "view")
            agents = sorted(view["open"])
            if agents:
                retry = view["retry_at_hard"].get(agents[0], {"count": 0})["count"]
                level = "bulk" if view["open"][agents[0]]["count"] > retry else "hard"
                name, args = "dispatch_specialist", {"agent": agents[0], "level": level}
            else:
                name, args = "finish", {}
            call = ToolCallRequest("t", name, json.dumps({"reason": "go", **args}))
            return reply(tool_calls=(call,), output_tokens=orchestrator_output_tokens)
        if job == "severity_reason":
            reason = "one person hurt" if secret is None else f"one person hurt {secret}"
            return reply(
                {
                    "severities": [
                        {"finding_id": f["finding_id"], "severity_class": "S3", "reason": reason}
                        for f in block(request, "findings")
                    ]
                }
            )
        return _specialist(request, not_credible_every, specialist_tokens)

    return script


@pytest.fixture
def script() -> Script:
    return make_script()


@pytest.fixture
def capped_script() -> Script:
    """Each orchestrator turn really spends about $0.01, so the run meets the severity reserve
    at a cap of 0.08."""
    return make_script(orchestrator_output_tokens=2000)


@pytest.fixture
def script_factory() -> Callable[..., Script]:
    return make_script
