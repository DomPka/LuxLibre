// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - indicator (aux) LED patterns.
//
// Short event patterns (lock, unlock, refused, battery empty) have priority over the
// steady status display (charging, charged, battery colour after switch-on).
#pragma once

#include "lx_common.h"

namespace lx {
namespace aux {

enum Pattern : uint8_t {
    PAT_NONE = 0,
    PAT_LOCK,        // red x3
    PAT_UNLOCK,      // green x3
    PAT_REFUSE,      // one red blink
    PAT_EMPTY,       // five fast red blinks
    PAT_TICK,        // very short red flash (click while locked)
    PAT_BATTERY,     // battery colour for 2 s (green > 50 %, yellow 20-50 %, red < 20 %)
    PAT_RESET,       // white x5 (settings reset to defaults)
    PAT_COLOR,       // the colour beam's colour for 1 s (show_color)
};

enum Status : uint8_t {
    STATUS_NONE = 0,
    STATUS_CHARGING,   // red, slow blink
    STATUS_CHARGED,    // green, steady
    STATUS_LOW,        // red blink every 4 s (light on, battery below 10 %)
};

void init();
void event(Pattern pat, uint8_t battery_percent = 0);
void show_color(uint8_t r, uint8_t g, uint8_t b);   // the colour beam's new colour, 0-255 each (AUX_MODE >= 1)
void set_status(Status s);
void tick(uint16_t dt_ms);   // updates hal::set_aux()
bool busy();                 // an event pattern is still running

}  // namespace aux
}  // namespace lx
