# Held-out conversion report (P6-12)

Eight held-out packages in `cases/` converted to plant files `plants/case_k.json` … `case_s.json`, one case per session turn, in letter order. Rules (`docs/heldout-conversion.md`): only the package being converted was read, never `keys/`; facts are the package's own words; nothing is classified beyond what the package says. Every object and stated value has its package file as provenance. Words the schema has no field for are kept verbatim in `notes`.

**How to review:** tick a proposed assumption (`- [x]`) to accept it; the session then writes that value into the plant file with `"assumed"` in `provenance`. Leave it unticked to keep the gap. The modelling choices in section 3 are not assumptions (no value was invented), but each one shapes the question list, so say if any should change.

**Conventions used in every case** (as in `cases/dev/conversion-report.md`)

- A line end the package does not name goes to the case's `LOC-<case>-UNSTATED` location ("endpoint not stated in the package"), so no endpoint is guessed.
- Units are converted to the field-name units: bar g to kPa gauge (1 bar = 100 kPa), psig to kPa gauge (1 psi = 6.894757 kPa), inches to millimetres (2" = 50.8 mm). "About" and "~" values are entered as stated, with the words in a note.
- Safeguards the package lists are entered with their package words as `description` and no `layer_type`, so code gives none of them LOPA credit.
- Equipment `type` is the closest enum value to the package's name for it (listed per case in section 3).
- No package states EPA or CAMEO groups, so groups are proposed in section 1 from `reference/reactive_groups.csv`.
- **Assumption rule** (Bhargavi, case K review, 2026-10-28): section 1 proposes only reactivity groups and obvious physical forms. Volumes, pressures, valve positions, `no_flow` classes, line contents and locations that the package does not give are left empty and never proposed.
- No object is made from a verb: "started manually" is not a valve. A line is drawn only where a package sentence puts the flow there.

---

## case_k — Plant K: batch solution-polymerisation reactor area

Source: `cases/case_k_batch-polymer.md`.

### 1. Proposed assumptions

Ticked by Bhargavi in the case K review (2026-10-28). All are written into the plant file and marked `"assumed"` in `provenance`.

- [x] `R-1.design_pressure_kpa` = 517.1 (from "Maximum allowable working pressure 75 psig"; MAWP entered as design pressure on Bhargavi's instruction, with the sentence kept as a note on R-1)
- [x] `MONOMER.epa_groups` = [103] (polymerizable compounds; "free-radical polymerisation of acrylic monomers". The ester group 13 is not proposed, as the package does not say which acrylic monomer it is)
- [x] `MONOMER.cameo_groups` = [76] (polymerizable compounds)
- [x] `ALIPHATIC-SOLVENT.epa_groups` = [29] (hydrocarbons, aliphatic, saturated; the package says only "aliphatic")
- [x] `ALIPHATIC-SOLVENT.cameo_groups` = [29]
- [x] `AROMATIC-SOLVENT.epa_groups` = [16] (hydrocarbons, aromatic)
- [x] `AROMATIC-SOLVENT.cameo_groups` = [16]
- [x] `INITIATOR-SOLUTION.cameo_groups` = [99] (initiator not named; composition not stated)
- [x] `PRODUCT-K-7.cameo_groups` = [99] (polymer composition not stated)
- [x] `SILICA.cameo_groups` = [98] (not chemically reactive)
- [x] `INITIATOR-SOLUTION.physical_form` = liquid ("solution")
- [x] `SILICA.physical_form` = solid ("powder"; `dust` is not proposed because nothing says the silica is combustible)

Why: the reactivity lookup and the chemical-pair questions need groups and forms.

Left empty under the assumption rule: R-1 volume ("1,500 gal" does not say US or imperial), R-1 normal pressure, every valve position, `no_flow` on the jacket cooling line, the contents of the E-1, utility and vent lines and of the stripping station, and every location except R-1's.

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- Batch size: "the batch target is 6,080 lb of polymer", and "The current customer order is 12% larger than the usual order". The `chemicals` and `equipment` blocks have no field for batch mass or charge. Note on `PRODUCT-K-7`.
- Recipe change: "Monomer is increased by 12%; the extra monomer goes into the initial (Stage 1) charge." and "the aliphatic solvent is cut by 12%; aromatic solvent is increased by 6%. Total solvent is slightly below the standard recipe." The `procedures` and `planned_work` blocks have no field for recipe quantities. Notes on `W-K-1`.
- "The plant chemist estimated the effect of the solvent change on the mixture boiling point at about 1 °C (1.8 °F)." Mixture properties have no home in `chemicals`. Note on `W-K-1`.
- Manway closure: "closed with 4 removable clamps. The manufacturer's specification calls for 18 clamps for a tight seal at 75 psig." The `equipment` block has no field for closure or bolting. Note on `R-1-MW`.
- Condenser condition: "Design capacity not documented. In service about 30 years; the water side has not been opened for inspection or cleaning in that time." Also "Plant instruments cannot measure the E-1 cooling load." `heat_duty_kw` stays empty because no value is stated. Notes on `E-1`.
- "Set pressure not recorded in the available records. Other relief valves on site are set at their rated pressures." `set_pressure_kpa` stays empty. Note on `PSV-1`.
- The two solvents are called "flammable", but no flash point is given and `chemicals` has no flammability flag. Notes on the chemicals.
- The "Not installed on R-1: …" list is a note on `R-1`. It is not modelled as missing safeguards, because the schema can only hold protection that exists.
- Management and people facts (no PHA, no MOC, no calorimetry, informal training, emergency plan, no audit, staffing and time in post) are plant notes. No block holds organisational facts.
- Timing of the batch steps across shifts ("prepared and charged on the day shift; part of the monomer charged on the second shift; heating and initiator addition on the following day shift"). No dates are given, so `W-K-1` has no `start` or `end`. Note on `W-K-1`.

### 3. Modelling choices to confirm

- **Equipment types:** R-1 → `reactor`; E-1 → `heat_exchanger`; R-1-MW (manway) → `other`; initiator solution vessel → `vessel`; feed pumps → `pump`; solvent storage → `tank`; silica adsorption / powder conversion area → `solids_handler`; solvent stripping and drum-filling station → `other`.
- **R-1 design pressure:** "Maximum allowable working pressure 75 psig" is entered as `design_pressure_kpa` = 517.1 with provenance `"assumed"` (Bhargavi's review). MAWP and design pressure are not strictly the same quantity. The sentence is a note on R-1.
- **Objects the package names without an ID** were given new IDs: `V-K-INITIATOR` ("initiator solution vessel"), `P-K-INITIATOR` and `P-K-MONOMER` (each feed is "by pump"), `SOLVENT-STORAGE`, `SILICA-ADSORPTION`, `STRIP-DRUM-STATION`, `UT-K-CW`, `UT-K-STEAM`.
- **Manual valve:** `HV-STEAM-JACKET` (`kind: manual`) comes from "Steam to R-1 jacket, manually opened and closed by the operator", and those words are its note. It has no normal or fail position. The jacket cooling line `L-CW-JACKET` has no valve: "started manually by the operator" does not name one (review, 2026-10-28).
- **No R-1 → E-1 vapour line.** No package sentence puts R-1's vapour into E-1. "Process vapour in the tubes" says only what is in the tubes, so the line drawn in the first draft was deleted (review, 2026-10-28). R-1 and E-1 are joined only by `L-E1-CONDENSATE`.
- **Sight glass:** entered as instrument `SIGHT-GLASS-E1` (`kind: sensor`, measures `flow`, on `L-E1-CONDENSATE`, no `system`), because it is the only means of observing reflux. It is also the component of safeguard `SG-K-REFLUX-SIGHT-GLASS`.
- **E-1 vent** is a line to `LOC-K-ATMOSPHERE`, not a relief device: the package calls it a vent pipe, not relief.
- **No control loop** is created. "Temperature set point for steam heating set from the batch sheet" names no sensor or controller, and steam is "manually opened and closed". It is held as safeguard `SG-K-TEMP-SETPOINT`.
- **Monomer feed** starts at `LOC-K-UNSTATED`: the package says the monomer is "kept in drums/storage on site" but names no source vessel. No monomer storage object was created.
- **The batch sheet** is one procedure, `BATCH-SHEET-K-7`, with `kind: other`. It covers charging, reaction and finishing, so no single enum value fits. Its six steps are the package's numbered steps, verbatim.
- **"Planned work (this batch)"** is one planned-work item, `W-K-1` (`type: other`, on R-1), holding the six numbered statements as notes.
- **Initiator:** only the initiator solution is a chemical. The neat initiator is mentioned ("made up on site from initiator") but not described.
- **PSV-1:** `kind: prv` (from "relief valve"). Its discharge and inlet valves are not stated.

### 4. Remaining warnings

These are expected from a self-check only. They will be replaced with the `heldout_verify.py` output.

- No `epa_groups` on INITIATOR-SOLUTION, PRODUCT-K-7 or SILICA (only CAMEO 99 or 98 was ticked).
- Lines without contents: L-STEAM-JACKET, L-CW-JACKET, L-CW-E1, L-E1-CONDENSATE, L-E1-VENT.
- Missing design limits: E-1, V-K-INITIATOR, SOLVENT-STORAGE, R-1-MW, and R-1 temperature.
- Missing fail position: HV-STEAM-JACKET.
- PSV-1 has no set pressure (not recorded, stated).
- Equipment with no `location_id`: everything except R-1.

---

## case_l — Plant L: liquid chlorine repackaging and distribution facility

Source: `cases/case_l_chlorine-repack.md`.

### 1. Proposed assumptions

Reactivity groups and obvious physical forms only (assumption rule).

- [x] `CHLORINE.epa_groups` = [104] (oxidizing agents, strong)
- [x] `CHLORINE.cameo_groups` = [44] (`cameo_groups.csv`: `44,"Oxidizing Agents, Strong"`)
- [x] `SODIUM-HYDROXIDE.epa_groups` = [10, 106] (caustic, aqueous solution)
- [x] `SODIUM-HYDROXIDE.cameo_groups` = [10, 100]
- [x] `SODIUM-HYDROXIDE.physical_form` = liquid ("solution")
- [x] `SODIUM-HYPOCHLORITE.epa_groups` = [104, 106] (hypochlorite oxidizer, aqueous)
- [x] `SODIUM-HYPOCHLORITE.cameo_groups` = [44, 100] (`44,"Oxidizing Agents, Strong"`; `100,Water and Aqueous Solutions`)
- [x] `SODIUM-HYPOCHLORITE.physical_form` = liquid ("bleach", bulk tank)
- [x] `WASTEWATER.epa_groups` = [106]
- [x] `WASTEWATER.cameo_groups` = [100]
- [x] `WASTEWATER.physical_form` = liquid
- [x] `AIR.cameo_groups` = [49] (oxidizing agents, weak; as dev case E)
- [x] `AIR.physical_form` = gas
- [x] `AMMONIA-SOLUTION.epa_groups` = [10, 106] (aqueous base)
- [x] `AMMONIA-SOLUTION.cameo_groups` = [61, 100] (`61,"Bases, Weak"`; `100,Water and Aqueous Solutions`; corrected from [10, 100] once `cameo_groups.csv` could be read)
- [x] `AMMONIA-SOLUTION.physical_form` = liquid ("solution")

Why: the reactivity lookup and the chemical-pair questions need groups. Chlorine with ammonia solution (the start-up leak test) and chlorine with the bleach-unit chemicals are pairs in this package.

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- Tank-car quantities: "DOT load limit 180,000 lb" and "Contents at the start of the current shift: about 80,000 lb (by production records)". The schema has no mass field, and `level` is % of range. Notes on `TC-1`.
- Excess flow valve closing point: "closes above 15,000 lb/hr". The EFVs are on no line, so this flow has no operating row. Notes on `EFV-A`, `EFV-C` and `SG-L-EFV`.
- Hose rating: "Maximum operating pressure about 175 psig during unloading". Lines have no pressure field, and a maximum operating pressure is neither a `normal` nor a design value. Note on each hose.
- Hose specification and history: liner, braid and guard materials; "Specified service life 24 months from fabrication"; the most recent order, with its installation dates and documents; "Hoses are identified by paper tags only". The schema has no materials, age or procurement fields. Notes on each hose and on the station locations.
- ESD valve details: "Monel balls", "about 5 ft-lb torque", "position indicators on top", "All run from one central system". No logic solver was created, because `system` (bpcs or sis) is not stated. Notes on ESD-1 … ESD-5.
- Piping condition: "carbon steel, replaced 4 years ago; wall thickness never measured, never inspected internally; inspection interval 5 years". Note on `PLANT-LIQUID-HEADER`.
- Chlorine dryness: "under 50 ppm water". The schema has no composition field. Note on `CHLORINE`.
- Detector set points: "at 5 ppm …; at 10 ppm automatic ESD activation". `operating` holds only pressure, temperature, level and flow. Safeguard description and instrument note.
- "used at shutdown" (residual chlorine line, vacuum connection): `no_flow` has no shutdown-only value, so both lines have `no_flow` = [] and these words as their note.
- People, shift, offsite response, emergency plan and the 3.5-year-old incident are plant notes or procedure text.
- "about 100 ft" and "about 500 ft" are entered as 30.48 m and 152.4 m, and "about 11 ft" as 3.35 m, each with its words in a note. "less than 0.5 mile" and "Within 1 mile" are not single values, so those distances are left empty.

### 3. Modelling choices to confirm

- **Station-3 hoses (Bhargavi's decision, 2026-10-28):** H-3A, H-3B and H-3C are lines with those exact IDs, `is_hose: true`, each from `LOC-L-STATION-3` to `LOC-L-UNSTATED`. No hose is connected to a valve, and no hose has contents. Each of the three is one of the station-3 hoses, and the package does not say which route each one serves. That sentence is kept here, not in the plant file, because notes must be the package's exact words. Each hose instead carries the package's hose sentence ("H-3A, H-3B, H-3C transfer hoses at station 3; …"). The three route descriptions ("liquid hose from valve A", "the pad-air hose", "the liquid hose from valve C") and the three route lines are notes on `LOC-L-STATION-3`.
- **Consequence:** the file has no line from TC-1 to the plant liquid header and none from AC-1 to the car, so TC-1 joins the rest of the plant only through its location. ESD-1, ESD-2 and ESD-3 and car valves A, C and D are on no line (`on_line_id` empty).
- **Station-1 hoses** H-1A, H-1B and H-1C are modelled the same way, from `LOC-L-STATION-1`, because the package gives their IDs and the third new hose went to station 1. The three station-2 hoses and the ESD valves at stations 1 and 2 have no IDs and are not modelled.
- **Car valves** keep the package's IDs exactly: `A`, `B`, `C`, `D` (all valid IDs), `kind: manual` ("manually operated angle valves"). A, C and D are `normal_position: open` from "normally open during production and standby". B has no position ("valve B is not used"). No fail positions are given. All four valves are created because the package names all four.
- **ESD-1 … ESD-5:** `kind: block` (on/off ball valves; `control` would imply modulating). `fail_position: closed` comes from "spring-return … solenoid vents air so the spring closes the valve". `normal_position: open` comes from the route lines and standby step 3. ESD-4 and ESD-5 are on `L-HEADER-FILL` (header → fill stations) in that order, from "plant liquid header → ESD-4/5 → fill stations". The package does not say whether they are in series or parallel.
- **Excess flow valves** `EFV-A` and `EFV-C` (one "under each liquid valve") are `kind: block`. The valve enum has no excess-flow value, and `check` would imply reverse-flow protection.
- **Tank-car relief:** `PRD-TC-1`, `kind: prv` ("spring-loaded pressure relief device"). Its set pressure and discharge are not stated. It is not also entered as a safeguard.
- **Equipment types:** TC-1 → `tank`; plant liquid header, unused piping assemblies, fill stations, cleaning area, truck loading and bleach unit → `other`; 150-lb cylinders and 1-ton containers → `vessel` (one object each; not counted); AC-1 → `compressor`; its dryer → `dryer` (`AC-1-DRYER`); bulk caustic, bleach and wastewater tanks → `tank`.
- **Instruments:** the moisture analyzer is `kind: analyser` on `AC-1-DRYER`. The station-3 chlorine detector is `kind: analyser`, with no `on_id` (it is an area detector, and `on_id` takes equipment or lines only). The other area detectors are not counted, so they appear only in the safeguard description.
- **Air:** `AIR` is a chemical ("pad air", "instrument/plant air"). `UT-L-INSTRUMENT-AIR` is the instrument-air utility in the compressor room. The only air line drawn is `L-PLANT-AIR-SANDBLAST` (AC-1 → cleaning area), from "uses sandblasting equipment on plant air".
- **Ammonia solution** is a chemical, because the start-up step sprays it at possible chlorine leak points.
- **Process piping:** the residual chlorine line and the vacuum connection start at `PLANT-LIQUID-HEADER`, the only process piping object. The package says "from process piping". The vacuum source is not stated.
- **AC-1 operating pressure:** `normal` = 1206.6 kPa gauge, from "Supplies pad air to the tank car at about 175 psig".
- **Procedures:** the seven numbered procedures are seven procedure objects. Kinds: start-up → `start_up`; shutdown → `shutdown`; emergency response → `emergency`; hose receipt → `maintenance`; production, standby and the ESD daily test → `other`. Start-up and shutdown are split into steps at their semicolons, and every step is verbatim.
- **Locations:** occupied is set only where the package counts people (mobile home park, businesses). `offsite` is left empty everywhere, consistent with case K.

### 4. Remaining warnings

These are expected from a self-check only (no schema errors). They will be replaced with the `heldout_verify.py` output.

- All proposed groups and forms are written (section 1).
- Lines without contents: H-3A, H-3B, H-3C, H-1A, H-1B, H-1C, L-VACUUM.
- Missing design limits: every equipment item.
- Missing fail position: A, B, C, D, EFV-A, EFV-C.
- Valves on no line: A, B, C, D, EFV-A, EFV-C, ESD-1, ESD-2, ESD-3.
- PRD-TC-1 has no set pressure or discharge.

---

## case_m — Plant M: refinery light-ends (saturated gas) fractionation section

Source: `cases/case_m_gas-plant.md`.

### 1. Proposed assumptions

Reactivity groups and obvious physical forms only. Each line quotes the row it uses from `reference/reactive_groups.csv` (EPA) or `reference/cameo_groups.csv` (CAMEO).

- [x] `LIGHT-HYDROCARBONS.epa_groups` = [29] (EPA `29,"Hydrocarbons, Aliphatic, Saturated"`: methane, ethane, propane, butane)
- [x] `LIGHT-HYDROCARBONS.cameo_groups` = [29] (CAMEO `29,"Hydrocarbons, Aliphatic Saturated"`)
- [x] `H2S.epa_groups` = [33] (EPA `33,"Sulfides, Inorganic"`)
- [x] `H2S.cameo_groups` = [33] (CAMEO `33,"Sulfides, Inorganic"`)
- [x] `H2S.physical_form` = gas
- [x] `SOUR-WATER.epa_groups` = [106] (EPA `106,Water and Mixtures Containing Water`)
- [x] `SOUR-WATER.cameo_groups` = [100] (CAMEO `100,Water and Aqueous Solutions`)
- [x] `SOUR-WATER.physical_form` = liquid
- [x] `WASH-WATER.epa_groups` = [106] (EPA `106,Water and Mixtures Containing Water`)
- [x] `WASH-WATER.cameo_groups` = [100] (CAMEO `100,Water and Aqueous Solutions`)
- [x] `WASH-WATER.physical_form` = liquid
- [x] `COKER-DRILL-WATER.epa_groups` = [106] (EPA `106,Water and Mixtures Containing Water`)
- [x] `COKER-DRILL-WATER.cameo_groups` = [100, 99] (CAMEO `100,Water and Aqueous Solutions`; `99,Insufficient Information for Classification`, since the contaminants are not stated)
- [x] `COKER-DRILL-WATER.physical_form` = liquid
- [x] `CRUDE-OIL.epa_groups` = [29] (EPA `29,"Hydrocarbons, Aliphatic, Saturated"`; as dev case E heavy gas oil)
- [x] `CRUDE-OIL.cameo_groups` = [29, 16] (CAMEO `29,"Hydrocarbons, Aliphatic Saturated"`; `16,"Hydrocarbons, Aromatic"`)
- [x] `CRUDE-OIL.physical_form` = liquid
- [x] `GASOLINE.epa_groups` = [29] (EPA `29,"Hydrocarbons, Aliphatic, Saturated"`; as dev case E naphtha)
- [x] `GASOLINE.cameo_groups` = [29, 16] (CAMEO `29,"Hydrocarbons, Aliphatic Saturated"`; `16,"Hydrocarbons, Aromatic"`)
- [x] `GASOLINE.physical_form` = liquid
- [x] `PETROLEUM-COKE.epa_groups` = [101] (EPA `101,"Combustible and Flammable Materials, Miscellaneous"`; as dev case E coke)
- [x] `PETROLEUM-COKE.cameo_groups` = [99] (CAMEO `99,Insufficient Information for Classification`; as dev case E coke)
- [x] `PETROLEUM-COKE.physical_form` = solid
- [x] `HYDROGEN.epa_groups` = [101] (EPA `101,"Combustible and Flammable Materials, Miscellaneous"`)
- ~~`HYDROGEN.cameo_groups` = [45]~~ Declined by Bhargavi (2026-10-28): NOAA's group 45 page does not list hydrogen. HYDROGEN has no CAMEO group.
- [x] `HYDROGEN.physical_form` = gas

Not proposed: `LIGHT-HYDROCARBONS.physical_form`. The package has it as gas in L-OVHD ("high-pressure gas") and as liquid at WI-1 ("into liquid"), so no single form is obvious.

Why: the reactivity lookup and the chemical-pair questions need groups. Wash water with H2S-bearing hydrocarbons is the key pair here.

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- L-OVHD details: "carbon steel, original wall thickness about 7–8 mm" and "about 90% ethane/propane/butane with hydrogen sulphide". The schema has no material, wall-thickness or composition field. `size_mm` = 152.4 comes from "6 in nominal". Notes on `L-OVHD`.
- WI-2 geometry and history: "existing 1-inch vent connection on L-OVHD, 670 mm upstream of a 90° bend, about 9 m above ground", "No injection quill or dispersion device", the orifice change and MOC history. Injection points have no geometry or history fields. Note on `WI-2`.
- Operating pressures and temperatures: none are stated as numbers ("high-pressure gas"), so there are no `operating` rows.
- Inspection and integrity: WSE, database, backlog, RBI, the technical bulletin and the corrosion engineer's time. These are plant notes; the L-OVHD items are also notes on `L-OVHD`.
- Corrosion probes: they measure corrosion rate, which is not a `HazopParameter`, so `measures` is empty. Notes on `CP-D1-OUTLET` and `CP-E1A-INLET`.
- E-1A/B are "water-cooled", but no cooling-water line or utility is described, so no utility was created. Note on each condenser.
- Planned work: "None in this section." No planned-work object; people on site and the 15:00 handover are a plant note.
- Distances "about 0.5 km" and "about 1.5 km" are entered as 500 m and 1500 m, with the words in notes. The package does not say what they are measured from. "within 400 m" is not a single value, so it is left empty.

### 3. Modelling choices to confirm

- **WI-1 and WI-2 (Bhargavi's decision, 2026-10-28):** equipment `type: other` with the exact IDs. WI-1 is a component of `L-FEED` and WI-2 a component of `L-OVHD`, each line carrying `injection_points` [{WASH-WATER at WI-x}]. No wash-water supply line is drawn (source not stated).
- **E-1A and E-1B (Bhargavi's decision):** `L-OVHD` runs C-1 → `LOC-M-UNSTATED`, with the note "runs from the top of C-1 to E-1A/B". The fuel-gas line `L-C1-VAPOUR-FUEL-GAS` runs `LOC-M-UNSTATED` → `LOC-M-FUEL-GAS`, with the note "from E-1A/B to fuel gas system". E-1A and E-1B have notes but no lines, so neither is favoured.
- **Implied lines (Bhargavi's decision):** `L-C1-C2` and `L-C2-C3` come from "three columns in series"; the stream is not stated, so they have no contents. `L-D1-SOUR-WATER` and `L-D2-SOUR-WATER` go to `LOC-M-UNSTATED`, from "Sour water (from D-1 and D-2 draws)". No condenser → D-2 or D-2 → C-1 reflux line is drawn.
- **Stated lines:** `L-FEED` (`LOC-M-UNSTATED` → D-1; its upstream end is not stated); `L-D1-C1` ("D-1 feeds C-1"); `L-CRYO-FCC` (`LOC-M-FCC` → `CRYO-UNIT`; the direction of flow is not stated); `L-GASOLINE-RUNDOWN` (both ends `LOC-M-UNSTATED`).
- **Plural valves:** "slam-shut valves" and "manual isolation valves" are not counted, so each is one object (`SLAM-SHUT-VALVES`, `kind: block`; `MANUAL-ISOLATION-VALVES`, `kind: manual`), both on `L-CRYO-FCC`. The gasoline rundown "manual valve" is `HV-GASOLINE-RUNDOWN`. No positions are stated.
- **Control valves** ("operable from the central control room") are not counted or located, so they appear only as the safeguard `SG-M-CONTROL-VALVES`.
- **Contents:** section equipment and lines hold `LIGHT-HYDROCARBONS` and `H2S`, from "in the fractionation section" and L-OVHD's stated gas. D-1 and D-2 also hold `SOUR-WATER` ("from D-1 and D-2 draws"). H2S is its own chemical so that its reactivity is looked up separately.
- **Equipment types:** drums D-1 and D-2 → `vessel`; C-1, C-2, C-3 → `column`; E-1A and E-1B → `heat_exchanger`; WI-1, WI-2, cryogenic unit, blowdown unit and aromatics unit → `other`; hydrogen compressor → `compressor`; coker drill-water tank → `tank`.
- **Locations:** only C-1, C-2 and C-3 have `location_id` (`LOC-M-SECTION`), from "the saturated gas fractionation section … in three columns in series". The FCC is a location, not equipment (the package lists no FCC equipment). The control room is `indoor: true` ("Windowless central control room"). Villages, town and "Occupied buildings within 400 m" are `occupied: true`. `offsite` is left empty, as in K and L.
- **Site-wide chemicals:** crude oil, petroleum coke, gasoline, hydrogen and coker drill water come from the chemicals list, the gasoline rundown line, the hydrogen compressor and the drill-water tank. "intermediates and products" is too general to be a chemical.
- **Procedures:** the four numbered items are four procedure objects. The operating manual is `start_up` ("commissioned at start-up"); the others are `other`.

### 4. Remaining warnings

These are expected from a self-check only (no schema errors). They will be replaced with the `heldout_verify.py` output.

- HYDROGEN has no `cameo_groups` (declined).
- Lines without contents: L-C1-C2, L-C2-C3, L-CRYO-FCC.
- Missing design limits: every equipment item.
- Missing fail position: SLAM-SHUT-VALVES, MANUAL-ISOLATION-VALVES, HV-GASOLINE-RUNDOWN.
- No relief devices: the package names none.
- E-1A and E-1B are on no line.

---

## case_n — Plant N: hydrogenation unit of a styrene monomer / propylene oxide plant

Source: `cases/case_n_hydrogenation.md`.

### 1. Proposed assumptions

Reactivity groups and obvious physical forms only, with the row quoted from `reactive_groups.csv` (EPA) or `cameo_groups.csv` (CAMEO). Ethylbenzene, hydrogen and nitrogen have their physical form stated in the package, so those forms are already in the file.

- [x] `ETHYLBENZENE.epa_groups` = [16] (EPA `16,"Hydrocarbons, Aromatic"`)
- [x] `ETHYLBENZENE.cameo_groups` = [16] (CAMEO `16,"Hydrocarbons, Aromatic"`)
- [x] `HYDROGEN.epa_groups` = [101] (EPA `101,"Combustible and Flammable Materials, Miscellaneous"`; as ticked in case M. No CAMEO group, per your case M ruling)
- [x] `NITROGEN.cameo_groups` = [98] (CAMEO `98,Not Chemically Reactive`)
- [x] `MPK.epa_groups` = [19] (EPA `19,Ketones`: "methylphenyl ketone")
- [x] `MPK.cameo_groups` = [19] (CAMEO `19,Ketones`)
- [x] `MPC.epa_groups` = [4] (EPA `4,Alcohols and Glycols`: methylphenylcarbinol is an alcohol)
- [x] `MPC.cameo_groups` = [4] (CAMEO `4,Alcohols and Polyols`)
- [x] `PROPYLENE-OXIDE.epa_groups` = [34] (EPA `34,Epoxides`)
- [x] `PROPYLENE-OXIDE.cameo_groups` = [34] (CAMEO `34,Epoxides`)
- [x] `STYRENE.epa_groups` = [16, 103] (EPA `16,"Hydrocarbons, Aromatic"`; `103,Polymerizable Compounds`)
- [x] `STYRENE.cameo_groups` = [16, 76] (CAMEO `16,"Hydrocarbons, Aromatic"`; `76,Polymerizable Compounds`)
- [x] `PROPYLENE.epa_groups` = [28] (EPA `28,"Hydrocarbons, Aliphatic, Unsaturated"`)
- [x] `PROPYLENE.cameo_groups` = [28] (CAMEO `28,"Hydrocarbons, Aliphatic Unsaturated"`)
- [x] `PROPYLENE.physical_form` = gas
- [x] `ETHYLENE.epa_groups` = [28] (EPA `28,"Hydrocarbons, Aliphatic, Unsaturated"`)
- [x] `ETHYLENE.cameo_groups` = [28] (CAMEO `28,"Hydrocarbons, Aliphatic Unsaturated"`)
- [x] `ETHYLENE.physical_form` = gas
- [x] `OXYGEN.epa_groups` = [104] (EPA `104,"Oxidizing Agents, Strong"`)
- [x] `OXYGEN.cameo_groups` = [44] (CAMEO `44,"Oxidizing Agents, Strong"`. Ticked by Bhargavi, 2026-10-28)
- [x] `OXYGEN.physical_form` = gas
- [x] `CATALYST-B.epa_groups` = [24, 104] (EPA `24,"Metals and Metal Compounds, Toxic"`: chromium and barium compounds; `104,"Oxidizing Agents, Strong"`: hexavalent chromium "up to 5 wt%" as barium chromate. Ticked by Bhargavi, 2026-10-28: via its stated hexavalent chromium content (NOAA group 44 lists chromates and dichromates))
- [x] `CATALYST-B.cameo_groups` = [44] (CAMEO `44,"Oxidizing Agents, Strong"`, for the chromate. Ticked by Bhargavi, 2026-10-28: via its stated hexavalent chromium content (NOAA group 44 lists chromates and dichromates))
- [x] `CATALYST-B.physical_form` = solid ("cylindrical pellets")
- [x] `CATALYST-A.epa_groups` = [24] (EPA `24,"Metals and Metal Compounds, Toxic"`. The package gives only its "hexavalent chromium content 0.1–0.2 wt%", so 104 is not proposed)
- [x] `CATALYST-A.cameo_groups` = [99] (CAMEO `99,Insufficient Information for Classification`)

Not proposed: physical forms for MPK, MPC, propylene oxide and styrene. The package calls them "plant streams" without a phase.

Why: the reactivity lookup and the chemical-pair questions need groups. Ethylbenzene with the chromate catalyst is the pair the design basis treats as inert ("ethylbenzene is treated as inert").

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- Bed pressure difference "20–50 mbar": `operating` pressure is kPa gauge, and a differential pressure is neither gauge nor absolute. Note on R-1 and R-2.
- Gas discharge pressure alarm "12 bar; gauge/absolute not stated": it can't be converted to kPa gauge without knowing which, so there is no `operating` row. Safeguard description.
- Heating rates: design "30 °C/h" and planned "50 °C/h". The schema has no rate field. Notes on `PROC-N-STARTUP` and `W-N-2`.
- Nitrogen flows: design "475 kg/h" and planned "about 240 kg/h". The package does not say whether these are per reactor or in total, so neither is entered as a line flow. Notes on the nitrogen lines and `W-N-2`.
- Catalyst chromium content (Catalyst A "0.1–0.2 wt%", Catalyst B "up to 5 wt%") and the manufacturer's process change. The schema has no composition field. Notes on the catalysts.
- "Pit stop" dates: "started 9 days ago" and "This evening" have no calendar dates, so `W-N-1` and `W-N-2` have no `start` or `end`.
- Organisation, design basis, safety report and sister-plant history are plant, procedure or planned-work notes.

### 3. Modelling choices to confirm

- **Gas discharge (Bhargavi's decision, 2026-10-28):** shared header `GAS-DISCHARGE-HEADER` (`type: other`; dev convention A2). `L-V1-GAS` and `L-V2-GAS` run into it, and `L-GAS-FLARE` runs from it to `LOC-N-FLARE` carrying `PV-F` (`kind: control`). PV-F's normal and fail positions are not stated; its high-high closure is the safeguard `SG-N-SEP-LEVEL`.
- **E-1 (Bhargavi's decision):** equipment `heat_exchanger` ("gas condensing unit") with its notes and no line.
- **Ethylbenzene circulation** follows the stated loop "P-1 → H-1 → distribution plates of R-1 and R-2 → V-1 / V-2 → P-1": P-1 → H-1; H-1 → R-1 and H-1 → R-2; R-1 → V-1 and R-2 → V-2 ("V-1 … for R-1; V-2 for R-2"); V-1 → P-1 and V-2 → P-1. The design-basis "about 88 t/h to R-1, about 22 t/h to R-2" is `design_flow_kg_h` 88000 and 22000 on the H-1 → R-x lines, with the words in notes.
- **Nitrogen and hydrogen supplies** are utilities: `UT-N-NITROGEN` (`nitrogen`) and `UT-N-HYDROGEN` (`other`, as the utility enum has no hydrogen), each with a line to R-1 and one to R-2. The package names no hydrogen valve; the "leaking hydrogen valve" is in the sister plant, so it stays a plant note.
- **Separator levels:** `operating` rows on V-1 and V-2 hold the four stated settings (% of range). No level instruments or level control loop are created, because none is named ("Separator level control is in manual mode" names no controller).
- **Relief:** `PRD-V-1` and `PRD-V-2` from "Pressure relief devices on both separators". `kind` is left empty because the package says "devices", not valves or disks. Set pressures and discharge are not stated.
- **Contents:** R-1 and R-2 hold ethylbenzene, hydrogen, nitrogen, Catalyst B, MPK and MPC, from the unit description and the distribution-plate sentence. V-1, V-2, H-1, P-1 and the circulation lines hold ethylbenzene. The gas lines have no contents (gas composition not stated).
- **Equipment types:** R-1, R-2 and the plant N1 reactor → `reactor`; V-1, V-2 → `vessel`; H-1 ("heating/cooling installation") and E-1 → `heat_exchanger`; P-1 → `pump`; gas discharge header, styrene monomer section and cracker → `other`. H-1 has no `heat_sources`, because its medium is not stated.
- **Locations:** no equipment has `location_id`; the package doesn't say where U-H sits. "Contractors working in the adjacent unit" and "populated areas across the water" are `occupied: true`. The control room's occupancy is not stated.
- **Chemicals:** oxygen is a chemical, from start-up step 1 ("Release oxygen"). The cracker feeds (gasoil, naphtha, LPG) and ethylbenzene hydroperoxide are only in notes, as they belong to other units.
- **Procedure:** the job analysis is one `start_up` procedure with its five numbered steps, verbatim. The planned work is two items: the catalyst change `W-N-1` and this evening's start-up `W-N-2`.

### 4. Remaining warnings

These are expected from a self-check only (no schema errors). They will be replaced with the `heldout_verify.py` output.

- HYDROGEN has no `cameo_groups` (case M ruling); physical forms not stated for MPK, MPC, PROPYLENE-OXIDE, STYRENE.
- Lines without contents: L-V1-GAS, L-V2-GAS, L-GAS-FLARE.
- Missing design limits: every equipment item except R-1 and R-2 temperature (no design pressure anywhere).
- Missing fail position: PV-F.
- PRD-V-1 and PRD-V-2 have no kind, set pressure or discharge.
- E-1 is on no line.

---

## case_p — Plant P: mononitrotoluene distillation train (aniline / nitrotoluenes site)

Source: `cases/case_p_nitro-distillation.md`.

### 1. Proposed assumptions

Reactivity groups and obvious physical forms only, with the row quoted from `reactive_groups.csv` (EPA) or `cameo_groups.csv` (CAMEO). MNT's form ("liquid") is stated in the package, so it is already in the file.

- [x] `MNT.epa_groups` = [27] (EPA `27,"Nitro Compounds, Organic"`)
- [x] `MNT.cameo_groups` = [27] (CAMEO `27,"Nitro, Nitroso, Nitrate, and Nitrite Compounds, Organic"`)
- [x] `TOLUENE.epa_groups` = [16] (EPA `16,"Hydrocarbons, Aromatic"`)
- [x] `TOLUENE.cameo_groups` = [16] (CAMEO `16,"Hydrocarbons, Aromatic"`)
- [x] `TOLUENE.physical_form` = liquid
- [x] `NITRIC-ACID.epa_groups` = [2] (EPA `2,"Acids, Mineral, Oxidizing"`)
- [x] `NITRIC-ACID.cameo_groups` = [2] (CAMEO `2,"Acids, Strong Oxidizing"`)
- [x] `NITRIC-ACID.physical_form` = liquid
- [x] `SULFURIC-ACID.epa_groups` = [2] (EPA `2,"Acids, Mineral, Oxidizing"`. Source: NOAA CAMEO datasheet "Sulfuric acid" (cameochemicals.noaa.gov/chemical/5193, "Acids, Strong Oxidizing"); ticked by Bhargavi, 2026-10-28)
- [x] `SULFURIC-ACID.cameo_groups` = [2] (CAMEO `2,"Acids, Strong Oxidizing"`. Source: NOAA CAMEO datasheet "Sulfuric acid" (cameochemicals.noaa.gov/chemical/5193, "Acids, Strong Oxidizing"); ticked by Bhargavi, 2026-10-28)
- [x] `SULFURIC-ACID.physical_form` = liquid
- [x] `OLEUM.epa_groups` = [2, 107] (EPA `2,"Acids, Mineral, Oxidizing"`; `107,Water Reactive Substances`. Source: NOAA CAMEO datasheet "Sulfuric acid, fuming" (cameochemicals.noaa.gov/chemical/4115, "Acids, Strong Oxidizing"; water-reactive, ERG 137); ticked by Bhargavi, 2026-10-28)
- [x] `OLEUM.cameo_groups` = [2] (CAMEO `2,"Acids, Strong Oxidizing"`; the CAMEO table has no water-reactive row. Source: NOAA CAMEO datasheet "Sulfuric acid, fuming" (cameochemicals.noaa.gov/chemical/4115, "Acids, Strong Oxidizing"; water-reactive, ERG 137); ticked by Bhargavi, 2026-10-28)
- [x] `OLEUM.physical_form` = liquid
- [x] `AMMONIA.epa_groups` = [10] (EPA `10,Caustics`)
- [x] `AMMONIA.cameo_groups` = [61] (CAMEO `61,"Bases, Weak"`; as ticked for ammonia solution in case L)
- [x] `ANILINE.epa_groups` = [7] (EPA `7,"Amines, Aliphatic and Aromatic"`)
- [x] `ANILINE.cameo_groups` = [68] (CAMEO `68,"Amines, Aromatic"`)
- [x] `ANILINE.physical_form` = liquid
- [x] `HYDROGEN.epa_groups` = [101] (EPA `101,"Combustible and Flammable Materials, Miscellaneous"`; as ticked in M and N. No CAMEO group, per the case M ruling)
- [x] `HYDROGEN.physical_form` = gas
- [x] `FORMALDEHYDE.epa_groups` = [5] (EPA `5,Aldehydes`)
- [x] `FORMALDEHYDE.cameo_groups` = [5] (CAMEO `5,Aldehydes`)
- [x] `CHLORINE.epa_groups` = [104] (EPA `104,"Oxidizing Agents, Strong"`; as ticked in case L)
- [x] `CHLORINE.cameo_groups` = [44] (CAMEO `44,"Oxidizing Agents, Strong"`; as ticked in case L)
- [x] `NITROGEN.cameo_groups` = [98] (CAMEO `98,Not Chemically Reactive`; as ticked in case N)
- [x] `NITROGEN.physical_form` = gas

Not proposed: physical forms for anhydrous ammonia, formaldehyde and chlorine. They are stored or supplied as liquefied gas, solution or cylinder contents, and the package does not say which.

Why: the reactivity lookup and the chemical-pair questions need groups. MNT (organic nitro) with heat is the central hazard, and the acids, ammonia and aniline sit on the same site.

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- C-1 temperatures: "bottoms about 350 °F, mid-bed about 300 °F, top about 140 °F (procedure values)". An `operating` row holds one `normal` per target and parameter, so three points can't be entered without choosing one. Note on C-1.
- C-1 operating pressure: "Normal operation under vacuum" (no number), and today "at or slightly above atmospheric pressure". No `operating` pressure row.
- C-1 size and inventory: "7 ft diameter, about 145 ft tall" and "about 1,200 gal of MNT". There is no diameter or height field, and holdup is not vessel volume, so `volume_m3` stays empty.
- MNT decomposition: "MNT may decompose explosively above 374 °F", "flash point above 100 °F" (not a single value) and "NFPA flammability 1, reactivity 1". The schema has no decomposition-temperature or NFPA field. Note on `MNT`.
- B-310 limits: "documented safe temperature 374 °F or below; operating limit below 370 °F" and the procedure limits ("do not exceed 395 °F for more than 1 h"). These are not alarm, trip or design values. Only the "high-temperature alarm at 400 °F" is entered, as `alarm_high` = 204.4 °C. Note on B-310.
- Current isolation state: the outlet block valves and FV-A/FV-B are closed today, but this is the current state, not the normal position, so `normal_position` stays empty on those valves. Notes on the valves and the plant.
- Today's status, DCS losses, turnaround and "Restart date … not yet set": there are no dates or planned-work items. Plant notes.
- Tank inventories ("more than 2 million lb", "500,000 lb") and "about 500 ft from C-1" for T-PMNT: there is no mass field, and no location object was created for the tank. Notes on the tanks.

### 3. Modelling choices to confirm

- **Steam stations (Bhargavi's decision, 2026-10-28):** `SS-A` and `SS-B` are lines with those exact IDs, UT-P-STEAM → E-1A and → E-1B, `size_mm` 76.2 ("3-inch"). Components are [inlet manual block, FV-x, outlet manual block]. The bypasses are parallel lines `L-SS-A-BYPASS` and `L-SS-B-BYPASS` carrying `SS-x-BYPASS`, with `no_flow: [normally_closed]` and `normal_position: closed` from "(normally closed)". The manual block valves are `kind: manual`; FV-A and FV-B are `kind: control`. The 300 psig supply is `operating` pressure `normal` = 2068.4 kPa gauge on SS-A and SS-B.
- **Reboilers (Bhargavi's decision):** no process lines between C-1 and E-1A/E-1B. C-1 has four steam `heat_sources`, one via each station line and each bypass line, each with that line's valves as isolating valves. E-1A and E-1B connect only to steam and their condensate returns (→ `LOC-P-UNSTATED`). No condensate valve is created: "block in the condensate return" names none.
- **Feed path (Bhargavi's decision):** `T-MNT-ATM` (`tank`) and `TOLUENE-STRIPPER` (`column`), with lines tank → stripper → C-1 holding MNT.
- **Overhead (Bhargavi's decision):** `STEAM-EDUCTORS` (`other`); `L-C1-OVHD` runs C-1 → eductors; `UT-P-NITROGEN` with `L-N2-C1` → C-1 for "a nitrogen tubing connection" (nitrogen injected "at the top"). PSV-1 is a relief device protecting C-1 (`kind: prv`, `set_pressure_kpa` 103.4 from "15 psig"); its discharge is not stated.
- **Bottoms and reflux** (pumps confirmed against the package sentence "Bottoms pump sends mainly para- and meta-MNT to column C-2; reflux pump returns mainly ortho-MNT from the collector tray through the reflux cooler.", 2026-10-28): `L-C1-BOTTOMS` C-1 → C-2 through `P-C1-BOTTOMS`; reflux `L-C1-E2` C-1 → E-2 through `P-C1-REFLUX`, and `L-E2-C1` E-2 → C-1, from "Bottoms pump sends … to column C-2; reflux pump returns … through the reflux cooler" and "reflux from collector tray via E-2 to C-1". The pump IDs are new.
- **C-1 design pressure:** "Nameplate design pressure 15 psig" → `design_pressure_kpa` 103.4.
- **Temperature indicators:** TI-B and TI-R are instruments (`sensor`, `temperature`, on C-1). `system: bpcs` comes from "shown on DCS operator screens". The other six indicators are unnamed, so they appear only in the safeguard description. No logic solver or control loops are created, because "DCS" and the FV-A/FV-B flow control name no controller.
- **Equipment types:** C-1, C-2, C-3, toluene stripper and B-310 ("still … in an existing column") → `column`; E-1A, E-1B, E-2 → `heat_exchanger`; T-MNT-ATM, T-PMNT, T-NH3 → `tank`; eductors, acid concentrator, No. 2 hydrogen unit and cooling tower → `other`. B-310 has `heat_sources` [hot oil], with no line. The central steam plant is the steam utility `UT-P-STEAM`, not a separate equipment item.
- **Not modelled as objects:** the nitration, separator and washing steps (process description only); the pipe rack over T-NH3 (note).
- **Locations:** the control room (`distance_m` 15.24 from "about 50 ft from C-1") and the administration building are `indoor: true`. Their occupancy is not stated, so `occupied` is empty. The ship channel `distance_m` 402.3 comes from "0.25 mile west", though the package doesn't say what it is measured from. "400–450 ft" is a range, so it is left empty. `offsite` is left empty, as in the earlier cases.
- **Procedures:** the C-1 operating procedure (`other`, one step) and the emergency shutdown procedure (`emergency`, its two steam-failure steps verbatim). Item 3 (no written procedure; LOTO not applied) is a plant note, not a procedure.

### 4. Remaining warnings

These are expected from a self-check only (no schema errors). They will be replaced with the `heldout_verify.py` output.

- HYDROGEN has no `cameo_groups` (case M ruling); physical forms not stated for AMMONIA, FORMALDEHYDE, CHLORINE.
- Lines without contents: SS-A, SS-B, L-SS-A-BYPASS, L-SS-B-BYPASS, L-E1A-CONDENSATE, L-E1B-CONDENSATE, L-C1-OVHD.
- Missing design limits: every equipment item except C-1's pressure.
- Missing fail position: all eight steam-station valves.
- PSV-1 has no discharge.
- No equipment has `location_id`.

---

## case_q — Plant Q: hydrogen recovery section of a polycrystalline silicon plant — exchanger removal and cleaning

Source: `cases/case_q_exchanger-opening.md`.

### 1. Proposed assumptions

Reactivity groups and obvious physical forms only, with the row quoted from `reactive_groups.csv` (EPA) or `cameo_groups.csv` (CAMEO).

- [ ] `TCS.epa_groups` = [107] (EPA `107,Water Reactive Substances`: "react with water")
- [ ] `TCS.cameo_groups` = [55] (CAMEO `55,Chlorosilanes`)
- [ ] `STC.epa_groups` = [107] (EPA `107,Water Reactive Substances`)
- [ ] `STC.cameo_groups` = [55] (CAMEO `55,Chlorosilanes`)
- [ ] `DCS.epa_groups` = [107] (EPA `107,Water Reactive Substances`)
- [ ] `DCS.cameo_groups` = [55] (CAMEO `55,Chlorosilanes`)
- [ ] `HYDROGEN.epa_groups` = [101] (EPA `101,"Combustible and Flammable Materials, Miscellaneous"`; as ticked in M, N and P. No CAMEO group, per the case M ruling)
- [ ] `HYDROGEN.physical_form` = gas
- [ ] `HCL.epa_groups` = [1] (EPA `1,"Acids, Mineral, Non-oxidizing"`)
- [ ] `HCL.cameo_groups` = [1] (CAMEO `1,"Acids, Strong Non-oxidizing"`)
- [ ] `HCL.physical_form` = gas
- [ ] `CHLOROSILANE-POLYMERS.epa_groups` = [107] (EPA `107,Water Reactive Substances`: the work standard hydrolyses them with humidified nitrogen, and "less HCl and H2 is released at opening")
- [ ] `CHLOROSILANE-POLYMERS.cameo_groups` = [55] (CAMEO `55,Chlorosilanes`. The polymers are "chains of two or more Si atoms" formed from SiCl2, so placing them in this group is my judgement; please check)
- [ ] `NAOH.epa_groups` = [10, 106] (EPA `10,Caustics`; `106,Water and Mixtures Containing Water`)
- [ ] `NAOH.cameo_groups` = [10, 100] (CAMEO `10,"Bases, Strong"`; `100,Water and Aqueous Solutions`)
- [ ] `NAOH.physical_form` = liquid ("solution")
- [ ] `MG-SILICON.epa_groups` = [22] (EPA `22,"Metals, Other Elemental & Alloys as Powders, Vapors, or Sponges"`: "metallurgical silicon powder (about 98% Si)". Silicon is a metalloid, so placing it here is my judgement; please check)
- [ ] `MG-SILICON.cameo_groups` = [22] (CAMEO `22,"Metals, Elemental and Powder, Active"`. Same caveat)
- [ ] `MG-SILICON.physical_form` = solid ("powder"; `dust` not proposed, as in case K)
- [ ] `NITROGEN.cameo_groups` = [98] (CAMEO `98,Not Chemically Reactive`; as ticked in N and P)
- [ ] `NITROGEN.physical_form` = gas
- [ ] `WATER.epa_groups` = [106] (EPA `106,Water and Mixtures Containing Water`)
- [ ] `WATER.cameo_groups` = [100] (CAMEO `100,Water and Aqueous Solutions`)
- [ ] `WATER.physical_form` = liquid

Not proposed: physical forms for TCS, STC and DCS ("liquids/vapours") and for the chlorosilane polymers ("solid/viscous deposits"). The package gives two forms for each.

Why: the reactivity lookup and the chemical-pair questions need groups. The pairs this procedure turns on are polymers with water (the hydrolysis step and the wash) and polymers with NaOH (the drainage-tank explosion and the scrubber on the exhaust).

### 2. Package facts the schema cannot hold

All of these are kept verbatim as notes:

- Pressures "about 0.1 MPa (gauge/absolute not stated)" (system) and "0.018 MPa (gauge/absolute not stated)" (nitrogen blow): they can't be converted to kPa gauge without knowing which, so there are no `operating` pressure rows. Plant note and procedure text.
- Nitrogen blow "20 Nm³/h": `_kg_h` fields need a mass flow, and converting normal cubic metres needs a gas density the package does not give. As dev case E did with bbl/d, it stays in notes.
- HX-A/B/C geometry, materials and weights (101 m², 293 tubes, SUS304/SUS316L, 4,800 / 6,300 kg, channel cover about 300 kg): the schema has no geometry, material or mass field. "Operating temperature and pressure not stated." Notes on the exchangers.
- Polymer inventory: "HX-B (now removed) is estimated to hold several hundred kg of deposits". There is no mass field. Note on HX-B.
- Hydrolysis dose and duration: "about 0.8 vol% H2O", "20 working days", "Total water introduced about 11 kg", and the missing end-point. These are procedure text and notes.
- Deposition rod surface "about 1,000 °C" is a surface temperature, not a vessel operating value, so it is a note only. The chlorination furnace's "about 300 °C" is entered as `operating` temperature `normal` = 300, with the words in notes.
- Timing ("Seven weeks ago", "About 07:30", "Afternoon") has no calendar dates, so the planned work has no `start` or `end`.
- People on the job, history and training gaps are planned-work and plant notes.

### 3. Modelling choices to confirm

- **Changeover valves (Bhargavi's decision, 2026-10-28):** seven valves with the exact IDs `A` … `G` (`kind: block`), each with the changeover sentence as a note, on no line. No position or mapping to a line is invented. The changeover procedure's steps therefore list no `valve_ids`.
- **HX-B lines (Bhargavi's decision):** the train is drawn only through HX-A and HX-C: demister → HX-A / HX-C → GG-1 → LT-1 → condensate tanks → hydrogen purification. HX-B is at `LOC-Q-TEMP-STORAGE` ("moved to the temporary storage area"). Cooling water is drawn to HX-A and HX-C only (supply from `UT-Q-CW`, returns to `LOC-Q-UNSTATED`), because HX-B's cooling water was "drained" and the exchanger "disconnected".
- **Temporary connections to HX-B (Bhargavi's decision):**
  - two dry-nitrogen hoses, `L-N2-HOSE-UPPER` and `L-N2-HOSE-LOWER` (`is_hose: true`), from "hoses to both channel covers";
  - humidified nitrogen through the new vessel `HUMIDIFIER` ("a closed vessel");
  - purge exhaust HX-B → `OFFGAS-WATER-TANK`, from "to the water tank and NaOH scrubber" (planned step 3 names only the scrubber; both sentences are notes);
  - high-pressure wash `HP-JET-WATER-TANK` → HX-B through `HP-JET-PUMP`.
- **Off-gas chain (Bhargavi's decision):** `OFFGAS-WATER-TANK` → `NAOH-SCRUBBER` → `LOC-Q-ATMOSPHERE`, from "purge gas bubbled through water in a tank, then an NaOH gas scrubber, then to atmosphere". The reactor off-gas → demister and condensate → distillation links are not drawn.
- **Contents:**
  - The train lines from the demister to the condensate tanks hold TCS, STC, H2 and HCl, from "reactor off-gas (unreacted TCS, H2, STC, HCl)".
  - The condensate tanks hold TCS and STC ("chlorosilanes condense").
  - Condensate → purification holds H2 and HCl ("HCl separated and recovered, H2 purified").
  - HX-A and HX-C also hold the polymers ("deposit on the tube inner walls of HX-A/B/C").
  - HX-B holds polymers, HCl and H2 ("HCl and H2 formed by hydrolysis") and nitrogen (filled "with dry nitrogen", step 1).
  - The off-gas tank → scrubber → atmosphere lines have no contents (purge gas composition after the water tank is not stated).
- **Equipment types:** HX-A/B/C, GG-1 and LT-1 → `heat_exchanger`; chlorination furnace and deposition reactors → `reactor`; distillation columns, crude column No. 2 and the DCS distillation unit → `column`; condensate tanks, off-gas water tank, drainage tank facility and jet-water tank → `tank`; humidifier → `vessel`; HP jet pump → `pump`; demister, H2 purification, DCS plant, NaOH scrubber, drainage pit, neutralisation and activated carbon unit → `other`. Plural items not counted (condensate tanks, distillation columns, deposition reactors) are one object each.
- **Locations:** `HR-6` keeps the package's unit ID, and the train equipment except HX-B is located there ("Hydrogen recovery train (unit HR-6)"). The washing area is `indoor: false` ("open area"), and the jet-water tank and pump are located there. The pipe rack, the two neighbouring companies and the temporary storage area are locations. The activated carbon unit has no `location_id` ("next to the west side of the washing area" is beside it, not in it).
- **Chemicals:** `TCS`, `STC` and `DCS` keep the package's abbreviations as IDs. `WATER` is a chemical (cooling water, humidifier, washing), as the water-chlorosilane pair is central. The neighbouring company that takes STC is a plant note; the package does not say which neighbour it is.
- **Procedures and work:**
  - The changeover sentence is split into four steps at its commas.
  - The pre-opening work standard (six completed steps) and today's opening sequence (five steps) are `maintenance` procedures, with every step verbatim.
  - Today's job is `W-Q-1` (`other`, washing area, HX-B and the temporary lines), with the people note.
  - The crane-truck lifts of both channel covers are `W-Q-2` (`lifting`). `lifts_per_year` is not stated.

### 4. Remaining warnings

These are expected from a self-check only (no schema errors). They will be replaced with the `heldout_verify.py` output.

- No `epa_groups` or `cameo_groups` on any chemical until ticked (section 1).
- Lines without contents: L-WATER-TANK-SCRUBBER, L-SCRUBBER-ATMOSPHERE.
- Missing design limits: every equipment item (no design pressure or temperature is stated).
- Missing fail position: A–G.
- Valves on no line: A–G.
- No relief devices (none named).

---
