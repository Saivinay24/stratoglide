"""Lint outward files: (1) zero em dashes (U+2014); (2) every numeric token in the report, README, resume
contract and site/dashboard text is traceable to a results/numbers.json value at the token's printed precision
(also as a percentage x100 or in km /1000). Whitelisted: integers 0-20 (section, check, phase, MR numbers,
altitudes in km), years 1950-2030, and version-like strings. Writes results/lint_report.json."""
from __future__ import annotations

import html
import re

from ..common import CONFIG, OUTPUTS, RESULTS, ROOT, read_json, write_json

FILES = [OUTPUTS / "report" / "StratoGlide_Report.html", ROOT / "README.md", OUTPUTS / "RESUME_CONTRACT.md",
         ROOT / "site" / "index.html", ROOT / "outputs" / "BOM.md"] + sorted((OUTPUTS / "test_cards").glob("*.md"))
EM = "—"
TOK = re.compile(r"(?<![\w.\-/])-?\d[\d,]*(?:\.\d+)?(?![\w.]*\w)")


def visible(txt, is_html):
    if is_html:
        txt = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", txt, flags=re.S)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = html.unescape(txt)
    txt = re.sub(r"`[^`]*`", " ", txt)          # code spans: keys, hashes, commands
    txt = re.sub(r"\(\S+\.png\)", " ", txt)       # markdown image paths
    txt = re.sub(r"\b\d+\.\d+\.\d+\b", " ", txt)  # versions
    txt = re.sub(r"(XFOIL|JSBSim|AVL) \d+\.\d+", r"\1", txt)  # tool version names
    return txt


def _cfg_numbers(o, acc):
    if isinstance(o, dict):
        for v in o.values():
            _cfg_numbers(v, acc)
    elif isinstance(o, list):
        for v in o:
            _cfg_numbers(v, acc)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        acc.append(float(o))


def values():
    import yaml
    out = []
    acc = []
    for f in sorted(CONFIG.glob("*.yaml")):  # frozen config inputs are whitelisted (plan: "config inputs whitelisted")
        _cfg_numbers(yaml.safe_load(f.read_text()), acc)
    out += acc
    for v in read_json(RESULTS / "numbers.json")["numbers"].values():
        x = v["value"]
        xs = x if isinstance(x, list) else [x]
        for y in xs:
            if isinstance(y, (int, float)) and not isinstance(y, bool):
                out += [float(y), 100 * float(y), float(y) / 1000]
    return out


def traceable(tok, vals):
    t = tok.replace(",", "")
    x = float(t)
    if x.is_integer() and 0 <= abs(x) <= 20:
        return True
    if x.is_integer() and 1950 <= x <= 2030:
        return True
    nd = len(t.split(".")[1]) if "." in t else 0
    return any(round(v, nd) == x or round(abs(v), nd) == abs(x) for v in vals)


def main():
    vals = values()
    bad, n_tok, em = [], 0, []
    for f in FILES:
        if not f.exists():
            bad.append({"file": str(f.relative_to(ROOT)), "token": "MISSING FILE"})
            continue
        raw = f.read_text()
        if EM in raw:
            em.append(str(f.relative_to(ROOT)))
        txt = visible(raw, f.suffix == ".html")
        for m in TOK.finditer(txt):
            n_tok += 1
            if not traceable(m.group(0), vals):
                ctx = txt[max(0, m.start() - 40): m.end() + 20].replace("\n", " ")
                bad.append({"file": str(f.relative_to(ROOT)), "token": m.group(0), "context": ctx})
    out = {"n_tokens": n_tok, "untraceable": len(bad), "bad": bad[:100], "em_dash_files": em}
    write_json(RESULTS / "lint_report.json", out)
    print("tokens", n_tok, "untraceable", len(bad), "em dash files", em)
    for b in bad[:25]:
        print(" ", b)


if __name__ == "__main__":
    main()
