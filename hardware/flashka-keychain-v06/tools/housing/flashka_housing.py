#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.6 - parametric aluminium housing

One source of truth for the mechanics: every dimension lives in the
parameter class P below.  The script builds

  tray            - main body, 6061-T6: head block, PCB zone, antenna zone,
                    battery bay and the compact tail with the lanyard slot;
                    three button holes + counterbore in the floor, floor RF window
  lid             - top cover, 6061-T6, 4x M1.6 countersunk screws, stepped
                    opening for the plastic RF window, hold-down boss, rabbet lip
  rf_window       - plastic insert in the lid above the Bluetooth antenna
  tube            - light-pipe tube around the main button (resin, glued)
  cap_main        - main button cap (SUS304, JLCCNC; resin copy in the print kit)
  cap_slide       - slide button cap, next / previous (SUS304; resin copies)
  spacer_ring     - sets the window height above the LED (resin)
  antenna_spacer  - keeps the cells off the module's antenna, plug for the floor RF window (resin)

v0.6 against v0.5: three push buttons on the bottom face (main with a glowing ring,
next, previous), no side button, a second RF window in the floor, a thermal-pad
hold-down for the PCB, the laser label on the lid and a "fighter-jet skin" of
V-groove panel seams (frames + stringers) instead of the knurl and side grooves.

Coordinate system (all mm):
  X = 0 at the front face (light exits towards -X), +X towards the tail
  Y = 0 on the centre line, -Y = control side (USB-C),
  +Y = laser side (laser interlock S2)
  Z = 0 on the bottom face, +Z towards the lid

Run:  python3 flashka_housing.py [outdir]          (full build + checks, about 10 min)
      python3 flashka_housing.py --interface-only  (housing_interface.json only)
"""
import json
import math
import os
import sys
from dataclasses import dataclass, asdict

import cadquery as cq


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
@dataclass
class P:
    # envelope
    W: float = 20.0          # width (Y)
    H: float = 16.0          # height (Z)
    R_edge: float = 2.0      # radius of the four long edges
    C_end: float = 0.8       # bevel on the tail face outline
    C_front: float = 0.2     # chamfer on the front face outline
    wall: float = 1.5        # side wall thickness
    floor: float = 1.5       # floor thickness
    lid_t: float = 1.5       # lid thickness
    inner_r: float = 2.0     # vertical internal corner radius (JLCCNC: R >= H/10+0.5)

    # head block (solid, carries window + laser; the lid covers its rear part)
    L_head: float = 8.5
    Z_axis: float = 8.0      # LED axis height (= mid height)
    lid_x0: float = 4.2      # front edge of the lid (seam V-ring here)

    # main LED: Luminus SST-20 on a ready-made 10 mm DTP copper board, flat window
    Y_w: float = -3.825      # LED / window axis
    win_d: float = 10.0      # mineral-glass window (watch crystal) 10.0 x 1.0
    win_t: float = 1.0
    win_recess: float = 0.2
    bore_clear: float = 0.2  # bore = 10.2: DTP boards are 10.0 +/- 0.1
    led_h: float = 2.0       # SST-20 total height (package 3.45 x 3.45)
    led_gap: float = 0.40    # dome top -> window
    mcpcb_d: float = 10.0    # 10 mm DTP board
    mcpcb_t: float = 1.6
    tim_t: float = 0.15      # thermal adhesive under the board
    ring_od: float = 10.1    # printed spacer ring
    ring_id: float = 7.2
    wire_groove: tuple = (1.4, 0.8)   # LED wire grooves in the bore wall (w, radial depth)
    led_wire_dz: float = 4.3          # wire holes behind the board: Z_axis +/- this
    ledwire_d: float = 1.3            # 28 AWG PTFE wire

    # laser module (6 x 12 mm, integrated driver)
    Y_l: float = 5.85
    Z_las: float = 5.9       # below the PCB (module top 0.25 mm under the board)
    las_d: float = 6.0
    las_len: float = 12.0
    las_clear: float = 0.10
    las_recess: float = 0.3
    las_grub_x: float = 5.6  # M2 set screw from the bottom face (thread clear of the V-ring flank)
    las_bore_extra: float = 0.3
    sleeve_id: float = 4.6   # optional printed sleeve for a 4.5 mm module
    sleeve_od: float = 6.0
    sleeve_len: float = 10.0
    sleeve_slit: float = 0.8

    # main PCB (4 layers, 0.8 mm), parts on both sides; module on top
    pcb_len: float = 24.0
    pcb_t: float = 0.8
    Z_pcb_bot: float = 9.2   # rests on ledges at this height
    pcb_gap_front: float = 0.3
    pcb_side_gap: float = 0.25   # each side: the board drops in, no slide
    pcb_chamfer: float = 1.3     # front corners (clear the R2 cavity corners)
    ledge_w: float = 0.8
    las_keepout_x: float = 12.9  # no ledge / no bottom parts at +Y in front of this

    # ESP32-C3-MINI-1: antenna (16.6 - 11.2 = 5.4 mm) overhangs the PCB rear edge
    mod_w: float = 13.2
    mod_len: float = 16.6
    mod_onboard: float = 11.2
    mod_h: float = 2.4
    mod_y: float = -1.4           # module centre (top side, -Y aligned)
    ant_gap: float = 0.8          # antenna end -> cells (printed spacer)

    # cells: 2 x 601646 (6.0 x 16 x 47 incl. PCM) stacked, in parallel
    L_batt: float = 48.0
    cell_t: float = 6.0
    cell_w: float = 16.0
    cell_l: float = 47.0

    # tail (lid runs to the end): front wall, lanyard slot, end wall
    tail_front_wall: float = 1.0
    lan_slot_w: float = 4.4      # along X (full-round ends): split rings, carabiners <= 4 mm
    lan_slot_len: float = 7.6    # across (Y); 0.5 mm wall to the rear countersinks
    tail_end_wall: float = 2.0
    lan_chamfer: float = 0.35
    twin_x: float = 6.0          # recessed window on the bottom face (A9 style)
    twin_y: float = 14.0
    twin_r: float = 0.8
    twin_corner: float = 1.8     # 45 deg corners at the rear
    twin_depth: float = 1.0
    twin_chamfer: float = 0.3
    twin_front_gap: float = 1.0  # window front edge >= this behind the bay end (0.8 mm metal to the corner reliefs)
    tail_facet: float = 2.0      # 45 deg facets on the two tail corners

    # RF window (plastic insert) in the lid above the antenna
    rfw_x0_over_pcb: float = 1.0  # window starts this far in front of the PCB rear edge
    rfw_x_beyond_ant: float = 0.5
    rfw_y: float = 14.0
    rfw_r: float = 1.5
    rfw_flange: float = 0.8       # pocket margin on the lid underside
    rfw_flange_t: float = 0.6     # pocket depth in the lid
    rfw_flange_drop: float = 0.2  # flange hangs this far below the lid (0.8 mm flange: JLC3DP minimum wall)
    rfw_clear: float = 0.05       # insert clearance in the opening (glued)

    # fighter-jet skin: 90 deg V-grooves (one chamfer / engraving cutter), spec 2.8
    seam_depth: float = 0.25      # V ring around the body at the lid's front edge; also the skin groove depth
    skin_depth: float = 0.25      # frames and stringers (spec: 0.25 - 0.30 mm)
    skin_frames: tuple = (10.2, 30.1, 41.0, 56.0, 71.0, 86.0)   # frame stations (X); 10.2 and 30.1 are partial rings
    skin_stringer_z: tuple = (3.0, 13.0)    # side stringers (Z)
    skin_stringer_y: float = 3.6            # lid / bottom stringers at +/- this Y
    skin_stringer_x: tuple = (41.0, 86.0)   # lid / bottom stringers from frame to frame
    skin_clear: float = 0.5                 # groove edge -> hole / window / opening
    skin_min_metal: float = 1.1             # metal left under any groove
    # lid joint with a 0.6 mm rabbet lip, so that the skin seams run over the corner without a knife edge
    lid_lip_z: float = 13.9                 # lip bottom; the lid wraps the tray's side walls from here
    lid_lip_gap: float = 0.05               # lip inner face to the tray's rabbet (each side)
    cav_gusset: float = 0.3                 # 45 deg fillet in the cavity's four long corners (metal under the corner seams)

    # screws / threads
    m16_tap: float = 1.25
    m16_drill: float = 3.6
    m16_clear: float = 1.8
    m16_csk: float = 3.3
    screw_dy: float = 6.3        # all four lid screws (countersink stays on the flat top)
    screw_x_front: float = 7.0   # in the head block
    m2_tap: float = 1.6

    # control side (-Y): USB-C (S1 is gone in v0.6)
    X_usb: float = 14.6
    usb_open: tuple = (12.6, 6.8, 2.0)   # one opening through the wall (overmold size)
    usb_open_chamfer: float = 0.3
    # laser side (+Y): S2 interlock slide (top side of the PCB), knob into the wall
    X_s2: float = 14.05                  # front mounting pads >= 0.2 mm inside the PCB chamfer
    s2_slot: tuple = (3.2, 2.0, 0.8)
    s2_knob_z: float = 0.7
    s2_knob_len: float = 1.55
    s2_knob_out: float = 0.75            # knob tip beyond the PCB edge (tilt-in assembly)

    # v0.6: three buttons on the bottom face (floor), switches on the PCB bottom side
    # (Alps SKRKAEE020, 3.9 x 2.9 x 2.0 mm, top push, actuator pointing down)
    btn_y: float = 3.2                   # button row (housing Y); +Y = right when the floor faces up
    X_next: float = 16.4                 # "next" (towards the head)  - switch rot 0 (pads along X)
    X_main: float = 23.6                 # main button with the light-pipe ring - switch rot 90
    X_prev: float = 30.8                 # "previous" (towards the tail) - switch rot 90 (pads along Y)
    sw_h: float = 2.0                    # switch height incl. actuator (tip = Z_pcb_bot - sw_h)
    sw_body: tuple = (3.9, 2.9)          # switch body along footprint x, y (pads at x -/+2.1)
    sw_travel: float = 0.25
    cap_gap: float = 0.30                # free play: cap stem end -> actuator tip (cap on its seat)
    cap_apex_z: float = -0.10            # domed cap faces 0.1 mm proud of the bottom face (no pocket)
    # light-pipe tube around the main switch (8001 resin, glued in a counterbored floor hole)
    tube_od: float = 8.4                 # visible ring: ID 6.0 / OD 8.4, flush with the bottom face
    tube_rim: tuple = (8.8, 1.1, 1.5)    # rim d, z0, z1 - sits in a counterbore from the inside
    tube_id_low: float = 6.0             # cap head bore (Z 0 .. tube_step_z)
    tube_id_up: float = 6.8              # cap flange bore (above the step)
    tube_step_z: float = 2.4             # bore step = flange seat of the main cap
    main_hole: float = 8.45              # floor hole for the tube (counterbore = rim d + 0.05)
    ring_led_h: float = 0.85             # NH-B1010RGBT-HF height (worst case; datasheet drawing unread)
    ring_led_r: float = 3.8              # LED centres on the tube wall, at X_main -/+ this
    tube_led_gap: float = 0.15           # tube top -> LED face
    # stainless caps (SUS304, JLCCNC); the same geometry is also in the resin print kit (fallback)
    main_cap: tuple = (5.8, 6.6, 0.6, 3.0)    # head d, flange d, flange t, stem d
    slide_cap: tuple = (3.4, 5.0, 0.6, 2.0)   # head d, flange d, flange t, stem d
    slide_hole: float = 3.6
    # second RF window in the floor under the antenna (plugged by the antenna spacer)
    frw_box: tuple = (33.6, 38.7, 7.0, 1.5)   # x0, x1, half y, corner r
    # the switches push the PCB up: hold it down at the module can (lid boss + thermal pad)
    holddown_preload_n: float = 3.0      # target (spec 2.4)
    holddown_front: tuple = (15.6, 19.4, 0.0, 3.3)   # top-side component-free area for the front hold-down pad (x0, x1, y0, y1)
    boss_box: tuple = (22.1, 30.9, -7.6, 4.8)   # lid boss x0, x1, y0, y1 (inside the can plan X 22.0-32.6, Y -7.7..4.9; 0.1 off the RF pocket at X 31.0)
    boss_r: float = 1.0
    boss_h: float = 1.3                  # boss height below the lid underside (pad gap 0.8 mm = pad 1.0 mm compressed 20 %)
    pad_t0: float = 1.0                  # thermal gap pad on the can, free thickness (common sizes 0.5 / 1.0 / 1.5 / 2.0 mm)
    pad_E_mpa: float = 1.0               # assumed apparent compression modulus of a firm gap pad (Shore 00 70-80), linear to 30 %
    pad_press_n: float = 10.0            # button push used for the lift check
    # second hold-down next to SW2: lid boss + pad cut from a 1.0 mm silicone rubber sheet (Shore A 70) on keepout_top
    boss2_box: tuple = (15.65, 19.35, 0.05, 3.25)   # inside components.keepout_top X 15.6-19.4, Y 0.0-3.3 (0.05 mm margin)
    boss2_r: float = 0.5
    boss2_h: float = 3.7                 # boss height below the lid underside (boss face Z 10.8: pad gap 0.8 mm)
    pad2_t0: float = 1.0                 # silicone rubber sheet, free thickness (bought: 1 mm sheet, Shore A 70)
    pad2_E_mpa: float = 5.3              # assumed Young's modulus, Shore A 70 (Gent relation: A50 2.2, A60 3.3, A70 5.3 MPa)
    boss3_box: tuple = None              # optional third boss + rubber pad (model only unless set)
    boss3_h: float = 3.7
    pcb_E_mpa: float = 20000.0           # FR-4 plate
    pcb_nu: float = 0.14
    s2_stop_gap: float = 0.225           # S2 knob in its slot: free travel up from the rest position (slot 2.0 high, knob 1.55)

    # ---------------------------------------------------------------- derived
    @property
    def inner_half(self):
        return self.W / 2 - self.wall

    @property
    def Z_lid(self):
        return self.H - self.lid_t

    @property
    def Z_pcb_top(self):
        return self.Z_pcb_bot + self.pcb_t

    @property
    def D_w(self):              # depth of the window / LED-board bore
        return self.win_recess + self.win_t + self.led_gap + self.led_h + self.mcpcb_t + self.tim_t

    @property
    def x_led_board(self):      # front face of the DTP board
        return self.win_recess + self.win_t + self.led_gap + self.led_h

    @property
    def X_pcb0(self):
        return self.L_head + self.pcb_gap_front

    @property
    def X_pcb1(self):
        return self.X_pcb0 + self.pcb_len

    @property
    def Y_pcb(self):
        return self.inner_half - self.pcb_side_gap

    @property
    def X_ant1(self):           # rear end of the module (antenna tip)
        return self.X_pcb1 + self.mod_len - self.mod_onboard

    @property
    def X_batt0(self):
        return self.X_ant1 + self.ant_gap

    @property
    def X_batt1(self):
        return self.X_batt0 + self.L_batt

    @property
    def L_tail(self):
        return self.tail_front_wall + self.lan_slot_w + self.tail_end_wall

    @property
    def L(self):
        return self.X_batt1 + self.L_tail

    @property
    def X_lan(self):            # lanyard slot centre
        return self.X_batt1 + self.tail_front_wall + self.lan_slot_w / 2

    @property
    def X_screw_back(self):
        return self.X_lan

    @property
    def Z_usb(self):            # receptacle centre (bottom side, 3.21 tall)
        return self.Z_pcb_bot - 3.21 / 2

    @property
    def minusY_open(self):     # X ranges without the -Y ledge (USB-C only in v0.6)
        return ((self.X_usb - 4.9, self.X_usb + 5.0),)

    @property
    def Z_sw_tip(self):        # switch actuator tip (bottom side, pointing down)
        return self.Z_pcb_bot - self.sw_h

    @property
    def can_top_z(self):        # module can top
        return self.Z_pcb_top + self.mod_h

    @property
    def pad_t(self):            # pad thickness after assembly
        return self.Z_lid - self.boss_h - self.can_top_z

    @property
    def pad2_t(self):           # pad 2 thickness after assembly (PCB top Z 10.0 to the boss face)
        return self.Z_lid - self.boss2_h - self.Z_pcb_top

    @property
    def pad2_strain(self):
        return 1.0 - self.pad2_t / self.pad2_t0

    @property
    def pad_strain(self):
        return 1.0 - self.pad_t / self.pad_t0

    @property
    def Z_tube_top(self):
        return self.Z_pcb_bot - self.ring_led_h - self.tube_led_gap



    @property
    def rfw_box(self):          # RF window opening (x0, x1, half y)
        return (self.X_pcb1 - self.rfw_x0_over_pcb, self.X_ant1 + self.rfw_x_beyond_ant,
                self.rfw_y / 2)

    @property
    def L_total(self):
        return self.L


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def rbox(x0, x1, y0, y1, z0, z1, r=0.0, axis="Z"):
    """Axis-aligned box with the edges parallel to `axis` rounded by r."""
    b = (cq.Workplane("XY")
         .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
         .translate((x0, y0, z0)))
    if r > 0:
        b = b.edges("|" + axis).fillet(r)
    return b


def cyl_x(y, z, d, x0, x1):
    return (cq.Workplane("YZ").workplane(offset=x0)
            .center(y, z).circle(d / 2).extrude(x1 - x0))


def cyl_z(x, y, d, z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0)
            .center(x, y).circle(d / 2).extrude(z1 - z0))


def cyl_y(x, z, d, y0, y1):
    return (cq.Workplane("XZ").workplane(offset=-y0)
            .center(x, z).circle(d / 2).extrude(-(y1 - y0)))


def slot_y(xc, zc, w, h, r, y0, y1):
    """Rounded-rectangle prism through a side wall (extent y0..y1)."""
    return rbox(xc - w / 2, xc + w / 2, y0, y1, zc - h / 2, zc + h / 2,
                r=min(r, h / 2 - 1e-3, w / 2 - 1e-3), axis="Y")


def rrect_z(x0, x1, y0, y1, z0, z1, r):
    return rbox(x0, x1, y0, y1, z0, z1, r=min(r, (x1 - x0) / 2 - 1e-3, (y1 - y0) / 2 - 1e-3))


# --------------------------------------------------------------------------
# tactile exterior (texture tools are plain OCC solids, cut in one operation)
# --------------------------------------------------------------------------
def vgroove(a, b, n_in, d, ext=0.3):
    """90 deg V-groove with pyramid ends (what a V-cutter leaves): the apex line
    a->b lies d below the surface, n_in points into the material."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeWedge
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    a, b, n = cq.Vector(*a), cq.Vector(*b), cq.Vector(*n_in).normalized()
    g = b - a
    ln = g.Length
    g = g.normalized()
    zd = g.cross(n)
    D = d + ext
    Pt = a - g * D - n * D - zd * D
    ax = gp_Ax2(gp_Pnt(Pt.x, Pt.y, Pt.z), gp_Dir(zd.x, zd.y, zd.z), gp_Dir(g.x, g.y, g.z))
    return cq.Solid(BRepPrimAPI_MakeWedge(ax, ln + 2 * D, D, 2 * D, D, D, D + ln, D).Shape())


def _rrect_face_yz(x, hw, hh, r, zc):
    return (cq.Workplane("YZ", origin=(x, 0, 0)).center(0, zc)
            .sketch().rect(2 * hw, 2 * hh).vertices().fillet(r).finalize())


def seam_groove_cutter(p: P, ext=0.3):
    """90 deg V-groove ring around the body at the lid's front edge (X = lid_x0):
    the lid seam continues it on the top."""
    d = p.seam_depth
    xa = p.lid_x0 - d          # apex; the groove's rear flank ends at lid_x0
    D = d + ext
    hw, hh, zc = p.W / 2 - d, p.H / 2 - d, p.H / 2
    r = p.R_edge - d
    left = _rrect_face_yz(xa, hw, hh, r, zc).extrude(-D, taper=-45)
    right = _rrect_face_yz(xa, hw, hh, r, zc).extrude(D, taper=-45)
    core = left.union(right)
    ring = rbox(xa - D + 0.01, xa + D - 0.01, -p.W, p.W, -p.H, 2 * p.H).cut(core)
    return ring


# --------------------------------------------------------------------------
# fighter-jet skin: panel seams (frames = transverse rings, stringers = longitudinal lines)
# --------------------------------------------------------------------------
def _loop(p: P, d):
    """Rounded-rectangle loop of the groove apex line, in (y, z).  s = 0 at the top centre, running
    to +Y, down the +Y side, along the bottom to -Y and up the -Y side.  -> (pieces, total length)"""
    hw, hh, zc, r = p.W / 2 - d, p.H / 2 - d, p.H / 2, p.R_edge - d
    zt, zb = zc + hh, zc - hh
    pcs = [("L", (0.0, zt), (hw - r, zt)),
           ("A", (hw - r, zt - r), r, 90.0, 0.0),
           ("L", (hw, zt - r), (hw, zb + r)),
           ("A", (hw - r, zb + r), r, 0.0, -90.0),
           ("L", (hw - r, zb), (-(hw - r), zb)),
           ("A", (-(hw - r), zb + r), r, -90.0, -180.0),
           ("L", (-hw, zb + r), (-hw, zt - r)),
           ("A", (-(hw - r), zt - r), r, 180.0, 90.0),
           ("L", (-(hw - r), zt), (0.0, zt))]
    out, tot = [], 0.0
    for pc in pcs:
        ln = math.dist(pc[1], pc[2]) if pc[0] == "L" else r * math.radians(abs(pc[4] - pc[3]))
        out.append((pc, tot, ln))
        tot += ln
    return out, tot


def loop_s(p: P, face, v, d=None):
    """arc length s of a point on a face of the apex loop: ('top', y) ('bottom', y) ('+Y', z) ('-Y', z)"""
    d = p.skin_depth if d is None else d
    pcs, tot = _loop(p, d)
    hw, hh, zc, r = p.W / 2 - d, p.H / 2 - d, p.H / 2, p.R_edge - d
    zt, zb = zc + hh, zc - hh
    s_r0 = (hw - r) + math.pi / 2 * r
    s_b0 = s_r0 + 2 * (hh - r) + math.pi / 2 * r
    s_l0 = s_b0 + 2 * (hw - r) + math.pi / 2 * r
    if face == "top":
        return v % tot
    if face == "+Y":
        return s_r0 + (zt - r - v)
    if face == "bottom":
        return s_b0 + (hw - r - v)
    if face == "-Y":
        return s_l0 + (v - (zb + r))
    raise ValueError(face)


def _loop_point(pc, t, ln):
    if pc[0] == "L":
        (y0, z0), (y1, z1) = pc[1], pc[2]
        f = t / ln if ln else 0.0
        return (y0 + (y1 - y0) * f, z0 + (z1 - z0) * f)
    (cy, cz), r, a0, a1 = pc[1], pc[2], pc[3], pc[4]
    a = math.radians(a0 + (a1 - a0) * (t / ln))
    return (cy + r * math.cos(a), cz + r * math.sin(a))


def frame_path(p: P, x, s0, s1, d=None):
    """cq.Wire along the apex loop at station X = x from s0 to s1 (s1 - s0 <= loop length; may wrap)."""
    d = p.skin_depth if d is None else d
    pcs, tot = _loop(p, d)
    edges = []
    for lap in (0, 1, 2):
        for pc, st, ln in pcs:
            a, b = st + lap * tot, st + lap * tot + ln
            lo, hi = max(a, s0), min(b, s1)
            if hi - lo < 1e-6:
                continue
            pa, pb = _loop_point(pc, lo - a, ln), _loop_point(pc, hi - a, ln)
            va, vb = cq.Vector(x, pa[0], pa[1]), cq.Vector(x, pb[0], pb[1])
            if pc[0] == "L":
                edges.append(cq.Edge.makeLine(va, vb))
            else:
                pm = _loop_point(pc, 0.5 * (lo + hi) - a, ln)
                edges.append(cq.Edge.makeThreePointArc(va, cq.Vector(x, pm[0], pm[1]), vb))
    return cq.Wire.assembleEdges(edges)


def frame_groove(p: P, x, s0, s1, d=None, ext=0.3):
    """90 deg V-groove (apex d under the surface, flat triangular ends) swept along the loop."""
    d = p.skin_depth if d is None else d
    pcs, tot = _loop(p, d)
    path = frame_path(p, x, s0, s1, d)
    # profile at the start: apex on the path, opening outwards
    for pc, st, ln in pcs:
        for lap in (0, 1, 2):
            a = st + lap * tot
            if a <= s0 + 1e-9 < a + ln + 1e-9:
                t = s0 - a
                y, z = _loop_point(pc, t, ln)
                y2, z2 = _loop_point(pc, min(t + 1e-3, ln), ln)
                if (y2, z2) == (y, z):
                    y2, z2 = _loop_point(pc, t - 1e-3, ln)
                    ty, tz = y - y2, z - z2
                else:
                    ty, tz = y2 - y, z2 - z
                nrm = math.hypot(ty, tz)
                ty, tz = ty / nrm, tz / nrm
                ny, nz = -tz, ty                      # outward normal
                D = d + ext
                A = cq.Vector(x, y, z)
                pts = [A, cq.Vector(x + D, y + ny * D, z + nz * D), cq.Vector(x - D, y + ny * D, z + nz * D)]
                prof = cq.Wire.makePolygon(pts + [pts[0]])
                return cq.Solid.sweep(prof, [], path, True, False, None, "transformed")
    raise RuntimeError("no start piece")


def skin_layout(p: P):
    """The panel-seam layout as data: list of dict(name, kind, ...).  frames: x, s0, s1 (s on the apex loop);
    stringers: face, a, b (3D apex-line end points)."""
    d = p.skin_depth
    pcs, P_ = _loop(p, d)
    s = lambda f, v: loop_s(p, f, v)
    zlo, zhi = p.skin_stringer_z
    fr = p.skin_frames
    items = []
    # A (head panel / label panel boundary): lid + corners on top, ends on the upper stringers (+Y: S2 slot and
    # laser-bore wall in the way); the bottom half runs between the lower stringers
    items.append(dict(name=f"frame A X{fr[0]:g} (top)", kind="frame", x=fr[0], s0=s("-Y", zhi), s1=P_ + s("+Y", zhi)))
    items.append(dict(name=f"frame A X{fr[0]:g} (bottom)", kind="frame", x=fr[0], s0=s("+Y", zlo), s1=s("-Y", zlo)))
    # B: lid and both sides, ends on the low stringers (the floor holes are in the way underneath)
    items.append(dict(name=f"frame B X{fr[1]:g}", kind="frame", x=fr[1], s0=s("-Y", zlo), s1=P_ + s("+Y", zlo)))
    for nm, x in zip("CDEF", fr[2:]):
        items.append(dict(name=f"frame {nm} X{x:g} (upper half)", kind="frame", x=x, s0=0.0, s1=P_ / 2))
        items.append(dict(name=f"frame {nm} X{x:g} (lower half)", kind="frame", x=x, s0=P_ / 2, s1=P_))
    x0s, x1s = p.skin_stringer_x
    xa, xb = p.lid_x0 - p.seam_depth, fr[-1]
    for sy in (-1, 1):
        y = sy * p.skin_stringer_y
        items.append(dict(name=f"stringer lid Y{y:+g}", kind="stringer", face="top", a=(x0s, y, p.H - d),
                          b=(x1s, y, p.H - d), n_in=(0, 0, -1)))
        items.append(dict(name=f"stringer bottom Y{y:+g}", kind="stringer", face="bottom", a=(x0s, y, d),
                          b=(x1s, y, d), n_in=(0, 0, 1)))
        for z in p.skin_stringer_z:
            items.append(dict(name=f"stringer {'+Y' if sy > 0 else '-Y'} side Z{z:g}", kind="stringer",
                              face="+Y" if sy > 0 else "-Y", a=(xa, sy * (p.W / 2 - d), z),
                              b=(xb, sy * (p.W / 2 - d), z), n_in=(0, -sy, 0)))
    return items


_SKIN_CACHE = {}


def skin_tools(p: P):
    """[(name, kind, solid)] - all skin grooves (the lid-front V-ring is separate: seam_groove_cutter)"""
    key = repr(sorted(asdict(p).items()))
    if key in _SKIN_CACHE:
        return _SKIN_CACHE[key]
    out = []
    for it in skin_layout(p):
        if it["kind"] == "frame":
            sol = frame_groove(p, it["x"], it["s0"], it["s1"])
        else:
            sol = vgroove(it["a"], it["b"], it["n_in"], p.skin_depth)
        out.append((it["name"], it["kind"], sol))
    _SKIN_CACHE[key] = out
    return out


def skin_apex_wires(p: P):
    """apex lines of the skin grooves (3D wires / edges) for the metal-under-groove check"""
    out = []
    for it in skin_layout(p):
        if it["kind"] == "frame":
            out.append((it["name"], frame_path(p, it["x"], it["s0"], it["s1"])))
        else:
            out.append((it["name"], cq.Edge.makeLine(cq.Vector(*it["a"]), cq.Vector(*it["b"]))))
    return out


def _chamfered_through(face_wp_fn, z0, z1, c, ext=0.1, top=True, bottom=True):
    core = face_wp_fn(z0 - 1).extrude(z1 - z0 + 2)
    if top:
        core = core.union(face_wp_fn(z1 - c).extrude(c + ext, taper=-45))
    if bottom:
        # nominal outline at z0 + c, flaring downwards (a negative taper grows)
        core = core.union(face_wp_fn(z0 + c).extrude(-(c + ext), taper=-45))
    return core


def tail_tools(p: P):
    """Compact tail: stadium slot through tray and lid, a recessed window on the
    bottom face around it (after the RovyVon A9 tail), 45 deg tail facets.
    Returns (tray_tools, lid_tools)."""
    xc, d, H = p.X_lan, p.twin_depth, p.H
    x0, x1 = max(xc - p.twin_x / 2, p.X_batt1 + p.twin_front_gap), xc + p.twin_x / 2
    hy, k = p.twin_y / 2, p.twin_corner
    sk = (cq.Sketch().polygon([(x0, -hy), (x1 - k, -hy), (x1, -hy + k), (x1, hy - k),
                               (x1 - k, hy), (x0, hy), (x0, -hy)])
          .vertices().fillet(p.twin_r))
    bot = cq.Workplane("XY", origin=(0, 0, -1)).placeSketch(sk).extrude(d + 1)
    rim = (cq.Workplane("XY", origin=(0, 0, p.twin_chamfer)).placeSketch(sk)
           .extrude(-(p.twin_chamfer + 0.3), taper=-45))
    bot = bot.union(rim)

    def slot(z):
        return (cq.Workplane("XY", origin=(0, 0, z)).center(xc, 0)
                .slot2D(p.lan_slot_len, p.lan_slot_w, 90))
    tray_slot = _chamfered_through(slot, d, p.Z_lid, p.lan_chamfer, top=False)
    lid_slot = _chamfered_through(slot, p.Z_lid, H, p.lan_chamfer, bottom=False)
    facets = []
    for s in (-1, 1):
        f, L, w = p.tail_facet, p.L, p.W / 2
        facets.append(cq.Workplane("XY", origin=(0, 0, -1))
                      .polyline([(L - f, s * w), (L + 3, s * w), (L + 3, s * (w - f - 3))]).close()
                      .extrude(H + 2))
    return [bot, tray_slot] + facets, [lid_slot] + facets


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------
def envelope(p: P):
    env = (cq.Workplane("YZ").center(0, p.H / 2).rect(p.W, p.H)
           .extrude(p.L).edges("|X").fillet(p.R_edge))
    env = env.faces("<X").chamfer(p.C_front).faces(">X").chamfer(p.C_end)
    return env


def led_wire_paths(p: P):
    """LED wires: grooves in the bore wall at 12 and 6 o'clock (around the DTP
    board's rim), then holes from the bore floor into the PCB zone - the top
    wire ends above the PCB (LED+ pad, top side), the bottom one below it
    (LED- pad, bottom side)."""
    gw, gd = p.wire_groove
    rb = (p.win_d + p.bore_clear) / 2
    out = []
    for s in (1, -1):
        z_out = p.Z_axis + s * (rb + gd / 2 - 0.2)
        groove = rbox(p.x_led_board - 0.6, p.D_w + 0.01, p.Y_w - gw / 2, p.Y_w + gw / 2,
                      min(p.Z_axis + s * (rb - 0.5), z_out + s * gd / 2),
                      max(p.Z_axis + s * (rb - 0.5), z_out + s * gd / 2))
        hole = cyl_x(p.Y_w, p.Z_axis + s * p.led_wire_dz, p.ledwire_d,
                     p.D_w - 0.01, p.L_head + 0.01)
        out.append((groove, hole))
    return out


def lid_region(p: P):
    """Volume that belongs to the lid (cut out of the tray): the plate above Z_lid plus a 0.6 mm
    rabbet lip that wraps the tray's two side walls (so the skin seams cross the joint on the flat
    side face and the lid has no knife edge).  The tray gets the lip without clearance."""
    ih = p.inner_half
    r = rbox(p.lid_x0, p.L + 1, -p.W, p.W, p.Z_lid, p.H + 1)
    for s in (-1, 1):
        y0, y1 = (ih, p.W) if s > 0 else (-p.W, -ih)
        r = r.union(rbox(p.lid_x0, p.L + 1, y0, y1, p.lid_lip_z, p.H + 1))
    return r


def lid_part_region(p: P):
    """Same, with the lip's inner face lid_lip_gap clear of the tray's rabbet wall."""
    ih = p.inner_half + p.lid_lip_gap
    r = rbox(p.lid_x0, p.L + 1, -p.W, p.W, p.Z_lid, p.H + 1)
    for s in (-1, 1):
        y0, y1 = (ih, p.W) if s > 0 else (-p.W, -ih)
        r = r.union(rbox(p.lid_x0, p.L + 1, y0, y1, p.lid_lip_z, p.H + 1))
    return r


def gusset_prisms_bottom(p: P, c=None, x0=None, x1=None):
    """Triangular prisms (legs c) in the two floor corners of the cavity (metal under the corner seams)."""
    c = p.cav_gusset if c is None else c
    ih, fl = p.inner_half, p.floor
    x0 = p.L_head if x0 is None else x0
    x1 = p.X_batt1 if x1 is None else x1
    out = None
    for s in (-1, 1):
        pts = [(s * (ih - c), fl - 0.01), (s * (ih + 0.01), fl - 0.01), (s * (ih + 0.01), fl + c),
               (s * ih, fl + c), (s * (ih - c), fl)]
        w = cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(pts).close().extrude(x1 - x0)
        out = w if out is None else out.union(w)
    return out


def lid_gussets(p: P):
    """Triangular fillets in the lid's two inner corners (underside / lip), only where the cavity is."""
    c = p.cav_gusset
    ih, zl = p.inner_half + p.lid_lip_gap, p.Z_lid
    out = None
    for s in (-1, 1):
        pts = [(s * (ih + 0.01), zl + 0.01), (s * (ih - c), zl + 0.01), (s * (ih - c), zl), (s * ih, zl - c),
               (s * (ih + 0.01), zl - c)]
        w = cq.Workplane("YZ", origin=(p.L_head, 0, 0)).polyline(pts).close().extrude(p.X_batt1 - p.L_head)
        out = w if out is None else out.union(w)
    box = rbox(p.L_head, p.X_batt1, -(p.inner_half + 0.06), p.inner_half + 0.06, p.Z_lid - 1, p.Z_lid + 0.5,
               p.inner_r + 0.06)
    return out.intersect(box)


def cavity_solid(p: P):
    """The milled interior: upper level full width (PCB zone to bay end), a
    trough between the ledges under the PCB, full width in the antenna zone
    and the bay, plus the ledge interruptions (USB-C, laser tail).  The two floor
    corners carry a 0.3 mm 45 deg fillet (metal under the corner seams)."""
    ih, r = p.inner_half, p.inner_r
    c = rbox(p.L_head, p.X_batt1, -ih, ih, p.Z_pcb_bot, p.Z_lid + 0.01, r)
    c = c.union(rbox(p.L_head, p.X_pcb1 + 0.5, -(ih - p.ledge_w), ih - p.ledge_w,
                     p.floor, p.Z_pcb_bot + 0.01, r))
    c = c.union(rbox(p.X_pcb1, p.X_batt1, -ih, ih, p.floor, p.Z_pcb_bot + 0.01, r))
    # USB-C hangs under the -Y edge: no ledge there
    for (xa, xb) in p.minusY_open:
        c = c.union(rbox(xa, xb, -ih, -(ih - p.ledge_w) + 1.0, p.floor, p.Z_pcb_bot + 0.01, 0.6))
    # laser module tail at +Y: no ledge in front of las_keepout_x
    c = c.union(rbox(p.L_head, p.las_keepout_x, ih - p.ledge_w - 1.0, ih,
                     p.floor, p.Z_pcb_bot + 0.01, 0.6))
    return c.cut(gusset_prisms_bottom(p))


def floor_hole_tools(p: P):
    """Floor holes (v0.6): main button hole + counterbore for the tube rim, two slide-button holes with
    a 0.2 x 45 deg outer chamfer, the floor RF window."""
    fl = p.floor
    zb = p.tube_rim[1]
    out = [cyl_z(p.X_main, p.btn_y, p.main_hole, -1, zb + 0.05),
           cyl_z(p.X_main, p.btn_y, p.tube_rim[0] + 0.05, zb, fl + 0.1)]
    for x in (p.X_next, p.X_prev):
        out.append(cyl_z(x, p.btn_y, p.slide_hole, -1, fl + 0.1))
        c = 0.2
        out.append(cq.Workplane("XY").add(cq.Solid.makeCone(p.slide_hole / 2 + c + 0.2, p.slide_hole / 2, c + 0.2,
                                                           pnt=cq.Vector(x, p.btn_y, -0.2))))
    x0, x1, hy, r = p.frw_box
    out.append(rrect_z(x0, x1, -hy, hy, -1, fl + 0.1, r))
    return out


def build_tray(p: P, texture=None):
    """texture=True (default): the skin grooves are cut; False: plain body (fast, for fit checks)."""
    if texture is None:
        texture = True
    t = envelope(p).cut(lid_region(p))
    t = t.cut(cavity_solid(p))
    ih = p.inner_half
    # corner reliefs at the bay's rear end so square-cornered cells fit
    rr = 1.2
    off = rr / math.sqrt(2)
    for sy in (-1, 1):
        t = t.cut(cyl_z(p.X_batt1 - off, sy * (ih - off), 2 * rr, p.floor, p.Z_lid + 0.01))

    # --- head: window / LED-board bore, LED wire grooves + holes, laser bore
    t = t.cut(cyl_x(p.Y_w, p.Z_axis, p.win_d + p.bore_clear, -1, p.D_w))
    for groove, hole in led_wire_paths(p):
        t = t.cut(groove).cut(hole)
    t = t.cut(cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1,
                    p.las_recess + p.las_len + p.las_bore_extra))
    t = t.cut(cyl_z(p.las_grub_x, p.Y_l, p.m2_tap, -1, p.Z_las))

    # --- lid screws: front pair in the head block, rear pair beside the slot
    for s in (-1, 1):
        for x in (p.screw_x_front, p.X_screw_back):
            t = t.cut(cyl_z(x, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid + 0.1))

    # --- floor: three button holes, counterbore, RF window
    for h in floor_hole_tools(p):
        t = t.cut(h)

    # --- control side (-Y): USB-C opening (through)
    yo = -p.W / 2
    w, h, r = p.usb_open
    t = t.cut(slot_y(p.X_usb, p.Z_usb, w, h, r, yo - 1, -ih + 0.01))
    # 45 deg chamfer on the outer edge of the opening (drafted band)
    c = p.usb_open_chamfer
    band = (cq.Workplane("XZ", origin=(0, yo + c, 0)).center(p.X_usb, p.Z_usb).sketch()
            .rect(w, h).vertices().fillet(r).finalize().extrude(c + 0.3, taper=-45))
    t = t.cut(band)
    # --- laser side (+Y): S2 slot
    w, h, r = p.s2_slot
    t = t.cut(slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w, h, r, ih - 0.01, p.W / 2 + 1))

    # --- exterior: V-ring at the lid front edge, tail, skin seams
    t = t.cut(seam_groove_cutter(p))
    tray_tail, _ = tail_tools(p)
    for c_ in tray_tail:
        t = t.cut(c_)
    if texture:
        t = cq.Workplane().add(t.val().cut(*[s for _, _, s in skin_tools(p)]))
    return t


def rf_window_outline(p: P, grow=0.0, z0=0.0, z1=1.0):
    x0, x1, hy = p.rfw_box
    return rrect_z(x0 - grow, x1 + grow, -hy - grow, hy + grow, z0, z1, p.rfw_r + grow)


def boss_solid(p: P):
    x0, x1, y0, y1 = p.boss_box
    return rrect_z(x0, x1, y0, y1, p.Z_lid - p.boss_h, p.Z_lid + 0.01, p.boss_r)


def boss2_solid(p: P):
    x0, x1, y0, y1 = p.boss2_box
    return rrect_z(x0, x1, y0, y1, p.Z_lid - p.boss2_h, p.Z_lid + 0.01, p.boss2_r)


def build_lid(p: P, texture=None):
    if texture is None:
        texture = True
    lid = envelope(p).intersect(lid_part_region(p))
    pts = [(p.screw_x_front, -p.screw_dy), (p.screw_x_front, p.screw_dy),
           (p.X_screw_back, -p.screw_dy), (p.X_screw_back, p.screw_dy)]
    lid = (lid.faces(">Z").workplane(origin=(0, 0, p.H)).pushPoints(pts)
           .cskHole(p.m16_clear, p.m16_csk, 90))
    # RF window: through opening + flange pocket from the underside
    lid = lid.cut(rf_window_outline(p, 0.0, p.Z_lid - 1, p.H + 1))
    lid = lid.cut(rf_window_outline(p, p.rfw_flange, p.Z_lid - 1, p.Z_lid + p.rfw_flange_t))
    _, lid_tail = tail_tools(p)
    for c_ in lid_tail:
        lid = lid.cut(c_)
    # hold-down boss over the module can, fillets in the two inner corners
    lid = lid.union(boss_solid(p)).union(boss2_solid(p)).union(lid_gussets(p))
    lid = lid.cut(seam_groove_cutter(p))
    if texture:
        lid = cq.Workplane().add(lid.val().cut(*[s for _, _, s in skin_tools(p)]))
    return lid


def build_rf_window(p: P):
    """Stepped plastic insert: plug in the opening (flush with the lid top),
    flange in the underside pocket. Glue in from inside (epoxy)."""
    c = p.rfw_clear
    plug = rf_window_outline(p, -c, p.Z_lid + p.rfw_flange_t - 0.01, p.H)
    flange = rf_window_outline(p, p.rfw_flange - c, p.Z_lid - p.rfw_flange_drop, p.Z_lid + p.rfw_flange_t)
    w = plug.union(flange)
    return w


def _revolve(pts, x, y, arc=None):
    """Solid of revolution about the vertical axis through (x, y); pts = (r, z) polygon; arc = (index,
    (rm, zm)) makes the edge pts[index] -> pts[index+1] a circular arc through the mid point."""
    wp = cq.Workplane("XZ").moveTo(*pts[0])
    for i in range(1, len(pts) + 1):
        q = pts[i % len(pts)]
        if arc and arc[0] == i - 1:
            wp = wp.threePointArc(arc[1], q)
        else:
            wp = wp.lineTo(*q)
    return wp.close().revolve(360, (0, 0, 0), (0, 1, 0)).translate((x, y, 0))


def _dome(r_head, sag, apex):
    R = (r_head ** 2 + sag ** 2) / (2 * sag)
    rm = 0.5 * r_head
    zm = apex + R - math.sqrt(R * R - rm * rm)
    return (rm, zm), apex + sag


def build_tube(p: P):
    """Light-pipe tube (8001 resin) around the main button: OD 8.4 from the bottom face (Z 0) to Z_tube_top,
    rim 8.8 in the counterbore, bore 6.0 (cap head) / 6.8 (cap flange) with the cap seat at Z 2.4."""
    ro, rr, z0r, z1r = p.tube_od / 2, p.tube_rim[0] / 2, p.tube_rim[1], p.tube_rim[2]
    ri1, ri2, zs, zt = p.tube_id_low / 2, p.tube_id_up / 2, p.tube_step_z, p.Z_tube_top
    pts = [(ri1, 0.0), (ro, 0.0), (ro, z0r), (rr, z0r), (rr, z1r), (ro, z1r), (ro, zt), (ri2, zt), (ri2, zs),
           (ri1, zs)]
    return _revolve(pts, p.X_main, p.btn_y)


def _cap(p: P, x, y, head_d, fl_d, fl_t, stem_d, z_flange, sag):
    """Button cap: domed head (apex cap_apex_z), flange resting at z_flange, stem to the stem end Z."""
    rh, rf, rs = head_d / 2, fl_d / 2, stem_d / 2
    z_end = p.Z_sw_tip - p.cap_gap
    mid, z_edge = _dome(rh, sag, p.cap_apex_z)
    pts = [(0.0, p.cap_apex_z), (rh, z_edge), (rh, z_flange), (rf, z_flange), (rf, z_flange + fl_t),
           (rs, z_flange + fl_t), (rs, z_end), (0.0, z_end)]
    return _revolve(pts, x, y, arc=(0, mid))


def build_cap_main(p: P, rest=0.0):
    hd, fd, ft, sd = p.main_cap
    return _cap(p, p.X_main, p.btn_y, hd, fd, ft, sd, p.tube_step_z, 0.4).translate((0, 0, rest))


def build_cap_slide(p: P, x=None, rest=0.0):
    hd, fd, ft, sd = p.slide_cap
    x = p.X_next if x is None else x
    return _cap(p, x, p.btn_y, hd, fd, ft, sd, p.floor, 0.3).translate((0, 0, rest))


def build_spacer_ring(p: P):
    """Ring between the DTP board and the window, with notches for the wire
    solder joints at 12 and 6 o'clock."""
    x0 = p.win_recess + p.win_t
    x1 = p.x_led_board
    ring = (cq.Workplane("YZ").workplane(offset=x0).center(p.Y_w, p.Z_axis)
            .circle(p.ring_od / 2).circle(p.ring_id / 2).extrude(x1 - x0))
    for s in (1, -1):
        ring = ring.cut(rbox(x1 - 1.2, x1 + 0.1, p.Y_w - 1.5, p.Y_w + 1.5,
                             p.Z_axis + s * 3.4 - 1.8, p.Z_axis + s * 3.4 + 1.8))
    return ring


def build_antenna_spacer(p: P):
    """U-shaped printed block between the PCB rear edge and the cells: the
    antenna overhang sits in the U, the cells rest against the rear face,
    the cell wires pass through the notch at +Y.  A plug on its bottom fills the floor RF window flush."""
    ih = p.inner_half - 0.1
    x0, x1 = p.X_pcb1 + 0.15, p.X_batt0 - 0.05
    z_top_low = p.Z_pcb_top - 0.4          # below the antenna (module PCB bottom = PCB top)
    body = rbox(x0, x1, -ih, ih, p.floor + 0.05, z_top_low, 0.4)
    side = p.mod_y + p.mod_w / 2 + 0.45    # +Y edge of the module + clearance (PCB may shift 0.24)
    for (ya, yb) in ((-ih, p.mod_y - p.mod_w / 2 - 0.3), (side, ih)):
        if yb - ya > 0.6:
            body = body.union(rbox(x0, x1, ya, yb, p.floor + 0.05,
                                   p.Z_lid - p.rfw_flange_drop - 0.15, 0.2))
    # cell-wire notch (+Y, lower corner)
    for sg in (1, -1):      # both lower rear corners: the cell pads J2 may end up at either side
        ya, yb = (ih - 1.6, ih + 1) if sg > 0 else (-ih - 1, -ih + 1.6)
        body = body.cut(rbox(x0 - 1, x1 + 1, ya, yb, p.floor, p.floor + 2.2))
    # clear of the PCB ledge blocks beside the antenna zone (tray material at X < 34.3, |Y| > 7.2)
    for sg in (1, -1):
        ya, yb = (7.2, ih + 1) if sg > 0 else (-ih - 1, -7.2)
        body = body.cut(rbox(x0 - 1, 34.3, ya, yb, p.floor - 0.1, p.Z_pcb_bot + 0.2))
    # relief for the SW3 slide-cap flange (5.0 dia x 0.6 on the floor, 0.3 clearance)
    fx1 = p.X_prev + p.slide_flange / 2 + 0.3 if hasattr(p, "slide_flange") else p.X_prev + 2.8
    body = body.cut(rbox(x0 - 1, fx1, p.btn_y - 3.0, p.btn_y + 3.0, p.floor - 0.1, p.floor + 1.2))
    # keep clear of the 0.3 mm floor-corner fillets of the cavity
    body = body.cut(gusset_prisms_bottom(p, c=0.7, x0=x0 - 1, x1=x1 + 1))
    # plug for the floor RF window (0.05 clearance), flush with the bottom face
    wx0, wx1, hy, r = p.frw_box
    c = p.rfw_clear
    plug = rrect_z(wx0 + c, wx1 - c, -hy + c, hy - c, 0.0, p.floor + 0.1, r - c)
    return body.union(plug)


def build_laser_sleeve(p: P):
    x0 = p.las_recess
    sl = (cq.Workplane("YZ").workplane(offset=x0).center(p.Y_l, p.Z_las)
          .circle(p.sleeve_od / 2).circle(p.sleeve_id / 2).extrude(p.sleeve_len))
    slit = rbox(x0 - 1, x0 + p.sleeve_len + 1, p.Y_l - p.sleeve_slit / 2, p.Y_l + p.sleeve_slit / 2,
                p.Z_las - p.sleeve_od, p.Z_las)
    return sl.cut(slit)


def build_print_kit(p: P, parts, gap=2.5, sprue_d=1.0):
    """All resin parts on one sprue so that JLC3DP sees a single part above
    its minimum build size (5 x 5 x 5 mm): parts side by side along X,
    joined by 1 mm rods that are cut with side cutters after printing."""
    placed, cursor = [], 0.0
    for name, s in parts:
        bb = s.val().BoundingBox()
        dx = cursor - bb.xmin
        dy = -(bb.ymin + bb.ymax) / 2
        dz = -bb.zmin
        moved = s.translate((dx, dy, dz))
        placed.append((name, moved, moved.val().BoundingBox()))
        cursor += (bb.xmax - bb.xmin) + gap
    kit = placed[0][1]
    for (na, a, ba), (nb, b, bb_) in zip(placed, placed[1:]):
        y0, y1 = max(ba.ymin, bb_.ymin), min(ba.ymax, bb_.ymax)
        z0, z1 = max(ba.zmin, bb_.zmin), min(ba.zmax, bb_.zmax)
        done = False
        for fy in (0.5, 0.3, 0.7, 0.15, 0.85):
            for fz in (0.5, 0.3, 0.7, 0.15, 0.85):
                y, z = y0 + fy * (y1 - y0), z0 + fz * (z1 - z0)
                rod = cq.Workplane("YZ").workplane(offset=ba.xmax - 1.2).center(y, z) \
                    .circle(sprue_d / 2).extrude(bb_.xmin - ba.xmax + 2.4)
                ia = rod.intersect(a).val().Volume() if rod.intersect(a).solids().size() else 0
                ib = rod.intersect(b).val().Volume() if rod.intersect(b).solids().size() else 0
                if ia > 0.05 and ib > 0.05:
                    kit = kit.union(rod)
                    done = True
                    break
            if done:
                break
        if not done:
            raise RuntimeError(f"no sprue position between {na} and {nb}")
        kit = kit.union(b)
    return kit


# --------------------------------------------------------------------------
# PCB interface (read by the KiCad generator)
# --------------------------------------------------------------------------
def pcb_outline(p: P):
    x0, x1, y, c = p.X_pcb0, p.X_pcb1, p.Y_pcb, p.pcb_chamfer
    return [(x0 + c, -y), (x1, -y), (x1, y), (x0 + c, y), (x0, y - c), (x0, -y + c)]


def component_positions(p: P):
    zt, zb = p.Z_pcb_top, p.Z_pcb_bot
    return {
        "J1_usb": {"x": p.X_usb, "face_y": -p.Y_pcb, "side": "B", "z_centre": p.Z_usb,
                   "note": "TYPE-C-31-M-12 on the bottom side, mating face flush with the PCB edge"},
        "buttons": {
            "part": "Alps SKRKAEE020 (LCSC C115357), KiCad Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
            "side": "B", "z_actuator_tip": p.Z_sw_tip,
            "note": "top-push switches on the bottom side, actuator pointing down (-Z) at the "
                    "floor; rot 0 = the two pads (footprint x -/+2.1) along housing X, rot 90 = "
                    "pads along housing Y",
            "SW1_main": {"x": p.X_main, "y": p.btn_y, "rot": 90},
            "SW2_next": {"x": p.X_next, "y": p.btn_y, "rot": 0},
            "SW3_prev": {"x": p.X_prev, "y": p.btn_y, "rot": 90},
        },
        "ring_leds": {
            "part": "NH-B1010RGBT-HF (LCSC C2874113), Aurora:LED_RGB_1010_NH-B1010RGBT",
            "side": "B", "rot": 0,
            "LED3": {"x": p.X_main - p.ring_led_r, "y": p.btn_y},
            "LED4": {"x": p.X_main + p.ring_led_r, "y": p.btn_y},
            "note": "emit downwards into the top face of the light-pipe tube "
                    f"(tube top Z {p.Z_tube_top:.2f}, LED face Z {p.Z_pcb_bot - p.ring_led_h:.2f})",
        },
        "S2_interlock": {"x": p.X_s2, "knob_tip_y": p.Y_pcb + p.s2_knob_out, "side": "F",
                         "note": "PCM12-class slide, knob towards +Y into the wall slot"},
        "U4_module": {"x_onboard_end": p.X_pcb1, "y": p.mod_y, "side": "F",
                      "note": "ESP32-C3-MINI-1, antenna overhangs the rear edge by "
                              f"{p.mod_len - p.mod_onboard:.1f} mm"},
        "pcb": {"x0": p.X_pcb0, "x1": p.X_pcb1, "y_minus": -p.Y_pcb, "y_plus": p.Y_pcb,
                "z_bottom": zb, "t": p.pcb_t},
        "keepout_bottom": [
            {"what": "laser module tail", "x0": p.X_pcb0 - 1, "x1": p.las_keepout_x,
             "y0": p.Y_l - p.las_d / 2 - 0.3, "y1": p.Y_pcb + 1},
        ],
        "keepout_top": [
            {"what": "front hold-down pad (lid boss presses here, next to SW2)",
             "x0": p.holddown_front[0], "x1": p.holddown_front[1],
             "y0": p.holddown_front[2], "y1": p.holddown_front[3],
             "note": "no top-side components inside; copper, vias and solder mask allowed"},
        ],
        "keepout_bottom_circles": [
            {"what": "light-pipe tube around SW1", "x": p.X_main, "y": p.btn_y,
             "r": p.tube_od / 2 + 0.2, "allowed": ["SW1", "LED3", "LED4"],
             "z_top": p.Z_tube_top,
             "note": "only SW1 (inside the bore, r <= tube_id_up/2) and the two ring LEDs "
                     "(on the tube wall) may sit inside this circle on the bottom side"},
        ],
        "trough_y": [-(p.inner_half - p.ledge_w) + 0.15, p.inner_half - p.ledge_w - 0.15],
        "trough_exceptions": [
            {"what": "USB-C (no ledge)", "x0": p.minusY_open[0][0], "x1": p.minusY_open[0][1], "side": "-Y"},
            {"what": "laser (no ledge)", "x0": p.X_pcb0 - 1, "x1": p.las_keepout_x, "side": "+Y"},
        ],
        "rf_window": {"x0": p.rfw_box[0], "x1": p.rfw_box[1], "half_y": p.rfw_box[2]},
        "max_height_top": p.Z_lid - zt - 0.2,
        "max_height_bottom": zb - p.floor - 0.3,
        "led_wire_top": {"y": p.Y_w, "z": p.Z_axis + p.led_wire_dz},
        "led_wire_bottom": {"y": p.Y_w, "z": p.Z_axis - p.led_wire_dz},
        "front_screw_tips_z": p.Z_lid - p.m16_drill,
    }


# --------------------------------------------------------------------------
# stand-ins for bought parts (fit check + pictures)
# --------------------------------------------------------------------------
def build_dummies(p: P):
    d = {}
    zt, zb = p.Z_pcb_top, p.Z_pcb_bot
    pts = pcb_outline(p)
    d["pcb"] = cq.Workplane("XY").workplane(offset=zb).polyline(pts).close().extrude(p.pcb_t)
    # module (on top), antenna overhang included
    x0m = p.X_pcb1 - p.mod_onboard
    d["module"] = rbox(x0m, p.X_ant1, p.mod_y - p.mod_w / 2, p.mod_y + p.mod_w / 2,
                       zt, zt + 0.8)
    d["module_can"] = rbox(x0m + 0.4, p.X_pcb1 - 0.2, p.mod_y - p.mod_w / 2 + 0.3,
                           p.mod_y + p.mod_w / 2 - 0.3, zt + 0.8, zt + p.mod_h)
    # two pouch cells stacked, PCM end towards the PCB
    for i in range(2):
        z0 = p.floor + 0.1 + i * (p.cell_t + 0.05)
        d[f"cell{i + 1}"] = rbox(p.X_batt0 + 0.3, p.X_batt0 + 0.3 + p.cell_l,
                                 -p.cell_w / 2, p.cell_w / 2, z0, z0 + p.cell_t, 1.0, axis="X")
    # window, DTP board + LED
    d["window"] = cyl_x(p.Y_w, p.Z_axis, p.win_d, p.win_recess, p.win_recess + p.win_t)
    xb = p.x_led_board
    d["mcpcb"] = cyl_x(p.Y_w, p.Z_axis, p.mcpcb_d, xb, xb + p.mcpcb_t)
    led = rbox(xb - 0.7, xb, p.Y_w - 1.725, p.Y_w + 1.725, p.Z_axis - 1.725, p.Z_axis + 1.725)
    dome = (cq.Workplane("YZ").workplane(offset=xb - 0.7).center(p.Y_w, p.Z_axis).sphere(1.45))
    dome = dome.intersect(rbox(xb - p.led_h, xb - 0.7, -20, 20, -20, 40))
    d["led"] = led.union(dome)
    d["laser"] = cyl_x(p.Y_l, p.Z_las, p.las_d, p.las_recess, p.las_recess + p.las_len)
    # USB-C receptacle (8.94 x 7.35 x 3.21), bottom side, face flush with the PCB edge
    yf = -p.Y_pcb
    d["usb"] = rbox(p.X_usb - 4.47, p.X_usb + 4.47, yf, yf + 7.35, zb - 3.21, zb, 1.2, axis="Y")
    # three top-push switches on the bottom side: body 2.9 (X) x 3.9 (Y) x 1.6, round actuator
    # d 1.9 to the full height sw_h (Alps SKRK: 3.9 x 2.9 x 2.0 overall)
    bx, by = p.sw_body
    for nm, x, rot in (("sw1", p.X_main, 90), ("sw2", p.X_next, 0), ("sw3", p.X_prev, 90)):
        hx, hy = (bx / 2, by / 2) if rot == 0 else (by / 2, bx / 2)
        d[nm] = rbox(x - hx, x + hx, p.btn_y - hy, p.btn_y + hy, zb - 1.6, zb)
        d[nm + "_act"] = cyl_z(x, p.btn_y, 1.9, p.Z_sw_tip, zb - 1.6 + 0.01)
    # ring LEDs (1.0 x 1.0 x ring_led_h) on the bottom side
    for nm, x in (("led3", p.X_main - p.ring_led_r), ("led4", p.X_main + p.ring_led_r)):
        d[nm] = rbox(x - 0.5, x + 0.5, p.btn_y - 0.5, p.btn_y + 0.5, zb - p.ring_led_h, zb)
    # S2 (top side) body 6.7 x 2.6 x 1.4, knob 1.3 x 1.55 x 1.0 (+/- 0.75 travel)
    ytip2 = p.Y_pcb + p.s2_knob_out
    yb2 = ytip2 - p.s2_knob_len
    d["s2"] = rbox(p.X_s2 - 3.35, p.X_s2 + 3.35, yb2 - 2.6, yb2, zt, zt + 1.4)
    d["s2_knob"] = rbox(p.X_s2 - 1.4, p.X_s2 + 1.4, yb2, ytip2,
                        zt + p.s2_knob_z - 0.5, zt + p.s2_knob_z + 0.5)
    # tallest bottom part: inductor 4 x 4 x 2.0 (placed by the PCB generator; nominal spot)
    d["L1"] = rbox(11.0, 15.0, -1.5, 2.5, zt, zt + 2.0)
    return d


PCB_MOUNTED = ("pcb", "module", "module_can", "usb", "sw1", "sw1_act", "sw2", "sw2_act",
               "sw3", "sw3_act", "led3", "led4", "s2", "s2_knob", "L1")


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def _vol(a, b):
    try:
        return a.intersect(b).val().Volume()
    except Exception:
        return 0.0


def _dist(a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    d = BRepExtrema_DistShapeShape(a, b)
    d.Perform()
    return d.Value()


def interference(parts, dummies, dy=0.0):
    out = []
    for hn, h in parts.items():
        for dn, dm in dummies.items():
            moved = dm.translate((0, dy, 0)) if dn in PCB_MOUNTED and dy else dm
            v = _vol(h, moved)
            if v > 0.02:   # below 0.02 mm3 = boolean noise at rounded edges
                out.append((hn, dn, round(v, 3)))
    return out


def parts_interference(parts):
    """Overlap volume (mm3) between every pair of housing parts in place."""
    out, names = [], list(parts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = _vol(parts[a], parts[b])
            if v > 0.02:
                out.append((a, b, round(v, 3)))
    return out


def housing_parts(p: P):
    """All housing parts in place (caps at rest)."""
    return {
        "FlashKa_tray": build_tray(p),
        "FlashKa_lid": build_lid(p),
        "FlashKa_rf_window": build_rf_window(p),
        "FlashKa_tube": build_tube(p),
        "FlashKa_cap_main": build_cap_main(p),
        "FlashKa_cap_slide": build_cap_slide(p, p.X_next),
        "FlashKa_cap_slide_prev": build_cap_slide(p, p.X_prev),
        "FlashKa_spacer_ring": build_spacer_ring(p),
        "FlashKa_antenna_spacer": build_antenna_spacer(p),
    }


def insertion_check(p: P, parts, dummies, steps=12):
    """Assembly: the PCB goes in tilted about the X axis (+Y edge low) so the
    S2 knob enters its slot first, then the -Y side is lowered. Every pose is
    checked against the tray, the glued tube, the three resting caps (all fitted before the board) and the laser."""
    from OCP.gp import gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    pivot = (0.0, p.Y_pcb + p.s2_knob_out - 0.2, p.Z_pcb_top + p.s2_knob_z)
    against = {"tray": parts["FlashKa_tray"], "tube": parts["FlashKa_tube"],
               "cap_main": parts["FlashKa_cap_main"], "cap_next": parts["FlashKa_cap_slide"],
               "cap_prev": parts["FlashKa_cap_slide_prev"], "laser": dummies["laser"]}
    worst = []
    for k in range(steps + 1):
        ang = 9.0 * (1 - k / steps)                 # 9 deg -> 0 deg
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(*pivot), gp_Dir(1, 0, 0)), math.radians(-ang))
        for dn in PCB_MOUNTED:
            s = dummies[dn].val().wrapped
            m = cq.Workplane().add(cq.Shape.cast(BRepBuilderAPI_Transform(s, tr, True).Shape()))
            for hn, h in against.items():
                v = _vol(h, m)
                if v > 2e-3:
                    worst.append((round(ang, 2), dn, hn, round(v, 3)))
    return worst


def cap_stroke_check(p: P, parts, dummies, travel=None):
    """Press each cap up (+Z) with the PCB at -0.25 / 0 / +0.25 mm in Y: the stem must only reach its own
    switch actuator (never preloaded at rest) and touch nothing else (tube, tray, board, other switches, LEDs)."""
    travel = p.sw_travel if travel is None else travel
    caps = (("main (SW1)", "FlashKa_cap_main", "sw1"), ("next (SW2)", "FlashKa_cap_slide", "sw2"),
            ("previous (SW3)", "FlashKa_cap_slide_prev", "sw3"))
    res = {}
    for cname, pn, sw in caps:
        for label, dy in (("PCB at -Y wall", -p.pcb_side_gap), ("PCB centred", 0.0), ("PCB at +Y wall", p.pcb_side_gap)):
            steps = [round(0.05 * k, 2) for k in range(0, int(round((p.cap_gap + travel) / 0.05)) + 1)]
            first_act, other, full = None, [], None
            for st in steps:
                cap = parts[pn].translate((0, 0, st))
                for dn in ("pcb", "sw1", "sw2", "sw3", "sw1_act", "sw2_act", "sw3_act", "led3", "led4", "usb"):
                    v = _vol(cap, dummies[dn].translate((0, dy, 0)))
                    if v > 1e-4:
                        if dn == sw + "_act":
                            first_act = st if first_act is None else first_act
                            full = st
                        else:
                            other.append((st, dn))
                for hn in ("FlashKa_tray", "FlashKa_tube"):
                    if _vol(cap, parts[hn]) > 1e-4:
                        other.append((st, hn))
            res[f"{cname} / {label}"] = {"free_play_mm": p.cap_gap,
                                         "actuator_reached_within_mm": first_act,
                                         "pressed_to_mm": full, "other_contacts": other[:5]}
    return res


def tolerance_stack(p: P):
    """Free play of a cap on its seat: nominal 0.30 mm; worst case and RSS of the stack in spec 2.1."""
    tol = {"resin tube step Z 2.4 / printed seat": 0.10, "switch height (actuator tip)": 0.10,
           "floor ledge / PCB ledge Z": 0.05, "cap length (turned)": 0.05}
    wc = sum(tol.values())
    rss = math.sqrt(sum(v * v for v in tol.values()))
    return {"nominal_free_play_mm": p.cap_gap, "items_mm": tol, "worst_case_min_mm": round(p.cap_gap - wc, 3),
            "worst_case_max_mm": round(p.cap_gap + wc, 3), "rss_min_mm": round(p.cap_gap - rss, 3),
            "preload_possible": (p.cap_gap - wc) < 0,
            "note": "main cap seat is the resin tube step (+/-0.10); slide caps sit on the floor face (+/-0.05, no resin step)"}


def holddown_report(p: P, e_scale=1.0, gap_extra=0.0, nx=88, ny=60, forces=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0)):
    """Two silicone pads (can: thermal pad, SW2: rubber sheet) press the PCB onto the ledges; a button pushes it up.
    Model: Mindlin plate (FR-4, 0.8 mm, E 20 GPa, 0.275 mm grid, free edges) on unilateral ledge supports (+Y ledge X >= las_keepout_x,
    -Y ledge X >= USB gap end; support line at the middle of the 0.55 mm overlap), pads = linear springs
    (E*A/t0, pre-compressed), S2 knob slot = rigid stop p.s2_stop_gap above the rest position.
    e_scale scales both pad moduli, gap_extra (mm) thickens both pad gaps (tolerance cases)."""
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    t, E, nu = p.pcb_t, p.pcb_E_mpa, p.pcb_nu
    Dm = E * t ** 3 / (12 * (1 - nu ** 2))
    Gs = 5.0 / 6.0 * E / (2 * (1 + nu)) * t
    Db = Dm * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])
    x0p, x1p, hy = p.X_pcb0, p.X_pcb1, p.Y_pcb if hasattr(p, "Y_pcb") else 8.25
    xs, ys = np.linspace(x0p, x1p, nx + 1), np.linspace(-hy, hy, ny + 1)
    hx, hyy = xs[1] - xs[0], ys[1] - ys[0]
    nid = lambda i, j: j * (nx + 1) + i
    N = (nx + 1) * (ny + 1)
    # element matrices (identical for all elements)
    gp_ = [-1 / math.sqrt(3), 1 / math.sqrt(3)]
    Ke = np.zeros((12, 12))
    for xi in gp_:
        for eta in gp_:
            Nn = 0.25 * np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta), (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)])
            dNx = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)]) * 2 / hx
            dNy = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]) * 2 / hyy
            Bb = np.zeros((3, 12))
            Bs = np.zeros((2, 12))
            for k in range(4):
                Bb[0, 3 * k + 1] = dNx[k]
                Bb[1, 3 * k + 2] = dNy[k]
                Bb[2, 3 * k + 1] = dNy[k]
                Bb[2, 3 * k + 2] = dNx[k]
                Bs[0, 3 * k] = dNx[k]
                Bs[0, 3 * k + 1] = -Nn[k]
                Bs[1, 3 * k] = dNy[k]
                Bs[1, 3 * k + 2] = -Nn[k]
            wgt = hx * hyy / 4
            Ke += wgt * (Bb.T @ Db @ Bb + Gs * Bs.T @ Bs)
    rows, cols, vals = [], [], []
    for j in range(ny):
        for i in range(nx):
            nn = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            dofs = np.array([3 * n + d for n in nn for d in range(3)])
            rows.append(np.repeat(dofs, 12))
            cols.append(np.tile(dofs, 12))
            vals.append(Ke.ravel())
    K0 = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(3 * N, 3 * N))
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.ravel(), Y.ravel()
    wdof = 3 * np.arange(N)

    # ledge supports
    yl = p.inner_half - p.ledge_w
    ysup = yl + 0.5 * (hy - yl)
    jp, jm = int(round((ysup + hy) / hyy)), int(round((-ysup + hy) / hyy))
    sup = [nid(i, jp) for i in range(nx + 1) if xs[i] >= p.las_keepout_x] + \
          [nid(i, jm) for i in range(nx + 1) if xs[i] >= p.minusY_open[0][1]]
    sup = np.array(sup)
    # pads
    def pad_nodes(box):
        bx0, bx1, by0, by1 = box
        m = np.where((X >= bx0 - 1e-9) & (X <= bx1 + 1e-9) & (Y >= by0 - 1e-9) & (Y <= by1 + 1e-9))[0]
        return m
    pads = []
    plist = [(p.boss_box, p.pad_t0, p.pad_E_mpa, p.pad_t, p.boss_r), (p.boss2_box, p.pad2_t0, p.pad2_E_mpa, p.pad2_t, p.boss2_r)]
    if p.boss3_box:
        plist.append((p.boss3_box, p.pad2_t0, p.pad2_E_mpa, p.Z_lid - p.boss3_h - p.Z_pcb_top, p.boss2_r))
    for box, t0_, E_, tl, r_ in plist:
        bx0, bx1, by0, by1 = box
        A_ = (bx1 - bx0) * (by1 - by0) - (4 - math.pi) * r_ ** 2
        nodes = pad_nodes(box)
        tl2 = tl + gap_extra
        d0 = t0_ - tl2                                   # pre-compression (mm)
        k_tot = E_ * e_scale * A_ / t0_                  # N/mm
        pads.append(dict(nodes=nodes, k=k_tot / len(nodes), d0=d0, A=A_, k_tot=k_tot, eps=d0 / t0_, box=box))
    s2n = nid(int(round((p.X_s2 - x0p) / hx)), jp)

    def solve(push_xy, F):
        f = np.zeros(3 * N)
        if F:
            m = np.where((abs(X - push_xy[0]) <= 1.0) & (abs(Y - push_xy[1]) <= 1.0))[0]
            f[3 * m] += F / len(m)
        act_l = np.ones(len(sup), bool)
        act_s = False
        w = np.zeros(N)
        for it in range(60):
            diag = np.zeros(3 * N)
            rhs = f.copy()
            kL = 1e5
            diag[3 * sup[act_l]] += kL
            for pd in pads:
                diag[3 * pd["nodes"]] += pd["k"]
                rhs[3 * pd["nodes"]] += -pd["k"] * pd["d0"]
            if act_s:
                diag[3 * s2n] += 1e5
                rhs[3 * s2n] += 1e5 * p.s2_stop_gap
            u = spl.spsolve((K0 + sp.diags(diag)).tocsc(), rhs)
            w = u[0::3]
            new_l = w[sup] < 0.0
            new_s = w[s2n] > p.s2_stop_gap
            if np.array_equal(new_l, act_l) and new_s == act_s:
                break
            act_l, act_s = new_l, new_s
        return w, int((~act_l).sum())

    def at(w, xy):
        m = np.where((abs(X - xy[0]) <= 0.4) & (abs(Y - xy[1]) <= 0.4))[0]
        return float(w[m].mean())

    w0, n0 = solve((0, 0), 0.0)
    out = {"model": ("Mindlin plate FR-4 0.8 mm, E %.0f MPa, nu %.2f, grid %.3f x %.3f mm, free edges; unilateral ledge supports "
                     "(+Y ledge X >= %.1f, -Y ledge X >= %.1f); pads = linear springs; S2 knob stop %.3f mm above rest"
                     % (E, nu, hx, hyy, p.las_keepout_x, p.minusY_open[0][1], p.s2_stop_gap)),
           "pad_E_scale": e_scale, "pad_gap_extra_mm": gap_extra}
    for key, pd, name, t0_, E_, tl in (("can", pads[0], "can pad (thermal pad)", p.pad_t0, p.pad_E_mpa, p.pad_t),
                                       ("sw2", pads[1], "SW2 pad (silicone rubber sheet)", p.pad2_t0, p.pad2_E_mpa, p.pad2_t)):
        out[key] = {"pad": name, "box_mm": list(pd["box"]), "area_mm2": round(pd["A"], 1),
                    "free_thickness_mm": t0_, "compressed_mm": round(t0_ - pd["d0"], 3),
                    "compression_pct": round(100 * pd["eps"], 1), "E_MPa": round(E_ * e_scale, 2),
                    "stiffness_N_per_mm": round(pd["k_tot"], 2), "preload_N": round(pd["k_tot"] * pd["d0"], 2)}
    out["rest_board_deflection_mm"] = round(float(w0.min()), 3)
    out["preload_total_N"] = round(sum(pd["k_tot"] * pd["d0"] for pd in pads), 2)
    out["preload_target_N"] = p.holddown_preload_n
    res = {}
    for nm, x in (("SW2 next", p.X_next), ("SW1 main", p.X_main), ("SW3 previous", p.X_prev)):
        xy = (x, p.btn_y)
        w_rest = at(w0, xy)
        lifts, off = {}, None
        for F in forces:
            wF, nl = solve(xy, F)
            lifts[F] = round(max(at(wF, xy) - w_rest, 0.0), 4)
            if off is None and nl - n0 >= 3:
                off = F
        res[nm] = {"displacement_3N_mm": lifts.get(3.0), "displacement_10N_mm": lifts.get(10.0),
                   "board_leaves_ledge_at_N": off if off else ">12"}
        out["buttons"] = res
    out["lift_limit_mm"] = 0.05
    out["no_lift_below_N"] = 3.0
    out["ok"] = all(v["displacement_10N_mm"] <= 0.05 and (v["board_leaves_ledge_at_N"] == ">12" or v["board_leaves_ledge_at_N"] > 3.0)
                    and v["displacement_3N_mm"] <= 0.02 for v in res.values())
    out["note"] = ("pad moduli are assumptions from the Shore hardness (Gent): thermal gap pad (Shore 00 70-80) %.1f MPa, "
                   "silicone rubber Shore A 70 %.1f MPa; PCB components add stiffness (ignored); J1 in the USB-C opening "
                   "is not a support" % (p.pad_E_mpa, p.pad2_E_mpa))
    return out


def min_wall_report(p: P):
    rb = (p.win_d + p.bore_clear) / 2
    rl = (p.las_d + p.las_clear) / 2
    gw, gd = p.wire_groove
    rep = {
        "window bore to control-side face": p.W / 2 - abs(p.Y_w) - rb,
        "window bore to top face (lid seat, X > lid_x0)": p.Z_lid - (p.Z_axis + rb),
        "window bore to bottom face": p.Z_axis - rb,
        "LED wire groove (top) to lid seat": p.Z_lid - (p.Z_axis + rb + gd - 0.2),
        "LED wire groove (bottom) to bottom face": p.Z_axis - rb - gd + 0.2,
        "laser bore to laser-side face": p.W / 2 - p.Y_l - rl,
        "laser bore to bottom face (M2 thread length)": p.Z_las - rl,
        "window bore to laser bore": (p.Y_l - p.Y_w) - rb - rl,
        "laser module top below the PCB": p.Z_pcb_bot - (p.Z_las + p.las_d / 2),
        "side walls": p.wall,
        "floor": p.floor,
        "lid": p.lid_t,
        "lid around the RF window flange pocket": p.lid_t - p.rfw_flange_t,
        "lanyard bridge (slot to tail face)": p.L - (p.X_lan + p.lan_slot_w / 2),
        "tail front wall (bay to slot)": p.tail_front_wall,
        "slot end to rear screw tap": p.screw_dy - p.m16_tap / 2 - p.lan_slot_len / 2,
        "front screw tap to head rear face": p.L_head - p.screw_x_front - p.m16_tap / 2,
        "front screw tap to LED bore floor": p.screw_x_front - p.m16_tap / 2 - p.D_w,
        "bottom long-edge corner (R_edge vs cavity corner, with the fillet)": p.R_edge - math.hypot(
            p.R_edge - p.wall, p.R_edge - p.floor) + p.cav_gusset / math.sqrt(2),
        "floor: main counterbore to slide hole": (p.X_prev - p.slide_hole / 2) - (p.X_main + (p.tube_rim[0] + 0.05) / 2),
        "floor: next hole to main counterbore": (p.X_main - (p.tube_rim[0] + 0.05) / 2) - (p.X_next + p.slide_hole / 2),
        "floor: previous hole to floor RF window": p.frw_box[0] - (p.X_prev + p.slide_hole / 2),
        "floor: counterbore ledge (radial, rim seat)": (p.tube_rim[0] + 0.05 - p.main_hole) / 2,
        "tube body to the +Y trough wall (gap, not a wall)": (p.inner_half - p.ledge_w) - (p.btn_y + p.tube_od / 2),
        "floor RF window to side wall": p.inner_half - p.frw_box[2],
        "lid lip thickness (side)": p.W / 2 - p.inner_half - p.lid_lip_gap,
    }
    rep.update(feature_walls(p))
    return {k: round(v, 3) for k, v in rep.items()}


def feature_walls(p: P):
    f = {
        "window bore": cyl_x(p.Y_w, p.Z_axis, p.win_d + p.bore_clear, -1, p.D_w),
        "laser bore": cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1,
                            p.las_recess + p.las_len + p.las_bore_extra),
        "M2 hole": cyl_z(p.las_grub_x, p.Y_l, p.m2_tap, -1, p.Z_las),
    }
    for i, (g, h) in enumerate(led_wire_paths(p)):
        f[f"LED wire hole {'top' if i == 0 else 'bottom'}"] = h
        f[f"LED wire groove {'top' if i == 0 else 'bottom'}"] = g
    for s, nm in ((1, "+Y"), (-1, "-Y")):
        f[f"front lid tap {nm}"] = cyl_z(p.screw_x_front, s * p.screw_dy, p.m16_tap,
                                         p.Z_lid - p.m16_drill, p.Z_lid)
        f[f"rear lid tap {nm}"] = cyl_z(p.X_screw_back, s * p.screw_dy, p.m16_tap,
                                        p.Z_lid - p.m16_drill, p.Z_lid)
    f["lanyard slot"] = (cq.Workplane("XY", origin=(0, 0, 0)).center(p.X_lan, 0)
                         .slot2D(p.lan_slot_len, p.lan_slot_w, 90).extrude(p.H))
    pairs = [("front lid tap -Y", "LED wire hole top"), ("front lid tap -Y", "window bore"),
             ("front lid tap +Y", "laser bore"), ("window bore", "laser bore"),
             ("M2 hole", "window bore"), ("LED wire hole bottom", "laser bore"),
             ("LED wire hole top", "laser bore"), ("rear lid tap +Y", "lanyard slot"),
             ("rear lid tap -Y", "lanyard slot")]
    out = {}
    for a, b in pairs:
        out[f"wall {a} - {b}"] = _dist(f[a].val().wrapped, f[b].val().wrapped)
    return out


def tray_voids(p: P):
    """Solids of every void and opening in the body (for the metal-under-groove and clearance checks)."""
    voids = {"cavity": cavity_solid(p).cut(lid_gussets(p)).val()}
    voids["window bore"] = cyl_x(p.Y_w, p.Z_axis, p.win_d + p.bore_clear, -1, p.D_w).val()
    voids["laser bore"] = cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1, p.las_recess + p.las_len + p.las_bore_extra).val()
    voids["M2 hole"] = cyl_z(p.las_grub_x, p.Y_l, p.m2_tap, -1, p.Z_las).val()
    for i, (g, h) in enumerate(led_wire_paths(p)):
        voids[f"LED wire hole {i}"] = h.val()
        voids[f"LED wire groove {i}"] = g.val()
    for i, h in enumerate(floor_hole_tools(p)):
        voids[f"floor hole {i}"] = h.val()
    w, h, r = p.usb_open
    voids["USB-C opening"] = slot_y(p.X_usb, p.Z_usb, w, h, r, -p.W / 2 - 1, -p.inner_half + 0.01).val()
    w, h, r = p.s2_slot
    voids["S2 slot"] = slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w, h, r, p.inner_half - 0.01, p.W / 2 + 1).val()
    for s in (-1, 1):
        for x in (p.screw_x_front, p.X_screw_back):
            voids[f"tap {x:g}/{s:+d}"] = cyl_z(x, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid).val()
            voids[f"csk {x:g}/{s:+d}"] = (cq.Workplane().add(cq.Solid.makeCone(p.m16_csk / 2, p.m16_clear / 2,
                                          (p.m16_csk - p.m16_clear) / 2, pnt=cq.Vector(x, s * p.screw_dy, p.H - (p.m16_csk - p.m16_clear) / 2),
                                          dir=cq.Vector(0, 0, 1))).val())
            voids[f"clear hole {x:g}/{s:+d}"] = cyl_z(x, s * p.screw_dy, p.m16_clear, p.Z_lid - 0.01, p.H + 0.5).val()
    voids["RF window opening"] = rf_window_outline(p, 0.0, p.Z_lid - 1, p.H + 1).val()
    voids["RF window pocket"] = rf_window_outline(p, p.rfw_flange, p.Z_lid - 1, p.Z_lid + p.rfw_flange_t).val()
    tt, lt = tail_tools(p)
    voids["tail window"] = tt[0].val()
    voids["lanyard slot"] = tt[1].val()
    return voids


def skin_report(p: P, voids=None):
    """Metal under every skin groove (apex line to any void) and the clearance of the cut groove to the openings."""
    voids = voids or tray_voids(p)
    openings = {k: v for k, v in voids.items() if k != "cavity" and not k.startswith(("tap", "LED wire", "M2", "laser", "window bore"))}
    env = envelope(p).val()
    allv = cq.Compound.makeCompound(list(voids.values())).wrapped
    opn = cq.Compound.makeCompound(list(openings.values())).wrapped
    rows = []
    for (nm, edge), (_, kind, tool) in zip(skin_apex_wires(p), skin_tools(p)):
        under = _dist(edge.wrapped, allv)
        try:
            cut = tool.intersect(env)
            clear = _dist(cut.wrapped, opn)
        except Exception:
            clear = float("nan")
        rows.append({"groove": nm, "metal_under_mm": round(under, 3), "clearance_to_openings_mm": round(clear, 3)})
    # the lid-front V-ring
    ring = seam_groove_cutter(p).intersect(envelope(p)).val()
    rows.append({"groove": "V-ring X%.2f" % (p.lid_x0 - p.seam_depth), "metal_under_mm": None,
                 "clearance_to_openings_mm": round(_dist(ring.wrapped, opn), 3)})
    return rows


# --------------------------------------------------------------------------
def export_parts(p: P, parts, extra, outdir):
    for n, s in list(parts.items()) + list(extra.items()):
        cq.exporters.export(s, os.path.join(outdir, n + ".step"))
        cq.exporters.export(s, os.path.join(outdir, n + ".stl"), tolerance=0.02, angularTolerance=0.1)


def main(outdir, full_checks=True):
    os.makedirs(outdir, exist_ok=True)
    p = P()
    parts = housing_parts(p)
    dummies = build_dummies(p)
    # standalone copies of the turned caps (axis through the origin) for the order files
    caps_origin = {
        "FlashKa_cap_main": build_cap_main(p).translate((-p.X_main, -p.btn_y, 0)),
        "FlashKa_cap_slide": build_cap_slide(p, p.X_next).translate((-p.X_next, -p.btn_y, 0)),
    }
    resin = {"main": build_cap_main(p), "slide_next": build_cap_slide(p, p.X_next), "slide_prev": build_cap_slide(p, p.X_prev)}
    extra = {"FlashKa_laser_sleeve": build_laser_sleeve(p)}
    extra["FlashKa_print_kit"] = build_print_kit(p, [
        ("rf_window", parts["FlashKa_rf_window"]), ("spacer_ring", parts["FlashKa_spacer_ring"]),
        ("antenna_spacer", parts["FlashKa_antenna_spacer"]), ("tube", parts["FlashKa_tube"]),
        ("cap_main_resin", resin["main"]), ("cap_slide_resin_1", resin["slide_next"]),
        ("cap_slide_resin_2", resin["slide_prev"])])
    # STEP/STL: housing parts in place, caps at the origin (turned parts)
    place = {k: v for k, v in parts.items() if k not in ("FlashKa_cap_main", "FlashKa_cap_slide", "FlashKa_cap_slide_prev")}
    place.update(caps_origin)
    export_parts(p, place, extra, outdir)
    for n, s in dummies.items():
        cq.exporters.export(s, os.path.join(outdir, "_ref_" + n + ".stl"), tolerance=0.02, angularTolerance=0.1)
    ring = cq.Solid.makeTorus(12.0, 0.7, pnt=cq.Vector(p.X_lan + 11.75, 0, p.H / 2), dir=cq.Vector(0, 1, 0))
    cq.exporters.export(cq.Workplane().add(ring), os.path.join(outdir, "_ref_splitring.stl"),
                        tolerance=0.02, angularTolerance=0.1)
    heads = []
    for (x, y) in ((p.screw_x_front, -p.screw_dy), (p.screw_x_front, p.screw_dy),
                   (p.X_screw_back, -p.screw_dy), (p.X_screw_back, p.screw_dy)):
        cone = cq.Solid.makeCone(0.8, 1.5, 0.7, pnt=cq.Vector(x, y, p.H - 0.7))
        shank = cq.Solid.makeCylinder(0.8, 3.3, pnt=cq.Vector(x, y, p.H - 4.0))
        slot = cq.Solid.makeBox(2.4, 0.45, 0.5, pnt=cq.Vector(x - 1.2, y - 0.225, p.H - 0.45))
        slot2 = cq.Solid.makeBox(0.45, 2.4, 0.5, pnt=cq.Vector(x - 0.225, y - 1.2, p.H - 0.45))
        heads.append(cone.fuse(shank).cut(slot).cut(slot2))
    cq.exporters.export(cq.Workplane().add(cq.Compound.makeCompound(heads)),
                        os.path.join(outdir, "_ref_lidscrews.stl"), tolerance=0.01, angularTolerance=0.1)
    # the boss pad (silicone) as a reference solid for the renders / assembly
    x0, x1, y0, y1 = p.boss_box
    pad = rrect_z(x0, x1, y0, y1, p.can_top_z, p.Z_lid - p.boss_h, p.boss_r)
    cq.exporters.export(pad, os.path.join(outdir, "_ref_pad.stl"), tolerance=0.02, angularTolerance=0.1)
    x0, x1, y0, y1 = p.boss2_box
    pad2 = rrect_z(x0, x1, y0, y1, p.Z_pcb_top, p.Z_lid - p.boss2_h, p.boss2_r)
    cq.exporters.export(pad2, os.path.join(outdir, "_ref_pad2.stl"), tolerance=0.02, angularTolerance=0.1)

    vols = {n: round(s.val().Volume(), 1) for n, s in parts.items()}
    bb = parts["FlashKa_tray"].val().BoundingBox()
    valid = {n: s.val().isValid() for n, s in list(parts.items()) + list(extra.items()) + list(caps_origin.items())}
    rim = p.screw_dy + p.m16_csk / 2 - (p.W / 2 - p.R_edge)
    dens = {"FlashKa_tray": 2.70e-3, "FlashKa_lid": 2.70e-3, "FlashKa_rf_window": 1.15e-3,
            "FlashKa_tube": 1.15e-3, "FlashKa_cap_main": 7.93e-3, "FlashKa_cap_slide": 7.93e-3,
            "FlashKa_cap_slide_prev": 7.93e-3, "FlashKa_spacer_ring": 1.15e-3, "FlashKa_antenna_spacer": 1.15e-3}
    info = {
        "version": "0.6",
        "params": {k: v for k, v in asdict(p).items()},
        "derived": {"L": p.L, "L_total": p.L_total, "Z_lid": p.Z_lid, "Z_pcb_top": p.Z_pcb_top,
                    "D_w": p.D_w, "X_pcb0": p.X_pcb0, "X_pcb1": p.X_pcb1, "X_ant1": p.X_ant1,
                    "Y_pcb": p.Y_pcb, "X_batt0": p.X_batt0, "X_batt1": p.X_batt1,
                    "X_lan": p.X_lan, "X_screw_front": p.screw_x_front,
                    "X_screw_back": p.X_screw_back, "Z_usb": p.Z_usb,
                    "Z_sw_tip": p.Z_sw_tip, "Z_tube_top": p.Z_tube_top, "pad_t": p.pad_t,
                    "rf_window": p.rfw_box},
        "pcb_outline": pcb_outline(p),
        "components": component_positions(p),
        "volumes_mm3": vols,
        "mass_g": {n: round(v * dens[n], 2) for n, v in vols.items()},
        "tray_bbox": [bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax],
        "solids_valid": valid,
        "min_walls": min_wall_report(p),
        "countersink_rim_past_flat_top_mm": round(rim, 3),
        "skin_layout": [{k: (list(v) if isinstance(v, tuple) else v) for k, v in it.items()} for it in skin_layout(p)],
        "interference_pcb_centred": interference(parts, dummies),
        "interference_pcb_at_-Y": interference(parts, dummies, -p.pcb_side_gap + 0.01),
        "interference_pcb_at_+Y": interference(parts, dummies, p.pcb_side_gap - 0.01),
    }
    if full_checks:
        voids = tray_voids(p)
        sk = skin_report(p, voids)
        info["skin_walls"] = sk
        info["skin_min_metal_under_mm"] = min(r["metal_under_mm"] for r in sk if r["metal_under_mm"] is not None)
        info["skin_min_clearance_to_openings_mm"] = min(r["clearance_to_openings_mm"] for r in sk)
        info["insertion_path"] = insertion_check(p, parts, dummies)
        info["cap_stroke"] = cap_stroke_check(p, parts, dummies)
        info["interference_part_to_part"] = parts_interference(parts)
        info["cap_tolerance_stack"] = tolerance_stack(p)
        info["led_to_tube_gap_mm"] = {
            "LED3": round(_dist(dummies["led3"].val().wrapped, parts["FlashKa_tube"].val().wrapped), 3),
            "LED4": round(_dist(dummies["led4"].val().wrapped, parts["FlashKa_tube"].val().wrapped), 3),
            "SW1 body to tube bore": round(_dist(dummies["sw1"].val().wrapped, parts["FlashKa_tube"].val().wrapped), 3),
            "tube top to PCB": round(p.Z_pcb_bot - p.Z_tube_top, 3)}
        info["holddown"] = holddown_report(p, forces=(1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0))
        info["holddown_soft_case"] = holddown_report(p, e_scale=0.7, gap_extra=0.1, forces=(3.0, 10.0))
        info["holddown_hard_case"] = holddown_report(p, e_scale=1.3, gap_extra=-0.1, forces=(3.0, 10.0))
    path = os.path.join(outdir, "housing_interface.json")
    if os.path.exists(path):      # the PCB builds from "components" / "pcb_outline": never touch them
        old = json.load(open(path))
        for k in ("components", "pcb_outline"):
            if k in old and json.loads(json.dumps(old[k])) != json.loads(json.dumps(info[k], default=str)):
                print("WARNING: %s differs from the file; the file's value is kept" % k)
                info[k] = old[k]
    with open(path, "w") as f:
        json.dump(info, f, indent=1, default=str)
    return p, parts, dummies, info


def interface_only(outdir):
    """Write housing_interface.json without building the solids (fast path for
    PCB iterations); the full run adds volumes and all checks."""
    os.makedirs(outdir, exist_ok=True)
    p = P()
    path = os.path.join(outdir, "housing_interface.json")
    info = json.load(open(path)) if os.path.exists(path) else {}
    info.update({"version": "0.6", "params": {k: v for k, v in asdict(p).items()},
                 "derived": {"L": p.L, "Z_lid": p.Z_lid, "Z_pcb_top": p.Z_pcb_top,
                             "X_pcb0": p.X_pcb0, "X_pcb1": p.X_pcb1, "X_ant1": p.X_ant1,
                             "Y_pcb": p.Y_pcb, "X_batt0": p.X_batt0, "X_batt1": p.X_batt1,
                             "Z_sw_tip": p.Z_sw_tip, "Z_tube_top": p.Z_tube_top,
                             "Z_usb": p.Z_usb, "rf_window": p.rfw_box},
                 "pcb_outline": pcb_outline(p), "components": component_positions(p)})
    with open(path, "w") as f:
        json.dump(info, f, indent=1)
    return p


if __name__ == "__main__":
    if "--interface-only" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        p = interface_only(args[0] if args else "cad")
        print("interface written, L =", round(p.L, 2))
        sys.exit(0)
    out = sys.argv[1] if len(sys.argv) > 1 else "cad"
    fast = "--no-checks" in sys.argv
    out = [a for a in sys.argv[1:] if not a.startswith("--")] or ["cad"]
    p, parts, dummies, info = main(out[0], full_checks=not fast)
    print("L =", round(p.L, 2), " PCB X", round(p.X_pcb0, 2), "-", round(p.X_pcb1, 2),
          " antenna to", round(p.X_ant1, 2), " bay", round(p.X_batt0, 2), "-", round(p.X_batt1, 2),
          " slot X", round(p.X_lan, 2))
    print("valid", info["solids_valid"])
    print("mass", info["mass_g"])
    print("walls", json.dumps(info["min_walls"], indent=1))
    for k in ("skin_min_metal_under_mm", "skin_min_clearance_to_openings_mm", "interference_pcb_centred",
              "interference_pcb_at_-Y", "interference_pcb_at_+Y", "interference_part_to_part", "insertion_path", "led_to_tube_gap_mm",
              "cap_tolerance_stack", "holddown", "holddown_soft_case", "holddown_hard_case"):
        if k in info:
            print(k, json.dumps(info[k], indent=1, default=str))
    for k, v in info.get("cap_stroke", {}).items():
        print("cap_stroke", k, v)
