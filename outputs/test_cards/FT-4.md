# FT-4: 2-1-1 and doublet inputs (sysID for FlightLoop)

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. Trimmed level flight
2. Pitch 2-1-1 and doublets
3. Roll doublets

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| short-period natural frequency (SL) | 7.926 | 6.341 to 9.511 | rad/s | `p4.short_period_wn_sl` |
| short-period damping ratio (SL) | 0.6763 | 0.5411 to 0.8116 | - | `p4.short_period_zeta_sl` |
| Cm_alpha | -0.5462 | -0.6828 to -0.4097 | 1/rad | `p4.Cma_sl` |
| Cm_q | -8.921 | -11.15 to -6.691 | 1/rad | `p4.Cmq_sl` |
| Cm_delta_e | -0.02269 | -0.02836 to -0.01702 | 1/deg | `p4.Cmd02_sl` |
| Cl_p | -0.4384 | -0.548 to -0.3288 | 1/rad | `p4.Clp_sl` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** IMU, ATT, RCOU, ARSP
