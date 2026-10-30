# Grading rubric: held-out cases k, m, p

Grade each line on its own, against the key's `root_cause`, `component_ids` and `missed_by_original_review` only.

## Scores

- **hit**: the right mechanism on the right component. An engineer reading the line would say "that's the incident".
- **partial**: close but not that. Either the right component with the wrong mechanism, or the right mechanism on a neighbouring component.
- **miss**: anything else.

## Rules for the miss/partial line

- **R1. Right component means the component that fails or deviates in the line.** A key component that only appears in the equipment list, or as a bystander, doesn't count. For example, a generic piping leak that lists L-OVHD among four lines is a miss.
- **R2. An opposite deviation is a miss**, even on a key component. For example, a line about less flow, a valve driven closed or no feed, when the accident involved more flow, a valve leaking open or extra charge.
- **R3. A missed-review item with no failure mechanism is a miss.** For example, control-room siting, an evacuation plan, a sampling lapse with no key component, or an emergency-procedure gap.

## Open: the partial/hit line

Not yet decided. Two readings are in use:

- **A.** Hit = the right mechanism on a key component, even without the root cause. Example: case k X1, a fouled E-1 condenser leading to a runaway.
- **B.** Hit = the full causal chain in one line. Example: case k Z1, the recipe change pushing heat output past the fouled condenser, then the runaway and the manway release.

Seven rows depend on this choice: case k X1, X3, X6, Z2, Z4, case m X5 and case p X6.
