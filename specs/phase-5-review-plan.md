# Phase 5 review plan: evidence attachment, two card layers, visuals, D and G on the site

Status: approved 2026-10-25 (Bhargavi), with the changes in §0.

Source: Bhargavi's review of the live WG shortlist (2026-10-25), sets 1–3, plus the D and G
request. Scope is fixed and nothing is dropped. Everything comes from stored records, the plant
file and `reference/`: no new model text, no new dependency, no paid call. E and F stay held
until the leak-output rule is confirmed.

## 0. Changes on approval (Bhargavi, 2026-10-25)

1. **Q1, the exact rule first.** Before any R1 code, the exact attach rule is written here, and
   a table shows its result for every WG, D and G line that has a calculation candidate today or
   under the new rule. Bhargavi expects it to need the vessel and at least one mechanism input:
   its isolation valves, or the heat-source valves, or the step. No R1 code until she has seen
   the table.
2. **Q5, one event.** R2 also writes one event, "calculations re-attached <date> (<commit>)", so
   the WG replay ends on it. Its payload is part of v1.11, in R0.
3. **Q7, a round-trip test.** Undoing every substitution gives back the stored text exactly.
4. **R3's PR** shows the rendered plain titles of the top 10 WG lines, as well as the template
   list.
5. **Approved as proposed:** Q2–Q4, Q6, Q8–Q13. The F3 session is told about Q9: the landing
   stays on the shortlist with the plant picker, and F3 doesn't switch it to the replay (the
   deploy plan's line is amended to say so).

Settled while building R0 (each logged in `docs/decisions.md`):
- **R0 adds `via_ids` as an empty list.** R1 fills it with the approved rule, so v1.11 doesn't
  wait on Q1's table.
- **R0 serves WG only.** D's and G's runs and banners join in R5, once Bhargavi has supplied the
  banners.
- **The re-attach event** is a new event type with a structured payload (date, commit, the
  superseded and new record IDs). The text is a template built from it, never stored prose.

## 0a. Q1: the attach rule, for review before R1 (2026-10-25)

**Status: proposed. No R1 code until Bhargavi has seen this table.** It was computed at $0 by a
scratch script over the WG export and the D and G exports, read-only from `guideword-demo.db`.
The calculations were run on each plant file; no record was written.

### The rule (blocked-in heating)

For a line L (a finding, or a chain with its links) and a vessel E (equipment with
`design_pressure_kpa` and at least one heat source):

- **What the line names**, `named(L)`. For each of L's links:
  - a finding link's `failing_component_ids`;
  - a fact link's object (the ID before the first `.`);
  - for every procedure step among those, the step itself and its `equipment_ids` and
    `valve_ids`.

  A finding's *section* objects are not counted.
- **The mechanism inputs of E**, `mechanism(E)`:
  - E's heat-source isolating valves (`heat_sources[].isolating_valve_ids`);
  - the valves on E's process-side lines (lines from or to E that carry none of those heat
    valves): the valves that block it in;
  - the procedure steps whose `valve_ids` include any of them.
- **Attach** `blocked_in_heating(E)` to L when E is in `named(L)` and at least one of
  `mechanism(E)` is in `named(L)`.
- **`via_ids`:** L's links that supply a mechanism input, in stored order.

Unchanged:
- **The matrix rule (Q4):** `more:pressure`, `more:level` and `more:temperature` still bring
  their calculation on each equipment item of the finding's section.
- **Q3 needs no separate rule:** the mechanism inputs come from the plant's topology, not from
  the facts a calculation found, so a calculation with missing facts attaches the same way.
- **Only the top `evidence_top_n` (5) lines get calculation cards.** The other rows below show
  where the rule would act if those lines ranked higher.

Two variants were checked:
- **A:** also count section objects for both the vessel and the input. It attaches more: 9
  composition findings on the reboilers' process and quench-water lines get a card through
  their section's valve.
- **B:** count section objects for the vessel only. It gives the same result as C on every
  line.

### On the lines that get cards

| Run | # | Line | Blocked-in today | Under the rule | via |
|---|---|---|---|---|---|
| WG | 1 | fire, `f:m:S-EA-425B:more:temperature` | EA-425B confirmed (through its section) | none. Keeps its heat-up time card (skipped; matrix, Q4) | — |
| WG | 2 | the startup chain (`as_well_as:composition` + `P-REB-START-2:early`) | EA-425B confirmed | **EA-425B confirmed**; EA-425A not confirmed (not blocked in) | EA-425B: the 4 valve-position facts and `f:proc:P-REB-START-2:early`; EA-425A: `f:proc:P-REB-START-2:early` |
| WG | 3 | the EA-425A chain | EA-425B confirmed (through the fire link's section) | none. Keeps the heat-up time card on EA-425B through the fire link (matrix, Q4) | — |
| WG | 4 | `f:proc:P-REB-START-2:early` | none | **EA-425B confirmed**; EA-425A not confirmed (not blocked in) | `f:proc:P-REB-START-2:early` (the step names both reboilers and their quench-water valves) |
| WG | 5 | `f:m:S-EA-425A:more:flow` | EA-425A not confirmed (through its section) | none | — |
| G | 1–3 | the TOTES lines | TOTES skipped (matrix, `more:pressure`) | unchanged (Q4) | — |
| D | 1–5 | — | none | none | — |

### Questions on the result

1. **EA-425A on #2 and #4.** `P-REB-START-2` reads "the reboiler being placed in service" and
   names both reboilers and both sets of quench-water valves. So the rule also attaches
   EA-425A's card, which reads "not confirmed: not blocked in". Recommendation: keep it. It is
   what the plant file says, and the card reads not confirmed.
2. **Heat-up time on EA-425B stays on #3**, through the fire finding's section (the matrix rule,
   Q4, approved unchanged). Keep it, or apply the "names the vessel" test to the matrix rule as
   well?

### Every line with a candidate, today or under the rule (WG, D, G)

"Cards?" says whether the line is one of the top 5 that get calculation cards. Only
blocked-in heating is shown; matrix cards kept under Q4 are marked.

| Run | # | Cards? | Line | Blocked-in today | Under the rule (C) | via |
|---|---|---|---|---|---|---|
| WG | 1 | yes | `f:m:S-EA-425B:more` | EA-425B: confirmed | — | — |
| WG | 2 | yes | `chain: f:m:S-EA-425B:as_well_as, f:proc:P-REB-START-2:early` | EA-425B: confirmed | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:proc:P-REB-START-2:early`; EA-425B via `HV-B-SIN.normal_position`, `HV-B-SOUT.normal_position`, `HV-QW-B-IN.normal_position`, `HV-QW-B-OUT.normal_position`, `f:proc:P-REB-START-2:early` |
| WG | 3 | yes | `chain: f:m:S-EA-425B:more, f:m:S-L-A-SOUT:reverse, f:m:S-L-QW-A-IN:more` | EA-425B: confirmed | — | — |
| WG | 4 | yes | `f:proc:P-REB-START-2:early` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:proc:P-REB-START-2:early`; EA-425B via `f:proc:P-REB-START-2:early` |
| WG | 5 | yes | `f:m:S-EA-425A:more` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 6 | no | `f:m:S-EA-425A:less` | EA-425A: not confirmed: not blocked in | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-EA-425A:less`; EA-425B via `f:m:S-EA-425A:less` |
| WG | 7 | no | `chain: f:m:S-EA-425B:as_well_as, f:m:S-EA-425B:no` | EA-425B: confirmed | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `P-REB-START-1.equipment_ids`, `P-REB-START-1.valve_ids`, `P-REB-START-2.text`, `P-REB-START-2.valve_ids`, `f:m:S-EA-425B:no`; EA-425B via `HV-B-SIN.normal_position`, `HV-B-SOUT.normal_position`, `HV-QW-B-IN.normal_position`, `HV-QW-B-OUT.normal_position`, `P-REB-START-1.equipment_ids`, `P-REB-START-1.valve_ids`, `P-REB-START-2.text`, `P-REB-START-2.valve_ids`, `f:m:S-EA-425B:no` |
| WG | 9 | no | `chain: f:m:S-EA-425A:less, f:m:S-L-QW-A-OUT:more` | EA-425A: not confirmed: not blocked in | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `HV-QW-A-OUT.fail_position`, `HV-QW-A-OUT.kind`, `f:m:S-L-QW-A-OUT:more`; EA-425B via `f:m:S-L-QW-A-OUT:more` |
| WG | 10 | no | `chain: f:m:S-EA-425B:as_well_as, f:m:S-L-QW-B-IN:other_than, f:m:S-L-QW-B-OUT:as_well_as` | EA-425B: confirmed | EA-425B: confirmed | EA-425B via `HV-QW-B-IN.normal_position`, `HV-QW-B-OUT.normal_position` |
| WG | 11 | no | `f:m:S-EA-425B:as_well_as` | EA-425B: confirmed | — | — |
| WG | 12 | no | `chain: f:m:S-EA-425A:less, f:m:S-L-QW-A-OUT:as_well_as, f:m:S-L-QW-A-OUT:more` | EA-425A: not confirmed: not blocked in | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `HV-QW-A-OUT.fail_position`, `HV-QW-A-OUT.kind`, `f:m:S-L-QW-A-OUT:more`; EA-425B via `f:m:S-L-QW-A-OUT:more` |
| WG | 13 | no | `chain: f:m:S-EA-425A:less, f:m:S-L-A-SIN:other_than, f:m:S-L-QW-A-IN:other_than` | EA-425A: not confirmed: not blocked in | EA-425A: not confirmed: not blocked in | EA-425A via `HV-QW-A-IN.on_line_id` |
| WG | 14 | no | `f:m:S-EA-425A:less` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 15 | no | `chain: f:env:C4-HEAVIES:air, f:m:S-EA-425B:more, f:m:S-L-A-SIN:less` | EA-425B: confirmed | — | — |
| WG | 21 | no | `chain: f:env:PROPYLENE:water, f:m:S-L-QW-A-IN:other_than, f:m:S-L-QW-A-OUT:as_well_as` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 22 | no | `f:m:S-DA-406:more` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-DA-406:more`; EA-425B via `f:m:S-DA-406:more` |
| WG | 23 | no | `f:m:S-EA-425B:no` | EA-425B: confirmed | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-EA-425B:no`; EA-425B via `f:m:S-EA-425B:no` |
| WG | 24 | no | `f:m:S-EA-425B:no` | EA-425B: confirmed | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-EA-425B:no`; EA-425B via `f:m:S-EA-425B:no` |
| WG | 26 | no | `f:m:S-L-QW-B-IN:as_well_as` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-L-QW-B-IN:as_well_as`; EA-425B via `f:m:S-L-QW-B-IN:as_well_as` |
| WG | 28 | no | `f:pair:C4-HEAVIES:PROPANE` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:pair:C4-HEAVIES:PROPANE`; EA-425B via `f:pair:C4-HEAVIES:PROPANE` |
| WG | 29 | no | `f:proc:P-REB-START-1:late` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:proc:P-REB-START-1:late`; EA-425B via `f:proc:P-REB-START-1:late` |
| WG | 32 | no | `f:m:S-L-A-SIN:other_than` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 33 | no | `f:m:S-L-QW-A-IN:other_than` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 34 | no | `f:m:S-L-QW-A-IN:part_of` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 35 | no | `f:m:S-L-QW-A-OUT:as_well_as` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 36 | no | `f:m:S-L-QW-A-OUT:other_than` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 37 | no | `f:m:S-L-QW-A-OUT:part_of` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 38 | no | `f:m:S-L-QW-B-IN:other_than` | EA-425B: confirmed | — | — |
| WG | 39 | no | `f:m:S-L-QW-B-OUT:as_well_as` | EA-425B: confirmed | — | — |
| WG | 43 | no | `f:m:S-L-QW-A-OUT:more` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-L-QW-A-OUT:more`; EA-425B via `f:m:S-L-QW-A-OUT:more` |
| WG | 47 | no | `f:m:S-EA-425B:more` | EA-425B: confirmed | — | — |
| WG | 50 | no | `f:m:S-EA-425B:less` | EA-425B: confirmed | — | — |
| WG | 51 | no | `f:m:S-L-B-SIN:as_well_as` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:m:S-L-B-SIN:as_well_as`; EA-425B via `f:m:S-L-B-SIN:as_well_as` |
| WG | 53 | no | `f:proc:P-REB-START-2:late` | — | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | EA-425A via `f:proc:P-REB-START-2:late`; EA-425B via `f:proc:P-REB-START-2:late` |
| WG | 54 | no | `f:env:C4-HEAVIES:water` | EA-425A: not confirmed: not blocked in; EA-425B: confirmed | — | — |
| WG | 55 | no | `f:m:S-EA-425A:less` | EA-425A: not confirmed: not blocked in | — | — |
| WG | 56 | no | `f:m:S-EA-425A:less` | EA-425A: not confirmed: not blocked in | — | — |
| D | 8 | no | `f:m:S-L-RUNDOWN~E-106:more` | E-106: skipped (matrix, kept) | E-106: skipped (matrix, kept) | — |
| D | 24 | no | `f:m:S-P-104A:more` | P-104A: skipped (matrix, kept) | P-104A: skipped (matrix, kept) | — |
| D | 43 | no | `f:m:S-L-RUNDOWN~E-106:more` | E-106: skipped (matrix, kept) | E-106: skipped (matrix, kept) | — |
| G | 1 | yes | `chain: f:env:ACETIC-ACID:heat, f:env:BIOCIDE:water, f:env:SIH:heat, f:m:S-TOTES:more` | TOTES: skipped (matrix, kept) | TOTES: skipped (matrix, kept) | — |
| G | 2 | yes | `chain: f:env:ACETIC-ACID:heat, f:env:SIH:heat, f:m:S-TOTES:less, f:m:S-TOTES:more` | TOTES: skipped (matrix, kept) | TOTES: skipped (matrix, kept) | — |
| G | 3 | yes | `f:m:S-TOTES:more` | TOTES: skipped (matrix, kept) | TOTES: skipped (matrix, kept) | — |
| G | 6 | no | `chain: f:m:S-FILLING-LINE:more, f:m:S-FILLING-LINE:more, f:m:S-HOMOGENISER:more` | FILLING-LINE: skipped (matrix, kept) | FILLING-LINE: skipped (matrix, kept) | — |
| G | 7 | no | `f:m:S-FILLING-LINE:more` | FILLING-LINE: skipped (matrix, kept) | FILLING-LINE: skipped (matrix, kept) | — |
| G | 15 | no | `chain: f:m:S-L-HOSE-MX-3~PORTABLE-PUMP:as_well_as, f:m:S-L-HOSE-MX-4:other_than, f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |
| G | 17 | no | `chain: f:m:S-MX-2:more, f:m:S-TOTES:as_well_as, f:pair:DI-WATER:PT-CATALYST` | MX-2: skipped (matrix, kept) | MX-2: skipped (matrix, kept) | — |
| G | 20 | no | `chain: f:env:IPA:water, f:m:S-L-HOSE-MX-3:no, f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |
| G | 24 | no | `f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |
| G | 25 | no | `f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |
| G | 28 | no | `f:m:S-MX-2:more` | MX-2: skipped (matrix, kept) | MX-2: skipped (matrix, kept) | — |
| G | 34 | no | `f:m:S-MX-4:more` | MX-4: skipped (matrix, kept) | MX-4: skipped (matrix, kept) | — |
| G | 46 | no | `f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |
| G | 115 | no | `f:m:S-L-HOSE-MX-4~PORTABLE-PUMP:more` | PORTABLE-PUMP: skipped (matrix, kept) | PORTABLE-PUMP: skipped (matrix, kept) | — |

## 1. What exists today (checked $0)

- **Already built, not merged:** `phase-5/review-fixes` (5ea700b). It has the equipment on
  calculation cards (no "via" yet), skipped calculations as one line with the list expandable,
  the skip flag as a count, the recorded header without budget, engineer or plant status, and
  the start card scrolled into view. 139 frontend tests pass. It becomes R3's first commit.
- **The attachment rule** is `physics.applicable` (`tools/physics.py:598`). For each of the
  line's findings it takes the failing components and the finding's section objects, and puts
  `blocked_in_heating` on any of them that is equipment with a design pressure and a heat source.
  It never reads fact links or procedure steps. So #4 (`f:proc:P-REB-START-2`, failing the step
  `P-REB-START-2`, section `[P-REB-START]`) gets no card, even though the step names
  `equipment_ids [EA-425A, EA-425B]` and `valve_ids [HV-QW-A-IN, HV-QW-A-OUT, HV-QW-B-IN,
  HV-QW-B-OUT]`. #1 and #3 get EA-425B's card through the fire finding's section, S-EA-425B.
  (The full trace was reported 2026-10-25.)
- **D and G export cleanly from `guideword-demo.db`** (read-only; both stores' hashes unchanged):

  | Run | Files | Rows | Size | Load | Spend note |
  |---|---|---|---|---|---|
  | WG `run:76f8ee0b5d1f078e` | 17 | 2,011 | 7.05 MB | 0.41–0.55 s | record $0.0083 under ledger |
  | D `run:fede2ad2fa5d90f7:2` | 17 | 3,433 | 9.13 MB | 0.37 s | none (ledger = stored, $0.9187) |
  | G `run:dbaab5578fbff8f3` | 17 | 3,145 | 7.63 MB | 0.33 s | none (ledger = stored, $0.9883) |

  The three together bundle 23.8 MB, well inside a Vercel function's limit. D has no
  calculation cards; G has 3, all skipped.
- **LOPA records already store** the initiating event and frequency, each layer's credit or
  reason, the mitigated and tolerable frequencies, and `gap`. A severity override already
  recomputes the line's LOPA on the server (`review/overrides.py`). `reference/severity_classes.csv`
  has each class's `name` and `definition`, but no API response serves them yet.
- **Screenshots** can be taken at $0 with the installed Edge (`msedge --headless --screenshot`)
  against `vite preview` and a local API serving the export. No new dependency.

## 2. Questions (each with a recommendation)

| # | Question | Recommendation |
|---|---|---|
| Q1 | **The new attachment rule.** As worded ("the line's failing components or linked facts include the calculation's own inputs"), it still attaches nothing to #4: a finding line has no linked facts, and `P-REB-START-2` isn't an input. | Match on **objects**, not fact IDs (`HV-QW-B-IN.locked` counts as `HV-QW-B-IN`), and **expand a procedure step to its `equipment_ids` and `valve_ids`**. Then #4 gets EA-425B (and EA-425A, "not blocked in"), #2 keeps it, and #1 and #3 lose it. |
| Q2 | **Where candidate calculations come from.** | Every equipment item the line reaches (failing components, section objects and step expansion, as today plus steps). Not plant-wide: plant-wide would put EA-425A's card on #3 through its HV-A facts alone. |
| Q3 | **A skipped calculation has no inputs** (`fact_ids: []`), so under Q1 it can never attach. | Count `missing_fact_ids` as its inputs too, so a skipped card still shows where the calculation would have applied. |
| Q4 | **The matrix rule** (`more:temperature` → heat-up time on the section's equipment; also overflow and pressure). | Keep it unchanged. Q1 replaces only the blocked-in rule. |
| Q5 | **Re-attaching the stored runs.** Rerunning the evidence step would re-run the judge and Tavily (WG: 9 judge calls, $0.0225, and 5 searches), and the API refuses it on a recorded run anyway. | A **$0 code-only script**, `scripts/reattach_calculations.py`, on `guideword-demo.db` only. It recomputes the physics cards with the new rule, writes the new calculation records and tool calls, and supersedes the old ones through `superseded_records`. No model or search call; precedent records untouched. Run on WG, D and G, then re-export. The label's note gains "calculations re-attached 2026-10-2X (<commit>)". |
| Q6 | **"via" needs the backend.** No record says which link brought a card, and the frontend mustn't recompute safety logic. | Contract v1.11: `Evidence.via_ids`, computed at read time by the same rule that attaches. Each ID is shown as its tag or step name, with the raw ID on hover. A card reached two ways lists both. |
| Q7 | **Record keys inside model-written text** (a finding's consequence, a chain's description). P5-5 says model text is shown verbatim. | Substitute the key with its tag or step name **in display only**, raw key on hover; the stored text is unchanged and opens in the drawer. Apply this to model text too, with a decisions row narrowing P5-5. |
| Q8 | **The WG banner names "Line #2".** Ranks come from the stored shortlist, but a fixed "#2" in config would go stale if the order changed. | The banner text lives in `deploy/site.json` with `{start_rank}` filled from the start target's served rank. D and G get your one-line source banners, with no start target, no "start here" and no "found" text. |
| Q9 | **The landing.** The deploy plan says F3's PR switches the landing to the replay; this review says the landing opens the WG shortlist with #2 in view and a plant picker. | The landing stays on the shortlist with the picker (WG first and default). The replay is reached from the run's page. F3's PR doesn't switch the landing; I'll tell the F3 session. |
| Q10 | **The gap text "N× over the risk limit".** | From the stored `gap`, formatted by the one number formatter (2 significant figures). A gap of 1 or less reads "within the risk limit"; no LOPA reads "no LOPA". It's a frontend template, so the server's `gap_text` stays as stored and opens in the drawer. |
| Q11 | **The severity description** ("the severity code with the table's own description"). | Contract v1.11: the shortlist response gains `severity_classes: [{severity_class, name, definition}]`, read from `reference/severity_classes.csv`. |
| Q12 | **"A severity override moves the tolerable line."** | It works wherever overrides do: the server recomputes the LOPA and the bar redraws. On the deployed site every recorded run refuses overrides (403), so it is shown on the laptop only. |
| Q13 | **Who builds these.** F3 (live run), F4 (coverage and worksheet) and F5 (plant and sections) are with the second session; R3–R5 touch the shortlist, the detail screen, the header and the landing. | This session builds R0–R6. The F session leaves the shortlist, detail and landing to us; the header is shared, so the later PR rebases. |

## 3. Per item

### R0 — `contract/review-fields` (contract v1.11, backend)
- `Evidence.via_ids: list[str]` (API only, computed on read; not stored).
- `DemoResponse.runs: [{run_id, plant_id, banner, start_target_id}]` in picker order, WG first. The existing fields keep serving WG.
- `Shortlist.severity_classes: [{severity_class, name, definition}]`.
- Settings: `guideword_recorded_dirs` (a list) replaces `guideword_recorded_dir`; `deploy/site.json` gains `demo_runs` with each banner.
- Tests first: the fields validate and serialise, the fixtures are regenerated by `make_fixtures.py`, `openapi.json` matches, every banner comes from `site.json` and none from code, and D and G have no start target.

### R1 — `phase-5/attachment-rule` (backend, after Q1–Q4)
- `physics.applicable` returns `(calculation, equipment, via_ids)` under the approved rule; the evidence step and the API's `via_ids` both use it.
- Tests first: the WG lines #1–#4 give the attachments in Q1; a step expands to its equipment and valves; a skipped calculation attaches through its missing facts (if Q3); the matrix rule is unchanged (Q4); the existing Phase 4 tests still pass, and any that change are listed in the PR.

### R2 — `phase-5/reattach` (script, after R1 and Q5)
- `scripts/reattach_calculations.py <run> --store guideword-demo.db`: $0, refuses `guideword.db`, writes through the normal writer, supersedes the old calculation records.
- Tests first: on a generated fake run it writes only calculation records and tool calls, supersedes the old ones, makes no model or search call, and refuses the source store.
- Bhargavi runs it on WG, D and G, then re-exports the three.

### R3 — `phase-5/card-layers` (frontend; starts with `phase-5/review-fixes`)
- **Set 1:** "calculation on EA-425B · via <name>" on every calculation card; the merged review fixes.
- **Banner:** on recorded runs only, from `/demo`.
- **The plant picker:** on the landing, WG first and the default.
- **Plain line:** the card title, one fixed template per line kind (finding by question kind, chain, hypothesis), written in code. Every template string is listed in the PR for review.
- **Technical layer:** equipment and valve tags; the operating values used (temperature, pressure, design limit); the calculation's inputs and result with units; the LOPA line (initiating event and frequency, each layer's credit or reason, mitigated vs tolerable, the severity code with its definition); and the gap per Q10.
- **Record keys** in displayed text become tag or step names, raw on hover and in the drawer (Q7).
- Tests first: one test per template and line kind; every number in the technical layer is traced; no raw key is shown in text; the banner shows only on recorded runs, and D and G have none of WG's text.

### R4 — `phase-5/visuals` (frontend, hand SVG and CSS)
- **Chain flow:** `chain.links` in stored order as boxes with arrows. Each box shows its tag or step name, valves at their stored `normal_position` (closed in red), and calculation results inline. A click opens the record in the drawer.
- **LOPA bar:** a log scale from the initiating frequency, down through each layer (a credited layer is a step down labelled with its PFD; an uncredited one is crossed out with its reason), to the mitigated frequency, with the tolerable line and the gap marked.
- **Visual pass:** a type scale, one severity colour scale (S1–S5), card spacing.
- Tests first: the boxes follow the stored order and every box is traced; each bar step equals the stored layer credit, with no arithmetic beyond the log position; the tolerable line follows the served LOPA after an override.
- Before merging: a screenshot of card #2 with the chain flow and the LOPA bar, sent to you.

### R5 — `phase-5/recorded-dg` (deploy)
- Export D and G into `cases/demo/recorded/case_d` and `case_g` (read-only from `guideword-demo.db`, after R2's re-attach); `vercel.json` bundles them; your banners go in `site.json`.
- Tests first: the site entry serves all three runs with no key, the picker order, no "found" text for D or G, every route reads each run, and overrides are refused (403).

### R6 — `phase-5/schematic` (frontend; only if R0–R4 merge by Oct 27)
- A plant schematic built from the plant file's topology (lines' `from_id` and `to_id`), with the selected line's items highlighted.

## 4. Order

R0 → R1 → R2 (you run it) → R5; R3 after R0; R4 after R3; R6 last. Every merge redeploys
through Git. Target: R0–R3 by Oct 26, R4 and R5 by Oct 27, R6 by Oct 28 or skipped.

## 5. Not doing

E and F; any new model text; any change to rank, tier, LOPA arithmetic, severity or
recommendations; any record change outside R2's calculation records; any write to
`guideword.db`; opening `cases/dev/keys/`.

## 6. Live calls and spend

None. Every step is $0: the exports and the re-attach read or write only `guideword-demo.db`,
and no step calls a model or Tavily.
