# Benchmark case template

For the person writing held-out benchmark cases. Each case is one past industrial accident, written as the plant looked **before** the accident, plus a sealed answer key. Cases and keys live in your own private repository (`guideword-heldout`), never in this one, until the benchmark has been run and scored.

This template names no sources and no accidents on purpose.

---

## 1. Choosing a case

A case qualifies only if all of these hold:

- [ ] A public investigation describes the plant in enough detail to rebuild it: equipment, chemicals, procedures, safeguards.
- [ ] The investigation states the root cause.
- [ ] It is **not** a famous accident. Well-known disasters are excluded because models recognise them, which would test memory instead of reasoning. If you would expect an engineer to know it by name, skip it.
- [ ] It has not been used in any earlier test of this project.
- [ ] Taken together, the set mixes countries (aim for about half outside the US) and plant types.

Aim for 6 to 10 cases.

## 2. The data package (what the tool reads)

Write one Markdown file per case, `case_<letter>_<short-name>.md`. It describes the plant, not the accident.

**Rules**

- **Before the accident.** Describe the plant, its operation and any planned work as they stood beforehand. Never describe what happened.
- **No hints.** Do not name the root cause, the failed item or the outcome, and do not give any one item more detail than its neighbours. Words like "unfortunately", "critical" or "should have" give the answer away.
- **Mix in unrelated equipment.** Add three or more plausible items, lines or procedures from the same plant that had nothing to do with the accident, described at the same level of detail.
- **Facts from the source only.** If the source does not state a value (a design pressure, a valve position), leave it out. Do not fill gaps with typical values.
- **Neutral identities.** Replace the company, site, town, dates and any distinctive product names with neutral ones (e.g. "Plant K", "a coastal site"). Keep the chemistry and the equipment real.
- **Units.** Give every number with its unit, and say whether a pressure is gauge or absolute.

**Shape** (the headings are a guide; use the ones the case needs)

```markdown
# Plant K: <type of unit or area, neutral>

## Data package

**Process / products**
- <feed, main steps, products, rates with units>

**Major equipment**
- <ID> <what it is>, <stated conditions with units>
- ... (include the unrelated items)

**Lines and connections**
- <size> <line>, from <A> to <B>, <normally open / normally closed / used only during ...>

**Chemicals on site**
- <name> (<form>), <where it is kept>

**Procedures**
1. <step as written in the plant's procedure>

**Planned work** (if any)
1. <job, where, when, what it involves>

**Instrumentation and safeguards**
- <alarms, trips, relief devices and where they discharge, detectors, permits>

**Surroundings**
- <occupied buildings, nearby units, distances>

## Task
Perform a full HAZOP of this <unit / area / procedure>.
```

## 3. The plant file (how the package becomes data)

Each package is converted into a plant file in the format of `PROJECT.md` §9 (validated by `backend/guideword/schema/plant.py`). The conversion follows the same rules as the development cases:

- every object gets an ID matching `^[A-Za-z0-9][A-Za-z0-9_-]*$` (no `.`, `:`, `~` or `+`);
- a fact the package states goes in its field, with the package as `provenance`;
- words the schema has no field for go in `notes`, verbatim;
- a fact the package does not state stays empty. If a value has to be assumed, it is proposed, approved, and marked `"assumed"`.

A minimal skeleton:

```json
{
  "plant_id": "case_k",
  "schema_version": "1.0",
  "locations": [{"id": "LOC-K-UNIT", "description": "process unit", "occupied": true}],
  "equipment": [
    {"id": "V-1", "type": "vessel", "location_id": "LOC-K-UNIT", "contents": ["CHEM-A"],
     "design_pressure_kpa": 1000,
     "notes": [{"text": "<the package's exact words>", "source": "case_k_short-name.md"}]}
  ],
  "lines": [{"id": "L-1", "from_id": "V-1", "to_id": "LOC-K-UNIT", "no_flow": [], "contents": ["CHEM-A"]}],
  "chemicals": [{"id": "CHEM-A", "name": "<chemical name>"}],
  "provenance": {"V-1": "case_k_short-name.md"}
}
```

## 4. The answer key (sealed; the tool never sees it)

One JSON object per case in `keys/answer_keys.json` in your repository. It is used twice: an **automatic score** looks for the root cause in the tool's ranked shortlist (top 3, top 10, or missed) after normalising text; a **human score** (hit, partial or miss, with a reason) reads the full key.

```json
{
  "case_id": "case_k",
  "root_cause": "One or two plain sentences: what failed, how, and why it was not caught.",
  "component_ids": ["V-1", "L-1"],
  "cause_ids": ["C15"],
  "match_phrases": ["left closed", "isolated from its relief"],
  "consequence": "What the failure led to, in one sentence.",
  "missed_by_original_review": "What the plant's own hazard review or procedures missed, as the investigation states it.",
  "multi_failure": false,
  "source": {"kind": "public investigation report", "reference": "<title, publisher, year>", "pages": "<pages>"}
}
```

| Field | Meaning |
|---|---|
| `case_id` | Matches the plant file's `plant_id`. |
| `root_cause` | The investigation's root cause, in your words. |
| `component_ids` | Plant-file IDs of the items that failed or were involved. A shortlist entry on one of these is a candidate match. |
| `cause_ids` | The closest cause-library IDs from `reference/causes.csv`, or `[]` if none fits. |
| `match_phrases` | Two to five short phrases that a correct answer would contain, for the automatic score. Avoid words the package itself uses for the item. |
| `consequence` | What happened, briefly. |
| `missed_by_original_review` | What the original review missed: this is the claim the benchmark tests. |
| `multi_failure` | `true` if the accident needed two or more independent failures together. |
| `source` | Where the facts come from. Kept in the sealed repository only. |

## 5. Before you hand a case over

- [ ] The package reads as an ordinary plant description; someone who knows the accident could not tell which item matters.
- [ ] At least three unrelated items are in the package, at the same detail.
- [ ] Every number has its unit; every pressure says gauge or absolute.
- [ ] No company, site, town or date can identify the accident.
- [ ] The answer key's `component_ids` exist in the plant file.
- [ ] The package, plant file and key are committed to your repository only.
