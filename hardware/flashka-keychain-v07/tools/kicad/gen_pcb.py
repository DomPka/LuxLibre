#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generate the FlashKa Keychain v0.7 main PCB (KiCad 6/7 format, 4 layers, 0.8 mm).

v0.7: the three buttons, the two ring LEDs and their eight resistors moved to the key board
(gen_keys.py); the main board gets J6, six ENIG target pads on the bottom face right above the
key board's pogo pins (flashka_parts.KB["pogo"]).  The 1000 lm power stage (4 A buck U2, 1-cell
protection U6/Q3, 24 AWG pads J2/J3) takes the positions in PLACEMENT_POWER; every other footprint
keeps its released v0.6 position and rotation (PLACEMENT_V06; v0.6 placed them with the hand-made
clusters, the annealed slots and the legaliser of tools/kicad in hardware/flashka-keychain-v06).
Routing is done afterwards by route.py (see build_all.py).

Coordinates: housing (X along the light, Y across, see flashka_housing.py)
map to KiCad as  x = 100 + X,  y = 100 - Y  (board seen from the lid side).
"""
import copy
import json
import math
import os
import sys
import uuid

from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.items.common import Effects, Font, Net, Position
from kiutils.items.gritems import GrLine, GrText

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flashka_parts import KB, on_board  # noqa: E402
from gen_sch import sym_uuid  # noqa: E402

KFP = "/usr/share/kicad/footprints"
SILK_REFS = ("J", "S")   # reference designators printed on the silkscreen
# v0.6: pad copper to board edge for the placement (KiCad rule min_copper_edge_clearance 0.20)
PAD_EDGE = 0.21

# main PCB outline (housing mm), unchanged since v0.6 (cad/housing_interface.json pcb_outline)
OUTLINE = [(10.1, -8.25), (32.8, -8.25), (32.8, 8.25), (10.1, 8.25), (8.8, 6.95), (8.8, -6.95)]


def K(X, Y):
    return round(100 + X, 4), round(100 - Y, 4)


# --------------------------------------------------------------------------
# placement: housing coordinates (X, Y), KiCad rotation, side
# --------------------------------------------------------------------------
# the released v0.6 placement of every part that stays on the main board (v0.6 board file
# kicad/FlashKa_main/FlashKa_main.kicad_pcb = cad/pcb_placement.json of v0.6)
PLACEMENT_V06 = {
    "C1": (21.7, -5.4, 0, "B"), "C2": (24.93, -2.6, 90, "B"), "C5": (16.22, -2.1, 90, "F"),
    "C7": (17.45, -3.45, 90, "F"), "C8": (17.4, -6.5, 90, "F"), "C9": (11.95, -0.65, 0, "F"),
    "C10": (27.125, 7.125, 0, "B"), "C11": (20.575, 3.975, 90, "F"),
    "C12": (20.525, -2.875, 0, "F"), "C13": (31.3, -1.0, 0, "B"),
    "C14": (23.725, -5.325, 270, "B"), "C15": (30.6, 6.55, 0, "B"), "C16": (31.65, 5.775, 0, "F"),
    "C17": (22.525, -6.7, 180, "B"), "C18": (31.625, 7.375, 180, "F"),
    "C19": (20.5, 1.925, 180, "F"), "C20": (20.5, 1.125, 180, "F"), "D1": (24.93, -5.4, 90, "B"),
    "J1": (14.6, -4.6, 180, "B"), "J2": (31.3, -4.8, 90, "B"), "J3": (10.1, 1.8, 0, "F"),
    "J5": (15.55, 6.35, 0, "B"), "L1": (14.35, -5.9, 270, "F"), "Q1": (27.82, -5.9, 0, "B"),
    "Q2": (19.85, 6.6, 270, "F"), "Q4": (25.85, 6.9, 0, "F"), "Q5": (29.15, 6.9, 0, "F"),
    "R1": (16.75, 1.15, 0, "B"), "R2": (13.33, 2.2, 90, "B"), "R3": (20.5, -6.875, 0, "F"),
    "R7": (20.8, -6.7, 180, "B"), "R8": (31.625, 6.575, 180, "F"), "R9": (27.75, -0.15, 180, "B"),
    "R10": (11.07, -3.25, 0, "F"), "R11": (11.55, -4.7, 270, "F"), "R12": (20.5, -2.075, 0, "F"),
    "R13": (19.325, 4.525, 180, "F"), "R14": (14.5, 2.19, 0, "F"),
    "R15": (20.575, -3.675, 180, "F"), "R16": (20.5, -5.275, 0, "F"),
    "R17": (14.34, -0.45, 180, "F"), "R18": (24.25, -6.975, 180, "B"),
    "R19": (14.5, 2.99, 180, "F"), "R20": (20.5, -1.275, 180, "F"),
    "R21": (20.525, -4.475, 0, "F"), "R22": (28.325, 0.65, 0, "B"), "R26": (20.5, 2.725, 0, "F"),
    "R27": (20.5, -0.475, 0, "F"), "R28": (20.5, 0.325, 180, "F"), "R29": (20.275, -7.7, 180, "F"),
    "RS1": (12.6, 1.6, 270, "F"), "RT1": (14.5, 1.39, 180, "F"), "S2": (14.05, 5.85, 180, "F"),
    "U1": (22.0, -2.84, 180, "B"), "U2": (14.35, -2.25, 90, "F"), "U3": (22.65, 6.9, 0, "F"),
    "U4": (27.2, -1.4, 270, "F"), "U5": (27.87, -2.25, 0, "B"),
}


# v0.7 power stage (1000 lm): the new buck U2 (VQFN-16 3 x 3) sits between the USB-C pegs with its
# switch pins right above L1 (moved 1.5 mm towards the front), the input capacitor C5 above PVIN,
# the sense resistor RS1 next to the LED- pad, C23 (CP/CN) and the feedback divider R11/R10 beside
# the right peg, both output capacitors at L1's output pad.  The LED pads J3 split: LED+ on the top
# face between the receptacle's two front shell legs (next to the buck output, in line with the
# top LED wire hole), LED- on the bottom face behind the receptacle (the v0.6 place).  The
# protection MOSFET Q3 takes Q1's place next to the cell pads J2 (rotated: BAT- is now the pad
# nearer to Q3) and the protection IC U6 takes the LDO's place right above it, turned the same
# way so that the gate pins face each other, with R35/C24 between it and the cell pads and the
# current-sense resistor R36 right beside Q3's P- pin (Kelvin: its ground end joins that pin
# alone); Q1, C13 and the LDO U5 move to the free band of the bottom face above the key board,
# R18/R19 (laser gate) to the row under J5, R14 (current-loop input) between the J6 contacts 3
# and 4, RT1 below the J6 row, R17 and the BTN pull-up R9 to the corner behind J6.6, the RGB_G
# strap pull-up R21 from the resistor column to the bottom face next to R22 (its 3V3 pad had no
# way out of the column any more).
# R22 shifts 0.05 mm to make room for U6; R1 (CC1) sits right behind its USB-C pin A5, 0.15 mm
# further back than in v0.6 (the D- escape and VBUS run between it and the pin row).
# C7, C9 and the old SOT-563 footprint are gone.  No via may go under the USB-C shell except GND
# ones (route.py), so U2's escapes, the LED+ path and the VBAT trunk are hand-made
# (route.preroute_buck).
PLACEMENT_POWER = {
    "J3": (10.25, 1.7, 0, "F"), "RS1": (13.6, 2.53, 0, "F"), "C5": (14.1, 1.02, 180, "F"),
    "U2": (14.6, -1.67, 90, "F"), "L1": (12.85, -5.9, 270, "F"),
    "C8": (15.9, -6.75, 90, "F"), "C22": (17.25, -6.75, 90, "F"), "C23": (17.25, -0.65, 90, "F"),
    "R11": (17.46, -3.28, 0, "F"), "R10": (17.0, -4.5, 90, "F"),
    "J2": (31.3, -4.65, 270, "B"), "Q3": (27.95, -5.55, 90, "B"), "U6": (27.95, -1.63, 90, "B"),
    "R35": (31.3, -1.35, 180, "B"), "C24": (30.0, -0.92, 90, "B"), "R36": (25.98, -6.65, 270, "B"),
    "R22": (28.325, 0.7, 0, "B"),
    "Q1": (19.8, 5.6, 0, "B"), "U5": (23.6, 5.6, 180, "B"), "C13": (27.4, 4.8, 0, "B"),
    "R1": (16.36, 1.3, 0, "B"),
    "R18": (14.3, 4.25, 180, "B"), "R19": (16.3, 4.25, 0, "B"),
    "R14": (22.8, 2.5, 90, "B"), "RT1": (21.25, -0.45, 0, "B"), "R17": (30.2, 4.7, 0, "B"),
    "R9": (30.2, 3.9, 0, "B"), "R21": (26.3, 0.7, 180, "B"),
}
REMOVED_POWER = ("C7", "C9")


def j6_position():
    """J6 footprint origin (middle of the pad row) on the bottom face; pad n over pogo pin Pn."""
    xs = [x for (_n, x, _y) in KB["pogo"]]
    ys = {y for (_n, _x, y) in KB["pogo"]}
    assert len(ys) == 1, "J6 footprint expects the pogo pins in one row"
    return (round((min(xs) + max(xs)) / 2, 4), ys.pop(), 0, "B")


def main_placement():
    plc = dict(PLACEMENT_V06)
    for r in REMOVED_POWER:
        plc.pop(r, None)
    plc.update(PLACEMENT_POWER)
    plc["J6"] = j6_position()
    return plc


# --------------------------------------------------------------------------
# footprint helpers
# --------------------------------------------------------------------------
# Courtyard excess: KiCad's stock courtyards are 0.25 mm outside the pads/body. The v0.6 board has
# 71 parts and about 89 % of the usable copper area under courtyards with that margin (button row,
# light-pipe circle), which no placement can reach.  Rectangular courtyards of the small parts are
# pulled in by COURTYARD_SHRINK per side (margin 0.15 mm, IPC-7351 "most"; two touching courtyards
# still leave 0.30 mm between bodies/pads, JLCPCB's recommended part spacing).  The big edge parts
# (USB-C, module, slide switch, inductor) keep their library courtyards.
COURTYARD_SHRINK = 0.10
# v0.6: the module's courtyard shrinks too (0.25 -> 0.15 mm around the module PCB): with it a
# row of horizontal 0402s fits between the USB-C shell legs and the module's GPIO pads
NO_SHRINK = ("USB_C_Receptacle", "SW_SPDT_PCM12")   # v0.7: L1 shrinks too (buck stage next to it)


def shrink_courtyard(fp, d=COURTYARD_SHRINK):
    lines = [g for g in fp.graphicItems if getattr(g, "layer", "") in ("F.CrtYd", "B.CrtYd")
             and type(g).__name__ == "FpLine"]
    if len(lines) != 4:
        return
    xs = sorted({round(p.X, 4) for g in lines for p in (g.start, g.end)})
    ys = sorted({round(p.Y, 4) for g in lines for p in (g.start, g.end)})
    if len(xs) != 2 or len(ys) != 2:
        return
    x0, x1, y0, y1 = xs[0] + d, xs[1] - d, ys[0] + d, ys[1] - d

    for g in lines:
        for p in (g.start, g.end):
            p.X = x0 if abs(p.X - xs[0]) < 1e-3 else x1
            p.Y = y0 if abs(p.Y - ys[0]) < 1e-3 else y1


def load_fp(libref):
    lib, name = libref.split(":")
    if lib == "FlashKa":
        path = os.path.join(HERE, "..", "..", "kicad", "FlashKa.pretty", name + ".kicad_mod")
    else:
        path = os.path.join(KFP, lib + ".pretty", name + ".kicad_mod")
    fp = Footprint.from_file(path)
    fp.libraryNickname = lib
    fp.entryName = name
    if not any(k in name for k in NO_SHRINK):
        shrink_courtyard(fp)
    return fp


def to_v6(item):
    st = getattr(item, "stroke", None)
    if st is not None and hasattr(item, "width"):
        item.width = st.width if st.width else 0.12
        item.stroke = None


FLIP = {"F.Cu": "B.Cu", "B.Cu": "F.Cu", "F.Paste": "B.Paste", "B.Paste": "F.Paste",
        "F.Mask": "B.Mask", "B.Mask": "F.Mask", "F.SilkS": "B.SilkS", "B.SilkS": "F.SilkS",
        "F.CrtYd": "B.CrtYd", "B.CrtYd": "F.CrtYd", "F.Fab": "B.Fab", "B.Fab": "F.Fab",
        "F.Adhes": "B.Adhes", "B.Adhes": "F.Adhes"}


def _mir(p):
    if p is not None:
        p.Y = -p.Y


def flip_fp(fp):
    """KiCad 'top-bottom' flip of an orientation-0 library footprint."""
    fp.layer = "B.Cu"
    for g in fp.graphicItems:
        for attr in ("start", "end", "mid", "center", "position"):
            _mir(getattr(g, attr, None))
        for attr in ("coordinates", "points"):
            pts = getattr(g, attr, None)
            if pts:
                for p in pts:
                    _mir(p)
        if hasattr(g, "layer") and g.layer in FLIP:
            g.layer = FLIP[g.layer]
        if type(g).__name__ == "FpText":
            g.position.angle = (180 - (g.position.angle or 0)) % 360
            g.effects.justify.mirror = True
    for pad in fp.pads:
        _mir(pad.position)
        pad.position.angle = (-(pad.position.angle or 0)) % 360
        pad.layers = [FLIP.get(l, l) for l in pad.layers]
        if pad.chamfer:
            sw = {"top_left": "bottom_left", "bottom_left": "top_left",
                  "top_right": "bottom_right", "bottom_right": "top_right"}
            pad.chamfer = [sw.get(c, c) for c in pad.chamfer]
        for prim in pad.customPadPrimitives:
            for attr in ("start", "end", "mid", "center"):
                _mir(getattr(prim, attr, None))
            pts = getattr(prim, "coordinates", None)
            if pts:
                for p in pts:
                    _mir(p)


def place_fp(fp, x, y, rot):
    fp.position = Position(x, y, rot if rot else None)
    for pad in fp.pads:
        a = ((pad.position.angle or 0) + rot) % 360
        pad.position.angle = a if a else None
    for g in fp.graphicItems:
        if type(g).__name__ == "FpText":
            a = ((g.position.angle or 0) + rot) % 360
            g.position.angle = a if a else None


def xform_pt(x, y, rot, flip):
    if flip:
        y = -y
    t = math.radians(rot)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def housing_box(local_box, X, Y, rot, side):
    """local footprint box -> housing (X0, Y0, X1, Y1)."""
    x0, y0, x1, y1 = local_box
    pts = [xform_pt(px, py, rot, side == "B") for px in (x0, x1) for py in (y0, y1)]
    xs = [X + p[0] for p in pts]
    ys = [Y - p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def overlap(a, b, m=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > -m and min(a[3], b[3]) - max(a[1], b[1]) > -m


def box_hits_circle(bx, circ, margin=0.0):
    """Housing box (X0, Y0, X1, Y1) against a keep-out circle {x, y, r}."""
    nx = min(max(circ["x"], bx[0]), bx[2])
    ny = min(max(circ["y"], bx[1]), bx[3])
    return math.hypot(nx - circ["x"], ny - circ["y"]) < circ["r"] + margin


def inside_poly(pt, poly):
    x, y = pt
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                c = not c
    return c


def hole_boxes(fp):
    out = []
    for p in fp.pads:
        if p.type in ("thru_hole", "np_thru_hole"):
            w = max(p.size.X, p.drill.diameter if p.drill else 0) / 2 + 0.2
            h = max(p.size.Y, p.drill.diameter if p.drill else 0) / 2 + 0.2
            out.append((p.position.X - w, p.position.Y - h, p.position.X + w, p.position.Y + h))
    return out


# USB-C D+/D- escape (route.preroute_usb uses these numbers), v0.7: no vias - D- joins A7-B7
# with a B.Cu U USB_DN_BACK behind the inner pad ends, D+ joins B6-A6 with a B.Cu U USB_DP_FRONT
# in front of the outer pad ends (under the receptacle body) and leaves along USB_DP_EXIT
# (turn-down x, run y below the right peg, end x; KiCad mm).  v0.6 dropped D- to two vias behind
# the pins, right where the v0.7 buck stage (U2, C5) sits on the top face.
USB_DN_BACK, USB_DP_FRONT, USB_PAD_HALF = 0.5, 0.45, 0.725
USB_DP_EXIT = (116.4, 103.45, 119.65)


def pad_boxes(fp):
    """Local boxes of the copper pads (rotated pads: bounding square)."""
    out = []
    for p in fp.pads:
        if p.type == "np_thru_hole":
            continue
        a = (p.position.angle or 0) % 180
        w, h = (p.size.X, p.size.Y) if a in (0, 0.0) else (p.size.Y, p.size.X) if a == 90 else \
            (max(p.size.X, p.size.Y),) * 2
        out.append((p.position.X - w / 2, p.position.Y - h / 2, p.position.X + w / 2, p.position.Y + h / 2))
    return out


def hole_pad_conflicts(plc, comps):
    """Every drilled hole (NPTH pegs, plated shell legs) against every SMD pad
    of the other parts, on both sides (holes go through the whole board)."""
    holes, pads = [], []
    for ref, (X, Y, rot, side) in plc.items():
        fp = load_fp(comps[ref]["fp"])
        for p in fp.pads:
            bx = (p.position.X - p.size.X / 2, p.position.Y - p.size.Y / 2,
                  p.position.X + p.size.X / 2, p.position.Y + p.size.Y / 2)
            hb = housing_box(bx, X, Y, rot, side)
            if p.type in ("thru_hole", "np_thru_hole"):
                holes.append((ref, str(p.number), hb))
            else:
                pads.append((ref, str(p.number), hb))
    out = []
    for (hr, hn, h) in holes:
        g = (h[0] - 0.2, h[1] - 0.2, h[2] + 0.2, h[3] + 0.2)
        for (pr, pn, pb) in pads:
            if pr != hr and overlap(g, pb):
                out.append((f"{hr}.{hn or 'hole'}", f"{pr}.{pn}"))
    return out


# --------------------------------------------------------------------------
def new_board(layers=4):
    """Empty kiutils board: 0.8 mm FR4, ENIG, 4 layers (In1 = GND plane) or 2 layers."""
    b = Board.create_new()
    b.version = "20211014"
    b.generator = "pcbnew"
    b.general.thickness = 0.8
    from kiutils.items.brditems import LayerToken, Stackup, StackupLayer
    if layers == 4:
        b.layers = [
            LayerToken(ordinal=0, name="F.Cu", type="signal"),
            LayerToken(ordinal=1, name="In1.Cu", type="power", userName="In1_GND"),
            LayerToken(ordinal=2, name="In2.Cu", type="signal"),
            LayerToken(ordinal=31, name="B.Cu", type="signal"),
        ] + [l for l in b.layers if l.ordinal > 31]
        cu = [StackupLayer(name="F.Cu", type="copper", thickness=0.035),
              StackupLayer(name="dielectric 1", type="prepreg", thickness=0.1, material="FR4",
                           epsilonR=4.4, lossTangent=0.02),
              StackupLayer(name="In1.Cu", type="copper", thickness=0.0152),
              StackupLayer(name="dielectric 2", type="core", thickness=0.47, material="FR4",
                           epsilonR=4.6, lossTangent=0.02),
              StackupLayer(name="In2.Cu", type="copper", thickness=0.0152),
              StackupLayer(name="dielectric 3", type="prepreg", thickness=0.1, material="FR4",
                           epsilonR=4.4, lossTangent=0.02),
              StackupLayer(name="B.Cu", type="copper", thickness=0.035)]
    else:
        b.layers = [LayerToken(ordinal=0, name="F.Cu", type="signal"),
                    LayerToken(ordinal=31, name="B.Cu", type="signal")] + \
                   [l for l in b.layers if l.ordinal > 31]
        cu = [StackupLayer(name="F.Cu", type="copper", thickness=0.035),
              StackupLayer(name="dielectric 1", type="core", thickness=0.73, material="FR4",
                           epsilonR=4.5, lossTangent=0.02),
              StackupLayer(name="B.Cu", type="copper", thickness=0.035)]
    b.setup.stackup = Stackup(layers=[
        StackupLayer(name="F.SilkS", type="Top Silk Screen"),
        StackupLayer(name="F.Paste", type="Top Solder Paste"),
        StackupLayer(name="F.Mask", type="Top Solder Mask", thickness=0.01)] + cu + [
        StackupLayer(name="B.Mask", type="Bottom Solder Mask", thickness=0.01),
        StackupLayer(name="B.Paste", type="Bottom Solder Paste"),
        StackupLayer(name="B.SilkS", type="Bottom Silk Screen"),
    ], copperFinish="ENIG")
    return b


def add_footprints(b, comps, plc, nets, tag, sheetfile, silk_refs=SILK_REFS, models=None):
    """Place the parts (housing X, Y, KiCad rotation, side) on a kiutils board.  tag: UUID name
    space of the board; models: ref -> 3D model path that replaces the library model."""
    for ref, c in comps.items():
        X, Y, rot, side = plc[ref]
        fp = load_fp(c["fp"])
        for g in fp.graphicItems:
            to_v6(g)
        for g in fp.graphicItems:
            if type(g).__name__ == "FpText":
                if g.type == "reference":
                    g.text = ref
                    # too many parts for readable designators: the silkscreen keeps the ones a
                    # builder needs; every designator stays on the F.Fab / B.Fab layer (assembly PDFs)
                    if not ref.startswith(silk_refs):
                        g.hide = True
                elif g.type == "value":
                    g.text = c["value"]
        if models and ref in models:
            from kiutils.footprint import Coordinate, Model
            fp.models = [Model(path=models[ref], pos=Coordinate(0, 0, 0), scale=Coordinate(1, 1, 1),
                               rotate=Coordinate(0, 0, 0))]
        if side == "B":
            flip_fp(fp)
        x, y = K(X, Y)
        place_fp(fp, x, y, rot)
        fp.path = "/" + sym_uuid(ref)
        fp.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tag}/" + ref))
        fp.tedit = "6720A000"         # fixed (kiutils stamps the current time otherwise)
        # every pad and graphic item needs its own UUID: library footprints carry
        # fixed tstamps, and KiCad's DRC / connectivity confuse items that share one
        for n, pad in enumerate(fp.pads):
            pad.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tag}/{ref}/pad/{n}"))
        for n, g in enumerate(fp.graphicItems):
            if hasattr(g, "tstamp"):
                g.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tag}/{ref}/gr/{n}"))
        fp.properties = {"Sheetfile": sheetfile, "Sheetname": "", "LCSC": c.get("lcsc", "")}
        for pad in fp.pads:
            net = c["nets"].get(str(pad.number))
            pad.net = copy.deepcopy(nets[net]) if net else None
        if c.get("external") or not c.get("lcsc"):
            fp.attributes.excludeFromBom = True
            fp.attributes.excludeFromPosFiles = True
        b.footprints.append(fp)


def build(outdir, hj_path=None):
    """Main PCB with the frozen placement.  hj_path (cad/housing_interface.json, optional): the
    outline there must still be the v0.6 one."""
    comps = {c["ref"]: c for c in on_board("main")}
    plc = main_placement()
    missing, extra = set(comps) - set(plc), set(plc) - set(comps)
    if missing or extra:
        raise SystemExit(f"placement and parts table differ: missing {sorted(missing)}, extra {sorted(extra)}")
    if hj_path and os.path.exists(hj_path):
        ol = [tuple(round(v, 4) for v in p) for p in json.load(open(hj_path))["pcb_outline"]]
        if ol != [tuple(round(v, 4) for v in p) for p in OUTLINE]:
            raise SystemExit(f"cad/housing_interface.json: the main PCB outline changed ({ol})")
    hp = hole_pad_conflicts(plc, comps)
    if hp:
        raise SystemExit(f"holes through pads: {hp}")
    b = new_board(4)
    names = sorted({n for c in comps.values() for n in c["nets"].values()})
    nets = {n: Net(number=i + 1, name=n) for i, n in enumerate(names)}
    b.nets = [Net(number=0, name="")] + [nets[n] for n in names]
    # UUID name space of v0.6: the parts that stay keep their item UUIDs
    add_footprints(b, comps, plc, nets, "FlashKa06_pcb", "FlashKa_main.kicad_sch")

    # fixed UUIDs for the board-level items.  KiCad 7 orders the outline segments by UUID when
    # it builds the board polygon, which changes the zone fills in the last digits and with them
    # the router's repair decisions; these values are the ones the released board was routed with
    edge_ids = ["75f4bfeb-a8d1-47f0-8b67-e81404ebd4fd", "7649336a-9e78-4d17-a073-a460824533d0",
                "3307d1f6-fdda-4ae1-b5fb-55cdec3868b5", "929ad3df-1718-4f3c-a003-3a636f47bea2",
                "9ed87ed7-930f-4881-b496-b465ca3f7293", "47d3765e-e188-4f02-86ad-4718caae32c6"]
    note_ids = ["fb265f80-1615-4589-b752-865618512152", "ae9f734d-1943-4cbe-8e22-1d73946c9eef",
                "06d8f875-20fd-4081-9482-69b50395539f"]
    pts = [K(x, y) for (x, y) in OUTLINE]
    for i in range(len(pts)):
        a, c2 = pts[i], pts[(i + 1) % len(pts)]
        b.graphicItems.append(GrLine(start=Position(*a), end=Position(*c2), layer="Edge.Cuts",
                                     width=0.1, tstamp=edge_ids[i] if len(pts) == len(edge_ids) else
                                     str(uuid.uuid5(uuid.NAMESPACE_URL, f"FlashKa06_pcb/edge/{i}"))))
    notes = [
        (108.0, 89.0, "FlashKa Keychain v0.7 main PCB  4 layers 0.8 mm  outline/edge parts from cad/housing_interface.json"),
        (108.0, 87.8, "ESP32-C3-MINI-1 antenna overhangs the rear (+x) edge - keep it free of copper and wires"),
        (108.0, 86.6, "Bottom side: USB-C, charger, laser switch, J6 key-board contacts. Top side: module, LED driver, S2"),
    ]
    for (x, y, t), tid in zip(notes, note_ids):
        b.graphicItems.append(GrText(text=t, position=Position(x, y), layer="Cmts.User",
                                     effects=Effects(font=Font(height=0.7, width=0.7, thickness=0.1)),
                                     tstamp=tid))
    b.graphicItems.append(GrText(text="FLASHKA v0.7", position=Position(*K(24.0, -7.6)),
                                 layer="B.SilkS",
                                 effects=Effects(font=Font(height=0.6, width=0.6, thickness=0.12)),
                                 tstamp="4b50894a-65b9-435d-8db6-574884412395"))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "FlashKa_main.kicad_pcb")
    b.to_file(path)
    top = {r: (x, y, rot) for r, (x, y, rot, s) in plc.items() if s == "F"}
    bottom = {r: (x, y, rot) for r, (x, y, rot, s) in plc.items() if s == "B"}
    return path, top, bottom


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "kicad/FlashKa_main"
    hj = sys.argv[2] if len(sys.argv) > 2 else "cad/housing_interface.json"
    p, t, bt = build(out, hj)
    print("wrote", p, len(t), "top,", len(bt), "bottom")
