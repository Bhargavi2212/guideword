"""Engineer overrides: checked when made, applied on read (spec 3.5; Phase 3 plan PR 6, Q14,
Q17, G1, G2, G6; CLAUDE.md: model output is never edited in place).

An override names its target and replaces the latest override on that target, so each target
has one chain of overrides, oldest first. Views apply the chain in order; later ones win on
the same field. Nothing is ever removed: a rejected finding, chain or recommendation stays in
every view, with its state "rejected".

What fits which target (G2; 404 for an unknown target, else 422):

- `accept`, `reject`: a finding, chain or recommendation;
- `edit`: `action` on a recommendation, `consequence` on a finding, `purpose` on a section;
- `change_credit`: a LOPA record, on one of its layers that has a `protection_layers.csv` row;
- `change_severity`: a finding or a chain;
- `answer`: an engineer's question (`eng:`), which then counts as checked.

A credit the engineer gives uses the layer's own row (G1): a safeguard's `layer_type` row
`pfd`; a relief device's `relief_kind` row's full `pfd`, never `pfd_if_isolatable`, and the
layer's reason says "engineer asserts inlet valve managed". Code recomputes the mitigated
frequency, tolerable frequency and gap; the engineer never gives a number.
"""

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from guideword.reference import ReferenceSet
from guideword.reference.tables import ProtectionLayerRow
from guideword.schema import ids
from guideword.schema.enums import OverrideAction, QuestionKind, QuestionStatus, SeverityClass
from guideword.schema.plant import Plant
from guideword.schema.records import (
    Chain,
    Evidence,
    Finding,
    LayerCredit,
    LopaRecord,
    Override,
    Question,
    Recommendation,
    Section,
)

ENGINEER_ASSERTS_MANAGED = "engineer asserts inlet valve managed"
State = Literal["none", "accepted", "rejected", "edited"]
EDIT_FIELD_OF = {"finding": "consequence", "recommendation": "action", "section": "purpose"}


class OverrideRefused(ValueError):
    """An override that does not fit its target: `status` is 404 or 422."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status


class RunRecords(BaseModel):
    """The records of one run an override can name, and its overrides so far."""

    model_config = ConfigDict(frozen=True)

    findings: list[Finding]
    chains: list[Chain]
    lopa_records: list[LopaRecord]
    recommendations: list[Recommendation]
    questions: list[Question]
    sections: list[Section]
    overrides: list[Override]
    # Phase 4: read beside the line; never a target of an override
    evidence: list[Evidence] = Field(default_factory=list)

    def kind_of(self, target_id: str) -> str | None:
        for kind, records in (
            ("finding", self.findings),
            ("chain", self.chains),
            ("lopa", self.lopa_records),
            ("recommendation", self.recommendations),
            ("question", self.questions),
            ("section", self.sections),
        ):
            if any(r.id == target_id for r in records):
                return kind
        return None


# --- the chain of overrides on a target ------------------------------------------------------


def on_target(overrides: Sequence[Override], target_id: str) -> list[Override]:
    """The target's overrides, oldest first, following `replaces`."""
    mine = [o for o in overrides if o.target_id == target_id]
    by_replaced = {o.replaces: o for o in mine}
    chain: list[Override] = []
    current = by_replaced.get(None)
    while current is not None and current not in chain:
        chain.append(current)
        current = by_replaced.get(current.id)
    # anything off the chain (never written by this module) follows in stored order
    return chain + [o for o in mine if o not in chain]


def latest_on(overrides: Sequence[Override], target_id: str) -> Override | None:
    chain = on_target(overrides, target_id)
    return chain[-1] if chain else None


def override_state(chain: Sequence[Override]) -> State:
    """The state a view shows: the latest override's, or "none"."""
    if not chain:
        return "none"
    last = chain[-1].action
    if last == OverrideAction.ACCEPT:
        return "accepted"
    if last == OverrideAction.REJECT:
        return "rejected"
    return "edited"


# --- checked when made -------------------------------------------------------------------------


def _relief_kind_row(layer_id: str, plant: Plant, ref: ReferenceSet) -> ProtectionLayerRow | None:
    device = next((d for d in plant.relief_devices if d.id == layer_id), None)
    if device is None or device.kind is None:
        return None
    return next((r for r in ref.protection_layers if r.relief_kind == device.kind), None)


def layer_row(layer_id: str, plant: Plant, ref: ReferenceSet) -> ProtectionLayerRow | None:
    """The layer's own `protection_layers.csv` row (G1), or None when it has none."""
    if any(d.id == layer_id for d in plant.relief_devices):
        return _relief_kind_row(layer_id, plant, ref)
    guard = next((g for g in plant.safeguards if g.id == layer_id), None)
    if guard is None or guard.layer_type is None:
        return None
    return next((r for r in ref.protection_layers if r.id == guard.layer_type), None)


def check_override(
    target_id: str,
    action: OverrideAction,
    new_value: Any,
    records: RunRecords,
    plant: Plant,
    ref: ReferenceSet,
) -> None:
    """Raises OverrideRefused unless the override fits its target. The value's shape is
    already checked by the request model (contract v1.4)."""
    if any(e.id == target_id for e in records.evidence):
        # Phase 4 spec 4.4: the engineer reads evidence; it is never accepted or rejected
        raise OverrideRefused(422, "evidence can't be accepted or rejected")
    kind = records.kind_of(target_id)
    if kind is None:
        raise OverrideRefused(404, f"no record {target_id} in this run")
    if action in (OverrideAction.ACCEPT, OverrideAction.REJECT):
        if kind not in ("finding", "chain", "recommendation"):
            raise OverrideRefused(
                422, f"{action.value} applies to a finding, chain or recommendation"
            )
    elif action == OverrideAction.EDIT:
        [field] = new_value
        if EDIT_FIELD_OF.get(kind) != field:
            raise OverrideRefused(422, f"edit cannot change {field} on a {kind}")
    elif action == OverrideAction.CHANGE_CREDIT:
        if kind != "lopa":
            raise OverrideRefused(422, "change_credit applies to a LOPA record")
        record = next(r for r in records.lopa_records if r.id == target_id)
        layer_id = new_value["layer_id"]
        if layer_id not in {layer.layer_id for layer in record.layers}:
            raise OverrideRefused(422, f"{layer_id} is not a layer of {target_id}")
        if new_value["credited"] and layer_row(layer_id, plant, ref) is None:
            raise OverrideRefused(422, f"{layer_id} has no protection_layers row")
    elif action == OverrideAction.CHANGE_SEVERITY:
        if kind not in ("finding", "chain"):
            raise OverrideRefused(422, "change_severity applies to a finding or chain")
    elif action == OverrideAction.ANSWER:
        question = next((q for q in records.questions if q.id == target_id), None)
        if question is None or question.kind != QuestionKind.ENGINEER:
            raise OverrideRefused(422, "answer applies to an engineer's question")


def new_override(
    run_id: str,
    target_id: str,
    action: OverrideAction,
    new_value: Any,
    reason: str,
    by: str,
    at: datetime,
    records: RunRecords,
    plant: Plant,
    ref: ReferenceSet,
) -> Override:
    """A checked override that replaces the latest one on its target."""
    check_override(target_id, action, new_value, records, plant, ref)
    latest = latest_on(records.overrides, target_id)
    replaces = latest.id if latest is not None else None
    return Override(
        id=ids.override_id(target_id, action, new_value, replaces=replaces),
        run_id=run_id,
        target_id=target_id,
        action=action,
        new_value=new_value,
        reason=reason,
        by=by,
        at=at,
        replaces=replaces,
    )


# --- applied on read -------------------------------------------------------------------------


def _edits(chain: Sequence[Override], field: str) -> str | None:
    value = None
    for o in chain:
        if o.action == OverrideAction.EDIT and field in o.new_value:
            value = o.new_value[field]
    return value


def _severity(chain: Sequence[Override]) -> SeverityClass | None:
    value = None
    for o in chain:
        if o.action == OverrideAction.CHANGE_SEVERITY:
            value = SeverityClass(o.new_value["severity_class"])
    return value


def effective_finding(finding: Finding, overrides: Sequence[Override]) -> Finding:
    chain = on_target(overrides, finding.id)
    update: dict[str, Any] = {}
    if (consequence := _edits(chain, "consequence")) is not None:
        update["consequence"] = consequence
    if (severity := _severity(chain)) is not None:
        update["severity_class"] = severity
    return finding.model_copy(update=update) if update else finding


def effective_chain(chain: Chain, overrides: Sequence[Override]) -> Chain:
    severity = _severity(on_target(overrides, chain.id))
    return chain.model_copy(update={"severity_class": severity}) if severity else chain


def effective_recommendation(rec: Recommendation, overrides: Sequence[Override]) -> Recommendation:
    action = _edits(on_target(overrides, rec.id), "action")
    return rec.model_copy(update={"action": action}) if action is not None else rec


def effective_section(section: Section, overrides: Sequence[Override]) -> Section:
    purpose = _edits(on_target(overrides, section.id), "purpose")
    return section.model_copy(update={"purpose": purpose}) if purpose is not None else section


def effective_question(question: Question, overrides: Sequence[Override]) -> Question:
    """An engineer's question with an answer counts as checked (Q17)."""
    answered = any(o.action == OverrideAction.ANSWER for o in on_target(overrides, question.id))
    if answered and question.status == QuestionStatus.OPEN:
        return question.model_copy(update={"status": QuestionStatus.ANSWERED})
    return question


def _credited_layer(
    layer: LayerCredit, given: Override, plant: Plant, ref: ReferenceSet
) -> LayerCredit:
    if not given.new_value["credited"]:
        return layer.model_copy(
            update={
                "credited": False,
                "pfd": None,
                "reason": f"engineer removes credit ({given.id})",
            }
        )
    row = layer_row(layer.layer_id, plant, ref)
    if row is None:
        raise ValueError(f"{layer.layer_id} has no protection_layers row")
    reason = f"credited by the engineer — {row.id} pfd ({given.id})"
    if any(d.id == layer.layer_id for d in plant.relief_devices):
        reason = f"{reason}; {ENGINEER_ASSERTS_MANAGED}"
    return layer.model_copy(
        update={"credited": True, "pfd": row.pfd, "layer_type": row.id, "reason": reason}
    )


def effective_lopa(
    record: LopaRecord,
    overrides: Sequence[Override],
    severity_class: SeverityClass | None,
    plant: Plant,
    ref: ReferenceSet,
) -> LopaRecord:
    """The record with the engineer's credit changes and the target's severity as seen on
    read; the mitigated frequency, tolerable frequency and gap recomputed by code."""
    latest: dict[str, Override] = {}
    for o in on_target(overrides, record.id):
        if o.action == OverrideAction.CHANGE_CREDIT:
            latest[o.new_value["layer_id"]] = o
    severity = severity_class or record.severity_class
    if not latest and severity == record.severity_class:
        return record
    layers = [
        _credited_layer(layer, latest[layer.layer_id], plant, ref)
        if layer.layer_id in latest
        else layer
        for layer in record.layers
    ]
    tolerable = next(
        t.tolerable_per_year for t in ref.tolerable_frequencies if t.severity_class == severity
    )
    mitigated = gap = None
    if record.initiating_frequency_per_year is not None:
        credited = [layer.pfd for layer in layers if layer.credited and layer.pfd is not None]
        mitigated = record.initiating_frequency_per_year * math.prod(credited)
        gap = mitigated / tolerable
    return record.model_copy(
        update={
            "layers": layers,
            "severity_class": severity,
            "tolerable_per_year": tolerable,
            "mitigated_frequency_per_year": mitigated,
            "gap": gap,
        }
    )
