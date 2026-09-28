"""Flight-test cards FT-1..FT-6 (markdown) + predictions.json (the contract with FlightLoop) + JSON schema.

Every predicted value is a numbers.json key (merged results/numbers.json, written by collect_numbers). Bands follow
declared rules: aero performance +/-10%, stall EAS +/-5%, static margin +/-3% MAC, dynamic-mode values +/-20%,
derivatives +/-25% (AVL is linear inviscid); drop cards use the P5-P95 band of a 100-sample Monte Carlo at the drop
altitude (same LHS ranges as P5, autopilot).
Regulatory note on every card: drops need DGCA Digital Sky / airspace permission; out of scope here.
"""
from __future__ import annotations

import json

import numpy as np

from ..common import Numbers, OUTPUTS, ROOT, RESULTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from ..release import montecarlo as mcmod, sim6dof as sd

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "StratoGlide flight-test predictions",
    "type": "array",
    "items": {"type": "object", "additionalProperties": False,
              "required": ["card", "quantity", "value", "unit", "band_lo", "band_hi", "source_script", "numbers_key"],
              "properties": {"card": {"type": "string", "pattern": "^FT-[1-6]$"}, "quantity": {"type": "string"},
                             "value": {"type": "number"}, "unit": {"type": "string"}, "band_lo": {"type": "number"},
                             "band_hi": {"type": "number"}, "source_script": {"type": "string"},
                             "numbers_key": {"type": "string"}}}}
REG = "Regulatory: any drop or BVLOS flight needs DGCA Digital Sky and airspace permission; that is out of scope here."
ABORT = ["loss of telemetry > 5 s", "airspeed below AIRSPEED_MIN in powered phases", "battery voltage below 3.3 V/cell",
         "uncommanded oscillation", "any structural noise or flutter cue (abort and slow down)"]


def drop_mc(z0_agl, N=100):
    m = load_cfg("mission")
    z0 = z0_agl + m["recovery_site_elev_m"]
    p, X0, wind, s, _ = mcmod.build(N, z0=z0)
    r = sd.run(p, X0, wind, t_end=120.0, dt=0.01, mode="autopilot", record_every=100)
    loss = z0 - r["z_rec"]
    st = r["stats"]

    def b(x):
        x = x[np.isfinite(x)]
        return float(np.percentile(x, 50)), float(np.percentile(x, 5)), float(np.percentile(x, 95))
    return {"z0_m": z0, "recovery_rate": float(r["recovered"].mean()), "alt_lost": b(loss), "nz": b(st["nz"]),
            "eas": b(st["eas"]), "t_rec": b(r["t_rec"])}


def main():
    n_all = read_json(RESULTS / "numbers.json")["numbers"]
    g = lambda k: n_all[k]["value"]
    nb = Numbers("p8", "src/stratoglide/build/test_cards.py")
    d5, d6 = drop_mc(2000.0), drop_mc(10000.0)
    for tag, d in (("ft5", d5), ("ft6", d6)):
        nb.add(f"{tag}_recovery_rate", d["recovery_rate"])
        for q, u in (("alt_lost", "m"), ("nz", "g"), ("eas", "m/s"), ("t_rec", "s")):
            v, lo, hi = d[q]
            nb.add(f"{tag}_{q}_p50", v, u); nb.add(f"{tag}_{q}_p05", lo, u); nb.add(f"{tag}_{q}_p95", hi, u)
    # FT-3 trim gradient from AVL: d(delta_e)/dCL = -(Cma/CLa)/Cm_de  [deg per unit CL]
    dde_dcl = -(g("p4.Cma_sl") / g("p4.CLa_sl")) / g("p4.Cmd02_sl")
    nb.add("ft3_dde_dcl_deg", dde_dcl, "deg/CL")
    # FT-2 cruise electrical power at SL (loiter CL) and RPM
    p6 = read_json(latest_phase_file("p6", "prop.json"))
    sl6 = next(r for r in p6["table"] if r["z_m"] == 0.0)
    eta_esc = load_cfg("sizing")["propulsion_initial"]["eta_esc"]
    pf = read_json(latest_phase_file("p7", "perf.json"))
    P_sl = sl6["T_N"] * sl6["V_tas"] / (sl6["eta_A"] * p6["motor"]["eta_motor_loiter"] * eta_esc)
    nb.add("ft2_p_elec_cruise_w", P_sl, "W"); nb.add("ft2_rpm_cruise", sl6["rpm_A"], "rpm")
    W = g("p3.mtow_kg") * 9.80665
    nb.add("ft2_climb_rate_full_power", pf["altitudes"]["0"]["excess_power_min_w"] / W, "m/s")
    nb.save()
    nk = {**n_all, **{k: v for k, v in read_json(latest_phase_file("p8", "numbers.json")).items()}}
    gv = lambda k: nk[k]["value"]

    def pred(card, q, key, unit, band=None, lo_key=None, hi_key=None):
        v = float(gv(key))
        if lo_key:
            lo, hi = float(gv(lo_key)), float(gv(hi_key))
        else:
            lo, hi = sorted([v * (1 - band), v * (1 + band)])
        return {"card": card, "quantity": q, "value": v, "unit": unit, "band_lo": lo, "band_hi": hi,
                "source_script": nk[key]["script"], "numbers_key": key}
    P = [pred("FT-1", "stall EAS", "p3.vs_eas_sl", "m/s", 0.05),
         pred("FT-1", "V_bestLD EAS (SL)", "p7.V_bestLD_eas_0km", "m/s", 0.10),
         pred("FT-1", "L/D max (SL)", "p7.LD_max_0km", "-", 0.10),
         pred("FT-1", "min sink rate (SL)", "p7.sink_min_0km", "m/s", 0.10),
         pred("FT-1", "trim elevator at loiter CL (SL)", "p4.trim_elevator_deg_sl", "deg", 0.25),
         pred("FT-1", "static margin", "p4.sm_pct_sl", "%MAC", None, None, None) if False else
         {"card": "FT-1", "quantity": "static margin", "value": float(gv("p4.sm_pct_sl")), "unit": "%MAC",
          "band_lo": float(gv("p4.sm_pct_sl")) - 3, "band_hi": float(gv("p4.sm_pct_sl")) + 3,
          "source_script": nk["p4.sm_pct_sl"]["script"], "numbers_key": "p4.sm_pct_sl"},
         pred("FT-2", "electrical power at SL cruise (loiter CL)", "p8.ft2_p_elec_cruise_w", "W", 0.10),
         pred("FT-2", "climb rate at full power (SL)", "p8.ft2_climb_rate_full_power", "m/s", 0.10),
         pred("FT-2", "RPM at SL cruise", "p8.ft2_rpm_cruise", "rpm", 0.10),
         pred("FT-3", "trim gradient d(delta_e)/dCL", "p8.ft3_dde_dcl_deg", "deg/CL", 0.25),
         pred("FT-3", "neutral point x (from wing root LE)", "p4.x_np_m", "m", 0.05),
         pred("FT-4", "short-period natural frequency (SL)", "p4.short_period_wn_sl", "rad/s", 0.20),
         pred("FT-4", "short-period damping ratio (SL)", "p4.short_period_zeta_sl", "-", 0.20),
         pred("FT-4", "Cm_alpha", "p4.Cma_sl", "1/rad", 0.25),
         pred("FT-4", "Cm_q", "p4.Cmq_sl", "1/rad", 0.25),
         pred("FT-4", "Cm_delta_e", "p4.Cmd02_sl", "1/deg", 0.25),
         pred("FT-4", "Cl_p", "p4.Clp_sl", "1/rad", 0.25)]
    for card, tag in (("FT-5", "ft5"), ("FT-6", "ft6")):
        for q, u, nm in (("alt_lost", "m", "altitude lost in pull-out"), ("nz", "g", "peak load factor"),
                         ("eas", "m/s", "peak EAS"), ("t_rec", "s", "time to recover")):
            P.append(pred(card, nm, f"p8.{tag}_{q}_p50", u, lo_key=f"p8.{tag}_{q}_p05", hi_key=f"p8.{tag}_{q}_p95"))
    import jsonschema
    jsonschema.validate(P, SCHEMA)
    tc = OUTPUTS / "test_cards"
    tc.mkdir(parents=True, exist_ok=True)
    (ROOT / "schemas").mkdir(exist_ok=True)
    (ROOT / "schemas" / "predictions.schema.json").write_text(json.dumps(SCHEMA, indent=2) + "\n")
    (tc / "predictions.json").write_text(json.dumps(P, indent=2) + "\n")
    meta = {
        "FT-1": ("Sea-level hand-launch glide, ballasted to MTOW, motor off",
                 ["Ballast to MTOW and CG per wb.csv", "Hand launch into wind at or above 1.3 x stall EAS",
                  "Hold pitch for steady glides at 4-5 airspeeds", "Note trim elevator at each airspeed"],
                 ["ARSP", "BARO", "GPS", "ATT", "RCOU"]),
        "FT-2": ("Sea-level powered cruise and climb", ["Level cruise at loiter CL EAS for 60 s", "Full-power climb for 30 s"],
                 ["BAT", "ESC", "ARSP", "BARO", "RCOU"]),
        "FT-3": ("Trim-gradient static margin check", ["Trim at 3 airspeeds per CG", "Repeat at 2 CG positions",
                                                       "Extrapolate d(delta_e)/dCL to zero for NP"], ["ARSP", "RCOU", "ATT", "IMU"]),
        "FT-4": ("2-1-1 and doublet inputs (sysID for FlightLoop)", ["Trimmed level flight", "Pitch 2-1-1 and doublets",
                                                                     "Roll doublets"], ["IMU", "ATT", "RCOU", "ARSP"]),
        "FT-5": ("Low balloon drop (2 km AGL)", ["Release from tethered or free balloon at 2 km AGL",
                                                 "Autopilot pull-out armed, log until steady glide", "Chute at 1.5 km AGL is NOT used on this card; glide down"],
                 ["IMU", "ATT", "ARSP", "BARO", "GPS"]),
        "FT-6": ("Future: 10 km drop", ["As FT-5 at 10 km", "Only after FT-5 matches predictions inside bands"],
                 ["IMU", "ATT", "ARSP", "BARO", "GPS"])}
    for card, (title, proc, logs) in meta.items():
        rows = [p for p in P if p["card"] == card]
        md = [f"# {card}: {title}", "", "**Objective:** compare measured values with the predictions below.", "",
              f"**Preconditions:** airworthiness inspection done; starter params loaded (outputs/stratoglide_starter.param); "
              f"weather inside limits. {REG}", "",
              f"**Config:** MTOW {gv('p3.mtow_kg'):.3f} kg, CG x {gv('p4.x_cg_m'):.4f} m from wing root LE "
              f"(static margin {gv('p4.sm_pct_sl'):.2f}% MAC).", "", "**Procedure:**", ""]
        md += [f"{i + 1}. {s}" for i, s in enumerate(proc)]
        md += ["", "**Predicted values (band):**", "", "| Quantity | Predicted | Band | Unit | numbers.json key |", "|---|---|---|---|---|"]
        md += [f"| {p['quantity']} | {p['value']:.4g} | {p['band_lo']:.4g} to {p['band_hi']:.4g} | {p['unit']} | `{p['numbers_key']}` |" for p in rows]
        md += ["", "**Abort criteria:**", ""] + [f"- {a}" for a in ABORT]
        md += ["", "**Data to log (ArduPilot DataFlash):** " + ", ".join(logs)]
        (tc / f"{card}.md").write_text("\n".join(md) + "\n")
    write_json(phase_dir("p8") / "test_cards.json", {"n_predictions": len(P), "ft5": d5, "ft6": d6})
    print("predictions", len(P), "FT-5", d5["recovery_rate"], d5["alt_lost"], "FT-6", d6["recovery_rate"], d6["alt_lost"])


if __name__ == "__main__":
    main()
