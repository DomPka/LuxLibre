// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EXAMPLE - CH32V003 with a regulated buck LED driver.
//
// A template for a low-cost regulated driver: the CH32V003 (~$0.13) runs from the cell,
// PD2 (TIM1 CH1) PWM is filtered into the current set point of a buck driver whose enable
// pin is PC3, an NTC (100 k, B 4250) with 100 k to VDD sits on PA2 (A0), the e-switch pulls
// PC1 to ground. Copy this folder for a real board; see docs/firmware/porting.md.
#pragma once

#define LX_BOARD_NAME "example CH32V003 buck"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // emulated in flash (link.ld)
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

#define LX_OUT_MIN_Q16 64            // 1/1023 duty -> lowest stable current set point
#define LX_MAIN_MAX_MA 3000          // buck full scale (for the cell-current estimate)
#define LX_LED_VF0_MV 2800
#define LX_LED_RS_MOHM 120
#define LX_DRIVER_EFF_PCT 90

// CH32V003 port options (these are also the port's defaults)
#define LX_CH32_BTN_PORT CH_GPIOC_BASE
#define LX_CH32_BTN_PORTSEL 2u
#define LX_CH32_BTN_PIN 1u
#define LX_CH32_EN_PORT CH_GPIOC_BASE
#define LX_CH32_EN_PIN 3u
#define LX_CH32_NTC_ADC_CH 0
#define LX_CH32_NTC_PORT CH_GPIOA_BASE
#define LX_CH32_NTC_PIN 2u
#define LX_CH32_NTC_RFIX 100000L
#define LX_CH32_NTC_R25 100000L
#define LX_CH32_NTC_BETA 4250L

#define LX_DEF_THM_LIMIT 50
#define LX_DEF_BAT_MAX_MA 8000       // stay within a typical high-drain cell
