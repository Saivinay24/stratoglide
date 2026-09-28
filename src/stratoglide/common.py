"""Shared paths, config loading, run isolation and provenance-carrying number records.

Every phase writes runs/<run_id>/<phase>/numbers.json where each number is
{value, unit, script, git_sha, run_id, inputs_sha}. collect_numbers merges them into
results/numbers.json, the single source of truth for every outward number.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RUNS = ROOT / "runs"
RESULTS = ROOT / "results"
OUTPUTS = ROOT / "outputs"
TOOLS_BIN = ROOT / "tools" / "bin"
CACHE = ROOT / "cache"


def load_cfg(name: str) -> dict:
    with open(CONFIG / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=_jsonable).encode()).hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "nogit"


def run_id() -> str:
    """Current run id: env SG_RUN_ID, else runs/CURRENT, else a new <UTC>-<sha> id."""
    rid = os.environ.get("SG_RUN_ID")
    cur = RUNS / "CURRENT"
    if not rid and cur.exists():
        rid = cur.read_text().strip()
    if not rid:
        rid = new_run_id()
    return rid


def new_run_id() -> str:
    rid = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + git_sha()
    RUNS.mkdir(exist_ok=True)
    (RUNS / "CURRENT").write_text(rid + "\n")
    (RUNS / rid).mkdir(parents=True, exist_ok=True)
    return rid


def phase_dir(phase: str) -> Path:
    d = RUNS / run_id() / phase
    d.mkdir(parents=True, exist_ok=True)
    return d


def _jsonable(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not jsonable: {type(o)}")


def write_json(path: Path | str, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_jsonable, sort_keys=False)


def read_json(path: Path | str):
    with open(path) as f:
        return json.load(f)


def latest_phase_file(phase: str, name: str) -> Path:
    """Path of a phase artifact in the current run (falls back to the newest run that has it)."""
    p = RUNS / run_id() / phase / name
    if p.exists():
        return p
    cands = sorted(RUNS.glob(f"*/{phase}/{name}"))
    if not cands:
        raise FileNotFoundError(f"{phase}/{name} not found in any run")
    return cands[-1]


class Numbers:
    """Collect provenance-carrying numbers for one phase."""

    def __init__(self, phase: str, script: str, inputs: dict | None = None):
        self.phase = phase
        self.script = script
        self.inputs_sha = sha256_obj(inputs or {})[:16]
        self.items: dict[str, dict] = {}

    def add(self, key: str, value, unit: str = "-", note: str | None = None):
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        if isinstance(value, float):
            value = float(f"{value:.6g}")
        rec = {"value": value, "unit": unit, "script": self.script, "git_sha": git_sha(),
               "run_id": run_id(), "inputs_sha": self.inputs_sha}
        if note:
            rec["note"] = note
        self.items[f"{self.phase}.{key}"] = rec
        return value

    def save(self):
        """Merge into the phase file: keys previously written by THIS script are replaced, other scripts' keys kept
        (several scripts share one phase; a plain overwrite silently dropped earlier scripts' numbers)."""
        f = phase_dir(self.phase) / "numbers.json"
        cur = read_json(f) if f.exists() else {}
        cur = {k: v for k, v in cur.items() if v.get("script") != self.script}
        cur.update(self.items)
        write_json(f, cur)
        return self.items
