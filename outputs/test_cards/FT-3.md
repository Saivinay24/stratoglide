# FT-3: Trim-gradient static margin check

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. Trim at 3 airspeeds per CG
2. Repeat at 2 CG positions
3. Extrapolate d(delta_e)/dCL to zero for NP

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| trim gradient d(delta_e)/dCL | -5.065 | -6.331 to -3.799 | deg/CL | `p8.ft3_dde_dcl_deg` |
| neutral point x (from wing root LE) | 0.1584 | 0.1505 to 0.1664 | m | `p4.x_np_m` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** ARSP, RCOU, ATT, IMU
