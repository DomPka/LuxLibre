#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plot a routed board layer by layer (pads, tracks, vias, zones) to a PNG."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon
import pcbnew

LAYERS = [(pcbnew.F_Cu, "F.Cu (top, lid side)", "#c83434"), (pcbnew.In1_Cu, "In1.Cu (GND plane)", "#3a7d3a"),
          (pcbnew.In2_Cu, "In2.Cu", "#c8a034"), (pcbnew.B_Cu, "B.Cu (bottom, seen from top)", "#3464c8")]


def mm(v):
    return pcbnew.ToMM(v)


def plot(path, out, zones=True, window=None):
    b = pcbnew.LoadBoard(path)
    if zones:
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    fig, axs = plt.subplots(2, 2, figsize=(16, 12))
    ps = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(ps)
    edge = []
    if ps.OutlineCount():
        o = ps.Outline(0)
        edge = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
    for ax, (lid, title, col) in zip(axs.ravel(), LAYERS):
        if zones:
            for z in b.Zones():
                if z.GetLayer() != lid:
                    continue
                fp = z.GetFilledPolysList(lid)
                for k in range(fp.OutlineCount()):
                    o = fp.Outline(k)
                    pts = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
                    ax.add_patch(Polygon(pts, closed=True, fc="#d8ecd8", ec="none", alpha=0.8))
        for pad in b.GetPads():
            if not pad.IsOnLayer(lid):
                continue
            ps = pcbnew.SHAPE_POLY_SET()
            pad.TransformShapeToPolygon(ps, lid if lid in (pcbnew.F_Cu, pcbnew.B_Cu) else pcbnew.F_Cu, 0,
                                        pcbnew.FromMM(0.01))
            for k in range(ps.OutlineCount()):
                o = ps.Outline(k)
                pts = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
                ax.add_patch(Polygon(pts, closed=True, fc="#888888" if pad.GetNetCode() <= 0 else "#444444",
                                     ec="none", alpha=0.9))
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                ax.add_patch(Circle((mm(t.GetPosition().x), mm(t.GetPosition().y)), mm(t.GetWidth()) / 2,
                                    fc="#222", ec="none"))
                ax.add_patch(Circle((mm(t.GetPosition().x), mm(t.GetPosition().y)), mm(t.GetDrill()) / 2,
                                    fc="white", ec="none"))
            elif t.GetLayer() == lid:
                ax.plot([mm(t.GetStart().x), mm(t.GetEnd().x)], [mm(t.GetStart().y), mm(t.GetEnd().y)],
                        color=col, lw=max(0.6, mm(t.GetWidth()) * 28), solid_capstyle="round", alpha=0.85)
        if edge:
            xs = [p[0] for p in edge] + [edge[0][0]]
            ys = [p[1] for p in edge] + [edge[0][1]]
            ax.plot(xs, ys, "k-", lw=1)
        bb = b.GetBoardEdgesBoundingBox()
        if window:
            ax.set_xlim(window[0], window[2])
            ax.set_ylim(window[3], window[1])
        else:
            ax.set_xlim(mm(bb.GetLeft()) - 0.5, mm(bb.GetRight()) + 0.5)
            ax.set_ylim(mm(bb.GetBottom()) + 0.5, mm(bb.GetTop()) - 0.5)
        if window:
            for fp in b.GetFootprints():
                pos = fp.GetPosition()
                x, y = mm(pos.x), mm(pos.y)
                if window[0] <= x <= window[2] and window[1] <= y <= window[3]:
                    onl = (fp.GetLayer() == pcbnew.B_Cu) == (lid == pcbnew.B_Cu)
                    if onl or lid in (pcbnew.F_Cu, pcbnew.B_Cu):
                        ax.text(x, y, fp.GetReference(), fontsize=7, ha="center", va="center",
                                color="black" if onl else "#999999")
        ax.set_aspect("equal")
        ax.set_title(title)
    plt.tight_layout()
    plt.savefig(out, dpi=100)


if __name__ == "__main__":
    win = [float(v) for v in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    plot(sys.argv[1], sys.argv[2], zones=True, window=win)
