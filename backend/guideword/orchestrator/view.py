"""What the orchestrator sees each step (spec 2.5; plan R18, R44): built by code.

Coverage per list and per section; the open question IDs grouped by agent (up to
`dispatch_max_question_ids` per agent); the questions to retry at level `hard`, the failed
and the unsure ones (up to `id_list_max`); the last few steps' one-line results; and the
steps and spend left. Never a finding's consequence or cause text, nor the findings list.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from guideword.config import RunCaps
from guideword.questions.coverage import coverage
from guideword.schema.enums import Agent, Confidence, QuestionStatus, Tier
from guideword.schema.records import AgentStep, Finding, Question, Run, Section, ToolCall
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
) -> dict[str, Any]:
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
            "spent_usd": round(run.spent_usd, 6),
            "limit_usd": round(run.spend_cap_usd - caps.severity_reserve_usd, 6),
        },
        "unsure_reanswers_left": max(0, caps.unsure_reanswers_per_run - reanswers_used(findings)),
    }
