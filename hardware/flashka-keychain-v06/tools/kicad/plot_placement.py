# SPDX-License-Identifier: GPL-3.0-or-later
"""Plot top/bottom courtyards of a board (housing coordinates)."""
import sys, json
import pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon
sys.path.insert(0, __import__("os").path.dirname(__file__))
from check_pcb import courtyard_box
b = pcbnew.LoadBoard(sys.argv[1]); hj = json.load(open(sys.argv[2]))
fig, axs = plt.subplots(2, 1, figsize=(11, 9))
for ax, side in zip(axs, (pcbnew.F_Cu, pcbnew.B_Cu)):
    ax.add_patch(Polygon([(x, y) for x, y in hj["pcb_outline"]], fill=False, ec="k", lw=1.5))
    for f in b.GetFootprints():
        if f.GetLayer() != side:
            for p in f.Pads():
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    bb = p.GetBoundingBox()
                    x0, y1 = pcbnew.ToMM(bb.GetLeft()) - 100, 100 - pcbnew.ToMM(bb.GetTop())
                    x1, y0 = pcbnew.ToMM(bb.GetRight()) - 100, 100 - pcbnew.ToMM(bb.GetBottom())
                    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="r", alpha=0.3))
            continue
        x0, y0k, x1, y1k = courtyard_box(f)
        X0, X1 = x0 - 100, x1 - 100; Y0, Y1 = 100 - y1k, 100 - y0k
        ax.add_patch(Rectangle((X0, Y0), X1 - X0, Y1 - Y0, fill=False, ec="b"))
        ax.text((X0 + X1) / 2, (Y0 + Y1) / 2, f.GetReference(), fontsize=7, ha="center", va="center")
    P = hj["params"]; ih = P["W"] / 2 - P["wall"]
    if side == pcbnew.B_Cu:
        ax.axhline(-(ih - P["ledge_w"]), color="g", lw=0.8); ax.axhline(ih - P["ledge_w_btn"], color="g", lw=0.8)
    for (x, y) in P["lights"] if side == pcbnew.F_Cu else []:
        ax.add_patch(plt.Circle((x, y), P["light_d"] / 2, fc="y", alpha=0.6))
    ax.set_xlim(9, 41); ax.set_ylim(-13, 11); ax.set_aspect("equal")
    ax.set_title("TOP (seen from lid)" if side == pcbnew.F_Cu else "BOTTOM (seen from lid, through the board)")
    ax.grid(alpha=0.2)
plt.tight_layout(); plt.savefig(sys.argv[3], dpi=110)
