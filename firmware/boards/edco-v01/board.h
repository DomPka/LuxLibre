// SPDX-License-Identifier: GPL-3.0-or-later
// Board: EDCO v0.1 (LuxLibre reference design #2, hardware/edco-v01/).
//
// A round, sealed EDC light: Ø20 x 93.5 mm 6061 tube with a closed tail, the head and bezel ring screwed on
// for good, one 14500 cell. The electronics are the FlashKa v0.7 power stage without the laser and without the
// radio: an ESP32-C3FH4 chip (no antenna; the radio is never started) whose USB serial/JTAG port is the only
// way in - firmware updates and settings both go through the USB-C socket in the tail.
// Same as FlashKa v0.7: SST-20 Gen 2 (6500 K, G1) on a 10 mm copper DTP board behind a LEDiL LISA3-RS-PIN,
// TPS62095 4 A buck in the TLV333 current loop (100 % duty = 3552 mA), DW01A + SE8830A protection in the cell
// minus, TP4057 at 500 mA, NTC 100 k B4250 on the main board next to the head, Vapcell INR14500 F15.
// Changed: ONE digital button (stainless cap on a sealed membrane, Alps SKRK on the main board) on GPIO3 as on
// FlashKa v0.5; ONE RGB indicator LED under a PMMA light pipe next to the button (same pins as the v0.7 ring);
// no laser; the USB-C socket sits on a tail board joined to the main board by a 4-wire flex.
// The pin map below is the planned one: confirm it against the EDCO schematic when the boards are drawn.
#pragma once

#define LX_BOARD_NAME "EDCO v0.1"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1             // indicator under the light pipe
#define LX_HAS_LASER 0               // EDCO has no laser
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 100 % duty = 3552 mA.
// LuxLibre full scale (level 150) is 2850 mA, the FlashKa v0.7 turbo: the LED's 3000 mA maximum
// less the 5 % worst-case tolerance of the current loop (3.3 V rail, divider, sense resistor), so
// the LED never sees more than 3.0 A. 95 % of the LED maximum is above the 80 % of LED-2 (a
// "Should" rule): the 1000 lm target needs it; turbo is timed (TURBO_S) and regulated.
#define LX_OUT_MIN_Q16 23            // level 1 = 1 mA
#define LX_MAIN_MAX_MA 2850
#define LX_LED_VF0_MV 2800           // SST-20 Gen 2: V = 2.80 V + 0.15 V/A x I (3.0 V at 1.5 A, datasheet typical)
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 87         // TPS62095 + inductor + sense + protection FETs at 3 A (estimate)
#if LX_MAIN_MAX_MA > 3000
#error "EDCO v0.1: the SST-20 Gen 2 is rated for 3.0 A DC; LX_MAIN_MAX_MA must not exceed 3000"
#endif
#if LX_MAIN_MAX_MA * 105 > 3000 * 100
#error "EDCO v0.1: with the current loop's 5 % worst-case tolerance LX_MAIN_MAX_MA must stay at or below 2857"
#endif

// ---- ESP32-C3FH4 pin map (GPIO numbers; the v0.7 map with a digital button and no laser) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2 (measured against GND = P-, below the protection FETs)
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // indicator blue, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_BTN 3            // low = pressed (internal pull-up), light-sleep wake-up
#define LX_ESP_GPIO_CHG_STAT 4       // TP4057 CHRG, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // TP4057 STDBY, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // indicator green, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_CHG_SET 20       // low = ~500 mA (R3 2.0 k), floating = 10 mA trickle, high = off
#define LX_ESP_GPIO_RGB_R 21         // indicator red, active low (U0TXD: the ROM boot log flickers it)
#define LX_ESP_LED_FULL_MA 3552      // current at 100 % duty: 3.3 V x 2.2 k / 102.2 k / 20 mOhm
#define LX_ESP_VBAT_DIV 2            // VBAT = 2 x ADC voltage
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- defaults = the FlashKa v0.7 "Balanced" levels, the modes layout for one button ----
#define LX_DEF_UI_STYLE 1            // modes: hold steps Low -> Medium -> High (UI_STYLE 0 = smooth ramp)
#define LX_DEF_RAMP_FLOOR 22         // moon 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 70             // low 40 mA (19 lm out of the front)
#define LX_DEF_MODE_2 104            // medium 244 mA (FlashKa: 250 mA, 119 lm)
#define LX_DEF_MODE_3 138            // high 1501 mA (592 lm; FlashKa: 1530 mA, 601 lm; level 139 = 1583 mA)
#define LX_DEF_MEM_LEVEL 70
#define LX_DEF_TURBO_LVL 150         // turbo 2850 mA (966 lm out of the front, LED model at Tj 85 degC)
#define LX_DEF_TURBO_S 60
#define LX_DEF_TURBO_DOWN 138        // back to high after the turbo time
#define LX_DEF_BLINKY 0              // beacon / SOS / strobe off by default (can be enabled over USB)
#define LX_DEF_LOCK_MOON 0           // lockout stays dark (pocket)
#define LX_DEF_THM_LIMIT 49          // sensor = head node in the simulator: the body (held) settles at 47.5 degC (THM-1: <= 48);
                                     // at 50 the round tube (lower head-to-body resistance than FlashKa) would settle at 48.4 degC
#define LX_DEF_THM_SHUTDN 80
#define LX_DEF_LVP_WARN 3200         // the F15 (3.6 V nominal) still holds 5-10 % here under load; 3350 would waste 15 %
#define LX_DEF_LVP_CUT 3000
#define LX_DEF_BAT_RINT 130          // F15 DC about 90 mOhm (1.5 x its 60 mOhm AC, estimate) + strips/wires + FETs + copper
#define LX_DEF_BAT_MAX_MA 2800       // 93 % of the F15's 3 A: a LuxLibre BAT-1 deviation (70 % = 2100), only turbo (<= 60 s, regulated) comes near it; 7-12 % below the worst-case trip
#define LX_DEF_CHG_MAXLVL 121        // 609 mA while USB is connected (as v0.6: about 600 mA)
// Charge estimate: the F15's own open-circuit curve (no F15 curve is published: a generic 3.6 V-nominal
// NMC cell, as in the FlashKa firmware), mV at 100, 90, ... 10 % and 3.00 V = 0 % (the cut-off). The
// built-in Li-ion curve (3.82 V at 50 %) would show about 10 % at half charge and warn of a low battery.
#define LX_BAT_OCV_MV 4200, 4050, 3950, 3860, 3770, 3680, 3610, 3540, 3470, 3380, 3000
#define LX_DEF_BLINK_LVL 70

// ---- LED flux, optic and body model (used by the PC simulator only: make sim BOARD=edco-v01) ----
// Flux of the SST-20 Gen 2 6500 K G1 at Tj 85 degC, lumens at the LED: 680 lm at 1.5 A (bin minimum) and
// 1156 lm at 3.0 A are datasheet values; the other points are estimates from the datasheets' relative-flux
// values (SST-20-WE: 0.71 at 1.0 A, 1.26 at 2.0 A; SST-20-W Gen 1: 0.28 at 0.35 A, 0.53 at 0.7 A, all
// relative to 1.5 A). Below 350 mA a straight line to zero. The same table is in the FlashKa firmware.
#define LX_LED_LM_MA 0, 350, 700, 1000, 1500, 2000, 3000
#define LX_LED_LM    0, 191, 361, 485, 680, 855, 1156
#define LX_OPTIC_PCT 87              // LEDiL LISA3-RS-PIN with the SST-20 Gen 2: 87 % (datasheet, simulated)
// Body and cell from the EDCO v0.1 CAD (hardware/edco-v01/cad/edco_interface.json; 6061 0.896 J/gK, copper
// 0.385 J/gK):
//  head  = head (LED holder) 3.61 g + bezel ring 1.19 g + tube in front of x = 12 mm 2.81 g, 7.61 g of aluminium,
//          + copper LED board 1.13 g = 7.25 J/K
//  body  = rest of the tube, 30.26 g = 27.1 J/K (sled, boards and button not counted)
//  head to body: the head spigot sits in the bore on paste (391 mm2, about 0.02 K/W), then conduction along
//                the 81 mm of tube behind the head, section 132.6 mm2 (d20 / d15.2), 167 W/mK, lumped as
//                L / (3 k A) = 1.22 K/W; 1.3 K/W in all
//  body to air: aluminium surface 6393 mm2 x 11 W/m2K (still air, anodised: THM-2) = 14.2 K/W
//  cell: as FlashKa v0.7 (one F15, 1500 mAh, 132 mOhm to the LED path incl. FETs and strips); the cell's
//        22 J/K is weakly coupled to the tube (0.6 mm air gap) and not in this two-node model.
//  Sensor lag 4 s: the NTC sits on the main board 1-2 mm behind the head's rear face.
#define LX_SIM_CAPACITY_MAH 1500
#define LX_SIM_RINT_MOHM 132
#define LX_SIM_C_HEAD_MJ 7250        // mJ/K
#define LX_SIM_C_BODY_MJ 27100       // mJ/K
#define LX_SIM_R_HEAD_BODY_MK 1300   // mK/W
#define LX_SIM_R_BODY_AMB_MK 14200   // mK/W
#define LX_SIM_SENSOR_TAU_MS 4000
#define LX_SIM_DROP_MOHM 128         // battery (under load) to LED at 100 % duty
#define LX_SIM_OCV_V 2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20
#if LX_MAIN_MAX_MA > LX_ESP_LED_FULL_MA
#error "LX_MAIN_MAX_MA above the driver's full scale"
#endif
