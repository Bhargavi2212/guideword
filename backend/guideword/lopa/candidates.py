"""The scenario a LOPA record is for, and its candidate layers, chosen by code (spec 3.2; plan
PR 4, Q7, Q8).

A line is a scenario (R48): its target is the lead finding, its objects the lead's section
objects plus its failing components (a pair or environment question has no section, so only
the failing components). A chain's target is the chain: its cause is its first finding link
in the model's order (Q7), and its objects and failing components are the union over its
finding links (Q8); fact links add nothing.

Candidates: every safeguard with a `layer_type` whose `protects_id` is among the objects, and
every relief device whose `protects_id` is; in ID order. Ultra never adds one.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from guideword.schema.enums import SeverityClass
from guideword.schema.plant import Plant, ReliefDevice, Safeguard
from guideword.schema.records import Chain, Finding, Section

Layer = Safeguard | ReliefDevice


@dataclass(frozen=True)
class Scenario:
    # the lead finding ID, or the chain ID
    target_id: str
    # the finding whose likelihood is the initiating frequency
    finding: Finding
    severity_class: SeverityClass | None
    # section objects and failing components: what a candidate layer must protect
    object_ids: frozenset[str]
    # the cause's failing components (for a chain, every finding link's)
    failing_component_ids: frozenset[str]
    # a chain only: each failing component with the finding links that carry it, so a refusal
    # names the link that caused it (Bhargavi, 2026-10-19); empty for a line
    component_links: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def link_note(self, *component_ids: str) -> str:
        """` (chain link <id>, ...)` for the links carrying these components; "" on a line."""
        carried = dict(self.component_links)
        links = sorted({link for c in component_ids for link in carried.get(c, ())})
        return f" (chain link {', '.join(links)})" if links else ""


def _objects(found: Finding, section: Section | None) -> set[str]:
    return set(found.failing_component_ids) | set(section.object_ids if section else ())


def line_scenario(lead: Finding, section: Section | None) -> Scenario:
    """A shortlist line: its lead finding, in the lead's section (None for no section)."""
    return Scenario(
        target_id=lead.id,
        finding=lead,
        severity_class=lead.severity_class,
        object_ids=frozenset(_objects(lead, section)),
        failing_component_ids=frozenset(lead.failing_component_ids),
    )


def chain_scenario(chain: Chain, links: Sequence[tuple[Finding, Section | None]]) -> Scenario:
    """`links`: the chain's finding links, each with its section, in any order; the first in
    `chain.links` order is the cause."""
    by_id = {found.id: (found, section) for found, section in links}
    finding_links = [link for link in chain.links if link in by_id]
    if not finding_links or set(by_id) - set(chain.links):
        raise ValueError(f"{chain.id}: the findings given are not its finding links")
    objects: set[str] = set()
    failing: set[str] = set()
    carried: dict[str, set[str]] = {}
    for link in finding_links:
        found, section = by_id[link]
        objects |= _objects(found, section)
        failing |= set(found.failing_component_ids)
        for component in found.failing_component_ids:
            carried.setdefault(component, set()).add(link)
    return Scenario(
        target_id=chain.id,
        finding=by_id[finding_links[0]][0],
        severity_class=chain.severity_class,
        object_ids=frozenset(objects),
        failing_component_ids=frozenset(failing),
        component_links=tuple(sorted((c, tuple(sorted(links))) for c, links in carried.items())),
    )


def candidates(scenario: Scenario, plant: Plant) -> list[Layer]:
    guards: list[Layer] = [
        g
        for g in plant.safeguards
        if g.layer_type is not None and g.protects_id in scenario.object_ids
    ]
    reliefs: list[Layer] = [r for r in plant.relief_devices if r.protects_id in scenario.object_ids]
    return sorted([*guards, *reliefs], key=lambda layer: layer.id)
