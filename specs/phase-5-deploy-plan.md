# Phase 5 deploy plan — the first deploy: backend + the no-key landing on the WG run

Status: **draft, awaiting Bhargavi's approval** (mark `Status: approved <date>` here).

Written 2026-10-24, after F2 merged (#116). Bhargavi asked (2026-10-24): "After F2 merges, deploy
first: backend + the no-key replay landing on the WG run. Later PRs redeploy." This reaches into
Phase 7's scope (`specs/phase-5.md` "Not in scope": `GET /demo`, demo mode, the recorded-run
read-only serving, Vercel deploy), so this plan is the spec item and the plan together. Read with
`PROJECT.md` §11 (hosting and deployment, demo mode), §14, §15, and `CLAUDE.md` §4, §7, §13.

---

## 1. What exists today (checked $0)

| Fact | Where |
|---|---|
| `GET /demo` returns 501 "not implemented until phase 7" (mock mode serves `demo_response.json`) | `api/app.py` `NOT_BUILT_PHASE[("GET", "/demo")] = 7` |
| `DemoResponse` is `{label, plant: PlantDetail, run: RunDetail, shortlist: Shortlist}` | `api/models.py` |
| A recorded run gets 403 on every override (contract v1) | `api/live.py` |
| `guideword.db` is 138 MB and holds every run; `guideword-demo.db` does not exist yet | the main checkout |
| The WG final run `run:76f8ee0b5d1f078e` is stored with `label.kind = "live"`, `spent_usd` 0.8882; its ledger lines total 0.8965 (the refused-retry bug, 2026-10-22: the ledger is the authority for runs stored before the fix) | `guideword.db`, `budget/ledger.jsonl` |
| `cases/demo/recorded/` exists and is empty; PROJECT.md §11: "The recorded run's export is committed in `cases/demo/recorded/` (no keys)" | the repo |
| CLAUDE.md §7: never commit `*.db` run stores | |
| No Vercel CLI or project link on this machine | |
| The frontend is static (`vite build` → `dist/`, 230 kB) and calls the API same-origin | F0 |

## 2. Questions (each with a recommendation)

| # | Question | Recommendation |
|---|---|---|
| Q1 | **Host.** PROJECT.md §11 names Vercel: static frontend, the API as Python functions, Postgres via the Marketplace. | **Vercel**, as §11 says, but **no Postgres yet**: the API reads the WG run from an in-memory SQLite store loaded at cold start from the committed export (Q2). Nothing on a no-key landing writes; Vercel's filesystem is read-only anyway. Postgres arrives with the hosted live-run button (Phase 7). |
| Q2 | **How the WG run travels.** A `.db` file can't be committed (CLAUDE.md §7). | **A JSON export in `cases/demo/recorded/williams_geismar/`**: every stored row of the run, one file per table (run, sections, questions, findings, hypotheses, chains, LOPA, recommendations, evidence, overrides, events, agent steps, model calls, tool calls, superseded), plus its plant record, facts and sections. Exported read-only from `guideword.db` (`mode=ro`) by `scripts/export_recorded.py`; a key scan refuses to write if any configured key appears. Loaded by `scripts/`-free package code (`runs/recorded.py`) into an in-memory store at startup. No response cache rows and no ledger. |
| Q3 | **The label.** §11: demo mode is "labelled on screen as a recorded run (with its date and cost)". The run is stored `live`. | The **export** sets `label = {kind: recorded, recorded_at: 2026-10-22T…Z (its last event's time), cost_usd: 0.8965 (its ledger lines, the authority for runs stored before the fix)}`. `guideword.db` is never changed. Overrides then get 403, as the contract says for recorded runs. |
| Q4 | **`GET /demo`.** | Built now: with `GUIDEWORD_DEMO_RUN_ID` set (a new setting; no default), it returns `DemoResponse` for that run from the store; unset, it keeps its 501. Mock mode keeps its fixture. |
| Q5 | **The landing.** F3 (the replay) is the second session's and not built yet. | **This deploy lands on the WG run's shortlist** with the recorded banner: the empty hash reads `GET /demo` and opens `#/runs/<demo run>/shortlist`. When F3 merges, the landing switches to its replay (that PR redeploys). |
| Q6 | **No keys.** | The deployment sets no `NEBIUS_API_KEY` or `TAVILY_API_KEY`; `GUIDEWORD_ENV=hosted`; `POST /runs` is refused (a hosted app takes no laptop use, B2) and `live_run_available` stays false. A test starts the deployed app's settings with no keys and checks no route can call out. |
| Q7 | **Who deploys.** | Bhargavi: `npm i -g vercel` (a tool on her machine, not a repo dependency), `vercel link`, `vercel --prod`. I prepare `vercel.json`, `api/index.py` and the build; I never run a deploy (CLAUDE.md §4: outward-facing). |
| Q8 | **What the frontend calls.** | Same origin: `vercel.json` rewrites `/plants`, `/runs`, `/budget`, `/demo` to the Python function; everything else is the static `dist/`. |

## 3. Per item

### D1 — `phase-5/recorded-export` (backend)
- **Files:** `scripts/export_recorded.py` (read-only, key scan, the Q3 label on the copy); `cases/demo/recorded/williams_geismar/*.json`; `backend/guideword/runs/recorded.py` (`load_recorded(path) -> sessionmaker` into in-memory SQLite).
- **Tests first:**
  - `test_export_then_load_serves_the_same_shortlist` (on the fixture generator's $0 run: the shortlist, run detail, events and every record detail read the same from the loaded copy as from the source);
  - `test_the_export_sets_the_recorded_label_and_leaves_the_source_unchanged` (hash);
  - `test_the_export_refuses_a_configured_key`;
  - `test_the_recorded_copy_refuses_overrides_with_403`.

### D2 — `phase-5/demo-route` (backend)
- **Files:** `settings.py` (`guideword_demo_run_id: str | None = None`, `guideword_recorded_dir: str | None = None`); `api/app.py` (`GET /demo` from the store when set; the app loads the recorded store when `guideword_recorded_dir` is set); `NOT_BUILT_PHASE` loses `/demo` only when it is built.
- **Tests first:** `test_demo_returns_the_recorded_run_with_its_label`, `test_demo_without_a_demo_run_is_501`, `test_a_keyless_hosted_app_refuses_every_paid_route`, the contract route test unchanged.

### D3 — `phase-5/landing` (frontend)
- **Files:** `src/app/landing.ts` (pure: the empty hash → the demo run's shortlist), `App.tsx`.
- **Tests first:** `the empty hash opens the demo run's shortlist`; `without a demo the empty hash shows the plant list`; the recorded banner shows on the landing.

### D4 — `phase-5/vercel` (config)
- **Files:** `vercel.json` (build the frontend, the Python function, rewrites); `api/index.py` (`app = create_app(settings=Settings())`); `api/requirements.txt` (the backend's pinned runtime set, no dev tools); `docs/deploy.md` (Bhargavi's steps and the env vars: `GUIDEWORD_ENV=hosted`, `GUIDEWORD_DEMO_RUN_ID`, `GUIDEWORD_RECORDED_DIR`, no keys).
- **Tests first:** `test_the_function_entry_builds_the_app_with_no_keys`; `test_vercel_rewrites_name_every_api_prefix` (reads `vercel.json`; the prefixes equal the API's route prefixes).
- **Then Bhargavi** runs the deploy and sends the URL; I check it with `curl` (`/demo`, `/runs/<id>/shortlist`, the landing).

## 4. Order
D1 → D2 → D3 (D3 can start on D1's export) → D4 → Bhargavi deploys. Each later PR (F3, F4, F5, F6) redeploys with `vercel --prod`.

## 5. Not doing
- Postgres, the hosted ledger and the hosted live-run button, the per-visitor caps, hosted chaining (Phase 7).
- Browser-only overrides on the recorded run (Phase 7; the server refuses them with 403 meanwhile).
- Any change to `guideword.db` or the WG run's records.
- Any key in the deployment.

## 6. Live calls and spend
None. Every test uses the fixture generator's fake runs or the read-only export; the deployment has no keys.

## 7. Acceptance
- The deployed URL opens on the WG run's shortlist, labelled "Recorded run — 2026-10-22 — cost $0.90".
- The demo moment's card opens, its numbers traced, the drawer resolving `HV-B-SIN.normal_position`.
- An override answers 403 "This run is recorded and read-only".
- `curl` checks of `/demo` and the shortlist pass, recorded in the D4 PR.
