// SPDX-License-Identifier: GPL-3.0-or-later
// Unit tests of the core modules that do not need the simulated world.
#include <cmath>
#include <cstring>

#include "../core/lx_input.h"
#include "../core/lx_params.h"
#include "../core/lx_ramp.h"
#include "../core/lx_storage.h"
#include "../hal/lx_hal.h"
#include "../hal/lx_ntc.h"
#include "../ports/host/sim.h"
#include "lx_test.h"

using namespace lx;

// ---- ramp ------------------------------------------------------------------------------
TEST(ramp_log2_matches_libm) {
    const uint32_t xs[] = {1, 2, 3, 7, 30, 64, 100, 1000, 12345, 32768, 65535};
    for (uint32_t x : xs) {
        double exact = std::log2(x / 65536.0) * 256.0;
        int16_t got = ramp::log2_q8_of_q16(x);
        CHECK_MSG(std::fabs(got - exact) <= 1.01, "x=%u got %d exact %.2f", x, got, exact);
    }
}

TEST(ramp_endpoints_and_monotonic) {
    CHECK(ramp::power_of_level(0) == 0);
    CHECK(ramp::power_of_level(LEVEL_MAX) == 65535);
    double p1 = ramp::power_of_level(1);
    CHECK_MSG(std::fabs(p1 - LX_OUT_MIN_Q16) / LX_OUT_MIN_Q16 < 0.03, "level 1 = %.0f, expected %d", p1,
              LX_OUT_MIN_Q16);
    for (int l = 2; l <= LEVEL_MAX; l++) {
        CHECK_MSG(ramp::power_of_level((uint8_t)l) >= ramp::power_of_level((uint8_t)(l - 1)), "level %d", l);
    }
}

TEST(ramp_geometric_spacing) {
    // Every step should be the same ratio: compare a low and a high step (where the
    // integer resolution is good enough) with the ideal ratio.
    double ideal = std::pow(65535.0 / LX_OUT_MIN_Q16, 1.0 / 149.0);
    for (int l : {60, 90, 120, 149}) {
        double r = (double)ramp::power_of_level((uint8_t)(l + 1)) / ramp::power_of_level((uint8_t)l);
        CHECK_MSG(std::fabs(r - ideal) < 0.01, "step %d ratio %.4f ideal %.4f", l, r, ideal);
    }
}

TEST(ramp_inverse) {
    for (int l = 1; l <= LEVEL_MAX; l++) {
        power_t pw = ramp::power_of_level((uint8_t)l);
        uint8_t back = ramp::level_of_power(pw);
        CHECK_MSG(ramp::power_of_level(back) == pw, "level %d -> power %u -> level %u", l, pw, back);
    }
    CHECK(ramp::level_of_power(0) == 0);
}

// ---- NTC table ---------------------------------------------------------------------------
TEST(ntc_table_matches_beta_equation) {
    constexpr lx::ntc::Table<100000, 100000, 4250> t{};
    for (uint32_t code = 80; code <= 940; code += 20) {
        double r = code / 1023.0;
        double rn = 100000.0 * r / (1.0 - r);
        double exact = (1.0 / (1.0 / 298.15 + std::log(rn / 100000.0) / 4250.0) - 273.15) * 10.0;
        int16_t got = t.temp_dc(code, 1023);
        CHECK_MSG(std::fabs(got - exact) <= 5.0, "code %u: %d vs %.1f dC", code, got, exact);
    }
    CHECK(t.temp_dc(512, 1023) > 240 && t.temp_dc(512, 1023) < 260);   // ~25 degC at mid-scale
    CHECK(t.temp_dc(1023, 1023) < -400);                                 // open sensor
    CHECK(t.temp_dc(0, 1023) > 1500);                                    // shorted sensor
}

// ---- parameters ---------------------------------------------------------------------------
TEST(params_defaults_and_ranges) {
    params::reset_defaults();
    for (uint8_t i = 0; i < P_COUNT; i++) {
        ParamId id = (ParamId)i;
        CHECK(params::get(id) == params::default_of(id));
        CHECK(params::min_of(id) <= params::max_of(id));
    }
    CHECK(params::set(P_THM_LIMIT, 45));
    CHECK(p(P_THM_LIMIT) == 45);
    CHECK(!params::set(P_THM_LIMIT, 200));          // out of range: refused, unchanged
    CHECK(p(P_THM_LIMIT) == 45);
    CHECK(params::find("THM_LIMIT") == P_THM_LIMIT);
    CHECK(params::find("thm_limit") == P_THM_LIMIT); // case-insensitive
    CHECK(params::find("NOPE") == -1);
    char buf[12];
    CHECK(params::name_of(P_RAMP_CEIL, buf, sizeof buf) && strcmp(buf, "RAMP_CEIL") == 0);
    params::reset_defaults();
}

TEST(params_layout_hash_is_stable) {
    uint16_t a = params::layout_hash(), b = params::layout_hash();
    CHECK(a == b);
    CHECK(a != 0);
}

// ---- storage ------------------------------------------------------------------------------
TEST(storage_params_roundtrip_and_corruption) {
    sim::reset(sim::keychain_preset());               // blank storage, firmware init
    params::reset_defaults();
    CHECK(params::set(P_RAMP_CEIL, 111));
    CHECK(storage::save_params());
    params::reset_defaults();
    CHECK(p(P_RAMP_CEIL) != 111);
    CHECK(storage::load_params());
    CHECK(p(P_RAMP_CEIL) == 111);
    // corrupt one value byte: the CRC must reject the block and defaults are used
    uint8_t b;
    hal::storage_read(10, &b, 1);
    b ^= 0x55;
    hal::storage_write(10, &b, 1);
    CHECK(!storage::load_params());
    CHECK(p(P_RAMP_CEIL) == params::default_of(P_RAMP_CEIL));
}

TEST(storage_state_ring) {
    sim::reset(sim::keychain_preset());
    storage::State s{0, 0, 0}, r{0, 0, 0};
    for (int i = 1; i <= 21; i++) {                   // wraps the 8-slot ring several times
        s.locked = (uint8_t)(i & 1);
        s.mem_level = (uint8_t)(i * 5);
        CHECK(storage::save_state(s));
    }
    CHECK(storage::load_state(r));
    CHECK(r.mem_level == 105 && r.locked == 1);
    // destroy the newest slot: the previous record must be found
    uint16_t ring = LX_STORAGE_SIZE - 32;
    for (int slot = 0; slot < 8; slot++) {
        uint8_t d[4];
        hal::storage_read((uint16_t)(ring + slot * 4), d, 4);
        if (d[2] == 105) { d[3] ^= 0xFF; hal::storage_write((uint16_t)(ring + slot * 4), d, 4); }
    }
    CHECK(storage::load_state(r));
    CHECK(r.mem_level == 100 && r.locked == 0);
}

// ---- input decoder -----------------------------------------------------------------------
namespace {
struct Seen { uint8_t type, count; };
std::vector<Seen> feed(const std::vector<std::pair<bool, int>>& pattern, uint16_t click_ms = 400) {
    // pattern: (level, duration in ms), sampled every 10 ms
    std::vector<Seen> out;
    input::reset(false);
    for (auto& seg : pattern) {
        for (int t = 0; t < seg.second; t += 10) {
            input::Event e = input::update(seg.first, 10, click_ms);
            if (e.type != input::EV_NONE && e.type != input::EV_HOLD_TICK) out.push_back({e.type, e.count});
        }
    }
    return out;
}
bool has(const std::vector<Seen>& v, uint8_t type, uint8_t count) {
    for (auto& s : v) if (s.type == type && s.count == count) return true;
    return false;
}
}  // namespace

TEST(input_single_double_triple_click) {
    auto v1 = feed({{true, 100}, {false, 600}});
    CHECK(has(v1, input::EV_CLICK, 1));
    auto v2 = feed({{true, 100}, {false, 150}, {true, 100}, {false, 600}});
    CHECK(has(v2, input::EV_CLICK, 2) && !has(v2, input::EV_CLICK, 1));
    auto v3 = feed({{true, 80}, {false, 120}, {true, 80}, {false, 120}, {true, 80}, {false, 600}});
    CHECK(has(v3, input::EV_CLICK, 3));
}

TEST(input_hold_and_click_hold) {
    auto h1 = feed({{true, 1000}, {false, 600}});
    CHECK(has(h1, input::EV_HOLD, 1) && has(h1, input::EV_HOLD_END, 1) && !has(h1, input::EV_CLICK, 1));
    auto h2 = feed({{true, 100}, {false, 150}, {true, 900}, {false, 600}});
    CHECK(has(h2, input::EV_HOLD, 2) && has(h2, input::EV_HOLD_END, 2));
}

TEST(input_debounce_rejects_bounce) {
    // contact bounce: 10 ms glitches must not create extra clicks
    auto v = feed({{true, 10}, {false, 10}, {true, 10}, {false, 10}, {true, 120}, {false, 10}, {true, 10},
                   {false, 600}});
    CHECK(has(v, input::EV_CLICK, 1));
    CHECK(!has(v, input::EV_CLICK, 2));
}

TEST(input_click_count_saturates) {
    std::vector<std::pair<bool, int>> pat;
    for (int i = 0; i < 12; i++) { pat.push_back({true, 60}); pat.push_back({false, 100}); }
    pat.push_back({false, 600});
    auto v = feed(pat);
    CHECK(has(v, input::EV_CLICK, input::MAX_COUNT));
}

int main() { return lxt::run_all("units"); }
