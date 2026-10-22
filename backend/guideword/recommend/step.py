"""The recommendations step (spec 3.4; plan PR 5, Q12, G3, G17).

Every shortlist line with a complete LOPA record and a gap above 1, full or code-only, is
eligible (Q12, G17). Each `advance` sends the next `recommendation_batch_size` eligible lines,
in shortlist order, to Ultra (job `recommendation`, prompt `recommendation/v1`): per line its
scenario in words, its severity class, each layer considered with code's credit reason, and
the gap as an order of magnitude in words. Ultra proposes one action per line, with a reason;
no number comes from the model. The ID is `rec:<target>:<h(normalised action)>`.

A line sent once is never sent again: the call's record lists the lines it was about. A line
the answer leaves out, or a batch whose call fails, gets no recommendation and is flagged on
the shortlist (G3). A cap refusal stops the run with what was done kept; batches go in
shortlist order, so the lowest lines are the ones lost.
"""

import math
from collections import Counter
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.chains.words import chain_words, count_text, handles_for, line_words
from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.lopa.lines import (
    ShortlistLine,
    display_lines,
    lopa_plan,
    section_for,
    shortlist,
    writer_lead_rule,
)
from guideword.reference import ReferenceSet
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.plants import plant_facts
from guideword.runs.post_budget import post_budget, post_setting
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.plant import Plant
from guideword.schema.records import Recommendation, Run

JOB = "recommendation"
PROMPT = "recommendation"
# Phase 4: the evidence step comes after the recommendations
NEXT = "evidence"
# target-handles plan (approved 2026-10-21): targets by handle, L<n> or C<n>; no ID shown

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecommendationItem(_Strict):
    # a handle, L<n> or C<n>, mapped back to its target by code
    target: str
    action: Text300
    reason: Text300


class RecommendationAnswer(_Strict):
    recommendations: list[RecommendationItem]


def gap_words(gap: float) -> str:
    """The gap as an order of magnitude, in words; code's number, never the model's."""
    power = round(math.log10(gap))
    if power < 1:
        return "the mitigated frequency is above the tolerable frequency, by less than 10 times"
    return f"the mitigated frequency is about {10**power:,} times the tolerable frequency"


def current_shortlist(
    writer: StepWriter, plant: Plant, ref: ReferenceSet, config: Config
) -> list[ShortlistLine]:
    findings = writer.findings()
    questions = writer.questions()
    sections = writer.sections()
    lines = display_lines(
        findings,
        writer.hypotheses(),
        questions,
        sections,
        plant,
        ref,
        config.caps,
        prefer_own_section=writer_lead_rule(writer),
    )
    plan = lopa_plan(
        lines,
        writer.chains(),
        findings,
        questions,
        sections,
        top_n=post_setting(writer.run, config, "lopa_top_n"),
    )
    return shortlist(
        plan,
        writer.lopa_records(),
        writer.recommendations(),
        writer.model_calls(),
        run_id=writer.run.id,
        plant=plant,
        ref=ref,
        caps=config.caps,
    )


class RecommendationStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(PROMPT, config)

    def _line(self, item: ShortlistLine, writer: StepWriter, handle: str) -> dict[str, Any]:
        record = item.lopa
        assert record is not None and record.gap is not None
        planned = item.planned
        layers = {g.id: g.description for g in self.plant.safeguards}
        causes = {c.id: c.cause for c in self.ref.causes}
        if planned.chain is not None:
            findings = {f.id: f for f in writer.findings()}
            facts = {f.id: f.value for f in plant_facts(self.plant, writer.run.plant_record_id)}
            scenario = chain_words(planned.chain, findings, facts, causes)
        else:
            assert planned.scenario is not None
            lead = planned.scenario.finding
            section = section_for(
                lead,
                {q.id: q for q in writer.questions()},
                {s.id: s for s in writer.sections()},
            )
            scenario = line_words(lead, causes, section.id if section else None)
        return {
            "handle": handle,
            "scenario": scenario,
            "severity_class": record.severity_class.value,
            "layers": [
                {
                    "layer_id": layer.layer_id,
                    "description": layers.get(layer.layer_id),
                    "credited": layer.credited,
                    "reason": layer.reason,
                }
                for layer in record.layers
            ],
            "gap": gap_words(record.gap),
        }

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        attempted = {
            target for c in writer.model_calls() if c.job == JOB for target in c.record_ids
        }
        todo = [
            item
            for item in current_shortlist(writer, self.plant, self.ref, self.config)
            if item.eligible and not item.recommendations and item.target_id not in attempted
        ]
        if not todo:
            return StepResult(next_step=NEXT)
        batch = todo[: post_setting(writer.run, self.config, "recommendation_batch_size")]
        wanted = [item.target_id for item in batch]
        handles = handles_for([item.planned.chain is not None for item in batch])
        target_of = dict(zip(handles, wanted, strict=True))

        def validator(value: Any) -> None:
            if not isinstance(value, RecommendationAnswer):
                raise ValueError("not a recommendation answer")
            for handle, n in Counter(r.target for r in value.recommendations).items():
                if n > 1:
                    raise ValueError(f"{handle} has more than one recommendation")

        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=recommendation_messages(
                    self.prompt,
                    [
                        self._line(item, writer, handle)
                        for handle, item in zip(handles, batch, strict=True)
                    ],
                ),
                schema=RecommendationAnswer,
                validator=validator,
                run=post_budget(writer),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused, cap=POST_CAP)
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": wanted}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_post_spent(result.cost_usd)
        call_id = result.model_calls[-1].id if result.model_calls else None
        if result.outcome == "ok" and isinstance(result.value, RecommendationAnswer):
            # an unknown handle is dropped; each known one maps back to its target exactly
            by_target = {
                target_of[r.target]: r
                for r in result.value.recommendations
                if r.target in target_of
            }
            for target_id in wanted:
                given = by_target.get(target_id)
                if given is None:
                    continue
                writer.add_recommendation(
                    Recommendation(
                        id=ids.recommendation_id(target_id, given.action),
                        run_id=run.id,
                        target_id=target_id,
                        action=given.action,
                        reason=given.reason,
                        model_call_id=call_id,
                    )
                )
        return StepResult()


def ask(handles: list[str]) -> str:
    return (
        f"Propose one action for each of the {len(handles)} targets ({', '.join(handles)}), "
        "in the required JSON schema."
    )


def recommendation_messages(prompt: Prompt, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    handles = [line["handle"] for line in lines]
    # as data: the specialists' words and code's reasons cannot close the block
    counted = count_text(handles)
    system = render(
        prompt.body,
        {
            "lines": as_data(lines, default=str),
            "count": counted["count"],
            "handles": counted["handles"],
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": ask(handles)}]
