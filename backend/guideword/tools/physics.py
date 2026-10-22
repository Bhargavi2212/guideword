"""`physics_calc`: three calculations from plant facts, code only (Phase 4 spec 4.1; plan PR 2,
Q1, Q10-Q13, G3, G13).

Each takes plant facts only and returns a `CalcResult`: a value with its unit and the fact IDs
used, or `None` and the missing fact IDs. Nothing is defaulted: a missing fact is named, never
filled in. The verdict is `confirmed` or `none`, never `contradicted`, because each result is a
lower bound or a time to a limit.

- `blocked_in_heating`: the vapour pressure the equipment's contents reach at its heat source's
  temperature, as a multiple of design pressure; the lowest of the content chemicals with
  points (Q12). `confirmed` only when the facts show (1) the equipment blocked in, (2) a heat
  source not locked out and (3) the multiple at or above design (Q11).
- `overflow_time`: minutes from the normal level to 100 % at the largest inflow.
- `heat_up_rate`: °C per minute at the heat duty, and minutes from normal to the limit.

Thresholds are compared by `below` and `at_least`: a value within a relative 1e-9 of its
threshold counts as equal to it (Cowork's `example_overflow_heatup.json`). The confirm minutes
come from caps.yaml's `evidence:` block, through the caller.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from guideword.review.display import calc_text
from guideword.schema.enums import (
    Calculation,
    EvidenceKind,
    OperatingParameter,
    QuestionKind,
    ValvePosition,
    Verdict,
)
from guideword.schema.ids import calculation_evidence_id, parse_question_id
from guideword.schema.plant import Chemical, Equipment, Line, Operating, Plant, Valve
from guideword.schema.plant import VaporPressurePoint as Point
from guideword.schema.records import Evidence, Finding, Section

# ISO 2533 / CODATA standard atmosphere: gauge = absolute - 101.325 kPa
ATMOSPHERE_KPA = 101.325
# SI definition: T(K) = t(°C) + 273.15
KELVIN_OFFSET = 273.15
# Cowork's example_overflow_heatup.json: within this relative distance a value equals its
# threshold, so floating-point noise never flips a verdict
RELATIVE_TOLERANCE = 1e-9
# the check's definition, not a tunable threshold: "at or above design" (plan G3)
DESIGN_MULTIPLE = 1.0

LOWER_BOUND_FLAG = (
    "pure-component vapour pressure; liquid-full thermal expansion not modelled; "
    "real pressure can be higher"
)
NOT_BLOCKED_IN = "not blocked in"
LOCKED_OUT = "heat source locked out"
BELOW_DESIGN = "below design"
FULL_LEVEL_PCT = 100.0
MINUTES_PER_HOUR = 60.0
SECONDS_PER_MINUTE = 60.0

# the guideword and parameter of a matrix question that brings each calculation
_BY_QUESTION = {
    ("more", "pressure"): Calculation.BLOCKED_IN_HEATING,
    ("more", "level"): Calculation.OVERFLOW_TIME,
    ("more", "temperature"): Calculation.HEAT_UP_RATE,
}
_ORDER = list(Calculation)


@dataclass(frozen=True)
class CalcResult:
    calculation: Calculation
    equipment_id: str
    verdict: Verdict
    # the stored number, never rounded; None when a fact is missing
    value: float | None
    unit: str
    summary: str
    fact_ids: tuple[str, ...] = ()
    missing_fact_ids: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    # blocked_in_heating: the conditions that failed, in order 1, 2, 3
    failed: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict, compare=False)

    def tool_result(self) -> dict[str, Any]:
        """The `physics_calc` tool call's result: the raw value, never rounded, with
        everything it was computed from (Bhargavi, 2026-10-21)."""
        return {
            "calculation": str(self.calculation),
            "equipment_id": self.equipment_id,
            "verdict": str(self.verdict),
            "value": self.value,
            "unit": self.unit,
            "fact_ids": list(self.fact_ids),
            "missing_fact_ids": list(self.missing_fact_ids),
            "flags": list(self.flags),
            "failed": list(self.failed),
            "detail": self.detail,
        }


def as_evidence(result: CalcResult, *, run_id: str, target_id: str, tool_call_id: str) -> Evidence:
    """The line's evidence record: the card text from the one formatter in `summary` (the raw
    value stays in the tool call's result), keyed by calculation and equipment (plan G2)."""
    return Evidence(
        id=calculation_evidence_id(target_id, result.calculation, result.equipment_id),
        run_id=run_id,
        target_id=target_id,
        kind=EvidenceKind.CALCULATION,
        verdict=result.verdict,
        summary=result.summary,
        tool_call_id=tool_call_id,
        fact_ids=list(result.fact_ids),
        missing_fact_ids=list(result.missing_fact_ids),
        flags=list(result.flags),
    )


def below(value: float, threshold: float) -> bool:
    """`value < threshold`, where a value within a relative 1e-9 of it counts as equal."""
    return value < threshold and not math.isclose(value, threshold, rel_tol=RELATIVE_TOLERANCE)


def at_least(value: float, threshold: float) -> bool:
    return not below(value, threshold)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


# --- plant lookups -------------------------------------------------------------------------------


def _equipment(plant: Plant, equipment_id: str) -> Equipment:
    found = next((e for e in plant.equipment if e.id == equipment_id), None)
    if found is None:
        raise KeyError(f"no equipment {equipment_id}")
    return found


def _row(plant: Plant, target_id: str, parameter: OperatingParameter) -> Operating | None:
    return next(
        (o for o in plant.operating if o.target_id == target_id and o.parameter == parameter),
        None,
    )


def _operating_fact(target_id: str, parameter: OperatingParameter, limit: str) -> str:
    return f"{target_id}.operating.{parameter}.{limit}"


def _contents(plant: Plant, equipment: Equipment) -> list[Chemical]:
    chemicals = {c.id: c for c in plant.chemicals}
    return [chemicals[c] for c in equipment.contents if c in chemicals]


# --- vapour pressure -----------------------------------------------------------------------------


def vapour_pressure_kpaa(points: Sequence[Point], temp_c: float) -> float | None:
    """Clausius-Clapeyron between the two bracketing points: ln P linear in 1/T, T in K. A
    temperature at a point gives that point; outside the points, or with fewer than two, None:
    never extrapolated."""
    ordered = sorted(points, key=lambda p: p.temp_c)
    if len(ordered) < 2 or not ordered[0].temp_c <= temp_c <= ordered[-1].temp_c:
        return None
    for point in ordered:
        if point.temp_c == temp_c:
            return point.pressure_kpaa
    low, high = next(
        (a, b) for a, b in zip(ordered, ordered[1:], strict=False) if a.temp_c < temp_c < b.temp_c
    )
    t, t1, t2 = (x + KELVIN_OFFSET for x in (temp_c, low.temp_c, high.temp_c))
    fraction = (1 / t - 1 / t1) / (1 / t2 - 1 / t1)
    ln_p = math.log(low.pressure_kpaa) + fraction * (
        math.log(high.pressure_kpaa) - math.log(low.pressure_kpaa)
    )
    return math.exp(ln_p)


# --- blocked_in_heating --------------------------------------------------------------------------


def _isolating_valves(equipment: Equipment) -> set[str]:
    return {v for source in equipment.heat_sources for v in source.isolating_valve_ids}


def _locked_closed(valve: Valve) -> bool:
    return valve.locked is True and valve.normal_position == ValvePosition.CLOSED


def _blocked_in(
    equipment: Equipment, plant: Plant, valves: dict[str, Valve]
) -> tuple[bool, list[str], list[str]]:
    """(1): every process-side line has a normally closed valve. Returns (holds, facts,
    missing)."""
    heat_valves = _isolating_valves(equipment)
    process: list[Line] = [
        line
        for line in plant.lines
        if equipment.id in (line.from_id, line.to_id) and not heat_valves & set(line.components)
    ]
    if not process:
        return False, [], []
    holds, facts, missing = True, [], []
    for line in process:
        on_line = [valves[c] for c in line.components if c in valves]
        closed = [v for v in on_line if v.normal_position == ValvePosition.CLOSED]
        if closed:
            facts += [f"{v.id}.normal_position" for v in closed]
            continue
        unknown = [v for v in on_line if v.normal_position is None]
        if unknown:
            missing += [f"{v.id}.normal_position" for v in unknown]
        else:
            holds = False
            facts += [f"{v.id}.normal_position" for v in on_line]
    if missing and holds:
        return False, facts, missing
    return holds, facts, []


def _not_locked_out(
    equipment: Equipment, valves: dict[str, Valve]
) -> tuple[bool, list[str], list[int]]:
    """(2): at least one heat source has an isolating valve that isn't locked closed. Returns
    (holds, facts, the indexes of the heat sources not locked out)."""
    facts: list[str] = []
    open_sources: list[int] = []
    for index, source in enumerate(equipment.heat_sources):
        if not source.isolating_valve_ids:
            facts.append(f"{equipment.id}.heat_sources")
            open_sources.append(index)
            continue
        locked_out = True
        for valve_id in source.isolating_valve_ids:
            valve = valves.get(valve_id)
            if valve is None:
                locked_out = False
                continue
            if valve.locked is not None:
                facts.append(f"{valve.id}.locked")
            if valve.locked is True and valve.normal_position is not None:
                facts.append(f"{valve.id}.normal_position")
            if not _locked_closed(valve):
                locked_out = False
        if not locked_out:
            open_sources.append(index)
    return bool(open_sources), facts, open_sources


def blocked_in_heating(equipment_id: str, plant: Plant) -> CalcResult:
    """The verdict depends on the equipment and the plant only, so it is the same on every
    line that reaches it."""
    equipment = _equipment(plant, equipment_id)
    valves = {v.id: v for v in plant.valves}
    calc = Calculation.BLOCKED_IN_HEATING
    if not equipment.heat_sources:
        missing = [f"{equipment.id}.heat_sources"]
        if equipment.design_pressure_kpa is None:
            missing.append(f"{equipment.id}.design_pressure_kpa")
        return _skipped(calc, equipment, missing, (LOWER_BOUND_FLAG,))

    blocked, facts_1, missing_1 = _blocked_in(equipment, plant, valves)
    unlocked, facts_2, open_sources = _not_locked_out(equipment, valves)
    failed = [NOT_BLOCKED_IN] if not blocked and not missing_1 else []
    if not unlocked:
        failed.append(LOCKED_OUT)

    flags = [LOWER_BOUND_FLAG]
    facts = facts_1 + facts_2
    missing = list(missing_1)
    detail: dict[str, Any] = {}
    value: float | None = None

    if unlocked:
        multiple = _multiple(equipment, plant, open_sources, facts, missing, flags, detail)
        if multiple is not None:
            value = multiple
            if not at_least(multiple, DESIGN_MULTIPLE):
                failed.append(BELOW_DESIGN)

    verdict = (
        Verdict.CONFIRMED if value is not None and not failed and not missing else Verdict.NONE
    )
    summary = _blocked_in_summary(equipment, value, detail, failed, missing)
    return CalcResult(
        calculation=calc,
        equipment_id=equipment.id,
        verdict=verdict,
        value=value,
        unit="x_design",
        summary=summary,
        fact_ids=_unique(facts),
        missing_fact_ids=_unique(missing),
        flags=_unique(flags),
        failed=tuple(failed),
        detail=detail,
    )


def _multiple(
    equipment: Equipment,
    plant: Plant,
    open_sources: list[int],
    facts: list[str],
    missing: list[str],
    flags: list[str],
    detail: dict[str, Any],
) -> float | None:
    """(3)'s number: the lowest multiple of design over the content chemicals with points, at
    the highest temperature among the heat sources not locked out. Appends what it used or
    lacked to `facts`, `missing` and `flags`."""
    design = equipment.design_pressure_kpa
    if design is None:
        missing.append(f"{equipment.id}.design_pressure_kpa")
    temperature = _heat_source_temperature(equipment, plant, open_sources, missing)
    contents = _contents(plant, equipment)
    with_points = [c for c in contents if c.vapor_pressure_points]
    no_data = [c.id for c in contents if not c.vapor_pressure_points]
    if not with_points:
        missing += [f"{c}.vapor_pressure_points" for c in no_data]
        if not contents:
            missing.append(f"{equipment.id}.contents")
        return None
    if design is None or temperature is None:
        return None

    temp_c, source_name, temp_fact, used = temperature
    pressures: dict[str, float] = {}
    outside: list[str] = []
    for chemical in with_points:
        pressure = vapour_pressure_kpaa(chemical.vapor_pressure_points, temp_c)
        if pressure is None:
            outside.append(chemical.id)
        else:
            pressures[chemical.id] = pressure
    if not pressures:
        missing += [f"{c}.vapor_pressure_points" for c in outside]
        return None
    multiples = {c: (p - ATMOSPHERE_KPA) / design for c, p in pressures.items()}
    lowest = min(multiples, key=lambda c: (multiples[c], c))
    facts += [f"{equipment.id}.design_pressure_kpa", temp_fact]
    facts += [f"{c}.vapor_pressure_points" for c in pressures]
    flags.append(
        "heating-medium temperature from design_max"
        if used == "design_max"
        else "heating-medium temperature from normal (no design_max)"
    )
    if no_data:
        flags.append(f"no data: {', '.join(no_data)}; bound covers listed chemicals only")
    if outside:
        flags.append(
            f"outside vapour-pressure points at {temp_c:g} °C: {', '.join(outside)}; "
            "bound covers listed chemicals only"
        )
    detail.update(
        chemical=lowest,
        heat_source=source_name,
        temperature_c=temp_c,
        pressures_kpaa=pressures,
        multiples=multiples,
    )
    return multiples[lowest]


def _heat_source_temperature(
    equipment: Equipment, plant: Plant, open_sources: list[int], missing: list[str]
) -> tuple[float, str, str, str] | None:
    """The highest heating-medium temperature among the heat sources not locked out: each
    one's line `operating` temperature row, `design_max` if set, else `normal`. Returns
    (°C, medium, fact ID, limit used)."""
    found: list[tuple[float, str, str, str]] = []
    lacking: list[str] = []
    for index in open_sources:
        source = equipment.heat_sources[index]
        if source.via_line_id is None:
            lacking.append(f"{equipment.id}.heat_sources")
            continue
        row = _row(plant, source.via_line_id, OperatingParameter.TEMPERATURE)
        for limit in ("design_max", "normal"):
            value = getattr(row, limit) if row is not None else None
            if value is not None:
                fact = _operating_fact(source.via_line_id, OperatingParameter.TEMPERATURE, limit)
                found.append((float(value), source.medium, fact, limit))
                break
        else:
            lacking.append(
                _operating_fact(source.via_line_id, OperatingParameter.TEMPERATURE, "normal")
            )
    if not found:
        missing += lacking
        return None
    return max(found, key=lambda f: f[0])


def _blocked_in_summary(
    equipment: Equipment,
    value: float | None,
    detail: dict[str, Any],
    failed: Sequence[str],
    missing: Sequence[str],
) -> str:
    calc = Calculation.BLOCKED_IN_HEATING
    if value is None:
        text = f"Blocked-in heating check on {equipment.id}"
        if missing:
            text += f" skipped: missing {', '.join(_unique(missing))}"
    else:
        text = (
            f"Blocked-in heating check: if {equipment.id} is isolated while "
            f"{detail['heat_source']} stays on, vapour pressure reaches {calc_text(calc, value)} "
            f"(lowest of the listed chemicals: {detail['chemical']})"
        )
    if failed:
        text += f"; not confirmed: {', '.join(failed)}"
    return text


def _skipped(
    calc: Calculation, equipment: Equipment, missing: Sequence[str], flags: Sequence[str] = ()
) -> CalcResult:
    names = {
        Calculation.BLOCKED_IN_HEATING: "Blocked-in heating check",
        Calculation.OVERFLOW_TIME: "Overflow time",
        Calculation.HEAT_UP_RATE: "Heat-up time",
    }
    unit = {
        Calculation.BLOCKED_IN_HEATING: "x_design",
        Calculation.OVERFLOW_TIME: "min",
        Calculation.HEAT_UP_RATE: "min",
    }[calc]
    unique = _unique(missing)
    return CalcResult(
        calculation=calc,
        equipment_id=equipment.id,
        verdict=Verdict.NONE,
        value=None,
        unit=unit,
        summary=f"{names[calc]} on {equipment.id} skipped: missing {', '.join(unique)}",
        missing_fact_ids=unique,
        flags=tuple(flags),
    )


# --- overflow_time and heat_up_rate --------------------------------------------------------------


def _lowest(
    chemicals: Sequence[Chemical], field_name: str, missing: list[str], flags: list[str]
) -> tuple[float, str] | None:
    """The lowest value of a chemical property over the contents, named; a content chemical
    without it is flagged, and with none it is missing."""
    known = [
        (getattr(c, field_name), c.id) for c in chemicals if getattr(c, field_name) is not None
    ]
    lacking = [c.id for c in chemicals if getattr(c, field_name) is None]
    if not known:
        missing += [f"{c}.{field_name}" for c in lacking]
        return None
    if lacking:
        flags.append(f"no {field_name}: {', '.join(lacking)}; lowest of the listed chemicals only")
    value, chemical = min(known)
    return float(value), chemical


def overflow_time(equipment_id: str, plant: Plant, confirm_minutes: float) -> CalcResult:
    """minutes = (1 - normal/100) x volume x density / flow x 60, with the lowest content
    density and the largest inflow (flagged if several)."""
    equipment = _equipment(plant, equipment_id)
    calc = Calculation.OVERFLOW_TIME
    missing: list[str] = []
    flags: list[str] = []
    volume = equipment.volume_m3
    if volume is None:
        missing.append(f"{equipment.id}.volume_m3")
    row = _row(plant, equipment.id, OperatingParameter.LEVEL)
    normal = row.normal if row is not None else None
    if normal is None:
        missing.append(_operating_fact(equipment.id, OperatingParameter.LEVEL, "normal"))
    inflows = [line for line in plant.lines if line.to_id == equipment.id]
    flowing = [line for line in inflows if line.normal_flow_kg_h is not None]
    if not flowing:
        missing += [f"{line.id}.normal_flow_kg_h" for line in inflows]
        if not inflows:
            flags.append(f"no line flows into {equipment.id}")
    density = _lowest(_contents(plant, equipment), "density_kg_m3", missing, flags)
    if missing or not flowing or density is None or volume is None or normal is None:
        return _skipped(calc, equipment, missing, flags)
    rates = {line.id: float(line.normal_flow_kg_h) for line in flowing if line.normal_flow_kg_h}
    inflow_id = max(rates, key=lambda line_id: (rates[line_id], line_id))
    if len(flowing) > 1:
        flags.append(f"largest of {len(flowing)} inflows: {inflow_id}")
    flow = rates[inflow_id]
    rho, chemical = density
    minutes = (1 - normal / FULL_LEVEL_PCT) * volume * rho / flow * MINUTES_PER_HOUR
    verdict = Verdict.CONFIRMED if below(minutes, confirm_minutes) else Verdict.NONE
    return CalcResult(
        calculation=calc,
        equipment_id=equipment.id,
        verdict=verdict,
        value=minutes,
        unit="min",
        summary=(
            f"Overflow time: at {inflow_id}'s normal flow, {equipment.id} fills from "
            f"{normal:g} % to 100 % in {calc_text(calc, minutes)}"
        ),
        fact_ids=(
            f"{equipment.id}.volume_m3",
            _operating_fact(equipment.id, OperatingParameter.LEVEL, "normal"),
            f"{inflow_id}.normal_flow_kg_h",
            f"{chemical}.density_kg_m3",
        ),
        flags=_unique(flags),
        detail={"chemical": chemical, "inflow": inflow_id},
    )


def heat_up_rate(equipment_id: str, plant: Plant, confirm_minutes: float) -> CalcResult:
    """°C/min = duty_kW x 60 / (volume x lowest density x lowest heat capacity); minutes to
    the limit = (limit - normal) / rate. The limit is the temperature row's `design_max`, else
    `design_temp_c`."""
    equipment = _equipment(plant, equipment_id)
    calc = Calculation.HEAT_UP_RATE
    missing: list[str] = []
    flags: list[str] = []
    duty, volume = equipment.heat_duty_kw, equipment.volume_m3
    if duty is None:
        missing.append(f"{equipment.id}.heat_duty_kw")
    if volume is None:
        missing.append(f"{equipment.id}.volume_m3")
    contents = _contents(plant, equipment)
    density = _lowest(contents, "density_kg_m3", missing, flags)
    capacity = _lowest(contents, "heat_capacity_kj_kg_k", missing, flags)
    row = _row(plant, equipment.id, OperatingParameter.TEMPERATURE)
    normal = row.normal if row is not None else None
    if normal is None:
        missing.append(_operating_fact(equipment.id, OperatingParameter.TEMPERATURE, "normal"))
    limit: float | None
    if row is not None and row.design_max is not None:
        limit = row.design_max
        limit_fact = _operating_fact(equipment.id, OperatingParameter.TEMPERATURE, "design_max")
    elif equipment.design_temp_c is not None:
        limit, limit_fact = equipment.design_temp_c, f"{equipment.id}.design_temp_c"
    else:
        limit, limit_fact = None, ""
        missing.append(_operating_fact(equipment.id, OperatingParameter.TEMPERATURE, "design_max"))
        missing.append(f"{equipment.id}.design_temp_c")
    if (
        missing
        or duty is None
        or volume is None
        or density is None
        or capacity is None
        or normal is None
        or limit is None
    ):
        return _skipped(calc, equipment, missing, flags)
    rho, rho_chemical = density
    cp, cp_chemical = capacity
    rate = duty * SECONDS_PER_MINUTE / (volume * rho * cp)
    minutes = (limit - normal) / rate
    if not below(normal, limit):
        flags.append("already at or above the limit at normal")
    verdict = Verdict.CONFIRMED if below(minutes, confirm_minutes) else Verdict.NONE
    return CalcResult(
        calculation=calc,
        equipment_id=equipment.id,
        verdict=verdict,
        value=minutes,
        unit="min",
        summary=(
            f"Heat-up time: at its {duty:g} kW duty, {equipment.id} heats from "
            f"{normal:g} °C to its {limit:g} °C limit in {calc_text(calc, minutes)}"
        ),
        fact_ids=(
            f"{equipment.id}.heat_duty_kw",
            f"{equipment.id}.volume_m3",
            f"{rho_chemical}.density_kg_m3",
            f"{cp_chemical}.heat_capacity_kj_kg_k",
            _operating_fact(equipment.id, OperatingParameter.TEMPERATURE, "normal"),
            limit_fact,
        ),
        flags=_unique(flags),
        detail={
            "c_per_min": rate,
            "density_chemical": rho_chemical,
            "heat_capacity_chemical": cp_chemical,
        },
    )


# --- which calculations a line gets --------------------------------------------------------------


def applicable(
    links: Sequence[tuple[Finding, Section | None]], plant: Plant
) -> list[tuple[Calculation, str]]:
    """The (calculation, equipment ID) cards for a line: its findings (a chain's finding
    links), each with its section. One card per pair, whichever rule reached it, in the order
    of `Calculation` then equipment ID.

    - A matrix finding on `more:pressure`, `more:level` or `more:temperature` brings its
      calculation on each equipment item of its section.
    - Every scenario object (section objects and failing components) that is equipment with a
      design pressure and a heat source brings `blocked_in_heating` (Q1).
    """
    equipment = {e.id: e for e in plant.equipment}
    cards: set[tuple[Calculation, str]] = set()
    for found, section in links:
        objects = set(found.failing_component_ids) | set(section.object_ids if section else ())
        parsed = parse_question_id(found.question_id)
        if parsed.kind == QuestionKind.MATRIX and section is not None:
            _, guideword, parameter = parsed.parts
            calc = _BY_QUESTION.get((guideword, parameter))
            if calc is not None:
                cards |= {(calc, o) for o in section.object_ids if o in equipment}
        for object_id in objects:
            item = equipment.get(object_id)
            if item is not None and item.design_pressure_kpa is not None and item.heat_sources:
                cards.add((Calculation.BLOCKED_IN_HEATING, object_id))
    return sorted(cards, key=lambda card: (_ORDER.index(card[0]), card[1]))
