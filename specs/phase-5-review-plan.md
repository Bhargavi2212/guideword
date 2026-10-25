# Phase 5 review plan: evidence attachment, two card layers, visuals, D and G on the site

Status: **draft, awaiting Bhargavi's approval** (mark `Status: approved <date>` here).

Source: Bhargavi's review of the live WG shortlist (2026-10-25), sets 1–3, plus the D and G
request. Scope is fixed and nothing is dropped. Everything comes from stored records, the plant
file and `reference/`: no new model text, no new dependency, no paid call. E and F stay held
until the leak-output rule is confirmed.

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
