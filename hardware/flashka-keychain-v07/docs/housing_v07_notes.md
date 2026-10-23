<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.7 - housing notes

Status: designed and checked in CAD only. Nothing of v0.7 has been made yet; every picture is a render and
every number below comes from the model (`tools/housing/flashka_housing.py`, class `P`) or from one of its
checks (`docs/checks/`), unless it is marked as a maker's figure.

## 1. Files

| Where | What |
|---|---|
| `tools/housing/flashka_housing.py` | the parameter table `P`, every part, all checks; writes the STEP/STL files and `cad/housing_interface.json` |
| `tools/housing/drawings.py` | the nine drawing sheets (DXF, PDF, PNG) and the dimension table; every printed number is checked against `P` and against the solids |
| `tools/housing/key_mould.py` | the two casting moulds of the side keys - resin (SLA, the default) and aluminium (the durable option) - and their checks; writes the mould STEP / STL files, `_ref_mould_*.stl` and `cad/key_mould_checks.json` |
| `tools/housing/fit_pcb.py` | fit check of the real main board and key board (KiCad STEP exports) in the housing, with the wire paths |
| `tools/housing/assemble.py` | `cad/FlashKa_assembly_reference.step`: housing, both boards, keys, TIR optic, the cell with its strips, pads, screws, bought-part stand-ins |
| `tools/housing/render.py`, `render_anim.py` | the renders (`renders/`, README set in `assets/v07/`) and the two GIFs |
| `tools/housing/laser_label.py` | optional lid laser label (only for lights sold or given to others) |
| `tools/housing/order_files.py` | copies the order files (STEP, STL, drawing PDFs) from `cad/` into `order_files/` and the check files into `docs/checks/`; `flashka_housing.py`, `key_mould.py` and `drawings.py` call it whenever they write into `cad/` |
| `cad/` | STEP + STL of every part in the housing frame, `_ref_*.stl` stand-ins for the pictures, the two machining kits (STEP, kit frame), the side key with its stiffener (STEP), the casting moulds, drawings, `drawings_dimension_table.txt`, `housing_interface.json`, the assembly STEP; the board STEPs and `pcb_placement*.json` belong to the PCB tools |
| `order_files/2_JLCCNC/` | tray, lid, the PMMA kit and the POM-C kit (for JLCCNC), the single PMMA and POM-C parts (for shops that take small parts): STEP + PDF, README |
| `order_files/3_rubber_keys/` | side key (rubber body, stiffener, both together) + drawing; resin mould (two STL for JLC3DP + closed STEP); aluminium mould (closed, cavity half, lid) + drawing; README with the casting steps |
| `order_files/optional_laser_label/` | label DXF + preview, README |
| `docs/checks/` | `housing_v07_build_checks.txt`, `housing_v07_drawings_dimension_table.txt`, `key_mould_v07_checks.json`, `fit_pcb_v07_report.txt/.json` |

Drawings: FK-H-01 tray (2 sheets), FK-H-02 lid, FK-H-03 main key (PMMA), FK-H-04 side key (cast rubber + glued
stiffener), FK-H-05 POM-C parts, FK-H-06 PMMA machining kit, FK-H-07 POM-C machining kit, FK-H-08 casting moulds
of the side keys (aluminium, with the resin version beside it). Each title block carries "FlashKa Keychain v0.7"
and the file name(s).

Coordinates: X = 0 at the front face of the 99.2 mm body, +X to the tail; Y = 0 on the centre line, -Y control
side (USB-C), +Y laser side; Z = 0 on the bottom facet. The KiCad boards keep the coordinates of the first v0.7
layout (a 94.4 mm body): housing X = board X + 2.75 (`PCB_DX`). `cad/housing_interface.json` gives `pcb_outline`,
`components` and `key_board` in that board frame (entry `pcb_frame`), everything else in the housing frame.

## 2. Rebuild

Run in `tools/housing/` (CadQuery 2.x, ezdxf, PyMuPDF, VTK 9, trimesh; renders under `xvfb-run`):

```
python3 flashka_housing.py ../../cad > ../../docs/checks/housing_v07_build_checks.txt     # parts, kits + checks, about 3 min
python3 key_mould.py ../../cad
python3 drawings.py ../../cad ../../cad --quiet
python3 fit_pcb.py ../../cad/FlashKa_main_pcb.step ../../docs/checks --kb-step ../../cad/FlashKa_keys_pcb.step \
    --kicad-pcb ../../kicad/FlashKa_main/FlashKa_main.kicad_pcb --kb-kicad-pcb ../../kicad/FlashKa_keys/FlashKa_keys.kicad_pcb
python3 assemble.py ../../cad ../../cad/FlashKa_main_pcb.step --kb-step ../../cad/FlashKa_keys_pcb.step \
    --kicad-pcb ../../kicad/FlashKa_main/FlashKa_main.kicad_pcb
xvfb-run -a python3 render.py ../../cad ../../renders --pcb-step ../../cad/FlashKa_main_pcb.step \
    --kb-step ../../cad/FlashKa_keys_pcb.step --kicad-pcb ../../kicad/FlashKa_main/FlashKa_main.kicad_pcb --assets ../../assets/v07
xvfb-run -a python3 render_anim.py --pcb-step ../../cad/FlashKa_main_pcb.step --kb-step ../../cad/FlashKa_keys_pcb.step \
    --kicad-pcb ../../kicad/FlashKa_main/FlashKa_main.kicad_pcb
python3 laser_label.py                                                                    # optional label only
```

The order folders get copies of the STEP / STL files and drawings (PDF names = STEP base names; the POM-C sheet
is `FlashKa_pom_parts.pdf`, the side key sheet `FlashKa_key_side.pdf`, the kit sheets `FlashKa_pmma_kit.pdf` and
`FlashKa_pom_kit.pdf`, the mould sheet `FlashKa_key_mould.pdf`). `flashka_housing.py`, `key_mould.py` and
`drawings.py` refresh these copies, the dimension table and the mould checks in `docs/checks/` every time they
write into `cad/` (`order_files.py`; run it alone after changing `cad/` by hand), so no order file can stay
behind its source. `render.py` and `render_anim.py` read the copper pads of the key board from
`../../kicad/FlashKa_keys/FlashKa_keys.kicad_pcb` (option `--kb-kicad-pcb`).

## 3. Design

### 3.1 Exterior: the octagon

Body: a faceted octagon 20 wide x 18 high x 99.2 long (tray + lid), aluminium 6061-T6, bead blast, black anodise,
no marking. Eight flat facets with 45 degree legs of 3.4 mm: bottom facet (the key face) and top facet (the lid)
13.2 wide, side facets 11.2 high, four diagonal facets 4.81 wide. The owner chose one 14500 cell and this body
in place of the 20 x 16 rectangle with its 1.5 mm chamfer frame and the two pouch cells; length, style and every
approved detail stay. Outline perimeter 68.033 mm, section area 336.88 mm2.

Three proportions of the same 20 x 18 octagon were rendered (front and three-quarter views, hero camera):
legs 3.0 (facets 14.0 / 12.0 / 4.24), 3.4 (13.2 / 11.2 / 4.81) and 3.8 (12.4 / 10.4 / 5.37). The 3.4 legs were
built: with 3.0 the body still reads as a rectangle with chamfered edges; 3.8 reads as an octagon too, but the
bottom facet then keeps only 0.4 mm of frame beside the key bezel (11.6 wide at the face) and the chamfer of the
USB-C opening ends 0.1 above the lower diagonal facet. The 3.4 legs leave a 0.8 frame on both sides of the bezel,
0.5 of side facet under the USB-C chamfer and diagonal facets wide enough to catch the light.

- Recessed panels 0.3 deep, corners R0.8, with 1.2 rails along the facet edges and 1.2 frame bands, on the
  bottom, top and side facets: bottom and top panels |Y| <= 5.4, side panels Z 4.6 to 13.4. The diagonal facets
  (2.4 between two rails) are too narrow for a panel and stay plain between the grooves.
- Texture: 90 degree V grooves 0.2 deep at pitch 0.9 (0.4 grooves, 0.5 lands), at 45 degrees on one grid per
  face, cut with one 90 degree V cutter; at least 1.0 mm of metal under every panel.
- Transverse V grooves 0.3 deep at X 1.5 / 2.7 / 3.9 (head: top, bottom and diagonal facets; the optic and laser
  bores leave too little metal under the side facets) and X 87.95 / 89.15 / 90.35 (tail, all round).
- Front outline C0.4, tail outline C0.6, tail facets 2.0 x 45 degrees, tail window 4.1 x 10.8 x 1.0 round the
  lanyard slot on the bottom facet. The floor RF window (5.1 x 10.8) is filled by a textured POM-C plug flush
  with the panel floor, so it reads as part of the panel and not as a fourth key.
- Lid: the cap above the plane Z 14.6, which meets the outside exactly at the edges between the side facets and
  the upper diagonal facets, so the joint line follows a facet edge and needs no lip. The cap carries the top
  facet and the two upper diagonal facets (3.4 tall) from X 4.2 to the tail; over the cavity (X 11.45 to 93.35)
  it is pocketed from below (plate 1.5, 45 degree walls 1.5 under the diagonal facets, flat seat 2.121 wide on
  each side on the 1.5 tray walls); over the head and tail blocks it is solid, and there the four countersunk
  screws pass through it. The tray walls rise straight to Z 14.6, so the main board drops in from above.

Length chain (X): head 11.45 + 0.1 gap + main board 24.0 + antenna 5.4 + 0.8 gap + bay 51.6 + tail 5.85 = 99.2.

### 3.2 Head: TIR optic, LED board, laser

- Optic: LEDiL LISA3-RS-PIN (FP16558), d10.0, 6.93 +/-0.2 high above the LED board (LEDiL drawing FP165xx
  LISA3-x-PIN rev 1.2; data sheet 6.9), clear PMMA lens in a black PC holder. The two locating pins are cut
  off: the bought 10 mm copper DTP board has no holes, and the bore locates the optic. No front window and no
  spacer ring (v0.6 had both).
- One bore d10.1 +0.05/0 from the front face to a flat floor at X 8.83 centres both the optic (0.05 radial
  play) and the LED board. The holder stands on the board's front face - the LED level, as LEDiL designs it
  ("PCB or heatsink level. LED location"): board front face X 7.13, board 1.6 thick on 0.1 of thermal paste,
  floor X 8.83, then 2.62 of solid aluminium to the head rear face at X 11.45 (2.0 required) - the heat path.
  LED axis Y -3.825, Z 8.0 (unchanged). The bore keeps 1.125 to the -Y side facet, 2.569 to the lower -Y
  diagonal facet, 2.95 to the bottom facet and 1.55 to the head-block top under the lid.
- The optic's front face lies 0.2 behind the body's front face (0.0 to 0.4 over the +/-0.2 height
  tolerance): never proud. The bore keeps its full diameter to the front face (no lip): from the
  edge of the lens exit (d8.6, the unlabelled drawing callout) a ray clears the bore mouth up to 61.9 degrees from
  the axis at the deepest seat and 75.1 degrees at the nominal one, far outside the 20 degree beam.
- Retention: two-part epoxy (or neutral-cure silicone) on the holder rim against the bore wall, the optic held
  pressed onto the LED board while it cures; no cyanoacrylate (its vapour fogs PMMA). Not a press fit: the
  thin PC holder would have to carry the fit, the bore is +0.05/0, and the board must stay pressed onto the
  floor. The glued optic traps the LED board on the bore floor (LED board to head contact 78.51 mm2). If the
  board does not drop into the bore, sand its edge.
- LED wires (24 AWG PTFE, OD up to 1.05): two grooves in the bore wall, tilted 30 degrees from 12 and 6 o'clock
  (the upper one towards +Y), 1.4 wide and 1.3 deep into the wall (bottom R6.35), from X 6.13 to the floor,
  and two holes d1.5 on the same lines (R5.7 from the axis) through the solid behind the floor. The wire runs
  straight from the pad over the board's edge into the cavity and never passes under the board: radial room
  beside the board 1.35 (0.3 play), side play in the groove 0.175, in the hole 0.225; a d1.05 wire along the
  path keeps 0.125 (upper) and 0.088 (lower) to the tray and 0.175 to the board and the holder (build check).
  Hole exits: upper Y -0.975, Z 12.94 at X 11.46 (towards LED+ on the board's top face at X 12.6, Y -3.675);
  lower Y -6.675, Z 3.06, drilled on to X 12.64 past the R2.0 plan corner of the cavity, where its last 1.2 mm
  graze the 45 degree floor corner (towards LED- on the bottom face at X 13.0, Y 1.7, under the USB-C
  receptacle). Upper groove 0.751 and hole 0.914 under the head-block top; lower groove 1.304 and hole 1.363 to
  the lower -Y diagonal facet. Turn the LED board so that its two pads face the grooves.
- Front lid taps at X 10.14, Y +/-4.5, centred in the 2.62 of solid behind the bore floor: 0.51 of metal to
  the bore floor and 0.51 to the head rear face at the thread root (major diameter 1.6), 0.685 at the tap drill;
  the build checks it in 3D with the thread cut to its root. Every metal wall of the tray and the lid keeps at
  least 0.5 mm, JLCCNC's absolute minimum (see 6).
- Laser: bore d6.1 at Y 5.85, Z 5.9, open to the cavity behind X 11.45, unchanged; 1.1 to the +Y side facet,
  1.652 to the lower +Y diagonal facet, 1.8 to the optic bore. Retention: an M1.6 x 5 set screw from the top of
  the head block at X 5.5, Y 4.8, under the front end of the lid, so no hole, screw or mark shows on the closed
  light. It sits 1.05 to the -Y side of the laser axis; its hole lies 0.5 behind the lid edge (X 4.2); thread
  5.836 long at the screw axis; the point meets the module at Z 8.829, 12.5 degrees off its top; the screw top
  stays 0.771 below the head-block top (Z 14.6), so the lid closes over it; its thread keeps 3.05 to the front
  lid tap.
- Cavity front corners: a relief d2.0 at X 12.35, Y +/-7.9 from Z 9.2 to the lid seat clears the board's
  chamfered front corner (board pushed to a side wall) and the USB-C receptacle while the board is tilted in.

### 3.3 Cell bay and wire paths

- Bay X 41.75 to 93.35, 51.6 long: the inside of the octagon, 17.0 wide between the side walls, floor Z 1.5,
  lid plate Z 16.5, with 45 degree corners at the floor and under the lid's diagonal facets (1.5 walls).
- Cell: one Vapcell INR14500 F15 (maker's figures: 14.0 +/-0.2 x 49.0 +/-0.3, about 22 g, flat top,
  unprotected). The bay takes any flat-top 14500 up to 14.5 x 50.4, for example the Vapcell K10 (14.1 +/-0.2 x
  50.1 +/-0.3). Length budget: 51.6 = 50.4 + 2 x 0.4 (nickel strip 0.2 with its fold and weld bumps, each end) +
  0.4 (the thinnest tail pad).
- The cell lies on two floor rails, 1.2 wide and 1.1 high (top Z 2.6, X 44.75 to 90.35), on their inner edges at
  |Y| 3.5, with 0.05 polyimide tape on each rail: it cannot roll and stays 0.196 to 0.249 above the floor between
  the rails. Nominal F15: axis Y 0, Z 8.712 (8.596 to 8.827 over its tolerance, 8.999 for a 14.5 cell), front end
  (behind the strip) at X 42.15, 1.5 from the side walls (1.25 to 1.6 over all cases).
- No rattle: a soft closed-cell foam strip 6 wide under the lid presses the cell onto the rails, a foam pad at
  the tail end takes up the length. Both are stacked from 0.5 mm foam sheet, each about 1.6 x the gap it fills
  (20 to 55 % compression): nominal F15 1.5 strip on a 0.788 gap (47.5 %) and 3.0 pad on 1.8 (40 %); over the F15
  tolerance a 1.0 to 1.5 strip and a 2.5 to 3.5 pad; K10 1.0 to 1.5 and 0.5 to 1.5; a 14.5 x 50.4 cell 0.5 and
  0.5 (`bay` in the build log). Measure the cell and pick the stack.
- Connection: nickel strips 0.2 x 5 spot-welded to both cell ends (a pre-tabbed cell or a small spot welder;
  never solder on the can); cell + towards the head. Front end, BAT+: the strip runs across the front face and is
  bent forward into the cell-wire rebate of the antenna spacer, where the 24 AWG wire is soldered to it (joint
  at about X 40.55, Y -5.8, Z 6.6). Far end, BAT-: the strip is bent into the lower -Y corner of the bay, the
  channel between the round cell, the -Y rail, the 45 degree floor corner and the side wall (free radius 1.046
  round the channel line at Y -6.6, Z 3.6, against 0.525 for the d1.05 wire; 1.378 to the F15 at its lower limits,
  1.277 to a 14.5 cell); the joint sits in the channel at X 89.75, and the wire runs forward along it, climbs
  beside the cell's front end into the -Y side of the rebate and goes under the main board to J2 BAT- (X 34.05,
  Y -6.15, bottom face). The BAT+ wire stays on the +Y side of the rebate and goes to J2 BAT+ (Y -3.15): the two
  wires never cross.
- Rebate in the antenna spacer: Y -8.5 to -4.6, floor Z 5.6 (0.4 above the key board), open to the wall and to
  the top: 3.9 x 4.4 under the module, 3.6 high under the main board; at the spacer's front face the tray's
  ledge-block corner (R2.0) leaves 2.66 of width: 0.56 margin for the two wires side by side, 2.55 in height.
- Heat: the cell touches the body only along the two rails (through the tape) and through the foam, so it is
  weakly coupled. No thermal pad was fitted: a gap pad (1.0 MPa assumed, as for the can pad) compressed along
  the cell would need tens of newtons from the lid, far more than the foam strip gives.
- Laser wires (28 AWG): unchanged, beside the laser module under the main board.
- Wire corridors as solids (fit check against the real boards, section 5): 0 hits on the boards, the housing
  and the cell.

### 3.4 Keys

All three keys sit on the centre line of the bottom facet at X 18.65 / 25.65 / 32.65 (next / main / previous;
board frame 15.9 / 22.9 / 29.9), in one stadium bezel 0.5 deep with 45 degree walls (X 15.75 to 35.55, 11.6 wide
at the face, 0.8 of frame to the facet edges).

- Main key: clear cast PMMA, 6.8 x 6.8 R1.0, 2.75 tall, flange 7.6 x 7.6 x 0.45; pocket 4.4 x 3.4 x 1.2 round
  the switch body, nub d1.6 x 0.5. Face 0.15 inside the bottom plane, edges C0.15, polished; a frosted ring
  (d4.4 mean, 0.5 wide, 0.03 deep) on the outer face carries the light of the two ring LEDs (LED face 0.6 above
  the key's top face at rest). Opening 7.0 x 7.0 (0.1 per side).
- Side keys: black urethane rubber Shore A 80 (75-85), cast at home (3.10), one piece without inserts, pocket or
  nub; 4.2 x 10.0 R1.5, flange 5.2 x 11.0 x 0.45, face 0.30 inside the bottom plane. Raised chevron 0.2,
  90 degrees, stroke 0.6, 1.8 along the body and 3.0 across, with its apex along the body: towards the head
  on the next key (X 18.65), towards the tail on the previous key (X 32.65) - the same part turned 180 degrees.
  Held like a presenter (head towards the screen, keys up) the key nearest the head reads "^" (next) and the key
  nearest the hand "v" (previous). With the polished chevron grooves of the mould the chevron top is glossy on
  the matte key face. A stiffener cut from 0.3 stainless steel shim (1.4301) makes the key a stiff rocker: a
  plate 3.6 x 9.4 with its corners clipped 0.8 x 45 degrees (outline +0/-0.2, tin snips or laser), glued into a
  3.8 x 9.6 R1.0 recess 0.47 deep in the inner face after casting, and a 2.0 x 2.0 doubler on its centre that
  presses the switch (doubler top 0.15 above the inner face; flange underside to doubler top 0.6 +/-0.11 worst
  case). Opening 4.4 x 10.3 (0.1 per side, 0.15 at the ends).
- The flanges sit on the floor (Z 1.5); each key is held between the floor and its switch with 0.15 (main) or
  0.25 (side) of free play.

### 3.5 Key board (KB) and floor

- KB 19.0 x 14.8 R1.0, 0.8 thick, Z 4.4 to 5.2 (X 16.15 to 35.15), switches and ring LEDs on its bottom face, six
  pogo pins on its top face. Bottom-face parts sit 0.05 off the board (solder), as in the KiCad STEP export:
  switch tip Z 2.35, LED face Z 3.50, pin base Z 5.25.
- Two bosses d3.4 at (25.65, +/-5.8), joined to the trough walls, top Z 4.4, blind M1.6 tap (drill d1.25 to
  Z 2.025, point to Z 1.6495; full thread to Z 2.55): 1.7 thread engagement for the M1.6 x 2.5 pan-head
  screw, 1.649 of metal under the drill point. Four ribs 1.4 wide at X 18.65 and 32.65 (|Y| 5.9 to the wall; at
  -Y, X 18.65 a free post in the USB-C gap) carry the KB edges.
- Floor 1.5, 1.0 under the bezel; webs 1.3 between the key openings.

### 3.6 Pogo pins and main-board hold-down

- Harwin P70-1010045R on the KB top at Y 2.5, X 17.75 / 20.55 / 23.35 / 27.75 / 30.55 / 33.35 (board frame 15.0 to
  30.6) onto the J6 pads of the main board: working height 3.95 nominal, worst case 3.76 to 4.14 (inside 3.7 to
  4.2, margins 0.06 / 0.06), RSS 3.847 to 4.053; force per pin 1.229 N nominal (0.757 to 1.81 N with the spring
  tolerance), all six 7.37 N (4.54 to 10.86 N).
- The pins push the board up; two lid bosses hold it down. They hang from the lid plate (Z 16.5): the can boss
  (8.8 x 12.4, 2.95 tall, face Z 13.55) with a 1.5 mm silicone gap pad compressed to 1.15 (23.3 %) and the front
  boss (3.7 x 3.0, X 18.4-22.1, Y 0.25-3.25, 5.75 tall, face Z 10.75) with a 1.0 mm silicone rubber pad
  compressed to 0.75 (25 %). The front boss keeps 0.435 to the driver IC U2 next to it on the board, more than
  the board's side play, so the boss never meets U2.
- Plate model (Mindlin plate of the 0.8 mm board on its ledges, pads as springs, pins as point loads):
  nominal preload 39.68 N against 7.37 N, ledge lift 0.0004 mm, the board leaves the ledges at 3x the pin force;
  soft case (pads 30 % softer, gaps +0.1, pins at their maximum 10.86 N) 18.69 N, lift 0.0006 mm; hard case
  (pads 30 % stiffer, gaps -0.1) 68.47 N, lift 0.0008 mm (limit 0.02 mm). Without the front boss the pins lift
  the board front 0.0894 mm, so the front boss stays; top-side keep-out on the board (board frame) X 15.6-19.4,
  Y 0.2-3.3.
- Pad stacks: can pad gap worst case 0.86 to 1.44 (4.0 to 42.7 %), front pad 0.56 to 0.94 (6 to 44 %).

### 3.7 Other parts

- POM-C black: lid RF window insert (plug 6.84 x 10.74 R1.47 with 0.03 per side in the lid opening - the plug
  locates the insert; flange 8.3 x 12.2 x 0.8 with 0.10 per side in the pocket, so the flange edge locates
  nothing and can carry the kit tabs; face 0.3 below the lid top, textured); antenna spacer with the floor plug
  (5.04 x 10.74, flush with the panel floor, textured), the cell-wire rebate and a +Y wall that rises inside the
  lid's diagonal facets to 0.15 under the insert flange (Z 16.15), so the insert cannot drop in; optional laser
  sleeve.
- Bought screws, stainless steel: 4x M1.6 x 6 countersunk ISO 7046 / DIN 965 (lid; through the 3.4 of solid
  lid into 2.6 of thread), 2x M1.6 x 2.5 pan head ISO 7045 / DIN 7985 (key board), 1x M1.6 x 5 set screw
  ISO 4026 flat point or ISO 4029 cup point, hex socket 0.7 mm (laser).
- Cell bay: polyimide tape 0.05 on the rails; closed-cell foam sheet 0.5 mm for the strip and the tail pad (3.3).
- Removed from v0.6: light-pipe tube, stainless caps, resin print kit, laser marking, glass window and POM spacer
  ring.
- Masses (model): tray 22.487 g, lid 8.426 g, RF insert 0.166 g, antenna spacer 1.164 g, main key 0.134 g, side
  key 0.064 g each, stiffener (plate + doubler) 0.087 g each, laser sleeve 0.156 g; TIR optic 0.575 g (drawn
  shape, PMMA + PC); cell about 22 g (maker's figure).
- Boards: both boards (one JLCPCB panel) are ordered with black solder mask and white silkscreen, ENIG. The
  renders show them matte black; the copper pads come from the two `.kicad_pcb` files: gold where no solder
  covers them (the J6 pogo targets), solder-silver on the reflowed pads. The silkscreen is not drawn.

### 3.8 Thermal-model inputs (for the firmware's thermal simulator)

From the solids (`thermal_model_inputs` in `cad/housing_interface.json`): aluminium tray 22.49 g + lid 8.43 g =
30.91 g (6061-T6, 2.70 g/cm3); outer surface of the closed light 7382.1 mm2 (envelope with the facets), of it
6886.3 mm2 aluminium (minus the optic, laser, key, RF window, USB-C, S2 and lanyard openings); the panel texture
adds 625.2 mm2 of face area; head block (tray X 0 to 11.45) 6.34 g, the lid over it 1.05 g, the solid behind the
LED board (X 8.83 to 11.45) 1.72 g; LED board to head contact 78.51 mm2 (d10 board on the bore floor, 0.1 mm
paste); copper DTP board 1.13 g. The LED board's edge is 1.175 from the -Y side facet, 2.619 from the lower -Y
diagonal facet, 3.0 from the bottom facet, 1.6 under the head-block top (the lid lies on it) and 5.0 under the
top facet. Cell: about 22 g (maker), axis Y 0, Z 8.712, X 42.15 to 91.15; two line contacts along the rails
(|Y| 3.5, X 44.75 to 90.35) through 0.05 polyimide, foam to the lid, strips and wires to the board: weakly
coupled.

### 3.9 Machining kits (JLCCNC)

JLCCNC machines plastic parts only from 30 x 20 x 8 mm (rotary parts: longer than 20 mm, more than 6 mm in
diameter); the PMMA main key and every POM-C part are smaller. Two kits carry them, each one solid piece: a
frame with one through-pocket per part, every part hanging on small tabs in one tab plane. The single-part
files stay for shops that take small parts.

- `FlashKa_pmma_kit.step` (FK-H-06), 52.8 x 22.0 x 8.5: three main keys (1 + 2 spares), outer face up, centred
  in the height; 9 tabs 0.6 wide, the flange thickness (0.45) high and 3.0 long on the free flange edge (the cap
  locates the key in its opening, the flange underside on the floor seat); tab plane Z 3.825 to 4.275. Never on
  the outer face or the frosted ring.
- `FlashKa_pom_kit.step` (FK-H-07), 45.4 x 39.3 x 17.0: two lid RF inserts (1 + 1 spare, textured face up, tabs
  on the free flange edge flush with its underside) and the antenna spacer (15.85 tall, upright, floor plug up,
  tabs on its side faces, which clear the cavity walls by 0.1 while the plug locates it; 5.0 gap round it for
  the 12.5 mm deep cut); 9 tabs 0.6 x 0.6, 3.0 long (antenna spacer 5.0), tab plane Z 12.5 to 13.1. The laser
  sleeve (option) stays a single part: its slit along the axis needs a side setup.
- Two setups on a 3-axis mill: from the top (kit +Z: outer face and frosted ring of the keys, textured faces,
  spacer chamfers) and from the bottom; the gaps are cut from each side to the tab plane last. On arrival: cut
  the tabs, file flush; the frame is scrap.

### 3.10 Casting moulds of the side keys (`key_mould.py`, FK-H-08)

A vacuum-casting mould would cost more than two small keys justify, so the builder casts them at home, 4 keys
per pour (2 + 2 spares), in a mould that is a tool and not a part of the light (one per builder). Both versions
have the same cavities: the cavity half holds the keys face down, so the chevron is a groove in the cavity floor
(R0.3, the smallest internal radius) and bubbles rise away from the visible face; the parting plane is the inner
face, and the lid's plateaus form the plate recesses. Per cavity a pour hole, a runner and a gate on the near
flange end, a vent groove at the far end and a vent hole through the plateau: every stub lands on the flange
end or the hidden inner face. Walls with 1 degree of draft; the cap sits 0.04 per side under nominal, so the
cast cap stays inside its -0.05/-0.15 tolerance at every height (4.086 / 4.12 wide, 9.886 / 9.92 long near the
face / at the flange step). The keys and the moulds did not change with the octagon body.

- Resin (the cheap default): two SLA resin plates from JLC3DP (STL files), 48 x 28, the cavity half 6.0 and the
  lid 5.0 thick, each with a ribbed back (rim 3.0, ribs 2.0 under each cavity column and along the middle, solid
  round the bolt, pour and vent holes and the sockets; 2.0 of resin under the deepest cavity point, the lid's
  face plate 2.0; at least 1.25 round every hole). Two printed pins d4.0 on the cavity half fit two sockets d4.2
  in the lid (offset: the lid fits one way); four M3 x 16 socket head screws with washers and nuts go through
  both plates - no threads in the resin. Volumes 6.24 and 4.82 cm3. Print with the parting face up, supports on
  the back only. A print does not hold the aluminium tolerances: try the first key in its opening.
- Aluminium (the durable option): two 6061-T6 plates 48 x 28 x 8 (JLCCNC, above its 30 x 20 x 8 minimum), the
  chevron groove cut with a d0.6 end mill; two pressed dowel pins (offset), four M3 screws, cavity half
  bead-blasted for a matte key face.
- Rubber: Smooth-On ECON 80 (Shore 80A, 1A:1B by volume, maker's data) or Sugru (Shore 70A, pressed in by hand);
  PMC-780 DRY also works; the parts list names the default. Mould release is needed before every cast
  (urethane: a urethane mould release; Sugru: petroleum jelly). Polishing the chevron grooves once gives the
  glossy chevron top; in the resin mould a rub of the cavity floors with 400-grit paper gives the matte face.
  Casting steps: `order_files/3_rubber_keys/README.txt`.

## 4. Check results

| Check | Result | Margin / limit |
|---|---|---|
| Interference, stand-in boards (3 main-board poses, KB, KB vs main board, part to part) | none | - |
| Cell with its strips and joints in the bay (F15 at its lower / nominal / upper limits, K10 at its lower / upper limits, largest flat-top 14500 14.5 x 50.4) vs tray, lid, RF insert, antenna spacer | 0 mm3 each | gap under the lid 1.004 to 0.251, length left for the tail pad 2.1 to 0.4, side gap 1.6 to 1.25 |
| Optic seat | front face X 0.2 (0.0 to 0.4), LED board X 7.13 to 8.73, bore floor X 8.83, 2.62 solid behind it | 2.0 required; exit clear to 61.9 degrees |
| LED wire paths (d1.05 wire along groove + hole) | 0 mm3 with the tray; 0.125 (upper) / 0.088 (lower) to the tray, 0.175 to the LED board and the optic holder | radial play 0.3, hole play 0.225 |
| Cell wires | far-end channel: free radius 1.046 round a d1.05 wire; rebate 3.9 x 4.4 (3.6 under the board), 2.66 wide at the spacer front | two wires side by side 2.1 x 1.05: margins 0.56 / 2.55 |
| Metal under texture and grooves | min 1.0 under every panel, 1.076 under the tray tail grooves, 1.2 under the lid tail grooves, 1.352 under the head grooves | limits 0.9 over the cell bay, 1.0 elsewhere |
| Key free play at rest | 0.15 main, 0.25 side; no contact before full travel (0.4 / 0.5) | main: pocket floor 0.25 below a full-height switch box at full travel; side: doubler top 0.15, plate top 0.45 below the switch body |
| Key free play over the tolerance stack | main worst case -0.07 to 0.37 (RSS 0.033 to 0.267); side -0.05 to 0.55 (RSS 0.119 to 0.381) | a negative worst case is a small preload, below the 0.20 click travel |
| LED gap to the main key | 0.6 at rest, 0.2 at full travel; RSS minimum 0.051, worst case -0.08 | with the 0.85 mm worst-case LED height |
| Side key pressed 2 mm from its end (plate + doubler glued in) | 1.035 N at the click, 0.729 key travel (0.806 at full travel); near end rises 0.9, 1.55 below the KB (1.45 at full travel, 1.21 at the RSS-maximum free play); key end shifts 0.082-0.113 in its 0.15 end gap; no contacts | rubber only (no plate): 3.933 travel, 5.09 rise, would touch the KB |
| Pogo working height / force | see 3.6 | 0.06 / 0.06 to the 3.7-4.2 range |
| Hold-down | see 3.6 | ledge lift limit 0.02 mm |
| Insertion of the main board (tilted about X, S2 side first) | no collisions; the board meets the plunger tips from 9 degrees and compresses them | - |
| Walls (every metal wall >= 0.5, JLCCNC's absolute minimum) | front lid taps: 0.51 to the optic bore floor and 0.51 to the head rear face at the thread root (3D, thread cut to its root), 0.685 at the tap drill; upper LED wire groove to the head-block top 0.751, hole 0.914; lower groove / hole to the lower -Y diagonal facet 1.304 / 1.363; optic bore to the -Y side facet 1.125, to the lower -Y diagonal 2.569, to the laser bore 1.8; laser bore to the +Y side facet 1.1, to the lower +Y diagonal 1.652; side walls, floor, diagonal walls and lid plate 1.5; lid over the head and tail blocks 3.4; RF pocket to the upper diagonal facets 0.919, to the top 0.9; front corner relief to the side facet 1.1; floor under the bezel 1.0, floor webs 1.3, KB boss wall 0.9, KB tap to bezel 1.254, bezel edge to floor RF window 0.8; tail front wall 0.8, lanyard bridge 1.45, slot to rear tap 1.4 at the thread crest; laser set-screw thread to the front lid tap 3.05; on the lid's top face 0.3 between a rear countersink and the slot chamfer | all from `min_walls` in the build log |
| Laser set screw and the closed light | M1.6 x 5 from the head-block top under the lid: hole 0.5 behind the lid edge, screw top 0.771 below the head-block top, thread 5.836; ray scan of the closed light (10873 rays from below, 11798 from above): no hole deeper than 0.6 outside the key openings, the joints of the two RF plugs, the tail window and the four lid screws | `laser_retention` in the build log |
| RF windows | lid 6.9 x 10.8 (X 34.55 to 41.45), floor 5.1 x 10.8 (X 36.35 to 41.45); the antenna end of the module (X 35.55 to 40.95) lies under both; across it, Y -5.4 to 5.2 of the module's -8.0 to 5.2 is free of metal | `rf_windows` in the build log |
| Machining kits | bounding boxes 52.8 x 22.0 x 8.5 and 45.4 x 39.3 x 17.0 (minimum 30 x 20 x 8); one valid solid each; gap part to frame 3.0 (4.917 at the antenna spacer); volume balance exact; parts identical to the single files; two-setup reach: 652 + 786 points on 210 + 243 faces, 0 blocked | `machining_kit_checks` in the build log |
| Casting moulds | aluminium: cavity half and lid one valid solid each, 48 x 28 x 8.0 / 8.47; two-setup reach 0 blocked. Resin: one valid solid each, 48 x 28 x 8.5 (with the pins) / 5.47; 2.002 of resin between a cavity and the back pockets, 1.25 round the holes. Both: closed, the halves overlap 0; no undercut (rays from 448 points on 132 cavity faces and 112 points on 36 plateau faces, 0 blocked); cast key = model key, cap inside its tolerance | `key_mould_v07_checks.json` |
| Drawings | 574 entries, 441 distinct numbers on nine sheets, 0 differ from `P`; 74 ray probes into the solids, 0 differ; 0 layout findings | tolerance 6e-4 |

## 5. Real boards (`fit_pcb_v07_report.txt`)

Both boards from the PCB tools (`FlashKa_main_pcb.step`, `FlashKa_keys_pcb.step`), moved 2.75 along X from their
board frame, unchanged: main board 58 solids + stand-ins for U4, J1, L1; key board 20 solids, lifted by 4.4 mm;
the pogo pins (one solid each, free height) are split into barrel and plunger. The boards fit the octagon body
without any change to them: the board zone keeps the old inside width (17.0 between straight walls up to Z 14.6).

- Key board vs housing: 0 collisions. Clearances: SW1 to the main key 0.150, SW2 / SW3 to the side keys 0.250,
  LED3 to the tray 1.200, KB to the antenna spacer 0.550.
- Main board centred: 0 collisions, plungers end on the J6 pads (offset 0.0), plungers vs components 0.
  Working height pin base to pad 3.96 (the KiCad board is 0.79 thick), inside 3.7 to 4.2. Smallest
  clearances: J1 to the tray 0.211, U2 to the lid (front boss) 0.435, KB R30 to J1 0.400, KB P6 to R9 0.460; the
  optic holder and the LED stay 4.420 and the LED board 2.820 from the main board; the cell 1.200, its front strip
  1.000 and its front solder joint 1.900 from the module U4.
- Main board pushed to the -Y or +Y wall (0.24): a contact sliver of 0.0013 mm^3 (not a collision) where the
  chamfered front corner of the board meets the cavity corner at X 12.0; the real side play is 0.236 mm (the
  front corner reliefs). At the +Y wall U2 keeps 0.195 to the front boss, at the -Y wall KB P6 comes within
  0.295 of R9.
- Free travel: +/-Y 0.236, +X 0.149 (antenna spacer), -X 0.062, +Z 0.393 (S2 knob in its slot).
- Insertion (tilted, S2 side first, over the installed key board with the plungers at free height): no hit above
  0.002 mm^3 in any of the 13 poses; no bottom-side part meets a plunger.
- Wire paths as solids (24 AWG, d1.05; `flashka_housing.wire_corridors`): LED+ wire, LED- wire, cell wire from
  the far end (BAT-) and from the front end (BAT+) hit nothing on either board, in the housing or on the cell;
  nearest board items 0.207, 0.538, 0.346 and 0.077 (the board's underside: the wires run along it to J2).
- `assemble.py` (installed state): main board x housing 0, key board x housing 0, main board x key board 0.

## 6. Deviations from the specification

- Body 99.2 mm (limit 99.4): head 11.45 for the optic, 2.62 of solid behind the LED board and at least 0.5 of
  metal round the front lid taps; bay 51.6 for flat-top 14500 cells up to 50.4 long with their strips; tail 5.85
  (tail front wall 0.8, lanyard slot 3.6, end wall 1.45); board front gap 0.1.
- Section 20 x 18 with 3.4 legs (spec: about 20 x 18, eight flat facets); see 3.1 for the choice.
- The lid is a cap 3.4 tall that closes on a flat seat at the upper facet edges (the rectangular body had a
  1.5 plate with a rabbet lip); the seat must be flat (FK-H-02).
- Lanyard slot 3.6 x 4.6 with C0.25 (was 4.2 x 7.6, C0.35): the top facet is 13.2 wide and the rear lid screws
  stay 0.45 inside it at Y +/-4.5, so the slot is shortened until each rear countersink keeps a 0.3 land to the
  slot chamfer on the top face. It takes a split ring or a thin cord.
- Lid screws M1.6 x 6 at Y +/-4.5 (were M1.6 x 4 at +/-6.3): the lid is 3.4 thick over the head and tail blocks.
- RF windows 10.8 wide (were 14.0): they fill the bottom and top panel width (|Y| <= 5.4); see 7.
- Front lid taps (earlier release review): at X 10.1 in 2.37 of solid the M1.6 thread root kept only 0.37 to the
  bore floor and 0.4 to the head rear face, below JLCCNC's absolute 0.5 mm. Fixed by a 0.1 smaller optic recess
  (0.3 -> 0.2, still never proud) and a 0.15 longer head (11.3 -> 11.45): the strip is 2.62, the taps sit in
  its middle (X 10.14) with 0.51 on both sides. Rejected: a shallow -Y front tap over the bore, M1.2 / M1.4
  (JLCCNC's threaded-hole guideline names no smallest thread and nothing here confirms them).
- The optic is glued (epoxy on the holder rim), not pressed (3.2).
- One cell on two rails, held by foam, no thermal pad (3.3).
- LED wire grooves and holes tilted 30 degrees from 12 / 6 o'clock (the upper towards +Y) so that the holes lie
  on the groove lines and keep 0.914 under the head-block top; LED+ is reached with a 2.7 mm sideways bend.
- LED gap 0.6 at rest (spec 0.3-0.4): with 0.15 free play and 0.25 switch travel the 0.85 mm worst-case LEDs
  keep 0.2 at full travel.
- Bezel 0.5 deep (spec about 0.4): it keeps the key faces inside the bottom plane (main 0.15, side 0.30,
  chevron top 0.10).
- Key-board screws M1.6 x 2.5 (spec M1.6 x 4): a 4 mm screw would need its tap through the 1.5 mm floor.
- The front lid boss and pad of v0.6 stay (see 3.6), narrowed to 3.7 x 3.0 so that they keep clear of U2; the pad
  is compressed 25 %: with 20 % the soft case lifted the board 0.0217 mm once the 0.05 solder standoff of the
  pins was included.
- Side keys are cast at home (3.10) and get a glued-in stainless steel stiffener, plate + doubler (see 4: rubber
  only is too soft at the ends).
- The cell wires run above the KB through a rebate in the antenna spacer (the KB covers the floor); the rebate is
  open to the top so that the spacer can be machined in two setups. The far-end wire runs along the lower -Y
  corner of the bay.
- The lid RF insert flange has 0.10 per side in its pocket: the plug alone locates the insert.
- The small plastic parts are ordered as two machining kits (JLCCNC minimum size), see 3.9.
- SMD parts on the KB are modelled 0.05 off the board, as in the KiCad export.

## 7. Open points and risks

- Optic data: the LEDiL PDFs could not be downloaded here (blocked); the outer diameter, the height
  6.93 +/-0.2 and the LED level come from the LEDiL drawing as read in the research notes, the lens exit d8.6 is
  an unlabelled callout of that drawing and the inner shape of the lens in the model is drawn, not measured
  (pictures only). On the first optic: measure the height and the diameter; the seat and the recess follow
  the measured height (X 0.2 nominal). The recess counts the LED board at 1.6 and the paste at 0.1: a thicker
  board or more paste moves the optic forward by the same amount.
- The holder base may sit on the LED wire solder joints of the 10 mm DTP board: if it does not stand flat,
  file two notches into the holder rim at the pads.
- Cell: the dimensions and the mass are the maker's figures; the model cell is a plain cylinder with the strips
  and joints drawn. On the first cell measure the diameter (with its sleeve) and the length with the welded
  strips, then pick the foam stacks (3.3). The far-end strip and its joint must go into the lower -Y corner when
  the cell is laid in, the wire pressed into the channel before the lid goes on.
- RF: the windows are 10.8 wide (14.0 on the rectangular body); across the module (Y -8.0 to 5.2) the strip
  Y -8.0 to -5.4 now has aluminium round it (floor corner, side wall, lid seat and diagonal wall). Check the radio
  range on the first light.
- Thin walls: every metal wall is at least 0.5 mm; below JLCCNC's recommended 0.8 are only the front lid taps
  (0.51 at the thread root, 0.685 at the tap drill; a new tap may cut a few hundredths over the 1.6 basic
  diameter) and the upper LED wire groove (0.751 under the head-block top). Name them in the quote; the 0.2 mm
  left to 99.4 mm would give the taps 0.1 more on each side. The 0.3 land on the lid's top face between a rear
  countersink and the slot chamfer is an edge to break lightly, not a wall.
- The lid closes on its seat: if the seat or the tray wall tops are not flat, a gap shows along the facet edge
  (FK-H-02: seat flat 0.05).
- Nothing is built: the free play, LED gap, end press, hold-down and the foam compressions are model numbers. On
  the first build, measure the main-key free play (worst case -0.07: a light preload if every tolerance is at its
  limit) and the LED gap at full travel (worst case -0.08 with 0.85 mm LEDs; typical LEDs are lower).
- The side keys are cast and glued by hand: on the first pour check that the chevron groove fills, that the
  parting line leaves no flash on the key face and that the side-key free play is there (doubler top 0.6
  +/-0.11 above the flange underside). The resin mould does not hold the aluminium mould's tolerances: try the
  first key in its opening; Sugru (Shore 70A) is softer than the 75-85 of the drawing.
- Rubber modulus from the Shore hardness (Gent: A75 7.0, A80 9.4, A85 13.2 MPa) and pad moduli (gap pad 1.0 MPa,
  silicone A70 5.3 MPa) are assumptions; the end-press and hold-down numbers scale with them.
- The panel texture needs an engraving pass; some quick-quote shops may not offer it (the parts work without it).
- The kits clear the JLCCNC minimum size; ask in the quote whether the shop accepts parts on tabs (the drawings
  say "cut the tabs, file flush"). The tab witnesses are on hidden faces that locate nothing. The POM-C kit has a
  12.5 mm deep cut in the 5.0 gap round the antenna spacer.
- U4, J1, L1, the cell, the laser module, the LED board and the optic are stand-ins in the fit check and the
  pictures.
- The v0.6 texts (build guide, chapter 13) and the v0.6 housing notes are kept only in the v0.6 folder
  (`hardware/flashka-keychain-v06/docs/`).
