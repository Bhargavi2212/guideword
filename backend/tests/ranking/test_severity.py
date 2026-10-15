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
from guideword.ranking.severity import RankedStepper, SeverityStepper
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


def drain(view: dict[str, Any]) -> Any:
    for agent in sorted(view["open"]):
        return "dispatch_specialist", {"agent": agent, "level": "bulk"}
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
    ) -> tuple[dict[str, Any], Any]:
        def script(job: str, request: dict[str, Any]) -> Any:
            if job == "orchestrator":
                name, args = decide(block(request, "view"))
                call = ToolCallRequest("t", name, json.dumps({"reason": "go", **args}))
                return reply(tool_calls=(call,), output_tokens=orchestrator_output_tokens)
            if job == "severity_reason":
                return severity(request)
            return specialist(request)

        gateway, transport = fake_gateway(
            self.config,
            script,
            sessions=self.sessions,
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
    assert len(severity_calls) == -(-len(findings) // batch)
    assert sorted(i for c in severity_calls for i in c.record_ids) == sorted(f.id for f in findings)
    # the severity answers see no instruction text from the plant and only the batch's findings
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
    run = world.start(cap=0.17)
    # each orchestrator turn really spends about $0.01, so the second one meets the reserve
    steppers, _ = world.steppers(orchestrator_output_tokens=2000)
    assert world.run(run, steppers) == RunStatus.STOPPED_CAP
    reasons = [
        e.payload.get("reason") for e in world.runs.events(run.id) if e.type == EventType.CAP_HIT
    ]
    assert "severity reserve" in reasons
    findings = world.runs.findings(run.id)
    assert findings and all(f.severity_class == SeverityClass.S3 for f in findings)
    assert world.runs.get(run.id).spent_usd <= 0.17  # type: ignore[union-attr]
