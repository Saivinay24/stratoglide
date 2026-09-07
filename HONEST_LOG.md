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
