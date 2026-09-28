"""ArduPlane starter parameters from StratoGlide predictions (NOT flight-tuned) + airspeed-sensor range check.

Names are validated against data/validation/apm.pdef.xml (autotest.ardupilot.org, retrieval date in MANIFEST.csv):
a name is valid if it appears as name="ArduPlane:NAME" (vehicle) or name="NAME" (library). Where ArduPlane
renamed a parameter, the variant present in the file is used. ArduPilot flies EAS (EAS2TAS converts), so every
airspeed below is EAS: stall is a constant EAS, and so is the flutter-limited VNE.
"""
from __future__ import annotations

import csv
import re

import numpy as np

from ..common import DATA, Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json

PDEF = DATA / "validation" / "apm.pdef.xml"
RHO0 = 1.225


def valid_names():
    txt = PDEF.read_text()
    veh = set(re.findall(r'name="ArduPlane:([A-Z0-9_]+)"', txt))
    lib = set(re.findall(r'name="([A-Z0-9_]+)"', txt))
    return veh | lib


def pick(names, *cands):
    for c in cands:
        if c in names:
            return c
    return cands[0]  # left in; check 20 will flag it


def sensor_check(q_min, v_min, q_vne):
    need_range = 1.2 * q_vne
    need_res = RHO0 * v_min * 0.1  # q change for 0.1 m/s at minimum EAS
    rows = []
    for s in load_cfg("components")["airspeed_sensors"]:
        res = s.get("resolution_pa") or 2 * s["range_pa"] / (s.get("span_frac", 1.0) * 2 ** s["bits"])
        rows.append({"name": s["name"], "range_pa": s["range_pa"], "resolution_pa": res, "range_ok": s["range_pa"] >= need_range,
                     "resolution_ok": res <= need_res, "source": s["source"]})
    return {"q_min_pa": q_min, "q_vne_pa": q_vne, "required_range_pa": need_range, "required_resolution_pa": need_res,
            "sensors": rows, "recommended": [r["name"] for r in rows if r["range_ok"] and r["resolution_ok"]]}


def main():
    names = valid_names()
    s = read_json(latest_phase_file("p3", "sizing.json"))
    pf = read_json(latest_phase_file("p7", "perf.json"))
    fl = read_json(latest_phase_file("p5", "flutter.json"))
    vs = s["vs_eas_sl"]
    v_min = float(np.ceil(1.2 * vs))
    v_cruise = round(float(pf["altitudes"]["19000"]["V_bestLD_eas"]) * 1.1, 1)
    vne = min(r["vne_eas"] for r in fl["vne"])
    v_max = float(np.floor(vne))
    sl = pf["altitudes"]["0"]
    pol = sl["polar"]
    W = s["mtow_kg"] * 9.80665
    climb = max(sl["excess_power_min_w"], 0.0) / W
    sink_vmax = float(np.interp(v_max, pol["Veas"], pol["sink"]))
    P = [  # (name candidates, value, comment)
        ((pick(names, "AIRSPEED_MIN", "ARSPD_FBW_MIN"),), v_min, "1.2 x stall EAS (P3)"),
        ((pick(names, "AIRSPEED_CRUISE", "TRIM_ARSPD_CM"),), v_cruise, "1.1 x best-L/D EAS at 19 km (P7)"),
        ((pick(names, "AIRSPEED_MAX", "ARSPD_FBW_MAX"),), v_max, "min over 0-25 km of VNE(h) = min(flutter-screen EAS / 1.2, Mach 0.5 as EAS) (P5)"),
        (("ARSPD_USE",), 1, "use airspeed for TECS and stall prevention"),
        (("ARSPD_TYPE",), 0, "PLACEHOLDER: set to the fitted sensor type (see sensor check)"),
        ((pick(names, "PTCH_LIM_MAX_DEG", "LIM_PITCH_MAX"),), 20, "generic starter"),
        ((pick(names, "PTCH_LIM_MIN_DEG", "LIM_PITCH_MIN"),), -25, "generic starter"),
        ((pick(names, "ROLL_LIMIT_DEG", "LIM_ROLL_CD"),), 45, "generic starter"),
        (("STALL_PREVENTION",), 1, "on"),
        (("TECS_CLMB_MAX",), round(min(climb, 5.0), 2), "SL full-power climb rate (P7 excess power / W), capped 5"),
        (("TECS_SINK_MIN",), round(sl["sink_min"], 2), "SL min sink (P7)"),
        (("TECS_SINK_MAX",), round(sink_vmax, 2), "SL sink at AIRSPEED_MAX (P7 polar)"),
        (("TECS_TIME_CONST",), 5.0, "default-class starter"),
        (("SERVO1_FUNCTION",), 4, "aileron"), (("SERVO2_FUNCTION",), 19, "elevator"),
        (("SERVO3_FUNCTION",), 70, "throttle"), (("SERVO4_FUNCTION",), 21, "rudder"),
        (("SERVO1_REVERSED",), 0, "PLACEHOLDER: set on the bench"), (("SERVO2_REVERSED",), 0, "PLACEHOLDER: set on the bench"),
        (("SERVO4_REVERSED",), 0, "PLACEHOLDER: set on the bench"),
        (("THR_MAX",), 100, "full throttle allowed; motor limits per P6"),
    ]
    lines = ["# StratoGlide ArduPlane starter parameters",
             "# starter values from StratoGlide predictions, NOT flight-tuned",
             f"# names checked against apm.pdef.xml ({PDEF.name}, retrieval date in data/validation/MANIFEST.csv)",
             "# all airspeeds are EAS (ArduPilot converts with EAS2TAS at altitude)"]
    rows = []
    for (nm,), val, com in P:
        ok = nm in names
        lines.append(f"{nm},{val}    # {com}")
        rows.append({"name": nm, "value": val, "comment": com, "in_pdef": ok})
    (OUTPUTS / "stratoglide_starter.param").write_text("\n".join(lines) + "\n")
    q_min = 0.5 * RHO0 * v_min ** 2
    q_vne = 0.5 * RHO0 * vne ** 2
    sc = sensor_check(q_min, v_min, q_vne)
    out = {"params": rows, "all_names_valid": all(r["in_pdef"] for r in rows), "sensor_check": sc,
           "q_loiter_20km_pa": 0.5 * RHO0 * float(pf["altitudes"]["20000"]["V_bestLD_eas"]) ** 2}
    write_json(phase_dir("p8") / "ardupilot.json", out)
    n = Numbers("p8", "src/stratoglide/build/ardupilot_params.py")
    n.add("airspeed_min_eas", v_min, "m/s"); n.add("airspeed_cruise_eas", v_cruise, "m/s"); n.add("airspeed_max_eas", v_max, "m/s")
    n.add("sensor_required_range_pa", sc["required_range_pa"], "Pa"); n.add("sensor_required_resolution_pa", sc["required_resolution_pa"], "Pa")
    n.add("n_params", len(rows)); n.add("n_params_invalid", sum(not r["in_pdef"] for r in rows))
    n.save()
    print("invalid", [r["name"] for r in rows if not r["in_pdef"]], "sensor ok", sc["recommended"], "req", round(sc["required_range_pa"]), round(sc["required_resolution_pa"], 2))


if __name__ == "__main__":
    main()
