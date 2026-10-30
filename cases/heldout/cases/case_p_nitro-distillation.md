# Plant P: mononitrotoluene distillation train (aniline / nitrotoluenes site)

## Data package

**Process / products**
- 60-acre chemical site in a coastal industrial park making aniline and nitrotoluenes. 137 employees plus 8 full-time contractors.
- Mononitrotoluene (MNT) process (continuous, commissioned in the late 1960s): toluene is nitrated with mixed nitric and sulfuric acid → separator (acid recycled) → washing → atmospheric MNT storage tank → toluene stripper → three-column distillation train separating ortho-, meta- and para-MNT. MNT is used for dyes, rubber chemicals and agricultural chemicals.
- A separate batch MNT distillation (still B-310) was added about 6 years ago in an existing column.

**Major equipment**
- C-1 "No. 1 MNT still", first column of the train: 7 ft diameter, about 145 ft tall, insulated; stainless-steel structured packing; chimney tray near the top with a high-level alarm; top collector tray. Normal operation under vacuum drawn by steam eductors; bottoms about 350 °F, mid-bed about 300 °F, top about 140 °F (procedure values). Nameplate design pressure 15 psig (ASME code vessel). Bottoms pump sends mainly para- and meta-MNT to column C-2; reflux pump returns mainly ortho-MNT from the collector tray through the reflux cooler.
- E-1A / E-1B steam-heated shell-and-tube reboilers on C-1, each with a condensate return.
- Steam stations SS-A and SS-B (identical), one per reboiler, each on a 3-inch line: inlet manual block valve; automatic flow control valve FV-A / FV-B (DCS-operated; not a tight-shutoff valve); outlet manual block valve; manual block valve on a bypass line (normally closed). Supplied from the central steam plant at 300 psig.
- E-2 C-1 reflux cooler.
- PSV-1 3-inch relief valve on the C-1 overhead vapour line, set at 15 psig; no design-basis records.
- C-2 and C-3, second and third MNT columns.
- B-310 batch MNT still (hot-oil heated reboiler): documented safe temperature 374 °F or below; operating limit below 370 °F; high-temperature alarm at 400 °F; interlocks trip hot oil on high temperature and on high pressure (loss of vacuum). Procedure: shut off hot oil if pot above 400 °F; do not exceed 395 °F for more than 1 h; no heat without vacuum.
- T-PMNT para-MNT storage tank, about 500 ft from C-1, holding more than 2 million lb.
- T-NH3 anhydrous ammonia storage tank, 500,000 lb, with a pipe rack above it.
- Sulfuric acid concentrator upstream of the MNT unit.
- No. 2 hydrogen unit.
- Unit cooling tower.
- Central steam plant (boilers).

**Lines and connections**
- 3-inch 300 psig steam to E-1A via SS-A and to E-1B via SS-B.
- Condensate return from each reboiler.
- MNT feed from the atmospheric storage tank via the toluene stripper to C-1.
- C-1 overhead vapour line to steam eductors (vacuum), with PSV-1 and a nitrogen tubing connection.
- C-1 bottoms to C-2; reflux from collector tray via E-2 to C-1.

**Chemicals on site**
- Mononitrotoluene isomers (ortho, meta, para), liquid; NFPA flammability 1, reactivity 1; flash point above 100 °F. Current MSDS (revised 4 years ago) gives no decomposition temperature. Literature on file for the batch still project: MNT may decompose explosively above 374 °F; explosions have occurred in fractional distillation when MNT was overheated or held moderately hot for long periods.
- Toluene, nitric acid, sulfuric acid (and oleum), anhydrous ammonia, aniline, hydrogen, formaldehyde, chlorine cylinders.

**Procedures**
1. C-1 operating procedure ("No. 1 MNT still / No. 2 MNT still and toluene stripper"): normal operating steps; no cautions or temperature limits.
2. Emergency shutdown procedure for C-1 covers loss of steam to the overhead eductors and loss of cooling water. On steam failure: put the reboiler steam control valves in manual and closed, and block in the condensate return from each reboiler.
3. No written procedure for de-inventorying C-1 or for temperature monitoring while it is shut down. The site lockout/tagout programme is not applied to steam isolation of an idle column that still contains material; double block and bleed or blinds are not required on the reboiler steam lines.

**Current unit status (this package describes today)**
1. Feed to C-1 was stopped 4 weeks ago (problems at the acid concentrator; low demand; turnaround planned). C-1 holds about 1,200 gal of MNT, kept on total reflux under vacuum with steam on, then left idle.
2. Two weeks ago a fire in the No. 2 hydrogen unit threatened the steam supply; operators closed the outlet manual block valves on SS-A and SS-B (bypass valves already closed) and the DCS closed FV-A and FV-B. These are the current isolations.
3. About 9 days ago the reflux cooler E-2 was drained for tube work; vacuum on C-1 was broken by injecting nitrogen at the top (the 0–200 mmHg gauge cannot confirm the result); the column is now at or slightly above atmospheric pressure.
4. The central steam plant was shut for turnaround (C-1 cooled to near ambient) and came back on line today.
5. The DCS had a power loss and a hard-drive loss in the past week (both restored).
6. Restart date for C-1 not yet set.

**Instrumentation and safeguards**
- Eight temperature indicators on C-1 (seven working), shown on DCS operator screens; no alarms configured on them. TI-B at the vessel bottom; TI-R above the reboiler inlet line.
- Chimney-tray high-level alarm.
- Steam flow indication for FV-A and FV-B on the DCS.
- PSV-1 on the overhead (15 psig).
- No high-temperature interlock or emergency shutdown that cuts the C-1 heat source.
- No formal hazard evaluation of C-1 (judged lower-volume with a good history). MNT distillation is outside the process safety management rule (less than 10,000 lb of toluene downstream of the atmospheric tank; documentation not available). A site runaway incident 16 years ago in a batch distillation (different chemical) led to a recommendation to hazard-analyse existing processes.
- Site fire brigade with water monitors.

**Surroundings**
- Aniline/MNT control room about 50 ft from C-1: masonry block with sheet-metal roof and sides, glass windows and door; also houses locker room, offices, quality-control lab and breakroom. Never evaluated for building siting.
- Administration building about 400–450 ft from C-1.
- Neighbouring refinery to the east with crude tanks about 500 ft from the fence line (including a 250,000 bbl tank); fertiliser plant with an ammonia tank to the south; ship channel 0.25 mile west with residences beyond.

## Task
Perform a full HAZOP of column C-1 and its reboiler steam supply for its current idle state and the planned restart.
