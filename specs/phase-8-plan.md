# Phase 8 plan — Confirmed lines keep Ultra's order and Ultra's words

Status: approved 2026-10-29 (Bhargavi: "fix").

One PR, `phase-8/confirmed-lines`, $0, no live calls, no schema or API change.

## Per item

### 8.1 Order — `backend/guideword/lopa/lines.py`
- `_order`: confirmed tier sorts by `(tier, position, target_id)`; the other tiers keep
  `(tier, bucket, -gap, position, target_id)`. Docstring updated.
- Tests first:
  - `backend/tests/lopa/test_post_lines.py::test_the_confirmed_tier_keeps_its_display_order_not_the_gap`
    (two confirmed hypothesis lines, the lower-ranked one with the larger gap, stay in rank order;
    an also-found pair still goes by gap).
  - `backend/tests/review/test_views.py::_assert_ordered`: the gap check applies outside the
    confirmed tier; the existing test's assertions on tiers and overrides stand.

### 8.2 Words
- `frontend/src/model/shortlist.ts`: `leadText` returns the hypothesis mechanism for a confirmed
  line with a hypothesis; new `confirmedBy(item)` returns the lead finding's consequence for such a
  line, else null. `ShortlistCard.tsx` shows it under the lead. Tests in `shortlist.test.ts` and
  `ShortlistCard.test.tsx`.
- `backend/guideword/bench/heldout_scoring.py` `guideword_lines`: a confirmed finding item with a
  hypothesis reads `mechanism — hypothesis consequence`, components = finding's + hypothesis's.
  Test in `test_heldout_scoring.py`. `blind.py` inherits through `Line`.

### 8.3 Records
- `scripts/make_fixtures.py` if the fixture test says so; decisions row; spec ticks.

## Order
1. Tests (red) → 8.1 → 8.2 backend → 8.2 frontend → fixtures → docs. Full suites, ruff, mypy,
   frontend lint/typecheck/test.

## Conflicts (decided by Bhargavi, "fix", 2026-10-29)
- Spec 3.3 "then gap within a tier" vs R50 "the hypothesis rank orders the confirmed tier": R50
  wins for the confirmed tier; 3.3 stands for also-found.
- CLAUDE.md §5 (no tuning against held-out cases): the change is made after the benchmark closed,
  is a display and sort fix the records show was hiding the pipeline's own result, and the
  measured table is unchanged. Logged.

## Not doing
- Any model call, re-run, re-fold, tier or LOPA change; the title template (R3) stays ID-built.

## Live calls and spend
None.
