"""Running a specialist batch through the fake gateway (spec 2.4; plan R4, R34, R40, R43)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.client import Gateway, RunBudget
from guideword.gateway.fake import FakeTransport, fake_gateway, reply
from guideword.gateway.transport import ToolCallRequest
from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.schema.enums import (
    Agent,
    AgentTool,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.run import BatchOutcome, run_batch

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
_QUESTIONS = re.compile(r"<questions>\s*(.*?)\s*</questions>", re.S)


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture(scope="module")
def world(ref: ReferenceSet) -> tuple[Plant, dict[str, Section], dict[str, Question]]:
    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    sections = rule_cut(plant, "plant:x:0")
    return (
        plant,
        {s.id: s for s in sections},
        {q.id: q for q in build_questions(plant, sections, ref, RUN)},
    )


def batch_ids(request: dict[str, Any]) -> list[str]:
    """The question IDs a request's system prompt asks about."""
    system = request["messages"][0]["content"]
    match = _QUESTIONS.search(system)
    assert match is not None
    return [q["id"] for q in json.loads(match.group(1))]


def finding(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cause_id": "C01",
        "cause_text": None,
        "failing_component_type": "control_loop",
        "failing_component_ids": ["TIC-1"],
        "consequence": "steam keeps heating the mixer",
        "safeguard_ids": ["SG-TRIP"],
        "adequacy": "unknown",
        "confidence": "sure",
        "reason": "TV-1 fails open",
    }
    base.update(changes)
    return base


def answers(ids: list[str], make: Any = None, added: list[dict[str, Any]] | None = None) -> Any:
    def one(qid: str) -> dict[str, Any]:
        if make is not None:
            return make(qid)
        return {"question_id": qid, "not_credible": None, "findings": [finding()]}

    return reply({"answers": [one(q) for q in ids], "added_questions": added or []})


@pytest.fixture
def build(config: Config, tmp_path: Path) -> Any:
    def _build(script: Any) -> tuple[Gateway, FakeTransport]:
        sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        return fake_gateway(
            config, script, sessions=sessions, ledger_path=tmp_path / "l.jsonl", clock=lambda: NOW
        )

    return _build


def _run(
    gateway: Gateway,
    world: Any,
    ref: ReferenceSet,
    config: Config,
    agent: Agent,
    qids: list[str],
    **kw: Any,
) -> BatchOutcome:
    plant, sections, questions = world
    args: dict[str, Any] = {
        "plant": plant,
        "ref": ref,
        "config": config,
        "sections": sections,
        "questions": [questions[q] for q in qids],
        "agent": agent,
        "budget": RunBudget(RUN, 0.0, 1.0),
        "previous_step_id": "step:0000000000000000",
        "ai_remaining": 20,
        "existing_question_ids": set(questions),
    }
    args.update(kw)
    return run_batch(gateway, **args)


MX = ["m:S-MX-1:more:pressure", "m:S-MX-1:less:pressure"]


def test_a_batch_answer_becomes_findings_with_code_built_ids(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX)
    assert out.status == "answered"
    assert [f.question_id for f in out.findings] == MX
    assert all(f.id.startswith(f"f:{f.question_id}:lightning:C01:") for f in out.findings)
    assert all(f.tier == Tier.LIGHTNING and f.run_id == RUN for f in out.findings)
    assert {q.status for q in out.questions} == {QuestionStatus.ANSWERED}
    assert [s.tool for s in out.steps] == [AgentTool.ANSWER]
    assert out.steps[0].previous_id == "step:0000000000000000"
    assert len(out.model_calls) == 1 and out.findings[0].model_call_id == out.model_calls[0].id
    assert transport.sent[0][0] == "specialist_bulk"


def test_the_level_picks_the_job(build: Any, world: Any, ref: ReferenceSet, config: Config) -> None:
    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1], level="hard")
    assert transport.sent[0][0] == "specialist_hard"
    assert out.findings[0].tier == Tier.SUPER


def test_not_credible_sets_status_and_reason_no_finding(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    def make(qid: str) -> dict[str, Any]:
        return {
            "question_id": qid,
            "not_credible": {"reason": "vented to atmosphere"},
            "findings": [],
        }

    gateway, _ = build(lambda job, r: answers(batch_ids(r), make))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert out.findings == []
    [question] = out.questions
    assert (question.status, question.not_credible_reason) == (
        QuestionStatus.NOT_CREDIBLE,
        "vented to atmosphere",
    )
    assert question.model_call_id == out.model_calls[0].id


def test_missing_question_id_retried_alone(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    sent: list[list[str]] = []

    def script(job: str, request: dict[str, Any]) -> Any:
        asked = batch_ids(request)
        sent.append(asked)
        return answers(asked[:1])  # answers only the first question it is asked

    gateway, _ = build(script)
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX)
    assert sent == [MX, [MX[1]]]
    assert sorted(f.question_id for f in out.findings) == sorted(MX)


def test_an_invalid_answer_counts_an_attempt_and_two_fail_the_question(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    plant, sections, questions = world
    gateway, transport = build(lambda job, r: reply("not json"))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert out.status == "failed"
    assert len(transport.sent) == 2  # the gateway's one retry with the error
    [once] = out.questions
    assert (once.status, once.attempts) == (QuestionStatus.OPEN, 1)
    again = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1], questions=[once])
    assert (again.questions[0].status, again.questions[0].attempts) == (QuestionStatus.FAILED, 2)


def test_duplicate_or_unknown_question_id_invalid(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, _ = build(lambda job, r: answers(["m:S-MX-1:no:mixing"]))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert out.status == "failed"
    assert "not in this batch" in (out.error or "")


def test_finding_ids_built_by_code(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    from guideword.schema import ids  # noqa: PLC0415

    gateway, _ = build(lambda job, r: answers(batch_ids(r)))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert out.findings[0].id == ids.finding_id(MX[0], "lightning", ["TIC-1"], cause_id="C01")


# --- chemistry: the two-call tool path (R34) ---------------------------------------------------


PAIR = ["pair:KOH:SIH"]
LOOKUP = ToolCallRequest("c1", "reactivity_lookup", '{"chemical_a": "SIH", "chemical_b": "KOH"}')


def _chem_answer(qid: str) -> dict[str, Any]:
    return {
        "question_id": qid,
        "not_credible": None,
        "findings": [
            finding(
                cause_id="C14",
                failing_component_type="operator",
                failing_component_ids=["P-CHARGE-1"],
                safeguard_ids=[],
                consequence="flammable and toxic gas in MX-1",
            )
        ],
    }


def test_chemistry_tool_call_runs_result_returned_then_answer(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    def script(job: str, request: dict[str, Any]) -> Any:
        has_result = any(m.get("role") == "tool" for m in request["messages"])
        if "tools" in request:
            assert "response_format" not in request  # tools_with_schema is false
            return reply("no more tools") if has_result else reply(tool_calls=(LOOKUP,))
        assert has_result
        return answers(batch_ids(request), _chem_answer)

    gateway, transport = build(script)
    out = _run(gateway, world, ref, config, Agent.CHEMISTRY, PAIR)
    assert out.status == "answered"
    [tool] = out.tool_calls
    assert (tool.tool, tool.refused_reason) == ("reactivity_lookup", None)
    assert any(p["status"] == "listed" for p in tool.result["pairs"])
    assert [s.tool for s in out.steps] == [AgentTool.REACTIVITY_LOOKUP, AgentTool.ANSWER]
    assert tool.agent_step_id == out.steps[0].id
    assert out.steps[1].previous_id == out.steps[0].id
    tool_message = next(m for m in transport.sent[1][1]["messages"] if m.get("role") == "tool")
    assert "GF" in tool_message["content"]
    assert len(transport.sent) == 3


def test_third_tool_call_refused(build: Any, world: Any, ref: ReferenceSet, config: Config) -> None:
    def script(job: str, request: dict[str, Any]) -> Any:
        if "tools" in request:
            return reply(tool_calls=(LOOKUP,))  # always wants another lookup
        return answers(batch_ids(request), _chem_answer)

    gateway, _ = build(script)
    out = _run(gateway, world, ref, config, Agent.CHEMISTRY, PAIR)
    assert [t.refused_reason is None for t in out.tool_calls] == [True, True, False]
    assert "at most 2" in (out.tool_calls[2].refused_reason or "")
    assert out.status == "answered"


def test_other_agents_get_no_tools(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert all("tools" not in r for _, r in transport.sent)


# --- added questions --------------------------------------------------------------------------


def test_added_questions_get_ai_ids_join_open_stop_at_run_cap(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    added = [
        {"section_id": "S-MX-1", "text": f"What if the steam trap {n} sticks?"} for n in range(2)
    ]
    gateway, _ = build(lambda job, r: answers(batch_ids(r), added=added))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1], ai_remaining=1)
    [question] = out.added
    assert question.id.startswith("ai:S-MX-1:")
    assert (question.kind, question.origin, question.status) == (
        QuestionKind.ADDED_BY_AI,
        QuestionOrigin.ADDED_BY_AI,
        QuestionStatus.OPEN,
    )
    assert question.model_call_id == out.model_calls[-1].id


def test_added_questions_stop_at_the_batch_cap(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    added = [{"section_id": "S-MX-1", "text": f"Question {n}"} for n in range(5)]
    gateway, _ = build(lambda job, r: answers(batch_ids(r), added=added))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX[:1])
    assert len(out.added) == config.caps.run.ai_questions_per_batch


# --- writing a batch into the run --------------------------------------------------------------


def test_apply_batch_writes_every_record_with_its_event(
    build: Any, ref: ReferenceSet, config: Config, tmp_path: Path
) -> None:
    from guideword.runs.plants import PlantRepository, load_plant, plant_facts  # noqa: PLC0415
    from guideword.runs.start import RunSettings, start_run  # noqa: PLC0415
    from guideword.runs.store import RunRepository  # noqa: PLC0415
    from guideword.schema.enums import EventType  # noqa: PLC0415
    from guideword.specialists.run import apply_batch  # noqa: PLC0415

    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'run.db').as_posix()}")
    plants, runs = PlantRepository(sessions), RunRepository(sessions, lambda: NOW)
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    record, _ = load_plant(raw, ref)
    assert record is not None
    plants.add(record, raw, plant_facts(record.plant_file, record.id))
    plants.confirm(record.id, rule_cut(record.plant_file, record.id))
    settings = RunSettings(
        dict(config.routing.jobs), config.caps.run_input_caps(), dict(config.routing.prompts)
    )
    run = start_run(
        plants, runs, ref, settings, plant_record_id=record.id, spend_cap_usd=1.0, mode="full"
    )
    sections = {s.id: s for s in runs.sections(run.id)}
    questions = {q.id: q for q in runs.questions(run.id)}

    gateway, _ = build(lambda job, r: answers(batch_ids(r)))
    out = run_batch(
        gateway,
        plant=record.plant_file,
        ref=ref,
        config=config,
        sections=sections,
        questions=[questions[q] for q in MX],
        agent=Agent.PROCESS,
        budget=RunBudget(run.id, 0.0, 1.0),
        previous_step_id=run.id,
        ai_remaining=20,
        existing_question_ids=set(questions),
    )
    for _ in range(2):  # applying the same outcome twice stores each finding once (R42)
        with runs.step(run.id) as writer:
            apply_batch(writer, out)
    assert len(runs.findings(run.id)) == len(MX)
    stored = {q.id: q for q in runs.questions(run.id)}
    assert {stored[q].status for q in MX} == {QuestionStatus.ANSWERED}
    assert len(runs.model_calls(run.id)) == 1
    assert runs.get(run.id).spent_usd == pytest.approx(2 * out.cost_usd)  # type: ignore[union-attr]
    types = [e.type for e in runs.events(run.id)]
    assert (
        EventType.FINDING_ADDED in types
        and EventType.MODEL_CALL in types
        and EventType.AGENT_DECISION in types
    )


# --- R43 -----------------------------------------------------------------------------------


def test_batch_over_the_cap_fails_without_a_call(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    tight = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={
                    "run": config.caps.run.model_copy(update={"specialist_max_input_tokens": 50})
                }
            )
        }
    )
    out = _run(gateway, world, ref, tight, Agent.PROCESS, MX[:1])
    assert out.status == "failed"
    assert "specialist_max_input_tokens" in (out.error or "")
    assert transport.sent == []
    assert out.questions[0].attempts == 1
