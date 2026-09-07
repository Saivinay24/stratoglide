"""P4 driver: AVL S&C at sea level vs 19/20 km, W&B finalisation, AeroSandbox cross-check, XFLR5 export.

W&B: the CG target is set from the AVL neutral point (SM = mid-band 11.5% MAC). The battery cannot reach it
inside the pod (P3 found it clamped), so the pod (with every item mounted in it) is shifted along x relative
to the wing: the classic wing-position lever. Boom mass is held at its sized value (position only).
"""
from __future__ import annotations

import copy
import csv

import numpy as np

from ..atmos import isa
from ..common import Numbers, OUTPUTS, latest_phase_file, load_cfg, phase_dir, read_json, write_json
from ..sizing import wb
from . import avl_runner, avl_writer, modes

GEO = OUTPUTS / "geometry"
POD_ITEMS_PREFIX = ("pod_shell", "payload", "airspeed", "flight_controller", "gnss", "telemetry", "servos_tail",
                    "parachute", "esc", "motor", "propeller", "wiring", "battery", "heater")


def load_items():
    return [{"item": r["item"], "mass_kg": float(r["mass_kg"]), "x": float(r["x_m"]), "y": float(r["y_m"]),
             "z": float(r["z_m"])} for r in csv.DictReader(open(latest_phase_file("p3", "wb.csv")))]


def shift_pod(items, dx):
    out = copy.deepcopy(items)
    for r in out:
        if r["item"].startswith(POD_ITEMS_PREFIX):
            r["x"] += dx
    mg = next(r for r in out if r["item"] == "margin_distributed")
    rest = [r for r in out if r["item"] != "margin_distributed"]
    mg["x"] = sum(r["mass_kg"] * r["x"] for r in rest) / sum(r["mass_kg"] for r in rest)
    return out


def files_for(g, sizing, items, tag="", res=1.0):
    GEO.mkdir(parents=True, exist_ok=True)
    c = wb.cg(items)
    avl = GEO / f"stratoglide{tag}.avl"
    mass = GEO / f"stratoglide{tag}.mass"
    avl_writer.write_avl(g, sizing, avl, c["x"], c["z"], flying_wing=(tag == "_flyingwing"), res=res)
    avl_writer.write_mass(items, mass)
    extra = [GEO / f"{g['airfoil']}.dat", GEO / f"{g['htail']['airfoil']}.dat"]
    return avl, mass, extra, c


def run_at(g, sizing, items, z, cl, tag="", res=1.0):
    avl, mass, extra, c = files_for(g, sizing, items, tag, res)
    st = isa(z)
    r = avl_runner.run_case(avl, mass, sizing["mtow_kg"], st["rho"], cl, extra_files=extra)
    r["cg"] = c
    r["atm"] = st
    return r


def asb_crosscheck(g, cg, alpha_deg, V=20.0, sr=12, cr=8):
    import aerosandbox as asb
    from ..airfoil.uiuc_loader import normalized_dat
    af = asb.Airfoil(name=g["airfoil"], coordinates=str(normalized_dat(g["airfoil"])))
    tf = asb.Airfoil(name=g["htail"]["airfoil"], coordinates=str(normalized_dat(g["htail"]["airfoil"])))
    s0, s1 = g["wing_sections"]
    wing = asb.Wing(name="wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[s0["x_le"], 0, 0], chord=s0["chord"], twist=0.0, airfoil=af),
        asb.WingXSec(xyz_le=[s1["x_le"], s1["y"], s1["z"]], chord=s1["chord"], twist=s1["twist_deg"], airfoil=af)])
    h, v = g["htail"], g["vtail"]
    ht = asb.Wing(name="htail", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[h["x_le"], 0, h["z"]], chord=h["chord"], airfoil=tf),
        asb.WingXSec(xyz_le=[h["x_le"], h["b"] / 2, h["z"]], chord=h["chord"], airfoil=tf)])
    vt = asb.Wing(name="fin", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[v["x_le"], 0, v["z0"]], chord=v["chord"], airfoil=tf),
        asb.WingXSec(xyz_le=[v["x_le"], 0, v["z0"] + v["h"]], chord=v["chord"], airfoil=tf)])
    ap = asb.Airplane(name="StratoGlide", xyz_ref=[cg["x"], 0, cg["z"]], wings=[wing, ht, vt],
                      s_ref=g["S"], c_ref=g["mac"], b_ref=g["b"])
    res = {}
    for a in (alpha_deg - 0.5, alpha_deg + 0.5):
        op = asb.OperatingPoint(velocity=V, alpha=a)
        out = asb.VortexLatticeMethod(airplane=ap, op_point=op, spanwise_resolution=sr, chordwise_resolution=cr).run()
        res[a] = out
    a0, a1 = sorted(res)
    CLa = (float(res[a1]["CL"]) - float(res[a0]["CL"])) / np.radians(a1 - a0)
    Cma = (float(res[a1]["Cm"]) - float(res[a0]["Cm"])) / np.radians(a1 - a0)
    return {"CLa": CLa, "Cma": Cma, "Xnp": cg["x"] - Cma / CLa * g["mac"]}


def xflr5_export(g, path):
    """XFLR5 plane XML (wing, elevator, fin). Import is a human step; not claimed as run."""
    s0, s1 = g["wing_sections"]
    h, v = g["htail"], g["vtail"]

    def sec(y, c, xo, dih, tw, foil):
        return (f"<Section><y_position>{y:.4f}</y_position><Chord>{c:.4f}</Chord><xOffset>{xo:.4f}</xOffset>"
                f"<Dihedral>{dih:.2f}</Dihedral><Twist>{tw:.2f}</Twist><x_number_of_panels>13</x_number_of_panels>"
                f"<x_panel_distribution>COSINE</x_panel_distribution><y_number_of_panels>19</y_number_of_panels>"
                f"<y_panel_distribution>INVERSE SINE</y_panel_distribution><Left_Side_FoilName>{foil}</Left_Side_FoilName>"
                f"<Right_Side_FoilName>{foil}</Right_Side_FoilName></Section>")
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE explane>', '<explane version="1.0">',
           "<Units><length_unit_to_meter>1</length_unit_to_meter><mass_unit_to_kg>1</mass_unit_to_kg></Units>",
           "<Plane><Name>StratoGlide</Name>",
           f"<wing><Name>Main Wing</Name><Type>MAINWING</Type><Position>0,0,0</Position><Tilt_angle>0</Tilt_angle>"
           f"<Symetric>true</Symetric><isFin>false</isFin><Sections>"
           + sec(0, s0["chord"], 0, g["dihedral_deg"], 0, g["airfoil"])
           + sec(s1["y"], s1["chord"], s1["x_le"], 0, s1["twist_deg"], g["airfoil"]) + "</Sections></wing>",
           f"<wing><Name>Elevator</Name><Type>ELEVATOR</Type><Position>{h['x_le']:.4f},0,{h['z']:.4f}</Position>"
           f"<Tilt_angle>0</Tilt_angle><Symetric>true</Symetric><isFin>false</isFin><Sections>"
           + sec(0, h["chord"], 0, 0, 0, h["airfoil"]) + sec(h["b"] / 2, h["chord"], 0, 0, 0, h["airfoil"]) + "</Sections></wing>",
           f"<wing><Name>Fin</Name><Type>FIN</Type><Position>{v['x_le']:.4f},0,{v['z0']:.4f}</Position>"
           f"<Tilt_angle>0</Tilt_angle><Symetric>false</Symetric><isFin>true</isFin><Sections>"
           + sec(0, v["chord"], 0, 0, 0, v["airfoil"]) + sec(v["h"], v["chord"], 0, 0, 0, v["airfoil"]) + "</Sections></wing>",
           "</Plane></explane>"]
    path.write_text("\n".join(xml) + "\n")


def main():
    bars = load_cfg("bars")["stability"]
    g = read_json(latest_phase_file("p3", "geometry.json"))
    sizing = read_json(latest_phase_file("p3", "sizing.json"))
    m = load_cfg("mission")
    d = phase_dir("p4")
    items = load_items()
    cl = sizing["cl_loiter"]
    sm_t = float(np.mean(bars["sm_pct"])) / 100
    # 1) NP at the P3 CG, 2) pod shift to put CG at NP - SM_target * MAC, 3) iterate once (NP ~ CG-independent)
    hist = []
    dx = 0.0
    for it in range(4):
        it_items = shift_pod(items, dx)
        r = run_at(g, sizing, it_items, m["loiter"]["alt_m"], cl)
        xnp = r["st"]["Xnp"]
        xcg = r["cg"]["x"]
        target = xnp - sm_t * g["mac"]
        M = sum(x["mass_kg"] for x in it_items)
        m_pod = sum(x["mass_kg"] for x in it_items if x["item"].startswith(POD_ITEMS_PREFIX))
        hist.append({"dx": dx, "xnp": xnp, "xcg": xcg, "sm": (xnp - xcg) / g["mac"]})
        if abs(xcg - target) < 2e-4:
            break
        dx += (target - xcg) * M / (m_pod + 0.5 * M * 0)  # margin item follows the CG, exact enough to iterate
    items = shift_pod(items, dx)
    g["pod"]["x_nose"] += dx
    g["prop"]["x"] += dx
    g["boom"]["x0"] += dx
    g["boom"]["length"] = g["boom"]["x1"] - g["boom"]["x0"]
    c = wb.cg(items)
    I = wb.inertia(items)
    g["cg"].update({"x": c["x"], "z": c["z"], "pod_shift_m": dx})
    g["mass"].update(I)
    write_json(d / "geometry_final.json", g)
    wb.write_csv(items, d / "wb.csv")
    cases = {"sl": 0.0, "alt19": m["loiter"]["alt_m"], "alt20": 20000.0}
    out = {"pod_shift_m": dx, "np_iterations": hist, "cases": {}}
    for name, z in cases.items():
        r = run_at(g, sizing, items, z, cl)
        st = r["st"]
        rho = r["atm"]["rho"]
        V = float(np.sqrt(2 * sizing["mtow_kg"] * 9.80665 / (rho * g["S"] * cl)))
        Alon, Alat = modes.state_space(st, sizing["mtow_kg"], I, g["S"], g["mac"], g["b"], rho, V, st.get("e", 0.9), g["AR"])
        named = modes.classify(r["eig"], Alon, Alat)
        mu_rel = 2 * sizing["mtow_kg"] / (rho * g["S"] * g["mac"])
        out["cases"][name] = {"z_m": z, "rho": rho, "V_tas": V, "mu_rel": mu_rel, "cg_x": c["x"],
                              "sm_pct": 100 * (st["Xnp"] - c["x"]) / g["mac"], "derivs": st, "eig_avl": r["eig"],
                              "modes": named, "trim_alpha_deg": st.get("Alpha"), "trim_elevator_deg": st.get("elevator")}
        (d / f"avl_st_{name}.txt").write_text(r["raw_st"])
        (d / f"avl_eig_{name}.txt").write_text(r["raw_eig"])
    # CG limits at 20 km (+/- 2% MAC, the MC spread)
    for tag, dd in (("cg_fwd", -0.02), ("cg_aft", 0.02)):
        it = copy.deepcopy(items)
        for x in it:
            x["x"] += dd * g["mac"]
        r = run_at(g, sizing, it, 20000.0, cl)
        out["cases"][f"alt20_{tag}"] = {"sm_pct": 100 * (r["st"]["Xnp"] - r["cg"]["x"]) / g["mac"],
                                        "eig_avl": r["eig"], "trim_elevator_deg": r["st"].get("elevator")}
    # restore canonical files
    files_for(g, sizing, items)
    # AeroSandbox cross-check at the 19 km trim alpha
    a19 = out["cases"]["alt19"]["trim_alpha_deg"]
    out["vlm_convergence"] = conv = {"avl": [], "asb": []}
    for res in (1.0, 1.5, 2.0, 2.5):  # 3.0 overflows AVL NVMAX=6000
        r = run_at(g, sizing, items, m["loiter"]["alt_m"], cl, tag="_conv", res=res)
        conv["avl"].append({"res": res, "CLa": r["st"]["CLa"], "Xnp": r["st"]["Xnp"]})
    for sr, cr in ((12, 8), (30, 12), (50, 16), (80, 20)):
        try:
            conv["asb"].append({"sr": sr, "cr": cr, **asb_crosscheck(g, c, a19, sr=sr, cr=cr)})
        except Exception as e:
            conv["asb"].append({"sr": sr, "cr": cr, "error": f"{type(e).__name__}: {e}"})
    fin_avl, fin_asb = conv["avl"][-1], [x for x in conv["asb"] if "Xnp" in x][-1]
    conv["avl_last_step_xnp_frac_mac"] = abs(conv["avl"][-1]["Xnp"] - conv["avl"][-2]["Xnp"]) / g["mac"]
    good = [x for x in conv["asb"] if "Xnp" in x]
    conv["asb_last_step_xnp_frac_mac"] = abs(good[-1]["Xnp"] - good[-2]["Xnp"]) / g["mac"]
    out["asb"] = {"CLa": float(fin_asb["CLa"]), "Cma": float(fin_asb["Cma"]), "Xnp": float(fin_asb["Xnp"]),
                  "avl_CLa": fin_avl["CLa"], "avl_Xnp": fin_avl["Xnp"],
                  "cla_rel": abs(fin_avl["CLa"] / float(fin_asb["CLa"]) - 1),
                  "xnp_frac_mac": abs(fin_avl["Xnp"] - float(fin_asb["Xnp"])) / g["mac"]}
    out["avl_span_efficiency"] = out["cases"]["alt19"]["derivs"].get("e")
    # flying-wing one-off (same wing, no tail, same CG)
    try:
        fw = run_at(g, sizing, items, m["loiter"]["alt_m"], cl, tag="_flyingwing")
        out["flying_wing_trade"] = {"sm_pct": 100 * (fw["st"]["Xnp"] - c["x"]) / g["mac"], "Cnb": fw["st"].get("Cnb"),
                                    "Cma": fw["st"].get("Cma"), "Cnr": fw["st"].get("Cnr"),
                                    "note": "same wing and CG, tail removed: quantifies what the tail provides"}
        write_json(d / "flying_wing_trade.json", out["flying_wing_trade"])
    except Exception as e:
        out["flying_wing_trade"] = {"error": str(e)}
    xflr5_export(g, GEO / "stratoglide_xflr5.xml")
    write_json(d / "stability.json", out)
    # numbers
    n = Numbers("p4", "src/stratoglide/stability/run_stability.py")
    n.add("pod_shift_m", dx, "m")
    n.add("x_cg_m", c["x"], "m")
    n.add("x_np_m", out["cases"]["alt19"]["derivs"]["Xnp"], "m")
    n.add("case_alt_m", 20000.0, "m")
    for k, v in out["cases"].items():
        if "derivs" not in v:
            n.add(f"sm_pct_{k}", v["sm_pct"], "%MAC")
            continue
        tag = k.replace("alt", "") + ("km" if k != "sl" else "")
        n.add(f"sm_pct_{tag}", v["sm_pct"], "%MAC")
        n.add(f"mu_rel_{tag}", v["mu_rel"], "-")
        n.add(f"v_tas_{tag}", v["V_tas"], "m/s")
        n.add(f"trim_alpha_deg_{tag}", v["trim_alpha_deg"], "deg")
        n.add(f"trim_elevator_deg_{tag}", v["trim_elevator_deg"], "deg")
        for dk in ("CLa", "Cma", "Cnb", "Clb", "Clp", "Cmq", "Cnr", "Cmd02", "Cld01", "Cnd03", "Cnd01"):
            if dk in v["derivs"]:
                n.add(f"{dk}_{tag}", v["derivs"][dk], "1/rad")
        for mk, mv in v["modes"].items():
            a = mv["avl"]
            n.add(f"{mk}_zeta_{tag}", a["zeta"], "-")
            n.add(f"{mk}_wn_{tag}", a["wn"], "rad/s")
            if a["period_s"]:
                n.add(f"{mk}_period_s_{tag}", a["period_s"], "s")
            if a["tau_s"]:
                n.add(f"{mk}_tau_s_{tag}", a["tau_s"], "s")
            if a["t_double_s"]:
                n.add(f"{mk}_t_double_s_{tag}", a["t_double_s"], "s")
            if a["t_half_s"]:
                n.add(f"{mk}_t_half_s_{tag}", a["t_half_s"], "s")
    n.add("sm_pct_sl", out["cases"]["sl"]["sm_pct"], "%MAC")
    n.add("sm_pct_20km", out["cases"]["alt20"]["sm_pct"], "%MAC")
    if "CLa" in out["asb"]:
        n.add("asb_CLa", out["asb"]["CLa"]); n.add("asb_Xnp_m", out["asb"]["Xnp"])
        n.add("avl_vs_asb_cla_rel", out["asb"]["cla_rel"]); n.add("avl_vs_asb_xnp_frac_mac", out["asb"]["xnp_frac_mac"])
    n.add("avl_span_efficiency", out["avl_span_efficiency"])
    if "sm_pct" in out["flying_wing_trade"]:
        n.add("flying_wing_sm_pct", out["flying_wing_trade"]["sm_pct"], "%MAC")
    n.save()
    for k, v in out["cases"].items():
        if "modes" in v:
            print(k, f"SM {v['sm_pct']:.2f}% mu {v['mu_rel']:.0f} V {v['V_tas']:.1f} a {v['trim_alpha_deg']:.2f} de {v['trim_elevator_deg']:.2f}",
                  {mk: (round(mv['avl']['zeta'], 3), round(mv['avl']['wn'], 3), round(mv['rel_diff_wn'], 3)) for mk, mv in v["modes"].items()})
        else:
            print(k, f"SM {v['sm_pct']:.2f}%", v["eig_avl"])
    print("conv", [(x["res"], round(x["CLa"], 3), round(x["Xnp"], 4)) for x in conv["avl"]],
          [(x["sr"], x["cr"], round(float(x["CLa"]), 3), round(float(x["Xnp"]), 4)) for x in conv["asb"] if "Xnp" in x])
    print("pod shift", round(dx, 4), "asb", out["asb"], "flying wing", out["flying_wing_trade"])


if __name__ == "__main__":
    main()
