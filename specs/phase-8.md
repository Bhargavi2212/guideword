# Phase 8 — Confirmed lines keep Ultra's order and Ultra's words

Status: approved 2026-10-29 (Bhargavi: "fix"), after the held-out benchmark and the post-fix case Q.

## Why

The held-out records (K, M, P in `bench/heldout/`, Q in `bench/heldout-post/`) show the whole-plant
pass (R50: Ultra reads the plant once and proposes ranked hypotheses) put the real mechanism at
**hypothesis rank 1 in all four cases**, and the pipeline confirmed each one. Two deterministic steps
then hid it from the shortlist the graders (and an engineer) read:

1. **Order.** `lopa/lines.py` `shortlist()` re-sorts every tier by LOPA gap (spec 3.3), so inside
   the confirmed tier Ultra's order is overwritten: M's rank-1 hypothesis sits at line 7, P's at 2.
   R50 (decisions 2026-10-16) says the hypothesis rank orders the confirmed and unconfirmed tiers.
2. **Words.** A confirmed line's card shows its lead finding's question title and consequence; the
   hypothesis's mechanism is only in the detail view. K's line 1 read "Loss of cooling water supply"
   while its hypothesis said "runaway polymerisation generating heat faster than E-1 can remove";
   P's line 2 read "Control valve fails open" while its hypothesis said "steam leaks past non-tight
   FV-A/FV-B and closed manual valves into the reboilers of idle C-1". The blind sheets (P6-10)
   render what the card shows, so they graded the generic words.

Simulated on the stored shortlists (automatic match, post-hoc; `docs/decisions.md` 2026-10-29):
K 9 → 1, M 22 → 2, P none → 1 (with Ultra's wording "leaks past" added to the key's phrases),
Q 20 → 20 (not Q's mechanism). The 0-of-3 table stands as measured; this is the cause and the fix.

## Scope

### 8.1 Order (backend, deterministic)
- `shortlist()` keeps the confirmed tier in its display order (tiers.py: hypothesis rank, then
  each chain at its member line). The LOPA gap orders the also-found tier only, as before. The gap
  stays on every card, in the worksheet and in the export. Unconfirmed unchanged.
- Supersedes spec 3.3's "gap within a tier" for the confirmed tier (conflict logged).

### 8.2 Words (frontend and benchmark rendering)
- A confirmed line that stands for a hypothesis (finding line with `hypothesis_id`) leads with the
  hypothesis's **mechanism**; the lead finding's consequence is shown beneath it as "Confirmed by".
  The plain title (R3, from IDs) is unchanged. Chains, also-found and unconfirmed lines unchanged.
- `bench/heldout_scoring.guideword_lines` and the blind sheets render such a line the same way:
  mechanism — hypothesis consequence, naming the finding's failing components and the hypothesis's
  components (P6-9, P6-10: the sheet shows what the product shows).
- No API or schema change: `ShortlistItem` already carries `hypothesis` on every line.

### 8.3 Records
- `contract/fixtures/` regenerated if the order of the mock shortlist changes.
- Decisions row; README (publish PR) states the cause, the fix and the post-hoc re-score, labelled.
- A fresh second-grader blind pass on re-rendered sheets for K, M, P, Q is optional and $0; if run
  it is reported as post-hoc, never in the headline table.

## Not in scope
- Re-running any case; changing tiers, the fold, LOPA, severity or the cause library.
- Showing hypothesis text on also-found lines (they stand for no hypothesis).

## Done when
- [ ] 8.1 with tests: a lower-ranked confirmed hypothesis with a larger gap stays below a
      higher-ranked one; also-found still by gap; existing order tests updated to say so.
- [ ] 8.2 with tests: a confirmed finding line leads with the mechanism and shows "Confirmed by";
      the scorer's line for it carries the mechanism and both component sets.
- [ ] Fixtures, decisions row, spec ticks.
