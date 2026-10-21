#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Simulated-annealing placement for the FlashKa Keychain v0.6 main PCB.

State: every movable part has (X, Y, rot, side) in housing coordinates.
Hard rules (moves that break them are rejected): courtyard inside the board
outline, bottom parts inside the housing trough (except the ledge-free zones),
no part in the laser keep-out, no part on a hole, part-specific side locks.
Soft cost: weighted half-perimeter wire length of every net (GND excluded -
it is a plane), distance terms that pull decoupling capacitors to their IC
pins, and an overlap penalty whose weight rises during the anneal. The result
is cleaned by the greedy legaliser of gen_pcb.py and cached in a JSON file.
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_pcb  # noqa: E402
from autoplace import local_boxes  # noqa: E402
from flashka_parts import COMPONENTS  # noqa: E402

SIDE_LOCK = gen_pcb.SIDE_LOCK
NET_W = {"GND": 0.0, "VBAT": 1.5, "VOUT": 3.0, "SW": 4.0, "ISNS": 3.0, "3V3": 1.0,
         "VBUS": 1.5, "FB": 2.0, "INV": 2.0, "VC": 1.5, "QG": 1.5, "QS": 1.5,
         "USB_DP": 1.5, "USB_DN": 1.5}
# (part, pad, part, pad, weight): keep these pads close (decoupling, Kelvin)
AFFINITY = [
    ("C5", "1", "U2", "3", 25.0), ("C5", "2", "U2", "1", 25.0), ("C7", "1", "U2", "3", 8.0),
    ("C8", "1", "L1", "2", 12.0), ("C8", "2", "U2", "1", 6.0), ("L1", "1", "U2", "2", 12.0), ("C9", "2", "U2", "5", 2.0), ("R10", "2", "U2", "5", 2.0),
    ("R11", "1", "U2", "5", 2.0), ("Q2", "3", "U2", "5", 1.5),
    ("C10", "1", "U3", "5", 8.0), ("R14", "1", "RS1", "1", 10.0), ("C11", "1", "U3", "4", 2.0),
    ("C12", "1", "U3", "3", 1.0),
    ("C15", "1", "U4", "3", 4.0), ("C16", "1", "U4", "3", 10.0), ("C18", "1", "U4", "8", 2.0),
    ("R8", "2", "U4", "8", 1.5), ("C14", "1", "U5", "1", 8.0), ("C1", "1", "U1", "4", 8.0),
    ("C2", "1", "U1", "3", 8.0), ("C13", "1", "Q1", "3", 2.0), ("D1", "1", "J1", "A4", 2.0),
    ("R1", "1", "J1", "A5", 1.5), ("R2", "1", "J1", "B5", 1.5), ("C20", "1", "U4", "12", 1.0),
    ("C19", "1", "U4", "13", 0.5), ("R21", "2", "U4", "22", 1.0), ("R22", "2", "U4", "5", 1.0),
    # anchors to physical places: (part, pad, "@", (X, Y), weight)
    ("Q1", "3", "J5", "1", 5.0),             # laser switch next to the laser wire pads
    # ring LED resistors close to their LEDs (LEDs are fixed on the bottom face, inside the circle)
    ("R23", "1", "LED3", "2", 4.0), ("R24", "1", "LED3", "3", 4.0), ("R25", "1", "LED3", "4", 4.0),
    ("R32", "1", "LED4", "2", 4.0), ("R33", "1", "LED4", "3", 4.0), ("R34", "1", "LED4", "4", 4.0),
    # button ladder resistors at their own switch (v0.6 routing: BTN_NX / BTN_PV stay a few mm
    # long and BTN is the one net along the button row, instead of three long nets)
    ("R30", "2", "SW2", "1", 2.0), ("R31", "2", "SW3", "1", 2.0),
    ("RS1", "1", "@", (12.0, 1.0), 2.0),     # sense resistor next to the LED- pad
]


class Placer:
    def __init__(self, hj, comps, fixed, start, seed=1, extra=None):
        self.hj, self.comps, self.fixed = hj, comps, fixed
        self.extra = extra or {}      # ref -> extra clearance (mm), see routable()
        self.rng = random.Random(seed)
        C = hj["components"]
        self.outline = [tuple(p) for p in hj["pcb_outline"]]
        self.ty = C["trough_y"]
        self.exc = C["trough_exceptions"]
        self.keep_b = [(k["x0"], k["y0"], k["x1"], k["y1"]) for k in C["keepout_bottom"]]
        self.circ_b = C.get("keepout_bottom_circles", [])
        self.keep_t = [(k["x0"], k["y0"], k["x1"], k["y1"]) for k in C.get("keepout_top", [])]
        self.crt, self.holes, self.pads = {}, {}, {}
        for ref, c in comps.items():
            fp = gen_pcb.load_fp(c["fp"])
            self.crt[ref], _ = local_boxes(fp)
            self.holes[ref] = gen_pcb.hole_boxes(fp)
            self.pads[ref] = [(str(p.number), p.position.X, p.position.Y) for p in fp.pads
                              if str(p.number) in c["nets"]]
        self.state = dict(start)
        self.movable = [r for r in comps if r not in fixed]
        # nets
        self.nets = {}
        for ref, c in comps.items():
            for pin, net in c["nets"].items():
                self.nets.setdefault(net, set()).add(ref)
        self.part_nets = {r: [n for n, rs in self.nets.items() if r in rs and NET_W.get(n, 1.0) > 0]
                          for r in comps}
        self.aff = [a for a in AFFINITY if a[0] in comps and (a[2] in comps or a[2] == "@")]
        self.part_aff = {r: [i for i, a in enumerate(self.aff) if a[0] == r or a[2] == r] for r in comps}
        self.fixed_boxes = {"F": [], "B": []}
        self.fixed_holes = []
        for ref, (X, Y, rot, side) in fixed.items():
            for sd in self.sides_of(ref, side):
                self.fixed_boxes[sd].append(gen_pcb.housing_box(self.crt[ref], X, Y, rot, side))
            for hb in self.holes[ref]:
                self.fixed_holes.append(gen_pcb.housing_box(hb, X, Y, rot, side))
        # USB D+/D- escape: D- vias (both sides), D+ U (bottom) - against pad copper
        self.usb_v, self.usb_u = gen_pcb.usb_escape_keepouts(fixed, comps) if "J1" in fixed else ([], [])
        self.padbox = {ref: gen_pcb.pad_boxes(gen_pcb.load_fp(c["fp"])) for ref, c in comps.items()}

    def sides_of(self, ref, side):
        if self.comps[ref]["fp"].endswith("TopBottom_1.6x1.8"):
            return ("F", "B")
        return (side,)

    def pad_xy(self, ref, pin, st=None):
        X, Y, rot, side = (st or self.state)[ref] if ref in (st or self.state) else self.fixed[ref]
        for (num, px, py) in self.pads[ref]:
            if num == pin:
                x, y = gen_pcb.xform_pt(px, py, rot, side == "B")
                return X + x, Y - y
        return X, Y

    def all_pads(self, ref, st):
        X, Y, rot, side = st[ref]
        out = []
        for (num, px, py) in self.pads[ref]:
            x, y = gen_pcb.xform_pt(px, py, rot, side == "B")
            out.append((X + x, Y - y))
        return out

    def box(self, ref, st):
        X, Y, rot, side = st[ref]
        return gen_pcb.housing_box(self.crt[ref], X, Y, rot, side)

    def hard_ok(self, ref, st):
        X, Y, rot, side = st[ref]
        bx = self.box(ref, st)
        g = 0.06
        bx = (bx[0] - g, bx[1] - g, bx[2] + g, bx[3] + g)
        for pt in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3]),
                   ((bx[0] + bx[2]) / 2, bx[1]), ((bx[0] + bx[2]) / 2, bx[3])):
            if not gen_pcb.inside_poly(pt, self.outline):
                return False
        if side == "B":
            lo, hi = self.ty
            for e in self.exc:
                if bx[0] >= e["x0"] and bx[2] <= e["x1"]:
                    if e["side"] == "-Y":
                        lo = -99
                    else:
                        hi = 99
            if bx[1] < lo or bx[3] > hi:
                return False
            for k in self.keep_b:
                if gen_pcb.overlap(bx, k):
                    return False
            for ci in self.circ_b:       # light-pipe circle around SW1 (fixed parts are exempt)
                if ref not in ci["allowed"] and gen_pcb.box_hits_circle(bx, ci):
                    return False
        else:
            for k in self.keep_t:        # front hold-down pad on the top side
                if gen_pcb.overlap(bx, k):
                    return False
        for fb in self.fixed_boxes[side]:
            if gen_pcb.overlap(bx, fb):
                return False
        for h in self.fixed_holes:
            if gen_pcb.overlap(bx, h):
                return False
        if gen_pcb.usb_conflict(self.padbox[ref], X, Y, rot, side, self.usb_v, self.usb_u):
            return False
        return True

    def overlap_area(self, ref, st, boxes):
        b = self.box(ref, st)
        side = st[ref][3]
        a = 0.0
        for r2, (b2, s2) in boxes.items():
            if r2 == ref or s2 != side:
                continue
            m = 0.10 + self.extra.get(ref, 0.0) + self.extra.get(r2, 0.0)
            dx = min(b[2], b2[2]) - max(b[0], b2[0]) + m
            dy = min(b[3], b2[3]) - max(b[1], b2[1]) + m
            if dx > 0 and dy > 0:
                a += dx * dy
        return a

    def net_cost(self, net, st):
        xs, ys = [], []
        for ref in self.nets[net]:
            s = st if ref in st else None
            if ref in st:
                for (x, y) in self.all_pads_pin(ref, net, st):
                    xs.append(x)
                    ys.append(y)
            else:
                for (x, y) in self.all_pads_pin(ref, net, None):
                    xs.append(x)
                    ys.append(y)
        if len(xs) < 2:
            return 0.0
        sides = set()
        for ref in self.nets[net]:
            sides.add((st[ref] if (st is not None and ref in st) else self.fixed[ref])[3]
                      if not self.comps[ref]["fp"].endswith("TopBottom_1.6x1.8") else "FB")
        cross = 1.6 if len(sides - {"FB"}) > 1 else 0.0
        return NET_W.get(net, 1.0) * ((max(xs) - min(xs)) + (max(ys) - min(ys)) + cross)

    def all_pads_pin(self, ref, net, st):
        X, Y, rot, side = st[ref] if st is not None and ref in st else self.fixed[ref]
        pins = [p for p, n in self.comps[ref]["nets"].items() if n == net]
        out = []
        for (num, px, py) in self.pads[ref]:
            if num in pins:
                x, y = gen_pcb.xform_pt(px, py, rot, side == "B")
                out.append((X + x, Y - y))
        return out

    def aff_cost(self, i, st):
        a, pa, b, pb, w = self.aff[i]
        full = dict(self.fixed)
        full.update(st)
        x1, y1 = self.pad_xy(a, pa, full)
        if b == "@":
            return w * math.hypot(x1 - pb[0], y1 - pb[1])
        x2, y2 = self.pad_xy(b, pb, full)
        d = math.hypot(x1 - x2, y1 - y2)
        side_pen = 2.0 if full[a][3] != full[b][3] else 0.0
        return w * (d + side_pen)

    def run(self, iters=60000, t0=3.0, t1=0.01, w0=1.0, w1=1500.0, log=None):
        st = self.state
        full = dict(self.fixed)
        full.update(st)
        boxes = {r: (self.box(r, full), full[r][3]) for r in full}
        netc = {n: self.net_cost(n, full) for n in self.nets if NET_W.get(n, 1.0) > 0}
        affc = [self.aff_cost(i, full) for i in range(len(self.aff))]
        best = None
        for it in range(iters):
            f = it / iters
            T = t0 * (t1 / t0) ** f
            w = w0 * (w1 / w0) ** f
            ref = self.rng.choice(self.movable)
            old = full[ref]
            X, Y, rot, side = old
            mv = self.rng.random()
            sig = (0.3 + 3.0 * (1 - f)) if w0 < 1000 else 0.25
            if mv < 0.70:
                new = (round(X + self.rng.gauss(0, sig), 2), round(Y + self.rng.gauss(0, sig), 2), rot, side)
            elif mv < 0.85:
                new = (X, Y, (rot + self.rng.choice((90, 180, 270))) % 360, side)
            elif mv < 0.93 and ref not in SIDE_LOCK:
                new = (X, Y, rot, "B" if side == "F" else "F")
            else:
                other = self.rng.choice(self.movable)
                if other == ref:
                    continue
                o = full[other]
                if (ref in SIDE_LOCK and o[3] != SIDE_LOCK[ref]) or (other in SIDE_LOCK and side != SIDE_LOCK[other]):
                    continue
                full[ref], full[other] = (o[0], o[1], rot, o[3]), (X, Y, o[2], side)
                if not (self.hard_ok(ref, full) and self.hard_ok(other, full)):
                    full[ref], full[other] = old, o
                    continue
                d, newc = self._delta([ref, other], full, boxes, netc, affc, w)
                if d < 0 or self.rng.random() < math.exp(-d / T):
                    self._commit([ref, other], full, boxes, netc, affc, newc)
                else:
                    full[ref], full[other] = old, o
                continue
            if ref in SIDE_LOCK and new[3] != SIDE_LOCK[ref]:
                continue
            full[ref] = new
            if not self.hard_ok(ref, full):
                full[ref] = old
                continue
            d, newc = self._delta([ref], full, boxes, netc, affc, w, old={ref: old})
            if d < 0 or self.rng.random() < math.exp(-d / T):
                self._commit([ref], full, boxes, netc, affc, newc)
            else:
                full[ref] = old
            if log and it % 50000 == 0:
                tot_ov = sum(self.overlap_area(r, full, boxes) for r in self.movable) / 2
                log(f"it {it} T {T:.3f} w {w:.1f} wl {sum(netc.values()):.1f} "
                    f"aff {sum(affc):.1f} overlap {tot_ov:.2f}")
        self.state = {r: full[r] for r in self.movable}
        return self.state

    def _delta(self, refs, full, boxes, netc, affc, w, old=None):
        nets = set()
        affs = set()
        for r in refs:
            nets.update(self.part_nets[r])
            affs.update(self.part_aff[r])
        newnet = {n: self.net_cost(n, full) for n in nets}
        newaff = {i: self.aff_cost(i, full) for i in affs}
        d = sum(newnet[n] - netc[n] for n in nets) + sum(newaff[i] - affc[i] for i in affs)
        # overlap: recompute for moved parts against the current boxes
        ov_old = 0.0
        for r in refs:
            b = boxes[r]
            ov_old += self._ov_box(r, b[0], b[1], boxes)
        newb = {r: (self.box(r, full), full[r][3]) for r in refs}
        tmp = dict(boxes)
        tmp.update(newb)
        ov_new = 0.0
        for r in refs:
            ov_new += self._ov_box(r, newb[r][0], newb[r][1], tmp)
        d += w * (ov_new - ov_old)
        return d, (newnet, newaff, newb)

    def _ov_box(self, ref, b, side, boxes):
        a = 0.0
        for r2, (b2, s2) in boxes.items():
            if r2 == ref or (s2 != side and not (self.comps[r2]["fp"].endswith("TopBottom_1.6x1.8"))):
                continue
            m = 0.10 + self.extra.get(ref, 0.0) + self.extra.get(r2, 0.0)
            dx = min(b[2], b2[2]) - max(b[0], b2[0]) + m
            dy = min(b[3], b2[3]) - max(b[1], b2[1]) + m
            if dx > 0 and dy > 0:
                a += dx * dy
        return a

    def _commit(self, refs, full, boxes, netc, affc, newc):
        newnet, newaff, newb = newc
        netc.update(newnet)
        for i, v in newaff.items():
            affc[i] = v
        boxes.update(newb)


def anneal(hj_path, out_json, seed=7, iters=300000, start=None, log=print, t0=3.0, w0=1.0, extra=None):
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = gen_pcb.fixed_parts(hj)
    pref = start or {r: v for r, v in gen_pcb.PREFERRED.items() if r in comps}
    for r, v in list(pref.items()):
        if r in SIDE_LOCK:
            pref[r] = (v[0], v[1], v[2], SIDE_LOCK[r])
    pl = Placer(hj, comps, fixed, pref, seed=seed, extra=extra)
    # starting points that break a hard rule are pulled to the board centre
    full = dict(fixed)
    full.update(pl.state)
    for r in pl.movable:
        if not pl.hard_ok(r, full):
            for k in range(400):
                cand = (round(pl.rng.uniform(10, 31), 2), round(pl.rng.uniform(-7, 7), 2),
                        pl.rng.choice((0, 90)), full[r][3])
                full[r] = cand
                if pl.hard_ok(r, full):
                    break
    pl.state = {r: full[r] for r in pl.movable}
    st = pl.run(iters=iters, t0=t0, w0=w0, log=log)
    # polish: overlap removal at (almost) zero temperature
    st = pl.run(iters=iters // 2, t0=0.02, t1=0.001, w0=3000.0, w1=20000.0, log=log)

    def legal(st):
        order = sorted(st, key=lambda r: -((pl.crt[r][2] - pl.crt[r][0]) * (pl.crt[r][3] - pl.crt[r][1])))
        return gen_pcb.legalise(hj, comps, {r: st[r] for r in order}, fixed, extra=extra)
    # greedy clean-up of residual overlaps with gen_pcb.legalise; if parts stay unplaced, reheat
    # slightly (the packing is tight: ~85 % of the usable area) and polish again
    plc, moved, unplaced = legal(st)
    tries = 0
    while unplaced and tries < int(os.environ.get("FLASHKA_SA_REHEATS", "8")):
        tries += 1
        log(f"reheat {tries}: unplaced {unplaced}")
        pl.rng.seed(seed * 1000 + tries)
        pl.run(iters=iters // 3, t0=0.3, t1=0.01, w0=300.0, w1=3000.0, log=None)
        st = pl.run(iters=iters // 3, t0=0.02, t1=0.001, w0=3000.0, w1=20000.0, log=None)
        plc, moved, unplaced = legal(st)
    res = {"seed": seed, "iters": iters, "unplaced": unplaced,
           "placement": {r: list(v) for r, v in plc.items()},
           "moved_by_legaliser": [[m[0], m[4]] for m in moved]}
    with open(out_json, "w") as f:
        json.dump(res, f, indent=1)
    return res


def routable(hj_path, out_json, seed=7, iters=300000, rounds=12, workdir=None, log=print):
    """Anneal, then repeat: build the bare board, find the pads that are boxed in by their
    neighbours (route.Router.unreachable_pads), give those parts and the parts around them extra
    clearance and re-anneal from the current placement.  Stops when no pad is stuck."""
    import route
    workdir = workdir or out_json + ".work"
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = gen_pcb.fixed_parts(hj)
    res = anneal(hj_path, out_json, seed=seed, iters=iters, log=log)
    extra = {}
    for rnd in range(rounds + 1):
        plc = {r: tuple(v) for r, v in res["placement"].items()}
        path, _, _, _ = gen_pcb.build(workdir, hj_path, placement=plc)
        bad = route.Router(path).unreachable_pads()
        log(f"round {rnd}: unplaced {res['unplaced']}, stuck pads {len(bad)} {bad}, "
            f"parts with extra clearance {len(extra)}")
        res["stuck"] = [f"{n}:{p}" for n, p in bad]
        with open(out_json, "w") as f:
            json.dump(res, f, indent=1)
        if not bad or rnd == rounds:
            break
        for (_, pad) in bad:
            ref = pad.split(".")[0]
            X, Y, _, side = plc[ref] if ref in plc else fixed[ref]
            for r2, v in plc.items():
                if r2 in fixed or v[3] != side:
                    continue
                d = math.hypot(v[0] - X, v[1] - Y)
                if r2 == ref or d < 2.2:
                    extra[r2] = min(extra.get(r2, 0.0) + (0.12 if r2 == ref else 0.06), 0.45)
        start = {r: v for r, v in plc.items() if r not in fixed}
        res = anneal(hj_path, out_json, seed=seed + rnd + 1, iters=iters // 2, start=start, t0=0.5, w0=30.0,
                     extra=extra, log=log)
    return res


if __name__ == "__main__":
    if "--routable" in sys.argv:
        sys.argv.remove("--routable")
        r = routable(sys.argv[1], sys.argv[2], seed=int(sys.argv[3]) if len(sys.argv) > 3 else 7,
                     iters=int(os.environ.get("FLASHKA_SA_ITERS", "300000")))
        print("unplaced:", r["unplaced"], " stuck pads:", r.get("stuck"))
        sys.exit(0)
    hj = sys.argv[1] if len(sys.argv) > 1 else "cad/housing_interface.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "cad/pcb_placement_sa.json"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    start, t0, iters = None, 3.0, int(os.environ.get("FLASHKA_SA_ITERS", "300000"))
    if len(sys.argv) > 4:              # refine an existing placement: start json, cooler start
        start = {r: tuple(v) for r, v in json.load(open(sys.argv[4]))["placement"].items()}
        comps_ = {c["ref"] for c in COMPONENTS}
        fixed_ = gen_pcb.fixed_parts(json.load(open(hj)))
        start = {r: v for r, v in start.items() if r in comps_ and r not in fixed_}
        t0, iters = float(sys.argv[5]) if len(sys.argv) > 5 else 0.4, 150000
    r = anneal(hj, out, seed=seed, iters=iters, start=start, t0=t0, w0=30.0 if start else 1.0)
    print("unplaced:", r["unplaced"], " legaliser moves:", len(r["moved_by_legaliser"]))
