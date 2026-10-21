# SPDX-License-Identifier: GPL-3.0-or-later
"""
Greedy legaliser for the hand-made placement in gen_pcb.py.

Each movable part keeps its preferred position if that spot is free;
otherwise it moves to the nearest free spot (0.2 mm grid, rotations 0/90)
that keeps the courtyard inside the board, off the other parts on the same
side, off through-hole pads (both sides) and - on the bottom - inside the
trough between the housing ledges.
"""
import math

from kiutils.footprint import Footprint

KFP = "/usr/share/kicad/footprints"


def local_boxes(fp):
    """courtyard box and list of through-hole pad boxes, local coords."""
    xs, ys = [], []
    for g in fp.graphicItems:
        if getattr(g, "layer", "") == "F.CrtYd":
            for a in ("start", "end", "center"):
                p = getattr(g, a, None)
                if p is not None:
                    xs.append(p.X)
                    ys.append(p.Y)
            if type(g).__name__ in ("FpCircle",):
                r = math.hypot(g.end.X - g.center.X, g.end.Y - g.center.Y)
                xs += [g.center.X - r, g.center.X + r]
                ys += [g.center.Y - r, g.center.Y + r]
    if not xs:
        for p in fp.pads:
            xs += [p.position.X - p.size.X / 2 - 0.25, p.position.X + p.size.X / 2 + 0.25]
            ys += [p.position.Y - p.size.Y / 2 - 0.25, p.position.Y + p.size.Y / 2 + 0.25]
    crt = (min(xs), min(ys), max(xs), max(ys))
    tht = []
    for p in fp.pads:
        if p.type in ("thru_hole", "np_thru_hole"):
            w = max(p.size.X, p.drill.diameter if p.drill else 0) / 2 + 0.25
            h = max(p.size.Y, p.drill.diameter if p.drill else 0) / 2 + 0.25
            tht.append((p.position.X - w, p.position.Y - h, p.position.X + w, p.position.Y + h))
    return crt, tht


def xform(box, rot, flip):
    x0, y0, x1, y1 = box
    pts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    out = []
    t = math.radians(rot)
    for (x, y) in pts:
        if flip:
            y = -y
        xr = x * math.cos(t) + y * math.sin(t)
        yr = -x * math.sin(t) + y * math.cos(t)
        out.append((xr, yr))
    return (min(p[0] for p in out), min(p[1] for p in out),
            max(p[0] for p in out), max(p[1] for p in out))


def at(box, x, y):
    return (box[0] + x, box[1] + y, box[2] + x, box[3] + y)


def ov(a, b, m=0.0):
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


def legalise(top, bottom, comps, load_fp, outline_k, y_trough_k, fixed=("J1", "S1", "S2"),
             order=None, max_r=20.0, step=0.2):
    """top/bottom: ref -> (x, y, rot) in KiCad coordinates. Returns new dicts."""
    info = {}
    for ref in list(top) + list(bottom):
        fp = load_fp(comps[ref]["fp"])
        info[ref] = local_boxes(fp)
    placed = {"F": [], "B": []}
    tht_all = []
    new_top, new_bot = {}, {}

    def commit(ref, side, x, y, rot):
        crt, tht = info[ref]
        flip = side == "B"
        b0 = at(xform(crt, rot, flip), x, y)
        placed[side].append((ref, (b0[0] - 0.06, b0[1] - 0.06, b0[2] + 0.06, b0[3] + 0.06)))
        for tb in tht:
            tht_all.append((ref, at(xform(tb, rot, flip), x, y)))

    for ref in fixed:
        x, y, r = top[ref]
        commit(ref, "F", x, y, r)
        new_top[ref] = (x, y, r)

    def ok(ref, side, x, y, rot):
        crt, tht = info[ref]
        flip = side == "B"
        bx = at(xform(crt, rot, flip), x, y)
        g = 0.12
        bx = (bx[0] - g / 2, bx[1] - g / 2, bx[2] + g / 2, bx[3] + g / 2)
        for (cx, cy) in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3]),
                         ((bx[0] + bx[2]) / 2, bx[1]), ((bx[0] + bx[2]) / 2, bx[3])):
            if not inside_poly((cx, cy), outline_k):
                return False
        if side == "B" and (bx[1] < y_trough_k[0] or bx[3] > y_trough_k[1]):
            return False
        for (_, o) in placed[side]:
            if ov(bx, o):
                return False
        for (_, t) in tht_all:
            if ov(bx, t):
                return False
        # own THT pads must not hit parts on the other side
        other = "B" if side == "F" else "F"
        for tb in tht:
            tbx = at(xform(tb, rot, flip), x, y)
            for (_, o) in placed[other]:
                if ov(tbx, o):
                    return False
        return True

    seq = order or ([r for r in top if r not in fixed] + list(bottom))
    moved = []
    unplaced = []
    for ref in seq:
        side = "F" if ref in top else "B"
        x0, y0, r0 = (top if side == "F" else bottom)[ref]
        best = None
        rots = [r0, (r0 + 90) % 180]
        if ok(ref, side, x0, y0, r0):
            best = (x0, y0, r0)
        else:
            rr = step
            while rr <= max_r and best is None:
                cands = []
                n = max(8, int(2 * math.pi * rr / step))
                for k in range(n):
                    a = 2 * math.pi * k / n
                    cands.append((x0 + rr * math.cos(a), y0 + rr * math.sin(a)))
                for rot in rots:
                    for (x, y) in cands:
                        x, y = round(x / 0.1) * 0.1, round(y / 0.1) * 0.1
                        if ok(ref, side, x, y, rot):
                            best = (round(x, 2), round(y, 2), rot)
                            break
                    if best:
                        break
                rr += step
        if best is None:
            unplaced.append(ref)
            continue
        if best != (x0, y0, r0):
            moved.append((ref, side, (x0, y0, r0), best))
        commit(ref, side, *best)
        (new_top if side == "F" else new_bot)[ref] = best
    # fallback: try the other side for parts that did not fit
    still = []
    for ref in unplaced:
        side0 = "F" if ref in top else "B"
        side = "B" if side0 == "F" else "F"
        x0, y0, r0 = (top if side0 == "F" else bottom)[ref]
        best = None
        rr = 0.0
        while rr <= max_r and best is None:
            n = 1 if rr == 0 else max(8, int(2 * math.pi * rr / step))
            for k in range(n):
                a = 2 * math.pi * k / n
                x, y = round((x0 + rr * math.cos(a)) / 0.1) * 0.1, round((y0 + rr * math.sin(a)) / 0.1) * 0.1
                for rot in (r0, (r0 + 90) % 180):
                    if ok(ref, side, x, y, rot):
                        best = (round(x, 2), round(y, 2), rot)
                        break
                if best:
                    break
            rr += step
        if best is None:
            still.append(ref)
            continue
        moved.append((ref, side0 + "->" + side, (x0, y0, r0), best))
        commit(ref, side, *best)
        (new_top if side == "F" else new_bot)[ref] = best
    unplaced = still
    legalise.state = dict(placed=placed, tht=tht_all, unplaced=unplaced)
    return new_top, new_bot, moved
