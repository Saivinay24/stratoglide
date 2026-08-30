"""Weight and balance: item table (mass, x, y, z), CG, and the battery position solved for a CG target.

Distributed structure (wing, tails, boom) is split into point masses so the same table gives the AVL .mass
inertias. The battery is the mover; its x is solved so CG = target and clamped to the pod.
"""
from __future__ import annotations

import numpy as np

from ..common import load_cfg


def items(g, masses):
    c = load_cfg("components")
    fx = c["fixed"]
    pod = g["pod"]
    xn = pod["x_nose"]
    L = []

    def add(name, m, x, y=0.0, z=0.0):
        L.append({"item": name, "mass_kg": float(m), "x": float(x), "y": float(y), "z": float(z)})

    # wing shell + spar as 8 strips per side at 40% local chord
    n = 8
    sec = g["wing_sections"]
    for side in (-1, 1):
        for k in range(n):
            f = (k + 0.5) / n
            y = f * g["b"] / 2
            chord = g["c_root"] + f * (g["c_tip"] - g["c_root"])
            w = chord / ((g["c_root"] + g["c_tip"]) / 2) / (2 * n)
            xle = sec[0]["x_le"] + f * (sec[1]["x_le"] - sec[0]["x_le"])
            z = f * sec[1]["z"]
            add(f"wing_shell_{'L' if side < 0 else 'R'}{k}", masses["wing_shell"] * w, xle + 0.40 * chord, side * y, z)
            add(f"wing_spar_{'L' if side < 0 else 'R'}{k}", masses["wing_spar"] * w, xle + 0.25 * chord, side * y, z)
    h, v = g["htail"], g["vtail"]
    mt = masses["tails"]
    for side in (-1, 1):
        add(f"htail_{'L' if side < 0 else 'R'}", mt * h["S"] / (h["S"] + v["S"]) / 2, h["x_le"] + 0.4 * h["chord"],
            side * h["b"] / 4, h["z"])
    add("vtail", mt * v["S"] / (h["S"] + v["S"]), v["x_le"] + 0.4 * v["chord"], 0.0, v["z0"] + v["h"] * 0.45)
    bm = g["boom"]
    for k in range(4):
        add(f"boom_{k}", masses["boom"] / 4, bm["x0"] + (k + 0.5) / 4 * bm["length"], 0.0, bm["z"])
    add("pod_shell", masses["pod"], xn + 0.45 * pod["length"], 0, pod["z"])
    add("payload_eo_gimbal", fx["payload"]["mass_kg"], xn + 0.17, 0, pod["z"] - 0.06)
    add("payload_insulation", masses["payload_insulation"], xn + 0.17, 0, pod["z"] - 0.06)
    add("airspeed_sensor", fx["airspeed_sensor"]["mass_kg"], xn + 0.05, 0, pod["z"])
    for k in ("flight_controller", "gnss", "telemetry"):
        add(k, fx[k]["mass_kg"], xn + 0.30, 0, pod["z"] + 0.02)
    add("servos_wing", fx["servos"]["mass_kg"] * 2 / 5, g["x_ac_wing"] + 0.1 * g["mac"], 0, 0.0)
    add("servos_tail", fx["servos"]["mass_kg"] * 3 / 5, xn + 0.60, 0, pod["z"])
    add("parachute_release", fx["parachute_release"]["mass_kg"], xn + 0.55, 0, pod["z"] + 0.02)
    add("esc", fx["esc"]["mass_kg"], xn + 0.06, 0, pod["z"])
    add("motor", masses["motor"], xn + 0.02, 0, pod["z"])
    add("propeller", masses["propeller"], g["prop"]["x"], 0, pod["z"])
    add("wiring", masses["wiring"], xn + 0.35, 0, pod["z"])
    add("margin_distributed", masses["margin"], None if False else 0.0, 0, 0.0)  # placed at CG of the rest below
    add("battery_pack", masses["battery"], 0.0, 0, pod["z"])
    add("battery_insulation", masses["insulation"], 0.0, 0, pod["z"])
    add("heater", fx["heater"]["mass_kg"], 0.0, 0, pod["z"])
    return L


def solve(L, x_target, pod):
    movers = {"battery_pack", "battery_insulation", "heater"}
    rest = [r for r in L if r["item"] not in movers and r["item"] != "margin_distributed"]
    m_rest = sum(r["mass_kg"] for r in rest)
    x_rest = sum(r["mass_kg"] * r["x"] for r in rest) / m_rest
    mg = next(r for r in L if r["item"] == "margin_distributed")
    mg["x"] = x_rest  # margin mass assumed to land at the CG of the existing items
    mm = sum(r["mass_kg"] for r in L if r["item"] in movers)
    M = sum(r["mass_kg"] for r in L)
    xb = (x_target * M - sum(r["mass_kg"] * r["x"] for r in L if r["item"] not in movers)) / mm
    lo, hi = pod["x_nose"] + 0.12, pod["x_nose"] + pod["length"] - 0.10
    xb_c = float(np.clip(xb, lo, hi))
    for r in L:
        if r["item"] in movers:
            r["x"] = xb_c
    return {"x_battery": xb_c, "x_battery_unclamped": float(xb), "clamped": bool(xb_c != xb), "range": [lo, hi]}


def cg(L):
    M = sum(r["mass_kg"] for r in L)
    return {"mass": M, **{k: sum(r["mass_kg"] * r[k] for r in L) / M for k in ("x", "y", "z")}}


def inertia(L):
    c = cg(L)
    I = np.zeros((3, 3))
    for r in L:
        d = np.array([r["x"] - c["x"], r["y"] - c["y"], r["z"] - c["z"]])
        I += r["mass_kg"] * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return {"Ixx": I[0, 0], "Iyy": I[1, 1], "Izz": I[2, 2], "Ixz": -I[0, 2]}


def write_csv(L, path):
    with open(path, "w") as f:
        f.write("item,mass_kg,x_m,y_m,z_m,moment_x_kgm\n")
        for r in L:
            f.write(f"{r['item']},{r['mass_kg']:.6f},{r['x']:.5f},{r['y']:.5f},{r['z']:.5f},{r['mass_kg']*r['x']:.6f}\n")
