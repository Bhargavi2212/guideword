# Phase 3 — Reasoning: chains, LOPA, shortlist, recommendations, review

**Dates:** Oct 18–20 · **Ends with:** a shortlist with LOPA records, chains and recommendations on dev cases D, E, F and G
**Source of truth:** `PROJECT.md` (§5 Steps 5, 6 and 8; §10; §11; §12; §16 open items; §18 LOPA tests). If this spec and `PROJECT.md` disagree, stop and ask.
**Status:** approved 2026-10-18

## Goal, and what the video shows

A finished run ends with a **shortlist** an engineer can act on: each line in its R50 tier, with its LOPA record (initiating frequency, every protection layer credited or not with the reason, mitigated frequency, tolerable frequency, gap), any chain it belongs to, and a recommendation where the gap is above 1. The engineer can accept, reject or edit each row, and export the worksheet to Excel.

Video beat: the shortlist card for the demo plant's top line → the chain → the protection layers, with the relief valve shown **"no credit — inlet valve closed"** → the gap → the recommendation.

## Decisions this spec asks Bhargavi to make (recommended answers given)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| P3-1 | Chains, LOPA and recommendations run as **fixed code steps after the analysis**, not as orchestrator tools (`propose_chains` and `run_lopa` leave the §5 tool table; the `finish` guard no longer waits for LOPA). | Yes | Same pattern as severity today; the agent still drives the analysis, which is what the video shows. As tools, they'd change every orchestrator request. |
| P3-1b | Existing finished runs (D, E, F, G) get the new steps by being **extended in place**: same run ID, step set to `chains`, status back to `running` until the new steps finish; earlier records never change. **Not** by starting new runs. | Yes | A new run can't replay at $0. The run ID hashes the caps, so any cap change gives a new run ID. The screen's first line is `Request marker: <run ID>` (Oct 16 fix), so the screen request changes and misses the cache. That changes the hypotheses and the orchestrator's priority block, so every orchestrator call misses too: a full re-run, about $1–2 per case. Extending costs only the new steps. |
| P3-2 | The new steps get their **own per-run allowance**, `post_spend_cap_usd`, a Run field that is **not hashed** (like `spend_cap_usd`; contract v1.4), start $0.30. The gateway's run check uses it during post-analysis steps; the analysis cap and its severity reserve are unchanged. | Yes | Otherwise extending a run would mean changing its hashed caps. |
| P3-3 | Conditional modifiers (§16 open item): **none applied in Phase 3**. Each LOPA record lists the modifiers it did not apply, with "no plant fact or rule". | Yes | Likelihood must never come from a model, and no plant fact gives release phase, rate band, occupancy or operating pattern. Leaving modifiers out raises the mitigated frequency (conservative) and is honest. Revisit with a code rule after the hackathon. |
| P3-4 | Piping leak size (§16 open item): C20 on a line with `size_mm` > 150 uses `IE-PIPE-LEAK-L`; otherwise `IE-PIPE-LEAK-S`; missing `size_mm` → `S`, flagged "size assumed ≤ 150 mm". | Yes | One rule, in `ranking/likelihood.py`, so screening and LOPA always agree. |
| P3-5 | Human-error frequency (§16 open item): C14–C17 stay on `IE-HE-MONTHLY`, flagged "task frequency assumed — engineer to confirm". | Yes | No plant fact gives task frequency. |
| P3-6 | What "confirmed" requires (G2b backlog item 2): **no change in Phase 3.** | Yes | Any tightening can't be validated on D–G (spent) and must not be tuned before the held-out run. Recorded as a known limit; revisit only with a rule written before Phase 6 opens the held-out cases. |
| P3-7 | Held-out cost plan (G2b backlog item 1): **claim the second $25 Token Factory grant now** (§22, still open), and set the Phase 6 per-case cap from the measured E/F cost. | Yes | `benchmark` has $4.50: about 3 full runs at $1–2 each, not 6–10. Cutting coverage to save money would weaken the claim the benchmark exists to support. |

## In scope

### 3.1 Connector — chains (§5 Step 5)
- One Ultra call per run (routing job `connector`, prompt `prompts/connector/v1.md`, drafted by Claude Code, reviewed by Bhargavi; Cowork does not write or review it).
- Input: one line per **scenario** (R48: cause, components, section), with ID, cause, consequence, components and severity; plus the plant record as data. Within `connector_max_input_tokens`; if over, keep the top scenarios by the R50 tier order and log how many were left out.
- Output: up to `connector_max_chains` (caps.yaml, start 10) chains: ordered links, description, reason.
- Code validation: **every link must be an existing finding ID or plant fact ID**, at least 2 links, at least one link a finding. Any other link rejects the chain, and the rejection is logged with its reason. Misused terms, or more than two independent failures, are **flagged, never filtered**.
- A chain's severity comes from a **chain-severity step** after the connector, using the same severity classes and rules, with chains in their own batch. The current severity prompt (v2) is built around a finding's question, cause and components. Whether a chain fits it as-is or needs `severity_chain/v1` is Claude Code's call in the plan, and it's a prompt, so Bhargavi reviews it. The `Chain` record gains `severity_class` and `severity_reason` (contract v1.4, mirroring `Finding`); today it has nowhere to hold them. Its initiating frequency is its **first finding link's** frequency, by the same `likelihood()` function. The other links are conditions and are never multiplied in, which is conservative. Chains are never ranked down for needing two failures.
- A chain takes the tier of its highest-ranked member (§5 Step 6.3).
- ID `ch:<sorted links joined by +>`; event `chain_added`.

### 3.2 LOPA engine (§5 Step 6.2) — code, with one Ultra argument per batch
- **Which lines.** PROJECT.md says both "LOPA for every high-severity finding" (Step 6.2) and "LOPA on the top `lopa_top_n`" (Step 6.1). Resolved here:
  - **Full LOPA**, with Ultra's layer argument, on the top `lopa_top_n` (10) confirmed and also-found lines, plus every chain.
  - **Code-only LOPA** on every other S4–S5 line: no model call, every candidate layer marked "not argued — no credit". The gap is conservative and labelled.
  - Unconfirmed lines get no LOPA and are listed after (R50).
- **Target.** A line is a scenario (R48), so its LOPA target is the line's **lead finding** ID; for a chain, the chain ID. `ShortlistItem.unsure` comes from the lead finding's confidence.
- **Initiating frequency:** the same `likelihood()` used for screening. Missing multiplier fact → record `complete: false`, naming the fact; **never a default**. Outside-library → assumed frequency, flagged.
- **Candidate layers, chosen by code:**
  - safeguards with a `layer_type` whose `protects_id` is in the scenario's section or failing components;
  - every relief device whose `protects_id` is in the scenario's section or failing components. There is no code rule for "overpressure scenario", and inventing one would be a new detection rule, so code lists the device and Ultra's argument says whether it applies. The §5 relief rule then sets the credit: the `relief_kind` row, and the inlet valves decide `pfd`, `pfd_if_isolatable` or no credit.
- **Ultra's role** (job `lopa_argument`, prompt `prompts/lopa_argument/v1.md`, Claude Code drafts, Bhargavi reviews): for each candidate layer, *applies to this scenario: yes/no, with a reason*. It never sees or sets a PFD, and never adds a layer that code didn't list.
- **Code decides credit:**
  - no credit if any of the safeguard's `component_ids` is among the cause's failing components;
  - no credit if it shares a logic solver with the failing control loop, where its `protection_layers.csv` row requires independence;
  - no credit for a safeguard with no `layer_type`;
  - relief inlet-valve rules as in §5.
  - Each layer is shown credited or not, with the reason.
- Mitigated = initiating × Π(credited PFD). Modifiers: none (P3-3). Tolerable from `tolerable_frequencies.csv` by severity. Gap = mitigated ÷ tolerable. Shown as orders of magnitude.
- ID `lopa:<target id>`; event `lopa_done`.

### 3.3 Shortlist (§5 Step 6.3)
- Tier first (R50), then gap within a tier (largest first; incomplete LOPA after complete, flagged). Gap never lifts an also-found line above a confirmed one.
- `GET /runs/{id}/shortlist` built for real (contract v1.2 `ShortlistItem`: tier, hypothesis, support, finding or chain, LOPA, recommendations). Evidence stays empty until Phase 4.

### 3.4 Recommendations (§5 Step 6.4)
- For each shortlist line with gap > 1: one Ultra batch call (job `recommendation`, prompt `prompts/recommendation/v1.md`, Claude Code drafts, Bhargavi reviews) proposes an action with a reason.
- ID `rec:<target>:<h(normalised action)>`. No number comes from the model.

### 3.5 Review and export (§5 Step 8; endpoints marked Phase 3 in `NOT_BUILT_PHASE`)
- `POST /runs/{id}/overrides`: every override action, including `change_credit`, `change_severity` and `answer`; 403 on a recorded run.
  - `change_credit` targets the LOPA record (`lopa:<target>`), with `new_value = {layer_id, credited}`, so the record ID convention doesn't change.
  - `change_severity` targets a finding or chain, with `new_value = {severity_class}`. The gap is recomputed on read.
- `GET /runs/{id}/worksheet` with origin and override state. **One row per finding** (unfolded: the worksheet is the full record, the shortlist is the folded view), plus one row per question that has no finding (not credible, failed, or open), with its status. Coverage stays visible in the export.
- `GET /runs/{id}/export.xlsx` with the §5 Step 8 columns.
- `GET /runs/{id}/export/coverage.json` and `GET /runs/{id}/export/run.json`.
- Overrides never edit model output; the views apply them on read.

### 3.6 Run machine
Steps: `plant_screen → analysis → severity → chains → chain_severity → lopa → recommendations → ranked`. The connector reads finding severities, so `chains` must come after `severity`. Each step resumes on its own; a cap stop in a post-analysis step leaves the run `stopped_cap` with the analysis intact. R38 still applies: a `stopped_cap` run is reported, not scored.
- **Extension never changes a hashed run field** (`caps`, `prompt_versions`, `routing_config`, …); otherwise the run's stored inputs would no longer rebuild its ID. Two consequences:
  - Values it needs that aren't in the stored caps, such as the new `connector_max_chains`, are read from the current config.
  - The new prompts' versions (`connector`, `lopa_argument`, `recommendation`, and chain severity if it gets its own) live on each `ModelCall`, as today, and in one `run_extended` event that lists the config and prompt versions the extension used. Add that event type in contract v1.4.
- `scripts/extend_run.py <run_id> --post-cap 0.30` (P3-1b) extends a finished run. It refuses runs that already have a `chains` step done, and runs whose analysis isn't finished.
- **D and G runs predate R50** (no hypotheses): extended, they show every line as "also found", labelled "pre-R50 run". If an old run's records fail to load on the new code, skip it and record why; don't patch old records.
- `run_case.py` and `extend_run.py` take the phase from a flag (`--phase 3`), not the hard-coded `PHASE = "2"`, so Phase 3 spend lands under `phase_caps_usd."3"`.

### 3.7 Demo plant (Cowork, in parallel; not Claude Code)
- `cases/demo/williams_geismar.json`, written by Cowork from the public CSB report, with every fact sourced or marked "assumed". The plant file holds no answer key; the key stays in Cowork's notes.
- It must contain the reboiler, its heat source, and the relief device with its **inlet valve closed**, so the LOPA engine's "isolated relief gets no credit" test (§18) runs on a real plant. Due Oct 19.

### 3.8 Contract v1.4 (first PR, so the frontend builds on it)
- `Chain.severity_class` and `Chain.severity_reason`.
- `Run.post_spend_cap_usd`: not hashed, default 0.
- `ShortlistItem.target_kind` already has `"chain"` and `"hypothesis"`. Check that its `lopa` field carries `severity_class` and the full layer list.
- The `change_credit` and `change_severity` `new_value` shapes (3.5).
- Fixtures: a chain with severity, a complete and an incomplete LOPA record, a "not argued — no credit" layer, a recommendation.
- One naming note for Phase 5: the R50 tier "confirmed" and the evidence verdict "confirmed" (Step 7, Phase 4) are different things. The UI must label the tier "confirmed by the checks" and the evidence verdict "evidence: confirmed", so they don't read as the same claim.

## Out of scope (Phase 4 or later)
Evidence tools (`web_research`, `search_precedent`, `physics_calc`, `run_simulation`); the precedent index; the Tennessee Eastman wrapper; the frontend (Phase 5, its own spec); any change to analysis-phase prompts, views or validity rules (rule freeze; P3-1).

## Acceptance tests (all $0, written first)
- **LOPA, hand-worked.** Two examples worked out by hand from the reference tables **before** the code exists, committed as fixtures with the arithmetic shown; the engine must match them exactly:
  1. a BPCS-loop cause with one independent alarm-and-operator layer;
  2. the Williams Geismar reboiler: relief inlet valve closed → no credit, gap shown.
- Shared component → no credit. Shared logic solver → no credit. Open, unlocked inlet valve → `pfd_if_isolatable`. All inlet valves locked open → `pfd`. No `layer_type` → no credit.
- `per_metre_year` cause with `length_m` missing → incomplete record naming the fact, no default (§18).
- C20 on a > 150 mm line → `IE-PIPE-LEAK-L`, in both screening and LOPA (P3-4).
- Chain validator: any link that isn't a finding or fact ID rejects the chain; a two-link chain of facts only is rejected.
- Shortlist order: tier, then gap; gap never crosses tiers.
- Overrides: applied on read; model records unchanged; 403 on a recorded run.
- **Extension makes no analysis calls:** extending a finished run (on a $0 fake run) runs only `chains` onward. Every earlier record is byte-identical before and after. The run ID is unchanged.
- **Replay:** a full $0 fake run through all eight steps replays identically (R45), including chains, LOPA and recommendations.
- Code-only LOPA on an S4 line outside the top N: no model call, every layer marked "not argued — no credit".
- The post-analysis cap stops at the cap with the analysis intact; the analysis cap's behaviour is unchanged.
- Export: the xlsx has the §5 Step 8 columns, one row per worksheet row, overrides applied.

## Done when
- [x] P3-1…P3-7 decided and recorded in `docs/decisions.md` (PR 0).
- [ ] Every acceptance test passes; CI green.
- [ ] D, E, F, G re-run on Phase 3 code: analysis replayed at $0; shortlist with LOPA, chains and recommendations written to `bench/phase3/<case>.json`. H is skipped: it is recognised, and a full run costs ~$1.5.
- [ ] Williams Geismar demo plant committed, validated, and run through LOPA. (Committed in #69; validated, and its reboiler run through the LOPA engine as example 2, in PR 7. The demo plant's full run is Bhargavi's.)
- [x] `PROJECT.md` updated (PR 7):
  - §5 Step 4: the tool table and the `finish` guard (P3-1);
  - §5 Step 6.1/6.2: which lines get full or code-only LOPA, and modifiers (P3-3);
  - §11: records and run steps (Chain severity, `post_spend_cap_usd`);
  - §12 screen 4: "ranked by tier, then LOPA gap", not "by LOPA gap";
  - §16: open items closed.
- [ ] Phase 3 spend within its cap; `budget/ledger-g3pre.jsonl` snapshot.

## Live calls and spend
- Add `phase_caps_usd."3": 2.50` (use `development`, $3.27 left).
- Per extended run: connector ~$0.03, LOPA arguments ~$0.04, recommendations ~$0.02, chain severity ~$0.02. About $0.10 per case; 4 cases ≈ $0.40.
- **Demo plant full run:** a new plant pays for its whole analysis. Williams Geismar is small (a few items of equipment), so roughly $0.4–0.8. This was $0.30 in the first draft, which was wrong.
- Total ≈ $1.2–1.5, which leaves about $1.8 of `development` for Phase 4.
- Bhargavi starts every live call. Claude Code makes none.

## Who writes what
- **Claude Code:** plan, code, tests, the three prompts (connector, lopa_argument, recommendation).
- **Bhargavi:** decisions P3-1…P3-7, prompt reviews, live runs, merges.
- **Cowork:** this spec, the Williams Geismar plant file (due Oct 19; LOPA example 2 depends on it), and the **two hand-worked LOPA examples themselves**: written from the reference tables, with every row ID and every multiplication shown, before Claude Code writes the engine, so the fixture is independent of the code. Cowork does not write or review prompts.

## Phase 2 close-out, before Phase 3 starts
- `docs/decisions.md`: the G2b deviation entry says "E was hand-scored by Bhargavi afterwards". The CSV shows E's 20 rows were scored by the grader fallback (two fresh Claude agents), with reasons marked `grader:`. Correct the entry so provenance matches the CSV.
- Phase 2 boxes still open:
  - routing for Phase 3: the four-tier table has validity, latency and cost, but **no hand scores**. Record "routing unchanged (Lightning bulk, Super hard, Ultra orchestrator and severity), decided on validity and cost; four-tier accuracy not hand-scored". Hand-scoring 200 rows isn't affordable this week.
  - CI green on `main`;
  - the `ledger-g2` and `g2` items, which already exist, so tick them.
