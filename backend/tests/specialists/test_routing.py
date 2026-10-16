"""Which agent answers which question, and how questions are batched (spec 2.4)."""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import Agent, QuestionKind, QuestionOrigin, QuestionStatus
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.batch import batches
from guideword.specialists.routing import agent_for

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def built(ref: ReferenceSet) -> tuple[dict[str, Section], list[Question]]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["lines"][0]["no_flow"] = ["standby"]
    data["chemicals"].append({"id": "FLOUR", "name": "flour", "combustible_dust": True})
    data["equipment"].append(
        {"id": "D-1", "type": "dryer", "location_id": "BLDG-1", "contents": ["FLOUR"]}
    )
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, "plant:x:0")
    return {s.id: s for s in sections}, build_questions(plant, sections, ref, RUN)


EXPECTED = {
    QuestionKind.MATRIX: Agent.PROCESS,
    QuestionKind.RELIEF_DISCHARGE: Agent.PROCESS,
    QuestionKind.CHEMICAL_PAIR: Agent.CHEMISTRY,
    QuestionKind.CHEMICAL_ENVIRONMENT: Agent.CHEMISTRY,
    QuestionKind.NO_FLOW_LINE: Agent.PIPING,
    QuestionKind.PROCEDURE_STEP: Agent.PROCEDURES,
    QuestionKind.PLANNED_WORK: Agent.MAINTENANCE,
    QuestionKind.DUST: Agent.DUST,
}


def test_routing_every_kind_reaches_its_agent(
    built: tuple[dict[str, Section], list[Question]],
) -> None:
    sections, questions = built
    seen = {}
    for q in questions:
        seen[q.kind] = agent_for(q, sections)
    assert seen == EXPECTED


def _added(kind: QuestionKind, section_id: str) -> Question:
    origin = (
        QuestionOrigin.ADDED_BY_AI if kind == QuestionKind.ADDED_BY_AI else QuestionOrigin.ENGINEER
    )
    make = (
        ids.added_by_ai_question_id
        if kind == QuestionKind.ADDED_BY_AI
        else ids.engineer_question_id
    )
    return Question(
        id=make(section_id, "what if"),
        run_id=RUN,
        kind=kind,
        origin=origin,
        status=QuestionStatus.OPEN,
        section_id=section_id,
        text="what if",
    )


@pytest.mark.parametrize(
    ("section_id", "agent"),
    [
        ("S-MX-1", Agent.PROCESS),
        ("S-L-STM", Agent.PROCESS),
        ("S-L-12", Agent.PIPING),
        ("S-P-CHARGE", Agent.PROCEDURES),
        ("S-W-1", Agent.MAINTENANCE),
    ],
)
@pytest.mark.parametrize("kind", [QuestionKind.ADDED_BY_AI, QuestionKind.ENGINEER])
def test_added_and_engineer_questions_go_by_their_section_kind(
    built: tuple[dict[str, Section], list[Question]],
    section_id: str,
    agent: Agent,
    kind: QuestionKind,
) -> None:
    sections, _ = built
    assert agent_for(_added(kind, section_id), sections) == agent


def test_a_batch_never_mixes_agents_or_sections(
    built: tuple[dict[str, Section], list[Question]],
) -> None:
    sections, questions = built
    for agent in set(EXPECTED.values()):
        mine = [q for q in questions if agent_for(q, sections) == agent]
        for batch in batches(mine, sections, size=4):
            assert len(batch) <= 4
            assert {agent_for(q, sections) for q in batch} == {agent}
            assert len({q.section_id for q in batch}) == 1


def test_batches_cover_every_question_once_in_id_order(
    built: tuple[dict[str, Section], list[Question]],
) -> None:
    sections, questions = built
    process = [q for q in questions if agent_for(q, sections) == Agent.PROCESS]
    out = batches(list(reversed(process)), sections, size=5)
    flat = [q.id for b in out for q in b]
    assert sorted(flat) == sorted(q.id for q in process)
    assert len(flat) == len(set(flat))
    for batch in out:
        assert [q.id for q in batch] == sorted(q.id for q in batch)


def test_batches_refuse_mixed_agents(built: tuple[dict[str, Section], list[Question]]) -> None:
    sections, questions = built
    mixed = [
        next(q for q in questions if q.kind == k)
        for k in (QuestionKind.MATRIX, QuestionKind.CHEMICAL_PAIR)
    ]
    with pytest.raises(ValueError, match="one agent"):
        batches(mixed, sections, size=10)


def test_batches_keep_the_given_order_when_asked(
    built: tuple[dict[str, Section], list[Question]],
) -> None:
    """A priority dispatch (spec 2b.3) keeps its order through batching, so admission reaches
    the linked questions first: groups in order of first appearance, members in input order.
    The same sections and sizes as without it."""
    sections, questions = built
    process = sorted(
        (q for q in questions if agent_for(q, sections) == Agent.PROCESS), key=lambda q: q.id
    )
    given = [process[-1], *process[:-1]]
    out = batches(given, sections, size=5, keep_order=True)
    flat = [q.id for b in out for q in b]
    assert flat[0] == process[-1].id
    assert sorted(flat) == sorted(q.id for q in process) and len(flat) == len(set(flat))
    for batch in out:
        assert len(batch) <= 5 and len({q.section_id for q in batch}) == 1
        assert [q.id for q in batch] == [q.id for q in given if q in batch]
    assert sorted(map(len, out)) == sorted(map(len, batches(given, sections, size=5)))
