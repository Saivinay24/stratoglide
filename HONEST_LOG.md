# HONEST_LOG

Append-only record of pre-registrations, downgrades, deviations from the plan, null results and
misses. Newest entries at the bottom. Nothing here is edited after the fact; corrections are new entries.

## 2026-11-18 P0 pre-registration

PREREG bars.yaml sha256=329c66080aa03875ceaac78206e6736d9e3bd89fe15d85a9b470b5baca49b3a6
PREREG mission.yaml sha256=3348d87014ae21bad5434679f7b16655d9300c7c9193cda89b6432747c8fc8b1

Both files are frozen from this point. Check 0 compares the live files to these hashes.
Selection weights and Re-band rules are pre-registered in config/design_space.yaml before any sweep runs.

## 2026-11-18 P0 toolchain

- XFOIL 6.99 built from MIT source on rung 1 (Homebrew gfortran 16.1 + Homebrew libX11 1.8.13),
  flags `-std=legacy -fallow-argument-mismatch -fdefault-real-8`. Runs headless with `PLOP / G F`.
  Smoke: NACA 0012, Re 1e6, alpha 4 deg gives CL 0.4278 (plan expected about 0.44; XFOIL's own value).
- AVL: the plan names 3.40; the MIT page serves `avl3.40b.tgz`, built on rung 1 (gfortran + libX11 +
  Accelerate LAPACK). Smoke: bundled `vanilla.avl` alpha 0 gives CLtot 0.15546, e 0.9745.
- No rung beyond 1 was needed for either tool.
## 2026-11-18 P1 reference-table deviation

- The plan lists USSA-1976 reference points 0, 11, 20, 25, 30, 32 km. The fetched public-domain source
  (PDAS tables of USSA-1976, stored raw in data/validation/) tabulates geometric altitude every 5 km
  (bigtables, 5 significant figures) and every 2 km (ratio table, 4-5 significant figures). 11 km is in
  neither table, so check 1 uses all 22 tabulated points from 0 to 35 km (which include 0/20/25/30/32 km
  and 10/12 km around the tropopause) instead of an 11 km point. This is more points, not fewer.

## 2026-11-18 P2 pre-registration (written before validate.py was first run)

- Validation series: primary Vol 3 E387 (C) clean and Vol 3 SD7037 (D) clean; secondary Vol 1 E387 (A)
  and Vol 1 SD7037 (B), used only to report tunnel-to-tunnel scatter with the same metric.
- Models run at the tunnel's measured average Re for each run (e.g. 99,744 not 100,000).
- Design Ncrit rule: minimise mean over {E387, SD7037} x {100k, 200k} of
  (CD MAPE / 0.15 + CLa err / 0.10 + CLmax err / 0.10) / 3; ties to the value closest to 9.
  Re 60k and 300k are held out.
- Re_min_validated = lowest Re in {60k, 100k, 200k, 300k} where both foils pass all three metrics at the
  design Ncrit.
- Stall gentleness in selection comes from NeuralFoil for every candidate (XFOIL post-stall convergence
  is unreliable), stated in SELECTION_RATIONALE.
- Selection winner robustness rule: if the design-Ncrit winner is not the winner at every Ncrit in
  {7, 9, 11, 12}, the candidate with the best mean rank over those Ncrit wins, and the flip is logged.

## 2026-11-18 P2 validation result: check 5 FAILS (honest negative)

Design Ncrit by the pre-registered rule = 5 (scores N5 0.942, N7 0.993, N9 1.066, N11 1.261, N12 1.397).
XFOIL at Ncrit 5 vs UIUC Vol 3 (CD MAPE / CLa err / CLmax err):

| Foil | 60k | 100k | 200k | 300k |
|---|---|---|---|---|
| E387 | 58.8% / 21.3% / 0.05 | 38.9% / 22.6% / 0.03 | 19.5% / 6.1% / 0.07 | 13.4% / 3.5% / 0.01 PASS |
| SD7037 | 37.0% / 1.5% / 0.03 | 17.9% / 2.6% / 0.07 | 5.5% / 2.0% / 0.08 PASS | 2.5% / 2.2% / 0.10 PASS |

- XFOIL drag is LOW in every failing case (E387 100k: -20% to -34% across the bubble drag hump at CL 0.35-0.84).
- No single Ncrit passes both foils at 100k. At Ncrit 9 both pass at 200k, but the rule picked 5. Rule kept.
- Tunnel-to-tunnel scatter (UIUC Vol 1 vs Vol 3 model of the same airfoil, same metric): E387 33.9% (60k),
  16.6% (100k), 4.6% (200k); SD7037 21.2% (60k), 1.6% (100k), 4.1% (200k). At E387 100k the 15% bar is
  tighter than the tunnel's own repeatability.
- NeuralFoil tracks XFOIL within about 1 point of CD MAPE everywhere, as expected: it is trained on XFOIL
  and has the same bias.
- Strict pre-registered result: Re_min_validated = 300k (numbers.json p2.re_min_validated). MR-9 is
  judged against this value and will be reported NOT MET if the design loiter Re is below it.

## 2026-11-18 Downgrades D1/D2, decided AFTER seeing the validation numbers and BEFORE selection/P3

- D1 design Re floor: Re >= 300k at 19 km within span <= 3 m (MR-7) and stall <= 11 m/s EAS (MR-8) is
  expected to be infeasible; P3 computes and reports the maximum loiter Re that is reachable. The design
  floor used for sizing and for the selection Re bands is p2.re_design_floor = 100k, the upper end of the
  "expected 60k-100k" bracket written into MR-9 in the frozen mission requirements. This is a labelled
  downgrade, not a pass: MR-9 stays NOT MET against 300k in check 9 and in every report table.
- D2 measured drag correction: in sizing and performance, the XFOIL section CD is multiplied by
  k(Re) = mean over {E387, SD7037} of mean(CD_exp / CD_xfoil) at design Ncrit at that validation Re,
  interpolated in log Re and clamped to the measured range. The larger single-foil k is carried as the
  pessimistic band in P7. Validation is still reported as FAILED; k is a design knockdown, not a
  validation result, and it is never applied to the validation numbers themselves.

## 2026-11-18 P2 selection: argmax winner S1223, Ncrit flip, then disqualified by its own tunnel data (D3, D4)

- Pre-registered argmax at design Ncrit 5: S1223 0.688, E387 0.570, SD7032 0.520, SA7038 0.442,
  SD7037 0.397, SA7035 0.286, AG35 0.247, MH32 0.206. Flip: S1223 is not the winner at every Ncrit in
  {7, 9, 11, 12} (Kendall tau of the top-3 drops to 0.33 at Ncrit 11 and 12). The pre-registered robust
  rule (best mean rank) still returns S1223.
- S1223 is outside the E387/SD7037 validation set. UIUC Vol 5 has clean S1223 LIFT data (no drag) at
  Re 80k-250k. Against it, XFOIL Ncrit 5 overpredicts CLmax by 0.74 / 0.64 / 0.56 at Re 80k / 100k / 120k
  and agrees to 0.02-0.03 at Re 140k-250k: a laminar-bubble lift cliff between 120k and 140k, inside the
  loiter band. The S1223 lift slope over -2..5 deg misses the 10% bar at every Re (20-71%).
- An earlier draft of validate_selected.py fell back to the 100k floor when no Re passed. That would have
  loosened the gate. Caught before use and replaced by D3.
- D3 (decided after seeing the S1223 data): a candidate whose OWN tunnel data show a CLmax error above the
  0.10 bar at any tested Re inside the loiter design band is disqualified (an unmodelled lift cliff is a
  safety hazard; the D2 drag knockdown does not cover it). Selection then moves down the argmax order.
  With this gate S1223 is disqualified and E387 (rank 2) is checked next against its own data.
- D4 (tightening): if the selected section is itself one of the validation foils, the nominal design
  drag knockdown is that foil's OWN measured k(Re) instead of the two-foil mean; the two-foil mean becomes
  the optimistic band. This can only make predictions more conservative.
- D3 applied: S1223 own-data CLmax errors in band 0.64 (100k), 0.56 (120k), 0.03 (140k) -> disqualified.
  E387 own data (Vol 3) CLmax error 0.03 at 100k -> PASS -> selected. Independent Vol 5 E387 lift entry:
  CLmax error 0.03-0.09 at 60k-460k (passes), CLa 21-42% at 60k-100k (fails), reported as measured.
- D4 consequence: E387 is a validation foil, so sizing uses E387's own measured knockdown
  (k = 1.66 at 100k, 1.24 at 200k) as nominal; the two-foil mean is the optimistic band.
- Tail section by the pre-registered rule: HT12 (lowest mean CD over |alpha| <= 4 deg at Re 30-50k).

## 2026-11-18 P3 sizing results and notes

- Grid (108,000 points, 2,778 feasible) 3.764 kg vs AeroSandbox Opti 3.746 kg: 0.50% apart (bar 2%).
- Final closure with an integer 4S pack re-optimises the planform with the pack fixed: an earlier closure
  held the planform fixed after rounding 16.x cells to 20 and violated MR-8 by 0.23 m/s. Fixed by
  re-solving; final MTOW 4.067 kg, span 1.683 m, S 0.472 m^2, AR 6.0, 20 cells, W/S 84.5 N/m^2.
- Active constraints: MR-8 stall (11.00 m/s EAS) and the D1 Re floor (Re 100,000). They meet at one wing
  loading: the validated-Re constraint pinches the feasible region to a line.
- The AR lower bound (6.0, design-practice floor in design_space.yaml) is active. Not widened: lower AR
  only worsens loiter L/D (already 9.3, driven by E387's own measured 1.66x drag knockdown).
- MR-9 strict NOT MET: max loiter Re reachable under every other constraint is 150,037 < 300,000.
  Check 9 FAILS on this, as pre-declared.
- Span 1.68 m is outside the 2-3 m plausibility band (MTOW 4.07 kg is inside 3-5 kg). Forced by the Re
  floor plus the stall limit, not hardcoded.
- MR-5 payload thermal: with 10 mm payload foam the payload box reached -22.9 C (< -20 C). Design change:
  20 mm foam (config/sizing.yaml), foam mass added to the weight build-up; payload min now -9.4 C.
- MR-10: cells stay >= -2.3 C, but the heater delivers only 0.007 Wh. The 20-cell heat capacity and I^2R
  self-heating carry the pack. Check 10's "heater energy > 0" condition passes on a negligible value; the
  substantive result is the cell temperature and the -37.7 C no-insulation counterfactual.
- Spar: ideal carbon caps came out at about 4 mm^2 (28 g). A 20 mm^2 per-cap minimum gauge was added as a
  stated assumption before the final run.

## 2026-11-18 P4 stability

- Dutch-roll damping at 20 km was 0.001 with VV 0.035 (bar 0.02); the aft-CG case at 20 km was divergent.
  Design change, not a bar change: stability/dr_trade.py swept VV x dihedral. The rule was smallest VV
  meeting the bar with a stable spiral, and it selected VV 0.065 at 5 deg dihedral. P3 was re-sized:
  MTOW 4.105 kg, span 1.691 m, L/D 8.90. 20 km DR zeta is now 0.026; at the aft CG it is stable.
- Pitch trim: the battery cannot reach the target CG inside the pod, so the pod and every item mounted in it
  shift +0.0235 m relative to the wing. SM is 11.56% MAC at every altitude.
- Check 12 FAIL (honest): phugoid period ratio T(20 km)/T(SL) is 2.903 vs V_TAS ratio 3.712 (21.8%, bar 20%).
  Every mode bar passes. The Lanchester T proportional to V scaling is approximate at mu ~670.
- Check 13 FAIL (honest): AeroSandbox 4.2.10 VLM does not grid-converge on this geometry. Grids 12x8 / 30x12
  / 50x16 / 80x20 give Xnp 0.1592 / 0.1635 / non-physical (CLa < 0) / 0.1503 m. AVL is converged (Xnp
  0.1662 m, 0.01% MAC across 1.0-2.5x resolution; 3x overflows NVMAX=6000).
  Hypothesis "tail in the wing wake plane" tested by stability/asb_diag.py: with the tail 0.15 m lower,
  ASB still fails at 50x16, so the hypothesis is REJECTED. Root cause unknown. At 30x12 the codes agree
  within the bars, but that is a post-hoc grid choice and is not used for the check.
- AVL limitation: the pod is not modelled as a BODY, so its destabilising Cm_alpha and Cn_beta are absent.
  AVL is linear and inviscid.
- Flying-wing trade (same wing and CG, no tail): SM -13.1%, Cn_beta -0.0039. The tail is required.

## 2026-11-18 P6 propulsion

- BEMT (Ning-style phi residual, Prandtl tip/hub loss, NeuralFoil section table, Prandtl-Glauert + Korn wave
  drag). APC section geometry is proprietary, so a stand-in section was chosen on a declared calibration prop
  (APC 10x7, all RPMs) from {naca4412, clarky, naca6412, e63, sd7037} by the CT metric: e63. APC 9x6 and 10x5
  are held out.
- Check 17 FAIL (honest): held-out CT error up to 40.8% (9x6 at 5000 rpm; bar 10%). eta_peak error max 0.049
  (bar 0.05) and eta <= momentum ideal everywhere both pass. The J trend is right; the CT level is model-form
  error from the section stand-in at Re75 43k-67k. The section was NOT re-picked on the held-out props.
- Bugs found and fixed before results were used: (1) tip Mach was read from the r = R element, where F -> 0
  makes the induction meaningless (reported 0.10 at 19 km); it is now the geometric helical tip Mach (0.65 at
  20 km). (2) The VP collective optimiser was local (VP < fixed pitch B at 10 and 15 km); it is now a 1-deg
  grid scan plus a bounded refine.
- Physics result: at constant EAS, rho V^2 is constant, so the required CT/J^2 is identical at every altitude.
  Fixed pitch with free RPM loses only to blade Re and tip Mach. VP gain vs same-blade fixed pitch A is
  1.04 points max (at sea level); vs B it is 3.05 points (at 20 km). The plan's "~15 points" target came from
  a density-ratio argument, and the real number replaces it.
- Check 18 was first written stricter than the plan (VP >= both A and B). Blade B has a different helical
  twist, so collective on blade A falls 0.0001 short of B at 10 km. The check was aligned to the plan's
  definition (same blade, a single FP design point); the B shortfall is still printed by the check.
- Diameter trade hits its upper bound (0.45 m; eta still rising). Kept as a stated layout limit.
- P3 <-> P6 iterated to convergence: MTOW 4.105 -> 3.760 kg, 16 cells (4S4P), prop D 0.45 m P/D 1.18,
  motor AT2814 KV900 class (ESTIMATE catalog values), motor eta 0.81 at loiter. P4 re-run on this airframe:
  SM 11.49%, 20 km DR zeta 0.021 (bar 0.02).
- Winding temperature at low rho is not modelled (GAPS).

## 2026-11-18 P5 release and pull-out

- Own vectorised 6-DOF (quaternion, RK4, dt 0.01 s) and JSBSim 1.3.3 share one aero model (aero_tables.py)
  and one control law (autopilot.py). Deviation from the plan: the pull-out law runs in Python through the
  JSBSim property tree each step instead of as an XML <system>, so both simulators fly the identical law.
- Autopilot bugs found and fixed before the MC used for results: (1) a proportional-only pitch-rate loop left a
  steady flight-path error (integral added); (2) yaw-damper sign inverted (AVL Cn_dr > 0) drove stalled
  spirals; (3) gains were unscheduled, giving 5-13 ms closed-loop time constants at dive dynamic pressure,
  comparable to the 10 ms control step. JSBSim showed a +/-100 deg/s roll limit cycle that RK4 had tolerated.
  Fixed with EAS-scheduled gains, (V_ref/EAS)^2, V_ref = 1.3 Vs, set from target time constants; roll-angle hold
  is gated off above |theta| 60 deg (Euler gimbal lock). The final MC was re-run on the corrected law.
- MC N = 500 (LHS, seed 20261118). The plan's "blend width +/-3 deg" is interpreted as blend centre +/-3 deg plus
  width 1-3 deg.
  Autopilot: 100% recovered; P99 Mach 0.417; max n 2.70 g; altitude lost P50 841 m / P95 1065 m.
- Check 15 FAIL (honest) on the passive case: 0% "recovered" (bar 95%). Every passive run pulls out (max Mach
  0.460, max n 3.10 g), but the 20-25 km phugoid (zeta ~0.09, period ~25 s) is not inside |gamma - gamma_glide|
  < 3 deg held 10 s within 120 s. Gamma swing in the last 20 s has P50 13.9 deg. The bare airframe is
  statically safe but not "recovered" by the pre-registered definition.
- JSBSim vs own nominal: altitude lost 826.6 vs 819.4 m (0.9%), peak n 2.42 vs 2.46 g (1.6%); JSBSim rho(25 km)
  matches atmos.py to 2.0e-6.
- Vertical-dive counterfactual (point mass, zero lift, locked nose-down): max Mach 0.698 (0.694 with the drag-rise
  placeholder). The plan expected M > 1; with CD0 0.048 the terminal speed stays subsonic. The real number goes in.
- Flutter screen (Theodorsen 2-DOF typical section, V-g, ESTIMATE skin/section values): min flutter speed
  54.5 m/s EAS (at 25 km, where the flutter TAS is near M 1, outside incompressible Theodorsen validity,
  flagged). Margin vs MC max EAS 27.4 m/s is 2.0x. Screening estimate, not clearance.
- Energy sanity: max d(V_air^2/2 + g h)/dt + wind-shear work over 1000 runs = -2.0e-5 W/kg (dissipative).
- Wind direction is assumed constant with altitude (IGRA percentiles carry speed only).

## 2026-11-18 P7 mission performance

- Same drag model and energy budget as P3 (SizingModel), P6 prop/motor efficiencies.
- MR-4 met: loiter endurance 35.5 min at 19 km (39.6 at 18 km, 31.7 at 20 km) vs 30 min required.
- Check 19 FAIL (honest): still-air glide range 25 km -> deploy is 239.6 km by quadrature of L/D_max(h) vs
  252.9 km from dh x L/D at mid altitude (L/D 10.82): 5.3% apart, bar 5%. L/D_max falls from 11.9 (SL) to
  8.9 (20 km) with Re, so the mid-altitude L/D is not the path average. The definition (mid-altitude L/D) was
  fixed before the result and is not changed.
- Return footprint from end of loiter (19 km, P95 winds, all layers aligned): downwind reach 513 km, into wind
  24 km, crosswind tracks 75-105 deg infeasible (P95 jet-layer crosswind exceeds airspeed, so the track cannot
  be held). Operator reading: the release point must not be crosswind of the recovery site in P95 conditions.
- Induced drag uses the AVL span efficiency (0.99) because the CL-dependence of profile drag is already in the
  section polar fit; this is not an Oswald factor.

## 2026-11-18 P8 build package

- CadQuery: wing halves and tails lofted from airfoil coordinates, pod as a capped loft (a revolve with an edge on
  the axis gave a non-watertight pole in the STL), boom tube. 7/7 parts watertight; STEP re-imports 7 solids;
  mesh span matches geometry.json to 8.5e-9 and planform area to 0.36% (bar 1%).
- BOM: INR 70,600 airframe total (payload excluded). 100% ESTIMATE: unit prices are class values in
  config/bom_prices.yaml, not fetched from vendors, so no URLs or retrieval dates are claimed. Sourced share 0%.
- ArduPlane starter params: 21 names, all present in apm.pdef.xml (renamed variants chosen from the file).
  AIRSPEED_MAX 26 m/s EAS is the minimum over 0-25 km of VNE(h); at 25 km the Mach 0.5 limit governs, not
  flutter. Airspeed sensors covering 535 Pa range and 1.72 Pa resolution: MS4525DO, SDP33, DLVR-L10D class
  (SDP31's 500 Pa range is short).
- Test cards FT-1..FT-6: 25 schema-valid predictions, each keyed to numbers.json. FT-5 (2 km AGL) and FT-6 (10 km)
  bands come from 100-sample MCs at those altitudes (100% recovered both).
- Provenance bug fixed: Numbers.save() overwrote the phase file, so with several scripts per phase the last
  writer silently dropped earlier numbers (P5 lost JSBSim/flutter keys, P6 lost BEMT validation keys). save()
  now merges, replacing only keys from the same script; affected scripts were re-run.

## 2026-11-18 P9 report, site, lint

- Report (HTML + PDF via headless Chrome; WeasyPrint not installed), README and resume contract are rendered
  from results/numbers.json. Every hardcoded literal found in the first template draft (bars typed in as text)
  was replaced by its bars.* key before the first lint pass counted.
- lint_report.py: numeric tokens in report, README, resume contract, site HTML, BOM and test cards must match a
  numbers.json value (or a frozen config input) at printed precision. First pass: 33 untraceable tokens, all
  derived band limits printed from raw floats; fixed by recording every band limit and every computed BOM cell
  as a numbers.json key and rounding printed values from the stored 6-significant-figure value. Now 0.
- Footprint: tracks that cannot make progress into the P95 wind were -inf in perf.json; the site JSON writes
  them as null and draws them as gaps instead of plotting a fake reach.

## 2026-11-18 clean-clone reproduction (incomplete)

- `make pipeline` from a fresh `git clone` of 3542d31 (backups/clean_clone, log backups/clean_clone.log) rebuilt
  XFOIL/AVL and ran P1, the full uncached P2 sweep and two passes of the coupled P3/P4/P6 loop. P3 pass 1 (no P6
  data): MTOW 4.105 kg, 20 cells; pass 2: MTOW 3.761 kg, 16 cells, span 1.618 m (repo: 3.760 kg, 16 cells).
- The run was then stopped by the host (system low on memory, not a pipeline error), during the second P4 pass.
  No results/repro.json was written, so check 20's reproducibility item stays FAIL. Not re-run unattended.
