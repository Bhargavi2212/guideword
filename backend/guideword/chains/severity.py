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

**v2 (target-handles plan, approved 2026-10-21).** On case F, `severity_chain/v1` rated only the
last 2 of 10 chains, reading the tail of a long list as "the last batch". So each call now
sends at most `chain_severity_batch_size` chains, named `C1…` (no chain or finding ID shown,
the list never called a batch, its count and handles stated), and code checks the answer
against what was sent: the handles it left out are asked once more, alone, in the next call;
a chain left out twice (or in two failed calls) is "not assessed" and gets no LOPA. An unknown
handle is dropped; a handle answered twice makes the answer invalid. Each call's summary
records how many were sent and answered, and which handles were missing.
"""

from collections import Counter
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.chains.words import chain_words, count_text
from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.ranking.severity import NOT_ASSESSED, severity_classes, severity_context
from guideword.reference import ReferenceSet
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.plants import plant_facts
from guideword.runs.post_budget import post_budget, post_setting
from guideword.runs.store import StepWriter
from guideword.schema.enums import SeverityClass
from guideword.schema.plant import Plant
from guideword.schema.records import Chain, Finding, Run

JOB = "chain_severity"
PROMPT = "severity_chain"
NEXT = "lopa"
STEP = "chain_severity"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChainSeverity(_Strict):
    # a handle, C1…, mapped back to its chain by code
    chain: str
    severity_class: SeverityClass
    reason: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class ChainSeverityAnswer(_Strict):
    severities: list[ChainSeverity]


def _done(chain: Chain) -> bool:
    return chain.severity_class is not None or chain.severity_reason is not None


def ask(handles: list[str], re_ask: bool) -> str:
    """The user message: the count and handles, never a group label."""
    listed = ", ".join(handles)
    if re_ask:
        return (
            f"Your last answer left out these {len(handles)} chains ({listed}). Give the "
            "severity of each of them, in the required JSON schema."
        )
    return (
        f"Give the severity of each of the {len(handles)} chains ({listed}), in the required "
        "JSON schema."
    )


def chain_severity_messages(
    prompt: Prompt,
    chains: list[Chain],
    findings: dict[str, Finding],
    facts: dict[str, Any],
    ref: ReferenceSet,
    plant: Plant,
    *,
    re_ask: bool = False,
) -> list[dict[str, Any]]:
    causes = {c.id: c.cause for c in ref.causes}
    handles = [f"C{i}" for i in range(1, len(chains) + 1)]
    shown = [
        {"handle": handle, **chain_words(c, findings, facts, causes)}
        for handle, c in zip(handles, chains, strict=True)
    ]
    system = render(
        prompt.body,
        {
            # as data: the connector's and specialists' words cannot close a block
            "severity_classes": as_data(severity_classes(ref)),
            "chains": as_data(shown, default=str),
            "context": as_data(severity_context(plant), default=str),
            "count": count_text(handles)["count"],
            "handles": count_text(handles)["handles"],
        },
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": ask(handles, re_ask)},
    ]


class ChainSeverityStepper:
    def __init__(
        self, gateway: Gateway, *, config: Config, ref: ReferenceSet, plant: Plant
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.prompt = load_prompt(PROMPT, config)

    def _not_assessed(self, writer: StepWriter, chain: Chain, why: str) -> None:
        update = {"severity_reason": f"{NOT_ASSESSED}: {why}"[:300]}
        writer.fill_chain_severity(chain.model_copy(update=update))

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        todo = [c for c in writer.chains() if not _done(c)]
        if not todo:
            return StepResult(next_step=NEXT)
        summaries = writer.step_summaries(STEP)
        asked = Counter(i for s in summaries for i in s.get("sent_ids", []))
        last_missing = summaries[-1].get("missing_ids", []) if summaries else []
        # a chain asked twice is done with: not assessed
        for chain in todo:
            if asked[chain.id] >= 2:
                self._not_assessed(writer, chain, "left out of the chain severity answer twice")
        todo = [c for c in todo if asked[c.id] < 2]
        # first the handles the last answer left out, alone; then the next new chains
        re_ask = [c for c in todo if c.id in last_missing and asked[c.id] == 1]
        size = post_setting(writer.run, self.config, "chain_severity_batch_size")
        batch = re_ask or [c for c in todo if asked[c.id] == 0][:size]
        if not batch:
            for chain in todo:
                self._not_assessed(writer, chain, "left out of the chain severity answer")
            return StepResult(next_step=NEXT)
        handles = {f"C{i}": c for i, c in enumerate(batch, start=1)}
        wanted = {c.id for c in batch}

        def validator(value: Any) -> None:
            if not isinstance(value, ChainSeverityAnswer):
                raise ValueError("not a chain severity answer")
            for handle, n in Counter(s.chain for s in value.severities).items():
                if n > 1:
                    raise ValueError(f"{handle} is rated more than once")

        findings = {f.id: f for f in writer.findings()}
        facts = {f.id: f.value for f in plant_facts(self.plant, run.plant_record_id)}
        messages = chain_severity_messages(
            self.prompt, batch, findings, facts, self.ref, self.plant, re_ask=bool(re_ask)
        )
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
            # an unknown handle is dropped; each known one maps back to its chain exactly
            rated = {handles[s.chain].id: s for s in result.value.severities if s.chain in handles}
        missing = [h for h, c in handles.items() if c.id not in rated]
        for chain in handles.values():
            given = rated.get(chain.id)
            if given is not None:
                update = {"severity_class": given.severity_class, "severity_reason": given.reason}
                writer.fill_chain_severity(chain.model_copy(update=update))
            elif re_ask:
                why = (
                    "left out of the chain severity answer twice"
                    if result.outcome == "ok"
                    else f"{result.error or result.outcome} (asked twice)"
                )
                self._not_assessed(writer, chain, why)
        summary = {
            "sent": len(handles),
            "answered": len(rated),
            "missing": missing,
            "re_ask": bool(re_ask),
            "sent_ids": [c.id for c in handles.values()],
            "missing_ids": [handles[h].id for h in missing],
            "outcome": result.outcome,
        }
        left = [c for c in writer.chains() if not _done(c)]
        return StepResult(next_step=None if left else NEXT, summary=summary)
