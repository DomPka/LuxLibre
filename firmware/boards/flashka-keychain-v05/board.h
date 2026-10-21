// SPDX-License-Identifier: GPL-3.0-or-later
// Board: FlashKa Keychain v0.5 (LuxLibre reference design #1, hardware/flashka-keychain-v05/).
//
// ESP32-C3-MINI-1 module, TLV62585 buck with a cascaded current loop (TLV333 + 20 mOhm sense)
// driving a Luminus SST-20 on a 10 mm DTP board, TP4057 USB-C charger, common-anode RGB status
// LED, 520 nm Class 2 laser behind the slide-switch interlock S2, NTC 100 k B4250 next to the
// LED driver, two LP601646 LiPo cells in parallel (~800 mAh). Pin map = tools/kicad/aurora_parts.py
// of the v0.5 package (the design files still carry the working name "Aurora").
#pragma once

#define LX_BOARD_NAME "FlashKa Keychain v0.5"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1
#define LX_HAS_LASER 1
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 8191 counts = 3235 mA.
// LuxLibre full scale is limited to 2200 mA (the v0.5 "Extreme" turbo).
#define LX_OUT_MIN_Q16 30            // level 1 = 1 mA
#define LX_MAIN_MAX_MA 2200
#define LX_LED_VF0_MV 2750           // SST-20: V = 2.75 V + 0.15 V/A x I (v0.5 firmware model)
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 90

// ---- ESP32-C3 pin map (GPIO numbers) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_BTN 3            // low = pressed
#define LX_ESP_GPIO_CHG_STAT 4       // TP4057 CHRG, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // TP4057 STDBY, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // active low (strap pin)
#define LX_ESP_GPIO_LASER 10         // high = laser on, if S2 is armed (100 k pull-down)
#define LX_ESP_GPIO_CHG_SET 20       // low = ~300 mA, floating = 10 mA trickle, high = off
#define LX_ESP_GPIO_RGB_R 21         // active low (U0TXD: the ROM boot log flickers it)
#define LX_ESP_LED_FULL_MA 3235      // current at 100 % duty
#define LX_ESP_VBAT_DIV 2            // VBAT = 2 x ADC voltage
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- defaults = the v0.5 "Balanced" profile and button layout ----
#define LX_DEF_UI_STYLE 1            // modes: hold steps Low -> Medium -> High
#define LX_DEF_PREVIEW 0             // the laser gesture must not flash the main LED
#define LX_DEF_RAMP_FLOOR 22         // moon 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 67             // low 30 mA
#define LX_DEF_MODE_2 103            // medium ~200 mA
#define LX_DEF_MODE_3 125            // high ~600 mA
#define LX_DEF_MEM_LEVEL 67
#define LX_DEF_TURBO_LVL 138         // turbo ~1200 mA (150 = 2200 mA, the "Extreme" profile)
#define LX_DEF_TURBO_S 60
#define LX_DEF_TURBO_DOWN 125
#define LX_DEF_BLINKY 0              // no beacon / SOS / strobe on a keychain light
#define LX_DEF_LOCK_MOON 0           // lockout stays dark (pocket)
#define LX_DEF_THM_LIMIT 50
#define LX_DEF_THM_SHUTDN 80
#define LX_DEF_LVP_WARN 3350
#define LX_DEF_LVP_CUT 3000
#define LX_DEF_BAT_RINT 120
#define LX_DEF_BAT_MAX_MA 1120       // 70 % of two 2C cells (2 x 0.8 A, BAT-1); 1680 with 3C cells
#define LX_DEF_CHG_MAXLVL 125
#define LX_DEF_BLINK_LVL 67
