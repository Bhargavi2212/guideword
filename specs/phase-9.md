# Phase 9 — Credible-first ranking (next version, on its own branch)

Status: **approved 2026-10-30** (Bhargavi's twelve answers are in `specs/phase-9-plan.md` and
`docs/decisions.md`). v2 filled the gaps found on a second reading of the research note; v3 applies
the answers and adds 9.0.

Asked for by Bhargavi on 2026-10-30 ("get other branch, build the entire thing, don't merge it,
don't touch the main code"), from the research note "Rank hazards by credibility, not protection
gaps". Everything lands on `next/credible-ranking` in the worktree
`D:\Hackathon\guideword\guideword-next`. Nothing is merged to `main`, and `main`'s worktree is
never edited.

## Why

The held-out benchmark (0 of 3) and its post-mortem showed that the whole-plant pass found the
mechanism and two deterministic steps hid it. Phase 8 fixed the order of the confirmed tier. The
note argues the rest of the design should follow the same principle: **generate holistically,
verify narrowly, rank comparatively**, with LOPA gap as a separate list for protection work, and
a benchmark that can tell architectures apart. Grades in brackets are the note's own: Strong,
Moderate, Weak, Inference.

## The pipeline after this phase

```
plant_screen ×3 (reordered plant)  →  candidates, agreement, holistic order
→ precedent per candidate (index, $0 + Super judge)
→ severity per candidate (Ultra, with reason)
→ credibility_rank ×3 (preliminary List A)          ← anytime: complete from here
→ analysis sweep, dispatched in List A order          ← recall net
→ verify_hypothesis (Super, grounded in plant facts)  ← narrow verification
→ chains, chain severity, LOPA, recommendations, evidence (as today)
→ credibility_rank ×3 again, over candidates + chains + unmatched sweep findings (final List A)
→ ranked: Lists A, B, C
```

## Scope

### 9.0 Fifty development cases from ARIA, eMARS and CSB (before the ranking work)
- Bhargavi's addition. Fifty cases in the held-out format (`docs/case-template.md`: package, key,
  plant file), labelled **development**: used for ablations and tuning, never as evidence. Real
  evidence needs a new sealed set (answer 9).
- CLAUDE.md §5 forbids Claude Code to open or summarise accident reports, so the cases are written
  by a separate case-writer session, as K–S were, from `docs/case-writing-v2.md` (the protocol of
  9.10: time split, rewrite before the accident, strip date, site and outcome, three-mechanism
  check, reference mechanism). Claude Code builds the tooling: the protocol document, the
  `cases/dev2/` layout and its README, `scripts/case_lint.py` (moved here from 9.10), a selection
  log template, and `scripts/dev2_check.py` (every package lints clean, every plant file
  validates, every key has the template's fields). Open question for Bhargavi in the plan.

### 9.1 A specific hypothesis card (prompt `plant_screen/v4`, schema)
- Each hypothesis states its **initiating event**, **enabling condition** (operating mode,
  change, defeated or shared safeguard), **propagation path** and **consequence with a magnitude
  where the plant facts give one**, each its own field, plus the plant fact IDs it rests on.
  [Moderate: CEP 2025, Lee et al. 2026]
- Two enum fields, each with `other`: `operating_mode` (normal, startup, shutdown, maintenance,
  idle_or_standby, batch_step, changeover, other) and `mechanism_class` (the classes 9.4's
  signals name, plus other).
- Up to `plant_screen_max_hypotheses` hypotheses, 12 → 20; the prompt asks for diverse,
  specific mechanisms and tells the model to cover non-routine modes, recent changes, defeated
  safeguards and common-cause double failures. [Moderate: McDuff et al.; Baybutt 2003, 2013]
- Every cited fact ID must exist in the plant; an unknown one drops the hypothesis.
- Runs stored before v4 read with the new fields empty. v3 hypothesis IDs and the recorded WG
  replay are unchanged (answer 10, tested).

### 9.2 Plant facts the note says accidents cluster in (schema, contract)
- Two optional plant blocks, empty by default so every existing plant file still validates:
  - `changes`: recent modifications (`id`, `description`, `object_ids`, `date`,
    `hazard_review_done: bool | null`, `source`, required: values come only from stated
    records, answer 6);
  - `impairments`: safeguards or relief devices not in their design state (`id`,
    `safeguard_id`, `state`: bypassed, defeated, overdue_test, removed, other; `since`,
    `description`, `source`, required).
- The whole-plant pass sees both blocks. A change links the questions of its objects (as
  planned work does); an impairment links its safeguard's protected object's questions.
- An impaired layer gets no LOPA credit (a new first rule in `lopa/credit.py`, with the
  impairment ID as the reason) and is on List C.
- One question kind, `change` ("what did this change defeat or introduce?"), one per change,
  built by code, counted in coverage like a planned job. [Moderate: PT Note 135; Baybutt 2016;
  CSB Geismar]
- No P&ID or document ingestion (CLAUDE.md §14): the blocks are filled by the engineer or the
  case writer.

### 9.3 Several holistic passes, fused by rank
- `plant_screen` runs `credibility.holistic_passes` times (default 3), each on the plant record
  with its object lists in a different code-made order (pass 1 as stored, 2 reversed, 3 rotated
  by half); no randomness. [Moderate: Liu et al. 2024]
- Code groups the passes' hypotheses into **candidates**: same cause (library ID or normalised
  outside-library text) and at least one shared component. Deterministic; the candidate's ID is
  built from its members' IDs.
- Each candidate carries its **agreement**, "named in 2 of 3 passes"; never a probability.
  [Moderate: Xiong et al. 2024]
- The **holistic order** fuses the passes' ranks by reciprocal rank fusion, by code.

### 9.4 Evidence attached to each candidate before ranking
- **Precedent:** the existing code-built query and BM25 over `reference/precedent_index.csv`
  (no web call), judged by Super as today, for every candidate; the number of matching
  precedents and their rows are shown on the card and given to the ranker as data.
  [Weak for the benefit, the note's own grade]
- **Severity:** every candidate gets a severity class with a reason from the existing severity
  job (as chains do today). Shown in its own column; never multiplied into a score. [Strong:
  Cox 2008 on why not a product]
- **Accident-data priors:** new reference table `accident_priors.csv`, one row per pre-accident
  signal from the note's table, with its lift where a source gives one, its evidence grade, the
  **dataset and n** it rests on, and its source (answer 5); rows with no frequency source are kept
  with no lift (shown, never used in a number). The weight the prior order carries in the fusion
  is a setting (`credibility.prior_weight`), never fitted. Code matches a candidate to signals from its `operating_mode`, `mechanism_class`,
  the plant's `changes` and `impairments`, equipment kind and line service. The **prior order**
  ranks by the product of matched lifts, ties by the holistic order. **Every row needs
  Bhargavi's tick before it is loaded** (CLAUDE.md §10).

### 9.5 Comparative credibility ranking (new job `credibility_rank`, Ultra)
- **Listwise:** Ultra is shown the plant and the candidates (card, agreement, severity,
  precedents, priors, verification state when known) in a code-made order and asked to order
  them by "which is most likely to be the real accident on this plant", with a reason per
  candidate. It runs `credibility.rank_orders` times (default 3), each with a different code-made
  order; code fuses by RRF. [Weak: permutation self-consistency]
- **Pairwise, both orders** (answer 1, R50b): over the top `credibility.pairwise_top_k` of the
  listwise order, every pair is asked both ways ("A then B" and "B then A"), each answer a choice
  with a reason, logged. Code scores each candidate by wins, a split pair counting half, ties by
  the listwise order. [Weak: PRP] The window keeps the call count at k(k-1): k = 6 is 30 calls.
- The answer must be a permutation of exactly the IDs given; anything else fails validation and
  gets the one retry every job has.
- It runs twice per run: **preliminary**, after 9.3–9.4 (listwise only: the anytime list and the
  dispatch order), and **final**, after LOPA (listwise, then the pairwise window), over the candidates plus the chains and the top unmatched
  sweep findings (folded, by code order, at most `credibility.sweep_candidates`). The sweep is a
  recall net: what it finds can enter List A; its answers never set the rank. [Inference]
- A setwise heapsort ranker (`credibility.ranker: setwise`) is built and tested beside it, off
  by default (about ten times the calls). [Weak: Setwise, SIGIR 2024]
- The model orders; it never sets a number. Code fuses, ties and stores.

### 9.6 Narrow verification, grounded in the plant record (new job `verify_hypothesis`, Super)
- After the sweep, for the top `credibility.verify_top_n` candidates: Super is given the card
  and the plant facts it cites and must return, per claimed condition, `supported`,
  `contradicted` or `not_stated`, the fact ID, and a **quote** from the plant record. Code
  checks the quote is a substring of that fact's stored text; a claim whose quote is not found
  is recorded as `ungrounded` and never counts as support. [Moderate: RCAgent's grounding
  check; SpecRCA]
- The candidate's **verification state** is computed on read: `supported` (a supporting
  finding by the R50 rule, or every claim supported), `contradicted` (any claim contradicted),
  `unchecked` (a linked question still open, the run stopped at its cap, or no verification
  call), `not_supported` (every linked question answered, none supports, no claim contradicted).
- The state enters the final fusion as one more ranking with ties (supported, unchecked,
  not_supported, contradicted). It can lower a candidate; it never removes one. [Inference, to
  test in 9.10's ablation]

### 9.7 Three lists, never one blended score
- **List A, most credible mechanisms** (default view; the benchmarked list): the final fused
  order (comparative, holistic, prior, verification), each with severity in its own column,
  agreement, verification state, precedents, matched priors, Ultra's reason, and its supporting
  findings and chains under it. No LOPA credit in its order.
- **List B, largest protection gap:** every finding and chain with a LOPA record, by gap, then
  severity: today's ordering as its own list.
- **List C, defeatable or fragile protection:** every safeguard or relief layer refused or
  discounted by a LOPA record because it is impaired (9.2), shared with the cause, not
  independent, isolatable (an inlet valve normally closed or not locked open) or procedure-only,
  with the lines it affects and the stored reason; ordered by lines affected, then severity.
- A List A candidate with a layer on List C is flagged "credible, and its protection can be
  defeated" (the Geismar pattern). [Moderate: Baybutt 2013; CSB Geismar]
- One new read-only route returns the three lists; the existing shortlist route is unchanged.
  The worksheet and the Excel export gain a "credibility rank" column.
- Engineer overrides: `dismiss_candidate` and `promote_candidate`, each with a reason, stored as
  overrides (never editing the ranking record); List A shows them applied with the original
  rank beside.

### 9.8 Anytime order of work and the reserve
- Steps run in the order of the diagram. The orchestrator's priority dispatch takes the
  preliminary List A order. A run that stops at its cap still has a complete List A.
- The cost of the passes, the per-candidate evidence and both rankings is reserved before the
  sweep starts, as the severity reserve is today; the verification calls come from the post
  cap.
- LOPA candidates: the top `lopa_top_n` lines of List A's supporting findings and chains, plus
  the top `lopa_top_n` by code order (today's rule), deduplicated.

### 9.9 Confidence without verbalised probabilities
- Agreement across passes (9.3) and the verification state are the only confidence shown.
- A conformal-set calculator: given at least `credibility.conformal_min_cases` (50) labelled
  cases of a process class, returns the k such that the top k held the true mechanism in 90% of
  them; below the minimum it refuses and the UI shows nothing. [Moderate: Kumar et al.]

### 9.10 Benchmark v2 tooling (code and protocol; no new cases, no graders hired)
- Metrics: hit@1/3/5/10 (hit@5 primary), MRR, scenario validity rate, severe-mechanism
  under-rank rate; every report line carries its cost.
- Agreement: Cohen's κ and Krippendorff's α (nominal) for two graders, before adjudication.
- Tests: Wilson and exact McNemar (existing), a paired permutation test for MRR (exact to 20
  cases; a fixed content-derived sequence above).
- Repeated runs: K per case, averaged per case first.
- Configurations: List A; List A without verification; without priors; without the final
  re-rank; ordered by gap (the note's ablation); the prior-only base-rate ranker ($0); baseline
  A; baseline B; and **baseline B at matched cost** (N plain prompts fused by RRF, N chosen so
  its cost matches the pipeline's). [Moderate: Tran & Kiela; Nori et al. on cost frontiers]
- **LLM judge tooling:** a `judge` job answering "does item i describe the reference
  mechanism?" (yes, partial, no, with the mismatch named), and `scripts/judge_validate.py`
  that reports its κ against adjudicated human labels and refuses to be used as a grader below
  0.70. The judge's tier is a placeholder Bhargavi fills from the live model list (a non-Nemotron
  model on Token Factory, if one is listed; else Nemotron, labelled as same-family).
  [Moderate: Thakur et al.; Nori et al.]
- `docs/benchmark-v2.md`: the pre-registration template (metric, rubric, judge, tests, α) and
  the case protocol from the note (time split, rewrite, three-mechanism check, reference
  mechanism, external graders, contamination subset).
- Development cases are D–H, the demo plants, the now-published K–S and the 9.0 set, all
  labelled development; nothing on them counts as evidence (answer 9).

### 9.11 Frontend
- The shortlist screen opens on three tabs: Most credible (default), Largest gap, Defeatable
  protection.
- A List A card: initiating event, enabling condition, path, consequence; agreement;
  verification state with its grounded claims; severity; precedents; matched priors with their
  source; Ultra's reason; the A∩C flag; the dismiss and promote controls. Every number opens its
  record.
- The live-run timeline names the new steps (passes, per-candidate evidence, both rankings,
  verification) and shows each ranking's reasons.
- Mock fixtures for the new route match the contract exactly.

## Not in scope
- P&ID or document ingestion (CLAUDE.md §14).
- Building an accident corpus from ARIA, eMARS, CSB or FKD, or fitting a count model (weeks,
  licences, and CLAUDE.md §5).
- Writing the 100–150 benchmark cases or recruiting external graders.
- A web precedent search per candidate (Tavily spend); the index only.
- Any live call by Claude Code. Any change on `main`.

## Done when
- [ ] 9.0 tooling and 9.1–9.11 built with tests written first; every suite green; ruff, mypy, eslint, tsc clean.
- [ ] A $0 replay of the recorded WG, D and G runs through the new read path renders all three
      lists (pre-v4 records show the new fields empty and List A "not ranked comparatively").
- [ ] Decisions rows for every conflict Bhargavi rules on.
- [ ] Bhargavi's live check (her call, her spend): one WG run on the new pipeline.
