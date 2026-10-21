#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Size comparison picture v0.6: FlashKa Keychain v0.6 next to the v0.4 body and the RovyVon Aurora A9 Pro.

usage (needs an X server for VTK: xvfb-run -a):
    xvfb-run -a python3 tools/housing/size_comparison.py <cad_dir> <out_dir> [--v04-cad DIR]

  <cad_dir>    folder written by flashka_housing.py (v0.6: FlashKa_tray.stl, FlashKa_lid.stl, ...)
  <out_dir>    where size_comparison_A9.png and size_comparison_summary.txt go
  --v04-cad    folder with the v0.4 STL files (default: <repo>/cad if it holds a v0.4 tray of
               107.6 x 24 x 14 mm).  Without it the v0.4 body is drawn as a plain outline.

FlashKa Keychain v0.6 (and v0.4 when its STL files are available) is rendered orthographically
(top = lid side, and the control side) at a known scale.  The RovyVon Aurora A9 Pro is drawn as a
plain outline of its published size (60.5 x 15.5 mm, RovyVon's "2.38 inch x 0.61 inch"), with a
EUR 2 coin and a US quarter for reference - everything on the same scale, head ends lined up.

Numbers: v0.6 length / width / height come from flashka_housing.P (L, W, H); v0.4 is 107.6 x 24 x 14 mm
(read from its tray STL when present); the "envelope volume" is the bounding box L x W x H, the A9 Pro
is taken as D x D x L (a square envelope, the same measure) and additionally as its real cylinder.
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon  # noqa: E402
import numpy as np  # noqa: E402
import vtk  # noqa: E402
from vtk.util.numpy_support import vtk_to_numpy  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402

PPM = 16                      # render resolution, px per mm
A9 = {"L": 60.5, "D": 15.5}   # RovyVon Aurora A9 Pro, published: 2.38 in x 0.61 in
DPI = 181                       # picture resolution: about 1600 px wide, like the other renders
V04 = {"L": 107.6, "W": 24.0, "H": 14.0}   # the v0.4 body (tray bounding box)
ALU = 2.70                    # g/cm3, 6061
INCH = 25.4
ORANGE = "#f39200"
INK = "#2b2f36"
DIM = "#6b7078"

COL = {"FlashKa_tray": (0.20, 0.21, 0.24), "FlashKa_lid": (0.26, 0.27, 0.30),
       "FlashKa_rf_window": (0.93, 0.95, 0.98),
       # parts that show through the openings of the control side
       "_ref_usb": (0.80, 0.80, 0.82), "_ref_s2_knob": (0.92, 0.92, 0.92),
       "_ref_pcb_real": (0.10, 0.45, 0.22), "_ref_pcb": (0.10, 0.45, 0.22),
       "_ref_lidscrews": (0.58, 0.60, 0.63)}


def ortho(parts, cam_dir, up, centre, size_mm):
    """Orthographic render of parts = [(folder, name), ...]: world rectangle size_mm = (w, h) around
    centre, seen along cam_dir with the given up vector; returns an RGB array."""
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    for folder, n in parts:
        r = vtk.vtkSTLReader()
        r.SetFileName(os.path.join(folder, n + ".stl"))
        nm = vtk.vtkPolyDataNormals()
        nm.SetInputConnection(r.GetOutputPort())
        nm.SetFeatureAngle(30)
        nm.SplittingOn()
        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(nm.GetOutputPort())
        a = vtk.vtkActor()
        a.SetMapper(m)
        pr = a.GetProperty()
        pr.SetColor(*COL[n])
        pr.SetSpecular(0.25)
        pr.SetSpecularPower(25)
        pr.SetDiffuse(0.85)
        pr.SetAmbient(0.22)
        ren.AddActor(a)
    l1 = vtk.vtkLight()
    l1.SetLightTypeToCameraLight()
    l1.SetPosition(0.35, 0.55, 1)
    l1.SetIntensity(0.75)
    ren.AddLight(l1)
    l2 = vtk.vtkLight()                 # raking light: shows recesses and openings
    l2.SetLightTypeToCameraLight()
    l2.SetPosition(-1.0, 1.2, 0.6)
    l2.SetIntensity(0.55)
    ren.AddLight(l2)
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cx, cy, cz = centre
    dx, dy, dz = cam_dir
    cam.SetFocalPoint(cx, cy, cz)
    cam.SetPosition(cx - 300 * dx, cy - 300 * dy, cz - 300 * dz)
    cam.SetViewUp(*up)
    cam.SetParallelScale(size_mm[1] / 2)
    ren.ResetCameraClippingRange()
    w = vtk.vtkRenderWindow()
    w.SetOffScreenRendering(1)
    w.AddRenderer(ren)
    w.SetSize(int(size_mm[0] * PPM), int(size_mm[1] * PPM))
    w.SetMultiSamples(8)
    w.Render()
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(w)
    f.ReadFrontBufferOff()
    f.Update()
    img = f.GetOutput()
    wd, ht, _ = img.GetDimensions()
    arr = vtk_to_numpy(img.GetPointData().GetScalars()).reshape(ht, wd, -1)[::-1, :, :3]
    return arr


def vbracket(ax, x, y0, y1, label, side=1, tick=2.2):
    """Vertical dimension bracket at x from y0 to y1, ticks pointing to -side."""
    ax.plot([x, x], [y0, y1], color=DIM, lw=1.6, solid_capstyle="butt")
    for y in (y0, y1):
        ax.plot([x, x - side * tick], [y, y], color=DIM, lw=1.6)
    ym = (y0 + y1) / 2
    ax.text(x + side * 3.2, ym, label, rotation=90, ha="center", va="center",
            fontsize=10.5, color=INK, fontweight="bold" if "\n" not in label else "normal")


def hbracket(ax, y, x0, x1, label, tick=2.2):
    ax.plot([x0, x1], [y, y], color=DIM, lw=1.6)
    for x in (x0, x1):
        ax.plot([x, x], [y, y - tick], color=DIM, lw=1.6)
    ax.text((x0 + x1) / 2, y + 1.6, label, ha="center", va="bottom", fontsize=10.5, color=INK)


def fmt(mm):
    return f"{mm:.1f} mm  ({mm / INCH:.2f} in)".replace(".0 mm", " mm")


def fmt2(mm):
    return f"{mm:.1f} mm\n({mm / INCH:.2f} in)".replace(".0 mm", " mm")


def mass_g(cad):
    """tray + lid mass (g, 6061) from the volumes in housing_interface.json, or None"""
    try:
        v = json.load(open(os.path.join(cad, "housing_interface.json")))["volumes_mm3"]
        return (v["FlashKa_tray"] + v["FlashKa_lid"]) * ALU * 1e-3
    except Exception:
        return None


def v04_dims(v04_cad):
    """(L, W, H) of the v0.4 tray from its STL when it is there and plausible, else the known numbers"""
    if v04_cad and os.path.exists(os.path.join(v04_cad, "FlashKa_tray.stl")):
        r = vtk.vtkSTLReader()
        r.SetFileName(os.path.join(v04_cad, "FlashKa_tray.stl"))
        r.Update()
        b = r.GetOutput().GetBounds()
        d = (b[1] - b[0], b[3] - b[2], b[5] - b[4])
        if all(abs(d[i] - v) < 0.2 for i, v in enumerate((V04["L"], V04["W"], V04["H"]))):
            return d, True
    return (V04["L"], V04["W"], V04["H"]), False


def summary_lines(L5, W5, H5, L4, W4, H4):
    v5, v4 = L5 * W5 * H5 / 1000.0, L4 * W4 * H4 / 1000.0
    va9 = A9["L"] * A9["D"] ** 2 / 1000.0
    va9c = math.pi / 4 * A9["D"] ** 2 * A9["L"] / 1000.0
    return [
        f"Length: v0.6 {L5:.1f} mm = {L5 / L4 * 100:.0f} % of v0.4 ({L4:.1f} mm, {L4 - L5:.1f} mm shorter); "
        f"{L5 / A9['L']:.2f} x the A9 Pro ({A9['L']:.1f} mm, {L5 - A9['L']:.1f} mm longer).",
        f"Cross-section: v0.6 {W5:.0f} x {H5:.0f} mm; v0.4 {W4:.0f} x {H4:.0f} mm; A9 Pro round {A9['D']:.1f} mm.",
        f"Envelope volume (L x W x H): v0.6 {v5:.1f} cm3; v0.4 {v4:.1f} cm3; A9 Pro {va9:.1f} cm3 "
        f"(its cylinder {va9c:.1f} cm3).",
        f"Envelope volume ratio: v0.6 / v0.4 = {v5 / v4:.2f} ({(1 - v5 / v4) * 100:.0f} % less); "
        f"v0.6 / A9 Pro = {v5 / va9:.2f} (vs its cylinder {v5 / va9c:.2f}).",
    ]


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir")
    ap.add_argument("out_dir", nargs="?", default="renders")
    ap.add_argument("--v04-cad", default=None)
    a = ap.parse_args()
    cad, out, v04_cad = a.cad_dir, a.out_dir, a.v04_cad
    if v04_cad is None:
        guess = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cad")
        v04_cad = guess if os.path.exists(os.path.join(guess, "FlashKa_tray.stl")) else None
    os.makedirs(out, exist_ok=True)
    p = H.P()
    L5, W5, H5 = p.L, p.W, p.H
    (L4, W4, H4), have04 = v04_dims(v04_cad)
    if have04 and os.path.abspath(v04_cad) == os.path.abspath(cad):
        have04 = False              # same folder: not a v0.4 model
    print("v0.4 body:", "STL files from " + os.path.abspath(v04_cad) if have04 else "outline (no v0.4 STL found)",
          "%.1f x %.1f x %.1f" % (L4, W4, H4))

    def names(folder, v05):
        base = ["FlashKa_tray", "FlashKa_lid"]
        if v05:
            base.append("FlashKa_rf_window")
        base += ["_ref_usb", "_ref_s2_knob", "_ref_lidscrews"]
        pcb = "_ref_pcb_real" if os.path.exists(os.path.join(folder, "_ref_pcb_real.stl")) else "_ref_pcb"
        base.append(pcb)
        return [(folder, n) for n in base if os.path.exists(os.path.join(folder, n + ".stl"))]

    # ---- layout, mm on the figure (y up)
    FW, FH = 224.0, 250.0
    fig = plt.figure(figsize=(FW / INCH, FH / INCH), dpi=DPI)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FW)
    ax.set_ylim(0, FH)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Polygon([(0, FH), (122, FH), (114, FH - 15), (0, FH - 15)], closed=True, color=ORANGE, lw=0))
    ax.text(6, FH - 7.6, "Size comparison", fontsize=22, color="white", va="center", fontweight="bold")
    ax.text(6, FH - 22, "FlashKa Keychain v0.6 (this design)  vs  Aurora++ v0.4  vs  RovyVon Aurora A9 Pro  -  "
            "all drawn to the same scale", fontsize=9.5, color=INK, va="center")
    ytop = FH - 50.0                              # head ends line up here

    def model_pair(parts, L, W, Ht, x_top, x_side, label, label_y):
        """top view + control-side view of one light, head end at ytop"""
        box = (40.0, L + 12.0)
        xc = L / 2
        top = ortho(parts, (0, 0, -1), (-1, 0, 0), (xc, 0, Ht / 2), box)    # right = +Y
        side = ortho(parts, (0, 1, 0), (-1, 0, 0), (xc, 0, Ht / 2), box)    # right = +Z
        yimg_top = ytop + (box[1] - L) / 2
        for img, xcen in ((top, x_top), (side, x_side)):
            ax.imshow(img, extent=[xcen - box[0] / 2, xcen + box[0] / 2, yimg_top - box[1], yimg_top],
                      interpolation="lanczos", zorder=1)
        hbracket(ax, ytop + 4.0, x_top - W / 2, x_top + W / 2, fmt(W) if W >= 20 else fmt2(W))
        hbracket(ax, ytop + 4.0, x_side - Ht / 2, x_side + Ht / 2, fmt2(Ht))
        vbracket(ax, x_top - W / 2 - 4.0, ytop - L, ytop, fmt(L), side=-1)
        ax.text(x_top, ytop - L - 6.5, "top (lid)", ha="center", fontsize=9, color=DIM)
        ax.text(x_side, ytop - L - 6.5, "control side", ha="center", fontsize=9, color=DIM)
        ax.text((x_top + x_side) / 2, label_y, label, ha="center", fontsize=12.5, color=INK, fontweight="bold")

    def outline_pair(L, W, Ht, x_top, x_side, label, label_y):
        for xcen, w in ((x_top, W), (x_side, Ht)):
            ax.add_patch(FancyBboxPatch((xcen - w / 2 + 0.6, ytop - L + 0.6), w - 1.2, L - 1.2,
                                        boxstyle="round,pad=0.6", facecolor="#c9ccd1", edgecolor="#6b7078",
                                        lw=1.4, linestyle="--", zorder=2))
        hbracket(ax, ytop + 4.0, x_top - W / 2, x_top + W / 2, fmt(W))
        hbracket(ax, ytop + 4.0, x_side - Ht / 2, x_side + Ht / 2, fmt2(Ht))
        vbracket(ax, x_top - W / 2 - 4.0, ytop - L, ytop, fmt(L), side=-1)
        ax.text(x_top, ytop - L - 6.5, "top (outline)", ha="center", fontsize=9, color=DIM)
        ax.text(x_side, ytop - L - 6.5, "side (outline)", ha="center", fontsize=9, color=DIM)
        ax.text((x_top + x_side) / 2, label_y, label, ha="center", fontsize=12.5, color=INK, fontweight="bold")

    # ---- FlashKa Keychain v0.6 (this design)
    x5t = 34.0
    x5s = x5t + W5 / 2 + 12.0 + H5 / 2
    model_pair(names(cad, True), L5, W5, H5, x5t, x5s, "FlashKa Keychain v0.6", ytop - L5 - 13.0)
    # ---- Aurora++ v0.4
    x4t = x5s + H5 / 2 + 20.0 + W4 / 2
    x4s = x4t + W4 / 2 + 12.0 + H4 / 2
    if have04:
        model_pair(names(v04_cad, False), L4, W4, H4, x4t, x4s, "Aurora++ v0.4 (previous)", ytop - L4 - 13.0)
    else:
        outline_pair(L4, W4, H4, x4t, x4s, "Aurora++ v0.4 (previous)", ytop - L4 - 13.0)
    # ---- RovyVon Aurora A9 Pro: outline of the published size
    x_a9 = x4s + H4 / 2 + 20.0 + A9["D"] / 2
    ax.add_patch(FancyBboxPatch((x_a9 - A9["D"] / 2 + 1.2, ytop - A9["L"] + 1.2),
                                A9["D"] - 2.4, A9["L"] - 2.4, boxstyle="round,pad=1.2",
                                facecolor="#d6c2b3", edgecolor="#8a6a55", lw=1.4, zorder=2))
    hbracket(ax, ytop + 4.0, x_a9 - A9["D"] / 2, x_a9 + A9["D"] / 2, fmt2(A9["D"]))
    vbracket(ax, x_a9 + A9["D"] / 2 + 4.0, ytop - A9["L"], ytop, fmt(A9["L"]), side=1)
    ax.text(x_a9, ytop - A9["L"] - 6.5, "outline of the\npublished size", ha="center", va="top",
            fontsize=9, color=DIM)
    ax.text(x_a9, ytop - A9["L"] - 19.0, "RovyVon\nAurora A9 Pro", ha="center", va="top",
            fontsize=12.5, color=INK, fontweight="bold")
    # ---- coins (same scale)
    x_coin = x_a9 + A9["D"] / 2 + 26.0
    yc1 = ytop - 14.0
    ax.add_patch(Circle((x_coin, yc1), 25.75 / 2, facecolor="#cfd2d6", edgecolor="#8d9298", lw=1.2, zorder=2))
    ax.add_patch(Circle((x_coin, yc1), 18.75 / 2, facecolor="#d9b45a", edgecolor="#a8852f", lw=1.0, zorder=3))
    ax.text(x_coin, yc1 - 25.75 / 2 - 3.0, "2 euro coin\nØ25.75 mm", ha="center", va="top",
            fontsize=9, color=INK)
    yc2 = yc1 - 25.75 / 2 - 16.0 - 24.26 / 2
    ax.add_patch(Circle((x_coin, yc2), 24.26 / 2, facecolor="#d5d7da", edgecolor="#8d9298", lw=1.2, zorder=2))
    ax.add_patch(Circle((x_coin, yc2), 24.26 / 2 - 1.2, facecolor="none", edgecolor="#a3a7ad", lw=0.8, zorder=3))
    ax.text(x_coin, yc2 - 24.26 / 2 - 3.0, "US quarter\nØ24.26 mm", ha="center", va="top",
            fontsize=9, color=INK)
    right_edge = x_coin + 25.75 / 2

    # ---- table
    v5, v4 = L5 * W5 * H5 / 1000, L4 * W4 * H4 / 1000
    va9 = A9["L"] * A9["D"] ** 2 / 1000
    va9c = math.pi / 4 * A9["D"] ** 2 * A9["L"] / 1000
    m5, m4 = mass_g(cad), (mass_g(v04_cad) if have04 else None)   # no v0.4 mass from a folder that is not v0.4
    rows = [("", "FlashKa Keychain v0.6", "Aurora++ v0.4", "RovyVon Aurora A9 Pro"),
            ("Length", f"{L5:.1f} mm", f"{L4:.1f} mm", f"{A9['L']:.1f} mm"),
            ("Cross-section", f"{W5:.0f} x {H5:.0f} mm", f"{W4:.0f} x {H4:.0f} mm", f"Ø{A9['D']:.1f} mm"),
            ("Envelope volume", f"{v5:.1f} cm³", f"{v4:.1f} cm³", f"{va9:.1f} cm³  (cylinder {va9c:.1f})"),
            ("Volume vs v0.6", "1.00", f"{v4 / v5:.2f}  (v0.6 is {v5 / v4:.2f} x)",
             f"{va9 / v5:.2f}  (v0.6 is {v5 / va9:.2f} x)"),
            ("Battery", "2 x LP601646, ≈ 800 mAh", "1 x 102050, ≈ 1000 mAh", "330 mAh")]
    if m5 and m4:
        rows.append(("Tray + lid mass", f"{m5:.1f} g (6061)", f"{m4:.1f} g (6061)", "-"))
    nrow = len(rows)
    row_h = 5.0
    cols = (8.0, 52.0, 100.0, 148.0)
    y_foot = 4.0
    y_sum = y_foot + 7.0
    sums = summary_lines(L5, W5, H5, L4, W4, H4)
    y_tab_bottom = y_sum + 5.0 * 4 + 4.0                     # last table row
    for i, row in enumerate(rows):
        y = y_tab_bottom + (nrow - 1 - i) * row_h
        for j, (x, t) in enumerate(zip(cols, row)):
            ax.text(x, y, t, fontsize=9.5, color=INK, va="center",
                    fontweight="bold" if i == 0 or j == 0 else "normal")
        if i == 0:
            ax.plot([cols[0], FW - 8], [y - 2.6, y - 2.6], color=DIM, lw=0.8)
    # ---- text summary
    for k, s in enumerate(sums):
        ax.text(8, y_sum + (len(sums) - 1 - k) * 5.0, s, fontsize=8.8, color=INK, va="center",
                fontweight="normal")
    ax.text(8, y_foot, "A9 Pro data: RovyVon's size picture (2.38 x 0.61 in) and retailer listings; the A9 Pro is shown as "
            "an outline only.  Envelope volume = bounding box L x W x H (A9: D x D x L).", fontsize=7.0, color=DIM,
            va="center")
    assert right_edge < FW - 2, (right_edge, FW)
    # layout check: every text inside the figure, no two texts overlapping
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    wpx, hpx = fig.canvas.get_width_height()
    boxes = [(t.get_text().replace("\n", " / "), t.get_window_extent(rend)) for t in ax.texts]
    bad = []
    for i, (s1, b1) in enumerate(boxes):
        if b1.x0 < 0 or b1.y0 < 0 or b1.x1 > wpx or b1.y1 > hpx:
            bad.append(("outside the figure", s1))
        for s2, b2 in boxes[i + 1:]:
            if b1.overlaps(b2):
                bad.append(("overlap", s1, s2))
    print("layout check: %d texts, %d findings" % (len(boxes), len(bad)))
    for b_ in bad:
        print("   ", b_)
    path = os.path.join(out, "size_comparison_A9.png")
    fig.savefig(path, dpi=DPI, facecolor="white")
    with open(os.path.join(out, "size_comparison_summary.txt"), "w") as f:
        f.write("FlashKa Keychain v0.6 size comparison\n\n" + "\n".join(sums) + "\n")
        if m5 and m4:
            f.write(f"Housing (tray + lid, 6061, from the volumes in housing_interface.json): v0.6 {m5:.1f} g, "
                    f"v0.4 {m4:.1f} g.\n")
        f.write("A9 Pro: 60.5 x 15.5 mm (RovyVon size picture, retailer listings), shown as an outline.\n")
    print("wrote", path, "(%d x %d px)" % (int(FW / INCH * 300), int(FH / INCH * 300)))
    print("\n".join(sums))


if __name__ == "__main__":
    main()
