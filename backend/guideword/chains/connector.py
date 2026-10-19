"""The chains step: the connector (spec 3.1; PROJECT.md §5 Step 5; plan PR 5, Q6, Q7, G3, G7).

One Ultra call (job `connector`, prompt `connector/v1`) reads one line per scenario (R48) in
R50 tier order, the plant record as the whole-plant pass sees it (G17) and the plant's fact
IDs (G7), all as data, and proposes at most `connector_max_chains` chains. The scenario lines
are cut, from the bottom, until the request fits `connector_max_input_tokens` by the agreed
estimate; how many were left out is logged and kept in the step's summary.

Code checks every chain: at least two links, none repeated; every link exactly a finding ID
of this run or a fact ID of the plant; at least one a finding. Any other chain is rejected,
logged with its reason and listed in the step's summary. A chain needing more than two
independent failures (more than two groups of finding links whose failing components do not
overlap) is flagged, never filtered (Q6). Misused terms are not checked by code; the engineer
reads the description. The links keep the model's order: the first finding link is the cause
(Q7); the ID sorts them.

A call that fails (invalid twice, cut off, an error) leaves the run going with no chains,
logged (G3); only a cap refusal stops the run.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.lopa.lines import cause_words, display_lines, section_for
from guideword.reference import ReferenceSet
from guideword.runs.machine import StepResult, stop_for_refusal
from guideword.runs.plants import plant_facts
from guideword.runs.post_budget import post_budget, post_setting
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import Tier
from guideword.schema.plant import Plant
from guideword.schema.records import Chain, Finding, Run
from guideword.screen.schema import plant_for_screen

JOB = "connector"
PROMPT = "connector"
NEXT = "chain_severity"
ASK = "Name the chains, in the required JSON schema."
MORE_THAN_TWO_FLAG = "possibly more than two independent failures"

log = get_logger(__name__)

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorChain(_Strict):
    links: list[str]
    description: Text300
    reason: Text300


class ConnectorAnswer(_Strict):
    chains: list[ConnectorChain]


def chain_problem(
    links: Sequence[str], finding_ids: Collection[str], fact_ids: Collection[str]
) -> str | None:
    """Why code rejects this chain, or None (spec 3.1, G7: a fact link must be exact)."""
    if len(links) < 2:
        return "fewer than two links"
    repeated = sorted({link for link in links if list(links).count(link) > 1})
    if repeated:
        return f"link repeated: {', '.join(repeated)}"
    unknown = [link for link in links if link not in finding_ids and link not in fact_ids]
    if unknown:
        return f"not a finding ID or plant fact ID: {', '.join(unknown)}"
    if not any(link in finding_ids for link in links):
        return "no link is a finding"
    return None


def chain_flags(links: Sequence[str], findings: Mapping[str, Finding]) -> list[str]:
    """Q6: finding links grouped by overlapping failing components; more than two groups is
    flagged "possibly more than two independent failures"."""
    groups: list[set[str]] = []
    for link in links:
        found = findings.get(link)
        if found is None:
            continue
        components = set(found.failing_component_ids)
        touching = [g for g in groups if g & components]
        merged = components.union(*touching)
        groups = [g for g in groups if not g & components] + [merged]
    return [MORE_THAN_TWO_FLAG] if len(groups) > 2 else []


def scenario_lines(
    writer: StepWriter, plant: Plant, ref: ReferenceSet, config: Config
) -> list[dict[str, Any]]:
    """One line per scenario with a lead finding, in R50 tier order (no repeats)."""
    findings = writer.findings()
    questions = writer.questions()
    sections = writer.sections()
    lines = display_lines(
        findings, writer.hypotheses(), questions, sections, plant, ref, config.caps
    )
    causes = {c.id: c.cause for c in ref.causes}
    by_question = {q.id: q for q in questions}
    by_section = {s.id: s for s in sections}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        if line.lead is None or line.lead.finding.id in seen:
            continue
        lead = line.lead.finding
        seen.add(lead.id)
        section = section_for(lead, by_question, by_section)
        out.append(
            {
                "finding_id": lead.id,
                "cause": cause_words(lead, causes),
                "consequence": lead.consequence,
                "failing_component_ids": list(lead.failing_component_ids),
                "section_id": section.id if section else None,
                "severity_class": lead.severity_class.value if lead.severity_class else None,
            }
        )
    return out


def connector_messages(
    prompt: Prompt,
    scenarios: list[dict[str, Any]],
    plant: Plant,
    fact_ids: list[str],
    max_chains: int,
) -> list[dict[str, Any]]:
    system = render(
        prompt.body,
        {
            # as data: plant text and the specialists' words cannot close a block (CLAUDE.md §3)
            "scenarios": as_data(scenarios),
            "plant": as_data(plant_for_screen(plant)),
            "fact_ids": as_data(fact_ids),
            "max_chains": str(max_chains),
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]


class ConnectorStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(PROMPT, config)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        scenarios = scenario_lines(writer, self.plant, self.ref, self.config)
        fact_ids = sorted(f.id for f in plant_facts(self.plant, run.plant_record_id))
        max_chains = post_setting(writer.run, self.config, "connector_max_chains")
        limit = post_setting(writer.run, self.config, "connector_max_input_tokens")
        prices = self.config.models.tiers[Tier(self.config.routing.jobs[JOB])]
        total = len(scenarios)
        messages = connector_messages(self.prompt, scenarios, self.plant, fact_ids, max_chains)
        while scenarios and estimate_cost(prices, messages, None, 0).input_tokens > limit:
            scenarios = scenarios[:-1]
            messages = connector_messages(self.prompt, scenarios, self.plant, fact_ids, max_chains)
        left_out = total - len(scenarios)
        if left_out:
            log.warning(
                "connector input cut to fit connector_max_input_tokens",
                extra={"context": {"run_id": run.id, "left_out": left_out, "sent": len(scenarios)}},
            )
        if not scenarios:
            return StepResult(next_step=NEXT, summary={"scenarios": 0, "left_out": left_out})

        def validator(value: Any) -> None:
            if isinstance(value, ConnectorAnswer) and len(value.chains) > max_chains:
                raise ValueError(f"more than {max_chains} chains")

        try:
            result = self.gateway.call(
                job=JOB,
                prompt_version=self.prompt.label,
                messages=messages,
                schema=ConnectorAnswer,
                validator=validator,
                run=post_budget(writer),
                made=frozenset(c.id for c in writer.model_calls()),
            )
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused)
        findings = {f.id: f for f in writer.findings()}
        kept: list[Chain] = []
        rejected: list[dict[str, Any]] = []
        call_id = result.model_calls[-1].id if result.model_calls else None
        if result.outcome == "ok" and isinstance(result.value, ConnectorAnswer):
            for proposed in result.value.chains:
                problem = chain_problem(proposed.links, findings, set(fact_ids))
                chain_id = None if problem else ids.chain_id(proposed.links)
                if chain_id is not None and any(c.id == chain_id for c in kept):
                    problem = "the same links as an earlier chain"
                if problem is not None or chain_id is None:
                    rejected.append({"links": list(proposed.links), "reason": problem})
                    log.warning(
                        "connector chain rejected",
                        extra={
                            "context": {
                                "run_id": run.id,
                                "links": proposed.links,
                                "reason": problem,
                            }
                        },
                    )
                    continue
                kept.append(
                    Chain(
                        id=chain_id,
                        run_id=run.id,
                        links=list(proposed.links),
                        description=proposed.description,
                        reason=proposed.reason,
                        flags=chain_flags(proposed.links, findings),
                        model_call_id=call_id,
                    )
                )
        else:
            log.warning(
                "connector call failed; the run goes on with no chains",
                extra={
                    "context": {"run_id": run.id, "outcome": result.outcome, "error": result.error}
                },
            )
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": [c.id for c in kept]}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_spent(result.cost_usd, cap_usd=result.cap_cost_usd)
        for chain in kept:
            writer.add_chain(chain)
        summary: dict[str, Any] = {
            "connector": {"outcome": result.outcome, "error": result.error},
            "scenarios": len(scenarios),
            "left_out": left_out,
            "rejected": rejected,
        }
        return StepResult(next_step=NEXT, summary=summary)
