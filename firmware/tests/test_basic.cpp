// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour tests on the minimal board "host-sim-basic": PWM channel, no indicator LED,
// no laser, no charger. Checks the fallbacks the core uses when hardware is missing.
#include "../core/lx_params.h"
#include "../core/lx_ui.h"
#include "../ports/host/sim.h"
#include "lx_test.h"

using namespace lx;

namespace {
void fresh() {
    sim::Config c = sim::keychain_preset();
    sim::reset(c);
    sim::run_for(500);
}
int count_flashes(uint32_t t0, uint32_t t1) {
    int n = 0;
    bool prev = false;
    for (const sim::Sample& s : sim::log()) {
        if (s.t < t0 || s.t >= t1) continue;
        bool on = s.level > 0;
        if (on && !prev) n++;
        prev = on;
    }
    return n;
}
}  // namespace

TEST(click_hold_is_momentary_turbo_without_laser) {
    fresh();
    uint32_t t = sim::cursor();
    sim::hold(1, 2000);
    sim::run_to(t + 1200);
    CHECK(ui::state() == ui::S_MOMENT);
    CHECK_MSG(sim::level() >= 140, "momentary %u", sim::level());
    CHECK(!sim::laser());
    sim::run_script();
    CHECK(sim::level() == 0 && ui::state() == ui::S_OFF);
}

TEST(lock_confirms_with_main_led_blinks) {
    fresh();
    params::set(P_PREVIEW, 0);                   // so that only the confirmation blinks show
    sim::click(4);
    uint32_t t = sim::cursor();
    sim::run_script(1500);
    CHECK(ui::state() == ui::S_LOCK);
    int n = count_flashes(t - 400, t + 1500);
    CHECK_MSG(n == 3, "%d confirmation blinks", n);
}

TEST(basic_turbo_and_off) {
    fresh();
    sim::click(2);
    sim::run_script(300);
    CHECK(ui::turbo_active());
    sim::click(1);
    sim::run_script();
    CHECK(sim::level() == 0);
}

int main() { return lxt::run_all("sim (basic board)"); }
