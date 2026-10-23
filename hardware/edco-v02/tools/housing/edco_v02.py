#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""EDCO v0.2 housing and cartridge, CadQuery (LuxLibre reference design #2), in two sizes:

    EDCO-18   one 18500 cell, Ø24 body, Ø26 head      (the 2000 lm version)
    EDCO-14   one 14500 cell, Ø20 body, Ø22 head      (the slim version)

What changed from v0.1: a Luminus SST-40 (5 x 5 mm) instead of the SST-20, a bigger TIR optic in a head that is
2 mm larger than the body; the USB-C socket moved from the tail to the side of the head, under a rotating
fluted collar (twist to open: the collar's window lines up with the port); a crenellated bezel, grooves at the
bezel and the tail, six milled flats along the body; a bigger button whose membrane glows (halo indicator).

Front to tail:
    bezel ring  - crenellated, screws onto the band's external thread (M18 x 0.75 / M22 x 0.75), clamps the
                  LED holder (insert) metal on metal and presses the optic onto its gasket
    insert      - LED holder: a cup for the optic, the LED board on a 2 mm shelf, a face O-ring on its rear face
                  against the band's front face, a key that stops it turning while the ring is tightened
    collar      - turns freely on the band between the ring and the body shoulder: window down over the port =
                  open, turned away = closed. A moulded silicone gasket in a groove round the port window on the
                  band is wiped and pressed by the collar's bore, so the port is sealed whenever the window is
                  turned away; the space between collar and band may get wet
    body        - the band (thread + collar seat + port window) and the tube with six flats, the button pocket,
                  the label and the tail grooves, closed tail with two lanyard holes
    cartridge   - insert, main board in a POM sled (vertical USB-C socket on its underside looking down through
                  the port window, the switch on its top side), the cell

Frame: X along the light, X = 0 at the front of the bezel's crenellations, X = L at the tail face; button on
+Z; port on -Z (opposite the button). Units mm.

usage:  python3 edco_v02.py <out_dir> [--size 18|14|both] [--stl]
"""
import json
import math
import os
import sys
from dataclasses import dataclass, asdict, field

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-SemiBold.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"

SIZES = {
    # body, head, bore (cell bay), band = thread major, cell, optic, LED board, flats, button, socket
    "18": dict(name="EDCO-18", body_od=24.0, head_od=26.0, bore_d=19.4, band_d=22.0, cell_d=18.4, cell_len=50.5,
               cell_name="18500", opt_d=20.0, opt_h=11.5, mcpcb_d=20.0, flat_r=11.2, cap_d=7.5, btn_cb_d=9.4,
               pocket_floor_r=10.95, ring_wall=2.0),
    "14": dict(name="EDCO-14", body_od=20.0, head_od=22.0, bore_d=15.2, band_d=18.0, cell_d=14.0, cell_len=49.5,
               cell_name="14500", opt_d=17.0, opt_h=10.5, mcpcb_d=16.0, flat_r=9.3, cap_d=6.5, btn_cb_d=8.4,
               pocket_floor_r=9.05, ring_wall=1.6),
}


@dataclass
class P:
    size: str = "18"
    name: str = ""
    body_od: float = 0.0
    head_od: float = 0.0
    bore_d: float = 0.0
    band_d: float = 0.0
    cell_d: float = 0.0
    cell_len: float = 0.0
    cell_name: str = ""
    opt_d: float = 0.0           # TIR optic for the SST-40 (stand-in until the part is chosen)
    opt_h: float = 0.0
    mcpcb_d: float = 0.0
    flat_r: float = 0.0          # six flats along the body, at this distance from the axis
    cap_d: float = 0.0           # stainless button cap
    btn_cb_d: float = 0.0        # counterbore for the membrane + collar
    pocket_floor_r: float = 0.0
    # common
    pitch: float = 0.75          # M18 x 0.75 / M22 x 0.75
    ring_wall: float = 1.6       # bezel wall over the insert (set per size; fins are cut into it)
    fin_n: int = 5               # cooling fins round the bezel
    fin_d: float = 0.8
    fin_w: float = 0.9
    fin_pitch: float = 1.9
    cren_n: int = 6              # crenellations
    cren_w: float = 3.4
    cren_d: float = 1.5
    lip_t: float = 0.8           # bezel lip over the optic
    gasket_t: float = 0.5        # optic gasket (silicone)
    opt_in_ring: float = 1.5     # front part of the optic inside the bezel's small bore
    mcpcb_t: float = 1.6
    shelf_t: float = 2.0         # solid insert floor behind the LED board
    thread_len: float = 4.2
    spigot_len: float = 1.5      # insert spigot in the bore (centring + key)
    face_or_cs: float = 0.8      # face O-ring between insert and band
    collar_len: float = 10.8
    collar_wall: float = 1.95
    win_ax: float = 7.2          # port window, along the axis (plug overmould 6.5 + play)
    win_tan: float = 13.2        # port window, across (overmould 12.35 + play)
    gasket_w: float = 1.3        # port gasket band round the window (groove 0.9 wide, 0.6 deep)
    sw_h: float = 2.0            # Alps SKRK incl. actuator
    sw_body: tuple = (2.9, 3.9, 1.5)
    board_t: float = 0.8
    usb_h: float = 6.5           # vertical USB-C socket height above the board (stand-in)
    usb_shell: tuple = (8.94, 3.26)
    usb_body: tuple = (9.6, 4.4)  # across (Y), along (X)
    usb_half_w: float = 4.6       # half width incl. shell for the bore clearance
    strip_t: float = 0.15
    insul_t: float = 0.15
    tail_wall: float = 2.2
    lan_d: float = 1.6
    tail_grooves: int = 3
    groove_w: float = 0.8
    groove_d: float = 0.6
    label_text: str = "EDCO"
    label_size: float = 2.4

    def __post_init__(self):
        for k, v in SIZES[self.size].items():
            setattr(self, k, v)

    # ---- derived positions (X)
    @property
    def R(self): return self.body_od / 2
    @property
    def RH(self): return self.head_od / 2
    @property
    def rb(self): return self.bore_d / 2
    @property
    def rband(self): return self.band_d / 2
    @property
    def ring_bore(self): return self.head_od - 2 * self.ring_wall
    @property
    def lip_id(self): return self.opt_d - 1.6
    @property
    def x_lip1(self): return self.cren_d + self.lip_t
    @property
    def x_opt0(self): return self.x_lip1 + self.gasket_t
    @property
    def x_opt1(self): return self.x_opt0 + self.opt_h
    @property
    def x_cup0(self): return self.x_opt0 + self.opt_in_ring
    @property
    def x_mc1(self): return self.x_opt1 + self.mcpcb_t
    @property
    def x_bf(self): return self.x_mc1 + self.shelf_t           # band front face = insert flange rear face
    @property
    def x_r1(self): return self.x_bf + self.thread_len          # bezel rear face
    @property
    def x_c0(self): return self.x_r1 + 0.1
    @property
    def x_c1(self): return self.x_c0 + self.collar_len
    @property
    def x_sh(self): return self.x_c1 + 0.1                      # body shoulder
    @property
    def x_win(self): return (self.x_c0 + self.x_c1) / 2
    @property
    def x_btn(self): return self.x_sh + 1.2 + self.btn_cb_d / 2
    @property
    def board_x(self): return (self.x_bf + self.spigot_len + 0.3, self.x_btn + self.btn_cb_d / 2 + 0.6)
    @property
    def x_cell0(self): return self.board_x[1] + 0.9
    @property
    def x_cell1(self): return self.x_cell0 + self.cell_len
    @property
    def x_bay1(self): return self.x_cell1 + self.strip_t + self.insul_t + 0.1
    @property
    def L(self): return self.x_bay1 + self.tail_wall
    # ---- derived heights (Z)
    @property
    def z_mouth(self):   # socket mouth: its corners just clear the bore
        return -math.sqrt(self.rb ** 2 - self.usb_half_w ** 2) + 0.1
    @property
    def z_board_bot(self): return self.z_mouth + self.usb_h
    @property
    def z_board_top(self): return self.z_board_bot + self.board_t
    @property
    def z_sw_top(self): return self.z_board_top + 0.05 + self.sw_h
    @property
    def z_cb_floor(self): return self.pocket_floor_r - 0.6
    @property
    def board_w(self):
        z = max(abs(self.z_board_bot), abs(self.z_board_top))
        return 2 * (math.sqrt(self.rb ** 2 - z ** 2) - 0.35)


# --------------------------------------------------------------------------------------------- helpers
def revolve_x(pts):
    q = []
    for pt in pts:   # drop repeated points (zero-length edges)
        if not q or abs(pt[0] - q[-1][0]) > 1e-6 or abs(pt[1] - q[-1][1]) > 1e-6:
            q.append(pt)
    if abs(q[0][0] - q[-1][0]) < 1e-6 and abs(q[0][1] - q[-1][1]) < 1e-6:
        q.pop()
    return cq.Workplane("XY").polyline(q).close().revolve(360, (0, 0, 0), (1, 0, 0))


def cyl(d, p0, direction, length):
    v = cq.Vector(*direction).normalized()
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, length, cq.Vector(*p0), v))


def cyl_x(d, x0, x1, y=0.0, z=0.0):
    return cyl(d, (x0, y, z), (1, 0, 0), x1 - x0)


def cyl_z(d, z0, z1, x=0.0, y=0.0):
    return cyl(d, (x, y, z0), (0, 0, 1), z1 - z0)


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def stadium_xy(xc, ax, tan, z0, z1):
    """stadium in the XY plane (long axis Y = tan, short X = ax) extruded along Z"""
    return (cq.Workplane("XY").workplane(offset=z0).center(xc, 0).slot2D(tan, ax, 90).extrude(z1 - z0))


def stadium_z(x0, x1, w, z0, z1, fillet=0.0):
    s = (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, 0).slot2D(x1 - x0, w, 0).extrude(z1 - z0))
    if fillet:
        s = s.edges("<Z").fillet(fillet)
    return s


def torus_x(x, r_major, r_minor):
    return cq.Workplane("XY").add(cq.Solid.makeTorus(r_major, r_minor, cq.Vector(x, 0, 0), cq.Vector(1, 0, 0)))


def thread_zigzag(x0, x1, r_crest, r_root, pitch):
    pts = []
    n = int((x1 - x0) / pitch + 1e-6)
    for i in range(n + 1):
        x = x0 + i * pitch
        pts.append((x, r_crest))
        if i < n:
            pts.append((x + pitch / 2, r_root))
    return pts


def rot_x(w, deg):
    return w.rotate((0, 0, 0), (1, 0, 0), deg)


def solid(w):
    return w.val() if isinstance(w, cq.Workplane) else w


# --------------------------------------------------------------------------------------------- parts
def build_body(p, cosmetic=True):
    R, L, rb, rbd = p.R, p.L, p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch                       # external minor radius (d3 / 2)
    x0 = p.x_bf
    xt1 = p.x_bf + p.thread_len - 0.6                 # thread run-out
    pts = [(x0, 0.0), (x0, rbd - 0.3), (x0 + 0.3, rbd)]
    if cosmetic:
        pts += thread_zigzag(x0 + 0.5, xt1, rbd, d3, p.pitch)[1:]
    else:
        pts += [(xt1, rbd)]
    pts += [(xt1, d3 - 0.05), (p.x_r1, d3 - 0.05), (p.x_r1, rbd), (p.x_sh, rbd), (p.x_sh, R - 0.4),
            (p.x_sh + 0.4, R), (L - 0.6, R), (L, R - 0.6), (L, 0.0)]
    body = revolve_x(pts)
    # cell bay (+ entry chamfer)
    body = body.cut(revolve_x([(x0 - 0.1, 0.0), (x0 - 0.1, rb + 0.3), (x0 + 0.3, rb), (p.x_bay1, rb),
                               (p.x_bay1, 0.0)]))
    # anti-rotation notch for the insert key (+Y), from the front face
    body = body.cut(box(x0 - 0.1, x0 + p.spigot_len + 0.1, rb - 0.2, rb + 0.8, -0.65, 0.65))
    # port window at -Z: a stadium (long side across) cut from below up to the socket mouth
    body = body.cut(stadium_xy(p.x_win, p.win_ax, p.win_tan, -R - 2, p.z_mouth + 0.2))
    # gasket groove round the port window (follows the band surface: 0.6 deep, 0.9 wide)
    body = body.cut(port_gasket_ring(p, depth=0.6, proud=1.0, inset=0.2, width=0.9))
    # six flats from the shoulder to the tail grooves
    xf0, xf1 = p.x_sh + 0.6, p.L - 3.0 - p.tail_grooves * 2.0 - 1.0
    for k in range(6):
        a = 90 + 60 * k
        cutter = box(xf0, xf1, -20, 20, p.flat_r, p.flat_r + 6)
        cutter = cutter.edges("|Y").fillet(0.0) if False else cutter
        body = body.cut(rot_x(cutter, a - 90))
    # button pocket (round scallop in the top flat), counterbore, pin hole
    pr = p.btn_cb_d / 2 + 0.9
    pocket = cyl_z(2 * pr, p.pocket_floor_r, p.R + 2, x=p.x_btn).edges("<Z").fillet(0.5)
    body = body.cut(pocket)
    body = body.cut(cyl_z(p.btn_cb_d, p.z_cb_floor, p.R + 2, x=p.x_btn))
    body = body.cut(cyl_z(2.6, 0.0, p.z_cb_floor + 0.01, x=p.x_btn))
    # tail grooves
    for i in range(p.tail_grooves):
        xg = p.L - 3.0 - i * 2.0
        body = body.cut(revolve_x([(xg - p.groove_w / 2, R - p.groove_d), (xg + p.groove_w / 2, R - p.groove_d),
                                   (xg + p.groove_w / 2, R + 1), (xg - p.groove_w / 2, R + 1)]))
    # lanyard holes through the tail corners (+Z and -Z, at 45 deg)
    for s in (1, -1):
        body = body.cut(lanyard_hole(p, s))
    return body


def lanyard_hole(p, s, extra=1.5):
    L = p.L
    entry_r = p.R - 3.2
    dx = 3.0
    d = (-1.0, 0.0, s * 1.0)
    n = 1 / math.sqrt(2)
    start = (L - d[0] * n * extra, 0.0, s * entry_r - d[2] * n * extra)
    return cyl(p.lan_d, start, d, (dx + 2 * extra) * math.sqrt(2))


def build_ring(p, cosmetic=True):
    RH = p.RH
    rbd = p.rband
    D1 = rbd - 0.5413 * p.pitch                        # internal minor radius (D1 / 2)
    rbore = p.ring_bore / 2
    rsmall = p.opt_d / 2 + 0.1
    rl = p.lip_id / 2
    pts = [(0.0, rl + 0.4), (0.0, RH - 0.5), (0.5, RH), (p.x_r1 - 0.4, RH), (p.x_r1, RH - 0.4), (p.x_r1, D1)]
    if cosmetic:
        th = thread_zigzag(p.x_bf + 0.2, p.x_r1 - 0.3, D1, rbd, p.pitch)
        pts += list(reversed(th))
    pts += [(p.x_bf, rbd + 0.1), (p.x_bf, rbore), (p.x_cup0, rbore), (p.x_cup0, rsmall), (p.x_lip1, rsmall),
            (p.x_lip1, rl), (p.cren_d + 0.2, rl)]
    ring = revolve_x(pts)
    # crenellations: notches through the front of the wall
    for k in range(p.cren_n):
        a = 360.0 / p.cren_n * k + 30.0
        n = box(-0.1, p.cren_d, -p.cren_w / 2, p.cren_w / 2, rl + 0.6, RH + 1).edges("|X").fillet(0.4)
        ring = ring.cut(rot_x(n, a))
    # cooling fins over the insert, ending before the thread zone
    xg = p.x_bf - 1.2
    for i in range(p.fin_n):
        ring = ring.cut(revolve_x([(xg - p.fin_w / 2, RH - p.fin_d), (xg + p.fin_w / 2, RH - p.fin_d),
                                   (xg + p.fin_w / 2, RH + 1), (xg - p.fin_w / 2, RH + 1)]))
        xg -= p.fin_pitch
    # one groove over the thread zone
    xg = p.x_bf + 2.0
    ring = ring.cut(revolve_x([(xg - 0.4, RH - 0.5), (xg + 0.4, RH - 0.5), (xg + 0.4, RH + 1), (xg - 0.4, RH + 1)]))
    return ring


def build_insert(p):
    rbore = p.ring_bore / 2 - 0.05
    rb = p.rb - 0.025
    rc = p.opt_d / 2 + 0.05
    rm = p.mcpcb_d / 2 + 0.05
    pts = [(p.x_cup0, rc), (p.x_cup0, rbore - 0.2), (p.x_cup0 + 0.2, rbore), (p.x_bf, rbore), (p.x_bf, rb),
           (p.x_bf + p.spigot_len - 0.2, rb), (p.x_bf + p.spigot_len, rb - 0.2), (p.x_bf + p.spigot_len, 0.0),
           (p.x_mc1, 0.0), (p.x_mc1, rm), (p.x_opt1, rm), (p.x_opt1, rc)]
    if rm > rc:
        pts = [(p.x_cup0, rc), (p.x_cup0, rbore - 0.2), (p.x_cup0 + 0.2, rbore), (p.x_bf, rbore), (p.x_bf, rb),
               (p.x_bf + p.spigot_len - 0.2, rb), (p.x_bf + p.spigot_len, rb - 0.2), (p.x_bf + p.spigot_len, 0.0),
               (p.x_mc1, 0.0), (p.x_mc1, rm), (p.x_opt1, rm), (p.x_opt1, rc)]
    ins = revolve_x(pts)
    # face O-ring groove in the rear face of the flange (between bore and band)
    g0 = p.rb + 0.25
    ins = ins.cut(revolve_x([(p.x_bf - 0.6, g0), (p.x_bf - 0.6, g0 + 1.05), (p.x_bf + 0.01, g0 + 1.05),
                             (p.x_bf + 0.01, g0)]))
    # key on the spigot (+Y), into the band notch
    ins = ins.union(box(p.x_bf, p.x_bf + p.spigot_len - 0.1, rb - 0.4, p.rb + 0.6, -0.5, 0.5))
    # LED wire holes through the shelf (at -Z, outside the LED board)
    for a in (-30.0, 30.0):
        r = min(p.mcpcb_d / 2 + 0.9, p.rb - 1.0)
        y, z = r * math.sin(math.radians(a)), -r * math.cos(math.radians(a))
        ins = ins.cut(cyl_x(1.3, p.x_opt1 - 0.5, p.x_bf + p.spigot_len + 0.1, y, z))
    return ins


def build_face_oring(p):
    g0 = p.rb + 0.25
    return torus_x(p.x_bf - 0.31, g0 + 0.52, 0.29)    # drawn squeezed into its 0.6 mm groove


def build_optic(p):
    """TIR optic stand-in for a 5050 LED: clear PMMA body with a flange, a black holder ring"""
    x0, x1 = p.x_opt0, p.x_opt1
    h = x1 - x0
    r = p.opt_d / 2
    lens = revolve_x([(x0 + 0.05, 0.0), (x0 + 0.05, r - 0.3), (x0 + 1.2, r - 0.3), (x0 + 1.2, r - 0.9),
                      (x0 + 0.62 * h, 0.40 * r), (x1 - 1.8, 0.25 * r), (x1 - 1.8, 0.0)])
    lens = lens.cut(revolve_x([(x1 - 1.85, 0.0), (x1 - 1.85, 0.22 * r), (x1 - 3.4, 0.18 * r),
                               (x1 - 3.6, 0.0)]))
    holder = revolve_x([(x0 + 1.2, r - 0.9), (x0 + 1.2, r), (x1, r), (x1, 0.30 * r), (x1 - 1.8, 0.30 * r),
                        (x1 - 1.8, 0.27 * r), (x0 + 0.62 * h, 0.43 * r)])
    return holder, lens


def build_gasket(p):
    return revolve_x([(p.x_lip1, p.lip_id / 2 + 0.1), (p.x_lip1, p.opt_d / 2), (p.x_opt0, p.opt_d / 2),
                      (p.x_opt0, p.lip_id / 2 + 0.1)])


def build_led(p):
    x0, x1 = p.x_opt1, p.x_mc1
    mc = cyl_x(p.mcpcb_d, x0, x1)
    pkg = box(x0 - 0.75, x0, -2.5, 2.5, -2.5, 2.5)
    dome = (cq.Workplane("YZ").workplane(offset=x0 - 0.75).sphere(2.0)
            .intersect(box(x0 - 2.8, x0 - 0.74, -3, 3, -3, 3)))
    return mc, pkg, dome


def build_collar(p, angle=0.0):
    """angle 0: window at -Z over the port (open); 180: window up (closed)"""
    rbd = p.rband
    ri = rbd + 0.05
    ro = ri + p.collar_wall
    x0, x1 = p.x_c0, p.x_c1
    c = revolve_x([(x0, ri), (x0, ro - 0.35), (x0 + 0.35, ro), (x1 - 0.35, ro), (x1, ro - 0.35), (x1, ri)])
    # window at -Z, inner edge chamfered so it slides over the gasket
    c = c.cut(stadium_xy(p.x_win, p.win_ax, p.win_tan, -ro - 1, -rbd + 1.5))
    c = c.cut(stadium_xy(p.x_win, p.win_ax + 0.6, p.win_tan + 0.6, -ro - 1, -rbd + 1.5).intersect(
        revolve_x([(x0 - 1, 0.0), (x0 - 1, ri + 0.3), (x1 + 1, ri + 0.3), (x1 + 1, 0.0)])))
    # 16 grip flutes
    for k in range(16):
        a = 360.0 / 16 * k + 11.25
        fl = cyl_x(1.5, x0 + 1.2, x1 - 1.2, 0.0, ro + 0.35)
        c = c.cut(rot_x(fl, a))
    if angle:
        c = rot_x(c, angle)
    return c


def port_gasket_ring(p, depth, proud, inset, width):
    """obround ring round the port window, following the band surface between rband - depth and rband + proud"""
    a0, t0 = p.win_ax + 2 * inset, p.win_tan + 2 * inset
    ring = stadium_xy(p.x_win, a0 + 2 * width, t0 + 2 * width, -p.rband - 3, 0).cut(
        stadium_xy(p.x_win, a0, t0, -p.rband - 4, 1))
    shell = revolve_x([(p.x_c0 - 1, p.rband - depth), (p.x_c0 - 1, p.rband + proud), (p.x_c1 + 1, p.rband + proud),
                       (p.x_c1 + 1, p.rband - depth)])
    return ring.intersect(shell)


def build_port_gasket(p):
    """moulded silicone gasket in the band groove, 0.15 mm proud of the band (pressed by the collar's bore)"""
    return port_gasket_ring(p, depth=0.58, proud=0.04, inset=0.22, width=0.86)


def build_sled(p):
    x0, x1 = p.board_x[0] - 0.2, p.x_cell0 - p.strip_t - 0.05
    s = cyl_x(p.bore_d - 0.2, x0, x1).cut(cyl_x(p.bore_d - 1.6, x0 - 1, x1 + 1))
    s = s.cut(box(p.board_x[0] - 0.05, p.board_x[1] + 0.05, -p.board_w / 2 - 0.05, p.board_w / 2 + 0.05,
                  p.z_board_bot - 0.03, p.z_board_top + 0.03))
    # plug access below the socket, pin guide
    s = s.cut(stadium_xy(p.x_win, p.win_ax, p.win_tan, -p.rb - 1, p.z_mouth + 0.5))
    ux, uy = p.usb_body[1], p.usb_body[0]
    s = s.cut(box(p.x_win - ux / 2 - 0.3, p.x_win + ux / 2 + 0.3, -uy / 2 - 0.3, uy / 2 + 0.3, -p.rb - 1,
                  p.z_board_bot + 0.01))
    s = s.cut(cyl_z(2.6, 0.0, p.rb + 1, x=p.x_btn))
    return s


def build_board(p):
    x0, x1 = p.board_x
    zt, zb = p.z_board_top, p.z_board_bot
    w = p.board_w / 2
    brd = box(x0, x1, -w, w, zb, zt).edges("|Z").chamfer(0.8)
    parts = {}
    sx, sy, sh = p.sw_body
    parts["sw_body"] = box(p.x_btn - sx / 2, p.x_btn + sx / 2, -sy / 2, sy / 2, zt + 0.05, zt + 0.05 + sh)
    parts["sw_act"] = cyl_z(1.4, zt + 0.05 + sh, zt + 0.05 + p.sw_h, x=p.x_btn)
    parts["halo_led"] = box(p.x_btn - 0.5, p.x_btn + 0.5, 2.6, 3.6, zt + 0.05, zt + 0.40)
    # bottom side: the vertical USB-C socket under the window, driver, MCU ...
    ux, uy = p.usb_body[1], p.usb_body[0]
    parts["usb_body"] = box(p.x_win - ux / 2, p.x_win + ux / 2, -uy / 2, uy / 2, p.z_mouth, zb)
    parts["usb_shell"] = (stadium_xy(p.x_win, p.usb_shell[1] + 0.3, p.usb_shell[0] + 0.3, p.z_mouth, p.z_mouth + 6.2)
                          .cut(stadium_xy(p.x_win, p.usb_shell[1], p.usb_shell[0], p.z_mouth - 1, p.z_mouth + 6.0)))
    parts["usb_tongue"] = box(p.x_win - 0.35, p.x_win + 0.35, -3.3, 3.3, p.z_mouth + 0.6, p.z_mouth + 6.0)
    room = (x1 - (p.x_win + ux / 2 + 0.5))
    xa = p.x_win + ux / 2 + 0.6
    bot = [("mcu", xa + 3.0, 0.0, 5.0, 5.0, 0.85), ("drv", xa + 3.0, -w + 3.0, 3.0, 3.0, 0.9),
           ("fet", xa + 7.5, w - 3.2, 3.3, 3.3, 0.9), ("ind", xa + 8.0, -1.5, 4.0, 4.0, 2.0),
           ("chg", xa + 12.0, 2.5, 1.6, 2.9, 1.1), ("prot", xa + 12.0, -2.5, 1.6, 2.9, 1.1)]
    for (nm, x, y, lx, ly, h) in bot:
        if x + lx / 2 > x1 - 0.4:
            continue
        parts["b_" + nm] = box(x - lx / 2, x + lx / 2, y - ly / 2, y + ly / 2, zb - 0.05 - h, zb - 0.05)
    tp = None
    for (x, y) in [(x0 + 1.5, 2.0), (x0 + 1.5, -2.0), (x0 + 4.0, 3.0), (p.x_btn - 3.5, -2.5), (p.x_btn + 3.2, 2.0),
                   (x1 - 1.6, -3.0), (x1 - 1.6, 3.0)]:
        b = box(x - 0.5, x + 0.5, y - 0.25, y + 0.25, zt + 0.02, zt + 0.37)
        tp = b if tp is None else tp.union(b)
    parts["top_passives"] = tp
    return brd, parts


def build_button(p):
    x = p.x_btn
    zf = p.z_cb_floor
    cb = p.btn_cb_d
    memb = cyl_z(cb - 0.05, zf, zf + 0.35, x=x).union(cyl_z(2.6, zf - 0.15, zf, x=x))
    zc = zf + 0.35
    collar = (cyl_z(cb - 0.02, zc, zc + 0.95, x=x)
              .cut(cyl_z(p.cap_d + 0.35, zc - 0.1, zc + 0.70, x=x))
              .cut(cyl_z(p.cap_d + 0.1, zc - 0.1, zc + 1.2, x=x)))
    collar = collar.faces(">Z").edges().chamfer(0.12)
    cap = cyl_z(p.cap_d + 0.3, zc, zc + 0.3, x=x).union(cyl_z(p.cap_d - 0.1, zc + 0.3, zc + 1.25, x=x))
    cap = cap.faces(">Z").edges().fillet(0.4)
    # concentric grip rings on the cap face
    for rr in (1.2, 2.2):
        ring = cyl_z(2 * rr + 0.3, zc + 1.1, zc + 1.4, x=x).cut(cyl_z(2 * rr - 0.3, zc + 1.0, zc + 1.5, x=x))
        cap = cap.cut(ring)
    z_sw = p.z_sw_top
    pin = cyl_z(2.4, z_sw + 0.05, zf - 0.15, x=x)
    return memb, collar, cap, pin


def build_cell(p):
    x0, x1 = p.x_cell0, p.x_cell1
    rc = p.cell_d / 2
    can = revolve_x([(x0, 0.0), (x0, rc - 0.6), (x0 + 0.6, rc), (x1 - 0.6, rc), (x1, rc - 0.6), (x1, 0.0)])
    plus = cyl_x(6.0, x0 - 0.05, x0 + 0.1)
    st = p.strip_t
    s_plus = box(x0 - st - 0.02, x0 - 0.02, -2.0, 2.0, -3.0, 4.0)
    zc = -(rc + 0.03)
    s_minus = (box(x1 + 0.02, x1 + 0.02 + st, -2.0, 2.0, zc - st + 0.6, 0.0)
               .union(box(p.board_x[1] - 2.0, x1 + 0.02 + st, -2.0, 2.0, zc - st, zc)))
    insul = cyl_x(p.cell_d - 0.4, x1 + 0.02 + st, x1 + 0.02 + st + p.insul_t)
    return can, plus, s_plus, s_minus, insul


def build_split_ring(p, s=-1, r=7.0, wire=1.0):
    L = p.L
    n = 1 / math.sqrt(2)
    entry_r = p.R - 3.2
    ex, ez = L, s * entry_r
    mx, mz = ex - 1.5, ez + s * 1.5
    cx, cz = mx + r * n, mz + s * r * n
    rings = None
    for dy in (-0.52, 0.52):
        t = cq.Workplane("XY").add(cq.Solid.makeTorus(r, wire / 2, cq.Vector(cx, dy, cz), cq.Vector(0, 1, 0)))
        rings = t if rings is None else rings.union(t)
    return rings


def build_label(p):
    xc = (p.x_btn + p.btn_cb_d / 2 + 2.0 + p.L - 12.0) / 2
    t = (cq.Workplane("XY").workplane(offset=p.flat_r)
         .text(p.label_text, p.label_size, 0.015, font=FONT, kind="regular", halign="center", valign="center"))
    return t.rotate((0, 0, 0), (0, 0, 1), 90).translate((xc, 0, 0))


def build_all(p, collar_angle=0.0):
    d = {}
    d["body"] = build_body(p)
    d["ring"] = build_ring(p)
    d["insert"] = build_insert(p)
    d["face_oring"] = build_face_oring(p)
    d["gasket"] = build_gasket(p)
    d["optic_holder"], d["optic_lens"] = build_optic(p)
    d["mcpcb"], d["led"], d["phosphor"] = build_led(p)
    d["collar"] = build_collar(p, collar_angle)
    d["port_gasket"] = build_port_gasket(p)
    d["sled"] = build_sled(p)
    brd, parts = build_board(p)
    d["board"] = brd
    for k, v in parts.items():
        d["bp_" + k] = v
    d["membrane"], d["btn_collar"], d["cap"], d["pin"] = build_button(p)
    d["cell"], d["cell_plus"], d["strip_plus"], d["strip_minus"], d["insulator"] = build_cell(p)
    d["split_ring"] = build_split_ring(p)
    d["label"] = build_label(p)
    return d


# --------------------------------------------------------------------------------------------- checks
def checks(p, d):
    out = {"name": p.name, "size": p.size, "length_mm": round(p.L, 2), "body_od": p.body_od, "head_od": p.head_od}
    vol = {k: solid(v).Volume() for k, v in d.items() if v is not None}
    rho = {"body": 2.70, "ring": 2.70, "insert": 2.70, "collar": 2.70, "cap": 7.93, "btn_collar": 7.93,
           "sled": 1.41, "pin": 1.19, "optic_holder": 1.20, "optic_lens": 1.19, "mcpcb": 8.96}
    mass = {k: round(vol[k] * rho[k] / 1000, 2) for k in rho if k in vol}
    out["mass_g"] = mass
    out["aluminium_g"] = round(sum(mass[k] for k in ("body", "ring", "insert", "collar")), 2)
    rb, rbd = p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    out["walls_mm"] = {
        "tube over the cell": round(p.R - rb, 2),
        "flats over the cell": round(p.flat_r - rb, 2),
        "under the button counterbore": round(p.z_cb_floor - rb, 2),
        "band (collar seat) over the bore": round(rbd - rb, 2),
        "thread root over the bore": round(d3 - rb, 2),
        "run-out over the bore": round(d3 - 0.05 - rb, 2),
        "bezel over the insert": p.ring_wall,
        "bezel at its fins (over the insert)": round(p.ring_wall - p.fin_d, 2),
        "bezel at its groove (thread zone)": round(p.RH - 0.5 - rbd, 2),
        "band under the port gasket groove": round(rbd - 0.6 - rb, 2),
        "collar at the flutes": round(p.collar_wall - 0.4, 2),
        "tail wall": p.tail_wall,
    }
    out["fits_mm"] = {
        "board width": round(p.board_w, 2),
        "board corner to bore": round(rb - math.hypot(p.board_w / 2, max(abs(p.z_board_top), abs(p.z_board_bot))), 2),
        "socket mouth below the axis": round(p.z_mouth, 2),
        "plug depth: collar surface to socket mouth": round(p.RH - abs(p.z_mouth), 2) if False else
        round((rbd + p.collar_wall + 0.05) - abs(p.z_mouth), 2),
        "button pin length": round(p.z_cb_floor - 0.15 - p.z_sw_top - 0.05, 2),
        "cell radial room": round(rb - p.cell_d / 2, 2),
        "thread engagement": round(p.thread_len - 0.9, 2),
        "port gasket squeeze (mm)": 0.15,
    }
    out["stack_x_mm"] = {k: round(v, 2) for k, v in dict(
        optic=p.x_opt0, led_board=p.x_opt1, band_front=p.x_bf, bezel_rear=p.x_r1, collar0=p.x_c0, collar1=p.x_c1,
        window=p.x_win, shoulder=p.x_sh, button=p.x_btn, board0=p.board_x[0], board1=p.board_x[1],
        cell0=p.x_cell0, cell1=p.x_cell1, L=p.L).items()}
    out["outer_area_mm2"] = round(math.pi * p.body_od * (p.L - p.x_sh) + math.pi * p.head_od * p.x_sh
                                  + math.pi / 4 * p.body_od ** 2 + math.pi / 4 * (p.head_od ** 2 - p.lip_id ** 2), 0)
    pairs = [("body", "insert"), ("body", "ring"), ("ring", "insert"), ("body", "collar"), ("ring", "collar"),
             ("body", "sled"), ("body", "cell"), ("sled", "board"), ("body", "board"), ("insert", "optic_holder"),
             ("insert", "mcpcb"), ("body", "pin"), ("body", "btn_collar"), ("sled", "pin"), ("sled", "cell"),
             ("body", "strip_minus"), ("cell", "strip_minus"), ("body", "bp_usb_body"), ("sled", "bp_usb_body"),
             ("body", "bp_usb_shell"), ("collar", "port_gasket"), ("insert", "sled"), ("ring", "optic_lens"),
             ("ring", "gasket"), ("body", "face_oring")]
    no_thread = box(p.x_r1 + 0.05, p.L + 1, -30, 30, -30, 30).val()
    inter = {}
    for a, b in pairs:
        try:
            if (a, b) == ("body", "ring"):
                v = solid(d[a]).intersect(solid(d[b])).intersect(no_thread).Volume()
            else:
                v = solid(d[a]).intersect(solid(d[b])).Volume()
        except Exception as e:  # pragma: no cover
            v = "err %s" % e
        inter["%s / %s" % (a, b)] = round(v, 4) if isinstance(v, float) else v
    out["interference_mm3"] = inter
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_dir = args[0] if args else os.path.join(HERE, "..", "..", "cad")
    sizes = ["18", "14"]
    if "--size" in sys.argv:
        v = sys.argv[sys.argv.index("--size") + 1]
        sizes = ["18", "14"] if v == "both" else [v]
    os.makedirs(out_dir, exist_ok=True)
    allinfo = {}
    for sz in sizes:
        p = P(size=sz)
        d = build_all(p)
        nm = p.name
        for shape, part in ((build_body(p, cosmetic=False), "body"), (build_ring(p, cosmetic=False), "bezel"),
                            (d["insert"], "insert"), (d["collar"], "collar")):
            cq.exporters.export(shape, os.path.join(out_dir, "%s_%s.step" % (nm, part)))
        asm = cq.Assembly(name=nm + "_v0.2")
        for k, v in d.items():
            if v is not None and k != "split_ring":
                asm.add(v, name=k)
        asm.save(os.path.join(out_dir, "%s_v0.2_assembly.step" % nm))
        info = {"params": asdict(p)}
        info.update(checks(p, d))
        allinfo[nm] = info
        print(json.dumps({k: info[k] for k in ("name", "length_mm", "aluminium_g", "walls_mm", "fits_mm",
                                               "interference_mm3", "stack_x_mm", "outer_area_mm2")}, indent=1))
    with open(os.path.join(out_dir, "edco_v02_interface.json"), "w") as f:
        json.dump(allinfo, f, indent=1)


if __name__ == "__main__":
    main()
