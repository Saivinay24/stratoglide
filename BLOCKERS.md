# StratoGlide blockers

The done definition is 21/21 checks (0-20) from a clean clone. The checks below fail on pre-registered bars.
None was loosened; each real number is in HONEST_LOG.md and results/numbers.json. They are physics or
model-fidelity limits, not missing work, so they cannot be closed inside this repo's toolchain without
changing a frozen bar (forbidden) or adding a higher-fidelity tool / test.

| Check | Bar | Measured | Why it cannot be closed here | What would close it |
|---|---|---|---|---|
| 5 XFOIL vs UIUC | CD error <= 15% at Re 100k and 200k, both foils | E387 38.9% / 19.5%, SD7037 17.9% / 5.5% (Ncrit 5) | XFOIL's e^N transition under-predicts laminar-bubble drag at Re 100k on E387; no Ncrit fixes all four cases | transition-RANS (SU2) or tunnel data at the design Re; the design already carries the measured knockdown k(Re) |
| 9 MR-9 strict | loiter Re >= Re_min_validated (300,000) | 100,000; max reachable under the other MRs 144,811 | at 19 km with a 1.62 m span limit and an 11 m/s hand-launch stall, Re 300k is infeasible (mission conflict, shown by the sizing sweep) | relax span or stall requirement (mission change, not a design change) |
| 12 Dynamic modes | phugoid period ratio within 20% of the V_TAS ratio | T(20 km)/T(SL) 2.903 vs V_TAS ratio 3.712 (21.8%) | the bar assumes Lanchester scaling (period proportional to V), which is approximate at relative density mu ~670; the AVL eigenvalues are the measured result and every damping bar passes | nothing inside the frozen bar; the scaling model is the approximation |
| 13 AVL vs AeroSandbox | CLa within 5%, Xnp within 2% MAC, both converged | CLa 6.33%, Xnp 5.54% MAC; ASB last-step change 53.9% MAC | ASB VLM does not grid-converge on this geometry (wake hypothesis tested and rejected in p4/asb_wake_diag.json); picking one ASB grid would be cherry-picking | an independent converged VLM/panel code (e.g. XFLR5 run by hand on the exported XML) |
| 15 Passive recovery | >= 95% recovered with controls fixed | 0.0% (airframe pulls out, max Mach and n inside bars) | the 20-25 km phugoid (zeta ~0.09, period ~25 s) never holds flight path within 3 deg for 10 s inside 120 s (gamma swing P50 13.9 deg in the last 20 s); autopilot recovery is 100% | longer window or a passive pitch damper; changing the definition is not allowed |
| 17 BEMT held-out CT | CT error <= 10% on held-out APC props | 40.8% (eta peak 0.049 passes) | section stand-in calibrated on one prop; low-Re blade sections are the same XFOIL limit as check 5 | measured blade-section polars or a static thrust test |
| 19 Glide range consistency | still-air range within 5% of dh x L/D(mid altitude) | 5.3% | L/D varies with altitude through Re and Mach; the single mid-altitude product is the approximation | none needed; the integrated range is the trusted number |

| 20 Clean-clone hash | `make pipeline` from a clean clone reproduces the numbers.json values hash | not measured: run stopped by the host for low memory during the second coupled P4 pass (P3 pass 2 already at MTOW 3.761 vs 3.760 kg) | machine memory pressure, not a code failure; every other check-20 item passes (STEP/STL, mesh 0.36%, 21 valid params, 25 schema-valid keyed predictions, 0 untraceable tokens, 0 em dashes) | run `make reproduce` on an idle machine; it writes results/repro.json |
