# Dev-case conversion report (spec 0.7)

Five kill-test #4 packages in `cases/dev/source/` converted to plant files `cases/dev/case_d.json` … `case_h.json`. Rule (CLAUDE.md §5, spec 0.7): only `cases/dev/source/` was read, never `cases/dev/keys/`; facts are the package's own words; nothing is classified beyond what the package says. Every object and stated operating value has its package as provenance. Words the schema has no field for are kept verbatim in `notes` (a test checks every note is an exact substring of its package).

**How to review:** tick a proposed assumption (`- [x]`) to accept it; I then write that value into the plant file with `"assumed"` in `provenance` (a test checks every `"assumed"` entry is ticked here). Leave it unticked to keep the gap. The modelling choices in section 3 are not assumptions (no value was invented), but each one shapes the question list, so say if any should change.

**Conventions used in every case**

- A line end the package does not name goes to the case's `LOC-<case>-UNSTATED` location ("endpoint not stated in the package"), so no endpoint is guessed.
- Inches are converted to millimetres (2" = 50.8 mm) and bar g to kPa gauge (1 bar = 100 kPa). "About" and "~" values are entered as stated, with the words in a note.
- Safeguards the package lists are entered with their package words as `description` and no `layer_type`: none of them states enough for a LOPA layer, so code gives none of them credit (survey decision A5).
- Equipment `type` is the closest enum value to the package's name for it (table per case in section 3).
- No EPA or CAMEO group is stated in any package, so all chemicals have warning 3; groups are proposed in section 1 (survey decision C).

---

## case_d — Unit D: butadiene extraction unit

### 1. Proposed assumptions

- [x] `BUTANES.epa_groups` = [29] (hydrocarbons, aliphatic, saturated)
- [x] `BUTANES.cameo_groups` = [29]
- [x] `BUTENES.epa_groups` = [28] (hydrocarbons, aliphatic, unsaturated)
- [x] `BUTENES.cameo_groups` = [28]
- [x] `BUTADIENE.epa_groups` = [28, 103] (unsaturated aliphatic; polymerizable)
- [x] `BUTADIENE.cameo_groups` = [65, 76] (conjugated dienes; polymerizable compounds)
- [x] `ACETYLENES.epa_groups` = [28]
- [x] `ACETYLENES.cameo_groups` = [63] (alkynes with acetylenic hydrogen)
- [x] `WATER.epa_groups` = [106]
- [x] `WATER.cameo_groups` = [100]
- [x] `NMP.epa_groups` = [6] (amides)
- [x] `NMP.cameo_groups` = [6] (amides and imides)
- [x] `TBC.epa_groups` = [31] (phenols and cresols)
- [x] `TBC.cameo_groups` = [31]
- [x] `HEAVIES.cameo_groups` = [99] (insufficient information for classification)
- [x] `ANTIFOAM.cameo_groups` = [99] (composition not stated)

Why: the reactivity lookup and the chemical-pair questions need groups; without them every pair is "not listed".

### 2. Package facts the schema cannot hold

None left without a home: feed composition ("1,3-butadiene ~45%"), "ambient temperature", the TBC dose "50–100 ppm", "last used 14 months ago", "switched over a few times a year", "carbon steel, insulated", the 5-year UT checks and the strainer cleaning are kept as notes on their objects or the plant.

### 3. Modelling choices to confirm

- **Equipment types:** V-101, V-104 (drums) → `vessel`; C-101…C-104 → `column`; E-104, E-105, E-106 → `heat_exchanger`; P-104A/B → `pump`; TK-201, TK-202 (pressurised spheres) and the off-spec tank → `tank`; the flare header → `other`.
- **C-101/C-102 reboilers and condensers** are not separate objects (the package names none); each column has a steam heat source and the package words as a note.
- **`L-STARTUP-RECYCLE`** starts at P-104A: the package says "from the P-104 discharge" (shared by A and B). `no_flow` = [normally_closed, startup_only], both stated ("normally closed, used during start-ups").
- **P-104B spare piping:** `L-P104B-SUC` and `L-P104B-DIS` with closed block valves; `no_flow` = [normally_closed], from "suction and discharge block valves closed". Not marked `standby`, as the package says "installed spare".
- **TBC injection** is on V-104 as an equipment injection point; the package says "at the V-104 outlet", and no outlet line is named.
- **Rundown line** ends at `LOC-D-SPHERES` (both spheres); its start is not stated. The 1" sample connections are notes, not lines.
- **`L-FEED`** (olefins plant → V-101) is drawn from "Feed: crude C4 cut from an olefins plant" and "V-101 feed surge drum".
- **Relief devices:** one PRV to the flare on each column, each drum (V-101, V-104) and each pump discharge (P-104A, P-104B), from "Relief valves on all columns, drums and pump discharge to the flare". Set pressures and inlet valves are not stated.
- **Contents** of each item follow its stated duty (feed drum: the feed components; rerun column, reflux drum, rundown and spheres: 1,3-butadiene; solvent stripper: NMP).

### 4. Remaining warnings

<!-- warnings:case_d -->
Generated from `validate_plant`: 18 warnings, 0 errors.
- `line_without_contents` (4): L-OFFSPEC, L-P104B-DIS, L-P104B-SUC, L-STARTUP-RECYCLE
- `missing_design_limits` (12): C-101, C-102, C-103, C-104, E-104, E-105, E-106, TK-201, TK-202, TK-OFFSPEC, V-101, V-104
- `missing_fail_position` (2): BV-P104B-DIS, BV-P104B-SUC
<!-- /warnings:case_d -->

### 5. Known gaps (found in the first 5B dev run, 2026-10-16)

- **No line joins C-104 to its reflux drum V-104.** The package says "overhead condenser E-105, reflux drum V-104" for C-104, and V-104 is in the file, but no line connects it to C-104's section, so specialists answering C-104's questions cannot cite it (2 refusals in the run). Adding the overhead line would add a section and questions and change the case D counts in `expected_counts.json` (25 sections, 362 questions), so it is left as it is until after G2 (Bhargavi, 2026-10-16).
- **No controllers, so no control-loop causes.** The package says "Basic process control system; high/low level alarms on all drums; high-pressure alarms on columns" and names no controller, loop or instrument (no LIC, PIC, FIC or TIC). The conversion holds these as the safeguards `SG-D-BPCS`, `SG-D-LEVEL-ALARMS` and `SG-D-PRESSURE-ALARMS`; adding loops would invent them. Under R46, C01–C03 (control loop) and C13 (interlock) therefore have nothing to name on case D, so "loss of level control" and the like can only appear as outside-library causes. Nothing was dropped by the conversion; left as it is until after G2 (2026-10-16).

---

## case_e — Unit E: FCC unit, planned shutdown

### 1. Proposed assumptions

- [x] `HGO.epa_groups` = [29] (heavy gas oil: saturated hydrocarbons)
- [x] `HGO.cameo_groups` = [29, 16]
- [x] `CRACKED-VAPOURS.epa_groups` = [28, 29]
- [x] `CRACKED-VAPOURS.cameo_groups` = [28, 29]
- [x] `C1-C4-GASES.epa_groups` = [28, 29]
- [x] `C1-C4-GASES.cameo_groups` = [28, 29]
- [x] `NAPHTHA.epa_groups` = [29]
- [x] `NAPHTHA.cameo_groups` = [29, 16]
- [x] `TORCH-OIL.epa_groups` = [29]
- [x] `TORCH-OIL.cameo_groups` = [29]
- [x] `ASPHALT.epa_groups` = [101] (combustible and flammable materials, miscellaneous)
- [x] `ASPHALT.cameo_groups` = [29]
- [x] `HF.epa_groups` = [1, 15] (mineral acid, non-oxidizing; inorganic fluorides)
- [x] `HF.cameo_groups` = [1]
- [x] `COKE.epa_groups` = [101]
- [x] `COKE.cameo_groups` = [99]
- [x] `CATALYST.cameo_groups` = [99] (composition not stated)
- [x] `FLUE-GAS.cameo_groups` = [99] (composition not stated)
- [x] `AIR.cameo_groups` = [49] (oxidizing agents, weak)

### 2. Package facts the schema cannot hold

None left without a home. "~25,000 bbl/day" stays a note: converting it to `normal_flow_kg_h` would need a density the package does not give.

### 3. Modelling choices to confirm

- **Equipment types:** riser reactor → `reactor`; regenerator → `reactor` (it "burns coke off the spent catalyst"); main fractionator, absorber, stripper, debutaniser → `column`; main air blower and wet gas compressor → `compressor`; expander, CO boiler and spent catalyst hopper → `other`; asphalt tanks → `tank`.
- **Lines** are drawn only where the package states a flow: standpipes with their slide valves, air to the regenerator, vapours to the fractionator, the fractionator → wet gas compressor → gas plant chain, the flue gas route to the stack, and catalyst withdrawal to the hopper (shutdown step 3). The gas plant's internal order is not stated, so its three columns share `LOC-E-GAS-PLANT`.
- **Slide valves** are `control` valves ("Flow is controlled by…"); fail positions are not stated.
- **"Relief valves to the flare"** names no equipment, so no relief device is created (a relief device needs `protects_id`); it is a safeguard description instead. This means case E has no `relief:` questions.
- **HF** is a chemical of the case (from "An alkylation unit using hydrofluoric (HF) acid, 300 m away"), so it enters the chemical-pair lists; no equipment of this unit holds it.
- **Shutdown step equipment** links follow the step words (e.g. step 6 links the wet gas compressor and the three gas-plant columns, from "depressure the gas plant").

### 4. Remaining warnings

<!-- warnings:case_e -->
Generated from `validate_plant`: 10 warnings, 0 errors.
- `missing_design_limits` (8): ABSORBER, DEBUTANISER, MAIN-FRACTIONATOR, REGENERATOR, RISER, STRIPPER, TK-ASPHALT-1, TK-ASPHALT-2
- `missing_fail_position` (2): SV-REGEN, SV-SPENT
<!-- /warnings:case_e -->

---

## case_f — Area F: pulp mill evaporator and condensate area, two-week work window

### 1. Proposed assumptions

- [x] `WATER.epa_groups` = [106]
- [x] `WATER.cameo_groups` = [100]
- [x] `METHANOL.epa_groups` = [4] (alcohols and glycols)
- [x] `METHANOL.cameo_groups` = [4]
- [x] `TURPENTINE.epa_groups` = [28]
- [x] `TURPENTINE.cameo_groups` = [28]
- [x] `ORGANICS.cameo_groups` = [99] (composition not stated)
- [x] `BLACK-LIQUOR.epa_groups` = [10, 106] (caustic, aqueous)
- [x] `BLACK-LIQUOR.cameo_groups` = [10, 100]
- [x] `WEAK-BLACK-LIQUOR.epa_groups` = [10, 106] ("hot, caustic")
- [x] `WEAK-BLACK-LIQUOR.cameo_groups` = [10, 100]
- [x] `NAOH.epa_groups` = [10]
- [x] `NAOH.cameo_groups` = [10]
- [x] `NA2S.epa_groups` = [33] (sulfides, inorganic)
- [x] `NA2S.cameo_groups` = [33]

### 2. Package facts the schema cannot hold

None left without a home: "atmospheric, fixed cone roof", "an organic layer can float on top", "Levels vary with mill operation", "Tanks stay in service during the work" and the work-control and safeguard lines are notes or safeguard descriptions. The two-week window has no dates, so no job has `start` or `end`.

### 3. Modelling choices to confirm

- **Equipment types:** evaporators → `other` (no enum value for an evaporator); surface condenser → `heat_exchanger`; vacuum system → `other`; T-31, T-32, T-33 and the weak black liquor tank → `tank`; stripper feed pump → `pump`.
- **Shared headers** (survey decision A2): the common overflow line and the common vent header are equipment `type: other`, with one line from each tank to each header (from "Connected by a common overflow line and a common vent header"). The vent header discharges to `LOC-F-ATMOSPHERE` ("discharges to atmosphere above the roofline"). It is not entered as a relief device; the package does not call it one.
- **The 8" condensate line and the white liquor line** cross the area with neither end stated, so both ends are `LOC-F-UNSTATED`.
- **Planned work:** W-1 `hot_work` (it states "cutting, welding and grinding" and a hot work permit) on the condensate line and T-32 (`line_ids`, `equipment_ids`), located on the roof of T-32; W-2 `other` (seal replacement on the stripper feed pump); W-3 `lifting` over the white liquor line; W-4 `other` ("no hot work"). `lifts_per_year` for W-3 is not stated.
- **Evaporators** are one object: the package does not say how many effects.

### 4. Remaining warnings

<!-- warnings:case_f -->
Generated from `validate_plant`: 10 warnings, 0 errors.
- `line_without_contents` (5): L-CONDENSATE-8IN, L-T31-VENT, L-T32-VENT, L-T33-VENT, L-VENT-DISCHARGE
- `missing_design_limits` (5): SURFACE-CONDENSER, T-31, T-32, T-33, TK-WEAK-BLACK-LIQUOR
<!-- /warnings:case_f -->

---

## case_g — Plant G: silicone emulsions and blends, batch plant

### 1. Proposed assumptions

- [x] `SIH.epa_groups` = [105] (strong reducing agents; plant-data decision of 2026-10-12)
- [x] `SIH.cameo_groups` = [58, 35] (siloxanes; metal hydrides and silanes)
- [x] `KOH-EMULSIFIER.epa_groups` = [10, 106] (caustic, aqueous)
- [x] `KOH-EMULSIFIER.cameo_groups` = [10, 100]
- [x] `PDMS.cameo_groups` = [58]
- [x] `VINYL-POLYMER.cameo_groups` = [58]
- [x] `ACETIC-ACID.epa_groups` = [3] (organic acids)
- [x] `ACETIC-ACID.cameo_groups` = [3]
- [x] `IPA.epa_groups` = [4]
- [x] `IPA.cameo_groups` = [4]
- [x] `DI-WATER.epa_groups` = [106]
- [x] `DI-WATER.cameo_groups` = [100]
- [x] `PT-CATALYST.cameo_groups` = [99] (composition not stated)
- [x] `SURFACTANTS.cameo_groups` = [99] (composition not stated)
- [x] `BIOCIDE.cameo_groups` = [99] (composition not stated)

### 2. Package facts the schema cannot hold

None left without a home: "loose lids with a manway", "re-packaged into totes on site and labelled by hand", "Electrical area classification: unclassified, general-purpose equipment throughout", batch sizes and PPE are notes.

### 3. Modelling choices to confirm

- **Totes** are one object (`TOTES`, type `tank`, 1 m³ from "1,000-litre IBC totes") in the warehouse bay, holding the nine materials that "arrive in 1,000-litre IBC totes or drums" (deionised water comes "from the plant system", so it is not in the totes). The number of totes is not stated.
- **Hoses** (survey decision A3): one `is_hose` line per mixing tank, from the warehouse bay through the portable pump to MX-1 … MX-4. This is a modelling choice, not a stated layout: the package says only "A portable air-operated diaphragm pump and hoses used to charge tank contents".
- **The charging procedure** is split into four steps, each the package's own words, at its commas: read the batch sheet; collect the listed tote with a forklift; connect the hose and pump into the mixing tank; sign the batch sheet. The whole sentence is kept as a note on the procedure.
- **The building** is `indoor: true` ("Single enclosed production building"). `ignition_sources` is left empty: "unclassified, general-purpose equipment throughout" is kept as a note, not turned into a flag.
- **Equipment types:** mixing tanks → `mixer`; portable pump → `pump`; homogeniser and filling line → `other`.

### 4. Remaining warnings

<!-- warnings:case_g -->
Generated from `validate_plant`: 9 warnings, 0 errors.
- `line_without_contents` (4): L-HOSE-MX-1, L-HOSE-MX-2, L-HOSE-MX-3, L-HOSE-MX-4
- `missing_design_limits` (5): MX-1, MX-2, MX-3, MX-4, TOTES
<!-- /warnings:case_g -->

---

## case_h — Plant H: dry corn mill

### 1. Proposed assumptions

- [x] `CORNMEAL.combustible_dust` = true (survey decision C; the package does not say combustible)
- [x] `CORN-FLOUR.combustible_dust` = true (survey decision C)
- [x] `CORN.epa_groups` = [101]
- [x] `CORN.cameo_groups` = [98] (not chemically reactive)
- [x] `GRITS.epa_groups` = [101]
- [x] `GRITS.cameo_groups` = [98]
- [x] `CORNMEAL.epa_groups` = [101]
- [x] `CORNMEAL.cameo_groups` = [98]
- [x] `CORN-FLOUR.epa_groups` = [101]
- [x] `CORN-FLOUR.cameo_groups` = [98]
- [x] `WATER.epa_groups` = [106]
- [x] `WATER.cameo_groups` = [100]
- [x] `NATURAL-GAS.epa_groups` = [29]
- [x] `NATURAL-GAS.cameo_groups` = [29]
- [x] `DEGERMINATION.location_id` = LOC-H-MILL-BUILDING
- [x] `ROLLER-MILLS.location_id` = LOC-H-MILL-BUILDING
- [x] `HAMMER-MILLS.location_id` = LOC-H-MILL-BUILDING
- [x] `ROTARY-SIFTERS.location_id` = LOC-H-MILL-BUILDING
- [x] `ASPIRATORS.location_id` = LOC-H-MILL-BUILDING
- [x] `PURIFIERS.location_id` = LOC-H-MILL-BUILDING
- [x] `BUCKET-ELEVATORS.location_id` = LOC-H-MILL-BUILDING
- [x] `SCREW-CONVEYORS.location_id` = LOC-H-MILL-BUILDING
- [x] `PNEUMATIC-CONVEYING.location_id` = LOC-H-MILL-BUILDING
- [x] `BAGGING.location_id` = LOC-H-MILL-BUILDING

Why the locations (proposed by Bhargavi, 2026-10-13): "5-storey mill building; operators work on all floors", with the mill process listed under it. SILOS, BINS, CORN-DRYER, CLEANING, TEMPERING and BULK-LOADOUT stay unlocated.

### 2. Package facts the schema cannot hold

None left without a home: the three-year records (bearing replacements, "3 reports of smouldering material found in equipment", belt misalignment, housekeeping, the lost-time injury) and "~20 people per shift" are notes.

### 3. Modelling choices to confirm

- **Plural equipment** the package does not count (roller mills, hammer mills, sifters, aspirators, purifiers, bucket elevators, screw conveyors, pneumatic conveying lines, silos, bins) is one object each.
- **Equipment types:** silos and bins → `tank`; tempering → `other`; corn dryer → `dryer` (natural gas heat source); every other process step and conveyor → `solids_handler`; baghouse → `other` on the roof.
- **Dust collection:** `dust_collection: true` on the mills, sifters, conveyors and bagging (from "ductwork from mills, sifters, conveyors and bagging"), each with a duct line to the shared baghouse (survey decision A2). Aspirators and purifiers are not named in that sentence and are left unset.
- **Locations:** the mill building is `occupied` and `indoor` ("operators work on all floors"). Which equipment sits in it is not stated, so no equipment has `location_id` except the baghouse ("on the roof").
- **Process lines** are not drawn between steps (the package lists the order with "then" but names no lines), except truck and rail receiving into the silos.

### 4. Remaining warnings

<!-- warnings:case_h -->
Generated from `validate_plant`: 10 warnings, 0 errors.
- `line_without_contents` (7): L-DUCT-BAGGING, L-DUCT-ELEVATORS, L-DUCT-HAMMER-MILLS, L-DUCT-PNEUMATIC, L-DUCT-ROLLER-MILLS, L-DUCT-SCREW-CONVEYORS, L-DUCT-SIFTERS
- `missing_design_limits` (3): BINS, CORN-DRYER, SILOS
<!-- /warnings:case_h -->
