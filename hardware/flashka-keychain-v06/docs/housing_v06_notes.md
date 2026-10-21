<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.6 housing: files, rebuild, checks (2026-10-16)

Housing 94.4 x 20 x 16 mm, 6061-T6 tray + lid, 2 cells. Source of truth: `tools/housing/flashka_housing.py` (class `P` holds
every parameter; the build functions and the checks are in the same file). Output: `cad/` (STEP, STL, `housing_interface.json`).
Every number and every check result is in chapter 13 (`docs/ch13_v0.6_presenter.md`, section 13.4) and in the logs in `docs/checks/`.

## 1. Files

| File | What |
|---|---|
| `cad/FlashKa_tray.step`, `FlashKa_lid.step` | aluminium parts with the skin seams |
| `cad/FlashKa_cap_main.step`, `FlashKa_cap_slide.step` | stainless caps, axis through the origin |
| `cad/FlashKa_tube.step`, `FlashKa_rf_window`, `FlashKa_spacer_ring`, `FlashKa_antenna_spacer` | resin parts |
| `cad/FlashKa_print_kit.stl/.step`, `FlashKa_laser_sleeve` | resin kit on sprues (tube, 3 resin caps, spacers, window insert) |
| `cad/FlashKa_tray_drawing.pdf` (2 sheets), `_lid_`, `_cap_main_`, `_cap_slide_`, `_tube_drawing` (.pdf .dxf .png) | A3 drawings, 2:1 (caps and tube 10:1 details) |
| `cad/FlashKa_marking_lid_class2/_class3R/_bottom/_minus_y/_plus_y` (.dxf .png) | laser artwork, 1:1 |
| `cad/housing_interface.json` | parameters + all check results (keys `components` and `pcb_outline` are read by the PCB build: do not change) |
| `renders/`, `assets/v06/` | pictures |
| `order_files/2_JLCCNC`, `3_JLC3DP` | upload files with a README each |
| `docs/checks/housing_v06_*.txt` | build log, drawing number table, size comparison |

## 2. Rebuild (from `tools/housing/`)

```
python3 flashka_housing.py ../../cad                      # solids + all checks, about 75 s
python3 flashka_marking.py ../../cad ../../cad --tex-dir ../../cad
FK_CACHE=.fk_cache python3 drawings.py ../../cad ../../cad
xvfb-run -a python3 render.py ../../cad ../../renders
python3 render_marking.py ../../cad ../../renders
xvfb-run -a python3 size_comparison.py ../../cad ../../renders
python3 fit_pcb.py ../../cad/FlashKa_main_pcb.step ../../docs/checks    # only when the PCB STEP exists
python3 assemble.py ../../cad ../../cad/FlashKa_main_pcb.step ../../cad
```
`flashka_housing.py --interface-only` writes only the JSON (fast). `--no-checks` skips the slow checks.

## 3. Design points in short

* Buttons on the bottom face at Y +3.2: SW2 next X 16.4, SW1 main X 23.6, SW3 previous X 30.8. Main cap in a resin light-pipe
  tube (ring LEDs at X 19.8 and 27.4, lit ring = the end face of the tube, Ø6.0 to Ø8.4). Slide caps sit on the floor.
* Floor RF window 5.1 x 14.0 (X 33.6 to 38.7) closed by a plug on the antenna spacer. S1 is removed.
* Hold-down: two lid bosses with bought pads, both compressed to 0.8 mm: can boss 8.8 x 12.4 x 1.3 + 1.0 mm gap pad; front boss 3.7 x 3.2 x 3.7 next to SW2 + 1.0 mm silicone rubber (Shore A 70).
* Skin: V grooves 0.25 deep. Frames at X 10.2, 30.1, 41, 56, 71, 86 and the V ring at X 3.95; stringers on the sides
  (Z 3.0, 13.0), lid and bottom (Y +/-3.6). Lid and tray meet in a 0.6 mm rabbet so seams cross the joint on the flat side.
* Marking: SAFE toward the head, ARM toward the tail (armed = knob toward the tail, as in v0.5). The chevrons at X 16.4 (next) point to the head, at X 30.8 (previous) to the tail.

## 4. Open points

See chapter 13, section 13.9 (hold-down: SW3 over the 0.05 mm limit at 10 N, accepted for v0.6, section 13.4.5) and the layout notes printed by `drawings.py`. The fit check with the real PCB model passed: `docs/checks/fit_pcb_report.txt`.
