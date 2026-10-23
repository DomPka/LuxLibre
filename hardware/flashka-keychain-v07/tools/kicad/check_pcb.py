#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks for the generated FlashKa Keychain v0.7 boards (run with KiCad 7's pcbnew).

usage:  check_pcb.py kicad/FlashKa_main/FlashKa_main.kicad_pcb cad/housing_interface.json
        check_pcb.py kicad/FlashKa_keys/FlashKa_keys.kicad_pcb --keys

Main PCB:
1. the file loads in pcbnew
2. pad positions/layers of flipped and rotated footprints equal a reference
   placed by pcbnew itself (validates gen_pcb.flip_fp / place_fp)
3. courtyard overlaps per side
4. courtyards inside the board outline (edge parts J1/S2/U4 excepted)
5. bottom-side parts stay inside the trough between the ledges and clear of
   the through-hole pads of top-side parts; no top-side part in
   components.keepout_top (part bodies); USB-C, module and S2 where the housing wants them;
   v0.7: every part at its position in gen_pcb.main_placement() (the v0.6 positions plus the
   v0.7 power stage), J6 on the bottom face with pad n over pogo pin Pn (flashka_parts.KB), no
   paste on J6
6. pad nets agree with flashka_parts.py
Key board (--keys, v0.7): checks 1-3 and 6, plus outline and corner radius, bottom-face parts
and pogo pins at the interface positions (flashka_parts.KB), only the holes inside the d3.8
screw keep-outs, nothing on the floor-support areas of the bottom face, part heights in the
USB-C shadow (<= 0.4 mm) and the cell-wire zone (<= 1.0 mm) of the top face, and the
orientation marks of the silkscreen (inside the board, clear of keep-outs, floor supports and
mask openings, JLCPCB legend minimums).
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flashka_parts import COMPONENTS, KB  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KFP = "/usr/share/kicad/footprints"
EDGE_PARTS = {"J1", "S2", "U4"}
# housing-fixed parts whose courtyards may touch by design (v0.6: SW2/LED3; none since v0.7)
CRT_FIXED_PAIRS = set()
WIRE_PADS = {"J2", "J3", "J5"}   # U4: antenna overhangs the rear edge by design


def mm(v):
    return pcbnew.ToMM(v)


def hous(x, y):            # KiCad -> housing
    return x - 100.0, 100.0 - y


def lib_path(libref):
    lib, name = libref.split(":")
    if lib == "FlashKa":
        return os.path.join(HERE, "..", "..", "kicad", "FlashKa.pretty"), name
    return os.path.join(KFP, lib + ".pretty"), name


def courtyard_box(fp):
    layer = pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == layer:
            bb = g.GetBoundingBox()
            xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
            ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    if not xs:
        bb = fp.GetBoundingBox(False, False)
        xs = [mm(bb.GetLeft()), mm(bb.GetRight())]
        ys = [mm(bb.GetTop()), mm(bb.GetBottom())]
    return min(xs), min(ys), max(xs), max(ys)


def body_box(fp):
    """Bounding box of the part body (F.Fab / B.Fab outline); a wire pad has no body: its copper.
    v0.7: the top keep-out (front hold-down) forbids components, copper is allowed there, so the
    body counts, not the courtyard (the 3 x 3 mm buck U2 sits right next to it)"""
    layer = pcbnew.F_Fab if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_Fab
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == layer and g.GetClass() != "MTEXT" and "TEXT" not in g.GetClass():
            bb = g.GetBoundingBox()
            xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
            ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    if not xs:
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
            ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
    return min(xs), min(ys), max(xs), max(ys)


def overlap(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.01 and min(a[3], b[3]) - max(a[1], b[1]) > 0.01


def main(board_path, hj_path):
    hj = json.load(open(hj_path))
    ok = True
    brd = pcbnew.LoadBoard(board_path)
    fps = {f.GetReference(): f for f in brd.GetFootprints()}
    comps = {c["ref"]: c for c in COMPONENTS}
    print("loaded:", len(fps), "footprints, layers", brd.GetCopperLayerCount(),
          "thickness", mm(brd.GetDesignSettings().GetBoardThickness()))

    # 2. flip / rotation reference
    ref_board = pcbnew.BOARD()
    worst = 0.0
    for r, f in fps.items():
        lp, name = lib_path(comps[r]["fp"])
        g = pcbnew.FootprintLoad(lp, name)
        g.SetPosition(f.GetPosition())
        ref_board.Add(g)
        if f.GetLayer() == pcbnew.B_Cu:
            g.Flip(g.GetPosition(), False)
        g.SetOrientationDegrees(f.GetOrientationDegrees())
        a = sorted((p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y),
                    p.GetLayerSet().Contains(pcbnew.B_Cu), p.GetLayerSet().Contains(pcbnew.F_Cu))
                   for p in f.Pads())
        b = sorted((p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y),
                    p.GetLayerSet().Contains(pcbnew.B_Cu), p.GetLayerSet().Contains(pcbnew.F_Cu))
                   for p in g.Pads())
        for pa, pb in zip(a, b):
            d = abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
            worst = max(worst, d)
            if d > 0.001 or pa[3:] != pb[3:]:
                print("FLIP/ROT MISMATCH", r, pa, pb)
                ok = False
                break
        # pad orientation check (size along x/y after rotation)
        skey = lambda p: (p.GetNumber(), p.GetPosition().x, p.GetPosition().y, p.GetSizeX(), p.GetSizeY())
        for pa, pb in zip(sorted(f.Pads(), key=skey), sorted(g.Pads(), key=skey)):
            ba, bb_ = pa.GetBoundingBox(), pb.GetBoundingBox()
            if abs(mm(ba.GetWidth()) - mm(bb_.GetWidth())) > 0.01 or \
               abs(mm(ba.GetHeight()) - mm(bb_.GetHeight())) > 0.01:
                print("PAD SHAPE/ORIENT MISMATCH", r, pa.GetNumber())
                ok = False
                break
    print("flip/rotation check: worst pad offset %.4f mm" % worst)

    # 3. courtyard overlaps
    boxes = {r: courtyard_box(f) for r, f in fps.items()}
    side = {r: ("B" if f.GetLayer() == pcbnew.B_Cu else "F") for r, f in fps.items()}
    refs = sorted(fps)
    def cyard(f):
        return f.GetCourtyard(pcbnew.B_CrtYd if side[f.GetReference()] == "B" else pcbnew.F_CrtYd)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            if side[a] == side[b] and overlap(boxes[a], boxes[b]):
                if (a, b) in CRT_FIXED_PAIRS or (b, a) in CRT_FIXED_PAIRS:
                    # both parts are fixed by the housing (their positions may not move);
                    # the pads must stay >= 0.3 mm apart instead
                    dmin = min(((pcbnew.ToMM(p.GetPosition().x) - pcbnew.ToMM(q.GetPosition().x)) ** 2 +
                                (pcbnew.ToMM(p.GetPosition().y) - pcbnew.ToMM(q.GetPosition().y)) ** 2) ** 0.5
                               for p in fps[a].Pads() for q in fps[b].Pads())
                    print("courtyards of the housing-fixed pair %s/%s touch by design (closest pad centres %.2f mm)"
                          % (a, b, dmin))
                    continue
                pa, pb = cyard(fps[a]), cyard(fps[b])
                if pa.OutlineCount() and pb.OutlineCount():
                    inter = pcbnew.SHAPE_POLY_SET(pa)
                    inter.BooleanIntersection(pb, pcbnew.SHAPE_POLY_SET.PM_FAST)
                    if inter.Area() <= 1e-3 * pcbnew.FromMM(1) ** 2:
                        continue            # boxes touch, real courtyards do not
                print("COURTYARD OVERLAP", side[a], a, b)
                ok = False

    # 4. inside the outline (bounding box of outline, then notch tests)
    outline = hj["pcb_outline"]
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    poly = pcbnew.SHAPE_LINE_CHAIN()
    for (x, y) in outline:
        poly.Append(pcbnew.FromMM(100 + x), pcbnew.FromMM(100 - y))
    poly.SetClosed(True)
    for r, bx in boxes.items():
        if r in EDGE_PARTS:
            continue
        for (x, y) in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3])):
            if not poly.PointInside(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))):
                print("OUTSIDE OUTLINE", r, "corner", hous(x, y))
                ok = False
                break

    # 5. bottom side keep-in: between the ledges (trough_y) except where the
    #    housing has no ledge (trough_exceptions), outside keepout_bottom; THT
    #    pads of top parts (their leads stick out below) stay off the ledges
    c = hj["components"]
    ylo, yhi = c["trough_y"]
    tht = []
    for r, f in fps.items():
        if side[r] == "F":
            for p in f.Pads():
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    bb = p.GetBoundingBox()
                    tht.append((r, (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))))

    def limits(X0, X1):
        lo, hi = ylo, yhi
        for e in c["trough_exceptions"]:
            if X0 >= e["x0"] - 1e-6 and X1 <= e["x1"] + 1e-6:
                if e["side"] == "-Y":
                    lo = -99.0
                else:
                    hi = 99.0
        return lo, hi
    for r, bx in boxes.items():
        if side[r] != "B" or r in EDGE_PARTS:
            continue
        X0, Y1 = hous(bx[0], bx[1])
        X1, Y0 = hous(bx[2], bx[3])
        lo, hi = limits(X0, X1)
        if Y0 < lo or Y1 > hi:
            print("BOTTOM PART ON LEDGE", r, "Y %.2f..%.2f (allowed %.2f..%.2f)" % (Y0, Y1, lo, hi))
            ok = False
        for ci in c.get("keepout_bottom_circles", []):
            if not all(a in fps for a in ci["allowed"]):
                continue           # v0.6 light-pipe circle: its parts moved to the key board
            nx, ny = min(max(ci["x"], X0), X1), min(max(ci["y"], Y0), Y1)
            if r not in ci["allowed"] and ((nx - ci["x"]) ** 2 + (ny - ci["y"]) ** 2) ** 0.5 < ci["r"]:
                print("BOTTOM PART IN LIGHT-PIPE CIRCLE", r, ci["what"])
                ok = False
        for k in c["keepout_bottom"]:
            if X1 > k["x0"] and X0 < k["x1"] and Y1 > k["y0"] and Y0 < k["y1"]:
                print("BOTTOM PART IN KEEP-OUT", r, k["what"])
                ok = False
        for (tr, tb) in tht:
            if r in WIRE_PADS:
                # a wire pad pair has no body: only its copper (+0.2 mm) must stay off the peg/leg
                # (J5 sits around the 0.9 mm peg of S2, in the gap between its two pads)
                cu = [(mm(q.GetBoundingBox().GetLeft()) - 0.2, mm(q.GetBoundingBox().GetTop()) - 0.2,
                       mm(q.GetBoundingBox().GetRight()) + 0.2, mm(q.GetBoundingBox().GetBottom()) + 0.2)
                      for q in fps[r].Pads()]
                if any(overlap(b2, tb) for b2 in cu):
                    print("BOTTOM WIRE PAD OVER THT PAD", r, "of", tr)
                    ok = False
            elif overlap(bx, tb):
                print("BOTTOM PART OVER THT PAD", r, "of", tr)
                ok = False
    # 5a. top side keep-out (front hold-down: lid boss + pad press the board here; copper,
    #     vias and solder mask are allowed, components are not)
    for k in c.get("keepout_top", []):
        hit = []
        for r in boxes:
            if side[r] != "F":
                continue
            bx = body_box(fps[r])
            X0, Y1 = hous(bx[0], bx[1])
            X1, Y0 = hous(bx[2], bx[3])
            if X1 > k["x0"] + 0.005 and X0 < k["x1"] - 0.005 and Y1 > k["y0"] + 0.005 and Y0 < k["y1"] - 0.005:
                hit.append(r)
        print("top keep-out %s: %s" % (k["what"].split(" (")[0], ", ".join(hit) or "free"))
        if hit:
            print("TOP PART IN KEEP-OUT", hit)
            ok = False
    for (tr, tb) in tht:
        X0, Y1 = hous(tb[0], tb[1])
        X1, Y0 = hous(tb[2], tb[3])
        lo, hi = limits(X0, X1)
        if Y0 < lo - 0.1 or Y1 > hi + 0.1:
            print("THT PAD OVER LEDGE", tr, "Y %.2f..%.2f (allowed %.2f..%.2f)" % (Y0, Y1, lo, hi))
            ok = False

    # 5b. housing interface: the parts the housing fixes sit exactly where
    #     cad/housing_interface.json says (position, rotation, side); v0.7: every other part
    #     keeps its released v0.6 position, J6 sits under the pogo pins
    import gen_pcb
    plc = gen_pcb.main_placement()
    for r, f in fps.items():
        wx, wy, wr, ws = plc[r]
        px, py = hous(mm(f.GetPosition().x), mm(f.GetPosition().y))
        rot = f.GetOrientationDegrees() % 360
        if side[r] != ws or abs(px - wx) > 0.001 or abs(py - wy) > 0.001 or \
           min(abs(rot - wr % 360), 360 - abs(rot - wr % 360)) > 0.01:
            print("PLACEMENT MISMATCH", r, (px, py, rot, side[r]), "want", (wx, wy, wr, ws))
            ok = False
    jx = fps["J1"]
    jpx, jpy = hous(mm(jx.GetPosition().x), mm(jx.GetPosition().y))
    if side["J1"] != "B" or abs(jpx - c["J1_usb"]["x"]) > 0.001 or abs(jpy - (c["J1_usb"]["face_y"] + 3.65)) > 0.001:
        print("HOUSING INTERFACE MISMATCH J1", (jpx, jpy))
        ok = False
    m = c["U4_module"]
    ux, uy = hous(mm(fps["U4"].GetPosition().x), mm(fps["U4"].GetPosition().y))
    if abs(ux - (m["x_onboard_end"] - 5.6)) > 0.001 or abs(uy - m["y"]) > 0.001:
        print("HOUSING INTERFACE MISMATCH U4", (ux, uy))
        ok = False
    s2 = c["S2_interlock"]
    sx, sy = hous(mm(fps["S2"].GetPosition().x), mm(fps["S2"].GetPosition().y))
    if abs(sx - s2["x"]) > 0.001 or abs(sy - (s2["knob_tip_y"] - 3.15)) > 0.001:
        print("HOUSING INTERFACE MISMATCH S2", (sx, sy))
        ok = False
    for gone in ("S1", "SW1", "SW2", "SW3", "LED3", "LED4"):
        if gone in fps:
            print(gone, "still on the main board")
            ok = False
    # J6: pad n over pogo pin Pn, bottom copper + mask, no paste
    pads6 = {p.GetNumber(): p for p in fps["J6"].Pads()}
    for n, (pref, X, Y) in enumerate(KB["pogo"], start=1):
        p = pads6[str(n)]
        px, py = hous(mm(p.GetPosition().x), mm(p.GetPosition().y))
        lay = p.GetLayerSet()
        if abs(px - X) > 0.001 or abs(py - Y) > 0.001 or not lay.Contains(pcbnew.B_Cu) or \
           not lay.Contains(pcbnew.B_Mask) or lay.Contains(pcbnew.B_Paste) or lay.Contains(pcbnew.F_Cu):
            print("J6 PAD WRONG", n, (px, py), "want over", pref, (X, Y))
            ok = False
    print("J6: 6 target pads over the pogo pins", ", ".join(f"{p}({x}, {y})" for p, x, y in KB["pogo"]))
    # light-pipe circles (v0.6 housing file): only meaningful while their parts are on this board
    for ci in c.get("keepout_bottom_circles", []):
        if not all(a in fps for a in ci["allowed"]):
            continue
        inside = sorted(r for r, bx in boxes.items() if side[r] == "B" and
                        ((min(max(ci["x"], hous(bx[0], bx[1])[0]), hous(bx[2], bx[3])[0]) - ci["x"]) ** 2 +
                         (min(max(ci["y"], hous(bx[2], bx[3])[1]), hous(bx[0], bx[1])[1]) - ci["y"]) ** 2) ** 0.5 < ci["r"])
        print("parts touching the r %.1f circle on the bottom: %s" % (ci["r"], ", ".join(inside)))
        if sorted(inside) != sorted(ci["allowed"]):
            print("LIGHT-PIPE CIRCLE: expected exactly", ci["allowed"])
            ok = False

    # 6. nets
    for r, f in fps.items():
        want = comps[r]["nets"]
        for p in f.Pads():
            n = p.GetNetname()
            w = want.get(p.GetNumber(), "")
            if (n or "") != w:
                print("NET MISMATCH", r, p.GetNumber(), repr(n), "want", repr(w))
                ok = False
                break
    print("PCB CHECK:", "OK" if ok else "ERRORS")
    return ok


# key board: part heights above the top face (mm, worst case) for the zones with a height limit
TOP_HEIGHT = {"Resistor_SMD:R_0402_1005Metric": 0.40, "FlashKa:Pogo_Harwin_P70-1010045R": 5.0,
              "FlashKa:MountingHole_1.8mm_M1.6": 0.0}


def main_keys(board_path):
    """Key board checks (see the module docstring)."""
    import math
    ok = True
    brd = pcbnew.LoadBoard(board_path)
    fps = {f.GetReference(): f for f in brd.GetFootprints()}
    comps = {c["ref"]: c for c in COMPONENTS if c["board"] == "keys"}
    print("loaded:", len(fps), "footprints, layers", brd.GetCopperLayerCount(),
          "thickness", mm(brd.GetDesignSettings().GetBoardThickness()))
    if set(fps) != set(comps):
        print("PARTS DIFFER from flashka_parts.py:", sorted(set(fps) ^ set(comps)))
        ok = False
    side = {r: ("B" if f.GetLayer() == pcbnew.B_Cu else "F") for r, f in fps.items()}
    # flip / rotation reference (as for the main board)
    worst = 0.0
    ref_board = pcbnew.BOARD()
    for r, f in fps.items():
        lp, name = lib_path(comps[r]["fp"])
        g = pcbnew.FootprintLoad(lp, name)
        g.SetPosition(f.GetPosition())
        ref_board.Add(g)
        if side[r] == "B":
            g.Flip(g.GetPosition(), False)
        g.SetOrientationDegrees(f.GetOrientationDegrees())
        a = sorted((p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in f.Pads())
        b = sorted((p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in g.Pads())
        for pa, pb in zip(a, b):
            worst = max(worst, abs(pa[1] - pb[1]) + abs(pa[2] - pb[2]))
    print("flip/rotation check: worst pad offset %.4f mm" % worst)
    if worst > 0.001:
        ok = False
    # courtyards per side (real polygons)
    refs = sorted(fps)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            if side[a] != side[b]:
                continue
            lay = pcbnew.B_CrtYd if side[a] == "B" else pcbnew.F_CrtYd
            pa, pb = fps[a].GetCourtyard(lay), fps[b].GetCourtyard(lay)
            if pa.OutlineCount() and pb.OutlineCount():
                inter = pcbnew.SHAPE_POLY_SET(pa)
                inter.BooleanIntersection(pb, pcbnew.SHAPE_POLY_SET.PM_FAST)
                if inter.Area() > 1e-3 * pcbnew.FromMM(1) ** 2:
                    print("COURTYARD OVERLAP", side[a], a, b)
                    ok = False
    # outline: bounding box and corner radius
    bb = brd.GetBoardEdgesBoundingBox()
    X0, Y0, X1, Y1 = KB["outline"]
    got = (round(mm(bb.GetLeft()) - 100, 3), round(100 - mm(bb.GetBottom()), 3),
           round(mm(bb.GetRight()) - 100, 3), round(100 - mm(bb.GetTop()), 3))
    print("outline X %.2f..%.2f, Y %.2f..%.2f (want X %.2f..%.2f, Y %.2f..%.2f, corners R%.1f)"
          % (got[0], got[2], got[1], got[3], X0, X1, Y0, Y1, KB["corner_r"]))
    if any(abs(u - v) > 0.06 for u, v in zip(got, (X0, Y0, X1, Y1))):    # line width 0.1 included
        print("KB OUTLINE MISMATCH")
        ok = False
    arcs = [d for d in brd.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_ARC]
    if len(arcs) != 4 or any(abs(mm(a.GetRadius()) - KB["corner_r"]) > 0.01 for a in arcs):
        print("KB CORNER RADIUS MISMATCH", [round(mm(a.GetRadius()), 3) for a in arcs])
        ok = False
    # interface positions: bottom parts, pogo pins, holes
    want = {r: (X, Y, rot, "B") for r, (X, Y, rot) in KB["bottom"].items()}
    want.update({r: (X, Y, 0, "F") for r, X, Y in KB["pogo"]})
    want.update({f"H{n + 1}": (X, Y, 0, "F") for n, (X, Y) in enumerate(KB["holes"])})
    for r, (wx, wy, wr, ws) in want.items():
        f = fps[r]
        px, py = hous(mm(f.GetPosition().x), mm(f.GetPosition().y))
        rot = f.GetOrientationDegrees() % 360
        if side[r] != ws or abs(px - wx) > 0.001 or abs(py - wy) > 0.001 or \
           min(abs(rot - wr % 360), 360 - abs(rot - wr % 360)) > 0.01:
            print("KB INTERFACE MISMATCH", r, (px, py, rot, side[r]), "want", (wx, wy, wr, ws))
            ok = False
    # switch pads along X (SW1) / Y (SW2, SW3), as the keys need them
    for r, axis in (("SW1", "X"), ("SW2", "Y"), ("SW3", "Y")):
        p = sorted(fps[r].Pads(), key=lambda q: q.GetNumber())
        dx = abs(mm(p[0].GetPosition().x - p[1].GetPosition().x))
        dy = abs(mm(p[0].GetPosition().y - p[1].GetPosition().y))
        if (axis == "X") != (dx > dy):
            print("SWITCH PADS NOT ALONG", axis, r)
            ok = False
    print("interface: SW1-SW3, LED3, LED4 (bottom), P1-P6 (top), H1, H2 at the flashka_parts.KB positions")
    # screw keep-outs: only the hole's own footprint inside, no copper but the hole (none)
    for n, (hx, hy) in enumerate(KB["holes"]):
        rk = KB["keepout_d"] / 2
        for r, f in fps.items():
            if r == f"H{n + 1}":
                continue
            lay = pcbnew.B_CrtYd if side[r] == "B" else pcbnew.F_CrtYd
            cy = f.GetCourtyard(lay)
            circ = pcbnew.SHAPE_POLY_SET()
            circ.NewOutline()
            for k in range(48):
                circ.Append(pcbnew.FromMM(100 + hx + rk * math.cos(2 * math.pi * k / 48)),
                            pcbnew.FromMM(100 - hy + rk * math.sin(2 * math.pi * k / 48)))
            if cy.OutlineCount():
                inter = pcbnew.SHAPE_POLY_SET(cy)
                inter.BooleanIntersection(circ, pcbnew.SHAPE_POLY_SET.PM_FAST)
                if inter.Area() > 1e-4 * pcbnew.FromMM(1) ** 2:
                    print("PART IN SCREW KEEP-OUT", r, f"H{n + 1}")
                    ok = False
    # floor supports (bottom face): no part courtyard, no pad
    for (x0, y0, x1, y1) in KB["floor_supports"]:
        for r, f in fps.items():
            if side[r] != "B":
                continue
            bx = courtyard_box(f)
            HX0, HY1 = hous(bx[0], bx[1])
            HX1, HY0 = hous(bx[2], bx[3])
            if HX1 > x0 and HX0 < x1 and HY1 > y0 and HY0 < y1:
                print("PART ON FLOOR SUPPORT AREA", r, (x0, y0, x1, y1))
                ok = False
    # height zones of the top face (USB-C shadow, cell wires)
    for (zone, hmax), what in ((KB["j1_shadow"], "USB-C shadow"), (KB["cell_wires"], "cell-wire zone")):
        x0, y0, x1, y1 = zone
        inside = []
        for r, f in fps.items():
            if side[r] != "F":
                continue
            bx = courtyard_box(f)
            HX0, HY1 = hous(bx[0], bx[1])
            HX1, HY0 = hous(bx[2], bx[3])
            if HX1 > x0 and HX0 < x1 and HY1 > y0 and HY0 < y1:
                h = TOP_HEIGHT.get(comps[r]["fp"])
                inside.append(f"{r} {h} mm")
                if h is None or h > hmax + 1e-9:
                    print("PART TOO TALL IN", what, r, h, "max", hmax)
                    ok = False
        print("top face, %s (max %.1f mm): %s" % (what, hmax, ", ".join(inside) or "free"))
    # silkscreen marks (board-level F/B.SilkS items): inside the board, clear of the screw keep-outs, of
    # the floor-support areas (bottom) and of every mask opening (JLCPCB: silkscreen to pad 0.15 mm);
    # text at least 1.0 mm high with lines >= 0.153 mm and >= 1/6 of the height (JLCPCB legend rules)
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    H2 = lambda x, y: (mm(x) - 100, 100 - mm(y))
    X0, Y0, X1, Y1 = KB["outline"]
    keep = [Point(hx, hy).buffer(KB["keepout_d"] / 2, 64) for (hx, hy) in KB["holes"]]
    floor = [box(*a) for a in KB["floor_supports"]]
    masks = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for r, f in fps.items():
        for p in f.Pads():
            for silk, ml in ((pcbnew.F_SilkS, pcbnew.F_Mask), (pcbnew.B_SilkS, pcbnew.B_Mask)):
                if p.IsOnLayer(ml):
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, ml, int(p.GetSolderMaskExpansion()), pcbnew.FromMM(0.005))
                    for n in range(ps.OutlineCount()):
                        o = ps.Outline(n)
                        masks[silk].append(Polygon([H2(o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())]).buffer(0))
    marks = []
    for d in brd.GetDrawings():
        lay = d.GetLayer()
        if lay not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        if d.GetClass() == "PCB_TEXT":
            sb = d.GetEffectiveShape(lay).BBox()          # stroke extents incl. line width
            (ax0, ay1), (ax1, ay0) = H2(sb.GetLeft(), sb.GetTop()), H2(sb.GetRight(), sb.GetBottom())
            g, name = box(ax0, ay0, ax1, ay1), '"%s"' % d.GetText()
            hh, ww = mm(d.GetTextHeight()), mm(d.GetTextThickness())
            if hh < 1.0 - 1e-9 or ww < max(0.153, hh / 6) - 1e-9:
                print("SILK TEXT BELOW THE JLCPCB MINIMUM", name, hh, ww)
                ok = False
        elif d.GetShape() == pcbnew.SHAPE_T_POLY:
            o = d.GetPolyShape().Outline(0)
            g, name = Polygon([H2(o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())]).buffer(mm(d.GetWidth()) / 2), "arrow"
        else:
            g = LineString([H2(d.GetStart().x, d.GetStart().y), H2(d.GetEnd().x, d.GetEnd().y)]).buffer(mm(d.GetWidth()) / 2)
            name = "line"
            if mm(d.GetWidth()) < 0.153 - 1e-9:
                print("SILK LINE BELOW THE JLCPCB MINIMUM", mm(d.GetWidth()))
                ok = False
        brdbox = box(X0, Y0, X1, Y1)
        e = brdbox.exterior.distance(g) if brdbox.contains(g) else -1.0
        k = min(c.distance(g) for c in keep)
        fl = min(a.distance(g) for a in floor) if lay == pcbnew.B_SilkS else 99.0
        mk = min((m.distance(g) for m in masks[lay]), default=99.0)
        if e < 0.25 or k <= 0.0 or fl <= 0.0 or mk < 0.15:
            print("SILK MARK TOO CLOSE", name, "edge %.2f keep-out %.2f floor %.2f mask %.2f" % (e, k, fl, mk))
            ok = False
        marks.append((name, "top" if lay == pcbnew.F_SilkS else "bottom", e, k, mk))
    print("silkscreen marks: %s (min edge %.2f, screw keep-outs %.2f, mask openings %.2f mm)" % (
        ", ".join(f"{n} {s}" for n, s, *_ in marks), min(m[2] for m in marks), min(m[3] for m in marks),
        min(m[4] for m in marks)) if marks else "silkscreen marks: none")
    # nets
    for r, f in fps.items():
        w = comps[r]["nets"]
        for p in f.Pads():
            n = p.GetNetname()
            if (n or "") != w.get(p.GetNumber(), ""):
                print("NET MISMATCH", r, p.GetNumber(), repr(n), "want", repr(w.get(p.GetNumber(), "")))
                ok = False
    print("KB CHECK:", "OK" if ok else "ERRORS")
    return ok


if __name__ == "__main__":
    if "--keys" in sys.argv:
        sys.exit(0 if main_keys(sys.argv[1]) else 1)
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
