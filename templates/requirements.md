<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Requirement sheet

## How to use

Fill this sheet in before you choose any part ([REQ-1](../docs/design-rules.md#req-1)).
Write a target value that can be measured or checked (a number with a unit, or a yes/no
fact), not a wish like "bright". Mark each row Must (M), Should (S) or Could (C): a Must that
fails stops the release, a Should needs a written reason, a Could is nice to have. Say how
each row will be verified: T = test, I = inspection, A = analysis or calculation,
D = demonstration. Delete rows that do not apply, add rows as needed, and keep the IDs
stable (do not renumber; mark removed rows "deleted"). The test report
([test-report.md](test-report.md)) gives a result for every ID.

## Project

| Field | Value |
|---|---|
| Product name | `<...>` |
| Flashlight type (see [docs/flashlight-types.md](../docs/flashlight-types.md)) | `<EDC / keychain / headlamp / thrower / ...>` |
| Sheet revision and date | `<rev>`, `<YYYY-MM-DD>` |
| Author(s) | `<...>` |
| Status | `<draft / agreed / frozen for release>` |

## Requirements

### Use case and user

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R1 | Main use case (what, where, how long per use) | `<...>` | M | I | [REQ-1](../docs/design-rules.md#req-1) |
| R2 | Typical user (experience, gloves, age group) | `<...>` | M | I | [REQ-1](../docs/design-rules.md#req-1), [LAS-1](../docs/design-rules.md#las-1) (children) |

### Size and weight

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R3 | Length, max | `<...> mm` |  | I |  |
| R4 | Diameter or width, max | `<...> mm` |  | I |  |
| R5 | Mass with cell, max | `<...> g` |  | T |  |
| R6 | Carry option (clip, lanyard, keyring, magnet) | `<...>` |  | T | [MEC-7](../docs/design-rules.md#mec-7) |

### Output

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R7 | Peak output (at switch-on) | `<...> lm` |  | T | [REQ-2](../docs/design-rules.md#req-2) |
| R8 | Output at 30 s (ANSI/PLATO FL 1 rating) | `<...> lm` |  | T | [REQ-2](../docs/design-rules.md#req-2) |
| R9 | Sustained output after 10 min | `<...> lm` |  | T | [REQ-2](../docs/design-rules.md#req-2), [THM-2](../docs/design-rules.md#thm-2) |
| R10 | Peak intensity | `<...> cd` |  | T | [REQ-2](../docs/design-rules.md#req-2), [LED-1](../docs/design-rules.md#led-1) |
| R11 | Beam distance (2 x sqrt(cd)) | `<...> m` |  | T, A | [REQ-2](../docs/design-rules.md#req-2) |
| R12 | Beam type (throw / flood / mixed) | `<...>` |  | I | [LED-1](../docs/design-rules.md#led-1) |

### Runtime per mode

Runtime = time from the 30 s output value until output falls to 10 % of it
([REQ-2](../docs/design-rules.md#req-2)).

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R13 | Moon: output and runtime | `<...> lm`, `<...> h` |  | T | [REQ-2](../docs/design-rules.md#req-2), [LED-7](../docs/design-rules.md#led-7) |
| R14 | Low: output and runtime | `<...> lm`, `<...> h` |  | T | [REQ-2](../docs/design-rules.md#req-2) |
| R15 | Medium: output and runtime | `<...> lm`, `<...> h` |  | T | [REQ-2](../docs/design-rules.md#req-2) |
| R16 | High: output and runtime | `<...> lm`, `<...> h` |  | T | [REQ-2](../docs/design-rules.md#req-2) |
| R17 | Turbo: duration before step-down | `<...> s` |  | T, A | [THM-3](../docs/design-rules.md#thm-3) |

### Battery

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R18 | Cell type and size | `<chemistry, size, e.g. Li-ion 18650>` |  | I | [BAT-1](../docs/design-rules.md#bat-1) |
| R19 | Cell user-replaceable | `<yes / no + reason>` |  | D | [BAT-2](../docs/design-rules.md#bat-2) |
| R20 | Max continuous cell current (<= 70 % of rated max) | `<...> A` |  | A, T | [BAT-1](../docs/design-rules.md#bat-1) |
| R21 | Reversed cell: no damage, no output | `<yes / n.a.>` |  | T | [BAT-4](../docs/design-rules.md#bat-4) |
| R22 | Standby drain, max | `<...> µA` |  | T | [BAT-6](../docs/design-rules.md#bat-6) |

### Charging

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R23 | Charge port (USB-C, works with C-to-C cable) | `<yes / no charging>` |  | T | [CHG-1](../docs/design-rules.md#chg-1) |
| R24 | Charge current (CC phase) | `<...> A` |  | T | [CHG-2](../docs/design-rules.md#chg-2) |
| R25 | Charge time, empty to full | `<...> h` |  | T | [CHG-2](../docs/design-rules.md#chg-2) |
| R26 | Charge indicator | `<...>` |  | D | [CHG-6](../docs/design-rules.md#chg-6) |

### User interface

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R27 | Buttons (number, position, side or tail) | `<...>` |  | I | [MEC-6](../docs/design-rules.md#mec-6) |
| R28 | Button layout (ramp / modes / simple) | `<...>` |  | D | [FW-3](../docs/design-rules.md#fw-3) |
| R29 | Lockout (electronic, mechanical) | `<...>` |  | D | [BAT-7](../docs/design-rules.md#bat-7), [FW-6](../docs/design-rules.md#fw-6) |
| R30 | Battery level display | `<...>` |  | D | [FW-3](../docs/design-rules.md#fw-3) |

### Environment

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R31 | Operating temperature range | `<...> °C to <...> °C` |  | T, A |  |
| R32 | Water protection (IP code) | `<IPX4 / IPX7 / IPX8>` |  | T | [MEC-2](../docs/design-rules.md#mec-2) |
| R33 | Drop height onto concrete | `<...> m` |  | T | [MEC-3](../docs/design-rules.md#mec-3) |

### Touch temperature

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R34 | Hottest touchable surface in continuous use, max | `<...> °C` (LuxLibre rule: <= 48 °C) | M | T | [THM-1](../docs/design-rules.md#thm-1), [THM-6](../docs/design-rules.md#thm-6) |
| R35 | Hottest touchable surface, never above | `<...> °C` (LuxLibre rule: 51 °C, metal) | M | T | [THM-1](../docs/design-rules.md#thm-1) |

### Colour

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R36 | Colour temperature (CCT) | `<...> K` (LuxLibre default for EDC: 4000-5000 K) |  | I | [LED-4](../docs/design-rules.md#led-4) |
| R37 | Colour rendering index (CRI), min | `<...>` (LuxLibre default for EDC: >= 90) |  | I | [LED-4](../docs/design-rules.md#led-4) |
| R38 | R9 (saturated red rendering), min | `<...>` |  | I | [LED-4](../docs/design-rules.md#led-4) |

### Safety features

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R39 | Laser fitted, and its class | `<none / Class 1 / Class 2>` |  | T | [LAS-1](../docs/design-rules.md#las-1), [LAS-3](../docs/design-rules.md#las-3) |
| R40 | Low-voltage protection (warn, cut-off) | `<...> mV`, `<...> mV` |  | T | [BAT-5](../docs/design-rules.md#bat-5) |
| R41 | Thermal regulation and shutdown | `<limit °C>`, `<shutdown °C>` |  | T | [THM-5](../docs/design-rules.md#thm-5) |
| R42 | Photobiological risk group (LED) | `<...>` |  | A | [LED-5](../docs/design-rules.md#led-5) |
| R43 | No visible flicker in any mode | `<yes>` |  | T | [LED-6](../docs/design-rules.md#led-6) |

### Regulations and markets

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R44 | Markets where it will be sold or given away | `<EU / UK / US / none, personal use>` |  | I |  |
| R45 | EU Battery Regulation 2023/1542 (removable, replaceable cell) | `<applies / n.a.>` |  | I | [BAT-2](../docs/design-rules.md#bat-2) |
| R46 | CE / UKCA / FCC marking | `<check for your market>` |  | I |  |
| R47 | Laser and LED safety labels | `<...>` |  | I | [LAS-3](../docs/design-rules.md#las-3), [LED-5](../docs/design-rules.md#led-5) |

### Budget and schedule

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R48 | Cost per unit (landed: parts, boards, shipping, VAT, duty) | `<...> <currency>` |  | A | [DFM-5](../docs/design-rules.md#dfm-5) |
| R49 | Quantity per batch | `<...> pcs` |  | I | [DFM-5](../docs/design-rules.md#dfm-5) |
| R50 | Prototype ready | `<YYYY-MM-DD>` |  | I |  |
| R51 | Release (tested, documented) | `<YYYY-MM-DD>` |  | I | [FW-8](../docs/design-rules.md#fw-8) |

## Example: 18650 EDC light, > 1000 lm

An imaginary product. The values are its own targets, not LuxLibre recommendations, except
where a LuxLibre rule is named.

| ID | Requirement | Target value | M/S/C | Verification | Rule |
|---|---|---|---|---|---|
| R7 | Peak output (at switch-on) | > 1000 lm | M | T: lumen tube, 0 s | [REQ-2](../docs/design-rules.md#req-2) |
| R11 | Beam distance | >= 150 m (= 5625 cd) | S | T: lux at 5 m, `lux_calc.py` | [REQ-2](../docs/design-rules.md#req-2) |
| R19 | Cell user-replaceable | yes, standard 18650 | M | D: change cell without tools | [BAT-2](../docs/design-rules.md#bat-2) |
| R22 | Standby drain, max | <= 123 µA (3 % per month of 3000 mAh) | M | T: µA meter, light off | [BAT-6](../docs/design-rules.md#bat-6) |
| R24 | Charge current (CC phase) | <= standard charge current of the chosen cell | M | T: USB power meter | [CHG-2](../docs/design-rules.md#chg-2) |
| R32 | Water protection | IPX7 (1 m, 30 min) | S | T: after drop test | [MEC-2](../docs/design-rules.md#mec-2) |
| R34 | Hottest touchable surface, continuous | <= 48 °C | M | T: 10 min per mode, 25 °C still air | [THM-1](../docs/design-rules.md#thm-1) |
| R37 | CRI, min | >= 90 | S | I: LED bin on datasheet | [LED-4](../docs/design-rules.md#led-4) |
