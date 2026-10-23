// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EDCO-14 v0.2 (LuxLibre reference design #2, hardware/edco-v02/), one 14500 cell, Ø20 x 95.6 mm.
//
// EDCO v0.2: a round, sealed EDC light without laser or radio; USB-C on the side of the head under a twist
// collar, the only way in (charging, firmware, settings over the ESP32-C3's USB serial/JTAG port).
// LED: Luminus SST-40-W Gen 2 (5 x 5 mm, 6500 K), datasheet maximum 6.0 A DC, under a TIR optic.
// Driver: MPS MP2145GD 6 A synchronous buck (2.8-5.5 V in, 100 % duty mode, QFN-12 2 x 3 mm, high-side limit 7.5-8.1 A) with its 0.6 V FB pin in the LuxLibre current loop (TLV333 op-amp, 10 mOhm sense resistor; VSET divider 1.0 k / 53.6 k from the 3.3 V PWM filter). Below about 3.65 V at the loaded cell the buck sits at 100 % duty and the LED follows the cell (direct drive).
// Cell: Vapcell INR14500 H10: 1000 mAh typical (900 minimum), 10 A continuous, at most 18 mOhm, 14.3 x 49.4 mm, flat top, no protection board; nickel strips welded to both ends.
// Protection: DW01A with a common-drain dual N-MOSFET path of about 15 mOhm in the cell minus (for example AOS AOC4810, or two TI CSD17575Q3 plus a 10 mOhm resistor): over-current trip about 9.3-12 A over the DW01A's 0.14-0.18 V threshold; about 0.5 W in the path at 6 A.
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

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 100 % duty = 6044 mA.
// Level 150 = LX_MAIN_MAX_MA. 95 % of the LED's 6.0 A maximum is above the 80 % of LED-2 (a "Should" rule):
// the 2000 lm target needs it; turbo is timed (TURBO_S) and regulated.
#define LX_OUT_MIN_Q16 12            // level 1 = about 1 mA
#define LX_MAIN_MAX_MA 5000
#define LX_LED_VF0_MV 2750           // SST-40 Gen 2: V = 2.75 V + 0.11 V/A x I (2.9 V at 1.5 A, datasheet typical)
#define LX_LED_RS_MOHM 110
#define LX_DRIVER_EFF_PCT 90         // MP2145 at 5-6 A into about 3.4 V incl. inductor and sense resistor (estimate; MPS curves to be checked)
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
#define LX_ESP_LED_FULL_MA 6044      // current at 100 % duty: 3.3 V x 1.0 k / 54.6 k / 10 mOhm
#define LX_ESP_VBAT_DIV 2
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- defaults: the modes layout for one button ----
#define LX_DEF_UI_STYLE 1            // hold steps Low -> Medium -> High (UI_STYLE 0 = smooth ramp)
#define LX_DEF_RAMP_FLOOR 21         // moonlight about 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 74             // low
#define LX_DEF_MODE_2 104            // medium
#define LX_DEF_MODE_3 132            // high
#define LX_DEF_MEM_LEVEL 74
#define LX_DEF_TURBO_LVL 150         // turbo = LX_MAIN_MAX_MA
#define LX_DEF_TURBO_S 45
#define LX_DEF_TURBO_DOWN 132        // back to high after the turbo time
#define LX_DEF_BLINKY 0
#define LX_DEF_LOCK_MOON 0
#define LX_DEF_THM_LIMIT 49           // sensor = head node in the simulator: the body (held) stays below the 48 degC of THM-1
#define LX_DEF_THM_SHUTDN 80
#define LX_DEF_LVP_WARN 3100
#define LX_DEF_LVP_CUT 2900
#define LX_DEF_BAT_RINT 45          // H10 at most 18 mOhm AC, about 25 DC (estimate) + strips + protection path + copper
#define LX_DEF_BAT_MAX_MA 7000       // 70 % of the H10's 10 A (BAT-1)
#define LX_DEF_CHG_MAXLVL 110        // light while USB is connected: about 500 mA
#define LX_BAT_OCV_MV 4200, 4050, 3950, 3860, 3770, 3680, 3610, 3540, 3470, 3380, 3000
#define LX_DEF_BLINK_LVL 74

// ---- LED flux, optic and body model (simulator only: make sim BOARD=edco-v02-14) ----
// SST-40-W Gen 2, 6500 K, G1 bin: minimum flux at Tj 85 degC from the datasheet's correlated-flux table
// (340 lm at 0.7 A, 680 at 1.5 A, 1231 at 3 A, 1836 at 5 A, 2101 at 6 A); below 0.7 A a straight line to zero.
#define LX_LED_LM_MA 0, 350, 700, 1500, 3000, 5000, 6000
#define LX_LED_LM    0, 175, 340, 680, 1231, 1836, 2101
#define LX_OPTIC_PCT 85              // LEDiL FA10888 TINA-RS: efficiency not published, 85 % assumed; its fit over the SST-40 dome is to be checked
// Body from the EDCO v0.2 CAD (hardware/edco-v02/cad/edco_v02_interface.json; 6061 0.896 J/gK, copper 0.385 J/gK):
//  head  = bezel 6.39 g + head insert 4.14 g + band in front of the shoulder 2.42 g = 12.95 g of aluminium
//          (11.60 J/K) + copper LED board 2.88 g (1.11 J/K) = 12.71 J/K; the twist collar (2.98 g) is left out
//  body  = rest of the tube, 20.27 g = 18.16 J/K
//  head to body: tube section over the cell about 120 mm2 (d20 / d15.2, less the flats), 63 mm long,
//                L / (3 k A) = 1.05 K/W, plus the joints: 1.1 K/W
//  body to air: 6740 mm2 plus the bezel fins (about 550 mm2) x 11 W/m2K = 12.5 K/W
//  Sensor lag 4 s: the NTC sits on the main board 1-2 mm behind the head insert.
#define LX_SIM_CAPACITY_MAH 950
#define LX_SIM_RINT_MOHM 30
#define LX_SIM_C_HEAD_MJ 12710       // mJ/K
#define LX_SIM_C_BODY_MJ 18160       // mJ/K
#define LX_SIM_R_HEAD_BODY_MK 1100   // mK/W
#define LX_SIM_R_BODY_AMB_MK 12500   // mK/W
#define LX_SIM_SENSOR_TAU_MS 4000
#define LX_SIM_DROP_MOHM 55          // cell terminal to LED at 100 % duty: high-side switch 20 + inductor 8 + sense 10 + protection path 15 + strips 2 (mOhm, estimate)
#define LX_SIM_OCV_V 2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20
#if LX_MAIN_MAX_MA > LX_ESP_LED_FULL_MA
#error "LX_MAIN_MAX_MA above the driver's full scale"
#endif
