"""The run state machine and its event log (spec 2.1; plan R24, R32)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from guideword.reference import ReferenceSet
from guideword.runs.db import make_session_factory
from guideword.runs.machine import Stepper, StepResult, advance, cancel
from guideword.runs.plants import PlantRepository
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import EMITTED_EVENT_TYPES, RunRepository, StepWriter
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Agent,
    AgentTool,
    BudgetUse,
    Confidence,
    EventType,
    FailingComponentType,
    QuestionStatus,
    RunStatus,
    Tier,
)
from guideword.schema.records import AgentStep, Finding, ModelCall, Run, ToolCall

Upload = Callable[..., str]
# Phase 3 emits chain_added, lopa_done and run_extended with its post-analysis steps (plan
# G11); evidence_added comes with the Phase 4 tools
# Phase 4 emits evidence_added (plan PR 5b); no event type is left for a later phase
LATER_PHASE_EVENTS: set[EventType] = set()


def past_screen(runs: RunRepository, run: Run) -> Run:
    """Harnesses that test later steps start where runs started before R50: a new run's
    plant_screen step is skipped (it is tested in tests/screen)."""
    if run.step != "plant_screen":
        return run
    with runs.step(run.id) as writer:
        writer.set_step("analysis")
    moved = runs.get(run.id)
    assert moved is not None
    return moved


@pytest.fixture
def run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> Run:
    run = start_run(
        plants,
        runs,
        ref,
        settings,
        plant_record_id=upload(),
        spend_cap_usd=1.0,
        mode="full",
        use=BudgetUse.DEVELOPMENT,
        post_spend_cap_usd=0.0,
    )
    return past_screen(runs, run)


def _finding(run: Run, question_id: str) -> Finding:
    return Finding(
        id=ids.finding_id(question_id, "lightning", ["P-1"], cause_id="C04"),
        run_id=run.id,
        question_id=question_id,
        tier=Tier.LIGHTNING,
        cause_id="C04",
        failing_component_type=FailingComponentType.PUMP,
        failing_component_ids=["P-1"],
        consequence="no flow to the mixer",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
    )


def _records(run: Run) -> tuple[AgentStep, ModelCall, ToolCall]:
    step = AgentStep(
        id=ids.agent_step_id(run.id, "orchestrator", "check_coverage", {}),
        run_id=run.id,
        previous_id=run.id,
        agent=Agent.ORCHESTRATOR,
        tool=AgentTool.CHECK_COVERAGE,
        arguments={},
        reason="see what is open",
    )
    call = ModelCall(
        id=ids.model_call_id("m", "v1", ["x"]),
        run_id=run.id,
        model_id="m",
        prompt_version="v1",
        job="orchestrator",
        cache_hit=False,
        outcome="ok",
        input_tokens=10,
        output_tokens=5,
        latency_ms=1.0,
        cost_usd=0.001,
        raw_response="{}",
    )
    tool = ToolCall(
        id=ids.tool_call_id(step.id, "check_coverage", {}),
        run_id=run.id,
        agent_step_id=step.id,
        tool="check_coverage",
        arguments={},
        result={"open": 98},
    )
    return step, call, tool


def test_advance_runs_one_step_and_saves_everything(runs: RunRepository, run: Run) -> None:
    question = runs.questions(run.id)[0]

    def stepper(current: Run, writer: StepWriter) -> StepResult:
        writer.add_finding(_finding(current, question.id))
        writer.put_question(question.model_copy(update={"status": QuestionStatus.ANSWERED}))
        return StepResult()

    assert advance(runs, run.id, {"analysis": stepper}) == RunStatus.RUNNING
    assert [f.question_id for f in runs.findings(run.id)] == [question.id]
    assert runs.questions(run.id)[0].status == QuestionStatus.ANSWERED
    assert [e.type for e in runs.events(run.id)] == [
        EventType.RUN_STARTED,
        EventType.STEP_STARTED,
        EventType.FINDING_ADDED,
        EventType.STEP_FINISHED,
    ]


def test_advance_after_a_crash_continues_from_the_saved_step(
    runs: RunRepository, run: Run, db_url: str
) -> None:
    """A step that fails saves nothing; a fresh process on the same file redoes it."""
    question = runs.questions(run.id)[0]

    def crashing(current: Run, writer: StepWriter) -> StepResult:
        writer.add_finding(_finding(current, question.id))
        raise RuntimeError("process killed")

    with pytest.raises(RuntimeError):
        advance(runs, run.id, {"analysis": crashing})
    assert runs.findings(run.id) == []
    assert len(runs.events(run.id)) == 1

    fresh = RunRepository(
        make_session_factory(db_url), lambda: datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
    )

    def working(current: Run, writer: StepWriter) -> StepResult:
        writer.add_finding(_finding(current, question.id))
        return StepResult()

    advance(fresh, run.id, {"analysis": working})
    assert len(fresh.findings(run.id)) == 1
    assert [e.seq for e in fresh.events(run.id)] == [1, 2, 3, 4]


def test_steps_move_through_the_lifecycle_to_finished(runs: RunRepository, run: Run) -> None:
    """R24: analysis, then severity, then ranked, then finished (after the plant screen, R50,
    which this fixture skips; `test_start` covers it as the first step)."""
    steppers: dict[str, Stepper] = {
        "analysis": lambda r, w: StepResult(next_step="severity"),
        "severity": lambda r, w: StepResult(next_step="ranked"),
        "ranked": lambda r, w: StepResult(status=RunStatus.FINISHED),
    }
    assert advance(runs, run.id, steppers) == RunStatus.RUNNING
    assert runs.get(run.id).step == "severity"  # type: ignore[union-attr]
    advance(runs, run.id, steppers)
    assert advance(runs, run.id, steppers) == RunStatus.FINISHED
    assert runs.events(run.id)[-1].type == EventType.RUN_FINISHED
    assert advance(runs, run.id, steppers) == RunStatus.FINISHED


def test_a_failed_step_emits_run_failed(runs: RunRepository, run: Run) -> None:
    advance(runs, run.id, {"analysis": lambda r, w: StepResult(status=RunStatus.FAILED)})
    assert runs.get(run.id).status == RunStatus.FAILED  # type: ignore[union-attr]
    assert runs.events(run.id)[-1].type == EventType.RUN_FAILED


def test_cancelled_run_does_nothing_on_advance(runs: RunRepository, run: Run) -> None:
    called: list[str] = []

    def stepper(current: Run, writer: StepWriter) -> StepResult:
        called.append(current.id)
        return StepResult()

    assert cancel(runs, run.id) == RunStatus.CANCELLED
    assert advance(runs, run.id, {"analysis": stepper}) == RunStatus.CANCELLED
    assert called == []


def test_cancel_does_not_change_an_ended_run(runs: RunRepository, run: Run) -> None:
    advance(runs, run.id, {"analysis": lambda r, w: StepResult(status=RunStatus.FINISHED)})
    assert cancel(runs, run.id) == RunStatus.FINISHED


def test_events_are_contiguous_from_1_and_every_record_has_its_event(
    runs: RunRepository, run: Run
) -> None:
    question = runs.questions(run.id)[1]
    step, call, tool = _records(run)

    def stepper(current: Run, writer: StepWriter) -> StepResult:
        writer.add_step(step)
        writer.add_model_call(call)
        writer.add_tool_call(tool)
        writer.add_finding(_finding(current, question.id))
        return StepResult()

    advance(runs, run.id, {"analysis": stepper})
    advance(runs, run.id, {"analysis": lambda r, w: StepResult()})
    events = runs.events(run.id)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    by_type = {e.type: e.payload for e in events}
    assert by_type[EventType.AGENT_DECISION]["step_id"] == step.id
    assert by_type[EventType.MODEL_CALL]["model_call_id"] == call.id
    assert by_type[EventType.TOOL_CALL]["tool_call_id"] == tool.id
    assert by_type[EventType.FINDING_ADDED]["finding_id"] == runs.findings(run.id)[0].id
    assert runs.steps(run.id) == [step]
    assert runs.model_calls(run.id) == [call]
    assert runs.tool_calls(run.id) == [tool]
    assert [e.seq for e in runs.events(run.id, after=3)] == [e.seq for e in events if e.seq > 3]


def test_spend_is_added_to_the_run(runs: RunRepository, run: Run) -> None:
    """R45: paid money and the cap figure are kept apart."""

    def stepper(current: Run, writer: StepWriter) -> StepResult:
        writer.add_spent(0.25, cap_usd=0.25)
        writer.add_spent(0.0, cap_usd=0.125)  # a cache hit
        return StepResult()

    advance(runs, run.id, {"analysis": stepper})
    stored = runs.get(run.id)
    assert stored is not None
    assert stored.spent_usd == pytest.approx(0.25)
    assert stored.cap_spent_usd == pytest.approx(0.375)


def _finish_with(
    runs: RunRepository, run: Run, call: ModelCall, paid: float, counted: float
) -> RunStatus:
    def stepper(current: Run, writer: StepWriter) -> StepResult:
        writer.add_model_call(call)
        writer.add_spent(paid, cap_usd=counted)
        return StepResult(status=RunStatus.FINISHED)

    return advance(runs, run.id, {"analysis": stepper})


def test_spend_matching_its_records_logs_nothing(
    runs: RunRepository, run: Run, caplog: pytest.LogCaptureFixture
) -> None:
    _, call, _ = _records(run)
    with caplog.at_level("ERROR", logger="guideword.runs.machine"):
        assert _finish_with(runs, run, call, call.cost_usd, call.cap_cost_usd) == RunStatus.FINISHED
    assert caplog.records == []


@pytest.mark.parametrize("paid_extra, counted_extra", [(0.01, 0.0), (0.0, 0.01)])
def test_spend_not_matching_its_records_is_logged_when_the_run_stops(
    runs: RunRepository,
    run: Run,
    caplog: pytest.LogCaptureFixture,
    paid_extra: float,
    counted_extra: float,
) -> None:
    _, call, _ = _records(run)
    with caplog.at_level("ERROR", logger="guideword.runs.machine"):
        status = _finish_with(
            runs, run, call, call.cost_usd + paid_extra, call.cap_cost_usd + counted_extra
        )
    assert status == RunStatus.FINISHED  # the status stands
    assert [r.message for r in caplog.records] == ["run spend does not match its call records"]


def test_phase_2_event_types() -> None:
    """R32: the store emits only the types of the phases built; later ones come with their
    tools. Phase 3 (plan G11) adds the post-analysis steps' events."""
    assert set(EventType) - LATER_PHASE_EVENTS >= EMITTED_EVENT_TYPES
    assert {
        EventType.CHAIN_ADDED,
        EventType.LOPA_DONE,
        EventType.RUN_EXTENDED,
        EventType.EVIDENCE_ADDED,
    } <= (EMITTED_EVENT_TYPES)


def test_a_second_record_with_the_same_model_call_id_is_refused(
    runs: RunRepository, run: Run
) -> None:
    """Found in the case D dev run: a repeated request's cache hit overwrote the paid record."""
    _, call, _ = _records(run)

    def stepper(current: Run, writer: StepWriter) -> StepResult:
        writer.add_model_call(call)
        writer.add_model_call(call.model_copy(update={"cache_hit": True, "cost_usd": 0.0}))
        return StepResult()

    with pytest.raises(ValueError, match="already recorded"):
        advance(runs, run.id, {"analysis": stepper})
    assert runs.model_calls(run.id) == []  # the step saved nothing


def test_a_model_call_id_stored_in_an_earlier_step_is_refused(
    runs: RunRepository, run: Run
) -> None:
    _, call, _ = _records(run)
    advance(runs, run.id, {"analysis": lambda r, w: (w.add_model_call(call), StepResult())[1]})
    with pytest.raises(ValueError, match="already recorded"):
        advance(runs, run.id, {"analysis": lambda r, w: (w.add_model_call(call), StepResult())[1]})
    assert runs.model_calls(run.id) == [call]


def test_step_result_summary_stays_out_of_the_api_contract() -> None:
    """Bhargavi, 2026-10-20: `StepResult.summary` is internal. It only adds keys to a
    `step_finished` event's free-form payload; no contract model or schema names it."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    repo = Path(__file__).resolve().parents[3]
    openapi = json.loads((repo / "contract" / "openapi.json").read_text(encoding="utf-8"))
    schemas = openapi["components"]["schemas"]
    assert "StepResult" not in schemas
    assert "summary" not in schemas["Event"]["properties"]
    assert not any("StepResult" in p.name for p in (repo / "contract" / "schemas").iterdir())
