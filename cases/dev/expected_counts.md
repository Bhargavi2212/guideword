# Expected question counts for dev cases D–H

Computed by Cowork on 2026-10-13 with a separate script that shares no code with the `guideword` package, from the dev-case files on `main` at `ec0818e` (assumptions applied) and `reference/applicability.csv`. **Claude Code never edits this file or `expected_counts.json`.** If the builder disagrees, stop and ask; the rule in `specs/phase-1.md` §1.4 decides which side is wrong.

Counts are for the **rule cut only** (no suggestions, no engineer changes). List names are the coverage list names: `sections` plus every `QuestionKind` value.

Applicability rows per section type: pipe 12, tank 11, vessel 11, column 14, reactor 16, heat_exchanger 10, pump 7, compressor 8, dryer 11, mixer 13, solids_handler 6, other 11; procedure guidewords 5.

| Case | Sections | Matrix | Pairs | Environment | No-flow | Procedure steps | Work | Dust | Relief | Total questions |
|---|---|---|---|---|---|---|---|---|---|---|
| D | 25 | 286 | 36 | 27 | 5 | 0 | 0 | 0 | 8 | 362 |
| E | 27 | 315 | 55 | 33 | 0 | 40 | 0 | 0 | 0 | 443 |
| F | 24 | 225 | 28 | 24 | 0 | 0 | 5 | 0 | 0 | 282 |
| G | 17 | 188 | 45 | 30 | 0 | 20 | 0 | 0 | 0 | 283 |
| H | 25 | 223 | 15 | 18 | 0 | 0 | 0 | 14 | 0 | 270 |

`added_by_ai` and `engineer` are 0 for every case (nothing adds them in Phase 1).

## How each count is made

**Case D** (15 equipment, 9 lines, 9 chemicals, no procedures or jobs, 8 relief devices)
- Equipment matrix: vessel 2×11 + column 4×14 + heat_exchanger 3×10 + pump 2×7 + tank 3×11 + other 1×11 = 166.
- Lines: 5 have a non-empty `no_flow` (E-106 bypass, start-up recycle, P-104B suction and discharge, off-spec): one flagged section each, never split. Of the 4 flowing lines, the rundown line splits at E-106 (heat exchanger) into 2 parts; the others are 1 part each. 10 pipe sections × 12 = 120. Matrix 166 + 120 = 286.
- Sections 15 + 10 = 25. Pairs 9×8/2 = 36; environment 27; no-flow 5; relief 8.

**Case E** (13 equipment, 11 lines, 11 chemicals, 1 procedure of 8 steps)
- Equipment matrix: reactor 2×16 + compressor 2×8 + column 4×14 + other 3×11 + tank 2×11 = 159.
- Lines: the two standpipes each split at their slide valve (a control valve) into 2 parts; the other 9 lines are 1 part each: 13 × 12 = 156. Matrix 315.
- Sections 13 + 13 + 1 = 27. Pairs 55; environment 33; procedure 8×5 = 40. No relief devices (none named in the package).

**Case F** (10 equipment, 10 lines, 8 chemicals, 4 jobs)
- Equipment matrix: other 4×11 + heat_exchanger 1×10 + tank 4×11 + pump 1×7 = 105. Lines: 10 × 1 part × 12 = 120. Matrix 225.
- Sections 10 + 10 + 4 = 24. Pairs 28; environment 24.
- Work (within reach, PROJECT.md §5 Step 3 item 5 with the Oct 13 answers): W-1 is at LOC-F-T32-ROOF, which holds no equipment, line end or relief discharge, so its reach is its listed T-32 and L-CONDENSATE-8IN = 2. W-2 has no location: its listed pump = 1. W-3 has no location: its listed white liquor line = 1. W-4 lists nothing and has no location: `work:W-4:W-4` = 1. Unlocated jobs never share a location. Total 5.

**Case G** (8 equipment, 4 hose lines, 10 chemicals, 1 procedure of 4 steps)
- Equipment matrix: tank 1×11 + mixer 4×13 + pump 1×7 + other 2×11 = 92. Each hose line splits at the portable pump into 2 parts: 8 × 12 = 96. Matrix 188.
- Sections 8 + 8 + 1 = 17. Pairs 45; environment 30; procedure 4×5 = 20.

**Case H** (17 equipment, 8 lines, 6 chemicals)
- Equipment matrix: tank 2×11 + solids_handler 12×6 + other 2×11 + dryer 1×11 = 127. Lines 8 × 12 = 96. Matrix 223.
- Sections 17 + 8 = 25. Pairs 15; environment 18.
- Dust: the 12 solids handlers and the dryer (13), plus BINS (a tank whose contents include cornmeal or corn flour, `combustible_dust: true`) = 14.
