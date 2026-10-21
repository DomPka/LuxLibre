// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EXAMPLE - ATtiny1616 driving one LED channel with PWM.
//
// A template for the classic single-cell enthusiast driver: the MCU runs straight from the
// Li-ion cell (1.8-5.5 V), an e-switch pulls PA2 to ground, and PB0 (TCA0 WO0) switches the
// LED through a logic-level N-MOSFET (FET drive) or enables a linear current regulator.
// Copy this folder for a real board and change the pins and limits; see docs/firmware/porting.md.
#pragma once

#define LX_BOARD_NAME "example ATtiny1616 PWM"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // EEPROM
#define LX_HAS_TEMP 1                // internal temperature sensor of the MCU
#define LX_BAT_CELLS 1

#define LX_OUT_MIN_Q16 64            // 1/1023 duty cycle
#define LX_MAIN_MAX_MA 0             // FET drive: current not known

// ATtiny1616 port options
#define LX_TINY_PWM_WO 0             // TCA0 WO0 = PB0
#define LX_TINY_BTN_PIN 2            // PA2 (e-switch to GND, internal pull-up)
#define LX_TINY_TEMP_OFFSET_DC 0     // calibrate: sensor vs. hottest touchable point

// FET drive has no current regulation: keep turbo short and the thermal limit modest.
#define LX_DEF_TURBO_S 45
#define LX_DEF_THM_LIMIT 50
#define LX_DEF_RAMP_CEIL 120
