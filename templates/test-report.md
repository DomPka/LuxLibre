<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Test report

## How to use

Fill in one report per tested hardware revision and firmware build
([FW-8](../docs/design-rules.md#fw-8)). The procedures are in
[docs/testing.md](../docs/testing.md); each section below names the rules it verifies and
the testing.md section to follow. Write measured values with units, keep the raw data files
(CSV logs, photos, scope screenshots) next to this report and name them in the "Data file"
cells. Mark sections that do not apply "n.a." with a reason. End with the summary table: a
release is tested when every requirement ID from [requirements.md](requirements.md) has a
result.

## Header

| Field | Entry |
|---|---|
| Product | `<...>` |
| Hardware revision (silkscreen) | `<...>` |
| Firmware version (console `ver`) | `<...>` |
| Board header name | `<firmware/boards/.../board.h>` |
| Cell used (make, model, capacity) | `<...>` |
| Tester | `<...>` |
| Date(s) | `<YYYY-MM-DD>` |
| Ambient temperature | `<...> °C` |
| Raw data folder | `<path>` |

### Equipment

| Item | Model | Serial / ID | Calibration date or reference |
|---|---|---|---|
| Multimeter (µA range) |  |  |  |
| Bench supply with current limit |  |  |  |
| USB power meter |  |  |  |
| Thermocouple meter |  |  |  |
| Lux meter |  |  |  |
| Lumen tube or sphere (calibration light) |  |  |  |
| Photodiode + oscilloscope |  |  |  |
| Laser power meter (if laser fitted) |  |  |  |

## 1. Electrical bring-up

Verifies [DRV-7](../docs/design-rules.md#drv-7), [DRV-9](../docs/design-rules.md#drv-9),
[BAT-9](../docs/design-rules.md#bat-9), [BAT-6](../docs/design-rules.md#bat-6),
[DRV-2](../docs/design-rules.md#drv-2), [DRV-3](../docs/design-rules.md#drv-3).
Procedure: [docs/testing.md](../docs/testing.md), "Bring-up of a new board".

| Check | Result | OK? |
|---|---|---|
| All LED and laser outputs off during reset and without firmware |  |  |
| `ver` output |  |  |
| Battery voltage: multimeter / `status` cell_mV / BAT_CAL set | `<...> mV / <...> mV / <...> mV` |  |

**Standby current** (limit from BAT-6: `<...> µA`)

| State | Current (µA) | OK? |
|---|---|---|
| Off |  |  |
| Lockout |  |  |
| After LVP cut-off |  |  |

**LED current per level** (set with `level N`)

| Level | LED current (mA, meter) | `status` cell_mA | Cell current (mA, meter) | Notes |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 30 |  |  |  |  |
| 70 |  |  |  |  |
| 100 |  |  |  |  |
| 120 |  |  |  |  |
| 150 |  |  |  |  |

## 2. Output

Verifies [REQ-2](../docs/design-rules.md#req-2). Procedure:
[docs/testing.md](../docs/testing.md), "Output and runtime".

Method: `<lumen tube calibrated against ... / integrating sphere>`, cell charged to
`<...> V` at start.

| Mode | 0 s (lm) | 30 s (lm) | 2 min (lm) | 10 min (lm) | Requirement ID | Data file |
|---|---|---|---|---|---|---|
| Moon |  |  |  |  |  |  |
| Low |  |  |  |  |  |  |
| Medium |  |  |  |  |  |  |
| High |  |  |  |  |  |  |
| Turbo |  |  |  |  |  |  |

## 3. Runtime to 10 %

Verifies [REQ-2](../docs/design-rules.md#req-2). Procedure:
[docs/testing.md](../docs/testing.md), "Output and runtime". Runtime = time from the 30 s
value until output falls to 10 % of it.

| Mode | 30 s value (lm) | Runtime to 10 % (h:min) | End reason (10 % / LVP) | Requirement ID | Data file |
|---|---|---|---|---|---|
| Low |  |  |  |  |  |
| Medium |  |  |  |  |  |
| High |  |  |  |  |  |
| Turbo |  |  |  |  |  |

## 4. Intensity and beam distance

Verifies [REQ-2](../docs/design-rules.md#req-2), [LED-1](../docs/design-rules.md#led-1).
Procedure: [docs/testing.md](../docs/testing.md), "Intensity and beam distance".
cd = lux x d²; beam distance = 2 x sqrt(cd); see `tools/lux_calc.py`.

| Mode | Distance d (m) | Illuminance (lx) | Intensity (cd) | Beam distance (m) | Requirement ID |
|---|---|---|---|---|---|
| High |  |  |  |  |  |
| Turbo |  |  |  |  |  |

## 5. Thermal

Verifies [THM-1](../docs/design-rules.md#thm-1), [THM-4](../docs/design-rules.md#thm-4),
[THM-5](../docs/design-rules.md#thm-5), [THM-6](../docs/design-rules.md#thm-6).
Procedure: [docs/testing.md](../docs/testing.md), "Thermal and touch temperature".

Setup: `<held / hanging>`, still air, thermocouple on `<hottest touchable point>`.

**Surface temperature over time (°C)**

| Mode | 0 min | 1 min | 2 min | 5 min | 10 min | Max | THM-1 OK? |
|---|---|---|---|---|---|---|---|
| Medium |  |  |  |  |  |  |  |
| High |  |  |  |  |  |  |  |
| Turbo |  |  |  |  |  |  |  |

Turbo: time to first step-down `<...> s`, regulated level after 10 min `<...>`.

**Sensor vs surface (THM_OFFSET calibration)**

| Condition | Reference (°C) | Sensor `status` temp_dC / 10 (°C) | Difference (°C) |
|---|---|---|---|
| Rested 1 h at room temperature |  |  |  |
| Regulated at THM_LIMIT, end of 10 min |  |  |  |

Values set: THM_OFFSET `<...>`, THM_LIMIT `<...>`, THM_SHUTDN `<...>`.

## 6. Battery and charging

Verifies [BAT-4](../docs/design-rules.md#bat-4), [BAT-5](../docs/design-rules.md#bat-5),
[CHG-1](../docs/design-rules.md#chg-1), [CHG-2](../docs/design-rules.md#chg-2),
[CHG-3](../docs/design-rules.md#chg-3), [CHG-6](../docs/design-rules.md#chg-6).
Procedure: [docs/testing.md](../docs/testing.md), "Battery and charging".

**Low-voltage protection** (bench supply ramped down slowly)

| Event | Parameter | Set (mV) | Measured at the cell (mV) | OK? |
|---|---|---|---|---|
| Warning / step-down | LVP_WARN |  |  |  |
| Cut-off | LVP_CUT |  |  |  |
| Allowed on again | LVP_RESUME |  |  |  |

**Charging**

| Check | Result | OK? |
|---|---|---|
| Charges with a C-to-C cable / with an A-to-C cable |  |  |
| Charge current, CC phase (A) |  |  |
| Voltage at the cell at termination (4.20 V +-1 %) |  |  |
| Termination current (mA) |  |  |
| Charge time, empty to full (h:min) |  |  |
| Charge pauses below CHG_TMIN / above CHG_TMAX |  |  |
| Charge indicator and level limit on USB (CHG_MAXLVL) |  |  |
| Reversed cell: no damage, no output (removable cells) |  |  |

## 7. Flicker

Verifies [LED-6](../docs/design-rules.md#led-6), [FW-4](../docs/design-rules.md#fw-4).
Procedure: [docs/testing.md](../docs/testing.md), "Flicker".
Mod % = 100 x (Lmax - Lmin) / (Lmax + Lmin).

Method: `<phone camera / photodiode + oscilloscope>`

| Level | Frequency (Hz) | Lmax | Lmin | Modulation (%) | OK? |
|---|---|---|---|---|---|
| Low (level `<...>`) |  |  |  |  |  |
| Medium (level `<...>`) |  |  |  |  |  |
| High (level `<...>`) |  |  |  |  |  |
| During thermal regulation |  |  |  |  |  |

## 8. Drop test

Verifies [MEC-3](../docs/design-rules.md#mec-3), [REQ-2](../docs/design-rules.md#req-2).
Procedure: [docs/testing.md](../docs/testing.md), "Durability". Height `<...> m` onto
concrete.

| Drop | Orientation | Damage seen | Works after? |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |

## 9. Water test

Verifies [MEC-2](../docs/design-rules.md#mec-2), [REQ-2](../docs/design-rules.md#req-2).
Procedure: [docs/testing.md](../docs/testing.md), "Durability".

| Check | Result | OK? |
|---|---|---|
| Rating tested (IPX4 / IPX7 / IPX8) |  |  |
| Depth and duration |  |  |
| Done after the drop test? |  |  |
| Water inside after opening? |  |  |
| Works after the test? |  |  |

## 10. Laser (if fitted)

Verifies [LAS-1](../docs/design-rules.md#las-1), [LAS-2](../docs/design-rules.md#las-2),
[LAS-3](../docs/design-rules.md#las-3). Procedure: [docs/testing.md](../docs/testing.md),
"Optical safety".

| Check | Result | OK? |
|---|---|---|
| Measured output power (mW), meter and wavelength setting |  |  |
| Laser class and label |  |  |
| Hardware interlock open: no emission, whatever the firmware does |  |  |
| Emission indicator works |  |  |
| Stops after LASER_S; refused above LASER_TMAX and below LASER_VMIN |  |  |

## 11. Firmware gestures

Verifies [FW-3](../docs/design-rules.md#fw-3), [FW-5](../docs/design-rules.md#fw-5),
[FW-6](../docs/design-rules.md#fw-6), [BAT-7](../docs/design-rules.md#bat-7),
[FW-8](../docs/design-rules.md#fw-8). Procedure: [docs/testing.md](../docs/testing.md),
"Firmware tests"; button map in
[docs/firmware/user-interface.md](../docs/firmware/user-interface.md).

| Gesture | Expected | OK? |
|---|---|---|
| `make test` for this firmware build | all tests pass |  |
| 1C from off / from on | on at remembered level / off |  |
| Hold from off | moon, then ramps up |  |
| 2C | turbo; steps down after TURBO_S |  |
| 3C | battery voltage as blinks |  |
| 4C from off / in lockout | lockout on (3 blinks) / lockout off |  |
| Lockout after battery removal and reboot | still locked |  |
| Button held in lockout | dark (or moon if LOCK_MOON = 1); ignored after 10 s |  |
| 9C from off | factory reset (5 blinks), defaults restored |  |
| Laser gesture (1C, then hold) | laser while held; refused in lockout |  |

## 12. Summary

| Requirement ID | Requirement | Target | Result | Pass / fail | Section |
|---|---|---|---|---|---|
| R1 |  |  |  |  |  |
| R2 |  |  |  |  |  |
| R3 |  |  |  |  |  |

Open issues: `<...>`

Tester signature and date: `<...>`
