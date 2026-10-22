"""Content-built IDs (PROJECT.md §11 "IDs and enums").

Every ID is a pure function of its inputs: never random, never a clock, never a hidden
counter. The only counter is the visible run attempt number. `h(x)` is the first 16 hex
characters of SHA-256 over the canonical JSON of `x` (sorted keys, no whitespace, UTF-8,
Unicode NFC). Text that is hashed into an ID always goes through `normalise_text()` (D4).
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from guideword.schema.enums import (
    OPERATING_LIMITS,
    Calculation,
    EvidenceKind,
    Guideword,
    HazopParameter,
    OperatingParameter,
    OverrideAction,
    QuestionKind,
    RunStatus,
)

# Plant object IDs; `.`, `:`, `~` and `+` are reserved for derived IDs.
PLANT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
_PLANT_ID = re.compile(PLANT_ID_PATTERN)
_FIELD = re.compile(r"^[a-z][a-z0-9_]*$")

ENVIRONMENT_KINDS = ("water", "air", "heat")

# Run inputs hashed into the run ID (PROJECT.md §11). The run's spend cap is not one of
# them, so a run stopped at its cap can be resumed with a higher cap.
RUN_INPUT_KEYS = frozenset(
    {
        "plant_id",
        "section_snapshot",
        "reference_versions",
        "routing_config",
        "caps",
        "prompt_versions",
        "mode",
    }
)
# A new attempt starts only after one of these; any other status is resumed.
ENDED_RUN_STATUSES = frozenset({RunStatus.FINISHED, RunStatus.CANCELLED, RunStatus.FAILED})

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-")
_SPACES = dict.fromkeys(map(ord, "   "), " ")


# --- hashing ------------------------------------------------------------------------


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {str(_canonical(k)): _canonical(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    return value


def canonical_json(value: object) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def h(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:16]


def normalise_text(text: str) -> str:
    """Normalise text before hashing it into an ID (D4).

    NFC; Unicode dashes to '-'; non-breaking spaces to ' '; collapse whitespace; trim; casefold.
    """
    text = unicodedata.normalize("NFC", text).translate(_DASHES).translate(_SPACES)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return unicodedata.normalize("NFC", text)


# --- part checks --------------------------------------------------------------------


def _object_id(value: str) -> str:
    if not _PLANT_ID.fullmatch(value):
        raise ValueError(f"not a plant object ID: {value!r}")
    return value


def _part(value: str, *, forbidden: str = ":") -> str:
    if not value or any(c in value for c in forbidden):
        raise ValueError(f"ID part is empty or contains one of {forbidden!r}: {value!r}")
    return value


# --- plant, facts, sections -----------------------------------------------------------


def plant_record_id(plant_id: str, plant_file: Mapping[str, object]) -> str:
    return f"plant:{_object_id(plant_id)}:{h(plant_file)}"


@dataclass(frozen=True)
class FactRef:
    object_id: str
    field: str
    parameter: OperatingParameter | None = None
    limit: str | None = None


def fact_id(object_id: str, field: str) -> str:
    """`<object id>.<field>`; a value object is cited by its parent's field (D10)."""
    if not _FIELD.fullmatch(field) or field == "operating":
        raise ValueError(f"not a top-level field name: {field!r}")
    return f"{_object_id(object_id)}.{field}"


def operating_fact_id(target_id: str, parameter: OperatingParameter | str, limit: str) -> str:
    """`<target_id>.operating.<parameter>.<limit field>`: one setpoint (D10)."""
    if limit not in OPERATING_LIMITS:
        raise ValueError(f"not an operating limit field: {limit!r}")
    return f"{_object_id(target_id)}.operating.{OperatingParameter(parameter)}.{limit}"


def parse_fact_id(value: str) -> FactRef:
    parts = value.split(".")
    if len(parts) == 2:
        object_id, field = parts
        fact_id(object_id, field)  # validates
        return FactRef(object_id, field)
    if len(parts) == 4 and parts[1] == "operating":
        object_id, _, parameter, limit = parts
        operating_fact_id(object_id, parameter, limit)  # validates
        return FactRef(object_id, "operating", OperatingParameter(parameter), limit)
    raise ValueError(f"not a fact ID: {value!r}")


def section_id(object_id: str) -> str:
    return f"S-{_object_id(object_id)}"


def split_section_id(object_id: str, first_component_id: str) -> str:
    return f"S-{_object_id(object_id)}~{_object_id(first_component_id)}"


def engineer_section_id(object_ids: Iterable[str]) -> str:
    covered = sorted(_object_id(i) for i in object_ids)
    if not covered:
        raise ValueError("an engineer-added section covers at least one plant object")
    return f"S~eng~{h(covered)}"


def merged_section_id(section_ids: Iterable[str]) -> str:
    """A merge keeps the lowest of the merged IDs."""
    merged = [_part(s) for s in section_ids]
    if len(merged) < 2:
        raise ValueError("a merge needs at least two sections")
    return min(merged)


# --- questions ------------------------------------------------------------------------

_QUESTION_PREFIX: dict[QuestionKind, tuple[str, int]] = {
    QuestionKind.MATRIX: ("m", 3),
    QuestionKind.CHEMICAL_PAIR: ("pair", 2),
    QuestionKind.CHEMICAL_ENVIRONMENT: ("env", 2),
    QuestionKind.NO_FLOW_LINE: ("nf", 1),
    QuestionKind.PROCEDURE_STEP: ("proc", 2),
    QuestionKind.PLANNED_WORK: ("work", 2),
    QuestionKind.DUST: ("dust", 1),
    QuestionKind.RELIEF_DISCHARGE: ("relief", 1),
    QuestionKind.ADDED_BY_AI: ("ai", 2),
    QuestionKind.ENGINEER: ("eng", 2),
}
_KIND_BY_PREFIX = {prefix: kind for kind, (prefix, _) in _QUESTION_PREFIX.items()}


@dataclass(frozen=True)
class ParsedQuestionId:
    kind: QuestionKind
    parts: tuple[str, ...]


def build_question_id(parsed: ParsedQuestionId) -> str:
    prefix, count = _QUESTION_PREFIX[parsed.kind]
    if len(parsed.parts) != count:
        raise ValueError(f"{parsed.kind} question IDs have {count} parts")
    return ":".join([prefix, *(_part(p) for p in parsed.parts)])


def parse_question_id(value: str) -> ParsedQuestionId:
    prefix, _, rest = value.partition(":")
    kind = _KIND_BY_PREFIX.get(prefix)
    if kind is None or not rest:
        raise ValueError(f"not a question ID: {value!r}")
    parsed = ParsedQuestionId(kind, tuple(rest.split(":")))
    build_question_id(parsed)  # validates the part count and parts
    return parsed


def matrix_question_id(
    section: str, guideword: Guideword | str, parameter: HazopParameter | str
) -> str:
    return build_question_id(
        ParsedQuestionId(
            QuestionKind.MATRIX, (section, Guideword(guideword), HazopParameter(parameter))
        )
    )


def pair_question_id(chemical_a: str, chemical_b: str) -> str:
    a, b = sorted((_object_id(chemical_a), _object_id(chemical_b)))
    return build_question_id(ParsedQuestionId(QuestionKind.CHEMICAL_PAIR, (a, b)))


def environment_question_id(chemical: str, environment: str) -> str:
    if environment not in ENVIRONMENT_KINDS:
        raise ValueError(f"environment must be one of {ENVIRONMENT_KINDS}: {environment!r}")
    parts = (_object_id(chemical), environment)
    return build_question_id(ParsedQuestionId(QuestionKind.CHEMICAL_ENVIRONMENT, parts))


def no_flow_question_id(line: str) -> str:
    return build_question_id(ParsedQuestionId(QuestionKind.NO_FLOW_LINE, (_object_id(line),)))


def procedure_question_id(step: str, guideword: Guideword | str) -> str:
    parts = (_object_id(step), Guideword(guideword))
    return build_question_id(ParsedQuestionId(QuestionKind.PROCEDURE_STEP, parts))


def work_question_id(job: str, target: str) -> str:
    parts = (_object_id(job), _object_id(target))
    return build_question_id(ParsedQuestionId(QuestionKind.PLANNED_WORK, parts))


def dust_question_id(equipment: str) -> str:
    return build_question_id(ParsedQuestionId(QuestionKind.DUST, (_object_id(equipment),)))


def relief_question_id(device: str) -> str:
    parts = (_object_id(device),)
    return build_question_id(ParsedQuestionId(QuestionKind.RELIEF_DISCHARGE, parts))


def added_by_ai_question_id(section: str, text: str) -> str:
    parts = (section, h(normalise_text(text)))
    return build_question_id(ParsedQuestionId(QuestionKind.ADDED_BY_AI, parts))


def engineer_question_id(section: str, text: str) -> str:
    parts = (section, h(normalise_text(text)))
    return build_question_id(ParsedQuestionId(QuestionKind.ENGINEER, parts))


# --- runs -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Attempt:
    """An earlier attempt with the same run inputs."""

    status: RunStatus
    spend_cap_usd: float


class CapReachedError(ValueError):
    """A stopped_cap run was asked to continue without a higher cap. The API returns 409."""

    def __init__(self) -> None:
        super().__init__("cap reached; raise spend_cap_usd to continue")


def run_id(
    inputs: Mapping[str, object], previous_attempts: Sequence[Attempt], *, spend_cap_usd: float
) -> str:
    """`run:<h(inputs)>`, or `run:<h(inputs)>:<n>` for attempt n >= 2.

    `previous_attempts` are the earlier attempts with these inputs, oldest first. After a
    finished, cancelled or failed attempt, the next attempt number is used. Any other
    latest attempt is resumed, except a stopped_cap one, which resumes only when
    `spend_cap_usd` is higher than its cap; otherwise CapReachedError.
    """
    if set(inputs) != RUN_INPUT_KEYS:
        raise ValueError(f"run inputs must be exactly {sorted(RUN_INPUT_KEYS)}")
    base = f"run:{h(dict(inputs))}"
    count = len(previous_attempts)
    if count == 0:
        return base
    latest = previous_attempts[-1]
    if latest.status in ENDED_RUN_STATUSES:
        return f"{base}:{count + 1}"
    if latest.status == RunStatus.STOPPED_CAP and spend_cap_usd <= latest.spend_cap_usd:
        raise CapReachedError()
    return base if count == 1 else f"{base}:{count}"


# --- findings, chains, LOPA, recommendations, evidence ------------------------------


def finding_id(
    question_id: str,
    tier: str,
    failing_component_ids: Iterable[str],
    *,
    cause_id: str | None = None,
    cause_text: str | None = None,
) -> str:
    """`f:<question>:<tier>:<cause>:<h(sorted failing component IDs)>`.

    An outside-library cause uses h(normalised cause text) in place of the cause ID.
    """
    if (cause_id is None) == (cause_text is None):
        raise ValueError("give exactly one of cause_id or cause_text")
    components = sorted(failing_component_ids)
    if not components:
        raise ValueError("failing_component_ids is never empty")
    cause = _part(cause_id) if cause_id is not None else h(normalise_text(cause_text or ""))
    parse_question_id(question_id)
    return f"f:{question_id}:{_part(tier)}:{cause}:{h(components)}"


def chain_id(links: Iterable[str]) -> str:
    """`ch:<link IDs sorted and joined with +>`; the same set of links is the same chain."""
    unique = sorted({_part(link, forbidden="+") for link in links})
    if len(unique) < 2:
        raise ValueError("a chain needs at least two distinct links")
    return "ch:" + "+".join(unique)


def hypothesis_id(rank: int, mechanism: str, component_ids: Iterable[str]) -> str:
    """`h:<rank>:<h(normalised mechanism, sorted component IDs)>` (R50); stored per run, so the
    run is not part of the ID."""
    if rank < 1:
        raise ValueError("a hypothesis rank starts at 1")
    components = sorted(component_ids)
    if not components:
        raise ValueError("a hypothesis names at least one component")
    return f"h:{rank}:{h([normalise_text(mechanism), components])}"


def lopa_id(target_id: str) -> str:
    return f"lopa:{_part(target_id, forbidden='')}"


def recommendation_id(target_id: str, action_text: str) -> str:
    return f"rec:{_part(target_id, forbidden='')}:{h(normalise_text(action_text))}"


def evidence_id(target_id: str, kind: EvidenceKind | str, source_key: str) -> str:
    return f"ev:{_part(target_id, forbidden='')}:{EvidenceKind(kind)}:{_part(source_key)}"


def calculation_evidence_id(
    target_id: str, calculation: Calculation | str, equipment_id: str
) -> str:
    """`ev:<target>:calculation:<calculation>-<equipment id>` (Phase 4 plan G2): one line
    can hold the same calculation on two equipment items."""
    key = f"{Calculation(calculation)}-{_object_id(equipment_id)}"
    return evidence_id(target_id, EvidenceKind.CALCULATION, key)


NO_PRECEDENT = "none"


def precedent_evidence_id(
    target_id: str, *, precedent_id: str | None = None, url: str | None = None
) -> str:
    """Keyed by the precedent index ID, or h(url) for a web result."""
    if (precedent_id is None) == (url is None):
        raise ValueError("give exactly one of precedent_id or url")
    if precedent_id == NO_PRECEDENT:
        raise ValueError(f"{NO_PRECEDENT!r} is the no-precedent key, not an index ID")
    key = precedent_id if precedent_id is not None else h(url)
    return evidence_id(target_id, EvidenceKind.PRECEDENT, key)


def no_precedent_evidence_id(target_id: str) -> str:
    """The one record of a line with no accepted incident (Phase 4 plan Q2)."""
    return evidence_id(target_id, EvidenceKind.PRECEDENT, NO_PRECEDENT)


# --- model calls, tool calls, agent steps, overrides ------------------------------------


def cache_key(model_id: str, prompt_version: str, exact_input: object) -> str:
    return h([model_id, prompt_version, exact_input])


def model_call_id(model_id: str, prompt_version: str, exact_input: object) -> str:
    return f"mc:{cache_key(model_id, prompt_version, exact_input)}"


def agent_step_id(previous_id: str, agent: str, tool: str, arguments: object) -> str:
    """`previous_id` is the previous step ID, or the run ID for the first step."""
    return f"step:{h([previous_id, agent, tool, arguments])}"


def tool_call_id(step_id: str, tool: str, arguments: object) -> str:
    return f"tc:{_part(step_id, forbidden='')}:{_part(tool)}:{h(arguments)}"


def override_id(
    target_id: str,
    action: OverrideAction | str,
    new_value: object,
    replaces: str | None = None,
) -> str:
    """`ov:<target>:<h(action, new value, ID of the override it replaces or "none")>`."""
    payload = [OverrideAction(action), new_value, replaces or "none"]
    return f"ov:{_part(target_id, forbidden='')}:{h(payload)}"
