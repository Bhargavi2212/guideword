# Phase 7 — Cause library: slow and hidden failures

Status: approved 2026-10-29, after the held-out benchmark. Written at Bhargavi's request: "we see we
did a mistake, we go back, fix and build the best one out."

## Why

The held-out benchmark (`bench/heldout/results.md`, freeze `phase6-freeze-3`) scored Guideword 0 of
3 in the top 3 against 2 of 3 (checklist baseline) and 3 of 3 (one-prompt baseline). The run records
show one cause behind all three misses: each real root cause was a mechanism the 26-row cause
library (`reference/causes.csv`) does not name, so the specialists gave the right equipment and the
right consequence with a generic library cause instead of the real one:

| Case | Real mechanism | Nearest library cause Guideword used |
|---|---|---|
| K | Unreviewed recipe change (larger batch, all monomer charged up front) exceeded the fouled condenser's capacity | C07 loss of cooling water; C15 valve left wrong |
| M | Erosion-corrosion of the overhead line downstream of a wash-water injection point | C20 piping leak (no mechanism); C16 sampling step skipped |
| P | Steam passing through closed single valves into an idle column for 8 days | C01 control valve fails open; C15 bypass left open |

The hit rule needs the right mechanism, so each was a miss. The one-prompt baseline is free to name
any mechanism. `outside_library` exists, but the specialists chose a listed cause in every case.

The benchmark result is **not changed** by this phase. K, M and P are spent (their answers are
known); the library change is labelled as made after the benchmark, and `results.md` is published
as measured. This is the "fix" a judge should be able to read next to the result.

## Scope

### 7.1 Three cause rows (reference data, no schema change)

Add to `reference/causes.csv`, keeping the frozen header and the project-default source pattern
(sources.md row "Guideword project defaults": cause wording is ours; each row maps to an existing
sourced initiating-event frequency):

| id | cause | applies_to | failing_component_type | initiating_event_id |
|---|---|---|---|---|
| C27 | Internal corrosion or erosion thins the pipe wall (for example downstream of an injection or mixing point) | pipe | pipe | IE-PIPE-LEAK-S |
| C28 | Control valve passes (leaks through) when closed, so flow or heat reaches equipment meant to be isolated | pipe;heat_exchanger;reactor;vessel;tank;column;dryer;mixer | control_loop | IE-BPCS |
| C29 | Process change (recipe, batch size, feed, service of a connection) made without a hazard review | reactor;vessel;tank;mixer;column;heat_exchanger;pipe;procedure | operator | IE-HE-RARE |

`source` for each: `Guideword cause library (project default, engineer-editable; added 2026-10-29
after the held-out benchmark, see docs/decisions.md); frequency class from EGPC-PSM-GL-015 Rev 0
(Nov 2022) Annex A, citing CCPS Guidelines for Initiating Events and IPLs in LOPA (2015)`.

No question count changes: questions come from `applicability.csv`, not from causes. No prompt,
routing, applicability or schema change. The reference version hash changes, as it must.

### 7.2 Tests

- `test_reference_tables.py`: the row count becomes 29; every existing check (IE exists, type in the
  enum, `applies_to` valid) still passes.
- `backend/tests/specialists/test_causes.py` (new tests): on the §9 example plant,
  C27 is offered on a line-section batch whose context cites a line; C28 is offered only when a
  control valve, loop or instrument is citable; C29 is offered on a procedure-step batch and on a
  reactor batch; none of the three is offered where nothing of its type is citable (R46).
- `test_demo_plant.py`, `test_dev_cases.py`: unchanged and still green (plant files do not name
  causes).

### 7.3 Docs

- `docs/decisions.md`, three rows dated 2026-10-29: (a) the post-mortem read of the held-out keys and
  run records after grading, at Bhargavi's request, as a departure from CLAUDE.md §5 that could not
  affect a score; (b) which second-grader pass `results.md` used, and why (Bhargavi's words); (c)
  the three cause rows, why, and that they were added after the benchmark and never tested on K, M
  or P.
- `reference/sources.md`: one line under "Project interpretations" naming C27–C29 and the date.
- README: the results section (Phase 6 §6.6, publish PR) states the 0-of-3 result, the per-case
  reason above, and that C27–C29 were added afterwards and are untested on held-out cases.

## Not in scope

- Re-running or re-scoring K, M, P or Q; any edit to `bench/heldout/`.
- A `block_valve` failing-component type and a "manual isolation valve passes" cause: needs a schema
  enum change (contract PR) and a sourced frequency there is no EGPC/CCPS row for. Listed as next.
- A "fouled exchanger: capacity below design" cause: no sourced initiating event. Listed as next.
- Any prompt, routing or applicability change; any change to how `outside_library` is offered.

## Done when

- [ ] 7.1 rows merged with the source on every row; loaders pass.
- [ ] 7.2 tests written first and green; full suite, ruff, mypy green.
- [ ] 7.3 decisions rows and sources note merged; README text in the publish PR.
