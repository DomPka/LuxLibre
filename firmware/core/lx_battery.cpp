// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_battery.h"
#include "lx_params.h"

namespace lx {
namespace battery {

namespace {

constexpr uint8_t STEP_LEVELS = 10;       // step-down size
constexpr uint8_t WARN_TICKS = 20;        // 2.0 s below LVP_WARN before the first step
constexpr uint8_t STEP_TICKS = 50;        // 5.0 s between further steps
constexpr uint8_t CUT_TICKS = 10;         // 1.0 s below LVP_CUT before switching off

// Open-circuit voltage -> state of charge, per cell, mV at 100, 90, ... 0 %.
// Li-ion (NMC/NCA, typical), LiFePO4 (very flat curve: voltage is a poor gauge), NiMH.
const uint16_t k_ocv[3][11] LX_FLASH = {
    {4200, 4060, 3980, 3920, 3870, 3820, 3790, 3770, 3740, 3680, 3300},
    {3400, 3350, 3330, 3320, 3310, 3300, 3290, 3270, 3250, 3200, 2800},
    {1400, 1340, 1320, 1300, 1280, 1260, 1250, 1240, 1220, 1180, 1000},
};

// Lowest cut-off per chemistry (LuxLibre rule, mV per cell): above the cells' datasheet
// discharge limits with a margin. LVP_CUT and LVP_WARN can be set higher, never lower.
const uint16_t k_cut_floor[3] LX_FLASH = {2700, 2000, 900};

int32_t g_mv_q4 = 0;           // filtered cell voltage * 16
uint16_t g_cell_ma = 0;
uint8_t g_cap = LEVEL_MAX;
uint8_t g_low_ticks = 0;
uint8_t g_cut_ticks = 0;
bool g_empty = false;
bool g_cut_event = false;

uint16_t per_cell(uint16_t pack_mv) {
    int32_t v = (int32_t)pack_mv + p(P_BAT_CAL);
    if (v < 0) v = 0;
    uint8_t n = (uint8_t)clamp<int16_t>(p(P_BAT_CELLS), 1, 4);
    return (uint16_t)(v / n);
}

}  // namespace

void init() {
    g_mv_q4 = 0;
    g_cap = LEVEL_MAX;
    g_low_ticks = g_cut_ticks = 0;
    g_empty = false;
    g_cut_event = false;
}

void prime(uint16_t pack_mv) { g_mv_q4 = (int32_t)per_cell(pack_mv) << 4; }

uint16_t cell_mv() { return (uint16_t)(g_mv_q4 >> 4); }

uint16_t rest_cell_mv() {
    uint32_t comp = (uint32_t)g_cell_ma * (uint32_t)p(P_BAT_RINT) / 1000u;   // mV
    return (uint16_t)(cell_mv() + comp);
}

uint8_t percent() {
    uint8_t chem = (uint8_t)clamp<int16_t>(p(P_BAT_CHEM), 0, 2);
    uint16_t v = rest_cell_mv();
    if (v >= lx_flash_u16(&k_ocv[chem][0])) return 100;
    for (uint8_t i = 1; i < 11; i++) {
        uint16_t hi = lx_flash_u16(&k_ocv[chem][i - 1]);
        uint16_t lo = lx_flash_u16(&k_ocv[chem][i]);
        if (v >= lo) {
            // linear between the two points (10 % apart)
            uint16_t pct_hi = (uint16_t)(100 - 10 * (i - 1));
            return (uint8_t)(pct_hi - (uint32_t)(hi - v) * 10u / (uint32_t)(hi - lo));
        }
    }
    return 0;
}

uint8_t cap() { return g_cap; }
bool empty() { return g_empty; }
void user_action() {
    g_cap = LEVEL_MAX;
    g_low_ticks = 0;
}

bool cutoff_event() {
    bool e = g_cut_event;
    g_cut_event = false;
    return e;
}

void update(uint16_t pack_mv, uint16_t cell_ma, uint8_t level_now, bool usb) {
    bool light_on = level_now > 0;
    int32_t v = (int32_t)per_cell(pack_mv) << 4;
    if (g_mv_q4 == 0) g_mv_q4 = v;
    else g_mv_q4 += (v - g_mv_q4) / 8;                                   // tau ~ 0.8 s
    g_cell_ma = light_on ? cell_ma : 0;

    uint16_t vf = cell_mv();
    uint8_t chem = (uint8_t)clamp<int16_t>(p(P_BAT_CHEM), 0, 2);
    uint16_t cut = max_of((uint16_t)p(P_LVP_CUT), lx_flash_u16(&k_cut_floor[chem]));
    uint16_t warn = max_of((uint16_t)p(P_LVP_WARN), (uint16_t)(cut + 200));   // always step down before the cut-off

    // Release the latch once the cell has recovered or external power is present.
    if (g_empty && (usb || (!light_on && vf >= (uint16_t)p(P_LVP_RESUME)))) g_empty = false;

    if (!light_on) {
        g_low_ticks = 0;
        g_cut_ticks = 0;
        // A cell that is already below the cut-off at rest refuses switch-on.
        if (!usb && vf < cut) g_empty = true;
        return;
    }

    // Cut-off.
    if (vf < cut) {
        if (++g_cut_ticks >= CUT_TICKS) {
            g_cut_ticks = 0;
            g_empty = true;
            g_cut_event = true;
            g_cap = 1;
        }
    } else {
        g_cut_ticks = 0;
    }

    // Step-down.
    if (vf < warn) {
        g_low_ticks++;
        if (g_low_ticks >= WARN_TICKS + STEP_TICKS || (g_low_ticks == WARN_TICKS)) {
            uint8_t c = min_of(g_cap, level_now);        // step down from the level in use
            g_cap = c > STEP_LEVELS + 1 ? (uint8_t)(c - STEP_LEVELS) : 1;
            if (g_low_ticks >= WARN_TICKS + STEP_TICKS) g_low_ticks = WARN_TICKS;
        }
    } else if (vf > warn + 100) {
        g_low_ticks = 0;
    }
}

}  // namespace battery
}  // namespace lx
