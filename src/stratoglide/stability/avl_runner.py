"""Batch AVL runs: trimmed level flight at a given density/CL, ST derivatives file, eigenmodes file.

Each case runs in a fresh temp directory (AVL prompts before overwriting files). The runner parses the
written files, not screen output. Eigenvalues come from AVL's MODE / N / W; mode identification is done
from eigenvalue magnitude and eigenvector content is not needed for the bars (see modes.py).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..common import TOOLS_BIN

AVL = TOOLS_BIN / "avl"


def run_case(avl_file: Path, mass_file: Path, mass: float, rho: float, cl: float, g0=9.80665, cg=None,
             extra_files=(), timeout=60):
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        shutil.copy(avl_file, wd / "a.avl")
        shutil.copy(mass_file, wd / "a.mass")
        for f in extra_files:
            shutil.copy(f, wd / Path(f).name)
        cmds = ["PLOP", "G", "", "LOAD a.avl", "MASS a.mass", "MSET", "0", "OPER", "C1", f"M {mass:.6f}", f"D {rho:.6f}",
                f"G {g0}", f"C {cl:.6f}", ""]
        if cg is not None:
            cmds[-1:-1] = [f"X {cg[0]:.6f}", f"Z {cg[1]:.6f}"]
        cmds += ["D2 PM 0", "X", "ST st.txt", "FT ft.txt", "", "MODE", "N", "W", "eig.txt", "", "QUIT"]
        p = subprocess.run([str(AVL)], input="\n".join(cmds) + "\n", text=True, capture_output=True,
                           timeout=timeout, cwd=wd)
        st = (wd / "st.txt").read_text() if (wd / "st.txt").exists() else ""
        ft = (wd / "ft.txt").read_text() if (wd / "ft.txt").exists() else ""
        eig = (wd / "eig.txt").read_text() if (wd / "eig.txt").exists() else ""
        return {"st": parse_st(st), "ft": parse_kv(ft), "eig": parse_eig(eig), "stdout_tail": p.stdout[-3000:],
                "raw_st": st, "raw_eig": eig}


def parse_kv(txt: str):
    out = {}
    for k, v in re.findall(r"([A-Za-z][A-Za-z0-9_'/]*)\s*=\s*(-?\d+\.\d*(?:[Ee][-+]?\d+)?)", txt):
        out.setdefault(k, float(v))
    return out


def parse_st(txt: str):
    d = parse_kv(txt)
    m = re.search(r"Xnp\s*=\s*(-?\d+\.\d+)", txt)
    if m:
        d["Xnp"] = float(m.group(1))
    m = re.search(r"Clb Cnr / Clr Cnb\s*=\s*(-?\d+\.\d+)", txt)
    if m:
        d["spiral_ratio"] = float(m.group(1))
    # control derivatives are named CLd1, Cmd2, ... in the ST file
    return d


def parse_eig(txt: str):
    ev = []
    for ln in txt.splitlines():
        t = ln.split()
        if len(t) >= 3 and not ln.lstrip().startswith("#"):
            try:
                ev.append((float(t[1]), float(t[2])))
            except ValueError:
                pass
    return ev
