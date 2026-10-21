// SPDX-License-Identifier: GPL-3.0-or-later
// Board: FlashKa Keychain v0.6 (LuxLibre reference design, hardware/flashka-keychain-v06/).
//
// The v0.5 board (../flashka-keychain-v05/board.h) with three buttons and an RGB light ring.
// Unchanged: ESP32-C3-MINI-1 module, TLV62585 buck with a cascaded current loop (TLV333 +
// 20 mOhm sense) driving a Luminus SST-20 on a 10 mm DTP board, TP4057 USB-C charger, 520 nm
// Class 2 laser behind the slide-switch interlock S2, NTC 100 k B4250 next to the LED driver,
// two LP601646 LiPo cells in parallel (~800 mAh), and every GPIO except the button. Changed:
//  * the side button S1 is gone; the main button (a stainless cap inside the light ring) and
//    two slide buttons, next and previous, share the net BTN as a resistor ladder (below);
//  * the status LED is now two RGB ring LEDs in parallel on the same three GPIOs (common anode,
//    active low). The red series resistors are 330 Ohm instead of v0.5's 1 k (more red behind
//    the light pipe), green and blue 100 Ohm. LuxLibre has no per-board colour balance, so check
//    the mixed colours (yellow, white) on the bench.
// Pin map = GPIO_MAP in tools/kicad/flashka_parts.py of the v0.6 package.
#pragma once

#define LX_BOARD_NAME "FlashKa Keychain v0.6"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1             // the light ring
#define LX_HAS_LASER 1
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 8191 counts = 3235 mA.
// LuxLibre full scale is limited to 2200 mA (the FlashKa "Extreme" turbo).
#define LX_OUT_MIN_Q16 30            // level 1 = 1 mA
#define LX_MAIN_MAX_MA 2200
#define LX_LED_VF0_MV 2750           // SST-20: V = 2.75 V + 0.15 V/A x I (FlashKa firmware model)
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 90

// ---- ESP32-C3 pin map (GPIO numbers) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // ring blue, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_CHG_STAT 4       // TP4057 CHRG, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // TP4057 STDBY, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // ring green, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_LASER 10         // high = laser on, if S2 is armed (100 k pull-down)
#define LX_ESP_GPIO_CHG_SET 20       // low = ~300 mA, floating = 10 mA trickle, high = off
#define LX_ESP_GPIO_RGB_R 21         // ring red, active low (U0TXD: the ROM boot log flickers it)
#define LX_ESP_LED_FULL_MA 3235      // current at 100 % duty
#define LX_ESP_VBAT_DIV 2            // VBAT = 2 x ADC voltage
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- buttons: resistor ladder on BTN (R9 10 k 1 % pull-up to 3V3) ----
// Main (SW1) shorts BTN to GND; next (SW2) pulls it down through R30 1 k, previous (SW3)
// through R31 2.2 k. BTN reaches two pins: GPIO3 measures it with ADC1 channel 3, GPIO9 (a boot
// strap pin) reads it as a digital input.
//
//   pressed                          BTN       class in the FlashKa firmware (calibrated mV)
//   none                             3.30 V    > 810
//   main (alone or with any other)   0 V       < 106          <- the LuxLibre button
//   previous + next together         0.212 V   106 to < 256
//   next                             0.300 V   256 to < 448
//   previous                         0.595 V   448 to 810
//
// LuxLibre's user interface has one button, so on this board the main button is the button.
// The slide buttons belong to the original FlashKa firmware (level steps while the light is on,
// and its presenter mode: a Bluetooth LE keyboard that turns slides), which LuxLibre does not
// have. They are ignored: every press is a digital low on GPIO9 (all levels are below
// VIL = 0.25 x VDD = 0.825 V) and wakes the chip, the port reads the ladder, and if it was not
// the main button the port sleeps again. Main always wins, because it pulls BTN to 0 V whatever
// else is pressed. 106 mV is the midpoint between main (0 V) and the lowest other level
// (0.212 V), which leaves 106 mV of room on each side for resistor, supply and ADC tolerances.
// The internal pull-ups of GPIO3 and GPIO9 must stay off: in parallel with R9 they would move
// every level (the port switches them off).
#define LX_ESP_BTN_LADDER_ADC_GPIO 3     // ADC1_CH3, read at 2.5 dB (0 to 1050 mV), curve-fitting calibration
#define LX_ESP_BTN_WAKE_GPIO 9           // digital input, internal pull-up off: low = some button; light-sleep wake
#define LX_ESP_BTN_MAIN_BELOW_MV 106     // pressed = calibrated BTN voltage below this

// ---- defaults = the FlashKa "Balanced" profile (as v0.5) and the v0.5 button layout ----
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
