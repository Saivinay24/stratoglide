# GAPS (deferred, with reason)

| Item | Why deferred | Named next step |
|---|---|---|
| SU2 RANS gamma-ReTheta E387 check at Re 200k with 3-level GCI | plan negative scope: no CFD this run | Azure VM, SU2 LM2015, Roache GCI on CD |
| NeuralFoil-in-the-loop airfoil optimisation | plan negative scope (P2) | Kulfan shape opt on the loiter Re band, validated vs UIUC |
| Multi-fidelity correction of XFOIL toward UIUC | plan deferred list | GP on (Re, CL) residuals, leave-one-Re-out |
| Aeroelastic flutter beyond a 2-DOF screen | plan deferred list | GVT + p-k analysis before any flight |
| Hot/cold-day atmospheres, humidity | P1 negative scope | MIL-HDBK-310 profiles |
| Motor winding temperature at low rho | P6 note: convective cooling falls with rho | lumped motor thermal model + bench test in a vacuum chamber |
| ArduPilot SITL with the JSBSim model | plan negative scope | SITL JSBSim backend with the generated aircraft XML |
| FlightLoop correlation | sister project | predictions.json is the contract |
