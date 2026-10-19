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

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.fake import FakeTransport, fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.replay import MANIFEST, ReplayTransport, export_replay, load_replay
from guideword.gateway.transport import Reply, ToolCallRequest
from guideword.lopa.credit import NOT_ARGUED
from guideword.lopa.engine import CODE_ONLY_FLAG
from guideword.lopa.step import ARGUMENT_FAILED_FLAG
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs import db
from guideword.runs.case import case_report, drive, prepare_plant, start_case, steppers_for
from guideword.runs.extend import ExtendRefused, extend
from guideword.runs.machine import Stepper, StepResult
from guideword.runs.plants import PlantRepository
from guideword.runs.post_budget import POST_JOBS, POST_STEPS
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
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
EIGHT_STEPS = [
    "plant_screen",
    "analysis",
    "severity",
    "chains",
    "chain_severity",
    "lopa",
    "recommendations",
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
    connector: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    applies: bool = False,
    recommend: bool = True,
    fail: frozenset[str] = frozenset(),
) -> Script:
    """A run with one line per cause group: each question's finding names `outside <group>`
    on the first location; severity by group (S3 by default); the connector proposes what
    `connector` returns; every LOPA layer applies or not; one recommendation per line. A job
    in `fail` answers with text that is not JSON (invalid twice)."""
    grades = severities or {}

    def script(job: str, request: dict[str, Any]) -> Reply:
        if job in fail:
            return reply("not json")
        if job == "plant_screen":
            return reply({"hypotheses": []})
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
            chains = connector(block(request, "scenarios")) if connector else []
            return reply({"chains": chains})
        if job == "chain_severity":
            return reply(
                {
                    "severities": [
                        {"chain_id": c["chain_id"], "severity_class": "S4", "reason": "two hurt"}
                        for c in block(request, "chains")
                    ]
                }
            )
        if job == "lopa_argument":
            return reply(
                {
                    "lines": [
                        {
                            "target_id": line["target_id"],
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
                {"target_id": line["target_id"], "action": "add an independent trip", "reason": "r"}
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


def first_two(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One chain of the first two scenarios, plus a plant fact."""
    links = [scenarios[0]["finding_id"], scenarios[1]["finding_id"], "MX-1.design_pressure_kpa"]
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

    extended = extend(world.runs, run.id, 0.30, config)
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
        name: config.routing.prompts[name] for name in sorted(PHASE_3_PROMPTS)
    }


def test_extension_refuses_an_unfinished_run_and_a_run_already_extended(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "a", ref)
    unfinished = world.start(config)
    with pytest.raises(ExtendRefused, match="not finished"):
        extend(world.runs, unfinished.id, 0.30, config)

    other = World(tmp_path / "b", ref)
    script = post_script()
    run = phase_2_run(other, config, script)
    extend(other.runs, run.id, 0.30, config)
    gateway, _ = other.gateway(config, script)
    assert drive(other.runs, run.id, other.steppers(config, gateway)) == RunStatus.FINISHED
    with pytest.raises(ExtendRefused, match="already"):
        extend(other.runs, run.id, 0.30, config)
    # a new run on the Phase 3 steps has its chains step done already
    fresh, _ = World(tmp_path / "c", ref).run(config, script)
    assert fresh.status == RunStatus.FINISHED
    with pytest.raises(ExtendRefused, match="already"):
        extend(World(tmp_path / "c", ref).runs, fresh.id, 0.30, config)


def test_pre_r50_run_extends_with_every_line_also_found_and_labelled(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path, ref)
    script = post_script(connector=first_two)
    run = phase_2_run(world, config, script, pre_r50=True)
    assert world.runs.hypotheses(run.id) == []
    extend(world.runs, run.id, 0.30, config)
    gateway, _ = world.gateway(config, script)
    drive(world.runs, run.id, world.steppers(config, gateway))
    report = world.report(config, run.id)
    assert report["pre_r50"] is True
    assert report["shortlist"]
    assert {line["tier"] for line in report["shortlist"]} == {"also_found"}
    assert all("pre-R50 run" in line["flags"] for line in report["shortlist"])


# --- the eight steps, replayed (R45) ----------------------------------------------------------


def test_full_eight_step_fake_run_replays_identically(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = World(tmp_path / "original", ref)
    run, _ = world.run(config, post_script(connector=first_two, severities={0: "S4", 1: "S5"}))
    assert run.status == RunStatus.FINISHED
    assert world.steps_started(run.id)[0] == "plant_screen"
    assert sorted(set(world.steps_started(run.id))) == sorted(EIGHT_STEPS)
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


def test_r38_stop_still_comes_at_ranked_after_the_post_steps(
    tmp_path: Path, ref: ReferenceSet, config: Config, capped_script: Any
) -> None:
    world = World(tmp_path, ref)
    run, _ = world.run(config, capped_script, cap=0.08)
    assert run.status == RunStatus.STOPPED_CAP and run.step == "ranked"
    started = world.steps_started(run.id)
    assert list(dict.fromkeys(started))[-5:] == [*POST_STEPS, "ranked"]
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
    argued = {
        line["target_id"]
        for job, request in transport.sent
        if job == "lopa_argument"
        for line in block(request, "lines")
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
    sent = [
        line["target_id"]
        for job, request in transport.sent
        if job == "recommendation"
        for line in block(request, "lines")
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
    world = World(tmp_path, ref)
    run, transport = world.run(config, post_script())
    (request,) = [r for job, r in transport.sent if job == "connector"]
    facts = block(request, "fact_ids")
    assert "MX-1.design_pressure_kpa" in facts and facts == sorted(facts)
    scenarios = block(request, "scenarios")
    lines = [x for x in world.report(config, run.id)["shortlist"] if x["target_kind"] == "finding"]
    assert [s["finding_id"] for s in scenarios] == sorted(
        (x["target_id"] for x in lines),
        key=lambda t: next(x["position"] for x in lines if x["target_id"] == t),
    )
    assert {"finding_id", "cause", "consequence", "failing_component_ids", "severity_class"} <= set(
        scenarios[0]
    )
    assert "plant_id" not in block(request, "plant")


def test_a_rejected_chain_is_logged_with_its_reason_and_listed(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    def bad(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            *first_two(scenarios),
            {
                "links": [scenarios[0]["finding_id"], "f:invented"],
                "description": "d",
                "reason": "r",
            },
            {
                "links": ["MX-1.design_pressure_kpa", "HV-12.normal_position"],
                "description": "d",
                "reason": "r",
            },
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
        list(args),
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
            [str(EXAMPLE), *flag],
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

    assert screen_check._arguments([str(EXAMPLE), "--cap", "1"]).phase == "3"
    assert screen_check._arguments([str(EXAMPLE), "--cap", "1", "--phase", "2"]).phase == "2"
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
