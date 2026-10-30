"""The whole-plant pass's answer and its checks (spec 2b.1; R50; plan Q4–Q7, G11).

The answer as a whole must hold together: at most `plant_screen_max_hypotheses` hypotheses,
ranked 1 to n in order, no two the same hypothesis. Each hypothesis must name plant objects
that can fail as its type (R46, over the whole plant), plant chemicals, and either a library
cause of that same type or an outside-library cause with its text. A whole-answer problem
fails the answer; a hypothesis's own problem drops just that hypothesis.

Phase 9 (spec 9.1): from `plant_screen/v4` each hypothesis is a **card**: its initiating event,
enabling condition, propagation path, its consequence's magnitude where the plant gives one,
its operating mode and mechanism class, and the plant object or fact IDs it rests on. The card
fields are required when the run's prompt version asks for them (`requires_card`); a cited fact
ID that names nothing in the plant drops the hypothesis, on every version.
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import (
    OPERATING_LIMITS,
    FailingComponentType,
    MechanismClass,
    OperatingMode,
)
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY
from guideword.specialists.causes import fitting_ids

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Text200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]

# the card fields a v4 answer must fill (consequence_magnitude may be null: not every plant
# record gives one; fact_ids may be empty, and every ID given is checked)
CARD_FIELDS = (
    "initiating_event",
    "enabling_condition",
    "propagation",
    "operating_mode",
    "mechanism_class",
)
CARD_FROM_VERSION = 4
_VERSION = re.compile(r"^v(\d+)$")


def requires_card(version: str) -> bool:
    """Whether a prompt version asks for the card: `v4` and later; anything else does not."""
    match = _VERSION.match(version)
    return match is not None and int(match.group(1)) >= CARD_FROM_VERSION


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScreenHypothesis(_Strict):
    rank: Annotated[int, Field(ge=1)]
    mechanism: Text300
    component_ids: Annotated[list[str], Field(min_length=1)]
    chemical_ids: list[str]
    failing_component_type: FailingComponentType
    cause_id: str
    cause_text: Text200 | None
    consequence: Text300
    reason: Text300
    # Phase 9 (spec 9.1): the card; required from v4 (`requires_card`), absent before
    initiating_event: Text300 | None = None
    enabling_condition: Text300 | None = None
    propagation: Text300 | None = None
    consequence_magnitude: Text200 | None = None
    operating_mode: OperatingMode | None = None
    mechanism_class: MechanismClass | None = None
    fact_ids: list[str] = Field(default_factory=list)

    def id_for(self, pass_number: int = 1) -> str:
        return ids.hypothesis_id(
            self.rank, self.mechanism, self.component_ids, pass_number=pass_number
        )

    @property
    def hypothesis_id(self) -> str:
        return self.id_for(1)


class ScreenAnswer(_Strict):
    hypotheses: list[ScreenHypothesis]


def _steps_and_jobs(plant: Plant) -> set[str]:
    """What can fail as an operator: steps, jobs and, from Phase 9 (spec 9.2), changes."""
    steps = {s.id for p in plant.procedures for s in p.steps}
    return steps | {w.id for w in plant.planned_work} | {c.id for c in plant.changes}


def _can_fail_as(kind: FailingComponentType, plant: Plant) -> frozenset[str]:
    if kind == FailingComponentType.OPERATOR:
        return frozenset(_steps_and_jobs(plant))
    return fitting_ids(kind, plant)


def fitting(plant: Plant) -> dict[str, list[str]]:
    """For each failing-component type, the plant IDs that can fail as it, in enum order, types
    with none left out: the rule every finding is held to (R46), shown to the whole-plant pass
    as guidance (`can_fail_as`). Not enforced on hypotheses since G23."""
    listed = {kind.value: sorted(_can_fail_as(kind, plant)) for kind in FailingComponentType}
    return {kind: ids for kind, ids in listed.items() if ids}


def screen_causes(plant: Plant, ref: ReferenceSet) -> list[dict[str, str]]:
    """The library causes the whole plant can support (Q7, R46): their type fits a plant ID."""
    return [
        {"id": c.id, "cause": c.cause, "failing_component_type": c.failing_component_type}
        for c in sorted(ref.causes, key=lambda c: c.id)
        if _can_fail_as(FailingComponentType(c.failing_component_type), plant)
    ]


def answer_problems(answer: ScreenAnswer, max_hypotheses: int) -> list[str]:
    """Problems with the answer as a whole (G11): these fail it."""
    problems = []
    if len(answer.hypotheses) > max_hypotheses:
        problems.append(f"{len(answer.hypotheses)} hypotheses, at most {max_hypotheses}")
    ranks = [h.rank for h in answer.hypotheses]
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append(f"ranks must run 1 to {len(ranks)} in order, got {ranks}")
    seen: set[str] = set()
    for h in answer.hypotheses:
        if h.hypothesis_id in seen:
            problems.append(f"rank {h.rank} repeats an earlier hypothesis")
        seen.add(h.hypothesis_id)
    return problems


def hypothesis_problem(
    h: ScreenHypothesis, plant: Plant, ref: ReferenceSet, *, card_required: bool = False
) -> str | None:
    """What is wrong with one hypothesis, or None; a problem drops it."""
    objects = _objects(plant)
    unknown = [c for c in h.component_ids if c not in objects]
    if unknown:
        return f"rank {h.rank}: {', '.join(unknown)} not in this plant"
    chemicals = {c.id for c in plant.chemicals}
    unknown_chemicals = [c for c in h.chemical_ids if c not in chemicals]
    if unknown_chemicals:
        return f"rank {h.rank}: {', '.join(unknown_chemicals)} not a chemical of this plant"
    # G23: the failing type is not checked against the components of a hypothesis; every
    # finding that supports one is (R46)
    if h.cause_id == OUTSIDE_LIBRARY:
        if not h.cause_text:
            return f"rank {h.rank}: an outside_library cause needs cause_text"
    else:
        cause = next((c for c in ref.causes if c.id == h.cause_id), None)
        if cause is None:
            return f"rank {h.rank}: {h.cause_id} is not a library cause"
        if cause.failing_component_type != h.failing_component_type:
            return (
                f"rank {h.rank}: {h.cause_id} fails a {cause.failing_component_type}, "
                f"not a {h.failing_component_type}"
            )
    if card_required:
        lacking = [f for f in CARD_FIELDS if getattr(h, f) is None]
        if lacking:
            return f"rank {h.rank}: the card lacks {', '.join(lacking)}"
    for fact in h.fact_ids:
        problem = fact_problem(fact, plant, objects)
        if problem is not None:
            return f"rank {h.rank}: {problem}"
    return None


def fact_problem(
    fact: str, plant: Plant, objects: Mapping[str, BaseModel] | None = None
) -> str | None:
    """Why a cited ID is not a plant object or a plant fact (the provenance-key rule of
    `schema/validate.py`, applied to a model's citation), or None."""
    by_id = objects if objects is not None else _objects(plant)
    if fact in by_id:
        return None
    try:
        ref = ids.parse_fact_id(fact)
    except ValueError:
        return f"{fact} is not a plant object or fact ID"
    obj = by_id.get(ref.object_id)
    if obj is None:
        return f"{fact} names no plant object"
    if ref.field == "operating":
        for row in plant.operating:
            if row.target_id == ref.object_id and row.parameter == ref.parameter:
                if ref.limit in OPERATING_LIMITS and getattr(row, ref.limit or "") is not None:
                    return None
                return f"{fact} names an unset operating limit"
        return f"{fact} names no operating row"
    if ref.field not in type(obj).model_fields or ref.field == "id":
        return f"{fact} names no field of {ref.object_id}"
    return None


def _objects(plant: Plant) -> dict[str, BaseModel]:
    """Every plant object by ID, procedure steps included."""
    found: dict[str, BaseModel] = {}
    for _, value in plant:
        if isinstance(value, list):
            for obj in value:
                object_id = getattr(obj, "id", None)
                if object_id:
                    found[object_id] = obj
                for step in getattr(obj, "steps", None) or []:
                    found[step.id] = step
    return found


def _all_ids(plant: Plant) -> set[str]:
    return set(_objects(plant))


def every_problem(
    answer: Any,
    plant: Plant,
    ref: ReferenceSet,
    max_hypotheses: int,
    *,
    card_required: bool = False,
) -> list[str]:
    """For the validator (Q6): every problem, so the one retry can fix them all."""
    if not isinstance(answer, ScreenAnswer):
        return ["not a screen answer"]
    problems = answer_problems(answer, max_hypotheses)
    problems += [
        p
        for h in answer.hypotheses
        if (p := hypothesis_problem(h, plant, ref, card_required=card_required))
    ]
    return problems


def parse_answer(content: str | None) -> ScreenAnswer | None:
    """The final answer read again after an invalid retry, to keep the valid hypotheses (Q6);
    None when it is not even structurally a screen answer."""
    try:
        return ScreenAnswer.model_validate(json.loads(content or ""))
    except (json.JSONDecodeError, ValueError):
        return None


def plant_for_screen(plant: Plant) -> dict[str, Any]:
    """The plant record the screen reads (G17): everything but the plant ID, the provenance
    and every `source` (on a dev case they name the case file); the notes' text stays."""
    data: dict[str, Any] = plant.model_dump(mode="json", exclude_none=True)
    data.pop("plant_id", None)
    data.pop("provenance", None)
    cleaned: dict[str, Any] = _without_sources(data)
    return cleaned


def _without_sources(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_sources(v) for k, v in value.items() if k != "source"}
    if isinstance(value, list):
        return [_without_sources(v) for v in value]
    return value


def question_kinds(kinds: Sequence[str]) -> str:
    return ", ".join(sorted(set(kinds)))
