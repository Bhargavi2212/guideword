# Phase 1 plan — Plant and questions

Status: approved 2026-10-13 (Bhargavi). P1–P12 and Q1–Q9 are answered (see the two decision tables); no open questions.

Covers every item in `specs/phase-1.md`. On approval this file and `specs/phase-1.md` (currently untracked) are committed as the first commits on `phase-1/plant-store`.

## Context

Phase 1 turns a validated plant file into the confirmed section set and the complete, deterministic question list, with coverage counts, and proves the counts on dev cases D–H against independently computed expected counts. It builds on `contract-v1` exactly as tagged (`b44f9b2`): every endpoint keeps its request and response models. No paid calls; the live Super suggestion is wired in Phase 2.

**State at planning (Oct 13):** `main` at `ec0818e`; 720 backend tests pass; schema frozen; `contract-v1` tagged on GitHub; dev cases D–H merged with 89 ticked assumptions; `prompts/` is empty; `settings.database_url` defaults to `sqlite:///./guideword.db`. The local `main` is behind GitHub (`b44f9b2`), so `phase-1/plant-store` is branched from an up-to-date `main` (`git pull` first) that includes PR #14.

**Hand count for the §9 example** (used in the 1.4 test; `work:` per decision P9):

| List | Count | Arithmetic |
|---|---|---|
| sections | 9 | 3 equipment + 4 line parts + 1 procedure + 1 job |
| matrix | 79 | mixer 13 + pump 7 + tank 11 + 4 pipe parts × 12 |
| chemical_pair | 1 | n = 2: 2·1/2 |
| chemical_environment | 6 | 3 × 2 |
| no_flow_line | 0 | both lines flow |
| procedure_step | 10 | 2 steps × 5 guidewords |
| planned_work | 1 | W-1 on ROOF reaches PSV-1, which discharges to ROOF (P9) → `work:W-1:PSV-1` |
| dust | 0 | no solids handler, dryer or combustible dust |
| relief_discharge | 1 | PSV-1 |
| **total questions** | **98** | |

---

## Pull requests in order

| # | Branch | Items | Depends on | Day |
|---|---|---|---|---|
| 1 | `phase-1/plant-store` | approved plan and spec; docs commits (P2, P9 and the decisions lines below); 1.1 | `contract-v1` | Oct 14 |
| 2 | `phase-1/section-rules` | 1.2 | PR 1 (uses `PlantRecord` IDs only; can start in parallel, see below) | Oct 14 |
| 3a | `phase-1/section-suggest-prompt` | `prompts/section_suggestion/v1.md` only (P1), for review | PR 1 | Oct 14 |
| 3 | `phase-1/section-suggest-confirm` | 1.3 without the prompt | PR 1, PR 2, PR 3a merged | Oct 15 |
| 4 | `phase-1/question-builder` | 1.4, 1.7 | PR 2 | Oct 14–15 |
| 5 | `phase-1/coverage` | 1.5 | PR 4 | Oct 15 |
| 6 | `phase-1/dev-case-counts` | 1.6 | PR 4, PR 5, and your own branch with `cases/dev/expected_counts.json` and `.md` merged (Q7) | Oct 15 |

- `rule_cut` (PR 2) is pure and needs only the plant model and a plant record ID string, so PR 2 can be built alongside PR 1. PRs 3 and 4 can run in parallel after PR 2.
- **If time runs short** (spec): PR 2 → 4 → 5 → 6 first, then 1 → 3a → 3. The endpoints can slip into Phase 2's first day; the builder and counts cannot.
- Cowork delivered `cases/dev/expected_counts.json` and `.md` on Oct 13 (P12). They are untracked in the working tree; you commit them on your own branch (Q7), and my branches never stage them. Their keys are already `sections` plus every `QuestionKind` value, for D–H.
- 1.8 (video script) is Bhargavi's with Cowork; not in any PR of mine.

**Every PR:** run the test suite first; small Conventional Commits with the Co-Authored-By line; the `CLAUDE.md` §8 command set before each commit; tick its `specs/phase-1.md` boxes; a dated `docs/decisions.md` line for every decision; PR description with what, why, items, test evidence and anything open.

---

## 1.1 Plant store and plant endpoints — PR 1

**Docs commits first (docs only):**
- `PROJECT.md` §15 Phase 1 row: Phase 1 builds the suggestion logic with a stand-in, and the live Super call is wired in Phase 2 (P2). Plus the matching §11 propose-row wording.
- `PROJECT.md` §5 Step 3 item 5 and `specs/phase-1.md` 1.4: "within reach" also includes every relief device whose `discharge.location_id` is the job's location, with the relief device ID as the target (P9). Unlocated jobs never share a location (P4). `PROJECT.md` also gains the two rules spec 1.4 already has and §5 lacks: a job with no `start` or `end` overlaps every other job at its location, and a job with nothing in reach gets `work:<job>:<job>`.
- `PROJECT.md` §5 Step 2 item 3: "adds procedure or work sections" becomes "adds sections that regroup existing plant objects; a new procedure or job means uploading a new plant file" (P6).
- `specs/phase-1.md` 1.1 and 1.3, where they need the answers written in:
  - P3: not-stated warnings in both upload and detail;
  - P5: re-propose and the PUT straight after upload;
  - P6: engineer sections only regroup objects;
  - P7: the plant routes leave `NOT_BUILT_PHASE` as they are built (1.1 routes in PR 1, propose and PUT in PR 3);
  - P8: names;
  - P10 and Q3: what counts as a fact;
  - P11: the hash;
  - Q1 and Q9: the `check_confirmed` rules and issue codes;
  - Q4: window overlap; Q5: section of each question; Q6: the `sections` coverage line; Q8: both warning kinds in both responses.
- `docs/decisions.md`: the spec's two lines ("Super wired in Phase 2", "rejected suggestions logged, not returned") and one line per decision P1–P12 and Q1–Q9.

**Files**
- `backend/guideword/runs/db.py`: SQLAlchemy 2 (already a dependency) declarative models for `plants`, `plant_facts` and `sections` only; `make_engine(database_url)` and a session factory; `metadata.create_all`, no migration tool. Large payloads (plant file, section records) are JSON columns; links are foreign keys.
- `backend/guideword/runs/plants.py`:
  - `load_plant(data, ref) -> (PlantRecord | None, ValidationReport)` (pure):
    - runs `validate_plant`; with errors it returns `None`;
    - otherwise a `PlantRecord`, status `uploaded`, with ID `ids.plant_record_id(plant_id, data)`, where `ids.h` runs on the parsed JSON object as uploaded, not the Pydantic model, so a schema default never changes the ID (P11).
  - `plant_facts(plant, plant_record_id) -> list[PlantFact]` (pure), per P10:
    - one fact per top-level field of a plant object (procedure steps included) that is not None and not an empty list. Booleans count, including `false`. `id` and `notes` are excluded.
    - a value object is one fact at its parent field;
    - each non-null operating limit is its own fact;
    - the plant's own `plant_id` and `schema_version` are not facts;
    - not facts (Q3): a procedure's `steps` list, a chemical's `source` (used only as the source fallback), and an operating row's `alarm_instrument_id` and `trip_instrument_id`. A procedure step is a plant object, so its own fields are facts (`P-CHARGE-1.text`, `P-CHARGE-1.equipment_ids`);
    - source order: provenance for the fact ID → for the object ID → a chemical's `source` → `"not stated"`.
  - `not_stated_issues(facts) -> list[Issue]`: one `source_not_stated` issue per fact, with `object_id` set to the object and the message naming the field (P3).
  - `PlantRepository(session)`: `add` (idempotent on record ID), `get`, `list`, `set_sections`, `set_status`, `confirm`.
- `backend/guideword/api/app.py`:
  - the three 1.1 routes (`POST /plants`, `GET /plants`, `GET /plants/{id}`) go live when `GUIDEWORD_MOCK` is off and leave `NOT_BUILT_PHASE` in this PR. Propose and PUT leave it in PR 3, when they are built, so no route is ever live before it works (P7, staged). Every other route keeps its 501;
  - `{id}` is the URL-encoded record ID (`plant%3Acase_d%3A<hash>`), decoded by the framework;
  - upload and detail both carry both kinds of warning: the validation warnings, then the `source_not_stated` issues (P3, Q8);
  - the DB engine is created lazily on the first plant request, so the 501 tests and `export_openapi.py` never create `./guideword.db`;
  - mock mode is unchanged.

**Tests first** (`backend/tests/runs/test_plants.py`, `backend/tests/api/test_plant_routes.py`; temp SQLite file per test)
- `test_example_uploads_ok`: `ok: true`, status `uploaded`; facts include `MX-1.design_pressure_kpa` (source `"assumed"`) and `MX-1.operating.temperature.trip_high`.
- `test_upload_with_error_stores_nothing`: one validation error → 200, `ok: false`, `plant_record_id: null`, the error's code and object ID, zero rows.
- `test_same_file_twice_one_row` and `test_changed_value_new_record_id`.
- `test_fact_without_provenance_is_not_stated_and_warned`: source `"not stated"`; one `source_not_stated` issue per fact, object ID set, message naming the field; present in both the upload result and the plant detail (P3).
- `test_value_object_is_one_fact_at_its_parent_field` (`PSV-1.discharge`, `MX-1.heat_sources`).
- `test_false_boolean_is_a_fact_and_empty_list_is_not` (P10).
- `test_ids_notes_and_plant_level_fields_are_not_facts` (P10).
- `test_steps_list_chemical_source_and_operating_instruments_are_not_facts_but_step_fields_are` (Q3: no `P-CHARGE.steps`, no `<chem>.source`, no operating instrument facts; `P-CHARGE-1.text` present).
- `test_record_id_ignores_schema_defaults`: the ID equals `plant:<plant_id>:<h(uploaded JSON object)>`, not a hash of the parsed model, whose defaults (e.g. `"contents": []`) would otherwise change it (P11).
- `test_list_and_get_plant`; `test_unknown_plant_is_404`.
- `test_each_dev_case_uploads_with_no_errors` (D–H).
- `test_url_encoded_record_id_is_found` (`GET /plants/plant%3A...`).
- `test_upload_warnings_include_validation_warnings_and_not_stated` (Q8).
- `test_only_unbuilt_routes_still_501`: the existing 501 test narrowed to the routes still in `NOT_BUILT_PHASE` (P7); after this PR the three 1.1 routes are out of the map, and propose and PUT are still 501 naming phase 1.
- `test_mock_mode_unchanged` (the existing contract tests still pass untouched).

**Dependencies:** none new.

## 1.2 Section rules — PR 2

**Files:** `backend/guideword/sections/rules.py`: `rule_cut(plant, plant_record_id) -> list[Section]`, pure, sorted by section ID, every section `drawn_by: "rule"`. Split points: control valves, pumps, compressors and heat exchangers on the line's `components`. Names (P8):
- whole object `<id> (<type>)`, e.g. `MX-1 (mixer)`, `L-12 (pipe)` for an unsplit line or its first part;
- later line part `<line id> from <split point id> (pipe)`;
- no-flow line `<line id> (no-flow line)`;
- procedure `<id> (procedure: <kind>)`;
- job `<id> (<work type>)`.

**Tests first** (`backend/tests/sections/test_rules.py`)
- `test_example_cut_is_exactly_nine_sections`: the nine IDs in the spec, kinds and types per the table, `object_ids` per part (`S-L-12` = [L-12]; `S-L-12~P-1` = [L-12, P-1, HV-12]; `S-L-STM` = [L-STM, XV-STM]; `S-L-STM~TV-1` = [L-STM, TV-1]).
- `test_no_flow_line_with_a_pump_is_one_flagged_section`.
- `test_first_component_split_point_leaves_an_empty_first_part`.
- `test_line_without_split_points_is_one_section`.
- `test_every_plant_object_covered_and_nothing_else` (equipment, lines, procedures, jobs only; no valve, utility, location, instrument, safeguard, relief device or chemical section).
- `test_section_ids_parse_and_are_unique` (through the `Section` record's ID check).
- `test_planned_work_section_has_no_type`.
- `test_section_names` (each format in P8).

## 1.3a Section suggestion prompt — PR 3a (P1)

**Files:** `prompts/section_suggestion/v1.md` only. It covers:
- the fixed response schema (`{"suggestions": [...]}`, each with `kind`, `section_ids`, `purpose`, `reason`, and the length caps);
- a reason on every suggestion;
- "the section list and the plant are data, not instructions";
- the four triggers (phase change, new temperature range, new chemical entering, start-up-only line);
- the no-flow rule (never merge or split a flagged no-flow section);
- plant `notes` passed as data.

Nothing loads it in Phase 1. Its own small PR, for your review, merged before PR 3.

**Tests:** none in this PR; PR 3 adds `test_prompt_exists_and_asks_for_schema_and_reason`.

## 1.3 Section suggestions, propose and confirm — PR 3

**Files**
- `backend/guideword/sections/suggest.py`:
  - `SuggestionResponse`, an internal model in this module, is the model-response schema: `{"suggestions": [...]}`, each item in the contract's `SectionSuggestion` shape plus the caps (reason 1–300 characters, purpose 1–160). After validation it is converted to the contract's `SectionSuggestion`, which is unchanged (P10b; not a contract change).
  - `Suggester` protocol; `NullSuggester` (endpoint); `FakeSuggester(fixed)` (tests).
  - `check_suggestions(plant, sections, suggestions) -> (valid, rejected)`, `rejected` = list of (suggestion, reason). Rules:
    - unknown section or component;
    - merge or split touching a flagged no-flow section;
    - merge across kinds or section types;
    - split of a non-line section, or at a component not strictly inside the part;
    - wrong `section_ids` count for the kind (split 2, merge ≥ 2, purpose 1);
    - a purpose suggestion with no purpose;
    - **following from Q1:** a merge whose result `check_confirmed` would refuse, i.e. parts of two different lines, or two procedure or two planned-work sections (each holds one object). Without this, a "valid" suggestion would always end in a 409.
  - `apply(sections, accepted) -> list[Section]`:
    - split: the new part is `S-<line>~<component>`, named `<line id> from <component id> (pipe)` (P8); the old part keeps the components before it;
    - merge: the lowest ID and that section's name; `object_ids` = each merged section's `object_ids` in section-ID order, first occurrence kept;
    - purpose: sets `purpose`;
    - changed sections get `drawn_by: "suggestion"` and the reason as `suggestion_reason`.
- `backend/guideword/sections/confirm.py`: `check_confirmed(plant, plant_record_id, sections) -> list[Issue]`, each issue naming its object. It applies the spec's five rules, plus the rules below (P6, Q1, Q9):
  - **"section belongs to another plant":** the PUT's `plant_record_id` check;
  - **"engineer section covers an object not in the plant":** engineer-added sections may only regroup existing plant objects; a new procedure or job means uploading a new plant file (P6).
  - The engineer section ID is checked with `ids.engineer_section_id(object_ids)`.
  - **Objects fit the kind and type (Q1):**
    - an `equipment` section holds only equipment, all of exactly its `section_type`;
    - a `line` or `no_flow_line` section holds exactly one line plus only components of that line (`flagged_no_flow` true exactly for `no_flow_line`);
    - a `procedure` or `planned_work` section holds exactly that one object.
  - **Nothing dropped (Q9, replacing Q2's subset rule):** (1) every equipment item is in an `equipment` section of its own type; (2) every component of every line is in a `line` or `no_flow_line` section of that line; (3) every line has a confirmed section with ID `S-<line id>` (a merge that includes it keeps that ID, the lowest on the line).
  - **Issue codes**, one per rule: `object_not_in_section`, `no_flow_line_not_own_section`, `invalid_section_id`, `duplicate_section_id`, `engineer_section_id_mismatch`, `section_type_missing`, `section_objects_do_not_fit`, `section_of_other_plant`, `engineer_section_unknown_object`, `equipment_not_in_own_section`, `line_component_not_in_line_section`, `line_first_part_missing`.
- `create_app` gains a `suggester` argument (default `NullSuggester()`), so the endpoint test can inject a `FakeSuggester` and check that rejected suggestions are logged (spec 1.3: "the endpoint logs it"). Internal; not a contract change.
- Propose and PUT leave `NOT_BUILT_PHASE` in this PR (P7, staged).
- `api/app.py`:
  - **`POST /plants/{id}/sections/propose`:**
    - runs the rule cut with `NullSuggester` and stores it as the current set;
    - logs each rejected suggestion through `guideword/logs.py` with its reason;
    - status → `sections_proposed`;
    - on a `sections_confirmed` plant it also clears `confirmed_section_ids` and moves the status back to `sections_proposed`; existing runs keep their own snapshots (P5).
  - **`PUT /plants/{id}/sections`:**
    - allowed from any status, including straight after upload; `check_confirmed` is the guard (P5);
    - issues → 409, one issue per line as `<code> <object id>: <message>`;
    - otherwise it stores the set, sets `confirmed_section_ids`, and the status → `sections_confirmed`.

**Tests first** (`backend/tests/sections/test_suggest.py`, `test_confirm.py`, `backend/tests/api/test_section_routes.py`)
- `test_valid_split_creates_the_new_part` (`["S-L-12~P-1", "S-L-12~HV-12"]` → `S-L-12~HV-12` = [L-12, HV-12], `S-L-12~P-1` = [L-12, P-1]).
- `test_merge_keeps_the_lowest_id_and_unions_objects`; `test_purpose_is_set`; each carries `suggestion_reason` and `drawn_by: "suggestion"`.
- One test per rejection rule, each returning the suggestion in `rejected` with its reason and never raising; `test_merge_with_flagged_no_flow_section_is_rejected`.
- `test_rejected_suggestions_are_logged` (endpoint with an injected `FakeSuggester`; captures the JSON log line); `test_propose_returns_only_valid_suggestions_and_stores_the_rule_cut`.
- `test_propose_and_put_unknown_plant_is_404`; `test_put_section_of_another_plant_is_409`.
- `test_split_part_name` (P8).
- `test_reason_and_purpose_caps_enforced_by_the_response_schema`.
- One test per `check_confirmed` rule, exactly that issue and object ID.
- `test_engineer_section_must_regroup_existing_objects` (P6).
- Q1, one test per kind: `test_equipment_section_with_mixed_types_is_refused` (MX-1 + TOTE-1 typed mixer); `test_line_section_with_two_lines_is_refused`; `test_line_section_with_a_foreign_component_is_refused`; `test_procedure_section_with_two_objects_is_refused`; `test_planned_work_section_with_two_objects_is_refused`; `test_same_type_equipment_merge_is_accepted`.
- `test_merge_of_two_lines_is_a_rejected_suggestion` (follows from Q1).
- Q9, the five cases: `test_valid_split_passes` (the spec's `S-L-12~HV-12` example); `test_dropped_empty_first_part_fails` (`S-L-12` gone → `line_first_part_missing`); `test_dropped_equipment_section_fails` (`S-P-1` gone, P-1 still in `S-L-12~P-1` → `equipment_not_in_own_section`); `test_dropped_later_part_fails` (`S-L-12~P-1` gone → `line_component_not_in_line_section` for P-1 and HV-12); `test_merge_of_two_parts_of_one_line_passes` (`S-L-12` + `S-L-12~P-1` → `S-L-12`).
- `test_propose_then_put_moves_status_and_reads_back_identical`.
- `test_repropose_after_confirm_clears_the_confirmed_set` (P5).
- `test_put_straight_after_upload_is_allowed_when_checks_pass` (P5).
- `test_rename_keeps_the_id`.
- `test_put_issues_are_409_one_per_line`.
- `test_prompt_exists_and_asks_for_schema_and_reason`; `test_no_section_code_loads_a_prompt_or_model_client`.

## 1.4 Question builder — PR 4

**Files**
- `backend/guideword/questions/build.py`: `build_questions(plant, sections, ref, run_id) -> list[Question]`, pure, all `open`, sorted by list (spec table order) then ID. Section of each question per the spec. "Within reach" is the spec's union plus two decisions:
  - every relief device whose `discharge.location_id` is the job's location, with the relief device ID as the target (P9);
  - a job with no location never matches another job's location, and two unlocated jobs are not "the same location" (P4).
  - windows overlap when `a.start <= b.end and b.start <= a.end` (touching counts); a missing time or a time-zone mismatch between the two jobs counts as overlapping (Q4).
- Section of each question (Q5): an equipment-keyed question (`dust:`, and `relief:` through `protects_id`) belongs to the `equipment`-kind section containing that equipment; a line-keyed one (`nf:`) to the section of kind `line` or `no_flow_line` containing the line; `proc:` and `work:` to the one section holding that procedure or job (unique under Q1). If several qualify, the lowest section ID. If none qualifies (only possible on a set that never passed `check_confirmed`), `section_id` is None.
- Tests pass the fixed run ID `run:test` (spec 1.4).
- `backend/guideword/questions/text.py`: fixed neutral templates, filled only with IDs, names and enum values; never reads `notes`.

**Tests first** (`backend/tests/questions/test_build.py`)
- `test_example_counts_per_list` (the hand count above, arithmetic written in the test).
- `test_chemical_counts` (n = 0, 1, 2, 10 → pairs 0, 0, 1, 45; environment 0, 3, 6, 30).
- `test_no_flow_line_gets_pipe_matrix_plus_one_nf`.
- `test_procedure_steps_times_five_and_never_before_or_after`.
- Within reach: `test_reach_listed_equipment_and_lines`, `test_reach_equipment_in_location`, `test_reach_lines_by_endpoint_in_location`, `test_reach_line_ending_at_the_location_itself`, `test_reach_overlapping_job`, `test_reach_non_overlapping_job_excluded`, `test_reach_job_without_window_included`, `test_reach_relief_device_discharging_at_the_location` (P9; §9 example gives `work:W-1:PSV-1`), `test_unlocated_jobs_never_reach_each_other` (P4), `test_reach_empty_gives_job_itself`.
- `test_dust_dryer_with_combustible_dust_once`.
- `test_every_id_parses_no_duplicates_sections_exist`.
- `test_templates_never_include_note_text` (marker string in notes).
- `test_relief_question_section_is_protected_equipment` (`relief:PSV-1` → `S-MX-1`).
- `test_section_of_each_question_kind` (one case per row of the spec's "Section of each question" list: matrix, `nf:`, `proc:`, `work:`, `dust:`, `relief:`, and none for `pair:` and `env:`).
- `test_touching_windows_overlap`; `test_time_zone_mismatch_counts_as_overlap` (Q4).
- `test_relief_on_a_pump_goes_to_its_equipment_section` (P-1 → `S-P-1`, not `S-L-12~P-1`); `test_several_qualifying_sections_take_the_lowest_id` (Q5).

## 1.5 Coverage counts — PR 5

**Files:** `backend/guideword/questions/coverage.py`: `coverage(sections, questions, findings=()) -> (list[CoverageList], list[str])`, lines in the spec's order (`sections`, then every `QuestionKind`), every list present even at `0 of 0`. A finding counts toward unsure through its `question_id`. On the `sections` line (Q6): `total` = sections in the set; `unsure` = sections with at least one answered question that has an unsure finding; `failed` = sections with at least one failed question.

**Tests first** (`backend/tests/questions/test_coverage.py`)
- `test_fresh_list_is_zero_of_n_per_list`.
- `test_answered_and_not_credible_check_failed_does_not`; `test_failed_ids_returned`.
- `test_unsure_counts_answered_questions_with_an_unsure_finding`.
- `test_section_checked_only_when_all_its_questions_are`; `test_section_with_no_questions_is_checked`.
- `test_every_list_appears_even_when_empty`.
- `test_sections_line_unsure_and_failed` (Q6).

## 1.6 Dev-case counts — PR 6

**Files**
- `backend/tests/cases/test_question_counts.py`: per case D–H, upload → `rule_cut` → `build_questions` → `coverage`; every list count equals `cases/dev/expected_counts.json`, compared on all 11 keys (`sections` plus every `QuestionKind`; Q7). The test also fails if a case or key is missing on either side.
- `scripts/build_questions.py <plant file>`: prints the section cut and the counts per list (CLI `print`); no live calls.
- I never edit `cases/dev/expected_counts.json` or `expected_counts.md`. If a count disagrees, I stop and report it with the question IDs on each side; I change neither file nor builder to match (spec).

**Tests:** the count test; `test_build_questions_cli_runs_on_case_g` (subprocess, no network).

## 1.7 Determinism and completeness — PR 4

**Tests first** (`backend/tests/questions/test_determinism.py`)
- `test_building_twice_is_identical` (IDs, order, text).
- `test_shuffled_plant_lists_give_identical_output`: every list shuffled with a seeded shuffle in the test, nested lists included (`contents`, `equipment_ids`, `line_ids`, `no_flow`, `epa_groups` and so on), except a line's `components` and a procedure's `steps`. The same `plant_record_id` is passed, since the shuffled file has a different hash.
- `test_two_processes_give_identical_output`.
- `test_no_public_function_removes_questions` (each public function of `questions/` given a known list returns a superset or a count, never fewer questions).
- `test_sections_and_questions_import_no_client` (AST: no `openai`, `tavily`, `httpx`, `live_call`, `gateway`).

---

## Decisions from the plan review (Bhargavi, Oct 13)

Each gets a dated line in `docs/decisions.md` in PR 1's docs commits.

| # | Question | Decision |
|---|---|---|
| P1 | The prompt in PR 3 | `prompts/section_suggestion/v1.md` gets its own small PR, `phase-1/section-suggest-prompt` (PR 3a), merged before PR 3. |
| P2 | PROJECT.md still lists Super suggestions in Phase 1 | Update PROJECT.md §15 (Phase 1 builds the suggestion logic with a stand-in; the live Super call is wired in Phase 2) and the matching §11 line, in PR 1's docs commits. |
| P3 | Where "not stated" warnings appear | In both the upload result and the plant detail. Code `source_not_stated`, one issue per fact, `object_id` = the object, the message names the field. |
| P4 | Jobs with no location | A job without a location never matches another job's location; two unlocated jobs are not "the same location". |
| P5 | Re-propose after confirm; PUT after upload | A re-propose after confirm replaces the stored set with the new rule cut, clears `confirmed_section_ids` and moves the status back to `sections_proposed` (existing runs keep their own snapshots). A PUT straight after upload is allowed; `check_confirmed` is the guard. |
| P6 | Engineer-added procedure or work sections | Engineer-added sections only regroup existing plant objects (`S~eng~…`). A new procedure or job means uploading a new plant file. |
| P7 | The existing 501 test | Narrow it to routes still marked unbuilt in `NOT_BUILT_PHASE`, and remove the five plant routes from that map. Staged: the three 1.1 routes leave it in PR 1, propose and PUT in PR 3, so no route goes live before it is built. |
| P8 | Section names | Whole object `<id> (<type>)`; line part `<line id> from <split point id> (pipe)`; no-flow line `<line id> (no-flow line)`; procedure `<id> (procedure: <kind>)`; job `<id> (<work type>)`. |
| P9 | Relief discharge and planned work | "Within reach" also includes every relief device whose `discharge.location_id` is the job's location; the target is the relief device ID. Update spec 1.4 and PROJECT.md §5 Step 3 item 5. The §9 example then has `work:W-1:PSV-1` instead of `work:W-1:W-1`; the total stays 98. |
| P10 | What counts as a plant fact | One per top-level field of a plant object that is not None and not an empty list (booleans count, including false), excluding `id` and `notes`. A value object is one fact at its parent field; each non-null operating limit is its own fact. The plant's own `plant_id` and `schema_version` are not facts. |
| P10b | The suggestion response schema | Not a contract change: the model-response schema with the length caps is an internal model in `sections/suggest.py`, converted to the contract's `SectionSuggestion` after validation. |
| P11 | The plant record hash | The canonical JSON of the raw uploaded file (`ids.h` on the parsed JSON object as uploaded, not the Pydantic model), so a schema default never changes a plant's ID. |
| P12 | Expected counts | Cowork delivered `cases/dev/expected_counts.json` and `.md` on Oct 13, computed from the current dev-case files with these decisions. |

## Decisions from the second check (Bhargavi, Oct 13)

| # | Question | Decision |
|---|---|---|
| Q1 | What objects a section may hold | Strict. An equipment section holds equipment of exactly its `section_type`; a line or no-flow section holds one line and only components of that line; a procedure or planned-work section holds that one object. Anything else is a `check_confirmed` issue. |
| Q2 | Nothing silently dropped | Every rule-drawn section's `object_ids` must be a subset of some confirmed section's `object_ids`. Merges pass; a dropped part (including an empty first part like `S-L-12`) fails. Test both. Superseded by Q9. |
| Q3 | Edge fields of P10 | None of the three is a fact: a procedure's `steps` list, a chemical's `source`, an operating row's instrument IDs. A procedure step is a plant object, so its own fields are facts (e.g. `P-CHARGE-1.text`). |
| Q4 | Overlapping windows | Touching windows overlap (`a.start <= b.end and b.start <= a.end`). A time-zone mismatch, like a missing time, counts as overlapping. |
| Q5 | Section of each question | An equipment-keyed question (`dust:`, `relief:` via `protects_id`) belongs to the equipment-kind section containing that equipment; a line-keyed one (`nf:`) to the line's section. If several qualify, the lowest section ID. |
| Q6 | The `sections` coverage line | `unsure` = sections with at least one answered question that has an unsure finding; `failed` = sections with at least one failed question. |
| Q7 | `expected_counts.json` keys | Uses `sections` plus the `QuestionKind` values; Bhargavi commits it on its own branch. |
| Q8 | Upload warnings | Both responses carry both kinds of warning. |
| Q9 | The Q2 rule, which refused valid splits and missed dropped parts | Replaced by three checks: every equipment item in an equipment section of its own type; every line component in a section of that line; every line keeps `S-<line id>`. Tests for five cases: valid split passes, dropped empty first part fails, dropped equipment section fails, dropped later part fails, merge of two parts of one line passes. Suggestion-time rejection of cross-line, cross-procedure and cross-job merges approved. |

No open questions remain.

## Not doing (near the scope line)

- No gateway, no live Super call, no `GatewaySuggester` (Phase 2).
- No runs, no run state machine, no `/runs/...` endpoint, no `GET /runs/{id}/coverage` (Phase 2); coverage is a function only.
- No `ai:` or `eng:` questions; no findings, LOPA, ranking or tools.
- No change to any `contract-v1` request or response model, to `api/models.py`, or to the mock fixtures.
- No migration tool; no tables beyond `plants`, `plant_facts`, `sections`.
- No `Question.fact_ids` (Phase 2 decides them).
- No edits to `cases/dev/expected_counts.json` or `.md`; no reading of `cases/dev/keys/`.
- No frontend work; no video script (1.8 is Bhargavi's).

## Live calls and spend

None. Every test uses a temp SQLite file and the `FakeSuggester`; the prompt is never sent. Phase 1 spend: **$0.00** (ledger unchanged).

## Verification

- Per PR: `CLAUDE.md` §8 commands; CI green before merge; `contract/openapi.json` still matches the app (no contract change).
- PR 1: upload, list and get on the five dev cases and the §9 example against a temp DB; the mock-mode tests unchanged.
- PR 4: the §9 example gives exactly 9 sections and 98 questions (79 / 1 / 6 / 0 / 10 / 1 / 0 / 1, with `work:W-1:PSV-1`, P9).
- PR 6: every list count on D–H equals `expected_counts.json`; `python scripts/build_questions.py cases/dev/case_g.json` prints the cut and counts on Windows.
- Done when: every `specs/phase-1.md` box ticked; ledger unchanged; every decision dated in `docs/decisions.md`.
