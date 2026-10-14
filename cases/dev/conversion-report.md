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

- [ ] `BUTANES.epa_groups` = [29] (hydrocarbons, aliphatic, saturated)
- [ ] `BUTANES.cameo_groups` = [29]
- [ ] `BUTENES.epa_groups` = [28] (hydrocarbons, aliphatic, unsaturated)
- [ ] `BUTENES.cameo_groups` = [28]
- [ ] `BUTADIENE.epa_groups` = [28, 103] (unsaturated aliphatic; polymerizable)
- [ ] `BUTADIENE.cameo_groups` = [65, 76] (conjugated dienes; polymerizable compounds)
- [ ] `ACETYLENES.epa_groups` = [28]
- [ ] `ACETYLENES.cameo_groups` = [63] (alkynes with acetylenic hydrogen)
- [ ] `WATER.epa_groups` = [106]
- [ ] `WATER.cameo_groups` = [100]
- [ ] `NMP.epa_groups` = [6] (amides)
- [ ] `NMP.cameo_groups` = [6] (amides and imides)
- [ ] `TBC.epa_groups` = [31] (phenols and cresols)
- [ ] `TBC.cameo_groups` = [31]
- [ ] `HEAVIES.cameo_groups` = [99] (insufficient information for classification)
- [ ] `ANTIFOAM.cameo_groups` = [99] (composition not stated)

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
Generated from `validate_plant`: 27 warnings, 0 errors.
- `chemical_without_groups` (9): ACETYLENES, ANTIFOAM, BUTADIENE, BUTANES, BUTENES, HEAVIES, NMP, TBC, WATER
- `line_without_contents` (4): L-OFFSPEC, L-P104B-DIS, L-P104B-SUC, L-STARTUP-RECYCLE
- `missing_design_limits` (12): C-101, C-102, C-103, C-104, E-104, E-105, E-106, TK-201, TK-202, TK-OFFSPEC, V-101, V-104
- `missing_fail_position` (2): BV-P104B-DIS, BV-P104B-SUC
<!-- /warnings:case_d -->

---

## case_e — Unit E: FCC unit, planned shutdown

### 1. Proposed assumptions

- [ ] `HGO.epa_groups` = [29] (heavy gas oil: saturated hydrocarbons)
- [ ] `HGO.cameo_groups` = [29, 16]
- [ ] `CRACKED-VAPOURS.epa_groups` = [28, 29]
- [ ] `CRACKED-VAPOURS.cameo_groups` = [28, 29]
- [ ] `C1-C4-GASES.epa_groups` = [28, 29]
- [ ] `C1-C4-GASES.cameo_groups` = [28, 29]
- [ ] `NAPHTHA.epa_groups` = [29]
- [ ] `NAPHTHA.cameo_groups` = [29, 16]
- [ ] `TORCH-OIL.epa_groups` = [29]
- [ ] `TORCH-OIL.cameo_groups` = [29]
- [ ] `ASPHALT.epa_groups` = [101] (combustible and flammable materials, miscellaneous)
- [ ] `ASPHALT.cameo_groups` = [29]
- [ ] `HF.epa_groups` = [1, 15] (mineral acid, non-oxidizing; inorganic fluorides)
- [ ] `HF.cameo_groups` = [1]
- [ ] `COKE.epa_groups` = [101]
- [ ] `COKE.cameo_groups` = [99]
- [ ] `CATALYST.cameo_groups` = [99] (composition not stated)
- [ ] `FLUE-GAS.cameo_groups` = [99] (composition not stated)
- [ ] `AIR.cameo_groups` = [49] (oxidizing agents, weak)

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
Generated from `validate_plant`: 21 warnings, 0 errors.
- `chemical_without_groups` (11): AIR, ASPHALT, C1-C4-GASES, CATALYST, COKE, CRACKED-VAPOURS, FLUE-GAS, HF, HGO, NAPHTHA, TORCH-OIL
- `missing_design_limits` (8): ABSORBER, DEBUTANISER, MAIN-FRACTIONATOR, REGENERATOR, RISER, STRIPPER, TK-ASPHALT-1, TK-ASPHALT-2
- `missing_fail_position` (2): SV-REGEN, SV-SPENT
<!-- /warnings:case_e -->

---

## case_f — Area F: pulp mill evaporator and condensate area, two-week work window

### 1. Proposed assumptions

- [ ] `WATER.epa_groups` = [106]
- [ ] `WATER.cameo_groups` = [100]
- [ ] `METHANOL.epa_groups` = [4] (alcohols and glycols)
- [ ] `METHANOL.cameo_groups` = [4]
- [ ] `TURPENTINE.epa_groups` = [28]
- [ ] `TURPENTINE.cameo_groups` = [28]
- [ ] `ORGANICS.cameo_groups` = [99] (composition not stated)
- [ ] `BLACK-LIQUOR.epa_groups` = [10, 106] (caustic, aqueous)
- [ ] `BLACK-LIQUOR.cameo_groups` = [10, 100]
- [ ] `WEAK-BLACK-LIQUOR.epa_groups` = [10, 106] ("hot, caustic")
- [ ] `WEAK-BLACK-LIQUOR.cameo_groups` = [10, 100]
- [ ] `NAOH.epa_groups` = [10]
- [ ] `NAOH.cameo_groups` = [10]
- [ ] `NA2S.epa_groups` = [33] (sulfides, inorganic)
- [ ] `NA2S.cameo_groups` = [33]

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
Generated from `validate_plant`: 18 warnings, 0 errors.
- `chemical_without_groups` (8): BLACK-LIQUOR, METHANOL, NA2S, NAOH, ORGANICS, TURPENTINE, WATER, WEAK-BLACK-LIQUOR
- `line_without_contents` (5): L-CONDENSATE-8IN, L-T31-VENT, L-T32-VENT, L-T33-VENT, L-VENT-DISCHARGE
- `missing_design_limits` (5): SURFACE-CONDENSER, T-31, T-32, T-33, TK-WEAK-BLACK-LIQUOR
<!-- /warnings:case_f -->

---

## case_g — Plant G: silicone emulsions and blends, batch plant

### 1. Proposed assumptions

- [ ] `SIH.epa_groups` = [105] (strong reducing agents; plant-data decision of 2026-10-12)
- [ ] `SIH.cameo_groups` = [58, 35] (siloxanes; metal hydrides and silanes)
- [ ] `KOH-EMULSIFIER.epa_groups` = [10, 106] (caustic, aqueous)
- [ ] `KOH-EMULSIFIER.cameo_groups` = [10, 100]
- [ ] `PDMS.cameo_groups` = [58]
- [ ] `VINYL-POLYMER.cameo_groups` = [58]
- [ ] `ACETIC-ACID.epa_groups` = [3] (organic acids)
- [ ] `ACETIC-ACID.cameo_groups` = [3]
- [ ] `IPA.epa_groups` = [4]
- [ ] `IPA.cameo_groups` = [4]
- [ ] `DI-WATER.epa_groups` = [106]
- [ ] `DI-WATER.cameo_groups` = [100]
- [ ] `PT-CATALYST.cameo_groups` = [99] (composition not stated)
- [ ] `SURFACTANTS.cameo_groups` = [99] (composition not stated)
- [ ] `BIOCIDE.cameo_groups` = [99] (composition not stated)

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
Generated from `validate_plant`: 19 warnings, 0 errors.
- `chemical_without_groups` (10): ACETIC-ACID, BIOCIDE, DI-WATER, IPA, KOH-EMULSIFIER, PDMS, PT-CATALYST, SIH, SURFACTANTS, VINYL-POLYMER
- `line_without_contents` (4): L-HOSE-MX-1, L-HOSE-MX-2, L-HOSE-MX-3, L-HOSE-MX-4
- `missing_design_limits` (5): MX-1, MX-2, MX-3, MX-4, TOTES
<!-- /warnings:case_g -->

---

## case_h — Plant H: dry corn mill

### 1. Proposed assumptions

- [ ] `CORNMEAL.combustible_dust` = true (survey decision C; the package does not say combustible)
- [ ] `CORN-FLOUR.combustible_dust` = true (survey decision C)
- [ ] `CORN.epa_groups` = [101]
- [ ] `CORN.cameo_groups` = [98] (not chemically reactive)
- [ ] `GRITS.epa_groups` = [101]
- [ ] `GRITS.cameo_groups` = [98]
- [ ] `CORNMEAL.epa_groups` = [101]
- [ ] `CORNMEAL.cameo_groups` = [98]
- [ ] `CORN-FLOUR.epa_groups` = [101]
- [ ] `CORN-FLOUR.cameo_groups` = [98]
- [ ] `WATER.epa_groups` = [106]
- [ ] `WATER.cameo_groups` = [100]
- [ ] `NATURAL-GAS.epa_groups` = [29]
- [ ] `NATURAL-GAS.cameo_groups` = [29]

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
Generated from `validate_plant`: 16 warnings, 0 errors.
- `chemical_without_groups` (6): CORN, CORN-FLOUR, CORNMEAL, GRITS, NATURAL-GAS, WATER
- `line_without_contents` (7): L-DUCT-BAGGING, L-DUCT-ELEVATORS, L-DUCT-HAMMER-MILLS, L-DUCT-PNEUMATIC, L-DUCT-ROLLER-MILLS, L-DUCT-SCREW-CONVEYORS, L-DUCT-SIFTERS
- `missing_design_limits` (3): BINS, CORN-DRYER, SILOS
<!-- /warnings:case_h -->
