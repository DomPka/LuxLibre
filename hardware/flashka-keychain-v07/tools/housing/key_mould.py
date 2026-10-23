#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - casting moulds for the rubber side keys (cast at home, 4 keys per pour)

Two versions with the same four cavities, plateaus, runners and vents (the keys come out the same):

  resin (default, cheap)  two SLA resin plates printed by JLC3DP (a tool, not a part of the light): cavity half 6.0 and
                          lid 5.0 thick with a ribbed back (rim, ribs under the cavity columns and along the middle,
                          solid round the bolt holes, the pour and the vent holes), two printed alignment pins d4 on
                          the cavity half and slip sockets in the lid (offset: one way only), four M3 x 16 through
                          bolts with washers and nuts - no threads in the resin.  build_resin_cavity_half /
                          build_resin_lid
  aluminium (durable)     two plates of 6061-T6, CNC (JLCCNC; each part at least 30 x 20 x 8 mm so that the instant
                          quote takes it), described below.  build_cavity_half / build_lid

Aluminium version:

  cavity half   four key-shaped pockets with the key face down, so that the bubbles rise away from the visible
                face; the chevron is a groove in the pocket floor; the parting plane is the key's inner face (the
                flange top).  Per cavity a sprue well, a runner and a gate on the near flange end, and a vent groove
                at the far flange end.  Two pressed dowel pins, four M3 tapped holes, a pry slot at each short end.
  lid           forms the inner face: one plateau per cavity makes the recess for the stiffener plate.  Per cavity
                a pour hole (sprue) over the sprue well and a vent hole through the plateau.  Slip holes for the
                dowels, clearance holes for the M3 screws.

The cavity is the key of flashka_housing.build_key_side without its recess, with a draft of P.mould_draft on the
cap and flange walls and the cap set to the middle of the key's outline tolerance (-0.05/-0.15) at every height.
No shrink allowance: PMC-780 DRY shrinks less than 0.001 in./in. (data sheet), about 0.01 mm on the 11 mm key.
The plate and the doubler are glued in after casting (flashka_housing.build_key_stiffener).

Frame: x along the row of cavities, y along the keys' long side, z up; parting plane z = 0, cavity half below,
lid above.  A key point (X, Y, Z) of the housing frame sits at (X - X_next + cavity x, Y - key_y, Z - key top).

usage:  python3 key_mould.py [out_dir]          (default ../../cad)
        writes FlashKa_key_mould.step (both halves closed, dowel pins, screws), FlashKa_key_mould_cavity.step,
        FlashKa_key_mould_lid.step (one per JLCCNC part), FlashKa_key_mould_resin_cavity.stl / _lid.stl (one per
        JLC3DP part, + .step), FlashKa_key_mould_resin.step (closed, with the bolts), _ref_mould_*.stl (pictures)
        and key_mould_checks.json; written into the package's cad folder, the order copies in
        ../../order_files/3_rubber_keys and the checks in ../../docs/checks are refreshed too (order_files.py)
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402

cq = H.cq


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def key_top(p):
    return p.Z_seat + p.flange_t


def to_mould(p, cx):
    """translation housing frame -> mould frame for the key in the cavity at x = cx"""
    return (cx - p.X_next, -p.key_y, -key_top(p))


def cavity_x(p):
    return [(i - (p.mould_n - 1) / 2) * p.mould_pitch for i in range(p.mould_n)]


def rrect_wire(cx, cy, w, h, r, z):
    sk = cq.Sketch().push([(cx, cy)]).rect(w, h).reset().vertices().fillet(min(r, w / 2 - 1e-3, h / 2 - 1e-3))
    return sk._faces.Faces()[0].outerWire().translate(cq.Vector(0, 0, z))


def drafted_prism(cx, cy, w, h, r, z0, z1, off0, tg):
    """rounded-rectangle prism from z0 to z1 whose outline (w x h, corner r) is offset by off0 at z0 and grows by
    tan(draft) = tg per mm of height (a mould wall with draft)"""
    o1 = off0 + (z1 - z0) * tg
    w0 = rrect_wire(cx, cy, w + 2 * off0, h + 2 * off0, r + off0, z0)
    w1 = rrect_wire(cx, cy, w + 2 * o1, h + 2 * o1, r + o1, z1)
    return cq.Workplane().add(cq.Solid.makeLoft([w0, w1], True))


def cavity_solid(p, cx):
    """positive shape of one cavity: the cast key below the parting plane (without its recess), with the draft and
    the cap at the middle of its tolerance, plus 0.5 above the parting plane for a clean cut"""
    sx, sy, sr = p.side_key
    fw = p.flange_side
    zt = key_top(p)
    zf, zface = p.Z_seat - zt, p.side_face_z - zt
    tg = math.tan(math.radians(p.mould_draft))
    flange = drafted_prism(cx, 0.0, sx + 2 * fw, sy + 2 * fw, sr + fw, zf, 0.5, 0.0, tg)
    off_face = p.mould_cap_offset - (zf - zface) * tg
    cap = drafted_prism(cx, 0.0, sx, sy, sr, zface, zf + 0.01, off_face, tg)
    cap = cap.faces("<Z").edges().fillet(0.2)                       # the key face's edge radius
    chev = H.chevron_solid(p, p.X_next, -1).translate(to_mould(p, cx))
    return flange.union(cap).union(chev)


def plateau_solid(p, cx, z_top=0.0):
    """the lid's plateau that forms the plate recess (from the recess floor up to z_top)"""
    rx, ry, rr = p.plate_recess
    z0 = (p.stiff_z0 - p.plate_glue) - key_top(p)
    return H.rrect_z(cx - rx / 2, cx + rx / 2, -ry / 2, ry / 2, z0, z_top, rr)


def sprue_y(p):
    return -(p.side_key[1] / 2 + p.flange_side) - p.mould_runner[2]


def vent_hole_y(p):
    return p.plate_recess[1] / 2 - p.mould_vent_hole[3]


# --------------------------------------------------------------------------
# the two halves
# --------------------------------------------------------------------------
def build_cavity_half(p):
    X, Y = p.mould_size
    tc = p.mould_t[0]
    blk = H.rbox(-X / 2, X / 2, -Y / 2, Y / 2, -tc, 0.0)
    gw, gd, _ = p.mould_runner
    ve_w, ve_d = p.mould_vent
    y_end = p.side_key[1] / 2 + p.flange_side
    ys = sprue_y(p)
    cuts = []
    for cx in cavity_x(p):
        cuts.append(cavity_solid(p, cx))
        cuts.append(H.cyl_z(cx, ys, p.mould_sprue_d, -gd, 0.5))                         # sprue well
        cuts.append(H.rbox(cx - gw / 2, cx + gw / 2, ys, -y_end + 0.3, -gd, 0.5))     # runner + gate
        cuts.append(H.rbox(cx - ve_w / 2, cx + ve_w / 2, y_end - 0.3, Y / 2 + 1.0, -ve_d, 0.5))   # vent groove
    dd, _, dpress = p.mould_dowel
    for (x, y) in p.mould_dowels:
        cuts.append(H.cyl_z(x, y, dd, -dpress, 0.5))                                     # press fit, H7
    tap, tdepth, _, _ = p.mould_m3
    for (x, y) in p.mould_screws:
        cuts.append(H.cyl_z(x, y, tap, -tdepth, 0.5))                                    # M3 tap drill, blind (thread 6 deep)
    pw, pd, preach = p.mould_pry
    for s in (-1, 1):
        x0, x1 = (X / 2 - preach, X / 2 + 1.0) if s > 0 else (-X / 2 - 1.0, -X / 2 + preach)
        cuts.append(H.rbox(x0, x1, -5.0 - pw / 2, -5.0 + pw / 2, -pd, 0.5))
    return H.cut_all(blk, cuts)


def build_lid(p):
    X, Y = p.mould_size
    tl = p.mould_t[1]
    blk = H.rbox(-X / 2, X / 2, -Y / 2, Y / 2, 0.0, tl)
    for cx in cavity_x(p):
        blk = blk.union(plateau_solid(p, cx, 0.01))
    d_small, d_cb, h_small, _ = p.mould_vent_hole
    z_pl = (p.stiff_z0 - p.plate_glue) - key_top(p)
    cuts = []
    for cx in cavity_x(p):
        cuts.append(H.cyl_z(cx, sprue_y(p), p.mould_sprue_d, -0.1, tl + 0.1))              # pour hole
        cuts.append(H.cyl_z(cx, vent_hole_y(p), d_small, z_pl - 0.1, h_small))              # vent through the plateau
        cuts.append(H.cyl_z(cx, vent_hole_y(p), d_cb, h_small, tl + 0.1))                   # its counterbore
    dd = p.mould_dowel[0]
    for (x, y) in p.mould_dowels:
        cuts.append(H.cyl_z(x, y, dd + 0.025, -0.1, tl + 0.1))                             # slip fit 2.02-2.03
    for (x, y) in p.mould_screws:
        cuts.append(H.cyl_z(x, y, p.mould_m3[3], -0.1, tl + 0.1))
    return H.cut_all(blk, cuts)


def _back_pockets(p, z_back, depth, holes, hole_boss):
    """pockets in the back face of a resin plate (z_back = back face, pockets go `depth` into the plate): inside the
    rim, minus a rib under each cavity column and one along the middle, minus a solid boss round every bolt hole and
    round the given holes [(x, y)] or [(x, y, boss d)]"""
    X, Y = p.mould_size
    rim, rib = p.resin_rim, p.resin_rib
    zb0, zb1 = sorted((z_back, z_back - depth if z_back > 0 else z_back + depth))
    pk = H.rbox(-X / 2 + rim, X / 2 - rim, -Y / 2 + rim, Y / 2 - rim, zb0 - 0.01 if z_back < 0 else zb0,
                zb1 + 0.01 if z_back > 0 else zb1, 1.0)
    keep = [H.rbox(cx - rib / 2, cx + rib / 2, -Y, Y, zb0 - 1, zb1 + 1) for cx in cavity_x(p)]
    keep.append(H.rbox(-X, X, -rib / 2, rib / 2, zb0 - 1, zb1 + 1))
    for (x, y) in p.mould_screws:
        keep.append(H.cyl_z(x, y, p.resin_boss, zb0 - 1, zb1 + 1))
    for h in holes:
        keep.append(H.cyl_z(h[0], h[1], h[2] if len(h) > 2 else hole_boss, zb0 - 1, zb1 + 1))
    for k in keep:
        pk = pk.cut(k)
    return pk


def build_resin_cavity_half(p):
    """SLA resin cavity half: the cavities, runners, vent grooves and pry slots of the aluminium one; printed pins
    instead of the dowels, M3 through holes, ribbed back"""
    X, Y = p.mould_size
    tc = p.resin_t[0]
    blk = H.rbox(-X / 2, X / 2, -Y / 2, Y / 2, -tc, 0.0)
    dpin, hpin, cpin, _ = p.resin_pin
    for (x, y) in p.mould_dowels:
        pin = H.cyl_z(x, y, dpin, -0.01, hpin).faces(">Z").edges().chamfer(cpin)
        blk = blk.union(pin)
    gw, gd, _ = p.mould_runner
    ve_w, ve_d = p.mould_vent
    y_end = p.side_key[1] / 2 + p.flange_side
    ys = sprue_y(p)
    cuts = []
    for cx in cavity_x(p):
        cuts.append(cavity_solid(p, cx))
        cuts.append(H.cyl_z(cx, ys, p.mould_sprue_d, -gd, 0.5))
        cuts.append(H.rbox(cx - gw / 2, cx + gw / 2, ys, -y_end + 0.3, -gd, 0.5))
        cuts.append(H.rbox(cx - ve_w / 2, cx + ve_w / 2, y_end - 0.3, Y / 2 + 1.0, -ve_d, 0.5))
    for (x, y) in p.mould_screws:
        cuts.append(H.cyl_z(x, y, p.resin_bolt[0], -tc - 1, 0.5))
    pw, pd, preach = p.mould_pry
    for s_ in (-1, 1):
        x0, x1 = (X / 2 - preach, X / 2 + 1.0) if s_ > 0 else (-X / 2 - 1.0, -X / 2 + preach)
        cuts.append(H.rbox(x0, x1, -5.0 - pw / 2, -5.0 + pw / 2, -pd, 0.5))
    depth = tc - cavity_depth(p) - p.resin_floor
    cuts.append(_back_pockets(p, -tc, depth, [], p.resin_hole_boss))
    return H.cut_all(blk, cuts)


def build_resin_lid(p):
    """SLA resin lid: the plateaus, pour holes and vent holes of the aluminium one; sockets for the printed pins,
    M3 through holes, ribbed back"""
    X, Y = p.mould_size
    tl = p.resin_t[1]
    blk = H.rbox(-X / 2, X / 2, -Y / 2, Y / 2, 0.0, tl)
    for cx in cavity_x(p):
        blk = blk.union(plateau_solid(p, cx, 0.01))
    d_small, d_cb, h_small, _ = p.mould_vent_hole
    z_pl = (p.stiff_z0 - p.plate_glue) - key_top(p)
    cuts, holes = [], []
    for cx in cavity_x(p):
        cuts.append(H.cyl_z(cx, sprue_y(p), p.mould_sprue_d, -0.1, tl + 0.1))
        cuts.append(H.cyl_z(cx, vent_hole_y(p), d_small, z_pl - 0.1, h_small))
        cuts.append(H.cyl_z(cx, vent_hole_y(p), d_cb, h_small, tl + 0.1))
        holes += [(cx, sprue_y(p)), (cx, vent_hole_y(p))]
    for (x, y) in p.mould_dowels:
        cuts.append(H.cyl_z(x, y, p.resin_pin[3], -0.1, tl + 0.1))
        holes.append((x, y, p.resin_boss))
    for (x, y) in p.mould_screws:
        cuts.append(H.cyl_z(x, y, p.resin_bolt[0], -0.1, tl + 0.1))
    cuts.append(_back_pockets(p, tl, tl - p.resin_floor, holes, p.resin_hole_boss))
    return H.cut_all(blk, cuts)


def resin_bought_parts(p):
    """four M3 x 16 socket head screws with washers and nuts, closed resin mould (pictures, assembly STEP)"""
    out = {}
    tl, tc = p.resin_t[1], p.resin_t[0]
    for i, (x, y) in enumerate(p.mould_screws):
        head = H.cyl_z(x, y, 5.5, tl + 0.5, tl + 3.5)
        shank = H.cyl_z(x, y, 3.0, tl + 0.5 - p.resin_bolt[1], tl + 0.51)
        wash = H.cyl_z(x, y, 7.0, tl, tl + 0.5).union(H.cyl_z(x, y, 7.0, -tc - 0.5, -tc)).cut(
            H.cyl_z(x, y, 3.2, -tc - 1, tl + 1))
        nut = (cq.Workplane("XY", origin=(0, 0, -tc - 0.5 - 2.4)).center(x, y).polygon(6, 5.5 / math.cos(math.pi / 6))
               .extrude(2.4)).cut(H.cyl_z(x, y, 3.0, -tc - 4, -tc))
        out["screw%d" % (i + 1)] = head.union(shank).union(wash).union(nut)
    return out


def cavity_depth(p):
    """deepest point of a cavity below the parting plane (the chevron groove floor)"""
    return key_top(p) - (p.side_face_z - p.chevron_h)


def bought_parts(p):
    """dowel pins (pressed into the cavity half) and M3 x 12 socket head screws, closed mould"""
    dd, dl, dpress = p.mould_dowel
    out = {}
    for i, (x, y) in enumerate(p.mould_dowels):
        out["dowel%d" % (i + 1)] = H.cyl_z(x, y, dd, -dpress, dl - dpress)
    tl = p.mould_t[1]
    for i, (x, y) in enumerate(p.mould_screws):
        out["screw%d" % (i + 1)] = H.cyl_z(x, y, 5.5, tl, tl + 3.0).union(H.cyl_z(x, y, 3.0, tl - 12.0, tl + 0.01))
    return out


def cast_key(p, cx=0.0):
    """the key as the mould makes it (cavity below the parting plane minus the plateau), mould frame"""
    X, Y = p.mould_size
    cav = cavity_solid(p, cx).intersect(H.rbox(-X, X, -Y, Y, -10.0, 0.0))
    return cav.cut(plateau_solid(p, cx, 0.5))


def target_key(p, cx=0.0):
    """the key of the model (with its recess) moved into the mould frame"""
    return H.build_key_side(p, p.X_next, -1).translate(to_mould(p, cx))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def release_check(p, half, side, footprints, zmax, eps=0.01, per_face=4):
    """no undercut: every face of the moulding surface must see the opening direction.  side 'cavity': faces between
    the parting plane and zmax below it inside a cavity footprint, ray +Z; side 'lid': faces below the parting plane
    (the plateaus), ray -Z.  A face looking against the opening direction is an undercut by itself."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomLProp import GeomLProp_SLProps
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    shape = H._shape(half).wrapped
    BRepMesh_IncrementalMesh(shape, 0.02, False, 0.3, True)
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    dz = 1.0 if side == "cavity" else -1.0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n_faces = n_pts = 0
    bad = []
    while ex.More():
        f = TopoDS.Face_s(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        tr = loc.Transformation()
        rev = f.Orientation() == TopAbs_REVERSED
        surf = BRep_Tool.Surface_s(f)
        cand = []
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            pa, pb, pc = (tri.Node(k).Transformed(tr) for k in (a, b, c))
            cen = ((pa.X() + pb.X() + pc.X()) / 3, (pa.Y() + pb.Y() + pc.Y()) / 3, (pa.Z() + pb.Z() + pc.Z()) / 3)
            u = (pb.X() - pa.X(), pb.Y() - pa.Y(), pb.Z() - pa.Z())
            v = (pc.X() - pa.X(), pc.Y() - pa.Y(), pc.Z() - pa.Z())
            ar = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 + (u[0] * v[1] - u[1] * v[0]) ** 2)
            cand.append((ar, cen))
        cand.sort(key=lambda t: -t[0])
        cand = [cpt for _, cpt in cand[:per_face]]
        used = False
        for cen in cand:
            if not (-zmax < cen[2] < -1e-3) or not any(abs(cen[0] - fx) < hx and abs(cen[1] - fy) < hy
                                                       for fx, fy, hx, hy in footprints):
                continue
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*cen), surf)
            if pr.NbPoints() == 0:
                continue
            uu, vv = pr.LowerDistanceParameters()
            lp = GeomLProp_SLProps(surf, uu, vv, 1, 1e-7)
            if not lp.IsNormalDefined():
                continue
            q, d = pr.NearestPoint(), lp.Normal()
            sg = -1 if rev else 1
            nrm = (sg * d.X(), sg * d.Y(), sg * d.Z())
            used = True
            n_pts += 1
            if nrm[2] * dz < -1e-3:
                bad.append({"point": [round(q.X(), 3), round(q.Y(), 3), round(q.Z(), 3)], "why": "faces away from the opening"})
                continue
            o = (q.X() + eps * nrm[0], q.Y() + eps * nrm[1], q.Z() + eps * nrm[2])
            inter.Perform(gp_Lin(gp_Pnt(*o), gp_Dir(0, 0, dz)), 0.0, 1e3)
            if inter.NbPnt() > 0:
                bad.append({"point": [round(q.X(), 3), round(q.Y(), 3), round(q.Z(), 3)], "why": "covered"})
        n_faces += used
    return {"faces": n_faces, "points": n_pts, "undercuts": len(bad), "undercut_points": bad[:10]}


def cast_vs_key(p):
    """the cast key against the model's key: volumes, difference, outline at the face and at the flange step"""
    ck, tk = cast_key(p), target_key(p)
    vc, vt = H._shape(ck).Volume(), H._shape(tk).Volume()
    extra = H._shape(ck.cut(tk)).Volume()
    missing = H._shape(tk.cut(ck)).Volume()
    import drawings as D
    R = D.Rays(ck.val())
    zt = key_top(p)
    z_face, z_step = p.side_face_z - zt + 0.25, p.Z_seat - zt - 0.01     # 0.25 above the face: above its R0.2 edge
    sx, sy, _ = p.side_key

    def span(iv):
        return round(iv[-1][1] - iv[0][0], 4) if iv else float("nan")
    out = {"key_volume_mm3": round(vt, 3), "cast_volume_mm3": round(vc, 3),
           "cast_minus_key_mm3": round(extra, 4), "key_minus_cast_mm3": round(missing, 4),
           "cap_width_X": {"near the face": span(R.x(0.0, z_face)), "at the flange step": span(R.x(0.0, z_step)),
                           "tolerance": [round(sx - 0.15, 3), round(sx - 0.05, 3)]},
           "cap_length_Y": {"near the face": span(R.y(0.0, z_face)), "at the flange step": span(R.y(0.0, z_step)),
                            "tolerance": [round(sy - 0.15, 3), round(sy - 0.05, 3)]},
           "flange_length_Y": {"at the flange underside": span(R.y(0.0, p.Z_seat - zt + 0.01)),
                               "at the parting plane": span(R.y(0.0, -0.01)), "nominal": sy + 2 * p.flange_side},
           "recess_depth": round(-((p.stiff_z0 - p.plate_glue) - zt), 4),
           "shrink_allowance": "none: PMC-780 DRY shrinks < %g (data sheet), %.3f mm over the %.1f mm flange" % (
               p.rubber_shrink, p.rubber_shrink * (sy + 2 * p.flange_side), sy + 2 * p.flange_side)}
    tol_ok = all(out[k]["tolerance"][0] <= out[k][w] <= out[k]["tolerance"][1]
                 for k in ("cap_width_X", "cap_length_Y") for w in ("near the face", "at the flange step"))
    out["cap_inside_its_tolerance"] = tol_ok
    return out


def mould_checks(p, cav, lid, resin=False):
    sx, sy, _ = p.side_key
    fp = [(cx, 0.0, (sx + 2 * p.flange_side) / 2 + 0.2, (sy + 2 * p.flange_side) / 2 + 0.2) for cx in cavity_x(p)]
    out = {}
    for n, s in (("cavity half", cav), ("lid", lid)):
        v = H._shape(s)
        bb = v.BoundingBox()
        size = sorted([bb.xlen, bb.ylen, bb.zlen], reverse=True)
        out[n] = {"valid": v.isValid(), "solids": len(v.Solids()), "volume_mm3": round(v.Volume(), 1),
                  "bbox_mm": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)]}
        if resin:
            out[n]["volume_cm3"] = round(v.Volume() / 1000.0, 2)
        else:
            out[n].update({"mass_g": round(v.Volume() * H.DENS["Al"], 1),
                           "jlccnc_minimum_ok": all(a >= b for a, b in zip(size, sorted(p.kit_min, reverse=True))),
                           "two_setup_reach": H.kit_two_setup_check(s)})
    depth = cavity_depth(p)                                          # deepest point of a cavity (chevron groove)
    out["cavity half"]["release (ray +Z from every cavity face)"] = release_check(p, cav, "cavity", fp, depth + 0.1)
    out["lid"]["release (ray -Z from every plateau face)"] = release_check(p, lid, "lid", fp, 1.0)
    out["closed: cavity half x lid overlap_mm3"] = round(H._vol(cav, lid), 4)
    out["cast key vs model key"] = cast_vs_key(p)
    if resin:
        tc, tl = p.resin_t
        pk_c = _back_pockets(p, -tc, tc - cavity_depth(p) - p.resin_floor, [], p.resin_hole_boss)
        out["resin between a cavity and the back pockets (min, measured), mm"] = round(min(
            H._dist(cavity_solid(p, cx), pk_c) for cx in cavity_x(p)), 3)
        holes = [(cx, sprue_y(p)) for cx in cavity_x(p)] + [(cx, vent_hole_y(p)) for cx in cavity_x(p)] + [
            (x, y, p.resin_boss) for x, y in p.mould_dowels]
        pk_l = _back_pockets(p, tl, tl - p.resin_floor, holes, p.resin_hole_boss)
        out["lid: resin round the pour / vent holes and sockets to the back pockets (min, measured), mm"] = round(min(
            [H._dist(H.cyl_z(x, y, p.mould_sprue_d, 0.0, tl), pk_l) for x, y in holes[:len(cavity_x(p))]] +
            [H._dist(H.cyl_z(x, y, p.mould_vent_hole[1], 0.0, tl), pk_l) for x, y in holes[len(cavity_x(p)):2 * len(cavity_x(p))]] +
            [H._dist(H.cyl_z(x, y, p.resin_pin[3], 0.0, tl), pk_l) for x, y in p.mould_dowels] +
            [H._dist(H.cyl_z(x, y, p.resin_bolt[0], 0.0, tl), pk_l) for x, y in p.mould_screws]), 3)
        out["lid: face plate under the back pockets, mm"] = p.resin_floor
        out["back pockets: depth cavity half / lid, mm"] = [round(tc - cavity_depth(p) - p.resin_floor, 3),
                                                            round(tl - p.resin_floor, 3)]
        out["pin d / socket d (slip per side)"] = [p.resin_pin[0], p.resin_pin[3],
                                                   round((p.resin_pin[3] - p.resin_pin[0]) / 2, 3)]
        out["bolts"] = "4 x M3 x %g socket head through both plates (d%g holes), washers + nuts; stack %.1f + %.1f" % (
            p.resin_bolt[1], p.resin_bolt[0], tc, tl)
        out["smallest internal radius"] = "R%g: chevron groove (printed)" % (p.chevron[0] / 2)
        out["ok"] = bool(all(out[n]["valid"] and out[n]["solids"] == 1 for n in ("cavity half", "lid"))
                         and out["cavity half"]["release (ray +Z from every cavity face)"]["undercuts"] == 0
                         and out["lid"]["release (ray -Z from every plateau face)"]["undercuts"] == 0
                         and out["closed: cavity half x lid overlap_mm3"] < 1e-3
                         and out["cast key vs model key"]["cap_inside_its_tolerance"])
        return out
    out["smallest internal radius"] = "R%g: chevron groove (cut with a d%g end mill along its centre line, %g deep)" % (
        p.chevron[0] / 2, p.chevron[0], p.chevron_h)
    out["ok"] = bool(all(out[n]["valid"] and out[n]["solids"] == 1 and out[n]["jlccnc_minimum_ok"]
                         and out[n]["two_setup_reach"]["blocked"] == 0 for n in ("cavity half", "lid"))
                     and out["cavity half"]["release (ray +Z from every cavity face)"]["undercuts"] == 0
                     and out["lid"]["release (ray -Z from every plateau face)"]["undercuts"] == 0
                     and out["closed: cavity half x lid overlap_mm3"] < 1e-3
                     and out["cast key vs model key"]["cap_inside_its_tolerance"])
    return out


# --------------------------------------------------------------------------
def main(out):
    os.makedirs(out, exist_ok=True)
    p = H.P()
    cav, lid = build_cavity_half(p), build_lid(p)
    bp = bought_parts(p)
    H.export_shape(cav, os.path.join(out, "FlashKa_key_mould_cavity"), stl=False)
    H.export_shape(lid, os.path.join(out, "FlashKa_key_mould_lid"), stl=False)
    asm = cq.Assembly(name="FlashKa_key_mould")
    asm.add(cav, name="cavity_half_6061", color=cq.Color(0.75, 0.76, 0.78))
    asm.add(lid, name="lid_6061", color=cq.Color(0.80, 0.81, 0.83))
    for n, s in bp.items():
        asm.add(s, name=("dowel_pin_d2_m6_x8_" if n.startswith("dowel") else "screw_M3x12_ISO4762_") + n[-1],
                color=cq.Color(0.55, 0.56, 0.58))
    asm.export(os.path.join(out, "FlashKa_key_mould.step"), "STEP")
    # pictures: the open mould (lid turned over beside the cavity half), cast keys in two cavities, two keys beside
    H.export_shape(cav, os.path.join(out, "_ref_mould_cavity"), step=False, tol=0.01)
    H.export_shape(lid, os.path.join(out, "_ref_mould_lid"), step=False, tol=0.01)
    H.export_shape(cq.Workplane().add(cq.Compound.makeCompound([s.val() for s in bp.values()])),
                   os.path.join(out, "_ref_mould_bought"), step=False, tol=0.01)
    # resin version (JLC3DP, SLA): STL per part (+ STEP), closed assembly with the bolts, pictures
    rcav, rlid = build_resin_cavity_half(p), build_resin_lid(p)
    rbp = resin_bought_parts(p)
    H.export_shape(rcav, os.path.join(out, "FlashKa_key_mould_resin_cavity"), tol=0.005)
    H.export_shape(rlid, os.path.join(out, "FlashKa_key_mould_resin_lid"), tol=0.005)
    asm = cq.Assembly(name="FlashKa_key_mould_resin")
    asm.add(rcav, name="cavity_half_SLA_resin", color=cq.Color(0.86, 0.86, 0.84))
    asm.add(rlid, name="lid_SLA_resin", color=cq.Color(0.86, 0.86, 0.84))
    for n, s_ in rbp.items():
        asm.add(s_, name="screw_M3x16_washers_nut_" + n[-1], color=cq.Color(0.55, 0.56, 0.58))
    asm.export(os.path.join(out, "FlashKa_key_mould_resin.step"), "STEP")
    H.export_shape(rcav, os.path.join(out, "_ref_mould_resin_cavity"), step=False, tol=0.01)
    H.export_shape(rlid, os.path.join(out, "_ref_mould_resin_lid"), step=False, tol=0.01)
    H.export_shape(cq.Workplane().add(cq.Compound.makeCompound([s_.val() for s_ in rbp.values()])),
                   os.path.join(out, "_ref_mould_resin_bought"), step=False, tol=0.01)
    chk = {"aluminium (JLCCNC, durable)": mould_checks(p, cav, lid),
           "resin (JLC3DP SLA, default)": mould_checks(p, rcav, rlid, resin=True)}
    chk["ok"] = bool(chk["aluminium (JLCCNC, durable)"]["ok"] and chk["resin (JLC3DP SLA, default)"]["ok"])
    with open(os.path.join(out, "key_mould_checks.json"), "w") as f:
        json.dump(chk, f, indent=1, default=str)
    print(json.dumps(chk, indent=1, default=str))
    import order_files                       # copies in order_files/3_rubber_keys and docs/checks: refresh them
    if order_files.is_package_cad(out):
        order_files.copy(("mould",))
    return p, cav, lid, chk


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cad"))
