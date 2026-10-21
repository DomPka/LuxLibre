#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Grid router for the Aurora++ v0.5 main PCB (4 layers).

  python3 tools/kicad/route.py kicad/Aurora_main/Aurora_main.kicad_pcb

Layers: F.Cu, In2.Cu and B.Cu carry tracks; In1.Cu is a solid GND plane that
every GND pad reaches through a short stub and a via ("fanout").  Each net is
routed as a tree: A* from the copper already connected to the nearest pad not
yet connected, on a 0.05 mm grid, with clearances taken from exact distance
fields (scipy EDT) of all foreign copper.  Wide nets (power) neck down to
0.2 mm only next to fine-pitch pads.  Nets that fail trigger rip-up and
reroute of the nets that block them.  Afterwards GND pours are added on every
layer, zones are filled and KiCad's own DRC checks the result.
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
CLR = float(os.environ.get("AURORA_CLR", "0.115"))  # target copper clearance (JLCPCB multilayer min 0.09; DRC rule 0.10)
EDGE = 0.25              # copper to board edge (JLCPCB: 0.2)
MARGIN = 0.04            # raster error allowance for routed copper (on-grid tracks: <= 0.035)
PAD_EPS = 0.012          # pads use exact distance fields; allowance for diagonal track midpoints
VIA_D, VIA_DRILL = 0.45, 0.20      # JLCPCB: no surcharge for 0.2 mm holes with >= 0.45 mm pads
NPTH_CLR = 0.20          # JLCPCB: NPTH hole edge to copper 0.2 mm
PADHOLE_GAP = 0.45       # JLCPCB: pad hole to hole 0.45 mm (via drill to NPTH / PTH drill)
VIA_GAP = 0.20           # JLCPCB: via to via, hole edge to hole edge 0.2 mm
VIA_PITCH = VIA_DRILL + VIA_GAP + 0.03   # minimum via centre distance, any nets
EP_VIAS = {"U4": ("49", (-0.9875, 0.9875))}   # web centre lines between the 3 x 3 paste apertures
GND_POUR_CLR = float(os.environ.get("AURORA_POUR_CLR", "0.15"))  # GND pour clearance to other nets
GND_POUR_MIN = float(os.environ.get("AURORA_POUR_MIN", "0.15"))  # GND pour minimum width
VIA_COST = 10            # in grid steps (0.5 mm)
HIST_INC = 0.6           # congestion history added per conflict
PFAC_MAX = 250.0
LAYER_IDS = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
ROUTE = [0, 2, 3]
LAYER_COST = {0: 1.0, 2: 1.0, 3: 1.0}
WIDTH = {"VOUT": 0.5, "SW": 0.5, "ISNS": 0.5, "VBAT": 0.4, "VBUS": 0.25, "3V3": 0.25,
         "LASER_P": 0.2, "GND": 0.25}
# high-current branches: full width only between these parts' pads, the
# low-current branches of the same net (dividers, op-amp input, LDO, charger) get LOW_W
POWER_REFS = {"VBAT": {"J2", "U2", "C5"}, "VOUT": {"L1", "C8", "J3"}, "ISNS": {"J3", "RS1"}}
LOW_W = {"VBAT": 0.25, "VOUT": 0.2, "ISNS": 0.2}
SIGNAL_W = 0.13
NECK_W = 0.2
NECK_R = 0.7             # neck-down allowed this close to the pads being joined
POWER_ORDER = ["SW", "VOUT", "ISNS", "VBAT", "VBUS", "3V3", "LASER_P"]
FREEZE = ["SW", "VOUT", "ISNS"]   # once routed, these keep their copper
FREEZE_ALL_AFTER = 10
POWER_GND = ["U2", "C5", "C8", "RS1", "J2"]   # GND pads with their own via, placed first (high current)
# local pours (net, layer, [(ref, pad), ...]) - buck power stage and sense path
LOCAL_ZONES = [
    ("SW", pcbnew.F_Cu, [("U2", "2"), ("L1", "1")], 5),
    ("VOUT", pcbnew.F_Cu, [("L1", "2"), ("C8", "1")], 4),
    ("VBAT", pcbnew.F_Cu, [("U2", "3"), ("C5", "1")], 4),
    ("GND", pcbnew.F_Cu, [("U2", "1"), ("C5", "2"), ("C8", "2")], 2),
]


def mm(v):
    return pcbnew.ToMM(v)


class Router:
    def __init__(self, path):
        self.path = path
        self.board = pcbnew.LoadBoard(path)
        bb = self.board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = mm(bb.GetX()) - 0.2, mm(bb.GetY()) - 0.2
        self.nx = int(math.ceil((mm(bb.GetWidth()) + 0.4) / G))
        self.ny = int(math.ceil((mm(bb.GetHeight()) + 0.4) / G))
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
        self.pour = None        # filled GND pour outline ids per layer (KiCad fill, see pour_fill)
        self.pour_area, self.pour_merge = {}, []
        self.pad_polys = []     # (layer, polygon, netcode or -1) of every copper pad
        self.pads = {}          # netcode -> list of pad dicts
        self._outline()
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
        KEEP = {"J1": (3, 0.55), "S1": (3, 0.5), "S2": (0, 0.5), "L1": (0, 0.35)}
        self.keep = np.zeros((4, self.ny, self.nx), dtype=bool)
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
        # the D+/D- escape behind the USB-C pads stays allowed (pre-routed)

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
    def fields(self, code, w):
        """Hard legality (pads, holes, edge, frozen copper) and soft conflicts
        (other nets' tracks) for a net of width w; returns dicts per routing
        layer.  Pads: exact distances; routed copper: raster EDT + MARGIN."""
        need_p, need_pn = w / 2 + CLR + PAD_EPS, NECK_W / 2 + CLR + PAD_EPS
        need, need_n = w / 2 + CLR + MARGIN, NECK_W / 2 + CLR + MARGIN
        edge_ok = (self.d_edge >= w / 2 + EDGE + MARGIN) & (self.D_npth >= w / 2 + NPTH_CLR + 0.01)
        edge_ok_n = (self.d_edge >= NECK_W / 2 + EDGE + MARGIN) & (self.D_npth >= NECK_W / 2 + NPTH_CLR + 0.01)
        hard, hard_n, conf, conf_n = {}, {}, {}, {}
        rv, rvp = VIA_D / 2 + CLR + MARGIN, VIA_D / 2 + CLR + PAD_EPS
        via_hard = self.d_edge >= VIA_D / 2 + EDGE + MARGIN
        via_hard &= self.D_padhole >= VIA_DRILL / 2 + PADHOLE_GAP + 0.01
        via_hard &= ~self.via_block()
        via_conf = np.zeros((self.ny, self.nx), dtype=bool)
        frozen = self.frozen_mask(code)
        big = np.full((self.ny, self.nx), 99.0)
        for k in range(4):
            Dp = self.pad_dist(k, code)
            ft = (self.trk[k] != 0) & (self.trk[k] != code) & ~frozen[k]
            Df = (ndimage.distance_transform_edt(~frozen[k]) * G - 0.01) if frozen[k].any() else big
            Dt = ndimage.distance_transform_edt(~ft) * G if ft.any() else big
            via_hard &= (Dp >= rvp) & (Df >= rv)
            via_conf |= Dt < rv
            via_hard &= ~self.keep[k]
            if k in ROUTE:
                hard[k] = (Dp >= need_p) & (Df >= need) & edge_ok & ~self.keep[k]
                hard_n[k] = (Dp >= need_pn) & (Df >= need_n) & edge_ok_n & ~self.keep[k]
                conf[k] = Dt < need
                conf_n[k] = Dt < need_n
        via_hard &= self.smd_far
        return hard, hard_n, conf, conf_n, via_hard, via_conf

    def frozen_mask(self, code):
        """Routed copper of frozen nets and locked connections (not rippable)
        acts like pads for every other net."""
        m = np.zeros(self.trk.shape, dtype=bool)
        if self.frozen:
            m |= np.isin(self.trk, [c for c in self.frozen if c != code])
        if self.locked:
            m |= np.isin(self.cid, list(self.locked)) & (self.trk != code)
        return m

    def all_vias(self):
        """(x, y, netcode) of every committed via."""
        return [(d[0], d[1], n) for (n, items) in self.conns.values() for (kind, d) in items if kind == "via"]

    def via_block(self):
        """Cells whose centre is closer than VIA_PITCH to a committed via
        (hole-to-hole spacing applies to all vias, same net included)."""
        tmp = np.zeros((1, self.ny, self.nx), dtype=np.int8)
        for (x, y, _n) in self.all_vias():
            self._mark_circle([0], x, y, VIA_PITCH - 1e-6, 1, tmp)
        return tmp[0] != 0

    def preroute(self, name, items):
        """Add hand-made copper for a net (locked)."""
        code = self.nets[name]
        cid = self.next_cid
        self.next_cid += 1
        self.conns[cid] = (code, items)
        for (k, j, i) in self.raster_items(items, code, self.trk):
            self.cid[k, j, i] = cid
        self.locked.add(cid)
        return cid

    def pad_xy(self, ref, num):
        for ps in self.pads.values():
            for p in ps:
                if p["ref"] == ref and p["num"] == num:
                    return p["x"], p["y"]
        raise KeyError((ref, num))

    def preroute_usb(self):
        """USB-C D+/D- escape (pads interleaved B6 A7 A6 B7): D+ joins A6-B6 with
        a U behind A7 on B.Cu; D- drops A7 and B7 to vias and joins them on In2."""
        from gen_pcb import USB_PAD_HALF, USB_U_BACK, USB_VIA_BACK
        ya = self.pad_xy("J1", "A6")[1]
        y_end = ya - USB_PAD_HALF             # inner pad end (towards the board centre)
        xa6, xb6 = self.pad_xy("J1", "A6")[0], self.pad_xy("J1", "B6")[0]
        xa7, xb7 = self.pad_xy("J1", "A7")[0], self.pad_xy("J1", "B7")[0]
        yu, yv = y_end - USB_U_BACK, y_end - USB_VIA_BACK
        # the placement keeps these spots free (gen_pcb.usb_escape_keepouts);
        # verify against the exact pad fields anyway
        for (x, y) in ((xa7, yv), (xb7, yv)):
            i, j = self.ij(x, y)
            for k in range(4):
                d = min(self.pad_dist(k, self.nets["USB_DN"])[j, i], 99.0)
                if d < VIA_D / 2 + CLR:
                    raise RuntimeError(f"USB D- via at ({x:.2f}, {y:.2f}) is {d:.3f} mm from a pad on layer {k}")
        w = SIGNAL_W
        dp = [("seg", (3, xa6, ya, xa6, yu, w)), ("seg", (3, xa6, yu, xb6, yu, w)),
              ("seg", (3, xb6, yu, xb6, ya, w))]
        dn = [("seg", (3, xa7, ya, xa7, yv, w)), ("via", (xa7, yv)),
              ("seg", (3, xb7, ya, xb7, yv, w)), ("via", (xb7, yv)),
              ("seg", (2, xa7, yv, xb7, yv, w))]
        self.preroute("USB_DP", dp)
        self.preroute("USB_DN", dn)

    def preroute_ep(self, n_max=4):
        """Thermal vias in the exposed GND pad of the module: on the centre
        lines of the solder-mask webs between the paste apertures, clear of
        copper on every layer (parts on the bottom side under the module),
        spread out (farthest-point choice)."""
        code = self.nets["GND"]
        foreign = (self.owner != 0) & (self.owner != code)
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
                        if self.keep[:, j, i].any() or not self._via_hole_ok(x, y):
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
              via_target=False, pfac=4.0, hard_tracks=False, max_expand=900000):
        hard, hard_n, conf, conf_n, via_hard, via_conf = self.fields(code, w)
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
    def geometry(self, code, path, w, end_via=False):
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
        hard = None
        if w > NECK_W:
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

    def rip_conn(self, c):
        code, items = self.conns.pop(c)
        m = self.cid == c
        self.trk[m] = 0
        self.cid[m] = 0

    def rip(self, code):
        for c in [c for c, (n, _) in self.conns.items() if n == code]:
            self.rip_conn(c)

    @property
    def items(self):
        out = {}
        for c, (n, it) in self.conns.items():
            out.setdefault(n, []).extend(it)
        return out

    def components(self, code):
        """Connected groups of this net's pads through its routed copper."""
        st8 = np.ones((3, 3), dtype=bool)
        cop = (self.owner == code) | (self.trk == code)
        labs, off = [], 0
        for k in range(4):
            lab, n = ndimage.label(cop[k], structure=st8)
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
        groups = {}
        for p in self.pads.get(code, []):
            k, j, i = p["cells"][0]
            groups.setdefault(find(int(labs[k][j, i])), []).append(p)
        roots = {}
        for root in groups:
            roots[root] = root
        # all cells per group (pads + copper) for use as search targets
        cellsets = {}
        for root, ps in groups.items():
            cs = set()
            for k in range(4):
                lab = labs[k]
                m = np.zeros(lab.shape, dtype=bool)
                ids = [l for l in np.unique(lab[lab > 0]).tolist() if find(l) == root]
                if ids:
                    m = np.isin(lab, ids)
                jj, ii = np.nonzero(m)
                cs.update(zip([k] * len(jj), jj.tolist(), ii.tolist()))
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
            pw = [g for g in range(len(groups)) if prefs and any(p["ref"] in prefs for p in groups[g])]
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
            for ww in [w] + [x for x in (0.3, NECK_W, SIGNAL_W) if x < w]:
                for padw in (2.5, 6.0, None):
                    win = self.window_for(list(tree), list(tgt), padw) if padw else None
                    path = self.astar(code, ww, tree, tgt, window=win, neck_cells=neck, pfac=pfac)
                    if path:
                        break
                if path:
                    used_w = ww
                    break
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
            items = self.geometry(code, path, used_w)
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

    gnd_first = False       # True: GND stubs before the signal nets
    gnd_start = 25          # otherwise GND joins the negotiation when signals are done (or at this iteration)
    gnd_iters = 0           # negotiated GND iterations before the monotonic repair
    allow_relax = True      # route_net may unfreeze everything once when blocked (off in repair)
    frozen = set()
    locked = set()

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
        n_ep = self.preroute_ep()
        log(f"pre-routes: USB D+/D-, {n_ep} thermal vias in the module pad")
        self.gnd_cid = {}
        self._set_pour_state(None)
        pk = {self._gkey(p) for p in self._gnd_pads() if p["ref"] in POWER_GND}
        fails, _ = self.fanout_gnd(pfac=6.0, only=pk, force=True, lock=True)
        log(f"power-stage GND vias: {len(pk) - len(fails)} of {len(pk)}")
        gnd_on = self.gnd_first
        if gnd_on:
            fails, _ = self.fanout_gnd(pfac=6.0)
            log(f"GND fanout: {len(fails)} failed, {time.time() - t0:.0f}s")
        queue = list(order)
        pfac = 6.0
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
                self.route_net(nm, pfac)
            gnd_fail = []
            if gnd_on:
                self.pour_fill()
                miss = self.gnd_missing()
                if miss:
                    gnd_fail, _ = self.fanout_gnd(pfac=pfac, only=miss)
            incomplete = [n for n in order if len(self.components(self.nets[n])[0]) > 1]
            queue = incomplete
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
        if not self.gnd_first:
            self.repair(order, log=log)
            if self.incomplete(order) or self.gnd_missing():
                self.deep_repair(order, log=log)
            queue = self.incomplete(order)
        self.failed = queue
        self.gnd_fail = sorted(f"{k[0]}.{k[1]}" for k in self.gnd_missing())
        log(f"done: incomplete {queue}, GND pads off-plane {self.gnd_fail}, {time.time() - t0:.0f}s")
        return queue

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
        return [n for n in names if len(self.components(self.nets[n])[0]) > 1]

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

    # ------------------------------------------------------------- finishing
    def finish(self, log=print):
        """After routing: remove dangling copper, parallel vias on the
        high-current nets, then re-check GND plane connectivity with the real
        pour fill (extra vias can cut pours) and patch it without ripping."""
        self.prune(log=log)
        added = self.augment_vias(["VBAT", "VOUT", "ISNS", "SW", "VBUS"], n_extra=2)
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
        for (k, j, i) in cells:
            if self.keep[k, j, i] or self.d_edge[j, i] < EDGE + MARGIN or self.D_npth[j, i] < NPTH_CLR + 0.04:
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
        def rebuild(table):
            self.trk[:] = 0
            self.cid[:] = 0
            self.conns, self.locked = {}, set()
            for n, items in table.items():
                cid = self.next_cid
                self.next_cid += 1
                self.conns[cid] = (n, items)
                for (k, j, i) in self.raster_items(items, n, self.trk):
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
        b = pcbnew.LoadBoard(self.path)
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
        b = self._build_board(True, gnd_layers=lids)
        gnd = self.nets["GND"]
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

    def add_zones(self, b, gnd_layers=None):
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


def drc(pcb_path, report):
    b = pcbnew.LoadBoard(pcb_path)
    apply_rules(b)
    pcbnew.WriteDRCReport(b, report, pcbnew.EDA_UNITS_MILLIMETRES, True)
    return open(report).read()


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else src
    r = Router(src)
    failed = r.run()
    r.write(out)
    print("written", out, "failed nets:", failed, "GND fanout failures:", r.gnd_fail)
