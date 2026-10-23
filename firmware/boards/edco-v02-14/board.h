// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EDCO-14 v0.2 (LuxLibre reference design #2, hardware/edco-v02/), one 14500 cell, Ø20 x 95.3 mm.
//
// EDCO v0.2: a round, sealed EDC light without laser or radio; USB-C on the side of the head under a twist
// collar, the only way in (charging, firmware, settings over the ESP32-C3's USB serial/JTAG port).
// LED: Luminus SST-40-W Gen 2 (5 x 5 mm, 6500 K), datasheet maximum 6.0 A DC, under a TIR optic.
// Driver: ASSUMED (to be replaced): 6 A synchronous buck with 100 % duty mode in the LuxLibre current loop.
// Cell: ASSUMED 14500, 1000 mAh, 10 A
// Protection: ASSUMED: DW01A-type IC with a low-resistance dual MOSFET.
// One button (stainless cap on a sealed, translucent membrane) on GPIO3; the RGB indicator lights the membrane
// from below (halo). Charger TP4057 at about 500 mA. NTC 100 k B4250 on the main board next to the head insert.
// The pin map below is the planned one: confirm it against the schematic when the boards are drawn.
#pragma once

#define LX_BOARD_NAME "EDCO-14 v0.2"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1             // halo under the button membrane
#define LX_HAS_LASER 0
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 100 % duty = 6000 mA.
// Level 150 = LX_MAIN_MAX_MA. 95 % of the LED's 6.0 A maximum is above the 80 % of LED-2 (a "Should" rule):
// the 2000 lm target needs it; turbo is timed (TURBO_S) and regulated.
#define LX_OUT_MIN_Q16 12            // level 1 = about 1 mA
#define LX_MAIN_MAX_MA 4500
#define LX_LED_VF0_MV 2750           // SST-40 Gen 2: V = 2.75 V + 0.11 V/A x I (2.9 V at 1.5 A, datasheet typical)
#define LX_LED_RS_MOHM 110
#define LX_DRIVER_EFF_PCT 92         // assumed
#if LX_MAIN_MAX_MA * 105 > 6000 * 100
#error "EDCO v0.2: with the current loop's 5 % worst-case tolerance LX_MAIN_MAX_MA must stay at or below 5714"
#endif

// ---- ESP32-C3FH4 pin map (as EDCO v0.1) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // halo blue, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_BTN 3            // low = pressed (internal pull-up), wake-up
#define LX_ESP_GPIO_CHG_STAT 4       // TP4057 CHRG, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // TP4057 STDBY, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // halo green, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_CHG_SET 20       // low = ~500 mA, floating = 10 mA trickle, high = off
#define LX_ESP_GPIO_RGB_R 21         // halo red, active low
#define LX_ESP_LED_FULL_MA 6000      // current at 100 % duty: assumed
#define LX_ESP_VBAT_DIV 2
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- defaults: the modes layout for one button ----
#define LX_DEF_UI_STYLE 1            // hold steps Low -> Medium -> High (UI_STYLE 0 = smooth ramp)
#define LX_DEF_RAMP_FLOOR 22         // moonlight about 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 75             // low
#define LX_DEF_MODE_2 106            // medium
#define LX_DEF_MODE_3 134            // high
#define LX_DEF_MEM_LEVEL 75
#define LX_DEF_TURBO_LVL 150         // turbo = LX_MAIN_MAX_MA
#define LX_DEF_TURBO_S 45
#define LX_DEF_TURBO_DOWN 134        // back to high after the turbo time
#define LX_DEF_BLINKY 0
#define LX_DEF_LOCK_MOON 0
#define LX_DEF_THM_LIMIT 49           // assumed
#define LX_DEF_THM_SHUTDN 80
#define LX_DEF_LVP_WARN 3100
#define LX_DEF_LVP_CUT 2900
#define LX_DEF_BAT_RINT 60          // assumed
#define LX_DEF_BAT_MAX_MA 6500       // assumed
#define LX_DEF_CHG_MAXLVL 110        // light while USB is connected: about 500 mA
#define LX_BAT_OCV_MV 4200, 4050, 3950, 3860, 3770, 3680, 3610, 3540, 3470, 3380, 3000
#define LX_DEF_BLINK_LVL 75

// ---- LED flux, optic and body model (simulator only: make sim BOARD=edco-v02-14) ----
// SST-40-W Gen 2, 6500 K, G1 bin: minimum flux at Tj 85 degC from the datasheet's correlated-flux table
// (340 lm at 0.7 A, 680 at 1.5 A, 1231 at 3 A, 1836 at 5 A, 2101 at 6 A); below 0.7 A a straight line to zero.
#define LX_LED_LM_MA 0, 350, 700, 1500, 3000, 5000, 6000
#define LX_LED_LM    0, 175, 340, 680, 1231, 1836, 2101
#define LX_OPTIC_PCT 85              // assumed TIR efficiency
// Body from the EDCO v0.2 CAD (hardware/edco-v02/cad/edco_v02_interface.json; 6061 0.896 J/gK, copper 0.385 J/gK):
//  head  = bezel 6.06 g + head insert 3.50 g + band in front of the shoulder 2.42 g = 11.98 g of aluminium
//          (10.73 J/K) + copper LED board 2.88 g (1.11 J/K) = 11.84 J/K; the twist collar (2.98 g) is left out
//  body  = rest of the tube, 20.30 g = 18.19 J/K
//  head to body: tube section over the cell about 120 mm2 (d20 / d15.2, less the flats), 63 mm long,
//                L / (3 k A) = 1.05 K/W, plus the joints: 1.1 K/W
//  body to air: 6698 mm2 plus the bezel fins (about 550 mm2) x 11 W/m2K = 12.5 K/W
//  Sensor lag 4 s: the NTC sits on the main board 1-2 mm behind the head insert.
#define LX_SIM_CAPACITY_MAH 1000
#define LX_SIM_RINT_MOHM 80
#define LX_SIM_C_HEAD_MJ 11840       // mJ/K
#define LX_SIM_C_BODY_MJ 18190       // mJ/K
#define LX_SIM_R_HEAD_BODY_MK 1100   // mK/W
#define LX_SIM_R_BODY_AMB_MK 12500   // mK/W
#define LX_SIM_SENSOR_TAU_MS 4000
#define LX_SIM_DROP_MOHM 45          // assumed
#define LX_SIM_OCV_V 2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20
#if LX_MAIN_MAX_MA > LX_ESP_LED_FULL_MA
#error "LX_MAIN_MAX_MA above the driver's full scale"
#endif
