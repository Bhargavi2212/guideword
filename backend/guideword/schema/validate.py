"""Plant validation (spec 0.5): errors and warnings, each naming the offending ID.

Errors stop a plant from being used; warnings are missing facts shown in the UI as gaps
and never filled in by code. The validator takes the raw plant JSON so that unknown fields
(error 7) and bad IDs (error 8) can name the object they belong to.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import OPERATING_LIMITS, EquipmentType, ValveKind
from guideword.schema.plant import Plant

LOCATION = "location"
UTILITY = "utility"
EQUIPMENT = "equipment"
INSTRUMENT = "instrument"
LOGIC_SOLVER = "logic solver"
VALVE = "valve"
LINE = "line"
CHEMICAL = "chemical"

NEEDS_DESIGN_LIMITS = {
    EquipmentType.TANK,
    EquipmentType.VESSEL,
    EquipmentType.COLUMN,
    EquipmentType.REACTOR,
    EquipmentType.HEAT_EXCHANGER,
    EquipmentType.DRYER,
    EquipmentType.MIXER,
}
# design_min <= trip_low <= alarm_low <= normal <= alarm_high <= trip_high <= design_max
LIMIT_ORDER = (
    "design_min",
    "trip_low",
    "alarm_low",
    "normal",
    "alarm_high",
    "trip_high",
    "design_max",
)


@dataclass(frozen=True)
class Issue:
    code: str
    object_id: str | None
    message: str


@dataclass(frozen=True)
class ValidationReport:
    errors: list[Issue]
    warnings: list[Issue]
    plant: Plant | None

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_plant(data: Mapping[str, Any], ref: ReferenceSet) -> ValidationReport:
    try:
        plant = Plant.model_validate(data)
    except ValidationError as error:
        return ValidationReport(_schema_errors(error, data), [], None)
    return ValidationReport(_errors(plant, ref), _warnings(plant, ref), plant)


# --- schema errors (rules 7 and 8, and other malformed values) -------------------------------


def _nearest_object_id(data: Any, loc: Sequence[int | str]) -> str | None:
    found: str | None = data.get("plant_id") if isinstance(data, Mapping) else None
    node = data
    for part in loc:
        try:
            node = node[part]
        except (KeyError, IndexError, TypeError):
            break
        if isinstance(node, Mapping):
            if isinstance(node.get("id"), str):
                found = node["id"]
            elif isinstance(node.get("target_id"), str):
                found = node["target_id"]
    return found


def _schema_errors(error: ValidationError, data: Mapping[str, Any]) -> list[Issue]:
    issues = []
    for item in error.errors():
        loc = item["loc"]
        where = ".".join(str(p) for p in loc)
        if item["type"] == "extra_forbidden":
            owner = _nearest_object_id(data, loc[:-1])
            issues.append(Issue("unknown_field", owner, f"{owner}: unknown field '{loc[-1]}'"))
        elif item["type"] == "string_pattern_mismatch" and loc and loc[-1] in ("id", "plant_id"):
            bad = str(item["input"])
            issues.append(
                Issue("bad_id_pattern", bad, f"{bad}: IDs must match {ids.PLANT_ID_PATTERN}")
            )
        else:
            owner = _nearest_object_id(data, loc)
            issues.append(Issue("invalid_value", owner, f"{owner}: {where}: {item['msg']}"))
    return issues


# --- reference and consistency errors (rules 1-6 and 9) -----------------------------------------


def _plant_objects(plant: Plant) -> list[tuple[str, BaseModel]]:
    """Every plant object with an ID, with its kind."""
    objects: list[tuple[str, BaseModel]] = []
    objects += [(LOCATION, o) for o in plant.locations]
    objects += [(UTILITY, o) for o in plant.utilities]
    objects += [(EQUIPMENT, o) for o in plant.equipment]
    objects += [(INSTRUMENT, o) for o in plant.instruments]
    objects += [(LOGIC_SOLVER, o) for o in plant.logic_solvers]
    objects += [(VALVE, o) for o in plant.valves]
    objects += [(LINE, o) for o in plant.lines]
    objects += [("control loop", o) for o in plant.control_loops]
    objects += [("safeguard", o) for o in plant.safeguards]
    objects += [("relief device", o) for o in plant.relief_devices]
    objects += [(CHEMICAL, o) for o in plant.chemicals]
    objects += [("procedure", o) for o in plant.procedures]
    objects += [("procedure step", s) for p in plant.procedures for s in p.steps]
    objects += [("planned work", o) for o in plant.planned_work]
    return objects


class _Checker:
    def __init__(self, plant: Plant) -> None:
        self.objects = _plant_objects(plant)
        self.kinds: dict[str, set[str]] = {}
        self.by_id: dict[str, BaseModel] = {}
        for kind, obj in self.objects:
            object_id = getattr(obj, "id")  # noqa: B009 - every plant object has an id
            self.kinds.setdefault(object_id, set()).add(kind)
            self.by_id.setdefault(object_id, obj)
        self.errors: list[Issue] = []

    def add(self, code: str, object_id: str | None, message: str) -> None:
        self.errors.append(Issue(code, object_id, message))

    def refs(self, owner: str, field: str, values: Iterable[str | None], *kinds: str) -> None:
        for value in values:
            if value is None:
                continue
            if not self.kinds.get(value, set()) & set(kinds):
                wanted = " or ".join(kinds)
                self.add("bad_reference", owner, f"{owner}.{field}: '{value}' is not a {wanted}")

    def ref(self, owner: str, field: str, value: str | None, *kinds: str) -> None:
        self.refs(owner, field, [value], *kinds)


def _errors(plant: Plant, ref: ReferenceSet) -> list[Issue]:
    c = _Checker(plant)

    # 1. duplicate IDs anywhere in the file
    counts = Counter(getattr(obj, "id") for _, obj in c.objects)  # noqa: B009
    for object_id, n in counts.items():
        if n > 1:
            c.add("duplicate_id", object_id, f"{object_id}: ID used {n} times")

    # 2. references to missing IDs or to the wrong kind of object
    for loc in plant.utilities:
        c.ref(loc.id, "location_id", loc.location_id, LOCATION)
    for eq in plant.equipment:
        c.ref(eq.id, "location_id", eq.location_id, LOCATION)
        c.refs(eq.id, "contents", eq.contents, CHEMICAL)
        for source in eq.heat_sources:
            c.ref(eq.id, "heat_sources.via_line_id", source.via_line_id, LINE)
            c.refs(eq.id, "heat_sources.isolating_valve_ids", source.isolating_valve_ids, VALVE)
        c.refs(eq.id, "injection_points", [p.chemical_id for p in eq.injection_points], CHEMICAL)
    for inst in plant.instruments:
        c.ref(inst.id, "on_id", inst.on_id, EQUIPMENT, LINE)
    for valve in plant.valves:
        c.ref(valve.id, "on_line_id", valve.on_line_id, LINE)
    for line in plant.lines:
        c.ref(line.id, "from_id", line.from_id, EQUIPMENT, UTILITY, LOCATION)
        c.ref(line.id, "to_id", line.to_id, EQUIPMENT, UTILITY, LOCATION)
        c.refs(line.id, "components", line.components, VALVE, EQUIPMENT)
        c.refs(line.id, "contents", line.contents, CHEMICAL)
        for point in line.injection_points:
            c.ref(line.id, "injection_points.chemical_id", point.chemical_id, CHEMICAL)
            if point.at_component_id not in line.components:
                c.add(
                    "bad_reference",
                    line.id,
                    f"{line.id}.injection_points: '{point.at_component_id}' is not on the line",
                )
    for row in plant.operating:
        c.ref(row.target_id, "operating.target_id", row.target_id, EQUIPMENT, LINE)
        c.ref(row.target_id, "operating.alarm_instrument_id", row.alarm_instrument_id, INSTRUMENT)
        c.ref(row.target_id, "operating.trip_instrument_id", row.trip_instrument_id, INSTRUMENT)
    for loop in plant.control_loops:
        c.ref(loop.id, "sensor_id", loop.sensor_id, INSTRUMENT)
        c.ref(loop.id, "controller_id", loop.controller_id, LOGIC_SOLVER)
        c.ref(loop.id, "final_element_id", loop.final_element_id, VALVE, EQUIPMENT)
        c.ref(loop.id, "acts_on_id", loop.acts_on_id, EQUIPMENT, LINE)
    for guard in plant.safeguards:
        c.ref(guard.id, "protects_id", guard.protects_id, EQUIPMENT, LOCATION)
        c.refs(
            guard.id,
            "component_ids",
            guard.component_ids,
            INSTRUMENT,
            LOGIC_SOLVER,
            VALVE,
            EQUIPMENT,
        )
    for device in plant.relief_devices:
        c.ref(device.id, "protects_id", device.protects_id, EQUIPMENT)
        c.refs(device.id, "inlet_valve_ids", device.inlet_valve_ids, VALVE)
        if device.discharge is not None:
            c.ref(device.id, "discharge.location_id", device.discharge.location_id, LOCATION)
    for procedure in plant.procedures:
        for step in procedure.steps:
            c.refs(step.id, "equipment_ids", step.equipment_ids, EQUIPMENT)
            c.refs(step.id, "valve_ids", step.valve_ids, VALVE)
    for work in plant.planned_work:
        c.ref(work.id, "location_id", work.location_id, LOCATION)
        c.refs(work.id, "equipment_ids", work.equipment_ids, EQUIPMENT)
        c.refs(work.id, "line_ids", work.line_ids, LINE)

    # 3. values that must exist in the reference tables
    layers = {row.id for row in ref.protection_layers}
    epa = {row.epa_group_id for row in ref.reactive_groups}
    cameo = {row.cameo_group_id for row in ref.cameo_groups}
    for guard in plant.safeguards:
        if guard.layer_type is not None and guard.layer_type not in layers:
            c.add(
                "unknown_reference_value",
                guard.id,
                f"{guard.id}.layer_type: '{guard.layer_type}' is not in protection_layers.csv",
            )
    for chemical in plant.chemicals:
        for group in chemical.epa_groups:
            if group not in epa:
                c.add(
                    "unknown_reference_value",
                    chemical.id,
                    f"{chemical.id}.epa_groups: {group} is not in reactive_groups.csv",
                )
        for group in chemical.cameo_groups:
            if group not in cameo:
                c.add(
                    "unknown_reference_value",
                    chemical.id,
                    f"{chemical.id}.cameo_groups: {group} is not in cameo_groups.csv",
                )

    # 4. one operating row per target and parameter
    rows = Counter((row.target_id, row.parameter) for row in plant.operating)
    for (target, parameter), n in rows.items():
        if n > 1:
            c.add(
                "duplicate_operating_row",
                target,
                f"{target}: {n} operating rows for {parameter}",
            )

    # 5. planned work that ends before it starts
    for work in plant.planned_work:
        if work.start is not None and work.end is not None:
            try:
                backwards = work.end < work.start
            except TypeError:
                c.add("invalid_value", work.id, f"{work.id}: start and end mix time zones")
                continue
            if backwards:
                c.add("work_ends_before_start", work.id, f"{work.id}: end is before start")

    # 6. provenance keys must name an existing object or fact
    for key in plant.provenance:
        problem = _provenance_problem(key, c, plant)
        if problem is not None:
            owner, message = problem
            c.add("bad_provenance_key", owner, message)

    # 9. a valve's line must list the valve among its components
    lines = {each.id: each for each in plant.lines}
    for valve in plant.valves:
        on_line = lines.get(valve.on_line_id or "")
        if on_line is not None and valve.id not in on_line.components:
            c.add(
                "valve_not_on_line",
                valve.id,
                f"{valve.id}: on_line_id is {on_line.id}, "
                f"but {on_line.id}.components does not list it",
            )

    return c.errors


def _provenance_problem(key: str, c: _Checker, plant: Plant) -> tuple[str, str] | None:
    if key in c.by_id:
        return None
    owner = key.split(".", 1)[0]
    try:
        fact = ids.parse_fact_id(key)
    except ValueError:
        return owner, f"{owner}: provenance key '{key}' is not an object ID or a fact ID"
    obj = c.by_id.get(fact.object_id)
    if obj is None:
        return owner, f"{owner}: provenance key '{key}' names no plant object"
    if fact.field == "operating":
        for row in plant.operating:
            if row.target_id == fact.object_id and row.parameter == fact.parameter:
                if fact.limit in OPERATING_LIMITS and getattr(row, fact.limit or "") is not None:
                    return None
                return owner, f"{owner}: provenance key '{key}' names an unset operating limit"
        return owner, f"{owner}: provenance key '{key}' names no operating row"
    if fact.field not in type(obj).model_fields or fact.field == "id":
        return owner, f"{owner}: provenance key '{key}' names no field of {fact.object_id}"
    return None


# --- warnings (missing facts, never filled in by code) ------------------------------------------


def _warnings(plant: Plant, ref: ReferenceSet) -> list[Issue]:
    warnings: list[Issue] = []

    def warn(code: str, object_id: str, message: str) -> None:
        warnings.append(Issue(code, object_id, message))

    for eq in plant.equipment:
        if eq.type in NEEDS_DESIGN_LIMITS and (
            eq.design_pressure_kpa is None or eq.design_temp_c is None
        ):
            warn("missing_design_limits", eq.id, f"{eq.id}: no design pressure or temperature")
    for valve in plant.valves:
        if valve.kind in (ValveKind.CONTROL, ValveKind.BLOCK) and valve.fail_position is None:
            warn("missing_fail_position", valve.id, f"{valve.id}: no fail position")
    for chemical in plant.chemicals:
        if not chemical.epa_groups and not chemical.cameo_groups:
            warn("chemical_without_groups", chemical.id, f"{chemical.id}: no EPA or CAMEO groups")
    for device in plant.relief_devices:
        if device.discharge is None:
            warn("relief_without_discharge", device.id, f"{device.id}: no discharge")
    for procedure in plant.procedures:
        if not procedure.steps:
            warn("procedure_without_steps", procedure.id, f"{procedure.id}: no steps")
    categories = {row.id: row.category for row in ref.protection_layers}
    for guard in plant.safeguards:
        if (
            guard.layer_type is not None
            and categories.get(guard.layer_type) == "active"
            and not guard.component_ids
        ):
            warn(
                "safeguard_components_missing",
                guard.id,
                f"{guard.id}: active layer with no component_ids; independence cannot be checked",
            )
    for line in plant.lines:
        if not line.contents:
            warn("line_without_contents", line.id, f"{line.id}: no contents")
    for row in plant.operating:
        present = [
            (name, getattr(row, name)) for name in LIMIT_ORDER if getattr(row, name) is not None
        ]
        for (low_name, low), (high_name, high) in zip(present, present[1:], strict=False):
            if low > high:
                warn(
                    "operating_limits_out_of_order",
                    row.target_id,
                    f"{row.target_id} {row.parameter}: "
                    f"{low_name} {low} is above {high_name} {high}",
                )
                break
    return warnings
