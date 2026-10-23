#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - OPTIONAL laser warning label for the lid (EN 60825-1), artwork for laser marking.

The v0.7 light itself carries no marking: the laser label goes into the manual and onto the packaging.  A light that
is sold or given to other people needs the label on the light; this script draws it for that case only.

usage:  python3 laser_label.py [out_dir]
        default out_dir: ../../order_files/optional_laser_label (relative to this script)
        writes FlashKa_laser_label_lid_class2.dxf and .png: 1:1, the lid seen from above with the head (X = 0) on the
        left, housing coordinates (X, Y) in mm

DXF layers: MARK = laser (filled letters and symbol, as hatches); REF = reference only, not to be marked (lid
outline, flat-top edges, panels, RF window, screw countersinks, lanyard slot, label field).
The label sits in the lid panel over the main board (panel 'top PCB zone' of flashka_housing.panel_layout).
Laser data on the label: the 520 nm module of the light, Class 2 (P <= 1 mW).  LuxLibre design rule LAS-1 allows
Class 1 and Class 2 lasers only, so there is no label for a stronger class.
"""
import argparse
import math
import os
import sys

import ezdxf
from ezdxf.addons import text2path
from ezdxf.fonts import fonts
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402

FONT = fonts.FontFace(family="DejaVu Sans", weight=700)
MARGIN = 0.5            # label field inside the panel outline
TEXT = {
    "2": ("LASER RADIATION", "DO NOT STARE INTO BEAM", "CLASS 2 LASER PRODUCT", "520 nm   P \u2264 1 mW   EN 60825-1:2014"),
}


# --------------------------------------------------------------------------
# geometry helpers (shapely, mm)
# --------------------------------------------------------------------------
def _hatch_polys(h):
    from ezdxf import path as ezpath
    rings = []
    for pth in h.paths:
        try:
            pp = ezpath.from_hatch_boundary_path(pth)
        except Exception:
            continue
        pts = [(v.x, v.y) for v in pp.flattening(0.005)]
        if len(pts) >= 3:
            rings.append(Polygon(pts))
    return rings


def text_geom(s, em):
    """filled letters of s at font size em (mm), baseline y = 0, left x = 0"""
    polys = []
    for h in text2path.make_hatches_from_str(s, FONT, size=em):
        rings = _hatch_polys(h)
        if not rings:
            continue
        g = rings[0]
        for r in rings[1:]:
            g = g.symmetric_difference(r)
        polys.append(g)
    return unary_union(polys) if polys else Polygon()


def fit(s, em, max_w):
    g = text_geom(s, em)
    w = g.bounds[2] - g.bounds[0]
    if w > max_w:
        em *= max_w / w
        g = text_geom(s, em)
    return g, em


def put(g, x, y_top):
    """move g so that its bounding box starts at x and its top is at y_top"""
    x0, y0, x1, y1 = g.bounds
    return affinity.translate(g, x - x0, y_top - y1)


def hazard_symbol(cx, cy, a):
    """ISO 7010 W004 style laser warning sign as filled geometry: triangle band + sunburst + beam"""
    h = a * math.sqrt(3) / 2
    tri = Polygon([(cx - a / 2, cy - h / 3), (cx + a / 2, cy - h / 3), (cx, cy + 2 * h / 3)])
    band = tri.difference(affinity.scale(tri, 0.78, 0.78, origin=(cx, cy)))
    sc = a / 7.0
    sx, sy = cx - 0.35 * sc, cy - 0.15 * sc
    parts = [band, Point(sx, sy).buffer(0.42 * sc, 24)]
    for i in range(12):
        ang = 2 * math.pi * i / 12
        r1, r2 = 0.62 * sc, (1.15 if i % 2 else 1.55) * sc
        parts.append(LineString([(sx + r1 * math.cos(ang), sy + r1 * math.sin(ang)),
                                 (sx + r2 * math.cos(ang), sy + r2 * math.sin(ang))]).buffer(0.09 * sc, cap_style=2))
    parts.append(LineString([(sx, sy), (cx + 2.1 * sc, sy)]).buffer(0.11 * sc, cap_style=2))
    return unary_union(parts)


def rrect(x0, x1, y0, y1, r):
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, 32) if r > 0 else box(x0, y0, x1, y1)


# --------------------------------------------------------------------------
def reference(p):
    """lid outline and features (REF layer), housing (X, Y)"""
    L, W, tf = p.L, p.W, p.tail_facet
    lid = Polygon([(p.lid_x0, -W / 2), (L - tf, -W / 2), (L, -W / 2 + tf), (L, W / 2 - tf), (L - tf, W / 2),
                   (p.lid_x0, W / 2)])
    out = [list(lid.exterior.coords)]
    fl = W / 2 - p.C_edge
    out += [[(p.lid_x0, s * fl), (L - tf, s * fl)] for s in (-1, 1)]          # edges of the flat top (chamfers)
    for q in H.panel_layout(p):
        if q["face"] == "top":
            out.append(list(rrect(q["u0"], q["u1"], q["v0"], q["v1"], q["r"]).exterior.coords))
    x0, x1, hy = p.rfw_box
    out.append(list(rrect(x0, x1, -hy, hy, p.rfw_r).exterior.coords))
    for x in (p.screw_x_front, p.X_screw_back):
        for s in (-1, 1):
            out.append(list(Point(x, s * p.screw_dy).buffer(p.m16_csk / 2, 48).exterior.coords))
    hl, hw = p.lan_slot_len / 2, p.lan_slot_w / 2
    slot = LineString([(p.X_lan, -(hl - hw)), (p.X_lan, hl - hw)]).buffer(hw, 32)
    out.append(list(slot.exterior.coords))
    return out


def label(p, cls):
    """-> (filled geometry of the label, field box, info)"""
    q = {r["name"]: r for r in H.panel_layout(p)}["top PCB zone"]
    fx0, fx1 = q["u0"] + MARGIN, q["u1"] - MARGIN
    fy0, fy1 = q["v0"] + MARGIN, q["v1"] - MARGIN
    W, Hh = fx1 - fx0, fy1 - fy0
    lines = TEXT[cls]
    a = 6.0
    sym = hazard_symbol(0, 0, a)
    sym = put(sym, fx0, fy1)
    xt = sym.bounds[2] + 0.9
    g1, e1 = fit("FlashKa Keychain", 1.5, fx1 - xt)
    g2, e2 = fit("v0.7  LuxLibre", 1.25, fx1 - xt)
    top = fy1 - 0.4
    head = [put(g1, xt, top), put(g2, xt, top - 1.5 * e1 - 0.3)]
    em = min(fit(t, 1.3, W)[1] for t in lines[:3])
    gl = [text_geom(t, em) for t in lines[:3]] + [fit(lines[3], em, W)[0]]
    y = sym.bounds[1] - 0.8
    body = []
    for g in gl:
        g = put(g, fx0, y)
        body.append(g)
        y = g.bounds[1] - 0.55 * em
    art = unary_union([sym] + head + body)
    # scale the whole label down if it does not fit the field
    bx0, by0, bx1, by1 = art.bounds
    s = min(1.0, W / (bx1 - bx0), Hh / (by1 - by0))
    if s < 1.0:
        art = affinity.scale(art, s, s, origin=(fx0, fy1))
    bx0, by0, bx1, by1 = art.bounds
    art = affinity.translate(art, 0, (fy0 - by0) / 2)          # centre vertically in the field
    info = {"class": cls, "field": (fx0, fx1, fy0, fy1), "text_em_mm": round(em * s, 3), "symbol_mm": round(a * s, 2),
            "art_bbox": [round(v, 3) for v in art.bounds], "scaled": round(s, 3)}
    return art, box(fx0, fy0, fx1, fy1), info


def write_dxf(path, art, field, ref):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("MARK", color=1)
    doc.layers.add("REF", color=8)
    msp = doc.modelspace()
    for pl in ref + [list(field.exterior.coords)]:
        msp.add_lwpolyline(pl, dxfattribs={"layer": "REF"})
    geoms = list(art.geoms) if art.geom_type == "MultiPolygon" else [art]
    for g in geoms:
        h = msp.add_hatch(color=1, dxfattribs={"layer": "MARK"})
        h.paths.add_polyline_path(list(g.exterior.coords)[:-1], is_closed=True, flags=1)
        for r in g.interiors:
            h.paths.add_polyline_path(list(r.coords)[:-1], is_closed=True, flags=0)
    doc.saveas(path)


def write_png(path, art, field, ref, p, cls):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath
    fig, ax = plt.subplots(figsize=(14, 3.6), dpi=150)
    for pl in ref:
        xs, ys = zip(*pl)
        ax.plot(xs, ys, color="0.6", lw=0.6)
    xs, ys = field.exterior.xy
    ax.plot(xs, ys, color="0.75", lw=0.5, ls="--")
    geoms = list(art.geoms) if art.geom_type == "MultiPolygon" else [art]
    for g in geoms:
        verts, codes = [], []
        for ring in [g.exterior] + list(g.interiors):
            c = list(ring.coords)
            verts += c
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), facecolor="black", edgecolor="none"))
    ax.set_aspect("equal")
    ax.set_xlim(p.lid_x0 - 2, p.L + 2)
    ax.set_ylim(-p.W / 2 - 2, p.W / 2 + 2)
    ax.set_title("FlashKa Keychain v0.7 - optional lid laser label, class %s (lid from above, head left; "
                 "black = mark, grey = reference)" % cls, fontsize=9)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    fig.tight_layout()
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", nargs="?", default=os.path.join(here, "..", "..", "order_files", "optional_laser_label"))
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    p = H.P()
    ref = reference(p)
    for cls in TEXT:
        art, field, info = label(p, cls)
        base = os.path.join(a.out_dir, "FlashKa_laser_label_lid_class%s" % cls)
        write_dxf(base + ".dxf", art, field, ref)
        write_png(base + ".png", art, field, ref, p, cls)
        print(os.path.basename(base), info)


if __name__ == "__main__":
    main()
