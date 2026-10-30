"""Links and support between the whole-plant pass's hypotheses and the pipeline (spec 2b.2;
R50; plan C1, A, B, Q8). Code only, deterministic.

**Question links** are made once, when a hypothesis is created, from the plant and the run's
sections: a question links when its objects include one of the hypothesis's components, or the
equipment and valves named by a procedure step or planned job among them (the reverse of R40),
or what any of those is attached to (a valve's line, an instrument's equipment, a loop's
equipment, a relief device's protected item: G16), or when its chemicals (pair and
environment questions) include one of the hypothesis's chemicals. An external or utility
hypothesis is plant-wide, and links no questions, only when every component really is of that
type, per `fitting()`: locations for `external`, utilities of the matching kind for the
utility types (G24). One that names equipment, a line or a step links like any other.

**Support** is computed from the current findings whenever it is read, never stored. A finding
supports a hypothesis when it answers a linked question and:
its failing components overlap the hypothesis's own components, or its question's chemicals
are all among the hypothesis's chemicals, or its question's section holds one of the
hypothesis's own components (not what they are attached to: G23, so an item no failing type
fits, which no finding can name, can still be confirmed); and
- for a library cause: it has the same cause;
- for an outside-library cause: it is outside-library too. The failing type is not compared;
  every finding already passed R46.
For a plant-wide hypothesis (a plant-wide type and, by the rule above, no links): the same
cause on the same component ID, on any question.
"""

from collections.abc import Iterable, Mapping, Sequence

from guideword.schema import ids
from guideword.schema.enums import FailingComponentType, QuestionKind
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Finding, Hypothesis, Question, Section
from guideword.screen.schema import fitting

PLANT_WIDE = frozenset(
    {
        FailingComponentType.EXTERNAL,
        FailingComponentType.UTILITY_COOLING,
        FailingComponentType.UTILITY_POWER,
    }
)
CHEMICAL_KINDS = frozenset({QuestionKind.CHEMICAL_PAIR, QuestionKind.CHEMICAL_ENVIRONMENT})


def _attached(plant: Plant, object_ids: set[str]) -> set[str]:
    """What the objects sit on (G16): a valve its line, an instrument the equipment or line it
    is on, a control loop what it acts on and where its sensor and final element sit, a relief
    device what it protects. Sections list only equipment and lines, so these reach them."""
    valves = {v.id: v.on_line_id for v in plant.valves}
    instruments = {i.id: i.on_id for i in plant.instruments}
    found: set[str] = set()
    for object_id in object_ids:
        found.add(valves.get(object_id) or "")
        found.add(instruments.get(object_id) or "")
    for loop in plant.control_loops:
        if loop.id in object_ids:
            found |= {
                loop.acts_on_id or "",
                instruments.get(loop.sensor_id) or "",
                valves.get(loop.final_element_id) or "",
                loop.final_element_id,
                loop.sensor_id,
            }
    for device in plant.relief_devices:
        if device.id in object_ids:
            found.add(device.protects_id)
    found.discard("")
    return found


def _reach(plant: Plant, component_ids: Iterable[str]) -> set[str]:
    """The components, the equipment and valves named by the procedure steps and planned jobs
    among them (the reverse of R40), and what all of those are attached to."""
    reach = set(component_ids)
    for procedure in plant.procedures:
        for step in procedure.steps:
            if step.id in reach:
                reach |= set(step.equipment_ids) | set(step.valve_ids)
    for job in plant.planned_work:
        if job.id in reach:
            reach |= set(job.equipment_ids)
    # Phase 9 (spec 9.2): a change reaches its objects; an impairment what its safeguard protects
    for change in plant.changes:
        if change.id in reach:
            reach |= set(change.object_ids)
    guards = {g.id: g for g in plant.safeguards}
    devices = {d.id: d for d in plant.relief_devices}
    for impairment in plant.impairments:
        if impairment.id in reach:
            guard = guards.get(impairment.safeguard_id)
            if guard is not None:
                reach |= {guard.id, guard.protects_id or ""} | set(guard.component_ids)
            device = devices.get(impairment.safeguard_id)
            if device is not None:
                reach |= {device.id, device.protects_id}
    reach.discard("")
    return reach | _attached(plant, reach)


def _chemicals(question: Question) -> set[str]:
    if question.kind == QuestionKind.CHEMICAL_PAIR:
        parts = ids.parse_question_id(question.id).parts
        return {parts[0], parts[1]}
    if question.kind == QuestionKind.CHEMICAL_ENVIRONMENT:
        return {ids.parse_question_id(question.id).parts[0]}
    return set()


def _objects(question: Question, sections: Mapping[str, Section], plant_ids: set[str]) -> set[str]:
    """The plant objects a question is about: its section's, and any named in its ID."""
    section = sections.get(question.section_id) if question.section_id is not None else None
    objects = set(section.object_ids) if section is not None else set()
    if question.kind not in CHEMICAL_KINDS:
        objects |= {part for part in ids.parse_question_id(question.id).parts if part in plant_ids}
    return objects


def _plant_ids(plant: Plant) -> set[str]:
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


def question_links(
    component_ids: Sequence[str],
    chemical_ids: Sequence[str],
    failing_component_type: FailingComponentType | str,
    plant: Plant,
    sections: Iterable[Section],
    questions: Iterable[Question],
) -> list[str]:
    """The question IDs a new hypothesis links to, in ID order."""
    kind = FailingComponentType(failing_component_type)
    if kind in PLANT_WIDE and set(component_ids) <= set(fitting(plant).get(kind.value, [])):
        return []
    by_id = {s.id: s for s in sections}
    plant_ids = _plant_ids(plant)
    reach = _reach(plant, component_ids)
    chemicals = set(chemical_ids)
    linked = {
        q.id
        for q in questions
        if (_objects(q, by_id, plant_ids) & reach) or (_chemicals(q) & chemicals)
    }
    return sorted(linked)


def _same_cause(hypothesis: Hypothesis, finding: Finding) -> bool:
    if hypothesis.cause_id == OUTSIDE_LIBRARY:
        return (
            finding.cause_id == OUTSIDE_LIBRARY
            and finding.failing_component_type == hypothesis.failing_component_type
        )
    return finding.cause_id == hypothesis.cause_id


def supports(
    hypothesis: Hypothesis,
    finding: Finding,
    questions: Mapping[str, Question],
    sections: Mapping[str, Section],
) -> bool:
    own = set(hypothesis.component_ids)
    overlap = bool(set(finding.failing_component_ids) & own)
    # plant-wide: the links were set by the rule above when the hypothesis was made (G24)
    if hypothesis.failing_component_type in PLANT_WIDE and not hypothesis.question_ids:
        return overlap and _same_cause(hypothesis, finding)
    if finding.question_id not in hypothesis.question_ids:
        return False
    question = questions.get(finding.question_id)
    chemicals = _chemicals(question) if question is not None else set()
    same_chemicals = bool(chemicals) and chemicals <= set(hypothesis.chemical_ids)
    section = (
        sections.get(question.section_id)
        if question is not None and question.section_id is not None
        else None
    )
    in_own_section = section is not None and bool(set(section.object_ids) & own)
    matched = overlap or same_chemicals or in_own_section
    if hypothesis.cause_id == OUTSIDE_LIBRARY:
        return finding.cause_id == OUTSIDE_LIBRARY and matched
    return matched and finding.cause_id == hypothesis.cause_id


def support(
    hypothesis: Hypothesis,
    findings: Iterable[Finding],
    questions: Iterable[Question],
    sections: Iterable[Section],
) -> list[Finding]:
    """The findings that support the hypothesis now, in ID order."""
    by_id = {q.id: q for q in questions}
    by_section = {s.id: s for s in sections}
    return sorted(
        (f for f in findings if supports(hypothesis, f, by_id, by_section)), key=lambda f: f.id
    )
