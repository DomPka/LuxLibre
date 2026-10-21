// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_ui.h"
#include "lx_aux.h"
#include "lx_battery.h"
#include "lx_board.h"
#include "lx_params.h"
#include "lx_storage.h"
#include "lx_thermal.h"

namespace lx {
namespace ui {

using namespace input;

#define EVB(type, count) (uint8_t)(((type) << 4) | (count))

// ---------------------------------------------------------------------------------------
// The button map. First matching line wins, so specific click counts come before "any".
const Binding k_bindings[] LX_FLASH = {
    // ---- light off ----
    {L_ALL,            S_OFF,    EVB(EV_CLICK, 1),     A_ON_MEM, 0},
    {L_RAMP,           S_OFF,    EVB(EV_HOLD, 1),      A_ON_FLOOR_RAMP, 0},
    {L_MODES | L_SIMPLE, S_OFF,  EVB(EV_HOLD, 1),      A_ON_FLOOR, 0},
    {L_RAMP | L_MODES, S_OFF,    EVB(EV_CLICK, 2),     A_TURBO_FROM_OFF, 0},
    {L_SIMPLE,         S_OFF,    EVB(EV_CLICK, 2),     A_ON_LEVEL, LV_SIMPLE},
    {L_ALL,            S_OFF,    EVB(EV_HOLD, 2),      A_LASER_OR_MOMENT, 0},
    {L_ALL,            S_OFF,    EVB(EV_CLICK, 3),     A_BATTCHECK, 0},
    {L_ALL,            S_OFF,    EVB(EV_CLICK, 4),     A_LOCK, 0},
    {L_ALL,            S_OFF,    EVB(EV_CLICK, 9),     A_FACTORY_RESET, 0},
    // ---- light on ----
    {L_ALL,            S_ON,     EVB(EV_CLICK, 1),     A_OFF, 0},
    {L_RAMP,           S_ON,     EVB(EV_HOLD, 1),      A_RAMP, 0},
    {L_RAMP,           S_ON,     EVB(EV_HOLD, 2),      A_RAMP, 1},
    {L_RAMP,           S_ON,     EVB(EV_HOLD_TICK, 0), A_RAMP_TICK, 0},
    {L_RAMP,           S_ON,     EVB(EV_HOLD_END, 0),  A_RAMP_END, 0},
    {L_MODES | L_SIMPLE, S_ON,   EVB(EV_HOLD, 1),      A_MODE_NEXT, 0},
    {L_MODES | L_SIMPLE, S_ON,   EVB(EV_HOLD_TICK, 1), A_MODE_TICK, 0},
    {L_MODES | L_SIMPLE, S_ON,   EVB(EV_HOLD_END, 1),  A_MODE_END, 0},
    {L_RAMP | L_MODES, S_ON,     EVB(EV_CLICK, 2),     A_TURBO_TOGGLE, 0},
    {L_ALL,            S_ON,     EVB(EV_CLICK, 3),     A_BATTCHECK, 0},
    // ---- lockout ----
    {L_ALL,            S_LOCK,   EVB(EV_CLICK, 4),     A_UNLOCK, 0},
    {L_ALL,            S_LOCK,   EVB(EV_CLICK, 0),     A_TICK_BLINK, 0},
    {L_ALL,            S_LOCK,   EVB(EV_HOLD, 1),      A_MOMENT, LV_FLOOR},
    // ---- blinky group (battery check, temperature, beacon, SOS, strobe) ----
    {L_ALL,            S_BLINKY, EVB(EV_CLICK, 1),     A_OFF, 0},
    {L_RAMP | L_MODES, S_BLINKY, EVB(EV_CLICK, 2),     A_BLINKY_NEXT, 0},
    // ---- held states ----
    {L_ALL,            S_LASER,  EVB(EV_HOLD_END, 0),  A_LASER_END, 0},
    {L_ALL,            S_MOMENT, EVB(EV_HOLD_END, 0),  A_MOMENT_END, 0},
};

namespace {

State g_state = S_OFF;
State g_prev_state = S_OFF;   // for momentary
uint8_t g_level = 0;          // chosen level while on
uint8_t g_mem = 70;           // memorised level
bool g_locked = false;
bool g_mem_dirty = false;

bool g_turbo = false;
uint8_t g_before_turbo = 0;
uint32_t g_turbo_ms = 0;

bool g_ramping = false;
int8_t g_ramp_dir = 1;
uint16_t g_ramp_acc = 0;
bool g_ramp_flashed = false;
uint16_t g_flash_ms = 0;      // short dark flash at the end of the ramp

bool g_mode_holding = false;
uint16_t g_mode_acc = 0;

uint8_t g_moment_level = 0;
bool g_moment = false;

uint8_t g_blinky = B_BATT;
uint32_t g_seq_t = 0;         // time in the blinky sequence
uint8_t g_seq_value = 0;      // value being read out

uint32_t g_laser_ms = 0;
bool g_laser_cut = false;

uint8_t g_fb_count = 0;       // feedback blinks on the main LED (boards without aux LED)
uint16_t g_fb_t = 0;
bool g_out_on = false;        // current blink phase (for instant())

uint8_t resolve(uint8_t code) {
    switch (code) {
    case LV_FLOOR: return (uint8_t)p(P_RAMP_FLOOR);
    case LV_CEIL: return (uint8_t)p(P_RAMP_CEIL);
    case LV_TURBO: return (uint8_t)p(P_TURBO_LVL);
    case LV_SIMPLE: return (uint8_t)p(P_SIMPLE_MAX);
    default: return code;
    }
}

uint8_t floor_lvl() { return (uint8_t)p(P_RAMP_FLOOR); }
uint8_t ceil_lvl() { return (uint8_t)max_of(p(P_RAMP_CEIL), p(P_RAMP_FLOOR)); }

bool aux_available() { return LX_HAS_AUX_RGB && p(P_AUX_MODE) != 0; }

void feedback(uint8_t blinks) {
    // Confirmation for boards without an indicator LED: short blinks at the floor level.
    if (!aux_available()) {
        g_fb_count = blinks;
        g_fb_t = 0;
    }
}

bool switch_on_allowed() {
    if (battery::empty()) {
        aux::event(aux::PAT_EMPTY);
        feedback(5);
        return false;
    }
    if (thermal::shutdown()) {
        aux::event(aux::PAT_REFUSE);
        feedback(1);
        return false;
    }
    return true;
}

void set_mem(uint8_t lvl) {
    if (p(P_MEMORY) && lvl != g_mem && lvl >= 1 && lvl <= LEVEL_MAX) {
        g_mem = lvl;
        g_mem_dirty = true;
    }
}

void go_on(uint8_t lvl) {
    g_state = S_ON;
    g_level = clamp<uint8_t>(lvl, 1, LEVEL_MAX);
    g_turbo = false;
    g_ramping = false;
    g_mode_holding = false;
    battery::user_action();
    aux::event(aux::PAT_BATTERY, battery::percent());
}

void go_off() {
    g_state = S_OFF;
    g_turbo = false;
    g_ramping = false;
    g_mode_holding = false;
    g_moment = false;
    g_laser_cut = false;
}

uint8_t mode_level(uint8_t i) { return (uint8_t)p((ParamId)(P_MODE_1 + i)); }

void step_mode() {
    uint8_t n = (uint8_t)p(P_MODE_CNT);
    int8_t idx = -1;
    if (!g_turbo) {
        for (uint8_t i = 0; i < n; i++) if (mode_level(i) == g_level) idx = (int8_t)i;
    }
    g_turbo = false;
    idx = (int8_t)((idx + 1) % n);
    g_level = mode_level((uint8_t)idx);
    battery::user_action();
}

bool blinky_enabled(uint8_t b) {
    switch (b) {
    case B_BATT: return true;
    case B_TEMP: return LX_HAS_TEMP != 0;
    case B_BEACON: return (p(P_BLINKY) & 1) != 0;
    case B_SOS: return (p(P_BLINKY) & 2) != 0;
    case B_STROBE: return (p(P_BLINKY) & 4) != 0;
    default: return false;
    }
}

void start_blinky(uint8_t b) {
    g_state = S_BLINKY;
    g_blinky = b;
    g_seq_t = 0;
    if (b == B_BATT) {
        uint16_t mv = battery::rest_cell_mv();
        g_seq_value = (uint8_t)min_of<uint16_t>((uint16_t)((mv + 50) / 100), 99);   // tenths of a volt
        aux::event(aux::PAT_BATTERY, battery::percent());
    } else if (b == B_TEMP) {
        int16_t t = thermal::temperature();
        g_seq_value = (uint8_t)clamp<int16_t>((int16_t)((t + 5) / 10), 0, 99);
    }
}

bool laser_allowed() {
#if LX_HAS_LASER
    if (!p(P_LASER_EN) || g_locked) return false;
    if (thermal::sensor_fault()) return false;
    if (LX_HAS_TEMP && thermal::temperature() > 10 * p(P_LASER_TMAX)) return false;
    if (battery::cell_mv() < (uint16_t)p(P_LASER_VMIN)) return false;
    return true;
#else
    return false;
#endif
}

// --- read-out sequences -----------------------------------------------------------------
// Two digits: each digit is shown as that many blinks (a zero as one very short blink).
bool readout_on(uint32_t t, uint8_t value) {
    const uint16_t LEAD = 600, ON = 200, ZERO_ON = 40, OFF = 300, GAP = 900, END = 2000;
    uint8_t d[2] = {(uint8_t)(value / 10), (uint8_t)(value % 10)};
    uint32_t total = LEAD + END;
    for (uint8_t k = 0; k < 2; k++) total += (uint32_t)(d[k] ? d[k] : 1) * (ON + OFF) + GAP;
    t %= total;
    if (t < LEAD) return false;
    t -= LEAD;
    for (uint8_t k = 0; k < 2; k++) {
        uint8_t n = d[k] ? d[k] : 1;
        uint16_t on = d[k] ? ON : ZERO_ON;
        for (uint8_t i = 0; i < n; i++) {
            if (t < on) return true;
            if (t < (uint32_t)ON + OFF) return false;
            t -= (uint32_t)ON + OFF;
        }
        if (t < GAP) return false;
        t -= GAP;
    }
    return false;
}

bool sos_on(uint32_t t) {
    // ... --- ...  in units of 200 ms: (on, off) pairs
    static const uint8_t k_sos[9][2] LX_FLASH = {{1, 1}, {1, 1}, {1, 3}, {3, 1}, {3, 1}, {3, 3}, {1, 1}, {1, 1}, {1, 7}};
    uint32_t u = t / 200u, total = 0;
    for (uint8_t i = 0; i < 9; i++) total += (uint32_t)lx_flash_u8(&k_sos[i][0]) + lx_flash_u8(&k_sos[i][1]);
    u %= total;
    for (uint8_t i = 0; i < 9; i++) {
        uint8_t on = lx_flash_u8(&k_sos[i][0]), off = lx_flash_u8(&k_sos[i][1]);
        if (u < on) return true;
        u -= on;
        if (u < off) return false;
        u -= off;
    }
    return false;
}

void run_action(uint8_t action, uint8_t arg, const Event& e) {
    switch (action) {
    case A_OFF:
        if (g_state == S_ON && !g_turbo) set_mem(g_level);
        go_off();
        break;
    case A_ON_MEM: {
        if (!switch_on_allowed()) break;
        uint8_t lvl = p(P_MEMORY) ? g_mem : (layout() == L_RAMP ? (uint8_t)p(P_MEM_LEVEL) : mode_level(0));
        go_on(lvl);
        break;
    }
    case A_ON_FLOOR_RAMP:
        if (!switch_on_allowed()) break;
        go_on(floor_lvl());
        g_ramping = true;
        g_ramp_dir = 1;
        g_ramp_acc = 0;
        g_ramp_flashed = false;
        break;
    case A_ON_FLOOR:
        if (!switch_on_allowed()) break;
        go_on(floor_lvl());
        set_mem(floor_lvl());
        break;
    case A_ON_LEVEL:
        if (!switch_on_allowed()) break;
        go_on(resolve(arg));
        break;
    case A_TURBO_FROM_OFF:
        if (!switch_on_allowed()) break;
        go_on(p(P_MEMORY) ? g_mem : (uint8_t)p(P_MEM_LEVEL));
        g_before_turbo = g_level;
        g_turbo = true;
        g_turbo_ms = 0;
        break;
    case A_TURBO_TOGGLE:
        if (g_turbo) {
            g_turbo = false;
            g_level = g_before_turbo;
        } else {
            g_before_turbo = g_level;
            g_turbo = true;
            g_turbo_ms = 0;
        }
        battery::user_action();
        break;
    case A_RAMP:
        if (g_turbo) {
            g_turbo = false;
            g_level = ceil_lvl();
            g_ramp_dir = -1;
        } else if (arg == 1 || g_level >= ceil_lvl()) {
            g_ramp_dir = -1;
        } else {
            g_ramp_dir = 1;
        }
        g_level = clamp(g_level, floor_lvl(), ceil_lvl());
        g_ramping = true;
        g_ramp_acc = 0;
        g_ramp_flashed = false;
        battery::user_action();
        break;
    case A_RAMP_TICK:
        if (!g_ramping) break;
        g_ramp_acc = (uint16_t)(g_ramp_acc + LX_TICK_MS);
        while (g_ramp_acc >= (uint16_t)p(P_RAMP_MS)) {
            g_ramp_acc = (uint16_t)(g_ramp_acc - p(P_RAMP_MS));
            uint8_t lo = floor_lvl(), hi = ceil_lvl();
            if (g_ramp_dir > 0 && g_level < hi) g_level++;
            else if (g_ramp_dir < 0 && g_level > lo) g_level--;
            else if (!g_ramp_flashed) {
                g_flash_ms = 40;             // the end of the ramp: one short dark flash
                g_ramp_flashed = true;
            }
        }
        break;
    case A_RAMP_END:
        if (!g_ramping) break;
        g_ramping = false;
        set_mem(g_level);
        break;
    case A_MODE_NEXT:
        step_mode();
        g_mode_holding = true;
        g_mode_acc = 0;
        break;
    case A_MODE_TICK:
        if (!g_mode_holding) break;
        g_mode_acc = (uint16_t)(g_mode_acc + LX_TICK_MS);
        if (g_mode_acc >= (uint16_t)p(P_MODE_MS)) {
            g_mode_acc = 0;
            step_mode();
        }
        break;
    case A_MODE_END:
        if (!g_mode_holding) break;
        g_mode_holding = false;
        set_mem(g_level);
        break;
    case A_BATTCHECK:
        if (g_state == S_ON && !g_turbo) set_mem(g_level);
        g_turbo = false;
        start_blinky(B_BATT);
        break;
    case A_BLINKY_NEXT: {
        uint8_t b = g_blinky;
        for (uint8_t i = 0; i < B_COUNT; i++) {
            b = (uint8_t)((b + 1) % B_COUNT);
            if (blinky_enabled(b)) break;
        }
        start_blinky(b);
        break;
    }
    case A_LOCK:
        go_off();
        g_state = S_LOCK;
        if (!g_locked) { g_locked = true; g_mem_dirty = true; }
        aux::event(aux::PAT_LOCK);
        feedback(3);
        break;
    case A_UNLOCK:
        go_off();
        if (g_locked) { g_locked = false; g_mem_dirty = true; }
        aux::event(aux::PAT_UNLOCK);
        feedback(2);
        break;
    case A_TICK_BLINK:
        aux::event(aux::PAT_TICK);
        break;
    case A_MOMENT:
        if (g_state == S_LOCK && !p(P_LOCK_MOON)) break;
        if (battery::empty() || thermal::shutdown()) break;
        g_prev_state = g_state;
        g_state = S_MOMENT;
        g_moment = true;
        g_moment_level = resolve(arg);
        break;
    case A_MOMENT_END:
        if (!g_moment) break;
        g_moment = false;
        g_state = g_prev_state;
        break;
    case A_LASER_OR_MOMENT:
        if (LX_HAS_LASER && p(P_LASER_EN)) {
            // Laser boards never fall back to momentary turbo: a refused laser stays dark.
            if (laser_allowed()) {
                g_state = S_LASER;
                g_laser_ms = 0;
                g_laser_cut = false;
            } else {
                aux::event(aux::PAT_REFUSE);
            }
        } else {
            if (battery::empty() || thermal::shutdown()) break;
            g_prev_state = g_state;
            g_state = S_MOMENT;
            g_moment = true;
            g_moment_level = layout() == L_SIMPLE ? resolve(LV_SIMPLE) : resolve(LV_TURBO);
        }
        break;
    case A_LASER_END:
        go_off();
        break;
    case A_FACTORY_RESET:
        params::reset_defaults(true);              // keeps BAT_CAL and THM_OFFSET
        storage::save_params();
        g_mem = (uint8_t)p(P_MEM_LEVEL);
        g_mem_dirty = true;
        aux::event(aux::PAT_RESET);
        feedback(5);
        break;
    default:
        break;
    }
    (void)e;
}

}  // namespace

// ---------------------------------------------------------------------------------------
void init(const Memory& m) {
    g_state = m.locked ? S_LOCK : S_OFF;
    g_locked = m.locked != 0;
    g_mem = (m.level >= 1 && m.level <= LEVEL_MAX) ? m.level : (uint8_t)p(P_MEM_LEVEL);
    g_level = 0;
    g_mem_dirty = false;
    go_off();
    if (g_locked) g_state = S_LOCK;
    g_fb_count = 0;
    g_flash_ms = 0;
}

uint8_t layout() {
    switch (p(P_UI_STYLE)) {
    case 1: return L_MODES;
    case 2: return L_SIMPLE;
    default: return L_RAMP;
    }
}

void handle(const Event& e) {
    if (e.type == EV_NONE) return;
    uint8_t ev_exact = EVB(e.type, e.count);
    uint8_t ev_any = EVB(e.type, 0);
    uint8_t lay = layout();
    for (uint8_t i = 0; i < LX_ARRAY_LEN(k_bindings); i++) {
        uint8_t layouts = lx_flash_u8(&k_bindings[i].layouts);
        uint8_t st = lx_flash_u8(&k_bindings[i].state);
        uint8_t ev = lx_flash_u8(&k_bindings[i].event);
        if (!(layouts & lay) || st != g_state) continue;
        if (ev != ev_exact && ev != ev_any) continue;
        run_action(lx_flash_u8(&k_bindings[i].action), lx_flash_u8(&k_bindings[i].arg), e);
        return;
    }
}

void tick(uint16_t dt) {
    if (g_flash_ms) g_flash_ms = g_flash_ms > dt ? (uint16_t)(g_flash_ms - dt) : 0;
    if (g_fb_count) g_fb_t = (uint16_t)(g_fb_t + dt);

    switch (g_state) {
    case S_ON:
        if (g_turbo) g_turbo_ms += dt;
        break;
    case S_BLINKY:
        g_seq_t += dt;
        break;
    case S_LASER:
        g_laser_ms += dt;
        if (!g_laser_cut) {
            if (g_laser_ms >= (uint32_t)p(P_LASER_S) * 1000u || !laser_allowed()) g_laser_cut = true;
        }
        break;
    default:
        break;
    }
}

void force_off() { go_off(); if (g_locked) g_state = S_LOCK; }

void lock_now() {
    if (g_state != S_OFF) return;
    g_state = S_LOCK;
    if (!g_locked) { g_locked = true; g_mem_dirty = true; }
}

bool remote_level(uint8_t lvl) {
    if (g_locked || lvl > LEVEL_MAX) return false;
    if (lvl == 0) { remote_off(); return true; }
    if (battery::empty() || thermal::shutdown()) return false;
    go_on(lvl);
    return true;
}

void remote_off() {
    if (g_state == S_ON || g_state == S_BLINKY) go_off();
}

State state() { return g_state; }
bool turbo_active() { return g_state == S_ON && g_turbo; }
bool momentary_from_lock() { return g_state == S_MOMENT && g_prev_state == S_LOCK; }

uint8_t level() {
    uint8_t lvl = 0;
    g_out_on = false;
    // Feedback blinks (no aux LED): 100 ms on, 150 ms off at the floor level.
    if (g_fb_count) {
        uint16_t per = 250;
        if (g_fb_t >= per * g_fb_count) {
            g_fb_count = 0;
        } else {
            g_out_on = true;
            return (g_fb_t % per) < 100 ? floor_lvl() : 0;
        }
    }
    switch (g_state) {
    case S_ON:
        lvl = g_level;
        if (g_turbo) {
            bool timed_out = p(P_TURBO_S) > 0 && g_turbo_ms >= (uint32_t)p(P_TURBO_S) * 1000u;
            lvl = timed_out ? (uint8_t)p(P_TURBO_DOWN) : (uint8_t)p(P_TURBO_LVL);
        }
        if (layout() == L_SIMPLE) lvl = min_of(lvl, (uint8_t)p(P_SIMPLE_MAX));
        if (g_flash_ms) { g_out_on = true; return 0; }
        return lvl;
    case S_MOMENT:
        return g_moment_level;
    case S_BLINKY: {
        g_out_on = true;
        bool on = false;
        uint8_t bright = (uint8_t)p(P_BLINK_LVL);
        switch (g_blinky) {
        case B_BATT:
        case B_TEMP: on = readout_on(g_seq_t, g_seq_value); break;
        case B_BEACON: on = (g_seq_t % 2000u) < 100u; bright = g_mem; break;
        case B_SOS: on = sos_on(g_seq_t); bright = g_mem; break;
        case B_STROBE: {
            uint32_t per = 1000u / (uint32_t)max_of<int16_t>(p(P_STROBE_HZ), 1);
            on = (g_seq_t % per) < per / 4u;
            bright = ceil_lvl();
            break;
        }
        default: break;
        }
        return on ? bright : 0;
    }
    default:
        return 0;
    }
}

bool instant() { return g_out_on; }

bool laser() { return LX_HAS_LASER && g_state == S_LASER && !g_laser_cut; }

bool busy() {
    return g_state == S_ON || g_state == S_BLINKY || g_state == S_LASER || g_state == S_MOMENT ||
           g_fb_count != 0 || g_flash_ms != 0;
}

Memory memory() {
    Memory m;
    m.level = g_mem;
    m.locked = g_locked ? 1 : 0;
    return m;
}
bool memory_dirty() { return g_mem_dirty; }
void memory_saved() { g_mem_dirty = false; }

const Binding* bindings(uint8_t* count) {
    *count = (uint8_t)LX_ARRAY_LEN(k_bindings);
    return k_bindings;
}

const char* state_name(uint8_t st) {
    switch (st) {
    case S_OFF: return "off";
    case S_ON: return "on";
    case S_LOCK: return "lockout";
    case S_BLINKY: return "blinky";
    case S_LASER: return "laser";
    case S_MOMENT: return "momentary";
    default: return "?";
    }
}

#if defined(LX_HOST)
const char* action_text(uint8_t action, uint8_t arg) {
    switch (action) {
    case A_OFF: return "switch off";
    case A_ON_MEM: return "on at the remembered level (MEMORY), otherwise MEM_LEVEL / mode 1";
    case A_ON_FLOOR_RAMP: return "on at the floor (moon), then brighter while held";
    case A_ON_FLOOR: return "on at the floor (moon); moon becomes the remembered level";
    case A_ON_LEVEL: return arg == LV_SIMPLE ? "on at SIMPLE_MAX" : "on at a fixed level";
    case A_TURBO_FROM_OFF: return "turbo (TURBO_LVL, steps down to TURBO_DOWN after TURBO_S)";
    case A_TURBO_TOGGLE: return "turbo on; again: back to the previous level";
    case A_RAMP: return arg ? "ramp down while held" : "ramp up while held (down if already at the ceiling)";
    case A_RAMP_TICK: return "(continues the ramp)";
    case A_RAMP_END: return "stop ramping, remember the level";
    case A_MODE_NEXT: return "next mode, repeating every MODE_MS while held (moon/turbo -> mode 1)";
    case A_MODE_TICK: return "(continues stepping)";
    case A_MODE_END: return "stop stepping, remember the mode";
    case A_BATTCHECK: return "battery check: volts per cell as blinks (3.8 V = 3 blinks, pause, 8 blinks), repeats";
    case A_BLINKY_NEXT: return "next blinky mode: temperature read-out, beacon, SOS, strobe (as enabled by BLINKY)";
    case A_LOCK: return "lockout on (3 blinks)";
    case A_UNLOCK: return "lockout off";
    case A_TICK_BLINK: return "short indicator flash, nothing else";
    case A_MOMENT: return arg == LV_FLOOR ? "moon while held (if LOCK_MOON = 1)" : "light while held";
    case A_MOMENT_END: return "(back to the previous state)";
    case A_LASER_OR_MOMENT: return "laser while held on laser boards (limits: LASER_S, LASER_TMAX, LASER_VMIN); otherwise turbo while held";
    case A_LASER_END: return "laser off";
    case A_FACTORY_RESET: return "factory reset: all parameters back to their defaults except the calibration (5 blinks)";
    default: return "";
    }
}
#else
const char* action_text(uint8_t, uint8_t) { return nullptr; }
#endif

}  // namespace ui
}  // namespace lx
