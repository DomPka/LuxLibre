<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../README.md) › Documentation

# Documentation

## Reading paths

**I want to design a flashlight**

1. [../templates/requirements.md](../templates/requirements.md): write down what the light must do,
   in numbers.
2. [flashlight-types.md](flashlight-types.md): what is typical for your kind of light and which
   rules dominate.
3. [choosing-parts.md](choosing-parts.md): the six-step method, the part families, and a worked
   1200 lm 18650 example.
4. [design-rules.md](design-rules.md): check every decision against the rules; use
   [../templates/design-review-checklist.md](../templates/design-review-checklist.md) before
   ordering.
5. [testing.md](testing.md): prove it, and publish measured numbers.

**I want LuxLibre firmware on my board**

1. [firmware/README.md](firmware/README.md): what the firmware does and how it is built.
2. [firmware/porting.md](firmware/porting.md): a board header for a supported MCU, or a new port.
3. [firmware/simulator.md](firmware/simulator.md): test the header before the hardware exists.
4. [firmware/parameters.md](firmware/parameters.md) and
   [firmware/user-interface.md](firmware/user-interface.md): generated references.

**I want to build a FlashKa**

[../hardware/flashka-keychain-v07/README.md](../hardware/flashka-keychain-v07/README.md) for v0.7,
the current design (1000 lm with a TIR optic, keys on the centre line, a key board, a presenter
mode),
[../hardware/flashka-keychain-v06/README.md](../hardware/flashka-keychain-v06/README.md) for v0.6,
the previous design, or
[../hardware/flashka-keychain-v05/README.md](../hardware/flashka-keychain-v05/README.md) for v0.5,
each with the build guide PDF in its folder.

**I want to choose a light**

[comparison.md](comparison.md): every LuxLibre design next to popular lights of the same cell size, with the
reviewers' measurements and the simulated figures side by side.

**I want to follow EDCO**

EDCO is the family of round, sealed everyday-carry lights without laser or radio. All are concepts: the housing and
the firmware board header exist, the boards are not drawn yet.

* [EDCO Prism](../hardware/edco-prism/README.md): 18350, 83 mm, a white or any-colour beam.
* [EDCO Mini](../hardware/edco-mini/README.md): 16340 keychain light of about 70 mm, red and UV side lights.
* [EDCO v0.2](../hardware/edco-v02/README.md): about 1,760 lm in two sizes (18500 and 14500).
* [EDCO v0.1](../hardware/edco-v01/README.md): the first one, 14500 in a Ø20 tube.

## All documents

| Document | Contents |
|---|---|
| [comparison.md](comparison.md) | the LuxLibre designs against 14 popular everyday-carry lights: light at 30 s and after 10 minutes, throw, runtime, size, price; simulated against measured, with sources |
| [design-rules.md](design-rules.md) | 69 rules (requirements, battery, charging, LED, driver, thermal, mechanical, firmware, lasers, manufacturing) with reasons, sources and checks |
| [choosing-parts.md](choosing-parts.md) | how to choose any part; cells, LEDs, optics, drivers, MCUs, chargers, protection, small parts, housing; worked example; cost; using search tools and AI assistants |
| [flashlight-types.md](flashlight-types.md) | twelve kinds of lights with parts direction, dominant rules and firmware settings |
| [testing.md](testing.md) | bring-up, firmware, output and runtime, intensity, thermal, battery and charging, flicker, durability, optical safety, report |
| [firmware/README.md](firmware/README.md) | features, why C++17, architecture, building, flashing, console, parameters, tests |
| [firmware/porting.md](firmware/porting.md) | adding a board or an MCU, the HAL contract |
| [firmware/simulator.md](firmware/simulator.md) | luxsim, models, plots, writing tests |
| [firmware/parameters.md](firmware/parameters.md) | every parameter with default, range and meaning (generated) |
| [firmware/user-interface.md](firmware/user-interface.md) | every button gesture per layout, level table (generated) |
| [../tools/README.md](../tools/README.md) | the `lux_calc.py` calculator |
| [../templates/README.md](../templates/README.md) | the fill-in templates |

## Conventions

- Rule IDs such as [THM-1](design-rules.md#thm-1) link to the design rules.
- Numbers from standards and datasheets carry a source link; numbers marked *LuxLibre rule*,
  *default* or *suggestion* are project choices.
- Prices and stock were checked in October 2026.
- `docs/img/` holds figures in a light and a dark version; GitHub shows the one that matches the
  reader's theme.
