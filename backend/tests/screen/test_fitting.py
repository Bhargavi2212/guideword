"""The `can_fail_as` list in the plant_screen prompt (R50 review, G23). It is guidance for the
whole-plant pass, computed by `screen.schema.fitting` from the plant: the same rule every
finding is held to (R46, `specialists.causes.fitting_ids`). It is not enforced on hypotheses:
since G23 a hypothesis may name any real plant ID, whatever its type."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from guideword.config import load_config
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.enums import FailingComponentType
from guideword.schema.plant import Plant
from guideword.screen.schema import ScreenHypothesis, _all_ids, fitting, hypothesis_problem
from guideword.specialists.causes import fitting_ids

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
def test_prompt_guidance_list_comes_from_fitting(path: Path) -> None:
    """The list is computed from the plant by the rule findings are held to: per type, the
    IDs `fitting_ids` gives, and for `operator` the procedure steps and planned jobs."""
    plant = load(path)
    steps = sorted(
        [s.id for p in plant.procedures for s in p.steps] + [j.id for j in plant.planned_work]
    )
    for kind in FailingComponentType:
        expected = (
            steps
            if kind == FailingComponentType.OPERATOR
            else sorted(fitting_ids(kind.value, plant))
        )
        assert fitting(plant).get(kind.value, []) == expected, kind


@pytest.mark.parametrize("path", PLANTS, ids=lambda p: p.stem)
def test_any_real_plant_id_is_accepted_for_any_type(path: Path, ref: ReferenceSet) -> None:
    """G23: the type is not checked against a hypothesis's components."""
    plant = load(path)
    for kind in FailingComponentType:
        for component in sorted(_all_ids(plant)):
            assert hypothesis_problem(hypothesis(component, kind), plant, ref) is None


def test_an_unknown_id_is_still_refused(ref: ReferenceSet) -> None:
    plant = load(PLANTS[0])
    problem = hypothesis_problem(hypothesis("NOT-IN-PLANT", FailingComponentType.TANK), plant, ref)
    assert problem is not None and "not in this plant" in problem


def test_equipment_with_no_failing_type_is_in_no_list() -> None:
    plant = load(PLANTS[-1])
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
