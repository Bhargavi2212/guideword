# Writing the development cases, set 2 (Phase 9 spec 9.0)

For the **separate case-writer session** that writes `cases/dev2/`: fifty past industrial
accidents from the ARIA, eMARS and CSB public records, each written as the plant looked
**before** the accident, with a key and a plant file. These cases are labelled **development**:
Guideword's builders will read them, run ablations on them and tune against them, so nothing
measured on them is evidence. Real evidence needs a new sealed set that nobody on the project
has read (`docs/case-template.md`, the held-out protocol).

The session that builds Guideword never takes part in writing these cases (CLAUDE.md §5). Work
in a folder outside the repo, for example `D:\Hackathon\guideword\guideword-dev2`, with the same
three sub-folders; Bhargavi copies the result into `cases/dev2/` once `scripts/dev2_check.py`
passes.

## What you may read

- `docs/case-template.md` (the package, plant-file and key formats) and
  `docs/heldout-conversion.md` (the conversion rules), both in the Guideword repo.
- `contract/schemas/plant.schema.json` and `PROJECT.md` §9, for the plant file.
- `reference/causes.csv` (for `cause_ids`) and `reference/reactive_groups.csv` (for a
  chemical's groups), in the Guideword repo.
- The public investigation record of the case you are writing.

## What you must never read

- Guideword's prompts (`prompts/`), its rules (`backend/guideword/`), its specs or its earlier
  cases (`cases/dev/`, `cases/heldout/`). A case written with the tool's rules in mind tests the
  rules, not the plant.

## Choosing the fifty

1. **Sources:** ARIA detailed sheets (BARPI), eMARS full reports (Seveso accidents) and CSB
   investigation reports and case studies. Aim for about half outside the US and a spread of
   process types (storage, batch reactors, continuous reactors, distillation, gas processing,
   solids and dust, utilities) and of mechanism classes (see the key below).
2. **Qualifies** only if the record describes the plant well enough to rebuild it (equipment,
   chemicals, procedures, safeguards) and states the root cause.
3. **Time split:** record the report's publication year. Prefer reports published after the
   models' training cutoffs where you can; keep the year in the key, never in the package.
4. **Contamination subset:** a famous accident (one an engineer would know by name) may be
   included only with `contamination.flagged = true` and the reason; it is reported apart.
5. **Not used before:** none of Guideword's earlier cases (D–H, K–S, the demo plants). Bhargavi
   gives you that list of sources without the cases themselves.
6. Keep a `selection-log.md`: every accepted case with its source, and every rejected candidate
   with the reason.

## Writing one case (one per turn; finish it before opening the next record)

1. **The package**, `cases/case_<nn>_<short-name>.md`, in the template's shape, numbered
   `01` to `50`:
   - the plant **before** the accident: process, equipment, lines, chemicals, procedures,
     planned work, instruments and safeguards, surroundings, with units;
   - **three or more unrelated items** from the same plant, at the same level of detail;
   - **neutral identities**: no company, site, town, country, date or distinctive product name;
   - **no outcome and no hint**: nothing about what happened, no "unfortunately", "critical",
     "should have", no investigators' language;
   - **pre-existing conditions an engineer could have known**, stated plainly where the record
     states them: recent changes, bypassed or overdue safeguards, the operating mode (these
     become the plant file's `changes` and `impairments` blocks where the schema has them);
   - facts from the record only; a value the record does not give is left out.
   Run `python scripts/case_lint.py cases/case_<nn>_<short-name>.md` and fix every flag, or note
   in the selection log why a flag is a false positive.
2. **The three-mechanism check:** a second person (or a second session that has not read the
   record) reads the package alone and names three distinct mechanisms that fit it. If fewer
   than three fit, the package points at the answer: rewrite it. Record who did the check in the
   key's `second_check`.
3. **The key**, `keys/case_<nn>.json`: the template's fields (`case_id`, `root_cause`,
   `component_ids`, `cause_ids`, `match_phrases`, `consequence`,
   `missed_by_original_review`, `multi_failure`, `source`) plus:
   - `reference_mechanism`: one to three sentences, initiating event → path → consequence,
     from the record, checked by a second person;
   - `report_year`: the publication year of the record;
   - `process_class`: one of `storage`, `batch_reactor`, `continuous_reactor`, `distillation`,
     `gas_processing`, `solids_dust`, `utilities`, `transfer_loading`, `other`;
   - `operating_mode`: one of `normal`, `startup`, `shutdown`, `maintenance`,
     `idle_or_standby`, `batch_step`, `changeover`, `other`;
   - `mechanism_class`: one of `runaway_reaction`, `wrong_material_or_contamination`,
     `corrosion_erosion`, `isolation_or_blocked_in`, `defeated_safeguard`, `change_without_review`,
     `dust_explosion`, `hot_work`, `overpressure_other`, `loss_of_containment_other`, `other`;
   - `contamination`: `{"flagged": bool, "reason": str}`;
   - `second_check`: `{"three_mechanisms_fit": bool, "by": str}`.
4. **The plant file**, `plants/case_<nn>.json`, by the conversion rules of
   `docs/heldout-conversion.md`: every object ID matches `^[A-Za-z0-9][A-Za-z0-9_-]*$`; a
   stated fact goes in its field with the package as provenance; words the schema has no field
   for go in `notes` verbatim; nothing is invented; assumptions are proposed in
   `conversion-report.md` and marked `"assumed"` only once ticked.

## Before handing over

```powershell
python scripts/dev2_check.py D:\Hackathon\guideword\guideword-dev2
```

It stops unless every package lints clean, every case has all three parts, every key has every
field, every plant file validates, and every key component is a plant ID. Bhargavi then copies
the folder into `cases/dev2/`, commits it with the selection log, and the ablations can read it.
