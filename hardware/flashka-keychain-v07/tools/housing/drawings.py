#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
2D manufacturing drawings of the FlashKa Keychain v0.7 housing parts (DXF, plus PDF / PNG for people), generated
from the same parameters (class P in flashka_housing.py) as the STEP files.

  FlashKa_tray_drawing.dxf / _sheet2.dxf    FK-H-01 tray: sheet 1 interior (holes, threads, fits, key-board bosses),
                                           sheet 2 exterior (octagon facets, panels and texture, grooves, key bezel)
  FlashKa_tray_drawing.pdf (2 pages), .png (sheet 1), _sheet2.png
  FlashKa_lid_drawing.dxf / .pdf / .png     FK-H-02 lid
  FlashKa_key_main_drawing.*                FK-H-03 main key (clear PMMA, polished, frosted ring)
  FlashKa_key_side_drawing.*                FK-H-04 side key (cast rubber with a glued-in stiffener)
  FlashKa_pom_parts_drawing.*               FK-H-05 POM-C parts (RF window insert, antenna spacer, laser sleeve)
  FlashKa_pmma_kit_drawing.*                FK-H-06 machining kit: three PMMA main keys on tabs in a frame (JLCCNC)
  FlashKa_pom_kit_drawing.*                 FK-H-07 machining kit: one set of POM-C parts + a spare lid insert
  FlashKa_key_mould_drawing.*               FK-H-08 casting mould for the side keys (4 per pour): aluminium version
                                           (JLCCNC) with the resin version (JLC3DP) beside it
  drawings_dimension_table.txt             every number written on the sheets against its value in P, plus a
                                           cross-check against the solids (ray probes)

usage:  python3 drawings.py [out_dir] [housing_dir] [--quiet]   (A3 sheets; housing_dir = folder with
        housing_interface.json: the wall and texture numbers in the notes come from it).
Written into the package's cad folder, the PDFs are also copied into ../../order_files (under the names the order
READMEs use) and the dimension table into ../../docs/checks (order_files.py).
Environment: FK_CACHE=<dir> caches the (slow) hidden-line projections while the layout is being tuned.
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
DATE = "2026-10-23"
VER = "v0.7"
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
    def __init__(self, title, partno, sheet="1/1", size=(420, 297), scale_text="SCALE 2:1 (details as marked)",
                 tol_text="ISO 2768-mK"):
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
        self.scale_text = scale_text
        self.tol_text = tol_text
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
        part_lines = f"Part: {self.partno}".split("\n")
        if len(part_lines) == 1:
            self.text(part_lines[0], x0 + 3, y0 + 16, 3.0, track=False)
        else:                               # several STEP files: two smaller lines in the same cell
            for i, ln in enumerate(part_lines[:2]):
                self.text(ln, x0 + 3, y0 + 19.2 - i * 4.4, 2.2, track=False)
        self.text(f"FlashKa Keychain {VER}  {DATE}", x0 + 3, y0 + 4, 2.5, track=False)
        self.text(f"{self.scale_text}   SHEET {self.sheet}", x0 + 113, y0 + 16, 2.2, track=False)
        self.text(f"Units mm  |  {self.tol_text}", x0 + 113, y0 + 4, 2.5, track=False)

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
    rb = p.opt_bore / 2
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
    return comp, ((js or {}).get("texture_and_grooves") or [])


def make_V(nm):
    def V(what, val, expr, pval=None, dec=3, view="table", md=0, rnd=False):
        """a number written into a note, table or callout: registered against its P expression.
        rnd=True: a model result printed rounded to `dec` decimals on purpose (registered as round(value, dec))"""
        s_ = num(val, dec, md)
        pv = val if pval is None else pval
        if rnd:
            pv, expr = round(pv, dec), "%s, rounded to %d dec" % (expr, dec)
        reg(nm, view, what, float(s_), expr, pv)
        return s_
    return V



def tray_sheet1(p, out, housing_dir=None):
    """Sheet 1: interior, holes, threads, critical fits (the tray without the exterior panels)."""
    wp = H.build_tray(p, texture="none")
    tray = wp.val().wrapped
    sh = Sheet("MAIN BODY (TRAY)", "FK-H-01  FlashKa_tray.step", "1/2")
    nm = sh.name
    V = make_V(nm)
    L, ih = p.L, p.inner_half
    rb, rl = p.opt_bore / 2, (p.las_d + p.las_clear) / 2
    zs2 = p.Z_pcb_top + p.s2_knob_z
    gw, gd = p.wire_groove
    r_groove = rb + gd
    (yht, zht), (yhb, zhb) = H.led_wire_hole_yz(p)
    xht, xhb = H.led_wire_hole_x_end(p)
    a_w = math.radians(p.led_wire_ang)
    tdepth = p.m16_drill - 1.0
    walls, texw = thin_walls(p, housing_dir)
    xr0, xr1 = p.X_batt0 + 3.0, p.X_batt1 - 3.0                  # cell rails
    kr = H.key_rects(p, p.key_clear, p.key_clear_end)
    yb = p.kb_holes[0][1]
    th_kb = p.kb_z0 - p.kb_thread_z            # full thread length in a KB boss
    dr_kb = p.kb_z0 - p.kb_drill_z             # tap drill depth (cylindrical part)

    top = hlr(tray, (0, 0, 1), (1, 0, 0), "v7_t1_top")
    side_m = hlr(tray, (0, -1, 0), (1, 0, 0), "v7_t1_side_m")
    side_p = hlr(tray, (0, 1, 0), (-1, 0, 0), "v7_t1_side_p")
    front = hlr(tray, (-1, 0, 0), (0, -1, 0), "v7_t1_front")
    secA, hatA, _ = section_long(wp, p, p.Y_w, "A-A")
    secD, hatD, _ = section_long(wp, p, p.las_set[1], "D-D")
    secB, hatB, _ = section_trans(wp, p, p.X_main, "B-B")
    secC, hatC, _ = section_trans(wp, p, p.screw_x_front, "C-C")
    XE = 7.5                                     # section E-E: through the LED wire grooves (X 6.13 .. 8.83)
    secE, hatE, _ = section_trans(wp, p, XE, "E-E")
    XD, XS = 14.0, 32.0
    secD, hatD = clip_view(secD, u1=XD), clip_segs(hatD, u1=XD)
    side_m = clip_view(side_m, u1=XS)
    side_p = {k: clip_polys(v, u0=-XS) for k, v in side_p.items()}

    T = (28, 246)
    SM = (28, 149)
    SP = (216, 149)
    A = (28, 68)
    F = (272, 240)
    C = (356, 240)
    B = (272, 170)
    D = (336, 170)
    E = (122, 137)

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
    sh.view(secE, *E, "secE", hidden=False)
    sh.hatch(hatE, *E)
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
    sh.hdim(*T, p.L_head, -ih, p.kb_holes[0][0], -yb, -16, "KB bosses from the head block", "kb_holes[0][0]-L_head",
            p.kb_holes[0][0] - p.L_head)
    sh.hdim(*T, p.kb_holes[0][0], -yb, p.X_pcb1, -ih, -16, "bosses to the end of the ledges", "X_pcb1-kb_holes[0][0]",
            p.X_pcb1 - p.kb_holes[0][0])
    sh.hdim(*T, p.X_pcb1, -ih, p.X_batt1, -ih, -16, "antenna zone + cell bay", "X_batt1-X_pcb1",
            p.X_batt1 - p.X_pcb1)
    sh.hdim(*T, p.X_batt1, -ih, L, -10, -16, "tail (front wall + slot + end wall)", "L_tail", p.L_tail)
    sh.hdim(*T, 0, -10, L, -10, -22, "overall length", "L", p.L)
    sh.vdim(*T, L - p.tail_facet, -10, L - p.tail_facet, 10, L + 5, "width", "W", p.W)
    for (x, y) in ((p.screw_x_front, p.screw_dy), (p.screw_x_front, -p.screw_dy),
                   (p.X_screw_back, p.screw_dy), (p.X_screw_back, -p.screw_dy)) + tuple(p.kb_holes) + (tuple(p.las_set),):
        thread_symbol(sh, *T, x, y, 1.6)
    sh.cutline(*T, (0, p.Y_w), (L, p.Y_w), "A", (0, 1), ext=3.5, shaft=2.5)
    sh.cutline(*T, (0, p.las_set[1]), (L, p.las_set[1]), "D", (0, 1), ext=3.5, shaft=2.5)
    sh.cutline(*T, (p.X_main, -10), (p.X_main, 10), "B", (-1, 0), ext=3.5)
    sh.cutline(*T, (p.screw_x_front, -10), (p.screw_x_front, 10), "C", (-1, 0), ext=3.5)
    sh.text("TOP VIEW (from +Z, lid removed)   items 5-7, 9, 11-14", 28, 190, 3.0)
    sh.leader(*T, p.X_screw_back, p.screw_dy, -5, 16,
              ["(6) 4x M1.6x0.35-6H, thread %s" % V("thread depth", tdepth, "m16_drill-1.0", view="top"),
               "tap drill Ø%s x %s" % (V("tap drill", p.m16_tap, "m16_tap", view="top"),
                                       V("tap drill depth", p.m16_drill, "m16_drill", view="top"))], h=2.2)
    sh.leader(*T, 60.0, p.rail_y + p.rail_w / 2, 6, -7,
              "(12) 2x cell rail, 2x front relief Ø%s" % V(
                  "front relief dia", p.front_relief[0], "front_relief[0]", view="top", md=1), h=2.2)
    sh.leader(*T, p.kb_holes[0][0] + 1.2, yb + 1.2, 10, 9, "(13) 2x KB boss, see B-B", h=2.2)

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
    sh.leader(*SP, -p.X_s2, zs2 + s2h / 2, -8, 22,
              ["(10) S2 slot, THRU",
               "%s x %s R%s +/-0.1" % (V("S2 slot width", s2w, "s2_slot[0]", view="side_p", md=1),
                                        V("S2 slot height", s2h, "s2_slot[1]", view="side_p", md=1),
                                        V("S2 slot radius", s2r, "s2_slot[2]", view="side_p", md=1)),
               "centre Z %s" % V("S2 slot centre Z", zs2, "Z_pcb_top+s2_knob_z", view="side_p")], h=2.2)
    sh.text("SIDE VIEW from +Y (laser side)   item 10", 152, 123, 3.0)

    # ------------------------------------------------------------ section A-A
    sh.cur = "secA"
    sh.hdim(*A, 0, p.H, p.D_w, p.Z_axis + rb, 22, "optic bore depth", "D_w", p.D_w, "<> +/-0.05")
    sh.vdim(*A, 2.5, p.Z_axis - rb, 2.5, p.Z_axis + rb, 2.5, "optic bore diameter", "opt_bore",
            2 * rb, "%%c<>")
    sh.vdim(*A, 60, p.floor, 60, p.Z_lid, 60, "cavity depth (floor to lid seat)", "Z_lid-floor",
            p.Z_lid - p.floor)
    sh.vdim(*A, p.X_pcb1, 0, p.X_pcb1, p.Z_pcb_bot, p.X_pcb1 + 9, "PCB ledge height", "Z_pcb_bot",
            p.Z_pcb_bot, "<> +/-0.05", shift=9)
    sh.leader(*A, p.D_w, p.Z_axis - 0.6 * rb, 6, -21.4, "(1) optic bore, flat floor", h=2.2)
    sh.cutline(*A, (XE, -1.0), (XE, p.H + 1.0), "E", (-1, 0), ext=2.5, shaft=2.0)
    sh.text("SECTION A-A  (Y = %s, optic axis)   items 1, 7, 11" % num(p.Y_w), 112, 52, 3.0)

    # ------------------------------------------------------------ front view
    sh.cur = "front"
    fb, fs = p.W / 2 - p.C_edge, p.C_edge          # bottom facet half width, side facet bottom Z
    sh.hdim(*F, -p.W / 2, fs, -p.Y_l, p.Z_las, -6, "laser axis from the +Y face", "W/2-Y_l", p.W / 2 - p.Y_l)
    sh.hdim(*F, -p.Y_l, p.Z_las, -p.Y_w, p.Z_axis, -6, "optic axis to laser axis", "Y_l-Y_w", p.Y_l - p.Y_w)
    sh.hdim(*F, -p.Y_w, p.Z_axis, p.W / 2, fs, -6, "optic axis from the control face", "W/2+Y_w", p.W / 2 + p.Y_w)
    sh.vdim(*F, -fb, 0, -p.Y_l, p.Z_las, -14, "laser axis height", "Z_las", p.Z_las)
    sh.vdim(*F, fb, 0, -p.Y_w, p.Z_axis, 14, "optic axis height", "Z_axis", p.Z_axis)
    sh.vdim(*F, fb, 0, fb, p.H, 20, "height", "H", p.H)
    sh.center(*F, -p.Y_w, p.Z_axis, rb)
    sh.center(*F, -p.Y_l, p.Z_las, rl)
    a45 = math.radians(45)
    sh.leader(*F, -p.Y_w + rb * math.cos(a45), p.Z_axis + rb * math.sin(a45), 8, 14,
              "(1) Ø%s +0.05/0" % V("optic bore diameter", 2 * rb, "opt_bore", view="front"), h=2.2)

    sh.leader(*F, -p.Y_l - rl * math.cos(a45), p.Z_las + rl * math.sin(a45), -4, 22,
              "(4) Ø%s +0.05/0" % V("laser bore diameter", 2 * rl, "las_d+las_clear", view="front"), h=2.2)
    sh.text("FRONT VIEW (from -X)   items 1-4", 246, 217.5, 3.0)

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
    for (yh_, zh_) in ((yht, zht), (yhb, zhb)):
        sh.center(*C, yh_, zh_, p.ledwire_d / 2)
    sh.leader(*C, yhb, zhb - p.ledwire_d / 2, -6, -10, "(3) 2x Ø%s" % V(
        "LED wire hole diameter", p.ledwire_d, "ledwire_d", view="secC"), h=2.2)
    sh.leader(*C, p.Y_l, p.Z_las - rl, 4, -10, "(4) Ø%s +0.05/0" % V(
        "laser bore diameter", 2 * rl, "las_d+las_clear", view="secC"), h=2.2)
    sh.text("SECTION C-C  (X = %s)   items 3, 4, 6" % num(p.screw_x_front), 318, 217.5, 3.0)

    # ------------------------------------------------------------ section E-E (through the LED wire grooves; u = Y)
    sh.cur = "secE"
    rgm = rb + gd / 2
    sh.center(*E, p.Y_w, p.Z_axis, rb)
    sh.leader(*E, p.Y_w + rgm * math.sin(a_w), p.Z_axis + rgm * math.cos(a_w), 6, 7, "(2) 2x groove", h=2.0)
    sh.leader(*E, p.Y_w - rb * math.cos(a45), p.Z_axis - rb * math.sin(a45), -9, -6,
              "(1) Ø%s" % V("optic bore diameter", 2 * rb, "opt_bore", view="secE"), h=2.0)
    sh.text("SECTION E-E  (X = %s)   items 1, 2" % num(XE, 1), 98, 129.5, 3.0)

    # ------------------------------------------------------------ section B-B (through the main key and the KB bosses)
    sh.cur = "secB"
    sh.hdim(*B, -ih, p.Z_lid, ih, p.Z_lid, 19, "cavity width", "2*(W/2-wall)", 2 * ih)
    sh.hdim(*B, -10, 7.0, 10, 7.0, -6.5, "width", "W", p.W)
    sh.hdim(*B, kr["main"][2], p.floor, kr["main"][3], p.floor, -2.6, "main key opening (Y)", "main_key[1]+2*key_clear",
            kr["main"][3] - kr["main"][2], "<> +0.05/0")
    sh.vdim(*B, p.W / 2 - p.C_edge, 0, 7.9, p.Z_pcb_bot, 13.5, "PCB ledge height", "Z_pcb_bot", p.Z_pcb_bot,
            "<> +/-0.05")
    sh.vdim(*B, -yb, 0, -yb, p.kb_z0, -12.5, "KB boss top", "kb_z0", p.kb_z0, "<> +/-0.03", shift=4.5)
    sh.vdim(*B, -(p.W / 2 - p.C_edge), 0, -p.W / 2, p.Z_lid, -16.5, "lid seat height", "Z_lid", p.Z_lid)
    for sg in (-1, 1):
        for dx in (-0.8, 0.8):
            sh.msp.add_line(sh.P(*B, sg * yb + dx, p.kb_z0), sh.P(*B, sg * yb + dx, p.kb_thread_z),
                            dxfattribs={"layer": "HATCH"})
    sh.leader(*B, yb + 0.625, p.kb_z0 - 0.6, 7.5, 14,
              ["(13) 2x M1.6x0.35-6H BLIND",
               "thread %s, drill Ø%s x %s" % (V("KB tap thread length", th_kb, "kb_z0-kb_thread_z", view="secB"),
                                               V("KB tap drill", p.m16_tap, "m16_tap", view="secB"),
                                               V("KB tap drill depth", dr_kb, "kb_z0-kb_drill_z", view="secB"))], h=2.0)
    sh.text("SECTION B-B  (X = %s)   items 7, 9, 11, 13" % num(p.X_main), 242, 147, 3.0)

    # ------------------------------------------------------------ section D-D (through the laser set screw)
    sh.cur = "secD"
    xs, zsb = p.las_set[0], p.las_set_bore_z
    sh.hdim(*D, 0, p.H, xs, p.Z_lid, p.H + 2.5, "laser set screw from the front face", "las_set[0]", xs)
    sh.vdim(*D, 0, 0, 0, p.Z_las, -5, "laser axis height", "Z_las", p.Z_las)
    for dx in (-0.8, 0.8):
        sh.msp.add_line(sh.P(*D, xs + dx, p.Z_lid), sh.P(*D, xs + dx, zsb), dxfattribs={"layer": "HATCH"})
    sh.leader(*D, xs + 0.6, p.Z_lid - 0.7, 17, 10,
              ["(5) M1.6x0.35-6H from the top",
               "(under the lid), thread %s" % V("laser set-screw thread length", p.Z_lid - zsb, "Z_lid-las_set_bore_z",
                                                view="secD"),
               "drill Ø%s; set screw M1.6 x %s" % (
                   V("laser set-screw tap drill", p.m16_tap, "m16_tap", view="secD"),
                   V("laser set screw length", p.las_set_len, "las_set_len", view="secD", md=0))], h=2.0)
    sh.leader(*D, 7.5, p.Z_las + 1.0, 16, -22, ["(4) laser bore Ø%s +0.05/0," % V(
        "laser bore diameter", 2 * rl, "las_d+las_clear", view="secD"), "open to the cavity from X %s" % V(
        "head block length", p.L_head, "L_head", view="secD")], h=2.0)
    sh.text("SECTION D-D  (Y = %s)   items 4, 5" % num(p.las_set[1]), 332, 147, 3.0)

    # ------------------------------------------------------------ feature table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    sx = kr["next"][1] - kr["next"][0]
    sy = kr["next"][3] - kr["next"][2]
    mxo = kr["main"][1] - kr["main"][0]
    ribs = sorted(set(x for x, _ in p.kb_ribs))
    rows = [
        ["1", "Optic bore (front)",
         "Ø%s x %s deep, flat floor; axis Y %s, Z %s = %s from the\ncontrol-side face; centres the TIR optic and the LED board" % (
             n("optic bore dia", 2 * rb, "opt_bore", md=1), n("optic bore depth", p.D_w, "D_w"),
             n("optic axis Y", p.Y_w, "Y_w"), n("optic axis Z", p.Z_axis, "Z_axis", md=1),
             n("optic axis from the control face", p.W / 2 + p.Y_w, "W/2+Y_w")),
         "Ø +0.05/0; depth +/-0.05\nfloor flat 0.03, Ra 1.6"],
        ["2", "LED wire grooves 2x",
         "in the bore wall, %s deg from 12 and 6 o'clock (upper one towards +Y):\n%s wide, bottom R%s from the axis, X %s to %s (bore floor)" % (
             n("LED wire groove angle from vertical", p.led_wire_ang, "led_wire_ang", md=0),
             n("groove width", gw, "wire_groove[0]", md=1), n("groove bottom radius", r_groove, "opt_bore/2+wire_groove[1]"),
             n("groove start X", p.x_led_board - 1.0, "x_led_board-1.0", md=1), n("groove end X", p.D_w, "D_w")),
         "+/-0.1"],
        ["3", "LED wire holes 2x",
         "Ø%s on the groove lines, R%s from the axis; upper: Y %s, Z %s,\nto X %s; lower: Y %s, Z %s, to X %s (cavity corner)" % (
             n("wire hole dia", p.ledwire_d, "ledwire_d", md=1), n("wire hole radius from the axis", p.led_wire_r, "led_wire_r", md=1),
             n("upper wire hole Y", yht, "Y_w+led_wire_r*sin(led_wire_ang)"),
             n("upper wire hole Z", zht, "Z_axis+led_wire_r*cos(led_wire_ang)", dec=2, rnd=True),
             n("upper wire hole end X", xht, "led_wire_hole_x_end[0]", dec=2, rnd=True),
             n("lower wire hole Y", yhb, "Y_w-led_wire_r*sin(led_wire_ang)"),
             n("lower wire hole Z", zhb, "Z_axis-led_wire_r*cos(led_wire_ang)", dec=2, rnd=True),
             n("lower wire hole end X", xhb, "led_wire_hole_x_end[1]", dec=2, rnd=True)),
         "+/-0.1"],
        ["4", "Laser bore (front)",
         "Ø%s, axis Y %s (%s from the +Y face), Z %s; open to the\ncavity at X %s (module Ø%s x %s, recess %s)" % (
             n("laser bore dia", 2 * rl, "las_d+las_clear", md=1), n("laser axis Y", p.Y_l, "Y_l"),
             n("laser axis from the +Y face", p.W / 2 - p.Y_l, "W/2-Y_l"), n("laser axis Z", p.Z_las, "Z_las", md=1),
             n("head block length", p.L_head, "L_head", md=1), n("laser module diameter", p.las_d, "las_d"),
             n("laser module length", p.las_len, "las_len"), n("laser recess", p.las_recess, "las_recess")),
         "Ø +0.05/0; axis +/-0.05"],
        ["5", "Laser set-screw hole (top)",
         "M1.6x0.35-6H from the head-block top (under the lid) into the\nlaser bore, X %s, Y %s; tap drill Ø%s, thread %s" % (
             n("laser set screw X", p.las_set[0], "las_set[0]", md=1), n("laser set screw Y", p.las_set[1], "las_set[1]", md=1),
             n("laser set-screw tap drill", p.m16_tap, "m16_tap"),
             n("laser set-screw thread length", p.Z_lid - p.las_set_bore_z, "Z_lid-las_set_bore_z")),
         "6H; position +/-0.1\nhidden under the lid"],
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
        ["9", "Key openings 3x (floor)",
         "through, centres X %s / %s / %s, Y %s;\nside keys %s x %s R%s, main key %s x %s R%s; bezel: sheet 2" % (
             n("next key X", p.X_next, "X_next", md=1), n("main key X", p.X_main, "X_main", md=1),
             n("prev key X", p.X_prev, "X_prev", md=1), n("key Y", p.key_y, "key_y", md=1),
             n("side key opening X", sx, "side_key[0]+2*key_clear", md=1), n("side key opening Y", sy, "side_key[1]+2*key_clear_end", md=1),
             n("side key opening radius", kr["next"][4], "side_key[2]+key_clear", md=1),
             n("main key opening X", mxo, "main_key[0]+2*key_clear", md=1), n("main key opening Y", kr["main"][3] - kr["main"][2], "main_key[1]+2*key_clear", md=1),
             n("main key opening radius", kr["main"][4], "main_key[2]+key_clear", md=1)),
         "+0.05/0; position +/-0.05\nedges sharp inside"],
        ["10", "S2 slot (+Y wall)",
         "%s x %s R%s through; centre X %s, Z %s" % (
             n("S2 slot width", p.s2_slot[0], "s2_slot[0]", md=1), n("S2 slot height", p.s2_slot[1], "s2_slot[1]", md=1),
             n("S2 slot radius", p.s2_slot[2], "s2_slot[2]", md=1), n("S2 X", p.X_s2, "X_s2"),
             n("S2 slot centre Z", zs2, "Z_pcb_top+s2_knob_z", md=1)),
         "+/-0.1"],
        ["11", "Cavity",
         "%s wide (%s walls), floor Z %s, lid seat Z %s, vertical corners R%s;\n45 deg floor corners (%s walls), trough %s between the ledges" % (
             n("cavity width", 2 * ih, "2*(W/2-wall)", md=1), n("wall", p.wall, "wall", md=1),
             n("floor Z", p.floor, "floor", md=1), n("lid seat Z", p.Z_lid, "Z_lid", md=1),
             n("inner corner radius", p.inner_r, "inner_r", md=1), n("diagonal wall", p.wall, "wall", md=1),
             n("trough width", 2 * (ih - p.ledge_w), "2*(inner_half-ledge_w)", md=1)),
         "+/-0.1"],
        ["12", "Cell rails 2x, front reliefs 2x",
         "rails |Y| %s to %s, top Z %s, X %s to %s (the cell rests on the\ninner edges); front reliefs Ø%s, Z %s up, X %s, Y +/- %s" % (
             n("rail inner Y", p.rail_y, "rail_y", md=1), n("rail outer Y", p.rail_y + p.rail_w, "rail_y+rail_w", md=1),
             n("rail top Z", p.floor + p.rail_h, "floor+rail_h", md=1), n("rail start X", xr0, "X_batt0+3.0"),
             n("rail end X", xr1, "X_batt1-3.0"),
             n("front relief dia", p.front_relief[0], "front_relief[0]", md=1),
             n("front relief bottom Z", p.Z_pcb_bot, "Z_pcb_bot", md=1),
             n("front relief X", p.L_head + p.front_relief[1], "L_head+front_relief[1]"),
             n("front relief Y", ih - p.front_relief[2], "inner_half-front_relief[2]", md=1)),
         "rails top +/-0.05\nreliefs +/-0.1"],
        ["13", "Key-board bosses 2x",
         "Ø%s at X %s, Y +/- %s, joined to the trough wall, top Z %s; M1.6\nblind: drill Ø%s to Z %s, thread to Z %s (screw M1.6 x %s)" % (
             n("boss dia", p.boss_d, "boss_d", md=1), n("boss X", p.kb_holes[0][0], "kb_holes[0][0]", md=1),
             n("boss Y", abs(yb), "kb_holes[0][1]", md=1), n("boss top Z", p.kb_z0, "kb_z0", md=1),
             n("KB tap drill", p.m16_tap, "m16_tap"), n("KB drill end Z", p.kb_drill_z, "kb_drill_z"),
             n("KB thread end Z", p.kb_thread_z, "kb_thread_z"), n("KB screw length", p.kb_screw_len, "kb_screw_len", md=1)),
         "top Z +/-0.03, flat 0.02\nno break-through"],
        ["14", "Key-board ribs 4x",
         "%s wide at X %s, |Y| %s to the trough wall; top Z %s;\n-Y at X %s (USB-C gap): free post |Y| %s to %s" % (
             n("rib width", p.rib_w, "rib_w", md=1), " and ".join(num(x, 1) for x in ribs),
             n("rib inner Y", p.rib_y0, "rib_y0", md=1), n("rib top Z", p.kb_z0, "kb_z0", md=1),
             n("free post X", ribs[0], "kb_ribs[0][0]", md=1), n("free post inner Y", p.rib_y0, "rib_y0", md=1),
             n("free post outer Y", p.kb_y - 0.3, "kb_y-0.3", md=1)),
         "coplanar with 13\nwithin 0.03"],
    ]
    sh.table(234, 141, (7, 36, 86, 45), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)

    # ------------------------------------------------------------ notes
    t = lambda k: walls[k]
    NW = 96.0
    notes_a = [
        "NOTES",
        "1  Material: aluminium 6061-T6. Geometry per FlashKa_tray.step; this sheet adds threads, fits, "
        "finish and notes. Exterior (octagon facets, panels, texture, grooves, key bezel, floor RF window, "
        "tail): sheet 2. Lid: drawing FK-H-02.",
        "2  General tolerances ISO 2768-mK; toleranced values are critical.",
        "3  Threads are tapped before anodising and gauged after finishing. The two key-board taps (13) are "
        "blind: do not drill through the floor.",
        "4  Break all sharp edges 0.05-0.1. Deburr the USB-C and S2 openings, the key openings from inside and "
        "the optic bore edge: the TIR optic (Ø%s) and the LED board (Ø%s) must drop in; the bore centres both." % (
            V("optic diameter", p.opt_od, "opt_od", view="notes", md=1),
            V("LED board diameter", p.mcpcb_d, "mcpcb_d", view="notes", md=1)),
        "5  Finish: fine glass-bead blast, then anodise type II matte black (8-12 um). Tolerances apply "
        "after finishing. No marking of any kind.",
    ]
    notes_b = [
        "6  Optic bore floor (X %s) is the LED board contact face (heat path): flat 0.03, Ra 1.6, no burr or "
        "anodise step." % V("bore floor X", p.D_w, "D_w", view="notes"),
        "7  Thin walls in the STEP (mm; none below 0.5): %s optic bore to control face; %s laser bore to +Y face; "
        "%s front tap to head back face and %s to the optic bore floor (%s and %s at the thread crest); %s upper "
        "LED wire groove (2) to the head-block top; %s tail front wall; %s floor under "
        "the key bezel; %s floor web between two key openings; %s metal under a key-board tap drill. "
        "Finish them in a light last pass." % (
            V("wall optic bore - control face", t("optic bore to control-side face"), "min_walls", view="notes"),
            V("wall laser bore - +Y face", t("laser bore to laser-side face"), "min_walls", view="notes", md=1),
            V("wall front tap - head back face", t("front screw tap to head rear face"), "min_walls", view="notes"),
            V("wall front tap - bore floor", t("wall front lid tap -Y - optic bore"), "min_walls", view="notes"),
            V("wall front tap crest - head back face", t("front screw tap to head rear face (thread crest)"), "min_walls",
              view="notes", md=1),
            V("wall front tap crest - bore floor", t("front screw tap to the optic bore floor (thread crest)"), "min_walls",
              view="notes"),
            V("wall upper LED wire groove - head-block top", t("LED wire groove (upper) to lid seat"), "min_walls",
              view="notes"),
            V("wall tail front", t("tail front wall (bay to slot)"), "min_walls", view="notes", md=1),
            V("wall floor under the bezel", t("floor under the key bezel"), "min_walls", view="notes", md=1),
            V("wall floor web", t("floor web: next opening to main opening"), "min_walls", view="notes", md=1),
            V("wall under the KB tap", t("KB tap: metal under the drill point to the bottom face"), "min_walls", view="notes")),
        "8  Inner vertical corners R%s (pocket %s deep); the front corner reliefs (12) are intended. "
        "The tops of the bosses (13) and ribs (14) carry the key board: machine them in one setup." % (
            V("inner corner radius", p.inner_r, "inner_r", view="notes", md=1),
            V("pocket depth", p.Z_lid - p.floor, "Z_lid-floor", view="notes", md=1)),
        "9  Sections: A-A at Y %s (optic axis), D-D at Y %s (laser set screw), B-B at X %s (main key, bosses), "
        "C-C at X %s (front taps, LED wire holes)." % (V("section A-A plane", p.Y_w, "Y_w", view="notes"),
                                        V("section D-D plane", p.las_set[1], "las_set[1]", view="notes"),
                                        V("section B-B plane", p.X_main, "X_main", view="notes", md=1),
                                        V("section C-C plane", p.screw_x_front, "screw_x_front", view="notes", md=1)),
    ]
    lines_a = [ln for n_ in notes_a for ln in wrap(n_, NW, 2.0)]
    lines_b = [ln for n_ in notes_b for ln in wrap(n_, NW, 2.0)]
    sh.mtext(lines_a, 28, 47, 2.0, 1.0)
    sh.mtext(lines_b, 128, 47, 2.0, 1.0)
    return sh, locals()


def vgroove_profile(depth, pitch=None, n=1, ext=0.9, h=0.6, recess=0.0):
    """schematic section of 90 deg V grooves (u across, v into the material), optionally n grooves at `pitch`
    below a recess"""
    pts = [(-ext, -recess)]
    if n == 1:
        pts += [(-depth, -recess), (0.0, depth - recess), (depth, -recess)]
    else:
        for k in range(n):
            c = (k - (n - 1) / 2) * pitch
            pts += [(c - depth, -recess), (c, depth - recess), (c + depth, -recess)]
    pts += [(ext, -recess), (ext, h), (-ext, h)]
    if recess:
        pts = [(-ext - 0.6, 0.0)] + [(-ext, 0.0)] + pts + [(-ext - 0.6, h)]
        pts = [q for q in pts]
    return {"vis": [pts + [pts[0]]]}, hatch_segments([pts], 0.15)


def tray_sheet2(p, out, housing_dir=None):
    """Sheet 2: exterior - chamfer frame, recessed panels with the V texture, transverse grooves, key bezel, floor
    RF window, tail window, lanyard slot."""
    tex = H.build_tray(p, texture="panels")
    sh = Sheet("MAIN BODY (TRAY) - EXTERIOR", "FK-H-01  FlashKa_tray.step", "2/2")
    nm = sh.name
    V = make_V(nm)
    L = p.L
    xw0, xw1 = tail_window_x(p)
    xs0 = p.X_lan - p.lan_slot_w / 2
    hy, kc = p.twin_y / 2, p.twin_corner
    fx0, fx1, fhy, fr = p.frw_box
    kr = H.key_rects(p, p.bez_margin)
    bx0, bx1, by1 = kr["next"][0] - p.bez_depth, kr["prev"][1] + p.bez_depth, kr["next"][3] + p.bez_depth
    lay = {q["name"]: q for q in H.panel_layout(p)}
    b1, b2 = lay["bottom bay 1 (with the RF window)"], lay["bottom bay 2"]
    sm1, sm2, smp = lay["minus_y bay 1"], lay["minus_y bay 2"], lay["minus_y PCB zone"]

    bottom = hlr(tex.val().wrapped, (0, 0, -1), (1, 0, 0), "v7_t2_bottom")     # u = X, v = -Y
    side_m = hlr(tex.val().wrapped, (0, -1, 0), (1, 0, 0), "v7_t2_side_m")      # u = X, v = Z
    secK, hatK, _ = section_long(tex, p, p.key_y, "K-K", spacing=0.25)          # keys + bezel, Y 0
    KW = (12.0 + H.PCB_DX, 34.6 + H.PCB_DX, -0.2, 5.0)        # round the three keys
    secK, hatK = clip_view(secK, u0=KW[0], u1=KW[1], v0=KW[2], v1=KW[3]), clip_segs(hatK, *KW)
    secV, hatV = vgroove_profile(p.tex_depth, p.tex_pitch, n=3, ext=1.6, h=0.8, recess=0.0)
    secG, hatG = vgroove_profile(p.grv_depth, ext=0.9, h=0.8)

    B = (28, 250)
    SM = (28, 160)
    KS = 6.0
    K = (40 - KS * KW[0], 76.2)
    VD = (330, 254)
    GD = (330, 200)
    sh.view(bottom, *B, "bottom", hidden=False)
    sh.view(side_m, *SM, "side_m", hidden=False)
    sh.view(secK, *K, "secK", hidden=False, scale=KS)
    sh.hatch(hatK, *K)
    sh.frame(*K, *KW)
    sh.view(secV, *VD, "secV", hidden=False, scale=25.0)
    sh.hatch(hatV, *VD)
    sh.view(secG, *GD, "secG", hidden=False, scale=25.0)
    sh.hatch(hatG, *GD)

    # ------------------------------------------------------------ bottom view (v = -Y)
    sh.cur = "bottom"
    row = -15
    sh.hdim(*B, 0, -10, p.X_next, 0, row, "next key from the front face", "X_next", p.X_next)
    sh.hdim(*B, p.X_next, 0, p.X_main, 0, row, "main key from the next key", "X_main-X_next", p.X_main - p.X_next)
    sh.hdim(*B, p.X_main, 0, p.X_prev, 0, row, "previous key from the main key", "X_prev-X_main", p.X_prev - p.X_main)
    sh.hdim(*B, p.X_prev, 0, fx0, -fhy, row, "floor RF window from the previous key", "frw_box[0]-X_prev", fx0 - p.X_prev)
    sh.hdim(*B, fx0, -fhy, fx1, -fhy, row, "floor RF window length", "frw_box[1]-frw_box[0]", fx1 - fx0)
    sh.hdim(*B, b1["u0"], -fhy, b1["u1"], -7.0, row - 6, "bottom panel 1 length", "panel_layout", b1["u1"] - b1["u0"])
    sh.hdim(*B, b2["u0"], -7.0, b2["u1"], -7.0, row - 6, "bottom panel 2 length", "panel_layout", b2["u1"] - b2["u0"])
    sh.vdim(*B, bx0, -by1, bx0, by1, bx0 - 2.0, "bezel width (at the face)", "bezel", 2 * by1)
    xp2 = 0.5 * (b2["u0"] + b2["u1"])
    sh.vdim(*B, xp2, -b2["v1"], xp2, -b2["v0"], xp2, "panel width", "2*(W/2-C_edge-rail)", b2["v1"] - b2["v0"])
    sh.vdim(*B, p.X_lan, -hy, p.X_lan, hy, L + 5, "tail window width", "twin_y", p.twin_y)
    sh.vdim(*B, xs0, -p.lan_slot_len / 2, xs0, p.lan_slot_len / 2, xs0 - 1.9, "lanyard slot length",
            "lan_slot_len", p.lan_slot_len)
    for x in (p.X_next, p.X_main, p.X_prev):
        sh.center(*B, x, 0, 0.5)
    # leaders leave the view upwards (above the view: the +v side)
    sh.leader(*B, p.X_main, p.main_key[1] / 2 + p.key_clear, -6, 17.2, "(9) key openings: sheet 1, item 9", h=2.2)
    sh.leader(*B, 0.5 * (fx0 + fx1), fhy - 0.4, 4, 10.8,
              "(20) RF window %s x %s R%s, POM plug" % (V("floor RF window length", fx1 - fx0, "frw_box[1]-frw_box[0]",
                                                          view="bottom", md=1),
                                                        V("floor RF window width", 2 * fhy, "2*frw_box[2]", view="bottom", md=1),
                                                        V("floor RF window radius", fr, "frw_box[3]", view="bottom", md=1)),
              h=2.2)
    sh.text("BOTTOM VIEW (from -Z)   items 15-23   (transverse groove positions: table, item 18)", 28, 281, 3.0)

    # ------------------------------------------------------------ side view -Y
    sh.cur = "side_m"
    sh.vdim(*SM, L, 0, sm2["u1"], sm2["v0"], L + 5.0, "side panel bottom Z", "C_edge+rail", sm2["v0"])
    sh.vdim(*SM, L, 0, sm2["u1"], sm2["v1"], L + 10.0, "side panel top Z", "Z_lid-rail", sm2["v1"])
    sh.vdim(*SM, 0, 0, 0, p.H, -6, "height", "H", p.H)
    sh.hdim(*SM, 0, 0, smp["u0"], sm1["v0"], -7, "side PCB-zone panel start", "panel_layout", smp["u0"])
    sh.hdim(*SM, smp["u0"], sm1["v0"], smp["u1"], sm1["v0"], -7, "side PCB-zone panel length", "panel_layout",
            smp["u1"] - smp["u0"])
    sh.hdim(*SM, sm1["u0"], sm1["v0"], sm1["u1"], sm1["v0"], -7, "side bay panel length", "panel_layout",
            sm1["u1"] - sm1["u0"])
    sh.hdim(*SM, sm1["u1"], sm1["v0"], sm2["u0"], sm2["v0"], -7, "band between the bay panels", "band", sm2["u0"] - sm1["u1"],
            shift=4.5)
    sh.text("SIDE VIEW from -Y (the +Y side is the mirror image, its PCB-zone panel starts at X %s)   items 15-18"
            % V("+Y PCB-zone panel start", lay["plus_y PCB zone"]["u0"], "panel_layout", view="side_m"), 28, 139, 3.0)

    # ------------------------------------------------------------ section K-K (keys, Y 0)
    sh.cur = "secK"
    sh.vdim(*K, kr["next"][0] - 0.2, 0, kr["next"][0] - 0.2, p.bez_depth, KW[0] - 0.8, "bezel depth",
            "bez_depth", p.bez_depth, "<> +/-0.05")
    sh.vdim(*K, KW[1] - 0.6, 0, KW[1] - 0.6, p.floor, KW[1] + 1.0, "floor", "floor", p.floor)
    sh.hdim(*K, bx0, 0, bx1, 0, -1.6, "bezel length (at the face)", "bezel", bx1 - bx0)
    sh.text("SECTION K-K  (Y = %s, keys removed, %d:1)   items 9, 19" % (num(p.key_y, 1), KS), 28, 60, 3.0)
    # ------------------------------------------------------------ details
    sh.cur = "secV"
    sh.hdim(*VD, p.tex_pitch - p.tex_depth, 0, p.tex_pitch + p.tex_depth, 0, -0.35, "texture groove width",
            "2*tex_depth", 2 * p.tex_depth)
    sh.hdim(*VD, -p.tex_pitch, 0, 0, 0, -0.9, "texture pitch", "tex_pitch", p.tex_pitch)
    sh.vdim(*VD, p.tex_pitch, 0, p.tex_pitch, p.tex_depth, 2.05, "texture groove depth", "tex_depth",
            p.tex_depth, "<> +/-0.03")
    sh.text("DETAIL T  (panel texture, 90 deg V, 25:1)   item 17", 300, 279, 3.0)
    sh.cur = "secG"
    sh.hdim(*GD, -p.grv_depth, 0, p.grv_depth, 0, -0.6, "transverse groove width", "2*grv_depth", 2 * p.grv_depth)
    sh.vdim(*GD, p.grv_depth, 0, p.grv_depth, p.grv_depth, 1.35, "transverse groove depth", "grv_depth",
            p.grv_depth, "<> +/-0.03")
    sh.text("DETAIL G  (transverse groove, 90 deg V, 25:1)   item 18", 300, 225, 3.0)

    # ------------------------------------------------------------ table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    rows = [
        ["15", "Octagon section",
         "%s x %s, 45 deg legs %s: bottom / top facets %s, sides %s, diagonals %s;\nfront outline C%s, tail outline C%s; flat lid joint at Z %s (upper facet edges)" % (
             n("width", p.W, "W"), n("height", p.H, "H"), n("facet leg", p.C_edge, "C_edge", md=1),
             n("bottom facet width", p.W - 2 * p.C_edge, "W-2*C_edge", md=1),
             n("side facet height", p.H - 2 * p.C_edge, "H-2*C_edge", md=1),
             n("diagonal facet width", p.C_edge * math.sqrt(2), "C_edge*sqrt2", dec=2, rnd=True),
             n("front outline chamfer", p.C_front, "C_front", md=1),
             n("tail outline chamfer", p.C_end, "C_end", md=1), n("lid seat Z", p.Z_lid, "Z_lid", md=1)),
         "ISO 2768-mK"],
        ["16", "Recessed panels",
         "%s deep, corners R%s; frame bands %s, rails %s along the facet edges;\nbottom: 2 panels, sides: 3 panels (layout in housing_interface.json)" % (
             n("panel depth", p.pan_depth, "pan_depth", md=1), n("panel corner radius", p.pan_r, "pan_r", md=1),
             n("frame band", p.band, "band", md=1), n("rail", p.rail, "rail", md=1)),
         "depth +/-0.03\nposition +/-0.1"],
        ["17", "Panel texture",
         "90 deg V grooves %s deep (%s wide), pitch %s, at 45 deg on one grid\nper face (lines X -/+ v = k x %s); land %s" % (
             n("texture depth", p.tex_depth, "tex_depth", md=1), n("texture groove width", 2 * p.tex_depth, "2*tex_depth", md=1),
             n("texture pitch", p.tex_pitch, "tex_pitch", md=1), n("texture grid step", p.tex_pitch * math.sqrt(2), "tex_pitch*sqrt2"),
             n("texture land", p.tex_pitch - 2 * p.tex_depth, "tex_pitch-2*tex_depth", md=1)),
         "depth +/-0.03"],
        ["18", "Transverse grooves",
         "90 deg V, %s deep: head set X %s (top, bottom, diagonal facets only),\ntail set X %s all round (apex positions)" % (
             n("transverse groove depth", p.grv_depth, "grv_depth", md=1), ", ".join(num(x, 1) for x in p.grv_head),
             ", ".join(num(x, 1) for x in p.grv_tail)),
         "depth +/-0.03\nX +/-0.1"],
        ["19", "Key bezel (bottom)",
         "recess %s deep, 45 deg walls, floor %s beyond the keys (stadium\nX %s to %s, Y +/- %s at the face)" % (
             n("bezel depth", p.bez_depth, "bez_depth", md=1), n("bezel floor margin", p.bez_margin, "bez_margin", md=1),
             n("bezel start X", bx0, "X_next-side_key[0]/2-bez_margin-bez_depth", md=1),
             n("bezel end X", bx1, "X_prev+side_key[0]/2+bez_margin+bez_depth", md=1), n("bezel half width", by1, "side_key[1]/2+bez_margin+bez_depth", md=1)),
         "depth +/-0.05"],
        ["20", "Floor RF window",
         "%s x %s R%s through, X %s to %s; POM-C plug of the antenna spacer\nflush with the panel floor, textured (FK-H-05)" % (
             n("floor RF window length", fx1 - fx0, "frw_box[1]-frw_box[0]", md=1), n("floor RF window width", 2 * fhy, "2*frw_box[2]", md=1),
             n("floor RF window radius", fr, "frw_box[3]", md=1), n("floor RF window start X", fx0, "frw_box[0]", md=1),
             n("floor RF window end X", fx1, "frw_box[1]", md=1)),
         "+/-0.05"],
        ["21", "Tail window (bottom)",
         "%s x %s, %s deep, corners R%s / R%s, chamfer C%s; X %s to %s" % (
             n("tail window length", xw1 - xw0, "twin_x", md=1), n("tail window width", p.twin_y, "twin_y", md=1),
             n("tail window depth", p.twin_depth, "twin_depth", md=1), n("tail window corner", p.twin_r, "twin_r", md=1),
             n("tail window big corner", kc, "twin_corner", md=1), n("tail window chamfer", p.twin_chamfer, "twin_chamfer", md=1),
             n("tail window start X", xw0, TW_X0_EXPR, md=1), n("tail window end X", xw1, "X_lan+twin_x/2", md=1)),
         "+/-0.1"],
        ["22", "Lanyard slot, THRU",
         "stadium %s x %s, centre X %s; chamfer C%s both faces" % (
             n("lanyard slot width", p.lan_slot_w, "lan_slot_w", md=1), n("lanyard slot length", p.lan_slot_len, "lan_slot_len", md=1),
             n("lanyard slot centre X", p.X_lan, "X_lan", md=1), n("lanyard slot chamfer", p.lan_chamfer, "lan_chamfer")),
         "+/-0.1"],
        ["23", "Tail facets",
         "%s x 45 deg on the two vertical tail corners" % n("tail facet", p.tail_facet, "tail_facet", md=1), "ISO 2768-mK"],
    ]
    sh.table(232, 156, (7, 30, 100, 40), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)
    NW = 96.0
    lim = min(r["metal_under_mm"] for r in (thin_walls(p, housing_dir)[1] or [{"metal_under_mm": 0.9}]))
    notes = [
        "NOTES",
        "1  Order: finish the body, then the panels (16) with a flat end mill, then the texture (17) and the "
        "grooves (18) with one 90 deg V engraving cutter (tip R <= 0.03), then blast and anodise. Do not "
        "deepen the texture: the metal under it is %s mm at the thinnest spot." % V(
            "min metal under texture or grooves", lim, "texture_min_metal_mm", view="notes"),
        "2  The bottom and side views show the panels without the texture lines; the texture covers every "
        "panel and stops at the panel wall.",
        "3  Finish: fine glass-bead blast, anodise type II matte black (8-12 um); break the panel and groove "
        "edges 0.05. No marking of any kind.",
        "4  The keys sit %s (main key) and %s (side keys, chevron %s) inside the bottom-face plane, in the bezel "
        "(19); the floor RF window plug and the lid RF insert carry the same texture (FK-H-05)." % (
            V("main key face below the bottom plane", p.main_face_z, "main_face_z", view="notes", md=2),
            V("side key face below the bottom plane", p.side_face_z, "side_face_z", view="notes", md=2),
            V("chevron top below the bottom plane", p.side_face_z - p.chevron_h, "side_face_z-chevron_h", view="notes", md=2)),
    ]
    lines = [ln for n_ in notes for ln in wrap(n_, NW, 2.0)]
    sh.mtext(lines, 232, 94, 2.0, 1.0)
    return sh, locals()


def lid_sheet(p, out, housing_dir=None):
    """Lid (the cap above the lid seat): outline, panels, RF window opening + underside pocket, countersunk screws,
    pocket over the cavity, two hold-down bosses (sections use the lid without the panels)."""
    lid_t = H.build_lid(p, texture="panels")
    lid_p = H.build_lid(p, texture="none")
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
    flat = p.W - 2 * p.C_edge
    lay = {q["name"]: q for q in H.panel_layout(p)}
    t1, tb1, tb2 = lay["top PCB zone"], lay["top bay 1"], lay["top bay 2"]
    zb2 = p.Z_pcb_top + p.pad2_gap                     # front boss face
    h2 = p.Z_ceil - zb2
    land = p.wall * math.sqrt(2)                       # flat seat of the lid on the tray walls (each side)
    y_seat = p.W / 2 - land                            # pocket edge at the seat
    y_ceil = p.W / 2 - p.C_edge - p.wall * math.sqrt(2) + p.lid_t   # pocket edge at the plate
    XJ = 23.5                                          # sections J-J, K-K: between the two hold-down bosses

    top = hlr(lid_t.val().wrapped, (0, 0, 1), (1, 0, 0), "v7_lid_top")
    bot = hlr(lid_t.val().wrapped, (0, 0, -1), (1, 0, 0), "v7_lid_bot")
    secJ, hatJ, _ = section_trans(lid_p, p, XJ, "J-J", spacing=0.4)
    GW = (14.0 + H.PCB_DX, 33.0 + H.PCB_DX, 10.4, 18.4)       # round the two hold-down bosses
    secG, hatG, _ = section_long(lid_p, p, 1.7, "G-G", spacing=0.2)
    secG, hatG = clip_view(secG, u0=GW[0], u1=GW[1], v0=GW[2], v1=GW[3]), clip_segs(hatG, *GW)
    KW = (2.0, 10.4, 14.0, 18.4)
    secK, hatK, _ = section_trans(lid_p, p, XJ, "K-K", spacing=0.12)
    secK, hatK = clip_view(secK, u0=KW[0], u1=KW[1], v0=KW[2], v1=KW[3]), clip_segs(hatK, *KW)

    T = (21.6, 245)
    U = (21.6, 128)
    J = (320, 182)
    G = (161 - 0 * 5, 71.0)
    K = (260, 46)
    sh.view(top, *T, "top", hidden=False)
    sh.view(bot, *U, "under", hidden=False)
    sh.view(secJ, *J, "secJ", hidden=False, scale=4.0)
    sh.hatch(hatJ, *J)
    sh.view(secG, *(G[0] - 5 * GW[0] + 5 * (15.0 + H.PCB_DX), G[1]), "secG", hidden=False, scale=5.0)
    G = (G[0] - 5 * GW[0] + 5 * (15.0 + H.PCB_DX), G[1])
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
    sh.hdim(*T, x0, yb, t1["u0"], -t1["v1"], -22, "first panel from the lid front edge", "panel_layout",
            t1["u0"] - x0)
    sh.hdim(*T, t1["u0"], -t1["v1"], t1["u1"], -t1["v1"], -22, "PCB-zone panel length", "panel_layout",
            t1["u1"] - t1["u0"])
    sh.hdim(*T, rfx0, -rfhy, rfx1, -rfhy, -22, "RF opening length", "rfw_box[1]-rfw_box[0]", rfx1 - rfx0)
    sh.hdim(*T, tb1["u0"], -tb1["v1"], tb1["u1"], -tb1["v1"], -22, "bay panel 1 length", "panel_layout",
            tb1["u1"] - tb1["u0"])
    sh.hdim(*T, tb2["u0"], -tb2["v1"], tb2["u1"], -tb2["v1"], -22, "bay panel 2 length", "panel_layout",
            tb2["u1"] - tb2["u0"])
    sh.hdim(*T, x0, yb, L, yb, -28, "lid length", "L-lid_x0", L - x0)
    sh.vdim(*T, p.screw_x_front, -sy, p.screw_x_front, sy, x0 - 1.2, "screw spacing across",
            "2*screw_dy", 2 * sy)
    sh.vdim(*T, rfx0, -rfhy, rfx0, rfhy, rfx0 - 2.4, "RF opening width", "rfw_y", p.rfw_y)
    xq = 0.5 * (tb2["u0"] + tb2["u1"])
    sh.vdim(*T, xq, -tb2["v1"], xq, -tb2["v0"], xq, "panel width", "2*(W/2-C_edge-rail)", tb2["v1"] - tb2["v0"])
    sh.vdim(*T, xs0, -hy, xs0, hy, xs0 - 1.9, "lanyard slot length", "lan_slot_len", p.lan_slot_len)
    sh.vdim(*T, L, -(p.W / 2 - p.tail_facet), L, p.W / 2 - p.tail_facet, L + 4.0, "tail end width",
            "W-2*tail_facet", p.W - 2 * p.tail_facet)
    sh.tag(*T, p.screw_x_front, sy, -3, 17, 2)
    sh.tag(*T, p.X_screw_back, sy + 1.0, 3, 13, 2)
    sh.tag(*T, 0.5 * (rfx0 + rfx1) - 1.0, rfhy - 0.6, 0, 16, 3)
    sh.tag(*T, 0.5 * (t1["u0"] + t1["u1"]), t1["v1"] - 0.5, 0, 15, 7)
    sh.tag(*T, p.X_lan - 1.0, hy - 0.4, -14, 22, 5)
    sh.tag(*T, L - p.tail_facet / 2, p.W / 2 - p.tail_facet / 2, 8, 6, 1)
    sh.text("TOP VIEW (from +Z)   items 1, 2, 3, 5, 7", 28, 279, 3.0)

    # ------------------------------------------------------------ underside view
    sh.cur = "under"
    sh.hdim(*U, rfx0, -rfhy, rfx1, -rfhy, -14, "RF opening length", "rfw_box[1]-rfw_box[0]", rfx1 - rfx0)
    sh.hdim(*U, pk_x0, -pk_hy, pk_x1, -pk_hy, -18, "RF pocket length", "rfw_box[1]-rfw_box[0]+2*rfw_flange",
            pk_x1 - pk_x0)
    sh.hdim(*U, bx0, -by0, bx1, -by0, 12.4, "hold-down boss length", "boss_box[1]-boss_box[0]", bx1 - bx0)
    sh.vdim(*U, bx0, -by0, bx0, -by1, bx0 - 2.4, "hold-down boss width", "boss_box[3]-boss_box[2]", by1 - by0)
    sh.hdim(*U, cx0, -cy0, cx1, -cy0, 12.4, "front boss length", "boss2_box[1]-boss2_box[0]", cx1 - cx0)
    sh.vdim(*U, cx0, -cy1, cx0, -cy0, cx0 - 2.0, "front boss width", "boss2_box[3]-boss2_box[2]", cy1 - cy0)
    sh.vdim(*U, rfx1, -rfhy, rfx1, rfhy, rfx1 + 3.4, "RF opening width", "rfw_y", p.rfw_y)
    sh.tag(*U, 0.5 * (pk_x0 + pk_x1), pk_hy, 0, 11, 4)
    sh.tag(*U, bx0 + 1.9, -by1 + 0.4, -2, -19, 8)
    sh.tag(*U, cx0 + 0.6, -cy1 + 0.4, -5, -19, 8)
    sh.tag(*U, p.screw_x_front, -sy, 0, -16, 2)
    sh.tag(*U, p.X_lan + 1.6, 0.0, 9, 0, 5)
    sh.tag(*U, 66.0, 4.0, 0, 17, 6)
    sh.text("UNDERSIDE (from -Z)   items 2-6, 8", 28, 162, 3.0)

    # ------------------------------------------------------------ section J-J (4:1)
    sh.cur = "secJ"
    sh.hdim(*J, -flat / 2, z1, flat / 2, z1, z1 + 2.6, "flat top width", "W-2*C_edge", flat)
    sh.vdim(*J, p.W / 2, z0, flat / 2, z1, 12.6, "lid height (seat to top)", "H-Z_lid", z1 - z0)
    sh.text("SECTION J-J  (X = %s, no panels)   items 1, 6" % num(XJ, 1), 270, 276, 3.0)
    sh.leader(*J, -(p.W / 2 - p.C_edge / 2) - 0.05, z1 - p.C_edge / 2 - 0.05, -7, 3, "facets %s x 45 deg" % V(
        "facet leg", p.C_edge, "C_edge", view="secJ", md=1), h=2.2)

    # ------------------------------------------------------------ section G-G (5:1)
    sh.cur = "secG"
    zb1 = p.Z_ceil - p.boss_h
    sh.hdim(*G, bx0, zb1, bx1, zb1, zb1 - 0.55, "can boss length", "boss_box[1]-boss_box[0]", bx1 - bx0)
    sh.vdim(*G, bx0, zb1, bx0, p.Z_ceil, bx0 - 1.2, "can boss height", "Z_ceil-can_top_z-pad_gap", p.boss_h, shift=-6.1)
    sh.hdim(*G, cx0, zb2, cx1, zb2, zb2 - 1.4, "front boss length", "boss2_box[1]-boss2_box[0]", cx1 - cx0)
    sh.vdim(*G, cx0, zb2, cx0, p.Z_ceil, GW[0] - 0.8, "front boss height", "Z_ceil-Z_pcb_top-pad2_gap", h2)
    sh.text("SECTION G-G  (Y = %s, no panels, 5:1)   item 8" % num(1.7, 1), 236, 166, 3.0)

    # ------------------------------------------------------------ section K-K (10:1)
    sh.cur = "secK"
    sh.hdim(*K, y_seat, z0, p.W / 2, z0, z0 - 0.5, "seat width (each side)", "wall*sqrt2", land)
    sh.vdim(*K, y_seat, z0, y_ceil, p.Z_ceil, 3.0, "pocket depth (seat to plate)", "Z_ceil-Z_lid", p.Z_ceil - z0)
    sh.leader(*K, 0.5 * (y_seat + y_ceil), 0.5 * (z0 + p.Z_ceil), -8, -5,
              "(6) 45 deg wall %s" % V("diagonal wall", p.wall, "wall", view="secK", md=1), h=2.0)
    sh.text("DETAIL K-K  (lid edge on the seat, X = %s, 10:1)   item 6" % num(XJ, 1), 292, 176, 3.0)

    # ------------------------------------------------------------ feature table
    n = lambda what, val, expr, **k: V(what, val, expr, **k)
    web_pocket = p.lid_t - p.rfw_flange_t
    sliver = sy - p.m16_csk / 2 - (hy + p.lan_chamfer)
    csk_edge = (p.W / 2 - p.C_edge) - (sy + p.m16_csk / 2)
    rows = [
        ["1", "Lid (cap)",
         "the body above Z %s (the upper facet edges), %s tall: top facet %s wide, diagonal\nfacets %s x 45 deg; X %s to %s (body coordinates); tail facets %s x 45 deg as the tray" % (
             n("lid seat Z", z0, "Z_lid", md=1), n("lid height", z1 - z0, "H-Z_lid", md=1),
             n("flat top width", flat, "W-2*C_edge", md=1), n("facet leg", p.C_edge, "C_edge", md=1),
             n("lid front edge X", x0, "lid_x0", md=1), n("lid end X", L, "L"),
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
         "+/-0.03"],
        ["4", "RF pocket (underside)",
         "%s x %s, R%s, %s deep (Z %s to %s), %s margin round the opening;\nseat of the POM insert flange; %s of lid remains above" % (
             n("RF pocket length", pk_x1 - pk_x0, "rfw_box[1]-rfw_box[0]+2*rfw_flange", md=1),
             n("RF pocket width", 2 * pk_hy, "rfw_y+2*rfw_flange", md=1), n("RF pocket corner radius", p.rfw_r + fl, "rfw_r+rfw_flange", md=1),
             n("RF pocket depth", p.rfw_flange_t, "rfw_flange_t", md=1), n("lid plate underside Z", p.Z_ceil, "Z_ceil", md=1),
             n("RF pocket ceiling Z", p.Z_ceil + p.rfw_flange_t, "Z_ceil+rfw_flange_t", md=1), n("RF pocket margin", fl, "rfw_flange", md=1),
             n("lid above the pocket", web_pocket, "lid_t-rfw_flange_t")),
         "+/-0.05; depth +/-0.03"],
        ["5", "Lanyard slot, THRU",
         "stadium %s x %s, centre X %s, Y 0; chamfer C%s on the top face;\nsame slot as the tray (FK-H-01 item 22)" % (
             n("lanyard slot width", p.lan_slot_w, "lan_slot_w", md=1), n("lanyard slot length", p.lan_slot_len, "lan_slot_len", md=1),
             n("lanyard slot centre X", p.X_lan, "X_lan", md=1), n("lanyard slot chamfer", p.lan_chamfer, "lan_chamfer")),
         "+/-0.1"],
        ["6", "Pocket over the cavity",
         "X %s to %s, plan corners R%s: plate %s (Z %s), 45 deg walls %s under the diagonal\nfacets, flat seat %s wide each side (pocket |Y| %s at the seat); solid over head and tail" % (
             n("pocket start X", p.L_head, "L_head"), n("pocket end X", p.X_batt1, "X_batt1"),
             n("pocket plan corner radius", p.inner_r, "inner_r", md=1), n("lid plate thickness", p.lid_t, "lid_t", md=1),
             n("lid plate underside Z", p.Z_ceil, "Z_ceil", md=1), n("diagonal wall", p.wall, "wall", md=1),
             n("seat width (each side)", land, "wall*sqrt2"), n("pocket half width at the seat", y_seat, "W/2-wall*sqrt2")),
         "+/-0.1; seat flat 0.05"],
        ["7", "Panels, texture, grooves",
         "3 recessed panels %s deep with the V texture and the tail grooves as the\ntray (FK-H-01 sheet 2, items 16-18); panels |Y| <= %s" % (
             n("panel depth", p.pan_depth, "pan_depth", md=1), n("panel half width", t1["v1"], "W/2-C_edge-rail", md=1)),
         "depth +/-0.03"],
        ["8", "Hold-down bosses 2x",
         "can boss X %s to %s, Y %s to %s, R%s, %s tall (face Z %s);\nfront boss X %s to %s, Y %s to %s, R%s, %s tall (face Z %s)" % (
             n("boss start X", bx0, "boss_box[0]", md=1), n("boss end X", bx1, "boss_box[1]", md=1),
             n("boss start Y", by0, "boss_box[2]", md=1), n("boss end Y", by1, "boss_box[3]", md=1),
             n("boss corner radius", p.boss_r, "boss_r", md=1), n("boss height", p.boss_h, "Z_ceil-can_top_z-pad_gap"),
             n("can boss face Z", p.Z_ceil - p.boss_h, "can_top_z+pad_gap", pval=p.can_top_z + p.pad_gap),
             n("front boss start X", cx0, "boss2_box[0]", dec=2), n("front boss end X", cx1, "boss2_box[1]", dec=2),
             n("front boss start Y", cy0, "boss2_box[2]", dec=2), n("front boss end Y", cy1, "boss2_box[3]", dec=2),
             n("front boss corner radius", p.boss2_r, "boss2_r", md=1), n("front boss height", h2, "Z_ceil-Z_pcb_top-pad2_gap", md=1),
             n("front boss face Z", zb2, "Z_pcb_top+pad2_gap", md=1)),
         "+/-0.03 (height)\nposition +/-0.05"],
        ["8a", "Pads (bought parts)",
         "can: %s thermal gap pad (Shore 00 70-80) cut to the can boss, compressed to %s;\nfront: %s silicone rubber sheet (Shore A 70) cut %s x %s, compressed to %s" % (
             n("can pad free thickness", p.pad_t0, "pad_t0", md=1), n("can pad gap", p.pad_gap, "pad_gap"),
             n("front pad free thickness", p.pad2_t0, "pad2_t0", md=1),
             n("front pad length", cx1 - cx0, "boss2_box[1]-boss2_box[0]", md=1), n("front pad width", cy1 - cy0, "boss2_box[3]-boss2_box[2]", md=1),
             n("front pad gap", p.pad2_gap, "pad2_gap", md=1)),
         "stick on with a drop of\nsilicone adhesive"],
        ["9", "RF window insert",
         "not machined here: POM-C insert (FlashKa_rf_window.step, FK-H-05), %s\nclearance per side, held by its flange and the antenna spacer" % (
             n("insert clearance", p.rfw_clear, "rfw_clear", md=2)),
         ""],
    ]
    sh.table(28, 90, (7, 34, 112, 43), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
             h=1.9, pad=0.9, line=2.7)

    NW = 80.0
    notes = [
        "NOTES",
        "1  Material: aluminium 6061-T6, a cap %s tall (plate %s over the cavity). Geometry per FlashKa_lid.step; "
        "X, Y, Z are body coordinates (X = 0 at the front face of the body)." % (
            V("lid height", z1 - z0, "H-Z_lid", view="notes", md=1), V("lid plate thickness", p.lid_t, "lid_t", view="notes", md=1)),
        "2  General tolerances ISO 2768-mK; toleranced values are critical.",
        "3  Screws: 4x M1.6 x %s countersunk, ISO 7046 / DIN 965, stainless steel. The countersink edge is %s "
        "inside the top facet edge: do not enlarge it. The seat (6) must be flat: the lid closes on it, the facets "
        "of lid and tray meet flush." % (
            V("lid screw length", p.lid_screw_len, "lid_screw_len", view="notes"),
            V("countersink edge to the facet edge", csk_edge, "(W/2-C_edge)-(screw_dy+m16_csk/2)", view="notes", dec=2)),
        "4  Finish: fine glass-bead blast, anodise type II matte black (8-12 um). Cut the panels and grooves "
        "before blasting. No marking of any kind. Sections G-G, J-J, K-K are drawn without the panels.",
        "5  At X %s the rear countersinks and the slot chamfer leave a sliver of only %s at the top face: "
        "break edges lightly (max 0.05)." % (
            V("rear screw X", p.X_screw_back, "X_screw_back", view="notes", md=1),
            V("sliver csk - slot chamfer", sliver, "screw_dy-m16_csk/2-(lan_slot_len/2+lan_chamfer)", view="notes", dec=2)),
        "6  The front end of the lid covers the laser set screw in the head block (tray FK-H-01, item 5): no "
        "hole or screw shows on the closed light apart from the four lid screws.",
        "7  A light that is sold to others needs the laser class label on the lid (EN 60825-1): the optional "
        "artwork is in order_files/optional_laser_label/; it is not part of this drawing.",
    ]
    lines = [ln for n_ in notes for ln in wrap(n_, NW, 2.0)]
    half = (len(lines) + 1) // 2
    sh.mtext(lines[:half], 236, 108, 2.0, 1.0)
    sh.mtext(lines[half:], 324, 108, 2.0, 1.0)
    return sh, locals()


# --------------------------------------------------------------------------
# small parts: views of a part moved to the drawing origin
# --------------------------------------------------------------------------
def _views_small(sh, shape, names_dirs, origins, scale, cache=None):
    """HLR views of `shape` (a Workplane) at `scale`: names_dirs = [(name, normal, xdir)], origins = {name: (ox, oy)}"""
    out = {}
    for nm_, nrm, xd in names_dirs:
        v = hlr(shape.val().wrapped, nrm, xd, (cache + "_" + nm_) if cache else None)
        ox, oy = origins[nm_]
        sh.view(v, ox, oy, nm_, hidden=False, scale=scale)
        out[nm_] = v
    return out


def section_y(wp, y, spacing, half=True):
    """section in the plane Y = y, seen from -Y: (polys, hatch)"""
    keep = wp.intersect(H.rbox(-30, 30, y, 30, -5, 30)) if half else wp
    slab = wp.intersect(H.rbox(-30, 30, y, y + 0.3, -5, 30))
    polys = hlr(keep.val().wrapped, (0, -1, 0), (1, 0, 0))
    loops = cut_loops(slab, "y", y, lambda a, b, c: (a, c))
    return polys, hatch_segments(loops, spacing)


def section_x(wp, x, spacing):
    """section in the plane X = x, seen from -X (the part with X >= x), u = -Y... drawn with u = Y mirrored: (polys, hatch)"""
    keep = wp.intersect(H.rbox(x, 30, -30, 30, -5, 30))
    slab = wp.intersect(H.rbox(x, x + 0.3, -30, 30, -5, 30))
    polys = hlr(keep.val().wrapped, (-1, 0, 0), (0, -1, 0))
    loops = cut_loops(slab, "x", x, lambda a, b, c: (-b, c))
    return polys, hatch_segments(loops, spacing)


def key_main_sheet(p, out):
    """FK-H-03 main key: clear cast PMMA, polished, frosted ring icon (sections 15:1, views 10:1)"""
    k = H.build_key_main(p).translate((-p.X_main, -p.key_y, 0))
    SC, SS = 10.0, 15.0
    sh = Sheet("MAIN KEY - CLEAR PMMA (1x)", "FK-H-03  FlashKa_key_main.step", "1/1",
               scale_text="SCALE 10:1, sections 15:1", tol_text="ISO 2768-fH")
    V = make_V(sh.name)
    mx, my, mr = p.main_key
    fw, ft = p.flange_main, p.flange_t
    zf, zt, z0 = p.Z_seat, p.main_top_z, p.main_face_z
    bx, by = p.sw_body
    pcx, pcy = bx + 2 * p.pocket_clear, by + 2 * p.pocket_clear
    zpf = p.main_nub_z - p.nub_h
    dm, rw, rd = p.ring_icon
    secX, hatX = section_y(k, 0.0, 0.12)
    secY, hatY = section_x(k, 0.0, 0.12)
    O = {"secX": (117, 190), "secY": (117, 98), "top": (345, 228), "bot": (345, 140)}
    sh.view(secX, *O["secX"], "secX", hidden=False, scale=SS)
    sh.hatch(hatX, *O["secX"])
    sh.view(secY, *O["secY"], "secY", hidden=False, scale=SS)
    sh.hatch(hatY, *O["secY"])
    _views_small(sh, k, [("top", (0, 0, 1), (1, 0, 0)), ("bot", (0, 0, -1), (1, 0, 0))], O, SC, "v7_kmain")
    # ---- section X (u = X, v = Z)
    sh.cur = "secX"
    ox, oy = O["secX"]
    sh.hdim(ox, oy, -mx / 2, z0, mx / 2, z0, z0 - 0.6, "key width X", "main_key[0]", mx, "<> -0.03/-0.08")
    sh.hdim(ox, oy, -mx / 2 - fw, zf, mx / 2 + fw, zf, z0 - 1.1, "flange X", "main_key[0]+2*flange_main", mx + 2 * fw,
            "<> -0.05/-0.10")
    sh.hdim(ox, oy, -pcx / 2, zt, pcx / 2, zt, zt + 0.3, "pocket X", "sw_body[0]+2*pocket_clear", pcx)
    sh.hdim(ox, oy, -p.nub_d / 2, p.main_nub_z, p.nub_d / 2, p.main_nub_z, 2.6, "nub diameter", "nub_d", p.nub_d, "%%c<>")
    sh.vdim(ox, oy, -mx / 2, z0, -mx / 2, zt, -mx / 2 - fw - 0.8, "key height", "main_top_z-main_face_z", zt - z0,
            "<> +/-0.03", shift=10.4)
    sh.vdim(ox, oy, -mx / 2, z0, -mx / 2 - fw, zf, -mx / 2 - fw - 1.6, "face to flange underside",
            "Z_seat-main_face_z", zf - z0, "<> +/-0.03")
    sh.vdim(ox, oy, mx / 2 + fw, zf, mx / 2 + fw, zf + ft, mx / 2 + fw + 0.7, "flange thickness", "flange_t", ft,
            "<> +/-0.03", shift=-13.6)
    sh.vdim(ox, oy, mx / 2 + fw, zf, p.nub_d / 2, p.main_nub_z, mx / 2 + fw + 1.5, "flange underside to nub top",
            "main_nub_z-Z_seat", p.main_nub_z - zf, "<> +/-0.03", shift=16)
    sh.vdim(ox, oy, 0.9, zpf, 0.9, zt, 1.5, "pocket depth", "main_top_z-(main_nub_z-nub_h)", zt - zpf, shift=3.75)
    sh.text("SECTION X  (plane Y = 0, seen from -Y, 15:1)", 40, 247, 3.0)
    # ---- section Y (u = Y, v = Z)
    sh.cur = "secY"
    ox, oy = O["secY"]
    sh.hdim(ox, oy, -my / 2, z0, my / 2, z0, z0 - 0.6, "key width Y", "main_key[1]", my, "<> -0.03/-0.08")
    sh.hdim(ox, oy, -pcy / 2, zt, pcy / 2, zt, zt + 0.3, "pocket Y", "sw_body[1]+2*pocket_clear", pcy)
    sh.hdim(ox, oy, -p.led_y, zt, p.led_y, zt, zt + 0.8, "ring LED axes (light input)", "2*led_y", 2 * p.led_y,
            "<> LED axes")
    sh.text("SECTION Y  (plane X = 0, seen from -X, 15:1)", 40, 164, 3.0)
    # ---- top / bottom (10:1)
    sh.cur = "top"
    ox, oy = O["top"]
    sh.hdim(ox, oy, -mx / 2, -my / 2, mx / 2, -my / 2, -my / 2 - fw - 0.9, "key width X", "main_key[0]", mx)
    sh.vdim(ox, oy, -mx / 2 - fw, -my / 2 - fw, -mx / 2 - fw, my / 2 + fw, -mx / 2 - fw - 0.8, "flange Y",
            "main_key[1]+2*flange_main", my + 2 * fw)
    c45 = 0.5 * math.sqrt(0.5)
    sh.leader(ox, oy, pcx / 2 - 0.5 + c45, pcy / 2 - 0.5 + c45, 22, 16,
              "pocket R%s" % V("pocket corner radius", 0.5, "0.5 (build_key_main)", view="top", md=1), h=2.2)
    sh.text("TOP VIEW (from +Z, light input face, 10:1)", 296, 271, 3.0)
    sh.cur = "bot"
    ox, oy = O["bot"]
    q = dm / 2 * math.sqrt(0.5)
    sh.leader(ox, oy, -q, q, -24, 16,
              ["frosted ring Ø%s / Ø%s" % (V("ring outer dia", dm + rw, "ring_icon[0]+ring_icon[1]", view="bot", md=1),
                                          V("ring inner dia", dm - rw, "ring_icon[0]-ring_icon[1]", view="bot", md=1)),
               "%s deep, matte" % V("ring depth", rd, "ring_icon[2]", view="bot", dec=2)], h=2.2)
    rc = mr * math.sqrt(0.5)
    sh.leader(ox, oy, -(mx / 2 - mr) - rc, -(my / 2 - mr) - rc, -8, -6,
              "corners R%s" % V("key corner radius", mr, "main_key[2]", view="bot", md=1), h=2.2)
    sh.text("BOTTOM VIEW (from -Z, outer face, 10:1)", 296, 95, 3.0)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["1", "Material", "clear cast PMMA (cast acrylic, colourless, not extruded), CNC from sheet or bar", ""],
        ["2", "Outer face", "%s x %s, corners R%s, flat; frosted ring Ø%s mean, %s wide; edge C%s polished" % (
            n("key width X", mx, "main_key[0]", md=1), n("key width Y", my, "main_key[1]", md=1), n("key corner radius", mr, "main_key[2]", md=1),
            n("ring mean dia", dm, "ring_icon[0]", md=1), n("ring width", rw, "ring_icon[1]", md=1), n("face edge chamfer", 0.15, "0.15 (build_key_main)", md=2)),
         "-0.03/-0.08 (opening\n%s x %s)" % (n("floor opening X", mx + 2 * p.key_clear, "main_key[0]+2*key_clear", md=1),
                                              n("floor opening Y", my + 2 * p.key_clear, "main_key[1]+2*key_clear", md=1))],
        ["3", "Flange", "%s x %s x %s, sits on the floor of the tray; the key is held between the floor and the switch" % (
            n("flange X", mx + 2 * fw, "main_key[0]+2*flange_main", md=1), n("flange Y", my + 2 * fw, "main_key[1]+2*flange_main", md=1),
            n("flange thickness", ft, "flange_t", dec=2)), "thickness +/-0.03\noutline -0.05/-0.10"],
        ["4", "Pocket + nub", "pocket %s x %s, %s deep round the switch body; nub Ø%s x %s presses the switch" % (
            n("pocket X", pcx, "sw_body[0]+2*pocket_clear", md=1), n("pocket Y", pcy, "sw_body[1]+2*pocket_clear", md=1),
            n("pocket depth", zt - zpf, "main_top_z-(main_nub_z-nub_h)", md=1), n("nub diameter", p.nub_d, "nub_d", md=1),
            n("nub height", p.nub_h, "nub_h", md=1)), "nub top flat 0.02"],
        ["5", "Light path", "the two ring LEDs (Y +/- %s) shine into the top face, %s above it at rest; the light leaves\nthrough the frosted ring" % (
            n("ring LED offset", p.led_y, "led_y", md=1), n("LED gap at rest", p.led_gap_rest, "led_gap_rest", md=1)), ""],
        ["6", "Finish", "vapour or flame polish on every face (top face and outer face optically clear, no tool\nmarks); the ring only frosted (laser-etched or blasted through a mask)", "clear Ra <= 0.05\nring Ra 1.6-3.2"],
        ["7", "Quantity", "1 per light, plus 1 spare", ""],
    ]
    sh.table(28, 84, (7, 28, 135, 30), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  Geometry per FlashKa_key_main.step (in the STEP the key sits in the housing frame at X %s; here it "
             "is centred on its axis). General tolerances ISO 2768-fH." % V("main key X", p.X_main, "X_main", view="notes", md=1),
             "2  Free play nub -> switch %s mm at rest, LED gap at full travel %s mm: keep the height %s +/-0.03 "
             "and the flange-to-nub length %s +/-0.03." % (
                 V("main key free play", p.pre_main, "pre_main", view="notes", dec=2),
                 V("LED gap at full travel", p.led_gap_rest - p.pre_main - p.sw_travel, "led_gap_rest-pre_main-sw_travel", view="notes", dec=2),
                 V("key height", zt - z0, "main_top_z-main_face_z", view="notes", md=1),
                 V("flange underside to nub top", p.main_nub_z - zf, "main_nub_z-Z_seat", view="notes", dec=2)),
             "3  Clean with water and a mild soap only: solvents and alcohol craze PMMA.",
             "4  No paint, no marking. The frosted ring is the only diffuse area.",
             "5  JLCCNC takes plastic parts from 30 x 20 x 8 mm only: order three keys (1 + 2 spares) as one machining "
             "kit, FlashKa_pmma_kit.step (drawing FK-H-06). This single file is for shops that take small parts."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 86, 2.0, 1.0)
    return sh, locals()


def key_side_sheet(p, out):
    """FK-H-04 side key: cast black rubber (no insert) + stiffener plate and doubler glued in (sections 12:1, views 8:1)"""
    k = H.build_key_side(p, p.X_next, -1).translate((-p.X_next, -p.key_y, 0))
    stf = H.build_key_stiffener(p, p.X_next).translate((-p.X_next, -p.key_y, 0))
    SC, SS = 8.0, 12.0
    sh = Sheet("SIDE KEY - CAST RUBBER + GLUED STIFFENER (2x)", "FK-H-04  FlashKa_key_side.step (rubber),\n"
               "FlashKa_key_stiffener.step (plate + doubler)", "1/1",
               scale_text="SCALE 8:1, sections 12:1", tol_text="ISO 3302-1 M2")
    V = make_V(sh.name)
    sx, sy_, sr = p.side_key
    fw, ft = p.flange_side, p.flange_t
    zf, z0 = p.Z_seat, p.side_face_z
    zt = zf + ft                                # key top (inner face)
    sw_, sa, sb = p.chevron                     # stroke, half length along X (apex direction), half span along Y
    w_, ln_, t_, c_ = p.stiffener
    dx_, dy_, dt_ = p.doubler
    rx, ry, rr = p.plate_recess
    zr = p.stiff_z0 - p.plate_glue              # recess floor
    zd = p.side_nub_z                           # doubler top: presses the switch
    zc = z0 - p.chevron_h                       # chevron top (outermost)
    both = k.union(stf)
    secL, secS = section_x(both, 0.0, 0.12)[0], section_y(both, 0.0, 0.12)[0]
    hatL, hatS = section_x(k, 0.0, 0.12)[1], section_y(k, 0.0, 0.12)[1]
    secLp, hatLp = section_x(stf, 0.0, 0.04)
    secSp, hatSp = section_y(stf, 0.0, 0.04)
    O = {"secL": (100, 238), "secS": (300, 238), "bot": (95, 185), "top": (240, 185), "plate": (355, 185)}
    sh.view(secL, *O["secL"], "secL", hidden=False, scale=SS)
    sh.hatch(hatL, *O["secL"])
    sh.view(secLp, *O["secL"], "secLp", hidden=False, scale=SS)
    sh.hatch(hatLp, *O["secL"])
    sh.view(secS, *O["secS"], "secS", hidden=False, scale=SS)
    sh.hatch(hatS, *O["secS"])
    sh.view(secSp, *O["secS"], "secSp", hidden=False, scale=SS)
    sh.hatch(hatSp, *O["secS"])
    del sh.vboxes["secLp"], sh.vboxes["secSp"]
    # plan views with the long axis (Y) horizontal: bottom u = Y, v = X; top u = Y, v = -X
    _views_small(sh, k, [("bot", (0, 0, -1), (0, 1, 0)), ("top", (0, 0, 1), (0, 1, 0))], O, SC, "v8_kside_h")
    _views_small(sh, stf, [("plate", (0, 0, 1), (0, 1, 0))], O, SC, "v8_kside_plate")
    # ---- section L (plane X = 0; u = -Y, v = Z)
    sh.cur = "secL"
    ox, oy = O["secL"]
    sh.hdim(ox, oy, -sy_ / 2, z0, sy_ / 2, z0, zc - 0.6, "key length", "side_key[1]", sy_, "<> -0.05/-0.15")
    sh.hdim(ox, oy, -sy_ / 2 - fw, zt, sy_ / 2 + fw, zt, zd + 0.55, "flange length", "side_key[1]+2*flange_side", sy_ + 2 * fw)
    sh.vdim(ox, oy, -sy_ / 2, z0, -sy_ / 2 - fw, zf, -sy_ / 2 - fw - 0.9, "face to flange underside",
            "Z_seat-side_face_z", zf - z0, "<> +/-0.08", shift=16.3)
    sh.vdim(ox, oy, -sy_ / 2 - fw, zt, -ry / 2, zr, -sy_ / 2 - fw - 0.1, "recess depth", "Z_seat+flange_t-(stiff_z0-plate_glue)",
            zt - zr, "<> +/-0.03", shift=7)
    sh.vdim(ox, oy, sy_ / 2 + fw, zf, sy_ / 2 + fw, zt, sy_ / 2 + fw + 0.6, "flange thickness", "flange_t", ft,
            "<> +/-0.05", shift=-13)
    sh.vdim(ox, oy, sy_ / 2 + fw, zf, dy_ / 2, zd, sy_ / 2 + fw + 1.4, "flange underside to doubler top",
            "side_nub_z-Z_seat", zd - zf, "<> +/-0.11", shift=14)
    sh.text("SECTION L  (plane X = 0, along the key, plate + doubler glued in, 12:1)", 34, 276, 3.0)
    # ---- section S (plane Y = 0; u = X, v = Z)
    sh.cur = "secS"
    ox, oy = O["secS"]
    sh.hdim(ox, oy, -sx / 2, z0, sx / 2, z0, zc - 0.6, "key width", "side_key[0]", sx, "<> -0.05/-0.15")
    sh.hdim(ox, oy, -sx / 2 - fw, zt, sx / 2 + fw, zt, zd + 0.95, "flange width", "side_key[0]+2*flange_side", sx + 2 * fw)
    sh.hdim(ox, oy, -rx / 2, zt, rx / 2, zt, zd + 0.45, "recess width", "plate_recess[0]", rx, "<> +0.05/0")
    sh.vdim(ox, oy, -sb / 2, zc, -sx / 2, z0, -sx / 2 - fw - 0.8, "chevron height", "chevron_h", p.chevron_h,
            "<> +/-0.05", shift=-10.5)
    sh.text("SECTION S  (plane Y = 0, across the key, 12:1)", 262, 281, 3.0)
    # ---- bottom view (u = Y, v = X)
    sh.cur = "bot"
    ox, oy = O["bot"]
    sh.hdim(ox, oy, -sy_ / 2, -sx / 2, sy_ / 2, -sx / 2, -sx / 2 - fw - 1.0, "key length", "side_key[1]", sy_)
    sh.vdim(ox, oy, sy_ / 2, -sx / 2, sy_ / 2, sx / 2, sy_ / 2 + fw + 1.0, "key width", "side_key[0]", sx)
    sh.leader(ox, oy, sb, sa, 50, 14, ["chevron %s deg, raised %s," % (
        V("chevron apex angle", 2 * math.degrees(math.atan2(sb, 2 * sa)), "2*atan(chevron[2]/(2*chevron[1]))", view="bot", md=0),
        V("chevron height", p.chevron_h, "chevron_h", view="bot", md=1)), "stroke %s, %s (X) x %s (Y);" % (
        V("chevron stroke", sw_, "chevron[0]", view="bot", md=1),
        V("chevron overall X", 2 * sa + sw_, "2*chevron[1]+chevron[0]", view="bot", md=1),
        V("chevron overall Y", 2 * sb + sw_, "2*chevron[2]+chevron[0]", view="bot", md=1)),
        "apex to -X (the head) as the", "next key; previous key:", "turned 180 deg (apex to the tail)"], h=2.0)
    sh.text("BOTTOM VIEW (from -Z, outer face, 8:1)", 40, 147, 3.0)
    # ---- top view (u = Y, v = -X): the recess of the inner face
    sh.cur = "top"
    ox, oy = O["top"]
    sh.hdim(ox, oy, -ry / 2, -rx / 2, ry / 2, -rx / 2, -sx / 2 - fw - 1.0, "recess length", "plate_recess[1]", ry, "<> +0.05/0")
    sh.vdim(ox, oy, ry / 2 - rr, -rx / 2, ry / 2 - rr, rx / 2, sy_ / 2 + fw + 1.0, "recess width", "plate_recess[0]", rx,
            "<> +0.05/0")
    q = rr * math.sqrt(0.5)
    sh.leader(ox, oy, -(ry / 2 - rr) - q, -(rx / 2 - rr) - q, -6, -9, "R%s" % V("recess corner radius", rr, "plate_recess[2]",
                                                                             view="top", md=1), h=2.2)
    sh.text("TOP VIEW (from +Z, inner face: the recess, 8:1)", 196, 147, 3.0)
    # ---- stiffener: plate with the doubler on its centre (u = Y, v = -X)
    sh.cur = "plate"
    ox, oy = O["plate"]
    sh.hdim(ox, oy, -ln_ / 2, 0, ln_ / 2, 0, -w_ / 2 - 1.0, "plate length", "stiffener[1]", ln_, "<> +0/-0.2")
    sh.vdim(ox, oy, ln_ / 2 - c_ - 0.2, -w_ / 2, ln_ / 2 - c_ - 0.2, w_ / 2, ln_ / 2 + 1.0, "plate width", "stiffener[0]", w_,
            "<> +0/-0.2")
    sh.hdim(ox, oy, -dy_ / 2, dx_ / 2, dy_ / 2, dx_ / 2, w_ / 2 + 0.9, "doubler size", "doubler[0]", dy_, "<> +/-0.2")
    sh.leader(ox, oy, -ln_ / 2 + c_ / 2, -w_ / 2 + c_ / 2, -6, -9, "4x %s x 45\u00b0" % V("plate corner clip", c_, "stiffener[3]",
                                                                                     view="plate", md=1), h=2.2)
    sh.text("STIFFENER: PLATE + DOUBLER (%s shim, 8:1)" % V("plate thickness", t_, "stiffener[2]", view="plate", md=1),
            317, 147, 3.0)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["1", "Rubber", "black PU rubber Shore A 80 cast at home in the mould FK-H-08 (resin print or aluminium), e.g.\n"
         "ECON 80 or PMC-780 DRY + black colorant (Sugru, pressed in, is Shore A 70); series: moulded silicone A 75-85",
         "Shore A 80 +/-5"],
        ["2", "Stiffener", "plate %s x %s, corners clipped %s x 45 deg, and doubler %s x %s, both %s stainless\n"
         "steel shim 1.4301: cut with tin snips (or laser cut), deburred, flat" % (
            n("plate width", w_, "stiffener[0]", md=1), n("plate length", ln_, "stiffener[1]", md=1),
            n("plate corner clip", c_, "stiffener[3]", md=1), n("doubler size", dx_, "doubler[0]", md=1),
            n("doubler size", dy_, "doubler[1]", md=1), n("plate thickness", t_, "stiffener[2]", md=1)),
         "outline +0/-0.2\nthickness +/-0.02"],
        ["3", "Gluing", "doubler on the plate centre, then the plate into the recess, doubler up; cyanoacrylate on\n"
         "degreased, roughened faces (Sugru keys: fresh Sugru); the doubler top presses the switch", "doubler top see\nsection L"],
        ["4", "Key", "%s x %s, R%s; flange %s x %s x %s on the floor of the tray; recess %s x %s R%s,\n%s deep in "
         "the inner face; no pocket, no nub" % (
            n("key width", sx, "side_key[0]", md=1), n("key length", sy_, "side_key[1]", md=1), n("key corner radius", sr, "side_key[2]", md=1),
            n("flange width", sx + 2 * fw, "side_key[0]+2*flange_side", md=1), n("flange length", sy_ + 2 * fw, "side_key[1]+2*flange_side", md=1),
            n("flange thickness", ft, "flange_t", dec=2), n("recess width", rx, "plate_recess[0]", md=1),
            n("recess length", ry, "plate_recess[1]", md=1), n("recess corner radius", rr, "plate_recess[2]", md=1),
            n("recess depth", zt - zr, "Z_seat+flange_t-(stiff_z0-plate_glue)", md=2)), "outline -0.05/-0.15\nothers: see sections"],
        ["5", "Surface", "key face as the mould leaves it (aluminium mould: matte, chevron top glossy; resin mould: the print's\n"
         "surface); no flash on the outer face; face edge R%s; cut the gate (flange end) and the vent stubs flush" % (
            n("face edge radius", 0.2, "0.2 (build_key_side)", md=1)), ""],
        ["6", "Quantity", "2 per light (next and previous are the same part, turned 180 deg), plus spares;\n"
         "the mould casts %d per pour" % p.mould_n, ""],
    ]
    sh.table(28, 136, (7, 28, 135, 30), rows, ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"], h=1.9, pad=0.9, line=2.7)
    ep = H.side_key_end_press(p)
    notes = ["NOTES",
             "1  Geometry per FlashKa_key_side.step (cast rubber), FlashKa_key_stiffener.step (plate + doubler in the "
             "glued position) and FlashKa_key_side_with_plate.step; in the STEP files the key sits in the housing "
             "frame at X %s, here it is centred." % V("next key X", p.X_next, "X_next", view="notes", md=1),
             "2  The plate makes the key a stiff rocker: pressed %s mm from one end it actuates the switch with "
             "%s N and %s mm of key travel (rubber only, without the plate: %s mm)." % (
                 V("end press distance", 2.0, "2.0 (side_key_end_press)", view="notes", md=1),
                 V("end press force", ep["press_force_at_click_N"], "side_key_end_press", view="notes", dec=3),
                 V("end press travel", ep["click"]["press_travel_mm"], "side_key_end_press", view="notes", dec=2, rnd=True),
                 V("end press travel rubber only", ep["without the stiffener plate (rubber only)"]["press_travel_at_click_mm"],
                   "side_key_end_press", view="notes", dec=1, rnd=True)),
             "3  Free play doubler -> switch %s mm at rest: flange underside to doubler top %s +/-0.11 worst case "
             "(recess floor +/-0.05, two shims +/-0.02 each, glue films %s)." % (
                 V("side key free play", p.pre_side, "pre_side", view="notes", dec=2),
                 V("flange underside to doubler top", zd - zf, "side_nub_z-Z_seat", view="notes", dec=2),
                 V("glue film", p.plate_glue, "plate_glue", view="notes", dec=2)),
             "4  General tolerances ISO 3302-1 class M2; home-cast keys +/-0.10 where no tolerance is given. Black "
             "throughout, no paint, no marking."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 136, 2.0, 1.0)
    return sh, locals()


def pom_sheet(p, out):
    """FK-H-05 POM-C parts: lid RF window insert, antenna spacer with the floor plug, laser sleeve (the v0.6 spacer
    ring went with the glass window)"""
    SC = 4.0
    sh = Sheet("POM-C PARTS (black)", "FK-H-05  FlashKa_rf_window.step, FlashKa_antenna_spacer.step,\n"
               "FlashKa_laser_sleeve.step", "1/1", scale_text="SCALE 4:1 (a: section 8:1)")
    V = make_V(sh.name)
    rfx0, rfx1, rfhy = p.rfw_box
    c = p.rfw_clear
    fl = p.rfw_flange
    ins = H.build_rf_window(p, texture=False).translate((-(rfx0 + rfx1) / 2, 0, 0))
    asp = H.build_antenna_spacer(p, texture=False)
    ax0 = asp.val().BoundingBox().xmin
    asp = asp.translate((-ax0, 0, 0))
    slv = H.build_laser_sleeve(p).translate((0, -p.Y_l, -p.Z_las))
    O = {"ins_top": (72, 236), "ins_sec": (72, 168 - 8.0 * (p.Z_ceil - p.rfw_flange_drop)),
         "asp_top": (160, 232), "asp_side": (160, 110), "asp_front": (290, 110),
         "slv": (50, 66), "slv_side": (72 - SC * p.las_recess, 66)}
    sh.view(hlr(ins.val().wrapped, (0, 0, 1), (1, 0, 0)), *O["ins_top"], "ins_top", hidden=False, scale=SC)
    secI, hatI = section_y(ins, 0.0, 0.12)
    sh.view(secI, *O["ins_sec"], "ins_sec", hidden=False, scale=8.0)
    sh.hatch(hatI, *O["ins_sec"])
    sh.view(hlr(asp.val().wrapped, (0, 0, 1), (1, 0, 0)), *O["asp_top"], "asp_top", hidden=False, scale=SC)
    sh.view(hlr(asp.val().wrapped, (0, -1, 0), (1, 0, 0)), *O["asp_side"], "asp_side", hidden=False, scale=SC)
    sh.view(hlr(asp.val().wrapped, (-1, 0, 0), (0, -1, 0)), *O["asp_front"], "asp_front", hidden=False, scale=SC)
    sh.view(hlr(slv.val().wrapped, (-1, 0, 0), (0, -1, 0)), *O["slv"], "slv", hidden=False, scale=SC)
    sh.view(hlr(slv.val().wrapped, (0, -1, 0), (1, 0, 0)), *O["slv_side"], "slv_side", hidden=False, scale=SC)
    # ---- (a) lid RF window insert
    sh.cur = "ins_top"
    ox, oy = O["ins_top"]
    L_i, W_i = rfx1 - rfx0 - 2 * c, 2 * (rfhy - c)
    fc = p.rfw_flange_clear
    L_f, W_f = rfx1 - rfx0 + 2 * (fl - fc), 2 * (rfhy + fl - fc)
    sh.hdim(ox, oy, -L_i / 2, -W_i / 2, L_i / 2, -W_i / 2, -W_f / 2 - 1.6, "insert plug length",
            "rfw_box[1]-rfw_box[0]-2*rfw_clear", L_i, "<> -0.02/-0.05")
    sh.vdim(ox, oy, L_i / 2, -W_i / 2, L_i / 2, W_i / 2, L_f / 2 + 1.6, "insert plug width", "rfw_y-2*rfw_clear", W_i,
            "<> -0.02/-0.05")
    sh.hdim(ox, oy, -L_f / 2, W_f / 2, L_f / 2, W_f / 2, W_f / 2 + 1.6, "insert flange length",
            "rfw_box[1]-rfw_box[0]+2*(rfw_flange-rfw_flange_clear)", L_f, "<> +/-0.05")
    sh.vdim(ox, oy, -L_f / 2, -W_f / 2, -L_f / 2, W_f / 2, -L_f / 2 - 1.6, "insert flange width",
            "rfw_y+2*(rfw_flange-rfw_flange_clear)", W_f, "<> +/-0.05")
    sh.text("(a) LID RF WINDOW INSERT - top (textured face), 4:1", 28, 282, 2.6)
    sh.cur = "ins_sec"
    ox, oy = O["ins_sec"]
    zfa = p.H - p.pan_depth
    zb = p.Z_ceil - p.rfw_flange_drop
    sh.vdim(ox, oy, -L_f / 2, zb, -L_i / 2, zfa, -L_f / 2 - 0.8, "insert height", "H-pan_depth-(Z_ceil-rfw_flange_drop)",
            zfa - zb)
    sh.vdim(ox, oy, L_f / 2, zb, L_f / 2, p.Z_ceil + p.rfw_flange_t, L_f / 2 + 0.8, "insert flange thickness",
            "rfw_flange_t+rfw_flange_drop", p.rfw_flange_t + p.rfw_flange_drop)
    sh.text("(a) section Y = 0, 8:1", 28, 184, 2.6)
    # ---- (b) antenna spacer
    bb = asp.val().BoundingBox()
    sh.cur = "asp_top"
    ox, oy = O["asp_top"]
    sh.hdim(ox, oy, bb.xmin, bb.ymin, bb.xmax, bb.ymin, bb.ymin - 1.6, "antenna spacer length",
            "X_batt0-0.05-(X_pcb1+0.15)", bb.xmax - bb.xmin)
    sh.vdim(ox, oy, bb.xmax, bb.ymin, bb.xmax, bb.ymax, bb.xmax + 1.6, "antenna spacer width", "2*(inner_half-0.1)",
            bb.ymax - bb.ymin)
    sh.text("(b) ANTENNA SPACER - top, 4:1", 150, 282, 2.6)
    sh.cur = "asp_side"
    ox, oy = O["asp_side"]
    fx0, fx1, fhy, fr = p.frw_box
    sh.vdim(ox, oy, bb.xmin, bb.zmin, bb.xmin, bb.zmax, bb.xmin - 1.6, "antenna spacer height",
            "Z_ceil-rfw_flange_drop-0.15-pan_depth", bb.zmax - bb.zmin)
    sh.leader(ox, oy, fx1 - c - ax0 - 0.5, p.pan_depth, 12, -6, ["floor RF plug, face Z %s (panel level)," % V(
        "plug face Z", p.pan_depth, "pan_depth", view="asp_side", md=1), "textured like the panels"], h=2.0)
    sh.text("(b) from -Y", 150, 180, 2.6)
    sh.cur = "asp_front"
    ox, oy = O["asp_front"]
    cy0, cy1, cz0, cz1 = H.cell_wire_channel(p)
    sh.vdim(ox, oy, bb.ymin, bb.zmin, bb.ymin, bb.zmax, -bb.ymax - 1.6, "antenna spacer height",
            "Z_ceil-rfw_flange_drop-0.15-pan_depth", bb.zmax - bb.zmin)
    sh.leader(ox, oy, 0.5 * (-cy1 - bb.ymin), cz0, 10, -14, ["cell-wire rebate (-Y), %s wide, open" % (
        V("cell-wire rebate width", cy1 - bb.ymin, "inner_half-0.1+cell_wire_channel[1]", view="asp_front", md=1)),
        "to the wall and the top; floor Z %s" % (V("rebate floor Z", cz0, "kb_z1+0.4", view="asp_front", md=1))], h=2.0)
    sh.text("(b) from the front (-X)", 256, 180, 2.6)
    # ---- (c) laser sleeve
    sh.cur = "slv"
    ox, oy = O["slv"]
    sh.hdim(ox, oy, -p.sleeve_od / 2, 0, p.sleeve_od / 2, 0, -p.sleeve_od / 2 - 1.4, "sleeve outer dia", "sleeve_od",
            p.sleeve_od, "%%c<>")
    q = p.sleeve_id / 2 * math.sqrt(0.5)
    sh.leader(ox, oy, -q, q, -4, 9, "Ø%s" % V("sleeve inner dia", p.sleeve_id, "sleeve_id", view="slv", md=1), h=2.2)
    sh.cur = "slv_side"
    ox, oy = O["slv_side"]
    sh.hdim(ox, oy, p.las_recess, -p.sleeve_od / 2, p.las_recess + p.sleeve_len, -p.sleeve_od / 2, -p.sleeve_od / 2 - 1.4,
            "sleeve length", "sleeve_len", p.sleeve_len)
    sh.text("(c) LASER SLEEVE (option), 4:1", 34, 30, 2.6)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["-", "Material", "POM-C (acetal copolymer), black, CNC; all three parts", ""],
        ["a", "Lid RF window insert\nFlashKa_rf_window.step",
         "plug %s x %s R%s in the lid opening (%s per side: it locates),\nface %s below the lid top, textured; flange %s x %s x %s\nin the pocket (%s per side, free: it carries the kit tabs)" % (
             n("insert plug length", L_i, "rfw_box[1]-rfw_box[0]-2*rfw_clear", md=2), n("insert plug width", W_i, "rfw_y-2*rfw_clear", md=2),
             n("insert plug radius", p.rfw_r - c, "rfw_r-rfw_clear", md=2), n("insert clearance", c, "rfw_clear", md=2),
             n("insert face below the lid top", p.pan_depth, "pan_depth", md=1),
             n("insert flange length", L_f, "rfw_box[1]-rfw_box[0]+2*(rfw_flange-rfw_flange_clear)", md=2),
             n("insert flange width", W_f, "rfw_y+2*(rfw_flange-rfw_flange_clear)", md=2),
             n("insert flange thickness", p.rfw_flange_t + p.rfw_flange_drop, "rfw_flange_t+rfw_flange_drop", md=1),
             n("insert flange clearance", fc, "rfw_flange_clear", md=2)),
         "plug -0.02/-0.05, flange\n+/-0.05 (free); flat 0.05"],
        ["b", "Antenna spacer\nFlashKa_antenna_spacer.step",
         "between the board and the cell; plug %s x %s fills the floor RF\nwindow flush with the panel floor (textured); cell-wire rebate\non the -Y side (open to the top); the antenna sits in the U;\nthe +Y wall ends 0.15 under the insert flange" % (
             n("floor plug length", fx1 - fx0 - 2 * c, "frw_box[1]-frw_box[0]-2*rfw_clear", md=2), n("floor plug width", 2 * (fhy - c), "2*(frw_box[2]-rfw_clear)", md=2)),
         "plug -0.02/-0.05"],
        ["c", "Laser sleeve (option)\nFlashKa_laser_sleeve.step", "Ø%s / Ø%s x %s, slit %s: only for a laser module thinner\nthan Ø%s" % (
            n("sleeve outer dia", p.sleeve_od, "sleeve_od", md=1), n("sleeve inner dia", p.sleeve_id, "sleeve_id", md=1),
            n("sleeve length", p.sleeve_len, "sleeve_len", md=1), n("sleeve slit", p.sleeve_slit, "sleeve_slit", md=1),
            n("laser module diameter", p.las_d, "las_d", md=1)), ""],
        ["-", "Texture (a, b)", "90 deg V grooves %s deep, pitch %s, at 45 deg on the housing grid" % (
            n("texture depth", p.tex_depth, "tex_depth", md=1), n("texture pitch", p.tex_pitch, "tex_pitch", md=1)), "depth +/-0.03"],
        ["-", "Quantity", "1 of a and b per light; c only when needed", ""],
    ]
    sh.table(232, 282, (7, 40, 92, 38), rows, ["ID", "PART", "SPECIFICATION", "TOLERANCE / NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  Geometry per the three STEP files (housing frame); the views here are moved to their own origins.",
             "2  General tolerances ISO 2768-mK; break edges 0.1; no burrs on the textured faces.",
             "3  POM does not bond well: the lid insert is held by its flange and the antenna spacer below it; for "
             "service a dot of cyanoacrylate with a polyolefin primer is enough.",
             "4  JLCCNC takes plastic parts from 30 x 20 x 8 mm only: order a and b plus a spare a as one machining "
             "kit, FlashKa_pom_kit.step (drawing FK-H-07). These single files are for shops that take small parts. "
             "There is no spacer ring (v0.6): the TIR optic stands on the LED board."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 230, 2.0, 1.0)
    return sh, locals()


# --------------------------------------------------------------------------
# machining kits (JLCCNC minimum size for plastic parts)
# --------------------------------------------------------------------------
def _kit_section(kit, y0, spacing):
    """section of a kit in the plane Y = y0, seen from -Y (u = X, v = Z): (polys, hatch)"""
    bb = kit.val().BoundingBox()
    keep = kit.intersect(H.rbox(bb.xmin - 5, bb.xmax + 5, y0, bb.ymax + 5, bb.zmin - 5, bb.zmax + 5))
    slab = kit.intersect(H.rbox(bb.xmin - 5, bb.xmax + 5, y0, y0 + 0.3, bb.zmin - 5, bb.zmax + 5))
    polys = hlr(keep.val().wrapped, (0, -1, 0), (1, 0, 0))
    loops = cut_loops(slab, "y", y0, lambda a, b, c: (a, c))
    return polys, hatch_segments(loops, spacing)


def kit_pmma_sheet(p, out):
    """FK-H-06 machining kit: three PMMA main keys hanging on tabs in a frame (JLCCNC)"""
    kit, info, pcs = H.build_pmma_kit(p)
    sh = Sheet("MACHINING KIT - PMMA MAIN KEYS (3x)", "FK-H-06  FlashKa_pmma_kit.step", "1/1",
               scale_text="SCALE 2:1, detail 6:1", tol_text="ISO 2768-mK")
    V = make_V(sh.name)
    X, Y, hk = info["size"]
    g, tw, th = info["gap"], info["tab"][0], info["tab"][1]
    zt0, zt1 = info["tab_plane_z"]
    c1 = info["parts"][0]["centre_xy"]
    hf = p.main_key[0] / 2 + p.flange_main
    zk0, zk1 = info["parts"][0]["z"]
    E = "build_pmma_kit"
    top = hlr(kit.val().wrapped, (0, 0, 1), (1, 0, 0), "v7_kit_pmma_top")
    secA, hatA = _kit_section(kit, c1[1], 0.5)
    O = {"top": (40.0, 212.0), "secA": (40.0, 172.0), "det": (40.0, 62.0)}
    sh.view(top, *O["top"], "top", hidden=False)
    sh.view(secA, *O["secA"], "secA", hidden=False)
    sh.hatch(hatA, *O["secA"])
    XD = 2 * c1[0]                                     # detail: the first cell with its walls
    secD, hatD = clip_view(secA, u1=XD), clip_segs(hatA, u1=XD)
    sh.view(secD, *O["det"], "det", hidden=False, scale=6.0)
    sh.hatch(hatD, *O["det"])
    # ---- top view
    sh.cur = "top"
    ox, oy = O["top"]
    sh.hdim(ox, oy, 0, 0, X, 0, -4.5, "kit length X", E + ": (n+1)*kit_wall+n*cell", X)
    sh.vdim(ox, oy, X, 0, X, Y, X + 4.0, "kit width Y", E + ": max(cell+2*kit_wall, kit_min[1]+2)", Y)
    k2 = info["parts"][1]["centre_xy"]
    tx, ty = k2[0], k2[1] + hf + g / 2                 # +Y tab of key 2 (the key lies turned over: it is the -Y tab of the part)
    sh.leader(ox, oy, tx, ty, 8, 20, ["%d tabs (3 per key) %s wide, %s long," % (info["n_tabs"],
        V("tab width", tw, "kit_tab[0]", view="top", md=1), V("tab length", g, "kit_gap", view="top", md=1)),
        "on the edge of the key flange"], h=2.2)
    k3 = info["parts"][2]["centre_xy"]
    sh.leader(ox, oy, k3[0] + 2.0, k3[1] - 2.0, 30, -10, ["main key (3x),", "outer face up"], h=2.2)
    sh.leader(ox, oy, X - 1.5, Y - 1.5, 12, 14, ["frame: scrap"], h=2.2)
    sh.cutline(ox, oy, (0, c1[1]), (X, c1[1]), "A", (0, 1), ext=3.5, shaft=2.5)
    sh.text("TOP VIEW (kit +Z: first setup), 2:1", 40, 278, 3.0)
    # ---- section A-A
    sh.cur = "secA"
    ox, oy = O["secA"]
    sh.vdim(ox, oy, 0, 0, 0, hk, -4.0, "kit height Z", "kit_h_pmma", hk)
    sh.text("SECTION A-A (through the key centres), 2:1", 40, 195, 3.0)
    # ---- detail: one cell, 6:1
    sh.cur = "det"
    ox, oy = O["det"]
    xe = c1[0] + hf                                    # +X flange edge (tab side)
    sh.vdim(ox, oy, 0, 0, 0, hk, -2.0, "kit height Z", "kit_h_pmma", hk)
    sh.vdim(ox, oy, xe + 0.4, 0, xe + 0.4, zt0, XD + 1.6, "tab plane Z (bottom)", E + ": (h-key)/2+flange from the face",
            zt0, shift=-6)
    sh.vdim(ox, oy, xe + 0.4, zt0, xe + 0.4, zt1, XD + 1.6, "tab height (flange thickness)", "flange_t", zt1 - zt0,
            shift=7)
    sh.hdim(ox, oy, xe, zt1, xe + g, zt1, hk + 1.2, "gap key flange - frame", "kit_gap", g)
    sh.leader(ox, oy, xe + g / 2, 0.5 * (zt0 + zt1), 45, -18, ["tab, %s x %s:" % (
        V("tab width", tw, "kit_tab[0]", view="det", md=1), V("tab height (flange thickness)", th, "flange_t", view="det", md=2)),
        "cut, file flush"], h=2.2)
    sh.leader(ox, oy, c1[0] - 2.0, zk1, -10, 21, ["outer face (frosted ring) up"], h=2.2)
    sh.leader(ox, oy, c1[0] - 2.6, zk0, -8, -24, ["light-input face and switch pocket down"], h=2.2)
    sh.text("DETAIL B (section A-A at the first key), 6:1", 40, 128, 3.0)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["1", "Material", "clear cast PMMA (acrylic, not extruded); stock at least %s thick" % n(
            "kit height Z", hk, "kit_h_pmma", md=1), "frame: scrap"],
        ["2", "Parts", "3x main key FlashKa_key_main.step (1 per light + 2 spares);\ngeometry, tolerances, finish: drawing FK-H-03", ""],
        ["3", "Orientation", "outer face up (kit +Z), centred in the kit height", ""],
        ["4", "Tabs", "%d, %s x %s, %s long, on the free edge of the key flange\n(never on the outer face, the frosted ring or a locating face)" % (
            info["n_tabs"], n("tab width", tw, "kit_tab[0]", md=1), n("tab height (flange thickness)", th, "flange_t", md=2),
            n("tab length", g, "kit_gap", md=1)), "cut, file flush"],
        ["5", "Machining", "3-axis, two setups. Top: outer face, frosted ring, edge break,\ncap below the flange. Bottom: light-input face, switch pocket,\nnub, cap above the flange. Cut the gaps to the tab plane last.", ""],
        ["6", "Finish", "after the tabs are cut: vapour or flame polish as FK-H-03;\nthe frosted ring stays matte", ""],
    ]
    sh.table(232, 282, (7, 22, 108, 36), rows, ["ID", "FEATURE", "SPECIFICATION", "NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  CUT THE TABS, FILE FLUSH: the tab witness must not stand proud of the flange edge; do not touch "
             "any other face.",
             "2  JLCCNC machines plastic parts from 30 x 20 x 8 mm only; this kit is %s x %s x %s. The single file "
             "FlashKa_key_main.step is for shops that take small parts." % (
                 n("kit length X", X, E, md=1), n("kit width Y", Y, E, md=1), n("kit height Z", hk, "kit_h_pmma", md=1)),
             "3  Geometry per FlashKa_pmma_kit.step (kit frame); the keys are identical to FlashKa_key_main.step.",
             "4  General tolerances: keys as FK-H-03; frame ISO 2768-c."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 178, 2.0, 1.0)
    # cross-check against the kit solid
    R = Rays(kit.val())
    bb = kit.val().BoundingBox()
    probe("PMMA kit length X", X, bb.xlen)
    probe("PMMA kit width Y", Y, bb.ylen)
    probe("PMMA kit height Z", hk, bb.zlen)
    iv = R.z(c1[0], c1[1] + hf + g / 2)                # through the +Y tab of the first key
    probe("PMMA kit tab bottom Z", zt0, iv[0][0] if iv else float("nan"))
    probe("PMMA kit tab top Z", zt1, iv[0][1] if iv else float("nan"))
    ix = R.x(c1[1] + 1.0, 0.5 * (zt0 + zt1))           # beside the +X tab, at the flange height
    gaps = [b_[0] - a_[1] for a_, b_ in zip(ix, ix[1:])]
    probe("PMMA kit gap frame - flange (first)", g, gaps[0] if gaps else float("nan"))
    return sh, locals()


def kit_pom_sheet(p, out):
    """FK-H-07 machining kit: one set of POM-C parts plus a spare lid RF insert hanging on tabs in a frame (JLCCNC)"""
    kit, info, pcs = H.build_pom_kit(p, texture=False)
    sh = Sheet("MACHINING KIT - POM-C PARTS", "FK-H-07  FlashKa_pom_kit.step", "1/1",
               scale_text="SCALE 2:1", tol_text="ISO 2768-mK")
    V = make_V(sh.name)
    X, Y, hk = info["size"]
    g, gt, tw, th = info["gap"], info["gap_spacer"], info["tab"][0], info["tab"][1]
    kt0, kt1 = info["tab_plane_z"]
    pa, pa2, pb = info["parts"]
    E = "build_pom_kit"
    top = hlr(kit.val().wrapped, (0, 0, 1), (1, 0, 0), "v7_kit_pom_top")
    yA, yB = pa["centre_xy"][1], pb["centre_xy"][1]
    secB, hatB = _kit_section(kit, yA, 0.5)
    secC, hatC = _kit_section(kit, yB, 0.5)
    O = {"top": (38.0, 186.0), "secB": (38.0, 132.0), "secC": (38.0, 82.0)}
    sh.view(top, *O["top"], "top", hidden=False)
    sh.view(secB, *O["secB"], "secB", hidden=False)
    sh.hatch(hatB, *O["secB"])
    sh.view(secC, *O["secC"], "secC", hidden=False)
    sh.hatch(hatC, *O["secC"])
    x0, x1, hy = p.rfw_box
    fo = p.rfw_flange - p.rfw_flange_clear
    # ---- top view
    sh.cur = "top"
    ox, oy = O["top"]
    sh.hdim(ox, oy, 0, 0, X, 0, -4.5, "kit length X", E + ": 3*kit_wall+4*insert cell", X)
    sh.vdim(ox, oy, X, 0, X, Y, X + 4.0, "kit width Y", E + ": 3*kit_wall+rows", Y)
    ca, cb = pa["centre_xy"], pb["centre_xy"]
    c2 = pa2["centre_xy"]
    sh.leader(ox, oy, c2[0] + 5.0, c2[1] + 2.0, 32, -4, ["a  lid RF window insert (2x),", "textured face up"], h=2.2)
    sh.leader(ox, oy, cb[0], cb[1] + 2.5, 4, 22, ["b  antenna spacer, floor plug up"], h=2.2)
    tx, ty = c2[0], c2[1] - ((x1 - x0) / 2 + fo) - g / 2       # a tab on a long flange edge of the spare insert
    sh.leader(ox, oy, tx, ty, 40, -12, ["%d tabs %s x %s, 3 per part," % (
        info["n_tabs"], V("tab width", tw, "kit_tab[0]", view="top", md=1), V("tab height", th, "kit_tab[1]", view="top", md=1)),
        "%s long (antenna spacer %s)," % (
        V("tab length", g, "kit_gap", view="top", md=1),
        V("tab length at the antenna spacer", gt, "kit_gap_tall", view="top", md=1)),
        "all in one plane"], h=2.2)
    sh.cutline(ox, oy, (0, yA), (X, yA), "B", (0, 1), ext=3.5, shaft=2.5)
    sh.cutline(ox, oy, (0, yB), (X, yB), "C", (0, 1), ext=3.5, shaft=2.5)
    sh.text("TOP VIEW (kit +Z: first setup), 2:1", 38, 280, 3.0)
    # ---- section B-B: the two lid inserts
    sh.cur = "secB"
    ox, oy = O["secB"]
    sh.vdim(ox, oy, 0, 0, 0, hk, -4.0, "kit height Z", "kit_h_pom", hk)
    xe = ca[0] - ((hy + fo))                                   # -X end of insert 1 in the kit (short flange edge, tab)
    sh.vdim(ox, oy, xe - g / 2, 0, xe - g / 2, kt0, -9.0, "tab plane Z (bottom)", E + ": spacer side face middle", kt0)
    sh.leader(ox, oy, xe - g / 2, kt1, 6, 12, ["tab plane (all tabs)"], h=2.2)
    sh.text("SECTION B-B (lid RF window inserts), 2:1", 38, 125, 3.0)
    # ---- section C-C: antenna spacer
    sh.cur = "secC"
    ox, oy = O["secC"]
    sh.vdim(ox, oy, 0, 0, 0, hk, -4.0, "kit height Z", "kit_h_pom", hk)
    sh.text("SECTION C-C (antenna spacer), 2:1", 38, 75, 3.0)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["1", "Material", "POM-C (acetal copolymer), black; stock at least %s thick" % n("kit height Z", hk, "kit_h_pom", md=1),
         "frame: scrap"],
        ["a", "Lid RF window\ninsert (2x)", "FlashKa_rf_window.step, 1 + 1 spare; textured face up; tabs on\nthe free flange edge, flush with the flange underside", "FK-H-05 (a)"],
        ["b", "Antenna spacer", "FlashKa_antenna_spacer.step; floor plug (textured) up; tabs on\nthe side faces (clear of the cavity walls, the plug locates it)", "FK-H-05 (b)"],
        ["-", "Tabs", "%d, %s x %s, one plane (Z %s to %s); never on a sealing or locating\nface or on a textured face" % (
            info["n_tabs"], n("tab width", tw, "kit_tab[0]", md=1), n("tab height", th, "kit_tab[1]", md=1),
            n("tab plane Z (bottom)", kt0, E, md=1), n("tab plane Z (top)", kt1, E, md=1)), "cut, file flush"],
        ["-", "Machining", "3-axis, two setups. Top: textured faces of a and b, chamfers of b.\nBottom: flange undersides of a, top side of b (U, rebate, tall wall).\nCut the gaps to the tab plane last.", ""],
        ["-", "Not in the kit", "laser sleeve (option): its slit along the axis needs a side setup;\nsingle file FlashKa_laser_sleeve.step", ""],
    ]
    sh.table(232, 282, (7, 26, 106, 34), rows, ["ID", "PART", "SPECIFICATION", "NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  CUT THE TABS, FILE FLUSH: no witness may stand proud of its face; break edges 0.1; no burrs on the "
             "textured faces.",
             "2  JLCCNC machines plastic parts from 30 x 20 x 8 mm only; this kit is %s x %s x %s. The single files "
             "(FK-H-05) are for shops that take small parts." % (
                 n("kit length X", X, E, md=1), n("kit width Y", Y, E, md=1), n("kit height Z", hk, "kit_h_pom", md=1)),
             "3  Geometry per FlashKa_pom_kit.step (kit frame); the parts are identical to their single files. The "
             "views here show the parts without the texture.",
             "4  General tolerances: parts as FK-H-05; frame ISO 2768-c."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 160, 2.0, 1.0)
    R = Rays(kit.val())
    bb = kit.val().BoundingBox()
    probe("POM kit length X", X, bb.xlen)
    probe("POM kit width Y", Y, bb.ylen)
    probe("POM kit height Z", hk, bb.zlen)
    iv = R.z(tx, ty)                                           # through a long-edge tab of insert 1
    probe("POM kit tab bottom Z (insert)", kt0, iv[0][0] if iv else float("nan"))
    probe("POM kit tab top Z (insert)", kt1, iv[0][1] if iv else float("nan"))
    return sh, locals()


# --------------------------------------------------------------------------
# casting mould of the side keys (key_mould.py)
# --------------------------------------------------------------------------
def _section_plane(solid, axis, pos, spacing):
    """section of a (large) solid in the plane axis = pos: 'x' seen from -X (u = -Y, v = Z), 'y' seen from -Y
    (u = X, v = Z) -> (polys, hatch)"""
    bb = solid.val().BoundingBox()
    big = (bb.xmin - 5, bb.xmax + 5, bb.ymin - 5, bb.ymax + 5, bb.zmin - 5, bb.zmax + 5)
    if axis == "x":
        keep = solid.intersect(H.rbox(pos, big[1], *big[2:]))
        slab = solid.intersect(H.rbox(pos, pos + 0.3, *big[2:]))
        polys = hlr(keep.val().wrapped, (-1, 0, 0), (0, -1, 0))
        loops = cut_loops(slab, "x", pos, lambda a, b, c: (-b, c))
    else:
        keep = solid.intersect(H.rbox(big[0], big[1], pos, big[3], big[4], big[5]))
        slab = solid.intersect(H.rbox(big[0], big[1], pos, pos + 0.3, big[4], big[5]))
        polys = hlr(keep.val().wrapped, (0, -1, 0), (1, 0, 0))
        loops = cut_loops(slab, "y", pos, lambda a, b, c: (a, c))
    return polys, hatch_segments(loops, spacing)


def mould_sheet(p, out):
    """FK-H-08 casting mould for the side keys, 4 keys per pour: the aluminium version (cavity half + lid, JLCCNC) and,
    beside it, the resin version (SLA, JLC3DP: the same cavities, ribbed back, printed pins, through bolts)"""
    import key_mould as KM
    cav, lid = KM.build_cavity_half(p), KM.build_lid(p)
    rcav, rlid = KM.build_resin_cavity_half(p), KM.build_resin_lid(p)
    sh = Sheet("CASTING MOULD - SIDE KEYS (4 PER POUR)", "FK-H-08  FlashKa_key_mould_cavity.step, _lid.step (aluminium);\n"
               "FlashKa_key_mould_resin_cavity.stl, _lid.stl (resin)", "1/1",
               scale_text="SCALES AS MARKED", tol_text="ISO 2768-mK")
    V = make_V(sh.name)
    X, Y = p.mould_size
    tc, tl = p.mould_t
    cxs = KM.cavity_x(p)
    c0 = cxs[0]
    sx, sy_, sr = p.side_key
    fw = p.flange_side
    zt = KM.key_top(p)
    zf, zface = p.Z_seat - zt, p.side_face_z - zt
    zgr = zface - p.chevron_h
    zpl = (p.stiff_z0 - p.plate_glue) - zt
    tg = math.tan(math.radians(p.mould_draft))
    cap_w, cap_l = sx + 2 * p.mould_cap_offset, sy_ + 2 * p.mould_cap_offset
    cap_w_face = cap_w - 2 * (zf - zface) * tg
    ys, yv = KM.sprue_y(p), KM.vent_hole_y(p)
    yend = sy_ / 2 + fw
    SC = 1.5
    O = {"cav": (68, 236), "lid": (170, 236), "secA": (104, 166.8), "secB": (140 - 10.0 * c0, 110),
         "rcav": (50, 34), "rlid": (110, 34), "rsec": (174, 33)}

    def no_tangent(pol):                       # sections: outlines and visible edges, no tangent (smooth) edges
        return {k: v for k, v in pol.items() if k != "smooth"}
    top = hlr(cav.val().wrapped, (0, 0, 1), (1, 0, 0), "v8_mould_cav")
    sh.view(top, *O["cav"], "cav", hidden=False, scale=SC)
    bot = hlr(lid.val().wrapped, (0, 0, -1), (1, 0, 0), "v8_mould_lid")          # seen from below: u = X, v = -Y
    sh.view(bot, *O["lid"], "lid", hidden=False, scale=SC)
    # section A-A: plane X = first cavity centre, closed mould, seen from -X: u = -Y, v = Z
    UA = (-7.0, 10.5, -2.2, 2.4)
    for nm, solid in (("secA", cav), ("secAl", lid)):
        pol, hat = _section_plane(solid, "x", c0, 0.5)
        sh.view(no_tangent(clip_view(pol, u0=UA[0], u1=UA[1], v0=UA[2], v1=UA[3])), *O["secA"], nm, hidden=False,
                scale=8.0)
        sh.hatch(clip_segs(hat, u0=UA[0], u1=UA[1], v0=UA[2], v1=UA[3]), *O["secA"])
    del sh.vboxes["secAl"]
    sh.frame(*O["secA"], *UA)
    # section B-B: plane Y = 0 through the first cavity (cavity half), seen from -Y: u = X, v = Z
    UB = (c0 - 3.8, c0 + 3.8, -2.4, 0.0)
    pol, hat = _section_plane(cav, "y", 0.0, 0.25)
    sh.view(no_tangent(clip_view(pol, u0=UB[0], u1=UB[1], v0=UB[2], v1=UB[3])), *O["secB"], "secB", hidden=False,
            scale=10.0)
    sh.hatch(clip_segs(hat, u0=UB[0], u1=UB[1], v0=UB[2], v1=UB[3]), *O["secB"])
    sh.frame(*O["secB"], *UB)
    # resin version, 1:1: cavity half from below (ribbed back), lid from above (ribbed back), section through a cavity
    sh.view(hlr(rcav.val().wrapped, (0, 0, -1), (1, 0, 0), "v8_mould_rcav_back"), *O["rcav"], "rcav", hidden=False, scale=1.0)
    sh.view(hlr(rlid.val().wrapped, (0, 0, 1), (1, 0, 0), "v8_mould_rlid_back"), *O["rlid"], "rlid", hidden=False, scale=1.0)
    rtc, rtl = p.resin_t
    for nm_, solid_ in (("rsec", rcav), ("rsecl", rlid)):
        pol, hat = _section_plane(solid_, "x", c0, 0.6)
        sh.view(no_tangent(pol), *O["rsec"], nm_, hidden=False, scale=2.0)
        sh.hatch(hat, *O["rsec"])
    del sh.vboxes["rsecl"]
    # ---- cavity half, top view
    sh.cur = "cav"
    ox, oy = O["cav"]
    sh.hdim(ox, oy, -X / 2, -Y / 2, X / 2, -Y / 2, -Y / 2 - 5.5, "mould length", "mould_size[0]", X)
    sh.vdim(ox, oy, -X / 2, -Y / 2, -X / 2, Y / 2, -X / 2 - 4.5, "mould width", "mould_size[1]", Y)
    sh.hdim(ox, oy, cxs[0], Y / 2, cxs[1], Y / 2, Y / 2 + 3.5, "cavity pitch", "mould_pitch", p.mould_pitch, "3x <>")
    sh.cutline(ox, oy, (c0, -Y / 2), (c0, Y / 2), "A", (1, 0), ext=2.5, shaft=2.0)
    sh.cutline(ox, oy, (c0 - 3.4, 0.0), (c0 + 3.4, 0.0), "B", (0, 1), ext=1.0, shaft=2.0)
    sh.text("CAVITY HALF from above (parting face), 1.5:1", 22, 272, 3.0)
    # ---- lid from below
    sh.cur = "lid"
    ox, oy = O["lid"]
    sh.hdim(ox, oy, -X / 2, Y / 2, X / 2, Y / 2, Y / 2 + 4.5, "mould length", "mould_size[0]", X)
    sh.leader(ox, oy, c0 + p.plate_recess[0] / 2, -1.0, 6, 25, ["4 plateaus %s x %s R%s, %s high" % (
        V("plateau width", p.plate_recess[0], "plate_recess[0]", view="lid", md=1),
        V("plateau length", p.plate_recess[1], "plate_recess[1]", view="lid", md=1),
        V("plateau corner radius", p.plate_recess[2], "plate_recess[2]", view="lid", md=1),
        V("plateau height", -zpl, "Z_seat+flange_t-(stiff_z0-plate_glue)", view="lid", md=2))], h=2.0)
    sh.text("LID from below (mould face), 1.5:1", 124, 272, 3.0)
    # ---- section A-A (u = -Y: the far end with the vent on the left, the gate and the sprue on the right)
    sh.cur = "secA"
    ox, oy = O["secA"]
    sh.vdim(ox, oy, -yend + 0.25, 0.0, -yend + 0.25, zf, -7.6, "flange depth", "flange_t", -zf, "<> +/-0.02",
            shift=12.3)
    sh.vdim(ox, oy, -yend + 0.25, 0.0, -4.4, zface, -9.0, "cavity depth (key face)", "Z_seat+flange_t-side_face_z",
            -zface, "<> +/-0.02")
    sh.leader(ox, oy, -6.5, -p.mould_vent[1] / 2, 6, -24, ["vent groove %s x %s to the edge" % (
        V("vent width", p.mould_vent[0], "mould_vent[0]", view="secA", md=1),
        V("vent depth", p.mould_vent[1], "mould_vent[1]", view="secA", md=1))], h=2.0)
    sh.leader(ox, oy, -yv, 1.0, 4, 15, ["vent hole %s + counterbore %s through the lid" % (
        "Ø" + V("vent hole", p.mould_vent_hole[0], "mould_vent_hole[0]", view="secA", md=1),
        "Ø" + V("vent counterbore", p.mould_vent_hole[1], "mould_vent_hole[1]", view="secA", md=1))], h=2.0)
    sh.leader(ox, oy, -ys - 0.9, -0.35, 24, 10, ["runner %s x %s," % (
        V("runner width", p.mould_runner[0], "mould_runner[0]", view="secA", md=1),
        V("runner depth", p.mould_runner[1], "mould_runner[1]", view="secA", md=2)),
        "gate on the flange end;", "pour hole %s through the lid" % (
        "Ø" + V("sprue diameter", p.mould_sprue_d, "mould_sprue_d", view="secA", md=1))], h=2.0)
    sh.text("SECTION A-A (closed mould, along a cavity, 8:1)", 22, 197, 3.0)
    # ---- section B-B
    sh.cur = "secB"
    ox, oy = O["secB"]
    sh.hdim(ox, oy, c0 - cap_w / 2, zf - 0.01, c0 + cap_w / 2, zf - 0.01, 0.5, "cap width at the flange step",
            "side_key[0]+2*mould_cap_offset", cap_w, "<> +/-0.02")
    sh.hdim(ox, oy, c0 - sx / 2 - fw, zf + 0.01, c0 + sx / 2 + fw, zf + 0.01, 1.1, "flange width at the flange step",
            "side_key[0]+2*flange_side", sx + 2 * fw, "<> +/-0.02")
    sh.vdim(ox, oy, c0 - 0.55, zgr, c0 + 1.5, zface, c0 + 4.5, "chevron groove depth", "chevron_h", p.chevron_h,
            "<> +/-0.02")
    sh.leader(ox, oy, c0 - cap_w / 2 + 0.03, (zf + zface) / 2, -14, 12, ["draft %s deg" % V(
        "mould draft", p.mould_draft, "mould_draft", view="secB", md=0)], h=2.0)
    q = 0.2 * math.sqrt(0.5)
    sh.leader(ox, oy, c0 - cap_w_face / 2 + 0.2 - q, zface + 0.2 - q, -12, -12.5, ["R%s floor radius" % V(
        "floor radius", 0.2, "0.2 (build_key_side)", view="secB", md=1)], h=2.0)
    sh.leader(ox, oy, c0 - 0.6, zgr + 0.03, 8, -16, ["chevron groove %s wide: %s end mill" % (
        V("chevron groove width", p.chevron[0], "chevron[0]", view="secB", md=1),
        "Ø" + V("chevron cutter", p.chevron[0], "chevron[0]", view="secB", md=1))], h=2.0)
    sh.text("SECTION B-B (across a cavity, cavity half, 10:1)", 22, 132, 3.0)
    # ---- resin version
    sh.cur = "rcav"
    ox, oy = O["rcav"]
    sh.leader(ox, oy, 0.5 * (cxs[0] + cxs[1]), 6.0, 4, 22, ["back pockets %s deep, rim %s," % (
        V("resin back pocket depth (cavity half)", rtc - KM.cavity_depth(p) - p.resin_floor,
          "resin_t[0]-cavity depth-resin_floor", view="rcav", md=2),
        V("resin rim", p.resin_rim, "resin_rim", view="rcav", md=1)), "ribs %s under the cavity columns" % V(
        "resin rib", p.resin_rib, "resin_rib", view="rcav", md=1)], h=2.0)
    sh.text("RESIN: CAVITY HALF from below, 1:1", 22, 13.5, 2.6)
    sh.cur = "rlid"
    ox, oy = O["rlid"]
    sh.leader(ox, oy, p.mould_screws[3][0], p.mould_screws[3][1], 6, 12, ["4x Ø%s through (M3 x %s," % (
        V("resin bolt hole", p.resin_bolt[0], "resin_bolt[0]", view="rlid", md=1),
        V("resin bolt length", p.resin_bolt[1], "resin_bolt[1]", view="rlid", md=0)), "washers, nuts)"], h=2.0)
    sh.text("RESIN: LID from above, 1:1", 88, 13.5, 2.6)
    sh.cur = "rsec"
    ox, oy = O["rsec"]
    sh.vdim(ox, oy, -Y / 2, -rtc, -Y / 2, 0.0, -Y / 2 - 3.0, "resin cavity half thickness", "resin_t[0]", rtc)
    sh.vdim(ox, oy, -Y / 2, 0.0, -Y / 2, rtl, -Y / 2 - 3.0, "resin lid thickness", "resin_t[1]", rtl)
    sh.text("RESIN: SECTION A-A (closed), 2:1", 150, 13.5, 2.6)
    n = lambda what, val, expr, **k_: V(what, val, expr, **k_)
    rows = [
        ["1", "Material", "aluminium 6061-T6, two parts %s x %s x %s; 1 set" % (
            n("mould length", X, "mould_size[0]", md=1), n("mould width", Y, "mould_size[1]", md=1),
            n("plate thickness", tc, "mould_t[0]", md=1)), ""],
        ["2", "Finish", "cavity half: fine glass-bead blast (matte key face), no anodising; the\nbuilder polishes the chevron groove floors (glossy chevron top);\nlid: as machined; both parting faces flat %s" % (
            n("parting face flatness", 0.02, "0.02 (drawing)", md=2)), ""],
        ["3", "Cavities", "%d, = side key FK-H-04 face down without its recess; draft %s deg\non cap and flange walls; cap %s x %s at the flange step (key\ntolerance -0.05/-0.15); no shrink allowance (PMC-780 DRY < 0.1 %%)" % (
            p.mould_n, n("mould draft", p.mould_draft, "mould_draft", md=0), n("cap width at the flange step", cap_w,
            "side_key[0]+2*mould_cap_offset", md=2), n("cap length at the flange step", cap_l, "side_key[1]+2*mould_cap_offset", md=2)),
         "outlines, depths\n+/-0.02"],
        ["4", "Cutters", "chevron groove Ø%s end mill along its centre line (R%s, the smallest\nradius); floor radius R%s: bull-nose or ball cutter; runner Ø%s; corners of\nrunners, vent grooves and pry slots not dimensioned: tool radius, R%s max" % (
            n("chevron cutter", p.chevron[0], "chevron[0]", md=1), n("chevron groove radius", p.chevron[0] / 2, "chevron[0]/2", md=1),
            n("floor radius", 0.2, "0.2 (build_key_side)", md=1), n("runner width", p.mould_runner[0], "mould_runner[0]", md=1),
            n("corner radius limit (tool)", p.mould_runner[0] / 2, "mould_runner[0]/2", md=1)), ""],
        ["5", "Holes", "dowels: 2x Ø%s H7, %s deep (cavity half), 2x Ø2.02-2.03 through (lid);\nM3: 4x thread %s deep, drill Ø%s x %s (cavity half), 4x Ø%s through (lid);\nper cavity pour hole Ø%s and vent Ø%s (counterbore Ø%s) through the lid" % (
            n("dowel diameter", p.mould_dowel[0], "mould_dowel[0]", md=1), n("dowel press depth", p.mould_dowel[2], "mould_dowel[2]", md=1),
            n("M3 thread depth", p.mould_m3[2], "mould_m3[2]", md=1), n("M3 tap drill", p.mould_m3[0], "mould_m3[0]", md=1),
            n("M3 drill depth", p.mould_m3[1], "mould_m3[1]", md=1), n("M3 clearance", p.mould_m3[3], "mould_m3[3]", md=1),
            n("sprue diameter", p.mould_sprue_d, "mould_sprue_d", md=1), n("vent hole", p.mould_vent_hole[0], "mould_vent_hole[0]", md=1),
            n("vent counterbore", p.mould_vent_hole[1], "mould_vent_hole[1]", md=1)), "H7 reamed"],
        ["6", "Bought", "2 dowel pins ISO 8734 Ø%s m6 x %s; 4 socket head screws ISO 4762\nM3 x 12, stainless steel" % (
            n("dowel diameter", p.mould_dowel[0], "mould_dowel[0]", md=1), n("dowel length", p.mould_dowel[1], "mould_dowel[1]", md=1)), ""],
        ["7", "Resin version\n(default)", "SLA resin print, JLC3DP: the same cavities, plateaus, runners, vents\nand pry slots; plates %s and %s thick, ribbed back; printed pins Ø%s\n(sockets Ø%s); 4x M3 x %s through bolts, washers, nuts; no threads" % (
            n("resin cavity half thickness", p.resin_t[0], "resin_t[0]", md=1), n("resin lid thickness", p.resin_t[1], "resin_t[1]", md=1),
            n("resin pin diameter", p.resin_pin[0], "resin_pin[0]", md=1), n("resin socket diameter", p.resin_pin[3], "resin_pin[3]", md=1),
            n("resin bolt length", p.resin_bolt[1], "resin_bolt[1]", md=0)),
         "print parting face\nup; mould release\nbefore every pour"],
    ]
    sh.table(232, 282, (7, 22, 108, 36), rows, ["ID", "FEATURE", "SPECIFICATION", "NOTE"], h=1.9, pad=0.9, line=2.7)
    notes = ["NOTES",
             "1  Press the dowel pins into the cavity half; they stand %s above the parting face. They are offset, so "
             "the lid fits one way only." % V("dowel height above the parting face", p.mould_dowel[1] - p.mould_dowel[2],
                                              "mould_dowel[1]-mould_dowel[2]", view="notes", md=1),
             "2  Once, on arrival: polish the floor of each chevron groove (sharpened toothpick, metal polish) for a "
             "glossy chevron top. Before each pour: clean both halves, spray a mould release made for urethane "
             "rubber and let it dry.",
             "3  Stand the cavity half level. Pour the mixed rubber slowly into one corner of each cavity until it is "
             "level with the parting face. Lower the lid over the dowels slowly; the surplus leaves through the pour "
             "holes and the vents. Fit the four M3 screws, tightened evenly.",
             "4  Gates and vents sit on the flange end and on the hidden inner face, never on the key face. After the "
             "cure open the mould with a screwdriver in the pry slots, cut the stubs flush and glue the stiffener in "
             "(FK-H-04). Casting steps: 3_rubber_keys/README.txt.",
             "5  JLCCNC: upload FlashKa_key_mould_cavity.step and FlashKa_key_mould_lid.step as two parts with this "
             "drawing; each is %s x %s x %s or more." % (
                 V("mould length", X, "mould_size[0]", view="notes", md=1), V("mould width", Y, "mould_size[1]", view="notes", md=1),
                 V("plate thickness", tc, "mould_t[0]", view="notes", md=1)),
             "6  Resin version (7, the cheap default): JLC3DP, SLA resin, upload FlashKa_key_mould_resin_cavity.stl and "
             "_lid.stl as two parts; print with the parting face up so that supports touch only the ribbed back. The "
             "pins are offset like the dowels. Resin does not hold the aluminium tolerances: check a cast key in its "
             "opening. Mould release is needed on every face before each pour (urethane: a urethane mould "
             "release; Sugru: petroleum jelly)."]
    lines = [ln for n_ in notes for ln in wrap(n_, 80.0, 2.0)]
    sh.mtext(lines, 236, 192, 2.0, 1.0)
    # cross-check against the mould solids
    RC, RL = Rays(cav.val()), Rays(lid.val())
    bb = cav.val().BoundingBox()
    probe("mould cavity half length X", X, bb.xmax - bb.xmin, tol=0.02)
    probe("mould cavity half width Y", Y, bb.ymax - bb.ymin, tol=0.02)
    iz = RC.z(c0 + 1.2, 2.5)
    probe("mould cavity depth at the key face", -zface, -iz[0][1] if iz else float("nan"))
    ig = RC.z(c0 - p.chevron[1], 0.0)                                  # chevron apex point (next key: apex at -X)
    probe("mould chevron groove floor depth", -zgr, -ig[0][1] if ig else float("nan"))
    il = RL.z(c0, 0.0)
    probe("mould plateau height", -zpl, -il[0][0] if il else float("nan"))
    ix = RC.iv((0.0, 0.0, zf - 0.01), (1, 0, 0), t0=-X)                 # the ray starts outside the 48 mm block
    gaps = [(b_[0] - a_[1], (a_[1] + b_[0]) / 2) for a_, b_ in zip(ix, ix[1:])]
    g0 = [g for g, c in gaps if abs(c - c0) < 0.5]
    probe("mould cap width at the flange step (first cavity)", cap_w, g0[0] if g0 else float("nan"))
    iy = RC.iv((c0 + 0.7, 0.0, zf + 0.01), (0, 1, 0), t0=-Y)           # beside the runner (half width 0.6)
    gy = [(b_[0] - a_[1], (a_[1] + b_[0]) / 2) for a_, b_ in zip(iy, iy[1:])]
    probe("mould flange pocket length at its floor (first cavity)", sy_ + 2 * fw,
          max((g for g, c in gy if abs(c) < 1.5), default=float("nan")), tol=0.03)
    # resin version: same cavities, plate thicknesses
    RR, RRL = Rays(rcav.val()), Rays(rlid.val())
    irz = RR.z(c0 + 1.2, 2.5)
    probe("resin mould cavity depth at the key face", -zface, -irz[0][1] if irz else float("nan"))
    irg = RR.z(c0 - p.chevron[1], 0.0)
    probe("resin mould chevron groove floor depth", -zgr, -irg[0][1] if irg else float("nan"))
    irb = RR.z(-X / 2 + 1.0, -Y / 2 + 1.0)                             # in the rim
    probe("resin cavity half thickness", p.resin_t[0], irb[0][1] - irb[0][0] if irb else float("nan"))
    irl = RRL.z(-X / 2 + 1.0, -Y / 2 + 1.0)
    probe("resin lid thickness", p.resin_t[1], irl[0][1] - irl[0][0] if irl else float("nan"))
    irp = RRL.z(c0, 0.0)
    probe("resin mould plateau height", -zpl, -irp[0][0] if irp else float("nan"))
    return sh, locals()


# --------------------------------------------------------------------------
# cross-check against the solids
# --------------------------------------------------------------------------
def audit(p, plain, lid_p, kmain, kside):
    R, RL, RM, RS = Rays(plain.val()), Rays(lid_p.val()), Rays(kmain.val()), Rays(kside.val())
    ih = p.inner_half
    rb, rl = p.opt_bore / 2, (p.las_d + p.las_clear) / 2
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
    probe("optic bore diameter", 2 * rb, width(iv, p.Y_w))
    probe("optic bore axis Y", p.Y_w, centre(iv, p.Y_w))
    probe("optic bore floor X (depth D_w)", p.D_w, R.x(p.Y_w, p.Z_axis)[0][0])
    probe("solid head block behind the optic bore floor", p.L_head - p.D_w,
          R.x(p.Y_w, p.Z_axis)[0][1] - R.x(p.Y_w, p.Z_axis)[0][0])
    (yht, zht), (yhb, zhb) = H.led_wire_hole_yz(p)
    for nm_, (yh_, zh_) in (("upper", (yht, zht)), ("lower", (yhb, zhb))):
        ivh = R.y(10.0, zh_)
        probe("LED wire hole %s: Y centre (X 10)" % nm_, yh_, centre(ivh, yh_))
        probe("LED wire hole %s: diameter (X 10)" % nm_, p.ledwire_d, width(ivh, yh_))
    ivg = R.x(p.Y_w + (rb + 0.5) * math.sin(math.radians(p.led_wire_ang)),
              p.Z_axis + (rb + 0.5) * math.cos(math.radians(p.led_wire_ang)))
    probe("LED wire groove (upper): start X", p.x_led_board - 1.0, ivg[0][1] if ivg else nan)
    ivt = R.x(p.screw_dy, p.Z_lid - 1.0)
    probe("front lid tap X", p.screw_x_front, centre(ivt, p.screw_x_front))
    iz = R.z(2.0, p.Y_l)
    probe("laser bore diameter (Z span)", 2 * rl, width(iz, p.Z_las))
    probe("laser axis Z", p.Z_las, centre(iz, p.Z_las))
    probe("laser axis Y", p.Y_l, centre(R.y(2.0, p.Z_las), p.Y_l))
    ixs = R.x(p.las_set[1], p.Z_lid - 1.0)
    probe("laser set-screw hole X", p.las_set[0], centre(ixs, p.las_set[0]))
    probe("laser set-screw tap drill (X span)", p.m16_tap, width(ixs, p.las_set[0]))
    probe("laser set-screw hole Y", p.las_set[1], centre(R.y(p.las_set[0], p.Z_lid - 1.0), p.las_set[1]))
    probe("no hole in the bottom face under the laser (solid to the bore)", p.Z_las - rl, R.z(6.0, p.Y_l)[0][1])
    probe("PCB ledge height Z_pcb_bot", p.Z_pcb_bot, R.z(40.0 - 10, ih - 0.4)[0][1])
    probe("trough width between the ledges", 2 * (ih - p.ledge_w), width(R.y(26.0, p.Z_pcb_bot - 0.3), 0.0))
    lay_ = {q["name"]: q for q in H.panel_layout(p)}
    xband = 0.5 * (lay_["bottom bay 1 (with the RF window)"]["u1"] + lay_["bottom bay 2"]["u0"])
    probe("floor thickness (band between the bottom panels, X %.2f)" % xband, p.floor, R.z(xband, 0.0)[0][1])
    probe("side wall top at the lid seat (Z_lid)", p.Z_lid, R.z(60.0, 9.0)[0][1])
    # key openings and bezel
    probe("main key opening X", p.main_key[0] + 2 * p.key_clear, width(R.x(0.0, 1.0), p.X_main))
    probe("main key opening centre X", p.X_main, centre(R.x(0.0, 1.0), p.X_main))
    probe("next key opening X", p.side_key[0] + 2 * p.key_clear, width(R.x(0.0, 1.0), p.X_next))
    probe("previous key opening Y", p.side_key[1] + 2 * p.key_clear_end, width(R.y(p.X_prev, 1.0), 0.0))
    probe("bezel floor Z (beside the next key)", p.bez_depth, R.z(p.X_next, p.side_key[1] / 2 + p.key_clear_end + 0.1)[0][0])
    # bosses and ribs
    for (x, y) in p.kb_holes:
        probe("KB boss top Z at the boss edge (%g, %+g)" % (x, y), p.kb_z0, R.z(x + 1.2, y)[0][1])
        probe("KB tap drill diameter (%g, %+g)" % (x, y), p.m16_tap, width(R.x(y, p.kb_z0 - 0.5), x))
    for (x, s) in p.kb_ribs:
        probe("KB rib top Z (%g, %s)" % (x, "+Y" if s > 0 else "-Y"), p.kb_z0, R.z(x, s * (p.rib_y0 + 0.4))[0][1])
    fx0, fx1, fhy, fr = p.frw_box
    probe("floor RF window length", fx1 - fx0, width(R.x(0.0, 1.0), 0.5 * (fx0 + fx1)))
    probe("floor RF window width", 2 * fhy, width(R.y(0.5 * (fx0 + fx1), 1.0), 0.0))
    zl = RL.z(50.0, 0.0)
    probe("lid thickness (bay, no panels)", p.lid_t, zl[0][1] - zl[0][0])
    ys = RL.y(50.0, p.Z_lid + 0.05)
    probe("lid seat width (X 50, +Y side)", p.wall * math.sqrt(2), ys[-1][1] - ys[-1][0] if ys else nan)
    probe("can boss face Z", p.Z_ceil - p.boss_h, RL.z(0.5 * (p.boss_box[0] + p.boss_box[1]), 0.0)[0][0])
    probe("front boss face Z", p.Z_pcb_top + p.pad2_gap,
          RL.z(0.5 * (p.boss2_box[0] + p.boss2_box[1]), 0.5 * (p.boss2_box[2] + p.boss2_box[3]))[0][0])
    # keys
    zm = RM.z(p.X_main + 3.0, p.key_y)
    probe("main key height (outer face to top face)", p.main_top_z - p.main_face_z, zm[-1][1] - zm[0][0])
    probe("main key nub top Z", p.main_nub_z, RM.z(p.X_main, p.key_y)[-1][1])
    probe("main key width X", p.main_key[0], RM.x(p.key_y, 0.8)[-1][1] - RM.x(p.key_y, 0.8)[0][0])
    # probes stay on the straight parts of the rounded outlines (|offset| < half size - corner radius)
    probe("main key flange X", p.main_key[0] + 2 * p.flange_main, RM.x(p.key_y + 1.0, 1.7)[-1][1] - RM.x(p.key_y + 1.0, 1.7)[0][0])
    zs = RS.z(p.X_next, p.key_y)
    probe("side key doubler top Z (presses the switch)", p.side_nub_z, zs[-1][1])
    probe("side key length Y", p.side_key[1], RS.y(p.X_next + 0.3, 0.6)[-1][1] - RS.y(p.X_next + 0.3, 0.6)[0][0])
    probe("side key flange Y", p.side_key[1] + 2 * p.flange_side,
          RS.y(p.X_next + 0.3, 1.7)[-1][1] - RS.y(p.X_next + 0.3, 1.7)[0][0])
    probe("side key plate top Z (beside the doubler)", p.stiff_z0 + p.stiffener[2], RS.z(p.X_next + 0.5, p.key_y + 3.0)[-1][1])


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
    sh1, _ = tray_sheet1(p, out, housing_dir)
    sh2, _ = tray_sheet2(p, out, housing_dir)
    shl, _ = lid_sheet(p, out, housing_dir)
    shm, _ = key_main_sheet(p, out)
    shs, _ = key_side_sheet(p, out)
    shp, _ = pom_sheet(p, out)
    shk1, _ = kit_pmma_sheet(p, out)
    shk2, _ = kit_pom_sheet(p, out)
    shmo, _ = mould_sheet(p, out)
    findings = sum(sh.check() for sh in (sh1, sh2, shl, shm, shs, shp, shk1, shk2, shmo))
    p1 = sh1.save(os.path.join(out, "FlashKa_tray_drawing.dxf"), os.path.join(out, "_sheet1.pdf"))
    p2 = sh2.save(os.path.join(out, "FlashKa_tray_drawing_sheet2.dxf"), os.path.join(out, "_sheet2.pdf"))
    pdf = os.path.join(out, "FlashKa_tray_drawing.pdf")
    merge_pdfs([p1, p2], pdf)
    for tmp in (p1, p2):
        os.remove(tmp)
    png_from_pdf(pdf, 0, os.path.join(out, "FlashKa_tray_drawing.png"), dpi=150)
    png_from_pdf(pdf, 1, os.path.join(out, "FlashKa_tray_drawing_sheet2.png"), dpi=150)
    for sh, base in ((shl, "FlashKa_lid_drawing"), (shm, "FlashKa_key_main_drawing"),
                     (shs, "FlashKa_key_side_drawing"), (shp, "FlashKa_pom_parts_drawing"),
                     (shk1, "FlashKa_pmma_kit_drawing"), (shk2, "FlashKa_pom_kit_drawing"),
                     (shmo, "FlashKa_key_mould_drawing")):
        pd = sh.save(os.path.join(out, base + ".dxf"), os.path.join(out, base + ".pdf"))
        png_from_pdf(pd, 0, os.path.join(out, base + ".png"), dpi=150)
    plain = H.build_tray(p, texture="none")
    lid_p = H.build_lid(p, texture="none")
    audit(p, plain, lid_p, H.build_key_main(p, icon=False),
          H.build_key_side(p, p.X_next, -1).union(H.build_key_stiffener(p, p.X_next)))
    lines, bad, nb = dimension_table(os.path.join(out, "drawings_dimension_table.txt"))
    print("\n".join(lines if table else lines[-3:]))
    print("layout findings: %d; number-vs-P mismatches: %d; solid mismatches: %d" % (findings, len(bad), len(nb)))
    import order_files                       # the order folders carry copies of the PDFs: refresh them
    if order_files.is_package_cad(out):
        order_files.copy(("pdf",))
    return findings, bad, nb


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    here = os.path.dirname(os.path.abspath(__file__))
    cad = os.path.join(here, "..", "..", "cad")
    main(args[0] if args else cad, args[1] if len(args) > 1 else cad, table="--quiet" not in sys.argv)
