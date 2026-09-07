"""P3 driver: grid sweep + AeroSandbox Opti on the same model, final closure, thermal, geometry, W&B, plots.

  uv run python -m stratoglide.sizing.run_sizing            # uses P6 prop.json if present (re-run after P6)
"""
from __future__ import annotations

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..atmos import RHO0, isa
from ..common import Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from . import battery_thermal as bt
from . import geometry as geom
from . import wb
from .model import G, SizingModel


def prop_override():
    try:
        p = read_json(latest_phase_file("p6", "prop.json"))
    except FileNotFoundError:
        return {}, False
    o = {"eta_prop_loiter": p["design"]["eta_loiter_19km"], "eta_motor": p["motor"]["eta_motor_loiter"],
         "motor_mass_kg": p["motor"]["mass_kg"], "prop_mass_kg": p["design"]["prop_mass_kg"],
         "prop_diameter_m": p["design"]["diameter_m"]}
    try:
        st = read_json(latest_phase_file("p4", "stability.json"))
        o["oswald_e"] = st["avl_span_efficiency"]
    except (FileNotFoundError, KeyError):
        pass
    return o, True


def grid_sweep(M: SizingModel):
    b = M.ds["sizing"]["bounds"]
    gn = M.ds["sizing"]["grid_n"]
    S = np.linspace(*b["S_m2"], gn["S"])
    AR = np.linspace(*b["AR"], gn["AR"])
    CL = np.linspace(*b["CL_loiter"], gn["CL"])
    SS, AA, CC = np.meshgrid(S, AR, CL, indexing="ij")
    m = np.full(SS.shape, 6.0)
    for _ in range(60):
        r = M.evaluate(SS, AA, CC, m)
        m_new = r["m_sum"]
        if np.nanmax(np.abs(m_new - m) / m) < 1e-6:
            m = m_new
            break
        m = m_new
    r = M.evaluate(SS, AA, CC, m)
    feas = np.ones(SS.shape, bool)
    for k, v in r["cons"].items():
        feas &= v <= 0
    feas &= np.isfinite(m)
    out = {"n_points": int(SS.size), "n_feasible": int(feas.sum())}
    if feas.any():
        mm = np.where(feas, m, np.inf)
        i = np.unravel_index(int(np.argmin(mm)), mm.shape)
        out.update({"S": float(SS[i]), "AR": float(AA[i]), "CL": float(CC[i]), "mtow": float(m[i])})
    # strict MR-9 demonstration: max loiter Re reachable under every other constraint
    feas_other = np.ones(SS.shape, bool)
    for k, v in r["cons"].items():
        if k != "re_floor":
            feas_other &= v <= 0
    re_ = np.where(feas_other, r["loiter"]["re"], -np.inf)
    j = np.unravel_index(int(np.argmax(re_)), re_.shape)
    out["max_re_other_constraints"] = float(re_[j])
    out["max_re_point"] = {"S": float(SS[j]), "AR": float(AA[j]), "CL": float(CC[j]), "mtow": float(m[j])}
    out["_arrays"] = (SS, AA, CC, m, feas, r)
    return out


def opti(M: SizingModel, guess=(1.0, 10.0, 0.7, 6.0), n_cells_fixed=None, E_heat=None):
    import aerosandbox as asb
    import aerosandbox.numpy as anp
    b = M.ds["sizing"]["bounds"]
    o = asb.Opti()
    S = o.variable(init_guess=guess[0], lower_bound=b["S_m2"][0], upper_bound=b["S_m2"][1])
    AR = o.variable(init_guess=guess[1], lower_bound=b["AR"][0], upper_bound=b["AR"][1])
    CL = o.variable(init_guess=guess[2], lower_bound=b["CL_loiter"][0], upper_bound=b["CL_loiter"][1])
    mt = o.variable(init_guess=guess[3], lower_bound=1.0, upper_bound=40.0)
    r = M.evaluate(S, AR, CL, mt, np=anp, n_cells_fixed=n_cells_fixed, E_heat_override=E_heat)
    o.subject_to(mt == r["m_sum"])
    for k, v in r["cons"].items():
        o.subject_to(v <= 0)
    o.minimize(mt)
    try:
        sol = o.solve(verbose=False)
        return {"S": float(sol(S)), "AR": float(sol(AR)), "CL": float(sol(CL)), "mtow": float(sol(mt)), "status": "solved"}
    except Exception as e:  # report, never hide
        return {"status": f"failed: {type(e).__name__}: {str(e)[:200]}"}


def close_final(M, S, AR, CL, m0):
    """Integer cells (multiple of pack_series) + transient heater energy. For each candidate pack the planform
    is RE-OPTIMISED (Opti, same model) with the pack fixed and an explicit usable-energy constraint, so the
    final design satisfies every constraint after rounding. Loop until pack and heater energy are stable."""
    ns = M.s["pack_series"]
    E_heat = None
    r = M.evaluate(S, AR, CL, m0)
    n_int = int(ns * math.ceil(float(r["energy"]["n_cells_cont"]) / ns - 1e-9))
    guess = (S, AR, CL, m0)
    for it in range(12):
        op = opti(M, guess, n_cells_fixed=n_int, E_heat=E_heat)
        if op["status"] != "solved":
            n_int += ns
            continue
        S, AR, CL, m = op["S"], op["AR"], op["CL"], op["mtow"]
        r = M.evaluate(S, AR, CL, m, n_cells_fixed=n_int, E_heat_override=E_heat)
        en = r["energy"]
        p_base = M.m["avionics"]["power_w"] + M.m["payload"]["standby_power_w"]
        th = bt.simulate(n_int, en["P_loiter_elec_w"] + M.m["payload"]["power_w"] - M.m["payload"]["standby_power_w"]
                         + M.m["avionics"]["servo_power_w"], p_base, en["t_ascent_s"], en["t_release_glide_s"],
                         en["t_loiter_s"], en["t_descent_s"])
        stable = E_heat is not None and abs(th["E_heater_wh"] - E_heat) < 1e-3
        E_heat = th["E_heater_wh"]
        guess = (S, AR, CL, m)
        if stable:
            break
    # mass-loop residual at the final point (check 8)
    r = M.evaluate(S, AR, CL, m, n_cells_fixed=n_int, E_heat_override=E_heat)
    return m, n_int, r, th, it, (S, AR, CL)


def constraint_plot(M, S, AR, CL, m, r, path):
    W = m * G
    lo = M.atm["loiter"]
    ws = np.linspace(20, 160, 300)
    Sx = W / ws
    pw_loiter, pw_climb = [], []
    for Si in Sx:
        f = M.evaluate(Si, AR, CL, m)
        pw_loiter.append(float(f["energy"]["P_loiter_shaft_w"]) / W)
        pw_climb.append(float(f["energy"]["P_max_shaft_w"]) / 1.2 / W)
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    ax.plot(ws, pw_loiter, color="#FED176", lw=2.2, label="loiter power, 19 km (shaft)")
    ax.plot(ws, pw_climb, color="#7aa2f7", lw=1.8, label="climb 0.5 m/s at 20 km (shaft)")
    ws_stall = 0.5 * RHO0 * M.m["handlaunch"]["stall_eas_max_mps"] ** 2 * M.clmax3d
    ax.axvline(ws_stall, color="#f7768e", lw=1.8, label=f"MR-8 stall <= 11 m/s EAS")
    mac = r["geo"]["mac"]
    ws_re = (M.re_floor * lo["mu"] / mac) ** 2 * CL / (2 * lo["rho"])
    ax.axvline(ws_re, color="#9ece6a", lw=1.8, ls="--", label=f"Re >= {M.re_floor/1e3:.0f}k at loiter (D1 floor)")
    ws_re300 = (M.re_min_validated * lo["mu"] / mac) ** 2 * CL / (2 * lo["rho"])
    if ws_re300 < 400:
        ax.axvline(ws_re300, color="#9ece6a", lw=1.0, ls=":", label=f"Re >= {M.re_min_validated/1e3:.0f}k (strict MR-9)")
    clbl = float(r["cl_bestld"])
    vw = M.ds["sizing"]["wind_penetration_factor"] * M.w95_loiter
    ws_wind = 0.5 * lo["rho"] * vw ** 2 * clbl
    ax.axvline(ws_wind, color="#bb9af7", lw=1.5, ls="-.", label="wind penetration 1.25 x P95")
    rel = M.atm["rel"]
    ws_po = G * M.ds["sizing"]["pullout_alt_budget_m"] * rel["rho"] * M.clmax3d
    if ws_po < 160:
        ax.axvline(ws_po, color="#e0af68", lw=1.2, label="pull-out altitude budget")
    ax.axvspan(max(ws_re, ws_wind), ws_stall, color="#FED176", alpha=0.08)
    ax.plot([W / S], [float(r["energy"]["P_loiter_shaft_w"]) / W], "o", color="w", mec="k", ms=9, label="design point")
    ax.set_xlabel("wing loading W/S (N/m^2)"); ax.set_ylabel("P/W (W/N)")
    ax.set_title(f"Constraint diagram at the design AR {AR:.1f}, CL_loiter {CL:.2f}")
    ax.set_xlim(20, 160); ax.set_ylim(0, max(pw_climb) * 1.05); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def main():
    po, used_p6 = prop_override()
    M = SizingModel(prop_override=po)
    d = phase_dir("p3")
    gr = grid_sweep(M)
    SS, AA, CC, mgrid, feas, rgrid = gr.pop("_arrays")
    op = opti(M)
    if op["status"] != "solved" and "S" in gr:
        op = opti(M, (gr["S"], gr["AR"], gr["CL"], gr["mtow"]))
        op["note"] = "re-solved from the grid optimum after a failed cold start"
    if "S" not in gr:
        raise SystemExit(f"grid sweep found no feasible design: {gr}")
    base = op if op.get("status") == "solved" else gr
    S, AR, CL = base["S"], base["AR"], base["CL"]
    m, n_cells, r, th, iters, (S, AR, CL) = close_final(M, S, AR, CL, base["mtow"])
    noins = bt.simulate(n_cells, 0.0, 0.0, r["energy"]["t_ascent_s"], r["energy"]["t_release_glide_s"],
                        r["energy"]["t_loiter_s"], r["energy"]["t_descent_s"], insulated=False, heater=False)
    pay = bt.payload_budget(th["t"], th["z"], th["phase"])
    g = geom.build(S, AR, M.foil, read_json(latest_phase_file("p2", "selection.json"))["tail_selected"], M.tc)
    if used_p6:
        g["prop"]["diameter"] = po["prop_diameter_m"]
    x_np = geom.np_estimate(g)
    sm_target = float(np.mean(load_cfg("bars")["stability"]["sm_pct"])) / 100
    L = wb.items(g, {k: float(v) for k, v in r["masses"].items()})
    sol = wb.solve(L, x_np - sm_target * g["mac"], g["pod"])
    c = wb.cg(L)
    I = wb.inertia(L)
    g["cg"] = {"x": c["x"], "z": c["z"], "x_np_estimate": x_np, "sm_target": sm_target, **sol}
    g["mass"] = {"mtow": m, **I}
    lo = r["loiter"]
    st = isa(M.m["loiter"]["alt_m"])
    cell = M.c["battery_cell"]
    E_name = n_cells * cell["v_nom"] * cell["ah"]
    cap_T = bt.capacity_fraction(th["T_min_loiter"])
    E_usable = E_name * cap_T * cell["dod_limit"] - th["E_heater_wh"]
    E_need_noheat = float(r["energy"]["E_noheat_wh"])
    sizing = {
        "airfoil": M.foil, "ncrit": M.ncrit, "drag_k": M.which_k, "used_p6": used_p6, "prop_override": po,
        "mtow_kg": m, "S_m2": S, "AR": AR, "span_m": g["b"], "mac_m": g["mac"], "c_root_m": g["c_root"],
        "c_tip_m": g["c_tip"], "taper": g["taper"], "wing_loading_npm2": m * G / S, "cl_loiter": CL,
        "loiter_alt_m": M.m["loiter"]["alt_m"], "v_loiter_tas": float(lo["V"]), "v_loiter_eas": float(lo["V"] * math.sqrt(st["sigma"])),
        "q_loiter": float(m * G / S / CL), "re_loiter": float(lo["re"]), "mach_loiter": float(lo["V"] / st["a"]),
        "ld_loiter": float(lo["LD"]), "cd_loiter": float(lo["CD"]), "cd_parts": {k: float(lo[k]) for k in ("cd_wing_profile", "cd_induced", "cd_parasite")},
        "clmax_3d": M.clmax3d, "vs_eas_sl": float(r["vs_eas"]), "S_h_m2": g["htail"]["S"], "S_v_m2": g["vtail"]["S"],
        "tail_arm_m": g["tail_arm"], "n_cells": n_cells, "pack": f"{M.s['pack_series']}S{n_cells // M.s['pack_series']}P",
        "E_nameplate_wh": E_name, "E_usable_wh": E_usable, "E_required_noheat_wh": E_need_noheat,
        "E_heater_wh": th["E_heater_wh"], "cap_fraction_at_Tmin_loiter": cap_T,
        "P_loiter_elec_w": float(r["energy"]["P_loiter_elec_w"]), "P_loiter_shaft_w": float(r["energy"]["P_loiter_shaft_w"]),
        "P_max_shaft_w": float(r["energy"]["P_max_shaft_w"]), "times_s": {k: float(v) for k, v in r["energy"].items() if k.startswith("t_")},
        "cell_T_min_c": th["T_min"], "cell_T_min_loiter_c": th["T_min_loiter"], "noinsulation_cell_T_min_c": noins["T_min"],
        "payload_T_min_c": pay["T_min"], "payload_T_min_loiter_c": pay["T_min_loiter"],
        "masses": {k: float(v) for k, v in r["masses"].items()}, "spar": {k: float(v) for k, v in r["spar"].items()},
        "constraints": {k: float(v) for k, v in r["cons"].items()}, "grid": gr, "mass_loop_residual_frac": float(abs(r["m_sum"] - m) / m),
        "continuous_optimum": {"S": base["S"], "AR": base["AR"], "CL": base["CL"], "mtow": base["mtow"]}, "opti": op, "closure_iterations": iters,
        "re_min_validated_strict": M.re_min_validated, "re_floor_design": M.re_floor,
        "mr9_strict_met": bool(lo["re"] >= M.re_min_validated), "polar_fit": {k: M.polar.fit[k] for k in ("rms_log", "max_rel_err", "n")}, "polar_fit_coef": M.polar.fit["coef"],
        "tail_cd": M.polar.tail_cd,
        "oswald_e": float(r["e"]), "w95_loiter_mps": M.w95_loiter, "v_bestld_tas_loiter": float(r["v_bestld_tas_loiter"]),
    }
    write_json(d / "sizing.json", sizing)
    write_json(d / "geometry.json", g)
    wb.write_csv(L, d / "wb.csv")
    with open(d / "weights.csv", "w") as f:
        f.write("group,mass_kg\n")
        for k, v in r["masses"].items():
            f.write(f"{k},{float(v):.6f}\n")
    write_json(d / "thermal.json", {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in th.items() if k != "phase"}
               | {"phase": th["phase"].tolist(), "noins_T_cell": noins["T_cell"].tolist(), "payload_T": pay["T"].tolist()})
    constraint_plot(M, S, AR, CL, m, r, d / "p3_constraint.png")
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.plot(th["t"] / 60, th["T_amb"], color="#7aa2f7", label="ambient (ISA along timeline)")
    ax.plot(th["t"] / 60, th["T_cell"], color="#FED176", lw=2, label="cells, insulated + heater")
    ax.plot(th["t"] / 60, noins["T_cell"], color="#f7768e", ls="--", label="cells, no insulation, no heater")
    ax.plot(th["t"] / 60, pay["T"], color="#9ece6a", ls="-.", label="payload box")
    ax.axhline(M.m["thermal"]["cell_min_c"], color="w", lw=0.8, ls=":")
    ax.set_xlabel("time from launch (min)"); ax.set_ylabel("temperature (C)"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    ax.set_title(f"Battery cold soak: heater {th['E_heater_wh']:.1f} Wh, cell min {th['T_min']:.1f} C")
    fig.tight_layout(); fig.savefig(d / "p3_thermal.png", dpi=130); plt.close(fig)
    n = Numbers("p3", "src/stratoglide/sizing/run_sizing.py")
    for k in ("mtow_kg", "S_m2", "AR", "span_m", "mac_m", "c_root_m", "c_tip_m", "wing_loading_npm2", "cl_loiter",
              "v_loiter_tas", "v_loiter_eas", "q_loiter", "re_loiter", "mach_loiter", "ld_loiter", "vs_eas_sl", "S_h_m2",
              "S_v_m2", "tail_arm_m", "n_cells", "E_nameplate_wh", "E_usable_wh", "E_heater_wh", "P_loiter_elec_w",
              "P_loiter_shaft_w", "cell_T_min_c", "noinsulation_cell_T_min_c", "payload_T_min_c", "clmax_3d", "oswald_e"):
        n.add(k, sizing[k])
    n.add("pack", sizing["pack"])
    n.add("mtow_grid_kg", gr["mtow"]); n.add("mtow_opti_kg", op.get("mtow"))
    n.add("max_re_loiter_other_constraints", gr["max_re_other_constraints"])
    n.add("mr9_strict_met", sizing["mr9_strict_met"], "bool")
    n.add("x_cg_m", c["x"]); n.add("x_np_estimate_m", x_np)
    n.add("battery_x_m", sol["x_battery"]); n.add("battery_x_clamped", sol["clamped"], "bool")
    for k, v in r["masses"].items():
        n.add(f"mass_{k}_kg", float(v))
    n.save()
    for p in ("p3_constraint.png", "p3_thermal.png"):
        (OUTPUTS / p).write_bytes((d / p).read_bytes())
    print(f"grid {gr.get('mtow'):.3f} kg (S {gr['S']:.3f} AR {gr['AR']:.2f} CL {gr['CL']:.2f}, {gr['n_feasible']}/{gr['n_points']} feasible) | "
          f"opti {op}")
    print(f"FINAL MTOW {m:.3f} kg span {g['b']:.3f} m S {S:.3f} AR {AR:.2f} CL {CL:.3f} cells {n_cells} Re {lo['re']:.0f} "
          f"L/D {float(lo['LD']):.2f} P_elec {float(r['energy']['P_loiter_elec_w']):.1f} W heater {th['E_heater_wh']:.1f} Wh "
          f"cellTmin {th['T_min']:.1f} noins {noins['T_min']:.1f} payload {pay['T_min']:.1f} | max Re (other cons) {gr['max_re_other_constraints']:.0f}")
    print("cons", {k: round(float(v), 3) for k, v in r["cons"].items()}, "usable", round(E_usable, 1), "need", round(E_need_noheat, 1))


if __name__ == "__main__":
    main()
