#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fit check v0.7: the real main board and key board (KiCad STEP exports) inside the housing.

usage:  python3 fit_pcb.py <main_pcb_step> [out_dir] [--kb-step FILE] [--kicad-pcb FILE] [--kb-kicad-pcb FILE]
                            [--no-path]

  <main_pcb_step>  KiCad STEP export of the main board.  Frame: the PCB frame of the 94.4 mm v0.7 body (KiCad
                   x = 100 + X, y = 100 - Y), Z = 0 on the board's bottom face; moved here by H.PCB_DX along X
                   (the frame of the first 94.4 mm layout; the head is longer now) and lifted by P.Z_pcb_bot.
  out_dir          report folder (default: current folder): fit_pcb_v07_report.txt / .json
  --kb-step        KiCad STEP export of the key board (KB).  Frame: PCB frame X, Y; Z = 0 on the KB bottom face
                   (the face with the switches); moved by H.PCB_DX along X and lifted by P.kb_z0 (a file that is
                   already at the housing height is recognised by the height of its board solid).  Without it the
                   KB stand-in of flashka_housing.py is used.
  --kicad-pcb      .kicad_pcb of the main board (stand-ins for parts without a 3D model, J6 pad positions);
                   default: the single *.kicad_pcb next to the STEP, if any
  --kb-kicad-pcb   .kicad_pcb of the key board (pogo pin positions); default: none

What is checked (tray, lid, RF window insert, antenna spacer, keys at rest, TIR optic, 14500 cell with its nickel
strips and solder joints, laser and LED-board stand-ins):
  1  collisions (intersection volume) of both boards with the housing parts, the main board centred and pushed
     to the -Y and +Y walls (P.pcb_side_gap - 0.01); the pogo plungers pressing into the main board are the
     intended compression and are reported separately
  2  minimum clearances: components -> every housing part; main board -> key-board parts
  3  pogo pins: working height measured from the two STEP files, plunger tip over its J6 pad
  4  free travel of the main-board assembly in +-X, +-Y, +Z before it touches
  5  the insertion path of the main board (tilted about the X axis, +Y edge low, S2 knob first) over the
     installed key board with the pogo pins at their free height
  6  wire paths: the two LED wires (hole exits -> J3 pads) and the two cell wires (joints in the lower -Y corner
     channel of the bay -> antenna-spacer rebate -> J2 pads) as solids against both boards, the housing and the cell
     (flashka_housing.wire_corridors)
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
import flashka_housing as H  # noqa: E402

KICAD_ORIGIN = (100.0 - H.PCB_DX, 100.0)       # KiCad (PCB frame) -> housing frame: X = x - 100 + PCB_DX
VOL_TOL = 1e-3
VOL_TOL_PATH = 2e-3
SLIVER = 0.01


# --------------------------------------------------------------------------
# STEP -> named solids
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


def load_step(path):
    """-> list of dict(name, model, solid) in the STEP frame; the board (largest thin solid) is named 'PCB'"""
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    rd.SetColorMode(True)
    if rd.ReadFile(path) != IFSelect_RetDone:
        raise RuntimeError("cannot read %s" % path)
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
    if items:
        board = max(items, key=lambda it: it["solid"].Volume())
        bb = board["solid"].BoundingBox()
        if bb.zlen < 1.2 and bb.xlen > 10:
            board["name"], board["model"] = "PCB", "board"
    seen = {}
    for k, it in enumerate(items):
        nm = it["name"]
        if nm in seen or not nm or nm == "part":
            nm = "%s_%d" % (nm or "part", k)
        seen[nm] = 1
        it["name"] = nm
    return items


load_pcb_step = load_step


def parse_kicad_pcb(path):
    """{refdes: dict(x, y, rot, side, footprint, pads=[(num, x, y)])} in housing X, Y (KiCad 6/7 text format)"""
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
        X, Y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        pads = []
        for pm in re.finditer(r'\(pad "([^"]*)" \w+ \w+ \(at ([\-\d.]+) ([\-\d.]+)(?: [\-\d.]+)?\)', blk):
            px, py = float(pm.group(2)), float(pm.group(3))
            c, s = math.cos(math.radians(-rot)), math.sin(math.radians(-rot))
            kx, ky = X + px * c - py * s, Y + px * s + py * c
            pads.append((pm.group(1), round(kx - KICAD_ORIGIN[0], 4), round(KICAD_ORIGIN[1] - ky, 4)))
        out[ref.group(1)] = {"x": X - KICAD_ORIGIN[0], "y": KICAD_ORIGIN[1] - Y, "rot": rot,
                             "side": "B" if lay and lay.group(1).startswith("B") else "F",
                             "footprint": fp.group(1) if fp else "", "pads": pads}
    return out


def _sexp_block(txt, i):
    """the balanced (...) block that starts at txt[i] == '('"""
    depth, j, q = 0, i, False
    while j < len(txt):
        ch = txt[j]
        if ch == '"' and txt[j - 1] != "\\":
            q = not q
        elif not q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return txt[i:j + 1]
        j += 1
    return txt[i:]


def parse_kicad_pads(path):
    """copper pads of a .kicad_pcb (KiCad 6/7 text format) in the housing frame: list of dict(ref, num, kind, shape,
    x, y, angle (deg, counter-clockwise seen from +Z), w, h, rratio, top, bottom, paste).  Pad positions in the file
    are in the footprint frame, pad angles are absolute; KiCad y points down (housing Y = 100 - y)."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    idx = [m.start() for m in re.finditer(r"\n\s*\(footprint ", txt)] + [len(txt)]
    out = []
    for a, b in zip(idx, idx[1:]):
        blk = txt[a:b]
        at = re.search(r"\(at ([\-\d.]+) ([\-\d.]+)(?: ([\-\d.]+))?\)", blk)
        ref = re.search(r'\(fp_text reference "([^"]*)"', blk) or re.search(r'\(property "Reference" "([^"]*)"', blk)
        if not (at and ref):
            continue
        X, Y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        c, s = math.cos(math.radians(-rot)), math.sin(math.radians(-rot))
        for pm in re.finditer(r'\(pad "', blk):
            pb = _sexp_block(blk, pm.start())
            hd = re.match(r'\(pad "([^"]*)" (\w+) (\w+)', pb)
            pat = re.search(r"\(at ([\-\d.]+) ([\-\d.]+)(?: ([\-\d.]+))?\)", pb)
            sz = re.search(r"\(size ([\-\d.]+) ([\-\d.]+)\)", pb)
            ly = re.search(r"\(layers ([^)]*)\)", pb)
            if not (hd and pat and sz and ly) or hd.group(2) == "np_thru_hole":
                continue
            layers = re.findall(r'"([^"]+)"', ly.group(1))
            top = any(q in ("F.Cu", "*.Cu") for q in layers)
            bot = any(q in ("B.Cu", "*.Cu") for q in layers)
            if not (top or bot):
                continue
            px, py = float(pat.group(1)), float(pat.group(2))
            kx, ky = X + px * c - py * s, Y + px * s + py * c
            rr = re.search(r"\(roundrect_rratio ([\-\d.]+)\)", pb)
            out.append({"ref": ref.group(1), "num": hd.group(1), "kind": hd.group(2), "shape": hd.group(3),
                        "x": kx - KICAD_ORIGIN[0], "y": KICAD_ORIGIN[1] - ky, "angle": float(pat.group(3) or 0),
                        "w": float(sz.group(1)), "h": float(sz.group(2)), "rratio": float(rr.group(1)) if rr else 0.0,
                        "top": top, "bottom": bot, "paste": any(q.endswith(".Paste") for q in layers)})
    return out


def standins(p, dm, have, kicad):
    """stand-ins (housing frame) for main-board parts missing in the STEP -> {name: (note, Workplane)}"""
    zt = p.Z_pcb_top
    out = {}
    if "U4" not in have:
        out["U4"] = ("ESP32-C3-MINI-1 stand-in: module PCB + can, antenna overhang (build_dummies)",
                     dm["module"].union(dm["module_can"]))
    if "J1" not in have:
        out["J1"] = ("USB-C receptacle stand-in 8.94 x 7.35 x 3.21 (build_dummies)", dm["usb"])
    if kicad and "L1" not in have and "L1" in kicad:
        f = kicad["L1"]
        out["L1"] = ("inductor 4.0 x 4.0 x 2.0 stand-in at the KiCad position",
                     H.rbox(f["x"] - 2.0, f["x"] + 2.0, f["y"] - 2.0, f["y"] + 2.0, zt, zt + 2.0))
    return out


def pcb_items(step_path, p, dm, kicad_path=None, verbose=True):
    """main-board assembly in the housing frame: list of dict(name, model, solid, kind), plus stand-in notes"""
    raw = load_step(step_path)
    lift = cq.Vector(H.PCB_DX, 0, p.Z_pcb_bot)
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
        notes.append("%s: %s" % (nm, note))
    if verbose:
        print("main board STEP: %d solids, %d stand-ins" % (len(raw), len(notes)))
    return items, notes


def kb_items(step_path, p, verbose=False):
    """key-board assembly in the housing frame (stand-ins for missing switches / LEDs are not added: the KB STEP is
    expected to be complete).  The pogo pins come as one solid each at their free height: they are split into the
    barrel part (base + barrel, name Pn) and the plunger (name Pn_pl) just above the barrel top."""
    raw = load_step(step_path)
    board = [r for r in raw if r["name"] == "PCB"]
    z0 = board[0]["solid"].BoundingBox().zmin if board else 0.0
    dz = p.kb_z0 - z0 if abs(z0 - p.kb_z0) > 0.05 else 0.0
    items = []
    for r in raw:
        s = r["solid"].translate(cq.Vector(H.PCB_DX, 0, dz))
        nm = "KB_" + r["name"] if r["name"] == "PCB" else r["name"]
        kind = "board" if r["name"] == "PCB" else "part"
        if "pogo" in (r["model"] or "").lower():
            bb = s.BoundingBox()
            zc = bb.zmin + p.pogo_barrel[1] + 0.02
            lo = s.intersect(cq.Solid.makeBox(bb.xlen + 2, bb.ylen + 2, zc - bb.zmin + 1,
                                              cq.Vector(bb.xmin - 1, bb.ymin - 1, bb.zmin - 1)))
            hi = s.intersect(cq.Solid.makeBox(bb.xlen + 2, bb.ylen + 2, bb.zmax - zc + 1,
                                              cq.Vector(bb.xmin - 1, bb.ymin - 1, zc)))
            items.append({"name": nm, "model": r["model"], "solid": lo, "kind": kind, "pogo_base_z": bb.zmin})
            items.append({"name": nm + "_pl", "model": r["model"], "solid": hi, "kind": kind, "pogo_base_z": bb.zmin})
        else:
            items.append({"name": nm, "model": r["model"], "solid": s, "kind": kind})
    if verbose:
        print("key board STEP: %d solids, lifted by %.3f mm" % (len(raw), dz))
    return items


def at_working_height(solid, p):
    """a free-height plunger cut off at the J6 pad level (main-board bottom face): the installed state"""
    bb = solid.BoundingBox()
    if bb.zmax <= p.Z_pcb_bot:
        return solid
    return solid.intersect(cq.Solid.makeBox(bb.xlen + 2, bb.ylen + 2, p.Z_pcb_bot - bb.zmin + 1,
                                            cq.Vector(bb.xmin - 1, bb.ymin - 1, bb.zmin - 1)))


def kb_standin_items(p):
    d = H.build_kb_standin(p, pogo_state="free")
    return [{"name": k, "model": "stand-in", "solid": v.val(), "kind": "board" if k == "kb" else "part"} for k, v in d.items()]


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


def is_plunger(name, solid, p):
    """pogo plunger solids: thin vertical pins reaching above the KB top face by more than the barrel"""
    bb = solid.BoundingBox()
    return (name.endswith("_pl") or (bb.xlen < 1.2 and bb.ylen < 1.2 and bb.zmax > p.kb_z1 + p.pogo_barrel[1] - 0.2
                                     and bb.zmin > p.kb_z1 - 0.05))


# --------------------------------------------------------------------------
def housing_parts(p, dm):
    parts = {
        "tray": H.build_tray(p, texture="none").val(),
        "lid": H.build_lid(p, texture="none").val(),
        "rf_window": H.build_rf_window(p, texture=False).val(),
        "antenna_spacer": H.build_antenna_spacer(p, texture=False).val(),
        "key_main": H.build_key_main(p).val(),
        # side keys with their glued-in stiffener (plate + doubler): the doubler is what meets the switch
        "key_next": H.build_key_side(p, p.X_next, -1).union(H.build_key_stiffener(p, p.X_next)).val(),
        "key_prev": H.build_key_side(p, p.X_prev, +1).union(H.build_key_stiffener(p, p.X_prev)).val(),
    }
    for k in H.CELL_PARTS + ("laser", "optic_holder", "optic_lens", "mcpcb", "led"):
        parts[k] = dm[k].val()
    return parts


def pogo_report(p, main_items, kb, main_kicad):
    """working height from the STEP solids and the plunger positions against the J6 pads"""
    zb = [it for it in main_items if it["name"] == "PCB"]
    kbb = [it for it in kb if it["kind"] == "board"]
    out = {}
    if zb and kbb:
        z_main = zb[0]["solid"].BoundingBox().zmin
        z_kb = kbb[0]["solid"].BoundingBox().zmax
        bases = [it["pogo_base_z"] for it in kb if "pogo_base_z" in it]
        if not bases:                                   # stand-in: base solids kb_pogoN
            bases = [it["solid"].BoundingBox().zmin for it in kb if re.fullmatch(r"kb_pogo\d+", it["name"])]
        out["main_board_bottom_z"] = round(z_main, 3)
        out["kb_top_z"] = round(z_kb, 3)
        out["kb_top_to_main_board_mm"] = round(z_main - z_kb, 3)
        if bases:
            out["pogo_base_z (on its solder)"] = [round(min(bases), 3), round(max(bases), 3)]
            out["working_height_mm (pin base to J6 pad)"] = round(z_main - max(bases), 3)
            out["working_height_in_range"] = bool(p.pogo_min <= z_main - max(bases) <= p.pogo_max_work)
    pins = [it for it in kb if is_plunger(it["name"], it["solid"], p)]
    tips = []
    for it in pins:
        bb = it["solid"].BoundingBox()
        tips.append((it["name"], round((bb.xmin + bb.xmax) / 2, 3), round((bb.ymin + bb.ymax) / 2, 3), round(bb.zmax, 3)))
    out["plunger_tips (name, X, Y, Z top as modelled)"] = tips
    if main_kicad and "J6" in main_kicad:
        pads = main_kicad["J6"]["pads"]
        res = []
        for nm, x, y, zt in tips:
            best = min(pads, key=lambda q: math.hypot(q[1] - x, q[2] - y)) if pads else None
            if best:
                res.append((nm, "J6." + best[0], round(math.hypot(best[1] - x, best[2] - y), 3)))
        out["plunger_to_nearest_J6_pad_mm"] = res
        out["max_offset_mm"] = max((r[2] for r in res), default=None)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcb_step")
    ap.add_argument("out_dir", nargs="?", default=".")
    ap.add_argument("--kb-step", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--kb-kicad-pcb", default=None)
    ap.add_argument("--no-path", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    p = H.P()
    dm = H.build_dummies(p)
    parts = housing_parts(p, dm)
    items, notes = pcb_items(a.pcb_step, p, dm, a.kicad_pcb)
    kpath = a.kicad_pcb
    if kpath is None:
        cands = glob.glob(os.path.join(os.path.dirname(os.path.abspath(a.pcb_step)), "*.kicad_pcb"))
        kpath = cands[0] if len(cands) == 1 else None
    main_kicad = parse_kicad_pcb(kpath) if kpath else None
    if a.kb_step:
        kb = kb_items(a.kb_step, p, verbose=True)
        kb_src = os.path.basename(a.kb_step)
    else:
        kb = kb_standin_items(p)
        kb_src = "stand-in (flashka_housing.build_kb_standin)"
    kb_parts = [it for it in kb]
    bb = bbox(cq.Compound.makeCompound([i["solid"] for i in items]))
    x0, y0, z0, x1, y1, z1 = bb.Get()
    kbb = bbox(cq.Compound.makeCompound([i["solid"] for i in kb]))
    kx0, ky0, kz0, kx1, ky1, kz1 = kbb.Get()
    report = {"pcb_step": os.path.basename(a.pcb_step), "kb_source": kb_src, "stand_ins": notes,
              "main_bbox": [round(v, 3) for v in (x0, x1, y0, y1, z0, z1)],
              "kb_bbox": [round(v, 3) for v in (kx0, kx1, ky0, ky1, kz0, kz1)]}
    lines = ["FIT CHECK v0.7 (body %.1f mm; boards moved by %g along X from their PCB frame) - %s + key board %s"
             % (p.L, H.PCB_DX, os.path.basename(a.pcb_step), kb_src), "",
             "main board assembly bbox: X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (x0, x1, y0, y1, z0, z1),
             "key board assembly bbox:  X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (kx0, kx1, ky0, ky1, kz0, kz1)]
    lines += ["stand-in: " + n for n in notes]
    print("built housing parts and boards in %.1f s" % (time.time() - t0), flush=True)

    # ---- key board against the housing parts (keys at rest) and the screws
    kb_hits = collisions(kb_parts, {k: v for k, v in parts.items()})
    kb_hits_real = [h for h in kb_hits if not (h[0].startswith("kb_screw") and h[1] == "tray")]
    report["kb_vs_housing"] = kb_hits_real
    lines += ["", "[key board vs housing parts, keys at rest] collisions (> %g mm^3): %d" % (VOL_TOL, len(kb_hits_real))]
    for h in kb_hits_real:
        lines.append("   %-10s x %-14s %8.4f mm^3 at X %.2f Y %.2f Z %.2f" % (h[0], h[1], h[2], *h[3]))
    kclr = clearances([i for i in kb_parts if not is_plunger(i["name"], i["solid"], p)],
                      {k: parts[k] for k in ("tray", "key_main", "key_next", "key_prev", "antenna_spacer")},
                      skip_board_for=("tray",))
    report["kb_clearance"] = {k: list(v) for k, v in kclr.items()}
    lines.append("   min clearance key board -> part:")
    for k, (d, who) in kclr.items():
        lines.append("      %-15s %s" % (k, ("%.3f mm  (%s)" % (d, who)) if who else "more than 5 mm"))

    # ---- main board in three poses against the housing parts and the key board
    gap = p.pcb_side_gap
    poses = (("main board centred", 0.0), ("main board at the -Y wall (-%.2f)" % (gap - 0.01), -(gap - 0.01)),
             ("main board at the +Y wall (+%.2f)" % (gap - 0.01), gap - 0.01))
    kb_solid = {("KB:" + it["name"]): it["solid"] for it in kb_parts if not is_plunger(it["name"], it["solid"], p)}
    plungers = {("KB:" + it["name"]): it["solid"] for it in kb_parts if is_plunger(it["name"], it["solid"], p)}
    plungers_work = {k: at_working_height(v, p) for k, v in plungers.items()}     # installed: tips on the J6 pads
    report["poses"] = {}
    for label, dy in poses:
        its = moved(items, dy=dy)
        allp = dict(parts)
        allp.update(kb_solid)
        hits = collisions(its, allp)
        comp = [i for i in its if i["kind"] != "board"]
        pl_hits = collisions(its, plungers_work)
        pl_board = [h for h in pl_hits if h[0] == "PCB"]
        pl_other = [h for h in pl_hits if h[0] != "PCB"]
        clr = clearances(its, parts)
        kclr2 = clearances(comp, kb_solid, skip_board_for=())
        report["poses"][label] = {"collisions": hits, "pogo_into_board (intended compression)": pl_board,
                                  "pogo_vs_components": pl_other,
                                  "clearance": {k: list(v) for k, v in clr.items()},
                                  "components_to_kb_parts": {k: list(v) for k, v in kclr2.items()}}
        lines += ["", "[%s]  collisions (> %g mm^3): %d" % (label, VOL_TOL, len(hits))]
        for h in hits:
            lines.append("   %8s x %-16s %8.4f mm^3 at X %.2f Y %.2f Z %.2f" % (h[0], h[1], h[2], *h[3])
                         + ("   (contact-level sliver)" if h[2] < SLIVER else "   (REAL COLLISION)"))
        lines.append("   pogo plungers pressing into the main board (intended compression): %d; plungers vs components: %d"
                     % (len(pl_board), len(pl_other)))
        for h in pl_other:
            lines.append("      PLUNGER HITS %s: %s %.4f mm^3" % (h[0], h[1], h[2]))
        lines.append("   min clearance (components; board vs all but the tray):")
        for k, (d, who) in clr.items():
            lines.append("      %-15s %s" % (k, ("%.3f mm  (%s)" % (d, who)) if who else "more than 5 mm"))
        tight = sorted([(v[0], k, v[1]) for k, v in kclr2.items() if v[1]], key=lambda q: q[0])[:6]
        lines.append("   smallest main-board component -> key-board part clearances: " +
                     ", ".join("%s %.3f (%s)" % (k, d, w) for d, k, w in tight))
        print("[%s] collisions %d" % (label, len(hits)), flush=True)

    # ---- pogo pins
    pr = pogo_report(p, items, kb_parts, main_kicad)
    report["pogo"] = pr
    lines += ["", "Pogo pins:"]
    for k, v in pr.items():
        lines.append("   %s: %s" % (k, v))

    # ---- free travel of the main board
    lines += ["", "Free travel of the main-board assembly from the centred position (mm, until it touches):"]
    report["free_travel"] = {}
    allp = dict(parts)
    allp.update(kb_solid)
    for nm, d, hi in (("+Y", (0, 1, 0), 1.0), ("-Y", (0, -1, 0), 1.0), ("+X (rear)", (1, 0, 0), 1.5),
                      ("-X (front)", (-1, 0, 0), 1.5), ("+Z (up)", (0, 0, 1), 3.0)):
        t, who = free_travel(items, allp, d, hi)
        report["free_travel"][nm] = {"mm": t, "stopped_by": who}
        lines.append("   %-11s %s   %s" % (nm, ("%.3f" % t) if t is not None else "> %.1f" % hi, who if who else ""))
        print("travel", nm, t, who, flush=True)
    lines.append("   (-Z: the board rests on the ledges at Z = %.2f by design)" % p.Z_pcb_bot)

    # ---- insertion path over the installed key board
    if not a.no_path:
        pivot = (p.Y_pcb + p.s2_knob_out - 0.2, p.Z_pcb_top + p.s2_knob_z)
        against = {"tray": parts["tray"], "key_main": parts["key_main"], "key_next": parts["key_next"],
                   "key_prev": parts["key_prev"], "laser": parts["laser"]}
        against.update(kb_solid)
        lines += ["", "Insertion path: tilt about the X axis through Y %.2f / Z %.2f, +Y edge low, 9 -> 0 deg in 12 steps,"
                  % pivot, "  over the installed key board (pogo plungers at their free height)"]
        report["insertion"] = []
        steps = 12
        # only bottom-side parts of the main board can meet a plunger: the board itself pushes the plungers down
        # (a free-height plunger drawn through the board would otherwise "touch" top-side parts)
        bottom = {i["name"] for i in items if i["kind"] != "board" and i["solid"].BoundingBox().zmax <= p.Z_pcb_bot + 0.02}
        lines.append("  (bottom-side parts of the main board checked against the plungers: %d)" % len(bottom))
        for k in range(steps + 1):
            ang = 9.0 * (1 - k / steps)
            its = moved(items, tilt=(pivot[0], pivot[1], ang))
            hits = collisions(its, against)
            botc = [i for i in its if i["name"] in bottom]
            ph = collisions(botc, plungers)
            report["insertion"].append({"angle": round(ang, 2), "hits": hits, "components_on_plungers": ph})
            lines.append("   %5.2f deg: hits %d%s   components on plungers %d%s" % (
                ang, len(hits), (" " + str(hits[:3])) if hits else "", len(ph), (" " + str(ph[:3])) if ph else ""))
            print("path", round(ang, 2), len(hits), len(ph), flush=True)

    # ---- wire paths against both boards (main board centred)
    wires = H.wire_corridors(p)
    board_items = items + [it for it in kb_parts]
    lines += ["", "Wire paths (24 AWG, OD %.2f; flashka_housing.wire_corridors) against both boards, main board centred:"
              % H.WIRE_OD]
    report["wire_paths"] = {}
    for wn, ws in wires.items():
        hits = collisions([{"name": wn, "solid": ws, "kind": "wire"}], {it["name"]: it["solid"] for it in board_items})
        own = {"BAT-": ("cell_joint_rear", "cell_strip_rear"), "BAT+": ("cell_joint_front", "cell_strip_front")}
        skip = [k for tag, ks in own.items() if tag in wn for k in ks]       # a cell wire starts in its own joint
        real_parts = {k: v for k, v in parts.items() if k not in skip}
        hp = collisions([{"name": wn, "solid": ws, "kind": "wire"}], real_parts)
        clr = min((distance(ws, it["solid"]), it["name"]) for it in board_items
                  if bbox(it["solid"]).Distance(bbox(ws)) < 3.0) if any(
            bbox(it["solid"]).Distance(bbox(ws)) < 3.0 for it in board_items) else (float("inf"), None)
        report["wire_paths"][wn] = {"board_hits": hits, "housing_hits": hp,
                                    "clearance_to_board_items": [round(clr[0], 3), clr[1]]}
        lines.append("   %-30s board hits %d, housing hits %d, nearest board item %s" % (
            wn, len(hits), len(hp), ("%.3f mm (%s)" % clr) if clr[1] else "more than 3 mm"))
        for h in hits + hp:
            lines.append("      %s x %s %.4f mm^3 at X %.2f Y %.2f Z %.2f" % (h[0], h[1], h[2], *h[3]))
    print("wire paths done", flush=True)

    # ---- summary
    lines += ["", "SUMMARY", "-------"]
    real = [(lb, h) for lb, d in report["poses"].items() for h in d["collisions"] if h[2] >= SLIVER]
    sliv = [(lb, h) for lb, d in report["poses"].items() for h in d["collisions"] if h[2] < SLIVER]
    pl = [(lb, h) for lb, d in report["poses"].items() for h in d["pogo_vs_components"]]
    lines.append("main board: collisions >= %g mm^3 in the three poses: %d%s" % (
        SLIVER, len(real), "" if not real else "  " + str([(lb, h[0], h[1], h[2]) for lb, h in real])))
    lines.append("main board: contact-level slivers (< %g mm^3): %d" % (SLIVER, len(sliv)))
    lines.append("pogo plungers touching main-board components (not the board): %d" % len(pl))
    lines.append("key board vs housing parts: %d collisions" % len(kb_hits_real))
    wh = sum(len(v["board_hits"]) + len(v["housing_hits"]) for v in report["wire_paths"].values())
    lines.append("wire paths (LED wires, cell wires) hitting a board part, a housing part or the cell: %d" % wh)
    if "insertion" in report:
        over = [(s["angle"], h) for s in report["insertion"] for h in s["hits"] if h[2] > VOL_TOL_PATH]
        onpl = [(s["angle"], h) for s in report["insertion"] for h in s["components_on_plungers"]]
        lines.append("insertion path: poses with a hit above %g mm^3: %d; components meeting a plunger: %d"
                     % (VOL_TOL_PATH, len(over), len(onpl)))
    with open(os.path.join(a.out_dir, "fit_pcb_v07_report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(a.out_dir, "fit_pcb_v07_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("\n".join(lines))
    print("fit check done in %.1f s -> %s" % (time.time() - t0, a.out_dir))


if __name__ == "__main__":
    main()
