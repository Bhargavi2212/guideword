"""The LOPA record, pure code (spec 3.2; plan PR 4, P3-3, Q11, M1; PROJECT.md §5 Step 6.2).

- **Severity:** the scenario's (the lead finding's, or the chain's); none → no LOPA, listed
  "no severity", never a default class (Q11).
- **Initiating frequency:** `likelihood()`, the same function screening uses. A missing
  multiplier fact → an incomplete record naming it, never a default. No frequency and no fact
  to name (a cause that names no line or job, a `per_opportunity` event) → no LOPA, listed.
- **Layers:** the code-listed candidates, each credited or not by `credit()`. `arguments` is
  Ultra's yes or no per layer ID; None means code-only LOPA ("code-only LOPA: layers not
  argued"). An argument for a layer code did not list is refused: Ultra never adds a layer.
- **Arithmetic:** mitigated = initiating × Π credited PFD; tolerable from
  `tolerable_frequencies.csv` by severity; gap = mitigated ÷ tolerable. Nothing is rounded.
- **Modifiers:** none applied (P3-3); every modifier kind in `modifiers.csv` is listed, once,
  with "no plant fact or rule" (M1).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from guideword.config import CapsConfig
from guideword.lopa.candidates import Scenario, candidates
from guideword.lopa.credit import LayerArgument, credit
from guideword.ranking.likelihood import likelihood
from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.plant import Plant
from guideword.schema.records import LopaRecord, ModifierNotApplied

CODE_ONLY_FLAG = "code-only LOPA: layers not argued"
FREQUENCY_ASSUMED_FLAG = "frequency assumed — engineer to confirm"
MODIFIER_REASON = "no plant fact or rule"
NO_SEVERITY = "no severity"


class UnknownLayerError(ValueError):
    """An argument names a layer code did not list."""


@dataclass(frozen=True)
class NoLopa:
    """A line that gets no LOPA record, and why (listed, never given a default)."""

    target_id: str
    reason: str


def lopa_record(
    scenario: Scenario,
    *,
    run_id: str,
    plant: Plant,
    ref: ReferenceSet,
    caps: CapsConfig,
    arguments: Mapping[str, LayerArgument] | None,
    model_call_id: str | None = None,
) -> LopaRecord | NoLopa:
    if scenario.severity_class is None:
        return NoLopa(scenario.target_id, NO_SEVERITY)
    listed = candidates(scenario, plant)
    if arguments is not None:
        unknown = sorted(set(arguments) - {layer.id for layer in listed})
        if unknown:
            raise UnknownLayerError(
                f"{scenario.target_id}: argued layers not listed by code: {unknown}"
            )
    found = likelihood(scenario.finding, plant, ref, caps)
    if found.frequency_per_year is None and not found.missing_fact_ids:
        return NoLopa(scenario.target_id, f"no likelihood: {found.note}")

    layers = [
        credit(layer, scenario, plant, ref, None if arguments is None else arguments.get(layer.id))
        for layer in listed
    ]
    tolerable = next(
        t.tolerable_per_year
        for t in ref.tolerable_frequencies
        if t.severity_class == scenario.severity_class
    )
    flags = list(found.flags)
    if found.assumed:
        flags.append(FREQUENCY_ASSUMED_FLAG)
    if arguments is None:
        flags.append(CODE_ONLY_FLAG)

    mitigated: float | None = None
    gap: float | None = None
    if found.frequency_per_year is not None:
        credited = [layer.pfd for layer in layers if layer.credited and layer.pfd is not None]
        mitigated = found.frequency_per_year * math.prod(credited)
        gap = mitigated / tolerable

    return LopaRecord(
        id=ids.lopa_id(scenario.target_id),
        run_id=run_id,
        target_id=scenario.target_id,
        severity_class=scenario.severity_class,
        complete=found.frequency_per_year is not None,
        missing_fact_ids=list(found.missing_fact_ids),
        initiating_event_id=found.initiating_event_id,
        initiating_frequency_per_year=found.frequency_per_year,
        frequency_assumed=found.assumed,
        layers=layers,
        mitigated_frequency_per_year=mitigated,
        tolerable_per_year=tolerable,
        gap=gap,
        model_call_id=model_call_id,
        flags=flags,
        modifiers_not_applied=[
            ModifierNotApplied(kind=kind, reason=MODIFIER_REASON)
            for kind in dict.fromkeys(m.kind for m in ref.modifiers)
        ],
    )
