"""The orchestrator loop (spec 2.5; plan R3, R4, R24, R38, R44).

One `advance` in the analysis phase is one Ultra call (native tool calling, a tool required)
that picks exactly one tool. Code runs it, records the agent step and the tool call, and
returns. The guards are code: `finish` is refused while a question is open; an answered
question is not sent again; the step cap stops the run; the severity reserve ends the
analysis phase so severity can run; malformed arguments are refused once, and a second
refusal in a row fails the run; the orchestrator's own call failing twice fails the run.
"""

import json
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, GatewayResult, RunBudget
from guideword.gateway.prompts import load_prompt, render
from guideword.logs import get_logger
from guideword.orchestrator.tools import ARGUMENTS, Dispatch, Reactivity, tool_schemas
from guideword.orchestrator.view import (
    build_view,
    by_agent,
    linked_ids,
    prioritised,
    reanswers_used,
    unsure_question_ids,
)
from guideword.questions.coverage import coverage
from guideword.ranking.severity import SeverityReserve, severity_reserve
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import Agent, AgentTool, EventType, QuestionStatus, RunStatus, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import AgentStep, Hypothesis, Question, Run, Section, ToolCall
from guideword.specialists.batch import batches
from guideword.specialists.routing import agent_for
from guideword.specialists.run import (
    JOB_FOR_LEVEL,
    BatchOutcome,
    apply_batch,
    batch_slice_usd,
    prepare_batch,
    run_batch,
)
from guideword.tools.record import execute_tool

log = get_logger(__name__)
ADMISSION = "admission"

JOB = "orchestrator"
ASK = "Choose the next step: call exactly one tool."
NEXT = "severity"
MALFORMED = "bad arguments"


class OrchestratorStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.caps = config.caps.run
        self.prompt = load_prompt("orchestrator", config)

    # --- one step ------------------------------------------------------------------------

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        caps = self.caps
        sections = {s.id: s for s in writer.sections()}
        questions = writer.questions()
        findings = writer.findings()
        steps = writer.steps()
        tool_calls = writer.tool_calls()
        hypotheses = writer.hypotheses()
        mine = [s for s in steps if s.agent == Agent.ORCHESTRATOR]
        if len(mine) >= caps.orchestrator_max_steps:
            writer.emit(
                EventType.CAP_HIT,
                {"reason": "orchestrator_max_steps", "limit": caps.orchestrator_max_steps},
            )
            return StepResult(status=RunStatus.STOPPED_CAP)

        # what severity will need for the findings so far; the analysis may spend up to the
        # rest of the cap (R38, with the reserve computed after the case D dev run)
        reserve = severity_reserve(findings, questions, self.plant, self.ref, self.config)
        limit = run.spend_cap_usd - reserve.usd
        log.info(
            "severity reserve",
            extra={
                "context": {
                    "run_id": run.id,
                    "reserve_usd": reserve.usd,
                    "unrated": reserve.unrated,
                    "calls": reserve.calls,
                    "per_call_usd": reserve.per_call_usd,
                    "limit_usd": limit,
                }
            },
        )
        view = build_view(
            run,
            questions=questions,
            findings=findings,
            steps=steps,
            tool_calls=tool_calls,
            sections=sections,
            caps=caps,
            limit_usd=limit,
            hypotheses=hypotheses,
        )
        system = render(
            self.prompt.body,
            {
                "view": json.dumps(view, indent=1, ensure_ascii=False),
                "dispatch_max_question_ids": str(caps.orchestrator_view.dispatch_max_question_ids),
                "unsure_reanswers_left": str(view["unsure_reanswers_left"]),
            },
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": ASK},
        ]
        result: GatewayResult | None = None
        for attempt in (1, 2):
            try:
                result = self._call(run, writer, messages, limit)
            except BudgetRefused as refused:
                return self._refused(writer, refused, reserve)
            if result.outcome == "ok" and result.tool_calls:
                break
            if attempt == 2:
                log.warning("orchestrator call failed twice", extra={"context": {"run_id": run.id}})
                return StepResult(status=RunStatus.FAILED)
            messages = [
                *messages,
                {"role": "assistant", "content": result.content or ""},
                {
                    "role": "user",
                    "content": "That was not a tool call. Call exactly one of the tools.",
                },
            ]
        if result is None:
            return StepResult(status=RunStatus.FAILED)
        request = result.tool_calls[0]
        arguments = _parse(request.arguments)
        previous = mine[-1].id if mine else run.id
        tool = request.name if request.name in ARGUMENTS else None
        step = AgentStep(
            id=ids.agent_step_id(previous, Agent.ORCHESTRATOR.value, request.name, arguments),
            run_id=run.id,
            previous_id=previous,
            agent=Agent.ORCHESTRATOR,
            # a tool name the run does not offer is recorded under its own name when the enum
            # has it (a later-phase tool), else as check_coverage, and refused below
            tool=_agent_tool(request.name),
            arguments=arguments,
            reason=str(arguments.get("reason") or "")[:200] or f"{request.name}",
            model_call_id=result.model_calls[-1].id if result.model_calls else None,
        )
        writer.add_step(step)
        if tool is None:
            return self._malformed(
                writer,
                step,
                request.name,
                arguments,
                f"{MALFORMED}: {request.name} is not offered",
                tool_calls,
            )
        try:
            parsed = ARGUMENTS[tool].model_validate(arguments)
        except ValidationError as error:
            reason = f"{MALFORMED}: " + "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                for e in error.errors()
            )
            return self._malformed(writer, step, tool, arguments, reason, tool_calls)

        if isinstance(parsed, Dispatch):
            return self._dispatch(
                run, writer, step, parsed, arguments, questions, findings, sections, reserve
            )
        if isinstance(parsed, Reactivity):
            call = execute_tool(
                run.id,
                step.id,
                "reactivity_lookup",
                {"chemical_a": parsed.chemical_a, "chemical_b": parsed.chemical_b},
                plant=self.plant,
                ref=self.ref,
            )
            if call.result is not None:
                # the one-line result the next view shows; added before the call is recorded
                call = call.model_copy(
                    update={"result": call.result | {"summary": _reactivity_summary(call.result)}}
                )
            writer.add_tool_call(call)
            return StepResult()
        if tool == "finish":
            return self._finish(writer, step, arguments, questions)
        lines, failed = coverage(list(sections.values()), questions, findings)
        open_count = sum(1 for q in questions if q.status == QuestionStatus.OPEN)
        self._record(
            writer,
            step,
            tool,
            arguments,
            {
                "summary": f"{open_count} open, {len(failed)} failed",
                "lines": [line.model_dump() for line in lines],
                "failed": failed,
            },
        )
        return StepResult()

    # --- the tools -----------------------------------------------------------------------

    def _finish(
        self,
        writer: StepWriter,
        step: AgentStep,
        arguments: dict[str, Any],
        questions: Sequence[Question],
    ) -> StepResult:
        open_ids = sorted(q.id for q in questions if q.status == QuestionStatus.OPEN)
        if open_ids:
            shown = ", ".join(open_ids[: self.caps.orchestrator_view.id_list_max])
            more = "" if len(open_ids) <= self.caps.orchestrator_view.id_list_max else ", ..."
            self._record(
                writer,
                step,
                "finish",
                arguments,
                None,
                f"{len(open_ids)} questions are open: {shown}{more}",
            )
            return StepResult()
        self._record(
            writer,
            step,
            "finish",
            arguments,
            {"summary": "accepted: every question answered, not credible or failed"},
        )
        return StepResult(next_step=NEXT)

    def _dispatch(
        self,
        run: Run,
        writer: StepWriter,
        step: AgentStep,
        args: Dispatch,
        arguments: dict[str, Any],
        questions: Sequence[Question],
        findings: Sequence[Any],
        sections: dict[str, Section],
        reserve: SeverityReserve,
    ) -> StepResult:
        caps = self.caps
        agent = Agent(args.agent)
        limit = caps.orchestrator_view.dispatch_max_question_ids
        by_id = {q.id: q for q in questions}
        hypotheses = writer.hypotheses() if args.priority else []
        eligible = self._eligible(agent, args.level, questions, findings, sections, hypotheses)
        skipped: list[str] = []
        if args.question_ids is None:
            chosen = eligible[:limit]
            if not chosen:
                self._record(
                    writer,
                    step,
                    "dispatch_specialist",
                    arguments,
                    None,
                    f"nothing to dispatch to {agent.value} at level {args.level}",
                )
                return StepResult()
        else:
            if len(args.question_ids) > limit:
                self._record(
                    writer,
                    step,
                    "dispatch_specialist",
                    arguments,
                    None,
                    f"{MALFORMED}: more than {limit} question IDs",
                )
                return StepResult()
            unknown = [q for q in args.question_ids if q not in by_id]
            if unknown:
                self._record(
                    writer,
                    step,
                    "dispatch_specialist",
                    arguments,
                    None,
                    f"{MALFORMED}: unknown question IDs {', '.join(unknown)}",
                )
                return StepResult()
            wrong = [q for q in args.question_ids if agent_for(by_id[q], sections) != agent]
            if wrong:
                owner = agent_for(by_id[wrong[0]], sections).value
                self._record(
                    writer,
                    step,
                    "dispatch_specialist",
                    arguments,
                    None,
                    f"{wrong[0]} belongs to {owner}, not {agent.value}",
                )
                return StepResult()
            allowed = set(eligible)
            chosen = [q for q in args.question_ids if q in allowed]
            skipped = [q for q in args.question_ids if q not in allowed]

        job = JOB_FOR_LEVEL[args.level]
        tier = Tier(self.config.routing.jobs[job])
        payload: dict[str, Any] = {
            "agent": agent.value,
            "level": args.level,
            "question_ids": chosen if args.question_ids is None else list(args.question_ids),
            "selected_by_code": args.question_ids is None,
            "priority": args.priority,
            "skipped": skipped,
        }
        if not chosen:
            writer.emit(EventType.DISPATCH, payload | {"batches": 0})
            self._record(
                writer,
                step,
                "dispatch_specialist",
                arguments,
                {"summary": "all already answered; stored results used", "skipped": skipped},
            )
            return StepResult()

        to_run = [by_id[q] for q in chosen]
        keep_order = args.priority and args.question_ids is None
        groups = batches(to_run, sections, caps.specialist_batch_size[tier], keep_order=keep_order)
        ai_left = max(
            0,
            caps.ai_questions_per_run - sum(1 for q in questions if q.kind.value == "added_by_ai"),
        )
        # R13 as amended: every batch is prepared and priced from its request alone, then
        # admitted in batch order against the cap spent before this dispatch; each admitted
        # batch runs on its own slice, so no refusal depends on thread timing
        spend_limit = run.spend_cap_usd - reserve.usd
        before = writer.run.cap_spent_usd
        prepared = [
            prepare_batch(
                self.gateway,
                plant=self.plant,
                ref=self.ref,
                config=self.config,
                sections=sections,
                questions=group,
                agent=agent,
                ai_remaining=ai_left,
                level=args.level,
            )
            for group in groups
        ]
        slices = [
            0.0 if isinstance(p, BatchOutcome) else batch_slice_usd(p, self.config)
            for p in prepared
        ]
        admitted: list[int] = []
        # from the first batch that does not fit, the rest wait for a later dispatch: never
        # sent, so no repeat; never tried, so they keep their level (R13 as amended)
        deferred_at_admission: list[dict[str, Any]] = []
        running = before
        for index, slice_usd in enumerate(slices):
            if not deferred_at_admission and running + slice_usd <= spend_limit:
                admitted.append(index)
                running += slice_usd
            else:
                deferred_at_admission.append(
                    {"question_ids": [q.id for q in groups[index]], "slice_usd": slice_usd}
                )
        if groups and not admitted:
            # no room even for the first batch: the analysis ends here, and severity runs
            room = spend_limit - before
            writer.emit(
                EventType.DISPATCH,
                payload
                | {
                    "batches": len(groups),
                    "admission": {
                        "cap_spent_usd": before,
                        "limit_usd": spend_limit,
                        "slices_usd": slices,
                    },
                    "deferred_at_admission": deferred_at_admission,
                },
            )
            writer.emit(
                EventType.CAP_HIT,
                {
                    "reason": ADMISSION,
                    "detail": (
                        f"the first batch of the dispatch does not fit: slice "
                        f"${slices[0]:.4f}, room ${room:.4f} under the limit ${spend_limit:.4f}"
                    ),
                    "reserve_usd": reserve.usd,
                    "unrated": reserve.unrated,
                    "severity_calls": reserve.calls,
                },
            )
            self._record(
                writer,
                step,
                "dispatch_specialist",
                arguments,
                None,
                "no batch fits the spend left: the analysis ends",
            )
            return StepResult(next_step=NEXT)
        existing = set(by_id)
        made = frozenset(c.id for c in writer.model_calls())
        outcomes: list[BatchOutcome | BaseException] = []
        with ThreadPoolExecutor(max_workers=self.config.caps.concurrency[tier]) as pool:
            # in batch order: a batch too large to send is already a failed outcome
            pending: list[BatchOutcome | Future[BatchOutcome]] = []
            for index in admitted:
                ready = prepared[index]
                if isinstance(ready, BatchOutcome):
                    pending.append(ready)
                    continue
                pending.append(
                    pool.submit(
                        run_batch,
                        self.gateway,
                        plant=self.plant,
                        ref=self.ref,
                        config=self.config,
                        sections=sections,
                        questions=groups[index],
                        agent=agent,
                        budget=RunBudget(run.id, 0.0, slices[index], f"{step.id}/{index}"),
                        previous_step_id=step.id,
                        ai_remaining=ai_left,
                        existing_question_ids=existing,
                        level=args.level,
                        made=made,
                        prepared=ready,
                    )
                )
            for item in pending:
                if isinstance(item, BatchOutcome):
                    outcomes.append(item)
                    continue
                try:
                    outcomes.append(item.result())
                except BudgetRefused as refused:
                    outcomes.append(refused)

        refusal: BudgetRefused | None = None
        added_total = 0
        answered = failed = 0
        found = 0
        dropped: list[str] = []
        failed_batches = []
        answered_ids: list[str] = []
        for outcome in outcomes:
            if isinstance(outcome, BudgetRefused):
                refusal = refusal or outcome
                continue
            if isinstance(outcome, BaseException):
                raise outcome
            if args.level == "unsure":
                # an Ultra re-answer adds findings; the question keeps its status (R4)
                outcome.questions = []
            keep = max(0, ai_left - added_total)
            outcome.added = outcome.added[:keep]
            added_total += len(outcome.added)
            apply_batch(writer, outcome)
            dropped += list(outcome.dropped_ids)
            found += len(outcome.findings)
            if outcome.status == "answered":
                answered += len(outcome.question_ids)
                answered_ids += list(outcome.question_ids)
            else:
                failed += len(outcome.question_ids)
                failed_batches.append(
                    {
                        "question_ids": outcome.question_ids,
                        "status": "failed",
                        "reason": outcome.error,
                    }
                )
        # G15: first answers only; an unsure re-answer neither counts nor ends the count
        linked = linked_ids(writer.hypotheses())
        first_answers = args.level != "unsure"
        sent = [q.id for index in admitted for q in groups[index]]
        payload |= {
            "linked_answered": sum(1 for q in answered_ids if q in linked) if first_answers else 0,
            "unlinked_sent": sum(1 for q in sent if q not in linked) if first_answers else 0,
            "batches": len(groups),
            "dropped_ids": dropped,
            "failed_batches": failed_batches,
            "admission": {"cap_spent_usd": before, "limit_usd": spend_limit, "slices_usd": slices},
            "deferred_at_admission": deferred_at_admission,
        }
        writer.emit(EventType.DISPATCH, payload)
        lines, _ = coverage(list(sections.values()), writer.questions(), writer.findings())
        writer.emit(EventType.COVERAGE_UPDATED, {"lines": [line.model_dump() for line in lines]})
        summary = (
            f"{agent.value} at {args.level}: {answered} answered, {failed} failed, {found} findings"
        )
        if added_total:
            summary += f", {added_total} questions added"
        if deferred_at_admission:
            waiting = sum(len(d["question_ids"]) for d in deferred_at_admission)
            summary += f", {waiting} questions deferred for spend (still open)"
        self._record(
            writer,
            step,
            "dispatch_specialist",
            arguments,
            {
                "summary": summary,
                "question_ids": chosen,
                "skipped": skipped,
                "dropped_ids": dropped,
            },
        )
        if refusal is not None:
            return self._refused(writer, refusal, reserve)
        return StepResult()

    def _eligible(
        self,
        agent: Agent,
        level: str,
        questions: Sequence[Question],
        findings: Sequence[Any],
        sections: dict[str, Section],
        hypotheses: Sequence[Hypothesis] = (),
    ) -> list[str]:
        """R44 as amended after the case D dev run: bulk → open and not yet tried; hard → open
        with a failed attempt; unsure → answered with an unsure finding and no Ultra
        re-answer, within the cap. In ID order, or with `hypotheses` (a priority dispatch,
        spec 2b.3) the linked ones first. A tried question never goes back to bulk: the same
        batch again is a cache hit and can only fail again."""
        if level == "unsure":
            left = max(0, self.caps.unsure_reanswers_per_run - reanswers_used(findings))
            pool = set(unsure_question_ids(questions, findings))
            mine = by_agent([x for x in questions if x.id in pool], sections).get(agent, [])
            return prioritised(mine, hypotheses)[:left]
        wanted = [
            q
            for q in questions
            if q.status == QuestionStatus.OPEN and ((q.attempts == 0) == (level == "bulk"))
        ]
        return prioritised(by_agent(wanted, sections).get(agent, []), hypotheses)

    # --- records and refusals ---------------------------------------------------------------

    def _call(
        self, run: Run, writer: StepWriter, messages: list[dict[str, Any]], limit: float
    ) -> GatewayResult:
        result = self.gateway.call(
            job=JOB,
            prompt_version=self.prompt.label,
            messages=messages,
            tools=tool_schemas(),
            tool_choice="required",
            run=RunBudget(run.id, writer.run.cap_spent_usd, limit),
            made=frozenset(c.id for c in writer.model_calls()),
        )
        for call in result.model_calls:
            writer.add_model_call(call, fell_back_from=result.fell_back_from)
        writer.add_spent(result.cost_usd, cap_usd=result.cap_cost_usd)
        return result

    def _record(
        self,
        writer: StepWriter,
        step: AgentStep,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        refused: str | None = None,
    ) -> ToolCall:
        call = ToolCall(
            id=ids.tool_call_id(step.id, tool, arguments),
            run_id=step.run_id,
            agent_step_id=step.id,
            tool=tool,
            arguments=arguments,
            result=result,
            refused_reason=refused,
        )
        writer.add_tool_call(call)
        return call

    def _malformed(
        self,
        writer: StepWriter,
        step: AgentStep,
        tool: str,
        arguments: dict[str, Any],
        reason: str,
        earlier: Sequence[ToolCall],
    ) -> StepResult:
        self._record(writer, step, tool, arguments, None, reason)
        previous = _last_orchestrator_call(writer, earlier, step)
        if previous is not None and (previous.refused_reason or "").startswith(MALFORMED):
            log.warning(
                "orchestrator sent malformed arguments twice", extra={"context": {"reason": reason}}
            )
            return StepResult(status=RunStatus.FAILED)
        return StepResult()

    def _refused(
        self, writer: StepWriter, refused: BudgetRefused, reserve: SeverityReserve
    ) -> StepResult:
        if refused.status == RunStatus.STOPPED_CAP:
            # R38: the analysis phase stops at the run cap minus the reserve; severity runs next
            writer.emit(
                EventType.CAP_HIT,
                {
                    "reason": "severity reserve",
                    "detail": str(refused),
                    "reserve_usd": reserve.usd,
                    "unrated": reserve.unrated,
                    "severity_calls": reserve.calls,
                },
            )
            return StepResult(next_step=NEXT)
        return stop_for_refusal(writer, refused)


def _last_orchestrator_call(
    writer: StepWriter, earlier: Sequence[ToolCall], current: AgentStep
) -> ToolCall | None:
    orchestrator_steps = {
        s.id for s in writer.steps() if s.agent == Agent.ORCHESTRATOR and s.id != current.id
    }
    mine = [c for c in earlier if c.agent_step_id in orchestrator_steps]
    return mine[-1] if mine else None


def _agent_tool(name: str) -> AgentTool:
    try:
        return AgentTool(name)
    except ValueError:
        return AgentTool.CHECK_COVERAGE


def _parse(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {"_unparsed": text}
    return value if isinstance(value, dict) else {"_unparsed": text}


def _reactivity_summary(result: dict[str, Any]) -> str:
    codes = sorted({c["meaning"] for p in result.get("pairs", []) for c in p.get("codes", [])})
    names = " and ".join(c["id"] for c in result.get("chemicals", []))
    return f"{names}: {', '.join(codes) if codes else 'no listed hazard (not proof of safety)'}"
