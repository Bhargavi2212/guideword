"""Running a tool from an agent step: a ToolCall record and a tool_call event every time."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import PlantRow, RunRow, make_session_factory
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import EventType, RunLabelKind, RunStatus
from guideword.schema.plant import Plant
from guideword.schema.records import Run, RunLabel
from guideword.tools.record import run_tool

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
STEP = "step:0123456789abcdef"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture
def plant() -> Plant:
    return Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


@pytest.fixture
def runs(tmp_path: Path) -> tuple[RunRepository, str]:
    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
    inputs: dict[str, Any] = {
        k: {} for k in ("reference_versions", "routing_config", "caps", "prompt_versions")
    }
    inputs |= {"plant_id": "plant:x:0", "section_snapshot": [], "mode": "full"}
    run = Run(
        id=ids.run_id(inputs, [], spend_cap_usd=1.0),
        plant_record_id="plant:x:0",
        attempt=1,
        section_snapshot=[],
        status=RunStatus.RUNNING,
        step="analysis",
        mode="full",
        spend_cap_usd=1.0,
        reference_versions={},
        routing_config={},
        caps={},
        prompt_versions={},
        label=RunLabel(kind=RunLabelKind.LIVE),
    )
    with sessions.begin() as session:
        session.add(
            PlantRow(id="plant:x:0", plant_id="x", status="sections_confirmed", plant_file={})
        )
        session.add(
            RunRow(
                id=run.id,
                base_id=run.id,
                attempt=1,
                plant_record_id="plant:x:0",
                status="running",
                record=run.model_dump(mode="json"),
                sections=[],
            )
        )
    return RunRepository(sessions, lambda: datetime(2026, 10, 15, tzinfo=UTC)), run.id


def test_every_call_is_a_tool_call_record_and_event(
    runs: tuple[RunRepository, str], plant: Plant, ref: ReferenceSet
) -> None:
    repo, run_id = runs
    arguments = {"chemical_a": "SIH", "chemical_b": "KOH"}
    with repo.step(run_id) as writer:
        outcome = run_tool(writer, STEP, "reactivity_lookup", arguments, plant=plant, ref=ref)
    assert outcome.refused_reason is None
    assert outcome.result is not None
    [call] = repo.tool_calls(run_id)
    assert call.id == ids.tool_call_id(STEP, "reactivity_lookup", arguments)
    assert (call.agent_step_id, call.tool, call.arguments) == (STEP, "reactivity_lookup", arguments)
    assert call.result == outcome.result
    assert call.refused_reason is None
    assert [e.type for e in repo.events(run_id)] == [EventType.TOOL_CALL]


def test_a_refused_call_stores_its_reason_and_returns_the_error(
    runs: tuple[RunRepository, str], plant: Plant, ref: ReferenceSet
) -> None:
    repo, run_id = runs
    with repo.step(run_id) as writer:
        outcome = run_tool(
            writer,
            STEP,
            "reactivity_lookup",
            {"chemical_a": "SIH", "chemical_b": "NOPE"},
            plant=plant,
            ref=ref,
        )
    assert outcome.result is None
    assert outcome.refused_reason == "NOPE is not a chemical in this plant"
    [call] = repo.tool_calls(run_id)
    assert call.refused_reason == outcome.refused_reason
    assert repo.events(run_id)[0].payload["refused"] is True


@pytest.mark.parametrize(
    "arguments",
    [
        {"chemical_a": "SIH"},
        {"chemical_a": "SIH", "chemical_b": "KOH", "extra": 1},
        {"chemical_a": 3, "chemical_b": "KOH"},
    ],
)
def test_malformed_arguments_are_refused(
    runs: tuple[RunRepository, str], plant: Plant, ref: ReferenceSet, arguments: dict[str, Any]
) -> None:
    repo, run_id = runs
    with repo.step(run_id) as writer:
        outcome = run_tool(writer, STEP, "reactivity_lookup", arguments, plant=plant, ref=ref)
    assert outcome.result is None
    assert outcome.refused_reason and outcome.refused_reason.startswith("bad arguments")


def test_an_unknown_tool_is_refused(
    runs: tuple[RunRepository, str], plant: Plant, ref: ReferenceSet
) -> None:
    repo, run_id = runs
    with repo.step(run_id) as writer:
        outcome = run_tool(writer, STEP, "web_research", {"query": "x"}, plant=plant, ref=ref)
    assert outcome.refused_reason == "web_research is not a tool in this phase"
