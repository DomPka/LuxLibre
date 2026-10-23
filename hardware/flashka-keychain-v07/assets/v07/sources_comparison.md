<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa v0.7 vs RovyVon Aurora A2: sources of every number

The pictures `comparison_beams.png`, `comparison_size.png`, `comparison_output.png`, `comparison_combined.png` and `comparison_combined_dark.png` in this folder are made by [`tools/compare/compare_a2.py`](../../tools/compare/compare_a2.py). Rerun (needs Rust/cargo for the FlashKa firmware simulation, VTK, cadquery, trimesh, numpy, scipy, Pillow, matplotlib and an X server or `xvfb-run`):

```sh
cd hardware/flashka-keychain-v07/tools/compare
xvfb-run -a python3 compare_a2.py ../../cad ../../assets/v07
```

**FlashKa Keychain v0.7 has not been built.** Its light figures are simulated: the FlashKa firmware 0.7.0 thermal simulation gives the LED current and the head temperature over time, the Luminus SST-20 Gen 2 datasheet gives the LED's lumens, and the LEDiL datasheet (LEDiL's own simulation) gives the optic's efficiency, beam width and intensity. Its size comes from the CAD; its mass is an estimate. Every picture of it is a render. The RovyVon Aurora A2 figures are the maker's data (retail listings) and the independent measurement published by 1lumen. Labels: *simulated*, *datasheet*, *model*, *CAD*, *estimate*, *maker's data*, *measured*.

## Which RovyVon Aurora A2

| Generation | What is known | Used here |
|---|---|---|
| Gen 1 (2018) | Cree XP-G3, 550 lm, 980 cd, 80 m, 130 mAh, micro-USB, 53.9 x 14.5 mm, 28 g ([BudgetLightForum review](https://budgetlightforum.com/t/-/54488)) | no: older design |
| Gen 3 (2022) | Luminus SST-20 cool white, 650 lm, 2,500 cd, 110 m, 300 mAh LiPo, USB-C, 57.3 x 15.6 mm; **measured by [1lumen](https://1lumen.com/review/rovyvon-a2/)** (September 2022) | the measurement: light output, intensity, throw |
| Gen 4 (G4, sold in 2026) | SST-20 6500 K 650 lm (or Nichia 219C 420 lm), High 650 lm stepping down to 100 lm after 60 s, 110 m, 300 mAh LiPo, USB-C, 57.3 x 15.6 mm, 33.9 g ([Adventure Carry](https://www.adventurecarry.com/products/aurora-a2-usb-c), [Kapuga](https://kapuga.pl/produkt/rovyvon-aurora-a2-g4-silver-650-lm-keychain-flashlight), [Mukama](https://www.mukama.com/products/rovyvon-aurora-a2-stainless-steel-g4-flashlight)) | the maker's data: size, battery, weight, step-down |

Gen 3 and Gen 4 share the LED, the 650 lm rating, the 110 m beam distance, the 300 mAh cell and the 57.3 x 15.6 mm size, so the Gen 3 measurement is the best public stand-in for the current light; no independent test of Gen 4 was found. That the two generations perform the same is an assumption. The official rovyvon.com product page could not be opened from the machine that made these pictures, so the maker's figures are taken from the specification table that 1lumen copied from the maker (Gen 3) and from the Gen 4 retail listings above.

## Numbers in the pictures

FlashKa values are for the Balanced profile (the default) at 25 °C in still air with a full battery; "switch-on" is the first simulated second.

| Number | FlashKa v0.7 | Source / kind | RovyVon Aurora A2 | Source / kind |
|---|---|---|---|---|
| Light output at switch-on (out of the front) | 1,045 lm | simulated: 1,201 lm at the LED (datasheet model 1,111 lm at 2,850 mA and Tj 85 °C, x 1.081 for Tj 36.4 °C) x 0.87 optic | 633 lm | measured, [1lumen](https://1lumen.com/review/rovyvon-a2/), Gen 3 |
| Maker's rating | - | - | 650 lm | maker's data ([1lumen spec table](https://1lumen.com/review/rovyvon-a2/), [Adventure Carry](https://www.adventurecarry.com/products/aurora-a2-usb-c)) |
| Light output at 30 s (the ANSI FL 1 time) | 1,019 lm | simulated: 2,850 mA (thermal regulation from 58 s), Tj 52.6 °C, x 1.054 | 394 lm | measured, [1lumen](https://1lumen.com/review/rovyvon-a2/) |
| Light output with the LED at Tj 85 °C (datasheet reference, turbo current) | 966 lm | datasheet model 1,111 lm x 0.87; the simulation never gets the LED that hot (highest Tj 60 °C) | - | - |
| Light output after 10 min | 325 lm (turbo at the start), 331 lm (High at the start) | simulated | 118 lm | measured, [1lumen](https://1lumen.com/review/rovyvon-a2/) |
| Sustained output, 25 °C still air (mean of 15-25 min) | 296 lm (about 622 mA, Tj 52 °C; 281 lm with the LED at 85 °C) | simulated | - | - |
| Peak intensity | 6,605 cd at switch-on (6,440 cd at 30 s; 6,110 cd at Tj 85 °C) | 5.5 cd per LED lumen (LEDiL datasheet, simulated) x LED lumens | 3,775 cd at switch-on (2,750 cd at 30 s; maker: 2,500 cd for Gen 3) | measured, [1lumen](https://1lumen.com/review/rovyvon-a2/) |
| Throw (ANSI FL 1: distance to 0.25 lx = 2 sqrt(cd)) | 162.5 m at switch-on (160.5 m at 30 s; 156.3 m at Tj 85 °C) | from the peak | 123 m at switch-on (105 m at 30 s; maker: 110 m) | 1lumen's published value; maker's data |
| Illuminance at the wall centre, 2 m | 1,650.7 lx | E = I0 / d^2 (d from the optic's exit) | 943.8 lx | E = I0 / d^2 with 1lumen's 3,775 cd |
| Size | 99.2 x 20.0 x 18.0 mm | CAD (`cad/FlashKa_tray.stl`) | 57.3 mm x 15.6 mm diameter | maker's data, confirmed by 1lumen |
| Weight | about 62 g (62.3 g: breakdown below) | CAD + estimate, not weighed | 19.5 g (1lumen page) to 33.9 g (Gen 4 listing at Adventure Carry; 34 g for the stainless version at Mukama) | 1lumen / maker's data |
| Battery | 1,500 mAh typical, 1,150 mAh minimum (both at 0.2C): one [Vapcell INR14500 F15](https://www.vapcelltech.com/h-pd-251.html) Li-ion cell, 14.0 x 49.0 mm, 3.60 V nominal, 3 A maximum continuous, about 22 g; the firmware's runtime estimates use 1,400 mAh, the simulation 1,500 mAh | maker's data; firmware board.rs; simulation | 300 mAh LiPo, built in | maker's data |
| Extras | Class 2 laser, Bluetooth presenter mode | design | none listed by the maker | maker's data |
| Runtime from turbo (not in the pictures) | 137.1 min to the ANSI end point (10 % of the 30 s output), off after 235.0 min | simulated | 1 h 04 min to the ANSI end point, off at 1 h 07 min | measured, [1lumen](https://1lumen.com/review/rovyvon-a2/) |

Mass (estimate, not weighed): parts in the housing CAD 32.84 g (tray 22.487 g, lid 8.426 g, rf_window 0.166 g, antenna_spacer 1.164 g, key_main 0.134 g, key_side 0.064 g, key_side_prev 0.064 g, key_stiffener 0.087 g, key_stiffener_prev 0.087 g, laser_sleeve 0.156 g; `housing_interface.json`, 6061 aluminium 2.70 g/cm3 and the other materials' densities); optic 0.575 g and copper LED board 1.126 g (same file); cell 22 g (one Vapcell INR14500 F15, about 22 g: maker's data); electronics 5.75 g (estimate: main board with the ESP32-C3 module 2.70 g, key board and pogo pins 0.70 g, laser module 1.20 g, LED 0.05 g, lid and key-board screws 0.60 g, wires (24 AWG power, thin signal) 0.50 g). Not counted: tape, foam and the cell's nickel strips (a fraction of a gram).

## FlashKa: simulated output

The FlashKa firmware's own controller (firmware 0.7.0 for the v0.7 board) drives a thermal and battery model of the light in a host test, [`hardware/flashka-keychain-v06/firmware/flashka-core/tests/thermal_v07.rs`](../../../flashka-keychain-v06/firmware/flashka-core/tests/thermal_v07.rs): head 7.06 J/K, body 21.07 J/K, the cell as a third node of 22 J/K coupled to the body by 8 K/W (estimate), head to body 2.2 K/W, body to still air at 25 °C 13.20 K/W, temperature sensor following the head with a 4 s time constant; one cell of 1,500 mAh with a generic 3.6 V open-circuit curve (no F15 curve is published), 0.10 ohm from the cell to the board and, when the cell sags and the buck runs at 100 % duty, at most (V - 2.80 V) / 0.31 ohm for the LED, LED 2.80 V + 0.15 V/A, 87 % from the cell to the LED, 30 % of the LED power leaves as light, 20 mA for the controller and radio. The boards, keys and optic store no heat in the model and nobody holds the light, so the times are on the short side. This script runs it (the build folder stays outside the repository):

```sh
cd hardware/flashka-keychain-v06/firmware/flashka-core
FLASHKA_SIM_CSV=<dir> CARGO_TARGET_DIR=<tmp>/target cargo test --offline --locked --features board-v07 --test thermal_v07 -- --nocapture
```

It writes one row per second; the scenarios used are `flashka_v07_balanced_turbo` (Turbo, 2,850 mA, 60 s timer, then High) and `flashka_v07_balanced_high` (High, 1,530 mA), both from a full cell. Turbo runs at full current for 58 s, High for 210 s; then the thermal regulation holds the head and both settle at the same level.

| Time | Turbo: LED current | head | Tj | factor | LED lumens | out of the front | High: LED current | out of the front |
|---|---|---|---|---|---|---|---|---|
| 1 s | 2,850 mA | 26.1 °C | 36.4 °C | 1.081 | 1,201 lm | 1,045 lm | 1,530 mA | 655 lm |
| 10 s | 2,850 mA | 33.4 °C | 43.7 °C | 1.069 | 1,187 lm | 1,033 lm | 1,530 mA | 651 lm |
| 30 s | 2,850 mA | 42.3 °C | 52.6 °C | 1.054 | 1,171 lm | 1,019 lm | 1,530 mA | 647 lm |
| 57 s | 2,850 mA | 49.6 °C | 59.9 °C | 1.042 | 1,157 lm | 1,007 lm | 1,530 mA | 643 lm |
| 59 s | 2,731 mA | 50.0 °C | 59.8 °C | 1.042 | 1,120 lm | 974 lm | 1,530 mA | 643 lm |
| 60 s | 2,651 mA | 50.2 °C | 59.7 °C | 1.042 | 1,095 lm | 953 lm | 1,530 mA | 643 lm |
| 90 s | 1,530 mA | 48.1 °C | 53.3 °C | 1.053 | 727 lm | 632 lm | 1,530 mA | 640 lm |
| 2 min | 1,530 mA | 49.6 °C | 54.8 °C | 1.050 | 725 lm | 631 lm | 1,530 mA | 637 lm |
| 3 min | 1,027 mA | 50.1 °C | 53.5 °C | 1.052 | 521 lm | 454 lm | 1,529 mA | 630 lm |
| 5 min | 880 mA | 50.0 °C | 52.9 °C | 1.053 | 459 lm | 399 lm | 977 mA | 435 lm |
| 10 min | 685 mA | 50.0 °C | 52.2 °C | 1.055 | 373 lm | 325 lm | 700 mA | 331 lm |
| 15 min | 632 mA | 50.0 °C | 52.0 °C | 1.055 | 346 lm | 301 lm | 638 mA | 304 lm |
| 20 min | 620 mA | 50.0 °C | 52.0 °C | 1.055 | 340 lm | 296 lm | 623 mA | 297 lm |
| 30 min | 611 mA | 49.8 °C | 51.8 °C | 1.055 | 335 lm | 292 lm | 613 mA | 293 lm |

Highest simulated temperatures: head 50.5 °C, body 46.5 °C (the surface held in the hand), cell 46.7 °C, LED junction 60.0 °C (Tj model below).

### Turbo and the cell's charge

One Li-ion cell sags under load: below a certain charge the buck runs at 100 % duty and the LED gets less than the 2,850 mA asked for. From a half-full cell (`flashka_v07_turbo_half_cell`) turbo starts at 2,139 mA = 848 lm out of the front (junction factor; 780 lm with the LED at 85 °C) instead of 1,045 lm. Turbo 30 s after switching on, by the charge at switch-on (LED current printed by the simulation test; lumens out of the front with the LED at 85 °C, the firmware's model, and with this script's junction factor; head temperature from the full-cell and half-full-cell runs, for the other charges interpolated in LED power, estimate):

| Charge at switch-on | LED current at 30 s | Out of the front, LED at 85 °C | Out of the front, junction factor |
|---|---|---|---|
| 100 % | 2,850 mA | 966 lm | 1,019 lm |
| 90 % | 2,780 mA | 948 lm | 1,001 lm (estimate) |
| 75 % | 2,658 mA | 916 lm | 969 lm (estimate) |
| 50 % | 2,119 mA | 775 lm | 828 lm |
| 25 % | 1,696 mA | 651 lm | 700 lm (estimate) |

## FlashKa: LED lumens and junction temperature

- LED: Luminus SST-20 Gen 2, 6500 K, G1 bin. [Luminus datasheet](https://download.luminus.com/datasheets/Luminus_SST-20-WS_Gen%202_Datasheet.pdf): G1 bin minimum 680 lm at 1.5 A and 1,156 lm at 3.0 A (both Tj 85 °C), 748 lm at 1.5 A and Tj 25 °C; thermal resistance junction to solder point 1.6 °C/W; 3.0 A maximum DC.
- The firmware's LED model (`hardware/flashka-keychain-v06/firmware/flashka-core/src/board.rs`, `LED_LM_TABLE`, mA -> lm at the LED, Tj 85 °C, linear between the points): 0 mA 0 lm, 350 mA 191 lm, 700 mA 361 lm, 1,000 mA 485 lm, 1,500 mA 680 lm, 2,000 mA 855 lm, 3,000 mA 1,156 lm. The 1.5 A and 3.0 A points are the datasheet's G1 minimum; the other points are the firmware's estimates, not datasheet values. The simulator's LED lumens are this table at the simulated current (checked below).
- Junction factor: relative flux 1.10 at Tj 25 °C to 1.00 at Tj 85 °C, linear (748 / 680 lm = 1.100 from the datasheet at 1.5 A; assumed to hold at every current).
- Tj = simulated head temperature + 1.6 °C/W x 70 % x LED power, LED power = (2.80 V + 0.15 V/A x I) x I (the simulation's LED model). Assumption: 70 % of the LED's electrical power is heat (the simulation counts the other 30 % as light). Not counted: the copper LED board and the 0.1 mm thermal paste between the LED's solder point and the head; at about 0.3 K/W (estimate for that paste layer over the 78.5 mm2 contact) they would add about 2 K at turbo, i.e. about 0.3 % less light.
- Switch-on (first simulated second): head 26.09 °C, 2,850 mA, LED power 9.20 W, Tj 36.4 °C, factor 1.081, 1,201 lm at the LED. At 30 s: head 42.27 °C, 2,850 mA, Tj 52.6 °C, factor 1.054, 1,171 lm. Hot reference: Tj 85 °C, factor 1.000, 1,111 lm.

## FlashKa: optic model (no front window)

- Optic: LEDiL LISA3-RS-PIN (FP16558). [LEDiL datasheet](https://www.ledil.com/data/prod/Lisa/16558/16558-ds.pdf), row for the SST-20 Gen 2 (simulated by LEDiL, not measured): 87 % efficiency, 20 deg FWHM, 5.5 cd/lm. The firmware uses the same 87 % (`OPTIC_PCT` in board.rs). The optic's front face is the exit: no window in front of it.
- Intensity per LED lumen: I(theta) = a exp(-theta^2 / (2 sigma^2)) + b cos(theta) S(theta), S = raised-cosine edge from 50 to 70 deg. Conditions: a + b = 5.5 cd/lm, 2 pi x integral(I sin theta dtheta) = 0.87, I(10 deg) = I(0) / 2. Solved: sigma = 8.431 deg, a = 5.4425 cd/lm, b = 0.0575 cd/lm (1.0 % of the peak). The core carries 84.5 % of the light out of the front, the spill 15.5 %.
- So the datasheet's three numbers need about 15.5 % of the light outside a Gaussian core. The peak, the lumens and the wall-centre illuminance do not depend on this split; the spill's brightness does:

| Assumption | Spill share | sigma | Spill brightness at 25-45 deg (base = 1) |
|---|---|---|---|
| base: edge 50-70 deg, cos spill, 20 deg FWHM, 5.5 cd/lm, 87 % | 15.5 % | 8.43 deg | 1.00 |
| spill edge 35-55 deg | 16.8 % | 8.39 deg | 1.39 |
| spill edge 60-80 deg | 15.1 % | 8.44 deg | 0.85 |
| spill shape cos^2 | 16.2 % | 8.41 deg | 1.08 |
| FWHM 19 deg | 24.9 % | 7.97 deg | 1.46 |
| FWHM 21 deg | 5.4 % | 8.90 deg | 0.53 |
| peak 5.5 cd/lm - 5 % | 20.5 % | 8.41 deg | 1.27 |
| peak 5.5 cd/lm + 5 % | 10.5 % | 8.45 deg | 0.73 |
| efficiency 85 % | 13.1 % | 8.44 deg | 0.85 |
| efficiency 89 % | 17.8 % | 8.42 deg | 1.15 |

  The FWHM and the peak decide the split most: one degree of FWHM moves the spill share by about 10 points, so the spill in the picture is uncertain by a factor of about 2; the hotspot is not.
- Bore: the optic's front (holder rim) sits 0.2 mm behind the front face (0.0-0.4 mm with the optic's height tolerance) in the 10.10 mm bore; a ray from the edge of the 8.6 mm exit clears the bore mouth up to 75.1 deg (nominal) or 61.9 deg (deepest seat; `housing_interface.json`). The model sends 0.28 % of the light beyond 61.9 deg and 0.000 % beyond 75.1 deg, so the bore can take at most about 0.3 % (not subtracted).
- Emission point in the beam scene: the centre of the optic's exit face, 0.35 mm behind the light's front face (the lens in `_ref_optic_lens.stl`), on the LED axis.
- Plausibility: the model gives 6.32 cd per lumen out of the front (5.5 / 0.87); the A2 measured 5.96 cd/lm at switch-on (3,775 cd / 633 lm, 1lumen).

## RovyVon Aurora A2: beam model (TIR optic)

- I(theta) = I_h exp(-theta^2 / (2 sigma^2)) + I_s cos(theta) S(theta), S = raised-cosine edge from 50 to 70 deg.
- Conditions: I(0) = I_h + I_s = 3,775 cd and 2 pi x integral(I sin theta dtheta) = 633 lm (1lumen, at switch-on); the spill carries an assumed 25 % of the light (TIR optics put most light into the hotspot; 1lumen describes "a defined hotspot with a light spill").
- Solved: I_h = 3,708 cd, I_s = 67.4 cd, sigma = 8.21 deg (hotspot 19.3 deg wide at half maximum). Peak and lumens are matched exactly; the ANSI throw 2 sqrt(I0) = 123 m equals 1lumen's published 123 m.
- What the assumption changes: the wall-centre illuminance and the lumens do not depend on it. A spill share of 15 % or 35 % would make the hotspot about 1 deg wider or narrower and the far spill about 40 % weaker or stronger.

## How the beam picture is made

- Scene (mm): dark matte table (reflectance 0.016, satin finish: GGX microfacet sheen, F0 = 0.04, roughness 0.40), each light resting at the table edge, white matte wall (reflectance 0.85) 2000 mm in front of the lights, a dim room (3 lx everywhere) and a small warm spot lamp on the light body that does not reach the wall; the same in both panels. Haze: 0.004 /m, single scattering, isotropic.
- Wall and table luminance in numpy from E = I(theta) cos(alpha) / d^2 and L = rho E / pi (direct light). The light that the lit wall reflects onto the table (4.0 lx for the FlashKa and 2.5 lx for the A2, on the table next to the head) is left out: on the dark table it stays below the black point of the tone curve, and it does not change the wall. Light bodies: VTK physically based rendering, lit by the environment they see (the computed wall, the room, the lamp); soft shadows and ambient occlusion from VTK depth maps. Both beams are drawn in the same neutral white, so colour plays no part in the comparison.
- One exposure and one tone curve for both panels: white point = 1.10 x the brightest wall luminance (the FlashKa's wall centre), a log2 curve over 10.0 stops with a power toe of 1.70, sRGB output, dither. The same luminance gives the same pixel value in both panels.
- The A2 is drawn as a plain size stand-in (rounded tube, lens face, one clip ring) from its published size; no logo, no lettering and no design details of the real light.
- The size views show the CAD of the v0.7 housing with the optic (clear lens drawn see-through, black holder), the laser module, the USB-C socket, the screws and the RF window where they are visible; parts inside the body are left out.

## Checks run with every picture

- [PASS] simulator LED lumens = board.rs LED_LM_TABLE, every row (lm) 0.0500 vs 0.0000 (deviation 0.050, limit 0.060)
- [PASS] simulator front lumens = OPTIC_PCT x LED lumens, every row (lm) 0.0500 vs 0.0000 (deviation 0.050, limit 0.060)
- [PASS] board.rs OPTIC_PCT = LEDiL efficiency used here (%) 87.0000 vs 87.0000 (deviation 0.000, limit 0.000)
- [PASS] junction factor at Tj 25 C (datasheet 748 / 680 lm) 1.1000 vs 1.1000 (0.000 %, limit 0.10 %)
- [PASS] junction factor at Tj 85 C 1.0000 vs 1.0000 (0.000 %, limit 0.00 %)
- [PASS] Lambertian 1000 lm: angular integral (lm) 999.9999 vs 1000.0000 (0.000 %, limit 0.01 %)
- [PASS] Lambertian 1000 lm: 40 m wall at 2 m = view factor (lm) 991.8856 vs 991.8856 (0.000 %, limit 0.20 %)
- [PASS] FlashKa optic model: grid integral = quadrature (per LED lm) 0.8700 vs 0.8700 (0.000 %, limit 0.01 %)
- [PASS] FlashKa: peak = 5.5 cd/lm x LED lumens (cd) 6604.9356 vs 6604.9356 (0.000 %, limit 0.00 %)
- [PASS] FlashKa: angular integral = 0.87 x LED lumens (lm) 1044.7807 vs 1044.7807 (0.000 %, limit 0.01 %)
- [PASS] FlashKa: full width at half maximum (deg) 20.0000 vs 20.0000 (0.000 %, limit 0.10 %)
- [PASS] FlashKa: wall integral at 2 m = lumens (lm) 1044.7820 vs 1044.7807 (0.000 %, limit 0.50 %)
- [PASS] FlashKa: inclined plane (40 deg): area = solid-angle flux 995.5313 vs 995.5340 (0.000 %, limit 0.50 %)
- [PASS] FlashKa: E d^2 on axis at 2 m = peak (cd) 6604.9356 vs 6604.9356 (0.000 %, limit 0.00 %)
- [PASS] FlashKa: E d^2 on axis at 5 m = peak (cd) 6604.9356 vs 6604.9356 (0.000 %, limit 0.00 %)
- [PASS] A2: angular integral = its lumens (lm) 633.0000 vs 633.0000 (0.000 %, limit 0.10 %)
- [PASS] A2: peak = its candela (cd) 3775.0000 vs 3775.0000 (0.000 %, limit 0.00 %)
- [PASS] A2: wall integral at 2 m = lumens (lm) 633.0007 vs 633.0000 (0.000 %, limit 0.50 %)
- [PASS] A2: inclined plane (40 deg): area = solid-angle flux 585.1411 vs 585.1430 (0.000 %, limit 0.50 %)
- [PASS] A2: E d^2 on axis at 2 m = peak (cd) 3775.0000 vs 3775.0000 (0.000 %, limit 0.00 %)
- [PASS] A2: E d^2 on axis at 5 m = peak (cd) 3775.0000 vs 3775.0000 (0.000 %, limit 0.00 %)
- [PASS] FlashKa panel: flux into the visible wall area, pixel sum 924.37 lm vs angular 924.37 lm (0.00 %, limit 0.5 %)
- [PASS] FlashKa panel: VTK light body and numpy camera agree within 0.35 px (limit 1.5 px at the final scale)
- FlashKa panel: the haze glow adds 1.09 % to the wall luminance at the marked wall centre and 0.74 % in the middle of the beam spot (median of the wall points with at least 10 % of the brightest illuminance); at most 110 % just above the light, where the line of sight passes close to its head
- [PASS] A2 panel: flux into the visible wall area, pixel sum 523.41 lm vs angular 523.41 lm (0.00 %, limit 0.5 %)
- [PASS] A2 panel: VTK light body and numpy camera agree within 0.36 px (limit 1.5 px at the final scale)
- A2 panel: the haze glow adds 1.09 % to the wall luminance at the marked wall centre and 0.80 % in the middle of the beam spot (median of the wall points with at least 10 % of the brightest illuminance); at most 103 % just above the light, where the line of sight passes close to its head
- exposure: one white point for both panels, 1.100 x 447.4 cd/m2 (brightest wall point); tone curve: log2, 10.0 stops, power 1.70

## Not verified

- FlashKa v0.7 has not been built: no measured lumens, candela, runtime, temperatures or mass. The first build should measure them (docs/testing.md).
- The optic figures are LEDiL's simulation for the SST-20 Gen 2, not a measurement. How well the LED is centred and seated under the optic (pins cut off, optic glued in the bore) changes the peak and is not modelled. The core/spill split is a model choice (table above).
- The LED's flux between and below the datasheet's 1.5 A and 3.0 A points is the firmware's estimate; the junction factor assumes the 1.5 A ratio (25 °C / 85 °C) at every current; the LED board and paste under the LED are not in the Tj model; the thermal model has no hand, stores no heat in the boards, keys and optic, and couples the cell to the body with an estimated 8 K/W.
- The cell: no independent test of the Vapcell INR14500 F15 at 3 A was found; the simulation uses a generic open-circuit curve (no F15 curve is published) and about 0.10 ohm from the cell to the board (its DC resistance estimated from the maker's 60 mOhm AC value). The runtime is for a typical cell (1,500 mAh); a cell at the maker's minimum (1,150 mAh) would run about 77 % as long (proportional estimate). The electronics mass is an estimate.
- No independent measurement of the Gen 4 A2 was found; the Gen 3 measurement stands in for it. The official rovyvon.com page could not be opened from here; 1lumen's runtime graphs exist only as pictures, so the chart shows the three published points (switch-on, 30 s, 10 min) without a line between them.
- The A2 beam shape (hotspot width, spill) is a model fitted to its lumens and candela with an assumed spill share; the real TIR beam has a sharper hotspot edge and faint rings.
- The weight of the A2 differs between sources: 19.5 g on 1lumen's page, 33.9 g at Adventure Carry (whose page names both an aluminium and a stainless body) and 34 g for the stainless Gen 4 at Mukama; the pictures show the range.
