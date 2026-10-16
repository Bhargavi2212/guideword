"""The whole-plant pass's answer and its checks (spec 2b.1; R50; plan Q4–Q7, G11).

The answer as a whole must hold together: at most `plant_screen_max_hypotheses` hypotheses,
ranked 1 to n in order, no two the same hypothesis. Each hypothesis must name plant objects
that can fail as its type (R46, over the whole plant), plant chemicals, and either a library
cause of that same type or an outside-library cause with its text. A whole-answer problem
fails the answer; a hypothesis's own problem drops just that hypothesis.
"""

import json
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import FailingComponentType
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY
from guideword.specialists.causes import fitting_ids

Text300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Text200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]


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

    @property
    def hypothesis_id(self) -> str:
        return ids.hypothesis_id(self.rank, self.mechanism, self.component_ids)


class ScreenAnswer(_Strict):
    hypotheses: list[ScreenHypothesis]


def _steps_and_jobs(plant: Plant) -> set[str]:
    return {s.id for p in plant.procedures for s in p.steps} | {w.id for w in plant.planned_work}


def _can_fail_as(kind: FailingComponentType, plant: Plant) -> frozenset[str]:
    if kind == FailingComponentType.OPERATOR:
        return frozenset(_steps_and_jobs(plant))
    return fitting_ids(kind, plant)


def fitting(plant: Plant) -> dict[str, list[str]]:
    """For each failing-component type, the plant IDs that can fail as it, in enum order, types
    with none left out. The one source for the prompt's list, the misfit check and the retry
    message (plant_screen v2), so the model is told the rule it is judged by."""
    listed = {kind.value: sorted(_can_fail_as(kind, plant)) for kind in FailingComponentType}
    return {kind: ids for kind, ids in listed.items() if ids}


def _misfit(component: str, kind: str, listed: dict[str, list[str]]) -> str:
    kinds = [k for k, members in listed.items() if component in members]
    allowed = (
        f"{component} can fail as: {', '.join(kinds)}"
        if kinds
        else f"{component} can fail as nothing; name its loop, instrument, line or location instead"
    )
    return f"{component} cannot fail as a {kind}; {allowed}"


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


def hypothesis_problem(h: ScreenHypothesis, plant: Plant, ref: ReferenceSet) -> str | None:
    """What is wrong with one hypothesis, or None; a problem drops it."""
    plant_ids = _all_ids(plant)
    unknown = [c for c in h.component_ids if c not in plant_ids]
    if unknown:
        return f"rank {h.rank}: {', '.join(unknown)} not in this plant"
    chemicals = {c.id for c in plant.chemicals}
    unknown_chemicals = [c for c in h.chemical_ids if c not in chemicals]
    if unknown_chemicals:
        return f"rank {h.rank}: {', '.join(unknown_chemicals)} not a chemical of this plant"
    listed = fitting(plant)
    fits = listed.get(h.failing_component_type.value, [])
    misfits = [c for c in h.component_ids if c not in fits]
    if misfits:
        why = "; ".join(_misfit(c, h.failing_component_type.value, listed) for c in misfits)
        return f"rank {h.rank}: {why}"
    if h.cause_id == OUTSIDE_LIBRARY:
        return None if h.cause_text else f"rank {h.rank}: an outside_library cause needs cause_text"
    cause = next((c for c in ref.causes if c.id == h.cause_id), None)
    if cause is None:
        return f"rank {h.rank}: {h.cause_id} is not a library cause"
    if cause.failing_component_type != h.failing_component_type:
        return (
            f"rank {h.rank}: {h.cause_id} fails a {cause.failing_component_type}, "
            f"not a {h.failing_component_type}"
        )
    return None


def _all_ids(plant: Plant) -> set[str]:
    found: set[str] = set()
    for _, value in plant:
        if isinstance(value, list):
            for obj in value:
                object_id = getattr(obj, "id", None)
                if object_id:
                    found.add(object_id)
                for step in getattr(obj, "steps", None) or []:
                    found.add(step.id)
    return found


def every_problem(answer: Any, plant: Plant, ref: ReferenceSet, max_hypotheses: int) -> list[str]:
    """For the validator (Q6): every problem, so the one retry can fix them all."""
    if not isinstance(answer, ScreenAnswer):
        return ["not a screen answer"]
    problems = answer_problems(answer, max_hypotheses)
    problems += [p for h in answer.hypotheses if (p := hypothesis_problem(h, plant, ref))]
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
