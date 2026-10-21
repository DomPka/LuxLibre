# Aurora++ v0.5 — firmware

Firmware for the Aurora++ v0.5 keychain flashlight: ESP32-C3-MINI-1-N4, Rust `no_std`,
esp-hal 1.1.2 + esp-rtos 0.3 (embassy) + esp-radio 0.18 (BLE controller) + trouble-host 0.6
(BLE host). The Bluetooth protocol is specified in [`ble_protocol.md`](ble_protocol.md); this
document describes how the firmware implements it, how the light behaves, the flash layout,
how to rebuild, and every constant you might want to tune.

| | |
|---|---|
| Firmware version | 0.5.0 (`firmware/aurora-fw/Cargo.toml`) |
| Release image | `firmware/dist/aurora-fw-v0.5.0-merged.bin`, write at flash offset **0x0** |
| Image contents | ESP-IDF 2nd-stage bootloader (from espflash 4.6.0) + partition table + app |
| Logic tests | `cd firmware/aurora-core && cargo test` (93 host tests) |
| Rebuild | `firmware/build.sh` |

---

## 1. Architecture

### 1.1 Two crates

```
firmware/
├── aurora-core/      no_std library, no dependencies, tested on the host with `cargo test`
│   └── src/
│       ├── controller.rs   the state machine of the light (uses everything below)
│       ├── gesture.rs      debouncer + click / hold gesture parser
│       ├── profile.rs      levels, built-in profiles, Custom clamping, 20-byte Profile packet
│       ├── protocol.rs     Status / Command packets, error codes, UUIDs
│       ├── protection.rs   thermal derating, low-voltage state machine, laser rules
│       ├── battery.rs      OCV curve, load correction, SoC filter, cell current, runtime
│       ├── charger.rs      TP4057 control on GPIO20, USB detection
│       ├── rgb.rs          RGB status patterns and priorities
│       ├── settings.rs     64-byte settings record (magic/version/CRC) and flash log
│       ├── hw.rs           mA <-> PWM duty, ADC -> VBAT, NTC -> temperature
│       ├── mathx.rs        ln() for the NTC (no libm on the target)
│       └── config.rs       all tunable constants (table in section 6)
├── aurora-fw/        the ESP32-C3 binary: hardware I/O and async glue only
│   └── src/
│       ├── main.rs         init (safety first), control loop, settings save, sleep
│       ├── ble.rs          GATT server, advertising windows, connection handling
│       ├── io.rs           LEDC (LED current + RGB), LED_EN, LASER_ON, CHG_SET, ADC
│       ├── power.rs        reset/wake info, deep sleep, panic handler
│       ├── storage.rs      flash access for the settings log (esp-storage)
│       └── board.rs        GPIO map (mirrors tools/kicad/aurora_parts.py)
├── partitions.csv    flash layout given to espflash
├── build.sh          tests + release build + merged image
└── dist/             build outputs
```

Everything that can be decided without touching a register is in `aurora-core`; the firmware
samples inputs, feeds them to `aurora_core::Controller` and applies the returned `Outputs`.
That keeps the parts that are hard to test on the bench (gestures, protection, packets,
settings) under unit tests.

### 1.2 Data flow and tasks

```
              every 10 ms             every 100 ms
 GPIO3 button ─────────┐   ADC VBAT/NTC, CHRG/STDBY ──┐
                       v                              v
                 ┌────────────────────── Controller ───────────────────────┐
 BLE writes ───> │ command() / profile_write() / ble_connected()           │
 BLE reads  <─── │ status() / profile_packet() / battery_percent()         │
                 └───────────────────────── tick() ────────────────────────┘
                                              │ Outputs
          LED current (LEDC duty + LED_EN) ───┤── LASER_ON ── RGB LEDC ── CHG_SET
          advertising mode ──> BLE task       └── save settings / deep sleep / reboot
```

One embassy executor runs on esp-rtos (the scheduler esp-radio needs):

* **main** – the control loop. Every 10 ms: sample the button, run `button()` + `tick()`, apply
  the outputs, store settings when asked, feed the watchdog, enter deep sleep when idle.
  Every 100 ms: four averaged ADC conversions per channel and the charger pins.
* **ble::host_task** – the trouble-host runner (HCI to the esp-radio controller).
* **ble::peripheral_task** – starts/stops advertising according to the controller's
  window/interval request, accepts one connection, serves GATT, sends notifications.

The controller lives in a critical-section mutex shared by the control loop and the BLE task.

**Lazy Bluetooth start.** The BLE controller (PHY calibration) is started the first time the
controller asks for a radio window while no gesture is in progress. Its start-up blocks the
executor; doing it at boot would make the button deaf right after a wake-up — exactly when the
second click of a "double click from sleep" arrives. Wake-ups that never open a window
(lockout, laser, stray presses) never power the radio.

### 1.3 Start-up order

1. `esp_hal::init` (80 MHz), then **LED_EN (GPIO7) and LASER_ON (GPIO10) driven low** —
   before logging, heap or anything else. Until then their 100 k pull-downs hold them low.
2. Logger (USB-Serial-JTAG), heap for esp-radio (64 KiB in the RAM the bootloader used +
   36 KiB, as the esp-radio documentation recommends), pin-map self-check.
3. Reset reason and deep-sleep wake cause; the wake pins' pad hold / wake enable left behind
   by the previous sleep are released (like ESP-IDF's `esp_deep_sleep_wakeup_io_reset`).
4. Settings from flash (partition table -> `nvs` partition -> settings log).
5. LEDC timer 0: 13 bit at 9765 Hz (80 MHz / 8192); channel 0 = LED current set point (0 %),
   channels 1-3 = RGB (100 % = dark, the LED is common-anode). CHG_SET floating.
6. ADC1 GPIO0/GPIO1, 11 dB, curve-fitting calibration (`AdcCalCurve`).
7. Watchdog: TIMG1 MWDT, 3 s, system reset.
8. esp-rtos scheduler, then the controller (with the button level sampled last) and the loop.

### 1.4 Fail-safe design

| Situation | What happens |
|---|---|
| Reset, boot, bootloader, deep sleep | GPIOs are inputs; the 100 k pull-downs keep LED_EN and LASER_ON low. The LED loop is additionally safe with the op-amp unpowered: the buck alone regulates to 0.6 V x 3 = 1.8 V, below the LED's forward voltage. |
| Panic (incl. CPU exceptions, stack overflow) | `#[panic_handler]` clears GPIO7/GPIO10 through `GPIO_OUT_W1TC` directly, logs, `software_reset()`. |
| Hang | TIMG1 watchdog (3 s) resets the system. |
| ADC conversion fails | Isolated failures are skipped; after 5 failed samples in a row zeros are reported: VBAT 0 -> the light is switched off, NTC 0 V -> "shorted sensor" -> thermal shutdown. |
| NTC open (or colder than about -7 °C) | Output limited to High, no turbo, no laser, no charging. Status shows -40.0 °C. |
| NTC shorted | Light off and refused, no laser. Status shows +150.0 °C. |
| Bluetooth fails to start | Logged; the flashlight works without Bluetooth. |
| Flash write fails | Retried every 2 s, given up after 3 failures so that sleep/reboot still happen. |
| Deep-sleep request rejected | Software reset after 100 ms (see `power::deep_sleep`). |
| Laser | Only from the button gesture. No BLE opcode or code path can switch it; it is cut after 60 s, above 60 °C, below 3.20 V, by lockout. The hardware interlock S2 is outside firmware control. |

### 1.5 Dependency notes

* `embassy-sync = "0.7"` (not 0.8): the trouble-host 0.6 `#[gatt_server]`/`#[gatt_service]`
  macros emit code that names `embassy_sync::blocking_mutex::raw::{NoopRawMutex, RawMutex}`
  and needs the trait of the embassy-sync version trouble-host uses (0.7.x).
* `esp-println` with `jtag-serial` only (no `auto`): the auto backend falls back to UART0,
  whose TX pin GPIO21 is the red cathode of the RGB LED.
* `esp-storage = "=0.9.0"`: the release that matches esp-hal 1.1.x (same esp-hal-procmacros
  / esp-metadata-generated). Its flash routines run from RAM inside a critical section, so
  BLE interrupts are only delayed during a write.
* The settings log does its own address checks on top of esp-storage instead of using
  `esp_bootloader_esp_idf::partitions::FlashRegion`, whose `erase()` (0.5.0) rejects an erase
  that ends at the end of the partition.
* `Rtc::sleep_deep` is not used: it calls `unreachable!()` right after requesting the sleep,
  which would race the reset-on-panic handler; `power::deep_sleep` issues the request with
  `Rtc::sleep` and waits.

---

## 2. How the light works (user manual)

### 2.1 Button

*Click* = press shorter than 0.4 s. Clicks belong together while the pause between them is
shorter than 0.4 s. *Hold* = press of 0.4 s or longer. Contacts are debounced (25 ms).

| Light is OFF | |
|---|---|
| 1 click | On at the remembered level (Moon / Low / Medium / High). With the profile's "remember" flag off: Low. |
| Hold | On in Moon (keeps Moon while held; Moon becomes the remembered level). |
| 2 clicks | Turbo (High if the profile has no turbo; High plus one red blink if the board is within 5 °C of the profile's temperature limit). |
| Click, then click-and-hold | **Laser** while held (max 60 s; see 2.5). The main LED stays off. |
| 3 clicks | Opens a 120 s Bluetooth window, RGB blinks blue twice, the light stays off. |
| 4 clicks | Lockout on (red x3) / off (green x3). |

| Light is ON | |
|---|---|
| 1 click | Off (settings are saved if they changed). |
| Hold | Steps Low -> Medium -> High -> Low ... The first step happens when the press becomes a hold (0.4 s), then every 0.6 s while held. From Moon or Turbo the cycle continues at Low. The level you stop at is remembered. |
| 2 clicks | Turbo on; 2 clicks again: back to the previous level. Refused (one red blink) within 5 °C of the temperature limit. |
| 3 clicks | Battery check on the RGB LED: 1-5 blinks (one per started 20 %) in green (> 50 %), yellow (20-50 %) or red (< 20 %). |

| In lockout | |
|---|---|
| 4 clicks | Unlock (green x3). |
| anything else | Ignored; clicks give one short red flash, holds give nothing (a button pressed in a pocket stays dark). |

Every button action blocks app commands that switch or dim the light for 3 s (the button
always wins), and a button action cancels an exact current set by the app.

**From deep sleep** the first press wakes the chip; the firmware knows the button woke it and
counts that press, so single, double (turbo), triple and quadruple clicks and the hold work
from sleep. (Very fast double clicks may be seen as one click if the second press starts and
ends while the chip is still booting, ~0.2 s.)

### 2.2 Levels and profiles

| | Extreme | Balanced (default) | Endurance | Custom |
|---|---|---|---|---|
| Moon / Low / Medium / High | 3 / 40 / 250 / 900 mA | 3 / 30 / 200 / 600 mA | 2 / 15 / 100 / 300 mA | set by the app, default = Balanced |
| Turbo | 2200 mA for 45 s | 1200 mA for 60 s | none (turbo = High) | |
| After the turbo time | 900 mA | 600 mA | — | |
| Temperature limit | 55 °C | 50 °C | 45 °C | 40-70 °C |
| Low-voltage step-down | 3.30 V | 3.35 V | 3.40 V | 3.10-3.60 V |
| Cell current limit | 2600 mA | 1600 mA | 800 mA | 200-3000 mA |
| Flags | turbo, remember, battery display | turbo, remember, battery display | remember, battery display | |

The profile is chosen in the app (there is no button gesture for it).

### 2.3 Turbo

Turbo runs at most the profile's turbo time, then the light steps down to the profile's
step-down current (the app shows "automatic" as the reason). Two clicks then return to the
level used before turbo; two more clicks start a new turbo. Thermal derating, the cell
current limit and low-voltage protection apply on top at all times.

### 2.4 RGB status LED

Highest priority first:

| Pattern | Meaning |
|---|---|
| Red x3 / green x3 | Lockout on / off |
| Cyan x3 | "Identify" from the app |
| Blue x2 | Bluetooth window opened (3 clicks while off) |
| 1-5 blinks green / yellow / red | Battery check (3 clicks while on) |
| One red blink | Request refused (turbo too hot, laser not allowed, switch-on refused) |
| Five fast red blinks | Battery empty: switched off, or switch-on refused |
| Short red flash | Click while locked |
| Green / yellow / red for 2 s after switch-on | Battery > 50 % / 20-50 % / < 20 % (profile flag) |
| Red slow breathing (3 s) | USB connected, charging |
| Green steady | USB connected, charge complete |
| Red blink every 4 s (light on) | Battery below 10 % |
| Cyan (dim) steady | App connected |
| Blue double blink every 3 s | Bluetooth window open, nobody connected |

The red LED also flickers briefly at every boot: the bootloader prints on U0TXD = GPIO21, which
is the red cathode (hardware choice). The firmware suppresses the ROM banner after deep sleep.

### 2.5 Laser

Click, then click-and-hold while the light is off: the laser is on while the button stays
held — at most 60 s per press (release and repeat the gesture to continue). It goes off above
60 °C or below 3.20 V and stays off until the button is released. Never in lockout, never from
Bluetooth. The slide switch S2 must be armed as well; the firmware cannot see or override S2.

### 2.6 Protection (what you notice)

* **Hot**: above the profile's temperature limit the brightness falls smoothly, reaching Low
  15 °C above the limit; above 70 °C Moon; above 80 °C the light switches off and cannot be
  switched on again until it has cooled below 75 °C.
* **Battery low**: below the profile's step-down voltage (measured with the LED running) the
  light drops one level every 5 s; below 3.10 V Moon; below 3.00 V it switches off (five red
  blinks) and refuses to switch on until the battery rests above 3.30 V or USB is connected.
  Choosing a level again lifts the step-down; it comes back if the voltage is still low.
* **Cell current**: the estimated battery current `V_LED(I)·I / (0.9·V_BAT)` with
  `V_LED = 2.75 V + 0.15 V/A·I` is kept below the profile's limit (the output is reduced).

### 2.7 Charging

USB-C charging at ~300 mA (nominal; the SoC estimate assumes 280 mA) between 0 °C and 45 °C (resumes 2 °C inside the window after a
temperature pause). Charging pauses while the LED runs above 500 mA. Plugging USB in resets
the MCU (VBUS-edge reset), keeps it awake and keeps Bluetooth reachable while connected.
Without firmware (e.g. a completely flat cell) the charger trickles at 10 mA.

### 2.8 Battery percentage and runtime

The percentage comes from the LiPo open-circuit curve (4.20 V = 100 % ... 3.30 V = 0 %) with
a load correction of +0.12 V per A of estimated cell current while the LED is on (and -0.12 V/A
of charge current while fast-charging), filtered so that it does not jump (at most 0.5 %/s,
small dead band, and it only moves "backwards" for differences above 3 %). "Charge complete"
reads 100 %. Runtime = 800 mAh x SoC / (estimated LED cell current + 20 mA for the MCU and
radio); the MCU term matters at Moon, where the LED itself draws ~2 mA from the cell.

### 2.9 Bluetooth windows and sleep

The radio advertises only in windows: while the light is on; 120 s after it is switched off
(by anything); 120 s after 3 clicks; while USB is connected; while an app is connected and 30 s
after it disconnects; or as long as the app asks with KEEPALIVE. Advertising is fast (100 ms)
for the first 30 s, then slow (500 ms).

When the light is off, no window is open and no USB is connected, the MCU goes to deep sleep
(LED_EN, LASER_ON and the RGB LED off first). The button or plugging in USB wakes it. If the
button is held down in lockout for 10 s (pocket), the MCU sleeps without the button as a wake
source and checks it every 20 s instead.

### 2.10 Flashing

Hold the button while plugging in USB: the VBUS-edge reset samples GPIO9 low and the ROM starts
download mode (no programmer needed). While the firmware runs with USB connected, tools can
also reset into download mode over USB-Serial-JTAG. Write `aurora-fw-v0.5.0-merged.bin` at
offset 0x0 with the web flasher, or:

```
espflash write-bin 0x0 firmware/dist/aurora-fw-v0.5.0-merged.bin
espflash monitor            # firmware log over USB-Serial-JTAG
```

Writing the merged image resets the settings to the factory defaults (the settings region at
0x9000 is erased by the image). To keep them, flash only the app:
`espflash flash --partition-table firmware/partitions.csv firmware/dist/aurora-fw-v0.5.0.elf`.

---

## 3. Bluetooth implementation notes

* **Address and name**: the controller uses its public address = eFuse base MAC with the
  Bluetooth offset (`esp_hal::efuse::interface_mac_address(Bluetooth)`, the value esp-radio
  hands to the controller). Name `Aurora-XXXX` = last two bytes of that address, upper-case
  hex; also the GAP Device Name. Appearance: Generic Light Source.
* **Advertising data** (21 bytes): Flags (LE General Discoverable, BR/EDR not supported) +
  complete list of 128-bit service UUIDs (Aurora Control Service). **Scan response**: complete
  local name. Connectable undirected, legacy advertising, one connection.
* **GATT**: GAP + GATT services, Battery Service (Battery Level read/notify), Aurora Control
  Service (Status read/notify, Command write, Profile read/write, Info read
  `"Aurora++ fw 0.5.0"`). Reads of Status, Profile and Battery Level refresh the value from the
  controller first. Command and Profile writes go to the controller; a refusal becomes an ATT
  error response with the protocol's application error code.
* **Notifications**: Status immediately when flags, profile, level, LED current, SoC, control
  source or laser change (at most every 150 ms) and every 2 s regardless (carries voltage,
  temperature, turbo / app-lock countdowns, runtime). Battery Level when the percentage changes.

**Details the protocol leaves open, and how the firmware decides them** (none of them
changes the packet formats; see also the report):

| Topic | Firmware behaviour |
|---|---|
| Command length | Exact: missing or extra argument bytes -> 0x81. |
| Error priority | 0x81 (malformed) before 0x80 (button priority) before 0x83 (lockout) before 0x82 (protection). |
| Profile characteristic write | Not 20 bytes or byte 0 != 3 -> 0x81; during the 3 s app lock -> 0x80 (like the PROFILE opcode). |
| ON / LEVEL / OUTPUT_MA while off | Switch the light on. ON while on: no change, success. |
| OUTPUT_MA | 0 -> 0x81. Clamped to 1 mA ... turbo current (High if the profile has no turbo / turbo not allowed). Above the step-down current the turbo timer runs; it is not restarted by further writes while running; after it expired, a new request above step-down restarts it. |
| Turbo near the limit | LEVEL 4, or OUTPUT_MA above step-down, within 5 °C of the limit (or with no valid temperature) -> 0x82 (not while turbo is already running). |
| LOCKOUT 1 while on | Switches the light off (and stops a held laser). |
| KEEPALIVE n | The window stays open at least n s from now (n <= 255 by the u8 argument; 600 s is the protocol cap). |
| Status level when off | The level a switch-on would use. Turbo after its time ran out: 4 with bit 1 cleared and turbo time 0. Turbo on a profile without turbo: 3 (High). |
| Status temperature on sensor fault | -400 (-40.0 °C) = open, 1500 (+150.0 °C) = shorted. |
| Fast advertising | 100 ms for the first 30 s of every advertising period, also after a disconnect. |
| Empty-battery shutdown | Opens the 120 s window like every switch-off. |

---

## 4. Flash layout

ESP32-C3-MINI-1-N4, 4 MB. `firmware/partitions.csv` (identical to espflash's default table,
written out so that image and firmware agree):

| Offset | Size | Content |
|---|---|---|
| 0x0000 | 0x8000 | ESP-IDF 2nd-stage bootloader (bundled with espflash 4.6.0, built from ESP-IDF v6.1; DIO, 40 MHz, 4 MB header; needs chip revision >= v0.3) |
| 0x8000 | 0x1000 | Partition table (with MD5) |
| 0x9000 | 0x6000 | `nvs` (data/nvs). **First 8 KiB = settings log**, rest unused. |
| 0xF000 | 0x1000 | `phy_init` (unused by esp-radio) |
| 0x10000 | 0x3F0000 | `factory` app (image 353 600 bytes, 8.6 % used) |

The merged image covers 0x0 up to the end of the app (no padding); the gaps (incl. the settings
region) are 0xFF.

### 4.1 Settings record (64 bytes, little-endian)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic `"AUR5"` |
| 4 | 1 | format version (1) |
| 5 | 1 | selected profile (0..3) |
| 6 | 1 | remembered level (0..3) |
| 7 | 1 | flags: bit0 lockout, bit1 battery-empty latch |
| 8 | 4 | sequence number |
| 12 | 20 | Custom profile (Profile packet format, id 3) |
| 32 | 28 | reserved (0xFF) |
| 60 | 4 | CRC-32 (IEEE) of bytes 0..60 |

The two 4 KiB sectors at 0x9000 and 0xA000 are a log of 64 records each. A save appends after
the newest record; when a sector is full the *other* sector is erased and the log continues
there. The newest record with a valid CRC (highest sequence number) wins, so a power failure
during a write or an erase never loses the previous settings. Nothing is written unless the
settings changed. One erase per 64 saves and two sectors -> about 12 million saves at 100 000
erase cycles.

**Saved**: the Custom profile, the selected profile, the remembered level, lockout and the
battery-empty latch. **When**: on SAVE, when the light is switched off by the button, when
lockout changes, when the empty latch changes, before deep sleep (sleep is a reboot) and before
the factory-reset reboot — each time only if something changed. The partition is found at run
time from the partition table (fallback 0x9000).

---

## 5. Building

Requirements: Rust with `build-std` for `riscv32imc-unknown-none-elf` — the simplest is a
rustup toolchain (`rustup toolchain install stable --component rust-src`), whose own `rust-lld`
links the firmware; a host Rust toolchain for the tests; espflash 4.x. (The image in `dist/` was
built with a distribution rustc 1.91 and `RUSTC_BOOTSTRAP=1`; `build.sh` then uses the first
`rust-lld` it finds, or the one in `CARGO_TARGET_RISCV32IMC_UNKNOWN_NONE_ELF_LINKER`. Rebuilding
gives the identical image in any folder, SHA-256 `9016ac6c…7d0c6`: `build.sh` fixes the build date
(`SOURCE_DATE_EPOCH`) and maps the machine-specific source paths (`--remap-path-prefix`), and the
two crates form one Cargo workspace, `firmware/Cargo.toml`.)

```
firmware/build.sh                 # host tests, release build, merged image, sizes
SKIP_TESTS=1 firmware/build.sh    # without the host tests
```

Environment overrides: `FW_RUST_BIN` (directory with the rustc/cargo for the target build,
default `/usr/lib/rust-1.91/bin`; if it does not exist, `cargo` from the PATH is used),
`HOST_CARGO`, `ESPFLASH`. If espflash is missing the script
runs `cargo install espflash --locked --version ^4` (on Linux it needs `pkg-config` and
`libudev-dev`).

By hand:

```
cd firmware/aurora-core && cargo test
cd firmware/aurora-fw && RUSTC_BOOTSTRAP=1 cargo build --release
espflash save-image --chip esp32c3 --merge --skip-padding --flash-size 4mb \
    --partition-table firmware/partitions.csv \
    firmware/target/riscv32imc-unknown-none-elf/release/aurora-fw \
    firmware/dist/aurora-fw-v0.5.0-merged.bin
```

The log level is set at build time with `ESP_LOG` (default `info`, in `.cargo/config.toml`).

---

## 6. Tunable constants

Values marked *P* are fixed by `ble_protocol.md`; changing them changes the product behaviour
the app expects. Times in ms unless noted, temperatures in 0.1 °C ("dC"), voltages in mV.

### 6.1 `aurora-core/src/config.rs`

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
| `STUCK_BUTTON_MS` | 10000 | Lockout: button held this long counts as stuck. |
| `STUCK_BUTTON_AFTER_WAKE_MS` | 300 | Same after a stuck-button timer wake. |
| `MIN_AWAKE_TIMER_WAKE_MS` | 400 | Minimum awake time after a stuck-button timer wake. |
| `STUCK_RECHECK_MS` | 20000 | Timer wake period while the button is stuck. |

### 6.2 Hardware conversion (`aurora-core/src/hw.rs`, `rgb.rs`)

| Constant | Value | Meaning |
|---|---|---|
| `LED_FULL_SCALE_MA` | 3235 | LED current at 100 % duty (3.3 V x 2k/102k / 20 mOhm). Calibrate on the bench. |
| `PWM_MAX_COUNTS` | 8191 | Largest 13-bit duty used; `duty = round(I / 3235 x 8191)`. |
| `NTC_SUPPLY_MV` | 3300 | NTC divider supply. |
| `NTC_R_FIXED` / `NTC_R25` | 100 k / 100 k | Divider resistor / NTC at 25 °C. |
| `NTC_BETA` | 4250 | NTC B25/50. |
| `RGB_FULL_R` / `_G` / `_B` | 255 / 70 / 110 | RGB channel duty at full logical brightness (out of 255): red has 1 k, green/blue 100 R. Tune for even colours. |
| `Rgb::YELLOW`, `CYAN_DIM`, ... | see `rgb.rs` | Logical colours of the patterns. |

### 6.3 Firmware (`aurora-fw/src`)

| Constant | Value | Meaning |
|---|---|---|
| `CONTROL_PERIOD_MS` (main.rs) | 10 | Control loop / button sampling period. |
| `SENSOR_PERIOD_MS` (main.rs) | 100 | ADC and charger pin sampling period. |
| `WATCHDOG_S` (main.rs) | 3 | Watchdog timeout (> worst-case flash erase). |
| `SLEEP_ADV_QUIET_MS` (main.rs) | 500 | Advertising must be off this long before deep sleep. |
| heap (main.rs) | 64 KiB + 36 KiB | esp-radio heap: `#[ram(reclaimed)]` region (bootloader RAM, 0x3FCCE400) + normal RAM. |
| `PWM_FREQ_HZ` (board.rs) | 9765 | LEDC frequency (13 bit from 80 MHz). |
| `DEFAULT_SETTINGS_OFFSET` (storage.rs) | 0x9000 | Settings region if the partition table cannot be read. |
| esp-radio `Config` (ble.rs) | defaults, 1 connection | BLE TX power is the esp-radio default (+9 dBm). |

Profile values (levels, turbo, limits) are not constants to edit: the built-in profiles are
fixed by the protocol (`profile.rs`), and the Custom profile is set from the app.

---

## 7. Verification status

**Host tests** (`cd firmware/aurora-core && cargo test`, 93 tests): gesture parser (debounce,
1-4 clicks, holds and repeats, click+hold, 400 ms boundaries at the firmware's 10 ms sampling,
wake from sleep), profile table and clamping, packet layouts, command decoding and error codes,
NTC conversion against the formula, duty scaling, OCV curve, load correction and SoC filter,
cell current limit (inverse checked), runtime, thermal derating, low-voltage state machine,
laser rules, charger / USB detection incl. the pause probing, RGB priorities, settings record,
CRC, log rotation, power loss during a write, and 31 end-to-end scenarios of the controller
(button UI, turbo timer, lockout, laser 60 s, app commands and their errors, exact current,
profile write clamping, save-only-when-changed, factory reset, windows and sleep, thermal and
low-voltage protection, empty latch, cell limit, sensor faults, charging, stuck button).

**Built**: `cargo build --release` without warnings; merged image checked for bootloader /
partition table (MD5) / app headers and the app descriptor.

**Not verified** (no hardware): everything in the bench plan below.

### 7.1 Bench plan (in this order)

1. **Safe outputs first** (LED and laser wires disconnected, current-limited supply on BAT+):
   scope GPIO7 (LED_EN), GPIO10 (LASER_ON) and GPIO6 (LED_PWM) through power-up, EN reset,
   flashing, panic (debug build), watchdog and deep-sleep wake. LED_EN/LASER_ON must stay
   < 0.4 V except when commanded.
2. **Boot log** (`espflash monitor`): reset reason, settings loaded from 0x9000, no panic; BLE
   starts at the first window.
3. **ADC**: VBAT vs. DMM at 3.0 / 3.7 / 4.2 V; NTC at room temperature; replace the NTC by
   resistors to check the thresholds (33.2 k = 50 °C, 27.2 k = 55 °C, 22.4 k = 60 °C,
   15.4 k = 70 °C, 10.9 k = 80 °C); open NTC must read "open" (-40.0 °C). Check the reading
   at ADC saturation stays >= 2800 mV, otherwise lower `NTC_OPEN_MV`.
4. **LED current loop** with the LED on a heat sink: set 3, 30, 200, 600, 1200, 2200 mA with
   OUTPUT_MA and measure (sense resistor voltage). Calibrate `LED_FULL_SCALE_MA`; check Moon
   (op-amp offset) and that duty is set before LED_EN.
5. **Button**: all gestures from off and on, from deep sleep (double click -> turbo, quadruple
   click -> unlock), hold stepping, lockout.
6. **RGB**: polarity and colours (identify, lockout, battery colours); tune `RGB_FULL_*`.
7. **Charger**: USB in -> CHG_SET low, ~300 mA, red breathing; LED > 500 mA -> CHG_SET high.
   Record what CHRG/STDBY do while CHG_SET is high (the firmware tolerates both) and that USB
   removal is detected (<= 1 s while charging, <= 10 s while paused).
8. **Deep-sleep current** after the 120 s window: expect ~10 µA + 17 µA (NTC divider) + 2 µA
   (VBAT divider). If clearly higher, check GPIO20's pad state in sleep (U0RXD reset default
   may enable an internal pull-up into R29) and the TP4057 status pins without VBUS (the
   internal pull-ups on GPIO4/5 must not leak into the unpowered charger or cause wake loops).
9. **Bluetooth** (nRF Connect): name vs. MAC, 100 ms -> 500 ms after 30 s, GATT table,
   notifications, every error code (0x80 within 3 s of a click, 0x81, 0x82 with a hot NTC
   substitute, 0x83 in lockout), Profile write clamping read-back, SAVE + power cycle,
   FACTORY_RESET.
10. **Protection**: low voltage with a bench supply (3.35 -> 3.10 -> 2.95 V under load), empty
    latch, cell current limit (Custom profile with 500 mA), thermal derating with NTC
    substitutes.
11. **Laser** (S2 armed, safe target): 60 s cut, > 60 °C and < 3.20 V cuts, lockout, nothing
    from Bluetooth.
12. **Stuck button in lockout** (clamp the button): sleeps after 10 s, wakes every 20 s, average
    current.

---

## 8. Known limitations

* The red RGB LED flickers at each boot (bootloader log on U0TXD/GPIO21; the ROM banner is
  suppressed after deep sleep, the 2nd-stage bootloader's own log is not).
* A press that starts and ends while the chip boots from deep sleep (~0.2 s) is merged with
  the wake press.
* Below about -7 °C the NTC reading is indistinguishable from an open sensor: output limited to
  High, no charging, no laser until the board warms up.
* The merged image resets the settings (flash the ELF to keep them).
