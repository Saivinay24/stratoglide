"""P2 step A: validate XFOIL (Ncrit family) and NeuralFoil against UIUC LSAT before any polar is trusted.

Metrics per (foil, Re, Ncrit, tool), all pre-registered in config/bars.yaml:
  cla_rel_err  : lift-curve slope from a linear fit over alpha in [-2, 5] deg (relative error)
  clmax_abs_err: |CLmax_model - CLmax_exp| (exp = ascending branch of the LIFT file)
  alpha_stall_err: alpha at CLmax difference (reported, no bar)
  cd_mape      : mean |CD_model(CL_exp) - CD_exp| / CD_exp over drag-file points with 0.3 <= CL <= 1.0
                 and alpha below the experimental stall alpha (model CD interpolated at the experimental CL
                 along the model's monotonic pre-stall CL branch)
  cl15cd_peak_rel_err: peak CL^1.5/CD relative error (reported)

Design Ncrit rule (pre-registered, written before results were seen):
  minimise mean over {E387, SD7037} x {100k, 200k} of (cd_mape/0.15 + cla_rel_err/0.10 + clmax_abs_err/0.10)/3;
  ties -> closest to 9. Re 60k and 300k are HELD OUT (reported, not used to choose Ncrit).
Re_min_validated = lowest Re in {60k, 100k, 200k, 300k} at which BOTH foils pass all three metrics at the
design Ncrit.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..common import Numbers, load_cfg, phase_dir, read_json, write_json
from . import neuralfoil_runner, xfoil_runner
from .uiuc_loader import ascending_branch, load_series

FOILS = ["E387", "SD7037"]


def _monotonic_branch(alpha, cl, cd):
    """Pre-stall branch with strictly increasing CL starting from the lowest alpha."""
    alpha, cl, cd = map(np.asarray, (alpha, cl, cd))
    if len(alpha) == 0:
        return alpha, cl, cd
    i_max = int(np.argmax(cl))
    a, c, d = alpha[: i_max + 1], cl[: i_max + 1], cd[: i_max + 1]
    keep = [0]
    for i in range(1, len(c)):
        if c[i] > c[keep[-1]]:
            keep.append(i)
    return a[keep], c[keep], d[keep]


def _fit_slope(alpha, cl, lo, hi):
    alpha, cl = np.asarray(alpha), np.asarray(cl)
    m = (alpha >= lo) & (alpha <= hi)
    if m.sum() < 3:
        return np.nan
    return float(np.polyfit(alpha[m], cl[m], 1)[0])


def metrics(model: dict, exp: dict, bars: dict):
    lift = ascending_branch(exp["lift"])
    drag = exp["drag"]
    a_lo, a_hi = bars["cla_alpha_range_deg"]
    cla_e = _fit_slope(lift[:, 0], lift[:, 1], a_lo, a_hi)
    cla_m = _fit_slope(model["alpha"], model["cl"], a_lo, a_hi)
    i_e = int(np.argmax(lift[:, 1]))
    clmax_e, astall_e = float(lift[i_e, 1]), float(lift[i_e, 0])
    if len(model["cl"]) == 0:
        return None
    cl_m = np.asarray(model["cl"])
    i_m = int(np.argmax(cl_m))
    clmax_m, astall_m = float(cl_m[i_m]), float(model["alpha"][i_m])
    a_b, cl_b, cd_b = _monotonic_branch(model["alpha"], model["cl"], model["cd"])
    lo, hi = bars["cl_range"]
    m = (drag[:, 1] >= lo) & (drag[:, 1] <= hi) & (drag[:, 0] < astall_e)
    errs, used, skipped = [], [], 0
    for a, c, d in drag[m][:, :3]:
        if c < cl_b.min() or c > cl_b.max():
            skipped += 1
            continue
        cdm = float(np.interp(c, cl_b, cd_b))
        errs.append(abs(cdm - d) / d)
        used.append([a, c, d, cdm])
    cd_mape = float(np.mean(errs)) if errs else np.nan
    # endurance parameter
    pe = drag[(drag[:, 1] > 0) & (drag[:, 0] < astall_e)]
    e_peak = float(np.max(pe[:, 1] ** 1.5 / pe[:, 2])) if len(pe) else np.nan
    pm = (cl_b > 0)
    m_peak = float(np.max(cl_b[pm] ** 1.5 / cd_b[pm])) if pm.any() else np.nan
    return {"cla_exp": cla_e, "cla_model": cla_m, "cla_rel_err": abs(cla_m / cla_e - 1),
            "clmax_exp": clmax_e, "clmax_model": clmax_m, "clmax_abs_err": abs(clmax_m - clmax_e),
            "alpha_stall_exp": astall_e, "alpha_stall_model": astall_m, "alpha_stall_err": astall_m - astall_e,
            "cd_mape": cd_mape, "cd_points_used": len(errs), "cd_points_skipped": skipped,
            "cl15cd_peak_exp": e_peak, "cl15cd_peak_model": m_peak, "cl15cd_peak_rel_err": m_peak / e_peak - 1,
            "matched": used}


def passes(mt: dict, bars: dict) -> dict:
    if mt is None:
        return {"cd": False, "cla": False, "clmax": False, "all": False}
    r = {"cd": bool(mt["cd_mape"] <= bars["cd_mape_max"]), "cla": bool(mt["cla_rel_err"] <= bars["cla_rel_err_max"]),
         "clmax": bool(mt["clmax_abs_err"] <= bars["clmax_abs_err_max"])}
    r["all"] = all(r.values())
    return r


def run():
    bars = load_cfg("bars")["validation"]
    ds = load_cfg("design_space")["airfoils"]
    res = ds["validation_re"]
    ncs = ds["sweep_ncrit"]
    out = {"bars": bars, "series": "primary: Vol3 E387 (C), Vol3 SD7037 (D); secondary: Vol1 E387 (A), SD7037 (B)",
           "results": {}, "scatter_secondary": {}}
    exp = {f: load_series(f, "primary") for f in FOILS}
    exp2 = {f: load_series(f, "secondary") for f in FOILS}
    for f in FOILS:
        for r in res:
            e = exp[f][r]
            for nc in ncs:
                for tool, mod in (("xfoil", xfoil_runner), ("neuralfoil", neuralfoil_runner)):
                    p = mod.polar(f, float(e["re"]), float(nc))  # model run at the tunnel's measured average Re
                    mt = metrics(p, e, bars)
                    key = f"{f}|{r}|{nc}|{tool}"
                    out["results"][key] = {"foil": f, "re_nominal": r, "re_actual": e["re"], "ncrit": nc, "tool": tool,
                                           "metrics": mt, "pass": passes(mt, bars),
                                           "n_converged": len(p["alpha"]),
                                           "nonconverged": p.get("nonconverged", [])}
            # tunnel-to-tunnel scatter (secondary series as the "model")
            if r in exp2[f] and "drag" in exp2[f][r]:
                e2 = exp2[f][r]
                l2 = ascending_branch(e2["lift"]) if "lift" in e2 else e2["drag"][:, :3]
                pseudo = {"alpha": e2["drag"][:, 0].tolist(), "cl": e2["drag"][:, 1].tolist(),
                          "cd": e2["drag"][:, 2].tolist()}
                mt = metrics(pseudo, e, bars)
                if mt:
                    mt["clmax_exp_secondary"] = float(np.max(l2[:, 1]))
                out["scatter_secondary"][f"{f}|{r}"] = mt
    # design Ncrit on 100k/200k only
    scores = {}
    for nc in ncs:
        vals = []
        for f in FOILS:
            for r in bars["re"]:
                mt = out["results"][f"{f}|{r}|{nc}|xfoil"]["metrics"]
                vals.append((mt["cd_mape"] / bars["cd_mape_max"] + mt["cla_rel_err"] / bars["cla_rel_err_max"]
                             + mt["clmax_abs_err"] / bars["clmax_abs_err_max"]) / 3)
        scores[nc] = float(np.mean(vals))
    best = min(ncs, key=lambda n: (round(scores[n], 9), abs(n - 9)))
    out["ncrit_scores"] = scores
    out["design_ncrit"] = best
    # Re_min_validated
    re_pass = {r: all(out["results"][f"{f}|{r}|{best}|xfoil"]["pass"]["all"] for f in FOILS) for r in res}
    out["re_pass_at_design_ncrit"] = re_pass
    passing = [r for r in res if re_pass[r]]
    out["re_min_validated"] = min(passing) if passing else None
    out["check5_pass"] = all(re_pass[r] for r in bars["re"])
    # D2 drag knockdown (design use only, never applied to the validation numbers above)
    kt = {}
    for r in res:
        per = {}
        for f in FOILS:
            mt = out["results"][f"{f}|{r}|{best}|xfoil"]["metrics"]
            per[f] = float(np.mean([d / dm for _, _, d, dm in mt["matched"]]))
        kt[r] = {"per_foil": per, "mean": float(np.mean(list(per.values()))), "max": float(max(per.values()))}
    out["drag_k"] = kt
    out["re_design_floor"] = load_cfg("downgrades")["re_design_floor"]
    return out, exp


def drag_k(re_, which="mean", vjson=None):
    """D2 knockdown factor at Re (log-interpolated, clamped to the validated Re range)."""
    if vjson is None:
        from ..common import latest_phase_file
        vjson = read_json(latest_phase_file("p2", "validation.json"))
    rs = sorted(int(k) for k in vjson["drag_k"])
    if which in ("mean", "max"):
        ks = [vjson["drag_k"][str(r)][which] for r in rs]
    else:  # per-foil measured knockdown (D4)
        ks = [vjson["drag_k"][str(r)]["per_foil"][which] for r in rs]
    return float(np.interp(np.log(np.clip(re_, rs[0], rs[-1])), np.log(rs), ks))


def plots(out, exp, d):
    nc_best = out["design_ncrit"]
    res = sorted({v["re_nominal"] for v in out["results"].values()})
    fig, axs = plt.subplots(2, len(res), figsize=(4.2 * len(res), 8), squeeze=False)
    cols = {5: "#7aa2f7", 7: "#9ece6a", 9: "#e0af68", 11: "#f7768e", 12: "#bb9af7"}
    for i, f in enumerate(FOILS):
        for j, r in enumerate(res):
            ax = axs[i, j]
            e = exp[f][r]["drag"]
            lo = np.nanmin(e[:, 3:7], axis=1)
            hi = np.nanmax(e[:, 3:7], axis=1)
            ax.errorbar(e[:, 2], e[:, 1], xerr=[e[:, 2] - lo, hi - e[:, 2]], fmt="ko", ms=3.5, lw=0.8,
                        label="UIUC LSAT (bars: spanwise wake-rake spread)", zorder=5)
            for nc in sorted(cols):
                v = out["results"][f"{f}|{r}|{nc}|xfoil"]
                p = xfoil_runner.polar(f, float(v["re_actual"]), float(nc))
                ax.plot(p["cd"], p["cl"], "-", color=cols[nc], lw=2.0 if nc == nc_best else 0.9,
                        label=f"XFOIL Ncrit {nc}" + (" (design)" if nc == nc_best else ""))
            pn = neuralfoil_runner.polar(f, float(v["re_actual"]), float(nc_best))
            ax.plot(pn["cd"], pn["cl"], "--", color="#444", lw=1.2, label=f"NeuralFoil xlarge Ncrit {nc_best}")
            mt = out["results"][f"{f}|{r}|{nc_best}|xfoil"]["metrics"]
            ax.set_title(f"{f}  Re {r/1e3:.0f}k   CD MAPE {100*mt['cd_mape']:.1f}%", fontsize=10)
            ax.set_xlim(0, 0.05); ax.set_ylim(-0.4, 1.6); ax.grid(alpha=0.3)
            ax.set_xlabel("CD"); ax.set_ylabel("CL")
            if i == 0 and j == 0:
                ax.legend(fontsize=6.5, loc="lower right")
    fig.tight_layout(); fig.savefig(d / "p2_validation.png", dpi=120); plt.close(fig)


def main():
    d = phase_dir("p2")
    out, exp = run()
    plots(out, exp, d)
    # slim the json (drop per-point match lists from secondary scatter only)
    write_json(d / "validation.json", out)
    n = Numbers("p2", "src/stratoglide/airfoil/validate.py")
    nc = out["design_ncrit"]
    n.add("design_ncrit", nc, "-")
    n.add("re_min_validated", out["re_min_validated"], "-")
    worst = {}
    for f in FOILS:
        for r in (60000, 100000, 200000, 300000):
            mt = out["results"][f"{f}|{r}|{nc}|xfoil"]["metrics"]
            tag = f"{f}_re{r//1000}k"
            n.add(f"cd_mape_{tag}", mt["cd_mape"], "-")
            n.add(f"cla_err_{tag}", mt["cla_rel_err"], "-")
            n.add(f"clmax_err_{tag}", mt["clmax_abs_err"], "-")
            n.add(f"pass_{tag}", out["results"][f"{f}|{r}|{nc}|xfoil"]["pass"]["all"], "bool")
            mtn = out["results"][f"{f}|{r}|{nc}|neuralfoil"]["metrics"]
            n.add(f"nf_cd_mape_{tag}", mtn["cd_mape"], "-")
            worst.setdefault(r, []).append(mt["cd_mape"])
            sc = out["scatter_secondary"].get(f"{f}|{r}")
            if sc:
                n.add(f"tunnel_scatter_cd_mape_{tag}", sc["cd_mape"], "-",
                      note="UIUC Vol1 vs Vol3 model of the same airfoil, same metric")
    n.add("cd_mape_re100k_200k_best", max(worst[100000] + worst[200000]), "-",
          note="worse of E387/SD7037 over Re 100k and 200k at the design Ncrit")
    n.add("cd_mape_re60k_worst", max(worst[60000]), "-")
    n.add("cd_mape_re300k_worst", max(worst[300000]), "-")
    n.add("check5_pass", out["check5_pass"], "bool")
    n.add("re_design_floor", out["re_design_floor"], "-", note="downgrade D1, see HONEST_LOG")
    for r, v in out["drag_k"].items():
        n.add(f"drag_k_mean_re{int(r)//1000}k", v["mean"], "-", note="downgrade D2 knockdown")
        n.add(f"drag_k_max_re{int(r)//1000}k", v["max"], "-")
    p = d / "numbers.json"
    prev = read_json(p) if p.exists() else {}
    prev.update(n.items)
    write_json(p, prev)
    print("design Ncrit", nc, "scores", {k: round(v, 3) for k, v in out["ncrit_scores"].items()})
    print("Re pass at design Ncrit", out["re_pass_at_design_ncrit"], "Re_min_validated", out["re_min_validated"])
    for f in FOILS:
        for r in (60000, 100000, 200000, 300000):
            mt = out["results"][f"{f}|{r}|{nc}|xfoil"]["metrics"]
            mn = out["results"][f"{f}|{r}|{nc}|neuralfoil"]["metrics"]
            print(f"{f} {r:6d} XFOIL cd_mape {mt['cd_mape']:.3f} cla {mt['cla_rel_err']:.3f} clmax {mt['clmax_abs_err']:.3f}"
                  f" | NF cd_mape {mn['cd_mape']:.3f} cla {mn['cla_rel_err']:.3f} clmax {mn['clmax_abs_err']:.3f}")


if __name__ == "__main__":
    main()
