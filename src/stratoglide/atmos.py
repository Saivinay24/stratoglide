"""U.S. Standard Atmosphere 1976 at GEOMETRIC altitude, 0-47 km (layers 0-3).

Geometric z is converted to geopotential H = r0 z / (r0 + z) before the layer formulas.
Using z directly in the geopotential formulas gives rho(20 km) about 1% low (the recon trap).
Viscosity: Sutherland, mu = 1.458e-6 T^1.5 / (T + 110.4).
"""
from __future__ import annotations

import argparse
import re

import numpy as np

from .common import DATA, Numbers, phase_dir, write_json

R0 = 6356766.0          # m, effective Earth radius used by USSA-1976 for H
G0 = 9.80665
RAIR = 287.05287        # J/kg/K (USSA-1976: R*/M0)
GAMMA = 1.4
T0, P0, RHO0 = 288.15, 101325.0, 1.225
# (H_base [m geopotential], T_base, lapse K/m)
LAYERS = [(0.0, 288.15, -0.0065), (11000.0, 216.65, 0.0), (20000.0, 216.65, 0.001),
          (32000.0, 228.65, 0.0028), (47000.0, 270.65, 0.0)]


def _base_pressures():
    p = [P0]
    for i in range(len(LAYERS) - 1):
        hb, tb, L = LAYERS[i]
        ht = LAYERS[i + 1][0]
        if L == 0.0:
            p.append(p[-1] * np.exp(-G0 * (ht - hb) / (RAIR * tb)))
        else:
            p.append(p[-1] * (tb / (tb + L * (ht - hb))) ** (G0 / (RAIR * L)))
    return p


_PB = _base_pressures()


def geopotential(z):
    z = np.asarray(z, dtype=float)
    return R0 * z / (R0 + z)


def isa(z):
    """Return dict of T, p, rho, mu, nu, a, sigma at geometric altitude z [m] (scalar or array)."""
    z = np.asarray(z, dtype=float)
    H = geopotential(z)
    T = np.empty_like(H)
    p = np.empty_like(H)
    for i, (hb, tb, L) in enumerate(LAYERS):
        hi = LAYERS[i + 1][0] if i + 1 < len(LAYERS) else np.inf
        m = (H >= hb) & (H < hi) if i > 0 else (H < hi)
        if not np.any(m):
            continue
        dh = H[m] - hb
        T[m] = tb + L * dh
        if L == 0.0:
            p[m] = _PB[i] * np.exp(-G0 * dh / (RAIR * tb))
        else:
            p[m] = _PB[i] * (tb / T[m]) ** (G0 / (RAIR * L))
    rho = p / (RAIR * T)
    mu = 1.458e-6 * T ** 1.5 / (T + 110.4)
    a = np.sqrt(GAMMA * RAIR * T)
    out = {"T": T, "p": p, "rho": rho, "mu": mu, "nu": mu / rho, "a": a, "sigma": rho / RHO0}
    if out["T"].ndim == 0:
        out = {k: float(v) for k, v in out.items()}
    return out


def rho(z):
    return isa(z)["rho"]


def load_reference():
    """USSA-1976 tabulated values at geometric altitude, transcribed from the PDAS HTML tables
    (Public Domain Aeronautical Software, Carmichael), stored raw in data/validation/.
    Returns list of dicts {z_m, T, p, rho, source}."""
    refs = []
    h = (DATA / "validation" / "pdas_ussa1976_bigtables.html").read_text()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S)
    cells = [re.sub(r"<[^>]*>", " ", r).split() for r in rows]
    t1 = [c for c in cells if len(c) == 10 and re.match(r"^-?\d+$", c[0])]
    seen = set()
    for c in t1:
        zkm = int(c[0])
        if zkm > 35 or zkm in seen:
            continue
        seen.add(zkm)
        refs.append({"z_m": zkm * 1000.0, "T": float(c[2]), "p": float(c[4]), "rho": float(c[6]),
                     "source": "PDAS bigtables Table 1 (USSA-1976, geometric km)"})
    # 2 km table: sigma, delta, theta to 4-5 significant figures
    h2 = (DATA / "validation" / "pdas_ussa1976_table1SI.html").read_text()
    txt = re.sub(r"<[^>]*>", " ", h2)
    for line in txt.splitlines():
        s = line.split()
        if len(s) == 10 and re.match(r"^-?\d+$", s[0]):
            zkm = int(s[0])
            if zkm < 0 or zkm > 35 or zkm in seen or zkm % 2:
                continue
            seen.add(zkm)
            refs.append({"z_m": zkm * 1000.0, "T": float(s[3]) * T0, "p": float(s[2]) * P0,
                         "rho": float(s[1]) * RHO0,
                         "source": "PDAS atmosTable1SI (USSA-1976, ratios sigma/delta/theta)"})
    refs.sort(key=lambda r: r["z_m"])
    return refs


def validate():
    refs = load_reference()
    rows = []
    for r in refs:
        m = isa(r["z_m"])
        rows.append({"z_m": r["z_m"], "source": r["source"],
                     "err_T": m["T"] / r["T"] - 1, "err_p": m["p"] / r["p"] - 1,
                     "err_rho": m["rho"] / r["rho"] - 1,
                     "ref": {k: r[k] for k in ("T", "p", "rho")},
                     "model": {k: m[k] for k in ("T", "p", "rho")}})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zmax", type=float, default=35000)
    ap.add_argument("--step", type=float, default=100)
    a = ap.parse_args()
    d = phase_dir("p1")
    z = np.arange(0, a.zmax + a.step / 2, a.step)
    s = isa(z)
    with open(d / "isa.csv", "w") as f:
        f.write("z_m,T_K,p_Pa,rho_kgm3,mu_Pas,nu_m2s,a_mps,sigma\n")
        for i in range(len(z)):
            f.write(f"{z[i]:.0f},{s['T'][i]:.4f},{s['p'][i]:.6g},{s['rho'][i]:.6g},{s['mu'][i]:.6g},"
                    f"{s['nu'][i]:.6g},{s['a'][i]:.4f},{s['sigma'][i]:.6g}\n")
    val = validate()
    write_json(d / "atmos_validation.json", val)
    n = Numbers("p1", "src/stratoglide/atmos.py", {"zmax": a.zmax, "step": a.step})
    for zk in (0, 11000, 18000, 19000, 20000, 25000, 30000):
        m = isa(zk)
        k = f"{zk // 1000}km"
        n.add(f"rho_{k}", m["rho"], "kg/m^3")
        n.add(f"T_{k}", m["T"], "K")
        n.add(f"a_{k}", m["a"], "m/s")
        n.add(f"sigma_{k}", m["sigma"], "-")
        n.add(f"nu_{k}", m["nu"], "m^2/s")
    n.add("max_ref_err_frac", max(max(abs(r["err_T"]), abs(r["err_p"]), abs(r["err_rho"])) for r in val), "-")
    n.add("n_ref_points", len(val), "-")
    # recon trap quantified: geometric z used as geopotential
    zt = 20000.0
    Hfake = zt  # pretend z is H, i.e. evaluate at geometric altitude whose H equals 20 km
    zfake = Hfake * R0 / (R0 - Hfake)
    n.add("rho_20km_if_z_used_as_H", isa(zfake)["rho"], "kg/m^3",
          note="error made by treating geometric z as geopotential H")
    n.add("density_ratio_sl_20km", isa(0)["rho"] / isa(20000)["rho"], "-")
    n.add("density_ratio_sl_19km", isa(0)["rho"] / isa(19000)["rho"], "-")
    n.add("density_ratio_3_15km", isa(3000)["rho"] / isa(15000)["rho"], "-")
    n.save()
    print(f"p1 atmos: {len(z)} levels, {len(val)} ref points, max ref err "
          f"{n.items['p1.max_ref_err_frac']['value']:.2e}")


if __name__ == "__main__":
    main()
