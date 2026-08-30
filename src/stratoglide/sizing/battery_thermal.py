"""Lumped transient cold-soak model of the insulated battery box (MR-10) and the payload budget (MR-5).

m c dT/dt = Q_heater + I^2 R_pack(T) - (T - T_amb(t)) / R_th
R_th = t_ins / (k A_mean) + 1 / (h_ext A_out). Heater: proportional thermostat, clipped to [0, P_max].
Timeline: ascent at 5 m/s from the launch site to 25 km, glide 25 -> 19 km, 30 min loiter, descent to
chute deploy. Counterfactual: no insulation and no heater (R_th = 1 / (h_ext A_cells)).
"""
from __future__ import annotations

import numpy as np

from ..atmos import isa
from ..common import load_cfg


def timeline(t_asc, t_rel, t_loit, t_desc, z_launch, z_rel, z_loit, z_deploy, dt=10.0):
    t = np.arange(0.0, t_asc + t_rel + t_loit + t_desc + dt, dt)
    z = np.empty_like(t)
    phase = np.empty(len(t), dtype=object)
    t1, t2, t3 = t_asc, t_asc + t_rel, t_asc + t_rel + t_loit
    for i, ti in enumerate(t):
        if ti <= t1:
            z[i] = z_launch + (z_rel - z_launch) * ti / t_asc; phase[i] = "ascent"
        elif ti <= t2:
            z[i] = z_rel + (z_loit - z_rel) * (ti - t1) / t_rel; phase[i] = "transit"
        elif ti <= t3:
            z[i] = z_loit; phase[i] = "loiter"
        else:
            z[i] = z_loit + (z_deploy - z_loit) * min(1.0, (ti - t3) / t_desc); phase[i] = "descent"
    return t, z, phase


def simulate(n_cells, p_loiter_elec, p_base, t_asc, t_rel, t_loit, t_desc, insulated=True, heater=True):
    m, c, s = load_cfg("mission"), load_cfg("components"), load_cfg("sizing")
    cell, th, ins = c["battery_cell"], s["thermal"], c["insulation"]
    zl = m["recovery_site_elev_m"]
    t, z, ph = timeline(t_asc, t_rel, t_loit, t_desc, zl, m["release"]["alt_m"], m["loiter"]["alt_m"],
                        zl + m["return"]["chute_deploy_agl_m"])
    Tamb = isa(z)["T"] - 273.15
    vol = n_cells * th["cell_d_m"] ** 2 * th["cell_h_m"]
    side = vol ** (1 / 3) + 2 * th["box_wall_gap_m"]
    A_in = 6 * 1.15 * side ** 2
    A_out = 6 * 1.15 * (side + 2 * ins["thickness_m"]) ** 2
    if insulated:
        R = ins["thickness_m"] / (ins["k_w_mk"] * np.sqrt(A_in * A_out)) + 1 / (th["h_ext_wm2k"] * A_out)
    else:
        R = 1 / (th["h_ext_wm2k"] * A_in)
    mc = n_cells * cell["mass_kg"] * cell["cp_jkgk"]
    ns = s["pack_series"]
    npar = n_cells / ns
    rf = cell["rint_factor_vs_temp_c"]
    tk = sorted(float(k) for k in rf)
    rv = [rf[int(k)] for k in tk]
    T = np.empty_like(t)
    Ph = np.zeros_like(t)
    T[0] = m["thermal"]["launch_cell_c"]
    dt = t[1] - t[0]
    for i in range(1, len(t)):
        Tc = T[i - 1]
        load = p_base + (p_loiter_elec if ph[i] == "loiter" else 0.0)
        V = ns * cell["v_nom"]
        I = load / V
        Rpack = cell["r_int_ohm_25c"] * float(np.interp(Tc, tk, rv)) * ns / npar
        q_self = I ** 2 * Rpack
        ph_ = float(np.clip(2.0 * (th["setpoint_c"] - Tc), 0.0, th["heater_max_w"])) if heater else 0.0
        Ph[i] = ph_
        T[i] = Tc + dt * (ph_ + q_self - (Tc - Tamb[i]) / R) / mc
    E_heat = float(np.sum(Ph) * dt / 3600.0)
    return {"t": t, "z": z, "phase": ph, "T_amb": Tamb, "T_cell": T, "P_heater": Ph, "E_heater_wh": E_heat,
            "T_min": float(T.min()), "T_min_loiter": float(T[ph == "loiter"].min()), "R_th": float(R),
            "heater_mean_w_mission": float(Ph[ph != "ascent"].mean())}


def capacity_fraction(T_c):
    cap = load_cfg("components")["battery_cell"]["capacity_vs_temp_c"]
    tk = sorted(float(k) for k in cap)
    return float(np.interp(T_c, tk, [cap[int(k)] for k in tk]))


def payload_budget(t, z, phase):
    """Payload box: 1 kg, 900 J/kgK, 10 mm foam, 8 W in loiter, standby otherwise."""
    m, c, s = load_cfg("mission"), load_cfg("components"), load_cfg("sizing")
    A = 6 * 0.12 ** 2
    R = s["thermal"]["payload_insulation_m"] / (c["insulation"]["k_w_mk"] * A) + 1 / (s["thermal"]["h_ext_wm2k"] * A)
    Tamb = isa(z)["T"] - 273.15
    T = np.empty_like(t); T[0] = m["thermal"]["launch_cell_c"]
    mc = m["payload"]["mass_kg"] * 900.0
    for i in range(1, len(t)):
        P = m["payload"]["power_w"] if phase[i] == "loiter" else m["payload"]["standby_power_w"]
        T[i] = T[i - 1] + (t[i] - t[i - 1]) * (P - (T[i - 1] - Tamb[i]) / R) / mc
    return {"T_min": float(T.min()), "T_min_loiter": float(T[phase == "loiter"].min()), "R_th": float(R), "T": T}
