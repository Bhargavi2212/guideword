"""The shortlist as the API serves it (spec 3.3; Phase 3 plan PR 6, G6, G9; contract v1.2, v1.5).

PR 5's `lopa/lines.py` decides which lines there are and their order (tier first, R50; then
complete LOPA by gap, largest first; then incomplete LOPA; then no LOPA); this module reads
the run's records, applies the engineer's overrides on read and builds the contract items.
The lines and their LOPA plan are those the run computed from its stored findings; an
override changes what an item shows and its gap, so the order within a tier follows the gap
as seen, and never crosses tiers.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from guideword.api import models as api
from guideword.config import CapsConfig
from guideword.lopa.lines import (
    NO_SEVERITY_NO_LOPA,
    ShortlistLine,
    display_lines,
    lopa_plan,
    section_for,
    shortlist,
)
from guideword.reference import ReferenceSet
from guideword.review.display import gap_text
from guideword.review.overrides import (
    RunRecords,
    effective_chain,
    effective_finding,
    effective_lopa,
    effective_recommendation,
    on_target,
    override_state,
)
from guideword.review.text_check import unexpected_flags, unfinished_flags
from guideword.schema.enums import Confidence, EvidenceKind, Verdict
from guideword.schema.plant import Plant
from guideword.schema.records import (
    Chain,
    Evidence,
    Finding,
    Hypothesis,
    LopaRecord,
    ModelCall,
    Override,
)
from guideword.tools import physics

PRE_R50_LABEL = "pre-R50 run"
# Phase 4 spec 4.4: what a line's evidence adds to its card
EVIDENCE_SKIPPED = "evidence skipped: missing {facts}"
EVIDENCE_CONTRADICTS = "evidence contradicts this line: {summary}"


def evidence_for(records: Sequence[Evidence], target_id: str) -> list[Evidence]:
    return [e for e in records if e.target_id == target_id]


def evidence_flags(records: Sequence[Evidence]) -> list[str]:
    flags = [
        EVIDENCE_SKIPPED.format(facts=", ".join(e.missing_fact_ids))
        for e in records
        if e.missing_fact_ids
    ]
    flags += [
        EVIDENCE_CONTRADICTS.format(summary=e.summary)
        for e in records
        if e.verdict == Verdict.CONTRADICTED
    ]
    return flags


@dataclass(frozen=True)
class RunView:
    """What a view reads of one run."""

    run_id: str
    # the run's own `lopa_top_n` (G8)
    top_n: int
    pre_r50: bool
    records: RunRecords
    hypotheses: Sequence[Hypothesis]
    model_calls: Sequence[ModelCall]
    # the run's lead tie-break (lead tie-break plan); off for runs stored without it
    prefer_own_section: bool = False


def _state_flag(what: str, chain: Sequence[Override]) -> str | None:
    state = override_state(chain)
    if state == "none":
        return None
    return f"{what} {state} by the engineer ({chain[-1].id})"


def effective_records(view: RunView, plant: Plant, ref: ReferenceSet) -> list[LopaRecord]:
    """Every LOPA record as seen: the engineer's credit changes, and its target's severity
    after any `change_severity`."""
    records, overrides = view.records, view.records.overrides
    severity = {f.id: effective_finding(f, overrides).severity_class for f in records.findings}
    severity |= {c.id: effective_chain(c, overrides).severity_class for c in records.chains}
    return [
        effective_lopa(r, overrides, severity.get(r.target_id), plant, ref)
        for r in records.lopa_records
    ]


def shortlist_lines(
    view: RunView, plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[ShortlistLine]:
    records = view.records
    lines = display_lines(
        records.findings,
        view.hypotheses,
        records.questions,
        records.sections,
        plant,
        ref,
        caps,
        prefer_own_section=view.prefer_own_section,
    )
    plan = lopa_plan(
        lines,
        records.chains,
        records.findings,
        records.questions,
        records.sections,
        top_n=view.top_n,
    )
    return shortlist(
        plan,
        effective_records(view, plant, ref),
        records.recommendations,
        view.model_calls,
        run_id=view.run_id,
        plant=plant,
        ref=ref,
        caps=caps,
    )


def model_text(line: ShortlistLine, lead: Finding | None) -> list[tuple[str, str | None]]:
    """The model's own text on a card, as stored (never the override-applied view): the lead
    finding, the chain, the hypothesis, the LOPA arguments and the recommendations."""
    fields: list[tuple[str, str | None]] = []
    if lead is not None:
        fields += [
            ("finding cause", lead.cause_text),
            ("finding consequence", lead.consequence),
            ("finding severity reason", lead.severity_reason),
        ]
    chain = line.planned.chain
    if chain is not None:
        fields += [
            ("chain description", chain.description),
            ("chain reason", chain.reason),
            ("chain severity reason", chain.severity_reason),
        ]
    tiered = line.planned.line
    hypothesis = tiered.hypothesis if tiered is not None else None
    if hypothesis is not None:
        fields += [
            ("hypothesis mechanism", hypothesis.mechanism),
            ("hypothesis cause", hypothesis.cause_text),
            ("hypothesis consequence", hypothesis.consequence),
            ("hypothesis reason", hypothesis.reason),
        ]
    if line.lopa is not None:
        fields += [
            (f"LOPA argument {layer.layer_id}", layer.argument) for layer in line.lopa.layers
        ]
    for rec in line.recommendations:
        fields += [("recommendation action", rec.action), ("recommendation reason", rec.reason)]
    return fields


def _unsure(finding: Finding | None, chain: Chain | None, findings: dict[str, Finding]) -> bool:
    if chain is not None:
        # G9: a chain is unsure when any of its finding links is
        return any(
            findings[link].confidence == Confidence.UNSURE
            for link in chain.links
            if link in findings
        )
    return finding is not None and finding.confidence == Confidence.UNSURE


def _via(line: ShortlistLine, view: RunView, plant: Plant) -> dict[str, tuple[str, ...]]:
    """Contract v1.11: each calculation card's `via_ids`, by its evidence ID's
    `calculation:<calculation>-<equipment>` key, from the attachment rule the evidence step
    uses (review plan §0a), computed when the list is read. A stored card the rule no longer
    gives has none."""
    records = view.records
    findings = {f.id: f for f in records.findings}
    questions = {q.id: q for q in records.questions}
    sections = {s.id: s for s in records.sections}
    chain = line.planned.chain
    links = physics.line_links(
        chain.links if chain is not None else [line.planned.target_id],
        findings,
        lambda f: section_for(f, questions, sections),
    )
    return {
        f"calculation:{card.calculation}-{card.equipment_id}": card.via_ids
        for card in physics.applicable(links, plant)
    }


def _card(record: Evidence, via: Mapping[str, tuple[str, ...]]) -> api.ShortlistEvidence:
    _, _, key = record.id.rpartition(":calculation:")
    shown = via.get(f"calculation:{key}", ()) if record.kind == EvidenceKind.CALCULATION else ()
    return api.ShortlistEvidence.model_validate(record.model_dump() | {"via_ids": list(shown)})


def _item(line: ShortlistLine, rank: int, view: RunView, plant: Plant) -> api.ShortlistItem:
    planned, overrides = line.planned, view.records.overrides
    findings = {f.id: f for f in view.records.findings}
    tiered = planned.line
    hypothesis = tiered.hypothesis if tiered is not None else None
    lead = tiered.lead.finding if tiered is not None and tiered.lead is not None else None
    finding = effective_finding(lead, overrides) if lead is not None else None
    chain = effective_chain(planned.chain, overrides) if planned.chain is not None else None
    flags = list(line.flags)
    if line.no_lopa_reason is not None and NO_SEVERITY_NO_LOPA not in flags:
        flags.append(f"no LOPA: {line.no_lopa_reason}")
    if view.pre_r50:
        flags.append(PRE_R50_LABEL)
    evidence = (
        evidence_for(view.records.evidence, planned.target_id)
        if planned.target_kind != "hypothesis"
        else []
    )
    flags += evidence_flags(evidence)
    via = _via(line, view, plant) if evidence else {}
    stored = model_text(line, lead)
    flags += unexpected_flags(stored)
    flags += unfinished_flags(stored)
    target = "chain" if chain is not None else "finding"
    if planned.target_kind != "hypothesis":
        flag = _state_flag(target, on_target(overrides, planned.target_id))
        if flag is not None:
            flags.append(flag)
    if line.lopa is not None:
        flag = _state_flag("LOPA", on_target(overrides, line.lopa.id))
        if flag is not None:
            flags.append(flag)
    for rec in line.recommendations:
        flag = _state_flag(f"recommendation {rec.id}", on_target(overrides, rec.id))
        if flag is not None:
            flags.append(flag)
    return api.ShortlistItem(
        rank=rank,
        target_id=planned.target_id,
        target_kind=planned.target_kind,
        gap=line.lopa.gap if line.lopa is not None else None,
        multi_failure=chain.multi_failure if chain is not None else False,
        unsure=_unsure(finding, planned.chain, findings),
        finding=finding if chain is None else None,
        chain=chain,
        lopa=line.lopa,
        # contract v1.11: what each card is attached through (review plan R1)
        evidence=[_card(e, via) for e in evidence],
        recommendations=[effective_recommendation(r, overrides) for r in line.recommendations],
        tier=planned.tier,
        hypothesis_id=hypothesis.id if hypothesis is not None else None,
        hypothesis_rank=hypothesis.rank if hypothesis is not None else None,
        hypothesis=hypothesis,
        support_finding_ids=list(tiered.support_ids) if tiered is not None else [],
        flags=flags,
        # contract v1.6: the worksheet's formatter, so the card and the export agree
        gap_text=gap_text(line.lopa) if line.lopa is not None else None,
    )


def shortlist_items(
    view: RunView, plant: Plant, ref: ReferenceSet, caps: CapsConfig
) -> list[api.ShortlistItem]:
    return [
        _item(line, rank, view, plant)
        for rank, line in enumerate(shortlist_lines(view, plant, ref, caps), start=1)
    ]
