FlashKa Keychain v0.6 - JLCCNC order (housing). Same base name for each STEP and PDF.

Part                 Files                                   Material / finish                                  Qty per light
FlashKa_tray         FlashKa_tray.step + .pdf (2 sheets)     6061-T6, bead blast, black anodise type II 8-12 um,  1
                                                             laser marking (artwork below)
FlashKa_lid          FlashKa_lid.step + .pdf                 same as the tray                                     1
FlashKa_cap_main     FlashKa_cap_main.step + .pdf            SUS304, turned, bead blast, no coating              1 (+1 spare)
FlashKa_cap_slide    FlashKa_cap_slide.step + .pdf           SUS304, turned, bead blast, no coating              2 (+1 spare)

Laser marking (tray and lid, after anodising; layer MARK = laser, layer REF = outline, do not mark):
  FlashKa_marking_lid_class2.dxf  (or _class3R.dxf: only if the laser module is class 3R)   lid, seen from above
  FlashKa_marking_bottom.dxf      bottom face of the tray, seen from below
  FlashKa_marking_minus_y.dxf     -Y side (USB-C side)
  FlashKa_marking_plus_y.dxf      +Y side (S2 slot side)
Use a class 2 laser module only (LuxLibre design rule LAS-1). The seams (V grooves, 0.25 deep) are in the STEP files.

The caps are very small (head dia 3.4 and 5.8 mm). The JLCCNC instant quote may refuse them by size: check the quote.
If it does, any CNC service (PCBWay, Xometry, a local workshop) can make them from the same STEP + PDF,
or use the resin caps from the print kit (../3_JLC3DP/FlashKa_print_kit.stl).
The cap STEP files have the axis through the origin (turned part).

The lid has two underside bosses (hold-down). The pads are NOT part of the order; buy them and cut them to the boss size:
  can boss  (X 22.1-30.9, Y -7.6..4.8): 1.0 mm silicone gap pad (thermal pad), Shore 00 70-80, cut 8.8 x 12.4.
  front boss (X 15.65-19.35, Y 0.05-3.25): 1.0 mm silicone rubber sheet, Shore A 70, cut 3.7 x 3.2.
Stick them on the bosses with a drop of silicone adhesive. Both are compressed to 0.8 mm (20 %) when the lid is closed.
