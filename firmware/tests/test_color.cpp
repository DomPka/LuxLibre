// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour tests on the board "host-sim-color": a white channel plus a colour beam (red, green and
// blue LEDs on linear sinks), no side lights. Checks the colour gestures, the colour list, the
// memories, the console, and that protection treats the colour LEDs like the white ones.
#include <string>

#include "../core/lx_color.h"
#include "../core/lx_light.h"
#include "../core/lx_params.h"
#include "../core/lx_ramp.h"
#include "../core/lx_ui.h"
#include "../ports/host/sim.h"
#include "lx_test.h"

using namespace lx;

namespace {

void fresh(sim::Config c = sim::keychain_preset()) {
    sim::reset(c);
    sim::run_for(500);
}

void set(ParamId id, int16_t v) { CHECK(params::set(id, v)); }

// What the firmware should ask for: colour idx at level lvl (ramp layout: full current at RAMP_CEIL).
void expect_ma(uint8_t lvl, uint8_t idx, uint16_t ma[3]) {
    color::currents_ma(lvl, (uint8_t)p(P_RAMP_CEIL), idx, ma);
}

bool only(int c) {
    for (int k = 0; k < 3; k++) {
        bool on = sim::color_req_ma(k) > 0;
        if (on != (k == c)) return false;
    }
    return true;
}

}  // namespace

TEST(five_clicks_from_off_turn_on_the_colour_beam) {
    fresh();
    sim::click(5);
    sim::run_script();
    CHECK(ui::state() == ui::S_ON && ui::color_active());
    CHECK_MSG(sim::led_a() == 0.0, "white LED %.3f A", sim::led_a());
    CHECK(only(0));                              // red first
    uint16_t ma[3];
    expect_ma(sim::level(), color::C_RED, ma);
    CHECK_MSG(sim::color_req_ma(0) == ma[0], "red %u mA, expected %u", sim::color_req_ma(0), ma[0]);
    CHECK(sim::level() == p(P_MEM_LEVEL));       // first use: MEM_LEVEL in the ramp layout
    CHECK(sim::color_lumens() > 0 && sim::lumens() == sim::color_lumens());
    sim::click(1);
    sim::run_script();
    CHECK(ui::state() == ui::S_OFF && sim::color_req_ma(0) == 0 && sim::color_a(0) == 0.0);
}

TEST(two_clicks_step_through_the_colour_set) {
    fresh();
    sim::click(5);
    sim::run_script();
    CHECK(only(0));
    uint32_t t2 = sim::cursor();
    sim::click(2);
    sim::run_to(t2 + 400 + 300);                 // the gesture ends 400 ms after the last click
    CHECK_MSG(sim::aux_g() == 255 && sim::aux_r() == 0 && sim::aux_b() == 0, "halo %u %u %u", sim::aux_r(),
              sim::aux_g(), sim::aux_b());       // the halo shows the new colour
    sim::run_script();
    CHECK_MSG(only(1), "green: %u %u %u", sim::color_req_ma(0), sim::color_req_ma(1), sim::color_req_ma(2));
    CHECK(ui::color_active() && !ui::turbo_active());   // two clicks are not turbo in the colour beam
    sim::click(2);
    sim::run_script();
    CHECK(only(2));
    sim::click(2);                               // the custom colour: amber (100 / 35 / 0) by default
    sim::run_script();
    uint16_t ma[3];
    expect_ma(sim::level(), color::C_CUSTOM, ma);
    CHECK_MSG(sim::color_req_ma(0) == ma[0] && sim::color_req_ma(1) == ma[1] && sim::color_req_ma(2) == 0,
              "custom %u %u %u", sim::color_req_ma(0), sim::color_req_ma(1), sim::color_req_ma(2));
    CHECK(ma[1] * 100 / ma[0] >= 33 && ma[1] * 100 / ma[0] <= 37);
    sim::click(2);                               // back to red
    sim::run_script();
    CHECK(only(0));
}

TEST(four_clicks_switch_between_white_and_colour) {
    fresh();
    sim::click(1);                               // white
    sim::run_script();
    uint8_t lvl = sim::level();
    CHECK(!ui::color_active() && sim::led_a() > 0 && sim::color_req_ma(0) == 0);
    sim::click(4);
    sim::run_script();
    CHECK(ui::color_active() && sim::led_a() == 0.0 && sim::color_req_ma(0) > 0);
    CHECK_MSG(sim::level() == lvl, "level %u -> %u", lvl, sim::level());
    sim::click(4);
    sim::run_script();
    CHECK(!ui::color_active() && sim::led_a() > 0 && sim::color_req_ma(0) == 0 && sim::level() == lvl);
    // from turbo: the colour beam takes the level before turbo
    sim::click(2);
    sim::run_script(300);
    CHECK(ui::turbo_active());
    sim::click(4);
    sim::run_script();
    CHECK(ui::color_active() && !ui::turbo_active() && sim::level() == lvl);
}

TEST(holding_changes_the_colour_brightness_up_to_full_current) {
    fresh();
    sim::click(5);
    sim::run_script();
    uint16_t before = sim::color_req_ma(0);
    sim::hold(0, 4000);                          // ramp up to the ceiling
    sim::run_script();
    CHECK_MSG(sim::level() == p(P_RAMP_CEIL), "level %u", sim::level());
    CHECK_MSG(sim::color_req_ma(0) == LX_COLOR_MAX_MA && before < LX_COLOR_MAX_MA, "red %u mA (before %u)",
              sim::color_req_ma(0), before);
    CHECK(ui::color_active());
    // the colour beam keeps its own level: the white beam still comes on at its own memory
    sim::click(1);
    sim::run_script();
    sim::click(1);
    sim::run_script();
    CHECK(!ui::color_active() && sim::level() == p(P_MEM_LEVEL));
    sim::click(1);
    sim::run_script();
    sim::click(5);                               // and the colour beam at the level it had
    sim::run_script();
    CHECK(ui::color_active() && sim::level() == p(P_RAMP_CEIL));
}

TEST(colour_is_remembered_through_a_power_cycle) {
    fresh();
    sim::click(5);
    sim::run_script();
    sim::click(2);                               // green
    sim::run_script();
    sim::click(1);
    sim::run_script();
    sim::run_for(2000);                          // saved while off
    sim::Config c = sim::keychain_preset();
    c.keep_storage = true;
    sim::reset(c);                               // power cycle, same EEPROM
    sim::run_for(500);
    CHECK(ui::color_index() == color::C_GREEN);
    sim::click(5);
    sim::run_script();
    CHECK(only(1));
}

TEST(colour_set_and_custom_colour) {
    fresh();
    set(P_COLOR_SET, 4);                         // blue only
    sim::click(5);
    sim::run_script();
    CHECK(only(2));
    sim::click(2);
    sim::run_script();
    CHECK(only(2));
    sim::click(1);
    sim::run_script();
    set(P_COLOR_SET, 128);                       // custom only, all zero -> red
    set(P_COL_R, 0);
    set(P_COL_G, 0);
    set(P_COL_B, 0);
    sim::click(5);
    sim::run_script();
    CHECK(only(0));
    sim::click(1);
    sim::run_script();
    set(P_COL_R, 50);                            // 50 / 0 / 25 -> red at 100 %, blue at 50 %
    set(P_COL_B, 25);
    sim::click(5);
    sim::run_script();
    CHECK_MSG(sim::color_req_ma(1) == 0 && sim::color_req_ma(2) * 2 >= sim::color_req_ma(0) - 2 &&
                  sim::color_req_ma(2) * 2 <= sim::color_req_ma(0) + 2,
              "custom %u %u %u", sim::color_req_ma(0), sim::color_req_ma(1), sim::color_req_ma(2));
}

TEST(colour_refused_in_lockout_and_on_an_empty_cell) {
    fresh();
    sim::click(4);                               // lockout
    sim::run_script();
    sim::click(5);
    sim::run_script();
    CHECK(ui::state() == ui::S_LOCK && sim::color_req_ma(0) == 0);
    sim::click(4);
    sim::run_script();
    sim::Config c = sim::keychain_preset();
    c.soc = 0.0;                                 // empty cell
    fresh(c);
    sim::run_for(2000);
    sim::click(5);
    sim::run_script();
    CHECK(!ui::color_active() && sim::color_req_ma(0) == 0);
}

TEST(cell_current_and_thermal_limit_cover_the_colour_leds) {
    fresh();
    set(P_COLOR_SET, 64);                        // white from the three colours: 3 x 1 A at the top, capped at 2.5 A
    sim::click(5);
    sim::run_script();
    sim::hold(0, 4000);
    sim::run_script();
    CHECK_MSG(sim::color_req_ma(0) == LX_COLOR_MAX_MA * LX_COLOR_SUM_MA / (3 * LX_COLOR_MAX_MA) &&
                  sim::color_req_ma(1) == sim::color_req_ma(0) && sim::color_req_ma(2) == sim::color_req_ma(0),
              "white mix %u %u %u", sim::color_req_ma(0), sim::color_req_ma(1), sim::color_req_ma(2));
    sim::run_for(300);
    uint32_t sum = (uint32_t)sim::color_req_ma(0) + sim::color_req_ma(1) + sim::color_req_ma(2);
    CHECK_MSG((uint32_t)light::cell_ma() + 5u >= sum && (uint32_t)light::cell_ma() <= sum + 5u, "cell %u mA, colour LEDs %u mA",
              light::cell_ma(), sum);
    // BAT_MAX_MA limits the colour LEDs too
    set(P_BAT_MAX_MA, 1500);
    sim::run_for(500);
    sum = (uint32_t)sim::color_req_ma(0) + sim::color_req_ma(1) + sim::color_req_ma(2);
    CHECK_MSG(sum <= 1500, "colour LEDs %u mA with BAT_MAX_MA 1500", sum);
    set(P_BAT_MAX_MA, 0);
    // long run at the top: the regulator holds the temperature (about 6-9 W of heat in the head)
    sim::run_for(600000);
    CHECK(ui::color_active());
    CHECK_MSG(sim::t_sensor() < p(P_THM_LIMIT) + 3, "sensor %.1f degC", sim::t_sensor());
    CHECK(sim::level() < p(P_RAMP_CEIL));
}

TEST(turbo_all_lights_the_colour_leds_too) {
    fresh();
    sim::click(2);                               // white turbo, TURBO_ALL = 0: colour LEDs off
    sim::run_script(1000);                       // the gesture, then the soft ramp up (SMOOTH_MS)
    CHECK(ui::turbo_active() && sim::led_a() > 2.0 && sim::color_req_ma(0) == 0);
    double lm_white = sim::lumens();
    sim::click(1);
    sim::run_script();
    set(P_TURBO_ALL, 1);
    sim::click(2);
    sim::run_script(1000);
    CHECK(ui::turbo_active() && sim::led_a() > 2.0);
    uint16_t r = sim::color_req_ma(0), g = sim::color_req_ma(1), b = sim::color_req_ma(2);
    CHECK_MSG(r > 0 && r == g && g == b && r + g + b <= LX_COLOR_SUM_MA, "colour LEDs %u %u %u", r, g, b);
    CHECK_MSG(sim::lumens() > lm_white + 50, "%.0f lm with the colour LEDs, %.0f without", sim::lumens(), lm_white);
    sim::click(2);                               // back from turbo: the colour LEDs go off
    sim::run_script();
    CHECK(!ui::turbo_active() && sim::color_req_ma(0) == 0 && sim::led_a() > 0);
    sim::click(1);
    sim::run_script();
}

TEST(console_colour_command) {
    fresh();
    sim::console_in("color 100");
    sim::run_for(200);
    std::string out = sim::console_take();
    CHECK_MSG(out.find("ok") != std::string::npos, "%s", out.c_str());
    CHECK(ui::color_active() && sim::color_req_ma(0) > 0);
    sim::console_in("status");
    sim::run_for(200);
    out = sim::console_take();
    CHECK_MSG(out.find("beam=colour") != std::string::npos && out.find("color=red") != std::string::npos, "%s",
              out.c_str());
    sim::console_in("set COL_G 80");
    sim::run_for(200);
    sim::console_take();
    sim::console_in("color 100 custom");          // any colour, also one outside COLOR_SET
    sim::run_for(200);
    out = sim::console_take();
    CHECK_MSG(out.find("ok") != std::string::npos && ui::color_index() == color::C_CUSTOM, "%s", out.c_str());
    CHECK(sim::color_req_ma(0) > 0 && sim::color_req_ma(1) * 100 / sim::color_req_ma(0) >= 78 &&
          sim::color_req_ma(1) * 100 / sim::color_req_ma(0) <= 82);
    sim::console_in("color 100 purple");
    sim::run_for(200);
    out = sim::console_take();
    CHECK(out.find("err unknown colour") != std::string::npos);
    sim::console_in("color 0");
    sim::run_for(200);
    CHECK(ui::state() == ui::S_OFF && sim::color_req_ma(0) == 0);
    sim::console_take();
    sim::click(4);                               // locked: the console may not light it
    sim::run_script();
    sim::console_in("color 100");
    sim::run_for(200);
    out = sim::console_take();
    CHECK(out.find("err") != std::string::npos && sim::color_req_ma(0) == 0);
}

int main() { return lxt::run_all("sim (colour board)"); }
