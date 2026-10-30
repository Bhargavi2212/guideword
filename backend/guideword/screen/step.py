"""The whole-plant pass as the run's first step (spec 2b.1; R50).

One Ultra call (job `plant_screen`) reads the plant record as data, the causes the plant can
support and the question kinds, and proposes ranked hypotheses. Every problem goes back with
the one retry. After it, code keeps the attempt with more hypotheses that pass every check
(a tie keeps the first; an attempt invalid as a whole is never kept) and drops only that
attempt's hypotheses with a problem (Q6 as amended, R50 review), each with a
`hypothesis_dropped` event. The survivors are stored once, with
their question links (2b.2), and the run moves on to the analysis. With none left, the run
goes on without hypotheses. A cap refusal stops the run like any other.

Phase 9 (spec 9.1): the prompt version and the hypothesis limit are the run's own, stored when
it started (`prompt_versions`, `caps`), so a stored run replays on the prompt it ran on and a
new run takes the routing's. From `plant_screen/v4` each hypothesis is a card (`requires_card`).
"""

from typing import Any

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, GatewayResult, RunBudget
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, record_attempts, stop_for_refusal
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
    fitting,
    hypothesis_problem,
    parse_answer,
    plant_for_screen,
    question_kinds,
    requires_card,
    screen_causes,
)

JOB = "plant_screen"
NEXT = "analysis"
ASK = "Name the hazards to put in front of the HAZOP team first, in the required JSON schema."
MAX_SETTING = "plant_screen_max_hypotheses"

log = get_logger(__name__)


class PlantNotSent(RuntimeError):
    """The rendered request does not carry the whole plant: a code bug, never sent."""


def check_plant_sent(messages: list[dict[str, Any]], plant: Plant) -> None:
    """Guard (R50 review): one <plant> block holding every equipment and line ID, before any
    paid call."""
    system = str(messages[0]["content"])
    if system.count("<plant>") != 1 or system.count("</plant>") != 1:
        raise PlantNotSent("the request has no single <plant> block")
    block = system.split("<plant>")[1].split("</plant>")[0]
    missing = [
        i for i in [e.id for e in plant.equipment] + [x.id for x in plant.lines] if i not in block
    ]
    if missing:
        raise PlantNotSent(f"the <plant> block lacks {len(missing)} IDs: {', '.join(missing[:5])}")


def screen_prompt(run: Run, config: Config) -> Prompt:
    """The prompt the run started on, else the routing's (Phase 9: a replay reads its own)."""
    return load_prompt(JOB, config, version=run.prompt_versions.get(JOB))


def max_hypotheses_of(run: Run, config: Config) -> int:
    """The hypothesis limit the run started with (hashed into its ID), else the routing's."""
    stored = run.caps.get(MAX_SETTING)
    return int(stored) if stored is not None else config.caps.run.plant_screen_max_hypotheses


class PlantScreenStepper:
    def __init__(
        self,
        gateway: Gateway,
        *,
        config: Config,
        ref: ReferenceSet,
        plant: Plant,
        prompt: Prompt | None = None,
        preamble: str | None = None,
    ) -> None:
        """`prompt` and `preamble` are for diagnostics only (scripts/screen_check.py): another
        prompt file, and a first line in place of the run's request marker."""
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt_given = prompt
        self.prompt = prompt if prompt is not None else load_prompt(JOB, config)
        self.preamble = preamble
        self.max_hypotheses = config.caps.run.plant_screen_max_hypotheses
        self.min_valid = config.caps.run.plant_screen_min_valid
        self.card_required = requires_card(self.prompt.version)
        self.reasked = False
        # every parsed attempt of the last call, and which was kept (for scripts/screen_check)
        self.attempts: list[ScreenAnswer] = []
        self.kept_attempt: int | None = None

    def messages(self, kinds: list[str], marker: str | None = None) -> list[dict[str, Any]]:
        """`marker` is the system message's first line (the run's request marker)."""
        system = render(
            self.prompt.body,
            {
                # as data: a note cannot close the <plant> block (CLAUDE.md §3)
                "plant": as_data(plant_for_screen(self.plant)),
                "causes": as_data(screen_causes(self.plant, self.ref)),
                # the same list the misfit check reads (plant_screen v2)
                "can_fail_as": as_data(fitting(self.plant)),
                "question_kinds": question_kinds(kinds),
                "max_hypotheses": str(self.max_hypotheses),
            },
        )
        if marker is not None:
            system = f"{marker}\n\n{system}"
        return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]

    def _settle(self, run: Run) -> None:
        """The run's own prompt version and limit (Phase 9), unless a diagnostic prompt is set."""
        if self.prompt_given is None:
            self.prompt = screen_prompt(run, self.config)
        self.max_hypotheses = max_hypotheses_of(run, self.config)
        self.card_required = requires_card(self.prompt.version)

    def _problem(self, h: ScreenHypothesis) -> str | None:
        return hypothesis_problem(h, self.plant, self.ref, card_required=self.card_required)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        """One ask; with fewer than `plant_screen_min_valid` valid hypotheses, one fresh re-ask
        (a new conversation with its own marker, so neither cache can replay the first answer);
        then the attempt with the most valid hypotheses is kept (R50 review)."""
        self._settle(run)
        questions = writer.questions()
        kinds = [q.kind.value for q in questions]
        self.attempts, self.kept_attempt, self.reasked = [], None, False
        # the first line, so no provider cache reuses a prefix from another run's request; the
        # run ID without its attempt number, so a re-run of the same inputs is served from our
        # own cache with no provider call (scripts/screen_check.py --nonce replaces it)
        base = ":".join(run.id.split(":")[:2])
        marker = self.preamble if self.preamble is not None else f"Request marker: {base}"
        call_of: list[str | None] = []
        try:
            result = self._ask(run, writer, kinds, marker, call_of)
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        notes: list[str] = []
        if self._valid(self._best_attempt()) < self.min_valid:
            self.reasked = True
            try:
                result = self._ask(run, writer, kinds, f"{marker}:reask", call_of)
            except BudgetRefused as refused:
                record_attempts(writer, refused)
                notes.append("screen degenerate: re-ask refused at cap")
        chosen = self._best_attempt()

        kept: list[ScreenHypothesis] = []
        if chosen is not None:
            for h in self.attempts[chosen].hypotheses:
                problem = self._problem(h)
                if problem is None:
                    kept.append(h)
                else:
                    writer.emit(EventType.HYPOTHESIS_DROPPED, {"rank": h.rank, "reason": problem})
        elif result.outcome == "invalid":
            answer = parse_answer(result.content)
            why = "; ".join(answer_problems(answer, self.max_hypotheses)) if answer else ""
            writer.emit(
                EventType.HYPOTHESIS_DROPPED,
                {"rank": None, "reason": f"the answer was invalid: {why or result.error}"},
            )
        else:
            writer.emit(
                EventType.HYPOTHESIS_DROPPED,
                {"rank": None, "reason": f"no usable answer: {result.error or result.outcome}"},
            )
        if self.reasked and not notes and len(kept) < self.min_valid:
            notes.append(
                f"screen degraded: {len(kept)} kept"
                if kept
                else "screen degenerate: no valid hypothesis"
            )
        for note in notes:
            writer.emit(EventType.HYPOTHESIS_DROPPED, {"rank": None, "reason": note})

        sections = writer.sections()
        call_id = call_of[chosen] if chosen is not None else None
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
                    initiating_event=h.initiating_event,
                    enabling_condition=h.enabling_condition,
                    propagation=h.propagation,
                    consequence_magnitude=h.consequence_magnitude,
                    operating_mode=h.operating_mode,
                    mechanism_class=h.mechanism_class,
                    fact_ids=list(h.fact_ids),
                )
            )
        if chosen is not None and len(self.attempts) > 1:
            log.info(
                "plant_screen attempt kept",
                extra={"context": {"run_id": run.id, "attempt": chosen + 1}},
            )
        if not kept:
            log.warning(
                "the whole-plant pass gave no hypotheses", extra={"context": {"run_id": run.id}}
            )
        return StepResult(next_step=NEXT)

    def _ask(
        self,
        run: Run,
        writer: StepWriter,
        kinds: list[str],
        marker: str,
        call_of: list[str | None],
    ) -> GatewayResult:
        """One gateway call (with its one validation retry); every parsed attempt is kept in
        `self.attempts`, with the call that made it in `call_of`. Raises BudgetRefused."""
        before = len(self.attempts)

        def validator(value: Any) -> None:
            if isinstance(value, ScreenAnswer):
                self.attempts.append(value)
            problems = every_problem(
                value,
                self.plant,
                self.ref,
                self.max_hypotheses,
                card_required=self.card_required,
            )
            if problems:
                raise ValueError("; ".join(problems))

        messages = self.messages(kinds, marker)
        check_plant_sent(messages, self.plant)
        result = self.gateway.call(
            job=JOB,
            prompt_version=self.prompt.label,
            messages=messages,
            schema=ScreenAnswer,
            validator=validator,
            run=RunBudget(run.id, writer.run.cap_spent_usd, run.spend_cap_usd),
            made=frozenset(c.id for c in writer.model_calls()),
        )
        for call in result.model_calls:
            writer.add_model_call(call, fell_back_from=result.fell_back_from)
        writer.add_spent(result.cost_usd, cap_usd=result.cap_cost_usd)
        last = result.model_calls[-1].id if result.model_calls else None
        call_of.extend([last] * (len(self.attempts) - before))
        return result

    def _valid(self, index: int | None) -> int:
        if index is None:
            return 0
        return sum(1 for h in self.attempts[index].hypotheses if self._problem(h) is None)

    def _best_attempt(self) -> int | None:
        """The attempt with more hypotheses passing every check; a tie keeps the earlier one.
        Code chooses between two model answers; it never edits either (Q6 as amended)."""
        best: int | None = None
        best_count = -1
        for index, answer in enumerate(self.attempts):
            if answer_problems(answer, self.max_hypotheses):
                continue
            count = sum(1 for h in answer.hypotheses if self._problem(h) is None)
            if count > best_count:
                best, best_count = index, count
        self.kept_attempt = best
        return best
