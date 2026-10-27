# Converting the held-out packages into plant files (Phase 6, P6-12)

These are the instructions for the **fresh Claude session** that turns each held-out package
into a plant file. Bhargavi starts that session in `D:\Hackathon\guideword\guideword-heldout`
and gives it this file. The session that builds Guideword never takes part (CLAUDE.md §5).
The rules are the dev-case conversion rules (`cases/dev/conversion-report.md`, CLAUDE.md §10)
applied to the held-out cases. All of this is finished and frozen before the probe.

## What you may read

- **One package at a time:** `cases/case_<letter>_<name>.md`, the case you are converting.
- **The plant format:** `docs/case-template.md` §3 and `contract/schemas/plant.schema.json`
  in the Guideword repo (`D:\Hackathon\guideword\guideword`). `PROJECT.md` §9 is the long form.
- **How the dev cases were converted:** `cases/dev/conversion-report.md` in the Guideword repo:
  its conventions and its layout, not its facts.
- **Reactivity groups**, to propose a chemical's `epa_groups` and `cameo_groups` as the dev
  report did: `reference/reactive_groups.csv` in the Guideword repo.

## What you must never open

- **`keys/`**, any file in it, for any reason. The keys are the answers.
- `selection-log.md`, `README.md`, `seal.sh` and `SEALS.txt` in the held-out folder: none is
  needed to convert a package, and some may name the source.
- Anything on the web about the case, and any accident report.

## What to write, per case

1. **`plants/case_<letter>.json`**: the plant file. It must validate. Bhargavi checks it with
   `heldout_verify.py`, which prints every error by object ID and field.
2. **One section in `plants/conversion-report.md`**, in the dev report's layout:
   - **Proposed assumptions**: one line per value the package does not state but the plant file
     needs, as an unticked box: `- [ ] <fact ID> = <value> (<why it is needed>)`. Nothing goes
     into the plant file until Bhargavi ticks it; a ticked value is marked `"assumed"` in
     `provenance`.
   - **Package facts the schema can't hold**: quoted, with the block that would need to change.
   - **Remaining warnings**.

## The rules

- **Never invent a fact.** A fact the package states goes in its field, with the package's file
  name as `provenance`. A fact it doesn't state stays empty, or is proposed as an assumption.
- **Keep every ID the package uses**, exactly as written. Where the package names a thing
  without an ID, make one that matches `^[A-Za-z0-9][A-Za-z0-9_-]*$`: no `.`, `:`, `~` or `+`.
  The keys name plant IDs, so a renamed ID is a scoring error; if one must change to be valid,
  list it in `plants/fixes.md` as `- rename: OLD -> NEW`.
- **Words the schema has no field for** go in `notes`, verbatim, with their source.
- **Classify nothing beyond what the package says.** No `no_flow: dead_leg` unless the package
  says dead leg; no safeguard credited unless the package describes it; equipment `type` is the
  closest enum value to the package's own word.
- **Units live in field names**: `_kpa` is always gauge, `_kpaa` absolute, `_c`, `_m3`, `_kg_h`,
  `_per_year` and the rest of PROJECT.md §9. Convert as the dev report did (1 bar = 100 kPa,
  2" = 50.8 mm) and keep "about" values as stated, with the words in a note.
- **A line end the package doesn't name** goes to the case's `LOC-<case>-UNSTATED` location.
- **One case per session turn**: finish, validate and report one case before opening the next
  package, so no case's wording leaks into another.

## When all eight are done

Bhargavi ticks the assumptions, the session writes the ticked values, and then, from the freeze
worktree:

```powershell
python scripts/heldout_verify.py D:\Hackathon\guideword\guideword-heldout --frozen-out D:\Hackathon\guideword\guideword\bench\heldout-frozen.txt
```

It stops unless every sealed file still matches, every package has a plant file and every plant
file validates. Then `bench/heldout-frozen.txt` is committed in a small PR, the plant files are
committed to the held-out repo, and the probe can start. If any ID was renamed, copy
`plants/fixes.md` to `bench/heldout/fixes.md` in the Guideword repo, where the scorer reads it.
