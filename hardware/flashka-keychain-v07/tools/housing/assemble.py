#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference assembly v0.7: housing parts + the real main board and key board (KiCad STEP exports) + bought-part
stand-ins, one STEP file.

usage:  python3 assemble.py <cad_dir> <pcb_step> [out_dir] [--kb-step FILE] [--kicad-pcb FILE] [--no-check]
                            [--rebuild]

  <cad_dir>    folder written by flashka_housing.py (FlashKa_*.step).  A part whose STEP file is missing
               (or all of them with --rebuild) is built from flashka_housing.py instead.
  <pcb_step>   KiCad STEP export of the main board: X, Y in the PCB frame (housing X - PCB_DX), Z = 0 on its
               bottom face; moved and lifted into place by fit_pcb.pcb_items.
  out_dir      FlashKa_assembly_reference.step goes here (default: cad_dir)
  --kb-step    KiCad STEP export of the key board (Z = 0 on its bottom face, lifted by P.kb_z0); without it the
               key-board stand-in of flashka_housing.py is used
  --kicad-pcb  .kicad_pcb of the main board (position of the L1 stand-in); default: the single *.kicad_pcb next to
               the STEP, if there is one
  --no-check   skip the collision count of both boards against the housing parts

Contents (housing frame: X = 0 front face, -Y control side, Z = 0 bottom, lid on top), installed state:
  tray, lid, POM RF window insert, POM antenna spacer
  keys: clear PMMA main key, two cast rubber side keys (next, previous) each with its glued-in stainless steel stiffener
        (plate + doubler)
  main board: every solid of its STEP as PCB_<designator> (board = PCB_PCB), plus stand-ins for the parts the STEP
  lacks (U4 ESP32 module, J1 USB-C, L1 - see fit_pcb.standins)
  key board: every solid of its STEP as KB_<designator> (board = KB_PCB), the pogo plungers cut at the working
  height (tips on the J6 pads); 2 pan-head M1.6 x 2.5 key-board screws
  hold-down pads (gap pad on the module can, rubber pad at the front boss), the 14500 cell (Vapcell F15, nominal size)
  with its two nickel strips and solder joints and the two foam pads, laser module, the LEDiL LISA3-RS-PIN TIR optic (black PC holder + clear PMMA lens, drawn shape) standing on
  the 10 mm copper LED board with the SST-20 LED (stand-ins from flashka_housing.build_dummies), 4 countersunk
  M1.6 x 6 lid screws, the M1.6 x 5 laser set screw (from the head-block top, under the lid)
The optional laser sleeve and the split ring are not part of the assembly.
"""
import argparse
import os
import sys

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flashka_housing as H  # noqa: E402
import fit_pcb  # noqa: E402

BUILDERS = {
    "FlashKa_tray": H.build_tray,
    "FlashKa_lid": H.build_lid,
    "FlashKa_rf_window": H.build_rf_window,
    "FlashKa_antenna_spacer": H.build_antenna_spacer,
    "FlashKa_key_main": H.build_key_main,
    "FlashKa_key_side": lambda p: H.build_key_side(p, p.X_next, -1),
    "FlashKa_key_stiffener": lambda p: H.build_key_stiffener(p, p.X_next),
    "FlashKa_key_side_prev": lambda p: H.build_key_side(p, p.X_prev, +1),
    "FlashKa_key_stiffener_prev": lambda p: H.build_key_stiffener(p, p.X_prev),
}
BUILD_ONLY = ("FlashKa_key_side_prev", "FlashKa_key_stiffener_prev")      # no STEP files of their own (same parts)
ANOD, POM, PMMA, RUBBER, STEEL = (0.10, 0.10, 0.11), (0.07, 0.07, 0.07), (0.82, 0.93, 0.97), (0.04, 0.04, 0.04), \
    (0.62, 0.64, 0.68)
HOUSING_COL = {"FlashKa_tray": ANOD, "FlashKa_lid": ANOD, "FlashKa_rf_window": POM, "FlashKa_antenna_spacer": POM,
               "FlashKa_key_main": PMMA, "FlashKa_key_side": RUBBER,
               "FlashKa_key_side_prev": RUBBER, "FlashKa_key_stiffener": STEEL, "FlashKa_key_stiffener_prev": STEEL}
DUMMY_COL = {"cell": (0.88, 0.70, 0.30), "cell_strip_front": (0.75, 0.75, 0.77), "cell_strip_rear": (0.75, 0.75, 0.77),
             "cell_joint_front": (0.84, 0.84, 0.82), "cell_joint_rear": (0.84, 0.84, 0.82),
             "cell_pad_top": (0.12, 0.12, 0.13), "cell_pad_end": (0.12, 0.12, 0.13), "optic_holder": (0.05, 0.05, 0.05),
             "optic_lens": (0.80, 0.90, 1.0), "led": (0.95, 0.85, 0.35), "mcpcb": (0.80, 0.50, 0.22),
             "laser": (0.78, 0.62, 0.32)}


def part_colour(name, model):
    n = (name or "").upper()
    m = (model or "").lower()
    if name in ("PCB", "KB_PCB"):
        return (0.07, 0.40, 0.19)
    if "pogo" in m:
        return (0.85, 0.68, 0.25)
    if n.startswith("J") or n in ("S1", "S2", "U4") or n.startswith("SW"):
        return (0.80, 0.80, 0.83)
    if m.startswith("c_") or (n.startswith("C") and n[1:2].isdigit()):
        return (0.72, 0.56, 0.34)
    if n.startswith("LED"):
        return (0.95, 0.95, 0.85)
    return (0.11, 0.11, 0.12)


def housing_part(cad, name, p, rebuild):
    path = os.path.join(cad, name + ".step")
    if not rebuild and name not in BUILD_ONLY and os.path.exists(path):
        return cq.importers.importStep(path), "STEP " + os.path.basename(path)
    return BUILDERS[name](p), "built from flashka_housing.py"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir")
    ap.add_argument("pcb_step")
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument("--kb-step", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    out_dir = a.out_dir or a.cad_dir
    os.makedirs(out_dir, exist_ok=True)
    p = H.P()
    dm = H.build_dummies(p)

    asm = cq.Assembly(name="FlashKa_v0.7_reference")
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
    if a.kb_step:
        kb = fit_pcb.kb_items(a.kb_step, p, verbose=True)
        kb_src = os.path.basename(a.kb_step)
    else:
        kb = [it for it in fit_pcb.kb_standin_items(p) if not it["name"].startswith("kb_screw")]
        kb_src = "stand-in (flashka_housing.build_kb_standin)"
    for it in kb:
        s = fit_pcb.at_working_height(it["solid"], p) if fit_pcb.is_plunger(it["name"], it["solid"], p) else it["solid"]
        it["solid_installed"] = s
        nm = it["name"] if it["name"].startswith("KB_") else "KB_" + it["name"]
        asm.add(s, name=nm, color=cq.Color(*part_colour(it["name"], it["model"])))
    for n, s in H.kb_screws_detail(p):
        asm.add(s, name=n, color=cq.Color(*STEEL))
    asm.add(H.pad_solid(p), name="ref_pad_can", color=cq.Color(0.55, 0.55, 0.58))
    if p.front_boss:
        asm.add(H.pad2_solid(p), name="ref_pad_front", color=cq.Color(0.20, 0.20, 0.20))
    for n, col in DUMMY_COL.items():
        asm.add(dm[n], name="ref_" + n, color=cq.Color(*col))
    for n, s in H.lid_screws(p):
        asm.add(s, name=n, color=cq.Color(*STEEL))
    asm.add(H.laser_set_screw(p), name="ref_laser_set_screw_M1.6x5", color=cq.Color(*STEEL))

    path = os.path.join(out_dir, "FlashKa_assembly_reference.step")
    asm.export(path)
    bb = cq.Compound.makeCompound([housing["FlashKa_tray"]] + [i["solid"] for i in items]).BoundingBox()
    print("assembly written:", path, "(%.1f MB)" % (os.path.getsize(path) / 1e6))
    for n, src in listing:
        print("  %-28s %s" % (n, src))
    n_si = len([i for i in items if i["kind"] == "standin"])
    print("  main board: %d solids from %s + %d stand-ins; key board: %d solids from %s"
          % (len(items) - n_si, os.path.basename(a.pcb_step), n_si, len(kb), kb_src))
    print("  plus 2 key-board screws, 2 hold-down pads, the 14500 cell (strips, joints, pads), laser, TIR optic "
          "(holder + lens), LED board + LED, 4 lid screws and the laser set screw")
    print("  tray + main board bbox: X %.2f..%.2f  Y %.2f..%.2f  Z %.2f..%.2f" % (bb.xmin, bb.xmax, bb.ymin, bb.ymax,
                                                                             bb.zmin, bb.zmax))
    if not a.no_check:
        parts = {n: s for n, s in housing.items()}
        for k in H.CELL_PARTS + ("laser", "optic_holder", "optic_lens", "mcpcb", "led"):
            parts[k] = dm[k].val()
        hits = fit_pcb.collisions(items, parts)
        kb_inst = [{**it, "solid": it["solid_installed"]} for it in kb]
        kb_hits = fit_pcb.collisions(kb_inst, parts)
        both = fit_pcb.collisions([i for i in items], {("KB_" + it["name"]): it["solid_installed"] for it in kb})
        print("collisions above %g mm^3 (installed state): main board x housing %d, key board x housing %d, "
              "main board x key board %d" % (fit_pcb.VOL_TOL, len(hits), len(kb_hits), len(both)))
        for h in hits + kb_hits + both:
            print("   %s x %s  %.4f mm^3 at X %.2f Y %.2f Z %.2f" % (h[0], h[1], h[2], *h[3]))


if __name__ == "__main__":
    main()
