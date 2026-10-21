"""The chain severity step (spec 3.1; plan PR 5, Q5, G3).

After the connector, the run's chains without a severity go to Ultra in their own batch (job
`chain_severity`, prompt `severity_chain/v1`; `severity/v2` is unchanged), with the same
severity classes and plant context as the finding severity step, and each link in words: a
finding link's cause, consequence and failing components; a fact link's ID and value. Each
chain's severity is filled once. A chain the answer leaves out, or a batch whose answer stays
invalid, is marked "not assessed" and gets no LOPA, listed "no severity" (G3). A cap refusal
stops the run.

A chain's initiating frequency is its first finding link's, and its tier its highest member
line's; both are code (`lopa/lines.py`), never this step.
"""

from collections import Counter
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.lopa.lines import cause_words
from guideword.ranking.severity import NOT_ASSESSED, severity_classes, severity_context
from guideword.reference import ReferenceSet
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.plants import plant_facts
from guideword.runs.post_budget import post_budget
from guideword.runs.store import StepWriter
from guideword.schema.enums import SeverityClass
from guideword.schema.plant import Plant
from guideword.schema.records import Chain, Finding, Run

JOB = "chain_severity"
PROMPT = "severity_chain"
NEXT = "lopa"
ASK = "Give the severity of every chain in the batch, in the required JSON schema."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChainSeverity(_Strict):
    chain_id: str
    severity_class: SeverityClass
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class ChainSeverityAnswer(_Strict):
    severities: list[ChainSeverity]


def _done(chain: Chain) -> bool:
    return chain.severity_class is not None or chain.severity_reason is not None


def chain_severity_messages(
    prompt: Prompt,
    chains: list[Chain],
    findings: dict[str, Finding],
    facts: dict[str, Any],
    ref: ReferenceSet,
    plant: Plant,
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}

    def link_words(link: str) -> dict[str, Any]:
        found = findings.get(link)
        if found is not None:
            return {
                "finding_id": link,
                "cause": cause_words(found, causes),
                "consequence": found.consequence,
                "failing_component_ids": list(found.failing_component_ids),
            }
        return {"fact_id": link, "value": facts.get(link)}

    batch = [
        {
            "chain_id": c.id,
            "description": c.description,
            "links": [link_words(link) for link in c.links],
        }
        for c in chains
    ]
    system = render(
        prompt.body,
        {
            # as data: the connector's and specialists' words cannot close a block
            "severity_classes": as_data(severity_classes(ref)),
            "chains": as_data(batch, default=str),
            "context": as_data(severity_context(plant), default=str),
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]


class ChainSeverityStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(PROMPT, config)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        todo = [c for c in writer.chains() if not _done(c)]
        if not todo:
            return StepResult(next_step=NEXT)
        wanted = {c.id for c in todo}

        def validator(value: Any) -> None:
            if not isinstance(value, ChainSeverityAnswer):
                raise ValueError("not a chain severity answer")
            counts = Counter(s.chain_id for s in value.severities)
            for chain_id, n in counts.items():
                if chain_id not in wanted:
                    raise ValueError(f"{chain_id} is not in this batch")
                if n > 1:
                    raise ValueError(f"{chain_id} is rated more than once")

        findings = {f.id: f for f in writer.findings()}
        facts = {f.id: f.value for f in plant_facts(self.plant, run.plant_record_id)}
        messages = chain_severity_messages(self.prompt, todo, findings, facts, self.ref, self.plant)
        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=messages,
                schema=ChainSeverityAnswer,
                validator=validator,
                run=post_budget(writer),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused, cap=POST_CAP)
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": sorted(wanted)}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_post_spent(result.cost_usd)
        rated: dict[str, ChainSeverity] = {}
        if result.outcome == "ok" and isinstance(result.value, ChainSeverityAnswer):
            rated = {s.chain_id: s for s in result.value.severities}
        for chain in todo:
            given = rated.get(chain.id)
            update: dict[str, Any]
            if given is not None:
                update = {"severity_class": given.severity_class, "severity_reason": given.reason}
            else:
                why = (
                    result.error or result.outcome
                    if not rated
                    else "left out of the chain severity answer"
                )
                update = {"severity_reason": f"{NOT_ASSESSED}: {why}"[:300]}
            writer.fill_chain_severity(chain.model_copy(update=update))
        return StepResult(next_step=NEXT)
