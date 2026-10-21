#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fit check v0.5: the real PCB 3D model (KiCad STEP export) inside the housing.

usage:  python3 fit_pcb.py <pcb_step> [out_dir] [--kicad-pcb FILE] [--no-path]

  <pcb_step>   KiCad STEP export of the main PCB.  Frame: X, Y = housing X, Y
               (KiCad x = 100 + X, y = 100 - Y), Z = 0 on the PCB bottom face;
               the script lifts it by P.Z_pcb_bot.  Components are read with
               their reference designators (STEP product names).
  out_dir      report folder (default: current folder): fit_pcb_report.txt / .json
  --kicad-pcb  .kicad_pcb of the same board.  Only used to place stand-ins for
               parts whose 3D model is missing from the STEP (inductor L1, RGB
               LED3); default: the single *.kicad_pcb next to the STEP, if any.

What is checked (tray, lid, RF window insert, antenna spacer, button cap, cell
stand-ins, laser / window / LED-board stand-ins):
  1  collisions (intersection volume) with the PCB centred and pushed to the
     -Y and +Y side walls (P.pcb_side_gap - 0.01, as aurora_housing.py does)
  2  minimum clearances: components -> every housing part, board -> every part
     except the tray (the board rests on the ledges by design: contact)
  3  free travel of the whole PCB assembly in +-X, +-Y, +Z before it touches
  4  the insertion path of aurora_housing.insertion_check (tilted about the X
     axis, +Y edge low, S2 knob into its wall slot first) with the real parts

The PCB STEP exported by KiCad lacks the models of U4 (ESP32-C3-MINI-1), J1
(USB-C), S1 (side switch), L1 and LED3: stand-ins from build_dummies() are used
for the ones whose designator is missing from the STEP.
"""
import argparse
import glob
import json
import math
import os
import re
import sys
import time

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.XCAFDoc import XCAFDoc_DocumentTool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aurora_housing as H  # noqa: E402

KICAD_ORIGIN = (100.0, 100.0)    # KiCad x = 100 + X, y = 100 - Y
VOL_TOL = 1e-3                   # mm^3, the same threshold as aurora_housing.interference()
VOL_TOL_PATH = 2e-3              # mm^3, the threshold of aurora_housing.insertion_check()
SLIVER = 0.01                    # mm^3: below this an overlap is contact within model tolerance (0.003 mm^3
                                 # = 0.017 mm over a 0.2 mm^2 patch), above it a real collision


# --------------------------------------------------------------------------
# PCB STEP -> named solids
# --------------------------------------------------------------------------
def _name(lbl):
    n = TDataStd_Name()
    return n.Get().ToExtString() if lbl.FindAttribute(TDataStd_Name.GetID_s(), n) else None


def _solids(shape):
    ex, out = TopExp_Explorer(shape, TopAbs_SOLID), []
    while ex.More():
        out.append(TopoDS.Solid_s(ex.Current()))
        ex.Next()
    return out


def load_pcb_step(path):
    """-> list of dict(name, model, solid) in the STEP frame (not yet lifted).
    name = reference designator (STEP product name); the board gets the name 'PCB'.
    Falls back to numbered names when the STEP has no assembly structure."""
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    rd.SetColorMode(True)
    if rd.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError(f"cannot read {path}")
    rd.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    st.GetFreeShapes(free)
    items = []

    def walk(lbl, top):
        comps = TDF_LabelSequence()
        st.GetComponents_s(lbl, comps)
        if comps.Length() == 0 and not top:
            ref = TDF_Label()
            model = _name(ref) if st.GetReferredShape_s(lbl, ref) else None
            for s in _solids(st.GetShape_s(lbl)):
                items.append({"name": _name(lbl) or "part", "model": model, "solid": cq.Shape.cast(s)})
            return
        for i in range(1, comps.Length() + 1):
            walk(comps.Value(i), False)
        if comps.Length() == 0 and top:
            for s in _solids(st.GetShape_s(lbl)):
                items.append({"name": "part", "model": None, "solid": cq.Shape.cast(s)})
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), True)
    # unique, readable names; the board = the biggest thin solid
    if items:
        board = max(items, key=lambda it: it["solid"].Volume())
        bb = board["solid"].BoundingBox()
        if bb.zlen < 1.2 and bb.xlen > 10:
            board["name"], board["model"] = "PCB", "board"
    seen = {}
    for k, it in enumerate(items):
        nm = it["name"]
        if nm in seen or not nm or nm == "part":
            nm = f"{nm or 'part'}_{k}"
        seen[nm] = 1
        it["name"] = nm
    return items


def parse_kicad_pcb(path):
    """{refdes: dict(x, y, rot, side, footprint)} in housing X, Y (KiCad 6/7 text format)."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    idx = [m.start() for m in re.finditer(r"\n\s*\(footprint ", txt)] + [len(txt)]
    out = {}
    for a, b in zip(idx, idx[1:]):
        blk = txt[a:b]
        at = re.search(r"\(at ([\-\d.]+) ([\-\d.]+)(?: ([\-\d.]+))?\)", blk)
        ref = re.search(r'\(fp_text reference "([^"]*)"', blk) or re.search(r'\(property "Reference" "([^"]*)"', blk)
        lay = re.search(r'\(layer "([^"]+)"', blk)
        fp = re.search(r'\(footprint "([^"]+)"', blk)
        if not (at and ref):
            continue
        out[ref.group(1)] = {"x": float(at.group(1)) - KICAD_ORIGIN[0],
                             "y": KICAD_ORIGIN[1] - float(at.group(2)),
                             "rot": float(at.group(3) or 0), "side": "B" if lay and lay.group(1).startswith("B") else "F",
                             "footprint": fp.group(1) if fp else ""}
    return out


def standins(p, dm, have, kicad):
    """Stand-ins (housing frame) for parts missing in the STEP.  -> {name: (note, Workplane)}"""
    zt = p.Z_pcb_top
    out = {}
    if "U4" not in have:
        out["U4"] = ("ESP32-C3-MINI-1 stand-in: module PCB + can, antenna overhang (build_dummies)",
                     dm["module"].union(dm["module_can"]))
    if "J1" not in have:
        out["J1"] = ("USB-C receptacle stand-in 8.94 x 7.35 x 3.21 (build_dummies)", dm["usb"])
    if "S1" not in have:
        out["S1"] = ("S1 side switch + actuator stand-in (build_dummies)", dm["s1"].union(dm["s1_act"]))
    if kicad:
        if "L1" not in have and "L1" in kicad:
            f = kicad["L1"]       # 1 uH FNR4020S 4.0 x 4.0 x 2.0, top side
            out["L1"] = ("inductor 4.0 x 4.0 x 2.0 stand-in at the KiCad position",
                         H.rbox(f["x"] - 2.0, f["x"] + 2.0, f["y"] - 2.0, f["y"] + 2.0, zt, zt + 2.0))
        if "LED3" not in have and "LED3" in kicad:
            f = kicad["LED3"]     # RGB 1010, top side
            out["LED3"] = ("RGB LED 1.0 x 1.0 x 0.5 stand-in at the KiCad position",
                           H.rbox(f["x"] - 0.5, f["x"] + 0.5, f["y"] - 0.5, f["y"] + 0.5, zt, zt + 0.5))
    return out


def pcb_items(step_path, p, dm, kicad_path=None, verbose=True):
    """PCB assembly in the housing frame: list of dict(name, solid, kind) with
    kind in board / part / standin, plus the list of stand-in notes."""
    raw = load_pcb_step(step_path)
    lift = cq.Vector(0, 0, p.Z_pcb_bot)
    items = [{"name": r["name"], "model": r["model"], "solid": r["solid"].translate(lift),
              "kind": "board" if r["name"] == "PCB" else "part"} for r in raw]
    if kicad_path is None:
        cands = glob.glob(os.path.join(os.path.dirname(os.path.abspath(step_path)), "*.kicad_pcb"))
        kicad_path = cands[0] if len(cands) == 1 else None
    kicad = parse_kicad_pcb(kicad_path) if kicad_path else None
    have = {it["name"] for it in items}
    notes = []
    for nm, (note, wp) in standins(p, dm, have, kicad).items():
        items.append({"name": nm, "model": "stand-in", "solid": wp.val(), "kind": "standin"})
        notes.append(f"{nm}: {note}")
    if not kicad:
        notes.append("no .kicad_pcb found: stand-ins for L1 and LED3 skipped")
    if verbose:
        print(f"PCB STEP: {len(raw)} solids ({sum(i['kind'] == 'part' for i in items)} parts + board), "
              f"{len([i for i in items if i['kind'] == 'standin'])} stand-ins added")
        for n in notes:
            print("  stand-in", n)
    return items, notes


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def bbox(shape, pad=0.0):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, b)
    if pad:
        b.Enlarge(pad)
    return b


def common(a, b):
    """intersection of two shapes -> (volume, centre) ; (0, None) when empty or the boolean fails"""
    try:
        r = a.intersect(b)
        v = r.Volume() if r is not None else 0.0
        return (v, r.Center()) if v > 0 else (0.0, None)
    except Exception:
        return 0.0, None


def distance(a, b):
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def moved(items, dy=0.0, dx=0.0, dz=0.0, tilt=None):
    """items shifted / rotated; tilt = (pivot_y, pivot_z, angle_deg) about the X axis (+angle = -Y edge up)."""
    out = []
    for it in items:
        s = it["solid"]
        if tilt:
            py, pz, ang = tilt
            s = s.rotate(cq.Vector(0, py, pz), cq.Vector(1, py, pz), -ang)
        if dx or dy or dz:
            s = s.translate(cq.Vector(dx, dy, dz))
        out.append({**it, "solid": s})
    return out


def collisions(items, parts, tol=VOL_TOL):
    """[(item, part, volume, centre)] for every pair that overlaps by more than tol mm^3"""
    pb = {k: bbox(v, 0.001) for k, v in parts.items()}
    hits = []
    for it in items:
        ib = bbox(it["solid"])
        for pn, part in parts.items():
            if ib.IsOut(pb[pn]):
                continue
            v, c = common(it["solid"], part)
            if v > tol:
                hits.append((it["name"], pn, round(v, 4), (round(c.x, 2), round(c.y, 2), round(c.z, 2))))
    return hits


def clearances(items, parts, skip_board_for=("tray",), reach=5.0):
    """{part: (min distance, item)} - component items vs each part, the board vs
    every part except those in skip_board_for (ledge contact by design)."""
    res = {}
    pb = {k: bbox(v) for k, v in parts.items()}
    for pn, part in parts.items():
        best = (float("inf"), None)
        for it in sorted(items, key=lambda i: i["kind"] == "board"):
            if it["kind"] == "board" and pn in skip_board_for:
                continue
            ib = bbox(it["solid"])
            if ib.Distance(pb[pn]) > min(best[0], reach):
                continue
            d = distance(it["solid"], part)
            if d < best[0]:
                best = (d, it["name"])
        res[pn] = (round(best[0], 3) if best[1] else None, best[1])
    return res


def free_travel(items, parts, direction, hi, steps=9):
    """largest shift (mm) of the whole PCB assembly along `direction` (dx, dy, dz unit vector)
    before an intersection volume above VOL_TOL appears; None if > hi"""
    def hit(t):
        its = moved(items, dx=direction[0] * t, dy=direction[1] * t, dz=direction[2] * t)
        return bool(collisions(its, parts))
    base = collisions(items, parts)
    if base:
        return 0.0, [(h[0], h[1]) for h in base[:3]]
    if not hit(hi):
        return None, []
    lo, up = 0.0, hi
    for _ in range(steps):
        m = 0.5 * (lo + up)
        if hit(m):
            up = m
        else:
            lo = m
    its = moved(items, dx=direction[0] * up, dy=direction[1] * up, dz=direction[2] * up)
    return round(lo, 3), [(h[0], h[1]) for h in collisions(its, parts)[:3]]


# --------------------------------------------------------------------------
def housing_parts(p, dm):
    """name -> Shape.  Tray and lid without the knurl (exterior only: >= 1.15 mm
    from every cavity face, see texture_walls in housing_interface.json)."""
    parts = {
        "tray": H.build_tray(p, texture=False).val(),
        "lid": H.build_lid(p, texture=False).val(),
        "rf_window": H.build_rf_window(p).val(),
        "antenna_spacer": H.build_antenna_spacer(p).val(),
        "button_cap": H.build_button_cap(p).val(),
        "spacer_ring": H.build_spacer_ring(p).val(),
    }
    for k in ("cell1", "cell2", "laser", "window", "mcpcb", "led"):
        parts[k] = dm[k].val()
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcb_step")
    ap.add_argument("out_dir", nargs="?", default=".")
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--no-path", action="store_true", help="skip the insertion path")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    p = H.P()
    dm = H.build_dummies(p)
    parts = housing_parts(p, dm)
    items, notes = pcb_items(a.pcb_step, p, dm, a.kicad_pcb)
    bb = bbox(cq.Compound.makeCompound([i["solid"] for i in items]))
    x0, y0, z0, x1, y1, z1 = bb.Get()
    print("PCB assembly bbox in the housing: X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (x0, x1, y0, y1, z0, z1))
    print("built housing parts in %.1f s" % (time.time() - t0))
    report = {"pcb_step": os.path.abspath(a.pcb_step), "stand_ins": notes,
              "bbox": [round(v, 3) for v in (x0, x1, y0, y1, z0, z1)]}
    lines = [f"FIT CHECK v0.5 - {os.path.basename(a.pcb_step)}", "",
             "PCB assembly bbox: X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (x0, x1, y0, y1, z0, z1)]
    lines += ["stand-in: " + n for n in notes]
    gap = p.pcb_side_gap
    poses = (("PCB centred", 0.0), ("PCB at the -Y wall (-%.2f)" % (gap - 0.01), -(gap - 0.01)),
             ("PCB at the +Y wall (+%.2f)" % (gap - 0.01), gap - 0.01))

    # ---- 1/2 collisions and clearances in the three poses
    report["poses"] = {}
    for label, dy in poses:
        its = moved(items, dy=dy)
        hits = collisions(its, parts)
        clr = clearances(its, parts)
        report["poses"][label] = {"collisions": hits, "clearance": {k: list(v) for k, v in clr.items()}}
        lines += ["", f"[{label}]  collisions (> {VOL_TOL} mm^3): {len(hits)}"]
        for h in hits:
            lines.append(f"   {h[0]:>8s} x {h[1]:<14s} {h[2]:8.4f} mm^3 at X %.2f Y %.2f Z %.2f" % h[3]
                         + ("   (contact-level sliver)" if h[2] < SLIVER else "   (REAL COLLISION)"))
        lines.append("   min clearance (components; board vs all but the tray):")
        for k, (d, who) in clr.items():
            lines.append(f"      {k:<15s} {('%.3f mm  (%s)' % (d, who)) if who else 'more than 5 mm'}")
        print(f"[{label}] collisions {len(hits)}", flush=True)
    print("poses done %.1f s" % (time.time() - t0), flush=True)

    # ---- 3 free travel of the assembly
    lines += ["", "Free travel of the PCB assembly from the centred position (mm, until it touches):"]
    report["free_travel"] = {}
    for nm, d, hi in (("+Y", (0, 1, 0), 1.0), ("-Y", (0, -1, 0), 1.0), ("+X (rear)", (1, 0, 0), 1.5),
                      ("-X (front)", (-1, 0, 0), 1.5), ("+Z (up)", (0, 0, 1), 3.0)):
        t, who = free_travel(items, parts, d, hi)
        report["free_travel"][nm] = {"mm": t, "stopped_by": who}
        lines.append(f"   {nm:<11s} {('%.3f' % t) if t is not None else '> %.1f' % hi}   {who if who else ''}")
        print("travel", nm, t, who, flush=True)
    lines.append("   (-Z: the board rests on the ledges at Z = %.2f by design)" % p.Z_pcb_bot)

    # ---- 4 insertion path
    if not a.no_path:
        pivot = (p.Y_pcb + p.s2_knob_out - 0.2, p.Z_pcb_top + p.s2_knob_z)
        against = {"tray": parts["tray"], "button_cap": parts["button_cap"], "laser": parts["laser"]}
        info_only = {"antenna_spacer": parts["antenna_spacer"], "cell1": parts["cell1"], "cell2": parts["cell2"]}
        lines += ["", "Insertion path: tilt about the X axis through Y %.2f / Z %.2f (S2 knob height), +Y edge low,"
                  % pivot, "  9 deg -> 0 deg in 12 steps; against tray, button cap, laser stand-in (spacer and cells: information)"]
        report["insertion"] = []
        worst_clear = (9.9, None)
        steps = 12
        for k in range(steps + 1):
            ang = 9.0 * (1 - k / steps)
            its = moved(items, tilt=(pivot[0], pivot[1], ang))
            hits = collisions(its, against)
            extra = collisions(its, info_only)
            s2 = [i for i in its if i["name"] == "S2"]
            d_s2 = round(distance(s2[0]["solid"], parts["tray"]), 3) if s2 else None
            comp = [i for i in its if i["kind"] != "board"]
            clr = clearances(comp, {"tray": parts["tray"]})["tray"]
            report["insertion"].append({"angle": round(ang, 2), "hits": hits, "info_hits": extra,
                                        "S2_to_tray": d_s2, "components_to_tray": list(clr)})
            lines.append(f"   {ang:5.2f} deg: hits {len(hits)}{' ' + str(hits[:3]) if hits else ''}"
                         f"   S2 to tray {d_s2}   components to tray {clr[0]} ({clr[1]})"
                         f"{'   [with spacer/cells: ' + str(extra[:3]) + ']' if extra else ''}")
            print("path", round(ang, 2), len(hits), d_s2, clr, flush=True)
            if clr[0] is not None and clr[0] < worst_clear[0]:
                worst_clear = (clr[0], (round(ang, 2), clr[1]))
        lines.append(f"   smallest component clearance to the tray along the path: {worst_clear[0]} mm at {worst_clear[1]}")
        report["insertion_min_component_to_tray"] = worst_clear

    # ---- summary
    lines += ["", "SUMMARY", "-------"]
    real = [(lb, h) for lb, d in report["poses"].items() for h in d["collisions"] if h[2] >= SLIVER]
    sliv = [(lb, h) for lb, d in report["poses"].items() for h in d["collisions"] if h[2] < SLIVER]
    lines.append(f"collisions >= {SLIVER} mm^3 in the three poses: {len(real)}"
                 + ("" if not real else "  " + str([(lb, h[0], h[1], h[2]) for lb, h in real])))
    lines.append(f"contact-level slivers (< {SLIVER} mm^3, above the {VOL_TOL} mm^3 threshold): {len(sliv)}"
                 + "".join(f"\n   {lb}: {h[0]} x {h[1]} {h[2]} mm^3 at X %.2f Y %.2f Z %.2f" % h[3] for lb, h in sliv))
    lines.append("minimum clearance per part over the three poses (mm, nearest item):")
    mins = {}
    for lb, d in report["poses"].items():
        for k, (dist, who) in d["clearance"].items():
            if who is not None and (k not in mins or dist < mins[k][0]):
                mins[k] = (dist, who, lb)
    report["min_clearance"] = {k: list(v) for k, v in mins.items()}
    for k in parts:
        if k in mins:
            lines.append(f"   {k:<15s} {mins[k][0]:7.3f}   {mins[k][1]:<5s} in pose '{mins[k][2]}'")
        else:
            lines.append(f"   {k:<15s} more than 5 mm")
    if "insertion" in report:
        over = [(s["angle"], h) for s in report["insertion"] for h in s["hits"] if h[2] > VOL_TOL_PATH]
        report["insertion_hits_over_generator_threshold"] = over
        lines.append(f"insertion path: poses with a hit above the generator's {VOL_TOL_PATH} mm^3 threshold: {len(over)}; "
                     f"smallest S2-to-tray distance {min(s['S2_to_tray'] for s in report['insertion'] if s['S2_to_tray'] is not None)} mm")
    lines += ["", "housing_interface.json (simplified stand-in PCB) for comparison: see its interference_* keys."]
    with open(os.path.join(a.out_dir, "fit_pcb_report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(a.out_dir, "fit_pcb_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("\n".join(lines))
    print("fit check done in %.1f s -> %s" % (time.time() - t0, a.out_dir))


if __name__ == "__main__":
    main()
