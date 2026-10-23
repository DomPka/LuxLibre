// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EDCO Mini-14 v0.1 (LuxLibre reference design #3, hardware/edco-mini/), Ø17 x 66.0 mm (head Ø19).
//
// EDCO Mini: the small, sealed sister of EDCO v0.2, at most 70 mm long. No laser, no radio; a waterproof USB-C
// socket on the side of the head is the only way in (charging, firmware, settings over the ESP32-C3's USB
// serial/JTAG port). Red and UV side lights shine out of two clear rods in front of the button (LX_HAS_SIDE).
// LED: Luminus SST-20-W Gen 2 (6500 K, G1), datasheet maximum 3.0 A DC, on a 12 mm copper DTP board under a
// Carclo 12079 10 mm IP66 narrow spot (flange Ø12.5, about 6 mm tall).
// Driver: the EDCO v0.1 / FlashKa v0.7 power stage: TPS62095 4 A buck in the TLV333 current loop (20 mOhm sense,
// VSET 2.2 k / 100 k: 100 % duty = 3552 mA), DW01A + SE8830A protection in the cell minus.
// Cell: a made-to-order high-rate LiPo cell, Ø14 x 35 mm, about 400 mAh, 4 A continuous (estimate: no
// off-the-shelf high-drain 14350 was found; see hardware/edco-mini/README.md); nickel strips to both ends.
// Charger: about 500 mA (about 1.25 C of the 400 mAh cell (to be confirmed with the cell maker)): a 1 A single-cell charger in a 2 x 2 mm package (TI BQ24050,
// LCSC C2859551) instead of the 500 mA TP4057; its status and control pins are mapped to CHG_STAT / CHG_DONE /
// CHG_SET when the board is drawn (the HAL may need a small change).
// Side lights: UV Nichia NVSU233B-U365 (365 nm, 3.5 x 3.5 mm) straight from the cell through a P-MOSFET and a
// resistor (about 250 mA on a full cell; the UV output falls as the cell runs down); red: a 2.0 x 1.6 mm power LED
// (627 nm class, about 150 mA) through an N-MOSFET and a resistor.
// One button (stainless cap on a sealed, translucent membrane) on GPIO3; the RGB indicator lights the membrane
// from below (halo). NTC 100 k B4250 on the main board next to the head insert.
// The pin map below is the planned one: confirm it against the schematic when the boards are drawn.
#pragma once

#define LX_BOARD_NAME "EDCO Mini-14 v0.1"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1             // halo under the button membrane
#define LX_HAS_LASER 0
#define LX_HAS_SIDE 1                // red and UV side lights (5 clicks from off)
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 100 % duty = 3552 mA.
// Level 150 = 2850 mA: the LED's 3000 mA maximum less the 5 % worst-case tolerance of the current loop, as in
// EDCO v0.1. 95 % of the LED maximum is above the 80 % of LED-2 (a "Should" rule): turbo is timed and regulated.
#define LX_OUT_MIN_Q16 23            // level 1 = 1 mA
#define LX_MAIN_MAX_MA 2850
#define LX_LED_VF0_MV 2800           // SST-20 Gen 2: V = 2.80 V + 0.15 V/A x I (3.0 V at 1.5 A, datasheet typical)
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 87         // TPS62095 + inductor + sense + protection FETs at 3 A (estimate)
#if LX_MAIN_MAX_MA * 105 > 3000 * 100
#error "EDCO Mini: with the current loop's 5 % worst-case tolerance LX_MAIN_MAX_MA must stay at or below 2857"
#endif

// ---- ESP32-C3FH4 pin map (EDCO v0.1 + the side lights) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // halo blue, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_BTN 3            // low = pressed (internal pull-up), wake-up
#define LX_ESP_GPIO_CHG_STAT 4       // charger status, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // charger status, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // halo green, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_SIDE_UV 9        // UV side light: P-MOSFET, on when low; the strap pin's pull-up keeps it off at reset
#define LX_ESP_SIDE_UV_ACTIVE_LOW 1
#define LX_ESP_GPIO_SIDE_RED 10      // red side light: N-MOSFET, on when high (100 k pull-down)
#define LX_ESP_GPIO_CHG_SET 20       // charger control: low = charge, floating = trickle, high = off (as EDCO v0.1)
#define LX_ESP_GPIO_RGB_R 21         // halo red, active low
#define LX_ESP_LED_FULL_MA 3552      // current at 100 % duty: 3.3 V x 2.2 k / 102.2 k / 20 mOhm
#define LX_ESP_VBAT_DIV 2
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- defaults: the modes layout for one button (the EDCO v0.1 levels) ----
#define LX_DEF_UI_STYLE 1            // hold steps Low -> Medium -> High (UI_STYLE 0 = smooth ramp)
#define LX_DEF_RAMP_FLOOR 22         // moon 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 70             // low 40 mA
#define LX_DEF_MODE_2 104            // medium 244 mA
#define LX_DEF_MODE_3 138            // high 1501 mA
#define LX_DEF_MEM_LEVEL 70
#define LX_DEF_TURBO_LVL 150         // turbo 2850 mA
#define LX_DEF_TURBO_S 45
#define LX_DEF_TURBO_DOWN 138        // back to high after the turbo time
#define LX_DEF_BLINKY 0              // beacon / SOS / strobe off by default (BLINKY over USB: 4 = strobe after the battery check)
#define LX_DEF_LOCK_MOON 0
#define LX_DEF_THM_LIMIT 48          // sensor = head node in the simulator: the body (held) stays below 48 degC (THM-1)
#define LX_DEF_THM_LEAD 10           // a small body heats fast: the regulator looks 10 s ahead (at 4 s it swings 70-330 lm)
#define LX_DEF_THM_SHUTDN 80
#define LX_DEF_LVP_WARN 3200
#define LX_DEF_LVP_CUT 3000
#define LX_DEF_BAT_RINT 90           // cell about 40 mOhm (estimate) + strips + protection FETs + copper
#define LX_DEF_BAT_MAX_MA 2800       // 70 % of the cell's 4 A (BAT-1; the cell is an estimate until it is ordered)
#define LX_DEF_CHG_MAXLVL 121        // light while USB is connected: about 600 mA
#define LX_BAT_OCV_MV 4200, 4050, 3950, 3860, 3770, 3680, 3610, 3540, 3470, 3380, 3000
#define LX_DEF_BLINK_LVL 70
#define LX_DEF_SIDE_RED 60           // % of the red side light
#define LX_DEF_SIDE_UV 100           // % of the UV side light

// ---- LED flux, optic and body model (simulator only: make sim BOARD=edco-mini-14) ----
// SST-20 Gen 2 6500 K G1 at Tj 85 degC (the EDCO v0.1 table): 190 lm at 0.35 A, 354 at 0.7 A, 680 at 1.5 A,
// 857 at 2 A, 1156 at 3 A are the datasheet's correlated bin minima; 1.0 A is interpolated.
#define LX_LED_LM_MA 0, 350, 700, 1000, 1500, 2000, 3000
#define LX_LED_LM    0, 190, 354, 485, 680, 857, 1156
#define LX_OPTIC_PCT 88              // Carclo 12079: 88-93 % with XP-G-class LEDs (datasheet); 88 % assumed for the SST-20
// Body from the EDCO Mini CAD (hardware/edco-mini/cad/edco_mini_interface.json; 6061 0.896 J/gK, copper 0.385 J/gK):
//  head  = bezel 2.73 g + head insert 2.78 g + body in front of the step (head section, band) 3.70 g = 9.21 g of
//          aluminium (8.25 J/K) + copper LED board 1.22 g (0.47 J/K) = 8.72 J/K
//  body  = the tube behind the step, 6.44 g = 5.77 J/K (sled, board, button and cell not counted; the cell's
//          heat capacity is weakly coupled through its 0.5 mm air gap)
//  head to body: one piece of aluminium; tube section 47 mm2 (d17 / d15, less the flats), 39.5 mm long,
//                L / (3 k A) = 1.66 K/W, 1.7 K/W
//  body to air: 4102 mm2 plus the bezel fins (about 130 mm2) x 11 W/m2K = 21.5 K/W
//  Sensor lag 4 s: the NTC sits on the main board 1-2 mm behind the head insert.
#define LX_SIM_CAPACITY_MAH 380
#define LX_SIM_RINT_MOHM 85
#define LX_SIM_C_HEAD_MJ 8720        // mJ/K
#define LX_SIM_C_BODY_MJ 5770        // mJ/K
#define LX_SIM_R_HEAD_BODY_MK 1700    // mK/W
#define LX_SIM_R_BODY_AMB_MK 21500   // mK/W
#define LX_SIM_SENSOR_TAU_MS 4000
#define LX_SIM_DROP_MOHM 128         // battery (under load) to LED at 100 % duty (as EDCO v0.1)
#define LX_SIM_OCV_V 2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20
#define LX_SIM_CHARGE_MA 500       // charge current (constant until 90 %, then tapering: a rough CC/CV)
#define LX_SIM_MCU_UA 10000         // ESP32-C3 at 80 MHz idling between 10 ms ticks (no automatic light sleep while on), regulator
                                     // and op-amp: about 10 mA (estimate from Espressif's modem-sleep figures); asleep 0.3 mA
#define LX_SIM_SIDE_UV_MW 1000       // UV side light at full duty: about 250 mA from the cell
#define LX_SIM_SIDE_RED_MW 500       // red side light at full duty: about 150 mA from the cell
#if LX_MAIN_MAX_MA > LX_ESP_LED_FULL_MA
#error "LX_MAIN_MAX_MA above the driver's full scale"
#endif
