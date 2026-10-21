"""The LOPA step (spec 3.2; plan PR 5, Q9, Q10, G3, G19).

Which lines get full, code-only or no LOPA is `lopa/lines.py` `lopa_plan`. Each `advance`:

1. writes, with no call, every full-LOPA line that has nothing for Ultra to argue (no
   candidate layer), and skips every line that gets no record (no severity, no likelihood:
   it stays on the shortlist with its reason);
2. sends one batch of `lopa_batch_size` full-LOPA lines to Ultra (job `lopa_argument`, prompt
   `lopa_argument/v1`): per line its scenario in words and the candidate layers code listed,
   each with its `protection_layers.csv` row's `layer`, `scenarios` and `conditions_text`,
   never its PFD (G19). Ultra says, per layer, whether it applies, with a reason; code decides
   credit (`credit.py`) and every number (`engine.py`). A layer the answer leaves out is "not
   argued — no credit". A batch whose call fails gets code-only LOPA, flagged (G3);
3. when no full line is left, writes the code-only records (no call) and moves on.

Every record is written once, with a `lopa_done` event. A cap refusal stops the run.
"""

from collections import Counter
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.lopa.candidates import Layer, Scenario, candidates
from guideword.lopa.credit import LayerArgument
from guideword.lopa.engine import NoLopa, lopa_record
from guideword.lopa.lines import (
    CODE_ONLY,
    FULL,
    Planned,
    cause_words,
    display_lines,
    lopa_plan,
    section_for,
)
from guideword.reference import ReferenceSet
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.post_budget import post_budget, post_setting
from guideword.runs.store import StepWriter
from guideword.schema.plant import Plant, ReliefDevice
from guideword.schema.records import LopaRecord, Run

JOB = "lopa_argument"
PROMPT = "lopa_argument"
NEXT = "recommendations"
ASK = "Judge every listed layer of every line, in the required JSON schema."
ARGUMENT_FAILED_FLAG = "argument call failed"
LEFT_OUT_FLAG = "left out of the argument answer: layers not argued"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayerJudgment(_Strict):
    layer_id: str
    applies: bool
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class LineJudgment(_Strict):
    target_id: str
    layers: list[LayerJudgment]


class LopaArgumentAnswer(_Strict):
    lines: list[LineJudgment]


def layer_view(layer: Layer, ref: ReferenceSet) -> dict[str, Any]:
    """What Ultra sees of a candidate layer: never its PFD (G19)."""
    if isinstance(layer, ReliefDevice):
        row = next((r for r in ref.protection_layers if r.relief_kind == layer.kind), None)
        view: dict[str, Any] = {
            "layer_id": layer.id,
            "kind": "relief_device",
            "relief_kind": layer.kind.value if layer.kind else None,
            "protects_id": layer.protects_id,
        }
    else:
        row = next((r for r in ref.protection_layers if r.id == layer.layer_type), None)
        view = {
            "layer_id": layer.id,
            "kind": "safeguard",
            "description": layer.description,
            "protects_id": layer.protects_id,
        }
    view["row"] = (
        {
            "layer": row.layer,
            "scenarios": list(row.scenarios),
            "conditions_text": row.conditions_text,
        }
        if row is not None
        else None
    )
    return view


def scenario_words(planned: Planned, ref: ReferenceSet, section_id: str | None) -> dict[str, Any]:
    if planned.chain is not None:
        return {"description": planned.chain.description, "links": list(planned.chain.links)}
    assert planned.scenario is not None
    lead = planned.scenario.finding
    return {
        "cause": cause_words(lead, {c.id: c.cause for c in ref.causes}),
        "consequence": lead.consequence,
        "failing_component_ids": list(lead.failing_component_ids),
        "section_id": section_id,
    }


def lopa_messages(prompt: Prompt, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # as data: plant text, the specialists' words and table text cannot close the block
    system = render(prompt.body, {"lines": as_data(lines)})
    return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]


class LopaStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(PROMPT, config)

    def _record(
        self,
        scenario: Scenario,
        run: Run,
        arguments: dict[str, LayerArgument] | None,
        model_call_id: str | None = None,
    ) -> LopaRecord | NoLopa:
        return lopa_record(
            scenario,
            run_id=run.id,
            plant=self.plant,
            ref=self.ref,
            caps=self.config.caps,
            arguments=arguments,
            model_call_id=model_call_id,
        )

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        findings = writer.findings()
        questions = writer.questions()
        sections = writer.sections()
        lines = display_lines(
            findings,
            writer.hypotheses(),
            questions,
            sections,
            self.plant,
            self.ref,
            self.config.caps,
        )
        plan = lopa_plan(
            lines,
            writer.chains(),
            findings,
            questions,
            sections,
            top_n=post_setting(writer.run, self.config, "lopa_top_n"),
        )
        stored = {r.target_id for r in writer.lopa_records()}
        to_argue: list[Planned] = []
        for planned in plan:
            if planned.kind != FULL or planned.target_id in stored or planned.scenario is None:
                continue
            if isinstance(self._record(planned.scenario, run, None), NoLopa):
                continue  # no record; the shortlist lists it with its reason
            if candidates(planned.scenario, self.plant):
                to_argue.append(planned)
                continue
            # nothing for Ultra to argue: the full record has no layers
            found = self._record(planned.scenario, run, {})
            if isinstance(found, LopaRecord):
                writer.add_lopa(found, full=True)
        if to_argue:
            return self._argue(
                run,
                writer,
                to_argue[: post_setting(writer.run, self.config, "lopa_batch_size")],
                questions,
                sections,
            )
        for planned in plan:
            if planned.kind != CODE_ONLY or planned.target_id in stored or planned.scenario is None:
                continue
            found = self._record(planned.scenario, run, None)
            if isinstance(found, LopaRecord):
                writer.add_lopa(found, full=False)
        return StepResult(next_step=NEXT)

    def _argue(
        self,
        run: Run,
        writer: StepWriter,
        batch: list[Planned],
        questions: list[Any],
        sections: list[Any],
    ) -> StepResult:
        by_question = {q.id: q for q in questions}
        by_section = {s.id: s for s in sections}
        listed: dict[str, set[str]] = {}
        payload: list[dict[str, Any]] = []
        for planned in batch:
            assert planned.scenario is not None
            layers = candidates(planned.scenario, self.plant)
            listed[planned.target_id] = {layer.id for layer in layers}
            section = (
                section_for(planned.scenario.finding, by_question, by_section)
                if planned.chain is None
                else None
            )
            payload.append(
                {
                    "target_id": planned.target_id,
                    "scenario": scenario_words(planned, self.ref, section.id if section else None),
                    "layers": [layer_view(layer, self.ref) for layer in layers],
                }
            )

        def validator(value: Any) -> None:
            if not isinstance(value, LopaArgumentAnswer):
                raise ValueError("not a LOPA argument answer")
            targets = Counter(line.target_id for line in value.lines)
            for target_id, n in targets.items():
                if target_id not in listed:
                    raise ValueError(f"{target_id} is not in this batch")
                if n > 1:
                    raise ValueError(f"{target_id} appears more than once")
            for line in value.lines:
                layers = Counter(j.layer_id for j in line.layers)
                for layer_id, n in layers.items():
                    if layer_id not in listed[line.target_id]:
                        raise ValueError(f"{layer_id} is not listed for {line.target_id}")
                    if n > 1:
                        raise ValueError(f"{layer_id} is judged more than once")

        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=lopa_messages(self.prompt, payload),
                schema=LopaArgumentAnswer,
                validator=validator,
                run=post_budget(writer),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused, cap=POST_CAP)
        targets = [p.target_id for p in batch]
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": targets}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_post_spent(result.cost_usd)
        call_id = result.model_calls[-1].id if result.model_calls else None
        answered: dict[str, LineJudgment] | None = None
        if result.outcome == "ok" and isinstance(result.value, LopaArgumentAnswer):
            answered = {line.target_id: line for line in result.value.lines}
        for planned in batch:
            assert planned.scenario is not None
            if answered is None:
                found = self._record(planned.scenario, run, None)
                if isinstance(found, LopaRecord):
                    why = f"{ARGUMENT_FAILED_FLAG} ({call_id}): {result.error or result.outcome}"
                    writer.add_lopa(
                        found.model_copy(update={"flags": [*found.flags, why[:300]]}), full=False
                    )
                continue
            line = answered.get(planned.target_id)
            arguments = (
                {j.layer_id: LayerArgument(j.applies, j.reason) for j in line.layers}
                if line is not None
                else {}
            )
            found = self._record(planned.scenario, run, arguments, call_id)
            if isinstance(found, LopaRecord):
                if line is None:
                    found = found.model_copy(update={"flags": [*found.flags, LEFT_OUT_FLAG]})
                writer.add_lopa(found, full=True)
        return StepResult()
