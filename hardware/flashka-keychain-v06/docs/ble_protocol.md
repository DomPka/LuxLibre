<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.6 — Bluetooth LE protocol (version 2)

This document is the contract between the firmware (`firmware/flashka-fw`) and the
phone/desktop app (`app/`). Both sides implement exactly this. All multi-byte numbers are
**little-endian**. All packets fit in 20 bytes, so the default ATT MTU (23) is enough.

Version 2 = version 1 (Aurora++ v0.5) plus:

* Status grows from 18 to **20 bytes**: byte 0 = 2, byte 18 = mode, byte 19 = paired computers;
* the **Presenter** characteristic (`a7d40006-...`, 4 bytes);
* the commands **0x0A PRESENTER** and **0x0B FORGET_HOSTS**;
* SAVE also stores the presenter settings;
* the service is now called "FlashKa Control"; every v1 UUID is unchanged.

A version 1 app that reads only bytes 0-17 still works, apart from the version byte.

Besides the app link, v0.6 has a **presenter mode** in which the light is a Bluetooth LE
keyboard (HID over GATT) for a computer (section 7). The app cannot connect then.

The FlashKa Keychain v0.7 (firmware 0.7.x) speaks the same version 2; its numbers differ in
the places listed in section 9 (Info text, turbo maximum, built-in profiles, cell-current
model).

> The firmware side is built and host-tested only; nothing here has been tested over the air
> with a v0.6 board yet (see `firmware.md` section 7).

## 1. Advertising

| Item | Flashlight mode (app) | Presenter mode (keyboard) |
|---|---|---|
| Device name | `FlashKa-XXXX` (XXXX = last two bytes of the BLE MAC, hex, upper case) | same |
| Advertising data | Flags + FlashKa Control service UUID (128-bit) | Flags + Appearance 0x03C1 (keyboard) + HID service 0x1812 (16-bit) + name |
| Scan response | complete local name | complete local name |
| Interval | 100 ms for the first 30 s of a window, then 500 ms | 30 ms for 30 s, then 152.5 ms |
| Connectable | yes, one central at a time | yes, one computer at a time |
| Security | none (no pairing). Range and the short windows are the protection; the laser can never be switched from Bluetooth. | LE Secure Connections "Just Works", bonding (section 7) |
| When | only in windows (below) | whenever no computer is connected |

The radio advertises for the app **only in windows** (the light sleeps otherwise):

1. while the main LED is on;
2. for 120 s after the main LED is switched off;
3. for 120 s after ● **3 clicks** while the light is off (the ring blinks blue);
4. while USB power is present (charging or charged);
5. while a central is connected, plus 30 s after it disconnects;
6. `KEEPALIVE` (command 0x09) extends the current window, at most 255 s per command.

When no window is open, the light is off, presenter mode is off and no USB is present, the
MCU goes to deep sleep. Any button wakes it.

## 2. GATT services

One GATT layout for both modes (GAP, GATT, Battery, Device Information, HID, FlashKa Control).
The HID service and Device Information are for the computer in presenter mode (section 7); the
app uses Battery and FlashKa Control.

### 2.1 Battery Service (standard, 0x180F)

| Characteristic | UUID | Properties | Format |
|---|---|---|---|
| Battery Level | 0x2A19 | read, notify | `u8` state of charge, 0–100 % |

### 2.2 FlashKa Control Service

Service UUID: **`a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13`** (unchanged from version 1)

| Characteristic | UUID | Properties | Size |
|---|---|---|---|
| Status | `a7d40002-3c5e-4b8a-9f61-2d0c8e5b7a13` | read, notify | **20 bytes** |
| Command | `a7d40003-3c5e-4b8a-9f61-2d0c8e5b7a13` | write (with response) | 1–3 bytes |
| Profile | `a7d40004-3c5e-4b8a-9f61-2d0c8e5b7a13` | read, write (with response) | 20 bytes |
| Info | `a7d40005-3c5e-4b8a-9f61-2d0c8e5b7a13` | read | UTF-8 text, ≤ 20 bytes (`"FlashKa fw 0.6.0"`; v0.7: `"FlashKa fw 0.7.0"`, section 9) |
| **Presenter** (v2) | `a7d40006-3c5e-4b8a-9f61-2d0c8e5b7a13` | read, write (with response) | 4 bytes |

Status is notified on every change and at least every 2 s while a central is subscribed.
Battery Level is notified when the percentage changes.

## 3. Status (20 bytes, read / notify)

| Offset | Type | Field |
|---|---|---|
| 0 | u8 | protocol version = **2** |
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
| **18** | u8 | **mode**: 0 flashlight · 1 presenter, waiting for the computer · 2 presenter, computer connected (link encrypted) |
| **19** | u8 | **paired computers** stored (0–4) |

## 4. Command (write with response)

First byte = opcode. Lengths are exact (missing or extra bytes: 0x81).

| Opcode | Arguments | Action |
|---|---|---|
| 0x01 OFF | — | main LED off |
| 0x02 ON | — | main LED on at the remembered level |
| 0x03 LEVEL | u8 level 0–4 | set level (4 = turbo; turbo follows the profile's time limit) |
| 0x04 PROFILE | u8 profile 0–3 | select profile (the light stays in its state; the level is re-applied with the new table) |
| 0x05 OUTPUT_MA | u16 mA | exact current, clamped to the profile's turbo current; above the profile's step-down current the turbo timer runs |
| 0x06 LOCKOUT | u8 0/1 | 1 = lock (button and app cannot switch on; ● four clicks unlock; also ends presenter mode); 0 = unlock |
| 0x07 IDENTIFY | — | ring blinks cyan three times |
| 0x08 SAVE | — | store the Custom profile, the selected profile, the remembered level **and the presenter settings** in flash |
| 0x09 KEEPALIVE | u8 seconds (1–255) | keep the Bluetooth window open at least this long from now; repeat to extend |
| **0x0A PRESENTER** | u8 0/1 | 1 = enter presenter mode: the main LED goes off, the app is disconnected (about 0.3 s after the write response), keyboard advertising starts. 0 = leave presenter mode. |
| **0x0B FORGET_HOSTS** | u8 0xA5 | forget all paired computers (ring white x3) |
| 0x7F FACTORY_RESET | u8 0xA5 | built-in defaults (Custom = Balanced, presenter settings = defaults), reboots. Paired computers are kept (use FORGET_HOSTS). |

Errors (ATT application error codes returned to the write):

| Code | Meaning |
|---|---|
| 0x80 | refused — the button has priority (a button action happened in the last 3 s, see Status byte 14) |
| 0x81 | invalid opcode or argument (also: ON, LEVEL or OUTPUT_MA while presenter mode is active) |
| 0x82 | refused by protection (battery empty, too hot; PRESENTER 1 below 3.20 V) |
| 0x83 | refused — lockout is active (also PRESENTER 1) |

**Button priority.** The button always works, whatever the app did before. Every button
action (also › / ‹ level steps while the light is on) starts a 3 s app lock; during it the app's
OFF / ON / LEVEL / PROFILE / OUTPUT_MA / **PRESENTER** writes fail with 0x80. A button press also
cancels an app-selected exact current (level 0xFF). IDENTIFY, SAVE, KEEPALIVE, LOCKOUT,
FORGET_HOSTS, FACTORY_RESET and Presenter writes are not blocked.

## 5. Profile (20 bytes, read / write)

Unchanged from version 1. Reading returns the parameters of the **active** profile. Writing
always writes the **Custom** profile (byte 0 must be 3) and selects it; the firmware clamps
every value to the safe range below and the value read back afterwards is what is really used.
`SAVE` makes it permanent.

| Offset | Type | Field | Range |
|---|---|---|---|
| 0 | u8 | profile id | 0–3 (write: 3) |
| 1 | u8 | flags: bit0 turbo allowed · bit1 remember last level · bit2 show battery on the ring when switched on | |
| 2 | u16 | Moon, mA | 1–50 |
| 4 | u16 | Low, mA | Moon–300 |
| 6 | u16 | Medium, mA | Low–1000 |
| 8 | u16 | High, mA | Medium–2000 |
| 10 | u16 | Turbo, mA | High–3000 (v0.7: High–2850, section 9) |
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

## 6. Presenter (4 bytes, read / write) — new in version 2

| Offset | Type | Field | Range / default |
|---|---|---|---|
| 0 | u8 | key set: 0 = Page Up / Page Down · 1 = Left / Right arrow | 0–1, default 0 |
| 1 | u8 | idle time: presenter mode ends after this many minutes without a button press | 5–120, default 30 |
| 2 | u8 | flags: bit0 swap › and ‹ (clicks and holds) | default 0 |
| 3 | u8 | reserved (write 0; reads 0) | |

Write rules: not 4 bytes, or key set > 1 → 0x81. The idle time is clamped to 5–120; undefined
flag bits and the reserved byte are ignored. Read back to see what is used. A write takes effect
at once; SAVE stores it (unsaved changes are also stored before the next deep sleep, as for the
profile). Presenter writes are not blocked by the 3 s button priority.

## 7. Presenter mode (HID keyboard)

Entered with ‹ + › held 2 s or PRESENTER 1; left with ‹ + › held 2 s, PRESENTER 0, ● 4 clicks
(lockout), after the idle time, or when the battery is empty (below 3.20 V for 2 s).

### 7.1 Inputs and keys

| Input | Key (HID usage, keyboard page 0x07) |
|---|---|
| › click | Page Down 0x4E (key set 1: Right Arrow 0x4F) |
| ‹ click | Page Up 0x4B (key set 1: Left Arrow 0x50) |
| › hold 0.8 s | F5 0x3E (once, at 0.8 s) |
| ‹ hold 0.8 s | Escape 0x29 (once) |
| ● click | B 0x05 (black screen) |
| ● hold | laser while held (no key) |
| ‹ + › held 10 s | forget all paired computers |

Each key is sent as an input report with the key pressed, then a report with all keys released
(10 ms later). A held button never keeps a key down (no key repeat on the computer). Keys are
only sent while a paired computer is connected and the link is encrypted.

### 7.2 Security and bonding

* LE Secure Connections only, IO capabilities "no input, no output" → Just Works (no PIN; the
  computer asks for a confirmation). Hosts that support only legacy pairing (Windows 10 before
  1803, Android before 6) cannot pair.
* Bondable only in presenter mode. Up to **4** bonds are stored in flash with the computer's
  CCCD (notification) settings and restored at boot; a fifth pairing replaces the oldest one.
* Report Map, Input Report (value and CCCD) and Report Reference need an encrypted link. An
  unencrypted access is answered with **Insufficient Authentication (0x05)**, which makes iOS
  start pairing. If nothing happens within 3 s of connecting the light sends a Security
  Request; a link still unencrypted after 30 s is dropped.
* A pairing request with the "OOB data present" flag is refused (Pairing Failed).
* In flashlight mode a paired computer that reconnects by itself is dropped after 10 s unless it
  uses the FlashKa Control service (the app running on that computer).

### 7.3 HID service (0x1812) and Device Information (0x180A)

| Characteristic | UUID | Properties | Value |
|---|---|---|---|
| HID Information | 0x2A4A | read | `11 01 00 02`: HID 1.11, country 0, normally connectable |
| Report Map | 0x2A4B | read (encrypted) | boot keyboard, 8-byte input report, **no report ID**, no LED output report (45 bytes) |
| HID Control Point | 0x2A4C | write without response | suspend / exit suspend (ignored) |
| Protocol Mode | 0x2A4E | read, write without response | 1 = report (boot mode uses the same report) |
| Report (input) | 0x2A4D | read (encrypted), notify (CCCD write encrypted) | 8 bytes: modifiers, 0, key, 0, 0, 0, 0, 0 |
| └ Report Reference | 0x2908 | read (encrypted) | `00 01`: report ID 0, input |
| PnP ID | 0x2A50 | read | `02 09 12 01 00 60 00`: VID source USB-IF, VID 0x1209 (pid.codes), PID 0x0001 (test PID — apply for a free PID before distributing), version 0.6.0 |

GAP Appearance (both modes): 0x03C1 Keyboard. There is no Service Changed characteristic: a
computer must forget FlashKa and pair again if a future firmware changes this layout.

## 8. Protection (firmware, all profiles)

* **Temperature** (NTC): above the profile limit the current drops linearly, 15 °C → Low;
  above 70 °C Moon; above 80 °C off. Turbo is refused within 5 °C of the limit. (v0.7: the limit
  is a set point that the light holds, section 9.)
* **Low voltage**: below the profile's step-down voltage (under load) the level drops one
  step every 5 s; below 3.10 V Moon; below 3.00 V off (red blinks) and the light refuses to
  switch on until the cell is above 3.30 V or USB is present. Presenter mode is refused and
  ended below 3.20 V.
* **Cell current**: the estimated battery current, `V_LED(I) · I / (0.9 · V_BAT)` with
  `V_LED = 2.75 V + 0.15 V/A · I`, is kept below the profile's limit (v0.7: section 9).
* **Charging**: enabled between 0 and 45 °C; paused while the LED runs above 500 mA.
* **Laser**: main button only (flashlight mode: click + click-and-hold; presenter mode: hold),
  while held, max 60 s, never from Bluetooth, never in lockout, off above 60 °C or below 3.20 V.
  The slide switch S2 must also be armed — that path is hardware and the firmware cannot
  override it.

## 9. FlashKa Keychain v0.7 (firmware 0.7.x)

Same packets and commands (version 2, same UUIDs). The v0.7 board has a stronger LED driver, an
SST-20 Gen 2 LED behind a TIR optic and one 14500 cell, a Vapcell INR14500 F15 (`firmware.md`
section 9), so these values and one rule differ:

* **Info** reads `"FlashKa fw 0.7.0"`. An app tells the boards apart by it: firmware 0.7.x runs
  on v0.7 boards, 0.6.x on v0.6 boards.
* **Turbo maximum 2850 mA** (Profile offset 10, range High–2850): the LED's 3.0 A rating less the
  worst-case tolerance of the current loop. The firmware clamps 2851–3000 to 2850 like any other
  out-of-range value; the read-back shows it. `OUTPUT_MA` is limited to the active profile's
  turbo current as before, so it never asks for more than 2850 mA either; 2850 mA stays at or
  below 3.0 A even with the worst-case tolerance. Behind that, the firmware's LED ceiling
  limits every set point to 3000 mA, whatever asks for it.
* **Temperature limit = set point** (Profile offset 16; this replaces the first point of section 8
  on the v0.7). The light regulates: it holds the sensor 0.1 to 0.3 °C below the limit and gives
  the full requested current until the temperature, predicted 8 s ahead from its rate of rise,
  gets there. It does not dim linearly over 15 °C above the limit as the v0.6 does. Requests at or
  below Low are never reduced; more than 5 °C above the limit the light drops to Low at once;
  limits above 65 °C act as 65 °C (5 °C below the Moon limit). Unchanged from section 8: Moon
  above 70 °C, off above 80 °C, Turbo refused within 5 °C of the limit, and Status bit 6
  ("thermal limit") whenever the regulator holds the current below the request. The same range
  (40–70 °C) is accepted; the built-in profiles use 50 °C (47 °C in Endurance).
* **Cell current** estimate: `V_LED(I) · I / (0.87 · V_BAT)` with `V_LED = 2.80 V + 0.15 V/A · I`.
  The built-in limit is 2800 mA in Extreme and Balanced (800 mA in Endurance): 93 % of the F15's
  3 A rating, a documented deviation from LuxLibre BAT-1 (70 %) for the timed, regulated turbo
  (`firmware.md` 9.4); the Custom profile accepts 200–3000 mA as in section 5. The battery
  protection on the board (DW01A) trips at 4.3–4.5 A with hot MOSFETs (typical), but in the worst
  case already at 3.0–3.15 A. A trip switches the whole light off at once (no Status, no
  Bluetooth) and it stays off until USB power is plugged in: switching off and on does not help.
  If the protection ever trips in turbo, use a Custom cell limit of 2500 mA.
* **LED current in Status** (offset 4) is the current the LED gets. In turbo from a part-empty
  cell the driver runs at 100 % duty and gives less than the set point: the v0.7 reports
  `min(set point, (V_BAT − 2.80 V) / 0.278 Ω)` (a half-full cell gives about 2100 mA instead of
  2850 mA), and the state of charge (offset 8) and the runtime (offset 15) use the same value. The
  battery-limit flag (bit 7) is set while the cell current limit holds the set point down.
* **Battery:** state of charge and runtime use the F15 (1400 mAh, its open-circuit curve, 0.13 V
  per A of load correction). The low-voltage rule of section 8 is unchanged, with the step-down
  voltages of the built-in profiles below (3.15 / 3.20 / 3.25 V under load); Moon below 3.10 V
  and off below 3.00 V as before.
* **Charging** at about 500 mA (the percentage while charging assumes 475 mA), with the
  temperature window of section 8. With a nearly empty cell the charger warms the board and the
  light pauses charging above 45 °C until 43 °C: normal, not a fault (Status: USB present,
  not charging).
* The other protection rules of section 8 (laser, presenter mode below 3.20 V) are unchanged.

Built-in profiles of the v0.7 (flags as on the v0.6: Extreme and Balanced turbo, remember,
battery display; Endurance remember, battery display):

| | Extreme | Balanced | Endurance | Custom (default) |
|---|---|---|---|---|
| Moon / Low / Medium / High, mA | 3 / 50 / 400 / 1800 | 3 / 40 / 250 / 1530 | 2 / 15 / 100 / 500 | = Balanced |
| Turbo, mA · time | 2850 · 60 s | 2850 · 60 s | none (turbo = High) | |
| Step-down after turbo, mA | 1800 | 1530 | — | |
| Temperature limit (set point) | 50 °C | 50 °C | 47 °C | |
| Low-voltage step-down | 3.15 V | 3.20 V | 3.25 V | |
| Cell current limit | 2800 mA | 2800 mA | 800 mA | |
