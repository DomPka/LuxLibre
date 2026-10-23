// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - board configuration.
//
// Includes the board header of the build ("board.h", found through the include path
// boards/<board>/) and fills in defaults for everything the board does not define.
// See docs/firmware/porting.md for the meaning of every LX_ macro.
#pragma once

#include "board.h"

#ifndef LX_BOARD_NAME
#error "board.h must define LX_BOARD_NAME"
#endif

// --- timing and storage -------------------------------------------------------
#ifndef LX_TICK_MS
#define LX_TICK_MS 10            // main loop period
#endif
#ifndef LX_STORAGE_SIZE
#define LX_STORAGE_SIZE 256      // bytes of EEPROM (or emulated EEPROM) for settings, at least 256
#endif

// --- optional hardware ----------------------------------------------------------
#ifndef LX_HAS_CONSOLE
#define LX_HAS_CONSOLE 0         // text console over USB/UART (parameters, status)
#endif
#ifndef LX_HAS_AUX_RGB
#define LX_HAS_AUX_RGB 0         // RGB or single-colour indicator LED
#endif
#ifndef LX_HAS_LASER
#define LX_HAS_LASER 0           // laser module with hardware interlock
#endif
#ifndef LX_HAS_SIDE
#define LX_HAS_SIDE 0            // side lights: a red and a UV LED shining out of the side
#endif
#ifndef LX_HAS_CHARGER
#define LX_HAS_CHARGER 0         // on-board charger with status signals
#endif
#ifndef LX_HAS_TEMP
#define LX_HAS_TEMP 1            // temperature sensor (NTC or MCU internal)
#endif
#ifndef LX_BAT_CELLS
#define LX_BAT_CELLS 1
#endif

// --- main channel ------------------------------------------------------------------
// Power (Q16) at level 1. Pick the lowest output that is still stable and visible:
// for a current-regulated driver e.g. 1 mA of a 2 A full scale -> 65535 * 1 / 2000 = 33;
// for plain PWM the smallest usable duty cycle (1/1023 of 10-bit PWM -> 64).
#ifndef LX_OUT_MIN_Q16
#define LX_OUT_MIN_Q16 64
#endif
// Full-scale LED current in mA (0 = unknown, e.g. FET direct drive). Used for the cell
// current limit, the runtime estimate and the documentation tables.
#ifndef LX_MAIN_MAX_MA
#define LX_MAIN_MAX_MA 0
#endif
// LED forward voltage model V = LX_LED_VF0_MV + LX_LED_RS_MOHM * I and driver efficiency,
// used to estimate the cell current from the LED current.
#ifndef LX_LED_VF0_MV
#define LX_LED_VF0_MV 2750
#endif
#ifndef LX_LED_RS_MOHM
#define LX_LED_RS_MOHM 150
#endif
#ifndef LX_DRIVER_EFF_PCT
#define LX_DRIVER_EFF_PCT 90
#endif

// --- defaults of user parameters (a board may override any of them) -------------------
#ifndef LX_DEF_UI_STYLE
#define LX_DEF_UI_STYLE 0        // 0 = ramp, 1 = modes, 2 = simple
#endif
#ifndef LX_DEF_PREVIEW
#define LX_DEF_PREVIEW 1
#endif
#ifndef LX_DEF_RAMP_FLOOR
#define LX_DEF_RAMP_FLOOR 1
#endif
#ifndef LX_DEF_RAMP_CEIL
#define LX_DEF_RAMP_CEIL 120
#endif
#ifndef LX_DEF_MODE_CNT
#define LX_DEF_MODE_CNT 4
#endif
#ifndef LX_DEF_MODE_1
#define LX_DEF_MODE_1 30
#endif
#ifndef LX_DEF_MODE_2
#define LX_DEF_MODE_2 70
#endif
#ifndef LX_DEF_MODE_3
#define LX_DEF_MODE_3 100
#endif
#ifndef LX_DEF_MODE_4
#define LX_DEF_MODE_4 120
#endif
#ifndef LX_DEF_MODE_5
#define LX_DEF_MODE_5 140
#endif
#ifndef LX_DEF_MEM_LEVEL
#define LX_DEF_MEM_LEVEL 70
#endif
#ifndef LX_DEF_TURBO_LVL
#define LX_DEF_TURBO_LVL 150
#endif
#ifndef LX_DEF_TURBO_S
#define LX_DEF_TURBO_S 60
#endif
#ifndef LX_DEF_TURBO_DOWN
#define LX_DEF_TURBO_DOWN 120
#endif
#ifndef LX_DEF_BLINKY
#define LX_DEF_BLINKY 3          // beacon + SOS; strobe off by default
#endif
#ifndef LX_DEF_LOCK_MOON
#define LX_DEF_LOCK_MOON 1
#endif
#ifndef LX_DEF_AUX_MODE
#define LX_DEF_AUX_MODE (LX_HAS_AUX_RGB ? 2 : 0)
#endif
#ifndef LX_DEF_POCKET_S
#define LX_DEF_POCKET_S 30       // see docs/design-rules.md (BAT-7, pocket safety)
#endif
#ifndef LX_DEF_THM_LIMIT
#define LX_DEF_THM_LIMIT 50      // see docs/design-rules.md (touch temperature)
#endif
#ifndef LX_DEF_THM_SHUTDN
#define LX_DEF_THM_SHUTDN 75
#endif
#ifndef LX_DEF_THM_KP
#define LX_DEF_THM_KP 20         // 2.0 levels per degree
#endif
#ifndef LX_DEF_THM_KI
#define LX_DEF_THM_KI 8          // 0.8 levels per degree-second
#endif
#ifndef LX_DEF_THM_LEAD
#define LX_DEF_THM_LEAD 4        // seconds
#endif
#ifndef LX_DEF_THM_FLOOR
#define LX_DEF_THM_FLOOR 60
#endif
#ifndef LX_DEF_LVP_WARN
#define LX_DEF_LVP_WARN 3200     // mV per cell under load
#endif
#ifndef LX_DEF_LVP_CUT
#define LX_DEF_LVP_CUT 2900
#endif
#ifndef LX_DEF_BAT_RINT
#define LX_DEF_BAT_RINT 80       // mOhm (cell + springs)
#endif
#ifndef LX_DEF_BAT_MAX_MA
#define LX_DEF_BAT_MAX_MA 0      // 0 = no cell current limit
#endif
#ifndef LX_DEF_CHG_MAXLVL
#define LX_DEF_CHG_MAXLVL 100
#endif
#ifndef LX_DEF_BLINK_LVL
#define LX_DEF_BLINK_LVL 60
#endif
#ifndef LX_DEF_SIDE_RED
#define LX_DEF_SIDE_RED 40       // % of the red side light's full output
#endif
#ifndef LX_DEF_SIDE_UV
#define LX_DEF_SIDE_UV 100       // % of the UV side light's full output (0 = no UV)
#endif

static_assert(LX_TICK_MS >= 1 && LX_TICK_MS <= 50, "LX_TICK_MS out of range");
static_assert(LX_OUT_MIN_Q16 >= 1 && LX_OUT_MIN_Q16 < 32768, "LX_OUT_MIN_Q16 out of range");
static_assert(LX_STORAGE_SIZE >= 256, "need at least 256 bytes of storage");
static_assert(LX_DRIVER_EFF_PCT > 0 && LX_DRIVER_EFF_PCT <= 100, "LX_DRIVER_EFF_PCT = LED power / input power x 100");
static_assert(LX_MAIN_MAX_MA >= 0 && LX_MAIN_MAX_MA <= 60000, "LX_MAIN_MAX_MA out of range");
