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

Report: `bench/demo/williams_geismar.json`. A full new run, with the analysis and all eight steps: $0.98 paid, the analysis counted at $0.849 of its $1.00 cap, and $0.128 of the $0.30 post cap.

- **The whole-plant pass** found the incident's story in its confirmed lines: tube rupture with the relief path blocked, reboiler B's shell-side block valves closed, HV-A-SIN left closed, and the generic start-up procedure written for the wrong side.
- **Phase 3:** 8 chains, all rated, with the text cleaned. 19 LOPA records (18 complete) and 18 recommendations.
- **Open, planned in `specs/phase-3-demo-fixes-plan.md`:**
  1. **No "no credit — inlet valve … closed" on the reboilers' relief paths.** Ultra judged valve states itself, against `PROJECT.md`'s rule that code decides credit, and invented one: it called HV-A-SOUT closed when it is locked open. It also called the relief path not applicable to a tube rupture. The fix is `lopa_argument/v3`.
  2. **15 matrix questions failed as whole batches,** on S-EA-425B, S-L-A-SOUT and S-L-QW-B-OUT. The causes were cut-offs at the token limit and duplicate or out-of-batch answers. So reboiler B's own section has no findings, and its top lines are led by a C4-heavies-and-air finding. The fix is a single-question retry, applied to this run as a targeted extension (no full re-run).
  3. **Every top-10 line is S3.** The severity prompt stays frozen. On camera, the engineer applies `change_severity` S3 → S4 with a reason.

## Spend, Phase 3

$1.90 of $2.50 at the time of writing (`scripts/budget_status.py`, 2026-10-21): $0.42 + $0.45 + $0.05 on D–G, and $0.98 on the demo run. The ledger snapshot `budget/ledger-g3pre.jsonl` is added once the demo re-run is done.
