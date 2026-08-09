"""P1 flight-envelope map: Re, q and Mach over altitude 0-35 km x V_TAS 5-150 m/s.

Overlays constant-EAS lines and M = 0.5 / 0.7. Chords 0.10-0.35 m.
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .atmos import RHO0, isa
from .common import Numbers, phase_dir, write_json


def re_number(z, v_tas, chord):
    s = isa(z)
    return s["rho"] * v_tas * chord / s["mu"]


def tas_from_eas(z, v_eas):
    return v_eas / np.sqrt(isa(z)["sigma"])


def loiter_state(z, wing_loading, cl, chord):
    """Level flight at given W/S [N/m^2], CL and chord: V_TAS, q, Re, Mach."""
    s = isa(z)
    q = wing_loading / cl
    v = np.sqrt(2 * q / s["rho"])
    return {"v_tas": v, "q": q, "re": s["rho"] * v * chord / s["mu"], "mach": v / s["a"],
            "v_eas": v * np.sqrt(s["sigma"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chords", type=float, nargs="+", default=[0.10, 0.15, 0.20, 0.25, 0.30, 0.35])
    a = ap.parse_args()
    d = phase_dir("p1")
    z = np.linspace(0, 35000, 141)
    v = np.linspace(5, 150, 146)
    Z, V = np.meshgrid(z, v, indexing="ij")
    s = isa(Z)
    q = 0.5 * s["rho"] * V ** 2
    mach = V / s["a"]
    env = {"z_m": z, "v_tas": v, "chords": a.chords,
           "re": {f"{c:.2f}": (s["rho"] * V * c / s["mu"]).tolist() for c in a.chords},
           "q": q.tolist(), "mach": mach.tolist()}
    write_json(d / "envelope.json", env)

    fig, axs = plt.subplots(1, 2, figsize=(13, 5.2))
    c = 0.25
    re = s["rho"] * V * c / s["mu"]
    cs = axs[0].contourf(V, Z / 1000, np.log10(re), levels=np.arange(3.5, 6.6, 0.1), cmap="viridis")
    cl = axs[0].contour(V, Z / 1000, re, levels=[3e4, 6e4, 1e5, 2e5, 5e5], colors="w", linewidths=0.8)
    axs[0].clabel(cl, fmt=lambda x: f"Re {x/1e3:.0f}k")
    fig.colorbar(cs, ax=axs[0], label="log10 Re (c = 0.25 m)")
    for veas, ls in ((9.0, "--"), (12.0, "-."), (27.0, ":")):
        axs[0].plot(veas / np.sqrt(isa(z)["sigma"]), z / 1000, "r" + ls, lw=1.2, label=f"EAS {veas:.0f} m/s")
    for m in (0.5, 0.7):
        axs[0].plot(m * isa(z)["a"], z / 1000, "k-", lw=1.0)
    axs[0].set_xlim(5, 150); axs[0].set_xlabel("V_TAS (m/s)"); axs[0].set_ylabel("geometric altitude (km)")
    axs[0].legend(loc="lower right", fontsize=8); axs[0].set_title("Chord Re map with constant-EAS and M 0.5/0.7")
    cs2 = axs[1].contourf(V, Z / 1000, np.log10(q), levels=np.arange(0, 4.2, 0.1), cmap="magma")
    fig.colorbar(cs2, ax=axs[1], label="log10 q (Pa)")
    cm = axs[1].contour(V, Z / 1000, mach, levels=[0.1, 0.2, 0.3, 0.5, 0.7], colors="c", linewidths=0.8)
    axs[1].clabel(cm, fmt=lambda x: f"M {x:.1f}")
    axs[1].set_xlabel("V_TAS (m/s)"); axs[1].set_title("Dynamic pressure and Mach")
    fig.tight_layout(); fig.savefig(d / "p1_re_map.png", dpi=130); plt.close(fig)

    n = Numbers("p1", "src/stratoglide/reynolds.py")
    # anchor (NOT an input to design, sanity band only): plan section 1.2
    for zk in (0, 19000, 20000, 25000):
        st = loiter_state(zk, 56.9, 0.8, 0.24)
        n.add(f"anchor_re_{zk // 1000}km", st["re"], "-", note="hand-calc anchor W/S 56.9, CL 0.8, c 0.24")
        n.add(f"anchor_vtas_{zk // 1000}km", st["v_tas"], "m/s")
    n.add("mach_limited_vne_eas_25km_m05", 0.5 * isa(25000)["a"] * np.sqrt(isa(25000)["sigma"]), "m/s")
    prev = {}
    try:
        from .common import read_json
        prev = read_json(d / "numbers.json")
    except Exception:
        pass
    prev.update(n.items)
    write_json(d / "numbers.json", prev)
    print("p1 envelope written")


if __name__ == "__main__":
    main()
