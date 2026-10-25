# Phase 6 plan: the held-out benchmark

Status: **draft, awaiting Bhargavi's approval** (mark `Status: approved <date>` here). It also
needs `specs/phase-6.md` approved: the spec is still a draft.

Written 2026-10-25 from `main` at `2a6f97e`+ (after #128), against `specs/phase-6.md` (Cowork,
2026-10-25). Claude Code has not opened `guideword-heldout`, `bench/heldout/` or any key, and
will not (CLAUDE.md §5). Every script is built and tested on synthetic folders. Bhargavi runs
every one of them, and every paid call.

## 1. What I checked ($0)

- **Code paths differ from the spec's.** The benchmark code lives in `backend/guideword/bench/`
  (`test5a.py`, `scoring.py`, `results.py`, `kill4.py`) with CLIs in `scripts/`
  (`run_test5a.py`, `score_test5.py`, `test5_results.py`), not in `bench/*.py`. The plan uses the
  real paths.
- **`test5a.package_for(letter, source_dir)` already takes the package folder.** Only the output
  roots (`bench/test5/raw/5a/`, `bench/test5/5a/`) are fixed.
- **Run IDs.** `runs/case.py` `run_settings` hashes every routing job and `max_tokens` entry
  except the five post jobs, so the `test5a` job is already in every run's hash. Adding `probe`
  and `baseline_plain` (routing and `max_tokens`) before the freeze moves only the IDs of runs
  not yet started. No stored run changes, and nothing in routing changes after the freeze (P6-2).
  Taking the outside-run jobs out of the hash instead would move every existing ID, `test5a`
  included, so the plan doesn't.
- **The spend cap.** `Run.spend_cap_usd` is not hashed (PROJECT.md §11), but `caps.yaml`'s
  `run.run_spend_cap_usd` default is. `run_case.py` already takes `--cap`. So the benchmark's
  $1.40 and $0.30 can live outside the hashed block and be passed explicitly.
- **Evidence is already off for `benchmark`** (`evidence/step.py` `off_reason`: "use benchmark").
  `run_case.py`'s `--use` offers `development, test_5, video`.
- **`bench/example_stats.json` is present** (untracked) with `wilson_95`, `mcnemar_exact` and
  `smallest_all_one_way_discordant_for_p_below_0_05`. I read its keys only.

## 2. Conflicts and questions (for Bhargavi; not resolved here)

| # | Where | The conflict | Question / recommendation |
|---|---|---|---|
| C1 | P6-7, acceptance 2, decisions 2026-10-25 | **Three stop rules.** Decided: stop when remaining is under **$1.30**. P6-7: under **$1.75** ($1.40 + $0.30 + $0.05). Acceptance 2: "stops exactly when remaining < **$1.35**". | Which one? P6-7's $1.75 follows from P6-7's caps; with $5.19 that allows 2 cases for certain and a third only if the first two cost ≤ $1.72 together. Acceptance 2's $1.35 looks like a slip. **Recommend $1.75**, held in `caps.yaml` (C5), with the decisions row superseded. |
| C2 | P6-1 … P6-12 table | **P6-13 and P6-14 are cited** ("P6-13 deals with this", "P6-14") but are not in the table. | P6-13 (run IDs): **recommend** adding the two jobs before the freeze, as in §1. P6-14 (lifting CLAUDE.md §5 after G3): **recommend** a separate PR after `results.md` is committed, as 6.6 says. Both as decisions rows. |
| C3 | Acceptance 8, "Cowork" | **`example_stats.json`'s place.** The spec puts it at `bench/heldout/example_stats.json`, but `bench/heldout/` is git-ignored and Claude Code may not read it, so tests couldn't use it there. It landed at `bench/example_stats.json`. | **Recommend** moving it to `backend/tests/bench/fixtures/example_stats.json`, committed, with its source named. The Wilson and McNemar tests read it. |
| C4 | P6-7 | **The second-$25 clause** raises `benchmark` "and the laptop and global totals" if the grant lands before the first run. | Fine as written, but `GLOBAL_BUDGET_USD` comes from settings (`.env`), not `caps.yaml`. The change is two edits (`.env` and `caps.yaml`) plus the config test, made by Bhargavi before the first run. Confirm. |
| C5 | P6-7 | **Where the benchmark caps live.** | A new unhashed `benchmark:` block in `caps.yaml`: `run_cap_usd: 1.40`, `post_cap_usd: 0.30`, `baselines_usd: 0.05`, `stop_below_usd: 1.75` (C1). The runner passes the two caps to `start_case`. The hashed `run:` block is unchanged. |
| C6 | P6-10 | **Names in the blind sheet.** Guideword's lines must show tag and step names, not record keys. Phase 5 R3 does that substitution in the frontend. | Phase 6 needs its own backend function (`bench/blind.py`), tested the same way: undoing every substitution gives back the stored text. R3 and Phase 6 share the rule, not the code. |
| C7 | 6.6, P6-3 | **Who builds Phase 5's R3–R4.** The spec says the frontend session does R3, R4 and F3–F6 while this session builds Phase 6. The review plan (Q13) gave R0–R6 to this session. | **Recommend:** this session does Phase 6 PRs 1–4 and R5 (deploy, backend). The frontend session takes R3, R4 and F3–F6. Confirm, and I'll write the handover note. |
| C8 | Dates | Oct 26: four PRs merged and the folder opened; Oct 27: runs. This sits beside Phase 5's Oct 28 end and one reviewer. | Feasible only if the spec and this plan are approved tonight. If not, a day slips, and G3 moves to Oct 28 with the runs on Oct 27–28. |

## 3. Per item

### PR 1 — `phase-6/verify` (6.1; acceptance 1)

- **Files:** `scripts/heldout_verify.py` and `backend/guideword/bench/heldout.py` (pure functions:
  seals, inventory, plant validation); `bench/heldout-frozen.txt` is written by Bhargavi's run.
- **Tests first** (`backend/tests/bench/test_heldout_verify.py`, synthetic folder in `tmp_path`):
  - `test_a_sealed_folder_passes`;
  - `test_one_changed_byte_fails_naming_the_file`;
  - `test_a_missing_file_fails`;
  - `test_an_unlisted_file_fails`;
  - `test_it_prints_names_and_counts_never_contents` (the output holds no line of any file);
  - `test_the_inventory_counts_packages_plants_keys_and_names_key_fields_only`;
  - `test_a_plant_that_doesnt_validate_is_listed_by_id_and_field`;
  - `test_the_frozen_hashes_are_written_for_plant_files_only`.
- **Dependencies:** none new.

### PR 2 — `phase-6/probe-baselines` (6.2, 6.3; acceptance 4)

- **Files:**
  - `prompts/probe/v1.md` and `prompts/baseline_plain/v1.md`: drafts for Bhargavi's review;
    every prompt asks for its JSON schema and a reason;
  - `backend/guideword/bench/probe.py`, `scripts/probe_heldout.py`;
  - `backend/guideword/bench/test5a.py`, generalised: output roots are arguments, and
    `baseline_plain` uses the same call path, schema and validator;
  - `config/routing.yaml`: jobs `probe` and `baseline_plain` on Ultra;
  - `config/caps.yaml`: their `max_tokens`, and the `benchmark:` block (C5).
- **Tests first:**
  - `test_probe_schema_needs_a_reason_and_allows_empty_names`;
  - `test_probe_writes_under_the_given_root_with_use_benchmark_and_phase_6` (fake gateway; the
    ledger line);
  - `test_probe_judgement_csv_is_read_and_a_case_without_a_row_is_refused`;
  - `test_baselines_write_under_the_given_root_never_bench_test5`;
  - `test_baseline_b_uses_5as_schema_and_a_cut_off_answer_is_a_failure`;
  - `test_the_two_new_jobs_route_to_ultra`;
  - `test_the_benchmark_block_is_outside_the_run_hash`: a run's ID doesn't move when the
    benchmark caps change.
- **Live:** none in tests. Bhargavi's probe run is about $0.04.

### PR 3 — `phase-6/runner` (6.4; acceptance 2, 3)

- **Files:** `scripts/run_benchmark.py` and `backend/guideword/bench/runner.py`. `scripts/run_case.py`
  gains `benchmark` among its `--use` choices.
- **Tests first** (fake gateway, synthetic held-out folder and probe CSV):
  - `test_cases_run_in_letter_order_skipping_excluded`;
  - `test_a_case_with_no_probe_row_is_refused`;
  - `test_the_stop_rule_stops_before_a_case_when_remaining_is_below_the_threshold` (C1's value,
    from `caps.yaml`), listing the unrun cases;
  - `test_a_case_with_a_line_in_runs_jsonl_is_never_started_again`;
  - `test_a_crashed_case_resumes_its_own_run_id_at_0`;
  - `test_each_line_records_the_freeze_commit_status_cost_seconds_and_questions_open`;
  - `test_a_run_stopped_at_its_cap_is_recorded_and_the_runner_moves_on`;
  - `test_run_case_use_benchmark_has_evidence_off` (the step summary says "use benchmark");
  - `test_per_case_order_is_baseline_a_then_b_then_guideword`.

### PR 4 — `phase-6/scoring` (6.5; acceptance 5–8)

- **Files:**
  - `backend/guideword/bench/heldout_keys.py`: a Pydantic model of the template key; it refuses
    a missing field and names the field only;
  - `scoring.py`, extended with the P6-9 match (component AND phrase), the `fixes.md` ID map, and
    found-anywhere;
  - `bench/blind.py`, `scripts/heldout_sheets.py`: blind sheets, `blind_map.json` and the
    second-grader packets;
  - `bench/stats.py`: the Wilson interval and exact McNemar;
  - `scripts/heldout_results.py`: renders `results.md` and refuses while any row is unscored.
- **Tests first:**
  - `test_the_template_example_key_loads` and `test_a_key_missing_a_field_is_refused_naming_only_the_field`;
  - `test_component_and_phrase_match`, `test_component_without_phrase_doesnt`,
    `test_phrase_without_component_doesnt`, `test_hyphen_and_unicode_dash_variants_match`;
  - `test_a_renamed_id_matches_through_the_fixes_map`;
  - `test_found_anywhere_is_the_first_rank_in_the_full_list`;
  - `test_the_xyz_order_is_fixed_by_h_case_id` and `test_regenerating_gives_the_same_files`;
  - `test_no_sheet_line_holds_a_record_key_tier_label_or_config_name`;
  - `test_undoing_the_name_substitution_gives_the_stored_text` (C6);
  - `test_wilson_matches_example_stats` (0/4, 2/4, 4/4, 3/8) and
    `test_mcnemar_matches_example_stats` (0, 1, 3, 5 discordant);
  - `test_a_stopped_run_counts_as_a_miss`;
  - `test_no_percentage_without_x_of_n`;
  - `test_results_refuse_while_a_row_is_unscored`;
  - `test_dev_results_are_a_separate_table`.

### PR 5 — `phase-6/publish` (6.6, 6.7; after G3)

- Cases, keys, seals, probe outputs and run dumps under `cases/heldout/` and `bench/heldout/`. The
  `.gitignore` line comes out, and CLAUDE.md §5 is updated (P6-14).
- Test: `test_every_published_case_file_matches_the_seals`.
- README results section; PROJECT.md §13 and §15. Decisions rows P6-1 … P6-14.

## 4. Order

PR 1 → PR 2 → PR 3 → PR 4, each merged before the next; PR 2 and PR 4's pure parts can be
written in parallel with PR 3. Bhargavi's steps, in the spec's P6-3 order:

1. Commit `bench/heldout-seals.txt` and record its date evidence (P6-1).
2. Tag `phase6-freeze` once PRs 1–4 are merged.
3. Run `heldout_verify.py` and commit `bench/heldout-frozen.txt`.
4. Run the probe and fill `probe_judgement.csv` at step 3b.
5. Run `run_benchmark.py`.
6. Run the auto-score.
7. Grade blind (both graders).
8. Generate `results.md`.
9. G3, then PR 5.

## 5. Not doing

- **No pipeline, prompt (other than the two drafts), routing (other than the two jobs) or
  reference change.**
- **No evidence on benchmark runs.**
- **Claude Code doesn't touch the held-out material:**
  - no reading of `guideword-heldout`, `bench/heldout/` or the keys before PR 5;
  - no converting held-out packages (P6-12 says a fresh session in that folder does it);
  - no proposing scores.
- **No frontend results page.**

## 6. Live calls and spend

| Step | Who | Cost |
|---|---|---|
| Probe, 8 cases | Bhargavi | ≈ $0.04 |
| Per case: baselines A + B | Bhargavi | ≈ $0.04 |
| Per case: Guideword | Bhargavi | ≈ $0.88–1.15, at most $1.70 under P6-7's caps |
| **Total** | | at most $5.19 (phase cap "6", benchmark allowance) |

No test makes a live call. Every call goes through the gateway's budget guard, phase cap "6" and
use `benchmark`.
