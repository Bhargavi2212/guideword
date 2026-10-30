"""Which specialist answers which question (spec 2.4): fixed by code, never by a model."""

from collections.abc import Mapping

from guideword.schema.enums import Agent, QuestionKind, SectionKind
from guideword.schema.records import Question, Section

BY_KIND: dict[QuestionKind, Agent] = {
    QuestionKind.MATRIX: Agent.PROCESS,
    QuestionKind.RELIEF_DISCHARGE: Agent.PROCESS,
    QuestionKind.CHEMICAL_PAIR: Agent.CHEMISTRY,
    QuestionKind.CHEMICAL_ENVIRONMENT: Agent.CHEMISTRY,
    QuestionKind.NO_FLOW_LINE: Agent.PIPING,
    QuestionKind.PROCEDURE_STEP: Agent.PROCEDURES,
    QuestionKind.PLANNED_WORK: Agent.MAINTENANCE,
    # Phase 9 (spec 9.2): a change is management-of-change work
    QuestionKind.CHANGE: Agent.MAINTENANCE,
    QuestionKind.DUST: Agent.DUST,
}

# added-by-AI and engineer questions go to the agent of their section's kind
BY_SECTION_KIND: dict[SectionKind, Agent] = {
    SectionKind.EQUIPMENT: Agent.PROCESS,
    SectionKind.LINE: Agent.PROCESS,
    SectionKind.NO_FLOW_LINE: Agent.PIPING,
    SectionKind.PROCEDURE: Agent.PROCEDURES,
    SectionKind.PLANNED_WORK: Agent.MAINTENANCE,
}

SPECIALISTS = (
    Agent.PROCESS,
    Agent.CHEMISTRY,
    Agent.PIPING,
    Agent.PROCEDURES,
    Agent.MAINTENANCE,
    Agent.DUST,
)


def agent_for(question: Question, sections: Mapping[str, Section]) -> Agent:
    agent = BY_KIND.get(question.kind)
    if agent is not None:
        return agent
    if question.section_id is None or question.section_id not in sections:
        raise ValueError(f"{question.id} names no section of this run")
    return BY_SECTION_KIND[sections[question.section_id].kind]
