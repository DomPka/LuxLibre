// SPDX-License-Identifier: GPL-3.0-or-later
// Board: simulated light with a colour beam for the PC build (tests of LX_HAS_COLOR).
// A current-regulated white channel plus red, green and blue LEDs on linear sinks, an RGB
// indicator, a charger, an NTC and the console; no side lights and no laser, so that five
// clicks from off turn on the colour beam.
#pragma once

#define LX_BOARD_NAME "host simulator (colour beam)"
#define LX_HOST_SIM_BOARD 1        // luxsim keeps the presets' own LED models
#define LX_HAS_CONSOLE 1
#define LX_HAS_AUX_RGB 1
#define LX_HAS_COLOR 1
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1
#define LX_STORAGE_SIZE 256

#define LX_OUT_MIN_Q16 30          // 1 mA of 2200 mA
#define LX_MAIN_MAX_MA 2200
#define LX_LED_VF0_MV 2750
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 90
#define LX_COLOR_FULL_MA 1200      // sink current at the full set point
#define LX_COLOR_MAX_MA 1000       // most a colour LED gets
