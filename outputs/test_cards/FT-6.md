# FT-6: Future: 10 km drop

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. As FT-5 at 10 km
2. Only after FT-5 matches predictions inside bands

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| altitude lost in pull-out | 90.17 | 59.72 to 170.8 | m | `p8.ft6_alt_lost_p50` |
| peak load factor | 2.265 | 2.101 to 2.521 | g | `p8.ft6_nz_p50` |
| peak EAS | 21.03 | 18.14 to 23.83 | m/s | `p8.ft6_eas_p50` |
| time to recover | 15.81 | 9.957 to 30.62 | s | `p8.ft6_t_rec_p50` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** IMU, ATT, ARSP, BARO, GPS
