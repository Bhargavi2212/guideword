# Phase 4 plan — Evidence: calculations, precedent, web research, simulation

Status: approved 2026-10-21 (Bhargavi: "yeah lets go", after Q1–Q16 were answered)

Written 2026-10-21. It covers every item of `specs/phase-4.md`, which is itself a draft and untracked. I read that spec, `CLAUDE.md`, the `PROJECT.md` sections the spec cites (§5 Steps 3, 4 and 7; §8; §9; §10; §11; §13; §15; §20; §23; §25) and the code on `main` at "Merge pull request #86" (Phase 3 complete). No code is written until this plan **and** the spec are approved. The questions below each come with a recommended answer; nothing that depends on one is built before it is answered.

---

## 1. The spec's claims about the code, checked

Every claim in the spec's "What the code has today" section, read against `main`:

| Spec says | Code | Note |
|---|---|---|
| `Evidence` has `kind`, `verdict`, `summary`, `tool_call_id`, `fact_ids`, `sources`, and no `model_call_id` | ✅ exactly | |
| `evidence_added` exists but is not emitted | ✅ (`EMITTED_EVENT_TYPES` lacks it) | |
| `ShortlistItem.evidence` is always `[]`; the worksheet's Evidence column is `None`; `record()` has no evidence kind | ✅ (`review/shortlist.py:156`, `review/worksheet.py:148,181`, `api/live.py`) | The run dump already reads `runs.evidence()` (`api/live.py:205`). |
| Steps, `POST_*` sets, `AFTER_ANALYSIS`, `RERUN_FROM = ("chains", "lopa")`, `SUPERSEDED_TABLES` (4 kinds) | ✅ exactly | |
| `evidence_top_n: 5` is in `run:` and hashed | ✅; D, E, F, G **and** the demo run all store it | So moving it out of the hash leaves their IDs unchanged (rule: the hash covers what a run stores). |
| Adding a table to `ReferenceSet` moves every new run ID | ✅ (`reference/loader.py` puts every table it reads into `versions`) | |
| `tools/record.py` runs only `reactivity_lookup`; the orchestrator offers no evidence tool | ✅ (`orchestrator/tools.py` offers `check_coverage`, `dispatch_specialist`, `reactivity_lookup`, `finish`) | `AgentTool` already has `web_research`, `search_precedent`, `physics_calc` and `run_simulation`. |
| `ToolCall.agent_step_id` required; `ids.tool_call_id(step_id, …)` | ✅ | `ToolCall` also has `source_urls` and `record_ids`, which the spec doesn't mention. Both are useful here. |
| `simulator/` empty | ✅ | |
| Tavily only in `scripts/live_call.py`; the allow-list's comment names `tools/**` for Phase 4; `tavily-python` pinned (0.8.5); `Settings.tavily_api_key` | ✅ | |
| `gateway/replay.py` has no Tavily and no evidence | ✅ | |
| `operating.target_id` must be equipment or line; no TE plant file | ✅ (`schema/validate.py:200`) | Operating units are fixed by parameter (§9: pressure kPa gauge, temperature °C, level % of range), as the spec's `overflow_time` assumes. |
| **Not in the spec:** the precedent evidence ID | `ids.precedent_evidence_id(target, precedent_id=…, url=…)` already exists, matching `PROJECT.md` §11: **one record per incident** (`ev:<target>:precedent:<index id or h(url)>`) | The spec says **one precedent record per line**, with several URLs in `sources`. **Conflict C5.** |
| **Not in the spec:** `routing_config` and `run.max_tokens` are hashed | Adding the job `precedent_judge` to `routing.yaml`, or its `max_tokens`, **moves every new run's ID** | The spec's hashing test would miss it. **Conflict C8.** |
| **Not in the spec:** `test_no_precedent_index_yet` | `backend/tests/reference/test_reference_tables.py:73` pins that `reference/precedent_index.csv` does **not** exist | It is renamed or replaced in PR 3. |
| **WG plant facts today** | PROPANE and PROPYLENE have only `boiling_point_c`; no `vapor_pressure_points`. EA-425A and B have `design_pressure_kpa: 2068` and heat sources via `L-QW-A-IN` and `L-QW-B-IN`; no line has an operating row; `volume_m3`, `heat_duty_kw` and densities are absent | The pressure calculation (`blocked_in_heating` after Q13) needs Cowork's 4.5 facts; `overflow_time` and `heat_up_rate` will honestly skip on WG. |

### A finding the spec needs to know before approval (checked at $0, read-only)

On today's demo run (`run:4e6842d31fbdee3b`), the top 5 confirmed or also-found lines and the questions of their findings are:

| Rank | Line | Its findings' questions |
|---|---|---|
| 1 | the HV-B-SIN chain (the video's opening card) | `env:C4-HEAVIES:air`, `env:C4-HEAVIES:air` |
| 2 | hypothesis #3 | `env:C4-HEAVIES:air` |
| 3 | hypothesis #4 | `env:C4-HEAVIES:air` |
| 4 | chain | `env:C4-HEAVIES:air`, `m:S-L-QW-B-IN:less:flow` |
| 5 | chain | `m:S-EA-425A:less:flow`, **`m:S-EA-425A:more:pressure`** |

With the spec's rule (4.1: applicability by the question ID `m:<section>:more:pressure`), **only line 5 (reboiler A) gets a `pressure_multiple`**. The opening card and every reboiler-B line get none, although S-EA-425B has 3 findings on `more:pressure`. So the video beat ("Heating the blocked-in reboiler…") and the done-when line "a `pressure_multiple` on reboiler B's pressure line" are **not met by the spec's rule on today's run**. A new final run may rank differently, but nothing guarantees it. **Question Q1.**

---

## 2. Conflicts with `PROJECT.md` and `CLAUDE.md` (quoted; not resolved by me)

| # | Where | Says | Spec says | Question |
|---|---|---|---|---|
| C1 | `PROJECT.md` §5 Step 4, tool table; Step 7 "(gathered by the orchestrator)"; worked example ("calls `search_precedent` and `physics_calc`") | the four evidence tools are orchestrator tools | P4-1: a fixed code step; the orchestrator gets none | Approve P4-1, and PR 0 rewrites those passages (as Phase 3 did for chains and LOPA)? |
| C2 | `PROJECT.md` §5 Step 4, specialists | "may take **at most 2 tool steps per batch** (`reactivity_lookup`, `web_research`)" | "No orchestrator or specialist evidence tools" | The code never gave specialists `web_research` (`AGENT_TOOLS` is chemistry → `reactivity_lookup` only). PR 0 fixes the text to match the code? |
| C3 | `PROJECT.md` §8 and §11 tool table: precedent sources "CSB, ARIA, eMARS and other national reports" | | CSB only; ARIA and eMARS are "next" | PR 0 updates §8, the tool table and §23? |
| C4 | `PROJECT.md` §10: `precedent_index.csv` with **id, title, date, location, hazard_type, summary, url, source** (headers listed, but never frozen in code: Phase 0 deferred it) | | `precedents.csv` with id, title, date, country, company, location, chemicals, equipment_types, mechanism_keywords, summary, url, source | `CLAUDE.md` §2: a reference-table format change is stop-and-ask. Which name and columns? |
| C5 | `PROJECT.md` §11 IDs: `ev:<…>:precedent:<precedent index id, or h(url) for a web result>`; code `ids.precedent_evidence_id` | one evidence record **per incident** | "one `precedent` record per line", with the accepted incidents in `sources` | Which? |
| C6 | `CLAUDE.md` §5: "The precedent index is built by a script from report metadata; you do not read the reports to build it." | | Cowork writes it from CSB's investigation pages | Who builds it: a script, or Cowork by hand? Either way, Claude Code never reads its rows. |
| C7 | `PROJECT.md` §5 Step 4 code guards: "During benchmark runs, Tavily and the precedent index **block the case under test** by name, company, location and date." | | P4-7: benchmark runs **skip** evidence | Skipping is stricter. PR 0 rewrites the guard to "benchmark runs skip the evidence step; demo and dev runs use a block list"? |
| C8 | `PROJECT.md` §11 Run ID hashes `routing config` and `caps`; connector/v2 Q5 took post-step **prompts and four caps** out | | P4-9: evidence settings not hashed | The spec doesn't cover the **job** `precedent_judge` (routing) or its **`max_tokens`** (`run:` block), both hashed today. The same is true of the four Phase 3 jobs. |
| C9 | `PROJECT.md` §15: Phase 4 "Oct 19–22"; feature date "Simulator running Tennessee Eastman faults: Oct 22" | | Oct 22–24; simulator gate Oct 23, working Oct 24 | PR 0 updates §15 to the spec's dates? Note that Phase 6 (benchmark, G3 on Oct 24) overlaps. |
| C10 | `CLAUDE.md` §5: never "open or summarise accident investigation reports … unless the task explicitly names a dev case (D–H) or the demo plants" | | D–G evidence and the WG demo cite CSB reports | It's allowed for D–G and the demo plants. **D–H are themselves CSB cases**, though, so the index holds their own reports: without a block list, a D–G line could be "confirmed" by its own accident (C11). |
| C11 | Spec P4-7: block list for **demo plants** only | | | D–G need block lists too: their own CSB reports would otherwise match. |

---

## 3. Decisions P4-1…P4-10: my reading and recommendations

| # | Spec's recommendation | My view |
|---|---|---|
| P4-1 | Evidence is a fixed code step after `recommendations`; no orchestrator evidence tools | **Agree.** Same reasoning as P3-1; it also keeps every orchestrator request, and so every analysis replay, unchanged. |
| P4-2 | Evidence never changes rank, tier, lead, severity, LOPA or recommendations | **Agree.** The test compares those fields only. The line's `evidence` list and its flags do change, by design (§7). |
| P4-3 | Top `evidence_top_n` confirmed and also-found lines (chains included), from stored records, with the run's lead rule, without overrides | **Agree.** It is built on `review.shortlist.shortlist_lines` with no overrides applied, and `lead_prefers_own_section` read from the run. |
| P4-4 | `physics_calc` pure code; applicability by guideword and parameter; missing fact → `none` with fact IDs | **Agree on pure code and no defaults. See Q1 on applicability**, which as written misses the demo's reboiler lines. |
| P4-5 | Local index, then Tavily; Super judge per line, by handle | **Agree.** The judge sees candidates as `K1…` (connector/v2 lesson) and states the count and handles, never "batch" (target-handles lesson). |
| P4-6 | (a) optional `agent_step_id` plus a `step` field on `ToolCall`, or (b) one `AgentStep` per evidence line with `Agent.evidence` | **Recommend (b).** It keeps the frozen tool-call ID form `tc:<agent step id>:…` (§11). `AgentTool` already has `physics_calc`, `search_precedent`, `web_research` and `run_simulation`. `record()` already joins tool calls to their step. The run timeline shows the evidence steps like any agent step. The cost is one enum value, `Agent.evidence`, in contract v1.8. |
| P4-7 | Benchmark runs skip evidence (`--no-evidence`); demo block list | **Agree, with Q4.** Make "off" the default for any plant outside `cases/demo/`, so a held-out run can never reach the index or the web by a forgotten flag. Add block lists for D–G (C11). |
| P4-8 | `web_research` and `search_precedent` are one routine, `kind: precedent` | **Agree.** |
| P4-9 | An `evidence:` caps block, not hashed; the new tables outside `ReferenceSet.versions`, hashes on the pass event | **Agree, and extend it (Q3):** post-step **jobs** and their **`max_tokens`** also leave the hash. |
| P4-10 | Simulator TE only, last PR, gated by Oct 23 | **Agree.** The new dependency is approved only if the gate passes and the licence is confirmed; until then it is not added to `requirements.in`. |

---

## 4. Questions for Bhargavi (each with a recommendation)

| # | Question | Recommendation |
|---|---|---|
| Q1 | **Applicability of `pressure_multiple`.** By question ID alone (spec), the opening HV-B-SIN chain and every reboiler-B line get no calculation on today's run (§1). | Keep the spec's rule (`m:<section>:more:pressure`), **and add one code rule**: a line whose **scenario objects** (section objects ∪ failing components, the set LOPA candidates use) include equipment with `design_pressure_kpa` **and** a `heat_sources` entry also gets `pressure_multiple` for that equipment. It is labelled "the scenario's equipment, if heated by its heat source", so the card says it is a property of the equipment, not a claim about this cause. It is deterministic, no model is involved, and it reaches the HV-B-SIN chain (its links' failing components include EA-425B). If you'd rather keep the spec's rule only, the done-when line changes to "a `pressure_multiple` on the reboiler A line, if it is in the top 5". |
| Q2 | **Precedent records: one per line, or one per incident?** (C5) | One per **accepted incident**, as §11 and `precedent_evidence_id` already define: each card links one incident, with its own judge reason. A line with none gets one `ev:<target>:precedent:none` record. |
| Q3 | **Post-step jobs and `max_tokens` in the hash** (C8). | Leave `POST_JOBS` (now with `precedent_judge`) out of a new run's stored `routing_config`, and the post jobs' `max_tokens` out of its stored `caps`. They are recorded on `run_extended` with the prompts, as connector/v2 Q5 did. Stored runs keep their IDs (the hash covers what they store). |
| Q4 | **Evidence default** (P4-7). | **On** only for plants under `cases/demo/` (as `--out-dir` already decides) and by `extend_run.py --evidence`. **Off** otherwise, recorded as "evidence off" in the step's summary. `--no-evidence` stays as an explicit switch. |
| Q5 | **Index name, columns and builder** (C4, C6). | Name `reference/precedent_index.csv` (the name `PROJECT.md` and the existing test use), with the spec's richer columns. §10 is updated in PR 0, and the test's absence check becomes a header check. Built **by Cowork from CSB's public investigation list and its published summaries**, with a `source` on every row, as the spec says; `CLAUDE.md` §5's "built by a script" line is updated to say so. Claude Code writes only the loader and tests with **synthetic** rows, and never opens the real file's rows. |
| Q6 | **Block lists for D–G** (C10, C11). | Yes. Cowork writes `cases/dev/case_<x>.block.txt` from each case's **public CSB report name** (the company, place and incident as CSB titles it), never from `cases/dev/keys/`. They're needed before any D–G `--evidence` run. |
| Q7 | **The 4.5 fork: a new final demo run** (≈ $1.1). | Agree with the spec: add Cowork's facts, then one final run on the new plant record, after the grant. It carries every Phase 3 fix from the start and becomes Phase 7's recorded run. Run it with **`use: demo_recording`** (a `CLAUDE.md` use) once the allowances are re-set: development has $1.03 left, below $1.1. *(Superseded: see Answers, use `video`.)* |
| Q8 | **Budget after the grant.** The spec's live list is the WG run ≈ $1.1, D–G ≈ $0.2 and TE ≈ $0.6–1.0, up to $2.3, against a proposed `phase_caps_usd."4": 1.50`. | Set `"4": 1.50` now (enough for WG + D–G). When the grant arrives, raise `GLOBAL_BUDGET_USD` and re-split the use allowances in `caps.yaml` (a test checks they sum), and raise phase 4 only if the TE gate passes. |
| Q9 | **Spec dates vs `PROJECT.md` §15** (C9), and the Phase 6 overlap. | PR 0 sets §15 to the spec's dates. Phase 6's held-out runs must start only on code where evidence is off for non-demo plants (Q4) or before PR 5 merges. I'll note it in the PR 5 description. |
| Q11 | **G1: the opening card gets `none` under Q1's rule** (it names no isolation valve, though its LOPA cites HV-B-SIN closed). | Add one code-only `confirmed` condition: the plant facts show the equipment isolated in its normal state (an isolation valve with `normal_position: closed`), citing that fact, as the LOPA inlet-valve rule does. Reboiler A's in-service line stays `none`. |
| Q12 | **G14: the chemical named, and the video line.** | The video line takes the chemical and N from the record, so it may say propylene. Cowork's propylene points stop at its critical point. A content chemical without points gets a flag. |
| Q13 | **G15: `pressure_multiple`'s label.** | *"Pressure check: if <equipment> reaches <medium>'s <temperature> °C with no way out, <chemical> vapour pressure is about N× design"*. |
| Q14 | **G19: Tavily spend on a hosted deploy.** | Write through `ledger_for`, in both environments, now. |
| Q15 | **G21: guarantee the runtime Tavily call.** | One `web_research` per evidence-on run on the top line, as well as the fallback. This changes P4-5. |
| Q16 | **G22: API runs' phase.** | `API_RUN_PHASE = "4"`. |
| Q17 | **Block terms: substring or whole word?** (Cowork's files) | Whole words, so `PCA` doesn't drop "upcast". *(Answered: see Answers.)* |
| Q10 | **More hand-worked fixtures?** The spec has Cowork's fixture for the pressure calculation only. | Cowork also hand-works one small `overflow_time` and one `heat_up_rate` example on the §9 example plant (synthetic facts allowed there). Every number is then checked against a hand calculation, like LOPA examples 1 and 2. |

### Answers (Bhargavi, 2026-10-21)

| # | Answer |
|---|---|
| Q1 | **Yes, with code-set verdicts.** A new calculation, `blocked_in_heating`, on the equipment of a line's scenario objects that has `design_pressure_kpa` and a `heat_sources` entry. Label: *"Blocked-in heating check: if <equipment> is isolated while <heat source> stays on, <chemical> vapour pressure reaches about N× design"*. **`confirmed` only if the line's failing components or fact links include one of that equipment's isolation valves**: a valve on a line whose `from_id` or `to_id` is the equipment, or an inlet valve of a relief device protecting it. Otherwise `none`, labelled "applies only if <equipment> is isolated". The spec's `more:pressure` rule (`pressure_multiple`) keeps its own verdicts. Tests cover both, including reboiler A's in-service line getting `none`. *The verdict rule in this answer is replaced by Q11, and `pressure_multiple` is dropped by Q13.* |
| Q2 | As recommended: one precedent record per accepted incident, plus `ev:<target>:precedent:none` when none is accepted. |
| Q3 | As recommended: the post-step jobs and their `max_tokens` leave a new run's stored, hashed inputs, recorded on `run_extended`. |
| Q4 | **Changed.** Evidence is **off when the run's use is `benchmark` or `test_5`**, and on otherwise, recorded in the step summary. `--no-evidence` still forces it off. Test: a benchmark-use run makes no evidence call. Reason: API-uploaded plants must get evidence, for §25's runtime Tavily rule. |
| Q5 | As recommended: `reference/precedent_index.csv` with the spec's columns, built by Cowork from CSB's public list; `CLAUDE.md` §5 updated; Claude Code never opens its rows. |
| Q6 | As recommended: block lists for D–G from each case's public CSB report name, before any D–G `--evidence` run. |
| Q7 | **Changed.** The final demo run uses **`video`** ($2.00 left, laptop), not `demo_recording` (hosted). **Checked in code:** the gateway refuses a call whose use belongs to another environment (`gateway/client.py`: "use … belongs to the hosted allowance, not laptop"), so a laptop run under a hosted use is refused before sending. No test covers it yet, so PR 5 adds one (G9). |
| Q8 | As recommended: `"4": 1.50` now; re-split the use allowances and `GLOBAL_BUDGET_USD` with the grant. |
| Q9 | As recommended: §15 takes the spec's dates. With Q4, Phase 6's held-out runs (use `benchmark`) never run evidence. |
| Q10 | As recommended: Cowork hand-works one `overflow_time` and one `heat_up_rate` example on the §9 example plant. |
| P4-6 | **Option (b):** one `AgentStep` per evidence line, `Agent.evidence`. |
| Q11 | **Yes, with a stricter rule; it replaces Q1's verdict rule.** `blocked_in_heating` is `confirmed` only when, from plant facts: **(1)** every process-side line to or from the equipment (excluding lines carrying any of its `heat_sources[].isolating_valve_ids`) has a valve with `normal_position: closed`; **(2)** at least one heat source's isolating valves are not all `locked: true` and closed; **(3)** the multiple is ≥ 1.0. The record cites every fact used (`fact_ids`). Otherwise `none`, with the failed condition named in the summary ("not blocked in", "heat source locked out", "below design"). Tests: WG reboiler B → `confirmed`, citing `HV-B-SIN.normal_position`, `HV-B-SOUT.normal_position`, `HV-QW-B-IN.locked` and the vapour-pressure points; reboiler A → `none` ("not blocked in"); a heat source with every isolating valve locked closed → `none` ("heat source locked out"). |
| G2–G12 | Accepted as written. |
| Q12 | **The lowest multiple.** Report the **lowest** multiple among content chemicals with vapour-pressure points, labelled *"at least N× design (lowest of the listed chemicals)"*. Name the chemicals with no points (*"no data: <ids>; bound covers listed chemicals only"*). PR 0 fixes the spec's "highest". The video takes N and the chemical from the record. Cowork's propylene points stop below its critical point. |
| Q13 | **Drop `pressure_multiple`.** `blocked_in_heating` is the one pressure calculation, applied to `more:pressure` lines on the equipment **and** by Q1's scenario-object rule, with Q11's three-condition verdict. Update the spec, `PROJECT.md` §5's "multiple of design pressure" wording, the evidence ID builder and the tests. Reboiler A's line gets one card: `none` ("not blocked in"). |
| Q14 | As recommended: Tavily spend goes through `ledger_for`, laptop or hosted. |
| Q15 | As recommended, and it changes P4-5: **one Tavily search on the top line always, judged alongside the index candidates** (one judge call), under the same block list. Other lines keep the spec's fallback. |
| Q16 | As recommended: `API_RUN_PHASE = "4"`. |
| Q17 | **Whole-word matching**, case-insensitive: a term matches as a phrase on word boundaries at both ends (`\b<term>\b`). My EA-425 example was wrong: `\bEA-425\b` doesn't match "EA-425B". Cowork fixed the data instead, so the WG list now names `EA-425A` and `EA-425B`, and every block file's header says "whole word or phrase". The WG list is re-copied into PR 2b and the D–H lists go into PR 5, byte for byte. Tests: "EA-425B" is blocked by its own term; "upcast" is not blocked by `PCA`; "PCA mill" is. |

### Gaps found on the reread (each with a recommendation)

| # | Gap | Recommendation | Lands in |
|---|---|---|---|
| G1 | **Q1's verdict rule gives the opening HV-B-SIN chain `none`.** Its links are two `env:C4-HEAVIES:air` findings (failing on EA-425A, EA-425B and LOC-OLEFINS-UNIT) and the location facts `LOC-OLEFINS-UNIT.description`, `.occupied`, `EA-425A.location_id` and `EA-425B.location_id`. None of them is an isolation valve, although the chain's LOPA says "no credit — inlet valve HV-B-SIN closed", which code read from the plant file (HV-B-SIN `normal_position: closed`). Checked at $0. So the card would read "applies only if EA-425B is isolated". | **Answered by Q11** (the stricter rule). Checked against the plant file at $0: EA-425B's process-side lines are `L-B-SIN` (HV-B-SIN closed) and `L-B-SOUT` (HV-B-SOUT closed); `L-QW-B-IN` and `L-QW-B-OUT` carry its heat source's valves, so they're excluded; HV-QW-B-IN and HV-QW-B-OUT are `locked: false`. So (1) and (2) hold for reboiler B. For reboiler A, HV-A-SIN and HV-A-SOUT are open, so (1) fails: "not blocked in". The verdict depends on the equipment only, so every top line with EA-425B among its scenario objects, the HV-B-SIN chain included, gets the same confirmed record. | 2 |
| G2 | **Evidence IDs collide on a line with two equipment items.** `ev:<target>:calculation:<calculation name>` (`PROJECT.md` §11) gives the HV-B-SIN chain one ID for both EA-425A's and EA-425B's `blocked_in_heating`. | **The calculation name carries the equipment:** `ev:<target>:calculation:<calculation>-<equipment id>`, for example `blocked_in_heating-EA-425B`. Plant IDs never contain `:`, so the form stays parseable. The builder `ids.calculation_evidence_id(target, calculation, equipment_id)` goes in contract v1.8, and §11 is updated in PR 0. | 0, 1 |
| G3 | **Physical constants in logic.** The calculations need 101.325 kPa (gauge ↔ absolute) and 273.15 K. `CLAUDE.md` §3 bans hard-coded **thresholds, frequencies and matrices**; these are unit constants, not plant or reference values. | Named module constants in `tools/physics.py` (`ATMOSPHERE_KPA`, `KELVIN_OFFSET`), each with a one-line source comment; recorded in decisions. The confirm thresholds (60 minutes, ≥ 1.0× design) come from the `evidence:` caps block. The 1.0 is part of the definition ("at or above design"), recorded too. | 0, 2 |
| G4 | **Where an extended run reads `evidence_top_n`.** Stored runs (D–G, the demo run) hold it in `run.caps`; new runs won't once it moves to `evidence:`. `post_setting` reads `run.caps` then `config.caps.run`. | `evidence_setting(run, config, key)`: the run's stored caps first (G8 of Phase 3), else `config.caps.evidence`. The source is recorded on the pass event, as `post_settings` does. | 5 |
| G5 | **Tool and judge failures.** The spec doesn't say what a failed Tavily search or a failed judge call does. | Like Phase 3's G3: the run goes on. A failed judge call (invalid twice, cut off, error) gives the line `ev:<target>:precedent:none`, flagged "precedent judge failed (<call ID>)". A Tavily error gives a `ToolCall` with `refused_reason` and the same `none`, flagged "web search failed". Only a budget refusal stops the run. | 5 |
| G6 | **"Refused and recorded in the ledger"** (spec acceptance). A refused search costs nothing, and ledger lines record spend. | A search past `tavily_searches_per_run` is **refused before sending** and recorded as a `ToolCall` with `refused_reason` and an event, **not** as a ledger line. A sent search writes its ledger line (`kind: tavily`, `searches: 1`). The acceptance test checks both. | 5 |
| G7 | **`run_case.py` rejects `--use video`.** Its `USES` are `development` and `test_5` only. | Add `video` to `run_case.py`'s `USES` (and `extend_run.py`'s, for re-running evidence on the final demo run). It is a laptop use, so the gateway's environment check stays the guard. | 5 |
| G8 | **The demo plant file is read by Phase 3 tests.** Example 2 (`backend/tests/lopa/fixtures/example_2.json`) and `test_demo_plant.py` load `cases/demo/williams_geismar.json`. Cowork's 4.5 additions (vapour-pressure points; operating rows on `L-QW-A-IN` and `L-QW-B-IN`) must keep them passing. | Cowork's plant change lands in its own PR (2b, below), with the full suite run. Example 2's candidates and credits don't read those fields, so they should be unchanged; the PR proves it. Bhargavi ticks each new fact's source, as `CLAUDE.md` §10 asks. | 2b |
| G9 | **No test for the cross-environment refusal** (Q7). *Correction (2026-10-22): one exists, `backend/tests/gateway/test_gateway.py::test_use_of_the_other_environment_is_refused`; PR 5a adds the same check for web searches.* | `test_a_laptop_run_under_a_hosted_use_is_refused` (gateway, fake transport, zero sends). | 5 |
| G10 | **The judge prompt's count wording.** precedent_judge/v1 needs the target-handles lessons: no "batch", the count and handles stated, made-up examples. | Stated in PR 4 (already listed), plus a guard test: no prompt body or user message says "batch". The existing test covers the three Phase 3 prompts, and it is extended to `precedent_judge`. | 4, 5 |
| G11 | **The frontend worktree reads `types.ts`.** Contract v1.8 changes `Evidence` and `Agent`. | PR 1 regenerates `frontend/src/api/types.ts` and runs the frontend's lint, typecheck and tests, as v1.5–v1.7 did. Phase 5 renders the cards. | 1 |
| G12 | **The `evidence_added` payload and the worksheet text** need one source of wording. | The card's text and the worksheet's Evidence column both come from `review/display.py` (`calc_text`, and the judge reason as stored), like `gap_text`. One test checks they're equal for the same record. | 5 |

### Gaps found on the second reread (code read again, 2026-10-21)

| # | Gap | Recommendation | Lands in |
|---|---|---|---|
| G13 | **Q11's edge cases aren't pinned.** (a) Equipment with no process-side line. (b) A heat source with no `isolating_valve_ids`. (c) Several conditions failing at once. (d) Missing facts for (3), which would wrongly read "below design". (e) Which facts a `none` cites. | (a) No process-side line → "not blocked in": the facts don't show it blocked in. (b) A heat source that can't be isolated isn't locked out, so (2) holds, citing `<equipment>.heat_sources`. (c) Every condition is checked, and the summary names each failed one in the order 1, 2, 3. (d) A missing input for (3) gives `none` with `missing_fact_ids` and the "evidence skipped" flag, never "below design". (e) A `none` cites the facts that failed it, e.g. `HV-A-SIN.normal_position`. "Locked closed" means `locked: true` **and** `normal_position: closed`. (2) cites the first valve, in `isolating_valve_ids` order, that isn't locked closed: its `.locked` fact if unlocked, else its `.normal_position`. | 2 |
| G14 | **Which chemical the multiple names, and the video line.** Like `pressure_multiple`, `blocked_in_heating` reports the content chemical with the **highest** multiple. Propylene is more volatile than propane, so with both sets of points the record will most likely name **propylene**, but the spec's video line says "the propane's vapour pressure". Also, propylene's critical temperature is about 91.6 °C, so its saturation points can't reach the spec's "about 40–95 °C". 85 °C is still bracketed. A content chemical with no points (C4-HEAVIES) is silently ignored by the spec. | **Answered by Q12:** the lowest multiple, "at least N×", with "no data: <ids>" for chemicals without points. | 2, 2b |
| G15 | **Two cards that read as contradicting each other on one line.** Today's line 5 has `m:S-EA-425A:more:pressure`, so it gets the spec's `pressure_multiple` on EA-425A, which is `confirmed` if ≥ 1.0. The same line's `blocked_in_heating` on EA-425A is `none` ("not blocked in"). | **Answered by Q13:** `pressure_multiple` is dropped; one card per equipment. | 2 |
| G16 | **Re-runs and retries would collide with evidence IDs.** `--rerun-from chains`, `--rerun-from lopa` and `--retry-failed` all re-run the steps after them, so they re-run `evidence` too, but `RERUN_SUPERSEDES` and `_retry` don't supersede evidence. The new evidence would have the **same IDs** as the old. Also, `supersede_post_records`'s default `kinds` is every `SUPERSEDED_TABLES` entry, so once `tool_call` and `agent_step` join it, a retry would supersede the **orchestrator's and specialists'** tool calls and steps. | Every re-run and retry supersedes the evidence pass: `evidence`, the agent steps with agent `evidence`, **their** tool calls, and `precedent_judge` calls. `RERUN_SUPERSEDES["lopa"]` gains them, and `"chains"` and `_retry` get them through `POST_JOBS` and the kinds. `tool_call` and `agent_step` rows are always filtered to agent `evidence`. Tests: `test_a_retry_never_supersedes_an_orchestrator_or_specialist_step_or_tool_call`; `test_rerun_from_lopa_and_chains_supersede_the_old_evidence`. | 5 |
| G17 | **`--evidence` on D–G and today's demo run.** `extend()` refuses an already-extended run ("already has its chains step done"), and those runs are extended. | A new mode: `extend(…, evidence_only=True)` sets the step to `evidence` and emits `run_extended` with `"step": "evidence"`. It is refused if the current pass already ran evidence (use `--rerun-from evidence`), or if the run isn't finished. Tested in `test_extend_evidence_keeps_the_run_id_and_every_earlier_record`, plus `test_evidence_twice_is_refused`. | 5 |
| G18 | **Tavily in the cache and the replay.** `ResponseCache.put` takes a model `Reply`. `export_replay` collects keys from the run's **model calls**, so a Tavily response would never be exported. | `ResponseCache.put_tool` and `get_tool` store the search JSON in the same `response_cache` table (`model_id: "tavily"`); no schema change. `export_replay` also collects keys from the run's `web_research` tool calls, runs the same secrets check on them, and lists them in the manifest. | 5 |
| G19 | **The hosted ledger.** The spec says the hosted Tavily ledger is Phase 7's, but `HostedLedger` (the `spend_ledger` table) and `ledger_for` already exist. With Q4, an API run on a hosted deploy would search. | **Q14.** `tools/web.py` writes through `ledger_for(settings)`, like the gateway, in both environments, tested with each. Phase 7 then has nothing to add for Tavily spend. | 5 |
| G20 | **How the step finds a plant's block list.** A run stores its plant record, not the file path. | It looks up `<plant_id>.block.txt` under `cases/demo/` and `cases/dev/` (the names match: `williams_geismar`, `case_d`…). With none, the pass event records `"block_list": null`, as for an uploaded plant. The list's hash goes on the pass event. | 5 |
| G21 | **§25's runtime Tavily call isn't guaranteed.** Tavily runs only when no local candidate is accepted, so if the index has a match on every top line, the final run makes no Tavily call, and the "Best Use of Tavily" prize needs one (`PROJECT.md` §1). The plan's done-when note left this as "can". | **Q15.** `web_research` also runs once per evidence-on run, on the top line, even if a local candidate was accepted. Its results are block-filtered and judged the same way. That's one search and one more judge call (≈ $0.006), within the 5-search cap. | 5 |
| G22 | **API runs charge phase "3".** `API_RUN_PHASE = "3"` (`api/app.py`), and phase 3 has $0.26 left. With Q4, API runs add evidence calls. | **Q16.** PR 5 sets `API_RUN_PHASE = "4"` and tests it. | 5 |
| G23 | **Evidence IDs.** `ids.evidence_id(target, kind, key)` already exists, and `_part` forbids `:` in the key. | `calculation_evidence_id` is a thin wrapper over it (key `<calculation>-<equipment id>`), and the `none` precedent is `evidence_id(target, "precedent", "none")`. The index loader rejects a row whose `id` is `none`. `target_id` is the line's `ShortlistItem.target_id`: the lead finding, or the chain. | 1, 3 |
| G24 | **Stale text from before the answers.** Q4 changes P4-7 ("benchmark runs skip evidence") and C7's guard text. The acceptance map still names `test_evidence_off_for_non_demo_plants_records_it_and_makes_no_call`. | PR 0 writes P4-7 and the §5 Step 4 guard as Q4 states it (off for use `benchmark` or `test_5`). The map uses the new test names. | 0 |

### Cowork's Phase 4 files (delivered 2026-10-21, `D:\Hackathon\guideword\cowork-phase4\`)

Copied **unchanged** to the target path in the PR its README names. `reference/precedent_index.csv` follows separately (PR 3).

| File | Target | PR |
|---|---|---|
| `williams_geismar.json` (PROPANE points 30–95 °C, PROPYLENE 30–90 °C, both NIST; C4-HEAVIES no points, stated in provenance; `normal: 85` on `L-QW-A-IN` and `L-QW-B-IN`) | `cases/demo/williams_geismar.json` (replaces it) | 2b |
| `williams_geismar.block.txt` | `cases/demo/` | 2b |
| `example_wg_blocked_in.json` | `backend/tests/physics/fixtures/` | 2 |
| `example_overflow_heatup.json` (both Q10 examples in one file) | `backend/tests/physics/fixtures/` | 2 |
| `case_d.block.txt` … `case_h.block.txt` | `cases/dev/` | 5 |

**What they pin (the code follows the fixtures):**
- **The threshold rule** (`example_overflow_heatup.json`): a value within a relative 1e-9 of a threshold **counts as equal** to it. The level-80 % overflow variant evaluates to 59.999999999999986 minutes in floating point, which is **not** below 60, so it's `none`. One helper, `physics.compare(value, threshold)`, does every threshold comparison: `< 60` minutes for both time checks, and `≥ 1.0` for the multiple (so a multiple within 1e-9 of 1.0 is at design and `confirmed`). Recorded in decisions. Tests: `test_a_value_within_1e_9_of_a_threshold_counts_as_equal`, and the fixture's boundary variant.
- **Citations** (`example_wg_blocked_in.json`, which amends G13):
  - Condition (2) cites the `.locked` fact of **every** isolating valve of the heat source it checked, e.g. `HV-QW-B-IN.locked` and `HV-QW-B-OUT.locked`.
  - Condition (1)'s `none` cites **every** open valve on the failing lines, e.g. `HV-A-SIN.normal_position` and `HV-A-SOUT.normal_position`.
  - `fact_ids` also include the `vapor_pressure_points` of every chemical that had points (PROPANE and PROPYLENE), not only the lowest.
- **Flags** (`example_wg_blocked_in.json`): the temperature source is **always** flagged ("heating-medium temperature from normal (no design_max)", or the `design_max` form), as spec 4.1 says ("flagged which"). The plan's "flagged only when design max used" is corrected. The lower-bound flag and "no data: C4-HEAVIES; bound covers listed chemicals only" also appear.
- **The numbers:** PROPANE gives 1.6125604448742747× and PROPYLENE 1.9233438104448743× at 85 °C, so the record reports **PROPANE, "at least 1.6× design"**, and the video's N is 1.6.
- **Order:** the WG fixture reads the plant file with the Phase 4 facts, so **PR 2b lands before PR 2**.

**Q17 (answered):** block terms match as whole words or phrases, case-insensitive (`\b<term>\b`, the term escaped), on every field and the URL.

---

## 5. Per item

### PR 0 — `phase-4/docs` (docs and config only)

- **Files:**
  - `specs/phase-4.md` (Status approved);
  - this plan;
  - `docs/decisions.md`: P4-1…P4-10, the 4.5 fork and Q1–Q16 as answered.
- **`PROJECT.md`:**
  - §5 Step 3 item 7: "a `physics_calc` multiple-of-design-pressure" becomes the `blocked_in_heating` check, on `more:pressure` lines and the lines whose scenario objects include heated equipment (Q1, Q13); §5's tool table row "pressure as a multiple of design limit" becomes "blocked-in heating pressure (lowest multiple of design)" (Q12, Q13);
  - §5 Step 4: the tool table loses the four evidence tools (C1); the specialists' tools text (C2); the benchmark block guard (C7);
  - §5 Step 7: "a fixed code step after recommendations";
  - §8 and the tool table: CSB only for now (C3);
  - §10: `precedent_index.csv` with its columns, and `te_faults.csv` (C4);
  - §11: the `evidence` module row; the Evidence record with `model_call_id`, `missing_fact_ids` and `flags`; run steps with `evidence`; Agents gain `evidence` (P4-6b);
  - §15: dates (C9);
  - §23: "evidence can't be accepted or rejected".
- **`CLAUDE.md` §5:** the precedent-index line (Q5). That's a `CLAUDE.md` change, so it's Bhargavi's to approve here.
- **`PROJECT.md` §11 IDs:** the calculation evidence ID carries the equipment (G2).
- **`docs/decisions.md`:** the physical constants and the 1.0× definition (G3); Q4, Q7, Q11 and Q12–Q16 as answered.
- **The spec:**
  - P4-7 and the done-when line as answered (Q4, Q11, G24);
  - §4.1: the `pressure_multiple` row is replaced by `blocked_in_heating` (applicability per Q1 and Q13, verdict per Q11, the **lowest** multiple per Q12, "never `contradicted`" and the lower-bound flag kept); the acceptance tests renamed to match;
  - P4-5 and §4.3 step 5: one Tavily search on the top line always, judged with the index candidates (Q15);
  - the hosted Tavily ledger is no longer Phase 7's (Q14);
  - the video line takes the chemical and N from the record (Q12).
- **`config/caps.yaml`:** `phase_caps_usd."4": 1.50` only. The `evidence:` block lands in **PR 5**, with its config model: `CapsConfig` forbids unknown keys, so the block can't come before the model. PR 5 also moves `run.evidence_top_n` into it and adds it to the hash-free list, so no run ID moves twice.
- **Tests:** the existing config tests (the new phase cap loads); no new code.

### PR 1 — `contract/evidence-v1.8`

- **`schema/records.py`:**
  - `Evidence.model_call_id: str | None = None`, `missing_fact_ids: list[FactId] = []` and `flags: list[str] = []`;
  - `Evidence.id` checked against `ev:` (as other records are).
- **`schema/enums.py`:** `Agent.EVIDENCE = "evidence"` (P4-6b).
- **`schema/ids.py`:** `calculation_evidence_id(target, calculation, equipment_id)` → `ev:<target>:calculation:<calculation>-<equipment id>`, a thin wrapper over `evidence_id` (G2, G23). `calculation` is checked against the three names, `blocked_in_heating`, `overflow_time` and `heat_up_rate` (Q13). `precedent_evidence_id` gains the `none` form.
- **`api/models.py`:** `SupersededRecord.kind` gains `evidence`, `tool_call` and `agent_step`.
- **The `evidence_added` payload** is documented in `PROJECT.md` §11: `{evidence_id, target_id, kind, verdict}`.
- **Mock fixtures:** the `example.org` placeholder goes, and the mocks get one confirmed calculation (with fact IDs), one confirmed precedent (with a URL), one skipped calculation (`none`, `missing_fact_ids`) and the precedent `none` record (Q2). The `ShortlistItem.evidence` and worksheet Evidence fields are filled in the mocks.
- **Regenerate:** schemas, `openapi.json` and `frontend/src/api/types.ts`. Tag `contract-v1.8` after merge.
- **Tests first:**
  - `test_evidence_new_fields_default_for_older_records`;
  - `test_evidence_id_must_be_an_ev_id`;
  - `test_agent_evidence_is_an_agent`;
  - `test_superseded_kinds_include_evidence_tool_call_and_agent_step`;
  - `test_mock_evidence_shows_each_kind_and_verdict` (and no `example.org`);
  - `test_calculation_evidence_ids_carry_the_equipment_and_round_trip` (G2);
  - the frontend's lint, typecheck and tests on the regenerated types (G11).

### PR 2 — `phase-4/physics` (`backend/guideword/tools/physics.py`)

- **Order:** after PR 2b. Cowork's fixtures `backend/tests/physics/fixtures/example_wg_blocked_in.json` and `example_overflow_heatup.json` land first, committed as delivered. It hand-works `blocked_in_heating` for EA-425B: each chemical's interpolation, the **lowest** multiple, and the three conditions with their fact IDs (Q11–Q13). So do Q10's two fixtures.
- **Functions (pure; no I/O):**
  - `blocked_in_heating(equipment, plant)`, `overflow_time(equipment, plant, caps)` and `heat_up_rate(equipment, plant, caps)`, each returning `CalcResult{name, value, unit, fact_ids, missing_fact_ids, flags, detail}`. There is no `pressure_multiple` (Q13).
  - `applicable(line, …)`: `blocked_in_heating` on (a) the equipment of a `m:<section>:more:pressure` finding's section, and (b) each scenario-object equipment item (section objects ∪ failing components of the line's findings) that has `design_pressure_kpa` and a `heat_sources` entry (Q1). Each equipment item gets **one** card per line, whichever rule reached it. On (a), equipment lacking either fact gets `none` naming the missing fact; (b) never reaches it. `overflow_time` on `more:level`, `heat_up_rate` on `more:temperature`.
  - `blocked_in_heating`'s verdict depends on the equipment only, so it is computed once per equipment and reused on every line. Label (Q1, Q12): *"Blocked-in heating check: if <equipment> is isolated while <heat source> stays on, vapour pressure reaches at least N× design (lowest of the listed chemicals: <chemical>)"*.
  - **The multiple** (Q12): computed for each content chemical with `vapor_pressure_points`; the **lowest** is reported, naming its chemical. Chemicals without points are named: *"no data: <ids>; bound covers listed chemicals only"*. If no content chemical has points, it's `none` with their `vapor_pressure_points` as missing facts.
    - **(1) Blocked in:** the process-side lines are those whose `from_id` or `to_id` is the equipment, minus any line whose `components` hold a valve in one of its `heat_sources[].isolating_valve_ids`. Each must have a valve with `normal_position: closed`. Cites each closed valve's `.normal_position`.
    - **(2) Heat source not locked out:** at least one heat source has an isolating valve that isn't locked closed (`locked: true` and `normal_position: closed`). Cites that valve's `.locked` or `.normal_position` (G13).
    - **(3) At or above design:** the multiple ≥ 1.0. Cites `<equipment>.design_pressure_kpa`, the heat-source line's temperature fact (e.g. `L-QW-B-IN.operating.temperature.normal`) and `<chemical>.vapor_pressure_points`.
    - **All three hold → `confirmed`**, citing every fact used. Otherwise **`none`**, with each failed condition named in order ("not blocked in", "heat source locked out", "below design") and its facts cited. A missing input gives `missing_fact_ids` instead (G13).
  - Physical constants as named module constants with a source comment (G3).
  - Evidence IDs carry the equipment: `<calculation>-<equipment id>` (G2).
- **Clausius–Clapeyron:** `ln P` linear in `1/T`, with T in K = °C + 273.15, between the two bracketing points (sorted by temperature). At a point exactly it returns that point; outside the range it skips, naming `<chemical>.vapor_pressure_points`; with fewer than 2 points it skips. Gauge = kPaa − 101.325.
- **The heating-medium temperature:** for each heat source with a `via_line_id` that isn't locked out (Q11 (2)), that line's operating temperature row, `design_max` if set, else `normal`, always flagged which (Cowork's fixture); the highest of those is used, naming its heat source in the label.
- **Verdict:**
  - `blocked_in_heating`: Q11's three conditions → `confirmed`, else `none`. Always flagged "pure-component vapour pressure; liquid-full thermal expansion not modelled; real pressure can be higher".
  - `overflow_time` and `heat_up_rate`: below `evidence.overflow_confirm_minutes` and `heat_up_confirm_minutes` respectively → `confirmed`, else `none`.
  - Never `contradicted`.
- **The display text:** `review/display.py` gains `calc_text(result)`, 2 significant figures ("about 1.6× design", "about 18 minutes"). The stored values are never rounded.
- **Tests first:**
  - `test_blocked_in_heating_matches_the_hand_worked_wg_fixture_exactly` (rel 1e-9, every step the fixture shows, the lowest chemical named);
  - `test_interpolation_is_exact_at_a_point_and_never_extrapolates`;
  - `test_fewer_than_two_points_skips`;
  - one test per input of each calculation (`test_<calc>_without_<fact>_names_it`): each missing fact gives `none` with that fact ID, with no default anywhere;
  - `test_below_one_is_none_never_contradicted`;
  - `test_the_lowest_multiple_is_reported_and_its_chemical_named` (Q12);
  - `test_chemicals_without_points_are_named_no_data` (Q12);
  - `test_no_content_chemical_with_points_is_none_naming_them` (Q12);
  - `test_a_locked_out_heat_source_temperature_is_not_used`;
  - `test_the_design_max_is_used_when_set_and_flagged`;
  - `test_the_highest_heat_source_temperature_is_used`;
  - `test_the_lowest_density_and_heat_capacity_are_used_and_named`;
  - `test_applicability_is_by_question_id_and_scenario_objects` (`more:pressure` and a heated scenario-object equipment get `blocked_in_heating`; `less:flow` with no heated equipment gets nothing);
  - `test_one_card_per_equipment_when_both_rules_reach_it` (Q13);
  - `test_wg_reboiler_a_line_gets_one_card_none_not_blocked_in` (Q13, on today's line 5's findings);
  - `test_more_pressure_equipment_without_heat_sources_names_the_missing_fact`;
  - `test_wg_reboiler_b_blocked_in_heating_is_confirmed_and_cites_every_fact` (Q11: `HV-B-SIN.normal_position`, `HV-B-SOUT.normal_position`, `HV-QW-B-IN.locked`, the vapour-pressure points, plus `EA-425B.design_pressure_kpa` and `L-QW-B-IN.operating.temperature.normal`);
  - `test_wg_reboiler_a_is_none_not_blocked_in` (Q11; cites `HV-A-SIN.normal_position`);
  - `test_every_isolating_valve_locked_closed_is_none_heat_source_locked_out` (Q11);
  - `test_below_design_is_none_below_design` (Q11);
  - `test_heat_source_lines_are_excluded_from_the_blocked_in_check` (Q11 (1));
  - `test_no_process_side_line_is_not_blocked_in` and `test_a_heat_source_with_no_isolating_valve_is_not_locked_out` (G13);
  - `test_every_failed_condition_is_named_in_order` (G13);
  - `test_a_missing_input_is_skipped_never_below_design` (G13);
  - `test_the_verdict_is_the_same_on_every_line_with_that_equipment`;
  - `test_two_equipment_on_one_line_get_two_calculation_ids` (G2);
  - `test_overflow_time_matches_its_hand_example` and `test_heat_up_rate_matches_its_hand_example` (Q10);
  - `test_calc_text_is_two_significant_figures`;
  - an AST guard that `tools/physics.py` imports no gateway and no network client.
- **Dependencies:** none (the `math` module only).

### PR 2b — `phase-4/demo-plant-facts` (Cowork's data; G8)

- **Files:** `cases/demo/williams_geismar.json` gains PROPANE and PROPYLENE `vapor_pressure_points` (about 40–95 °C, NIST, `pressure_kpaa`; propylene's stop below its critical point, about 91.6 °C, Q12) and operating temperature rows on `L-QW-A-IN` and `L-QW-B-IN` (`normal: 85`, CSB p. 10). Each has its source in `provenance`, and Bhargavi ticks each one (`CLAUDE.md` §10).
- **Also:** the block list `cases/demo/williams_geismar.block.txt`.
- **Tests:** the full suite, with nothing changed. Example 2, `test_demo_plant.py` and the connector's demo fact-list test must pass unchanged. A new `test_the_demo_plant_has_bracketing_vapour_pressure_points_for_the_quench_temperature`.

### PR 3 — `phase-4/precedent-index`

- **Data:** Cowork's `reference/precedent_index.csv` (Q5). Claude Code never opens its rows.
- **Loader:** `reference/precedents.py` loads it **outside** `ReferenceSet` and returns `PrecedentIndex{rows, version}`:
  - checks the frozen header, unique IDs (none may be `none`, G23), a non-empty `url` (https) and `source` on every row, and LF and UTF-8;
  - `chemicals`, `equipment_types` and `mechanism_keywords` are `;`-separated.
- **Search:** `tools/precedent.py`:
  - `query_for(line, plant)` builds the query by code (the lead finding's cause words, or each finding link's for a chain; the content chemicals' names; the section's equipment type; guideword and parameter);
  - `blocked(text, terms)`: each term, escaped, matches as a whole word or phrase on word boundaries at both ends (`\b<term>\b`), case-insensitive, on every field and the URL (Q17);
  - `bm25(rows, query, k)` is about 50 lines, with no dependency, deterministic, ties broken by row ID.
- **Block lists:** `cases/demo/williams_geismar.block.txt` and `cases/dev/case_<x>.block.txt` (Cowork). A loader reads one term per line, with `#` comments.
- **Tests first** (synthetic index rows in `tests/reference/fixtures/`):
  - `test_index_header_is_frozen`;
  - `test_every_index_row_has_a_url_and_a_source`;
  - `test_index_ids_are_unique`;
  - `test_the_index_is_outside_reference_versions` (loading it leaves `ReferenceSet.versions` unchanged);
  - `test_bm25_ranks_by_terms_and_breaks_ties_by_id`;
  - `test_a_block_term_removes_a_row_by_any_field_or_url`;
  - `test_ea_425b_is_blocked_by_its_own_term` (Q17);
  - `test_upcast_is_not_blocked_by_pca` and `test_pca_mill_is_blocked_by_pca` (Q17);
  - `test_a_phrase_term_matches_across_its_words_only_whole` (e.g. `propylene fractionator`);
  - `test_the_query_is_built_from_the_line_only` (no model);
  - `test_no_precedent_index_yet` becomes `test_precedent_index_loads_when_present`.

### PR 4 — `phase-4/precedent-judge-prompt` (Bhargavi reviews; Cowork does not)

- **The file:** `prompts/precedent_judge/v1.md`. Its placeholders:
  - `{{line}}`: the cause, consequence and components in words;
  - `{{candidates}}`: `K1…`, each with title, date, location and summary, **all as data**;
  - `{{count}}` and `{{handles}}`.
- **What it asks:** per candidate, `same_mechanism` yes/no and a reason, by handle only. Never a URL, an ID or a number, and never the word "batch".
- **Routing** is not changed in this PR. PR 5 routes it.
- **Before merge:** Bhargavi's review and `prompt_leak_check.py` ($0).
- **Check:** the draft's examples use made-up handles, with no real incident, ID or plant name. No "batch" or group label anywhere (G10).

### PR 5 — `phase-4/evidence-step`

**Split into three PRs, landed in order (2026-10-22; nothing in their content changes):**
- **5a `phase-4/tavily`:** `tools/web.py` (`WebSearch`, cache by exact query, one ledger line per sent search through the environment's ledger, the environment and phase refusals, `TavilySearch`, `ReplaySearch`, `FakeSearch`), `ResponseCache.put_tool` and `get_tool`, the replay export of the run's searches, and the allow-list.
- **5b `phase-4/evidence-step`:** the `evidence:` caps block, the step and its wiring, the hash exclusions (Q3), supersession (G16), `--evidence` (G17), `--no-evidence`, the scripts (G7), `API_RUN_PHASE` (Q16), and the D–H block lists.
- **5c `phase-4/evidence-reads`:** the shortlist, worksheet, record detail, run dump, xlsx and replay manifest.

- **Tavily (`tools/web.py`):**
  - It is the only importer of `tavily` outside `scripts/live_call.py`, so `test_http_allowlist.py` gains `tavily: backend/guideword/tools/**`. That's a stop-and-ask change, approved by the spec.
  - The client is injected; tests use a fake. `search(query, run_budget)` checks the per-run cap `evidence.tavily_searches_per_run`, counted from the run's `web_research` tool calls in the current pass, and writes a ledger line (`kind: tavily`, `searches: 1`, `cost_usd: 0`, phase, use).
  - **Cache:** results are stored in `response_cache` through `ResponseCache.put_tool` and `get_tool`, with key `h("tavily", query, max_results)`, `model_id: "tavily"` and `prompt_version: "search/v1"`. No new table (G18).
  - **Replay:** `export_replay` collects the keys of the run's `web_research` tool calls, runs the secrets check on them, writes them and lists them in the manifest. `ReplayTavily` serves them or raises `ReplayMiss` (G18).
  - **Ledger:** written through `ledger_for(settings)`, laptop or hosted (Q14).
  - **The runtime call** (Q15): on the top line, one Tavily search always; its block-filtered results join the BM25 candidates in **one** judge call. Other lines search only as the fallback.
- **The step (`evidence/step.py`):** `EvidenceStepper`, one line per call, writing before it returns.
  - **Line choice:** P4-3, from `shortlist_lines` with no overrides and the run's lead rule.
  - **Per line:** one `AgentStep` (`agent: evidence`, `tool: physics_calc`, `search_precedent` or `web_research`, with the arguments and a reason). Then the calculations, then precedent: block → BM25 (and, on the top line, a Tavily search, block-filtered, Q15) → judge (`precedent_judge`, Super) → on other lines, if nothing is accepted, one Tavily search → block → judge.
  - **Records:** `Evidence` records (Q2), each `evidence_added`; one `ToolCall` per tool run (`source_urls` filled); the judge's `ModelCall` (`model_call_id` on the precedent records).
  - **Flags:** "evidence skipped: missing <fact IDs>"; a `contradicted` result (simulator only) adds "evidence contradicts this line: <summary>".
  - **When it ends:** the step summary lists the lines done, and the run goes to `ranked`.
  - **When it's off** (Q4 as answered): when the gateway's `use` is `benchmark` or `test_5`, or `--no-evidence` was given, it writes `{"evidence": "off", "reason": …}` in the step summary and moves on, with no call.
  - **Failures** (G5): a judge or Tavily failure leaves the line `precedent:none`, flagged; only a budget refusal stops the run.
  - **Settings** (G4): `evidence_setting(run, config, key)` reads the run's stored caps first, else `config.caps.evidence`.
- **Wiring:**
  - `recommend/step.py` `NEXT` becomes `evidence`.
  - `AFTER_ANALYSIS`, `POST_STEPS`, `steppers_for`, `POST_JOBS` (`precedent_judge`) and `POST_PROMPTS` (`precedent_judge`) gain it.
  - `routing.yaml`: `precedent_judge: super` and the prompt `precedent_judge: v1`. `caps.yaml`: `max_tokens.precedent_judge`.
  - `config/caps.yaml` gains the `evidence:` block (`evidence_top_n: 5`, `precedent_candidates: 5`, `tavily_searches_per_run: 5`, `tavily_max_results: 5`, `overflow_confirm_minutes: 60`, `heat_up_confirm_minutes: 60`, `te_hours: 4`) with its `EvidenceCaps` model, and `run.evidence_top_n` moves there (P4-9).
  - Q3's hash exclusions.
  - `post_pass()` records the evidence settings, the block list (looked up by `plant_id`, or `null`; G20) and its hash, the index hash and on/off.
  - **Supersession** (G16): `RERUN_SUPERSEDES["lopa"]`, `"chains"` and `_retry` also supersede the evidence pass. `tool_call` and `agent_step` rows are always filtered to agent `evidence`.
  - `api/app.py`: `API_RUN_PHASE = "4"` (Q16).
- **Scripts** (G7): `run_case.py` and `extend_run.py` accept `--use video`.
- **Extension:**
  - `extend_run.py --evidence` adds the step to a finished run whose last pass had none, with the same run ID. It is a new `extend` mode, since `extend()` refuses an already-extended run today; running evidence twice is refused (G17).
  - `--rerun-from evidence` supersedes `evidence`, its `tool_call`s and `agent_step`s (agent `evidence` only) and the `precedent_judge` calls.
  - `SUPERSEDED_TABLES` gains `evidence`, `tool_call` and `agent_step`, each filtered to the evidence pass's own records.
- **Reads:**
  - `ShortlistItem.evidence` is filled from the records.
  - **Worksheet** Evidence column: `<kind>: <verdict> — <text>` (the text from `calc_text` or the judge reason), joined; folded members marked "(scenario)" as for the LOPA gap.
  - `record()` handles `kind: evidence` (parents: the target, the tool call, the model call) and `agent_step` records.
  - The run dump and Excel export carry the evidence.
  - The replay manifest gains `evidence: [[id, verdict]]`.
- **Tests first:**
  - `test_tavily_is_imported_only_under_tools`;
  - `test_a_search_past_the_per_run_cap_is_refused_and_recorded` (a refused tool call and an event, no ledger line; a sent search writes `kind: tavily`; G6);
  - `test_a_failed_judge_or_search_leaves_the_line_precedent_none_flagged` (G5);
  - `test_evidence_top_n_is_read_from_the_runs_stored_caps_first` (G4);
  - `test_a_laptop_run_under_a_hosted_use_is_refused` (Q7, G9);
  - `test_run_case_and_extend_run_accept_use_video` (G7);
  - `test_the_card_and_worksheet_evidence_text_are_the_same` (G12);
  - `test_tavily_results_are_cached_and_a_missing_replay_fixture_fails_loudly`;
  - `test_a_block_term_removes_a_tavily_result_before_the_judge`;
  - `test_the_judge_sees_handles_and_its_count_never_ids_or_batch`;
  - `test_an_unknown_handle_or_unsent_url_drops_that_item_and_the_rest_stand`;
  - `test_evidence_lines_are_the_top_n_confirmed_and_also_found_from_stored_records`;
  - `test_evidence_changes_no_order_tier_lead_severity_lopa_or_recommendation` (compares those fields byte-for-byte, before and after);
  - `test_each_evidence_record_names_its_tool_call_step_and_model_call`;
  - `test_full_nine_step_fake_run_replays_identically` (R45, including Tavily);
  - `test_extend_evidence_keeps_the_run_id_and_every_earlier_record`;
  - `test_rerun_from_evidence_supersedes_only_the_evidence_pass`;
  - `test_a_benchmark_use_run_makes_no_evidence_call` (Q4: `benchmark` and `test_5`; recorded in the step summary);
  - `test_no_evidence_forces_it_off_for_any_use`;
  - `test_an_api_run_gets_evidence` (Q4: an uploaded plant on use `development`);
  - `test_judge_spend_counts_against_the_post_cap_and_r45_holds`;
  - `test_evidence_settings_jobs_and_tables_leave_new_run_ids_unchanged` (Q3, P4-9);
  - `test_d_to_g_and_the_demo_run_ids_are_unchanged` (from stored inputs; the demo run's inputs join the fixture);
  - `test_the_shortlist_worksheet_record_dump_and_xlsx_show_evidence`;
  - `test_line_flags_name_skipped_facts`;
  - `test_no_overrides_on_evidence_records` (a 422);
  - `test_a_retry_never_supersedes_an_orchestrator_or_specialist_step_or_tool_call` (G16);
  - `test_rerun_from_lopa_and_chains_supersede_the_old_evidence` (G16);
  - `test_evidence_twice_is_refused` (G17);
  - `test_tavily_entries_are_exported_with_the_secrets_check` (G18);
  - `test_tavily_spend_is_written_to_the_laptop_and_hosted_ledgers` (Q14);
  - `test_the_top_line_always_searches_and_judges_web_and_index_candidates_together` (Q15: one judge call, the block list applied to both);
  - `test_the_block_list_is_found_by_plant_id_or_recorded_as_none` (G20);
  - `test_api_runs_charge_phase_4` (Q16).
- **Dependencies:** none new (`tavily-python` is already pinned).

### PR 6 — `phase-4/simulator` (only if the Oct 23 gate passes)

- **The gate is on Bhargavi's machine, at $0:** install `tennessee-eastman-profbraatz` in a scratch venv, confirm the licence, and reproduce kill test #1 (the cooling-water IDV; a high-pressure trip at about 1.05 h, temperature falling). If it fails, the simulator becomes "next" on Oct 24, recorded in decisions; PR 6 is not built.
- **If it passes:**
  - the package is pinned in `requirements.in`, with its reason;
  - Cowork writes `cases/demo/tennessee_eastman.json` (valve fail positions "assumed") and `reference/te_faults.csv`, loaded outside `ReferenceSet`;
  - `simulator/te.py` runs the mapped IDV for `evidence.te_hours` and returns the band crossings and limits crossed, with times;
  - code sets the verdict: confirmed, contradicted (the parameter moved the other way) or none;
  - the evidence step adds `run_simulation` where a line's cause and component map to an IDV.
- **Tests first:**
  - `test_the_fault_map_header_and_sources`;
  - `test_the_cooling_loss_idv_reproduces_kill_test_1_direction_and_trip_time_within_10_percent` (marked slow, $0, local);
  - `test_the_simulation_verdict_rules`;
  - `test_no_simulation_without_a_mapped_idv`.

---

## 6. Order

1. **PR 0** (docs and config) and **PR 1** (contract v1.8). PR 1 right after PR 0, so the frontend worktree can regenerate its types.
2. **PRs 2b, 3 and 4 in parallel, then PR 2:** the demo plant facts (Cowork's data, G8), the index (needs Cowork's CSV), and the judge prompt (Bhargavi's review); physics after 2b, because its WG fixture reads the new plant file.
3. **PR 5** after PRs 1–4 and 2b.
4. **The live runs:** the WG final demo run (Q7), then D–G `--evidence`, after the grant.
5. **PR 6** only after the Oct 23 gate.
6. **Then:** `budget/ledger-g4pre.jsonl` and the spec's done-when ticks.

---

## 7. What evidence touches, and what it must not

- **Never touched:** rank, tier, lead, severity, LOPA records and recommendations. The evidence step only adds records, events, agent steps, tool calls and judge calls, and a line's flags and `evidence` list.
- **Never offered:** no orchestrator or specialist tool is added; `AgentTool` keeps its values.
- **Never edited:** no prompt from Phases 2–3 changes.
- **Never hashed:** no evidence setting or new table in a new run's ID (P4-9, Q3).

---

## 8. Not doing

- No ARIA or eMARS sources (C3). No overrides on evidence. No DEXPI importer. No frontend: Phase 5 renders the v1.8 fields.
- No hosted Tavily ledger and no demo mode (Phase 7).
- No change to the benchmark harness beyond the evidence default (Q4).
- Claude Code never reads `precedent_index.csv` rows, Tavily results or CSB reports. The exception is checking a live run's evidence records for D–G or the demo plants, which `CLAUDE.md` §5 allows.

---

## 9. Live calls and spend (Bhargavi starts each one)

| Step | Use | Expected |
|---|---|---|
| `prompt_leak_check.py` on `precedent_judge/v1` | — | $0 |
| Simulator gate (local) | — | $0 |
| WG final demo run (Q7) | **`video`** (laptop; $2.00 left; Q7 as answered) | about $1.1: analysis $0.85, post $0.15, evidence about $0.03 (5 judge calls on Super), plus at most 5 Tavily searches |
| D–G `--evidence` | development | about $0.02–0.05 each, after the grant |
| TE full run (PR 6 only) | development | about $0.6–1.0, after the grant |

The phase cap is `"4": 1.50`: the WG run (≈ $1.1, `video`) plus D–G (≈ $0.2, `development`, $1.03 left) fit. The TE run waits for the grant and the re-split (Q8).

---

## 10. Acceptance map (every spec acceptance line → where it is proved)

| Spec acceptance line | Test | PR |
|---|---|---|
| The pressure calculation matches the WG fixture (rel 1e-9; `blocked_in_heating`, Q13) | `test_blocked_in_heating_matches_the_hand_worked_wg_fixture_exactly` | 2 |
| No extrapolation | `test_interpolation_is_exact_at_a_point_and_never_extrapolates` | 2 |
| One test per input, `none` with the missing fact | `test_<calc>_without_<fact>_names_it` (one each) | 2 |
| Below 1.0 → `none`, never `contradicted` | `test_below_one_is_none_never_contradicted` | 2 |
| Applicability by question ID (and Q1's scenario-object rule) | `test_applicability_is_by_question_id_and_scenario_objects`, `test_one_card_per_equipment_when_both_rules_reach_it` | 2 |
| A block term removes an index row and a Tavily result | `test_a_block_term_removes_a_row_by_any_field_or_url`, `test_a_block_term_removes_a_tavily_result_before_the_judge` | 3, 5 |
| Unknown handle or unsent URL dropped, logged | `test_an_unknown_handle_or_unsent_url_drops_that_item_and_the_rest_stand` | 5 |
| Tavily only under `tools`; cap refused and recorded | `test_tavily_is_imported_only_under_tools`, `test_a_search_past_the_per_run_cap_is_refused_and_recorded` | 5 |
| Evidence settings and tables leave run IDs unchanged; D–G and WG IDs unchanged | `test_evidence_settings_jobs_and_tables_leave_new_run_ids_unchanged`, `test_d_to_g_and_the_demo_run_ids_are_unchanged`, `test_the_index_is_outside_reference_versions` | 3, 5 |
| Replay through nine steps; a missing Tavily fixture fails | `test_full_nine_step_fake_run_replays_identically`, `test_tavily_results_are_cached_and_a_missing_replay_fixture_fails_loudly` | 5 |
| Evidence changes nothing else | `test_evidence_changes_no_order_tier_lead_severity_lopa_or_recommendation` | 5 |
| `--evidence` keeps the run ID and records | `test_extend_evidence_keeps_the_run_id_and_every_earlier_record` | 5 |
| `--rerun-from evidence` supersedes verbatim | `test_rerun_from_evidence_supersedes_only_the_evidence_pass` | 5 |
| `--no-evidence` → "evidence off", no call | `test_no_evidence_forces_it_off_for_any_use`, `test_a_benchmark_use_run_makes_no_evidence_call` | 5 |
| Judge spend under the post cap; R45 | `test_judge_spend_counts_against_the_post_cap_and_r45_holds` | 5 |
| Reads show evidence; flags name skipped facts | `test_the_shortlist_worksheet_record_dump_and_xlsx_show_evidence`, `test_line_flags_name_skipped_facts` | 5 |
| Simulator reproduces kill test #1 within 10 % | `test_the_cooling_loss_idv_reproduces_kill_test_1_direction_and_trip_time_within_10_percent` | 6 |

### Done-when lines and what they need
- **"P4-1…P4-10 and the 4.5 fork decided; `PROJECT.md` updated":** PR 0.
- **"WG final run has evidence on its top 5, including a `pressure_multiple` on reboiler B's pressure line, and a runtime Tavily search":** with Q1 and Q11 as answered, this is met as a **`confirmed` `blocked_in_heating` on EA-425B**, on every top line that has reboiler B among its scenario objects (the HV-B-SIN chain included), provided the **lowest** multiple is ≥ 1.0 on Cowork's facts (Q12). If it is below 1.0, the card is an honest `none` ("below design"), and the video line changes. PR 0 changes the done-when wording to `blocked_in_heating`. It needs Q7 (`video`). Q15 guarantees the runtime Tavily call on the top line. I'll confirm both on the final run's records.
- **"D–G have evidence on their top 5 (after the grant), or the README says they don't":** needs Q6 first.
- **"Simulator: working, or 'next' on Oct 24":** the PR 6 gate.
- **"Spend within the cap; `ledger-g4pre.jsonl`":** after the live runs.

## 11. Who writes what
- **Claude Code:** this plan, PRs 0–6 code and tests, the `precedent_judge/v1` draft.
- **Bhargavi:**
  - Q12–Q16 and the spec's approval;
  - the prompt review;
  - the simulator gate;
  - the live runs and the grant re-split;
  - merges.
- **Cowork:**
  - `precedent_index.csv`;
  - WG vapour-pressure points and the quench-water temperature rows;
  - the block lists (WG and D–G, Q6);
  - the WG blocked-in fixture and the overflow and heat-up fixture (delivered 2026-10-21);
  - the TE plant file and `te_faults.csv`, only if the gate passes.
