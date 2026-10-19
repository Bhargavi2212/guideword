"""Credit for one candidate layer: code decides, in the plan's order (spec 3.2; plan PR 4 rules
1-7, Q3, Q4, Q13, M2; PROJECT.md §5 Step 6.2).

The first rule that refuses gives the reason:

1. not argued (code-only, or Ultra left the layer out): "not argued — no credit";
2. Ultra says it does not apply: "does not apply: <Ultra's reason>";
3. a safeguard with no `layer_type` (or a relief device with no `kind`): no row, no credit;
4. a shared component: any of the safeguard's `component_ids`, or the layer itself, among the
   cause's failing components;
5. independence (Q3): where the layer's `protection_layers.csv` row requires it, the failing
   control loop's `sensor_id`, `controller_id` or `final_element_id` among the safeguard's
   `component_ids` (the loop's parts are not failing components themselves, Q4);
6. a relief device: its `relief_kind` row; any inlet valve normally closed → no credit; else
   any inlet valve not known to be locked open ("unmanaged") → `pfd_if_isolatable`; else `pfd`;
7. otherwise the `pfd` of the safeguard's `layer_type` row.

A refused layer has no PFD (M2). Ultra's yes or no and its reason are kept apart from code's
reason. Every PFD comes from `protection_layers.csv`.
"""

from dataclasses import dataclass

from guideword.lopa.candidates import Layer, Scenario
from guideword.reference import ReferenceSet
from guideword.reference.tables import ProtectionLayerRow
from guideword.schema import ids
from guideword.schema.enums import ValvePosition
from guideword.schema.plant import ControlLoop, Plant, ReliefDevice
from guideword.schema.records import LayerCredit

NOT_ARGUED = "not argued — no credit"


@dataclass(frozen=True)
class LayerArgument:
    """Ultra's judgment for one candidate layer: applies to this scenario, and why."""

    applies: bool
    reason: str


def _refused(
    layer: Layer, layer_type: str | None, reason: str, argument: LayerArgument | None
) -> LayerCredit:
    return LayerCredit(
        layer_id=layer.id,
        layer_type=layer_type,
        credited=False,
        pfd=None,
        reason=reason,
        applies=argument.applies if argument else None,
        argument=argument.reason if argument else None,
    )


def _credited(
    layer: Layer, layer_type: str, pfd: float, reason: str, argument: LayerArgument
) -> LayerCredit:
    return LayerCredit(
        layer_id=layer.id,
        layer_type=layer_type,
        credited=True,
        pfd=pfd,
        reason=reason,
        applies=argument.applies,
        argument=argument.reason,
    )


def _row(layer: Layer, ref: ReferenceSet) -> ProtectionLayerRow | str:
    """The layer's protection_layers.csv row, or why it has none."""
    if isinstance(layer, ReliefDevice):
        if layer.kind is None:
            fact = ids.fact_id(layer.id, "kind")
            return f"no credit — no kind ({fact}), so no protection_layers row"
        row = next((r for r in ref.protection_layers if r.relief_kind == layer.kind), None)
        if row is None:
            return f"no credit — no protection_layers row has relief_kind {layer.kind}"
        return row
    if layer.layer_type is None:
        return "no credit — no layer_type"
    row = next((r for r in ref.protection_layers if r.id == layer.layer_type), None)
    if row is None:
        return f"no credit — layer_type {layer.layer_type} is not in protection_layers.csv"
    return row


def _shared_component(layer: Layer, scenario: Scenario) -> str | None:
    if layer.id in scenario.failing_component_ids:
        return f"no credit — {layer.id} is itself a failing component"
    if isinstance(layer, ReliefDevice):
        return None
    shared = sorted(set(layer.component_ids) & scenario.failing_component_ids)
    if shared:
        return f"no credit — shares component {', '.join(shared)} with the cause"
    return None


def _failing_loops(scenario: Scenario, plant: Plant) -> list[ControlLoop]:
    return sorted(
        (loop for loop in plant.control_loops if loop.id in scenario.failing_component_ids),
        key=lambda loop: loop.id,
    )


def _shared_loop_part(
    layer: Layer, row: ProtectionLayerRow, scenario: Scenario, plant: Plant
) -> str | None:
    """Q3: the failing loop's part among the safeguard's components, where the row requires
    that part to be independent."""
    if isinstance(layer, ReliefDevice):
        return None
    components = set(layer.component_ids)
    for loop in _failing_loops(scenario, plant):
        parts = (
            ("sensor", loop.sensor_id, row.requires_independent_sensor),
            ("logic solver", loop.controller_id, row.requires_independent_logic),
            ("final element", loop.final_element_id, row.requires_independent_final_element),
        )
        for name, part, required in parts:
            if required and part in components:
                return f"no credit — shares {name} {part} with failing loop {loop.id}"
    return None


def _relief(
    device: ReliefDevice, row: ProtectionLayerRow, plant: Plant, argument: LayerArgument
) -> LayerCredit:
    valves = {v.id: v for v in plant.valves}
    inlets = [valves.get(valve_id) for valve_id in device.inlet_valve_ids]
    for valve_id, valve in zip(device.inlet_valve_ids, inlets, strict=True):
        if valve is not None and valve.normal_position == ValvePosition.CLOSED:
            return _refused(device, row.id, f"no credit — inlet valve {valve_id} closed", argument)
    for valve_id, valve in zip(device.inlet_valve_ids, inlets, strict=True):
        locked_open = (
            valve is not None
            and valve.normal_position == ValvePosition.OPEN
            and valve.locked is True
        )
        if not locked_open:
            if row.pfd_if_isolatable is None:
                return _refused(
                    device,
                    row.id,
                    f"no credit — inlet valve {valve_id} unmanaged and {row.id} has no "
                    "pfd_if_isolatable",
                    argument,
                )
            return _credited(
                device,
                row.id,
                row.pfd_if_isolatable,
                f"credited at pfd_if_isolatable — inlet valve {valve_id} unmanaged",
                argument,
            )
    why = "every inlet valve locked open" if device.inlet_valve_ids else "no inlet valve"
    return _credited(device, row.id, row.pfd, f"credited — {row.id} pfd, {why}", argument)


def credit(
    layer: Layer,
    scenario: Scenario,
    plant: Plant,
    ref: ReferenceSet,
    argument: LayerArgument | None,
) -> LayerCredit:
    row = _row(layer, ref)
    if isinstance(row, ProtectionLayerRow):
        layer_type: str | None = row.id
    else:
        layer_type = None if isinstance(layer, ReliefDevice) else layer.layer_type
    if argument is None:
        return _refused(layer, layer_type, NOT_ARGUED, None)
    if not argument.applies:
        return _refused(layer, layer_type, f"does not apply: {argument.reason}", argument)
    if isinstance(row, str):
        return _refused(layer, layer_type, row, argument)
    shared = _shared_component(layer, scenario) or _shared_loop_part(layer, row, scenario, plant)
    if shared is not None:
        return _refused(layer, layer_type, shared, argument)
    if isinstance(layer, ReliefDevice):
        return _relief(layer, row, plant, argument)
    return _credited(layer, row.id, row.pfd, f"credited — {row.id} pfd", argument)
