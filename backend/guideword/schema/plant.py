"""The plant file (PROJECT.md §9). Frozen at G1; change only through contract/...

Units are in field names; `_kpa` is always gauge and `_kpaa` absolute. `operating` limits
carry the unit fixed by `parameter`. References between objects are plain strings here;
`schema/validate.py` checks that each points to an existing object of the right kind.
`heat_sources`, `injection_points`, `discharge`, `vapor_pressure_points` and `operating`
rows are value objects with no ID of their own (D10).
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.schema.enums import (
    ControlSystem,
    DischargeKind,
    EquipmentType,
    FailPosition,
    HazopParameter,
    InstrumentKind,
    NoFlow,
    OperatingParameter,
    PhysicalForm,
    ProcedureKind,
    ReliefKind,
    UtilityKind,
    ValveKind,
    ValvePosition,
    WorkType,
)
from guideword.schema.ids import PLANT_ID_PATTERN

PlantObjectId = Annotated[str, StringConstraints(pattern=PLANT_ID_PATTERN)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(_Strict):
    id: PlantObjectId
    occupied: bool | None = None
    ignition_sources: bool | None = None
    indoor: bool | None = None


class Utility(_Strict):
    id: PlantObjectId
    kind: UtilityKind
    location_id: str | None = None


class HeatSource(_Strict):
    medium: str
    via_line_id: str | None = None
    isolating_valve_ids: list[str] = Field(default_factory=list)


class Equipment(_Strict):
    id: PlantObjectId
    type: EquipmentType
    location_id: str | None = None
    contents: list[str] = Field(default_factory=list)
    volume_m3: float | None = None
    design_pressure_kpa: float | None = None
    design_temp_c: float | None = None
    max_surface_temp_c: float | None = None
    heat_duty_kw: float | None = None
    dust_collection: bool | None = None
    heat_sources: list[HeatSource] = Field(default_factory=list)


class Instrument(_Strict):
    id: PlantObjectId
    kind: InstrumentKind
    measures: HazopParameter | None = None
    on_id: str | None = None
    system: ControlSystem | None = None


class LogicSolver(_Strict):
    id: PlantObjectId
    system: ControlSystem


class Valve(_Strict):
    id: PlantObjectId
    kind: ValveKind
    on_line_id: str | None = None
    normal_position: ValvePosition | None = None
    fail_position: FailPosition | None = None
    locked: bool | None = None


class InjectionPoint(_Strict):
    chemical_id: str
    at_component_id: str


class Line(_Strict):
    id: PlantObjectId
    from_id: str
    to_id: str
    components: list[str] = Field(default_factory=list)
    no_flow: NoFlow | None = None
    is_hose: bool | None = None
    contents: list[str] = Field(default_factory=list)
    size_mm: float | None = None
    length_m: float | None = None
    normal_flow_kg_h: float | None = None
    design_flow_kg_h: float | None = None
    injection_points: list[InjectionPoint] = Field(default_factory=list)


class Operating(_Strict):
    """One row per (target, parameter). Limits: pressure kPa gauge, temperature °C,
    level % of range, flow kg/h. Cited as `<target_id>.operating.<parameter>.<limit>`."""

    target_id: str
    parameter: OperatingParameter
    normal: float | None = None
    alarm_low: float | None = None
    alarm_high: float | None = None
    trip_low: float | None = None
    trip_high: float | None = None
    design_min: float | None = None
    design_max: float | None = None
    alarm_instrument_id: str | None = None
    trip_instrument_id: str | None = None


class ControlLoop(_Strict):
    id: PlantObjectId
    sensor_id: str
    controller_id: str
    final_element_id: str
    system: ControlSystem | None = None
    acts_on_id: str | None = None


class Safeguard(_Strict):
    id: PlantObjectId
    layer_type: str
    protects_id: str | None = None
    component_ids: list[str] = Field(default_factory=list)


class Discharge(_Strict):
    kind: DischargeKind | None = None
    location_id: str | None = None
    elevation_m: float | None = None


class ReliefDevice(_Strict):
    id: PlantObjectId
    protects_id: str
    kind: ReliefKind | None = None
    set_pressure_kpa: float | None = None
    capacity_kg_h: float | None = None
    inlet_valve_ids: list[str] = Field(default_factory=list)
    discharge: Discharge | None = None


class VaporPressurePoint(_Strict):
    temp_c: float
    pressure_kpaa: float


class Chemical(_Strict):
    id: PlantObjectId
    name: str
    epa_groups: list[int] = Field(default_factory=list)
    cameo_groups: list[int] = Field(default_factory=list)
    physical_form: PhysicalForm | None = None
    combustible_dust: bool | None = None
    boiling_point_c: float | None = None
    flash_point_c: float | None = None
    density_kg_m3: float | None = None
    heat_capacity_kj_kg_k: float | None = None
    vapor_pressure_points: list[VaporPressurePoint] = Field(default_factory=list)
    heat_of_reaction_kj_kg: float | None = None
    source: str | None = None


class ProcedureStep(_Strict):
    id: PlantObjectId
    text: str
    equipment_ids: list[str] = Field(default_factory=list)
    valve_ids: list[str] = Field(default_factory=list)


class Procedure(_Strict):
    id: PlantObjectId
    kind: ProcedureKind
    steps: list[ProcedureStep]


class PlannedWork(_Strict):
    id: PlantObjectId
    type: WorkType
    location_id: str | None = None
    equipment_ids: list[str] = Field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    lifts_per_year: float | None = None


class Plant(_Strict):
    plant_id: PlantObjectId
    schema_version: str
    locations: list[Location] = Field(default_factory=list)
    utilities: list[Utility] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)
    instruments: list[Instrument] = Field(default_factory=list)
    logic_solvers: list[LogicSolver] = Field(default_factory=list)
    valves: list[Valve] = Field(default_factory=list)
    lines: list[Line] = Field(default_factory=list)
    operating: list[Operating] = Field(default_factory=list)
    control_loops: list[ControlLoop] = Field(default_factory=list)
    safeguards: list[Safeguard] = Field(default_factory=list)
    relief_devices: list[ReliefDevice] = Field(default_factory=list)
    chemicals: list[Chemical] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
    planned_work: list[PlannedWork] = Field(default_factory=list)
    # fact ID or object ID -> source reference or "assumed"
    provenance: dict[str, str] = Field(default_factory=dict)


PLANT_MODELS: list[type[BaseModel]] = [
    Location,
    Utility,
    HeatSource,
    Equipment,
    Instrument,
    LogicSolver,
    Valve,
    InjectionPoint,
    Line,
    Operating,
    ControlLoop,
    Safeguard,
    Discharge,
    ReliefDevice,
    VaporPressurePoint,
    Chemical,
    ProcedureStep,
    Procedure,
    PlannedWork,
    Plant,
]
