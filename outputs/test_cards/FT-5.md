# FT-5: Low balloon drop (2 km AGL)

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. Release from tethered or free balloon at 2 km AGL
2. Autopilot pull-out armed, log until steady glide
3. Chute at 1.5 km AGL is NOT used on this card; glide down

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| altitude lost in pull-out | 40.45 | 27.47 to 69.28 | m | `p8.ft5_alt_lost_p50` |
| peak load factor | 2.003 | 1.777 to 2.302 | g | `p8.ft5_nz_p50` |
| peak EAS | 21.39 | 18.49 to 23.86 | m/s | `p8.ft5_eas_p50` |
| time to recover | 11.27 | 7.307 to 19.66 | s | `p8.ft5_t_rec_p50` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** IMU, ATT, ARSP, BARO, GPS
