"""Batching a specialist's questions (spec 2.4): one section, or one chunk of a plant-wide
list, per batch; never two agents; ordered by question ID so batches are deterministic."""

from collections.abc import Mapping, Sequence

from guideword.schema.records import Question, Section
from guideword.specialists.routing import agent_for


def batches(
    questions: Sequence[Question], sections: Mapping[str, Section], size: int
) -> list[list[Question]]:
    if size < 1:
        raise ValueError("a batch holds at least one question")
    agents = {agent_for(q, sections) for q in questions}
    if len(agents) > 1:
        raise ValueError(f"a batch is for one agent, not {sorted(agents)}")
    groups: dict[str, list[Question]] = {}
    for question in sorted(questions, key=lambda q: q.id):
        # pair and environment questions have no section: they form one plant-wide list
        groups.setdefault(question.section_id or "", []).append(question)
    out: list[list[Question]] = []
    for key in sorted(groups):
        group = groups[key]
        out += [group[i : i + size] for i in range(0, len(group), size)]
    return out
