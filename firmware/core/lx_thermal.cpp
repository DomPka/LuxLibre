// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_thermal.h"
#include "lx_params.h"

namespace lx {
namespace thermal {

namespace {

constexpr int16_t T_MIN_VALID = -400;     // below -40 degC: open sensor
constexpr int16_t T_MAX_VALID = 1500;     // above 150 degC: shorted sensor
constexpr int32_t CAP_MAX_Q8 = (int32_t)LEVEL_MAX << 8;
constexpr int32_t HYST_Q8 = 128;          // output hysteresis: half a level on either side
constexpr int32_t DEAD_Q4 = 5 * 16;       // integral dead band, 0.5 degC
constexpr int32_t DERR_MAX_Q4 = 1600;     // error change per step is limited to 10 degC (glitches)
constexpr int32_t ERR_MAX_Q4 = 32000;
constexpr uint8_t STEADY_STEPS = 30;      // the level must be unchanged for 3 s before the cap snaps to it
constexpr uint8_t DWELL_STEPS = 50;       // 5 s between output changes in opposite directions
constexpr int32_t HOT_Q4 = 2 * 160;       // more than 2 degC too hot: step down without waiting

// Fixed point: temperatures in deci-degC * 256 (q8) for the filters, deci-degC * 16 (q4) for
// the regulator. The filters keep their fractions (no dead zone from integer truncation), so a
// slow rise of a few hundredths of a degree per second is still seen by the prediction.
bool g_valid = false;
bool g_fault = false;
bool g_shutdown = false;
int32_t g_temp_q8 = 0;         // filtered temperature
int32_t g_prev_temp_q8 = 0;
int32_t g_rate_acc = 0;        // filtered rate of change per second, q8 * 64
int32_t g_prev_err_q4 = 0;
int32_t g_rem = 0;             // remainder of the regulator step, so that the integral stays exact
int32_t g_cap_q8 = CAP_MAX_Q8;
uint8_t g_cap_out = LEVEL_MAX; // cap with hysteresis: what the light uses
uint8_t g_last_level = 0;
uint8_t g_steady = 0;
int8_t g_out_dir = 0;          // direction of the last output change (+1 up, -1 down)
uint8_t g_since_change = 255;  // steps since that change

}  // namespace

void init() {
    g_valid = false;
    g_fault = false;
    g_shutdown = false;
    g_temp_q8 = 0;
    g_prev_temp_q8 = 0;
    g_rate_acc = 0;
    g_prev_err_q4 = 0;
    g_rem = 0;
    g_cap_q8 = CAP_MAX_Q8;
    g_cap_out = LEVEL_MAX;
    g_last_level = 0;
    g_steady = 0;
    g_out_dir = 0;
    g_since_change = 255;
}

void resync() { g_valid = false; }      // the cap and the shutdown latch are kept

temp_dc_t temperature() { return (temp_dc_t)(g_temp_q8 / 256); }
int16_t rate_dc_per_s() { return (int16_t)(g_rate_acc / (64 * 256)); }
bool shutdown() { return g_shutdown; }
bool sensor_fault() { return g_fault; }

uint8_t cap() {
    if (g_fault) return (uint8_t)clamp<int16_t>(p(P_THM_FLOOR), 1, LEVEL_MAX);
    return g_cap_out;
}

void update(temp_dc_t raw, uint8_t level_now) {
    // --- sensor check ---
    if (raw == NO_SENSOR || raw < T_MIN_VALID || raw > T_MAX_VALID) {
        // No regulation is possible: the light is held at THM_FLOOR (no turbo, no laser,
        // no charging). A shorted NTC usually reads very hot, an open one very cold.
        g_fault = true;
        g_valid = false;
        return;
    }
    g_fault = false;
    int32_t offset_dc = 10 * (int32_t)p(P_THM_OFFSET);
    int32_t t_q8 = ((int32_t)raw + offset_dc) * 256;

    // --- filters: temperature (tau ~1.6 s) and its rate of change (tau ~6.4 s) ---
    // A coarse or noisy sensor (1 degC steps, a few ADC counts of noise) must not reach the
    // output: the light would visibly flicker between two levels.
    bool first = !g_valid;
    if (first) {
        g_temp_q8 = t_q8;
        g_prev_temp_q8 = t_q8;
        g_rate_acc = 0;
        g_rem = 0;
        g_valid = true;
    } else {
        g_temp_q8 += (t_q8 - g_temp_q8) / 16;
    }
    int32_t inst_rate_q8 = (g_temp_q8 - g_prev_temp_q8) * 10;           // per second (10 updates/s)
    g_prev_temp_q8 = g_temp_q8;
    g_rate_acc += inst_rate_q8 - g_rate_acc / 64;
    int32_t temp_q4 = g_temp_q8 / 16;
    int32_t rate_q4 = g_rate_acc / (64 * 16);

    // --- hard limit with 5 degC hysteresis ---
    // It also looks at the uncalibrated reading, so a calibration offset can only make it act
    // earlier, never later.
    int32_t t_dc = g_temp_q8 / 256;
    int32_t t_hot = offset_dc < 0 ? t_dc - offset_dc : t_dc;
    int32_t shut_dc = 10 * (int32_t)p(P_THM_SHUTDN);
    if (t_hot >= shut_dc) g_shutdown = true;
    else if (g_shutdown && t_hot < shut_dc - 50) g_shutdown = false;

    // --- PI regulator (velocity form) on the predicted temperature ---
    if (rate_q4 < 0) rate_q4 /= 2;                                      // predict cooling cautiously
    int32_t pred_q4 = temp_q4 + rate_q4 * p(P_THM_LEAD);
    // Never regulate closer than 5 degC to the hard limit, which also watches the uncalibrated
    // reading (so a negative offset moves it down in calibrated terms).
    int32_t limit_c = min_of<int32_t>(p(P_THM_LIMIT), p(P_THM_SHUTDN) - 5 + min_of<int32_t>(p(P_THM_OFFSET), 0));
    int32_t err_q4 = clamp<int32_t>(pred_q4 - limit_c * 160, -ERR_MAX_Q4, ERR_MAX_Q4);
    if (first) g_prev_err_q4 = err_q4;                                  // no derivative kick at start
    int32_t derr_q4 = clamp<int32_t>(err_q4 - g_prev_err_q4, -DERR_MAX_Q4, DERR_MAX_Q4);
    g_prev_err_q4 = err_q4;

    // The integral term ignores the first 0.5 degC of error: a coarse sensor (1 degC steps)
    // then rests on one reading instead of driving a slow up-and-down cycle.
    int32_t err_i = err_q4 > DEAD_Q4 ? err_q4 - DEAD_Q4 : (err_q4 < -DEAD_Q4 ? err_q4 + DEAD_Q4 : 0);

    // delta [level/256 per step] = -256 * (KP/10 * d(err) + KI/10 * err * 0.1 s) with err in degC
    //                            = -(KP * derr_q4 * 10 + KI * err_q4) * 2 / 125
    // Bounded: |KP * derr * 10| <= 20 * 1600 * 10 and |KI * err| <= 12 * 32000, no overflow.
    // (The ranges of KP, KI and LEAD are limited to values that were tested not to oscillate.)
    int32_t s = (int32_t)p(P_THM_KP) * derr_q4 * 10 + (int32_t)p(P_THM_KI) * err_i;
    int32_t num = -2 * s + g_rem;
    int32_t delta = num / 125;
    g_rem = num - delta * 125;

    // Recovery is rate limited (THM_UP tenths of a level per second); far below the limit
    // (more than 10 degC) the cap simply climbs back at that rate.
    int32_t up_max = ((int32_t)p(P_THM_UP) * 256 + 50) / 100;
    if (delta > up_max || (err_q4 < -1600 && delta < up_max)) {
        delta = up_max;
        g_rem = 0;
    }

    int32_t floor_q8 = (int32_t)clamp<int16_t>(p(P_THM_FLOOR), 1, LEVEL_MAX) << 8;
    // When it is too hot and the light has been running steadily below the cap (a lower
    // level, or another limit such as low voltage), start regulating from the level in use
    // instead of first walking the cap down to it. Short levels (preview, blinks) are ignored.
    if (level_now != g_last_level) {
        g_last_level = level_now;
        g_steady = 0;
    } else if (g_steady < 255) {
        g_steady++;
    }
    int32_t now_q8 = (int32_t)level_now << 8;
    if (err_q4 > 0 && level_now > 0 && g_steady >= STEADY_STEPS && g_cap_q8 > now_q8 + 255) {
        g_cap_q8 = max_of(now_q8 + 255, floor_q8);
        g_rem = 0;
    }
    int32_t c = g_cap_q8 + delta;
    if (c < floor_q8 || c > CAP_MAX_Q8) g_rem = 0;
    g_cap_q8 = clamp<int32_t>(c, floor_q8, CAP_MAX_Q8);

    // --- output with hysteresis and dwell: never a visible flicker ---
    // The output level N is kept while the cap stays within [N - 0.5, N + 1.5), and after a
    // change the output does not move back the other way for 5 s (except down when it is
    // clearly too hot), so a noisy or coarse sensor cannot make it blink between two levels.
    int32_t out_q8 = (int32_t)g_cap_out << 8;
    int32_t next = g_cap_out;
    if (g_cap_q8 >= CAP_MAX_Q8) next = LEVEL_MAX;
    else if (g_cap_q8 >= out_q8 + 256 + HYST_Q8 || g_cap_q8 < out_q8 - HYST_Q8) next = g_cap_q8 >> 8;
    next = clamp<int32_t>(next, floor_q8 >> 8, LEVEL_MAX);
    if (next != g_cap_out) {
        int8_t dir = next > g_cap_out ? 1 : -1;
        bool reverse = g_out_dir != 0 && dir != g_out_dir && g_since_change < DWELL_STEPS;
        if (!reverse || (dir < 0 && err_q4 > HOT_Q4)) {
            g_cap_out = (uint8_t)next;
            g_out_dir = dir;
            g_since_change = 0;
        }
    }
    if (g_since_change < 255) g_since_change++;
}

}  // namespace thermal
}  // namespace lx
