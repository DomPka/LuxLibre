<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Ports

A port implements the hardware abstraction layer ([../hal/lx_hal.h](../hal/lx_hal.h)) for one
MCU family. How to write one: [docs/firmware/porting.md](../../docs/firmware/porting.md).

| Port | Status | Flash / RAM used | Build | Flash with |
|---|---|---|---|---|
| [host](host/) | simulator and tests, used by CI on every change | PC | `make test`, `make sim` | |
| [attiny1616](attiny1616/) | builds and links; not yet tested on hardware | 11.4 KB of 16 KB / 0.2 KB of 2 KB | `make tiny1616 BOARD=<board>` | UPDI (`pymcuprog`) |
| [ch32v003](ch32v003/) | builds and links; not yet tested on hardware | 11.8 KB of 15.75 KB / 0.5 KB of 2 KB | `make ch32v003 BOARD=<board>` | WCH-LinkE (`minichlink`) |
| [esp32c3](esp32c3/) | experimental; checked against the ESP-IDF API, CI build configured (allowed to fail until it has passed once); not yet compiled with ESP-IDF or tested on hardware | | `idf.py build` | USB |

"Not yet tested on hardware" means exactly that: the code follows the datasheets and reference
manuals and has been checked by building, by disassembly (vector tables, start-up) and by
review, but nobody has run it on a board. The first board for each port goes through the
bring-up in [docs/testing.md](../../docs/testing.md#bring-up-of-a-new-board) before anything
else.

## host

`ports/host/sim.cpp` implements the HAL on top of a simulated flashlight (cell, LED and driver,
two-node thermal model, sensor with lag and noise, USB charger, emulated EEPROM, console).
Details: [docs/firmware/simulator.md](../../docs/firmware/simulator.md).

## attiny1616

The MCU of many current enthusiast drivers (Microchip tinyAVR 1-series).

- **Clock:** 10 MHz (20 MHz oscillator / 2), inside the chip's speed grade down to 2.7 V, below
  the low-voltage cut-off of a Li-ion cell.
- **Main output:** TCA0 single-slope PWM, 10 bit, about 9.8 kHz, on the pin chosen by
  `LX_TINY_PWM_WO` (default WO0 = PB0).
- **Tick:** TCB0 interrupt every 10 ms; in sleep, the RTC periodic interrupt (1 Hz from the
  32 kHz ultra-low-power oscillator) keeps the time and the button pin wakes the MCU from
  power-down.
- **Battery:** the MCU runs from the cell and measures its own supply against the 1.1 V
  reference (4 samples), so a single Li-ion cell powers it directly.
- **Temperature:** the internal sensor with the factory calibration from the signature row,
  16 samples summed so that ADC noise gives readings finer than the 1 °C resolution of one
  sample; `LX_TINY_TEMP_OFFSET_DC` adds a board offset.
- **Storage:** EEPROM, unchanged bytes are skipped.
- **Watchdog:** 1 s.
- **Brown-out detector:** set only by the BODCFG fuse, which is off from the factory. Write it
  once per chip with `make tiny1616-fuses UPDI_PORT=<port>` (0x44: 2.6 V, on while running, off in
  power-down) ([DRV-8](../../docs/design-rules.md#drv-8)).
- **Toolchain:** avr-gcc 7.3 or newer. avr-libc provides `avr/pgmspace.h`; the chip header
  `tiny1x_io.h` is generated from Microchip's ATDF file by `atdf_to_header.py`, and
  `crt_avrxmega3.S` is the start-up code, so the port does not depend on avr-libc's device
  support for this chip.

## ch32v003

A 32-bit RISC-V MCU that costs about $0.13 in quantity and runs from 2.7 to 5.5 V.

- **Clock:** 24 MHz internal oscillator, no PLL.
- **Main output:** TIM1 channel 1 on PD2, 10 bit, about 23 kHz; an optional enable pin
  (`LX_CH32_EN_PORT`/`LX_CH32_EN_PIN`) switches the driver off at level 0.
- **Tick:** SysTick every 10 ms; in sleep, standby mode with the auto-wake-up timer (1 s, from
  the 128 kHz LSI oscillator) and the button on an EXTI line.
- **Battery:** VDD measured through the 1.2 V internal reference (`LX_CH32_VREFINT_MV`;
  calibrate with `BAT_CAL`).
- **Temperature:** an NTC on an ADC channel, converted with a table that the compiler computes
  from `LX_CH32_NTC_RFIX`, `_R25` and `_BETA` ([../hal/lx_ntc.h](../hal/lx_ntc.h)).
- **Storage:** the last 256 bytes of flash (four 64-byte pages, see `link.ld`) emulate the
  EEPROM; a changed page is erased and written again. The parameters, the calibration and the
  lockout/memory record are in different pages, so the frequent state saves never touch the
  calibration. Known limitation: every state save erases its page, and flash has a limited
  number of erase cycles (see the datasheet); a wear-levelling log is planned.
- **Brown-out:** the chip's built-in power-on and power-down reset.
- **Watchdog:** independent watchdog, 4 s.
- **Start-up:** `startup.S` (vector table with absolute addresses, `mtvec` mode 3), `link.ld`.
- **Toolchain:** `riscv64-unknown-elf-gcc` 13 (Ubuntu package `gcc-riscv64-unknown-elf`) with
  `-march=rv32ec_zicsr -mabi=ilp32e`.

## esp32c3

The ESP32-C3 port runs the FlashKa keychain light under ESP-IDF 5.x: v0.5 with one button, and
v0.6 with three buttons on a resistor ladder (one pin measures the ladder with the ADC, a second
pin on the same net wakes the chip), of which LuxLibre uses the main button. How a board declares
a ladder: [docs/firmware/porting.md](../../docs/firmware/porting.md#resistor-ladder-buttons-esp32-c3).
See [esp32c3/README.md](esp32c3/README.md) for building and its limitations; the ladder path is
untested on hardware.
