# guideword-heldout

Held-out benchmark cases for Guideword. **Bhargavi does not open anything in this folder before Phase 6.** Claude Code never reads it.

- `case-template.md` — copied from the Guideword repo (`docs/case-template.md`); the format every case follows.
- `cases/` — one data package per case (`case_<letter>_<short-name>.md`): the plant as it was before the accident, no hints, with unrelated equipment mixed in.
- `keys/` — one sealed answer key per case (`case_<letter>.json`): source, what actually happened, the match phrase groups, memorisation markers.
- `SEALS.txt` — one line per file: `<sha256>  <path>  <UTC date>`. Only this file's contents (hashes, no names) are copied into the Guideword repo as `bench/heldout-seals.txt`.
- `selection-log.md` — inside this folder only: why each case was chosen and which candidates were rejected.

Written by a separate Claude session that does not design Guideword's rules or prompts.
