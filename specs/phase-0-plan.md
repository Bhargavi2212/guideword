# Phase 0 plan — Foundations

Status: approved 2026-10-12 (Bhargavi). All 16 questions answered on Oct 12; see "Decisions from the plan review".

On approval this file is copied to `specs/phase-0-plan.md` and committed as the first commit on `phase-0/scaffold`.

## Context

Phase 0 (Oct 12–14, gate G1 on Oct 14 morning) builds everything later phases stand on:
- the repo tree, tooling and CI;
- config;
- the budget-capped live-call script and the smoke test;
- the schema package and reference loaders;
- dev cases D–H;
- the frozen API contract with a mock server.

The Oct 12 pre-freeze review decisions are already written into `PROJECT.md`, `specs/phase-0.md`, `CLAUDE.md`, `reference/` and `docs/decisions.md`, and this plan builds against those versions. No code exists yet, and the folder is not yet a git repo.

**Bootstrap check (done Oct 12):**
- Every file uses LF.
- No key-like strings anywhere.
- Reference tables:
  - `applicability.csv`: 135 rows.
  - `protection_layers.csv`: 26 rows, `relief_kind` set on 4.
  - `risk_matrix.csv`: 25 rows.
  - `reactive_pairs.csv`: still 303 valid pairs.
- The §9 example parses: no duplicate IDs, every valve is listed in its line's `components`, MX-1 is 350 / PSV-1 is 350, SIH `epa_groups` is [105].
- The only unexpected item is an empty `.qodo/` folder. The bootstrap `git add` names explicit paths, so it can't be committed, and PR 1 adds `.qodo/` to `.gitignore` (D8).

## Bhargavi's steps (not code)

| When | Step |
|---|---|
| Before PR 1 | Bootstrap commit per spec 0.0 (`git init -b main`, `git add <listed paths>`, review `git status`, commit, add remote, push). Turn on branch protection. Set the licence in the GitHub About panel. |
| After PR 1 merges, in every clone and worktree | `git config core.hooksPath scripts/hooks` |
| Oct 12 | Copy the kill-test #4 packages to `cases/dev/source/` and the answer keys to `cases/dev/keys/` |
| Oct 12 evening, after PR 3 and PR 4 | Set `$env:NEBIUS_API_KEY` and `$env:TAVILY_API_KEY` in the session, then run `python scripts/live_call.py opening-balance --usd <dashboard figure> --use development` and `python scripts/smoke_test.py --phase 0 --use development` (D5) |
| Oct 12 | 0.10: choose and contact the case writer; claim the second $25 grant if not yet claimed; send facilitator outreach |
| Oct 13 | Tick assumptions in `cases/dev/conversion-report.md`. Ask the City Winner attendance question in the Nebius Discord. |
| By G1 | 0.9: confirm on your machine that kill test #1 ran on tep-rust and that none of it, and no Operon code, enters the repo (I log your answer in `docs/decisions.md`). Case writer has started and owns `guideword-heldout`. Commit `budget/ledger-g1.jsonl`. |

**If time runs short:** G1 says only a missing schema or contract blocks Phase 1. So the priority order is PR 1 → 2 → 5 → 6 → 8 (schema and contract), then 3 → 4 (smoke test), then 7 (dev cases), then 9 (case template). Anything missed applies its §16 fallback and is logged in `docs/decisions.md`.

---

## Pull requests in order

| # | Branch | Spec items | Depends on | Target day |
|---|---|---|---|---|
| 1 | `phase-0/scaffold` | approved plan, 0.0 tree, 0.1 tooling and CI | bootstrap commit | Oct 12 |
| 2 | `phase-0/schema-core` | 0.5 enums, IDs, plant models | PR 1 | Oct 12 |
| 3 | `phase-0/config-live-call` | 0.2, 0.3 | PR 1 | Oct 12 |
| 4 | `phase-0/smoke-test` | 0.4 script; results after the run | PR 3 | Oct 12 (results Oct 12 evening) |
| 5 | `phase-0/reference-loaders` | 0.6 | PR 2 | Oct 13 |
| 6 | `phase-0/schema-validation` | 0.5 validation, record models, JSON Schema export, **schema freeze** | PR 2, PR 5, and the package survey below | Oct 13 |
| 7 | `phase-0/dev-cases` | 0.7 | PR 6, source packages | Oct 13 |
| 8 | `phase-0/contract-mock` | 0.8, tag `contract-v1` | PR 6 | Oct 13 |
| 9 | `phase-0/case-template` | 0.10 `docs/case-template.md` (D14) | PR 6 | Oct 13 |

- PRs 2 and 3 can run in parallel after PR 1. So can 7 and 8 after PR 6. Every PR is squash-merged by Bhargavi.
- **Package survey before the freeze (D13):** before PR 6 merges, I read the five dev-case packages (allowed; they are dev cases D–H, keys excluded) and list any fact the schema can't hold. Each gap that matters goes to you as a `contract/...` branch and PR, merged before PR 6 freezes the schema.
- **PR 9 `phase-0/case-template` (D14):** after the freeze, I draft `docs/case-template.md`, generic with no sources named, showing the plant file format and the answer key format. You review it.

**Every PR (CLAUDE.md §1, §7, §11, §12):**
- Run the test suite at the start of the session and report it if it is red.
- Restate the task and the files before touching them.
- Make small Conventional Commits, each with the Co-Authored-By line; review `git status` before every `git add` (never a blind `add -A`).
- Run the `CLAUDE.md` §8 command set.
- Tick its checkboxes in `specs/phase-0.md`.
- Log any decision in `docs/decisions.md`.
- Log any Token Factory or Nemotron friction in `docs/feedback-log.md`.
- Description covers: what changed, why, spec items, test evidence, anything left open.
- End every session with the §12 summary (done, tests, commits, not done, open questions, next step).
- Use `pathlib` for every path, inject a clock anywhere time matters (no sleeps in tests), and log through `guideword/logs.py`. `print` is allowed only for human-readable output in `scripts/` (D16).

---

## Per item

### 0.0 + 0.1 — PR 1 `phase-0/scaffold`

**First commits (docs only, after the approved plan):** the spec and rule changes from this review, each with a dated line in `docs/decisions.md`:
- **`specs/phase-0.md`:**
  - 0.0 tree gains `backend/guideword/logs.py` (D16).
  - 0.1 `requirements-dev.in` line becomes `-e ./backend` (D1); CI and hook also lint and type-check `scripts/` (D12).
  - 0.3 opening-balance command gains `--use development` (D5).
  - 0.5 adds the operating fact-ID form, value objects, and one normalisation function (D4, D10).
  - 0.8 adds: `POST /runs` returns 409 on an unconfirmed plant (D6); non-mock 501 with the phase named (D11); xlsx built from the fixture (D15).
  - 0.10: Claude Code drafts the case template (D14).
- **`PROJECT.md`:**
  - §9: operating fact IDs (D10).
  - §11: 409 on `POST /runs` (D6); 501 in non-mock mode (D11).
- **`CLAUDE.md`:**
  - §8: add `ruff format scripts; ruff check scripts; mypy scripts` (D12).
  - §9 Python: the logger is `guideword/logs.py`; `print` only for human-readable output in `scripts/` (D16).
- **`.gitignore`:** `.qodo/` under "editors and OS" (D8).

**Files**
- **Folder tree:** the full tree from spec 0.0. Folders with no files get `.gitkeep`; that includes `bench/replay/`, `cases/demo/recorded/` and `budget/` (gate snapshots only; the live ledger is git-ignored). Every `backend/guideword/*` package gets an empty `__init__.py`.
- **Python tooling:**
  - `backend/pyproject.toml`: package `guideword`, Python 3.12, ruff, mypy strict on `guideword/`, pytest config. `pythonpath` includes `../scripts` so tests can import the scripts.
  - `backend/requirements.in` / `requirements-dev.in` exactly as spec 0.1, with `-e ./backend` (D1). Always compiled and synced from the repo root. I reject the commit if a compiled `.txt` contains an absolute path (`file:///` or a drive letter); a test enforces this (`test_requirements.py::test_no_absolute_paths`).
- **Logger:** `backend/guideword/logs.py`, standard-library `logging` with a JSON formatter; no new dependency (D16).
- **Settings:** `backend/guideword/settings.py`, one pydantic-settings object reading `.env`. Fields: `nebius_api_key`, `nebius_base_url`, `tavily_api_key`, `global_budget_usd`, `database_url`, `guideword_mock`, `guideword_env` (`laptop` | `hosted`), `internal_advance_secret`. Keys are `SecretStr`. No run-cap field.
- **Test plumbing:** `backend/tests/conftest.py` holds the autouse network block (patches `socket.socket.connect` / `connect_ex`; loopback `127.0.0.1`, `::1`, `localhost` allowed).
- **Repo plumbing:**
  - `scripts/hooks/pre-commit`: POSIX `sh`; refuses on `main`; runs `python -m ruff format --check` and `ruff check` on staged Python files in `backend/` and `scripts/`, and `mypy scripts` (D12); refuses with "activate .venv first" if ruff is missing.
  - `.github/workflows/ci.yml`: on every push and PR:
    - backend `ruff format --check`, `ruff check` and `mypy` (strict), each run on `backend` and `scripts` (D12), then `pytest`;
    - frontend on Node 22: `npm ci`, lint, typecheck, test;
    - no secrets.
  - `docs/feedback-log.md`: the five seed entries (date, tool, what happened, what would help).
- **Frontend:** `frontend/` with Vite + React + TS strict, ESLint, Prettier, Vitest, placeholder `App.tsx`, `.nvmrc` = 22, `engines` set, committed `package-lock.json`. It is scaffolded here, and the frontend worktree takes over from `contract-v1`.

**Tests first**
- `test_network_block.py::test_non_loopback_connect_raises`
- `test_network_block.py::test_asyncio_loop_starts` (loopback allowed)
- `test_settings.py::test_repr_hides_keys` (`repr`, `str`, `model_dump_json`)
- `test_settings.py::test_reads_env_file` (temporary `.env`)
- `test_settings.py::test_no_run_cap_setting`
- `test_logs.py::test_json_format`: one log call emits one valid JSON line with level, logger name and message.
- `test_logs.py::test_no_print_in_package`: AST scan; no `print` call anywhere under `backend/guideword/`.
- `test_requirements.py::test_no_absolute_paths`
- `test_repo_tree.py::test_every_spec_folder_exists`: every folder in the spec 0.0 tree exists. It also checks that `bench/heldout/` does not exist and that `.gitignore` covers it.
- Frontend: one Vitest test that renders `App`.

`pyproject.toml` also turns on the Pydantic mypy plugin, which ships with pydantic, so it is not a new dependency.

**Manual checks (noted in the PR):** the hook refuses a commit on `main`; a fresh clone on Windows passes `pytest backend -q`.

**Dependencies:** as named in the spec, plus the five approved frontend packages (D2): `@vitejs/plugin-react`, `typescript-eslint`, `eslint-plugin-react-hooks`, `@testing-library/react`, `jsdom`. Each gets its one-line reason in the commit message.

### 0.5 (part 1) — PR 2 `phase-0/schema-core`

**Files**
- **`schema/enums.py`:** every enum in the 0.5 table, including Utility kind, Plant status, the trimmed Run status, Likelihood class, Risk rating, Budget use, override `answer`, and question kind `engineer`.
- **`schema/ids.py`:** pure builders and parsers.
  - `h()` = the first 16 hex characters of SHA-256 over canonical JSON (sorted keys, no whitespace, UTF-8, NFC).
  - One `normalise_text()` used for every hashed text in an ID (`ai:`, `eng:`, `rec:`, outside-library causes): NFC, Unicode dashes → `-`, non-breaking spaces → space, collapse whitespace, trim, casefold (D4).
  - Fact IDs: `<object id>.<field>` for top-level fields; nested value objects are cited by their parent's field (e.g. `PSV-1.discharge`); operating limits are cited down to one setpoint, `<target_id>.operating.<parameter>.<limit field>` (e.g. `MX-1.operating.temperature.trip_high`) (D10).
  - Plant, fact and section IDs: `S-<obj>`, split `S-<obj>~<first component>`, engineer `S~eng~<h>`, and merge keeps the lowest ID by string order.
  - Every question ID form, including `eng:`.
  - Run, finding, chain, LOPA, recommendation, evidence, model call, tool call, agent step and override IDs.
- **Run attempts:** `run_id(inputs, existing_attempts)` is a pure function. It takes the statuses of earlier attempts as an argument, so no database is needed.
- **`schema/plant.py`:** the plant models, all `extra="forbid"`.
  - Top level: `plant_id`, `schema_version`, and every §9 block including `utilities`.
  - `lines.is_hose`.
  - Chemical physics fields: `density_kg_m3`, `heat_capacity_kj_kg_k`, `vapor_pressure_points: list[{temp_c, pressure_kpaa}]`.
  - The ID pattern.
- **Fixture:** `backend/tests/schema/fixtures/example_mixing_unit.json`, copied from §9.

**Tests first** (`backend/tests/schema/`)
- **`test_ids.py`:**
  - `h()` matches a hand-computed value.
  - NFC-composed and decomposed text hash the same.
  - Key order doesn't change `h()`.
  - `pair:` is the same whichever order the chemicals are given.
  - Every question ID round-trips through build and parse.
  - Different causes, or the same cause on different components, give different finding IDs.
  - The same `check_coverage` arguments at different steps give different `tc:` IDs.
  - `ch:` ignores link order.
  - `rec:` and `eng:` are stable.
  - `normalise_text()`: one case each for an NFC difference, an en/em dash, a non-breaking space, repeated whitespace, leading and trailing space, and case. Each pair hashes the same, and text that really differs hashes differently.
  - Every builder that hashes text calls `normalise_text()` (AST check that no builder hashes raw text).
  - Fact IDs: build and parse round-trip for the top-level, value-object and `operating` forms.
  - Section IDs: split, engineer-added, merge-keeps-lowest.
  - Run attempts: an unfinished run returns the same ID; after a cancelled run the next start is `…:2`.
  - Two subprocesses give identical IDs.
  - AST scan: `ids.py` has no `random`, `uuid`, `itertools.count`, `time` or `datetime`.
- **`test_plant_models.py`:**
  - The example loads.
  - load → dump → load gives an identical object.
  - An unknown field is rejected.
  - An ID containing `.`, `:`, `~` or `+` is rejected.
- **`test_unit_suffixes.py`:**
  - Every numeric field has an allowed suffix (the §9 list) or is exempt (the seven `operating` limit fields, `epa_groups`, `cameo_groups`).
  - A temporary model with a bare numeric field makes the check fail.

### 0.2 + 0.3 — PR 3 `phase-0/config-live-call`

**Files**
- `config/models.yaml`, `config/routing.yaml`, `config/caps.yaml` exactly as spec 0.2. That includes `connector_max_input_tokens`, `section_suggest_cap_usd`, uses with their environments, and `phase_caps_usd: {"0": 0.65}`.
- `backend/guideword/config.py`: loaders and validation.
- **`scripts/live_call.py`:**
  - Exposes `chat`, `list_models`, `tavily_search`, `record_opening_balance` and a CLI. `--phase` and `--use` are required.
  - Estimates cost before sending: input = ceil(characters of messages and tool schemas ÷ 3.5), output = `max_tokens`, prices from `models.yaml`.
  - Refuses on the phase cap, the use allowance or the laptop allowance.
  - Records the real cost from returned usage.
  - Always writes `environment: laptop`.
  - The client and clock are injected.
- **`scripts/budget_status.py`:**
  - Shows spend by model, phase and use; remaining per use; Tavily searches; laptop remaining.
  - Prints `GLOBAL_BUDGET_USD` and the weekly-reconcile reminder.
  - Refuses to print "remaining" without an opening balance.
  - Every limit comes from settings and `caps.yaml`.
- `budget/ledger.jsonl` is not created in the repo; it is git-ignored and created on first write.

**Tests first**
- **`test_config.py`** — the loader rejects each of these:
  - an unknown tier;
  - a negative price;
  - a job mapped to a missing tier;
  - a fallback cycle;
  - use allowances that don't sum to `GLOBAL_BUDGET_USD`;
  - environment allowances that don't sum to it;
  - a use with an unknown environment;
  - per-environment use sums that don't match that environment's allowance.
- **`test_live_call.py`** (fake client):
  - The estimate matches a hand-computed example, including tool schemas.
  - Calls over the phase cap, over the use allowance and over the laptop allowance are each refused before sending (zero fake calls).
  - Calls with no `use`, an unknown `use`, or a phase with no entry in `phase_caps_usd` are refused (never a default cap).
  - The ledger is appended after success and not after failure.
  - A written line has `use` and `environment: laptop`, and contains no prompt text and no key.
  - A Tavily call writes `kind: tavily`, `searches`, `cost_usd: 0`.
  - The opening balance writes `kind: opening_balance` and counts toward the laptop total.
  - A missing API key gives a clear error that names the setting, never a value, and no call is attempted.
  - `live_call` has no retry loop (a test checks a failed fake call is attempted exactly once).
- **`test_budget_status.py`:**
  - Refuses "remaining" without an opening balance.
  - Changing `caps.yaml` changes the output (no literals).
- **`test_http_allowlist.py`:**
  - The allow-list constant from 0.3 passes.
  - A temporary file importing `openai` outside the allow-list makes it fail.

### 0.4 — PR 4 `phase-0/smoke-test`

**Files**
- **`scripts/smoke_test.py`:** T1–T14, every paid call through `live_call.py`.
  - Fixed, harmless prompts with no plant or accident content.
  - T14 uses about 100k tokens of neutral filler (a repeated numbered list) with `max_tokens` 50.
  - It saves each raw response to `docs/smoke/` with headers stripped.
  - It stops at the first refusal from `live_call`.
  - No retries anywhere. The parallel calls in T9 and T13 are a fixed 5 and 3, not a loop that could grow.
  - T3, T4 and T11 outputs are validated with a Pydantic model (`verdict`, `reason` ≤ 200 characters). A `finish_reason=length` response is recorded as a failure and never parsed.
  - Each record holds latency, tokens, real cost, `finish_reason` and where reasoning appeared.
- **After the run:**
  - `docs/smoke-test-results.md`: a model × test table with every cell filled, cost per call, total, and a Decisions section covering:
    - structured output per model;
    - the bulk path (T11);
    - Ultra tool calling (T12), or the JSON next-action fallback;
    - reasoning off, and where reasoning text appears;
    - safe concurrency per model;
    - T14 long input;
    - confirmed IDs.
  - Confirmed IDs written back to `config/models.yaml`.
  - Fallbacks applied per `PROJECT.md` §16 and logged in `docs/decisions.md`.
  - New friction added to `docs/feedback-log.md`.

**Tests first** (fake client)
- `test_smoke_test.py::test_all_calls_go_through_live_call`
- `test_saved_responses_have_no_keys` (headers stripped, key-like values rejected)
- `test_t8_length_not_parsed` (a `finish_reason=length` response is recorded as a failure and never parsed)
- `test_stops_on_refusal`

### 0.6 — PR 5 `phase-0/reference-loaders`

**Files:** `backend/guideword/reference/`, with one row model and loader per table (including `risk_matrix`), a `ReferenceSet`, and a per-file SHA-256 version hash. The applicability loader exposes the `proc:` guideword list. The reactivity API returns `not_listed` for missing pairs. Tests go in `backend/tests/reference/`.

**Tests first** — one per 0.6 acceptance line:
- every header equals the frozen header (including `relief_kind` and `risk_matrix`);
- every row has a non-empty source;
- no CR byte in any file;
- applicability: no duplicates, values in their enums, every section type has a row, and the `procedure` rows are exactly the five procedure guidewords;
- causes: unique IDs, `initiating_event_id` exists, `applies_to` values valid, failing type in the enum;
- frequencies > 0; probabilities in (0, 1]; flags 0 or 1; `pfd_if_isolatable` empty or in range;
- the unit is exposed, and a non-`per_year` value is never returned as a yearly frequency;
- S1–S5 appear once in each table;
- likelihood bands are contiguous from 0 with an open top;
- `risk_matrix`: all 25 pairs once each, ratings valid;
- `relief_kind`: empty or a relief kind, each kind on exactly one row;
- reactive groups: 41 rows, `do_not_mix` 0 or 1;
- pairs: groups exist, codes valid, unique, none with group 107;
- a missing pair returns `not_listed`;
- the hash changes when a file changes.

### 0.5 (part 2) — PR 6 `phase-0/schema-validation` (freeze)

**Files**
- **`schema/validate.py`:** errors and warnings returned separately, each naming the offending ID; the `ReferenceSet` is an input.
  - Errors 1–9:
    - Error 2 covers `utilities.location_id`, and line endpoints that point to equipment or utilities.
    - Error 9: a valve's `on_line_id` names a line whose `components` doesn't list it.
  - Warnings 1–8 unchanged.
  - `heat_sources`, `injection_points`, `discharge`, `vapor_pressure_points` and `operating` rows are value objects with no ID (D10). Error 1 (duplicate ID) and error 8 (ID pattern) apply only to plant objects.
  - Error 6 (provenance keys) accepts an object ID, `<object id>.<top-level field>`, or `<target_id>.operating.<parameter>.<limit field>` where that operating row and limit exist.
- **`schema/records.py`:**
  - Plant (with `status`) and Run (`label`, section snapshot).
  - PlantFact, Section, Question.
  - Finding, with `failing_component_ids` of `min_length=1`.
  - AgentStep, ModelCall, ToolCall, Chain, LopaRecord.
  - Recommendation.
  - Evidence, Override, Event.
  - SpendEntry (with `use`).
- **`scripts/export_schemas.py`:** writes `contract/schemas/plant.schema.json` (the name in PROJECT.md §9) plus one file per record model. API request and response models are added in PR 8, when they exist.

**Tests first**
- One test per error (1–9) and per warning (1–8), each with exactly that message and the offending ID.
- No warning when the optional `lines.length_m` or `planned_work.lifts_per_year` is missing.
- Provenance (D10):
  - `MX-1.operating.temperature.trip_high` is accepted when that row and limit exist.
  - It is rejected when the parameter row is missing, or when the limit field is unknown or unset.
  - `PSV-1.discharge` is accepted.
  - `PSV-1.discharge.location_id` is rejected.
- The example plant validates with no errors.
- An empty `failing_component_ids` fails.
- The exported schemas match the models (the test regenerates and compares).

**Freeze:** after merge, schema changes go only through `contract/...` branches.

### 0.7 — PR 7 `phase-0/dev-cases`

**Files**
- `cases/dev/case_d.json` … `case_h.json`, unrelated equipment kept, facts only from the packages. A utility object is created only where the package names that utility, with the package as provenance; otherwise it is proposed in the report as an assumption (D7).
- `cases/dev/conversion-report.md`, one section per case: proposed assumptions (fact ID, value, why needed, checkbox); package facts the schema can't hold, quoted, with the block that would need to change; remaining warnings.
- `backend/tests/cases/test_dev_cases.py`.

**Tests first**
- All five cases validate with no errors.
- Every `"assumed"` provenance entry matches a ticked `- [x]` report line.

**Rules**
- No assumed value goes into a file until you have ticked it.
- I don't open `cases/dev/keys/` while converting, so no answer hint leaks into a plant file. The packages are neutral, with distractors, and the conversion keeps them that way.

### 0.8 — PR 8 `phase-0/contract-mock`

**Files**
- **API app:** `backend/guideword/api/`, a FastAPI app with every §11 endpoint, including `POST /runs/{id}/questions`, with request and response models.
  - The clock is injected.
  - `GUIDEWORD_MOCK=1` serves `contract/fixtures/`.
  - Non-mock mode (`GUIDEWORD_MOCK=0`): every endpoint returns 501 naming the phase that will build it, and the contract documents this (D11).
  - `POST /runs` on a plant that isn't `sections_confirmed` returns 409 "sections not confirmed", documented in the contract (D6). Mock Plant A is confirmed; a test-only unconfirmed plant exercises the 409.
  - `advance` checks `X-Internal-Secret`; in mock mode it returns 202 and does nothing.
  - Mock overrides are echoed back, not stored.
  - `GET /runs/{id}/export.xlsx` is built at request time from the worksheet fixture with `openpyxl`; no binary is committed (D15).
- **Fixtures:** "Mock Plant A", clearly fictional, with sections, questions (including one `eng:`), findings, one chain, LOPA records, a recommendation, evidence, coverage, events and budget. Every fixture has `label.kind = "mock"` and describes no real accident.
- **Tests:** `backend/tests/contract/`. The 403 test injects a `recorded` run from a **test-only** fixture in `backend/tests/contract/`, so `contract/fixtures/` stays mock-only.
- **Exports:** `scripts/export_openapi.py` → `contract/openapi.json`. Re-run `export_schemas.py` so the API models are exported too.
- **Frontend types:** `npm run gen:types` generates `frontend/src/api/types.ts` with `openapi-typescript`.

**Tests first**
- The route list equals the §11 table exactly; the test fails on a missing or extra route.
- Every mock response validates against its model, and every response model has a fixture. `export.xlsx` is the only exempt route, named in the test (D15).
- `POST /runs` on an unconfirmed plant returns 409 (D6).
- With `GUIDEWORD_MOCK=0`, every route returns 501 and the body names the phase (D11).
- Every run-related mock response has `label.kind == "mock"`.
- `advance` without the secret returns 401; with it in mock mode, 202.
- When `internal_advance_secret` is empty in settings, every `advance` call returns 401 (an empty secret never matches).
- `export.xlsx` in mock mode returns a valid workbook with the §5 Step 8 column headers (D15).
- An override on a recorded run returns 403.
- `POST /runs/{id}/questions` returns an `eng:` question with origin `engineer` and status open.
- An override with `answer` is echoed back.
- Mock events are released over about 20 s of injected time, counted from the first poll; the test runs in under a second.
- `openapi.json` and the exported schemas match the app.
- The frontend typechecks with the generated types.

**Tag:** `contract-v1` on `main` after merge.

---

## Decisions from the plan review (Bhargavi, Oct 12)

Each one gets a dated line in `docs/decisions.md` in PR 1's first commits.

| # | Question | Decision |
|---|---|---|
| D1 | Editable install path | `-e ./backend`; always compile and sync from the repo root; reject the commit if a compiled line contains an absolute path (tested). |
| D2 | Frontend supporting packages | Approved: `@vitejs/plugin-react`, `typescript-eslint`, `eslint-plugin-react-hooks`, `@testing-library/react`, `jsdom`. |
| D3 | `before` / `after` in the Guideword enum | **Kept.** They are standard IEC 61882 vocabulary, the applicability table is engineer-editable, and removing them later would be a contract change. |
| D4 | Text normalisation for hashed IDs | One function, used for every hashed ID, with tests: NFC, Unicode dashes → `-`, non-breaking spaces → space, collapse whitespace, trim, casefold. |
| D5 | `use` for the opening balance and the smoke test | Both `development`; add `--use` to the commands. |
| D6 | `POST /runs` on an unconfirmed plant | 409, in the contract. |
| D7 | Utilities in dev cases | Only where the package names them, with the package as provenance; otherwise proposed as an assumption (the no-invented-facts rule). |
| D8 | `.qodo/` | Ignored in `.gitignore`. |
| D9 | Run status `draft` | Kept, meaning "run created, setup not yet done". |
| D10 | Value objects and fact IDs | `heat_sources`, `injection_points`, `discharge`, `vapor_pressure_points` and `operating` rows are value objects inside their parent. Operating facts are cited down to the single limit: `<target_id>.operating.<parameter>.<limit field>` (e.g. `MX-1.operating.temperature.trip_high`), so LOPA and physics cite one setpoint. No `id` on operating rows (error 4 already makes target + parameter unique). Provenance accepts this form. |
| D11 | Non-mock API in Phase 0 | 501 naming the phase that will build it, documented in the contract. |
| D12 | Linting `scripts/` | ruff and mypy on `scripts/`, in CLAUDE.md §8, CI and the hook. |
| D13 | Package survey before the freeze | Yes. Schema gaps are raised as a `contract/...` change before the freeze. |
| D14 | `docs/case-template.md` | Claude Code drafts it after the freeze: generic, no sources named, showing the plant file format and the answer key format. Bhargavi reviews it. |
| D15 | Mock `export.xlsx` | Built at request time from the worksheet fixture; that route is exempt from the fixture test. |
| D16 | Logger | `guideword/logs.py`, standard `logging` with a JSON formatter; `print` only for human-readable output in `scripts/`; added to the spec tree. |

No open questions remain.

---

## Not doing (near the scope line)

- No section rules, question builder or counts (Phase 1), even though the Oct 12 decisions define them.
- No relief-credit or LOPA code (Phase 3). Phase 0 only loads and checks `relief_kind`.
- No interpolation or physics code (Phase 4). Phase 0 only adds the schema fields.
- No risk-rating lookup or screening code (Phase 2). Phase 0 only loads and checks `risk_matrix.csv`.
- No `reactivity_lookup` tool (Phase 2). Phase 0 only provides the loader API that returns `not_listed`.
- No gateway, agents, orchestrator, `spend_ledger` table, database models, precedent index, demo plants, simulator, deployment, CORS or proxy setup, README changes or video script.
- No change to reference values. No reading of held-out material or accident reports beyond the dev-case packages.
- No new top-level folders beyond the 0.0 tree.

## Live calls and spend

| Step | Who runs it | Expected cost |
|---|---|---|
| Opening balance | Bhargavi | $0 (records past spend) |
| Smoke test T1–T13 | Bhargavi | about $0.30–0.50 |
| Smoke test T14 (Ultra, ~100k input tokens) | Bhargavi | about $0.10 |
| Tavily T10 | Bhargavi | 1 search (separate Tavily credits) |
| **Phase 0 total** | | **≤ $0.65, enforced by `phase_caps_usd`** |

Every other test and script uses fake clients, and the network is blocked in tests.

## Verification

- **Per PR:** run the `CLAUDE.md` §8 commands, including ruff and mypy on `scripts/` (D12). CI must be green before you merge.
- **PR 1:**
  - Fresh-clone check on Windows: `conda deactivate`, create the venv, `pip-sync`, `pytest backend -q`.
  - `npm ci`, then lint, typecheck and test in `frontend/` on Node 22.
  - Confirm by hand that the hook refuses a commit on `main`.
- **Line endings:** `git ls-files --eol` shows `i/lf` for every text file.
- **`main` history:** `git log --first-parent main` shows only the bootstrap commit without a `(#N)` suffix.
- **G1:**
  - CI green on `main`, licence visible.
  - Smoke-test spend ≤ $0.65 per `budget_status.py`; opening balance recorded.
  - The T12 decision is recorded.
  - The schema is frozen and `contract-v1` is tagged.
  - Reference loaders pass on every table.
  - All five dev cases validate and every assumption is ticked.
  - Case writer started.
  - Bhargavi commits `budget/ledger-g1.jsonl`.
