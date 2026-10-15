# Phase 1 — Plant and questions

**Dates:** Oct 14 (after G1) – Oct 15, 2026 **Ends with:** exact question counts on dev cases D–H
**Live-call budget for this phase:** $0.00. No paid calls (see "Super suggestions" below).
**Source of truth:** `PROJECT.md` (§5 Steps 1–3, §9, §10, §11). If this spec and `PROJECT.md` disagree, stop and ask.
**Before any code:** Claude Code writes `specs/phase-1-plan.md` in plan mode (`CLAUDE.md` §1, "Plan before code") and waits for approval.

## Goal

From a validated plant file, code draws the sections, the engineer confirms them, and code builds the complete question list with coverage counts. Every count on dev cases D–H matches an independently computed expected count. This is the "complete by construction" claim: the question list exists, is deterministic, and nothing can be deleted from it.

**What the video shows from this phase:** the plant loading with its missing-fact warnings, the section cut with no-flow lines flagged, and the coverage panel's totals (e.g. "212 questions: 98 matrix, 45 chemical pairs, 30 chemical environment…") before the agent starts. Also the video script itself (1.8).

## Depends on (must be merged before the PR that needs it)

| Needs | From Phase 0 | Used by |
|---|---|---|
| Frozen schema: plant models, records, enums, IDs, validation | PR 6/7 (merged) | everything |
| Reference loaders (`ReferenceSet.procedure_guidewords`, applicability rows) | PR 5 (merged) | 1.4 |
| API contract `contract-v1` (`api/models.py`: `PlantSummary`, `PlantUploadResult`, `PlantDetail`, `SectionSuggestion`, `SectionProposal`, `ConfirmSectionsRequest`, `ConfirmSectionsResult`, `CoverageList`, `Coverage`, `ErrorBody`, `Issue`) | PR 13 (merged, tagged) | 1.1, 1.3, 1.5 |
| Dev cases D–H as plant files with every assumption ticked | PRs 11–12 (merged) | 1.6 |

**This phase builds against `contract-v1` as it is.** Every endpoint keeps its request and response model exactly. Where this spec needs something the contract cannot carry, it says so and defers it (see 1.3, rejected suggestions). If you find another gap, stop and ask; it goes through a `contract/...` branch, never a quiet edit. The five plant endpoints are the ones `NOT_BUILT_PHASE` in `api/app.py` marks as phase 1; every other route keeps returning 501 with its phase, and mock mode (`GUIDEWORD_MOCK=1`) is unchanged.

## In scope

| # | Item | Built by |
|---|---|---|
| 1.1 | Plant store and plant endpoints (upload, validate, list, facts) | Claude Code |
| 1.2 | Section rules: the rule-drawn first cut | Claude Code |
| 1.3 | Section suggestions (schema, prompt v1, validation, apply) with a fake suggester; propose and confirm endpoints | Claude Code |
| 1.4 | Question builder | Claude Code |
| 1.5 | Coverage counts | Claude Code |
| 1.6 | Dev-case counts: expected counts and the count test | Cowork (expected counts), Claude Code (test, CLI) |
| 1.7 | Determinism and completeness tests | Claude Code |
| 1.8 | Video script | Bhargavi with Cowork |

## Out of scope

Gateway, any live model call, the live Super suggestion call (wired in Phase 2), runs and the run state machine, `POST /runs` and every `/runs/...` endpoint (Phase 2), agents and orchestrator, `ai:` questions (added by agents in Phase 2), engineer-added questions (`POST /runs/{id}/questions` needs runs: Phase 2), findings, LOPA, ranking, tools, frontend screens (Phase 5 builds on the contract in parallel), demo plants. Do not start any of them.

## Super suggestions in this phase (decision to log)

`PROJECT.md` §15 lists "Super suggestions" in Phase 1. But the only path to a model is the gateway (Phase 2), and until then `scripts/live_call.py`, which backend code may not import (`CLAUDE.md` §3, `test_http_allowlist.py`). So Phase 1 builds everything around the suggestion except the call:
- the suggestion response schema, the prompt `prompts/section_suggestion/v1.md`, the validation and apply logic, and a `Suggester` protocol;
- a `NullSuggester` (returns no suggestions) used by the endpoint, and a `FakeSuggester` (returns fixed suggestions) used in tests.

Phase 2 adds `GatewaySuggester` as the gateway's first job (`section_suggestion: super`, capped by `section_suggest_cap_usd`). Record this in `docs/decisions.md` in PR 1 of this phase. Phase 1 therefore spends nothing.

---

## 1.1 Plant store and plant endpoints

**Build**
- `backend/guideword/runs/db.py`: SQLAlchemy models and a session factory from `settings.database_url` (SQLite in development). Phase 1 creates only `plants`, `plant_facts` and `sections` (`PROJECT.md` §11 storage list); later phases add their tables. Tables are created with `metadata.create_all`; no migration tool (no new dependency).
- `backend/guideword/runs/plants.py` (pure functions plus a repository class):
  - `load_plant(data, ref) -> (PlantRecord | None, ValidationReport)`: runs `schema.validate.validate_plant`. With errors, nothing is stored. With only warnings, the plant is stored with status `uploaded`.
  - Plant record ID `plant:<plant_id>:<h(plant file)>` (`ids.plant_record_id`), where `h` runs on the parsed JSON object as uploaded, not the Pydantic model, so a schema default never changes the ID (P11). Uploading the identical file again returns the existing record (idempotent). A changed file is a new record.
  - `plant_facts(plant) -> list[PlantFact]`: one fact per top-level field of every plant object, procedure steps included, that is not None and not an empty list (booleans count, including `false`) (`<object id>.<field>`), plus one per non-null operating limit (`<target_id>.operating.<parameter>.<limit field>`). Value objects are one fact at their parent's field (D10). `id` and `notes` are not facts, nor are the plant's `plant_id` and `schema_version`, a procedure's `steps` list, a chemical's `source`, or an operating row's instrument IDs (P10, Q3). Source, in this order: the provenance entry for the fact ID; else for the object ID; else a chemical's own `source` field; else `"not stated"`. Each fact with `"not stated"` is one `source_not_stated` warning (`object_id` = the object, the message names the field), never filled in (P3).
- Endpoints (non-mock; `api/`), using the `contract-v1` request and response models:
  - `POST /plants` → `PlantUploadResult`, HTTP 200 in both cases. With validation errors: `ok: false`, `plant_record_id: null`, every error as an `Issue` (code, object ID, message), and nothing stored. Otherwise `ok: true`, the record ID, `errors: []` and the warnings: the validation warnings, then the `source_not_stated` ones (Q8). (A body that is not JSON at all gets FastAPI's own 422, as the contract already declares.)
  - `GET /plants` → `PlantList` of `PlantSummary` (record ID, `plant_id`, status).
  - `GET /plants/{id}` → `PlantDetail`: facts with sources, warnings (validation warnings plus "not stated" sources), status, and the plant's current sections (empty until a propose). Unknown ID → 404 `ErrorBody`.
- `{id}` in every plant route is the plant record ID (`plant:<plant_id>:<hash>`), URL-encoded by the client.
- Each plant route leaves `NOT_BUILT_PHASE` in the PR that builds it (the three above in PR 1, propose and PUT in PR 3), and the 501 test covers only the routes still in the map (P7).

**Acceptance (tests first)**
- [x] `example_mixing_unit.json` uploads: `ok: true`, status `uploaded`, facts include `MX-1.design_pressure_kpa` with source `"assumed"` and `MX-1.operating.temperature.trip_high`.
- [x] A file with one validation error returns 200 with `ok: false`, that error and object named, and stores nothing.
- [x] Uploading the same file twice returns the same record ID and creates one row.
- [x] Changing one value gives a new record ID.
- [x] A fact with no provenance has source `"not stated"` and appears in the warnings.
- [x] Each dev case D–H uploads with no errors.
- [x] Tests use a temporary SQLite file per test; no network.

## 1.2 Section rules (the first cut)

**Build** `backend/guideword/sections/rules.py`: `rule_cut(plant: Plant, plant_record_id: str) -> list[Section]`, pure and deterministic. Every section has `drawn_by: "rule"`.

| Plant object | Sections | ID | Kind | Section type |
|---|---|---|---|---|
| Each equipment item (every type, pumps and compressors included) | one | `S-<equipment id>` | equipment | the equipment `type` |
| Each line with an empty `no_flow` | one per part (rule below) | `S-<line id>` for the first part; `S-<line id>~<split point id>` for each later part | line | `pipe` |
| Each line with a non-empty `no_flow` | one, never split, `flagged_no_flow: true` | `S-<line id>` | no_flow_line | `pipe` |
| Each procedure | one | `S-<procedure id>` | procedure | `procedure` |
| Each planned job | one | `S-<job id>` | planned_work | none |

**Line split rule.** A *split point* is a component on the line that is a valve of kind `control`, or equipment of type `pump`, `compressor` or `heat_exchanger`. Walk the line's `components` in order:
- The first part runs from `from_id` up to the first split point. Its ID is `S-<line id>`. It exists even if it holds no components (it is still a stretch of pipe).
- Each split point starts a new part that runs to the next split point or to `to_id`. Its ID is `S-<line id>~<split point id>`; the split point is that part's first component.
- A line with no split points is one section, `S-<line id>`.
- `object_ids` of a part: the line ID plus the components in that part, in order.

Utilities, locations, instruments, logic solvers, valves (other than as line components), safeguards, relief devices and chemicals get no section. Relief devices and chemicals get their questions from the cross lists (1.4).

**Names.** `name` defaults to the object ID plus its kind (P8): whole object `<id> (<type>)`, e.g. `MX-1 (mixer)` or `L-12 (pipe)`; a later line part `<line id> from <split point id> (pipe)`, e.g. `L-12 from P-1 (pipe)`; a no-flow line `<line id> (no-flow line)`; a procedure `<id> (procedure: <kind>)`; a job `<id> (<work type>)`. `purpose` is empty until a suggestion fills it. The engineer can rename; renaming never changes the ID.

**Acceptance (tests first)**
- [x] §9 example: sections exactly `S-MX-1`, `S-P-1`, `S-TOTE-1`, `S-L-12`, `S-L-12~P-1`, `S-L-STM`, `S-L-STM~TV-1`, `S-P-CHARGE`, `S-W-1` (hand-checked in the test), with the kinds and types in the table.
- [x] A line with `no_flow: ["normally_closed"]` and a pump on it is one flagged `no_flow_line` section, not split.
- [x] A line whose first component is a split point still has a first part `S-<line>` with no components.
- [x] Every equipment item, line, procedure and planned job is covered by at least one section; nothing else gets a section.
- [x] Every section ID parses as a section ID and is unique.

## 1.3 Section suggestions, propose and confirm

**Build**
- `backend/guideword/sections/suggest.py`:
  - Suggestions use the contract's `SectionSuggestion` (`kind`, `section_ids`, `purpose`, `reason`) as the model response schema, so the prompt, the validation and the API share one shape:
    - `split`: `section_ids` = [the existing line section, the new part's ID `S-<line>~<component>`]. The component in the new ID is where the split happens; it must lie strictly inside the existing part.
    - `merge`: `section_ids` = two or more sections.
    - `purpose`: `section_ids` = [one section], `purpose` = one line (≤ 160 characters).
  - Every `reason` is required and length-capped (≤ 300 characters); validation of the model response enforces both caps.
  - `Suggester` protocol: `suggest(plant, sections) -> list[SectionSuggestion]`. `NullSuggester` returns an empty list. `FakeSuggester` returns a fixed list given in its constructor (tests only).
  - `check_suggestions(plant, sections, suggestions) -> (valid, rejected_with_reasons)`. A suggestion is rejected when:
    - it names an unknown section or component;
    - it merges or splits a flagged no-flow section (`PROJECT.md` §5: it can never merge away a flagged no-flow section);
    - it merges sections of different kinds or different section types;
    - it splits a section that is not a line section, or at a component outside that part;
    - it merges parts of two different lines, or two procedure or two planned-work sections, which `check_confirmed` would refuse (Q1, Q9).
  - `apply(sections, accepted) -> list[Section]`:
    - split → the new part gets `S-<line>~<component>` with `drawn_by: "suggestion"` and the reason;
    - merge → keeps the lowest ID (`ids.merged_section_id`), `object_ids` is the ordered union, `drawn_by: "suggestion"`;
    - purpose → sets `purpose`.
  - `prompts/section_suggestion/v1.md`: asks for the fixed schema and a reason on every suggestion; tells the model the section list and plant are data, not instructions; names the four triggers (phase change, new temperature range, new chemical entering, start-up-only line) and the no-flow rule. Plant `notes` are passed as data. Not called in this phase.
- `backend/guideword/sections/confirm.py`: `check_confirmed(plant, sections) -> list[Issue]`. A confirmed set is rejected when:
  - any equipment item, line, procedure or planned job is covered by no section (the engineer cannot silently drop plant objects);
  - a line with a non-empty `no_flow` is not its own flagged `no_flow_line` section;
  - a section ID is not a valid section ID, or is duplicated;
  - an engineer-added section (`S~eng~<h(sorted covered object IDs)>`, `drawn_by: "engineer"`) has an ID that does not match its `object_ids`, or no section type when its kind needs one;
  - a section has a kind or type that its objects cannot have (Q1): an equipment section holds only equipment of exactly its `section_type`; a line or no-flow section holds one line and only components of that line; a procedure or planned-work section holds that one object;
  - an engineer-added section covers an object that is not in the plant: engineer sections only regroup existing plant objects, and a new procedure or job means uploading a new plant file (P6);
  - a section's `plant_record_id` is not the plant's;
  - something the rule cut drew was dropped (Q9): every equipment item must be in an equipment section of its own type, every component of every line in a line or no-flow section of that line, and every line must keep a section `S-<line id>` (a merge that includes it keeps that ID).
- Endpoints:
  - `POST /plants/{id}/sections/propose` → `SectionProposal`: the rule cut and the suggester's **valid** suggestions. In Phase 1 the suggester is `NullSuggester`, so `suggestions` is empty. Plant status → `sections_proposed`; the rule cut is stored as the plant's current sections.
  - **Rejected suggestions:** `SectionProposal` has no field for them in `contract-v1`. Each one is logged through `guideword/logs.py` with its reason (never dropped without a trace). Whether to show them on screen is a Phase 2 decision with a `contract/...` change, taken when the live suggester exists. Record this in `docs/decisions.md`.
  - `PUT /plants/{id}/sections` with `ConfirmSectionsRequest` (a list of `Section` records: accepted, rejected or edited suggestions already applied by the client, renames, engineer-added sections) → `ConfirmSectionsResult` (record ID, status, section IDs). Every section's `plant_record_id` must equal `{id}`. Issues from `check_confirmed` → 409 `ErrorBody` whose `detail` lists each issue on its own line as `<code> <object id>: <message>`. Otherwise the set is stored, `PlantRecord.confirmed_section_ids` is set, and the status → `sections_confirmed`. A later propose or PUT replaces the stored set and moves the status accordingly (P5): a propose after confirm stores the new rule cut, clears `confirmed_section_ids` and moves the status back to `sections_proposed` (existing runs keep their own snapshots); a PUT is allowed from any status, including straight after upload, with `check_confirmed` as the guard.

**Acceptance (tests first)**
- [ ] With `FakeSuggester`: a valid split `section_ids=["S-L-12~P-1", "S-L-12~HV-12"]` creates `S-L-12~HV-12`; a merge keeps the lowest ID; a purpose is set. Each carries its reason as `suggestion_reason` and `drawn_by: "suggestion"`.
- [ ] Each rejection rule above produces a rejected suggestion with its reason, and the endpoint logs it; none raises.
- [ ] A merge that includes a flagged no-flow section is rejected.
- [ ] Each `check_confirmed` rule has a test that produces exactly that issue with the offending ID.
- [ ] Q9 on the §9 example: a valid split passes, a dropped empty first part fails, a dropped equipment section fails, a dropped later part fails, and a merge of two parts of one line passes.
- [ ] Propose then PUT on the §9 example moves the plant `uploaded → sections_proposed → sections_confirmed`; the stored sections read back identical.
- [ ] Renaming a section in the PUT body keeps its ID.
- [ ] The prompt file exists, asks for the schema and a reason, and is not called by any code in this phase (test: nothing imports a model client).

## 1.4 Question builder

**Build** `backend/guideword/questions/build.py`: `build_questions(plant, sections, ref, run_id) -> list[Question]`, pure and deterministic. Every question has status `open`. Run IDs arrive in Phase 2; tests pass a fixed `run:test`.

| List | Rule (`PROJECT.md` §5 Step 3) | ID | Kind | Origin |
|---|---|---|---|---|
| Matrix | for each section of kind equipment, line or no_flow_line: one question per `applicability.csv` row whose `section_type` equals the section's type | `m:<section>:<guideword>:<parameter>` | matrix | matrix |
| Chemical pairs | every unordered pair of distinct chemicals in the plant: n(n−1)/2 | `pair:<a>:<b>` (sorted) | chemical_pair | cross_list |
| Chemical environment | every chemical × water, air, heat: 3n | `env:<chem>:<water\|air\|heat>` | chemical_environment | cross_list |
| No-flow lines | every line with a non-empty `no_flow` | `nf:<line>` | no_flow_line | cross_list |
| Procedure steps | every step of every procedure × `ref.procedure_guidewords` (the five) | `proc:<step>:<guideword>` | procedure_step | cross_list |
| Planned work | every job × every target within reach (rule below) | `work:<job>:<target>` | planned_work | cross_list |
| Dust | every equipment item of type `solids_handler` or `dryer`, plus any equipment whose `contents` include a chemical with `combustible_dust: true` (each equipment item once) | `dust:<equipment>` | dust | cross_list |
| Relief | every relief device | `relief:<device>` | relief_discharge | cross_list |

Procedure and planned-work sections get no matrix questions. No-flow line sections get both the pipe matrix questions and their `nf:` question.

**"Within reach" of a job**, the union (each target once):
- its `equipment_ids` and `line_ids`;
- every equipment item whose `location_id` is the job's location;
- every line whose `from_id` or `to_id` is in the job's location: an endpoint equipment item or utility located there, or the location itself;
- every relief device whose `discharge.location_id` is the job's location; the target is the relief device ID (P9);
- every other planned job at the same location whose time window overlaps the job's (`a.start <= b.end and b.start <= a.end`, so touching windows overlap). If either job has no `start` or `end`, or the two jobs' times mix time zones, overlap cannot be ruled out, so the other job is included (completeness over precision) (Q4). A job with no location shares a location with no other job (P4).
- If the union is empty (a job with no location and no listed objects), the job gets one question `work:<job>:<job>`, so every job is checked at least once.

**Section of each question:** matrix → its section; `nf:` → the line's section; `proc:` → the procedure's section; `work:` → the job's section; `dust:` → the equipment's section; `relief:` → the section of the protected equipment (`protects_id`), or none if it protects a location; `pair:` and `env:` → none (plant-wide). An equipment-keyed question (`dust:`, `relief:`) takes the equipment-kind section containing that equipment, and a line-keyed one (`nf:`) the line's section; if several qualify, the lowest section ID (Q5).

**Question text** comes from fixed templates in `questions/text.py`, filled only with IDs, names and enum values: for example "More pressure in S-MX-1 (mixer): what could cause it, what would happen, and is the existing protection adequate?" Templates are neutral. They never add facts, hints or causes, and never read `notes`.

**Order.** The list is sorted by list (the table order above), then by ID. The position in this order is the question's number in the worksheet; it is display only and never part of an ID.

`Question.fact_ids` stays empty in this phase. Choosing the facts each specialist needs is Phase 2 work (specialist context), so it is decided there, not guessed here.

**Acceptance (tests first)**
- [x] §9 example: exact counts per list, hand-computed in the test file with the arithmetic written out (e.g. matrix = mixer rows + pump rows + tank rows + 4 pipe parts × pipe rows).
- [x] Chemical counts: n = 0, 1, 2, 10 give 0, 0, 1, 45 pairs and 0, 3, 6, 30 environment questions.
- [x] A no-flow line produces its pipe matrix questions plus exactly one `nf:`.
- [x] Procedure steps × 5; the `before` and `after` guidewords never appear in `proc:` IDs.
- [x] Within reach: one test per bullet above, including overlapping windows, a missing window (included) and the empty case (`work:<job>:<job>`).
- [x] Dust: an equipment item that is a dryer *and* contains combustible dust gets one `dust:` question, not two.
- [x] Every ID parses with `ids.parse_question_id`; no duplicates; every question's `section_id` exists in the section set or is none.
- [x] Templates never include note text (test with a plant whose notes contain a marker string).

## 1.5 Coverage counts

**Build** `backend/guideword/questions/coverage.py`: `coverage(sections, questions, findings=()) -> tuple[list[CoverageList], list[str]]` (the `contract-v1` `CoverageList` lines and the failed question IDs). The `GET /runs/{id}/coverage` endpoint that wraps them in `Coverage` with the run's label is Phase 2, when runs exist.
- One `CoverageList` per list, in this order, with `list` set to: `sections`, then every `QuestionKind` value (`matrix`, `chemical_pair`, `chemical_environment`, `no_flow_line`, `procedure_step`, `planned_work`, `dust`, `relief_discharge`, `added_by_ai`, `engineer`). Each line has `total`, `checked`, `unsure` and `failed`.
- A question counts as checked only when its status is `answered` or `not_credible`. `failed` counts per list, and every failed question ID is returned.
- A section counts as checked when every question whose `section_id` is that section is checked; a section with no questions counts as checked. On the `sections` line, `unsure` is the number of sections with at least one answered question that has an unsure finding, and `failed` the number with at least one failed question (Q6).
- Unsure: the number of `answered` questions whose findings include one with confidence `unsure`, shown separately. With no findings (this phase) it is 0.
- Lists with no questions show `0 of 0`, never disappear.

**Acceptance (tests first)**
- [ ] On a freshly built list everything is `0 of N` with the exact N per list.
- [ ] Marking questions answered, not credible and failed moves `checked` and the failed list exactly as defined; failed never counts as checked.
- [ ] Unsure counting with a fake finding of confidence `unsure`.
- [ ] A section with one open question is not checked; when that question is answered, it is.

## 1.6 Dev-case counts

**Build**
- **Expected counts (Cowork, independent of the builder):** once the dev cases from 0.7 are merged, Cowork computes the expected count per list for each case from the plant files with a separate script written outside this package, using the rule cut (no suggestions applied). The result is committed by Bhargavi as `cases/dev/expected_counts.json` (`{case: {list: count}}`) with a short `cases/dev/expected_counts.md` explaining each count. **Claude Code never edits these two files.**
- `backend/tests/cases/test_question_counts.py`: for each case D–H, upload → rule cut → build questions → coverage; every list count equals `expected_counts.json`.
- `scripts/build_questions.py <plant file>`: prints the section cut and the counts per list (human-readable CLI output, so `print` is allowed). No live calls.

**If a count disagrees:** stop and ask. Do not change the expected file, and do not change the builder to match it. Bhargavi and Cowork find which side breaks the §5 rule, and the fix is a commit with its reason.

**Acceptance**
- [ ] All five cases match every list count exactly.
- [ ] `scripts/build_questions.py cases/dev/case_g.json` runs on Windows and prints the counts.

## 1.7 Determinism and completeness

**Acceptance (tests first)**
- [x] Building twice gives identical sections and questions (same IDs, same order, same text).
- [x] Shuffling every list in the plant file (equipment, lines, chemicals, procedures and so on, but not a line's `components` or a procedure's `steps`, whose order is meaningful) gives the identical section set and question list.
- [x] Two separate processes give identical output (IDs are content-built).
- [x] No code path deletes a question: the builder's output is append-only, and no function in `questions/` removes items from a question list (test over the module's public functions with a known list).
- [x] `sections/` and `questions/` import no HTTP or model client (allow-list test still passes).

## 1.8 Video script (Bhargavi, with Cowork drafting)

- [ ] `docs/video-script.md` by **Oct 15**, before the frontend screens are built, following `PROJECT.md` §14: problem (≈20 s), Guideword running (≈60 s), the Williams Geismar moment (≈40 s), the numbers (≈40 s), close (≈20 s). Under 3 minutes spoken (about 400 words).
- [ ] Names Nebius Token Factory and each Nemotron model out loud.
- [ ] A shot list per beat naming the screen (§12) and what is visible, so Phase 5 builds the screens the video needs.
- [ ] Every number is a placeholder (`[x of n]`, `[cost per study]`) to be filled from run records. No invented results.

---

## PR order (the plan may refine it)

| # | Branch | Items | Depends on |
|---|---|---|---|
| 1 | `phase-1/plant-store` | approved plan; 1.1; decisions-log lines for "Super wired in Phase 2" and "rejected suggestions logged, not returned" | `contract-v1` |
| 2 | `phase-1/section-rules` | 1.2 | PR 1 |
| 3 | `phase-1/section-suggest-confirm` | 1.3 | PR 2 |
| 4 | `phase-1/question-builder` | 1.4, 1.7 | PR 2 |
| 5 | `phase-1/coverage` | 1.5 | PR 4 |
| 6 | `phase-1/dev-case-counts` | 1.6 | PR 4, PR 5, dev cases (0.7), `expected_counts.json` |

PRs 3 and 4 can run in parallel after PR 2. 1.8 is not code and runs alongside.

**If time runs short:** the gate is the exact counts on D–H, so the priority order is PR 2 → 4 → 5 → 6, then 1 → 3. The endpoints (1.1, 1.3) can slip into the first day of Phase 2 without blocking test #5; the builder and counts cannot.

## Done when

- [ ] Every acceptance box above is ticked, CI green on `main`.
- [ ] The question counts on D–H match `expected_counts.json` exactly.
- [ ] `docs/video-script.md` is written.
- [ ] Phase 1 spent $0.00 (ledger unchanged).
- [ ] Every decision taken in this phase has a dated line in `docs/decisions.md`.
