"""Running one specialist batch (spec 2.4; plan R4, R34, R40, R43).

`run_batch` writes nothing: it returns every record it made, so batches can run in parallel
and the orchestrator writes them in batch order with `apply_batch`. Code builds every ID.

The tool path (R34): a tool request never carries the answer schema. The specialist may
call its tools; a call past `specialist_max_tool_steps` is refused and recorded, and the
answer is then asked for in the schema, without tools.

A batch of more than one question whose answer is cut off at the token limit, or invalid only
because a question is answered twice or one is answered that was not sent, is re-asked one
question at a time before any of its questions is marked failed (`retry_singly`; the run's
`retry_failed_batch_singly` cap, demo-fixes plan, approved 2026-10-21). The batch and a
question's single call together count one attempt for that question. Other invalid answers
fail the batch as before.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from guideword.config import Config, TierModel
from guideword.gateway.client import (
    BudgetRefused,
    Gateway,
    GatewayResult,
    RepeatedRequest,
    RunBudget,
)
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.reference import ReferenceSet
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import (
    Agent,
    AgentTool,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    RunStatus,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import (
    OUTSIDE_LIBRARY,
    AgentStep,
    Finding,
    ModelCall,
    Question,
    Section,
    ToolCall,
)
from guideword.specialists.causes import offered_cause_ids
from guideword.specialists.context import BatchTooLarge, SpecialistContext, build_context, fit
from guideword.specialists.schema import (
    ANSWERED_TWICE,
    NOT_IN_BATCH,
    BatchAnswer,
    QuestionAnswer,
    check_answer,
    finding_id,
)
from guideword.tools.record import TOOLS, execute_tool

log = get_logger(__name__)

Level = Literal["bulk", "hard", "unsure"]
JOB_FOR_LEVEL: dict[str, str] = {
    "bulk": "specialist_bulk",
    "hard": "specialist_hard",
    "unsure": "unsure_answer",
}
AGENT_TOOLS: dict[Agent, tuple[str, ...]] = {Agent.CHEMISTRY: ("reactivity_lookup",)}
ASK = "Answer every question in the batch, in the required JSON schema."


@dataclass
class BatchOutcome:
    agent: Agent
    question_ids: list[str]
    status: Literal["answered", "failed"] = "failed"
    error: str | None = None
    tier: Tier | None = None
    findings: list[Finding] = field(default_factory=list)
    # the batch's questions with their new status and attempt count
    questions: list[Question] = field(default_factory=list)
    added: list[Question] = field(default_factory=list)
    model_calls: list[ModelCall] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    cost_usd: float = 0.0
    # counted against the run cap (R45)
    cap_cost_usd: float = 0.0
    dropped_ids: tuple[str, ...] = ()
    fell_back_from: tuple[Tier, ...] = ()


def tool_schema(name: str) -> dict[str, Any]:
    spec = TOOLS[name]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": spec.description,
            "parameters": spec.arguments.model_json_schema(),
        },
    }


def _question_rows(questions: Sequence[Question]) -> list[dict[str, Any]]:
    return [{"id": q.id, "text": q.text, "section_id": q.section_id} for q in questions]


def _cause_rows(
    questions: Sequence[Question],
    sections: Mapping[str, Section],
    plant: Plant,
    ref: ReferenceSet,
    context: SpecialistContext,
) -> list[dict[str, Any]]:
    """The library causes valid for the batch that its context can support (R7, R46)."""
    valid = offered_cause_ids(questions, sections, plant, ref, context)
    rows = [
        {"id": c.id, "cause": c.cause, "failing_component_type": c.failing_component_type}
        for c in sorted(ref.causes, key=lambda c: c.id)
        if c.id in valid
    ]
    return rows


def _messages(
    body: str,
    context: SpecialistContext,
    questions: list[dict[str, Any]],
    causes: list[dict[str, Any]],
    max_added: int,
    agent: Agent,
) -> list[dict[str, Any]]:
    # as data: plant notes, step text and added questions cannot close a block (CLAUDE.md §3)
    values = {
        "context": as_data(context.data),
        "questions": as_data(questions),
        "causes": as_data(causes),
    }
    if agent != Agent.CHEMISTRY:
        values["max_added_questions"] = str(max_added)
    return [{"role": "system", "content": render(body, values)}, {"role": "user", "content": ASK}]


@dataclass(frozen=True)
class PreparedBatch:
    """A batch ready to send: what `run_batch` needs, built before any thread starts so a
    dispatch can price every batch from its request alone (R13 as amended)."""

    batch: list[Question]
    agent: Agent
    level: Level
    job: str
    tier: Tier
    model_id: str
    prices: TierModel
    prompt: Prompt
    tools: list[dict[str, Any]]
    context: SpecialistContext
    conversation: list[dict[str, Any]]
    max_added: int
    # set only by the four-tier comparison (spec 2.10): the tier to call instead of the job's
    forced_tier: Tier | None = None


def prepare_batch(
    gateway: Gateway,
    *,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
    sections: Mapping[str, Section],
    questions: Sequence[Question],
    agent: Agent,
    ai_remaining: int,
    level: Level = "bulk",
    tier: Tier | None = None,
) -> "PreparedBatch | BatchOutcome":
    """The batch's context (fitted to the input cap, R43), cause list and messages; a batch
    too large even with every step and job dropped comes back as a failed outcome."""
    caps = config.caps.run
    job = JOB_FOR_LEVEL[level]
    batch = list(questions)
    prompt = load_prompt(f"specialists/{agent.value}", config)
    tools = [tool_schema(t) for t in AGENT_TOOLS.get(agent, ())]
    question_rows = _question_rows(batch)
    max_added = min(caps.ai_questions_per_batch, ai_remaining)
    resolved = gateway.catalog.resolve(tier if tier is not None else Tier(config.routing.jobs[job]))
    prices = config.models.tiers[resolved.tier]

    def measure(ctx: SpecialistContext) -> int:
        causes = _cause_rows(batch, sections, plant, ref, ctx)
        messages = _messages(prompt.body, ctx, question_rows, causes, max_added, agent)
        return estimate_cost(prices, messages, tools, 0).input_tokens

    try:
        context = fit(
            build_context(agent, plant, sections, batch), measure, caps.specialist_max_input_tokens
        )
    except BatchTooLarge as error:
        log.warning(
            "specialist batch too large", extra={"context": {"questions": [q.id for q in batch]}}
        )
        outcome = BatchOutcome(agent=agent, question_ids=[q.id for q in batch])
        return _failed(outcome, batch, str(error), caps.question_max_attempts)
    # offered from the context as sent: a step or job trimmed to fit no longer supports a cause
    cause_rows = _cause_rows(batch, sections, plant, ref, context)
    conversation = _messages(prompt.body, context, question_rows, cause_rows, max_added, agent)
    return PreparedBatch(
        batch=batch,
        agent=agent,
        level=level,
        job=job,
        tier=resolved.tier,
        model_id=resolved.model_id,
        prices=prices,
        prompt=prompt,
        tools=tools,
        context=context,
        conversation=conversation,
        max_added=max_added,
        forced_tier=tier,
    )


def batch_slice_usd(prepared: PreparedBatch, config: Config) -> float:
    """The batch's slice, from its request alone (R13 as amended): the answer and one
    validation retry, and for tool agents the tool request before them (the R34 two-call
    path), each at the agreed estimate with `max_tokens` as output, each later call
    re-sending up to `max_tokens` of earlier output as input. A batch that needs more (a
    further tool request) fails on its own slice; the run goes on."""
    max_tokens = config.caps.run.max_tokens[prepared.job]
    calls = 3 if prepared.tools else 2
    first = estimate_cost(
        prepared.prices, prepared.conversation, prepared.tools or None, max_tokens
    )
    total = 0.0
    for k in range(calls):
        input_tokens = first.input_tokens + k * max_tokens
        total += (
            input_tokens * prepared.prices.input_usd_per_1m
            + max_tokens * prepared.prices.output_usd_per_1m
        ) / 1_000_000
    return total


def run_batch(
    gateway: Gateway,
    *,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
    sections: Mapping[str, Section],
    questions: Sequence[Question],
    agent: Agent,
    budget: RunBudget,
    previous_step_id: str,
    ai_remaining: int,
    existing_question_ids: set[str],
    level: Level = "bulk",
    retry_missing: bool = True,
    made: frozenset[str] = frozenset(),
    prepared: PreparedBatch | None = None,
    retry_singly: bool = False,
) -> BatchOutcome:
    """Answer one batch. `BudgetRefused` from the gateway is not caught: it stops the run,
    except a refusal by the batch's own slice (`budget.slice_id`), which fails the batch. A
    request already made in this run (`made`, its model call IDs) is not sent: the call comes
    back as an error, so the batch fails like any other."""
    caps = config.caps.run
    if prepared is None:
        ready = prepare_batch(
            gateway,
            plant=plant,
            ref=ref,
            config=config,
            sections=sections,
            questions=questions,
            agent=agent,
            ai_remaining=ai_remaining,
            level=level,
        )
        if isinstance(ready, BatchOutcome):
            return ready
        prepared = ready
    job = prepared.job
    batch = prepared.batch
    outcome = BatchOutcome(agent=agent, question_ids=[q.id for q in batch])
    prompt = prepared.prompt
    tools = prepared.tools
    max_added = prepared.max_added
    context = prepared.context
    outcome.dropped_ids = context.dropped_ids
    conversation = list(prepared.conversation)
    tier, model_id = prepared.tier, prepared.model_id
    spent = budget.cap_spent_usd
    step_id = previous_step_id

    def call(**kwargs: Any) -> GatewayResult:
        nonlocal spent
        try:
            result = gateway.call(
                job=job,
                prompt_version=prompt.label,
                run=RunBudget(budget.run_id, spent, budget.limit_usd, budget.slice_id),
                made=made,
                tier=prepared.forced_tier,
                **kwargs,
            )
        except RepeatedRequest as repeated:
            log.error("repeated request refused", extra={"context": {"error": str(repeated)}})
            return GatewayResult(outcome="error", tier=tier, model_id=model_id, error=str(repeated))
        except BudgetRefused as refused:
            if budget.slice_id is None or refused.status != RunStatus.STOPPED_CAP:
                # the batch's records so far go with the refusal, so the run records them
                refused.carry(outcome.model_calls, outcome.cost_usd, outcome.cap_cost_usd)
                raise
            # the slice is used up: the batch fails, and the attempts already made stay
            result = GatewayResult(
                outcome="error",
                tier=tier,
                model_id=model_id,
                error=f"the batch slice is used up: {refused}",
                cost_usd=refused.cost_usd,
                cap_cost_usd=refused.cap_cost_usd,
                model_calls=list(refused.attempts),
            )
        spent += result.cap_cost_usd
        outcome.cost_usd += result.cost_usd
        outcome.cap_cost_usd += result.cap_cost_usd
        outcome.model_calls += result.model_calls
        outcome.tier, outcome.fell_back_from = result.tier, result.fell_back_from
        return result

    # the tool steps (R34: the tool request never carries the schema)
    used = 0
    while tools:
        asked = call(messages=conversation, tools=tools, tool_choice="auto")
        if not asked.tool_calls:
            break
        conversation.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": t.call_id,
                        "type": "function",
                        "function": {"name": t.name, "arguments": t.arguments},
                    }
                    for t in asked.tool_calls
                ],
            }
        )
        stop = False
        for request in asked.tool_calls:
            arguments = _arguments(request.arguments)
            step = AgentStep(
                id=ids.agent_step_id(step_id, agent.value, request.name, arguments),
                run_id=budget.run_id,
                previous_id=step_id,
                agent=agent,
                tool=_agent_tool(request.name),
                arguments=arguments,
                reason=f"{request.name} {json.dumps(arguments, sort_keys=True)}",
                model_call_id=asked.model_calls[-1].id if asked.model_calls else None,
            )
            step_id = step.id
            outcome.steps.append(step)
            if used >= caps.specialist_max_tool_steps:
                refused = f"at most {caps.specialist_max_tool_steps} tool calls per batch"
                tool_call = ToolCall(
                    id=ids.tool_call_id(step.id, request.name, arguments),
                    run_id=budget.run_id,
                    agent_step_id=step.id,
                    tool=request.name,
                    arguments=arguments,
                    result=None,
                    refused_reason=refused,
                )
                stop = True
            else:
                tool_call = execute_tool(
                    budget.run_id, step.id, request.name, arguments, plant=plant, ref=ref
                )
                used += 1
            outcome.tool_calls.append(tool_call)
            content = (
                tool_call.result
                if tool_call.refused_reason is None
                else {"error": tool_call.refused_reason}
            )
            conversation.append(
                {"role": "tool", "tool_call_id": request.call_id, "content": json.dumps(content)}
            )
        if stop:
            break

    def validator(value: Any) -> None:
        if not isinstance(value, BatchAnswer):
            raise ValueError("not a batch answer")
        check_answer(
            value,
            questions=batch,
            context=context,
            sections=sections,
            plant=plant,
            ref=ref,
            tier=tier,
        )

    final = call(messages=conversation, schema=BatchAnswer, validator=validator)
    if final.outcome != "ok" or not isinstance(final.value, BatchAnswer):
        error = final.error or final.outcome
        if retry_singly and len(batch) > 1 and _batch_shaped(final.outcome, error):
            return _each_alone(
                outcome,
                error,
                gateway,
                plant=plant,
                ref=ref,
                config=config,
                sections=sections,
                batch=batch,
                agent=agent,
                budget=RunBudget(budget.run_id, spent, budget.limit_usd, budget.slice_id),
                previous_step_id=step_id,
                existing_question_ids=existing_question_ids,
                level=level,
                made=made,
            )
        return _failed(outcome, batch, error, caps.question_max_attempts)

    answer: BatchAnswer = final.value
    model_call_id = final.model_calls[-1].id if final.model_calls else None
    tier = final.tier
    answered = {a.question_id: a for a in answer.answers}
    answer_step = AgentStep(
        id=ids.agent_step_id(
            step_id, agent.value, "answer", {"question_ids": outcome.question_ids, "level": level}
        ),
        run_id=budget.run_id,
        previous_id=step_id,
        agent=agent,
        tool=AgentTool.ANSWER,
        arguments={"question_ids": outcome.question_ids, "level": level},
        reason=f"answered {len(answered)} of {len(batch)} questions",
        model_call_id=model_call_id,
    )
    outcome.steps.append(answer_step)
    missing: list[Question] = []
    for question in batch:
        item = answered.get(question.id)
        if item is None:
            missing.append(question)
            continue
        outcome.questions.append(_answered(question, item, model_call_id))
        outcome.findings += _findings(question, item, tier, budget.run_id, model_call_id)
    outcome.added = _added(answer, budget.run_id, max_added, existing_question_ids, model_call_id)
    outcome.status = "answered"
    for question in missing:
        if not retry_missing:
            outcome.questions.append(_attempted(question, caps.question_max_attempts))
            continue
        try:
            alone = run_batch(
                gateway,
                plant=plant,
                ref=ref,
                config=config,
                sections=sections,
                questions=[question],
                agent=agent,
                budget=RunBudget(budget.run_id, spent, budget.limit_usd, budget.slice_id),
                previous_step_id=answer_step.id,
                ai_remaining=0,
                existing_question_ids=existing_question_ids,
                level=level,
                retry_missing=False,
                made=made,
            )
        except BudgetRefused as refused:
            refused.carry(outcome.model_calls, outcome.cost_usd, outcome.cap_cost_usd)
            raise
        spent += alone.cap_cost_usd
        _merge(outcome, alone)
    return outcome


def _batch_shaped(outcome: str, error: str) -> bool:
    """A failure about the batch, not its answers: cut off, or a question answered twice or
    answered without being sent."""
    if outcome == "truncated":
        return True
    return outcome == "invalid" and (ANSWERED_TWICE in error or NOT_IN_BATCH in error)


def _each_alone(
    outcome: BatchOutcome,
    error: str,
    gateway: Gateway,
    *,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
    sections: Mapping[str, Section],
    batch: Sequence[Question],
    agent: Agent,
    budget: RunBudget,
    previous_step_id: str,
    existing_question_ids: set[str],
    level: Level,
    made: frozenset[str],
) -> BatchOutcome:
    """Re-ask each of the batch's questions alone; the batch is answered if any one is."""
    log.info(
        "batch re-asked one question at a time",
        extra={"context": {"run_id": budget.run_id, "error": error, "questions": len(batch)}},
    )
    spent = budget.cap_spent_usd
    answered = False
    for question in batch:
        try:
            alone = run_batch(
                gateway,
                plant=plant,
                ref=ref,
                config=config,
                sections=sections,
                questions=[question],
                agent=agent,
                budget=RunBudget(budget.run_id, spent, budget.limit_usd, budget.slice_id),
                previous_step_id=previous_step_id,
                ai_remaining=0,
                existing_question_ids=existing_question_ids,
                level=level,
                retry_missing=False,
                made=made,
            )
        except BudgetRefused as refused:
            # the batch's own calls, and the singles' before this one, were paid
            refused.carry(outcome.model_calls, outcome.cost_usd, outcome.cap_cost_usd)
            raise
        spent += alone.cap_cost_usd
        answered = answered or alone.status == "answered"
        _merge(outcome, alone)
    outcome.status = "answered" if answered else "failed"
    outcome.error = None if answered else error
    return outcome


def apply_batch(writer: StepWriter, outcome: BatchOutcome) -> None:
    """Write a batch's records into the run, each with its event. A finding ID already stored
    is stored once (R42); questions take their new status; added questions join as open."""
    for step in outcome.steps:
        writer.add_step(step)
    for call in outcome.model_calls:
        writer.add_model_call(call, fell_back_from=outcome.fell_back_from)
    for tool_call in outcome.tool_calls:
        writer.add_tool_call(tool_call)
    for finding in outcome.findings:
        writer.add_finding(finding)
    for question in [*outcome.questions, *outcome.added]:
        writer.put_question(question)
    writer.add_spent(outcome.cost_usd, cap_usd=outcome.cap_cost_usd)


def _arguments(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {"_unparsed": text}
    return value if isinstance(value, dict) else {"_unparsed": text}


def _agent_tool(name: str) -> AgentTool:
    try:
        return AgentTool(name)
    except ValueError:
        return AgentTool.ANSWER


def _attempted(question: Question, max_attempts: int) -> Question:
    attempts = question.attempts + 1
    status = QuestionStatus.FAILED if attempts >= max_attempts else question.status
    return question.model_copy(update={"attempts": attempts, "status": status})


def _failed(
    outcome: BatchOutcome, batch: Sequence[Question], error: str, max_attempts: int
) -> BatchOutcome:
    outcome.status = "failed"
    outcome.error = error
    outcome.questions = [_attempted(q, max_attempts) for q in batch]
    return outcome


def _answered(question: Question, item: QuestionAnswer, model_call_id: str | None) -> Question:
    changes: dict[str, Any] = {"attempts": question.attempts + 1, "model_call_id": model_call_id}
    if item.not_credible is not None:
        changes |= {
            "status": QuestionStatus.NOT_CREDIBLE,
            "not_credible_reason": item.not_credible.reason,
        }
    else:
        changes["status"] = QuestionStatus.ANSWERED
    return Question.model_validate({**question.model_dump(), **changes})


def _findings(
    question: Question, item: QuestionAnswer, tier: Tier, run_id: str, model_call_id: str | None
) -> list[Finding]:
    return [
        Finding(
            id=finding_id(question.id, tier, f),
            run_id=run_id,
            question_id=question.id,
            tier=tier,
            cause_id=f.cause_id if f.cause_id != OUTSIDE_LIBRARY else OUTSIDE_LIBRARY,
            cause_text=f.cause_text if f.cause_id == OUTSIDE_LIBRARY else None,
            failing_component_type=f.failing_component_type,
            failing_component_ids=list(f.failing_component_ids),
            consequence=f.consequence,
            safeguard_ids=list(f.safeguard_ids),
            adequacy=f.adequacy,
            confidence=f.confidence,
            model_call_id=model_call_id,
        )
        for f in item.findings
    ]


def _added(
    answer: BatchAnswer,
    run_id: str,
    limit: int,
    existing: set[str],
    model_call_id: str | None,
) -> list[Question]:
    out: list[Question] = []
    for proposed in answer.added_questions:
        if len(out) >= limit:
            log.info(
                "added question over the cap not kept", extra={"context": {"text": proposed.text}}
            )
            continue
        question_id = ids.added_by_ai_question_id(proposed.section_id, proposed.text)
        if question_id in existing or question_id in {q.id for q in out}:
            continue
        out.append(
            Question(
                id=question_id,
                run_id=run_id,
                kind=QuestionKind.ADDED_BY_AI,
                origin=QuestionOrigin.ADDED_BY_AI,
                status=QuestionStatus.OPEN,
                section_id=proposed.section_id,
                text=proposed.text,
                model_call_id=model_call_id,
            )
        )
    return out


def _merge(outcome: BatchOutcome, extra: BatchOutcome) -> None:
    outcome.findings += extra.findings
    outcome.questions += extra.questions
    outcome.model_calls += extra.model_calls
    outcome.tool_calls += extra.tool_calls
    outcome.steps += extra.steps
    outcome.cost_usd += extra.cost_usd
    outcome.cap_cost_usd += extra.cap_cost_usd
