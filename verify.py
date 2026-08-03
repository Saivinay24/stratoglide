#!/usr/bin/env python3
"""StratoGlide verifier: 21 numbered checks (0-20). Bars come from config/bars.yaml (frozen at P0).

Usage: uv run python verify.py [--checks 0,1,5] [--strict]
Prints [n] PASS/FAIL/SKIP name: measured vs bar. Exit code nonzero on any FAIL
(and on any SKIP with --strict).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from stratoglide import checks as C  # noqa: E402

CHECKS = [
    (0, "pre-registration sha256 (bars.yaml, mission.yaml)", C.check0),
    (1, "ISA vs USSA-1976 tabulated (geometric)", C.check1),
    (2, "mu(216.65 K), layer continuity, monotonic rho", C.check2),
    (3, "independent recompute of loiter Re, q, Mach", C.check3),
    (4, "determinism: XFOIL + NeuralFoil re-run", C.check4),
    (5, "XFOIL vs UIUC LSAT at Re 100k/200k", C.check5),
    (6, "Re 60k result present; Re_min_validated defined", C.check6),
    (7, "selection reproducible; Ncrit robustness", C.check7),
    (8, "mass loop converged; MTOW = sum(weights); CG match AVL .mass", C.check8),
    (9, "design meets MR-4/7/8/9; Opti vs grid MTOW", C.check9),
    (10, "battery cold derate + heater + cell temperature", C.check10),
    (11, "static stability SL and 20 km", C.check11),
    (12, "dynamic modes vs bars; altitude physics direction", C.check12),
    (13, "AVL vs AeroSandbox VLM", C.check13),
    (14, "JSBSim atmosphere; JSBSim vs own 6-DOF nominal", C.check14),
    (15, "release Monte Carlo bars", C.check15),
    (16, "energy sanity, motor off, all MC runs", C.check16),
    (17, "BEMT vs UIUC APC data; momentum bound", C.check17),
    (18, "variable pitch >= fixed pitch at every altitude", C.check18),
    (19, "glide range and endurance consistency", C.check19),
    (20, "build package, name checks, schema, lint, reproducibility", C.check20),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checks", default="")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    sel = {int(x) for x in a.checks.split(",") if x.strip()} if a.checks else None
    n_pass = n_fail = n_skip = 0
    results = []
    for n, name, fn in CHECKS:
        if sel is not None and n not in sel:
            continue
        try:
            status, msg = fn()
        except C.Skip as e:
            status, msg = "SKIP", str(e)
        except Exception as e:  # a crashing check is a failure, never a pass
            status, msg = "FAIL", f"check crashed: {type(e).__name__}: {e}"
        results.append({"n": n, "name": name, "status": status, "msg": msg})
        print(f"[{n}] {status} {name}: {msg}")
        n_pass += status == "PASS"
        n_fail += status == "FAIL"
        n_skip += status == "SKIP"
    total = len(results)
    print(f"\n{n_pass}/{total} PASS, {n_fail} FAIL, {n_skip} SKIP")
    (ROOT / "results").mkdir(exist_ok=True)
    with open(ROOT / "results" / "verify_last.json", "w") as f:
        json.dump({"pass": n_pass, "fail": n_fail, "skip": n_skip, "total": total, "results": results}, f, indent=1)
    if n_fail or (a.strict and n_skip):
        sys.exit(1)


if __name__ == "__main__":
    main()
