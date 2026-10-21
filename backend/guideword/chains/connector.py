"""The chains step: the connector (spec 3.1; PROJECT.md §5 Step 5; plan PR 5, Q6, Q7, G3, G7;
connector/v2 plan, approved 2026-10-21).

One Ultra call (job `connector`, prompt `connector/v2`) reads one line per scenario (R48) in
R50 tier order, the plant record as the whole-plant pass sees it (G17) and a numbered list of
plant facts, all as data, and proposes at most `connector_max_chains` chains. The scenario
lines are cut, from the bottom, until the request fits `connector_max_input_tokens` by the
agreed estimate; how many were left out is logged and kept in the step's summary.

**Handles (v2).** In v1, Ultra copied the long finding IDs wrongly. Now each line sent is
shown as `L1`, `L2`, … with no finding ID, and each fact as `P1`, `P2`, … with its fact ID and
value; Ultra links only by handle, and code maps each handle back to its ID exactly. The
handles are numbered after the cut, so each names a line that was sent. A link that is not a
handle in the lists, written exactly, rejects the chain. The fact list holds only facts on
the lines' scenario objects (failing components and section objects), their locations and
utilities, and, for those, the relief devices protecting them, those devices' inlet valves,
the heat sources' isolating valves and the valves on lines that start or end at them.

Code checks every chain: at least two links, none repeated; every link a handle that maps
to a finding ID of this run or a fact ID of the plant; at least one a finding. Any other chain
is rejected,
logged with its reason and listed in the step's summary. A chain needing more than two
independent failures (more than two groups of finding links whose failing components do not
overlap) is flagged, never filtered (Q6). Misused terms are not checked by code; the engineer
reads the description. The links keep the model's order: the first finding link is the cause
(Q7); the ID sorts them.

**Chain text (target-handles plan, approved 2026-10-21).** Ultra writes its own handles into a
chain's description and reason ("(L20)"). After mapping, code replaces each whole `L<n>` token
with the mapped line's question ID ("<question ID> (<cause ID>)" where two lines sent share a
question ID, or the lead finding ID where they also share the cause) and each `P<n>` with the
fact ID, so no later prompt reads another prompt's handle. A chain where a token was replaced
is flagged "handles in text replaced by code"; a handle that was not sent is left as it is and
the chain is flagged "unresolved handle in text". The raw answer stays unchanged in the
model-call record.

A call that fails (invalid twice, cut off, an error) leaves the run going with no chains,
logged (G3); only a cap refusal stops the run.
"""

import re
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
from guideword.runs.extend import post_pass
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.plants import _plant_objects, plant_facts
from guideword.runs.post_budget import post_budget, post_setting
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import EventType, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import Chain, Finding, PlantFact, Run
from guideword.screen.schema import plant_for_screen

JOB = "connector"
PROMPT = "connector"
NEXT = "chain_severity"
ASK = "Name the chains, in the required JSON schema."
MORE_THAN_TWO_FLAG = "possibly more than two independent failures"
HANDLES_REPLACED_FLAG = "handles in text replaced by code"
UNRESOLVED_HANDLE_FLAG = "unresolved handle in text"
# a whole connector handle in the model's text: L or P and a number, nothing joined to it
HANDLE_IN_TEXT = re.compile(r"\b[LP]\d+\b")

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


def map_links(
    links: Sequence[str], line_handles: Mapping[str, str], fact_handles: Mapping[str, str]
) -> tuple[list[str], str | None]:
    """v2: each link a handle, mapped back to its finding or fact ID exactly, in the model's
    order; any other link (a lower-case or spaced handle, a raw ID) rejects the chain."""
    unknown = [link for link in links if link not in line_handles and link not in fact_handles]
    if unknown:
        return [], f"not a handle in the lists: {', '.join(repr(u) for u in unknown)}"
    return [line_handles.get(link) or fact_handles[link] for link in links], None


def line_labels(scenarios: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """What each `L` handle becomes in chain text: the lead finding's question ID; "<question
    ID> (<cause ID>)" where two lines sent share the question ID (Bhargavi, Q4); the lead
    finding ID where they also share the cause, so each label names one line."""
    questions = [line["question_id"] for line in scenarios]
    pairs = [(line["question_id"], line["cause_id"]) for line in scenarios]
    labels: dict[str, str] = {}
    for i, line in enumerate(scenarios, start=1):
        question, cause = line["question_id"], line["cause_id"]
        if questions.count(question) == 1:
            labels[f"L{i}"] = question
        elif pairs.count((question, cause)) == 1:
            labels[f"L{i}"] = f"{question} ({cause})"
        else:
            labels[f"L{i}"] = line["finding_id"]
    return labels


def clean_chain_text(
    text: str, labels: Mapping[str, str], fact_handles: Mapping[str, str]
) -> tuple[str, list[str]]:
    """The chain text with each sent handle replaced (exact tokens only), and its flags."""
    replaced = unresolved = False

    def swap(match: re.Match[str]) -> str:
        nonlocal replaced, unresolved
        token = match.group(0)
        found = labels.get(token) or fact_handles.get(token)
        if found is None:
            unresolved = True
            return token
        replaced = True
        return found

    cleaned = HANDLE_IN_TEXT.sub(swap, text)
    flags = [HANDLES_REPLACED_FLAG] if replaced else []
    return cleaned, flags + ([UNRESOLVED_HANDLE_FLAG] if unresolved else [])


def scenario_prompt_lines(scenarios: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The lines as the prompt shows them: a handle each, no finding ID."""
    hidden = ("finding_id", "object_ids", "question_id", "cause_id")
    return [
        {"handle": f"L{i}", **{k: v for k, v in line.items() if k not in hidden}}
        for i, line in enumerate(scenarios, start=1)
    ]


def fact_objects(object_ids: Collection[str], plant: Plant) -> set[str]:
    """The objects whose facts the connector sees (connector/v2 plan, approved 2026-10-21)."""
    base = set(object_ids)
    by_id = {getattr(o, "id"): o for o in _plant_objects(plant)}  # noqa: B009
    utilities = {u.id for u in plant.utilities}
    listed = set(base)
    for object_id in base:
        location = getattr(by_id.get(object_id), "location_id", None)
        if location:
            listed.add(location)
    heat_lines = {
        h.via_line_id
        for e in plant.equipment
        if e.id in base
        for h in e.heat_sources
        if h.via_line_id
    }
    for line in plant.lines:
        if line.id in base or line.id in heat_lines or {line.from_id, line.to_id} & base:
            listed |= {end for end in (line.from_id, line.to_id) if end in utilities}
    found = set(listed)
    for device in plant.relief_devices:
        if device.protects_id in listed:
            found.add(device.id)
            found |= set(device.inlet_valve_ids)
    for equipment in plant.equipment:
        if equipment.id in listed:
            for source in equipment.heat_sources:
                found |= set(source.isolating_valve_ids)
    ends = {line.id for line in plant.lines if {line.from_id, line.to_id} & listed}
    found |= {v.id for v in plant.valves if v.on_line_id in ends}
    return found


def fact_list(object_ids: Collection[str], plant: Plant, plant_record_id: str) -> list[PlantFact]:
    """The plant facts on `fact_objects`, sorted by fact ID."""
    objects = fact_objects(object_ids, plant)
    return [f for f in plant_facts(plant, plant_record_id) if f.id.split(".", 1)[0] in objects]


def fact_prompt_lines(facts: Sequence[PlantFact]) -> list[dict[str, Any]]:
    return [
        {"handle": f"P{i}", "fact_id": f.id, "value": f.value} for i, f in enumerate(facts, start=1)
    ]


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
                # for the chain-text labels (not shown in the prompt)
                "question_id": lead.question_id,
                "cause_id": lead.cause_id,
                # what the fact list hangs off (not shown in the prompt)
                "object_ids": sorted(
                    set(lead.failing_component_ids) | set(section.object_ids if section else ())
                ),
            }
        )
    return out


def connector_messages(
    prompt: Prompt,
    scenarios: list[dict[str, Any]],
    plant: Plant,
    facts: list[PlantFact],
    max_chains: int,
) -> list[dict[str, Any]]:
    system = render(
        prompt.body,
        {
            # as data: plant text and the specialists' words cannot close a block (CLAUDE.md §3)
            "scenarios": as_data(scenario_prompt_lines(scenarios)),
            "plant": as_data(plant_for_screen(plant)),
            "facts": as_data(fact_prompt_lines(facts)),
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

    def facts(self, run: Run, scenarios: Sequence[Mapping[str, Any]]) -> list[PlantFact]:
        objects = {o for line in scenarios for o in line["object_ids"]}
        return fact_list(objects, self.plant, run.plant_record_id)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        if not writer.has_event(EventType.RUN_EXTENDED):
            # a new run: its post-step prompts and caps are recorded here, not hashed (Q5)
            writer.emit(
                EventType.RUN_EXTENDED,
                {
                    **post_pass(run, self.config, run.post_spend_cap_usd),
                    "resumed_after_post_cap": False,
                    "step": run.step,
                },
            )
        scenarios = scenario_lines(writer, self.plant, self.ref, self.config)
        max_chains = post_setting(writer.run, self.config, "connector_max_chains")
        limit = post_setting(writer.run, self.config, "connector_max_input_tokens")
        prices = self.config.models.tiers[Tier(self.config.routing.jobs[JOB])]
        total = len(scenarios)
        facts = self.facts(run, scenarios)
        messages = connector_messages(self.prompt, scenarios, self.plant, facts, max_chains)
        while scenarios and estimate_cost(prices, messages, None, 0).input_tokens > limit:
            scenarios = scenarios[:-1]
            facts = self.facts(run, scenarios)
            messages = connector_messages(self.prompt, scenarios, self.plant, facts, max_chains)
        # handles are numbered after the cut: each names a line or fact that was sent
        line_handles = {f"L{i}": line["finding_id"] for i, line in enumerate(scenarios, start=1)}
        labels = line_labels(scenarios)
        fact_handles = {f"P{i}": fact.id for i, fact in enumerate(facts, start=1)}
        fact_ids = set(fact_handles.values())
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
            return stop_for_refusal(writer, refused, cap=POST_CAP)
        findings = {f.id: f for f in writer.findings()}
        kept: list[Chain] = []
        rejected: list[dict[str, Any]] = []
        call_id = result.model_calls[-1].id if result.model_calls else None
        if result.outcome == "ok" and isinstance(result.value, ConnectorAnswer):
            for proposed in result.value.chains:
                links, problem = map_links(proposed.links, line_handles, fact_handles)
                if problem is None:
                    problem = chain_problem(links, findings, fact_ids)
                chain_id = None if problem else ids.chain_id(links)
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
                                "mapped": links,
                                "reason": problem,
                            }
                        },
                    )
                    continue
                description, text_flags = clean_chain_text(
                    proposed.description, labels, fact_handles
                )
                reason, reason_flags = clean_chain_text(proposed.reason, labels, fact_handles)
                kept.append(
                    Chain(
                        id=chain_id,
                        run_id=run.id,
                        links=links,
                        description=description,
                        reason=reason,
                        flags=[
                            *chain_flags(links, findings),
                            *dict.fromkeys([*text_flags, *reason_flags]),
                        ],
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
        writer.add_post_spent(result.cost_usd)
        for chain in kept:
            writer.add_chain(chain)
        summary: dict[str, Any] = {
            "connector": {"outcome": result.outcome, "error": result.error},
            "scenarios": len(scenarios),
            "left_out": left_out,
            "rejected": rejected,
        }
        return StepResult(next_step=NEXT, summary=summary)
