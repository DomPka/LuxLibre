// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_aux.h"
#include "lx_board.h"
#include "lx_params.h"
#include "../hal/lx_hal.h"

namespace lx {
namespace aux {

namespace {

Pattern g_pat = PAT_NONE;
Status g_status = STATUS_NONE;
uint16_t g_t = 0;            // time in the current pattern
uint16_t g_status_t = 0;

#if LX_HAS_AUX_RGB
uint8_t g_r = 0, g_g = 0, g_b = 0;   // colour of the running pattern

struct Blink { uint8_t count; uint16_t on_ms; uint16_t off_ms; };

Blink blink_of(Pattern pat) {
    switch (pat) {
    case PAT_LOCK:
    case PAT_UNLOCK: return {3, 150, 150};
    case PAT_REFUSE: return {1, 300, 100};
    case PAT_EMPTY: return {5, 80, 80};
    case PAT_TICK: return {1, 30, 30};
    case PAT_BATTERY: return {1, 2000, 0};
    case PAT_RESET: return {5, 100, 100};
    default: return {0, 0, 0};
    }
}
#endif

}  // namespace

void init() {
    g_pat = PAT_NONE;
    g_status = STATUS_NONE;
    g_t = g_status_t = 0;
}

bool busy() { return g_pat != PAT_NONE; }

void event(Pattern pat, uint8_t battery_percent) {
#if LX_HAS_AUX_RGB
    if (p(P_AUX_MODE) == 0) return;
    if (pat == PAT_BATTERY && p(P_AUX_MODE) < 2) return;
    g_pat = pat;
    g_t = 0;
    switch (pat) {
    case PAT_UNLOCK: g_r = 0; g_g = 255; g_b = 0; break;
    case PAT_RESET: g_r = 255; g_g = 255; g_b = 255; break;
    case PAT_BATTERY:
        if (battery_percent > 50) { g_r = 0; g_g = 255; g_b = 0; }
        else if (battery_percent >= 20) { g_r = 255; g_g = 160; g_b = 0; }
        else { g_r = 255; g_g = 0; g_b = 0; }
        break;
    default: g_r = 255; g_g = 0; g_b = 0; break;
    }
#else
    (void)pat;
    (void)battery_percent;
#endif
}

void set_status(Status s) {
    if (s != g_status) {
        g_status = s;
        g_status_t = 0;
    }
}

void tick(uint16_t dt_ms) {
#if LX_HAS_AUX_RGB
    uint8_t r = 0, g = 0, b = 0;
    if (g_pat != PAT_NONE) {
        Blink bl = blink_of(g_pat);
        uint16_t period = (uint16_t)(bl.on_ms + bl.off_ms);
        uint16_t total = (uint16_t)(period * bl.count);
        if (g_t >= total) {
            g_pat = PAT_NONE;
        } else if ((g_t % period) < bl.on_ms) {
            r = g_r; g = g_g; b = g_b;
        }
        g_t = (uint16_t)(g_t + dt_ms);
    } else if (p(P_AUX_MODE) != 0) {
        g_status_t = (uint16_t)((g_status_t + dt_ms) % 4000u);
        switch (g_status) {
        case STATUS_CHARGING: if (g_status_t % 2000u < 1000u) r = 255; break;
        case STATUS_CHARGED: g = 255; break;
        case STATUS_LOW: if (g_status_t < 150u) r = 255; break;
        default: break;
        }
    }
    hal::set_aux(r, g, b);
#else
    (void)dt_ms;
#endif
}

}  // namespace aux
}  // namespace lx
