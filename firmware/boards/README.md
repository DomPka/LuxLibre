<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../../README.md) › [Firmware](../README.md) › Boards

# Board headers

One folder per light. Its `board.h` says everything the firmware needs to know about that light: the pins, the LED
and driver, the current and temperature limits, the default settings and, for the simulator, the thermal and battery
model. Build any of them with `make sim BOARD=<folder>` (the simulator) or for its microcontroller
([porting guide](../../docs/firmware/porting.md)).

| Board | Light | Microcontroller |
|---|---|---|
| [edco-prism](edco-prism/board.h) | [EDCO Prism](../../hardware/edco-prism/README.md): white and colour beam, RGB button | ESP32-C3 |
| [edco-mini-16](edco-mini-16/board.h) | [EDCO Mini-16](../../hardware/edco-mini/README.md): red and UV side lights | ESP32-C3 |
| [edco-mini-14](edco-mini-14/board.h) | [EDCO Mini-14](../../hardware/edco-mini/README.md) | ESP32-C3 |
| [edco-v02-18](edco-v02-18/board.h) | [EDCO-18 (v0.2)](../../hardware/edco-v02/README.md) | ESP32-C3 |
| [edco-v02-14](edco-v02-14/board.h) | [EDCO-14 (v0.2)](../../hardware/edco-v02/README.md) | ESP32-C3 |
| [edco-v01](edco-v01/board.h) | [EDCO v0.1](../../hardware/edco-v01/README.md) | ESP32-C3 |
| [flashka-keychain-v07](flashka-keychain-v07/board.h) | [FlashKa v0.7](../../hardware/flashka-keychain-v07/README.md) (an alternative to its own Rust firmware) | ESP32-C3 |
| [flashka-keychain-v06](flashka-keychain-v06/board.h) | [FlashKa v0.6](../../hardware/flashka-keychain-v06/README.md) | ESP32-C3 |
| [flashka-keychain-v05](flashka-keychain-v05/board.h) | [FlashKa v0.5](../../hardware/flashka-keychain-v05/README.md) | ESP32-C3 |
| [example-tiny1616-pwm](example-tiny1616-pwm/board.h) | example: one LED channel with PWM | ATtiny1616 |
| [example-ch32v003-buck](example-ch32v003-buck/board.h) | example: a regulated buck driver | CH32V003 |
| [host-sim](host-sim/board.h), [host-sim-basic](host-sim-basic/board.h), [host-sim-color](host-sim-color/board.h) | simulated lights for the tests | PC |
