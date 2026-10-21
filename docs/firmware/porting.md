<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Porting LuxLibre

Two kinds of port:

- **[A new board](#a-new-board)** with an MCU that LuxLibre already supports (ATtiny1616,
  CH32V003, ESP32-C3): one header file, no C++ changes. This is the usual case.
- **[A new MCU](#a-new-mcu)**: implement the hardware abstraction layer (about 20 functions),
  start-up code and a build file.

Either way, the result is only finished when the board has been measured and tested
([FW-2](../design-rules.md#fw-2), [FW-8](../design-rules.md#fw-8)).

---

## A new board

### 1. Copy the closest board

| Start from | When |
|---|---|
| `boards/example-tiny1616-pwm/` | ATtiny1616 switching the LED with PWM (FET drive or a linear regulator's enable) |
| `boards/example-ch32v003-buck/` | CH32V003 with a regulated driver: PWM filtered into a current set point, an enable pin, an NTC |
| `boards/flashka-keychain-v05/` | ESP32-C3 with charger, RGB indicator, laser and console |
| `boards/flashka-keychain-v06/` | the same with several buttons on one pin ([resistor ladder](#resistor-ladder-buttons-esp32-c3)) |

```sh
cd firmware/boards
cp -r example-ch32v003-buck my-light
```

### 2. Fill in the header

`core/lx_board.h` includes your `board.h` and fills in a default for everything you leave out.

**Identity and hardware present**

| Macro | Meaning | Default |
|---|---|---|
| `LX_BOARD_NAME` | name printed by `ver` (required) | none |
| `LX_TICK_MS` | main loop period | 10 |
| `LX_STORAGE_SIZE` | bytes of EEPROM or emulated EEPROM for settings (at least 256) | 256 |
| `LX_HAS_CONSOLE` | text console (USB or UART) | 0 |
| `LX_HAS_AUX_RGB` | indicator LED (RGB or single colour) | 0 |
| `LX_HAS_LASER` | laser with hardware interlock | 0 |
| `LX_HAS_CHARGER` | charger with status signals | 0 |
| `LX_HAS_TEMP` | temperature sensor (NTC or the MCU's own) | 1 |
| `LX_BAT_CELLS` | cells in series | 1 |

**Main channel and LED model** (measure these, [FW-2](../design-rules.md#fw-2))

| Macro | Meaning | How to get it |
|---|---|---|
| `LX_OUT_MIN_Q16` | output at level 1, as a fraction of full scale × 65535 | the lowest stable output: for 10-bit PWM the smallest duty 1/1024 gives 64; for a current set point, 65535 × I_min / I_max (1 mA of 2.2 A gives 30) ([LED-7](../design-rules.md#led-7)) |
| `LX_MAIN_MAX_MA` | LED current at level 150 (0 if unknown, e.g. FET drive); at most 80 % of the LED's maximum current ([LED-2](../design-rules.md#led-2)) | measure at level 150 with a full cell |
| `LX_LED_VF0_MV`, `LX_LED_RS_MOHM` | LED voltage model V = VF0 + RS × I | measure the hot LED's voltage at two currents I1, I2: RS = (V2 - V1) / (I2 - I1), VF0 = V1 - RS × I1 |
| `LX_DRIVER_EFF_PCT` | driver efficiency for the cell-current estimate, 1-100 | LED power / input power × 100 at a high level (for example 88); for a linear regulator use Vf at turbo / 4.2 V × 100, so that the turbo cell current is not underestimated |

The LED model and the efficiency feed the cell current limit (`BAT_MAX_MA`,
[BAT-1](../design-rules.md#bat-1)) and the simulator. A wrong model gives a wrong limit, so
measure.

**Parameter defaults.** Any parameter's default can be set with `LX_DEF_<NAME>`, for example
`LX_DEF_THM_LIMIT`, `LX_DEF_TURBO_LVL`, `LX_DEF_BAT_MAX_MA`, `LX_DEF_UI_STYLE`,
`LX_DEF_POCKET_S`. The full list with ranges is in [parameters.md](parameters.md). Set at least
the thermal limit (from the measured sensor-to-surface difference,
[THM-1](../design-rules.md#thm-1)), the turbo level (below the full-scale current, which itself
stays within 80 % of the LED's maximum, [LED-2](../design-rules.md#led-2)), the cell current
limit and the low-voltage thresholds for the chemistry ([BAT-5](../design-rules.md#bat-5)).

### 3. Pins and port options

Each port reads its own macros; the defaults are those of the port's example board.

| Port | Macros |
|---|---|
| ATtiny1616 | `LX_TINY_PWM_WO` (TCA0 output: 0 = PB0 ...), `LX_TINY_BTN_PIN` (PORTA pin, fully asynchronous pins wake from power-down), `LX_TINY_TEMP_OFFSET_DC` (internal sensor offset) |
| CH32V003 | `LX_CH32_BTN_PORT`, `LX_CH32_BTN_PORTSEL` (EXTI code: 0 = PA, 2 = PC, 3 = PD), `LX_CH32_BTN_PIN`, `LX_CH32_EN_PORT`, `LX_CH32_EN_PIN` (driver enable), `LX_CH32_NTC_ADC_CH` (-1 = no NTC), `LX_CH32_NTC_PORT`, `LX_CH32_NTC_PIN`, `LX_CH32_NTC_RFIX`, `LX_CH32_NTC_R25`, `LX_CH32_NTC_BETA`, `LX_CH32_VREFINT_MV` |
| ESP32-C3 | `LX_ESP_GPIO_BTN` (one button, low = pressed) or a resistor ladder (`LX_ESP_BTN_LADDER_ADC_GPIO`, `LX_ESP_BTN_WAKE_GPIO`, `LX_ESP_BTN_MAIN_BELOW_MV`, [below](#resistor-ladder-buttons-esp32-c3)), `LX_ESP_GPIO_LED_PWM`, `LX_ESP_GPIO_LED_EN`, `LX_ESP_GPIO_LASER`, `LX_ESP_GPIO_RGB_R/G/B`, `LX_ESP_GPIO_CHG_STAT`, `LX_ESP_GPIO_CHG_DONE`, `LX_ESP_GPIO_CHG_SET`, `LX_ESP_LED_FULL_MA`, `LX_ESP_VBAT_DIV`, `LX_ESP_NTC_RFIX`, `LX_ESP_NTC_R25`, `LX_ESP_NTC_BETA` |

The CH32V003 main PWM is fixed on PD2 (TIM1 channel 1); the ATtiny1616 MCU measures its own
supply as the cell voltage, so it must run directly from a single Li-ion cell.

#### Resistor-ladder buttons (ESP32-C3)

A resistor ladder puts several buttons on one pin: a pull-up resistor to the supply, the main
button straight to ground and every other button to ground through its own resistor, so each
press gives its own voltage. LuxLibre's user interface uses one button
([FW-3](../design-rules.md#fw-3)): on such a board the port reports "pressed" only for the main
button and ignores the others. A board declares the ladder with three macros instead of
`LX_ESP_GPIO_BTN`; the FlashKa Keychain v0.6 header
([boards/flashka-keychain-v06/board.h](../../firmware/boards/flashka-keychain-v06/board.h)) is
the example.

| Macro | Meaning | FlashKa v0.6 |
|---|---|---|
| `LX_ESP_BTN_LADDER_ADC_GPIO` | the pin that measures the ladder with ADC1 (GPIO0 to GPIO4 on the ESP32-C3) | 3 |
| `LX_ESP_BTN_WAKE_GPIO` | a second pin on the same net, read as a digital input (low = some button); it wakes the chip from light sleep | 9 |
| `LX_ESP_BTN_MAIN_BELOW_MV` | "pressed" = calibrated voltage below this, in mV | 106 |

- **Threshold.** Put the main button at 0 V and the threshold midway to the lowest other level
  (FlashKa v0.6: previous and next together give 0.212 V, so 106 mV). Check the worst case with
  the resistor and supply tolerances and the ADC error (±10 mV after calibration,
  [datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html)). The port reads
  the pin at 2.5 dB attenuation, 0 to 1050 mV
  ([ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32c3/api-reference/peripherals/adc.html)),
  so the threshold must lie inside that range.
- **Wake pin.** Every press must pull the wake pin below the digital low threshold (0.25 × VDD,
  [datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html)), so that any
  button wakes the chip; the port then reads the ladder and goes back to sleep if it was not the
  main button. A button that stays pressed does not keep the chip awake
  ([BAT-6](../design-rules.md#bat-6), [BAT-7](../design-rules.md#bat-7)); details in the
  [port README](../../firmware/ports/esp32c3/README.md#resistor-ladder-buttons-flashka-v06).
- **Pull-ups.** The port switches off the internal pull-ups of both pins: in parallel with the
  ladder's pull-up they would move every level.
- **Measure** the levels on the real board and note them in the header
  ([FW-2](../design-rules.md#fw-2)).

### 4. Simulate, build, measure

```sh
cd firmware
make sim BOARD=my-light                     # the simulator with your header
build/luxsim-my-light --preset 18650 --set TURBO_S=0 "2C W600000"
make ch32v003 BOARD=my-light                # or: make tiny1616 BOARD=my-light
```

Then follow [testing.md](../testing.md): bring-up with a current-limited supply, default-off
check, flashing, calibration (`BAT_CAL`, `THM_OFFSET`), the measured values above, the thermal
test, and a test report. Put the measured values back into the header and cite the report in a
comment.

### 5. Share it

A pull request with the board folder, a short README for the board (what it is, where the
hardware files are, the test report) and an entry in CHANGELOG.md
([CONTRIBUTING.md](../../CONTRIBUTING.md)).

---

## A new MCU

### What a port contains

```text
firmware/ports/<mcu>/
    hal_<mcu>.cpp     the HAL functions (hal/lx_hal.h)
    main.cpp          lx::light::init(); for (;;) { hal::wait_tick(); lx::light::tick(); }
    startup.S, link.ld, <mcu>_regs.h    for bare-metal ports (vector table, stack, registers)
    port.mk           make rules, included by firmware/Makefile (or the vendor's build files)
    README.md         status, toolchain, flashing, limitations
```

Register definitions can come from the vendor's headers, or be generated from the vendor's
machine-readable description (the ATtiny1616 port generates `tiny1x_io.h` from Microchip's ATDF
file with `atdf_to_header.py`). Keep the port free of vendor frameworks where possible: it
makes the build reproducible and the binary small.

### The HAL contract

The core calls these functions from the main loop only (no re-entrancy). Units: mV, deci-°C,
ms, and Q16 output power (0-65535).

| Function | Must do |
|---|---|
| `init()` | **first** drive every output that can make light or heat to off ([DRV-7](../design-rules.md#drv-7)); then clocks, tick timer, PWM, ADC, storage, watchdog |
| `watchdog_kick()` | reset the watchdog; called every tick ([DRV-8](../design-rules.md#drv-8)) |
| `reboot()` | software reset |
| `millis()` | monotonic milliseconds, also advanced over sleep |
| `wait_tick()` | idle in a low-power mode until the next `LX_TICK_MS` tick |
| `sleep(max_ms, wake_on_button)` | deepest sleep that still keeps RAM: wake on a button press and/or after `max_ms` (0 = no timer); outputs off; return true if the button woke it |
| `button_down()` | raw switch state (the core debounces) |
| `battery_mv()` | pack voltage in mV, averaged if the ADC is noisy |
| `temperature()` | deci-°C; `-32768` if the board has no sensor; return values outside -40...150 °C for an open or shorted sensor so that the core detects the fault |
| `usb_present()`, `charger_status()` | USB power and charger state (`CHG_NONE` if not supported) |
| `set_main(power)` | 0 = driver disabled (enable pin off); 1-65535 = fraction of full scale, as PWM at 3 kHz or more, a current set point, or both ([LED-6](../design-rules.md#led-6)) |
| `set_aux(r, g, b)`, `set_laser(on)` | optional outputs; no-ops if absent |
| `set_charge(enable, allowed)` | called every 100 ms; `enable` = charge now; `allowed` = the cell temperature is inside the charge window. While `allowed` is false, no current may reach the cell, not even to detect USB power ([CHG-3](../design-rules.md#chg-3)) |
| `storage_read()`, `storage_write()` | `LX_STORAGE_SIZE` bytes; skip unchanged bytes to save wear; return false if the write failed. A reset in the middle of a write is detected by the core's checksums (it falls back to an older state slot or to defaults); flash emulation with pages should keep the core's blocks in separate pages (the core places the calibration 64 bytes below the state ring for that reason) |
| `console_getc()`, `console_write()` | optional text console; may drop output when no host is connected |

### Rules for port code

- No heap, exceptions, RTTI or virtual functions; build with `-fno-exceptions -fno-rtti
  -fno-threadsafe-statics` and section garbage collection.
- No floating point at run time on MCUs without an FPU (compute tables with `constexpr`, see
  `hal/lx_ntc.h`).
- Interrupts only set flags or count time; all decisions stay in the core.
- The sleep current is part of the design ([BAT-6](../design-rules.md#bat-6)): disable the ADC,
  pull-ups that draw current, and unused clocks before sleeping; measure it.

### Bring-up of a new port

1. Build and check the size (`avr-size`, `riscv64-unknown-elf-size`), the vector table and the
   start-up code in the disassembly (`objdump -d`).
2. On a test board with a current-limited supply: outputs off during reset and with a blank MCU,
   then the tick (blink the indicator at 1 Hz from a test build), the button, the ADC readings.
3. Run the gesture checklist and protections from [testing.md](../testing.md#firmware-tests),
   including `wdtest` if the board has a console, and measure the sleep current.
4. Add the build to CI ([.github/workflows/firmware.yml](../../.github/workflows/firmware.yml)) and
   write the port README with its status.

The existing ports are the best examples: [ports/README.md](../../firmware/ports/README.md).
