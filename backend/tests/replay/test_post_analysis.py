"""The post-analysis steps on whole $0 fake runs (Phase 3 plan PR 5; spec 3.1-3.4, 3.6; P3-1b,
P3-2; Q10, Q12, Q19; G3, G4, G10, G11, G14, G17). Every call goes through the fake gateway."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from guideword.chains.connector import HANDLES_REPLACED_FLAG
from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.fake import FakeTransport, fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.replay import MANIFEST, ReplayTransport, export_replay, load_replay
from guideword.gateway.transport import Reply, ToolCallRequest
from guideword.lopa.credit import NOT_ARGUED
from guideword.lopa.engine import CODE_ONLY_FLAG
from guideword.lopa.lines import NO_SEVERITY_NO_LOPA
from guideword.lopa.step import ARGUMENT_FAILED_FLAG, LEFT_OUT_FLAG
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs import db
from guideword.runs.case import case_report, drive, prepare_plant, start_case, steppers_for
from guideword.runs.extend import ExtendRefused, extend
from guideword.runs.machine import Stepper, StepResult, spend_matches_records
from guideword.runs.plants import PlantRepository
from guideword.runs.post_budget import POST_JOBS, POST_PROMPTS, POST_STEPS, post_spent
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, EventType, QuestionStatus, RunStatus
from guideword.schema.records import Run

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
GROUPS = 12
# keys and prompts a Phase 2 run did not have (spec 3.6: read from the current config)
PHASE_3_CAPS = {
    "connector_max_chains",
    "lopa_batch_size",
    "recommendation_batch_size",
    "post_spend_cap_usd",
}
PHASE_3_PROMPTS = {"connector", "lopa_argument", "recommendation", "severity_chain"}
# Phase 4 adds the evidence step before ranked (plan PR 5b)
RUN_STEPS = [
    "plant_screen",
    "analysis",
    "severity",
    "chains",
    "chain_severity",
    "lopa",
    "recommendations",
    "evidence",
    "ranked",
]
Script = Callable[[str, dict[str, Any]], Reply]
_BLOCK = r"<{0}>\s*(.*?)\s*</{0}>"


def block(request: dict[str, Any], name: str) -> Any:
    match = re.search(_BLOCK.format(name), request["messages"][0]["content"], re.S)
    assert match is not None, name
    return json.loads(match.group(1))


def orchestrator(request: dict[str, Any]) -> Reply:
    """Drain every open list at bulk, then hard for retries, then finish (as the conftest)."""
    view = block(request, "view")
    agents = sorted(view["open"])
    if agents:
        retry = view["retry_at_hard"].get(agents[0], {"count": 0})["count"]
        level = "bulk" if view["open"][agents[0]]["count"] > retry else "hard"
        name, args = "dispatch_specialist", {"agent": agents[0], "level": level}
    else:
        name, args = "finish", {}
    return reply(tool_calls=(ToolCallRequest("t", name, json.dumps({"reason": "go", **args})),))


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def with_run_caps(config: Config, **changes: Any) -> Config:
    run = config.caps.run.model_copy(update=changes)
    return config.model_copy(update={"caps": config.caps.model_copy(update={"run": run})})


def group_of(question_id: str) -> int:
    return sum(map(ord, question_id)) % GROUPS


def post_script(
    *,
    severities: dict[int, str] | None = None,
    connector: Callable[[list[dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]]
    | None = None,
    applies: bool = False,
    recommend: bool = True,
    rate: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    fail: frozenset[str] = frozenset(),
) -> Script:
    """A run with one line per cause group: each question's finding names `outside <group>`
    on the first location; severity by group (S3 by default); the connector proposes what
    `connector` returns, given the `L` scenario lines and the `P` facts (connector/v2);
    every LOPA layer applies or not; one recommendation per line. A job
    in `fail` answers with text that is not JSON (invalid twice)."""
    grades = severities or {}

    def script(job: str, request: dict[str, Any]) -> Reply:
        if job in fail:
            return reply("not json")
        if job == "plant_screen":
            return reply({"hypotheses": []})
        if job == "precedent_judge":
            # Phase 4: the evidence step's judge accepts nothing in these runs
            return reply({"judgements": []})
        if job == "orchestrator":
            return orchestrator(request)
        if job == "severity_reason":
            return reply(
                {
                    "severities": [
                        {
                            "finding_id": f["finding_id"],
                            "severity_class": grades.get(int(f["cause"].split()[-1]), "S3"),
                            "reason": "test",
                        }
                        for f in block(request, "findings")
                    ]
                }
            )
        if job == "connector":
            chains = (
                connector(block(request, "scenarios"), block(request, "facts")) if connector else []
            )
            return reply({"chains": chains})
        if job == "chain_severity":
            # severity_chain/v2: each chain by its handle; `rate` picks which are answered
            chains = block(request, "chains")
            shown = rate(chains) if rate else chains
            return reply(
                {
                    "severities": [
                        {"chain": c["handle"], "severity_class": "S4", "reason": "two hurt"}
                        for c in shown
                    ]
                }
            )
        if job == "lopa_argument":
            return reply(
                {
                    "lines": [
                        {
                            "target": line["handle"],
                            "layers": [
                                {"layer_id": layer["layer_id"], "applies": applies, "reason": "r"}
                                for layer in line["layers"]
                            ],
                        }
                        for line in block(request, "lines")
                    ]
                }
            )
        if job == "recommendation":
            items = [
                {"target": line["handle"], "action": "add an independent trip", "reason": "r"}
                for line in block(request, "lines")
            ]
            return reply({"recommendations": items if recommend else []})
        return specialist(request)

    return script


def specialist(request: dict[str, Any]) -> Reply:
    locations = block(request, "context").get("locations") or []
    questions = block(request, "questions")
    if not locations:
        answers = [
            {"question_id": q["id"], "not_credible": {"reason": "no location"}, "findings": []}
            for q in questions
        ]
    else:
        answers = [
            {
                "question_id": q["id"],
                "not_credible": None,
                "findings": [
                    {
                        "cause_id": "outside_library",
                        "cause_text": f"outside {group_of(q['id'])}",
                        "failing_component_type": "external",
                        "failing_component_ids": [locations[0]["id"]],
                        "consequence": "a release",
                        "safeguard_ids": [],
                        "adequacy": "unknown",
                        "confidence": "sure",
                        "reason": "test",
                    }
                ],
            }
            for q in questions
        ]
    return reply({"answers": answers, "added_questions": []})


def first_two(scenarios: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One chain of the first two scenarios, plus a plant fact, linked by handle (v2)."""
    links = [scenarios[0]["handle"], scenarios[1]["handle"], facts[0]["handle"]]
    return [{"links": links, "description": "one then the other", "reason": "shared building"}]


class World:
    def __init__(self, path: Path, ref: ReferenceSet) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.dir, self.ref = path, ref
        self.sessions = db.make_session_factory(f"sqlite:///{(path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: NOW)
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.record = prepare_plant(self.plants, raw, ref)
        self.plant = self.record.plant_file

    def gateway(self, config: Config, script: Script) -> tuple[Gateway, FakeTransport]:
        return fake_gateway(
            config,
            script,
            sessions=self.sessions,
            ledger_path=self.dir / "l.jsonl",
            clock=lambda: NOW,
            phase="3",
        )

    def start(self, config: Config, cap: float = 1.0, post_cap: float | None = None) -> Run:
        return start_case(
            self.plants,
            self.runs,
            self.ref,
            config,
            self.record.id,
            cap,
            post_spend_cap_usd=post_cap,
            use=BudgetUse.DEVELOPMENT,
        )

    def steppers(self, config: Config, gateway: Gateway) -> dict[str, Stepper]:
        return steppers_for(gateway, config, self.ref, self.plant)

    def run(
        self, config: Config, script: Script, cap: float = 1.0, post_cap: float | None = None
    ) -> tuple[Run, FakeTransport]:
        run = self.start(config, cap, post_cap)
        gateway, transport = self.gateway(config, script)
        drive(self.runs, run.id, self.steppers(config, gateway))
        done = self.runs.get(run.id)
        assert done is not None
        return done, transport

    def report(self, config: Config, run_id: str) -> dict[str, Any]:
        return case_report(self.runs, run_id, self.plant, self.ref, config.caps, "example")

    def steps_started(self, run_id: str) -> list[str]:
        return [
            e.payload["step"] for e in self.runs.events(run_id) if e.type == EventType.STEP_STARTED
        ]


def phase_2_severity(real: Stepper) -> Stepper:
    """The severity step as it ended before Phase 3: it handed over to `ranked`."""

    def stepper(run: Run, writer: Any) -> StepResult:
        result = real(run, writer)
        if result.next_step == "chains":
            return StepResult(status=result.status, next_step="ranked")
        return result

    return stepper


def phase_2_run(world: World, config: Config, script: Script, *, pre_r50: bool = False) -> Run:
    """A run finished on the Phase 2 steps, with the stored caps and prompts a Phase 2 run had
    (no Phase 3 keys); `pre_r50` also leaves out the whole-plant pass (cases D and G)."""
    caps = {k: v for k, v in config.caps.run_input_caps().items() if k not in PHASE_3_CAPS}
    prompts = {k: v for k, v in config.routing.prompts.items() if k not in PHASE_3_PROMPTS}
    jobs = {k: str(v) for k, v in config.routing.jobs.items() if k != "chain_severity"}
    if pre_r50:
        prompts.pop("plant_screen")
    run = start_run(
        world.plants,
        world.runs,
        world.ref,
        RunSettings(jobs, caps, prompts),
        plant_record_id=world.record.id,
        spend_cap_usd=1.0,
        mode="full",
        use=BudgetUse.DEVELOPMENT,
        post_spend_cap_usd=0.0,
    )
    if pre_r50:
        with world.runs.step(run.id) as writer:
            writer.set_step("analysis")
    gateway, _ = world.gateway(config, script)
    steppers = world.steppers(config, gateway)
    steppers["severity"] = phase_2_severity(steppers["severity"])
    assert drive(world.runs, run.id, steppers) == RunStatus.FINISHED
    done = world.runs.get(run.id)
    assert done is not None and done.step == "ranked"
    return done


RECORD_TABLES = [
    db.QuestionRow,
    db.FindingRow,
    db.HypothesisRow,
    db.AgentStepRow,
    db.ModelCallRow,
    db.ToolCallRow,
]


def snapshot(world: World, run_id: str) -> dict[str, dict[str, str]]:
    """Every record row of the run, as stored, plus the event log."""
    out: dict[str, dict[str, str]] = {}
    with world.sessions() as session:
        for table in RECORD_TABLES:
            rows = session.scalars(select(table).where(table.run_id == run_id)).all()
            out[table.__tablename__] = {
                r.id: json.dumps(r.record, sort_keys=True) + f"@{r.position}" for r in rows
            }
        events = session.scalars(select(db.EventRow).where(db.EventRow.run_id == run_id)).all()
        out["events"] = {str(e.seq): json.dumps(e.record, sort_keys=True) for e in events}
    return out


# --- extension (P3-1b) ------------------------------------------------------------------------


def test_extension_makes_no_analysis_calls_and_keeps_every_earlier_record_byte_identical(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script)
    before = snapshot(world, run.id)
    steps_before = len(world.steps_started(run.id))

    extended = extend(world.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    assert extended.id == run.id
    assert extended.status == RunStatus.RUNNING and extended.step == "chains"
    assert extended.post_spend_cap_usd == 0.30
    assert extended.caps == run.caps and extended.prompt_versions == run.prompt_versions
    assert extended.routing_config == run.routing_config

    gateway, transport = world.gateway(config, script)
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    jobs = {job for job, _ in transport.sent}
    assert "connector" in jobs and jobs <= POST_JOBS
    after = snapshot(world, run.id)
    for table, rows in before.items():
        for key, value in rows.items():
            assert after[table][key] == value, (table, key)
    final = world.runs.get(run.id)
    assert final is not None and final.id == run.id  # the stored inputs still rebuild the ID
    new_steps = world.steps_started(run.id)[steps_before:]
    assert list(dict.fromkeys(new_steps)) == [*POST_STEPS, "ranked"]
    assert world.runs.chains(run.id) and world.runs.lopa_records(run.id)

    (event,) = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED]
    settings = event.payload["settings"]
    assert settings["connector_max_chains"] == {"value": 10, "source": "config"}
    assert settings["lopa_top_n"] == {"value": 10, "source": "run.caps"}
    assert event.payload["post_spend_cap_usd"] == 0.30
    assert event.payload["prompt_versions"] == {
        # the post-step prompts, Phase 4's precedent judge included
        name: config.routing.prompts[name]
        for name in sorted(POST_PROMPTS)
    }


def test_extension_refuses_an_unfinished_run_and_a_run_already_extended(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "a", ref)
    unfinished = world.start(config)
    with pytest.raises(ExtendRefused, match="not finished"):
        extend(world.runs, unfinished.id, 0.30, config, use=BudgetUse.DEVELOPMENT)

    other = World(tmp_path / "b", ref)
    script = post_script()
    run = phase_2_run(other, config, script)
    extend(other.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    gateway, _ = other.gateway(config, script)
    assert drive(other.runs, run.id, other.steppers(config, gateway)) == RunStatus.FINISHED
    with pytest.raises(ExtendRefused, match="already"):
        extend(other.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    # a new run on the Phase 3 steps has its chains step done already
    fresh, _ = World(tmp_path / "c", ref).run(config, script)
    assert fresh.status == RunStatus.FINISHED
    with pytest.raises(ExtendRefused, match="already"):
        extend(World(tmp_path / "c", ref).runs, fresh.id, 0.30, config, use=BudgetUse.DEVELOPMENT)


def test_pre_r50_run_extends_with_every_line_also_found_and_labelled(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script, pre_r50=True)
    assert world.runs.hypotheses(run.id) == []
    extend(world.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    gateway, _ = world.gateway(config, script)
    drive(world.runs, run.id, world.steppers(config, gateway))
    report = world.report(config, run.id)
    assert report["pre_r50"] is True
    assert report["shortlist"]
    assert {line["tier"] for line in report["shortlist"]} == {"also_found"}
    assert all("pre-R50 run" in line["flags"] for line in report["shortlist"])


# --- the eight steps, replayed (R45) ----------------------------------------------------------


def test_full_nine_step_fake_run_replays_identically(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "original", ref)
    run, _ = world.run(config, post_script(connector=first_two, severities={0: "S4", 1: "S5"}))
    assert run.status == RunStatus.FINISHED
    assert world.steps_started(run.id)[0] == "plant_screen"
    assert sorted(set(world.steps_started(run.id))) == sorted(RUN_STEPS)
    out = export_replay(
        world.runs,
        ResponseCache(world.sessions),
        run.id,
        tmp_path / "fixtures",
        plant=world.plant,
        plant_file=EXAMPLE.relative_to(REPO).as_posix(),
        ref=ref,
        caps=config.caps,
        secrets=[],
    )
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["chains"] and manifest["lopa"] and manifest["recommendations"]

    again = World(tmp_path / "replayed", ref)
    loaded = load_replay(out, again.sessions)
    gateway = Gateway(
        config=config,
        transport=ReplayTransport(loaded),
        cache=ResponseCache(again.sessions),
        ledger=LaptopLedger(again.dir / "l.jsonl"),
        use=BudgetUse.DEVELOPMENT,
        phase="3",
        clock=lambda: NOW,
    )
    replayed = again.start(config)
    assert replayed.id == run.id
    assert drive(again.runs, replayed.id, again.steppers(config, gateway)) == RunStatus.FINISHED
    assert [[c.id, c.links] for c in again.runs.chains(run.id)] == manifest["chains"]
    assert [[r.id, r.gap] for r in again.runs.lopa_records(run.id)] == manifest["lopa"]
    assert [r.id for r in again.runs.recommendations(run.id)] == manifest["recommendations"]
    assert world.report(config, run.id)["shortlist"] == again.report(config, run.id)["shortlist"]
    done = again.runs.get(run.id)
    assert done is not None and done.spent_usd == 0.0


# --- the post budget (P3-2, Q19) and R38 (G4) -------------------------------------------------


def test_post_cap_stops_a_post_step_with_the_analysis_intact(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=first_two), post_cap=0.0)
    assert run.status == RunStatus.STOPPED_CAP
    assert run.step == "chains"
    assert "connector" not in {job for job, _ in transport.sent}
    hits = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]
    assert hits and hits[-1]["status"] == RunStatus.STOPPED_CAP
    # the analysis is whole: every question checked, every finding rated
    assert all(q.status != QuestionStatus.OPEN for q in world.runs.questions(run.id))
    assert all(f.severity_class is not None for f in world.runs.findings(run.id))
    assert world.runs.chains(run.id) == [] and world.runs.lopa_records(run.id) == []


def test_analysis_cap_behaviour_unchanged(
    tmp_path: Path, ref: ReferenceSet, config: Config, capped_script: Any
) -> None:
    """The analysis stops at the cap minus its severity reserve as before; the post cap does
    not move it (the analysis calls are the same with a post cap of 0 or 0.30)."""
    calls = {}
    for post_cap in (0.0, 0.30):
        world = World(tmp_path / str(post_cap), ref)
        run, _ = world.run(config, capped_script, cap=0.08, post_cap=post_cap)
        hits = [
            e.payload["reason"] for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT
        ]
        assert "severity reserve" in hits
        calls[post_cap] = [c.id for c in world.runs.model_calls(run.id) if c.job not in POST_JOBS]
    assert calls[0.0] == calls[0.30]


def test_extending_a_run_at_its_analysis_cap_is_not_refused(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Bhargavi, 2026-10-20 (point 3): a finished run whose analysis spend is at its analysis
    cap still extends, and the post steps spend only against the post cap."""
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script)
    assert run.cap_spent_usd > 0
    with world.runs.step(run.id) as writer:
        writer.set_spend_cap(run.cap_spent_usd)  # no analysis room left
    extend(world.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    gateway, transport = world.gateway(config, script)
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    assert "connector" in {job for job, _ in transport.sent}
    assert world.runs.chains(run.id) and world.runs.lopa_records(run.id)
    assert not [e for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]


def test_post_spend_never_counts_against_the_analysis_cap(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Bhargavi, 2026-10-20 (point 3): post spend counts against the post cap (and, through
    the ledger, the phase cap and use allowance), never the analysis cap; R45 still holds."""
    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=first_two, severities={0: "S4"}))
    assert run.status == RunStatus.FINISHED
    calls = world.runs.model_calls(run.id)
    post = [c for c in calls if c.job in POST_JOBS]
    analysis = [c for c in calls if c.job not in POST_JOBS]
    assert post and sum(c.cap_cost_usd for c in post) > 0
    assert run.cap_spent_usd == pytest.approx(sum(c.cap_cost_usd for c in analysis))
    assert run.spent_usd == pytest.approx(sum(c.cost_usd for c in calls))
    with world.runs.step(run.id) as writer:
        assert spend_matches_records(writer)


def _stop_at_post_cap(world: World, config: Config, script: Script) -> Run:
    run, _ = world.run(config, script, post_cap=0.0)
    assert run.status == RunStatus.STOPPED_CAP and run.step == "chains"
    return run


def test_a_run_stopped_at_the_post_cap_resumes_with_a_higher_post_cap(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Bhargavi, 2026-10-20 (point 2): extend takes a run that stopped at the post cap, with a
    higher post cap; the run ID stays and the analysis is not run again."""
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = _stop_at_post_cap(world, config, script)
    before = snapshot(world, run.id)

    resumed = extend(world.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    assert resumed.id == run.id
    assert resumed.status == RunStatus.RUNNING and resumed.step == "chains"
    assert resumed.post_spend_cap_usd == 0.30
    events = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED]
    assert events[-1].payload["resumed_after_post_cap"] is True

    gateway, transport = world.gateway(config, script)
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    assert {job for job, _ in transport.sent} <= POST_JOBS
    after = snapshot(world, run.id)
    for table, rows in before.items():
        for key, value in rows.items():
            assert after[table][key] == value, (table, key)
    assert world.runs.chains(run.id) and world.runs.lopa_records(run.id)


def test_a_resume_after_a_mid_post_stop_sends_no_finished_step_again(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """A stop after the chains step is paid for: on resume the connector call is not sent
    again, and the spend still matches the call records (R45)."""
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = world.start(config, post_cap=0.30)
    gateway, _ = world.gateway(config, script)
    steppers = world.steppers(config, gateway)
    real = steppers["chain_severity"]

    def no_room_left(current: Run, writer: Any) -> StepResult:
        writer.set_post_spend_cap(post_spent(writer.model_calls()))
        return real(current, writer)

    steppers["chain_severity"] = no_room_left
    assert drive(world.runs, run.id, steppers) == RunStatus.STOPPED_CAP
    stopped = world.runs.get(run.id)
    assert stopped is not None and stopped.step == "chain_severity"
    connector_calls = [c.id for c in world.runs.model_calls(run.id) if c.job == "connector"]
    assert connector_calls

    extend(world.runs, run.id, 0.30, config, use=BudgetUse.DEVELOPMENT)
    gateway, transport = world.gateway(config, script)
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    assert "connector" not in {job for job, _ in transport.sent}
    assert [c.id for c in world.runs.model_calls(run.id) if c.job == "connector"] == (
        connector_calls
    )
    with world.runs.step(run.id) as writer:
        assert spend_matches_records(writer)


def test_extend_refuses_an_analysis_cap_stop_and_a_post_cap_that_is_not_higher(
    tmp_path: Path, ref: ReferenceSet, config: Config, capped_script: Any
) -> None:
    world = World(tmp_path / "post", ref)
    run = _stop_at_post_cap(world, config, post_script())
    with pytest.raises(ExtendRefused, match="higher"):
        extend(world.runs, run.id, 0.0, config, use=BudgetUse.DEVELOPMENT)
    stored = world.runs.get(run.id)
    assert stored is not None and stored.status == RunStatus.STOPPED_CAP

    other = World(tmp_path / "analysis", ref)
    stopped, _ = other.run(config, capped_script, cap=0.08)
    assert stopped.status == RunStatus.STOPPED_CAP
    with pytest.raises(ExtendRefused, match="analysis cap"):
        extend(other.runs, stopped.id, 0.30, config, use=BudgetUse.DEVELOPMENT)


def test_extend_run_resumes_a_post_cap_stop(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script)
    code, out = _extend_run(world, config, script, run.id, "--post-cap", "0", "--name", "case_x")
    assert code == 0
    assert json.loads((out / "case_x.json").read_text(encoding="utf-8"))["status"] == "stopped_cap"
    code, out = _extend_run(world, config, script, run.id, "--post-cap", "0.3", "--name", "case_x")
    assert code == 0
    report = json.loads((out / "case_x.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run.id and report["status"] == "finished"
    assert report["chains"] and report["lopa"]


def test_r38_stop_still_comes_at_ranked_after_the_post_steps(
    tmp_path: Path, ref: ReferenceSet, config: Config, capped_script: Any
) -> None:
    world = World(tmp_path, ref)
    run, _ = world.run(config, capped_script, cap=0.08)
    assert run.status == RunStatus.STOPPED_CAP and run.step == "ranked"
    started = world.steps_started(run.id)
    assert list(dict.fromkeys(started))[-len(POST_STEPS) - 1 :] == [*POST_STEPS, "ranked"]
    hits = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT]
    assert hits[-1]["reason"] == "questions left open"


# --- LOPA (3.2; Q10) and recommendations (3.4; Q12, G17) --------------------------------------


def test_code_only_lopa_makes_no_model_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    small = with_run_caps(config, lopa_top_n=2)
    world = World(tmp_path, ref)
    run, transport = world.run(small, post_script(severities={g: "S4" for g in range(GROUPS)}))
    assert run.status == RunStatus.FINISHED
    records = world.runs.lopa_records(run.id)
    code_only = [r for r in records if CODE_ONLY_FLAG in r.flags]
    full = [r for r in records if CODE_ONLY_FLAG not in r.flags]
    lines = [x for x in world.report(small, run.id)["shortlist"] if x["target_kind"] == "finding"]
    assert len(lines) > 3
    assert len(full) == 2 and len(code_only) == len(lines) - 2
    # v2 requests carry handles only: the targets sent are each call's record IDs
    argued = {
        target
        for call in world.runs.model_calls(run.id)
        if call.job == "lopa_argument"
        for target in call.record_ids
    }
    assert argued == {r.target_id for r in full}
    for record in code_only:
        assert record.model_call_id is None
        assert all(layer.reason == NOT_ARGUED for layer in record.layers)
    assert any(record.layers for record in code_only)
    done = [e.payload for e in world.runs.events(run.id) if e.type == EventType.LOPA_DONE]
    assert sorted(p["kind"] for p in done) == sorted(
        ["full"] * 2 + ["code_only"] * (len(lines) - 2)
    )


def test_recommendations_go_in_shortlist_order_and_include_code_only_lines(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    small = with_run_caps(config, lopa_top_n=2, recommendation_batch_size=3)
    world = World(tmp_path, ref)
    grades = {g: ("S5" if g % 2 else "S4") for g in range(GROUPS)}
    run, transport = world.run(small, post_script(severities=grades))
    assert run.status == RunStatus.FINISHED
    report = world.report(small, run.id)
    eligible = [
        line["target_id"]
        for line in report["shortlist"]
        if line["complete"] and line["gap"] is not None and line["gap"] > 1
    ]
    # v2 requests carry handles only: the targets sent are each call's record IDs, in order
    sent = [
        target
        for call in world.runs.model_calls(run.id)
        if call.job == "recommendation"
        for target in call.record_ids
    ]
    assert sent == eligible
    assert any(
        line["lopa"] == "code_only" for line in report["shortlist"] if line["target_id"] in sent
    )
    assert {r.target_id for r in world.runs.recommendations(run.id)} == set(eligible)
    for job, request in transport.sent:
        if job == "recommendation":
            assert len(block(request, "lines")) <= 3


# --- failures (G3) ----------------------------------------------------------------------------


def test_each_post_step_failure_leaves_the_run_going_with_a_flag(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "a", ref)
    failing = frozenset({"chain_severity", "lopa_argument", "recommendation"})
    run, _ = world.run(config, post_script(connector=first_two, fail=failing))
    assert run.status == RunStatus.FINISHED
    (the_chain,) = world.runs.chains(run.id)
    assert the_chain.severity_class is None
    assert (the_chain.severity_reason or "").startswith("not assessed")
    records = world.runs.lopa_records(run.id)
    assert records and all(r.target_id != the_chain.id for r in records)
    assert all(CODE_ONLY_FLAG in r.flags for r in records)
    assert all(any(f.startswith(ARGUMENT_FAILED_FLAG) for f in r.flags) for r in records)
    assert world.runs.recommendations(run.id) == []
    report = world.report(config, run.id)
    by_target = {line["target_id"]: line for line in report["shortlist"]}
    assert by_target[the_chain.id]["no_lopa_reason"] == "no severity"
    eligible = [line for line in report["shortlist"] if line["complete"] and line["gap"] > 1]
    assert eligible and all(
        "no recommendation: the call failed" in line["flags"] for line in eligible
    )

    other = World(tmp_path / "b", ref)
    run, _ = other.run(config, post_script(connector=first_two, fail=frozenset({"connector"})))
    assert run.status == RunStatus.FINISHED
    assert other.runs.chains(run.id) == []
    assert other.runs.lopa_records(run.id)  # the run went on
    assert other.report(config, run.id)["connector"]["outcome"] == "invalid"


def test_connector_input_carries_the_fact_ids_as_data(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """G7 on connector/v2: the scenario lines and the facts go in as data, each with its
    handle; the lines show no finding ID, in display order; the facts are sorted by ID."""
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script())
    (request,) = [r for job, r in transport.sent if job == "connector"]
    facts = block(request, "facts")
    assert [f["handle"] for f in facts] == [f"P{i}" for i in range(1, len(facts) + 1)]
    assert [f["fact_id"] for f in facts] == sorted(f["fact_id"] for f in facts)
    scenarios = block(request, "scenarios")
    assert [s["handle"] for s in scenarios] == [f"L{i}" for i in range(1, len(scenarios) + 1)]
    assert {"handle", "cause", "consequence", "failing_component_ids", "severity_class"} <= set(
        scenarios[0]
    )
    assert "finding_id" not in scenarios[0] and "f:" not in json.dumps(scenarios)
    lines = [x for x in world.report(config, run.id)["shortlist"] if x["target_kind"] == "finding"]
    assert len(scenarios) == len(lines)
    assert "plant_id" not in block(request, "plant")


def test_a_rejected_chain_is_logged_with_its_reason_and_listed(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    def bad(scenarios: list[dict[str, Any]], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            *first_two(scenarios, facts),
            {"links": [scenarios[0]["handle"], "L999"], "description": "d", "reason": "r"},
            {"links": [facts[0]["handle"], facts[1]["handle"]], "description": "d", "reason": "r"},
        ]

    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=bad))
    assert len(world.runs.chains(run.id)) == 1
    rejected = world.report(config, run.id)["chains_rejected"]
    assert len(rejected) == 2 and all(r["reason"] for r in rejected)
    added = [e.payload for e in world.runs.events(run.id) if e.type == EventType.CHAIN_ADDED]
    assert added == [{"chain_id": world.runs.chains(run.id)[0].id, "links": 3}]


# --- the scripts (P3-1b, Q15, Q16, R38) -------------------------------------------------------


def _settings(world: World) -> Any:
    from guideword.settings import Settings  # noqa: PLC0415

    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{(world.dir / 'g.db').as_posix()}",
    )


def _extend_run(
    world: World, config: Config, script: Script, *args: str, ledger: Path | None = None
) -> tuple[int, Path]:
    import extend_run  # noqa: PLC0415

    from guideword.gateway.fake import catalog_for  # noqa: PLC0415

    out = world.dir / "phase3"
    code = extend_run.main(
        ["--use", "development", *args],
        transport=FakeTransport(script, catalog_for(config)),
        config=config,
        settings=_settings(world),
        ledger=LaptopLedger(ledger or world.dir / "ledger.jsonl"),
        clock=lambda: NOW,
        out_dir=out,
    )
    return code, out


def _phases(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return {json.loads(line)["phase"] for line in lines if line.strip()}


def test_scripts_take_the_phase_from_the_flag(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    import four_tier  # noqa: PLC0415
    import run_case  # noqa: PLC0415
    import run_test5a  # noqa: PLC0415
    import screen_check  # noqa: PLC0415

    from guideword.gateway.fake import catalog_for  # noqa: PLC0415

    script = post_script()
    for flag, expected in (([], "3"), (["--phase", "2"], "2")):
        world = World(tmp_path / f"case{expected}", ref)
        ledger = world.dir / "ledger.jsonl"
        code = run_case.main(
            ["--use", "development", str(EXAMPLE), *flag],
            transport=FakeTransport(script, catalog_for(config)),
            config=config,
            settings=_settings(world),
            ledger=LaptopLedger(ledger),
            clock=lambda: NOW,
            out_dir=world.dir / "5b",
        )
        assert code == 0 and _phases(ledger) == {expected}

    world = World(tmp_path / "extend", ref)
    run = phase_2_run(world, config, script)
    ledger = world.dir / "extend-ledger.jsonl"
    code, _ = _extend_run(world, config, script, run.id, "--name", "case_x", ledger=ledger)
    assert code == 0 and _phases(ledger) == {"3"}

    assert (
        screen_check._arguments(["--use", "development", str(EXAMPLE), "--cap", "1"]).phase == "3"
    )
    assert (
        screen_check._arguments(
            ["--use", "development", str(EXAMPLE), "--cap", "1", "--phase", "2"]
        ).phase
        == "2"
    )
    assert run_test5a._arguments(["--case", "d", "--use", "development"]).phase == "3"
    assert four_tier._arguments(["--cap", "1"]).phase == "3"
    assert four_tier._arguments(["--cap", "1", "--phase", "2"]).phase == "2"


def test_extend_run_writes_the_phase_3_report(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script)
    code, out = _extend_run(world, config, script, run.id, "--post-cap", "0.3", "--name", "case_x")
    assert code == 0
    report = json.loads((out / "case_x.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run.id and report["status"] == "finished"
    assert report["post_spend_cap_usd"] == 0.3
    assert {"shortlist", "chains", "lopa", "recommendations", "pre_r50"} <= set(report)
    assert report["chains"] and report["lopa"]
    # already extended: refused, nothing changed
    assert _extend_run(world, config, script, run.id, "--name", "case_x")[0] == 1


def test_a_post_step_cap_stop_is_reported_not_scored(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    from guideword.bench.results import _scored  # noqa: PLC0415

    world = World(tmp_path, ref)
    script = post_script()
    run = phase_2_run(world, config, script)
    code, out = _extend_run(world, config, script, run.id, "--post-cap", "0", "--name", "case_x")
    assert code == 0
    report = json.loads((out / "case_x.json").read_text(encoding="utf-8"))
    assert report["status"] == "stopped_cap"
    scored = _scored(report, "hybrid", [["outside"]])
    assert scored == {"status": "stopped_cap", "scored": False}


def test_extend_run_skips_a_run_whose_records_fail_to_load(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script()
    run = phase_2_run(world, config, script)
    with world.sessions.begin() as session:
        row = session.scalars(select(db.FindingRow).where(db.FindingRow.run_id == run.id)).first()
        assert row is not None
        row.record = {**row.record, "no_such_field": 1}
    code, out = _extend_run(world, config, script, run.id, "--name", "case_x")
    assert code == 1
    report = json.loads((out / "case_x.json").read_text(encoding="utf-8"))
    assert report["status"] == "skipped" and report["reason"]
    stored = world.runs.get(run.id)
    assert stored is not None and stored.status == RunStatus.FINISHED and stored.step == "ranked"


# --- connector/v2 plan (approved 2026-10-21): the run ID, run_extended, re-runs -----------------

POST_HASH_FREE_CAPS = (
    "connector_max_chains",
    "lopa_batch_size",
    "recommendation_batch_size",
    "lopa_top_n",
)


def with_prompt(config: Config, name: str, version: str) -> Config:
    routing = config.routing.model_copy(
        update={"prompts": {**config.routing.prompts, name: version}}
    )
    return config.model_copy(update={"routing": routing})


def test_a_post_step_prompt_version_is_not_in_the_run_id_inputs(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    run = World(tmp_path, ref).start(config)
    assert not set(PHASE_3_PROMPTS) & set(run.prompt_versions)
    assert not set(POST_HASH_FREE_CAPS) & set(run.caps)


def test_changing_a_post_step_prompt_version_keeps_the_run_id(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    first = World(tmp_path / "a", ref).start(config)
    for i, name in enumerate(sorted(PHASE_3_PROMPTS)):
        other = World(tmp_path / f"b{i}", ref).start(with_prompt(config, name, "v9"))
        assert other.id == first.id, name


@pytest.mark.parametrize("key", POST_HASH_FREE_CAPS)
def test_changing_lopa_top_n_keeps_a_runs_id(
    key: str, tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """`lopa_top_n` and the other three post-step caps are recorded on `run_extended`, not
    hashed into the run ID (Bhargavi, Q5)."""
    first = World(tmp_path / "a", ref).start(config)
    value = int(getattr(config.caps.run, key)) + 3
    other = World(tmp_path / "b", ref).start(with_run_caps(config, **{key: value}))
    assert other.id == first.id


def test_a_new_run_records_its_post_prompt_versions_on_run_extended(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=first_two))
    assert run.status == RunStatus.FINISHED
    (event,) = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED]
    assert event.payload["prompt_versions"] == {
        # the post-step prompts, Phase 4's precedent judge included
        name: config.routing.prompts[name]
        for name in sorted(POST_PROMPTS)
    }
    assert event.payload["prompt_versions"]["connector"] == "v2"
    for key in POST_HASH_FREE_CAPS:
        assert event.payload["settings"][key] == {
            "value": int(getattr(config.caps.run, key)),
            "source": "config",
        }
    chains_started = next(
        e.seq
        for e in world.runs.events(run.id)
        if e.type == EventType.STEP_STARTED and e.payload["step"] == "chains"
    )
    assert event.seq > chains_started  # emitted by the chains step, before its call


def test_connector_v2_maps_handles_on_a_run_and_rejects_an_unknown_one(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    captured: dict[str, Any] = {}

    def answer(
        scenarios: list[dict[str, Any]], facts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        captured["scenarios"], captured["facts"] = scenarios, facts
        return [
            *first_two(scenarios, facts),
            {"links": ["L1", "l2"], "description": "d", "reason": "r"},
        ]

    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=answer))
    (chain,) = world.runs.chains(run.id)
    report = world.report(config, run.id)
    leads = {
        x["position"]: x["target_id"] for x in report["shortlist"] if x["target_kind"] == "finding"
    }
    first, second = (leads[k] for k in sorted(leads)[:2])
    assert chain.links[:2] == [first, second]
    assert chain.links[2] == captured["facts"][0]["fact_id"]
    (rejected,) = report["chains_rejected"]
    assert rejected["links"] == ["L1", "l2"] and "not a handle" in rejected["reason"]


def test_handles_are_built_after_the_input_is_cut(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "full", ref)
    _, transport = world.run(config, post_script())
    (request,) = [r for job, r in transport.sent if job == "connector"]
    full = block(request, "scenarios")
    assert len(full) > 2
    from guideword.gateway.estimate import estimate_cost  # noqa: PLC0415
    from guideword.schema.enums import Tier  # noqa: PLC0415

    prices = config.models.tiers[Tier(config.routing.jobs["connector"])]
    whole = estimate_cost(prices, request["messages"], None, 0).input_tokens
    cut = World(tmp_path / "cut", ref)
    tight = with_run_caps(config, connector_max_input_tokens=whole - 1)
    _, transport = cut.run(tight, post_script())
    (request,) = [r for job, r in transport.sent if job == "connector"]
    sent = block(request, "scenarios")
    assert 0 < len(sent) < len(full)
    assert [s["handle"] for s in sent] == [f"L{i}" for i in range(1, len(sent) + 1)]


def _rerun_world(tmp_path: Path, ref: ReferenceSet, config: Config) -> tuple[World, Run]:
    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=first_two, severities={0: "S4", 1: "S5"}))
    assert run.status == RunStatus.FINISHED
    assert world.runs.chains(run.id) and world.runs.lopa_records(run.id)
    assert world.runs.recommendations(run.id)
    return world, run


def changed(config: Config) -> Config:
    """A re-run's config: a request that differs from the first pass (as a new prompt version
    would), so the connector is asked again instead of read from the cache."""
    return with_run_caps(config, connector_max_chains=9)


def _second_chain(
    scenarios: list[dict[str, Any]], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "links": [scenarios[1]["handle"], scenarios[2]["handle"]],
            "description": "d",
            "reason": "r",
        }
    ]


def test_rerun_from_chains_redoes_chain_severity_lopa_and_recommendations(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    old_chain_ids = {c.id for c in world.runs.chains(run.id)}
    before = len(world.steps_started(run.id))
    rerun = extend(
        world.runs, run.id, 0.30, changed(config), rerun_from="chains", use=BudgetUse.DEVELOPMENT
    )
    assert rerun.id == run.id and rerun.status == RunStatus.RUNNING and rerun.step == "chains"
    gateway, transport = world.gateway(changed(config), post_script(connector=_second_chain))
    assert drive(world.runs, run.id, world.steppers(changed(config), gateway)) == RunStatus.FINISHED
    assert {job for job, _ in transport.sent} <= POST_JOBS
    assert list(dict.fromkeys(world.steps_started(run.id)[before:])) == [*POST_STEPS, "ranked"]
    new_chains = {c.id for c in world.runs.chains(run.id)}
    assert new_chains and new_chains != old_chain_ids
    assert any(r.target_id in new_chains for r in world.runs.lopa_records(run.id))
    done = world.runs.get(run.id)
    assert done is not None and done.id == run.id


def test_rerun_supersedes_old_records_through_the_event_log_and_deletes_nothing(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    analysis = snapshot(world, run.id)
    old = {
        "chain": [c.model_dump(mode="json") for c in world.runs.chains(run.id)],
        "lopa": [r.model_dump(mode="json") for r in world.runs.lopa_records(run.id)],
        "recommendation": [r.model_dump(mode="json") for r in world.runs.recommendations(run.id)],
        "model_call": [
            c.model_dump(mode="json") for c in world.runs.model_calls(run.id) if c.job in POST_JOBS
        ],
    }
    first_pass = max(e.seq for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED)
    extend(world.runs, run.id, 0.30, config, rerun_from="chains", use=BudgetUse.DEVELOPMENT)
    event = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED][-1]
    assert event.payload["rerun_from"] == "chains"
    kept = world.runs.superseded(run.id)
    for kind, records in old.items():
        assert [k.record for k in kept if k.kind == kind] == records, kind
    assert {k.pass_seq for k in kept} == {first_pass}
    assert {k.superseded_seq for k in kept} == {event.seq}
    assert sorted(event.payload["superseded_ids"]) == sorted(
        r["id"] for records in old.values() for r in records
    )
    # cleared from the live tables, so the re-run can write the same IDs; the analysis untouched
    assert world.runs.chains(run.id) == [] and world.runs.lopa_records(run.id) == []
    assert not [c for c in world.runs.model_calls(run.id) if c.job in POST_JOBS]
    after = snapshot(world, run.id)
    for table in ("questions", "findings", "hypotheses", "agent_steps", "tool_calls"):
        assert after[table] == analysis[table], table


def test_the_run_dump_lists_superseded_records_marked_as_superseded(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    from guideword.api.live import LiveRuns  # noqa: PLC0415

    world, run = _rerun_world(tmp_path, ref, config)
    old_chains = world.runs.chains(run.id)
    extend(
        world.runs, run.id, 0.30, changed(config), rerun_from="chains", use=BudgetUse.DEVELOPMENT
    )
    gateway, _ = world.gateway(changed(config), post_script(connector=_second_chain))
    drive(world.runs, run.id, world.steppers(changed(config), gateway))
    live = LiveRuns(
        world.sessions,
        config=config,
        ref=ref,
        gateway_factory=lambda _, __: gateway,
        clock=lambda: NOW,
    )
    dump = live.dump(run.id)
    superseded = [s for s in dump.superseded if s.kind == "chain"]
    assert [s.record["id"] for s in superseded] == [c.id for c in old_chains]
    assert all(s.superseded_seq > s.pass_seq for s in dump.superseded)
    assert {c.id for c in dump.chains}.isdisjoint({c.id for c in old_chains})


def test_rerun_serves_unchanged_requests_from_the_cache_at_zero_cost(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    spent = world.runs.get(run.id).spent_usd  # type: ignore[union-attr]
    extend(world.runs, run.id, 0.30, config, rerun_from="chains", use=BudgetUse.DEVELOPMENT)
    gateway, transport = world.gateway(
        config, post_script(connector=first_two, severities={0: "S4", 1: "S5"})
    )
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    assert transport.sent == []  # every post request is the same as before: all cache hits
    post = [c for c in world.runs.model_calls(run.id) if c.job in POST_JOBS]
    assert post and all(c.cache_hit and c.cost_usd == 0 for c in post)
    done = world.runs.get(run.id)
    assert done is not None and done.spent_usd == pytest.approx(spent)


def test_rerun_spend_matches_records_including_superseded_calls(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    extend(
        world.runs, run.id, 0.30, changed(config), rerun_from="chains", use=BudgetUse.DEVELOPMENT
    )
    gateway, _ = world.gateway(changed(config), post_script(connector=_second_chain))
    drive(world.runs, run.id, world.steppers(changed(config), gateway))
    with world.runs.step(run.id) as writer:
        assert spend_matches_records(writer)
    done = world.runs.get(run.id)
    live = sum(c.cost_usd for c in world.runs.model_calls(run.id))
    old = sum(k.record["cost_usd"] for k in world.runs.superseded(run.id) if k.kind == "model_call")
    assert done is not None and done.spent_usd == pytest.approx(live + old)


def test_rerun_is_refused_for_an_unfinished_run_or_one_never_extended(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    from guideword.schema.enums import OverrideAction  # noqa: PLC0415
    from guideword.schema.records import Override  # noqa: PLC0415

    unfinished = World(tmp_path / "a", ref)
    started = unfinished.start(config)
    with pytest.raises(ExtendRefused, match="not finished"):
        extend(
            unfinished.runs,
            started.id,
            0.30,
            config,
            rerun_from="chains",
            use=BudgetUse.DEVELOPMENT,
        )
    never = World(tmp_path / "b", ref)
    old = phase_2_run(never, config, post_script())
    with pytest.raises(ExtendRefused, match="chains step has not run"):
        extend(never.runs, old.id, 0.30, config, rerun_from="chains", use=BudgetUse.DEVELOPMENT)
    # Q3: refused while an override names a post record
    world, run = _rerun_world(tmp_path / "c", ref, config)
    lopa = world.runs.lopa_records(run.id)[0]
    override = Override(
        id=ids.override_id(lopa.id, OverrideAction.ACCEPT, None),
        run_id=run.id,
        target_id=lopa.id,
        action=OverrideAction.ACCEPT,
        new_value=None,
        reason="r",
        by="B",
        at=NOW,
    )
    with world.runs.step(run.id) as writer:
        writer.add_override(override)
    with pytest.raises(ExtendRefused, match="override"):
        extend(world.runs, run.id, 0.30, config, rerun_from="chains", use=BudgetUse.DEVELOPMENT)
    assert world.runs.superseded(run.id) == []


def test_copy_and_clear_happen_in_one_transaction(
    tmp_path: Path, ref: ReferenceSet, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from guideword.runs.store import StepWriter  # noqa: PLC0415

    world, run = _rerun_world(tmp_path, ref, config)
    before = snapshot(world, run.id)
    chains = world.runs.chains(run.id)

    def broken(self: StepWriter, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the clear failed")

    monkeypatch.setattr(StepWriter, "_clear_post_records", broken)
    with pytest.raises(RuntimeError, match="the clear failed"):
        extend(world.runs, run.id, 0.30, config, rerun_from="chains", use=BudgetUse.DEVELOPMENT)
    assert world.runs.superseded(run.id) == []
    assert world.runs.chains(run.id) == chains
    assert snapshot(world, run.id) == before
    stored = world.runs.get(run.id)
    assert stored is not None and stored.status == RunStatus.FINISHED


def test_extend_run_reruns_from_chains(tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    script = post_script(connector=_second_chain)
    args = (run.id, "--rerun-from", "chains", "--post-cap", "0.3", "--name", "case_x")
    code, out = _extend_run(world, config, script, *args)
    assert code == 0
    report = json.loads((out / "case_x.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run.id and report["status"] == "finished"
    assert report["chains"] and world.runs.superseded(run.id)


# --- target-handles plan (approved 2026-10-21): handles for chain and line targets ---------------

# lopa_argument moved on to v3 (demo-fixes plan); the other two stay at v2
V2_POST_PROMPTS = {"severity_chain": "v2", "lopa_argument": "v3", "recommendation": "v2"}
HANDLE_TOKEN = re.compile(r"\b[LPC]\d+\b")
# a finding ID (`f:<question kind prefix>:`) or a chain ID (`ch:`), not "part_of:" inside a
# question ID
FINDING_OR_CHAIN_ID = re.compile(
    r"(?<![\w-])(?:f:(?:m|pair|env|nf|proc|work|dust|relief|ai|eng):|ch:)"
)


def _sent(transport: FakeTransport, job: str) -> list[dict[str, Any]]:
    return [r for j, r in transport.sent if j == job]


def _many_chains(
    scenarios: list[dict[str, Any]], facts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Seven chains of consecutive lines, each text naming its links by connector handle."""
    out = []
    for i in range(7):
        a, b = scenarios[i]["handle"], scenarios[i + 1]["handle"]
        out.append({"links": [a, b], "description": f"{a} then {b}", "reason": f"{a} sets up {b}"})
    return out


def test_the_three_later_post_prompts_are_routed(config: Config) -> None:
    assert {k: config.routing.prompts[k] for k in V2_POST_PROMPTS} == V2_POST_PROMPTS


def test_chain_severity_goes_in_batches_and_re_asks_left_out_chains_once(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Q1: batches of `chain_severity_batch_size` (5); the handles a batch's answer leaves out
    are asked once more, alone."""
    asked: list[list[str]] = []

    def rate(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        asked.append([c["handle"] for c in chains])
        return chains if len(asked) > 1 else chains[:3]  # the first answer leaves out two

    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=_many_chains, rate=rate))
    assert run.status == RunStatus.FINISHED
    assert config.caps.run.chain_severity_batch_size == 5
    assert asked[0] == ["C1", "C2", "C3", "C4", "C5"]
    assert asked[1] == ["C1", "C2"]  # exactly the two left out, renumbered from C1
    assert asked[2] == ["C1", "C2"]  # the other two chains of the seven
    assert all(c.severity_class is not None for c in world.runs.chains(run.id))


def test_the_re_ask_names_exactly_the_missing_handles_and_the_answer_count_is_checked(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    def rate(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return chains if len(chains) < 5 else [chains[0], chains[3]]

    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=_many_chains, rate=rate))
    first, again = _sent(transport, "chain_severity")[:2]
    sent_first = [c["description"] for c in block(first, "chains")]
    sent_again = [c["description"] for c in block(again, "chains")]
    assert sent_again == [sent_first[1], sent_first[2], sent_first[4]]
    summary = [
        e.payload
        for e in world.runs.events(run.id)
        if e.type == EventType.STEP_FINISHED and e.payload.get("step") == "chain_severity"
    ][0]
    assert summary["sent"] == 5 and summary["answered"] == 2
    assert summary["missing"] == ["C2", "C3", "C5"]


def test_a_chain_left_out_twice_is_not_assessed(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    first: dict[str, str] = {}

    def rate(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Never answers the first chain it is shown (its text is code's, without handles)."""
        first.setdefault("description", chains[0]["description"])
        return [c for c in chains if c["description"] != first["description"]]

    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=_many_chains, rate=rate))
    chains = world.runs.chains(run.id)
    left = [c for c in chains if c.severity_class is None]
    assert len(left) == 1
    assert left[0].severity_reason is not None and "not assessed" in left[0].severity_reason
    assert len([c for c in chains if c.severity_class is not None]) == len(chains) - 1


def test_chain_severity_v2_maps_chain_handles_back_and_drops_an_unknown_one(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    def rate(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        extra = {**chains[0], "handle": "C99"}
        return [*chains, extra]

    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=_many_chains, rate=rate))
    assert run.status == RunStatus.FINISHED
    assert all(c.severity_class is not None for c in world.runs.chains(run.id))


def test_lopa_argument_v2_maps_line_and_chain_targets_back_and_drops_an_unknown_one(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=first_two, applies=True))
    requests = _sent(transport, "lopa_argument")
    assert requests
    handles = [line["handle"] for r in requests for line in block(r, "lines")]
    assert any(h.startswith("L") for h in handles) and any(h.startswith("C") for h in handles)
    argued = [r for r in world.runs.lopa_records(run.id) if r.model_call_id]
    assert argued and all(any(layer.applies for layer in r.layers) for r in argued)
    # an unknown target handle drops that item: it is left out, not a failed call
    other = World(tmp_path / "unknown", ref)

    def wrong(job: str, request: dict[str, Any]) -> Reply:
        if job == "lopa_argument":
            return reply({"lines": [{"target": "L99", "layers": []}]})
        return post_script(connector=first_two)(job, request)

    run2, _ = other.run(config, wrong)
    records = [r for r in other.runs.lopa_records(run2.id) if r.layers]
    assert records and all(LEFT_OUT_FLAG in r.flags for r in records if r.model_call_id)


def test_recommendation_v2_maps_line_and_chain_targets_back_and_drops_an_unknown_one(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=first_two, severities={0: "S5"}))
    recs = world.runs.recommendations(run.id)
    targets = {r.target_id for r in recs}
    assert recs and targets <= {r.target_id for r in world.runs.lopa_records(run.id)}
    other = World(tmp_path / "unknown", ref)

    def wrong(job: str, request: dict[str, Any]) -> Reply:
        if job == "recommendation":
            return reply({"recommendations": [{"target": "C99", "action": "a", "reason": "r"}]})
        return post_script(connector=first_two, severities={0: "S5"})(job, request)

    run2, _ = other.run(config, wrong)
    assert other.runs.recommendations(run2.id) == []
    assert run2.status == RunStatus.FINISHED


def test_no_v2_prompt_input_shows_a_finding_or_chain_id(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    _, transport = world.run(config, post_script(connector=first_two, severities={0: "S5"}))
    for job in ("chain_severity", "lopa_argument", "recommendation"):
        requests = _sent(transport, job)
        assert requests, job
        for request in requests:
            text = request["messages"][0]["content"] + request["messages"][1]["content"]
            assert not FINDING_OR_CHAIN_ID.search(text), (job, FINDING_OR_CHAIN_ID.search(text))


def test_no_v2_prompt_or_user_message_says_batch_and_each_states_its_count(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    _, transport = world.run(config, post_script(connector=first_two, severities={0: "S5"}))
    for job, block_name in (
        ("chain_severity", "chains"),
        ("lopa_argument", "lines"),
        ("recommendation", "lines"),
    ):
        for request in _sent(transport, job):
            system, user = (m["content"] for m in request["messages"])
            assert "batch" not in (system + user).lower(), job
            items = block(request, block_name)
            handles = ", ".join(i["handle"] for i in items)
            assert f"There are **{len(items)} " in system and handles in system, job
            assert str(len(items)) in user and handles in user, job


def test_no_chain_text_sent_to_a_v2_prompt_contains_a_connector_handle(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script(connector=_many_chains, severities={0: "S5"}))
    chains = world.runs.chains(run.id)
    assert chains
    for chain in chains:
        assert not HANDLE_TOKEN.search(chain.description) and not HANDLE_TOKEN.search(chain.reason)
        assert HANDLES_REPLACED_FLAG in chain.flags
    for job in ("chain_severity", "lopa_argument", "recommendation"):
        for request in _sent(transport, job):
            for item in block(request, "chains" if job == "chain_severity" else "lines"):
                words = item.get("description", "") + json.dumps(item.get("scenario", {}))
                assert not re.search(r"\bL\d+\b|\bP\d+\b", words), (job, words)


def test_the_connectors_raw_answer_is_unchanged_in_its_model_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=_many_chains))
    (call,) = [c for c in world.runs.model_calls(run.id) if c.job == "connector"]
    assert "L1 then L2" in call.raw_response
    assert all("L1 then" not in c.description for c in world.runs.chains(run.id))


def test_a_chain_with_no_severity_is_on_the_shortlist_flagged_no_severity_no_lopa(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    from guideword.api.live import LiveRuns  # noqa: PLC0415

    world = World(tmp_path, ref)
    run, _ = world.run(config, post_script(connector=first_two, rate=lambda chains: []))
    (chain,) = world.runs.chains(run.id)
    assert chain.severity_class is None
    rows = [x for x in world.report(config, run.id)["shortlist"] if x["target_id"] == chain.id]
    assert len(rows) == 1 and NO_SEVERITY_NO_LOPA in rows[0]["flags"]
    gateway, _ = world.gateway(config, post_script())
    live = LiveRuns(
        world.sessions,
        config=config,
        ref=ref,
        gateway_factory=lambda _, __: gateway,
        clock=lambda: NOW,
    )
    (item,) = [i for i in live.shortlist(run.id) if i.target_id == chain.id]
    assert NO_SEVERITY_NO_LOPA in item.flags and item.lopa is None


# --- demo-fixes plan (approved 2026-10-21): retry a finished run's failed questions ---------------

FAILING_SECTION = "m:S-L-12:"


def _failing(job: str, request: dict[str, Any]) -> Reply:
    """S-L-12's questions fail at every level (invalid twice); everything else as post_script."""
    if job.startswith("specialist") and any(
        q["id"].startswith(FAILING_SECTION) for q in block(request, "questions")
    ):
        return reply("not json")
    return post_script(connector=first_two)(job, request)


def _with_failed(tmp_path: Path, ref: ReferenceSet, config: Config) -> tuple[World, Run, set[str]]:
    world = World(tmp_path, ref)
    run, _ = world.run(config, _failing)
    assert run.status == RunStatus.FINISHED
    failed = {q.id for q in world.runs.questions(run.id) if q.status == QuestionStatus.FAILED}
    assert failed and all(q.startswith(FAILING_SECTION) for q in failed)
    return world, run, failed


def test_retry_failed_asks_each_failed_question_alone_and_makes_no_orchestrator_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, failed = _with_failed(tmp_path, ref, config)
    extend(
        world.runs,
        run.id,
        0.30,
        config,
        retry_failed=True,
        retry_cap_usd=0.30,
        use=BudgetUse.DEVELOPMENT,
    )
    gateway, transport = world.gateway(config, post_script(connector=first_two))
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    jobs = [job for job, _ in transport.sent]
    assert "orchestrator" not in jobs and "plant_screen" not in jobs
    asked = [
        [q["id"] for q in block(r, "questions")]
        for j, r in transport.sent
        if j.startswith("specialist")
    ]
    assert all(len(a) == 1 for a in asked)
    assert {a[0] for a in asked} == failed
    assert {j for j, _ in transport.sent if j.startswith("specialist")} == {"specialist_hard"}
    after = {q.id: q for q in world.runs.questions(run.id)}
    assert all(after[q].status == QuestionStatus.ANSWERED for q in failed)


def test_retry_failed_keeps_the_run_id_and_every_checked_question(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, failed = _with_failed(tmp_path, ref, config)
    checked = {q.id: q for q in world.runs.questions(run.id) if q.id not in failed}
    extended = extend(
        world.runs,
        run.id,
        0.30,
        config,
        retry_failed=True,
        retry_cap_usd=0.30,
        use=BudgetUse.DEVELOPMENT,
    )
    assert extended.id == run.id and extended.step == "retry_failed"
    assert extended.spend_cap_usd == pytest.approx(run.spend_cap_usd + 0.30)
    assert extended.caps == run.caps and extended.prompt_versions == run.prompt_versions
    gateway, _ = world.gateway(config, post_script(connector=first_two))
    drive(world.runs, run.id, world.steppers(config, gateway))
    done = world.runs.get(run.id)
    assert done is not None and done.id == run.id
    now = {q.id: q for q in world.runs.questions(run.id)}
    assert all(now[i] == q for i, q in checked.items())


def test_retry_failed_rates_only_new_findings_then_reruns_from_chains(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, failed = _with_failed(tmp_path, ref, config)
    old_findings = {f.id for f in world.runs.findings(run.id)}
    before = len(world.steps_started(run.id))
    extend(
        world.runs,
        run.id,
        0.30,
        config,
        retry_failed=True,
        retry_cap_usd=0.30,
        use=BudgetUse.DEVELOPMENT,
    )
    gateway, transport = world.gateway(config, post_script(connector=first_two))
    drive(world.runs, run.id, world.steppers(config, gateway))
    new = {f.id for f in world.runs.findings(run.id)} - old_findings
    assert new and all(
        next(f for f in world.runs.findings(run.id) if f.id == i).question_id in failed for i in new
    )
    rated = {
        f["finding_id"]
        for j, r in transport.sent
        if j == "severity_reason"
        for f in block(r, "findings")
    }
    # one finding per scenario is sent, and its class copied to the rest (R48): only new
    # findings are sent, none of the old, and every new finding ends up rated
    assert rated and rated <= new and not rated & old_findings
    stored = {f.id: f for f in world.runs.findings(run.id)}
    assert all(stored[i].severity_class is not None for i in new)
    steps = list(dict.fromkeys(world.steps_started(run.id)[before:]))
    assert steps == ["retry_failed", "severity", *POST_STEPS, "ranked"]
    assert world.runs.superseded(run.id)  # the old post records, kept
    event = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED][-1]
    assert sorted(event.payload["retry_failed"]) == sorted(failed)


def test_retry_failed_is_refused_for_an_unfinished_run_or_one_with_no_failed_questions(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    unfinished = World(tmp_path / "a", ref)
    started = unfinished.start(config)
    with pytest.raises(ExtendRefused, match="not finished"):
        extend(
            unfinished.runs,
            started.id,
            0.30,
            config,
            retry_failed=True,
            retry_cap_usd=0.30,
            use=BudgetUse.DEVELOPMENT,
        )
    clean = World(tmp_path / "b", ref)
    run, _ = clean.run(config, post_script(connector=first_two))
    with pytest.raises(ExtendRefused, match="no failed question"):
        extend(
            clean.runs,
            run.id,
            0.30,
            config,
            retry_failed=True,
            retry_cap_usd=0.30,
            use=BudgetUse.DEVELOPMENT,
        )


def test_extend_run_retry_failed_writes_to_the_out_dir(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, _ = _with_failed(tmp_path, ref, config)
    out = tmp_path / "demo"
    args = (run.id, "--retry-failed", "--post-cap", "0.3", "--name", "x", "--out-dir", str(out))
    code, _ = _extend_run(world, config, post_script(connector=first_two), *args)
    assert code == 0
    report = json.loads((out / "x.json").read_text(encoding="utf-8"))
    assert report["run_id"] == run.id and report["status"] == "finished"


def test_a_demo_plant_report_goes_to_bench_demo() -> None:
    import run_case  # noqa: PLC0415

    assert run_case.default_out_dir(REPO / "cases" / "demo" / "williams_geismar.json") == (
        REPO / "bench" / "demo"
    )
    assert run_case.default_out_dir(REPO / "cases" / "dev" / "case_d.json") == (
        REPO / "bench" / "test5" / "5b"
    )
    assert run_case._arguments(
        ["--use", "development", str(EXAMPLE), "--out-dir", "x"]
    ).out_dir == Path("x")


def test_lopa_argument_v3_leaves_valve_states_to_code(config: Config) -> None:
    from guideword.gateway.prompts import load_prompt  # noqa: PLC0415

    assert config.routing.prompts["lopa_argument"] == "v3"
    body = load_prompt("lopa_argument", config).body
    assert "Valve positions, isolation and lock state are checked by code, never by you" in body
    assert "never a valve's position" in body
    assert not re.search(r"(?i)williams|geismar|reboiler|EA-425|HV-[AB]-", body)


# --- lead tie-break plan (approved 2026-10-21): re-run from lopa; the retry summary ---------------


def test_rerun_from_lopa_keeps_chains_and_supersedes_lopa_and_recommendations(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run = _rerun_world(tmp_path, ref, config)
    chains = [c.model_dump(mode="json") for c in world.runs.chains(run.id)]
    old_lopa = {r.id for r in world.runs.lopa_records(run.id)}
    old_recs = {r.id for r in world.runs.recommendations(run.id)}
    kept_calls = {
        c.id for c in world.runs.model_calls(run.id) if c.job in ("connector", "chain_severity")
    }
    before = len(world.steps_started(run.id))
    rerun = extend(world.runs, run.id, 0.30, config, rerun_from="lopa", use=BudgetUse.DEVELOPMENT)
    assert rerun.id == run.id and rerun.step == "lopa"
    superseded = world.runs.superseded(run.id)
    assert {k.kind for k in superseded} == {"lopa", "recommendation", "model_call"}
    assert {k.record["id"] for k in superseded if k.kind == "lopa"} == old_lopa
    assert {k.record["id"] for k in superseded if k.kind == "recommendation"} == old_recs
    assert all(
        k.record["job"] in ("lopa_argument", "recommendation")
        for k in superseded
        if k.kind == "model_call"
    )
    gateway, transport = world.gateway(
        config, post_script(connector=first_two, severities={0: "S4", 1: "S5"})
    )
    assert drive(world.runs, run.id, world.steppers(config, gateway)) == RunStatus.FINISHED
    assert {job for job, _ in transport.sent} <= {"lopa_argument", "recommendation"}
    assert [c.model_dump(mode="json") for c in world.runs.chains(run.id)] == chains
    assert kept_calls <= {c.id for c in world.runs.model_calls(run.id)}
    steps = list(dict.fromkeys(world.steps_started(run.id)[before:]))
    assert steps == ["lopa", "recommendations", "evidence", "ranked"]
    assert world.runs.lopa_records(run.id) and world.runs.recommendations(run.id)
    event = [e for e in world.runs.events(run.id) if e.type == EventType.RUN_EXTENDED][-1]
    assert event.payload["rerun_from"] == "lopa"
    assert event.payload["ranking"] == {"lead_prefers_own_section": True}


def test_after_the_change_the_new_leads_get_lopa_and_recommendations(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """A run started with the rule off, re-run from lopa with it on: every confirmed line's
    lead under the rule has a LOPA record, and a recommendation where its gap is above 1."""
    from guideword.lopa.lines import display_lines  # noqa: PLC0415
    from guideword.schema.enums import ShortlistTier  # noqa: PLC0415

    off = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={
                    "ranking": config.caps.ranking.model_copy(
                        update={"lead_prefers_own_section": False}
                    )
                }
            )
        }
    )
    world = World(tmp_path, ref)

    def screen(job: str, request: dict[str, Any]) -> Reply:
        if job == "plant_screen":
            location = block(request, "plant")["locations"][0]["id"]
            hypothesis = {
                "rank": 1,
                "mechanism": "something outside hits the building",
                "component_ids": [location],
                "chemical_ids": [],
                "failing_component_type": "external",
                "cause_id": "outside_library",
                "cause_text": "outside 0",
                "consequence": "a release",
                "reason": "test",
            }
            return reply({"hypotheses": [hypothesis]})
        return post_script(connector=first_two, severities={g: "S4" for g in range(GROUPS)})(
            job, request
        )

    run, _ = world.run(off, screen)
    assert run.status == RunStatus.FINISHED and world.runs.hypotheses(run.id)
    extend(world.runs, run.id, 0.30, config, rerun_from="lopa", use=BudgetUse.DEVELOPMENT)
    gateway, _ = world.gateway(config, screen)
    drive(world.runs, run.id, world.steppers(config, gateway))
    lines = display_lines(
        world.runs.findings(run.id),
        world.runs.hypotheses(run.id),
        world.runs.questions(run.id),
        world.runs.sections(run.id),
        world.plant,
        ref,
        config.caps,
        prefer_own_section=True,
    )
    leads = [
        line.lead.finding.id for line in lines if line.tier == ShortlistTier.CONFIRMED and line.lead
    ]
    assert leads
    lopa = {r.target_id: r for r in world.runs.lopa_records(run.id)}
    recs = {r.target_id for r in world.runs.recommendations(run.id)}
    for lead in leads:
        assert lead in lopa, lead
        record = lopa[lead]
        if record.complete and record.gap is not None and record.gap > 1:
            assert lead in recs, lead


def test_the_retry_summary_records_the_questions_outcome(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, failed = _with_failed(tmp_path, ref, config)
    extend(
        world.runs,
        run.id,
        0.30,
        config,
        retry_failed=True,
        retry_cap_usd=0.30,
        use=BudgetUse.DEVELOPMENT,
    )
    gateway, _ = world.gateway(config, post_script(connector=first_two))
    drive(world.runs, run.id, world.steppers(config, gateway))
    rows = [
        e.payload
        for e in world.runs.events(run.id)
        if e.type == EventType.STEP_FINISHED
        and e.payload.get("step") == "retry_failed"
        and "question_id" in e.payload
    ]
    assert {r["question_id"] for r in rows} == failed
    assert {r["outcome"] for r in rows} == {"answered"}


def test_with_no_scenario_line_the_chains_step_skips_the_connector(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Emit coverage (contract v1.9): the `chains` summary when nothing reaches the connector,
    checked by its strict model."""
    base = post_script()

    def script(job: str, request: dict[str, Any]) -> Reply:
        if job.startswith("specialist"):
            answers = [
                {"question_id": q["id"], "not_credible": {"reason": "none"}, "findings": []}
                for q in block(request, "questions")
            ]
            return reply({"answers": answers, "added_questions": []})
        return base(job, request)

    world = World(tmp_path, ref)
    run, transport = world.run(config, script)
    assert world.runs.findings(run.id) == []
    assert "connector" not in [job for job, _ in transport.sent]
    [chains] = [
        e.payload
        for e in world.runs.events(run.id)
        if e.type == EventType.STEP_FINISHED and e.payload["step"] == "chains"
    ]
    assert (chains["scenarios"], chains["left_out"]) == (0, 0)
    assert "connector" not in chains


# --- B2 (plan H5, Q9): extension keeps the run's use --------------------------------------------


def test_extend_refuses_another_use(tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
    world = World(tmp_path, ref)
    run = phase_2_run(world, config, post_script())
    with pytest.raises(ExtendRefused, match="development"):
        extend(world.runs, run.id, 0.30, config, use=BudgetUse.VIDEO)
    assert world.runs.get(run.id).step == "ranked"  # type: ignore[union-attr]


def test_extend_stores_a_use_on_a_run_with_none(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    run = phase_2_run(world, config, post_script())
    with world.runs.step(run.id) as writer:
        writer.set_use(None)
    extended = extend(world.runs, run.id, 0.30, config, use=BudgetUse.VIDEO)
    assert extended.use == BudgetUse.VIDEO
