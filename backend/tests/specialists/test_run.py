"""Running a specialist batch through the fake gateway (spec 2.4; plan R4, R34, R40, R43)."""

import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.client import Gateway, RunBudget
from guideword.gateway.estimate import estimate_cost
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
    with runs.step(run.id) as writer:
        apply_batch(writer, out)
    # a second answer giving the same findings stores each finding once (R42)
    again = replace(out, model_calls=[], steps=[], cost_usd=0.0, cap_cost_usd=0.0)
    with runs.step(run.id) as writer:
        apply_batch(writer, again)
    assert len(runs.findings(run.id)) == len(MX)
    stored = {q.id: q for q in runs.questions(run.id)}
    assert {stored[q].status for q in MX} == {QuestionStatus.ANSWERED}
    assert len(runs.model_calls(run.id)) == 1
    assert runs.get(run.id).spent_usd == pytest.approx(out.cost_usd)  # type: ignore[union-attr]
    # the same call record again is refused, not overwritten (case D dev run)
    with pytest.raises(ValueError, match="already recorded"), runs.step(run.id) as writer:
        apply_batch(writer, out)
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


def test_the_request_lists_only_causes_the_context_can_support(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    """R46: the causes sent are those valid for the batch whose type fits an ID in its context."""
    import re  # noqa: PLC0415

    from guideword.specialists.causes import can_fail_as, valid_cause_ids  # noqa: PLC0415
    from guideword.specialists.context import build_context  # noqa: PLC0415

    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    _run(gateway, world, ref, config, Agent.PROCESS, MX)
    text = transport.sent[0][1]["messages"][0]["content"]
    match = re.search(r"<causes>\s*(.*?)\s*</causes>", text, re.S)
    assert match is not None
    sent = {c["id"] for c in json.loads(match.group(1))}
    plant, sections, questions = world
    batch = [questions[q] for q in MX]
    context = build_context(Agent.PROCESS, plant, sections, batch)
    valid = set().union(*(valid_cause_ids(q, sections, plant, ref) for q in batch))
    types = {c.id: c.failing_component_type for c in ref.causes}
    assert sent == {c for c in valid if can_fail_as(types[c], context, plant)}
    assert "C10" not in sent and "C01" in sent


# --- R13 as amended: per-batch slices ---------------------------------------------------------


def test_the_slice_is_the_worst_case_of_the_batch_from_its_request_alone(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    """Answer plus one validation retry (tool agents also every allowed tool request), each at
    the agreed estimate with max_tokens, later calls re-sending the earlier output."""
    from guideword.specialists.run import batch_slice_usd, prepare_batch  # noqa: PLC0415

    gateway, transport = build(lambda job, r: answers(batch_ids(r)))
    plant, sections, questions = world
    batch = [questions[q] for q in MX]
    prepared = prepare_batch(
        gateway,
        plant=plant,
        ref=ref,
        config=config,
        sections=sections,
        questions=batch,
        agent=Agent.PROCESS,
        ai_remaining=20,
        level="bulk",
    )
    assert not isinstance(prepared, BatchOutcome)
    max_tokens = config.caps.run.max_tokens["specialist_bulk"]
    prices = config.models.tiers[Tier.LIGHTNING]
    first = estimate_cost(prices, prepared.conversation, None, max_tokens)
    retry_input = first.input_tokens + max_tokens
    retry = (
        retry_input * prices.input_usd_per_1m + max_tokens * prices.output_usd_per_1m
    ) / 1_000_000
    assert batch_slice_usd(prepared, config) == pytest.approx(first.cost_usd + retry)
    assert transport.sent == []  # computed from the request, nothing sent


def test_a_batch_that_uses_up_its_slice_fails_without_stopping_the_run(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: reply("not the schema"))
    plant, sections, questions = world
    max_tokens = config.caps.run.max_tokens["specialist_bulk"]
    prices = config.models.tiers[Tier.LIGHTNING]
    # room for the first call only: the validation retry is refused by the slice
    from guideword.specialists.run import prepare_batch  # noqa: PLC0415

    prepared = prepare_batch(
        gateway,
        plant=plant,
        ref=ref,
        config=config,
        sections=sections,
        questions=[questions[q] for q in MX],
        agent=Agent.PROCESS,
        ai_remaining=20,
        level="bulk",
    )
    assert not isinstance(prepared, BatchOutcome)
    # exactly the first call: the retry, which re-sends the answer and the error, cannot fit
    limit = estimate_cost(prices, prepared.conversation, None, max_tokens).cost_usd
    out = _run(
        gateway,
        world,
        ref,
        config,
        Agent.PROCESS,
        MX,
        budget=RunBudget(RUN, 0.0, limit, slice_id="b0"),
    )
    assert out.status == "failed" and "slice" in (out.error or "")
    assert len(transport.sent) == 1


def test_a_tool_agents_slice_is_the_two_tool_path_calls_and_one_retry(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    from guideword.specialists.run import batch_slice_usd, prepare_batch  # noqa: PLC0415

    gateway, _ = build(lambda job, r: answers(batch_ids(r)))
    plant, sections, questions = world
    prepared = prepare_batch(
        gateway,
        plant=plant,
        ref=ref,
        config=config,
        sections=sections,
        questions=[questions["pair:KOH:SIH"]],
        agent=Agent.CHEMISTRY,
        ai_remaining=0,
        level="bulk",
    )
    assert not isinstance(prepared, BatchOutcome) and prepared.tools
    max_tokens = config.caps.run.max_tokens["specialist_bulk"]
    prices = config.models.tiers[Tier.LIGHTNING]
    first = estimate_cost(prices, prepared.conversation, prepared.tools, max_tokens)
    total = sum(
        (
            (first.input_tokens + k * max_tokens) * prices.input_usd_per_1m
            + max_tokens * prices.output_usd_per_1m
        )
        / 1_000_000
        for k in range(3)
    )
    assert batch_slice_usd(prepared, config) == pytest.approx(total)


# --- demo-fixes plan (approved 2026-10-21): a failed batch re-asked one question at a time -------

MX3 = ["m:S-MX-1:more:pressure", "m:S-MX-1:less:pressure", "m:S-MX-1:more:temperature"]


def test_a_cut_off_batch_is_re_asked_one_question_at_a_time(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    def script(job: str, request: dict[str, Any]) -> Any:
        asked = batch_ids(request)
        if len(asked) > 1:
            return reply('{"answers": [', finish_reason="length")
        return answers(asked)

    gateway, transport = build(script)
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX3, retry_singly=True)
    assert out.status == "answered"
    assert [batch_ids(r) for _, r in transport.sent] == [MX3, *([q] for q in MX3)]
    assert sorted(f.question_id for f in out.findings) == sorted(MX3)
    assert all(q.status == QuestionStatus.ANSWERED for q in out.questions)
    # the batch and its single call together count one attempt for each question
    assert {q.attempts for q in out.questions} == {1}


@pytest.mark.parametrize("bad", ["twice", "not_sent"])
def test_a_batch_answering_a_question_twice_or_one_not_sent_is_re_asked_singly(
    bad: str, build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    def script(job: str, request: dict[str, Any]) -> Any:
        asked = batch_ids(request)
        if len(asked) == 1:
            return answers(asked)
        extra = [asked[0]] if bad == "twice" else ["m:S-MX-1:no:mixing"]
        return answers([*asked, *extra])

    gateway, transport = build(script)
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX3, retry_singly=True)
    assert out.status == "answered"
    singles = [batch_ids(r) for _, r in transport.sent if len(batch_ids(r)) == 1]
    assert singles == [[q] for q in MX3]
    assert all(q.status == QuestionStatus.ANSWERED for q in out.questions)


def test_other_invalid_answers_still_fail_the_batch_as_before(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: reply("not json"))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX3, retry_singly=True)
    assert out.status == "failed"
    assert all(len(batch_ids(r)) == 3 for _, r in transport.sent)  # no single-question call


def test_the_single_retry_is_off_unless_asked_for(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    """Runs whose stored caps lack `retry_failed_batch_singly` keep today's behaviour."""
    gateway, transport = build(lambda job, r: reply("{", finish_reason="length"))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX3)
    assert out.status == "failed" and "cut off" in (out.error or "")
    assert len(transport.sent) == 1


def test_a_question_whose_single_call_also_fails_counts_one_attempt(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    gateway, transport = build(lambda job, r: reply("{", finish_reason="length"))
    out = _run(gateway, world, ref, config, Agent.PROCESS, MX3, retry_singly=True)
    assert out.status == "failed"
    assert len(transport.sent) == 1 + len(MX3)
    assert {(q.status, q.attempts) for q in out.questions} == {(QuestionStatus.OPEN, 1)}


def test_new_runs_store_the_single_retry_cap_and_d_to_g_do_not(config: Config) -> None:
    from guideword.runs.case import run_settings  # noqa: PLC0415

    assert run_settings(config).caps["retry_failed_batch_singly"] is True
    stored = json.loads(
        (REPO / "backend" / "tests" / "runs" / "fixtures" / "dev_run_inputs.json").read_text(
            encoding="utf-8"
        )
    )["runs"]
    assert all("retry_failed_batch_singly" not in r["inputs"]["caps"] for r in stored.values())


def test_a_refused_retry_keeps_the_first_attempts_record_and_cost(
    build: Any, world: Any, ref: ReferenceSet, config: Config
) -> None:
    """Bug fix (2026-10-22): the first attempt was invalid and paid; the slice refused the
    validation retry. The first attempt's record and cost stay on the outcome, so the run's
    spend matches the ledger for that call (the WG final run lost $0.0083 this way)."""
    from guideword.specialists.run import prepare_batch  # noqa: PLC0415

    gateway, transport = build(lambda job, r: reply("not the schema"))
    plant, sections, questions = world
    max_tokens = config.caps.run.max_tokens["specialist_bulk"]
    prices = config.models.tiers[Tier.LIGHTNING]
    prepared = prepare_batch(
        gateway,
        plant=plant,
        ref=ref,
        config=config,
        sections=sections,
        questions=[questions[q] for q in MX],
        agent=Agent.PROCESS,
        ai_remaining=20,
        level="bulk",
    )
    assert not isinstance(prepared, BatchOutcome)
    limit = estimate_cost(prices, prepared.conversation, None, max_tokens).cost_usd
    out = _run(
        gateway,
        world,
        ref,
        config,
        Agent.PROCESS,
        MX,
        budget=RunBudget(RUN, 0.0, limit, slice_id="b0"),
    )
    assert out.status == "failed" and len(transport.sent) == 1
    assert [c.outcome for c in out.model_calls] == ["invalid"]
    paid = gateway._ledger.entries()  # noqa: SLF001 - the ledger line the call wrote
    assert len(paid) == 1
    assert paid[0].cost_usd > 0
    assert out.cost_usd == pytest.approx(paid[0].cost_usd)
    assert out.model_calls[0].cost_usd == pytest.approx(paid[0].cost_usd)
