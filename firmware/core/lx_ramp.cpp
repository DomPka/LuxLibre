// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_ramp.h"

namespace lx {
namespace ramp {

power_t power_of_level(uint8_t level) {
    if (level == 0) return 0;
    if (level >= LEVEL_MAX) return 65535;
    // e = log2(power / 65536) + 16, in Q8; runs from LOG_MIN+16 (level 1) to 16 (level 150)
    int32_t lg = (int32_t)LOG_MIN_Q8 * (int32_t)(LEVEL_MAX - level) / (int32_t)(LEVEL_MAX - 1);
    int32_t e = 16 * 256 + lg;
    if (e < 0) return 1;
    uint8_t n = (uint8_t)(e >> 8);
    uint32_t r = (uint32_t)(e & 0xFF);
    // 2^(r/256) in Q15 with the quadratic 1 + 0.65632 x + 0.34368 x^2 (error < 0.2 %)
    uint32_t m = 32768u + ((21506u * r) >> 8) + ((11262u * r * r) >> 16);
    uint32_t p = (m << n) >> 15;
    if (p > 65535u) p = 65535u;
    if (p < 1u) p = 1u;
    return (power_t)p;
}

uint8_t level_of_power(power_t p) {
    if (p < power_of_level(1)) return 0;
    uint8_t lo = 1, hi = LEVEL_MAX;   // power_of_level is monotonic
    while (lo < hi) {
        uint8_t mid = (uint8_t)((lo + hi + 1) / 2);
        if (power_of_level(mid) <= p) lo = mid; else hi = (uint8_t)(mid - 1);
    }
    return lo;
}

}  // namespace ramp
}  // namespace lx
