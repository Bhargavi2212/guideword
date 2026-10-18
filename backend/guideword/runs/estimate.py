"""The upper-bound cost of a new run, returned by `POST /runs` (spec 2.8; plan R20).

The agreed estimate rule (input = characters / 3.5, output = `max_tokens`), applied to the run's
real first-step inputs and summed over every call the run could make, then capped at the
run's spend cap. It is an upper bound, never a forecast:
- the whole-plant pass: two asks (R50 safety net) of two attempts each (the validation retry);
- every specialist batch at bulk, at its admission slice (R13 as amended);
- `orchestrator_max_steps` orchestrator steps, each at `max_tokens`, with the tools offered;
- severity for up to two findings per question, in full batches whose findings carry the
  longest texts the answer schema allows, each call at `max_tokens`.
"""

import math
from collections.abc import Sequence
from typing import Any, get_args

from guideword.config import Config
from guideword.gateway.client import Gateway
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.prompts import load_prompt
from guideword.orchestrator.loop import OrchestratorStepper
from guideword.orchestrator.tools import tool_schemas
from guideword.orchestrator.view import build_view, by_agent
from guideword.ranking.severity import JOB as SEVERITY_JOB
from guideword.ranking.severity import severity_messages
from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import Adequacy, Confidence, FailingComponentType, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding, Question, Run, Section
from guideword.screen.step import JOB as SCREEN_JOB
from guideword.screen.step import PlantScreenStepper
from guideword.specialists.batch import batches
from guideword.specialists.run import BatchOutcome, batch_slice_usd, prepare_batch
from guideword.specialists.schema import Text200, Text300

FINDINGS_PER_QUESTION = 2  # R20
SCREEN_ASKS = 2  # the first ask and the safety net's re-ask (R50 review)
ATTEMPTS = 2  # an answer and its one validation retry


def _longest(text_type: Any) -> int:
    """The `max_length` of a text type of the specialist answer schema."""
    for meta in get_args(text_type)[1:]:
        longest = getattr(meta, "max_length", None)
        if longest is not None:
            return int(longest)
    raise ValueError(f"{text_type} has no max_length")


def calls_usd(prices: object, input_tokens: int, max_tokens: int, calls: int) -> float:
    """`calls` calls in one conversation, each re-sending up to `max_tokens` of earlier output."""
    total = 0.0
    for k in range(calls):
        total += (
            (input_tokens + k * max_tokens) * prices.input_usd_per_1m  # type: ignore[attr-defined]
            + max_tokens * prices.output_usd_per_1m  # type: ignore[attr-defined]
        ) / 1_000_000
    return total


def run_upper_bound(
    run: Run,
    *,
    plant: Plant,
    sections: Sequence[Section],
    questions: Sequence[Question],
    ref: ReferenceSet,
    config: Config,
    gateway: Gateway,
) -> float:
    caps = config.caps.run
    by_id = {s.id: s for s in sections}
    total = 0.0

    # the whole-plant pass
    screen = PlantScreenStepper(gateway, config=config, ref=ref, plant=plant)
    base = ":".join(run.id.split(":")[:2])
    messages = screen.messages([q.kind.value for q in questions], f"Request marker: {base}")
    prices = config.models.tiers[Tier(config.routing.jobs[SCREEN_JOB])]
    first = estimate_cost(prices, messages, None, caps.max_tokens[SCREEN_JOB])
    total += SCREEN_ASKS * calls_usd(
        prices, first.input_tokens, caps.max_tokens[SCREEN_JOB], ATTEMPTS
    )

    # every specialist batch, at bulk
    bulk_tier = Tier(config.routing.jobs["specialist_bulk"])
    for agent, question_ids in sorted(by_agent(list(questions), by_id).items()):
        mine = [q for q in questions if q.id in set(question_ids)]
        for group in batches(mine, by_id, caps.specialist_batch_size[bulk_tier]):
            prepared = prepare_batch(
                gateway,
                plant=plant,
                ref=ref,
                config=config,
                sections=by_id,
                questions=group,
                agent=agent,
                ai_remaining=caps.ai_questions_per_run,
            )
            if not isinstance(prepared, BatchOutcome):
                total += batch_slice_usd(prepared, config)

    # the orchestrator's steps
    orchestrator = OrchestratorStepper(gateway, config=config, ref=ref, plant=plant)
    view = build_view(
        run,
        questions=questions,
        findings=[],
        steps=[],
        tool_calls=[],
        sections=by_id,
        caps=caps,
        limit_usd=run.spend_cap_usd,
    )
    prices = config.models.tiers[Tier(config.routing.jobs["orchestrator"])]
    step = estimate_cost(
        prices, orchestrator.messages(view), tool_schemas(), caps.max_tokens["orchestrator"]
    )
    total += caps.orchestrator_max_steps * step.cost_usd

    # severity: up to two findings per question, in full batches of the longest findings
    size = caps.severity_batch_size
    count = FINDINGS_PER_QUESTION * len(questions)
    if count and plant.locations:
        location = plant.locations[0].id
        sample = [
            Finding(
                id=ids.finding_id(
                    q.id, "lightning", [location], cause_text="x" * _longest(Text200)
                ),
                run_id=run.id,
                question_id=q.id,
                tier=Tier.LIGHTNING,
                cause_id=OUTSIDE_LIBRARY,
                cause_text="x" * _longest(Text200),
                failing_component_type=FailingComponentType.EXTERNAL,
                failing_component_ids=[location],
                consequence="x" * _longest(Text300),
                adequacy=Adequacy.UNKNOWN,
                confidence=Confidence.SURE,
            )
            for q in list(questions)[:size]
        ]
        prompt = load_prompt("severity", config)
        batch = severity_messages(prompt, sample, {q.id: q for q in questions}, ref, plant)
        prices = config.models.tiers[Tier(config.routing.jobs[SEVERITY_JOB])]
        call = estimate_cost(prices, batch, None, caps.max_tokens[SEVERITY_JOB])
        total += math.ceil(count / size) * call.cost_usd

    return round(min(total, run.spend_cap_usd), 6)
