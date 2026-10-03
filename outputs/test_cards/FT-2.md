# FT-2: Sea-level powered cruise and climb

**Objective:** compare measured values with the predictions below.

**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); weather inside limits. Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here.

**Config:** MTOW 3.760 kg, CG x 0.1268 m from wing root LE (static margin 11.49% MAC).

**Procedure:**

1. Level cruise at loiter CL EAS for 60 s
2. Full-power climb for 30 s

**Predicted values (band):**

| Quantity | Predicted | Band | Unit | numbers.json key |
|---|---|---|---|---|
| electrical power at SL cruise (loiter CL) | 90.43 | 81.38 to 99.47 | W | `p8.ft2_p_elec_cruise_w` |
| climb rate at full power (SL) | 11.03 | 9.931 to 12.14 | m/s | `p8.ft2_climb_rate_full_power` |
| RPM at SL cruise | 1983 | 1785 to 2182 | rpm | `p8.ft2_rpm_cruise` |

**Abort criteria:**

- loss of telemetry > 5 s
- airspeed below AIRSPEED_MIN in powered phases
- battery voltage below 3.3 V/cell
- uncommanded oscillation
- any structural noise or flutter cue (abort and slow down)

**Data to log (ArduPilot DataFlash):** BAT, ESC, ARSP, BARO, RCOU
