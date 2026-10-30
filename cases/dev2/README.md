# Development cases, set 2 (Phase 9 spec 9.0)

Fifty past accidents from the ARIA, eMARS and CSB public records, written as the plant looked
before the accident, by a separate case-writer session following `docs/case-writing-v2.md`.
**Labelled development:** the builders read them, run ablations on them and tune against them,
so nothing measured on them is evidence. Real evidence needs a new sealed set.

- `cases/case_<nn>_<short-name>.md`: the package the tool reads.
- `keys/case_<nn>.json`: the key (template fields plus the protocol's).
- `plants/case_<nn>.json`: the plant file.
- `selection-log.md`: every accepted case with its source, every rejected candidate with the
  reason.

Nothing reads the folder until `python scripts/dev2_check.py cases\dev2` passes.
