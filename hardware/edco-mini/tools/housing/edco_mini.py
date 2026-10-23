#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""EDCO Mini v0.1 housing and cartridge, CadQuery (LuxLibre reference design #3), in two sizes, both at most 70 mm:

    EDCO Mini-14   one 14350 cell, Ø17 body, Ø19 head   (the slim version)
    EDCO Mini-16   one 16340 cell, Ø20 body, Ø22 head

The small sister of EDCO v0.2: the same sealed build (a crenellated bezel clamps the LED holder, the cartridge
slides in from the front and the bezel is locked for good), but no twist collar: the USB-C socket is a
waterproof one that seals in its own hole, so the head only needs to be 2 mm larger than the body.

Front to tail:
    bezel ring  - crenellated, three fins, screws onto the band's external thread (M17 x 0.5 / M20 x 0.5),
                  clamps the LED holder (insert) metal on metal and presses the optic onto its gasket
    insert      - LED holder: a cup for the optic, the LED board on a shelf, a face O-ring on its rear face
                  against the band's front face, a key that stops it turning while the bezel is tightened
    body        - the band (thread), the head section (the same diameter as the bezel) with the USB-C hole
                  (-Z), the two side-light windows and the button (+Z); then the tube with six flats, the label,
                  three tail grooves, and a tab at the tail (two bevels, two flats) with a long keyring hole through
                  it (M version: two magnets in the tab's end face)
    cartridge   - insert, main board in a POM sled (waterproof USB-C socket on its underside, looking down
                  through the hole, axial; the switch, the halo LED and the red and UV side LEDs on its top
                  side, under the button pin and two clear light rods), the cell

Frame: X along the light, X = 0 at the front of the bezel's crenellations, X = L at the tail face; button on
+Z; port on -Z (under the button). Units mm.

Each size comes in two versions: without a magnet, and M (Mini-16M, Mini-14M) with two magnets in the tail tab's end.

usage:  python3 edco_mini.py <out_dir> [--size 14|16|both]
"""
import json
import math
import os
import sys
from dataclasses import dataclass, asdict

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-SemiBold.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"

SIZES = {
    # body, head (= bezel = head section), bore, band (thread major), cell, optic, LED board, flats, button, magnet.
    # Mini-14: a made-to-order high-rate LiPo cell Ø14 x 35 (no off-the-shelf high-drain 14350 found), Carclo 12079
    #          10 mm IP66 spot optic (flange Ø12.5, about 6 mm tall: inferred from the drawing); M version: two
    #          supermagnete S-04-02-N (Ø4 x 2, N45, about 420 g each) in the end of the tail tab
    # Mini-16: Vapcell INR16340 T6 (650 mAh, 6 A; Ø16.5 x 34.0) or T9 (950 mAh, 3 A); the bay takes 16.6 x 34.5.
    #          LEDiL FA10887 TINA-RS for XP-E (Ø16.1 x 9.7, 13 deg; its fit over the SST-20 dome is to be checked),
    #          M version: two supermagnete S-05-02-N52N (Ø5 x 2, N52, about 680 g each) in the end of the tail tab
    # Both: Luminus SST-20-W Gen 2 (3.45 mm, 3.0 A maximum)
    "14": dict(name="EDCO Mini-14", body_od=17.0, head_od=19.0, bore_d=15.0, band_d=17.0, cell_d=14.0,
               cell_len=35.0, cell_name="14350", opt_d=12.5, opt_h=6.0, mcpcb_d=12.0, mcpcb_t=1.2, led_w=3.45,
               flat_r=8.3, cap_d=5.8, btn_cb_d=7.4, mag_d=4.0, mag_t=2.0, mag_y=2.9, lug_t=8.5, hole_l=8.0, hole_w=3.0, tab_rc=3.0),
    "16": dict(name="EDCO Mini-16", body_od=20.0, head_od=22.0, bore_d=17.4, band_d=20.0, cell_d=16.6,
               cell_len=34.5, cell_name="16340", opt_d=16.1, opt_h=9.7, mcpcb_d=16.0, mcpcb_t=1.5, led_w=3.45,
               flat_r=9.6, cap_d=6.5, btn_cb_d=8.2, mag_d=5.0, mag_t=2.0, mag_y=3.3, lug_t=10.0, hole_l=10.0, hole_w=3.2, tab_rc=3.5),
}


@dataclass
class P:
    size: str = "14"
    name: str = ""
    body_od: float = 0.0
    head_od: float = 0.0
    bore_d: float = 0.0
    band_d: float = 0.0
    cell_d: float = 0.0
    cell_len: float = 0.0
    cell_name: str = ""
    opt_d: float = 0.0
    opt_h: float = 0.0
    mcpcb_d: float = 0.0
    mcpcb_t: float = 1.2
    led_w: float = 3.45          # LED package (square)
    flat_r: float = 0.0          # six flats along the tube, at this distance from the axis
    cap_d: float = 0.0           # stainless button cap
    btn_cb_d: float = 0.0        # counterbore for the membrane + collar
    magnet: bool = False         # the M version: two NdFeB discs flush in the end face of the tail tab
    mag_d: float = 4.0
    mag_t: float = 2.0
    mag_y: float = 4.4           # magnet centres at (+-mag_y, 0) on the tab's end face
    lug_t: float = 8.5           # tail tab: thickness between its two flats (Z)
    hole_l: float = 8.0          # keyring hole through the tab (Z): long side across (Y)
    hole_w: float = 3.0          #   and short side along the light (X): wide enough for a split ring through the tab
    # common
    pitch: float = 0.5           # M17 x 0.5 / M20 x 0.5
    fin_n: int = 3               # cooling fins round the bezel
    fin_d: float = 0.35
    fin_w: float = 0.8
    fin_pitch: float = 1.7
    cren_n: int = 6              # crenellations
    cren_w: float = 2.8
    cren_d: float = 1.0
    lip_t: float = 0.6           # bezel lip over the optic
    gasket_t: float = 0.4        # optic gasket (silicone)
    opt_in_ring: float = 1.2     # front part of the optic inside the bezel's small bore
    shelf_t: float = 1.2         # solid insert floor behind the LED board
    thread_len: float = 3.0
    spigot_len: float = 1.0      # insert spigot in the bore (centring + key)
    face_or_cs: float = 0.6      # face O-ring between insert and band
    head_gap: float = 0.15       # bezel rear face to the head-section shoulder (the bezel must clamp the insert)
    mouth_recess: float = 0.25   # socket mouth below the head surface (the plug's overmould sits on the crest)
    usb_h: float = 7.45          # waterproof vertical USB-C, board to mouth (SHOU HAN 16PFS LTH7.45, C3020055)
    usb_shell: tuple = (8.94, 3.26)     # along X (axial), across Y
    usb_seal: tuple = (9.5, 3.8)        # sealing ring round the shell = the hole in the head wall
    usb_body: tuple = (9.6, 4.6)        # plastic body inside the bore (X, Y)
    usb_seal_h: float = 1.0
    sw_h: float = 2.0            # Alps SKRK incl. actuator
    sw_body: tuple = (2.9, 3.9, 1.5)
    board_t: float = 0.8
    uv_led: tuple = (3.5, 3.5, 1.23)   # 365 nm UV LED: Nichia NVSU233B-U365 (3.5 x 3.5 x 1.23)
    red_led: tuple = (2.04, 1.64, 0.7) # red LED, 2.0 x 1.6 mm power LED (e.g. LUXEON C Color Red, to be confirmed)
    uv_rod_d: float = 3.0        # UV-transmitting light rod
    red_rod_d: float = 2.4
    win_y: tuple = (-1.75, 1.75) # rod positions across: UV, red
    strip_t: float = 0.15
    insul_t: float = 0.15
    tail_wall: float = 1.2       # metal between the cell bay and the keyring hole
    end_bar: float = 2.8         # the tab's end beyond the hole (the loop the ring goes round)
    ramp_deg: float = 55.0       # slope of the bevels from the round tube down to the tab's flats
    tab_rc: float = 3.0          # the tab's end corners, rounded in the top view
    end_chamfer: float = 1.0     # 45 deg chamfer on the end's top and bottom edges (a slimmer loop)
    tail_grooves: int = 3
    groove_w: float = 0.7
    groove_d: float = 0.4
    label_text: str = "EDCO"
    label_size: float = 2.0

    def __post_init__(self):
        for k, v in SIZES[self.size].items():
            setattr(self, k, v)
        if self.magnet:
            self.name += "M"

    # ---- derived (X)
    @property
    def R(self): return self.body_od / 2
    @property
    def RH(self): return self.head_od / 2
    @property
    def rb(self): return self.bore_d / 2
    @property
    def rband(self): return self.band_d / 2
    @property
    def ring_bore(self): return self.band_d                    # the insert flange is as large as the band
    @property
    def ring_wall(self): return (self.head_od - self.ring_bore) / 2
    @property
    def lip_id(self): return self.opt_d - 1.4
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
    def x_hs0(self): return self.x_r1 + self.head_gap           # head section shoulder
    @property
    def board_x0(self): return self.x_bf + self.spigot_len + 0.3
    @property
    def x_win(self): return self.board_x0 + 0.5 + self.uv_led[0] / 2
    @property
    def pocket_r(self): return self.btn_cb_d / 2 + 0.9
    @property
    def x_btn(self):
        a = self.x_win + self.uv_rod_d / 2 + 0.05 + 0.9 + self.pocket_r
        b = self.x_hs0 + self.pocket_r + 0.6
        c = self.board_x0 + self.usb_body[0] / 2 + 0.3
        return max(a, b, c)
    @property
    def board_x1(self):
        return self.x_btn + max(self.usb_body[0] / 2, self.sw_body[0] / 2 + 1.0) + 0.4
    @property
    def x_step(self): return max(self.board_x1, self.x_btn + self.pocket_r + 0.6) + 0.3   # head section -> tube
    @property
    def x_cell0(self): return self.board_x1 + 0.75
    @property
    def x_cell1(self): return self.x_cell0 + self.cell_len
    @property
    def x_bay1(self): return self.x_cell1 + self.strip_t + self.insul_t + 0.1
    @property
    def x_hole(self): return self.x_bay1 + self.tail_wall + self.hole_w / 2   # keyring hole centre
    @property
    def L(self): return self.x_bay1 + self.tail_wall + self.hole_w + self.end_bar
    @property
    def ramp_len(self): return (self.R - self.lug_t / 2) / math.tan(math.radians(self.ramp_deg))
    @property
    def x_grooves(self): return [self.x_bay1 - 1.0 - i * 1.6 for i in range(self.tail_grooves)]
    @property
    def x_flats_end(self): return min(self.x_grooves) - self.groove_w / 2 - 0.8
    # ---- derived (Z)
    @property
    def z_mouth(self): return -(self.RH - self.mouth_recess)
    @property
    def z_board_bot(self): return self.z_mouth + self.usb_h
    @property
    def z_board_top(self): return self.z_board_bot + self.board_t
    @property
    def z_sw_top(self): return self.z_board_top + 0.05 + self.sw_h
    @property
    def z_pocket(self): return self.RH - 0.5                    # pocket floor (round scallop)
    @property
    def z_cb_floor(self): return self.z_pocket - 0.6
    @property
    def z_usb_in(self):   # bottom of the socket's plastic body: its corners just clear the bore
        return -math.sqrt(self.rb ** 2 - (self.usb_body[1] / 2) ** 2) + 0.15
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


def cyl_y(d, y0, y1, x=0.0, z=0.0):
    return cyl(d, (x, y0, z), (0, 1, 0), y1 - y0)


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def stadium_ax(xc, lx, wy, z0, z1):
    """stadium in the XY plane, long axis along X, extruded along Z"""
    return cq.Workplane("XY").workplane(offset=z0).center(xc, 0).slot2D(lx, wy, 0).extrude(z1 - z0)


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
    R, RH, L, rb, rbd = p.R, p.RH, p.L, p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch                       # external minor radius (d3 / 2)
    x0 = p.x_bf
    xt1 = p.x_bf + p.thread_len - 0.5                 # thread run-out
    pts = [(x0, 0.0), (x0, rbd - 0.15), (x0 + 0.15, rbd)]
    if cosmetic:
        pts += thread_zigzag(x0 + 0.4, xt1, rbd, d3, p.pitch)[1:]
    else:
        pts += [(xt1, rbd)]
    xs = p.x_step
    pts += [(xt1, d3 - 0.05), (p.x_hs0, d3 - 0.05), (p.x_hs0, RH - 0.3), (p.x_hs0 + 0.3, RH), (xs, RH),
            (xs + 0.8, R), (L - 0.5, R), (L, R - 0.5), (L, 0.0)]
    body = revolve_x(pts)
    # cell bay (+ entry chamfer)
    body = body.cut(revolve_x([(x0 - 0.1, 0.0), (x0 - 0.1, rb + 0.2), (x0 + 0.2, rb), (p.x_bay1, rb),
                               (p.x_bay1, 0.0)]))
    # anti-rotation notch for the insert key (+Y), from the front face
    body = body.cut(box(x0 - 0.1, x0 + p.spigot_len + 0.1, rb - 0.2, rb + 0.6, -0.5, 0.5))
    # USB-C hole at -Z (axial obround, the socket's sealing ring seals in it)
    body = body.cut(stadium_ax(p.x_btn, p.usb_seal[0] + 0.1, p.usb_seal[1] + 0.1, -RH - 2, 0.0))
    # side-light windows at +Z (two rods side by side, in front of the button)
    for (d, y) in ((p.uv_rod_d, p.win_y[0]), (p.red_rod_d, p.win_y[1])):
        body = body.cut(cyl_z(d + 0.1, 0.0, RH + 2, x=p.x_win, y=y))
    # six flats on the tube, from the step to the tail grooves
    xf0, xf1 = p.x_step + 1.2, p.x_flats_end
    for k in range(6):
        cutter = box(xf0, xf1, -20, 20, p.flat_r, p.flat_r + 6)
        body = body.cut(rot_x(cutter, 60 * k))
    # button pocket (round scallop in the head section), counterbore, pin hole
    pocket = cyl_z(2 * p.pocket_r, p.z_pocket, RH + 2, x=p.x_btn).edges("<Z").fillet(0.4)
    body = body.cut(pocket)
    body = body.cut(cyl_z(p.btn_cb_d, p.z_cb_floor, RH + 2, x=p.x_btn))
    body = body.cut(cyl_z(2.6, 0.0, p.z_cb_floor + 0.01, x=p.x_btn))
    # tail grooves, just in front of the tab
    for xg in p.x_grooves:
        body = body.cut(revolve_x([(xg - p.groove_w / 2, R - p.groove_d), (xg + p.groove_w / 2, R - p.groove_d),
                                   (xg + p.groove_w / 2, R + 1), (xg - p.groove_w / 2, R + 1)]))
    # tail tab: two bevels and flats (+Z, -Z) behind the cell bay, a long keyring hole through it, and (M version)
    # two magnet pockets in its end face
    for s in (1, -1):
        body = body.cut(tab_cutter(p, s))
    body = body.cut(cq.Workplane("XY").workplane(offset=-p.R - 1).center(p.x_hole, 0)
                    .slot2D(p.hole_l, p.hole_w, 90).extrude(2 * p.R + 2))
    # rounded end corners (top view) and chamfered end edges
    rc = p.tab_rc
    keep = box(p.L - 2 * rc - 1.0, p.L, -p.R, p.R, -p.R - 1, p.R + 1).edges("|Z").edges(">X").fillet(rc)
    body = body.cut(box(p.L - 2 * rc - 0.5, p.L + 1, -p.R - 1, p.R + 1, -p.R - 1, p.R + 1).cut(keep))
    c = p.end_chamfer
    for s in (1, -1):
        tri = [(p.L - c, s * (p.lug_t / 2 + 0.01)), (p.L + 0.01, s * (p.lug_t / 2 + 0.01)),
               (p.L + 0.01, s * (p.lug_t / 2 - c))]
        body = body.cut(cq.Workplane("XZ").polyline(tri).close().extrude(p.R + 2, both=True))
    if p.magnet:
        for sy in (1, -1):
            body = body.cut(cyl_x(p.mag_d + 0.1, p.L - p.mag_t - 0.1, p.L + 1, y=sy * p.mag_y))
    return body


def tab_cutter(p, s):
    """removes everything beyond z = s * lug_t / 2 behind the cell bay, with a bevel from the round tube"""
    t = math.tan(math.radians(p.ramp_deg))
    x0 = p.x_bay1                                       # the bevel starts where the cell bay ends
    top = p.R + 2.0
    pts = [(x0 - (top - p.R) / t, top), (x0 + p.ramp_len, p.lug_t / 2), (p.L + 1, p.lug_t / 2), (p.L + 1, top)]
    pts = [(x, s * z) for (x, z) in pts]
    return cq.Workplane("XZ").polyline(pts).close().extrude(p.R + 2, both=True)


def tail_clearances(p):
    """metal left round the tail tab's keyring hole and the magnets, mm"""
    out = {"cell bay to the keyring hole": round(p.tail_wall, 2),
           "tab end beyond the hole": round(p.end_bar, 2),
           "tab beside the hole (at its flats)": round(math.sqrt(p.R ** 2 - (p.lug_t / 2) ** 2) - p.hole_l / 2, 2),
           "tube under the tail grooves": round(p.R - p.groove_d - p.rb, 2)}
    if p.magnet:
        out["magnet pockets to the keyring hole"] = round(p.end_bar - p.mag_t - 0.1, 2)
        out["magnet pockets to the end chamfers"] = round(p.lug_t / 2 - p.end_chamfer - (p.mag_d + 0.1) / 2, 2)
        out["magnet pockets to the rounded corners"] = round(p.R - p.tab_rc - p.mag_y - (p.mag_d + 0.1) / 2, 2)
    return out


def build_ring(p, cosmetic=True):
    RH = p.RH
    rbd = p.rband
    D1 = rbd - 0.5413 * p.pitch                        # internal minor radius (D1 / 2)
    rbore = p.ring_bore / 2 + 0.05
    rsmall = p.opt_d / 2 + 0.1
    rl = p.lip_id / 2
    pts = [(0.0, rl + 0.3), (0.0, RH - 0.4), (0.4, RH), (p.x_r1 - 0.3, RH), (p.x_r1, RH - 0.3), (p.x_r1, D1)]
    if cosmetic:
        th = thread_zigzag(p.x_bf + 0.2, p.x_r1 - 0.2, D1, rbd, p.pitch)
        pts += list(reversed(th))
    pts += [(p.x_bf, rbd + 0.05), (p.x_bf, rbore), (p.x_cup0, rbore), (p.x_cup0, rsmall), (p.x_lip1, rsmall),
            (p.x_lip1, rl), (p.cren_d + 0.15, rl)]
    ring = revolve_x(pts)
    # crenellations: notches through the front of the wall
    for k in range(p.cren_n):
        a = 360.0 / p.cren_n * k + 30.0
        n = box(-0.1, p.cren_d, -p.cren_w / 2, p.cren_w / 2, rl + 0.5, RH + 1).edges("|X").fillet(0.35)
        ring = ring.cut(rot_x(n, a))
    # cooling fins over the insert, ending before the thread zone
    xg = p.x_bf - 1.0
    for i in range(p.fin_n):
        ring = ring.cut(revolve_x([(xg - p.fin_w / 2, RH - p.fin_d), (xg + p.fin_w / 2, RH - p.fin_d),
                                   (xg + p.fin_w / 2, RH + 1), (xg - p.fin_w / 2, RH + 1)]))
        xg -= p.fin_pitch
    return ring


def build_insert(p):
    rbore = p.ring_bore / 2 - 0.05
    rb = p.rb - 0.025
    rc = p.opt_d / 2 + 0.05
    rm = p.mcpcb_d / 2 + 0.05
    pts = [(p.x_cup0, rc), (p.x_cup0, rbore - 0.15), (p.x_cup0 + 0.15, rbore), (p.x_bf, rbore), (p.x_bf, rb),
           (p.x_bf + p.spigot_len - 0.15, rb), (p.x_bf + p.spigot_len, rb - 0.15), (p.x_bf + p.spigot_len, 0.0),
           (p.x_mc1, 0.0), (p.x_mc1, rm), (p.x_opt1, rm), (p.x_opt1, rc)]
    ins = revolve_x(pts)
    # face O-ring groove in the rear face of the flange (between the bore and the band's edge)
    g0, gw = p.rb + 0.15, p.face_or_cs + 0.1
    ins = ins.cut(revolve_x([(p.x_bf - 0.45, g0), (p.x_bf - 0.45, g0 + gw), (p.x_bf + 0.01, g0 + gw),
                             (p.x_bf + 0.01, g0)]))
    # key on the spigot (+Y), into the band notch
    ins = ins.union(box(p.x_bf, p.x_bf + p.spigot_len - 0.1, rb - 0.3, p.rb + 0.45, -0.4, 0.4))
    # LED wire holes through the shelf (at -Z, outside the LED board)
    for a in (-35.0, 35.0):
        r = min(p.mcpcb_d / 2 + 0.7, p.rb - 0.8)
        y, z = r * math.sin(math.radians(a)), -r * math.cos(math.radians(a))
        ins = ins.cut(cyl_x(1.0, p.x_opt1 - 0.5, p.x_bf + p.spigot_len + 0.1, y, z))
    return ins


def build_face_oring(p):
    g0 = p.rb + 0.15
    cs = p.face_or_cs
    return torus_x(p.x_bf - 0.45 + cs * 0.4 - 0.05, g0 + 0.05 + cs / 2, cs * 0.4)   # drawn squeezed


def build_optic(p):
    """TIR optic stand-in: clear PMMA body with a flange, a black holder ring"""
    x0, x1 = p.x_opt0, p.x_opt1
    h = x1 - x0
    r = p.opt_d / 2
    lens = revolve_x([(x0 + 0.05, 0.0), (x0 + 0.05, r - 0.25), (x0 + 1.0, r - 0.25), (x0 + 1.0, r - 0.8),
                      (x0 + 0.62 * h, 0.40 * r), (x1 - 1.4, 0.27 * r), (x1 - 1.4, 0.0)])
    lens = lens.cut(revolve_x([(x1 - 1.45, 0.0), (x1 - 1.45, 0.24 * r), (x1 - 2.8, 0.20 * r),
                               (x1 - 3.0, 0.0)]))
    holder = revolve_x([(x0 + 1.0, r - 0.8), (x0 + 1.0, r), (x1, r), (x1, 0.32 * r), (x1 - 1.4, 0.32 * r),
                        (x1 - 1.4, 0.29 * r), (x0 + 0.62 * h, 0.43 * r)])
    return holder, lens


def build_gasket(p):
    return revolve_x([(p.x_lip1, p.lip_id / 2 + 0.1), (p.x_lip1, p.opt_d / 2), (p.x_opt0, p.opt_d / 2),
                      (p.x_opt0, p.lip_id / 2 + 0.1)])


def build_led(p):
    x0, x1 = p.x_opt1, p.x_mc1
    mc = cyl_x(p.mcpcb_d, x0, x1)
    w = p.led_w / 2
    pkg = box(x0 - 0.6, x0, -w, w, -w, w)
    dome = (cq.Workplane("YZ").workplane(offset=x0 - 0.6).sphere(w * 0.82)
            .intersect(box(x0 - 2.5, x0 - 0.59, -3, 3, -3, 3)))
    return mc, pkg, dome


def build_usb(p):
    """waterproof vertical USB-C: metal shell through the hole, a sealing ring in the hole, the plastic body inside"""
    xc = p.x_btn
    sx, sy = p.usb_shell
    zm = p.z_mouth
    z_ring0 = -math.sqrt(p.RH ** 2 - (p.usb_seal[1] / 2) ** 2) + 0.35       # ring starts just inside the surface
    shell = stadium_ax(xc, sx, sy, zm, p.z_usb_in + 0.3).cut(stadium_ax(xc, sx - 0.4, sy - 0.4, zm - 1, p.z_usb_in))
    tongue = box(xc - 3.3, xc + 3.3, -0.35, 0.35, zm + 0.6, p.z_usb_in)
    seal = stadium_ax(xc, p.usb_seal[0], p.usb_seal[1], z_ring0, z_ring0 + p.usb_seal_h).cut(
        stadium_ax(xc, sx, sy, z_ring0 - 1, z_ring0 + p.usb_seal_h + 1))
    bx, by = p.usb_body
    body = box(xc - bx / 2, xc + bx / 2, -by / 2, by / 2, p.z_usb_in, p.z_board_bot)
    return shell, tongue, seal, body


def build_sled(p):
    x0, x1 = p.board_x0 - 0.2, p.x_cell0 - p.strip_t - 0.05
    s = cyl_x(p.bore_d - 0.2, x0, x1).cut(cyl_x(p.bore_d - 1.4, x0 - 1, x1 + 1))
    s = s.cut(box(p.board_x0 - 0.05, p.board_x1 + 0.05, -p.board_w / 2 - 0.05, p.board_w / 2 + 0.05,
                  p.z_board_bot - 0.03, p.z_board_top + 0.03))
    bx, by = p.usb_body
    s = s.cut(box(p.x_btn - bx / 2 - 0.3, p.x_btn + bx / 2 + 0.3, -by / 2 - 0.3, by / 2 + 0.3, -p.rb - 1,
                  p.z_board_bot + 0.01))
    s = s.cut(cyl_z(2.6, 0.0, p.rb + 1, x=p.x_btn))
    for (d, y) in ((p.uv_rod_d, p.win_y[0]), (p.red_rod_d, p.win_y[1])):
        s = s.cut(cyl_z(d + 0.3, 0.0, p.rb + 1, x=p.x_win, y=y))
    return s


def build_board(p):
    x0, x1 = p.board_x0, p.board_x1
    zt, zb = p.z_board_top, p.z_board_bot
    w = p.board_w / 2
    brd = box(x0, x1, -w, w, zb, zt).edges("|Z").chamfer(0.6)
    parts = {}
    sx, sy, sh = p.sw_body
    parts["sw_body"] = box(p.x_btn - sx / 2, p.x_btn + sx / 2, -sy / 2, sy / 2, zt + 0.05, zt + 0.05 + sh)
    parts["sw_act"] = cyl_z(1.4, zt + 0.05 + sh, zt + 0.05 + p.sw_h, x=p.x_btn)
    parts["halo_led"] = box(p.x_btn - 0.5, p.x_btn + 0.5, 2.4, 3.4, zt + 0.05, zt + 0.40)
    ux, uy, uh = p.uv_led
    parts["uv_led"] = box(p.x_win - ux / 2, p.x_win + ux / 2, p.win_y[0] - uy / 2, p.win_y[0] + uy / 2,
                          zt + 0.05, zt + 0.05 + uh)
    rx, ry, rh = p.red_led
    parts["red_led"] = box(p.x_win - rx / 2, p.x_win + rx / 2, p.win_y[1] - ry / 2, p.win_y[1] + ry / 2,
                           zt + 0.05, zt + 0.05 + rh)
    # bottom side: MCU, driver, inductor, protection, charger between the board's front end and the socket
    xa = p.board_x0 + 0.4
    xb = p.x_btn - p.usb_body[0] / 2 - 0.3
    bot = [("mcu", 5.0, 5.0, 0.85), ("ind", 4.0, 4.0, 2.0)]
    xx = xa
    for (nm, lx, ly, h) in bot:
        if xx + lx > xb:
            break
        parts["b_" + nm] = box(xx, xx + lx, -ly / 2, ly / 2, zb - 0.05 - h, zb - 0.05)
        xx += lx + 0.4
    tp = None
    for (x, y) in [(x0 + 0.9, 3.2), (x0 + 0.9, -3.4), (p.x_btn - 2.6, -2.6), (p.x_btn + 2.5, 2.2),
                   (x1 - 1.2, -2.8), (x1 - 1.2, 2.8), (p.x_win + 2.4, 0.2)]:
        b = box(x - 0.5, x + 0.5, y - 0.25, y + 0.25, zt + 0.02, zt + 0.37)
        tp = b if tp is None else tp.union(b)
    parts["top_passives"] = tp
    return brd, parts


def build_rods(p):
    """UV-transmitting light rods from the side LEDs to the head surface (bonded in their holes)"""
    out = []
    shell = cyl_x(2 * (p.RH - 0.05), p.x_win - 3, p.x_win + 3)
    for (d, y, led) in ((p.uv_rod_d, p.win_y[0], p.uv_led), (p.red_rod_d, p.win_y[1], p.red_led)):
        z0 = p.z_board_top + 0.05 + led[2] + 0.05
        out.append(cyl_z(d, z0, p.RH + 1, x=p.x_win, y=y).intersect(shell))
    return out


def build_button(p):
    x = p.x_btn
    zf = p.z_cb_floor
    cb = p.btn_cb_d
    memb = cyl_z(cb - 0.05, zf, zf + 0.35, x=x).union(cyl_z(2.6, zf - 0.15, zf, x=x))
    zc = zf + 0.35
    collar = (cyl_z(cb - 0.02, zc, zc + 0.9, x=x)
              .cut(cyl_z(p.cap_d + 0.35, zc - 0.1, zc + 0.65, x=x))
              .cut(cyl_z(p.cap_d + 0.1, zc - 0.1, zc + 1.2, x=x)))
    collar = collar.faces(">Z").edges().chamfer(0.1)
    cap = cyl_z(p.cap_d + 0.3, zc, zc + 0.3, x=x).union(cyl_z(p.cap_d - 0.1, zc + 0.3, zc + 1.15, x=x))
    cap = cap.faces(">Z").edges().fillet(0.35)
    for rr in (1.0, 1.9):
        ring = cyl_z(2 * rr + 0.25, zc + 1.0, zc + 1.3, x=x).cut(cyl_z(2 * rr - 0.25, zc + 0.9, zc + 1.4, x=x))
        cap = cap.cut(ring)
    pin = cyl_z(2.4, p.z_sw_top + 0.05, zf - 0.15, x=x)
    return memb, collar, cap, pin


def build_cell(p):
    x0, x1 = p.x_cell0, p.x_cell1
    rc = p.cell_d / 2
    can = revolve_x([(x0, 0.0), (x0, rc - 0.5), (x0 + 0.5, rc), (x1 - 0.5, rc), (x1, rc - 0.5), (x1, 0.0)])
    plus = cyl_x(5.0, x0 - 0.05, x0 + 0.1)
    st = p.strip_t
    s_plus = box(x0 - st - 0.02, x0 - 0.02, -1.8, 1.8, -3.0, 3.5)
    zc = -(rc + 0.03)
    s_minus = (box(x1 + 0.02, x1 + 0.02 + st, -1.8, 1.8, zc - st + 0.5, 0.0)
               .union(box(p.board_x1 - 1.5, x1 + 0.02 + st, -1.8, 1.8, zc - st, zc)))
    insul = cyl_x(p.cell_d - 0.4, x1 + 0.02 + st, x1 + 0.02 + st + p.insul_t)
    return can, plus, s_plus, s_minus, insul


def build_magnet(p):
    if not p.magnet:
        return None
    m = None
    for sy in (1, -1):
        c = cyl_x(p.mag_d, p.L - p.mag_t - 0.08, p.L - 0.08, y=sy * p.mag_y)
        m = c if m is None else m.union(c)
    return m


def build_split_ring(p, wire=0.8):
    """a split ring (two turns) through the tab's keyring hole and round the tab's end. It lies in the XZ plane; at
    mid-depth it touches the hole's front, and where it leaves the tab (at the flats) it is still inside the hole"""
    r = 6.0 if p.size == "14" else 8.0
    hs = p.x_hole - p.hole_w / 2
    cx = hs + wire / 2 + 0.15 + r
    rings = None
    for dy in (-0.42, 0.42):
        tr = cq.Workplane("XY").add(cq.Solid.makeTorus(r, wire / 2, cq.Vector(cx, dy, 0.0), cq.Vector(0, 1, 0)))
        rings = tr if rings is None else rings.union(tr)
    return rings


def build_label(p):
    xc = (p.x_step + 1.2 + p.x_flats_end) / 2
    t = (cq.Workplane("XY").workplane(offset=p.flat_r)
         .text(p.label_text, p.label_size, 0.015, font=FONT, kind="regular", halign="center", valign="center"))
    return t.rotate((0, 0, 0), (0, 0, 1), 90).translate((xc, 0, 0))


def build_all(p):
    d = {}
    d["body"] = build_body(p)
    d["ring"] = build_ring(p)
    d["insert"] = build_insert(p)
    d["face_oring"] = build_face_oring(p)
    d["gasket"] = build_gasket(p)
    d["optic_holder"], d["optic_lens"] = build_optic(p)
    d["mcpcb"], d["led"], d["phosphor"] = build_led(p)
    d["usb_shell"], d["usb_tongue"], d["usb_seal"], d["usb_body"] = build_usb(p)
    d["sled"] = build_sled(p)
    brd, parts = build_board(p)
    d["board"] = brd
    for k, v in parts.items():
        d["bp_" + k] = v
    d["uv_rod"], d["red_rod"] = build_rods(p)
    d["membrane"], d["btn_collar"], d["cap"], d["pin"] = build_button(p)
    d["cell"], d["cell_plus"], d["strip_plus"], d["strip_minus"], d["insulator"] = build_cell(p)
    d["magnet"] = build_magnet(p)
    d["split_ring"] = build_split_ring(p)
    d["label"] = build_label(p)
    return d


# --------------------------------------------------------------------------------------------- checks
def checks(p, d):
    out = {"name": p.name, "size": p.size, "length_mm": round(p.L, 2), "body_od": p.body_od, "head_od": p.head_od}
    vol = {k: solid(v).Volume() for k, v in d.items() if v is not None}
    rho = {"body": 2.70, "ring": 2.70, "insert": 2.70, "cap": 7.93, "btn_collar": 7.93, "sled": 1.41, "pin": 1.19,
           "optic_holder": 1.20, "optic_lens": 1.19, "mcpcb": 8.96, "magnet": 7.5, "uv_rod": 2.2, "red_rod": 1.19,
           }
    mass = {k: round(vol[k] * rho[k] / 1000, 2) for k in rho if k in vol}
    out["mass_g"] = mass
    out["aluminium_g"] = round(sum(mass[k] for k in ("body", "ring", "insert")), 2)
    # thermal split for the simulator: head = bezel + insert + body in front of the step; body = the tube
    front = box(-5, p.x_step, -30, 30, -30, 30).val()
    body_head = solid(d["body"]).intersect(front).Volume() * 2.70 / 1000
    out["thermal_g"] = {"head_aluminium": round(mass["ring"] + mass["insert"] + body_head, 2),
                        "body_aluminium": round(mass["body"] - body_head, 2), "led_board_copper": mass["mcpcb"],
                        "tube_section_mm2": round(math.pi * (p.R ** 2 - p.rb ** 2) - 6 * 0.0, 1),
                        "tube_length_mm": round(p.L - p.x_step, 1)}
    rb, rbd = p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    out["walls_mm"] = {
        "tube over the cell": round(p.R - rb, 2),
        "flats over the cell": round(p.flat_r - rb, 2),
        "head section over the bore": round(p.RH - rb, 2),
        "under the button counterbore": round(p.z_cb_floor - rb, 2),
        "thread root over the bore": round(d3 - rb, 2),
        "run-out over the bore": round(d3 - 0.05 - rb, 2),
        "bezel over the insert": round(p.ring_wall - 0.05, 2),
        "bezel at its fins (over the insert)": round(p.ring_wall - 0.05 - p.fin_d, 2),
        "bezel over the thread (minor diameter)": round(p.RH - (rbd - 0.5413 * p.pitch), 2),
    }
    out["walls_mm"].update(tail_clearances(p))
    out["fits_mm"] = {
        "board width": round(p.board_w, 2),
        "board length": round(p.board_x1 - p.board_x0, 2),
        "board corner to bore": round(rb - math.hypot(p.board_w / 2, max(abs(p.z_board_top), abs(p.z_board_bot))), 2),
        "socket mouth below the head crest": p.mouth_recess,
        "socket wall (hole length at its edge)": round(
            math.sqrt(p.RH ** 2 - (p.usb_seal[1] / 2) ** 2) - math.sqrt(rb ** 2 - (p.usb_seal[1] / 2) ** 2), 2),
        "button pin length": round(p.z_cb_floor - 0.15 - p.z_sw_top - 0.05, 2),
        "UV rod length": round(p.RH - (p.z_board_top + 0.1 + p.uv_led[2]), 2),
        "cell radial room": round(rb - p.cell_d / 2, 2),
        "thread engagement": round(p.thread_len - 0.7, 2),
        "keyring hole (along x across)": "%.1f x %.1f" % (p.hole_w, p.hole_l),
    }
    out["stack_x_mm"] = {k: round(v, 2) for k, v in dict(
        optic=p.x_opt0, led_board=p.x_opt1, band_front=p.x_bf, bezel_rear=p.x_r1, head_section=p.x_hs0,
        windows=p.x_win, button_and_port=p.x_btn, step=p.x_step, board0=p.board_x0, board1=p.board_x1,
        cell0=p.x_cell0, cell1=p.x_cell1, L=p.L).items()}
    out["outer_area_mm2"] = round(math.pi * p.body_od * (p.L - p.x_step) + math.pi * p.head_od * p.x_step
                                  + math.pi / 4 * p.body_od ** 2 + math.pi / 4 * (p.head_od ** 2 - p.lip_id ** 2), 0)
    pairs = [("body", "insert"), ("body", "ring"), ("ring", "insert"), ("body", "sled"), ("body", "cell"),
             ("sled", "board"), ("body", "board"), ("insert", "optic_holder"), ("insert", "mcpcb"), ("body", "pin"),
             ("body", "btn_collar"), ("sled", "pin"), ("sled", "cell"), ("body", "strip_minus"),
             ("cell", "strip_minus"), ("body", "usb_body"), ("sled", "usb_body"), ("body", "usb_shell"),
             ("body", "usb_seal"), ("insert", "sled"), ("ring", "optic_lens"), ("ring", "gasket"),
             ("body", "face_oring"), ("body", "uv_rod"), ("body", "red_rod"), ("sled", "uv_rod"),
             ("sled", "red_rod"), ("bp_uv_led", "uv_rod"), ("bp_red_led", "red_rod"), ("body", "magnet"),
             ("cell", "insulator"), ("board", "usb_body"), ("bp_sw_body", "pin"), ("body", "split_ring"),
             ("magnet", "split_ring")]
    pairs = [(a, b) for (a, b) in pairs if d.get(a) is not None and d.get(b) is not None]
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
    sizes = ["14", "16"]
    if "--size" in sys.argv:
        v = sys.argv[sys.argv.index("--size") + 1]
        sizes = ["14", "16"] if v == "both" else [v]
    os.makedirs(out_dir, exist_ok=True)
    allinfo = {}
    for sz, mag in [(sz, mag) for sz in sizes for mag in (False, True)]:
        p = P(size=sz, magnet=mag)
        d = build_all(p)
        nm = p.name.replace(" ", "_")
        parts = [(build_body(p, cosmetic=False), "body")]
        if not mag:                                     # bezel and head insert are the same for both versions
            parts += [(build_ring(p, cosmetic=False), "bezel"), (d["insert"], "insert")]
        for shape, part in parts:
            cq.exporters.export(shape, os.path.join(out_dir, "%s_%s.step" % (nm, part)))
        asm = cq.Assembly(name=nm + "_v0.1")
        for k, v in d.items():
            if v is not None and k not in ("split_ring",):
                asm.add(v, name=k)
        asm.save(os.path.join(out_dir, "%s_v0.1_assembly.step" % nm))
        info = {"params": asdict(p)}
        info.update(checks(p, d))
        allinfo[p.name] = info
        print(json.dumps({k: info[k] for k in ("name", "length_mm", "aluminium_g", "walls_mm", "fits_mm",
                                               "interference_mm3", "stack_x_mm", "outer_area_mm2")}, indent=1))
    with open(os.path.join(out_dir, "edco_mini_interface.json"), "w") as f:
        json.dump(allinfo, f, indent=1)


if __name__ == "__main__":
    main()
