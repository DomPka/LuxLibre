#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""EDCO v0.1 housing and cartridge, CadQuery (LuxLibre reference design #2).

EDCO is a round, sealed EDC light: a 6061 tube with a closed tail, one 14500 cell, no laser, no radio.
Everything inside is one cartridge that slides in from the front:

    head (LED holder, TIR optic glued in, O-ring) -> POM sled with the main board -> 14500 cell -> tail board
    with a waterproof vertical USB-C socket whose seal ring seals inside the obround hole of the tail wall.

A bezel ring screws onto the external M18 x 0.75 thread of the tube and clamps the head flange; it is
fitted with thread-locker, so the light is closed for good.  The single button is a stainless cap on a
clamped silicone membrane (static seal) in a scalloped pocket near the head; a POM pin carries the press
to a tactile switch on the main board.  A PMMA light pipe below it shows the charge state.

Frame: X along the light, X = 0 at the front face of the bezel ring, X = L at the tail face; button on +Z;
the USB-C socket's long side along Y.  Units mm.

usage:  python3 edco_housing.py <out_dir> [--stl]   writes STEP (machined parts + assembly) and
                                                    edco_interface.json (sizes, masses, checks); --stl also every
                                                    part as STL (the renderer rebuilds the parts itself)
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


@dataclass
class P:
    # ---- envelope
    OD: float = 20.0
    # ---- bezel ring (screws over the tube's external thread, clamps the head flange)
    ring_len: float = 6.0
    ring_lip_t: float = 0.8          # front lip that clamps the head flange
    ring_lip_id: float = 16.6
    ring_chamfer: float = 0.6
    thread_major: float = 18.0       # M18 x 0.75 (6g/6H, DIN 13 fine), about 3 mm engaged, locked
    thread_pitch: float = 0.75
    thread_minor_ext: float = 17.08  # external thread minor d3 = d - 1.2269 P
    thread_minor_int: float = 17.19  # internal thread minor D1 = D - 1.0825 P
    # ---- head (LED holder): front boss through the ring lip, flange under the lip, spigot in the bore
    head_face_x: float = 0.25        # head front face behind the ring's front face
    head_boss_d: float = 16.4
    head_flange_d: float = 17.1     # passes the ring's thread minor (17.19)
    head_flange_x: tuple = (0.8, 2.0)
    head_end_x: float = 11.5         # rear face of the head (wire exits)
    head_lip_d: float = 9.2          # front lip over the optic rim (lens exit d8.6)
    head_lip_t: float = 0.3
    oring_groove_x: tuple = (9.6, 10.9)
    oring_groove_d: float = 13.6     # groove bottom: 0.8 mm gland in the d15.2 bore = 20 % squeeze of a CS 1.0
    oring_cs: float = 1.0
    oring_id: float = 13.0           # 13 x 1 NBR 70: 4.6 % stretch on the groove bottom
    spanner_r: float = 6.6           # two d1.0 spanner holes in the head face (hold the head while the ring turns)
    # ---- optic and LED (as FlashKa v0.7)
    opt_od: float = 10.0             # LEDiL LISA3-RS-PIN (FP16558), pins cut off
    opt_h: float = 6.93
    opt_exit_d: float = 8.6
    opt_bore: float = 10.1
    mcpcb_d: float = 10.0            # 10 mm copper DTP board, SST-20 Gen 2
    mcpcb_t: float = 1.6
    sst: float = 3.45
    sst_h: float = 0.7
    led_wire_r: float = 5.7          # LED wire grooves + holes (24 AWG PTFE)
    led_wire_d: float = 1.4
    # ---- body tube
    body_front_x: float = 2.0        # front face of the tube (head flange seat)
    bore_d: float = 15.2             # cell bay and sled bore (any flat-top 14500 up to 14.4 mm with strips)
    undercut: tuple = (5.4, 6.0, 16.9)   # thread run-out: x0, x1, diameter (0.85 mm wall to the bore)
    shoulder_chamfer: float = 0.3
    tail_chamfer: float = 0.5
    tail_wall: float = 2.4           # end wall that carries the USB-C seal
    tail_cav_d: float = 12.6         # tail board cavity
    usb_hole: tuple = (10.0, 4.4)    # obround hole for the socket's seal housing (Y, Z), see usb_* below
    # ---- button (stainless cap on a clamped silicone membrane) and indicator
    pocket_x: tuple = (16.0, 29.0)   # scalloped pocket (stadium) on +Z
    pocket_w: float = 7.0
    pocket_floor_z: float = 9.2
    btn_x: float = 21.5
    btn_cb_d: float = 6.0            # counterbore for membrane + collar
    btn_cb_floor_z: float = 8.4      # 0.8 mm of wall under it (bore radius 7.6)
    btn_hole_d: float = 2.4          # pin hole through the wall
    ind_x: float = 26.5
    ind_d: float = 1.5               # PMMA light pipe d1.45
    # ---- label flat
    flat_x: tuple = (32.0, 62.0)
    flat_z: float = 9.0              # 1.4 mm wall over the cell
    flat_w: float = 9.6              # stadium width (the sides are the natural chord, 8.7 mm)
    label_text: str = "EDCO"
    label_size: float = 2.3
    # ---- lanyard: one straight d1.6 hole through each tail corner (+Z and -Z), 45 deg
    lan_d: float = 1.6
    lan_entry_r: float = 6.8         # where the hole axis meets the tail face
    lan_exit_dx: float = 3.2         # where it meets the outer surface, from the tail face
    # ---- cartridge
    sled_od: float = 15.0
    sled_id: float = 13.6
    board_x: tuple = (12.0, 34.0)
    board_w: float = 12.0
    board_t: float = 0.8
    board_top_z: float = 4.2         # main board top face (switch side)
    sw_body: tuple = (2.9, 3.9, 1.5)  # Alps SKRK: along X, along Y, body height
    sw_h: float = 2.0                # incl. actuator
    cell_d: float = 14.0             # Vapcell INR14500 F15
    cell_len: float = 49.0
    strip_t: float = 0.15            # nickel strip
    tail_insul_t: float = 0.1
    tail_parts_h: float = 1.0
    tail_board_d: float = 12.2
    tail_board_t: float = 0.8
    usb_h: float = 7.45              # socket height above the tail board (SHOU HAN TYPE-C 16PFS LTH7.45 IPX8, C3020055;
    #                                  "LTH7.45" read as the height - to be measured on a sample)
    usb_recess: float = 0.10         # socket face behind the tail face
    usb_shell: tuple = (8.94, 3.26)
    usb_body: tuple = (10.4, 5.2)

    # ---- derived
    @property
    def R(self):
        return self.OD / 2

    @property
    def cell_x0(self):
        return self.board_x[1] + 0.9

    @property
    def cell_x1(self):
        return self.cell_x0 + self.cell_len

    @property
    def tail_board_x0(self):
        return self.cell_x1 + self.strip_t + self.tail_insul_t + self.tail_parts_h

    @property
    def L(self):
        return self.tail_board_x0 + self.tail_board_t + self.usb_h + self.usb_recess

    @property
    def tail_cav_x0(self):
        return self.tail_board_x0 - 0.3

    @property
    def end_wall_x0(self):
        return self.L - self.tail_wall

    @property
    def mcpcb_x0(self):
        return self.head_face_x + self.head_lip_t + self.opt_h

    @property
    def mcpcb_x1(self):
        return self.mcpcb_x0 + self.mcpcb_t


# --------------------------------------------------------------------------------------------- helpers
def revolve_x(pts):
    """profile [(x, r), ...] revolved about the X axis"""
    return cq.Workplane("XY").polyline(pts).close().revolve(360, (0, 0, 0), (1, 0, 0))


def cyl(d, p0, direction, length):
    v = cq.Vector(*direction).normalized()
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, length, cq.Vector(*p0), v))


def cyl_x(d, x0, x1, y=0.0, z=0.0):
    return cyl(d, (x0, y, z), (1, 0, 0), x1 - x0)


def cyl_z(d, z0, z1, x=0.0, y=0.0):
    return cyl(d, (x, y, z0), (0, 0, 1), z1 - z0)


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def stadium_z(x0, x1, w, z0, z1, fillet=0.0):
    """stadium (long axis X) extruded along Z"""
    s = (cq.Workplane("XY").workplane(offset=z0).center((x0 + x1) / 2, 0)
         .slot2D(x1 - x0, w, 0).extrude(z1 - z0))
    if fillet:
        s = s.edges("<Z").fillet(fillet)
    return s


def obround_x(wy, hz, x0, x1, y=0.0, z=0.0):
    """obround (long axis Y) extruded along X"""
    return (cq.Workplane("YZ").workplane(offset=x0).center(y, z).slot2D(wy, hz, 0).extrude(x1 - x0))


def torus_x(x, r_major, r_minor):
    t = cq.Solid.makeTorus(r_major, r_minor, cq.Vector(x, 0, 0), cq.Vector(1, 0, 0))
    return cq.Workplane("XY").add(t)


def thread_zigzag(x0, x1, r_crest, r_root, pitch, start_crest=True):
    """cosmetic thread: closed V-rings (not a helix) between x0 < x1, as (x, r) points from x0 to x1"""
    pts = []
    n = int((x1 - x0) / pitch + 1e-6)
    for i in range(n + 1):
        x = x0 + i * pitch
        pts.append((x, r_crest if start_crest else r_root))
        if i < n:
            pts.append((x + pitch / 2, r_root if start_crest else r_crest))
    return pts


# --------------------------------------------------------------------------------------------- parts
def build_body(p, cosmetic=True):
    """cosmetic=False: plain thread diameters (the STEP for machining; the drawing calls up M18 x 0.75)"""
    R, L = p.R, p.L
    rt = p.thread_major / 2
    rtm = p.thread_minor_ext / 2
    x0 = p.body_front_x
    ux0, ux1, ud = p.undercut
    # outer profile with a cosmetic thread
    pts = [(x0, 0.0), (x0, rt - 0.3), (x0 + 0.3, rt)]
    if cosmetic:
        pts += thread_zigzag(x0 + 0.5, ux0, rt, rtm, p.thread_pitch)[1:]
    else:
        pts += [(ux0, rt)]
    pts += [(ux0, ud / 2), (ux1, ud / 2), (ux1, R - p.shoulder_chamfer), (ux1 + p.shoulder_chamfer, R),
            (L - p.tail_chamfer, R), (L, R - p.tail_chamfer), (L, 0.0)]
    body = revolve_x(pts)
    # cavities: bore (entry chamfer for the O-ring), tail cavity
    rb = p.bore_d / 2
    inner = revolve_x([(x0 - 0.1, 0.0), (x0 - 0.1, rb + 0.4), (x0 + 0.4, rb), (p.tail_cav_x0, rb),
                       (p.tail_cav_x0 + 0.3, p.tail_cav_d / 2), (p.end_wall_x0, p.tail_cav_d / 2),
                       (p.end_wall_x0, 0.0)])
    body = body.cut(inner)
    # USB-C socket hole through the end wall
    body = body.cut(obround_x(p.usb_hole[0], p.usb_hole[1], p.end_wall_x0 - 0.1, L + 0.1))
    # scalloped button pocket (rounded floor edges), button counterbore + pin hole, indicator hole
    body = body.cut(stadium_z(p.pocket_x[0], p.pocket_x[1], p.pocket_w, p.pocket_floor_z, R + 1, fillet=0.6))
    body = body.cut(cyl_z(p.btn_cb_d, p.btn_cb_floor_z, R + 1, x=p.btn_x))
    body = body.cut(cyl_z(p.btn_hole_d, 5.0, p.btn_cb_floor_z + 0.01, x=p.btn_x))
    body = body.cut(cyl_z(p.ind_d, 5.0, R + 1, x=p.ind_x))
    # label flat
    body = body.cut(stadium_z(p.flat_x[0], p.flat_x[1], p.flat_w, p.flat_z, R + 1))
    # lanyard holes through the two tail corners
    for s in (1, -1):
        body = body.cut(lanyard_hole(p, s))
    return body


def lanyard_hole(p, s, extra=1.5):
    """straight hole at 45 deg through the tail corner on side s (+1: +Z, -1: -Z)"""
    L = p.L
    e = (L, 0.0, s * p.lan_entry_r)
    d = (-1.0, 0.0, s * 1.0)
    n = 1 / math.sqrt(2)
    start = (e[0] - d[0] * n * extra, 0.0, e[2] - d[2] * n * extra)
    return cyl(p.lan_d, start, d, (p.lan_exit_dx + 2 * extra) * math.sqrt(2))


def build_ring(p, cosmetic=True):
    R = p.R
    rt = p.thread_major / 2
    rmi = p.thread_minor_int / 2
    rl = p.ring_lip_id / 2
    c = p.ring_chamfer
    pts = [(0.0, rl + 0.2), (0.0, R - c), (c, R), (p.ring_len - 0.3, R), (p.ring_len, R - 0.3),
           (p.ring_len, rmi)]
    # internal cosmetic thread from the rear face to the lip
    # phase: the ring's roots sit on the tube's crests (x = 2.5, 3.25, ...), so the cosmetic V-rings interleave
    if cosmetic:
        th = thread_zigzag(p.ring_lip_t + 0.575, p.ring_len - 0.3, rmi, rt, p.thread_pitch)
        pts += list(reversed(th))
    else:
        pts += [(p.ring_lip_t + 0.575, rmi)]
    pts += [(p.ring_lip_t, rt), (p.ring_lip_t, rl), (0.2, rl)]
    ring = revolve_x(pts)
    return ring


def build_head(p):
    rb = p.bore_d / 2
    sp = rb - 0.025                       # spigot d15.15 in the d15.2 bore (paste)
    f0, f1 = p.head_flange_x
    g0, g1 = p.oring_groove_x
    xf = p.head_face_x
    pts = [(xf, p.head_lip_d / 2), (xf, p.head_boss_d / 2 - 0.2), (xf + 0.2, p.head_boss_d / 2),
           (f0, p.head_boss_d / 2), (f0, p.head_flange_d / 2), (f1, p.head_flange_d / 2), (f1, sp),
           (g0, sp), (g0, p.oring_groove_d / 2), (g1, p.oring_groove_d / 2), (g1, sp),
           (p.head_end_x - 0.2, sp), (p.head_end_x, sp - 0.2), (p.head_end_x, 0.0),
           (p.mcpcb_x1, 0.0), (p.mcpcb_x1, p.opt_bore / 2), (xf + p.head_lip_t, p.opt_bore / 2),
           (xf + p.head_lip_t, p.head_lip_d / 2)]
    head = revolve_x(pts)
    # LED wire grooves in the bore wall + holes through the shelf (two, at -Z +/- 35 deg)
    for a in (-35.0, 35.0):
        y = p.led_wire_r * math.sin(math.radians(a))
        z = -p.led_wire_r * math.cos(math.radians(a))
        head = head.cut(cyl_x(p.led_wire_d, p.mcpcb_x0 - 1.4, p.head_end_x + 0.1, y, z))
    # spanner holes in the front face
    for y in (-p.spanner_r, p.spanner_r):
        head = head.cut(cyl_x(1.0, xf - 0.1, xf + 1.0, y, 0.0))
    return head


def wire_points(p):
    """LED wire hole centres (y, z)"""
    out = []
    for a in (-35.0, 35.0):
        out.append((p.led_wire_r * math.sin(math.radians(a)), -p.led_wire_r * math.cos(math.radians(a))))
    return out


def build_oring(p):
    g0, g1 = p.oring_groove_x
    rc = p.oring_groove_d / 2 + 0.4
    return torus_x((g0 + g1) / 2, rc, 0.42)


def build_optic(p):
    """LEDiL LISA3-RS-PIN as installed, simplified (same drawing as FlashKa v0.7): (holder, lens)"""
    x0 = p.head_face_x + p.head_lip_t
    h = p.opt_h
    re_ = p.opt_exit_d / 2

    def rev(pts):
        return revolve_x([(x0 + t, r) for t, r in pts])
    lens = rev([(0.15, 0.0), (0.15, re_ - 0.05), (0.75, re_ - 0.05), (2.0, re_ - 0.45), (3.5, 3.55), (5.0, 3.05),
                (h - 0.9, 2.75), (h - 0.9, 2.55), (h - 2.1, 2.55), (h - 2.4, 1.6), (h - 2.55, 0.0)])
    holder = rev([(0.0, re_), (0.0, p.opt_od / 2), (h, p.opt_od / 2), (h, 2.6), (h - 0.9, 2.6), (h - 0.9, 2.8),
                  (5.0, 3.1), (3.5, 3.6), (2.0, re_ - 0.4), (0.75, re_)])
    return holder, lens


def build_led(p):
    x0, x1 = p.mcpcb_x0, p.mcpcb_x1
    mc = cyl_x(p.mcpcb_d, x0, x1)
    pkg = box(x0 - p.sst_h, x0, -p.sst / 2, p.sst / 2, -p.sst / 2, p.sst / 2)
    dome = cyl_x(2.4, x0 - p.sst_h - 0.12, x0 - p.sst_h + 0.01)
    return mc, pkg, dome


def build_sled(p):
    """black POM-C sled: carries the main board in two slots, guides the button pin and the light pipe,
    passes the axial preload from the cell to the head"""
    x0, x1 = p.head_end_x + 0.1, p.cell_x0 - p.strip_t - 0.05
    s = cyl_x(p.sled_od, x0, x1).cut(cyl_x(p.sled_id, x0 - 1, x1 + 1))
    zt, zb = p.board_top_z, p.board_top_z - p.board_t
    # board slots (the board edges sit in the wall)
    s = s.cut(box(p.board_x[0] - 0.05, p.board_x[1] + 0.05, -p.board_w / 2 - 0.05, p.board_w / 2 + 0.05,
                  zb - 0.03, zt + 0.03))
    # pin guide and light-pipe holes
    s = s.cut(cyl_z(p.btn_hole_d, 5.0, 9.0, x=p.btn_x))
    s = s.cut(cyl_z(p.ind_d, 5.0, 9.0, x=p.ind_x))
    # wire windows at both ends (bottom)
    s = s.cut(box(x0 - 1, x0 + 1.8, -3.5, 3.5, -8, -3.0))
    s = s.cut(box(x1 - 1.8, x1 + 1, -3.0, 3.0, -8, -3.0))
    return s


def build_board(p):
    """main board stand-in (4 layers, 0.8 mm): board + the main parts (for pictures, clearance and mass)"""
    x0, x1 = p.board_x
    zt, zb = p.board_top_z, p.board_top_z - p.board_t
    w = p.board_w / 2
    brd = box(x0, x1, -w, w, zb, zt).edges("|Z").chamfer(0.6)
    parts = {}
    # top side: switch, indicator LED, a few passives
    sx, sy, sh = p.sw_body
    parts["sw_body"] = box(p.btn_x - sx / 2, p.btn_x + sx / 2, -sy / 2, sy / 2, zt + 0.05, zt + 0.05 + sh)
    parts["sw_act"] = cyl_z(1.4, zt + 0.05 + sh, zt + 0.05 + p.sw_h, x=p.btn_x)
    parts["ind_led"] = box(p.ind_x - 0.5, p.ind_x + 0.5, -0.5, 0.5, zt + 0.05, zt + 0.40)
    top_pass = [(17.4, 1.6), (17.4, -1.6), (25.0, 2.2), (28.2, -2.0), (30.5, 1.5), (31.8, -1.2), (14.2, 2.4)]
    parts["top_passives"] = None
    tp = None
    for (x, y) in top_pass:
        b = box(x - 0.5, x + 0.5, y - 0.25, y + 0.25, zt + 0.02, zt + 0.37)
        tp = b if tp is None else tp.union(b)
    parts["top_passives"] = tp
    # LED wire pads (front, top) and cell / flex pads (rear)
    pads = None
    for (x, y, wx, wy) in [(13.0, -2.6, 1.6, 1.8), (13.0, 2.6, 1.6, 1.8), (33.0, -3.5, 1.6, 2.4), (33.0, 3.5, 1.6, 2.4),
                           (32.6, 0.0, 1.0, 1.2)]:
        b = box(x - wx / 2, x + wx / 2, y - wy / 2, y + wy / 2, zt, zt + 0.04)
        pads = b if pads is None else pads.union(b)
    parts["pads"] = pads
    # bottom side
    bot = [("mcu", 27.0, 0.0, 5.0, 5.0, 0.85),        # ESP32-C3FH4 QFN-32
           ("xtal", 31.2, 2.6, 1.6, 2.0, 0.55),
           ("buck", 16.3, -3.0, 3.0, 3.0, 0.9),       # TPS62095
           ("ind", 16.8, 2.2, 4.0, 4.0, 2.0),          # 1 uH 4 x 4
           ("sot_chg", 21.6, 3.6, 1.6, 2.9, 1.1),     # TP4057
           ("sot_dw", 21.6, -3.6, 1.6, 2.9, 1.1),     # DW01A
           ("sot_fet", 24.0, -3.6, 1.6, 2.9, 1.1),    # SE8830A
           ("ldo", 24.0, 3.6, 1.6, 2.9, 1.0),         # RT9080
           ("opamp", 19.6, -0.4, 1.25, 2.0, 1.0),     # TLV333 SC70-5
           ("rsense", 13.6, -2.8, 1.25, 2.0, 0.5),
           ("cbulk1", 13.6, 1.0, 1.6, 0.8, 0.8), ("cbulk2", 13.6, 3.0, 1.6, 0.8, 0.8),
           ("cbulk3", 19.8, 2.6, 0.8, 1.6, 0.8), ("cin", 19.6, -3.6, 2.0, 1.25, 1.2)]
    bp = None
    mats = {}
    for (nm, x, y, lx, ly, h) in bot:
        b = box(x - lx / 2, x + lx / 2, y - ly / 2, y + ly / 2, zb - 0.05 - h, zb - 0.05)
        parts["b_" + nm] = b
    for (x, y) in [(29.9, -2.9), (30.6, -1.0), (25.0, 0.8), (25.0, -1.2), (23.0, 0.0), (22.5, 1.8), (29.6, 3.6),
                   (32.6, -3.2), (32.6, 2.8), (18.4, 4.2), (14.8, -4.6)]:
        b = box(x - 0.25, x + 0.25, y - 0.5, y + 0.5, zb - 0.37, zb - 0.02)
        bp = b if bp is None else bp.union(b)
    parts["bot_passives"] = bp
    return brd, parts


def build_button(p):
    """stainless cap, collar and the silicone membrane; POM pin; PMMA light pipe"""
    x = p.btn_x
    zf = p.btn_cb_floor_z
    memb = cyl_z(p.btn_cb_d - 0.05, zf, zf + 0.35, x=x).union(cyl_z(2.2, zf - 0.15, zf, x=x))
    zc = zf + 0.35
    collar = (cyl_z(p.btn_cb_d - 0.02, zc, zc + 0.95, x=x)
              .cut(cyl_z(4.55, zc - 0.1, zc + 0.70, x=x))
              .cut(cyl_z(4.30, zc - 0.1, zc + 1.2, x=x)))
    collar = collar.faces(">Z").edges().chamfer(0.12)
    cap = (cyl_z(5.0, zc, zc + 0.3, x=x).union(cyl_z(4.2, zc + 0.3, zc + 1.25, x=x)))
    cap = cap.faces(">Z").edges().fillet(0.35)
    z_sw = p.board_top_z + 0.05 + p.sw_h
    pin = cyl_z(2.0, z_sw + 0.05, zf - 0.15, x=x).union(cyl_z(1.4, z_sw + 0.02, z_sw + 0.05, x=x))
    lp = cyl_z(p.ind_d - 0.05, p.board_top_z + 0.45, p.pocket_floor_z - 0.02, x=p.ind_x)
    return memb, collar, cap, pin, lp


def build_cell(p):
    x0, x1 = p.cell_x0, p.cell_x1
    rc = p.cell_d / 2
    can = revolve_x([(x0, 0.0), (x0, rc - 0.5), (x0 + 0.5, rc), (x1 - 0.5, rc), (x1, rc - 0.5), (x1, 0.0)])
    plus = cyl_x(5.0, x0 - 0.05, x0 + 0.1)
    # nickel strips: + (front, soldered to the board), - (tail end, along -Z to the board)
    st = p.strip_t
    s_plus = box(x0 - st - 0.02, x0 - 0.02, -2.0, 2.0, -3.0, 3.6)
    zc = -(p.cell_d / 2 + 0.03)
    s_minus = (box(x1 + 0.02, x1 + 0.02 + st, -2.0, 2.0, zc - st + 0.5, 0.0)
               .union(box(p.board_x[1] - 2.0, x1 + 0.02 + st, -2.0, 2.0, zc - st, zc)))
    # 4-wire flex (VBUS, D+, D-, GND) along +Y from the tail board to the main board
    yf = p.cell_d / 2 + 0.05
    xb = p.tail_cav_x0 - 0.45               # the flex turns inwards just before the tail cavity step
    flex = (box(p.board_x[1] - 2.5, xb + 0.12, yf, yf + 0.12, -2.0, 2.0)
            .union(box(xb, xb + 0.12, 4.6, yf + 0.12, -2.0, 2.0))
            .union(box(xb, p.tail_board_x0, 4.6, 4.72, -2.0, 2.0)))
    insul = cyl_x(p.cell_d - 0.4, x1 + 0.02 + st, x1 + 0.02 + st + p.tail_insul_t)
    return can, plus, s_plus, s_minus, flex, insul


def build_tail(p):
    x0 = p.tail_board_x0
    x1 = x0 + p.tail_board_t
    brd = cyl_x(p.tail_board_d, x0, x1)
    parts = None
    for (y, z, ly, lz) in [(0.0, -3.0, 2.9, 1.6), (3.0, 1.5, 1.0, 0.5), (-3.0, 1.5, 1.0, 0.5), (0.0, 3.2, 1.6, 1.0)]:
        b = box(x0 - p.tail_parts_h + 0.05, x0, y - ly / 2, y + ly / 2, z - lz / 2, z + lz / 2)
        parts = b if parts is None else parts.union(b)
    # USB-C socket stand-in: body, flange, seal housing with seal ring, metal shell + tongue
    xf = p.L - p.usb_recess
    bw, bh = p.usb_body
    body = box(x1, p.end_wall_x0 - 0.2, -bw / 2, bw / 2, -bh / 2, bh / 2).edges("|X").fillet(1.2)
    flange = obround_x(11.4, 5.8, p.end_wall_x0 - 0.2, p.end_wall_x0, 0, 0)
    housing = obround_x(p.usb_hole[0] - 0.08, p.usb_hole[1] - 0.08, p.end_wall_x0, xf)
    housing = housing.cut(obround_x(p.usb_shell[0] + 0.3, p.usb_shell[1] + 0.3, xf - 6.6, xf + 0.1))
    seal = (obround_x(p.usb_hole[0] + 0.05, p.usb_hole[1] + 0.05, p.end_wall_x0 + 0.5, p.end_wall_x0 + 1.3)
            .cut(obround_x(p.usb_hole[0] - 0.6, p.usb_hole[1] - 0.6, p.end_wall_x0, p.L)))
    housing = housing.cut(obround_x(p.usb_hole[0] + 1, p.usb_hole[1] + 1, p.end_wall_x0 + 0.5,
                                    p.end_wall_x0 + 1.3).cut(obround_x(p.usb_hole[0] - 0.6, p.usb_hole[1] - 0.6,
                                                                      p.end_wall_x0, p.L)))
    shell = (obround_x(p.usb_shell[0] + 0.3, p.usb_shell[1] + 0.3, xf - 6.4, xf)
             .cut(obround_x(p.usb_shell[0], p.usb_shell[1], xf - 6.2, xf + 0.1)))
    tongue = box(xf - 6.2, xf - 0.6, -3.3, 3.3, -0.35, 0.35)
    return brd, parts, body.union(flange), housing, seal, shell, tongue


def build_split_ring(p, s=-1, r=6.0, wire=0.9):
    """stainless split ring through the lanyard hole on side s (two turns, 0.95 mm apart)"""
    L = p.L
    n = 1 / math.sqrt(2)
    ex, ez = L, s * p.lan_entry_r
    mx, mz = ex - p.lan_exit_dx / 2, ez + s * p.lan_exit_dx / 2     # mid point of the hole axis
    # ring plane = XZ; centre outward from the corner
    cx, cz = mx + r * n, mz + s * r * n
    rings = None
    for dy in (-0.48, 0.48):
        t = cq.Solid.makeTorus(r, wire / 2, cq.Vector(cx, dy, cz), cq.Vector(0, 1, 0))
        w = cq.Workplane("XY").add(t)
        rings = w if rings is None else rings.union(w)
    return rings


def build_label(p):
    """laser marking stand-in: the letters as a 0.015 mm skin on the label flat"""
    xc = (p.flat_x[0] + p.flat_x[1]) / 2
    t = (cq.Workplane("XY").workplane(offset=p.flat_z)
         .text(p.label_text, p.label_size, 0.015, font=FONT, kind="regular", halign="center", valign="center"))
    t = t.rotate((0, 0, 0), (0, 0, 1), 90).translate((xc, 0, 0))
    return t


# --------------------------------------------------------------------------------------------- build
def build_all(p):
    d = {}
    d["body"] = build_body(p)
    d["ring"] = build_ring(p)
    d["head"] = build_head(p)
    d["oring"] = build_oring(p)
    d["optic_holder"], d["optic_lens"] = build_optic(p)
    d["mcpcb"], d["led"], d["phosphor"] = build_led(p)
    d["sled"] = build_sled(p)
    brd, parts = build_board(p)
    d["board"] = brd
    for k, v in parts.items():
        d["bp_" + k] = v
    d["membrane"], d["collar"], d["cap"], d["pin"], d["lightpipe"] = build_button(p)
    d["cell"], d["cell_plus"], d["strip_plus"], d["strip_minus"], d["flex"], d["insulator"] = build_cell(p)
    (d["tail_board"], d["tail_parts"], d["usb_body"], d["usb_housing"], d["usb_seal"], d["usb_shell"],
     d["usb_tongue"]) = build_tail(p)
    d["split_ring"] = build_split_ring(p)
    d["label"] = build_label(p)
    return d


def solid(w):
    return w.val() if isinstance(w, cq.Workplane) else w


def checks(p, d):
    """sizes, walls, fits and masses for the design document"""
    out = {}
    R = p.R
    rb = p.bore_d / 2
    out["length_mm"] = round(p.L, 2)
    out["diameter_mm"] = p.OD
    vol = {k: solid(v).Volume() for k, v in d.items() if v is not None}
    rho = {"body": 2.70, "ring": 2.70, "head": 2.70, "collar": 7.93, "cap": 7.93, "sled": 1.41, "pin": 1.41,
           "membrane": 1.15, "optic_holder": 1.20, "optic_lens": 1.19, "mcpcb": 8.96, "lightpipe": 1.19,
           "oring": 1.30}
    mass = {k: round(vol[k] * rho[k] / 1000, 2) for k in rho if k in vol}
    out["mass_g"] = mass
    out["aluminium_g"] = round(mass["body"] + mass["ring"] + mass["head"], 2)
    out["walls_mm"] = {
        "tube over the cell (bore d%.1f)" % p.bore_d: round(R - rb, 2),
        "label flat over the cell": round(p.flat_z - rb, 2),
        "pocket floor over the bore": round(p.pocket_floor_z - rb, 2),
        "under the button counterbore": round(p.btn_cb_floor_z - rb, 2),
        "external thread root to bore": round(p.thread_minor_ext / 2 - rb, 2),
        "thread undercut to bore": round(p.undercut[2] / 2 - rb, 2),
        "bezel ring at the thread": round(R - p.thread_major / 2, 2),
        "head spigot at the O-ring groove (solid shelf behind the LED)": "solid",
        "tail end wall": p.tail_wall,
        "tail cavity to lanyard hole": None,
        "lanyard bridge (hole to outer corner)": None,
    }
    # lanyard geometry: distance from the hole axis to the cavity corner and to the outer corner
    n = 1 / math.sqrt(2)
    ex, ez = p.L, p.lan_entry_r
    dvec = (-n, n)

    def dist(px, pz):
        vx, vz = px - ex, pz - ez
        return abs(vx * dvec[1] - vz * dvec[0])
    out["walls_mm"]["tail cavity to lanyard hole"] = round(dist(p.end_wall_x0, p.tail_cav_d / 2) - p.lan_d / 2, 2)
    out["walls_mm"]["lanyard bridge (hole to outer corner)"] = round(
        dist(p.L - p.tail_chamfer * 0.5, R - p.tail_chamfer * 0.5) - p.lan_d / 2, 2)
    usb_z = p.usb_hole[1] / 2
    out["walls_mm"]["USB hole to lanyard hole (tail face)"] = round(
        p.lan_entry_r - p.lan_d / 2 * math.sqrt(2) - usb_z, 2)
    # fits
    out["fits_mm"] = {
        "cell radial play in the bore (bare can)": round(rb - p.cell_d / 2, 2),
        "flex + strip room each side (bore - can)": round(rb - p.cell_d / 2, 2),
        "board corner to bore": round(rb - math.hypot(p.board_w / 2, p.board_top_z), 2),
        "switch top (z)": round(p.board_top_z + 0.05 + p.sw_h, 2),
        "pin length": round(p.btn_cb_floor_z - 0.15 - (p.board_top_z + 0.05 + p.sw_h + 0.05), 2),
        "O-ring squeeze %": round(100 * (1 - (rb - p.oring_groove_d / 2) / p.oring_cs), 1),
        "O-ring stretch %": round(100 * (p.oring_groove_d / p.oring_id - 1), 1),
        "head flange in ring thread (radial)": round(p.thread_minor_int / 2 - p.head_flange_d / 2, 3),
        "head boss in ring lip (radial)": round(p.ring_lip_id / 2 - p.head_boss_d / 2, 3),
        "thread engagement length": round(p.undercut[0] - (p.body_front_x + 0.5) - 0.1, 2),
        "tail cavity: socket body diagonal vs cavity d": [round(math.hypot(*p.usb_body), 2), p.tail_cav_d],
    }
    out["stack_x_mm"] = {
        "bezel ring": [0.0, p.ring_len], "head": [p.head_face_x, p.head_end_x],
        "optic front": round(p.head_face_x + p.head_lip_t, 2), "LED board": [round(p.mcpcb_x0, 2), round(p.mcpcb_x1, 2)],
        "tube front face": p.body_front_x, "main board": list(p.board_x), "button": p.btn_x, "indicator": p.ind_x,
        "cell": [round(p.cell_x0, 2), round(p.cell_x1, 2)], "tail board": [round(p.tail_board_x0, 2),
                                                                         round(p.tail_board_x0 + p.tail_board_t, 2)],
        "end wall": [round(p.end_wall_x0, 2), round(p.L, 2)],
    }
    # surface of the aluminium for the thermal model
    out["aluminium_outer_area_mm2"] = round(
        math.pi * p.OD * p.L + math.pi / 4 * p.OD ** 2 - p.usb_hole[0] * p.usb_hole[1]
        + math.pi / 4 * (p.OD ** 2 - p.head_lip_d ** 2), 0)
    # interference check between neighbouring parts
    pairs = [("body", "head"), ("body", "ring"), ("ring", "head"), ("body", "sled"), ("body", "cell"),
             ("sled", "board"), ("body", "board"), ("body", "usb_body"), ("body", "usb_housing"),
             ("body", "tail_board"), ("head", "optic_holder"), ("head", "mcpcb"), ("body", "pin"),
             ("body", "lightpipe"), ("body", "collar"), ("sled", "pin"), ("sled", "cell"), ("body", "flex"),
             ("body", "strip_minus"), ("cell", "flex"), ("cell", "strip_minus"), ("body", "oring_free")]
    inter = {}
    no_thread = box(p.undercut[1], p.L + 1, -20, 20, -20, 20).val()
    for a, b in pairs:
        if b == "oring_free":
            continue
        try:
            if (a, b) == ("body", "ring"):   # outside the thread (the cosmetic V-rings stand in for a helix)
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
    p = P()
    d = build_all(p)
    if "--stl" in sys.argv:
        for k, v in d.items():
            if v is not None:
                cq.exporters.export(v, os.path.join(out_dir, "_ref_%s.stl" % k), tolerance=0.01,
                                    angularTolerance=0.15)
    # machining STEP files: plain thread diameters (M18 x 0.75 6g on the tube, 6H in the ring, on the drawing),
    # no marking (the label is a laser-marking note)
    for shape, nm in ((build_body(p, cosmetic=False), "EDCO_body"), (build_ring(p, cosmetic=False), "EDCO_bezel_ring"),
                      (d["head"], "EDCO_head")):
        cq.exporters.export(shape, os.path.join(out_dir, nm + ".step"))
    asm = cq.Assembly(name="EDCO_v0.1")
    for k, v in d.items():
        if v is not None and k != "split_ring":
            asm.add(v, name=k)
    asm.save(os.path.join(out_dir, "EDCO_v0.1_assembly.step"))
    info = {"params": {k: v for k, v in asdict(p).items()}, "derived": {"L": round(p.L, 3)}}
    info.update(checks(p, d))
    with open(os.path.join(out_dir, "edco_interface.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(json.dumps({k: info[k] for k in ("length_mm", "aluminium_g", "walls_mm", "fits_mm", "interference_mm3",
                                           "mass_g", "aluminium_outer_area_mm2", "stack_x_mm")}, indent=1))


if __name__ == "__main__":
    main()
