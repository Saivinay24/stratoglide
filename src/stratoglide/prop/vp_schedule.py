"""P6 design study: fixed pitch A (19 km loiter), fixed pitch B (sea-level test cruise), variable pitch (same
blade as A, collective schedule per altitude). Motor pick from the catalog (QPROP-style Kv, Rm, I0).

Flight condition at every altitude: level flight at the loiter CL (constant EAS), thrust = W / (L/D)_loiter
from P3 (drag Re-dependence across altitude neglected, logged). Climb sizing point: 0.5 m/s at 20 km.
Physics note: at constant EAS, rho V^2 is constant, so the required CT/J^2 is identical at every altitude.
Fixed pitch with free RPM therefore loses only through blade Re (falls ~sqrt(sigma)) and helical tip Mach
(rises ~1/sqrt(sigma)). The VP gain reported here is exactly that, not a density-ratio argument.
Blade: two blades, APC 10x7 c/R distribution scaled to D, helical twist beta = atan(P / (2 pi r)).
Sea-level test cruise (B design point) is defined as SL level flight at the loiter CL.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from ..atmos import isa
from ..common import DATA, Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from . import bemt
from .section import Section

ALTS = [0.0, 3000.0, 5000.0, 10000.0, 15000.0, 18000.0, 19000.0, 20000.0]
G0 = 9.80665


def blade(D, pitch_m):
    base = bemt.load_geom(DATA / "validation" / "props" / "apce_10x7_geom.txt")
    rr = base["rR"] * D / 2
    return {"rR": base["rR"], "cR": base["cR"], "beta": np.degrees(np.arctan(pitch_m / (2 * np.pi * rr)))}


def at_thrust(sec, geom, D, V, T_req, z, dbeta=0.0):
    """RPM that produces T_req; returns the BEMT result or None."""
    f = lambda rpm: bemt.solve(sec, geom, D, 2, rpm, V, z=z, dbeta=dbeta)["T"] - T_req
    lo, hi = 300.0, 40000.0
    try:
        if f(lo) > 0 or f(hi) < 0:
            return None
        rpm = brentq(f, lo, hi, xtol=0.5)
    except ValueError:
        return None
    r = bemt.solve(sec, geom, D, 2, rpm, V, z=z, dbeta=dbeta)
    r["rpm"] = rpm
    return r


def flight(s, z, climb=0.0):
    W = s["mtow_kg"] * G0
    rho = isa(z)["rho"]
    V = float(np.sqrt(2 * W / (rho * s["S_m2"] * s["cl_loiter"])))
    return V, W / s["ld_loiter"] + W * climb / V


def best_pitch(sec, D, s, z):
    V, T = flight(s, z)

    def neg(pd):
        r = at_thrust(sec, blade(D, pd * D), D, V, T, z)
        return -(r["eta"] if r else 0.0)
    o = minimize_scalar(neg, bounds=(0.3, 2.2), method="bounded", options={"xatol": 1e-3})
    return o.x, -o.fun


def vp_point(sec, geom, D, V, T, z):
    """Global over collective: 1-deg grid scan on [-15, 20] deg, then bounded refine around the best cell.
    dbeta = 0 (the fixed-pitch blade A itself) is always a candidate."""
    def eta(db):
        r = at_thrust(sec, geom, D, V, T, z, dbeta=db)
        return r["eta"] if r else 0.0
    grid = np.arange(-15.0, 20.01, 1.0)
    vals = [eta(db) for db in grid]
    k = int(np.argmax(vals))
    o = minimize_scalar(lambda db: -eta(db), bounds=(grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]),
                        method="bounded", options={"xatol": 0.02})
    cands = [(0.0, eta(0.0)), (grid[k], vals[k]), (o.x, -o.fun)]
    db = max(cands, key=lambda c: c[1])[0]
    return float(db), at_thrust(sec, geom, D, V, T, z, dbeta=db)


def motor_point(m, Q, rpm, v_pack):
    kv = m["kv_rpm_per_v"] * 2 * np.pi / 60
    w = rpm * 2 * np.pi / 60
    I = Q * kv + m["i0_a"]
    V = I * m["rm_ohm"] + w / kv
    return {"I": I, "V": V, "P_elec": V * I, "eta_m": Q * w / (V * I), "feasible_v": V <= v_pack}


def main():
    s = read_json(latest_phase_file("p3", "sizing.json"))
    val = read_json(latest_phase_file("p6", "prop_validation.json"))
    comp = load_cfg("components")
    sz = load_cfg("sizing")
    sec = Section(val["section"], val["section_tc"])
    # diameter trade for fixed pitch A at 19 km
    dtrade = {}
    for D in (0.30, 0.35, 0.40, 0.45):
        pd, eta = best_pitch(sec, D, s, 19000.0)
        m_prop = comp["propeller"]["areal_mass_kg_per_m2_disk"] * np.pi * D ** 2 / 4 + comp["propeller"]["hub_kg"]
        dtrade[D] = {"pitch_over_D": pd, "eta_19km": eta, "prop_mass_kg": m_prop}
        print("D", D, "P/D", round(pd, 3), "eta19", round(eta, 4), flush=True)
    D = max(dtrade, key=lambda k: (round(dtrade[k]["eta_19km"], 3), -k))
    pdA = dtrade[D]["pitch_over_D"]
    pdB, _ = best_pitch(sec, D, s, 0.0)
    gA, gB = blade(D, pdA * D), blade(D, pdB * D)
    table = []
    for z in ALTS:
        V, T = flight(s, z)
        rA = at_thrust(sec, gA, D, V, T, z)
        rB = at_thrust(sec, gB, D, V, T, z)
        db, rV = vp_point(sec, gA, D, V, T, z)
        row = {"z_m": z, "V_tas": V, "T_N": T, "eta_A": rA["eta"] if rA else 0.0, "eta_B": rB["eta"] if rB else 0.0,
               "eta_VP": rV["eta"] if rV else 0.0, "vp_dbeta_deg": db, "rpm_A": rA and rA["rpm"], "rpm_VP": rV and rV["rpm"],
               "Q_A": rA and rA["Q"], "Q_VP": rV and rV["Q"], "re75_A": rA and rA["re75"], "mach_tip_A": rA and rA["mach_tip"],
               "mach_tip_B": rB and rB["mach_tip"], "J_A": rA and rA["J"]}
        table.append(row)
        print(f"z {z/1000:4.0f} km V {V:5.1f} T {T:.2f} eta A {row['eta_A']:.4f} B {row['eta_B']:.4f} VP {row['eta_VP']:.4f} "
              f"dbeta {db:+.2f} re75 {row['re75_A'] or 0:.0f} Mtip A {row['mach_tip_A'] or 0:.3f}", flush=True)
    gain_A = [(100 * (r["eta_VP"] - r["eta_A"]), r["z_m"]) for r in table]
    gain_B = [(100 * (r["eta_VP"] - r["eta_B"]), r["z_m"]) for r in table]
    band = [r for r in table if 3000 <= r["z_m"] <= 15000]
    # climb sizing point (20 km, 0.5 m/s) with the fixed-pitch A blade
    Vc, Tc = flight(s, 20000.0, load_cfg("mission")["loiter"]["climb_rate_mps"])
    rc = at_thrust(sec, gA, D, Vc, Tc, 20000.0)
    loiter = next(r for r in table if r["z_m"] == 19000.0)
    v_cell = comp["battery_cell"]["v_nom"]
    v_pack = sz["pack_series"] * v_cell * 0.9  # loaded-voltage allowance, ESTIMATE
    motors = []
    for m in comp["motors"]:
        lo = motor_point(m, loiter["Q_A"], loiter["rpm_A"], v_pack)
        cl = motor_point(m, rc["Q"], rc["rpm"], v_pack) if rc else None
        ok = lo["feasible_v"] and cl is not None and cl["feasible_v"] and cl["P_elec"] <= m["p_max_w"]
        motors.append({"name": m["name"], "mass_kg": m["mass_kg"], "loiter": lo, "climb": cl, "feasible": bool(ok),
                       "source": m["source"]})
    feas = [m for m in motors if m["feasible"]]
    pick = min(feas, key=lambda m: m["loiter"]["P_elec"]) if feas else None
    out = {"section": val["section"], "diameter_trade": {str(k): v for k, v in dtrade.items()},
           "design": {"diameter_m": D, "pitch_over_D_A": pdA, "pitch_over_D_B": pdB, "blades": 2,
                      "eta_loiter_19km": loiter["eta_A"], "prop_mass_kg": dtrade[D]["prop_mass_kg"],
                      "rpm_loiter": loiter["rpm_A"], "torque_loiter_nm": loiter["Q_A"], "re75_20km": table[-1]["re75_A"],
                      "mach_tip_19km": loiter["mach_tip_A"], "climb_20km": rc and {k: rc[k] for k in ("rpm", "Q", "P", "eta", "mach_tip")}},
           "table": table, "vp_gain_vs_A_points": gain_A, "vp_gain_vs_B_points": gain_B,
           "vp_gain_eta_points_max": max(gain_A), "vp_gain_vs_B_max": max(gain_B),
           "band_3_15km_gain_vs_A_max": max(100 * (r["eta_VP"] - r["eta_A"]) for r in band),
           "v_pack_loaded": v_pack, "motors": motors,
           "motor": pick and {"name": pick["name"], "mass_kg": pick["mass_kg"], "eta_motor_loiter": pick["loiter"]["eta_m"],
                              "P_elec_loiter_w": pick["loiter"]["P_elec"], "P_elec_climb_w": pick["climb"]["P_elec"],
                              "V_loiter": pick["loiter"]["V"], "source": pick["source"]},
           "notes": ["winding temperature at low rho not modelled (GAPS)", "section stand-in from prop_validation calibration"]}
    if pick is None:
        out["motor"] = {"name": None, "error": "no catalog motor feasible at pack voltage and climb power"}
    write_json(phase_dir("p6") / "prop.json", out)
    _plot(out)
    n = Numbers("p6", "src/stratoglide/prop/vp_schedule.py")
    n.add("prop_diameter_m", D, "m")
    n.add("prop_pitch_over_D_A", pdA)
    n.add("prop_pitch_over_D_B", pdB)
    n.add("eta_prop_loiter_19km", loiter["eta_A"])
    n.add("vp_gain_eta_points_max", max(gain_A)[0], "eta points", note=f"vs fixed pitch A, at {max(gain_A)[1]:.0f} m")
    n.add("vp_gain_eta_points_max_alt_m", max(gain_A)[1], "m")
    n.add("vp_gain_vs_B_max", max(gain_B)[0], "eta points", note=f"vs fixed pitch B, at {max(gain_B)[1]:.0f} m")
    n.add("vp_gain_vs_B_max_alt_m", max(gain_B)[1], "m")
    n.add("band_3_15km_gain_vs_A_max", out["band_3_15km_gain_vs_A_max"], "eta points")
    n.add("re75_20km", table[-1]["re75_A"])
    n.add("mach_tip_19km", loiter["mach_tip_A"])
    n.add("rpm_loiter", loiter["rpm_A"], "rpm")
    for r in table:
        k = f"{r['z_m']/1000:.0f}km"
        n.add(f"eta_A_{k}", r["eta_A"]); n.add(f"eta_B_{k}", r["eta_B"]); n.add(f"eta_VP_{k}", r["eta_VP"])
        n.add(f"vp_dbeta_deg_{k}", r["vp_dbeta_deg"], "deg")
    if pick:
        n.add("motor_eta_loiter", pick["loiter"]["eta_m"])
        n.add("motor_mass_kg", pick["mass_kg"], "kg", note=pick["name"])
        n.add("motor_p_elec_loiter_w", pick["loiter"]["P_elec"], "W")
    n.save()
    print("D", D, "A P/D", round(pdA, 3), "B P/D", round(pdB, 3), "gain vs A max", max(gain_A), "vs B max", max(gain_B),
          "motor", out["motor"].get("name"), out["motor"].get("eta_motor_loiter"))


def _plot(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = out["table"]
    z = [r["z_m"] / 1000 for r in t]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.plot(z, [r["eta_A"] for r in t], "o-", label=f"fixed pitch A (19 km), P/D {out['design']['pitch_over_D_A']:.2f}")
    ax.plot(z, [r["eta_B"] for r in t], "s-", label=f"fixed pitch B (SL), P/D {out['design']['pitch_over_D_B']:.2f}")
    ax.plot(z, [r["eta_VP"] for r in t], "^-", label="variable pitch (blade A + collective)")
    ax.axvspan(3, 15, color="#FED176", alpha=0.15, label="3-15 km band")
    ax.set_xlabel("altitude (km), level flight at loiter CL")
    ax.set_ylabel("propeller efficiency")
    ax.set_title(f"BEMT, D = {out['design']['diameter_m']:.2f} m, section {out['section']}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUTS / "p6_eta_vs_alt.png", dpi=130)


if __name__ == "__main__":
    main()
