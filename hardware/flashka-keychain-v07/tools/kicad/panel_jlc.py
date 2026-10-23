#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - the JLCPCB panel: main PCB + key board in one design (KiKit).

  python3 tools/kicad/panel_jlc.py kicad/FlashKa_main/FlashKa_main.kicad_pcb \
          kicad/FlashKa_keys/FlashKa_keys.kicad_pcb kicad/FlashKa_panel/FlashKa_panel.kicad_pcb

Why one panel (docs/ch14, order_files/1_JLCPCB): both boards have parts on both faces, so each
needs JLCPCB Standard PCBA (set-up fee and stencil per side).  In one panel they share one
order, one set-up per side and one stencil per side; the key board gets the main board's
4-layer 0.8 mm ENIG stack-up (In1 GND plane); the panel stays below 50 x 50 mm.

Layout (KiCad coordinates; the main PCB keeps its own coordinates, so its CPL positions equal
the board file):
  key board left, main PCB right, 2.0 mm routed gap between them and to the rails.  The main
  PCB's rear edge (ESP32 antenna, which overhangs the board by 5.6 mm) is the panel's right edge,
  so nothing of the panel sits under the antenna.
  rails 6 mm on top and bottom (JLCPCB Standard PCBA: edge rails >= 5 mm), three fiducials
  (d1.0 copper, d2.0 mask opening, both faces, 4.4 mm from the panel edge: opening >= 3.35 mm
  from the edge) and four d1.152 tooling holes on the rails.
  tabs 4 mm wide (JLCPCB breakaway tab >= 4 mm), two per long edge of each board, placed clear of
  the S2 knob (main +Y edge), the USB-C opening (main -Y edge) and the key board's screw bosses;
  mouse bites d0.5 at 0.8 mm pitch, centred 0.3 mm outside the board edge (no hole touches the
  boards' edge copper; file the 0.3 mm nubs flush after breaking out).
"""
import os
import sys

sys.path.append("/usr/lib/python3/dist-packages")      # KiCad 7 pcbnew (Debian)
import pcbnew  # noqa: E402
from kikit import panelize  # noqa: E402
from kikit.annotations import TabAnnotation  # noqa: E402
from kikit.panelize_ui_impl import polygonToSubstrate  # noqa: E402


def mm(v):
    """mm -> KiCad internal units (nm)"""
    return int(round(v * 1e6))
from shapely.geometry import box  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flashka_parts import KB  # noqa: E402

GAP = 2.0           # routed gap board-board and board-rail
RAIL = 6.0          # rail width (top and bottom)
TAB_W = 4.0
# tab centres along the long edges, housing X (the boards' own frame)
TABS_MAIN = {"top": (21.0, 28.0), "bottom": (23.5, 29.5)}       # S2 knob X ~14, USB-C X 9.3-19.9
TABS_KEYS = {"top": (18.0, 28.0), "bottom": (18.0, 28.0)}       # screw bosses at X 22.9
MAIN_OUTLINE_X = (8.8, 32.8)
MAIN_OUTLINE_Y = (-8.25, 8.25)


def build(main_pcb, keys_pcb, out_pcb):
    os.makedirs(os.path.dirname(os.path.abspath(out_pcb)), exist_ok=True)
    pcbnew.KIID.SeedGenerator(42)            # same item UUIDs on every build
    panel = panelize.Panel(out_pcb)
    src = pcbnew.LoadBoard(main_pcb)
    panel.inheritDesignSettings(src)
    panel.inheritProperties(src)
    panel.inheritTitleBlock(src)
    panel.inheritLayerNames(src)
    rename = lambda n, name: f"Board_{n}-{name}"     # the two boards' nets stay apart
    keep_ref = lambda n, ref: ref                     # designators are unique across both boards
    # main PCB at its own coordinates, key board to the left of it
    mx0, mx1 = MAIN_OUTLINE_X
    main_c = pcbnew.VECTOR2I(mm(100 + (mx0 + mx1) / 2), mm(100.0))
    kx0, ky0, kx1, ky1 = KB["outline"]
    kb_w = kx1 - kx0
    kb_right = 100 + mx0 - GAP
    kb_c = pcbnew.VECTOR2I(mm(kb_right - kb_w / 2), mm(100.0))
    # the key board's design rules are the main board's (same .kicad_dru): taken once, from the main
    panel.appendBoard(keys_pcb, kb_c, origin=panelize.Origin.Center, tolerance=mm(1),
                      netRenamer=rename, refRenamer=keep_ref, inheritDrc=False)
    panel.appendBoard(main_pcb, main_c, origin=panelize.Origin.Center, tolerance=mm(7),
                      netRenamer=rename, refRenamer=keep_ref)
    kb_sub, main_sub = panel.substrates[0], panel.substrates[1]
    # ghost rails for the partition line (where the rails will be)
    minx = min(s.bounds()[0] for s in panel.substrates)
    maxx = max(s.bounds()[2] for s in panel.substrates)
    miny = min(s.bounds()[1] for s in panel.substrates)
    maxy = max(s.bounds()[3] for s in panel.substrates)
    ghosts = [polygonToSubstrate(box(minx, miny - 2 * mm(GAP) - mm(1), maxx, miny - 2 * mm(GAP))),
              polygonToSubstrate(box(minx, maxy + 2 * mm(GAP), maxx, maxy + 2 * mm(GAP) + mm(1)))]
    panel.buildPartitionLineFromBB(ghosts)
    panel.clearTabsAnnotations()

    def tabs(sub, xs_top, xs_bottom, x_shift):
        b = sub.bounds()
        for X in xs_top:              # top edge = small KiCad y; direction into the board
            sub.annotations.append(TabAnnotation(None, (mm(100 + X + x_shift), b[1]), [0, 1], mm(TAB_W)))
        for X in xs_bottom:
            sub.annotations.append(TabAnnotation(None, (mm(100 + X + x_shift), b[3]), [0, -1], mm(TAB_W)))
    kb_shift = (kb_right - kb_w / 2) - (100 + (kx0 + kx1) / 2)      # key board moved by this in x
    tabs(kb_sub, TABS_KEYS["top"], TABS_KEYS["bottom"], kb_shift)
    tabs(main_sub, TABS_MAIN["top"], TABS_MAIN["bottom"], 0.0)
    cuts = panel.buildTabsFromAnnotations(fillet=0)
    panel.makeRailsTb(mm(RAIL))          # attached at the main PCB's tab ends (GAP from the board)
    # the key board (14.8 mm high, main 16.5 mm) ends its tabs halfway to the rails: extend them,
    # 0.5 mm into the rails, so that the key board hangs on the rails like the main PCB
    rail_top = main_sub.bounds()[1] - mm(GAP)
    rail_bottom = main_sub.bounds()[3] + mm(GAP)
    kb_b = kb_sub.bounds()
    for X in TABS_KEYS["top"]:
        xc = mm(100 + X + kb_shift)
        panel.appendSubstrate(box(xc - mm(TAB_W / 2), rail_top - mm(0.5), xc + mm(TAB_W / 2), kb_b[1] + mm(0.05)))
    for X in TABS_KEYS["bottom"]:
        xc = mm(100 + X + kb_shift)
        panel.appendSubstrate(box(xc - mm(TAB_W / 2), kb_b[3] - mm(0.05), xc + mm(TAB_W / 2), rail_bottom + mm(0.5)))
    panel.addCornerTooling(4, mm(3.0), mm(3.0), mm(1.152))
    panel.addCornerFiducials(3, mm(7.0), mm(4.4), mm(1.0), mm(2.0))
    x0, y0, x1, y1 = [int(v) for v in panel.panelBBox()]
    panel.addText("FlashKa v0.7  LuxLibre", pcbnew.VECTOR2I((x0 + x1) // 2, y0 + mm(RAIL / 2)),
                  width=mm(1.0), height=mm(1.0), thickness=mm(0.18))      # JLCPCB legend minimum
    panel.makeMouseBites(cuts, mm(0.5), mm(0.8), offset=mm(-0.3), prolongation=mm(0.0))
    panel.save(reconstructArcs=False, refillAllZones=True)
    w, h = pcbnew.ToMM(x1 - x0), pcbnew.ToMM(y1 - y0)
    return out_pcb, (round(w, 2), round(h, 2)), list(getattr(panel, "errors", []))


if __name__ == "__main__":
    p, size, errs = build(sys.argv[1], sys.argv[2], sys.argv[3])
    print("wrote", p, "panel %.2f x %.2f mm" % size, "errors:", errs or "none")
