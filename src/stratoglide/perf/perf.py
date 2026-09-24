"""P7 mission performance from the P3 SizingModel (same drag model, same energy budget) and P6 propulsion.

- Power required / available at 0, 10, 15, 18, 19, 20 km (P_avail = motor p_max x motor eta x prop eta(h)).
- Glide polar per altitude: V_bestLD, V_minsink, L/D_max, min sink (EAS and TAS).
- Loiter endurance at 18/19/20 km: usable Wh minus every non-loiter segment's energy, divided by loiter
  electrical power (propulsion + payload 8 W + avionics + servos + heater average).
- Glide range 25 km -> chute deploy (1.5 km AGL): still air by quadrature of L/D_max(h); through P50/P95 wind
  layers with speed-to-fly (maximise along-track ground speed per unit sink, MacCready style, no lift).
- Return footprint from the end of loiter (19 km) to deploy, per wind direction, P50 and P95 (wind direction
  assumed constant with altitude: all layers aligned, the conservative case).
- Mission timeline table.
"""
from __future__ import annotations

import csv

import numpy as np

from ..atmos import isa
from ..common import Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from ..sizing.model import SizingModel
from ..sizing.run_sizing import prop_override
from . import wind_profile

G = 9.80665
ALTS = [0.0, 10000.0, 15000.0, 18000.0, 19000.0, 20000.0]


class Aircraft:
    def __init__(self):
        self.s = read_json(latest_phase_file("p3", "sizing.json"))
        po, _ = prop_override()
        self.M = SizingModel(prop_override=po)
        self.geo = self.M.geometry(self.s["S_m2"], self.s["AR"])
        self.W = self.s["mtow_kg"] * G
        self.e = self.s["oswald_e"]
        self.cls = np.linspace(0.15, self.s["clmax_3d"] / 1.1, 160)

    def at(self, z, CL):
        a = isa(z)
        f = self.M.flight(self.s["S_m2"], self.s["AR"], CL, self.W, {"rho": float(a["rho"]), "mu": float(a["mu"])}, self.geo, self.e)
        sig = float(a["rho"]) / 1.225
        return {"V": f["V"], "Veas": f["V"] * np.sqrt(sig), "D": f["D"], "P": f["P"], "LD": f["LD"], "sink": f["V"] / f["LD"]}

    def polar(self, z):
        rows = [self.at(z, c) for c in self.cls]
        return {k: np.array([r[k] for r in rows]) for k in rows[0]}


def speed_to_fly(pol, w_par, w_perp):
    """Max along-track distance per metre of descent over the polar points (crab to hold the track)."""
    V, sink = pol["V"], pol["sink"]
    ok = V > abs(w_perp) + 1e-6
    along = np.where(ok, np.sqrt(np.maximum(V ** 2 - w_perp ** 2, 0)) + w_par, -np.inf)
    ratio = along / sink
    k = int(np.argmax(ratio))
    return ratio[k], V[k]


def glide_distance(ac, z_top, z_bot, wind_speed=None, psi=0.0, dz=250.0):
    """psi = track direction relative to the downwind direction (0 = tailwind, pi = into wind)."""
    zs = np.arange(z_top, z_bot, -dz)
    dist, t = 0.0, 0.0
    for z in zs:
        h = min(dz, z - z_bot)
        pol = ac.polar(z - h / 2)
        w = 0.0 if wind_speed is None else float(wind_speed(z - h / 2))
        r, V = speed_to_fly(pol, w * np.cos(psi), w * np.sin(psi))
        if not np.isfinite(r):
            return -np.inf, t
        dist += r * h
        sink = pol["sink"][int(np.argmin(abs(pol["V"] - V)))]
        t += h / sink
    return dist, t


def main():
    ac = Aircraft()
    s, m = ac.s, load_cfg("mission")
    p6 = read_json(latest_phase_file("p6", "prop.json"))
    comp = load_cfg("components")
    mot = next(x for x in comp["motors"] if x["name"] == p6["motor"]["name"])
    eta_m = p6["motor"]["eta_motor_loiter"]
    t6 = p6["table"]
    eta_p = lambda z: float(np.interp(z, [r["z_m"] for r in t6], [r["eta_A"] for r in t6]))
    eta_esc = load_cfg("sizing")["propulsion_initial"]["eta_esc"]
    out = {"altitudes": {}}
    for z in ALTS:
        pol = ac.polar(z)
        i_ld, i_ms = int(np.argmax(pol["LD"])), int(np.argmin(pol["sink"]))
        p_av = mot["p_max_w"] * eta_m * eta_esc * eta_p(z)
        out["altitudes"][str(int(z))] = {
            "V_bestLD_tas": pol["V"][i_ld], "V_bestLD_eas": pol["Veas"][i_ld], "LD_max": pol["LD"][i_ld],
            "V_minsink_tas": pol["V"][i_ms], "V_minsink_eas": pol["Veas"][i_ms], "sink_min": pol["sink"][i_ms],
            "P_req_min_w": float(pol["P"].min()), "P_avail_w": p_av, "excess_power_min_w": float(p_av - pol["P"].min()),
            "polar": {k: v.tolist() for k, v in pol.items()}}
    # ---------------- endurance
    E_use = s["E_usable_wh"]
    p_base = m["avionics"]["power_w"]
    t = s["times_s"]
    t_tot = t["t_ascent_s"] + t["t_release_glide_s"] + t["t_loiter_s"] + t["t_descent_s"]
    E_heat_rate = s["E_heater_wh"] / (t_tot / 3600)  # average heater power (transient model total / mission time)
    E_nonloiter = ((m["payload"]["standby_power_w"] + p_base) * (t_tot - t["t_loiter_s"])
                   + m["avionics"]["servo_power_w"] * (t["t_release_glide_s"] + t["t_descent_s"])) / 3600 \
        + E_heat_rate * (t_tot - t["t_loiter_s"]) / 3600
    endur = {}
    for z in (18000.0, 19000.0, 20000.0):
        f = ac.at(z, s["cl_loiter"])
        P_prop = f["P"] / (eta_p(z) * eta_m * eta_esc)
        P_tot = P_prop + m["payload"]["power_w"] + p_base + m["avionics"]["servo_power_w"] + E_heat_rate
        E_loit = E_use - E_nonloiter
        endur[str(int(z))] = {"P_loiter_elec_total_w": P_tot, "P_prop_elec_w": P_prop, "E_avail_loiter_wh": E_loit,
                              "endurance_min": 60 * E_loit / P_tot}
    out["endurance"] = endur
    out["mr4_required_min"] = m["loiter"]["duration_min"]
    out["mr4_met"] = all(v["endurance_min"] >= m["loiter"]["duration_min"] for v in endur.values())
    # ---------------- glide range from release
    z_dep = m["recovery_site_elev_m"] + m["return"]["chute_deploy_agl_m"]
    z_rel = m["release"]["alt_m"]
    d_still, t_still = glide_distance(ac, z_rel, z_dep)
    ld_mid = ac.polar((z_rel + z_dep) / 2)["LD"].max()
    prof = wind_profile.load()
    wp = {pc: (lambda zz, pc=pc: wind_profile.wind_at(zz, pc, prof)) for pc in ("p50", "p95")}
    rng = {"still_air_m": d_still, "still_air_time_s": t_still, "dh_x_LDmid_m": (z_rel - z_dep) * ld_mid, "LD_mid": ld_mid}
    for pc in ("p50", "p95"):
        rng[f"{pc}_downwind_m"] = glide_distance(ac, z_rel, z_dep, wp[pc], 0.0)[0]
        rng[f"{pc}_upwind_m"] = glide_distance(ac, z_rel, z_dep, wp[pc], np.pi)[0]
    out["glide_range"] = rng
    # ---------------- return footprint from end of loiter
    z_l = m["loiter"]["alt_m"]
    psis = np.radians(np.arange(0, 360, 15))
    fp = {}
    for pc in ("p50", "p95"):
        fp[pc] = [{"psi_deg": float(np.degrees(ps)), "reach_m": float(glide_distance(ac, z_l, z_dep, wp[pc], ps)[0])} for ps in psis]
    fp["still"] = glide_distance(ac, z_l, z_dep)[0]
    out["footprint"] = fp
    out["mr6_p95_min_reach_m"] = min(r["reach_m"] for r in fp["p95"])
    out["mr6_note"] = ("reach = max offset between end-of-loiter point and recovery point at which the glider still "
                       "arrives at 1.5 km AGL, per track direction relative to downwind; negative/-inf = cannot make "
                       "progress into wind")
    # ---------------- timeline
    mc = read_json(latest_phase_file("p5", "release_mc.json"))
    tl = [
        ("ascent (balloon)", 0.0, z_rel, t["t_ascent_s"], (p_base + m["payload"]["standby_power_w"] + E_heat_rate) * t["t_ascent_s"] / 3600),
        ("release + pull-out (P50)", z_rel, z_rel - mc["autopilot"]["alt_loss_m"]["50"], mc["autopilot"]["t_rec_s"]["50"], 0.0),
        ("transit glide to loiter", z_rel - mc["autopilot"]["alt_loss_m"]["50"], z_l, t["t_release_glide_s"],
         (p_base + m["payload"]["standby_power_w"] + m["avionics"]["servo_power_w"] + E_heat_rate) * t["t_release_glide_s"] / 3600),
        ("loiter (MR-4)", z_l, z_l, t["t_loiter_s"], endur[str(int(z_l))]["P_loiter_elec_total_w"] * t["t_loiter_s"] / 3600),
        ("return glide to deploy", z_l, z_dep, t["t_descent_s"],
         (p_base + m["payload"]["standby_power_w"] + m["avionics"]["servo_power_w"] + E_heat_rate) * t["t_descent_s"] / 3600),
        ("parachute deploy (MR-6)", z_dep, m["recovery_site_elev_m"], 0.0, 0.0)]
    out["timeline"] = [{"phase": a, "alt_start_m": b, "alt_end_m": c, "duration_s": d, "energy_wh": e} for a, b, c, d, e in tl]
    out["timeline_energy_wh"] = sum(r["energy_wh"] for r in out["timeline"])
    out["E_usable_wh"] = E_use
    d = phase_dir("p7")
    write_json(d / "perf.json", out)
    with open(d / "mission_timeline.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out["timeline"][0]))
        w.writeheader()
        w.writerows(out["timeline"])
    (OUTPUTS / "mission_timeline.csv").write_text((d / "mission_timeline.csv").read_text())
    _plots(out, ac)
    n = Numbers("p7", "src/stratoglide/perf/perf.py")
    for z, v in out["altitudes"].items():
        k = f"{int(z)//1000}km"
        for kk in ("V_bestLD_tas", "V_bestLD_eas", "LD_max", "V_minsink_tas", "sink_min", "P_req_min_w", "P_avail_w"):
            n.add(f"{kk}_{k}", v[kk])
    for z, v in endur.items():
        n.add(f"endurance_min_{int(z)//1000}km", v["endurance_min"], "min")
        n.add(f"p_loiter_elec_total_w_{int(z)//1000}km", v["P_loiter_elec_total_w"], "W")
        n.add(f"e_avail_loiter_wh_{int(z)//1000}km", v["E_avail_loiter_wh"], "Wh")
    n.add("glide_range_still_km", d_still / 1000, "km")
    n.add("glide_range_dh_x_ld_km", rng["dh_x_LDmid_m"] / 1000, "km")
    for pc in ("p50", "p95"):
        for dd in ("downwind", "upwind"):
            v = rng[f"{pc}_{dd}_m"]
            n.add(f"glide_range_{pc}_{dd}_km", v / 1000 if np.isfinite(v) else -1.0, "km", note=None if np.isfinite(v) else "cannot progress")
    n.add("footprint_p95_min_reach_km", out["mr6_p95_min_reach_m"] / 1000 if np.isfinite(out["mr6_p95_min_reach_m"]) else -1.0, "km")
    n.add("footprint_p95_max_reach_km", max(r["reach_m"] for r in fp["p95"]) / 1000, "km")
    n.add("footprint_still_reach_km", fp["still"] / 1000, "km")
    n.add("timeline_energy_wh", out["timeline_energy_wh"], "Wh")
    n.save()
    print("endurance", {k: round(v["endurance_min"], 1) for k, v in endur.items()}, "range still", round(d_still / 1000, 1),
          "dh*LD", round(rng["dh_x_LDmid_m"] / 1000, 1), "p95 up/down", rng["p95_upwind_m"], rng["p95_downwind_m"],
          "fp p95 min", out["mr6_p95_min_reach_m"], "still reach", fp["still"])


def _plots(out, ac):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for z, v in out["altitudes"].items():
        pol = v["polar"]
        l, = ax.plot(pol["V"], pol["P"], label=f"{int(z)//1000} km P_req")
        ax.axhline(v["P_avail_w"], color=l.get_color(), ls=":", lw=0.8)
    ax.set_xlabel("V_TAS (m/s)"); ax.set_ylabel("thrust power (W)"); ax.set_ylim(0, None)
    ax.set_title("power required (solid) and available (dotted)"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUTPUTS / "p7_power_curves.png", dpi=130)
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for z, v in out["altitudes"].items():
        pol = v["polar"]
        ax.plot(pol["V"], -np.array(pol["sink"]), label=f"{int(z)//1000} km, L/D max {v['LD_max']:.1f}")
    ax.set_xlabel("V_TAS (m/s)"); ax.set_ylabel("vertical speed (m/s)"); ax.set_title("glide polars")
    ax.grid(alpha=0.3); ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUTPUTS / "p7_glide_polar.png", dpi=130)
    fig = plt.figure(figsize=(6, 6)); ax = fig.add_subplot(projection="polar")
    for pc, col in (("p50", "#2b6cb0"), ("p95", "#c05621")):
        r = out["footprint"][pc]
        th = np.radians([x["psi_deg"] for x in r] + [r[0]["psi_deg"]])
        rr = [max(x["reach_m"], 0) / 1000 for x in r] + [max(r[0]["reach_m"], 0) / 1000]
        ax.plot(th, rr, color=col, label=f"{pc.upper()} wind")
    ax.plot(np.linspace(0, 2 * np.pi, 100), [out["footprint"]["still"] / 1000] * 100, "k--", lw=0.8, label="still air")
    ax.set_title("return reach from end of loiter (km), 0 deg = downwind"); ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout(); fig.savefig(OUTPUTS / "p7_footprint.png", dpi=130)


if __name__ == "__main__":
    main()
