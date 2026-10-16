"""The whole-plant pass as the run's first step (spec 2b.1; R50).

One Ultra call (job `plant_screen`) reads the plant record as data, the causes the plant can
support and the question kinds, and proposes ranked hypotheses. Every problem goes back with
the one retry; after it, the final answer is read again and only the hypotheses with a problem
are dropped (Q6), each with a `hypothesis_dropped` event. The survivors are stored once, with
their question links (2b.2), and the run moves on to the analysis. With none left, the run
goes on without hypotheses. A cap refusal stops the run like any other.
"""

import json
from typing import Any

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.gateway.prompts import as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.store import StepWriter
from guideword.schema.enums import EventType
from guideword.schema.plant import Plant
from guideword.schema.records import Hypothesis, Run
from guideword.screen.link import question_links
from guideword.screen.schema import (
    ScreenAnswer,
    ScreenHypothesis,
    answer_problems,
    every_problem,
    hypothesis_problem,
    parse_answer,
    plant_for_screen,
    question_kinds,
    screen_causes,
)

JOB = "plant_screen"
NEXT = "analysis"
ASK = "Name the hazards to put in front of the HAZOP team first, in the required JSON schema."

log = get_logger(__name__)


class PlantScreenStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(JOB, config)
        self.max_hypotheses = config.caps.run.plant_screen_max_hypotheses

    def messages(self, kinds: list[str]) -> list[dict[str, Any]]:
        system = render(
            self.prompt.body,
            {
                # as data: a note cannot close the <plant> block (CLAUDE.md §3)
                "plant": as_data(plant_for_screen(self.plant)),
                "causes": json.dumps(screen_causes(self.plant, self.ref), indent=1),
                "question_kinds": question_kinds(kinds),
                "max_hypotheses": str(self.max_hypotheses),
            },
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        questions = writer.questions()

        def validator(value: Any) -> None:
            problems = every_problem(value, self.plant, self.ref, self.max_hypotheses)
            if problems:
                raise ValueError("; ".join(problems))

        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=self.messages([q.kind.value for q in questions]),
                schema=ScreenAnswer,
                validator=validator,
                run=RunBudget(run.id, writer.run.cap_spent_usd, run.spend_cap_usd),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        for call in result.model_calls:
            writer.add_model_call(call, fell_back_from=result.fell_back_from)
        writer.add_spent(result.cost_usd, cap_usd=result.cap_cost_usd)
        call_id = result.model_calls[-1].id if result.model_calls else None

        kept: list[ScreenHypothesis] = []
        if result.outcome == "ok" and isinstance(result.value, ScreenAnswer):
            kept = list(result.value.hypotheses)
        elif result.outcome == "invalid":
            answer = parse_answer(result.content)
            if answer is None or answer_problems(answer, self.max_hypotheses):
                why = "; ".join(answer_problems(answer, self.max_hypotheses)) if answer else ""
                writer.emit(
                    EventType.HYPOTHESIS_DROPPED,
                    {"rank": None, "reason": f"the answer was invalid: {why or result.error}"},
                )
            else:
                for h in answer.hypotheses:
                    problem = hypothesis_problem(h, self.plant, self.ref)
                    if problem is None:
                        kept.append(h)
                    else:
                        writer.emit(
                            EventType.HYPOTHESIS_DROPPED, {"rank": h.rank, "reason": problem}
                        )
        else:
            writer.emit(
                EventType.HYPOTHESIS_DROPPED,
                {"rank": None, "reason": f"no usable answer: {result.error or result.outcome}"},
            )

        sections = writer.sections()
        for h in kept:
            writer.add_hypothesis(
                Hypothesis(
                    id=h.hypothesis_id,
                    run_id=run.id,
                    rank=h.rank,
                    mechanism=h.mechanism,
                    component_ids=h.component_ids,
                    chemical_ids=h.chemical_ids,
                    failing_component_type=h.failing_component_type,
                    cause_id=h.cause_id,
                    cause_text=h.cause_text,
                    consequence=h.consequence,
                    reason=h.reason,
                    question_ids=question_links(
                        h.component_ids,
                        h.chemical_ids,
                        h.failing_component_type,
                        self.plant,
                        sections,
                        questions,
                    ),
                    model_call_id=call_id,
                )
            )
        if not kept:
            log.warning(
                "the whole-plant pass gave no hypotheses", extra={"context": {"run_id": run.id}}
            )
        return StepResult(next_step=NEXT)
