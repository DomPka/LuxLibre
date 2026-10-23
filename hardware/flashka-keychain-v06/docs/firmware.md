<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.6 and v0.7 — firmware

Firmware for the FlashKa Keychain v0.6: ESP32-C3-MINI-1-N4, Rust `no_std`, esp-hal 1.1.2 +
esp-rtos 0.3 (embassy) + esp-radio 0.18 (BLE controller) + trouble-host 0.6 (BLE host, with
LE Secure Connections). The Bluetooth protocol is specified in
[`ble_protocol.md`](ble_protocol.md) (version 2); this document describes how the firmware
implements it, how the light behaves, the flash layout, how to rebuild, and every constant you
might want to tune.

v0.6 = v0.5 plus three buttons on one ADC ladder, level stepping with › and ‹, a presenter
mode (the light becomes a Bluetooth keyboard), the RGB ring and protocol version 2.

The same sources also build **firmware 0.7.0 for the FlashKa Keychain v0.7** (1000 lm: stronger
LED driver, SST-20 Gen 2 behind a TIR optic, one 14500 cell) with the Cargo feature `board-v07`. Sections 1 to 8 describe both boards unless they give a v0.6 number;
**section 9** lists everything that is different on the v0.7. The default build is the v0.6
firmware 0.6.0, unchanged byte for byte.

> **Not tested on hardware.** No v0.6 or v0.7 board exists yet. Everything in this document is
> built and host-tested only (sections 7 and 9.8); the v0.7 output, temperature and runtime
> numbers are simulated or estimated and marked so. Items marked **(untested)** depend on the
> real board, the radio or a real computer and must be checked with the bring-up plan (7.1).

| | |
|---|---|
| Firmware version | 0.6.0 for v0.6 boards (`FW_VERSION` in `flashka-core/src/board.rs`, = `firmware/flashka-fw/Cargo.toml`); 0.7.0 for v0.7 boards (section 9) |
| Release image (v0.6) | `firmware/dist/flashka-fw-v0.6.0-merged.bin` (534 736 bytes), write at flash offset **0x0** |
| SHA-256 of the image | `e21058791bab990439835fbd977eecfed385af5837405e36ae923cb6083a8fdd` |
| Release image (v0.7) | `firmware/dist/flashka-fw-v0.7.0-merged.bin` (535 328 bytes), SHA-256 `6554028f31b3e86c958335a1b03b4fd6f2a95000f727d752f4cb891318e79f96` — **v0.7 boards only** |
| Image contents | ESP-IDF 2nd-stage bootloader (from espflash 4.6.0) + partition table + app |
| Logic tests | `cd firmware/flashka-core && cargo test` (153 host tests); `cargo test --features board-v07` (166 + 9 simulation tests) |
| Rebuild | `firmware/build.sh` (v0.6), `BOARD=v07 firmware/build.sh` (v0.7) |

---

## 1. Architecture

### 1.1 Two crates (one Cargo workspace)

```
firmware/
├── flashka-core/     no_std library, no dependencies, tested on the host with `cargo test`
│   └── src/
│       ├── board.rs        the board table: every constant that differs between v0.6 and v0.7 (section 9)
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
│   └── tests/thermal_v07.rs   v0.7: the controller driving a simulated light (section 9.6)
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
├── build.sh          tests + release build + merged image + sizes (reproducible in any folder); BOARD=v06|v07
└── dist/             build outputs: the 0.6.0 image (v0.6) and the 0.7.0 image (v0.7)
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

The numbers in this section are those of the v0.6 board; the v0.7 levels, profiles, cell-current
model and capacity are in section 9.3 and 9.4, its temperature regulation (instead of the linear
dimming described under "Protection") in 9.11.

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

USB-C charging at ~300 mA (nominal; the SoC estimate assumes 280 mA; v0.7: about 500 mA, 9.4)
between 0 °C and 45 °C (resumes 2 °C inside the window after a temperature pause). Charging pauses while the LED runs above 500 mA. Plugging USB in resets
the MCU (VBUS-edge reset), keeps it awake and keeps Bluetooth reachable while connected.
Without firmware (e.g. a completely flat cell) the charger trickles at 10 mA.

#### Battery percentage and runtime

The percentage comes from the LiPo open-circuit curve (4.20 V = 100 % ... 3.30 V = 0 %) with
a load correction of +0.12 V per A of estimated cell current while the LED is on (and -0.12 V/A
of charge current while fast-charging), filtered so that it does not jump (at most 0.5 %/s,
small dead band, and it only moves "backwards" for differences above 3 %). "Charge complete"
reads 100 %. Runtime = 800 mAh x SoC / (estimated LED cell current + 20 mA for the MCU and
radio); the MCU term matters at Moon, where the LED itself draws ~2 mA from the cell. The v0.7
(one 14500 cell) uses that cell's curve, 0.13 V per A and 1400 mAh (9.4).

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
download mode. Write the image of **your board** at offset 0x0 with the web installer (it asks
for the board first and checks the firmware already on the light, `web_apps.md` section 2), or:

```
espflash write-bin 0x0 firmware/dist/flashka-fw-v0.6.0-merged.bin   # FlashKa v0.6
espflash write-bin 0x0 firmware/dist/flashka-fw-v0.7.0-merged.bin   # FlashKa v0.7
espflash monitor            # firmware log over USB-Serial-JTAG
```

Never write one board's image to the other board: the two firmwares set the LED current with
different scales and limits (section 9.2).

Writing the merged image erases the settings **and the paired computers** (the `nvs` region is
0xFF in the image); remove FlashKa on each computer and pair again. To keep both, flash only the
app: `espflash flash --partition-table firmware/partitions.csv firmware/dist/flashka-fw-v0.6.0.elf`
(`flashka-fw-v0.7.0.elf` on a v0.7).

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
firmware/build.sh                 # v0.6: host tests, release build, merged image, sizes, SHA-256
BOARD=v07 firmware/build.sh       # v0.7: the same with the feature board-v07 (firmware 0.7.0)
SKIP_TESTS=1 firmware/build.sh    # without the host tests
```

Environment overrides: `FW_RUST_BIN` (default `/usr/lib/rust-1.91/bin`), `HOST_CARGO`, `ESPFLASH`,
`CARGO_TARGET_RISCV32IMC_UNKNOWN_NONE_ELF_LINKER` (a `rust-lld`). By hand:

```
cd firmware/flashka-core && cargo test                     # and: cargo test --features board-v07
cd firmware/flashka-fw && RUSTC_BOOTSTRAP=1 cargo build --release   # build.sh adds the path remapping
espflash save-image --chip esp32c3 --merge --skip-padding --flash-size 4mb \
    --partition-table firmware/partitions.csv \
    firmware/target/riscv32imc-unknown-none-elf/release/flashka-fw \
    firmware/dist/flashka-fw-v0.6.0-merged.bin
```

The log level is set at build time with `ESP_LOG` (default `info`). Build with
`ESP_LOG=debug` to log every ladder class change with its mV reading (bring-up).

**Memory** (release build, v0.6; the v0.7 build differs by a few hundred bytes, section 9.7):
flash 428 778 bytes of code + constants (app image 469 200 bytes, 11 % of the app partition);
RAM 90 104 bytes static (IRAM code 30 676, data 9 636, bss 49 792 incl. the 36 KiB heap),
230 400 bytes left for the stack, plus the 64 KiB heap in the reclaimed bootloader RAM.

**Reproducible**: the image depends only on the sources and the compiler (rustc 1.91.1), not on
the folder or the machine it is built on. `build.sh` sets `SOURCE_DATE_EPOCH` (app descriptor time
2026-10-17 00:00:00; esp-bootloader-esp-idf 0.5.0 reads it in microseconds) and maps the
machine-specific source paths with `--remap-path-prefix` (this folder becomes `firmware`, the cargo
registry `/cargo/registry/src`, the Rust sysroot `/rust`). The two crates form one Cargo workspace
(`firmware/Cargo.toml`, shared `Cargo.lock` and `target/`), so cargo hashes their paths relative to
it. A clean build in the repository and a clean build of a copy in another folder gave the
identical image (SHA-256 above) and ELF. The v0.7 image builds in its own folder
(`firmware/target/v07/`) with its own date (section 9.7). The CI job *Firmware build* rebuilds
both images on GitHub and compares them with `dist/`.

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
| `THERMAL_DERATE_SPAN_DC` | 150 | Linear derating span above the limit (to Low). *P* (v0.6; the v0.7 regulates instead, 9.11) |
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
| `CELL_CAPACITY_MAH` | 800 | Capacity for the runtime estimate (from `board.rs`; v0.7: 1400). |
| `LOAD_CORR_MV_PER_A` | 120 | SoC load correction (mV per A of cell current; from `board.rs`; v0.7: 130). |
| `MCU_AWAKE_MA` | 20 | MCU + radio current in the runtime estimate. |
| `CHARGE_FAST_MA` | 280 | Charge current (SoC correction while charging; from `board.rs`; v0.7: 475). |
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
| `LED_FULL_SCALE_MA` | 3235 | LED current at 100 % duty (3.3 V x 2k/102k / 20 mOhm). Calibrate on the bench. Now in `board.rs`; v0.7: 3552 (section 9). |
| `PWM_MAX_COUNTS` | 8191 | Largest 13-bit duty used; `duty = round(I / 3235 x 8191)` (v0.7: / 3552, at most 3000 mA). |
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

**Host tests** (`cd firmware/flashka-core && cargo test`): **153 passed, 0 failed** — the 149 of
firmware 0.6.0 and 4 added with the v0.7 variant (board table, version texts, the LED ceiling for
every possible request in `hw.rs` and in the controller); with `--features board-v07` the same
tests with the v0.7 values (the linear-derating test replaced by one for the regulator) plus 13 unit
tests and 9 simulation tests (section 9.8). The 149 are the
93 v0.5 tests (two adapted to protocol v2, see the report) and 56 new ones: ladder classification incl.
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

---

## 9. FlashKa Keychain v0.7 (firmware 0.7.0)

The v0.7 board ([hardware/flashka-keychain-v07/](../../flashka-keychain-v07/README.md)) runs this
firmware built for its electronics: `BOARD=v07 firmware/build.sh` (Cargo feature `board-v07`)
gives **firmware 0.7.0**. Everything in sections 1 to 8 applies, except what this section lists.
**Nothing has been built in hardware yet: the lumens, temperatures and runtimes here are estimates
or simulations, marked as such.**

| | |
|---|---|
| Firmware version | 0.7.0 (`FW_VERSION` in `flashka-core/src/board.rs`; Info characteristic `"FlashKa fw 0.7.0"`, PnP version 0x0070) |
| Release image | `firmware/dist/flashka-fw-v0.7.0-merged.bin` (535 328 bytes), write at flash offset **0x0**, **v0.7 boards only** |
| SHA-256 of the image | `6554028f31b3e86c958335a1b03b4fd6f2a95000f727d752f4cb891318e79f96` |
| ELF | `firmware/dist/flashka-fw-v0.7.0.elf` (932 772 bytes), SHA-256 `b9026e430434cd7c48bba9d0ee65f44011a53ae0cc3da303b9492f96ba3a8a47` |
| Logic tests | `cd firmware/flashka-core && cargo test --features board-v07` (166 unit tests + 9 simulation tests) |
| Rebuild | `BOARD=v07 firmware/build.sh` |

### 9.1 What is different on the v0.7 board

| | v0.6 | v0.7 |
|---|---|---|
| LED | Luminus SST-20 on a 10 mm copper board | Luminus SST-20 Gen 2, 6500 K, G1 bin, on a 10 mm copper board behind a LEDiL LISA3-RS-PIN TIR optic (87 %); **3.0 A DC maximum** (datasheet) |
| Driver | TLV62585 buck in the TLV333 current loop; VSET 2.0 k / 100 k: 3235 mA at 100 % duty | TPS62095 4 A buck (100 % duty mode) in the same loop; VSET 2.2 k / 100 k: **3552 mA** at 100 % duty, ±3 % (RSS) and ±5 % (worst case) |
| Cells | 2 × LP601646, about 800 mAh, with protection boards | **one Vapcell INR14500 F15**: 1500 mAh typical / 1150 mAh minimum (0.2C), 3.60 V nominal, **3 A** maximum continuous, about 60 mΩ AC; nickel strips welded to both ends; protected on the main board: DW01A + SE8830A (Kelvin-sensed), trip 5.3-5.6 A typical at 25 °C, 4.3-4.5 A hot, as low as **3.0-3.15 A** in the worst case; a trip latches until USB power is plugged in (9.4) |
| Cell path | about 0.12 Ω | about 0.13 Ω: the F15's DC resistance about 90 mΩ (estimated as 1.5 × its AC value, not measured), strips and wires about 10 mΩ, protection MOSFETs 28 mΩ, copper about 4 mΩ |
| Charger | TP4057, about 280 mA (R3 3.3 k) | TP4057, **494 mA** (R3 2.0 k; the F15's standard charge is 500 mA) |
| Body | 94.4 × 20 × 16 mm | octagonal (eight flat facets), 99.2 × 20 × 18 mm; one 14500 cell in the bay |
| MCU, pins, buttons, ring, laser, NTC | | unchanged (no GPIO change); the three keys sit on a key board in the middle of the body |

### 9.2 One code base, two boards

* **Selection at compile time:** Cargo feature `board-v07` of `flashka-core`; `flashka-fw` has a
  feature of the same name that switches it on. No feature = the v0.6 board. `build.sh` takes
  `BOARD=v06` (default) or `BOARD=v07` and builds each board in its own target folder.
* **One table:** every board-dependent constant is in `flashka-core/src/board.rs`: firmware
  version, Info text, PnP version, LED full scale, LED ceiling, highest turbo, cell capacity, load
  correction, charge current, LED forward-voltage model, driver efficiency, the driver's headroom
  (v0.7), LED flux table and optic factor. The built-in profiles (`profile.rs`), the cell-current
  formula and the open-circuit voltage curve (`battery.rs`) have one version per board.
  `flashka-fw` takes the version and its app descriptor from `board.rs`. The v0.7 build also has
  `thermal.rs`, the temperature regulator (9.11), in place of the protocol's linear derating.
* **The LED ceiling, in one place:** `hw::led_duty_counts()` is the only function that turns a
  current into PWM counts, and it limits every request to `LED_MAX_MA`, **3000 mA** on the v0.7
  (6918 of the 8192 PWM counts = 2999.6 mA; v0.6: the full scale, as before). No level, profile,
  Custom value, `OUTPUT_MA`, protection result or bug elsewhere can ask the driver for more. A host
  test tries every possible u16 request; another drives the controller with random sequences of
  levels, profiles, Custom writes (also out of range) and exact currents and watches the output.
* **Below the ceiling:** the highest current any level can request is `TURBO_MAX_MA`, **2850 mA**
  (the Custom profile's "turbo max", the built-in turbos). The build fails (compile-time checks in
  `board.rs`) if the ceiling is above 3000 mA or above the full scale, if `TURBO_MAX_MA` plus the 5 %
  worst-case tolerance is above 3000 mA, if `TURBO_MAX_MA` is above the ceiling or does not match the
  protocol limit, or if a built-in level is above `TURBO_MAX_MA`.
* **v0.6 unchanged:** without the feature every constant has its 0.6.0 value; the sources rebuild
  the published 0.6.0 image and ELF byte for byte (9.7).

### 9.3 Levels and profiles (v0.7)

| | Extreme | Balanced (default) | Endurance | Custom |
|---|---|---|---|---|
| Moon / Low / Medium / High | 3 / 50 / 400 / 1800 mA | 3 / 40 / 250 / 1530 mA | 2 / 15 / 100 / 500 mA | set by the app, default = Balanced |
| out of the front (estimate) | 1 / 24 / 187 / 683 lm | 1 / 19 / 119 / 601 lm | 1 / 7 / 48 / 230 lm | |
| Turbo | 2850 mA (966 lm) for 60 s | 2850 mA (966 lm) for 60 s | none (turbo = High) | at most 2850 mA |
| After the turbo time | 1800 mA | 1530 mA | — | |
| Temperature limit (held, 9.11) | 50 °C | 50 °C | 47 °C | 40-70 °C |
| Low-voltage step-down (under load) | 3.15 V | 3.20 V | 3.25 V | 3.10-3.60 V |
| Cell current limit | 2800 mA | 2800 mA | 800 mA | 200-3000 mA |
| Flags | turbo, remember, battery display | turbo, remember, battery display | remember, battery display | |

Lumens "out of the front" = the LED model of 9.5 (junction at 85 °C) × the optic's 87 %. They are
estimates; the control app shows the same numbers on a v0.7.

### 9.4 Why these numbers

* **Turbo 2850 mA (966 lm), not 3000 mA.** The LED is rated 3.0 A DC. The full scale of the current
  loop is ±3 % (RSS) and ±5 % in the worst case (3.3 V rail, divider, sense resistor), so a
  3000 mA set point could become 3.15 A on a real board. 2850 mA × 1.05 = 2993 mA: within the
  rating even in the worst corner. The cost is 40 lm (966 instead of 1006 lm out of the front,
  -4 %, a difference the eye cannot see). From a full F15 turbo draws about 2.7 A; the 2800 mA cell
  limit cuts in below about 3.78 V under load (about 4.14 V at rest, 96 % charge), and below about
  3.7 V at the pads the buck runs at 100 % duty and the cell's own sag decides (below about 3.97 V
  at rest, 82 %): **turbo dims as the cell empties** (simulated, 9.6: 966 lm from a full cell,
  948 lm at 90 %, 916 lm at 75 %, 775 lm at 50 %, 651 lm at 25 %). The owner's target
  of about 1000 lm out of the front is met within the accuracy of the LED model: 966 lm is the
  value at the rating temperature (Tj 85 °C); with a cool LED in the first seconds the datasheet's
  temperature curve gives about 10 % more (estimate).
* **High 1530 mA (601 lm).** About 600 lm out of the front needs about 690 lm at the LED; the
  datasheet gives 680 lm at 1.5 A (G1 bin minimum, Tj 85 °C), so High is 1530 mA, not the 1.7 A of
  the first estimate (1.7 A would be about 653 lm). It is held until the temperature regulation
  takes over: about 210 s from cold in 25 °C still air (9.6); the F15 gives it in full down to about
  15 % charge (Extreme's 1800 mA down to about 30 %).
* **Moon 3 mA,** as on the v0.6: 7 PWM counts at the 3552 mA scale (1 count = 0.43 mA). The op-amp's
  offset makes it ±3 % typical, ±25 % worst case.
* **Low and Medium** split the range in even steps for the eye, about × 5-6 per step in light
  (Balanced: 1, 19, 119, 601, 966 lm). Extreme moves Low, Medium and High up (24, 187, 683 lm).
  Endurance keeps the v0.6 low levels and a High of 500 mA (230 lm) that the body sheds in still
  air at 25 °C without stepping down.
* **Cell current limit 2800 mA** in Extreme and Balanced (Endurance 800 mA; the Custom profile
  accepts 200-3000 mA, as in the protocol). The F15 is rated 3 A continuous: 2800 mA is 93 % of
  that, above the 70 % of LuxLibre BAT-1 (2100 mA). This is a **documented BAT-1 deviation**: only
  turbo comes near it, and turbo lasts at most 60 s and is thermally regulated (High draws
  1.3-1.7 A, the sustained level about 0.6 A, both within BAT-1). No independent test of the F15 at
  3 A was found. The firmware estimates the battery current as
  `V_LED(I) · I / (0.87 · V_BAT)` with `V_LED = 2.80 V + 0.15 V/A · I` (there is no current
  sensing) and lowers the LED current to keep the estimate at or below the limit. The board
  protection (DW01A + SE8830A, Kelvin-sensed; electronics "power" block) trips at 5.3-5.6 A typical
  at 25 °C and 4.3-4.5 A with hot MOSFETs, but in the worst case (DW01A at its 120 mV minimum, both
  MOSFETs at their maximum resistance and hot, cell at 3.7-3.8 V) already at 3.0-3.15 A. 2800 mA
  keeps 7-12 % from that (5-10 % if the real efficiency is 85 %); the earlier 3000 mA kept 0-5 %.
  Against the F15 the protection is a fault and short-circuit guard, not the 3 A limit.
  **What a trip looks like:** 10-20 ms above the trip current the protection cuts the cell off:
  the whole light goes dark at once (LED, ring, Bluetooth) and no key does anything; switching off
  and on does not help. The DW01A latches (the light's own load holds it off), so the light stays
  off until USB power is plugged in; then it works again, also after unplugging. Nothing is damaged.
  If the protection ever trips in turbo, use the Custom profile with a cell limit of **2500 mA**.
  For full turbo to a lower charge the bay also takes a high-drain 14500 such as the Vapcell K10
  (1000 mAh, 8 A; not simulated): shorter runtime, and the cell limit can stay.
* **Turbo timer 60 s** in both turbo profiles. In 25 °C still air the regulator takes over at 57 s,
  the timer ends turbo at 60 s (9.6).
* **Temperature limit 50 °C, held by a regulator** (9.11). The NTC sits on the main board near
  the driver and follows the head. The protocol's linear law (dimming from the limit to Low over
  15 °C) settles about 9 °C above the limit, so with it the limits had to be 40-41 °C and High
  started dimming after 83 s while the body was still at 33 °C (simulated, earlier body). On the
  v0.7 the limit is the set point instead: the light holds the sensor 0.1-0.3 °C below it, and
  50 °C there keeps the simulated body (the surface held in the hand) at or below 46.5 °C in 25 °C
  still air and the head below 51 °C on the way, inside LuxLibre's touch limits
  ([THM-1](../../../docs/design-rules.md#thm-1): 48 °C continuous, 51 °C at any time). Extreme and
  Balanced both use 50 °C (the regulator holds it whatever the level); Endurance 47 °C, which its
  500 mA High does not reach at 25 °C (the sensor settles at about 45.2 °C with the MCU's and the
  cell's own heat).
* **Battery: one F15.** Capacity for the percentage and runtime estimates **1400 mAh**: the maker
  gives 1500 mAh typical and 1150 mAh minimum, both at 0.2C to 2.5 V; this light draws 0.4-1.9 A
  and stops at 3.0 V under load, which costs a typical cell about 7 % (estimate). A cell at the
  maker's minimum runs about 18 % shorter than the runtime shown. **Load correction 130 mV/A**
  (the cell path above; the DC resistance is an estimate from the AC value). **Percentage:** the
  F15's open-circuit voltage is lower than a LiPo's over most of the charge; no F15 curve is
  published, so the v0.7 uses a generic curve of a 3.6 V-nominal NMC cell (4.20 / 4.05 / 3.95 /
  3.86 / 3.77 / 3.68 V at 100 / 90 / 80 / 70 / 60 / 50 %, 3.47 V at 20 %, 3.25 V at 5 %, 3.00 V
  empty; `battery.rs`): an estimate within about ±5 %. In turbo from a part-empty cell the buck can
  give less than asked; the percentage, the runtime and the Status packet's LED current use the
  current it can deliver, `(V_BAT - 2.80 V) / 0.278 Ω` (`board::DROP_PATH_MOHM`), and the
  percentage uses the LED current through the same filter as the voltage, so it does not jump when
  the level changes. **Low-voltage step-down 3.15 / 3.20 / 3.25 V under load** (Extreme / Balanced
  / Endurance; was 3.30 / 3.35 / 3.40 V): with the F15's curve and one cell's sag the old values cut
  in with 10-30 % still in the cell, the new ones at about 5-11 % (from the sustained level to a
  full High). Moon below 3.10 V and off below
  3.00 V stay (protocol); the F15 may go to 2.5 V, the DW01A's own cut-off is 2.3-2.5 V.
  **Charging:** 494 mA (R3 2.0 k), so the percentage correction while charging uses 475 mA (less
  about 20 mA for the MCU); a full charge takes about 3.5 h. With a nearly empty cell the charger,
  2.5 mm from the NTC, warms the board; above 45 °C the firmware pauses charging and resumes at
  43 °C (as on the v0.6): normal, not a fault.
* **LuxLibre rule LED-2** (a "Should": at most 80 % of the LED's maximum current) is not met:
  2850 mA is 95 % of 3.0 A. The 1000 lm target needs it; turbo is timed (60 s) and regulated (the
  regulator starts after about 57 s from cold), so the LED spends little time there.

### 9.5 LED model

| LED current, mA | 350 | 700 | 1000 | 1500 | 2000 | 2850 | 3000 |
|---|---|---|---|---|---|---|---|
| At the LED, lm (Tj 85 °C) | 191 | 361 | 485 | **680** | 855 | 1111 | **1156** |
| Out of the front, lm (× 0.87) | 166 | 314 | 422 | 592 | 744 | 966 | 1006 |

Bold: datasheet values (Luminus SST-20-WS Gen 2, 6500 K: G1 bin minimum at 1.5 A, and 3.0 A).
The other points are **estimates** from the relative-flux curves of the SST-20 datasheets
(SST-20-WE: 0.71 at 1.0 A and 1.26 at 2.0 A; SST-20-W Gen 1: 0.28 at 0.35 A and 0.53 at 0.7 A, all
relative to 1.5 A), with straight lines in between and to zero below 350 mA. `board::front_lumens()`
computes it with integers; the control app uses the same table and arithmetic (a web unit test
compares them), and so does the LuxLibre board header `flashka-keychain-v07`.

### 9.6 Simulated behaviour (25 °C still air)

The firmware's own controller (`flashka-core`) drives a simulated light in
`flashka-core/tests/thermal_v07.rs`. **Thermal model:** three nodes, with masses and areas from the
CAD of the octagonal body: the head (LED, driver and sensor) 7.06 J/K (7.4 g of aluminium and the
LED board's copper), the body (the surface you touch) 21.07 J/K (23.5 g of aluminium), head to
body 2.2 K/W (87.75 mm along about 80 mm² of metal), body to air 13.2 K/W (68.9 cm² of
aluminium at 11 W/m²K; the texture's extra area is not counted), sensor lag 4 s; and the cell,
22 J/K (22 g × about 1 J/gK), coupled weakly to the body: about 8 K/W through the two line
contacts along the rails (polyimide tape), the air gaps and the foam strip (an estimate; with 4
or 16 K/W High's full output lasts 234 or 189 s, and the current settles at the same level). The
driver's losses, the part of the LED power that does not leave as light (70 %) and the MCU
(20 mA) heat the head; the cell heats itself with I² × 0.10 Ω.
**Electrical model:** one F15, 1500 mAh, the curve of 9.4, 0.10 Ω from the cell to the J2 pads
and 0.132 Ω to the battery ADC; at 100 % duty the buck gives the LED at most
(V_pads - 2.80 V) / 0.31 Ω (electronics "power" block). The light lies alone in still air with a
full cell; there is no "held in the hand" case. The PCB, keys and optic do not store heat in the
model, so the times are on the short side. **Simulated, not measured.**

| Run | Full output | Then | Sustained | Body (touch) | Runtime, F15 |
|---|---|---|---|---|---|
| Balanced, turbo 2850 mA (966 lm) | 58 s | regulated from 57 s (2731 mA at 59 s); at 60 s the timer ends turbo: High 1530 mA (601 lm; 1447 mA for 3 s right after the turbo) until about 2 min, then 462 lm at 3 min, 379 lm at 5 min, 308 lm at 10 min | 620 mA = **280 lm** at 20 min, 611 mA = 276 lm from 30 min | at most 46.4 °C, steady after about 10 min | 137 min to 10 % of the 30 s output (ANSI FL 1 style; here the low-voltage step-down to Low); off after 235 min |
| Balanced, High 1530 mA (601 lm) | 210 s | regulated: 464 lm at 4 min, 414 lm at 5 min, 314 lm at 10 min | 282 lm at 20 min, 276 lm from 30 min | at most 46.5 °C | 138 min; off after 236 min |
| Extreme, turbo 2850 mA | 58 s | timer at 60 s: 1800 mA (683 lm; 1703 mA for 3 s right after the turbo) until about 1.6 min, then regulated | 281 lm, 276 lm from 30 min | at most 46.5 °C | 139 min; off after 201 min |
| Extreme, High 1800 mA (683 lm) | 149 s | regulated | 281 lm, 276 lm from 30 min | at most 46.4 °C | 140 min; off after 201 min |
| Endurance, High 500 mA (230 lm) | 178 min (no thermal step-down) | low-voltage step-down to Medium (100 mA, 48 lm) at 178 min | 230 lm | 42.4 °C | 193 min; off after 303 min |
| Balanced, turbo from a **half-full cell** (50 %) | never: 2139 mA = **780 lm** at switch-on, 775 lm at 30 s, 770 lm at 59 s | at 60 s High 1530 mA (601 lm) until about 3 min, then regulated | 282 lm, 276 lm at 30 min | at most 46.4 °C | (starts at 50 %) |

**Turbo and the state of charge** (simulated, `balanced_turbo_from_a_half_full_cell`): under
2.7 A the F15 sags, and below about 3.7 V at the pads the buck runs at 100 % duty, so the LED gets
what the cell can push through it. The whole 2850 mA needs about 4.14 V at rest (96 % charge: the
cell limit); the buck alone would hold it down to about 3.97 V (82 %; the electronics estimate was
3.95-4.0 V). 30 s after switching on, turbo gives 966 lm from a full cell, 948 lm at 90 % (2780 mA:
the 2800 mA cell limit), 916 lm at 75 % (2658 mA), **775 lm at 50 % (2119 mA, -20 %)** and 651 lm
at 25 % (1696 mA). High (1530 mA) comes in full down to about 15 %,
and the regulated level of about 280 lm down to the low-voltage step-down. The app shows the
current the LED really gets (9.4). A high-drain 14500 such as the Vapcell K10 would keep the turbo
down to a lower charge (not simulated).

The sensor peaks at 50.5 °C (Balanced) to 50.6 °C (Extreme), the head at 50.5-50.6 °C, then the
sensor settles within the band, 49.7-50.0 °C; the cell warms to at most 46.7 °C and gives at most
2.74 A (turbo, full cell; 2.16 A from a half-full cell). Once settled the current changes by at
most 1 mA per second. The LuxLibre firmware on the same model (board header
`flashka-keychain-v07`, its regulator at `THM_LIMIT` 50 °C; two nodes, without the cell node)
holds turbo 56 s and its High (level 138: 1501 mA, 592 lm) 185 s, with its sensor peaking at
51.0 °C, then 289-304 lm. With the LED's temperature curve (a cool LED gives more light) the
comparison script `hardware/flashka-keychain-v07/tools/compare/` puts the turbo at about 1045 lm out
of the front at switch-on and 1019 lm at 30 s (estimates).

**Step response** (simulated, `regulator_step_response_to_the_air_temperature`): with High
regulated in 25 °C air, the air steps to 30 °C. The current falls from 618 to 490 mA without
undershoot, the sensor peaks at 50.11 °C and is back at or below 49.9 °C after 2.8 min. Then the
air steps to 20 °C: the current rises to 729 mA without overshoot and the sensor stays below the
limit (at most 49.86 °C). No oscillation; the current changes by at most 0.2 % per update. At
30 °C air the body settles at about 47 °C (47.05 °C with the sensor at 49.86 °C): the regulator
holds the sensor, not the body (9.10).

**Noisy sensor** (simulated, `regulator_is_steady_with_a_noisy_sensor`): with a pseudo-random
-3 to +3 mV on the NTC voltage at every sample (about ±0.12 °C at 50 °C) High still runs 210 s at
full output and settles without hunting: from 30 to 45 min the current stays at 615-617 mA
(278 lm). Without the gap of the proportional part (9.11) the same run wanders between 603 and
618 mA.

`FLASHKA_SIM_CSV=<folder> cargo test --features board-v07 --test thermal_v07` writes the time
series (1 s rows) of these runs, of the step response and of the noisy-sensor run.

### 9.7 Image and reproducible build

`BOARD=v07 firmware/build.sh` builds in `firmware/target/v07/` with `SOURCE_DATE_EPOCH`
2026-10-22 00:00:00 UTC (the v0.6 image keeps `firmware/target/` and 2026-10-17, so building one
board never reuses the other's compiled date) and the same path remapping as for 0.6.0. The app
descriptor reads "flashka-fw 0.7.0"; build.sh checks it.

| | v0.7 (0.7.0) |
|---|---|
| Merged image | 535 328 bytes, SHA-256 `6554028f31b3e86c958335a1b03b4fd6f2a95000f727d752f4cb891318e79f96` |
| ELF | 932 772 bytes, SHA-256 `b9026e430434cd7c48bba9d0ee65f44011a53ae0cc3da303b9492f96ba3a8a47` |
| App image | 469 792 bytes (11 % of the app partition) |
| Flash, code + constants | 429 348 bytes |
| RAM, static | 90 136 bytes (IRAM code 30 676, data 9 668, bss 49 792); 230 368 bytes left for the stack |

Check: two copies of the firmware folder (without `dist/`) in two different folders, each built
for both boards (v0.6 then v0.7 in one, v0.7 then v0.6 in the other), gave identical v0.7 images and
ELFs, and both reproduced the published 0.6.0 image and ELF byte for byte. rustc 1.91.1, espflash
4.6.0.

### 9.8 Tests (v0.7)

`cargo test --features board-v07`: **166 unit tests and 9 simulation tests, all passed.** Every
test of the default build runs with the v0.7 values (built-in profiles, duty counts, cell-current
formula, open-circuit voltage curve, load correction, runtime, low-voltage thresholds, battery
limits); the protocol's linear-derating test is replaced by one for the regulator (held within the
band, falls to Low when too hot, never below, Moon and off as before). Added: the LED ceiling for
every u16 request and through the controller (also in the default build), the board table and
version texts, the LED model's datasheet anchors and shape, the lumens of every v0.7 level, the
battery limits of the F15 (no level the cell or the protection cannot carry: the estimated cell
current within the cell limit, at least 7 % below the protection's worst-case trip and the F15's
3 A; every level but turbo within LuxLibre BAT-1, 2100 mA, down to the step-down voltage;
1400 mAh and 130 mV/A), the current the buck can deliver at 100 % duty and the percentage during a
dimmed turbo, nine unit tests of the regulator (band, floor, backstop, set point clamp, no wind-up,
prediction, no dip after a lower request, a reading flicking at the edge of the band, sensor
faults), and the nine simulation runs of 9.6: turbo at 2850 mA for at least 35 s and High for at
least 150 s from cold, the body at or below 47 °C at every moment, head and sensor at or below
51 °C and, once settled, 50 °C, 270 lm or more sustained, at most 2 % change per update and no
oscillation, never more than 2850 mA, the Custom maximum clamped, the step response, the noisy
sensor and turbo from a half-full cell (it dims but stays above High, the cell at or below 2.8 A,
the Status packet reports the current the LED gets).

### 9.9 Bring-up additions for the v0.7

24. **Full scale.** Set 250, 1530 and 2850 mA (`OUTPUT_MA` from the app) and measure the LED current
    (shunt in series, or the voltage across RS1: 57 mV at 2850 mA). Calibrate
    `LED_FULL_SCALE_MA = 3552 × measured / set` if it is off by more than 2 %; the turbo must be at
    or below 3.00 A.
25. **Turbo by charge.** Turbo from a full F15 and from a half-full one (about 3.7 V at rest):
    measure the LED current (simulated 2850 mA and about 2.1 A, 9.6) and compare the app's reading.
    If they differ, correct `board::DROP_PATH_MOHM` (the driver's headroom seen from the battery
    ADC: 0.278 Ω in all with the LED's 0.15 Ω).
26. **Cell current and resistance.** Measure the battery current at turbo at 4.2, 3.8 and 3.6 V
    (supply in place of the cell, shunt in BAT-), also right after 60 s of turbo (hot MOSFETs).
    Expected 2.5-2.8 A; the protection must not trip. If the measurement is higher than the
    estimate, lower the cell limit. Then measure the trip current itself, hot: raise the load on a
    current-limited supply until the DW01A cuts (expected above 3.0 A; plug in USB to wake the board
    again). With an F15: its voltage at rest and in High and turbo at the ADC (app) gives the DC
    resistance of the cell path, estimated 0.13 Ω; correct `LOAD_CORR_MV_PER_A` if it differs.
27. **Temperatures** (LuxLibre THM-4 / THM-6): thermocouples on the head and on the body where it
    is held, the NTC reading in the app; turbo and High from cold in 25 °C still air. The body must
    stay at or below 48 °C; compare with 9.6. If the NTC does not follow the head as assumed, lower
    the limit or lengthen the regulator's prediction (`LEAD_S`, 9.11) and check that the current
    settles without hunting (the app shows it).
28. **Moonlight** 3 mA: visible and steady (op-amp offset up to ±25 %).
29. **Output and runtime** with a lumen tube ([docs/testing.md](../../../docs/testing.md)):
    turbo at 30 s and High against 966 / 601 lm, runtime at High against about 138 min (to the
    ANSI end point; a cell at the maker's 1150 mAh minimum gives about 18 % less).
30. **Charging** from a nearly empty F15: charge current (about 490 mA, R3 2.0 k), the percentage
    while charging, the NTC reading and the pauses above 45 °C; a full charge in about 3.5 h.

### 9.10 Open points (v0.7)

* Hardware untested: every number above is a datasheet value, an estimate or a simulation.
* The temperature limits assume that the NTC (on the main board, about 12 mm behind the head
  block) follows the head; check it on the bench (9.9, step 27).
* Full-scale tolerance: the 3.0 A guarantee assumes at most +5 %; calibrate (step 24).
* **The F15:** no independent test of the F15 at 3 A was found; its DC resistance (about 90 mΩ) is
  estimated from the maker's 60 mΩ AC value, and no discharge curve is published. The load
  correction, the percentage (a generic curve, about ±5 %), the low-voltage thresholds and the
  dimming of turbo by charge (9.6) are estimates; check them (steps 25, 26, 29).
* Capacity: the estimates use 1400 mAh; a cell at the maker's minimum (1150 mAh) runs about 18 %
  shorter than shown.
* **Cell limit 2800 mA = 93 % of the F15's 3 A, a LuxLibre BAT-1 deviation** (9.4). The estimate
  assumes 87 % from the cell to the LED; at 85 % the real current at the limit would be 2.87 A,
  still below 3 A and the protection's worst-case trip of 3.0-3.15 A, but measure it (step 26).
* Buck dropout: modelled from the electronics estimate (0.31 Ω from the J2 pads to the LED at
  100 % duty); the turbo from a part-empty cell depends on it and on the cell (step 25).
* LED-2 deviation (95 % of the LED maximum), documented in 9.4.
* The sustained level is 276-282 lm (294 lm in the earlier simulation of the rectangular body,
  which left out the MCU's and the cells' heat); the simulation test accepts 270 lm or more.
* The regulator holds the sensor, not the body: in warmer air the body runs closer to the sensor
  (simulated: 47.1 °C at 30 °C air, 47.8 °C at 35 °C; above about 36.5 °C air the body would pass
  48 °C at the 50 °C limit). Lower the Custom limit for hot days, or measure and add an air term.
* The regulator's gains were tuned on the simulation model; a real NTC with noise, another lag or
  another coupling to the head can need other values (9.9, step 27). In the design check of 9.11
  the head peaks at 50.5-50.95 °C in turbo with a sensor lag of 2 or 8 s, the head's heat capacity
  halved or doubled, twice the body's heat capacity, 30 % less resistance to the air, 15 °C air or
  the cell coupled by 4 or 16 K/W; it passes 51 °C with the head-to-body resistance doubled
  (51.2 °C; turbo then lasts 33 s, the sustained level is 249 lm) and in 35 °C air (51.3 °C); with
  the head-to-body resistance halved the body settles at 48.1 °C.
* The lumens below 1.5 A are estimates (no SST-20 Gen 2 curve at those currents was available).

### 9.11 Thermal regulator (v0.7)

The v0.6 keeps the protocol's linear derating (section 2.6). On the v0.7 the profile's temperature
limit is the set point of a regulator (`flashka-core/src/thermal.rs`, built only with
`board-v07`), fed by every temperature sample (100 ms) and applied in the same place as the old law
(Moon above 70 °C and off above 80 °C stay):

```text
T      = sensor temperature through one more filter (1/16 per sample, about 1.6 s)
rate   = its rate of rise (filtered, 1/32 per sample, about 3.2 s), less 0.03 degC/s; cooling = 0
T_pred = T + rate x 8 s                     (the sensor lags the head by about 4 s)
aim    = limit - 0.1 degC                   (the reading has a resolution of 0.1 degC)
e      = T_pred - aim, or 0 while T_pred is within 0.2 degC below the aim
e'     = e less 0.1 degC on either side (one step of the reading), or 0
I      = I - KI' x e x 0.1 s                KI = 24 mA/(degC s), smaller below 0.5 degC of error
cap    = I - 300 mA/degC x e'               both between Low and the requested current
```

* **Full output until it is needed:** while the predicted temperature is below the aim the cap is
  the request, so turbo and High run at their full current until the temperature, 8 s ahead, gets
  to the limit. The prediction (and the filters) are why the cut starts early enough that the head
  stays below 51 °C after it.
* **No wind-up, no deep dips:** the integrator stays between Low and the request; while it is too
  hot it may sit above the request by the proportional part, so the end of turbo goes to High at
  once instead of dipping far below it first. While the temperature is still rising after the
  turbo the cap stays a few per cent below High for a few seconds (simulated: 1447 mA, -5 %, for
  3 s). Requests at or below Low are never reduced; more than 5 °C
  above the limit the cap is Low at once (backstop); limits above 65 °C act as 65 °C.
* **Stability:** linearised with the thermal model of 9.6 (head 7.06 J/K, body 21.07 J/K, cell
  22 J/K at 8 K/W, 2.2 and 13.2 K/W, sensor lag 4 s; the sampling, both filters and one sample of
  delay included, the full integral gain), the loop crosses over at 0.16-0.20 rad/s (a period of
  31-39 s) for 0.62-2.85 A while the prediction acts, at 0.10-0.12 rad/s once settled (the rate
  below 0.03 °C/s): faster than the light as a whole (about 750 s), slower than the head (about
  16 s) and the sensor. The phase margin is at least 57 degrees with the prediction and 43 degrees
  without it, the gain margin at least 10 and 12.8 dB; with the sensor lag doubled to 8 s or the
  head-to-body resistance doubled at least 46 / 29 degrees and 9.1 / 10.9 dB, with the head's heat
  capacity halved 33 / 44 degrees and 5.7 / 9.8 dB. The cell's coupling (4-16 K/W) does not change
  them. Near the aim the integral gain is smaller still.
* **No hunting on the steps of the reading:** within the band neither term acts, and the
  proportional part starts one step of the reading (0.1 °C) beyond it. A reading that flicks
  between two values at the edge of the band (the 0.1 °C resolution, or noise) then moves only the
  slow integral part, by a fraction of a mA per sample, instead of the current in steps of
  300 mA/°C x 0.1 °C = 30 mA. In the simulation the settled current does not change, also with
  ±3 mV of noise on the NTC voltage (9.6). With a sensor lag of 2 or 8 s, the head's heat capacity
  or the head-to-body resistance halved or doubled, twice the body's heat capacity, 30 % less
  resistance to the air, 15 or 35 °C air, or the cell coupled by 4 or 16 K/W, the current still
  settles without hunting: it falls steadily and does not turn back once (design check on the same
  model, not a test; the peaks of those cases are in 9.10).
* **Step response:** 9.6 (a 5 °C warmer and a 10 °C cooler air step while regulating): no
  oscillation, no undershoot or overshoot of the current, the sensor at most 0.11 °C above the
  limit.
* **Protocol and app:** the same packets and range (40-70 °C); `ble_protocol.md` section 9
  describes the rule; the control app (0.7.0) and its demo light follow it on a v0.7 and keep the
  linear law for a v0.6.
