// SPDX-License-Identifier: GPL-3.0-or-later
// Board: simulated light for the PC build (tests and the simulator).
// A current-regulated driver with an RGB indicator, a laser, side lights, a charger and an NTC, so
// every feature of the core is exercised. The physics live in ports/host/sim.cpp.
#pragma once

#define LX_BOARD_NAME "host simulator (full)"
#define LX_HOST_SIM_BOARD 1        // luxsim keeps the presets' own LED models
#define LX_HAS_CONSOLE 1
#define LX_HAS_AUX_RGB 1
#define LX_HAS_LASER 1
#define LX_HAS_SIDE 1              // red and UV side lights
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1
#define LX_STORAGE_SIZE 256

#define LX_OUT_MIN_Q16 30          // 1 mA of 2200 mA
#define LX_MAIN_MAX_MA 2200
#define LX_LED_VF0_MV 2750
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 90
