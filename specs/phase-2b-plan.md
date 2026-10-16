# Phase 2b plan — hybrid ranking (R50)

Status: **draft, awaiting Bhargavi's approval** (mark `Status: approved <date>` here). No code until then.

Covers every item of `specs/phase-2b-hybrid.md`. Written after reading the spec, `PROJECT.md` §5, §11, §13, §15, the G2 entry and the code it touches (`gateway/client.py`, `orchestrator/{loop,view,tools}.py`, `runs/{start,machine,case}.py`, `ranking/{rank,severity}.py`, `specialists/{causes,context,run}.py`, `api/models.py`, `schema/{records,ids,enums}.py`, `bench/results.py`, `config/caps.yaml`, the ledger via `budget_status.py`).

Facts checked: no tag `contract-v1.2` exists locally or on GitHub (only `contract-v1`, `contract-v1.1`), so this bump takes **v1.2** and section-rejections (9a) moves to v1.3. The ledger shows phase 2 at **$3.41** ($3.40 test_5), `test_5` $0.60 left, `benchmark` $8.00 untouched; `benchmark` and `test_5` are both laptop uses, so moving between them keeps the laptop $19 and the per-environment sums.

## Per item

### 2b.5 Contract (first, so the frontend can start on the mock server)

- **Branch / PR:** `contract/hypotheses-tiers` → tag `contract-v1.2`.
- **Files:**
  - `schema/records.py`: `Hypothesis` (id, run_id, rank, mechanism, component_ids, failing_component_type, cause_id, cause_text, consequence, reason, question_ids, support_finding_ids, model_call_id).
  - `schema/ids.py`: `hypothesis_id(...)`.
  - `schema/enums.py`: `EventType.HYPOTHESIS_ADDED`, and `ShortlistTier` (`confirmed`, `also_found`, `unconfirmed`).
  - `api/models.py`: `ShortlistItem` gains `tier`, `hypothesis_id`, `hypothesis_rank` (the last two nullable; `tier` defaults so older fixtures stay valid).
  - `scripts/export_schemas.py`: register `Hypothesis`.
  - Regenerated: `contract/schemas/hypothesis.schema.json`, `enums.schema.json`, `api/shortlist.schema.json`, `contract/openapi.json`, `frontend/src/api/types.ts`.
  - Mock fixtures: `shortlist.json` items carry tiers (one of each); a hypothesis appears through the record endpoint fixture (`record_detail` for an `h:` ID); `events_page.json` gains one `hypothesis_added` event.
  - `PROJECT.md` §11 (the contract section): the `hypotheses` table, the `h:` ID form, the event type, the shortlist fields.
- **Tests first:**
  - `test_hypothesis_record_round_trips_and_rejects_unknown_fields`.
  - `test_hypothesis_id_is_built_from_content` (same inputs, same ID; mechanism normalised; component order ignored).
  - `test_shortlist_item_tier_fields_default_for_older_items`.
  - `test_fixture_shortlist_shows_each_tier`.
  - The existing exported-schema, openapi and fixture-validity tests then cover the rest.
- **Dependencies:** none.

### 2b.1 Whole-plant pass (`plant_screen`)

- **Branch / PR:**
  - prompt `prompts/plant_screen/v1.md` in `phase-2b/prompts`, which Bhargavi reviews;
  - code in `phase-2b/hybrid`.
- **Files:**
  - `guideword/screen/step.py`: the `PlantScreenStepper`.
  - `guideword/screen/schema.py`: the answer schema and its checks.
  - `runs/start.py`: the first step becomes `plant_screen`.
  - `runs/case.py`: the steppers.
  - `runs/store.py`: `add_hypothesis`, and the `hypotheses` read.
  - `runs/db.py`: the `hypotheses` table.
  - `config/routing.yaml`: `plant_screen: ultra`, prompt `plant_screen: v1`.
  - `config/caps.yaml`: `run.plant_screen_max_hypotheses: 12` and `max_tokens.plant_screen`; both enter `Run.caps` and the run-ID hash.
- **Input:** the confirmed plant record as JSON inside the untrusted-data delimiters, the cause library (see Q7) and the question kinds.
- **Validation:** see Q4–Q6. One retry with the errors. After the retry, the final answer is parsed with the schema; hypotheses that fail their checks are dropped and logged, and the rest are recorded.
- **Tests first:**
  - `test_unknown_id_is_retried_then_dropped_and_the_rest_stand`.
  - `test_failing_components_must_fit_the_type` (R46, whole plant).
  - `test_at_most_max_hypotheses`.
  - `test_one_call_per_run_and_it_counts_against_the_cap`.
  - `test_screen_failure_leaves_the_run_going_with_no_hypotheses`.
  - `test_input_holds_the_plant_and_no_case_or_key_text`.

### 2b.2 Linking (code only)

- **Branch:** `phase-2b/hybrid`.
- **Files:** `guideword/screen/link.py`. Links are computed after the analysis and stored on the hypothesis by an update; the record is otherwise never edited.
- **Rules:**
  - Questions link when their section, pair or environment contains a component ID. Chemicals come through equipment contents, as in R40.
  - Support is the spec's rules (a), (b) and (c).
- **Tests first:**
  - `test_pair_hypothesis_links_the_pair_question`.
  - `test_same_pair_same_cause_supports_a_different_cause_does_not`.
  - `test_component_overlap_is_required_for_section_questions`.
  - `test_links_are_deterministic`.

### 2b.3 Priority dispatch (the agent part)

- **Branch / PR:**
  - prompt `prompts/orchestrator/v2.md` in `phase-2b/prompts`;
  - code in `phase-2b/hybrid`.
- **Files:**
  - `orchestrator/view.py`: a `priority` block per hypothesis with its rank, component IDs, cause ID, linked open question IDs and supported yes/no. No mechanism or consequence text.
  - `orchestrator/tools.py`: `Dispatch.priority: bool = False`.
  - `orchestrator/loop.py`: `_eligible` puts linked questions first, in hypothesis rank and then ID order.
  - The run summary gains the linked-before-first-unlinked count.
- **Tests first:**
  - `test_view_priority_block_has_no_mechanism_or_consequence_text`.
  - `test_priority_dispatch_selects_linked_questions_first_in_rank_then_id_order`.
  - `test_explicit_question_ids_ignore_priority`.
  - `test_bulk_then_hard_no_repeat_and_deferral_still_hold_with_priority`.

### 2b.4 and 2b.4a Final ranking, tiers and the Phase 3 shortlist rule

- **Branch:** `phase-2b/hybrid`.
- **Files:**
  - `ranking/rank.py`: `tiered(...)`, with the fold applied within the tiers. A confirmed line folds its supporting scenarios, which never reappear under also found.
  - `runs/case.py`: the report carries `tiered` (the displayed list), `5a-plant` (the screen's own top 10) and `5b-from-hybrid` (2.6 order over all scenarios).
  - `bench/results.py`: new configs (Q10), and the scorer reads the displayed top N.
  - `PROJECT.md` §5 Step 6: the screen is the tiered list; the shortlist sorts by tier, then LOPA gap within a tier; chains take the tier of their highest member.
- **Tests first:**
  - `test_tier_order_confirmed_also_found_unconfirmed`.
  - `test_confirmed_line_folds_its_support_and_it_is_not_repeated`.
  - `test_5b_from_hybrid_equals_the_current_ranking_with_no_hypotheses`.
  - `test_scorer_reads_the_displayed_top_n_across_tiers`.
  - `test_unconfirmed_lines_are_flagged`.

### Run machine, replay and the $0 check

- **Branch:** `phase-2b/hybrid`.
- **Order of steps:** `plant_screen` → `analysis` → link (at analysis end) → `severity` → `ranked`.
- **Test helpers:** every test that builds steppers gains a screen stepper.
- **Tests first:**
  - `test_replay_reproduces_hypotheses_links_tiers_and_stop_point` (R45).
  - `test_case_d_end_to_end_on_the_fake_gateway_with_a_scripted_screen`. The scripted screen reply is generic and does not encode case D's real cause.

### Budget (2b, Budget)

- **Branch:** `phase-2b/hybrid`, one commit, logged in `decisions.md`.
- **Files:** `config/caps.yaml`:
  - `benchmark` 8.00 → 6.50;
  - `test_5` 4.00 → 5.50;
  - `phase_caps_usd."2"` 5.00 → 6.50.
- **Tests:** `test_config` values updated; the sums still equal `GLOBAL_BUDGET_USD` and the laptop allowance (the loader checks this).

## PROJECT.md edits (in this plan's PR, as the spec asks)

- **§5:**
  - Step 4 gains "Step 3b: the whole-plant pass" before the orchestrator.
  - Step 6 gets the tiered screen and the shortlist rule (2b.4a).
- **§13 Test #5:**
  - G2's result.
  - G2b: cases E and F; hybrid against 5A; the hit rule; Bhargavi's hand scores.
- **§15 gates:**
  - G2 recorded as failed (Oct 16).
  - G2b (Oct 17–18), with its "if it fails" line from the spec.
- **§11:** see Q2. It needs the record, the ID form, the event type, the table and the shortlist fields. I'd put the §11 lines in the contract PR, since that is the contract.

The wording of §5 Step 6 depends on Q1, so these edits are written into this PR after your answers, before merge.

## Order of pull requests

1. `docs/phase-2b-plan`: the spec, this plan and the PROJECT.md edits. Bhargavi approves.
2. `contract/hypotheses-tiers` (2b.5), then tag `contract-v1.2`. The frontend starts from it.
3. `phase-2b/prompts`: `plant_screen/v1` and `orchestrator/v2`. Bhargavi reviews.
4. `phase-2b/hybrid`: 2b.1, 2b.2, 2b.4, then 2b.3, the machine, the $0 check and the budget. Small commits, one PR, to save merge rounds on a one-day build (see Q11).
5. Bhargavi's runs: E hybrid, score, commit; F hybrid, score, commit; 5A on E and F, score, commit; `test5_results.py`; the G2b entry.

## Questions for Bhargavi (not resolved here)

1. **A model orders tiers 1 and 3.** "Confirmed … in hypothesis rank order" uses the model's ranking. `CLAUDE.md` §3 and §14 say risk ranking is code and never a model's, and `PROJECT.md` §5 Step 6 is titled "Ranking (code, with reasons from Ultra)". Choose one:
   - (a) Amend `CLAUDE.md` §3/§14 and §5 Step 6 in this PR to say: "the whole-plant pass's hypothesis rank, a model judgment with a reason, orders the confirmed and unconfirmed tiers; code computes ratings, links, tiers and the fold". This is recommended, because it is the spec as written, and it says plainly what the model does.
   - (b) Within each tier, order by the spec 2.6 code key, so the model decides only membership. This keeps the rule, but drops the ordering that made 5A work.
2. **`PROJECT.md` §11** lists every record, ID form, event type and table, and the spec's edit list (§5, §13, §15) leaves it out. Add the §11 lines in the contract PR?
3. **The hypothesis ID.** The spec gives `h:<run>:<rank>:<h(normalised mechanism, sorted component_ids)>`. Findings and the other run records leave the run ID out, because they are stored per (run ID, record ID), and a run ID holds `:` and the attempt number, so the same hypothesis would get a different ID on attempt `:2`. Use `h:<rank>:<h(...)>` instead?
4. **The failing-component type.** The output has `cause_id` but no failing-component type, and R46 needs a type to check the components. A library cause has one, but an outside-library cause has none. Add `failing_component_type` to the schema, required and equal to the library cause's type when one is given?
5. **"Cause valid for the component type".** R7 decides validity per question, and a hypothesis has none. I read it as: the library cause exists, and every component fits the type under R46 over the whole plant (operator causes name the plant's steps or jobs). Correct?
6. **Dropping only the bad hypotheses.** The gateway marks a whole answer invalid after its one retry. To keep the good hypotheses, the validator lists every bad one on the first attempt (that is the retry with the error). After the retry, code parses the final content with the schema and drops the hypotheses that fail their checks. A cut-off answer is still never parsed, and a structurally invalid one is dropped whole. Agree?
7. **The cause library sent to the screen.** Send all 26 causes, or only those the whole plant can support (R46, so C10 regulator and anything without a fitting ID drops out)? The second is recommended, for consistency with the specialists.
8. **Support rule (c), "both outside-library", ignores the cause text,** so any outside-library finding on the linked components supports any outside-library hypothesis. That's loose but it is the spec; keep it?
9. **Contract scope for v1.2.** The bump covers `Hypothesis`, the `hypothesis_added` event type, `ShortlistTier`, the three `ShortlistItem` fields and the fixtures. `Run.step` is free text, so `plant_screen` needs no contract change. Anything else the frontend needs?
10. **Config names in `results.md`.** Use `hybrid` for the run's displayed tiered list, `5a-plant` and `5b-from-hybrid` for the two $0 views, and keep `5b` for the D and G rows. Should `5a-plant` and `5b-from-hybrid` get hand-score rows, or are they automatic only? The spec says "same scoring".
11. **One code PR or three?** `CLAUDE.md` asks for a PR per task. With a one-day build I propose one code PR with small commits per item. Or should 2b.1/2b.2, 2b.4 and 2b.3 go as three PRs?
12. **Budget:** move $1.50 from `benchmark` to `test_5`, and raise the phase 2 cap to $6.50? The spec's reason for the cap rests on held slices. The gateway in fact holds only the estimates of calls in flight, not slices. The raise is still prudent: $3.41 spent plus about $1.55 is about $4.96.
13. **Orchestrator v2 changes only the `priority` option** (and nothing else), so the cache keeps every specialist answer, but every orchestrator call changes. Agree to keep v2 that narrow?

## Not doing

- Any validity rule (R7, R40, R46, R47), severity (R48, R49), LOPA, admission or replay behaviour, beyond adding the new step.
- Re-running D or G, or scoring anything against them.
- PR 12b (kill test #4 and the four-tier comparison), PRs 9a, 9 and 10, `budget/ledger-g2.jsonl`, the `g2` tag, the video script.
- The frontend: that's its own worktree, and the contract PR gives it what it needs.

## Live calls and spend

| Step | Use | Expected cost |
|---|---|---|
| $0 fake case D run | — | $0 |
| E hybrid (cap 1.20) | test_5 | ≈ $0.75 (+ $0.02 screen) |
| F hybrid (cap 1.20) | test_5 | ≈ $0.75 (+ $0.02) |
| 5A on E and F | test_5 | ≈ $0.03 |
| **Total** | | **≈ $1.55**, above the $0.60 left unless Q12 is approved |
