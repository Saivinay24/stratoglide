"""CadQuery geometry export from geometry_final.json (P4): wing halves lofted from the selected airfoil at root
and tip (twist, dihedral, sweep from the LE line), horizontal tail halves and fin lofted from the tail section,
pod (revolved ogive-cylinder), boom (tube). STEP assembly + one STL per part.
Mesh checks (check 20): each STL watertight; wing span and planform area from the mesh vs geometry.json.
"""
from __future__ import annotations

import numpy as np

from ..airfoil.uiuc_loader import normalized_dat
from ..common import Numbers, OUTPUTS, latest_phase_file, phase_dir, read_json, write_json

OUT = OUTPUTS / "geometry"


def foil_pts(name, n=60):
    d = np.loadtxt(normalized_dat(name), skiprows=1)
    # resample by arc length to n points per surface keeping the LE, drop duplicate TE point
    le = int(np.argmin(d[:, 0]))
    up, lo = d[: le + 1], d[le:]

    def rs(seg):
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(seg, axis=0).T))]
        t = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
        return np.c_[np.interp(t * s[-1], s, seg[:, 0]), np.interp(t * s[-1], s, seg[:, 1])]
    pts = np.r_[rs(up), rs(lo)[1:]]
    pts[-1] = pts[0] = [1.0, 0.5 * (pts[0, 1] + pts[-1, 1])]  # close the trailing edge
    return pts[:-1]


def section_wire(cq, pts, chord, x_le, y, z, twist_deg, plane="xz"):
    tw = np.radians(twist_deg)
    xs = (pts[:, 0] - 0.25) * chord
    zs = pts[:, 1] * chord
    xr = xs * np.cos(tw) + zs * np.sin(tw) + x_le + 0.25 * chord
    zr = -xs * np.sin(tw) + zs * np.cos(tw) + z
    if plane == "xz":
        v = [cq.Vector(float(a), float(y), float(b)) for a, b in zip(xr, zr)]
    else:  # fin: section in the x-y plane at height z = y argument
        v = [cq.Vector(float(a), float(b - z), float(y)) for a, b in zip(xr, zr)]
    return cq.Wire.makePolygon(v, close=True)


def loft(cq, w0, w1):
    return cq.Solid.makeLoft([w0, w1], True)


def build(g):
    import cadquery as cq
    wf, tf = foil_pts(g["airfoil"]), foil_pts(g["htail"]["airfoil"])
    s0, s1 = g["wing_sections"]
    parts = {}
    for side, sg in (("wing_right", 1), ("wing_left", -1)):
        w0 = section_wire(cq, wf, s0["chord"], s0["x_le"], 0.0, s0["z"], 0.0)
        w1 = section_wire(cq, wf, s1["chord"], s1["x_le"], sg * s1["y"], s1["z"], s1["twist_deg"])
        parts[side] = loft(cq, w0, w1)
    h = g["htail"]
    for side, sg in (("htail_right", 1), ("htail_left", -1)):
        parts[side] = loft(cq, section_wire(cq, tf, h["chord"], h["x_le"], 0.0, h["z"], 0.0),
                           section_wire(cq, tf, h["chord"], h["x_le"], sg * h["b"] / 2, h["z"], 0.0))
    v = g["vtail"]
    parts["fin"] = loft(cq, section_wire(cq, tf, v["chord"], v["x_le"], v["z0"], 0.0, 0.0, plane="xy"),
                        section_wire(cq, tf, v["chord"], v["x_le"], v["z0"] + v["h"], 0.0, 0.0, plane="xy"))
    p = g["pod"]
    r = p["diameter"] / 2
    L = p["length"]
    # capped loft through circular stations (a revolve with an edge on the axis gives a degenerate pole in STL)
    st = [(0.0, 0.08), (0.03, 0.55), (0.08, 0.80), (0.15, 0.95), (0.25, 1.0), (0.80, 1.0), (0.92, 0.85), (1.0, 0.5)]
    wires = [cq.Wire.makeCircle(max(f * r, 0.004), cq.Vector(p["x_nose"] + x * L, 0, p["z"]), cq.Vector(1, 0, 0))
             for x, f in st]
    parts["pod"] = cq.Solid.makeLoft(wires, True)
    bm = g["boom"]
    tube = (cq.Workplane("YZ").circle(bm["d"] / 2).circle(bm["d"] / 2 - 0.001).extrude(bm["length"])).val()
    parts["boom"] = tube.translate(cq.Vector(bm["x0"], 0, bm["z"]))
    return parts


def mesh_checks(g, stl):
    import trimesh
    res = {}
    for name, f in stl.items():
        m = trimesh.load(f, force="mesh")
        res[name] = {"watertight": bool(m.is_watertight), "faces": int(len(m.faces))}
    wr = trimesh.load(stl["wing_right"], force="mesh")
    wl = trimesh.load(stl["wing_left"], force="mesh")
    span = float(max(wr.bounds[1][1], wl.bounds[1][1]) - min(wr.bounds[0][1], wl.bounds[0][1]))
    # projected planform area: half of sum |n_z| A over both surfaces, corrected for dihedral (constant per half)
    area = 0.0
    for m in (wr, wl):
        area += 0.5 * float(np.sum(np.abs(m.face_normals[:, 2]) * m.area_faces))
    area /= np.cos(np.radians(g["dihedral_deg"]))
    return res, {"span_mesh_m": span, "span_geom_m": g["b"], "span_rel": abs(span / g["b"] - 1),
                 "area_mesh_m2": area, "area_geom_m2": g["S"], "area_rel": abs(area / g["S"] - 1)}


def main():
    import cadquery as cq
    g = read_json(latest_phase_file("p4", "geometry_final.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    parts = build(g)
    asm = cq.Assembly(name="stratoglide")
    stl = {}
    for name, solid in parts.items():
        asm.add(solid, name=name)
        f = OUT / f"{name}.stl"
        cq.exporters.export(cq.Workplane().add(solid), str(f), tolerance=0.0005, angularTolerance=0.1)
        stl[name] = f
    step = OUT / "stratoglide.step"
    asm.save(str(step))
    re = cq.importers.importStep(str(step))
    n_solids = len(re.solids().vals())
    parts_ck, mesh = mesh_checks(g, stl)
    out = {"step": str(step.relative_to(OUTPUTS.parent)), "step_reimport_solids": n_solids, "parts": parts_ck, **mesh,
           "stl": {k: str(v.relative_to(OUTPUTS.parent)) for k, v in stl.items()}}
    write_json(phase_dir("p8") / "cad.json", out)
    n = Numbers("p8", "src/stratoglide/build/cad.py")
    n.add("mesh_span_m", mesh["span_mesh_m"], "m"); n.add("mesh_area_m2", mesh["area_mesh_m2"], "m^2")
    n.add("mesh_span_rel", mesh["span_rel"]); n.add("mesh_area_rel", mesh["area_rel"])
    n.add("step_reimport_solids", n_solids)
    n.save()
    print({k: v["watertight"] for k, v in parts_ck.items()}, mesh, "STEP solids", n_solids)


if __name__ == "__main__":
    main()
