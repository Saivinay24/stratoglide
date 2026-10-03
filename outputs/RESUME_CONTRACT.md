# Resume contract (StratoGlide)

StratoGlide - XFLR5/AVL, XFOIL, JSBSim 6-DOF, BEMT, Python (AeroSandbox, NeuralFoil, CadQuery)

- Designed StratoGlide, a balloon-launched stratospheric ISR glider taken from mission requirements to a build-ready package (build pending), sizing a 3.76 kg, 1.62 m span airframe and validating XFOIL low-Re polars against UIUC wind-tunnel data (6 to 39% drag error at Re 100k-200k, carried as a measured knockdown).
- Built a JSBSim 6-DOF cross-checked to an own simulator (0.9% apart); 500 Monte Carlo releases from 25,000 m recovered 100% to trimmed glide, P99 Mach 0.42, P95 altitude loss 1,065 m. Held 11.5% static margin at sea level and 20 km; BEMT showed variable pitch recovering only 1.0 efficiency points.

| Number | numbers.json key |
|---|---|
| 3.76 kg | `p3.mtow_kg` |
| 1.62 m | `p3.span_m` |
| 6 to 39% | `derived.cd_mape_re100k_200k_best`, `derived.cd_mape_re100k_200k_worst` |
| 500 runs | `p5.mc_n` |
| 100% | `p5.recovery_rate_autopilot` |
| P99 Mach 0.42 | `p5.mach_p99` |
| 1,065 m | `p5.alt_loss_p95_m` |
| 11.5% | `p4.sm_pct_sl` |
| 1.0 points | `p6.vp_gain_eta_points_max` |