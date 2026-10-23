<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# ESP32-C3 port (experimental)

LuxLibre on the Espressif ESP32-C3, written for ESP-IDF 5.x and the FlashKa keychain boards:
v0.5 ([../../boards/flashka-keychain-v05/board.h](../../boards/flashka-keychain-v05/board.h))
with one button, v0.6 ([../../boards/flashka-keychain-v06/board.h](../../boards/flashka-keychain-v06/board.h))
with three buttons on a resistor ladder, of which LuxLibre uses the main one
([below](#resistor-ladder-buttons-flashka-v06)), and v0.7
([../../boards/flashka-keychain-v07/board.h](../../boards/flashka-keychain-v07/board.h)): the v0.6
pins and ladder with a stronger LED driver (3552 mA at full duty; LuxLibre's level 150 is
2850 mA, so the LED never gets more than its 3.0 A rating) and one 14500 Li-ion cell (Vapcell
F15, 1500 mAh).

**Status:** experimental. The port is written against the ESP-IDF 5.x API and has been checked
against declarations of that API; the GitHub workflow builds it for every FlashKa board in the
`espressif/idf` container once the repository is published, as a job that may fail until it has
passed once. It has not been compiled with ESP-IDF itself or run on a FlashKa yet. **The
resistor-ladder path for v0.6 is untested on hardware** as well; check it with the
[ladder bring-up](#bring-up-checks-for-the-ladder) below. Until the port has passed the bring-up
tests ([docs/testing.md](../../../docs/testing.md)), the original FlashKa firmware (written in
Rust, with the Bluetooth app and deep sleep, on v0.6 also the presenter mode) stays the reference
firmware for that light: [hardware/flashka-keychain-v05/](../../../hardware/flashka-keychain-v05/README.md),
[hardware/flashka-keychain-v06/](../../../hardware/flashka-keychain-v06/README.md) (its firmware
also builds the v0.7 image, firmware 0.7.0).

## Build and flash

Install ESP-IDF 5.x ([Espressif's guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/get-started/index.html)), then:

```sh
cd firmware/ports/esp32c3
idf.py set-target esp32c3
idf.py -DLX_BOARD=flashka-keychain-v05 build     # or flashka-keychain-v06, flashka-keychain-v07
idf.py -p <serial port> flash monitor
```

`LX_BOARD` selects the folder under `firmware/boards/`. When you switch boards, run
`idf.py fullclean` first, or give each board its own build directory with `-B`. The console
(`help`, `status`, `set`, ...) runs over the chip's built-in USB serial/JTAG interface, so
`idf.py monitor` or any serial terminal reaches it.

## What the port uses

| Function | ESP32-C3 resource |
|---|---|
| Main LED | LEDC PWM, 13 bit, 9.77 kHz, filtered into the current set point of the FlashKa's buck driver; `LED_EN` switches the driver off at level 0 |
| Indicator | three LEDC channels for the common-anode RGB LED (v0.6: the two RGB LEDs of the light ring, in parallel on the same pins) |
| Button | v0.5: GPIO3, digital, low = pressed, internal pull-up on. v0.6: a resistor ladder read with ADC1 on GPIO3, wake-up on GPIO9 ([below](#resistor-ladder-buttons-flashka-v06)) |
| Laser | a GPIO behind the hardware slide-switch interlock (S2) |
| Battery voltage | ADC1 channel 0 (cell / 2) with the curve-fitting calibration |
| Temperature | ADC1 channel 1, 100 kΩ NTC (B 4250) with 100 kΩ to 3.3 V, table from [lx_ntc.h](../../hal/lx_ntc.h) |
| Charger | TP4057 status pins; the charge-set pin selects normal current (low), 10 mA trickle (floating) or off (high). The board has no VBUS sense pin, so while charging is off the pin is floated for 100 ms every 5 s to see whether USB is plugged in, only while the cell temperature allows charging ([CHG-3](../../../docs/design-rules.md#chg-3)) |
| Sleep | light sleep with wake-up on the button (GPIO; on v0.6 GPIO9) and a timer; while charging is allowed, also on the charger status pins, so that plugging in USB wakes the light and charging starts (to verify on hardware: no leakage from the pull-ups into the unpowered charger) |
| Storage | one 256-byte NVS blob, written only when it changes; the RAM copy is updated only after a successful write |
| Watchdog | task watchdog, 3 s, with panic reset; brown-out detector on (`sdkconfig.defaults`) |
| Tick | FreeRTOS `vTaskDelayUntil`, 10 ms (`CONFIG_FREERTOS_HZ=1000`) |

## Resistor-ladder buttons (FlashKa v0.6)

A resistor ladder puts several buttons on one pin. On the v0.6 board the net BTN has a 10 kΩ
pull-up (R9) to 3.3 V; the main button connects BTN straight to ground, next through 1 kΩ and
previous through 2.2 kΩ, so every press gives its own voltage. BTN goes to two pins: GPIO3
measures it with the ADC, GPIO9 reads it as a digital input.

| Pressed | BTN | LuxLibre |
|---|---|---|
| nothing | 3.30 V | released |
| main (alone or with any other) | 0 V | pressed |
| previous + next together | 0.212 V | released (ignored) |
| next | 0.300 V | released (ignored) |
| previous | 0.595 V | released (ignored) |

LuxLibre's user interface has one button ([FW-3](../../../docs/design-rules.md#fw-3)). The slide
buttons belong to the original FlashKa firmware (level steps, and the presenter mode: a Bluetooth
keyboard that turns slides), which LuxLibre does not have. How the port handles the ladder:

- **Reading.** GPIO3 is ADC1 channel 3 at 2.5 dB attenuation (0 to 1050 mV,
  [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32c3/api-reference/peripherals/adc.html))
  with its own curve-fitting calibration. `button_down()` is true when one calibrated reading is
  below `LX_ESP_BTN_MAIN_BELOW_MV` (106 mV, midway between main at 0 V and the lowest other level,
  0.212 V). The core debounces it like any button, and the main button always wins because it
  pulls BTN to 0 V whatever else is pressed.
- **Pull-ups off.** The levels are computed for R9 alone. The chip's internal pull-ups (45 kΩ
  typical, [datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html)) would move
  them, so the port switches them off on GPIO3 (analog input) and on GPIO9 (a boot strap pin
  whose pull-up is on at reset).
- **Wake-up.** An ADC pin has no digital input, so GPIO9 is the light-sleep wake-up source. Every
  press is below the digital low threshold (0.25 × VDD = 0.825 V,
  [datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html)), so any button
  wakes the chip. The port waits one tick (10 ms) for the contacts to settle, reads the ladder and
  goes back to sleep if it was not the main button.
- **A slide button held down** keeps GPIO9 low, so a low-level wake-up would fire again at once.
  The port then wakes when GPIO9 goes high (release) and reads the ladder every 50 ms for the main
  button; after 10 s (a button squeezed in a pocket) only every 2 s, to keep the standby current
  down ([BAT-6](../../../docs/design-rules.md#bat-6), [BAT-7](../../../docs/design-rules.md#bat-7)).
  These are port defaults (`LADDER_POLL_MS`, `LADDER_STUCK_MS`, `LADDER_STUCK_POLL_MS` in
  `main/hal_esp32c3.cpp`).
- **Fallback.** Without a calibrated reading (the chip has no calibration data for 2.5 dB, or a
  conversion fails) GPIO9 decides and any button counts as the main button: the single-button
  behaviour of v0.5, as in the FlashKa firmware.

How another board declares a ladder: [docs/firmware/porting.md](../../../docs/firmware/porting.md#resistor-ladder-buttons-esp32-c3).

### Bring-up checks for the ladder

None of this has run on a board yet. On the first v0.6 board, before relying on the port:

1. With the firmware running, measure BTN against GND for each button: 3.30 V, 0 V, 0.212 V,
   0.300 V and 0.595 V (within about 10 mV with 1 % resistors, as in the bring-up plan of the
   [FlashKa firmware](../../../hardware/flashka-keychain-v06/docs/firmware.md)). Higher readings
   mean an internal pull-up is still on.
2. The main button: every gesture of [user-interface.md](../../../docs/firmware/user-interface.md)
   from off, from on and in lockout.
3. Next, previous and both together: nothing happens, from off (asleep) and while the light is on.
4. Hold next and click main: the click counts. Hold next for more than 10 s, then hold main for
   3 s: the light reacts.
5. Standby current asleep, and with a slide button held ([BAT-6](../../../docs/design-rules.md#bat-6));
   the ladder alone then draws about 0.3 mA (3.3 V across R9 plus R30 or R31: 11 kΩ or 12.2 kΩ).
6. Plugging in USB while the light is asleep still starts charging.

## Known limitations

- **Standby current.** Light sleep keeps the radio off but draws much more than deep sleep
  (the module needs 5 µA in deep sleep,
  [datasheet](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.html)). With the
  FlashKa's 800 mAh, design rule [BAT-6](../../../docs/design-rules.md#bat-6) allows 33 µA.
  Measure the real value; a deep-sleep mode that wakes on the button (as the Rust FlashKa
  firmware does) is the planned fix.
- **No Bluetooth yet.** The Rust FlashKa firmware and its web app offer Bluetooth control (and on
  v0.6 the presenter mode); this port does not. A LuxLibre Bluetooth service that exposes the
  parameters and `status` is planned.
- **v0.6 slide buttons.** Next and previous do nothing under LuxLibre. While one has been held for
  more than 10 s, the port looks for the main button only every 2 s, so a short main click can be
  missed until the slide button is released.
- **The red indicator LED** (on v0.6 the red of the light ring) is on the UART0 TX pin, so it
  flickers during the ROM boot messages (`CONFIG_BOOTLOADER_LOG_LEVEL_NONE` silences the
  bootloader; the ROM's own boot messages are controlled by eFuse and strapping settings, not by
  the firmware). On v0.6 the red resistors are 330 Ω instead of 1 kΩ and LuxLibre has no colour
  balance per board: check the mixed colours (yellow, white) on the bench.
- **USB is also the charger input.** While the console is connected the light does not sleep and
  the main LED is capped at `CHG_MAXLVL`.
