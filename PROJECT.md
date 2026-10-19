# Guideword

Guideword prepares a HAZOP study before the meeting. Code builds every question a HAZOP should ask about a plant; a Nemotron Ultra orchestrator agent runs six specialist agents and a set of tools to answer them, finds the few findings that matter, proves each one with evidence, ranks them by how far short the existing protection falls (LOPA), and shows a coverage report proving nothing was skipped. The engineer decides everything. It is measured on real industrial accidents it has never seen.

Entry for the **Nebius × NVIDIA Global AI Hackathon**, track **Best Apps and Agents**. Submission target: **Oct 29, 2026** (deadline Oct 30, 10:00 am PT).

---

## 1. The problem

Every chemical, refining and pharmaceutical plant must run a hazard analysis before startup, after major changes and at least every five years (OSHA PSM in the US; HAZOP method per IEC 61882). In a HAZOP, a team of 5–8 engineers walks every section of the plant through every guideword (No, More, Less, Reverse, Other than…) for every parameter (flow, pressure, temperature, level…), and records causes, consequences, safeguards and actions in a worksheet. It takes days to weeks, most rows end in "no issue", and the team is tired by the time it reaches the rows that matter.

Hazards still get missed. US Chemical Safety Board (CSB) investigations repeatedly find a hazard review was done and missed the cause. Common misses: chemicals that react when mixed, lines with no flow where material builds up, start-up and shutdown steps, maintenance work near flammables, and combinations of two normal-looking conditions. Example: at Williams Geismar (2013) a reboiler isolated from its relief valve was heated; the plant's own reviews missed it three times; two people died.

AI HAZOP tools exist (Uptime AI, Gordium, Kenexis, Kairos, Salus). None publishes measured accuracy, and research shows LLM worksheets look similar to expert ones while only 19–37% of scenarios are valid. Practitioners say they will not adopt without proof.

**Guideword's answer:** guaranteed coverage (code builds every question), judgment with reasons (Nemotron), ranking by protection gap (LOPA), evidence on every top finding, and a published benchmark on real accidents.

## 2. Users

- **Primary:** the engineer preparing a HAZOP (facilitator or plant process safety engineer). Called "the engineer" below.
- **Secondary:** the review team, who run the meeting from Guideword's shortlist.

## 3. What Guideword is not

- Not a replacement for the HAZOP team or meeting.
- Not a certified safety tool. It never approves anything.
- Never connected to real equipment or live plant data.
- Does not read P&ID images.

---

## 4. Hackathon constraints (from the official rules)

- Must run on **Nebius Token Factory** with at least one **NVIDIA open model** (Nemotron). Calls through other providers do not count.
- Submission: working demo URL usable by judges until judging ends (Dec 15); public repo with an open-source licence visible in the About section; README with setup and a section on how Nemotron and Token Factory were used; project description; public YouTube video under 3 minutes naming Nebius and Nemotron out loud; feedback on Token Factory, AI Cloud and each NVIDIA model used.
- Judging: pass/fail fit check, then four equally weighted criteria scored 1–5: **Technological Implementation, Design, Potential Impact, Quality of the Idea**. Judges may judge from the video and description alone.
- Track guidance: Ultra for serious reasoning, Nano or Super for fast everyday calls. Multi-step autonomous workflows that chain tools stand out.
- Prizes targeted: overall (Grand $20k / 2nd $10k / 3rd $6k), Best Use of Tavily ($3k, needs a runtime Tavily call), Most Valuable Feedback ($100). Each project can win one overall award, or one track award plus one bonus award.
- Judging Dec 1–15, 2026. Winners announced around Jan 11, 2027.

---

## 5. How a run works (end to end)

### Step 1 — Plant input
The engineer uploads a **plant file** (JSON, format in §9). It is validated on load. Missing facts are flagged before anything runs. Every fact carries its source (data sheet, CSB report page, drawing, or "assumed").

### Step 2 — Section split (hybrid)
1. **Rules** draw the first cut: one section per equipment item, of every type (pumps and compressors included); lines split at control valves, pumps, compressors and heat exchangers; **a line with a non-empty `no_flow` gets its own flagged section**; every procedure and planned job becomes a section.
2. **Nemotron Super** reviews the cut and suggests splits or merges where the design intent changes (phase change, new temperature range, new chemical entering, start-up-only line), each with a reason. It writes a one-line purpose for each section. **It can never merge away a flagged no-flow section.** This call has its own cap (`section_suggest_cap_usd` in `config/caps.yaml`) and is logged to the ledger like any other call.
3. **The engineer confirms**: accepts, rejects or edits each suggestion, renames sections, adds sections that regroup existing plant objects (a new procedure or job means uploading a new plant file). Nothing proceeds until confirmed.

Sections belong to the **plant**, not the run. The plant moves through `uploaded → sections_proposed → sections_confirmed`. A run starts from a snapshot of the plant's confirmed sections.

### Step 3 — Question list (complete by construction)
Code builds a numbered list of every question. Nothing on it can be deleted.

1. **Guideword × parameter matrix**, filtered by section type through the applicability matrix (e.g. a pipe gets No/More/Less/Reverse flow and Other-than composition; a tank gets High/Low level, High pressure, Vacuum, High/Low temperature; a reactor adds reaction too fast/slow and loss of mixing). Equipment and line sections get matrix questions; **no-flow line sections get both the pipe matrix questions and their `nf:` question**. Procedure sections and planned-work sections get no matrix questions.
2. **Every chemical pair** on site: n(n−1)/2 pair questions for n chemicals (10 chemicals → 45 pairs), plus a separate list of 3n environment questions (each chemical with water, air and heat). The coverage report counts the two lists separately.
3. **Every no-flow line** (a line with a non-empty `no_flow`): what accumulates, what is missing there (e.g. inhibitor).
4. **Every procedure step × Skipped / Wrong / Too early / Too late / Out of order** (guidewords `skipped`, `wrong`, `early`, `late`, `out_of_order`; `out_of_order` covers sequence). The `procedure` rows of the applicability table supply only this guideword list.
5. **Every planned job × what is within reach** (flammables, live lines, overlapping jobs, isolation). "Within reach" of a job means: its listed `equipment_ids`; its listed `line_ids`; every equipment item in its location; every line whose `from_id` or `to_id` is in its location (an endpoint in the location, or the location itself); every relief device whose `discharge.location_id` is its location (the target is the relief device); and every other planned job at the same location whose time window overlaps. Windows overlap when they touch or cross; a missing `start` or `end`, or a time-zone mismatch between the two jobs, counts as overlapping. A job without a location shares a location with no other job. A job with nothing within reach gets one question `work:<job>:<job>`. Planned-work sections get only these `work:` questions.
6. **Dust and ignition** questions for every equipment item of type `solids_handler` or `dryer`, plus any equipment whose `contents` include a chemical with `combustible_dust: true`.
7. **Every relief device × where it discharges** (people, ignition sources, other equipment). Overpressure is the other common PHA oversight (AIChE CEP, July 2025); it has no separate question. Instead, every `m:<section>:more:pressure` finding in the top N gets a `physics_calc` multiple-of-design-pressure in its evidence when the plant facts allow it.

Nemotron may **add plant-specific questions** (tagged "added by AI") and **mark questions not credible with a reason** (the question stays; the engineer can disagree). The engineer may **add questions** to a run (`POST /runs/{id}/questions`, origin `engineer`, status open): in a running run the orchestrator treats them like any open question; in a finished run they stay open until the engineer answers them with the override action `answer`. The question list is what the coverage report counts.

### Step 3b — Whole-plant pass (`plant_screen`, R50)
Before any dispatch, one Ultra call reads the confirmed plant record (as data), the cause library the plant can support (R46) and the question kinds, and proposes up to `plant_screen_max_hypotheses` ranked hypotheses: mechanism, component and chemical IDs, cause, consequence and a reason each. Code validates every ID and the failing-component mapping (R46); bad hypotheses are dropped and logged. Each hypothesis is linked by code, once, to the questions on its components, chemicals and the equipment and valves of its steps and jobs. It steers dispatch (the orchestrator may dispatch linked questions first) and the final tiers (Step 6); it never deletes or answers a question.

### Step 4 — The agent runs the analysis (agent drives, code guards)
After the engineer confirms the sections, **an orchestrator agent (Nemotron Ultra, tool calling) runs the whole analysis** to the end. It dispatches six **specialist agents**, researches and gathers evidence, deciding at each step what to do next. Code decides what it is allowed to do and when it may stop. Chains, chain severity, LOPA and recommendations are not orchestrator tools: they run as fixed code steps after the analysis (P3-1; Steps 5 and 6).

**Orchestrator tools**

| Tool | Does | Returns |
|---|---|---|
| `check_coverage` | Code reports open, answered, failed and unsure questions by type and section | Counts and question IDs |
| `dispatch_specialist` | Sends a batch of question IDs to one specialist agent | Findings, or failures |
| `web_research` | Tavily search on a specific question or cause | Snippets with URLs |
| `search_precedent` | Local precedent index (CSB, ARIA, eMARS and other national reports), then Tavily if nothing fits | Matching incidents with URLs |
| `reactivity_lookup` | Reactive-group table for a chemical pair | Hazard type and source row |
| `physics_calc` | Overflow time, pressure as a multiple of design limit, heat-up rate, from plant facts | Number with units and the facts used |
| `run_simulation` | A fault on the Tennessee Eastman demo plant | Variables that moved, limits crossed |
| `finish` | Ends the run | Accepted, or refused with the reason |

**Specialist agents.** Each gets only its own questions and the data they need, works independently of the others, may take **at most 2 tool steps per batch** (`reactivity_lookup`, `web_research`), then must answer in the fixed schema. The data includes the `notes` of the plant objects in its scope (the source's exact words, passed as data, never parsed by code), and safeguards with no `layer_type` as existing protection, with their description.

| Specialist agent | Gets only | Answers |
|---|---|---|
| Process deviations | Sections, operating values, alarm/trip setpoints, design limits, control loops with valve fail positions, safeguards, relief devices, and the procedure steps and planned jobs that act on them (rule R40) | Guideword × parameter questions; relief discharge questions |
| Chemical interactions | Chemical list, properties, reactivity groups, and where each chemical is present (the equipment and lines whose contents list it, and the injection points that add it), and the procedure steps and planned jobs that act on them (rule R40) | Every pair, plus water, air, heat |
| Piping and no-flow lines | Line list, no-flow lines (non-empty `no_flow`), injection points on lines and equipment, and the procedure steps and planned jobs that act on them (rule R40) | What builds up, what is missing |
| Procedures | Start-up, shutdown, charging steps | Each step × time and sequence deviations |
| Maintenance work | Planned jobs and their surroundings | Hot work, overlapping jobs, isolation |
| Dust and ignition | Solids handling, hot surfaces, dust collection, and the procedure steps and planned jobs that act on them (rule R40) | Explosion and how it spreads |

Every answer is a **finding**: cause (a cause-library ID bound to the specific failing component IDs in this plant, e.g. C01 + `TV-1`; or a new cause tagged "outside library, needs evidence", with its failing component IDs), consequence, existing protection, whether protection is adequate, confidence (sure / unsure), and optional not-credible reason.

What the failing component IDs point to, by the cause's failing-component type: utility causes → the utility ID; hose causes → the line; operator causes → the procedure step or planned job; external causes → the location; every other type → the equipment, valve, instrument, control loop or relief device that fails. **`failing_component_ids` is never empty**; finding validation rejects an empty list.

**Unsure is a confidence, not a question status.** An unsure answer leaves the question `answered`, which counts as checked; the coverage report shows the unsure count separately. The orchestrator may research unsure findings or re-dispatch them to Ultra (capped per run). Unsure findings do not block `finish`; they are flagged in the shortlist.

**Code guards**
- The question list is fixed before the agent starts. The agent chooses order and tools, never which questions exist.
- `finish` is **refused until every question has a valid answer** (or has failed twice and is listed as failed) and the top findings have been through evidence. An unsure answer is a valid answer. The guard does not wait for LOPA, which runs after the analysis (P3-1).
- A question dispatched twice is answered from the first result; duplicates cost nothing.
- Step caps (orchestrator steps per run, specialist steps per question), token and dollar caps per run; hitting one stops the run with a message.
- The orchestrator sees counts and short summaries, never the full findings list, so each step stays small; only the connector (Step 5, after the analysis) reads a summary of every finding plus the whole plant.
- Every tool argument is validated; every model and tool call is logged before the next step.
- During benchmark runs, Tavily and the precedent index block the case under test by name, company, location and date. The same block applies to demo plants: the Williams Geismar demo never cites its own CSB report as precedent.

**Worked example (silicones plant, 10 chemicals).** `check_coverage` → 212 open questions. Orchestrator dispatches the 45 chemical-pair questions to the chemistry agent and 32 procedure-step questions to the procedures agent. The chemistry agent is unsure about KOH emulsifier + Si-H fluid, calls `reactivity_lookup`, gets "flammable gas (GF), from the EPA chart", answers. The orchestrator sees "flammable gas" and "wrong tote loaded" and calls `search_precedent` and `physics_calc`. It calls `finish`; code refuses because 3 questions failed validation; it re-dispatches them, then finishes. After the analysis, the connector proposes the chain, and LOPA on it shows a large gap.

### Step 5 — Chains (connector, a fixed code step after the analysis; P3-1)
Ultra reads a one-line summary of every finding (ID, cause, consequence, components), never the raw answers, plus the whole plant, within `connector_max_input_tokens` (`config/caps.yaml`), and proposes **chains**: two or more findings that combine into something worse (e.g. reboiler isolated from relief + heat still reaching it → pressure with nowhere to go → rupture).

- **Every link must be an existing finding ID or plant fact ID.** Any other link rejects the chain.
- Chains are labelled **multi-failure** and are **never ranked down** for needing two failures.
- Misused terms and scenarios needing more than two independent failures are flagged for the engineer, never filtered out.

### Step 6 — Ranking (code, with reasons from Ultra; tier order per R50)
1. **Screen**: every row gets a severity × likelihood risk-matrix rating from `risk_matrix.csv` (the engineer can load their company's matrix). The screening likelihood is the likelihood band (`likelihood_classes.csv`) that holds the cause's initiating frequency, chosen by code.
   The screened list is shown in three tiers (R50): **confirmed** (hypotheses with at least one supporting finding, each line showing its lead scenario), **also found** (every other scenario, in the risk-matrix order, folded as in R48) and **unconfirmed** (hypotheses no check supported, flagged for the engineer). Per R50, the whole-plant pass's hypothesis rank, a model judgment with a reason, orders only the confirmed and unconfirmed tiers; code computes tier membership, ratings, links, the fold, LOPA gap and all of "also found"; the model never sets a number. LOPA (below) runs on the top `lopa_top_n` confirmed and also-found lines; unconfirmed lines get no LOPA and are listed after.
2. **LOPA** (spec 3.2), on these lines and no others:
   - **Full LOPA**, with Ultra's layer argument, on the top `lopa_top_n` confirmed and also-found lines, plus every chain. A line is a scenario (R48), so its LOPA target is the line's lead finding; for a chain, the chain.
   - **Code-only LOPA** on every other S4–S5 line in the confirmed and also-found tiers: no model call, every candidate layer marked "not argued — no credit", flagged "code-only LOPA: layers not argued". The gap is conservative and labelled.
   - Unconfirmed lines, and S1–S3 lines outside the top `lopa_top_n`, get no LOPA.
   - Initiating event frequency from the reference table (each cause-library entry maps to one initiating-event class). Classes not given per year are converted with a plant fact: `per_metre_year` × `lines.length_m`, `per_lift` × `planned_work.lifts_per_year`. **If that fact is missing, the LOPA record is marked incomplete and names the missing fact ID; code never substitutes a default frequency.** The finding stays on the list, flagged. **Outside-library causes:** code (never a model) assigns the highest frequency among library causes with the same failing-component type (converted by the same rule), or 0.1 per year if the type has none, flagged "frequency assumed — engineer to confirm".
   - Conditional modifiers: **none applied in Phase 3** (P3-3). Each LOPA record lists every modifier kind in `modifiers.csv` as not applied, with the reason "no plant fact or rule".
   - Protection layers: Ultra argues which safeguards apply and why; **code decides credit**. A safeguard gets no credit if any ID in its `component_ids` is among the cause's failing component IDs, or shares a logic solver with the failing control loop (as required by its row in `protection_layers.csv`); a relief device with a closed inlet valve gets no credit, and one with an unmanaged inlet valve gets the `pfd_if_isolatable` value. A safeguard with no `layer_type` never gets credit. Each layer is shown credited or not, with the reason.
   - **Relief devices** need no safeguard row: every relief device is a candidate layer for overpressure scenarios on its `protects_id`, using the `protection_layers.csv` row whose `relief_kind` matches its `kind` (prv → IPL-PRV, rupture_disk → IPL-RD, prv_with_disk → IPL-PRV-RD, vent → IPL-CONS-VENT). Its inlet valves decide the credit: any inlet valve with `normal_position: closed` → no credit; otherwise any inlet valve that is open and not `locked` ("unmanaged") → `pfd_if_isolatable`; all inlet valves locked open, or none → `pfd`.
   - Mitigated frequency = initiating frequency × modifiers (none in Phase 3, P3-3) × each credited layer's failure-on-demand probability.
   - Compared to the tolerable frequency for its severity class → **gap**.
   - Shown as orders of magnitude ("about 1 in 10,000 years"), never false precision.
3. **Shortlist** = the top findings and chains ranked by tier first (R50), then by gap within a tier; gap never lifts an also-found line above a confirmed one, and a chain takes the tier of its highest-ranked member. Counts and caps (how many get LOPA, how many get evidence, step and spend caps) live in `config/caps.yaml`; starting values: LOPA on the top 10, full evidence on the top 5.
4. **Recommendation**: where the gap is above 1, Ultra proposes an action (e.g. an independent high-temperature trip), stored as a Recommendation record with its reason and target finding or chain; the engineer accepts, rejects or edits it (overrides).

Severity: Ultra picks a severity class and must give a reason; code looks up the tolerable frequency and the risk rating. Likelihood never comes from the model.

### Step 7 — Evidence (gathered by the orchestrator)
For each top finding and chain:
- **Physics calculation** (e.g. "overflows in 18 minutes", "pressure reaches 3.5× design"). Vapour pressure is interpolated between the chemical's `vapor_pressure_points` (Clausius–Clapeyron) and never extrapolated beyond them; if the facts are missing, the calculation is skipped and flagged.
- **CSB precedent** with link.
- **Simulator run** on Tennessee Eastman where applicable. Known result from kill test #1: with cooling lost, the plant tripped on high pressure at 1.05 h while reactor temperature *fell* (122.6 → 84.6 °C), a counter-intuitive outcome the simulator catches and a model would likely get wrong.

Each finding is marked **confirmed**, **contradicted** or **no evidence available**.

### Step 8 — Review and export
The engineer accepts, edits or rejects every row, chain, protection credit and recommendation, and answers engineer-added questions. Changes are stored as **overrides**; model output is never edited in place. Outputs:
- **HAZOP worksheet** (Excel) — columns: Section, Design intent, Guideword, Parameter, Deviation, Causes, Consequences, Existing safeguards, Severity, Likelihood, Risk, LOPA gap, Recommendation, Action owner (blank), Origin (matrix / cross-list / added by AI / engineer), Evidence, Status.
- **Shortlist** with evidence and sources.
- **Coverage report**: checked versus total for every list: sections, matrix questions, chemical pairs, chemical environment, no-flow lines, procedure steps, jobs, dust, relief devices, engineer-added questions. A question counts as checked only with a valid answer (`answered` or `not_credible`); unsure answers are counted separately; failed questions are listed.
- **Full trail** for any number: its record, parents, model calls and tool calls.

---

## 6. Models and routing

All through Token Factory, endpoint `https://api.tokenfactory.nebius.com/v1` (OpenAI-compatible). Model IDs are read from the live model list at startup, never hard-coded.

| Model | Catalog ID (Oct 11) | Price per 1M tokens in / out | Starting job |
|---|---|---|---|
| Nemotron 3 Ultra 550B | `nvidia/Nemotron-3-Ultra-550b-a55b` | $1.00 / $3.00 | Orchestrator agent, connector, LOPA protection arguments, severity reasons, recommendations, unsure answers |
| Nemotron 3 Super 120B | `nvidia/nemotron-3-super-120b-a12b` | $0.30 / $0.90 | Section suggestions, harder specialist questions, fallback if a tier disappears |
| Nemotron 3.5 Lightning | `nvidia/Nemotron-3_5-Lightning` | $0.06 / $0.24 | Specialist agents on bulk questions, not-credible marks, extraction and formatting |
| Nemotron 3 Nano 30B | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | $0.06 / $0.24 | Four-tier comparison only (same price as Lightning, so no job is routed to it) |

Test #5 confirms or moves each job to the cheapest tier that passes. The four-tier comparison (accuracy, speed, cost) runs on a fixed sample of 50 questions and goes in the README and video.

---

## 7. Budget: $25 of Token Factory credit

| Use (`use` in the ledger) | Environment | Allowance |
|---|---|---|
| Development (`development`) | laptop | $5 |
| Test #5 (`test_5`) | laptop | $7.50 (was $4; moved for G2b, Oct 16 and 17) |
| Held-out benchmark (`benchmark`) | laptop | $4.50 (was $8; moved for G2b, Oct 16 and 17) |
| Video (`video`) | laptop | $2 |
| Demo recording (`demo_recording`) | hosted | $1 |
| Judging period, Dec 1–15 (`judging`) | hosted | $3 |
| Buffer, released only by Bhargavi (`buffer`) | hosted | $2 |

Laptop $19 = 5 + 7.50 + 4.50 + 2; hosted $6 = 1 + 3 + 2; total $25.

Cost rules, enforced in code:
- Development iterates on specialist prompts with Lightning. Ultra and Super are used only for the jobs routed to them (orchestrator, severity, section suggestions, unsure answers, the gateway check), always under the run and phase caps. Every model response is cached by model, prompt version and exact input; a re-run after a code change costs nothing.
- Claude Code sessions never make live model calls. Bhargavi starts every live call: through the budget-capped `scripts/live_call.py` until the Phase 2 gateway exists, then through `guideword/gateway` and `guideword/tools`.
- Ultra runs the orchestrator (about 30–60 small steps per run, each seeing counts and summaries, not full findings), the connector, LOPA arguments, recommendations and unsure answers (capped per run). Evidence and LOPA run on the top findings only.
- The connector receives one-line finding summaries (ID, cause, consequence, components) plus the plant, never raw answers, capped at `connector_max_input_tokens` in `config/caps.yaml`.
- The Super section-suggestion call has its own cap, `section_suggest_cap_usd`, in `config/caps.yaml`.
- Specialist agents run on the cheap tier and take at most 2 tool steps per batch.
- Hard spend cap per run and a running total per environment and per use; a call that would cross any of them is refused and the run stops with a message. The per-run cap lives only in `config/caps.yaml`.
- **Each environment enforces its own allowance:** laptop $19 (development, test #5, benchmark, video), tracked in `budget/ledger.jsonl`; hosted $6 (demo recording, judging period, buffer), tracked in the `spend_ledger` table. Neither reads the other. A weekly check of the Token Factory dashboard balance reconciles the two. Every ledger line carries a required `use`, and a call that would push a use past its allowance is refused.
- `budget/ledger.jsonl` is git-ignored: one local file that survives branch switches. At each gate Bhargavi commits a snapshot, `budget/ledger-<gate>.jsonl`.
- Every call logs tokens and dollars; running total checked daily.
- Hosting and any Nebius AI Cloud compute are paid separately from these credits.
- Rough estimate to confirm in the Phase 0 smoke test: about $0.40 of Ultra orchestration per run plus specialist and connector calls.

To raise the ceiling: the promo form (code NEBIUS-DEVPOST-GLOBAL26) and the Nebius Builders Program are separate $25 Token Factory grants; claim whichever is not yet claimed.

---

## 8. Data sources (all public)

| Source | Feeds |
|---|---|
| CSB investigation reports (US) | Dev cases, held-out cases, precedent index |
| Other national investigation sources: ARIA (France, 46,000+ events, English summaries), eMARS (EU major accidents), Dutch Safety Board, UK HSE, national committee reports (e.g. India) | Held-out cases, precedent index |
| NOAA CAMEO Chemicals reactive groups; US EPA chemical compatibility chart (EPA-600/2-80-076, 1980) | Chemical classification; group-pair reactivity hazards |
| EGPC-PSM-GL-015 (2022), tabulating CCPS typical values | Initiating event frequencies, protection layer failure probabilities, conditional modifiers, default tolerable frequencies per severity class |
| Downs & Vogel (1993) Tennessee Eastman paper; open-licence Python implementation `tennessee-eastman-profbraatz` (University of Illinois licence) | Demo plant description and simulator |
| Safety data sheets | Chemical properties |
| Tavily (runtime) | Research and precedent search |

Anything not in a source is written into the plant file as **"assumed"** and shown in the UI as an assumption (e.g. Tennessee Eastman valve fail positions).

---

## 9. Plant file format

One JSON file per plant, validated with Pydantic against the frozen schema (`contract/schemas/plant.schema.json`). Rules:

- **Every object has an ID**, unique across the whole file, matching `^[A-Za-z0-9][A-Za-z0-9_-]*$` (`.`, `:`, `~` and `+` are reserved for derived IDs, §11). Every reference must point to an existing ID; validation fails otherwise.
- **Units are in field names** (`_kpa`, `_kpaa`, `_c`, `_m3`, `_kg_h`, `_kw`, `_mm`, `_m`, `_pct`, `_kj_kg`, `_kg_m3`, `_kj_kg_k`, `_per_year`, `_usd`). Exception: `operating` rows, where the unit is fixed by the parameter (pressure kPa gauge, temperature °C, level % of range, flow kg/h). `epa_groups` and `cameo_groups` hold reference-table IDs, not quantities.
- **Pressure:** `_kpa` is always kPa gauge (vacuum is negative); `_kpaa` is kPa absolute. There are no exceptions hidden in descriptions: the suffix says which.
- **Fact IDs** are `<object id>.<field>` (e.g. `MX-1.design_pressure_kpa`). `heat_sources`, `injection_points`, `discharge`, `vapor_pressure_points` and `operating` rows are value objects inside their parent, with no ID; a value object is cited by its parent's field (e.g. `PSV-1.discharge`). Operating facts are cited down to one limit: `<target_id>.operating.<parameter>.<limit field>` (e.g. `MX-1.operating.temperature.trip_high`). `provenance` keys are fact IDs or object IDs (an object ID covers all its fields). Values are a source reference or `"assumed"`. Chains and LOPA records cite fact IDs.
- `from` / `to` are stored as `from_id` / `to_id` (`from` is a Python keyword).
- Plant validation depends on the reference tables: every `epa_groups` entry must exist in `reference/reactive_groups.csv`, and every `layer_type` in `reference/protection_layers.csv`.

| Block | Fields (required in bold) | Feeds |
|---|---|---|
| `locations` | **id**, description, occupied (bool), ignition_sources (bool), indoor (bool), distance_m (distance from the unit or area under study), offsite (bool) | Severity, relief discharge, planned work, line endpoints outside the study |
| `utilities` | **id**, **kind** (steam, cooling_water, nitrogen, instrument_air, power, other), location_id | Line sources, failing component for utility causes |
| `equipment` | **id**, **type**, location_id, contents (chemical IDs), volume_m3, design_pressure_kpa, design_temp_c, max_surface_temp_c, heat_duty_kw, dust_collection (bool), heat_sources (list: medium, via_line_id, isolating_valve_ids), injection_points (list: chemical_id; a chemical injected straight into the equipment) | Sections, questions, physics, independence |
| `instruments` | **id**, **kind** (sensor, switch, analyser), measures (parameter), on_id (equipment or line), system (bpcs, sis, standalone) | Independence check |
| `logic_solvers` | **id**, **system** (bpcs, sis) | Independence check (shared controller or SIS logic) |
| `valves` | **id**, **kind** (control, block, check, manual, relief_isolation), on_line_id (a line whose `components` lists this valve), normal_position (open, closed), fail_position (open, closed, last), locked (bool) | Section splits, independence, isolation, relief credit |
| `lines` | **id**, **from_id**, **to_id** (equipment, utility or location IDs; a location is an endpoint outside the study, e.g. a pipe rack or battery limit), components (ordered IDs of valves, pumps, compressors, exchangers on the line), no_flow (list of normally_closed, dead_leg, standby, startup_only; empty list = flowing), is_hose (bool), contents (chemical IDs), size_mm, length_m, normal_flow_kg_h, design_flow_kg_h, injection_points (list: chemical_id, at_component_id) | Section splits, no-flow questions, physics, hose causes |
| `operating` | **target_id**, **parameter** (pressure, temperature, level, flow), normal, alarm_low, alarm_high, trip_low, trip_high, design_min, design_max, alarm_instrument_id, trip_instrument_id | Process questions, LOPA, physics |
| `control_loops` | **id**, **sensor_id**, **controller_id** (a logic solver ID), **final_element_id**, system (bpcs, sis), acts_on_id | Causes, independence |
| `safeguards` | **id**, layer_type (ID from `protection_layers.csv`), description, protects_id (equipment or location), component_ids (sensors, logic solver, final elements it relies on). A safeguard with no layer_type (e.g. gas detectors, a permit system, PPE) is passed to specialists as existing protection with its description and **never gets LOPA credit** | LOPA credit and independence; existing protection |
| `relief_devices` | **id**, **protects_id**, kind (prv, rupture_disk, prv_with_disk, vent), set_pressure_kpa, capacity_kg_h, inlet_valve_ids, discharge (kind: atmosphere, flare, scrubber, vessel, header; location_id; elevation_m) | Overpressure, relief discharge, isolation |
| `chemicals` | **id**, **name**, epa_groups, cameo_groups, physical_form (gas, liquid, solid, dust), combustible_dust (bool), boiling_point_c, flash_point_c, density_kg_m3, heat_capacity_kj_kg_k, vapor_pressure_points (list: temp_c, pressure_kpaa), heat_of_reaction_kj_kg, source | Chemistry, dust, physics (all physics fields optional; a calculation without its facts is skipped and flagged) |
| `procedures` | **id**, **kind** (start_up, shutdown, charging, transfer, cleaning, maintenance, emergency, other), **steps** (list: **id**, **text**, equipment_ids, valve_ids) | Procedure questions |
| `planned_work` | **id**, **type** (hot_work, confined_space, line_break, lifting, other), location_id, equipment_ids, line_ids (lines the job works on or over), start, end (ISO 8601), lifts_per_year | Maintenance questions, overlapping jobs, LOPA for `per_lift` causes |
| `provenance` | fact ID or object ID → source or "assumed" | Trail, assumptions shown in UI |
| `notes` | on every plant object with an ID, and on the plant itself: list of {**text**, **source**}. The source package's exact words, never a paraphrase or comment. Code never parses notes; specialists receive the notes of the objects in their scope | Facts the schema has no field for |

A complete, valid example (a small fictional mixing unit; every ID it uses is defined):

```json
{
  "plant_id": "example_mixing_unit",
  "schema_version": "1.0",
  "locations": [
    {"id": "BLDG-1", "occupied": true, "ignition_sources": true, "indoor": true},
    {"id": "ROOF", "occupied": false, "ignition_sources": false, "indoor": false}
  ],
  "utilities": [
    {"id": "UT-STEAM", "kind": "steam", "location_id": "BLDG-1"}
  ],
  "equipment": [
    {"id": "TOTE-1", "type": "tank", "location_id": "BLDG-1", "contents": ["SIH"], "volume_m3": 1},
    {"id": "P-1", "type": "pump", "location_id": "BLDG-1"},
    {"id": "MX-1", "type": "mixer", "location_id": "BLDG-1", "contents": ["SIH", "KOH"],
     "volume_m3": 10, "design_pressure_kpa": 350, "design_temp_c": 80,
     "heat_sources": [{"medium": "steam", "via_line_id": "L-STM", "isolating_valve_ids": ["XV-STM"]}]}
  ],
  "instruments": [
    {"id": "TT-1", "kind": "sensor", "measures": "temperature", "on_id": "MX-1", "system": "bpcs"},
    {"id": "TS-2", "kind": "switch", "measures": "temperature", "on_id": "MX-1", "system": "sis"}
  ],
  "logic_solvers": [
    {"id": "DCS-1", "system": "bpcs"},
    {"id": "SIS-1", "system": "sis"}
  ],
  "valves": [
    {"id": "TV-1", "kind": "control", "on_line_id": "L-STM", "normal_position": "open", "fail_position": "closed", "locked": false},
    {"id": "XV-STM", "kind": "block", "on_line_id": "L-STM", "normal_position": "open", "fail_position": "closed", "locked": false},
    {"id": "HV-12", "kind": "manual", "on_line_id": "L-12", "normal_position": "closed", "fail_position": "last", "locked": false}
  ],
  "lines": [
    {"id": "L-12", "from_id": "TOTE-1", "to_id": "MX-1", "components": ["P-1", "HV-12"],
     "no_flow": [], "contents": ["SIH"], "size_mm": 50, "normal_flow_kg_h": 2000},
    {"id": "L-STM", "from_id": "UT-STEAM", "to_id": "MX-1", "components": ["XV-STM", "TV-1"],
     "no_flow": [], "size_mm": 25}
  ],
  "operating": [
    {"target_id": "MX-1", "parameter": "temperature", "normal": 25, "alarm_high": 50,
     "trip_high": 60, "design_max": 80, "alarm_instrument_id": "TT-1", "trip_instrument_id": "TS-2"}
  ],
  "control_loops": [
    {"id": "TIC-1", "sensor_id": "TT-1", "controller_id": "DCS-1", "final_element_id": "TV-1",
     "system": "bpcs", "acts_on_id": "MX-1"}
  ],
  "safeguards": [
    {"id": "SG-TRIP", "layer_type": "IPL-SIS-SIL1", "protects_id": "MX-1", "component_ids": ["TS-2", "SIS-1", "XV-STM"]},
    {"id": "SG-VENT", "layer_type": "IPL-VENT-CONT", "protects_id": "BLDG-1", "component_ids": []}
  ],
  "relief_devices": [
    {"id": "PSV-1", "protects_id": "MX-1", "kind": "prv", "set_pressure_kpa": 350, "capacity_kg_h": 5000,
     "inlet_valve_ids": [], "discharge": {"kind": "atmosphere", "location_id": "ROOF", "elevation_m": 12}}
  ],
  "chemicals": [
    {"id": "SIH", "name": "methylhydrogen siloxane fluid", "epa_groups": [105], "cameo_groups": [58, 35],
     "physical_form": "liquid", "combustible_dust": false, "source": "SDS"},
    {"id": "KOH", "name": "potassium hydroxide solution", "epa_groups": [10, 106], "cameo_groups": [10, 100],
     "physical_form": "liquid", "combustible_dust": false, "source": "SDS"}
  ],
  "procedures": [
    {"id": "P-CHARGE", "kind": "charging",
     "steps": [{"id": "P-CHARGE-1", "text": "Select tote by label", "equipment_ids": ["TOTE-1"]},
               {"id": "P-CHARGE-2", "text": "Open HV-12 and start P-1", "equipment_ids": ["P-1"], "valve_ids": ["HV-12"]}]}
  ],
  "planned_work": [
    {"id": "W-1", "type": "hot_work", "location_id": "ROOF", "equipment_ids": [],
     "start": "2026-10-20T08:00:00", "end": "2026-10-20T16:00:00"}
  ],
  "provenance": {"MX-1.design_pressure_kpa": "assumed", "SIH": "SDS", "KOH": "SDS"}
}
```

The Si-H fluid is classed EPA 105 (strong reducing agents): its SDS says it reacts with bases to release hydrogen, consistent with CAMEO group 35 (hydrides and silanes). KOH solution is EPA 10 (caustics) and 106 (water mixtures). The pair therefore hits the chart's 105 × 106 row (GF, GT).

---

## 10. Reference data (versioned files in `reference/`, every row has a source column)

Files are UTF-8 CSV with LF line endings (enforced by `.gitattributes`), so version hashes match on every machine. Column headers are frozen in Phase 0.

| File | Columns | Used by |
|---|---|---|
| `applicability.csv` | section_type, guideword, parameter, source — **only applicable rows are listed; not listed means not applicable**. The `procedure` rows only supply the guideword list for `proc:` questions | Question builder |
| `causes.csv` | id, cause, applies_to, failing_component_type, initiating_event_id, source | Specialists, LOPA |
| `initiating_events.csv` | id, event, frequency, unit, source — `unit` is `per_year`, `per_opportunity`, `per_metre_year` or `per_lift`; only `per_year` is used directly (conversion rule in §5 Step 6) | LOPA |
| `protection_layers.csv` | id, layer, category, pfd, pfd_if_isolatable, requires_independent_sensor, requires_independent_logic, requires_independent_final_element, no_credit_if_isolated, scenarios, conditions_text, relief_kind, source — `relief_kind` names the relief-device kind that uses the row (empty for other rows) | LOPA credit and independence; relief-device credit |
| `modifiers.csv` | id, kind, release_phase, release_rate_kg_s_band, area_occupancy, event_type, operating_pattern, value, source | LOPA |
| `severity_classes.csv` | severity_class, name, definition, source | Severity choice, screening |
| `tolerable_frequencies.csv` | severity_class, tolerable_per_year, source | LOPA gap |
| `likelihood_classes.csv` | likelihood_class, name, min_per_year, max_per_year, source — contiguous bands from 0; an empty `max_per_year` on the top band means no upper limit | Screening |
| `risk_matrix.csv` | severity_class, likelihood_class, rating, source — 25 rows; rating from S number + L number: 2–4 low, 5–6 medium, 7–8 high, 9–10 very_high | Screening |
| `reactive_groups.csv` | epa_group_id, name, do_not_mix, source (41 EPA 1980 chart groups; `do_not_mix` = 1 only for 107, water-reactive substances, which the chart says not to mix with anything) | Plant validation, chemistry |
| `reactive_pairs.csv` | group_a, group_b, codes (H, F, G, GT, GF, E, P, S, U), source | `reactivity_lookup` |
| `cameo_groups.csv` | cameo_group_id, name, source | Chemical classification aid |
| `precedent_index.csv` | id, title, date, location, hazard_type, summary, url, source (built in Phase 4) | `search_precedent` |
| `sources.md` | Every source cited, with URL and access date | Trail |

A run records the version hash of every table it used.

---

## 11. Architecture

### System layers
1. **Prepared once, versioned in the repo:** public sources → reference tables; plant files (dev cases, demo plants; held-out cases in a separate private repo until G3).
2. **Runtime:** web app → API → run worker. Only the run worker calls Nemotron and Tavily.
3. **External services:** Token Factory, Tavily.
4. **Storage:** run store (Postgres) with an append-only event log; exports.
5. **Evaluation:** batch runs on a laptop by default, auto-score, human score, results table.

### Backend modules (Python package `guideword`)

| Module | Owns |
|---|---|
| `schema` | Pydantic models for the plant file and all record types; schema version |
| `reference` | Loads and checks reference tables; stamps runs with their version hash |
| `sections` | Rule-based split, no-flow flags, Super suggestions, applying confirmation |
| `questions` | Matrix and cross lists, numbering, coverage counts |
| `gateway` | Token Factory client, live model list, routing, cache, budget guard, retries, concurrency limit, call log |
| `orchestrator` | The Ultra agent loop: state, step caps, summaries it sees, the `finish` guard |
| `specialists` | The six specialist agents: versioned prompts, output schemas, 2-step tool limit, tier routing |
| `tools` | Every tool the agents can call, with argument schemas and caps |
| `lopa` | LOPA calculation, independence check, gap |
| `connector` | Chain proposal and ID validation |
| `ranking` | Risk-matrix screen, shortlist, recommendations |
| `simulator` | Tennessee Eastman model and fault runs |
| `importers` | Reserved for a DEXPI importer (after the hackathon) |
| `runs` | Run state machine, event log, persistence, resume |
| `api` | FastAPI routes, live updates, demo mode, per-visitor caps |
| `export` | Excel worksheet, coverage report, JSON dump |
| `bench` | Memorisation probe, batch runner, auto-scorer, results table |

**Call boundaries:** only `gateway` calls Token Factory; only `tools` calls Tavily. This is what makes caching, the budget cap and the call log enforceable.

### Model gateway (every call, in this order)
1. **Route**: job → tier (routing config) → model ID (live list). If a model left the catalog, use the next tier up and log it.
2. **Cache**: key = hash(model ID, prompt version, exact input). Hit = zero cost, logged.
3. **Budget guard**: refuse if the estimated cost would cross the run cap or this environment's remaining allowance.
4. **Send**: concurrency limit per model; back off and retry rate-limit and server errors up to 3 times.
5. **Validate** (JSON rules below); retry once with the validation error, then mark failed.
6. **Log**: model, prompt version, tokens, latency, real cost, raw response, reasoning text.

### JSON output rules
- Reasoning off for bulk questions; a reasoning budget for Ultra. Any response with `finish_reason` = length is failed, never parsed.
- Read the answer only from `content`; strip a leading `<think>` block if present; log `reasoning_content` separately.
- Request `json_schema` output; fall back to JSON mode; always validate with Pydantic.
- Every ID in a response must be one we sent; unknown IDs fail validation.
- Batched questions (several per call) each carry their question ID; every ID must come back exactly once; missing ones are retried alone.
- Enums for severity class, cause-library ID, verdict, confidence; reasons in separate length-capped text fields.
- Normalise Unicode dashes, non-breaking spaces and unit variants before matching or scoring.
- Malformed tool arguments are refused; the error goes back to the agent once, then that branch stops.
- Tool results and plant text are data, never instructions; no tool can write or spend beyond caps.

### Run orchestration
Sections are proposed and confirmed on the plant before any run. A run has two parts. **Setup** is a fixed sequence (validate the confirmed-section snapshot → build the question list), stored in `runs.step`. **Analysis** is the orchestrator loop: every orchestrator step, tool call and specialist result is written to the database before the next step, so a crashed run resumes from its last saved step without paying again. Specialist dispatches run in parallel up to the concurrency limit. Each orchestrator step (with the dispatches it launches) runs as its own function invocation and triggers the next, which keeps every invocation well under hosting time limits.

**Run steps** (`runs.step`, spec 3.6): `plant_screen → analysis → severity → chains → chain_severity → lopa → recommendations → ranked`. The connector reads finding severities, so `chains` comes after `severity`. Each step resumes on its own and writes before returning. The post-analysis steps (`chains` to `recommendations`) spend under the run's own `post_spend_cap_usd` (P3-2); the analysis cap and its severity reserve are unchanged. A cap stop in a post-analysis step leaves the run `stopped_cap` with the analysis intact, and R38 still applies. An existing finished run is extended in place (P3-1b): same run ID, step set to `chains`, status back to `running`, one `run_extended` event; no hashed run field and no earlier record changes.

### Record types

| Record | Holds | Points back to |
|---|---|---|
| Plant | Plant file, status (uploaded / sections_proposed / sections_confirmed), confirmed section set | Its uploaded file |
| Run | Plant, section snapshot, status, step, spend cap, post-analysis cap (`post_spend_cap_usd`, not hashed; contract v1.4), spent, reference versions, routing config, caps, prompt versions, mode, attempt, label (live / recorded / mock). The stored inputs rebuild the run ID exactly | Plant |
| Plant fact | One fact about the plant, ID `<object id>.<field>` | Its source or "assumed" |
| Section | Confirmed section, type, purpose | Plant record; plant facts; rule or suggestion that drew it |
| Question | One check; status; not-credible reason (a not-credible answer is a question status with its reason and needs no finding) | Run; section, facts needed; origin tag; the model call that marked it not credible or added it (`ai:`) |
| Finding | Cause, failing component type and IDs (never empty), consequence, safeguard IDs, adequacy, severity class with reason, confidence, the tier that answered (ultra / super / lightning / nano) | Run; question; cause-library entry or "outside library"; plant IDs of the failing components |
| Recommendation | Action, reason | Target finding or chain |
| Agent step | Which agent, its decision, the tool it chose (a §5 tool name, or `answer`), a one-line reason | Run; previous step |
| Model call | Model, prompt version, routing job, cache hit, outcome (ok / invalid / truncated / error), finish reason, tokens, latency, cost, raw response. Stored per (run ID, call ID): a cached response reused by another run is a second record with cache hit true and cost 0 | Run; record produced |
| Tool call | Tool, arguments, result, sources, refused reason (when code refused the call) | Finding or chain |
| Chain | Ordered links, multi-failure label, flags, severity class with reason (from the chain severity step; contract v1.4) | Finding IDs and plant fact IDs; the connector's model call |
| LOPA record | Initiating frequency, modifiers applied and the modifier kinds not applied with the reason, layers credited or not with code's reason and Ultra's argument (applies yes/no, why), flags, frequency, tolerable, gap (contract v1.4) | Finding or chain; reference table rows |
| Evidence | Calculation, precedent or simulation result; verdict | Finding; tool call; plant fact IDs it used |
| Override | Action, new value, reason, who (display name) and when | Any record |
| Event | Sequence number, type, payload, time | Run |

### IDs and enums (frozen in Phase 0)

- **Every ID is built from content: never random, never a counter**, so the cache, replays and the trail are stable and a replay produces the same IDs. `h(x)` = the first 16 hex characters of SHA-256 over the canonical JSON of `x` (sorted keys, no whitespace, UTF-8, Unicode NFC). IDs are unique within a run; clients URL-encode them in paths.

  | Record | ID |
  |---|---|
  | Plant | `plant:<plant_id>:<h(plant file)>` |
  | Plant object | its ID in the plant file (pattern in §9) |
  | Plant fact | `<object id>.<field>` |
  | Section | Rule-drawn: `S-<object id>` (the equipment, line, procedure or planned job it came from). A split part: `S-<object id>~<id of the first component in that part>`. Engineer-added: `S~eng~<h(sorted IDs of the plant objects it covers)>`. A merge keeps the lowest of the merged IDs. Renaming never changes an ID. |
  | Question | `m:<section>:<guideword>:<parameter>`, `pair:<chemA>:<chemB>` (sorted), `env:<chem>:<water\|air\|heat>`, `nf:<line>`, `proc:<step>:<guideword>`, `work:<job>:<target>`, `dust:<equipment>`, `relief:<device>`, `ai:<section>:<h(normalised question text)>`, `eng:<section>:<h(normalised question text)>` |
  | Run | `run:<h(plant ID, section snapshot, reference version hashes, routing config, caps, prompt versions, mode)>`. The run's `spend_cap_usd` is **not** hashed. Starting a run with identical inputs **resumes** that run if it is unfinished (draft, running, stopped_budget). A `stopped_cap` run resumes only when the new `spend_cap_usd` is higher than its cap, and then continues under the new cap; with the same or a lower cap the start is refused with 409 "cap reached; raise spend_cap_usd to continue". If the run is finished, cancelled or failed, the new run is `run:<h(inputs)>:<n>` (n = attempt number, 2, 3…): a deliberate, visible counter, so a cancelled run can be restarted and a benchmark case can be run more than once. |
  | Finding | `f:<question id>:<tier>:<cause id>:<h(sorted failing component IDs)>`. One question can have several findings (one per cause). For an outside-library cause, `h(normalised cause text)` replaces the cause ID. The tier is the one that answered; an Ultra re-answer of an unsure finding is a second finding, never an edit of the first |
  | Hypothesis | `h:<rank>:<h(normalised mechanism, sorted component IDs)>` (R50, contract v1.2). Stored per run (run ID as a field, not in the ID). Immutable: its question links (`question_ids`) are set when it is created; whether findings support it is computed when read, never stored |
  | Chain | `ch:<link IDs sorted and joined with +>`; the same set of links is the same chain |
  | LOPA record | `lopa:<finding or chain id>` |
  | Recommendation | `rec:<finding or chain id>:<h(normalised action text)>` |
  | Evidence | `ev:<finding or chain id>:calculation:<calculation name>`, `ev:<…>:precedent:<precedent index id, or h(url) for a web result>`, `ev:<…>:simulation:<fault id>` |
  | Model call | `mc:<cache key>` (cache key = h(model ID, prompt version, exact input)); retries of the same input are attempts inside one record |
  | Tool call | `tc:<agent step id>:<tool>:<h(canonical arguments)>` (the same tool with the same arguments at a later step, e.g. `check_coverage`, is a different call) |
  | Agent step | `step:<h(previous step ID, or the run ID for the first step; agent; tool; canonical arguments)>` |
  | Override | `ov:<target id>:<h(action, new value, ID of the override it replaces on that target or "none")>` |
  | Event | No content ID: an event is identified by (run ID, `seq`). Events are a log, not part of the replay comparison, and the same record can be reported more than once (e.g. a cached model call reused in a run). |
- **Question status:** open, answered, not_credible, failed. `answered` and `not_credible` both count as checked. Unsure is a finding confidence, not a status.
- **Plant status:** uploaded, sections_proposed, sections_confirmed.
- **Run status:** draft, running, finished, stopped_cap, stopped_budget, failed, cancelled.
- **Override action:** accept, reject, edit, change_credit, change_severity, answer (`answer` answers an engineer-added question in a finished run). `new_value` by action (contract v1.4): `accept`, `reject` → null; `edit` → `{field: value}`, only `recommendation.action`, `finding.consequence` or `section.purpose`; `change_credit` → `{layer_id, credited}` on `lopa:<target>`; `change_severity` → `{severity_class}` on a finding or chain; `answer` → `{text}` on an `eng:` question.
- **Utility kind:** steam, cooling_water, nitrogen, instrument_air, power, other.
- **Evidence kind:** calculation, precedent, simulation. **Verdict:** confirmed, contradicted, none.
- **Protection adequacy:** adequate, inadequate, unknown.
- **Agents:** orchestrator, process, chemistry, piping, procedures, maintenance, dust, connector.
- **Event types:** run_started, step_started, step_finished, agent_decision, dispatch, model_call, tool_call, finding_added, chain_added, lopa_done, evidence_added, coverage_updated, cap_hit, run_finished, run_failed, hypothesis_added, hypothesis_dropped (the last two: R50, contract v1.2), run_extended (contract v1.4: a finished run extended with the post-analysis steps).

### Storage schema (Postgres; SQLite in development)
`plants` (status uploaded / sections_proposed / sections_confirmed), `plant_facts`, `runs` (status, step, section snapshot, spend_cap_usd, spent_usd, reference_versions, routing_config, caps, prompt_versions, label), `sections`, `questions` (status open / answered / not_credible / failed, not_credible_reason), `findings`, `hypotheses` (R50: rank, mechanism, component and chemical IDs, cause, consequence, reason, question links), `agent_steps`, `model_calls` (key: run_id + id), `tool_calls`, `chains`, `lopa_records`, `recommendations`, `evidence`, `overrides`, `events` (append-only: seq, run_id, type, payload), `response_cache`, `spend_ledger` (environment, phase, use, model or tool, tokens or searches, cost). Links are foreign keys; large payloads are JSON columns.

### API contract (frozen in Phase 0)

Every run-related response carries a `label`: `{kind: live | recorded | mock, recorded_at, cost_usd}`, shown on screen. Until a phase builds an endpoint, it returns 501 naming that phase, except in mock mode (`GUIDEWORD_MOCK=1`), where every endpoint serves fixtures.

| Method and path | Request | Does |
|---|---|---|
| `GET /plants` | — | List plants |
| `POST /plants` | plant file | Upload and validate; returns errors and missing-fact warnings |
| `GET /plants/{id}` | — | Plant facts with sources |
| `POST /plants/{id}/sections/propose` | — | Rules plus Super suggestions with reasons (under `section_suggest_cap_usd`; the live Super call is wired in Phase 2, and Phase 1 returns no suggestions), and the suggestions code refused with its reasons (`rejected`, contract v1.3); plant status → sections_proposed |
| `PUT /plants/{id}/sections` | confirmed section set | Save confirmed sections; plant status → sections_confirmed |
| `GET /runs` | — | List runs |
| `POST /runs` | plant_id, spend_cap_usd, mode (full, sample) | Start a run; returns run ID and estimated cost; 409 if the plant's sections are not confirmed, or if a `stopped_cap` run with the same inputs is restarted without a higher `spend_cap_usd` |
| `POST /runs/{id}/cancel` | — | Cancel a running run |
| `GET /runs/{id}` | — | Status, step, cost, counts |
| `GET /runs/{id}/events?after={seq}` | — | New events since `seq` (polled every few seconds) |
| `GET /runs/{id}/sections` | — | The run's section snapshot |
| `GET /runs/{id}/questions` | filters | Questions with status |
| `POST /runs/{id}/questions` | section_id, text | Add an engineer question (origin `engineer`, ID `eng:<section>:<h(text)>`, status open) |
| `GET /runs/{id}/shortlist` | — | Ranked findings and chains with LOPA, evidence, sources; from contract v1.2 each item carries its `tier` (confirmed / also_found / unconfirmed), its hypothesis where it has one, and the supporting finding IDs (computed); an unconfirmed hypothesis is an item of kind `hypothesis` (R50) |
| `GET /runs/{id}/worksheet` | filters | All rows with origin and override state |
| `GET /runs/{id}/coverage` | — | Checked versus total per list; failed questions |
| `GET /runs/{id}/records/{record_id}` | — | Any record with parents, model calls, tool calls |
| `POST /runs/{id}/overrides` | target_id, action, new_value, reason, by (display name) | Record an override (targets include recommendations; `answer` answers an engineer question); returns 403 on a `recorded` run (read-only) |
| `GET /runs/{id}/export.xlsx` | — | Excel worksheet |
| `GET /runs/{id}/export/coverage.json` | — | Coverage report |
| `GET /runs/{id}/export/run.json` | — | Full JSON dump of the run |
| `GET /demo` | — | Preloaded plant and recorded run; no credits used |
| `GET /budget` | — | Spend by environment and model, remaining, live-run availability |
| `POST /internal/runs/{id}/advance` | secret header | Runs the next step; called by the previous step (not public) |

TypeScript types are generated from `contract/openapi.json` with `openapi-typescript`.

### Hosting and deployment
- **Vercel**: frontend, API (Python functions), Postgres through the Vercel Marketplace.
- Vercel Hobby stops a function at 300 seconds; each pipeline step is its own invocation, which ends by calling `POST /internal/runs/{id}/advance` (authenticated with a server secret) to start the next; the live view polls instead of streaming. The live-run sample plant must finish every step in under 5 minutes (tested by Oct 24). If a step cannot fit: Vercel Pro (800 s) or Vercel Workflows for that step.
- **Demo mode**: the site opens on a preloaded plant with a cached run, so judges see results with no wait and no credits. It works with zero credits until winners are announced. It is **labelled on screen as a recorded run** (with its date and cost), so it never looks like faked output. The recorded run's export is committed in `cases/demo/recorded/` (no keys). The recorded run is read-only on the server, so one judge cannot change what the next sees; accept/reject choices in demo mode are kept in the visitor's browser only.
- **Live-run button**: runs a small sample plant under a per-run cap, per-visitor rate limit and daily cap; turns off with a message when the budget is empty.
- Benchmark runs on a laptop.
- **One budget, two environments, each enforcing its own allowance:** laptop $19 (development, test #5, benchmark, video) in `budget/ledger.jsonl`; hosted $6 (demo recording, judging period, buffer) in the `spend_ledger` table, because the Vercel filesystem is read-only. Each refuses calls past its own allowance without reading the other. The weekly Token Factory dashboard check reconciles the two against the real balance.
- **Tavily in demo mode:** the recorded run replays its real Tavily results; the live-run button makes real Tavily calls.
- **Secrets**: Nebius and Tavily keys only in server environment variables; never in the browser, repo or chat.

---

## 12. Frontend: seven screens

1. **Plant input** — upload, validation results, missing facts and assumptions flagged.
2. **Sections** — the plant as a diagram with the proposed cut, suggestions with reasons, confirm button.
3. **Live run** — the agent timeline: each orchestrator decision with its one-line reason, each specialist dispatch, each tool call and which Nemotron tier made it, as it lands; coverage filling up; cost so far.
4. **Shortlist** — top findings and chains as cards ranked by tier, then LOPA gap.
5. **Finding detail** — the chain, protection layers credited or not with reasons, LOPA numbers, evidence, CSB precedent, sources, accept/reject.
6. **Worksheet** — full table, filterable, editable, origin tags; Excel export.
7. **Coverage** — checked versus total for every list, failed questions.

Stack: React, TypeScript, Vite. Built against mock responses of the frozen API contract from day 1, then wired to the real API.

---

## 13. Evaluation

### Development set
CSB cases D–H (TPC Port Neches, Husky Superior, PCA DeRidder, AB Specialty Silicones, Didion Milling), written as neutral plant data packages with distractors. Used for tuning only; results are reported as development numbers, never as the headline.

### Test #5 (Phase 2, gate G2)
Same dev cases, three versions:
- **#4**: one big prompt (done).
- **5A**: one prompt plus a step-by-step checklist.
- **5B (core)**: code-built question list, orchestrator and specialist agents, risk-matrix ranking — what exists at G2. The full pipeline (connector, LOPA, evidence) is re-run on D–H after Phase 3 as a development check.

Plus the four-tier comparison on 50 fixed questions. Hand-scored.

**G2 result (Oct 16): failed.** 5B found the real cause on D and G but ranked it at folded rank 23 and at 229; 5A hit G at #3 and missed D. See `docs/decisions.md`.

### G2b (Phase 2b, R50)
- Cases **E and F** only (D and G are spent as gate cases; H is excluded for recognition, R37).
- Configurations: **hybrid** (the tiered list, model-ordered tiers, scored), with `hybrid-codeorder`, `5a-plant` and `5b-from-hybrid` written from the same run at $0 and scored automatically only; and 5A.
- Per case: hybrid run → hand-score its top 10 → commit → 5A run → hand-score → commit. Hit rule: only a hit in the top 3 passes; a partial does not.
- **Passes** if the hybrid has a hit in the top 3 on at least one of E and F, and on as many cases as 5A. Hand scores are Bhargavi's (fallback fixed in `docs/decisions.md`).

### Held-out benchmark (Phase 6, gate G3)
- About 6–10 lesser-known accidents not used in any earlier test, from several countries (CSB plus ARIA, eMARS, Dutch Safety Board, UK HSE and national reports; aim for about half outside the US). Written by **a separate Claude session**, run once as a scheduled task on Oct 13 on Bhargavi's computer and instructed not to read this repo's code, prompts or specs, as the plant looked before the accident, with unrelated equipment mixed in. The cases and keys live in the `guideword-heldout` folder outside this repo, which Bhargavi owns and does not open before Phase 6 (an honour system, stated in the README); each file is sealed by SHA-256 in `SEALS.txt`, copied here as `bench/heldout-seals.txt`.
- A case qualifies only if its source describes the plant in enough detail to rebuild it (equipment, chemicals, procedures, safeguards) and states the root cause. Famous accidents (Bhopal, Texas City, Flixborough, Seveso) are excluded: models recognise them, so they would test memory, not reasoning.
- **Memorisation probe**: each model is first asked whether the case is a real accident it knows; a correctly named case is excluded for that model.
- Configurations: Guideword on the routing chosen in test #5; baseline 1 = one big prompt; baseline 2 = plain checklist with no reasoning.
- **Auto-score**: where the answer key's cause lands in the ranked shortlist (top 3 / top 10 / missed), after text normalisation.
- **Human score**: Bhargavi scores every answer against the sealed keys (hit / partial / miss, with reason); disagreements with the auto-score are listed.
- **Results table**: hits out of n with a 95% confidence interval per configuration, cost and time per run, every failure listed. Generated from run records, never typed by hand. Reported as "x of n", never a bare percentage.
- After G3, held-out cases and keys are published in the repo so judges can rerun the benchmark.

### Headline claim
"Found what the original hazard review missed, on real accidents it had never seen" — stated only with the measured x of n.

---

## 14. Demo and video

**The one moment:** the Williams Geismar reboiler — a hazard the plant's own reviews missed three times. Guideword ranks it at the top, shows the chain (isolated from relief + heat still reaching it), the LOPA gap with zero credited protection, and the CSB report.

Video (under 3 minutes, a pitch, not a tutorial):
1. Problem (≈20 s): the real accident; a review was done and missed it.
2. Guideword running (≈60 s): plant loaded, sections confirmed, then the agent timeline: the Ultra orchestrator dispatching specialist agents on cheaper Nemotron tiers, calling tools, coverage filling up, shortlist forming.
3. The moment (≈40 s): the reboiler finding, chain, LOPA gap, evidence.
4. The numbers (≈40 s): held-out benchmark x of n vs baselines; coverage counts; cost per study per tier.
5. Close (≈20 s): who it's for; the engineer decides.

Nebius Token Factory and each Nemotron model are named out loud. No copyrighted music.

Schedule: script written in Phase 1 (by Oct 15, before the frontend screens are built); rough cut recorded Oct 20 with whatever exists; final cut Oct 27–28.

---

## 15. Phases

Each phase has a spec (`specs/phase-N.md`) written and approved before it starts: goal and what the video shows; in scope / out of scope; interfaces; acceptance tests; done-when checklist; live-call cost limit.

| Phase | Dates | Builds | Ends with |
|---|---|---|---|
| 0. Foundations | Oct 12–14 | Bootstrap commit; smoke test on all four models; repo, CI, licence, `CLAUDE.md`; price and routing config; budget-capped live-call script; schema package; reference tables; dev cases D–H as plant files; API contract and mock server; simulator, DEXPI and CAMEO feasibility | **G1** |
| 1. Plant and questions | Oct 14–15 | Plant loading and validation; sections (rules, suggestion logic with a stand-in suggester, confirm; the live Super call is wired in Phase 2); question builder; coverage counts | Exact question counts on D–H |
| 2. Gateway and agents | Oct 15–17 | Gateway with JSON rules; six specialist agents; orchestrator core (`check_coverage`, `dispatch_specialist`, `finish` guard); `reactivity_lookup` (the chemistry agent has it at G2); risk-matrix ranking; test #5 harness and run | **G2** |
| 3. Reasoning | Oct 18–20 | Connector (`propose_chains`) with ID validation; LOPA engine (`run_lopa`) with independence check; shortlist; recommendations | Shortlist per dev case |
| 4. Tools and evidence | Oct 19–22 | Remaining tools: `web_research`, `search_precedent`, `physics_calc`, `run_simulation`; precedent index; simulator wrapper around the open-licence Tennessee Eastman package | Evidence on top findings |
| 5. Frontend | Oct 14–25 (parallel, from `contract-v1`) | Seven screens on mocks, then real API; rough video cut Oct 20 | Demo moment works on screen |
| 6. Benchmark | Oct 22–24 | Memorisation probe, held-out runs, baselines, scoring, results table | **G3** |
| 7. Ship | Oct 24–28 | Vercel deploy, demo mode, live-run button, README, feedback write-up, final video | **G4**; submit Oct 29 |

### Gates

| Gate | Date | Pass condition | If it fails |
|---|---|---|---|
| G1 Foundations | Oct 14 (morning) | Smoke test passed per model (JSON schema, tool calling, reasoning on/off, cost per call); schema frozen; API contract frozen; LOPA source and CAMEO data confirmed; dev cases D–H validate; simulator and DEXPI feasibility decided; case writer started | Fall back per §16; only a missing schema or contract blocks Phase 1 |
| G2 Architecture | Oct 17 (decided Oct 16: **failed**) | 5B (core) puts the real cause in the top 3 on cases D and G, hand-scored | Stop and rethink before building further; use 5A if it matches 5B |
| G2b Hybrid | Oct 17–18 | The hybrid (R50) has a hit in the top 3 on at least one of E and F, and on as many cases as 5A, hand-scored | Stop; the pitch reports the finding honestly (the pipeline finds, the whole-plant pass ranks) and Phase 3 is re-planned |
| G3 Proof | Oct 24 | Held-out benchmark run and hand-scored | Report honestly; pitch leans on coverage and LOPA |
| G4 Dry run | Oct 28 | Devpost draft saved; repo public with licence; demo works logged out; video under 3 min; feedback written | Cut the last unfinished feature, never the video |

### Feature dates (if a feature is not working by its date, it appears in the pitch as "next" and its time goes to the video)
- Simulator running Tennessee Eastman faults: Oct 22.
- Maintenance and dust specialists: Oct 20.
- Live-run button within the 5-minute step limit: Oct 24.

---

## 16. Pending verification in Phase 0 (decided fallbacks)

| Item | Fallback if it fails |
|---|---|
| `json_schema` output per model | JSON mode plus Pydantic validation |
| Tool calling on Ultra | Agent loop with JSON "next action" output, parsed by code |
| Reasoning on/off via Token Factory | Larger token limits and length-failure detection |
| Rate limits | Lower concurrency |
| Free citable LOPA source | **Resolved Oct 11:** EGPC-PSM-GL-015 (CCPS typical values) |
| Tennessee Eastman simulator | **Resolved Oct 11:** use the open-licence `tennessee-eastman-profbraatz` package |
| Tennessee Eastman DEXPI file | **Resolved Oct 11:** no public file found; importer moves to "next" |
| Tavily credit balance | Cap searches per run |

**Open items for the Phase 3 spec** (closed by the Phase 3 spec, 2026-10-18; see `docs/decisions.md`):
- Piping leak frequency by line size: C20 always maps to the ≤150 mm event; lines with `size_mm` > 150 may need IE-PIPE-LEAK-L. **Closed (P3-4):** C20 on a line with `size_mm` > 150 uses `IE-PIPE-LEAK-L`, otherwise `IE-PIPE-LEAK-S`; a missing `size_mm` → `S`, flagged "size assumed ≤ 150 mm"; one rule in `ranking/likelihood.py`, so screening and LOPA agree.
- Human-error frequency choice: C14–C17 always map to IE-HE-MONTHLY; no plant fact gives task frequency. **Closed (P3-5):** C14–C17 stay on `IE-HE-MONTHLY`, flagged "task frequency assumed — engineer to confirm".
- The code rule for conditional modifiers: release phase, release-rate band, event type and operating pattern have no plant fact or rule yet (likelihood must never come from a model). **Closed (P3-3):** none applied in Phase 3; each LOPA record lists the modifiers it did not apply, with "no plant fact or rule". Revisit with a code rule after the hackathon.

---

## 17. Standing rules

- Code owns completeness and arithmetic; data owns facts; Nemotron owns judgment, always with a reason.
- No one tuning prompts sees a held-out case before G3.
- Accidents a model recognises by name do not count.
- No API keys in code, repo history or chat.
- No Operon code; no reading of P&ID images.
- Model output is never edited in place; engineer changes are overrides.
- Every number on screen traces to a plant fact, a model call or a published table.

---

## 18. Testing and repo

Deterministic parts are tested without model calls; model-dependent steps replay cached responses. CI runs on every push and costs nothing.

| Test | Checks |
|---|---|
| Question builder | Exact counts per list for each dev case; no-flow lines always get their own section |
| LOPA engine | Hand-worked examples match; shared-component protection gets no credit; isolated relief gets no credit (the Williams Geismar case, inlet valve closed, gets none); an open, unlocked inlet valve gives `pfd_if_isolatable`; a `per_metre_year` or `per_lift` cause with its multiplier fact missing gives an incomplete record naming the fact, never a default frequency |
| Chain validator | Any link that is not a finding or fact ID rejects the chain |
| Orchestrator guards | `finish` refused while questions are open; duplicate dispatch costs nothing; step and spend caps stop the run; specialist agents stop after 2 tool steps |
| Gateway | Cache hit costs zero; budget guard refuses over-cap calls; missing model falls back |
| Full pipeline | Replay of one dev case from the committed fixtures in `bench/replay/<case>/` gives an identical shortlist (`response_cache/` stays a git-ignored local cache) |
| Live smoke test | One small plant end to end on real models, cost logged (daily, by hand) |

```
guideword/                public repo, Apache 2.0
  CLAUDE.md               rules every Claude Code session follows
  PROJECT.md              this file
  specs/                  phase-0.md … phase-7.md, and an approved phase-N-plan.md for each
  backend/guideword/      the package
  backend/tests/
  frontend/               React app
  reference/              versioned tables with source columns
  cases/dev/              dev cases D–H (plant files)
  cases/dev/keys/         dev answer keys (not secret)
  cases/dev/source/       kill-test #4 source packages
  cases/demo/             demo plants (Tennessee Eastman, Williams Geismar)
  cases/demo/recorded/    recorded demo run export (no keys)
  prompts/                versioned prompt templates
  config/                 model prices, routing, caps
  contract/               OpenAPI, JSON Schemas, mock fixtures
  scripts/                live_call.py, smoke_test.py, budget_status.py
  budget/                 ledger-<gate>.jsonl snapshots (live ledger.jsonl is git-ignored; no keys, no prompts)
  docs/                   decisions, feedback log, smoke-test results, case template
  docs/smoke/             raw smoke-test responses (no keys)
  .gitattributes          LF line endings for all text files
  bench/                  runner config and published results
  bench/replay/<case>/    committed replay fixtures for the CI replay test (no keys)
guideword-heldout/        folder outside this repo, owned by Bhargavi and pushed to a private GitHub repo
                          unopened until Phase 6: held-out cases and keys, sealed by SEALS.txt (copied as bench/heldout-seals.txt)
```

### Build method
- Two Claude Code sessions in parallel git worktrees: backend (phases 1–4, 6) and frontend (phase 5).
- Each phase: spec approved → Claude Code's plan (`specs/phase-N-plan.md`) approved → tests written → code → diff reviewed → merged.
- Schema and API contract changes go through a reviewed pull request, never a quiet edit.

---

## 19. Positioning

| | Typical AI HAZOP tools (Uptime AI, Gordium, Kenexis, Kairos, Salus) | SafeFlux (same hackathon) | Guideword |
|---|---|---|---|
| Coverage | Draft rows; no proof nothing was skipped | Searches one toy tank | Every question built by code; coverage report |
| Proof of accuracy | None published | No real-world validation | Held-out benchmark on real CSB accidents, with memorisation check and baselines |
| Ranking | Model or risk matrix | Threshold verdicts on its simulator | LOPA protection gap with independence check |
| Evidence | Varies | Simulator on a 2-variable tank | Physics calculations, CSB precedent, Tennessee Eastman simulator |
| Models | Single | Single, not yet called on Nebius when inspected | Ultra orchestrator, specialist agents on cheaper tiers, measured routing |

"Multi-agent" alone is not our difference (DWSIM HAZOP Bridge already uses several LLM agents). The differences are proof on real accidents, guaranteed coverage, LOPA ranking and the measured Nemotron routing.

---

## 20. Evidence so far (kill tests)

| Test | Result |
|---|---|
| #1 Simulator | Tennessee Eastman ran 20 faults in 56 s; cooling loss tripped on high pressure at 1.05 h while temperature fell |
| #2 Famous accidents | Ultra found the Williams Geismar cause without recognising the accident; the other two cases were recognised and excluded |
| #3 Lesser-known accidents | All tiers passed, but the write-ups contained hints; not used as evidence |
| #4 Plant only, no hints | Ultra: real cause in top 3 on 2 of 4 unrecognised cases (3 counting the under-ranked dead leg); missed the chemical pair. Nano 0 of 5. These misses drove the code-built question list, specialist agents and code ranking |

---

## 21. Lessons from earlier hackathons, applied

| Earlier mistake | Rule here |
|---|---|
| Engineering judges never saw | Every feature must appear on screen or in the video; infrastructure gets one line in the video |
| Feature-list demos with no single moment | The video is built around the Williams Geismar moment |
| Video and README left to the last day | Script by Oct 15, rough cut Oct 20, final Oct 27–28, submit Oct 29 |
| Claims without proof | Every number comes from run records; benchmark reported as x of n |
| Not meeting the sponsor's requirements | Rules checked line by line (§4, §25) |
| Split focus | Nebius gets its own schedule and gates; nothing in this plan depends on other projects |

---

## 22. Non-build tasks

| Task | By |
|---|---|
| Held-out cases written (done Oct 13: a separate scheduled Claude session, told not to read this repo; sealed in `SEALS.txt`) | Oct 12 |
| Facilitator call: one 30-minute call with a HAZOP facilitator (Haber network, then LinkedIn); questions: what takes the most prep time, would a measured hit rate on past accidents make you trust a draft, what would make you refuse to use it; capture one quotable line for the video and README | Oct 16 |
| Feedback log, kept from day 1: 401 from using the wrong key, answers cut off at the token limit, Unicode hyphens breaking scoring, Nano slowness, catalog deprecations with no automatic rerouting, plus anything new | Ongoing |
| Confirm the City Winner attendance rule in the Nebius Discord (FAQ and resources page disagree; official rules require attending a Builders & Brews event) | Oct 13 |
| Claim the second $25 Token Factory grant if not yet claimed | Oct 12 |

---

## 23. Known limits (said openly in the pitch and README)

- Plant data entry is the main adoption blocker for AI HAZOP tools. Guideword takes a structured plant file; a DEXPI importer is the path to reading engineering software exports.
- LOPA values are order-of-magnitude, from generic public tables; companies should load their own.
- The benchmark is small (x of n with a wide interval); it shows the method works on unseen accidents, not a certified accuracy.
- Tennessee Eastman valve fail positions and other missing facts are labelled assumptions.
- Decision support only; the engineer and review team decide.

---

## 24. After the hackathon

- Distil Ultra's not-credible and screening judgments into a small fast decision model (e.g. Laya) for bulk screening.
- Company risk matrices and private failure-rate data.
- Larger benchmark with facilitator-reviewed answer keys.

---

## 25. Submission checklist

- [ ] Track: Best Apps and Agents
- [ ] Runtime calls to Token Factory with Nemotron models
- [ ] Working demo URL, no login needed (or credentials in testing instructions), live until Dec 15
- [ ] Public GitHub repo, Apache 2.0 licence visible in About
- [ ] README: setup, how each Nemotron model and Token Factory were used, routing table, benchmark results
- [ ] Project description naming Nebius and NVIDIA; Built With filled
- [ ] Public YouTube video under 3 minutes; Nebius and Nemotron named with audio
- [ ] Feedback on Token Factory, AI Cloud and each NVIDIA model (what for, what worked, what needs work, onboarding, would we build again)
- [ ] Runtime Tavily call in the product
- [ ] No API keys anywhere in repo history
- [ ] Submitted Oct 29
