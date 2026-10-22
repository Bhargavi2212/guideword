# Phase 4 — Evidence: calculations, precedent, web research, simulation

**Dates:** Oct 22–24 (feature dates at the end) · **Ends with:** evidence on the top shortlist lines of the Williams Geismar demo run and dev cases D–G, every item traceable to a plant fact, a tool call, a model call or a source URL
**Source of truth:** `PROJECT.md` (§5 Step 3 item 7, Step 4 tool table and code guards, Step 7; §8; §10; §11 call boundaries; §13 isolation; §20 kill test #1; §25 checklist). If this spec and `PROJECT.md` disagree, stop and ask.
**Status:** approved 2026-10-21 (Bhargavi), as amended by `specs/phase-4-plan.md`'s answers.

## Goal, and what the video shows

Each top line of the shortlist carries **evidence** that is not the model's opinion: a calculation from plant facts, a real past incident, and, on the Tennessee Eastman plant, a simulator run. Each item is marked **confirmed**, **contradicted** or **no evidence available** (§5 Step 7), with its sources.

Video beat, after the "no credit — inlet valve HV-B-SIN closed" layer: *"Heating the blocked-in reboiler to the quench water's 85 °C takes the vapour pressure to at least N× the shell's design pressure, before any liquid expansion."* N and the chemical come from the record, which the hand-worked fixture (4.5) checks (plan Q12). (The precedent beat was dropped on 2026-10-22: the final run's precedents are honestly `none`; see `docs/decisions.md`.)

## What the code has today (checked on `main` at "Merge pull request #86", 2026-10-21)

- **Evidence record:** `Evidence` exists in `schema/records.py`: `kind` calculation / precedent / simulation; `verdict` confirmed / contradicted / none; `summary`, `tool_call_id`, `fact_ids`, `sources`. It has **no `model_call_id`**, so a judged precedent couldn't name the call that judged it.
- **Event:** `evidence_added` exists in the enum, but `runs/store.py` doesn't emit it (it's not in `EMITTED_EVENT_TYPES`).
- **Reads:**
  - `ShortlistItem.evidence` is always `[]` (`review/shortlist.py`).
  - The worksheet's Evidence column is always `None` (`review/worksheet.py`).
  - `GET /runs/{id}/records/{id}` has no evidence kind (`api/live.py` `record()`).
- **Steps:**
  - The machine's steps are `plant_screen → analysis → severity → chains → chain_severity → lopa → recommendations → ranked` (+ `retry_failed`).
  - The post-step sets are `POST_JOBS`, `POST_STEPS`, `POST_PROMPTS` and `POST_HASH_FREE_CAPS` (`runs/post_budget.py`), plus `AFTER_ANALYSIS` (`runs/start.py`).
  - Re-runs: `RERUN_FROM = ("chains", "lopa")` and `RERUN_SUPERSEDES` (`runs/extend.py`). `SUPERSEDED_TABLES` holds chain, lopa, recommendation and model_call (`runs/store.py`), and the contract's `SupersededRecord.kind` has the same four.
- **Hashing:**
  - Everything in caps.yaml's `run:` and `ranking:` blocks is hashed into new run IDs (`config.run_input_caps`), except `POST_HASH_FREE_CAPS`.
  - `evidence_top_n: 5` is already in `run:`, so it's hashed today.
  - `reference_versions`, one hash per `reference/` table, is hashed too, so **adding a table to the `ReferenceSet` moves every new run ID**.
- **Tools:**
  - `tools/record.py` runs only `reactivity_lookup`, and `orchestrator/tools.py` offers no evidence tool.
  - `ToolCall.agent_step_id` is required (`step:` ID), and `ids.tool_call_id` needs a step ID.
  - `simulator/` is an empty package.
- **Tavily:**
  - It's called only from `scripts/live_call.py`; smoke test T10 called it once, so a key exists.
  - `test_http_allowlist.py` allows `tavily` only there. Its comment says `backend/guideword/tools/**` is added "with the Phase 4 tools that call Tavily".
  - `tavily-python` is already a dependency, and `Settings.tavily_api_key` exists. The ledger records Tavily as `kind: tavily`, cost 0.
- **Replay:** `gateway/replay.py` exports model responses and a manifest with ranked lines, hypotheses, tiers, chains, LOPA and recommendations. It has no Tavily responses and no evidence.
- **Plant facts:** `operating.target_id` must be an **equipment or line** ID (`schema/validate.py`), so a utility can't carry a temperature row. No Tennessee Eastman plant file exists in `cases/demo/`. The simulator package decision (Oct 11, `tennessee-eastman-profbraatz`) has never been installed or run in this repo, and its PyPI availability is unconfirmed.
- **Submission rule:** §25 lists "Runtime Tavily call in the product". Phase 4 is where that gets met.

## Decisions this spec asks Bhargavi to make (recommended answers given)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| P4-1 | Evidence is a **fixed code step, `evidence`, after `recommendations` and before `ranked`** (the P3-1 pattern). The orchestrator gets no evidence tools; `web_research`, `search_precedent`, `physics_calc` and `run_simulation` leave the §5 tool table as orchestrator tools and become functions the evidence step calls. | Yes | Evidence is for the **top** lines, which are only known after severity, LOPA and ranking. As orchestrator tools they would change every orchestrator request (new run IDs, no replay). The agent still drives the analysis, which is what the video shows. |
| P4-2 | **Evidence never changes** rank, tier, lead, severity, likelihood, LOPA or recommendations. It is shown beside them. | Yes | It can't feed anything back into the score (P4-7), and it keeps "code ranks, evidence informs" simple to explain. |
| P4-3 | Which lines: the top `evidence_top_n` (5) **confirmed and also-found** lines in display order (chains included), chosen from the stored records exactly as the shortlist is built (same lead rule as the run's pass), **without** overrides, so an engineer's edit never re-selects lines. | Yes | §5 Step 6: "full evidence on the top 5". Line choice must be reproducible on replay. |
| P4-4 | `physics_calc` is **pure code**: three calculations with fixed inputs (4.1). Which apply is decided by the question's guideword and parameter, never by a model. A missing fact gives a `none` record naming the missing fact IDs; **never a default value**. | Yes | CLAUDE.md: code owns arithmetic; never invent plant facts. |
| P4-5 | Precedent: a **local index** (`reference/precedent_index.csv`, plan Q5, written by Cowork from CSB investigation-page metadata, a source on every row) searched by code; **Tavily** only when the index gives nothing the judge accepts. One Super call per line judges the candidates (`precedent_judge/v1`): same mechanism yes/no with a reason, citing only candidates and URLs it was sent. **Amended (plan Q15):** the top line always gets one Tavily search too, its results judged alongside the index candidates under the same block list. | Yes | §5 Step 4: "local index, then Tavily if nothing fits". Retrieval, blocking and the URL check stay code. |
| P4-6 | How a code step's tool calls are recorded: **(a)** `ToolCall.agent_step_id` becomes optional and `ToolCall` gains `step: str` (the run step that made it), with `ids.tool_call_id` taking either; or **(b)** one `AgentStep` per evidence line with a new `Agent` value `evidence`. | Claude Code proposes in the plan; Bhargavi decides | Every tool call must be logged and traceable (§5 code guards). Today's record can't hold one with no agent step. Either way it's a contract change. |
| P4-7 | **Benchmark runs (Phase 6) skip the evidence step.** **Amended (plan Q4):** evidence is off when the run's use is `benchmark` or `test_5`, on otherwise (API runs included), recorded in the step summary; `--no-evidence` still forces it off. For demo plants, a committed **block list** filters every precedent row and Tavily result: `cases/demo/<plant>.block.txt`; WG: `Williams`, `Geismar`, `EA-425`, `propylene fractionator`. | Yes | Evidence can't change the score (P4-2), so skipping it in the benchmark loses nothing, saves money and removes any path from the precedent index or the web to a held-out answer. The block list keeps the demo from citing its own CSB report (§5 code guards). |
| P4-8 | `web_research` and `search_precedent` are **one evidence routine** producing `kind: precedent` records (the enum has no research kind). | Yes | No contract change for a second kind with the same shape. |
| P4-9 | **Evidence settings are not hashed.** A new top-level caps.yaml block `evidence:` (outside `run:`) holds `evidence_top_n`, `precedent_candidates`, `tavily_searches_per_run`, `tavily_max_results`, `overflow_confirm_minutes`, `heat_up_confirm_minutes`, `te_hours`. `run.evidence_top_n` moves there and joins the hash-free list (stored runs keep their stored value, so D–G keep their IDs). The `precedent_index.csv` (plan Q5) and `te_faults.csv` tables are loaded **outside** `ReferenceSet.versions`, and their hashes are recorded on the evidence pass event. | Yes | Same rule as the Phase 3 post-step settings (connector/v2 plan Q5): a later step's settings must not move run IDs. Adding a table to `ReferenceSet` would change every new run's ID and break the replay of stored fixtures. |
| P4-10 | Simulator: Tennessee Eastman **only**. It needs a TE plant file, a fault map and one full TE run, so it is the **last** PR, gated: the package must install and reproduce kill test #1 by Oct 23, or it goes in the pitch as "next" (§15 rule). New dependency: stop-and-ask, approved here only if the gate passes and the licence is confirmed. | Yes | The WG demo can't use it; it's the highest-risk item. |

## In scope

### 4.1 `physics_calc`: code only (`tools/physics.py`)

Each calculation takes plant facts only and returns a number with units plus the fact IDs it used, or `skipped` with the missing fact IDs. Units in names (`_kpa` gauge, `_kpaa` absolute, `_c`).

| Calculation | Applies to findings on | Inputs (fact IDs) | Result | Verdict |
|---|---|---|---|---|
| `blocked_in_heating` (amended, plan Q1, Q11–Q13; replaces `pressure_multiple`) | the equipment of a `m:<section>:more:pressure` finding's section, **and** each scenario-object equipment item (section objects ∪ failing components) with `design_pressure_kpa` and a `heat_sources` entry; one card per equipment per line | equipment `design_pressure_kpa`; each content chemical's `vapor_pressure_points`; the heating-medium temperature: for each `heat_sources[]` not locked out with a `via_line_id`, that **line's** `operating` temperature row, `design_max` if set, else `normal` (flagged which); the highest of those; the valve facts of the three conditions | for each content chemical with points: vapour pressure at that temperature by Clausius–Clapeyron interpolation **between the two bracketing points** (`ln P` linear in `1/T`, T in K), **never extrapolated**; minus 101.325 to gauge; ÷ design pressure. The **lowest** is reported, naming the chemical: "at least N× design (lowest of the listed chemicals)"; chemicals with no points are named ("no data: <ids>; bound covers listed chemicals only"). | `confirmed` only when (1) every process-side line to or from the equipment (excluding lines carrying its heat sources' isolating valves) has a valve `normal_position: closed`, (2) at least one heat source's isolating valves are not all locked closed, and (3) the multiple ≥ 1.0, citing every fact used. Otherwise `none` naming each failed condition ("not blocked in", "heat source locked out", "below design"), **never `contradicted`**, because the calculation is a lower bound. Always flagged "pure-component vapour pressure; liquid-full thermal expansion not modelled; real pressure can be higher". |
| `overflow_time` | `m:<section>:more:level` | equipment `volume_m3`; `operating` level `normal` (% of range); the largest `normal_flow_kg_h` among lines whose `to_id` is the equipment (flagged if several); content chemicals' `density_kg_m3`, using the **lowest** (shortest time), named | minutes to 100 % = (1 − normal/100) × volume × density ÷ flow × 60 | `confirmed` if < `overflow_confirm_minutes` (60), else `none`; never `contradicted` |
| `heat_up_rate` | `m:<section>:more:temperature` | equipment `heat_duty_kw`; `volume_m3`; content chemicals' `density_kg_m3` and `heat_capacity_kj_kg_k` (the lowest of each, fastest heat-up, named); `operating` temperature `normal`; the limit is `design_max`, else `design_temp_c` | °C per minute, and minutes from normal to the limit | `confirmed` if the limit is reached in < `heat_up_confirm_minutes` (60), else `none` |

- For a chain: each calculation runs on each finding link whose question qualifies; all results are listed.
- Display: the stored number is never rounded. The text the card and worksheet show ("about 1.6× design") comes from the backend's one formatter (`review/display.py`, alongside `gap_text`), 2 significant figures.

### 4.2 Precedent index (`reference/precedent_index.csv`, plan Q5): data by Cowork, loader by Claude Code

- **Headers (new table; PROJECT.md §10 gains it):** `id, title, date, country, company, location, chemicals, equipment_types, mechanism_keywords, summary, url, source`.
- **Rows:** CSB completed investigations, from CSB's own investigation pages: title, date, location, and the summary CSB publishes. `chemicals`, `equipment_types` and `mechanism_keywords` are `;`-separated words taken from that summary, never inferred. Every row has `url` and `source`.
- **Who writes it:** Cowork. Claude Code never reads accident reports (CLAUDE.md §5). The loader checks headers, unique IDs, and a URL and a source on every row. It is loaded outside `ReferenceSet.versions` (P4-9).
- **Isolation:** Cowork has not seen the held-out cases and builds the index from CSB's public list only. P4-7 keeps the index out of benchmark runs.

### 4.3 Precedent search and web research (`tools/precedent.py`, `tools/web.py`)

1. **Query, built by code** from the line: its lead finding's cause text (each finding link's for a chain), the content chemicals' names, the section's equipment type, and the question's guideword and parameter. No model writes the query.
2. **Block:** rows and results containing any block term as a whole word or phrase (word boundaries at both ends, case-insensitive, in any field or URL; plan Q17) are dropped first.
3. **Local search:** BM25 over `title + summary + chemicals + equipment_types + mechanism_keywords`, implemented in the module (about 50 lines, no new dependency). Top `precedent_candidates` (5).
4. **Judge (Super):** job `precedent_judge`, prompt `prompts/precedent_judge/v1.md`, drafted by Claude Code and reviewed by Bhargavi. It sees the line's cause and consequence and the candidates by **handle** (`K1…`, as in connector/v2: no long IDs to copy), all as data. Per candidate: `same_mechanism` yes/no and a reason. Code maps handles back exactly; an unknown handle or an unsent URL drops that item and logs it.
5. **Tavily:** on the **top line, always** one Tavily search with the same code-built query (`tavily_max_results`, 5), block-filtered, its results judged with the local candidates in one call (plan Q15). On other lines, the fallback: if no local candidate is judged `yes`, one search, block-filtered, then the same judge.
6. **Result** (amended, plan Q2): one `precedent` record per **accepted incident**, `confirmed`, with its title and URL in `sources` and the judge's reason in `summary`; or one `none` record (`ev:<target>:precedent:none`, "no matching precedent found"). Never `contradicted`.

**Rules that apply throughout:**
- **Call boundary:** only `guideword/tools` calls Tavily (§11). `test_http_allowlist.py` gains `tavily: backend/guideword/tools/**`. That's a stop-and-ask change, **approved by this spec**.
- **Spend:** every search is checked and written through the run environment's ledger (`kind: tavily`, cost 0 against the $25), capped by `tavily_searches_per_run` (5). Written through `ledger_for`, laptop or hosted (plan Q14).
- **Cache and replay:** Tavily responses are cached by exact query, as model responses are. `export_replay` writes them with the model responses, and a replay serves them from the fixtures; a missing one fails loudly, like `ReplayMiss`.

### 4.4 The evidence step (`evidence/step.py`) and its wiring

**Step and sets:**
- `evidence` is a new step: `recommendations` now goes to `evidence`, and `evidence` goes to `ranked`.
- Add it to `AFTER_ANALYSIS`, `POST_STEPS` and `steppers_for`. Add job `precedent_judge` to `POST_JOBS`, prompt `precedent_judge` to `POST_PROMPTS`, `routing.yaml` (`precedent_judge: super`) and `max_tokens`.
- Its spend counts against the post cap, like the other post steps.

**Existing runs:**
- A finished run whose last pass had no evidence step: `extend_run.py <run> --evidence --post-cap <usd>` adds it (same run ID).
- A run that already has evidence: `--rerun-from evidence`. Add it to `RERUN_FROM`, with `RERUN_SUPERSEDES["evidence"] = (("evidence", "tool_call", "model_call"), {"precedent_judge"})`. `SUPERSEDED_TABLES` gains `evidence` and `tool_call`.

**Per line (P4-3), in order:**
1. Each qualifying `physics_calc`.
2. Precedent search.

Each produces `Evidence` records (`ev:<target>:<kind>:<h>`), an `evidence_added` event each (added to `EMITTED_EVENT_TYPES`), `ToolCall` records per P4-6, and the judge's `ModelCall`. The pass event records the evidence settings, the block list used, and the index and fault-map hashes (P4-9).

**Reads and export:**
- `ShortlistItem.evidence` filled from the records.
- The worksheet's Evidence column: `<kind>: <verdict> — <summary text>`.
- `record()` returns `kind: evidence` with its tool call and model call.
- The run dump and Excel export carry them.
- The replay manifest gains `evidence: [[ID, verdict]]`.

**Flags:** a `none` calculation that names missing facts adds "evidence skipped: missing <fact IDs>" to the line's `flags`. A `contradicted` result (simulator only) adds "evidence contradicts this line: <summary>".

**Overrides:** none on evidence records in Phase 4. The engineer reads them; the known-limits list gains "evidence can't be accepted or rejected".

### 4.5 Demo plant facts for the calculation (Cowork), and the final demo run

`cases/demo/williams_geismar.json` gains, each with its source:
- `PROPANE.vapor_pressure_points` and `PROPYLENE.vapor_pressure_points` spanning about 40–95 °C (NIST Chemistry WebBook saturation data, `pressure_kpaa`);
- `operating` temperature rows on the quench-water inlet lines `L-QW-A-IN` and `L-QW-B-IN`, `normal: 85` (CSB p. 10, 185 °F; a line, because a utility can't hold an operating row).

Cowork also writes:
- the block list `cases/demo/williams_geismar.block.txt`;
- the hand-worked fixture `backend/tests/physics/fixtures/example_wg_blocked_in.json` (delivered 2026-10-21), with every interpolation step shown, written **before** the code, like the LOPA examples. N in the video line comes from it.

**Fork (Bhargavi decides before any code):** changing the plant file gives a new plant record ID, and a run reads facts only from its own stored plant record. The current demo run (`run:4e6842d31fbdee3b`) would therefore show `pressure_multiple` honestly "skipped: missing PROPANE.vapor_pressure_points".
- **Recommended:** add the facts, then make **one final demo run** on the new plant record (≈ $1.1 with post steps and evidence, after the grant). It runs every Phase 3 fix (lopa_argument v3, single retry, lead tie-break) from the start, and it becomes the recorded run Phase 7 serves in demo mode, which needs a clean final run anyway.
- Not recommended: a separate property table keyed by chemical name. It would split a chemical's facts across two places.

### 4.6 Simulator: Tennessee Eastman (`simulator/`, last PR, feature date Oct 24)

1. **Gate (Bhargavi's machine, $0, by Oct 23):** install `tennessee-eastman-profbraatz` (pinned, licence checked) and reproduce kill test #1: a cooling-water fault, a high-pressure trip near 1.05 h, reactor temperature falling. If it fails, stop: the simulator becomes "next".
2. **TE plant file** `cases/demo/tennessee_eastman.json` (Cowork): from Downs & Vogel (1993) and the package documentation. Valve fail positions are marked "assumed" (§8).
3. **Fault map** `reference/te_faults.csv` (Cowork): `cause_id, component_id, idv, description, source`. It records which TE disturbance (IDV 1–20) stands for which library cause on which TE component. Loaded outside `ReferenceSet.versions` (P4-9).
4. **Wrapper** `simulator/te.py`: runs the mapped IDV for `te_hours` (4) and returns the variables that left their normal band and the limits crossed, with times. Code sets the verdict: `confirmed` if a limit is crossed; `contradicted` if the deviation's parameter moved the other way (the kill-test #1 pattern); else `none`. Records as `kind: simulation`.
5. **A TE run:** one paid full run, about $0.6–1.0, after the grant, to show it end to end.

### 4.7 Contract (next free tag, v1.8)

- P4-6's choice (`ToolCall` fields or `Agent.evidence`).
- `Evidence` gains `model_call_id: str | None`, `missing_fact_ids: list[str]` and `flags: list[str]`, all defaulted.
- `SupersededRecord.kind` gains `evidence` and `tool_call`.
- The `evidence_added` payload is documented: `{evidence_id, target_id, kind, verdict}`.
- Mock fixtures get one confirmed calculation (with fact IDs), one confirmed precedent (with a URL) and one skipped calculation (`none`, missing fact IDs). The placeholder `example.org` evidence goes.
- Regenerate `contract/openapi.json`, the schemas and `frontend/src/api/types.ts`.

## Not in scope

- No orchestrator or specialist evidence tools (P4-1). `AgentTool` keeps its values; none are offered.
- No change to severity, LOPA, ranking, any analysis or Phase 3 prompt, or any validity rule (P4-2).
- No precedent sources beyond CSB. ARIA and eMARS are "next", stated in the README.
- No overrides on evidence. No DEXPI importer. The frontend is the Phase 5 spec. Hosted Tavily ledger and demo mode are Phase 7.

## Acceptance tests (all $0, written first)

**Calculations**
- `blocked_in_heating` matches the WG hand-worked fixture exactly (relative tolerance 1e-9 before formatting), reporting the lowest multiple and its chemical.
- No extrapolation: a temperature outside a chemical's points → skipped, naming its `vapor_pressure_points`.
- One test per input of each calculation: that fact missing → `none` with `missing_fact_ids` naming it; no default anywhere.
- Below 1.0 → `none` ("below design"), never `contradicted`.
- Reboiler B → `confirmed`, citing `HV-B-SIN.normal_position`, `HV-B-SOUT.normal_position`, `HV-QW-B-IN.locked` and the vapour-pressure points; reboiler A → one card, `none` ("not blocked in"); every isolating valve locked closed → `none` ("heat source locked out").
- Applicability: `more:pressure` and a heated scenario-object equipment get `blocked_in_heating`; `less:flow` with no heated equipment gets nothing.

**Precedent**
- A block term removes a matching index row and a matching Tavily result before the judge sees them.
- A judge answer with an unknown handle or an unsent URL drops that item, logs it, and the rest stand.
- Tavily is imported only under `guideword/tools` (allow-list). A search past `tavily_searches_per_run` is refused and recorded in the ledger.

**Hashing**
- `evidence_top_n`, the other `evidence:` settings and the two new tables leave new run IDs unchanged when changed. D–G and the WG demo run IDs are unchanged.

**The step**
- Replay: a $0 fake run through all nine steps reproduces the evidence records from the model and Tavily fixtures (R45). A missing Tavily fixture fails loudly.
- **Evidence changes nothing else:** shortlist order, tiers, leads, severities, LOPA records and recommendations are byte-identical before and after the evidence step.
- `--evidence` on a finished run keeps its run ID and every earlier record.
- `--rerun-from evidence` supersedes the old evidence, tool calls and judge calls verbatim, through the event log.
- `--no-evidence` → the step records "evidence off" and makes no call.
- Spend: the judge's calls count against the post cap, and R45 spend still matches the call records.

**Reads**
- The shortlist, worksheet, record detail, run dump and Excel export show the evidence. Line flags name skipped facts.

**Simulator** (only if PR 6 lands)
- The cooling-loss IDV reproduces kill test #1's direction (pressure up, temperature down) and its trip time within 10 %.

## Pull requests, in order (the plan may refine)

| # | Branch | What | Depends on |
|---|---|---|---|
| 0 | `phase-4/docs` | P4-1…P4-10 in `docs/decisions.md`; PROJECT.md §5 Step 4 tool table and Step 7, §8, §10 (`precedent_index.csv`, `te_faults.csv`), §11 modules (`evidence`), §23 ("evidence can't be accepted or rejected"); caps.yaml `phase_caps_usd."4"` (the `evidence:` block lands in PR 5 with its config model); this spec and the plan | — |
| 1 | `contract/evidence-v1.8` | §4.7 | 0 |
| 2 | `phase-4/physics` | §4.1, with Cowork's fixture | 1 |
| 3 | `phase-4/precedent-index` | loader, BM25, block terms; Cowork's `precedent_index.csv` | 0 |
| 4 | `phase-4/precedent-judge-prompt` | `precedent_judge/v1`, for Bhargavi's review | 0 |
| 5 | `phase-4/evidence-step` | Tavily in tools with cache and replay; the step; `--evidence`, `--rerun-from evidence`, `--no-evidence`; reads; export | 1–4 |
| 6 | `phase-4/simulator` | §4.6, only after the Oct 23 gate passes | 5 |

PRs 2, 3 and 4 can run in parallel (cloud agent) while the frontend proceeds in its own worktree.

## Live calls and spend (Bhargavi starts each one)

- caps.yaml: `phase_caps_usd."4": 1.50`. The TE run needs the second grant.
- **WG final demo run** (4.5, use `video`, plan Q7): ≈ $1.1 (analysis ≈ $0.85, post ≈ $0.15, evidence ≈ $0.03).
- **D–G `--evidence`:** ≈ $0.02–0.05 each, after the grant. Their plants have few vapour-pressure points, so most calculations will honestly be skipped.
- **TE full run** (PR 6 only): ≈ $0.6–1.0, after the grant.
- **Tavily:** at most 5 searches per run, on the existing key or the Builder Program's Tavily credit.

## Done when

- [ ] P4-1…P4-10 and the 4.5 fork decided and recorded; PROJECT.md updated.
- [ ] Every acceptance test passes; CI green.
- [ ] The WG final demo run has evidence on its top 5 lines, including a `blocked_in_heating` on reboiler B (EA-425B), and a runtime Tavily search in its records (§25).
- [ ] D–G have evidence on their top 5 lines (after the grant), or the README says they don't.
- [ ] Simulator: running on TE with one confirmed result, **or** recorded as "next" on Oct 24 with the reason.
- [ ] Phase 4 spend within its cap; `budget/ledger-g4pre.jsonl` snapshot.

## Who writes what

- **Claude Code:** plan, code, tests, the `precedent_judge/v1` prompt.
- **Bhargavi:** P4-1…P4-10, the 4.5 fork, the prompt review, live runs, the Oct 23 simulator gate, merges.
- **Cowork:** this spec; `reference/precedent_index.csv`; block lists for WG and D–G (plan Q6); WG vapour-pressure points, the quench-water temperature rows and the block list; the hand-worked pressure fixture; the TE plant file and `te_faults.csv`, only if the gate passes. Cowork does not write or review prompts.

## Feature dates (PROJECT.md §15 rule: not working by its date → "next" in the pitch)

- `physics_calc` and precedent search with Tavily, on the WG demo: Oct 23.
- Simulator: gate Oct 23, working Oct 24.
