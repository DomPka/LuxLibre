#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generate the Aurora++ v0.5 main PCB (KiCad 6/7 format, 4 layers, 0.8 mm):
board outline and edge-critical parts from the housing model
(cad/housing_interface.json), the rest placed from the preferred positions
below and legalised (no courtyard overlaps, keep-outs, housing trough).
Routing is done afterwards by route.py.

Coordinates: housing (X along the light, Y across, see aurora_housing.py)
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
from aurora_parts import COMPONENTS  # noqa: E402
from gen_sch import sym_uuid  # noqa: E402
from autoplace import local_boxes  # noqa: E402

KFP = "/usr/share/kicad/footprints"
SILK_REFS = ("J", "S")   # reference designators printed on the silkscreen


def K(X, Y):
    return round(100 + X, 4), round(100 - Y, 4)


# --------------------------------------------------------------------------
# placement: housing coordinates (X, Y), KiCad rotation, side
# --------------------------------------------------------------------------
def fixed_parts(hj):
    c = hj["components"]
    j1, s1, s2, m = c["J1_usb"], c["S1_button"], c["S2_interlock"], c["U4_module"]
    return {
        # module on top, antenna (footprint -y) towards +X, beyond the rear edge
        "U4": (m["x_onboard_end"] - 5.6, m["y"], 270, "F"),
        # USB-C on the bottom, mating face (footprint y +3.65) at the -Y edge
        "J1": (j1["x"], j1["face_y"] + 3.65, 180, "B"),
        # S1 on the bottom, actuator tip (footprint y +2.04) towards -Y
        "S1": (s1["x"], s1["actuator_tip_y"] + 2.04, 180, "B"),
        # S2 on top, knob tip (footprint y +3.15) towards +Y into the wall slot
        "S2": (s2["x"], s2["knob_tip_y"] - 3.15, 180, "F"),
        # LED wire pads (LED+ top, LED- bottom), clear of the USB-C rear pads
        "J3": (10.1, 1.8, 0, "F"),
        **BUCK_CLUSTER,
    }


# hand-placed buck power stage (top, between the USB-C shell legs): VIN/SW/GND
# pins of U2 face down, L1 right below SW, C5 across VIN/GND, C8 at L1's output
BUCK_CLUSTER = {
    "U2": (14.35, -2.25, 90, "F"),
    "L1": (14.35, -5.9, 270, "F"),
    "C5": (16.22, -2.1, 90, "F"),
    "C7": (17.45, -3.45, 90, "F"),
    "C8": (17.4, -6.5, 90, "F"),
}


PREFERRED = {
    # ---- top, front: LED driver power stage (VOUT straight to J3 LED+)
    "L1": (13.3, -5.9, 0, "F"), "U2": (13.7, -2.4, 0, "F"), "C5": (16.4, -6.6, 90, "F"),
    "C7": (12.7, -0.5, 90, "F"), "C8": (18.4, 1.6, 90, "F"), "R17": (15.9, -0.6, 0, "F"),
    "R10": (16.3, -2.6, 90, "F"), "C9": (17.2, -3.9, 90, "F"), "R11": (15.6, -3.9, 90, "F"),
    # ---- top, front: current loop next to the sense resistor
    "RS1": (12.6, 1.6, 90, "F"), "U3": (15.2, 1.6, 0, "F"), "R14": (14.6, 3.0, 0, "F"),
    "C11": (16.3, 3.0, 0, "F"), "C10": (17.0, -0.6, 0, "F"),
    "R21": (19.3, -7.3, 0, "F"),
    # ---- top, strip beside the module (+Y), RGB LED under the RF window
    "LED3": (31.0, 7.0, 0, "F"), "R23": (29.6, 7.4, 0, "F"), "R24": (29.6, 6.5, 0, "F"),
    "R25": (28.0, 7.4, 0, "F"), "C15": (27.9, 6.4, 0, "F"), "C16": (26.2, 7.4, 0, "F"),
    "R22": (26.2, 6.5, 0, "F"), "R8": (24.6, 7.4, 0, "F"), "C18": (24.6, 6.5, 0, "F"),
    "R15": (22.9, 7.4, 0, "F"), "R16": (22.9, 6.5, 0, "F"), "C12": (21.3, 7.0, 90, "F"),
    # ---- bottom, front: NTC near the head block, laser pads + switch behind the laser
    "RT1": (12.1, 1.6, 90, "B"), "R26": (13.4, 1.4, 90, "B"), "C19": (14.4, 1.4, 90, "B"),
    "J5": (14.6, 4.9, 90, "B"), "Q1": (17.4, 5.5, 0, "B"), "R18": (17.2, 2.6, 0, "B"),
    "R19": (19.2, 2.8, 90, "B"), "C13": (16.8, 1.4, 0, "B"),
    "Q4": (21.2, 6.2, 0, "B"), "R20": (21.0, 3.9, 90, "B"),
    # ---- bottom, rear: charger, LDO, reset, cell pads, sense divider, FB sink
    "J2": (28.6, 4.4, 90, "B"),
    "U1": (23.4, 0.6, 0, "B"), "R3": (23.4, 3.0, 0, "B"), "R29": (25.3, 3.0, 0, "B"),
    "C1": (20.8, -1.6, 90, "B"), "C2": (26.2, -0.6, 90, "B"), "D1": (20.6, 1.6, 90, "B"),
    "R1": (21.8, -2.6, 0, "B"), "R2": (23.6, -2.6, 0, "B"),
    "U5": (24.8, 5.4, 0, "B"), "C14": (26.8, 6.8, 0, "B"),
    "Q5": (29.2, -1.6, 0, "B"), "C17": (29.2, 0.4, 0, "B"), "R7": (30.9, -1.6, 90, "B"),
    "R27": (30.9, -4.4, 90, "B"), "R28": (30.9, -6.4, 90, "B"), "C20": (29.7, -5.4, 90, "B"),
    "Q2": (28.5, -3.6, 0, "B"), "R12": (27.0, -2.6, 0, "B"), "R13": (27.0, -1.7, 0, "B"),
    "R9": (29.7, -7.3, 0, "B"),
}


# --------------------------------------------------------------------------
# footprint helpers
# --------------------------------------------------------------------------
def load_fp(libref):
    lib, name = libref.split(":")
    if lib == "Aurora":
        path = os.path.join(HERE, "..", "..", "kicad", "Aurora.pretty", name + ".kicad_mod")
    else:
        path = os.path.join(KFP, lib + ".pretty", name + ".kicad_mod")
    fp = Footprint.from_file(path)
    fp.libraryNickname = lib
    fp.entryName = name
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


# USB-C D+/D- escape (route.preroute_usb uses the same numbers): D- drops to two
# vias USB_VIA_BACK behind the inner end of pins A7/B7, D+ joins A6-B6 with a
# U-shaped B.Cu track USB_U_BACK behind it.  Nothing may sit on those spots.
USB_VIA_BACK, USB_U_BACK, USB_PAD_HALF = 0.45, 0.88, 0.725


def usb_escape_keepouts(fixed, comps):
    """Housing-coordinate boxes: D- via spots (both sides) and the D+ U (bottom)."""
    X0, Y0, rot, side = fixed["J1"]
    fp = load_fp(comps["J1"]["fp"])
    pos = {}
    for p in fp.pads:
        if p.number in ("A6", "B6", "A7", "B7"):
            dx, dy = xform_pt(p.position.X, p.position.Y, rot, side == "B")
            pos[p.number] = (X0 + dx, Y0 - dy)
    # the pins' inner end points towards +Y (board centre) for the J1 at the -Y edge
    yv = pos["A7"][1] + USB_PAD_HALF + USB_VIA_BACK
    yu = pos["A7"][1] + USB_PAD_HALF + USB_U_BACK
    # compared with the pad copper of the other parts (legalise / placer):
    # via pad 0.225 + clearance 0.13 + margin 0.06; the router checks the real
    # pad distance again (route.preroute_usb)
    r = 0.225 + 0.13 + 0.06
    vias = [(pos[n][0] - r, yv - r, pos[n][0] + r, yv + r) for n in ("A7", "B7")]
    xa, xb = sorted((pos["A6"][0], pos["B6"][0]))
    u = [(xa - 0.25, yu - 0.25, xb + 0.25, yu + 0.25)]
    return vias, u


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


def usb_conflict(ref_pads, X, Y, rot, side, usb_v, usb_u):
    for pb in ref_pads:
        hb = housing_box(pb, X, Y, rot, side)
        if any(overlap(hb, b) for b in usb_v):
            return True
        if side == "B" and any(overlap(hb, b) for b in usb_u):
            return True
    return False


def legalise(hj, comps, preferred, fixed, gap=0.08, step=0.05, max_r=8.0):
    """Greedy: every movable part keeps its preferred spot if legal, else the
    nearest legal spot (rotations r and r+90). Legal = courtyard inside the
    board, no overlap with parts on the same side, off all holes, off the
    keep-outs, bottom parts inside the housing trough."""
    outline = [tuple(p) for p in hj["pcb_outline"]]
    C = hj["components"]
    ty0, ty1 = C["trough_y"]
    exc = C["trough_exceptions"]
    keep_b = [(k["x0"], k["y0"], k["x1"], k["y1"]) for k in C["keepout_bottom"]]
    info = {}
    for ref in comps:
        fp = load_fp(comps[ref]["fp"])
        crt, _ = local_boxes(fp)
        info[ref] = (crt, hole_boxes(fp))
    placed = {"F": [], "B": []}
    holes = []

    def commit(ref, X, Y, rot, side):
        crt, hb = info[ref]
        placed[side].append((ref, housing_box(crt, X, Y, rot, side)))
        if comps[ref]["fp"].endswith("TopBottom_1.6x1.8"):
            placed["B" if side == "F" else "F"].append((ref, housing_box(crt, X, Y, rot, side)))
        for b in hb:
            holes.append((ref, housing_box(b, X, Y, rot, side)))

    for ref, (X, Y, rot, side) in fixed.items():
        commit(ref, X, Y, rot, side)
    usb_v, usb_u = usb_escape_keepouts(fixed, comps) if "J1" in fixed else ([], [])
    pads = {ref: pad_boxes(load_fp(comps[ref]["fp"])) for ref in comps}

    def trough_ok(bx):
        lo, hi = ty0, ty1
        for e in exc:
            if bx[0] >= e["x0"] - 1e-6 and bx[2] <= e["x1"] + 1e-6:
                if e["side"] == "-Y":
                    lo = -99
                else:
                    hi = 99
        return bx[1] >= lo and bx[3] <= hi

    def ok(ref, X, Y, rot, side):
        crt, hb = info[ref]
        bx = housing_box(crt, X, Y, rot, side)
        bx = (bx[0] - gap / 2, bx[1] - gap / 2, bx[2] + gap / 2, bx[3] + gap / 2)
        for pt in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3]),
                   ((bx[0] + bx[2]) / 2, bx[1]), ((bx[0] + bx[2]) / 2, bx[3])):
            if not inside_poly(pt, outline):
                return False
        if side == "B":
            if not trough_ok(bx):
                return False
            for k in keep_b:
                if overlap(bx, k):
                    return False
        for (_, o) in placed[side]:
            if overlap(bx, o):
                return False
        for (_, h) in holes:
            if overlap(bx, h):
                return False
        if usb_conflict(pads[ref], X, Y, rot, side, usb_v, usb_u):
            return False
        for b in hb:     # own holes vs. parts on the other side
            hbx = housing_box(b, X, Y, rot, side)
            for (_, o) in placed["B" if side == "F" else "F"]:
                if overlap(hbx, o):
                    return False
        return True

    out, moved, unplaced = dict(fixed), [], []
    # parts whose preferred spot lies on a USB escape keep-out go last, so they
    # take a free spot instead of pushing their neighbours around
    def on_usb(ref, X, Y, rot, side):
        return usb_conflict(pads[ref], X, Y, rot, side, usb_v, usb_u)
    order = [r for r in preferred if not on_usb(r, *preferred[r])] + \
            [r for r in preferred if on_usb(r, *preferred[r])]
    for ref in order:
        X0, Y0, r0, side = preferred[ref]
        best = None
        if ok(ref, X0, Y0, r0, side):
            best = (X0, Y0, r0)
        rr = step
        while best is None and rr <= max_r:
            n = max(8, int(2 * math.pi * rr / step))
            cand = []
            for k in range(n):
                a = 2 * math.pi * k / n
                cand.append((round((X0 + rr * math.cos(a)) / 0.05) * 0.05,
                             round((Y0 + rr * math.sin(a)) / 0.05) * 0.05))
            for rot in (r0, (r0 + 90) % 360):
                for (x, y) in cand:
                    if ok(ref, x, y, rot, side):
                        best = (round(x, 3), round(y, 3), rot)
                        break
                if best:
                    break
            rr += step
        if best is None:
            unplaced.append(ref)
            continue
        if (best[0], best[1], best[2]) != (X0, Y0, r0):
            moved.append((ref, side, (X0, Y0, r0), best, round(math.hypot(best[0] - X0, best[1] - Y0), 2)))
        commit(ref, *best, side)
        out[ref] = (*best, side)
    legalise.state = dict(placed=placed, holes=holes, unplaced=unplaced)
    return out, moved, unplaced


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


def plot_placement(hj, plc, comps, path, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Rectangle
    st = legalise.state
    outline = hj["pcb_outline"]
    fig, axs = plt.subplots(2, 1, figsize=(13, 12))
    for ax, sd in zip(axs, ("F", "B")):
        ax.add_patch(Polygon(outline, fill=False, ec="k", lw=1.5))
        for (r, b) in st["placed"][sd]:
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fill=False,
                                   ec="tab:red" if r in ("U4", "J1", "S1", "S2", "J3") else "tab:blue"))
            ax.text((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, r, fontsize=7, ha="center", va="center")
        for (r, b) in st["holes"]:
            ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc="orange", alpha=0.4))
        if sd == "B":
            for k in hj["components"]["keepout_bottom"]:
                ax.add_patch(Rectangle((k["x0"], k["y0"]), k["x1"] - k["x0"], k["y1"] - k["y0"],
                                       fc="gray", alpha=0.25))
            for y in hj["components"]["trough_y"]:
                ax.axhline(y, color="g", lw=0.8, ls="--")
        ax.set_xlim(7.5, 37)
        ax.set_ylim(-9.5, 9.5)
        ax.set_aspect("equal")
        ax.set_title(f"{'TOP (lid side)' if sd == 'F' else 'BOTTOM (floor side), seen from the top'} {title}")
        ax.grid(alpha=0.2)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close(fig)


# --------------------------------------------------------------------------
def build(outdir, hj_path, plot=None):
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = fixed_parts(hj)
    pref = {r: v for r, v in PREFERRED.items() if r in comps}
    missing = set(comps) - set(fixed) - set(pref)
    if missing:
        raise SystemExit(f"no preferred position: {sorted(missing)}")
    cache = os.path.join(os.path.dirname(os.path.abspath(hj_path)), "pcb_placement_sa.json")
    if os.path.exists(cache):          # annealed placement (tools/kicad/placer.py)
        sa = json.load(open(cache))["placement"]
        pref = {r: tuple(v) for r, v in sa.items() if r in comps and r not in fixed}
    plc, moved, unplaced = legalise(hj, comps, pref, fixed)
    if plot:
        plot_placement(hj, plc, comps, plot)
    if unplaced:
        raise SystemExit(f"unplaced: {unplaced}")
    hp = hole_pad_conflicts(plc, comps)
    if hp:
        raise SystemExit(f"holes through pads: {hp}")

    b = Board.create_new()
    b.version = "20211014"
    b.generator = "pcbnew"
    b.general.thickness = 0.8
    from kiutils.items.brditems import LayerToken, Stackup, StackupLayer
    b.layers = [
        LayerToken(ordinal=0, name="F.Cu", type="signal"),
        LayerToken(ordinal=1, name="In1.Cu", type="power", userName="In1_GND"),
        LayerToken(ordinal=2, name="In2.Cu", type="signal"),
        LayerToken(ordinal=31, name="B.Cu", type="signal"),
    ] + [l for l in b.layers if l.ordinal > 31]
    b.setup.stackup = Stackup(layers=[
        StackupLayer(name="F.SilkS", type="Top Silk Screen"),
        StackupLayer(name="F.Paste", type="Top Solder Paste"),
        StackupLayer(name="F.Mask", type="Top Solder Mask", thickness=0.01),
        StackupLayer(name="F.Cu", type="copper", thickness=0.035),
        StackupLayer(name="dielectric 1", type="prepreg", thickness=0.1, material="FR4",
                     epsilonR=4.4, lossTangent=0.02),
        StackupLayer(name="In1.Cu", type="copper", thickness=0.0152),
        StackupLayer(name="dielectric 2", type="core", thickness=0.47, material="FR4",
                     epsilonR=4.6, lossTangent=0.02),
        StackupLayer(name="In2.Cu", type="copper", thickness=0.0152),
        StackupLayer(name="dielectric 3", type="prepreg", thickness=0.1, material="FR4",
                     epsilonR=4.4, lossTangent=0.02),
        StackupLayer(name="B.Cu", type="copper", thickness=0.035),
        StackupLayer(name="B.Mask", type="Bottom Solder Mask", thickness=0.01),
        StackupLayer(name="B.Paste", type="Bottom Solder Paste"),
        StackupLayer(name="B.SilkS", type="Bottom Silk Screen"),
    ], copperFinish="ENIG")
    names = sorted({n for c in COMPONENTS for n in c["nets"].values()})
    nets = {n: Net(number=i + 1, name=n) for i, n in enumerate(names)}
    b.nets = [Net(number=0, name="")] + [nets[n] for n in names]

    for ref, c in comps.items():
        X, Y, rot, side = plc[ref]
        fp = load_fp(c["fp"])
        for g in fp.graphicItems:
            to_v6(g)
        for g in fp.graphicItems:
            if type(g).__name__ == "FpText":
                if g.type == "reference":
                    g.text = ref
                    # 63 parts on 24 x 16.5 mm: designators would only overlap. The silkscreen keeps
                    # the ones a builder needs (connectors / wire pads J, switches S); every
                    # designator stays on the F.Fab / B.Fab layer (assembly PDFs).
                    if not ref.startswith(SILK_REFS):
                        g.hide = True
                elif g.type == "value":
                    g.text = c["value"]
        if side == "B":
            flip_fp(fp)
        x, y = K(X, Y)
        place_fp(fp, x, y, rot)
        fp.path = "/" + sym_uuid(ref)
        fp.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, "Aurora05_pcb/" + ref))
        # every pad and graphic item needs its own UUID: library footprints carry
        # fixed tstamps, and KiCad's DRC / connectivity confuse items that share one
        for n, pad in enumerate(fp.pads):
            pad.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"Aurora05_pcb/{ref}/pad/{n}"))
        for n, g in enumerate(fp.graphicItems):
            if hasattr(g, "tstamp"):
                g.tstamp = str(uuid.uuid5(uuid.NAMESPACE_URL, f"Aurora05_pcb/{ref}/gr/{n}"))
        fp.properties = {"Sheetfile": "Aurora_main.kicad_sch", "Sheetname": "",
                         "LCSC": c.get("lcsc", "")}
        for pad in fp.pads:
            net = c["nets"].get(str(pad.number))
            pad.net = copy.deepcopy(nets[net]) if net else None
        if c.get("external") or not c.get("lcsc"):
            fp.attributes.excludeFromBom = True
            fp.attributes.excludeFromPosFiles = True
        b.footprints.append(fp)

    pts = [K(x, y) for (x, y) in hj["pcb_outline"]]
    for i in range(len(pts)):
        a, c2 = pts[i], pts[(i + 1) % len(pts)]
        b.graphicItems.append(GrLine(start=Position(*a), end=Position(*c2), layer="Edge.Cuts",
                                     width=0.1, tstamp=str(uuid.uuid4())))
    notes = [
        (108.0, 89.0, "Aurora++ v0.5 main PCB  4 layers 0.8 mm  outline/edge parts from cad/housing_interface.json"),
        (108.0, 87.8, "ESP32-C3-MINI-1 antenna overhangs the rear (+x) edge - keep it free of copper and wires"),
        (108.0, 86.6, "Bottom side: USB-C, S1, charger, laser switch. Top side: module, LED driver, S2, RGB LED"),
    ]
    for (x, y, t) in notes:
        b.graphicItems.append(GrText(text=t, position=Position(x, y), layer="Cmts.User",
                                     effects=Effects(font=Font(height=0.7, width=0.7, thickness=0.1)),
                                     tstamp=str(uuid.uuid4())))
    b.graphicItems.append(GrText(text="AURORA++ v0.5", position=Position(*K(24.0, -7.6)),
                                 layer="B.SilkS",
                                 effects=Effects(font=Font(height=0.6, width=0.6, thickness=0.12)),
                                 tstamp=str(uuid.uuid4())))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "Aurora_main.kicad_pcb")
    b.to_file(path)
    top = {r: (x, y, rot) for r, (x, y, rot, s) in plc.items() if s == "F"}
    bottom = {r: (x, y, rot) for r, (x, y, rot, s) in plc.items() if s == "B"}
    return path, top, bottom, moved


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "kicad/Aurora_main"
    hj = sys.argv[2] if len(sys.argv) > 2 else "cad/housing_interface.json"
    p, t, bt, moved = build(out, hj, plot="placement_debug.png")
    for m in moved:
        print("moved", m)
    print("wrote", p, len(t), "top,", len(bt), "bottom")
