// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - NTC thermistor conversion for ports (no floating point at run time).
//
// Circuit: fixed resistor R_FIX from the ADC reference to the ADC pin, NTC from the pin to
// ground. The ADC ratio r = code / FULL gives R_ntc = R_FIX * r / (1 - r), and the beta
// equation 1/T = 1/298.15 K + ln(R_ntc / R25) / B gives the temperature. The table is
// computed by the compiler (constexpr) for the board's values; at run time a reading is
// one table look-up and a linear interpolation.
#pragma once

#include "lx_common.h"

namespace lx {
namespace ntc {

constexpr double ln_c(double x) {
    // ln(x) = k ln 2 + 2 atanh((m - 1) / (m + 1)), with m in [0.75, 1.5)
    if (x <= 0) return -1e9;
    int k = 0;
    while (x >= 1.5) { x /= 2.0; k++; }
    while (x < 0.75) { x *= 2.0; k--; }
    double y = (x - 1.0) / (x + 1.0), y2 = y * y, term = y, sum = 0.0;
    for (int n = 1; n < 40; n += 2) { sum += term / n; term *= y2; }
    return 2.0 * sum + k * 0.69314718055994530942;
}

// Temperature in deci-degC for an ADC ratio (0 ... 1).
constexpr int16_t temp_dc_of_ratio(double r, double r_fix, double r25, double beta) {
    if (r <= 0.002) return 1600;      // pin near ground: shorted NTC (outside the valid range)
    if (r >= 0.998) return -600;      // pin near the reference: open NTC (outside the valid range)
    double r_ntc = r_fix * r / (1.0 - r);
    double inv_t = 1.0 / 298.15 + ln_c(r_ntc / r25) / beta;
    double c = 1.0 / inv_t - 273.15;
    double dc = c * 10.0;
    if (dc > 1500) dc = 1500;
    if (dc < -500) dc = -500;
    return (int16_t)(dc >= 0 ? dc + 0.5 : dc - 0.5);
}

// 65-point table over the full ADC range.
template <long R_FIX, long R25, long BETA>
struct Table {
    static constexpr int N = 65;
    int16_t t[N];
    constexpr Table() : t() {
        for (int i = 0; i < N; i++) t[i] = temp_dc_of_ratio(i / 64.0, (double)R_FIX, (double)R25, (double)BETA);
    }
    // code: ADC reading, full: ADC full scale (e.g. 1023 or 4095)
    int16_t temp_dc(uint32_t code, uint32_t full) const {
        if (code >= full) return t[N - 1];
        uint32_t pos = code * 64u * 256u / full;   // table index in 1/256 steps
        uint32_t i = pos >> 8, f = pos & 0xFF;
        int32_t a = t[i], b = t[i + 1];
        return (int16_t)(a + ((b - a) * (int32_t)f) / 256);
    }
};

}  // namespace ntc
}  // namespace lx
