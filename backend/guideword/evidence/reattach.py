"""Re-attach a stored run's calculation cards under the current attach rule (review plan R2, Q5).

A stored run's physics cards were attached by the rule of their day. Each line that went
through the evidence step (one with a precedent record) is read again with
`physics.applicable`. The cards it now gives and the run lacks are calculated and added, the
way the evidence step writes them: an agent step, a tool call and the record. The cards it no
longer gives are superseded: copied to `superseded_records` verbatim and cleared. Cards it
still gives are left as they are. Code only and $0: no model call and no search; precedent
records, the run's status and every other record are untouched.

One `calculations_reattached` event, written last, names the date, the commit whose rule did it,
and every superseded and added ID, so a replay ends on it. A run with nothing to change gets
no event and no write.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from guideword.config import Config
from guideword.evidence.step import _Pending, calculate
from guideword.lopa.lines import section_for
from guideword.runs.extend import current_pass_seq
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import AgentTool, EventType, EvidenceKind, RunStatus
from guideword.schema.plant import Plant
from guideword.tools import physics

MARK = ":calculation:"
STEP_REASON = "code: calculations re-attached under the current attach rule (review plan R2)"


class ReattachRefused(ValueError):
    """The run can't be re-attached (not finished)."""


@dataclass(frozen=True)
class Reattached:
    superseded_ids: list[str]
    added_ids: list[str]


def reattach(
    runs: RunRepository,
    run_id: str,
    plant: Plant,
    config: Config,
    *,
    commit: str,
    today: date,
) -> Reattached:
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if run.status != RunStatus.FINISHED:
        raise ReattachRefused(f"run {run_id} is {run.status}, not finished")
    pass_seq = current_pass_seq(runs, run_id)
    with runs.step(run_id) as writer:
        findings = {f.id: f for f in writer.findings()}
        questions = {q.id: q for q in writer.questions()}
        sections = {s.id: s for s in writer.sections()}
        chains = {c.id: c for c in writer.chains()}
        evidence = writer.evidence()
        lines = list(
            dict.fromkeys(e.target_id for e in evidence if e.kind == EvidenceKind.PRECEDENT)
        )
        superseded: list[str] = []
        added: list[str] = []
        for target in lines:
            link_ids: Sequence[str] = chains[target].links if target in chains else [target]
            cards = physics.applicable(
                physics.line_links(
                    link_ids, findings, lambda f: section_for(f, questions, sections)
                ),
                plant,
            )
            given = {f"{c.calculation}-{c.equipment_id}": c for c in cards}
            stored = {
                e.id.rsplit(MARK, 1)[1]: e
                for e in evidence
                if e.target_id == target and e.kind == EvidenceKind.CALCULATION
            }
            superseded += [e.id for key, e in stored.items() if key not in given]
            new = [card for key, card in given.items() if key not in stored]
            if not new:
                continue
            pending = _Pending(writer, run.id, target)
            step = pending.step(AgentTool.PHYSICS_CALC, STEP_REASON)
            for card in new:
                result = calculate(run, config, plant, card.calculation, card.equipment_id)
                arguments = {
                    "calculation": str(card.calculation),
                    "equipment_id": card.equipment_id,
                }
                call = ids.tool_call_id(step.id, AgentTool.PHYSICS_CALC, arguments)
                record = physics.as_evidence(
                    result, run_id=run.id, target_id=target, tool_call_id=call
                )
                pending.tool(
                    step,
                    AgentTool.PHYSICS_CALC,
                    arguments,
                    result.tool_result(),
                    record_ids=[record.id],
                )
                pending.evidence.append(record)
                added.append(record.id)
            pending.write()
        if not superseded and not added:
            return Reattached([], [])
        event = writer.emit(
            EventType.CALCULATIONS_REATTACHED,
            {
                "date": today.isoformat(),
                "commit": commit,
                "superseded_ids": superseded,
                "added_ids": added,
            },
        )
        copied = writer.supersede_evidence(superseded, pass_seq, event.seq)
        if sorted(copied) != sorted(superseded):  # one transaction: nothing changes in between
            raise RuntimeError(f"run {run_id}: the superseded cards changed while copying")
    return Reattached(superseded, added)
