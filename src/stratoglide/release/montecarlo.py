"""Release Monte Carlo (N from bars, seeded Latin hypercube) with the own vectorised 6-DOF.

Parameters (plan table): release pitch -90..+10 deg, roll +/-30, yaw 0..360; body rates +/-30 deg/s each;
vertical velocity 0-5 m/s up, horizontal = wind at 25 km (drifting with the balloon) plus a +/-5 m/s gust
(applied as an initial air-relative velocity); wind profile P50 or P95 (IGRA Lucknow), direction uniform;
mass +/-5%, CG +/-2% MAC, elevator and tail effectiveness +/-20% each, post-stall CD90 1.0-1.4, blend centre
+/-3 deg and blend width 1-3 deg (interpretation of the plan's "blend width +/-3 deg", logged), inertia +/-10%.
Each sample is flown twice: autopilot and passive (controls at trim). Also the vertical-dive counterfactual.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import qmc

from ..atmos import isa
from ..common import Numbers, OUTPUTS, load_cfg, phase_dir, write_json
from ..perf import wind_profile
from . import aero_tables, sim6dof as sd

D2R = np.pi / 180
SEED = 20261118
NAMES = ["pitch", "roll", "yaw", "p", "q", "r", "v_up", "gust_n", "gust_e", "wind_pct", "wind_dir", "mass", "cg",
         "k_elev", "k_tail", "cd90", "blend_c", "blend_w", "inertia"]


def samples(N):
    u = qmc.LatinHypercube(d=len(NAMES), seed=SEED).random(N)
    m = load_cfg("mission")["release"]
    lo = np.array([m["pitch_deg"]["min"], -m["roll_deg_abs"], 0, -30, -30, -30, 0, -5, -5, 0, 0, -0.05, -0.02,
                   0.8, 0.8, 1.0, -3, 1, -0.10])
    hi = np.array([m["pitch_deg"]["max"], m["roll_deg_abs"], 360, 30, 30, 30, 5, 5, 5, 1, 360, 0.05, 0.02,
                   1.2, 1.2, 1.4, 3, 3, 0.10])
    return dict(zip(NAMES, (lo + u * (hi - lo)).T))


def build(N):
    s = samples(N)
    p0 = aero_tables.nominal()
    p = dict(p0)
    p["mass"] = p0["mass"] * (1 + s["mass"])
    for k in ("Ixx", "Iyy", "Izz"):
        p[k] = p0[k] * (1 + s["inertia"])
    p["dcg_mac"] = s["cg"]
    p["k_elev"], p["k_tail"], p["CD90"] = s["k_elev"], s["k_tail"], s["cd90"]
    p["alpha_stall"] = p0["alpha_stall"] + s["blend_c"] * D2R
    p["blend_w"] = s["blend_w"] * D2R
    prof = wind_profile.load()
    zs = np.array(prof["bins_m"], float)
    p50 = np.array([wind_profile.wind_at(z, "p50", prof) for z in zs])
    p95 = np.array([wind_profile.wind_at(z, "p95", prof) for z in zs])
    use95 = s["wind_pct"] >= 0.5
    speeds = np.where(use95[:, None], p95[None, :], p50[None, :])
    wind = sd.Wind(zs, speeds, s["wind_dir"] * D2R)
    z0 = load_cfg("mission")["release"]["alt_m"]
    X0 = np.zeros((N, 13))
    X0[:, 2] = -z0
    X0[:, 6:10] = sd.euler2q(s["roll"] * D2R, s["pitch"] * D2R, s["yaw"] * D2R)
    w0 = wind(np.full(N, z0))
    v_ned = w0 + np.stack([s["gust_n"], s["gust_e"], -s["v_up"]], 1)
    R = sd.q2R(X0[:, 6:10])
    X0[:, 3:6] = np.einsum("nji,nj->ni", R, v_ned)
    X0[:, 10:13] = np.stack([s["p"], s["q"], s["r"]], 1) * D2R
    return p, X0, wind, s, use95


def vertical_dive(p, z0, wave=True, dt=0.01):
    """Point-mass vertical dive at zero lift from z0 (controls locked nose-down): max Mach reached."""
    z, V, mmax, t = z0, 0.0, 0.0, 0.0
    m = p["mass"]
    while z > 0 and t < 600:
        at = isa(z)
        M = V / float(at["a"])
        cd = p["CD0"] + (20 * (M - 0.6) ** 4 if (wave and M > 0.6) else 0.0)
        acc = 9.80665 - 0.5 * float(at["rho"]) * V ** 2 * p["S"] * cd / m
        V += acc * dt
        z -= V * dt
        t += dt
        mmax = max(mmax, M)
        if acc < 0 and M < mmax - 0.05:
            break
    return mmax


def pct(x, q):
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float("nan")


def main():
    bars = load_cfg("bars")["release"]
    N = int(bars["mc_n_min"])
    p, X0, wind, s, use95 = build(N)
    out = {"N": N, "seed": SEED, "params": {k: [float(v.min()), float(v.max())] for k, v in s.items()}}
    res = {}
    for mode in ("autopilot", "passive"):
        r = sd.run(p, X0, wind, t_end=bars["recovered_def"]["window_s"], dt=0.01, mode=mode, record_every=50)
        z0 = -X0[0, 2]
        loss = z0 - r["z_rec"]
        st = r["stats"]
        # looser descriptive metric (not a bar): pulled out = flight path above -30 deg at the end and no stall at end
        res[mode] = r
        out[mode] = {"recovery_rate": float(r["recovered"].mean()), "n_recovered": int(r["recovered"].sum()),
                     "mach": {q: pct(st["mach"], q) for q in (50, 95, 99)} | {"max": float(st["mach"].max())},
                     "nz": {q: pct(st["nz"], q) for q in (50, 95, 99)} | {"max": float(st["nz"].max()), "min": float(st["nz_min"].min())},
                     "qd_pa": {q: pct(st["qd"], q) for q in (50, 95, 99)} | {"max": float(st["qd"].max())},
                     "eas": {q: pct(st["eas"], q) for q in (50, 95, 99)} | {"max": float(st["eas"].max())},
                     "alt_loss_m": {q: pct(loss, q) for q in (50, 95, 99)} | {"max": float(np.nanmax(loss)) if np.isfinite(loss).any() else None},
                     "t_rec_s": {q: pct(r["t_rec"], q) for q in (50, 95, 99)},
                     "e_viol_max_wpkg": float(np.max(r["e_viol_max"])),
                     "misses": [int(i) for i in np.where(~r["recovered"])[0][:50]]}
        print(mode, out[mode]["recovery_rate"], out[mode]["mach"], out[mode]["nz"]["max"], out[mode]["alt_loss_m"], flush=True)
    gp = res["passive"]["hist"][:, -40:, 6]  # last 20 s of gamma (recorded every 0.5 s)
    swing = np.degrees(gp.max(1) - gp.min(1))
    out["passive"]["gamma_swing_last20s_deg"] = {q: pct(swing, q) for q in (50, 95)} | {"max": float(swing.max())}
    out["vertical_dive_max_mach_clean"] = vertical_dive(aero_tables.nominal(), -X0[0, 2], wave=False)
    out["vertical_dive_max_mach_with_placeholder"] = vertical_dive(aero_tables.nominal(), -X0[0, 2], wave=True)
    d = phase_dir("p5")
    write_json(d / "release_mc.json", out)
    np.savez_compressed(d / "release_traj.npz", auto=res["autopilot"]["hist"].astype(np.float32),
                        passive=res["passive"]["hist"].astype(np.float32),
                        cols=np.array(["t", "z", "V", "mach", "nz", "eas", "gamma", "alpha", "theta", "phi", "x", "y"]))
    _plots(res, out)
    n = Numbers("p5", "src/stratoglide/release/montecarlo.py")
    a = out["autopilot"]
    n.add("mc_n", N)
    n.add("recovery_rate_autopilot", a["recovery_rate"])
    n.add("recovery_rate_passive", out["passive"]["recovery_rate"])
    n.add("mach_p99", a["mach"][99]); n.add("mach_max", a["mach"]["max"])
    n.add("nz_max", a["nz"]["max"], "g"); n.add("nz_p99", a["nz"][99], "g")
    n.add("alt_loss_p95_m", a["alt_loss_m"][95], "m"); n.add("alt_loss_p50_m", a["alt_loss_m"][50], "m")
    n.add("t_rec_p95_s", a["t_rec_s"][95], "s")
    n.add("peak_eas_max", a["eas"]["max"], "m/s"); n.add("peak_q_max_pa", a["qd_pa"]["max"], "Pa")
    n.add("passive_mach_max", out["passive"]["mach"]["max"]); n.add("passive_nz_max", out["passive"]["nz"]["max"], "g")
    n.add("passive_gamma_swing_last20s_p50_deg", out["passive"]["gamma_swing_last20s_deg"][50], "deg", note="descriptive, not a bar")
    n.add("e_viol_max_wpkg", max(a["e_viol_max_wpkg"], out["passive"]["e_viol_max_wpkg"]), "W/kg")
    n.add("vertical_dive_max_mach_clean", out["vertical_dive_max_mach_clean"])
    n.add("vertical_dive_max_mach_with_placeholder", out["vertical_dive_max_mach_with_placeholder"])
    n.save()
    print("dive", out["vertical_dive_max_mach_clean"], out["vertical_dive_max_mach_with_placeholder"])


def _plots(res, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h = res["autopilot"]["hist"]
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))
    for i in range(0, h.shape[0], 5):
        ax[0].plot(h[i, :, 0], h[i, :, 1] / 1000, lw=0.4, color="#2b6cb0", alpha=0.35)
    hp = res["passive"]["hist"]
    for i in range(0, hp.shape[0], 25):
        ax[0].plot(hp[i, :, 0], hp[i, :, 1] / 1000, lw=0.4, color="#c05621", alpha=0.5)
    ax[0].set_xlabel("time since release (s)"); ax[0].set_ylabel("altitude (km)")
    ax[0].set_title("trajectory fan: autopilot (blue), passive (orange, every 25th)")
    ax[1].hist(res["autopilot"]["stats"]["mach"], bins=40, color="#2b6cb0", alpha=0.8, label="autopilot")
    ax[1].hist(res["passive"]["stats"]["mach"], bins=40, color="#c05621", alpha=0.5, label="passive")
    ax[1].axvline(0.5, color="k", ls="--", label="bar 0.50"); ax[1].set_xlabel("peak Mach"); ax[1].legend()
    ax[2].hist(res["autopilot"]["stats"]["nz"], bins=40, color="#2b6cb0", alpha=0.8, label="autopilot")
    ax[2].hist(res["passive"]["stats"]["nz"], bins=40, color="#c05621", alpha=0.5, label="passive")
    ax[2].axvline(4.0, color="k", ls="--", label="limit 4 g"); ax[2].set_xlabel("peak n_z (g)"); ax[2].legend()
    for a in ax:
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUTS / "p5_release_mc.png", dpi=130)


if __name__ == "__main__":
    main()
