# Aurora++ v0.5 housing — drawings, renders and checks (2026-10-14)

Housing: 94.4 × 20 × 16 mm, 6061-T6 tray + lid, two LP601646 cells. Source of truth:
`tools/housing/aurora_housing.py` (class `P` = every parameter, the build functions and the
checks). Its output is in `cad/` (STEP, STL, `housing_interface.json`). The PCB in every check
below is the final routed board (`cad/Aurora_main_pcb.step`, exported by
`tools/kicad/build_all.py`, with the KiCad board for the parts that have no 3D model).

## 1. Files

| File | What |
|---|---|
| `cad/Aurora_tray_drawing.pdf` (+ `.dxf`, `.png`) | tray, sheet 1 of 2: interior, threads, fits (the PDF has both sheets) |
| `cad/Aurora_tray_drawing_sheet2.dxf` / `.png` | tray, sheet 2 of 2: exterior (knurl, grooves, thumb dish, tail, marking field) |
| `cad/Aurora_lid_drawing.pdf` (+ `.dxf`, `.png`) | lid: outline, RF window opening and its underside pocket, countersunk holes, knurl |
| `cad/Aurora_marking_class2.dxf`, `cad/Aurora_marking_class3R.dxf` | laser-marking artwork for the bottom face (layer MARK = engrave, layer REF = outline, do not engrave) |
| `cad/Aurora_print_kit.stl` / `.step` | the four resin parts on 1 mm sprues — one part for JLC3DP |
| `cad/Aurora_assembly_reference.step` | reference assembly: housing, PCB parts by designator, cells, laser, LED board, window, screws |
| `renders/*.png` | pictures (section 3) |
| `docs/checks/` | `drawings_dimension_table.txt` (every number on the sheets against `P` and the solid), `fit_pcb_report.txt` (section 5), `size_comparison_summary.txt` |

Commands (from `tools/housing/`; `AUR_CACHE` only caches slow hidden-line projections):

```
AUR_CACHE=.aur_cache python3 drawings.py ../../cad ../../cad
xvfb-run -a python3 render.py ../../cad ../../renders --pcb-step ../../cad/Aurora_main_pcb.step --kicad-pcb ../../kicad/Aurora_main/Aurora_main.kicad_pcb
xvfb-run -a python3 size_comparison.py ../../cad ../../renders
python3 fit_pcb.py ../../cad/Aurora_main_pcb.step ../../docs/checks --kicad-pcb ../../kicad/Aurora_main/Aurora_main.kicad_pcb   # about 12 min
python3 assemble.py ../../cad ../../cad/Aurora_main_pcb.step ../../cad --kicad-pcb ../../kicad/Aurora_main/Aurora_main.kicad_pcb
```

## 2. Drawings (A3, 2:1, title blocks "v0.5 2026-10-14")

**Tray sheet 1 (AUR-H-01 1/2).** Top view (lid removed) with the tap chain 7 / 83.2 / 4.2 and
the zones 8.5 / 24.3 / 54.2 / 7.4 (94.4 overall); front view with the window bore Ø10.2 +0.05/0
and the laser bore Ø6.1 +0.05/0; sections C-C (front taps 4 × M1.6×0.35-6H, drill 1.25 × 3.6,
thread 2.6 min), B-B (PCB ledges Z 9.2 ±0.05, trough 15.4), D-D (laser axis, M2×0.4-6H from
below: drill 1.6, thread 2.85) and A-A (window axis: bore floor X 5.35 = LED-board contact face,
flat 0.03; LED wire grooves at 12 and 6 o'clock and their holes); side views with the USB-C
opening 12.6 × 6.8 R2.0 ±0.05, the S1 hole 3.4 × 2.4 and the S2 slot 3.2 × 2.0. Feature table
(13 items), notes on material, tolerances, edge breaks, finish (threads tapped before anodising)
and the thin walls.

**Tray sheet 2 (AUR-H-01 2/2).** Bottom view (knurl X 40.5–81.5 × 12.4, tail window 5.2 × 14 ×
1.0 deep from X 88.0, lanyard slot 4.4 × 7.6, laser-marking field X 8–37.5 × 15), side view
(V-ring at the lid seam, side grooves at Z 5.5 / 10.5, thumb dish SR8 at S1), tail view, section
F-F through the tail, details V (V-ring), K (knurl profile) and E-E (thumb dish: a full sphere,
centre Z 7.95 on the S1 axis, 0.6 deep).

**Lid (AUR-H-02).** RF window opening 6.9 × 14 R1.5 at X 31.8–38.7, underside pocket 8.5 × 15.6
R2.3 × 0.6 deep (0.9 mm of lid above it) for the flange of the resin insert; 4 countersunk
holes Ø1.8 / Ø3.3 × 90° at X 7.0 and 90.2, Y ±6.3; lanyard slot with C0.35 on the top face;
knurl X 40.5–81.5 — clear of the RF pocket, which ends at X 39.5.

**Checks run by `drawings.py`:** 227 distinct numbers on the sheets against their `P`
expression: 0 mismatches; 88 ray probes of the STEP solids against the drawn values: 0
mismatches; layout check of every sheet (overlapping texts, texts outside the frame, colliding
views): 0 findings. Every page was rendered and inspected.

## 3. Renders (`renders/`, 1600 px wide)

| PNG | Shows |
|---|---|
| `housing_closed_control_side.png` | closed, control side: USB-C opening, button cap in the thumb dish, side grooves, RF window with the status LED behind it, knurl, lanyard ring |
| `housing_closed_rear.png`, `housing_closed_bottom.png` | tail, S2 slot, bottom knurl, tail window, set-screw hole |
| `housing_front.png` | head: window, LED board, laser in its bore |
| `housing_open_top.png`, `housing_open_iso.png` | lid off: the routed PCB, S2, the antenna zone under the RF window, cells, lanyard slot |
| `housing_exploded.png` | every part, labelled |
| `housing_print_kit.png` | the print kit: RF window insert, button cap, spacer ring, antenna spacer on sprues |
| `size_comparison_A9.png` | v0.5 next to v0.4 and the RovyVon Aurora A9 Pro, same scale |

Size: v0.5 is 94.4 mm long, 88 % of v0.4 (107.6 mm) and 1.56 × the A9 Pro (60.5 mm); envelope
volume 30.2 cm³ = 0.84 × v0.4, 2.08 × the A9 Pro; aluminium about 29.5 g (v0.4: 39.3 g).

## 4. Housing checks (`aurora_housing.py`, every build)

All eight solids valid. Thinnest metal: **0.8 mm** where the upper LED wire groove passes under
the lid seat (X 4.2–5.35, covered by the lid) — exactly JLCCNC's minimum; then 0.825 (V-ring to
the window bore), 0.875 (front tap to the head's rear face), 0.9 (thumb dish to the cavity and
lid over the RF pocket), 1.0 (tail front wall). Laser module top 0.3 mm below the PCB. Button
cap: reaches the S1 actuator after 0.15 / 0.4 / 0.65 mm with the PCB at the −Y wall / centred /
at the +Y wall, touching nothing else. Simplified PCB: no interference centred; a 0.003 mm³
contact sliver against the cavity corner fillet when pushed to either wall.

## 5. Fit check with the real PCB (`docs/checks/fit_pcb_report.txt`)

The 56 solids of the PCB STEP (board + parts by designator) placed on the ledges (Z 9.2), plus
stand-ins for U4 (module + antenna overhang), J1 (USB-C 8.94 × 7.35 × 3.21), S1 (switch +
actuator), L1 (4 × 4 × 2) and LED3 (1 × 1 × 0.5) at their KiCad positions. Tested against tray,
lid, RF window insert, antenna spacer, button cap, spacer ring, both cells, laser, window, LED
board and LED. An overlap below 0.01 mm³ is a contact-level sliver (model tolerance).

| Pose | Collisions | Closest approach |
|---|---|---|
| PCB centred | **0** | tray 0.211 (J1), antenna spacer 0.150 (board), button cap 0.200, laser 0.300, cell 1.10 (U4), RF insert 1.90 (U4), lid 2.10 (U4) |
| PCB against the −Y wall (−0.24) | 0 (one 0.0026 mm³ sliver: board corner chamfer on the cavity fillet) | tray 0.000 (J1 — by design), button cap 0.110 (S1 actuator) |
| PCB against the +Y wall (+0.24) | 0 (same sliver, mirrored) | tray 0.252 (S2 knob) |

Free travel of the whole PCB from centred: ±Y 0.229, rear 0.149 (onto the antenna spacer),
front 0.261, up 0.393 (S2 knob in its slot). Insertion path (tilted about the X axis through
the S2 knob, +Y edge low, 9° → 0° in 12 steps, against tray, button cap and laser): no hit
above the generator's 0.002 mm³ threshold; J1 grazes the cavity corner fillet (≤ 0.0019 mm³)
from 9° to 6.75°, clear from 6°; S2 knob keeps ≥ 0.215 mm to the tray all the way.

## 6. Things to watch (none blocks ordering)

1. **0.8 mm wall** under the lid seat at the upper LED wire groove: at JLCCNC's limit. If JLCCNC
   objects, the groove can be made 0.2 mm shallower (`P.wire_groove`) — the 28 AWG PTFE wire
   (≤ 0.8 mm) still fits.
2. **J1 in the cavity corner:** the USB-C receptacle touches the corner fillet (0.000 mm) when
   the PCB lies against the −Y wall, which is where it is pushed by design; during the tilt-in
   the stand-in grazes the fillet (≤ 0.002 mm³) above 6°. Tilt the board only slightly (about
   5°, as the build guide says).
3. **3D models:** the PCB STEP has no models for U4, J1, S1, L1 and LED3; the checks use
   dimensioned stand-ins (`build_dummies`). Measure the real module height and the switch
   actuator on the first board.
4. **Countersinks:** the countersink edge is 0.05 mm inside the start of the R2.0 top edge — do
   not enlarge the countersinks (lid note 3).
5. **Print kit:** the button cap's flange is 0.6 mm, below JLC3DP's 0.8 mm recommended wall
   (the RF window's flange is 0.8 mm); the quote may warn. It prints in SLA resin; order a spare kit.
