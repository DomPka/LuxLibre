// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - battery voltage, low-voltage protection (LVP) and charge estimate.
//
//  * below LVP_WARN (per cell, under load) for 2 s: the brightness cap drops 10 levels,
//    and again every 5 s while the voltage stays low
//  * below LVP_CUT for 1 s: the light switches off and refuses to switch on until the
//    rested cell is above LVP_RESUME or USB power is present
//  * a new brightness choice by the user lifts the step-down (it returns if still low)
#pragma once

#include "lx_common.h"

namespace lx {
namespace battery {

constexpr uint16_t PERIOD_MS = 100;    // update() interval

void init();
// pack_mv: measured pack voltage; cell_ma: estimated cell current (0 if unknown);
// level_now: level of the main LED (0 = off); usb: external power present.
void update(uint16_t pack_mv, uint16_t cell_ma, uint8_t level_now, bool usb);
void prime(uint16_t pack_mv);          // set the filter to a fresh reading (after wake-up)
uint8_t cap();                         // LVP brightness cap, 1 ... 150
bool cutoff_event();                   // true once when LVP_CUT forces the light off
bool empty();                          // switch-on refused (latched cut-off, cell still low)
void user_action();                    // the user picked a level: lift the step-down
uint16_t cell_mv();                    // filtered voltage per cell (raw, under load)
uint16_t rest_cell_mv();               // per cell, compensated for the load (estimate of rest voltage)
uint8_t percent();                     // state of charge estimate 0 ... 100

}  // namespace battery
}  // namespace lx
