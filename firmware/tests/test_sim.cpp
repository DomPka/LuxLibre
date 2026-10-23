// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour tests: the complete firmware running against the simulated flashlight
// (board "host-sim": current driver, RGB indicator, laser, charger, NTC, console).
#include <algorithm>
#include <cmath>
#include <string>

#include "../core/lx_battery.h"
#include "../core/lx_params.h"
#include "../core/lx_ramp.h"
#include "../core/lx_storage.h"
#include "../core/lx_thermal.h"
#include "../core/lx_ui.h"
#include "../hal/lx_hal.h"
#include "../ports/host/sim.h"
#include "lx_test.h"

using namespace lx;

namespace {

void fresh(sim::Config c = sim::keychain_preset()) {
    sim::reset(c);
    sim::run_for(500);
}

// Number of off->on transitions of the main LED in [t0, t1).
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

double max_sensor(uint32_t t0, uint32_t t1) {
    double m = -100;
    for (const sim::Sample& s : sim::log()) if (s.t >= t0 && s.t < t1) m = std::max(m, s.t_sensor);
    return m;
}

void set(ParamId id, int v) { CHECK(params::set(id, (int16_t)v)); }

}  // namespace

// ---- basic button behaviour (ramp layout, defaults) ---------------------------------------
TEST(click_on_off_memory) {
    fresh();
    sim::click(1);
    sim::run_script();
    CHECK_MSG(sim::level() == p(P_MEM_LEVEL), "level %u", sim::level());
    CHECK(ui::state() == ui::S_ON);
    sim::click(1);
    sim::run_script();
    CHECK(sim::level() == 0 && ui::state() == ui::S_OFF);
}

TEST(hold_from_off_ramps_up_and_is_remembered) {
    fresh();
    sim::hold(0, 1400);            // 0.4 s to become a hold, then ~1 s of ramping
    sim::run_script(300);
    uint8_t lvl = sim::level();
    CHECK_MSG(lvl > 40 && lvl < 120, "ramped to %u", lvl);
    sim::click(1);                 // off
    sim::run_script();
    sim::click(1);                 // on again: same level
    sim::run_script();
    CHECK_MSG(sim::level() == lvl, "memory %u vs %u", sim::level(), lvl);
}

TEST(ramp_stops_at_ceiling_and_floor) {
    fresh();
    sim::hold(0, 4000);            // long hold: up to the ceiling and stop there
    sim::run_script(300);
    CHECK(sim::level() == p(P_RAMP_CEIL));
    sim::hold(1, 4000);            // click + hold: down to the floor
    sim::run_script(300);
    CHECK(sim::level() == p(P_RAMP_FLOOR));
}

TEST(double_click_turbo_and_timer) {
    fresh();
    set(P_TURBO_S, 5);
    sim::click(2);
    sim::run_script(1000);
    CHECK(ui::turbo_active());
    CHECK_MSG(sim::level() >= 140, "turbo level %u", sim::level());
    sim::run_for(6000);            // past TURBO_S
    CHECK_MSG(sim::level() <= p(P_TURBO_DOWN), "after turbo time %u", sim::level());
    sim::click(2);                 // back to the level before turbo
    sim::run_script(1000);
    CHECK(!ui::turbo_active());
    CHECK_MSG(sim::level() == p(P_MEM_LEVEL), "back to %u", sim::level());
}

TEST(lockout) {
    fresh();
    sim::click(4);
    sim::run_script();
    CHECK(ui::state() == ui::S_LOCK);
    sim::click(1);
    sim::run_script();
    CHECK(sim::level() == 0 && ui::state() == ui::S_LOCK);
    sim::click(2);
    sim::run_script();
    CHECK(sim::level() == 0);
    // hold = momentary moon, dark again after release
    uint32_t t = sim::cursor();
    sim::press_at(t, true);
    sim::press_at(t + 1500, false);
    sim::run_to(t + 1200);
    CHECK_MSG(sim::level() == p(P_RAMP_FLOOR), "momentary %u", sim::level());
    sim::run_to(t + 2000);
    CHECK(sim::level() == 0);
    sim::wait(500);
    sim::click(4);
    sim::run_script();
    CHECK(ui::state() == ui::S_OFF);
}

TEST(lockout_survives_reboot) {
    fresh();
    sim::click(4);
    sim::run_script(1500);
    sim::Config c = sim::keychain_preset();
    c.keep_storage = true;
    sim::reset(c);
    sim::run_for(300);
    CHECK(ui::state() == ui::S_LOCK);
}

TEST(battery_check_readout) {
    sim::Config c = sim::keychain_preset();
    c.soc = 0.75;                  // ~3.97 V at rest
    fresh(c);
    uint16_t mv = battery::rest_cell_mv();
    int tenths = (mv + 50) / 100;
    sim::click(3);
    uint32_t start = sim::cursor();
    sim::run_script(0);
    sim::run_to(start + 12000);
    int first = tenths / 10, second = tenths % 10;
    int flashes = count_flashes(start, start + 12000);
    // one full read-out = first + second blinks (a zero shows as one short blink); it repeats
    int per_round = (first ? first : 1) + (second ? second : 1);
    CHECK_MSG(flashes >= per_round, "%d.%d V: %d flashes, expected >= %d", first, second, flashes, per_round);
    CHECK(ui::state() == ui::S_BLINKY);
    sim::click(1);
    sim::run_script();
    CHECK(ui::state() == ui::S_OFF);
}

TEST(preview_while_pressing_from_off) {
    fresh();
    uint32_t t = sim::cursor();
    sim::press_at(t, true);
    sim::press_at(t + 200, false);
    sim::run_to(t + 120);
    CHECK_MSG(sim::level() == p(P_RAMP_FLOOR), "preview %u", sim::level());
}

// ---- other layouts --------------------------------------------------------------------------
TEST(modes_layout_hold_cycles) {
    fresh();
    set(P_UI_STYLE, 1);
    set(P_MODE_CNT, 3);
    sim::click(1);                               // on at MEM_LEVEL (remembered)
    sim::run_script();
    sim::hold(0, 500);                           // one step
    sim::run_script(200);
    uint8_t a = sim::level();
    CHECK_MSG(a == p(P_MODE_1) || a == p(P_MODE_2) || a == p(P_MODE_3), "mode level %u", a);
    sim::hold(0, 500);
    sim::run_script(200);
    uint8_t b = sim::level();
    CHECK(b != a);
    sim::click(1);
    sim::run_script();
    sim::hold(0, 1500);                          // hold from off = moon, stays on
    sim::run_script(300);
    CHECK(sim::level() == p(P_RAMP_FLOOR) && ui::state() == ui::S_ON);
}

TEST(simple_layout_is_capped) {
    fresh();
    set(P_UI_STYLE, 2);
    set(P_SIMPLE_MAX, 90);
    sim::click(2);                               // simple: 2C = SIMPLE_MAX, no turbo
    sim::run_script(1000);
    CHECK_MSG(sim::level() == 90, "simple 2C %u", sim::level());
    CHECK(!ui::turbo_active());
}

// ---- laser ----------------------------------------------------------------------------------
TEST(laser_gesture_and_limits) {
    fresh();
    set(P_LASER_S, 3);
    uint32_t t = sim::cursor();
    sim::hold(1, 6000);                          // click, then click-and-hold for 6 s
    sim::run_to(t + 1500);
    CHECK(sim::laser());
    CHECK(sim::level() == 0);                    // main LED stays off
    sim::run_to(t + 5000);                       // LASER_S = 3 s exceeded while still held
    CHECK(!sim::laser());
    sim::run_script();
    CHECK(!sim::laser() && ui::state() == ui::S_OFF);
}

TEST(laser_refused_in_lockout_and_when_hot) {
    fresh();
    sim::click(4);
    sim::run_script();
    uint32_t t0 = sim::cursor();
    sim::hold(1, 3000);
    sim::run_to(t0 + 1500);                      // checked while the button is still held
    CHECK(!sim::laser());
    sim::run_script();
    // unlock, heat up above LASER_TMAX
    sim::click(4);
    sim::run_script();
    sim::Config c = sim::keychain_preset();
    c.ambient_c = 65.0;
    fresh(c);
    sim::run_for(3000);
    uint32_t t = sim::cursor();
    sim::hold(1, 1500);
    sim::run_to(t + 1000);
    CHECK(!sim::laser());
}

// ---- side lights ----------------------------------------------------------------------------
TEST(side_light_gestures) {
    fresh();
    sim::click(5);                               // 5 clicks from off: side light, red first
    sim::run_script();
    CHECK(ui::state() == ui::S_SIDE);
    CHECK_MSG(sim::side_red() == (p(P_SIDE_RED) * 255 + 50) / 100 && sim::side_uv() == 0, "red %u uv %u",
              sim::side_red(), sim::side_uv());
    CHECK(sim::level() == 0);                    // the main LED stays off
    sim::click(2);                               // red -> UV
    sim::run_script();
    CHECK_MSG(sim::side_red() == 0 && sim::side_uv() == 255, "red %u uv %u", sim::side_red(), sim::side_uv());
    sim::run_for(5000);
    CHECK(!sim::sleeping() && sim::side_uv() == 255);
    sim::click(1);                               // off
    sim::run_script();
    CHECK(ui::state() == ui::S_OFF && sim::side_red() == 0 && sim::side_uv() == 0);
    sim::click(5);                               // the colour used last comes back
    sim::run_script();
    CHECK(sim::side_uv() == 255);
    sim::click(1);
    sim::run_script();
    set(P_SIDE_UV, 0);                           // no UV: two clicks keep the red light
    sim::click(5);
    sim::run_script();
    CHECK(sim::side_red() > 0 && sim::side_uv() == 0);
    sim::click(2);
    sim::run_script();
    CHECK(sim::side_red() > 0 && sim::side_uv() == 0);
    sim::click(1);
    sim::run_script();
    CHECK(sim::side_red() == 0);
}

TEST(side_light_refused_in_lockout_and_by_protection) {
    fresh();
    sim::click(4);                               // lockout
    sim::run_script();
    sim::click(5);
    sim::run_script();
    CHECK(ui::state() == ui::S_LOCK && sim::side_red() == 0 && sim::side_uv() == 0);
    sim::click(4);
    sim::run_script();
    // pocket protection: a button held for POCKET_S while a side light is on locks the light
    set(P_POCKET_S, 5);
    sim::click(5);
    sim::run_script();
    CHECK(sim::side_red() > 0);
    uint32_t t = sim::cursor();
    sim::hold(0, 8000);
    sim::run_to(t + 7000);
    CHECK_MSG(sim::side_red() == 0 && ui::state() == ui::S_LOCK, "red %u state %u", sim::side_red(), ui::state());
    sim::run_script();
    // an empty cell refuses the side light
    sim::Config c = sim::keychain_preset();
    c.soc = 0.0;
    fresh(c);
    sim::click(5);
    sim::run_script();
    CHECK(sim::side_red() == 0 && sim::side_uv() == 0 && ui::state() != ui::S_SIDE);
}

// ---- thermal regulation -------------------------------------------------------------------
TEST(thermal_regulation_keychain) {
    sim::Config c = sim::keychain_preset();
    fresh(c);
    set(P_TURBO_S, 0);                           // no timer: only the thermal regulator limits turbo
    sim::click(2);
    sim::run_script(1000);
    uint32_t t0 = sim::now();
    sim::run_for(15 * 60 * 1000);                // 15 minutes
    double limit = p(P_THM_LIMIT);
    double peak = max_sensor(t0, sim::now());
    CHECK_MSG(peak <= limit + 3.0, "peak %.1f C, limit %.0f C", peak, limit);
    // settled: the last 3 minutes stay between limit - 4 C and limit + 2 C
    double lo = 1e9, hi = -1e9;
    for (const sim::Sample& s : sim::log()) {
        if (s.t + 180000 < sim::now()) continue;
        lo = std::min(lo, s.t_sensor);
        hi = std::max(hi, s.t_sensor);
    }
    CHECK_MSG(hi <= limit + 2.0 && lo >= limit - 4.0, "last 3 min: %.1f ... %.1f C", lo, hi);
    CHECK_MSG(sim::level() < 150 && sim::level() >= p(P_THM_FLOOR), "regulated level %u", sim::level());
}

TEST(thermal_regulation_18650) {
    sim::Config c = sim::edc18650_preset();
    fresh(c);
    set(P_TURBO_S, 0);
    sim::click(2);
    sim::run_script(1000);
    uint32_t t0 = sim::now();
    sim::run_for(12 * 60 * 1000);
    double limit = p(P_THM_LIMIT);
    double peak = max_sensor(t0, sim::now());
    CHECK_MSG(peak <= limit + 3.0, "peak %.1f C, limit %.0f C", peak, limit);
}

// Thermal regulation must never be visible as flicker: with a noisy, coarse sensor
// (1 degC steps like the ATtiny internal sensor) the output level may wander slowly,
// but a step up must never follow a step down (or the reverse) within 5 seconds.
void check_no_flicker(sim::Config c, const char* name) {
    fresh(c);
    set(P_TURBO_S, 0);
    sim::click(2);
    sim::run_script(1000);
    uint32_t t0 = sim::now();
    sim::run_for(10 * 60 * 1000);
    int changes = 0, late_changes = 0, last_dir = 0;
    uint32_t last_t = 0, min_gap = 0xFFFFFFFF;
    uint8_t prev = 0;
    for (const sim::Sample& s : sim::log()) {
        if (s.t < t0) { prev = s.level; continue; }
        if (s.level != prev) {
            int dir = s.level > prev ? 1 : -1;
            if (last_dir && dir != last_dir) min_gap = std::min(min_gap, s.t - last_t);
            last_dir = dir;
            last_t = s.t;
            changes++;
            if (s.t + 5 * 60 * 1000 > sim::now()) late_changes++;
        }
        prev = s.level;
    }
    CHECK_MSG(min_gap >= 5000, "%s: level reversed after %u ms", name, (unsigned)min_gap);
    CHECK_MSG(late_changes <= 20, "%s: %d level changes in the last 5 min", name, late_changes);
    CHECK_MSG(changes > 5, "%s: the regulator did not act (%d changes)", name, changes);
}

TEST(thermal_regulation_does_not_flicker) {
    sim::Config c = sim::keychain_preset();
    c.sensor_noise_c = 0.4;
    c.sensor_step_c = 1.0;
    check_no_flicker(c, "keychain, 1 degC sensor");
    c = sim::edc18650_preset();
    c.sensor_noise_c = 0.4;
    check_no_flicker(c, "18650");
}

// The regulator must stay calm at the ends of its parameter ranges too (FW-5: a user cannot
// set it into oscillation).
TEST(thermal_regulation_calm_at_parameter_limits) {
    const int kp[] = {10, 20, 20, 10, 10, 20, 20, 10};
    const int ki[] = {12, 12, 1, 1, 12, 12, 1, 1};
    const int lead[] = {10, 10, 10, 10, 0, 0, 0, 0};
    for (int i = 0; i < 8; i++) {
        sim::Config c = sim::keychain_preset();
        c.sensor_noise_c = 0.4;
        fresh(c);
        set(P_THM_KP, kp[i]);
        set(P_THM_KI, ki[i]);
        set(P_THM_LEAD, lead[i]);
        set(P_TURBO_S, 0);
        sim::click(2);
        sim::run_script(1000);
        uint32_t t0 = sim::now();
        sim::run_for(10 * 60 * 1000);
        int last_dir = 0, reversals_fast = 0, late_changes = 0;
        uint32_t last_t = 0;
        uint8_t prev = 0, lo = 255, hi = 0;
        for (const sim::Sample& s : sim::log()) {
            if (s.t < t0) { prev = s.level; continue; }
            bool late = s.t + 5 * 60 * 1000 > sim::now();
            if (late) { lo = std::min(lo, s.level); hi = std::max(hi, s.level); }
            if (s.level != prev) {
                int dir = s.level > prev ? 1 : -1;
                if (last_dir && dir != last_dir && s.t - last_t < 5000) reversals_fast++;
                last_dir = dir;
                last_t = s.t;
                if (late) late_changes++;
            }
            prev = s.level;
        }
        CHECK_MSG(reversals_fast == 0, "KP=%d KI=%d LEAD=%d: %d fast reversals", kp[i], ki[i], lead[i], reversals_fast);
        // no slow limit cycle either: in the last 5 minutes the level settles (or drifts slowly)
        CHECK_MSG(late_changes <= 25 && hi - lo <= 10, "KP=%d KI=%d LEAD=%d: %d changes over %d levels in the last 5 min",
                  kp[i], ki[i], lead[i], late_changes, hi - lo);
        CHECK_MSG(max_sensor(t0, sim::now()) <= p(P_THM_LIMIT) + 5.0, "KP=%d KI=%d: peak %.1f C", kp[i], ki[i],
                  max_sensor(t0, sim::now()));
    }
}

// A short press from off (preview) or a blink must not pull the thermal cap down to the floor.
TEST(thermal_cap_survives_a_short_off) {
    fresh();
    set(P_TURBO_S, 0);
    sim::click(2);
    sim::run_script(1000);
    sim::run_for(5 * 60 * 1000);                 // regulated at the limit
    uint8_t before = sim::level();
    sim::click(1);                               // off ...
    sim::wait(1500);
    sim::click(2);                               // ... and turbo again
    sim::run_script(1500);
    CHECK_MSG(sim::level() + 3 >= before, "regulated level %u, after a short off %u", before, sim::level());
}

TEST(thermal_shutdown_and_refuse) {
    sim::Config c = sim::keychain_preset();
    c.ambient_c = 85.0;                          // hotter than THM_SHUTDN
    fresh(c);
    sim::run_for(2000);
    CHECK(thermal::shutdown());
    sim::click(1);
    sim::run_script();
    CHECK(sim::level() == 0);
}

TEST(sensor_fault_limits_output) {
    sim::Config c = sim::keychain_preset();
    c.sensor_open = true;
    fresh(c);
    CHECK(thermal::sensor_fault());
    sim::click(2);                               // turbo request
    sim::run_script(500);
    CHECK_MSG(sim::level() <= p(P_THM_FLOOR), "with a broken sensor: %u", sim::level());
    sim::click(1);
    sim::run_script();
    uint32_t t = sim::cursor();
    sim::hold(1, 3000);                          // no laser either
    sim::run_to(t + 1500);                       // checked while the button is still held
    CHECK(!sim::laser());
    sim::run_script(0);
}

// ---- low-voltage protection -----------------------------------------------------------------
TEST(lvp_cannot_be_set_below_the_chemistry_floor) {
    sim::Config c = sim::keychain_preset();
    c.soc = 0.06;
    c.capacity_mah = 150;
    fresh(c);
    set(P_LVP_WARN, 900);                        // allowed by the range (NiMH), but BAT_CHEM = Li-ion
    set(P_LVP_CUT, 900);
    set(P_TURBO_S, 0);
    sim::click(2);
    sim::run_script(1000);
    sim::run_for(15 * 60 * 1000);
    double vmin = 9;
    for (const sim::Sample& s : sim::log()) if (s.level > 0) vmin = std::min(vmin, s.v_pack);
    CHECK_MSG(sim::level() == 0 && battery::empty(), "level %u, empty %d", sim::level(), battery::empty());
    CHECK_MSG(vmin > 2.55, "the cell was run down to %.2f V under load", vmin);
}

TEST(lvp_steps_down_then_cuts_off) {
    sim::Config c = sim::keychain_preset();
    c.soc = 0.06;                                // nearly empty
    c.capacity_mah = 150;                        // runs down quickly
    fresh(c);
    set(P_TURBO_S, 0);
    set(P_THM_LIMIT, 70);                        // keep thermal out of the way
    set(P_THM_SHUTDN, 100);
    sim::click(2);
    sim::run_script(1000);
    uint32_t t0 = sim::now();
    bool stepped = false;
    for (int i = 0; i < 600 && ui::state() == ui::S_ON; i++) {
        sim::run_for(1000);
        if (battery::cap() < LEVEL_MAX) stepped = true;
    }
    CHECK(stepped);
    CHECK_MSG(ui::state() == ui::S_OFF, "state %d after %u s", ui::state(), (sim::now() - t0) / 1000);
    CHECK(battery::empty());
    sim::click(1);                               // refused
    sim::run_script();
    CHECK(sim::level() == 0);
    sim::usb_at(sim::now() + 100, true);         // USB power releases the latch
    sim::run_for(1000);
    CHECK(!battery::empty());
}

// ---- charging -------------------------------------------------------------------------------
TEST(charging_status_and_temperature_window) {
    sim::Config c = sim::keychain_preset();
    c.soc = 0.5;
    fresh(c);
    sim::usb_at(sim::now() + 100, true);
    sim::run_for(4000);
    CHECK(hal::charger_status() == hal::CHG_CHARGING);
    double s0 = sim::soc();
    sim::run_for(60000);
    CHECK(sim::soc() > s0);
    // too cold for charging
    sim::Config cold = sim::keychain_preset();
    cold.soc = 0.5;
    cold.ambient_c = -5.0;
    fresh(cold);
    sim::usb_at(sim::now() + 100, true);
    sim::run_for(4000);
    CHECK(hal::charger_status() != hal::CHG_CHARGING);
}

// ---- console ----------------------------------------------------------------------------------
TEST(console_get_set_save) {
    fresh();
    sim::console_in("set THM_LIMIT 45");
    sim::run_for(100);
    std::string r = sim::console_take();
    CHECK_MSG(r.find("THM_LIMIT=45") != std::string::npos && r.find("ok") != std::string::npos, "%s", r.c_str());
    sim::console_in("set THM_LIMIT 99");
    sim::run_for(100);
    r = sim::console_take();
    CHECK(r.find("err range") != std::string::npos);
    sim::console_in("save");
    sim::run_for(100);
    sim::console_take();
    sim::Config c = sim::keychain_preset();
    c.keep_storage = true;
    sim::reset(c);
    sim::run_for(100);
    CHECK(p(P_THM_LIMIT) == 45);
    sim::console_in("status");
    sim::run_for(100);
    r = sim::console_take();
    CHECK(r.find("state=off") != std::string::npos);
    sim::console_in("level 80");
    sim::run_for(1000);
    CHECK(sim::level() == 80);
}

// ---- convenience and safety features --------------------------------------------------------
TEST(autolock_after_idle) {
    fresh();
    set(P_AUTOLOCK, 1);
    sim::run_for(65000);
    CHECK(ui::state() == ui::S_LOCK);
}

TEST(stuck_button_in_lockout_goes_dark) {
    fresh();
    sim::click(4);
    sim::run_script();
    uint32_t t = sim::cursor();
    sim::press_at(t, true);                      // pressed in a pocket for 30 s
    sim::press_at(t + 30000, false);
    sim::run_to(t + 5000);
    CHECK(sim::level() == p(P_RAMP_FLOOR));      // momentary moon at first
    sim::run_to(t + 15000);
    CHECK(sim::level() == 0);                    // then dark after 10 s
    sim::run_to(t + 31000);
    CHECK(ui::state() == ui::S_LOCK);
}

// A stuck button must not stop the 100 ms tasks while USB is connected: the charge
// temperature window (CHG-3) still has to act within seconds.
TEST(stuck_button_keeps_the_charge_window_working) {
    sim::Config c = sim::keychain_preset();
    c.soc = 0.5;
    c.c_head = 1.0;                               // a tiny, fast model so that it heats in seconds
    c.c_body = 2.0;
    c.r_body_amb = 2.0;
    c.sensor_tau_s = 1.0;
    fresh(c);
    sim::click(4);                                // locked, in a bag ...
    sim::run_script();
    uint32_t t = sim::cursor();
    sim::usb_at(t, true);                         // ... on a charger ...
    sim::press_at(t + 1000, true);                // ... with the button squeezed
    sim::ambient_at(t + 15000, 70.0);             // and the bag gets hot
    sim::press_at(t + 90000, false);
    sim::run_to(t + 12000);
    CHECK(hal::charger_status() == hal::CHG_CHARGING);
    // find when the sensor passes CHG_TMAX and check that charging stopped soon after
    sim::run_to(t + 60000);
    uint32_t t_hot = 0;
    for (const sim::Sample& s : sim::log())
        if (!t_hot && s.t > t && s.t_sensor > p(P_CHG_TMAX) + 1.0) t_hot = s.t;
    CHECK(t_hot > 0);
    CHECK_MSG(hal::charger_status() != hal::CHG_CHARGING, "still charging at %.1f C", sim::t_sensor());
    CHECK_MSG(t_hot && t_hot + 5000 < t + 60000, "sensor passed the window late (%u ms)", (unsigned)(t_hot - t));
    sim::run_script();
}

// On USB the firmware keeps ticking while the button is stuck (no naps); the main LED must
// still stay dark: no preview light and no gestures while the button is considered stuck.
TEST(stuck_button_on_usb_stays_dark) {
    fresh();
    set(P_LASER_S, 3);
    uint32_t t = sim::cursor();
    sim::usb_at(t, true);
    sim::hold(1, 60000);                          // laser gesture, then the button stays pressed
    sim::run_to(t + 2000);
    CHECK(sim::laser());
    sim::run_to(t + 20000);                       // laser timed out, button still held
    CHECK_MSG(!sim::laser() && sim::level() == 0, "laser %d, level %u", sim::laser(), sim::level());
    sim::run_to(t + 55000);
    CHECK_MSG(sim::level() == 0, "level %u while stuck on USB", sim::level());
    sim::run_script();
    CHECK(sim::level() == 0);
}

TEST(stuck_button_while_on_switches_off_and_locks) {
    fresh();
    uint32_t t = sim::cursor();
    sim::press_at(t, true);                      // squeezed in a pocket from off, unlocked
    sim::press_at(t + 45000, false);
    sim::run_to(t + 5000);
    CHECK_MSG(sim::level() > 0, "a hold from off ramps up (level %u)", sim::level());
    uint32_t pocket = (uint32_t)p(P_POCKET_S) * 1000u;
    sim::run_to(t + pocket + 500);
    CHECK_MSG(sim::level() == 0 && ui::state() == ui::S_LOCK, "after POCKET_S: level %u, state %s",
              sim::level(), ui::state_name(ui::state()));
    sim::run_to(t + 47000);
    sim::wait(500);
    sim::click(1);                               // stays locked after the release
    sim::run_script();
    CHECK(sim::level() == 0 && ui::state() == ui::S_LOCK);
    sim::click(4);
    sim::run_script();
    CHECK(ui::state() == ui::S_OFF);
    // POCKET_S = 0 switches the protection off
    set(P_POCKET_S, 0);
    t = sim::cursor();
    sim::press_at(t, true);
    sim::press_at(t + 40000, false);
    sim::run_to(t + 39000);
    CHECK(sim::level() > 0 && ui::state() == ui::S_ON);
}

TEST(factory_reset_nine_clicks) {
    fresh();
    set(P_RAMP_CEIL, 99);
    sim::click(9);
    sim::run_script(2000);
    CHECK(p(P_RAMP_CEIL) == params::default_of(P_RAMP_CEIL));
}

TEST(calibration_survives_reset_and_new_parameter_list) {
    fresh();
    set(P_BAT_CAL, 45);
    set(P_THM_OFFSET, -3);
    set(P_RAMP_CEIL, 99);
    CHECK(storage::save_params());
    sim::click(9);                               // factory reset keeps the calibration
    sim::run_script(2000);
    CHECK(p(P_RAMP_CEIL) == params::default_of(P_RAMP_CEIL));
    CHECK_MSG(p(P_BAT_CAL) == 45 && p(P_THM_OFFSET) == -3, "after 9C: BAT_CAL %d THM_OFFSET %d",
              p(P_BAT_CAL), p(P_THM_OFFSET));
    // A firmware with a different parameter list ignores the old parameter block, but the
    // calibration block survives.
    const uint8_t junk[2] = {'X', 'X'};
    CHECK(hal::storage_write(0, junk, 2));
    sim::Config c = sim::keychain_preset();
    c.keep_storage = true;
    sim::reset(c);
    sim::run_for(300);
    CHECK_MSG(p(P_BAT_CAL) == 45 && p(P_THM_OFFSET) == -3, "after reboot: BAT_CAL %d THM_OFFSET %d",
              p(P_BAT_CAL), p(P_THM_OFFSET));
    // console: "defaults" keeps it, "defaults all" clears it
    sim::console_in("defaults");
    sim::run_for(100);
    CHECK(p(P_BAT_CAL) == 45);
    sim::console_in("defaults all");
    sim::run_for(100);
    std::string r = sim::console_take();
    CHECK_MSG(p(P_BAT_CAL) == 0 && p(P_THM_OFFSET) == 0, "%s", r.c_str());
    sim::console_in("wdtest");                   // refused in the simulator
    sim::run_for(100);
    r = sim::console_take();
    CHECK_MSG(r.find("err") != std::string::npos, "%s", r.c_str());
}

TEST(sleeps_when_off) {
    fresh();
    uint32_t before = sim::sleep_ms_total();
    sim::run_for(3000);
    CHECK_MSG(sim::sleep_ms_total() - before > 2000, "slept %u ms of 3000", sim::sleep_ms_total() - before);
    // a click from sleep still works
    sim::click(1);
    sim::run_script();
    CHECK(ui::state() == ui::S_ON);
}

int main() { return lxt::run_all("sim (full board)"); }
