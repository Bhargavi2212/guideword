"""The evidence step (Phase 4 spec 4.4; plan PR 5b, P4-1 to P4-9, Q2, Q4, Q11-Q15, G4-G6, G20).

A fixed code step after `recommendations`. It never changes rank, tier, lead, severity, LOPA or
recommendations (P4-2): it only adds evidence records, agent steps, tool calls and judge calls.

**Which lines** (P4-3): the top `evidence_top_n` confirmed and also-found lines (findings and
chains) of the shortlist built from the stored records, with the run's lead rule and without
overrides. One line per `advance`; a line is done once it has a precedent record.

**Off** (Q4): when the run's use is `benchmark` or `test_5`, when `--no-evidence` was given, or
when no evidence tools were given (a test or replay that doesn't ask for them). The step then
records why and moves on with no call.

**Per line**, one agent step per tool used (agent `evidence`):
1. `physics_calc`: each calculation `physics.applicable` gives the line (the attachment rule,
   review plan §0a), one card per equipment; the raw value goes in the tool call's result, the
   card text in the summary.
2. `search_precedent`: the local index, minus the plant's block terms, ranked by BM25 against a
   query built by code from the line.
3. `web_research` (Q15): one Tavily search on the top line always, its results judged with the
   index candidates; on other lines only when no index candidate is accepted. Block-filtered,
   capped per run (`tavily_searches_per_run`, counted from the run's own tool calls).
4. The judge (`precedent_judge`, Super): each candidate by handle `K<n>`, same mechanism true or
   false with a reason. Each accepted candidate is one `confirmed` precedent record (Q2); with
   none, one `ev:<target>:precedent:none` record.

**Failures** (G5): a judge call that fails, or a search that fails, leaves the line's precedent
`none`, flagged; only a budget refusal stops the run, and then nothing of that line is written
except the model calls already paid for.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.chains.words import count_text
from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway
from guideword.gateway.prompts import Prompt, as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.lopa.lines import ShortlistLine, cause_words, section_for
from guideword.recommend.step import current_shortlist
from guideword.reference import ReferenceSet
from guideword.reference.precedents import PrecedentIndex, PrecedentRow
from guideword.runs.machine import POST_CAP, StepResult, stop_for_refusal
from guideword.runs.post_budget import evidence_setting, evidence_settings, post_budget
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.enums import (
    Agent,
    AgentTool,
    BudgetUse,
    Calculation,
    EvidenceKind,
    QuestionKind,
    ShortlistTier,
    Verdict,
)
from guideword.schema.plant import Plant
from guideword.schema.records import AgentStep, Chain, Evidence, Finding, Run, Section, ToolCall
from guideword.tools import physics
from guideword.tools.precedent import block_list_for, blocked, bm25, query_for, row_texts
from guideword.tools.web import SearchFailed, WebHit, WebSearch

log = get_logger(__name__)

STEP = "evidence"
JOB = "precedent_judge"
PROMPT = "precedent_judge"
NEXT = "ranked"
# Q4: these uses never run evidence, so a benchmark run can't reach the index or the web
OFF_USES = frozenset({BudgetUse.BENCHMARK, BudgetUse.TEST_5})
LINE_TIERS = frozenset({ShortlistTier.CONFIRMED, ShortlistTier.ALSO_FOUND})
NO_PRECEDENT_TEXT = "no matching precedent found"
# shown verbatim at the start of a precedent's summary, so the card says where it came from
SOURCE_TYPE = {"index": "CSB investigation", "web": "web result"}
JUDGE_FAILED = "precedent judge failed ({call})"
SEARCH_FAILED = "web search failed: {reason}"
CAP_REACHED = "per-run web search cap of {cap} reached"
FALLBACK_NOT_JUDGED = "web results not judged: {reason}"

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Judgement(_Strict):
    """precedent_judge/v2: two questions, each with its reason (Bhargavi, 2026-10-22)."""

    # a handle, K<n>, mapped back to its candidate by code
    candidate: str
    # an actual event at a site, not guidance, troubleshooting, a data sheet or a video
    is_incident: bool
    incident_reason: Text300
    same_mechanism: bool
    reason: Text300


class JudgeAnswer(_Strict):
    judgements: list[Judgement]


@dataclass(frozen=True)
class EvidenceTools:
    """What the step needs beyond the gateway: the web search, the precedent index, where the
    block lists live, and whether evidence is on at all (`--no-evidence` sets it off)."""

    web: WebSearch
    index: PrecedentIndex
    cases_dir: Path | None = None
    enabled: bool = True


@dataclass(frozen=True)
class Candidate:
    """A precedent candidate as code holds it; the judge sees it only by handle."""

    source: str  # "index" or "web"
    key: str  # the index row ID, or the URL
    title: str
    url: str
    shown: dict[str, Any] = field(compare=False)


def evidence_lines(lines: Sequence[ShortlistLine], top_n: int) -> list[ShortlistLine]:
    """P4-3: the top lines with a finding or a chain, in the confirmed and also-found tiers."""
    chosen = [
        item
        for item in lines
        if item.planned.tier in LINE_TIERS and item.planned.target_kind in ("finding", "chain")
    ]
    return chosen[:top_n]


def off_reason(gateway: Gateway, tools: EvidenceTools | None) -> str | None:
    if tools is None:
        return "no evidence tools given"
    if not tools.enabled:
        return "--no-evidence"
    if gateway.use in OFF_USES:
        return f"use {gateway.use}"
    return None


# --- the line in words ---------------------------------------------------------------------------


def line_links(
    item: ShortlistLine,
    findings: Mapping[str, Finding],
    questions: Mapping[str, Any],
    sections: Mapping[str, Section],
) -> list[tuple[Finding, Section | None]]:
    """A finding line's lead, or a chain's finding links, each with its section."""
    chain = item.planned.chain
    wanted = chain.links if chain is not None else [item.target_id]
    return [
        (findings[link], section_for(findings[link], questions, sections))
        for link in wanted
        if link in findings
    ]


def _question_words(found: Finding, chemicals: Mapping[str, str]) -> str:
    parsed = ids.parse_question_id(found.question_id)
    if parsed.kind == QuestionKind.MATRIX:
        return f"{parsed.parts[1]} {parsed.parts[2]}"
    return " with ".join(chemicals.get(p, p) for p in parsed.parts)


def _component_types(plant: Plant) -> dict[str, str]:
    types = {e.id: str(e.type).replace("_", " ") for e in plant.equipment}
    types |= {v.id: f"{v.kind} valve" for v in plant.valves}
    types |= {line.id: "line" for line in plant.lines}
    return types


def judge_line(
    links: Sequence[tuple[Finding, Section | None]],
    chain: Chain | None,
    plant: Plant,
    ref: ReferenceSet,
) -> dict[str, Any]:
    """The line as the judge reads it: no finding ID, chain ID or number."""
    causes = {c.id: c.cause for c in ref.causes}
    chemicals = {c.id: c.name for c in plant.chemicals}
    types = _component_types(plant)
    words = [
        {
            "question": _question_words(found, chemicals),
            "cause": cause_words(found, causes),
            "consequence": found.consequence,
            "failing_components": [
                {"id": c, "type": types.get(c)} for c in found.failing_component_ids
            ],
        }
        for found, _ in links
    ]
    if chain is not None:
        return {"chain": chain.description, "links": words}
    return words[0] if words else {}


# --- the step ------------------------------------------------------------------------------------


class EvidenceStepper:
    def __init__(
        self,
        gateway: Gateway,
        *,
        config: Config,
        ref: ReferenceSet,
        plant: Plant,
        tools: EvidenceTools | None = None,
    ) -> None:
        self.gateway = gateway
        self.config = config
        self.ref = ref
        self.plant = plant
        self.tools = tools
        self.prompt = load_prompt(PROMPT, config)

    def __call__(self, run: Run, writer: StepWriter) -> StepResult:
        reason = off_reason(self.gateway, self.tools)
        if reason is not None or self.tools is None:
            return StepResult(next_step=NEXT, summary={"evidence": "off", "reason": reason})
        tools = self.tools
        top_n = int(evidence_setting(run, self.config, "evidence_top_n"))
        lines = evidence_lines(current_shortlist(writer, self.plant, self.ref, self.config), top_n)
        done = {e.target_id for e in writer.evidence() if e.kind == EvidenceKind.PRECEDENT}
        todo = [item for item in lines if item.target_id not in done]
        if not todo:
            return StepResult(next_step=NEXT, summary=self._summary(run, tools, lines))
        item = todo[0]
        return self._line(run, writer, tools, item, top=item is lines[0])

    def _summary(
        self, run: Run, tools: EvidenceTools, lines: Sequence[ShortlistLine]
    ) -> dict[str, Any]:
        block = block_list_for(self.plant.plant_id, tools.cases_dir)
        return {
            "evidence": "on",
            "lines": [item.target_id for item in lines],
            "settings": evidence_settings(run, self.config),
            "block_list": None
            if block is None
            else {"file": block.path.name, "version": block.version, "terms": len(block.terms)},
            "precedent_index_version": tools.index.version,
        }

    # --- one line ----------------------------------------------------------------------------

    def _line(
        self,
        run: Run,
        writer: StepWriter,
        tools: EvidenceTools,
        item: ShortlistLine,
        *,
        top: bool,
    ) -> StepResult:
        findings = {f.id: f for f in writer.findings()}
        questions = {q.id: q for q in writer.questions()}
        sections = {s.id: s for s in writer.sections()}
        links = line_links(item, findings, questions, sections)
        target = item.target_id
        block = block_list_for(self.plant.plant_id, tools.cases_dir)
        terms = block.terms if block is not None else ()
        pending = _Pending(writer, run.id, target)

        # 1. physics, pure code: the line's links in its order, fact links too (review plan §0a)
        chain = item.planned.chain
        cards = physics.applicable(
            physics.line_links(
                chain.links if chain is not None else [target],
                findings,
                lambda f: section_for(f, questions, sections),
            ),
            self.plant,
        )
        if cards:
            step = pending.step(AgentTool.PHYSICS_CALC, "code: physics calculations for this line")
            for calculation, equipment_id, _ in cards:
                result = self._calculate(run, calculation, equipment_id)
                arguments = {"calculation": str(calculation), "equipment_id": equipment_id}
                calc_call = ids.tool_call_id(step.id, AgentTool.PHYSICS_CALC, arguments)
                evidence = physics.as_evidence(
                    result, run_id=run.id, target_id=target, tool_call_id=calc_call
                )
                pending.tool(
                    step,
                    AgentTool.PHYSICS_CALC,
                    arguments,
                    result.tool_result(),
                    record_ids=[evidence.id],
                )
                pending.evidence.append(evidence)

        # 2. the local index
        k = int(evidence_setting(run, self.config, "precedent_candidates"))
        rows = [row for row in tools.index.rows if not blocked(row_texts(row), terms)]
        query = query_for(links, self.plant, self.ref)
        ranked = bm25(rows, query, k)
        index_step = pending.step(AgentTool.SEARCH_PRECEDENT, "code: precedent index search")
        index_call = pending.tool(
            index_step,
            AgentTool.SEARCH_PRECEDENT,
            {"query": query, "k": k},
            {
                "candidates": [row.id for row, _ in ranked],
                "scores": [score for _, score in ranked],
                "blocked_rows": len(tools.index.rows) - len(rows),
                "index_version": tools.index.version,
            },
            source_urls=[row.url for row, _ in ranked],
        )
        candidates = [_index_candidate(row) for row, _ in ranked]
        flags: list[str] = []
        sources: dict[str, str] = {c.key: index_call for c in candidates}

        # 3. the top line always searches the web too (Q15)
        if top:
            hits, web_call = self._search(run, writer, tools, pending, query, terms, flags)
            web = [_web_candidate(hit) for hit in hits]
            candidates += [c for c in web if c.key not in {x.key for x in candidates}]
            sources |= {c.key: web_call for c in web if web_call is not None}

        # 4. judge; a refusal here stops the run before anything of the line is written
        line = judge_line(links, item.planned.chain, self.plant, self.ref)
        try:
            accepted, call_id, failed = self._judge(writer, target, line, candidates)
        except BudgetRefused as refused:
            return stop_for_refusal(writer, refused, cap=POST_CAP)
        if failed:
            flags.append(JUDGE_FAILED.format(call=call_id))
        stopped: StepResult | None = None
        if not top and not accepted and not failed:
            hits, web_call = self._search(run, writer, tools, pending, query, terms, flags)
            if hits:
                web = [_web_candidate(hit) for hit in hits]
                sources |= {c.key: web_call for c in web if web_call is not None}
                try:
                    accepted, call_id, failed = self._judge(writer, target, line, web)
                except BudgetRefused as refused:
                    flags.append(FALLBACK_NOT_JUDGED.format(reason=refused))
                    stopped = stop_for_refusal(writer, refused, cap=POST_CAP)
                else:
                    if failed:
                        flags.append(JUDGE_FAILED.format(call=call_id))

        # 5. the precedent records (Q2)
        for candidate, judgement in accepted:
            pending.evidence.append(
                Evidence(
                    id=_precedent_id(target, candidate),
                    run_id=run.id,
                    target_id=target,
                    kind=EvidenceKind.PRECEDENT,
                    verdict=Verdict.CONFIRMED,
                    summary=(
                        f"{SOURCE_TYPE[candidate.source]}: {candidate.title}: {judgement.reason}"
                    ),
                    tool_call_id=sources.get(candidate.key),
                    sources=[candidate.title, candidate.url],
                    model_call_id=call_id,
                    flags=list(flags),
                )
            )
        if not accepted:
            pending.evidence.append(
                Evidence(
                    id=ids.no_precedent_evidence_id(target),
                    run_id=run.id,
                    target_id=target,
                    kind=EvidenceKind.PRECEDENT,
                    verdict=Verdict.NONE,
                    summary=NO_PRECEDENT_TEXT,
                    tool_call_id=index_call,
                    model_call_id=call_id,
                    flags=list(flags),
                )
            )
        pending.write()
        return stopped if stopped is not None else StepResult()

    def _calculate(
        self, run: Run, calculation: Calculation, equipment_id: str
    ) -> physics.CalcResult:
        return calculate(run, self.config, self.plant, calculation, equipment_id)

    def _search(
        self,
        run: Run,
        writer: StepWriter,
        tools: EvidenceTools,
        pending: "_Pending",
        query: str,
        terms: Sequence[str],
        flags: list[str],
    ) -> tuple[list[WebHit], str | None]:
        """One web search, block-filtered; refused past the per-run cap (G6: a tool call with
        its reason, no ledger line). A failed search is flagged and the line goes on (G5); a
        budget refusal propagates."""
        cap = int(evidence_setting(run, self.config, "tavily_searches_per_run"))
        n = int(evidence_setting(run, self.config, "tavily_max_results"))
        arguments = {"query": query, "max_results": n}
        step = pending.step(AgentTool.WEB_RESEARCH, "code: web search")
        sent = [
            c
            for c in [*writer.tool_calls(), *pending.calls]
            if c.tool == AgentTool.WEB_RESEARCH and c.refused_reason is None
        ]
        if len(sent) >= cap:
            reason = CAP_REACHED.format(cap=cap)
            pending.tool(step, AgentTool.WEB_RESEARCH, arguments, None, refused=reason)
            flags.append(reason)
            return [], None
        try:
            found = tools.web.search(query, n)
        except SearchFailed as error:
            reason = SEARCH_FAILED.format(reason=error)
            pending.tool(step, AgentTool.WEB_RESEARCH, arguments, None, refused=reason)
            flags.append(reason)
            return [], None
        kept = [h for h in found.hits if not blocked([h.title, h.url, h.content], terms)]
        call_id = pending.tool(
            step,
            AgentTool.WEB_RESEARCH,
            arguments,
            {
                "cache_key": found.cache_key,
                "cache_hit": found.cache_hit,
                "urls": [h.url for h in kept],
                "blocked_results": len(found.hits) - len(kept),
            },
            source_urls=[h.url for h in kept],
        )
        return kept, call_id

    def _judge(
        self,
        writer: StepWriter,
        target: str,
        line: dict[str, Any],
        candidates: Sequence[Candidate],
    ) -> tuple[list[tuple[Candidate, Judgement]], str | None, bool]:
        """(accepted candidates with their judgement, the judge's call ID, failed). With no
        candidate there is no call."""
        if not candidates:
            return [], None, False
        handles = [f"K{n}" for n in range(1, len(candidates) + 1)]
        by_handle = dict(zip(handles, candidates, strict=True))
        result = self.gateway.call(
            job=JOB,
            prompt_version=self.prompt.label,
            messages=judge_messages(
                self.prompt,
                line,
                [{"handle": h, **c.shown} for h, c in by_handle.items()],
            ),
            schema=JudgeAnswer,
            run=post_budget(writer),
            made=frozenset(c.id for c in writer.model_calls()),
        )
        for call in result.model_calls:
            writer.add_model_call(
                call.model_copy(update={"record_ids": [target]}),
                fell_back_from=result.fell_back_from,
            )
        writer.add_post_spent(result.cost_usd)
        call_id = result.model_calls[-1].id if result.model_calls else None
        if result.outcome != "ok" or not isinstance(result.value, JudgeAnswer):
            return [], call_id, True
        counts = Counter(j.candidate for j in result.value.judgements)
        dropped = sorted(h for h, n in counts.items() if h not in by_handle or n > 1)
        if dropped:
            log.warning(
                "precedent judge answer items dropped",
                extra={"context": {"target_id": target, "handles": dropped, "call": call_id}},
            )
        accepted = [
            (by_handle[j.candidate], j)
            for j in result.value.judgements
            if j.candidate in by_handle
            and counts[j.candidate] == 1
            and accepts(by_handle[j.candidate], j)
        ]
        return accepted, call_id, False


def calculate(
    run: Run, config: Config, plant: Plant, calculation: Calculation, equipment_id: str
) -> physics.CalcResult:
    """One physics card, with the run's own confirm minutes (the evidence step and R2)."""
    if calculation == Calculation.OVERFLOW_TIME:
        minutes = float(evidence_setting(run, config, "overflow_confirm_minutes"))
        return physics.overflow_time(equipment_id, plant, minutes)
    if calculation == Calculation.HEAT_UP_RATE:
        minutes = float(evidence_setting(run, config, "heat_up_confirm_minutes"))
        return physics.heat_up_rate(equipment_id, plant, minutes)
    return physics.blocked_in_heating(equipment_id, plant)


class _Pending:
    """A line's agent steps, tool calls and evidence, written together once the line is done,
    so a budget refusal mid-line leaves none of them."""

    def __init__(self, writer: StepWriter, run_id: str, target_id: str) -> None:
        self._writer = writer
        self._run_id = run_id
        self._target = target_id
        steps = writer.steps()
        self._previous = steps[-1].id if steps else run_id
        self.steps: list[AgentStep] = []
        self.calls: list[ToolCall] = []
        self.evidence: list[Evidence] = []

    def step(self, tool: AgentTool, reason: str) -> AgentStep:
        arguments = {"target_id": self._target}
        made = AgentStep(
            id=ids.agent_step_id(self._previous, Agent.EVIDENCE, tool, arguments),
            run_id=self._run_id,
            previous_id=self._previous,
            agent=Agent.EVIDENCE,
            tool=tool,
            arguments=arguments,
            reason=reason,
        )
        self._previous = made.id
        self.steps.append(made)
        return made

    def tool(
        self,
        step: AgentStep,
        tool: AgentTool,
        arguments: dict[str, Any],
        result: Any,
        *,
        refused: str | None = None,
        source_urls: Sequence[str] = (),
        record_ids: Sequence[str] = (),
    ) -> str:
        call = ToolCall(
            id=ids.tool_call_id(step.id, tool, arguments),
            run_id=self._run_id,
            agent_step_id=step.id,
            tool=tool,
            arguments=arguments,
            result=result,
            refused_reason=refused,
            source_urls=list(source_urls),
            record_ids=list(record_ids),
        )
        self.calls.append(call)
        return call.id

    def write(self) -> None:
        for step in self.steps:
            self._writer.add_step(step)
        for call in self.calls:
            self._writer.add_tool_call(call)
        for evidence in self.evidence:
            self._writer.add_evidence(evidence)


def accepts(candidate: Candidate, judgement: Judgement) -> bool:
    """The same mechanism, and either a CSB investigation from the index or an actual
    incident: a web guide or troubleshooting page with the same physics is not a precedent."""
    return judgement.same_mechanism and (candidate.source == "index" or judgement.is_incident)


def _index_candidate(row: PrecedentRow) -> Candidate:
    return Candidate(
        "index",
        row.id,
        row.title,
        row.url,
        {
            "source": "incident index",
            "title": row.title,
            "date": row.date,
            "location": row.location,
            "summary": row.summary,
        },
    )


def _web_candidate(hit: WebHit) -> Candidate:
    return Candidate(
        "web",
        hit.url,
        hit.title,
        hit.url,
        {"source": "web", "title": hit.title, "text": hit.content},
    )


def _precedent_id(target: str, candidate: Candidate) -> str:
    if candidate.source == "index":
        return ids.precedent_evidence_id(target, precedent_id=candidate.key)
    return ids.precedent_evidence_id(target, url=candidate.url)


def ask(handles: Sequence[str]) -> str:
    return (
        f"Judge each of the {len(handles)} candidates ({', '.join(handles)}), "
        "in the required JSON schema."
    )


def judge_messages(
    prompt: Prompt, line: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    handles = [c["handle"] for c in candidates]
    counted = count_text(handles)
    system = render(
        prompt.body,
        {
            "line": as_data(line, default=str),
            "candidates": as_data(candidates, default=str),
            "count": counted["count"],
            "handles": counted["handles"],
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": ask(handles)}]
