<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.6 — firmware

Firmware for the FlashKa Keychain v0.6: ESP32-C3-MINI-1-N4, Rust `no_std`, esp-hal 1.1.2 +
esp-rtos 0.3 (embassy) + esp-radio 0.18 (BLE controller) + trouble-host 0.6 (BLE host, with
LE Secure Connections). The Bluetooth protocol is specified in
[`ble_protocol.md`](ble_protocol.md) (version 2); this document describes how the firmware
implements it, how the light behaves, the flash layout, how to rebuild, and every constant you
might want to tune.

v0.6 = v0.5 plus three buttons on one ADC ladder, level stepping with › and ‹, a presenter
mode (the light becomes a Bluetooth keyboard), the RGB ring and protocol version 2.

> **Not tested on hardware.** No v0.6 board exists yet. Everything in this document is built
> and host-tested only (section 7). Items marked **(untested)** depend on the real board, the
> radio or a real computer and must be checked with the bring-up plan (7.1).

| | |
|---|---|
| Firmware version | 0.6.0 (`firmware/flashka-fw/Cargo.toml`) |
| Release image | `firmware/dist/flashka-fw-v0.6.0-merged.bin` (534 736 bytes), write at flash offset **0x0** |
| SHA-256 of the image | `e21058791bab990439835fbd977eecfed385af5837405e36ae923cb6083a8fdd` |
| Image contents | ESP-IDF 2nd-stage bootloader (from espflash 4.6.0) + partition table + app |
| Logic tests | `cd firmware/flashka-core && cargo test` (149 host tests) |
| Rebuild | `firmware/build.sh` |

---

## 1. Architecture

### 1.1 Two crates (one Cargo workspace)

```
firmware/
├── flashka-core/     no_std library, no dependencies, tested on the host with `cargo test`
│   └── src/
│       ├── controller.rs   the state machine of the light (uses everything below)
│       ├── buttons.rs      v0.6: ladder classification (mV -> button), slide-button gestures
│       ├── gesture.rs      debouncer + click / hold gesture parser of the main button
│       ├── presenter.rs    v0.6: presenter settings (Presenter characteristic), key mapping
│       ├── hid.rs          v0.6: HID report map, key codes, PnP ID, OOB pairing guard
│       ├── bonds.rs        v0.6: paired computers (bond record, max 4, oldest replaced)
│       ├── profile.rs      levels, built-in profiles, Custom clamping, 20-byte Profile packet
│       ├── protocol.rs     Status / Command packets (version 2), error codes, UUIDs
│       ├── protection.rs   thermal derating, low-voltage state machine, laser rules
│       ├── battery.rs      OCV curve, load correction, SoC filter, cell current, runtime
│       ├── charger.rs      TP4057 control on GPIO20, USB detection
│       ├── rgb.rs          ring patterns and priorities
│       ├── settings.rs     64-byte settings record (format 2) and the flash record log
│       ├── hw.rs           mA <-> PWM duty, ADC -> VBAT, NTC -> temperature
│       ├── mathx.rs        ln() for the NTC (no libm on the target)
│       └── config.rs       all tunable constants (table in section 6)
├── flashka-fw/       the ESP32-C3 binary: hardware I/O and async glue only
│   └── src/
│       ├── main.rs         init (safety first), control loop, settings + bond saves, sleep
│       ├── ble.rs          advertising (app / keyboard), connections, pairing, bonds, keys
│       ├── gatt.rs         v0.6: the GATT database (also checked on the host)
│       ├── hci.rs          v0.6: HCI transport wrapper with the OOB pairing guard
│       ├── io.rs           LEDC (LED current + ring), LED_EN, LASER_ON, CHG_SET, ADC, GPIO9
│       ├── power.rs        reset/wake info, deep sleep, panic handler
│       ├── storage.rs      flash access for the settings and bond logs (esp-storage)
│       └── board.rs        GPIO map (mirrors tools/kicad/flashka_parts.py)
├── Cargo.toml        the workspace of both crates (release profile; shared Cargo.lock and target/)
├── partitions.csv    flash layout given to espflash
├── build.sh          tests + release build + merged image + sizes (reproducible in any folder)
└── dist/             build outputs
```

Everything that can be decided without touching a register is in `flashka-core`; the firmware
samples inputs, feeds them to `flashka_core::Controller` and applies the returned `Outputs`.

### 1.2 Data flow and tasks

```
        every 10 ms                 every 100 ms
 GPIO3 ADC -> ladder class ──┐   ADC VBAT/NTC, CHRG/STDBY ──┐
                             v                              v
                 ┌────────────────────── Controller ───────────────────────┐
 BLE writes ───> │ command() / profile_write() / presenter_write()          │
 BLE events ───> │ ble_connected() / hid_connected() / set_bonded_hosts()   │
 BLE reads  <─── │ status() / profile_packet() / presenter_packet()         │
 key reports <── │ take_key()          bond erase <── take_forget_hosts()   │
                 └───────────────────────── tick() ────────────────────────┘
                                              │ Outputs
          LED current (LEDC duty + LED_EN) ───┤── LASER_ON ── ring LEDC ── CHG_SET
          advertising mode ──> BLE task       └── save settings / deep sleep / reboot
```

One embassy executor runs on esp-rtos (the scheduler esp-radio needs):

* **main** – the control loop. Every 10 ms: one ADC conversion of the button ladder, run
  `buttons()` + `tick()`, apply the outputs, store settings and bonds when needed, feed the
  watchdog, enter deep sleep when idle. Every 100 ms: four averaged conversions of VBAT and
  NTC and the charger pins.
* **ble::host_task** – the trouble-host runner (HCI to the esp-radio controller).
* **ble::peripheral_task** – advertising (for the app in flashlight mode, as a keyboard in
  presenter mode), one connection, GATT, pairing, bond and CCCD bookkeeping, key reports,
  notifications.

The controller lives in a critical-section mutex shared by the control loop and the BLE task.
The paired computers live in a second one (`ble::BONDS`): the BLE task changes them, the
control loop writes them to flash.

**Lazy Bluetooth start** (as v0.5). The BLE controller starts the first time the controller
asks for advertising while no gesture is in progress. Its start-up blocks the executor for a
moment; at boot it would make the buttons deaf right after a wake-up.

### 1.3 Start-up order

1. `esp_hal::init` (80 MHz), then **LED_EN (GPIO7) and LASER_ON (GPIO10) driven low** —
   before logging, heap or anything else. Until then their 100 k pull-downs hold them low.
2. Logger (USB-Serial-JTAG), heap for esp-radio (64 KiB + 36 KiB), pin-map self-check.
3. Reset reason and deep-sleep wake cause; the wake pins' pad hold and wake enable are
   released. **GPIO9** becomes a digital input with its internal pull-up **off** (R9, 10 k,
   is the pull-up the ladder levels are computed for).
4. Settings and paired computers from flash (partition table -> `nvs` partition -> two logs).
5. LEDC timer 0: 13 bit at 9765 Hz; channel 0 = LED current set point (0 %), channels 1-3 =
   ring (100 % = dark, common anode). CHG_SET floating.
6. ADC1 with curve-fitting calibration: GPIO0 (VBAT) and GPIO1 (NTC) at 11 dB, **GPIO3
   (button ladder) at 2.5 dB** (0-1050 mV).
7. Watchdog: TIMG1 MWDT, 3 s, system reset.
8. esp-rtos scheduler, then the **first ladder sample** (it tells which button woke the chip),
   the controller and the loop.

At the first Bluetooth start: BLE controller, then the TRNG (it has an entropy source once
the radio runs) seeds the security manager, IO capabilities "no input, no output", the paired
computers are handed to trouble-host, then the GATT server and the tasks.

### 1.4 Fail-safe design

| Situation | What happens |
|---|---|
| Reset, boot, bootloader, deep sleep | GPIOs are inputs; the 100 k pull-downs keep LED_EN and LASER_ON low. |
| Panic (incl. CPU exceptions, stack overflow) | `#[panic_handler]` clears GPIO7/GPIO10 through `GPIO_OUT_W1TC` directly, logs, `software_reset()`. |
| Hang | TIMG1 watchdog (3 s) resets the system. |
| ADC conversion fails (battery / NTC) | As v0.5: isolated failures skipped; after 5 in a row VBAT 0 / NTC 0 V -> light off, thermal shutdown. |
| ADC conversion fails (button) | GPIO9 decides: low = main button, high = none. The light keeps its v0.5 single-button behaviour. |
| Pairing request with "OOB data" | Refused before trouble-host 0.6 reaches its `todo!()` (would panic) — see 3.4. |
| No TRNG entropy at Bluetooth start | Bluetooth stays off (trouble-host would panic with an unseeded generator); the flashlight works. |
| Bluetooth fails to start | Logged; the flashlight works without Bluetooth. |
| Flash write fails | Retried every 2 s, given up after 3 failures so that sleep/reboot still happen (settings and bonds separately). |
| Deep-sleep request rejected | Software reset after 100 ms. |
| Laser | Only from the main button. No BLE opcode or code path can switch it; it is cut after 60 s, above 60 °C, below 3.20 V, by lockout — in both modes. S2 is outside firmware control. |

### 1.5 Dependency notes

* Pinned as v0.5: esp-hal 1.1.2, esp-rtos 0.3.0, esp-radio 0.18.0, esp-bootloader-esp-idf
  0.5.0, esp-storage 0.9.0, trouble-host 0.6.0.
* trouble-host features added: **`security`** (LE Secure Connections pairing and bonding; pulls
  in p256, aes, cmac, rand_chacha from crates.io) and **`connection-event-queue-size-8`**: with
  the default queue of 2 the `PairingComplete` event can be lost during pairing, and then the
  bond is never stored.
* `embedded-io = "0.7"`: the trait version bt-hci 0.8 uses, needed by the HCI wrapper (`hci.rs`).
* `embassy-sync = "0.7"`, `esp-println` with `jtag-serial` only: as v0.5 (see the v0.5 notes:
  the GATT macros need embassy-sync 0.7; UART0 TX is the red ring cathode).
* `Rtc::sleep_deep` is not used (as v0.5): `power::deep_sleep` issues the request with
  `Rtc::sleep` and waits.

### 1.6 Pins and button ladder

Mirrors `GPIO_MAP` in `tools/kicad/flashka_parts.py` (`flashka-fw/src/board.rs`). Unchanged from
v0.5 except GPIO3/GPIO9 (button ladder) and the RGB nets (now the two ring LEDs in parallel).

| GPIO | Net | Use in firmware |
|---|---|---|
| 0 | VBAT_ADC | ADC1_CH0, 11 dB, curve calibration; VBAT = 2 x V |
| 1 | NTC_ADC | ADC1_CH1, 11 dB; 100 k to 3V3, NTC 100 k B4250 to GND |
| 2 | RGB_B | LEDC ch3, active low: ring blue (LED3 + LED4) |
| 3 | BTN | **ADC1_CH3, 2.5 dB (0-1050 mV)**, curve calibration: button ladder. Deep sleep: digital input, wake on low |
| 4 | CHG_STAT | input + pull-up, low = charging; wake source |
| 5 | CHG_DONE | input + pull-up, low = charge complete; wake source |
| 6 | LED_PWM | LEDC ch0, 13 bit, 9.77 kHz -> LED current set point |
| 7 | LED_EN | output, high = LED driver on (100 k pull-down) |
| 8 | RGB_G | LEDC ch2, active low: ring green |
| 9 | BTN (strap) | **digital input, internal pull-up off after boot**: low = some button; never driven |
| 10 | LASER_ON | output, high = laser on if S2 armed (100 k pull-down) |
| 18 / 19 | USB D- / D+ | USB-Serial-JTAG (log, flashing) |
| 20 | CHG_SET | low = ~300 mA, floating = 10 mA trickle, high = charger off |
| 21 | RGB_R | LEDC ch1, active low: ring red (U0TXD: boot log flickers it) |

Button ladder on BTN (spec 3.2; R9 10 k to 3V3, R30 1 k, R31 2.2 k):

| Pressed | BTN voltage | ADC class (mV) | GPIO9 |
|---|---|---|---|
| none | 3.30 V | > 810: none (the ADC saturates near 1050 mV) | high |
| ● main (alone or with any other) | 0 V | < 106: main | low |
| ‹ + › together | 0.212 V | 106 to < 256: both | low |
| › next | 0.300 V | 256 to < 448: next | low |
| ‹ previous | 0.595 V | 448 to 810: previous | low |

The thresholds are the midpoints between the nominal levels. With 1 % resistors, the
datasheet's ± 10 mV ADC error (2.5 dB, after calibration) and 3V3 ± 2 %, every level stays
inside its band with at least 22 mV to spare (worst case › near 256 mV; ‹ + › 25 mV; ‹ 115 mV;
host test `ladder_tolerance`). Every press is a valid digital low (VIL ≤ 0.825 V):
any button wakes the chip, and any button held while USB is plugged in starts download mode.

---

## 2. How the light works (user manual)

### 2.1 The three buttons

All three are on the **bottom face**. With the floor up and the head away from you the row
reads, head -> tail: **›  ●  ‹** (› next is towards the screen when presenting).

* **●** main button (stainless, with the glowing ring around it): exactly the v0.5 button.
* **›** next and **‹** previous: level up / down while the light is on; slide keys in
  presenter mode.
* **‹ + ›** pressed together: mode change (2 s) and "forget computers" (10 s).

*Click* = press shorter than 0.4 s (●) or 0.8 s (› and ‹). *Hold* = longer. Contacts are
debounced (25 ms). The main button always wins: while ● is pressed, › and ‹ are ignored until
every button has been released. A › or ‹ click counts when you release it, so pressing ‹ + ›
never sends a click of the first button.

### 2.2 Flashlight mode (default after power-up)

| Light is OFF | |
|---|---|
| ● 1 click | On at the remembered level (Moon / Low / Medium / High). |
| ● hold | On in Moon. |
| ● 2 clicks | Turbo (High if the profile has no turbo or the board is too warm). |
| ● click, then click-and-hold | **Laser** while held (max 60 s; see 2.6). The main LED stays off. |
| ● 3 clicks | Opens a 120 s Bluetooth window for the app (ring blinks blue twice). |
| ● 4 clicks | Lockout on (red x3) / off (green x3). |
| › or ‹ | Ignored: no light, no LED (pocket safety). |
| ‹ + › held 2 s | Presenter mode (2.3). |

| Light is ON | |
|---|---|
| ● 1 click | Off (settings are saved if they changed). |
| ● hold | Steps Low -> Medium -> High -> Low ... every 0.6 s (as v0.5). |
| ● 2 clicks | Turbo on / back to the previous level. |
| ● 3 clicks | Battery check on the ring: 1-5 blinks in green / yellow / red. |
| › click (or hold) | One level up: Moon -> Low -> Medium -> High. No wrap; never into Turbo. From Turbo: nothing. |
| ‹ click (or hold) | One level down: High -> Medium -> Low -> Moon. No wrap. From Turbo: High. |
| ‹ + › held 2 s | Presenter mode: the main LED goes off. |

A › / ‹ step counts as a button action: it blocks app commands that switch or dim the light for
3 s and cancels an exact current set by the app (stepping then starts from the remembered
level). The level you step to is remembered. A › / ‹ hold steps once (at 0.8 s), not repeatedly.

| In lockout | |
|---|---|
| ● 4 clicks | Unlock (green x3). |
| anything else | Ignored. ● clicks give one short red flash; holds, › ‹ and ‹ + › give nothing. |

**From deep sleep** any button wakes the chip, and the first ADC sample tells which one is still
held. A press that is already over at that sample (shorter than the ~0.2 s boot) counts as one
● click — the chip cannot tell which button it was (section 8).

### 2.3 Presenter mode

FlashKa becomes a Bluetooth keyboard that turns slides; the laser is the pointer.

| Input | Action (key sent) |
|---|---|
| › click | next slide: **Page Down** (key set "arrows": Right Arrow) |
| ‹ click | previous slide: **Page Up** (key set "arrows": Left Arrow) |
| › hold 0.8 s | start the show: **F5** (sent once, at 0.8 s) |
| ‹ hold 0.8 s | end the show: **Esc** (sent once) |
| ● click | black screen on / off: **B** |
| ● hold | **laser** on while held — same rules as in flashlight mode (S2 armed, max 60 s, not hot, not flat, never in lockout); works with or without a computer |
| ● 4 clicks | lockout on; this also leaves presenter mode |
| ‹ + › held 2 s | leave presenter mode |
| ‹ + › held 10 s | forget all paired computers (ring white x3) |

* Every key goes out as two reports: key down, then key up 10 ms later. Holding a button never
  holds the key down, so the computer's key repeat cannot flip several slides.
* ● 2 or 3 clicks send nothing (two B presses would cancel each other anyway).
* The main LED cannot be switched on in presenter mode.
* Keys are sent only while a paired computer is connected (ring off); while the light is waiting
  (cyan breathing) presses are not stored.
* The app setting "swap" exchanges › and ‹ (clicks and holds).
* Presenter mode ends by itself after the idle time (default **30 min** without a button press,
  5-120 min in the app) and when the battery is empty (below 3.20 V for 2 s; five red blinks).
  It is refused below 3.20 V (one red blink).
* The radio stays on in presenter mode: about **20 mA (estimate, untested)**, that is about
  30-40 h with the 800 mAh pack. The light does not sleep in presenter mode.
* The phone app cannot connect while presenter mode is active (one connection; the light
  advertises as a keyboard, not with the app's service UUID).

**Forget and the 10 s hold.** The 2 s mode change happens while you keep holding: from
flashlight mode the light enters presenter mode at 2 s and forgets the computers at 10 s (it
stays in presenter mode, ready to pair a new one). From presenter mode it leaves at 2 s and
forgets at 10 s. Also remove "FlashKa" on the computer, otherwise it keeps trying the old keys.

### 2.4 First pairing (untested on all systems)

Pairing works only in presenter mode. Enter it with ‹ + › for 2 s (magenta x2, then **cyan
breathing**). The light uses LE Secure Connections "Just Works": there is no PIN; the computer
asks you to confirm. When the computer is connected the ring blinks **cyan twice and goes off**.

| System | Steps | Notes |
|---|---|---|
| Windows 10 (1803 or newer) / 11 | Settings > Bluetooth & devices > Add device > Bluetooth > "FlashKa-XXXX" (keyboard icon) | Older Windows 10 cannot pair: trouble-host 0.6 supports only LE Secure Connections. |
| macOS | System Settings > Bluetooth > "FlashKa-XXXX" > Connect | The Keyboard Setup Assistant may open: close it. Keynote: choose the "arrows" key set in the app; F5 does not start a Mac show (use the computer for that). |
| Android 6 or newer | Settings > Connected devices > Pair new device > "FlashKa-XXXX" > Pair | |
| iOS / iPadOS 9 or newer | Settings > Bluetooth > "FlashKa-XXXX" (Other devices) > Pair | iOS starts pairing when the light answers "insufficient authentication"; the on-screen keyboard hides while a keyboard is connected. |
| Linux (BlueZ, kernel 3.19+) | `bluetoothctl`: `scan on`, `pair <addr>`, `trust <addr>`, `connect <addr>` | |

* Up to **4 computers** are remembered (in flash, with their notification settings); pairing a
  fifth replaces the one paired longest ago.
* After that, entering presenter mode is enough: the computer reconnects by itself (cyan
  double blink).
* Which keys suit which program: PowerPoint (Windows/Mac) and LibreOffice Impress: Page Up /
  Down, B, Esc (F5 starts PowerPoint and Impress on Windows/Linux). Keynote and Google Slides:
  use the "arrows" key set. PDF viewers: Page Up / Down.
* The PnP ID uses the pid.codes test PID 0x1209:0x0001. **Apply for a free PID at pid.codes
  before distributing the firmware.**

### 2.5 Ring colours

The ring (two RGB LEDs around ●, driven together by the three v0.5 status-LED GPIOs) shows,
highest priority first:

| Pattern | Meaning |
|---|---|
| Red steady | laser on |
| White x3 | paired computers forgotten |
| Cyan double blink, then off | presenter mode: computer connected |
| Short white blip (40 ms) | presenter key sent |
| Magenta x2 | presenter mode entered / left |
| Red x3 / green x3 | lockout on / off |
| Cyan x3 | "Identify" from the app |
| Blue x2 | Bluetooth window opened (● 3 clicks while off) |
| 1-5 blinks green / yellow / red | battery check (● 3 clicks while on) |
| One red blink | request refused (turbo too hot, laser not allowed, switch-on refused, presenter mode refused) |
| Five fast red blinks | battery empty: switched off, switch-on refused, or presenter mode ended |
| Short red flash | ● click while locked |
| Cyan breathing (2 s) | presenter mode: waiting for the computer |
| Green / yellow / red for 2 s after switch-on | battery > 50 % / 20-50 % / < 20 % (profile flag) |
| Red slow breathing (3 s) | USB connected, charging |
| Green steady | USB connected, charge complete |
| Red blink every 4 s (light on) | battery below 10 % |
| Cyan (dim) steady | flashlight mode: app connected |
| Blue double blink every 3 s | flashlight mode: Bluetooth window open, nobody connected |

One-shot patterns (the blinks) overlay the steady and breathing states. A presenter one-shot is
not cut short by a lower one in the table (the white x3 is never hidden by a key blip). Blue is
the weakest colour of this LED (4.5 mcd at 2 mA), so presenter states use cyan. The red
resistors are now 330 Ω (more red behind the light pipe); the colour balance (`RGB_FULL_*`) is
not tuned yet **(untested)**.

### 2.6 Levels, profiles, turbo, laser, protection, charging, battery (as v0.5)

#### Levels and profiles

| | Extreme | Balanced (default) | Endurance | Custom |
|---|---|---|---|---|
| Moon / Low / Medium / High | 3 / 40 / 250 / 900 mA | 3 / 30 / 200 / 600 mA | 2 / 15 / 100 / 300 mA | set by the app, default = Balanced |
| Turbo | 2200 mA for 45 s | 1200 mA for 60 s | none (turbo = High) | |
| After the turbo time | 900 mA | 600 mA | — | |
| Temperature limit | 55 °C | 50 °C | 45 °C | 40-70 °C |
| Low-voltage step-down | 3.30 V | 3.35 V | 3.40 V | 3.10-3.60 V |
| Cell current limit | 2600 mA | 1600 mA | 800 mA | 200-3000 mA |
| Flags | turbo, remember, battery display | turbo, remember, battery display | remember, battery display | |

The profile is chosen in the app (there is no button gesture for it). › / ‹ step through the
four levels of the active profile.

#### Turbo

Turbo runs at most the profile's turbo time, then the light steps down to the profile's
step-down current (the app shows "automatic" as the reason). Two clicks then return to the
level used before turbo; two more clicks start a new turbo. Thermal derating, the cell
current limit and low-voltage protection apply on top at all times.

#### Laser

Flashlight mode: ● click, then click-and-hold while the light is off; presenter mode: ● hold.
The laser is on while the button stays held — at most 60 s per press (release and repeat the gesture to continue). It goes off above
60 °C or below 3.20 V and stays off until the button is released. Never in lockout, never from
Bluetooth. The slide switch S2 must be armed as well; the firmware cannot see or override S2.

#### Protection (what you notice)

* **Hot**: above the profile's temperature limit the brightness falls smoothly, reaching Low
  15 °C above the limit; above 70 °C Moon; above 80 °C the light switches off and cannot be
  switched on again until it has cooled below 75 °C.
* **Battery low**: below the profile's step-down voltage (measured with the LED running) the
  light drops one level every 5 s; below 3.10 V Moon; below 3.00 V it switches off (five red
  blinks) and refuses to switch on until the battery rests above 3.30 V or USB is connected.
  Choosing a level again lifts the step-down; it comes back if the voltage is still low.
* **Cell current**: the estimated battery current `V_LED(I)·I / (0.9·V_BAT)` with
  `V_LED = 2.75 V + 0.15 V/A·I` is kept below the profile's limit (the output is reduced).

#### Charging

USB-C charging at ~300 mA (nominal; the SoC estimate assumes 280 mA) between 0 °C and 45 °C (resumes 2 °C inside the window after a
temperature pause). Charging pauses while the LED runs above 500 mA. Plugging USB in resets
the MCU (VBUS-edge reset), keeps it awake and keeps Bluetooth reachable while connected.
Without firmware (e.g. a completely flat cell) the charger trickles at 10 mA.

#### Battery percentage and runtime

The percentage comes from the LiPo open-circuit curve (4.20 V = 100 % ... 3.30 V = 0 %) with
a load correction of +0.12 V per A of estimated cell current while the LED is on (and -0.12 V/A
of charge current while fast-charging), filtered so that it does not jump (at most 0.5 %/s,
small dead band, and it only moves "backwards" for differences above 3 %). "Charge complete"
reads 100 %. Runtime = 800 mAh x SoC / (estimated LED cell current + 20 mA for the MCU and
radio); the MCU term matters at Moon, where the LED itself draws ~2 mA from the cell.

### 2.7 Bluetooth windows and sleep

Flashlight mode: as v0.5 — the radio advertises for the app only in windows (light on; 120 s
after it is switched off; 120 s after ● 3 clicks; while USB is connected; while the app is
connected and 30 s after; KEEPALIVE). Fast 100 ms for the first 30 s, then 500 ms.

Presenter mode: the radio advertises as a keyboard whenever no computer is connected: 30 ms
for the first 30 s (after entering the mode or after a disconnect), then 152.5 ms (the
intervals Apple QA1931 and Windows Swift Pair ask for). No sleep.

When the light is off, presenter mode is off, no window is open and no USB is connected, the
MCU goes to deep sleep. Any button or USB wakes it. A button held for 10 s while it does
nothing (lockout, or › / ‹ with the light off — e.g. in a pocket) counts as stuck: the MCU then
sleeps without the button as a wake source and checks it every 20 s.

### 2.8 Flashing

Hold ● (any button works: every press pulls GPIO9 low) while plugging in USB: the ROM starts
download mode. Write `flashka-fw-v0.6.0-merged.bin` at offset 0x0 with the web flasher, or:

```
espflash write-bin 0x0 firmware/dist/flashka-fw-v0.6.0-merged.bin
espflash monitor            # firmware log over USB-Serial-JTAG
```

Writing the merged image erases the settings **and the paired computers** (the `nvs` region is
0xFF in the image); remove FlashKa on each computer and pair again. To keep both, flash only the
app: `espflash flash --partition-table firmware/partitions.csv firmware/dist/flashka-fw-v0.6.0.elf`.

---

## 3. Bluetooth implementation notes

### 3.1 Address, name, advertising

* Public address = eFuse base MAC with the Bluetooth offset; it never changes, so paired
  computers find the light again (trouble-host's controller address, no random address).
* Name `FlashKa-XXXX` = last two address bytes, upper-case hex; also the GAP Device Name.
  GAP Appearance: Keyboard (0x03C1), the same in both modes (one GATT layout).
* Flashlight-mode advertising (21 bytes, as v0.5): Flags + complete list of 128-bit service UUIDs
  (FlashKa Control). Scan response: complete local name.
* Presenter-mode advertising (25 bytes): Flags (LE general discoverable, BR/EDR not supported),
  Appearance 0x03C1, 16-bit service UUID 0x1812 (HID), complete local name. Scan response: name.
  Byte layout checked on the host: `02 01 06 03 19 c1 03 03 02 12 18 0d 09 "FlashKa-XXXX"`.

### 3.2 GATT database

One layout for both modes, so a paired computer never sees it change. Handles as generated by
trouble-host 0.6 (dumped on the host from `flashka-fw/src/gatt.rs`):

| Handles | Service / characteristic | Access |
|---|---|---|
| 1-5 | GAP: Device Name, Appearance | read |
| 6 | GATT service (no Service Changed, see 8) | — |
| 7-10 | Battery Service: Battery Level (9) + CCCD (10) | read, notify |
| 11-13 | Device Information: PnP ID (13) `02 09 12 01 00 60 00` | read |
| 14 | HID service 0x1812 | |
| 16 | HID Information `11 01 00 02` (HID 1.11, country 0, normally connectable) | read |
| 18 | Report Map (45 bytes, boot keyboard, no report ID, no LED report) | read, **encrypted** |
| 20 | HID Control Point | write without response (ignored) |
| 22 | Protocol Mode (1 = report) | read, write without response |
| 24 | Input Report (8 bytes) | read **encrypted**, notify |
| 25 | its CCCD | write **encrypted** |
| 26 | Report Reference `00 01` (no ID, input) | read **encrypted** |
| 27-38 | FlashKa Control: Status 29 (+CCCD 30), Command 32, Profile 34, Info 36, Presenter 38 | as `ble_protocol.md` |

* An unencrypted read or write of 18, 24, 25 or 26 is answered with **Insufficient
  Authentication (0x05)** (trouble-host's default would be Insufficient Encryption 0x0F); this
  is what makes iOS start pairing. Other refused requests keep trouble-host's error code.
* HID Control Point and Protocol Mode are not encrypted on purpose: trouble-host 0.6 answers a
  refused write *command* with an error response, which ATT does not allow.
* Reads of Status, Profile, Presenter and Battery Level refresh the value from the controller
  first. Command, Profile and Presenter writes go to the controller; a refusal becomes an ATT
  error with the protocol's application code.

### 3.3 Pairing and bonds

* Security manager: trouble-host 0.6 `security`, LE Secure Connections only, IO capabilities
  "no input, no output" -> Just Works (security level "encrypted", unauthenticated). The
  generator is seeded from the TRNG after the radio is up.
* A connection is **bondable only in presenter mode** (`set_bondable(true)`); in flashlight mode
  the default (not bondable) is kept.
* `PairingComplete` with bond information: the bond (identity address, IRK, LTK, level) and the
  link's current CCCD table go into the bond table (max 4, the oldest pairing is replaced and
  also removed from trouble-host); the control loop writes it to flash.
* A paired computer that reconnects re-encrypts with its stored key without a
  `PairingComplete` event; the firmware notices the encrypted link (polled every 20 ms) and puts
  back the computer's stored subscriptions (`set_cccd_table`), so notifications work at once.
* Every accepted write from a paired, encrypted computer (CCCD changes) updates its stored CCCD
  table; flash is written only if it changed.
* At boot the stored bonds are given to trouble-host with `add_bond_information` before
  advertising. "Forget" clears the table, the flash record and trouble-host's list, and drops a
  connected paired computer.
* Presenter mode: if the computer has not started pairing / encryption after 3 s the light
  sends a Security Request; a link still unencrypted after 30 s is dropped (so a stray device
  cannot block the computer).
* Flashlight mode: a paired computer that connects by itself (HID auto-reconnect) is not
  counted as "app connected" (it would hold the radio window open) and is dropped after 10 s,
  unless it uses the FlashKa Control service (the app running on that computer).
* When the mode changes, the current link is dropped 300 ms later (after the write response of
  a PRESENTER command has gone out).

### 3.4 trouble-host 0.6 OOB guard

trouble-host 0.6.0 reaches `todo!("OOB not implemented")` (`pairing/peripheral.rs:328`) when a
central's Pairing Request has the "OOB data present" flag. `hci.rs` wraps the esp-radio HCI
transport: every packet from the controller is checked; an SMP Pairing Request (L2CAP CID 6,
code 0x01) with the OOB flag set gets its Secure Connections bit cleared, so trouble-host
refuses it at once with Pairing Failed (it only supports LE Secure Connections). The byte logic
is `flashka_core::hid::smp_reject_oob` (host-tested). **(untested on air.)**

### 3.5 Keys and notifications

* Keys: `Controller::take_key()` -> Input Report notification `00 00 <usage> 00 00 00 00 00`,
  10 ms later `00 x 8`. Usages: Page Down 0x4E, Page Up 0x4B, Right 0x4F, Left 0x50, F5 0x3E,
  Esc 0x29, B 0x05.
* Status: on every change of flags, profile, level, LED current, SoC, control source, laser,
  mode or bonded count (at most every 150 ms) and every 2 s. Battery Level when the percentage
  changes. A notify is a no-op while the client is not subscribed.

### 3.6 Details the protocol leaves open

| Topic | Firmware behaviour |
|---|---|
| Command length | Exact: missing or extra argument bytes -> 0x81. |
| Error priority | 0x81 (malformed) before 0x80 (button priority) before 0x83 (lockout) before 0x82 (protection). |
| PRESENTER 1 | 0x80 during the 3 s app lock, 0x83 in lockout, 0x82 below 3.20 V; in presenter mode already: success, no change. |
| PRESENTER 0 | Leaves presenter mode; in flashlight mode: success, no change. |
| ON / LEVEL / OUTPUT_MA in presenter mode | 0x81 (only reachable from a paired computer). |
| FORGET_HOSTS | Not subject to the app lock; ring white x3. |
| Presenter write | Not 4 bytes or key set > 1 -> 0x81; idle time clamped to 5-120; flag bits other than bit 0 and the reserved byte are ignored (read back as 0). Not subject to the app lock. Takes effect at once; SAVE (or the next sleep) stores it. |
| FACTORY_RESET | Settings to defaults (incl. presenter settings), leaves presenter mode, reboots; paired computers are kept. |
| Status byte 18 | 2 = a paired computer is connected **and** the link is encrypted; 1 = presenter mode otherwise. |
| v0.5 behaviour | Everything in the v0.5 table (lengths, LOCKOUT while on, KEEPALIVE, Status level when off, sensor faults, fast advertising, empty shutdown) is unchanged. |

---

## 4. Flash layout

ESP32-C3-MINI-1-N4, 4 MB. `firmware/partitions.csv` (identical to espflash's default table):

| Offset | Size | Content |
|---|---|---|
| 0x0000 | 0x8000 | ESP-IDF 2nd-stage bootloader (from espflash 4.6.0) |
| 0x8000 | 0x1000 | Partition table (with MD5) |
| 0x9000 | 0x6000 | `nvs`: 0x9000-0xAFFF **settings log**, 0xB000-0xCFFF **paired-computer log**, rest unused |
| 0xF000 | 0x1000 | `phy_init` (unused by esp-radio) |
| 0x10000 | 0x3F0000 | `factory` app (image 469 200 bytes, 11 % used) |

Both logs work like v0.5's settings log: two 4 KiB sectors, a save appends after the newest
record, a full sector makes the log continue in the freshly erased other sector, the newest
record with a valid CRC wins (a power failure never loses the previous state), nothing is
written when nothing changed.

### 4.1 Settings record (64 bytes, little-endian, 64 per sector)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic `"AUR5"` (kept so that v0.5 records still load) |
| 4 | 1 | format version: **2**; version 1 (v0.5) is still read, with default presenter settings |
| 5 | 1 | selected profile (0..3) |
| 6 | 1 | remembered level (0..3) |
| 7 | 1 | flags: bit0 lockout, bit1 battery-empty latch |
| 8 | 4 | sequence number |
| 12 | 20 | Custom profile (Profile packet format, id 3) |
| 32 | 4 | presenter settings (Presenter characteristic format: key set, idle minutes, flags, 0) |
| 36 | 24 | reserved (0xFF) |
| 60 | 4 | CRC-32 (IEEE) of bytes 0..60 |

**Saved** as v0.5 (on SAVE, button switch-off, lockout and empty-latch changes, before sleep and
the factory-reset reboot), now including the presenter settings. Presenter mode itself is not
saved: after a reboot the light starts in flashlight mode.

### 4.2 Paired-computer record (256 bytes, 16 per sector)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic `"FKB1"` |
| 4 | 1 | format version (1) |
| 5 | 1 | number of bonds (information only) |
| 6 | 2 | reserved (0xFF) |
| 8 | 4 | sequence number |
| 12 | 4 | next pairing number |
| 16 | 4 x 59 | bonds |
| 252 | 4 | CRC-32 (IEEE) of bytes 0..252 |

Bond (59 bytes): flags (bit0 valid, bit1 IRK present, bit2 authenticated), identity address
(6, LSB first), IRK (16), LTK (16), pairing number (4, higher = newer), CCCD table 4 x
(handle u16, value u16). Saved after a pairing, after a CCCD change and after "forget".

---

## 5. Building

Requirements as v0.5: Rust with `build-std` for `riscv32imc-unknown-none-elf` (a rustup
toolchain with `rust-src`, or the distribution rustc 1.91 with `RUSTC_BOOTSTRAP=1` as used for
`dist/`), a host Rust toolchain for the tests, espflash 4.x. crates.io must be reachable the
first time (the `security` feature adds p256, aes, cmac, rand_chacha).

```
firmware/build.sh                 # host tests, release build, merged image, sizes, SHA-256
SKIP_TESTS=1 firmware/build.sh    # without the host tests
```

Environment overrides: `FW_RUST_BIN` (default `/usr/lib/rust-1.91/bin`), `HOST_CARGO`, `ESPFLASH`,
`CARGO_TARGET_RISCV32IMC_UNKNOWN_NONE_ELF_LINKER` (a `rust-lld`). By hand:

```
cd firmware/flashka-core && cargo test
cd firmware/flashka-fw && RUSTC_BOOTSTRAP=1 cargo build --release   # build.sh adds the path remapping
espflash save-image --chip esp32c3 --merge --skip-padding --flash-size 4mb \
    --partition-table firmware/partitions.csv \
    firmware/target/riscv32imc-unknown-none-elf/release/flashka-fw \
    firmware/dist/flashka-fw-v0.6.0-merged.bin
```

The log level is set at build time with `ESP_LOG` (default `info`). Build with
`ESP_LOG=debug` to log every ladder class change with its mV reading (bring-up).

**Memory** (release build): flash 428 778 bytes of code + constants (app image 469 200 bytes,
11 % of the app partition); RAM 90 104 bytes static (IRAM code 30 676, data 9 636, bss 49 792
incl. the 36 KiB heap), 230 400 bytes left for the stack, plus the 64 KiB heap in the reclaimed
bootloader RAM.

**Reproducible**: the image depends only on the sources and the compiler (rustc 1.91.1), not on
the folder or the machine it is built on. `build.sh` sets `SOURCE_DATE_EPOCH` (app descriptor time
2026-10-17 00:00:00; esp-bootloader-esp-idf 0.5.0 reads it in microseconds) and maps the
machine-specific source paths with `--remap-path-prefix` (this folder becomes `firmware`, the cargo
registry `/cargo/registry/src`, the Rust sysroot `/rust`). The two crates form one Cargo workspace
(`firmware/Cargo.toml`, shared `Cargo.lock` and `target/`), so cargo hashes their paths relative to
it. A clean build in the repository and a clean build of a copy in another folder gave the
identical image (SHA-256 above) and ELF. The CI job *Firmware build* rebuilds the image on GitHub
and compares it with `dist/`.

---

## 6. Tunable constants

Values marked *P* are fixed by `ble_protocol.md`, *H* by the hardware. Times in ms unless
noted, temperatures in 0.1 °C ("dC"), voltages in mV. New in v0.6: 6.1 and 6.2; unchanged from
v0.5: 6.3-6.5.

### 6.1 `flashka-core/src/config.rs`

| Constant | Value | Meaning |
|---|---|---|
| `BTN_MAIN_BELOW_MV` | 106 | Ladder reading below this = ● (0 V nominal). *H* |
| `BTN_BOTH_BELOW_MV` | 256 | 106 to < 256 = ‹ + › (0.212 V nominal). *H* |
| `BTN_NEXT_BELOW_MV` | 448 | 256 to < 448 = › (0.300 V nominal). *H* |
| `BTN_PREV_MAX_MV` | 810 | 448 to 810 = ‹ (0.595 V nominal); above = no button. *H* |
| `SLIDE_HOLD_MS` | 800 | › / ‹ hold threshold (F5 / Esc, single level step). |
| `BOTH_PRESENTER_MS` | 2000 | ‹ + › hold: enter / leave presenter mode. |
| `BOTH_FORGET_MS` | 10000 | ‹ + › hold: forget paired computers. |
| `PRESENTER_IDLE_DEFAULT_MIN` | 30 | Default idle time (min). *P* |
| `PRESENTER_IDLE_MIN_MIN` / `_MAX_MIN` | 5 / 120 | Idle time range (min). *P* |
| `PRESENTER_MIN_MV` | 3200 | Presenter mode refused / ended below this ("empty"; = laser limit). |
| `PRESENTER_EMPTY_DELAY_MS` | 2000 | Persistence before the empty exit. |
| `HID_ADV_FAST_INTERVAL_US` | 30000 | Keyboard advertising, first 30 s. |
| `HID_ADV_FAST_PERIOD_MS` | 30000 | Length of the fast period. |
| `HID_ADV_SLOW_INTERVAL_US` | 152500 | Keyboard advertising afterwards (Apple QA1931 value). |
| `KEY_QUEUE_LEN` | 8 | Keys waiting for the radio. |
| `BONDS_MAX` | 4 | Paired computers kept. *P* (spec) |
| `STUCK_BUTTON_MS` | 10000 | Now also for › / ‹ held with the light off. |

### 6.2 Firmware (`flashka-fw/src`)

| Constant | Value | Meaning |
|---|---|---|
| `PRESENTER_UNENCRYPTED_TIMEOUT_MS` (ble.rs) | 30000 | Presenter mode: unencrypted link dropped. |
| `PRESENTER_SECURITY_REQUEST_MS` (ble.rs) | 3000 | Presenter mode: Security Request if nothing happened. |
| `HOST_IN_FLASHLIGHT_MODE_MS` (ble.rs) | 10000 | Flashlight mode: paired computer without app use dropped. |
| `KEY_RELEASE_GAP_MS` (ble.rs) | 10 | Key-down to key-up report. |
| `MODE_CHANGE_DISCONNECT_MS` (ble.rs) | 300 | Link dropped this long after a mode change. |
| `SAVE_MAX_FAILURES` (main.rs) | 3 | Flash write attempts per record before giving up. |
| `DEFAULT_REGION_OFFSET` (storage.rs) | 0x9000 | Settings + bond region if the partition table cannot be read. |

### 6.3 Unchanged from v0.5: `flashka-core/src/config.rs`

| Constant | Value | Meaning |
|---|---|---|
| `DEBOUNCE_MS` | 25 | Button level must be stable this long. |
| `CLICK_MAX_MS` | 400 | Shorter press = click, longer = hold. |
| `CLICK_GAP_MS` | 400 | Max pause between clicks of one gesture. |
| `HOLD_REPEAT_MS` | 600 | Level step period while holding with the light on. |
| `APP_LOCK_MS` | 3000 | App lock after a button action. *P* |
| `BLE_WINDOW_AFTER_OFF_MS` | 120000 | Window after switch-off. *P* |
| `BLE_WINDOW_TRIPLE_CLICK_MS` | 120000 | Window after 3 clicks. *P* |
| `BLE_WINDOW_AFTER_DISCONNECT_MS` | 30000 | Window after a disconnect. *P* |
| `BLE_KEEPALIVE_MAX_S` | 600 | KEEPALIVE cap (s). *P* |
| `ADV_FAST_PERIOD_MS` | 30000 | Fast advertising at the start of a window. *P* |
| `ADV_FAST_INTERVAL_MS` | 100 | Fast advertising interval. *P* |
| `ADV_SLOW_INTERVAL_MS` | 500 | Slow advertising interval. *P* |
| `STATUS_NOTIFY_PERIOD_MS` | 2000 | Periodic Status notification. *P* |
| `STATUS_NOTIFY_MIN_GAP_MS` | 150 | Rate limit of change-triggered notifications. |
| `LASER_MAX_MS` | 60000 | Longest laser burst per press. *P* |
| `LASER_MAX_TEMP_DC` | 600 | Laser off above 60.0 °C. *P* |
| `LASER_MIN_MV` | 3200 | Laser off below 3.20 V. *P* |
| `THERMAL_DERATE_SPAN_DC` | 150 | Linear derating span above the limit (to Low). *P* |
| `THERMAL_MOON_DC` | 700 | Moon above 70.0 °C. *P* |
| `THERMAL_OFF_DC` | 800 | Off above 80.0 °C. *P* |
| `THERMAL_OFF_CLEAR_DC` | 750 | May switch on again below 75.0 °C. |
| `TURBO_TEMP_MARGIN_DC` | 50 | Turbo refused within 5.0 °C of the limit. *P* |
| `NTC_OPEN_MV` | 2800 | NTC node above this = open sensor (or < about -7 °C). |
| `NTC_SHORT_MV` | 100 | NTC node below this = shorted sensor (> about 135 °C). |
| `NTC_FAULT_SAMPLES` | 3 | Consecutive bad NTC samples before a fault is declared. |
| `LV_STEP_PERIOD_MS` | 5000 | One level down per period below the profile voltage. *P* |
| `LV_MOON_MV` | 3100 | Moon below this (under load). *P* |
| `LV_OFF_MV` | 3000 | Off below this (under load). *P* |
| `LV_RECOVER_MV` | 3300 | Empty latch released above this at rest. *P* |
| `LV_MOON_DELAY_MS` | 1000 | Persistence before the Moon limit. |
| `LV_OFF_DELAY_MS` | 2000 | Persistence before the empty shutdown. |
| `CELL_CAPACITY_MAH` | 800 | Capacity for the runtime estimate. |
| `LOAD_CORR_MV_PER_A` | 120 | SoC load correction (mV per A of cell current). |
| `MCU_AWAKE_MA` | 20 | MCU + radio current in the runtime estimate. |
| `CHARGE_FAST_MA` | 280 | Charge current (SoC correction while charging). |
| `SOC_SLEW_X10_PER_S` | 5 | SoC filter slew limit (0.1 %/s). |
| `SOC_RECOVER_HYST_X10` | 30 | SoC "backwards" threshold (0.1 %). |
| `SOC_DEADBAND_X10` | 5 | SoC dead band (0.1 %). |
| `CHARGE_MIN_DC` | 0 | Charging allowed from 0.0 °C ... *P* |
| `CHARGE_MAX_DC` | 450 | ... to 45.0 °C. *P* |
| `CHARGE_HYST_DC` | 20 | Hysteresis for resuming after a temperature pause. |
| `CHARGE_PAUSE_LED_MA` | 500 | Charging paused above this LED current. *P* |
| `USB_PROBE_PERIOD_MS` | 10000 | USB re-check period while charging is paused. |
| `USB_PROBE_MS` | 200 | Length of that re-check (CHG_SET floating). |
| `USB_GONE_MS` | 1000 | Both status pins high this long = USB removed. |
| `BATTERY_DISPLAY_MS` | 2000 | Battery colour after switch-on. *P* |
| `LOW_BATTERY_PCT` | 10 | Low-battery blink below this. *P* |
| `SOC_GREEN_ABOVE_PCT` | 50 | Green above this. *P* |
| `SOC_RED_BELOW_PCT` | 20 | Red below this, yellow in between. *P* |
| `MIN_AWAKE_MS` | 1500 | Minimum awake time after boot (wake gesture, sensors). |
| `STUCK_BUTTON_MS` | 10000 | A button held this long while it does nothing counts as stuck. |
| `STUCK_BUTTON_AFTER_WAKE_MS` | 300 | Same after a stuck-button timer wake. |
| `MIN_AWAKE_TIMER_WAKE_MS` | 400 | Minimum awake time after a stuck-button timer wake. |
| `STUCK_RECHECK_MS` | 20000 | Timer wake period while the button is stuck. |

### 6.4 Unchanged from v0.5: hardware conversion (`flashka-core/src/hw.rs`, `rgb.rs`)

| Constant | Value | Meaning |
|---|---|---|
| `LED_FULL_SCALE_MA` | 3235 | LED current at 100 % duty (3.3 V x 2k/102k / 20 mOhm). Calibrate on the bench. |
| `PWM_MAX_COUNTS` | 8191 | Largest 13-bit duty used; `duty = round(I / 3235 x 8191)`. |
| `NTC_SUPPLY_MV` | 3300 | NTC divider supply. |
| `NTC_R_FIXED` / `NTC_R25` | 100 k / 100 k | Divider resistor / NTC at 25 °C. |
| `NTC_BETA` | 4250 | NTC B25/50. |
| `RGB_FULL_R` / `_G` / `_B` | 255 / 70 / 110 | RGB channel duty at full logical brightness (out of 255): v0.5 values (red 1 k); v0.6 red is 330 Ω - retune on the bench. |
| `Rgb::YELLOW`, `CYAN_DIM`, ... | see `rgb.rs` | Logical colours of the patterns. |

### 6.5 Unchanged from v0.5: firmware (`flashka-fw/src`)

| Constant | Value | Meaning |
|---|---|---|
| `CONTROL_PERIOD_MS` (main.rs) | 10 | Control loop / button sampling period. |
| `SENSOR_PERIOD_MS` (main.rs) | 100 | ADC and charger pin sampling period. |
| `WATCHDOG_S` (main.rs) | 3 | Watchdog timeout (> worst-case flash erase). |
| `SLEEP_ADV_QUIET_MS` (main.rs) | 500 | Advertising must be off this long before deep sleep. |
| heap (main.rs) | 64 KiB + 36 KiB | esp-radio heap: `#[ram(reclaimed)]` region (bootloader RAM, 0x3FCCE400) + normal RAM. |
| `PWM_FREQ_HZ` (board.rs) | 9765 | LEDC frequency (13 bit from 80 MHz). |
| esp-radio `Config` (ble.rs) | defaults, 1 connection | BLE TX power is the esp-radio default (+9 dBm). |

---

## 7. Verification status

**Host tests** (`cd firmware/flashka-core && cargo test`): **149 passed, 0 failed** — the 93 v0.5
tests (two adapted to protocol v2, see the report) and 56 new ones: ladder classification incl.
every boundary (105/106, 255/256, 447/448, 810/811 mV) and 1 % / ±10 mV tolerances, slide
clicks / holds (790 ms click, 810 ms hold), ‹ + › 2 s and 10 s, main-button priority, release
transients, boot with a button held; level stepping without wrap, Turbo rules, ignored while off
and in lockout, app-current cancel; presenter entry / exit, all keys in both key sets and
swapped, holds sent once, no keys without a computer, key blip and connect blink, laser in
presenter mode (60 s, too hot, lockout), 4 clicks, idle timeout (30 min, 5 min), battery
refusal and exit, forget from both modes, PRESENTER / FORGET_HOSTS commands and errors, Status v2
bytes, stuck slide button, wake with ‹ + › held; Presenter packet validation and clamping; HID
report map structure, key codes, PnP ID, OOB guard bytes; bond table (replace, evict oldest,
CCCD), bond record round trip and corruption, bond log next to the settings log; settings v1
records still load, v2 record layout.

**Built**: release build without warnings; merged image checked (bootloader magic, partition
table MD5, app descriptor "flashka-fw 0.6.0", nvs region blank). GATT layout and advertising
bytes checked on the host with the same `gatt.rs` (scratch tool, section 3).

**Not verified (no hardware)**: everything in 7.1, in particular the ladder readings, the
deep-sleep wake on GPIO3 after it was an ADC pin, pairing with every OS, bond restore after a
reboot, CCCD restore, the OOB guard on air, presenter-mode current and range.

### 7.1 Bring-up plan (v0.5 plan steps 1-12 still apply; new steps)

13. **Ladder voltages** (DMM on BTN / GPIO3 against GND, USB-powered): none 3.30 V, ● 0 V,
    › 0.300 V, ‹ 0.595 V, ‹ + › 0.212 V (± 10 mV with 1 % parts). Check GPIO9's internal pull-up
    is off after boot: the readings must not shift by more than ~5 mV between boot and run.
14. **ADC readings**: build with `ESP_LOG=debug`, press each button and compare the logged mV
    with the DMM (expect ± 10 mV, thresholds 106 / 256 / 448 / 810 mV). The boot log prints the
    first sample after a wake-up.
15. **Wake-up** from deep sleep with ●, ›, ‹ and ‹ + › (all must wake; GPIO3 is switched from
    ADC back to a digital input before sleep). Hold ‹ + › from sleep: presenter mode after 2 s.
16. **Flashlight mode**: › / ‹ steps (no wrap, Turbo rules), ignored while off and in lockout.
17. **Ring**: all patterns of 2.5; tune `RGB_FULL_*` for the 330 Ω red; brightness through the
    light pipe.
18. **Pairing** on Windows 11, Windows 10 (1803+), macOS, Android, iOS, Linux: pairing without
    a PIN, cyan double blink. Before pairing, nRF Connect on a phone sees the keyboard
    advertising (appearance 0x03C1, UUID 0x1812) and gets 0x05 when it reads the Report Map.
19. **Reconnect**: deep sleep / power cycle (a reboot), enter presenter mode, the computer must
    reconnect without pairing and keys must work at once (CCCD restore). Pair 5 computers: the
    first one must be replaced. Forget (‹ + › 10 s): white x3, no computer reconnects.
20. **Keys and key repeat**: in a text editor / keyboard tester each click gives exactly one
    key; hold › for 3 s: exactly one F5 and no repeated Page Down; same for ‹ (Esc) and ● (B).
    Check PowerPoint, Keynote (arrows), Google Slides, Impress, a PDF viewer.
21. **Presenter current** with and without a connected computer (estimate ~20 mA); idle exit
    after 5 min (app setting) and the following deep sleep current.
22. **Flashlight mode with a paired computer nearby**: the computer reconnects by itself and is
    dropped after 10 s; the app on that computer must keep its link.
23. **Range** with the hand over the bottom face (spec section 7).

---

## 8. Known limitations

* **Hardware untested**: see 7. The ladder thresholds assume the R9/R30/R31 values of spec 3.2.
* From deep sleep, a press that ends before the first ADC sample (~0.2 s boot) counts as a ●
  click, even if it was › or ‹ (the light switches on). Hold › / ‹ a little longer when waking.
* Only LE Secure Connections (trouble-host 0.6): Windows 10 before 1803 and Android before 6
  cannot pair.
* No Service Changed characteristic (trouble-host's GAP/GATT service has none): if a later
  firmware changes the GATT layout, computers must forget FlashKa and pair again. Devices that
  cached the v0.5 layout may need Bluetooth switched off and on once.
* No BLE modem sleep in esp-radio 0.18: presenter mode costs about 20 mA (estimate). The
  firmware does not use light sleep, so GPIO9 is not set up as a light-sleep wake source.
* Plugging USB in resets the MCU (VBUS-edge reset, hardware as v0.5): presenter mode ends and
  has to be entered again (the computer then reconnects by itself).
* While a paired computer holds the link in flashlight mode (up to 10 s at a time, repeated
  while the light advertises), the app on another device cannot connect.
* F5 starts a show only on Windows / Linux programs; Mac programs use other shortcuts.
* PnP ID uses the pid.codes test PID 0x0001 (apply for a PID before distributing).
* The merged image erases settings and paired computers (flash the ELF to keep them).
* As v0.5: the red ring LED flickers at boot (bootloader log on GPIO21); below about -7 °C the
  NTC reads as open.
