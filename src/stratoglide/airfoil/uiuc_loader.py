"""Load UIUC LSAT polars (raw ASCII, Vols 1 and 3) and UIUC airfoil coordinates.

PRE-REGISTERED validation series (written before any XFOIL run, see HONEST_LOG P2 entry):
  primary   : Vol 3 E387 (C) clean "used for validating UIUC data against LTPT data"
              Vol 3 SD7037 (D) clean (first SD7037 (D) block; the second is "with upper surface covering")
  secondary : Vol 1 E387 (A) clean, Vol 1 SD7037 (B) clean  -> reported as tunnel-to-tunnel scatter only
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ..common import CACHE, DATA, Numbers, load_cfg, phase_dir, sha256_file, write_json

LSAT = DATA / "validation" / "uiuc_lsat"
COORDS = DATA / "validation" / "coords"

PRIMARY = {"E387": ("03", "E387 (C)", "clean (used for validating"),
           "SD7037": ("03", "SD7037 (D)", "clean")}
SECONDARY = {"E387": ("01", "E387 (A)", "clean"), "SD7037": ("01", "SD7037 (B)", "clean")}


def _blocks(fn: Path):
    s = fn.read_text(errors="replace").replace("\r", "")
    for b in re.split(r"\n(?=Airfoil:)", s):
        m = re.match(r"Airfoil:\s*(.*)", b)
        if m:
            com = re.search(r"Comment:\s*(.*)", b)
            yield m.group(1).strip(), (com.group(1).strip() if com else ""), b


def _parse_runs(block: str, ncol_min: int):
    runs = []
    parts = re.split(r"Average Reynolds #:\s*\n", block)[1:]
    for p in parts:
        lines = p.split("\n")
        re_avg = float(lines[0].split()[0])
        rows = []
        for ln in lines[1:]:
            t = ln.split()
            if len(t) >= ncol_min:
                try:
                    vals = [float(x) for x in t[:7]]
                    rows.append(vals + [np.nan] * (7 - len(vals)))
                except ValueError:
                    if rows:
                        break
            elif rows and (ln.startswith("Tabulated") or ln.strip() == ""):
                break
        runs.append({"re": re_avg, "data": np.array(rows)})
    return runs


def load_series(foil: str, which: str = "primary"):
    """Return {re_nominal: {"re": avg, "drag": (alpha, cl, cd), "lift": (alpha, cl, cm)}}."""
    vol, name, com_prefix = (PRIMARY if which == "primary" else SECONDARY)[foil]
    out = {}
    for kind, fn, ncol in (("drag", LSAT / f"DRAG{vol}.TXT", 3), ("lift", LSAT / f"LIFT{vol}.TXT", 3)):
        for nm, com, b in _blocks(fn):
            if nm == name and com.startswith(com_prefix):
                for r in _parse_runs(b, ncol):
                    nom = int(round(r["re"] / 1e4) * 1e4) if r["re"] < 1e5 else int(round(r["re"] / 5e4) * 5e4)
                    if r["data"].size == 0:
                        continue
                    out.setdefault(nom, {"re": r["re"]})[kind] = r["data"]
                break  # first matching block only
    return out


def ascending_branch(a: np.ndarray):
    """LSAT lift files sweep up then down (hysteresis). Keep the first monotonic-increasing alpha run."""
    alpha = a[:, 0]
    k = len(alpha)
    for i in range(1, len(alpha)):
        if alpha[i] < alpha[i - 1] - 0.3:
            k = i
            break
    return a[:k]


def read_coords(path: Path):
    """Read Selig or Lednicer format; return Nx2 array in Selig order (TE upper -> LE -> TE lower)."""
    lines = [ln.strip() for ln in path.read_text(errors="replace").replace("\r", "").split("\n")]
    nums = []
    for ln in lines[1:]:
        t = ln.split()
        if len(t) >= 2:
            try:
                nums.append((float(t[0]), float(t[1])))
            except ValueError:
                continue
    arr = np.array(nums)
    if arr[0, 0] > 1.5 and arr[0, 1] > 1.5:  # Lednicer: first line = counts
        nu, nl = int(arr[0, 0]), int(arr[0, 1])
        up = arr[1:1 + nu]
        lo = arr[1 + nu:1 + nu + nl]
        arr = np.vstack([up[::-1], lo[1:]])
    # normalise chord to 1, LE at x=0
    xmin, xmax = arr[:, 0].min(), arr[:, 0].max()
    arr[:, 0] = (arr[:, 0] - xmin) / (xmax - xmin)
    arr[:, 1] = arr[:, 1] / (xmax - xmin)
    return arr


def thickness(arr: np.ndarray) -> float:
    ile = int(np.argmin(arr[:, 0]))
    up, lo = arr[:ile + 1][::-1], arr[ile:]
    x = np.linspace(0.01, 0.99, 197)
    yu = np.interp(x, up[:, 0], up[:, 1])
    yl = np.interp(x, lo[:, 0], lo[:, 1])
    return float(np.max(yu - yl))


def normalized_dat(foil: str) -> Path:
    """Write a Selig-format .dat for XFOIL/NeuralFoil into cache/coords; NACA0008 generated analytically."""
    ds = load_cfg("design_space")
    d = CACHE / "coords"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{foil}.dat"
    if foil.upper().startswith("NACA") and not (COORDS / f"{foil.lower()}.dat").exists():
        raise FileNotFoundError(foil)
    key = ds["airfoils"]["coord_files"].get(foil, foil.lower())
    arr = read_coords(COORDS / f"{key}.dat")
    with open(out, "w") as f:
        f.write(f"{foil}\n")
        for x, y in arr:
            f.write(f" {x:.6f} {y:.6f}\n")
    return out


def main():
    d = phase_dir("p2")
    summary = {}
    for foil in PRIMARY:
        for which in ("primary", "secondary"):
            s = load_series(foil, which)
            summary[f"{foil}_{which}"] = {str(k): {"re_avg": v["re"], "n_drag": len(v.get("drag", [])),
                                                   "n_lift": len(v.get("lift", []))} for k, v in s.items()}
    ds = load_cfg("design_space")
    foils = ds["airfoils"]["candidates"] + ["AG24"] + ds["airfoils"]["tail_candidates"]
    tc = {}
    for foil in foils:
        p = normalized_dat(foil)
        tc[foil] = {"tc": thickness(np.loadtxt(p, skiprows=1)),
                    "raw_sha256": sha256_file(COORDS / f"{ds['airfoils']['coord_files'].get(foil, foil.lower())}.dat")}
    write_json(d / "uiuc_series.json", {"series": summary, "airfoils": tc})
    n = Numbers("p2", "src/stratoglide/airfoil/uiuc_loader.py")
    for foil, v in tc.items():
        n.add(f"tc_{foil}", v["tc"], "-")
    prev = {}
    p = d / "numbers.json"
    if p.exists():
        from ..common import read_json
        prev = read_json(p)
    prev.update(n.items)
    write_json(p, prev)
    for k, v in summary.items():
        print(k, {kk: (round(vv["re_avg"]), vv["n_drag"], vv["n_lift"]) for kk, vv in v.items()})
    print({k: round(v["tc"], 4) for k, v in tc.items()})


if __name__ == "__main__":
    main()
