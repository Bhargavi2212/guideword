"""physics_calc: code-only calculations from plant facts (Phase 4 spec 4.1; plan PR 2, Q1,
Q10-Q13, G2, G3, G13).

The two fixtures are Cowork's hand-worked examples, written before this code and committed as
delivered; every expected number comes from them.
"""

import ast
import json
import math
from pathlib import Path
from typing import Any

import pytest

from guideword.review.display import calc_text
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Calculation,
    Confidence,
    FailingComponentType,
    SectionKind,
    SectionType,
    Tier,
    Verdict,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Section
from guideword.tools import physics
from guideword.tools.physics import (
    LOWER_BOUND_FLAG,
    Card,
    applicable,
    as_evidence,
    blocked_in_heating,
    heat_up_rate,
    overflow_time,
    vapour_pressure_kpaa,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
WG_FILE = ROOT / "cases" / "demo" / "williams_geismar.json"
EXAMPLE_FILE = ROOT / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
CONFIRM_MINUTES = 60.0
REL = 1e-9


def _fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return loaded


def _raw(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _plant(raw: dict[str, Any]) -> Plant:
    return Plant.model_validate(raw)


@pytest.fixture
def wg_raw() -> dict[str, Any]:
    return _raw(WG_FILE)


@pytest.fixture
def wg(wg_raw: dict[str, Any]) -> Plant:
    return _plant(wg_raw)


def _item(raw: dict[str, Any], block: str, object_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(o for o in raw[block] if o["id"] == object_id)
    return found


def _operating(raw: dict[str, Any], target: str, parameter: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        o for o in raw["operating"] if o["target_id"] == target and o["parameter"] == parameter
    )
    return found


def finding(question: str, components: list[str]) -> Finding:
    return Finding(
        id=ids.finding_id(question, Tier.LIGHTNING.value, components, cause_id="C01"),
        run_id=RUN,
        question_id=question,
        tier=Tier.LIGHTNING,
        cause_id="C01",
        failing_component_type=FailingComponentType.EXTERNAL,
        failing_component_ids=components,
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
    )


def section(section_id: str, object_ids: list[str]) -> Section:
    return Section(
        id=section_id,
        plant_record_id="plant:test",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.HEAT_EXCHANGER,
        name=section_id,
        object_ids=object_ids,
        drawn_by="rule",
    )


# --- the hand-worked WG fixture ------------------------------------------------------------------


def test_blocked_in_heating_matches_the_hand_worked_wg_fixture_exactly(wg: Plant) -> None:
    case = _fixture("example_wg_blocked_in.json")["cases"][0]
    result = blocked_in_heating("EA-425B", wg)
    reported = case["reported"]
    assert result.value == pytest.approx(reported["multiple"], rel=REL)
    assert result.detail["chemical"] == reported["chemical"]
    per_chemical = {c["chemical"]: c for c in case["per_chemical"] if c["multiple"] is not None}
    for chemical, expected in per_chemical.items():
        assert result.detail["multiples"][chemical] == pytest.approx(expected["multiple"], rel=REL)
        assert result.detail["pressures_kpaa"][chemical] == pytest.approx(
            expected["pressure_kpaa"], rel=REL
        )
    assert result.detail["temperature_c"] == case["temperature"]["used_c"]
    assert result.verdict == case["expected"]["verdict"]
    assert set(case["expected"]["fact_ids_include"]) <= set(result.fact_ids)
    assert set(case["expected"]["flags_include"]) <= set(result.flags)


def test_wg_reboiler_b_blocked_in_heating_is_confirmed_and_cites_every_fact(wg: Plant) -> None:
    result = blocked_in_heating("EA-425B", wg)
    assert result.verdict == Verdict.CONFIRMED
    assert result.failed == ()
    for fact in (
        "HV-B-SIN.normal_position",
        "HV-B-SOUT.normal_position",
        "HV-QW-B-IN.locked",
        "HV-QW-B-OUT.locked",
        "PROPANE.vapor_pressure_points",
        "PROPYLENE.vapor_pressure_points",
        "EA-425B.design_pressure_kpa",
        "L-QW-B-IN.operating.temperature.normal",
    ):
        assert fact in result.fact_ids, fact
    assert result.missing_fact_ids == ()
    assert "at least 1.6× design (lowest of the listed chemicals: PROPANE)" in result.summary
    assert "if EA-425B is isolated while hot quench water stays on" in result.summary


def test_wg_reboiler_a_is_none_not_blocked_in(wg: Plant) -> None:
    case = _fixture("example_wg_blocked_in.json")["cases"][1]
    result = blocked_in_heating("EA-425A", wg)
    assert result.verdict == case["expected"]["verdict"] == Verdict.NONE
    assert case["expected"]["summary_contains"] in result.summary
    assert result.failed == ("not blocked in",)
    assert set(case["expected"]["fact_ids_include"]) <= set(result.fact_ids)


def test_the_unit_interpolation_example_matches(wg: Plant) -> None:
    example = _fixture("example_wg_blocked_in.json")["unit_interpolation_example"]
    propane = next(c for c in wg.chemicals if c.id == example["chemical"])
    pressure = vapour_pressure_kpaa(propane.vapor_pressure_points, example["t_c"])
    assert pressure == pytest.approx(example["pressure_kpaa"], rel=REL)
    assert (
        vapour_pressure_kpaa(propane.vapor_pressure_points, example["out_of_range"]["t_c"]) is None
    )


# --- interpolation -------------------------------------------------------------------------------


def test_interpolation_is_exact_at_a_point_and_never_extrapolates(wg: Plant) -> None:
    propane = next(c for c in wg.chemicals if c.id == "PROPANE")
    points = propane.vapor_pressure_points
    assert vapour_pressure_kpaa(points, 85.0) == 3436.1
    assert vapour_pressure_kpaa(points, 30.0) == 1079.0
    assert vapour_pressure_kpaa(points, 95.0) == 4119.5
    assert vapour_pressure_kpaa(points, 29.9) is None
    assert vapour_pressure_kpaa(points, 95.1) is None
    # ln P is linear in 1/T between the bracketing points
    t1, t2 = 85.0 + physics.KELVIN_OFFSET, 90.0 + physics.KELVIN_OFFSET
    t = 87.5 + physics.KELVIN_OFFSET
    f = (1 / t - 1 / t1) / (1 / t2 - 1 / t1)
    expected = math.exp(math.log(3436.1) + f * (math.log(3764.1) - math.log(3436.1)))
    assert vapour_pressure_kpaa(points, 87.5) == pytest.approx(expected, rel=REL)


def test_points_are_used_in_temperature_order(wg: Plant) -> None:
    propane = next(c for c in wg.chemicals if c.id == "PROPANE")
    shuffled = list(reversed(propane.vapor_pressure_points))
    assert vapour_pressure_kpaa(shuffled, 87.0) == vapour_pressure_kpaa(
        propane.vapor_pressure_points, 87.0
    )


def test_fewer_than_two_points_skips(wg: Plant) -> None:
    propane = next(c for c in wg.chemicals if c.id == "PROPANE")
    assert vapour_pressure_kpaa(propane.vapor_pressure_points[:1], 30.0) is None
    assert vapour_pressure_kpaa([], 30.0) is None


# --- blocked_in_heating: the three conditions ----------------------------------------------------


def test_heat_source_lines_are_excluded_from_the_blocked_in_check(
    wg_raw: dict[str, Any],
) -> None:
    """EA-425B's quench-water lines carry its heat source's valves, so (1) looks only at its
    shell-side lines; opening a quench-water valve doesn't unblock it."""
    _item(wg_raw, "valves", "HV-QW-B-OUT")["normal_position"] = "open"
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert "not blocked in" not in result.failed
    assert "HV-QW-B-OUT.normal_position" not in result.fact_ids


def test_every_isolating_valve_locked_closed_is_none_heat_source_locked_out(
    wg_raw: dict[str, Any],
) -> None:
    for valve_id in ("HV-QW-B-IN", "HV-QW-B-OUT"):
        _item(wg_raw, "valves", valve_id)["locked"] = True
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.verdict == Verdict.NONE
    assert result.failed == ("heat source locked out",)
    assert "heat source locked out" in result.summary
    for fact in ("HV-QW-B-IN.locked", "HV-QW-B-IN.normal_position"):
        assert fact in result.fact_ids


def test_a_locked_open_valve_is_not_locked_out(wg_raw: dict[str, Any]) -> None:
    """Locked closed needs `locked: true` and `normal_position: closed`."""
    for valve_id in ("HV-QW-B-IN", "HV-QW-B-OUT"):
        _item(wg_raw, "valves", valve_id)["locked"] = True
    _item(wg_raw, "valves", "HV-QW-B-IN")["normal_position"] = "open"
    assert "heat source locked out" not in blocked_in_heating("EA-425B", _plant(wg_raw)).failed


def test_a_locked_out_heat_source_temperature_is_not_used(wg_raw: dict[str, Any]) -> None:
    """A second heat source, locked out, with a hotter line: its temperature isn't used."""
    _item(wg_raw, "equipment", "EA-425B")["heat_sources"].append(
        {"medium": "steam", "via_line_id": "L-QW-A-IN", "isolating_valve_ids": ["HV-QW-A-IN"]}
    )
    valve = _item(wg_raw, "valves", "HV-QW-A-IN")
    valve["locked"], valve["normal_position"] = True, "closed"
    _operating(wg_raw, "L-QW-A-IN", "temperature")["normal"] = 90
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.detail["temperature_c"] == 85
    assert result.detail["heat_source"] == "hot quench water"


def test_the_highest_heat_source_temperature_is_used(wg_raw: dict[str, Any]) -> None:
    _item(wg_raw, "equipment", "EA-425B")["heat_sources"].append(
        {"medium": "steam", "via_line_id": "L-QW-A-IN", "isolating_valve_ids": []}
    )
    _operating(wg_raw, "L-QW-A-IN", "temperature")["normal"] = 90
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.detail["temperature_c"] == 90
    assert result.detail["heat_source"] == "steam"
    assert "L-QW-A-IN.operating.temperature.normal" in result.fact_ids


def test_the_design_max_is_used_when_set_and_flagged(wg_raw: dict[str, Any]) -> None:
    _operating(wg_raw, "L-QW-B-IN", "temperature")["design_max"] = 90
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.detail["temperature_c"] == 90
    assert "L-QW-B-IN.operating.temperature.design_max" in result.fact_ids
    assert "heating-medium temperature from design_max" in result.flags


def test_below_design_is_none_below_design(wg_raw: dict[str, Any]) -> None:
    _item(wg_raw, "equipment", "EA-425B")["design_pressure_kpa"] = 5000
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.verdict == Verdict.NONE
    assert result.failed == ("below design",)
    assert result.value is not None and result.value < 1


def test_below_one_is_none_never_contradicted(wg_raw: dict[str, Any]) -> None:
    _item(wg_raw, "equipment", "EA-425B")["design_pressure_kpa"] = 50000
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.verdict == Verdict.NONE
    assert result.verdict != Verdict.CONTRADICTED


def test_a_multiple_within_1e_9_of_one_is_at_design(wg_raw: dict[str, Any]) -> None:
    """The threshold rule (Cowork's example_overflow_heatup.json): within a relative 1e-9 of
    a threshold counts as equal, so at design is `confirmed`."""
    gauge = 3436.1 - physics.ATMOSPHERE_KPA
    _item(wg_raw, "equipment", "EA-425B")["design_pressure_kpa"] = gauge * (1 + 1e-12)
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.value is not None and result.value < 1
    assert result.verdict == Verdict.CONFIRMED


def test_no_process_side_line_is_not_blocked_in(wg_raw: dict[str, Any]) -> None:
    """With no shell-side line the facts can't show the equipment blocked in."""
    shell = ("L-B-SIN", "L-B-SOUT")
    wg_raw["lines"] = [line for line in wg_raw["lines"] if line["id"] not in shell]
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.failed[0] == "not blocked in"


def test_a_heat_source_with_no_isolating_valve_is_not_locked_out(
    wg_raw: dict[str, Any],
) -> None:
    _item(wg_raw, "equipment", "EA-425B")["heat_sources"][0]["isolating_valve_ids"] = []
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert "heat source locked out" not in result.failed
    assert "EA-425B.heat_sources" in result.fact_ids


def test_every_failed_condition_is_named_in_order(wg_raw: dict[str, Any]) -> None:
    for valve_id in ("HV-QW-A-IN", "HV-QW-A-OUT"):
        valve = _item(wg_raw, "valves", valve_id)
        valve["locked"], valve["normal_position"] = True, "closed"
    result = blocked_in_heating("EA-425A", _plant(wg_raw))
    assert result.failed == ("not blocked in", "heat source locked out")
    assert result.summary.index("not blocked in") < result.summary.index("heat source locked out")


def test_a_missing_input_is_skipped_never_below_design(wg_raw: dict[str, Any]) -> None:
    del _item(wg_raw, "equipment", "EA-425B")["design_pressure_kpa"]
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.verdict == Verdict.NONE
    assert result.value is None
    assert result.missing_fact_ids == ("EA-425B.design_pressure_kpa",)
    assert "below design" not in result.failed


def test_blocked_in_heating_without_the_temperature_row_names_it(
    wg_raw: dict[str, Any],
) -> None:
    wg_raw["operating"] = [o for o in wg_raw["operating"] if o["target_id"] != "L-QW-B-IN"]
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.missing_fact_ids == ("L-QW-B-IN.operating.temperature.normal",)
    assert result.verdict == Verdict.NONE


def test_blocked_in_heating_without_heat_sources_names_it(wg_raw: dict[str, Any]) -> None:
    _item(wg_raw, "equipment", "EA-425B")["heat_sources"] = []
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.missing_fact_ids == ("EA-425B.heat_sources",)
    assert result.verdict == Verdict.NONE


def test_the_lowest_multiple_is_reported_and_its_chemical_named(wg: Plant) -> None:
    result = blocked_in_heating("EA-425B", wg)
    multiples = result.detail["multiples"]
    assert set(multiples) == {"PROPANE", "PROPYLENE"}
    assert result.value == min(multiples.values()) == multiples["PROPANE"]
    assert result.detail["chemical"] == "PROPANE"


def test_chemicals_without_points_are_named_no_data(wg: Plant) -> None:
    result = blocked_in_heating("EA-425B", wg)
    assert "no data: C4-HEAVIES; bound covers listed chemicals only" in result.flags
    assert "C4-HEAVIES.vapor_pressure_points" not in result.missing_fact_ids


def test_no_content_chemical_with_points_is_none_naming_them(wg_raw: dict[str, Any]) -> None:
    for chemical in wg_raw["chemicals"]:
        chemical.pop("vapor_pressure_points", None)
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert result.verdict == Verdict.NONE
    assert result.value is None
    assert set(result.missing_fact_ids) == {
        "PROPANE.vapor_pressure_points",
        "PROPYLENE.vapor_pressure_points",
        "C4-HEAVIES.vapor_pressure_points",
    }


def test_a_chemical_outside_its_points_is_not_extrapolated(wg_raw: dict[str, Any]) -> None:
    """At 93 °C propylene (points to 90 °C) is left out and named; propane still bounds."""
    _operating(wg_raw, "L-QW-B-IN", "temperature")["normal"] = 93
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    assert set(result.detail["multiples"]) == {"PROPANE"}
    assert "PROPYLENE.vapor_pressure_points" not in result.fact_ids
    assert any("PROPYLENE" in flag and "outside" in flag for flag in result.flags)


def test_blocked_in_heating_always_carries_the_lower_bound_flag(wg: Plant) -> None:
    for equipment in ("EA-425A", "EA-425B"):
        assert LOWER_BOUND_FLAG in blocked_in_heating(equipment, wg).flags


def test_the_verdict_is_the_same_on_every_line_with_that_equipment(wg: Plant) -> None:
    """It depends on the equipment and the plant only: no line is passed in."""
    assert blocked_in_heating("EA-425B", wg) == blocked_in_heating("EA-425B", wg)


# --- applicability -------------------------------------------------------------------------------


def test_applicability_is_by_question_id_and_what_the_line_names(wg: Plant) -> None:
    """The matrix rule reads the question; the blocked-in rule (review plan §0a) needs the line
    to name the vessel and one of its valves or steps, so naming the vessel alone is not
    enough (Phase 4's scenario-object rule gave `env` a card here)."""
    pressure = finding("m:S-EA-425B:more:pressure", ["HV-B-SIN"])
    flow = finding("m:S-L-QW-B-IN:less:flow", ["HV-QW-B-IN"])
    env = finding("env:C4-HEAVIES:air", ["EA-425B", "LOC-OLEFINS-UNIT"])
    s_b = section("S-EA-425B", ["EA-425B"])
    s_flow = section("S-L-QW-B-IN", ["L-QW-B-IN", "HV-QW-B-IN"])
    assert applicable([(pressure, s_b)], wg) == [
        Card(Calculation.BLOCKED_IN_HEATING, "EA-425B", (pressure.id,))
    ]
    assert applicable([(env, None)], wg) == []  # the vessel, but none of its valves
    assert applicable([(flow, s_flow)], wg) == []  # a valve, but not the vessel


def test_more_level_and_more_temperature_get_their_calculations() -> None:
    plant = _plant(_raw(EXAMPLE_FILE))
    level = finding("m:S-MX-1:more:level", ["HV-12"])
    temp = finding("m:S-MX-1:more:temperature", ["TV-1"])
    s = section("S-MX-1", ["MX-1"])
    # the line names HV-12, an MX-1 valve, but not MX-1 itself: no blocked-in check (§0a)
    assert applicable([(level, s)], plant) == [
        Card(Calculation.OVERFLOW_TIME, "MX-1", (level.id,)),
    ]
    assert Card(Calculation.HEAT_UP_RATE, "MX-1", (temp.id,)) in applicable([(temp, s)], plant)


def test_one_card_per_equipment_when_both_rules_reach_it(wg: Plant) -> None:
    pressure = finding("m:S-EA-425A:more:pressure", ["EA-425A"])
    other = finding("m:S-EA-425A:more:pressure", ["HV-A-SIN"])
    s_a = section("S-EA-425A", ["EA-425A"])
    assert applicable([(pressure, s_a), (other, s_a)], wg) == [
        Card(Calculation.BLOCKED_IN_HEATING, "EA-425A", (pressure.id, other.id))
    ]


def test_wg_reboiler_a_line_gets_one_card_none_not_blocked_in(wg: Plant) -> None:
    """Today's line 5: `m:S-EA-425A:less:flow` and `m:S-EA-425A:more:pressure`."""
    s_a = section("S-EA-425A", ["EA-425A"])
    links = [
        (finding("m:S-EA-425A:less:flow", ["HV-A-SIN"]), s_a),
        (finding("m:S-EA-425A:more:pressure", ["EA-425A"]), s_a),
    ]
    cards = applicable(links, wg)
    # the matrix rule through more:pressure; the blocked-in rule through less:flow's HV-A-SIN
    assert cards == [
        Card(Calculation.BLOCKED_IN_HEATING, "EA-425A", (links[0][0].id, links[1][0].id))
    ]
    result = blocked_in_heating("EA-425A", wg)
    assert (result.verdict, result.failed) == (Verdict.NONE, ("not blocked in",))


def test_more_pressure_equipment_without_heat_sources_names_the_missing_fact() -> None:
    raw = _raw(EXAMPLE_FILE)
    _item(raw, "equipment", "MX-1")["heat_sources"] = []
    plant = _plant(raw)
    s = section("S-MX-1", ["MX-1"])
    pressure = finding("m:S-MX-1:more:pressure", ["TV-1"])
    assert applicable([(pressure, s)], plant) == [
        Card(Calculation.BLOCKED_IN_HEATING, "MX-1", (pressure.id,))
    ]
    assert "MX-1.heat_sources" in blocked_in_heating("MX-1", plant).missing_fact_ids
    # the blocked-in rule never reaches equipment without a heat source
    assert applicable([(finding("env:SIH:air", ["MX-1", "HV-12"]), None)], plant) == []


def test_two_equipment_on_one_line_get_two_calculation_ids(wg: Plant) -> None:
    named = ["EA-425A", "EA-425B", "HV-QW-A-IN", "HV-QW-B-IN", "LOC-OLEFINS-UNIT"]
    env = finding("env:C4-HEAVIES:air", named)
    cards = applicable([(env, None)], wg)
    assert cards == [
        Card(Calculation.BLOCKED_IN_HEATING, "EA-425A", (env.id,)),
        Card(Calculation.BLOCKED_IN_HEATING, "EA-425B", (env.id,)),
    ]
    evidence_ids = {ids.calculation_evidence_id(env.id, c, e) for c, e, _ in cards}
    assert len(evidence_ids) == 2


# --- overflow_time and heat_up_rate (Cowork's example_overflow_heatup.json) -------------------


def _example(synthetic: dict[str, Any], level: float | None, duty: float | None) -> Plant:
    raw = _raw(EXAMPLE_FILE)
    for chemical in raw["chemicals"]:
        chemical["density_kg_m3"] = synthetic[f"{chemical['id']}.density_kg_m3"]
        chemical["heat_capacity_kj_kg_k"] = synthetic[f"{chemical['id']}.heat_capacity_kj_kg_k"]
    if level is not None:
        raw["operating"].append({"target_id": "MX-1", "parameter": "level", "normal": level})
    if duty is not None:
        _item(raw, "equipment", "MX-1")["heat_duty_kw"] = duty
    return _plant(raw)


def test_overflow_time_matches_its_hand_example() -> None:
    example = _fixture("example_overflow_heatup.json")
    for variant in example["overflow_time"]["variants"]:
        plant = _example(example["synthetic_facts"], variant["normal"], None)
        result = overflow_time("MX-1", plant, CONFIRM_MINUTES)
        assert result.verdict == variant["verdict"], variant["name"]
        if "minutes" in variant:
            assert result.value == pytest.approx(variant["minutes"], rel=REL)
            assert result.detail["chemical"] == "SIH"
        else:
            assert result.missing_fact_ids == tuple(variant["missing_fact_ids"])


def test_a_value_within_1e_9_of_a_threshold_counts_as_equal() -> None:
    """Level 80 %: 59.999999999999986 minutes in floating point is not below 60."""
    example = _fixture("example_overflow_heatup.json")
    plant = _example(example["synthetic_facts"], 80, None)
    result = overflow_time("MX-1", plant, CONFIRM_MINUTES)
    assert result.value is not None and result.value < 60
    assert result.verdict == Verdict.NONE
    assert physics.below(59.999999999999986, 60.0) is False
    assert physics.below(59.9, 60.0) is True
    assert physics.at_least(1.0 - 1e-12, 1.0) is True


def test_heat_up_rate_matches_its_hand_example() -> None:
    example = _fixture("example_overflow_heatup.json")
    for variant in example["heat_up_rate"]["variants"]:
        plant = _example(example["synthetic_facts"], None, variant["heat_duty_kw"])
        result = heat_up_rate("MX-1", plant, CONFIRM_MINUTES)
        assert result.verdict == variant["verdict"], variant["name"]
        assert result.value == pytest.approx(variant["minutes_to_limit"], rel=REL)
        assert result.detail["c_per_min"] == pytest.approx(variant["c_per_min"], rel=REL)


def test_the_lowest_density_and_heat_capacity_are_used_and_named() -> None:
    example = _fixture("example_overflow_heatup.json")
    plant = _example(example["synthetic_facts"], None, 50.0)
    result = heat_up_rate("MX-1", plant, CONFIRM_MINUTES)
    assert result.detail["density_chemical"] == "SIH"
    assert result.detail["heat_capacity_chemical"] == "SIH"
    assert "SIH.density_kg_m3" in result.fact_ids
    assert "SIH.heat_capacity_kj_kg_k" in result.fact_ids


@pytest.mark.parametrize(
    "remove, fact",
    [
        ("volume", "MX-1.volume_m3"),
        ("level", "MX-1.operating.level.normal"),
        ("flow", "L-12.normal_flow_kg_h"),
        ("density", "SIH.density_kg_m3"),
    ],
)
def test_overflow_time_without_each_fact_names_it(remove: str, fact: str) -> None:
    example = _fixture("example_overflow_heatup.json")
    raw = _raw(EXAMPLE_FILE)
    for chemical in raw["chemicals"]:
        chemical["density_kg_m3"] = example["synthetic_facts"][f"{chemical['id']}.density_kg_m3"]
    raw["operating"].append({"target_id": "MX-1", "parameter": "level", "normal": 90})
    if remove == "volume":
        del _item(raw, "equipment", "MX-1")["volume_m3"]
    elif remove == "level":
        raw["operating"] = [o for o in raw["operating"] if o["parameter"] != "level"]
    elif remove == "flow":
        del _item(raw, "lines", "L-12")["normal_flow_kg_h"]
    else:
        for chemical in raw["chemicals"]:
            del chemical["density_kg_m3"]
    result = overflow_time("MX-1", _plant(raw), CONFIRM_MINUTES)
    assert result.verdict == Verdict.NONE
    assert fact in result.missing_fact_ids
    assert result.value is None


@pytest.mark.parametrize(
    "remove, fact",
    [
        ("duty", "MX-1.heat_duty_kw"),
        ("volume", "MX-1.volume_m3"),
        ("density", "SIH.density_kg_m3"),
        ("heat_capacity", "SIH.heat_capacity_kj_kg_k"),
        ("normal", "MX-1.operating.temperature.normal"),
        ("limit", "MX-1.operating.temperature.design_max"),
    ],
)
def test_heat_up_rate_without_each_fact_names_it(remove: str, fact: str) -> None:
    example = _fixture("example_overflow_heatup.json")
    raw = _raw(EXAMPLE_FILE)
    for chemical in raw["chemicals"]:
        chemical["density_kg_m3"] = example["synthetic_facts"][f"{chemical['id']}.density_kg_m3"]
        chemical["heat_capacity_kj_kg_k"] = example["synthetic_facts"][
            f"{chemical['id']}.heat_capacity_kj_kg_k"
        ]
    mx = _item(raw, "equipment", "MX-1")
    mx["heat_duty_kw"] = 50.0
    row = _operating(raw, "MX-1", "temperature")
    if remove == "duty":
        del mx["heat_duty_kw"]
    elif remove == "volume":
        del mx["volume_m3"]
    elif remove == "density":
        for chemical in raw["chemicals"]:
            del chemical["density_kg_m3"]
    elif remove == "heat_capacity":
        for chemical in raw["chemicals"]:
            del chemical["heat_capacity_kj_kg_k"]
    elif remove == "normal":
        del row["normal"]
    else:
        del row["design_max"]
        del mx["design_temp_c"]
    result = heat_up_rate("MX-1", _plant(raw), CONFIRM_MINUTES)
    assert result.verdict == Verdict.NONE
    assert fact in result.missing_fact_ids
    assert result.value is None


def test_heat_up_rate_falls_back_to_design_temp_c() -> None:
    example = _fixture("example_overflow_heatup.json")
    raw = _raw(EXAMPLE_FILE)
    for chemical in raw["chemicals"]:
        chemical["density_kg_m3"] = example["synthetic_facts"][f"{chemical['id']}.density_kg_m3"]
        chemical["heat_capacity_kj_kg_k"] = example["synthetic_facts"][
            f"{chemical['id']}.heat_capacity_kj_kg_k"
        ]
    _item(raw, "equipment", "MX-1")["heat_duty_kw"] = 500.0
    del _operating(raw, "MX-1", "temperature")["design_max"]
    result = heat_up_rate("MX-1", _plant(raw), CONFIRM_MINUTES)
    assert "MX-1.design_temp_c" in result.fact_ids
    assert result.value == pytest.approx(27.5, rel=REL)


def test_no_calculation_is_ever_contradicted(wg: Plant) -> None:
    results = [blocked_in_heating(e, wg) for e in ("EA-425A", "EA-425B")]
    assert all(r.verdict != Verdict.CONTRADICTED for r in results)


# --- display -------------------------------------------------------------------------------------


def test_calc_text_is_two_significant_figures(wg: Plant) -> None:
    assert calc_text(Calculation.BLOCKED_IN_HEATING, 1.6125604448742747) == "at least 1.6× design"
    assert calc_text(Calculation.OVERFLOW_TIME, 27.5) == "about 28 minutes"
    assert calc_text(Calculation.HEAT_UP_RATE, 275.00000000000006) == "about 280 minutes"
    assert calc_text(Calculation.OVERFLOW_TIME, 0.123) == "about 0.12 minutes"
    assert calc_text(Calculation.HEAT_UP_RATE, 3.5) == "about 3.5 minutes"
    assert calc_text(Calculation.BLOCKED_IN_HEATING, 1.9233438104448743) == "at least 1.9× design"
    # the stored value is never rounded
    assert blocked_in_heating("EA-425B", wg).value == pytest.approx(1.6125604448742747, rel=REL)


# --- the module ----------------------------------------------------------------------------------


def test_physics_imports_no_gateway_and_no_network_client() -> None:
    tree = ast.parse(Path(physics.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    banned = ("guideword.gateway", "openai", "httpx", "tavily", "requests", "socket", "urllib")
    assert not [name for name in imported if name.startswith(banned)]


def test_the_physical_constants_are_named() -> None:
    assert physics.ATMOSPHERE_KPA == 101.325
    assert physics.KELVIN_OFFSET == 273.15


# --- the tool call's result and the evidence record (Bhargavi, 2026-10-21) ---------------------


def test_the_tool_result_holds_the_raw_unrounded_value(wg: Plant) -> None:
    result = blocked_in_heating("EA-425B", wg)
    tool = result.tool_result()
    assert tool["value"] == result.value
    assert tool["value"] == pytest.approx(1.6125604448742747, rel=REL)
    assert tool["value"] != 1.6
    # it survives the tool call record's JSON unchanged
    assert json.loads(json.dumps(tool))["value"] == result.value
    assert tool["detail"]["multiples"]["PROPYLENE"] == pytest.approx(1.9233438104448743, rel=REL)
    assert tool["fact_ids"] == list(result.fact_ids)


def test_the_evidence_summary_is_the_card_text_from_the_one_formatter(wg: Plant) -> None:
    result = blocked_in_heating("EA-425B", wg)
    assert result.value is not None
    evidence = as_evidence(result, run_id=RUN, target_id="f:x", tool_call_id="tc:step:x:y:z")
    assert evidence.summary == result.summary
    assert calc_text(Calculation.BLOCKED_IN_HEATING, result.value) in evidence.summary
    assert "1.612" not in evidence.summary
    assert evidence.id == ids.calculation_evidence_id("f:x", "blocked_in_heating", "EA-425B")
    assert evidence.verdict == Verdict.CONFIRMED
    assert evidence.tool_call_id == "tc:step:x:y:z"
    assert evidence.fact_ids == list(result.fact_ids)
    assert evidence.flags == list(result.flags)


def test_a_skipped_calculation_record_names_its_missing_facts(wg_raw: dict[str, Any]) -> None:
    del _item(wg_raw, "equipment", "EA-425B")["design_pressure_kpa"]
    result = blocked_in_heating("EA-425B", _plant(wg_raw))
    evidence = as_evidence(result, run_id=RUN, target_id="f:x", tool_call_id="tc:step:x:y:z")
    assert evidence.verdict == Verdict.NONE
    assert evidence.missing_fact_ids == ["EA-425B.design_pressure_kpa"]
    assert result.tool_result()["value"] is None


def test_overflow_and_heat_up_summaries_use_the_one_formatter() -> None:
    example = _fixture("example_overflow_heatup.json")
    plant = _example(example["synthetic_facts"], 90, 500.0)
    for result in (
        overflow_time("MX-1", plant, CONFIRM_MINUTES),
        heat_up_rate("MX-1", plant, CONFIRM_MINUTES),
    ):
        assert result.value is not None
        assert calc_text(result.calculation, result.value) in result.summary
        assert result.tool_result()["value"] == result.value
