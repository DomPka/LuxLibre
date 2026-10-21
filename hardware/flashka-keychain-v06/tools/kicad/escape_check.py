#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Pad escape check (and fix) for a FlashKa Keychain v0.6 placement.

The slot placer packs the 0402 parts 0.04 mm apart.  A pad can end up walled in by
pads of other nets, holes and the board edge, so that no track (0.13 mm at the router
clearance) can leave it - the net is then unroutable whatever the router does.

check: builds the board from the placement, adds the router's fixed pre-routes (USB,
module pad vias, ring-LED fan-outs, power-stage GND vias) and floods, for every SMD
pad, the area a track of its net may use on the pad's layer (4-connected, like the
router's A*) within 1.6 mm.  The pad is free if that area holds a legal via spot, or
(signals) leaves the 1.6 mm window or touches another pad of the same net.  GND pads
need a via spot.

fix: flips / swaps 0402 parts (keeping the slot positions) until no pad is trapped,
choosing among the moves by trapped count, then by the legal_placer cost.

  python3 tools/kicad/escape_check.py cad/housing_interface.json placement.json [out.json]
  (with out.json: fix and write the fixed placement)
"""
import contextlib
import io
import json
import os
import sys
import tempfile

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_pcb  # noqa: E402
import legal_placer  # noqa: E402
from flashka_parts import COMPONENTS  # noqa: E402

SMALL = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric")
SKIP = {("U4", "49"), ("U4", "50")}      # module ground pad: thermal vias are pre-routed
REACH = 1.6


def trapped(hj_path, placement, workdir):
    """list of (ref, pad, net) that cannot escape"""
    import route
    fixed = gen_pcb.fixed_parts(json.load(open(hj_path)))
    plc = {r: tuple(v) for r, v in placement.items() if r not in fixed}
    with contextlib.redirect_stdout(io.StringIO()):
        path, _t, _b, _m = gen_pcb.build(workdir, hj_path, plot=None, placement=plc)
    r = route.Router(path)
    for p in (q for ps in r.pads.values() for q in ps):
        p["cellset"] = set(p["cells"])
    r.smd_far = ndimage.distance_transform_edt(~(r.smd_own != 0)) * route.G >= route.VIA_D / 2 + 0.06
    r.locked, r.frozen = set(), set()
    r.preroute_usb()
    r.preroute_ep()
    r.preroute_leds(log=lambda m: None)
    r.gnd_cid = {}
    r._set_pour_state(None)
    pk = {r._gkey(p) for p in r._gnd_pads() if p["ref"] in route.POWER_GND}
    r.fanout_gnd(pfac=6.0, only=pk, force=True, lock=True)
    r.locked = set(r.conns)
    R = int(REACH / route.G)
    bad = []
    for name, code in r.nets.items():
        ps = r.pads.get(code, [])
        if len(ps) < 2 and name != "GND":
            continue
        w = route.WIDTH.get(name, route.SIGNAL_W)
        hard, hard_n, _c, _cn, vh, _vc = r.fields(code, w)
        if w > route.NECK_W:
            hard = hard_n
        for p in ps:
            if p["pth"] or (p["ref"], p["num"]) in SKIP:
                continue
            k = p["layers"][0]
            cells = [c for c in p["cells"] if c[0] == k]
            if any(r.trk[c] == code for c in cells):
                continue                                  # pre-routed
            j0, i0 = cells[0][1], cells[0][2]
            jlo, jhi, ilo, ihi = max(j0 - R, 0), min(j0 + R, r.ny), max(i0 - R, 0), min(i0 + R, r.nx)
            cells = [c for c in cells if jlo <= c[1] < jhi and ilo <= c[2] < ihi]
            A = hard[k][jlo:jhi, ilo:ihi].copy()
            for c in cells:
                A[c[1] - jlo, c[2] - ilo] = True
            lab, _n = ndimage.label(A)
            ids = list({lab[c[1] - jlo, c[2] - ilo] for c in cells} - {0})
            reg = np.isin(lab, ids)
            if (reg & vh[jlo:jhi, ilo:ihi]).any():
                continue
            if name == "GND":
                bad.append((p["ref"], p["num"], name))
                continue
            if reg[0, :].any() or reg[-1, :].any() or reg[:, 0].any() or reg[:, -1].any():
                continue
            own = np.zeros_like(reg)
            for q in ps:
                if q is not p:
                    for c in q["cells"]:
                        if c[0] == k and jlo <= c[1] < jhi and ilo <= c[2] < ihi:
                            own[c[1] - jlo, c[2] - ilo] = True
            if (ndimage.binary_dilation(reg) & own).any():
                continue
            bad.append((p["ref"], p["num"], name))
    return sorted(set(bad))


def score(bad):
    return sum(3 if n == "GND" else 10 for (_r, _p, n) in bad)


def fix(hj_path, placement, log=print, max_rounds=8):
    hj = json.load(open(hj_path))
    comps = {c["ref"]: c for c in COMPONENTS}
    fixed = gen_pcb.fixed_parts(hj)
    plc = {r: tuple(v) for r, v in placement.items()}
    small = sorted(r for r in plc if r not in fixed and comps[r]["fp"] in SMALL)
    allfixed = dict(fixed)
    allfixed.update({r: v for r, v in plc.items() if r not in small})
    lp = legal_placer.LegalPlacer(hj, comps, allfixed, seed=1)
    lp.esc_w = 10.0
    lp.movable = list(small)

    def cost(p):
        lp.init({r: p[r] for r in small})
        return lp.total()

    wd = tempfile.mkdtemp(prefix="flashka_esc_")
    bad = trapped(hj_path, plc, wd)
    cur = (score(bad), cost(plc))
    log(f"escape fix: start trapped {bad}, cost {cur[1]:.1f}")
    for rnd in range(max_rounds):
        if not bad:
            break
        parts = sorted({b[0] for b in bad if b[0] in small})
        if not parts:
            log("escape fix: trapped pads on hand-placed parts only")
            break
        best = None
        for ref in parts:
            X, Y, rot, sd = plc[ref]
            cands = [{ref: (X, Y, (rot + 180) % 360, sd)}]
            for o in small:
                if o == ref:
                    continue
                Xo, Yo, roto, sdo = plc[o]
                if lp.side_lock.get(ref, sdo) != sdo or lp.side_lock.get(o, sd) != sd:
                    continue
                for fa in (0, 180):
                    for fb in (0, 180):
                        cands.append({ref: (Xo, Yo, (roto + fa) % 360, sdo), o: (X, Y, (rot + fb) % 360, sd)})
            # cheap pre-selection by the placement cost, then the real check
            scored = []
            for ch in cands:
                p2 = dict(plc)
                p2.update(ch)
                scored.append((cost(p2), ch))
            scored.sort(key=lambda t: t[0])
            for c2, ch in scored[:24]:
                p2 = dict(plc)
                p2.update(ch)
                b2 = trapped(hj_path, p2, wd)
                key = (score(b2), c2)
                if best is None or key < best[0]:
                    best = (key, ch, b2)
        if best is None or best[0] >= cur:
            log(f"escape fix: no improving move, trapped {bad}")
            break
        plc.update(best[1])
        cur, bad = best[0], best[2]
        log(f"escape fix round {rnd + 1}: {sorted(best[1])} -> trapped {bad}, cost {cur[1]:.1f}")
    return plc, bad


if __name__ == "__main__":
    hj = sys.argv[1]
    d = json.load(open(sys.argv[2]))
    plc = {r: tuple(v) for r, v in d.get("placement", d).items()}
    if len(sys.argv) > 3:
        plc, bad = fix(hj, plc)
        d = d if "placement" in d else {}
        d["placement"] = {r: list(v) for r, v in plc.items()}
        d["trapped"] = [list(b) for b in bad]
        with open(sys.argv[3], "w") as f:
            json.dump(d, f, indent=1)
    else:
        bad = trapped(hj, plc, tempfile.mkdtemp(prefix="flashka_esc_"))
    print("trapped pads:", len(bad), bad)
