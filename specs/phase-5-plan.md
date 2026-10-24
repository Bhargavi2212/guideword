# Phase 5 plan — Frontend: seven screens on the real API

Status: approved 2026-10-23 (Bhargavi)

Written 2026-10-23 against `specs/phase-5.md` as it stood then (192 lines, modified 2026-10-22 07:28, SHA-256 `47738ae3…`; Cowork is still editing it, so the spec version this plan answers is named here). Read with `PROJECT.md` (§5 Steps 1–8, §11, §12, §14, §15, §23), `CLAUDE.md` (§1–§9, §13) and the code on `main` after "Merge pull request #104" plus `phase-4/close`. No code is written until this plan and the spec are approved.

---

## 1. The spec's claims, checked against the code

| Spec says | Code today | Note |
|---|---|---|
| "checked on `main` at Merge pull request #96" | `main` is now past #104 | #97–#104 since: PR 5c (evidence reads, agent steps in record detail), `precedent_judge/v2`, the priority-line relabel, the `linked_answered` fix, the refused-retry fix, the records PR. See C1. |
| Frontend: React 19.3, Vite 8, Vitest 5, TS 6 strict + `noUncheckedIndexedAccess`; no router, data library, CSS framework or chart library; no dev proxy | ✅ exactly (`frontend/package.json`, `tsconfig.json`, `vite.config.ts`) | `types.ts` is 3,203 lines at v1.8. `@testing-library/user-event` is not installed; tests use `fireEvent` (no new dependency). |
| No CORS middleware | ✅ | The dev proxy (5.0) avoids it. |
| Every §11 endpoint runs except `GET /demo` (501) | ✅ (26 routes in `api/app.py`) | |
| `POST /runs` creates or resumes, nothing drives it; `advance` needs the server secret | ✅ (`app.py:329`, `:588`) | `advance` already uses the "first step now, `live().drive` as a background task" pattern B2 reuses. |
| `GET /runs/{id}/records/{id}`: "Evidence records arrive with PR 5c. Agent steps and tool calls are not directly addressable." | **Outdated.** Evidence (target, tool call, judge call) and **agent steps** (with their own tool calls) are addressable since PR 5c (#97). **Tool calls (`tc:`) are not.** | B3 shrinks to tool calls (C1). |
| `GET /plants/{id}` facts resolve every fact link | ✅ on the WG final run: 37/37 chain fact links and 14/14 facts evidence cites as used resolve | Fact IDs a record names as **missing** (e.g. `EA-425B.heat_duty_kw`) are by definition not in the facts: shown "not stated in the plant file" (C11). |
| The events table (fixture vs backend) | ✅ and worse: on the WG final run's 916 stored events, 14 of 18 types differ from the fixture. `run_started`, `run_extended` and `step_finished` carry fields the fixture omits; `step_finished` merges each step's own summary into its payload, so its keys differ per step (`answered`, `block_list`, `connector`, `evidence`, `lines`, `sent_ids`, …). **No stored `model_call` event has a `tier`.** | C3, C4. |
| `GET /budget` gives "hints" for the spend-cap default | `Budget` has per-**environment** rows (allowance, spent, remaining) and `live_run_available`; **no per-use rows** | API runs spend use `development`: $0.93 left, while the laptop environment has more. C6. |
| Demo moment: "the reboiler-B chain card → … 'no credit — inlet valve HV-B-SIN closed' → … blocked-in heating 'at least 1.6× design' → … change severity S3→S4 → gap text moves by 10×" | **No single card on the WG final run has all of these.** See C2. | Tolerable frequencies are 10× apart per class (S3 1e-4/yr, S4 1e-5/yr), so any one-class change moves the gap 10×. |
| `phase_caps_usd."5": 0.50` | Not in `caps.yaml` yet (phases 0, 2, 3, 4) | Added in P0. |

### The WG final run's top 12, as the shortlist serves it (checked $0)

| Rank | Kind | Target | Severity | Gap | "HV-B-SIN closed" layer | Confirmed evidence |
|---|---|---|---|---|---|---|
| 1 | finding | `f:m:S-EA-425B:more:temperature…` (external fire, C22) | **S4** | about 10,000× | **yes** | **blocked-in heating, at least 1.6×** |
| 2 | chain | `ch:EA-425B.design_pressure_kpa+…` | S3 | about 1,000× | no (Ultra's "does not apply"; feedback log) | blocked-in heating |
| 3 | chain | `ch:HV-A-SIN.normal_position+…` | S3 | about 1,000× | no | blocked-in heating |
| 7 | chain | `ch:HV-B-SIN.normal_position+HV-B-SOUT…` | S2 | about 100× | **yes** | none (outside the evidence top 5) |

---

## 2. Conflicts and open questions (quoted; not resolved by me)

All of C1–C13 are answered (see "Answers" below). Where a recommendation in this table differs from the answer, **the answer wins**: C2 (rank 2, S3 → S4, not rank 1), C6 (the use is picked on the form, not fixed to `development`) and C8 (`guideword-demo.db`, not an unnamed copy). The table is kept as it was asked.

| # | Where | Says | Code / other source | Question for Bhargavi |
|---|---|---|---|---|
| C1 | Spec §"What the code has today" | "Evidence records arrive with PR 5c. Agent steps and tool calls are not directly addressable." / B3: "also resolves `step:` agent steps and `tc:` tool calls" | Evidence and `step:` are addressable since #97 | B3 becomes **tool calls only** (`tc:` with its step as parent). Agree? |
| C2 | Spec header, 5.2, acceptance 1 | "the reboiler-B chain card → … 'no credit — inlet valve HV-B-SIN closed' → the gap → the blocked-in heating evidence → the recommendation → the engineer's S3 → S4 override moving the gap" | No one card has all of them (table above). Rank 1 (a **finding**, S4) has the layer and the evidence; rank 2 (a chain, S3) has the evidence and an S3 but not the layer; rank 7 (the HV-B-SIN chain) has the layer but is S2 with no evidence. | **Which card is the demo moment?** Recommendation: **rank 1**, the finding on EA-425B (external fire): layer "no credit — inlet valve HV-B-SIN closed" → gap about 10,000× → blocked-in heating "at least 1.6× design" → recommendation → change severity **S4 → S5** (gap moves 10×). The spec's and `PROJECT.md` §14's wording ("chain", "S3 → S4") then changes in P0. Alternative: rank 2, a chain at S3 → S4, but its relief layer reads Ultra's "does not apply". |
| C3 | P5-1: "`model_call` and `dispatch` payloads gain `tier` (the backend knows it from routing; the frontend must not)"; acceptance 3: "Replay of the WG run at 60× shows … the tier of each call" | Stored events (the WG run, D–G) have no `tier`; the replay reads stored events | **Tier on stored events.** Recommendation: the backend emits `tier` on new events, and the events endpoint adds it on read to stored events from the call's `model_id` against `config/models.yaml` (each tier's `expected_id`), `null` when unknown. Code still owns it; the frontend never derives it. |
| C4 | P5-1: "`Event` a discriminated union on `type` … a test that every emitted payload validates" | Stored payloads vary by era (Phase 2, 3, 4 runs) and `step_finished` carries each step's summary as extra top-level keys | **How strict are the payload models?** Recommendation: each type's model types the fields the timeline uses, required where every era has them and optional otherwise; `step_finished` keeps its step summary as extra fields (`extra="allow"` on that one model only), every other model forbids unknown fields. Stored events are validated once by a $0 script against the local store (WG, D–G), result in the B1 PR; CI validates a fake run's events. |
| C5 | P5-1: "the fixture regenerated from a $0 fake run through the real emitters" | The other run fixtures (shortlist, run dump, worksheet …) share `run:8ede059837927e4a` and its records; a fake run gives a new run ID and new record IDs | **Fixture coherence.** Recommendation: rewrite `events_page.json` (and the run dump's events) by hand to the real payload shapes, keeping the mock run's IDs, and validate them with the new models; **separately** test that a fake run's emitted events all validate. No fixture invents a field the emitters don't write. |
| C6 | 5.3: "spend cap input (default from `GET /budget` hints, never above the remaining allowance)" | `Budget` has no per-use rows; API runs spend `development` ($0.93 left) | **Per-use budget.** Recommendation: v1.9 (B1) adds `uses: [{use, environment, allowance_usd, spent_usd, remaining_usd}]` to `Budget`, and the start form caps the spend cap at `development`'s remaining amount minus the default post cap. |
| C7 | P5-2 and acceptance 2 | UI-started runs: spend cap entered; post cap not mentioned | `StartRunRequest` has no post cap, so a UI run gets caps.yaml's default `post_spend_cap_usd` (0.30) **on top of** its spend cap; the phase cap is $0.50 | **The post cap of a UI run.** Recommendation: no contract change; the start form shows "up to $<spend cap> + $0.30 post-analysis", and the upper-bound estimate returned already includes the post cap. Acceptance 2's run then uses a spend cap of $0.15 (≤ $0.45 with the post cap and the proposal), or the replay. |
| C8 | 5.2 and acceptance 1: the override "moving the gap" on the WG final run | The WG final run is `label: live`; an override there is **stored permanently** in the run store, and Phase 7's demo mode reads stored records | **Where the demo override is made.** Recommendation: acceptance 1 runs on a **copy** of `guideword.db` (the API pointed at it through `DATABASE_URL`), so the recorded WG run stays as the analysis left it. The video's override is made the same way. |
| C9 | `CLAUDE.md` §7: "Two worktrees run in parallel: backend and frontend. Do not edit the other worktree's area." | B1 regenerates `frontend/src/api/types.ts` | Same as contract v1.5–v1.8: **B1 regenerates `types.ts` in the backend worktree**, and the frontend worktree rebases on it. Agree? |
| C10 | `PROJECT.md` §15: "5. Frontend · Oct 14–25 (parallel, from `contract-v1`)" | Spec: Oct 22–26, feature dates Oct 24 / 25 / 26 | P0 sets §15 to the spec's dates. |
| C11 | P5-6: "An ID the API can't resolve shows 'not addressable yet'" | Missing facts (`missing_fact_ids`) are by definition not in the plant facts | Recommendation: a fact ID not in the facts reads **"not stated in the plant file"**; only a record ID the API returns 404 for reads "not addressable yet". |
| C12 | `CLAUDE.md` §9: "Every number shown carries its source link (record ID)"; spec tests: "every rendered number in the shortlist and detail fixtures sits inside a `Traced`" | The header's spend and budget, coverage counts and timeline totals are run or ledger figures, not records | Recommendation: the DOM test covers the shortlist and detail (as the spec says); the header's spend links to the run (`Traced id=<run ID>`, the run detail), and coverage counts link to their list's questions. Agree? |
| C13 | `CLAUDE.md` §4: "Bhargavi starts every live call herself" | B2 lets a UI click start a live run | The click is Bhargavi's, under a cap they type, with the cost line and confirm (P5-8); nothing starts a run without it. Recorded in decisions. Agree? |

### Answers (Bhargavi, 2026-10-23)

| # | Answer |
|---|---|
| C1 | Accepted: B3 resolves tool calls only. |
| C2 | **Not rank 1**: that's the C22 external-fire finding, not the Williams mechanism, and there's no S4 → S5 change. **The demo moment is rank 2, the `P-REB-START-2` startup chain** (`ch:EA-425B.design_pressure_kpa+…+f:proc:P-REB-START-2:early…`). It shows: the 1.6× evidence card; the RV-PATH-EA425B layer with its stored "does not apply" reason, and the `HV-B-SIN.normal_position` fact link in the drawer; and the engineer's override **S3 → S4**, with the gap going from about 1,000× to about 10,000×, recomputed by code. "No credit — inlet valve HV-B-SIN closed" leaves the demo-card requirements. The spec and `PROJECT.md` §14 change to match. The chain description is shown **as stored, with its unexpected-character flag visible**; no cleaning. *Checked $0: the chain's links, its layer reason, its evidence, its flag "unexpected character in model text: U+4E92 (chain description)" and its gap all match.* |
| C3 | Accepted: **tier derived on read, never written back, labelled "inferred"; an unknown model ID shows "unknown"**. New events write the tier directly. |
| C4, C5 | **The payload model is selected by the run's recorded era, never by a strict-then-loose fallback.** v1.9 events are strict; `step_finished` is a **per-step union with no extra fields**. **The events fixture is generated from the fake run, not by hand**, and a test checks that regenerating it gives the same file. |
| C6, C7 | Accepted: per-use budget rows in v1.9. **The start form picks the use (`development` or `video`), shows its remaining amount, shows spend cap + post cap = maximum, and refuses if the maximum is more than the remaining amount.** |
| C8 | Accepted: **overrides go in `guideword-demo.db`, which is what Phase 7 deploys; `guideword.db` stays the untouched record.** |
| C9–C12 | Accepted. |
| C13 | Accepted: the cap field is **never pre-filled**, and **Claude Code never clicks Start**; all tests use the fake gateway. |

### Gaps found on the reread (each with a recommendation; "Q" marks the ones that need your answer)

Q1–Q5 are answered below. Where this table's first wording differs, **the answers and the H rows win**: G1's field is `payload_schema` (H1); G4's single WG file becomes four legacy files (Q3, H2); G5's "stored runs read `development`" becomes `null` until the run names a use (Q4, H6).

| # | Gap | Recommendation | Lands in |
|---|---|---|---|
| G1 | **What records "the run's recorded era"?** Stored events have no version, and an extended pre-v1.9 run gets v1.9 events in a later pass, so a run can hold both. | **Q1.** Each event records its own payload schema: v1.9 `emit` writes `schema: "v1.9"` on the `Event` (a contract field); an event without it is pre-v1.9. The model is chosen by that field only. Pre-v1.9 events get one **legacy** model per type, its known fields typed, and extra fields allowed (the only extra-allowing models), never tried as a fallback for a v1.9 event. | B1 |
| G2 | **The per-step union needs every step's summary.** From the code and the stored runs: `chains` (connector, left_out, rejected, scenarios), `chain_severity` (answered, missing, missing_ids, outcome, re_ask, sent, sent_ids), `evidence` (on: block_list, evidence, lines, precedent_index_version, settings; off: evidence, reason), `retry_failed` (question_id, outcome, …), and the rest with no summary. | B1 lists each stepper's summary from its code, one model per step; a test runs every step of a fake run (evidence on and off, a retry, an extension) and validates each `step_finished`. | B1 |
| G3 | **A generated events fixture belongs to its fake run**, while the other run fixtures (shortlist, run dump, worksheet …) are hand-built for `run:8ede059837927e4a`. The run dump fixture's `events` would then be either hand-written (against the answer) or from another run. | **Q2.** Generate **every run-scoped fixture** (run detail, events page, shortlist, worksheet, coverage, record detail, run dump) from **one** $0 fake run of Mock Plant A, through the real API with mock mode off, then stamp `label.kind = "mock"`. `scripts/make_fixtures.py` writes them; `test_regenerating_the_fixtures_gives_the_same_files` checks it. The plant-only fixtures stay as they are. | B1 |
| G4 | **The frontend's replay of the WG run reads pre-v1.9 events**, but the fixtures (G3) would all be v1.9, so the legacy path and the "inferred" tier would have no test data. | **Q3.** Commit the WG final run's stored events once as `contract/fixtures/events_page_legacy.json`, exported by a $0 script. It's real recorded data, not hand-made, with `tier` added on read as "inferred". Timeline tests run on both fixtures. | B1, F3 |
| G5 | **The start form picks the use, but the API can't take one.** `StartRunRequest` has no `use`; `API_RUN_USE` is fixed at `development`; `LiveRuns` holds one gateway; and a `Run` records no use (checked: its fields are `attempt, cap_spent_usd, caps, id, label, mode, plant_record_id, post_spend_cap_usd, prompt_versions, reference_versions, routing_config, section_snapshot, spend_cap_usd, spent_usd, status, step`). So a later advance, resume or restart can't know the run's use. | **Q4.** v1.9 adds `use` to `StartRunRequest` (`development` or `video`) and to `Run`. It isn't hashed, so run IDs don't move, and stored runs read `development`. `LiveRuns` makes one gateway per use and drives each run with its own. `POST /runs` also refuses with 409 when spend cap + post cap is more than the use's remaining amount, so the server enforces the form's rule. | B1, B2 |
| G6 | **The phase cap can stop a UI run part-way.** Every API run books to phase "5" ($0.50) whatever its use, so a `video` run with $1.10 left could still stop at the phase cap. | The budget's v1.9 rows add the API runs' phase (`api_run_phase: {phase, cap_usd, spent_usd, remaining_usd}`). The form's maximum must fit both the use's remaining amount and the phase's, and it names which one limits. | B1, F3 |
| G7 | **The `video` use on a UI run** and the phase cap of $0.50: a WG-sized run (≈ $1.1) can't be started from the UI in Phase 5. | Stated in the start form ("up to $0.50 this phase"). No change to the cap without your say. | F3 |
| G8 | **Which store each acceptance step uses.** `guideword.db` stays untouched (C8), but acceptance 2 (a UI run) and acceptance 5 (upload, propose, confirm) write runs, plants and sections, and acceptance 4 writes an override. | **Q5.** Acceptance 1 and 4 (overrides) use `guideword-demo.db`. Acceptance 2 and 5 (new runs and plants) use a scratch store, `guideword-scratch.db`. Both are copies of `guideword.db` made by `scripts/copy_store.py` ($0), and both are git-ignored (`*.db`). `guideword.db` is opened read-only by every acceptance step. | P0, F6 |
| G9 | **`guideword-demo.db` doesn't exist yet**, and nothing makes it. | `scripts/copy_store.py <from> <to>` copies a store file and refuses to overwrite an existing target. Phase 7 deploys the demo store. | P0 |
| G10 | **Who does F6's click-through?** Claude Code never clicks Start (C13) and can't click in a browser from this terminal. | F6's manual acceptance is Bhargavi's: they click, take the screenshots, and make the paid UI calls. Cowork does the cold click-through (acceptance 6). Claude Code does the fixes, the README screenshots section and the PR. | F6 |
| G11 | **The spec still says "default from `GET /budget` hints"** for the spend cap, against C13. | P0 changes 5.3 to "never pre-filled; the use's remaining amount and the maximum shown". | P0 |
| G12 | **The demo override re-orders the shortlist.** At about 10,000× the chain ties rank 1's gap, and within a tier the server orders by gap. | The detail page reloads the shortlist after the override; F2's test asserts the order comes from the server and isn't kept on the client. | F2 |
| G13 | **Feature date Oct 24** (shortlist and detail with the demo moment) is tomorrow. P0, F0, F1 and F2 must all land by then. | F0 starts on v1.8 right after P0; B1's types follow. F2's demo fixture is the WG item (G14), so F2 doesn't wait for B1. | Order |
| G14 | **F2's demo fixture** must be the real rank-2 item, not an invented one. | `scripts/export_item.py <run> <target>` writes `GET /runs/{id}/shortlist`'s item for that target, plus the records the drawer opens, to `frontend/src/test/fixtures/wg_demo_item.json` ($0, from `guideword.db`, read-only). | F2 |

### Answers to Q1–Q5 (Bhargavi, 2026-10-23)

| # | Answer |
|---|---|
| Q1 | Accepted. **The schema stamp is added in one place, the event writer (`StepWriter.emit`), never at each call site.** The fake-run test fails if any emitted event lacks the v1.9 stamp. |
| Q2 | Accepted, but first **list the cases each hand-built fixture covers** (table F below). **The scripted fake gateway makes the generated Mock Plant A run cover every one**, with timestamps and durations frozen so regenerating matches exactly. |
| Q3 | **Changed: one legacy fixture per era** (a Phase 2 run, a Phase 3 run, WG for Phase 4). **A script picks the events**, so every event type in each run appears at least once, and **each file records its source run ID**. Not all 916 WG events. |
| Q4 | Accepted, plus: **a run's use is fixed at start; an advance or resume with a different use gets a 409. An old run with no use must name one on its first advance (no default); it's then stored.** |
| Q5 | Accepted. **Both copies go in `.gitignore`. Acceptance steps open `guideword.db` with SQLite `mode=ro`.** |

### F. The cases the hand-built fixtures cover today (Q2: the generated run must cover each)

Read from `contract/fixtures/` ($0). "Run" is the hand-built `run:8ede059837927e4a`.

| Fixture | Cases it covers |
|---|---|
| `run_dump.json`, `question_list.json` | questions of 8 kinds: matrix, chemical pair, chemical environment, procedure step, relief discharge, planned work, engineer (and their origins: matrix, cross list, engineer); statuses **answered**, **not credible with its reason** (`m:S-MX-1:more:pressure`), **failed** (`work:W-1:MX-1`), **open engineer question** (`eng:`) |
| `run_dump.json` findings | 4 findings: tiers lightning and ultra; library causes (C01, C14, C20) and an **outside-library cause**; adequacy adequate, inadequate and unknown; confidence sure and unsure; severities S2, S3, S4; one finding with no safeguards |
| `run_dump.json` hypotheses | **h:1 with linked questions** (confirmed tier) and **h:2 with none** (unconfirmed tier) |
| chains | one two-link chain (a pair finding + a relief finding), no flags |
| LOPA | **complete with a credited layer and a not-credited one** ("not argued — no credit"); **a chain LOPA with no layers** (gap 1,000); **incomplete**: `L-12.length_m` missing, frequency null, gap null, flag "code-only LOPA: layers not argued"; `modifiers_not_applied` on each |
| recommendations | one, on the chain |
| evidence | **calculation confirmed** (heat-up rate, with its tool call); **calculation skipped** (blocked-in heating, verdict none, "skipped: no va…"); **precedent confirmed** (mock source); **precedent none** |
| `shortlist.json` | **confirmed** tier (a chain under h:1, with its support finding), **also found** (a finding with a gap of 10; a finding with an **incomplete LOPA**, its flag and "incomplete: L-12.length_m missing"), **unconfirmed** (h:2, no gap); `multi_failure`, `unsure` both ways; recommendations present and absent |
| `coverage.json` | 10 lists, including **empty ones** (no-flow line, dust); an **unsure** count; a **failed** question; an engineer question not yet checked |
| `worksheet.json` | 4 rows, the §5 Step 8 columns, **no override state** |
| `record_detail.json`, `record_detail_hypothesis.json` | a finding with a parent, one model call and one tool call; a hypothesis with one model call and no tool call |
| `override_result.json` | a **change_severity** S3 → S4 with its reason, the reviewer and time, `replaces: null`, **`stored: false`** (the mock echoes) |
| `question_created.json` | a new engineer question, open |
| `run_status_result.json` | **cancelled** |
| `start_run_result.json` | an estimate of $0.40 |
| `run_detail.json`, `run_list.json`, `run_sections.json` | the run's 15 fields, 7 counts; one run; 7 sections (3 equipment, 2 lines, a procedure, planned work) |
| `events_page.json` | 16 of the 18 event types (all but `cap_hit`, `run_extended`; it has `hypothesis_dropped`) in 20 events |
| Plant-scoped (stay hand-built): `mock_plant_a.json`, `plant_detail.json`, `plant_list.json`, `plant_upload_result.json`, `section_proposal.json` (2 suggestions: purpose, split), `confirm_sections_result.json`, `budget.json`, `accepted.json`, `demo_response.json` | — |

**Two hand-built cases a real run can't produce**, and their generated equivalents:
- an **Ultra outside-library finding with no model call** (`model_call_id: null`): generated, it carries its call;
- **"cancelled" for a finished run's ID**: generated, it comes from a second Mock Plant A run with another cap (its own ID).

**Cases the generated run adds:** `cap_hit` then `run_extended` (the run stops at its analysis cap and is extended), a stored override with its worksheet override state, `hypothesis_dropped`, and the tier on every `model_call` and `dispatch`.

### Gaps found on the second reread ("Q" = needs your answer)

| # | Gap | Recommendation | Lands in |
|---|---|---|---|
| H1 | **A field named `schema` breaks on Pydantic.** Checked: `class E(BaseModel): schema: str` raises "Field name "schema" shadows an attribute in parent BaseModel" under `-W error`. | **Q6.** Name it **`payload_schema`** (`Literal["v1.9"] \| None`), in Python and in JSON. | B1 |
| H2 | **The three era runs don't cover every stored shape.** Picked per era, all three of them pure (checked against the ledger's phases): Phase 2 `run:e4f544ce3e94a468` (case D, 10 types, 15 shapes), Phase 3 `run:4e6842d31fbdee3b` (WG's first run, 15 types, 36 shapes), Phase 4 `run:76f8ee0b5d1f078e` (15 types, 34 shapes). Together they cover **44 of the 52** payload shapes in `guideword.db`. The other 8 occur only in extended runs: 2 `cap_hit` (D `run:6e4f55dd0daaaa31`), 3 `dispatch` (D attempts 1 and 2, G), 2 `run_extended` (evidence-only and rerun-from, D attempt 2) and a `chain_severity` `step_finished` (D attempt 2). | **Q7.** The three era files as asked, picked by one script: the first event of each (type, step, payload keys), 15 + 36 + 34 events, each file naming its source run. **Plus a fourth file, `events_legacy_other_shapes.json`, with the 8**, each event naming its own source run. No era is claimed for them, because a mixed run's era per event isn't recorded. `scripts/check_event_payloads.py` still validates all events in the store ($0, mode=ro). | B1 |
| H3 | **Two event types were never stored**: `hypothesis_dropped` and `run_failed`. They need no legacy model. The main generated run can emit 17 of the 18 types, but it can't both finish and fail. | **Q8.** A third small generated Mock Plant A run that fails (the gateway scripted to fail twice); its events go in `events_page_failed.json`, so the timeline shows `run_failed` from real emitted data. | B1 |
| H4 | **Q4 needs the advance route to carry a use.** `POST /internal/runs/{id}/advance` takes no body today. | v1.9 adds `AdvanceRequest {use: BudgetUse \| null}`. An advance with a use different from the run's → 409. An advance without one on a run with no use → 409 "name a use". `POST /runs` makes `use` **required**; a resume with a different use → 409, and an old run without a use stores the one given. | B1, B2 |
| H5 | **Q4 reaches past the API.** `start_run` (`runs/start.py`) takes no use; only the gateway knows it. `extend` (`runs/extend.py`) doesn't either, and `scripts/extend_run.py` **defaults `--use` to `development`**, which is the default Q4 rules out. | **Q9.** `start_run(use=…)` stores it; `run_case.py` passes its `--use`. `extend(use=…)` applies the same rule; `extend_run.py`'s `--use` loses its default and is needed only when the run has none. **One check in the run machine:** a step refuses to run when the gateway's use differs from the run's, so no path can drive a run on another use. | B1, B2 |
| H6 | **My plan said "stored runs read `development`"**, against Q4's no-default rule. | Fixed: `Run.use: BudgetUse \| None = None`; a stored run reads `null` until it names one. | B1 |
| H7 | **Which uses can a UI run take?** The form offers `development` and `video`; listing them in the frontend would be a hard-coded value. | `config/caps.yaml` gains `api_run_uses: [development, video]` (laptop), served on `Budget`; `POST /runs` refuses any other use with 409. | P0, B1 |
| H8 | **The spec's acceptance 2 cap can't be started.** "cap $0.40" + the default post cap $0.30 = $0.70, above the Phase 5 cap of $0.50, and acceptance 5 ($0.05) shares that cap. | **Q10.** Either (a) acceptance 2 uses spend cap $0.15 (0.15 + 0.30 + 0.05 = $0.50), or (b) the Phase 5 cap rises to $0.80, or (c) acceptance 2 is the WG replay only. I recommend (a). | P0, spend |
| H9 | **The generator must never touch the real ledger or store.** The fake gateway writes ledger lines like a live one. | `make_fixtures.py` uses a temporary store and a temporary ledger only; a test asserts `budget/ledger.jsonl` and `guideword.db` are untouched (same hash) after a run of it. | B1 |
| H10 | **Frozen time.** The API's clock and the gateway's `timer` are already injectable (`app.py` `clock`, `client.py` `timer=time.perf_counter`). | The generator injects a fixed clock (2026-10-13T10:00:00Z, +1 s per tick) and a timer that moves 250 ms per call. | B1 |
| H11 | **The generated run's ID is content-hashed** from the prompt, reference and routing versions. So any later PR that changes one of them must regenerate the fixtures (the regeneration test fails until it does). | Recorded in `docs/decisions.md`. **Frontend tests read IDs from the fixtures, never type them in.** | B1, frontend |
| H12 | **The mock mode echoes and never stores**, but a generated override is stored. | After generation, exactly two stamps: `label.kind = "mock"`, and `override_result.stored = false`. The stamp list lives in the script and is tested. Nothing else is edited. | B1 |
| H13 | **Plant fixtures stay hand-built, but must agree with the generated run.** | A test checks the run fixtures' `plant_record_id` and section IDs equal `plant_detail.json`'s. `demo_response.json` (a Phase 7 route) is assembled from the generated run and shortlist plus the hand-built plant. | B1 |
| H14 | **Stored `dispatch` events have no model ID**, so C3's inference covers only `model_call`. Checked: a stored `dispatch` carries its `level` (`bulk`, …), and the run records its `routing_config` (`specialist_bulk: lightning`, …). | A legacy `dispatch`'s tier is `routing_config[JOB_FOR_LEVEL[level]]` from **its own run's record**, labelled "inferred"; no job, no tier ("unknown"). | B1 |
| H15 | **Opening read-only.** Checked $0 on a scratch copy: `DATABASE_URL=sqlite:///file:<path>?mode=ro&uri=true` serves reads through the real session factory, a write is refused ("attempt to write a readonly database"), and the file's hash is unchanged. A write route would then answer 500. | No code change to open it. The scripts that read the record (`copy_store.py`, `export_item.py`, the legacy export, `check_event_payloads.py`) open it this way; `test_source_store_is_opened_read_only`. The acceptance steps that read `guideword.db` write nothing; no new error code. | P0, B1, F6 |
| H16 | **Stores for acceptance 3, 6 and 7** weren't assigned. | 3 (the WG replay): **`guideword.db` with `mode=ro`**. 6 (Cowork's cold click-through, which may override): `guideword-scratch.db`, so the demo store stays clean. 7 (screenshots): `guideword-demo.db`. | F6 |
| H17 | **`.gitignore` already ignores `*.db`** (line 16). | Both names are added explicitly anyway (Q5), with a comment. | P0 |

### Answers to Q6–Q10 (Bhargavi, 2026-10-23)

Q10 replaces C7's "no contract change" (the post cap becomes a request field) and H8's $0.30 post cap.

| # | Answer |
|---|---|
| Q6 | Accepted: **`payload_schema`**. |
| Q7 | Accepted: the fourth file. **Plus a $0 local script that parses every one of the 52 payload shapes in `guideword.db` with the models; its result is recorded in `docs/decisions.md`.** |
| Q8 | Accepted: the failing run and `events_page_failed.json`. |
| Q9 | Accepted, all three. **`--use` is a required argument on `extend_run.py`.** |
| Q10 | **(a), adjusted: the post cap is editable on the start form.** Acceptance 2 uses a **$0.15 spend cap and a $0.10 post cap ($0.25 maximum)**. With acceptance 5 that's $0.30 of the $0.50, leaving room for one redo. Acceptance 2 is reworded: **"a UI-started run streams live and ends in finished or a cap stop; the UI shows which, with spend against the cap."** No cap raise. |

### Gaps found on the third reread ("Q" = needs your answer)

| # | Gap | Recommendation | Lands in |
|---|---|---|---|
| J1 | **An editable post cap is a contract change**, and it reverses C7's "no contract change". `StartRunRequest` is `{plant_id, spend_cap_usd, mode}`, and a UI run gets `caps.yaml`'s `post_spend_cap_usd: 0.30`. | v1.9 adds `StartRunRequest.post_spend_cap_usd`, ≥ 0. "Not doing: the post cap" is removed, and C7 is marked as replaced by Q10. `runs/start.py` already takes it. | B1 |
| J2 | **Is the post cap pre-filled or defaulted?** C13 says the spend cap is never pre-filled; an omitted post cap would silently fall back to 0.30. | **Q11.** The post cap field is **never pre-filled**, the same as the spend cap, and `post_spend_cap_usd` is **required** in the request (no server default for UI runs). `caps.yaml`'s 0.30 stays the default only for `run_case.py`. | B1, F3 |
| J3 | **A resume with another post cap** is silently ignored today: the post cap is stored only on a new run and isn't part of the ID. | **Q12.** Same rule as the use: a `POST /runs` resume with a post cap different from the stored one → 409, naming the stored one. Raising a post cap stays the job of `extend_run.py` (not in the UI this phase). | B2 |
| J4 | **"The UI shows which" cap stopped the run, but `cap_hit` doesn't always say.** `stop_for_refusal` writes `cap` only for the post cap (`machine.py` line 155); an analysis-cap stop has no `cap`, and a budget stop has `status: stopped_budget`. | The v1.9 `cap_hit` model makes `cap: "analysis" \| "post" \| null` **always present** (null for a budget or allowance stop), written by `stop_for_refusal`. The live screen's end banner reads finished, analysis cap, post cap or budget, with spent vs that cap. | B1, F3 |
| J5 | **"Room for one redo" holds for acceptance 5 but not always for acceptance 2.** The start is refused when the maximum ($0.25) exceeds the phase's remaining amount; after the first two steps that's 0.50 − 0.05 − (what the first run actually spent). | Stated in the spend table: **a redo of acceptance 2 can start only if the first run spent ≤ $0.20**; a redo of acceptance 5 always fits. No cap raise. | spend |
| J6 | **Other scripts that start runs keep a `--use` default.** Every new run goes through `start_case` (`runs/case.py`), which calls `start_run`. It has three callers: `api/live.py`, `scripts/run_case.py` and `scripts/screen_check.py`, and both scripts default `--use` to `development`. Q9 names only `extend_run.py`. | **Q13.** `start_case(use=…)` is required and passes it to `start_run`. `--use` becomes required on `run_case.py` and `screen_check.py` too, since each starts a run whose use is now fixed for life. | B1, B2 |
| J7 | **The 52-shape check needs a home.** `scripts/check_event_payloads.py` was planned as a pass/fail over all events. | It reports each of the 52 (type, step, payload keys) shapes with its source run, the model that parsed it, and pass or the error, and exits non-zero on any failure. Opened `mode=ro`. I run it ($0) and record the table's result in `docs/decisions.md` in B1's PR. A unit test runs it on a small synthetic store. | B1 |

### Answers to Q11–Q13 and a standing rule (Bhargavi, 2026-10-23)

| # | Answer |
|---|---|
| Q11 | Accepted: the post cap field is never pre-filled, and `post_spend_cap_usd` is required in the request. |
| Q12 | Accepted: a resume with a different post cap → 409, naming the stored value. |
| Q13 | Accepted: `start_case(use=…)` required; `--use` required on `run_case.py` and `screen_check.py`. |

**Standing rule for the rest of Phase 5.** A question that follows from an approved rule is not asked. The rule is applied, logged in `docs/decisions.md`, and work continues. The approved rules:
- no cap and no use is pre-filled or defaulted;
- a run's use and caps are fixed when it starts;
- a mismatch gets a 409 naming the stored value;
- nothing is ever loosened silently.

Anything outside these rules still stops for a question (`CLAUDE.md` §13).

---

## 3. P5-1…P5-10: my reading

| # | Spec's recommendation | My view |
|---|---|---|
| P5-1 | Typed event payloads (v1.9), `tier` on `model_call` and `dispatch`, fixture regenerated, every emitted payload validates | **Agree, with C3–C5.** |
| P5-2 | Laptop runs from the UI driven in-process | **Agree.** One driver per run, guarded in `LiveRuns` (a lock and a set of run IDs being driven), shared with `advance`'s background drive, so the button and `advance` never drive one run twice. |
| P5-3 | No new runtime dependencies | **Agree.** No dev dependency either: `fireEvent` instead of `user-event`. |
| P5-4 | Live polling + labelled replay | **Agree.** The replay schedules by each event's `time` and `seq`, speed 1×/10×/60×/max, with the banner always on. |
| P5-5 | One number formatter | **Agree.** |
| P5-6 | `Traced` + record drawer | **Agree, with C11.** |
| P5-7 | Engineer name in `localStorage`; no overrides on `recorded`/`mock` | **Agree.** |
| P5-8 | Paid actions explicit | **Agree, with the cost line: spend cap + post cap = the maximum (Q10).** |
| P5-9 | Screen priority 4 → 5 → 3 → 7 → 6 → 2 → 1 | **Agree.** |
| P5-10 | Visual direction | **Agree.** |

---

## 4. Per item

### P0 — `phase-5/docs` (docs and config; backend worktree)
- `specs/phase-5.md` (approved), amended to the answers:
  - the demo moment is the rank-2 startup chain with S3 → S4 (C2);
  - the tier is inferred on read (C3);
  - payload models by era, strict v1.9 events, and generated fixtures (C4, C5, G1–G4);
  - the use picked on the start form, and the cap never pre-filled (C6, C13, G5, G11);
  - the demo store (C8, G8).
- This plan.
- `docs/decisions.md`: P5-1…P5-10, C1–C13 and Q1–Q13 as answered, the standing rule, and H11 (fixtures regenerate with any prompt, reference or routing change).
- `PROJECT.md`:
  - §11: typed event payloads (v1.9), `tier` on `model_call` and `dispatch`, budget per use (C6);
  - §12: hash routes, the record drawer, live and replay modes, UI-started laptop runs;
  - §14: the demo moment as answered in C2 (the startup chain; S3 → S4; the description shown with its flag);
  - §15: Phase 5 dates (C10).
- `config/caps.yaml`: `phase_caps_usd."5": 0.50` (no raise, Q10); `api_run_uses: [development, video]` (H7).
- `.gitignore`: `guideword-demo.db` and `guideword-scratch.db`, named (Q5, H17).
- The spec's acceptance 2, as Q10 answers: $0.15 spend cap + $0.10 post cap, reworded "a UI-started run streams live and ends in finished or a cap stop; the UI shows which, with spend against the cap" (H8).
- `scripts/copy_store.py` (G8, G9): opens the source with `mode=ro` and copies it through SQLite's backup API. Tests: `test_copy_store_refuses_to_overwrite`, `test_copy_store_copies_every_table` and `test_copy_store_leaves_the_source_unchanged` (H15).
- **Tests:** the config test that pins the phase caps gains `"5"`.

### B1 — `contract/event-payloads` (v1.9; backend worktree)
- **Files:**
  - `backend/guideword/schema/events.py` (new):
    - one **strict** v1.9 payload model per `EventType`;
    - `step_finished` as a **per-step union** with no extra fields (G2);
    - one **legacy** model per stored type (16; H3), for events without the stamp (G1), the only models that allow extra fields;
    - the model is chosen by the event's `payload_schema` field only (H1).
  - `schema/records.py`:
    - `Event` gains `payload_schema: Literal["v1.9"] | None = None` (G1, H1);
    - `payload` is discriminated on `type` and chosen by `payload_schema`;
    - `Run` gains `use: BudgetUse | None = None`, not hashed; a stored run reads `null` (G5, H6).
  - `runs/store.py`: **`emit` is the one place that stamps `payload_schema: "v1.9"`** and validates the payload against its model before writing (Q1); no call site sets the stamp;
  - `orchestrator/loop.py`, `runs/store.py` (`add_model_call`): `tier` on `dispatch` and `model_call` (from the gateway result's tier, passed in);
  - `api/live.py` events read, for unstamped events only, never written back (C3):
    - `model_call`: `tier` from `model_id` against `models.yaml`;
    - `dispatch`: `tier` from the run's own `routing_config[JOB_FOR_LEVEL[level]]` (H14);
    - both with `tier_source: "inferred"`; nothing found gives `tier: null`, shown "unknown";
    - new events carry `tier_source: "recorded"`.
  - `api/models.py`:
    - `Budget.uses` (C6), `Budget.api_run_phase` (G6) and `Budget.api_run_uses` (H7);
    - `StartRunRequest.use` and `StartRunRequest.post_spend_cap_usd`, both **required** (G5, H4, J1, J2);
    - `AdvanceRequest {use: BudgetUse | null}`, the advance route's new optional body (H4).
  - **Fixtures generated, not hand-written** (C5, G3, Q2): `scripts/make_fixtures.py`, with its scripted fake gateway kept in `scripts/` (scripts never import tests):
    - three $0 fake runs of Mock Plant A through the real API, on a temporary store and ledger (H9), with a frozen clock and timer (H10):
      - **the main run**, covering every case in table F, plus `cap_hit` → `run_extended`, a stored override and `hypothesis_dropped`;
      - **a cancelled run** (another cap), for `run_status_result.json`;
      - **a failing run**, for `events_page_failed.json` (H3, Q8);
    - it writes every run-scoped fixture and assembles `demo_response.json` (H13);
    - then only the two stamps: `label.kind = "mock"` and `override_result.stored = false` (H12);
  - **legacy fixtures** (Q3, H2, Q7), picked by `scripts/export_legacy_events.py` ($0, `mode=ro`) as the first event of each (type, step, payload keys), each file naming its source run:
    - `events_legacy_phase2.json` from `run:e4f544ce3e94a468` (15 events);
    - `events_legacy_phase3.json` from `run:4e6842d31fbdee3b` (36);
    - `events_legacy_phase4.json` from `run:76f8ee0b5d1f078e` (34);
    - `events_legacy_other_shapes.json`: the 8 remaining shapes, each event naming its run;
  - `runs/start.py` and `runs/case.py`: `start_run(use=…)` stores the use, and `start_case(use=…)` requires it; all three callers pass it (H5, J6);
  - `runs/machine.py`: `stop_for_refusal` always writes `cap` on `cap_hit`: `analysis`, `post` or null (J4). (The gateway-use check moved to B2.)
  - `scripts/check_event_payloads.py`: the 52-shape report (Q7, J7).
  - `contract/fixtures/budget.json`: `uses`;
  - regenerated `openapi.json`, schemas and `frontend/src/api/types.ts` (C9);
  - `scripts/check_event_payloads.py`: a $0 check of every stored run's events against the models, run once by Bhargavi or me on the local store, result in the PR.
- **Tests first:**
  - `test_every_event_type_has_a_payload_model`;
  - `test_a_fake_runs_emitted_events_all_validate` (a whole $0 fake run through the nine steps, extension and a re-run included);
  - `test_emit_refuses_a_payload_its_model_rejects`;
  - `test_model_call_and_dispatch_events_carry_the_tier`;
  - `test_stored_model_call_events_get_their_tier_on_read` (and `null` for an unknown model);
  - `test_step_finished_keeps_its_step_summary`;
  - `test_regenerating_the_fixtures_gives_the_same_files` (C5, G3);
  - `test_the_generated_run_covers_every_case_in_table_f` (Q2: one assertion per row of table F, plus the added cases);
  - `test_making_fixtures_leaves_the_real_ledger_and_store_untouched` (H9);
  - `test_only_the_two_mock_stamps_differ_from_the_api_output` (H12);
  - `test_run_fixtures_agree_with_the_plant_fixtures` (H13);
  - `test_every_emitted_event_carries_the_v1_9_stamp` (Q1: the fake runs fail on any event without it);
  - `test_no_call_site_sets_payload_schema` (Q1: an AST check that only `emit` writes it);
  - `test_the_legacy_fixtures_validate_with_the_legacy_models_and_v1_9_events_never_do` (G1, Q3);
  - `test_each_legacy_fixture_names_its_source_and_has_each_type_of_that_run` (Q3: the type list per source run is stored in the file and checked);
  - `test_a_legacy_dispatch_gets_its_tier_from_its_runs_routing_config` (H14);
  - `test_cap_hit_names_the_analysis_cap_the_post_cap_or_none` (J4);
  - `test_check_event_payloads_reports_each_shape_and_fails_on_a_bad_one` (J7, a synthetic store);
  - `test_start_needs_a_post_cap` (J2);
  - `test_a_v1_9_event_with_an_unknown_field_is_refused`;
  - `test_every_step_summary_validates_against_its_step_model` (G2: evidence on and off, a retry, an extension, a re-run);
  - `test_stored_tier_is_labelled_inferred_and_never_written_back` and `test_an_unknown_model_id_has_no_tier` (C3);
  - `test_a_run_records_its_use_and_stored_runs_read_null` (G5, H6);
  - `test_budget_lists_each_use_and_the_api_run_phase_with_what_remains` (C6, G6);
  - the contract tests' fixture-per-model check;
  - frontend lint, typecheck and tests on the regenerated types.
- **Tag** `contract-v1.9` after merge (Bhargavi).

### B2 — `phase-5/drive-laptop-runs` (backend worktree)
- **Files:**
  - `api/app.py`:
    - `POST /runs` adds `live().drive` as a background task when not mock and `guideword_env == laptop`;
    - it refuses with 409 when spend cap + post cap is more than the use's remaining amount or the phase's remaining cap, naming which (G5, G6);
    - it refuses with 409 a use not in `api_run_uses` (H7);
    - *done in B1 (7c448da):* a resume with another use or post cap → 409 naming the stored value; a run with no use stores the one given; `advance` refuses another use, needs one for a run with none, and stores it (Q4, Q12, H4);
    - **remove the interim `one_gateway_use` refusal** (B1, 2026-10-23: until per-use gateways, the API spends `development` only), in the same PR as the per-use gateways;
    - the maximum checked is the request's spend cap + its post cap (Q10);
    - `API_RUN_PHASE` "4" → "5";
  - `runs/machine.py`: a step refuses to run when the gateway's use differs from the run's (H5; moved here from B1, 2026-10-23);
  - `api/live.py`:
    - one gateway per use;
    - each run is driven with its own recorded use (G5);
    - `drive` holds a per-run guard (a lock and a set), and returns at once when the run is already being driven;
    - `advance`'s background drive goes through the same guard.
  - `runs/extend.py`: `extend(use=…)`, with the same rule (H5);
  - `scripts/extend_run.py`: **`--use` is required** (Q9); refused when it differs from the run's; stored when the run has none (H5);
  - `scripts/run_case.py` and `scripts/screen_check.py`: pass `--use` to `start_case`, and `--use` becomes required on both (H5, J6, Q13).
- **Tests first:**
  - `test_a_run_started_through_the_api_reaches_finished_with_no_further_request` (fake gateway);
  - `test_a_second_start_of_a_driving_run_starts_no_second_driver`;
  - `test_advance_and_start_never_drive_one_run_twice`;
  - `test_a_hosted_or_mock_app_does_not_drive_on_start`;
  - `test_cancel_stops_a_background_drive`;
  - `test_api_runs_charge_phase_5`;
  - `test_a_run_is_driven_with_its_own_use` (a `video` run's ledger lines carry `video`; G5);
  - `test_start_refuses_a_maximum_above_the_uses_remaining_amount_or_the_phase_cap` (G5, G6);
  - `test_start_refuses_a_use_not_offered_to_api_runs` (H7);
  - *(the Q4 resume and advance tests landed in B1)*;
  - `test_a_video_run_starts_and_advances_through_the_api_once_gateways_are_per_use` (the interim refusal's removal);
  - `test_the_machine_refuses_a_gateway_of_another_use` (H5, moved from B1);
  - `test_extend_refuses_another_use_and_stores_one_when_the_run_has_none` (H5);
  - `test_extend_run_requires_use`, `test_run_case_requires_use` and `test_screen_check_requires_use` (Q9, J6);
  - `test_a_resume_with_another_post_cap_is_refused_with_409` (J3).

### B3 — `phase-5/records-addressable` (backend worktree)
- **Files:** `api/live.py` `record()`: `tc:` tool calls (kind `tool_call`; parent: its agent step; its own record), so every timeline entry opens in the drawer.
- **Tests first:**
  - `test_record_detail_returns_a_tool_call_with_its_step`;
  - `test_every_timeline_entry_of_a_fake_run_is_addressable` (each event's record ID resolves, or the event names none).

### Frontend (its own worktree: `git worktree add ..\guideword-frontend -b phase-5/shell`)

Every PR runs `npm run lint`, `npm run typecheck`, `npm test`. Tests use `contract/fixtures/*.json` through a fake `fetch`; `tsconfig.json` gains `resolveJsonModule` and includes the fixtures; each fixture is assigned to its generated response type, so a drifting fixture fails `typecheck`. **Every screen's tests include "renders from its fixtures with no console error"** (the spec's screens-on-fixtures line). **Tests read record IDs from the fixtures and never type them in**, because a regenerated run's IDs change (H11).

#### F0 — `phase-5/shell` (5.0)
- **Files:**
  - `src/app/router.ts`: hash routes, URL-encoded IDs;
  - `src/app/Shell.tsx`: the header (plant and run selectors, label banner, status and step, spend vs cap, engineer name, budget);
  - `src/api/client.ts`: typed from `types.ts`; one `ApiError`;
  - `src/api/hooks.ts`: `useResource`, `usePolling`;
  - `src/format/number.ts`, `time.ts`, `ids.ts`;
  - `src/ui/Traced.tsx`, `RecordDrawer.tsx`, `Chip.tsx`, `Flags.tsx`, `CostLine.tsx`, `ConfirmInline.tsx`;
  - `src/ui/tokens.css` and base styles (light theme plus `prefers-color-scheme: dark` tokens);
  - `vite.config.ts`: the dev proxy to `127.0.0.1:8000`;
  - `src/test/fakeFetch.ts`.
- **Tests first:**
  - **router:** every route builds and parses, with IDs containing `:`, `~`, `+`;
  - **client:** 501 names the phase, 403 reads "recorded and read-only", 404, 409 shows the server's detail, a network error offers retry; no override request is sent on a `recorded` or `mock` label;
  - **number formatter:** every P5-5 rule, float noise (0.010000000000000002 → "0.01"), boundaries, `null`;
  - **record drawer:** a record with parents and calls; a missing fact reads "not stated in the plant file" (C11); an unknown ID reads "not addressable yet";
  - **label banner:** live, recorded with its date and cost, mock;
  - **header:** the plant and run selectors list `GET /plants` and `GET /runs`, and change the route;
  - **engineer name:** survives a reload, and `localStorage` failing is handled.

#### F1 — `phase-5/shortlist` (5.1)
- **Files:**
  - `src/screens/Shortlist.tsx`, `src/screens/ShortlistCard.tsx`;
  - `src/model/shortlist.ts`: pure; groups by tier, keeping the server's order.
- **Tests first:**
  - three tier groups in order, never re-sorted;
  - every flag shown verbatim;
  - `gap_text` shown as served; no component formats a gap;
  - up to 3 evidence chips with their summaries;
  - unconfirmed cards carry their flag;
  - keyboard navigation;
  - **every number on a card sits inside a `Traced`** (a DOM walk over text nodes with digits).

#### F2 — `phase-5/finding-detail` (5.2)
- **Files:**
  - `src/screens/Detail.tsx`, `src/screens/LopaTable.tsx`, `EvidenceCards.tsx`, `Overrides.tsx`;
  - `src/model/lopa.ts`: pure; layer rows, with Ultra's and code's columns.
- **Tests first:**
  - **chain detail:** the links in order, findings and facts each traced;
  - **LOPA:** a refused layer shows code's reason and Ultra's argument apart, styled refused; `complete: false` lists its missing facts;
  - **evidence:** the summary verbatim, cited facts traced, sources open in a new tab, the precedent's source type;
  - **supporting findings:** `support_finding_ids`, each traced;
  - **recommendations:** accept, reject and edit the action, each sending its override and reloading;
  - **accept, reject and edit consequence** on a finding; accept and reject on a chain;
  - **change severity:** sends exactly `{target_id, action: "change_severity", new_value: {severity_class}, reason, by}`, then reloads the item;
  - **change credit:** shows the §23 limit text;
  - **read-only runs:** overrides are disabled on `recorded` and `mock` labels with the reason;
  - **the demo moment** (C2) on `wg_demo_item.json`, the real rank-2 item exported by `scripts/export_item.py` (G14):
    - the 1.6× evidence card, with its cited facts traced;
    - the RV-PATH-EA425B layer showing its stored "does not apply" reason verbatim;
    - `HV-B-SIN.normal_position` among the chain's links, opening in the drawer with its value and source;
    - the description shown as stored, ending "…that互", with its flag "unexpected character in model text: U+4E92 (chain description)" visible;
    - the S3 → S4 override form sending exactly the change-severity body;
    - after reload, the gap text is the server's (on a fake response of about 10,000×) and the shortlist order is the server's (G12).

#### F3 — `phase-5/live-run` (5.3; after B1, B2)
- **Files:**
  - `src/screens/Live.tsx`, `src/screens/Timeline.tsx`, `src/screens/RunStart.tsx`;
  - `src/api/useEvents.ts`: live mode by `next_after`, replay mode;
  - `src/model/timeline.ts`: pure; grouping, the model mix per tier.
- **Tests first:**
  - **timeline grouping:** `events_page.json` (v1.9), `events_page_failed.json` (H3), and the four legacy files (Q3, H2) give the expected groups; tier chips come from the payload's `tier`, and "inferred" and "unknown" are shown as such (C3);
  - **replay:** events play in `seq` order and none is skipped or added; the banner is always present; speed changes keep the order;
  - **live mode:** polling stops when the run ends and while the tab is hidden;
  - **start form** (C6, C7, C13, G5–G7):
    - the use picker lists `Budget.api_run_uses` (H7) and shows the use's remaining amount and the phase's;
    - the spend cap and the **post cap** fields, both editable and **never pre-filled** (Q10, J2);
    - spend cap + post cap = the maximum, shown;
    - Start is refused, with the reason, when the maximum is more than either remaining amount;
    - confirm is built into the page;
    - the request carries `use`;
  - **side panel:** coverage bars from the latest `coverage_updated.lines`, the findings count, spend vs cap, and the model mix (calls and cost per tier, a pure function);
  - **end state** (Q10, J4): finished, stopped at the analysis cap, stopped at the post cap, or stopped by the budget, each named, with spend against that cap;
  - **cancel:** the cancel button;
  - **auto-scroll:** it follows new events unless the user has scrolled up.

#### F4 — `phase-5/coverage-worksheet` (5.4, 5.5)
- **Files:**
  - `src/screens/Coverage.tsx`, `src/screens/Worksheet.tsx`;
  - `src/model/worksheet.ts`: pure; the filters.
- **Tests first:**
  - **coverage:** rows and totals from `coverage.json`; failed questions traced; adding an engineer question posts and lists it as open;
  - **worksheet:** the §5 Step 8 columns in order; every filter (a pure function); row actions follow the override rules; the export links.
- **Virtualisation:** measured on the WG run first (it has about 300 rows); none unless it's slow.

#### F5 — `phase-5/plant-sections` (5.6, 5.7)
- **Files:**
  - `src/screens/Plants.tsx`, `src/screens/PlantInput.tsx`, `src/screens/Sections.tsx`, `src/screens/PlantDiagram.tsx`;
  - `src/model/layout.ts`: pure; longest-path layering, ties by ID.
- **Tests first:**
  - **layout:** deterministic for the same facts; every line an edge; sources on the left;
  - **sections:** no-flow sections dashed; refused suggestions show code's reason; accept and reject each suggestion; rename and edit purpose; confirm sends the PUT; a refused merge of a no-flow section shows the server's reason;
  - **plant input:** an upload (file input and drag and drop) shows errors and warnings with object IDs; the facts table's counts and the "assumed" and "not stated" filters;
  - **plant list:** each plant with its status and its runs.

#### F6 — `phase-5/real-api`
- Bhargavi's click-through on the real backend (G10):
  - acceptance 1, 4 and 7 against `guideword-demo.db`;
  - acceptance 2 and 5 against `guideword-scratch.db` (G8), and Cowork's acceptance 6 there too (H16);
  - acceptance 3 (the WG replay) against `guideword.db` opened with `mode=ro` (Q5, H15);
  - `guideword.db` is never opened writable;
  - plus one dev case.
- Claude Code does the fixes and the PR; Cowork does the cold click-through.
- Fixes, and 1920×1080 screenshots of all seven screens for the README.
- Acceptance 1–7 recorded in the PR.

---

## 5. Order

1. **P0** (docs and config) → **B1** (v1.9, tagged) → **B2** and **B3** in parallel (backend worktree).
2. **F0** can start on v1.8 as soon as P0 merges; it rebases on B1's types. F1 and F2 don't wait for B1: F2's demo test uses the exported WG item (G13, G14).
3. **F1**, then **F2** (the demo moment, feature date Oct 24).
4. **F3** after B1 and B2 (Oct 25).
5. **F4** and **F5** in parallel after F0 (Oct 26).
6. **F6** last.

The cut line follows P5-9: if time runs out, it runs out at the end of 4 → 5 → 3 → 7 → 6 → 2 → 1.

## 6. Not doing
- `GET /demo`, demo mode, browser-only overrides on a recorded run, the hosted live-run button and its limits, Vercel, and hosted chaining (Phase 7).
- Any change to ranking, LOPA, evidence or prompts, and any new runtime or dev dependency.
- Authentication and multi-user editing. Mobile layout beyond "doesn't break at 400 px".
- Re-running or re-judging any stored run.

## 7. Live calls and spend (Bhargavi starts each one)

| Step | Use | Expected |
|---|---|---|
| Acceptance 5: one Super section proposal, on `guideword-scratch.db` (G8) | development ($0.93 left) | ≤ $0.05 |
| Acceptance 2: one small dev-plant run from the UI, on `guideword-scratch.db` (G8) | development (or video) | spend cap $0.15 + post cap $0.10 = **$0.25 maximum** (Q10). It ends finished or at a cap; either passes. Bhargavi clicks Start (C13). |
| Redo room | — | Steps 2 and 5 take at most $0.30 of the $0.50. A redo of 5 always fits; **a redo of 2 can start only if the first run spent ≤ $0.20** (J5). |
| B1 fixture generation (fake gateway, temporary ledger), legacy export, stored-event check, B3, all screens, acceptance 1, 3, 4, 6, 7 | — | $0 |

The phase cap `"5": 0.50` covers both paid steps. Everything else runs on fixtures and stored runs.

## 8. Acceptance map
- **Demo moment** (the rank-2 startup chain, S3 → S4): acceptance 1 on `guideword-demo.db`, F2's test on the exported item, and F6.
- **Live run and replay:** acceptance 2 (scratch store) and 3 (`guideword.db`, `mode=ro`), F3's tests, and B1's tier on read.
- **Worksheet and export:** acceptance 4 and F4.
- **Sections:** acceptance 5 and F5.
- **Cold click-through and screenshots:** acceptance 6 (scratch store) and 7 (demo store), in F6.
- **"Every number traced":** F1's and F2's DOM tests, B3, and the drawer.
