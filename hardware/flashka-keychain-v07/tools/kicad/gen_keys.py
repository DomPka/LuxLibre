#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generate the FlashKa Keychain v0.7 key board (KB) PCB (KiCad 6/7 format, 0.8 mm, ENIG).

The key board sits on two bosses of the floor, right above the three keys:
  bottom face (towards the keys)  SW1 main, SW2 next, SW3 previous, ring LEDs LED3 / LED4
  top face (towards the main PCB) the eight resistors and six SMT pogo pins P1-P6 that press on
                                  the target pads J6 of the main board's bottom face
Every position the housing fixes comes from flashka_parts.KB (outline, holes, keep-outs, the
switch and LED positions, the pogo row).  The resistors are placed here, next to the pogo pin of
their net.  It is built with the stack-up of the main board (4 layers, In1 = GND plane) because
both boards are ordered as one JLCPCB panel (build_all.py, panel_jlc.py).  Routing: route.py
(full run + finalize, same rules as the main board); see build_all.py.

Coordinates: housing (X along the light, Y across) map to KiCad as x = 100 + X, y = 100 - Y
(board seen from the lid side, like the main board): F.Cu = top face, B.Cu = bottom face.
"""
import math
import os
import sys
import uuid

from kiutils.items.common import Effects, Font, Justify, Net, Position
from kiutils.items.gritems import GrArc, GrLine, GrPoly, GrText
from kiutils.items.zones import Hatch, KeepoutSettings, Zone, ZonePolygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flashka_parts import KB, on_board  # noqa: E402
import gen_pcb  # noqa: E402
from gen_pcb import K  # noqa: E402

TAG = "FlashKa07_keys"          # UUID name space of the key board items

# top-face resistors: (X, Y, KiCad rotation).  Each LED resistor pair sits under the pogo pin of
# its colour (pad 2 = RGB net towards the pin, pad 1 = LED cathode); the ladder resistors sit
# next to their switch.  rot 90 = pad 1 at -Y, pad 2 at +Y; rot 180 = pad 1 at +X.
RESISTORS = {
    "R23": (20.15, 0.25, 90), "R32": (21.05, 0.25, 90),    # RGB_R  (P3 at X 20.6)
    "R24": (24.55, 0.25, 90), "R33": (25.45, 0.25, 90),    # RGB_G  (P4 at X 25.0)
    "R25": (27.35, 0.25, 90), "R34": (28.25, 0.25, 90),    # RGB_B  (P5 at X 27.8)
    "R30": (17.4, -2.1, 180),                              # BTN -> BTN_NX (SW2)
    "R31": (28.4, -2.1, 0),                                # BTN -> BTN_PV (SW3)
}
SILK_REFS = ()              # no designators on the key board's silkscreen (all stay on the Fab layers):
                            # the top face carries the orientation marks instead

# orientation marks (white silkscreen on black mask).  The outline and the holes are symmetric, so
# the board also fits turned by 180 deg - then P5/P6 sit in the USB-C receptacle and next/previous
# swap.  JLCPCB legend minimums: text height 1.0 mm, line width 0.153 mm, line : height >= 1 : 6.
SILK_H, SILK_W = 1.0, 0.18
# top face: (text, X, Y) left-justified, Y = text centre; arrow (tip X, tail X, Y) points to -X
SILK_TOP_TEXT = (("HEAD", 16.75, 6.2), ("PINS:", 25.2, 6.2), ("S2 SIDE", 25.2, 4.55), ("KB v0.7", 25.6, -4.6))
SILK_TOP_ARROW = (13.85, 16.35, 6.2)
# bottom face: arrow between SW2 and SW1 (tip X, tail X, Y), points to the head as well
SILK_BOTTOM_ARROW = (17.9, 19.9, 0.0)


def placement():
    plc = {}
    for ref, (X, Y, rot) in KB["bottom"].items():
        plc[ref] = (X, Y, rot, "B")
    for ref, X, Y in KB["pogo"]:
        plc[ref] = (X, Y, 0, "F")
    for ref, (X, Y, rot) in RESISTORS.items():
        plc[ref] = (X, Y, rot, "F")
    for n, (X, Y) in enumerate(KB["holes"]):
        plc[f"H{n + 1}"] = (X, Y, 0, "F")
    return plc


def outline_items():
    """Rounded rectangle (housing X0..X1, Y0..Y1, corner radius r) as Edge.Cuts lines and arcs."""
    X0, Y0, X1, Y1 = KB["outline"]
    r = KB["corner_r"]
    s = math.sqrt(0.5)
    out = []
    lines = [((X0 + r, Y0), (X1 - r, Y0)), ((X1, Y0 + r), (X1, Y1 - r)),
             ((X1 - r, Y1), (X0 + r, Y1)), ((X0, Y1 - r), (X0, Y0 + r))]
    # corners: start, mid, end (counter-clockwise in housing coordinates)
    arcs = [((X1 - r, Y0), (X1 - r + r * s, Y0 + r - r * s), (X1, Y0 + r)),
            ((X1, Y1 - r), (X1 - r + r * s, Y1 - r + r * s), (X1 - r, Y1)),
            ((X0 + r, Y1), (X0 + r - r * s, Y1 - r + r * s), (X0, Y1 - r)),
            ((X0, Y0 + r), (X0 + r - r * s, Y0 + r - r * s), (X0 + r, Y0))]
    for i, (a, b) in enumerate(lines):
        out.append(GrLine(start=Position(*K(*a)), end=Position(*K(*b)), layer="Edge.Cuts", width=0.1,
                          tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/edge/{i}"))))
    for i, (a, m, b) in enumerate(arcs):
        out.append(GrArc(start=Position(*K(*a)), mid=Position(*K(*m)), end=Position(*K(*b)),
                         layer="Edge.Cuts", width=0.1,
                         tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/arc/{i}"))))
    return out


def silk_text(text, X, Y, layer, n):
    """left-justified silkscreen text, centred on Y (housing coordinates)"""
    e = Effects(font=Font(height=SILK_H, width=SILK_H, thickness=SILK_W), justify=Justify(horizontally="left"))
    if layer.startswith("B."):
        e.justify.mirror = True
    return GrText(text=text, position=Position(*K(X, Y)), layer=layer, effects=e,
                  tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/silk/{n}")))


def silk_arrow(tip, tail, Y, layer, n, head=0.9, half=0.45, w=0.2):
    """arrow along X: filled triangle at the tip + shaft (housing coordinates)"""
    d = 1 if tail > tip else -1
    base = tip + d * head
    tri = GrPoly(layer=layer, coordinates=[Position(*K(tip, Y)), Position(*K(base, Y + half)),
                                           Position(*K(base, Y - half))], width=0.1, fill="solid",
                 tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/silk/{n}/tip")))
    shaft = GrLine(start=Position(*K(base - d * 0.05, Y)), end=Position(*K(tail, Y)), layer=layer, width=w,
                   tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/silk/{n}/shaft")))
    return [tri, shaft]


def keepout(name, pts, layers, footprints=True, copper=True):
    """Rule area (KiCad keep-out): no tracks, vias, pours (copper=True) and/or no parts and pads
    (footprints=True)."""
    z = Zone()
    z.net, z.netName = 0, ""
    z.layers = layers
    z.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/keepout/{name}"))
    z.name = name
    z.hatch = Hatch(style="edge", pitch=0.5)
    z.connectPads = None
    z.clearance = 0
    z.minThickness = 0.25
    z.fillSettings = None
    na, ok = "not_allowed", "allowed"
    z.keepoutSettings = KeepoutSettings(tracks=na if copper else ok, vias=na if copper else ok,
                                        pads=na if footprints else ok, copperpour=na if copper else ok,
                                        footprints=na if footprints else ok)
    z.polygons = [ZonePolygon(coordinates=[Position(*K(x, y)) for (x, y) in pts])]
    return z


def circle_pts(x, y, r, n=40):
    return [(round(x + r * math.cos(2 * math.pi * k / n), 4), round(y + r * math.sin(2 * math.pi * k / n), 4))
            for k in range(n)]


def build(outdir, layers=4):
    comps = {c["ref"]: c for c in on_board("keys")}
    plc = placement()
    missing, extra = set(comps) - set(plc), set(plc) - set(comps)
    if missing or extra:
        raise SystemExit(f"key board placement and parts table differ: missing {sorted(missing)}, "
                         f"extra {sorted(extra)}")
    hp = gen_pcb.hole_pad_conflicts(plc, comps)
    if hp:
        raise SystemExit(f"holes through pads: {hp}")
    b = gen_pcb.new_board(layers)
    names = sorted({n for c in comps.values() for n in c["nets"].values()})
    nets = {n: Net(number=i + 1, name=n) for i, n in enumerate(names)}
    b.nets = [Net(number=0, name="")] + [nets[n] for n in names]
    # the Alps SKRK switches have no model in the KiCad library: models_3d.py makes one
    sw = {r: "${KIPRJMOD}/FlashKa.3dshapes/SW_Alps_SKRK.step" for r in comps if r.startswith("SW")}
    gen_pcb.add_footprints(b, comps, plc, nets, TAG, "FlashKa_keys.kicad_sch", silk_refs=SILK_REFS,
                           models=sw)
    b.graphicItems += outline_items()
    cu = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] if layers == 4 else ["F.Cu", "B.Cu"]
    # screw heads (top, d3.0-3.2) and floor bosses (bottom, d3.4): no copper in d3.8 (the rule
    # area cannot exclude other parts without flagging the hole itself: check_keys.py checks that
    # no courtyard but the hole's enters the circle)
    for n, (X, Y) in enumerate(KB["holes"]):
        b.zones.append(keepout(f"screw H{n + 1}", circle_pts(X, Y, KB["keepout_d"] / 2), cu,
                               footprints=False))
    # floor supports touch the bottom face here: no parts, no exposed pads (copper under mask is fine)
    for n, (x0, y0, x1, y1) in enumerate(KB["floor_supports"]):
        b.zones.append(keepout(f"floor support {n + 1}", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                               ["B.Cu"], footprints=True, copper=False))
    notes = [(108.0, 89.0, "FlashKa Keychain v0.7 key board  0.8 mm ENIG  positions from tools/kicad/flashka_parts.py (KB)"),
             (108.0, 87.8, "Bottom face: SW1-SW3, LED3, LED4 (keys side). Top face: resistors, pogo pins P1-P6 (to J6 of the main PCB)")]
    for i, (x, y, t) in enumerate(notes):
        b.graphicItems.append(GrText(text=t, position=Position(x, y), layer="Cmts.User",
                                     effects=Effects(font=Font(height=0.7, width=0.7, thickness=0.1)),
                                     tstamp=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TAG}/note/{i}"))))
    for n, (t, X, Y) in enumerate(SILK_TOP_TEXT):
        b.graphicItems.append(silk_text(t, X, Y, "F.SilkS", n))
    b.graphicItems += silk_arrow(*SILK_TOP_ARROW, "F.SilkS", "arrow_top")
    b.graphicItems += silk_arrow(*SILK_BOTTOM_ARROW, "B.SilkS", "arrow_bottom")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "FlashKa_keys.kicad_pcb")
    b.to_file(path)
    return path, plc


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "kicad/FlashKa_keys"
    p, plc = build(out)
    print("wrote", p, len(plc), "parts")
