#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Wiring picture for builders: both sides of the main PCB with the hand-soldered
pads (cells J2, LED J3, laser J5) coloured by polarity and the parts a builder
has to recognise (USB-C, button S1, slide switch S2, Bluetooth module).

usage:  python3 tools/kicad/plot_wiring.py kicad/Aurora_main/Aurora_main.kicad_pcb out.png
The top side is drawn as seen from above (lid side). The bottom side is drawn as
seen after turning the board over around its long edge: the front (LED) end
stays on the left, the USB-C edge comes to the top.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import pcbnew

PLUS, MINUS, PART = "#d62728", "#1f3a5a", "#9aa4ae"
WIRES = {   # (ref, pad) -> (label, colour)
    ("J2", "1"): ("J2 +  cells (red)", PLUS),
    ("J2", "2"): ("J2 −  cells (black)", MINUS),
    ("J3", "1"): ("J3 LED+ (red)", PLUS),
    ("J3", "2"): ("J3 LED− (black)", MINUS),
    ("J5", "1"): ("J5 +  laser (red)", PLUS),
    ("J5", "2"): ("J5 −  laser (black)", MINUS),
}
PARTS = {"F": [("U4", "U4 Bluetooth module"), ("S2", "S2 laser safety switch")],
         "B": [("J1", "J1 USB-C socket"), ("S1", "S1 button")]}


def mm(v):
    return pcbnew.ToMM(v)


def pad_polys(pad, layer):
    ps = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.005))
    out = []
    for n in range(ps.OutlineCount()):
        o = ps.Outline(n)
        out.append([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())])
    return out


def main(path, out):
    b = pcbnew.LoadBoard(path)
    ol = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(ol)
    o = ol.Outline(0)
    outline = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    fig, axes = plt.subplots(2, 1, figsize=(11, 10.5))
    for ax, side in zip(axes, ("F", "B")):
        lid = pcbnew.F_Cu if side == "F" else pcbnew.B_Cu
        ax.add_patch(Polygon(outline, closed=True, fc="#e3ecd9", ec="k", lw=1.2))
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if not pad.IsOnLayer(lid):
                    continue
                key = (fp.GetReference(), pad.GetNumber())
                if key in WIRES and not ((key == ("J3", "1") and side == "B") or (key == ("J3", "2") and side == "F")):
                    col = WIRES[key][1]
                else:
                    col = PART
                for poly in pad_polys(pad, lid):
                    ax.add_patch(Polygon(poly, closed=True, fc=col, ec="none", alpha=1.0 if col != PART else 0.8))
        # labels: wire pads and the parts to recognise, outside the board, staggered so they never overlap
        labs = []
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                key = (fp.GetReference(), pad.GetNumber())
                if key not in WIRES or not pad.IsOnLayer(lid):
                    continue
                if (key == ("J3", "1") and side == "B") or (key == ("J3", "2") and side == "F"):
                    continue
                label, col = WIRES[key]
                labs.append(([(mm(pad.GetPosition().x), mm(pad.GetPosition().y))], label, col, "bold"))
        # the two laser pads sit side by side: one label with two leaders
        j5 = [l for l in labs if l[1].startswith("J5")]
        if len(j5) == 2:
            labs = [l for l in labs if not l[1].startswith("J5")]
            pts = sorted(j5[0][0] + j5[1][0])
            labs.append((pts, "J5 laser:  + red (left),  − black (right)", "#5b1a2a", "bold"))
        for ref, label in PARTS[side]:
            fp = b.FindFootprintByReference(ref)
            if fp is not None:
                bb = fp.GetBoundingBox(False, False)
                labs.append(([(mm(bb.GetCenter().x), mm(bb.GetCenter().y))], label, "#333", "normal"))
        flip = side == "B"
        for row in ("outside_low", "outside_high"):
            # "low" = small KiCad y (the +Y edge); drawn at the top for the top view, at the bottom when flipped
            sel = [l for l in labs if (l[0][0][1] < (y0 + y1) / 2) == (row == "outside_low")]
            sel.sort(key=lambda l: sum(p[0] for p in l[0]) / len(l[0]))
            ends = []                      # right end of the last text on each level
            for (pts, label, col, weight) in sel:
                px = sum(p[0] for p in pts) / len(pts)
                w = 0.56 * max(len(t) for t in label.split("\n"))
                tx = min(max(px, x0 - 5.0 + w / 2), x1 + 4.5 - w / 2)
                lvl = 0
                while lvl < len(ends) and tx - w / 2 < ends[lvl] + 0.6:
                    lvl += 1
                if lvl == len(ends):
                    ends.append(-1e9)
                ends[lvl] = tx + w / 2
                d = 2.0 + 2.1 * lvl
                ty = (y0 - d) if row == "outside_low" else (y1 + d)
                for k, (ax_, ay_) in enumerate(pts):
                    ax.annotate(label if k == 0 else "", (ax_, ay_), xytext=(tx, ty), ha="center", va="center",
                                fontsize=10, color=col, fontweight=weight,
                                arrowprops=dict(arrowstyle="-", color=col, lw=1.3 if weight == "bold" else 0.9,
                                                shrinkA=6))
        ax.text(x0 - 0.8, (y0 + y1) / 2, "FRONT\n(LED end)", ha="right", va="center", fontsize=10, color="#333")
        ax.text(x1 + 0.8, (y0 + y1) / 2, "REAR\n(cells)", ha="left", va="center", fontsize=10, color="#333")
        ax.set_xlim(x0 - 5.5, x1 + 5.0)
        ax.set_ylim(y0 - 8.5, y1 + 8.5)
        ax.set_aspect("equal")
        if side == "F":
            ax.invert_yaxis()           # KiCad y points down: seen from above
            ax.set_title("TOP side (lid side, with the Bluetooth module) — seen from above", fontsize=12)
        else:
            ax.set_title("BOTTOM side (with the USB-C socket) — board turned over along its long edge",
                         fontsize=12)
        ax.axis("off")
    fig.text(0.5, 0.015, "red = + (plus), dark blue = − (minus); grey = other pads. "
             "J3 is one pad on each side at the same spot: LED+ on top, LED− underneath.",
             ha="center", fontsize=10, color="#333")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    plt.savefig(out, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
