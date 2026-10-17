# Phase 2b plan — hybrid ranking (R50)

Status: approved 2026-10-16 (Bhargavi), with changes C1–C5 below folded in.

Covers every item of `specs/phase-2b-hybrid.md`. It includes Bhargavi's answers to Q1–Q13, her review points A–E, and gaps G1–G15 found on two rereads (G16–G24 found while building and in review). Each gap is settled here as a plan decision, marked **(plan)**, for her to keep or change.

Facts checked:

- No tag `contract-v1.2` exists, locally or on GitHub, so this bump takes **v1.2**. Section rejections (9a) moves to v1.3.
- The ledger shows phase 2 at **$3.41** ($3.40 of it test_5), with $0.60 of `test_5` left and `benchmark` untouched at $8.00.
- `benchmark` and `test_5` are both laptop uses, so moving money between them keeps the $19 laptop allowance and the per-environment sums.

## The decisions this plan builds on

| # | Decision (Bhargavi, 2026-10-16) |
|---|---|
| Q1 | (a), narrow wording: "the whole-plant pass's hypothesis rank, a model judgment with a reason, orders only the confirmed and unconfirmed tiers; code computes tier membership, ratings, links, the fold, LOPA gap and all of 'also found'; the model never sets a number." `hybrid-codeorder` is also written, at $0. The model-ordered list (`hybrid`) is the scored G2b config. |
| Q2 | The `PROJECT.md` §11 lines go in the contract PR. |
| Q3 | ID `h:<rank>:<h(normalised mechanism, sorted component_ids)>`, with `run_id` as a field. |
| Q4 | `failing_component_type` is required. When a library cause is given, it must equal that cause's type. |
| Q5 | Validity = the library cause exists, and every component fits the type under R46 over the whole plant (operator causes name the plant's steps or jobs). |
| Q6 | The validator lists every bad hypothesis on the first attempt (the retry with the error). After the retry, code parses the final answer with the schema and drops the hypotheses that fail. A cut-off answer is never parsed. With zero survivors, the run continues with no hypotheses, and this is logged. |
| Q7 | The screen gets the R46-filtered cause list: only causes the whole plant can support. |
| Q8 | Support rule (c) is kept, but outside-library support also requires the same `failing_component_type`. Every confirmed line shows its supporting finding's text. The R50 entry states what "confirmed" means. |
| Q9 / D | Contract v1.2 also: `ShortlistItem.target_kind` gains `"hypothesis"`; an optional `ShortlistItem.hypothesis`; event types `hypothesis_added` and `hypothesis_dropped`. |
| Q10 / C | Configs `hybrid` (hand-scored), and `hybrid-codeorder`, `5a-plant` and `5b-from-hybrid` (automatic only). |
| Q11 | One code PR, small commits, each green. |
| Q12 | Budget: `benchmark` 8.00 → 6.50, `test_5` 4.00 → 5.50, phase 2 cap 5.00 → 6.50. |
| Q13 | Orchestrator v2 changes only the `priority` option. |
| A | Question links are computed and stored when the hypothesis is created, from the plant and sections only. Support is computed on demand from the current findings and is never stored or updated, like `rank.py`. The view's `supported` flag uses it. The Hypothesis record is immutable. |
| B | External- and utility-type hypotheses link no questions for priority, because they are plant-wide. Their support is a finding with the same cause on the same component ID. Both are tested. |
| E | `support_finding_ids` moves to `ShortlistItem`, computed. The Hypothesis record keeps `question_ids`. |

## Changes at approval (Bhargavi, 2026-10-16)

| # | Change |
|---|---|
| C1 | `Hypothesis` gains optional `chemical_ids` (validated: plant chemicals). Question links use `component_ids` ∪ `chemical_ids` ∪ the equipment and valves named by any step or job in `component_ids` (the reverse of R40). Support (b): component overlap **or** the same chemicals. Tested on case G's shape: C14 on a step with chemicals `KOH-EMULSIFIER` and `SIH` links, and is supported by, a `pair:KOH-EMULSIFIER:SIH` C14 finding. This replaces G12. |
| C2 | 2b.4a: the LOPA top N counts only confirmed and also-found lines; unconfirmed lines get no LOPA and are listed after. |
| C3 | G3 changed: on confirmed lines the automatic scorer reads only the hypothesis text (`<mechanism> — <consequence>`), as for `5a-plant`. The hand sheet shows both texts. |
| C4 | The G2b rules (G5, G14) add the grader fallback, fixed now: if Bhargavi can't score, a fresh Claude session is given only each case's `actual_event` and the ten lines (no repo, no design, no other configs), and its scores are recorded as such. |
| C5 | `max_tokens.plant_screen`: 12288. |

G1, G2, G4, G6, G7 and G8 are kept as written.

## Gaps found on rereading, settled here (plan)

| # | Gap | Plan decision |
|---|---|---|
| G1 | A confirmed hypothesis can have several supporting scenarios, and the spec says the line shows "the supporting scenario's severity and likelihood". | **(plan)** The line shows its **lead** scenario: the supporting scenario first in the spec 2.6 code order (rating, severity, frequency, protection, ID). The others fold under it. |
| G2 | One scenario can support two hypotheses. | **(plan)** It counts as support for each, so both are confirmed. It is **displayed** only under the highest-ranked hypothesis it supports, so it never appears twice. A confirmed hypothesis whose every supporting scenario is shown under a higher one stays a confirmed line with its own text, and its folded list names those scenarios by ID ("shown under h:…"). |
| G3 | What text the scorer and the hand sheet read on a tiered line. | **Changed by C3.** Automatic scorer: on confirmed and unconfirmed lines, the hypothesis text (`<mechanism> — <consequence>`), as for `5a-plant`; on also-found lines, the finding text, as now. Hand sheet: confirmed lines show both the hypothesis text and the lead finding's text. IDs are never matched. |
| G4 | `hybrid-codeorder` ordering of tier 3, whose hypotheses have no rating. | **(plan)** Tier 1 by its lead scenario's 2.6 key; tier 3 by hypothesis ID. Tier 3's order is reproducible but carries no risk meaning, and the report says so. |
| G5 | The spec says the G2b rules are "fixed before any run", but nothing records them yet. | **(plan)** This PR adds a `decisions.md` entry with the G2b rules (cases E and F; scored config `hybrid`; the hit rule; Bhargavi's hand scores; the pass condition; what happens on failure), dated before any E or F run. |
| G6 | Q1(a) amends `CLAUDE.md`. | **(plan)** This PR amends `CLAUDE.md` §3 and §14 with the Q1 wording, and `PROJECT.md` §5 Step 6 with the same wording. |
| G7 | `runs/store.py` refuses event types it doesn't list (`EMITTED_EVENT_TYPES`). | **(plan)** `hypothesis_added` and `hypothesis_dropped` are added to it in the code PR, with a test. |
| G8 | My first draft linked questions at analysis end, which contradicts A. | **(plan)** Linking runs inside the `plant_screen` step, when each hypothesis is created; support is computed only when read. |
| G9 | My run order (E hybrid, F hybrid, then 5A on both) didn't follow the spec's order. | **(plan)** Follow the spec's order, per case: hybrid run → hand-score its top 10 → commit → 5A run → hand-score → commit. Do E, then F, then `test5_results.py`. |
| G10 | The replay manifest holds only the plain ranked list (`gateway/replay.py`), so a replay can't check the tiers. | **(plan)** The manifest gains the hypotheses and the `hybrid` tiered lines (ID, tier, lead finding). The replay test compares them, along with the stop point. |
| G11 | The answer's ranks and repeats are unchecked. | **(plan)** Structural checks on the whole answer:<br>• ranks are unique and run 1 to n;<br>• no two hypotheses share an ID;<br>• field limits: `mechanism`, `consequence` and `reason` at most 300 characters each, `cause_text` at most 200.<br>A failure here invalidates the answer (the retry path). Gaps left in the ranks by later per-hypothesis drops are kept, and display order follows rank. |
| G12 | "The same chemicals" for pair and environment links and support was undefined. | **Replaced by C1** (`chemical_ids` on the hypothesis; links through components, chemicals, and the equipment and valves of its steps and jobs). |
| G13 | Two lines are undefined: the text of a `5a-plant` line, and the order of a `hybrid-codeorder` confirmed line whose scenarios all show under a higher one. | **(plan)** A `5a-plant` line is `<mechanism> — <consequence>`. Such a confirmed line is ordered by its lead scenario's 2.6 key, even though the lead is displayed under the higher line. |
| G14 | The G2b rules entry (G5) doesn't spell out what it must contain. | **(plan)** The entry states:<br>• the cases, E and F;<br>• the per-case order (G9);<br>• the scored config, `hybrid`;<br>• the hit rule, with partials not passing;<br>• R38: a `stopped_cap` hybrid run is reported, not scored;<br>• hand scores are Bhargavi's alone, and Cowork may explain the rule but does not propose scores;<br>• the pass condition: a hit in the top 3 on at least one of E and F, and on as many cases as 5A;<br>• the recognition caveat;<br>• if it fails: stop, report honestly, and re-plan Phase 3;<br>• the grader fallback (C4). |
| G15 | Two gaps:<br>• the spec's "Cowork does not" review the screen prompt isn't in the plan;<br>• the spec's run summary line has no place in `run_case.py`. | **(plan)**<br>• The prompt PR says it is reviewed by Bhargavi only.<br>• `run_case.py` prints the linked-before-first-unlinked count, and the case report carries it. |
| G16 | Found while building 2b.2: sections list only equipment and lines, so a hypothesis naming a control loop, instrument, valve or relief device would link no section question and could never be confirmed through one. | **(plan, build)** A component also reaches what it is attached to: a valve its line (`on_line_id`), an instrument its equipment or line (`on_id`), a control loop what it acts on (`acts_on_id`) and where its sensor and final element sit, a relief device what it protects (`protects_id`). The same goes for the valves a step names. |
| G17 | Found while building 2b.1: a dev plant file names its case in `plant_id` and in every `source` (notes, chemicals) and `provenance` value (e.g. `cases/dev/source/case_g_batch_plant.md`), but the spec says the screen gets no case names. | **(plan, build)** The screen's copy of the plant leaves out `plant_id`, `provenance` and every `source`; the notes' text stays word for word. The specialists' contexts are outside 2b's scope and unchanged; flagged to Bhargavi. |
| G18 | Found while building 2b.3: two gaps.<br>• `batches()` re-sorts a dispatch by section and ID, so admission would still reach the linked questions last and a deferral could leave them unanswered.<br>• "Linked questions answered before the first non-linked dispatch" was undefined when one dispatch holds both. | **(plan)**<br>• A priority dispatch (`priority: true`, list left out) batches with `keep_order`: section groups in order of first appearance, members in the priority order. Batch sizes and section grouping are unchanged, and every other dispatch batches exactly as before.<br>• Each dispatch event carries `priority`, `linked_answered` and `unlinked_sent` (first answers only; an `unsure` re-answer counts 0 for both). The report's count adds `linked_answered` over the dispatches in order, up to and including the first with `unlinked_sent` > 0: one dispatch's batches run together, so that dispatch's linked answers count. |
| G19 | Found in Bhargavi's review of the PR: the view cuts each agent's open list to the first IDs, so a linked question can be out of sight and the model would have to guess its agent from the ID. | **(Bhargavi, 2026-10-16)** Each `priority` entry groups its linked open question IDs by agent. Acceptance on the $0 case D run: every linked question is answered by the first dispatch that sends an unlinked one, and that dispatch leads with them. G18 kept as built. |
| G20 | Found in Bhargavi's review: no injection test for the screen prompt. Writing one showed that a plant note holding `</plant>` closed the data block, because JSON leaves `<` and `>` as they are. | **(Bhargavi, 2026-10-16)** The screen writes the plant record with `as_data` (`<`, `>`, `&` escaped as `<` …; it reads back to the same value). A $0 test plants an instruction in two notes, with and without a closing tag: it stays inside the block, and the same answer validates, links and drops exactly as without it. The specialist, severity and orchestrator data blocks embed JSON the same way and are not changed here (open question). |
| G21 | Found in Bhargavi's review: before any paid E or F run, a check that the screen prompt's new lines carry no key words, and one screen-only live call. | **(Bhargavi, 2026-10-16)** `scripts/prompt_leak_check.py` (written against the key formats only; counts and line numbers unless `--show`), which Bhargavi runs on `plant_screen/v1` against `test5a/v1`. `scripts/screen_check.py` runs only the `plant_screen` step on one plant and prints validity and counts, never hypothesis text, ranks or IDs; Bhargavi runs it once on case H at a $0.05 cap. No E or F run until G19, G20 and G21 pass. |
| G22 | Follows G20: the specialist, severity and orchestrator data blocks embedded JSON the same way, so plant notes, step text, model-written consequences and tool results could close their blocks. | **(Bhargavi, 2026-10-16)** Every data slot is written with `as_data`, before E and F. A structural test reads every `render()` call and fails on any slot that skips `as_data` unless it is listed as code-only with its reason, so a later slot is covered too. The test 5A `package` is the one text slot kept as written, so 5A on E and F reads what it read on D and G; a package holding a `<package>` tag is refused before any call. Old D and G response caches no longer match; their committed outputs stay the record. |
| G23 | The H screen check (v1, then v2) dropped most hypotheses on the failing-type rule; on H the dryer and tempering cannot be named, and nothing on them can. | **(Bhargavi, 2026-10-16)** Built: A (the retry names only what each item offers) and B (Q6 amended: keep the attempt with more valid hypotheses). **Adopted 2026-10-16 (Bhargavi), before any run on it, on the structural count of equipment the strict rule leaves unnameable even with A (D 1, E 0, F 2, G 0, H 2; F's `EVAPORATORS` and `VACUUM-SYSTEM` in an evaporator-area plant); built as written below, with `failing_component_type` kept required (no contract change), the section overlap on the hypothesis's own IDs only, A's misfit message and `nameable_on` removed, and `fitting()` kept as prompt guidance (plant_screen v3).** Originally drafted as the fallback: a hypothesis's `component_ids` must be real plant IDs of any kind (equipment of every type, lines, valves, instruments, steps, jobs, locations); the failing-type check is dropped for hypotheses only and kept for findings. Support is unchanged: a finding still has to pass R46, answer a linked question, overlap the components or chemicals, and share the library cause (or both be outside-library with the same type). Cost: an outside-library hypothesis on a vessel is confirmed by any outside-library finding of the same type on it, which is looser; hence fallback, not plan. Files it would touch: `screen/schema.py` (`hypothesis_problem`), `prompts/plant_screen/v3.md` (drop the can_fail_as rule for hypotheses), `screen/link.py` (the type in `_same_cause` for outside-library support), and their tests. |
| G24 | Found in review after G23: a library cause of a plant-wide type (C07 is `utility_cooling`) on an item such as F's `EVAPORATORS` was treated as plant-wide, so it linked nothing and needed a finding naming the item, which R46 never allows: it could never be confirmed. | **(Bhargavi, 2026-10-16)** Plant-wide only when every component really is of that type per `fitting()` (locations for `external`, utilities of the matching kind for the utility types); otherwise it links and is supported like any hypothesis (own section, same cause). Applied once, when links are made; `supports()` reads "plant-wide type and no links". No prompt or contract change. |

## Per item

### 2b.5 Contract (first, so the frontend can start on the mock server)

- **Branch / PR:** `contract/hypotheses-tiers`, then tag `contract-v1.2`.
- **Files:**
  - `schema/records.py`: the immutable `Hypothesis` record, with `id`, `run_id`, `rank`, `mechanism`, `component_ids` (non-empty), `chemical_ids` (optional, C1), `failing_component_type`, `cause_id`, `cause_text` (outside library only), `consequence`, `reason`, `question_ids` and `model_call_id`.
  - `schema/ids.py`: `hypothesis_id(rank, mechanism, component_ids)` → `h:<rank>:<h(normalised mechanism, sorted component_ids)>`, built with `normalise_text`.
  - `schema/enums.py`: `EventType.HYPOTHESIS_ADDED`, `EventType.HYPOTHESIS_DROPPED`, and `ShortlistTier` (`confirmed`, `also_found`, `unconfirmed`).
  - `api/models.py`: `ShortlistItem` gains:
    - `target_kind` `"hypothesis"`;
    - `tier` (default `also_found`, so older items stay valid);
    - `hypothesis_id` and `hypothesis_rank` (nullable);
    - `hypothesis` (an optional `Hypothesis`);
    - `support_finding_ids` (default `[]`).
  - `scripts/export_schemas.py`: registers `Hypothesis`.
  - Regenerated: `contract/schemas/hypothesis.schema.json`, `enums.schema.json`, the shortlist schema, `contract/openapi.json`, `frontend/src/api/types.ts`.
  - Mock fixtures:
    - `shortlist.json`: one item per tier, with a confirmed item that has a hypothesis and its support;
    - `record_detail.json`: an `h:` record;
    - `events_page.json`: one `hypothesis_added` and one `hypothesis_dropped` event.
  - `PROJECT.md` §11 (Q2): the `hypotheses` table, the `h:` ID form, the two event types, and the shortlist fields.
  - `docs/decisions.md`: the 9a tag moves to v1.3.
- **Tests first:**
  - `test_hypothesis_record_is_strict_and_round_trips`.
  - `test_hypothesis_needs_components_and_the_library_type` (Q4).
  - `test_hypothesis_id_is_built_from_content` (same input, same ID; the mechanism normalised; component order ignored; no run in the ID).
  - `test_shortlist_item_new_fields_default_for_older_items`.
  - `test_fixture_shortlist_shows_each_tier_and_a_hypothesis_item`.
  - The existing schema, openapi and fixture tests cover the rest.

### 2b.1 Whole-plant pass (`plant_screen`) and question links

- **Branch / PR:**
  - `prompts/plant_screen/v1.md` in `phase-2b/prompts`, which Bhargavi reviews and Cowork does not (G15);
  - the code in `phase-2b/hybrid`.
- **Files:**
  - `guideword/screen/schema.py`: the answer schema and its checks (Q4, Q5).
  - `guideword/screen/step.py`: `PlantScreenStepper`. It builds the input, calls the gateway, validates (Q6), creates hypotheses with their question links, and records `hypothesis_added` and `hypothesis_dropped` events.
  - `guideword/screen/link.py`:
    - question links (A, B), from the run's section snapshot;
    - support on demand (Q8, B);
    - the lead scenario (G1).
  - `runs/start.py`: the first step is `plant_screen`.
  - `runs/case.py`: the steppers.
  - `runs/db.py` and `runs/store.py`: the `hypotheses` table, `add_hypothesis` (refused if the ID is already stored), the `hypotheses()` read, and `EMITTED_EVENT_TYPES` (G7).
  - `config/routing.yaml`: `plant_screen: ultra`, and prompt `plant_screen: v1`.
  - `config/caps.yaml`: `run.plant_screen_max_hypotheses: 12` and `max_tokens.plant_screen: 12288` (C5), both in `Run.caps` and the run-ID hash.
- **The screen's input:**
  - the confirmed plant record as JSON inside the untrusted-data delimiters;
  - the R46-filtered cause list (Q7);
  - the question kinds.

  No case name, package or key.
- **Tests first:**
  - `test_unknown_id_is_retried_then_dropped_and_the_rest_stand`.
  - `test_zero_survivors_leave_the_run_going_with_no_hypotheses_logged`.
  - `test_failing_components_must_fit_the_type_over_the_whole_plant`.
  - `test_library_cause_type_must_match`.
  - `test_at_most_max_hypotheses`.
  - `test_ranks_unique_one_to_n_and_no_duplicate_ids_or_the_answer_is_retried` (G11).
  - `test_one_call_per_run_counted_against_the_cap`.
  - `test_input_holds_the_plant_and_no_case_package_or_key_text`.
  - `test_hypothesis_added_and_dropped_events`.

### 2b.2 Links and support (code only)

- **Branch:** `phase-2b/hybrid`.
- **Question links** (stored at creation):
  - a hypothesis links to every question whose section, pair or environment contains one of: its `component_ids`; its `chemical_ids`; or the equipment and valves named by any procedure step or planned job in its `component_ids` (the reverse of R40) (C1);
  - external- and utility-type hypotheses link none (B).
- **Support** (computed when read, never stored) requires all three of:
  - (a) the finding answers a linked question;
  - (b) its failing components overlap the hypothesis's components, **or** its question's chemicals (pair or environment) are among the hypothesis's `chemical_ids` (C1);
  - (c) its cause ID matches, or both causes are outside-library with the same failing-component type (Q8).

  External and utility hypotheses: a finding with the same cause on the same component ID (B).
- **Tests first:**
  - `test_pair_hypothesis_links_the_pair_question`.
  - `test_same_pair_same_cause_supports_a_different_cause_does_not`.
  - `test_outside_library_support_needs_the_same_type`.
  - `test_component_overlap_is_required_for_section_questions`.
  - `test_external_hypothesis_links_no_questions_and_is_supported_by_the_same_cause_on_the_same_location`.
  - `test_utility_hypothesis_same_for_the_same_utility`.
  - `test_support_follows_the_current_findings_and_the_record_never_changes`.
  - `test_case_g_shape_a_c14_step_hypothesis_with_its_chemicals_links_and_is_supported_by_the_pair_finding` (C1): on `cases/dev/case_g.json`, C14 on `P-G-CHARGE-2` with chemicals `KOH-EMULSIFIER` and `SIH` links `pair:KOH-EMULSIFIER:SIH` and is supported by a C14 finding on it; the test first checks those IDs exist.
  - `test_links_through_the_equipment_and_valves_of_a_step` (C1).
  - `test_unknown_chemical_id_is_dropped_with_the_hypothesis` (C1).
  - `test_links_are_deterministic`.

### 2b.3 Priority dispatch

- **Branch / PR:**
  - `prompts/orchestrator/v2.md` (Q13, narrow) in `phase-2b/prompts`;
  - the code in `phase-2b/hybrid`.
- **Files:**
  - `orchestrator/view.py`: a `priority` block, one entry per hypothesis, with its rank, component IDs, cause ID, linked open question IDs and `supported` (on demand, A). No mechanism or consequence text.
  - `orchestrator/tools.py`: `Dispatch.priority: bool = False`.
  - `orchestrator/loop.py`: with `priority` set and the list omitted, linked open questions come first, in hypothesis rank and then ID order, then the other open questions.
  - The dispatch payload carries the count of linked questions answered before the first unlinked dispatch; the case report carries it and `run_case.py` prints it (G15).
- **Tests first:**
  - `test_view_priority_block_has_no_mechanism_or_consequence_text`.
  - `test_supported_flag_follows_the_findings`.
  - `test_priority_selects_linked_first_in_rank_then_id_order`.
  - `test_explicit_question_ids_ignore_priority`.
  - `test_bulk_then_hard_no_repeat_and_deferral_still_hold_with_priority`.

### 2b.4 and 2b.4a Tiers, the four views, and the Phase 3 shortlist rule

- **Branch:** `phase-2b/hybrid`.
- **Files:**
  - `ranking/tiers.py` (or an addition to `ranking/rank.py`): `tiered(...)`.
    - Confirmed: in hypothesis rank order, each line showing its lead scenario with the rest folded under it (G1, G2).
    - Also found: the R48 fold of every scenario not displayed under a confirmed line, in the 2.6 order.
    - Unconfirmed: in hypothesis rank order, flagged "not confirmed by the checks — engineer to review".
    - `hybrid-codeorder` uses the same membership in code order (G4).
  - `runs/case.py`: the report carries `hybrid` (displayed), `hybrid-codeorder`, `5a-plant` (the screen's own top 10, in its order) and `5b-from-hybrid` (the R48 folded list over every scenario, unchanged code).
  - `bench/results.py`:
    - the four configs, plus `5a`;
    - the scorer reads each config's displayed top N, with line text per G3;
    - the hand sheet gets rows for `hybrid` only (Q10).
  - `PROJECT.md` §5 Step 6 (this PR): the screen is the tiered list; the LOPA top `lopa_top_n` counts only confirmed and also-found lines, and unconfirmed lines get no LOPA and are listed after (C2). The shortlist sorts by tier, then by LOPA gap within a tier; gap never lifts an also-found line above a confirmed one; chains take the tier of their highest-ranked member.
- **Tests first:**
  - `test_tier_order_confirmed_also_found_unconfirmed`.
  - `test_lead_scenario_is_first_in_code_order_and_the_rest_fold_under_it`.
  - `test_a_scenario_supporting_two_hypotheses_shows_once_under_the_higher`.
  - `test_also_found_never_repeats_a_confirmed_lines_scenarios`.
  - `test_codeorder_keeps_membership_and_orders_by_code`.
  - `test_5b_from_hybrid_equals_the_current_ranking_with_no_hypotheses`.
  - `test_scorer_reads_the_hypothesis_text_on_confirmed_lines_and_the_sheet_shows_both` (G3, C3).
  - `test_hand_sheet_rows_only_for_hybrid`.

### Run machine, replay and the $0 check

- **Branch:** `phase-2b/hybrid`.
- **Files:** `gateway/replay.py`: the manifest gains the hypotheses and the tiered lines (G10).
- **Steps:** `plant_screen` → `analysis` → `severity` → `ranked`.
- **Test helpers:** every test that builds steppers gains a screen stepper. This is a mechanical change to the helpers; no test changes what it checks.
- **Tests first:**
  - `test_replay_reproduces_hypotheses_links_tiers_and_stop_point` (R45; the manifest carries the hypotheses and the tiered lines, G10).
  - `test_case_d_end_to_end_on_the_fake_gateway_with_a_scripted_screen`. The scripted screen reply is generic and does not encode case D's real cause.

### Budget (Q12)

- **Branch:** `phase-2b/hybrid`, in one commit, with a `decisions.md` line.
- **Files:** `config/caps.yaml`, with the three values above. `test_config` is updated, and the loader still checks that every sum equals `GLOBAL_BUDGET_USD` and the laptop allowance.

## This plan's PR (`docs/phase-2b-plan`)

- The spec and this plan.
- **`CLAUDE.md` §3 and §14:** the Q1 wording (G6).
- **`PROJECT.md`:**
  - §5: the whole-plant pass before the orchestrator, and Step 6 per 2b.4a with the Q1 wording;
  - §13: Test #5 records G2's result and adds G2b;
  - §15: G2 recorded as failed (Oct 16), and G2b (Oct 17–18) with its "if it fails" line.
- **`docs/decisions.md`** (G5):
  - R50 (option A), with what "confirmed" means (Q8), the recognition caveat, and the 5A input difference;
  - the G2b rules, fixed before any run.

## Order of pull requests

1. `docs/phase-2b-plan`. Bhargavi approves and merges it.
2. `contract/hypotheses-tiers`, then tag `contract-v1.2`. The frontend starts from it.
3. `phase-2b/prompts`: `plant_screen/v1` and `orchestrator/v2`. Bhargavi reviews them.
4. `phase-2b/hybrid`: one PR in small green commits.
   1. Links and support.
   2. The screen step.
   3. Tiers and the views.
   4. Priority dispatch.
   5. The machine and replay.
   6. The $0 check.
   7. The budget.
5. Bhargavi's runs, in the spec's per-case order (G9):
   1. Case E: hybrid run; hand-score its top 10; commit; 5A run; hand-score; commit.
   2. Case F: the same.
   3. `test5_results.py`.
   4. The G2b entry.

## Not doing

- Any change to validity rules (R7, R40, R46, R47), severity (R48, R49), LOPA, admission or replay, beyond adding the new step.
- Re-running D or G, or scoring against them.
- PR 12b, PRs 9a, 9 and 10, `budget/ledger-g2.jsonl`, the `g2` tag, the video script.
- The frontend, which has its own worktree and builds from the contract PR.

## Live calls and spend

| Step | Use | Expected cost |
|---|---|---|
| $0 fake case D run | — | $0 |
| E hybrid (cap 1.20) | test_5 | ≈ $0.77 |
| F hybrid (cap 1.20) | test_5 | ≈ $0.77 |
| 5A on E and F | test_5 | ≈ $0.03 |
| **Total** | | **≈ $1.57**, within the $2.10 left once the budget move (Q12) is in |
