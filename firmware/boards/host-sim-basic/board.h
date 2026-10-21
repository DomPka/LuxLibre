// SPDX-License-Identifier: GPL-3.0-or-later
// Board: simulated minimal light for the PC build - PWM FET channel, no indicator LED,
// no laser, no charger, no console. Tests that the core works with the bare minimum.
#pragma once

#define LX_BOARD_NAME "host simulator (basic)"
#define LX_HAS_TEMP 1
#define LX_STORAGE_SIZE 256
#define LX_OUT_MIN_Q16 64          // 1/1023 PWM
