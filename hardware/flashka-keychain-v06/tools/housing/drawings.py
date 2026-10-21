#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
2D manufacturing drawings for JLCCNC (DXF, plus PDF / PNG for people) and the
laser-marking artwork of the v0.5 housing, generated from the same parameters
(class P in flashka_housing.py) as the STEP files.

  FlashKa_tray_drawing.dxf / _sheet2.dxf   tray sheet 1 (interior, holes, threads, fits) and
                                          sheet 2 (exterior: knurl, grooves, tail, thumb dish)
  FlashKa_tray_drawing.pdf (2 pages), .png (sheet 1), _sheet2.png
  FlashKa_lid_drawing.dxf / .pdf / .png    lid: outline, RF window opening + underside pocket, screws
  FlashKa_marking_class2.dxf / _class3R.dxf (+ .png previews)   laser marking artwork, bottom face, 1:1
  drawings_dimension_table.txt            every dimension / number written on the sheets against the
                                          value in P, plus a cross-check against the solids (ray probes)

usage:  python3 drawings.py [out_dir] [housing_dir] [--quiet]   (A3 sheets, scale 2:1; housing_dir = folder with
        housing_interface.json: the min-wall numbers are compared with it).  The table of every number on the
        sheets against P and against the STEP solids is written to drawings_dimension_table.txt and printed
        (--quiet: only the summary).

The STEP files define the geometry; the drawings carry what a machinist cannot read from them:
threads and depths, critical fits with tolerances, finish, edge breaks, thin walls.
Environment: FK_CACHE=<dir> caches the (slow) HLR projections of the textured parts while the
layout is being tuned.
"""
import json
import math
import os
import pickle
import sys

import ezdxf
import numpy as np
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration, LineweightPolicy
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax2, gp_Dir, gp_Lin, gp_Pnt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402

S = 2.0                     # drawing scale 2:1
TXT = 2.5                   # text height on paper (mm)
DATE = "2026-10-16"
VER = "v0.6"
FRAME = (10.0, 10.0, 410.0, 287.0)          # inner frame of the A3 sheet
TITLE_BLOCK = (230.0, 10.0, 410.0, 46.0)
CACHE = os.environ.get("FK_CACHE")
_FONTS = {}


def text_w(s, h):
    """width of a text line on paper, measured with the font the renderer uses (OpenSans via ezdxf)"""
    from ezdxf.fonts import fonts
    f = _FONTS.get(h)
    if f is None:
        f = _FONTS[h] = fonts.make_font("OpenSans-Regular.ttf", h, 1.0)
    return f.text_width(s)


def wrap(s, width, h):
    """word-wrap s to a paper width, continuation lines indented by three spaces"""
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w) if cur else w
        if text_w(t, h) > width and cur:
            lines.append(cur)
            cur = "   " + w
        else:
            cur = t
    lines.append(cur)
    return lines


# --------------------------------------------------------------------------
# registry of everything that is written on the sheets
# --------------------------------------------------------------------------
ROWS = []        # dimensions and numbers: sheet, view, what, shown, expression, P value
PROBES = []      # cross-check against the solids: what, drawing / P value, measured, ok


def reg(sheet, view, what, shown, expr, pval):
    ROWS.append(dict(sheet=sheet, view=view, what=what, shown=shown, expr=expr, pval=pval,
                     ok=abs(shown - pval) <= 6e-4))


def num(x, dec=3, min_dec=0):
    """number as printed on the drawing (trailing zeros dropped, at least min_dec decimals kept)"""
    s = f"{x:.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    if min_dec and "." not in s:
        s += "." + "0" * min_dec
    elif min_dec and len(s.split(".")[1]) < min_dec:
        s += "0" * (min_dec - len(s.split(".")[1]))
    return s


TW_X0_EXPR = "max(X_lan-twin_x/2,X_batt1+twin_front_gap)"


def tail_window_x(p):
    """X range of the recessed tail window exactly as flashka_housing.build_tray cuts it: the front
    edge is kept twin_front_gap behind the bay end, so the window can be shorter than twin_x."""
    x0 = max(p.X_lan - p.twin_x / 2, p.X_batt1 + getattr(p, "twin_front_gap", 0.0))
    return x0, p.X_lan + p.twin_x / 2


# --------------------------------------------------------------------------
# projection / section helpers
# --------------------------------------------------------------------------
def hlr(shape, normal, xdir, cache_key=None):
    """hidden-line removal: polylines (x, y) in the view plane, by class vis/smooth/outl/hid"""
    path = None
    if CACHE and cache_key:
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, cache_key + ".pkl")
        if os.path.exists(path):
            return pickle.load(open(path, "rb"))
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*normal), gp_Dir(*xdir))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    out = {}
    for name, comp in (("vis", h.VCompound()), ("smooth", h.Rg1LineVCompound()),
                       ("outl", h.OutLineVCompound()), ("hid", h.HCompound())):
        polys = []
        if comp is not None and not comp.IsNull():
            ex = TopExp_Explorer(comp, TopAbs_EDGE)
            while ex.More():
                e = TopoDS.Edge_s(ex.Current())
                c = BRepAdaptor_Curve(e)
                d = GCPnts_QuasiUniformDeflection(c, 0.005)
                polys.append([(d.Value(i).X(), d.Value(i).Y()) for i in range(1, d.NbPoints() + 1)])
                ex.Next()
        out[name] = polys
    if path:
        pickle.dump(out, open(path, "wb"))
    return out


def clip_polys(polys, u0=-1e9, u1=1e9, v0=-1e9, v1=1e9):
    """clip polylines to the window [u0,u1] x [v0,v1] (Liang-Barsky per segment)"""
    out = []
    for pl in polys:
        cur = []
        for (xa, ya), (xb, yb) in zip(pl, pl[1:]):
            dx, dy = xb - xa, yb - ya
            t0, t1, ok = 0.0, 1.0, True
            for pp, qq in ((-dx, xa - u0), (dx, u1 - xa), (-dy, ya - v0), (dy, v1 - ya)):
                if abs(pp) < 1e-12:
                    if qq < 0:
                        ok = False
                        break
                else:
                    r = qq / pp
                    if pp < 0:
                        t0 = max(t0, r)
                    else:
                        t1 = min(t1, r)
                    if t0 > t1:
                        ok = False
                        break
            if not ok:
                if len(cur) >= 2:
                    out.append(cur)
                cur = []
                continue
            a = (xa + t0 * dx, ya + t0 * dy)
            b = (xa + t1 * dx, ya + t1 * dy)
            if cur and math.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) < 1e-9:
                cur.append(b)
            else:
                if len(cur) >= 2:
                    out.append(cur)
                cur = [a, b]
            if t1 < 1.0:
                out.append(cur)
                cur = []
        if len(cur) >= 2:
            out.append(cur)
    return out


def clip_view(polys, **kw):
    return {k: clip_polys(v, **kw) for k, v in polys.items()}


def wire_points(wire, defl=0.01):
    """ordered 3D points of a closed wire"""
    ex = BRepTools_WireExplorer(wire.wrapped)
    pts = []
    while ex.More():
        e = ex.Current()
        c = BRepAdaptor_Curve(e)
        d = GCPnts_QuasiUniformDeflection(c, defl)
        seg = [(d.Value(i).X(), d.Value(i).Y(), d.Value(i).Z()) for i in range(1, d.NbPoints() + 1)]
        if ex.Orientation() == TopAbs_REVERSED:
            seg.reverse()
        if pts and np.allclose(pts[-1], seg[0], atol=1e-6):
            seg = seg[1:]
        pts += seg
        ex.Next()
    return pts


def cut_loops(solid, axis, pos, uv):
    """closed loops of the planar faces of `solid` that lie in the plane axis = pos, mapped by uv(x,y,z)"""
    loops = []
    shape = solid.val() if isinstance(solid, H.cq.Workplane) else solid
    for f in shape.Faces():
        c, n = f.Center(), f.normalAt()
        comp = {"x": (c.x, n.x), "y": (c.y, n.y), "z": (c.z, n.z)}[axis]
        if abs(comp[0] - pos) < 1e-5 and abs(comp[1]) > 0.999:
            for w in [f.outerWire()] + list(f.innerWires()):
                loops.append([uv(*q) for q in wire_points(w)])
    return loops


def hatch_segments(loops, spacing, ang=45.0):
    """even-odd hatch lines through the loops at `ang` degrees -> [((u0,v0),(u1,v1))]"""
    a = math.radians(ang)
    d = np.array([math.cos(a), math.sin(a)])
    nrm = np.array([-d[1], d[0]])
    allp = np.vstack([np.asarray(lp) for lp in loops])
    cs = allp @ nrm
    P0 = np.vstack([np.asarray(lp) for lp in loops])
    P1 = np.vstack([np.roll(np.asarray(lp), -1, axis=0) for lp in loops])
    f0, f1 = P0 @ nrm, P1 @ nrm
    segs = []
    c = math.floor(cs.min() / spacing) * spacing + spacing * 0.5 + 1e-7
    while c < cs.max():
        s0, s1 = f0 - c, f1 - c
        m = (s0 * s1) < 0
        if m.any():
            t = s0[m] / (s0[m] - s1[m])
            pts = P0[m] + (P1[m] - P0[m]) * t[:, None]
            along = np.sort(pts @ d)
            for i in range(0, len(along) - 1, 2):
                segs.append((tuple(along[i] * d + c * nrm), tuple(along[i + 1] * d + c * nrm)))
        c += spacing
    return segs


class Rays:
    """ray probes into an OCC solid: solid intervals along a line (cross-check of the drawing values).
    Rays start 10 mm outside the part; hits closer than 1e-5 (edge hits) count once."""

    def __init__(self, shape):
        self.it = IntCurvesFace_ShapeIntersector()
        self.it.Load(shape.wrapped if hasattr(shape, "wrapped") else shape, 1e-6)

    def iv(self, o, d, t0=-10.0, tmax=400.0):
        """solid intervals along the line o + t*d, reported as coordinates (t - 10 offsets removed by the
        callers); o is the point at coordinate 0 of the swept axis"""
        org = (o[0] + d[0] * t0, o[1] + d[1] * t0, o[2] + d[2] * t0)
        self.it.Perform(gp_Lin(gp_Pnt(*org), gp_Dir(*d)), 0.0, tmax)
        ts = sorted(self.it.WParameter(i) + t0 for i in range(1, self.it.NbPnt() + 1))
        m = []
        for t in ts:
            if m and abs(t - m[-1]) < 1e-5:
                continue
            m.append(t)
        return [(m[i], m[i + 1]) for i in range(0, len(m) - 1, 2)]

    def z(self, x, y):
        return [(round(a, 3), round(b, 3)) for a, b in self.iv((x, y, 0.0), (0, 0, 1))]

    def x(self, y, z):
        return [(round(a, 3), round(b, 3)) for a, b in self.iv((0.0, y, z), (1, 0, 0))]

    def y(self, x, z):
        return [(round(a, 3), round(b, 3)) for a, b in self.iv((x, 0.0, z), (0, 1, 0), t0=-30.0)]


def probe(what, drawn, measured, tol=0.02):
    PROBES.append(dict(what=what, drawn=drawn, measured=measured, ok=abs(drawn - measured) <= tol))


# --------------------------------------------------------------------------
class Sheet:
    def __init__(self, title, partno, sheet="1/1", size=(420, 297)):
        self.doc = ezdxf.new("R2010", setup=True)
        self.doc.units = ezdxf.units.MM
        self.msp = self.doc.modelspace()
        L = self.doc.layers
        L.add("VISIBLE", color=7, lineweight=35)
        L.add("HIDDEN", color=8, linetype="DASHED", lineweight=18)
        L.add("CENTER", color=1, linetype="CENTER", lineweight=13)
        L.add("CUTLINE", color=1, linetype="DASHDOT", lineweight=25)
        L.add("DIM", color=5, lineweight=13)
        L.add("TEXT", color=7, lineweight=18)
        L.add("BORDER", color=7, lineweight=50)
        L.add("NOTE", color=1, lineweight=18)
        L.add("PHANTOM", color=1, linetype="DASHED", lineweight=18)
        L.add("HATCH", color=8, lineweight=9)
        L.add("TABLE", color=7, lineweight=18)
        self._dimstyle(S)
        self.size = size
        self.title = title
        self.partno = partno
        self.sheet = sheet
        self.name = f"{partno.split()[0]} {sheet}"
        self.cur = ""                       # current view name (registry)
        self.texts = []                     # (x0, y0, x1, y1, string, own) text boxes on paper
        self.segs = []                      # visible model geometry, paper segments
        self.dimsegs = []                   # dimension / leader line segments (owner, x0, y0, x1, y1)
        self.vboxes = {}                    # view name -> paper bbox of the visible geometry
        self.vscale = {}                    # view name -> drawing scale of that view
        self._own = 0
        self.border()

    def _dimstyle(self, scale):
        """dimension style for views drawn at `scale`:1 (dimlfac turns paper mm back into model mm)"""
        name = "FK" if scale == S else "FK%g" % scale
        if name not in self.doc.dimstyles:
            ds = self.doc.dimstyles.new(name)
            ds.dxf.dimtxt = TXT
            ds.dxf.dimasz = 2.0
            ds.dxf.dimlfac = 1.0 / scale
            ds.dxf.dimdec = 3
            ds.dxf.dimzin = 8          # suppress trailing zeros
            ds.dxf.dimdsep = 46        # decimal point
            ds.dxf.dimexe = 1.0
            ds.dxf.dimexo = 0.8
            ds.dxf.dimgap = 0.6
            ds.dxf.dimtad = 1
            ds.dxf.dimclrd = 5
            ds.dxf.dimclre = 5
            ds.dxf.dimclrt = 7
            ds.dxf.dimtih = 0
            ds.dxf.dimtoh = 0
        return name

    @property
    def sc(self):
        return self.vscale.get(self.cur, S)

    # ---- frame and title block
    def border(self):
        w, h = self.size
        m = self.msp
        m.add_point((0, 0), dxfattribs={"layer": "BORDER"})
        m.add_point((w, h), dxfattribs={"layer": "BORDER"})
        m.add_lwpolyline([(10, 10), (w - 10, 10), (w - 10, h - 10), (10, h - 10)], close=True,
                         dxfattribs={"layer": "BORDER"})
        x0, y0 = w - 190, 10
        m.add_lwpolyline([(x0, y0), (w - 10, y0), (w - 10, y0 + 36), (x0, y0 + 36)], close=True,
                         dxfattribs={"layer": "BORDER"})
        for yy in (y0 + 12, y0 + 24):
            m.add_line((x0, yy), (w - 10, yy), dxfattribs={"layer": "BORDER"})
        m.add_line((x0 + 110, y0), (x0 + 110, y0 + 24), dxfattribs={"layer": "BORDER"})
        self.text(self.title, x0 + 3, y0 + 28, 4.0, track=False)
        self.text(f"Part: {self.partno}", x0 + 3, y0 + 16, 3.0, track=False)
        self.text(f"FlashKa Keychain {VER}  {DATE}", x0 + 3, y0 + 4, 2.5, track=False)
        self.text(f"SCALE 2:1 (details as marked)   SHEET {self.sheet}", x0 + 113, y0 + 16, 2.2, track=False)
        self.text("Units mm  |  ISO 2768-mK", x0 + 113, y0 + 4, 2.5, track=False)

    # ---- text
    def _box(self, s, x, y, h, rot):
        w = text_w(s, h)
        return (x - 1.05 * h, y, x + 0.25 * h, y + w) if rot == 90 else (x, y - 0.25 * h, x + w, y + 1.05 * h)

    def text(self, s, x, y, h=TXT, layer="TEXT", rot=0.0, track=True, align="left"):
        w = text_w(s, h)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        t = self.msp.add_text(s, height=h, dxfattribs={"layer": layer, "style": "OpenSans",
                                                      "rotation": rot})
        t.set_placement((x, y))
        if track:
            self.texts.append(self._box(s, x, y, h, rot) + (s, 0))
        return t

    def mtext(self, lines, x, y, h=2.4, gap=1.6, layer="TEXT"):
        for i, ln in enumerate(lines):
            self.text(ln, x, y - i * (h + gap), h, layer)

    # ---- views
    def view(self, polys, ox, oy, name, hidden=True, flipx=False, hidden_layer="HIDDEN", scale=None):
        m = self.msp
        sc = scale or S
        self.vscale[name] = sc
        xs, ys = [], []
        for key, layer in (("vis", "VISIBLE"), ("outl", "VISIBLE"), ("smooth", "VISIBLE"),
                           ("hid", hidden_layer)):
            if key == "hid" and not hidden:
                continue
            for pl in polys.get(key, []):
                pts = [(ox + sc * (-x if flipx else x), oy + sc * y) for (x, y) in pl]
                if len(pts) >= 2:
                    m.add_lwpolyline(pts, dxfattribs={"layer": layer})
                    if key != "hid":
                        xs += [q[0] for q in pts]
                        ys += [q[1] for q in pts]
                        self.segs += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
        bb = (min(xs), min(ys), max(xs), max(ys)) if xs else None
        self.vboxes[name] = bb
        self.cur = name
        return bb

    def hatch(self, segs, ox, oy, flipx=False):
        sc = self.sc
        for (a, b) in segs:
            pa = (ox + sc * (-a[0] if flipx else a[0]), oy + sc * a[1])
            pb = (ox + sc * (-b[0] if flipx else b[0]), oy + sc * b[1])
            self.msp.add_line(pa, pb, dxfattribs={"layer": "HATCH"})

    def P(self, ox, oy, x, y):
        sc = self.sc
        return (ox + sc * x, oy + sc * y)

    def line(self, a, b, layer="DIM"):
        self.msp.add_line(a, b, dxfattribs={"layer": layer})

    def title_of(self, name, x, y, h=3.0):
        self.text(name, x, y, h)

    # ---- dimensions
    def _dim_log(self, d, shown, text, rot):
        self._own += 1
        for e in d.dimension.virtual_entities():
            if e.dxftype() == "LINE":
                a, b = e.dxf.start, e.dxf.end
                self.dimsegs.append((self._own, a.x, a.y, b.x, b.y))
        mp = d.dimension.dxf.get("text_midpoint")
        label = text.replace("<>", num(shown)).replace("%%c", "\u00d8")
        w, h = text_w(label, TXT), TXT
        if rot:
            w, h = h, w
        self.texts.append((mp[0] - w / 2, mp[1] - h / 2, mp[0] + w / 2, mp[1] + h / 2, label, self._own))

    def hdim(self, ox, oy, x1, y1, x2, y2, base_y, what, expr, pval, text="<>", shift=None):
        kw = {}
        if shift is not None:       # text moved along the dimension line (paper mm), no leader
            kw["location"] = (ox + self.sc * (x1 + x2) / 2 + shift, oy + self.sc * base_y + 2.85)
        d = self.msp.add_linear_dim(base=self.P(ox, oy, 0, base_y), p1=self.P(ox, oy, x1, y1),
                                    p2=self.P(ox, oy, x2, y2), angle=0, dimstyle=self._dimstyle(self.sc), text=text,
                                    dxfattribs={"layer": "DIM"}, **kw)
        d.render()
        shown = round(abs(x2 - x1), 4)
        reg(self.name, self.cur, what, shown, expr, pval)
        self._dim_log(d, shown, text, False)

    def vdim(self, ox, oy, x1, y1, x2, y2, base_x, what, expr, pval, text="<>", shift=None):
        kw = {}
        if shift is not None:
            kw["location"] = (ox + self.sc * base_x - 2.85, oy + self.sc * (y1 + y2) / 2 + shift)
        d = self.msp.add_linear_dim(base=self.P(ox, oy, base_x, 0), p1=self.P(ox, oy, x1, y1),
                                    p2=self.P(ox, oy, x2, y2), angle=90, dimstyle=self._dimstyle(self.sc), text=text,
                                    dxfattribs={"layer": "DIM"}, **kw)
        d.render()
        shown = round(abs(y2 - y1), 4)
        reg(self.name, self.cur, what, shown, expr, pval)
        self._dim_log(d, shown, text, True)

    def leader(self, ox, oy, x, y, dx, dy, lines, h=2.4, paper=False):
        """arrow at the model point (x, y), text lines at paper offset (dx, dy)"""
        p0 = (x, y) if paper else self.P(ox, oy, x, y)
        p1 = (p0[0] + dx, p0[1] + dy)
        a = math.atan2(p0[1] - p1[1], p0[0] - p1[0])
        self.msp.add_line(p0, p1, dxfattribs={"layer": "DIM"})
        self._own += 1
        self.dimsegs.append((self._own, p0[0], p0[1], p1[0], p1[1]))
        for s in (-1, 1):
            self.msp.add_line(p0, (p0[0] - 1.8 * math.cos(a + s * 0.3), p0[1] - 1.8 * math.sin(a + s * 0.3)),
                              dxfattribs={"layer": "DIM"})
        if isinstance(lines, str):
            lines = lines.split("\n")
        right = dx >= 0
        for i, ln in enumerate(lines):
            tx = p1[0] + 1.0 if right else p1[0] - 1.0 - text_w(ln, h)
            ty = p1[1] + 0.6 - i * (h + 1.2)
            self.text(ln, tx, ty, h)

    def tag(self, ox, oy, x, y, dx, dy, ident, r=2.6):
        """numbered balloon (feature table ID) with a leader to the model point"""
        p0 = self.P(ox, oy, x, y)
        c = (p0[0] + dx, p0[1] + dy)
        L = math.hypot(dx, dy)
        q = (c[0] - dx / L * r, c[1] - dy / L * r)
        self.msp.add_line(p0, q, dxfattribs={"layer": "DIM"})
        self.msp.add_circle(c, r, dxfattribs={"layer": "DIM"})
        self.msp.add_circle(p0, 0.35, dxfattribs={"layer": "DIM"})
        self._own += 1
        self.dimsegs.append((self._own, p0[0], p0[1], q[0], q[1]))
        s = str(ident)
        self.text(s, c[0], c[1] - 1.0, 2.6, align="center", track=False)
        self.texts.append((c[0] - r, c[1] - r, c[0] + r, c[1] + r, "(" + s + ")", self._own))

    def frame(self, ox, oy, u0, u1, v0, v1, layer="HATCH"):
        """thin window frame round a partial (detail) view"""
        pts = [self.P(ox, oy, u0, v0), self.P(ox, oy, u1, v0), self.P(ox, oy, u1, v1), self.P(ox, oy, u0, v1)]
        self.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
        self.segs += [(q[0], q[1], r[0], r[1]) for q, r in zip(pts, pts[1:] + pts[:1])]

    def center(self, ox, oy, x, y, r):
        for (a, b) in (((x - r - 1, y), (x + r + 1, y)), ((x, y - r - 1), (x, y + r + 1))):
            self.msp.add_line(self.P(ox, oy, *a), self.P(ox, oy, *b), dxfattribs={"layer": "CENTER"})

    def cutline(self, ox, oy, p1, p2, letter, look, ext=1.5, shaft=4.0, h=3.2):
        """cutting-plane line p1 -> p2 (model coords) with arrows pointing along `look` (unit vector on
        paper) and the section letter beyond each arrow"""
        a, b = self.P(ox, oy, *p1), self.P(ox, oy, *p2)
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        a2, b2 = (a[0] - ux * ext, a[1] - uy * ext), (b[0] + ux * ext, b[1] + uy * ext)
        self.msp.add_line(a2, b2, dxfattribs={"layer": "CUTLINE"})
        self._own += 1
        self.dimsegs.append((self._own, a2[0], a2[1], b2[0], b2[1]))
        lx, ly = look
        for e in (a2, b2):
            tip = (e[0] + lx * shaft, e[1] + ly * shaft)
            self.msp.add_line(e, tip, dxfattribs={"layer": "CUTLINE"})
            self.dimsegs.append((self._own, e[0], e[1], tip[0], tip[1]))
            for sg in (-1, 1):
                self.msp.add_line(tip, (tip[0] - lx * 2.0 - sg * ly * 0.8, tip[1] - ly * 2.0 + sg * lx * 0.8),
                                  dxfattribs={"layer": "CUTLINE"})
            cx, cy = tip[0] + lx * (h * 0.6 + 0.8), tip[1] + ly * (h * 0.6 + 0.8)
            self.text(letter, cx, cy - 0.37 * h, h, align="center")

    def breakline(self, ox, oy, x, y0, y1):
        """zig-zag break symbol at model x between y0 and y1"""
        p0, p1 = self.P(ox, oy, x, y0), self.P(ox, oy, x, y1)
        n = 6
        pts = [(p0[0], p0[1] - 1.5)]
        for i in range(n + 1):
            t = i / n
            pts.append((p0[0] + (1.6 if i % 2 else -1.6), p0[1] - 1.5 + t * (p1[1] - p0[1] + 3.0)))
        self.msp.add_lwpolyline(pts, dxfattribs={"layer": "VISIBLE"})
        self.segs += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]

    # ---- table
    def table(self, x0, y_top, cols, rows, head, h=2.0, pad=1.2, line=2.9):
        """feature table; rows = list of lists of cell strings (\\n separates lines); returns bottom y.
        Cell text wider than its column is reported."""
        xs = [x0]
        for w in cols:
            xs.append(xs[-1] + w)
        y = y_top
        allrows = [head] + rows
        for k, cells in enumerate(allrows):
            nl = max(c.count("\n") + 1 for c in cells)
            rh = nl * line + 2 * pad - 0.6
            for j, c in enumerate(cells):
                for i, ln in enumerate(c.split("\n")):
                    if text_w(ln, h) > cols[j] - 1.6:
                        print(f"  WARNING table cell too wide: '{ln}' ({text_w(ln, h):.1f} > {cols[j] - 1.6:.1f})")
                    self.text(ln, xs[j] + 0.9, y - pad - (i + 1) * line + 1.1, h,
                              layer="TEXT")
            self.msp.add_line((xs[0], y - rh), (xs[-1], y - rh), dxfattribs={"layer": "TABLE"})
            if k == 0:
                self.msp.add_line((xs[0], y), (xs[-1], y), dxfattribs={"layer": "TABLE"})
            y -= rh
        for xx in xs:
            self.msp.add_line((xx, y_top), (xx, y), dxfattribs={"layer": "TABLE"})
        return y

    # ---- layout check
    def check(self):
        """text vs text, text vs frame / title block, text vs model geometry and vs dimension lines,
        view boxes vs each other; prints every hit"""
        bad = 0
        T = self.texts
        fx0, fy0, fx1, fy1 = FRAME
        tx0, ty0, tx1, ty1 = TITLE_BLOCK

        def hit(a, b, pad=0.2):
            return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])
        for i, a in enumerate(T):
            if a[0] < fx0 + 0.5 or a[1] < fy0 + 0.5 or a[2] > fx1 - 0.5 or a[3] > fy1 - 0.5:
                print(f"  [{self.name}] text outside frame: '{a[4]}'")
                bad += 1
            if hit(a, (tx0, ty0, tx1, ty1), 0.0):
                print(f"  [{self.name}] text inside the title block: '{a[4]}'")
                bad += 1
            for b in T[i + 1:]:
                if hit(a, b):
                    print(f"  [{self.name}] texts overlap: '{a[4]}'  /  '{b[4]}'")
                    bad += 1
        # text box vs line segments (shrunk by 0.35 so that leaders touching their text do not count)
        def seg_hits(box, seg):
            x0, y0, x1, y1 = box
            sx0, sy0, sx1, sy1 = seg
            if max(sx0, sx1) < x0 or min(sx0, sx1) > x1 or max(sy0, sy1) < y0 or min(sy0, sy1) > y1:
                return False
            if x0 <= sx0 <= x1 and y0 <= sy0 <= y1:
                return True
            if x0 <= sx1 <= x1 and y0 <= sy1 <= y1:
                return True
            for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
                d1 = (sx1 - sx0) * (ay - sy0) - (sy1 - sy0) * (ax - sx0)
                d2 = (sx1 - sx0) * (by - sy0) - (sy1 - sy0) * (bx - sx0)
                d3 = (bx - ax) * (sy0 - ay) - (by - ay) * (sx0 - ax)
                d4 = (bx - ax) * (sy1 - ay) - (by - ay) * (sx1 - ax)
                if d1 * d2 < 0 and d3 * d4 < 0:
                    return True
            return False
        for a in T:
            box = (a[0] + 0.35, a[1] + 0.35, a[2] - 0.35, a[3] - 0.35)
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            hits = [sg for sg in self.segs if seg_hits(box, sg)]
            if hits:
                print(f"  [{self.name}] text over model lines ({len(hits)} segments, e.g. "
                      f"({hits[0][0]:.1f},{hits[0][1]:.1f})-({hits[0][2]:.1f},{hits[0][3]:.1f})): '{a[4]}'")
                bad += 1
            hits = [sg for sg in self.dimsegs if sg[0] != a[5] and seg_hits(box, sg[1:])]
            if hits:
                print(f"  [{self.name}] text crossed by {len(hits)} dimension / leader lines (e.g. "
                      f"({hits[0][1]:.1f},{hits[0][2]:.1f})-({hits[0][3]:.1f},{hits[0][4]:.1f})): '{a[4]}'")
                bad += 1
        names = list(self.vboxes)
        for i, na in enumerate(names):
            for nb in names[i + 1:]:
                A, B = self.vboxes[na], self.vboxes[nb]
                if A and B and hit(A, B, 0.0):
                    print(f"  [{self.name}] views collide: {na} / {nb}")
                    bad += 1
        for n, bb in self.vboxes.items():
            if bb and (bb[0] < fx0 or bb[1] < fy0 or bb[2] > fx1 or bb[3] > fy1):
                print(f"  [{self.name}] view outside the frame: {n}")
                bad += 1
        print(f"  [{self.name}] layout check: {bad} finding(s)")
        return bad

    def save(self, path_dxf, path_pdf=None):
        self.doc.saveas(path_dxf)
        if path_pdf is None:
            path_pdf = path_dxf.replace(".dxf", ".pdf")
        from ezdxf.addons.drawing import layout, pymupdf
        ctx = RenderContext(self.doc)
        backend = pymupdf.PyMuPdfBackend()
        cfg = Configuration(lineweight_policy=LineweightPolicy.ABSOLUTE,
                            background_policy=ezdxf.addons.drawing.config.BackgroundPolicy.WHITE,
                            color_policy=ezdxf.addons.drawing.config.ColorPolicy.COLOR)
        Frontend(ctx, backend, config=cfg).draw_layout(self.msp, finalize=True)
        page = layout.Page(self.size[0], self.size[1], layout.Units.mm, margins=layout.Margins.all(0))
        settings = layout.Settings(fit_page=False, scale=1.0)
        with open(path_pdf, "wb") as fp:
            fp.write(backend.get_pdf_bytes(page, settings=settings))
        return path_pdf


def png_from_pdf(path_pdf, page=0, path_png=None, dpi=110):
    import fitz   # PyMuPDF: rasterise the finished PDF page (keeps the sheet frame)
    with fitz.open(path_pdf) as d:
        d[page].get_pixmap(dpi=dpi).save(path_png or path_pdf.replace(".pdf", ".png"))


def merge_pdfs(paths, out):
    import fitz
    doc = fitz.open()
    for pth in paths:
        with fitz.open(pth) as d:
            doc.insert_pdf(d)
    doc.save(out)
    doc.close()


# --------------------------------------------------------------------------
def head_view_data(p):
    """derived numbers used on several sheets"""
    rb = (p.win_d + p.bore_clear) / 2
    return dict(rb=rb, rl=(p.las_d + p.las_clear) / 2, trough=2 * (p.inner_half - p.ledge_w),
                x_trough_end=p.X_pcb1 + 0.5, m2_wall=p.Z_las - (p.las_d + p.las_clear) / 2)


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------
def loops_to_polys(loops):
    return {"vis": [lp + [lp[0]] for lp in loops]}


def section_long(wp, p, y, label, spacing=0.8):
    """longitudinal section at Y = y seen from -Y (the part with Y >= y is kept): HLR of the half
    (cut outline + what lies behind), hatch from the cut faces of a thin slab"""
    half = wp.intersect(H.rbox(-1, p.L + 1, y, 30, -1, 30))
    slab = wp.intersect(H.rbox(-1, p.L + 1, y, y + 0.3, -1, 30))
    polys = hlr(half.val().wrapped, (0, -1, 0), (1, 0, 0))
    loops = cut_loops(slab, "y", y, lambda a, b, c: (a, c))
    return polys, hatch_segments(loops, spacing), loops


def section_trans(wp, p, x, label, spacing=0.8):
    """transverse section at X = x seen from +X (the part with X <= x is kept); only the cut face"""
    half = wp.intersect(H.rbox(-1, x, -30, 30, -1, 30))
    loops = cut_loops(half, "x", x, lambda a, b, c: (b, c))
    return loops_to_polys(loops), hatch_segments(loops, spacing), loops


def clip_segs(segs, u0=-1e9, u1=1e9, v0=-1e9, v1=1e9):
    out = []
    for pl in clip_polys([[a, b] for a, b in segs], u0, u1, v0, v1):
        out.append((pl[0], pl[-1]))
    return out


def thread_symbol(sh, ox, oy, x, y, d_major):
    """plan view of an internal thread: 3/4 circle on the major diameter"""
    c = sh.P(ox, oy, x, y)
    sh.msp.add_arc(c, sh.sc * d_major / 2, 0, 270, dxfattribs={"layer": "HATCH"})




_WALLS = {}


def thin_walls(p, housing_dir=None):
    """min-wall numbers of the STEP (min_wall_report + texture_walls) - from housing_interface.json when
    available, else computed; both are compared"""
    if housing_dir in _WALLS:
        return _WALLS[housing_dir]
    _WALLS[housing_dir] = _thin_walls(p, housing_dir)
    return _WALLS[housing_dir]


def _thin_walls(p, housing_dir):
    comp = H.min_wall_report(p)
    js = None
    if housing_dir:
        try:
            js = json.load(open(os.path.join(housing_dir, "housing_interface.json")))
        except OSError:
            js = None
    if js and js.get("min_walls"):
        for k, v in js["min_walls"].items():
            if abs(comp.get(k, v) - v) > 2e-3:
                print("  note: min wall '%s' differs: json %.3f, recomputed %.3f" % (k, v, comp[k]))
    return comp, ((js or {}).get("skin_walls") or [])


def make_V(nm):
    def V(what, val, expr, pval=None, dec=3, view="table", md=0):
        """a number written into a note, table or callout: registered against its P expression"""
        s_ = num(val, dec, md)
        reg(nm, view, what, float(s_), expr, val if pval is None else pval)
        return s_
    return V


def tray_sheet1(p, out, housing_dir=None):
    """Sheet 1: interior, holes, threads, critical fits (the tray without the knurl: its hidden
    edges would bury the drawing; the exterior texture is on sheet 2)."""
    wp = H.build_tray(p, texture=False)
    tray = wp.val().wrapped
    sh = Sheet("MAIN BODY (TRAY)", "FK-H-01  FlashKa_tray.step", "1/2")
    nm = sh.name
    V = make_V(nm)
    L, ih = p.L, p.inner_half
    rb, rl = (p.win_d + p.bore_clear) / 2, (p.las_d + p.las_clear) / 2
    zs2 = p.Z_pcb_top + p.s2_knob_z
    gw, gd = p.wire_groove
    r_groove = rb + gd - 0.2                 # groove bottom radius, from led_wire_paths()
    tdepth = p.m16_drill - 1.0               # full thread depth (3 pitches of run-out in the drill)
    rr = 1.2                                 # bay corner relief radius, hard-coded in build_tray()
    walls, texw = thin_walls(p, housing_dir)

    top = hlr(tray, (0, 0, 1), (1, 0, 0), "t1_top")                 # u = X, v = Y
    side_m = hlr(tray, (0, -1, 0), (1, 0, 0), "t1_side_m")           # u = X, v = Z (control side)
    side_p = hlr(tray, (0, 1, 0), (-1, 0, 0), "t1_side_p")           # u = -X, v = Z (laser side)
    front = hlr(tray, (-1, 0, 0), (0, -1, 0), "t1_front")            # u = -Y, v = Z
    secA, hatA, _ = section_long(wp, p, p.Y_w, "A-A")
    secD, hatD, _ = section_long(wp, p, p.Y_l, "D-D")
    secB, hatB, _ = section_trans(wp, p, 30.0, "B-B")
    secC, hatC, _ = section_trans(wp, p, p.screw_x_front, "C-C")
    XD, XS = 12.0, 32.0                                               # crop limits (X) of D-D, side views
    secD, hatD = clip_view(secD, u1=XD), clip_segs(hatD, u1=XD)
    side_m = clip_view(side_m, u1=XS)
    side_p = {k: clip_polys(v, u0=-XS) for k, v in side_p.items()}

    T = (28, 246)          # top view          (X = 0, Y = 0)
    SM = (28, 149)         # side view -Y      (X = 0, Z = 0)
    SP = (216, 149)        # side view +Y      (X = 0, Z = 0), x = -X
    A = (28, 68)           # section A-A       (X = 0, Z = 0)
    F = (272, 240)         # front view        (Y = 0, Z = 0), x = -Y
    C = (356, 240)         # section C-C       (Y = 0, Z = 0), x = Y
    B = (272, 170)         # section B-B       (Y = 0, Z = 0), x = Y
    D = (336, 170)         # section D-D       (X = 0, Z = 0)

    sh.view(top, *T, "top", hidden=False)
    sh.view(side_m, *SM, "side_m", hidden=False)
    sh.view(side_p, *SP, "side_p", hidden=False)
    sh.view(secA, *A, "secA", hidden=False)
    sh.hatch(hatA, *A)
    sh.view(front, *F, "front", hidden=False)
    sh.view(secC, *C, "secC", hidden=False)
    sh.hatch(hatC, *C)
    sh.view(secB, *B, "secB", hidden=False)
    sh.hatch(hatB, *B)
    sh.view(secD, *D, "secD", hidden=False)
    sh.hatch(hatD, *D)
    sh.breakline(*SM, XS, 0, p.H)
    sh.breakline(*SP, -XS, 0, p.H)
    sh.breakline(*D, XD, 0, p.H)

    # ------------------------------------------------------------ top view
    sh.cur = "top"
    sh.hdim(*T, 0, 10, p.screw_x_front, p.screw_dy, 16, "front taps from the front face", "screw_x_front",
            p.screw_x_front)
    sh.hdim(*T, p.screw_x_front, p.screw_dy, p.X_screw_back, p.screw_dy, 16, "rear taps from the front taps",
            "X_screw_back-screw_x_front", p.X_screw_back - p.screw_x_front)
    sh.hdim(*T, p.X_screw_back, p.screw_dy, L, 10, 16, "rear taps from the tail face", "L-X_screw_back",
            L - p.X_screw_back)
    sh.hdim(*T, 0, -10, p.L_head, -ih, -16, "head block length", "L_head", p.L_head)
    sh.hdim(*T, p.L_head, -ih, p.X_pcb1, -ih, -16, "PCB zone / ledge length", "X_pcb1-L_head",
            p.X_pcb1 - p.L_head)
    sh.hdim(*T, p.X_pcb1, -ih, p.X_batt1, -ih, -16, "antenna zone + cell bay", "X_batt1-X_pcb1",
            p.X_batt1 - p.X_pcb1)
    sh.hdim(*T, p.X_batt1, -ih, L, -10, -16, "tail (front wall + slot + end wall)", "L_tail", p.L_tail)
    sh.hdim(*T, 0, -10, L, -10, -22, "overall length", "L", p.L)
    sh.vdim(*T, L - p.tail_facet, -10, L - p.tail_facet, 10, L + 5, "width", "W", p.W)
    sh.vdim(*T, p.screw_x_front, -p.screw_dy, p.screw_x_front, p.screw_dy, 2.0, "tap spacing (front pair)",
            "2*screw_dy", 2 * p.screw_dy)
    for (x, y) in ((p.screw_x_front, p.screw_dy), (p.screw_x_front, -p.screw_dy),
                   (p.X_screw_back, p.screw_dy), (p.X_screw_back, -p.screw_dy)):
        thread_symbol(sh, *T, x, y, 1.6)
    sh.cutline(*T, (0, p.Y_w), (L, p.Y_w), "A", (0, 1), ext=3.5, shaft=2.5)
    sh.cutline(*T, (0, p.Y_l), (L, p.Y_l), "D", (0, 1), ext=3.5, shaft=2.5)
    sh.cutline(*T, (30, -10), (30, 10), "B", (-1, 0), ext=3.5)
    sh.cutline(*T, (p.screw_x_front, -10), (p.screw_x_front, 10), "C", (-1, 0), ext=3.5)
    sh.text("TOP VIEW (from +Z, lid removed)   items 6, 7, 11, 12", 28, 190, 3.0)
    # callouts in the empty bay
    sh.leader(*T, p.X_screw_back, -p.screw_dy, -36, 0,
              ["(6) 4x M1.6x0.35-6H, thread %s" % V("thread depth", tdepth, "m16_drill-1.0", view="top"),
               "tap drill Ø%s x %s" % (V("tap drill", p.m16_tap, "m16_tap", view="top"),
                                       V("tap drill depth", p.m16_drill, "m16_drill", view="top"))], h=2.2)
    sh.leader(*T, p.X_batt1 - rr / math.sqrt(2), ih - rr / math.sqrt(2), -14, -9,
              "(12) 2x Ø%s relief" % V("corner relief diameter", 2 * rr, "2*1.2 (hard-coded in build_tray)",
                                       2 * rr, view="top"), h=2.2)
    sh.leader(*T, 31.5, ih - p.ledge_w / 2, 14, -9, "(7) PCB ledges, see B-B", h=2.2)

    # ------------------------------------------------------------ side views
    sh.cur = "side_m"
    sh.hdim(*SM, 0, 0, p.X_usb, p.Z_usb, -7, "USB-C centre from the front face", "X_usb", p.X_usb)
    sh.vdim(*SM, 0, 0, 0, p.H, -6, "height", "H", p.H)
    sh.center(*SM, p.X_usb, p.Z_usb, 0.5)
    uw, uh, ur = p.usb_open
    sh.leader(*SM, p.X_usb + 1.5, p.Z_usb + uh / 2, 38.8, 11,
              ["(8) USB-C opening, THRU",
               "%s x %s R%s +/-0.05" % (V("USB-C opening width", uw, "usb_open[0]", view="side_m", md=1),
                                         V("USB-C opening height", uh, "usb_open[1]", view="side_m", md=1),
                                         V("USB-C opening radius", ur, "usb_open[2]", view="side_m", md=1)),
               "centre Z %s, outer edge C%s" % (V("USB-C centre Z", p.Z_usb, "Z_pcb_bot-3.21/2", view="side_m"),
                                                V("USB-C chamfer", p.usb_open_chamfer, "usb_open_chamfer",
                                                  view="side_m"))], h=2.2)
    sh.text("SIDE VIEW from -Y (control side)   item 8", 28, 123, 3.0)
    sh.cur = "side_p"
    sh.hdim(*SP, -p.X_s2, zs2, 0, 0, -7, "S2 slot centre from the front face", "X_s2", p.X_s2)
    sh.vdim(*SP, 0, 0, 0, p.H, 6, "height", "H", p.H)
    sh.center(*SP, -p.X_s2, zs2, 0.5)
    s2w, s2h, s2r = p.s2_slot
    sh.leader(*SP, -p.X_s2, zs2 + s2h / 2, -8, 14,
              ["(10) S2 slot, THRU",
               "%s x %s R%s +/-0.1" % (V("S2 slot width", s2w, "s2_slot[0]", view="side_p", md=1),
                                        V("S2 slot height", s2h, "s2_slot[1]", view="side_p", md=1),
                                        V("S2 slot radius", s2r, "s2_slot[2]", view="side_p", md=1)),
               "centre Z %s" % V("S2 slot centre Z", zs2, "Z_pcb_top+s2_knob_z", view="side_p")], h=2.2)
    sh.text("SIDE VIEW from +Y (laser side)   item 10", 152, 123, 3.0)

    # ------------------------------------------------------------ section A-A
    sh.cur = "secA"
    sh.hdim(*A, 0, p.H, p.D_w, p.Z_axis + rb, 22, "window bore depth", "D_w", p.D_w, "<> +/-0.05")
    sh.vdim(*A, 2.5, p.Z_axis - rb, 2.5, p.Z_axis + rb, 2.5, "window bore diameter", "win_d+bore_clear",
            2 * rb, "%%c<>")
    sh.vdim(*A, 60, p.floor, 60, p.Z_lid, 60, "cavity depth (floor to lid seat)", "Z_lid-floor",
            p.Z_lid - p.floor)
    sh.vdim(*A, p.X_pcb1, 0, p.X_pcb1, p.Z_pcb_bot, p.X_pcb1 + 9, "PCB ledge height", "Z_pcb_bot",
            p.Z_pcb_bot, "<> +/-0.05", shift=6)
    sh.vdim(*A, L, 0, L, p.H, L + 5, "height", "H", p.H)
    sh.leader(*A, 1.0, p.Z_axis - rb, 16, -21.4, "(1) window bore, flat floor", h=2.2)
    sh.leader(*A, 4.5, p.Z_axis - r_groove + 0.3, 9, -16.8, "(2) 2x LED wire grooves", h=2.2)
    sh.leader(*A, 7.0, p.Z_axis - p.led_wire_dz, 4, -15, "(3) 2x LED wire holes", h=2.2)
    sh.text("SECTION A-A  (plane Y = %s through the window axis, seen from -Y)   items 1, 2, 3, 7, 11"
            % num(p.Y_w), 100, 52, 3.0)

    # ------------------------------------------------------------ front view
    sh.cur = "front"
    sh.hdim(*F, -10, 0, -p.Y_l, p.Z_las, -6, "laser axis from the +Y face", "W/2-Y_l", p.W / 2 - p.Y_l)
    sh.hdim(*F, -p.Y_l, p.Z_las, -p.Y_w, p.Z_axis, -6, "window axis to laser axis", "Y_l-Y_w", p.Y_l - p.Y_w)
    sh.hdim(*F, -p.Y_w, p.Z_axis, 10, 0, -6, "window axis from the control face", "W/2+Y_w", p.W / 2 + p.Y_w)
    sh.vdim(*F, -10, 0, -p.Y_l, p.Z_las, -14, "laser axis height", "Z_las", p.Z_las)
    sh.vdim(*F, 10, 0, -p.Y_w, p.Z_axis, 14, "window axis height", "Z_axis", p.Z_axis)
    sh.vdim(*F, 10, 0, 10, p.H, 20, "height", "H", p.H)
    sh.center(*F, -p.Y_w, p.Z_axis, rb)
    sh.center(*F, -p.Y_l, p.Z_las, rl)
    a45 = math.radians(45)
    sh.leader(*F, -p.Y_w + rb * math.cos(a45), p.Z_axis + rb * math.sin(a45), 8, 14,
              "(1) Ø%s +0.05/0" % V("window bore diameter", 2 * rb, "win_d+bore_clear", view="front"), h=2.2)
    sh.leader(*F, -p.Y_l - rl * math.cos(a45), p.Z_las + rl * math.sin(a45), -4, 22,
              "(4) Ø%s +0.05/0" % V("laser bore diameter", 2 * rl, "las_d+las_clear", view="front"), h=2.2)
    sh.text("FRONT VIEW (from -X)   items 1-4", 246, 214, 3.0)

    # ------------------------------------------------------------ section C-C
    sh.cur = "secC"
    sh.hdim(*C, -p.screw_dy, p.Z_lid, p.screw_dy, p.Z_lid, 19, "tap spacing", "2*screw_dy", 2 * p.screw_dy)
    for sg in (-1, 1):
        for dx in (-0.8, 0.8):
            sh.msp.add_line(sh.P(*C, sg * p.screw_dy + dx, p.Z_lid),
                            sh.P(*C, sg * p.screw_dy + dx, p.Z_lid - tdepth), dxfattribs={"layer": "HATCH"})
    sh.leader(*C, p.screw_dy + 0.625, p.Z_lid - 1.0, 8, 8,
              ["(6) 4x M1.6x0.35-6H",
               "thread %s min" % V("thread depth", tdepth, "m16_drill-1.0", view="secC"),
               "drill Ø%s x %s" % (V("tap drill", p.m16_tap, "m16_tap", view="secC"),
                                    V("tap drill depth", p.m16_drill, "m16_drill", view="secC"))], h=2.0)
    sh.leader(*C, -p.Y_w, p.Z_axis - p.led_wire_dz - 0.65, -6, -10, "(3) 2x Ø%s" % V(
        "LED wire hole diameter", p.ledwire_d, "ledwire_d", view="secC"), h=2.2)
    sh.leader(*C, p.Y_l, p.Z_las - rl, 4, -10, "(4) Ø%s +0.05/0" % V(
        "laser bore diameter", 2 * rl, "las_d+las_clear", view="secC"), h=2.2)
    sh.text("SECTION C-C  (X = %s)   items 3, 4, 6" % num(p.screw_x_front), 318, 214, 3.0)

    # ------------------------------------------------------------ section B-B
    sh.cur = "secB"
    sh.hdim(*B, -ih, p.Z_lid, ih, p.Z_lid, 19, "cavity width", "2*(W/2-wall)", 2 * ih)
    sh.hdim(*B, -10, 2.0, 10, 2.0, -6, "width", "W", p.W)
    sh.hdim(*B, -(ih - p.ledge_w), 5.0, ih - p.ledge_w, 5.0, 5.0, "trough width between the ledges",
            "2*(inner_half-ledge_w)", 2 * (ih - p.ledge_w))
    sh.hdim(*B, ih - p.ledge_w, p.Z_pcb_bot, ih, p.Z_pcb_bot, 12.5, "ledge width", "ledge_w", p.ledge_w,
            shift=9)
    sh.vdim(*B, 7.9, 0, 7.9, p.Z_pcb_bot, 14, "PCB ledge height", "Z_pcb_bot", p.Z_pcb_bot, "<> +/-0.05")
    sh.vdim(*B, 8.0, 0, 9.9, p.Z_lid, 19, "lid seat height", "Z_lid", p.Z_lid)
    sh.text("SECTION B-B  (X = 30)   items 7, 11", 246, 147, 3.0)

    # ------------------------------------------------------------ section D-D
    sh.cur = "secD"
    sh.vdim(*D, 2.5, p.Z_las - rl, 2.5, p.Z_las + rl, 2.5, "laser bore diameter", "las_d+las_clear", 2 * rl,
            "%%c<>")
    sh.hdim(*D, 0, 0, p.las_grub_x, 0, -6, "M2 hole from the front face", "las_grub_x", p.las_grub_x)
    sh.vdim(*D, 0, 0, 0, p.Z_las, -5, "laser axis height", "Z_las", p.Z_las)
    for dx in (-1.0, 1.0):
        sh.msp.add_line(sh.P(*D, p.las_grub_x + dx, 0), sh.P(*D, p.las_grub_x + dx, p.Z_las - rl),
                        dxfattribs={"layer": "HATCH"})
    sh.leader(*D, XD - 1.0, p.Z_las + rl - 0.3, 8, 12, ["(4) Ø%s +0.05/0" % V(
        "laser bore diameter", 2 * rl, "las_d+las_clear", view="secD"), "open to the cavity", "from X %s" % V(
        "head block length", p.L_head, "L_head", view="secD")], h=2.0)
    sh.leader(*D, p.las_grub_x + 1.0, 1.2, 12, -12,
              ["(5) M2x0.4-6H into the bore",
               "tap drill Ø%s, thread %s" % (V("M2 tap drill", p.m2_tap, "m2_tap", view="secD"),
                                              V("M2 thread length", p.Z_las - rl, "Z_las-las_d/2-las_clear/2",
                                                view="secD"))], h=2.0)
    sh.text("SECTION D-D  (Y = %s)   items 4, 5" % num(p.Y_l), 318, 147, 3.0)

    # ------------------------------------------------------------ feature table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    rows = [
        ["1", "Window bore (front)",
         "Ø%s x %s deep, flat floor; axis Y %s, Z %s\n= %s from the control-side face" % (
             n("window bore dia", 2 * rb, "win_d+bore_clear", md=1), n("window bore depth", p.D_w, "D_w"),
             n("window axis Y", p.Y_w, "Y_w"), n("window axis Z", p.Z_axis, "Z_axis", md=1),
             n("window axis from the control face", p.W / 2 + p.Y_w, "W/2+Y_w")),
         "Ø +0.05/0; depth +/-0.05\nfloor flat 0.03, Ra 1.6"],
        ["2", "LED wire grooves 2x",
         "at 12 and 6 o'clock: %s wide, bottom R%s from the axis,\nX %s to %s (bore floor)" % (
             n("groove width", gw, "wire_groove[0]", md=1), n("groove bottom radius", r_groove, "rb+gd-0.2"),
             n("groove start X", p.x_led_board - 0.6, "x_led_board-0.6", md=1), n("groove end X", p.D_w, "D_w")),
         "+/-0.1"],
        ["3", "LED wire holes 2x",
         "Ø%s from the bore floor into the cavity (X %s to %s),\nat Z %s +/- %s, Y %s" % (
             n("wire hole dia", p.ledwire_d, "ledwire_d", md=1), n("wire hole start X", p.D_w, "D_w"),
             n("wire hole end X", p.L_head, "L_head", md=1), n("wire hole Z centre", p.Z_axis, "Z_axis", md=1),
             n("wire hole Z offset", p.led_wire_dz, "led_wire_dz", md=1), n("wire hole Y", p.Y_w, "Y_w")),
         "+/-0.1"],
        ["4", "Laser bore (front)",
         "Ø%s, axis Y %s (%s from the +Y face), Z %s; open to the\ncavity at X %s (module 6 x 12, recess %s)" % (
             n("laser bore dia", 2 * rl, "las_d+las_clear", md=1), n("laser axis Y", p.Y_l, "Y_l"),
             n("laser axis from the +Y face", p.W / 2 - p.Y_l, "W/2-Y_l"), n("laser axis Z", p.Z_las, "Z_las", md=1),
             n("head block length", p.L_head, "L_head", md=1), n("laser recess", p.las_recess, "las_recess")),
         "Ø +0.05/0; axis +/-0.05"],
        ["5", "Set-screw hole (bottom)",
         "M2x0.4-6H from the bottom face into the laser bore, X %s,\nY %s; tap drill Ø%s, thread length %s" % (
             n("M2 hole X", p.las_grub_x, "las_grub_x", md=1), n("M2 hole Y", p.Y_l, "Y_l"),
             n("M2 tap drill", p.m2_tap, "m2_tap", md=1), n("M2 thread length", p.Z_las - rl, "Z_las-rl")),
         "6H; position +/-0.1"],
        ["6", "Lid screw threads 4x",
         "M1.6x0.35-6H, drill Ø%s x %s deep (flat), thread %s min;\nX %s and %s, Y +/- %s" % (
             n("tap drill", p.m16_tap, "m16_tap"), n("tap drill depth", p.m16_drill, "m16_drill", md=1),
             n("thread depth", tdepth, "m16_drill-1.0", md=1), n("front tap X", p.screw_x_front, "screw_x_front", md=1),
             n("rear tap X", p.X_screw_back, "X_screw_back", md=1), n("tap Y", p.screw_dy, "screw_dy", md=1)),
         "6H; position +/-0.1"],
        ["7", "PCB ledges",
         "Z %s, %s wide, X %s to %s. None: -Y at X %s to %s (USB-C);\n+Y at X < %s (laser)" % (
             n("ledge height", p.Z_pcb_bot, "Z_pcb_bot", md=1), n("ledge width", p.ledge_w, "ledge_w", md=1),
             n("ledge start X", p.L_head, "L_head", md=1), n("ledge end X", p.X_pcb1, "X_pcb1", md=1),
             n("USB-C gap start", p.minusY_open[0][0], "X_usb-4.9"), n("USB-C gap end", p.minusY_open[0][1], "X_usb+5.0"),
             n("laser keepout X", p.las_keepout_x, "las_keepout_x")),
         "Z +/-0.05; both ledges\ncoplanar within 0.05"],
        ["8", "USB-C opening (-Y wall)",
         "%s x %s R%s through; centre X %s, Z %s;\nouter edge C%s" % (
             n("USB-C opening width", p.usb_open[0], "usb_open[0]", md=1), n("USB-C opening height", p.usb_open[1], "usb_open[1]", md=1),
             n("USB-C opening radius", p.usb_open[2], "usb_open[2]", md=1), n("USB-C X", p.X_usb, "X_usb", md=1),
             n("USB-C centre Z", p.Z_usb, "Z_pcb_bot-3.21/2"), n("USB-C chamfer", p.usb_open_chamfer, "usb_open_chamfer", md=1)),
         "+/-0.05"],
        ["9", "Floor holes (bottom face)",
         "main Ø%s thru + counterbore Ø%s x %s deep from inside;\n2 slide holes Ø%s thru (0.2 x 45 deg chamfer); window: sheet 2" % (
             n("main hole dia", p.main_hole, "main_hole", md=2), n("counterbore dia", p.tube_rim[0] + 0.05, "tube_rim[0]+0.05", md=2),
             n("counterbore depth", p.floor - p.tube_rim[1], "floor-tube_rim[1]", md=1), n("slide hole dia", p.slide_hole, "slide_hole", md=1)),
         "Ø +0.05/0; position +/-0.05"],
        ["10", "S2 slot (+Y wall)",
         "%s x %s R%s through; centre X %s, Z %s" % (
             n("S2 slot width", p.s2_slot[0], "s2_slot[0]", md=1), n("S2 slot height", p.s2_slot[1], "s2_slot[1]", md=1),
             n("S2 slot radius", p.s2_slot[2], "s2_slot[2]", md=1), n("S2 X", p.X_s2, "X_s2"),
             n("S2 slot centre Z", zs2, "Z_pcb_top+s2_knob_z", md=1)),
         "+/-0.1"],
        ["11", "Cavity",
         "%s wide (%s walls), floor Z %s, lid seat Z %s; vertical\ncorners R%s; trough %s wide between the ledges" % (
             n("cavity width", 2 * ih, "2*(W/2-wall)", md=1), n("wall", p.wall, "wall", md=1),
             n("floor Z", p.floor, "floor", md=1), n("lid seat Z", p.Z_lid, "Z_lid", md=1),
             n("inner corner radius", p.inner_r, "inner_r", md=1), n("trough width", 2 * (ih - p.ledge_w), "2*(inner_half-ledge_w)", md=1)),
         "+/-0.1"],
        ["12", "Bay corner reliefs 2x",
         "Ø%s through the bay-end corners, centres X %s, Y +/- %s" % (
             n("relief dia", 2 * rr, "2*1.2 (hard-coded)", pval=2 * rr, md=1),
             n("relief X", p.X_batt1 - rr / math.sqrt(2), "X_batt1-1.2/sqrt2"),
             n("relief Y", ih - rr / math.sqrt(2), "inner_half-1.2/sqrt2")),
         "+/-0.1"],
        ["13", "Exterior, lid, marking",
         "floor holes and window, V-ring and skin seams, tail and lanyard slot,\nmarking: sheet 2.  Lid: drawing FK-H-02.", ""],
    ]
    sh.table(234, 141, (7, 36, 86, 45), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)

    # ------------------------------------------------------------ notes
    t = lambda k: walls[k]
    NW = 96.0
    notes_a = [
        "NOTES",
        "1  Material: aluminium 6061-T6. Geometry per FlashKa_tray.step; this sheet adds threads, fits, "
        "finish and notes.",
        "2  General tolerances ISO 2768-mK; toleranced values are critical.",
        "3  Threads are tapped before anodising and gauged after finishing.",
        "4  Break all sharp edges 0.1-0.2. Deburr the USB-C and S2 openings and the floor holes from inside and the "
        "window bore edge: glass (10.0 x 1.0) and DTP board (10.0 +/-0.1) must drop in.",
        "5  Finish: fine glass-bead blast, then anodise type II matte black (8-12 um). Tolerances apply "
        "after finishing.",
        "6  Window bore floor (X %s) is the LED board contact face: flat 0.03, Ra 1.6, no burr or "
        "anodise step." % V("bore floor X", p.D_w, "D_w", view="notes"),
    ]
    notes_b = [
        "7  Thin walls in the STEP (mm): %s window bore to control face; %s laser bore to +Y face; "
        "%s front tap to head back face; %s front tap to window bore and bore floor; %s tail front wall; "
        "%s floor between the main counterbore and a slide hole. "
        "Finish them in a light last pass." % (
            V("wall window bore - control face", t("window bore to control-side face"), "min_walls", view="notes"),
            V("wall laser bore - +Y face", t("laser bore to laser-side face"), "min_walls", view="notes", md=1),
            V("wall front tap - head back face", t("front screw tap to head rear face"), "min_walls", view="notes"),
            V("wall front tap - bore", t("wall front lid tap -Y - window bore"), "min_walls", view="notes"),
            V("wall tail front", t("tail front wall (bay to slot)"), "min_walls", view="notes", md=1),
            V("wall floor counterbore - slide hole", t("floor: main counterbore to slide hole"), "min_walls", view="notes")),
        "8  Inner vertical corners R%s (pocket %s deep); the bay corner reliefs (12) are intended. "
        "Floor edges stay sharp (flat end mill)." % (
            V("inner corner radius", p.inner_r, "inner_r", view="notes", md=1),
            V("pocket depth", p.Z_lid - p.floor, "Z_lid-floor", view="notes", md=1)),
        "9  Sections: A-A at Y %s (window axis), D-D at Y %s (laser axis), B-B at X 30, C-C at X %s "
        "(front taps)." % (V("section A-A plane", p.Y_w, "Y_w", view="notes"),
                            V("section D-D plane", p.Y_l, "Y_l", view="notes"),
                            V("section C-C plane", p.screw_x_front, "screw_x_front", view="notes", md=1)),
    ]
    lines_a = [ln for n_ in notes_a for ln in wrap(n_, NW, 2.0)]
    lines_b = [ln for n_ in notes_b for ln in wrap(n_, NW, 2.0)]
    sh.mtext(lines_a, 28, 47, 2.0, 1.0)
    sh.mtext(lines_b, 128, 47, 2.0, 1.0)
    return sh, locals()






def vgroove_profile(depth, ext=0.9, h=0.6):
    """schematic section of a 90 deg V seam groove (u across, v depth), for the detail view"""
    loop = [(-ext, 0.0), (-depth, 0.0), (0.0, depth), (depth, 0.0), (ext, 0.0), (ext, h), (-ext, h)]
    return {"vis": [loop + [loop[0]]]}, hatch_segments([loop], 0.15)


def tray_sheet2(p, out, housing_dir=None):
    """Sheet 2: exterior - floor holes and RF window, skin seams (frames + stringers), V-ring, tail window,
    lanyard slot, facets, marking."""
    tex = H.build_tray(p)
    sh = Sheet("MAIN BODY (TRAY) - EXTERIOR", "FK-H-01  FlashKa_tray.step", "2/2")
    nm = sh.name
    V = make_V(nm)
    L = p.L
    xw0, xw1 = tail_window_x(p)
    xs0 = p.X_lan - p.lan_slot_w / 2
    hy, kc = p.twin_y / 2, p.twin_corner
    ax = p.lid_x0 - p.seam_depth
    fx0, fx1, fhy, fr = p.frw_box
    sd = p.skin_depth

    bottom = hlr(tex.val().wrapped, (0, 0, -1), (1, 0, 0), "t2_bottom")       # u = X, v = -Y
    side_m = hlr(tex.val().wrapped, (0, -1, 0), (1, 0, 0), "t2_side_m")        # u = X, v = Z
    side_p = hlr(tex.val().wrapped, (0, 1, 0), (-1, 0, 0), "t2_side_p")        # u = -X, v = Z
    secV, hatV = vgroove_profile(sd)

    B = (28, 250)
    SM = (28, 150)
    SP = (217, 96)
    VD = (352, 232)
    sh.view(bottom, *B, "bottom", hidden=False)
    sh.view(side_m, *SM, "side_m", hidden=False)
    sh.view(side_p, *SP, "side_p", hidden=False)
    sh.view(secV, *VD, "secV", hidden=False, scale=40.0)
    sh.hatch(hatV, *VD)

    # ------------------------------------------------------------ bottom view
    sh.cur = "bottom"
    row = -16
    sh.hdim(*B, 0, -10, p.X_next, -p.btn_y, row, "slide hole SW2 from the front face", "X_next", p.X_next)
    sh.hdim(*B, p.X_next, -p.btn_y, p.X_main, -p.btn_y, row, "main hole from SW2 hole", "X_main-X_next",
            p.X_main - p.X_next)
    sh.hdim(*B, p.X_main, -p.btn_y, p.X_prev, -p.btn_y, row, "SW3 hole from the main hole", "X_prev-X_main",
            p.X_prev - p.X_main)
    sh.hdim(*B, p.X_prev, -p.btn_y, fx0, -fhy, row, "floor RF window from the SW3 hole", "frw_box[0]-X_prev",
            fx0 - p.X_prev)
    sh.hdim(*B, fx0, -fhy, fx1, -fhy, row, "floor RF window length", "frw_box[1]-frw_box[0]", fx1 - fx0)
    sh.hdim(*B, 0, -10, ax, -10, -22, "V-ring apex from the front face", "lid_x0-seam_depth", ax)
    pv = ax
    for k, xk in enumerate(p.skin_frames):
        sh.hdim(*B, pv, -10, xk, -10, -22 if k % 2 == 0 else -28, "frame %d from the previous seam" % (k + 1),
                "skin_frames[%d]-prev" % k, xk - pv)
        pv = xk
    sh.hdim(*B, pv, -10, L, -10, -22, "last frame to the tail face", "L-skin_frames[-1]", L - pv)
    sh.vdim(*B, fx1, -fhy, fx1, fhy, fx1 + 3.2, "floor RF window width", "2*frw_box[2]", 2 * fhy)
    sh.vdim(*B, xs0, -p.lan_slot_len / 2, xs0, p.lan_slot_len / 2, xs0 - 1.9, "lanyard slot length",
            "lan_slot_len", p.lan_slot_len)
    sh.vdim(*B, p.X_lan, -hy, p.X_lan, hy, L + 5, "tail window width", "twin_y", p.twin_y)
    sh.center(*B, p.X_main, -p.btn_y, p.main_hole / 2)
    sh.center(*B, p.X_next, -p.btn_y, p.slide_hole / 2)
    sh.center(*B, p.X_prev, -p.btn_y, p.slide_hole / 2)
    sh.leader(*B, p.X_main, -p.btn_y + p.tube_rim[0] / 2 * 0.7, 3, 13.3,
              ["(9) main hole Ø%s, c'bore Ø%s" % (V("main hole dia", p.main_hole, "main_hole", view="bottom", md=2),
                                                   V("counterbore dia", p.tube_rim[0] + 0.05, "tube_rim[0]+0.05",
                                                     view="bottom", md=2))], h=2.2)
    sh.leader(*B, p.X_next, -p.btn_y - p.slide_hole / 2 * 0.7, -3, 19.5,
              "(9) 2x Ø%s, C0.2" % V("slide hole dia", p.slide_hole, "slide_hole", view="bottom", md=1),
              h=2.2)
    sh.leader(*B, 0.5 * (fx0 + fx1), fhy - 0.2, 6, 11.5,
              "(10) RF window %s x %s R%s" % (V("floor RF window length", fx1 - fx0, "frw_box[1]-frw_box[0]",
                                                 view="bottom", md=1),
                                               V("floor RF window width", 2 * fhy, "2*frw_box[2]", view="bottom",
                                                 md=1),
                                               V("floor RF window radius", fr, "frw_box[3]", view="bottom", md=1)),
              h=2.2)
    sh.text("BOTTOM VIEW (from -Z)   items 9, 10, 14-21", 28, 281, 3.0)

    # ------------------------------------------------------------ side views
    sh.cur = "side_m"
    sh.vdim(*SM, p.skin_stringer_x[1], 0, p.skin_stringer_x[1], p.skin_stringer_z[0], p.skin_stringer_x[1] + 4,
            "lower side stringer height", "skin_stringer_z[0]", p.skin_stringer_z[0], shift=2)
    sh.vdim(*SM, p.skin_stringer_x[1], 0, p.skin_stringer_x[1], p.skin_stringer_z[1], p.skin_stringer_x[1] + 8,
            "upper side stringer height", "skin_stringer_z[1]", p.skin_stringer_z[1])
    sh.vdim(*SM, 0, 0, 0, p.H, -6, "height", "H", p.H)
    sh.text("SIDE VIEW from -Y   items 14, 15, 16", 28, 139, 3.0)
    sh.cur = "side_p"
    sh.vdim(*SP, 0, 0, 0, p.H, 6, "height", "H", p.H)
    sh.text("SIDE VIEW from +Y   items 14, 15, 16", 28, 76, 3.0)
    sh.cur = "secV"
    sh.hdim(*VD, -sd, 0, sd, 0, -0.55, "seam groove width", "2*skin_depth", 2 * sd)
    sh.vdim(*VD, sd, 0, sd, sd, sd + 0.95, "seam groove depth", "skin_depth", sd, "<> +/-0.03")
    sh.text("DETAIL V  (seam groove, 90 deg, 40:1)   items 14-16", 300, 268, 3.0)

    # ------------------------------------------------------------ table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    frames = ", ".join(num(x, 1) for x in p.skin_frames)
    rows = [
        ["14", "V-ring seam (lid joint)",
         "90 deg V groove, %s deep, round the body at X %s (apex);\nlid and tray meet in a rabbet (lip %s)" % (
             n("V-ring depth", p.seam_depth, "seam_depth", md=2), n("V-ring apex X", ax, "lid_x0-seam_depth", dec=2),
             n("lid lip height", p.H - p.lid_lip_z, "H-lid_lip_z", md=1)),
         "depth +/-0.03"],
        ["15", "Frame seams 6x",
         "90 deg V, %s deep, rings round the body at X =\n%s; continuous over the lid joint; A, B in halves" % (
             n("frame groove depth", sd, "skin_depth", md=2), frames),
         "depth +/-0.03\nX +/-0.1"],
        ["16", "Stringer seams",
         "90 deg V, %s deep: sides Z %s and %s (X %s to %s);\nlid and bottom at Y +/- %s (X %s to %s)" % (
             n("stringer depth", sd, "skin_depth", md=2), n("lower stringer Z", p.skin_stringer_z[0], "skin_stringer_z[0]", md=1),
             n("upper stringer Z", p.skin_stringer_z[1], "skin_stringer_z[1]", md=1),
             n("side stringer start X", ax, "lid_x0-seam_depth", dec=2), n("side stringer end X", p.skin_stringer_x[1], "skin_stringer_x[1]", md=1),
             n("stringer Y", p.skin_stringer_y, "skin_stringer_y", md=1), n("stringer start X", p.skin_stringer_x[0], "skin_stringer_x[0]", md=1),
             n("stringer end X", p.skin_stringer_x[1], "skin_stringer_x[1]", md=1)),
         "depth +/-0.03"],
        ["17", "Seam clearances",
         "metal under any groove >= %s; seams >= %s from any\nopening or hole; numbers: housing_interface.json" % (
             n("min metal under a groove", p.skin_min_metal, "skin_min_metal", md=1), n("seam clearance", p.skin_clear, "skin_clear", md=1)),
         ""],
        ["18", "Tail window (bottom)",
         "%s x %s, %s deep, corners R%s / R%s, chamfer C%s; X %s to %s" % (
             n("tail window length", xw1 - xw0, "twin_x", md=1), n("tail window width", p.twin_y, "twin_y", md=1),
             n("tail window depth", p.twin_depth, "twin_depth", md=1), n("tail window corner", p.twin_r, "twin_r", md=1),
             n("tail window big corner", kc, "twin_corner", md=1), n("tail window chamfer", p.twin_chamfer, "twin_chamfer", md=1),
             n("tail window start X", xw0, TW_X0_EXPR, md=1), n("tail window end X", xw1, "X_lan+twin_x/2", md=1)),
         "+/-0.1"],
        ["19", "Lanyard slot, THRU",
         "stadium %s x %s, centre X %s; chamfer C%s both faces" % (
             n("lanyard slot width", p.lan_slot_w, "lan_slot_w", md=1), n("lanyard slot length", p.lan_slot_len, "lan_slot_len", md=1),
             n("lanyard slot centre X", p.X_lan, "X_lan", md=1), n("lanyard slot chamfer", p.lan_chamfer, "lan_chamfer")),
         "+/-0.1"],
        ["20", "Tail facets",
         "%s x 45 deg on the four tail corners; end edge C%s" % (
             n("tail facet", p.tail_facet, "tail_facet", md=1), n("end chamfer", p.C_end, "C_end", md=1)),
         "ISO 2768-mK"],
        ["21", "Laser marking (artwork)",
         "FlashKa_marking_bottom / _minus_y / _plus_y .dxf: layer\nMARK = laser, layer REF = outline (do not mark)", ""],
    ]
    sh.table(232, 190, (7, 30, 100, 40), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)
    NW = 96.0
    notes = [
        "NOTES",
        "1  Seams are 90 deg V grooves cut with a ball-free V cutter (tip R <= 0.03) after the final milling "
        "and before blasting. Do not deepen them: the metal under them is %s at the thinnest spot." % V(
            "min metal under a groove", 1.1, "skin_min_metal", view="notes", md=1),
        "2  The bottom view is drawn with all seams; marking artwork is laser-marked after anodising "
        "(black anodise type II removed by the laser, bare aluminium shows).",
        "3  Bottom-face features (9), (10) are on sheet 1 (items) and here (positions). Floor edges of the holes "
        "get the 0.2 x 45 deg chamfer on the outside.",
        "4  Finish: glass-bead blast, anodise type II matte black (8-12 um), then laser marking.",
    ]
    lines = [ln for n_ in notes for ln in wrap(n_, NW, 2.0)]
    sh.mtext(lines, 28, 60, 2.0, 1.0)
    return sh, locals()


LABEL_FIELD = (11.72, 28.57, 6.9)      # laser label field on the lid: X from, X to, |Y| (flashka_marking.py)


def lid_sheet(p, out, housing_dir=None):
    """Lid drawing: outline, RF window opening + underside pocket, countersunk screws, hold-down boss,
    rabbet lip, label field, seams (sections use the lid without the seams)."""
    lid_t = H.build_lid(p)
    lid_p = H.build_lid(p, texture=False)
    sh = Sheet("LID", "FK-H-02  FlashKa_lid.step", "1/1")
    nm = sh.name
    V = make_V(nm)
    L, x0 = p.L, p.lid_x0
    rfx0, rfx1, rfhy = p.rfw_box
    fl = p.rfw_flange
    pk_x0, pk_x1, pk_hy = rfx0 - fl, rfx1 + fl, rfhy + fl
    xs0 = p.X_lan - p.lan_slot_w / 2
    hy = p.lan_slot_len / 2
    sy = p.screw_dy
    csk_depth = (p.m16_csk - p.m16_clear) / 2
    bx0, bx1, by0, by1 = p.boss_box
    cx0, cx1, cy0, cy1 = p.boss2_box
    z0, z1 = p.Z_lid, p.H
    flat = p.W - 2 * p.R_edge
    LX0, LX1, LY = LABEL_FIELD
    lip = p.H - p.lid_lip_z

    top = hlr(lid_t.val().wrapped, (0, 0, 1), (1, 0, 0), "lid_top")
    bot = hlr(lid_t.val().wrapped, (0, 0, -1), (1, 0, 0), "lid_bot")
    secJ, hatJ, _ = section_trans(lid_p, p, 20.0, "J-J", spacing=0.4)
    GW = (15.0, 45.0, 10.6, 16.2)
    secG, hatG, _ = section_long(lid_p, p, 1.7, "G-G", spacing=0.2)
    secG, hatG = clip_view(secG, u0=GW[0], u1=GW[1], v0=GW[2], v1=GW[3]), clip_segs(hatG, *GW)
    KW = (7.0, 10.2, 13.4, 16.2)
    secK, hatK, _ = section_trans(lid_p, p, 20.0, "K-K", spacing=0.12)
    secK, hatK = clip_view(secK, u0=KW[0], u1=KW[1], v0=KW[2], v1=KW[3]), clip_segs(hatK, *KW)

    T = (21.6, 245)
    U = (21.6, 128)
    J = (320, 190)
    G = (161, 71.0)
    K = (260, 46)
    sh.view(top, *T, "top", hidden=False)
    sh.view(bot, *U, "under", hidden=False)
    sh.view(secJ, *J, "secJ", hidden=False, scale=4.0)
    sh.hatch(hatJ, *J)
    sh.view(secG, *G, "secG", hidden=False, scale=5.0)
    sh.hatch(hatG, *G)
    sh.frame(*G, *GW)
    sh.view(secK, *K, "secK", hidden=False, scale=10.0)
    sh.hatch(hatK, *K)
    sh.frame(*K, *KW)

    # ------------------------------------------------------------ top view
    sh.cur = "top"
    yb = -(p.W / 2 - 0.2)
    sh.hdim(*T, x0, yb, p.screw_x_front, -sy, -16, "front screws from the lid front edge",
            "screw_x_front-lid_x0", p.screw_x_front - x0)
    sh.hdim(*T, p.screw_x_front, -sy, p.X_screw_back, -sy, -16, "screw spacing along X",
            "X_screw_back-screw_x_front", p.X_screw_back - p.screw_x_front)
    sh.hdim(*T, p.X_screw_back, -sy, L, yb, -16, "rear screws to the lid end", "L-X_screw_back", L - p.X_screw_back)
    sh.hdim(*T, x0, yb, rfx0, -rfhy, -22, "RF opening from the lid front edge", "rfw_box[0]-lid_x0", rfx0 - x0)
    sh.hdim(*T, rfx0, -rfhy, rfx1, -rfhy, -22, "RF opening length", "rfw_box[1]-rfw_box[0]", rfx1 - rfx0)
    sh.hdim(*T, x0, yb, LX0, -LY, -28, "label field from the lid front edge", "LABEL_FIELD[0]-lid_x0", LX0 - x0)
    sh.hdim(*T, LX0, -LY, LX1, -LY, -28, "label field length", "LABEL_FIELD[1]-LABEL_FIELD[0]", LX1 - LX0)
    sh.hdim(*T, x0, yb, L, yb, -34, "lid length", "L-lid_x0", L - x0)
    sh.vdim(*T, p.screw_x_front, -sy, p.screw_x_front, sy, p.screw_x_front + 5.0, "screw spacing across",
            "2*screw_dy", 2 * sy)
    sh.vdim(*T, rfx0, -rfhy, rfx0, rfhy, rfx0 - 2.4, "RF opening width", "rfw_y", p.rfw_y)
    sh.vdim(*T, LX0, -LY, LX0, LY, LX0 - 1.8, "label field width", "2*LABEL_FIELD[2]", 2 * LY)
    sh.vdim(*T, xs0, -hy, xs0, hy, xs0 - 1.9, "lanyard slot length", "lan_slot_len", p.lan_slot_len)
    sh.vdim(*T, L, -(p.W / 2 - p.tail_facet), L, p.W / 2 - p.tail_facet, L + 4.0, "tail end width",
            "W-2*tail_facet", p.W - 2 * p.tail_facet)
    pts = [sh.P(*T, LX0, -LY), sh.P(*T, LX1, -LY), sh.P(*T, LX1, LY), sh.P(*T, LX0, LY)]
    sh.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "PHANTOM"})
    sh.tag(*T, p.screw_x_front, sy, -3, 13, 2)
    sh.tag(*T, p.X_screw_back, sy + 1.0, 3, 13, 2)
    sh.tag(*T, 0.5 * (rfx0 + rfx1) - 1.0, rfhy - 0.6, 0, 11, 3)
    sh.tag(*T, 0.5 * (LX0 + LX1), LY, 0, 10, 7)
    sh.tag(*T, p.X_lan - 1.0, hy - 0.4, -10, 18, 5)
    sh.tag(*T, L - p.tail_facet / 2, p.W / 2 - p.tail_facet / 2, 8, 6, 1)
    sh.text("TOP VIEW (from +Z)   items 1, 2, 3, 5, 7, 9", 28, 279, 3.0)

    # ------------------------------------------------------------ underside view
    sh.cur = "under"
    sh.hdim(*U, rfx0, -rfhy, rfx1, -rfhy, -14, "RF opening length", "rfw_box[1]-rfw_box[0]", rfx1 - rfx0)
    sh.hdim(*U, pk_x0, -pk_hy, pk_x1, -pk_hy, -18, "RF pocket length", "rfw_box[1]-rfw_box[0]+2*rfw_flange",
            pk_x1 - pk_x0)
    sh.hdim(*U, bx0, -by0, bx1, -by0, 12.4, "hold-down boss length", "boss_box[1]-boss_box[0]", bx1 - bx0)
    sh.vdim(*U, bx0, -by0, bx0, -by1, bx0 - 2.4, "hold-down boss width", "boss_box[3]-boss_box[2]", by1 - by0)
    sh.leader(*U, 0.5 * (cx0 + cx1), -cy0 - 0.2, -3, -9.5,
              "(8) front boss %s x %s" % (V("front boss length", cx1 - cx0, "boss2_box[1]-boss2_box[0]", view="under", md=1),
                                          V("front boss width", cy1 - cy0, "boss2_box[3]-boss2_box[2]", view="under", md=1)),
              h=2.0)
    sh.vdim(*U, rfx1, -rfhy, rfx1, rfhy, rfx1 + 3.4, "RF opening width", "rfw_y", p.rfw_y)
    sh.tag(*U, 0.5 * (pk_x0 + pk_x1), pk_hy, 0, 11, 4)
    sh.tag(*U, bx0 + 1.0, -by0 + 0.4, -8, 6, 8)
    sh.tag(*U, p.screw_x_front, -sy, 0, -12, 2)
    sh.tag(*U, p.X_lan + 1.6, 0.0, 9, 0, 5)
    sh.text("UNDERSIDE (from -Z)   items 2, 3, 4, 5, 8", 28, 162, 3.0)

    # ------------------------------------------------------------ section J-J (4:1)
    sh.cur = "secJ"
    sh.hdim(*J, -flat / 2, z1, flat / 2, z1, z1 + 2.6, "flat top width", "W-2*R_edge", flat)
    sh.vdim(*J, p.W / 2 - 0.2, z0, p.W / 2 - 0.2, z1, 12.6, "lid thickness", "lid_t", p.lid_t)
    sh.text("SECTION J-J  (X = %s, no seams)   item 1" % num(20.0, 1), 270, 276, 3.0)
    sh.leader(*J, -(p.W / 2 - p.R_edge) - 0.9, z1 - 0.6, -7, 3, "top edges R%s" % V(
        "top edge radius", p.R_edge, "R_edge", view="secJ", md=1), h=2.2)

    # ------------------------------------------------------------ section G-G (6:1)
    sh.cur = "secG"
    zb1, zb2 = p.Z_lid - p.boss_h, p.Z_lid - p.boss2_h
    sh.hdim(*G, bx0, zb1, bx1, zb1, zb1 - 0.5, "can boss length", "boss_box[1]-boss_box[0]", bx1 - bx0)
    sh.vdim(*G, bx1, zb1, bx1, p.Z_lid, bx1 + 0.9, "can boss height", "boss_h", p.boss_h)
    sh.hdim(*G, cx0, zb2, cx1, zb2, zb2 - 0.5, "front boss length", "boss2_box[1]-boss2_box[0]", cx1 - cx0)
    sh.vdim(*G, cx0, zb2, cx0, p.Z_lid, cx0 - 0.9, "front boss height", "boss2_h", p.boss2_h)
    sh.leader(*G, 0.5 * (bx0 + bx1), zb1 + 0.02, 3, -3.5, ["(8) can boss, R%s" % V("boss corner radius", p.boss_r, "boss_r", view="secG", md=1)], h=2.0)
    sh.leader(*G, 0.5 * (cx0 + cx1), zb2 + 0.4, -1, -2.0, ["(8) front boss, R%s" % V("front boss corner radius", p.boss2_r, "boss2_r", view="secG", md=1)], h=2.0)
    sh.text("SECTION G-G  (Y = %s, no seams)   items 8, 3" % num(1.7, 1), 236, 160, 3.0)

    # ------------------------------------------------------------ section K-K (10:1)
    sh.cur = "secK"
    sh.vdim(*K, 8.45, p.lid_lip_z, 8.45, p.Z_lid, 7.5, "lip height below the lid seat", "Z_lid-lid_lip_z",
            p.Z_lid - p.lid_lip_z)
    sh.text("DETAIL K-K  (rabbet lip, X = 20, 10:1)   item 6", 300, 176, 3.0)

    # ------------------------------------------------------------ feature table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    web_pocket = p.lid_t - p.rfw_flange_t
    sliver = sy - p.m16_csk / 2 - (hy + p.lan_chamfer)
    csk_edge = (p.W / 2 - p.R_edge) - (sy + p.m16_csk / 2)
    rows = [
        ["1", "Lid plate",
         "%s thick, X %s to %s (body coordinates); top edges R%s (flat top %s wide),\ntail facets %s x 45 deg as the tray; underside flat" % (
             n("lid thickness", p.lid_t, "lid_t", md=1), n("lid front edge X", x0, "lid_x0", md=1), n("lid end X", L, "L"),
             n("top edge radius", p.R_edge, "R_edge", md=1), n("flat top width", flat, "W-2*R_edge", md=1),
             n("tail facet", p.tail_facet, "tail_facet", md=1)),
         "ISO 2768-mK"],
        ["2", "Screw holes 4x",
         "for M1.6 countersunk (ISO 7046): Ø%s thru, countersink Ø%s x 90 deg\n(%s deep); X %s and %s, Y +/- %s (body coordinates)" % (
             n("screw hole diameter", p.m16_clear, "m16_clear", md=1), n("countersink diameter", p.m16_csk, "m16_csk", md=1),
             n("countersink depth", csk_depth, "(m16_csk-m16_clear)/2"), n("front screw X", p.screw_x_front, "screw_x_front", md=1),
             n("rear screw X", p.X_screw_back, "X_screw_back", md=1), n("screw Y", sy, "screw_dy", md=1)),
         "position +/-0.05\nØ +0.1/0"],
        ["3", "RF window opening",
         "%s x %s, corners R%s, through; X %s to %s, centred on Y 0\n(over the ESP32 module antenna)" % (
             n("RF opening length", rfx1 - rfx0, "rfw_box[1]-rfw_box[0]", md=1), n("RF opening width", p.rfw_y, "rfw_y", md=1),
             n("RF opening corner radius", p.rfw_r, "rfw_r", md=1), n("RF opening start X", rfx0, "rfw_box[0]", md=1),
             n("RF opening end X", rfx1, "rfw_box[1]", md=1)),
         "+/-0.05"],
        ["4", "RF pocket (underside)",
         "%s x %s, R%s, %s deep (Z %s to %s), %s margin round the opening;\nseat of the resin insert flange; %s of lid remains above" % (
             n("RF pocket length", pk_x1 - pk_x0, "rfw_box[1]-rfw_box[0]+2*rfw_flange", md=1),
             n("RF pocket width", 2 * pk_hy, "rfw_y+2*rfw_flange", md=1), n("RF pocket corner radius", p.rfw_r + fl, "rfw_r+rfw_flange", md=1),
             n("RF pocket depth", p.rfw_flange_t, "rfw_flange_t", md=1), n("lid underside Z", z0, "Z_lid", md=1),
             n("RF pocket ceiling Z", z0 + p.rfw_flange_t, "Z_lid+rfw_flange_t", md=1), n("RF pocket margin", fl, "rfw_flange", md=1),
             n("lid above the pocket", web_pocket, "lid_t-rfw_flange_t")),
         "+/-0.05; depth +/-0.03"],
        ["5", "Lanyard slot, THRU",
         "stadium %s x %s, centre X %s, Y 0; chamfer C%s on the top face;\nsame slot as the tray (FK-H-01 item 19)" % (
             n("lanyard slot width", p.lan_slot_w, "lan_slot_w", md=1), n("lanyard slot length", p.lan_slot_len, "lan_slot_len", md=1),
             n("lanyard slot centre X", p.X_lan, "X_lan", md=1), n("lanyard slot chamfer", p.lan_chamfer, "lan_chamfer")),
         "+/-0.1"],
        ["6", "Rabbet lip (underside)",
         "lip %s tall (Z %s to %s) round the joint, clearance %s per side to the tray;\nthe lid seam groove (V, %s deep) at X %s" % (
             n("lip height", p.Z_lid - p.lid_lip_z, "Z_lid-lid_lip_z", md=1), n("lip bottom Z", p.lid_lip_z, "lid_lip_z", md=1),
             n("lip top Z", p.Z_lid, "Z_lid", md=1), n("lip clearance", p.lid_lip_gap, "lid_lip_gap", md=2),
             n("V-ring depth", p.seam_depth, "seam_depth", md=2), n("V-ring apex X", x0 - p.seam_depth, "lid_x0-seam_depth", dec=2)),
         "+/-0.03"],
        ["7", "Label field (top face)",
         "X %s to %s, Y +/- %s: laser class label, hazard symbol,\nFLASHKA v0.6 (FlashKa_marking_lid_class2 / _class3R .dxf)" % (
             n("label field start X", LX0, "LABEL_FIELD[0]", md=1), n("label field end X", LX1, "LABEL_FIELD[1]", md=1),
             n("label field half width", LY, "LABEL_FIELD[2]", md=1)),
         "marking +/-0.1"],
        ["8", "Hold-down bosses 2x",
         "can boss X %s to %s, Y %s to %s, R%s, %s tall (face Z %s);\nfront boss X %s to %s, Y %s to %s, R%s, %s tall (face Z %s)" % (
             n("boss start X", bx0, "boss_box[0]", md=1), n("boss end X", bx1, "boss_box[1]", md=1),
             n("boss start Y", by0, "boss_box[2]", md=1), n("boss end Y", by1, "boss_box[3]", md=1),
             n("boss corner radius", p.boss_r, "boss_r", md=1), n("boss height", p.boss_h, "boss_h", md=1),
             n("can boss face Z", p.Z_lid - p.boss_h, "Z_lid-boss_h", md=1),
             n("front boss start X", cx0, "boss2_box[0]", dec=2), n("front boss end X", cx1, "boss2_box[1]", dec=2),
             n("front boss start Y", cy0, "boss2_box[2]", dec=2), n("front boss end Y", cy1, "boss2_box[3]", dec=2),
             n("front boss corner radius", p.boss2_r, "boss2_r", md=1), n("front boss height", p.boss2_h, "boss2_h", md=1),
             n("front boss face Z", p.Z_lid - p.boss2_h, "Z_lid-boss2_h", md=1)),
         "+/-0.03 (height)\nposition +/-0.05"],
        ["8a", "Pads (bought parts)",
         "can: %s thermal gap pad (Shore 00 70-80), cut to the can boss; front: %s silicone rubber\nsheet (Shore A 70), cut %s x %s. Both compressed to %s = %s %%" % (
             n("can pad free thickness", p.pad_t0, "pad_t0", md=1), n("front pad free thickness", p.pad2_t0, "pad2_t0", md=1),
             n("front pad length", cx1 - cx0, "boss2_box[1]-boss2_box[0]", md=1), n("front pad width", cy1 - cy0, "boss2_box[3]-boss2_box[2]", md=1),
             n("pad compressed thickness", p.pad_t, "pad_t", md=1), n("pad compression", p.pad_strain * 100, "pad_strain*100", dec=0)),
         "stick on with a drop of\nsilicone adhesive"],
        ["9", "Seams and rivets",
         "frames at X %s and the V-ring; stringers at Y +/- %s (X %s to %s);\nartwork: FlashKa_marking_lid_class2.dxf (MARK = laser, REF = no mark)" % (
             ", ".join(num(x, 1) for x in p.skin_frames), num(p.skin_stringer_y, 1), num(p.skin_stringer_x[0], 1),
             num(p.skin_stringer_x[1], 1)),
         "groove depth +/-0.03"],
        ["10", "RF window insert",
         "not machined here: translucent resin part (FlashKa_rf_window.step), %s clearance\nin the opening and the pocket, glued in from inside" % (
             n("insert clearance", p.rfw_clear, "rfw_clear", md=2)),
         ""],
    ]
    sh.table(28, 90, (7, 34, 112, 43), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)

    NW = 80.0
    notes = [
        "NOTES",
        "1  Material: aluminium 6061-T6, %s thick. Geometry per FlashKa_lid.step; X, Y, Z are body "
        "coordinates (X = 0 at the front face of the body)." % V("lid thickness", p.lid_t, "lid_t", view="notes", md=1),
        "2  General tolerances ISO 2768-mK; toleranced values are critical.",
        "3  Screws: 4x M1.6 x 4 countersunk, ISO 7046 / DIN 965, A2 stainless. The countersink edge is only %s "
        "inside the start of the edge radius: do not enlarge it." % V(
            "countersink edge to edge radius", csk_edge, "(W/2-R_edge)-(screw_dy+m16_csk/2)", view="notes", dec=2),
        "4  Finish: fine glass-bead blast, anodise type II matte black (8-12 um), then laser-mark. Cut the "
        "seams before blasting. Sections G-G, J-J, K-K are drawn without seams.",
        "5  At X %s the rear countersinks and the slot chamfer leave a sliver of only %s at the top face: "
        "break edges lightly (max 0.05)." % (
            V("rear screw X", p.X_screw_back, "X_screw_back", view="notes", md=1),
            V("sliver csk - slot chamfer", sliver, "screw_dy-m16_csk/2-(lan_slot_len/2+lan_chamfer)", view="notes", dec=2)),
        "6  The RF window insert (item 10) is a separate printed part; opening and pocket sizes must not "
        "change without the insert.",
    ]
    lines = [ln for n_ in notes for ln in wrap(n_, NW, 2.0)]
    half = (len(lines) + 1) // 2
    sh.mtext(lines[:half], 236, 108, 2.0, 1.0)
    sh.mtext(lines[half:], 324, 108, 2.0, 1.0)
    return sh, locals()


AX = 10.0       # X of the axis of a turned part on its drawing (the solid is moved there)
SZ = 10.0       # scale of the turned-part drawings


def _turned_views(sh, shape):
    """half-section (X, Z) at 10:1 and the view from -Z; shape has its axis at X = AX, Y = 0"""
    secP, hat, _ = section_long(shape, H.P(), 0.0, "axis", spacing=0.16)
    bv = hlr(shape.val().wrapped, (0, 0, -1), (1, 0, 0))
    SEC = (130 - SZ * AX, 112.0)
    BV = (300 - SZ * AX, 190.0)
    sh.view(secP, *SEC, "sec", hidden=False, scale=SZ)
    sh.hatch(hat, *SEC)
    sh.view(bv, *BV, "bot", hidden=False, scale=SZ)
    sh.center(*SEC, AX, 0, 0)
    sh.msp.add_line(sh.P(*SEC, AX, -0.6), sh.P(*SEC, AX, 8.8), dxfattribs={"layer": "CENTER"})
    return SEC, BV


def cap_sheet(p, kind, out):
    """FlashKa_cap_main (kind 'main') or FlashKa_cap_slide ('slide'): SUS304 turned part"""
    main = kind == "main"
    hd, fd, ft, sd = p.main_cap if main else p.slide_cap
    zf = p.tube_step_z if main else p.floor
    zend = p.Z_sw_tip - p.cap_gap
    sag = 0.4 if main else 0.3
    base = "FlashKa_cap_main" if main else "FlashKa_cap_slide"
    shape = (H.build_cap_main(p).translate((AX - p.X_main, -p.btn_y, 0)) if main else
             H.build_cap_slide(p, p.X_next).translate((AX - p.X_next, -p.btn_y, 0)))
    sh = Sheet("BUTTON CAP - " + ("MAIN (1x)" if main else "SLIDE (2x)"),
               "FK-H-%s  %s.step" % ("03" if main else "04", base), "1/1")
    V = make_V(sh.name)
    SEC, BV = _turned_views(sh, shape)
    ze0 = p.cap_apex_z
    zedge = ze0 + sag
    hole = (p.tube_id_low if main else p.slide_hole)
    # ---- section dims
    sh.cur = "sec"
    sh.hdim(*SEC, AX - hd / 2, ze0 + 0.6, AX + hd / 2, ze0 + 0.6, ze0 - 0.9, "head diameter", "main_cap[0]" if main else "slide_cap[0]",
            hd, "%%c<> -0.05/-0.10")
    sh.hdim(*SEC, AX - fd / 2, zf + ft, AX + fd / 2, zf + ft, zf + ft + 0.6, "flange diameter",
            "main_cap[1]" if main else "slide_cap[1]", fd, "%%c<> -0.05/-0.15", shift=SZ * (sd / 2 + 1.5) + 12)
    sh.hdim(*SEC, AX - sd / 2, zend, AX + sd / 2, zend, zend + 0.7, "stem diameter",
            "main_cap[3]" if main else "slide_cap[3]", sd, "%%c<> -0.02/-0.06")
    sh.vdim(*SEC, AX - fd / 2, ze0, AX - fd / 2, zend, AX - fd / 2 - 1.2, "overall length (apex to stem end)",
            "Z_sw_tip-cap_gap-cap_apex_z", zend - ze0, "<> +/-0.05")
    sh.vdim(*SEC, AX + fd / 2, ze0, AX + fd / 2, zf, AX + fd / 2 + 1.0, "apex to flange underside",
            "flange Z - cap_apex_z", zf - ze0, "<> +/-0.05")
    sh.vdim(*SEC, AX + fd / 2, zf, AX + fd / 2, zf + ft, AX + fd / 2 + 2.4, "flange thickness",
            "main_cap[2]" if main else "slide_cap[2]", ft, "<> +/-0.03", shift=0)
    sh.text("HALF-SECTION (10:1)", 62, 218, 3.0)
    sh.text("VIEW from -Z (10:1)", 256, 134, 3.0)
    sh.cur = "bot"
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    mark = "main_cap" if main else "slide_cap"
    rows = [
        ["1", "Material", "stainless steel SUS304 (1.4301), turned from bar; no thread", ""],
        ["2", "Head (visible)",
         "Ø%s, domed end: %s sag, apex at Z %s (flush with the bottom face -0.1);\ncylinder up to the flange; fits the %s hole (%s)" % (
             n("head diameter", hd, mark + "[0]", md=1), n("dome sag", sag, "dome sag (build_cap_*)", md=1),
             n("dome apex Z", ze0, "cap_apex_z", md=1), "Ø%s tube bore" % num(p.tube_id_low, 1) if main else "Ø%s floor" % num(p.slide_hole, 1),
             "0.1 per side"),
         "Ø +0/-0.05\nRa 1.6 before blast"],
        ["3", "Flange",
         "Ø%s x %s thick, rests on the %s (Z %s)" % (
             n("flange diameter", fd, mark + "[1]", md=1), n("flange thickness", ft, mark + "[2]", md=1),
             "tube step" if main else "floor inside", n("flange seat Z", zf, "tube_step_z" if main else "floor", md=1)),
         "Ø +0/-0.1; thickness +/-0.03"],
        ["4", "Stem",
         "Ø%s from the flange to the stem end at Z %s (free play %s above the\nswitch actuator at Z %s)" % (
             n("stem diameter", sd, mark + "[3]", md=1), n("stem end Z", zend, "Z_sw_tip-cap_gap"),
             n("free play", p.cap_gap, "cap_gap", md=2), n("switch actuator tip Z", p.Z_sw_tip, "Z_sw_tip")),
         "Ø +0/-0.06"],
        ["5", "Overall length",
         "%s from the dome apex to the stem end (stack: free play %s nominal)" % (
             n("overall length", zend - ze0, "Z_sw_tip-cap_gap-cap_apex_z"), n("free play", p.cap_gap, "cap_gap", md=2)),
         "+/-0.05"],
        ["6", "Edges", "break all edges 0.1; stem end face flat, square to the axis within 0.03", ""],
        ["7", "Finish", "fine glass-bead blast (matte), no coating, no marking", ""],
        ["8", "Quantity", "1 per keychain" if main else "2 per keychain (SW2 next, SW3 previous): one drawing, two parts", ""],
    ]
    sh.table(28, 74, (7, 34, 112, 43), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"], h=1.9, pad=0.9, line=2.7)
    NW = 80.0
    notes = [
        "NOTES",
        "1  Material SUS304, bead blast. General tolerances ISO 2768-mK. Geometry per %s.step "
        "(axis at the origin in the STEP; here it is moved to X %s)." % (base, V("axis X", AX, "AX", view="notes", md=1)),
        "2  Small turned part (head Ø%s). The JLCCNC quote may refuse it by size: confirm with the instant quote. "
        "If refused, any CNC service (PCBWay, Xometry, a local workshop) can make it from the same STEP and this "
        "PDF, or use the resin caps from the print kit (FlashKa_print_kit.stl)." % V(
            "head diameter", hd, mark + "[0]", view="notes", md=1),
        "3  The cap must move freely: after the blast, check it falls through the %s with no catch." % (
            "tube (Ø6.0 bore, Ø6.8 above the step)" if main else "Ø3.6 floor hole"),
        "4  Cap stroke and tolerance stack: docs/ch13_v0.6_presenter.md, 13.4.2 (nominal free play 0.30, worst case 0.00, RSS 0.14).",
    ]
    lines = [ln for n_ in notes for ln in wrap(n_, NW, 2.0)]
    sh.mtext(lines, 236, 120, 2.0, 1.0)
    return sh, locals()


def tube_sheet(p, out):
    """FlashKa_tube (reference, 8001 resin, glued into the floor counterbore)"""
    shape = H.build_tube(p).translate((AX - p.X_main, -p.btn_y, 0))
    sh = Sheet("LIGHT-PIPE TUBE (reference)", "FK-H-05  FlashKa_tube.step", "1/1")
    V = make_V(sh.name)
    SEC, BV = _turned_views(sh, shape)
    ro, rr = p.tube_od / 2, p.tube_rim[0] / 2
    z0r, z1r = p.tube_rim[1], p.tube_rim[2]
    zt, zs = p.Z_tube_top, p.tube_step_z
    ri1, ri2 = p.tube_id_low / 2, p.tube_id_up / 2
    sh.cur = "sec"
    sh.hdim(*SEC, AX - ro, zt, AX + ro, zt, zt + 0.9, "tube outer diameter", "tube_od", p.tube_od, "%%c<> -0.05/-0.15")
    sh.hdim(*SEC, AX - rr, z0r, AX + rr, z0r, -0.8, "rim diameter", "tube_rim[0]", p.tube_rim[0], "%%c<> -0.05/-0.15")
    sh.hdim(*SEC, AX - ri1, zs - 0.4, AX + ri1, zs - 0.4, 0.5 * zs - 0.4, "lower bore", "tube_id_low", p.tube_id_low,
            "%%c<> +0.10/0")
    sh.hdim(*SEC, AX - ri2, zt - 0.5, AX + ri2, zt - 0.5, zt - 1.3, "upper bore", "tube_id_up", p.tube_id_up,
            "%%c<> +0.10/0")
    sh.vdim(*SEC, AX + ro, 0, AX + ro, zt, AX + ro + 1.2, "tube height", "Z_tube_top", zt, "<> +/-0.05")
    sh.vdim(*SEC, AX - rr, 0, AX - rr, z0r, AX - rr - 0.6, "rim underside height", "tube_rim[1]", z0r)
    sh.vdim(*SEC, AX - ri1, 0, AX - ri1, zs, AX - ro - 1.4, "cap seat (step) height", "tube_step_z", zs)
    sh.text("HALF-SECTION (10:1)", 62, 218, 3.0)
    sh.text("VIEW from -Z (10:1)", 256, 134, 3.0)
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    rows = [
        ["1", "Material", "photopolymer resin 8001 (JLC3DP), opaque white / translucent as printed; reference part", ""],
        ["2", "Body", "Ø%s, Z 0 to %s; glued into the floor hole Ø%s (gap %s per side)" % (
            n("tube outer diameter", p.tube_od, "tube_od", md=1), n("tube top Z", zt, "Z_tube_top", md=1),
            n("main hole dia", p.main_hole, "main_hole", md=2), n("tube to hole gap", (p.main_hole - p.tube_od) / 2, "(main_hole-tube_od)/2", md=3)),
         "print tolerance +/-0.1"],
        ["3", "Rim", "Ø%s, Z %s to %s, seated in the counterbore Ø%s" % (
            n("rim diameter", p.tube_rim[0], "tube_rim[0]", md=1), n("rim bottom Z", z0r, "tube_rim[1]", md=1),
            n("rim top Z", z1r, "tube_rim[2]", md=1), n("counterbore dia", p.tube_rim[0] + 0.05, "tube_rim[0]+0.05", md=2)), ""],
        ["4", "Bore", "Ø%s from Z 0 to %s (cap head), Ø%s from there to the top (cap flange)" % (
            n("lower bore", p.tube_id_low, "tube_id_low", md=1), n("cap seat Z", zs, "tube_step_z", md=1),
            n("upper bore", p.tube_id_up, "tube_id_up", md=1)), ""],
        ["5", "Light path", "top Z %s, %s below the PCB; ring LEDs at X %s and %s (%s gap)" % (
            n("tube top Z", zt, "Z_tube_top", md=1), n("tube top to PCB", p.Z_pcb_bot - zt, "Z_pcb_bot-Z_tube_top", md=1),
            n("LED3 X", p.X_main - p.ring_led_r, "X_main-ring_led_r", md=1), n("LED4 X", p.X_main + p.ring_led_r, "X_main+ring_led_r", md=1),
            n("LED to tube gap", p.tube_led_gap, "tube_led_gap", md=2)), ""],
    ]
    sh.table(28, 74, (7, 34, 112, 43), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  Reference drawing: the tube is part of FlashKa_print_kit.stl (JLC3DP), not a CNC part. Geometry per FlashKa_tube.step.",
             "2  The ring LEDs light the tube from below; the visible lit ring on the bottom face is the end face of the "
             "tube (Ø%s bore to Ø%s outside). The cap head Ø%s sits in the bore with %s per side." % (
                 num(p.tube_id_low, 1), num(p.tube_od, 1), num(p.main_cap[0], 1),
                 V("ring gap", (p.tube_id_low - p.main_cap[0]) / 2, "(tube_id_low-main_cap[0])/2", view="notes", md=2))]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 120, 2.0, 1.0)
    return sh, locals()


# --------------------------------------------------------------------------
# cross-check against the solids
# --------------------------------------------------------------------------
def audit(p, plain, lid_p, tube, cap_m, cap_s):
    """Ray probes into the STEP solids: the value written on the drawings (from P) against the solid."""
    R, RL, RT, RM, RS = Rays(plain.val()), Rays(lid_p.val()), Rays(tube.val()), Rays(cap_m.val()), Rays(cap_s.val())
    ih = p.inner_half
    rb, rl = (p.win_d + p.bore_clear) / 2, (p.las_d + p.las_clear) / 2
    nan = float("nan")

    def air(ivs, c):
        for a, b in zip(ivs, ivs[1:]):
            if a[1] - 1e-6 <= c <= b[0] + 1e-6:
                return a[1], b[0]
        return None

    def width(ivs, c):
        g = air(ivs, c)
        return g[1] - g[0] if g else nan

    def centre(ivs, c):
        g = air(ivs, c)
        return 0.5 * (g[0] + g[1]) if g else nan

    bb = plain.val().BoundingBox()
    probe("tray length", p.L, bb.xmax - bb.xmin)
    probe("tray width", p.W, bb.ymax - bb.ymin)
    probe("tray height (head block)", p.H, bb.zmax - bb.zmin)
    iv = R.y(2.0, p.Z_axis)
    probe("window bore diameter", 2 * rb, width(iv, p.Y_w))
    probe("window bore axis Y", p.Y_w, centre(iv, p.Y_w))
    probe("window bore floor X (depth D_w)", p.D_w, R.x(p.Y_w, p.Z_axis)[0][0])
    iz = R.z(2.0, p.Y_l)
    probe("laser bore diameter (Z span)", 2 * rl, width(iz, p.Z_las))
    probe("laser axis Z", p.Z_las, centre(iz, p.Z_las))
    iy = R.y(2.0, p.Z_las)
    probe("laser axis Y", p.Y_l, centre(iy, p.Y_l))
    ix = R.x(p.Y_l, 1.0)
    probe("M2 hole X", p.las_grub_x, centre(ix, p.las_grub_x))
    probe("PCB ledge height Z_pcb_bot", p.Z_pcb_bot, R.z(20.0, ih - 0.4)[0][1])
    probe("trough width between the ledges", 2 * (ih - p.ledge_w), width(R.y(20.0, p.Z_pcb_bot - 0.3), 0.0))
    probe("floor thickness (bay)", p.floor, R.z(60.0, 0.0)[0][1])
    probe("wall top at the lip seat (lid_lip_z)", p.lid_lip_z, R.z(60.0, 9.0)[0][1])
    # floor holes: main hole at Z 0.5, counterbore at Z 1.3, slide holes at Z 0.5 (X rays at Y = btn_y)
    ixm = R.x(p.btn_y, 0.5)
    probe("main hole diameter", p.main_hole, width(ixm, p.X_main))
    probe("main hole X", p.X_main, centre(ixm, p.X_main))
    probe("counterbore diameter", p.tube_rim[0] + 0.05, width(R.x(p.btn_y, 1.3), p.X_main))
    probe("slide hole SW2 diameter", p.slide_hole, width(R.x(p.btn_y, 0.8), p.X_next))
    probe("slide hole SW3 diameter", p.slide_hole, width(R.x(p.btn_y, 0.8), p.X_prev))
    fx0, fx1, fhy, fr = p.frw_box
    probe("floor RF window length", fx1 - fx0, width(R.x(0.0, 0.5), 0.5 * (fx0 + fx1)))
    probe("floor RF window width", 2 * fhy, width(R.y(0.5 * (fx0 + fx1), 0.5), 0.0))
    probe("lid thickness", p.lid_t, RL.z(60.0, 0.0)[0][1] - RL.z(60.0, 0.0)[0][0])
    probe("tube height", p.Z_tube_top, RT.z(p.X_main + 3.6, p.btn_y)[-1][1])
    probe("tube outer diameter", p.tube_od, RT.x(p.btn_y, 5.0)[-1][1] - RT.x(p.btn_y, 5.0)[0][0])
    probe("tube lower bore", p.tube_id_low, width(RT.x(p.btn_y, 1.8), p.X_main))
    probe("tube upper bore", p.tube_id_up, width(RT.x(p.btn_y, 5.0), p.X_main))
    zm = RM.z(p.X_main, p.btn_y)
    probe("main cap length (apex to stem end)", p.Z_sw_tip - p.cap_gap - p.cap_apex_z, zm[-1][1] - zm[0][0])
    probe("main cap head diameter", p.main_cap[0], RM.x(p.btn_y, 1.0)[-1][1] - RM.x(p.btn_y, 1.0)[0][0])
    zs = RS.z(p.X_next, p.btn_y)
    probe("slide cap length (apex to stem end)", p.Z_sw_tip - p.cap_gap - p.cap_apex_z, zs[-1][1] - zs[0][0])
    probe("slide cap flange diameter", p.slide_cap[1], RS.x(p.btn_y, p.floor + 0.3)[-1][1] - RS.x(p.btn_y, p.floor + 0.3)[0][0])


def dimension_table(path):
    """text file: every number written on the sheets against its value in P, and the solid cross-check"""
    uniq, order = {}, []
    for r in ROWS:
        k = (r["sheet"], r["what"], r["shown"], r["expr"])
        if k not in uniq:
            uniq[k] = dict(r, views=[r["view"]], n=1)
            order.append(k)
        else:
            uniq[k]["n"] += 1
            if r["view"] not in uniq[k]["views"]:
                uniq[k]["views"].append(r["view"])
    out = ["FlashKa Keychain housing %s drawings (%s): every number written on the sheets against its value in P" % (VER, DATE),
           "(%d entries, %d distinct; 'shown' = value as printed, tolerance 6e-4)" % (len(ROWS), len(uniq)), ""]
    w = (12, 46, 9, 44, 9, 4)
    head = "%-*s %-*s %*s  %-*s %*s  %s" % (w[0], "sheet", w[1], "what", w[2], "shown", w[3], "P expression", w[4],
                                          "P value", "ok")
    sheet = None
    for k in order:
        r = uniq[k]
        if r["sheet"] != sheet:
            sheet = r["sheet"]
            out += ["", "== %s" % sheet, head, "-" * len(head)]
        out.append("%-*s %-*s %*s  %-*s %*s  %s   [%s]" % (
            w[0], r["sheet"].split()[0] + " " + r["sheet"].split()[-1], w[1], r["what"][:w[1]], w[2], num(r["shown"]),
            w[3], r["expr"][:w[3]], w[4], num(r["pval"]), "ok" if r["ok"] else "MISMATCH", ", ".join(r["views"])))
    bad = [r for r in uniq.values() if not r["ok"]]
    out += ["", "numbers vs P: %d distinct entries, %d mismatches" % (len(uniq), len(bad)), ""]
    out += ["Cross-check against the STEP solids (ray probes): value of P / drawing against the solid", ""]
    h2 = "%-*s %9s %9s %8s  %s" % (84, "what", "P/drawing", "solid", "diff", "")
    out += [h2, "-" * len(h2)]
    for q in PROBES:
        flag = "ok" if q["ok"] else ("DIFFERS (known)" if q.get("known") else "MISMATCH")
        out.append("%-*s %9s %9s %8s  %s" % (84, q["what"][:84], num(q["drawn"], 3), num(q["measured"], 3),
                                          num(q["measured"] - q["drawn"], 3), flag))
    nb = [q for q in PROBES if not q["ok"] and not q.get("known")]
    nk = [q for q in PROBES if not q["ok"] and q.get("known")]
    out += ["", "solid probes: %d, mismatches %d, known differences from P %d" % (len(PROBES), len(nb), len(nk))]
    open(path, "w").write("\n".join(out) + "\n")
    return out, bad, nb


def main(out, housing_dir=None, table=True):
    os.makedirs(out, exist_ok=True)
    p = H.P()
    ROWS.clear()
    PROBES.clear()
    sh1, l1 = tray_sheet1(p, out, housing_dir)
    sh2, l2 = tray_sheet2(p, out, housing_dir)
    shl, l3 = lid_sheet(p, out, housing_dir)
    shm, l4 = cap_sheet(p, "main", out)
    shs, l5 = cap_sheet(p, "slide", out)
    sht, l6 = tube_sheet(p, out)
    findings = sum(sh.check() for sh in (sh1, sh2, shl, shm, shs, sht))
    p1 = sh1.save(os.path.join(out, "FlashKa_tray_drawing.dxf"), os.path.join(out, "_sheet1.pdf"))
    p2 = sh2.save(os.path.join(out, "FlashKa_tray_drawing_sheet2.dxf"), os.path.join(out, "_sheet2.pdf"))
    pdf = os.path.join(out, "FlashKa_tray_drawing.pdf")
    merge_pdfs([p1, p2], pdf)
    for tmp in (p1, p2):
        os.remove(tmp)
    png_from_pdf(pdf, 0, os.path.join(out, "FlashKa_tray_drawing.png"), dpi=150)
    png_from_pdf(pdf, 1, os.path.join(out, "FlashKa_tray_drawing_sheet2.png"), dpi=150)
    for sh, base in ((shl, "FlashKa_lid_drawing"), (shm, "FlashKa_cap_main_drawing"),
                     (shs, "FlashKa_cap_slide_drawing"), (sht, "FlashKa_tube_drawing")):
        pd = sh.save(os.path.join(out, base + ".dxf"), os.path.join(out, base + ".pdf"))
        png_from_pdf(pd, 0, os.path.join(out, base + ".png"), dpi=150)
    plain = H.build_tray(p, texture=False)
    lid_p = H.build_lid(p, texture=False)
    audit(p, plain, lid_p, H.build_tube(p), H.build_cap_main(p), H.build_cap_slide(p, p.X_next))
    lines, bad, nb = dimension_table(os.path.join(out, "drawings_dimension_table.txt"))
    print("\n".join(lines if table else lines[-3:]))
    print("layout findings: %d; number-vs-P mismatches: %d; solid mismatches: %d" % (findings, len(bad), len(nb)))
    return findings, bad, nb


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "cad", args[1] if len(args) > 1 else None, table="--quiet" not in sys.argv)
