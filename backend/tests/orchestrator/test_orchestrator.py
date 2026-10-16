"""The orchestrator core (spec 2.5; plan R4, R24, R38, R44): fake gateway, scripted decisions."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.client import Gateway
from guideword.gateway.fake import FakeTransport, fake_gateway, reply
from guideword.gateway.transport import ToolCallRequest
from guideword.orchestrator.loop import OrchestratorStepper
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.machine import Stepper, StepResult, advance
from guideword.runs.plants import PlantRepository, load_plant, plant_facts
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, QuestionStatus, RunStatus
from guideword.schema.plant import Plant
from guideword.schema.records import Run
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
_VIEW = re.compile(r"<view>\s*(.*?)\s*</view>", re.S)
_QUESTIONS = re.compile(r"<questions>\s*(.*?)\s*</questions>", re.S)
TOOLS = {"check_coverage", "dispatch_specialist", "reactivity_lookup", "finish"}
Decide = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def view_of(request: dict[str, Any]) -> dict[str, Any]:
    match = _VIEW.search(request["messages"][0]["content"])
    assert match is not None
    view: dict[str, Any] = json.loads(match.group(1))
    return view


def batch_ids(request: dict[str, Any]) -> list[str]:
    match = _QUESTIONS.search(request["messages"][0]["content"])
    assert match is not None
    return [q["id"] for q in json.loads(match.group(1))]


def not_credible(request: dict[str, Any]) -> Any:
    return reply(
        {
            "answers": [
                {"question_id": q, "not_credible": {"reason": "not credible here"}, "findings": []}
                for q in batch_ids(request)
            ],
            "added_questions": [],
        }
    )


def tool(name: str, **args: Any) -> Any:
    return reply(
        tool_calls=(ToolCallRequest("t1", name, json.dumps({"reason": f"{name} now", **args})),)
    )


def level_for(view: dict[str, Any], agent: str) -> str:
    """Bulk while the agent has untried open questions, then hard for the tried ones (R44)."""
    retry = view["retry_at_hard"].get(agent, {"count": 0})["count"]
    return "bulk" if view["open"][agent]["count"] > retry else "hard"


def drain(view: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Dispatch the first agent with open questions; finish when none are open."""
    for agent in sorted(view["open"]):
        return "dispatch_specialist", {"agent": agent, "level": level_for(view, agent)}
    return "finish", {}


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


class World:
    def __init__(self, tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
        self.sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)
        self.ref, self.config = ref, config
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        record, _ = load_plant(raw, ref)
        assert record is not None
        self.plants.add(record, raw, plant_facts(record.plant_file, record.id))
        self.plants.confirm(record.id, rule_cut(record.plant_file, record.id))
        self.plant: Plant = record.plant_file
        self.record_id = record.id
        self.tmp = tmp_path

    def start(self, config: Config | None = None, cap: float = 1.0) -> Run:
        cfg = config or self.config
        settings = RunSettings(
            dict(cfg.routing.jobs), cfg.caps.run_input_caps(), dict(cfg.routing.prompts)
        )
        run = start_run(
            self.plants,
            self.runs,
            self.ref,
            settings,
            plant_record_id=self.record_id,
            spend_cap_usd=cap,
            mode="full",
        )
        return past_screen(self.runs, run)

    def gateway(
        self, decide: Decide, specialist: Any = not_credible, config: Config | None = None
    ) -> tuple[Gateway, FakeTransport]:
        def script(job: str, request: dict[str, Any]) -> Any:
            if job == "orchestrator":
                name, args = decide(view_of(request))
                return tool(name, **args)
            return specialist(request)

        return fake_gateway(
            config or self.config,
            script,
            sessions=self.sessions,
            ledger_path=self.tmp / "l.jsonl",
            clock=lambda: NOW,
        )

    def steppers(self, gateway: Gateway, config: Config | None = None) -> dict[str, Stepper]:
        return {
            "analysis": OrchestratorStepper(
                gateway, config=config or self.config, ref=self.ref, plant=self.plant
            ),
            "severity": lambda r, w: StepResult(next_step="ranked"),
            "ranked": lambda r, w: StepResult(status=RunStatus.FINISHED),
        }

    def run_to_end(self, run: Run, steppers: dict[str, Stepper], limit: int = 100) -> RunStatus:
        status = RunStatus.RUNNING
        for _ in range(limit):
            status = advance(self.runs, run.id, steppers)
            if status != RunStatus.RUNNING:
                return status
        raise AssertionError("the run did not end")


@pytest.fixture
def world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
    return World(tmp_path, ref, config)


def _tool_calls(world: World, run: Run, name: str) -> list[Any]:
    return [t for t in world.runs.tool_calls(run.id) if t.tool == name]


# --- the guards ---------------------------------------------------------------------------------


def test_finish_with_open_questions_refused_with_ids(world: World) -> None:
    run = world.start()
    gateway, _ = world.gateway(lambda view: ("finish", {}))
    advance(world.runs, run.id, world.steppers(gateway))
    [finish] = _tool_calls(world, run, "finish")
    assert finish.refused_reason is not None
    assert "98 questions are open" in finish.refused_reason
    assert world.runs.questions(run.id)[0].id in finish.refused_reason
    assert world.runs.get(run.id).step == "analysis"  # type: ignore[union-attr]


def test_finish_after_all_answered_accepted(world: World) -> None:
    run = world.start()
    gateway, _ = world.gateway(drain)
    assert world.run_to_end(run, world.steppers(gateway)) == RunStatus.FINISHED
    finish = _tool_calls(world, run, "finish")[-1]
    assert finish.refused_reason is None


def test_full_fake_run_on_the_example_finishes_every_question_answered_or_not_credible(
    world: World,
) -> None:
    run = world.start()
    gateway, _ = world.gateway(drain)
    assert world.run_to_end(run, world.steppers(gateway)) == RunStatus.FINISHED
    statuses = {q.status for q in world.runs.questions(run.id)}
    assert statuses <= {QuestionStatus.ANSWERED, QuestionStatus.NOT_CREDIBLE}
    events = world.runs.events(run.id)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    types = {e.type for e in events}
    assert {
        EventType.AGENT_DECISION,
        EventType.DISPATCH,
        EventType.MODEL_CALL,
        EventType.COVERAGE_UPDATED,
        EventType.RUN_FINISHED,
    } <= types


def test_dispatching_an_answered_question_costs_no_call(world: World) -> None:
    run = world.start()
    decisions = iter(
        [
            (
                "dispatch_specialist",
                {"agent": "dust", "level": "bulk"},
            ),  # nothing: refused, no call
            ("dispatch_specialist", {"agent": "maintenance", "level": "bulk"}),
            (
                "dispatch_specialist",
                {"agent": "maintenance", "level": "bulk", "question_ids": ["work:W-1:PSV-1"]},
            ),
        ]
    )
    gateway, transport = world.gateway(lambda view: next(decisions))
    steppers = world.steppers(gateway)
    for _ in range(3):
        advance(world.runs, run.id, steppers)
    specialist_calls = [j for j, _ in transport.sent if j != "orchestrator"]
    assert len(specialist_calls) == 1
    last = _tool_calls(world, run, "dispatch_specialist")[-1]
    assert last.result["skipped"] == ["work:W-1:PSV-1"]


def test_step_cap_stopped_cap_with_event(world: World, config: Config) -> None:
    tight = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={"run": config.caps.run.model_copy(update={"orchestrator_max_steps": 2})}
            )
        }
    )
    run = world.start(tight)
    gateway, _ = world.gateway(lambda view: ("check_coverage", {}), config=tight)
    assert world.run_to_end(run, world.steppers(gateway, tight)) == RunStatus.STOPPED_CAP
    hits = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]
    assert hits == [{"reason": "orchestrator_max_steps", "limit": 2}]
    assert len([s for s in world.runs.steps(run.id) if s.agent == "orchestrator"]) == 2


def test_orchestrator_input_never_contains_consequence_text(world: World) -> None:
    marker = "MARKER-CONSEQUENCE-TEXT"

    def specialist(request: dict[str, Any]) -> Any:
        return reply(
            {
                "answers": [
                    {
                        "question_id": q,
                        "not_credible": None,
                        "findings": [
                            {
                                "cause_id": "outside_library",
                                "cause_text": "a gremlin",
                                "failing_component_type": "external",
                                "failing_component_ids": ["ROOF"],
                                "consequence": marker,
                                "safeguard_ids": [],
                                "adequacy": "unknown",
                                "confidence": "unsure",
                                "reason": "test",
                            }
                        ],
                    }
                    for q in batch_ids(request)
                ],
                "added_questions": [],
            }
        )

    run = world.start()
    gateway, transport = world.gateway(drain, specialist)
    for _ in range(3):
        advance(world.runs, run.id, world.steppers(gateway))
    assert any(marker in f.consequence for f in world.runs.findings(run.id))
    for job, request in transport.sent:
        if job == "orchestrator":
            assert marker not in json.dumps(request)


def test_later_phase_tools_not_offered(world: World) -> None:
    run = world.start()
    gateway, transport = world.gateway(lambda view: ("check_coverage", {}))
    advance(world.runs, run.id, world.steppers(gateway))
    request = next(r for j, r in transport.sent if j == "orchestrator")
    assert {t["function"]["name"] for t in request["tools"]} == TOOLS
    assert request["tool_choice"] == "required"


def test_malformed_arguments_refused_once_then_branch_stops(world: World) -> None:
    run = world.start()
    gateway, _ = world.gateway(lambda view: ("dispatch_specialist", {"agent": "wizard"}))
    steppers = world.steppers(gateway)
    assert advance(world.runs, run.id, steppers) == RunStatus.RUNNING
    [first] = _tool_calls(world, run, "dispatch_specialist")
    assert (first.refused_reason or "").startswith("bad arguments")
    assert advance(world.runs, run.id, steppers) == RunStatus.FAILED


def test_orchestrator_call_failing_twice_fails_the_run(world: World) -> None:
    run = world.start()

    def script(job: str, request: dict[str, Any]) -> Any:
        return reply("I would rather not use a tool.")

    gateway, transport = fake_gateway(
        world.config,
        script,
        sessions=world.sessions,
        ledger_path=world.tmp / "l.jsonl",
        clock=lambda: NOW,
    )
    assert advance(world.runs, run.id, world.steppers(gateway)) == RunStatus.FAILED
    assert len(transport.sent) == 2
    assert world.runs.events(run.id)[-1].type == EventType.RUN_FAILED


def test_reactivity_lookup_result_and_its_summary_are_recorded(world: World) -> None:
    run = world.start()
    gateway, _ = world.gateway(
        lambda view: ("reactivity_lookup", {"chemical_a": "SIH", "chemical_b": "KOH"})
    )
    advance(world.runs, run.id, world.steppers(gateway))
    [call] = _tool_calls(world, run, "reactivity_lookup")
    assert call.refused_reason is None
    assert "flammable gas" in call.result["summary"] and "toxic gas" in call.result["summary"]
    seen: list[dict[str, Any]] = []
    gateway2, _ = world.gateway(lambda view: (seen.append(view), ("check_coverage", {}))[1])
    advance(world.runs, run.id, world.steppers(gateway2))
    assert "flammable gas" in seen[0]["recent_steps"][-1]["result"]


# --- R44: dispatch selection ----------------------------------------------------------------


def _dispatch_events(world: World, run: Run) -> list[dict[str, Any]]:
    return [e.payload for e in world.runs.events(run.id) if e.type == EventType.DISPATCH]


def test_omitted_list_selects_in_id_order(world: World, config: Config) -> None:
    run = world.start()
    gateway, _ = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "process", "level": "bulk"})
    )
    advance(world.runs, run.id, world.steppers(gateway))
    [event] = _dispatch_events(world, run)
    from guideword.specialists.routing import agent_for  # noqa: PLC0415

    sections = {s.id: s for s in world.runs.sections(run.id)}
    process = sorted(
        q.id for q in world.runs.questions(run.id) if agent_for(q, sections).value == "process"
    )
    limit = config.caps.run.orchestrator_view.dispatch_max_question_ids
    assert event["question_ids"] == process[:limit]
    assert event["selected_by_code"] is True


def test_explicit_list_unchanged(world: World) -> None:
    run = world.start()
    chosen = ["m:S-MX-1:more:pressure", "m:S-MX-1:less:pressure"]
    gateway, _ = world.gateway(
        lambda view: (
            "dispatch_specialist",
            {"agent": "process", "level": "bulk", "question_ids": chosen},
        )
    )
    advance(world.runs, run.id, world.steppers(gateway))
    [event] = _dispatch_events(world, run)
    assert (event["question_ids"], event["selected_by_code"]) == (chosen, False)


def test_omitted_list_with_nothing_open_for_that_agent_is_refused(world: World) -> None:
    run = world.start()
    gateway, transport = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "dust", "level": "bulk"})
    )
    advance(world.runs, run.id, world.steppers(gateway))
    [call] = _tool_calls(world, run, "dispatch_specialist")
    assert "nothing to dispatch" in (call.refused_reason or "")
    assert [j for j, _ in transport.sent] == ["orchestrator"]


def test_explicit_list_for_the_wrong_agent_is_refused(world: World) -> None:
    run = world.start()
    gateway, _ = world.gateway(
        lambda view: (
            "dispatch_specialist",
            {"agent": "dust", "level": "bulk", "question_ids": ["pair:KOH:SIH"]},
        )
    )
    advance(world.runs, run.id, world.steppers(gateway))
    [call] = _tool_calls(world, run, "dispatch_specialist")
    assert "chemistry" in (call.refused_reason or "")


def test_view_lists_open_ids_by_agent(world: World) -> None:
    run = world.start()
    seen: list[dict[str, Any]] = []

    def decide(view: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        seen.append(view)
        return "check_coverage", {}

    gateway, _ = world.gateway(decide)
    advance(world.runs, run.id, world.steppers(gateway))
    view = seen[0]
    assert set(view["open"]) == {"process", "chemistry", "procedures", "maintenance"}
    assert view["open"]["chemistry"]["count"] == 7
    assert view["steps_left"] == world.config.caps.run.orchestrator_max_steps


# --- R4: unsure re-answers -----------------------------------------------------------------


def test_unsure_reanswer_on_ultra_allowed_up_to_the_cap(world: World, config: Config) -> None:
    capped = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={"run": config.caps.run.model_copy(update={"unsure_reanswers_per_run": 1})}
            )
        }
    )
    unsure_finding = {
        "cause_id": "outside_library",
        "cause_text": "a gremlin",
        "failing_component_type": "external",
        "failing_component_ids": ["ROOF"],
        "consequence": "something",
        "safeguard_ids": [],
        "adequacy": "unknown",
        "confidence": "unsure",
        "reason": "test",
    }

    def specialist(request: dict[str, Any]) -> Any:
        return reply(
            {
                "answers": [
                    {"question_id": q, "not_credible": None, "findings": [unsure_finding]}
                    for q in batch_ids(request)
                ],
                "added_questions": [],
            }
        )

    decisions = iter(
        [
            ("dispatch_specialist", {"agent": "maintenance", "level": "bulk"}),
            ("dispatch_specialist", {"agent": "maintenance", "level": "unsure"}),
            ("dispatch_specialist", {"agent": "maintenance", "level": "unsure"}),
        ]
    )
    run = world.start(capped)
    gateway, transport = world.gateway(lambda view: next(decisions), specialist, config=capped)
    steppers = world.steppers(gateway, capped)
    for _ in range(3):
        advance(world.runs, run.id, steppers)
    jobs = [j for j, _ in transport.sent if j != "orchestrator"]
    assert jobs == ["specialist_bulk", "unsure_answer"]
    tiers = sorted(f.tier for f in world.runs.findings(run.id))
    assert tiers == ["lightning", "ultra"]
    third = _tool_calls(world, run, "dispatch_specialist")[-1]
    assert "nothing to dispatch" in (third.refused_reason or "")
    # an Ultra re-answer adds a finding; the question stays answered
    [work] = [q for q in world.runs.questions(run.id) if q.id == "work:W-1:PSV-1"]
    assert work.status == QuestionStatus.ANSWERED


# --- R38: the severity reserve -------------------------------------------------------------


def finds(request: dict[str, Any]) -> Any:
    """One outside-library finding per question, on a location every agent may cite."""
    return reply(
        {
            "answers": [
                {
                    "question_id": q,
                    "not_credible": None,
                    "findings": [
                        {
                            "cause_id": "outside_library",
                            "cause_text": "a gremlin",
                            "failing_component_type": "external",
                            "failing_component_ids": ["ROOF"],
                            "consequence": "a release",
                            "safeguard_ids": [],
                            "adequacy": "unknown",
                            "confidence": "sure",
                            "reason": "test",
                        }
                    ],
                }
                for q in batch_ids(request)
            ],
            "added_questions": [],
        }
    )


def test_the_analysis_stops_where_the_computed_severity_reserve_begins(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """The reserve is worked out each step from the findings so far. A first run measures one
    small dispatch: the cap spent before it, its batch's slice and the reserve its findings
    need. A second run with a cap just covering the first orchestrator turn and that dispatch
    admits the dispatch, then the reserve leaves no room for the next orchestrator call."""
    from guideword.ranking.severity import scenarios, severity_reserve  # noqa: PLC0415

    chosen = ["m:S-MX-1:more:pressure", "m:S-MX-1:less:pressure"]

    def process(view: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return "dispatch_specialist", {"agent": "process", "level": "bulk", "question_ids": chosen}

    (tmp_path / "a").mkdir()
    probe = World(tmp_path / "a", ref, config)
    first = probe.start(cap=1.0)
    gateway, transport = probe.gateway(process, finds)
    advance(probe.runs, first.id, probe.steppers(gateway))
    # with no findings yet, nothing is reserved: the view's limit is the whole cap
    assert view_of(transport.sent[0][1])["spend"]["limit_usd"] == 1.0
    [dispatch] = _dispatch_events(probe, first)
    admission = dispatch["admission"]
    found = probe.runs.findings(first.id)
    reserve = severity_reserve(found, probe.runs.questions(first.id), probe.plant, ref, config)
    # R48: the reserve counts scenarios, not findings
    assert reserve.unrated == len(scenarios(found, probe.runs.questions(first.id))) > 0

    (tmp_path / "b").mkdir()
    world = World(tmp_path / "b", ref, config)
    # the orchestrator's own call is checked at its max_tokens estimate, so the cap covers that
    # and the dispatch's admission; the reserve the findings then need covers neither
    from guideword.gateway.estimate import estimate_cost  # noqa: PLC0415
    from guideword.schema.enums import Tier  # noqa: PLC0415

    turn = transport.sent[0][1]
    orchestrator = estimate_cost(
        config.models.tiers[Tier.ULTRA], turn["messages"], turn["tools"], turn["max_tokens"]
    ).cost_usd
    # 10% over: this run's view shows its own (smaller) limit, so its prompt is a little longer
    needed = 1.1 * max(orchestrator, admission["cap_spent_usd"] + sum(admission["slices_usd"]))
    assert reserve.usd > needed
    run = world.start(cap=round(needed, 6))
    gateway, transport = world.gateway(process, finds)
    steppers = world.steppers(gateway)
    advance(world.runs, run.id, steppers)
    [admitted] = _dispatch_events(world, run)
    assert admitted["deferred_at_admission"] == []
    sent = len(transport.sent)
    assert advance(world.runs, run.id, steppers) == RunStatus.RUNNING
    assert len(transport.sent) == sent  # the second orchestrator call was refused, unsent
    assert world.runs.get(run.id).step == "severity"  # type: ignore[union-attr]
    [hit] = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]
    assert hit["reason"] == "severity reserve"
    assert hit["reserve_usd"] == pytest.approx(reserve.usd)
    assert (hit["unrated"], hit["severity_calls"]) == (reserve.unrated, reserve.calls)


# --- no identical request twice in one run (found in the case D dev run) ----------------------


def broken(request: dict[str, Any]) -> Any:
    return reply("this is not the answer schema")


def test_a_question_that_failed_at_bulk_is_never_sent_to_bulk_again(world: World) -> None:
    """The same batch sent again is a cache hit and can only fail again: a question with a
    failed attempt goes on at hard, never back to bulk (R44 as amended)."""
    run = world.start()
    gateway, transport = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "process", "level": "bulk"}), broken
    )
    steppers = world.steppers(gateway)
    advance(world.runs, run.id, steppers)
    first = set(_dispatch_events(world, run)[0]["question_ids"])
    tried = {q.id for q in world.runs.questions(run.id) if q.attempts > 0}
    assert first and first == tried
    advance(world.runs, run.id, steppers)
    second = _dispatch_events(world, run)[1]
    assert not first & set(second["question_ids"])
    sent = [json.dumps(r, sort_keys=True) for job, r in transport.sent if job != "orchestrator"]
    assert len(sent) == len(set(sent))  # no request was sent twice


def test_naming_failed_questions_at_bulk_again_is_refused_before_any_call(world: World) -> None:
    run = world.start()
    chosen = ["m:S-MX-1:more:pressure", "m:S-MX-1:less:pressure"]
    gateway, transport = world.gateway(
        lambda view: (
            "dispatch_specialist",
            {"agent": "process", "level": "bulk", "question_ids": chosen},
        ),
        broken,
    )
    steppers = world.steppers(gateway)
    advance(world.runs, run.id, steppers)
    specialist_calls = sum(1 for job, _ in transport.sent if job != "orchestrator")
    advance(world.runs, run.id, steppers)
    assert sum(1 for job, _ in transport.sent if job != "orchestrator") == specialist_calls
    second = _dispatch_events(world, run)[1]
    assert second["skipped"] == chosen and second["batches"] == 0
    # one record per model call ID: nothing was overwritten
    ids = [c.id for c in world.runs.model_calls(run.id)]
    assert len(ids) == len(set(ids))


# --- R13 as amended: deterministic admission -------------------------------------------------


def _dispatch_once(
    world: World, cap: float, config: Config | None = None
) -> tuple[Run, dict[str, Any]]:
    run = world.start(cap=cap, config=config)
    gateway, _ = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "process", "level": "bulk"}),
        finds,
        config=config,
    )
    advance(world.runs, run.id, world.steppers(gateway, config=config))
    [event] = _dispatch_events(world, run)
    return run, event


def test_batches_that_do_not_fit_are_deferred_in_order_and_the_analysis_goes_on(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Batches are admitted in batch order against the cap spent before the dispatch; from the
    first that does not fit, the rest are deferred, recorded in order on the dispatch event and
    not as a cap hit. Their questions are untouched (never sent, never promoted) and the
    analysis goes on."""
    (tmp_path / "probe").mkdir()
    _, probe = _dispatch_once(World(tmp_path / "probe", ref, config), cap=5.0)
    admission = probe["admission"]
    slices = admission["slices_usd"]
    assert len(slices) > 2 and probe["deferred_at_admission"] == []
    # a cap that fits the orchestrator turn and the first two slices only
    cap = admission["cap_spent_usd"] + slices[0] + slices[1] + slices[2] / 2
    (tmp_path / "run").mkdir()
    world = World(tmp_path / "run", ref, config)
    run, event = _dispatch_once(world, cap=round(cap, 6))
    assert event["admission"]["slices_usd"] == slices
    deferred = event["deferred_at_admission"]
    assert [d["slice_usd"] for d in deferred] == slices[2:]
    untouched = [q for d in deferred for q in d["question_ids"]]
    stored = {q.id: q for q in world.runs.questions(run.id)}
    assert untouched and all(stored[q].attempts == 0 for q in untouched)
    assert all(stored[q].status == QuestionStatus.OPEN for q in untouched)
    assert world.runs.get(run.id).step == "analysis"  # type: ignore[union-attr]
    assert [e for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT] == []


def test_a_deferred_batch_is_sent_at_bulk_by_a_later_dispatch(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """A deferred batch was never sent: it is no repeat, keeps its level, and a later bulk
    dispatch sends it."""
    (tmp_path / "probe").mkdir()
    _, probe = _dispatch_once(World(tmp_path / "probe", ref, config), cap=5.0)
    slices = probe["admission"]["slices_usd"]
    cap = probe["admission"]["cap_spent_usd"] + slices[0] + slices[1] + slices[2] / 2
    (tmp_path / "run").mkdir()
    world = World(tmp_path / "run", ref, config)
    run = world.start(cap=round(cap + 0.5, 6))
    gateway, transport = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "process", "level": "bulk"}), finds
    )
    steppers = world.steppers(gateway)
    # the first dispatch runs at the low cap: lower it by setting the stored spend cap
    with world.runs.step(run.id) as writer:
        writer.set_spend_cap(round(cap, 6))
    advance(world.runs, run.id, steppers)
    [first] = _dispatch_events(world, run)
    deferred = [q for d in first["deferred_at_admission"] for q in d["question_ids"]]
    assert deferred
    with world.runs.step(run.id) as writer:
        writer.set_spend_cap(round(cap + 0.5, 6))
    advance(world.runs, run.id, steppers)
    second = _dispatch_events(world, run)[1]
    assert second["level"] == "bulk" and set(deferred) <= set(second["question_ids"])
    sent = {q for job, r in transport.sent if job == "specialist_bulk" for q in batch_ids(r)}
    assert set(deferred) <= sent
    stored = {q.id: q for q in world.runs.questions(run.id)}
    assert {stored[q].status for q in deferred} <= {
        QuestionStatus.ANSWERED,
        QuestionStatus.NOT_CREDIBLE,
    }


def test_the_analysis_ends_when_a_dispatch_cannot_admit_its_first_batch(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """With bulk calls allowed a very large output, a batch's slice is larger than the room
    left after the orchestrator turn: nothing is admitted, the cap hit says so, and the
    analysis ends. Every dispatch therefore either admits a batch or ends the analysis."""
    big = {**config.caps.run.max_tokens, "specialist_bulk": 400_000}
    cfg = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={"run": config.caps.run.model_copy(update={"max_tokens": big})}
            )
        }
    )
    world = World(tmp_path, ref, config)
    run = world.start(cap=0.03, config=cfg)
    gateway, transport = world.gateway(
        lambda view: ("dispatch_specialist", {"agent": "process", "level": "bulk"}),
        finds,
        config=cfg,
    )
    advance(world.runs, run.id, world.steppers(gateway, config=cfg))
    assert [job for job, _ in transport.sent] == ["orchestrator"]
    [event] = _dispatch_events(world, run)
    assert event["admission"]["slices_usd"][0] > 0.03
    [hit] = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]
    assert hit["reason"] == "admission"
    assert "first batch" in hit["detail"]
    assert world.runs.get(run.id).step == "severity"  # type: ignore[union-attr]


def test_the_same_deferrals_whatever_the_thread_timing(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Concurrency is not a run input; one batch at a time or five at once, the same batches
    are admitted and deferred and the same calls recorded."""
    (tmp_path / "probe").mkdir()
    _, probe = _dispatch_once(World(tmp_path / "probe", ref, config), cap=5.0)
    slices = probe["admission"]["slices_usd"]
    cap = round(probe["admission"]["cap_spent_usd"] + sum(slices[:3]) + slices[3] / 2, 6)
    serial = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={"concurrency": {tier: 1 for tier in config.caps.concurrency}}
            )
        }
    )
    results = []
    for name, cfg in (("parallel", config), ("serial", serial)):
        (tmp_path / name).mkdir()
        world = World(tmp_path / name, ref, config)
        run, event = _dispatch_once(world, cap=cap, config=cfg)
        calls = sorted((c.id, c.cost_usd) for c in world.runs.model_calls(run.id))
        results.append(
            (event["deferred_at_admission"], calls, world.runs.get(run.id).cap_spent_usd)
        )  # type: ignore[union-attr]
    assert results[0][0] and results[0] == results[1]
