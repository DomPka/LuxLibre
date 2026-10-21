#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Aurora++ keychain flashlight - parametric aluminium housing (v0.5)

One source of truth for the mechanics: every dimension lives in the
parameter class P below.  The script builds

  tray            - main body, 6061-T6: head block, PCB zone, antenna zone,
                    battery bay and the compact tail with the lanyard slot
  lid             - top cover, 6061-T6, 4x M1.6 countersunk screws, with the
                    stepped opening for the plastic RF window
  rf_window       - plastic insert in the lid above the Bluetooth antenna
                    (translucent resin: the RGB status LED shines through it)
  button_cap      - plunger for the side switch S1 (resin or 6061)
  spacer_ring     - sets the window height above the LED (resin)
  antenna_spacer  - keeps the cells off the module's antenna (resin)

v0.5 against v0.4: 20 x 16 mm section (was 24 x 14); SST-20 on a ready-made
10 mm DTP board behind a 10 mm window; ESP32-C3 module with its antenna over
an empty zone under a plastic window in the lid; the lid runs from the head
block to the tail (front screws in the head block, rear screws beside the
lanyard slot); two 601646 pouch cells in parallel; compact 7.4 mm tail.

Coordinate system (all mm):
  X = 0 at the front face (light exits towards -X), +X towards the tail
  Y = 0 on the centre line, -Y = control side (USB-C, button S1),
  +Y = laser side (laser interlock S2)
  Z = 0 on the bottom face, +Z towards the lid

Run:  python3 aurora_housing.py [outdir]
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

    # tactile exterior - all 90 deg V-grooves (one chamfer / engraving cutter)
    knurl: bool = True
    knurl_x0: float = 40.5       # lid: clear of the RF window pocket (ends at X 39.5)
    knurl_x1: float = 81.5
    knurl_w: float = 12.4
    knurl_r: float = 2.0
    knurl_pitch: float = 1.6
    knurl_depth: float = 0.35
    sgroove_x0: float = 40.5
    sgroove_x1: float = 81.5
    sgroove_z: tuple = (5.5, 10.5)
    sgroove_depth: float = 0.3
    seam_depth: float = 0.25      # V ring around the body at the lid's front edge
    dish_r: float = 8.0          # thumb dish around S1
    dish_depth: float = 0.6

    # screws / threads
    m16_tap: float = 1.25
    m16_drill: float = 3.6
    m16_clear: float = 1.8
    m16_csk: float = 3.3
    screw_dy: float = 6.3        # all four lid screws (countersink stays on the flat top)
    screw_x_front: float = 7.0   # in the head block
    m2_tap: float = 1.6

    # control side (-Y): USB-C and S1 both on the bottom side of the PCB
    X_usb: float = 14.6
    usb_open: tuple = (12.6, 6.8, 2.0)   # one opening through the wall (overmold size)
    usb_open_chamfer: float = 0.3
    X_s1: float = 25.6
    s1_hole: tuple = (3.4, 2.4, 0.8)
    s1_act_z: float = 1.25               # actuator centre below the PCB bottom (Alps SKRTLAE010)
    s1_act_prot: float = 0.83            # actuator protrusion beyond the body
    s1_gap: float = 0.35                 # actuator tip -> cap flange, PCB centred
    cap_flange: tuple = (5.2, 2.1, 0.6)
    cap_protrude: float = 1.0
    # laser side (+Y): S2 interlock slide (top side of the PCB), knob into the wall
    X_s2: float = 14.05                  # front mounting pads >= 0.2 mm inside the PCB chamfer
    s2_slot: tuple = (3.2, 2.0, 0.8)
    s2_knob_z: float = 0.7
    s2_knob_len: float = 1.55
    s2_knob_out: float = 0.75            # knob tip beyond the PCB edge (tilt-in assembly)

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
    def Z_s1(self):            # S1 hangs under the PCB (bottom side)
        return self.Z_pcb_bot - self.s1_act_z

    @property
    def s1_tip_y(self):         # S1 actuator tip (PCB centred)
        return -self.inner_half + self.cap_flange[2] + self.s1_gap

    @property
    def Z_usb(self):            # receptacle centre (bottom side, 3.21 tall)
        return self.Z_pcb_bot - 3.21 / 2

    @property
    def minusY_open(self):     # X ranges without the -Y ledge (USB-C, S1)
        return ((self.X_usb - 4.9, self.X_usb + 5.0), (self.X_s1 - 3.2, self.X_s1 + 3.2))

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


def _rrect_sdf(cx, cy, hx, hy, r):
    def f(x, y):
        qx = abs(x - cx) - (hx - r)
        qy = abs(y - cy) - (hy - r)
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
    return f


def _chord(f, px, py, gx, gy, span=60.0):
    def h(t):
        return f(px + gx * t, py + gy * t)
    lo, hi = -span, span
    for _ in range(120):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if h(m1) < h(m2):
            hi = m2
        else:
            lo = m1
    tm = 0.5 * (lo + hi)
    if h(tm) >= 0:
        return None

    def root(a, b):
        for _ in range(80):
            m = 0.5 * (a + b)
            if h(m) < 0:
                a = m
            else:
                b = m
        return 0.5 * (a + b)
    return root(tm, -span), root(tm, span)


def knurl_frame_tool(p: P, face, ext=0.3):
    d, D = p.knurl_depth, p.knurl_depth + ext
    cx, L, w, r = 0.5 * (p.knurl_x0 + p.knurl_x1), p.knurl_x1 - p.knurl_x0, p.knurl_w, p.knurl_r

    def rr(off):
        return (cq.Workplane("XY", origin=(0, 0, -ext)).center(cx, 0).sketch()
                .rect(L + 2 * off, w + 2 * off).vertices().fillet(r + off).finalize())
    outer = rr(D).extrude(D, taper=45)
    inner = rr(-D).extrude(D, taper=-45)
    frame = outer.cut(inner)
    if face == "top":
        frame = frame.mirror("XY", basePointVector=(0, 0, p.H / 2))
    return frame.val()


def knurl_tools(p: P, face):
    d = p.knurl_depth
    x0, x1, w, r = p.knurl_x0, p.knurl_x1, p.knurl_w, p.knurl_r
    cx = 0.5 * (x0 + x1)
    sh = 0.15
    f = _rrect_sdf(cx, 0.0, 0.5 * (x1 - x0) - sh, 0.5 * w - sh, max(r - sh, 0.0))
    s = p.knurl_pitch * math.sqrt(2)
    za, n_in = (d, (0, 0, 1)) if face == "bottom" else (p.H - d, (0, 0, -1))
    tools = []
    kmax = int((0.5 * (x1 - x0) + 0.5 * w) / s) + 2
    for sg in (1, -1):
        gx, gy = 1 / math.sqrt(2), sg / math.sqrt(2)
        for k in range(-kmax, kmax + 1):
            px = cx + k * s
            c = _chord(f, px, 0.0, gx, gy)
            if c is None or c[1] - c[0] < 0.3:
                continue
            tools.append(vgroove((px + gx * c[0], gy * c[0], za),
                                 (px + gx * c[1], gy * c[1], za), n_in, d))
    return [knurl_frame_tool(p, face)] + tools


def side_groove_tools(p: P):
    d = p.sgroove_depth
    tools = []
    for s in (-1, 1):
        y = s * (p.W / 2 - d)
        for z in p.sgroove_z:
            tools.append(vgroove((p.sgroove_x0 + d, y, z), (p.sgroove_x1 - d, y, z),
                                 (0, -s, 0), d))
    return tools


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


def thumb_dish_tool(p: P):
    yc = -p.W / 2 - p.dish_r + p.dish_depth
    # full sphere (makeSphere defaults to a hemisphere: angleDegrees1 = 0)
    return cq.Solid.makeSphere(p.dish_r, cq.Vector(p.X_s1, yc, p.Z_s1), angleDegrees1=-90)


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


def lid_region(p: P):
    return rbox(p.lid_x0, p.L + 1, -p.W, p.W, p.Z_lid, p.H + 1)


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


def cavity_solid(p: P):
    """The milled interior: upper level full width (PCB zone to bay end), a
    trough between the ledges under the PCB, full width in the antenna zone
    and the bay, plus the ledge interruptions (USB-C, laser tail)."""
    ih, r = p.inner_half, p.inner_r
    c = rbox(p.L_head, p.X_batt1, -ih, ih, p.Z_pcb_bot, p.Z_lid + 0.01, r)
    c = c.union(rbox(p.L_head, p.X_pcb1 + 0.5, -(ih - p.ledge_w), ih - p.ledge_w,
                     p.floor, p.Z_pcb_bot + 0.01, r))
    c = c.union(rbox(p.X_pcb1, p.X_batt1, -ih, ih, p.floor, p.Z_pcb_bot + 0.01, r))
    # USB-C and S1 hang under the -Y edge: no ledge there
    for (xa, xb) in p.minusY_open:
        c = c.union(rbox(xa, xb, -ih, -(ih - p.ledge_w) + 1.0, p.floor, p.Z_pcb_bot + 0.01, 0.6))
    # laser module tail at +Y: no ledge in front of las_keepout_x
    c = c.union(rbox(p.L_head, p.las_keepout_x, ih - p.ledge_w - 1.0, ih,
                     p.floor, p.Z_pcb_bot + 0.01, 0.6))
    return c


def build_tray(p: P, texture=None):
    if texture is None:
        texture = p.knurl
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

    # --- control side (-Y): USB-C opening (through), S1 cap hole
    yo = -p.W / 2
    w, h, r = p.usb_open
    t = t.cut(slot_y(p.X_usb, p.Z_usb, w, h, r, yo - 1, -ih + 0.01))
    # 45 deg chamfer on the outer edge of the opening (drafted band)
    c = p.usb_open_chamfer
    band = (cq.Workplane("XZ", origin=(0, yo + c, 0)).center(p.X_usb, p.Z_usb).sketch()
            .rect(w, h).vertices().fillet(r).finalize().extrude(c + 0.3, taper=-45))
    t = t.cut(band)
    w, h, r = p.s1_hole
    t = t.cut(slot_y(p.X_s1, p.Z_s1, w, h, r, yo - 1, -ih + 0.01))
    # --- laser side (+Y): S2 slot
    w, h, r = p.s2_slot
    t = t.cut(slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w, h, r, ih - 0.01, p.W / 2 + 1))

    # --- exterior: V-ring at the lid front edge, tail, thumb dish, grooves, knurl
    t = t.cut(seam_groove_cutter(p))
    tray_tail, _ = tail_tools(p)
    for c_ in tray_tail:
        t = t.cut(c_)
    tools = [thumb_dish_tool(p)] + side_groove_tools(p)
    if texture:
        tools += knurl_tools(p, "bottom")
    t = cq.Workplane().add(t.val().cut(*tools))
    return t


def rf_window_outline(p: P, grow=0.0, z0=0.0, z1=1.0):
    x0, x1, hy = p.rfw_box
    return rrect_z(x0 - grow, x1 + grow, -hy - grow, hy + grow, z0, z1, p.rfw_r + grow)


def build_lid(p: P, texture=None):
    if texture is None:
        texture = p.knurl
    lid = envelope(p).intersect(lid_region(p))
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
    if texture:
        lid = cq.Workplane().add(lid.val().cut(*knurl_tools(p, "top")))
    return lid


def build_rf_window(p: P):
    """Stepped plastic insert: plug in the opening (flush with the lid top),
    flange in the underside pocket. Glue in from inside (epoxy)."""
    c = p.rfw_clear
    plug = rf_window_outline(p, -c, p.Z_lid + p.rfw_flange_t - 0.01, p.H)
    flange = rf_window_outline(p, p.rfw_flange - c, p.Z_lid - p.rfw_flange_drop, p.Z_lid + p.rfw_flange_t)
    w = plug.union(flange)
    return w


def build_button_cap(p: P):
    """Plunger for S1, modelled in place in the -Y wall (flange inside)."""
    hw, hh, hr = p.s1_hole
    cw, ch = hw - 0.2, hh - 0.2
    y_in = -p.inner_half
    fw, fh, ft = p.cap_flange
    plunger = slot_y(p.X_s1, p.Z_s1, cw, ch, hr - 0.1, -p.W / 2 - p.cap_protrude, y_in + 0.01)
    plunger = plunger.faces("<Y").edges().fillet(0.3)
    flange = slot_y(p.X_s1, p.Z_s1, fw, fh, 0.6, y_in, y_in + ft)
    return plunger.union(flange)


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
    the cell wires pass through the notch at +Y."""
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
    body = body.cut(rbox(x0 - 1, x1 + 1, ih - 1.6, ih + 1, p.floor, p.floor + 2.2))
    return body


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
        "S1_button": {"x": p.X_s1, "actuator_tip_y": p.s1_tip_y, "side": "B",
                      "z_actuator": p.Z_s1, "note": "side push, actuator towards -Y"},
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
        "trough_y": [-(p.inner_half - p.ledge_w) + 0.15, p.inner_half - p.ledge_w - 0.15],
        "trough_exceptions": [
            {"what": "USB-C (no ledge)", "x0": p.minusY_open[0][0], "x1": p.minusY_open[0][1], "side": "-Y"},
            {"what": "S1 (no ledge)", "x0": p.minusY_open[1][0], "x1": p.minusY_open[1][1], "side": "-Y"},
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
    # S1 (bottom side) 4.5 x 2.56 x 2.5 + actuator 2.0 x 0.83 x 1.5
    ytip = p.s1_tip_y
    yb = ytip + p.s1_act_prot
    d["s1"] = rbox(p.X_s1 - 2.25, p.X_s1 + 2.25, yb, yb + 2.56, zb - 2.5, zb)
    d["s1_act"] = rbox(p.X_s1 - 1.0, p.X_s1 + 1.0, ytip, yb,
                       zb - p.s1_act_z - 0.75, zb - p.s1_act_z + 0.75)
    # S2 (top side) body 6.7 x 2.6 x 1.4, knob 1.3 x 1.55 x 1.0 (+/- 0.75 travel)
    ytip2 = p.Y_pcb + p.s2_knob_out
    yb2 = ytip2 - p.s2_knob_len
    d["s2"] = rbox(p.X_s2 - 3.35, p.X_s2 + 3.35, yb2 - 2.6, yb2, zt, zt + 1.4)
    d["s2_knob"] = rbox(p.X_s2 - 1.4, p.X_s2 + 1.4, yb2, ytip2,
                        zt + p.s2_knob_z - 0.5, zt + p.s2_knob_z + 0.5)
    # tallest bottom part: inductor 4 x 4 x 2.0 (placed by the PCB generator; nominal spot)
    d["L1"] = rbox(11.0, 15.0, -1.5, 2.5, zt, zt + 2.0)
    return d


PCB_MOUNTED = ("pcb", "module", "module_can", "usb", "s1", "s1_act", "s2", "s2_knob", "L1")


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def _vol(a, b):
    try:
        return a.intersect(b).val().Volume()
    except Exception:
        return 0.0


def interference(parts, dummies, dy=0.0):
    out = []
    for hn, h in parts.items():
        for dn, dm in dummies.items():
            moved = dm.translate((0, dy, 0)) if dn in PCB_MOUNTED and dy else dm
            v = _vol(h, moved)
            if v > 1e-3:
                out.append((hn, dn, round(v, 3)))
    return out


def insertion_check(p: P, parts, dummies, steps=12):
    """Assembly: the PCB goes in tilted about the X axis (+Y edge low) so the
    S2 knob enters its slot first, then the -Y side is lowered. Every pose is
    checked against the tray and the button cap (laser fitted)."""
    from OCP.gp import gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    ih = p.inner_half
    pivot = (0.0, p.Y_pcb + p.s2_knob_out - 0.2, p.Z_pcb_top + p.s2_knob_z)
    against = {"tray": parts["Aurora_tray"], "cap": parts["Aurora_button_cap"],
               "laser": dummies["laser"]}
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


def cap_stroke_check(p: P, parts, dummies, travel=0.25):
    """Press the cap inwards (+Y) with the PCB at -0.25 / 0 / +0.25 mm: the cap
    must only reach the S1 actuator, never preloaded, never anything else."""
    res = {}
    for label, dy in (("PCB at -Y wall", -p.pcb_side_gap), ("PCB centred", 0.0),
                      ("PCB at +Y wall", p.pcb_side_gap)):
        gap = p.s1_gap + dy
        first_act, other = None, []
        steps = [round(0.05 * k, 2) for k in range(0, int((gap + travel) / 0.05) + 2)]
        for st in steps:
            cap = parts["Aurora_button_cap"].translate((0, st, 0))
            for dn in ("pcb", "s1", "s1_act", "module", "module_can"):
                v = _vol(cap, dummies[dn].translate((0, dy, 0)))
                if v > 1e-4:
                    if dn == "s1_act":
                        first_act = st if first_act is None else first_act
                    else:
                        other.append((st, dn))
        res[label] = {"free_gap_mm": round(gap, 2), "actuator_reached_at_mm": first_act,
                      "other_contacts": other[:5]}
    return res


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
        "floor under the knurl": p.floor - p.knurl_depth,
        "lid under the knurl": p.lid_t - p.knurl_depth,
        "side wall under the side grooves": p.wall - p.sgroove_depth,
        "lid around the RF window flange pocket": p.lid_t - p.rfw_flange_t,
        "lanyard bridge (slot to tail face)": p.L - (p.X_lan + p.lan_slot_w / 2),
        "tail front wall (bay to slot)": p.tail_front_wall,
        "slot end to rear screw tap": p.screw_dy - p.m16_tap / 2 - p.lan_slot_len / 2,
        "front screw tap to head rear face": p.L_head - p.screw_x_front - p.m16_tap / 2,
        "front screw tap to LED bore floor": p.screw_x_front - p.m16_tap / 2 - p.D_w,
        "bottom long-edge corner (R_edge vs cavity corner)": p.R_edge - math.hypot(
            p.R_edge - p.wall, p.R_edge - p.floor),
    }
    rep.update(feature_walls(p))
    return {k: round(v, 3) for k, v in rep.items()}


def feature_walls(p: P):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
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
        d = BRepExtrema_DistShapeShape(f[a].val().wrapped, f[b].val().wrapped)
        d.Perform()
        out[f"wall {a} - {b}"] = d.Value()
    return out


def texture_walls(p: P):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    def dist(a, b):
        d = BRepExtrema_DistShapeShape(a, b)
        d.Perform()
        return d.Value()
    cav = cavity_solid(p).val().wrapped
    out = {}
    out["knurl (bottom) to cavity"] = dist(cq.Compound.makeCompound(knurl_tools(p, "bottom")).wrapped, cav)
    out["side grooves to cavity"] = dist(cq.Compound.makeCompound(side_groove_tools(p)).wrapped, cav)
    ring = seam_groove_cutter(p).intersect(envelope(p)).val().wrapped
    holes = [h.val() for g, h in led_wire_paths(p)] + [g.val() for g, h in led_wire_paths(p)]
    holes += [cyl_x(p.Y_w, p.Z_axis, p.win_d + p.bore_clear, -1, p.D_w).val()]
    out["seam V-ring to window bore / wire grooves"] = dist(ring, cq.Compound.makeCompound(holes).wrapped)
    taps = cq.Compound.makeCompound([cyl_z(p.X_screw_back, s * p.screw_dy, p.m16_tap,
                                           p.Z_lid - p.m16_drill, p.Z_lid).val() for s in (-1, 1)]).wrapped
    tt, _ = tail_tools(p)
    win = cq.Compound.makeCompound([tt[0].val()]).wrapped
    out["tail bottom window to cavity"] = dist(win, cav)
    out["tail bottom window to rear lid taps"] = dist(win, taps)
    dish = thumb_dish_tool(p).intersect(envelope(p).val()).wrapped
    out["thumb dish to cavity"] = dist(dish, cav)
    return out


# --------------------------------------------------------------------------
def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    p = P()
    parts = {
        "Aurora_tray": build_tray(p),
        "Aurora_lid": build_lid(p),
        "Aurora_rf_window": build_rf_window(p),
        "Aurora_button_cap": build_button_cap(p),
        "Aurora_spacer_ring": build_spacer_ring(p),
        "Aurora_antenna_spacer": build_antenna_spacer(p),
    }
    dummies = build_dummies(p)
    extra = {"Aurora_laser_sleeve": build_laser_sleeve(p)}
    extra["Aurora_print_kit"] = build_print_kit(p, [
        ("rf_window", parts["Aurora_rf_window"]), ("button_cap", parts["Aurora_button_cap"]),
        ("spacer_ring", parts["Aurora_spacer_ring"]), ("antenna_spacer", parts["Aurora_antenna_spacer"])])
    for n, s in list(parts.items()) + list(extra.items()):
        cq.exporters.export(s, os.path.join(outdir, n + ".step"))
        cq.exporters.export(s, os.path.join(outdir, n + ".stl"), tolerance=0.02, angularTolerance=0.1)
    for n, s in dummies.items():
        cq.exporters.export(s, os.path.join(outdir, "_ref_" + n + ".stl"),
                            tolerance=0.02, angularTolerance=0.1)
    ring = cq.Solid.makeTorus(12.0, 0.7, pnt=cq.Vector(p.X_lan + 11.75, 0, p.H / 2),
                              dir=cq.Vector(0, 1, 0))
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

    vols = {n: round(s.val().Volume(), 1) for n, s in parts.items()}
    bb = parts["Aurora_tray"].val().BoundingBox()
    valid = {n: s.val().isValid() for n, s in list(parts.items()) + list(extra.items())}
    rim = p.screw_dy + p.m16_csk / 2 - (p.W / 2 - p.R_edge)
    dens = {"Aurora_tray": 2.70e-3, "Aurora_lid": 2.70e-3, "Aurora_rf_window": 1.15e-3,
            "Aurora_button_cap": 1.15e-3, "Aurora_spacer_ring": 1.15e-3,
            "Aurora_antenna_spacer": 1.15e-3}
    info = {
        "version": "0.5",
        "params": {k: v for k, v in asdict(p).items()},
        "derived": {"L": p.L, "L_total": p.L_total, "Z_lid": p.Z_lid, "Z_pcb_top": p.Z_pcb_top,
                    "D_w": p.D_w, "X_pcb0": p.X_pcb0, "X_pcb1": p.X_pcb1, "X_ant1": p.X_ant1,
                    "Y_pcb": p.Y_pcb, "X_batt0": p.X_batt0, "X_batt1": p.X_batt1,
                    "X_lan": p.X_lan, "X_screw_front": p.screw_x_front,
                    "X_screw_back": p.X_screw_back, "Z_s1": p.Z_s1, "Z_usb": p.Z_usb,
                    "rf_window": p.rfw_box},
        "pcb_outline": pcb_outline(p),
        "components": component_positions(p),
        "volumes_mm3": vols,
        "mass_g": {n: round(v * dens[n], 1) for n, v in vols.items()},
        "tray_bbox": [bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax],
        "solids_valid": valid,
        "min_walls": min_wall_report(p),
        "texture_walls": {k: round(v, 3) for k, v in texture_walls(p).items()},
        "countersink_rim_past_flat_top_mm": round(rim, 3),
        "interference_pcb_centred": interference(parts, dummies),
        "interference_pcb_at_-Y": interference(parts, dummies, -p.pcb_side_gap + 0.01),
        "interference_pcb_at_+Y": interference(parts, dummies, p.pcb_side_gap - 0.01),
        "insertion_path": insertion_check(p, parts, dummies),
        "button_cap_stroke": cap_stroke_check(p, parts, dummies),
    }
    with open(os.path.join(outdir, "housing_interface.json"), "w") as f:
        json.dump(info, f, indent=1)
    return p, parts, dummies, info


def interface_only(outdir):
    """Write housing_interface.json without building the solids (fast path for
    PCB iterations); the full run adds volumes and all checks."""
    os.makedirs(outdir, exist_ok=True)
    p = P()
    path = os.path.join(outdir, "housing_interface.json")
    info = json.load(open(path)) if os.path.exists(path) else {}
    info.update({"version": "0.5", "params": {k: v for k, v in asdict(p).items()},
                 "derived": {"L": p.L, "Z_lid": p.Z_lid, "Z_pcb_top": p.Z_pcb_top,
                             "X_pcb0": p.X_pcb0, "X_pcb1": p.X_pcb1, "X_ant1": p.X_ant1,
                             "Y_pcb": p.Y_pcb, "X_batt0": p.X_batt0, "X_batt1": p.X_batt1,
                             "Z_s1": p.Z_s1, "Z_usb": p.Z_usb, "rf_window": p.rfw_box},
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
    p, parts, dummies, info = main(out)
    print("L =", round(p.L, 2), " PCB X", round(p.X_pcb0, 2), "-", round(p.X_pcb1, 2),
          " antenna to", round(p.X_ant1, 2), " bay", round(p.X_batt0, 2), "-", round(p.X_batt1, 2),
          " slot X", round(p.X_lan, 2))
    print("valid", info["solids_valid"])
    print("mass", info["mass_g"])
    print("walls", json.dumps(info["min_walls"], indent=1))
    print("texture walls", json.dumps(info["texture_walls"], indent=1))
    for k in ("interference_pcb_centred", "interference_pcb_at_-Y", "interference_pcb_at_+Y",
              "insertion_path", "button_cap_stroke"):
        print(k, info[k])
