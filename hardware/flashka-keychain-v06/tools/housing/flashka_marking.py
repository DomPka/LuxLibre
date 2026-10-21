#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.6 - laser-marking artwork of the "fighter-jet skin" (rivets, stencils, labels).

The artwork is generated from the same parameters as the housing (class P in flashka_housing.py) and from the
panel-seam layout (skin_layout).  One drawing per flat face, 1:1, in the view of a person looking at that face:

  lid        from above,  head (X = 0) on the left,  u = X,      v = +Y
  bottom     from below,  head on the left,          u = X,      v = -Y
  minus_y    control side (USB-C) seen from -Y, head left,   u = X,      v = Z
  plus_y     laser side (S2) seen from +Y, head on the RIGHT, u = L - X, v = Z

Layers in the DXF: MARK = laser (filled letters / dots as hatches, thin lines as polylines),
REF = reference only, do not mark (face outline, groove edges, holes and openings, lid joint).

usage:  python3 flashka_marking.py <out_dir> [--png-dir DIR] [--tex-dir DIR]
        writes FlashKa_marking_*.dxf / .png + a check report (and the render textures _mark_<face>.png with --tex-dir)
"""
import json
import math
import os
import sys

import ezdxf
import numpy as np
from ezdxf import bbox as ezbbox
from ezdxf.addons import text2path
from ezdxf.fonts import fonts
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402

FACES = ("lid", "bottom", "minus_y", "plus_y")
FACE_TITLE = {"lid": "lid (seen from above, head left)", "bottom": "bottom face (seen from below, head left)",
              "minus_y": "control side -Y (USB-C), seen from -Y, head left",
              "plus_y": "laser side +Y (S2), seen from +Y, head RIGHT"}
RIVET_D = 0.45
RIVET_PITCH = 1.8
RIVET_OFF = 0.9           # rivet row distance from the seam centre line
MARK_MARGIN = 0.30        # marking edge -> groove edge
HOLE_MARGIN = 0.50        # marking edge -> hole / window / opening edge
FONT = fonts.FontFace(family="DejaVu Sans", weight=700)


# --------------------------------------------------------------------------
# face frames
# --------------------------------------------------------------------------
def to3d(p: H.P, face, u, v):
    """face coordinates -> housing (X, Y, Z) on the face surface"""
    if face == "lid":
        return (u, v, p.H)
    if face == "bottom":
        return (u, -v, 0.0)
    if face == "minus_y":
        return (u, -p.W / 2, v)
    return (p.L - u, p.W / 2, v)


def from3d(p: H.P, face, x, y, z):
    if face == "lid":
        return (x, y)
    if face == "bottom":
        return (x, -y)
    if face == "minus_y":
        return (x, z)
    return (p.L - x, z)


def flat_box(p: H.P, face):
    """usable flat part of the face (marks stay inside), face coordinates"""
    fl = p.W / 2 - p.R_edge          # 8.0: the flat top / bottom is |Y| <= 8
    if face in ("lid", "bottom"):
        return box(p.lid_x0 + 0.5, -(fl - 0.6), p.L - p.tail_facet - 0.3, fl - 0.6)
    z0, z1 = p.R_edge + 0.4, p.H - p.R_edge - 0.4        # flat side: Z 2 .. 14
    if face == "minus_y":
        return box(p.lid_x0 + 0.5, z0, p.L - p.tail_facet - 0.3, z1)
    return box(p.tail_facet + 0.3, z0, p.L - (p.lid_x0 + 0.5), z1)


def _circle(x, y, r, n=64):
    return Point(x, y).buffer(r, n)


def _stadium(xc, yc, length_y, width_x):
    """slot2D(length along Y, width along X, 90 deg) -> polygon in (x, y)"""
    r = width_x / 2
    return LineString([(xc, yc - (length_y / 2 - r)), (xc, yc + (length_y / 2 - r))]).buffer(r, 32)


def _rrect(x0, y0, x1, y1, r):
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, 16)


def openings(p: H.P, face):
    """exact outlines of holes / windows / openings visible on the face -> {name: polygon (face coords)}"""
    out = {}
    if face == "lid":
        for x in (p.screw_x_front, p.X_screw_back):
            for s in (-1, 1):
                out[f"csk {x:g}/{s:+d}"] = _circle(x, s * p.screw_dy, p.m16_csk / 2)
        x0, x1, hy = p.rfw_box
        out["RF window"] = _rrect(x0, -hy, x1, hy, p.rfw_r)
        r = p.lan_slot_w / 2 + p.lan_chamfer
        out["lanyard slot"] = _stadium(p.X_lan, 0.0, p.lan_slot_len + 2 * p.lan_chamfer, p.lan_slot_w + 2 * p.lan_chamfer)
    elif face == "bottom":
        out["main hole (tube)"] = _circle(p.X_main, -p.btn_y, p.main_hole / 2)
        for nm, x in (("next hole", p.X_next), ("previous hole", p.X_prev)):
            out[nm] = _circle(x, -p.btn_y, p.slide_hole / 2 + 0.2)
        x0, x1, hy, r = p.frw_box
        out["floor RF window"] = _rrect(x0, -hy, x1, hy, r)
        out["M2 set screw hole"] = _circle(p.las_grub_x, -p.Y_l, p.m2_tap / 2)
        # tail window (recess + 0.3 chamfer) and lanyard slot, exactly as tail_tools cuts them
        xc, k = p.X_lan, p.twin_corner
        x0t, x1t = max(xc - p.twin_x / 2, p.X_batt1 + p.twin_front_gap), xc + p.twin_x / 2
        hy = p.twin_y / 2
        win = Polygon([(x0t, -hy), (x1t - k, -hy), (x1t, -hy + k), (x1t, hy - k), (x1t - k, hy), (x0t, hy)]).buffer(0.3 + p.twin_r, 8).buffer(-p.twin_r, 8)
        out["tail window"] = win
        out["lanyard slot"] = _stadium(xc, 0.0, p.lan_slot_len + 2 * p.lan_chamfer, p.lan_slot_w + 2 * p.lan_chamfer)
    elif face == "minus_y":
        w, h, r = p.usb_open
        c = p.usb_open_chamfer
        out["USB-C opening"] = _rrect(p.X_usb - w / 2 - c, p.Z_usb - h / 2 - c, p.X_usb + w / 2 + c, p.Z_usb + h / 2 + c, r + c)
    else:
        w, h, r = p.s2_slot
        zc = p.Z_pcb_top + p.s2_knob_z
        out["S2 slot"] = _rrect(p.L - (p.X_s2 + w / 2), zc - h / 2, p.L - (p.X_s2 - w / 2), zc + h / 2, min(r, h / 2 - 1e-3))
    return out


def seams(p: H.P):
    """panel seams per face: list of dict(face, kind, a, b) in face coordinates (axis-parallel centre lines)"""
    d = p.skin_depth
    out = {f: [] for f in FACES}
    L = p.L
    # the V-ring at the lid's front edge: full height / width
    xr = p.lid_x0 - p.seam_depth
    fl = p.W / 2 - p.R_edge
    out["lid"].append(dict(kind="vring", a=(xr, -fl), b=(xr, fl)))
    out["bottom"].append(dict(kind="vring", a=(xr, -fl), b=(xr, fl)))
    out["minus_y"].append(dict(kind="vring", a=(xr, p.R_edge), b=(xr, p.H - p.R_edge)))
    out["plus_y"].append(dict(kind="vring", a=(L - xr, p.R_edge), b=(L - xr, p.H - p.R_edge)))
    pcs, tot = H._loop(p, d)
    flat = {0: "lid", 8: "lid", 2: "plus_y", 4: "bottom", 6: "minus_y"}
    for it in H.skin_layout(p):
        if it["kind"] == "frame":
            s0, s1, x = it["s0"], it["s1"], it["x"]
            for lap in (0, 1, 2):
                for k, (pc, st, ln) in enumerate(pcs):
                    if k not in flat:
                        continue
                    a, b = st + lap * tot, st + lap * tot + ln
                    lo, hi = max(a, s0), min(b, s1)
                    if hi - lo < 1e-6:
                        continue
                    pa, pb = H._loop_point(pc, lo - a, ln), H._loop_point(pc, hi - a, ln)
                    face = flat[k]
                    if face == "lid":
                        A, B = (x, pa[0]), (x, pb[0])
                    elif face == "bottom":
                        A, B = (x, -pa[0]), (x, -pb[0])
                    elif face == "minus_y":
                        A, B = (x, pa[1]), (x, pb[1])
                    else:
                        A, B = (L - x, pa[1]), (L - x, pb[1])
                    out[face].append(dict(kind="frame", a=A, b=B, name=it["name"]))
        else:
            face = it["face"]
            (ax, ay, az), (bx, by, bz) = it["a"], it["b"]
            if face == "top":
                A, B, f = (ax, ay), (bx, by), "lid"
            elif face == "bottom":
                A, B, f = (ax, -ay), (bx, -by), "bottom"
            elif face == "-Y":
                A, B, f = (ax, az), (bx, bz), "minus_y"
            else:
                A, B, f = (L - ax, az), (L - bx, bz), "plus_y"
            out[f].append(dict(kind="stringer", a=A, b=B, name=it["name"]))
    return out


def merge_lines(segs):
    """axis-parallel seam segments -> list of LineString (collinear overlapping / touching ones merged)"""
    from shapely.ops import linemerge
    ls = [LineString([s["a"], s["b"]]) for s in segs if s["a"] != s["b"]]
    if not ls:
        return []
    m = linemerge(unary_union(ls))
    return list(m.geoms) if m.geom_type == "MultiLineString" else [m]


# --------------------------------------------------------------------------
# text and glyph helpers
# --------------------------------------------------------------------------
def _hatch_polys(h):
    from ezdxf import path as ezpath
    rings = []
    for pth in h.paths:
        try:
            pp = ezpath.from_hatch_boundary_path(pth)
        except Exception:
            continue
        pts = [(v.x, v.y) for v in pp.flattening(0.01)]
        if len(pts) >= 3:
            rings.append(Polygon(pts))
    return rings


def text_geom(s, em, bold=True):
    """filled letters (shapely, baseline y = 0, left x = 0) of the string s at font size em (mm)"""
    hs = text2path.make_hatches_from_str(s, FONT, size=em, dxfattribs={"layer": "MARK"})
    polys = []
    for h in hs:
        rings = _hatch_polys(h)
        if not rings:
            continue
        g = rings[0]
        for r in rings[1:]:
            g = g.symmetric_difference(r)
        polys.append(g)
    return unary_union(polys) if polys else Polygon()


def fit_text(s, em, max_w):
    g = text_geom(s, em)
    w = g.bounds[2] - g.bounds[0]
    if w > max_w:
        em *= max_w / w
        g = text_geom(s, em)
    return g, em


def place(g, x, y, anchor="l", rot=0.0):
    """move a text geometry: its bounding box anchored at (x, y); anchor l / c / r in x, vertical centre in y"""
    x0, y0, x1, y1 = g.bounds
    ax = {"l": x0, "c": 0.5 * (x0 + x1), "r": x1}[anchor]
    g = affinity.translate(g, x - ax, y - 0.5 * (y0 + y1))
    if rot:
        g = affinity.rotate(g, rot, origin=(x, y))
    return g


def chevron(cx, cy, direction, size=1.0, w=0.28):
    """a '>' (direction +1) or '<' (-1) built from two thick strokes"""
    pts = [(-0.55 * size * direction, 0.9 * size), (0.55 * size * direction, 0.0), (-0.55 * size * direction, -0.9 * size)]
    g = LineString(pts).buffer(w / 2, cap_style=2, join_style=2)
    return affinity.translate(g, cx, cy)


def hazard_symbol(cx, cy, a):
    """ISO 7010 W004 style: triangle outline with the sunburst, as thin strokes -> (strokes, fills)"""
    tri = [(cx - a / 2, cy - a * 0.433), (cx + a / 2, cy - a * 0.433), (cx, cy + a * 0.433)]
    strokes = [tri + [tri[0]]]
    kk = 0.78
    cc = (cx, cy - a * 0.433 * (1 - kk) * 0.0)
    inner = [(cx + (x - cx) * kk, cy + (y - cy) * kk - 0.05 * a) for (x, y) in tri]
    strokes.append(inner + [inner[0]])
    sc = a / 7.0
    sx, sy = cx - 0.5 * sc, cy - 0.75 * sc
    for i in range(12):
        ang = 2 * math.pi * i / 12
        r1, r2 = 0.5 * sc, (1.1 if i % 2 else 1.6) * sc
        strokes.append([(sx + r1 * math.cos(ang), sy + r1 * math.sin(ang)), (sx + r2 * math.cos(ang), sy + r2 * math.sin(ang))])
    strokes.append([(sx, sy), (cx + 2.0 * sc, cy - 0.75 * sc)])
    return strokes


def solid_triangle(cx, cy, w, h, up=True):
    pts = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx, cy + h / 2)] if up else \
          [(cx - w / 2, cy + h / 2), (cx + w / 2, cy + h / 2), (cx, cy - h / 2)]
    return Polygon(pts)


# --------------------------------------------------------------------------
# the artwork
# --------------------------------------------------------------------------
class Art:
    def __init__(self, face):
        self.face = face
        self.fills = []      # shapely polygons (laser fills)
        self.strokes = []    # list of point lists (thin laser lines, drawn at STROKE_W)
        self.dots = []       # (x, y) rivets

    def bounds_geom(self, stroke_w=0.12):
        parts = list(self.fills) + [LineString(s).buffer(stroke_w / 2) for s in self.strokes]
        parts += [Point(x, y).buffer(RIVET_D / 2, 12) for x, y in self.dots]
        return unary_union(parts) if parts else Polygon()


STROKE_W = 0.12


def label_art(p: H.P, art: Art, laser_class, field):
    """the class 2 / 3R laser label in the field (x0, x1, y0, y1) on the lid"""
    fx0, fx1, fy0, fy1 = field
    if laser_class == "3R":
        lines = ("LASER RADIATION", "AVOID DIRECT EYE EXPOSURE", "CLASS 3R LASER PRODUCT", "520 nm  P < 5 mW  EN 60825-1:2014")
    else:
        lines = ("LASER RADIATION", "DO NOT STARE INTO BEAM", "CLASS 2 LASER PRODUCT", "520 nm  P < 1 mW  EN 60825-1:2014")
    W = fx1 - fx0
    a = 5.6
    cx, cy = fx0 + a / 2, fy1 - a * 0.433 - 0.15
    for s in hazard_symbol(cx, cy, a):
        art.strokes.append(s)
    xt = fx0 + a + 1.0
    wt = fx1 - xt
    g, e1 = fit_text("FLASHKA v0.6", 1.9, wt)
    art.fills.append(place(g, xt, fy1 - 1.05, "l"))
    g, e2 = fit_text("Li-Po 3.7 V  800 mAh", 1.2, wt)
    art.fills.append(place(g, xt, fy1 - 2.75, "l"))
    g, e3 = fit_text("LuxLibre", 1.2, wt)
    art.fills.append(place(g, xt, fy1 - 4.15, "l"))
    # warning text: lines 1-3 share one size, line 4 its own
    em_a = min(fit_text(t, 1.6, W)[1] for t in lines[:3])
    em_b = fit_text(lines[3], 1.6, W)[1]
    y = fy0 + 6.4
    for t, em, dy in ((lines[0], em_a, 0.0), (lines[1], em_a, -1.65), (lines[2], em_a, -3.3), (lines[3], em_b, -4.85)):
        g = text_geom(t, em)
        art.fills.append(place(g, fx0, y + dy, "l"))
    return dict(em_a=round(em_a, 3), em_b=round(em_b, 3))


def build_art(p: H.P, laser_class="2"):
    """-> ({face: Art}, info) : all markings without the rivets (those need the forbidden zones)"""
    arts = {f: Art(f) for f in FACES}
    fr = p.skin_frames
    A, B, C, D, E, F = fr
    info = {}
    m_in = 0.9 + RIVET_D / 2 + MARK_MARGIN          # inside a panel: rivet row + margin
    # ---- lid
    lid = arts["lid"]
    # label panel A..B
    field = (A + m_in + 0.1, B - m_in - 0.1, -6.9, 6.9)
    info["label_field"] = [round(v, 2) for v in field]
    info["label_text_em"] = label_art(p, lid, laser_class, field)
    # LASER ^ in the head panel, rotated: reads along +Y, the triangle points to the head (-X)
    xh = 0.5 * (p.lid_x0 + A) + 0.1          # panel middle (screws at X 7 sit at |Y| 6.3: text stays within |Y| < 4.3)
    em = 1.5
    while True:                                  # whole row (letters + triangle) <= 7.8 mm: screws at X 7 / |Y| 6.3 leave |Y| < 4.0
        g = text_geom("LASER", em)
        wl = g.bounds[2] - g.bounds[0]
        if wl + 1.0 + 1.2 <= 7.8 or em < 0.8:
            break
        em -= 0.05
    g = place(g, 0, 0, "c")
    tri = solid_triangle(0, 0, 1.2, 1.1, up=True)
    row = unary_union([affinity.translate(g, 0, 0), affinity.translate(tri, 0.5 * wl + 1.0 + 0.6, 0)])
    row = place(row, xh, 0.0, "c")
    row = affinity.rotate(row, 90, origin=(xh, 0.0))      # baseline along +Y, glyph "up" = -X (head)
    lid.fills.append(row)
    info["laser_stencil_em"] = round(em, 3)
    # FLASHKA-06 (panel C..D, centre strip between the lid stringers)
    ym = p.skin_stringer_y
    g, em = fit_text("FLASHKA-06", 1.7, (D - C) - 2 * m_in - 0.4)
    lid.fills.append(place(g, 0.5 * (C + D), 0.0, "c"))
    info["flashka_stencil_em"] = round(em, 3)
    # NO STEP + hatch over the cell bay (panel D..E)
    x0, x1 = D + m_in, E - m_in
    y1 = ym - 0.25 - 0.9 - RIVET_D / 2 - 0.35          # inside the stringer rivet rows
    rect = box(x0, -y1, x1, y1)
    lid.strokes.append(list(rect.exterior.coords))
    g, em = fit_text("NO STEP", 1.3, (x1 - x0) - 3.0)
    gt = place(g, 0.5 * (x0 + x1), 0.0, "c")
    clear = box(*gt.buffer(0.45).bounds)
    hatch_lines = []
    step = 0.75
    for k in range(-40, 41):
        c = 0.5 * (x0 + x1) + k * step
        ln = LineString([(c - 20, -20 + 0.0), (c + 20, 20 + 0.0)])
        hatch_lines.append(ln)
    hl = unary_union(hatch_lines).intersection(rect.buffer(-0.12)).difference(clear)
    for ls in (hl.geoms if hasattr(hl, "geoms") else [hl]):
        if not ls.is_empty and ls.length > 0.3:
            lid.strokes.append(list(ls.coords))
    lid.strokes.append(list(clear.exterior.coords))
    lid.fills.append(gt)
    info["nostep_em"] = round(em, 3)
    # serial plate (panel E..F): rounded plate, "SN" and a blank line for the number
    x0, x1 = E + m_in + 0.3, F - m_in - 0.3
    plate = _rrect(x0, -1.9, x1, 1.9, 0.5)
    lid.strokes.append(list(plate.exterior.coords))
    g, em = fit_text("SN", 1.5, 3.0)
    gs = place(g, x0 + 0.8, 0.0, "l")
    lid.fills.append(gs)
    xl0 = gs.bounds[2] + 0.7
    lid.strokes.append([(xl0, -0.75), (x1 - 0.8, -0.75)])
    info["serial_plate"] = [round(v, 2) for v in (x0, -1.9, x1, 1.9)]
    # ---- bottom: chevrons beside the slide buttons (at X_next pointing to the head, at X_prev to the tail), clear of the hole chamfers
    bot = arts["bottom"]
    for x, dirn in ((p.X_next, -1), (p.X_prev, +1)):
        bot.fills.append(chevron(x, 0.55, dirn, size=0.9, w=0.3))
    info["chevrons"] = {"next, points to the head (< in the head-left view), X": p.X_next,
                        "previous, points to the tail (> in the head-left view), X": p.X_prev, "v (view, = -Y)": 0.55}
    # ---- -Y side: big stencil in panel D..E
    my = arts["minus_y"]
    zc = 0.5 * (p.skin_stringer_z[0] + p.skin_stringer_z[1])
    g, em = fit_text("FLASHKA-06", 2.6, (E - D) - 2 * m_in)
    my.fills.append(place(g, 0.5 * (D + E), zc, "c"))
    info["side_stencil_em"] = round(em, 3)
    # ---- +Y side: SAFE (towards the head) / ARM (towards the tail) at the S2 slot, view mirrored (u = L - X)
    py = arts["plus_y"]
    w, h, r = p.s2_slot
    zs = p.Z_pcb_top + p.s2_knob_z
    xs0, xs1 = p.X_s2 - w / 2, p.X_s2 + w / 2          # slot X range
    g, em = fit_text("SAFE", 1.7, 5.0)
    wsafe = g.bounds[2] - g.bounds[0]
    py.fills.append(place(g, p.L - (xs0 - 0.9), zs, "l"))      # right of the slot in this view: x_view = L - X
    g2, em2 = fit_text("ARM", em, 5.0)
    py.fills.append(place(g2, p.L - (xs1 + 0.9), zs, "r"))
    info["s2_labels"] = {"SAFE em": round(em, 3), "ARM em": round(em2, 3), "slot X": [round(xs0, 2), round(xs1, 2)]}
    return arts, info


def forbidden(p: H.P, face, for_dots=False):
    """zones where marking must not go: groove bands, openings with margin, outside the flat"""
    d = p.skin_depth
    zones = []
    sm = merge_lines(seams(p)[face])
    for ls in sm:
        zones.append(ls.buffer(d + MARK_MARGIN, cap_style=2))
    for nm, poly in openings(p, face).items():
        zones.append(poly.buffer(HOLE_MARGIN))
    if face in ("minus_y", "plus_y"):                    # the lid joint on the flat side (Z = lid_lip_z)
        zones.append(box(-5, p.lid_lip_z - 0.5, p.L + 5, p.lid_lip_z + 0.5))
    return unary_union(zones), flat_box(p, face)


def rivets(p: H.P, face, avoid):
    """rivet rows beside every seam: pitch RIVET_PITCH, offset RIVET_OFF from the seam, culled where they
    would touch another seam, an opening or the artwork (avoid)"""
    flat = flat_box(p, face)
    d = p.skin_depth
    segs = seams(p)[face]
    zones, _ = forbidden(p, face, for_dots=True)
    dots = []
    for sg in segs:
        (ax, ay), (bx, by) = sg["a"], sg["b"]
        vertical = abs(ax - bx) < 1e-9
        ln = abs(by - ay) if vertical else abs(bx - ax)
        n = max(int(round(ln / RIVET_PITCH)), 1)
        for k in range(n + 1):
            t = k / n
            pt = (ax + (bx - ax) * t, ay + (by - ay) * t)
            for sgn in ((-1 if face == "plus_y" else 1,) if sg["kind"] == "vring" else (-1, 1)):
                q = (pt[0] + sgn * RIVET_OFF, pt[1]) if vertical else (pt[0], pt[1] + sgn * RIVET_OFF)
                dots.append(q)
    keep, seen = [], set()
    for q in dots:
        key = (round(q[0], 3), round(q[1], 3))
        if key in seen:
            continue
        seen.add(key)
        c = Point(q).buffer(RIVET_D / 2, 12)
        if not flat.contains(c):
            continue
        # distance to the seam it belongs to is RIVET_OFF; others / openings / artwork must stay clear
        if zones.intersects(c) and not _belongs_only(p, face, q):
            continue
        if avoid is not None and avoid.buffer(0.35).intersects(c):
            continue
        keep.append(q)
    return keep


def _belongs_only(p, face, q):
    """True when the dot is inside its own seam band only (never: its own band is narrower than RIVET_OFF)"""
    return False


def build_all(p: H.P, laser_class="2"):
    arts, info = build_art(p, laser_class)
    for f in FACES:
        art = arts[f]
        art.dots = rivets(p, f, unary_union([g for g in art.fills] + [LineString(s).buffer(0.1) for s in art.strokes]) if (art.fills or art.strokes) else None)
    return arts, info


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def check_art(p: H.P, arts):
    """no marking crosses a seam, a hole or the lid joint, everything on the flat; clearances in mm"""
    res = {}
    d = p.skin_depth
    for f in FACES:
        zones, flat = forbidden(p, f)
        art = arts[f]
        geoms = [("text/symbol", g) for g in art.fills] + [("line", LineString(s).buffer(STROKE_W / 2)) for s in art.strokes]
        geoms += [("rivet", Point(x, y).buffer(RIVET_D / 2, 12)) for x, y in art.dots]
        bad = [(k, [round(v, 2) for v in g.bounds]) for k, g in geoms if g.intersects(zones) or not flat.buffer(1e-6).contains(g)]
        seam_edges = unary_union([ls.buffer(d, cap_style=2) for ls in merge_lines(seams(p)[f])])
        holes = unary_union(list(openings(p, f).values())) if openings(p, f) else Polygon()
        allg = unary_union([g for _, g in geoms]) if geoms else Polygon()
        res[f] = {"marks": len(geoms), "rivets": len(art.dots), "violations": len(bad),
                  "first_violations": bad[:3],
                  "min_clearance_to_groove_mm": round(allg.distance(seam_edges), 3) if not seam_edges.is_empty else None,
                  "min_clearance_to_openings_mm": round(allg.distance(holes), 3) if not holes.is_empty else None}
    return res


# --------------------------------------------------------------------------
# outputs: DXF, PNG, textures
# --------------------------------------------------------------------------
def _ref_entities(p, face):
    """REF layer: outline of the flat face, groove edges, holes, lid joint -> list of (points, closed)"""
    out = []
    flat = flat_box(p, face)
    d = p.skin_depth
    if face in ("lid", "bottom"):
        fl = p.W / 2 - p.R_edge
        out.append(([(p.C_front, -fl), (p.L - p.C_end - p.tail_facet, -fl), (p.L - p.C_end, -fl + p.tail_facet), (p.L - p.C_end, fl - p.tail_facet),
                     (p.L - p.C_end - p.tail_facet, fl), (p.C_front, fl)], True))
    else:
        z0, z1 = p.R_edge, p.H - p.R_edge
        out.append(([(p.C_front, z0), (p.L - p.C_end, z0), (p.L - p.C_end, z1), (p.C_front, z1)], True))
        if face == "plus_y":
            out[-1] = ([(p.L - x, y) for x, y in out[-1][0]], True)
        zj = p.lid_lip_z
        a, b = (0.0, p.L)
        out.append(([(a, zj), (b, zj)], False))
    for ls in merge_lines(seams(p)[face]):
        # groove edges = centre line +/- d (flanks at the surface)
        for sgn in (-1, 1):
            x = ls.coords[0]
            y = ls.coords[-1]
            if abs(x[0] - y[0]) < 1e-9:
                out.append(([(x[0] + sgn * d, x[1]), (y[0] + sgn * d, y[1])], False))
            else:
                out.append(([(x[0], x[1] + sgn * d), (y[0], y[1] + sgn * d)], False))
    for nm, poly in openings(p, face).items():
        out.append((list(poly.exterior.coords), True))
    return out


def _add_polygon_hatch(msp, g, layer="MARK"):
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    for pg in polys:
        if pg.is_empty or pg.area < 1e-6:
            continue
        h = msp.add_hatch(color=1, dxfattribs={"layer": layer})
        h.set_solid_fill(color=1)
        h.paths.add_polyline_path(list(pg.exterior.coords)[:-1], is_closed=True)
        for r in pg.interiors:
            h.paths.add_polyline_path(list(r.coords)[:-1], is_closed=True)


def write_dxf(p: H.P, face, art: Art, path, title=""):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    doc.layers.add("MARK", color=1)
    doc.layers.add("REF", color=8)
    for pts, closed in _ref_entities(p, face):
        msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": "REF"})
    for g in art.fills:
        _add_polygon_hatch(msp, g)
    for s in art.strokes:
        msp.add_lwpolyline(s, dxfattribs={"layer": "MARK"})
    for x, y in art.dots:
        h = msp.add_hatch(color=1, dxfattribs={"layer": "MARK"})
        h.set_solid_fill(color=1)
        h.paths.add_edge_path().add_arc((x, y), RIVET_D / 2, 0, 360)
    msp.add_text(title or FACE_TITLE[face], height=1.0, dxfattribs={"layer": "REF", "insert": (0, -3.0)})
    doc.saveas(path)


def write_png(p: H.P, face, art: Art, path, ppmm=24):
    """preview: black = laser marks, grey = reference (white background), 1:1 scale grid"""
    from PIL import Image, ImageDraw, ImageFont
    x0, y0 = -2.0, (-9.0 if face in ("lid", "bottom") else -1.5)
    x1, y1 = p.L + 2.0, (9.0 if face in ("lid", "bottom") else p.H + 1.5)
    Wp, Hp = int((x1 - x0) * ppmm), int((y1 - y0) * ppmm)
    img = Image.new("RGB", (Wp, Hp + 40), (255, 255, 255))
    dr = ImageDraw.Draw(img)

    def px(pt):
        return ((pt[0] - x0) * ppmm, (y1 - pt[1]) * ppmm)

    for pts, closed in _ref_entities(p, face):
        q = [px(t) for t in pts] + ([px(pts[0])] if closed else [])
        dr.line(q, fill=(150, 150, 160), width=1)

    def fill_poly(g):
        for pg in (g.geoms if hasattr(g, "geoms") else [g]):
            if pg.is_empty:
                continue
            dr.polygon([px(t) for t in pg.exterior.coords], fill=(0, 0, 0))
            for r in pg.interiors:
                dr.polygon([px(t) for t in r.coords], fill=(255, 255, 255))
    for g in art.fills:
        fill_poly(g)
    for s in art.strokes:
        dr.line([px(t) for t in s], fill=(0, 0, 0), width=max(1, int(STROKE_W * ppmm)))
    r = RIVET_D / 2 * ppmm
    for x, y in art.dots:
        cx, cy = px((x, y))
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0))
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except Exception:
        f = None
    dr.text((8, Hp + 10), "FlashKa Keychain v0.6 - laser marking, %s, 1:1 (black = MARK layer, grey = REF layer, do not mark)" % FACE_TITLE[face], fill=(20, 20, 20), font=f)
    img.save(path)


def write_texture(p: H.P, face, art: Art, path, ppmm=40):
    """RGBA texture of the marks (transparent elsewhere) for the renders; covers u 0..L, v range of the face"""
    from PIL import Image, ImageDraw
    if face in ("lid", "bottom"):
        v0, v1 = -p.W / 2, p.W / 2
    else:
        v0, v1 = 0.0, p.H
    u0, u1 = 0.0, p.L
    Wp, Hp = int((u1 - u0) * ppmm), int((v1 - v0) * ppmm)
    img = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    def px(pt):
        return ((pt[0] - u0) * ppmm, (v1 - pt[1]) * ppmm)
    col = (236, 238, 242, 255)

    def fill_poly(g):
        for pg in (g.geoms if hasattr(g, "geoms") else [g]):
            if pg.is_empty:
                continue
            dr.polygon([px(t) for t in pg.exterior.coords], fill=col)
            for r in pg.interiors:
                dr.polygon([px(t) for t in r.coords], fill=(0, 0, 0, 0))
    for g in art.fills:
        fill_poly(g)
    for s in art.strokes:
        dr.line([px(t) for t in s], fill=col, width=max(2, int(0.16 * ppmm)), joint="curve")
    r = RIVET_D / 2 * ppmm
    for x, y in art.dots:
        cx, cy = px((x, y))
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    img.save(path)
    return (u0, u1, v0, v1)


def main(out_dir, png_dir=None, tex_dir=None):
    os.makedirs(out_dir, exist_ok=True)
    png_dir = png_dir or out_dir
    os.makedirs(png_dir, exist_ok=True)
    p = H.P()
    report = {}
    for cls in ("2", "3R"):
        arts, info = build_all(p, cls)
        chk = check_art(p, arts)
        report[f"class{cls}"] = {"info": info, "check": chk}
        for f in FACES:
            if f == "lid":
                name = f"FlashKa_marking_lid_class{cls}"
            elif cls == "2":
                name = f"FlashKa_marking_{f}"
            else:
                continue
            write_dxf(p, f, arts[f], os.path.join(out_dir, name + ".dxf"))
            write_png(p, f, arts[f], os.path.join(png_dir, name + ".png"))
        if cls == "2" and tex_dir:
            os.makedirs(tex_dir, exist_ok=True)
            for f in FACES:
                report.setdefault("texture_extent", {})[f] = write_texture(p, f, arts[f], os.path.join(tex_dir, f"_mark_{f}.png"))
    with open(os.path.join(out_dir, "flashka_marking_report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    return report


if __name__ == "__main__":
    # options take the next argument as their value; everything else is positional
    # (remove values by position, so that <out_dir> may be the same folder as --tex-dir)
    argv, args, png, tex = sys.argv[1:], [], None, None
    i = 0
    while i < len(argv):
        if argv[i] in ("--png-dir", "--tex-dir") and i + 1 < len(argv):
            if argv[i] == "--png-dir":
                png = argv[i + 1]
            else:
                tex = argv[i + 1]
            i += 2
            continue
        if not argv[i].startswith("--"):
            args.append(argv[i])
        i += 1
    rep = main(args[0] if args else "cad", png, tex)
    for cls in ("class2", "class3R"):
        print(cls, json.dumps(rep[cls]["info"]))
        for f, c in rep[cls]["check"].items():
            print("  ", f, c)
