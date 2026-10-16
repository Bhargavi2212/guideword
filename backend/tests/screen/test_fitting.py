"""What can fail as what, told to the model by the same function that judges it (plant_screen
v2; R46 made visible). The per-type ID list in the prompt, the validator's misfit check and the
retry message all come from `screen.schema.fitting`; these tests prove they agree on every
dev plant and the example, for every plant ID and every failing-component type."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from guideword.config import load_config
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import FailingComponentType
from guideword.schema.plant import Plant
from guideword.screen.schema import (
    ScreenHypothesis,
    _all_ids,
    fitting,
    hypothesis_problem,
)

REPO = Path(__file__).resolve().parents[3]
PLANTS = [REPO / "cases" / "dev" / f"case_{c}.json" for c in "defgh"] + [
    REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
]


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def load(path: Path) -> Plant:
    return Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))


def hypothesis(component: str, kind: FailingComponentType) -> ScreenHypothesis:
    return ScreenHypothesis(
        rank=1,
        mechanism="m",
        component_ids=[component],
        chemical_ids=[],
        failing_component_type=kind,
        cause_id="outside_library",
        cause_text="something",
        consequence="c",
        reason="r",
    )


@pytest.mark.parametrize("path", PLANTS, ids=lambda p: p.stem)
def test_the_listed_ids_are_exactly_those_the_validator_accepts(
    path: Path, ref: ReferenceSet
) -> None:
    plant = load(path)
    listed = fitting(plant)
    for kind in FailingComponentType:
        for component in sorted(_all_ids(plant)):
            accepted = hypothesis_problem(hypothesis(component, kind), plant, ref) is None
            assert accepted == (component in listed.get(kind.value, [])), (component, kind)


@pytest.mark.parametrize("path", PLANTS, ids=lambda p: p.stem)
def test_the_retry_message_names_what_the_id_can_fail_as_from_the_same_list(
    path: Path, ref: ReferenceSet
) -> None:
    plant = load(path)
    listed = fitting(plant)
    for component in sorted(_all_ids(plant)):
        kinds = [k for k, members in listed.items() if component in members]
        wrong = next(k for k in FailingComponentType if k.value not in kinds)
        problem = hypothesis_problem(hypothesis(component, wrong), plant, ref)
        assert problem is not None and f"cannot fail as a {wrong.value}" in problem
        if kinds:
            assert problem.endswith(f"{component} can fail as: {', '.join(kinds)}")
        else:
            assert problem.endswith(
                f"{component} can fail as nothing; name its loop, instrument, line or "
                "location instead"
            )


def test_equipment_with_no_failing_type_is_in_no_list() -> None:
    plant = load(REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json")
    listed = fitting(plant)
    assert not any("MX-1" in members for members in listed.values())  # a mixer
    assert all(members for members in listed.values())  # empty types are left out
    assert list(listed) == [k.value for k in FailingComponentType if k.value in listed]


def test_the_screen_prompt_carries_the_list_as_data(tmp_path: Path) -> None:
    from guideword.gateway.fake import fake_gateway  # noqa: PLC0415
    from guideword.runs.db import make_session_factory  # noqa: PLC0415
    from guideword.screen.step import PlantScreenStepper  # noqa: PLC0415

    config = load_config(global_budget_usd=25.0)
    plant = load(PLANTS[0])
    gateway, _ = fake_gateway(
        config,
        lambda job, request: None,
        sessions=make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}"),
        ledger_path=tmp_path / "l.jsonl",
        clock=lambda: datetime(2026, 10, 17, 9, 0, tzinfo=UTC),
    )
    stepper = PlantScreenStepper(gateway, config=config, ref=load_reference_set(), plant=plant)
    system = stepper.messages(["matrix"])[0]["content"]
    block = system.split("<can_fail_as>")[1].split("</can_fail_as>")[0]
    assert json.loads(block) == fitting(plant)
