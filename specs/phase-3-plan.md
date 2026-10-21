# Phase 3 plan — chains, LOPA, shortlist, recommendations, review

**Status:** approved 2026-10-18

Covers every item of `specs/phase-3.md` (approved 2026-10-18). Read before writing: `specs/phase-3.md`, `PROJECT.md` §5 Steps 4–8, §10, §11 (records, IDs, enums), §12, §16, §18; `CLAUDE.md`; and the code each item touches (named per item below). The questions for Bhargavi are in **Questions**; each has a recommended answer, and nothing that depends on one is built before it is answered.

## What exists today (so the plan builds on it, not around it)

- **Records:** `Chain`, `LopaRecord` (with `severity_class`, `complete`, `missing_fact_ids`, `layers: list[LayerCredit]`, `modifiers`, `gap`), `LayerCredit`, `Recommendation` and `Override` are in `schema/records.py` (contract v1). Their tables exist in `runs/db.py` (`chains`, `lopa_records`, `recommendations`, `overrides`); no writer method stores them yet.
- **IDs:** `ids.chain_id`, `lopa_id`, `recommendation_id` and `override_id` exist and follow §11.
- **Enums:** `Agent.CONNECTOR`, `EventType.CHAIN_ADDED`, `LOPA_DONE`, every `OverrideAction` exist. `run_extended` does not (contract v1.4).
- **Config:** `run.lopa_top_n: 10`, `run.connector_max_input_tokens: 80000`; routing jobs `connector`, `lopa_argument`, `recommendation` → Ultra. There is no `max_tokens` entry, prompt or batch size for them, and no `connector_max_chains`.
- **Run machine:** steps `plant_screen → analysis → severity → ranked`; `SeverityStepper` hands over to `ranked`. Every step builds `RunBudget(run.id, cap_spent_usd, spend_cap_usd)`.
- **Likelihood:** `ranking/likelihood.py` `likelihood()` is the one frequency function; C20 maps to `IE-PIPE-LEAK-S` by its `causes.csv` row; there is no flag channel apart from `note` (used for unrated reasons).
- **Ranking:** `ranking/tiers.py` builds the R50 tiers; a line is a scenario (R48) with a lead finding (`TieredLine.lead`) and the rest folded.
- **API:** the Phase 3 routes (`shortlist`, `worksheet`, `overrides`, `export.xlsx`, `export/coverage.json`, `export/run.json`) are mock-only (`NOT_BUILT_PHASE` 3). `api/mock.py` has `WORKSHEET_COLUMNS` and `worksheet_xlsx()` (openpyxl, already a dependency).
- **Phase constant:** `PHASE = "2"` is hard-coded in `run_case.py`, `run_test5a.py`, `screen_check.py`, `four_tier.py`, and `API_RUN_PHASE = "2"` in `api/app.py`.

## Decisions P3-1…P3-7

The spec gives a recommendation for each, and Bhargavi approved the spec. PR 0 records each in `docs/decisions.md` as "approved with the spec, 2026-10-18" (Q1 asks to confirm that this is what the approval meant).

| # | Decision (as recommended in the spec) | Where it lands |
|---|---|---|
| P3-1 | Chains, chain severity, LOPA and recommendations are fixed code steps after the analysis; `propose_chains` and `run_lopa` leave the §5 tool table; the `finish` guard does not wait for LOPA. | Run machine (PR 5); PROJECT.md §5 Step 4 (PR 7). The `finish` guard code already checks only open questions, so no guard code changes. |
| P3-1b | Existing finished runs are extended in place (same run ID; step → `chains`; status → `running`). | `runs/extend.py`, `scripts/extend_run.py` (PR 5). |
| P3-2 | `Run.post_spend_cap_usd`, not hashed, default 0; the gateway check uses it in post-analysis steps. | Contract (PR 1); post budget (PR 5). |
| P3-3 | No conditional modifiers in Phase 3; each LOPA record lists those not applied, "no plant fact or rule". | LOPA engine (PR 4). Needs a field: Q2. |
| P3-4 | C20: `size_mm` > 150 → `IE-PIPE-LEAK-L`, else `S`; missing size → `S`, flagged "size assumed ≤ 150 mm". | `likelihood()` (PR 3). |
| P3-5 | C14–C17 stay `IE-HE-MONTHLY`, flagged "task frequency assumed — engineer to confirm". | `likelihood()` (PR 3). |
| P3-6 | "Confirmed" unchanged in Phase 3. | Nothing built; recorded as a known limit (PR 0). |
| P3-7 | Claim the second $25 grant; set the Phase 6 per-case cap from the measured E/F cost. | Bhargavi's step; a decisions line (PR 0). The measured costs: E $1.66 (two legs), F $0.94. |

## Pull requests, in order

| # | Branch | Items | Depends on |
|---|---|---|---|
| 0 | `docs/phase-3-plan` | This plan (approved); P3-1…P3-7 lines; Phase 2 close-out (spec §"Phase 2 close-out"); `phase_caps_usd."3": 2.50` | — |
| 1 | `contract/v1.4` | Contract v1.4 (spec 3.8 plus Q2), fixtures, regenerated schemas, OpenAPI and frontend types; tag `contract-v1.4` | PR 0 |
| 2 | `phase-3/prompts` | `connector/v1`, `lopa_argument/v1`, `recommendation/v1`, `severity_chain/v1` (Q5); routing entries and `max_tokens`; Bhargavi reviews; leak check | PR 1 |
| 3 | `phase-3/likelihood` | P3-4, P3-5 in `likelihood()`, with a flag channel | PR 0 |
| 4 | `phase-3/lopa-engine` | Pure LOPA code: candidates, credit, arithmetic, code-only LOPA; hand-worked example 1 (delivered) | PR 1, PR 3 |
| 5 | `phase-3/post-analysis` | The four steps, the post budget, extension, the phase flag, replay manifest, the $0 eight-step run | PR 2, PR 4 |
| 6 | `phase-3/review-export` | Shortlist, worksheet, overrides, the three exports, built for real | PR 5 |
| 7 | `phase-3/demo-lopa` | Williams Geismar committed and validated, hand-worked example 2, PROJECT.md updates | PR 4; Cowork's plant file (Oct 19) and example 2 |
| — | Bhargavi | Extend D, E, F, G; the demo plant run; `bench/phase3/*.json`; `budget/ledger-g3pre.jsonl` | PR 5–7 |

PRs 3 and 4 can be built while PR 2's prompts are in review. PR 7 waits only on Cowork's files.

---

## Per item

### PR 0 — `docs/phase-3-plan`: the plan, the decisions and the Phase 2 close-out

- **Files:** `specs/phase-3-plan.md` (approved); `specs/phase-3.md` status line set to `Status: approved 2026-10-18` (Q1); `docs/decisions.md`; `specs/phase-2.md`; `config/caps.yaml` and `backend/tests/test_config.py`.
- **`docs/decisions.md`:**
  - P3-1…P3-7, one dated line each.
  - **Correction of the G2b deviation entry:** it says "E was hand-scored by Bhargavi afterwards". `bench/test5/hand_scores.csv` shows all 20 of E's rows with `grader:` reasons, the same as F's. The correction is a new dated line that names the error and states the provenance from the CSV; the old line is not rewritten.
  - **Phase 2 routing (spec close-out):** "Routing unchanged for Phase 3 (Lightning bulk, Super hard, Ultra orchestrator and severity), decided on validity and cost; four-tier accuracy not hand-scored." The table it rests on: Super 46/50 valid, Lightning 23/50, Ultra 34/50, Nano 32/50.
  - **Case H:** not run in Phase 2 or Phase 3: recognised (kill test #4) and about $1.5 a run (spec, Done when).
- **`specs/phase-2.md`:**
  - box 2.11 (routing) ticked, citing the decisions line;
  - `ledger-g2` and `g2`: ticked (both exist on `main`: #62 and the `g2` tag);
  - "A 5B run on every dev case": annotated "H not run (recognised; cost)" and left unticked;
  - "CI green on `main`": ticked only when Bhargavi confirms it (I have no CI access).
- **`config/caps.yaml`:** `phase_caps_usd."3": 2.50` (not hashed). Test: `test_config` reads the new cap.
- **Tests:** only the config test; the rest is documents.

### PR 1 — `contract/v1.4`

- **Files:** `schema/records.py`, `schema/enums.py`, `api/models.py`, `contract/fixtures/*`, regenerated `contract/openapi.json`, `contract/schemas/*`, `frontend/src/api/types.ts` (R39 rule: only the types file); `PROJECT.md` §11 (records, events); `docs/decisions.md`.
- **Spec 3.8 items:**
  - `Chain.severity_class: SeverityClass | None = None`, `Chain.severity_reason: str | None = None`, mirroring `Finding`.
  - `Run.post_spend_cap_usd: float = 0.0` (≥ 0), kept out of `Run.inputs()`, so the run ID does not change. Old stored runs load with 0.
  - `EventType.RUN_EXTENDED = "run_extended"`.
  - **Override `new_value` shapes,** as models used to validate `OverrideRequest` by action:
    - `change_credit` → `ChangeCreditValue {layer_id: str, credited: bool}`, target `lopa:<target>`;
    - `change_severity` → `ChangeSeverityValue {severity_class: SeverityClass}`, target a finding or chain ID;
    - `accept`, `reject` → `null`;
    - `edit` → `{field: value}`, allowed only on `recommendation.action`, `finding.consequence` and `section.purpose`; any other field → 422;
    - `answer` → `{text}`, only on an `eng:` question, which then counts as checked on read (Q17, answered).
  - `ShortlistItem.lopa`: checked, not changed. `LopaRecord` already carries `severity_class` and the full `layers` list. A test pins that.
  - **Fixtures:**
    - a chain with severity;
    - a complete LOPA record and an incomplete one naming a missing fact;
    - a layer with reason "not argued — no credit";
    - a recommendation;
    - a shortlist item with each.
- **Additions this plan proposes (Q2), so every number and every claim traces to a record (CLAUDE.md §3):**
  - **`LopaRecord.model_call_id`:** the Ultra call that argued the layers; null on code-only LOPA.
  - **`LopaRecord.flags: list[str]`:** "frequency assumed", "size assumed ≤ 150 mm", "task frequency assumed — engineer to confirm", "code-only LOPA: layers not argued". Today only a `frequency_assumed` boolean exists.
  - **`LopaRecord.modifiers_not_applied: list[{kind, reason}]`** (P3-3): one entry per modifier kind in `modifiers.csv` (today `ignition_probability`, `explosion_given_ignition`, `vulnerability`, `time_at_risk`), reason "no plant fact or rule", as Cowork's example 1 states (M1).
  - **`LayerCredit.applies: bool | None` and `LayerCredit.argument: str | None`:** Ultra's yes or no and its reason, apart from code's credit `reason`. Null when not argued.
- **Tests first:**
  - `test_chain_without_severity_still_validates` (additive);
  - `test_run_post_spend_cap_is_not_hashed` (the same inputs with two post caps give one run ID);
  - `test_old_run_record_loads_with_post_cap_zero`;
  - `test_change_credit_and_change_severity_values_validate_and_bad_ones_are_refused`;
  - `test_edit_only_on_the_three_allowed_fields`, `test_answer_only_on_an_engineer_question`, `test_accept_and_reject_take_null` (model-level; the 422s are PR 6);
  - `test_lopa_fixture_complete_and_incomplete`;
  - `test_shortlist_item_lopa_carries_severity_and_every_layer`;
  - the existing contract test regenerating `openapi.json` and schemas.
- **Tag:** `contract-v1.4` after merge (Bhargavi). The PR description tells the frontend session to rebase.

### PR 2 — `phase-3/prompts` (Bhargavi reviews; Cowork does not)

- **Files:** `prompts/connector/v1.md`, `prompts/lopa_argument/v1.md`, `prompts/recommendation/v1.md`, `prompts/severity_chain/v1.md` (Q5); `config/routing.yaml` (prompt versions; job `chain_severity: ultra`); `config/caps.yaml` (`max_tokens` for `connector`, `lopa_argument`, `recommendation`, `chain_severity`; `connector_max_chains: 10`; `lopa_batch_size: 5`; `recommendation_batch_size: 5`; Q9, Q12); `backend/tests/gateway/test_prompts.py`, `test_config.py`.
- **Each prompt:**
  - asks for its fixed JSON schema with a reason field;
  - every data slot goes through `as_data`;
  - no number is asked for (CLAUDE.md §3).
  - **`connector/v1`:** the scenario lines (ID, cause, consequence, components, severity), the plant record and the plant's fact IDs as data (G7); asks for at most `{{max_chains}}` chains of ordered links, each an existing finding ID or plant fact ID, with a description and a reason; says code rejects any other link.
  - **`lopa_argument/v1`:** per line, its scenario and the candidate layers code listed (ID, kind, description, what it protects, and its `protection_layers.csv` row's `layer`, `scenarios` and `conditions_text`, never the `pfd`; G19); asks for each "applies to this scenario: yes/no, with a reason"; never a PFD, never a new layer.
  - **`recommendation/v1`:** per line with gap > 1: its scenario, the layers and why each was or wasn't credited, the gap as an order of magnitude; asks for one action and a reason; no numbers.
  - **`severity_chain/v1`:** the same severity classes as `severity/v2`, for a chain: its description, its links in words (finding consequence lines, fact values), with a reason.
- **Caps placement:** `max_tokens`, `connector_max_chains` and the batch sizes go in the hashed `run:` block. They change answers (R18), and they change run IDs only for runs started after this PR. Extended runs keep their stored caps and read these values from the current config (spec 3.6), and the `run_extended` event records the values used.
- **Tests first:**
  - `test_<prompt>_fills_its_placeholders_and_asks_for_the_schema`, one per prompt;
  - `test_every_data_slot_is_written_with_as_data` (the existing guard covers the new renders automatically);
  - `test_config` with the new jobs and caps (the loader already refuses `max_tokens` for jobs not in routing).
- **Bhargavi's step:** review; run `scripts/prompt_leak_check.py` on each new prompt against `test5a/v1` ($0).

### PR 3 — `phase-3/likelihood` (P3-4, P3-5)

- **Files:** `ranking/likelihood.py`; `backend/tests/ranking/test_likelihood.py`.
- **Change:**
  - **The C20 event choice:** for a C20 finding on a line, `size_mm` > 150 → `IE-PIPE-LEAK-L`; ≤ 150 → `IE-PIPE-LEAK-S`; missing → `S`.
  - **The flag channel:** `Likelihood` gains `flags: tuple[str, ...]`. A missing size adds "size assumed ≤ 150 mm (`<line>.size_mm`)"; C14–C17 add "task frequency assumed — engineer to confirm".
  - **The event IDs** come from `initiating_events.csv`. The threshold 150 is a value in logic, so it goes in `config/caps.yaml` `ranking.pipe_leak_large_above_mm: 150` (hashed with ranking, as it changes ratings).
  - **Several failing lines:** each line's length uses its own event.
- **Effect on existing records:** none on stored findings. The ranked lines of D–G are computed on read, so a C20 line on a > 150 mm line re-rates one band lower when re-read.
- **Tests first:**
  - `test_c20_above_150_mm_uses_the_large_leak_event`;
  - `test_c20_without_size_uses_small_and_flags_the_assumption`;
  - `test_c14_to_c17_flag_task_frequency_assumed`;
  - `test_screening_and_lopa_read_the_same_likelihood` (with PR 4: the LOPA initiating frequency equals the screening frequency).

### PR 4 — `phase-3/lopa-engine` (pure code)

- **Files:** `lopa/__init__.py`, `lopa/candidates.py`, `lopa/credit.py`, `lopa/engine.py`; `backend/tests/lopa/` with `fixtures/example_1.json` (Cowork's hand-worked example 1, committed as written, with its arithmetic shown) and the tests.
- **`candidates(line, plant, sections)`:**
  - the safeguards with a `layer_type` whose `protects_id` is in the line's section objects or failing components;
  - every relief device whose `protects_id` is in the same set.
  - **Pair and environment questions** have no section, so only the failing components count. For a chain, the union over its finding links (Q8). In ID order.
- **`credit(layer, line, plant, ref, applies)` decides, in this order, with the first rule that refuses giving the reason:**
  1. **Not argued** (code-only, or Ultra left it out): "not argued — no credit".
  2. **Ultra says it does not apply:** "does not apply: <Ultra's reason>".
  3. **Safeguard with no `layer_type`:** no credit.
  4. **Any of the safeguard's `component_ids` among the cause's failing components:** no credit.
  5. **Independence (Q3, answered):** where the layer's `protection_layers.csv` row requires it, no credit when the failing control loop's part is in the safeguard's `component_ids`: `controller_id` (independent logic), `sensor_id` (independent sensor), `final_element_id` (independent final element). The reason names the shared part.
  6. **Relief device:**
     - the `relief_kind` row for its `kind`;
     - any inlet valve `normal_position: closed` → no credit "inlet valve <id> closed";
     - else any inlet valve open and not `locked` → `pfd_if_isolatable`, "inlet valve <id> unmanaged";
     - else `pfd`.
  7. **Otherwise:** the `pfd` of the safeguard's `layer_type` row.
- **`lopa_record(line, ...)`:**
  - **Severity:** the line's lead finding's `severity_class`, or the chain's (unrated → no LOPA, listed).
  - **Initiating frequency:** from `likelihood()`, the same function as screening. A missing fact → `complete: false`, naming it.
  - **Arithmetic:** mitigated = initiating × Π credited PFD; tolerable from `tolerable_frequencies.csv`; gap = mitigated ÷ tolerable. No modifiers, each listed in `modifiers_not_applied` (P3-3).
  - **ID:** `lopa:<lead finding ID or chain ID>`.
  - **Rounding** happens only at display (orders of magnitude), never in the stored numbers.
- **Code-only LOPA:** the same function with no arguments. Every candidate is "not argued — no credit", flagged "code-only LOPA: layers not argued".
- **Tests first** (all spec acceptance lines for the engine):
  - `test_example_1_variant_a_both_layers_apply_gap_10`, `test_example_1_variant_b_relief_does_not_apply_gap_1000`, `test_example_1_variant_c_code_only_gap_10000`: each reads `fixtures/example_1.json` and matches every checked value (candidates, the excluded SG-VENT, initiating frequency and L4, each layer's credit and PFD, mitigated, tolerable, gap, flags, the four modifier kinds not applied) with a relative tolerance of 1e-9;
  - `test_shared_component_gets_no_credit`;
  - `test_shared_logic_solver_gets_no_credit_where_required` (`requires_independent_logic`);
  - `test_shared_sensor_gets_no_credit_where_required` (`IPL-HUMAN`: an alarm on the same sensor as the failing loop gets no credit);
  - `test_shared_final_element_gets_no_credit_where_required` (`requires_independent_final_element`);
  - `test_an_independence_flag_the_row_does_not_set_does_not_refuse_credit` (`IPL-HUMAN` with the loop's final element in its components is still credited);
  - `test_open_unlocked_inlet_valve_gets_pfd_if_isolatable`;
  - `test_all_inlet_valves_locked_open_gets_pfd`;
  - `test_closed_inlet_valve_gets_no_credit`;
  - `test_no_layer_type_gets_no_credit`;
  - `test_per_metre_year_without_length_is_incomplete_naming_the_fact_and_no_default`;
  - `test_code_only_lopa_marks_every_layer_not_argued`;
  - `test_ultra_never_adds_a_layer` (an argued layer ID not in the candidates is refused);
  - `test_modifiers_not_applied_are_listed`;
  - `test_gap_is_mitigated_over_tolerable`;
  - `test_engine_is_pure` (the same inputs give the same record).
- **Dependency:** Cowork's example 1 is in the working tree at `backend/tests/lopa/fixtures/example_1.json` (§9 example plant, unchanged; three variants, every check shown). It is committed as is in this PR, and the three tests above are written from it before any engine code (spec: the fixture is independent of the code). It is not part of PR 0 (G18).
- **`LayerCredit.pfd`** holds a value only on a credited layer; a refused layer has `pfd: null` and its reason (M2, as the fixture).

### PR 5 — `phase-3/post-analysis`

- **Files:** `chains/connector.py` (step, schema, validator); `chains/severity.py` (chain severity step); `lopa/step.py` (full and code-only LOPA step, Ultra argument batches); `recommend/step.py`; `runs/post_budget.py`; `runs/extend.py`; `runs/store.py` (`add_chain`, `fill_chain_severity`, `add_lopa`, `add_recommendation`); `runs/case.py` (`steppers_for` gains the four steps; the report gains `shortlist`, `chains`, `lopa`, `recommendations`); `ranking/severity.py` (`next_step="chains"`); `gateway/replay.py` (manifest gains chains, LOPA and recommendations, as G10); `scripts/extend_run.py`; `scripts/run_case.py`, `run_test5a.py`, `screen_check.py`, `four_tier.py` (`--phase`, default the current phase from Q15); tests.
- **The run machine:** `plant_screen → analysis → severity → chains → chain_severity → lopa → recommendations → ranked`. Each step resumes on its own, and each writes before returning.
- **Post budget (P3-2):**
  - post steps use `RunBudget(run.id, post_spent, post_spend_cap_usd)`, where `post_spent` is the sum of `cap_cost_usd` over the run's model calls whose job is a post-analysis job (Q19);
  - a refusal → `stopped_cap` via the existing `stop_for_refusal`, analysis records untouched;
  - the analysis and its severity reserve read the analysis cap as today.
- **The chains step (3.1):**
  - **Input:** one line per scenario (R48) as the spec lists, in R50 tier order; cut to `connector_max_input_tokens`, logging how many were left out.
  - **The call:** one Ultra call, schema-validated.
  - **Code validation:**
    - every link a finding ID or plant fact ID of this run or plant, at least 2 links, at least one a finding; else rejected, logged with its reason, and listed;
    - flagged, never filtered (Q6, answered): more than two finding links whose failing components don't overlap → "possibly more than two independent failures". "Misused terms" are not checked by code; the engineer reads the description;
    - at most `connector_max_chains`.
  - **Stored** with `ids.chain_id`; `chain_added` event.
- **The chain severity step:**
  - chains in their own batch (`severity_chain/v1`); `fill_chain_severity` once;
  - **initiating frequency:** the first finding link's `likelihood()`; the other links are conditions, never multiplied;
  - **tier:** a chain takes the tier of its highest-ranked member line (3.1, 6.3).
- **The LOPA step (3.2):**
  - **Full LOPA** on the top `lopa_top_n` lines across the confirmed and also-found tiers, in display order, plus every chain: Ultra argument batches of `lopa_batch_size`, then the engine.
  - **Code-only LOPA** on every other S4–S5 line (Q10).
  - Unconfirmed lines and S1–S3 lines outside the top N: no LOPA.
  - `lopa_done` event per record.
- **The recommendations step (3.4):** lines with a complete LOPA and gap > 1 (Q12), in batches; `rec:<target>:<h(action)>`.
- **Extension (P3-1b), `runs/extend.py` `extend(runs, run_id, post_cap)`:**
  - **Refused when** the run isn't `finished`, or a `chains` step already finished (a `step_finished` event for `chains`).
  - **Otherwise,** in one write: `post_spend_cap_usd` set, step → `chains`, status → `running`, and a `run_extended` event listing the current config values and prompt versions the new steps use.
  - **Never touched:** `caps`, `prompt_versions`, `routing_config` or any earlier record.
  - **D and G, which predate R50:** every line "also found", labelled "pre-R50 run".
  - **A run whose records fail to load on the new code** is skipped, and the reason printed and recorded.
- **`scripts/extend_run.py <run_id> --post-cap 0.30 --phase 3 --use development [--name case_e]`:** extends, drives the run to a terminal status, and writes `bench/phase3/<name>.json` (the shortlist, chains, LOPA records, recommendations).
- **Tests first** (spec acceptance lines):
  - `test_extension_makes_no_analysis_calls_and_keeps_every_earlier_record_byte_identical` (a $0 fake run finished on the Phase 2 steps, then extended; the run ID unchanged; only `chains` onward in `transport.sent`; a byte diff of every earlier table row);
  - `test_extension_refuses_an_unfinished_run_and_a_run_already_extended`;
  - `test_full_eight_step_fake_run_replays_identically` (R45, including chains, LOPA and recommendations);
  - `test_post_cap_stops_a_post_step_with_the_analysis_intact`;
  - `test_analysis_cap_behaviour_unchanged` (the existing admission and severity-reserve tests stay green unchanged);
  - `test_chain_validator_rejects_unknown_links_and_facts_only`;
  - `test_chain_takes_the_tier_of_its_highest_member`;
  - `test_chain_initiating_frequency_is_the_first_finding_links`;
  - `test_a_chain_is_never_ranked_down_for_needing_two_failures` (a chain's gap uses only its first finding link's frequency; no factor for the other links);
  - `test_a_post_step_cap_stop_is_reported_not_scored` (R38: `bench/phase3/<case>.json` carries `stopped_cap` and the scorer does not score it);
  - `test_code_only_lopa_makes_no_model_call`;
  - `test_a_line_with_no_lopa_stays_on_the_shortlist_with_its_reason_and_s4_s5_are_flagged` (Bhargavi, 2026-10-19, on PR 4 choice 4: a `NoLopa` line — no severity, or no frequency and no missing fact — is never dropped; it stays on the shortlist with its reason, and an S4–S5 line without LOPA is flagged on its card);
  - `test_pre_r50_run_extends_with_every_line_also_found_and_labelled`;
  - `test_scripts_take_the_phase_from_the_flag`.

### PR 6 — `phase-3/review-export`

- **Files:** `review/shortlist.py`, `review/overrides.py`, `review/worksheet.py`; `api/live.py`, `api/app.py` (the six routes leave `NOT_BUILT_PHASE`); `runs/store.py` (`add_override`); tests in `backend/tests/api/` and `backend/tests/review/`.
- **The shortlist (3.3):**
  - tier first (R50); within a tier, gap largest first, incomplete LOPA after complete, flagged; gap never crosses tiers; chains inside their tier;
  - built as contract v1.2 `ShortlistItem`s (`target_kind` finding, chain or hypothesis);
  - `unsure` from the lead finding's confidence; `evidence` empty.
- **Overrides (3.5):**
  - `POST /runs/{id}/overrides` validates `new_value` by action (PR 1 shapes), and stores an `Override` with `replaces` set to the latest override on that target;
  - 403 on a recorded run;
  - views apply overrides on read: a credit change recomputes mitigated frequency and gap; a severity change recomputes tolerable and gap; model records are never edited.
- **The worksheet:**
  - one row per finding (unfolded), plus one row per question without a finding (not credible, failed or open), with its status;
  - columns as `WORKSHEET_COLUMNS`; `origin` and override state (Q14).
- **Exports:** `export.xlsx` (the existing `worksheet_xlsx`), `export/coverage.json` (the existing `coverage()`), `export/run.json` (`RunDump`).
- **Tests first:**
  - `test_shortlist_order_is_tier_then_gap_and_gap_never_crosses_tiers`;
  - `test_incomplete_lopa_after_complete_within_a_tier`;
  - `test_overrides_applied_on_read_and_model_records_unchanged`;
  - `test_override_on_a_recorded_run_is_403`;
  - `test_edit_of_any_other_field_is_422` and `test_answer_on_a_non_engineer_question_is_422`;
  - `test_answered_engineer_question_counts_as_checked_on_read`;
  - `test_change_credit_recomputes_gap_on_read`;
  - `test_change_severity_recomputes_tolerable_and_gap`;
  - `test_worksheet_has_one_row_per_finding_and_per_question_without_one`;
  - `test_gap_is_shown_as_an_order_of_magnitude` (the worksheet's `lopa_gap` and the shortlist display text, "about 1 in 10,000 years"; the stored numbers are not rounded);
  - `test_xlsx_has_the_step_8_columns_one_row_per_worksheet_row_overrides_applied`;
  - `test_exports_match_the_contract`;
  - `test_the_built_routes_left_not_built_phase`.

### PR 7 — `phase-3/demo-lopa` and PROJECT.md

- **Files:**
  - `cases/demo/williams_geismar.json` (Cowork's, committed as delivered);
  - `backend/tests/cases/test_demo_plant.py`;
  - `backend/tests/lopa/fixtures/example_2.json` (Cowork's hand-worked reboiler);
  - `PROJECT.md` (§5 Step 4 tool table and `finish` guard; §5 Step 6.1/6.2 lines and modifiers; §11 records and run steps; §12 screen 4 "ranked by tier, then LOPA gap"; §16 open items closed);
  - `docs/decisions.md`.
- **Tests first:**
  - `test_demo_plant_validates_with_no_errors`;
  - `test_demo_plant_has_the_reboiler_its_heat_source_and_a_relief_device_with_a_closed_inlet_valve`;
  - `test_example_2_matches_the_hand_worked_numbers_exactly` (relief inlet valve closed → no credit, gap shown).
- **Rule:** facts come only from Cowork's file, each sourced or "assumed". I add no plant fact. Validation warnings are reported, not fixed by me.

---

## Order and dependencies

1. PR 0 (docs). PR 1 (contract) right after, so the frontend can start.
2. PR 2 (prompts; Bhargavi reviews), PR 3 (likelihood) and PR 4 (engine) in parallel. Cowork's example 1 is delivered, so PR 4 can start now (its tests first).
3. PR 5 (steps and extension) after PRs 2 and 4. Then Bhargavi extends D–G (live).
4. PR 6 (review and export) after PR 5.
5. PR 7 when Cowork delivers the plant (Oct 19); then Bhargavi runs the demo plant (live).
6. `budget/ledger-g3pre.jsonl` snapshot (Bhargavi).

## Questions (please answer before approval)

| # | Question | Recommended answer |
|---|---|---|
| Q1 | Does approving the spec approve P3-1…P3-7 as recommended, so PR 0 records them as decided, and may PR 0 set the spec's status line (it still says "draft")? | Yes to both. |
| Q2 | Add to contract v1.4, beyond the spec's list: `LopaRecord.model_call_id`, `LopaRecord.flags`, `LopaRecord.modifiers_not_applied`, `LayerCredit.applies` and `LayerCredit.argument`? Without them the argument's model call, the P3-3/4/5 flags and Ultra's yes/no have no field, so they would not trace (CLAUDE.md §3). | Yes, all five, additive with defaults. |
| Q3 | "Shares a logic solver with the failing control loop": in plant terms? And the table's `requires_independent_sensor` and `requires_independent_final_element` flags, which the spec doesn't mention? | A safeguard shares a logic solver when the failing loop's `controller_id` is in its `component_ids`. Apply the sensor and final-element flags the same way (the loop's `sensor_id` or `final_element_id` in the safeguard's `component_ids` → no credit where the row requires it), since the table already requires them. If you want only what the spec names, I'll leave those two flags unused and note it. |
| Q4 | A failing component that is a control loop: should the shared-component rule also count the loop's parts (sensor, controller, final element) as failing components? | No; Q3's flags cover the parts, row by row. |
| Q5 | Chain severity: a new prompt `severity_chain/v1` (job `chain_severity`), or chains fed through `severity/v2`? v2 is built around a finding's question, cause and evidence. | New prompt; your review. |
| Q6 | "Misused terms" in a chain: the spec flags them but defines no check. | Code flags only what it can check: more than two finding links whose failing components don't overlap ("more than two independent failures"). "Misused terms" left to the engineer, noted as not checked by code. |
| Q7 | A chain's "first finding link" is the first in the model's order (stored in `Chain.links`), not in the sorted ID? | Yes, the model's order; the ID stays sorted. |
| Q8 | Candidate layers for a chain? | The union over its finding links' sections and failing components. |
| Q9 | LOPA argument batch size? | 5 lines per call (`lopa_batch_size`, caps.yaml). |
| Q10 | Code-only LOPA on "every other S4–S5 line": lines outside the top N in the confirmed and also-found tiers only (not unconfirmed); and S1–S3 lines outside the top N get none? | Yes to both. |
| Q11 | A line whose lead finding has no severity (not assessed): no LOPA, listed with "no severity"? | Yes; it is never given a default class. |
| Q12 | Recommendations only where the LOPA is complete and gap > 1; an incomplete record (gap unknown) gets none, flagged? Batch size? | Yes; batches of 5 (`recommendation_batch_size`). |
| Q13 | The video's "no credit — inlet valve closed": exact reason wording? | "no credit — inlet valve <id> closed". |
| Q14 | Worksheet: on a folded scenario, do all member findings show the line's LOPA gap and recommendation, or only the lead? And "Status": the override state (open, accepted, rejected, edited) or the question status? | All members show the line's gap and recommendation, marked "(scenario)". Status shows the override state, and for question-only rows the question status. |
| Q15 | The phase for spend: the scripts get `--phase`; what default, and what about `API_RUN_PHASE = "2"` in `api/app.py` (runs started through the API)? | Default `3` in every script; the API's constant becomes `"3"` in PR 5, a one-line change recorded in decisions. No new setting. |
| Q16 | `extend_run.py` use? | `development` (spec: Live calls). |
| Q17 | `new_value` shapes for `accept`, `reject`, `edit` and `answer`? PR 1 must fix them. | `accept`, `reject`: `null`. `edit`: `{field: value}` for a named text field of the target (a recommendation's `action`, a finding's `consequence`). `answer`: `{text}` on an `eng:` question, which then counts as checked on read. |
| Q18 | The replay manifest gains chains (ID, links), LOPA records (ID, gap) and recommendations (ID), as G10 did for hypotheses? | Yes. |
| Q19 | Post spend: derived from the call records of the post-analysis jobs (no new counter), so the gateway check is `post_spent + estimate ≤ post_spend_cap_usd`? | Yes; no new Run field beyond `post_spend_cap_usd`. |
| Q20 | A new run (not extended): where does its `post_spend_cap_usd` default come from? | `run_case.py --post-cap`, default `run.post_spend_cap_usd: 0.30` in caps.yaml (hashed, like `run_spend_cap_usd`, so only new runs' IDs move); the Run field holds the value used, unhashed. |
| Q21 | Cowork's example 1 needs a plant: the §9 example (`example_mixing_unit.json`, with `TIC-1` and an alarm), or a plant of its own? | The §9 example, so the fixture needs no new plant file. |

### Answers (Bhargavi, 2026-10-18)

| # | Answer |
|---|---|
| Q2 | Yes, all five, additive with defaults. |
| Q3 | Yes: all three independence flags; the loop's `controller_id`, `sensor_id` or `final_element_id` in the safeguard's `component_ids` → no credit where the row requires that independence; one test each, including `IPL-HUMAN`. |
| Q5 | New `severity_chain/v1` (job `chain_severity`); `severity/v2` untouched; Bhargavi reviews. |
| Q6 | Recommended, flag worded "possibly more than two independent failures". |
| Q15 | `--phase` on every script, default 3; `API_RUN_PHASE` becomes `"3"` in PR 5, recorded in decisions. |
| Q17 | `accept`/`reject`: `null`. `edit`: `{field: value}` only on `recommendation.action`, `finding.consequence`, `section.purpose`, else 422. `answer`: `{text}` only on an `eng:` question, which then counts as checked on read. |
| Q19 | Yes: `post_spent` from the post-analysis jobs' call records, no new counter; the check is `post_spent + estimate <= post_spend_cap_usd`. |
| Q21 | The §9 example plant for example 1. Delivered: `backend/tests/lopa/fixtures/example_1.json`, variants A (gap 10), B (gap 1000), C (gap 10000). |
| G1, G7 | Kept with changes (in the gap table): a relief device credited by override uses the full `pfd` and the view records "engineer asserts inlet valve managed"; the connector also gets the plant's `PlantFact` IDs, and a fact link must match one exactly. G1 confirmed as built: the view's layer reason carries "engineer asserts inlet valve managed" with the override ID; the `Override` record keeps only the engineer's own reason. |
| G2–G6, G8–G16 | Kept. |
| Q1, Q4, Q7–Q14, Q16, Q18, Q20 | As recommended. |

## Gaps found on the reread (plan decisions, marked **(plan)**: keep or change)

| # | Gap | Settled as | Lands in |
|---|---|---|---|
| G1 | A `change_credit` that credits a layer code refused had no defined PFD. | **(Bhargavi, kept with a change)** The engineer's credit uses the layer's own row: the safeguard's `layer_type` row `pfd`; for a relief device, its `relief_kind` row's **full `pfd`** (never `pfd_if_isolatable`), and the view's layer reason records "engineer asserts inlet valve managed" with the override ID. A layer with no row (no `layer_type`) cannot be credited by override: 422 "no protection_layers row". Tests: `test_change_credit_uses_the_layers_row_pfd`, `test_change_credit_on_a_relief_device_uses_the_full_pfd_and_records_the_assertion`, `test_change_credit_on_a_layer_without_a_row_is_422`. | PR 6 |
| G2 | No status for an override on an unknown target or layer. | **(plan)** Unknown target ID in the run → 404; `change_credit` with a `layer_id` not in that LOPA record → 422; `change_severity` on anything but a finding or chain → 422. Tests, one each. | PR 6 |
| G3 | What happens when a post-analysis call fails (invalid twice, cut off, error). | **(plan)** The run goes on; only a cap refusal stops it. Connector fails → no chains, logged. Chain severity fails → the chain is unrated, gets no LOPA, listed "no severity". A LOPA argument batch fails → its lines get code-only LOPA, flagged "argument call failed". Recommendations fail → none, flagged. Tests: `test_each_post_step_failure_leaves_the_run_going_with_a_flag`. | PR 5 |
| G4 | A new run whose analysis ended at the severity reserve with questions open still reaches the post-analysis steps before `ranked` stops it (R38). | **(plan)** The post steps run anyway (the shortlist is still useful to read); `ranked` then stops the run `stopped_cap` as today, so R38 still applies. Test: `test_r38_stop_still_comes_at_ranked_after_the_post_steps`. | PR 5 |
| G5 | §5 Step 8 "full trail for any number": `GET /runs/{id}/records/{record_id}` knows findings, hypotheses, questions, sections and model calls, not chains, LOPA records, recommendations or overrides. | **(plan)** The record route covers all four: a chain's parents are its links; a LOPA record's its target and the argument's model call; a recommendation's its target and model call; an override's its target. Test per kind. | PR 6 |
| G6 | `reject` could be read as removing a row. | **(plan)** Nothing is ever removed: a rejected finding, chain or recommendation stays in every view with status "rejected" (CLAUDE.md: never delete a record). Test: `test_a_rejected_row_stays_listed_as_rejected`. | PR 6 |
| G7 | The connector's plant input and where fact IDs come from. | **(Bhargavi, kept with a change)** The plant goes in as `plant_for_screen` (no plant ID, provenance or sources; G17), and **alongside it the compact list of the plant's `PlantFact` IDs**, both through `as_data`; the scenario lines are cut to `connector_max_input_tokens` by the agreed estimate; a fact link is valid only if it is exactly one of those IDs. Tests: `test_connector_input_carries_the_fact_ids_as_data`, `test_a_fact_link_must_match_a_fact_id_exactly`. The `connector/v1` prompt (PR 2) gains a `{{fact_ids}}` placeholder. | PR 2, PR 5 |
| G8 | `lopa_top_n` for an extended run: stored caps or current config? | **(plan)** The stored caps, since the key is there (spec 3.6 reads only keys the stored caps lack from the current config). The `run_extended` event records which source each value came from. | PR 5 |
| G9 | `ShortlistItem.unsure` for a chain. | **(plan)** True when any of its finding links is unsure. | PR 6 |
| G10 | The "pre-R50 run" label has no contract field. | **(plan)** No new field: the report (`bench/phase3/<case>.json`) carries `pre_r50: true`, and the run has no hypotheses, so every API shortlist item is "also found" already. | PR 5 |
| G11 | The new events. | **(plan)** `EMITTED_EVENT_TYPES` gains `chain_added` (`chain_id`, link count), `lopa_done` (`lopa_id`, `complete`, `full` or `code_only`) and `run_extended` (post cap, prompt versions, the config values used and their source). | PR 5 |
| G12 | The P3-4/5 flags were only on LOPA records; screening showed none. | **(plan)** The ranked lines in `runs/case.py` carry `likelihood.flags`, so `run_case.py` reports show them too. | PR 3 |
| G13 | `run_case.py` needs `--post-cap` for new runs (Q20). | **(plan)** `--post-cap`, default `run.post_spend_cap_usd`; stored on the Run, unhashed. | PR 5 |
| G14 | Every harness that drives a run past severity (replay conftest `make_script`, `test_severity`, `test_run_case`) stops at `ranked` today. | **(plan)** A mechanical change: the fake scripts answer the four new jobs (no chains, every layer "no", no recommendation by default) and the existing assertions stay as they are; no test changes what it checks (as with the screen step in Phase 2b). | PR 5 |
| G15 | Worksheet "Origin" and "Existing safeguards". | **(plan)** Origin: `m:` → matrix; `pair:`, `env:`, `nf:`, `proc:`, `work:`, `dust:`, `relief:` → cross-list; `ai:` → added by AI; `eng:` → engineer. Existing safeguards: the finding's `safeguard_ids`, each with its description. Evidence: empty until Phase 4. | PR 6 |
| G16 | Cowork's example 1 must use the §9 example plant (Q21), and Cowork needs to know that before writing it. | Done: the fixture is delivered on the §9 plant. | — |
| G17 | Example 1 variant C is a complete code-only record with gap 10,000, so under "complete LOPA and gap > 1" (Q12) code-only lines get recommendations too; with many S4–S5 lines that is many calls under the post cap. | **(plan)** Every shortlist line with a complete LOPA and gap > 1 is eligible, full or code-only (spec 3.4, literal). Batches go in shortlist order, so a post-cap stop loses the lowest lines first and the run stops `stopped_cap` with what was done kept. Test: `test_recommendations_go_in_shortlist_order_and_include_code_only_lines`. | PR 5 |
| G18 | The fixture is untracked on `main` and must not be lost or land in the wrong PR. | **(plan)** PR 0 commits only the spec, the plan, the decisions, `specs/phase-2.md` and the config line; the fixture stays untracked until PR 4's branch commits it. | PR 0, PR 4 |
| G19 | Ultra can't judge whether a layer applies without the layer's own row text. | **(plan)** The LOPA argument input carries each candidate's row `layer`, `scenarios` and `conditions_text` (never `pfd`). | PR 2, PR 5 |

### Answers on the PR 3 and PR 4 build choices (Bhargavi, 2026-10-19)

| # | Choice (made by the build, recorded in decisions.md) | Answer |
|---|---|---|
| 1 | Several failing lines: each uses its own leak event; flagged when they differ | Keep |
| 2 | A layer that is itself a failing component gets no credit | Keep |
| 3 | An inlet valve is managed only when known open and `locked: true`; anything missing → `pfd_if_isolatable` | Keep |
| 4 | No frequency and no missing fact → `NoLopa` with the reason | Keep, on condition (PR 5): the line stays on the shortlist with its reason, never dropped, and an S4–S5 line with no LOPA is flagged on its card; tested |
| 5 | A chain's refusals use every finding link's failing components | Keep; the no-credit reason names the chain link whose component caused it (built in PR 4) |
| 6 | `max_tokens` 12288 for the four new jobs | Fine |
| 7 | The assumed-frequency wording | "frequency assumed — engineer to confirm" (PROJECT.md §5), in `likelihood.py`'s two notes and the LOPA flag (built in PR 3 and PR 4) |

**Example 2** (Cowork, `backend/tests/lopa/fixtures/example_2.json`) is a test fixture only: it is never used to write or tune any prompt. Its `open_points_for_claude_code`: the closed-valve reason names the first closed valve in `inlet_valve_ids` order (the engine does); "does not apply" is decided before the inlet-valve rule (rules 2 and 6); variant D's override shape follows PR 6.

### Answers on the PR 5 open points (Bhargavi, 2026-10-20)

| # | Point | Answer (built where) |
|---|---|---|
| 1 | The S4–S5 "no LOPA" flag has no field on the card | New branch `contract/shortlist-flags`: `ShortlistItem.flags: list[str] = []`, types and mocks regenerated; merged before PR 6 |
| 2 | A run stopped at the post cap cannot be resumed | `extend_run.py` takes a run whose last cap stop was a post step's, with a higher `--post-cap`; same run ID; it goes on from the step it stopped at, finished steps not rerun, calls already made from cache at $0 (PR 5) |
| 3 | Post spend also counted in `cap_spent_usd` | Post spend counts against the post cap, the phase cap and the use allowance, never the analysis cap; R45 compares `cap_spent_usd` with the analysis calls (PR 5) |
| 4 | The `POST /runs` upper bound leaves out the post cap | Included: the analysis bound capped at the spend cap, plus `post_spend_cap_usd` (PR 5) |
| — | The seven PR 5 choices | All kept. The rounded gap in the recommendation prompt fits "Ultra never sees a PFD". `StepResult.summary` stays internal, never in the contract. The empty `connector/` package stays; the code lives in `chains/` |

### Misalignments found against Cowork's example 1 (fixed above)

| # | Plan said | Fixture says | Now |
|---|---|---|---|
| M1 | `modifiers_not_applied` per modifier ID (15 rows) | one entry per modifier kind (4) | per kind, `{kind, reason}` (PR 1, PR 4) |
| M2 | `LayerCredit.pfd` unspecified on a refused layer | PFD only on credited layers | `pfd: null` on a refused layer (PR 4) |


## Conflicts found (quoted, for Bhargavi)

- **PROJECT.md §5 Step 6.2** "LOPA for every high-severity finding" vs **§5 Step 6.1** "LOPA on the top `lopa_top_n`": the spec (3.2) resolves this; PR 7 updates PROJECT.md to match.
- **PROJECT.md §5 Step 4:** "`finish` is refused until … the top findings have been through LOPA and evidence" vs **P3-1** "the `finish` guard no longer waits for LOPA": P3-1 wins; PR 7 updates §5 Step 4.
- **PROJECT.md §5 Step 6.2** "Conditional modifiers … from the reference table" vs **P3-3** "none applied": P3-3 wins; PR 7 updates.
- **PROJECT.md §5 Step 6.2** names only shared components and logic solvers; **`protection_layers.csv`** also has sensor and final-element independence flags: Q3.
- **CLAUDE.md §3** "Every record carries the IDs of what it came from" vs **LopaRecord** having no `model_call_id`: Q2.
- **The spec's status line** says "draft" while the message says approved: Q1.

## Not doing (near the line)

- **No change to any analysis-phase prompt, view or validity rule** (rule freeze, P3-1). `severity/v2` is not edited (Q5). `plant_screen/v3` and the orchestrator are not touched.
- **No conditional modifiers** (P3-3), no task-frequency rule (P3-5), no new "overpressure scenario" detection rule (spec 3.2).
- **No change to what "confirmed" means** (P3-6).
- **No evidence tools, precedent index, simulator or frontend** (Phase 4–5). `ShortlistItem.evidence` stays empty.
- **No new run of D–G:** they are extended, not re-run. H is skipped.
- **No plant facts written by me:** Williams Geismar comes from Cowork; I only validate and test it.
- **No new dependency:** openpyxl is already in use.

## Live calls and spend (Bhargavi starts every one)

| Step | Who | Use | Expected |
|---|---|---|---|
| Extend D, E, F, G (`extend_run.py --post-cap 0.30 --phase 3`) | Bhargavi | development | ≈ $0.10 each, ≈ $0.40 |
| Williams Geismar full run (`run_case.py --phase 3`) | Bhargavi | development | ≈ $0.4–0.8 |
| Prompt leak checks | Bhargavi | — | $0 |
| **Total** | | | **≈ $1.2–1.5**, within `phase_caps_usd."3": 2.50` and `development`'s $3.27 |

Every test and replay uses the fake gateway; the network stays blocked in tests.

## Acceptance map (every spec line → where it is proved)

| Spec line | Proved by |
|---|---|
| LOPA hand-worked example 1 | PR 4 `test_example_1_variant_a/b/c_…` (Cowork's fixture: gaps 10, 1000, 10000) |
| LOPA hand-worked example 2 (Williams Geismar, inlet closed → no credit, gap shown) | PR 7 `test_example_2_…` (Cowork's fixture and plant) |
| Shared component / logic solver / open unlocked inlet / locked inlets / no `layer_type` | PR 4, one test each |
| `per_metre_year` without `length_m` → incomplete, no default | PR 4 |
| C20 > 150 mm → `IE-PIPE-LEAK-L` in screening and LOPA | PR 3 and PR 4 |
| Chain validator: non-finding/fact link rejects; facts-only rejects | PR 5 |
| Chains never ranked down for two failures (3.1) | PR 5 |
| Gap shown as orders of magnitude (3.2) | PR 6 |
| R38 for a post-step cap stop (3.6) | PR 5 |
| Gaps G1–G16 (this plan) | the PR named in each row |
| Shortlist order: tier then gap; never crosses tiers | PR 6 |
| Overrides applied on read; records unchanged; 403 recorded | PR 6 |
| Extension: no analysis calls, records byte-identical, run ID unchanged | PR 5 |
| Replay of a full eight-step $0 run | PR 5 |
| Code-only LOPA: no model call, every layer "not argued — no credit" | PR 4 (engine) and PR 5 (step) |
| Post cap stops with analysis intact; analysis cap unchanged | PR 5 |
| Export: xlsx columns, one row per worksheet row, overrides applied | PR 6 |
| Done when: P3-1…P3-7 recorded | PR 0 |
| Done when: every test passes; CI green | Every PR; CI green confirmed by Bhargavi |
| Done when: D, E, F, G extended, `bench/phase3/<case>.json` | PR 5 script; Bhargavi's runs |
| Done when: Williams Geismar committed, validated, run through LOPA | PR 7; Bhargavi's run |
| Done when: PROJECT.md §5 Step 4, 6.1/6.2, §11, §12 screen 4, §16 | PR 7 (§11 records also in PR 1) |
| Done when: spend within cap; `ledger-g3pre` | `phase_caps_usd."3"` (PR 0); Bhargavi's snapshot |
| Phase 2 close-out: G2b provenance; routing; CI; `ledger-g2`/`g2` ticks | PR 0 (CI by Bhargavi) |
| Contract v1.4 items, including the UI naming note | PR 1; the naming note recorded in decisions for Phase 5 |
