# Phase 2 — Gateway and agents

**Dates:** Oct 15–17, 2026 **Gate:** G2, Oct 17
**Live-call budget for this phase:** development $1.00 (gateway and agent checks) + test_5 $4.00 (the test #5 runs). Phase cap `"2": 5.00` in `config/caps.yaml`; each use's allowance is enforced separately. Bhargavi starts every live call.
**Source of truth:** `PROJECT.md` (§5 Steps 3–4 and 6.1, §6, §7, §11, §13 test #5, §15 G2). If this spec and `PROJECT.md` disagree, stop and ask.
**Before any code:** `specs/phase-2-plan.md` in plan mode, approved by Bhargavi (`CLAUDE.md` §1).

## Goal

A run goes end to end on a dev case: the plant's confirmed sections are snapshotted, the question list is built, the **Ultra orchestrator** works through it by dispatching the **six specialist agents** on cheaper tiers through the **gateway**, `finish` is refused until every question has a valid answer, and code ranks the findings with the risk matrix. Test #5 then compares this core pipeline (5B) with a single prompt plus checklist (5A) and the kill-test #4 baseline, and G2 asks one question: does 5B put the real cause in the top 3 on cases D and G?

**What the video shows from this phase:** the agent timeline (orchestrator decisions with one-line reasons, dispatches to each specialist and which Nemotron tier answered, tool calls, coverage filling up), and the four-tier comparison (accuracy, speed, cost).

## Who writes what (independence rule, logged Oct 13)

Cowork writes this spec's infrastructure, guards, data flow, schemas and tests, and **does not write or review**:
- any prompt (`prompts/orchestrator/`, `prompts/specialists/<agent>/`, `prompts/severity/`, `prompts/test5a/`);
- the content of each specialist's context beyond the scoping table in `PROJECT.md` §5 (which is already decided);
- anything else that decides what counts as a cause or a hazard.

Claude Code drafts those, each in its own reviewed PR (`CLAUDE.md` §2: prompts change through a separate PR), and **Bhargavi reviews them**. Prompts are tuned only on dev cases D–H (`CLAUDE.md` §5).

## Depends on

| Needs | From | Status |
|---|---|---|
| Plant store, rule cut, suggestions logic, confirm, question builder, coverage | Phase 1 (PRs #15–#22) | merged |
| Records, IDs, enums, `contract-v1` | Phase 0 | frozen |
| Smoke-test decisions (structured output per model, reasoning off, concurrency, Ultra tool calling) | `docs/smoke-test-results.md` | done |
| Estimate rule: text ÷ 2.5, tool schemas ÷ 1.25, +32 per request | decisions 2026-10-13 | done |
| Phase 0/1 leftovers (G1 close-out, video script) | see "Before Phase 2 starts" | **open** |

## Before Phase 2 starts (leftovers found in the Oct 15 review)

These are not Phase 2 work, but Phase 2 must not start on top of them unrecorded:
- **G1 was never closed:** no `g1` tag; `budget/ledger-g1.jsonl` not committed; the G1 checklist in `specs/phase-0.md` unticked (most items are done). Kill-test #1 confirmation (tep-rust, no Operon code) not logged.
- **Held-out writer decision not recorded:** `PROJECT.md` §13, §18 tree and §22, and `docs/decisions.md`, still say a human case writer. The held-out cases now exist (8, sealed). `bench/heldout-seals.txt` is not yet committed.
- **Video script (1.8) not written** (due Oct 15).
- Admin (0.10): facilitator outreach, second $25 grant, City Winner question.

Claude Code does the doc and tag items in a `chore/g1-closeout` PR at the start of Phase 2 (`specs/phase-0.md` ticks; decisions lines; `PROJECT.md` wording). Bhargavi supplies the confirmations and commits the seals and the ledger snapshot.

## In scope

| # | Item |
|---|---|
| 2.1 | Run store and run state machine (all record tables, events, resume) |
| 2.2 | Model gateway (route, cache, budget guard, send, validate, log) and ledger writers |
| 2.3 | `reactivity_lookup` tool |
| 2.4 | Six specialist agents (context builders, answer schema, tool loop, batching) |
| 2.5 | Orchestrator core (`check_coverage`, `dispatch_specialist`, `reactivity_lookup`, `finish` guard; caps) |
| 2.6 | Severity and risk-matrix ranking |
| 2.7 | Live section suggestions (`GatewaySuggester`) and rejected suggestions on screen |
| 2.8 | Run endpoints marked phase 2 in `NOT_BUILT_PHASE` |
| 2.9 | Run CLI and replay fixtures |
| 2.10 | Test #5 harness and run; four-tier comparison |
| 2.11 | G2 |

## Out of scope

Connector and chains, LOPA, shortlist by gap, recommendations (Phase 3); `web_research`, `search_precedent`, `physics_calc`, `run_simulation`, precedent index (Phase 4); frontend screens (Phase 5); hosted deployment and demo mode (Phase 7); endpoints marked phase 3 or 7.

---

## 2.1 Run store and state machine

**Build** in `backend/guideword/runs/`:
- **Tables** (`db.py`), one per `PROJECT.md` §11 storage list not yet present: `runs`, `questions`, `findings`, `agent_steps`, `model_calls`, `tool_calls`, `events`, `response_cache`, `spend_ledger`. Model calls and tool calls are keyed by (run ID, record ID) (record review, Oct 13). `chains`, `lopa_records`, `recommendations`, `evidence`, `overrides` tables are created now (empty) so Phase 3 adds no migration step. Large payloads are JSON columns.
- **Start** (`runs/start.py`): `start_run(plant_record_id, spend_cap_usd, mode)`:
  - 409 if the plant is not `sections_confirmed`;
  - section snapshot = the confirmed sections, frozen into the run;
  - run inputs = plant ID, section snapshot, reference version hashes, routing config, caps, prompt versions, mode (no spend cap); run ID by `ids.run_id` with the earlier attempts (resume, attempt `:n`, `CapReachedError` → 409);
  - setup step: build questions (Phase 1 builder) and store them, status `running`, event `run_started`.
- **State machine** (`runs/machine.py`): statuses per §11 (draft, running, finished, stopped_cap, stopped_budget, failed, cancelled). `advance(run_id) -> RunStatus` performs exactly **one orchestrator step** (with the dispatches that step launches) and persists everything before returning. A crash between steps resumes from the last saved step without paying again (cached calls cost zero).
- **Events** (`runs/events.py`): append-only, `seq` per run starting at 1; identified by (run ID, seq); every type in the `EventType` enum is emitted where it happens (table in 2.5).
- **Cancel**: sets `cancelled`; the next `advance` does nothing.

**Acceptance (tests first)**
- [x] Start on an unconfirmed plant → 409; on a confirmed one → questions stored, counts equal the Phase 1 builder's.
- [x] Identical inputs while running return the same run; after cancel, a new start gives `…:2`; `stopped_cap` + higher cap resumes the same run.
- [x] Killing the process between two `advance` calls and calling `advance` again continues from the saved step; no model call is repeated (fake gateway counts calls).
- [x] Events are contiguous from 1 and every record created in a step has its event.

## 2.2 Model gateway and ledgers

**Build** `backend/guideword/gateway/` (the only code allowed to import `openai` from now; add it to `test_http_allowlist.py` in this PR — a stop-and-ask change, approved here):

Every call goes through `Gateway.call(job, prompt_version, messages, schema=None, tools=None, run_id=None)` in this order (`PROJECT.md` §11):
1. **Route:** job → tier (`routing.yaml`) → model ID from the live model list (`GET /v1/models`, fetched once per process, cached in memory). A tier missing from the list falls back along `fallback_order`; the fallback is logged and an event emitted. A model with a non-empty `shutdown_date` in the past counts as missing.
2. **Cache:** key = `ids.cache_key(model ID, prompt version, exact input)` where exact input = messages + schema + tools, canonical JSON. A hit returns the stored response, records a `ModelCall` with `cache_hit: true`, `cost_usd: 0`.
3. **Budget guard:** estimate with the agreed rule (text ÷ 2.5, tool schemas ÷ 1.25, +32 tokens; output = `max_tokens`); refuse if run spent + estimate > run cap (→ run `stopped_cap`, event `cap_hit`), or if this environment's use or environment allowance would be passed (→ `stopped_budget`). Refusals never send.
4. **Send:** per-model concurrency limits from a new `config/caps.yaml` block `concurrency: {ultra: 3, super: 3, lightning: 5, nano: 3}` (smoke T9/T13); retry 429 and 5xx up to 3 times with backoff (injected clock and sleeper; tests never sleep).
5. **Validate** (JSON rules, §11): `finish_reason == "length"` → `outcome: truncated`, never parsed; strip a leading `<think>` block; read only `content`; log `reasoning_content` separately; validate against the Pydantic schema; unknown IDs fail; on failure retry once with the validation error appended, then `outcome: invalid`.
6. **Log:** a `ModelCall` record (job, model, prompt version, tokens, latency, cost from real usage, outcome, finish reason, raw response, reasoning text, cache hit) and a `SpendEntry`.

**Per-tier request settings** (from `docs/smoke-test-results.md`, in a new `config/models.yaml` field per tier so no literal lives in code):
- Ultra: `json_schema` strict, reasoning on (`reasoning_content`), native tool calling.
- Super: `json_schema` strict, reasoning on.
- Lightning and Nano: `json_schema` strict with `chat_template_kwargs.enable_thinking: false` (reasoning off is required on Lightning for structured output).
- `max_tokens` per job in `config/caps.yaml` (`max_tokens: {orchestrator: …, specialist_bulk: …}`), set by the plan from the smoke data.

**Ledgers:** `LaptopLedger` appends to `budget/ledger.jsonl` (environment `laptop`); `HostedLedger` writes the `spend_ledger` table (environment `hosted`); chosen by `settings.guideword_env`. Each enforces only its own environment's allowances (decision Oct 11). `scripts/budget_status.py` reads the same ledger class.

**Fake gateway** (`gateway/fake.py`): same interface, scripted responses keyed by job and input; used by every test. No test can construct the real client (the network block also prevents it).

**Live checks (Bhargavi runs, development use, ≤ $0.30):** `scripts/gateway_check.py` sends one call per tier through the real gateway and one Lightning call that combines **tool calling with `json_schema` and reasoning off** (the specialist path; smoke tested tool calling and structured output separately, never together). If that combination fails, the specialist falls back to two calls (tool call without schema, then the answer with schema) and the result goes in `docs/decisions.md` and `docs/feedback-log.md`.

**Acceptance (tests first, fake client)**
- [x] Route: missing tier falls back and logs; past `shutdown_date` counts as missing.
- [x] Cache: second identical call costs 0, `cache_hit: true`; changing the prompt version or one input character misses.
- [x] Budget guard: over run cap → refused, run `stopped_cap`; over a use or environment allowance → refused, `stopped_budget`; nothing sent in either case.
- [x] Retries: 429 then success → one `ModelCall` with `attempts: 2`; three 5xx → `outcome: error`.
- [x] Validation: `length` → `truncated`, not parsed; `<think>` stripped; invalid JSON → one retry with the error, then `invalid`; unknown ID → invalid.
- [x] Ledger line written after every non-cached call, with job, use and phase; laptop and hosted ledgers never read each other.
- [x] Allow-list test updated: `openai` allowed in `gateway/`; still forbidden everywhere else except `scripts/live_call.py`.

## 2.3 `reactivity_lookup`

**Build** `backend/guideword/tools/reactivity.py`: `reactivity_lookup(chemical_a, chemical_b)` on the run's plant:
- for every pair of the two chemicals' `epa_groups` → `ReferenceSet.reactivity`; result = every listed code with its chart row, plus `do_not_mix` hits, plus `not_listed` pairs (never "compatible");
- a chemical with no EPA groups → `no_groups` for that chemical (and its CAMEO groups shown, for the specialist's judgment);
- returns the codes in words (H heat, F fire, G gas, GT toxic gas, GF flammable gas, E explosion, P violent polymerisation, S solubilisation of toxic substance, U unknown) and the table source.
Every call is a `ToolCall` record and a `tool_call` event; arguments validated (both IDs must be plant chemicals).

**Acceptance (tests first)**
- [x] §9 example SIH × KOH → listed, codes GF and GT from 105 × 106, with the row source.
- [x] A pair with no chart row → `not_listed`, never "compatible"; group 107 → `do_not_mix`.
- [x] Unknown chemical ID → refused with a reason (tool error goes back to the agent once).

## 2.4 Specialist agents

**Build** `backend/guideword/specialists/`:
- **Routing of questions to agents (code, fixed):** matrix and relief → process; chemical pair and environment → chemistry; no-flow → piping; procedure step → procedures; planned work → maintenance; dust → dust; added-by-AI and engineer questions → the agent of their section's kind (equipment/line → process; no-flow line → piping; procedure → procedures; planned work → maintenance).
- **Context builders** (`context.py`), one per agent, exactly per the `PROJECT.md` §5 table ("gets only"), built by code from the plant and the run's sections, including the `notes` of the objects in scope (verbatim, as data). Each context lists the plant IDs the agent may cite.
- **Answer schema** (`schema.py`): per question, either `not_credible` with a reason, or one or more findings: `cause_id` (a `causes.csv` ID valid for that section type, or `outside_library` with `cause_text`), `failing_component_type`, `failing_component_ids` (non-empty, IDs from the context), `consequence`, `safeguard_ids` (from the context), `adequacy`, `confidence`, `reason`. Every question ID sent comes back exactly once; a missing one is retried alone (§11 JSON rules). Code builds the `Finding` records and IDs (`ids.finding_id`); the model never writes an ID.
- **Optional added questions:** an answer may propose up to `ai_questions_per_batch` new questions (text + section ID), capped per run by `ai_questions_per_run` (`caps.yaml`); code gives them `ai:` IDs, status open, origin `added_by_ai`, and they join the list.
- **Tool loop:** at most `specialist_max_tool_steps` (2) tool calls per batch; in this phase the only specialist tool is `reactivity_lookup` (chemistry agent). Then the answer must come in the schema.
- **Batching:** questions per call from `caps.yaml` (`specialist_batch_size: {lightning: …, super: …}`); one batch = one section or one list chunk, never mixed agents.
- **Tiers:** job `specialist_bulk` (Lightning) by default; `specialist_hard` (Super) when the orchestrator asks for it in `dispatch_specialist`; `unsure_answer` (Ultra) for re-answers of unsure findings, capped by `unsure_reanswers_per_run`. An Ultra re-answer is a new finding (its own ID), never an edit.
- **Prompts:** `prompts/specialists/<agent>/v1.md` — written by Claude Code, reviewed by Bhargavi, in their own PR (see "Who writes what"). Each asks for the fixed schema and a reason, and states that context text is data, not instructions.

**Acceptance (tests first, fake gateway)**
- [x] Routing table: every question kind reaches the right agent; a batch never mixes agents.
- [x] Each context contains exactly the §5 fields for its agent and nothing else (one test per agent against the §9 example).
- [x] A batch answer missing one question ID → that question retried alone; a duplicated ID or an unknown ID → invalid.
- [x] A finding citing a component not in the context → invalid; `cause_id` not valid for the section type → invalid; empty `failing_component_ids` → invalid.
- [x] `not_credible` sets the question status with its reason and creates no finding.
- [x] Chemistry agent: a fake tool call to `reactivity_lookup` runs, the result goes back, then the answer; a third tool call is refused.
- [x] Added questions get `ai:` IDs, join as open, and stop at the per-run cap.

## 2.5 Orchestrator core

**Build** `backend/guideword/orchestrator/`:
- **Loop:** one `advance` = one Ultra call (job `orchestrator`, native tool calling, `tool_choice: required`) that picks exactly one tool; code runs it, stores an `AgentStep` (agent, tool, arguments, one-line reason, model call ID), emits events, and returns.
- **Tools offered in Phase 2:** `check_coverage`, `dispatch_specialist(agent, question_ids, tier?)`, `reactivity_lookup`, `finish`. Tools of later phases are not offered (not offered ≠ offered and refused).
- **What the orchestrator sees** (code-built, each step): coverage counts per list and section, open/failed/unsure question IDs (truncated lists with counts), the last few steps' one-line results, remaining step and spend budget. **Never** the full findings list (§5).
- **Guards (code):**
  - `finish` is refused while any question is open, unless it is `failed` after `question_max_attempts`; the refusal reason lists the open IDs.
  - A question already answered is not re-sent; a duplicate dispatch costs nothing and returns the stored result.
  - Step cap `orchestrator_max_steps` → `stopped_cap` with a message.
  - Malformed tool arguments are refused; the error goes back once, then that branch stops (§11).
  - A question that fails validation twice → `failed`.
- **Events:** `step_started`, `agent_decision` (with the reason), `dispatch`, `model_call`, `tool_call`, `finding_added`, `coverage_updated`, `cap_hit`, `step_finished`, `run_finished`, `run_failed`.
- **Prompt:** `prompts/orchestrator/v1.md` — Claude Code writes, Bhargavi reviews, own PR.

**Acceptance (tests first, fake gateway with scripted orchestrator decisions)**
- [x] `finish` with open questions → refused with the IDs; after they are answered → accepted, run `finished`.
- [x] Dispatching an answered question costs no call.
- [x] Step cap reached → `stopped_cap`, event `cap_hit`.
- [x] The orchestrator's input never contains a finding's consequence text (test on the built context).
- [x] A full fake run on the §9 example reaches `finished` with every question answered or not credible.

## 2.6 Severity and risk-matrix ranking

**Build** `backend/guideword/ranking/`:
- **Severity** (after `finish`): every finding without a severity is sent to Ultra (job `severity_reason`) in batches; the answer is a severity class (S1–S5 enum) and a reason per finding ID. Code stores it on the finding. Prompt `prompts/severity/v1.md` (Claude Code writes, Bhargavi reviews).
- **Likelihood (code only):** the cause's initiating event (`causes.csv` → `initiating_events.csv`); a `per_year` frequency maps to the `likelihood_classes.csv` band that holds it. `per_metre_year` × `lines.length_m` and `per_lift` × `planned_work.lifts_per_year` when the fact exists; otherwise the finding is **unrated** with the missing fact ID named. Outside-library causes: the highest frequency among library causes with the same failing-component type, else 0.1 / year, flagged "frequency assumed" (§5 Step 6). `per_opportunity` events are unrated in this phase (no demand rate in the plant file) — flagged.
- **Rating:** `risk_matrix.csv` (severity × likelihood).
- **Order (deterministic):** rated findings by rating (very_high → low), then severity (S5 → S1), then initiating frequency (higher first), then finding ID. Unrated findings follow, in the same order without likelihood, each showing what is missing. Not-credible questions have no findings and do not appear.
- **Result:** a ranked list per run stored for the test #5 scorer; the shortlist endpoint stays Phase 3.

**Acceptance (tests first)**
- [x] Hand-worked example: a C01 cause (IE-BPCS, 0.1 / year → L4) with S4 → rating per `risk_matrix.csv`; ties broken exactly as above.
- [x] A C20 cause on a line without `length_m` → unrated, names `<line>.length_m`.
- [x] An outside-library cause gets the highest library frequency of its component type, flagged.
- [x] Ranking is identical across two runs replayed from cache.

## 2.7 Live section suggestions

- `GatewaySuggester` (job `section_suggestion`, Super, prompt `section_suggestion/v1`, cap `section_suggest_cap_usd`) replaces `NullSuggester` in the propose endpoint when not in mock mode; the call is logged to the ledger with use `development`.
- **Rejected suggestions on screen:** add `rejected: list[RejectedSuggestion]` (suggestion + reason) to `SectionProposal` through a `contract/section-rejections` branch and PR (additive; tag `contract-v1.2`). Recommended because the engineer should see what Super proposed and why code refused it; if Bhargavi declines, keep logging only.

**Acceptance:** fake gateway returns valid and invalid suggestions → valid ones returned, rejected ones returned with reasons (or logged, per the decision); the cap refuses a call that would exceed it.

## 2.8 Run endpoints (phase 2 in `NOT_BUILT_PHASE`)

`GET /runs`, `POST /runs`, `POST /runs/{id}/cancel`, `GET /runs/{id}`, `GET /runs/{id}/events?after=`, `GET /runs/{id}/sections`, `GET /runs/{id}/questions`, `POST /runs/{id}/questions`, `GET /runs/{id}/coverage`, `GET /runs/{id}/records/{record_id}`, `GET /budget`, `POST /internal/runs/{id}/advance` — exactly the `contract-v1` models, every run response with `label.kind = "live"`. Each route leaves `NOT_BUILT_PHASE` in the PR that builds it.
- `POST /internal/runs/{id}/advance` (secret header) calls `advance` once and, if the run is still `running`, schedules the next call (in-process loop on the laptop; the hosted chaining is Phase 7).
- `POST /runs/{id}/questions` adds an `eng:` question; a running run treats it as open; a finished run keeps it open until an `answer` override (Phase 3 builds overrides).

**Acceptance:** contract tests for each route against a fake-gateway run; `label.kind == "live"`; advance without the secret → 401.

## 2.9 Run CLI and replay

- `scripts/run_case.py <plant file> [--mode full|sample] [--use development|test_5] [--cap 1.00]`: upload, rule-cut confirm (no suggestions), start, `advance` until terminal, print coverage and the top 10 ranked findings. Human-readable output (print allowed).
- `scripts/export_replay.py <run id>`: writes every model response the run used into `bench/replay/<case>/` (no keys). The CI replay test runs a dev case from those fixtures through the fake gateway and asserts an identical ranked list (§18 "Full pipeline").

## 2.10 Test #5 and the four-tier comparison

**Build** `bench/test5/` and `backend/guideword/bench/`:
- **#4:** the kill-test #4 results (Bhargavi copies `results/run-20261009-215148.jsonl` and its report into `bench/test5/kill4/`) — no new calls.
- **5A:** one Ultra call per dev case: the package text plus a step-by-step HAZOP checklist, asked for a ranked list of top hazards. Prompt `prompts/test5a/v1.md` (Claude Code writes, Bhargavi reviews).
- **5B (core):** `run_case.py` on each dev plant file (D–H), use `test_5`.
- **Scoring:** `scripts/score_test5.py` applies the kill-test match rule (every phrase group of the case's key matched in one ranked line, text normalised) and reports the rank of the first match (top 3 / top 10 / missed) per configuration and case. The script reads `cases/dev/keys/answer_keys.json` at run time; Claude Code writes the script against the key *format* only and never opens the file. Bhargavi hand-scores every top 10 and the result table records both scores.
- **Four-tier comparison:** a fixed sample of 50 questions from D–H (chosen by code: the 50 lowest `h(question ID)` values across the five cases' lists, so the sample is reproducible and unbiased), each answered by the process/chemistry/etc. specialist on all four tiers (Ultra, Super, Lightning, Nano) with the same prompt version. Report per tier: valid-answer rate, Bhargavi's hand score (good / partial / wrong), median latency, cost. Use `test_5`.
- **Results:** `bench/test5/results.md` generated from run records by script, never typed: per case and configuration the rank of the real cause, both scores, cost and time; the four-tier table.

**Spend estimate (to confirm by the plan from the smoke data):** 5B ≈ $0.20–0.50 per case (≈ 270–440 questions on Lightning, ≤ 60 Ultra orchestrator steps, Ultra severity batches) → ≤ $2.50; 5A ≈ $0.10; four-tier ≈ $0.30. Total ≤ $3.00 of the $4 test_5 allowance.

## 2.11 G2 (Oct 17)

- [ ] 5B puts the real cause in the **top 3 on cases D and G**, hand-scored by Bhargavi.
- [ ] Results table generated; spend recorded; `docs/decisions.md` records the routing chosen for Phase 3 (cheapest tier that passed per job, from the four-tier comparison).
- If G2 fails: stop and rethink before Phase 3 (§15); if 5A matches 5B, record it and use 5A's finding honestly in the pitch.

---

## PR order (the plan may refine it)

| # | Branch | Items |
|---|---|---|
| 0 | `chore/g1-closeout` | leftovers above |
| 1 | `phase-2/run-store` | 2.1 |
| 2 | `phase-2/gateway` | 2.2 (+ allow-list change) |
| 3 | `phase-2/reactivity-lookup` | 2.3 |
| 4 | `phase-2/specialist-prompts` | prompts only (Bhargavi reviews) |
| 5 | `phase-2/specialists` | 2.4 |
| 6 | `phase-2/orchestrator-prompt` | prompt only |
| 7 | `phase-2/orchestrator` | 2.5 |
| 8 | `phase-2/ranking` (+ `severity` prompt PR) | 2.6 |
| 9 | `contract/section-rejections` + `phase-2/live-suggestions` | 2.7 |
| 10 | `phase-2/run-endpoints` | 2.8 |
| 11 | `phase-2/run-cli-replay` | 2.9 |
| 12 | `phase-2/test5` (+ `test5a` prompt PR) | 2.10 |

**If time runs short (G2 is in two days):** G2 needs only 2.1–2.6, 2.9 and the 5B part of 2.10, run from the CLI. Priority: 0 → 1 → 2 → 3 → 4/5 → 6/7 → 8 → 11 → 12 (5B and scoring first). The run endpoints (2.8), live suggestions (2.7), 5A and the four-tier comparison can follow on Oct 18 without blocking G2; record any slip in `docs/decisions.md`.

## Done when

- [ ] Every acceptance box ticked; CI green on `main`.
- [ ] A 5B run on every dev case reaches `finished` (or a recorded cap stop) with a ranked list.
- [x] G2 decided and recorded.
- [ ] Phase 2 spend within its cap, by use; ledger snapshot `budget/ledger-g2.jsonl` committed; `g2` tag.
- [ ] Every decision has a dated line in `docs/decisions.md`; Token Factory friction in `docs/feedback-log.md`.
