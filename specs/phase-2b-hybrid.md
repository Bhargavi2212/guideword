# Phase 2b — Hybrid ranking (decision R50, option A)

**Dates:** Oct 16 (plan) · Oct 17 (build + E/F runs) · Oct 18 (G2b, then Phase 3)
**Source of truth:** `PROJECT.md`, `specs/phase-2.md`, the G2 entry in `docs/decisions.md`. If they disagree with this file, stop and ask.
**Status:** draft — becomes active when Bhargavi adds `Status: approved <date>`.

## Why

G2 failed (see the G2 entry). On both dev gate cases the pipeline (5B) **found** the real cause but **ranked** it at 23 (D) and 229 (G). A single whole-plant Ultra prompt (5A) ranked G's cause at #3 for ~1/50th of the cost, and missed D. Generic plant-wide causes (C22, C07, C23) fill the pipeline's top 10.

R50: keep what each did well. A **whole-plant pass** proposes the likely top hazards; the **pipeline** checks every question and supplies evidence for each one. The ranking puts hazards that both agree on first.

## What changes (and what does not)

Unchanged: questions, specialists, validators (R7, R40, R46, R47), severity (R48 scenarios, R49 evidence), LOPA, caps, admission (R13 amendment), replay (R45). No change to any validity rule.

New, in order:

### 2b.1 Whole-plant pass (`plant_screen`, Ultra)

- Runs once, as the first step of every run, before any dispatch.
- Input: the **confirmed plant record (JSON)** as data inside the untrusted-data delimiters, the cause library, and the question kinds. No answer keys, no case names, no source package. This is what the product has at run time. Note: 5A reads the dev **source package** (`cases/dev/source/case_<x>_*.md`, see `bench/test5a.py`), so 5A and plant_screen do not see identical input; the plant JSON keeps the package's words verbatim in `notes`/`text` fields, but the form differs. Record this in the R50 entry.
- Output (json_schema): up to `plant_screen_max_hypotheses` (caps.yaml, start 12) ranked hypotheses, each with
  `rank`, `mechanism` (text), `component_ids` (plant IDs), `cause_id` (library ID or `outside_library` + `cause_text`), `consequence`, `reason`.
- Code validates exactly as for specialist findings: every ID exists in the plant, cause valid for the component type (R46 mapping), `component_ids` non-empty. Invalid → one retry with the error (R41 path), then the bad hypothesis is dropped and logged; the rest stand.
- Records: a new `Hypothesis` record type in `schema/records.py`, ID built in `schema/ids.py` from content like every other ID (`h:<run>:<rank>:<h(normalised mechanism, sorted component_ids)>`), a new event type `hypothesis_added`, model call recorded as usual. The run state machine gains a `plant_screen` step before the orchestrator loop. Routing job `plant_screen: ultra`; prompt `prompts/plant_screen/v1.md` (Claude Code drafts; it may start from `test5a/v1`; Bhargavi reviews; Cowork does not).
- Cost: ~$0.02 per run. It counts against the run cap like any call.
- `plant_screen_max_hypotheses` enters `Run.caps` and the run-ID hash (it changes model input, like R43(b)).
- **Recognition is inherited:** this is the same kind of call as 5A, so if Ultra recognises a public incident, the hybrid benefits too. The held-out cases and the Phase 6 memorisation probe remain the real test; record this in the R50 entry.

### 2b.2 Linking hypotheses to questions and findings (code only)

- **Questions:** a hypothesis links to every question whose section, pair or environment contains any of its `component_ids` (chemicals via equipment contents, as in R40). Deterministic, no model.
- **Findings:** a finding supports a hypothesis when (a) it answers a linked question, and (b) its failing components overlap the hypothesis's `component_ids`, or for pair/env questions the same chemicals, and (c) its cause matches the hypothesis's cause ID, or both are outside-library. Code only.
- Store links on the hypothesis (`question_ids`, `support_finding_ids`). Every link is traceable.

### 2b.3 Hypotheses steer dispatch (the agent part)

- The orchestrator view gains a `priority` block: each hypothesis with its rank, component IDs, cause ID, linked open question IDs and support status. **No mechanism or consequence text**, keeping the existing view rule (`orchestrator/view.py`: never a finding's cause or consequence text).
- `dispatch_specialist` gains an optional `priority: true` (R44 amendment). With `question_ids` omitted, code then selects the agent's **linked** open questions first, in hypothesis rank then ID order, up to `dispatch_max_question_ids`, and only then other open questions. Explicit `question_ids` work as before. All other R44 / no-repeat / bulk-then-hard / deferral rules unchanged.
- Orchestrator prompt v2 (Claude Code drafts, Bhargavi reviews) must mention the `priority` option; its wording is not specified here.
- Code does not force the order; it reports it. A run summary line counts how many linked questions were answered before the first non-linked dispatch.
- Effect: the questions that matter most are answered before any cap stop.

### 2b.4 Final ranking (spec 2.6 amendment)

Three tiers, in this order, each one line per scenario as in R48:

1. **Confirmed:** hypotheses with ≥1 supporting finding, in hypothesis rank order. The line shows the supporting scenario's severity and likelihood (R48/R49) and the hypothesis rank.
2. **Also found:** pipeline scenarios not linked to any hypothesis, in the current 2.6 order (severity, likelihood, protection adequacy, hash).
3. **Unconfirmed:** hypotheses with no supporting finding, in rank order, flagged "not confirmed by the checks — engineer to review".

- Fold (R48) still applies: a confirmed line is one hypothesis, and the scenarios that support it are folded under it and **not** shown again in "also found"; "also found" is folded as now.
- The scorer and the hand-score sheet read the displayed top N across tiers.
- Plant_screen's own top 10 is also written as config `5A-plant` at $0 (same scoring), so the effect of plant JSON vs source package input is visible.

### 2b.4a Phase 3 shortlist (PROJECT.md §5 Step 6 amendment)

PROJECT.md ranks the Phase 3 shortlist by **LOPA gap** after a risk-matrix screen picks the top 10 for LOPA. With R50:
- The **screen** is the tiered list above: its top `lopa_top_n` lines get LOPA.
- The **shortlist** sorts by tier first, then LOPA gap within a tier. Gap never lifts an "also found" line above a "confirmed" one.
- Chains (Phase 3) enter the shortlist under the tier of their highest-ranked member finding.
Decide this now so Phase 3 isn't re-planned later.
- From the same run, code also writes the **pipeline-only** order (tier 2 rules applied to all scenarios), labelled `5B-from-hybrid`, at $0. That gives a pipeline comparison on E/F without a second paid run.

### 2b.5 Contract (v1.x bump)

Latest tag is `contract-v1.1`; section-rejections (9a) was promised `v1.2` and is not tagged yet. Use the next free tag at merge time; grep before tagging.
- `RankedFinding` in `ranking/rank.py` is internal, not in the contract. The API surface is `ShortlistItem` (`api/models.py`, served at `GET /runs/{id}/shortlist`, Phase 3): it gains `tier` (`confirmed | also_found | unconfirmed`), `hypothesis_id` (nullable) and `hypothesis_rank` (nullable).
- New `contract/schemas/hypothesis.schema.json` (record), readable through `GET /runs/{id}/records/{record_id}` like other records.
- Regenerate types; update the mock fixtures so the frontend builds against it from day one.

## Tests (all $0, written first)

- A hypothesis citing an unknown ID → retried, then dropped; the others survive.
- Linking: a hypothesis on a pair links the pair question; a finding with the same pair and cause supports it; a different cause does not.
- Tier order on a fixture: confirmed, then also found, then unconfirmed.
- `5B-from-hybrid` equals the current ranking on a run with no hypotheses.
- Replay of a hybrid run reproduces the hypotheses, links, tiers and stop point (R45).
- A $0 case D run on the fake gateway end to end, with a scripted plant_screen reply.

## Validation (G2b) — rules fixed before any run

- Cases: **E and F only.** D and G are spent as gate cases; H is excluded for recognition (R37).
- Order per case: hybrid run → hand-score its top 10 → commit → 5A run → hand-score → commit → `test5_results.py`.
- R38 holds: a hybrid run that ends `stopped_cap` is reported, not scored.
- **Hand scores are Bhargavi's.** Cowork designed R50 and is not a neutral grader of it; Cowork may explain the rule but does not propose these scores. Record who scored in the G2b entry.
- **G2b passes** if the hybrid has a **hit** in the top 3 on at least one of E and F, **and** on as many cases as 5A. A "partial" does not pass (G2 rule).
- The recognition caveat applies to both 5A and plant_screen; the memorisation probe in Phase 6 and the held-out cases are the real test. Record it, don't use it to explain a result.
- If G2b fails: stop. The pitch then reports the finding honestly (pipeline finds, whole-plant ranks) and Phase 3 is re-planned.

## Budget

- `test_5` has ~$0.59 left. Two hybrid runs (~$0.75 each, cap 1.20) + two 5A runs (~$0.03) need ~$1.55.
- Proposal: move **$1.50 from `benchmark` (8.00 → 6.50) to `test_5` (4.00 → 5.50)** in `caps.yaml`, logged in `decisions.md`. Bhargavi decides.
- The phase cap `"2": 5.00` will block this. The ledger shows phase 2 at $3.406 ($3.404 test_5 + $0.002 development). The gateway checks `phase spent + all held slices + this call ≤ phase cap` (`gateway/client.py`), and a dispatch can hold ~$1.10 of slices (case D run 3). So the second E/F run would be refused mid-run below $5.00. Raise to `"2": 6.50` in the same commit, logged. The $25 total doesn't change; `test_5` allowance is checked the same way, so 5.50 covers it.

## PROJECT.md edits (same PR as this plan; the spec header says stop if they disagree)

- §5: add the plant_screen step before the orchestrator; Step 6 screen and shortlist as in 2b.4a.
- §13 Test #5: add G2b (E and F; hybrid vs 5A; hit rule).
- §15 gates: G2 recorded as failed; add G2b with its date (Oct 17–18) and the "if it fails" line.

## Not changed by this plan

Rule freeze still holds for validity rules (R40, R46, R47). R50 is the post-G2 rethink that 2.11 calls for, not a new validity rule. Still pending and untouched: PR 12b (kill test #4, four-tier comparison), PRs 9a/9/10, `budget/ledger-g2.jsonl`, the `g2` tag, the video script.

## Order of work

1. This plan approved (Bhargavi).
2. Contract bump (2b.5) — first, so the frontend can start on the mock server the same day.
3. 2b.1 → 2b.2 → 2b.4 (test-first), then 2b.3 with orchestrator prompt v2 (review).
4. $0 fake run. Budget move. E hybrid, score, F hybrid, score, 5A on E and F, score.
5. G2b entry in `decisions.md`.

**In parallel from Oct 17:** Phase 5 frontend in its own worktree on the mock server. The tiers change one list view, not the screens.
