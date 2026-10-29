# Phase 7 plan — Cause library: slow and hidden failures

Status: approved 2026-10-29 (Bhargavi: "approved"; conflicts 1–3 answered yes).

Submission is today (2026-10-29). One PR, $0, no live calls, no schema change.

## Per item

### 7.1 Three cause rows — PR 1 `phase-7/cause-library`

- **Files:** `reference/causes.csv` (+3 rows, LF, UTF-8, frozen header); `reference/sources.md`
  (+1 line under "Project interpretations").
- **Tests first (7.2):**
  - `backend/tests/reference/test_reference_tables.py::test_causes_reference_existing_events`:
    count 26 → 29 (the existing IE / enum / `applies_to` checks cover the new rows).
  - `backend/tests/specialists/test_causes.py`, four new tests on the §9 example plant:
    - `test_corrosion_is_offered_on_a_line_batch_with_a_citable_line` (C27, pipe type);
    - `test_passing_control_valve_is_offered_only_with_a_citable_loop` (C28 offered when a control
      valve / loop / instrument is in `citable_ids`, not otherwise);
    - `test_unreviewed_change_is_offered_on_procedure_and_reactor_batches` (C29, operator type:
      offered wherever the context has packet IDs);
    - `test_new_causes_follow_r46_like_the_old_ones` (none offered to an empty context).
- **Branch / PR:** `phase-7/cause-library` from `origin/main` (d82a0bc), one PR, squash-merged by
  Bhargavi. Merges after `phase-5/f6-defects` if that is still open (no overlap; order only matters
  for the deploy).
- **Dependencies:** none new.
- **Found in the build (2026-10-29):** `contract/fixtures/` is generated from a $0 fake run and
  carries the reference version hashes, which change with `causes.csv`; the suite says so
  (`test_regenerating_the_fixtures_gives_the_same_files`). Regenerated with
  `scripts/make_fixtures.py` in the same PR. The schemas and `openapi.json` do not change.

### 7.3 Docs — same PR

- `docs/decisions.md`: three rows (post-mortem read; grader pass used; C27–C29 added after the
  benchmark). Row (b) needs Bhargavi's line: which `sheets_grader2` pass `results.md` used
  (`bench/heldout/` holds `sheets_grader2_firstpass`, `grader_ai_a_firstpass`,
  `grader_ai_b_firstpass`) and why.
- README results section: in the Phase 6 publish PR (§6.6), not here.

## Order

1. PR 1 `phase-7/cause-library` (rows + tests + decisions + sources note).
2. Phase 6 publish PR (existing plan G3): README results section quotes `results.md` and this
   phase's reason table, and says C27–C29 came after the benchmark and are untested on held-out
   cases. (This PR also removes the `bench/heldout/` ignore and publishes the cases, per the spec.)

## Conflicts (for Bhargavi)

1. **CLAUDE.md §5:** "Never tune prompts, rules or reference tables against anything other than dev
   cases D–H and the demo plants." Phase 6 spec, Not in scope: "Any change to the pipeline, prompts
   …, routing or reference data." This phase changes `causes.csv` because of K, M and P.
   **Question:** confirm the reading that the rule protects the benchmark, and that the benchmark is
   now closed (results generated, cases spent), so the change is allowed when it is dated, logged and
   labelled as after the benchmark, and never scored on K, M, P or Q.
2. **CLAUDE.md §10:** "Never add a row without a source … data comes from Cowork with its source."
   The cause rows are project defaults (sources.md), each mapped to an existing sourced
   initiating-event row. **Question:** do you approve the three mappings in the spec table
   (C27 → IE-PIPE-LEAK-S, C28 → IE-BPCS, C29 → IE-HE-RARE) in Cowork's place? If you want Cowork
   to source them, the PR waits.
3. **Phase 6 spec, Not in scope:** "Re-running a scored case." Unchanged here; the spec says K, M, P
   are never re-run on the new library. **Question:** confirm you will not ask for a re-run to show
   the fix "working" (there is no clean case left to run; Q is unrun but the budget is $0.92).

## Not doing

- `block_valve` failing type + "manual isolation valve passes" cause (contract change; no sourced
  frequency). "Fouled exchanger" cause (no sourced frequency). Both go in the README as next.
- Prompt or applicability edits; re-recording the demo; touching `bench/heldout/` or the held-out
  repo.

## Live calls and spend

None. Every step is $0.
