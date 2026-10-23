// SPDX-License-Identifier: GPL-3.0-or-later
// Board: FlashKa Keychain v0.7 (LuxLibre reference design, hardware/flashka-keychain-v07/).
//
// The v0.6 board (../flashka-keychain-v06/board.h) with a stronger power stage and one 14500 cell
// in a 99.2 mm octagonal body.
// Unchanged: ESP32-C3-MINI-1 module and every GPIO (the pin map below is the v0.6 one), the button
// ladder (the three keys sit on a key board in the middle of the body: same switches, resistors
// and net), the RGB light ring, the TP4057 USB-C charger, the Class 2 laser behind the slide-switch
// interlock S2, the NTC 100 k B4250 on the main board near the LED driver. Changed:
//  * LED: Luminus SST-20 Gen 2 (6500 K, G1 bin) on a 10 mm copper DTP board behind a LEDiL
//    LISA3-RS-PIN TIR optic. Datasheet maximum 3.0 A DC (4 A only as a surge under 10 ms);
//  * driver: TPS62095 4 A synchronous buck (100 % duty mode) in the same TLV333 current loop with
//    the 20 mOhm sense resistor; the VSET divider is 2.2 k / 100 k, so 100 % PWM duty = 3552 mA;
//  * cell: one Vapcell INR14500 F15 (1500 mAh typical / 1150 mAh minimum, 3.60 V nominal, 3 A
//    maximum continuous, about 60 mOhm AC), nickel strips welded to both ends, protected on the main
//    board (DW01A + SE8830A dual MOSFET in the cell minus, Kelvin-sensed; trip 5.3-5.6 A typical at
//    25 degC, 4.3-4.5 A hot, as low as 3.0-3.15 A in the worst case: DW01A at its 120 mV minimum
//    with hot MOSFETs). A trip latches: the light stays off until USB power is plugged in. The TP4057
//    charges at 500 mA (R3 2.0 k).
// LuxLibre full scale (level 150) is 2850 mA, the FlashKa v0.7 turbo: the LED's 3000 mA datasheet
// maximum less the worst-case tolerance of the current loop. The port can never set more than
// LX_MAIN_MAX_MA, and this header refuses to build with more than 3000 mA.
// Pin map = GPIO_MAP in tools/kicad/flashka_parts.py of the v0.6 package (no GPIO change in v0.7).
#pragma once

#define LX_BOARD_NAME "FlashKa Keychain v0.7"

#define LX_TICK_MS 10
#define LX_STORAGE_SIZE 256          // NVS blob
#define LX_HAS_CONSOLE 1             // USB-Serial-JTAG
#define LX_HAS_AUX_RGB 1             // the light ring
#define LX_HAS_LASER 1
#define LX_HAS_CHARGER 1
#define LX_HAS_TEMP 1
#define LX_BAT_CELLS 1

// Main channel: LEDC 13-bit PWM -> RC filter -> current set point; 100 % duty = 3552 mA.
// LuxLibre full scale (level 150) is 2850 mA, the FlashKa v0.7 turbo: the LED's 3000 mA maximum
// less the 5 % worst-case tolerance of the current loop (3.3 V rail, divider, sense resistor), so
// the LED never sees more than 3.0 A. 95 % of the LED maximum is above the 80 % of LED-2 (a
// "Should" rule): the owner's 1000 lm target needs it; turbo is timed (TURBO_S) and regulated.
#define LX_OUT_MIN_Q16 23            // level 1 = 1 mA
#define LX_MAIN_MAX_MA 2850
#define LX_LED_VF0_MV 2800           // SST-20 Gen 2: V = 2.80 V + 0.15 V/A x I (3.0 V at 1.5 A, datasheet typical)
#define LX_LED_RS_MOHM 150
#define LX_DRIVER_EFF_PCT 87         // TPS62095 + inductor + sense + protection FETs at 3 A (estimate)
#if LX_MAIN_MAX_MA > 3000
#error "FlashKa v0.7: the SST-20 Gen 2 is rated for 3.0 A DC; LX_MAIN_MAX_MA must not exceed 3000"
#endif
#if LX_MAIN_MAX_MA * 105 > 3000 * 100
#error "FlashKa v0.7: with the current loop's 5 % worst-case tolerance LX_MAIN_MAX_MA must stay at or below 2857"
#endif

// ---- ESP32-C3 pin map (GPIO numbers, as v0.6) ----
#define LX_ESP_GPIO_VBAT_ADC 0       // ADC1_CH0, VBAT / 2 (measured against GND = P-, below the protection FETs)
#define LX_ESP_GPIO_NTC_ADC 1        // ADC1_CH1, 100 k to 3V3, NTC to GND
#define LX_ESP_GPIO_RGB_B 2          // ring blue, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_CHG_STAT 4       // TP4057 CHRG, low = charging
#define LX_ESP_GPIO_CHG_DONE 5       // TP4057 STDBY, low = charge complete
#define LX_ESP_GPIO_LED_PWM 6        // LEDC -> current set point
#define LX_ESP_GPIO_LED_EN 7         // high = driver on (100 k pull-down)
#define LX_ESP_GPIO_RGB_G 8          // ring green, active low (strap pin, 10 k pull-up)
#define LX_ESP_GPIO_LASER 10         // high = laser on, if S2 is armed (100 k pull-down)
#define LX_ESP_GPIO_CHG_SET 20       // low = ~500 mA (R3 2.0 k), floating = 10 mA trickle, high = off
#define LX_ESP_GPIO_RGB_R 21         // ring red, active low (U0TXD: the ROM boot log flickers it)
#define LX_ESP_LED_FULL_MA 3552      // current at 100 % duty: 3.3 V x 2.2 k / 102.2 k / 20 mOhm
#define LX_ESP_VBAT_DIV 2            // VBAT = 2 x ADC voltage
#define LX_ESP_NTC_RFIX 100000L
#define LX_ESP_NTC_R25 100000L
#define LX_ESP_NTC_BETA 4250L

// ---- buttons: resistor ladder on BTN, as v0.6 (see ../flashka-keychain-v06/board.h) ----
// Main (SW1) shorts BTN to GND; next (SW2) pulls it down through R30 1 k, previous (SW3) through
// R31 2.2 k; R9 10 k pull-up. The main button is the LuxLibre button; the port ignores the others.
#define LX_ESP_BTN_LADDER_ADC_GPIO 3     // ADC1_CH3, read at 2.5 dB (0 to 1050 mV), curve-fitting calibration
#define LX_ESP_BTN_WAKE_GPIO 9           // digital input, internal pull-up off: low = some button; light-sleep wake
#define LX_ESP_BTN_MAIN_BELOW_MV 106     // pressed = calibrated BTN voltage below this

// ---- defaults = the FlashKa v0.7 "Balanced" profile and the v0.5 button layout ----
#define LX_DEF_UI_STYLE 1            // modes: hold steps Low -> Medium -> High
#define LX_DEF_PREVIEW 0             // the laser gesture must not flash the main LED
#define LX_DEF_RAMP_FLOOR 22         // moon 3 mA
#define LX_DEF_MODE_CNT 3
#define LX_DEF_MODE_1 70             // low 40 mA (19 lm out of the front)
#define LX_DEF_MODE_2 104            // medium 244 mA (FlashKa: 250 mA, 119 lm)
#define LX_DEF_MODE_3 138            // high 1501 mA (592 lm; FlashKa: 1530 mA, 601 lm; level 139 = 1583 mA)
#define LX_DEF_MEM_LEVEL 70
#define LX_DEF_TURBO_LVL 150         // turbo 2850 mA (966 lm out of the front, LED model at Tj 85 degC)
#define LX_DEF_TURBO_S 60
#define LX_DEF_TURBO_DOWN 138        // back to high after the turbo time
#define LX_DEF_BLINKY 0              // no beacon / SOS / strobe on a keychain light
#define LX_DEF_LOCK_MOON 0           // lockout stays dark (pocket)
#define LX_DEF_THM_LIMIT 50          // sensor = head node in the simulator: the body (held) settles at 46.5 degC (THM-1)
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

// ---- LED flux, optic and body model (used by the PC simulator only: make sim BOARD=flashka-keychain-v07) ----
// Flux of the SST-20 Gen 2 6500 K G1 at Tj 85 degC, lumens at the LED: 680 lm at 1.5 A (bin minimum) and
// 1156 lm at 3.0 A are datasheet values; the other points are estimates from the datasheets' relative-flux
// values (SST-20-WE: 0.71 at 1.0 A, 1.26 at 2.0 A; SST-20-W Gen 1: 0.28 at 0.35 A, 0.53 at 0.7 A, all
// relative to 1.5 A). Below 350 mA a straight line to zero. The same table is in the FlashKa firmware.
#define LX_LED_LM_MA 0, 350, 700, 1000, 1500, 2000, 3000
#define LX_LED_LM    0, 191, 361, 485, 680, 855, 1156
#define LX_OPTIC_PCT 87              // LEDiL LISA3-RS-PIN with the SST-20 Gen 2: 87 % (datasheet, simulated)
// Body and cell from the v0.7 housing CAD, octagonal body (aluminium 6061, 0.896 J/gK; copper 0.385 J/gK):
//  head  = head block (tray X 0-11.45 mm) 6.34 g + lid over it 1.05 g + copper LED board 1.126 g = 7.06 J/K
//  body  = rest of tray and lid, 30.91 - 7.39 = 23.52 g = 21.07 J/K (PCB and keys not counted)
//  head to body: conduction along the 87.75 mm behind the head, mean metal section ~80 mm^2 (tray ~65 mm^2
//                plus half of the lid's ~30 mm^2), 167 W/mK; lumped as L / (3 k A) = 2.2 K/W
//  body to air: aluminium surface 6886 mm^2 x 11 W/m2K (still air, anodised: THM-2) = 13.2 K/W
//  LED board to head: 78.51 mm^2 on 0.1 mm paste, inside the head node (this model has no junction node)
//  cell: one F15, 1500 mAh, a generic 3.6 V-nominal NMC curve (no F15 curve is published); 132 mOhm =
//        cell DC about 90 mOhm (1.5 x the 60 mOhm AC value, estimate) + strips and wires 10 + protection
//        FETs 28 + copper 4. Driver headroom: at 100 % duty the LED gets at most (V - 2.80) / (0.15 +
//        0.128) A with V the battery voltage under load (electronics: 3.0 A down to 3.71 V at the cell
//        pads). The cell's 22 J/K is not in this two-node model (it is weakly coupled to the body, about
//        8 K/W through the rails, air and foam), so the body warms a little faster here than in the
//        FlashKa firmware's three-node simulation.
//  Sensor lag as the keychain preset (4 s): the NTC sits on the main board about 12 mm behind the head
//        block and is assumed to follow the head (check on the bench, THM-4/THM-6).
// Numbers: the housing figures of hardware/flashka-keychain-v07/cad/housing_interface.json.
#define LX_SIM_CAPACITY_MAH 1500
#define LX_SIM_RINT_MOHM 132
#define LX_SIM_C_HEAD_MJ 7060        // mJ/K
#define LX_SIM_C_BODY_MJ 21070       // mJ/K
#define LX_SIM_R_HEAD_BODY_MK 2200   // mK/W
#define LX_SIM_R_BODY_AMB_MK 13200   // mK/W
#define LX_SIM_SENSOR_TAU_MS 4000
#define LX_SIM_DROP_MOHM 128         // battery (under load) to LED at 100 % duty
#define LX_SIM_OCV_V 2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20
#if LX_MAIN_MAX_MA > LX_ESP_LED_FULL_MA
#error "LX_MAIN_MAX_MA above the driver's full scale"
#endif
