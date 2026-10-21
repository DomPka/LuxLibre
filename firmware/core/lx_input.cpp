// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_input.h"

namespace lx {
namespace input {

namespace {

enum State : uint8_t { ST_IDLE, ST_DOWN, ST_UP };

State g_state = ST_IDLE;
bool g_debounced = false;   // debounced switch level
bool g_last_raw = false;
uint8_t g_stable = 0;       // ticks the raw level has been stable
uint8_t g_count = 0;
uint16_t g_t = 0;           // time in the current state
bool g_holding = false;

Event make(uint8_t type, uint16_t held = 0) {
    Event e;
    e.type = type;
    e.count = g_count;
    e.held_ms = held;
    return e;
}

}  // namespace

void reset(bool pressed_now) {
    g_last_raw = pressed_now;
    g_debounced = pressed_now;
    g_stable = DEBOUNCE_TICKS;
    g_holding = false;
    g_t = 0;
    if (pressed_now) {
        // Woken up by the button: this press is the first one of a gesture.
        g_state = ST_DOWN;
        g_count = 1;
    } else {
        g_state = ST_IDLE;
        g_count = 0;
    }
}

bool idle() { return g_state == ST_IDLE && !g_debounced; }
bool pressed() { return g_debounced; }

Event update(bool raw_down, uint16_t dt_ms, uint16_t click_ms) {
    // --- debounce ---
    if (raw_down == g_last_raw) {
        if (g_stable < 255) g_stable++;
    } else {
        g_last_raw = raw_down;
        g_stable = 1;
    }
    bool edge = false;
    if (g_stable >= DEBOUNCE_TICKS && g_debounced != g_last_raw) {
        g_debounced = g_last_raw;
        edge = true;
    }

    // --- gesture state machine ---
    uint32_t t = (uint32_t)g_t + dt_ms;
    g_t = t > 60000u ? 60000u : (uint16_t)t;

    switch (g_state) {
    case ST_IDLE:
        if (edge && g_debounced) {
            g_state = ST_DOWN;
            g_count = 1;
            g_t = 0;
            g_holding = false;
            return make(EV_PRESS);
        }
        break;

    case ST_DOWN:
        if (edge && !g_debounced) {
            if (g_holding) {
                Event e = make(EV_HOLD_END, (uint16_t)(g_t - click_ms));
                g_holding = false;
                g_state = ST_IDLE;
                g_count = 0;
                g_t = 0;
                return e;
            }
            g_state = ST_UP;
            g_t = 0;
            return make(EV_RELEASE);
        }
        if (!g_holding && g_t >= click_ms) {
            g_holding = true;
            return make(EV_HOLD);
        }
        if (g_holding) return make(EV_HOLD_TICK, (uint16_t)(g_t - click_ms));
        break;

    case ST_UP:
        if (edge && g_debounced) {
            if (g_count < MAX_COUNT) g_count++;
            g_state = ST_DOWN;
            g_t = 0;
            return make(EV_PRESS);
        }
        if (g_t >= click_ms) {
            Event e = make(EV_CLICK);
            g_state = ST_IDLE;
            g_count = 0;
            g_t = 0;
            return e;
        }
        break;
    }
    return make(EV_NONE);
}

}  // namespace input
}  // namespace lx
