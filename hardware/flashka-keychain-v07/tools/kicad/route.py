#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Grid router for the FlashKa Keychain main PCB (4 layers) and, since v0.7, its key board.

  python3 tools/kicad/route.py kicad/FlashKa_main/FlashKa_main.kicad_pcb

Layers: F.Cu, In2.Cu and B.Cu carry tracks; In1.Cu is a solid GND plane that
every GND pad reaches through a short stub and a via ("fanout").  Each net is
routed as a tree: A* from the copper already connected to the nearest pad not
yet connected, on a 0.05 mm grid, with clearances taken from exact distance
fields (scipy EDT) of all foreign copper.  Wide nets (power) neck down to
0.2 mm only next to fine-pitch pads.  Nets that fail trigger rip-up and
reroute of the nets that block them.  Afterwards GND pours are added on every
layer, zones are filled and KiCad's own DRC checks the result.

v0.6 additions:
  * the A* inner loop runs in C (flashka_astar.c, compiled on first use; the Python loop is
    the fallback), distance maps are computed per search window and cached per copper state;
  * finalize(): monotonic window repair - for every incomplete net and every ground pad off
    the plane, rip the copper in a growing window (or the nets its path crosses) and let the
    ripped nets negotiate again; kept only if the weighted problem count goes down (or stays
    equal with a new set of problems, best state kept); then the clean-up and an exact
    shapely check of every copper-to-copper distance (>= 0.101 mm) with repair of offenders;
  * connectivity is checked twice: on the raster and on the exact copper shapes incl. the
    filled zones (exact_problems), so the written board agrees with KiCad's DRC;
  * `route.py --finish bare.kicad_pcb routed.kicad_pcb out.kicad_pcb` finishes an earlier
    result (also after small placement changes: copper that now hits a pad is dropped);
  * remove_islands(): routed copper that touches no pad of its net (rip-up left-overs) is
    removed before the last check, then remove_stubs() drops track pieces with an open end
    and vias that join one layer only, or cuts them back when they are needed
    (`route.py --clean bare routed out` does only these two steps);
  * In1 carries signals inside IN1_BOX only (the 0402 column next to the module, cost 4);
    VBAT is frozen as soon as it is routed.  When the window repair is stuck it first lets
    the remaining nets use In1 anywhere, then lets the windows rip VBAT too (both logged);
  * --finish loads the stage-1 copper in a canonical order (FLASHKA_LOAD_SEED picks another
    fixed order; build_all tries several), so the result depends on the copper only;
  * `route.py --refill board [out]` fills the zones again in a fresh process.

v0.7 additions:
  * the same router also routes the key board (`route.py --keys bare.kicad_pcb out.kicad_pcb`:
    full run, then finalize()); the main-board pre-routes (USB escape, ring-LED fan-out) are
    made only on a board that has the USB-C receptacle J1;
  * KiCad rule areas (keep-outs that forbid tracks / vias) are honoured: their cells, grown by
    KEEPOUT_GROW, are closed to tracks and vias on their layers (the key board's screw heads).
"""
import heapq
import json
import math
import os
import sys
import time

import numpy as np
import pcbnew
from matplotlib.path import Path as MPath
from scipy import ndimage

G = 0.05                 # grid pitch, mm
CLR = float(os.environ.get("FLASHKA_CLR", "0.115"))  # target copper clearance (JLCPCB multilayer min 0.09; DRC rule 0.10)
EDGE = 0.25              # copper to board edge (JLCPCB: 0.2)
MARGIN = float(os.environ.get("FLASHKA_MARGIN", "0.04"))   # raster error allowance for routed copper (on-grid tracks: <= 0.035)
PAD_EPS = 0.012          # pads use exact distance fields; allowance for diagonal track midpoints
VIA_D, VIA_DRILL = 0.45, 0.20      # JLCPCB: no surcharge for 0.2 mm holes with >= 0.45 mm pads
NPTH_CLR = 0.20          # JLCPCB: NPTH hole edge to copper 0.2 mm
PTH_HOLE_CLR = 0.28      # JLCPCB: plated pad hole edge to other nets' tracks 0.28 mm (board rule file)
PADHOLE_GAP = 0.45       # JLCPCB: pad hole to hole 0.45 mm (via drill to NPTH / PTH drill)
VIA_GAP = 0.20           # JLCPCB: via to via, hole edge to hole edge 0.2 mm
VIA_PITCH = VIA_DRILL + VIA_GAP + 0.03   # minimum via centre distance, any nets
EP_VIAS = {"U4": ("49", (-0.9875, 0.9875))}   # web centre lines between the 3 x 3 paste apertures
# v0.6: 0.12 / 0.13 mm (was 0.15 / 0.15): the pours reach into the 0402 rows and tie half of the
# ground pads that had no room for a via of their own (DRC 0.10 mm, min track 0.127 mm)
GND_POUR_CLR = float(os.environ.get("FLASHKA_POUR_CLR", "0.12"))  # GND pour clearance to other nets
GND_POUR_MIN = float(os.environ.get("FLASHKA_POUR_MIN", "0.13"))  # GND pour minimum width
VIA_COST = float(os.environ.get("FLASHKA_VIA_COST", "5"))    # in grid steps (v0.5: 10; v0.6 needs the inner layer more)
HIST_INC = float(os.environ.get("FLASHKA_HIST_INC", "1.5"))   # congestion history added per conflict (v0.5: 0.6)
PFAC_MAX = 250.0
LAYER_IDS = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
ROUTE = [0, 2, 3]
LAYER_COST = {0: 1.0, 2: 1.0, 3: 1.0}
# v0.6 (FLASHKA_IN1 = "X0,Y0,X1,Y1", housing mm; "" = off): signal tracks may also use In1 inside
# this rectangle (the 0402 column between the USB-C shell and the module), at a high cost - the
# ground plane keeps everything else (see the design report)
IN1_BOX = [float(v) for v in os.environ.get("FLASHKA_IN1", "19.0,-7.6,24.3,7.6").split(",") if v]
if IN1_BOX:
    ROUTE = [0, 1, 2, 3]
    LAYER_COST[1] = float(os.environ.get("FLASHKA_IN1_COST", "4.0"))
# v0.7 power stage (LED up to 3.0 A, 3.5 A full scale): 0.8 mm for the battery, LED and switch
# paths, 1.0 mm for the cell minus (BATN, one layer only); the pours of LOCAL_ZONES widen them
# (not BATN: the DW01A senses at Q3's pin, so its BAT- copper is one hand-made 1 mm track)
WIDTH = {"VOUT": 0.8, "SW": 0.8, "ISNS": 0.8, "VBAT": 0.8, "BATN": 1.0, "VBUS": 0.25, "3V3": 0.25,
         "LASER_P": 0.2, "GND": 0.25}
# high-current branches: full width only between these parts' pads (a "REF.PAD" entry names one
# pad: U2's DEF and AVIN pins are VBAT too, but carry no current), the low-current branches of the
# same net (dividers, op-amp input, LDO, charger, protection IC) get LOW_W
POWER_REFS = {"VBAT": {"J2", "U2.11", "U2.12", "C5"}, "VOUT": {"L1", "C8", "C22", "J3"},
              "ISNS": {"J3", "RS1"}, "BATN": {"J2", "Q3"}}
LOW_W = {"VBAT": 0.25, "VOUT": 0.2, "ISNS": 0.2, "BATN": 0.25}
SIGNAL_W = 0.13
NECK_W = 0.2
# v0.6: narrowest width a net may take to avoid ripping other nets (the high-current
# branches in POWER_REFS never narrow for that reason)
MIN_AVOID_W = {"VBUS": 0.2, "3V3": 0.2, "LASER_P": 0.2, "VBAT": 0.2, "VOUT": 0.2, "ISNS": 0.2,
               "BATN": 0.2}
AVOID_RIPS = os.environ.get("FLASHKA_AVOID_RIPS", "1") != "0"
ADAPTIVE_ORDER = os.environ.get("FLASHKA_ADAPTIVE_ORDER", "1") != "0"
GND_VIAS_UNDER_J1 = os.environ.get("FLASHKA_GND_VIAS_UNDER_J1", "1") != "0"
PF_ITERS = int(os.environ.get("FLASHKA_PF_ITERS", "30"))         # PathFinder rounds (0 = v0.5 loop only)
PF_GROWTH = float(os.environ.get("FLASHKA_PF_GROWTH", "1.3"))
PF_NEIGHBOURS = float(os.environ.get("FLASHKA_PF_NEIGHBOURS", "0"))   # mm: also re-route nets this close to a conflict
PF_PFAC_AFTER = float(os.environ.get("FLASHKA_PF_PFAC_AFTER", "30"))
PF_GND = os.environ.get("FLASHKA_PF_GND", "0") == "1"
# v0.6: the search counts a cell as "in conflict" from cell-centre distances, commit() tests the
# exact segment; the segment can pass up to ~G/2 closer to foreign copper than the nearest cell
# centre, so without this pad the negotiation saw no conflict where commit() refused one
CONF_PAD = float(os.environ.get("FLASHKA_CONF_PAD", "0"))
GND_RESERVE = float(os.environ.get("FLASHKA_GND_RESERVE", "0"))   # history added on the trial GND stub + via of every pad
GRID_ALIGN = os.environ.get("FLASHKA_GRID_ALIGN", "0") == "1"
USB_FIRST = os.environ.get("FLASHKA_USB_FIRST", "1") != "0"   # route + lock USB D+/D- before everything else   # GND pad stubs + vias take part in the PathFinder phase
NECK_R = 0.7             # neck-down allowed this close to the pads being joined
KEEPOUT_GROW = 0.30      # v0.7: rule-area keep-outs grown by half a via + raster margin (exact DRC)
POWER_ORDER = ["SW", "VOUT", "ISNS", "BATN", "VBAT", "VBUS", "3V3", "LASER_P"]
FREEZE = os.environ.get("FLASHKA_FREEZE", "SW,VOUT,ISNS,BATN,VBAT").split(",")   # once routed, these keep their copper
FREEZE_EARLY = [n for n in os.environ.get("FLASHKA_FREEZE_EARLY", "VBAT").split(",") if n]   # frozen as soon as routed
REPAIR_SEED = int(os.environ.get("FLASHKA_REPAIR_SEED", "0"))   # congestion shake of the window repair
LOAD_SEED = int(os.environ.get("FLASHKA_LOAD_SEED", "0"))       # order of the stage-1 copper in --finish
FREEZE_ALL_AFTER = int(os.environ.get("FLASHKA_FREEZE_ALL_AFTER", "10"))
POWER_GND = ["C5", "C8", "C22", "RS1", "Q3"]   # GND pads with their own via, placed first (high current)
# local pours (net, layer, [(ref, pad), ...], priority) - buck power stage, sense path, cell minus
LOCAL_ZONES = [
    ("SW", pcbnew.F_Cu, [("U2", "1"), ("U2", "2"), ("L1", "1")], 5),
    ("VOUT", pcbnew.F_Cu, [("L1", "2"), ("C8", "1"), ("C22", "1")], 4),
    ("VBAT", pcbnew.F_Cu, [("U2", "10"), ("U2", "11"), ("U2", "12"), ("C5", "1")], 4),
    ("GND", pcbnew.F_Cu, [("U2", "14"), ("U2", "15"), ("U2", "17")], 3),
    ("ISNS", pcbnew.F_Cu, [("J3", "2"), ("RS1", "1")], 4),
    ("VOUT", pcbnew.In2_Cu, [("J3", "1"), ("L1", "2"), ("C22", "1")], 4),
]
# Kelvin pads of the cell protection's current sense (v0.7): R36's ground end joins Q3's P- pin
# through its own hand-made stub and nothing else - the ground routing keeps off it (fields) and
# the ground pours leave it out (a no-pour rule area, add_zones)
KELVIN_PADS = {("R36", "2")}


def mm(v):
    return pcbnew.ToMM(v)


# v0.6: the A* inner loop in C (tools/kicad/flashka_astar.c, built with the system compiler on
# first use into __pycache__); FLASHKA_PY_ASTAR=1 or no compiler -> the Python loop below
_CLIB = None


def _clib():
    global _CLIB
    if _CLIB is None:
        _CLIB = False
        if os.environ.get("FLASHKA_PY_ASTAR", "0") != "1":
            try:
                import ctypes
                import hashlib
                import subprocess
                here = os.path.dirname(os.path.abspath(__file__))
                src = os.path.join(here, "flashka_astar.c")
                tag = hashlib.sha1(open(src, "rb").read()).hexdigest()[:12]
                so = os.path.join(here, "__pycache__", f"flashka_astar_{tag}.so")
                if not os.path.exists(so):
                    os.makedirs(os.path.dirname(so), exist_ok=True)
                    tmp = so + f".{os.getpid()}.tmp"
                    subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", tmp, src], check=True,
                                   capture_output=True)
                    os.replace(tmp, so)
                lib = ctypes.CDLL(so)
                P = ctypes.c_void_p
                I, D, LG = ctypes.c_int, ctypes.c_double, ctypes.c_long
                lib.astar.restype = LG
                lib.astar.argtypes = [I, I, I, P, P, P, P, P, P, P, P, I, I, I, I, I, I, I, I, I,
                                      P, D, D, I, LG, D, I, P, I, P, P]
                _CLIB = lib
            except Exception as e:      # noqa: BLE001
                print("route.py: C A* not available, using the Python loop:", e, file=sys.stderr)
    return _CLIB or None


class Router:
    def __init__(self, path):
        self.path = path
        self.board = pcbnew.LoadBoard(path)
        bb = self.board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = mm(bb.GetX()) - 0.2, mm(bb.GetY()) - 0.2
        if GRID_ALIGN:
            # v0.6: cell centres on multiples of G (parts sit on a 0.05 / 0.025 mm raster), so a
            # 0.13 mm track runs exactly through the middle of a 0.4 mm gap between two pads (module
            # pads at 0.8 mm pitch, 0402 pads); half a cell off, the gap was closed to the search
            self.x0 = math.floor(self.x0 / G + 1e-9) * G - G / 2
            self.y0 = math.floor(self.y0 / G + 1e-9) * G - G / 2
        self.nx = int(math.ceil((mm(bb.GetWidth()) + 0.5) / G))
        self.ny = int(math.ceil((mm(bb.GetHeight()) + 0.5) / G))
        self.xc = self.x0 + (np.arange(self.nx) + 0.5) * G
        self.yc = self.y0 + (np.arange(self.ny) + 0.5) * G
        self.nets = {}
        for name, net in self.board.GetNetsByName().items():
            n = str(name)
            if n:
                self.nets[n] = net.GetNetCode()
        self.code_name = {c: n for n, c in self.nets.items()}
        # pad copper (static) and routed copper (dynamic): netcode, 0 free, -1 obstacle
        self.owner = np.zeros((4, self.ny, self.nx), dtype=np.int32)       # pads / holes
        self.trk = np.zeros((4, self.ny, self.nx), dtype=np.int32)         # tracks / vias
        self.H = np.zeros((4, self.ny, self.nx), dtype=np.float32)         # congestion history
        self.cid = np.zeros((4, self.ny, self.nx), dtype=np.int32)         # connection id of routed copper
        self.conns = {}                                                     # cid -> (netcode, items)
        self.next_cid = 1
        self.smd_own = np.zeros((self.ny, self.nx), dtype=np.int32)   # SMD pad copper (any layer) - no vias in pads
        self.holes = []         # pad drills: (ax, ay, bx, by, radius, is_npth)
        self.pth_holes = []     # plated pad drills with their net: (ax, ay, bx, by, radius, netcode or -1)
        self.pour = None        # filled GND pour outline ids per layer (KiCad fill, see pour_fill)
        self.pour_area, self.pour_merge = {}, []
        self.pad_polys = []     # (layer, polygon, netcode or -1) of every copper pad
        self.pads = {}          # netcode -> list of pad dicts
        self._outline()
        self.in1_mask = np.zeros((self.ny, self.nx), dtype=bool)
        if IN1_BOX:
            X0, Y0, X1, Y1 = IN1_BOX           # housing -> KiCad: x = 100 + X, y = 100 - Y
            xm = (self.xc >= 100 + X0) & (self.xc <= 100 + X1)
            ym = (self.yc >= 100 - Y1) & (self.yc <= 100 - Y0)
            self.in1_mask = ym[:, None] & xm[None, :]
        self.in1_rescue = set()  # nets the window repair let onto In1 everywhere (last resort)
        self._pads()
        self._keepouts()
        self._exact_pad_fields()
        # exact distance from every cell centre to the nearest drill edge
        X, Y = np.meshgrid(self.xc, self.yc)
        self.D_npth = np.full((self.ny, self.nx), 99.0)
        self.D_padhole = np.full((self.ny, self.nx), 99.0)
        for (ax, ay, bx, by, r, npth) in self.holes:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = np.zeros_like(X) if L2 < 1e-12 else np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
            d = np.hypot(X - ax - t * dx, Y - ay - t * dy) - r
            self.D_padhole = np.minimum(self.D_padhole, d)
            if npth:
                self.D_npth = np.minimum(self.D_npth, d)
        self._pth_cache = {}

    def pth_dist(self, code):
        """Exact distance from every cell centre to the nearest plated pad drill of another net
        (the board rule file asks 0.28 mm from a plated hole to other copper; the pad's own net
        may run over its holes).  One map per net that owns plated pads, one for all others."""
        own = {h[5] for h in self.pth_holes if h[5] > 0}
        key = code if code in own else None
        if key not in self._pth_cache:
            X, Y = np.meshgrid(self.xc, self.yc)
            D = np.full((self.ny, self.nx), 99.0)
            for (ax, ay, bx, by, r, c) in self.pth_holes:
                if key is not None and c == key:
                    continue
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = np.zeros_like(X) if L2 < 1e-12 else np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
                D = np.minimum(D, np.hypot(X - ax - t * dx, Y - ay - t * dy) - r)
            self._pth_cache[key] = D
        return self._pth_cache[key]

    def pth_gap(self, x, y, code):
        """Exact distance from a point to the nearest plated pad drill of another net."""
        best = 99.0
        for (ax, ay, bx, by, r, c) in self.pth_holes:
            if c == code and c > 0:
                continue
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-12 else min(max(((x - ax) * dx + (y - ay) * dy) / L2, 0.0), 1.0)
            best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy) - r)
        return best

    # ------------------------------------------------------------------ setup
    def ij(self, x, y):
        return int((x - self.x0) / G), int((y - self.y0) / G)

    def xy(self, i, j):
        return self.x0 + (i + 0.5) * G, self.y0 + (j + 0.5) * G

    def _poly_mask(self, pts, grow=0.0):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        i0, j0 = self.ij(min(xs) - grow - G, min(ys) - grow - G)
        i1, j1 = self.ij(max(xs) + grow + G, max(ys) + grow + G)
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1 + 1, self.nx), min(j1 + 1, self.ny)
        X, Y = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
        m = MPath(pts).contains_points(np.c_[X.ravel(), Y.ravel()], radius=-2 * grow if grow else 0.0)
        return (j0, j1, i0, i1), m.reshape(X.shape)

    def _outline(self):
        pts = []
        for d in self.board.GetDrawings():
            if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() == "PCB_SHAPE":
                pts.append((mm(d.GetStart().x), mm(d.GetStart().y)))
        # order the outline vertices (segments are stored head-to-tail)
        segs = [((mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y)))
                for d in self.board.GetDrawings()
                if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() == "PCB_SHAPE"]
        poly = [segs[0][0], segs[0][1]]
        rest = segs[1:]
        while rest:
            for k, (a, b) in enumerate(rest):
                if math.dist(a, poly[-1]) < 1e-4:
                    poly.append(b)
                    rest.pop(k)
                    break
                if math.dist(b, poly[-1]) < 1e-4:
                    poly.append(a)
                    rest.pop(k)
                    break
            else:
                break
        self.outline = poly
        X, Y = np.meshgrid(self.xc, self.yc)
        inside = MPath(poly).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
        self.inside = inside
        self.d_edge = ndimage.distance_transform_edt(inside) * G - G / 2

    def _keepouts(self):
        """No tracks or vias under the bodies of parts that sit flat on the
        board (USB-C shell, switches, inductor): core of the courtyard,
        except around the part's own pads."""
        KEEP = {"J1": (3, 0.55), "S2": (0, 0.5), "L1": (0, 0.35)}
        self.keep = np.zeros((4, self.ny, self.nx), dtype=bool)
        # v0.6: under the USB-C shell (GND) tented GND vias are harmless; other vias stay out
        self.gnd_via_ok = np.zeros((self.ny, self.nx), dtype=bool)
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            if ref not in KEEP:
                continue
            k, shrink = KEEP[ref]
            cy = fp.GetCourtyard(LAYER_IDS[0] if k == 0 else pcbnew.B_CrtYd if False else
                                 (pcbnew.F_CrtYd if k == 0 else pcbnew.B_CrtYd))
            bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
            x0, y0 = mm(bb.GetLeft()) + shrink, mm(bb.GetTop()) + shrink
            x1, y1 = mm(bb.GetRight()) - shrink, mm(bb.GetBottom()) - shrink
            i0, j0 = self.ij(x0, y0)
            i1, j1 = self.ij(x1, y1)
            m = np.zeros((self.ny, self.nx), dtype=bool)
            m[max(j0, 0):max(j1, 0), max(i0, 0):max(i1, 0)] = True
            own = np.zeros((self.ny, self.nx), dtype=bool)
            for pad in fp.Pads():
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                for poly in self._pad_poly(pad, LAYER_IDS[k] if k in (0, 3) else pcbnew.F_Cu):
                    (a0, a1, b0, b1), pm = self._poly_mask(poly)
                    own[a0:a1, b0:b1] |= pm
            own = ndimage.binary_dilation(own, iterations=int(0.45 / G))
            self.keep[k] |= m & ~own
            if ref == "J1" and GND_VIAS_UNDER_J1:
                self.gnd_via_ok |= m & ~own
        # the D+/D- escape behind the USB-C pads stays allowed (pre-routed)
        # v0.7: rule areas that forbid tracks or vias (key board: screw heads and floor bosses)
        for z in self.board.Zones():
            if not z.GetIsRuleArea() or not (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
                continue
            ol = z.Outline()
            for n in range(ol.OutlineCount()):
                o = ol.Outline(n)
                pts = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
                (j0, j1, i0, i1), pm = self._poly_mask(pts, grow=KEEPOUT_GROW)
                for k, lid in enumerate(LAYER_IDS):
                    if z.IsOnLayer(lid):
                        self.keep[k, j0:j1, i0:i1] |= pm

    def _pad_poly(self, pad, layer):
        ps = pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.005))
        out = []
        for k in range(ps.OutlineCount()):
            o = ps.Outline(k)
            out.append([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())])
        return out

    def _add_hole(self, pad, npth):
        """Record a pad's drill (round or slot) as a capsule."""
        hs = pad.GetEffectiveHoleShape()
        seg = hs.GetSeg()
        self.holes.append((mm(seg.A.x), mm(seg.A.y), mm(seg.B.x), mm(seg.B.y), mm(hs.GetWidth()) / 2, npth))

    def _pads(self):
        for pad in self.board.GetPads():
            attr = pad.GetAttribute()
            code = pad.GetNetCode()
            if attr == pcbnew.PAD_ATTRIB_NPTH:
                x, y = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
                r = mm(pad.GetDrillSizeX()) / 2
                self._mark_circle(range(4), x, y, r, -1)
                self._add_hole(pad, True)
                continue
            layers = [k for k, lid in enumerate(LAYER_IDS) if pad.IsOnLayer(lid)]
            if attr == pcbnew.PAD_ATTRIB_PTH:
                layers = [0, 1, 2, 3]
                self._add_hole(pad, False)
                self.pth_holes.append(self.holes[-1][:5] + (code if code > 0 else -1,))
            if not layers:
                continue            # paste / mask aperture pads (no copper)
            cells = []
            for k in layers:
                for poly in self._pad_poly(pad, LAYER_IDS[k] if k in (0, 3) else pcbnew.F_Cu):
                    self.pad_polys.append((k, poly, code if code > 0 else -1))
                    (j0, j1, i0, i1), m = self._poly_mask(poly)
                    if code > 0 or attr == pcbnew.PAD_ATTRIB_PTH:
                        sub = self.owner[k, j0:j1, i0:i1]
                        sub[m] = code if code > 0 else -1
                    else:
                        self.owner[k, j0:j1, i0:i1][m] = -1     # unconnected pads are obstacles
                    if attr == pcbnew.PAD_ATTRIB_SMD:
                        self.smd_own[j0:j1, i0:i1][m] = max(code, 1)
                    jj, ii = np.nonzero(m)
                    cells.extend(zip([k] * len(jj), (jj + j0).tolist(), (ii + i0).tolist()))
            if code <= 0:
                continue
            fp = pad.GetParent()
            size = min(mm(pad.GetSizeX()), mm(pad.GetSizeY()))
            self.pads.setdefault(code, []).append({
                "ref": fp.GetReference(), "num": pad.GetNumber(),
                "x": mm(pad.GetPosition().x), "y": mm(pad.GetPosition().y),
                "layers": layers, "cells": cells, "fine": size < 0.5,
                "pth": attr == pcbnew.PAD_ATTRIB_PTH})

    def _exact_pad_fields(self, reach=1.2):
        """Exact distance from every cell centre to the nearest pad copper,
        kept as the two nearest nets per cell (PD1/PN1, PD2/PN2), so the
        distance to the nearest *foreign* pad of any net is one lookup."""
        shp = (4, self.ny, self.nx)
        self.PD1 = np.full(shp, 99.0, dtype=np.float32)
        self.PD2 = np.full(shp, 99.0, dtype=np.float32)
        self.PN1 = np.full(shp, -2, dtype=np.int32)
        self.PN2 = np.full(shp, -2, dtype=np.int32)
        for (k, poly, net) in self.pad_polys:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            i0, j0 = self.ij(min(xs) - reach, min(ys) - reach)
            i1, j1 = self.ij(max(xs) + reach, max(ys) + reach)
            i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1 + 1, self.nx), min(j1 + 1, self.ny)
            if i1 <= i0 or j1 <= j0:
                continue
            X, Y = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
            P = np.array(poly + [poly[0]])
            d = np.full(X.shape, 99.0)
            for (ax, ay), (bx, by) in zip(P[:-1], P[1:]):
                dx, dy = bx - ax, by - ay
                L2 = dx * dx + dy * dy
                t = np.zeros_like(X) if L2 < 1e-12 else np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
                d = np.minimum(d, np.hypot(X - ax - t * dx, Y - ay - t * dy))
            inside = MPath(poly).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
            d[inside] = 0.0
            d = d.astype(np.float32)
            D1 = self.PD1[k, j0:j1, i0:i1]
            D2 = self.PD2[k, j0:j1, i0:i1]
            N1 = self.PN1[k, j0:j1, i0:i1]
            N2 = self.PN2[k, j0:j1, i0:i1]
            m1 = N1 == net
            m2 = ~m1 & (N2 == net)
            m3 = ~m1 & ~m2
            D1[m1] = np.minimum(D1[m1], d[m1])
            D2[m2] = np.minimum(D2[m2], d[m2])
            sw = m2 & (D2 < D1)
            if sw.any():
                a, b = D1[sw].copy(), N1[sw].copy()
                D1[sw], N1[sw] = D2[sw], N2[sw]
                D2[sw], N2[sw] = a, b
            c1 = m3 & (d < D1)
            c2 = m3 & ~c1 & (d < D2)
            if c1.any():
                D2[c1], N2[c1] = D1[c1], N1[c1]
                D1[c1], N1[c1] = d[c1], net
            if c2.any():
                D2[c2], N2[c2] = d[c2], net

    def pad_dist(self, k, code):
        """Exact distance to the nearest pad copper of another net (or no net)."""
        return np.where(self.PN1[k] == code, self.PD2[k], self.PD1[k])

    def _mark_circle(self, layers, x, y, r, code, arr=None):
        i0, j0 = self.ij(x - r - G, y - r - G)
        i1, j1 = self.ij(x + r + G, y + r + G)
        i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1 + 1, self.nx), min(j1 + 1, self.ny)
        X, Y = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
        m = (X - x) ** 2 + (Y - y) ** 2 <= r * r
        arr = self.owner if arr is None else arr
        for k in layers:
            if code is not None:
                arr[k, j0:j1, i0:i1][m] = code
        jj, ii = np.nonzero(m)
        return [(k, j0 + a, i0 + b) for k in layers for a, b in zip(jj.tolist(), ii.tolist())]

    def _mark_segment(self, k, x1, y1, x2, y2, w, code, arr=None):
        r = w / 2
        i0, j0 = self.ij(min(x1, x2) - r - G, min(y1, y2) - r - G)
        i1, j1 = self.ij(max(x1, x2) + r + G, max(y1, y2) + r + G)
        i0, j0, i1, j1 = max(i0, 0), max(j0, 0), min(i1 + 1, self.nx), min(j1 + 1, self.ny)
        X, Y = np.meshgrid(self.xc[i0:i1], self.yc[j0:j1])
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            t = np.zeros_like(X)
        else:
            t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1)
        d2 = (X - x1 - t * dx) ** 2 + (Y - y1 - t * dy) ** 2
        m = d2 <= r * r
        arr = self.owner if arr is None else arr
        if code is not None:
            arr[k, j0:j1, i0:i1][m] = code
        jj, ii = np.nonzero(m)
        return [(k, j0 + a, i0 + b) for a, b in zip(jj.tolist(), ii.tolist())]

    # ------------------------------------------------------------- legality
    def _dist_maps(self, code, S):
        """Distance maps of one window for a net (independent of the track width): exact pad
        distance, distance to frozen / locked copper, distance to other nets' soft copper per
        layer, plus the width-independent via rules."""
        d_edge = self.d_edge[S]
        # tracks: NPTH edge >= NPTH_CLR and other nets' plated pad holes >= PTH_HOLE_CLR (+0.01
        # more for the straight runs between cell centres), one map for the width test below
        D_npth = np.minimum(self.D_npth[S], self.pth_dist(code)[S] - (PTH_HOLE_CLR + 0.01 - NPTH_CLR))
        vbase = d_edge >= VIA_D / 2 + EDGE + MARGIN
        vbase &= self.D_padhole[S] >= VIA_DRILL / 2 + PADHOLE_GAP + 0.01
        vbase &= ~self.via_block(S)
        vbase &= self.smd_far[S]
        frozen = self.frozen_mask(code, S)
        trk = self.trk[(slice(None),) + S]
        keep = self.keep[(slice(None),) + S]
        big = np.full(vbase.shape, 99.0)
        Dp, Df, Dt = [], [], []
        for k in range(4):
            Dp.append(self.pad_dist(k, code)[S])
            if k == 1 and 1 not in ROUTE:
                # In1 carries only vias (drawn on every layer) besides the plated pads (exact pad
                # field): its copper distances are those of the other layers - skip the EDTs
                Df.append(big)
                Dt.append(big)
            else:
                ft = (trk[k] != 0) & (trk[k] != code) & ~frozen[k]
                Df.append((ndimage.distance_transform_edt(~frozen[k]) * G - 0.01) if frozen[k].any() else big)
                Dt.append(ndimage.distance_transform_edt(~ft) * G if ft.any() else big)
            if code == self.nets.get("GND"):
                vbase &= ~(keep[k] & ~self.gnd_via_ok[S])
            else:
                vbase &= ~keep[k]
        return d_edge, D_npth, vbase, keep, Dp, Df, Dt

    def fields(self, code, w, win=None, cache=None):
        """Hard legality (pads, holes, edge, frozen copper) and soft conflicts
        (other nets' tracks) for a net of width w; returns dicts per routing
        layer.  Pads: exact distances; routed copper: raster EDT + MARGIN.
        win (v0.6): only this window (+1 mm, more than any clearance distance) is computed,
        everything outside it comes back blocked.  cache (v0.6): dict for the distance maps of
        one unchanged copper state (route_net: all widths and windows of one search)."""
        if win is not None:
            m = int(1.0 / G)
            j0, j1 = max(win[0] - m, 0), min(win[1] + m, self.ny)
            i0, i1 = max(win[2] - m, 0), min(win[3] + m, self.nx)
            S = (slice(j0, j1), slice(i0, i1))
        else:
            S = (slice(0, self.ny), slice(0, self.nx))
        key = (code, S[0].start, S[0].stop, S[1].start, S[1].stop)
        if cache is not None and key in cache:
            maps = cache[key]
        else:
            maps = self._dist_maps(code, S)
            if cache is not None:
                cache[key] = maps
        d_edge, D_npth, vbase, keep, Dp, Df, Dt = maps
        need_p, need_pn = w / 2 + CLR + PAD_EPS, NECK_W / 2 + CLR + PAD_EPS
        need, need_n = w / 2 + CLR + MARGIN, NECK_W / 2 + CLR + MARGIN
        edge_ok = (d_edge >= w / 2 + EDGE + MARGIN) & (D_npth >= w / 2 + NPTH_CLR + 0.01)
        edge_ok_n = (d_edge >= NECK_W / 2 + EDGE + MARGIN) & (D_npth >= NECK_W / 2 + NPTH_CLR + 0.01)
        hard, hard_n, conf, conf_n = {}, {}, {}, {}
        rv, rvp = VIA_D / 2 + CLR + MARGIN, VIA_D / 2 + CLR + PAD_EPS
        via_hard = vbase.copy()
        via_conf = np.zeros(vbase.shape, dtype=bool)
        for k in range(4):
            via_hard &= (Dp[k] >= rvp) & (Df[k] >= rv)
            via_conf |= Dt[k] < rv + CONF_PAD
            if k in ROUTE:
                hard[k] = (Dp[k] >= need_p) & (Df[k] >= need) & edge_ok & ~keep[k]
                hard_n[k] = (Dp[k] >= need_pn) & (Df[k] >= need_n) & edge_ok_n & ~keep[k]
                if k == 1:
                    box = False if code == self.nets.get("GND") else \
                        (True if code in self.in1_rescue else self.in1_mask[S])
                    hard[k] &= box
                    hard_n[k] &= box
                conf[k] = Dt[k] < need + CONF_PAD
                conf_n[k] = Dt[k] < need_n + CONF_PAD
        kd = getattr(self, "kelvin_dist", None)
        if kd is not None and code == self.nets.get("GND") and 3 in hard:
            kd = kd[S]          # the Kelvin copper (bottom face) is a foreign net for the ground routing
            hard[3] &= kd >= need
            hard_n[3] &= kd >= need_n
            via_hard &= kd >= rv
        if win is not None:
            def full(a):
                o = np.zeros((self.ny, self.nx), dtype=bool)
                o[S] = a
                return o
            hard = {k: full(v) for k, v in hard.items()}
            hard_n = {k: full(v) for k, v in hard_n.items()}
            conf = {k: full(v) for k, v in conf.items()}
            conf_n = {k: full(v) for k, v in conf_n.items()}
            via_hard, via_conf = full(via_hard), full(via_conf)
        return hard, hard_n, conf, conf_n, via_hard, via_conf

    def frozen_mask(self, code, S=None):
        """Routed copper of frozen nets and locked connections (not rippable)
        acts like pads for every other net (S: window slices)."""
        trk = self.trk if S is None else self.trk[(slice(None),) + S]
        cid = self.cid if S is None else self.cid[(slice(None),) + S]
        m = np.zeros(trk.shape, dtype=bool)
        if self.frozen:
            m |= np.isin(trk, [c for c in self.frozen if c != code])
        if self.locked:
            m |= np.isin(cid, list(self.locked)) & (trk != code)
        return m

    def all_vias(self):
        """(x, y, netcode) of every committed via (and, during the PathFinder phase, of the
        vias the nets of that phase hold)."""
        out = [(d[0], d[1], n) for (n, items) in self.conns.values() for (kind, d) in items if kind == "via"]
        for n, items_list in getattr(self, "_pf_conns", {}).items():
            code = self.nets["GND"] if n.startswith("GND:") else self.nets[n]
            out += [(d[0], d[1], code) for items in items_list for (kind, d) in items if kind == "via"]
        return out

    def via_block(self, S=None):
        """Cells whose centre is closer than VIA_PITCH to a committed via
        (hole-to-hole spacing applies to all vias, same net included).  S: window slices
        (v0.6: only the vias near the window are drawn, result is the window's shape)."""
        if S is None:
            S = (slice(0, self.ny), slice(0, self.nx))
        j0, j1, i0, i1 = S[0].start, S[0].stop, S[1].start, S[1].stop
        xa, xb = self.x0 + j0 * 0 + i0 * G - VIA_PITCH, self.x0 + i1 * G + VIA_PITCH
        ya, yb = self.y0 + j0 * G - VIA_PITCH, self.y0 + j1 * G + VIA_PITCH
        tmp = np.zeros((1, self.ny, self.nx), dtype=np.int8)
        for (x, y, _n) in self.all_vias():
            if xa <= x <= xb and ya <= y <= yb:
                self._mark_circle([0], x, y, VIA_PITCH - 1e-6, 1, tmp)
        return tmp[0][S] != 0

    def preroute(self, name, items):
        """Add hand-made copper for a net (locked)."""
        code = self.nets[name]
        cid = self.next_cid
        self.next_cid += 1
        self.conns[cid] = (code, items)
        for (k, j, i) in self.raster_items(items, code, self.trk):
            self.cid[k, j, i] = cid
        self.locked.add(cid)
        # v0.6: remembered, so prune() can lock them again after it rebuilds the tables
        if not hasattr(self, "pre_items"):
            self.pre_items = set()
        self.pre_items |= {(code, it) for it in items}
        return cid

    def has_part(self, ref):
        return any(p["ref"] == ref for ps in self.pads.values() for p in ps)

    def pad_xy(self, ref, num):
        for ps in self.pads.values():
            for p in ps:
                if p["ref"] == ref and p["num"] == num:
                    return p["x"], p["y"]
        raise KeyError((ref, num))

    def preroute_usb(self):
        """USB-C D+/D- escape (pads interleaved B6 A7 A6 B7), v0.7: both pairs join on B.Cu without
        vias, so the top face over the receptacle's pin row stays free for the buck stage (U2, C5):
        D- joins A7-B7 with a U behind the pin row (the router takes it from there), D+ joins B6-A6
        with a U in front of it (under the receptacle body) and leaves on B.Cu below the right peg
        to the edge of the receptacle's keep-out (the router cannot route under J1)."""
        from gen_pcb import USB_DN_BACK, USB_DP_FRONT, USB_DP_EXIT, USB_PAD_HALF
        if not self.has_part("J1"):
            return                    # v0.7: key board (no USB-C receptacle)
        ya = self.pad_xy("J1", "A6")[1]
        y_in = ya - USB_PAD_HALF              # inner pad end (towards the board centre)
        y_out = ya + USB_PAD_HALF             # outer pad end (under the receptacle body)
        xa6, xb6 = self.pad_xy("J1", "A6")[0], self.pad_xy("J1", "B6")[0]
        xa7, xb7 = self.pad_xy("J1", "A7")[0], self.pad_xy("J1", "B7")[0]
        yn, yp = y_in - USB_DN_BACK, y_out + USB_DP_FRONT
        (xt, yt, xe) = USB_DP_EXIT             # turn-down x, run y below the right peg, end x
        w = SIGNAL_W
        dn = [("seg", (3, xa7, ya, xa7, yn, w)), ("seg", (3, xa7, yn, xb7, yn, w)),
              ("seg", (3, xb7, yn, xb7, ya, w))]
        dp = [("seg", (3, xb6, ya, xb6, yp, w)), ("seg", (3, xb6, yp, xa6, yp, w)),
              ("seg", (3, xa6, ya, xa6, yp, w)), ("seg", (3, xa6, yp, xt, yp, w)),
              ("seg", (3, xt, yp, xt, yt, w)), ("seg", (3, xt, yt, xe, yt, w))]
        for net, items in (("USB_DN", dn), ("USB_DP", dp)):
            err = self._items_ok(self.nets[net], items)
            if err:
                raise RuntimeError(f"USB {net} escape: {err}")
        self.preroute("USB_DP", dp)
        self.preroute("USB_DN", dn)
        # CC1: pin A5 straight back to its pull-down R1 (placed right behind it), before the D-
        # route can take the way
        if self.has_part("R1") and "CC1" in self.nets:
            xa5, ya5 = self.pad_xy("J1", "A5")
            xr, yr = self.pad_xy("R1", "1")
            cc = [("seg", (3, xa5, ya5, xa5, yr, w)), ("seg", (3, xa5, yr, xr, yr, w))]
            if not self._items_ok(self.nets["CC1"], cc):
                self.preroute("CC1", cc)
        # 1000 lm power stage: CC2 likewise, pin B5 straight back to R2 (otherwise the D- route,
        # laid first, may leave behind the pin row towards the front and close it off)
        if self.has_part("R2") and "CC2" in self.nets:
            xb5, yb5 = self.pad_xy("J1", "B5")
            xr2, yr2 = self.pad_xy("R2", "1")
            x2 = xb5 + 0.05
            cc = [("seg", (3, x2, yb5, x2, yr2 + 0.4, w)), ("seg", (3, x2, yr2 + 0.4, xr2, yr2, w))]
            if not self._items_ok(self.nets["CC2"], cc):
                self.preroute("CC2", cc)

    def preroute_buck(self, log=print):
        """v0.7: escapes of the buck U2 (TPS62095, VQFN-16, rotated 90 deg between the USB-C pegs)
        and the LED+ path.  U2 sits over the receptacle's pin row on the other face, where no via
        fits: EN runs up past C5 to a via in front of the receptacle, VOS below the left peg into the
        LED+ wire pad J3.1, DEF (VBAT) past the end of L1's switch pad to a via above the rear-lower
        shell leg, FB below the right peg to a via below the rear-upper leg (with the divider R11 /
        R10 on it).  LED+ leaves the output pour through four vias to a 1.2 mm In2 track that ends
        at the four vias of J3.1.  The router joins the other vias on the inner layer.  Also
        hand-made: the VBAT trunk (cell pad -> buck), the cell protection U6/Q3/R35/R36/C24 beside
        the cell pads and the supply pins of the LDO U5."""
        if not self.has_part("U2"):
            return 0
        try:
            cx, cy = self.pad_xy("U2", "17")
            self.pad_xy("U2", "13"), self.pad_xy("U2", "16"), self.pad_xy("U2", "3")
        except KeyError:
            return 0
        # only for the v0.7 orientation: EN (pin 13) left of the centre, DEF (pin 3) below it
        ex, ey = self.pad_xy("U2", "13")
        dx3, dy3 = self.pad_xy("U2", "3")
        if not (ex < cx - 1.2 and dy3 > cy + 1.2):
            return 0
        w = SIGNAL_W
        try:
            x16, y16 = self.pad_xy("U2", "16")
            x5, y5 = self.pad_xy("U2", "5")
            xr11, yr11 = self.pad_xy("R11", "1")
            xr10f, yr10f = self.pad_xy("R10", "2")
            xr10v, yr10v = self.pad_xy("R10", "1")
            sx, sy = self.pad_xy("S2", "2")
            gx, gy = self.pad_xy("RS1", "2")
            xq, yq = self.pad_xy("R12", "1")
            xv, yv = self.pad_xy("R16", "1")
            xp, yp = self.pad_xy("R3", "1")
            xb, yb = self.pad_xy("J1", "A9")
            xa4, ya4 = self.pad_xy("J1", "A4")
            po = {n: self.pad_xy("U6", n) for n in ("1", "2", "3", "5", "6")}
            q4, q6, q3g = self.pad_xy("Q3", "4"), self.pad_xy("Q3", "6"), self.pad_xy("Q3", "3")
            r36, r36g = self.pad_xy("R36", "1"), self.pad_xy("R36", "2")
            r35v, r35c = self.pad_xy("R35", "1"), self.pad_xy("R35", "2")
            q1 = self.pad_xy("Q3", "1")
            d1g, u451 = self.pad_xy("D1", "2"), self.pad_xy("U4", "51")
            u11, u418 = self.pad_xy("U1", "1"), self.pad_xy("U4", "18")
            c17r = self.pad_xy("C17", "2")
            c24v, c24n = self.pad_xy("C24", "1"), self.pad_xy("C24", "2")
            lv, lg, le = self.pad_xy("U5", "1"), self.pad_xy("U5", "2"), self.pad_xy("U5", "3")
            u414, u32 = self.pad_xy("U4", "14"), self.pad_xy("U3", "2")
            c5g = self.pad_xy("C5", "2")
        except KeyError:
            return 0
        # cell protection: U6 sits right above Q3, both turned the same way, so that the gate
        # pins face each other; CS and VCC leave U6 through the gap between its pad rows (lanes
        # 0.137 mm off the pads), CS to the west and down beside Q3 to R36, VCC to the east to C24
        # and R35.  The DW01A senses Kelvin: R36's ground end joins Q3's P- pin (source 2) alone,
        # the DW01A ground pin joins Q3's BAT- pin (source 1) alone, and neither trace carries
        # load current (route.KELVIN keeps the ground routing and pours off R36's ground end)
        w2 = 0.2
        ycs = po["2"][1] - 0.66 - 0.137 - w2 / 2      # just above the pin 1-3 row
        yvc = po["5"][1] + 0.66 + 0.137 + w2 / 2      # just below the pin 4-6 row
        xcs = po["3"][0] - 0.45                         # west end of the CS lane
        xcd = q4[0] - 0.65                              # CS down close to U6's and Q3's west pins
        xv1, yv1 = c24n[0] + 0.45, c24n[1] - 0.69      # BATN via beside C24, east of the module pad
        xv2, yv2 = q1[0], (q6[1] + q1[1]) / 2           # BATN sense via between Q3's pins 6 and 1
        # No via may sit under the USB-C shell (route._keepouts) except right beside one of its
        # pads: five vias stand 0.4 mm off the ends of the shell legs (x 110.28 / 118.92); EN's via
        # sits in front of the receptacle's pin row, outside the shell.  Absolute KiCad mm.
        xl, xr = 110.28, 118.92
        plans = [   # (net, [(from, to, width)], [vias])
            # EN: up the gap between C5 and the left peg, out of the shell area
            ("LED_EN", [((ex, ey), (112.45, ey), w), ((112.45, ey), (112.45, 99.45), w)], [(112.45, 99.45)]),
            # VOS: below the left peg into the LED+ wire pad J3.1 (between the two front legs)
            ("VOUT", [((x16, y16), (112.75, y16), w), ((112.75, y16), (112.75, 102.68), w),
                      ((112.75, 102.68), (110.5, 102.68), w), ((110.5, 102.68), (110.5, 103.1), w)], []),
            # DEF (VBAT): past the end of L1's switch pad, between R10's pads to the via above the
            # rear-lower leg
            ("VBAT", [((dx3, dy3), (dx3 + 0.1, dy3), w), ((dx3 + 0.1, dy3), (dx3 + 0.1, 103.95), w),
                      ((dx3 + 0.1, 103.95), (115.5, 104.5), w), ((115.5, 104.5), (xr - 0.22, 104.5), w),
                      ((xr - 0.22, 104.5), (xr, 104.45), w)], [(xr, 104.45)]),
            # FB: below the right peg and up the only gap between the peg and the rear-upper leg to
            # a via above that leg (on to Q2), with the divider R11 / R10 hanging off it
            ("FB", [((x5, y5), (116.6, 102.7), w), ((116.6, 102.7), (118.16, 102.7), w),
                    ((118.16, 102.7), (118.16, 100.4), w), ((118.16, 100.4), (xr, 100.02), w),
                    ((xr11, 102.7), (xr11, yr11), w), ((xr11, yr11), (xr10f, yr10f), w)], [(xr, 100.02)]),
            # QS (R12 in the column beside the module): out of R12's pad corner between the leg and
            # C12 to the via below the rear-upper leg (on to Q2 on In2)
            ("QS", [((xq - 0.15, yq + 0.17), (119.3, 102.62), w), ((119.3, 102.62), (xr, 102.92), w)], [(xr, 102.92)]),
            # VSET: R16's pad down to a via between R16 and R3, beside the rear-lower leg
            ("VSET", [((xv - 0.1, yv + 0.12), (119.85, 106.1), w)], [(119.85, 106.1)]),
            # R10's top end (VOUT): between C8 and C22 down to the output pour
            ("VOUT", [((xr10v, yr10v), (116.575, yr10v + 0.425), w), ((116.575, yr10v + 0.425), (116.575, 107.2), w)], []),
            # LED+ (VOUT) to the wire pad J3.1 on two parallel paths: on the top face from L1's output
            # pad round the end of the front-lower shell leg and up the board edge (0.55 mm, the
            # only gap: the receptacle on the other face allows no via under its shell), and on In2:
            # a 1.2 mm track from the via below the front-lower leg, up beside that leg and between
            # the two front legs to J3.1's four vias; it runs on under L1 and the output capacitors
            # (the In2 pour of LOCAL_ZONES widens it)
            ("VOUT", [((111.4, 107.2), (110.0, 107.2), 0.55), ((110.0, 107.2), (109.36, 106.7), 0.55),
                      ((109.36, 106.7), (109.36, 104.3), 0.55)], []),
            ("VOUT", [((xl, 106.85), (111.3, 107.25), 0.5)], [(xl, 106.85)]),
            ("VOUT", [((2, 109.9, 103.675), (2, 111.55, 103.675), 1.2), ((2, 111.55, 103.675), (2, 111.55, 107.2), 1.2),
                      ((2, 111.55, 107.2), (2, 117.9, 107.2), 1.2), ((2, xl, 106.85), (2, 111.2, 107.2), 0.45)], []),
            # PROG (charger current set, R3 in the column) to the via below the rear-lower leg
            ("PROG", [((xp - 0.1, yp), (xr, 106.85), w)], [(xr, 106.85)]),
            # VBUS: the front pin pair A9/B4 of the receptacle up to a via behind the pin row (the
            # router joins it to the rear pair and the charger)
            ("VBUS", [((3, xb, 99.95), (3, 111.9, 99.45), 0.2), ((3, 111.9, 99.45), (3, 111.9, 99.3), 0.2)], [(111.9, 99.3)]),
            # ... and the rear pair A4/B9 likewise (R1 sits 0.15 mm further back for it), the two
            # vias joined on In2 behind the pin row; the router takes VBUS on from the rear pair
            ("VBUS", [((3, xa4, 99.95), (3, xa4, 99.45), 0.2), ((2, 111.9, 99.3), (2, 111.9, 100.05), 0.2),
                      ((2, 111.9, 100.05), (2, xa4 - 0.35, 100.05), 0.2), ((2, xa4 - 0.35, 100.05), (2, xa4, 99.45), 0.2)],
             [(xa4, 99.45)]),
            # VBAT (3.5 A, cell pad J2.1 -> C5 / PVIN): 0.9 mm on the top face from C5 through the free
            # area of the front hold-down pad to two vias between the slide-switch row and the J6
            # contacts, then a strip on In1 - 1.5 mm under the module's top-left corner (north of the
            # resistor column, whose nets need In1 further down), 2.0 mm on diagonally under the
            # module - to four vias in the cell pad J2.1.  Every signal layer is busy across the
            # column; on In1 the strip only takes a slot out of the ground plane, which stays whole
            # round both of its ends (the LED return from RS1 to Q3 runs south of it).
            ("VBAT", [((115.1, 99.0), (115.7, 98.65), 0.9), ((115.7, 98.65), (117.4, 98.65), 0.9),
                      ((117.4, 98.65), (117.4, 96.5), 0.9), ((117.4, 96.5), (117.6, 96.1), 0.9),
                      ((117.6, 96.1), (118.3, 96.15), 0.6), ((118.3, 96.15), (118.95, 96.2), 0.4)],
             [(117.6, 96.1), (118.3, 96.15), (118.95, 96.2)]),
            ("VBAT", [((1, 117.6, 96.1), (1, 124.2, 96.1), 1.5), ((1, 124.2, 96.1), (1, 130.5, 102.7), 2.0),
                      ((1, 130.5, 102.7), (1, 131.1, 102.7), 2.0)], []),
            # cell protection on the bottom face: OD and OC straight down from U6 into Q3's gates
            ("PROT_OD", [((3, *po["1"]), (3, q6[0], q6[1]), 0.3)], []),
            ("PROT_OC", [((3, *po["3"]), (3, q4[0], q4[1]), 0.3)], []),
            # Q3's source 2 (GND = P-, the whole battery current) to two vias under Q3's body,
            # between its pad rows (the module's pads sit above it on the top face), clear of R36
            ("GND", [((3, q3g[0], q3g[1] - 0.25), (3, q3g[0], yv2), 0.5),
                     ((3, q3g[0], yv2), (3, q3g[0] - 0.5, yv2 - 0.08), 0.4)],
             [(q3g[0], yv2), (q3g[0] - 0.5, yv2 - 0.08)]),
            # CS: up into the gap between U6's pad rows, west under pin 3, then down between C2/D1
            # and U6/Q3, past Q3's ground vias, into R36 beside Q3's P- pin
            ("PROT_CS", [((3, *po["2"]), (3, po["2"][0], ycs), w2), ((3, po["2"][0], ycs), (3, xcs, ycs), w2),
                         ((3, xcs, ycs), (3, xcd, ycs + (xcs - xcd)), w2),
                         ((3, xcd, ycs + (xcs - xcd)), (3, xcd, q4[1] + 0.54), w2),
                         ((3, xcd, q4[1] + 0.54), (3, r36[0] + 0.01, q4[1] + 0.94), w2),
                         ((3, r36[0] + 0.01, q4[1] + 0.94), (3, r36[0] + 0.01, r36[1] - 0.32), w2),
                         ((3, r36[0] + 0.01, r36[1] - 0.32), (3, *r36), w2)], []),
            # R36's ground end straight into Q3's P- pin (the Kelvin point of the current sense)
            ("GND", [((3, *r36g), (3, q3g[0] - 0.25, r36g[1]), 0.25)], []),
            # VCC: down into the same gap, east under pin 6 to C24 and R35 (100 ohm from BAT+)
            ("PROT_VCC", [((3, *po["5"]), (3, po["5"][0], yvc), w2), ((3, po["5"][0], yvc), (3, c24v[0], yvc), w2),
                          ((3, *c24v), (3, *r35c), w2)], []),
            ("VBAT", [((3, *r35v), (3, r35v[0], r35v[1] + 0.95), 0.25)], []),
            # DW01A ground (BATN): pin 6 to C24, a via beside it and a thin In2 track down the gap
            # between the module pad and the cell pad's vias to a via between Q3's pins 6 and 1,
            # then a stub into Q3's BAT- pin (source 1) itself: no current flows in it, so the
            # DW01A reads the voltage across the two MOSFETs alone
            ("BATN", [((3, *po["6"]), (3, *c24n), 0.25), ((3, *c24n), (3, xv1, yv1), 0.25),
                      ((2, xv1, yv1), (2, xv1 - 0.5, yv1 + 0.5), w2), ((2, xv1 - 0.5, yv1 + 0.5), (2, xv1 - 0.5, 104.95), w2),
                      ((2, xv1 - 0.5, 104.95), (2, xv2, yv2), w2), ((3, xv2, yv2), (3, q1[0], q1[1] - 0.49), w2)],
             [(xv1, yv1), (xv2, yv2)]),
            # the battery current from the BAT- pad into Q3's source 1: one short 1 mm track (no
            # pour, so the sense stub above touches the BAT- copper at the pin only)
            ("BATN", [((3, q1[0] + 0.1, q1[1] + 0.25), (3, 130.6, q1[1] + 0.25), 1.0)], []),
            # LDO U5 (above the key board, turned so that VIN and EN face east): VIN and EN joined
            # beside the package, EN to a via on the In1 VBAT strip; GND to a via under the package
            ("VBAT", [((3, *lv), (3, 125.65, lv[1]), w2), ((3, 125.65, lv[1]), (3, 125.65, le[1]), w2),
                      ((3, 125.65, le[1]), (3, *le), w2), ((3, *le), (3, 124.6, 96.35), 0.25)], [(124.6, 96.35)]),
            ("GND", [((3, *lg), (3, 123.6, 94.5), 0.25)], [(123.6, 94.5)]),
            # PVIN 11/12 and AVIN 10 joined across their pad ends and to C5
            ("VBAT", [((113.85, 100.0), (114.85, 100.0), 0.25), ((114.35, 99.95), (114.75, 99.3), 0.5)], []),
            # S2_COM: S2's middle pin through the gap between the switch pads and RS1 to a via in the
            # hold-down area (copper allowed there)
            ("S2_COM", [((sx, sy), (sx, sy + 0.97), w), ((sx, sy + 0.97), (116.4, sy + 0.97), w),
                        ((116.4, sy + 0.97), (116.4, 96.95), w)], [(116.4, 96.95)]),
            # RS1's ground pad (LED return) to a GND via beside it, clear of the J6 contacts below
            ("GND", [((gx, gy), (116.5, 97.65), 0.6)], [(116.5, 97.65)]),
            # the input capacitor's ground to a via right beside it: EN leaves the corner between
            # PVIN and PGND on the top face, so C5's ground reaches PGND through the In1 plane
            # under U2 (into U2's exposed-pad vias) - the shortest input loop this corner allows
            ("GND", [(c5g, (112.45, 98.6), 0.4)], [(112.45, 98.6)]),
            # the ESD diode's GND pad, the module's corner GND pin 51 and the charger's status pin:
            # their only free via spots (C2, C14, U1 and the module's pins box them in)
            ("GND", [((3, *d1g), (3, d1g[0] - 0.78, d1g[1] - 0.55), 0.25)], [(d1g[0] - 0.78, d1g[1] - 0.55)]),
            ("GND", [(u451, (u451[0] - 0.72, u451[1] + 0.03), 0.25)], [(u451[0] - 0.72, u451[1] + 0.03)]),
            ("CHG_STAT", [((3, u11[0] - 0.14, u11[1] - 0.15), (3, u11[0] - 0.14, 101.3), w),
                          ((u11[0] - 0.14, 101.3), u418, w)], [(u11[0] - 0.14, 101.3)]),
            # RST_G (charger corner -> Q5 at the far end): along the board edge under the USB pair
            # and up the gap between D1 and R36 to a via below the module's pad
            ("RST_G", [((3, c17r[0], c17r[1] + 0.15), (3, c17r[0], 107.7), w), ((3, c17r[0], 107.7), (3, 125.47, 107.7), w),
                       ((3, 125.47, 107.7), (3, 125.47, 104.9), w), ((3, 125.47, 104.9), (3, 125.75, 104.6), w)],
             [(125.75, 104.6)]),
            # the module's GND pin 14 and the op-amp's GND pin to their vias (the v0.7 spots: the
            # 0402 column beside the module leaves the router no other way to them)
            ("GND", [(u414, (u414[0] - 0.7, u414[1] - 0.1), 0.25)], [(u414[0] - 0.7, u414[1] - 0.1)]),
            ("GND", [(u32, (u32[0] + 0.65, u32[1]), 0.25), ((u32[0] + 0.65, u32[1]), (u32[0] + 0.65, u32[1] + 1.4), 0.25)],
             [(u32[0] + 0.65, u32[1] + 1.4)]),
        ]
        done = 0
        for net, segs, vias in plans:
            items = [("seg", ((a[0], *a[1:], *b[1:], ww) if len(a) == 3 else (0, *a, *b, ww)))
                     for (a, b, ww) in segs] + [("via", v) for v in vias]
            err = self._items_ok(self.nets[net], items)
            if err:
                log(f"buck escape {net} skipped: {err}")
                continue
            self.preroute(net, items)
            done += 1
        # the Kelvin copper (R36's ground pad and its stub, without Q3's pad) for fields()
        gnd = self.nets["GND"]
        km = np.zeros((4, self.ny, self.nx), dtype=np.int32)
        self.raster_items([("seg", (3, *r36g, q3g[0] - 0.25, r36g[1], 0.25))], 1, km)
        kel = km[3] > 0
        for p in self.pads.get(gnd, []):
            if not p["cells"]:
                continue
            cells = np.array(p["cells"])
            on_b = cells[cells[:, 0] == 3]
            if (p["ref"], p["num"]) in KELVIN_PADS:
                kel[on_b[:, 1], on_b[:, 2]] = True
            elif (p["ref"], p["num"]) == ("Q3", "3") and len(on_b):
                kel[on_b[:, 1], on_b[:, 2]] = False
        self.kelvin_dist = ndimage.distance_transform_edt(~kel) * G if kel.any() else None
        # the four VBAT vias inside the cell pad J2.1 (a wire pad: the router's no-via-in-pad rule
        # does not apply), clear of the module's pads on the top face
        try:
            jx, jy = self.pad_xy("J2", "1")
        except KeyError:
            return done
        jv = [(jx - 0.8, jy - 0.75), (jx - 0.2, jy - 0.75), (jx - 0.8, jy - 0.15), (jx - 0.2, jy - 0.15)]
        self.preroute("VBAT", [("via", v) for v in jv])
        return done + 1

    def _items_ok(self, code, items, tol=0.0):
        """Exact clearance of hand-made copper to every foreign pad and drill, and via rules."""
        for kind, d in items:
            if kind == "seg":
                k, x1, y1, x2, y2, w = d
                n = max(2, int(math.hypot(x2 - x1, y2 - y1) / (G / 2)) + 1)
                for t in np.linspace(0.0, 1.0, n):
                    x, y = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
                    i, j = self.ij(x, y)
                    if self.pad_dist(k, code)[j, i] < w / 2 + CLR - G * 0.71 - tol:
                        return f"segment near a foreign pad at ({x - 100:.2f}, {100 - y:.2f}) on layer {k}"
                    if self.d_edge[j, i] < w / 2 + EDGE or self.D_npth[j, i] < w / 2 + NPTH_CLR:
                        return f"segment near the edge / a hole at ({x - 100:.2f}, {100 - y:.2f})"
                    if self.pth_gap(x, y, code) < w / 2 + PTH_HOLE_CLR + 0.005 - tol:
                        return f"segment near a plated hole of another net at ({x - 100:.2f}, {100 - y:.2f})"
            else:
                x, y = d
                i, j = self.ij(x, y)
                for k in range(4):
                    if self.pad_dist(k, code)[j, i] < VIA_D / 2 + CLR - G * 0.71:
                        return f"via near a foreign pad at ({x - 100:.2f}, {100 - y:.2f}) layer {k}"
                if not self.smd_far[j, i] or not self._via_hole_ok(x, y) or self.keep[:, j, i].any():
                    return f"via spot not allowed at ({x - 100:.2f}, {100 - y:.2f})"
        return None

    def preroute_leds(self, log=print):
        """v0.6: fan-out of the two 1 x 1 mm ring LEDs (bottom side, 0.6 mm pad pitch, no track
        fits between the pads).  Each cathode pad leaves on its own outward side straight to its
        series resistor (hand-placed next to the LED, gen_pcb.BIG_PARTS), each common anode drops
        to a 3V3 via - a crossing-free pattern the negotiation does not find on its own."""
        H = lambda X, Y: (100.0 + X, 100.0 - Y)
        if not self.has_part("J1"):
            return 0                  # v0.7: the ring LEDs sit on the key board (routed freely)

        def P(ref, num):
            x, y = self.pad_xy(ref, num)
            return x - 100.0, 100.0 - y
        w, w3 = SIGNAL_W, NECK_W
        plans = []
        try:
            p1, p2, p3, p4 = (P("LED3", n) for n in "1234")
            r23, r24, r25 = P("R23", "1"), P("R24", "1"), P("R25", "1")
            q1, q2, q3, q4 = (P("LED4", n) for n in "1234")
            r32, r33, r34 = P("R32", "1"), P("R33", "1"), P("R34", "1")
        except KeyError:
            return 0
        v3 = (p1[0] - 0.2, p1[1] - 0.75)
        plans.append(("3V3", [(p1, (p1[0], p1[1] - 0.45), w3), ((p1[0], p1[1] - 0.45), v3, w3)], [v3]))
        plans.append(("R_K", [(p2, (p2[0], 1.7), w), ((p2[0], 1.7), (r23[0] + 0.5, r23[1] + 0.05), w),
                              ((r23[0] + 0.5, r23[1] + 0.05), r23, w)], []))
        plans.append(("G_K", [(p3, (p3[0] + 0.4, p3[1] + 0.4), w), ((p3[0] + 0.4, p3[1] + 0.4), (p3[0] + 0.4, r24[1] - 0.4), w),
                              ((p3[0] + 0.4, r24[1] - 0.4), (p3[0], r24[1]), w), ((p3[0], r24[1]), r24, w)], []))
        if r25[0] > 18.5 and abs(r25[1] - 5.7) < 0.2:      # R25 in the corner behind J5 (v0.6 first layout)
            plans.append(("B_K", [(p4, (p4[0], r25[1] - 0.75), w), ((p4[0], r25[1] - 0.75), (r25[0], r25[1] - 0.53), w),
                                  ((r25[0], r25[1] - 0.53), r25, w)], []))
        v4 = (q1[0], q1[1] - 0.65)
        plans.append(("3V3", [(q1, v4, w3)], [v4]))
        plans.append(("R_K2", [(q2, (r32[0] - 0.15, q2[1]), w)], []))
        plans.append(("G_K2", [(q3, (r33[0] - 0.15, q3[1]), w)], []))
        plans.append(("B_K2", [(q4, (q4[0], r34[1] - 0.4), w), ((q4[0], r34[1] - 0.4), (q4[0] + 0.4, r34[1]), w),
                               ((q4[0] + 0.4, r34[1]), (r34[0] - 0.15, r34[1]), w)], []))
        done = 0
        for net, segs, vias in plans:
            if net not in self.nets:
                continue
            items = [("seg", (3, *H(*a), *H(*b), ww)) for (a, b, ww) in segs] + [("via", H(*v)) for v in vias]
            err = self._items_ok(self.nets[net], items)
            if err:
                log(f"LED fan-out {net} skipped: {err}")
                continue
            self.preroute(net, items)
            done += 1
        return done

    def preroute_ep(self, n_max=4):
        """Thermal vias in the exposed GND pad of the module: on the centre
        lines of the solder-mask webs between the paste apertures, clear of
        copper on every layer (parts on the bottom side under the module),
        spread out (farthest-point choice)."""
        code = self.nets["GND"]
        # 1000 lm power stage: pads and the hand-made copper of the other nets (VBAT trunk, BATN)
        foreign = ((self.owner != 0) & (self.owner != code)) | ((self.trk > 0) & (self.trk != code))
        foreign[3] |= self.owner[3] != 0      # no via in a bottom-face pad, GND ones included (solder wicking)
        Df = {k: ndimage.distance_transform_edt(~foreign[k]) * G for k in range(4)}
        items = []
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            if ref not in EP_VIAS:
                continue
            num, webs = EP_VIAS[ref]
            pads = [p for p in fp.Pads() if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)]
            pad = max((p for p in pads if p.GetNumber() == num), key=lambda p: p.GetSizeX())
            cx, cy = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
            half = mm(pad.GetSizeX()) / 2 - VIA_D / 2 - 0.05
            cand = []
            for wv in webs:
                for t in np.arange(-half, half + 1e-9, G):
                    for (dx, dy) in ((wv, t), (t, wv)):
                        x, y = cx + dx, cy + dy
                        i, j = self.ij(x, y)
                        if any(Df[k][j, i] < VIA_D / 2 + CLR + MARGIN + G for k in range(4)):
                            continue
                        if (self.keep[:, j, i] & ~self.gnd_via_ok[j, i]).any() or not self._via_hole_ok(x, y):
                            continue
                        cand.append((float(x), float(y)))
            chosen = []
            if cand:
                chosen.append(min(cand, key=lambda c: math.hypot(c[0] - cx, c[1] - cy)))
            while cand and len(chosen) < n_max:
                best = max(cand, key=lambda c: min(math.hypot(c[0] - q[0], c[1] - q[1]) for q in chosen))
                if min(math.hypot(best[0] - q[0], best[1] - q[1]) for q in chosen) < max(VIA_PITCH, 0.8):
                    break
                chosen.append(best)
            items += [("via", c) for c in chosen]
        if items:
            self.preroute("GND", items)
        return len(items)

    # --------------------------------------------------------------- search
    def astar(self, code, w, sources, targets, window=None, neck_cells=None,
              via_target=False, pfac=4.0, hard_tracks=False, max_expand=900000, F=None):
        hard, hard_n, conf, conf_n, via_hard, via_conf = F if F is not None else self.fields(code, w)
        nx, ny = self.nx, self.ny
        jlo, jhi, ilo, ihi = window if window else (0, ny, 0, nx)
        ridx = {k: n for n, k in enumerate(ROUTE)}
        nl = len(ROUTE)
        nk = None
        if neck_cells:
            nk = np.zeros((ny, nx), dtype=bool)
            for (j, i) in neck_cells:
                nk[j, i] = True
            nk = ndimage.binary_dilation(nk, iterations=int(NECK_R / G))
        A = np.zeros((nl, ny, nx), dtype=bool)
        C = np.zeros((nl, ny, nx), dtype=bool)
        for k in ROUTE:
            r = ridx[k]
            if nk is None:
                A[r] = hard[k]
                C[r] = conf[k]
            else:
                A[r] = hard[k] | (hard_n[k] & nk)
                C[r] = np.where(hard[k], conf[k], conf_n[k])
        if hard_tracks:
            A &= ~C
        win = np.zeros((ny, nx), dtype=bool)
        win[jlo:jhi, ilo:ihi] = True
        A &= win[None]
        vh = via_hard & win
        if hard_tracks:
            vh &= ~via_conf
        src = [(ridx[k], j, i) for (k, j, i) in sources if k in ridx and win[j, i]]
        tgt = [(ridx[k], j, i) for (k, j, i) in targets if k in ridx]
        if not src or (not tgt and not via_target):
            return None
        T = np.zeros_like(A)
        for (r, j, i) in tgt:
            T[r, j, i] = True
        S = np.zeros_like(A)
        for (r, j, i) in src:
            S[r, j, i] = True
        A2 = A | T | S
        # reachability pre-check (layers joined where a via is allowed)
        st8 = np.ones((3, 3), dtype=bool)
        labs, off = [], 0
        for r in range(nl):
            lab, n = ndimage.label(A2[r], structure=st8)
            lab[lab > 0] += off
            labs.append(lab)
            off += n
        parent = list(range(off + 1))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a in range(nl):
            for b in range(a + 1, nl):
                m = vh & (labs[a] > 0) & (labs[b] > 0)
                if m.any():
                    for x, y in np.unique(np.stack([labs[a][m], labs[b][m]], 1), axis=0).tolist():
                        rx, ry = find(x), find(y)
                        if rx != ry:
                            parent[rx] = ry
        sroots = {find(int(labs[r][j, i])) for (r, j, i) in src if labs[r][j, i] > 0}
        if via_target:
            vroots = set()
            for r in range(nl):
                m = vh & (labs[r] > 0) & ~S[r]
                vroots |= {find(int(v)) for v in np.unique(labs[r][m]).tolist()}
            troots = {find(int(labs[r][j, i])) for (r, j, i) in tgt if labs[r][j, i] > 0}
            if not (sroots & (vroots | troots)):
                return None
        else:
            troots = {find(int(labs[r][j, i])) for (r, j, i) in tgt if labs[r][j, i] > 0}
            if not (sroots & troots):
                return None
        if tgt:
            tj = [t[1] for t in tgt]
            ti = [t[2] for t in tgt]
            tb = (min(tj), max(tj), min(ti), max(ti))
        else:
            tb = None

        def h(j, i):
            if tb is None:
                return 0.0
            dj = max(tb[0] - j, 0, j - tb[1])
            di = max(tb[2] - i, 0, i - tb[3])
            return max(di, dj) + 0.414 * min(di, dj)
        Hr = np.stack([self.H[k] for k in ROUTE])
        Hv = self.H[1]
        lib = _clib()
        if lib is not None:
            return self._astar_c(lib, nl, A2, C, Hr, Hv, vh, via_conf, T, S, (jlo, jhi, ilo, ihi), tb,
                                 src, pfac, via_target, max_expand)
        gb = np.full(A.shape, np.inf, dtype=np.float32)
        prev = np.full(A.shape, -1, dtype=np.int64)
        heap = []
        for (r, j, i) in src:
            gb[r, j, i] = 0.0
            heapq.heappush(heap, (h(j, i), 0.0, r, j, i))
        steps = ((0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
                 (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))
        lcost = [LAYER_COST.get(k, 1.0) for k in ROUTE]
        n = 0
        goal = None
        while heap:
            f, g, r, j, i = heapq.heappop(heap)
            if g > gb[r, j, i] + 1e-6:
                continue
            if T[r, j, i] or (via_target and vh[j, i] and not S[r, j, i]):
                goal = (r, j, i)
                break
            n += 1
            if n > max_expand:
                return None
            lc = lcost[r]
            Ar, Cr, Hrr = A2[r], C[r], Hr[r]
            for dj, di, c in steps:
                j2, i2 = j + dj, i + di
                if j2 < jlo or j2 >= jhi or i2 < ilo or i2 >= ihi:
                    continue
                if not Ar[j2, i2]:
                    continue
                if di and dj and not (Ar[j, i2] or Ar[j2, i]):
                    continue
                g2 = g + c * lc * (1.0 + Hrr[j2, i2]) + (pfac if Cr[j2, i2] else 0.0)
                if g2 < gb[r, j2, i2]:
                    gb[r, j2, i2] = g2
                    prev[r, j2, i2] = (r * ny + j) * nx + i
                    heapq.heappush(heap, (g2 + h(j2, i2), g2, r, j2, i2))
            if vh[j, i] and self._via_spaced(prev, r, j, i, ny, nx):
                vc = VIA_COST * (1.0 + Hv[j, i]) + (3 * pfac if via_conf[j, i] else 0.0)
                for r2 in range(nl):
                    if r2 == r or not A2[r2, j, i]:
                        continue
                    g2 = g + vc
                    if g2 < gb[r2, j, i]:
                        gb[r2, j, i] = g2
                        prev[r2, j, i] = (r * ny + j) * nx + i
                        heapq.heappush(heap, (g2 + h(j, i), g2, r2, j, i))
        if goal is None:
            return None
        path = [goal]
        while True:
            r, j, i = path[-1]
            p = prev[r, j, i]
            if p < 0:
                break
            r0, rem = divmod(int(p), ny * nx)
            j0, i0 = divmod(rem, nx)
            path.append((r0, j0, i0))
        return [(ROUTE[r], j, i) for (r, j, i) in path[::-1]]

    def _astar_c(self, lib, nl, A2, C, Hr, Hv, vh, via_conf, T, S, win, tb, src, pfac, via_target,
                 max_expand):
        ny, nx = self.ny, self.nx
        u8 = lambda a: np.ascontiguousarray(a, dtype=np.bool_).view(np.uint8)
        A2u, Cu, Tu, Su = u8(A2), u8(C), u8(T), u8(S)
        vhu, vcu = u8(vh), u8(via_conf)
        Hr = np.ascontiguousarray(Hr, dtype=np.float32)
        Hv = np.ascontiguousarray(Hv, dtype=np.float32)
        lcost = np.array([LAYER_COST.get(k, 1.0) for k in ROUTE], dtype=np.float64)
        srca = np.ascontiguousarray(np.array(src, dtype=np.int32).reshape(-1, 3))
        gb = np.full((nl, ny, nx), np.inf, dtype=np.float32)
        prev = np.full((nl, ny, nx), -1, dtype=np.int64)
        tbv = tb if tb is not None else (0, 0, 0, 0)
        P = lambda a: a.ctypes.data
        goal = lib.astar(nl, ny, nx, P(A2u), P(Cu), P(Hr), P(Hv), P(vhu), P(vcu), P(Tu), P(Su),
                         *[int(v) for v in win], int(tb is not None), *[int(v) for v in tbv],
                         P(lcost), float(pfac), float(VIA_COST), int(bool(via_target)), int(max_expand),
                         float((VIA_PITCH / G) ** 2), 24, P(srca), len(src), P(gb), P(prev))
        if goal < 0:
            return None
        L = ny * nx
        path = []
        p = int(goal)
        pf = prev.ravel()
        while p >= 0:
            r, rem = divmod(p, L)
            j, i = divmod(rem, nx)
            path.append((ROUTE[r], j, i))
            p = int(pf[p])
        return path[::-1]

    @staticmethod
    def _via_spaced(prev, r, j, i, ny, nx, back=24):
        """No earlier via of the same path closer than VIA_PITCH (walks back
        along the predecessor chain; a layer change marks a via)."""
        lim = (VIA_PITCH / G) ** 2
        cr, cj, ci = r, j, i
        p = prev[r, j, i]
        n = 0
        while p >= 0 and n < back:
            r0, rem = divmod(int(p), ny * nx)
            j0, i0 = divmod(rem, nx)
            if r0 != cr and (j0 - j) ** 2 + (i0 - i) ** 2 < lim:
                return False
            cr, cj, ci = r0, j0, i0
            p = prev[r0, j0, i0]
            n += 1
        return True

    # ------------------------------------------------------------- commit
    def geometry(self, code, path, w, end_via=False, hard=None):
        """path -> list of items (seg/via) with widths chosen per piece."""
        items = []
        runs = []
        run = [path[0]]
        for s in path[1:]:
            if s[0] != run[-1][0]:
                runs.append(run)
                k, j, i = s
                items.append(("via", self.xy(i, j)))
                run = [s]
            else:
                run.append(s)
        runs.append(run)
        if w <= NECK_W:
            hard = None
        elif hard is None:
            hard = self.fields(code, w)[0]
        for run in runs:
            if len(run) < 2:
                continue
            k = run[0][0]
            pts = [run[0]]
            for a, b, c in zip(run, run[1:], run[2:]):
                if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                    pts.append(b)
            pts.append(run[-1])
            for a, b in zip(pts, pts[1:]):
                ww = w
                if hard is not None:
                    n = max(abs(b[1] - a[1]), abs(b[2] - a[2])) + 1
                    jj = np.linspace(a[1], b[1], n).round().astype(int)
                    ii = np.linspace(a[2], b[2], n).round().astype(int)
                    if not hard[k][jj, ii].all():
                        ww = NECK_W
                x1, y1 = self.xy(a[2], a[1])
                x2, y2 = self.xy(b[2], b[1])
                items.append(("seg", (k, x1, y1, x2, y2, ww)))
        if end_via:
            k, j, i = path[-1]
            items.append(("via", self.xy(i, j)))
        return items

    def raster_items(self, items, code, arr, grow=0.0):
        cells = []
        for kind, d in items:
            if kind == "seg":
                k, x1, y1, x2, y2, ww = d
                cells += self._mark_segment(k, x1, y1, x2, y2, ww + 2 * grow, code, arr)
            else:
                x, y = d
                cells += self._mark_circle(range(4), x, y, VIA_D / 2 + grow, code, arr)
        return cells

    def commit(self, code, items, no_rip=False):
        """Rip the connections of other nets that come too close, add ours
        (no_rip: refuse instead, returns (None, None))."""
        probe = self.raster_items(items, None, self.trk, grow=CLR + MARGIN)
        if no_rip:
            for (k, j, i) in probe:
                v = self.trk[k, j, i]
                if v > 0 and v != code:
                    return None, None
        victims = set()
        for (k, j, i) in probe:
            v = self.trk[k, j, i]
            if v > 0 and v != code and v not in self.frozen and int(self.cid[k, j, i]) not in self.locked:
                victims.add(int(self.cid[k, j, i]))
                self.H[k, j, i] += HIST_INC
        vnets = set()
        for c in victims:
            if c in self.conns:
                vnets.add(self.conns[c][0])
                self.rip_conn(c)
        cid = self.next_cid
        self.next_cid += 1
        self.conns[cid] = (code, items)
        cells = self.raster_items(items, code, self.trk)
        for (k, j, i) in cells:
            self.cid[k, j, i] = cid
        return cells, vnets

    def victims(self, code, items):
        """Connections of other nets that commit(code, items) would rip."""
        probe = self.raster_items(items, None, self.trk, grow=CLR + MARGIN)
        vic = set()
        for (k, j, i) in probe:
            v = self.trk[k, j, i]
            if v > 0 and v != code and v not in self.frozen and int(self.cid[k, j, i]) not in self.locked:
                vic.add(int(self.cid[k, j, i]))
        return vic

    @staticmethod
    def _items_bbox(items, pad=0.0):
        xs, ys = [], []
        for kind, d in items:
            if kind == "seg":
                k, x1, y1, x2, y2, w = d
                r = w / 2 + pad
                xs += [x1 - r, x2 - r, x1 + r, x2 + r]
                ys += [y1 - r, y2 - r, y1 + r, y2 + r]
            else:
                r = VIA_D / 2 + pad
                xs += [d[0] - r, d[0] + r]
                ys += [d[1] - r, d[1] + r]
        return min(xs), min(ys), max(xs), max(ys)

    def rip_conn(self, c):
        code, items = self.conns.pop(c)
        m = self.cid == c
        self.trk[m] = 0
        self.cid[m] = 0
        # v0.6: cells shared with other copper of the same net (track ends, vias) belong to one
        # connection only; draw the neighbours again, or they would keep items without raster
        # (invisible to the router, written to the board)
        if not items:
            return
        bx = self._items_bbox(items, 0.05)
        for c2, (n2, it2) in self.conns.items():
            if n2 != code:
                continue
            b2 = self._items_bbox(it2, 0.05)
            if b2[0] > bx[2] or b2[2] < bx[0] or b2[1] > bx[3] or b2[3] < bx[1]:
                continue
            for (k, j, i) in self.raster_items(it2, code, self.trk):
                self.cid[k, j, i] = c2

    def rip(self, code):
        for c in [c for c, (n, _) in self.conns.items() if n == code]:
            self.rip_conn(c)

    @property
    def items(self):
        out = {}
        for c, (n, it) in self.conns.items():
            out.setdefault(n, []).extend(it)
        return out

    def _labels(self, code):
        """Labels of this net's copper (pads + routed) in the bounding box of that copper
        (v0.6: cropped, 4-connected; two shapes that only touch diagonally on the raster can be
        up to 0.07 mm apart - KiCad: unconnected).  Returns (labs, find, j0, i0)."""
        any2 = (self.owner == code).any(axis=0) | (self.trk == code).any(axis=0)
        jj = np.nonzero(any2.any(axis=1))[0]
        ii = np.nonzero(any2.any(axis=0))[0]
        if not len(jj):
            return None
        j0, j1, i0, i1 = int(jj[0]), int(jj[-1]) + 1, int(ii[0]), int(ii[-1]) + 1
        cop = (self.owner[:, j0:j1, i0:i1] == code) | (self.trk[:, j0:j1, i0:i1] == code)
        labs, off = [], 0
        for k in range(4):
            lab, n = ndimage.label(cop[k])
            lab[lab > 0] += off
            labs.append(lab)
            off += n
        parent = list(range(off + 1))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        # vias and plated holes join the layers where all four layers carry this net
        allk = cop.all(axis=0)
        if allk.any():
            for a in range(4):
                for b in range(a + 1, 4):
                    m = allk & (labs[a] > 0) & (labs[b] > 0)
                    for x, y in np.unique(np.stack([labs[a][m], labs[b][m]], 1), axis=0).tolist():
                        rx, ry = find(x), find(y)
                        if rx != ry:
                            parent[rx] = ry
        return labs, find, j0, i0

    def n_groups(self, code):
        """Number of separate pad groups of a net (components() without the cell sets)."""
        res = self._labels(code)
        if res is None:
            return 0
        labs, find, j0, i0 = res
        roots = set()
        for p in self.pads.get(code, []):
            k, j, i = p["cells"][0]
            roots.add(find(int(labs[k][j - j0, i - i0])))
        return len(roots)

    def components(self, code):
        """Connected groups of this net's pads through its routed copper, and all cells of
        each group (search targets)."""
        res = self._labels(code)
        if res is None:
            return [], []
        labs, find, j0, i0 = res
        groups = {}
        for p in self.pads.get(code, []):
            k, j, i = p["cells"][0]
            groups.setdefault(find(int(labs[k][j - j0, i - i0])), []).append(p)
        cellsets = {}
        for root, ps in groups.items():
            cs = set()
            for k in range(4):
                lab = labs[k]
                ids = [l for l in np.unique(lab[lab > 0]).tolist() if find(l) == root]
                if ids:
                    jj, ii = np.nonzero(np.isin(lab, ids))
                    cs.update(zip([k] * len(jj), (jj + j0).tolist(), (ii + i0).tolist()))
            cellsets[root] = cs
        return list(groups.values()), list(cellsets.values())

    # ------------------------------------------------------------- nets
    def width_of(self, name):
        return WIDTH.get(name, SIGNAL_W)

    def window_for(self, cells_a, cells_b, pad=3.0):
        js = [c[1] for c in cells_a] + [c[1] for c in cells_b]
        is_ = [c[2] for c in cells_a] + [c[2] for c in cells_b]
        m = int(pad / G)
        return (max(min(js) - m, 0), min(max(js) + m, self.ny), max(min(is_) - m, 0), min(max(is_) + m, self.nx))

    def route_net(self, name, pfac):
        code = self.nets[name]
        pads = self.pads.get(code, [])
        if len(pads) < 2:
            return True, set()
        w = self.width_of(name)
        vnets = set()
        neck = [(c[1], c[2]) for p in pads if p["fine"] for c in p["cells"]] if w > NECK_W else None
        for _guard in range(len(pads) + 2):
            groups, cellsets = self.components(code)
            if len(groups) <= 1:
                return True, vnets
            # grow the largest group towards the others (power pads first)
            w = self.width_of(name)
            prefs = POWER_REFS.get(name)
            pw = [g for g in range(len(groups)) if prefs and any(
                p["ref"] in prefs or f'{p["ref"]}.{p["num"]}' in prefs for p in groups[g])]
            if prefs and len(pw) >= 2:
                big = max(pw, key=lambda g: len(cellsets[g]))
                others = [g for g in pw if g != big]
            else:
                if prefs:
                    w = LOW_W[name]
                big = pw[0] if pw else max(range(len(groups)), key=lambda g: len(cellsets[g]))
                others = [g for g in range(len(groups)) if g != big]
            tree = cellsets[big]
            tgt = set()
            for g in others:
                tgt |= cellsets[g]
            path, used_w = None, w
            # v0.6: a path found inside a small window is taken only if it crosses no other
            # net's copper; otherwise the larger windows (and, except for the high-current
            # branches, narrower widths down to MIN_AVOID_W) are tried as well and the
            # candidate that rips the fewest connections wins.  The v0.5 search accepted the
            # first path in the 2.5 mm window even when it ripped a net while a clean path
            # existed outside the window - on the denser v0.6 board the nets kept ripping
            # each other and the negotiation never converged.
            high_current = bool(prefs and len(pw) >= 2)
            widths = [w] + [x for x in (0.3, NECK_W, SIGNAL_W) if x < w]
            floor_w = w if high_current else min(w, MIN_AVOID_W.get(name, SIGNAL_W))
            fcache = {}          # distance maps of this copper state (cleared with every commit)
            # v0.6: the nearest other group first (small search windows), all of them if that fails
            ta_all = np.array([(c[1], c[2]) for c in tree])

            def gdist(g):
                pc = np.array([(c[1], c[2]) for p in groups[g] for c in p["cells"][::7]])
                d = ((pc[:, None, 0] - ta_all[None, ::5, 0]) ** 2 + (pc[:, None, 1] - ta_all[None, ::5, 1]) ** 2)
                return float(d.min())
            near = min(others, key=gdist) if len(others) > 1 else others[0]
            tsets = [cellsets[near]] + ([tgt] if len(others) > 1 else [])
            for tg in tsets:
                best = None
                focus = None
                for ww in widths:
                    found = False
                    # v0.6: the windows span the targets and the nearest tree copper, not the whole
                    # tree (a power net's tree covers the board: every window was the full board)
                    if focus is None:
                        tl = list(tg)
                        ta = np.array([(c[1], c[2]) for c in tree])
                        cj = sum(c[1] for c in tl) / len(tl)
                        ci = sum(c[2] for c in tl) / len(tl)
                        q = int(np.argmin((ta[:, 0] - cj) ** 2 + (ta[:, 1] - ci) ** 2))
                        focus = tl + [(0, int(ta[q, 0]), int(ta[q, 1]))]
                    for padw in (2.5, 6.0, None):
                        win = self.window_for(focus, focus, padw) if padw else None
                        F = self.fields(code, ww, win, cache=fcache)   # this window only (v0.6, speed)
                        p = self.astar(code, ww, tree, tg, window=win, neck_cells=neck, pfac=pfac, F=F)
                        if not p:
                            continue
                        found = True
                        if not AVOID_RIPS:
                            best = (None, p, ww, self.geometry(code, p, ww, hard=F[0]))
                            break
                        geo = self.geometry(code, p, ww, hard=F[0])
                        nv = len(self.victims(code, geo))
                        if best is None or nv < best[0]:
                            best = (nv, p, ww, geo)
                        if nv == 0:
                            break
                    if best is not None and (best[0] in (None, 0) or (found and ww <= floor_w)):
                        break
                    if best is not None and high_current:
                        break
                if best is not None:
                    break
            geo = None
            if best is not None:
                path, used_w, geo = best[1], best[2], best[3]
            if not path:
                # blocked by frozen copper: retry once with only the power-stage
                # nets frozen (the copper it crosses gets ripped and re-routed)
                base = {self.nets[n] for n in FREEZE if n in self.nets}
                keep_frozen = None
                if self.allow_relax and self.frozen - base:
                    keep_frozen = self.frozen
                    self.frozen = base
                    used_w = SIGNAL_W if w <= NECK_W else NECK_W
                    path = self.astar(code, used_w, tree, tgt, neck_cells=neck, pfac=pfac)
                self.hard_fail.add(name)
                if not path:
                    if keep_frozen is not None:
                        self.frozen = keep_frozen
                    return False, vnets
                items = self.geometry(code, path, used_w)
                _, v = self.commit(code, items)      # rips what it crosses, frozen or not
                vnets |= v
                self.frozen = keep_frozen - {n for n in v}
                continue
            items = geo if geo is not None else self.geometry(code, path, used_w)
            _, v = self.commit(code, items)
            vnets |= v
        return False, vnets

    def _gnd_labels(self):
        """Connected GND copper across layers; roots of the groups that reach
        the main In1 plane.  Routed copper and pads are labelled per layer
        (4-connected raster); every filled pour outline is its own object that
        joins copper only where they overlap - two outlines that merely touch
        are separate in KiCad, so they must not merge here either.  Vias and
        plated holes join the layers.  The plane is the largest In1 outline
        (before the first pour fill: every via, In1 assumed solid)."""
        code = self.nets["GND"]
        cop = (self.owner == code) | (self.trk == code)
        vias = cop.all(axis=0)              # vias and plated holes
        labs, off = [], 0
        for k in range(4):
            lab, n = ndimage.label(cop[k])
            lab[lab > 0] += off
            labs.append(lab)
            off += n
        npour = int(self.pour.max()) if self.pour is not None else 0
        parent = list(range(off + npour + 1))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        if vias.any():
            for a in range(4):
                for b in range(a + 1, 4):
                    m = vias & (labs[a] > 0) & (labs[b] > 0)
                    for x, y in np.unique(np.stack([labs[a][m], labs[b][m]], 1), axis=0).tolist():
                        union(x, y)
        if self.pour is None or not npour:
            plane = {find(int(l)) for l in np.unique(labs[1][labs[1] > 0]).tolist()}
            return labs, find, plane
        for k in range(4):
            pk = self.pour[k]
            m = (pk > 0) & (labs[k] > 0)
            if m.any():
                for x, y in np.unique(np.stack([labs[k][m], pk[m] + off], 1), axis=0).tolist():
                    union(x, y)
        for a, b in self.pour_merge:
            union(a + off, b + off)
        in1 = [i for i, (k, _a) in self.pour_area.items() if k == 1]
        if in1:
            main = max(in1, key=lambda i: self.pour_area[i][1])
            plane = {find(main + off)}
        else:
            plane = {find(int(l)) for l in np.unique(labs[1][labs[1] > 0]).tolist()}
        labs = [np.where(labs[k] > 0, labs[k], np.where(self.pour[k] > 0, self.pour[k] + off, 0))
                for k in range(4)]
        return labs, find, plane

    def _gnd_pads(self):
        code = self.nets["GND"]
        return [p for p in sorted(self.pads.get(code, []), key=lambda q: (q["x"], q["y"])) if not p["pth"]]

    @staticmethod
    def _gkey(p):
        return (p["ref"], p["num"], p["cells"][0])

    def fanout_gnd(self, pfac=6.0, hard=False, only=None, force=False, lock=False, reach=2.2):
        """Every SMD GND pad not yet tied to the In1 plane gets (1) a via
        anywhere in the GND copper it already touches (pour, stubs), else
        (2) a stub to GND copper that is (a via, a plated hole, a pad with
        vias, a pour with vias) or to a new via.  force: pads get their own
        stub and via even when already connected (power stage)."""
        code = self.nets["GND"]
        w = WIDTH["GND"]
        fails, vnets = [], set()
        labs, find, plane = self._gnd_labels()
        F = None
        for p in self._gnd_pads():
            key = self._gkey(p)
            if only is not None and key not in only:
                continue
            k = p["layers"][0]
            c0 = p["cells"][0]
            root = find(int(labs[c0[0]][c0[1], c0[2]])) if labs[c0[0]][c0[1], c0[2]] > 0 else None
            if not force and root in plane:
                continue
            src = set(c for c in p["cells"] if c[0] == k)
            if not force and root is not None and self.pour is not None:
                if F is None:
                    F = self.fields(code, w)
                via_ok = F[4] & ~F[5] & self.smd_far
                grp = np.zeros((self.ny, self.nx), dtype=bool)
                for kk in range(4):
                    lab = labs[kk]
                    ids = [l for l in np.unique(lab[lab > 0]).tolist() if find(int(l)) == root]
                    if ids:
                        grp |= np.isin(lab, ids)
                cand = grp & via_ok
                if cand.any():
                    jj, ii = np.nonzero(cand)
                    pj, pi = c0[1], c0[2]
                    placed = False
                    for n in np.argsort((jj - pj) ** 2 + (ii - pi) ** 2)[:40].tolist():
                        items = [("via", self.xy(int(ii[n]), int(jj[n])))]
                        cells, v = self.commit(code, items, no_rip=True)
                        if cells is not None:
                            placed = True
                            break
                    if placed:
                        self.gnd_cid[key] = self.next_cid - 1
                        labs, find, plane = self._gnd_labels()
                        F = None
                        continue
            win = self.window_for(list(src), list(src), reach)
            jlo, jhi, ilo, ihi = win
            tg = set()
            if not force:
                sub = labs[k][jlo:jhi, ilo:ihi]
                ids = [l for l in np.unique(sub[sub > 0]).tolist() if find(int(l)) in plane]
                if ids:
                    jj, ii = np.nonzero(np.isin(sub, ids))
                    tg = {(k, jlo + a, ilo + b) for a, b in zip(jj.tolist(), ii.tolist())} - src
            neck = [(c[1], c[2]) for c in src]
            path = self.astar(code, w, src, tg, window=win, neck_cells=neck, via_target=True,
                              hard_tracks=hard, pfac=pfac)
            if path is None:
                fails.append(key)
                continue
            items = self.geometry(code, path, w, end_via=path[-1] not in tg)
            cells, v = self.commit(code, items, no_rip=hard)
            if cells is None:
                fails.append(key)
                continue
            vnets |= v
            self.gnd_cid[key] = self.next_cid - 1
            if lock:
                self.locked.add(self.next_cid - 1)
            labs, find, plane = self._gnd_labels()
            F = None
        return fails, vnets

    def gnd_missing(self):
        """SMD GND pads not connected to the In1 plane."""
        labs, find, plane = self._gnd_labels()
        miss = set()
        for p in self._gnd_pads():
            k, j, i = p["cells"][0]
            if not (labs[k][j, i] > 0 and find(int(labs[k][j, i])) in plane):
                miss.add(self._gkey(p))
        return miss

    gnd_first = os.environ.get("FLASHKA_GND_FIRST", "0") == "1"   # True: GND stubs before the signal nets
    gnd_start = int(os.environ.get("FLASHKA_GND_START", "0"))     # otherwise GND joins the negotiation when signals are done (or at this iteration)
    gnd_iters = 0           # negotiated GND iterations before the monotonic repair
    allow_relax = True      # route_net may unfreeze everything once when blocked (off in repair)
    frozen = set()
    locked = set()

    def unreachable_pads(self, w=SIGNAL_W):
        """Placement check on the bare board (pads and holes only): the pads of every net
        (GND excluded) that cannot reach any other pad of their net with a w-wide track, on any
        layer, with vias allowed.  A pad that is boxed in by its neighbours is found here in
        seconds, long before the router runs into it."""
        self.hard_fail, self.locked, self.frozen, self.gnd_cid = set(), set(), set(), {}
        for p in (q for ps in self.pads.values() for q in ps):
            p["cellset"] = set(p["cells"])
        smd = self.smd_own != 0
        self.smd_far = ndimage.distance_transform_edt(~smd) * G >= VIA_D / 2 + 0.06
        self._set_pour_state(None)
        bad = []
        for nm, code in self.nets.items():
            ps = self.pads.get(code, [])
            if nm == "GND" or len(ps) < 2:
                continue
            for a in range(len(ps)):
                others = set()
                for b in range(len(ps)):
                    if b != a:
                        others |= set(ps[b]["cells"])
                if not self.astar(code, w, set(ps[a]["cells"]), others, window=None, pfac=6.0):
                    bad.append((nm, f"{ps[a]['ref']}.{ps[a]['num']}"))
        return bad

    def run(self, iters=70, log=print):
        t0 = time.time()
        self.hard_fail = set()
        for p in (q for ps in self.pads.values() for q in ps):
            p["cellset"] = set(p["cells"])
        smd = self.smd_own != 0
        self.smd_far = ndimage.distance_transform_edt(~smd) * G >= VIA_D / 2 + 0.06
        names = [n for n in self.nets if n != "GND" and len(self.pads.get(self.nets[n], [])) >= 2]

        def hpwl(nm):
            ps = self.pads[self.nets[nm]]
            xs = [p["x"] for p in ps]
            ys = [p["y"] for p in ps]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))
        order = [n for n in POWER_ORDER if n in names] + sorted(
            [n for n in names if n not in POWER_ORDER], key=hpwl)
        self.locked = set()
        self.frozen = set()
        self.preroute_usb()
        n_buck = self.preroute_buck(log=log)      # before the module's thermal vias (VBAT, BATN under it)
        n_ep = self.preroute_ep()
        n_led = self.preroute_leds(log=log)
        log(f"buck escapes, LED+ paths and pins beside the receptacle (EN, VOS, DEF, FB, QS, VSET, "
            f"R10, LED+ top face, LED+ via, In2 LED+ track, PROG, VBUS, VBAT trunk, PROT_OD/OC/CS/VCC, R35, "
            f"DW01A ground, LDO VBAT + GND, PVIN, S2_COM, RS1 ground, C5 ground, Q3 ground, R36 Kelvin stub, BAT- track, D1 + U4.51 ground, CHG_STAT, RST_G, U4.14 + U3.2 "
            f"ground, J2 pad vias): {n_buck} of 37")
        log(f"pre-routes: USB D+/D-, {n_ep} thermal vias in the module pad, {n_led} ring-LED fan-outs")
        if USB_FIRST:
            # v0.6: the module's USB pins sit side by side in the bottom pad row next to the board
            # edge; their only way out is a via each under the module.  Routed first (inner layer
            # preferred) and locked, so the signal negotiation cannot take those via spots.
            saved = dict(LAYER_COST)
            LAYER_COST.update({0: 3.0, 3: 3.0})
            usb = [n for n in ("USB_DP", "USB_DN") if n in self.nets]
            self.gnd_cid = {}
            snap = self._snapshot()
            for seq in (usb, usb[::-1]):          # the first one can block the second: try both orders
                self._restore(snap)
                res = [self.route_net(nm, 6.0)[0] for nm in seq]
                if all(res):
                    break
            for nm, ok in zip(seq, res):
                code = self.nets[nm]
                self.locked |= {c for c, (n, _it) in self.conns.items() if n == code}
                if ok:
                    self.frozen.add(code)
                log(f"USB first: {nm} {'routed' if ok else 'FAILED'}")
            LAYER_COST.clear()
            LAYER_COST.update(saved)
            self.hard_fail = set()
        self.gnd_cid = {}
        self._set_pour_state(None)
        pk = {self._gkey(p) for p in self._gnd_pads() if p["ref"] in POWER_GND}
        fails, _ = self.fanout_gnd(pfac=6.0, only=pk, force=True, lock=True)
        log(f"power-stage GND vias: {len(pk) - len(fails)} of {len(pk)}")
        if GND_RESERVE > 0:
            # v0.6: a trial stub + via for every GND pad on the empty board, then removed again;
            # its cells get extra history so the signals leave those spots free if they can
            snap = self._snapshot()
            before = set(self.conns)
            fails, _ = self.fanout_gnd(pfac=6.0)
            m = np.zeros(self.trk.shape, dtype=np.int8)
            n_res = 0
            for c, (n, items) in self.conns.items():
                if c not in before:
                    self.raster_items(items, 1, m, grow=CLR)
                    n_res += 1
            self._restore(snap)
            self.H[m != 0] += GND_RESERVE
            log(f"GND via spots reserved (soft): {n_res}, no spot for {len(fails)}")
        gnd_on = self.gnd_first
        if gnd_on:
            # v0.6: every GND pad gets its stub + via before the signals (locked, so the
            # PathFinder phase routes around them - a dense board has no via sites left later)
            fails, _ = self.fanout_gnd(pfac=6.0, lock=True)
            log(f"GND fanout: {len(fails)} failed {fails[:6]}, {time.time() - t0:.0f}s")
        queue = list(order)
        self.fails = {}
        pfac = 6.0
        if PF_ITERS > 0:
            queue = self.negotiate_pf(order, PF_ITERS, log=log, t0=t0)
            pfac = PF_PFAC_AFTER
        it_phase = 0
        gnd_fail = []
        for it in range(iters):
            if gnd_on and it_phase >= self.gnd_iters and not self.gnd_first:
                break
            if not gnd_on and (not queue or it >= self.gnd_start):
                gnd_on = True
                it_phase = 0
                if self.gnd_iters == 0:
                    break
                # GND stubs may push signal copper around again
                self.frozen = {self.nets[n] for n in FREEZE if n in self.nets and n not in queue}
                log(f"GND phase from iteration {it + 1}")
            miss = self.gnd_missing() if gnd_on else set()
            if gnd_on and not queue and not miss:
                break
            for nm in queue:
                ok, _v = self.route_net(nm, pfac)
                if ok and nm in FREEZE_EARLY and nm in self.nets:
                    self.frozen.add(self.nets[nm])        # later nets route around it
            gnd_fail = []
            if gnd_on:
                self.pour_fill()
                miss = self.gnd_missing()
                if miss:
                    gnd_fail, _ = self.fanout_gnd(pfac=pfac, only=miss)
            incomplete = [n for n in order if len(self.components(self.nets[n])[0]) > 1]
            queue = incomplete
            if ADAPTIVE_ORDER:
                # v0.6: nets that keep failing go first in the next round (power nets keep
                # their lead); the v0.5 fixed order let the same late nets lose every round
                for n in incomplete:
                    self.fails[n] = self.fails.get(n, 0) + 1
                pw = [n for n in queue if n in POWER_ORDER]
                queue = pw + sorted([n for n in queue if n not in POWER_ORDER],
                                    key=lambda n: (-self.fails.get(n, 0), order.index(n)))
            for n in FREEZE:
                if n in self.nets and n not in incomplete:
                    self.frozen.add(self.nets[n])
            if it_phase >= FREEZE_ALL_AFTER:
                # progressive freeze: complete nets keep their copper; a net (or
                # GND pad) that cannot find any path unfreezes the nets around it
                for n in order:
                    if n not in incomplete:
                        self.frozen.add(self.nets[n])
                spots = []
                for n in self.hard_fail:
                    code = self.nets[n]
                    spots.append((code, [c for p in self.pads[code] for c in p["cells"]]))
                for key in gnd_fail:
                    spots.append((self.nets["GND"], [key[2]]))
                for code, cells in spots:
                    jlo, jhi, ilo, ihi = self.window_for(cells, cells, 1.5)
                    near = set(np.unique(self.trk[:, jlo:jhi, ilo:ihi]).tolist()) - {0, code}
                    for v in near:
                        if self.code_name.get(v) not in FREEZE:
                            self.frozen.discard(v)
            miss = self.gnd_missing() if gnd_on else set()
            log(f"iter {it + 1}: pfac {pfac:.1f}, incomplete {len(queue)} {queue[:12]}, "
                f"search failures {sorted(self.hard_fail)}, GND pads off-plane {len(miss)}"
                f"{' (GND phase)' if gnd_on else ''}, {time.time() - t0:.0f}s")
            self.hard_fail = set()
            pfac = min(pfac * 1.3, PFAC_MAX)
            it_phase += 1
        if True:                # v0.6: the monotonic repair also follows a GND-first negotiation
            # (three rounds; the window repair of finalize() takes over after run())
            self.repair(order, log=log, rounds=3)
            queue = self.incomplete(order)
        self.failed = queue
        self.gnd_fail = sorted(f"{k[0]}.{k[1]}" for k in self.gnd_missing())
        log(f"done: incomplete {queue}, GND pads off-plane {self.gnd_fail}, {time.time() - t0:.0f}s")
        return queue

    # ------------------------------------------------------------- PathFinder phase
    def negotiate_pf(self, order, iters, log=print, t0=None, patience=None):
        """v0.6: PathFinder-style negotiation before the rip-up loop.  The buck nets in FREEZE
        are routed first and keep their copper.  Then every other net is routed against the
        locked/frozen copper only; the copper of the other nets in this phase is a soft
        obstacle (cost pfac per conflicting cell, history H) and is never ripped, so two nets
        may overlap for a while.  After each round the cells where nets overlap (closer than the
        clearance) get more history, and only the nets involved are re-routed.  When no overlap
        is left (or after `iters` rounds) the copper goes into the normal tables; nets still in
        conflict are left for the rip-up loop.  Returns the incomplete nets."""
        t0 = t0 or time.time()
        SOFT = -7
        base_trk, base_cid = self.trk.copy(), self.cid.copy()
        nets = [n for n in order if self.nets[n] not in self.frozen]
        gcode = self.nets["GND"]
        gkeys = {}
        if PF_GND:
            # every GND pad still off the plane is a "net" of its own: a stub to a new via (or to
            # GND copper that has one); GND stubs may share copper, they only conflict with signals
            for key in sorted(self.gnd_missing()):
                gkeys[f"GND:{key[0]}.{key[1]}"] = key
            nets += list(gkeys)

        def codeof(n):
            return gcode if n in gkeys else self.nets[n]
        shape = self.trk.shape
        cop = {n: np.zeros(shape, dtype=bool) for n in nets}
        conns = {n: [] for n in nets}
        self._pf_conns = conns
        cnt = np.zeros(shape, dtype=np.int16)
        cntg = np.zeros(shape, dtype=np.int16)          # GND stub copper only
        orig_commit, orig_victims = self.commit, self.victims
        cur = {}

        def pf_commit(code, items, no_rip=False):
            cells = self.raster_items(items, code, self.trk)
            conns[cur["n"]].append(items)
            return cells, set()

        def pf_victims(code, items):
            probe = self.raster_items(items, None, self.trk, grow=CLR + MARGIN)
            return {c for c in probe if self.trk[c] == SOFT}

        todo = list(nets)
        pfac = 6.0
        halo = {n: np.zeros(shape, dtype=bool) for n in nets}   # clearance halo of each net's copper
        for it in range(iters):
            for n in todo:
                code = codeof(n)
                isg = n in gkeys
                cnt -= cop[n].astype(np.int16)
                if isg:
                    cntg -= cop[n].astype(np.int16)
                cop[n][:] = False
                conns[n] = []
                view = base_trk.copy()
                if isg:
                    view[(cntg > 0) & (view == 0)] = gcode
                    view[(cnt > cntg) & (view == 0)] = SOFT
                else:
                    view[(cnt > 0) & (view == 0)] = SOFT
                before = view == code
                self.trk, self.cid = view, base_cid
                self.commit, self.victims = pf_commit, pf_victims
                cur["n"] = n
                try:
                    if isg:
                        self.fanout_gnd(pfac=pfac, only={gkeys[n]}, reach=2.5)
                    else:
                        self.route_net(n, pfac)
                finally:
                    self.commit, self.victims = orig_commit, orig_victims
                cop[n] = (view == code) & ~before
                cnt += cop[n].astype(np.int16)
                if isg:
                    cntg += cop[n].astype(np.int16)
                h = np.zeros(shape, dtype=np.int8)
                for items in conns[n]:
                    self.raster_items(items, 1, h, grow=CLR + MARGIN)
                halo[n] = h != 0
            # overlap = exactly the commit() test: another net's copper inside this net's halo
            conflicted, ncells = [], 0
            hit = np.zeros(shape, dtype=bool)
            for n in nets:
                if not cop[n].any():
                    continue
                if n in gkeys:
                    foreign = (cnt - cntg) > 0
                else:
                    foreign = (cnt - cop[n].astype(np.int16)) > 0
                bad = halo[n] & foreign
                if bad.any():
                    hit |= bad
                    ncells += int(bad.sum())
                    conflicted.append(n)
            self.H[hit] += HIST_INC
            self.trk, self.cid = base_trk, base_cid
            incomplete = []
            for n in nets:
                if n in gkeys:
                    continue
                code = self.nets[n]
                view = base_trk.copy()
                view[cop[n]] = code
                self.trk = view
                if len(self.components(code)[0]) > 1:
                    incomplete.append(n)
            if gkeys:
                view = base_trk.copy()
                view[(cntg > 0) & (view == 0)] = gcode
                self.trk = view
                gm = self.gnd_missing()
                incomplete += [n for n, key in gkeys.items() if key in gm]
            self.trk = base_trk
            todo = [n for n in nets if n in conflicted or n in incomplete]
            if PF_NEIGHBOURS > 0 and hit.any():
                # nets with copper near the conflicts move too (PathFinder re-routes everyone;
                # settled nets that sit in the contested space must be able to give way)
                near = ndimage.binary_dilation(hit.any(axis=0), iterations=int(PF_NEIGHBOURS / G))
                for n in nets:
                    if n not in todo and (cop[n].any(axis=0) & near).any():
                        todo.append(n)
                todo = [n for n in nets if n in todo]
            log(f"PF round {it + 1}: pfac {pfac:.1f}, nets in conflict {len(conflicted)} ({ncells} cells) "
                f"{conflicted[:10]}, incomplete {incomplete[:8]}, {time.time() - t0:.0f}s")
            if not todo:
                break
            if patience:
                # local negotiations (window repair): stop when the overlap stops shrinking
                score = (len(incomplete), ncells)
                if it == 0 or score < best_score:
                    best_score, best_it = score, it
                elif it - best_it >= patience:
                    break
            pfac = min(pfac * PF_GROWTH, PFAC_MAX)
        dump = os.environ.get("FLASHKA_PF_DUMP")       # diagnostics: copper and conflicts after the PF phase
        if dump:
            import pickle
            with open(dump, "wb") as f:
                pickle.dump({"conns": {n: list(conns[n]) for n in nets}, "hit": hit, "todo": todo,
                             "x0": self.x0, "y0": self.y0, "G": G}, f)
        # into the normal tables: conflict-free nets first, then the rest without ripping
        self._pf_conns = {}
        self.trk, self.cid = base_trk.copy(), base_cid.copy()
        first = [n for n in nets if n not in todo] + [n for n in nets if n in todo]
        for n in first:
            for items in conns[n]:
                cells, _v = self.commit(codeof(n), items, no_rip=True)
                if cells is not None and n in gkeys:
                    self.gnd_cid[gkeys[n]] = self.next_cid - 1
        inc = [n for n in order if len(self.components(self.nets[n])[0]) > 1]
        for n in FREEZE:                  # buck nets keep their copper from here on
            if n in self.nets and n not in inc:
                self.frozen.add(self.nets[n])
        return inc

    # ------------------------------------------------------------- repair
    def _snapshot(self):
        return (self.trk.copy(), self.cid.copy(), self.H.copy(),
                {c: (n, list(it)) for c, (n, it) in self.conns.items()},
                set(self.frozen), set(self.locked), dict(self.gnd_cid), self.next_cid)

    def _restore(self, snap):
        trk, cid, H, conns, frozen, locked, gcid, nxt = snap
        self.trk[:] = trk
        self.cid[:] = cid
        self.H[:] = H
        self.conns, self.frozen, self.locked, self.gnd_cid = conns, frozen, locked, gcid
        self.next_cid = max(self.next_cid, nxt)

    def incomplete(self, names):
        return [n for n in names if self.n_groups(self.nets[n]) > 1]

    def _settle(self, names, pfac, rounds=8):
        """Re-route the given nets (everything else frozen) until complete."""
        for _ in range(rounds):
            inc = self.incomplete(names)
            if not inc:
                return True
            for n in inc:
                self.route_net(n, pfac)
        return not self.incomplete(names)

    def deep_settle(self, order, pfac, iters=14):
        """Negotiate every incomplete net with all signal copper rippable
        (only the power stage, locked pre-routes and GND copper stay put),
        progressive freeze in the second half."""
        base = {self.nets[n] for n in FREEZE if n in self.nets}
        gnd = self.nets.get("GND")
        saved = set(self.locked)
        self.locked |= {c for c, (n, _) in self.conns.items() if n == gnd}
        self.frozen = set(base)
        for it in range(iters):
            inc = self.incomplete(order)
            if not inc:
                break
            self.hard_fail = set()
            for n in inc:
                self.route_net(n, pfac)
            if it >= iters // 2:
                for n in order:
                    if n not in self.incomplete(order):
                        self.frozen.add(self.nets[n])
        self.locked = saved
        return not self.incomplete(order)

    def deep_repair(self, order, log=print, pfac=40.0):
        """Last resort, still monotonic: for each GND pad off the plane, lock a
        stub + via to it and re-negotiate all signal nets; for incomplete
        signal nets, re-negotiate everything.  Every attempt that does not end
        with all nets complete and fewer problems is undone."""
        t0 = time.time()
        self.allow_relax = False
        base = {self.nets[n] for n in FREEZE if n in self.nets}
        if self.incomplete(order):
            n_inc = len(self.incomplete(order))
            snap, pour_snap = self._snapshot(), self._pour_state()
            m0 = len(self.gnd_missing())
            ok = self.deep_settle(order, pfac)
            if ok:
                self.pour_fill()
                ok = len(self.gnd_missing()) <= m0
            if not ok and len(self.incomplete(order)) >= n_inc:
                self._restore(snap)
                self._set_pour_state(pour_snap)
            log(f"deep repair (signals): incomplete {self.incomplete(order)}, {time.time() - t0:.0f}s")
        self.pour_fill()
        for key in sorted(self.gnd_missing()):
            cur = self.gnd_missing()
            if key not in cur or self.incomplete(order):
                continue
            snap, pour_snap = self._snapshot(), self._pour_state()
            done = set(order)
            self.frozen = set(base)
            fails, vnets = self.fanout_gnd(pfac=pfac, only={key}, lock=True, reach=3.5)
            ok = not fails and self.deep_settle(order, pfac)
            if ok:
                self.pour_fill()
                ok = len(self.gnd_missing()) < len(cur)
            if ok:
                log(f"deep repair: GND {key[0]}.{key[1]} tied to the plane, {time.time() - t0:.0f}s")
            else:
                self._restore(snap)
                self._set_pour_state(pour_snap)
        self.frozen = base | {self.nets[n] for n in order if n not in self.incomplete(order)}
        self.allow_relax = True
        return not self.gnd_missing() and not self.incomplete(order)

    def repair(self, order, log=print, rounds=6, pfac=60.0):
        """End game, monotonic: every change that leaves a net or a GND pad
        worse off is undone.  (1) incomplete signal nets: route with the
        neighbours unfrozen, re-route what was ripped, keep only if all nets
        end up complete; (2) GND pads off the plane (real KiCad pour fill):
        in-group via or stub without ripping, else a stub that may rip
        signals, which are then re-routed - or the attempt is reverted."""
        t0 = time.time()
        base = {self.nets[n] for n in FREEZE if n in self.nets}
        self.allow_relax = False
        last_state = None
        for rnd in range(rounds):
            inc = self.incomplete(order)
            for name in inc:
                if name not in self.incomplete(order):
                    continue
                for radius in (2.0, 4.0, None):
                    n_before = len(self.incomplete(order))
                    snap = self._snapshot()
                    done = set(order) - set(self.incomplete(order))
                    self.frozen = base | {self.nets[n] for n in done}
                    code = self.nets[name]
                    if radius is None:
                        self.frozen = set(base)
                    else:
                        cells = [c for p in self.pads[code] for c in p["cells"]]
                        jlo, jhi, ilo, ihi = self.window_for(cells, cells, radius)
                        near = set(np.unique(self.trk[:, jlo:jhi, ilo:ihi]).tolist()) - {0, code}
                        self.frozen -= {v for v in near if self.code_name.get(v) not in FREEZE}
                    self.hard_fail = set()
                    ok, vnets = self.route_net(name, pfac)
                    vic = [self.code_name[v] for v in vnets if self.code_name.get(v) in order]
                    self.frozen = base | {self.nets[n] for n in done if n not in vic}
                    if not (ok and self._settle([name] + vic, pfac)) or len(self.incomplete(order)) >= n_before:
                        self._restore(snap)
                    else:
                        log(f"repair: {name} routed (re-routed {vic}), {time.time() - t0:.0f}s")
                        break
            self.pour_fill()
            miss = sorted(self.gnd_missing())
            inc = self.incomplete(order)
            log(f"repair round {rnd + 1}: incomplete {inc}, GND pads off-plane {len(miss)}, {time.time() - t0:.0f}s")
            if not miss and not inc:
                return True
            state = (tuple(inc), tuple(miss))
            if rnd > 0 and state == last_state:
                break                    # a whole round without any change: the next one is the same
            last_state = state
            for key in miss:
                cur_miss = self.gnd_missing()
                if key not in cur_miss:
                    continue
                fails, _ = self.fanout_gnd(hard=True, only={key})
                if not fails:
                    continue
                for reach in (2.2, 3.5):
                    n_before = len(self.incomplete(order))
                    m_before = len(cur_miss)
                    snap = self._snapshot()
                    pour_snap = self._pour_state()
                    done = set(order) - set(self.incomplete(order))
                    self.frozen = base | {self.nets[n] for n in done}
                    k, j, i = key[2]
                    rr = int((reach + 1.0) / G)
                    near = set(np.unique(self.trk[:, max(j - rr, 0):j + rr, max(i - rr, 0):i + rr]).tolist()) - {0}
                    self.frozen -= {v for v in near if self.code_name.get(v) not in FREEZE}
                    fails, vnets = self.fanout_gnd(pfac=pfac, only={key}, lock=True, reach=reach)
                    vic = [self.code_name[v] for v in vnets if self.code_name.get(v) in order]
                    self.frozen = base | {self.nets[n] for n in done if n not in vic}
                    ok = not fails and self._settle(vic, pfac) and len(self.incomplete(order)) <= n_before
                    if ok and vic:
                        # re-routed signals may have cut pours other GND pads relied on
                        self.pour_fill()
                        ok = len(self.gnd_missing()) < m_before
                    if not ok:
                        self._restore(snap)
                        self._set_pour_state(pour_snap)
                    else:
                        log(f"repair: GND {key[0]}.{key[1]} tied to the plane (re-routed {vic})")
                        break
        self.pour_fill()
        self.allow_relax = True
        return not self.gnd_missing() and not self.incomplete(order)

    # ------------------------------------------------------------- window repair (v0.6)
    def prepare(self):
        """Search state that run() sets up (also used before load_copper)."""
        self.hard_fail = set()
        for p in (q for ps in self.pads.values() for q in ps):
            p["cellset"] = set(p["cells"])
        smd = self.smd_own != 0
        self.smd_far = ndimage.distance_transform_edt(~smd) * G >= VIA_D / 2 + 0.06
        self.locked, self.frozen, self.gnd_cid = set(), set(), {}

    def signal_order(self):
        names = [n for n in self.nets if n != "GND" and len(self.pads.get(self.nets[n], [])) >= 2]
        return [n for n in POWER_ORDER if n in names] + sorted(n for n in names if n not in POWER_ORDER)

    def _fits_pads(self, code, it):
        """Routed item still legal against the pads, holes and keep-outs of this placement
        (used when parts moved since the copper was routed)."""
        tmp = np.zeros(self.trk.shape, dtype=np.int8)
        cells = self.raster_items([it], 1, tmp, grow=CLR)
        for (k, j, i) in cells:
            o = self.owner[k, j, i]
            if o != 0 and o != code:
                return False
        if it[0] == "via":
            x, y = it[1]
            i, j = self.ij(x, y)
            if not self.smd_far[j, i] or not self._via_hole_ok(x, y):
                return False
        return True

    def load_copper(self, routed_path, log=print, drop_conflicts=False):
        """Routed copper of an earlier run (tracks and vias of routed_path, same placement) into
        the tables, one connection per segment / via.  The pre-routes (USB escape, module pad
        vias, ring-LED fan-outs) are made again and stay locked; copper that repeats them is
        skipped."""
        self.prepare()
        self.preroute_usb()
        self.preroute_buck(log=log)
        self.preroute_ep()
        self.preroute_leds(log=lambda m: None)
        pre = []
        for c in self.locked:
            n, items = self.conns[c]
            pre += [(n, it) for it in items]

        def same(a, b):
            if a[0] != b[0]:
                return False
            if a[0] == "via":
                return math.dist(a[1], b[1]) < 1e-3
            ka, *pa = a[1]
            kb, *pb = b[1]
            return ka == kb and (all(abs(u - v) < 1e-3 for u, v in zip(pa[:4], pb[:4])) or
                                 all(abs(u - v) < 1e-3 for u, v in zip(pa[:4], pb[2:4] + pb[0:2])))
        b = pcbnew.LoadBoard(routed_path)
        n_new = n_drop = 0
        found = []
        for t in b.GetTracks():
            name = str(t.GetNetname())
            if name not in self.nets:
                continue
            if t.GetClass() == "PCB_VIA":
                it = ("via", (mm(t.GetPosition().x), mm(t.GetPosition().y)))
            else:
                lid = t.GetLayer()
                if lid not in LAYER_IDS:
                    continue
                it = ("seg", (LAYER_IDS.index(lid), mm(t.GetStart().x), mm(t.GetStart().y),
                              mm(t.GetEnd().x), mm(t.GetEnd().y), mm(t.GetWidth())))
            found.append((name, it))
        # v0.6: canonical order (net, kind, coordinates), not the file order - the result of
        # the repair phase must depend on the copper only
        found.sort(key=lambda q: (q[0], q[1][0], tuple(round(v, 4) for v in q[1][1])))
        if LOAD_SEED:                 # another fixed order (the repair outcome depends on it)
            perm = np.random.default_rng(LOAD_SEED).permutation(len(found))
            found = [found[i] for i in perm]
        for name, it in found:
            code = self.nets[name]
            if any(n == code and same(it, q) for (n, q) in pre):
                continue
            if drop_conflicts and not self._fits_pads(code, it):
                n_drop += 1
                continue
            cid = self.next_cid
            self.next_cid += 1
            self.conns[cid] = (code, [it])
            for (k, j, i) in self.raster_items([it], code, self.trk):
                self.cid[k, j, i] = cid
            n_new += 1
        self.frozen = {self.nets[n] for n in FREEZE if n in self.nets}
        log(f"load: {n_new} routed items from {os.path.basename(routed_path)}"
            + (f", {n_drop} dropped (pads moved)" if n_drop else ""))
        return n_new

    def atomize(self):
        """Split every unlocked connection into one connection per item, so a window rip
        removes only the copper inside the window."""
        for c in [c for c in self.conns if c not in self.locked]:
            n, items = self.conns[c]
            if len(items) < 2:
                continue
            self.rip_conn(c)
            for it in items:
                cid = self.next_cid
                self.next_cid += 1
                self.conns[cid] = (n, [it])
                for (k, j, i) in self.raster_items([it], n, self.trk):
                    self.cid[k, j, i] = cid

    def _local_negotiation(self, names, inc_before, everyone, iters=14):
        """PathFinder negotiation of a few nets after a window rip: their copper left outside
        the window is locked (hard for the others, own copper for themselves), everything else
        is frozen.  True when every net that was complete before is complete again."""
        names = list(dict.fromkeys(names))
        codes = {self.nets[n] for n in names}
        extra = {c for c, (n, _it) in self.conns.items() if n in codes and c not in self.locked}
        self.locked |= extra
        self.frozen = set(everyone) - codes
        try:
            self.negotiate_pf(names, iters, log=lambda m: None, patience=5)
            left = self.incomplete(names)
            if left:
                self.frozen = set(everyone) - {self.nets[n] for n in left}
                self._settle(left, 60.0, rounds=3)
        finally:
            self.locked -= extra
        return set(self.incomplete(names)) <= set(inc_before)

    def exact_groups(self, code):
        """Exact connectivity of one net from the copper shapes (shapely): pads, routed
        segments and vias, filled zones of the last pour_fill.  Shapes join where they overlap
        (round ends approximated from inside), vias and plated pads join all layers.  Returns
        (list of pad-key groups, set of pad keys tied to the main In1 GND zone)."""
        from shapely.geometry import LineString, Point, Polygon
        from shapely.strtree import STRtree
        geoms, owner = [], []          # owner: ("pad", key) / ("item", None) / ("zone", is_plane)
        layer_of = []
        for p in self.pads.get(code, []):
            key = (p["ref"], p["num"])
            for (k, poly, net) in self.pad_polys_of.get(key, []):
                geoms.append(Polygon(poly).buffer(0))
                owner.append(("pad", key))
                layer_of.append((k,) if not p["pth"] else (0, 1, 2, 3))
        for c, (n, items) in self.conns.items():
            if n != code:
                continue
            for kind, d in items:
                if kind == "seg":
                    k, x1, y1, x2, y2, w = d
                    g = Point(x1, y1).buffer(w / 2 - 1e-4, 8) if math.hypot(x2 - x1, y2 - y1) < 1e-9 \
                        else LineString([(x1, y1), (x2, y2)]).buffer(w / 2 - 1e-4, 8)
                    geoms.append(g)
                    owner.append(("item", None))
                    layer_of.append((k,))
                else:
                    geoms.append(Point(*d).buffer(VIA_D / 2 - 1e-4, 8))
                    owner.append(("item", None))
                    layer_of.append((0, 1, 2, 3))
        for (net, k, pts, holes, plane) in getattr(self, "zone_polys", []):
            if net != code:
                continue
            geoms.append(Polygon(pts, holes).buffer(1e-6))
            owner.append(("zone", plane))
            layer_of.append((k,))
        n = len(geoms)
        parent = list(range(n))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        if n:
            tree = STRtree(geoms)
            for a in range(n):
                for b in tree.query(geoms[a], predicate="intersects").tolist():
                    if b <= a or not (set(layer_of[a]) & set(layer_of[b])):
                        continue
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
        groups = {}
        plane_roots = {find(a) for a in range(n) if owner[a] == ("zone", True)}
        for a in range(n):
            if owner[a][0] == "pad":
                groups.setdefault(find(a), set()).add(owner[a][1])
        on_plane = set()
        for root, keys in groups.items():
            if root in plane_roots:
                on_plane |= keys
        return list(groups.values()), on_plane

    def exact_problems(self, order):
        """Signal nets whose pads are not all joined and SMD GND pads off the In1 plane, from
        exact shapes (after pour_fill)."""
        if not hasattr(self, "pad_polys_of"):
            self.pad_polys_of = {}
            for pad in self.board.GetPads():
                code = pad.GetNetCode()
                if code <= 0 or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    continue
                key = (pad.GetParent().GetReference(), pad.GetNumber())
                for k, lid in enumerate(LAYER_IDS):
                    if pad.IsOnLayer(lid) or pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                        for poly in self._pad_poly(pad, lid if k in (0, 3) else pcbnew.F_Cu):
                            self.pad_polys_of.setdefault(key, []).append((k, poly, code))
                        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                            break
        inc = []
        for nm in order:
            groups, _ = self.exact_groups(self.nets[nm])
            if len(groups) > 1:
                inc.append(nm)
        _g, on_plane = self.exact_groups(self.nets["GND"])
        miss = sorted(self._gkey(p) for p in self._gnd_pads() if (p["ref"], p["num"]) not in on_plane)
        return inc, miss

    def audit_clearance(self, min_clr=0.101):
        """Exact copper-to-copper check (shapely) of every routed item against the items and
        pads of the other nets on its layers; returns the connection ids of items closer than
        min_clr (KiCad DRC: 0.10 mm).  A safety net for the raster model."""
        from shapely.geometry import LineString, Point, Polygon
        from shapely.strtree import STRtree
        if not hasattr(self, "pad_polys_of"):
            self.exact_problems([])
        geoms, meta = [], []           # meta: (net, layers, cid or None)
        for key, lst in self.pad_polys_of.items():
            for (k, poly, code) in lst:
                geoms.append(Polygon(poly).buffer(0))
                meta.append((code, (k,), None))
        for c, (n, items) in self.conns.items():
            for kind, d in items:
                if kind == "seg":
                    k, x1, y1, x2, y2, w = d
                    g = LineString([(x1, y1), (x2, y2)]).buffer(w / 2, 16) if math.hypot(x2 - x1, y2 - y1) > 1e-9 \
                        else Point(x1, y1).buffer(w / 2, 16)
                    geoms.append(g)
                    meta.append((n, (k,), c))
                else:
                    geoms.append(Point(*d).buffer(VIA_D / 2, 16))
                    meta.append((n, (0, 1, 2, 3), c))
        tree = STRtree(geoms)
        bad = set()
        for a in range(len(geoms)):
            if meta[a][2] is None:
                continue
            for b in tree.query(geoms[a].buffer(min_clr)).tolist():
                if b == a or meta[b][0] == meta[a][0] or not (set(meta[a][1]) & set(meta[b][1])):
                    continue
                if geoms[a].distance(geoms[b]) < min_clr:
                    bad.add(meta[a][2])
                    if meta[b][2] is not None:
                        bad.add(meta[b][2])
        # plated pad drills to other nets' tracks (rule file: 0.28 mm; vias: hole-to-hole rule)
        for (ax, ay, bx, by, r, hc) in self.pth_holes:
            hole = LineString([(ax, ay), (bx, by)]).buffer(r, 16) if math.hypot(bx - ax, by - ay) > 1e-9 \
                else Point(ax, ay).buffer(r, 16)
            for b in tree.query(hole.buffer(PTH_HOLE_CLR)).tolist():
                n, layers, c = meta[b]
                if c is None or len(layers) != 1 or (n == hc and hc > 0):
                    continue
                if geoms[b].distance(hole) < PTH_HOLE_CLR + 0.001:
                    bad.add(c)
        return bad

    def _copper_sig(self):
        """Fingerprint of the routed copper (skips repeating a failed repair attempt)."""
        import hashlib
        return hashlib.sha1(self.trk.tobytes()).hexdigest()

    def problems(self, order):
        """(incomplete signal nets, GND pads off the plane) with a fresh pour fill: the raster
        view of the router and the exact shapes (exact_problems) together."""
        self.pour_fill()
        inc, miss = self.incomplete(order), set(self.gnd_missing())
        inc2, miss2 = self.exact_problems(order)
        return [n for n in order if n in inc or n in inc2], sorted(miss | set(miss2))

    def bridge(self, name=None, key=None):
        """Join copper the raster sees as one piece but the exact shapes do not (gap of a few
        hundredths of a mm): a short track between the nearest points of two exact groups on a
        shared layer, if legal.  name: a signal net; key: a GND pad off the plane."""
        from shapely.geometry import LineString, Point, Polygon
        from shapely.ops import nearest_points, unary_union
        code = self.nets[name] if name else self.nets["GND"]
        per = {}           # layer -> list of (group id, geometry)

        def add(gid, k, g):
            per.setdefault(k, []).append((gid, g))
        groups, on_plane = self.exact_groups(code)
        # rebuild element geometries with their group: simplest is to map every element to the
        # group of the pads it touches, via a second pass over exact_groups' union-find
        elems = []
        for p in self.pads.get(code, []):
            kk = (p["ref"], p["num"])
            for (k, poly, _n) in self.pad_polys_of.get(kk, []):
                elems.append(((0, 1, 2, 3) if p["pth"] else (k,), Polygon(poly).buffer(0), ("pad", kk)))
        for c, (n, items) in self.conns.items():
            if n != code:
                continue
            for kind, d in items:
                if kind == "seg":
                    k, x1, y1, x2, y2, w = d
                    g = LineString([(x1, y1), (x2, y2)]).buffer(w / 2 - 1e-4, 8) if \
                        math.hypot(x2 - x1, y2 - y1) > 1e-9 else Point(x1, y1).buffer(w / 2 - 1e-4, 8)
                    elems.append(((k,), g, None))
                else:
                    elems.append(((0, 1, 2, 3), Point(*d).buffer(VIA_D / 2 - 1e-4, 8), None))
        for (net, k, pts, holes, plane) in getattr(self, "zone_polys", []):
            if net == code:
                elems.append(((k,), Polygon(pts, holes).buffer(1e-6), ("plane",) if plane else None))
        n = len(elems)
        parent = list(range(n))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        from shapely.strtree import STRtree
        tree = STRtree([e[1] for e in elems])
        for a in range(n):
            for b in tree.query(elems[a][1], predicate="intersects").tolist():
                if b > a and set(elems[a][0]) & set(elems[b][0]):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[ra] = rb
        if key is not None:
            src = {find(a) for a in range(n) if elems[a][2] == ("pad", (key[0], key[1]))}
            dst = {find(a) for a in range(n) if elems[a][2] == ("plane",)}
        else:
            roots = {}
            for a in range(n):
                if elems[a][2] and elems[a][2][0] == "pad":
                    roots.setdefault(find(a), 0)
                    roots[find(a)] += 1
            if len(roots) < 2:
                return False
            big = max(roots, key=lambda r: roots[r])
            src = set(roots) - {big}
            dst = {big}
        best = None
        for k in ROUTE:
            ga = [elems[a][1] for a in range(n) if find(a) in src and k in elems[a][0]]
            gb = [elems[a][1] for a in range(n) if find(a) in dst and k in elems[a][0]]
            if not ga or not gb:
                continue
            A, B = unary_union(ga), unary_union(gb)
            d = A.distance(B)
            if d < 0.12 and (best is None or d < best[0]):
                pa, pb = nearest_points(A, B)
                best = (d, k, pa, pb)
        if best is None:
            return False
        d, k, pa, pb = best
        dx, dy = pb.x - pa.x, pb.y - pa.y
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        e = 0.05
        for w in (SIGNAL_W, 0.127):
            items = [("seg", (k, pa.x - ux * e, pa.y - uy * e, pb.x + ux * e, pb.y + uy * e, w))]
            if self._legal_add(code, items):
                cid = self.next_cid
                self.next_cid += 1
                self.conns[cid] = (code, items)
                for (kk, j, i) in self.raster_items(items, code, self.trk):
                    self.cid[kk, j, i] = cid
                return True
        return False

    def window_repair(self, order, log=print, radii=(0.8, 1.6, 3.0), rounds=12, pfac=40.0,
                      max_time=None, plateau=True, perturb=4):
        """Monotonic local rip-up and re-route.  For every incomplete net (cells of its smaller
        pad groups) and every GND pad off the plane: remove all unlocked copper in a window
        around it (every net, GND stubs included), route the problem first with all other copper
        fixed, then re-route the nets that lost copper (they may push each other, nothing else),
        then give the GND pads that lost their via a new one.  Kept only when the number of
        problems (incomplete nets + GND pads off the plane) goes down; windows grow step by
        step."""
        t0 = time.time()
        self.allow_relax = False
        base = {self.nets[n] for n in FREEZE if n in self.nets}
        gcode = self.nets["GND"]
        self.atomize()
        inc, miss = self.problems(order)
        log(f"window repair: start, incomplete {inc}, GND pads off-plane {len(miss)}")
        everyone = set(self.nets.values())
        state_sig = lambda i, m: (tuple(i), tuple((k[0], k[1]) for k in m))
        tried = {}
        epoch = 0
        cost = lambda i, m: 3 * len(i) + len(m)     # a broken signal net weighs three ground pads
        seen = {state_sig(inc, miss)}
        best = (cost(inc, miss), self._snapshot(), self._pour_state())
        n_viol = len(self.audit_clearance())      # an attempt may not add clearance violations
        for rnd in range(rounds):
            changed = False
            todo = [("gnd", k) for k in miss] + [("net", n) for n in inc]     # cheap ones first
            for kind, what in todo:
                if max_time and time.time() - t0 > max_time:
                    break
                if (kind == "net" and what not in inc) or (kind == "gnd" and what not in miss):
                    continue
                n0 = cost(inc, miss)
                # a gap the raster does not see: a short bridge track first
                snap, pour_snap = self._snapshot(), self._pour_state()
                if self.bridge(name=what) if kind == "net" else self.bridge(key=what):
                    inc2, miss2 = self.problems(order)
                    if cost(inc2, miss2) < n0 and len(self.audit_clearance()) <= n_viol:
                        inc, miss = inc2, miss2
                        changed = True
                        seen.add(state_sig(inc, miss))
                        if cost(inc, miss) < best[0]:
                            best = (len(inc) + len(miss), self._snapshot(), self._pour_state())
                        log(f"window repair: bridged {what if kind == 'net' else what[0] + '.' + what[1]}")
                        continue
                    self._restore(snap)
                    self._set_pour_state(pour_snap)
                if kind == "net":
                    code = self.nets[what]
                    groups, cs = self.components(code)
                    if len(groups) > 1:
                        # the window spans one gap: the smallest group and the nearest copper cell
                        # of any other group (a long net with several loose pads: one gap at a time)
                        small = min(range(len(groups)), key=lambda g: len(cs[g]))
                        cells = [c for p in groups[small] for c in p["cells"]]
                        cy = sum(c[1] for c in cells) / len(cells)
                        cx = sum(c[2] for c in cells) / len(cells)
                        near = [min(cs[g], key=lambda c: (c[1] - cy) ** 2 + (c[2] - cx) ** 2)
                                for g in range(len(groups)) if g != small]
                        cells.append(min(near, key=lambda c: (c[1] - cy) ** 2 + (c[2] - cx) ** 2))
                    else:                   # only the exact shapes see the gap
                        eg, _p = self.exact_groups(code)
                        keys = set().union(*sorted(eg, key=len)[:-1]) if len(eg) > 1 else set()
                        cells = [c for p in self.pads[code] if (p["ref"], p["num"]) in keys for c in p["cells"]]
                        if not cells:
                            continue
                else:
                    cells = [what[2]]
                for R in (["victims"] + list(radii)) if kind == "net" else (list(radii) + ["victims"]):
                    # deterministic: an attempt that failed on exactly this copper fails again
                    akey = (kind, what if kind == "net" else (what[0], what[1]), R)
                    if tried.get(akey) == self._copper_sig():
                        continue
                    snap, pour_snap = self._snapshot(), self._pour_state()
                    sig0 = self._copper_sig()
                    gm_before = set(miss)
                    self.hard_fail = set()
                    if R == "victims":
                        # route the problem through the other nets' copper (soft), rip whatever
                        # it crosses, then those nets entirely, and let them negotiate a new
                        # path anywhere on the board; a net that does not fit again is routed
                        # the same way in turn (rip-up chain, three levels)
                        ok = kind == "net"
                        ripped = set()
                        done_n, pending = set(), [what] if ok else []
                        for _depth in range(3):
                            newv = set()
                            for net in pending:
                                self.frozen = set(base) | {self.nets[n] for n in done_n if n != net}
                                okn, vnets = self.route_net(net, pfac)
                                if not okn:
                                    ok = ok and net != what
                                    continue
                                newv |= {self.code_name[v] for v in vnets if v != gcode
                                         and self.code_name.get(v) in order}
                                ripped |= set(vnets)
                            done_n |= set(pending)
                            newv -= done_n
                            if not ok or not newv:
                                break
                            codes = {self.nets[v] for v in newv}
                            for c, (n, _it) in list(self.conns.items()):
                                if n in codes and c not in self.locked:
                                    self.rip_conn(c)
                            self._local_negotiation(sorted(newv), inc, everyone)
                            pending = self.incomplete(sorted(newv))
                            if not pending:
                                break
                    else:
                        jlo, jhi, ilo, ihi = self.window_for(cells, cells, R)
                        ids = set(np.unique(self.cid[:, jlo:jhi, ilo:ihi]).tolist()) - {0}
                        ids = {c for c in ids if c in self.conns and c not in self.locked
                               and self.conns[c][0] not in base}
                        ripped = {self.conns[c][0] for c in ids}
                        for c in ids:
                            self.rip_conn(c)
                    if R == "victims":
                        pass
                    elif kind == "net":
                        self._local_negotiation([what] + [self.code_name[c] for c in ripped
                                                          if c != gcode and self.code_name[c] in order
                                                          and self.code_name[c] != what], inc, everyone)
                        ok = what not in self.incomplete([what])
                    else:
                        self.frozen = set(everyone)
                        fails, _v = self.fanout_gnd(pfac=pfac, only={what}, reach=R + 0.6)
                        ok = not fails
                        sig = [self.code_name[c] for c in ripped if c != gcode and self.code_name[c] in order]
                        if ok and sig:          # a ground pad is not worth a broken signal net
                            ok = self._local_negotiation(sig, inc, everyone)
                    if ok:
                        # GND pads that lost their via (ripped stubs, cut pours) get a new one
                        self.frozen = set(everyone)
                        self.pour_fill()
                        lost = self.gnd_missing() - gm_before - ({what} if kind == "gnd" else set())
                        if lost:
                            self.fanout_gnd(pfac=pfac, only=lost, reach=2.5)
                    if ok:
                        inc2, miss2 = self.problems(order)
                        n2 = cost(inc2, miss2)
                        fixed = (what not in inc2) if kind == "net" else \
                            ((what[0], what[1]) not in {(k[0], k[1]) for k in miss2})
                        # strictly better, or (plateau move) as many problems but this one gone
                        # and a set of problems not seen before - the trouble moves elsewhere
                        ok = n2 < n0 or (plateau and n2 == n0 and fixed and state_sig(inc2, miss2) not in seen)
                        if ok:
                            nv = len(self.audit_clearance())
                            ok = nv <= n_viol
                            if ok:
                                n_viol = nv
                    if ok:
                        changed = True
                        inc, miss = inc2, miss2
                        seen.add(state_sig(inc, miss))
                        if n2 < best[0]:
                            best = (n2, self._snapshot(), self._pour_state())
                        log(f"window repair: {what if kind == 'net' else what[0] + '.' + what[1]} fixed "
                            f"(window {R} mm, re-routed {sorted(self.code_name[c] for c in ripped)}), "
                            f"now incomplete {inc}, GND off-plane {len(miss)}, {time.time() - t0:.0f}s")
                        break
                    self._restore(snap)
                    self._set_pour_state(pour_snap)
                    tried[akey] = self._copper_sig()
                    if tried[akey] != sig0:
                        log(f"window repair: WARNING restore mismatch after {akey}")
            inc, miss = self.problems(order)
            log(f"window repair round {rnd + 1}: incomplete {inc}, GND pads off-plane "
                f"{[k[0] + '.' + k[1] for k in miss]}, {time.time() - t0:.0f}s")
            ck = os.environ.get("FLASHKA_CKPT")         # experiments: board after every round
            if ck:
                self.write(ck, zones=True)
            if not inc and not miss:
                break
            if not changed:
                # stuck with signal nets left: open In1 to them (whole board, cost 4) first - a
                # short jumper under the plane is better than an unrouted net
                rescue = {self.nets[n] for n in inc} - self.in1_rescue if IN1_BOX else set()
                if rescue:
                    self.in1_rescue |= rescue
                    tried = {}
                    log(f"window repair: In1 opened for {sorted(self.code_name[c] for c in rescue)}")
                    continue
                # then let the windows take VBAT copper too (frozen early, its wide track can
                # wall in pads); it is routed again like the other ripped nets
                vb = self.nets.get("VBAT")
                if vb in base:
                    base.discard(vb)
                    tried = {}
                    log("window repair: VBAT may be ripped and re-routed from now on")
                    continue
                if epoch >= perturb:
                    break
                # stuck: shake the congestion history (seeded, so runs repeat) and try again -
                # the same attempts on the same copper with other costs find other paths
                epoch += 1
                rng = np.random.default_rng(1000 + 100 * REPAIR_SEED + epoch)
                self.H += rng.exponential(1.5, self.H.shape).astype(np.float32)
                tried = {}
                log(f"window repair: no progress, congestion costs shaken (epoch {epoch})")
        if cost(inc, miss) > best[0]:          # plateau moves ended worse: back to the best
            self._restore(best[1])
            self._set_pour_state(best[2])
            inc, miss = self.problems(order)
            log(f"window repair: back to the best state, incomplete {inc}, GND pads off-plane {len(miss)}")
        self.frozen = base | {self.nets[n] for n in order if n not in inc}
        self.allow_relax = True
        self.failed = inc
        self.gnd_fail = sorted(f"{k[0]}.{k[1]}" for k in miss)
        return inc, miss

    def remove_islands(self, log=print):
        """Routed copper that touches no pad of its net (exact shapes, zones not counted): left
        over from rip-ups, KiCad reports it as unconnected items.  Removed, then pruned again."""
        from shapely.geometry import LineString, Point, Polygon
        from shapely.strtree import STRtree
        if not hasattr(self, "pad_polys_of"):
            self.exact_problems([])
        self.atomize()
        removed = 0
        gnd = self.nets["GND"]
        for code in sorted(set(n for n, _ in self.conns.values())):
            elems = []            # (layers, geometry, cid or None)
            for p in self.pads.get(code, []):
                for (k, poly, _n) in self.pad_polys_of.get((p["ref"], p["num"]), []):
                    elems.append(((0, 1, 2, 3) if p["pth"] else (k,), Polygon(poly).buffer(0), None))
            if code == gnd:       # the plane counts as a pad for ground copper
                for (net, k, pts, holes, plane) in getattr(self, "zone_polys", []):
                    if net == gnd and plane:
                        elems.append(((k,), Polygon(pts, holes).buffer(1e-6), None))
            for c, (n, items) in self.conns.items():
                if n != code:
                    continue
                for kind, d in items:
                    if kind == "seg":
                        k, x1, y1, x2, y2, w = d
                        g = LineString([(x1, y1), (x2, y2)]).buffer(w / 2 - 1e-4, 8) if \
                            math.hypot(x2 - x1, y2 - y1) > 1e-9 else Point(x1, y1).buffer(w / 2 - 1e-4, 8)
                        elems.append(((k,), g, c))
                    else:
                        elems.append(((0, 1, 2, 3), Point(*d).buffer(VIA_D / 2 - 1e-4, 8), c))
            n = len(elems)
            parent = list(range(n))

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a
            tree = STRtree([e[1] for e in elems])
            for a in range(n):
                for b in tree.query(elems[a][1], predicate="intersects").tolist():
                    if b > a and set(elems[a][0]) & set(elems[b][0]):
                        ra, rb = find(a), find(b)
                        if ra != rb:
                            parent[ra] = rb
            anchored = {find(a) for a in range(n) if elems[a][2] is None}
            for a in range(n):
                c = elems[a][2]
                if c is not None and find(a) not in anchored and c in self.conns and c not in self.locked:
                    self.rip_conn(c)
                    removed += 1
        log(f"islands: removed {removed} copper items that touch no pad of their net")
        return removed

    def _add_conn(self, code, items):
        cid = self.next_cid
        self.next_cid += 1
        self.conns[cid] = (code, items)
        for (k, j, i) in self.raster_items(items, code, self.trk):
            self.cid[k, j, i] = cid
        return cid

    def _stub_fix(self, code, it, fr):
        """Replacement items for a needed stub (see remove_stubs), or []: a track whose open end
        runs past the via / track end it joins is cut back to it; a via that joins tracks on one
        layer only is replaced by short tracks from their ends to its centre."""
        from shapely.geometry import LineString, Point
        kind, d = it
        end = fr                     # open end of a track (0 = start, 1 = end); None for a via
        if kind == "seg" and end is None:
            return []
        mine = [itm for (n, items) in self.conns.values() if n == code for itm in items]
        if kind == "seg":
            k, x1, y1, x2, y2, w = d
            fx, fy = (x2, y2) if end == 0 else (x1, y1)      # the end that stays
            ox, oy = (x1, y1) if end == 0 else (x2, y2)
            L = math.hypot(ox - fx, oy - fy)
            body = LineString([(x1, y1), (x2, y2)]).buffer(w / 2)
            line = LineString([(fx, fy), (ox, oy)])
            best = None
            for k2, d2 in mine:
                if k2 == "via":
                    pts = [d2]
                elif d2[0] == k:
                    pts = [(d2[1], d2[2]), (d2[3], d2[4])]
                else:
                    continue
                for q in pts:
                    if math.hypot(q[0] - fx, q[1] - fy) < 1e-6 or body.distance(Point(q)) > 1e-6:
                        continue
                    t = line.project(Point(q))
                    if best is None or t > best:
                        best = t
            if best is None or best < 1e-3 or best > L - 1e-3:
                return []
            p = line.interpolate(best)
            return [("seg", (k, fx, fy, round(p.x, 4), round(p.y, 4), w))]
        x, y = d
        out = []
        disk = Point(x, y).buffer(VIA_D / 2)
        for k2, d2 in mine:
            if k2 != "seg":
                continue
            k, ax, ay, bx, by, w = d2
            if LineString([(ax, ay), (bx, by)]).buffer(w / 2).distance(disk) > 1e-6:
                continue
            q = min(((ax, ay), (bx, by)), key=lambda q: math.hypot(q[0] - x, q[1] - y))
            if math.hypot(q[0] - x, q[1] - y) > 1e-6:
                out.append(("seg", (k, q[0], q[1], x, y, w)))
        return out

    def remove_stubs(self, order, log=print, locked_too=False):
        """Track pieces with an open end and vias that join fewer than two layers (grid
        left-overs, 0.05-0.15 mm; KiCad warns track_dangling / via_dangling).  Removed one at a
        time; put back if the exact connectivity check gets worse.  locked_too (the very end):
        the pre-routes as well - a hand-made escape the router did not continue from (it took
        another way) is a dead end then."""
        from shapely.geometry import LineString, Point, Polygon
        from shapely.strtree import STRtree
        if not hasattr(self, "pad_polys_of"):
            self.exact_problems([])
        if locked_too:
            self.locked = set()
        self.atomize()
        before = self.exact_problems(order)
        score = lambda pr: (len(pr[0]), len(pr[1]))
        removed = 0
        for _pass in range(60):           # a dead-end branch goes one piece per pass
            geoms, meta = [], []          # meta: (net, layers, cid or None)
            for lst in self.pad_polys_of.values():
                for (k, poly, code) in lst:
                    geoms.append(Polygon(poly).buffer(0))
                    meta.append((code, (k,), None))
            for (net, k, pts, holes, plane) in getattr(self, "zone_polys", []):
                geoms.append(Polygon(pts, holes).buffer(1e-6))
                meta.append((net, (k,), None))
            seg_idx, seg_d = set(), {}
            for c, (n, items) in self.conns.items():
                for kind, d in items:
                    if kind == "seg":
                        # centre line only: KiCad counts a track end as connected when it
                        # lies on another track's centre line (or in a pad, via or zone)
                        k, x1, y1, x2, y2, w = d
                        g = LineString([(x1, y1), (x2, y2)]).buffer(2e-3, 4) if \
                            math.hypot(x2 - x1, y2 - y1) > 1e-9 else Point(x1, y1).buffer(2e-3, 4)
                        seg_idx.add(len(geoms))
                        seg_d[len(geoms)] = d
                        meta.append((n, (k,), c))
                    else:
                        g = Point(*d).buffer(VIA_D / 2, 8)
                        meta.append((n, (0, 1, 2, 3), c))
                    geoms.append(g)
            tree = STRtree(geoms)

            def touching(g, net, layers, skip):
                out = set()
                for b in tree.query(g, predicate="intersects").tolist():
                    if b != skip and meta[b][0] == net and set(meta[b][1]) & set(layers):
                        out.add(b)
                return out
            cand, free = [], {}
            for idx, (n, layers, c) in enumerate(meta):
                if c is None or c in self.locked or c not in self.conns:
                    continue
                kind, d = self.conns[c][1][0]
                if kind == "seg":
                    k, x1, y1, x2, y2, w = d
                    # a piece lying on another track of the net is redundant (KiCad flags it)
                    if any(b in seg_idx and geoms[b].contains(LineString([(x1, y1), (x2, y2)]) if
                                                 math.hypot(x2 - x1, y2 - y1) > 1e-9 else Point(x1, y1))
                           for b in touching(geoms[idx], n, (k,), idx)):
                        cand.append(c)
                        continue
                    for e, (x, y) in enumerate(((x1, y1), (x2, y2))):
                        if not touching(Point(x, y).buffer(1e-3), n, (k,), idx):
                            cand.append(c)
                            free[c] = (idx, e)
                            break
                else:
                    lay = set()
                    for b in touching(geoms[idx], n, (0, 1, 2, 3), idx):
                        lay |= set(meta[b][1])
                    # a via also joins a track when its centre lies in the track's copper (the
                    # hand-made vias inside the cell pad sit on the In1 strip, off its centre line)
                    vp = Point(*d)
                    for b in tree.query(vp.buffer(1.2), predicate="intersects").tolist():
                        if b in seg_d and meta[b][0] == n and geoms[b].distance(vp) <= seg_d[b][5] / 2:
                            lay |= set(meta[b][1])
                    if len(lay) < 2:
                        cand.append(c)
                        free[c] = (idx, None)
            changed = False
            for c in cand:
                if c not in self.conns:
                    continue
                n, items = self.conns[c]
                self.rip_conn(c)
                now = self.exact_problems(order)
                if score(now) > score(before):
                    # needed copper: shorten the open end to the via / track it joins, or join
                    # a one-layer via's tracks directly, instead of keeping it as it is
                    new = self._stub_fix(n, items[0], free[c][1]) if c in free else []
                    cids = [self._add_conn(n, [it]) for it in new]
                    if cids:
                        now2 = self.exact_problems(order)
                        if score(now2) <= score(before) and not (self.audit_clearance() & set(cids)):
                            removed += 1
                            changed = True
                            before = now2
                            continue
                        for c2 in cids:
                            self.rip_conn(c2)
                    self._add_conn(n, items)
                else:
                    removed += 1
                    changed = True
                    before = now
            if not changed:
                break
        log(f"stubs: removed {removed} track pieces / vias with an open end")
        return removed

    def finalize(self, order, log=print, rounds=4):
        """v0.6 end game after run(): window repair, clean-up (finish), then the exact clearance
        audit; items closer than 0.10 mm to another net are ripped and repaired again."""
        self.window_repair(order, log=log)
        self.finish(log=log)
        for _ in range(rounds):
            self.atomize()           # prune() left one connection per net: rip single items only
            bad = self.audit_clearance()
            inc, miss = self.problems(order)
            if not bad and not inc and not miss:
                break
            stuck = [c for c in bad if c in self.locked]
            for c in bad:
                if c in self.conns and c not in self.locked:
                    self.rip_conn(c)
            log(f"finalize: clearance audit ripped {len(bad) - len(stuck)} items"
                + (f", {len(stuck)} locked items too close" if stuck else ""))
            self.window_repair(order, log=log, perturb=1)   # one shake only: the first pass had four
            self.prune(log=log)
        self.pour_fill()
        if self.remove_islands(log=log):
            self.prune(log=log)
        self.pour_fill()
        self.remove_stubs(order, log=log, locked_too=True)
        inc, miss = self.problems(order)
        bad = self.audit_clearance()
        self.failed = inc
        self.gnd_fail = sorted(f"{k[0]}.{k[1]}" for k in miss)
        log(f"finalize: incomplete {inc}, GND pads off-plane {self.gnd_fail}, clearance audit {len(bad)}")
        return inc, miss, bad

    # ------------------------------------------------------------- finishing
    def finish(self, log=print):
        """After routing: remove dangling copper, parallel vias on the
        high-current nets, then re-check GND plane connectivity with the real
        pour fill (extra vias can cut pours) and patch it without ripping."""
        self.prune(log=log)
        added = self.augment_vias(["VBAT", "VOUT", "ISNS", "SW"], n_extra=3)
        added += self.augment_vias(["VBUS"], n_extra=2)
        added += self.augment_vias(["GND"], n_extra=2, refs=POWER_GND)
        for _ in range(4):
            self.pour_fill()
            miss = self.gnd_missing()
            if not miss:
                break
            self.fanout_gnd(hard=True, only=miss)
        self.gnd_fail = sorted(f"{k[0]}.{k[1]}" for k in self.gnd_missing())
        log(f"finish: GND pads off-plane {self.gnd_fail}, extra vias {added}")
        return self.gnd_fail, added

    def augment_vias(self, names, n_extra=2, refs=None):
        """Add up to n_extra vias next to every via of the given nets, joined by
        short stubs on the two layers the original via connects (refs: only
        vias within 1.2 mm of those parts' pads of the net)."""
        added = 0
        for name in names:
            if name not in self.nets:
                continue
            code = self.nets[name]
            w = min(self.width_of(name), 0.4)
            near = None
            if refs:
                near = [(p["x"], p["y"]) for p in self.pads.get(code, []) if p["ref"] in refs]
            for cid, (n, items) in list(self.conns.items()):
                if n != code:
                    continue
                for idx, (kind, d) in enumerate(list(items)):
                    if kind != "via":
                        continue
                    vx, vy = d
                    if near is not None and not any(math.hypot(vx - x, vy - y) < 1.2 for (x, y) in near):
                        continue
                    # layers joined: tracks of this connection touching the via
                    lays = set()
                    for kind2, d2 in items:
                        if kind2 == "seg":
                            k, x1, y1, x2, y2, ww = d2
                            if math.dist((x1, y1), (vx, vy)) < 0.05 or math.dist((x2, y2), (vx, vy)) < 0.05:
                                lays.add(k)
                    for p in self.pads.get(code, []):
                        if math.dist((p["x"], p["y"]), (vx, vy)) < 1.0:
                            lays.update(k for k in p["layers"] if k in ROUTE)
                    lays = sorted(lays) or [0, 3]
                    got = 0
                    for rad in (0.6, 0.75):
                        for ang in range(0, 360, 30):
                            if got >= n_extra:
                                break
                            x = vx + rad * math.cos(math.radians(ang))
                            y = vy + rad * math.sin(math.radians(ang))
                            new = [("via", (x, y))] + [("seg", (k, vx, vy, x, y, w)) for k in lays]
                            if self._legal_add(code, new):
                                self.conns[cid][1].extend(new)
                                for (k, j, i) in self.raster_items(new, code, self.trk):
                                    self.cid[k, j, i] = cid
                                got += 1
                                added += 1
        return added

    def _legal_add(self, code, items):
        """Exact-ish legality of extra copper against everything else (hard)."""
        tmp = np.zeros(self.trk.shape, dtype=np.int32)
        self.raster_items(items, 1, tmp, grow=CLR + MARGIN)
        foreign = ((self.owner != 0) & (self.owner != code)) | ((self.trk != 0) & (self.trk != code))
        if (foreign & (tmp != 0)).any():
            return False
        own = np.zeros(self.trk.shape, dtype=np.int32)
        cells = self.raster_items(items, 1, own)
        is_gnd = code == self.nets.get("GND")
        vcells = set()
        for (x, y) in (d for kind, d in items if kind == "via"):
            vcells |= set((j, i) for (_k, j, i) in self._mark_circle([0], x, y, VIA_D / 2, None,
                                                                       np.zeros((1, self.ny, self.nx), dtype=np.int8)))
        for (k, j, i) in cells:
            blocked = self.keep[k, j, i]
            if blocked and is_gnd and (j, i) in vcells and self.gnd_via_ok[j, i]:
                blocked = False             # GND via under the USB-C shell
            if blocked or self.d_edge[j, i] < EDGE + MARGIN or self.D_npth[j, i] < NPTH_CLR + 0.04:
                return False
            if self.pth_dist(code)[j, i] < PTH_HOLE_CLR + 0.04:
                return False
        vias = [d for kind, d in items if kind == "via"]
        old = self.all_vias()
        for n, (x, y) in enumerate(vias):
            i, j = self.ij(x, y)
            if not self.smd_far[j, i]:
                return False
            if not self._via_hole_ok(x, y):
                return False
            for (x2, y2, _c) in old:
                if math.hypot(x - x2, y - y2) < VIA_PITCH:
                    return False
            for (x2, y2) in vias[n + 1:]:
                if math.hypot(x - x2, y - y2) < VIA_PITCH:
                    return False
        return True

    def _via_hole_ok(self, x, y):
        """Exact via-drill to pad-drill spacing (JLCPCB pad hole-to-hole)."""
        for (ax, ay, bx, by, r, _np) in self.holes:
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 < 1e-12 else min(max(((x - ax) * dx + (y - ay) * dy) / L2, 0.0), 1.0)
            if math.hypot(x - ax - t * dx, y - ay - t * dy) - r < VIA_DRILL / 2 + PADHOLE_GAP + 0.01:
                return False
        return True

    # ------------------------------------------------------------- cleanup
    def _seg_touch(self, x, y, d, tol=1e-3):
        k, x1, y1, x2, y2, w = d
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else min(max(((x - x1) * dx + (y - y1) * dy) / L2, 0.0), 1.0)
        return math.hypot(x - x1 - t * dx, y - y1 - t * dy) <= w / 2 + tol

    def _end_ok(self, code, k, x, y, me, segs, vias):
        i, j = self.ij(x, y)
        if 0 <= j < self.ny and 0 <= i < self.nx and self.owner[k, j, i] == code:
            return True
        for (vx, vy) in vias:
            if math.hypot(x - vx, y - vy) <= VIA_D / 2 + 1e-3:
                return True
        for d in segs:
            if d is not me and d[0] == k and self._seg_touch(x, y, d):
                return True
        return False

    def prune(self, log=print):
        """Remove track stubs with a free end and vias that join nothing
        (left behind when connections were ripped up and re-routed)."""
        gnd = self.nets.get("GND")
        zone_nets = {self.nets[z[0]] for z in LOCAL_ZONES if z[0] in self.nets}
        by_net, locked_items = {}, {}
        for cid, (n, items) in self.conns.items():
            by_net.setdefault(n, []).extend(items)
            if cid in self.locked:
                locked_items.setdefault(n, []).extend(items)
        removed = 0
        new = {}
        for n, items in by_net.items():
            items = list(dict.fromkeys(items))
            lock = set(locked_items.get(n, []))
            while True:
                segs = [d for kind, d in items if kind == "seg"]
                vias = [d for kind, d in items if kind == "via"]
                keep = []
                for it in items:
                    kind, d = it
                    if it in lock:
                        keep.append(it)
                        continue
                    if kind == "seg":
                        k, x1, y1, x2, y2, w = d
                        if math.hypot(x2 - x1, y2 - y1) < 1e-9:
                            continue
                        if self._end_ok(n, k, x1, y1, d, segs, vias) and self._end_ok(n, k, x2, y2, d, segs, vias):
                            keep.append(it)
                    else:
                        x, y = d
                        nconn = sum(1 for sd in segs if self._seg_touch(x, y, sd, VIA_D / 2))
                        i, j = self.ij(x, y)
                        nconn += int(any(self.owner[kk, j, i] == n for kk in range(4)))
                        if n == gnd or nconn >= 2 or (nconn == 1 and n in zone_nets):
                            keep.append(it)
                if len(keep) == len(items):
                    break
                removed += len(items) - len(keep)
                items = keep
            new[n] = items
        # rebuild the routed copper rasters from the pruned items, one entry per
        # net; a net whose pads come apart keeps its unpruned copper
        pre = getattr(self, "pre_items", set())

        def rebuild(table):
            self.trk[:] = 0
            self.cid[:] = 0
            self.conns, self.locked = {}, set()
            for n, items in table.items():
                # pre-routes (USB escape, module pad vias, ring-LED fan-outs) stay locked
                for part, lock in (([it for it in items if (n, it) in pre], True),
                                   ([it for it in items if (n, it) not in pre], False)):
                    if not part:
                        continue
                    cid = self.next_cid
                    self.next_cid += 1
                    self.conns[cid] = (n, part)
                    if lock:
                        self.locked.add(cid)
                    for (k, j, i) in self.raster_items(part, n, self.trk):
                        self.cid[k, j, i] = cid
        orig = {n: list(dict.fromkeys(items)) for n, items in by_net.items()}
        rebuild(new)
        broken = [n for n in new if n != gnd and n in self.pads and len(self.pads[n]) >= 2
                  and len(self.components(n)[0]) > 1]
        if broken:
            for n in broken:
                removed -= len(orig[n]) - len(new[n])
                new[n] = orig[n]
            rebuild(new)
            log(f"prune: kept the unpruned copper of {[self.code_name[n] for n in broken]}")
        gm = self.gnd_missing()
        log(f"prune: removed {removed} dangling items, GND pads off-plane after prune {len(gm)}")
        return removed

    # ------------------------------------------------------------- output
    def _add_copper(self, b):
        for code, items in self.items.items():
            for kind, d in items:
                if kind == "seg":
                    k, x1, y1, x2, y2, w = d
                    if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
                        continue
                    t = pcbnew.PCB_TRACK(b)
                    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
                    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
                    t.SetWidth(pcbnew.FromMM(w))
                    t.SetLayer(LAYER_IDS[k])
                    t.SetNetCode(code)
                    b.Add(t)
                else:
                    x, y = d
                    v = pcbnew.PCB_VIA(b)
                    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
                    v.SetWidth(pcbnew.FromMM(VIA_D))
                    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
                    v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNetCode(code)
                    b.Add(v)

    def _build_board(self, zones=True, gnd_layers=None):
        """Fresh copy of the unrouted board with the routed copper (and the
        pours, filled) - KiCad 7's Remove() of zones upsets the SWIG wrappers,
        so nothing is ever removed from a board here."""
        b = load_board(self.path)
        self._add_copper(b)
        apply_rules(b)
        if zones:
            self.add_zones(b, gnd_layers)
        return b

    def write(self, out_path, zones=True):
        b = self._build_board(zones)
        b.Save(out_path)

    def _pour_state(self):
        return None if self.pour is None else (self.pour.copy(), dict(self.pour_area), list(self.pour_merge))

    def _set_pour_state(self, st):
        if st is None:
            self.pour, self.pour_area, self.pour_merge = None, {}, []
        else:
            self.pour, self.pour_area, self.pour_merge = st[0], st[1], st[2]

    def pour_fill(self):
        """Fill the GND pours with KiCad on the current copper and rasterise
        every filled GND outline of all four layers as its own object (ids in
        self.pour; overlapping outlines of different zones are recorded in
        self.pour_merge) - for plane connectivity, see _gnd_labels."""
        lids = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
        # v0.6: the zones in the same order as the written board (add_zones default) - KiCad's
        # filler gives different F.Cu fills for another order, and the DRC sees the written one
        b = self._build_board(True)
        gnd = self.nets["GND"]
        # v0.6: every filled zone outline (all nets) for the exact connectivity check
        self.zone_polys = []
        for z in b.Zones():
            for lid in lids:
                if not z.IsOnLayer(lid):
                    continue
                fpl = z.GetFilledPolysList(lid)
                for n in range(fpl.OutlineCount()):
                    o = fpl.Outline(n)
                    pts = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
                    holes = []
                    for h in range(fpl.HoleCount(n)):
                        ho = fpl.Hole(n, h)
                        holes.append([(mm(ho.CPoint(i).x), mm(ho.CPoint(i).y)) for i in range(ho.PointCount())])
                    if len(pts) >= 3:
                        self.zone_polys.append((z.GetNetCode(), LAYER_IDS.index(lid), pts, holes,
                                                lid == pcbnew.In1_Cu and z.GetNetCode() == gnd))
        self.pour = np.zeros((4, self.ny, self.nx), dtype=np.int32)
        self.pour_area, self.pour_merge = {}, []
        nid = 0
        for z in b.Zones():
            if z.GetNetCode() != gnd:
                continue
            for lid in lids:
                if not z.IsOnLayer(lid):
                    continue
                k = LAYER_IDS.index(lid)
                fp = z.GetFilledPolysList(lid)
                for n in range(fp.OutlineCount()):
                    o = fp.Outline(n)
                    pts = [(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]
                    if len(pts) < 3:
                        continue
                    (j0, j1, i0, i1), m = self._poly_mask(pts)
                    for h in range(fp.HoleCount(n)):
                        ho = fp.Hole(n, h)
                        hp = [(mm(ho.CPoint(i).x), mm(ho.CPoint(i).y)) for i in range(ho.PointCount())]
                        if len(hp) < 3:
                            continue
                        (a0, a1, b0, b1), hm = self._poly_mask(hp)
                        ja, jb = max(a0, j0), min(a1, j1)
                        ia, ib = max(b0, i0), min(b1, i1)
                        if ja < jb and ia < ib:
                            m[ja - j0:jb - j0, ia - i0:ib - i0] &= ~hm[ja - a0:jb - a0, ia - b0:ib - b0]
                    if not m.any():
                        continue
                    nid += 1
                    sub = self.pour[k, j0:j1, i0:i1]
                    prev = np.unique(sub[m & (sub > 0)]).tolist()
                    self.pour_merge += [(int(q), nid) for q in prev]
                    sub[m] = nid
                    self.pour_area[nid] = (k, float(m.sum()) * G * G)
        return self.pour

    def local_zone(self, b, net, lid, refs_pads, grow=0.35, prio=3, full=True):
        """Small copper pour of `net` around the given (ref, pad) list on one
        layer: wide copper for the buck switch node, output and input."""
        xs, ys = [], []
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if (fp.GetReference(), pad.GetNumber()) in refs_pads:
                    bb = pad.GetBoundingBox()
                    xs += [mm(bb.GetLeft()), mm(bb.GetRight())]
                    ys += [mm(bb.GetTop()), mm(bb.GetBottom())]
        if not xs:
            return None
        z = pcbnew.ZONE(b)
        z.SetLayer(lid)
        z.SetNetCode(self.nets[net])
        z.SetAssignedPriority(prio)
        z.SetLocalClearance(pcbnew.FromMM(CLR + 0.02))
        z.SetMinThickness(pcbnew.FromMM(0.15))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if full else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        x0, x1, y0, y1 = min(xs) - grow, max(xs) + grow, min(ys) - grow, max(ys) + grow
        for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        b.Add(z)
        return z

    def kelvin_keepout(self, b):
        """No-pour rule area on the bottom face over the Kelvin pads (KELVIN_PADS) and their stub
        to Q3's P- pin, so that the ground pour leaves them alone (tracks and vias allowed)."""
        fps = {f.GetReference(): f for f in b.GetFootprints()}
        for (ref, num) in sorted(KELVIN_PADS):
            if ref not in fps or "Q3" not in fps:
                continue
            boxes = [p.GetBoundingBox() for p in fps[ref].Pads()]
            q3 = next((p.GetBoundingBox() for p in fps["Q3"].Pads() if p.GetNumber() == "3"), None)
            if q3 is None:
                continue
            x0 = min(mm(bb.GetLeft()) for bb in boxes) - 0.3
            y0 = min(mm(bb.GetTop()) for bb in boxes) - 0.3
            y1 = max(mm(bb.GetBottom()) for bb in boxes) + 0.3
            x1 = mm(q3.GetLeft()) - 0.02           # up to Q3's P- pin, not over it
            z = pcbnew.ZONE(b)
            z.SetLayer(pcbnew.B_Cu)
            z.SetIsRuleArea(True)
            z.SetDoNotAllowCopperPour(True)
            z.SetDoNotAllowTracks(False)
            z.SetDoNotAllowVias(False)
            z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False)
            ol = z.Outline()
            ol.NewOutline()
            for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            b.Add(z)

    def add_zones(self, b, gnd_layers=None):
        self.kelvin_keepout(b)
        for (net, lid, pads, prio) in LOCAL_ZONES:
            self.local_zone(b, net, lid, pads, prio=prio)
        gnd = self.nets["GND"]
        for lid in (gnd_layers or (pcbnew.In1_Cu, pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)):
            z = pcbnew.ZONE(b)
            z.SetLayer(lid)
            z.SetNetCode(gnd)
            z.SetAssignedPriority(0)
            z.SetLocalClearance(pcbnew.FromMM(GND_POUR_CLR))
            z.SetMinThickness(pcbnew.FromMM(GND_POUR_MIN))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            # solid connections: every GND pad reaches the In1 plane through
            # vias anyway, the outer pours add no heat sinking that matters
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
            ol = z.Outline()
            ol.NewOutline()
            for (x, y) in self.outline:
                ol.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
            b.Add(z)
        # v0.6: connectivity first - without it the first fill in a process differs from the
        # later ones (KiCad 7 island removal), and the written board would not be what the
        # router checked
        b.BuildConnectivity()
        filler = pcbnew.ZONE_FILLER(b)
        filler.Fill(b.Zones())


def apply_rules(b):
    """Design rules = JLCPCB 4-layer capabilities with margin."""
    ds = b.GetDesignSettings()
    ds.m_MinClearance = pcbnew.FromMM(0.10)          # JLCPCB multilayer: 0.09 mm
    ds.m_TrackMinWidth = pcbnew.FromMM(0.127)
    ds.m_ViasMinSize = pcbnew.FromMM(0.45)
    ds.m_ViasMinAnnularWidth = pcbnew.FromMM(0.1)
    ds.m_MinThroughDrill = pcbnew.FromMM(0.2)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.2)
    ds.m_HoleClearance = pcbnew.FromMM(0.2)
    ds.m_HoleToHoleMin = pcbnew.FromMM(0.2)
    ds.m_SolderMaskMinWidth = pcbnew.FromMM(0.1)
    ds.m_SolderMaskExpansion = pcbnew.FromMM(0.03)
    ds.m_SilkClearance = pcbnew.FromMM(0.0)
    po = b.GetPlotOptions()
    po.SetPlotViaOnMaskLayer(False)                   # tented vias (JLCPCB default)
    b.SetPlotOptions(po)
    nc = ds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(pcbnew.FromMM(0.10))
    nc.SetTrackWidth(pcbnew.FromMM(0.13))
    nc.SetViaDiameter(pcbnew.FromMM(0.45))
    nc.SetViaDrill(pcbnew.FromMM(0.2))


# v0.6: KiCad 7 resolves the netclass clearances of a board through the project settings it
# shares with the boards loaded after it; a board loaded before any apply_rules() keeps KiCad's
# default 0.2 mm, and its zone fills differ from every later one (the first pour fill of a run,
# or the written board).  Setting the rules once on a scratch board at import fixes the order.
apply_rules(pcbnew.BOARD())


def load_board(path):
    """pcbnew.LoadBoard with this project's rules in force for the loaded board: KiCad 7 resolves a
    board's netclass clearances from the current project's settings when it loads it, and saving
    or loading a board elsewhere can switch that project (default 0.2 mm clearance); zone fills
    of such a board differ from the DRC's.  The rules are set on a scratch board first."""
    apply_rules(pcbnew.BOARD())
    b = pcbnew.LoadBoard(path)
    apply_rules(b)
    return b


def drc(pcb_path, report):
    b = load_board(pcb_path)
    apply_rules(b)
    pcbnew.WriteDRCReport(b, report, pcbnew.EDA_UNITS_MILLIMETRES, True)
    return open(report).read()


def refill(src, out):
    """Fill the zones of a routed board again in a fresh process (KiCad 7 fills later boards of
    a long process differently; the written board must carry the fill the DRC expects)."""
    b = load_board(src)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(out)


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":      # same result on every run (see build_all.py)
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    if sys.argv[1] == "--clean":
        # python3 route.py --clean bare.kicad_pcb routed.kicad_pcb out.kicad_pcb
        r = Router(sys.argv[2])
        r.load_copper(sys.argv[3], log=print)
        r.pour_fill()
        r.remove_islands()
        r.prune()
        r.pour_fill()
        r.remove_stubs(r.signal_order())
        print("problems", r.problems(r.signal_order()), "audit", len(r.audit_clearance()))
        r.write(sys.argv[4], zones=True)
        sys.exit(0)
    if sys.argv[1] == "--refill":
        refill(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2])
        sys.exit(0)
    if sys.argv[1] == "--finish":
        # python3 route.py --finish unrouted.kicad_pcb routed.kicad_pcb out.kicad_pcb
        # (window repair of an earlier routing result, same placement)
        lg = lambda m: print("  route:", m, flush=True)
        r = Router(sys.argv[2])
        r.load_copper(sys.argv[3], log=lg, drop_conflicts=True)
        r.finalize(r.signal_order(), log=lg)
        r.write(sys.argv[4], zones=True)
        print("written", sys.argv[4], "failed nets:", r.incomplete(r.signal_order()), "GND off-plane:", r.gnd_fail)
        sys.exit(0)
    if sys.argv[1] == "--full":
        # python3 route.py --full unrouted.kicad_pcb out.kicad_pcb   (v0.7: negotiated route of the
        # bare main board, then the window repair, clean-up and exact clearance audit of finalize())
        lg = lambda m: print("  route:", m, flush=True)
        r = Router(sys.argv[2])
        r.run(log=lg)
        r.finalize(r.signal_order(), log=lg)
        r.write(sys.argv[3], zones=True)
        print("written", sys.argv[3], "failed nets:", r.incomplete(r.signal_order()), "GND off-plane:", r.gnd_fail)
        sys.exit(0)
    if sys.argv[1] == "--keys":
        # python3 route.py --keys unrouted.kicad_pcb out.kicad_pcb   (v0.7 key board: full run +
        # window repair, clean-up and exact clearance audit; run with FLASHKA_IN1="": In1 = plane)
        lg = lambda m: print("  route:", m, flush=True)
        r = Router(sys.argv[2])
        r.run(log=lg)
        r.finalize(r.signal_order(), log=lg)
        r.write(sys.argv[3], zones=True)
        print("written", sys.argv[3], "failed nets:", r.incomplete(r.signal_order()), "GND off-plane:", r.gnd_fail)
        sys.exit(0)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else src
    r = Router(src)
    failed = r.run()
    r.write(out, zones=True)
    print("written", out, "failed nets:", failed, "GND fanout failures:", r.gnd_fail)
