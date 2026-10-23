// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_color.h"
#include "lx_board.h"
#include "lx_params.h"
#include "lx_ramp.h"

namespace lx {
namespace color {

namespace {

// Fixed colours: red, green, blue share in %. The custom colour comes from COL_R / COL_G / COL_B.
const uint8_t k_mix[C_CUSTOM][3] LX_FLASH = {
    {100, 0, 0},     // red
    {0, 100, 0},     // green
    {0, 0, 100},     // blue
    {100, 50, 0},    // yellow (red + half green)
    {0, 100, 100},   // cyan
    {100, 0, 100},   // magenta
    {100, 100, 100}, // white made of the three colours
};

bool in_set(uint8_t idx) { return idx < C_COUNT && (p(P_COLOR_SET) & (1 << idx)) != 0; }

}  // namespace

uint8_t valid(uint8_t idx) {
    if (idx >= C_COUNT) idx = 0;
    for (uint8_t k = 0; k < C_COUNT; k++) {
        uint8_t c = (uint8_t)((idx + k) % C_COUNT);
        if (in_set(c)) return c;
    }
    return C_RED;                            // COLOR_SET cannot be 0 (its minimum is 1)
}

uint8_t next(uint8_t idx) { return valid((uint8_t)((idx + 1) % C_COUNT)); }

void mix(uint8_t idx, uint8_t pct[3]) {
    int16_t v[3];
    if (idx == C_CUSTOM) {
        v[0] = p(P_COL_R);
        v[1] = p(P_COL_G);
        v[2] = p(P_COL_B);
    } else {
        if (idx >= C_CUSTOM) idx = C_RED;
        for (uint8_t c = 0; c < 3; c++) v[c] = lx_flash_u8(&k_mix[idx][c]);
    }
    int16_t top = max_of(max_of(v[0], v[1]), v[2]);
    if (top <= 0) {                          // custom colour all zero: red
        pct[0] = 100;
        pct[1] = pct[2] = 0;
        return;
    }
    for (uint8_t c = 0; c < 3; c++) pct[c] = (uint8_t)((clamp<int16_t>(v[c], 0, 100) * 100 + top / 2) / top);
}

void currents_ma(uint8_t level, uint8_t top, uint8_t idx, uint16_t ma[3]) {
    ma[0] = ma[1] = ma[2] = 0;
    if (level == 0) return;
    if (top < 1) top = 1;
    uint32_t p_top = ramp::power_of_level(top);
    uint32_t p_lvl = ramp::power_of_level(level);
    if (p_top == 0) p_top = 1;
    // fraction of the full colour current, Q16 (levels above the top give full current)
    uint32_t frac = p_lvl >= p_top ? 65535u : (uint32_t)(p_lvl * 65535u / p_top);
    uint8_t pct[3];
    mix(idx, pct);
    for (uint8_t c = 0; c < 3; c++) {
        if (!pct[c]) continue;
        uint32_t i = frac * (uint32_t)LX_COLOR_MAX_MA / 65535u * pct[c] / 100u;
        ma[c] = (uint16_t)(i ? i : 1);       // at least 1 mA: the colour never vanishes at moon
    }
}

int find(const char* nm) {
    for (uint8_t i = 0; i < C_COUNT; i++) {
        const char* a = name(i);
        const char* b = nm;
        while (*a && *a == *b) { a++; b++; }
        if (!*a && !*b) return i;
    }
    return -1;
}

const char* name(uint8_t idx) {
    switch (idx) {
    case C_RED: return "red";
    case C_GREEN: return "green";
    case C_BLUE: return "blue";
    case C_YELLOW: return "yellow";
    case C_CYAN: return "cyan";
    case C_MAGENTA: return "magenta";
    case C_WHITE: return "white";
    case C_CUSTOM: return "custom";
    default: return "?";
    }
}

}  // namespace color
}  // namespace lx
