"""Section suggestions (spec 1.3): the response schema, the checks and apply.

A suggester proposes splits, merges and purposes, each with a reason; code checks every one
and rejects any that breaks the rules, with its reason. Phase 1 has no live suggester: the
endpoint uses `NullSuggester` and tests use `FakeSuggester`. Phase 2 adds the gateway one.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.api.models import SectionSuggestion
from guideword.schema import ids
from guideword.schema.enums import SectionKind, SectionType
from guideword.schema.plant import Plant
from guideword.schema.records import Section

REASON_MAX = 300
PURPOSE_MAX = 160
SECTION_ID_COUNT = {"split": "exactly 2", "merge": "at least 2", "purpose": "exactly 1"}
ONE_OBJECT_KINDS = {SectionKind.PROCEDURE, SectionKind.PLANNED_WORK}
LINE_KINDS = {SectionKind.LINE, SectionKind.NO_FLOW_LINE}


# --- the model response schema (internal; converted to the contract's SectionSuggestion) ------


class SuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["split", "merge", "purpose"]
    section_ids: Annotated[list[str], Field(min_length=1)]
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=PURPOSE_MAX)] | None = None
    reason: Annotated[str, StringConstraints(min_length=1, max_length=REASON_MAX)]


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[SuggestionItem]


def parse_response(data: Mapping[str, Any]) -> list[SectionSuggestion]:
    """Validate a suggester's JSON answer (caps included) and convert it to the contract shape."""
    response = SuggestionResponse.model_validate(data)
    return [SectionSuggestion.model_validate(item.model_dump()) for item in response.suggestions]


# --- suggesters -------------------------------------------------------------------------------


class Suggester(Protocol):
    def suggest(self, plant: Plant, sections: list[Section]) -> list[SectionSuggestion]: ...


class NullSuggester:
    """Phase 1's suggester: no suggestions (the live Super call is wired in Phase 2)."""

    def suggest(self, plant: Plant, sections: list[Section]) -> list[SectionSuggestion]:
        return []


class FakeSuggester:
    """Returns a fixed list (tests only)."""

    def __init__(self, suggestions: list[SectionSuggestion]) -> None:
        self._suggestions = list(suggestions)

    def suggest(self, plant: Plant, sections: list[Section]) -> list[SectionSuggestion]:
        return list(self._suggestions)


# --- checks -----------------------------------------------------------------------------------


def check_suggestions(
    plant: Plant, sections: list[Section], suggestions: list[SectionSuggestion]
) -> tuple[list[SectionSuggestion], list[tuple[SectionSuggestion, str]]]:
    """Split suggestions into valid ones and rejected ones with their reasons; never raises.

    Suggestions are checked in order, each against the set the earlier valid ones produce.
    """
    valid: list[SectionSuggestion] = []
    rejected: list[tuple[SectionSuggestion, str]] = []
    current = list(sections)
    for suggestion in suggestions:
        problem = _problem(plant, current, suggestion)
        if problem is None:
            valid.append(suggestion)
            current = apply(current, [suggestion])
        else:
            rejected.append((suggestion, problem))
    return valid, rejected


def _problem(plant: Plant, sections: list[Section], s: SectionSuggestion) -> str | None:
    wanted = s.section_ids
    count = len(wanted)
    if (s.kind == "merge" and count < 2) or (
        s.kind != "merge" and count != (2 if s.kind == "split" else 1)
    ):
        return f"a {s.kind} names {SECTION_ID_COUNT[s.kind]} section IDs, not {count}"
    if len(set(wanted)) != count:
        return "a section ID is repeated"
    by_id = {section.id: section for section in sections}
    named = wanted[:1] if s.kind == "split" else wanted
    unknown = [i for i in named if i not in by_id]
    if unknown:
        return f"unknown section {', '.join(unknown)}"
    if s.kind == "purpose":
        return None if s.purpose else "a purpose suggestion with no purpose"
    if s.kind == "split":
        return _split_problem(plant, by_id[wanted[0]], wanted[1], by_id)
    return _merge_problem([by_id[i] for i in wanted])


def _split_problem(
    plant: Plant, part: Section, new_id: str, by_id: Mapping[str, Section]
) -> str | None:
    if part.flagged_no_flow:
        return f"{part.id} is a flagged no-flow section; it is never split"
    if part.kind != SectionKind.LINE:
        return f"{part.id} is not a line section"
    line_id = part.object_ids[0]
    prefix = f"S-{line_id}~"
    component = new_id.removeprefix(prefix)
    if not new_id.startswith(prefix) or not component:
        return f"the new part's ID must be S-{line_id}~<component>, not {new_id}"
    line = next((x for x in plant.lines if x.id == line_id), None)
    if line is None or component not in line.components:
        return f"unknown component {component} on line {line_id}"
    if new_id in by_id:
        return f"{new_id} already exists"
    # strictly inside the part: one of its components, but not its first
    if component not in part.object_ids[2:]:
        return f"{component} is not inside {part.id}"
    return None


def _merge_problem(members: list[Section]) -> str | None:
    flagged = [m.id for m in members if m.flagged_no_flow]
    if flagged:
        return f"{', '.join(flagged)} is a flagged no-flow section; it is never merged"
    if len({m.kind for m in members}) > 1:
        return "a merge joins sections of different kinds"
    if len({m.section_type for m in members}) > 1:
        return "a merge joins sections of different section types"
    kind = members[0].kind
    if kind in ONE_OBJECT_KINDS:
        return f"a {kind.value} section holds one object; it is never merged"
    if kind in LINE_KINDS and len({m.object_ids[0] for m in members}) > 1:
        return "a merge joins parts of different lines"
    return None


# --- apply ------------------------------------------------------------------------------------


def apply(sections: list[Section], accepted: list[SectionSuggestion]) -> list[Section]:
    """Apply checked suggestions in order; the result is sorted by section ID."""
    by_id = {s.id: s for s in sections}
    for s in accepted:
        changed = {"drawn_by": "suggestion", "suggestion_reason": s.reason}
        if s.kind == "split":
            part, new_id = by_id[s.section_ids[0]], s.section_ids[1]
            line_id = part.object_ids[0]
            component = new_id.removeprefix(f"S-{line_id}~")
            at = part.object_ids.index(component)
            by_id[part.id] = part.model_copy(update={**changed, "object_ids": part.object_ids[:at]})
            by_id[new_id] = Section(
                id=ids.split_section_id(line_id, component),
                plant_record_id=part.plant_record_id,
                kind=SectionKind.LINE,
                section_type=SectionType.PIPE,
                name=f"{line_id} from {component} (pipe)",
                object_ids=[line_id, *part.object_ids[at:]],
                drawn_by="suggestion",
                suggestion_reason=s.reason,
            )
        elif s.kind == "merge":
            members = sorted((by_id.pop(i) for i in s.section_ids), key=lambda m: m.id)
            keep = members[0]
            object_ids = list(dict.fromkeys(o for m in members for o in m.object_ids))
            merged_id = ids.merged_section_id(m.id for m in members)
            by_id[merged_id] = keep.model_copy(update={**changed, "object_ids": object_ids})
        else:
            section = by_id[s.section_ids[0]]
            by_id[section.id] = section.model_copy(update={**changed, "purpose": s.purpose})
    return sorted(by_id.values(), key=lambda s: s.id)
