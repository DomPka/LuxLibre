#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Dimensioned drawings of the EDCO bodies (DXF, plus PDF and PNG for people):

  edco-v01/cad/EDCO_body_drawing.*          EDCO v0.1
  edco-v02/cad/EDCO-18_body_drawing.*       EDCO v0.2, 18500 size
  edco-v02/cad/EDCO-14_body_drawing.*       EDCO v0.2, 14500 size
  edco-mini/cad/EDCO_Mini-16_body_drawing.* EDCO Mini-16 and Mini-16M
  edco-mini/cad/EDCO_Mini-14_body_drawing.* EDCO Mini-14 and Mini-14M
  edco-prism/cad/EDCO_Prism_body_drawing.*  EDCO Prism and PrismM

Each sheet is an A3 drawing at 2:1, made from the same parameters (class P of each design's housing script) as the
STEP files and in the style of the FlashKa v0.7 drawings, whose helpers it uses (hidden-line projection, section
hatching, dimensions, layout check). Where a design has an M version, the M body is drawn: it is the plain body plus
two magnet pockets, marked "M version only".

Every dimension is registered against its parameter, and the main ones are measured on the solid with ray probes;
both checks are printed (and written to hardware/tools/edco_drawings_check.txt).

usage:  python3 hardware/tools/edco_drawings.py [v01 v02-18 v02-14 mini-16 mini-14 prism]
Environment: FK_CACHE=<dir> caches the hidden-line projections while the layout is tuned.
"""
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
DATE = "2026-10-24"


def load(rel, name):
    path = os.path.join(HW, rel)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


D = load("flashka-keychain-v07/tools/housing/drawings.py", "fk_drawings")
import cadquery as cq  # noqa: E402

num = D.num
SC = 2.0                                   # drawing scale 2:1
COL_X = 244.0                              # right column: end views, feature table, notes
TABLE_COLS = (6.0, 31.0, 89.0, 34.0)


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def wrap(s, width, h):
    return "\n".join(D.wrap(s, width, h))


class ESheet(D.Sheet):
    """the FlashKa sheet with the EDCO project line in the title block"""

    def __init__(self, project, *a, **k):
        self.project = project
        super().__init__(*a, **k)

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
        lines = f"Part: {self.partno}".split("\n")
        if len(lines) == 1:
            self.text(lines[0], x0 + 3, y0 + 16, 3.0, track=False)
        else:
            for i, ln in enumerate(lines[:2]):
                self.text(ln, x0 + 3, y0 + 19.2 - i * 4.4, 2.2, track=False)
        self.text(f"{self.project}  {DATE}", x0 + 3, y0 + 4, 2.5, track=False)
        self.text(f"{self.scale_text}   SHEET {self.sheet}", x0 + 113, y0 + 16, 2.2, track=False)
        self.text(f"Units mm  |  {self.tol_text}", x0 + 113, y0 + 4, 2.5, track=False)


# ------------------------------------------------------------------------------------------ projections
def project(body, key):
    """top (+Z), bottom (-Z), front (-X) and tail (+X) views, and section A-A at Y = 0 seen from -Y"""
    w = body.val().wrapped
    v = {"top": D.hlr(w, (0, 0, 1), (1, 0, 0), key + "_top"),
         "bot": D.hlr(w, (0, 0, -1), (1, 0, 0), key + "_bot"),
         "front": D.hlr(w, (-1, 0, 0), (0, -1, 0), key + "_front"),
         "tail": D.hlr(w, (1, 0, 0), (0, 1, 0), key + "_tail")}
    half = body.intersect(box(-5, 200, 0, 60, -60, 60))
    v["sec"] = D.hlr(half.val().wrapped, (0, -1, 0), (1, 0, 0), key + "_sec")
    slab = body.intersect(box(-5, 200, 0, 0.3, -60, 60))
    loops = D.cut_loops(slab, "y", 0.0, lambda a, b, c: (a, c))
    v["hatch"] = D.hatch_segments(loops, 0.8)
    return v


class Probe:
    """main dimensions measured on the solid"""

    def __init__(self, body, name):
        self.r = D.Rays(body.val())
        self.name = name
        self.rows = []

    def add(self, what, drawn, measured, tol=0.02):
        self.rows.append((self.name, what, drawn, measured, abs(drawn - measured) <= tol))

    def span(self, ivs):
        return ivs[-1][1] - ivs[0][0] if ivs else 0.0

    def x(self, y, z):
        return self.r.x(y, z)

    def z(self, x, y):
        return [(round(a, 3), round(b, 3)) for a, b in self.r.iv((x, y, 0.0), (0, 0, 1), t0=-30.0)]

    def y(self, x, z):
        return self.r.y(x, z)


# ------------------------------------------------------------------------------------------ sheet
class Spec:
    """one body drawing: design module, parameters, names, and the family's dimensioning"""

    def __init__(self, key, mod, p, body, project, partno, out, family):
        self.key, self.mod, self.p, self.body = key, mod, p, body
        self.project, self.partno, self.out, self.family = project, partno, out, family


def body_sheet(s, checks):
    p, body = s.p, s.body
    bb = body.val().BoundingBox()
    x0 = bb.xmin
    rmax = max(bb.zmax, -bb.zmin, bb.ymax, -bb.ymin)
    v = project(body, s.key)
    sh = ESheet(s.project, "BODY", s.partno, "1/1", scale_text="SCALE 2:1")
    ox = 46.0 - SC * x0
    yT = 287.0 - 13.0 - SC * rmax
    yS = yT - 2 * SC * rmax - 25.0
    yB = yS - 2 * SC * rmax - 31.0
    T, S, B = (ox, yT), (ox, yS), (ox, yB)
    EF, ET = (COL_X + 34.0, yT), (COL_X + 120.0, yT)
    sh.view(v["top"], *T, "top", hidden=False)
    sh.view(v["sec"], *S, "sec", hidden=False)
    sh.hatch(v["hatch"], *S)
    sh.view(v["bot"], *B, "bot", hidden=False)
    sh.view(v["front"], *EF, "front", hidden=False)
    sh.view(v["tail"], *ET, "tail", hidden=False)
    for (o, l1, l2) in ((T, "TOP VIEW", "(from +Z)"), (S, "SECTION A-A", "(Y = 0)"), (B, "BOTTOM VIEW", "(from -Z)")):
        sh.title_of(l1, 13.0, o[1] + SC * rmax + 6.0)
        sh.text(l2, 13.0, o[1] + SC * rmax + 1.6, 2.5)
        sh.line((ox + SC * x0 - 3.0, o[1]), (ox + SC * bb.xmax + 3.0, o[1]), layer="CENTER")
    for o in (EF, ET):
        sh.line((o[0] - SC * rmax - 2.5, o[1]), (o[0] + SC * rmax + 2.5, o[1]), layer="CENTER")
        sh.line((o[0], o[1] - SC * rmax - 2.5), (o[0], o[1] + SC * rmax + 2.5), layer="CENTER")
    sh.title_of("VIEW B (front)", EF[0] - 16, yT + SC * rmax + 4.5)
    sh.title_of("VIEW C (tail)", ET[0] - 15, yT + SC * rmax + 4.5)
    # cutting plane A-A in the top view: Y = 0, looking from -Y (paper down -> the arrows point up)
    sh.cur = "top"
    sh.cutline(*T, (x0 - 2.5, 0.0), (bb.xmax + 2.5, 0.0), "A", (0.0, 1.0), ext=0.5, shaft=3.0)
    pr = Probe(body, s.key)
    sh.rmax = rmax
    rows, notes = s.family(sh, s.p, T, S, B, EF, ET, rmax, pr)
    yt = EF[1] - SC * rmax - 21.0
    sh.text("FEATURES", COL_X, yt + 2.0, 2.5)
    yb = sh.table(COL_X, yt, TABLE_COLS, [[str(r[0]), wrap(r[1], TABLE_COLS[1] - 2, 2.0),
                                           wrap(r[2], TABLE_COLS[2] - 2, 2.0), wrap(r[3], TABLE_COLS[3] - 2, 2.0)]
                                          for r in rows], ["ID", "FEATURE", "SPECIFICATION", "TOLERANCE / NOTE"],
                  h=2.0, pad=0.9, line=3.0)
    y = yb - 5.0
    sh.text("NOTES", COL_X, y, 2.5)
    y -= 4.2
    for i, n in enumerate(notes):
        lines = D.wrap(f"{i + 1} {n}", 160.0, 2.0)
        for ln in lines:
            sh.text(ln, COL_X, y, 2.0)
            y -= 3.0
    if y < 49.0:
        print(f"  WARNING {s.key}: notes run into the title block (y = {y:.1f})")
    bad = sh.check()
    os.makedirs(os.path.dirname(s.out), exist_ok=True)
    pdf = sh.save(s.out + ".dxf")
    D.png_from_pdf(pdf, path_png=s.out + ".png", dpi=150)
    checks += pr.rows
    return bad


# ------------------------------------------------------------------------------------------ helpers
def thread_lines(sh, o, x0, x1, r_minor):
    """thin lines at the minor diameter of an external thread (section and top views)"""
    for zz in (r_minor, -r_minor):
        sh.line(sh.P(*o, x0, zz), sh.P(*o, x1, zz), layer="HATCH")


def tags(sh, o, items):
    """balloons: (x, y, dx, side, id): side +1 puts the balloon 7 mm above the view, -1 below it (paper mm)"""
    for (x, y, dx, side, ident) in items:
        dy = side * (SC * sh.rmax + 7.0) - SC * y
        sh.tag(*o, x, y, dx, dy, ident)


def tag_radial(sh, o, x, y, ang, ident, extra=7.0):
    """balloon in an end view, outside the outline in the direction ang (degrees)"""
    a = math.radians(ang)
    r = SC * sh.rmax + extra
    sh.tag(*o, x, y, r * math.cos(a) - SC * x, r * math.sin(a) - SC * y, ident)


def up(sh, k):
    """dimension line k paper mm above the view (model units for hdim)"""
    return sh.rmax + k / SC


def dn(sh, k):
    return -sh.rmax - k / SC


def f(x, d=2):
    return num(x, d)


GEN_NOTES = [
    "Material: aluminium 6061-T6 bar. Turn and mill; bead-blast; anodise type II (MIL-A-8625), black or clear, "
    "after machining. Thread, bore and sealing faces masked or held to size after anodising.",
    "General tolerances ISO 2768-mK. Break sharp edges 0.1-0.2 unless shown. Surface Ra 1.6, sealing faces Ra 0.8.",
    "Geometry per the STEP file named in the title block. In the table, x is the distance from the body's front face "
    "(the thread end), Y and Z are measured from the axis, Z up (button side).",
]


# ------------------------------------------------------------------------------------------ Mini and Prism
def family_mp(sh, p, T, S, B, EF, ET, rmax, pr):
    """EDCO Mini and EDCO Prism: thread band, head section (side lights or fins, button, USB-C below),
    flatted tube, tail grooves and the keyring tab"""
    prism = hasattr(p, "x_hfins")

    def fx(x):
        return f(x - p.x_bf)
    R, RH, rb, rbd = p.R, p.RH, p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    thr = "M%s x %s-6g" % (num(p.band_d), num(p.pitch))
    L = p.L
    xt1 = p.x_bf + p.thread_len - (0.6 if prism else 0.5)
    # ---------------- section A-A
    sh.cur = "sec"
    thread_lines(sh, S, p.x_bf + 0.2, xt1, d3)
    up1, up2 = up(sh, 6.0), up(sh, 14.0)
    sh.hdim(*S, p.x_bf, rbd, p.x_hs0, RH, up1, "thread band and relief", "x_hs0-x_bf", p.x_hs0 - p.x_bf,
            shift=SC * (p.x_hs0 - p.x_bf) / 2 + 5.0)
    sh.hdim(*S, p.x_hs0, RH, p.x_step, RH, up1, "head section", "x_step-x_hs0", p.x_step - p.x_hs0,
            shift=SC * (p.x_btn - p.x_hs0) / 2)
    sh.hdim(*S, p.x_bf, rbd, p.x_btn, RH, up2, "button and USB-C centre", "x_btn-x_bf", p.x_btn - p.x_bf)
    dn1, dn2 = dn(sh, 7.0), dn(sh, 15.0)
    sh.hdim(*S, p.x_bf, -rb, p.x_bay1, -rb, dn1, "cell bay depth", "x_bay1-x_bf", p.x_bay1 - p.x_bf)
    sh.hdim(*S, p.x_bay1, -rb, L, -p.lug_t / 2 + p.end_chamfer, dn1, "bay end to the tab end", "L-x_bay1",
            L - p.x_bay1, shift=13.0)
    sh.hdim(*S, p.x_bf, -rbd, L, -p.lug_t / 2 + p.end_chamfer, dn2, "body length", "L-x_bf", L - p.x_bf)
    sh.vdim(*S, p.x_bf, -rbd, p.x_bf, rbd, p.x_bf - 5.0, "thread", "band_d", p.band_d, text=thr)
    xh = (p.x_btn + p.x_step) / 2 + 2.0
    sh.vdim(*S, xh, -RH, xh, RH, p.x_bf - 12.0, "head section diameter", "head_od", p.head_od, text="%%c<>")
    xm = (p.x_step + p.x_bay1) / 2
    sh.vdim(*S, xm, -rb, xm, rb, xm, "cell bay diameter", "bore_d", p.bore_d, text="%%c<>")
    xe = L - p.end_chamfer - 0.4
    sh.vdim(*S, xe, -p.lug_t / 2, xe, p.lug_t / 2, L + 5.0, "tab thickness", "lug_t", p.lug_t)
    # ---------------- top view (X, Y)
    sh.cur = "top"
    items = [(p.x_bf + 1.2, rbd - 0.3, -5.0, 1, 1),
             (p.x_btn + p.pocket_r * 0.6, p.pocket_r * 0.5, 6.0, 1, 4),
             ((p.x_step + p.x_flats_end) / 2 + 9, R * 0.7, 3.0, 1, 6),
             (p.x_grooves[1], R - 0.2, -2.0, 1, 7),
             (p.x_hole, p.hole_l / 2 - 0.5, 6.0, 1, 8)]
    if prism:
        items.append((p.x_hfins[1], RH - 0.3, 1.0, 1, 2))
    else:
        items.append((p.x_win, p.win_y[1], 3.0, 1, 10))
        items.append(((p.x_hs0 + p.x_step) / 2 + 2.5, RH - 0.3, -3.0, 1, 2))
    tags(sh, T, items)
    # ---------------- bottom view (X, -Y): the USB-C opening
    sh.cur = "bot"
    tags(sh, B, [(p.x_btn - p.usb_seal[0] / 2 + 0.3, 0.0, -12.0, 1, 5)])
    if prism:
        sh.hdim(*B, p.x_btn - p.plug_pocket[0] / 2, -p.plug_pocket[1] / 2, p.x_btn + p.plug_pocket[0] / 2,
                -p.plug_pocket[1] / 2, dn(sh, 8.0), "plug pocket length", "plug_pocket[0]", p.plug_pocket[0])
    sh.hdim(*B, p.x_btn - (p.usb_seal[0] + 0.1) / 2, (p.usb_seal[1] + 0.1) / 2, p.x_btn + (p.usb_seal[0] + 0.1) / 2,
            (p.usb_seal[1] + 0.1) / 2, up(sh, 7.0), "USB-C hole length", "usb_seal[0]+0.1", p.usb_seal[0] + 0.1)
    # ---------------- end views
    sh.cur = "front"
    sh.hdim(*EF, -rb, 0.0, rb, 0.0, dn(sh, 8.0), "cell bay diameter (front)", "bore_d", p.bore_d, text="%%c<>")
    tag_radial(sh, EF, -(rb + 0.2), 0.0, 150.0, 3)
    sh.cur = "tail"
    sh.hdim(*ET, -R, 0.0, R, 0.0, dn(sh, 8.0), "tube diameter", "body_od", p.body_od, text="%%c<>")
    sh.vdim(*ET, -2.0, -p.flat_r, -2.0, p.flat_r, -rmax - 4.0, "across the flats", "2*flat_r", 2 * p.flat_r)
    if p.magnet:
        tag_radial(sh, ET, p.mag_y, 0.0, 35.0, 9)
    # ---------------- probes
    front = min(a for a, b in pr.x(-(rb + 0.3), 0.0))
    pr.add("body length (front face to tab end)", L - p.x_bf, max(b for a, b in pr.x(0.0, 0.5)) - front)
    pr.add("head section diameter", p.head_od, pr.span(pr.y(p.x_step - 1.0, 0.0)))
    pr.add("band (thread major) diameter", p.band_d, pr.span(pr.y(p.x_bf + 0.6, 0.0)))
    ivy = pr.y(xm, 0.0)
    pr.add("cell bay diameter", p.bore_d, ivy[1][0] - ivy[0][1])
    pr.add("cell bay depth", p.x_bay1 - p.x_bf, min(a for a, b in pr.x(0.0, 0.0)) - front)
    pr.add("tab thickness", p.lug_t, pr.span(pr.z(L - p.end_chamfer - 0.4, 0.0)))
    xq = (p.x_step + p.x_flats_end) / 2 + 3.0
    pr.add("across the flats", 2 * p.flat_r, pr.span(pr.z(xq, 0.0)))
    pr.add("tube diameter", p.body_od, pr.span(pr.y(xq, 0.0)))
    # ---------------- table and notes
    fl0, fl1 = p.x_step + 1.2, p.x_flats_end
    rows = [
        (1, "Thread band", f"{thr} external, {num(p.thread_len)} long from the front face, run-out to "
                           f"{f(2 * (d3 - 0.05))}; front face is the seat of the insert's face O-ring",
         "6g; front face Ra 0.8, flat 0.02"),
        (2, "Head section", f"{f(p.head_od)} from x {fx(p.x_hs0)} to {fx(p.x_step)}, 0.8 step to the tube"
         + (f"; {p.head_fins} fins {f(p.hfin_w)} wide, {f(p.hfin_d)} deep, pitch {f(p.hfin_pitch)}" if prism else ""),
         "+/-0.05"),
        (3, "Cell bay", f"{f(p.bore_d)} to x {fx(p.x_bay1)} (flat floor), entry chamfer 0.2 x 45 deg; key notch for "
                        f"the insert at +Y, {f(1.0)} wide x {f(p.spigot_len + 0.1)} deep", "+0.05/0; key +/-0.03"),
        (4, "Button", f"round scallop {f(2 * p.pocket_r)} to Z {f(p.z_pocket)} (R0.4 floor edge) at x {fx(p.x_btn)}; "
                      f"counterbore {f(p.btn_cb_d)} to Z {f(p.z_cb_floor)}; pin hole 2.6 into the bay",
         "counterbore H8, floor +/-0.03"),
        (5, "USB-C opening", f"obround {f(p.usb_seal[0] + 0.1)} x {f(p.usb_seal[1] + 0.1)} through at -Z (the socket's "
                             f"seal ring seals in it)" + (f"; plug pocket {f(p.plug_pocket[0])} x {f(p.plug_pocket[1])}"
                                                          f" to Z {f(p.z_mouth)}, R0.5 floor edge" if prism else ""),
         "obround +0.05/0, Ra 0.8"),
        (6, "Flats", f"six, {f(p.flat_r)} from the axis ({f(2 * p.flat_r)} across), x {fx(fl0)} to {fx(fl1)}; "
                     f"\"{p.label_text}\" laser-marked on the top flat, {f(p.label_size)} high", "+/-0.05"),
        (7, "Tail grooves", f"{p.tail_grooves} x {f(p.groove_w)} wide, {f(p.groove_d)} deep, at x "
                            + ", ".join(fx(x) for x in sorted(p.x_grooves)), "+/-0.1"),
        (8, "Keyring tab", f"two flats {f(p.lug_t)} apart (Z), bevels {f(p.ramp_deg, 0)} deg from the bay end; "
                           f"slot {f(p.hole_w)} x {f(p.hole_l)} through (Z) at x {fx(p.x_hole)}; end corners R{f(p.tab_rc)},"
                           f" end edges {f(p.end_chamfer)} x 45 deg", "slot +0.1/0"),
    ]
    if not prism:
        rows.append((10, "Side-light windows", f"UV rod hole {f(p.uv_rod_d + 0.1)} at Y {f(p.win_y[0])} and red rod hole "
                                               f"{f(p.red_rod_d + 0.1)} at Y {f(p.win_y[1])}, x {fx(p.x_win)}, through "
                                               f"to the bore (+Z)", "+0.05/0 (glued rods)"))
    if p.magnet:
        rows.append((9, "Magnet pockets (M version only)", f"two {f(p.mag_d + 0.1)} x {f(p.mag_t + 0.1)} deep in the "
                                                          f"tab's end face at Y +/-{f(p.mag_y)}, Z 0",
                     "+0.05/0; magnets bonded, opposite poles out"))
    rows.sort(key=lambda r: r[0])
    notes = GEN_NOTES + [
        f"The plain version ({p.name[:-1] if p.magnet else p.name}) is the same body without item 9.",
        "Items 3, 4 and 5 carry seals: no burrs, no tool marks across the sealing faces.",
    ]
    return rows, notes


# ------------------------------------------------------------------------------------------ v0.2
def family_v02(sh, p, T, S, B, EF, ET, rmax, pr):
    """EDCO v0.2: thread band, collar seat with the port window and its gasket groove, flatted body, button pocket,
    tail grooves, two lanyard holes"""
    R, rb, rbd = p.R, p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    thr = "M%s x %s-6g" % (num(p.band_d), num(p.pitch))
    L = p.L
    xt1 = p.x_bf + p.thread_len - 0.6
    xg = [L - 3.0 - i * 2.0 for i in range(p.tail_grooves)]

    def fx(x):
        return f(x - p.x_bf)
    fl0, fl1 = p.x_sh + 0.6, L - 3.0 - p.tail_grooves * 2.0 - 1.0
    sh.cur = "sec"
    thread_lines(sh, S, p.x_bf + 0.3, xt1, d3)
    up1, up2 = up(sh, 6.0), up(sh, 14.0)
    sh.hdim(*S, p.x_bf, rbd, p.x_r1, rbd, up1, "thread band and relief", "x_r1-x_bf", p.x_r1 - p.x_bf)
    sh.hdim(*S, p.x_r1, rbd, p.x_sh, R, up1, "collar seat", "x_sh-x_r1", p.x_sh - p.x_r1)
    sh.hdim(*S, p.x_bf, rbd, p.x_btn, R, up2, "button centre", "x_btn-x_bf", p.x_btn - p.x_bf)
    dn1, dn2 = dn(sh, 7.0), dn(sh, 15.0)
    sh.hdim(*S, p.x_bf, -rb, p.x_win, -rbd, dn1, "port window centre", "x_win-x_bf", p.x_win - p.x_bf)
    sh.hdim(*S, p.x_win, -rbd, p.x_bay1, -rb, dn1, "port window to the bay end", "x_bay1-x_win", p.x_bay1 - p.x_win)
    sh.hdim(*S, p.x_bf, -rbd, L, -R + 0.6, dn2, "body length", "L-x_bf", L - p.x_bf)
    sh.vdim(*S, p.x_bf, -rbd, p.x_bf, rbd, p.x_bf - 5.0, "thread", "band_d", p.band_d, text=thr)
    xm = (p.x_sh + p.x_bay1) / 2
    sh.vdim(*S, xm, -rb, xm, rb, xm, "cell bay diameter", "bore_d", p.bore_d, text="%%c<>")
    xe = L - 1.5
    sh.vdim(*S, xe, -R, xe, R, L + 5.0, "body diameter", "body_od", p.body_od, text="%%c<>")
    sh.cur = "top"
    tags(sh, T, [(p.x_bf + 1.5, rbd - 0.3, -5.0, 1, 1),
                 ((p.x_r1 + p.x_sh) / 2, rbd - 0.2, 1.0, 1, 2),
                 (p.x_btn + 2.0, 2.5, 6.0, 1, 4),
                 ((fl0 + fl1) / 2 + 9.0, R * 0.7, 3.0, 1, 6),
                 (xg[1], R - 0.2, -2.0, 1, 7)])
    sh.cur = "bot"
    tags(sh, B, [(p.x_win + p.win_ax / 2 - 0.3, 0.0, 8.0, -1, 5),
                 (L - 1.6, -(p.R - 3.2) * 0.0 - 0.0, 6.0, -1, 8)])
    sh.hdim(*B, p.x_win - p.win_ax / 2, -p.win_tan / 2, p.x_win + p.win_ax / 2, -p.win_tan / 2, up(sh, 7.0),
            "port window along the axis", "win_ax", p.win_ax)
    sh.cur = "front"
    sh.hdim(*EF, -rb, 0.0, rb, 0.0, dn(sh, 8.0), "cell bay diameter (front)", "bore_d", p.bore_d, text="%%c<>")
    tag_radial(sh, EF, -(rb + 0.3), 0.0, 150.0, 3)
    sh.cur = "tail"
    sh.vdim(*ET, -2.0, -p.flat_r, -2.0, p.flat_r, -rmax - 4.0, "across the flats", "2*flat_r", 2 * p.flat_r)
    sh.hdim(*ET, -R, 0.0, R, 0.0, dn(sh, 8.0), "body diameter (tail)", "body_od", p.body_od, text="%%c<>")
    # probes
    ivx = pr.x(-(rb + 0.5), 0.0)
    pr.add("body length", L - p.x_bf, ivx[-1][1] - ivx[0][0])
    pr.add("band (thread major) diameter", p.band_d, pr.span(pr.y(p.x_bf + 0.8, 0.0)))
    pr.add("collar seat diameter", p.band_d, pr.span(pr.y((p.x_r1 + p.x_sh) / 2, 0.0)))
    ivy = pr.y(xm, 0.0)
    pr.add("cell bay diameter", p.bore_d, ivy[1][0] - ivy[0][1])
    pr.add("cell bay depth", p.x_bay1 - p.x_bf, min(a for a, b in pr.x(0.0, 0.0)) - p.x_bf)
    pr.add("across the flats", 2 * p.flat_r, pr.span(pr.z(xm, 0.0)))
    pr.add("body diameter", p.body_od, pr.span(pr.y(xm, 0.0)))
    rows = [
        (1, "Thread band", f"{thr} external, {num(p.thread_len)} long from the front face, relief to "
                           f"{f(2 * (d3 - 0.05))}; front face is the seat of the insert's face O-ring",
         "6g; front face Ra 0.8, flat 0.02"),
        (2, "Collar seat", f"{f(p.band_d)} from x {fx(p.x_r1)} to the shoulder at {fx(p.x_sh)} (0.4 chamfer); the "
                           f"collar turns on it", "f7, Ra 0.8"),
        (3, "Cell bay", f"{f(p.bore_d)} to x {fx(p.x_bay1)} (flat floor), entry chamfer 0.3 x 45 deg; key notch for "
                        f"the insert at +Y, 1.3 wide x {f(p.spigot_len + 0.1)} deep", "+0.05/0; key +/-0.03"),
        (4, "Button", f"round scallop {f(p.btn_cb_d + 1.8)} to Z {f(p.pocket_floor_r)} (R0.5 floor edge) at x "
                      f"{fx(p.x_btn)}; counterbore {f(p.btn_cb_d)} to Z {f(p.z_cb_floor)}; pin hole 2.6 into the bay",
         "counterbore H8, floor +/-0.03"),
        (5, "Port window", f"stadium {f(p.win_ax)} along the axis by {f(p.win_tan)} across, at -Z, x {fx(p.x_win)}, up to the "
                           f"socket mouth (Z {f(p.z_mouth + 0.2)}); gasket groove 0.75 wide, 0.6 deep round it, "
                           f"0.2 from the window edge", "window +/-0.05; groove +0.05/0"),
        (6, "Flats", f"six, {f(p.flat_r)} from the axis ({f(2 * p.flat_r)} across), x {fx(fl0)} to {fx(fl1)}; "
                     f"\"{p.label_text}\" laser-marked on a flat, {f(p.label_size)} high", "+/-0.05"),
        (7, "Tail grooves", f"{p.tail_grooves} x {f(p.groove_w)} wide, {f(p.groove_d)} deep, at x "
                            + ", ".join(fx(x) for x in sorted(xg)), "+/-0.1"),
        (8, "Lanyard holes", f"two {f(p.lan_d)} straight holes at 45 deg through the tail corners (+Z and -Z), "
                             f"entering the tail face {f(p.R - 3.2)} from the axis", "+0.1/0, deburr"),
    ]
    notes = GEN_NOTES + ["Items 1, 3, 4 and 5 carry seals: no burrs, no tool marks across the sealing faces."]
    return rows, notes


# ------------------------------------------------------------------------------------------ v0.1
def family_v01(sh, p, T, S, B, EF, ET, rmax, pr):
    """EDCO v0.1: thread and undercut, plain tube, button pocket, indicator hole, label flat, tail cavity, USB-C
    hole in the end wall, two lanyard holes"""
    R, L = p.R, p.L
    x0 = p.body_front_x

    def fx(x):
        return f(x - x0)
    rb = p.bore_d / 2
    ux0, ux1, ud = p.undercut
    thr = "M%s x %s-6g" % (num(p.thread_major), num(p.thread_pitch))
    sh.cur = "sec"
    thread_lines(sh, S, x0 + 0.3, ux0, p.thread_minor_ext / 2)
    up1, up2 = up(sh, 6.0), up(sh, 14.0)
    sh.hdim(*S, x0, p.thread_major / 2, ux1, R, up1, "thread and undercut", "undercut[1]-body_front_x", ux1 - x0)
    sh.hdim(*S, x0, p.thread_major / 2, p.btn_x, R, up2, "button centre", "btn_x-body_front_x", p.btn_x - x0)
    sh.hdim(*S, p.btn_x, R, p.ind_x, R, up2, "button to indicator", "ind_x-btn_x", p.ind_x - p.btn_x)
    dn1, dn2 = dn(sh, 7.0), dn(sh, 15.0)
    sh.hdim(*S, x0, -rb, p.tail_cav_x0, -rb, dn1, "bore depth", "tail_cav_x0-body_front_x", p.tail_cav_x0 - x0)
    sh.hdim(*S, p.end_wall_x0, -p.tail_cav_d / 2, L, -R + 0.5, dn1, "end wall", "tail_wall", p.tail_wall, shift=7.0)
    sh.hdim(*S, x0, -p.thread_major / 2, L, -R + 0.5, dn2, "body length", "L-body_front_x", L - x0)
    sh.vdim(*S, x0, -p.thread_major / 2, x0, p.thread_major / 2, x0 - 5.0, "thread", "thread_major",
            p.thread_major, text=thr)
    xm = (p.flat_x[1] + p.tail_cav_x0) / 2
    sh.vdim(*S, xm, -rb, xm, rb, xm, "bore diameter", "bore_d", p.bore_d, text="%%c<>")
    xe = L - 1.5
    sh.vdim(*S, xe, -R, xe, R, L + 5.0, "tube diameter", "OD", p.OD, text="%%c<>")
    sh.cur = "top"
    dtop = dn(sh, 7.0)
    sh.hdim(*T, p.pocket_x[0], -p.pocket_w / 2, p.pocket_x[1], -p.pocket_w / 2, dtop, "button pocket length",
            "pocket_x[1]-pocket_x[0]", p.pocket_x[1] - p.pocket_x[0])
    sh.hdim(*T, p.flat_x[0], -p.flat_w / 2, p.flat_x[1], -p.flat_w / 2, dtop, "label flat length",
            "flat_x[1]-flat_x[0]", p.flat_x[1] - p.flat_x[0])
    tags(sh, T, [(x0 + 1.5, p.thread_major / 2 - 0.3, -5.0, 1, 1),
                 (p.btn_x + 1.5, 1.5, 4.0, 1, 4),
                 (p.ind_x, 0.0, 6.0, 1, 5),
                 ((p.flat_x[0] + p.flat_x[1]) / 2 + 6.0, 2.0, 3.0, 1, 6)])
    sh.cur = "bot"
    tags(sh, B, [(L - 1.6, 0.0, 6.0, -1, 8), ((x0 + L) / 2, -(R - 0.2), 0.0, -1, 2)])
    sh.cur = "front"
    sh.hdim(*EF, -rb, 0.0, rb, 0.0, dn(sh, 8.0), "bore diameter (front)", "bore_d", p.bore_d, text="%%c<>")
    tag_radial(sh, EF, -(rb + 0.3), 0.0, 150.0, 3)
    sh.cur = "tail"
    sh.hdim(*ET, -p.usb_hole[0] / 2, -p.usb_hole[1] / 2, p.usb_hole[0] / 2, -p.usb_hole[1] / 2, dn(sh, 8.0),
            "USB-C hole width", "usb_hole[0]", p.usb_hole[0])
    sh.vdim(*ET, p.usb_hole[0] / 2 - 2.2, -p.usb_hole[1] / 2, p.usb_hole[0] / 2 - 2.2, p.usb_hole[1] / 2, R + 5.0,
            "USB-C hole height", "usb_hole[1]", p.usb_hole[1])
    tag_radial(sh, ET, -1.0, -p.usb_hole[1] / 2, 235.0, 7)
    # probes
    ivx = pr.x(-(rb + 0.6), 0.0)
    pr.add("body length", L - x0, ivx[-1][1] - ivx[0][0])
    pr.add("tube diameter", p.OD, pr.span(pr.y(xm, 0.0)))
    ivy = pr.y(xm, 0.0)
    pr.add("bore diameter", p.bore_d, ivy[1][0] - ivy[0][1])
    pr.add("thread major diameter", p.thread_major, pr.span(pr.y(x0 + 1.0, 0.0)))
    ivx = pr.x(5.8, 0.0)
    pr.add("end wall thickness", p.tail_wall, ivx[-1][1] - ivx[-1][0])
    rows = [
        (1, "Thread and undercut", f"{thr} external from the front face to x {fx(ux0)}; undercut "
                                   f"{f(ud)} to x {fx(ux1)}; 0.3 x 45 deg shoulder; front face seats the head flange",
         "6g; front face Ra 0.8"),
        (2, "Tube", f"{f(p.OD)} from the shoulder to the tail, tail edge 0.5 x 45 deg", "+/-0.05"),
        (3, "Bore", f"{f(p.bore_d)} to x {fx(p.tail_cav_x0)}, entry chamfer 0.4 x 45 deg (the head O-ring seals "
                    f"in it); tail cavity {f(p.tail_cav_d)} to x {fx(p.end_wall_x0)}", "H8, Ra 0.8 for the first 11"),
        (4, "Button", f"pocket: stadium x {fx(p.pocket_x[0])} to {fx(p.pocket_x[1])}, {f(p.pocket_w)} wide, floor Z "
                      f"{f(p.pocket_floor_z)}, R0.6 floor edges; counterbore {f(p.btn_cb_d)} to Z {f(p.btn_cb_floor_z)}"
                      f" at x {fx(p.btn_x)}; pin hole {f(p.btn_hole_d)} through", "counterbore H8, floor +/-0.03"),
        (5, "Indicator hole", f"{f(p.ind_d)} through at x {fx(p.ind_x)} (the light pipe is glued in)",
         "+0.05/0"),
        (6, "Label flat", f"stadium x {fx(p.flat_x[0])} to {fx(p.flat_x[1])}, {f(p.flat_w)} wide, at Z {f(p.flat_z)}; "
                          f"\"{p.label_text}\" laser-marked, {f(p.label_size)} high", "+/-0.05"),
        (7, "USB-C hole", f"obround {f(p.usb_hole[0])} x {f(p.usb_hole[1])} through the {f(p.tail_wall)} end wall "
                          f"(the socket's seal ring seals in it)", "+0.05/0, Ra 0.8"),
        (8, "Lanyard holes", f"two {f(p.lan_d)} straight holes at 45 deg through the tail corners (+Z, -Z), "
                             f"entering the tail face {f(p.lan_entry_r)} from the axis", "+0.1/0, deburr"),
    ]
    notes = GEN_NOTES + ["Items 1, 3, 4, 5 and 7 carry seals: no burrs, no tool marks across the sealing faces."]
    return rows, notes


# ------------------------------------------------------------------------------------------ main
def specs():
    V1 = load("edco-v01/tools/housing/edco_housing.py", "edco_housing")
    V2 = load("edco-v02/tools/housing/edco_v02.py", "edco_v02")
    MI = load("edco-mini/tools/housing/edco_mini.py", "edco_mini")
    PR = load("edco-prism/tools/housing/edco_prism.py", "edco_prism")
    out = []
    p = V1.P()
    out.append(Spec("v01", V1, p, V1.build_body(p, cosmetic=False), "EDCO v0.1", "EDCO_body.step",
                    os.path.join(HW, "edco-v01/cad/EDCO_body_drawing"), family_v01))
    for sz in ("18", "14"):
        p = V2.P(size=sz)
        out.append(Spec("v02-" + sz, V2, p, V2.build_body(p, cosmetic=False), f"EDCO v0.2  EDCO-{sz}",
                        f"EDCO-{sz}_body.step", os.path.join(HW, f"edco-v02/cad/EDCO-{sz}_body_drawing"), family_v02))
    for sz in ("16", "14"):
        p = MI.P(size=sz, magnet=True)
        out.append(Spec("mini-" + sz, MI, p, MI.build_body(p, cosmetic=False), f"EDCO Mini v0.1  Mini-{sz}",
                        f"EDCO_Mini-{sz}M_body.step\n(plain: EDCO_Mini-{sz}_body.step)",
                        os.path.join(HW, f"edco-mini/cad/EDCO_Mini-{sz}_body_drawing"), family_mp))
    p = PR.P(magnet=True)
    out.append(Spec("prism", PR, p, PR.build_body(p, cosmetic=False), "EDCO Prism v0.1",
                    "EDCO_PrismM_body.step\n(plain: EDCO_Prism_body.step)",
                    os.path.join(HW, "edco-prism/cad/EDCO_Prism_body_drawing"), family_mp))
    return out


def main(names):
    checks = []
    bad = 0
    for s in specs():
        if names and s.key not in names:
            continue
        print(f"{s.key}: drawing")
        bad += body_sheet(s, checks)
    lines = ["EDCO body drawings: dimensions on the sheets against the parameters, and main sizes measured on the "
             "solids", ""]
    nreg = [r for r in D.ROWS if not r["ok"]]
    lines.append(f"{len(D.ROWS)} dimensions registered against their parameters, {len(nreg)} differ")
    for r in nreg:
        lines.append(f"  DIFFERS {r['sheet']} {r['view']} {r['what']}: shown {r['shown']} P {r['pval']}")
    lines.append("")
    lines.append("design     | probe | drawn | measured | ok")
    for (k, what, drawn, meas, ok) in checks:
        lines.append(f"{k:10s} | {what} | {num(drawn, 3)} | {num(meas, 3)} | {'ok' if ok else 'DIFFERS'}")
    nbad = sum(1 for c in checks if not c[4])
    lines.append("")
    lines.append(f"{len(checks)} probes, {nbad} differ; layout findings: {bad}")
    txt = "\n".join(lines) + "\n"
    print(txt)
    if not names:
        open(os.path.join(HERE, "edco_drawings_check.txt"), "w").write(txt)
    return 0 if nbad == 0 and not nreg else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
