#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
0402 slot placement for the FlashKa Keychain v0.6 main PCB.

At ~85 % fill the board has no room for a free-form annealer: almost every move of a
part collides with a neighbour.  The parts that are not 0402 resistors/capacitors are
placed by hand (gen_pcb.BIG_PARTS, with the housing-fixed parts and the hand-placed
clusters); what is left is cut into 0402 "slots":

  1. the free area (board, housing trough and keep-outs, fixed parts, holes, USB-C escape,
     the routing channels of legal_placer.CHANNELS) is packed with 0402 courtyards
     (1.66 x 0.74 mm, both orientations, 0.08 mm apart) by randomised greedy packing,
     the packing with the most slots wins;
  2. the 0402 parts are assigned to slots (and to one of the two orientations of the
     slot) by simulated annealing on the same cost as legal_placer.py (rectilinear MST
     of every net, side changes, decoupling/Kelvin affinities, pad escape).  A swap of two
     parts or a move to a free slot is always legal, so the search is effective.

  python3 tools/kicad/slot_placer.py cad/housing_interface.json out.json [seed] [iters]
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
import legal_placer  # noqa: E402
from flashka_parts import COMPONENTS  # noqa: E402

R0402 = "Resistor_SMD:R_0402_1005Metric"
# v0.6: the 0402 parts on the module's GPIO / ADC pins sit in the two columns left of the module;
# every one of their signal pads needs a via there unless it lines up with its module pin, and
# the 0.7 mm via channel between the columns and the module pads is what the router runs out of.
# These affinities (x PIN_W) pull each part to the row of its pin.
PIN_W = 1.0
PIN_AFF = [("C20", "1", "U4", "12", 4.0), ("R28", "1", "U4", "12", 2.0), ("R27", "2", "U4", "12", 2.0),
           ("C19", "1", "U4", "13", 4.0), ("R26", "2", "U4", "13", 2.0), ("R20", "1", "U4", "16", 4.0),
           ("R15", "1", "U4", "20", 4.0), ("R21", "2", "U4", "22", 4.0),
           # dividers kept together (one trace to the far end instead of three): LED current set
           # point R15-R16-C12, battery divider R27-R28-C20
           ("R16", "1", "R15", "2", 2.0), ("C12", "1", "R15", "2", 2.0),
           ("R28", "1", "C20", "1", 2.0), ("R27", "2", "C20", "1", 2.0)]
SMALL = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric")


def make_slots(lp, rng, side, tries=60, extra_gap=0.0):
    """Randomised greedy packing of 0402 courtyards; returns [(X, Y, horiz)]."""
    best = []
    m0 = lp.masks[(R0402, 0, side)]
    m9 = lp.masks[(R0402, 90, side)]
    c0 = list(zip(*np.nonzero(m0)))
    c9 = list(zip(*np.nonzero(m9)))
    cand = [(j, i, True) for (j, i) in c0] + [(j, i, False) for (j, i) in c9]
    w, h = 1.66, 0.74
    g = legal_placer.GAP + 1e-4 + extra_gap   # same separation as gen_pcb.legalise (courtyard grown by gap / 2)
    for t in range(tries):
        # scan order: random direction sweep with jitter (corner-first packings fill best)
        ax = rng.choice((1, -1))
        ay = rng.choice((1, -1))
        pref = rng.random()
        order = sorted(cand, key=lambda c: (ay * c[0] * (1 + pref) + ax * c[1] + rng.random() * 3))
        if rng.random() < 0.5:
            order = sorted(cand, key=lambda c: (ax * c[1] * (1 + pref) + ay * c[0] + rng.random() * 3))
        boxes, slots = [], []
        for (j, i, horiz) in order:
            X = round(8.8 + i * legal_placer.GRID, 3)
            Y = round(-8.25 + j * legal_placer.GRID, 3)
            bw, bh = (w, h) if horiz else (h, w)
            b = (X - bw / 2, Y - bh / 2, X + bw / 2, Y + bh / 2)
            ok = True
            for o in boxes:
                if min(b[2], o[2]) - max(b[0], o[0]) > -g and min(b[3], o[3]) - max(b[1], o[1]) > -g:
                    ok = False
                    break
            if ok:
                boxes.append(b)
                slots.append((X, Y, horiz))
        if len(slots) > len(best):
            best = slots
    return best


class SlotPlacer:
    def __init__(self, hj, comps, fixed, big, seed=1, esc_w=10.0, side_lock=None):
        self.rng = random.Random(seed)
        allfixed = dict(fixed)
        allfixed.update(big)
        self.small = [r for r in comps if r not in allfixed and comps[r]["fp"] in SMALL]
        rest = [r for r in comps if r not in allfixed and r not in self.small]
        if rest:
            raise SystemExit(f"not placed by hand and not 0402: {rest}")
        import placer
        pin_w = float(os.environ.get("FLASHKA_SP_PINW", PIN_W))
        aff = list(placer.AFFINITY) + [(a, pa, b, pb, w * pin_w) for (a, pa, b, pb, w) in PIN_AFF]
        self.lp = legal_placer.LegalPlacer(hj, comps, allfixed, seed=seed, affinity=aff)
        self.lp.esc_w = esc_w
        self.slots = []
        for side in "FB":
            for (X, Y, horiz) in make_slots(self.lp, self.rng, side):
                self.slots.append((X, Y, horiz, side))
        self.comps = comps

    def slot_state(self, s, flip):
        X, Y, horiz, side = self.slots[s]
        rot = (0 if horiz else 90) + (180 if flip else 0)
        return (X, Y, rot, side)

    def init(self, start=None):
        """greedy: each part to the free slot nearest to its start position (or to the
        centroid of its net partners)"""
        lp = self.lp
        free = set(range(len(self.slots)))
        self.assign = {}
        for r in self.small:
            if start and r in start:
                X0, Y0 = start[r][0], start[r][1]
                sd0 = start[r][3]
            else:
                X0, Y0, sd0 = 20.0, 0.0, "F"
            cand = [s for s in free if not (r in lp.side_lock and self.slots[s][3] != lp.side_lock[r])]
            s = min(cand, key=lambda s: math.hypot(self.slots[s][0] - X0, self.slots[s][1] - Y0) +
                    (1.0 if self.slots[s][3] != sd0 else 0.0))
            free.discard(s)
            self.assign[r] = (s, False)
        self.free = free
        lp.movable = list(self.small)
        st = {r: self.slot_state(*self.assign[r]) for r in self.small}
        lp.init(st)

    def _apply(self, changes):
        """changes: {ref: (slot, flip)} -> legal_placer state changes"""
        return {r: self.slot_state(s, f) for r, (s, f) in changes.items()}

    def run(self, iters=200000, t0=3.0, t1=0.01, log=None):
        lp = self.lp
        acc = 0
        for it in range(iters):
            f = it / iters
            T = t0 * (t1 / t0) ** f
            r = self.rng.choice(self.small)
            s, fl = self.assign[r]
            mv = self.rng.random()
            if mv < 0.25:
                ch = {r: (s, not fl)}
            elif mv < 0.6 and self.free:
                s2 = self.rng.choice(tuple(self.free))
                if r in lp.side_lock and self.slots[s2][3] != lp.side_lock[r]:
                    continue
                ch = {r: (s2, self.rng.random() < 0.5)}
            else:
                o = self.rng.choice(self.small)
                if o == r:
                    continue
                s2, f2 = self.assign[o]
                if (r in lp.side_lock and self.slots[s2][3] != lp.side_lock[r]) or \
                   (o in lp.side_lock and self.slots[s][3] != lp.side_lock[o]):
                    continue
                ch = {r: (s2, self.rng.random() < 0.5), o: (s, self.rng.random() < 0.5)}
            # slots are legal by construction; skip the dynamic check of legal_placer
            sd = lp.soft
            lp.soft = True
            ov = lp.ov_w
            lp.ov_w = 0.0
            ok = lp._try(self._apply(ch), T)
            lp.soft, lp.ov_w = sd, ov
            if ok:
                acc += 1
                for q, (sq, fq) in ch.items():
                    old = self.assign[q][0]
                    self.free.add(old)
                for q, (sq, fq) in ch.items():
                    self.free.discard(sq)
                    self.assign[q] = (sq, fq)
            if log and it % 50000 == 0:
                log(f"it {it} T {T:.3f} cost {lp.total():.1f} (nets {sum(lp.netc.values()):.1f}, "
                    f"aff {sum(lp.affc):.1f}, esc {lp.escc:.1f}) acc {acc}")
                acc = 0


def place(hj_path, start=None, seed=1, iters=300000, log=print):
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = gen_pcb.fixed_parts(hj)
    big = {r: v for r, v in gen_pcb.BIG_PARTS.items() if r not in fixed}
    ov = os.environ.get("FLASHKA_SP_BIG")            # experiments: JSON file with other hand positions
    if ov:
        big.update({r: tuple(v) for r, v in json.load(open(ov)).items()})
    drop = os.environ.get("FLASHKA_SP_DROP_CHANNELS")   # experiments: "x0,x0,..." channels to leave out
    if drop:
        xs = [float(x) for x in drop.split(",")]
        legal_placer.CHANNELS[:] = [c for c in legal_placer.CHANNELS if not any(abs(c[1] - x) < 1e-6 for x in xs)]
    sp = SlotPlacer(hj, comps, fixed, big, seed=seed, esc_w=float(os.environ.get("FLASHKA_SP_ESC", "10")))
    log(f"slots: {len(sp.slots)} (F {sum(1 for s in sp.slots if s[3] == 'F')}, "
        f"B {sum(1 for s in sp.slots if s[3] == 'B')}) for {len(sp.small)} parts")
    if len(sp.slots) < len(sp.small):
        raise SystemExit("not enough 0402 slots")
    sp.init(start)
    t0 = float(os.environ.get("FLASHKA_SP_T0", "3.0"))   # low start temperature: stay near the start placement
    sp.run(iters=iters, t0=t0, log=log)
    sp.run(iters=iters // 3, t0=0.05, t1=0.001, log=log)
    plc = dict(big)
    plc.update({r: sp.slot_state(*sp.assign[r]) for r in sp.small})
    return sp, plc


if __name__ == "__main__":
    hj = sys.argv[1]
    out = sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    iters = int(sys.argv[4]) if len(sys.argv) > 4 else 300000
    start = None
    if len(sys.argv) > 5:
        d = json.load(open(sys.argv[5]))
        start = {r: tuple(v) for r, v in d.get("placement", d).items()}
    sp, plc = place(hj, start=start, seed=seed, iters=iters)
    wl = sp.lp.report()
    res = {"seed": seed, "iters": iters, "mst_mm": round(sum(wl.values()), 1), "cost": round(sp.lp.total(), 1),
           "slots": len(sp.slots), "placement": {r: list(v) for r, v in plc.items()}}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print("MST %.1f mm, cost %.1f, slots %d" % (sum(wl.values()), sp.lp.total(), len(sp.slots)))
