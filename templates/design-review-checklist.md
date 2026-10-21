<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Design review checklist

## How to use

Review the design against every LuxLibre design rule before you order boards, before you
order housings, and before a release. The full rule text is in
[docs/design-rules.md](../docs/design-rules.md). For each rule write a status: **ok** (met,
with evidence), **n.a.** (does not apply, say why in the evidence column, e.g. "no laser") or
**open** (not met or not checked yet). Evidence is a short pointer: design log record
(D-03), requirement (R22), test report section, schematic sheet, photo or file name. Every
"open" line goes into the action list at the end. Reviewers should include at least one
person who did not design the light.

## Review

| Field | Entry |
|---|---|
| Project | `<...>` |
| Hardware revision | `<...>` |
| Firmware version (`ver`) and board header | `<...>` |
| Review stage | `<schematic / layout / prototype / release>` |
| Reviewer(s) | `<...>` |
| Date | `<YYYY-MM-DD>` |
| Documents reviewed | `<requirements rev, design log, schematic, layout, BOM, test report>` |

## Checklist

### REQ - requirements and documentation

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [REQ-1](../docs/design-rules.md#req-1) | Requirement sheet exists, targets measurable, M/S/C set |  |  |
| [REQ-2](../docs/design-rules.md#req-2) | Output at 30 s, runtime to 10 %, cd, beam distance, impact, water and 10-min sustained output stated |  |  |
| [REQ-3](../docs/design-rules.md#req-3) | Design log has a record for every important choice, with sources |  |  |
| [REQ-4](../docs/design-rules.md#req-4) | Hardware revision on silkscreen; firmware version readable (`ver`) |  |  |
| [REQ-5](../docs/design-rules.md#req-5) | Editable sources published with licence files |  |  |

### BAT - battery and power path

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [BAT-1](../docs/design-rules.md#bat-1) | Cell datasheet from a known maker; continuous cell current <= 70 % of rated max; BAT_MAX_MA set |  |  |
| [BAT-2](../docs/design-rules.md#bat-2) | Standard user-replaceable cell, or reason recorded (EU 2023/1542 Art. 11) |  |  |
| [BAT-3](../docs/design-rules.md#bat-3) | Built-in cell has a hardware protection circuit independent of firmware |  |  |
| [BAT-4](../docs/design-rules.md#bat-4) | Reversed cell causes no damage and no output |  |  |
| [BAT-5](../docs/design-rules.md#bat-5) | LVP_WARN / LVP_CUT / LVP_RESUME match the cell chemistry |  |  |
| [BAT-6](../docs/design-rules.md#bat-6) | Standby drain <= 3 % of capacity per month |  |  |
| [BAT-7](../docs/design-rules.md#bat-7) | Lockout available; a stuck button does not leave the light on |  |  |
| [BAT-8](../docs/design-rules.md#bat-8) | Contacts and springs rated for turbo current; spring bypass above ~3 A |  |  |
| [BAT-9](../docs/design-rules.md#bat-9) | Battery voltage reading within 1 % after BAT_CAL |  |  |

### CHG - charging and USB

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [CHG-1](../docs/design-rules.md#chg-1) | Two separate 5.1 kOhm Rd resistors, one per CC pin |  |  |
| [CHG-2](../docs/design-rules.md#chg-2) | CC/CV to 4.20 V +-1 %; charge current <= cell standard charge current |  |  |
| [CHG-3](../docs/design-rules.md#chg-3) | Charging only inside the cell's charge temperature window (CHG_TMIN / CHG_TMAX) |  |  |
| [CHG-4](../docs/design-rules.md#chg-4) | VBUS has TVS; products have input over-voltage protection |  |  |
| [CHG-5](../docs/design-rules.md#chg-5) | ESD protection at USB-C pins, button and metal body |  |  |
| [CHG-6](../docs/design-rules.md#chg-6) | Charge state shown; main LED limited on USB (CHG_MAXLVL) |  |  |

### LED - emitters and optics

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [LED-1](../docs/design-rules.md#led-1) | Emitter fits the beam goal (throw or flood) |  |  |
| [LED-2](../docs/design-rules.md#led-2) | LED current <= 80 % of datasheet max; flux taken at Tj 85 °C |  |  |
| [LED-3](../docs/design-rules.md#led-3) | LED on a DTP copper MCPCB with a short thermal path to the housing |  |  |
| [LED-4](../docs/design-rules.md#led-4) | CCT, CRI and R9 specified and bin ordered |  |  |
| [LED-5](../docs/design-rules.md#led-5) | Photobiological safety assessed (IEC 62471, 200 mm); labels where needed |  |  |
| [LED-6](../docs/design-rules.md#led-6) | Constant current or PWM >= 3 kHz in every mode |  |  |
| [LED-7](../docs/design-rules.md#led-7) | Lowest mode stable and repeatable (LX_OUT_MIN_Q16 set) |  |  |
| [LED-8](../docs/design-rules.md#led-8) | Lens, centering gasket, no force on the dome |  |  |

### DRV - driver and electronics

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [DRV-1](../docs/design-rules.md#drv-1) | Topology matches cell voltage vs LED forward voltage |  |  |
| [DRV-2](../docs/design-rules.md#drv-2) | Closed-loop current control with sense resistor; accuracy at low and high levels stated |  |  |
| [DRV-3](../docs/design-rules.md#drv-3) | Efficiency in most-used modes and quiescent current checked against BAT-6 |  |  |
| [DRV-4](../docs/design-rules.md#drv-4) | MLCCs rated >= 2x working voltage; effective capacitance after DC bias checked |  |  |
| [DRV-5](../docs/design-rules.md#drv-5) | Copper widths sized for current (IPC-2221) |  |  |
| [DRV-6](../docs/design-rules.md#drv-6) | Tight power loop, Kelvin sense, quiet feedback and ADC traces |  |  |
| [DRV-7](../docs/design-rules.md#drv-7) | Every light and laser output has a pull-down; MCU reset = off |  |  |
| [DRV-8](../docs/design-rules.md#drv-8) | Watchdog and brown-out detection enabled |  |  |
| [DRV-9](../docs/design-rules.md#drv-9) | Programming pads and test points for battery and LED current |  |  |

### THM - thermal

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [THM-1](../docs/design-rules.md#thm-1) | Hottest touchable surface <= 48 °C continuous, never above 51 °C |  |  |
| [THM-2](../docs/design-rules.md#thm-2) | Sustainable heat estimated with P = h x A x dT |  |  |
| [THM-3](../docs/design-rules.md#thm-3) | Turbo duration estimated from thermal mass and stated honestly |  |  |
| [THM-4](../docs/design-rules.md#thm-4) | Sensor close to the heat source; THM_OFFSET and sensor-to-surface difference calibrated |  |  |
| [THM-5](../docs/design-rules.md#thm-5) | Active regulation on; THM_FLOOR useful; THM_SHUTDN as last resort |  |  |
| [THM-6](../docs/design-rules.md#thm-6) | 10-min test per mode and turbo test done at 25 °C still air |  |  |

### MEC - mechanical

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [MEC-1](../docs/design-rules.md#mec-1) | Housing material matches the sustained power |  |  |
| [MEC-2](../docs/design-rules.md#mec-2) | O-ring glands, sealed switch boot, sealed USB; IP rating verified |  |  |
| [MEC-3](../docs/design-rules.md#mec-3) | Survives 6 drops from 1 m onto concrete; no MLCCs at board edges or flex points |  |  |
| [MEC-4](../docs/design-rules.md#mec-4) | Thread engagement adequate; mechanical lockout possible; O-rings lubricated |  |  |
| [MEC-5](../docs/design-rules.md#mec-5) | Current-carrying contact surfaces bare (masked from anodising) |  |  |
| [MEC-6](../docs/design-rules.md#mec-6) | Button shrouded or recessed, clear feedback, life rating adequate |  |  |
| [MEC-7](../docs/design-rules.md#mec-7) | Clip, lanyard and keyring points strength-checked; no sharp edges |  |  |
| [MEC-8](../docs/design-rules.md#mec-8) | Shop DFM rules followed; 2D drawings with tolerances for critical fits |  |  |

### FW - firmware

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [FW-1](../docs/design-rules.md#fw-1) | Power-up dark and safe; drivers held off during reset |  |  |
| [FW-2](../docs/design-rules.md#fw-2) | Own board header with measured limits; no example defaults |  |  |
| [FW-3](../docs/design-rules.md#fw-3) | Common LuxLibre button grammar kept |  |  |
| [FW-4](../docs/design-rules.md#fw-4) | No firmware flicker; thermal_regulation_does_not_flicker test passes |  |  |
| [FW-5](../docs/design-rules.md#fw-5) | Parameter ranges bound thermal, LVP and laser settings; factory reset restores safe defaults |  |  |
| [FW-6](../docs/design-rules.md#fw-6) | Lockout survives reboot and battery change; stuck button in lockout stays dark |  |  |
| [FW-7](../docs/design-rules.md#fw-7) | Settings stored with CRC and layout check; corrupt settings load defaults |  |  |
| [FW-8](../docs/design-rules.md#fw-8) | `make test` passes in CI; hardware test report for this board release |  |  |

### LAS - lasers

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [LAS-1](../docs/design-rules.md#las-1) | Class 1 or 2 visible laser only (<= 1 mW CW); Class 1 if it appeals to children |  |  |
| [LAS-2](../docs/design-rules.md#las-2) | Hardware interlock in series with firmware; deliberate activation; emission indicator |  |  |
| [LAS-3](../docs/design-rules.md#las-3) | Real laser power measured; class label per IEC 60825-1 |  |  |

### DFM - manufacturing and cost

| Rule | Check | Status (ok / n.a. / open) | Evidence |
|---|---|---|---|
| [DFM-1](../docs/design-rules.md#dfm-1) | SMD parts on one side where possible |  |  |
| [DFM-2](../docs/design-rules.md#dfm-2) | Unique part numbers minimised; assembler basic parts used |  |  |
| [DFM-3](../docs/design-rules.md#dfm-3) | Packages fit the build method |  |  |
| [DFM-4](../docs/design-rules.md#dfm-4) | Small boards panelised; fiducials and tooling as the assembler requires |  |  |
| [DFM-5](../docs/design-rules.md#dfm-5) | Landed cost planned (shipping, VAT, duty, fees); orders consolidated |  |  |
| [DFM-6](../docs/design-rules.md#dfm-6) | Second sources listed where pin-compatible parts exist |  |  |
| [DFM-7](../docs/design-rules.md#dfm-7) | Fabrication outputs generated by script; rotations and polarity checked in the viewer |  |  |

## Summary

| Status | Count |
|---|---|
| ok |  |
| n.a. |  |
| open |  |

## Actions

| # | Rule | Action | Owner | Due | Done |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |

## Sign-off

Result: `<approved / approved with actions / not approved>`

| Role | Name | Date | Signature |
|---|---|---|---|
| Designer |  |  |  |
| Reviewer |  |  |  |
| Reviewer |  |  |  |
