"""P2 step B: score the 8 candidates with the pre-registered weights; argmax, no hand override.

Bands come from the design Re floor (downgrade D1, see HONEST_LOG) using the pre-registered band rules.
Stall gentleness uses NeuralFoil for every candidate (pre-registered: XFOIL post-stall is unreliable).
Robustness: the scoring is repeated at Ncrit 7, 9, 11, 12; if the design-Ncrit winner is not the winner at
every one of them, the candidate with the best mean rank wins and the flip is logged.
Tail section rule: lowest mean CD over |alpha| <= 4 deg, averaged over the tail Re grid, at design Ncrit.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import kendalltau

from ..common import Numbers, ROOT, load_cfg, phase_dir, read_json, write_json, latest_phase_file
from . import neuralfoil_runner, xfoil_runner
from .uiuc_loader import normalized_dat, thickness
from .validate import _monotonic_branch


def foil_metrics(foil, loiter_res, return_res, nc):
    endur, rng, clmax, cm0, bub, gent, nfdel = [], [], [], [], [], [], []
    for r in loiter_res:
        p = xfoil_runner.polar(foil, float(r), float(nc))
        a, cl, cd = _monotonic_branch(p["alpha"], p["cl"], p["cd"])
        m = cl > 0
        e = cl[m] ** 1.5 / cd[m]
        i = int(np.argmax(e))
        endur.append(float(e[i]))
        a_end = float(a[m][i])
        clmax.append(float(np.max(p["cl"])))
        cm0.append(float(np.interp(0.0, p["alpha"], p["cm"])))
        bl = xfoil_runner.dump_bl(foil, float(r), float(nc), a_end)
        bub.append(bl["bubble_extent"] if bl else np.nan)
        pn = neuralfoil_runner.polar(foil, float(r), float(nc), amin=-4.0, amax=20.0)
        an, cln = np.array(pn["alpha"]), np.array(pn["cl"])
        j = int(np.argmax(cln))
        gent.append(-float(cln[j] - np.interp(an[j] + 2.0, an, cln)))
        cd_nf = float(np.interp(a_end, an, pn["cd"]))
        nfdel.append(cd_nf / float(cd[m][i]) - 1)
    for r in return_res:
        p = xfoil_runner.polar(foil, float(r), float(nc))
        a, cl, cd = _monotonic_branch(p["alpha"], p["cl"], p["cd"])
        m = cl > 0
        rng.append(float(np.max(cl[m] / cd[m])))
    tc = thickness(np.loadtxt(normalized_dat(foil), skiprows=1))
    return {"endurance_cl15cd_loiter": float(np.mean(endur)), "range_ld_return": float(np.mean(rng)),
            "clmax_loiter": float(np.mean(clmax)), "cm0_loiter": float(np.mean(cm0)),
            "stall_gentleness": float(np.mean(gent)), "bubble_extent_loiter": float(np.nanmean(bub)),
            "thickness": tc, "nf_cd_delta_loiter": [float(x) for x in nfdel]}


def score(mets: dict, weights: dict):
    names = list(mets)
    tot = {f: 0.0 for f in names}
    for k, w in weights.items():
        v = np.array([mets[f][k] for f in names], float)
        if k == "bubble_extent_loiter":
            v = -v
        lo, hi = np.nanmin(v), np.nanmax(v)
        nv = (v - lo) / (hi - lo) if hi > lo else np.ones_like(v)
        for f, x in zip(names, nv):
            tot[f] += w * float(x)
    return tot


def own_lift_data(foil):
    """Own tunnel lift runs for a candidate: Vol 3 primary (E387, SD7037), Vol 5 (S1223)."""
    from .uiuc_loader import PRIMARY, ascending_branch, load_series
    from .validate_selected import FILES, load_vol5_lift
    runs = []
    if foil in PRIMARY:
        for nom, v in load_series(foil, "primary").items():
            if "lift" in v:
                runs.append({"re": v["re"], "lift": ascending_branch(v["lift"]), "src": "UIUC Vol 3"})
    elif foil in FILES:
        for r in load_vol5_lift(foil):
            runs.append({"re": r["re"], "lift": ascending_branch(r["lift"]), "src": "UIUC Vol 5"})
    return runs


def apply_gate(out):
    """D3: disqualify candidates whose own tunnel CLmax error exceeds the bar inside the loiter band."""
    bar = load_cfg("bars")["validation"]["clmax_abs_err_max"]
    lo, hi = min(out["loiter_band_re"]), max(out["loiter_band_re"])
    nc = out["design_ncrit"]
    order = out["per_ncrit"][str(nc)]["order"]
    start = order.index(out["selected"]) if out["selected"] in order else 0
    ranked = [out["selected"]] + [f for f in order if f != out["selected"]]
    gate = {}
    final = None
    for f in ranked:
        rows = []
        for r in own_lift_data(f):
            if 0.95 * lo <= r["re"] <= 1.05 * hi:
                p = xfoil_runner.polar(f, float(round(r["re"])), float(nc))
                e = abs(float(np.max(p["cl"])) - float(np.max(r["lift"][:, 1])))
                rows.append({"re": r["re"], "clmax_exp": float(np.max(r["lift"][:, 1])),
                             "clmax_xfoil": float(np.max(p["cl"])), "err": e, "src": r["src"]})
        ok = all(x["err"] <= bar for x in rows)
        gate[f] = {"own_data_rows": rows, "has_own_data": bool(rows), "pass": ok}
        if ok and final is None:
            final = f
            break
    out["gate_d3"] = gate
    out["selected_pre_gate"] = out["selected"]
    out["selected"] = final
    return out


def main():
    import sys
    if "--gate-only" in sys.argv:
        d = phase_dir("p2")
        out = read_json(latest_phase_file("p2", "selection.json"))
        out["selected"] = out.get("selected_pre_gate", out["selected"])
        out = apply_gate(out)
        write_json(d / "selection.json", out)
        _save_numbers(out)
        write_rationale(out)
        print("gate:", {k: (v["pass"], [round(x["err"], 2) for x in v["own_data_rows"]]) for k, v in out["gate_d3"].items()},
              "selected", out["selected"])
        return
    ds = load_cfg("design_space")
    bars = load_cfg("bars")
    val = read_json(latest_phase_file("p2", "validation.json"))
    nc = val["design_ncrit"]
    floor = val["re_design_floor"]
    grid = ds["airfoils"]["sweep_re"]
    loiter_res = [r for r in grid if floor <= r <= 1.6 * floor]
    return_res = [r for r in grid if 1.6 * floor < r <= 3.2 * floor]
    cands = [f for f in ds["airfoils"]["candidates"]]
    w = ds["selection"]["weights"]
    per_nc, ranks = {}, {}
    for n_ in sorted({nc, *bars["selection"]["ncrit_robustness"]}):
        mets = {f: foil_metrics(f, loiter_res, return_res, n_) for f in cands}
        mets = {f: m for f, m in mets.items() if m["thickness"] >= ds["selection"]["min_tc"]}
        sc = score(mets, w)
        order = sorted(sc, key=lambda f: -sc[f])
        per_nc[n_] = {"metrics": mets, "scores": sc, "order": order}
        ranks[n_] = {f: order.index(f) + 1 for f in order}
    design = per_nc[nc]
    winner = design["order"][0]
    rob = bars["selection"]["ncrit_robustness"]
    stable = all(per_nc[n_]["order"][0] == winner for n_ in rob)
    taus = {}
    top3 = design["order"][:3]
    for n_ in rob:
        taus[n_] = float(kendalltau([ranks[nc][f] for f in top3], [ranks[n_][f] for f in top3]).statistic)
    chosen = winner
    if not stable:
        mean_rank = {f: np.mean([ranks[n_][f] for n_ in rob]) for f in design["order"]}
        chosen = min(mean_rank, key=lambda f: (mean_rank[f], design["order"].index(f)))
    # tail screen
    tails = {}
    for t in ds["airfoils"]["tail_candidates"]:
        cds, clas, bubs = [], [], []
        for r in ds["airfoils"]["tail_re"]:
            p = xfoil_runner.polar(t, float(r), float(nc))
            a = np.array(p["alpha"]); m = np.abs(a) <= 4.0
            cds.append(float(np.mean(np.array(p["cd"])[m])))
            mm = np.abs(a) <= 3.0
            clas.append(float(np.polyfit(a[mm], np.array(p["cl"])[mm], 1)[0] * 180 / np.pi))
            bl = xfoil_runner.dump_bl(t, float(r), float(nc), 2.0)
            bubs.append(bl["bubble_extent"] if bl else np.nan)
        tails[t] = {"mean_cd_abs_alpha_le4": float(np.mean(cds)), "cla_per_rad": clas,
                    "cla_vs_2pi": [c / (2 * np.pi) for c in clas], "bubble_extent_alpha2": bubs}
    tail = min(tails, key=lambda t: tails[t]["mean_cd_abs_alpha_le4"])
    flags = {f: [x for x in design["metrics"][f]["nf_cd_delta_loiter"] if abs(x) > ds["selection"]["neuralfoil_disagree_flag"]]
             for f in design["metrics"]}
    out = {"design_ncrit": nc, "re_design_floor": floor, "re_min_validated_strict": val["re_min_validated"],
           "loiter_band_re": loiter_res, "return_band_re": return_res, "weights": w,
           "per_ncrit": {str(k): v for k, v in per_nc.items()}, "winner_design_ncrit": winner,
           "winner_stable_across_ncrit": stable, "kendall_tau_top3": taus, "selected": chosen,
           "tail_screen": tails, "tail_selected": tail, "neuralfoil_flags": flags}
    out = apply_gate(out)
    d = phase_dir("p2")
    write_json(d / "selection.json", out)
    _save_numbers(out)
    write_rationale(out)
    print("order", [(f, round(design["scores"][f], 3)) for f in design["order"]])
    print("winner", winner, "stable", stable, "taus", taus, "chosen", chosen, "tail", tail)


def _save_numbers(out):
    d = phase_dir("p2")
    nc = out["design_ncrit"]
    design = out["per_ncrit"][str(nc)]
    chosen = out["selected"]
    n = Numbers("p2", "src/stratoglide/airfoil/select.py")
    n.add("selected_airfoil", chosen, "-")
    n.add("argmax_winner_pre_gate", out["selected_pre_gate"], "-")
    n.add("selected_tail_airfoil", out["tail_selected"], "-")
    n.add("winner_stable_across_ncrit", out["winner_stable_across_ncrit"], "bool")
    n.add("kendall_tau_top3_min", min(out["kendall_tau_top3"].values()), "-")
    m = design["metrics"][chosen]
    n.add("sel_cl15cd_loiter", m["endurance_cl15cd_loiter"], "-")
    n.add("sel_ld_return", m["range_ld_return"], "-")
    n.add("sel_clmax_loiter", m["clmax_loiter"], "-")
    n.add("sel_cm0", m["cm0_loiter"], "-")
    n.add("sel_bubble_extent", m["bubble_extent_loiter"], "x/c")
    n.add("sel_score", design["scores"][chosen], "-")
    g = out["gate_d3"][out["selected_pre_gate"]]
    if g["own_data_rows"]:
        n.add("pre_gate_winner_max_clmax_err", max(x["err"] for x in g["own_data_rows"]), "-")
    p = d / "numbers.json"
    prev = read_json(p) if p.exists() else {}
    prev.update(n.items)
    write_json(p, prev)


def write_rationale(o):
    nc = o["design_ncrit"]
    des = o["per_ncrit"][str(nc)]
    m = des["metrics"][o["selected"]]
    lines = ["# SELECTION_RATIONALE (auto-generated by src/stratoglide/airfoil/select.py)", "",
             f"Selected wing section: **{o['selected']}**. Tail section: **{o['tail_selected']}**.", "",
             f"Argmax winner before the D3 own-data lift gate: **{o.get('selected_pre_gate', o['selected'])}**. "
             + "; ".join(f"{f}: own-data CLmax errors in the loiter band "
                         + (", ".join(f"Re {x['re']/1e3:.0f}k {x['err']:.2f}" for x in g['own_data_rows']) or "none available")
                         + (" (PASS)" if g['pass'] else " (FAIL, disqualified)") for f, g in o.get('gate_d3', {}).items()) + ".", "",
             f"Design Ncrit {nc} (validation rule). Loiter band Re {o['loiter_band_re']}, return band Re "
             f"{o['return_band_re']}, from the design floor Re {o['re_design_floor']} (downgrade D1). The strict "
             f"validated floor is Re {o['re_min_validated_strict']}; see HONEST_LOG.", "",
             "| Rank | Airfoil | Score | CL^1.5/CD loiter | L/D return | CLmax | Cm0 | bubble x/c | gentleness | t/c |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(des["order"]):
        x = des["metrics"][f]
        lines.append(f"| {i+1} | {f} | {des['scores'][f]:.3f} | {x['endurance_cl15cd_loiter']:.1f} | "
                     f"{x['range_ld_return']:.1f} | {x['clmax_loiter']:.3f} | {x['cm0_loiter']:.4f} | "
                     f"{x['bubble_extent_loiter']:.3f} | {x['stall_gentleness']:.3f} | {x['thickness']:.3f} |")
    lines += ["", f"Winner at design Ncrit: {o['winner_design_ncrit']}. Stable across Ncrit "
              f"{list(o['kendall_tau_top3'])}: {o['winner_stable_across_ncrit']}. Kendall tau of the design top-3 "
              f"ranks at each Ncrit: {', '.join(f'N{k} {v:.2f}' for k, v in o['kendall_tau_top3'].items())}.", "",
              f"Bubble behaviour: at the endurance-optimum alpha the {o['selected']} upper-surface separated (Cf < 0) "
              f"region spans {m['bubble_extent_loiter']:.3f} of chord, averaged over the loiter band (XFOIL DUMP).",
              f"NeuralFoil vs XFOIL CD at the same point: {', '.join(f'{100*x:+.1f}%' for x in m['nf_cd_delta_loiter'])}.",
              "", "Stall gentleness is the NeuralFoil CL drop over 2 deg past CLmax (negative number, closer to 0 is "
              "gentler), used for every candidate.", "",
              "## Tail screen", "", "| Section | mean CD (abs alpha <= 4) | CLa / 2pi per Re | bubble x/c at alpha 2 |",
              "|---|---|---|---|"]
    for t, v in o["tail_screen"].items():
        lines.append(f"| {t} | {v['mean_cd_abs_alpha_le4']:.4f} | {', '.join(f'{x:.2f}' for x in v['cla_vs_2pi'])} | "
                     f"{', '.join(f'{x:.2f}' for x in v['bubble_extent_alpha2'])} |")
    lines += ["", "Tail Re 30k-50k is inside the laminar-bubble band; P5 carries +/-20% tail effectiveness."]
    (phase_dir("p2") / "SELECTION_RATIONALE.md").write_text("\n".join(lines) + "\n")
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "SELECTION_RATIONALE.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
