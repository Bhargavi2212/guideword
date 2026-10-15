# Phase 2 plan — Gateway and agents

Status: approved 2026-10-15 (Bhargavi). Decided: G1, G3, G4, G6, G7, G8 and R1–R39. Open: G2 (the kill-test #1 confirmation) and G5 (the 0.10 statuses), which PR 0 needs before it merges. The video script is deferred (G4).

Covers every item in `specs/phase-2.md`, starting with the `chore/g1-closeout` items it lists under "Before Phase 2 starts". On approval this plan and `specs/phase-2.md` (untracked today) are committed as the first commits on `chore/g1-closeout`.

## Context

Phase 2 makes a run go end to end on a dev case:
- the confirmed sections are snapshotted and the question list is built;
- the Ultra orchestrator dispatches six specialist agents through the gateway;
- `finish` is refused while questions are open;
- severity comes from Ultra, likelihood and rating from code;
- test #5 (5B against 5A and kill test #4) decides G2: is the real cause in the top 3 on cases D and G?

**State at planning (Oct 15):**
- `main` is at `79ad057`. All 925 backend tests pass; ruff, mypy and the frontend checks are clean.
- Phase 1 is merged (PRs #15–#22), and the D–H counts match `expected_counts.json`.
- `contract-v1` is tagged; there is no `g1` tag.
- `budget/` holds only `.gitkeep`. The ledger's last line is the Oct 13 smoke test.
- `development` has $3.50 left of $5.00: the $1.37 opening balance (unconfirmed) plus the $0.1277 smoke test. `test_5` is untouched at $4.00.

**What the dev cases need:**

| Case | Sections | Questions | Lists |
|---|---|---|---|
| D | 25 | 362 | matrix 286, pair 36, env 27, nf 5, relief 8 |
| E | 27 | 443 | matrix 315, pair 55, env 33, proc 40 |
| F | 24 | 282 | matrix 225, pair 28, env 24, work 5 |
| G | 17 | 283 | matrix 188, pair 45, env 30, proc 20 |
| H | 25 | 270 | matrix 223, pair 15, env 18, dust 14 |

G2 is judged on D and G, so the process, chemistry, piping and procedures agents must work by G2. Maintenance and dust are exercised only on F and H.

**Reference facts the plan relies on (checked):**
- No cause in `causes.csv` applies to a chemical pair or environment question; their `applies_to` values are section types. Only C24 applies to `planned_work`.
- Likelihood bands share their edges (L4 = 0.01–0.1, L5 = 0.1 upward). The spec's own example puts IE-BPCS at 0.1/year in **L4**, so a band includes its upper edge: `min < f <= max`, and the top band is `f > min`.
- `ModelCall.run_id` is required, so a call made outside a run cannot be stored as a `ModelCall` without a contract change (R9).
- Retries in `scripts/live_call.py` are `max_retries=0`. Its `Ledger` class and estimate rule live in `scripts/`, which the package cannot import (R16).

---

## Pull requests in order

| # | Branch | Items | Depends on | Day |
|---|---|---|---|---|
| 0 | `chore/g1-closeout` | plan and spec commits; the G1 close-out (G1–G8) | — | Oct 15 |
| 1 | `phase-2/run-store` | 2.1 | PR 0 | Oct 15 |
| 2 | `phase-2/gateway` | 2.2, config additions (R18, R19), allow-list change, `scripts/gateway_check.py` | PR 0 | Oct 15 |
| 3 | `phase-2/reactivity-lookup` | 2.3 | PR 1 | Oct 15 |
| 4 | `phase-2/specialist-prompts` | six `prompts/specialists/<agent>/v1.md`, for your review | PR 0 | Oct 15 |
| 5 | `phase-2/specialists` | 2.4 | PR 1, 2, 3, 4 | Oct 16 |
| 6 | `phase-2/orchestrator-prompt` | `prompts/orchestrator/v1.md`, for your review | PR 0 | Oct 16 |
| 7 | `phase-2/orchestrator` | 2.5 | PR 5, 6 | Oct 16 |
| 8a | `phase-2/severity-prompt` | `prompts/severity/v1.md`, for your review | PR 0 | Oct 16 |
| 8 | `phase-2/ranking` | 2.6 | PR 7, 8a | Oct 16 |
| 8b | `contract/run-cap-spend` | the additive `Run.cap_spent_usd` and `ModelCall.cap_cost_usd` fields; tag `contract-v1.1` (R45) | PR 0 | Oct 16 |
| 8c | `phase-2/cap-spend` | R45: stored cache costs, the cap figure in the guard, view and reserve; the 2.6 replay item | PR 8, 8b | Oct 16 |
| 11 | `phase-2/run-cli-replay` | 2.9 | PR 8 | Oct 16 |
| 12a | `phase-2/test5a-prompt` | `prompts/test5a/v1.md`, for your review | PR 0 | Oct 16 |
| 12 | `phase-2/test5` | 2.10 | PR 11, 12a | Oct 17 |
| 9a | `contract/section-rejections` | the additive `SectionProposal.rejected` field; tag `contract-v1.2` (R23) | PR 0 | Oct 17–18 |
| 9 | `phase-2/live-suggestions` | 2.7 | PR 2, 9a | Oct 17–18 |
| 10 | `phase-2/run-endpoints` | 2.8 | PR 8 | Oct 17–18 |
| 13 | `phase-2/g2-results` | 2.11 records: the results table, decisions, ticks (after your hand scores) | PR 12 and your scoring | Oct 17 |

**Order and timing:**
- **Merge order:** the order is the spec's "if time runs short" priority, so PR 11 and PR 12 come ahead of PRs 9 and 10. PRs 9, 10, 5A and the four-tier comparison may slip to Oct 18 without blocking G2; any slip gets a decisions line.
- **Prompt PRs:** 4, 6, 8a and 12a only depend on PR 0, so I can open them early for you to review while the code PRs are built.
- **Parallel work:** PR 1 and PR 2 are independent. PR 3 needs only PR 1's `ToolCall` and event tables.

**Every PR:**
- run the suite first, and write the tests first;
- small Conventional Commits with the Co-Authored-By line;
- the `CLAUDE.md` §8 commands before each commit;
- tick the PR's boxes in `specs/phase-2.md`, and add a dated `docs/decisions.md` line for every decision;
- add any Token Factory or Nemotron friction to `docs/feedback-log.md`;
- a description covering what, why, items, test evidence and anything open;
- **never** a live call, and never a read of `cases/dev/keys/`, `bench/heldout/` or `guideword-heldout`.

---

## PR 0 — `chore/g1-closeout`

Docs, ticks and records only, no code. Each item uses an answer from you (G1–G8).

1. **Commits:** this plan and `specs/phase-2.md`.
2. **`specs/phase-0.md` ticks, for items verifiable on `main` today:**
   - 0.8 "Tagged `contract-v1`" (on `b44f9b2`);
   - the gate G1 checklist: smoke test complete, decisions written, IDs confirmed, opening balance recorded (value per G8), spend ≤ $0.65;
   - T12 confirmed;
   - schema frozen and contract tagged;
   - reference loaders and LOPA source;
   - dev cases validate with every assumption ticked.

   The 0.0 first box is annotated per G1 (#2–#22 were merge commits, each through a PR; squash from now on). The gate's "case writer has started and owns the held-out repo" and the 0.10 case-writer and brief boxes are annotated per G3 (a scheduled Claude session wrote the cases; Bhargavi owns the folder). "CI green", 0.9 and the other 0.10 boxes wait for G7, G2 and G5.
3. **`specs/phase-1.md` "Done when" ticks:**
   - ticked now: counts match, $0.00 spent (the last ledger line is from Oct 13), decisions logged;
   - "CI green" is ticked (G7: Actions green on `main`); the video box stays open, deferred (G4).
4. **`docs/decisions.md` lines** (dated 2026-10-15):
   - kill test #1 confirmation (G2);
   - the held-out cases, exactly as decided in G3, superseding the Oct 11 "case writer creates and owns `guideword-heldout`" line;
   - the independence rule from `specs/phase-2.md` "Who writes what" (the spec says it was logged Oct 13, but no such line exists);
   - the video-script slip (G4): deferred, with Cowork drafting and Bhargavi editing; the date is yours to set;
   - the merge-style decision (G1);
   - the 0.10 statuses (G5);
   - one line per decided item: G8 (the trial-credit reconciliation, exactly as decided), R1–R39 (R5 logged as required for a valid finding, not tuning; R26c logged with the reason IDs are never matched; R12, R18, R37 and R38 with Bhargavi's changes). Decisions that only take effect in a later PR (for example R23, the contract change) are logged in PR 0 and referenced again by that PR.
5. **Held-out wording (G3)**, in exactly the decided facts:
   - **`PROJECT.md`:** §13 ("Written by a person other than the builder" becomes the separate scheduled Claude session, instructed not to read this repo); the §18 tree line for `guideword-heldout/` (Bhargavi's folder outside the repo, pushed to a private GitHub repo unopened until Phase 6, sealed by `SEALS.txt`, copied as `bench/heldout-seals.txt`); §22 (the "choose the case writer" task marked done Oct 13).
   - **`CLAUDE.md` §5:** "Never open, clone, list or read `guideword-heldout` (the folder `D:\Hackathon\guideword\guideword-heldout` or its GitHub repo), anything under `bench/heldout/`, or `bench/heldout-seals.txt`." The rest of §5 is unchanged.
   - **Annotations:** the 0.10 case-writer boxes in `specs/phase-0.md`, and the first line of `docs/case-template.md` ("your own private repository" becomes the `guideword-heldout` folder).
6. **Rule wording that Phase 2 code relies on**, landing before any code:
   - `CLAUDE.md` §4 (R1) and `PROJECT.md` §7 (R2), exactly as decided;
   - the `PROJECT.md` §5 chemistry row (R5): "Chemical list, properties, reactivity groups, and where each chemical is present";
   - `PROJECT.md` §5 and §7 "2 tool steps per question" become "per batch" (R33).
7. **Your steps:**
   - commit `bench/heldout-seals.txt` and `budget/ledger-g1.jsonl`; I never open the seals file, which is not under `bench/heldout/`;
   - tag `g1` on `main` after this PR merges (I don't push tags; G6).

**Tests:** none (docs only). The suite runs before commit as usual.

---

## 2.1 Run store and state machine — PR 1

**Files**
- `runs/db.py` gains tables:
  - `runs`, `questions`, `findings`, `agent_steps`;
  - `model_calls` and `tool_calls`, keyed by (`run_id`, `id`);
  - `events`, keyed by (`run_id`, `seq`);
  - `response_cache` (R15) and `spend_ledger`;
  - `chains`, `lopa_records`, `recommendations`, `evidence` and `overrides`, empty until Phase 3.

  Large payloads are JSON columns and links are foreign keys. Tables are made with `create_all`.
- `runs/store.py`: `RunRepository` (runs, questions, findings, steps, calls, events; every write in one transaction per step).
- `runs/events.py`: `append(run_id, type, payload)` assigns the next `seq` inside the step's transaction, so a crash never leaves a gap (contiguous from 1). The time comes from the injected clock.
- **`runs/start.py`, `start_run(plant_record_id, spend_cap_usd, mode, *, config, ref, clock)`:**
  - **refusals:** an unconfirmed plant raises `SectionsNotConfirmed`, which the API turns into a 409;
  - **snapshot:** the stored confirmed sections, frozen into the run. `Run.section_snapshot` holds only their IDs, and the plant's sections can change after a re-propose, so the full `Section` records are also stored with the run (a JSON column on `runs`). `GET /runs/{id}/sections` and the specialists read that copy, never the plant's current set;
  - **inputs:**
    - plant record ID, `section_snapshot` (the IDs), `ref.versions` and `routing.jobs`;
    - the run caps (R18 says which keys) and the prompt versions (R19), plus the mode;
  - **ID:** `ids.run_id` with the earlier attempts from `RunRepository.attempts(base)`. `CapReachedError` becomes a 409; resuming a `stopped_cap` run sets its new cap;
  - **setup:** build the questions with the Phase 1 builder on the snapshot, store them, set the status `draft → running` and `step = "analysis"`, and emit `run_started`.
- **`runs/machine.py`, `advance(run_id, *, stepper) -> RunStatus`:**
  - **resume:** loads the run, does nothing in a terminal status or `cancelled`, and otherwise runs one step of the current phase through an injected `Stepper` (the orchestrator in PR 7, severity in PR 8);
  - **persistence:** saves every record and event before returning;
  - **steps:** `analysis` → `severity` → `ranked` (R24);
  - **cancel:** `cancel(run_id)` sets `cancelled`.

  PR 1 tests the machine with a scripted fake stepper. `advance` makes no model calls itself.

**Tests first** (`backend/tests/runs/test_start.py`, `test_machine.py`, `test_events.py`)
- `test_start_on_unconfirmed_plant_is_refused`; `test_start_stores_questions_equal_to_the_builder`, on the §9 example: 98 questions and 9 sections.
- `test_identical_inputs_while_running_return_the_same_run`; `test_after_cancel_a_new_start_is_attempt_2`; `test_stopped_cap_with_a_higher_cap_resumes_the_same_run`; `test_stopped_cap_without_a_higher_cap_is_refused`.
- `test_run_id_matches_its_stored_inputs` (`Run` validates it).
- `test_advance_after_a_crash_continues_from_the_saved_step`: a stepper that raises after writing a record saves nothing; a fresh repository on the same DB file redoes the step. (Changed during the build, Oct 15: the "no model call is repeated" half needs the response cache, which lives with the gateway, so it moved to PR 2 as `test_crash_after_a_call_repeats_no_call`.)
- `test_events_are_contiguous_from_1_and_every_record_has_its_event`.
- `test_phase_2_event_types` (R32: the emitted set equals `EventType` minus `chain_added`, `lopa_done` and `evidence_added`; checked again after PR 8).
- `test_cancelled_run_does_nothing_on_advance`.
- `test_run_keeps_its_section_records_after_a_re_propose` (the plant's set changes; the run's does not).

## 2.2 Gateway and ledgers — PR 2

**Config additions** (values as decided in R18, with `specialist_bulk` at 6144; shape per R19; `config.py` models extended and validated):
- `caps.yaml`:
  - `phase_caps_usd."2": 5.00`;
  - `run.severity_reserve_usd: 0.15` (R38; in `Run.caps`);
  - `concurrency: {ultra: 3, super: 3, lightning: 5, nano: 3}`;
  - `gateway: {max_attempts: 3, backoff_seconds: [1, 2]}`;
  - `max_tokens: {<job>: n}`;
  - `specialist_batch_size: {<tier>: n}`;
  - `ai_questions_per_batch`, `ai_questions_per_run`, `unsure_reanswers_per_run`;
  - `orchestrator_view: {id_list_max, recent_steps, dispatch_max_question_ids}`;
  - `severity_batch_size`;
  - `ranking.outside_library_default_frequency_per_year` (R12).
- `models.yaml`: each tier gains `request: {structured_output: json_schema, reasoning: true|false, tool_calling: native, tools_with_schema: true}` (`tools_with_schema` per R34). These come from the smoke decisions: Ultra and Super reason, Lightning and Nano don't.
- `routing.yaml`: gains `prompts: {<prompt name>: <version>}` (R19).

**Files** (`backend/guideword/gateway/`)
- `ledgers.py`: `LaptopLedger` (moved from `scripts/live_call.py`, which then imports it) and `HostedLedger` (the `spend_ledger` table), plus `ledger_for(settings, …)`. `budget_status.py` reads the same class.
- `estimate.py`: the agreed rule (text ÷ 2.5, tools ÷ 1.25, +32), moved from `live_call.py` and re-exported there, so `test_estimate_upper_bound.py` is unchanged.
- `catalog.py`:
  - the live model list (`client.models.list()`), fetched once per gateway and cached in memory;
  - `resolve(tier)`, which follows `fallback_order` when a tier is missing or has a past `shutdown_date` (injected clock), and logs the fallback with an event when there is a run.
- `cache.py`: the `response_cache` table, keyed by `ids.cache_key(model_id, prompt_version, exact_input)`. The exact input is messages, schema, tools, tool choice and request settings (R14).
- **`client.py`, `Gateway`:**
  - **built with:** settings, config, ledger, clock, sleeper, an OpenAI client factory, `use` and `phase`;
  - **`call(...)`:** takes `job`, `prompt_version`, `messages`, `schema`, `tools`, `tool_choice`, `tier` (override), `run` and `validator` (R16), and returns a `GatewayResult` (parsed value or tool calls, the `ModelCall` record, outcome);
  - **in order:** route → cache → budget guard (run cap, phase cap, use and environment allowances, with holds for calls in flight, as `live_call` does) → send (per-model semaphore; retries 429 and 5xx with backoff through the injected sleeper, `max_attempts` in total, R13) → validate → log;
  - **validation:**
    - a `length` finish is `truncated` and never parsed;
    - a leading `<think>` is stripped, the answer is read only from `content`, and `reasoning_content` is kept separately;
    - the Pydantic schema plus the caller's ID validator is applied;
    - on failure, one retry with the error appended (a new input, so a new record), then `invalid`;
  - **logging:**
    - a `ModelCall` when there is a run (R9);
    - a ledger line after every non-cached call, carrying job, use and phase;
    - a `model_call` event.
- `fake.py`, `FakeGateway`: the same interface, with responses scripted by (job, input matcher), counting calls. No test builds the real client; the network block also stops it.
- `scripts/gateway_check.py`: one call per tier, plus the Lightning tool-calling + `json_schema` + reasoning-off check, all through the real gateway with `--use development --phase 2`. It writes `docs/gateway-check.md` from the results (print allowed). After you run it, I add the decisions and feedback-log lines from that file, and set `tools_with_schema` (R34) in a follow-up commit.
- **Allow-list (`backend/tests/test_http_allowlist.py`):** `openai` is also allowed in `backend/guideword/gateway/**`. No other change: `httpx` and `tavily` stay as they are (stop-and-ask, approved by the spec).

**Tests first** (`backend/tests/gateway/`)
- **Route:** `test_missing_tier_falls_back_and_logs`; `test_past_shutdown_date_counts_as_missing`; `test_model_list_fetched_once`.
- **Cache:** `test_second_identical_call_costs_zero_and_is_a_hit`; `test_prompt_version_or_one_character_or_max_tokens_change_misses`; `test_crash_after_a_call_repeats_no_call` (moved from PR 1: a step that calls the fake client and then raises; the next `advance` gets a cache hit, and the fake counts one call). The cache row is committed on its own, outside the step's transaction, so a failed step never loses a paid response.
- **Budget:**
  - `test_over_run_cap_refused_run_stopped_cap_nothing_sent`;
  - `test_over_use_or_environment_allowance_refused_stopped_budget`;
  - `test_over_phase_cap_refused` (R17);
  - `test_holds_count_calls_in_flight` (parallel fake calls);
  - `test_use_of_the_other_environment_is_refused` (a `judging` call on the laptop ledger never sends).
- **Retries:** `test_429_then_success_is_one_model_call_with_attempts_2`; `test_three_5xx_is_outcome_error`; `test_no_real_sleep` (an injected sleeper records the waits).
- **Validation:**
  - `test_length_is_truncated_and_not_parsed`;
  - `test_think_block_stripped_reasoning_logged`;
  - `test_invalid_json_retried_once_with_the_error_then_invalid`;
  - `test_unknown_id_is_invalid`.
- **Ledgers:** `test_ledger_line_after_every_non_cached_call_with_job_use_phase` (job in `purpose`, R31); `test_laptop_and_hosted_ledgers_never_read_each_other`; `test_live_call_and_budget_status_use_the_moved_ledger`.
- **Allow-list:** the updated test still fails for a temporary file importing `openai` outside `gateway/` and `live_call.py`.
- **Config:** loader tests for each new block: rejecting a negative, an unknown tier or job, a missing phase-2 cap, and so on.

**Dependencies:** none new. `openai` and `sqlalchemy` are already pinned; threads and semaphores come from the standard library.

## 2.3 `reactivity_lookup` — PR 3

**Files:** `tools/reactivity.py`:
- **Call:** `reactivity_lookup(plant, chemical_a, chemical_b)`, which checks that both IDs are plant chemicals.
- **What it returns:** every pair of their `epa_groups` is looked up through `ReferenceSet.reactivity`, giving:
  - listed codes, in words (H heat, F fire, G gas, GT toxic gas, GF flammable gas, E explosion, P violent polymerisation, S solubilisation of toxic substance, U unknown), with the chart row source;
  - `do_not_mix` hits and `not_listed` pairs (never "compatible");
  - `no_groups` for a chemical with no EPA groups, with its CAMEO groups shown.
- **Recording:** `tools/record.py` records a `ToolCall` (ID `ids.tool_call_id(step, tool, args)`) and a `tool_call` event. A refused call (unknown ID) stores `refused_reason` and returns the error to the agent once.

**Tests first:**
- `test_sih_koh_is_listed_gf_gt_from_105_x_106_with_source`;
- `test_pair_without_a_row_is_not_listed`;
- `test_group_107_is_do_not_mix`;
- `test_chemical_without_groups_is_no_groups_with_cameo`;
- `test_unknown_chemical_is_refused_with_a_reason`;
- `test_every_call_is_a_tool_call_record_and_event`.

## 2.4 Specialists — PR 4 (prompts) and PR 5 (code)

**PR 4:** six prompts (`prompts/specialists/{process,chemistry,piping,procedures,maintenance,dust}/v1.md`). Each one:
- asks for the fixed answer schema with a reason on every finding and on every not-credible mark;
- says the context text (notes included) is data, not instructions;
- names the cause-library rows valid for the batch, with the outside-library form;
- states the never-empty failing-component rule.

Their content is mine to draft and yours to review, tuned only on D–H.

**PR 5 files** (`backend/guideword/specialists/`):
- **`routing.py`:** question kind to agent, per the spec table. `ai:` and `eng:` questions go by their section's kind.
- **`context.py`:** one builder per agent, exactly the §5 "gets only" table, with these additions:
  - the `notes` of the in-scope objects, verbatim;
  - safeguards without a layer type, as existing protection with their description;
  - the list of plant IDs the agent may cite;
  - **chemistry (R5, decided):** where each chemical is present: the equipment and lines whose `contents` list it, and the injection points on equipment and lines that add it, with their IDs (and each holder's location ID), so a finding can cite where two chemicals meet;
  - **process (R6):** the name and physical form of each chemical in an in-scope `contents` list.
  - **every agent (R40):** the procedure steps and planned jobs that act on its objects (rule in R40), ordered by ID, trimmed to `specialist_max_input_tokens` from the end with the dropped IDs logged, or the batch fails if it still does not fit (R43).
- **`schema.py`:**
  - **Answer schema:** per question ID, either `not_credible {reason}` or `findings[]` with `cause_id`, `cause_text?`, `failing_component_type`, `failing_component_ids`, `consequence`, `safeguard_ids`, `adequacy`, `confidence` and `reason`. Optionally `added_questions[] {section_id, text}`.
  - **Length caps:** consequence, reason and text are capped in this internal schema.
  - **Validator** (code, never a model):
    - every question ID sent comes back once;
    - a missing ID is retried alone, and a duplicate or unknown ID is invalid;
    - component and safeguard IDs must be in the context;
    - `cause_id` must be valid for what the question is about (R7, decided): matrix, `nf:`, `relief:` and `dust:` check the question's section type against `applies_to`; `pair:` and `env:` accept any library cause; `work:` accepts `planned_work` or the target's section type; `proc:` accepts `procedure`; `outside_library` with `cause_text` is always allowed;
    - `failing_component_ids` must not be empty;
    - an operator cause must name a step or job ID from this agent's packet (R40, R41);
    - two findings with the same finding ID are invalid (R8).
- **`run.py`, `run_batch(gateway, run, agent, questions, tier)`:**
  - **Tool loop:** at most `specialist_max_tool_steps` tool calls per batch (R33), then the answer in the schema. Chemistry has `reactivity_lookup` in this phase, and other agents get no tools. A third tool call is refused. Two paths, chosen by the tier's `request.tools_with_schema` (R34): tools and schema in one request, or the tool call without a schema and then the answer with it.
  - **Records:** code builds the `Finding` records with `ids.finding_id`, sets the question status, and adds `ai:` questions up to the caps. An added question must name a section in the run's snapshot (its ID is `ai:<section>:<h(text)>`), so the chemistry agent, whose questions have no section, cannot add any.
  - **Steps and events:** an `AgentStep` per tool call and answer (tool `answer`), chained from the dispatch step. Events: `finding_added`, `coverage_updated`.
  - **Failures:** a question that fails validation twice becomes `failed`.
- **`batch.py`:** chunks question IDs by `specialist_batch_size[tier]`, one section or one list chunk per batch and never mixing agents, ordered by question ID so batches are deterministic.

**Tests first** (fake gateway)
- **Routing:** `test_routing_every_kind_reaches_its_agent`; `test_a_batch_never_mixes_agents`.
- **Context:** one test per agent, `test_<agent>_context_has_exactly_its_fields` on the §9 example, plus a test that notes and no-layer safeguards are included, and `test_chemistry_context_lists_where_each_chemical_is_present` (SIH in TOTE-1, MX-1 and L-12; KOH in MX-1).
- **Answer validation:**
  - `test_missing_question_id_retried_alone`;
  - `test_duplicate_or_unknown_question_id_invalid`;
  - `test_component_not_in_context_invalid`;
  - `test_cause_validity_per_question_kind` (R7: one case each for matrix, `nf:`, `relief:`, `dust:`, `pair:`, `env:`, `work:`, `proc:`, and outside library);
  - `test_empty_failing_components_invalid`;
  - `test_duplicate_finding_id_invalid` (R8).
- **Steps and jobs (R40, R43):** per agent, `test_<agent>_includes_a_step_in_scope_and_excludes_one_outside`; `test_chemistry_step_matched_through_equipment_contents`; `test_job_matched_through_reach`; `test_unlocated_job_never_matches`; `test_operator_cause_naming_a_step_outside_the_packet_is_invalid`; `test_steps_and_jobs_dropped_from_the_end_and_logged`; `test_batch_over_the_cap_with_nothing_left_to_drop_fails`.
- **Outcomes:**
  - `test_not_credible_sets_status_and_reason_no_finding`;
  - `test_chemistry_tool_call_runs_result_returned_then_answer`;
  - `test_third_tool_call_refused`;
  - `test_tool_then_answer_in_two_calls_when_tools_with_schema_is_false` (R34);
  - `test_added_questions_get_ai_ids_join_open_stop_at_run_cap`;
  - `test_question_failing_twice_is_failed`;
  - `test_finding_ids_built_by_code`.

## 2.5 Orchestrator — PR 6 (prompt) and PR 7 (code)

**PR 6:** `prompts/orchestrator/v1.md`. It sets out the four tools and the guards, one decision per step with a one-line reason, and treats coverage, IDs and results as data.

**PR 7 files** (`backend/guideword/orchestrator/`):
- **`view.py`:** the code-built input for each step:
  - coverage per list and section;
  - open, failed and unsure question IDs, truncated to `orchestrator_view.id_list_max` with counts;
  - the last `recent_steps` one-line results;
  - remaining steps and spend.

  Never a finding's consequence, cause text or full findings list.
- **`tools.py`:** argument schemas for `check_coverage`, `dispatch_specialist(agent, question_ids, level?)`, `reactivity_lookup` and `finish`. `level` is `bulk` (default, job `specialist_bulk`), `hard` (job `specialist_hard`) or `unsure` (job `unsure_answer`), so the orchestrator picks a job and the routing config picks the tier. Later tools are not offered at all.
- **`loop.py`, the `OrchestratorStepper`:**
  - one Ultra call per `advance` (job `orchestrator`, native tools, `tool_choice: required`);
  - code then runs the chosen tool, stores the `AgentStep` with its reason, and emits the events;
  - dispatches run batches in parallel up to the concurrency limit, and their results are stored in batch-ID order.
- **Guards:**
  - `finish` is refused while any question is open, unless it is `failed`, and the refusal lists the open IDs (R3);
  - an answered question is not re-sent and returns the stored result, with the unsure re-answer exception (R4);
  - malformed arguments are refused, the error goes back once, and then that branch stops;
  - the step cap gives `stopped_cap` and `cap_hit`;
  - **the severity reserve (R38):** during `analysis`, the gateway budget guard uses `run cap − severity_reserve_usd` as the limit. Reaching it ends the orchestrator phase with a `cap_hit` event (reason: severity reserve) and moves the run to `severity`; it does not stop the run. Severity then uses the full run cap. Open questions at that point stay open and are reported. Such a run ends `stopped_cap` after its severity step (never `finished`, because `finish` was not accepted), and like a run stopped during severity, it is reported and not scored until you decide;
  - the orchestrator's own call failing twice ends the run as `failed` (R24).

**Tests first** (fake gateway with scripted decisions)
- **`finish`:** `test_finish_with_open_questions_refused_with_ids`; `test_finish_after_all_answered_accepted`.
- **Dispatch:** `test_dispatching_an_answered_question_costs_no_call`; `test_dispatch_level_maps_to_job` (`bulk`, `hard`, `unsure`); `test_unsure_reanswer_on_ultra_allowed_up_to_the_cap` (R4).
- **Caps and errors:** `test_step_cap_stopped_cap_with_event`; `test_malformed_arguments_refused_once_then_branch_stops`.
- **What the orchestrator sees:** `test_orchestrator_input_never_contains_consequence_text`; `test_later_phase_tools_not_offered`.
- **End to end:** `test_full_fake_run_on_the_example_finishes_every_question_answered_or_not_credible`.
- **Severity reserve:** `test_fake_run_at_the_cap_boundary_still_completes_severity` (R38: the orchestrator phase stops at cap − reserve, and every finding still gets its severity within the cap).

## 2.6 Severity and ranking — PR 8a (prompt) and PR 8 (code)

**PR 8a:** `prompts/severity/v1.md`: a severity class from S1–S5 with a reason, using the `severity_classes.csv` definitions and the plant's location facts (occupancy, distance) as data.

**PR 8 files** (`backend/guideword/ranking/`):
- **`severity.py`, the `SeverityStepper`:**
  - one Ultra batch per `advance` (job `severity_reason`, `severity_batch_size` findings), validated by finding ID;
  - the severity and reason are written once into the finding's empty fields, and the severity call's `ModelCall.record_ids` lists those findings (R10);
  - a refused call (cap) stops the run and leaves the remaining findings without severity (R24).
- **`likelihood.py`:**
  - **Conversion:** the cause's initiating event, with `per_year` used directly, `per_metre_year` × the failing line's `length_m` and `per_lift` × the job's `lifts_per_year`.
  - **Missing facts:** a missing fact leaves the finding unrated and names the fact ID. `per_opportunity` is unrated and flagged.
  - **Outside-library causes:** the highest converted frequency among library causes of the same failing-component type, else `ranking.outside_library_default_frequency_per_year`, flagged "frequency assumed".
  - **Bands:** `min < f <= max`.
- **`rank.py`, `rank_findings(run) -> list[RankedFinding]`:**
  - computed by code, on demand, never stored (R11);
  - rated findings first, then the unrated ones, each group sorted by rating, then severity, then frequency (higher first), then finding ID;
  - Ultra re-answers are handled per R28.

**Tests first**
- `test_c01_ie_bpcs_0_1_is_l4_and_s4_rating_from_the_matrix` (the hand-worked example);
- `test_band_edges_are_upper_inclusive`;
- `test_ties_broken_by_severity_then_frequency_then_id`;
- `test_c20_without_length_is_unrated_naming_line_length_m`;
- `test_c24_without_lifts_is_unrated`;
- `test_outside_library_gets_highest_frequency_of_its_type_flagged`;
- `test_outside_library_type_with_no_library_cause_gets_the_default_flagged`;
- `test_ranking_identical_across_two_cache_replays`;
- `test_severity_batches_set_each_finding_once_and_record_ids`.

## 2.7 Live section suggestions — PR 9a (contract, R23) and PR 9

- **PR 9a (`contract/section-rejections`):**
  - `api/models.py`: `RejectedSuggestion {suggestion: SectionSuggestion, reason: str}`, and `SectionProposal.rejected: list[RejectedSuggestion] = []`, which is additive;
  - regenerated `openapi.json`, schemas and frontend types; the mock fixture gains `rejected: []`;
  - a decisions line, and the tag `contract-v1.2` (yours to push).
- **PR 9:**
  - **`GatewaySuggester`:** job `section_suggestion`, Super, prompt `section_suggestion/v1`, validated by `parse_response`. It is refused when its estimate exceeds `section_suggest_cap_usd` (R22). Ledger use is `development`, with no `ModelCall` record (R9).
  - **Propose endpoint:** uses the gateway suggester when not in mock mode and the gateway is configured. It returns rejected suggestions per R23 and still logs them.
- **Tests:** `test_valid_returned_rejected_returned_with_reasons`; `test_cap_refuses_a_call_that_would_exceed_it`; `test_null_suggester_still_used_without_a_gateway`.

## 2.8 Run endpoints — PR 10

The routes still in `NOT_BUILT_PHASE` at phase 2 leave the map as they are built, with `contract-v1` models unchanged and `label.kind = "live"`:
- `GET /runs`, `POST /runs` (estimated cost per R20), `POST /runs/{id}/cancel`, `GET /runs/{id}`, `GET /runs/{id}/events?after=`;
- `GET /runs/{id}/sections`, `GET /runs/{id}/questions` (filters), `POST /runs/{id}/questions` (an `eng:` question, open);
- `GET /runs/{id}/coverage` (the Phase 1 function with `findings`), `GET /runs/{id}/records/{record_id}` (record, parents, model and tool calls);
- `GET /budget` (R25), and `POST /internal/runs/{id}/advance`, which takes the secret, runs `advance` once and schedules the next one in-process while the run is `running`.

**Tests:** a contract test per route against a fake-gateway run; `label.kind == "live"`; 401 without the secret; 404s; an `eng:` question joins as open; `mode: sample` → 409 (R21); `POST /runs` returns the upper-bound estimate (R20); the advance loop runs to a terminal status with the fake gateway.

## 2.9 Run CLI and replay — PR 11

- **`scripts/run_case.py <plant> [--mode] [--use development|test_5] [--cap]`:**
  - upload, rule cut and confirm, with no suggestions;
  - start, then `advance` until a terminal status;
  - print the coverage lines and the top 10 ranked findings, and write the full ranked list to `bench/test5/5b/<case>.json` (R11);
  - when the run stops at a cap, say which cap and how many findings are unrated; when the orchestrator phase ended at the severity reserve, say how many questions were left open (R38).

  It runs only when you start it, and live only with keys set; the gateway refuses past the caps. It uses `settings.database_url` (by default `guideword.db` in the repo root, git-ignored). Keep that file between runs: it holds the response cache, so a re-run after a code change costs nothing.
- **`scripts/export_replay.py <run id>`:** writes every response the run used to `bench/replay/<case>/` as `<cache key>.json` (no keys, no headers), plus a manifest.
- **The replay test:** `backend/tests/replay/test_replay.py` runs the case through a `ReplayGateway`, which serves only fixtures and fails on a miss, and compares the ranked list. Until you have run a live case and committed fixtures, it uses a synthetic fixture set made by the fake gateway on the §9 example. The real-case fixture follows after your first 5B run (case G recommended).

## 2.10 Test #5 — PR 12a (prompt) and PR 12

- **PR 12a:** `prompts/test5a/v1.md`: package text, a step-by-step HAZOP checklist, a ranked list of top hazards in a fixed JSON schema with a reason per line.
- **PR 12 (`backend/guideword/bench/`, `bench/test5/`):**
  - **`test5a.py`:** one Ultra call per dev case, reading the package from `cases/dev/source/` (allowed: dev cases). Raw request and response go to `bench/test5/raw/5a/<case>.json` (R9); the ranked lines to `bench/test5/5a/<case>.json`.
  - **`four_tier.py`:** the 50-question sample (R27), each question answered by its own specialist on all four tiers with each tier's request settings, in batches of one case and one agent (never mixed), recording valid rate, latency and cost, with raw calls in `bench/test5/raw/four_tier/` (R9).
  - **`scripts/score_test5.py`:** the kill-test match rule (R26a), applied only to the agent's own words (R26c): for 5B, `<library cause name or cause_text> — <consequence>`; for 5A, each ranked hazard's text. #4 is not scored by this script (R37). IDs are never matched. A line matches when every `match` group has at least one of its phrases in that line, case-insensitive, with hyphens and Unicode dashes normalised (`ids.normalise_text`). It reports the rank of the first match (top 3, top 10 or missed) per configuration and case. Keys map to plant files by the letter after `case_` (`case_g_batch_plant` → `case_g`), and the `_note` entry is skipped. `memorization_markers` is not used in Phase 2 (the probe is Phase 6). It reads `cases/dev/keys/answer_keys.json` only when you run it; its tests use a synthetic key file of the same shape in `tmp_path`.
  - **`scripts/test5_results.py`:** writes `bench/test5/results.md` from run records, the raw files and the score files, never typed. It covers per-case rank, the automatic and hand scores, cost and time, and the four-tier table. Hand scores come from `bench/test5/hand_scores.csv` and `bench/test5/four_tier_scores.csv` (R35); the scripts write blank templates for you to fill.
  - **The case-by-case order (R29):** you run `run_case.py cases/dev/case_d.json --use test_5 --cap 0.85`, then `score_test5.py --case d` (the automatic rank) and your hand score, and report. A run that stopped at the cap is reported, not scored, until you decide (R38). I write nothing until you say go for G. E, F and H follow only if `budget_status.py` shows `test_5` covers them.
  - **`kill4.py`:** reads kill test #4's results JSONL (no key text, R26b) and reports, never re-scores (R37):
    - for the Ultra rows (the #4 configuration), the rank of the real cause per case as recorded in `score`;
    - case H as "recognised by Ultra, excluded" (from `recognized_incident`);
    - Nano's rows in a separate table, labelled "not the #4 configuration";
    - Bhargavi's hand review, quoted from `PROJECT.md` §20: 2 of 4 unrecognised cases in the top 3 (3 counting the under-ranked dead leg).

    It writes `bench/test5/kill4/summary.json` for `test5_results.py`. What `score` means is read from the file once you've copied it; if it isn't a rank, I stop and ask.
  - **The hand-scoring sheet:** `bench/test5/hand_scores.csv` lists the 5A and 5B top 10 per case with the matched text and, for 5B, the component and question IDs, for you to score (R35, R26c). #4 needs no sheet; its hand review is already recorded (R37).
  - **Your step:** copy kill test #4's results into `bench/test5/kill4/`.
- **Tests:**
  - `test_score_matches_every_phrase_group_in_one_line_after_normalising`;
  - `test_rank_of_first_match_top3_top10_missed`;
  - `test_sample_is_the_50_lowest_hashes_and_reproducible`;
  - `test_results_table_generated_from_records`;
  - `test_score_script_never_reads_keys_in_tests` (a synthetic path is injected);
  - `test_key_entries_map_to_cases_by_letter_and_note_is_skipped`;
  - `test_ids_are_never_matched` (a line whose only hit is in `pair:KOH-…:SIH` does not match);
  - `test_kill4_reports_recorded_ultra_ranks_without_rescoring` (R37: a synthetic file with the same fields; Nano rows are kept apart and case H is marked excluded);
  - `test_results_read_hand_scores_and_never_invent_them` (a missing score is shown as "not scored").

## 2.11 G2 — PR 13

After your hand scores:
- `bench/test5/results.md`, generated;
- a decisions line for G2 (pass or fail, and what follows);
- the Phase 3 routing (the cheapest tier that passed per job, from the four-tier table);
- the Phase 2 ticks.

**Your steps:** commit `budget/ledger-g2.jsonl` and tag `g2`.

---

## Conflicts and questions for Bhargavi

### Decided by Bhargavi (Oct 15)

Each gets a dated line in `docs/decisions.md`, in PR 0 unless noted.

| # | Decision |
|---|---|
| G3 | **Held-out cases.** The 8 cases (K–S, skipping O) were written by a separate Claude session, run as a one-time scheduled task on Oct 13 at 22:20 ET on Bhargavi's computer (auto mode, notifications off), instructed not to read this repo's code, prompts or specs. They live in `D:\Hackathon\guideword\guideword-heldout`, outside the repo. Bhargavi owns that folder and will push it to a private GitHub repo without opening it before Phase 6 (an honour system, stated in the README). Each case and key file is sealed by SHA-256 in its `SEALS.txt`, which Bhargavi commits here as `bench/heldout-seals.txt`. PR 0 says exactly this in `PROJECT.md` §13, the §18 tree and §22, `CLAUDE.md` §5 and `docs/decisions.md` (superseding the Oct 11 "case writer creates and owns" line). Claude Code still never reads that folder or the seals file. |
| R1 | `CLAUDE.md` §4 becomes: "Never write a test that calls a paid API, or a loop that can call one outside the gateway. Gateway retries and the run loop are allowed because every call passes the budget guard and caps, and only Bhargavi starts a live run." |
| R2 | `PROJECT.md` §7 becomes: "Development iterates on specialist prompts with Lightning. Ultra and Super are used only for the jobs routed to them (orchestrator, severity, section suggestions, unsure answers, the gateway check), always under the run and phase caps." |
| R5 | The chemistry context adds where each chemical is present: the equipment and lines whose `contents` list it, and the injection points (on equipment and on lines) that add it, with their IDs. The §5 table row becomes "Chemical list, properties, reactivity groups, and where each chemical is present". Logged as required for a valid finding, not a tuning change. |
| R7 | Cause validity is checked only against what the question is about. Matrix, `nf:`, `relief:` and `dust:` questions (which have a section type): the cause's `applies_to` must include that type. `pair:` and `env:` (no section): any library cause, or `outside_library`. `work:`: causes whose `applies_to` includes `planned_work` or the target's section type. `proc:`: causes whose `applies_to` includes `procedure`. `outside_library` with its cause text is always allowed. |
| R9 | No contract change. Model calls outside a run (section suggestions, 5A, the four-tier comparison) are not `ModelCall` records. They write a ledger line (job, use, cost), plus their raw request and response to `bench/test5/raw/` (test #5) or the structured log (suggestions). `ModelCall` stays the per-run trail. `gateway_check` follows the same rule, writing `docs/gateway-check.md`. |
| R26a | The dev key is `cases/dev/keys/answer_keys.json`: an object with a `_note` string and one entry per case, keyed `case_d_c4_unit`, `case_e_fcc_shutdown`, `case_f_pulp_mill_area`, `case_g_batch_plant`, `case_h_corn_mill` (mapped to plant files by the letter after `case_`). Each entry has `source` (string), `actual_event` (string), `match` (a list of phrase groups, each a list of strings) and `memorization_markers` (list of strings). A ranked line matches when every group has at least one of its phrases in that line, case-insensitive with hyphens normalised. The held-out keys use the case template's §4 format and are the Phase 6 scorer's job. |
| R29 | Per-run cap $0.85 for the 5B runs (R36). Run case D first, report its cost and the rank of the real cause, and wait. Then case G, then E, F and H only if the `test_5` allowance clearly covers them. |
| G1 | Squash-and-merge from now on. PR 0 annotates the 0.0 box: #2–#22 were merge commits, each through a pull request. `CLAUDE.md` §7 is unchanged. |
| G4 | The video script is deferred (Bhargavi deals with it later); Cowork drafts it and Bhargavi edits. Logged as a slip, with no date until Bhargavi sets one. |
| G6 | Bhargavi tags `g1` on `main` after PR 0 merges. |
| R3–R36 | Approved as recommended in the Phase 2 table below, except R12, R18 and R26, whose rows carry the changes. |
| G7 | GitHub Actions is green on `main` (Bhargavi, Oct 15). PR 0 ticks Phase 1 "CI green" and the gate's "CI green". |
| G8 | Dashboard on Oct 15: account balance $25.00 (untouched); trial credits $0.38 left (expiring in 23 days). All spend so far ($1.37 before the smoke test + $0.13 smoke test) came from trial credits. The ledger stays as it is: the $1.50 still counts against the $25 plan (conservative; no negative entries). The weekly reconciliation compares the ledger total with trial credits used plus balance used. Logged in `docs/decisions.md`; the opening-balance box is ticked as recorded. |
| R37 | Kill test #4 is **not re-scored**. The #4 configuration is Ultra: report the rank of the real cause per case as recorded in the file, plus Bhargavi's hand review from `PROJECT.md` §20 (2 of 4 unrecognised cases in the top 3; 3 counting the under-ranked dead leg). Case H was recognised by Ultra and is excluded. Nano's rows are reported but are not the #4 configuration. |
| R38 | A run stopped by a cap during severity is reported and not scored until Bhargavi decides. The run caps gain `severity_reserve_usd: 0.15` (it enters `Run.caps`): the orchestrator phase stops at the run cap minus the reserve, so severity can finish. |
| R39 | Approved: PR 9a regenerates only `frontend/src/api/types.ts`, and its description tells the frontend session to rebase. |
| R40 | Added Oct 15 (found while checking case G; same class as R5, not tuning). Every specialist context gains the procedure steps and planned jobs that act on its objects, chosen by code: a step that names an equipment, valve or line ID in the agent's scope (chemistry: equipment whose contents include the chemical and lines carrying it; dust: equipment holding the dust); a job whose Phase 1 within-reach set overlaps the scope (unlocated jobs never match). Per step: ID, procedure ID, its words verbatim inside the data delimiters, equipment and valve IDs; per job: ID, type, line IDs; ordered by ID. An operator cause must name a step or job from that agent's packet. `PROJECT.md` §5 rows for process, chemistry, piping and dust updated. Log entry, word for word: "R40 — found while checking case G (dev, G2). Needed for valid findings under the frozen §5 failing-component rule, not tuning: no prompt wording, threshold or case-specific content changed. Same class as R5." |
| R41 | The R40 operator-cause guard lives in the answer validator with the other answer checks: invalid, one retry with the error, the reason on the model call record (not `ToolCall.refused_reason`; an answer is not a tool call). |
| R42 | R8 still applies within one answer; across answers the same finding ID is stored once; different questions naming the same step stay separate findings. No extra dedupe logic. |
| R43 | `run.specialist_max_input_tokens: 24000` (in the run-ID hash). Steps and jobs are dropped from the end in ID order until the batch fits, with the dropped IDs on the `dispatch` event and in the log. If it still does not fit with all of them dropped, the batch fails (no oversized call, nothing else dropped, a `dispatch` event with status failed; its questions count one attempt). `run_case.py` and the test #5 results report the dropped count per run. Input cost at the cap: about $0.0014 Lightning, $0.0072 Super, $0.024 Ultra. |
| R44 | (a): the view lists open IDs grouped by agent, up to `dispatch_max_question_ids` per agent (failed and unsure lists stay at `id_list_max`; counts always shown). `question_ids` on `dispatch_specialist` is optional: left out, code selects the next IDs for that agent at that level in ID order, up to 60, and the dispatch event records them; an explicit list is still validated; an omitted list with nothing to select is refused. Levels select: `bulk` open; `hard` open with a failed attempt; `unsure` answered with an unsure finding and no Ultra re-answer, within the cap. |
| R45 | Added Oct 15 (found building PR 8: the view's spend made a cache replay miss from the second orchestrator turn, so 2.5's "spend budget in the view" and 2.6's "identical across two replays" could not both hold). Option 1, amended: (1) a cache entry stores the original call's `cost_usd` when written, and a hit adds that stored figure, never one recomputed from current prices; (2) the run keeps two figures: `spent_usd`, the money actually paid, from the call records ($0 on a full replay), and `cap_spent_usd`, paid calls plus cache hits at their stored cost. The orchestrator's view, the cap stop and `severity_reserve_usd` use `cap_spent_usd`; the UI, the run summary and the ledger use `spent_usd`; (3) environment allowances read the ledger only, and replays write no ledger lines; (4) `ModelCall.cap_cost_usd`: `cost_usd` on a paid call, the stored cost on a hit; the check `Run.cap_spent_usd == sum(ModelCall.cap_cost_usd)` runs in tests and at the end of every run; (5) a hit on an older cache row with no stored cost works the cost out once from the row's stored tokens and current prices, writes it into the row and logs a backfill; a row with no token counts counts $0 with a warning. Contract change `contract/run-cap-spend`, tag `contract-v1.1`; section rejections (R23) move to `contract-v1.2`. Tests: identical ranking and stop point on replay; identical after a prices change; full replay with `spent_usd` 0 and `cap_spent_usd` equal to the original; a partly cached resume sums both correctly; the backfill and the no-tokens warning. |

### Still open: your confirmations (PR 0 can merge only after these)

| # | Question | My recommendation |
|---|---|---|
| G2 | **Kill test #1 (0.9).** Your proposed words: "Kill test #1 ran on tep-rust, outside this repo. None of that code and no Operon code is in Guideword." You marked it "answer only if true". | Reply "G2 true" and I log those exact words and tick 0.9. Until then, 0.9 stays open. |
| G5 | **0.10 statuses:** facilitator outreach, the second $25 grant, the City Winner question. Still a template in your answers. | Tell me done or open for each (with a date if done), and I record them. |

### Phase 2 (approved Oct 15 as recommended, except where a row says otherwise)

| # | Where | Question | Decision |
|---|---|---|---|
| R3 | 2.5 vs `PROJECT.md` §5 | §5's `finish` guard also requires the top findings to have been through LOPA and evidence. Phase 2 has neither. | Phase 2's guard covers questions only; Phase 3 adds the LOPA and evidence condition. A decisions line. |
| R4 | 2.5 vs §5 | "A question already answered is not re-sent" conflicts with "re-dispatch unsure findings to Ultra (capped)". | `dispatch_specialist(..., level="unsure")` may re-send an answered question only if it has an unsure finding with no Ultra re-answer yet, up to `unsure_reanswers_per_run`. Every other answered question returns the stored result at no cost. |
| R6 | 2.4, §5 | The process agent's context names `contents` chemical IDs but has no chemical names or properties, so it can't judge a consequence. | Add the name and physical form of each chemical in an in-scope `contents` list. Nothing else from the chemistry data. |
| R8 | 2.4 | Two findings in one answer with the same cause and components get the same `f:` ID. | Treat it as invalid and retry once with the error. Never a silent merge. |
| R10 | 2.6 | Severity is stored on the `Finding` after the finding was made. Is that "editing model output"? And `Finding` has no field for the severity call's ID. | A one-time fill of the empty `severity_class` and `severity_reason` fields, never overwritten. The trace runs through the severity call's `ModelCall.record_ids`. A decisions line. |
| R11 | 2.6 | "A ranked list per run stored": there is no ranking table or record in §11, and likelihood and rating aren't `Finding` fields. | `rank_findings(run)` computes them on demand (code, deterministic). `run_case.py` and the scorer write the ranked list to `bench/test5/<config>/<case>.json`. No new table. |
| R12 | 2.6 | The outside-library default of 0.1/year would be a literal in logic. | `caps.yaml` `ranking.outside_library_default_frequency_per_year: 0.1`, citing §5 Step 6. The other option is a reference row, but that needs a sourced row from Cowork. **Approved:** in `caps.yaml`, with a comment citing `PROJECT.md` §5 Step 6. |
| R13 | 2.2 | "Retry up to 3 times" (4 attempts) vs the acceptance line "three 5xx → error" (3 attempts). | `max_attempts: 3` in total. |
| R14 | 2.2 | The cache key's "exact input" is messages + schema + tools, but `max_tokens`, reasoning and `tool_choice` also change the output. And which outcomes are cached? | Include every request setting. Cache every response that came back (ok, invalid, truncated) so replays are identical, but not transport errors. |
| R15 | 2.1, decisions Oct 12 | The spec lists a `response_cache` table, while the Oct 12 decision says "`response_cache/` stays a git-ignored local cache". | The DB table is the cache. The directory goes unused (it stays ignored). A decisions line supersedes Oct 12. |
| R16 | 2.2 | The spec's `Gateway.call` signature lacks a tier override (needed by the four-tier sample; dispatches choose a job, not a tier), `tool_choice` and a caller ID validator. `use` and `phase` have nowhere to go. `Ledger` and the estimate live in `scripts/`. | Add `tier`, `tool_choice` and `validator` to `call`, and give `use` and `phase` at construction. Move `Ledger` and the estimate into `gateway/` and re-export them from `live_call.py`. |
| R17 | 2.2 | The gateway guard lists the run cap and use and environment allowances, but not the phase cap that `live_call` enforces. | Also enforce `phase_caps_usd[phase]`. Passing it gives `stopped_budget`; no entry means refused. |
| R18 | 2.2–2.5 config | Values the spec leaves open (my starting values, to refine after `gateway_check`), plus which keys enter `Run.caps` and so the run ID. | `max_tokens`: orchestrator 4096, **specialist_bulk 6144** (changed by Bhargavi: a batch of 10 needs room for several findings each), specialist_hard 6144, unsure_answer 6144, severity_reason 4096, section_suggestion 6144, test5a 8192. `specialist_batch_size`: lightning 10, nano 10, super 5, ultra 5. `ai_questions_per_batch` 2, `ai_questions_per_run` 20, `unsure_reanswers_per_run` 10. `orchestrator_view`: id_list_max 20, recent_steps 5, dispatch_max_question_ids 60. `severity_batch_size` 20. `gateway`: max_attempts 3, backoff 1 s then 2 s. `Run.caps` holds the `run` block plus `max_tokens`, `specialist_batch_size`, `ai_*`, `unsure_*`, `orchestrator_view` and `severity_batch_size` (everything that can change answers); concurrency, retries and allowances stay out. |
| R19 | 2.1, `CLAUDE.md` §9 | Run inputs need "prompt versions", and `CLAUDE.md` says a prompt change means a routing config update, but no config holds prompt versions. | `routing.yaml` gains `prompts: {orchestrator: v1, specialists/process: v1, …, severity: v1, section_suggestion: v1, test5a: v1}`. The gateway loads `prompts/<name>/<version>.md`; a missing file is a config error. |
| R20 | 2.8 | `POST /runs` returns `estimated_cost_usd`, with no rule given. | Use the agreed estimate rule on the run's real first-step inputs: specialist batches × the batch estimate + `orchestrator_max_steps` × the orchestrator step estimate + severity batches for up to 2 findings per question, capped at `spend_cap_usd`. It is labelled an upper bound. |
| R21 | 2.1, 2.9 | `mode: sample` is in the contract and the run ID, but nothing defines it. Sampling questions would break "complete by construction". | Phase 2 accepts only `full`, and `sample` returns 409 "sample mode is built in Phase 7". The live-run button (Phase 7) uses a small sample *plant*, not sampled questions. |
| R22 | 2.7 | Is `section_suggest_cap_usd` per call or per plant? | Per propose call: refuse when the estimate exceeds 0.05. |
| R23 | 2.7 | The contract change for rejected suggestions on screen (additive, `contract-v1.2`). | Approve. `RejectedSuggestion {suggestion, reason}`; the default `[]` keeps existing clients valid. |
| R24 | 2.1, 2.5, 2.6 | The run lifecycle after `finish` isn't defined. | Steps: `analysis` (the orchestrator), then `severity` (one batch per advance), then `ranked`, then `finished`. A severity refusal by a cap gives `stopped_cap` and leaves those findings unrated. The orchestrator's own call invalid or truncated twice gives `failed` with `run_failed`. |
| R25 | 2.8 | `GET /budget` lists environments, but each environment reads only its own ledger. | Show only this environment's line, with spend by model from its own ledger. `live_run_available` is false on the laptop; the button is Phase 7. |
| R26 | 2.10 | (b) Does kill test #4's results file contain key text? (c) What text does the automatic score match? | (b) **No key text.** The fields are `answer`, `case`, `finish_reason`, `model`, `probe`, `recognized_incident`, `score`, `seconds`, `usage`, and `score` holds numbers only, so I may read it. (c) **Only the agent's own words:** `<library cause name or cause_text> — <consequence>`. Component IDs and the question ID appear in the hand-scoring sheet but are never matched (an ID like `pair:KOH-EMULSIFIER:SIH` would match the key's "koh" group whatever the agent said). Logged. |
| R27 | 2.10 | The sample uses "the 50 lowest `h(question ID)`", but question IDs can repeat across cases (for example the same chemical IDs), and the hash wouldn't say which case. | Use `h([plant_id, question_id])`, with each tier's own request settings and the same prompt versions. |
| R28 | 2.6 | An Ultra re-answer is a second finding for the same question. Are both ranked? | Rank every finding (none is ever edited). The original unsure finding shows "superseded by <id>" in the ranked output, and the test #5 scorer counts the first match either way. |
| R30 | 2.9 | Which case gets the committed replay fixtures? | Case G after its 5B run. Until then, the replay test uses a synthetic fixture from the §9 example. |
| R31 | 2.2 | The acceptance line wants a ledger line "with job, use and phase", but the frozen `SpendEntry` has no `job` field (it has `script` and `purpose`). | Set `script: "gateway"` and `purpose: "<job>"` (plus the run ID when there is one). No contract change. |
| R32 | 2.1 | "Every type in the `EventType` enum is emitted where it happens", but `chain_added`, `lopa_done` and `evidence_added` belong to Phase 3 and 4 tools. | Phase 2 emits every type it has a producer for. Those three come with their tools, and a test lists which types Phase 2 emits. |
| R33 | 2.4 vs `PROJECT.md` §5 and §7 | §5 and §7 say a specialist takes at most 2 tool steps **per question**, while spec 2.4 says at most 2 tool calls **per batch**. | Per batch, as the spec says (cheaper, and one answer per batch). Reword §5 and §7 in PR 0. |
| R34 | 2.2 fallback | If `gateway_check` shows Lightning cannot combine tool calls with strict `json_schema` and reasoning off, the specialist must fall back to two calls (a tool call without a schema, then the answer with it). The fallback has to exist in code before the check runs. | A per-tier `request.tools_with_schema: true|false` in `models.yaml` (starting `true`). `run_batch` supports both paths, with a test for each; the check's result sets the value, with a decisions and feedback-log line. |
| R35 | 2.10 | Your hand scores (5B top 10, 5A, #4, and good/partial/wrong on the four-tier sample) must feed a generated table, so they need a file format. | `bench/test5/hand_scores.csv` (`case, config, rank, score, reason`) and `bench/test5/four_tier_scores.csv` (`question_key, tier, score, reason`). The scripts write blank templates; you fill them; `test5_results.py` reads them. Scores are never typed into `results.md`. |
| R36 | R29 | "Per-run cap $0.85": is that the `--cap` for the test #5 runs only, or the `caps.yaml` default `run_spend_cap_usd` (now 1.00)? | `--cap 0.85` on the 5B runs; the `caps.yaml` default stays 1.00 (changing it would change every run ID). |


## Not doing (near the scope line)

- No connector, chains, LOPA, shortlist by gap or recommendations (Phase 3).
- No `web_research`, `search_precedent`, `physics_calc` or `run_simulation`, and no precedent index (Phase 4).
- No frontend, hosted deployment, demo mode, live-run button or `sample` mode (Phases 5 and 7).
- No `json_object` fallback (the smoke test showed strict `json_schema` works on every tier with its settings), and no use of the `not_credible` or `extraction` jobs (specialists mark not-credible in their own answer).
- No change to `contract-v1` except the additive PRs 8b (R45) and 9a (R23).
- No reference-table values changed or rows added.
- No memorisation probe (Phase 6); the dev key's `memorization_markers` are not used. `bench/heldout/`, `bench/heldout-seals.txt`, `guideword-heldout` or accident reports beyond the dev packages.

## Live calls and spend

Every live call is started by you, through the gateway, after the PR it needs has merged. My estimates use the agreed rule and the smoke data; real reasoning tokens on Ultra are the main unknown.

| Step (after PR) | Use | Estimate |
|---|---|---|
| `gateway_check.py`: 4 tiers + the Lightning tool + schema check (PR 2) | development | ≈ $0.01 real; ≤ $0.30 cap |
| Dev run of the §9 example end to end (PR 11): 98 questions | development | ≈ $0.10–0.25 |
| Live suggestions on the §9 example (PR 9) | development | ≈ $0.01 |
| 5B, one case at a time under `--cap 0.85` (R29): D, report, G, then E, F, H only if covered (PR 12) | test_5 | ≈ $0.30–0.85 per case (Lightning batches ≈ $0.05, orchestrator 20–40 Ultra steps ≈ $0.10–0.40, severity ≈ $0.15–0.40); D + G ≤ $1.70; all five ≤ $4.25 |
| 5A: 5 Ultra calls (PR 12) | test_5 | ≈ $0.20 |
| Four-tier: 50 questions × 4 tiers ≈ 20 calls (PR 12) | test_5 | ≈ $0.15 |

- **Development:** ≈ $0.40 of the $1.00 Phase 2 share, leaving about $3.10 of the $3.50 development balance.
- **test_5:** ≈ $1.85 at the low end; the high end ($4.60 with 5A and the four-tier sample) passes the $4.00 allowance. So the 5B runs go one case at a time (R29), and 5A and the four-tier sample run only from what is left after D and G. The gateway refuses any call that would pass the $0.85 run cap, the phase cap (5.00) or a use allowance, so the worst case is a refused call, never an overspend.

## Verification

- **Per PR:** the `CLAUDE.md` §8 commands, CI green before merge, and `contract/openapi.json` unchanged except in PRs 8b and 9a.
- **PR 2:** the allow-list test passes with the new entry and fails for a stray `import openai`.
- **PR 7:** a full fake run on the §9 example reaches `finished` with every question answered or not credible, and `finish` is refused while any is open.
- **PR 8:** the hand-worked C01 example matches `risk_matrix.csv`, and the ranking is identical across two cache replays.
- **PR 11:** the replay test is green from fixtures with the network blocked.
- **G2:** you hand-score the 5B top 10 on D and G; `results.md` is generated; the ledger snapshot and tag are made.
