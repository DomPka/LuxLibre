#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Build the complete FlashKa Keychain v0.7 electronics package - main PCB, key board and the
JLCPCB panel of both (run from hardware/flashka-keychain-v07):

  python3 tools/kicad/build_all.py            # everything (routing about 10 min)
  python3 tools/kicad/build_all.py --no-route  # keep the routed main PCB, redo the rest (the key
                                              # board is always generated and routed: 12 s)

  kicad/FlashKa.pretty, FlashKa.3dshapes  project footprints (gen_fp.py) and the 3D models KiCad
                                       has none for (models_3d.py: pogo pin, Alps SKRK, 1010 LED)
  kicad/FlashKa_main/                  KiCad 7 project: the schematic of the whole light (main PCB
                                       blocks 1-6, key board block 7), the routed 4-layer main PCB
  kicad/FlashKa_keys/                  KiCad 7 project: the routed key board (gen_keys.py)
  kicad/FlashKa_panel/                 the JLCPCB panel: key board + main PCB + rails (panel_jlc.py)
  production/FlashKa_panel_gerbers.zip upload this at jlcpcb.com (one design, 4 layers, 0.8 mm, ENIG)
  production/BOM_JLCPCB.csv            assembly BOM of the panel (both boards, LCSC part numbers)
  production/CPL_JLCPCB.csv            pick-and-place file of the panel (JLC rotation convention)
  production/BOM_JLCPCB_main.csv, CPL_JLCPCB_main.csv, BOM_JLCPCB_keys.csv, CPL_JLCPCB_keys.csv
                                       each board on its own (for a separate order)
  production/gerber/ + FlashKa_main_gerbers.zip, gerber_keys/ + FlashKa_keys_gerbers.zip,
  production/gerber_panel/             Gerber + Excellon files of each board and of the panel
  production/DRC_report.txt, DRC_report_keys.txt, DRC_report_panel.txt   KiCad DRC
  production/FlashKa_schematic.pdf     the schematic (one sheet, both boards)
  production/FlashKa_main_assembly_top.pdf / _bottom.pdf, FlashKa_keys_assembly_top.pdf /
                                       _bottom.pdf  copper, silkscreen and every designator (Fab
                                       layer); the bottom views are mirrored
  production/layer_*.svg, layer_keys_*.svg   one picture per copper layer
  production/pcb_layers.png, pcb_layers_keys.png, panel.png   overview pictures
  production/wiring_pads.png           the hand-soldered pads by polarity (build guide)
  production/Netlist_main.csv, Netlist_keys.csv   every net of each board with its pads
  cad/FlashKa_main_pcb.step, FlashKa_keys_pcb.step   board 3D models for the housing fit check
                                       (X, Y = housing frame, Z = 0 at the board's bottom face)
  cad/pcb_placement.json, pcb_placement_keys.json   part positions (housing X, Y, rotation, side)
  flashka.net                          schematic netlist (checked against flashka_parts.py)
  docs/checks/netlist_v07.txt          main PCB + key board through J6 / P1-P6 = v0.6 netlist
  order_files/1_JLCPCB/                the panel gerber zip, BOM and CPL for the order

v0.7: the buttons, ring LEDs and their resistors moved to the key board (gen_keys.py), the main
board keeps every other part at its v0.6 position (gen_pcb.PLACEMENT_V06) and gets the target
pads J6.  v0.7 (1000 lm power stage): the new power stage (TPS62095 buck, DW01A/SE8830A cell protection,
3.5 A copper) takes the front half of the main board (gen_pcb.PLACEMENT_POWER); the main board is
routed from scratch by `route.py --full` (pre-routes of the buck and LED/VBAT paths, negotiated
route, window repair, clean-up and the exact clearance audit), followed by `route.py --finish`
attempts while problems are left.  The key board is routed by `route.py --keys` (full run).
The v0.6 placement tools (annealing, slots, legaliser) stay in hardware/flashka-keychain-v06.

Needs: kiutils, KiCad 7 (pcbnew Python module, kicad-cli), numpy, scipy, matplotlib, shapely,
cadquery, KiKit 1.5 (the release for KiCad 7).
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
import gen_keys  # noqa: E402
import models_3d  # noqa: E402
from flashka_parts import COMPONENTS, nets_of, on_board  # noqa: E402
from kiutils.symbol import SymbolLib  # noqa: E402

KDIR = os.path.join(ROOT, "kicad")
PDIR = os.path.join(ROOT, "production")
HJ = os.path.join(ROOT, "cad", "housing_interface.json")
# released v0.6 routing: the copper the v0.7 main board is finished from
V06_NET = os.path.join(ROOT, "..", "flashka-keychain-v06", "flashka.net")

# design rules = JLCPCB 4-layer capabilities (2026): 0.09 mm trace/space, via
# 0.2/0.45 mm without surcharge, 0.2 mm copper-to-edge, 0.2 mm via/NPTH to
# copper, 0.2 mm via-to-via, 0.45 mm pad-hole to hole.  The router aims for
# 0.13 mm; the DRC minimum is 0.10 mm.  Both boards and the panel use them.
RULES = {"min_clearance": 0.10, "min_track_width": 0.127, "min_via_diameter": 0.45,
         "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.2,
         "min_hole_clearance": 0.2, "min_hole_to_hole": 0.2,
         "min_copper_edge_clearance": 0.2, "solder_mask_min_width": 0.1}

DRU = """(version 1)
# FlashKa Keychain v0.7 - extra design rules (JLCPCB 4-layer, 2026 capabilities)

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
        # the key board has no schematic of its own: block 7 of FlashKa_main.kicad_sch
        "sheets": [[sheet_uuid, ""]] if sheet_uuid else [],
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
           (r"^SOT-223", 180), (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 180),
           (r"^VQFN-", 270)]       # v0.7: U2 TPS62095 (QFN pin 1 rotated in JLCPCB's library)


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
    for lib in ("FlashKa.pretty", "FlashKa.3dshapes"):
        dst = os.path.join(d, lib)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(KDIR, lib), dst)
    return d


def run(cmd, cwd=None, env=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit("failed: " + " ".join(cmd))
    return r.stdout


def refkey(s):
    p = s.rstrip("0123456789")
    return (p, int("0" + s[len(p):]))


def bom(path, components):
    groups = {}
    for r in components:
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
    """Pick-and-place file in JLCPCB's format from a routed board (or the panel)."""
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
    m = re.search(r"\*\* Found (\d+) unconnected pads \*\*", txt)
    unconnected = int(m.group(1)) if m else -1
    return errs, warns, unconnected


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


# load orders for the finish attempts (route.py FLASHKA_LOAD_SEED) that follow the full route of
# the main board while problems are left
FINISH_SEEDS = (3, 0, 1, 2, 4, 5)
# v0.7 (1000 lm power stage): router settings of the main board's full route (route.py --full;
# empty = defaults)
ROUTE_ENV = {}


def _router_step(cmd, env=None):
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


def _result(line):
    m = re.search(r"failed nets: (\[.*?\]) GND off-plane: (\[.*?\])", line)
    return (ast.literal_eval(m.group(1)), ast.literal_eval(m.group(2))) if m else (["?"], ["?"])


def _cleanup(files, keep):
    for f in files:
        for g in (f, f.replace(".kicad_pcb", ".kicad_pro"), f.replace(".kicad_pcb", ".kicad_prl")):
            if g not in keep and os.path.exists(g):
                os.remove(g)


def route_main(pcb_path):
    """v0.7 (1000 lm power stage): the power stage (TPS62095, cell protection, 3.5 A copper)
    rebuilt the front half of the board, so the v0.6 copper is no longer a useful start.
    `route.py --full` routes the bare board: the hand-made pre-routes of the buck escapes, the
    LED+ and VBAT paths and the pins beside the USB-C receptacle, the negotiated route of every
    other net, then the window repair, clean-up and exact clearance audit of finalize().  While
    problems are left, `route.py --finish` repeats the window repair on its own result with other
    load orders.
    Each step runs in a fresh process (KiCad 7's zone filler gives a long process other fills)."""
    bare = pcb_path.replace(".kicad_pcb", "_bare.kicad_pcb")
    shutil.copyfile(pcb_path, bare)
    pro = pcb_path.replace(".kicad_pcb", ".kicad_pro")
    extra = [bare.replace(".kicad_pcb", ".kicad_pro")]
    shutil.copyfile(pro, extra[0])     # the bare copy gets the project's rules too
    rp = os.path.join(HERE, "route.py")
    tmp = pcb_path.replace(".kicad_pcb", "_try.kicad_pcb")
    stage = pcb_path.replace(".kicad_pcb", "_run.kicad_pcb")
    extra.append(stage)

    def finish(src):
        res = (["?"], ["?"])
        for attempt, seed in enumerate(FINISH_SEEDS):
            print(f"  route: finish attempt {attempt + 1} (load order {seed})", flush=True)
            res = _result(_router_step([sys.executable, rp, "--finish", bare, src, tmp],
                                       {"FLASHKA_LOAD_SEED": str(seed)}))
            shutil.copyfile(tmp, pcb_path)
            src = pcb_path.replace(".kicad_pcb", f"_src{attempt}.kicad_pcb")
            shutil.copyfile(tmp, src)
            extra.append(src)
            if not res[0] and not res[1]:
                break
        return res
    res = _result(_router_step([sys.executable, rp, "--full", bare, stage], ROUTE_ENV))
    shutil.copyfile(stage, pcb_path)
    if res[0] or res[1]:
        print("  route: problems left after the full route: finish attempts", flush=True)
        res = finish(stage)
    _router_step([sys.executable, rp, "--refill", pcb_path])
    _cleanup([bare, tmp] + extra, {pro})
    return res


def route_keys(pcb_path):
    """the key board: full run of route.py (In1 stays a solid GND plane), finalize, refill"""
    bare = pcb_path.replace(".kicad_pcb", "_bare.kicad_pcb")
    shutil.copyfile(pcb_path, bare)
    pro = pcb_path.replace(".kicad_pcb", ".kicad_pro")
    shutil.copyfile(pro, bare.replace(".kicad_pcb", ".kicad_pro"))
    rp = os.path.join(HERE, "route.py")
    tmp = pcb_path.replace(".kicad_pcb", "_try.kicad_pcb")
    res = _result(_router_step([sys.executable, rp, "--keys", bare, tmp], {"FLASHKA_IN1": ""}))
    shutil.copyfile(tmp, pcb_path)
    _router_step([sys.executable, rp, "--refill", pcb_path])
    _cleanup([bare, tmp], {pro})
    return res


def drc_report(pcb_path, name):
    import route
    rep = os.path.join(PDIR, name)
    route.drc(pcb_path, rep)
    with open(rep) as f:                      # repository-relative path in the report header
        txt = f.read().replace(ROOT + os.sep, "")
    txt = re.sub(r"\*\* Created on [^*]*\*\*\n", "", txt)       # same file on every build
    with open(rep, "w") as f:
        f.write(txt)
    return drc_summary(rep)


def gerbers(pcb_path, gdir, zpath):
    if os.path.exists(gdir):
        shutil.rmtree(gdir)
    os.makedirs(gdir)
    run(["kicad-cli", "pcb", "export", "gerbers", "-o", gdir + "/", "--layers",
         "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
         "--subtract-soldermask", pcb_path])
    run(["kicad-cli", "pcb", "export", "drill", "-o", gdir + "/", "--format", "excellon",
         "--excellon-units", "mm", "--excellon-separate-th", pcb_path])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, fn), fn)


def drawings(pcb_path, stem, suffix=""):
    """assembly PDFs (top, mirrored bottom) and one SVG per copper layer"""
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(PDIR, f"{stem}_assembly_top.pdf"),
         "--layers", "F.Cu,F.SilkS,F.Fab,Edge.Cuts", pcb_path])
    run(["kicad-cli", "pcb", "export", "pdf", "-o", os.path.join(PDIR, f"{stem}_assembly_bottom.pdf"),
         "--layers", "B.Cu,B.SilkS,B.Fab,Edge.Cuts", "--mirror", pcb_path])
    for lay in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        svg = os.path.join(PDIR, f"layer{suffix}_{lay.replace('.', '_')}.svg")
        run(["kicad-cli", "pcb", "export", "svg", "-o", svg,
             "--layers", f"{lay},Edge.Cuts", "--exclude-drawing-sheet", "--page-size-mode", "2",
             pcb_path])
        with open(svg) as f:                  # the published wording of the SVG description
            txt = f.read()
        with open(svg, "w") as f:
            f.write(re.sub(r"<desc>Image\s+generated\s+by\s+PCBNEW\s*</desc>",
                           "<desc>Image made with PCBNEW (KiCad) </desc>", txt))


def step_model(pcb_path, out):
    try:
        run(["kicad-cli", "pcb", "export", "step", "-o", out, "--subst-models", "--user-origin",
             "100x100mm", "--force", pcb_path])
    except SystemExit as e:
        print("STEP export failed:", e)


def netlist_csv(path, components):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Net", "Nodes (ref.pin)"])
        for n, nodes in sorted(nets_of(components).items()):
            w.writerow([n, " ".join(f"{r}.{p}" for r, p in nodes)])


def placement_json(path, plc):
    with open(path, "w") as f:
        json.dump({r: [round(x, 3), round(y, 3), rot, s] for r, (x, y, rot, s) in plc.items()},
                  f, indent=1, sort_keys=True)


# v0.6 outputs that no longer apply in v0.7 (replaced by the panel / renamed)
STALE = ("production/FlashKa_main_schematic.pdf", "order_files/1_JLCPCB/FlashKa_main_gerbers.zip",
         "cad/pcb_placement_sa.json")


def main(do_route=True):
    os.makedirs(PDIR, exist_ok=True)
    gen_fp.write(os.path.join(KDIR, "FlashKa.pretty"))
    models_3d.write(os.path.join(KDIR, "FlashKa.3dshapes"))
    d = project_dir("FlashKa_main", gen_sch.sym_uuid("__sheet__"))
    dk = project_dir("FlashKa_keys", None)
    # schematic of the whole light + netlist check
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
    run(["kicad-cli", "sch", "export", "pdf", "-o", os.path.join(PDIR, "FlashKa_schematic.pdf"), sch_path])
    errors = {}
    # main PCB: v0.6 placement + J6 + the 1000 lm power stage, full route
    pcb_path = os.path.join(d, "FlashKa_main.kicad_pcb")
    if do_route or not os.path.exists(pcb_path):
        gen_pcb.build(d, HJ)
        failed, gnd_fail = route_main(pcb_path)
        print("main PCB routing: incomplete nets", failed, "GND pads off-plane", gnd_fail)
    placement_json(os.path.join(ROOT, "cad", "pcb_placement.json"), gen_pcb.main_placement())
    print(run([sys.executable, os.path.join(HERE, "check_pcb.py"), pcb_path, HJ]).strip().splitlines()[-1])
    e, w, u = drc_report(pcb_path, "DRC_report.txt")
    print("main PCB DRC errors:", e or "none", " unconnected:", u, " warnings:", w)
    errors["main"] = (e, u)
    print("main PCB statistics:", board_stats(pcb_path))
    # key board
    kpcb = os.path.join(dk, "FlashKa_keys.kicad_pcb")
    gen_keys.build(dk)
    failed, gnd_fail = route_keys(kpcb)
    print("key board routing: incomplete nets", failed, "GND pads off-plane", gnd_fail)
    placement_json(os.path.join(ROOT, "cad", "pcb_placement_keys.json"), gen_keys.placement())
    print(run([sys.executable, os.path.join(HERE, "check_pcb.py"), kpcb, "--keys"]).strip().splitlines()[-1])
    e, w, u = drc_report(kpcb, "DRC_report_keys.txt")
    print("key board DRC errors:", e or "none", " unconnected:", u, " warnings:", w)
    errors["keys"] = (e, u)
    print("key board statistics:", board_stats(kpcb))
    # the JLCPCB panel (KiKit in its own process), zones filled again in a fresh one
    pdir = os.path.join(KDIR, "FlashKa_panel")
    os.makedirs(pdir, exist_ok=True)
    for lib in ("FlashKa.pretty", "FlashKa.3dshapes"):
        dst = os.path.join(pdir, lib)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(KDIR, lib), dst)
    ppcb = os.path.join(pdir, "FlashKa_panel.kicad_pcb")
    print(run([sys.executable, os.path.join(HERE, "panel_jlc.py"), pcb_path, kpcb, ppcb]).strip().splitlines()[-1])
    run([sys.executable, os.path.join(HERE, "route.py"), "--refill", ppcb])
    e, w, u = drc_report(ppcb, "DRC_report_panel.txt")
    print("panel DRC errors:", e or "none", " unconnected:", u, " warnings:", w)
    errors["panel"] = (e, u)
    # fabrication outputs
    gerbers(pcb_path, os.path.join(PDIR, "gerber"), os.path.join(PDIR, "FlashKa_main_gerbers.zip"))
    gerbers(kpcb, os.path.join(PDIR, "gerber_keys"), os.path.join(PDIR, "FlashKa_keys_gerbers.zip"))
    gerbers(ppcb, os.path.join(PDIR, "gerber_panel"), os.path.join(PDIR, "FlashKa_panel_gerbers.zip"))
    g_panel = bom(os.path.join(PDIR, "BOM_JLCPCB.csv"), COMPONENTS)
    rows_panel = cpl(ppcb, os.path.join(PDIR, "CPL_JLCPCB.csv"))
    bom(os.path.join(PDIR, "BOM_JLCPCB_main.csv"), on_board("main"))
    bom(os.path.join(PDIR, "BOM_JLCPCB_keys.csv"), on_board("keys"))
    cpl(pcb_path, os.path.join(PDIR, "CPL_JLCPCB_main.csv"))
    cpl(kpcb, os.path.join(PDIR, "CPL_JLCPCB_keys.csv"))
    drawings(pcb_path, "FlashKa_main")
    drawings(kpcb, "FlashKa_keys", "_keys")
    # overview pictures (design log), builder picture of the wire pads
    run([sys.executable, os.path.join(HERE, "plot_routing.py"), pcb_path, os.path.join(PDIR, "pcb_layers.png")])
    run([sys.executable, os.path.join(HERE, "plot_routing.py"), kpcb, os.path.join(PDIR, "pcb_layers_keys.png")])
    run([sys.executable, os.path.join(HERE, "plot_routing.py"), ppcb, os.path.join(PDIR, "panel.png")])
    run([sys.executable, os.path.join(HERE, "plot_wiring.py"), pcb_path, os.path.join(PDIR, "wiring_pads.png")])
    step_model(pcb_path, os.path.join(ROOT, "cad", "FlashKa_main_pcb.step"))
    step_model(kpcb, os.path.join(ROOT, "cad", "FlashKa_keys_pcb.step"))
    netlist_csv(os.path.join(PDIR, "Netlist_main.csv"), on_board("main"))
    netlist_csv(os.path.join(PDIR, "Netlist_keys.csv"), on_board("keys"))
    # the two boards together against the v0.6 netlist
    ok = subprocess.run([sys.executable, os.path.join(HERE, "verify_v07.py"), pcb_path, kpcb, V06_NET, net,
                         os.path.join(ROOT, "docs", "checks", "netlist_v07.txt")],
                        capture_output=True, text=True)
    print(next((l for l in ok.stdout.splitlines() if l.startswith("RESULT")), "netlist check failed:\n" + ok.stdout + ok.stderr))
    odir = os.path.join(ROOT, "order_files", "1_JLCPCB")
    os.makedirs(odir, exist_ok=True)
    for fn in ("FlashKa_panel_gerbers.zip", "BOM_JLCPCB.csv", "CPL_JLCPCB.csv"):
        shutil.copyfile(os.path.join(PDIR, fn), os.path.join(odir, fn))
    for fn in STALE:
        if os.path.exists(os.path.join(ROOT, fn)):
            os.remove(os.path.join(ROOT, fn))
    print("panel BOM lines:", len(g_panel), " placed parts:", len(rows_panel),
          " gerber zip:", os.path.join(PDIR, "FlashKa_panel_gerbers.zip").replace(ROOT + os.sep, ""))
    bad = {k: v for k, v in errors.items() if v[0] or v[1]}
    if ok.returncode:
        bad["netlist"] = "FAIL"
    return bad


if __name__ == "__main__":
    # the router's repair phase walks sets of net names: a fixed hash seed makes the routed
    # board the same on every run
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    bad = main(do_route="--no-route" not in sys.argv)
    if bad:
        print("PROBLEMS:", bad)
    sys.exit(1 if bad else 0)
