# Phase 0 — Foundations

**Dates:** Oct 12–14, 2026 **Gate:** G1, Oct 14 morning
**Live-call budget for this phase:** $0.65 (smoke test only, including the T14 long-input check). Everything else makes zero paid calls.
**Source of truth:** `PROJECT.md`. If this spec and `PROJECT.md` disagree, stop and ask.

## Goal

Everything later phases stand on exists and is frozen: the repo and its folder structure, tooling and CI, proof of what each Nemotron model on Token Factory actually supports, the plant schema and all record types, the reference tables with loaders, the dev cases in the new format, and the API contract with a mock server.

**What the video shows from this phase:** nothing directly. Smoke-test results feed the "how we use Nemotron" section and the feedback write-up.

## In scope

| # | Item | Built by |
|---|---|---|
| 0.0 | Bootstrap commit and full folder structure | Bhargavi (commit), Claude Code (folders) |
| 0.1 | Tooling and CI | Claude Code |
| 0.2 | Price, routing, caps and budget config | Claude Code |
| 0.3 | `scripts/live_call.py` and the budget ledger | Claude Code |
| 0.4 | Token Factory and Tavily smoke test | Claude Code writes, Bhargavi runs |
| 0.5 | Schema package (plant file, records, enums, IDs) | Claude Code |
| 0.6 | Reference table loaders and validation | Cowork data (done), Claude Code loaders |
| 0.7 | Dev cases D–H as plant files, with conversion reports | Claude Code converts, Bhargavi approves |
| 0.8 | API contract and mock server | Claude Code |
| 0.9 | Feasibility (remaining items) | Cowork, Bhargavi |
| 0.10 | Non-build tasks | Bhargavi |

## Out of scope

Section rules, question builder, gateway, agents, orchestrator, LOPA engine, connector, ranking, frontend screens, simulator wrapper, precedent index, demo plants, deployment, DEXPI importer, video script (Phase 1). Do not start any of them. Empty package folders for them are created in 0.0; nothing else.

---

## 0.0 Bootstrap commit and folder structure

**Bootstrap rule.** An empty repo cannot satisfy both "never commit to `main`" and "CI green on `main`". So exactly one commit goes to `main` directly: the bootstrap commit, made by Bhargavi, containing only docs and config (no code). Every commit after it goes through a branch and pull request.

Bootstrap commit contents (all already written by Cowork):
`PROJECT.md`, `CLAUDE.md`, `specs/phase-0.md`, `reference/*`, `docs/decisions.md`, `.gitignore`, `.gitattributes`, `.env.example`, `LICENSE` (Apache 2.0 text), `README.md` (one paragraph).

```powershell
git init -b main
git add PROJECT.md CLAUDE.md specs reference docs .gitignore .gitattributes .env.example LICENSE README.md
git status                     # review: no .env, no keys
git commit -m "chore: bootstrap repo with plan, rules and reference data"
git remote add origin https://github.com/<you>/guideword.git
git push -u origin main
git switch -c phase-0/scaffold
```

After the push: turn on branch protection for `main` (require a pull request and green CI; no force pushes). GitHub enforces this on public repos and on paid plans. If the repo stays private on GitHub Free, the rule is enforced locally by the `pre-commit` hook from 0.1 (`git config core.hooksPath scripts/hooks`), which refuses any commit on `main`.

**Folder structure.** Claude Code creates every folder below on `phase-0/scaffold`. Folders with no files yet get a `.gitkeep`. Python packages get an empty `__init__.py`. This is the whole tree for the project; later phases fill it and do not add top-level folders.

```
guideword/
├── .github/workflows/ci.yml          CI (0.1)
├── .gitattributes                    * text=auto eol=lf
├── .gitignore
├── .env.example
├── LICENSE                           Apache 2.0
├── README.md
├── CLAUDE.md
├── PROJECT.md
├── specs/                            phase-0.md … phase-7.md
├── backend/
│   ├── pyproject.toml                package, ruff, mypy, pytest config
│   ├── requirements.in / .txt        runtime deps (pinned .txt via pip-compile)
│   ├── requirements-dev.in / .txt    dev deps
│   ├── guideword/
│   │   ├── __init__.py
│   │   ├── settings.py               the one settings object (0.1)
│   │   ├── config.py                 loaders for config/*.yaml (0.2)
│   │   ├── logs.py                   the structured logger: stdlib logging, JSON formatter (0.1)
│   │   ├── schema/                   plant + record models, enums, IDs (0.5)
│   │   ├── reference/                table loaders, version hashes (0.6)
│   │   ├── api/                      FastAPI app, mock mode (0.8)
│   │   ├── sections/                 Phase 1
│   │   ├── questions/                Phase 1
│   │   ├── gateway/                  Phase 2
│   │   ├── orchestrator/             Phase 2
│   │   ├── specialists/              Phase 2
│   │   ├── tools/                    Phase 2–4
│   │   ├── ranking/                  Phase 2–3
│   │   ├── runs/                     Phase 2
│   │   ├── lopa/                     Phase 3
│   │   ├── connector/                Phase 3
│   │   ├── export/                   Phase 3
│   │   ├── simulator/                Phase 4
│   │   ├── importers/                reserved (DEXPI, after the hackathon)
│   │   └── bench/                    Phase 6
│   └── tests/
│       ├── conftest.py               blocks network in every test (0.1)
│       ├── test_settings.py
│       ├── test_config.py            (0.2)
│       ├── test_live_call.py         (0.3)
│       ├── test_http_allowlist.py    (0.3)
│       ├── schema/                   (0.5)
│       ├── reference/                (0.6)
│       ├── cases/                    (0.7)
│       └── contract/                 (0.8)
├── frontend/                         Vite + React + TypeScript (0.1); screens in Phase 5
│   ├── package.json, package-lock.json, tsconfig.json, vite.config.ts
│   ├── .nvmrc                        22
│   └── src/
│       ├── api/types.ts              generated from contract/openapi.json (0.8)
│       └── App.tsx                   placeholder page
├── reference/                        CSV tables + sources.md (data from Cowork)
├── cases/
│   ├── dev/                          case_d.json … case_h.json (0.7)
│   │   ├── keys/                     dev answer keys (not secret)
│   │   ├── source/                   kill-test #4 packages, copied by Bhargavi
│   │   └── conversion-report.md      (0.7)
│   └── demo/                         Phase 4 (Tennessee Eastman, Williams Geismar)
│       └── recorded/                 recorded demo run export, Phase 7 (no keys)
├── prompts/                          <agent>/<version>.md, Phase 2
├── config/
│   ├── models.yaml                   (0.2)
│   ├── routing.yaml                  (0.2)
│   └── caps.yaml                     (0.2)
├── contract/
│   ├── openapi.json                  (0.8)
│   ├── schemas/                      JSON Schemas (0.5)
│   └── fixtures/                     mock responses (0.8)
├── scripts/
│   ├── live_call.py                  (0.3)
│   ├── budget_status.py              (0.3)
│   ├── smoke_test.py                 (0.4)
│   ├── export_schemas.py             (0.5)
│   ├── export_openapi.py             (0.8)
│   └── hooks/pre-commit              refuses commits on main (0.1)
├── budget/
│   ├── ledger.jsonl                  live laptop ledger, git-ignored (0.3)
│   └── ledger-<gate>.jsonl           snapshot committed by Bhargavi at each gate
├── docs/
│   ├── decisions.md
│   ├── feedback-log.md               (0.1)
│   ├── smoke-test-results.md         (0.4)
│   ├── smoke/                        raw smoke responses, no keys (0.4)
│   └── case-template.md              generic, no sources named (0.10)
└── bench/                            runner config and published results, Phase 6
    └── replay/                       committed replay fixtures per case for the CI replay test (no keys)
```

Never in this repo before G3: held-out cases, held-out keys, the case writer brief. They live in `guideword-heldout`, which the case writer creates and owns.

**Acceptance**
- [ ] The bootstrap commit is the only commit on `main` not made through a pull request: every later commit in `git log --first-parent main` ends with GitHub's `(#<PR number>)` suffix from the squash merge. (Note 2026-10-13: PR #2 was merged with a merge commit, "Merge pull request #2 …"; it did go through a PR. Later PRs are squash-merged.)
- [x] Every folder in the tree exists on `phase-0/scaffold`.
- [x] `git ls-files --eol` shows `i/lf` for every text file.

## 0.1 Tooling and CI

**Build**
- `backend/pyproject.toml` for the `guideword` package (Python 3.12), with ruff, mypy (strict on `guideword/`) and pytest config.
- `backend/requirements.in`: pydantic, pydantic-settings, fastapi, uvicorn, httpx, openai, sqlalchemy, pyyaml, openpyxl, tavily-python. `backend/requirements-dev.in`: pytest, pytest-asyncio, ruff, mypy, pip-tools, respx, types-PyYAML, and `-e ./backend` (the `guideword` package itself, so `pip-sync` keeps it installed and `scripts/` can import it). pip resolves `-e` paths from the current directory, so compile and sync always run from the repo root; a compiled `.txt` containing an absolute path (`file:///` or a drive letter) is rejected by a test. Compile both to pinned `.txt` with pip-compile. No other dependency without Bhargavi's OK.
- `backend/guideword/logs.py`: the structured logger, standard-library `logging` with a JSON formatter (no new dependency). The package never calls `print`; `print` is allowed only for human-readable output in `scripts/` (budget table, smoke summary).
- `backend/guideword/settings.py`: one pydantic-settings object reading `.env`: `nebius_api_key`, `nebius_base_url`, `tavily_api_key`, `global_budget_usd`, `database_url`, `guideword_mock` (bool), `guideword_env` (`laptop` | `hosted`), `internal_advance_secret`. Keys are `SecretStr` and never appear in `repr` or logs. The per-run spend cap is **not** a setting: its only source is `config/caps.yaml` (0.2), so there is one value, not two.
- `backend/tests/conftest.py`: an autouse fixture that patches `socket.socket.connect` (and `connect_ex`) to raise for any address that is not loopback (`127.0.0.1`, `::1`, `localhost`), so no test can reach the network (no new dependency). Loopback stays allowed because asyncio on Windows builds its event loop from a localhost `socketpair()`; blocking it would break every async and `TestClient` test on Bhargavi's machine.
- `frontend/`: Vite + React + TypeScript, strict mode, ESLint, Prettier, Vitest, one placeholder page. Node 22 LTS (`.nvmrc`, `engines` in `package.json`). `npm ci` works from the lockfile.
- `scripts/hooks/pre-commit`: a POSIX `sh` script (Git for Windows runs hooks with its bundled `sh`, not PowerShell). Refuses a commit when the current branch is `main`; runs `python -m ruff format --check` and `python -m ruff check` on staged Python files in `backend/` and `scripts/`, and `python -m mypy scripts`. If `python -m ruff` is not available (venv not active), it refuses with the message "activate .venv first" rather than skipping the checks.
- `docs/feedback-log.md` seeded with five entries (date, tool, what happened, what would help): wrong key returning 401; answers cut off at the token limit; Unicode hyphens breaking keyword scoring; Nano slow with very long reasoning; catalog deprecations with no automatic rerouting.
- `.github/workflows/ci.yml` on every push and pull request: backend `ruff format --check`, `ruff check` and `mypy` on both `backend` and `scripts` (scripts hold the only paid-call code), then `pytest`; frontend (Node 22) `npm ci`, `lint`, `typecheck`, `test`. No secrets in CI.

**Acceptance**
- [x] Fresh clone on Windows: `conda deactivate`, `py -3.12 -m venv .venv`, activate, `pip-sync backend/requirements.txt backend/requirements-dev.txt`, `pytest backend -q` passes. (Checked 2026-10-13 on a fresh clone of `main`: 80 passed.)
- [x] `npm ci && npm run lint && npm run typecheck && npm test` passes in `frontend/` on Node 22.
- [x] A test proves a network call inside a test fails, and a second test proves an asyncio event loop still starts (loopback allowed).
- [x] Settings `repr` contains no key value (test).
- [x] The pre-commit hook refuses a commit on `main` (checked by hand once, noted in the PR).
- [x] CI green on the PR and on `main` after merge. Licence shown in the GitHub About panel. (2026-10-13: backend and frontend jobs green on `ac61124`; GitHub reports Apache-2.0.)

## 0.2 Config

**Build** (`config/`, each loaded and validated by `backend/guideword/config.py`):

- `models.yaml`: the four tiers, expected catalog ID, price per 1M tokens as of Oct 11, 2026. IDs are expectations; code always confirms them against the live model list.

  | Tier | Expected ID | Input $/1M | Output $/1M |
  |---|---|---|---|
  | ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1.00 | 3.00 |
  | super | `nvidia/nemotron-3-super-120b-a12b` | 0.30 | 0.90 |
  | lightning | `nvidia/Nemotron-3_5-Lightning` | 0.06 | 0.24 |
  | nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 0.06 | 0.24 |

- `routing.yaml`: job → tier. Starting values: `orchestrator: ultra`, `connector: ultra`, `lopa_argument: ultra`, `severity_reason: ultra`, `recommendation: ultra`, `unsure_answer: ultra`, `section_suggestion: super`, `specialist_hard: super`, `specialist_bulk: lightning`, `not_credible: lightning`, `extraction: lightning`. No job is routed to nano; it stays in `models.yaml` for the four-tier comparison. Fallback order: `nano → lightning → super → ultra`.
- `caps.yaml`:
  - run caps: `run_spend_cap_usd: 1.00`, `orchestrator_max_steps: 60`, `specialist_max_tool_steps: 2`, `lopa_top_n: 10`, `evidence_top_n: 5`, `question_max_attempts: 2`, `connector_max_input_tokens: 80000`;
  - plant caps: `section_suggest_cap_usd: 0.05` (the Super section-suggestion call, which runs outside any run);
  - budget allowances by use, each with its environment (`PROJECT.md` §7): development 5 (laptop), test_5 4 (laptop), benchmark 8 (laptop), video 2 (laptop), demo_recording 1 (hosted), judging 3 (hosted), buffer 2 (hosted);
  - by environment (`PROJECT.md` §11 hosting): laptop 19, hosted 6;
  - live-call phase caps: `phase_caps_usd: {"0": 0.65}` (later specs add their phase).

**Acceptance (tests first)**
- [x] Loaders reject: an unknown tier, a negative price, a job mapped to a missing tier, a fallback cycle, use allowances that do not sum to `GLOBAL_BUDGET_USD`, environment allowances that do not sum to it, a use whose environment is unknown, and use allowances per environment that do not sum to that environment's allowance.

## 0.3 Live-call script and budget ledger

`scripts/live_call.py` is the only code allowed to call Token Factory or Tavily **until the Phase 2 gateway exists**. From Phase 2, live calls go through `guideword/gateway` and `guideword/tools`, still started only by Bhargavi.

**Build**
- `live_call.py` exposes `chat(...)`, `list_models()`, `tavily_search(...)` and `record_opening_balance(...)`, plus a small CLI. Reads keys through settings. Every model call:
  1. **Estimates cost** before sending: input tokens = ceil(message text characters ÷ 2.5 + tool schema and tool call characters ÷ 1.25) + 32 per request; output tokens = the requested `max_tokens`; prices from `models.yaml`. (Revised 2026-10-13: the original ÷ 3.5 under-estimated every billed smoke call; the revised rule is an upper bound on all 32 of them, checked by `test_estimate_upper_bound.py`.)
  2. **Refuses** before sending if phase spend + estimate > the phase cap (`--phase`, cap from `caps.yaml`), or use spend + estimate > that use's allowance (`--use`, required, allowance from `caps.yaml`), or laptop spend + estimate > the laptop allowance ($19, from `caps.yaml`).
  3. Sends, then records the **real** cost from the returned token usage.
- `budget/ledger.jsonl` (**git-ignored**: one local file that survives branch switches; no keys, no prompts, no responses). At each gate Bhargavi commits a snapshot, `budget/ledger-<gate>.jsonl`. One JSON object per line:
  `ts`, `kind` (`model` | `tavily` | `opening_balance`), `environment` (`laptop` | `hosted`), `phase`, `use` (required; a use from `caps.yaml`), `model` (or null), `input_tokens`, `output_tokens`, `searches`, `cost_usd`, `script`, `purpose`.
  Tavily calls record `searches` and `cost_usd: 0` (Tavily credits are separate from the $25).
  `ledger.jsonl` is the **laptop** ledger: `live_call.py` always writes `environment: laptop`. Hosted spend cannot go to a file (the Vercel filesystem is read-only); from Phase 2 it goes to the `spend_ledger` table (`PROJECT.md` §11) with the same fields. **Each environment enforces its own allowance and never reads the other's ledger** (laptop $19 here, hosted $6 in `spend_ledger`); the weekly Token Factory dashboard check reconciles the two.
- **Opening balance:** before the smoke test, Bhargavi reads the spent-to-date figure on the Token Factory dashboard (earlier kill tests) and records it with `python scripts/live_call.py opening-balance --usd <amount> --use development`. It counts against the laptop allowance and the `development` use. The smoke test also runs with `--use development`. Without it, `budget_status` refuses to print "remaining".
- `scripts/budget_status.py`: laptop spend by model, by phase and by use (with each use's remaining allowance), Tavily searches, and laptop remaining = laptop allowance − laptop total. It also prints `GLOBAL_BUDGET_USD` and the reminder to reconcile with the dashboard weekly. Reads every limit from settings and `caps.yaml`, never a literal.

**HTTP allow-list test** (`backend/tests/test_http_allowlist.py`): scans every `.py` file under `backend/` and `scripts/` for imports of `openai`, `tavily` and `httpx`. Allowed:

| Import | Phase 0 allowed files | Added from Phase 2 |
|---|---|---|
| `openai` | `scripts/live_call.py` | `backend/guideword/gateway/**` |
| `tavily` | `scripts/live_call.py` | `backend/guideword/tools/**` |
| `httpx` | `scripts/live_call.py`, `backend/tests/**` (FastAPI TestClient, respx) | `backend/guideword/gateway/**`, `backend/guideword/tools/**` |

The allow-list is a constant in that test. Changing it is a stop-and-ask change.

**Acceptance (tests first, fake client only)**
- [x] Cost estimate matches a hand-computed example.
- [x] A call over the phase cap, a call over its use's allowance, and a call over the laptop allowance are each refused before sending (the fake client records zero calls). A call without a `use` is refused.
- [x] The ledger is appended after success and not after failure; it never contains prompt text or a key (test checks the written line).
- [x] `budget_status` refuses "remaining" without an opening balance and reads the limit from settings.
- [x] The allow-list test passes, and fails when a forbidden import is added to a temp file.

## 0.4 Smoke test (written by Claude Code, run by Bhargavi)

`scripts/smoke_test.py` uses `live_call.py` for every paid call. Short, fixed, harmless prompts. **No accident or plant-specific content in any prompt.** Run with `--phase 0 --use development`.

| # | Test | Models | Records |
|---|---|---|---|
| T1 | `GET /v1/models` | — | Which expected IDs exist, exact IDs; whether the response includes prices or context length (copy any that are returned) |
| T2 | Plain call "Reply with the word OK", `max_tokens` 400 | all four | Latency, tokens, real cost, `finish_reason`; where reasoning appears (`content`, `reasoning_content`, `<think>` tags) |
| T3 | `response_format` = `json_schema` (strict), schema `{"verdict": enum[yes,no], "reason": string ≤ 200 chars}` | all four | Accepted or rejected; output valid |
| T4 | `response_format` = `json_object`, schema described in the prompt | all four | Same as T3 |
| T5 | Reasoning off: `extra_body={"chat_template_kwargs": {"enable_thinking": false}}` | all four | Accepted or rejected; output tokens vs T2 |
| T6 | Reasoning budget: `extra_body={"reasoning_budget": 512}` | ultra, super | Accepted or rejected; output tokens vs T2 |
| T7 | Tool calling, one tool `lookup_unit(name)` returning a fixed value; send the result back; final answer | all four | `tool_calls` returned; arguments valid JSON; follow-up used the result |
| T8 | Truncation: reasoning on, `max_tokens` 32 | lightning | `finish_reason` = `length` detectable; no partial JSON accepted |
| T9 | Concurrency: 5 parallel T2 calls | lightning | Any 429 or 5xx; latency spread |
| T10 | Tavily: one search "how does water react with sodium metal", max 3 results | — | Works; result shape; any usage info |
| **T11** | **Bulk path:** `json_schema` (strict) **with reasoning off** | lightning, nano | Accepted; valid; output tokens |
| **T12** | **Orchestrator path:** reasoning on, **two tools** (`lookup_unit`, `count_items`), once with `tool_choice: "auto"` and once with `tool_choice: "required"` | ultra | Which tool chosen; arguments valid; whether `required` is accepted; where reasoning appears |
| **T13** | Concurrency: 3 parallel T2 calls | ultra | Any 429 or 5xx; latency spread |
| **T14** | Long input: one call with about 100k input tokens of harmless filler, `max_tokens` 50 | ultra | Accepted or rejected; real input tokens; real cost (expected ≈ $0.10) |

**Output**
- `docs/smoke-test-results.md`: model × test table (pass, fail, notes), measured cost per call, total spent, and a **Decisions** section applying the fallbacks in `PROJECT.md` §16.
- Raw responses in `docs/smoke/` as JSON (no keys, no headers).

**Acceptance**
- [x] Smoke-test spend ≤ $0.65 per `budget_status.py`.
- [x] Every cell filled.
- [x] Decisions written for: structured output method per model; bulk path method (T11); orchestrator tool calling on Ultra (T12), or the JSON "next action" fallback; how reasoning is turned off; where reasoning text appears; safe concurrency per model; whether Ultra accepts ~100k input tokens (T14) and its real cost; confirmed model IDs written back to `config/models.yaml`.
- [x] New friction added to `docs/feedback-log.md`.

## 0.5 Schema package

**Build** in `backend/guideword/schema/`. All models Pydantic v2 with `extra="forbid"`.

**Plant file** exactly per `PROJECT.md` §9 (blocks, field names, required fields, units). Notes:
- `from_id` / `to_id` are the stored names (no alias needed).
- **Pressure:** every `_kpa` field and every `operating` pressure limit is kPa gauge (vacuum is negative); `_kpaa` is kPa absolute. The suffix always says which, with no exceptions. The chemical's vapour pressure is `vapor_pressure_points`, a list of `{temp_c, pressure_kpaa}`. Overpressure multiples in Phase 4 depend on this.
- **Physics facts** on chemicals are optional: `density_kg_m3`, `heat_capacity_kj_kg_k`, `vapor_pressure_points` (the single-point `vapor_pressure_kpaa` / `vapor_pressure_at_c` fields are gone). Phase 4 interpolates between points (Clausius–Clapeyron), never extrapolates, and skips and flags a calculation whose facts are missing.
- **Utilities** block (`id`, `kind`, `location_id`); `lines.from_id` / `to_id` may be equipment, utilities or locations (a location is an endpoint outside the study, e.g. a pipe rack or battery limit). `lines.is_hose` (bool).
- **Survey additions (2026-10-13, before the freeze):** `lines.no_flow` is a list (no `none` value; empty list = flowing); `planned_work.line_ids`; `equipment.injection_points` (items: `chemical_id` only); `safeguards.layer_type` optional plus `description` (no layer type = existing protection for specialists, never LOPA credit); `locations.description`, `distance_m` (from the unit or area under study) and `offsite`; `notes` (list of `{text, source}`, both required) on every plant object with an ID and on the plant, holding the source's exact words only, never parsed by code. Value objects (`operating`, `heat_sources`, `discharge`, injection points, vapour pressure points) carry no notes.
- **Optional LOPA multipliers:** `lines.length_m` and `planned_work.lifts_per_year` (`PROJECT.md` §9). Plant validation does not warn when they are absent; Phase 3 LOPA flags the missing fact when a cause needs it and never uses a default frequency.
- **Plant object IDs** match `^[A-Za-z0-9][A-Za-z0-9_-]*$`. `.`, `:`, `~` and `+` are reserved for derived IDs, so none may appear in a plant ID.
- `operating` limit fields (`normal`, `alarm_low`, `alarm_high`, `trip_low`, `trip_high`, `design_min`, `design_max`) carry the unit fixed by `parameter`: pressure kPa gauge, temperature °C, level % of range, flow kg/h.
- The §9 example (`example_mixing_unit`) is copied to `backend/tests/schema/fixtures/example_mixing_unit.json` and must validate.

**Enums** (one module, `schema/enums.py`, exported to JSON Schema):

| Enum | Values |
|---|---|
| Equipment type | tank, vessel, column, reactor, heat_exchanger, pump, compressor, dryer, mixer, solids_handler, other |
| Section type (applicability key) | the equipment types, plus `pipe` (every line section) and `procedure`; planned-work sections have no section type (they get only `work:` questions) |
| Section kind | equipment, line, no_flow_line, procedure, planned_work |
| Instrument kind | sensor, switch, analyser |
| Control system | bpcs, sis, standalone |
| Utility kind | steam, cooling_water, nitrogen, instrument_air, power, other |
| Valve kind | control, block, check, manual, relief_isolation |
| Valve position | open, closed; fail position adds `last` |
| No-flow | normally_closed, dead_leg, standby, startup_only (`lines.no_flow` is a list of these; empty = flowing) |
| Operating parameter | pressure, temperature, level, flow |
| Relief kind | prv, rupture_disk, prv_with_disk, vent |
| Discharge kind | atmosphere, flare, scrubber, vessel, header |
| Physical form | gas, liquid, solid, dust |
| Procedure kind | start_up, shutdown, charging, transfer, cleaning, maintenance, emergency, other |
| Work type | hot_work, confined_space, line_break, lifting, other |
| Guideword | no, more, less, reverse, other_than, as_well_as, part_of, early, late, before, after, skipped, wrong, out_of_order |
| HAZOP parameter | flow, pressure, temperature, level, composition, reaction, mixing, phase, time |
| Question kind | matrix, chemical_pair, chemical_environment, no_flow_line, procedure_step, planned_work, dust, relief_discharge, added_by_ai, engineer |
| Question origin | matrix, cross_list, added_by_ai, engineer |
| Question status | open, answered, not_credible, failed (`answered` and `not_credible` count as checked; unsure is a confidence, not a status) |
| Failing component type | the values used in `causes.csv`: control_loop, pump, compressor, check_valve, regulator, relief_device, exchanger_tube, interlock, operator, hose, pipe, tank, external, solids_handler, utility_cooling, utility_power |
| Confidence | sure, unsure |
| Adequacy | adequate, inadequate, unknown |
| Severity class | S1–S5 (definitions from `severity_classes.csv`) |
| Likelihood class | L1–L5 (bands from `likelihood_classes.csv`) |
| Risk rating | low, medium, high, very_high (from `risk_matrix.csv`) |
| Plant status | uploaded, sections_proposed, sections_confirmed |
| Run status | draft, running, finished, stopped_cap, stopped_budget, failed, cancelled |
| Run label kind | live, recorded, mock |
| Override action | accept, reject, edit, change_credit, change_severity, answer |
| Budget use | development, test_5, benchmark, video, demo_recording, judging, buffer |
| Evidence kind / verdict | calculation, precedent, simulation / confirmed, contradicted, none |
| Agent | orchestrator, process, chemistry, piping, procedures, maintenance, dust, connector |
| Event type | run_started, step_started, step_finished, agent_decision, dispatch, model_call, tool_call, finding_added, chain_added, lopa_done, evidence_added, coverage_updated, cap_hit, run_finished, run_failed |
| Environment | laptop, hosted |

**IDs** (`schema/ids.py`, pure functions with tests): the full scheme in `PROJECT.md` §11 "IDs and enums". Every ID is built from content, never random and never a counter. `h(x)` = first 16 hex characters of SHA-256 over canonical JSON (sorted keys, no whitespace, UTF-8, NFC).
- Fact ID `<object id>.<field>` for a top-level field. `heat_sources`, `injection_points`, `discharge`, `vapor_pressure_points` and `operating` rows are **value objects** inside their parent, with no ID of their own; a value object is cited by its parent's field (e.g. `PSV-1.discharge`). Operating facts are cited down to one limit: `<target_id>.operating.<parameter>.<limit field>` (e.g. `MX-1.operating.temperature.trip_high`), so LOPA and physics cite a single setpoint; `operating` rows get no `id` (error 4 already makes target + parameter unique). Provenance keys are an object ID or any of these fact-ID forms.
- **Text normalisation:** one function, `normalise_text()`, used for every hashed text in an ID (`ai:`, `eng:`, `rec:`, outside-library causes): Unicode NFC, Unicode dashes → `-`, non-breaking spaces → space, whitespace collapsed, trimmed, casefolded.
- Section: `S-<object id>`; split part `S-<object id>~<first component id>`; engineer-added `S~eng~<h(sorted covered object IDs)>`; a merge keeps the lowest ID; renames never change an ID.
- Question: `m:<section>:<guideword>:<parameter>`, `pair:<chemA>:<chemB>` (sorted), `env:<chem>:<water|air|heat>`, `nf:<line>`, `proc:<step>:<guideword>`, `work:<job>:<target>`, `dust:<equipment>`, `relief:<device>`, `ai:<section>:<h(normalised question text)>`, `eng:<section>:<h(normalised question text)>`.
- Run `run:<h(inputs)>`, or `run:<h(inputs)>:<n>` for a later attempt after a finished, cancelled or failed run (an unfinished run with identical inputs is resumed; `spend_cap_usd` is not an input; a `stopped_cap` run resumes only with a higher cap, otherwise 409 "cap reached; raise spend_cap_usd to continue"); finding `f:<question id>:<tier>:<cause id>:<h(sorted failing component IDs)>` (outside-library: `h(normalised cause text)` replaces the cause ID); chain `ch:<sorted link IDs joined with +>`; LOPA `lopa:<target id>`; recommendation `rec:<finding or chain id>:<h(normalised action text)>`; evidence `ev:<target id>:<kind>:<source key>`; model call `mc:<cache key>`; tool call `tc:<agent step id>:<tool>:<h(arguments)>`; agent step `step:<h(previous step, agent, tool, arguments)>`; override `ov:<target id>:<h(action, new value, replaced override ID)>`. Events have no content ID: they are identified by (run ID, `seq`).

**Record models** per the `PROJECT.md` §11 record table: Plant (with `status`), Run (with `label: {kind, recorded_at, cost_usd}` and the section snapshot), PlantFact, Section, Question, Finding (`cause_id` = a `causes.csv` ID or `outside_library`; `failing_component_type`; `failing_component_ids` = plant IDs, **never empty** (utility causes → utility ID; hose → line; operator → procedure step or planned job; external → location); `safeguard_ids`; adequacy; severity class with reason; confidence; not-credible reason), AgentStep, ModelCall, ToolCall, Chain (links are finding IDs or fact IDs), LopaRecord, Recommendation (action, reason, target finding or chain ID), Evidence, Override (`by` = display name), Event (`seq`, type, payload, time), SpendEntry (the ledger line in 0.3, with `use`).

**Plant validation** (`schema/validate.py`) returns errors and warnings separately; each names the offending ID. It takes the loaded reference set (0.6) as an input.

Errors:
1. Duplicate ID anywhere in the file.
2. A reference to a missing ID, or to the wrong kind of object. Checked fields: `location_id`, `contents`, `heat_sources.via_line_id` (line), `heat_sources.isolating_valve_ids` (valves), `instruments.on_id` (equipment or line), `utilities.location_id`, `valves.on_line_id`, `lines.from_id` / `to_id` (equipment, utility or location), `equipment.injection_points.chemical_id` (chemical), `lines.components` (valves or equipment), `injection_points.chemical_id`, `injection_points.at_component_id` (must be in that line's components), `operating.target_id` (equipment or line), `alarm_instrument_id` / `trip_instrument_id` (instruments), `control_loops.sensor_id` (instrument), `controller_id` (logic solver), `final_element_id` (valve or equipment), `acts_on_id`, `safeguards.protects_id` (equipment or location), `safeguards.component_ids` (instruments, logic solvers, valves or equipment), `relief_devices.protects_id`, `inlet_valve_ids` (valves), `discharge.location_id`, procedure step `equipment_ids` / `valve_ids`, `planned_work.location_id` / `equipment_ids` / `line_ids` (lines).
3. `layer_type` not in `protection_layers.csv`; an `epa_groups` entry not in `reactive_groups.csv`; a `cameo_groups` entry not in `cameo_groups.csv`.
4. Two `operating` rows for the same target and parameter.
5. `planned_work` with `end` before `start`.
6. A provenance key whose object or field does not exist (for an operating key: no row for that target and parameter, or that limit is unknown or unset).
7. Unknown field (from `extra="forbid"`).
8. A plant object ID that does not match the ID pattern above.
9. A valve whose `on_line_id` names a line whose `components` does not list that valve.

Warnings (missing facts, shown in the UI as gaps, never filled in by code):
1. Tank, vessel, column, reactor, heat exchanger, dryer or mixer with no design pressure or design temperature.
2. Control or block valve with no fail position.
3. Chemical with neither EPA nor CAMEO groups.
4. Relief device with no discharge.
5. Procedure with no steps.
6. Active-category safeguard with empty `component_ids` (independence cannot be checked).
7. Line with no contents.
8. `operating` limits out of order (expected design_min ≤ trip_low ≤ alarm_low ≤ normal ≤ alarm_high ≤ trip_high ≤ design_max where present). A warning, not an error: a trip set above design is a real hazard the tool must be able to load and flag.

**Unit-suffix rule** is a test over the model definitions, not a validation error: every `int`/`float` field in the plant models must end in an allowed suffix (`_kpa`, `_kpaa`, `_c`, `_m3`, `_kg_h`, `_kw`, `_mm`, `_m`, `_pct`, `_kj_kg`, `_kg_m3`, `_kj_kg_k`, `_per_year`, `_usd`, the list in `PROJECT.md` §9) or be in an explicit exempt list in the test: the seven `operating` limit fields, and the reference-group ID lists `epa_groups` and `cameo_groups` (integers that are IDs, not quantities).

**JSON Schema export:** `scripts/export_schemas.py` writes the plant schema and every record and response model to `contract/schemas/`.

**Acceptance (tests first)**
- [x] `example_mixing_unit.json` validates with no errors.
- [x] One test per error rule and per warning rule, each producing exactly that message with the offending ID.
- [x] Unit-suffix test passes, and fails when a bare numeric field is added to a model.
- [x] Question ID builders and parsers round-trip; `pair` IDs are the same whichever order the chemicals are given.
- [x] Two findings for the same question with different causes, or the same cause on different components, get different IDs.
- [x] A finding with an empty `failing_component_ids` fails validation.
- [x] `eng:` and `rec:` IDs are pure functions of their inputs; the same action text on the same target gives the same `rec:` ID.
- [x] Two `check_coverage` calls with identical arguments at different agent steps get different tool call IDs.
- [x] Run IDs: identical inputs while a run is unfinished return that run; after cancelling it, starting again gives `…:2`.
- [x] Every ID builder is a pure function of its inputs: the same inputs give the same ID in two separate processes; `ch:` IDs are the same whichever order the links are given; a test fails if `ids.py` imports `random`, `uuid` or `itertools.count`, or reads the clock.
- [x] Round trip: load → dump → load gives an identical object.
- [x] Exported JSON Schemas match the models (test regenerates and compares).
- [x] Merged and frozen. Later changes only through a `contract/...` branch. (Frozen 2026-10-13 with PR #7, `a847858`.)

## 0.6 Reference tables: loaders and validation

**Data:** done by Cowork on Oct 11 and in the bootstrap commit. Claude Code does not research, add or change values. Headers are exactly those in `PROJECT.md` §10:

| File | Header |
|---|---|
| `applicability.csv` | `section_type,guideword,parameter,source` |
| `causes.csv` | `id,cause,applies_to,failing_component_type,initiating_event_id,source` |
| `initiating_events.csv` | `id,event,frequency,unit,source` |
| `protection_layers.csv` | `id,layer,category,pfd,pfd_if_isolatable,requires_independent_sensor,requires_independent_logic,requires_independent_final_element,no_credit_if_isolated,scenarios,conditions_text,relief_kind,source` |
| `modifiers.csv` | `id,kind,release_phase,release_rate_kg_s_band,area_occupancy,event_type,operating_pattern,value,source` |
| `severity_classes.csv` | `severity_class,name,definition,source` |
| `tolerable_frequencies.csv` | `severity_class,tolerable_per_year,source` |
| `likelihood_classes.csv` | `likelihood_class,name,min_per_year,max_per_year,source` |
| `risk_matrix.csv` | `severity_class,likelihood_class,rating,source` (25 rows) |
| `cameo_groups.csv` | `cameo_group_id,name,source` |
| `reactive_groups.csv` | `epa_group_id,name,do_not_mix,source` (41 rows) |
| `reactive_pairs.csv` | `group_a,group_b,codes,source` (303 rows; `group_a` comes before `group_b` in chart order) |

`precedent_index.csv` is Phase 4; not created now. Multi-value cells (`applies_to`, `scenarios`, `codes`) use `;` as the separator.

**Build** in `backend/guideword/reference/`: one Pydantic row model and loader per table; a `ReferenceSet` holding all tables; version hash per table = SHA-256 of the file bytes.

**Acceptance (tests first)**
- [x] The header of every file equals the frozen header.
- [x] Every row has a non-empty `source`.
- [x] No file contains `\r` (keeps the hash identical on Windows and Linux).
- [x] `applicability`: no duplicate (section_type, guideword, parameter); every value in its enum; every section type has at least one row. Not listed = not applicable. The `procedure` rows are exactly the five procedure guidewords (`skipped`, `wrong`, `early`, `late`, `out_of_order`); the loader exposes them as the `proc:` guideword list.
- [x] `risk_matrix`: every (S1–S5, L1–L5) pair exactly once; rating in {low, medium, high, very_high}.
- [x] `protection_layers.relief_kind`: empty or a relief kind; each relief kind (prv, rupture_disk, prv_with_disk, vent) on exactly one row.
- [x] `causes`: unique IDs; `initiating_event_id` exists; `applies_to` values are section types or `planned_work`; `failing_component_type` in the enum.
- [x] Frequencies > 0; probabilities in (0, 1]; flag columns 0 or 1; `pfd_if_isolatable` empty or in (0, 1].
- [x] `initiating_events.unit` is one of `per_year`, `per_opportunity`, `per_metre_year`, `per_lift` (the four in the file). The loader exposes the unit; it never treats a non-`per_year` value as a yearly frequency. Converting those (C20 piping leak × `lines.length_m`; C24 crane drop × `planned_work.lifts_per_year`; missing fact = LOPA incomplete, never a default) is Phase 3 LOPA work.
- [x] Every severity class S1–S5 appears once in `severity_classes` and once in `tolerable_frequencies`; likelihood bands are contiguous and do not overlap. The lowest band starts at 0 and the highest band's empty `max_per_year` means "no upper limit".
- [x] `reactive_groups`: 41 rows; `do_not_mix` is 0 or 1. `reactive_pairs`: both groups exist; codes in {H, F, G, GT, GF, E, P, S, U}; each unordered pair at most once; no pair involves group 107 (it is covered by `do_not_mix`).
- [x] A pair missing from `reactive_pairs` is reported by the loader API as "not listed", never as "compatible" (the chart says blanks do not mean safe).
- [x] Version hash changes when a file changes.

## 0.7 Dev cases D–H as plant files

**Build**
- Bhargavi copies the kill-test #4 packages and answer keys from `C:\Users\bharg\Downloads\guideword_killtest4\killtest4` into `cases/dev/source/` and `cases/dev/keys/` (dev cases are not secret).
- Claude Code converts the five packages (TPC Port Neches, Husky Superior, PCA DeRidder, AB Specialty Silicones, Didion Milling) into `cases/dev/case_d.json` … `case_h.json`, keeping their unrelated equipment.
- **Read only `cases/dev/source/`, never `cases/dev/keys/`,** for both the pre-freeze survey and the conversion. Record what each package states, in the package's own words; never classify anything beyond what the package says (e.g. no `no_flow: dead_leg` unless the package says dead leg). Where the schema needs an enum value the package does not state, the field stays empty and the gap goes in the report.
- **Modelling rules from the survey (2026-10-13):** a fact with no field goes into `notes` on its object (or the plant), as the package's exact words with the package file as `source`; a named shared header (overflow line, vent header, flare header, baghouse ductwork) becomes equipment `type: other`; a line whose endpoint lies outside the package ends at a location; portable hoses become one `is_hose` line per tank they charge, from the location the totes come from, flagged in the report as a modelling choice; a safeguard that is not a LOPA layer has no `layer_type` and keeps its package description; plural equipment the package does not count becomes one object with a note that the count is not stated.
- **Proposed assumptions already known (for Bhargavi to tick):** EPA and CAMEO groups for every chemical (no package states them), including case G: Si-H fluid EPA 105, KOH emulsifier EPA 10 and 106; and `combustible_dust: true` for corn flour and cornmeal in case H (the package does not say combustible).
- **No invented facts.** A fact missing from the package stays missing (it shows as a validation warning). Claude Code may *propose* an assumed value only where a later phase needs it, and never writes one into a plant file on its own.
- `cases/dev/conversion-report.md`, one section per case:
  1. **Proposed assumptions:** fact ID, proposed value, why it is needed, a checkbox. Only values Bhargavi ticks go into the file, with `"assumed"` in `provenance`.
  2. **Package facts the schema cannot hold:** quoted, with the block that would need to change. Never silently dropped. If any matter for Phase 1, raise a `contract/...` change before the freeze. (Since the survey, such facts go into `notes`; this section lists anything that still has no home.)
  3. Remaining warnings.

**Acceptance**
- [x] All five validate with no errors.
- [x] Every assumed value in the files is ticked by Bhargavi in the report. (2026-10-13: all 79 proposals accepted, plus 10 case H locations Bhargavi proposed; 89 assumed values.)
- [x] A test loads all five and checks every "assumed" provenance entry matches a ticked report line.

## 0.8 API contract and mock server

**Build**
- FastAPI app in `backend/guideword/api/` with **every endpoint in `PROJECT.md` §11** (including `GET /plants`, `GET /runs`, `POST /runs/{id}/cancel`, `GET /runs/{id}/sections`, `GET /runs/{id}/questions`, `POST /runs/{id}/questions`, both JSON exports, and `POST /internal/runs/{id}/advance`), with request and response models from 0.5.
  - Without mock mode (`GUIDEWORD_MOCK=0`), every endpoint returns 501 with a body naming the phase that will build it; the contract documents this.
  - `POST /runs`: `plant_id`, `spend_cap_usd`, `mode` (`full` | `sample`); returns 409 "sections not confirmed" when the plant's status is not `sections_confirmed`, and 409 "cap reached; raise spend_cap_usd to continue" when a `stopped_cap` run with the same inputs is restarted without a higher `spend_cap_usd`. `POST /runs/{id}/questions`: `section_id`, `text` (creates an `eng:` question, origin `engineer`, status open). `POST /runs/{id}/overrides`: `target_id`, `action`, `new_value`, `reason`, `by`.
  - Every run-related response carries `label: {kind, recorded_at, cost_usd}`.
  - `POST /internal/runs/{id}/advance` requires an `X-Internal-Secret` header matching settings; in mock mode it returns 202 and does nothing.
  - `POST /runs/{id}/overrides` on a run whose `label.kind` is `recorded` returns 403 ("recorded run is read-only"). The public demo run is shared by every judge, so no visitor can change what the next one sees; the frontend keeps demo-mode accept/reject choices in the browser only. Mock runs accept overrides and echo them back without storing them.
- Mock mode (`GUIDEWORD_MOCK=1`): every endpoint returns fixtures from `contract/fixtures/`. One small, clearly fictional plant, "Mock Plant A", with sections, questions, findings, one chain, LOPA records, a recommendation, evidence, coverage, events and budget. Every fixture has `label.kind = "mock"`. Fixtures describe no real accident. `GET /runs/{id}/export.xlsx` is built at request time from the worksheet fixture with `openpyxl` (no binary in the repo) and is the one route exempt from "every response model has a fixture". The 403 test uses a `recorded` run from a test-only fixture, so `contract/fixtures/` stays mock-only.
- `GET /runs/{id}/events?after={seq}` in mock mode releases fixture events over about 20 seconds, counted from the first poll for that run, so the frontend can build the live-run screen by polling. The clock is injected into the app, so tests advance it by hand instead of sleeping.
- `scripts/export_openapi.py` writes `contract/openapi.json`.
- **TypeScript types:** `openapi-typescript` (frontend dev dependency, approved by Bhargavi on Oct 11) generates `frontend/src/api/types.ts` from `contract/openapi.json`.

**Acceptance**
- [x] A test lists the §11 endpoints and fails if any route is missing or extra.
- [x] Every endpoint's mock response validates against its model; every response model has a fixture.
- [x] Every run-related mock response has `label.kind == "mock"`.
- [x] `advance` without the secret returns 401.
- [x] An override on a `recorded` run returns 403.
- [x] The mock events test runs in well under a second using the injected clock.
- [x] `contract/openapi.json` matches the app (test regenerates and compares).
- [x] The frontend generates types and `npm run typecheck` passes.
- [ ] Tagged `contract-v1` on `main`. Later changes only through `contract/...` branches.

## 0.9 Feasibility (remaining items)

Already resolved on Oct 11 and recorded in `docs/decisions.md`: LOPA source (EGPC-PSM-GL-015), simulator package (`tennessee-eastman-profbraatz`), DEXPI importer moved to "next", CAMEO group list.

- [x] **EPA 1980 compatibility chart** (EPA-600/2-80-076): transcribed Oct 11 from the one-page chart Bhargavi supplied. 41 groups, 303 pairs, every cell checked against the rendered page. In the bootstrap commit.
- [ ] **Kill-test #1 simulator origin:** Bhargavi confirms from her machine which code ran kill test #1 (recorded as tep-rust, which has no licence) and that none of it, and no Operon code, enters this repo. The project simulator is the open-licence package above.
- [ ] Results written to `docs/decisions.md`.

## 0.10 Non-build tasks (Bhargavi)

- [ ] Case writer chosen. **The case writer creates and owns `guideword-heldout`**; Bhargavi has no access until Phase 6, when she is invited to run and score.
- [ ] Case writer brief: Cowork drafts it; it goes to the writer without Bhargavi reading it; the writer commits it to their repo. This repo keeps only a generic `docs/case-template.md` with no sources named: Claude Code drafts it after the schema freeze, showing the plant file format and the answer key format, and Bhargavi reviews it.
- [ ] Facilitator outreach sent (Haber network, then LinkedIn).
- [ ] Second $25 Token Factory grant claimed if not already.
- [ ] City Winner attendance rule asked in the Nebius Discord (by Oct 13).

---

## Order of work

**Oct 12**
0. Claude Code writes `specs/phase-0-plan.md` in plan mode (`CLAUDE.md` §1, "Plan before code"); Bhargavi answers its questions and marks it approved. No code before that.
1. 0.0 bootstrap commit (Bhargavi), branch protection, folder tree on `phase-0/scaffold`.
2. 0.1 tooling and CI; merge.
3. 0.5 schema starts (everything after depends on it): enums, IDs, plant models.
4. 0.2 config and 0.3 live-call script with tests; merge.
5. 0.4 smoke test written; Bhargavi records the opening balance and runs it in the evening; results and decisions written.
6. 0.10 case writer contacted.

**Oct 13**
7. 0.6 loaders, then 0.5 validation rules (they need the reference set) and JSON Schema export; merge and freeze the schema.
8. 0.7 dev cases converted; Bhargavi ticks the conversion report.
9. 0.8 contract and mock server; tag `contract-v1`. The frontend worktree starts from the tag.

**Oct 14 morning**
10. G1 review. Phase 1 starts after it.

## G1 gate (Oct 14 morning)

All must be true to start Phase 1:
- [ ] Bootstrap commit only; everything else merged by pull request; CI green on `main`; licence visible.
- [ ] Smoke test complete; decisions written; model IDs confirmed; opening balance recorded; spend ≤ $0.65.
- [ ] Ultra tool calling (T12) confirmed, or the JSON next-action fallback chosen and written into `docs/decisions.md`.
- [ ] Schema frozen; contract tagged `contract-v1`.
- [ ] Reference loaders pass on all tables; LOPA source named.
- [ ] Dev cases D–H validate; every assumption ticked.
- [ ] Case writer has started and owns the held-out repo.

If an item fails, apply the fallback in `PROJECT.md` §16, record it in `docs/decisions.md`, and continue. Only a missing schema or contract blocks Phase 1.

## Open questions

None. The questions raised on Oct 11 (LOPA multipliers, record IDs, absolute vapour pressure), the ID fixes of Oct 12 (several findings per question, tool call IDs per step, run attempts, events by sequence) and the Oct 12 pre-freeze review (EPA class for Si-H, risk matrix, recommendations, relief credit, physics facts, utilities, plant-owned sections, unsure, engineer questions, question-count rules, budget by use, cache and ledger homes) are decided in `docs/decisions.md` and written into `PROJECT.md`.
