"""The severity and ranked steps (spec 2.6; plan R10, R24, R38)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.transport import ToolCallRequest
from guideword.orchestrator.loop import OrchestratorStepper
from guideword.ranking.rank import rank_findings
from guideword.ranking.severity import RankedStepper, SeverityStepper, scenarios
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.machine import advance
from guideword.runs.plants import PlantRepository, load_plant, plant_facts
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, RunStatus, SeverityClass
from guideword.schema.records import Run
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
_BLOCK = r"<{0}>\s*(.*?)\s*</{0}>"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def block(request: dict[str, Any], name: str) -> Any:
    match = re.search(_BLOCK.format(name), request["messages"][0]["content"], re.S)
    assert match is not None, name
    return json.loads(match.group(1))


def specialist(request: dict[str, Any]) -> Any:
    """A sure outside-library finding naming the first location (citable by every agent)."""
    location = block(request, "context")["locations"][0]["id"]
    return reply(
        {
            "answers": [
                {
                    "question_id": q["id"],
                    "not_credible": None,
                    "findings": [
                        {
                            "cause_id": "outside_library",
                            "cause_text": "something outside",
                            "failing_component_type": "external",
                            "failing_component_ids": [location],
                            "consequence": "a release",
                            "safeguard_ids": [],
                            "adequacy": "unknown",
                            "confidence": "sure",
                            "reason": "test",
                        }
                    ],
                }
                for q in block(request, "questions")
            ],
            "added_questions": [],
        }
    )


def severity_answer(request: dict[str, Any], skip: int = 0) -> Any:
    findings = block(request, "findings")
    return reply(
        {
            "severities": [
                {"finding_id": f["finding_id"], "severity_class": "S3", "reason": "one person hurt"}
                for f in findings[skip:]
            ]
        }
    )


def level_for(view: dict[str, Any], agent: str) -> str:
    """Bulk while the agent has untried open questions, then hard for the tried ones (R44)."""
    retry = view["retry_at_hard"].get(agent, {"count": 0})["count"]
    return "bulk" if view["open"][agent]["count"] > retry else "hard"


def drain(view: dict[str, Any]) -> Any:
    for agent in sorted(view["open"]):
        return "dispatch_specialist", {"agent": agent, "level": level_for(view, agent)}
    return "finish", {}


class World:
    def __init__(self, tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
        self.sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
        self.plants = PlantRepository(self.sessions)
        self.runs = RunRepository(self.sessions, lambda: datetime(2026, 10, 15))
        self.ref, self.config, self.tmp = ref, config, tmp_path
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        record, _ = load_plant(raw, ref)
        assert record is not None
        self.plants.add(record, raw, plant_facts(record.plant_file, record.id))
        self.plants.confirm(record.id, rule_cut(record.plant_file, record.id))
        self.plant, self.record_id = record.plant_file, record.id

    def start(self, cap: float = 1.0) -> Run:
        cfg = self.config
        settings = RunSettings(
            dict(cfg.routing.jobs), cfg.caps.run_input_caps(), dict(cfg.routing.prompts)
        )
        return start_run(
            self.plants,
            self.runs,
            self.ref,
            settings,
            plant_record_id=self.record_id,
            spend_cap_usd=cap,
            mode="full",
        )

    def steppers(
        self,
        severity: Any = severity_answer,
        decide: Any = drain,
        orchestrator_output_tokens: int = 50,
        cache_from: "World | None" = None,
        gateway_config: Config | None = None,
    ) -> tuple[dict[str, Any], Any]:
        """`cache_from` shares another world's response cache (a replay in a fresh store);
        `gateway_config` gives the gateway other prices."""

        def script(job: str, request: dict[str, Any]) -> Any:
            if job == "orchestrator":
                name, args = decide(block(request, "view"))
                call = ToolCallRequest("t", name, json.dumps({"reason": "go", **args}))
                return reply(tool_calls=(call,), output_tokens=orchestrator_output_tokens)
            if job == "severity_reason":
                return severity(request)
            return specialist(request)

        gateway, transport = fake_gateway(
            gateway_config or self.config,
            script,
            sessions=(cache_from or self).sessions,
            ledger_path=self.tmp / "l.jsonl",
            clock=lambda: datetime(2026, 10, 15, tzinfo=UTC),
        )
        args = {"config": self.config, "ref": self.ref, "plant": self.plant}
        return {
            "analysis": OrchestratorStepper(gateway, **args),
            "severity": SeverityStepper(gateway, **args),
            "ranked": RankedStepper(),
        }, transport

    def run(self, run: Run, steppers: dict[str, Any]) -> RunStatus:
        for _ in range(200):
            status = advance(self.runs, run.id, steppers)
            if status != RunStatus.RUNNING:
                return status
        raise AssertionError("did not end")


@pytest.fixture
def world(tmp_path: Path, ref: ReferenceSet, config: Config) -> World:
    return World(tmp_path, ref, config)


def test_severity_batches_set_each_finding_once_and_record_ids(
    world: World, config: Config
) -> None:
    run = world.start()
    steppers, transport = world.steppers()
    assert world.run(run, steppers) == RunStatus.FINISHED
    findings = world.runs.findings(run.id)
    assert findings and {f.severity_class for f in findings} == {SeverityClass.S3}
    assert all(f.severity_reason == "one person hurt" for f in findings)
    severity_calls = [c for c in world.runs.model_calls(run.id) if c.job == "severity_reason"]
    batch = config.caps.run.severity_batch_size
    # R48: one finding per scenario is sent, and its rating is copied to the whole scenario
    groups = scenarios(findings, world.runs.questions(run.id))
    assert 1 < len(groups) < len(findings)
    assert len(severity_calls) == -(-len(groups) // batch)
    assert sorted(i for c in severity_calls for i in c.record_ids) == sorted(f.id for f in findings)
    sent = [
        f["finding_id"]
        for j, r in transport.sent
        if j == "severity_reason"
        for f in block(r, "findings")
    ]
    assert sorted(sent) == sorted(min(m.id for m in members) for members in groups.values())
    for job, request in transport.sent:
        if job == "severity_reason":
            assert len(block(request, "findings")) <= batch


def test_a_finding_the_answer_leaves_out_is_marked_not_assessed(world: World) -> None:
    run = world.start()
    steppers, _ = world.steppers(severity=lambda r: severity_answer(r, skip=1))
    assert world.run(run, steppers) == RunStatus.FINISHED
    findings = world.runs.findings(run.id)
    unrated = [f for f in findings if f.severity_class is None]
    assert unrated and all((f.severity_reason or "").startswith("not assessed") for f in unrated)


def test_an_unknown_finding_id_in_the_severity_answer_is_invalid(world: World) -> None:
    run = world.start()

    def wrong(request: dict[str, Any]) -> Any:
        return reply(
            {"severities": [{"finding_id": "f:nope", "severity_class": "S1", "reason": "x"}]}
        )

    steppers, _ = world.steppers(severity=wrong)
    assert world.run(run, steppers) == RunStatus.FINISHED
    assert all(f.severity_class is None for f in world.runs.findings(run.id))
    assert all("not assessed" in (f.severity_reason or "") for f in world.runs.findings(run.id))


def test_fake_run_at_the_cap_boundary_still_completes_severity(world: World) -> None:
    """R38: analysis stops at cap minus the severity reserve; severity still runs within the
    cap; the run ends stopped_cap because questions were left open."""
    run = world.start(cap=0.08)
    # each orchestrator turn really spends about $0.01, so the second one meets the reserve
    steppers, _ = world.steppers(orchestrator_output_tokens=2000)
    assert world.run(run, steppers) == RunStatus.STOPPED_CAP
    reasons = [
        e.payload.get("reason") for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT
    ]
    assert "severity reserve" in reasons
    findings = world.runs.findings(run.id)
    assert findings and all(f.severity_class == SeverityClass.S3 for f in findings)
    assert world.runs.get(run.id).spent_usd <= 0.08  # type: ignore[union-attr]


# --- replays (R45) -----------------------------------------------------------------------------


def ranked(world: World, run: Run) -> list[tuple[str, Any, Any]]:
    order = rank_findings(world.runs.findings(run.id), world.plant, world.ref, world.config.caps)
    return [(r.finding.id, r.rating, r.likelihood.frequency_per_year) for r in order]


def spend(world: World, run: Run) -> tuple[float, float]:
    """(spent_usd, cap_spent_usd), after checking both equal the sums of the call records."""
    stored = world.runs.get(run.id)
    assert stored is not None
    calls = world.runs.model_calls(run.id)
    assert stored.spent_usd == pytest.approx(sum(c.cost_usd for c in calls), abs=1e-12)
    assert stored.cap_spent_usd == pytest.approx(sum(c.cap_cost_usd for c in calls), abs=1e-12)
    return stored.spent_usd, stored.cap_spent_usd


def doubled_prices(config: Config) -> Config:
    tiers = {
        tier: model.model_copy(
            update={
                "input_usd_per_1m": model.input_usd_per_1m * 2,
                "output_usd_per_1m": model.output_usd_per_1m * 2,
            }
        )
        for tier, model in config.models.tiers.items()
    }
    return config.model_copy(update={"models": config.models.model_copy(update={"tiers": tiers})})


def replay_world(world: World) -> World:
    (world.tmp / "replay").mkdir()
    return World(world.tmp / "replay", world.ref, world.config)


def test_ranking_identical_across_two_cache_replays(world: World) -> None:
    first = world.start()
    steppers, transport = world.steppers()
    world.run(first, steppers)
    paid = len(transport.sent)
    with world.runs.step(first.id) as writer:
        writer.set_status(RunStatus.FINISHED)
    second = world.start()
    assert second.id == f"{first.id}:2"
    steppers2, transport2 = world.steppers()
    world.run(second, steppers2)
    assert transport2.sent == []  # every call served from the cache
    assert paid > 0
    assert ranked(world, first) == ranked(world, second)
    first_spent, first_cap = spend(world, first)
    assert first_spent == pytest.approx(first_cap) and first_spent > 0
    # a full replay pays nothing and counts against its cap what the original did
    assert spend(world, second) == (0.0, pytest.approx(first_cap))


def test_capped_run_replays_to_the_same_stop_point_after_a_price_change(world: World) -> None:
    first = world.start(cap=0.08)
    steppers, _ = world.steppers(orchestrator_output_tokens=2000)
    assert world.run(first, steppers) == RunStatus.STOPPED_CAP

    again = replay_world(world)
    second = again.start(cap=0.08)
    assert second.id == first.id  # same inputs, fresh store
    steppers2, transport2 = again.steppers(
        orchestrator_output_tokens=2000,
        cache_from=world,
        gateway_config=doubled_prices(world.config),
    )
    assert again.run(second, steppers2) == RunStatus.STOPPED_CAP
    assert transport2.sent == []  # the call refused in the original is refused again, unsent

    def stops(w: World) -> list[Any]:
        return [
            e.payload.get("reason") for e in w.runs.events(first.id) if e.type == EventType.CAP_HIT
        ]

    assert stops(again) == stops(world)
    assert [c.id for c in again.runs.model_calls(first.id)] == [
        c.id for c in world.runs.model_calls(first.id)
    ]
    assert ranked(again, second) == ranked(world, first)
    _, first_cap = spend(world, first)
    assert spend(again, second) == (0.0, pytest.approx(first_cap))
    # replays write no ledger lines, so no allowance is used
    ledger = again.tmp / "l.jsonl"
    assert not ledger.exists() or ledger.read_text(encoding="utf-8") == ""


def test_a_run_partly_served_from_the_cache_sums_both_figures(world: World) -> None:
    """A higher cap changes the orchestrator's view (its limit), so its turns are paid again;
    the specialist and severity answers are cache hits at their stored cost."""
    first = world.start(cap=1.0)
    steppers, _ = world.steppers()
    assert world.run(first, steppers) == RunStatus.FINISHED

    again = replay_world(world)
    second = again.start(cap=2.0)
    steppers2, transport2 = again.steppers(cache_from=world)
    assert again.run(second, steppers2) == RunStatus.FINISHED
    calls = again.runs.model_calls(second.id)
    hits = [c for c in calls if c.cache_hit]
    sent = [c for c in calls if not c.cache_hit]
    assert hits and sent and len(transport2.sent) == len(sent)
    assert {c.job for c in sent} == {"orchestrator"}
    spent, cap = spend(again, second)
    assert spent == pytest.approx(sum(c.cost_usd for c in sent))
    assert cap == pytest.approx(spent + sum(c.cap_cost_usd for c in hits))
    assert 0 < spent < cap


# --- the computed reserve (case D dev run) -----------------------------------------------------


def test_the_reserve_is_one_severity_call_per_batch_of_unrated_findings(world: World) -> None:
    import math  # noqa: PLC0415

    from guideword.gateway.estimate import estimate_cost  # noqa: PLC0415
    from guideword.gateway.prompts import load_prompt  # noqa: PLC0415
    from guideword.ranking.severity import severity_messages, severity_reserve  # noqa: PLC0415
    from guideword.schema.enums import Tier  # noqa: PLC0415

    run = world.start()
    steppers, _ = world.steppers()
    world.run(run, steppers)
    rated = world.runs.findings(run.id)
    questions = world.runs.questions(run.id)
    cfg = world.config
    assert severity_reserve(rated, questions, world.plant, world.ref, cfg).usd == 0.0

    unrated = [
        f.model_copy(update={"severity_class": None, "severity_reason": None}) for f in rated
    ]
    groups = scenarios(unrated, questions)
    # a scenario with a finding already marked not assessed is done: it is not counted
    done = sorted(groups)[0]
    marked = groups[done][0].model_copy(update={"severity_reason": "not assessed: cut off"})
    findings = [marked if f.id == marked.id else f for f in unrated]
    reserve = severity_reserve(findings, questions, world.plant, world.ref, cfg)
    size = cfg.caps.run.severity_batch_size
    todo = sorted(
        (min(members, key=lambda f: f.id) for key, members in groups.items() if key != done),
        key=lambda f: f.id,
    )
    assert reserve.unrated == len(todo) == len(groups) - 1  # unrated scenarios, not findings
    assert reserve.calls == math.ceil(len(todo) / size)
    ultra = cfg.models.tiers[Tier.ULTRA]
    messages = severity_messages(
        load_prompt("severity", cfg),
        todo[:size],
        {q.id: q for q in questions},
        world.ref,
        world.plant,
    )
    # each call is priced at the expected output, not the max_tokens ceiling
    output = cfg.caps.run.severity_output_tokens_estimate
    assert output < cfg.caps.run.max_tokens["severity_reason"]
    per_call = estimate_cost(ultra, messages, None, output).cost_usd
    # one call is reserved at the ceiling the gateway checks it at, so the last call fits
    ceiling = estimate_cost(ultra, messages, None, cfg.caps.run.max_tokens["severity_reason"])
    assert reserve.per_call_usd == pytest.approx(per_call)
    assert reserve.ceiling_call_usd == pytest.approx(ceiling.cost_usd)
    assert reserve.usd == pytest.approx((reserve.calls - 1) * per_call + ceiling.cost_usd)
    assert per_call >= output * ultra.output_usd_per_1m / 1_000_000


# --- R48: one severity per scenario --------------------------------------------------------------


def _finding_like(base: Any, **changes: Any) -> Any:
    return base.model_copy(update={"severity_class": None, "severity_reason": None, **changes})


def test_a_scenario_is_cause_components_and_section(world: World) -> None:
    from guideword.ranking.severity import scenario_key  # noqa: PLC0415

    run = world.start()
    steppers, _ = world.steppers()
    world.run(run, steppers)
    questions = world.runs.questions(run.id)
    section_of = {q.id: q.section_id for q in questions}
    base = world.runs.findings(run.id)[0]
    same = _finding_like(
        base, id="f:other", failing_component_ids=list(reversed(base.failing_component_ids))
    )
    assert scenario_key(base, section_of) == scenario_key(same, section_of)
    # the outside-library text is compared after normalising
    shout = _finding_like(base, id="f:x", cause_text=base.cause_text.upper() + "  ")  # type: ignore[union-attr]
    assert scenario_key(base, section_of) == scenario_key(shout, section_of)
    other_text = _finding_like(base, id="f:y", cause_text="something else entirely")
    assert scenario_key(base, section_of) != scenario_key(other_text, section_of)
    other_section = next(
        q for q in questions if q.section_id not in (None, section_of[base.question_id])
    )
    moved = _finding_like(base, id="f:z", question_id=other_section.id)
    assert scenario_key(base, section_of) != scenario_key(moved, section_of)


def test_an_unrated_finding_of_a_rated_scenario_is_copied_without_a_call(world: World) -> None:
    from guideword.ranking.severity import scenario_key  # noqa: PLC0415

    run = world.start()
    steppers, transport = world.steppers()
    world.run(run, steppers)
    rated = world.runs.findings(run.id)[0]
    with world.runs.step(run.id) as writer:
        late = _finding_like(rated, id=f"{rated.id}x", confidence=rated.confidence)
        writer.add_finding(late)
        writer.set_step("severity")
        writer.set_status(RunStatus.RUNNING)
    sent = len(transport.sent)
    advance(world.runs, run.id, steppers)
    copied = next(f for f in world.runs.findings(run.id) if f.id == late.id)
    assert len(transport.sent) == sent
    assert copied.severity_class == rated.severity_class
    assert copied.severity_reason == f"same scenario as {rated.id}: {rated.severity_reason}"[:300]
    section_of = {q.id: q.section_id for q in world.runs.questions(run.id)}
    assert scenario_key(copied, section_of) == scenario_key(rated, section_of)
