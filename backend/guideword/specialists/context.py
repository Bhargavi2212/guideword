"""Specialist contexts, built by code (PROJECT.md §5 table; plan R5, R6, R40, R43).

Each agent gets only the plant data its questions need, as JSON passed to the model as data.
Objects keep their `notes` verbatim. Safeguards with no layer type are included as existing
protection, with their description. Every list is ordered by ID so a context is
deterministic.

Rule R40: the process, chemistry, piping and dust agents also get the procedure steps and
planned jobs that act on their objects. A step acts on them when it names an equipment or
valve ID in the agent's scope; a job when its Phase 1 within-reach set overlaps the scope
(an unlocated job matches only through what it lists). The procedures and maintenance
agents cite their own steps and jobs. An operator cause must name a step or job from this
packet (`packet_ids`).

Rule R43: `fit` trims the packet from the end, in ID order, until the request fits the input
cap, logging what it dropped; if it still does not fit with the packet empty, the batch fails.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from pydantic import BaseModel

from guideword.logs import get_logger
from guideword.questions.build import within_reach
from guideword.schema import ids
from guideword.schema.enums import Agent, QuestionKind, SectionKind
from guideword.schema.plant import (
    Equipment,
    Line,
    PlannedWork,
    Plant,
    ProcedureStep,
    Safeguard,
)
from guideword.schema.records import Question, Section

log = get_logger(__name__)

# the agents whose steps or jobs are the subject of their questions, not an added packet
OWN_PACKET = {Agent.PROCEDURES, Agent.MAINTENANCE}


class BatchTooLarge(ValueError):
    """The batch does not fit `specialist_max_input_tokens` even with every step and job dropped."""


@dataclass(frozen=True)
class SpecialistContext:
    agent: Agent
    data: dict[str, Any]
    # plant IDs a finding may name as failing components
    citable_ids: frozenset[str]
    # safeguard and relief-device IDs a finding may name as existing protection
    safeguard_ids: frozenset[str]
    # the step and job IDs an operator cause may name (R40)
    packet_ids: frozenset[str]
    # steps and jobs trimmed off to fit the input cap (R43), in ID order
    dropped_ids: tuple[str, ...] = ()


class _HasId(Protocol):
    @property
    def id(self) -> str: ...


# --- helpers -------------------------------------------------------------------------------


def _dump(obj: BaseModel) -> dict[str, Any]:
    """An object as JSON, without empty values (so the context stays small)."""
    return {k: v for k, v in obj.model_dump(mode="json").items() if v is not None and v != []}


def _safeguard(guard: Safeguard) -> dict[str, Any]:
    dumped = _dump(guard)
    # shown even when empty: a safeguard with no layer type gets no LOPA credit
    dumped["layer_type"] = guard.layer_type
    return dumped


def _by_id[T: _HasId](objects: Iterable[T], wanted: set[str]) -> list[T]:
    return sorted((o for o in objects if o.id in wanted), key=lambda o: o.id)


def _section(sections: Mapping[str, Section], question: Question) -> Section | None:
    return sections.get(question.section_id) if question.section_id is not None else None


def _first_part(question: Question) -> str:
    return ids.parse_question_id(question.id).parts[0]


class _Index:
    def __init__(self, plant: Plant) -> None:
        self.plant = plant
        self.equipment = {e.id: e for e in plant.equipment}
        self.lines = {line.id: line for line in plant.lines}
        self.valves = {v.id: v for v in plant.valves}
        self.utilities = {u.id: u for u in plant.utilities}
        self.locations = {loc.id: loc for loc in plant.locations}
        self.relief = {d.id: d for d in plant.relief_devices}
        self.jobs = {w.id: w for w in plant.planned_work}
        self.procedures = {p.id: p for p in plant.procedures}
        self.steps = {s.id: (p.id, s) for p in plant.procedures for s in p.steps}

    def location_of(self, object_id: str) -> str | None:
        if object_id in self.equipment:
            return self.equipment[object_id].location_id
        if object_id in self.utilities:
            return self.utilities[object_id].location_id
        if object_id in self.jobs:
            return self.jobs[object_id].location_id
        if object_id in self.locations:
            return object_id
        return None

    def locations_of(self, object_ids: Iterable[str]) -> set[str]:
        return {loc for o in object_ids if (loc := self.location_of(o)) is not None}


def _line_reach(line: Line) -> set[str]:
    return {line.id, *line.components, line.from_id, line.to_id}


# --- the R40 packet ------------------------------------------------------------------------


def _step_entry(procedure_id: str, step: ProcedureStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "procedure_id": procedure_id,
        "text": step.text,
        "equipment_ids": list(step.equipment_ids),
        "valve_ids": list(step.valve_ids),
    }


def _job_entry(job: PlannedWork) -> dict[str, Any]:
    return {"id": job.id, "type": job.type.value, "line_ids": list(job.line_ids)}


def _packet(index: _Index, scope: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps = [
        _step_entry(procedure_id, step)
        for procedure_id, step in index.steps.values()
        if scope & (set(step.equipment_ids) | set(step.valve_ids))
    ]
    jobs = [
        _job_entry(job)
        for job in index.plant.planned_work
        if scope & set(within_reach(index.plant, job))
    ]
    return sorted(steps, key=lambda s: s["id"]), sorted(jobs, key=lambda j: j["id"])


# --- shared pieces -------------------------------------------------------------------------


def _safeguards(index: _Index, scope: set[str], locations: set[str]) -> list[dict[str, Any]]:
    wanted = scope | locations
    return [
        _safeguard(g)
        for g in sorted(index.plant.safeguards, key=lambda g: g.id)
        if (g.protects_id is not None and g.protects_id in wanted) or wanted & set(g.component_ids)
    ]


def _chemical_names(index: _Index, holders: Iterable[Equipment | Line]) -> list[dict[str, Any]]:
    """R6: name and physical form of each chemical in the holders' contents, nothing else."""
    contained = {c for h in holders for c in h.contents}
    out = []
    for chemical in sorted(index.plant.chemicals, key=lambda c: c.id):
        if chemical.id in contained:
            entry: dict[str, Any] = {"id": chemical.id, "name": chemical.name}
            if chemical.physical_form is not None:
                entry["physical_form"] = chemical.physical_form.value
            out.append(entry)
    return out


def _context(
    agent: Agent,
    data: dict[str, Any],
    citable: set[str],
    safeguards: list[dict[str, Any]],
    relief_ids: Iterable[str],
    packet: set[str] | None = None,
) -> SpecialistContext:
    if packet is None:
        packet = {s["id"] for s in data.get("procedure_steps", [])}
        packet |= {j["id"] for j in data.get("planned_jobs", [])}
    return SpecialistContext(
        agent=agent,
        data=data,
        citable_ids=frozenset(citable | packet),
        safeguard_ids=frozenset({g["id"] for g in safeguards} | set(relief_ids)),
        packet_ids=frozenset(packet),
    )


# --- one builder per agent -----------------------------------------------------------------

Builder = Callable[[_Index, Mapping[str, Section], Sequence[Question]], SpecialistContext]


def build_context(
    agent: Agent,
    plant: Plant,
    sections: Mapping[str, Section],
    questions: Sequence[Question],
) -> SpecialistContext:
    builders: dict[Agent, Builder] = {
        Agent.PROCESS: _process,
        Agent.CHEMISTRY: _chemistry,
        Agent.PIPING: _piping,
        Agent.PROCEDURES: _procedures,
        Agent.MAINTENANCE: _maintenance,
        Agent.DUST: _dust,
    }
    return builders[agent](_Index(plant), sections, questions)


def _process_scope(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> set[str]:
    """The sections' objects, the lines into or out of their equipment (with components and
    endpoints), heat-source lines and valves, and the relief devices on that equipment."""
    scope: set[str] = set()
    for question in questions:
        section = _section(sections, question)
        if section is not None:
            scope |= set(section.object_ids)
        if question.kind == QuestionKind.RELIEF_DISCHARGE:
            device = index.relief[_first_part(question)]
            scope |= {device.id, device.protects_id}
    for object_id in list(scope):
        equipment = index.equipment.get(object_id)
        if equipment is not None:
            for connected in index.plant.lines:
                if equipment.id in (connected.from_id, connected.to_id):
                    scope |= _line_reach(connected)
            for source in equipment.heat_sources:
                if source.via_line_id is not None and source.via_line_id in index.lines:
                    scope |= _line_reach(index.lines[source.via_line_id])
                scope |= set(source.isolating_valve_ids)
        own_line = index.lines.get(object_id)
        if own_line is not None:
            scope |= _line_reach(own_line)
    for device in index.plant.relief_devices:
        if device.protects_id in scope:
            scope |= {device.id, *device.inlet_valve_ids}
    return scope


def _process(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    scope = _process_scope(index, sections, questions)
    section_ids = sorted({s.id for q in questions if (s := _section(sections, q)) is not None})
    equipment = _by_id(plant.equipment, scope)
    lines = _by_id(plant.lines, scope)
    instruments = [i for i in sorted(plant.instruments, key=lambda i: i.id) if i.on_id in scope]
    instrument_ids = {i.id for i in instruments}
    loops = [
        loop
        for loop in sorted(plant.control_loops, key=lambda c: c.id)
        if {loop.sensor_id, loop.final_element_id, loop.acts_on_id} & (scope | instrument_ids)
    ]
    relief = [d for d in sorted(plant.relief_devices, key=lambda d: d.id) if d.protects_id in scope]
    valve_ids = (
        {v for v in scope if v in index.valves}
        | {v.id for v in plant.valves if v.on_line_id in scope}
        | {loop.final_element_id for loop in loops if loop.final_element_id in index.valves}
        | {v for d in relief for v in d.inlet_valve_ids}
    )
    discharge = {
        d.discharge.location_id
        for d in relief
        if d.discharge is not None and d.discharge.location_id
    }
    locations = index.locations_of(scope) | {loc for loc in discharge if loc is not None}
    guards = _safeguards(index, scope, locations)
    guard_ids = {g["id"] for g in guards}
    solver_ids = {loop.controller_id for loop in loops} | {
        c for g in plant.safeguards if g.id in guard_ids for c in g.component_ids
    }
    utility_ids = {u for u in scope if u in index.utilities}
    steps, jobs = _packet(index, scope)
    data = {
        "sections": [_dump(sections[s]) | {"purpose": sections[s].purpose} for s in section_ids],
        "equipment": [_dump(e) for e in equipment],
        "lines": [_dump(line) for line in lines],
        "valves": [_dump(v) for v in _by_id(plant.valves, valve_ids)],
        "instruments": [_dump(i) for i in instruments],
        "control_loops": [_dump(c) for c in loops],
        "logic_solvers": [_dump(s) for s in _by_id(plant.logic_solvers, solver_ids)],
        "operating": [
            _dump(row)
            for row in sorted(plant.operating, key=lambda r: (r.target_id, r.parameter))
            if row.target_id in scope
        ],
        "safeguards": guards,
        "relief_devices": [_dump(d) for d in relief],
        "utilities": [_dump(u) for u in _by_id(plant.utilities, utility_ids)],
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "chemicals": _chemical_names(index, [*equipment, *lines]),
        "procedure_steps": steps,
        "planned_jobs": jobs,
    }
    citable = (
        {e.id for e in equipment}
        | {line.id for line in lines}
        | valve_ids
        | instrument_ids
        | {c.id for c in loops}
        | {s for s in solver_ids if s in {ls.id for ls in plant.logic_solvers}}
        | {d.id for d in relief}
        | locations
        | utility_ids
    )
    return _context(Agent.PROCESS, data, citable, guards, [d.id for d in relief])


def _chemicals_asked(questions: Sequence[Question]) -> set[str]:
    asked: set[str] = set()
    for question in questions:
        parts = ids.parse_question_id(question.id).parts
        if question.kind == QuestionKind.CHEMICAL_PAIR:
            asked |= {parts[0], parts[1]}
        elif question.kind == QuestionKind.CHEMICAL_ENVIRONMENT:
            asked.add(parts[0])
    return asked


def _presence(
    chemical: str, holder: str, kind: str, via: str, location: str | None
) -> dict[str, Any]:
    return {
        "chemical_id": chemical,
        "holder_id": holder,
        "holder_kind": kind,
        "via": via,
        "location_id": location,
    }


def _chemistry(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    asked = _chemicals_asked(questions)
    presence: list[dict[str, Any]] = []
    for equipment in plant.equipment:
        for chemical in sorted(asked & set(equipment.contents)):
            presence.append(
                _presence(chemical, equipment.id, "equipment", "contents", equipment.location_id)
            )
        for into_equipment in equipment.injection_points:
            if into_equipment.chemical_id in asked:
                presence.append(
                    _presence(
                        into_equipment.chemical_id,
                        equipment.id,
                        "equipment",
                        "injection_point",
                        equipment.location_id,
                    )
                )
    for line in plant.lines:
        for chemical in sorted(asked & set(line.contents)):
            presence.append(_presence(chemical, line.id, "line", "contents", None))
        for into_line in line.injection_points:
            if into_line.chemical_id in asked:
                presence.append(
                    _presence(into_line.chemical_id, line.id, "line", "injection_point", None)
                )
    presence.sort(key=lambda p: (p["chemical_id"], p["holder_id"], p["via"]))
    holders = {p["holder_id"] for p in presence}
    # R40: the equipment whose contents include the chemicals, and the lines carrying them
    scope = {e.id for e in plant.equipment if asked & set(e.contents)}
    scope |= {line.id for line in plant.lines if asked & set(line.contents)}
    locations = {p["location_id"] for p in presence if p["location_id"] is not None}
    guards = _safeguards(index, holders, locations)
    steps, jobs = _packet(index, scope)
    data = {
        "chemicals": [_dump(c) for c in _by_id(plant.chemicals, asked)],
        "presence": presence,
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "safeguards": guards,
        "procedure_steps": steps,
        "planned_jobs": jobs,
    }
    return _context(Agent.CHEMISTRY, data, holders | locations, guards, [])


def _piping(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    asked = {_first_part(q) for q in questions if q.kind == QuestionKind.NO_FLOW_LINE}
    for question in questions:
        section = _section(sections, question)
        if section is not None and section.kind in (SectionKind.LINE, SectionKind.NO_FLOW_LINE):
            asked |= {o for o in section.object_ids if o in index.lines}
    scope: set[str] = set()
    for line_id in asked:
        scope |= _line_reach(index.lines[line_id])
    locations = index.locations_of(scope)
    guards = _safeguards(index, scope, locations)
    steps, jobs = _packet(index, scope)
    valve_ids = {v for v in scope if v in index.valves}
    valve_ids |= {v.id for v in plant.valves if v.on_line_id in asked}
    data = {
        "lines": [_dump(line) for line in _by_id(plant.lines, asked)],
        "valves": [_dump(v) for v in _by_id(plant.valves, valve_ids)],
        "equipment": [_dump(e) for e in _by_id(plant.equipment, scope)],
        "utilities": [_dump(u) for u in _by_id(plant.utilities, scope)],
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "safeguards": guards,
        "procedure_steps": steps,
        "planned_jobs": jobs,
    }
    return _context(Agent.PIPING, data, scope | valve_ids | locations, guards, [])


def _procedures(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    procedure_ids: set[str] = set()
    for question in questions:
        if question.kind == QuestionKind.PROCEDURE_STEP:
            procedure_ids.add(index.steps[_first_part(question)][0])
        section = _section(sections, question)
        if section is not None:
            procedure_ids |= {o for o in section.object_ids if o in index.procedures}
    procedures = _by_id(plant.procedures, procedure_ids)
    steps = sorted(
        (_step_entry(p.id, s) for p in procedures for s in p.steps), key=lambda s: s["id"]
    )
    named = {e for s in steps for e in s["equipment_ids"]} | {
        v for s in steps for v in s["valve_ids"]
    }
    locations = index.locations_of(named)
    guards = _safeguards(index, named, locations)
    data = {
        "procedures": [_dump(p) | {"steps": [s.id for s in p.steps]} for p in procedures],
        "procedure_steps": steps,
        "equipment": [_dump(e) for e in _by_id(plant.equipment, named)],
        "valves": [_dump(v) for v in _by_id(plant.valves, named)],
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "safeguards": guards,
    }
    return _context(Agent.PROCEDURES, data, named | locations, guards, [])


def _maintenance(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    job_ids = {_first_part(q) for q in questions if q.kind == QuestionKind.PLANNED_WORK}
    for question in questions:
        section = _section(sections, question)
        if section is not None:
            job_ids |= {o for o in section.object_ids if o in index.jobs}
    reach: set[str] = set()
    for job_id in job_ids:
        reach |= set(within_reach(plant, index.jobs[job_id]))
    all_jobs = job_ids | {r for r in reach if r in index.jobs}
    equipment = _by_id(plant.equipment, reach)
    lines = _by_id(plant.lines, reach)
    relief = _by_id(plant.relief_devices, reach)
    locations = index.locations_of(all_jobs) | index.locations_of(reach)
    guards = _safeguards(index, reach, locations)
    data = {
        "planned_jobs": [_dump(index.jobs[j]) for j in sorted(all_jobs)],
        "equipment": [_dump(e) for e in equipment],
        "lines": [_dump(line) for line in lines],
        "relief_devices": [_dump(d) for d in relief],
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "safeguards": guards,
        "chemicals": _chemical_names(index, [*equipment, *lines]),
    }
    citable = reach | locations | all_jobs
    return _context(
        Agent.MAINTENANCE, data, citable, guards, [d.id for d in relief], packet=all_jobs
    )


def _dust(
    index: _Index, sections: Mapping[str, Section], questions: Sequence[Question]
) -> SpecialistContext:
    plant = index.plant
    scope = {_first_part(q) for q in questions if q.kind == QuestionKind.DUST}
    equipment = _by_id(plant.equipment, scope)
    contained = {c for e in equipment for c in e.contents}
    locations = index.locations_of(scope)
    guards = _safeguards(index, scope, locations)
    steps, jobs = _packet(index, scope)
    data = {
        "equipment": [_dump(e) for e in equipment],
        "chemicals": [_dump(c) for c in _by_id(plant.chemicals, contained)],
        "locations": [_dump(loc) for loc in _by_id(plant.locations, locations)],
        "safeguards": guards,
        "procedure_steps": steps,
        "planned_jobs": jobs,
    }
    return _context(Agent.DUST, data, scope | locations, guards, [])


# --- R43: fit to the input cap -------------------------------------------------------------


def fit(
    context: SpecialistContext, measure: Callable[[SpecialistContext], int], limit: int
) -> SpecialistContext:
    """Drop steps and jobs from the end, in ID order, until `measure` is within `limit`."""
    if measure(context) <= limit:
        return context
    droppable: list[str] = []
    if context.agent not in OWN_PACKET:
        droppable = sorted(
            [s["id"] for s in context.data.get("procedure_steps", [])]
            + [j["id"] for j in context.data.get("planned_jobs", [])]
        )
    dropped: list[str] = []
    current = context
    while measure(current) > limit:
        if not droppable:
            raise BatchTooLarge(
                f"the batch needs about {measure(current)} input tokens with every step and job "
                f"dropped, over specialist_max_input_tokens ({limit})"
            )
        last = droppable.pop()
        dropped.insert(0, last)
        data = dict(current.data)
        data["procedure_steps"] = [s for s in data.get("procedure_steps", []) if s["id"] != last]
        data["planned_jobs"] = [j for j in data.get("planned_jobs", []) if j["id"] != last]
        current = replace(
            current,
            data=data,
            packet_ids=current.packet_ids - {last},
            citable_ids=current.citable_ids - {last},
            dropped_ids=tuple(dropped),
        )
    log.warning(
        "specialist context trimmed",
        extra={"context": {"agent": context.agent, "dropped_ids": dropped, "limit": limit}},
    )
    return current
