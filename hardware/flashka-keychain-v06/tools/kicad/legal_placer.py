#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Placement in the space of legal placements (FlashKa Keychain v0.6 main PCB).

The v0.6 board is ~85 % full: the light-pipe circle, the button row, the USB-C
shell legs and pegs and the front hold-down area leave a handful of free spots
for the small SOT parts and a set of 0402 "slots".  Annealing with an overlap
penalty and a greedy legaliser at the end (placer.py) scatters the parts at this
density.  This annealer never leaves the set of legal placements:

  * legality against everything that does not move (board outline, housing
    trough, keep-outs incl. the light-pipe circle and the top hold-down area,
    fixed parts, drilled holes, USB-C escape spots) is precomputed as a boolean
    mask per footprint, rotation and side on a 0.05 mm grid (same rules as
    gen_pcb.legalise: courtyard grown by 0.04 mm);
  * a move (shift, rotate, flip side, swap two parts) is accepted only if the
    mask allows it and the courtyard keeps 0.04 mm from every other movable part
    on that side - so the result needs no legaliser;
  * cost = sum over nets of weight x (rectilinear minimum spanning tree of the
    pads + 1.2 mm per side change) + decoupling / Kelvin affinities
    (placer.AFFINITY) + a congestion term (RUDY: net bounding-box wire density on
    a 1 mm grid, squared excess over a capacity map that is lower where vias are
    not allowed, over the USB-C body).

  python3 tools/kicad/legal_placer.py cad/housing_interface.json start.json out.json [seed] [iters]
"""
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_pcb  # noqa: E402
import placer  # noqa: E402
from autoplace import local_boxes  # noqa: E402
from flashka_parts import COMPONENTS  # noqa: E402

GRID = 0.025
GAP = 0.04 + 1e-4          # courtyard growth, as gen_pcb.legalise (gap / 2), plus rounding margin
VIA_PEN = 1.2              # mm-equivalent per net that needs both sides
NET_W = dict(placer.NET_W)
NET_W.update({"VBAT": 1.0, "3V3": 0.8, "GND": 0.0})
ROTS = (0, 90, 180, 270)
# routing channels kept free of parts (side, X0, Y0, X1, Y1), found with the router's rip-up
# statistics: the only F.Cu ways into the via-less area over the USB-C body (buck stage):
CHANNELS = [
    ("F", 9.0, -8.3, 19.4, 0.12),      # over the USB-C body (no vias there): only the hand-placed
                                       # buck stage and feedback divider (gen_pcb.FRONT_CLUSTER)
    ("F", 13.3, -1.0, 15.6, 0.1),      # above U2: escape of its EN and FB pins
    ("F", 18.0, -4.65, 19.65, -2.72),  # between the USB-C shell legs: VBAT into C7 / C5
    ("B", 11.05, 0.67, 12.92, 2.55),   # USB-C corner: left VBUS pin, CC2, ISNS vias, RS1 GND vias
    ("F", 19.4, 0.1, 19.62, 3.3),      # beside the hold-down area: room for the 3V3 via of LED3
    ("B", 18.2, 5.25, 19.0, 6.05),     # corner behind J5: GND via of the laser wire pad J5.2
]


def _boxes_overlap(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > 0 and min(a[3], b[3]) - max(a[1], b[1]) > 0


class LegalPlacer:
    def __init__(self, hj, comps, fixed, seed=1, affinity=None, side_lock=None, channels=None):
        self.hj, self.comps, self.fixed = hj, comps, fixed
        self.channels = CHANNELS if channels is None else channels
        self.rng = random.Random(seed)
        self.side_lock = side_lock if side_lock is not None else dict(gen_pcb.SIDE_LOCK)
        C = hj["components"]
        self.movable = [r for r in comps if r not in fixed]
        self.xs = np.arange(8.8, 32.8 + 1e-9, GRID)
        self.ys = np.arange(-8.25, 8.25 + 1e-9, GRID)
        # footprint data
        self.fpkey, self.crt, self.pads = {}, {}, {}
        fpcache = {}
        for r, c in comps.items():
            k = c["fp"]
            if k not in fpcache:
                fp = gen_pcb.load_fp(k)
                crt, _ = local_boxes(fp)
                pads = [(str(p.number), p.position.X, p.position.Y) for p in fp.pads if p.type != "np_thru_hole"]
                pnum = [str(p.number) for p in fp.pads if p.type != "np_thru_hole"]
                fpcache[k] = (crt, pads, gen_pcb.pad_boxes(fp), pnum)
            self.fpkey[r] = k
            self.crt[r] = fpcache[k][0]
            self.pads[r] = [p for p in fpcache[k][1] if p[0] in c["nets"]]
        self.fpcache = fpcache
        # static obstacles
        gen_pcb.legalise(hj, comps, {}, fixed)
        st = gen_pcb.legalise.state
        self.static = {"F": [b for _, b in st["placed"]["F"]], "B": [b for _, b in st["placed"]["B"]]}
        self.holes = [b for _, b in st["holes"]]
        self.usb_v, self.usb_u = gen_pcb.usb_escape_keepouts(fixed, comps)
        self.outline = [tuple(p) for p in hj["pcb_outline"]]
        self.trough = C["trough_y"]
        self.exc = C["trough_exceptions"]
        self.keep_b = [(k["x0"], k["y0"], k["x1"], k["y1"]) for k in C["keepout_bottom"]]
        self.keep_t = [(k["x0"], k["y0"], k["x1"], k["y1"]) for k in C.get("keepout_top", [])]
        self.circ = C.get("keepout_bottom_circles", [])
        self.masks = {}
        for k in fpcache:
            for rot in ROTS:
                for side in "FB":
                    self.masks[(k, rot, side)] = self._mask(k, rot, side)
        # nets
        self.nets = {}
        for r, c in comps.items():
            for pin, net in c["nets"].items():
                if NET_W.get(net, 1.0) > 0:
                    self.nets.setdefault(net, []).append((r, pin))
        self.part_nets = {r: sorted({n for n, ms in self.nets.items() if any(m[0] == r for m in ms)}) for r in comps}
        aff = affinity if affinity is not None else placer.AFFINITY
        self.aff = [a for a in aff if a[0] in comps and (a[2] in comps or a[2] == "@")]
        self.part_aff = {r: [i for i, a in enumerate(self.aff) if a[0] == r or a[2] == r] for r in comps}
        # congestion: capacity map (tracks per mm per layer pair available), 1 mm cells
        self.cx = np.arange(8.8, 32.8, 1.0)
        self.cy = np.arange(-8.25, 8.25, 1.0)
        cap = np.full((len(self.cy), len(self.cx)), 3.0)
        j1 = [b for r_, b in st["placed"]["B"] if r_ == "J1"][0]
        for jy, y in enumerate(self.cy):
            for ix, x in enumerate(self.cx):
                if j1[0] + 0.5 < x + 0.5 < j1[2] - 0.5 and j1[1] < y + 0.5 < j1[3] - 0.5:
                    cap[jy, ix] = 1.2           # no vias over the USB-C body, B.Cu blocked
        self.cap = cap
        self.rudy_w = 0.0
        self.free_cells = {}
        self.soft = False          # overlap phase: courtyard overlaps allowed, penalised by ov_w
        self.ov_w = 0.0
        self.ovc = 0.0
        # pad escape: pads of different nets closer than one track channel trap each other
        self.esc_w = 0.0
        self.esc_d = 0.36
        self.spads = {"F": [], "B": []}
        for r, (X, Y, rot, side) in fixed.items():
            for (b, net, sd) in self._pad_list(r, (X, Y, rot, side)):
                self.spads[sd].append((b, net))
        self.sarr = {}
        for sd in "FB":
            a = np.array([b for b, _ in self.spads[sd]]) if self.spads[sd] else np.zeros((0, 4))
            self.sarr[sd] = (a, [n for _, n in self.spads[sd]])

    def _pad_list(self, r, st):
        X, Y, rot, side = st
        key = self.fpkey[r]
        out = []
        two = self.comps[r]["fp"].endswith("TopBottom_1.6x1.8")
        for pb, num in zip(self.fpcache[key][2], self.fpcache[key][3]):
            b = gen_pcb.housing_box(pb, X, Y, rot, side)
            net = self.comps[r]["nets"].get(num)
            sd = side
            if two:
                sd = "F" if num == "1" else "B"
            out.append((b, net, sd))
        return out

    def _pair_pen(self, pa, pb):
        tot = 0.0
        D = self.esc_d
        for (a, na, sa) in pa:
            for (b, nb, sb) in pb:
                if sa != sb or (na is not None and na == nb):
                    continue
                dx = max(0.0, a[0] - b[2], b[0] - a[2])
                dy = max(0.0, a[1] - b[3], b[1] - a[3])
                if dx >= D or dy >= D:
                    continue
                d = math.hypot(dx, dy)
                if d < D:
                    tot += (D - d) ** 2
        return tot

    def _static_pen(self, pa):
        tot = 0.0
        D = self.esc_d
        for (a, na, sa) in pa:
            arr, nets = self.sarr[sa]
            if not len(arr):
                continue
            dx = np.maximum(0.0, np.maximum(a[0] - arr[:, 2], arr[:, 0] - a[2]))
            dy = np.maximum(0.0, np.maximum(a[1] - arr[:, 3], arr[:, 1] - a[3]))
            d = np.hypot(dx, dy)
            idx = np.nonzero(d < D)[0]
            for i in idx:
                if na is not None and nets[i] == na:
                    continue
                tot += (D - d[i]) ** 2
        return tot

    def esc_set(self, S):
        """escape penalty of the parts in S: against static pads, other movables, and within S"""
        if self.esc_w <= 0:
            return 0.0
        tot = 0.0
        S = list(S)
        for i, r in enumerate(S):
            pa = self.pl[r]
            tot += self._static_pen(pa)
            br = self.boxes[r]
            for q in self.movable:
                if q in S:
                    continue
                bq = self.boxes[q]
                if bq[0] > br[2] + 0.5 or bq[2] < br[0] - 0.5 or bq[1] > br[3] + 0.5 or bq[3] < br[1] - 0.5:
                    if not (self.two.get(q) or self.two.get(r)):
                        continue
                tot += self._pair_pen(pa, self.pl[q])
            for r2 in S[i + 1:]:
                tot += self._pair_pen(pa, self.pl[r2])
        return self.esc_w * tot

    # ------------------------------------------------------------- legality
    def _mask(self, key, rot, side):
        crt = self.fpcache[key][0]
        b = gen_pcb.housing_box(crt, 0.0, 0.0, rot, side)
        X, Y = np.meshgrid(self.xs, self.ys)
        x0, y0, x1, y1 = X + b[0] - GAP, Y + b[1] - GAP, X + b[2] + GAP, Y + b[3] + GAP
        ok = np.ones(X.shape, dtype=bool)
        poly = self.outline
        n = len(poly)

        def inside(px, py):
            c = np.zeros(px.shape, dtype=bool)
            for i in range(n):
                xa, ya = poly[i]
                xb, yb = poly[(i + 1) % n]
                cond = (ya > py) != (yb > py)
                with np.errstate(divide="ignore", invalid="ignore"):
                    xi = xa + (py - ya) * (xb - xa) / (yb - ya) if yb != ya else np.full(px.shape, 1e9)
                c ^= cond & (px < xi)
            return c
        for (px, py) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)):
            ok &= inside(px, py)
        e = gen_pcb.PAD_EDGE              # v0.6: pad copper to the board edge (as gen_pcb.legalise)
        for pb in self.fpcache[key][2]:
            hb = gen_pcb.housing_box(pb, 0.0, 0.0, rot, side)
            for (px, py) in ((X + hb[0] - e, Y + hb[1] - e), (X + hb[2] + e, Y + hb[1] - e),
                             (X + hb[0] - e, Y + hb[3] + e), (X + hb[2] + e, Y + hb[3] + e)):
                ok &= inside(px, py)

        def ov(bx):
            return (np.minimum(x1, bx[2]) - np.maximum(x0, bx[0]) > 0) & (np.minimum(y1, bx[3]) - np.maximum(y0, bx[1]) > 0)
        if side == "B":
            lo = np.full(X.shape, self.trough[0])
            hi = np.full(X.shape, self.trough[1])
            for e in self.exc:
                m = (x0 >= e["x0"] - 1e-6) & (x1 <= e["x1"] + 1e-6)
                if e["side"] == "-Y":
                    lo = np.where(m, -99.0, lo)
                else:
                    hi = np.where(m, 99.0, hi)
            ok &= (y0 >= lo) & (y1 <= hi)
            for k in self.keep_b:
                ok &= ~ov(k)
            for ci in self.circ:
                nx = np.clip(ci["x"], x0, x1)
                ny = np.clip(ci["y"], y0, y1)
                ok &= np.hypot(nx - ci["x"], ny - ci["y"]) >= ci["r"]
        else:
            for k in self.keep_t:
                ok &= ~ov(k)
        for o in self.static[side]:
            ok &= ~ov(o)
        for (sd, cx0, cy0, cx1, cy1) in self.channels:
            if sd == side:
                ok &= ~ov((cx0, cy0, cx1, cy1))
        for h in self.holes:
            ok &= ~ov(h)
        # USB-C escape spots against pad copper (raw pad boxes)
        for pb in self.fpcache[key][2]:
            hb = gen_pcb.housing_box(pb, 0.0, 0.0, rot, side)
            px0, py0, px1, py1 = X + hb[0], Y + hb[1], X + hb[2], Y + hb[3]
            for u in self.usb_v + (self.usb_u if side == "B" else []):
                ok &= ~((np.minimum(px1, u[2]) - np.maximum(px0, u[0]) > 0) &
                        (np.minimum(py1, u[3]) - np.maximum(py0, u[1]) > 0))
        return ok

    def idx(self, X, Y):
        return int(round((X - 8.8) / GRID)), int(round((Y + 8.25) / GRID))

    def legal_static(self, r, st):
        X, Y, rot, side = st
        if r in self.side_lock and side != self.side_lock[r]:
            return False
        i, j = self.idx(X, Y)
        if not (0 <= i < len(self.xs) and 0 <= j < len(self.ys)):
            return False
        return bool(self.masks[(self.fpkey[r], rot, side)][j, i])

    def box(self, r, st):
        X, Y, rot, side = st
        return gen_pcb.housing_box(self.crt[r], X, Y, rot, side)

    def _ov_area(self, a, b):
        dx = min(a[2], b[2]) - max(a[0], b[0]) + 2 * GAP
        dy = min(a[3], b[3]) - max(a[1], b[1]) + 2 * GAP
        return dx * dy if dx > 0 and dy > 0 else 0.0

    def ov_set(self, S):
        tot = 0.0
        S = list(S)
        for i, r in enumerate(S):
            sd = self.state[r][3]
            for q in self.movable:
                if q in S or self.state[q][3] != sd:
                    continue
                tot += self._ov_area(self.boxes[r], self.boxes[q])
            for q in S[i + 1:]:
                if self.state[q][3] == sd:
                    tot += self._ov_area(self.boxes[r], self.boxes[q])
        return tot

    def all_legal(self):
        return all(self.legal_dynamic(r, self.state[r], self.movable) for r in self.movable)

    def ov_total(self):
        tot = 0.0
        for i, r in enumerate(self.movable):
            for q in self.movable[i + 1:]:
                if self.state[q][3] == self.state[r][3]:
                    tot += self._ov_area(self.boxes[r], self.boxes[q])
        return tot

    def legal_dynamic(self, r, st, others):
        b = self.box(r, st)
        g = (b[0] - GAP, b[1] - GAP, b[2] + GAP, b[3] + GAP)
        for r2 in others:
            if r2 == r:
                continue
            s2 = self.state[r2]
            if s2[3] != st[3]:
                continue
            if _boxes_overlap(g, self.boxes[r2]):
                return False
        return True

    # ------------------------------------------------------------- cost
    def pad_xy(self, r, pin, st):
        X, Y, rot, side = st
        for (num, px, py) in self.pads[r]:
            if num == pin:
                x, y = gen_pcb.xform_pt(px, py, rot, side == "B")
                return X + x, Y - y
        return X, Y

    def where(self, r):
        return self.state[r] if r in self.state else self.fixed[r]

    def net_pts(self, net):
        pts, sides = [], set()
        for (r, pin) in self.nets[net]:
            st = self.where(r)
            pts.append(self.pad_xy(r, pin, st))
            if not self.comps[r]["fp"].endswith("TopBottom_1.6x1.8"):
                sides.add(st[3])
        return pts, sides

    def net_cost(self, net):
        pts, sides = self.net_pts(net)
        n = len(pts)
        if n < 2:
            return 0.0, None
        # rectilinear MST (Prim)
        d = [1e9] * n
        used = [False] * n
        d[0] = 0.0
        tot = 0.0
        for _ in range(n):
            u = -1
            best = 1e18
            for i in range(n):
                if not used[i] and d[i] < best:
                    best, u = d[i], i
            used[u] = True
            tot += best
            ux, uy = pts[u]
            for v in range(n):
                if not used[v]:
                    dv = abs(ux - pts[v][0]) + abs(uy - pts[v][1])
                    if dv < d[v]:
                        d[v] = dv
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bb = (min(xs), min(ys), max(xs), max(ys))
        return NET_W.get(net, 1.0) * (tot + (VIA_PEN if len(sides) > 1 else 0.0)), (bb, tot)

    def aff_cost(self, i):
        a, pa, b, pb, w = self.aff[i]
        x1, y1 = self.pad_xy(a, pa, self.where(a))
        if b == "@":
            return w * math.hypot(x1 - pb[0], y1 - pb[1])
        x2, y2 = self.pad_xy(b, pb, self.where(b))
        side_pen = 2.0 if self.where(a)[3] != self.where(b)[3] else 0.0
        return w * (math.hypot(x1 - x2, y1 - y2) + side_pen)

    def rudy_add(self, info, sgn):
        if info is None or self.rudy_w <= 0:
            return
        (x0, y0, x1, y1), L = info
        w = max(x1 - x0, 0.5)
        h = max(y1 - y0, 0.5)
        dens = L / (w * h)
        i0 = max(int(math.floor(x0 - 8.8)), 0)
        i1 = min(int(math.floor(x1 - 8.8)), len(self.cx) - 1)
        j0 = max(int(math.floor(y0 + 8.25)), 0)
        j1 = min(int(math.floor(y1 + 8.25)), len(self.cy) - 1)
        self.rudy[j0:j1 + 1, i0:i1 + 1] += sgn * dens

    def rudy_cost(self):
        if self.rudy_w <= 0:
            return 0.0
        ex = np.maximum(self.rudy - self.cap, 0.0)
        return self.rudy_w * float((ex * ex).sum())

    def esc_total(self):
        tot = 0.0
        for i, r in enumerate(self.movable):
            tot += self._static_pen(self.pl[r])
            for q in self.movable[i + 1:]:
                tot += self._pair_pen(self.pl[r], self.pl[q])
        return self.esc_w * tot

    def total(self):
        return sum(self.netc.values()) + sum(self.affc) + self.rudy_cost() + self.escc

    # ------------------------------------------------------------- anneal
    def init(self, start):
        self.state = {}
        for r in self.movable:
            self.state[r] = tuple(start[r])
        self.boxes = {r: self.box(r, self.state[r]) for r in self.movable}
        # start spots that are not legal (off-grid, or overlapping): nearest legal spot,
        # placed parts first (largest parts first)
        ok = [r for r in self.movable if self.legal_static(r, self.state[r])]
        bad = [r for r in self.movable if r not in ok]
        good = []
        for r in sorted(ok, key=lambda q: -self._area(q)):
            if self.legal_dynamic(r, self.state[r], good):
                good.append(r)
            else:
                bad.append(r)
        stuck = []
        for r in sorted(bad, key=lambda q: -self._area(q)):
            st = self._nearest(r, self.state[r], good)
            if st is None:
                stuck.append(r)
                continue
            self.state[r] = st
            self.boxes[r] = self.box(r, st)
            good.append(r)
        for r in stuck:            # no free spot: nearest statically legal spot, overlap allowed
            st = self._nearest(r, self.state[r], [])
            if st is None:
                raise ValueError(f"no legal spot for {r}")
            self.state[r], self.boxes[r] = st, self.box(r, st)
        self.stuck = stuck
        self.two = {r: self.comps[r]["fp"].endswith("TopBottom_1.6x1.8") for r in self.comps}
        self.pl = {r: self._pad_list(r, self.state[r]) for r in self.movable}
        self.escc = self.esc_total() if self.esc_w > 0 else 0.0
        self.rudy = np.zeros(self.cap.shape)
        self.netc, self.neti = {}, {}
        for n in self.nets:
            c, info = self.net_cost(n)
            self.netc[n], self.neti[n] = c, info
            self.rudy_add(info, +1)
        self.affc = [self.aff_cost(i) for i in range(len(self.aff))]

    def _area(self, r):
        b = self.crt[r]
        return (b[2] - b[0]) * (b[3] - b[1])

    def _nearest(self, r, st, others, rmax=12.0):
        X, Y, rot, side = st
        sides = [side] if r in self.side_lock else [side, "B" if side == "F" else "F"]
        for sd in sides:
            rr = 0.0
            while rr <= rmax:
                n = max(1, int(2 * math.pi * rr / GRID))
                for k in range(n):
                    a = 2 * math.pi * k / n
                    x = round((X + rr * math.cos(a)) / GRID) * GRID
                    y = round((Y + rr * math.sin(a)) / GRID) * GRID
                    for q in [rot] + [q for q in ROTS if q != rot]:
                        cand = (round(x, 3), round(y, 3), q, sd)
                        if self.legal_static(r, cand):
                            self.state[r], self.boxes[r] = cand, self.box(r, cand)
                            if self.legal_dynamic(r, cand, others):
                                return cand
                rr += GRID
        return None

    def _try(self, changes, T):
        """changes: {ref: new_state}; returns True if accepted."""
        old = {r: self.state[r] for r in changes}
        oldb = {r: self.boxes[r] for r in changes}
        for r, st in changes.items():
            if not self.legal_static(r, st):
                return False
        e0 = self.esc_set(changes) if self.esc_w > 0 else 0.0
        oldpl = {r: self.pl[r] for r in changes}
        o0 = self.ov_set(changes) if self.soft else 0.0
        for r, st in changes.items():
            self.state[r] = st
            self.boxes[r] = self.box(r, st)
        for r, st in changes.items():
            if not self.soft and not self.legal_dynamic(r, st, self.movable):
                for r2 in changes:
                    self.state[r2], self.boxes[r2] = old[r2], oldb[r2]
                return False
        if self.esc_w > 0:
            for r, st in changes.items():
                self.pl[r] = self._pad_list(r, st)
            de = self.esc_set(changes) - e0
        else:
            de = 0.0
        nets = set()
        affs = set()
        for r in changes:
            nets.update(self.part_nets[r])
            affs.update(self.part_aff[r])
        c0 = self.rudy_cost()
        newn = {}
        for n in nets:
            self.rudy_add(self.neti[n], -1)
            newn[n] = self.net_cost(n)
            self.rudy_add(newn[n][1], +1)
        newa = {i: self.aff_cost(i) for i in affs}
        d = sum(newn[n][0] - self.netc[n] for n in nets) + sum(newa[i] - self.affc[i] for i in affs) + \
            self.rudy_cost() - c0 + de
        if self.soft:
            dov = self.ov_set(changes) - o0
            d += self.ov_w * dov
        if d <= 0 or (T > 0 and self.rng.random() < math.exp(-d / T)):
            for n in nets:
                self.netc[n], self.neti[n] = newn[n]
            for i, v in newa.items():
                self.affc[i] = v
            self.escc += de
            if self.soft:
                self.ovc += dov
            return True
        for n in nets:
            self.rudy_add(newn[n][1], -1)
            self.rudy_add(self.neti[n], +1)
        for r2 in changes:
            self.state[r2], self.boxes[r2] = old[r2], oldb[r2]
            self.pl[r2] = oldpl[r2]
        return False

    def run(self, iters=400000, t0=2.0, t1=0.005, s0=4.0, s1=0.15, log=None, ov=None):
        acc = 0
        for it in range(iters):
            f = it / iters
            T = t0 * (t1 / t0) ** f
            sig = s0 * (s1 / s0) ** f
            if ov is not None:
                self.ov_w = ov[0] * (ov[1] / ov[0]) ** f
                if it % 20000 == 0:
                    self.ovc = self.ov_total()
                    if f > 0.2 and self.all_legal():
                        break
            r = self.rng.choice(self.movable)
            X, Y, rot, side = self.state[r]
            mv = self.rng.random()
            if mv < 0.06:
                # jump: any free legal spot on the board (dense board: local moves rarely fit)
                sd = side if r in self.side_lock else self.rng.choice("FB")
                q = self.rng.choice(ROTS)
                m = self.masks[(self.fpkey[r], q, sd)]
                jj, ii = self.free_cells.get((self.fpkey[r], q, sd), (None, None))
                if jj is None:
                    jj, ii = np.nonzero(m)
                    self.free_cells[(self.fpkey[r], q, sd)] = (jj, ii)
                if not len(jj):
                    continue
                k = self.rng.randrange(len(jj))
                ch = {r: (round(8.8 + ii[k] * GRID, 3), round(-8.25 + jj[k] * GRID, 3), q, sd)}
            elif mv < 0.55:
                nx = round((X + self.rng.gauss(0, sig)) / GRID) * GRID
                ny = round((Y + self.rng.gauss(0, sig)) / GRID) * GRID
                ch = {r: (round(nx, 3), round(ny, 3), rot, side)}
            elif mv < 0.70:
                ch = {r: (X, Y, self.rng.choice([q for q in ROTS if q != rot]), side)}
            elif mv < 0.78:
                if r in self.side_lock:
                    continue
                nx = round((X + self.rng.gauss(0, sig)) / GRID) * GRID
                ny = round((Y + self.rng.gauss(0, sig)) / GRID) * GRID
                ch = {r: (round(nx, 3), round(ny, 3), self.rng.choice(ROTS), "B" if side == "F" else "F")}
            else:
                o = self.rng.choice(self.movable)
                if o == r:
                    continue
                so = self.state[o]
                if self.rng.random() < 0.5:
                    ch = {r: (so[0], so[1], so[2], so[3]), o: (X, Y, rot, side)}
                else:
                    ch = {r: (so[0], so[1], rot, so[3]), o: (X, Y, so[2], side)}
            if self._try(ch, T):
                acc += 1
            if log and it % 100000 == 0:
                log(f"it {it} T {T:.3f} sig {sig:.2f} cost {self.total():.1f} ov {self.ovc:.3f} "
                    f"(nets {sum(self.netc.values()):.1f}, aff {sum(self.affc):.1f}, rudy {self.rudy_cost():.1f}, "
                    f"esc {self.escc:.1f}) acc {acc}")
                acc = 0
        return self.state

    def report(self):
        tot = {}
        for n, (c, info) in ((n, (self.netc[n], self.neti[n])) for n in self.nets):
            tot[n] = info[1] if info else 0.0
        return tot


def place(hj_path, start, seed=1, iters=400000, t0=2.0, rudy_w=0.0, log=print, passes=1, esc_w=0.0):
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = gen_pcb.fixed_parts(hj)
    lp = LegalPlacer(hj, comps, fixed, seed=seed)
    lp.rudy_w = rudy_w
    lp.esc_w = esc_w
    lp.init({r: v for r, v in start.items() if r not in fixed})
    if lp.stuck:
        log(f"overlap phase for {lp.stuck}")
        lp.soft = True
        lp.ovc = lp.ov_total()
        for k in range(8):
            lp.run(iters=iters // 2, t0=t0 if k == 0 else 0.3, t1=0.02, s0=3.0, s1=0.2, log=log,
                   ov=(20.0 * (k + 1), 1e5))
            lp.ovc = lp.ov_total()
            if lp.all_legal():
                break
        if not lp.all_legal():
            raise ValueError(f"overlaps remain: {lp.ovc:.4f}")
        lp.soft = False
    for p in range(passes):
        lp.run(iters=iters, t0=t0 if p == 0 else t0 * 0.3, log=log)
    lp.run(iters=iters // 4, t0=0.05, t1=0.001, s0=0.5, s1=0.05, log=log)
    return lp


if __name__ == "__main__":
    extra = os.environ.get("FLASHKA_LP_CHANNELS", "")
    for c in filter(None, extra.split(";")):
        f = c.split(",")
        CHANNELS.append((f[0], *map(float, f[1:])))
    hj = sys.argv[1]
    d = json.load(open(sys.argv[2]))
    d = d.get("placement", d)
    out = sys.argv[3]
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    iters = int(sys.argv[5]) if len(sys.argv) > 5 else 400000
    t0 = float(os.environ.get("FLASHKA_LP_T0", "2.0"))
    rw = float(os.environ.get("FLASHKA_LP_RUDY", "0.0"))
    ew = float(os.environ.get("FLASHKA_LP_ESC", "0.0"))
    lp = place(hj, {r: tuple(v) for r, v in d.items()}, seed=seed, iters=iters, t0=t0, rudy_w=rw, esc_w=ew)
    wl = lp.report()
    res = {"seed": seed, "iters": iters, "t0": t0, "rudy_w": rw, "esc_w": ew, "esc": round(lp.escc, 1), "mst_mm": round(sum(wl.values()), 1),
           "cost": round(lp.total(), 1), "placement": {r: list(v) for r, v in lp.state.items()}}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print("MST %.1f mm, cost %.1f" % (sum(wl.values()), lp.total()))
