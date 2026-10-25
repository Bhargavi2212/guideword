# Phase 6 plan: the held-out benchmark

Status: **draft, awaiting Bhargavi's approval** (mark `Status: approved <date>` here). It also
needs `specs/phase-6.md` approved and committed: the spec is still marked draft and untracked.

Revised 2026-10-25 against the updated `specs/phase-6.md`, which now has P6-13, P6-14, P6-15,
the "started" line and acceptance 2b. Built from `main` at `37ecd31` (after #129, #130). Claude
Code has not opened `guideword-heldout`, `bench/heldout/` or any key, and will not (CLAUDE.md
§5). Every script is built and tested on synthetic folders, and Bhargavi runs every script and
every paid call.

## 1. Checked against the code ($0)

- **Paths.** The benchmark code is in `backend/guideword/bench/` (`test5a.py`, `scoring.py`,
  `results.py`, `kill4.py`), with CLIs in `scripts/`. The spec's `bench/probe.py`,
  `bench/scoring.py`, `bench/heldout_sheet.py` and `bench/heldout_results.py` map to
  `backend/guideword/bench/<name>.py`, with a CLI in `scripts/` for each.
- **Baseline A.** `test5a.run_5a(gateway, config, letter, *, source_dir, out_root)` already takes
  the folder and root. `JOB = "test5a"` is a module constant, and `scripts/run_test5a.py` fixes
  the paths and its `--use` choices. The plan makes the job a parameter and keeps `test5a` for A.
- **Run IDs (P6-13).** `runs/case.py` `run_settings` keeps the routing jobs, prompts and
  `run.max_tokens` entries, minus the post-step ones (`POST_JOBS`, `POST_PROMPTS`). The new jobs'
  `max_tokens` would sit in the hashed `run:` block. So the hash-free set has to cover all three:
  job, prompt and `max_tokens`. `test5a` is already hashed and stays so: taking it out would move
  every stored run's ID.
- **New attempts.** `ids.run_id` gives the same ID to an unfinished run, but `:<n+1>` after a
  finished, cancelled or failed one, and `CapReachedError` for a capped run unless the cap is
  raised. That is why 6.4's "started" line and store lookup are needed: a second start after a
  crash must never mint `:2`.
- **Caps.** `CapsConfig` is a closed model. Today the benchmark's $1.40 / $0.30 / $1.75 have no
  home outside the hashed `run:` block, which P6-2 freezes.
- **Evidence** is already off for use `benchmark` (`evidence/step.py` `off_reason`).
- **`bench/example_stats.json`** is present but untracked. I have read its top-level keys only.

## 2. Gaps and misalignments, with what this plan does

The spec settles C1–C3 and C7 of the first draft: the stop rule is $1.75, P6-13 is a hash-free
set, the stats file stays at `bench/`, and the frontend session does Phase 5 R3, R4 and F3–F6.
What remains:

| # | Where | Gap or misalignment | This plan, or the question for Bhargavi |
|---|---|---|---|
| G1 | 6.4, P6-15 | **Which store the benchmark runs write to** isn't said. `guideword.db` is the untouched source (C8); `guideword-demo.db` holds the demo override. | **Question.** Recommend a new `guideword-benchmark.db`. It's git-ignored like every `*.db`, and is given to the runner as an argument (no default). Bhargavi commits it to the private repo with the outputs (P6-15), and its run dumps are published in 6.6. |
| G2 | P6-2 | **"Post-freeze" can't be detected.** Phase 5 PRs (R3–R5, F3–F6) keep merging to `main` after the freeze, and some touch `backend/`. The spec says a pipeline fix makes later runs "post-freeze", but nothing tells. | The runner compares the **frozen paths** at HEAD with the `phase6-freeze` tag: `prompts/`, `config/routing.yaml`, `reference/`, the hashed `run:` and `ranking:` blocks of `caps.yaml`, and `backend/guideword/` minus `api/`, `bench/` and `export/`. Any change marks every later line `post_freeze: true`, and the results put those rows in their own table. **Question:** is that list the "pipeline"? |
| G3 | P6-7, 6.4 | **Where the benchmark caps live.** "Run cap and post cap from `caps.yaml`" names no block. | A new top-level `benchmark:` block in `caps.yaml` (`run_cap_usd: 1.40`, `post_cap_usd: 0.30`, `baselines_usd: 0.05`, `stop_below_usd: 1.75`), outside `run_input_caps()`, so it's hash-free. A test checks that `stop_below_usd` equals the sum of the other three. It lands in PR 2, before the freeze. |
| G4 | P6-13 | **The hash-free set must cover `max_tokens`**, which lives inside the hashed `run:` block (§1). | `OUTSIDE_RUN_JOBS = {"probe", "baseline_plain"}`, stripped from jobs, prompts and `max_tokens` in `run_settings`, like `POST_JOBS`. Acceptance 2b's test covers all three. |
| G5 | 6.7 vs done-when | **Decisions rows** are "P6-1…P6-12" in 6.7 but "P6-1…P6-15 (with the R26, R38 and §13 supersessions)" in done-when. | The plan follows done-when: P6-1…P6-15, plus rows for R26 (P6-9), R38 (P6-6), PROJECT.md §13's baselines (P6-4) and exclusion rule (P6-5), and the run rule superseded by P6-7. |
| G6 | P6-11 | **"Dev-case results (D–G) in a separate table"**: which records? | **Question.** Recommend the G2b hand-scored results already in `bench/test5/` (their sheets and `results.md`), copied as recorded, labelled development, with nothing re-scored. |
| G7 | 6.2, P6-3 step 3b | **The probe judgement script** is named in P6-3 ("prints the probe's answer next to only the key's `source`") but not in 6.2's file list. | Added: `scripts/probe_judgement.py`. It reads the probe outputs and only the `source` field of each key (a Pydantic model with that one field; every other field is dropped unread). It writes the CSV's case and probe columns for Bhargavi to fill. Tested on a synthetic key whose other fields hold sentinel text that must never appear in the output. |
| G8 | 6.5 | **The blind sheets need Guideword's record keys turned into names** (P6-10), which Phase 5 R3 does in the frontend. | A backend function, `bench/blind.py`, with its own round-trip test (undoing every substitution gives back the stored text). It shares the rule with R3, not the code. |
| G9 | P6-12, 6.1 | **Plant file names in the folder are unknown.** `docs/case-template.md` §3 gives the format, not the file names. | `heldout_verify` lists every file `SEALS.txt` names and classifies it by pattern: package `case_<letter>_*.md`, plant `case_<letter>*.json`, keys `keys/answer_keys.json`. Anything else is listed as "unclassified", by name only. The inventory never assumes a count. |
| G10 | P6-1 | **The seal date evidence** is Bhargavi's to record ("the private repo's first commit date and hash, or the files' timestamps"). | `heldout_verify --seal-info` prints `SEALS.txt`'s own mtime and size, and nothing from inside any file, for her decisions row. The private repo's commit history is hers to read. |
| G11 | Dates | Oct 26: four PRs merged, then the freeze, the folder opened and plant files frozen. Oct 27: the runs. | Holds only if the spec and this plan are approved tonight (Oct 25). PR 2 carries the two prompts for review, which gates the freeze. |

## 3. Per item

### PR 1 — `phase-6/verify` (6.1; acceptance 1)

- **Files:** `backend/guideword/bench/heldout.py` (pure functions for seals, inventory and plant
  validation) and `scripts/heldout_verify.py`. `bench/heldout-frozen.txt` is written by
  Bhargavi's run and committed by her.
- **Tests first** (`backend/tests/bench/test_heldout_verify.py`, synthetic folder in `tmp_path`):
  - `test_a_sealed_folder_passes`;
  - `test_one_changed_byte_fails_naming_the_file`;
  - `test_a_missing_file_fails`;
  - `test_an_unlisted_file_fails`;
  - `test_the_output_holds_names_and_counts_never_contents` (no line of any synthetic file
    appears);
  - `test_the_inventory_classifies_by_pattern_and_names_key_fields_only` (G9);
  - `test_a_plant_that_doesnt_validate_is_listed_by_id_and_field`;
  - `test_the_frozen_hashes_cover_plant_files_only`;
  - `test_seal_info_prints_only_the_seal_files_size_and_time` (G10).

### PR 2 — `phase-6/probe-baselines` (6.2, 6.3, P6-13, G3, G7; acceptance 2b, 4; before the freeze)

- **Files:**
  - `prompts/probe/v1.md` and `prompts/baseline_plain/v1.md`: drafts for review, each asking for
    its JSON schema and a reason;
  - `backend/guideword/bench/probe.py`, `scripts/probe_heldout.py` and
    `scripts/probe_judgement.py` (G7);
  - `test5a.py`: the job is a parameter;
  - `scripts/run_test5a.py`: folder, output root and job are arguments, and `--use` gains
    `benchmark`;
  - `config/routing.yaml`: jobs and prompts for `probe` and `baseline_plain` on Ultra;
  - `config/caps.yaml`: their `max_tokens`, and the `benchmark:` block (G3);
  - `config.py`: a `BenchmarkCaps` model;
  - `runs/case.py`: `OUTSIDE_RUN_JOBS` stripped in `run_settings` (G4).
- **Tests first:**
  - `test_run_settings_are_identical_with_and_without_the_outside_run_jobs`: the jobs, prompts
    and `max_tokens` entries (2b);
  - `test_a_guideword_run_id_is_unchanged_by_them` (2b);
  - `test_the_benchmark_block_is_hash_free_and_its_stop_is_the_sum` (G3);
  - `test_probe_schema_needs_a_reason_and_allows_empty_names`;
  - `test_probe_and_baselines_write_under_the_given_root_never_bench_test5`, with ledger use
    `benchmark` and phase 6 (acceptance 4; fake gateway);
  - `test_a_cut_off_answer_is_a_failure_never_parsed`;
  - `test_baseline_b_uses_5as_schema_and_validator`;
  - `test_the_judgement_script_reads_only_the_keys_source` (G7: sentinel text in every other
    field never appears).

### PR 3 — `phase-6/runner` (6.4, G1, G2; acceptance 2, 3)

- **Files:** `backend/guideword/bench/runner.py` and `scripts/run_benchmark.py`. Their arguments:
  the held-out folder, `--store`, `--out` and `--phase 6`, none with a default. Also
  `scripts/run_case.py`, whose `--use` gains `benchmark`.
- **Tests first** (fake gateway, synthetic folder, probe CSV and store):
  - `test_cases_run_in_letter_order_skipping_excluded`;
  - `test_a_case_with_no_probe_row_is_refused`;
  - `test_it_stops_before_a_case_when_remaining_is_under_stop_below_and_lists_unrun_cases`;
  - `test_a_started_line_is_written_before_the_run_is_driven`;
  - `test_a_case_with_a_started_line_never_starts_a_second_run_even_if_it_finished`;
  - `test_a_crashed_case_resumes_its_own_run_id_at_0`;
  - `test_per_case_order_is_a_then_b_then_guideword`;
  - `test_each_line_records_freeze_commit_status_cost_seconds_and_questions_open`;
  - `test_a_run_stopped_at_its_cap_is_recorded_and_the_runner_moves_on`;
  - `test_a_change_to_a_frozen_path_marks_later_lines_post_freeze` (G2);
  - `test_run_case_use_benchmark_has_evidence_off` (acceptance 3).

### PR 4 — `phase-6/scoring` (6.5, G6, G8; acceptance 5–8)

- **Files:**
  - `bench/heldout_keys.py` (the template key model);
  - `scoring.py`, extended: P6-9 match, the `fixes.md` map, found-anywhere;
  - `bench/blind.py` and `scripts/heldout_sheets.py` (sheets, `blind_map.json`, second-grader
    packets);
  - `bench/stats.py` (Wilson, exact McNemar);
  - `bench/heldout_results.py` and `scripts/heldout_results.py`.
  - `bench/example_stats.json` is committed by Cowork or Bhargavi, named as the tests' source.
- **Tests first:**
  - `test_the_template_example_key_loads`;
  - `test_a_key_missing_a_field_is_refused_naming_only_the_field`;
  - `test_component_and_phrase_match`, `test_component_without_phrase_doesnt`,
    `test_phrase_without_component_doesnt`, `test_hyphen_and_unicode_dash_variants_match`;
  - `test_a_renamed_id_matches_through_the_fixes_map`;
  - `test_found_anywhere_is_the_first_rank_in_the_full_list`;
  - `test_the_xyz_order_is_fixed_by_h_case_id`;
  - `test_regenerating_gives_the_same_files`;
  - `test_no_sheet_line_holds_a_record_key_tier_label_or_config_name`;
  - `test_undoing_the_name_substitution_gives_the_stored_text` (G8);
  - `test_wilson_matches_example_stats`: 0/4, 2/4, 4/4, 3/8, relative tolerance 1e-9;
  - `test_mcnemar_matches_example_stats`: (0,0), (1,0), (3,0), (5,0), (6,0), (4,1);
  - `test_the_power_sentence_comes_from_example_stats`: needs at least 6 discordant, all one
    way;
  - `test_a_stopped_run_counts_as_a_miss`;
  - `test_no_percentage_without_x_of_n`;
  - `test_results_refuse_while_a_row_is_unscored`;
  - `test_post_freeze_rows_are_a_separate_table` (G2);
  - `test_dev_results_are_a_separate_table_copied_as_recorded` (G6).

### PR 5 — `docs/heldout-published` (P6-14; right after G3)

- CLAUDE.md §5 only.

### PR 6 — `phase-6/publish` (6.6, 6.7)

- The cases, keys, seals, probe outputs, `results.md` and the benchmark store's run dumps go
  under `cases/heldout/` and `bench/heldout/`, and the `.gitignore` line comes out.
- Test: `test_every_published_case_file_matches_the_seals`.
- README results section; PROJECT.md §13 and §15; decisions rows (G5).

## 4. Order

PR 1 → PR 2 → PR 3 → PR 4 → freeze → runs → G3 → PR 5 → PR 6. PR 4's pure parts (keys, stats,
blind) can be written alongside PR 3.

Bhargavi's steps, in P6-3 order:
1. Commit `bench/heldout-seals.txt` and the seal-date row (P6-1, G10).
2. Review the two prompts in PR 2; merge PRs 1–4.
3. Tag `phase6-freeze`.
4. Run `heldout_verify.py`; fix any plant file per P6-12; commit `bench/heldout-frozen.txt`.
5. Run `probe_heldout.py`, then `probe_judgement.py`, and fill the CSV (step 3b).
6. Run `run_benchmark.py --store guideword-benchmark.db`.
7. Run the auto-score.
8. Grade blind; the second grader works from the packets.
9. Run `heldout_results.py`.
10. Commit each output to the private repo (P6-15).
11. Tag G3.

## 5. Not doing

- **No pipeline, prompt, routing or reference change** other than the two prompt drafts and the
  two hash-free jobs.
- **No evidence on benchmark runs.**
- **No reading of the held-out material:** `guideword-heldout`, `bench/heldout/` and the keys stay
  closed until PR 5 merges.
- **No converting packages** (P6-12 gives that to a fresh session in the held-out folder).
- **No proposed scores.**
- **No frontend results page.**
- **No Phase 5 R3, R4 or F3–F6** in this session (spec: the frontend session). This session
  keeps R5 (the D and G exports and the redeploy).

## 6. Live calls and spend

| Step | Who | Cost |
|---|---|---|
| Probe, 8 cases | Bhargavi | ≈ $0.04 |
| Per case: baselines A + B | Bhargavi | ≈ $0.04 |
| Per case: Guideword | Bhargavi | ≈ $0.90–1.15, at most $1.70 |
| **Total** | | at most $5.19 (phase cap "6", benchmark allowance) |

No test makes a live call, and every call goes through the gateway's budget guard, phase cap "6"
and use `benchmark`. The stop rule (`stop_below_usd`, $1.75) is checked before each case.
