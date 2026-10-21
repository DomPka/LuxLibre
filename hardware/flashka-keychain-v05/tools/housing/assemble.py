#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference assembly v0.5: housing parts + the real PCB 3D model + bought-part stand-ins, one STEP file.

usage:  python3 assemble.py <cad_dir> <pcb_step> [out_dir] [--kicad-pcb FILE] [--no-check] [--rebuild]

  <cad_dir>    folder written by aurora_housing.py (Aurora_*.step).  A part whose STEP file is missing
               (or all of them with --rebuild) is built from aurora_housing.py instead.
  <pcb_step>   KiCad STEP export of the main PCB: X, Y = housing X, Y (KiCad x = 100 + X, y = 100 - Y),
               Z = 0 on the PCB bottom face; lifted here by P.Z_pcb_bot.
  out_dir      Aurora_assembly_reference.step goes here (default: cad_dir)
  --kicad-pcb  .kicad_pcb of the same board (positions of the L1 / LED3 stand-ins);
               default: the single *.kicad_pcb next to the STEP, if there is one
  --no-check   skip the collision count of the PCB against the housing parts

Contents (all in the housing frame: X = 0 front face, -Y control side, Z = 0 bottom, lid on top):
  tray, lid, RF window insert, button cap, spacer ring, antenna spacer (the housing parts)
  every solid of the PCB STEP as PCB_<designator> (board = PCB_PCB), plus stand-ins for the parts the STEP
  lacks (U4 ESP32 module, J1 USB-C, S1 side switch, L1, LED3 - see fit_pcb.standins)
  2 pouch cells, laser module, glass window, LED board + LED (stand-ins from aurora_housing.build_dummies)
  4 countersunk M1.6 lid screws
The optional laser sleeve (for a 4.6 mm laser module) and the split ring are not part of the assembly.
"""
import argparse
import os
import sys

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aurora_housing as H  # noqa: E402
import fit_pcb  # noqa: E402

BUILDERS = {"Aurora_tray": H.build_tray, "Aurora_lid": H.build_lid, "Aurora_rf_window": H.build_rf_window,
            "Aurora_button_cap": H.build_button_cap, "Aurora_spacer_ring": H.build_spacer_ring,
            "Aurora_antenna_spacer": H.build_antenna_spacer}
HOUSING_COL = {"Aurora_tray": (0.15, 0.15, 0.17), "Aurora_lid": (0.22, 0.22, 0.25),
               "Aurora_rf_window": (0.93, 0.95, 0.98), "Aurora_button_cap": (0.75, 0.75, 0.78),
               "Aurora_spacer_ring": (0.95, 0.95, 0.93), "Aurora_antenna_spacer": (0.95, 0.62, 0.20)}
DUMMY_COL = {"cell1": (0.88, 0.70, 0.30), "cell2": (0.88, 0.70, 0.30), "window": (0.70, 0.85, 1.0),
             "led": (1.0, 0.98, 0.80), "mcpcb": (0.80, 0.50, 0.22), "laser": (0.78, 0.62, 0.32)}


def part_colour(name, model):
    n = (name or "").upper()
    m = model or ""
    if name == "PCB":
        return (0.07, 0.40, 0.19)
    if n in ("S1", "S2") or n.startswith("J") or n in ("U4", "S1"):
        return (0.80, 0.80, 0.83)
    if m.startswith("C_") or (n.startswith("C") and n[1:2].isdigit()):
        return (0.72, 0.56, 0.34)
    if n.startswith("LED"):
        return (0.95, 0.95, 0.85)
    return (0.11, 0.11, 0.12)


def housing_part(cad, name, p, rebuild):
    path = os.path.join(cad, name + ".step")
    if not rebuild and os.path.exists(path):
        return cq.importers.importStep(path), "STEP " + path
    return BUILDERS[name](p), "built from aurora_housing.py"


def lid_screws(p):
    """four countersunk M1.6 screws in the lid (the same solids as _ref_lidscrews.stl in aurora_housing.main)"""
    out = []
    for k, (x, y) in enumerate(((p.screw_x_front, -p.screw_dy), (p.screw_x_front, p.screw_dy),
                                (p.X_screw_back, -p.screw_dy), (p.X_screw_back, p.screw_dy))):
        cone = cq.Solid.makeCone(0.8, 1.5, 0.7, pnt=cq.Vector(x, y, p.H - 0.7))
        shank = cq.Solid.makeCylinder(0.8, 3.3, pnt=cq.Vector(x, y, p.H - 4.0))
        slot = cq.Solid.makeBox(2.4, 0.45, 0.5, pnt=cq.Vector(x - 1.2, y - 0.225, p.H - 0.45))
        slot2 = cq.Solid.makeBox(0.45, 2.4, 0.5, pnt=cq.Vector(x - 0.225, y - 1.2, p.H - 0.45))
        out.append((f"ref_lid_screw_{k + 1}", cone.fuse(shank).cut(slot).cut(slot2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir")
    ap.add_argument("pcb_step")
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    out_dir = a.out_dir or a.cad_dir
    os.makedirs(out_dir, exist_ok=True)
    p = H.P()
    dm = H.build_dummies(p)

    asm = cq.Assembly(name="Aurora_v0.5_reference")
    listing = []
    housing = {}
    for n in BUILDERS:
        wp, src = housing_part(a.cad_dir, n, p, a.rebuild)
        housing[n] = wp.val() if hasattr(wp, "val") else wp
        asm.add(wp, name=n, color=cq.Color(*HOUSING_COL[n]))
        listing.append((n, src))
    items, notes = fit_pcb.pcb_items(a.pcb_step, p, dm, a.kicad_pcb, verbose=True)
    for it in items:
        asm.add(it["solid"], name="PCB_" + it["name"], color=cq.Color(*part_colour(it["name"], it["model"])))
    for n, col in DUMMY_COL.items():
        asm.add(dm[n], name="ref_" + n, color=cq.Color(*col))
    for n, s in lid_screws(p):
        asm.add(s, name=n, color=cq.Color(0.62, 0.64, 0.68))

    path = os.path.join(out_dir, "Aurora_assembly_reference.step")
    asm.export(path)
    bb = cq.Compound.makeCompound([housing["Aurora_tray"]] + [i["solid"] for i in items]).BoundingBox()
    print("assembly written:", path, "(%.1f MB)" % (os.path.getsize(path) / 1e6))
    for n, src in listing:
        print("  %-24s %s" % (n, src))
    n_si = len([i for i in items if i["kind"] == "standin"])
    print("  PCB: %d solids from %s + %d stand-ins; plus cells, laser, window, LED board and 4 lid screws as stand-ins"
          % (len(items) - n_si, os.path.basename(a.pcb_step), n_si))
    print("  tray + PCB bbox: X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (bb.xmin, bb.xmax, bb.ymin, bb.ymax,
                                                                      bb.zmin, bb.zmax))
    if not a.no_check:
        parts = {n: s for n, s in housing.items()}
        for k in ("cell1", "cell2", "laser", "window", "mcpcb", "led"):
            parts[k] = dm[k].val()
        hits = fit_pcb.collisions(items, parts)
        print("PCB centred, collisions above %g mm^3 against the housing parts and stand-ins: %d"
              % (fit_pcb.VOL_TOL, len(hits)))
        for h in hits:
            print("   %s x %s  %.4f mm^3 at X %.2f Y %.2f Z %.2f" % (h[0], h[1], h[2], *h[3]))


if __name__ == "__main__":
    main()
