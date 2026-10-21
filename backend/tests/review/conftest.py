"""Fixtures for the review tests (Phase 3 plan PR 6): the §9 example plant and LOPA hand-worked
example 1's scenario on it, run through the real engine."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.lopa.candidates import line_scenario
from guideword.lopa.credit import LayerArgument
from guideword.lopa.engine import lopa_record
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    OverrideAction,
    SectionKind,
    SectionType,
    SeverityClass,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, LopaRecord, Override, Section

REPO = Path(__file__).resolve().parents[3]
EXAMPLE_1 = REPO / "backend" / "tests" / "lopa" / "fixtures" / "example_1.json"
RUN = "run:review"
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture(scope="session")
def example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE_1.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def plant(example: dict[str, Any]) -> Plant:
    return Plant.model_validate_json((REPO / example["plant_file"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def lead(example: dict[str, Any]) -> Finding:
    given = example["scenario"]["lead_finding"]
    return Finding(
        id=ids.finding_id(
            given["question_id"],
            Tier.ULTRA.value,
            given["failing_component_ids"],
            cause_id=given["cause_id"],
        ),
        run_id=RUN,
        question_id=given["question_id"],
        tier=Tier.ULTRA,
        cause_id=given["cause_id"],
        failing_component_type=FailingComponentType(given["failing_component_type"]),
        failing_component_ids=given["failing_component_ids"],
        consequence=given["consequence"],
        adequacy=Adequacy.UNKNOWN,
        severity_class=SeverityClass(given["severity_class"]),
        severity_reason="an input in the fixture",
        confidence=Confidence.SURE,
    )


@pytest.fixture(scope="session")
def section(example: dict[str, Any]) -> Section:
    given = example["scenario"]["lead_finding"]
    return Section(
        id=given["section_id"],
        plant_record_id="plant:example",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name=given["section_id"],
        object_ids=given["section_object_ids"],
        drawn_by="rule",
    )


def arguments(example: dict[str, Any], letter: str) -> dict[str, LayerArgument] | None:
    variant = next(v for v in example["variants"] if v["name"].startswith(f"{letter}:"))
    given = variant["argument_input"]
    if given is None:
        return None
    return {k: LayerArgument(applies=a["applies"], reason="r") for k, a in given.items()}


def record_for(
    example: dict[str, Any],
    letter: str,
    *,
    lead: Finding,
    section: Section,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
) -> LopaRecord:
    found = lopa_record(
        line_scenario(lead, section),
        run_id=RUN,
        plant=plant,
        ref=ref,
        caps=config.caps,
        arguments=arguments(example, letter),
        model_call_id=None if arguments(example, letter) is None else "mc:review",
    )
    assert isinstance(found, LopaRecord)
    return found


def override(
    target_id: str,
    action: OverrideAction,
    new_value: Any,
    *,
    replaces: str | None = None,
    reason: str = "engineer's reason",
) -> Override:
    return Override(
        id=ids.override_id(target_id, action, new_value, replaces=replaces),
        run_id=RUN,
        target_id=target_id,
        action=action,
        new_value=new_value,
        reason=reason,
        by="Bhargavi",
        at=NOW,
        replaces=replaces,
    )
