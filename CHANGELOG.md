<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Changelog

All notable changes to LuxLibre. Versions follow [semantic versioning](https://semver.org/):
the firmware version is `LX_FW_VERSION` in `firmware/core/lx_version.h`. A release that does not
change the firmware keeps its version.

## 0.3.0 - 2026-10-23

### Hardware

- FlashKa Keychain v0.7 reference design
  ([hardware/flashka-keychain-v07/](hardware/flashka-keychain-v07/README.md)), built on v0.6
  with the same module, charger, laser, ring and button ladder (no GPIO change):
  - a 1000 lm light: a Luminus SST-20 Gen 2 LED under a LEDiL LISA3-RS-PIN TIR optic (no front
    window), a TI TPS62095 4 A buck in the same current loop (full scale 3,552 mA), cell
    protection on the main board (DW01A and an SE8830A dual MOSFET in the cell minus, new net
    BATN, Kelvin-sensed; a trip switches the light off until USB is plugged in), new cell and LED
    pads with 24 AWG wires, and a body 4.8 mm longer than v0.6. Simulated: about 1,045 lm out of
    the front at switch-on (966 lm with the LED at 85 °C), 6,605 cd and 162.5 m of throw; full
    turbo for about 58 s and High (about 601 lm) for about 210 s from cold, then about 280 lm in
    25 °C still air, about 137 min from turbo to the low-voltage step-down;
  - one 14500 Li-ion cell, a Vapcell INR14500 F15 (1,500 mAh typical, 1,150 mAh minimum, 3 A, flat
    top, no protection board of its own; the Vapcell K10, 1,000 mAh and 8 A, is the documented
    alternative). Nickel strips welded to its ends carry the current (bought pre-tabbed or welded
    with a small spot welder; never soldered onto the cell); it lies on two floor rails, held by
    foam. R3 is 2.0 kΩ, so the charger gives about 500 mA, the F15's standard charge (a full
    charge in about 3.5 h; charging pauses while the board is above 45 °C, which is normal). The
    firmware's 2.8 A cell-current limit is 93 % of the cell's 3 A rating, a documented deviation
    from LuxLibre rule BAT-1 (turbo only). One cell sags under the turbo current, so turbo dims as
    the cell empties: 966 lm from a full cell, 775 lm from a half-full one (LED at 85 °C,
    simulated);
  - the three keys on the centre line of the bottom face, in a 0.5 mm deep bezel, their faces
    below the bottom face: a clear cast PMMA main key with a frosted ring that carries the light
    of the ring LEDs, and two black urethane rubber side keys (Shore A 80) with a raised chevron
    along the light (held like a presenter: ^ next, nearest the head, and v previous) and a
    glued-in stainless stiffener;
  - a key board (19.0 × 14.8 mm, 4 layers) with the three switches, the two ring LEDs and their
    resistors, screwed to two bosses of the floor; six gold pogo pins (Harwin P70-1010045R) join
    it to six new target pads on the main board; its silkscreen shows which way round it goes;
  - both boards in one JLCPCB panel (45.0 × 32.5 mm) with black solder mask;
  - no 3D-printed part in the light: the resin print kit, the stainless caps and the laser
    marking are gone. The PMMA main keys and the POM-C parts are ordered as two machining kits
    (JLCCNC machines plastic parts only from 30 × 20 × 8 mm), and the side keys are cast at home
    from Smooth-On ECON 80 in a resin mould printed by JLC3DP, with a machined aluminium mould as
    the durable option (drawing FK-H-08);
  - a rugged exterior: a faceted octagon of 99.2 × 20 × 18 mm (eight flat facets with 3.4 mm legs;
    the lid is a 3.4 mm cap on a flat seat, held by four M1.6 × 6 screws), recessed panels with a
    0.2 mm diagonal V texture and transverse grooves at the head and the tail; no marking at all, with an optional
    lid laser label for lights that are sold or given away; the laser set screw (now M1.6 × 5)
    sits under the lid instead of in the bottom face;
  - the lid pads now hold the main board against the 7.4 N of the pogo pins; a key press no
    longer lifts the main board;
  - comparison renders and a chart against the RovyVon Aurora A2 (beams, size, output over
    fifteen minutes), with the source of every number;
  - honest light figures: every lumen figure says whether it is at the LED or out of the front,
    and whether it is at switch-on or with the LED at 85 °C;
  - the cost: one light 859.28 USD and five lights 299.27 USD each, every fee, shipping and VAT
    included (v0.6 in 0.2.0: 620.21 and 239.00 USD). The optic, the 4 A driver, the protection,
    the key board and the cell's own parcel from an EU battery shop add cost; a printed resin casting mould, ECON 80
    rubber, one merged JLCCNC + JLC3DP parcel that stays below the EUR 150 customs line for one
    light, no front window and a cheaper LED board keep it down. The workbook prices the panel
    texture, economy shipping, a cheaper pogo pin and Sugru as options, each with what it costs
    in quality. A small spot welder for the cell's strips (about 40 USD) is a one-time tool, not
    needed with a pre-tabbed cell;
  - cost workbook, build guide, design chapter 14 and hardware package for v0.7; the build guide
    prints the laser warning label (made from the label artwork by
    `hardware/flashka-keychain-v07/tools/label_picture.py`).

  Designed and checked by software; not yet built.

### Firmware

- FlashKa firmware 0.7.0 for the FlashKa Keychain v0.7: one code base with a compile-time board
  selection (Cargo feature `board-v07`); LED ceiling 3.0 A enforced in one place; turbo 2,850 mA
  (about 966 lm out of the front, estimate) for 60 s, High 1,530 mA (about 601 lm), moonlight
  3 mA; new profiles; one Vapcell INR14500 F15: 1,400 mAh in the estimates, 130 mV/A load
  correction, the F15's voltage curve, charging at about 500 mA, low-voltage step-down
  3.15 / 3.20 / 3.25 V, a 2.8 A cell-current limit kept as a documented LuxLibre BAT-1 deviation
  (turbo only, at most 60 s, regulated); the battery percentage, the runtime and the reported LED
  current follow the current the driver can deliver from a part-empty cell. On the v0.7 the
  profile's temperature limit is the set point of a regulator (50 °C, Endurance 47 °C; it holds
  the light just below it and keeps turbo and High at full output until the temperature gets
  there). Simulated with the thermal model of the octagonal body and the cell, 25 °C still air:
  turbo 58 s at full output, High 210 s, then about 280 lm, about 137 min to the low-voltage
  step-down; turbo from a half-full cell about 775 lm. Reproducible image
  `flashka-fw-v0.7.0-merged.bin` (SHA-256 6554028f...). Firmware 0.6.0 for v0.6 boards unchanged
  (rebuilds byte for byte).
- Firmware installer: one page with both images and a required board choice ("FlashKa v0.7 -
  three keys in the middle" / "FlashKa v0.6 - stainless button"); it reads the firmware already
  on the light and asks for confirmation when it belongs to the other board; files for the other
  board are refused.
- Control app 0.7.0: recognises the board from the light; v0.7 profiles, 2,850 mA turbo limit and
  estimated lumens out of the front on a v0.7; demo light "FlashKa v0.7" with the same
  temperature regulator and the F15; the Custom editor explains the temperature limit per board;
  charge pauses are shown as normal.
- LuxLibre: board header `flashka-keychain-v07` for the F15 and the octagonal body (CI builds); a
  board header can give its cell's own open-circuit curve for the charge estimate
  (`LX_BAT_OCV_MV`) and, for the simulator, its curve and the driver's headroom (`LX_SIM_OCV_V`,
  `LX_SIM_DROP_MOHM`); simulator: LED flux table, optic factor and body model from the board
  header (`--preset board`), CSV column `lumens_front`. Boards without the new options build as
  before. The LuxLibre firmware version is now 0.3.0 (`ver` prints `LuxLibre 0.3.0`).

### Documentation

- Top README, hardware index and project site: FlashKa Keychain v0.7 as the current design,
  v0.6 as the previous one; banners and social preview made from the v0.7 renders (the script is
  `hardware/flashka-keychain-v07/tools/make_banners.py`).
- FlashKa v0.6 README: a note that v0.7 supersedes it and that its firmware sources build both
  versions. The v0.6 firmware, web and protocol documents describe firmware 0.7.0 as well
  (firmware.md, section 9).
- Reading paths and flashlight types name v0.7 as the current FlashKa; the firmware overview lists
  v0.7 among the ESP32-C3 boards with its own board header; SECURITY.md lists the 0.3.x line;
  the build report form asks for v0.7 builds (key board, machining kits, cast keys).
- Design rules and review checklist: DFM-7 is worded "fabrication outputs made by a script".

### CI

- The `flashka` workflow runs the host tests of both firmware variants, checks the v0.7 cost
  workbook and, in its experimental image job, builds both firmware images and compares them with
  `dist/`.
- The `firmware` workflow builds the simulator of every board header; its ESP-IDF job also builds
  the `flashka-keychain-v07` board.

## 0.2.0 - 2026-10-21

### Hardware

- FlashKa Keychain v0.6 reference design
  ([hardware/flashka-keychain-v06/](hardware/flashka-keychain-v06/README.md)), built on v0.5
  with the same body size, cells, LED, LED driver, laser, charger and module:
  - a stainless-steel main button in an RGB light ring (two ring LEDs on the three GPIOs of the
    old status LED);
  - two more buttons, next and previous, beside it on the bottom face; the side button S1 is gone;
  - presenter mode: the light becomes a Bluetooth LE HID keyboard (HID: human interface device,
    the standard for keyboards and mice) that turns slides;
  - the laser is the pointer in presenter mode, with the same limits and hardware interlock as in
    flashlight mode;
  - "fighter-jet skin": engraved panel seams, laser-marked rivet rows and stencils instead of the
    knurl and the side grooves;
  - PCB hold-down pads: lid bosses with silicone pads hold the board against its ledges when the
    buttons push it up;
  - a second RF window in the floor, under the antenna, so that Bluetooth also works with the
    bottom face up;
  - Bluetooth protocol version 2 for the web app (mode, number of paired computers, presenter
    settings and commands);
  - files renamed from the working name "Aurora" to FlashKa (the v0.5 folder keeps its names).

  Designed and checked by software; not yet built.
- FlashKa firmware 0.6.0 (Rust) with presenter mode, and the web app and firmware installer for
  protocol version 2. The firmware image is reproducible in any folder:
  `hardware/flashka-keychain-v06/firmware/build.sh`
  fixes the build date and maps the machine-specific source paths, and the two crates form one
  Cargo workspace. The same applies to the v0.5 firmware, whose image was rebuilt this way.

### Firmware

- Board header `flashka-keychain-v06`: the v0.5 pins, limits and defaults, with the buttons on a
  resistor ladder. Only the main button is used; next and previous serve the FlashKa firmware's
  level steps and presenter mode, which LuxLibre does not have.
- ESP32-C3 port: resistor-ladder buttons (`LX_ESP_BTN_LADDER_ADC_GPIO`, `LX_ESP_BTN_WAKE_GPIO`,
  `LX_ESP_BTN_MAIN_BELOW_MV`). The ladder pin is read with ADC1 at 2.5 dB and its own
  calibration, "pressed" means below the main-button threshold, a second pin on the same net wakes
  the chip from light sleep, and the other buttons are ignored (a held one is checked from light
  sleep instead of keeping the chip awake). Boards with one button are unchanged. Written against
  ESP-IDF 5.3; not yet compiled with ESP-IDF or tested on hardware.
- CI: the ESP32-C3 job also builds the v0.6 board and is marked experimental (allowed to fail)
  until it has been compiled once.
- CI: a new `flashka` workflow runs the FlashKa firmware host tests, rebuilds the firmware image
  and compares it with the published one (experimental), runs the web app and installer tests in
  a browser and checks the cost workbook.

### Documentation

- Hardware index: FlashKa Keychain v0.6 as the current design, v0.5 as the previous one.
- Porting guide and ESP32-C3 port README: resistor-ladder buttons (how a board declares them, the
  threshold, the wake pin, bring-up checks).
- Reading paths, flashlight types, simulator and firmware pages name both FlashKa versions.
- Project site on GitHub Pages (`site/`) with the FlashKa control app and firmware installer;
  a new top README with renders and web app recordings; SECURITY.md; a "build report" issue form.

## 0.1.0 - 2026-10-15

First public version.

### Firmware

- Portable core in C++17 (embedded subset): 150 geometric levels, ramp / modes / simple button
  layouts with a table-driven user interface, turbo with timer, battery check, beacon, SOS and
  strobe, lockout that survives reboots, factory reset, laser support with limits, momentary
  turbo on boards without a laser.
- Thermal regulation: PI regulator on a predicted temperature in fixed point without truncation
  dead zones; output hysteresis, a 5 s dwell before the output may move back, and an integral
  dead band, so that noisy or coarse sensors never cause flicker; gain ranges limited to values
  tested not to oscillate; a short off does not reset the cap; hard shutdown that a calibration
  offset can only make earlier; sensor-fault fallback.
- Battery: low-voltage warning, step-down and latched cut-off with a floor per chemistry that no
  setting can go below; cell current limit from the board's LED model; Li-ion, LiFePO4 and NiMH
  charge estimates; charging temperature window (ports may not even probe for USB outside it)
  and USB level cap.
- Pocket protection: stuck button ignored while dark (also on USB, where the charge window keeps
  running), light switched off and locked after `POCKET_S` while on; optional auto-lock.
- 50 ArduPilot-style parameters with ranges; storage with CRC-protected parameter block, a
  separate calibration block (in its own flash page) that survives factory resets and
  parameter-list changes, and a wear-spreading state ring; text console with `wdtest` watchdog
  test and `defaults [all]`.
- Ports: host simulator (tests), ATtiny1616 and CH32V003 (build and link, not yet tested on
  hardware), ESP32-C3 (experimental).
- PC simulator `luxsim` with keychain and 18650 models, sensor noise and resolution, and
  `make sim BOARD=<board>` for real board headers; plotting script; 47 unit and behaviour tests.
- ATtiny1616 brown-out fuse target (`make tiny1616-fuses`); ESP32-C3 brown-out detector and
  watchdog panic reset enabled.

### Documentation and tools

- Design rules (69 rules in 10 categories), choosing parts with a worked 1200 lm 18650 example,
  flashlight types, testing procedures, firmware architecture, porting and simulator guides.
- `tools/lux_calc.py` calculator (standby, runtime, cell current, throw, thermal, trace width,
  divider, NTC) with tests.
- Templates: requirements, design log, decision matrix, BOM, design-review checklist, test report.

### Hardware

- FlashKa Keychain v0.5 reference design (formerly "Aurora++"): KiCad, CAD, drawings, production
  files, cost workbook, build guide, the v0.5 Rust firmware with Bluetooth web app. Designed and
  checked by software; not yet built.
