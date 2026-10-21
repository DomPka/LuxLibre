// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - brightness levels <-> output power.
//
// Level 1 gives LX_OUT_MIN_Q16, level 150 gives full power, and every level in between
// is the same ratio brighter than the one below (geometric spacing). The eye judges
// brightness roughly logarithmically, so equal ratios look like equal steps.
// The mapping is computed in the log2 domain with integer maths only.
#pragma once

#include "lx_common.h"
#include "lx_board.h"

namespace lx {
namespace ramp {

// log2(x / 65536) in Q8 (1/256 steps) for x = 1 ... 65535, evaluated at compile time.
constexpr int16_t log2_q8_of_q16(uint32_t x) {
    int16_t ip = 0;                 // integer part: index of the highest set bit
    uint32_t v = x;
    while (v >= 2) { v >>= 1; ip++; }
    // normalise the mantissa to [1, 2) in Q16, then extract 8 fractional bits by squaring
    uint32_t m = (x << 16) >> ip;   // 65536 ... 131071
    int16_t frac = 0;
    for (int i = 0; i < 8; i++) {
        m = (uint32_t)(((uint64_t)m * m) >> 16);
        frac = (int16_t)(frac << 1);
        if (m >= 131072u) { m >>= 1; frac |= 1; }
    }
    return (int16_t)((ip - 16) * 256 + frac);
}

constexpr int16_t LOG_MIN_Q8 = log2_q8_of_q16(LX_OUT_MIN_Q16);   // negative
static_assert(LOG_MIN_Q8 < 0, "LX_OUT_MIN_Q16 must be below full scale");

// Output power of a level (0 -> 0, 1 ... 150).
power_t power_of_level(uint8_t level);

// Highest level whose power does not exceed p (0 if even level 1 is above p).
uint8_t level_of_power(power_t p);

}  // namespace ramp
}  // namespace lx
