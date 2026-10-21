<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/luxlibre_banner_dark.png">
  <img alt="LuxLibre: open-source firmware, design rules and reference designs for flashlights. On the right, a render of the FlashKa Keychain v0.6 with its lit ring." src="docs/img/luxlibre_banner_light.png">
</picture>

# LuxLibre

[![firmware](https://github.com/DomPka/LuxLibre/actions/workflows/firmware.yml/badge.svg)](https://github.com/DomPka/LuxLibre/actions/workflows/firmware.yml)
[![flashka](https://github.com/DomPka/LuxLibre/actions/workflows/flashka.yml/badge.svg)](https://github.com/DomPka/LuxLibre/actions/workflows/flashka.yml)
[![pages](https://github.com/DomPka/LuxLibre/actions/workflows/pages.yml/badge.svg)](https://github.com/DomPka/LuxLibre/actions/workflows/pages.yml)
[![version](https://img.shields.io/badge/version-0.2.0-0b7a83)](CHANGELOG.md)
[![firmware licence](https://img.shields.io/badge/firmware-GPL--3.0--or--later-blue)](LICENSING.md)
[![hardware licence](https://img.shields.io/badge/hardware-CERN--OHL--W--2.0-blue)](LICENSING.md)
[![docs licence](https://img.shields.io/badge/docs-CC--BY--SA--4.0-blue)](LICENSING.md)

**Open-source flashlights, from the first requirement to the finished light.** LuxLibre is a
firmware, a set of design rules, a guide to choosing parts and test procedures for any kind of
flashlight (keychain lights, everyday-carry lights, headlamps, throwers, bicycle and dive lights),
and complete reference designs, so far the FlashKa keychain light. Anyone may build, change and
sell lights made with it, companies included ([LICENSING.md](LICENSING.md)).

**[Try the FlashKa web app](https://dompka.github.io/LuxLibre/flashka/flashka-app.html)** (demo
mode, no light needed) · **[FlashKa v0.6](hardware/flashka-keychain-v06/README.md)** ·
**[Build guide (PDF)](hardware/flashka-keychain-v06/FlashKa_v0.6_Build_Guide.pdf)** ·
**[Design rules](docs/design-rules.md)** · **[Firmware](docs/firmware/README.md)**

## FlashKa Keychain v0.6

![FlashKa Keychain v0.6 turning on a turntable: bottom face with the three stainless caps and the lit ring, sides, lid with the laser label (render)](hardware/flashka-keychain-v06/assets/v06/flashka_v06_turntable.gif)

*Render made from the design files. FlashKa has not been built yet: everything below is checked
by software, and the first prototype is the next step.*

The first reference design is a 94.4 × 20 × 16 mm aluminium keychain light with a laser pointer.
Version 0.6 adds a stainless-steel main button with a glowing ring and two more buttons that turn
slides: in **presenter mode** the light is a Bluetooth keyboard meant for PowerPoint, Keynote,
Google Slides, Impress and PDF viewers (not yet tried with a real light), and the laser stays the
pointer.

| | |
|---|---|
| **Light** | Luminus SST-20 white LED, from 2 mA moonlight to a 2.2 A turbo burst (default turbo 1.2 A, about 445 lm in the simulator) |
| **Laser** | 520 nm, Class 2 (≤ 1 mW), switched off in hardware by the SAFE / ARM slide switch |
| **Buttons** | three stainless-steel caps on the bottom face: › next, ● main inside an RGB light ring, ‹ previous |
| **Presenter mode** | Bluetooth LE keyboard (HID over GATT): Page Down / Page Up or the arrow keys, F5, Esc, B for a black screen; up to 4 paired computers, no dongle, no driver |
| **Power** | two LiPo pouch cells, about 800 mAh, USB-C charging, battery and temperature protection |
| **Electronics** | ESP32-C3 module on a 24 × 16.5 mm four-layer board, assembled by JLCPCB on both sides |
| **Firmware** | open Rust firmware with 149 host tests and a reproducible image; LuxLibre's board header as an alternative |
| **Web pages** | control app over Web Bluetooth and firmware installer over Web Serial, each a single HTML file |
| **Body** | CNC-machined 6061-T6, black anodised, "fighter-jet" panel seams with laser-marked rivets and stencils |
| **Cost** | about 620 USD for one light, 239 USD per light when five are made, with every fee, shipping and VAT ([workbook](hardware/flashka-keychain-v06/FlashKa_Parts_List_v0.6.xlsx)) |

| ![Bottom face with the three buttons and the lit ring (render)](hardware/flashka-keychain-v06/assets/v06/housing_closed_bottom.png) | ![Housing without the lid, with the real routed board, the cells and the hold-down pads (render)](hardware/flashka-keychain-v06/assets/v06/housing_open_top.png) | ![Exploded view, animated (render)](hardware/flashka-keychain-v06/assets/v06/flashka_v06_exploded.gif) |
|---|---|---|
| Bottom face: › ● ‹ and the lit ring | Inside: the real board, cells and pads | Exploded: every part in its place |
| ![Lid with the Class 2 laser label and the radio window (render)](hardware/flashka-keychain-v06/assets/v06/housing_closed_lid.png) | ![Laser side with the SAFE and ARM marks of the slide switch (render)](hardware/flashka-keychain-v06/assets/v06/housing_closed_rear.png) | ![Size next to v0.4 and a RovyVon Aurora A9 Pro (render)](hardware/flashka-keychain-v06/assets/v06/size_comparison_A9.png) |
| Lid: laser label, radio window | Laser side: SAFE / ARM | Size comparison |

Everything needed to make one is in [hardware/flashka-keychain-v06/](hardware/flashka-keychain-v06/README.md):
upload-ready files for three shops (circuit boards, aluminium and stainless parts, a resin print
kit), the parts and cost workbook, a 30-page
[build guide](hardware/flashka-keychain-v06/FlashKa_v0.6_Build_Guide.pdf) for people without
electronics experience, and the 47-page
[hardware package](hardware/flashka-keychain-v06/FlashKa_v0.6_Hardware_Package.pdf) that explains
every design decision and check. Every design file is generated by scripts in the repository
(KiCad schematic and board, CadQuery housing, drawings, laser marking, renders, cost workbook), so
a change to the design is a change to code that can be reviewed and rebuilt.

## The FlashKa web app

![Three phone screens: the control app with the light on, its presenter card in the dark theme, and the firmware installer](hardware/flashka-keychain-v06/assets/v06/webapp_showcase.png)

| Page | What it does | Needs |
|---|---|---|
| **[Control app](https://dompka.github.io/LuxLibre/flashka/flashka-app.html)** | battery, temperature and runtime; light on and off, levels and exact current; profiles with an editor; presenter settings and paired computers; a demo mode with a simulated light | Chrome or Edge on Android, Windows, macOS or ChromeOS (on Linux, Chrome may need the Web Bluetooth flag); Bluefy on iPhone and iPad |
| **[Firmware installer](https://dompka.github.io/LuxLibre/flashka/flashka-flasher.html)** | writes the firmware through the light's USB-C port and checks what it wrote; the firmware image is inside the page | Chrome or Edge on a computer and a USB-C data cable |

Both pages run entirely in the browser: nothing is uploaded and there is no account. They are
published from [hardware/flashka-keychain-v06/app/](hardware/flashka-keychain-v06/app/) with
GitHub Pages ([site/](site/) holds the start page).

![The control app in demo mode on a desktop browser: switching the light, the fine-brightness slider, a profile, and starting presenter mode](hardware/flashka-keychain-v06/assets/v06/webapp_demo_desktop.gif)

*Recording of the control app in its demo mode; the light is simulated inside the page.*

## What is inside

| Folder | What it gives you |
|---|---|
| [firmware/](docs/firmware/README.md) | One firmware for many lights: C++17, ported to ATtiny1616, CH32V003 and ESP32-C3 (not yet run on hardware), with 150 levels, three button layouts, thermal regulation that never flickers, battery protection, lockout, laser support, 50 ArduPilot-style parameters and a text console, all tested in a PC simulator |
| [docs/](docs/README.md) | [Design rules](docs/design-rules.md) (69 rules with reasons and checks), [choosing parts](docs/choosing-parts.md) with a worked 1200 lm example, [flashlight types](docs/flashlight-types.md), [testing](docs/testing.md) |
| [hardware/](hardware/README.md) | Reference designs with complete sources: [FlashKa Keychain v0.6](hardware/flashka-keychain-v06/README.md) (current) and [v0.5](hardware/flashka-keychain-v05/README.md) (previous) |
| [tools/](tools/README.md) | `lux_calc.py`: standby budget, runtime, cell current, throw, heat, trace width, voltage divider, NTC |
| [templates/](templates/README.md) | Requirement sheet, design log, decision matrix, BOM, design-review checklist, test report |
| [site/](site/) | The start page of the project's GitHub Pages site |

## Quick start

**Try the FlashKa web app without a light:** open the
[control app](https://dompka.github.io/LuxLibre/flashka/flashka-app.html) and press *Try demo mode*.

**Try the LuxLibre firmware without hardware** (Linux, macOS, or Windows with WSL):

```sh
cd firmware
make test                                    # unit and behaviour tests
make sim
build/luxsim --set TURBO_S=0 "2C W600000"    # double click for turbo, then 10 minutes
make sim BOARD=flashka-keychain-v06          # the simulator with the FlashKa v0.6 board header
build/luxsim-flashka-keychain-v06 --set TURBO_S=0 "2C W600000"
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/thermal-regulation-dark.png">
  <img alt="Simulated turbo for a keychain light and an 18650 light: output steps down smoothly as the temperature reaches the 50 °C limit" src="docs/img/thermal-regulation-light.png">
</picture>

*The LuxLibre firmware in its simulator: turbo, then smooth thermal regulation at 50 °C for a
keychain light and an 18650 light ([how this was made](docs/firmware/simulator.md)).*

**Design a light:** start with the requirement sheet
([templates/requirements.md](templates/requirements.md)), then follow
[docs/choosing-parts.md](docs/choosing-parts.md) and check the result against
[docs/design-rules.md](docs/design-rules.md). [docs/README.md](docs/README.md) suggests a reading
order.

**Put LuxLibre on your board:** [docs/firmware/porting.md](docs/firmware/porting.md).

**Build a FlashKa:** read the
[build guide](hardware/flashka-keychain-v06/FlashKa_v0.6_Build_Guide.pdf) once from start to end,
then use the files in [order_files/](hardware/flashka-keychain-v06/order_files/README.txt).

## Status

LuxLibre 0.2.0 is new. What has been tested so far:

| Part | State |
|---|---|
| LuxLibre firmware core | tested in the simulator (47 unit and behaviour tests, run by CI) |
| ATtiny1616 and CH32V003 ports | build and link; not yet run on hardware |
| ESP32-C3 port | experimental, including the resistor-ladder buttons of FlashKa v0.6; checked against the ESP-IDF API and with stub headers, CI build configured; not yet compiled with ESP-IDF or run on hardware |
| Design rules, guides, tools | complete for version 0.2; numbers from standards and datasheets carry sources |
| FlashKa v0.6 | designed and checked by software: netlist, KiCad DRC with 0 errors, the routed board's 3D model inside the housing, cap travel, drawings against the CAD, cost; not yet built |
| FlashKa v0.6 firmware and web pages | 149 firmware host tests; 143 unit tests, and 67 control-app and 29 installer tests in a browser against simulated hardware; not yet run on a real light |

The first hardware results will be added as test reports. Measurements from your builds are the
most valuable contribution: the [build report](https://github.com/DomPka/LuxLibre/issues/new?template=build_report.yml)
issue form asks for exactly what is needed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Safety and security

Lithium cells, bright LEDs, hot surfaces and lasers can hurt people. Read [SAFETY.md](SAFETY.md)
before building or testing. Security problems (for example in Bluetooth pairing or the web pages)
are reported privately as described in [SECURITY.md](SECURITY.md).

## Licences

Like ArduPilot, LuxLibre may be used, changed, built and sold by anyone, companies included, as
long as the shared parts stay open:

- firmware and tools: [GPL-3.0-or-later](LICENSES/GPL-3.0-or-later.txt)
- hardware design files: [CERN-OHL-W-2.0](LICENSES/CERN-OHL-W-2.0.txt)
- documentation: [CC-BY-SA-4.0](LICENSES/CC-BY-SA-4.0.txt)
- the FlashKa Rust firmware, web pages and web tools: MIT or Apache-2.0

What that means in practice, including for products you sell: [LICENSING.md](LICENSING.md).
How to use the names LuxLibre and FlashKa: [TRADEMARKS.md](TRADEMARKS.md).

## Background

LuxLibre stands on the shoulders of the enthusiast flashlight community: the
[Anduril](https://github.com/ToyKeeper/anduril) firmware (GPL-3.0) showed how much a single
button can do, early open lights such as the
[HexBright](https://techcrunch.com/2011/07/06/kid-tested-grant-imahara-approved-hexbrite-open-source-flashlight)
showed that people want to change their lights, and the community keeps asking for exact
levels, visible settings and configuration without a command line
([BLF discussion, 2026](https://budgetlightforum.com/t/hey-folks-i-want-to-drag-flash-lights-into-2026/234210)).
LuxLibre adds what a design team needs around the firmware: rules, a part-selection method,
tests, a simulator and complete reference designs. Its parameter system and its licensing follow
ArduPilot.

The name: Latin *lux*, light, and *libre*, free as in freedom.
