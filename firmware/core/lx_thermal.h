// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - thermal regulation.
//
// A PI regulator in velocity form computes a brightness cap (in levels) that keeps the
// predicted temperature at THM_LIMIT:
//    T_pred = T_filtered + (rate of rise) * THM_LEAD
//    cap   -= KP * change of error + KI * error * dt        (error = T_pred - THM_LIMIT)
// Working in levels (a log scale of power) keeps the loop gain nearly constant from a
// keychain light to a 21700 light, because each level changes the power by the same ratio.
// The cap is clamped to [THM_FLOOR, 150]; above THM_SHUTDN the light switches off.
#pragma once

#include "lx_common.h"

namespace lx {
namespace thermal {

constexpr int16_t NO_SENSOR = -32768;
constexpr uint16_t PERIOD_MS = 100;       // update() interval

void init();
// level_now = the output level in use (after all caps; 0 = off). When it is too hot and the
// light has run steadily below the cap for 3 s, the cap starts from that level.
void update(temp_dc_t raw, uint8_t level_now);   // call every PERIOD_MS
void resync();                            // after a sleep: restart the filters from the next reading
uint8_t cap();                            // allowed maximum level, 1 ... 150
bool shutdown();                          // hard limit reached (latched with 5 degC hysteresis)
bool sensor_fault();                      // sensor missing, open or shorted
temp_dc_t temperature();                  // filtered and calibrated, deci-degC
int16_t rate_dc_per_s();                  // filtered rate of change, deci-degC per second

}  // namespace thermal
}  // namespace lx
