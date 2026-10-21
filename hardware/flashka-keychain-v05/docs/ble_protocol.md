# Aurora++ v0.5 — Bluetooth LE protocol (version 1)

This document is the contract between the firmware (`firmware/aurora-fw`) and the
phone/desktop app (`app/aurora-app.html`). Both sides implement exactly this.
All multi-byte numbers are **little-endian**. All packets fit in 20 bytes, so the
default ATT MTU (23) is enough.

## 1. Advertising

| Item | Value |
|---|---|
| Device name | `Aurora-XXXX` (XXXX = last two bytes of the BLE MAC, hex, upper case) — complete local name in the scan response |
| Advertised service | Aurora Control Service UUID (128-bit, below) in the advertising data |
| Interval | 100 ms for the first 30 s of a window, then 500 ms |
| Connectable | yes, one central at a time |
| Security | none (no pairing). Range and the short advertising windows are the protection; the laser can never be switched from Bluetooth. |

The radio is **only on in windows** (the light sleeps otherwise):

1. while the main LED is on;
2. for 120 s after the main LED is switched off;
3. for 120 s after a **triple click** while the light is off (the RGB LED blinks blue);
4. while USB power is present (charging or charged);
5. while a central is connected, plus 30 s after it disconnects;
6. `KEEPALIVE` (command 0x09) extends the current window, at most 255 s per command.

When no window is open, the light is off and no USB is present, the MCU goes to deep sleep
(about 10 µA plus the 17 µA of the NTC divider). A button press wakes it.

## 2. GATT services

### 2.1 Battery Service (standard, 0x180F)

| Characteristic | UUID | Properties | Format |
|---|---|---|---|
| Battery Level | 0x2A19 | read, notify | `u8` state of charge, 0–100 % |

### 2.2 Aurora Control Service

Service UUID: **`a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13`**

| Characteristic | UUID | Properties | Size |
|---|---|---|---|
| Status | `a7d40002-3c5e-4b8a-9f61-2d0c8e5b7a13` | read, notify | 18 bytes |
| Command | `a7d40003-3c5e-4b8a-9f61-2d0c8e5b7a13` | write (with response) | 1–3 bytes |
| Profile | `a7d40004-3c5e-4b8a-9f61-2d0c8e5b7a13` | read, write (with response) | 20 bytes |
| Info | `a7d40005-3c5e-4b8a-9f61-2d0c8e5b7a13` | read | UTF-8 text, ≤ 20 bytes |

Notifications of Status are sent on every change and at least every 2 s while a
central is subscribed (battery voltage and temperature change slowly; the 2 s tick keeps
the app's turbo countdown alive). Battery Level is notified when the percentage changes.

## 3. Status (18 bytes, read / notify)

| Offset | Type | Field |
|---|---|---|
| 0 | u8 | protocol version = **1** |
| 1 | u8 | flags: bit0 light on · bit1 turbo active · bit2 charging · bit3 charge complete · bit4 USB power present · bit5 lockout · bit6 thermal limit active · bit7 battery limit active (low voltage or cell current limit) |
| 2 | u8 | active profile: 0 Extreme · 1 Balanced · 2 Endurance · 3 Custom |
| 3 | u8 | level: 0 Moon · 1 Low · 2 Medium · 3 High · 4 Turbo · 0xFF = exact current set by the app |
| 4 | u16 | LED current now, mA (after every limit) |
| 6 | u16 | battery voltage, mV |
| 8 | u8 | battery state of charge, % |
| 9 | i16 | board temperature, 0.1 °C (NTC next to the LED wires) |
| 11 | u16 | turbo time left, s (0 when not in turbo) |
| 13 | u8 | last control source: 0 none · 1 button · 2 app · 3 automatic (protection, timer) |
| 14 | u8 | app lock time left, s (app commands that switch or dim the light are refused while > 0) |
| 15 | u16 | estimated runtime at the present output, minutes (0xFFFF = unknown / off) |
| 17 | u8 | laser on (0/1) — information only |

## 4. Command (write with response)

First byte = opcode.

| Opcode | Arguments | Action |
|---|---|---|
| 0x01 OFF | — | main LED off |
| 0x02 ON | — | main LED on at the remembered level |
| 0x03 LEVEL | u8 level 0–4 | set level (4 = turbo; turbo follows the profile's time limit) |
| 0x04 PROFILE | u8 profile 0–3 | select profile (the light stays in its state; the level is re-applied with the new table) |
| 0x05 OUTPUT_MA | u16 mA | exact current, clamped to the profile's turbo current; above the profile's step-down current the turbo timer runs |
| 0x06 LOCKOUT | u8 0/1 | 1 = lock (button and app cannot switch on; four clicks unlock); 0 = unlock |
| 0x07 IDENTIFY | — | RGB LED blinks cyan three times |
| 0x08 SAVE | — | store the Custom profile, the selected profile and the remembered level in flash |
| 0x09 KEEPALIVE | u8 seconds (1–255) | keep the Bluetooth window open at least this long from now; repeat to extend |
| 0x7F FACTORY_RESET | u8 0xA5 | built-in defaults, Custom = Balanced; reboots |

Errors (ATT application error codes returned to the write):

| Code | Meaning |
|---|---|
| 0x80 | refused — the button has priority (a button action happened in the last 3 s, see Status byte 14) |
| 0x81 | invalid opcode or argument |
| 0x82 | refused by protection (battery empty, too hot) |
| 0x83 | refused — lockout is active |

**Button priority.** The button always works, whatever the app did before. Every button
action starts a 3 s app lock; during it the app's OFF/ON/LEVEL/PROFILE/OUTPUT_MA writes
fail with 0x80. A button press also cancels an app-selected exact current (level 0xFF).

## 5. Profile (20 bytes, read / write)

Reading returns the parameters of the **active** profile. Writing always writes the
**Custom** profile (byte 0 must be 3) and selects it; the firmware clamps every value to the
safe range below and the value read back afterwards is what is really used. `SAVE` makes it
permanent.

| Offset | Type | Field | Range |
|---|---|---|---|
| 0 | u8 | profile id | 0–3 (write: 3) |
| 1 | u8 | flags: bit0 turbo allowed · bit1 remember last level · bit2 show battery on the RGB LED when switched on | |
| 2 | u16 | Moon, mA | 1–50 |
| 4 | u16 | Low, mA | Moon–300 |
| 6 | u16 | Medium, mA | Low–1000 |
| 8 | u16 | High, mA | Medium–2000 |
| 10 | u16 | Turbo, mA | High–3000 |
| 12 | u16 | turbo time, s | 0–300 (0 = turbo = High) |
| 14 | u16 | step-down current after the turbo time, mA | Low–High |
| 16 | u8 | temperature limit, °C (output is reduced above it) | 40–70 |
| 17 | u8 | low-voltage step-down, 10 mV steps above 3.00 V (30 → 3.30 V) | 10–60 |
| 18 | u16 | cell current limit, mA (battery side) | 200–3000 |

### 5.1 Built-in profiles

| | Extreme | Balanced | Endurance | Custom (default) |
|---|---|---|---|---|
| Moon / Low / Medium / High, mA | 3 / 40 / 250 / 900 | 3 / 30 / 200 / 600 | 2 / 15 / 100 / 300 | = Balanced |
| Turbo, mA · time | 2200 · 45 s | 1200 · 60 s | none (turbo = High) | |
| Step-down after turbo, mA | 900 | 600 | — | |
| Temperature limit | 55 °C | 50 °C | 45 °C | |
| Low-voltage step-down | 3.30 V | 3.35 V | 3.40 V | |
| Cell current limit | 2600 mA | 1600 mA | 800 mA | |

*Extreme* is for short bursts: two LP601646 cells in parallel deliver 2.6 A only for tens of
seconds. *Endurance* never drives the LED above 300 mA ("no overdrive") and keeps the cells
below 1 C. The firmware's protection limits (section 6) apply to every profile.

## 6. Protection (firmware, all profiles)

* **Temperature** (NTC): above the profile limit the current drops linearly, 15 °C → Low;
  above 70 °C Moon; above 80 °C off. Turbo is refused within 5 °C of the limit.
* **Low voltage**: below the profile's step-down voltage (under load) the level drops one
  step every 5 s; below 3.10 V Moon; below 3.00 V off (red blinks) and the light refuses to
  switch on until the cell is above 3.30 V or USB is present.
* **Cell current**: the estimated battery current, `V_LED(I) · I / (0.9 · V_BAT)` with
  `V_LED = 2.75 V + 0.15 V/A · I`, is kept below the profile's limit.
* **Charging**: enabled between 0 and 45 °C; paused while the LED runs above 500 mA.
* **Laser**: button gesture only (click + click-and-hold, while held, max 60 s), never from
  Bluetooth, never in lockout, off above 60 °C or below 3.20 V. The slide switch S2 must also
  be armed — that path is hardware and the firmware cannot override it.
