// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - button debouncing and gesture decoding.
//
// The decoder turns the raw switch signal into events:
//   PRESS(n)      the n-th press of a gesture started (immediately)
//   RELEASE(n)    the n-th press ended as a click (immediately)
//   CLICK(n)      n clicks, then no further press within CLICK_MS (the gesture is complete)
//   HOLD(n)       n-1 clicks followed by a press held longer than CLICK_MS ("click, click, hold" = HOLD(3))
//   HOLD_TICK(n)  every tick while that press stays down
//   HOLD_END(n)   the held press was released
#pragma once

#include "lx_common.h"

namespace lx {
namespace input {

enum EventType : uint8_t {
    EV_NONE = 0,
    EV_PRESS = 1,
    EV_RELEASE = 2,
    EV_CLICK = 3,
    EV_HOLD = 4,
    EV_HOLD_TICK = 5,
    EV_HOLD_END = 6,
};

struct Event {
    uint8_t type;      // EventType
    uint8_t count;     // 1 ... 9
    uint16_t held_ms;  // HOLD_TICK / HOLD_END: time since the hold started
};

constexpr uint8_t MAX_COUNT = 9;
constexpr uint8_t DEBOUNCE_TICKS = 2;   // the raw level must be stable for 2 ticks

void reset(bool pressed_now);           // forget the gesture (after boot or wake-up)
Event update(bool raw_down, uint16_t dt_ms, uint16_t click_ms);
bool idle();                            // no gesture in progress and button released
bool pressed();                         // debounced state

}  // namespace input
}  // namespace lx
