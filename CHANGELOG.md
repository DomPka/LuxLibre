<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Changelog

All notable changes to LuxLibre. Versions follow [semantic versioning](https://semver.org/):
the firmware version is `LX_FW_VERSION` in `firmware/core/lx_version.h`.

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
