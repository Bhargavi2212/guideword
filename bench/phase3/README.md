# Phase 3 results: the post-analysis on D–G and the demo plant

Every number here comes from the run records (`guideword.db`) and the reports in this folder and `bench/demo/`. All runs were started by Bhargavi under the Phase 3 cap (`phase_caps_usd."3": 2.50`), use `development`.

## The dev cases (extended in place; analysis replayed, never re-run)

| Case | Run | Chains (rated) | LOPA (complete) | Recommendations | Post-step spend (last pass) | Post prompts |
|---|---|---|---|---|---|---|
| D | `run:fede2ad2fa5d90f7:2` | 5 (5) | 19 (19) | 19 | $0.110 | connector v2; others v1 |
| E | `run:94f9624a118995e5` | 10 (10) | 20 (19) | 18 | $0.106 | connector v2; others v1 |
| F | `run:14aa6477a666ff65` | 10 (10) | 22 (19) | 15 | $0.097 | all v2 |
| G | `run:dbaab5578fbff8f3` | 10 (10) | 20 (20) | 20 | $0.138 | connector v2; others v1 |

What changed between passes (each earlier pass kept as superseded records, never deleted):

1. **Pass 1, every post prompt at v1.**
   - D and E kept 10 chains each. F kept 0 of 3 and G 0 of 10.
   - Ultra had copied the 46–94-character finding IDs wrongly, and code rejected every such link.
   - Cost $0.42.
2. **Pass 2, `connector/v2` (handles).**
   - No chain was rejected on any case.
   - F rated only 2 of its 10 chains: `severity_chain/v1` answered "the last batch" only.
   - Cost $0.45.
3. **Pass 3, F only, with all four post prompts at v2** (handles, batches of 5, one re-ask).
   - All 10 chains were rated, and each has a LOPA record.
   - No handle was left in the chain text.
   - The connector answer came from the cache.
   - Cost $0.05.

D, E and G stay on the v1 post prompts for chain severity, LOPA and recommendations until the second grant (`docs/decisions.md`, 2026-10-21). Their stored chain text still holds the connector's `L`/`P` handles from pass 2.

## The demo plant (Williams Geismar, `run:4e6842d31fbdee3b`)

Report: `bench/demo/williams_geismar.json`. The run ID is the same through all three passes; each earlier pass's post records are kept as superseded.

| Pass | What | Paid |
|---|---|---|
| 1 | A full new run: the analysis and all eight steps | $0.98 |
| 2 | `--retry-failed`: the 15 failed questions asked alone (13 answered, including all 5 of S-EA-425B's), then severity for the new findings and the post steps from `chains`, with `lopa_argument/v3` | $0.24 |
| 3 | `--rerun-from lopa` with the lead tie-break on | $0.10 |

The final pass:
- **10 chains, 22 LOPA records and 17 recommendations.** Every confirmed line has a LOPA record, and each one with a complete gap above 1 has a recommendation.
- **The opening card is shortlist rank 1 of 64,** in the confirmed tier. It is a chain rated S4, its LOPA shows **"no credit — inlet valve HV-B-SIN closed"**, and its gap reads "about 1,000× tolerable — mitigated about 1 in 100 years, tolerable about 1 in 100,000 years". Its recommendation is to manage inlet valves HV-A-SIN and HV-B-SIN.
- **Leads:** with the tie-break, reboiler A's line (#1) is led by its own section's finding (`m:S-EA-425A:less:flow`), whose gap reads within tolerable. Reboiler B's line (#2) keeps its C4-heavies-and-air lead, because S-EA-425B's own C12 findings were rated S2, not tied. That is a known limit, in `PROJECT.md` §23.
- **Still open:**
  - Two S-L-A-SOUT questions failed again on the model's answers.
  - One record still has Ultra call reboiler B's relief path "not applicable" to a tube rupture. No override is used on it, because the valve is closed and crediting it would be false. That is the other new limit in §23.
  - Every top-10 line was rated S3 by the frozen severity prompt. On camera, the engineer applies `change_severity` S3 → S4 with a reason.

## Spend, Phase 3

$2.24 of $2.50 (`budget/ledger-g3pre.jsonl`, 2026-10-21; `scripts/budget_status.py`). That is $0.92 on D–G ($0.42 + $0.45 + $0.05) and $1.32 on the demo run ($0.98 + $0.24 + $0.10). Development has $1.03 left. D, E and G wait for the second grant for their re-run on the v2 and v3 post prompts.
