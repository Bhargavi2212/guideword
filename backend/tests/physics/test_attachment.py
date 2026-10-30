"""Which calculations a line gets, and through what (review plan §0a, approved 2026-10-25).

Blocked-in heating attaches to a line when the line itself names the vessel and at least one of
its mechanism inputs: its heat-source isolating valves, the valves on its process-side lines, or
a procedure step that operates either. A finding names its failing components, a fact link its
object, and a step its equipment and valves; section objects don't count. The matrix rule is
unchanged (Q4). `via_ids` are the line's links that brought the card, in the line's order.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.lopa.lines import section_for
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Calculation,
    Confidence,
    FailingComponentType,
    SectionKind,
    SectionType,
    Tier,
)
from guideword.schema.plant import Equipment, Plant
from guideword.schema.records import Chain, Finding, Question, Section
from guideword.tools import physics
from guideword.tools.physics import Card, applicable, line_links, mechanism_inputs

ROOT = Path(__file__).resolve().parents[3]
WG_FILE = ROOT / "cases" / "demo" / "williams_geismar.json"
WG_EXPORT = ROOT / "cases" / "demo" / "recorded" / "williams_geismar"
RUN = "run:aaaaaaaaaaaaaaaa"
BLOCKED = Calculation.BLOCKED_IN_HEATING
HEAT_UP = Calculation.HEAT_UP_RATE


@pytest.fixture(scope="module")
def wg() -> Plant:
    return Plant.model_validate(json.loads(WG_FILE.read_text(encoding="utf-8")))


def _finding(question: str, components: list[str], n: int = 0) -> Finding:
    """A finding on `question` failing `components`; `n` gives it its own cause."""
    cause = f"C{n + 1:02d}"
    return Finding(
        id=ids.finding_id(question, Tier.LIGHTNING.value, components, cause_id=cause),
        run_id=RUN,
        question_id=question,
        tier=Tier.LIGHTNING,
        cause_id=cause,
        failing_component_type=FailingComponentType.EXTERNAL,
        failing_component_ids=components,
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
    )


def _section(section_id: str, objects: list[str]) -> Section:
    return Section(
        id=section_id,
        plant_record_id="plant:test",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.HEAT_EXCHANGER,
        name=section_id,
        object_ids=objects,
        drawn_by="rule",
    )


def _equipment(plant: Plant, equipment_id: str) -> Equipment:
    return next(e for e in plant.equipment if e.id == equipment_id)


# --- the rule's parts -------------------------------------------------------------------------


def test_a_vessels_mechanism_inputs_are_its_valves_and_the_steps_that_operate_them(
    wg: Plant,
) -> None:
    inputs = mechanism_inputs(_equipment(wg, "EA-425B"), wg)
    assert {"HV-QW-B-IN", "HV-QW-B-OUT", "HV-B-SIN", "HV-B-SOUT"} <= inputs
    assert "P-REB-START-2" in inputs  # it opens HV-QW-B-IN and HV-QW-B-OUT
    assert not {"HV-QW-A-IN", "HV-A-SIN", "EA-425B", "EA-425A"} & inputs


def test_naming_the_vessel_without_a_mechanism_input_attaches_nothing(wg: Plant) -> None:
    env = _finding("env:C4-HEAVIES:air", ["EA-425B", "LOC-OLEFINS-UNIT"])
    assert applicable([(env, None)], wg) == []


def test_section_objects_never_bring_the_blocked_in_check(wg: Plant) -> None:
    """The finding's section holds the vessel and a heat-source valve; the line names neither."""
    found = _finding("m:S-L-QW-B-IN:other_than:composition", ["LOC-OLEFINS-UNIT"])
    s = _section("S-L-QW-B-IN", ["L-QW-B-IN", "HV-QW-B-IN", "EA-425B"])
    assert applicable([(found, s)], wg) == []


def test_the_vessel_and_a_valve_named_by_two_links_attach_through_the_valves_link(
    wg: Plant,
) -> None:
    vessel = _finding("m:S-EA-425B:as_well_as:composition", ["EA-425B"])
    cards = applicable([(vessel, None), "HV-B-SIN.normal_position"], wg)
    assert cards == [Card(BLOCKED, "EA-425B", ("HV-B-SIN.normal_position",))]


def test_a_failing_step_names_its_equipment_and_valves(wg: Plant) -> None:
    step = _finding("proc:P-REB-START-2:early", ["P-REB-START-2"])
    assert applicable([(step, None)], wg) == [
        Card(BLOCKED, "EA-425A", (step.id,)),
        Card(BLOCKED, "EA-425B", (step.id,)),
    ]


def test_a_step_named_by_a_fact_link_counts_as_the_step(wg: Plant) -> None:
    vessel = _finding("m:S-EA-425B:no:flow", ["EA-425B"])
    cards = applicable([(vessel, None), "P-REB-START-2.valve_ids"], wg)
    assert Card(BLOCKED, "EA-425B", ("P-REB-START-2.valve_ids",)) in cards


def test_the_matrix_rule_is_unchanged_and_says_which_finding_brought_it(wg: Plant) -> None:
    fire = _finding("m:S-EA-425B:more:temperature", ["LOC-OLEFINS-UNIT"])
    pressure = _finding("m:S-EA-425A:more:pressure", ["HV-A-SIN"], 1)
    assert applicable([(fire, _section("S-EA-425B", ["EA-425B"]))], wg) == [
        Card(HEAT_UP, "EA-425B", (fire.id,))
    ]
    assert applicable([(pressure, _section("S-EA-425A", ["EA-425A"]))], wg) == [
        Card(BLOCKED, "EA-425A", (pressure.id,))
    ]


def test_a_card_both_rules_reach_is_one_card_with_both_links_in_line_order(wg: Plant) -> None:
    pressure = _finding("m:S-EA-425A:more:pressure", ["EA-425A"])
    valve = "HV-A-SIN.normal_position"
    cards = applicable([valve, (pressure, _section("S-EA-425A", ["EA-425A"]))], wg)
    assert cards == [Card(BLOCKED, "EA-425A", (valve, pressure.id))]


def test_line_links_keep_the_chains_order_and_resolve_each_findings_section(wg: Plant) -> None:
    a = _finding("m:S-EA-425B:as_well_as:composition", ["EA-425B"])
    s = _section("S-EA-425B", ["EA-425B"])
    links = line_links(["HV-B-SIN.normal_position", a.id], {a.id: a}, lambda f: s)
    assert links == ["HV-B-SIN.normal_position", (a, s)]


# --- the WG run's lines that get cards (§0a's table) ------------------------------------------


def _rows(table: str) -> list[dict[str, Any]]:
    data = json.loads((WG_EXPORT / f"{table}.json").read_text(encoding="utf-8"))
    return [r["record"] for r in data["rows"]]


@pytest.fixture(scope="module")
def wg_lines(wg: Plant) -> dict[str, list[Card]]:
    findings = {f["id"]: Finding.model_validate(f) for f in _rows("findings")}
    questions = {q["id"]: Question.model_validate(q) for q in _rows("questions")}
    sections = {s["id"]: Section.model_validate(s) for s in _rows("sections")}
    chains = {c["id"]: Chain.model_validate(c) for c in _rows("chains")}

    def cards(target: str) -> list[Card]:
        ids = chains[target].links if target in chains else [target]
        links = line_links(ids, findings, lambda f: section_for(f, questions, sections))
        return applicable(links, wg)

    return {t: cards(t) for t in [*chains, *findings]}


def _target(lines: dict[str, list[Card]], prefix: str) -> list[Card]:
    found = [t for t in lines if t.startswith(prefix)]
    assert len(found) == 1, (prefix, found)
    return lines[found[0]]


def test_wg_1_the_fire_keeps_only_its_heat_up_card(wg_lines: dict[str, list[Card]]) -> None:
    cards = _target(wg_lines, "f:m:S-EA-425B:more:temperature:super:C22")
    assert [(c.calculation, c.equipment_id) for c in cards] == [(HEAT_UP, "EA-425B")]


def test_wg_2_the_startup_chain_gets_both_reboilers_through_its_valves_and_step(
    wg_lines: dict[str, list[Card]],
) -> None:
    target = next(t for t in wg_lines if t.startswith("ch:EA-425B.design_pressure_kpa"))
    links = json.loads((WG_EXPORT / "chains.json").read_text(encoding="utf-8"))
    order = next(r["record"]["links"] for r in links["rows"] if r["id"] == target)
    step = next(link for link in order if link.startswith("f:proc:P-REB-START-2:early"))
    valves = {
        "HV-B-SIN.normal_position",
        "HV-B-SOUT.normal_position",
        "HV-QW-B-IN.normal_position",
        "HV-QW-B-OUT.normal_position",
    }
    assert wg_lines[target] == [
        Card(BLOCKED, "EA-425A", (step,)),
        Card(BLOCKED, "EA-425B", tuple(link for link in order if link in valves | {step})),
    ]


def test_wg_3_the_ea_425a_chain_loses_the_ea_425b_check_and_keeps_its_heat_up_card(
    wg_lines: dict[str, list[Card]],
) -> None:
    cards = _target(wg_lines, "ch:HV-A-SIN.normal_position+HV-A-SOUT.normal_position+RV-PATH")
    assert [(c.calculation, c.equipment_id) for c in cards] == [(HEAT_UP, "EA-425B")]


def test_wg_4_the_startup_step_gets_both_reboilers(wg_lines: dict[str, list[Card]]) -> None:
    cards = _target(wg_lines, "f:proc:P-REB-START-2:early:super:C16")
    assert [(c.calculation, c.equipment_id) for c in cards] == [
        (BLOCKED, "EA-425A"),
        (BLOCKED, "EA-425B"),
    ]
    verdicts = {c.equipment_id: physics.blocked_in_heating(c.equipment_id, _wg()) for c in cards}
    assert verdicts["EA-425B"].verdict == "confirmed"
    assert verdicts["EA-425A"].failed == ("not blocked in",)


def test_wg_5_the_ea_425a_flow_line_gets_none(wg_lines: dict[str, list[Card]]) -> None:
    assert _target(wg_lines, "f:m:S-EA-425A:more:flow:super:C22") == []


def _wg() -> Plant:
    return Plant.model_validate(json.loads(WG_FILE.read_text(encoding="utf-8")))


# --- the shortlist's `via_ids` (contract v1.11), read from the WG export ----------------------


def test_the_wg_shortlist_names_what_each_stored_calculation_card_is_attached_through() -> None:
    """Read time, same rule, on the re-attached export (R5): #2's EA-425B check is attached
    through its valves and step, #4's through its step, and every calculation card on the top
    five names its via; #1 keeps only its heat-up card; a precedent card has none."""
    from urllib.parse import quote

    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from guideword.api.app import create_app
    from guideword.settings import Settings

    settings = Settings(
        _env_file=None,
        guideword_env="hosted",
        nebius_api_key=SecretStr(""),
        tavily_api_key=SecretStr(""),
        database_url="sqlite://",
        guideword_recorded_dirs=[str(WG_EXPORT)],
    )
    run = _rows("runs")[0]["id"]
    items = (
        TestClient(create_app(settings=settings))
        .get(f"/runs/{quote(run, safe='')}/shortlist")
        .json()["items"]
    )

    # Phase 8 orders the confirmed tier by hypothesis rank, so the lines are found by what they
    # are, not by rank: the blocked-in chain (#2), the "more temperature" finding that carries
    # the heat-up card, and the start-up step finding
    def rank_of(prefix: str) -> int:
        return next(item["rank"] for item in items if item["target_id"].startswith(prefix))

    chain_rank = rank_of("ch:EA-425B.design_pressure_kpa+EA-425B.heat_sources")
    heat_rank = rank_of("f:m:S-EA-425B:more:temperature")
    step_rank = rank_of("f:proc:P-REB-START-2:early")
    assert chain_rank == 2
    via = {
        (item["rank"], ev["id"].rsplit(":", 1)[1]): ev["via_ids"]
        for item in items
        if item["rank"] in {*range(1, 6), heat_rank, step_rank}
        for ev in item["evidence"]
    }
    second = items[chain_rank - 1]["chain"]["links"]
    assert via[(chain_rank, "blocked_in_heating-EA-425B")] == [
        link
        for link in second
        if link.startswith("f:proc:P-REB-START-2:early")
        or link.split(".")[0] in {"HV-B-SIN", "HV-B-SOUT", "HV-QW-B-IN", "HV-QW-B-OUT"}
    ]
    assert (heat_rank, "blocked_in_heating-EA-425B") not in via
    assert via[(heat_rank, "heat_up_rate-EA-425B")] == [items[heat_rank - 1]["target_id"]]
    assert via[(step_rank, "blocked_in_heating-EA-425B")] == [items[step_rank - 1]["target_id"]]
    assert all(v for (_, key), v in via.items() if key.startswith(("blocked", "heat")))
    assert all(v == [] for (_, key), v in via.items() if not key.startswith(("blocked", "heat")))
