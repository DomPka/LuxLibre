#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks for the generated Aurora++ v0.5 board (run with KiCad 7's pcbnew).

1. the file loads in pcbnew
2. pad positions/layers of flipped and rotated footprints equal a reference
   placed by pcbnew itself (validates gen_pcb.flip_fp / place_fp)
3. courtyard overlaps per side
4. courtyards inside the board outline (edge parts J1/S1/S2 excepted)
5. bottom-side parts stay inside the trough between the ledges and clear of
   the through-hole pads of top-side parts
6. pad nets agree with aurora_parts.py
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aurora_parts import COMPONENTS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KFP = "/usr/share/kicad/footprints"
EDGE_PARTS = {"J1", "S1", "S2", "U4"}   # U4: antenna overhangs the rear edge by design


def mm(v):
    return pcbnew.ToMM(v)


def hous(x, y):            # KiCad -> housing
    return x - 100.0, 100.0 - y


def lib_path(libref):
    lib, name = libref.split(":")
    if lib == "Aurora":
        return os.path.join(HERE, "..", "..", "kicad", "Aurora.pretty"), name
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
        for k in c["keepout_bottom"]:
            if X1 > k["x0"] and X0 < k["x1"] and Y1 > k["y0"] and Y0 < k["y1"]:
                print("BOTTOM PART IN KEEP-OUT", r, k["what"])
                ok = False
        for (tr, tb) in tht:
            if overlap(bx, tb):
                print("BOTTOM PART OVER THT PAD", r, "of", tr)
                ok = False
    for (tr, tb) in tht:
        X0, Y1 = hous(tb[0], tb[1])
        X1, Y0 = hous(tb[2], tb[3])
        lo, hi = limits(X0, X1)
        if Y0 < lo - 0.1 or Y1 > hi + 0.1:
            print("THT PAD OVER LEDGE", tr, "Y %.2f..%.2f (allowed %.2f..%.2f)" % (Y0, Y1, lo, hi))
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


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
