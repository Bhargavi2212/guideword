"""What the orchestrator sees each step (spec 2.5; plan R18, R44): built by code.

Coverage per list and per section; the open question IDs grouped by agent (up to
`dispatch_max_question_ids` per agent); the questions to retry at level `hard`, the failed
and the unsure ones (up to `id_list_max`); the last few steps' one-line results; and the
steps and spend left. Never a finding's consequence or cause text, nor the findings list.

From R50 (spec 2b.3) it also holds a `priority` block: per whole-plant hypothesis, its rank,
component IDs, cause ID, linked open question IDs (by agent) and whether a finding supports it yet
(computed here, never stored). Never the hypothesis's mechanism or consequence text.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from guideword.config import RunCaps
from guideword.questions.coverage import coverage
from guideword.schema.enums import Agent, Confidence, QuestionStatus, Tier
from guideword.schema.records import (
    AgentStep,
    Finding,
    Hypothesis,
    Question,
    Run,
    Section,
    ToolCall,
)
from guideword.screen.link import support
from guideword.specialists.routing import agent_for


def unsure_question_ids(questions: Sequence[Question], findings: Sequence[Finding]) -> list[str]:
    """Answered questions with an unsure finding and no Ultra re-answer yet, in ID order."""
    unsure = {f.question_id for f in findings if f.confidence == Confidence.UNSURE}
    reanswered = {f.question_id for f in findings if f.tier == Tier.ULTRA}
    return sorted(
        q.id
        for q in questions
        if q.status == QuestionStatus.ANSWERED and q.id in unsure and q.id not in reanswered
    )


def reanswers_used(findings: Sequence[Finding]) -> int:
    return len({f.question_id for f in findings if f.tier == Tier.ULTRA})


def by_agent(
    questions: Sequence[Question], sections: Mapping[str, Section]
) -> dict[Agent, list[str]]:
    grouped: dict[Agent, list[str]] = {}
    for question in sorted(questions, key=lambda q: q.id):
        grouped.setdefault(agent_for(question, sections), []).append(question.id)
    return grouped


def prioritised(ids: Sequence[str], hypotheses: Sequence[Hypothesis]) -> list[str]:
    """Linked questions first, by the best rank linking them and then ID; then the rest in
    ID order (spec 2b.3). Code orders; the model only asks for it."""
    best: dict[str, int] = {}
    for h in hypotheses:
        for question_id in h.question_ids:
            best[question_id] = min(best.get(question_id, h.rank), h.rank)
    linked = sorted((q for q in ids if q in best), key=lambda q: (best[q], q))
    return linked + sorted(q for q in ids if q not in best)


def linked_ids(hypotheses: Sequence[Hypothesis]) -> set[str]:
    return {q for h in hypotheses for q in h.question_ids}


def _priority(
    hypotheses: Sequence[Hypothesis],
    questions: Sequence[Question],
    findings: Sequence[Finding],
    sections: Mapping[str, Section],
    limit: int,
) -> list[dict[str, Any]]:
    """The linked open questions are grouped by the agent that answers them (R50 review), so
    the model reads which agent to dispatch instead of guessing it from the ID."""
    open_q = [q for q in questions if q.status == QuestionStatus.OPEN]
    return [
        {
            "rank": h.rank,
            "component_ids": list(h.component_ids),
            "cause_id": h.cause_id,
            "open_question_ids": {
                agent.value: _listing(ids, limit)
                for agent, ids in sorted(
                    by_agent([q for q in open_q if q.id in set(h.question_ids)], sections).items()
                )
            },
            "supported": bool(support(h, findings, questions, sections.values())),
        }
        for h in sorted(hypotheses, key=lambda h: (h.rank, h.id))
    ]


def _listing(ids: list[str], limit: int) -> dict[str, Any]:
    return {"count": len(ids), "ids": ids[:limit]}


def _result_line(step: AgentStep, calls: Mapping[str, ToolCall]) -> str:
    call = next((c for c in calls.values() if c.agent_step_id == step.id), None)
    if call is None:
        return ""
    if call.refused_reason is not None:
        return f"refused: {call.refused_reason}"
    summary = call.result.get("summary") if isinstance(call.result, dict) else None
    return str(summary or "")


def build_view(
    run: Run,
    *,
    questions: Sequence[Question],
    findings: Sequence[Finding],
    steps: Sequence[AgentStep],
    tool_calls: Sequence[ToolCall],
    sections: Mapping[str, Section],
    caps: RunCaps,
    limit_usd: float,
    hypotheses: Sequence[Hypothesis] = (),
) -> dict[str, Any]:
    """`limit_usd` is what the analysis may spend: the cap minus the computed severity reserve."""
    view_caps = caps.orchestrator_view
    lines, failed = coverage(list(sections.values()), list(questions), findings)
    open_q = [q for q in questions if q.status == QuestionStatus.OPEN]
    retry = [q for q in open_q if q.attempts > 0]
    unsure = unsure_question_ids(questions, findings)
    per_section = []
    for section_id in sorted(sections):
        mine = [q for q in questions if q.section_id == section_id]
        if mine:
            done = sum(
                1
                for q in mine
                if q.status in (QuestionStatus.ANSWERED, QuestionStatus.NOT_CREDIBLE)
            )
            per_section.append({"section_id": section_id, "total": len(mine), "checked": done})
    orchestrator_steps = [s for s in steps if s.agent == Agent.ORCHESTRATOR]
    calls = {c.id: c for c in tool_calls}
    recent = [
        {"tool": s.tool.value, "reason": s.reason, "result": _result_line(s, calls)}
        for s in orchestrator_steps[-view_caps.recent_steps :]
    ]
    return {
        "coverage": [line.model_dump() for line in lines],
        "sections": per_section,
        "open": {
            agent.value: _listing(ids, view_caps.dispatch_max_question_ids)
            for agent, ids in sorted(by_agent(open_q, sections).items())
        },
        "retry_at_hard": {
            agent.value: _listing(ids, view_caps.id_list_max)
            for agent, ids in sorted(by_agent(retry, sections).items())
        },
        "failed": _listing(failed, view_caps.id_list_max),
        "unsure": _listing(unsure, view_caps.id_list_max),
        "recent_steps": recent,
        "steps_left": caps.orchestrator_max_steps - len(orchestrator_steps),
        "spend": {
            # what counts against the cap, so a cache replay sees what the original saw (R45)
            "cap_spent_usd": round(run.cap_spent_usd, 6),
            "limit_usd": round(limit_usd, 6),
        },
        "unsure_reanswers_left": max(0, caps.unsure_reanswers_per_run - reanswers_used(findings)),
        "priority": _priority(hypotheses, questions, findings, sections, view_caps.id_list_max),
    }
