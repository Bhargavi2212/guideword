# Phase 9 plan — Credible-first ranking

Status: **approved 2026-10-30** (Bhargavi's answers 1–12 below; her added task is 9.0).

One branch, `next/credible-ranking`, in the worktree `D:\Hackathon\guideword\guideword-next`,
cut from `main` at `40f4052`. Small Conventional Commits, one or more per item. No pull request
to `main` and no merge (Bhargavi, 2026-10-30). $0: fake gateway and recorded runs only.

## Gaps found on the second reading (v1 → v2)

| # | What the note asks for | v1 | v2 |
|---|---|---|---|
| G1 | Stage 1 plant model holds operating modes, **open changes and known impairments**; accidents cluster there (PT Note 135, Geismar) | Out of scope as a schema change | 9.2: optional `changes` and `impairments` blocks, a `change` question kind, impaired layers get no credit and sit on List C |
| G2 | Stage 3: analogous incidents attached **per candidate, before ranking**, as evidence and prior | Precedents only on the top lines, after everything | 9.4: index search and Super judge per candidate before the ranking |
| G3 | Stage 4: the sweep is a recall net; **new mechanisms it finds join the candidate pool** | Sweep findings could never enter List A | 9.5: a final re-rank after LOPA over candidates + chains + unmatched sweep findings |
| G4 | Stage 5: **narrow verification against cited spans**; an unverifiable claim is discarded | Verification was only the R50 support rule | 9.6: `verify_hypothesis` (Super) with code-checked quotes; `contradicted` and `ungrounded` states |
| G5 | Severity shown beside credibility, never multiplied | List A "shows severity", but an unsupported candidate had none | 9.4: every candidate rated by the severity job with a reason |
| G6 | Baselines at **equal spend** | Baseline B at $0.02 against a $1 pipeline | 9.10: baseline B at matched cost (N prompts fused by RRF) |
| G7 | An LLM judge only after κ ≥ 0.70 against experts, from another model family | Not built | 9.10: judge job, `judge_validate.py`, placeholder tier |
| G8 | Case-writing protocol: strip dates, sites, outcomes; a second person checks | Protocol doc only | 9.10: `case_lint.py` |
| G9 | The engineer signs: changes are theirs and visible | No override on List A | 9.7: dismiss and promote overrides with reasons |
| G10 | Chains (the Geismar line is one) compete on credibility | Chains only on List B and under candidates | 9.5: chains are candidates in the final re-rank |
| G11 | LOPA runs on what matters | LOPA top-N by code order only | 9.8: List A's lines plus code order |
| G12 | The engineer sees why | No ranking reasons in the UI; new steps unnamed on the timeline | 9.11 |

## Per item

### 9.0 Fifty development cases — `docs`, `feat(bench)` (tooling only by Claude Code)
- `docs/case-writing-v2.md` (the protocol for the separate case-writer session), `cases/dev2/`
  with README and selection-log template, `scripts/case_lint.py` with
  `reference/case_lint_terms.csv` (sourced word lists), `scripts/dev2_check.py`.
- Tests first: lint flags a year, an outcome word and a company-like noun in a synthetic package
  and passes a clean one; the check refuses a package without a plant file or a key without the
  template's fields; a dev2 case loads with the development label.
- **Open question (CLAUDE.md §5, §13):** Claude Code may not open or summarise accident reports,
  so it cannot write the 50 cases itself. Proposed: Bhargavi starts a separate case-writer session
  in a folder outside the repo, pointed at `docs/case-writing-v2.md`, as for K–S. If she would
  rather amend §5 for this branch, that is her decision to record first; the note's own estimate is
  30–60 minutes of writing and review per case.

### 9.1 Hypothesis card — `contract(screen)`
- `prompts/plant_screen/v4.md`; `config/routing.yaml` `plant_screen: v4`; `config/caps.yaml`
  `plant_screen_max_hypotheses: 20`.
- `schema/enums.py`: `OperatingMode`, `MechanismClass`. `screen/schema.py`: the card fields,
  the fact-ID check (keyed on the prompt version so v3 answers still validate).
  `schema/records.py`: `Hypothesis` gains the fields as optional plus `pass_number` (default 1).
  `schema/ids.py`: v4 `hypothesis_id` takes the pass. `contract/schemas/` re-exported.
- Tests first (`backend/tests/screen/test_v4_card.py`): required fields; unknown fact ID drops
  the hypothesis; a v3 answer still validates; pass number changes the ID only for v4; every v3
  ID in the recorded WG run is unchanged and its replay compares equal (answer 10); stored v3
  hypotheses read with empty fields; every placeholder filled.

### 9.2 Changes and impairments — `contract(schema)`, `feat(questions)`, `feat(lopa)`
- `schema/plant.py`: `Change`, `Impairment`, the two blocks; `schema/validate.py`: errors for
  unknown `object_ids` and `safeguard_id`; `contract/schemas/plant.schema.json`; PROJECT.md §9.
- `screen/link.py`: links through changes and impairments. `questions/build.py`,
  `questions/coverage.py`, `questions/text.py`: the `change` kind. `specialists/routing.py`:
  routed like planned work.
- `lopa/credit.py`: rule 0, "impaired: <impairment id>".
- Tests first: the example plant still validates; a change with an unknown object fails; one
  `change` question per change, in the coverage totals; an impaired layer gets no credit with
  the impairment as reason; the screen prompt renders both blocks.

### 9.3 Holistic passes — `feat(screen)`
- `screen/orders.py` (new), `screen/candidates.py` (new), `screen/step.py` loops the passes
  with distinct markers; `schema/ids.py` `candidate_id`; `config.py` `credibility` block
  (passes, rank orders, ranker, RRF k, sweep candidates, verify top n, conformal minimum),
  hashed into the run's caps; runs stored without it read as one pass.
- Tests first: each pass sees the same objects in a different order; three passes, three
  calls, distinct markers; a refusal after pass one keeps pass one; same cause and a shared
  component is one candidate; grouping ignores input order; agreement counts passes; RRF
  matches a hand example; a run without the block reads as one pass.

### 9.4 Per-candidate evidence — `feat(evidence)`, `feat(ranking)`, `contract(reference)`
- `evidence/candidates.py` (new): the precedent query from the candidate's card and components
  (reusing `tools/precedent.py`), the Super judge as today, stored as evidence records on the
  candidate ID.
- `ranking/severity.py`: candidates rated in batches like chains (`severity_reason`), stored
  with the model call ID.
- `reference/accident_priors.csv` (header only until rows are ticked in
  `docs/accident-priors-review.md`), `reference/tables.py`, `reference/loader.py`,
  PROJECT.md §10 header; `ranking/priors.py` (new): `matched_signals`, `prior_order`.
- Tests first: the precedent query names the candidate's components and chemicals and no
  model text; a candidate with no precedents shows zero; every candidate has a severity with
  a reason; the reference-table checks; a row with no lift is shown and never multiplied;
  matching reads mode, class, changes, impairments and plant facts; prior ties follow the
  holistic order.

### 9.5 Comparative ranking — `contract(prompts)`, `feat(ranking)`
- `prompts/credibility_rank/v1.md`; `config/routing.yaml` `credibility_rank: ultra`;
  `caps.yaml` `max_tokens`.
- `ranking/credibility.py` (new): `presentation_orders`, the permutation validator, `fuse`
  (RRF), `pairwise_window` (both orders, wins with half for a split pair, injected comparator),
  `setwise_heapsort` with an injected comparator, `final_pool` (candidates + chains +
  top unmatched folded findings by code order).
- `ranking/credibility_step.py` (new): the `credibility` step (preliminary) and
  `credibility_final` step; `CredibilityRanking` record per order (`schema/records.py`,
  `runs/store.py`, `runs/db.py`); `runs/start.py`, `runs/case.py` wire both.
- Tests first: orders distinct and repeatable; an answer that drops or adds an ID fails; three
  orders, three calls; fused order matches hand RRF; the pairwise window asks every pair both
  ways and never more than k(k-1) calls; a split pair counts half; a pair answer naming an ID
  outside the pair fails; heapsort returns the comparator's top k
  within its call bound; a cap refusal skips the ranking and the run goes on; the final pool
  holds every chain and at most `sweep_candidates` findings; the schema has no numeric field.

### 9.6 Grounded verification — `contract(prompts)`, `feat(ranking)`
- `prompts/verify_hypothesis/v1.md`; routing `verify_hypothesis: super`; `caps.yaml`.
- `ranking/verify.py` (new): the claim schema, the quote check (normalised substring of the
  cited fact's stored text), `verification_state`; `ranking/verify_step.py` (new) after the
  sweep, within the post cap; `VerificationRecord` stored per candidate.
- Tests first: a quote not in the fact's text is `ungrounded`; one test per state; a capped run
  reads `unchecked`; `contradicted` outranks nothing; verification lowers but never removes.

### 9.7 Three lists and overrides — `contract(api)`, `feat(review)`
- `review/lists.py` (new): `credible_list`, `gap_list`, `defeatable_list`, the A∩C flag,
  overrides applied on read. `api/models.py`, `api/app.py` (`GET /runs/{id}/lists`;
  `POST /runs/{id}/overrides` accepts the two new actions), `api/live.py`, `api/mock.py`,
  `contract/fixtures/lists.json` (`scripts/make_fixtures.py`), `contract/openapi.json`.
  `review/worksheet.py` and `export/`: the credibility-rank column.
- Tests first: List A never reads the gap; List B is gap then severity; List C holds impaired,
  shared, isolatable and procedure-only layers; the Geismar pattern is flagged on the recorded
  WG run; the route list gains exactly one route; a pre-v4 run (WG, D, G, $0) still returns
  three lists; a dismissed candidate shows its original rank; the export has the column.

### 9.8 Anytime order and the reserve — `feat(orchestrator)`, `feat(runs)`
- `orchestrator/view.py`, `orchestrator/loop.py`: priority follows the preliminary List A.
  `runs/estimate.py` and the reserve: passes, evidence and both rankings reserved before the
  sweep. `lopa/candidates.py`: List A's lines plus code order.
- Tests first: priority follows List A when ranked, else hypothesis rank; a capped run has a
  complete List A; the reserve refuses a sweep that could not leave room; LOPA candidates
  include List A's lead findings.

### 9.9 Conformal — `feat(bench)`
- `bench/conformal.py` (new). Tests first: k matches a hand example; refuses below fifty; a
  miss counts beyond every k.

### 9.10 Benchmark v2 — `feat(bench)`, `contract(prompts)`, `docs(bench)`
- `bench/stats.py`: `hit_at`, `mrr`, `cohen_kappa`, `krippendorff_alpha_nominal`,
  `paired_permutation_p`. `bench/v2.py` (new): validity rate, under-rank rate, K-run averaging,
  the configuration list including baseline B at matched cost, the item-question sheet.
- `prompts/judge/v1.md`, routing `judge: <placeholder tier>`, `scripts/judge_validate.py`.
- `docs/benchmark-v2.md`.
- Tests first: each statistic against a hand-worked or published example; K runs average per
  case first; every report line carries its cost; matched-cost N is computed from the ledger,
  never typed; the judge script refuses below κ 0.70; ablations refuse a held-out case; case
  lint flags a year, an outcome word and a company-like noun in a synthetic package and passes
  a clean one.

### 9.11 Frontend — `feat(frontend)`
- `api/types.ts` regenerated; `api/hooks.ts` `useRunLists`; `model/lists.ts`;
  `screens/Lists.tsx`, `screens/CredibleCard.tsx`, `screens/DefeatableTable.tsx`;
  `model/timeline.ts` labels for the new steps; the override controls.
- Tests first: `lists.test.ts` (labels, agreement text, states, A∩C flag, empty v3 fields,
  overrides applied); `Lists.test.tsx` (default tab; each tab renders its fixture; every number
  is a record link; dismiss posts the override with a reason); `timeline.test.ts` names the new
  steps.

## Order

9.0 (tooling) → 9.1 → 9.2 → 9.3 → 9.4 → 9.5 → 9.6 → 9.7 → 9.8 → 9.9 → 9.10 → 9.11. Each item ends with the
full CLAUDE.md §8 command set green before the next starts. 9.9 and 9.10 depend on nothing else
and go earlier if a later item is blocked.

## Conflicts, with Bhargavi's answers (2026-10-30)

1. R50b approved: pairwise both orders, reasons logged; code fuses, ties and computes.
2. Confirmed.
3–4. Acceptable while experimental; contract commits get split into `contract/` PRs before any
   merge.
5. Approved; each prior row carries source, dataset and n; weights are settings, not fitted.
6. Approved; values only from stated records.
7. OK on this branch only; the deployed site and `main` stay unchanged.
8. Keep the $1.00 cap; measure where runs stop: proving the anytime design under the cap is the
   point.
9. Development cases are D–H, the demo plants and the now-published K–S, labelled development;
   nothing on them counts as evidence; real evidence needs a new sealed set.
10. Approved for v4 only, with a test that old IDs and the WG replay are unchanged.
11. OK, labelled same-family; prefer a different family when a judge model is chosen.
12. Approved as its own contract commit.
Added: 9.0, fifty development cases from ARIA, eMARS and CSB before the ranking work.

### The questions as asked

1. **Model ranking.** CLAUDE.md §3 allows one model ordering (R50). 9.5 has Ultra order List A,
   twice. Proposed exception R50b: "the credibility ranking orders List A only; code fuses,
   ties and computes everything else; the model never sets a number". Approve?
2. **Model severity on candidates.** Already a model job with a reason (chains get it today);
   extending it to candidates is within the rule. Confirm.
3. **Contract changes on one branch** as separate `contract(...)` commits, since nothing merges.
   Acceptable?
4. **One branch, not one per task** (CLAUDE.md §7). Your instruction; confirm.
5. **Prior rows from the pasted note, not from Cowork** (CLAUDE.md §10): header-only file, rows
   loaded only after you tick them in `docs/accident-priors-review.md`. Approve?
6. **Schema blocks** `changes` and `impairments` (9.2): a plant-schema change, optional and
   empty by default, so every plant file and the recorded runs still load. Approve?
7. **The default view changes** to List A on this branch. The WG demo moment then depends on
   Ultra's credibility order, which no recorded run has until you run one. OK?
8. **Caps.** `plant_screen_max_hypotheses` 12 → 20; new `credibility` block; new `max_tokens`
   entries. The per-run cap stays $1.00 unless you say otherwise. With about six more Ultra
   calls and the per-candidate Super calls, $1.00 will stop a WG-sized run in the sweep more
   often; the anytime design is meant to make that acceptable. Raise the cap?
9. **Held-out cases.** Ablations on D–H and the demo plants only (CLAUDE.md §5). Confirm.
10. **Hypothesis ID** carries the pass number for v4 (an ID-form change). Approve?
11. **Judge tier.** `models.yaml` gains a `judge` tier only when you choose a model from the
    live list; until then the judge job is routed to `super` and labelled same-family. OK?
12. **Overrides** gain two actions (`dismiss_candidate`, `promote_candidate`): a contract
    change to the override enum. Approve?

## Not doing

- P&ID or document ingestion; an accident corpus or a fitted count model; new benchmark cases
  or external graders; a web precedent search per candidate; any live call; any edit to `main`
  or its worktree; any change to the published held-out records.
- No new dependency: RRF, κ, α, the permutation test and heapsort are standard-library code.

## Live calls and spend

None by Claude Code. Every item is tested with the fake gateway and the three recorded runs.
Expected cost per run on top of today's run, if Bhargavi checks it live (her call, her spend):

| Step | Calls | Expected cost |
|---|---|---|
| 3 holistic passes (WG today: 6.6k in, 6.9k out per pass; ~12k out at 20 hypotheses) | 3 Ultra | $0.08–0.15 |
| Precedent judge per candidate (~30 candidates, Super) | ~30 Super | $0.05–0.10 |
| Severity per candidate (batches of 10, Ultra) | ~3 Ultra | $0.03–0.06 |
| Preliminary ranking, 3 listwise orders | 3 Ultra | $0.08–0.12 |
| Verification, top 10 candidates (Super) | ~10 Super | $0.03–0.06 |
| Final ranking, 3 listwise orders (more candidates) | 3 Ultra | $0.10–0.15 |
| Pairwise window, both orders, k = 6 (30 calls, each with the plant) | 30 Ultra | $0.25–0.40 |
| Setwise heapsort instead of listwise (off by default) | ~30 Ultra per ranking | $0.60–1.00 |
| **Added per run, default settings** | ~39 Ultra, ~40 Super | **about $0.65–1.05** |

Under the $1.00 cap (answer 8) the analysis sweep will be short on a WG-sized plant; the reserve
(9.8) keeps the passes, evidence and both rankings inside it, and `cap_hits` records where the
run stopped. All-pairs over every candidate was not chosen: 30 candidates would be 870 calls.

Remaining today: about $1.50 across all uses. One WG check run would need about $1.60 moved
into `development`, which only you can decide; the second grant, if it lands, covers it.
