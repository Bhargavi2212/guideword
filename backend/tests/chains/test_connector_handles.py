"""connector/v2's handles and fact list, pure code (specs/phase-3-connector-v2-plan.md, approved
2026-10-21). Ultra links only by `L`/`P` handles; code maps them back exactly; an unknown handle
rejects the chain; the fact list holds only facts on the scenarios' objects and what hangs off
them."""

import json
from pathlib import Path

import pytest

from guideword.chains.connector import (
    fact_list,
    fact_objects,
    fact_prompt_lines,
    map_links,
    scenario_prompt_lines,
)
from guideword.schema.plant import Plant

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
DEMO = REPO / "cases" / "demo" / "williams_geismar.json"


def _plant(path: Path) -> Plant:
    return Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def example() -> Plant:
    return _plant(EXAMPLE)


@pytest.fixture(scope="module")
def demo() -> Plant:
    return _plant(DEMO)


LINES = {"L1": "f:m:S-MX-1:more:temperature:lightning:C01:aaaa", "L2": "f:pair:KOH:SIH:super:bbbb"}
FACTS = {"P1": "HV-12.normal_position", "P2": "MX-1.design_pressure_kpa"}


def test_connector_v2_maps_line_and_fact_handles_back_to_exact_ids() -> None:
    mapped, problem = map_links(["L2", "P1", "L1"], LINES, FACTS)
    assert problem is None
    # the model's order is kept: the first L link is the cause (Q7)
    assert mapped == [LINES["L2"], FACTS["P1"], LINES["L1"]]


@pytest.mark.parametrize(
    "bad",
    [
        "L999",
        "P0",
        "l1",
        " L1",
        "L1 ",
        "L 1",
        "f:m:S-MX-1:more:temperature:lightning:C01:aaaa",  # a raw finding ID
        "MX-1",  # a bare object ID
        "MX-1.design_pressure_kpa",  # a raw fact ID
    ],
)
def test_an_unknown_line_or_fact_handle_rejects_the_chain(bad: str) -> None:
    mapped, problem = map_links(["L1", bad], LINES, FACTS)
    assert mapped == []
    assert problem is not None and "not a handle" in problem and repr(bad) in problem


def test_the_prompt_shows_handles_and_no_finding_id() -> None:
    scenarios = [
        {
            "finding_id": LINES["L1"],
            "cause": "c",
            "consequence": "q",
            "failing_component_ids": ["TIC-1"],
            "section_id": "S-MX-1",
            "severity_class": "S4",
            "object_ids": ["TIC-1", "MX-1"],
        }
    ]
    shown = scenario_prompt_lines(scenarios)
    assert shown == [
        {
            "handle": "L1",
            "cause": "c",
            "consequence": "q",
            "failing_component_ids": ["TIC-1"],
            "section_id": "S-MX-1",
            "severity_class": "S4",
        }
    ]
    assert "f:" not in json.dumps(shown)


def test_the_fact_list_holds_only_facts_on_components_their_locations_and_utilities(
    example: Plant,
) -> None:
    """A scenario on MX-1: its location, the steam utility on its heat-source line, the relief
    device that protects it, the heat source's isolating valve and the valves on its lines."""
    objects = fact_objects({"MX-1"}, example)
    assert objects == {"MX-1", "BLDG-1", "UT-STEAM", "PSV-1", "XV-STM", "TV-1", "HV-12"}
    facts = fact_list({"MX-1"}, example, "plant:x")
    assert {f.id.split(".", 1)[0] for f in facts} <= objects
    assert [f.id for f in facts] == sorted(f.id for f in facts)
    for left_out in ("TOTE-1", "P-1", "L-12", "L-STM", "TT-1", "SG-TRIP", "ROOF", "SIH"):
        assert not any(f.id.startswith(f"{left_out}.") for f in facts), left_out
    assert "MX-1.operating.temperature.trip_high" in {f.id for f in facts}
    shown = fact_prompt_lines(facts)
    assert [s["handle"] for s in shown] == [f"P{i}" for i in range(1, len(facts) + 1)]
    assert shown[0] == {"handle": "P1", "fact_id": facts[0].id, "value": facts[0].value}


def test_the_demo_fact_list_reaches_the_reboilers_inlet_valve_and_relief_path(
    demo: Plant,
) -> None:
    """Bhargavi, 2026-10-21: a finding on S-EA-425B whose only failing component is the
    start-up step P-REB-START-2 reaches EA-425B through its section, and from there its
    relief path and that path's inlet valve."""
    section_objects = {"EA-425B"}
    facts = {f.id for f in fact_list({"P-REB-START-2", *section_objects}, demo, "plant:demo")}
    assert "HV-B-SIN.normal_position" in facts
    assert "RV-PATH-EA425B.inlet_valve_ids" in facts
    # the heat source's isolating valves and the valves on its lines, too
    assert "HV-QW-B-IN.normal_position" in facts
    assert "HV-B-SOUT.normal_position" in facts
    # Reboiler A is another object: none of its own facts
    assert not any(f.startswith("EA-425A.") for f in facts)
