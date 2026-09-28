# FT-1: Sea-level hand-launch glide, ballasted to MTOW, motor off

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. Ballast to MTOW and CG per wb.csv
2. Hand launch into wind at or above 1.3 x stall EAS
3. Hold pitch for steady glides at 4-5 airspeeds
4. Note trim elevator at each airspeed

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| stall EAS | 11 | 10.45 to 11.55 | m/s | `p3.vs_eas_sl` |
| V_bestLD EAS (SL) | 14.13 | 12.72 to 15.54 | m/s | `p7.V_bestLD_eas_0km` |
| L/D max (SL) | 11.9 | 10.71 to 13.09 | - | `p7.LD_max_0km` |
| min sink rate (SL) | 1.08 | 0.9722 to 1.188 | m/s | `p7.sink_min_0km` |
| trim elevator at loiter CL (SL) | -1.705 | -2.132 to -1.279 | deg | `p4.trim_elevator_deg_sl` |
| static margin | 11.49 | 8.491 to 14.49 | %MAC | `p4.sm_pct_sl` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** ARSP, BARO, GPS, ATT, RCOU
