// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_light.h"
#include "lx_aux.h"
#include "lx_battery.h"
#include "lx_board.h"
#include "lx_console.h"
#include "lx_input.h"
#include "lx_params.h"
#include "lx_ramp.h"
#include "lx_storage.h"
#include "lx_thermal.h"
#include "lx_ui.h"
#include "../hal/lx_hal.h"

namespace lx {
namespace light {

namespace {

constexpr uint16_t SLOW_MS = 100;           // sensor / protection update period
constexpr uint16_t IDLE_BEFORE_SLEEP_MS = 300;
constexpr uint16_t STUCK_MS = 10000;        // button held this long while dark = stuck (pocket)

uint8_t g_out = 0;            // smoothed output level
uint8_t g_req = 0;            // requested level (UI)
uint16_t g_slow_acc = 0;
uint16_t g_smooth_acc = 0;
uint32_t g_idle_ms = 0;       // time since the last button event
uint32_t g_off_ms = 0;        // time the light has been off (auto-lock)
uint32_t g_hold_ms = 0;       // how long the button has been held without a break
uint16_t g_cell_ma = 0;
uint8_t g_cell_cap = LEVEL_MAX;
bool g_usb = false;
bool g_stuck = false;         // button held down while dark for STUCK_MS: input is ignored
bool g_chg_window = true;     // last result of the charge temperature window

// Estimated cell current for an output level (needs the board's LED model). With the colour
// beam on, the colour LEDs' linear sinks draw their LED current straight from the cell.
uint16_t estimate_cell_ma(uint8_t level, uint16_t cell_mv) {
#if LX_HAS_COLOR
    if (ui::color_active()) {
        if (level == 0) return 0;
        uint16_t ma[3];
        ui::color_ma(level, ma);
        return (uint16_t)min_of<uint32_t>((uint32_t)ma[0] + ma[1] + ma[2], 65535u);
    }
#endif
#if LX_MAIN_MAX_MA > 0
    if (level == 0 || cell_mv < 500) return 0;
    uint32_t i_led = (uint32_t)ramp::power_of_level(level) * LX_MAIN_MAX_MA / 65535u;          // mA
    uint32_t v_led = LX_LED_VF0_MV + (uint32_t)LX_LED_RS_MOHM * i_led / 1000u;                 // mV
    uint32_t p_mw = v_led * i_led / 1000u;                      // mW (v_led * i_led < 2^32 for 60 A)
    uint32_t i_cell = (p_mw * 1000u / cell_mv) * 100u / (uint32_t)LX_DRIVER_EFF_PCT;          // mA
    if (i_cell > 65535u) i_cell = 65535u;
    return (uint16_t)i_cell;
#else
    (void)level;
    (void)cell_mv;
    return 0;
#endif
}

// Highest level whose estimated cell current stays within BAT_MAX_MA.
uint8_t cell_current_cap(uint16_t cell_mv) {
#if LX_MAIN_MAX_MA > 0
    int16_t lim = p(P_BAT_MAX_MA);
    if (lim <= 0) return LEVEL_MAX;
    uint8_t lo = 1, hi = LEVEL_MAX;
    if (estimate_cell_ma(1, cell_mv) > (uint16_t)lim) return 1;
    while (lo < hi) {
        uint8_t mid = (uint8_t)((lo + hi + 1) / 2);
        if (estimate_cell_ma(mid, cell_mv) <= (uint16_t)lim) lo = mid; else hi = (uint8_t)(mid - 1);
    }
    return lo;
#else
    (void)cell_mv;
    return LEVEL_MAX;
#endif
}

void slow_tasks() {
    g_usb = LX_HAS_CHARGER ? hal::usb_present() : false;
    uint16_t pack = hal::battery_mv();
    g_cell_ma = estimate_cell_ma(g_out, battery::cell_mv());
    battery::update(pack, g_cell_ma, g_out, g_usb);
    g_cell_cap = cell_current_cap(battery::cell_mv());

#if LX_HAS_TEMP
    thermal::update(hal::temperature(), g_out);
#endif

#if LX_HAS_CHARGER
    // Li-ion must only be charged inside its temperature window.
    bool temp_ok = true;
#if LX_HAS_TEMP
    int16_t t = thermal::temperature();
    temp_ok = !thermal::sensor_fault() && t >= 10 * p(P_CHG_TMIN) && t <= 10 * p(P_CHG_TMAX);
#endif
    g_chg_window = temp_ok;
    hal::set_charge(g_usb && temp_ok, temp_ok);
    uint8_t cs = hal::charger_status();
    if (g_usb && cs == hal::CHG_CHARGING) aux::set_status(aux::STATUS_CHARGING);
    else if (g_usb && cs == hal::CHG_DONE) aux::set_status(aux::STATUS_CHARGED);
    else if (g_out && battery::percent() < 10) aux::set_status(aux::STATUS_LOW);
    else aux::set_status(aux::STATUS_NONE);
#else
    aux::set_status((g_out && battery::percent() < 10) ? aux::STATUS_LOW : aux::STATUS_NONE);
#endif
}

void outputs_off() {
    hal::set_main(0);
    hal::set_laser(false);
    hal::set_side(0, 0);
    hal::set_color(0, 0, 0);
    hal::set_aux(0, 0, 0);
    g_out = 0;
}

void save_if_needed() {
    if (ui::memory_dirty()) {
        ui::Memory m = ui::memory();
        storage::State s;
        s.locked = m.locked;
        s.mem_level = m.level;
        s.color = m.color;
        if (storage::save_state(s)) ui::memory_saved();
    }
}

// Fresh readings before the first decision after a sleep.
void after_wake() {
    battery::prime(hal::battery_mv());
    thermal::resync();
    g_slow_acc = SLOW_MS;                      // sensor, charger and USB tasks in the next tick
}

void maybe_sleep() {
    ui::State st = ui::state();
    bool off = st == ui::S_OFF || st == ui::S_LOCK;

    // Pocket protection (design rule BAT-7): a press that does not end is a button squeezed
    // in a pocket or a bag. While the light is dark (off, locked, momentary moon from
    // lockout, laser timed out) it stops reacting after STUCK_MS. While the main LED is on
    // it switches off and locks after POCKET_S. A laser press is limited by LASER_S instead.
    if (input::pressed()) {
        if (g_hold_ms < 0xFFFF0000u) g_hold_ms += LX_TICK_MS;
    } else {
        g_hold_ms = 0;
        g_stuck = false;
    }
    bool pocket_moon = ui::momentary_from_lock();
    bool dark = off || pocket_moon || (st == ui::S_LASER && !ui::laser());
    uint32_t pocket_ms = (uint32_t)p(P_POCKET_S) * 1000u;
    if (!dark && !ui::laser() && pocket_ms > 0 && g_hold_ms >= pocket_ms) {
        ui::force_off();
        ui::lock_now();
        aux::event(aux::PAT_LOCK);
        if (g_hold_ms < STUCK_MS) g_hold_ms = STUCK_MS;   // continue below until released
        dark = true;
    }
    if (dark && g_hold_ms >= STUCK_MS) {
        g_stuck = true;                        // tick() ignores the button (no preview, no gestures)
        if (ui::state() != ui::S_OFF && ui::state() != ui::S_LOCK) ui::force_off();
        save_if_needed();
        // With USB power or an open console keep the normal 10 ms ticks: the charge
        // temperature window and the console need the 100 ms tasks.
        if (g_usb || console::active()) return;
        outputs_off();
        hal::sleep(2000, false);               // check again in 2 s; the button cannot wake us
        after_wake();
        if (!hal::button_down()) {
            input::reset(false);
            g_hold_ms = 0;
            g_idle_ms = 0;
            g_stuck = false;
        }
        return;
    }

    if (!off || !input::idle() || ui::busy() || aux::busy() || g_usb || console::active()) return;
    if (g_idle_ms < IDLE_BEFORE_SLEEP_MS) return;

    outputs_off();
    save_if_needed();

    uint32_t max_ms = 0;
    uint32_t autolock_ms = (uint32_t)p(P_AUTOLOCK) * 60000u;
    bool autolock = st == ui::S_OFF && autolock_ms > 0;
    if (autolock) max_ms = autolock_ms > g_off_ms ? autolock_ms - g_off_ms : 1;
#if LX_HAS_CHARGER
    // Outside the charge temperature window the port may not look for USB power, so wake up
    // once a minute to check the temperature: charging can then resume when the window opens.
    if (!g_chg_window && (max_ms == 0 || max_ms > 60000u)) max_ms = 60000u;
#endif

    uint32_t t0 = hal::millis();
    bool by_button = hal::sleep(max_ms, true);
    g_off_ms += (uint32_t)(hal::millis() - t0);

    if (!by_button && autolock && g_off_ms >= autolock_ms) {
        ui::lock_now();
        save_if_needed();
    }
    after_wake();
    input::reset(hal::button_down());
    g_idle_ms = 0;
}

}  // namespace

uint8_t output_level() { return g_out; }
uint8_t requested_level() { return g_req; }
uint16_t cell_ma() { return g_cell_ma; }

void init() {
    hal::init();                               // outputs safe first
    storage::load_params();
    ui::Memory m;
    m.level = (uint8_t)p(P_MEM_LEVEL);
    m.locked = 0;
    m.color = 0;
    storage::State s;
    if (storage::load_state(s)) {
        m.level = s.mem_level;
        m.locked = s.locked;
        m.color = s.color;
    }
    thermal::init();
    battery::init();
    aux::init();
    console::reset();
    ui::init(m);
    battery::prime(hal::battery_mv());
    input::reset(hal::button_down());
    g_out = g_req = 0;
    g_slow_acc = SLOW_MS;                      // run the sensor update in the first tick
    g_idle_ms = g_off_ms = g_hold_ms = 0;
    g_stuck = false;
    g_chg_window = true;
}

void tick() {
    const uint16_t dt = LX_TICK_MS;

    // 1. button
    input::Event e = input::update(hal::button_down(), dt, (uint16_t)p(P_CLICK_MS));
    if (e.type != input::EV_NONE && !g_stuck) {
        ui::handle(e);
        g_idle_ms = 0;
    } else if (g_idle_ms < 0xFFFF0000u) {
        g_idle_ms += dt;
    }

    // 2. sensors and protection (every 100 ms)
    g_slow_acc = (uint16_t)(g_slow_acc + dt);
    if (g_slow_acc >= SLOW_MS) {
        g_slow_acc = (uint16_t)(g_slow_acc - SLOW_MS);
        slow_tasks();
    }
    ui::tick(dt);
    if (battery::cutoff_event()) {
        ui::force_off();
        aux::event(aux::PAT_EMPTY);
    }
    if (thermal::shutdown() && ui::state() != ui::S_OFF && ui::state() != ui::S_LOCK) {
        ui::force_off();
        aux::event(aux::PAT_REFUSE);
    }

    // 3. requested level -> caps -> smoothing -> output
    uint8_t req = ui::level();
    bool inst = ui::instant();
    if (ui::state() == ui::S_OFF && p(P_PREVIEW) && input::pressed() && !g_stuck && !battery::empty() &&
        !thermal::shutdown()) {
        req = (uint8_t)p(P_RAMP_FLOOR);       // instant feedback while pressing from off
        inst = true;
    }
    g_req = req;
    uint8_t target = req;
    if (target) {
        target = min_of(target, thermal::cap());
        target = min_of(target, battery::cap());
        target = min_of(target, g_cell_cap);
        if (g_usb) target = min_of(target, (uint8_t)p(P_CHG_MAXLVL));
        if (target < 1) target = 1;
    }
    uint8_t smooth = (uint8_t)p(P_SMOOTH_MS);
    if (target == 0 || inst || smooth == 0) {
        g_out = target;
        g_smooth_acc = 0;
    } else {
        if (g_out == 0) g_out = min_of<uint8_t>(target, (uint8_t)p(P_RAMP_FLOOR));
        g_smooth_acc = (uint16_t)(g_smooth_acc + dt);
        while (g_smooth_acc >= smooth && g_out != target) {
            g_smooth_acc = (uint16_t)(g_smooth_acc - smooth);
            g_out = g_out < target ? (uint8_t)(g_out + 1) : (uint8_t)(g_out - 1);
        }
        if (g_out == target) g_smooth_acc = 0;
    }
    // the white beam, or the same level on the colour LEDs
#if LX_HAS_COLOR
    if (ui::color_active()) {
        uint16_t ma[3];
        ui::color_ma(g_out, ma);
        hal::set_main(0);
        hal::set_color(ma[0], ma[1], ma[2]);
    } else {
        hal::set_color(0, 0, 0);
        hal::set_main(ramp::power_of_level(g_out));
    }
#else
    hal::set_main(ramp::power_of_level(g_out));
#endif

    // 4. laser and side lights: the UI decides, protection can still veto
    bool aux_ok = !thermal::shutdown() && !battery::empty();
    hal::set_laser(ui::laser() && aux_ok);
    hal::set_side(aux_ok ? ui::side_red() : 0, aux_ok ? ui::side_uv() : 0);

    // 5. indicator, console, watchdog
    aux::tick(dt);
    console::poll();
    hal::watchdog_kick();

    // 6. off-time bookkeeping, persistence and sleep
    if (ui::state() == ui::S_OFF) {
        if (g_off_ms < 0xFFFF0000u) g_off_ms += dt;
    } else {
        g_off_ms = 0;
    }
    if (ui::state() == ui::S_OFF && ui::memory_dirty() && input::idle()) save_if_needed();
    maybe_sleep();
}

}  // namespace light
}  // namespace lx
