#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the complete FlashKa Keychain v0.6 main-PCB package (run from the repo root):

  python3 tools/kicad/build_all.py            # everything (routing takes ~35 min)
  python3 tools/kicad/build_all.py --no-route  # keep the routed board, redo exports

  kicad/FlashKa.pretty                  project footprints (gen_fp.py)
  kicad/FlashKa_main/                   KiCad 7 project: schematic, routed 4-layer PCB,
                                       design rules (.kicad_pro + .kicad_dru)
  production/gerber/                   Gerber + Excellon files  -> zipped for JLCPCB
  production/FlashKa_main_gerbers.zip   upload this at jlcpcb.com
  production/BOM_JLCPCB.csv            assembly BOM (LCSC part numbers)
  production/CPL_JLCPCB.csv            pick-and-place file (JLC rotation convention)
  production/DRC_report.txt            KiCad DRC of the routed board
  production/FlashKa_main_schematic.pdf
  production/FlashKa_main_assembly_top.pdf / _bottom.pdf   copper, silkscreen and every
                                       designator (Fab layer); the bottom view is mirrored
  production/layer_*.svg               one picture per copper layer
  production/pcb_layers.png            four-layer overview (design log figure 12.2)
  production/wiring_pads.png           the hand-soldered pads by polarity (build guide)
  production/Netlist_main.csv          every net with its pads
  cad/FlashKa_main_pcb.step             PCB 3D model for the housing fit check
  flashka.net                           schematic netlist (checked against flashka_parts.py)
  order_files/1_JLCPCB/                 copies of the gerber zip, BOM and CPL for the order

The PCB placement comes from cad/pcb_placement_sa.json plus the parts whose
position the housing fixes (USB-C, switches, ring LEDs, module, S2, wire pads).
v0.6: the hand-placed clusters and larger parts are in gen_pcb.py (FRONT_CLUSTER,
BUCK_CLUSTER, BIG_PARTS); the 0402 parts go to slots (tools/kicad/slot_placer.py)
and tools/kicad/escape_check.py makes sure no pad is walled in.  The routing is
done by tools/kicad/route.py (grid router: PathFinder negotiation, rip-up rounds, then
window repair, removal of copper islands and an exact clearance audit); KiCad's own DRC
checks the result.

Needs: kiutils, KiCad 7 (pcbnew Python module, kicad-cli), numpy, scipy, matplotlib.
"""
import ast
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import gen_fp  # noqa: E402
import gen_sch  # noqa: E402
import gen_pcb  # noqa: E402
from flashka_parts import COMPONENTS, nets_of  # noqa: E402
from kiutils.symbol import SymbolLib  # noqa: E402

KDIR = os.path.join(ROOT, "kicad")
PDIR = os.path.join(ROOT, "production")
HJ = os.path.join(ROOT, "cad", "housing_interface.json")

# design rules = JLCPCB 4-layer capabilities (2026): 0.09 mm trace/space, via
# 0.2/0.45 mm without surcharge, 0.2 mm copper-to-edge, 0.2 mm via/NPTH to
# copper, 0.2 mm via-to-via, 0.45 mm pad-hole to hole.  The router aims for
# 0.13 mm; the DRC minimum is 0.10 mm.
RULES = {"min_clearance": 0.10, "min_track_width": 0.127, "min_via_diameter": 0.45,
         "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.2,
         "min_hole_clearance": 0.2, "min_hole_to_hole": 0.2,
         "min_copper_edge_clearance": 0.2, "solder_mask_min_width": 0.1}

DRU = """(version 1)
# FlashKa Keychain v0.6 - extra design rules (JLCPCB 4-layer, 2026 capabilities)

(rule "PTH hole to other copper (JLCPCB 0.28 mm)"
  (constraint hole_clearance (min 0.28mm))
  (condition "A.Type == 'Pad' && A.isPlated()"))

(rule "Via hole to plated-pad copper (JLCPCB via to copper 0.2 mm)"
  # the rule above is meant for the plated hole; KiCad also applies it to a via's
  # hole next to the pad's copper, where JLCPCB asks 0.2 mm. The pad hole itself
  # stays >= 0.33 mm from via copper through the 0.45 mm hole-to-hole rule below.
  (constraint hole_clearance (min 0.2mm))
  (condition "A.Type == 'Pad' && A.isPlated() && B.Type == 'Via'"))

(rule "Via to pad hole (JLCPCB pad hole-to-hole 0.45 mm)"
  (constraint hole_to_hole (min 0.45mm))
  (condition "A.Type == 'Via' && B.Type == 'Pad'"))
"""


def pro_file(name, sheet_uuid):
    nc = {"clearance": 0.10, "track_width": 0.13, "via_diameter": 0.45, "via_drill": 0.2,
          "wire_width": 6, "bus_width": 12, "line_style": 0, "microvia_diameter": 0.3,
          "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_width": 0.2,
          "diff_pair_via_gap": 0.25, "schematic_color": "rgba(0, 0, 0, 0.000)",
          "pcb_color": "rgba(0, 0, 0, 0.000)"}
    return {
        "meta": {"filename": name + ".kicad_pro", "version": 1},
        "board": {"design_settings": {"defaults": {"board_outline_line_width": 0.05},
                                      "rules": RULES,
                                      # the standard KiCad libraries are not configured on a
                                      # build machine; the footprints are embedded in the board
                                      "rule_severities": {"lib_footprint_issues": "ignore",
                                                          "lib_footprint_mismatch": "ignore"}}},
        "net_settings": {"classes": [dict(nc, name="Default"),
                                     dict(nc, name="Power", track_width=0.4)],
                         "meta": {"version": 2}, "net_colors": None,
                         "netclass_assignments": None,
                         "netclass_patterns": [{"netclass": "Power", "pattern": p} for p in
                                               ("VBAT", "GND", "VBUS", "SW", "VOUT", "ISNS")]},
        "sheets": [[sheet_uuid, ""]],
        "text_variables": {},
    }


LIBTABLES = (
    '(sym_lib_table\n  (lib (name "FlashKa")(type "KiCad")(uri "${KIPRJMOD}/FlashKa.kicad_sym")'
    '(options "")(descr "FlashKa project symbols"))\n)\n',
    '(fp_lib_table\n  (lib (name "FlashKa")(type "KiCad")(uri "${KIPRJMOD}/FlashKa.pretty")'
    '(options "")(descr "FlashKa project footprints"))\n)\n')

# JLCPCB placement rotation corrections (footprint name regex -> degrees),
# the database KiBot uses for JLC; parts not listed need 0.  The JLC order
# page shows every part on the board - check the pin-1 marks there anyway.
JLC_ROT = [(r"^SOT-23", 180), (r"^TSOT-23", 180), (r"^SOT-353", 180), (r"^SOT-363", 180),
           (r"^SOT-223", 180), (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 180)]


def write_symlib(path):
    lib = SymbolLib(version="20211014", generator="kicad_symbol_editor")
    for s in gen_sch.flashka_symbols().values():
        s.libraryNickname = None
        lib.symbols.append(s)
    lib.to_file(path)


def project_dir(name, sch_uuid):
    d = os.path.join(KDIR, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".kicad_pro"), "w") as f:
        json.dump(pro_file(name, sch_uuid), f, indent=2)
    with open(os.path.join(d, name + ".kicad_dru"), "w") as f:
        f.write(DRU)
    with open(os.path.join(d, "sym-lib-table"), "w") as f:
        f.write(LIBTABLES[0])
    with open(os.path.join(d, "fp-lib-table"), "w") as f:
        f.write(LIBTABLES[1])
    write_symlib(os.path.join(d, "FlashKa.kicad_sym"))
    dst = os.path.join(d, "FlashKa.pretty")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(os.path.join(KDIR, "FlashKa.pretty"), dst)
    return d


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit("failed: " + " ".join(cmd))
    return r.stdout


def refkey(s):
    p = s.rstrip("0123456789")
    return (p, int("0" + s[len(p):]))


def bom(path):
    groups = {}
    for r in COMPONENTS:
        if not r["lcsc"] or r.get("dnp"):
            continue
        k = (r["value"], r["fp"].split(":")[1], r["lcsc"])
        groups.setdefault(k, []).append(r["ref"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Quantity"])
        for (val, fpn, lcsc), refs in sorted(groups.items(), key=lambda kv: refkey(kv[1][0])):
            refs = sorted(refs, key=refkey)
            w.writerow([val, ",".join(refs), fpn, lcsc, len(refs)])
    return groups


def cpl(board_path, path):
    """Pick-and-place file in JLCPCB's format from the routed board."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    comps = {c["ref"]: c for c in COMPONENTS}
    rows = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        c = comps.get(ref)
        if not c or not c.get("lcsc") or c.get("dnp"):
            continue
        name = fp.GetFPID().GetLibItemName().wx_str() if hasattr(fp.GetFPID().GetLibItemName(), "wx_str") \
            else str(fp.GetFPID().GetLibItemName())
        corr = next((a for (pat, a) in JLC_ROT if re.search(pat, name)), 0)
        bottom = fp.GetLayer() == pcbnew.B_Cu
        rot = fp.GetOrientationDegrees()
        rot = ((180 - rot) if bottom else rot) + corr
        # centre of the pads (= JLC's part centre for these packages)
        bb = None
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            pb = p.GetBoundingBox()
            if bb is None:
                bb = pb
            else:
                bb.Merge(pb)
        cx, cy = (pcbnew.ToMM(bb.GetCenter().x), pcbnew.ToMM(bb.GetCenter().y)) if bb else \
            (pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y))
        rows.append([ref, f"{cx:.3f}mm", f"{-cy:.3f}mm", "Bottom" if bottom else "Top",
                     f"{rot % 360:.1f}"])
    rows.sort(key=lambda r: refkey(r[0]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(rows)
    return rows


def drc_summary(report):
    txt = open(report).read()
    errs, warns = {}, {}
    for blk in re.split(r"\n(?=\[)", txt):
        m = re.match(r"\[(\w+)\]", blk)
        if not m:
            continue
        d = errs if "Severity: error" in blk else warns
        d[m.group(1)] = d.get(m.group(1), 0) + 1
    return errs, warns


def board_stats(pcb_path):
    """parts per side, track segments, track length, vias, nets (design-log numbers)"""
    import pcbnew
    brd = pcbnew.LoadBoard(pcb_path)
    fps = list(brd.GetFootprints())
    top = sum(1 for f in fps if f.GetLayer() == pcbnew.F_Cu)
    segs = [t for t in brd.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in brd.GetTracks() if t.GetClass() == "PCB_VIA"]
    length = sum(pcbnew.ToMM(t.GetLength()) for t in segs)
    nets = {str(n) for n in brd.GetNetsByName().keys() if str(n)}
    return {"parts": len(fps), "top": top, "bottom": len(fps) - top, "segments": len(segs),
            "length_mm": round(length), "vias": len(vias), "nets": len(nets)}


# load orders for the finish attempts (route.py FLASHKA_LOAD_SEED); the first one finishes the
# released placement (cad/pcb_placement_sa.json), the others are the fall-back for new placements
FINISH_SEEDS = (3, 0, 1, 2, 4, 5)


def route_board(pcb_path):
    """route.py in steps, each in a fresh process (KiCad 7's zone filler gives a long process
    other fills, and the repair phase decides by the fills): the negotiated routing of the
    bare board (saved next to it as *_run.kicad_pcb), then `route.py --finish`, which loads
    that copper and finishes it (window repair, clean-up, exact clearance audit) - repeated on
    its own result with another load order while problems are left - then the zone fill again."""
    stage = pcb_path.replace(".kicad_pcb", "_run.kicad_pcb")
    bare = pcb_path.replace(".kicad_pcb", "_bare.kicad_pcb")
    shutil.copyfile(pcb_path, bare)
    # the bare copy gets the project's rules too (KiCad reads <board>.kicad_pro next to it)
    pro = pcb_path.replace(".kicad_pcb", ".kicad_pro")
    extra = [bare.replace(".kicad_pcb", ".kicad_pro")]
    shutil.copyfile(pro, extra[0])
    rp = os.path.join(HERE, "route.py")
    tmp = pcb_path.replace(".kicad_pcb", "_try.kicad_pcb")

    def step(cmd, env=None):
        last = ""
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=dict(os.environ, **(env or {})))
        for line in p.stdout:
            if not line.startswith("swig/python"):
                print("  route:", line.rstrip().removeprefix("  route: "), flush=True)
            if line.startswith("written"):
                last = line
        if p.wait():
            raise SystemExit("failed: " + " ".join(cmd))
        return last

    step([sys.executable, rp, bare, stage])
    # finish; while nets or GND pads are left, finish the result again with the copper loaded
    # in another fixed order (FINISH_SEEDS): the repair then takes other paths
    src, res = stage, (["?"], ["?"])
    for attempt, seed in enumerate(FINISH_SEEDS):
        print(f"  route: finish attempt {attempt + 1} (load order {seed})", flush=True)
        fin = step([sys.executable, rp, "--finish", bare, src, tmp], {"FLASHKA_LOAD_SEED": str(seed)})
        m = re.search(r"failed nets: (\[.*?\]) GND off-plane: (\[.*?\])", fin)
        res = (ast.literal_eval(m.group(1)), ast.literal_eval(m.group(2))) if m else (["?"], ["?"])
        shutil.copyfile(tmp, pcb_path)
        src = pcb_path.replace(".kicad_pcb", f"_src{attempt}.kicad_pcb")
        shutil.copyfile(tmp, src)
        extra.append(src)
        if not res[0] and not res[1]:
            break
    step([sys.executable, rp, "--refill", pcb_path])
    for f in [stage, bare, tmp] + extra:
        for g in (f, f.replace(".kicad_pcb", ".kicad_pro"), f.replace(".kicad_pcb", ".kicad_prl")):
            if g != pro and os.path.exists(g):
                os.remove(g)
    return res


def main(do_route=True):
    os.makedirs(PDIR, exist_ok=True)
    gen_fp.write(os.path.join(KDIR, "FlashKa.pretty"))
    d = project_dir("FlashKa_main", gen_sch.sym_uuid("__sheet__"))
    # schematic + netlist check
    sch_path, _, _ = gen_sch.build(d)
    iss = gen_sch.check_layout(sch_path)
    print("schematic label overlaps:", len(iss))
    net = os.path.join(ROOT, "flashka.net")
    run(["kicad-cli", "sch", "export", "netlist", "-o", net, sch_path])
    with open(net) as f:                      # repository-relative source path in the netlist
        txt = f.read().replace(ROOT + os.sep, "")
    txt = re.sub(r'\(date "[^"]*"\)', '(date "")', txt, count=1)   # same file on every build
    with open(net, "w") as f:
        f.write(txt)
    print(run([sys.executable, os.path.join(HERE, "verify_netlist.py"), net]).strip())
    run(["kicad-cli", "sch", "export", "pdf", "-o", os.path.join(PDIR, "FlashKa_main_schematic.pdf"), sch_path])
    # PCB: placement, routing, checks
    pcb_path = os.path.join(d, "FlashKa_main.kicad_pcb")
    if do_route or not os.path.exists(pcb_path):
        pcb_path, top, bottom, moved = gen_pcb.build(d, HJ)
        print("placement: parts moved by the legaliser:", moved or "none")
        plc = {r: [round(x, 3), round(y, 3), rot, "F"] for r, (x, y, rot) in top.items()}
        plc.update({r: [round(x, 3), round(y, 3), rot, "B"] for r, (x, y, rot) in bottom.items()})
        with open(os.path.join(ROOT, "cad", "pcb_placement.json"), "w") as f:
            json.dump(plc, f, indent=1, sort_keys=True)
        failed, gnd_fail = route_board(pcb_path)
        print("routing: incomplete nets", failed, "GND pads off-plane", gnd_fail)
    print(run([sys.executable, os.path.join(HERE, "check_pcb.py"), pcb_path, HJ]).strip().splitlines()[-1])
    import route
    rep = os.path.join(PDIR, "DRC_report.txt")
    route.drc(pcb_path, rep)
    with open(rep) as f:                      # repository-relative path in the report header
        txt = f.read().replace(ROOT + os.sep, "")
    txt = re.sub(r"\*\* Created on [^*]*\*\*\n", "", txt)       # same file on every build
    with open(rep, "w") as f:
        f.write(txt)
    errs, warns = drc_summary(rep)
    print("DRC errors:", errs or "none", " warnings:", warns)
    print("board statistics:", board_stats(pcb_path))
    # fabrication outputs
    gdir = os.path.join(PDIR, "gerber")
    if os.path.exists(gdir):
        shutil.rmtree(gdir)
    os.makedirs(gdir)
    run(["kicad-cli", "pcb", "export", "gerbers", "-o", gdir + "/", "--layers",
         "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
         "--subtract-soldermask", pcb_path])
    run(["kicad-cli", "pcb", "export", "drill", "-o", gdir + "/", "--format", "excellon",
         "--excellon-units", "mm", "--excellon-separate-th", pcb_path])
    zpath = os.path.join(PDIR, "FlashKa_main_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, fn), fn)
    g = bom(os.path.join(PDIR, "BOM_JLCPCB.csv"))
    rows = cpl(pcb_path, os.path.join(PDIR, "CPL_JLCPCB.csv"))
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(PDIR, "FlashKa_main_assembly_top.pdf"),
         "--layers", "F.Cu,F.SilkS,F.Fab,Edge.Cuts", pcb_path])
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(PDIR, "FlashKa_main_assembly_bottom.pdf"),
         "--layers", "B.Cu,B.SilkS,B.Fab,Edge.Cuts", "--mirror", pcb_path])
    for lay in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        run(["kicad-cli", "pcb", "export", "svg", "-o",
             os.path.join(PDIR, f"layer_{lay.replace('.', '_')}.svg"),
             "--layers", f"{lay},Edge.Cuts", "--exclude-drawing-sheet", "--page-size-mode", "2",
             pcb_path])
    # four-layer overview picture (design log figure 12.2)
    run([sys.executable, os.path.join(HERE, "plot_routing.py"), pcb_path, os.path.join(PDIR, "pcb_layers.png")])
    # where the builder solders the wires (build guide, sections 9 and 12)
    run([sys.executable, os.path.join(HERE, "plot_wiring.py"), pcb_path, os.path.join(PDIR, "wiring_pads.png")])
    try:
        run(["kicad-cli", "pcb", "export", "step", "-o", os.path.join(ROOT, "cad", "FlashKa_main_pcb.step"),
             "--subst-models", "--user-origin", "100x100mm", "--force", pcb_path])
    except SystemExit as e:
        print("STEP export failed:", e)
    with open(os.path.join(PDIR, "Netlist_main.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Net", "Nodes (ref.pin)"])
        for n, nodes in sorted(nets_of().items()):
            w.writerow([n, " ".join(f"{r}.{p}" for r, p in nodes)])
    odir = os.path.join(ROOT, "order_files", "1_JLCPCB")
    os.makedirs(odir, exist_ok=True)
    for fn in ("FlashKa_main_gerbers.zip", "BOM_JLCPCB.csv", "CPL_JLCPCB.csv"):
        shutil.copyfile(os.path.join(PDIR, fn), os.path.join(odir, fn))
    print("BOM lines:", len(g), " placed parts:", len(rows), " gerber zip:", zpath)
    return errs


if __name__ == "__main__":
    # the router's repair phase walks sets of net names: a fixed hash seed makes the routed
    # board the same on every run
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    errs = main(do_route="--no-route" not in sys.argv)
    sys.exit(1 if errs else 0)
