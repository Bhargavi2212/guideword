"""Every enum in the schema (spec 0.5 table). Frozen at G1; change only through contract/..."""

from enum import StrEnum


class EquipmentType(StrEnum):
    TANK = "tank"
    VESSEL = "vessel"
    COLUMN = "column"
    REACTOR = "reactor"
    HEAT_EXCHANGER = "heat_exchanger"
    PUMP = "pump"
    COMPRESSOR = "compressor"
    DRYER = "dryer"
    MIXER = "mixer"
    SOLIDS_HANDLER = "solids_handler"
    OTHER = "other"


class SectionType(StrEnum):
    """Applicability key: the equipment types, plus pipe and procedure.

    Planned-work sections have no section type; they get only work: questions.
    """

    TANK = "tank"
    VESSEL = "vessel"
    COLUMN = "column"
    REACTOR = "reactor"
    HEAT_EXCHANGER = "heat_exchanger"
    PUMP = "pump"
    COMPRESSOR = "compressor"
    DRYER = "dryer"
    MIXER = "mixer"
    SOLIDS_HANDLER = "solids_handler"
    OTHER = "other"
    PIPE = "pipe"
    PROCEDURE = "procedure"


class SectionKind(StrEnum):
    EQUIPMENT = "equipment"
    LINE = "line"
    NO_FLOW_LINE = "no_flow_line"
    PROCEDURE = "procedure"
    PLANNED_WORK = "planned_work"


class InstrumentKind(StrEnum):
    SENSOR = "sensor"
    SWITCH = "switch"
    ANALYSER = "analyser"


class ControlSystem(StrEnum):
    BPCS = "bpcs"
    SIS = "sis"
    STANDALONE = "standalone"


class UtilityKind(StrEnum):
    STEAM = "steam"
    COOLING_WATER = "cooling_water"
    NITROGEN = "nitrogen"
    INSTRUMENT_AIR = "instrument_air"
    POWER = "power"
    OTHER = "other"


class ValveKind(StrEnum):
    CONTROL = "control"
    BLOCK = "block"
    CHECK = "check"
    MANUAL = "manual"
    RELIEF_ISOLATION = "relief_isolation"


class ValvePosition(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class FailPosition(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    LAST = "last"


class NoFlow(StrEnum):
    """`lines.no_flow` is a list of these; an empty list means the line flows normally."""

    NORMALLY_CLOSED = "normally_closed"
    DEAD_LEG = "dead_leg"
    STANDBY = "standby"
    STARTUP_ONLY = "startup_only"


class OperatingParameter(StrEnum):
    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    LEVEL = "level"
    FLOW = "flow"


class ReliefKind(StrEnum):
    PRV = "prv"
    RUPTURE_DISK = "rupture_disk"
    PRV_WITH_DISK = "prv_with_disk"
    VENT = "vent"


class DischargeKind(StrEnum):
    ATMOSPHERE = "atmosphere"
    FLARE = "flare"
    SCRUBBER = "scrubber"
    VESSEL = "vessel"
    HEADER = "header"


class PhysicalForm(StrEnum):
    GAS = "gas"
    LIQUID = "liquid"
    SOLID = "solid"
    DUST = "dust"


class ProcedureKind(StrEnum):
    START_UP = "start_up"
    SHUTDOWN = "shutdown"
    CHARGING = "charging"
    TRANSFER = "transfer"
    CLEANING = "cleaning"
    MAINTENANCE = "maintenance"
    EMERGENCY = "emergency"
    OTHER = "other"


class WorkType(StrEnum):
    HOT_WORK = "hot_work"
    CONFINED_SPACE = "confined_space"
    LINE_BREAK = "line_break"
    LIFTING = "lifting"
    OTHER = "other"


class Guideword(StrEnum):
    """IEC 61882 vocabulary. `before` and `after` are kept although no row uses them (D3)."""

    NO = "no"
    MORE = "more"
    LESS = "less"
    REVERSE = "reverse"
    OTHER_THAN = "other_than"
    AS_WELL_AS = "as_well_as"
    PART_OF = "part_of"
    EARLY = "early"
    LATE = "late"
    BEFORE = "before"
    AFTER = "after"
    SKIPPED = "skipped"
    WRONG = "wrong"
    OUT_OF_ORDER = "out_of_order"


class HazopParameter(StrEnum):
    FLOW = "flow"
    PRESSURE = "pressure"
    TEMPERATURE = "temperature"
    LEVEL = "level"
    COMPOSITION = "composition"
    REACTION = "reaction"
    MIXING = "mixing"
    PHASE = "phase"
    TIME = "time"


class QuestionKind(StrEnum):
    MATRIX = "matrix"
    CHEMICAL_PAIR = "chemical_pair"
    CHEMICAL_ENVIRONMENT = "chemical_environment"
    NO_FLOW_LINE = "no_flow_line"
    PROCEDURE_STEP = "procedure_step"
    PLANNED_WORK = "planned_work"
    DUST = "dust"
    RELIEF_DISCHARGE = "relief_discharge"
    ADDED_BY_AI = "added_by_ai"
    ENGINEER = "engineer"


class QuestionOrigin(StrEnum):
    MATRIX = "matrix"
    CROSS_LIST = "cross_list"
    ADDED_BY_AI = "added_by_ai"
    ENGINEER = "engineer"


class QuestionStatus(StrEnum):
    """`answered` and `not_credible` count as checked. Unsure is a confidence, not a status."""

    OPEN = "open"
    ANSWERED = "answered"
    NOT_CREDIBLE = "not_credible"
    FAILED = "failed"


class FailingComponentType(StrEnum):
    """The values used in reference/causes.csv."""

    CONTROL_LOOP = "control_loop"
    PUMP = "pump"
    COMPRESSOR = "compressor"
    CHECK_VALVE = "check_valve"
    REGULATOR = "regulator"
    RELIEF_DEVICE = "relief_device"
    EXCHANGER_TUBE = "exchanger_tube"
    INTERLOCK = "interlock"
    OPERATOR = "operator"
    HOSE = "hose"
    PIPE = "pipe"
    TANK = "tank"
    EXTERNAL = "external"
    SOLIDS_HANDLER = "solids_handler"
    UTILITY_COOLING = "utility_cooling"
    UTILITY_POWER = "utility_power"


class Confidence(StrEnum):
    SURE = "sure"
    UNSURE = "unsure"


class Adequacy(StrEnum):
    ADEQUATE = "adequate"
    INADEQUATE = "inadequate"
    UNKNOWN = "unknown"


class SeverityClass(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class LikelihoodClass(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class RiskRating(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class PlantStatus(StrEnum):
    UPLOADED = "uploaded"
    SECTIONS_PROPOSED = "sections_proposed"
    SECTIONS_CONFIRMED = "sections_confirmed"


class RunStatus(StrEnum):
    """`draft` = run created, setup not yet done (D9)."""

    DRAFT = "draft"
    RUNNING = "running"
    FINISHED = "finished"
    STOPPED_CAP = "stopped_cap"
    STOPPED_BUDGET = "stopped_budget"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunLabelKind(StrEnum):
    LIVE = "live"
    RECORDED = "recorded"
    MOCK = "mock"


class OverrideAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"
    CHANGE_CREDIT = "change_credit"
    CHANGE_SEVERITY = "change_severity"
    ANSWER = "answer"


class BudgetUse(StrEnum):
    DEVELOPMENT = "development"
    TEST_5 = "test_5"
    BENCHMARK = "benchmark"
    VIDEO = "video"
    DEMO_RECORDING = "demo_recording"
    JUDGING = "judging"
    BUFFER = "buffer"


class EvidenceKind(StrEnum):
    CALCULATION = "calculation"
    PRECEDENT = "precedent"
    SIMULATION = "simulation"


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    NONE = "none"


class Agent(StrEnum):
    ORCHESTRATOR = "orchestrator"
    PROCESS = "process"
    CHEMISTRY = "chemistry"
    PIPING = "piping"
    PROCEDURES = "procedures"
    MAINTENANCE = "maintenance"
    DUST = "dust"
    CONNECTOR = "connector"


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    AGENT_DECISION = "agent_decision"
    DISPATCH = "dispatch"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    FINDING_ADDED = "finding_added"
    CHAIN_ADDED = "chain_added"
    LOPA_DONE = "lopa_done"
    EVIDENCE_ADDED = "evidence_added"
    COVERAGE_UPDATED = "coverage_updated"
    CAP_HIT = "cap_hit"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"


class Environment(StrEnum):
    LAPTOP = "laptop"
    HOSTED = "hosted"


class Tier(StrEnum):
    """Model tiers; config/routing.yaml maps jobs to these, the live model list to IDs."""

    ULTRA = "ultra"
    SUPER = "super"
    LIGHTNING = "lightning"
    NANO = "nano"


class AgentTool(StrEnum):
    """The orchestrator tools in PROJECT.md §5, plus `answer` for a specialist's answer step."""

    CHECK_COVERAGE = "check_coverage"
    DISPATCH_SPECIALIST = "dispatch_specialist"
    WEB_RESEARCH = "web_research"
    SEARCH_PRECEDENT = "search_precedent"
    REACTIVITY_LOOKUP = "reactivity_lookup"
    PHYSICS_CALC = "physics_calc"
    PROPOSE_CHAINS = "propose_chains"
    RUN_LOPA = "run_lopa"
    RUN_SIMULATION = "run_simulation"
    FINISH = "finish"
    ANSWER = "answer"


# The seven `operating` limit fields; their unit is fixed by `operating.parameter`.
OPERATING_LIMITS = (
    "normal",
    "alarm_low",
    "alarm_high",
    "trip_low",
    "trip_high",
    "design_min",
    "design_max",
)
