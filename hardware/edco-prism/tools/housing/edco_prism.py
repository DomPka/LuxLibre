#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""EDCO Prism v0.1 housing and cartridge, CadQuery (LuxLibre reference design #4).

A sealed 18350 light of about 80 mm whose beam is white (turbo) or any colour: four LEDs behind one 24 mm quad TIR
optic (Carclo 10623 frosted medium; 10621 clear spot as the narrow option): a white Luminus SST-20-W and red (Luminus
SST-10-R), green (ams OSRAM OSCONIQ P 3030 GT) and blue (Luminus SST-20-B) LEDs, one in each cavity. A waterproof
USB-C socket in the side of the head (charging and the settings page), a stainless button with an RGB-lit membrane,
four cooling fins round the head, and the EDCO Mini's tail tab with a long keyring hole (M version: two magnets in
the tab's end).

The same sealed build as EDCO Mini: a crenellated bezel clamps the LED holder (insert) metal on metal and presses the
optic onto its gasket; the cartridge (insert, main board in a POM sled, the cell) slides in from the front and the
bezel is locked for good.

Front to tail:
    bezel ring  - crenellated, three fins, screws onto the band's external thread (M26 x 0.75), clamps the insert
    insert      - LED holder: a cup for the quad optic, the 24 mm copper LED board on a shelf, a face O-ring on its
                  rear face against the band's front face, a key that stops it turning while the bezel is tightened
    body        - the band (thread), the head section (as large as the bezel, four fins) with the USB-C hole and
                  a pocket for the plug (-Z) and the button (+Z); the tube with six flats, the label, three tail grooves, and the tail tab (two bevels,
                  two flats) with a long keyring hole through it (M version: two magnets in the tab's end face)
    cartridge   - insert, main board in a POM sled (waterproof USB-C socket on its underside, looking down through
                  the hole, axial; the switch and the halo RGB LED on its top side under the button pin), the cell

Frame: X along the light, X = 0 at the front of the bezel's crenellations, X = L at the tail face; button on +Z; port
on -Z (under the button). Units mm.

Two versions: without a magnet, and M (EDCO PrismM) with two magnets in the tail tab's end.

usage:  python3 edco_prism.py <out_dir>
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

# The four LEDs on the quad board, (kind, y, z) of each centre. Kinds: "white", "red", "green", "blue".
LEDS = (("white", 1, 1), ("red", -1, 1), ("green", -1, -1), ("blue", 1, -1))


@dataclass
class P:
    name: str = "EDCO Prism"
    magnet: bool = False         # the M version: two NdFeB discs flush in the end face of the tail tab
    body_od: float = 22.0
    head_od: float = 28.0        # = bezel = head section
    bore_d: float = 19.2         # cell bay: Keeppower UH1835P is 18.3 (one listing 18.6) x 35.0, + the - strip
    band_d: float = 26.0         # thread major diameter (M26 x 0.75)
    cell_d: float = 18.6         # the largest diameter the bay takes
    cell_len: float = 35.3       # the longest cell the bay takes (UH1835P2 datasheet: 35.2)
    cell_name: str = "18350"
    opt_d: float = 24.0          # Carclo 24 mm quad (10623 / 10621)
    opt_h: float = 11.5          #   its height is not published: to be measured on a sample
    quad_q: float = 4.4          # LED centres at (+-q, +-q) from the axis (the 24 mm QuadPod layout, to be checked)
    mcpcb_d: float = 24.0        # 24 mm round quad copper DTP board, four separate channels
    mcpcb_t: float = 1.6
    led_w: float = 3.45          # LED package (square, 3535 class)
    flat_r: float = 10.65        # six flats along the tube, at this distance from the axis
    cap_d: float = 7.0           # stainless button cap (larger than the Mini's)
    btn_cb_d: float = 8.8        # counterbore for the membrane + collar
    mag_d: float = 5.0           # supermagnete S-05-02-N52N
    mag_t: float = 2.0
    mag_y: float = 3.7           # magnet centres at (+-mag_y, 0) on the tab's end face
    lug_t: float = 11.0          # tail tab: thickness between its two flats (Z)
    hole_l: float = 11.0         # keyring hole through the tab (Z): long side across (Y)
    hole_w: float = 3.4          #   and short side along the light (X)
    tab_rc: float = 4.0          # the tab's end corners, rounded in the top view
    pitch: float = 0.75          # M22 x 0.75
    fin_n: int = 3
    fin_d: float = 0.35
    fin_w: float = 0.8
    fin_pitch: float = 1.7
    cren_n: int = 6
    cren_w: float = 3.4
    cren_d: float = 1.0
    lip_t: float = 0.6
    gasket_t: float = 0.4
    opt_in_ring: float = 1.4
    shelf_t: float = 1.2
    thread_len: float = 3.5
    spigot_len: float = 1.0
    face_or_cs: float = 0.6
    head_gap: float = 0.15
    mouth_recess: float = 1.9    # socket mouth below the head crest: the plug's overmould sits in a pocket
    plug_pocket: tuple = (12.8, 7.0)   # the pocket in the head round the socket (a USB-C plug's overmould)
    usb_h: float = 7.45          # waterproof vertical USB-C, board to mouth (SHOU HAN 16PFS LTH7.45, C3020055)
    usb_shell: tuple = (8.94, 3.26)
    usb_seal: tuple = (9.5, 3.8)
    usb_body: tuple = (9.6, 4.6)
    usb_seal_h: float = 1.0
    sw_h: float = 2.0
    sw_body: tuple = (2.9, 3.9, 1.5)
    board_t: float = 0.8
    strip_t: float = 0.15
    insul_t: float = 0.15
    tail_wall: float = 1.2
    end_bar: float = 3.0
    ramp_deg: float = 55.0
    end_chamfer: float = 1.0
    head_fins: int = 4           # cooling fins round the head section, between the bezel and the button
    hfin_w: float = 0.75
    hfin_d: float = 0.6
    hfin_pitch: float = 1.5
    tail_grooves: int = 3
    groove_w: float = 0.7
    groove_d: float = 0.4
    label_text: str = "EDCO"
    label_size: float = 2.2

    def __post_init__(self):
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
    def ring_bore(self): return self.band_d
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
    def x_bf(self): return self.x_mc1 + self.shelf_t
    @property
    def x_r1(self): return self.x_bf + self.thread_len
    @property
    def x_hs0(self): return self.x_r1 + self.head_gap
    @property
    def board_x0(self): return self.x_bf + self.spigot_len + 0.3
    @property
    def pocket_r(self): return self.btn_cb_d / 2 + 0.9
    @property
    def x_hfins(self): return [self.x_hs0 + 1.0 + self.hfin_w / 2 + i * self.hfin_pitch for i in range(self.head_fins)]
    @property
    def x_btn(self):
        fins_end = self.x_hs0 + 1.0 + self.head_fins * self.hfin_pitch
        a = fins_end + 0.2 + self.pocket_r                               # the button pocket behind the fins
        b = self.board_x0 + 0.4 + 5.0 + 0.3 + self.usb_body[0] / 2      # the MCU fits in front of the socket
        c = fins_end + 0.4 + self.plug_pocket[0] / 2                     # the plug pocket behind the fins
        return max(a, b, c)
    @property
    def board_x1(self): return self.x_btn + self.usb_body[0] / 2 + 0.4
    @property
    def x_step(self): return max(self.board_x1, self.x_btn + self.pocket_r + 0.6) + 0.3
    @property
    def x_cell0(self): return self.board_x1 + 0.75
    @property
    def x_cell1(self): return self.x_cell0 + self.cell_len
    @property
    def x_bay1(self): return self.x_cell1 + self.strip_t + self.insul_t + 0.1
    @property
    def x_hole(self): return self.x_bay1 + self.tail_wall + self.hole_w / 2
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
    def z_pocket(self): return self.RH - 0.5
    @property
    def z_cb_floor(self): return self.z_pocket - 0.6
    @property
    def z_usb_in(self):
        return -math.sqrt(self.rb ** 2 - (self.usb_body[1] / 2) ** 2) + 0.15
    @property
    def board_w(self):
        z = max(abs(self.z_board_bot), abs(self.z_board_top))
        return 2 * (math.sqrt(self.rb ** 2 - z ** 2) - 0.35)


# --------------------------------------------------------------------------------------------- helpers
def revolve_x(pts):
    q = []
    for pt in pts:
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


def stadium_ax(xc, lx, wy, z0, z1):
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


def led_centres(p):
    return [(kind, sy * p.quad_q, sz * p.quad_q) for (kind, sy, sz) in LEDS]


# --------------------------------------------------------------------------------------------- parts
def build_body(p, cosmetic=True):
    R, RH, L, rb, rbd = p.R, p.RH, p.L, p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    x0 = p.x_bf
    xt1 = p.x_bf + p.thread_len - 0.6
    pts = [(x0, 0.0), (x0, rbd - 0.2), (x0 + 0.2, rbd)]
    if cosmetic:
        pts += thread_zigzag(x0 + 0.5, xt1, rbd, d3, p.pitch)[1:]
    else:
        pts += [(xt1, rbd)]
    xs = p.x_step
    pts += [(xt1, d3 - 0.05), (p.x_hs0, d3 - 0.05), (p.x_hs0, RH - 0.3), (p.x_hs0 + 0.3, RH), (xs, RH),
            (xs + 0.8, R), (L - 0.5, R), (L, R - 0.5), (L, 0.0)]
    body = revolve_x(pts)
    body = body.cut(revolve_x([(x0 - 0.1, 0.0), (x0 - 0.1, rb + 0.2), (x0 + 0.2, rb), (p.x_bay1, rb),
                               (p.x_bay1, 0.0)]))
    body = body.cut(box(x0 - 0.1, x0 + p.spigot_len + 0.1, rb - 0.2, rb + 0.6, -0.5, 0.5))
    body = body.cut(stadium_ax(p.x_btn, p.usb_seal[0] + 0.1, p.usb_seal[1] + 0.1, -RH - 2, 0.0))
    body = body.cut(stadium_ax(p.x_btn, p.plug_pocket[0], p.plug_pocket[1], -RH - 2, p.z_mouth).edges(">Z").fillet(0.5))
    xf0, xf1 = p.x_step + 1.2, p.x_flats_end
    for k in range(6):
        cutter = box(xf0, xf1, -20, 20, p.flat_r, p.flat_r + 6)
        body = body.cut(rot_x(cutter, 60 * k))
    pocket = cyl_z(2 * p.pocket_r, p.z_pocket, RH + 2, x=p.x_btn).edges("<Z").fillet(0.4)
    body = body.cut(pocket)
    body = body.cut(cyl_z(p.btn_cb_d, p.z_cb_floor, RH + 2, x=p.x_btn))
    body = body.cut(cyl_z(2.6, 0.0, p.z_cb_floor + 0.01, x=p.x_btn))
    for xg in p.x_hfins:                              # cooling fins round the head section
        body = body.cut(revolve_x([(xg - p.hfin_w / 2, RH - p.hfin_d), (xg + p.hfin_w / 2, RH - p.hfin_d),
                                   (xg + p.hfin_w / 2, RH + 1), (xg - p.hfin_w / 2, RH + 1)]))
    for xg in p.x_grooves:
        body = body.cut(revolve_x([(xg - p.groove_w / 2, R - p.groove_d), (xg + p.groove_w / 2, R - p.groove_d),
                                   (xg + p.groove_w / 2, R + 1), (xg - p.groove_w / 2, R + 1)]))
    for s in (1, -1):
        body = body.cut(tab_cutter(p, s))
    body = body.cut(cq.Workplane("XY").workplane(offset=-p.R - 1).center(p.x_hole, 0)
                    .slot2D(p.hole_l, p.hole_w, 90).extrude(2 * p.R + 2))
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
    t = math.tan(math.radians(p.ramp_deg))
    x0 = p.x_bay1
    top = p.R + 2.0
    pts = [(x0 - (top - p.R) / t, top), (x0 + p.ramp_len, p.lug_t / 2), (p.L + 1, p.lug_t / 2), (p.L + 1, top)]
    pts = [(x, s * z) for (x, z) in pts]
    return cq.Workplane("XZ").polyline(pts).close().extrude(p.R + 2, both=True)


def tail_clearances(p):
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
    D1 = rbd - 0.5413 * p.pitch
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
    for k in range(p.cren_n):
        a = 360.0 / p.cren_n * k + 30.0
        n = box(-0.1, p.cren_d, -p.cren_w / 2, p.cren_w / 2, rl + 0.5, RH + 1).edges("|X").fillet(0.35)
        ring = ring.cut(rot_x(n, a))
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
    g0, gw = p.rb + 0.15, p.face_or_cs + 0.1
    ins = ins.cut(revolve_x([(p.x_bf - 0.45, g0), (p.x_bf - 0.45, g0 + gw), (p.x_bf + 0.01, g0 + gw),
                             (p.x_bf + 0.01, g0)]))
    ins = ins.union(box(p.x_bf, p.x_bf + p.spigot_len - 0.1, rb - 0.3, p.rb + 0.45, -0.4, 0.4))
    # wire holes through the shelf and the LED board for the five LED wires (white + and -, red, green and blue -;
    # the colour LEDs' + is common): three holes at -Z, inside the bore, between the LEDs
    r = p.rb - 1.0
    for a in (-30.0, 0.0, 30.0):
        y, z = r * math.sin(math.radians(a)), -r * math.cos(math.radians(a))
        ins = ins.cut(cyl_x(1.1, p.x_opt1 - 0.5, p.x_bf + p.spigot_len + 0.1, y, z))
    return ins


def build_face_oring(p):
    g0 = p.rb + 0.15
    cs = p.face_or_cs
    return torus_x(p.x_bf - 0.45 + cs * 0.4 - 0.05, g0 + 0.05 + cs / 2, cs * 0.4)


def build_optic(p):
    """quad TIR optic stand-in: a clear disc with four TIR cones, one over each LED, in a black holder ring"""
    x0, x1 = p.x_opt0, p.x_opt1
    r = p.opt_d / 2
    q = p.quad_q
    lens = cyl_x(2 * (r - 0.25), x0 + 0.05, x0 + 1.2)
    cone_r0 = q * 1.38                                     # each cone's front radius (they meet at the axis)
    for (_, y, z) in led_centres(p):
        cone = cq.Workplane("YZ").workplane(offset=x0 + 1.2).center(y, z).circle(cone_r0).workplane(
            offset=x1 - 1.0 - (x0 + 1.2)).circle(1.6).loft()
        lens = lens.union(cone)
        lens = lens.cut(cyl_x(3.0, x1 - 2.6, x1, y, z))    # the LED's cavity
    lens = lens.intersect(cyl_x(2 * (r - 0.25), x0, x1))
    holder = cyl_x(2 * r, x0 + 1.2, x1).cut(cyl_x(2 * r - 1.0, x0, x1 + 1))
    holder = holder.union(cyl_x(2 * r, x1 - 0.8, x1).cut(cyl_x(2 * r - 1.6, x0, x1 + 1)))
    return holder, lens


def build_gasket(p):
    return revolve_x([(p.x_lip1, p.lip_id / 2 + 0.1), (p.x_lip1, p.opt_d / 2), (p.x_opt0, p.opt_d / 2),
                      (p.x_opt0, p.lip_id / 2 + 0.1)])


def build_led(p):
    """the 20 mm copper LED board and the four LEDs: packages and domes (white phosphor, red, green, blue)"""
    x0, x1 = p.x_opt1, p.x_mc1
    mc = cyl_x(p.mcpcb_d, x0, x1)
    w = p.led_w / 2
    pkg, domes = None, {}
    for (kind, y, z) in led_centres(p):
        b = box(x0 - 0.6, x0, y - w, y + w, z - w, z + w)
        pkg = b if pkg is None else pkg.union(b)
        dome = (cq.Workplane("YZ").workplane(offset=x0 - 0.6).center(y, z).sphere(w * 0.82)
                .intersect(box(x0 - 2.5, x0 - 0.59, y - 3, y + 3, z - 3, z + 3)))
        domes[kind] = dome if kind not in domes else domes[kind].union(dome)
    return mc, pkg, domes


def build_usb(p):
    xc = p.x_btn
    sx, sy = p.usb_shell
    zm = p.z_mouth
    z_ring0 = -math.sqrt(p.RH ** 2 - (p.usb_seal[1] / 2) ** 2) + 0.35
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
    return s


def build_board(p):
    """main board across the bore: socket, MCU and the white-channel buck below; switch, halo LED, the colour DAC,
    op-amp and the three colour sinks on top"""
    x0, x1 = p.board_x0, p.board_x1
    zt, zb = p.z_board_top, p.z_board_bot
    w = p.board_w / 2
    brd = box(x0, x1, -w, w, zb, zt).edges("|Z").chamfer(0.6)
    parts = {}
    sx, sy, sh = p.sw_body
    parts["sw_body"] = box(p.x_btn - sx / 2, p.x_btn + sx / 2, -sy / 2, sy / 2, zt + 0.05, zt + 0.05 + sh)
    parts["sw_act"] = cyl_z(1.4, zt + 0.05 + sh, zt + 0.05 + p.sw_h, x=p.x_btn)
    parts["halo_led"] = box(p.x_btn - 0.5, p.x_btn + 0.5, 2.5, 3.5, zt + 0.05, zt + 0.40)
    # bottom: MCU in front of the socket, the buck and its inductor beside the socket body
    xa = p.board_x0 + 0.4
    parts["b_mcu"] = box(xa, xa + 5.0, -2.5, 2.5, zb - 0.05 - 0.85, zb - 0.05)
    by = p.usb_body[1] / 2 + 0.4
    parts["b_buck"] = box(p.x_btn - 1.5, p.x_btn + 1.5, -by - 3.0, -by, zb - 0.05 - 0.8, zb - 0.05)
    parts["b_prot"] = box(p.x_btn - 1.5, p.x_btn + 1.5, by, by + 3.0, zb - 0.05 - 0.8, zb - 0.05)
    # top: DAC (MSOP-10), op-amp and three sink FETs with their sense resistors, beside the switch
    ys = sy / 2 + 0.6
    parts["t_dac"] = box(x0 + 0.8, x0 + 3.8, ys, ys + 4.9, zt + 0.05, zt + 1.15)
    parts["t_opamp"] = box(x0 + 0.8, x0 + 3.0, -ys - 2.2, -ys, zt + 0.05, zt + 0.80)
    # the white channel's buck inductor (4 x 4 x 2) on top, behind the sink FETs
    parts["t_ind"] = box(x1 - 4.3, x1 - 0.3, -ys - 3.9, -ys + 0.1, zt + 0.05, zt + 2.05)
    fets = None
    for i in range(3):
        xf = x0 + 4.3 + i * 2.5
        f = box(xf, xf + 2.0, -ys - 2.6, -ys - 0.6, zt + 0.05, zt + 0.80)
        fets = f if fets is None else fets.union(f)
    parts["t_fets"] = fets
    tp = None
    for (x, y) in [(x0 + 0.9, -0.2), (p.x_btn - 2.6, 2.4), (p.x_btn + 2.6, -2.4), (x1 - 1.2, -3.0),
                   (x1 - 1.2, 3.0), (x1 - 2.4, 0.0)]:
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
    collar = (cyl_z(cb - 0.02, zc, zc + 0.9, x=x)
              .cut(cyl_z(p.cap_d + 0.35, zc - 0.1, zc + 0.65, x=x))
              .cut(cyl_z(p.cap_d + 0.1, zc - 0.1, zc + 1.2, x=x)))
    collar = collar.faces(">Z").edges().chamfer(0.1)
    cap = cyl_z(p.cap_d + 0.3, zc, zc + 0.3, x=x).union(cyl_z(p.cap_d - 0.1, zc + 0.3, zc + 1.15, x=x))
    cap = cap.faces(">Z").edges().fillet(0.35)
    for rr in (1.1, 2.1):
        ring = cyl_z(2 * rr + 0.25, zc + 1.0, zc + 1.3, x=x).cut(cyl_z(2 * rr - 0.25, zc + 0.9, zc + 1.4, x=x))
        cap = cap.cut(ring)
    pin = cyl_z(2.4, p.z_sw_top + 0.05, zf - 0.15, x=x)
    return memb, collar, cap, pin


def build_cell(p):
    x0, x1 = p.x_cell0, p.x_cell1 - 0.3              # drawn at 18.3 x 35.0 (UH1835P) in the 18.6 x 35.3 bay
    rc = 18.3 / 2
    can = revolve_x([(x0, 0.0), (x0, rc - 0.5), (x0 + 0.5, rc), (x1 - 0.5, rc), (x1, rc - 0.5), (x1, 0.0)])
    plus = cyl_x(5.0, x0 - 0.05, x0 + 0.1)
    st = p.strip_t
    s_plus = box(x0 - st - 0.02, x0 - 0.02, -1.8, 1.8, -3.0, 3.5)
    zc = -(rc + 0.03)
    s_minus = (box(x1 + 0.02, x1 + 0.02 + st, -1.8, 1.8, zc - st + 0.5, 0.0)
               .union(box(p.board_x1 - 1.5, x1 + 0.02 + st, -1.5, 1.5, zc - st, zc)))
    insul = cyl_x(18.3 - 0.4, x1 + 0.02 + st, x1 + 0.02 + st + p.insul_t)
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
    """a split ring (two turns) through the tab's keyring hole and round the tab's end, in the XZ plane"""
    r = 8.0
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
    mc, pkg, domes = build_led(p)
    d["mcpcb"], d["led"] = mc, pkg
    for kind, dome in domes.items():
        d["dome_" + kind] = dome
    d["usb_shell"], d["usb_tongue"], d["usb_seal"], d["usb_body"] = build_usb(p)
    d["sled"] = build_sled(p)
    brd, parts = build_board(p)
    d["board"] = brd
    for k, v in parts.items():
        d["bp_" + k] = v
    d["membrane"], d["btn_collar"], d["cap"], d["pin"] = build_button(p)
    d["cell"], d["cell_plus"], d["strip_plus"], d["strip_minus"], d["insulator"] = build_cell(p)
    d["magnet"] = build_magnet(p)
    d["split_ring"] = build_split_ring(p)
    d["label"] = build_label(p)
    return d


# --------------------------------------------------------------------------------------------- checks
def checks(p, d):
    out = {"name": p.name, "length_mm": round(p.L, 2), "body_od": p.body_od, "head_od": p.head_od}
    vol = {k: solid(v).Volume() for k, v in d.items() if v is not None}
    rho = {"body": 2.70, "ring": 2.70, "insert": 2.70, "cap": 7.93, "btn_collar": 7.93, "sled": 1.41, "pin": 1.19,
           "optic_holder": 1.20, "optic_lens": 1.19, "mcpcb": 8.96, "magnet": 7.5}
    mass = {k: round(vol[k] * rho[k] / 1000, 2) for k in rho if k in vol}
    out["mass_g"] = mass
    out["aluminium_g"] = round(sum(mass[k] for k in ("body", "ring", "insert")), 2)
    front = box(-5, p.x_step, -30, 30, -30, 30).val()
    body_head = solid(d["body"]).intersect(front).Volume() * 2.70 / 1000
    out["thermal_g"] = {"head_aluminium": round(mass["ring"] + mass["insert"] + body_head, 2),
                        "body_aluminium": round(mass["body"] - body_head, 2), "led_board_copper": mass["mcpcb"],
                        "tube_section_mm2": round(math.pi * (p.R ** 2 - p.rb ** 2), 1),
                        "tube_length_mm": round(p.L - p.x_step, 1)}
    rb, rbd = p.rb, p.rband
    d3 = rbd - 0.6134 * p.pitch
    out["walls_mm"] = {
        "tube over the cell": round(p.R - rb, 2),
        "flats over the cell": round(p.flat_r - rb, 2),
        "head section over the bore": round(p.RH - rb, 2),
        "head section under its fins": round(p.RH - p.hfin_d - rb, 2),
        "under the button counterbore": round(p.z_cb_floor - rb, 2),
        "thread root over the bore": round(d3 - rb, 2),
        "run-out over the bore": round(d3 - 0.05 - rb, 2),
        "bezel over the insert": round(p.ring_wall - 0.05, 2),
        "bezel at its fins (over the insert)": round(p.ring_wall - 0.05 - p.fin_d, 2),
        "bezel over the thread (minor diameter)": round(p.RH - (rbd - 0.5413 * p.pitch), 2),
        "insert cup round the optic": round(p.ring_bore / 2 - 0.05 - (p.opt_d / 2 + 0.05), 2),
    }
    out["walls_mm"].update(tail_clearances(p))
    out["fits_mm"] = {
        "board width": round(p.board_w, 2),
        "board length": round(p.board_x1 - p.board_x0, 2),
        "board corner to bore": round(rb - math.hypot(p.board_w / 2, max(abs(p.z_board_top), abs(p.z_board_bot))), 2),
        "socket mouth below the head crest": p.mouth_recess,
        "socket hole wall under the plug pocket (at its edge)": round(
            abs(p.z_mouth) - math.sqrt(rb ** 2 - (p.usb_seal[1] / 2) ** 2), 2),
        "button pin length": round(p.z_cb_floor - 0.15 - p.z_sw_top - 0.05, 2),
        "cell radial room (18.3 mm cell)": round(rb - 18.3 / 2, 2),
        "cell bay": "%.1f x %.1f" % (p.cell_d, p.cell_len),
        "thread engagement": round(p.thread_len - 0.8, 2),
        "keyring hole (along x across)": "%.1f x %.1f" % (p.hole_w, p.hole_l),
    }
    out["stack_x_mm"] = {k: round(v, 2) for k, v in dict(
        optic=p.x_opt0, led_board=p.x_opt1, band_front=p.x_bf, bezel_rear=p.x_r1, head_section=p.x_hs0,
        button_and_port=p.x_btn, step=p.x_step, board0=p.board_x0, board1=p.board_x1,
        cell0=p.x_cell0, cell1=p.x_cell1, L=p.L).items()}
    out["outer_area_mm2"] = round(math.pi * p.body_od * (p.L - p.x_step) + math.pi * p.head_od * p.x_step
                                  + math.pi / 4 * p.body_od ** 2 + math.pi / 4 * (p.head_od ** 2 - p.lip_id ** 2)
                                  + p.head_fins * 2 * math.pi * (p.RH - p.hfin_d / 2) * p.hfin_d, 0)
    pairs = [("body", "insert"), ("body", "ring"), ("ring", "insert"), ("body", "sled"), ("body", "cell"),
             ("sled", "board"), ("body", "board"), ("insert", "optic_holder"), ("insert", "optic_lens"),
             ("insert", "mcpcb"), ("optic_lens", "led"), ("optic_holder", "led"), ("body", "pin"),
             ("body", "btn_collar"), ("sled", "pin"), ("sled", "cell"), ("body", "strip_minus"),
             ("cell", "strip_minus"), ("body", "usb_body"), ("sled", "usb_body"), ("body", "usb_shell"),
             ("body", "usb_seal"), ("insert", "sled"), ("ring", "optic_lens"), ("ring", "optic_holder"),
             ("ring", "gasket"), ("body", "face_oring"), ("body", "magnet"), ("cell", "insulator"),
             ("board", "usb_body"), ("bp_sw_body", "pin"), ("sled", "bp_t_dac"), ("sled", "bp_t_fets"),
             ("sled", "bp_t_ind"), ("bp_t_fets", "bp_t_ind"), ("bp_sw_body", "bp_t_ind"), ("usb_body", "bp_b_buck"),
             ("usb_body", "bp_b_prot"), ("sled", "bp_b_prot"), ("sled", "bp_b_buck"), ("sled", "bp_t_opamp"),
             ("body", "split_ring"), ("magnet", "split_ring")]
    for kind in ("white", "red", "green", "blue", "rgb"):
        if d.get("dome_" + kind) is not None:
            pairs.append(("optic_lens", "dome_" + kind))
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
    os.makedirs(out_dir, exist_ok=True)
    allinfo = {}
    for mag in (False, True):
        p = P(magnet=mag)
        d = build_all(p)
        nm = p.name.replace(" ", "_")
        parts = [(build_body(p, cosmetic=False), "body")]
        if not mag:
            parts += [(build_ring(p, cosmetic=False), "bezel"), (d["insert"], "insert")]
        for shape, part in parts:
            cq.exporters.export(shape, os.path.join(out_dir, "%s_%s.step" % (nm, part)))
        asm = cq.Assembly(name=nm + "_v0.1")
        for k, v in d.items():
            if v is not None and k not in ("split_ring",):
                asm.add(v, name=k)
        asm.save(os.path.join(out_dir, "%s_v0.1_assembly.step" % nm))
        info = {"params": asdict(p), "leds": [list(x) for x in led_centres(p)]}
        info.update(checks(p, d))
        allinfo[p.name] = info
        print(json.dumps({k: info[k] for k in ("name", "length_mm", "aluminium_g", "walls_mm", "fits_mm",
                                               "interference_mm3", "stack_x_mm", "outer_area_mm2")}, indent=1))
    with open(os.path.join(out_dir, "edco_prism_interface.json"), "w") as f:
        json.dump(allinfo, f, indent=1)


if __name__ == "__main__":
    main()
