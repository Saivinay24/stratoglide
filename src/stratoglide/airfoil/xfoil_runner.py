"""Headless XFOIL 6.99 runner: one polar per (foil, Re, Ncrit), cached by input hash.

Sweep: alpha 0 -> +max then (fresh BL init) 0 -> min, step 0.25 deg, warm start along each branch.
If XFOIL hangs, the process is killed after `timeout` s; converged points already in the PACC file are
kept and the sweep restarts one step past the last converged alpha (the hanging point is recorded as
non-converged). Graphics are disabled with PLOP / G F.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from ..common import CACHE, TOOLS_BIN, load_cfg, sha256_file
from .uiuc_loader import normalized_dat

XFOIL = TOOLS_BIN / "xfoil"
VERSION_TAG = "xfoil6.99-v2"


def _parse_polar(path: Path):
    rows = []
    if not path.exists():
        return rows
    started = False
    for ln in path.read_text().splitlines():
        if ln.strip().startswith("------"):
            started = True
            continue
        if started:
            t = ln.split()
            if len(t) >= 7:
                rows.append([float(x) for x in t[:7]])
    return rows


def _run_branch(dat: Path, re_: float, ncrit: float, a0: float, a1: float, step: float, wd: Path,
                timeout: float, iters: int = 200):
    """Run alpha a0 -> a1 (inclusive) with restarts past hangs. Returns rows and non-converged alphas."""
    rows, nonconv = [], []
    sgn = 1.0 if a1 >= a0 else -1.0
    start = a0
    tries = 0
    while sgn * (a1 - start) >= -1e-9 and tries < 40:
        tries += 1
        pol = wd / f"pol_{tries}.txt"
        if pol.exists():
            pol.unlink()
        cmds = ["PLOP", "G F", "", f"LOAD {dat.name}", "PANE", "OPER", f"VISC {re_:.0f}", "VPAR", f"N {ncrit}", "",
                f"ITER {iters}", "PACC", pol.name, "", f"ASEQ {start:.3f} {a1:.3f} {sgn * step:.3f}", "PACC", "",
                "QUIT"]
        timed_out = False
        try:
            subprocess.run([str(XFOIL)], input="\n".join(cmds) + "\n", text=True, capture_output=True,
                           timeout=timeout, cwd=wd)
        except subprocess.TimeoutExpired:
            timed_out = True
        got = _parse_polar(pol)
        rows += got
        if not timed_out:
            break
        last = got[-1][0] if got else start - sgn * step
        hang = last + sgn * step
        nonconv.append(round(hang, 3))
        start = hang + sgn * step
    return rows, nonconv


def polar(foil: str, re_: float, ncrit: float, amin=-4.0, amax=14.0, step=0.25, timeout=40.0, nocache=False):
    dat = normalized_dat(foil)
    key = hashlib.sha256(json.dumps([VERSION_TAG, sha256_file(dat), sha256_file(XFOIL), re_, ncrit, amin, amax,
                                     step]).encode()).hexdigest()[:20]
    cdir = CACHE / "xfoil"
    cdir.mkdir(parents=True, exist_ok=True)
    cf = cdir / f"{foil}_{int(re_)}_{ncrit}_{key}.json"
    if cf.exists() and not nocache:
        return json.loads(cf.read_text())
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        local = wd / "foil.dat"
        local.write_text(dat.read_text())
        up, nc1 = _run_branch(local, re_, ncrit, 0.0, amax, step, wd, timeout)
        dn, nc2 = _run_branch(local, re_, ncrit, -step, amin, step, wd, timeout)
    rows = sorted({round(r[0], 3): r for r in up + dn}.values())
    out = {"foil": foil, "re": re_, "ncrit": ncrit, "alpha": [r[0] for r in rows], "cl": [r[1] for r in rows],
           "cd": [r[2] for r in rows], "cdp": [r[3] for r in rows], "cm": [r[4] for r in rows],
           "xtr_top": [r[5] for r in rows], "xtr_bot": [r[6] for r in rows], "nonconverged": nc1 + nc2,
           "n_requested": int(round((amax - amin) / step)) + 1, "cache_key": key}
    if rows and not nocache:  # never cache an empty polar
        cf.write_text(json.dumps(out))
    return out


def dump_bl(foil: str, re_: float, ncrit: float, alpha: float, timeout=40.0):
    """Converge at alpha (warm-started from 0) and DUMP the BL; return upper-surface separation extent.

    Bubble extent = chord fraction of the upper surface with Cf < 0 between laminar separation and
    reattachment (largest contiguous negative-Cf run upstream of the trailing-edge 5%)."""
    dat = normalized_dat(foil)
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        local = wd / "foil.dat"
        local.write_text(dat.read_text())
        dmp = wd / "bl.dmp"
        seq = [f"ALFA {a:.3f}" for a in np.arange(0.0, alpha + 1e-9, 0.5 if alpha >= 0 else -0.5)] + [f"ALFA {alpha:.3f}"]
        cmds = ["PLOP", "G F", "", f"LOAD {local.name}", "PANE", "OPER", f"VISC {re_:.0f}", "VPAR", f"N {ncrit}", "",
                "ITER 200"] + seq + [f"DUMP {dmp.name}", "", "QUIT"]
        try:
            subprocess.run([str(XFOIL)], input="\n".join(cmds) + "\n", text=True, capture_output=True,
                           timeout=timeout, cwd=wd)
        except subprocess.TimeoutExpired:
            return None
        if not dmp.exists():
            return None
        rows = []
        for ln in dmp.read_text().splitlines():
            if ln.startswith("#"):
                continue
            t = ln.split()
            if len(t) >= 7:
                try:
                    rows.append([float(x) for x in t[:8]])
                except ValueError:
                    pass
    a = np.array(rows)
    # columns: s x y Ue/Vinf Dstar Theta Cf H ; upper surface = from TE (first row) to LE (min x)
    ile = int(np.argmin(a[:, 1][: len(a) // 2 + 40])) if len(a) else 0
    up = a[: ile + 1][::-1]  # LE -> TE
    x, cf = up[:, 1], up[:, 6]
    neg = (cf < 0) & (x < 0.95)
    best, cur, start = 0.0, 0.0, None
    for i in range(len(x)):
        if neg[i]:
            if start is None:
                start = i
            cur = x[i] - x[start]
            best = max(best, cur)
        else:
            start = None
    return {"bubble_extent": float(best), "alpha": alpha}


def _job(args):
    foil, re_, nc = args
    p = polar(foil, re_, nc)
    return foil, re_, nc, len(p["alpha"]), len(p["nonconverged"])


def sweep(foils, res, ncrits, jobs=8):
    tasks = [(f, r, n) for f in foils for r in res for n in ncrits]
    with Pool(jobs) as pool:
        out = pool.map(_job, tasks, chunksize=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--foils", nargs="+", default=["all"])
    ap.add_argument("--re", nargs="+", default=["all"])
    ap.add_argument("--ncrit", nargs="+", default=["all"])
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    ds = load_cfg("design_space")["airfoils"]
    foils = ds["candidates"] if a.foils == ["all"] else a.foils
    res = ds["sweep_re"] if a.re == ["all"] else [float(x) for x in a.re]
    ncs = ds["sweep_ncrit"] if a.ncrit == ["all"] else [float(x) for x in a.ncrit]
    for row in sweep(foils, res, ncs, a.jobs):
        print(*row)


if __name__ == "__main__":
    main()
