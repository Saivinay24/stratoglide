"""2-DOF typical-section (pitch-plunge) flutter SCREEN at 75% semispan, Theodorsen aerodynamics, V-g method.
Screening estimate, NOT a clearance (GVT and proper aeroelastic analysis come before flight).

Coordinates: h plunge positive down (h~ = h/b), alpha nose up, a = elastic-axis position in semichords aft of
mid-chord, x_alpha = CG offset aft of EA in semichords, r_alpha^2 = I_alpha/(m b^2), mu = m/(pi rho b^2).
Theodorsen L (up) and M (nose up about EA) expressed as pi rho b^3 w^2 [...] and pi rho b^4 w^2 [...] give
(A + Z B) q = 0, Z = (w_alpha/w)^2 (1 + i g), B = diag(sigma^2, r_alpha^2), sigma = w_h/w_alpha.
Stiffness: bending EI from the P3 spar caps (cap area fixed, depth scaled with local chord); torsion GJ from a
Bredt closed-section skin (components.yaml structure.skin_torsion, ESTIMATE). Cantilever first modes:
w_h = 1.875^2 sqrt(EI/(m' L^4)), w_alpha = (pi/2) sqrt(GJ/(I_alpha' L^2)), L = semispan.
"""
from __future__ import annotations

import numpy as np
from scipy.special import hankel2

from ..atmos import isa
from ..common import Numbers, latest_phase_file, load_cfg, phase_dir, read_json, write_json


def theodorsen(k):
    H1, H0 = hankel2(1, k), hankel2(0, k)
    return H1 / (H1 + 1j * H0)


def vg(mu, a, xa, ra2, sig, ks=np.geomspace(3.0, 0.02, 600)):
    """Returns list of (k, [(U_over_b_walpha, g), ...]) for the two branches."""
    out = []
    for k in ks:
        C = theodorsen(k)
        Lh = -1 + 2j * C / k
        La = 1j / k + a + 2 * C / k ** 2 + 2j * C * (0.5 - a) / k
        Mh = -a + (a + 0.5) * 2j * C / k
        Ma = -1j * (0.5 - a) / k + 1 / 8 + a ** 2 + (a + 0.5) * (2 * C / k ** 2 + 2j * C * (0.5 - a) / k)
        A = np.array([[-1 + Lh / mu, -xa + La / mu], [-xa - Mh / mu, -ra2 - Ma / mu]])
        B = np.diag([sig ** 2, ra2])
        Z = np.linalg.eigvals(-np.linalg.solve(B, A))
        br = []
        for z in Z:
            if z.real <= 0:
                br.append((np.nan, np.nan))
                continue
            w_over_wa = 1 / np.sqrt(z.real)
            br.append((w_over_wa / k, z.imag / z.real))  # U/(b w_alpha) = (w/w_alpha)/k
        br.sort(key=lambda t: (np.nan_to_num(t[0], nan=1e9)))
        out.append((k, br))
    return out


def flutter_speed(mu, a, xa, ra2, sig, g_s=0.0):
    res = vg(mu, a, xa, ra2, sig)
    best = np.inf
    for j in range(2):
        prev = None
        for k, br in res:
            U, g = br[j]
            if np.isnan(U):
                prev = None
                continue
            if prev is not None and prev[1] < g_s <= g:
                f = (g_s - prev[1]) / (g - prev[1])
                best = min(best, prev[0] + f * (U - prev[0]))
            prev = (U, g)
    return best


def section():
    s = read_json(latest_phase_file("p3", "sizing.json"))
    comp = load_cfg("components")["structure"]
    sk, sf = comp["skin_torsion"], comp["section_flutter"]
    L = s["span_m"] / 2
    y = 0.75 * L
    c = s["c_root_m"] + (s["c_tip_m"] - s["c_root_m"]) * 0.75
    tc = read_json(latest_phase_file("p3", "geometry.json")).get("tc", 0.0907)
    h_loc = s["spar"]["h_m"] * c / s["c_root_m"]
    EI = comp["carbon_ud"]["E_pa"] * s["spar"]["A_cap_m2"] * h_loc ** 2 / 2
    A_enc = 0.65 * tc * c ** 2
    perim = 2.04 * c
    GJ = 4 * A_enc ** 2 * sk["G_pa"] * sk["t_m"] / perim
    m_span = (s["masses"]["wing_shell"] + s["masses"]["wing_spar"]) / s["span_m"]
    b = c / 2
    I_a = m_span * sf["r_alpha_sq"] * b ** 2
    w_h = 1.875 ** 2 * np.sqrt(EI / (m_span * L ** 4))
    w_a = (np.pi / 2) * np.sqrt(GJ / (I_a * L ** 2))
    a = (sf["ea_x_c"] - 0.5) / 0.5
    xa = (sf["cg_x_c"] - sf["ea_x_c"]) / 0.5
    return {"y_m": y, "chord_m": c, "b_m": b, "EI_Nm2": EI, "GJ_Nm2": GJ, "m_span_kgpm": m_span, "w_h": w_h, "w_a": w_a,
            "a": a, "x_alpha": xa, "r_alpha_sq": sf["r_alpha_sq"], "sigma": w_h / w_a, "g_s": sf["g_struct"]}


def main():
    sec = section()
    rows = []
    for z in (0.0, 5000.0, 10000.0, 15000.0, 20000.0, 25000.0):
        at = isa(z)
        rho = float(at["rho"])
        mu = sec["m_span_kgpm"] / (np.pi * rho * sec["b_m"] ** 2)
        Ub = flutter_speed(mu, sec["a"], sec["x_alpha"], sec["r_alpha_sq"], sec["sigma"], sec["g_s"])
        V = Ub * sec["b_m"] * sec["w_a"]
        rows.append({"z_m": z, "mu": mu, "U_over_b_walpha": Ub, "V_flutter_tas": V, "V_flutter_eas": V * np.sqrt(rho / 1.225),
                     "mach": V / float(at["a"])})
        print(rows[-1], flush=True)
    v_eas = min(r["V_flutter_eas"] for r in rows)
    m_lim = load_cfg("bars")["release"]["mach_p99_max"]
    vne = [{"z_m": r["z_m"], "vne_eas": min(v_eas / load_cfg("bars")["release"]["flutter_margin"],
                                             m_lim * float(isa(r["z_m"])["a"]) * np.sqrt(float(isa(r["z_m"])["rho"]) / 1.225))} for r in rows]
    out = {"section": sec, "rows": rows, "v_flutter_eas_min": v_eas, "vne": vne,
           "label": "screening estimate, not clearance"}
    write_json(phase_dir("p5") / "flutter.json", out)
    n = Numbers("p5", "src/stratoglide/release/flutter_screen.py")
    n.add("v_flutter_eas_min", v_eas, "m/s", note="screening estimate, not clearance")
    n.add("vne_eas_flutter_limited", v_eas / load_cfg("bars")["release"]["flutter_margin"], "m/s")
    for r in vne:
        n.add(f"vne_eas_{r['z_m']/1000:.0f}km", r["vne_eas"], "m/s")
    n.save()
    print("section", {k: round(v, 4) for k, v in sec.items()}, "V_fl EAS min", round(v_eas, 2))


if __name__ == "__main__":
    main()
