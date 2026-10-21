// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - host port: HAL implementation on top of a simulated flashlight.
#include "sim.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

#include "../../core/lx_board.h"
#include "../../core/lx_light.h"
#include "../../core/lx_thermal.h"
#include "../../hal/lx_hal.h"

namespace sim {

namespace {

enum EvKind { EV_BUTTON, EV_USB, EV_AMBIENT };
struct TimedEvent {
    uint32_t t;
    EvKind kind;
    double value;
    uint32_t seq;   // keeps insertion order for equal times
};

Config g_cfg;
uint32_t g_now = 0;
uint32_t g_target = 0;
uint32_t g_cursor = 0;
uint32_t g_seq = 0;
std::vector<TimedEvent> g_events;

// world state
bool g_button = false;
bool g_usb = false;
double g_soc = 1.0;
double g_th = 25.0, g_tb = 25.0, g_ts = 25.0;
double g_i_led = 0.0, g_i_bat = 0.0, g_v_pack = 4.2;
bool g_sleeping = false;
uint32_t g_sleep_total = 0;
uint32_t g_next_log = 0;
std::vector<Sample> g_log;

// outputs written by the firmware
uint16_t g_power = 0;
bool g_laser = false;
bool g_charge_en = false;
uint8_t g_r = 0, g_g = 0, g_b = 0;

uint32_t g_rng = 1;          // repeatable sensor noise

double rand01() {
    g_rng = g_rng * 1664525u + 1013904223u;
    return (g_rng >> 8) / 16777216.0;
}

uint8_t g_storage[LX_STORAGE_SIZE];
std::string g_con_in, g_con_out;

double ocv_cell(double soc) {
    // typical NMC cell; the last few percent fall off steeply
    static const double s[] = {0.0, 0.03, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00};
    static const double v[] = {2.70, 3.30, 3.45, 3.60, 3.70, 3.75, 3.79, 3.83, 3.88, 3.94, 4.00, 4.08, 4.20};
    soc = std::min(1.0, std::max(0.0, soc));
    for (int i = 1; i < 13; i++) {
        if (soc <= s[i]) return v[i - 1] + (v[i] - v[i - 1]) * (soc - s[i - 1]) / (s[i] - s[i - 1]);
    }
    return 4.20;
}

void apply_events() {
    while (!g_events.empty() && g_events.front().t <= g_now) {
        TimedEvent e = g_events.front();
        g_events.erase(g_events.begin());
        switch (e.kind) {
        case EV_BUTTON: g_button = e.value != 0.0; break;
        case EV_USB: g_usb = e.value != 0.0; break;
        case EV_AMBIENT: g_cfg.ambient_c = e.value; break;
        }
    }
}

void physics(double dt) {
    // LED and driver
    double frac = g_power / 65535.0;
    g_i_led = frac * g_cfg.i_max_a;
    double v_led = g_i_led > 0 ? g_cfg.vf0 + g_cfg.rs * g_i_led : 0.0;
    double p_led = v_led * g_i_led;
    double p_in = g_cfg.efficiency > 0 ? p_led / g_cfg.efficiency : 0.0;
    double p_laser = g_laser ? 0.25 : 0.0;   // small laser module incl. its driver
    // battery
    double ocv = ocv_cell(g_soc) * g_cfg.cells;
    double v = ocv;
    double i_bat = 0.0;
    for (int k = 0; k < 3; k++) {   // terminal voltage depends on the current
        i_bat = (p_in + p_laser) / std::max(v, 1.0) + 0.0003;
        v = ocv - i_bat * g_cfg.r_int_ohm;
    }
    double i_chg = 0.0;
    if (g_usb && g_charge_en && g_soc < 0.995) i_chg = g_cfg.charge_a * (g_soc > 0.9 ? (1.0 - g_soc) * 10.0 : 1.0);
    g_i_bat = i_bat - i_chg;
    g_v_pack = g_usb && i_chg > 0 ? ocv + i_chg * g_cfg.r_int_ohm : v;
    g_soc -= g_i_bat * dt / (g_cfg.capacity_mah * 3.6);
    g_soc = std::min(1.0, std::max(0.0, g_soc));
    // thermal: heat in the head, conduction to the body, body to the air
    double heat = p_in - g_cfg.light_fraction * p_led + p_laser * 0.8;
    double q_hb = (g_th - g_tb) / g_cfg.r_head_body;
    double q_ba = (g_tb - g_cfg.ambient_c) / g_cfg.r_body_amb;
    g_th += (heat - q_hb) * dt / g_cfg.c_head;
    g_tb += (q_hb - q_ba) * dt / g_cfg.c_body;
    g_ts += (g_th - g_ts) * dt / g_cfg.sensor_tau_s;
}

void sample_log() {
    if (g_now >= g_next_log) {
        g_next_log = g_now + 100;
        Sample s{g_now, lx::light::output_level(), g_i_led, lumens(), g_ts, g_tb, g_v_pack, g_soc, g_laser};
        g_log.push_back(s);
    }
}

void step_world() {
    g_now += LX_TICK_MS;
    apply_events();
    physics(LX_TICK_MS / 1000.0);
    sample_log();
}

void push(uint32_t t, EvKind k, double v) {
    TimedEvent e{t, k, v, g_seq++};
    g_events.push_back(e);
    std::stable_sort(g_events.begin(), g_events.end(), [](const TimedEvent& a, const TimedEvent& b) {
        return a.t < b.t || (a.t == b.t && a.seq < b.seq);
    });
}

}  // namespace

Config keychain_preset() {
    Config c;
#if LX_MAIN_MAX_MA > 0
    // The LED and driver model of the board being simulated (board.h); for the host-sim
    // board these are the defaults above.
    c.i_max_a = LX_MAIN_MAX_MA / 1000.0;
    c.vf0 = LX_LED_VF0_MV / 1000.0;
    c.rs = LX_LED_RS_MOHM / 1000.0;
    c.efficiency = LX_DRIVER_EFF_PCT / 100.0;
#endif
    c.cells = LX_BAT_CELLS;
    c.sensor_noise_c = 0.2;         // NTC on a 12-bit ADC: a few counts of noise
    return c;
}

Config edc18650_preset() {
    Config c;
    c.capacity_mah = 3000;
    c.r_int_ohm = 0.05;
    c.i_max_a = 5.0;
    c.vf0 = 2.8;
    c.rs = 0.10;
    c.lm_per_a = 380;
    c.droop_per_a = 0.03;
    c.c_head = 20;
    c.c_body = 52;
    c.r_head_body = 1.0;
    c.r_body_amb = 8.5;
    c.sensor_tau_s = 3.0;
    c.sensor_noise_c = 0.2;
    return c;
}

void reset(const Config& c) {
    g_cfg = c;
    g_now = 0;
    g_target = 0;
    g_cursor = 0;
    g_seq = 0;
    g_events.clear();
    g_button = false;
    g_usb = false;
    g_soc = c.soc;
    g_th = g_tb = g_ts = c.ambient_c;
    g_power = 0;
    g_laser = false;
    g_charge_en = false;
    g_r = g_g = g_b = 0;
    g_log.clear();
    g_next_log = 0;
    g_sleep_total = 0;
    g_rng = 12345;
    g_con_in.clear();
    g_con_out.clear();
    if (!c.keep_storage) memset(g_storage, 0xFF, sizeof(g_storage));
    physics(0.0);
    lx::light::init();
}

void press_at(uint32_t t, bool down) { push(t, EV_BUTTON, down ? 1.0 : 0.0); }
void usb_at(uint32_t t, bool present) { push(t, EV_USB, present ? 1.0 : 0.0); }
void ambient_at(uint32_t t, double a) { push(t, EV_AMBIENT, a); }

uint32_t cursor() { return std::max(g_cursor, g_now); }

void click(int n) {
    uint32_t t = cursor();
    for (int i = 0; i < n; i++) {
        press_at(t, true);
        press_at(t + 80, false);
        t += 200;
    }
    g_cursor = t;
}

void hold(int clicks_before, uint32_t ms) {
    click(clicks_before);
    uint32_t t = cursor();
    press_at(t, true);
    press_at(t + ms, false);
    g_cursor = t + ms + 100;
}

void wait(uint32_t ms) { g_cursor = cursor() + ms; }

void run_to(uint32_t t) {
    g_target = t;
    while (g_now < t) {
        step_world();
        lx::light::tick();
    }
}

void run_for(uint32_t ms) { run_to(g_now + ms); }

void run_script(uint32_t extra_ms) {
    uint32_t end = g_cursor;
    for (const TimedEvent& e : g_events) end = std::max(end, e.t);
    run_to(end + extra_ms);
}

uint32_t now() { return g_now; }
uint8_t level() { return lx::light::output_level(); }
double led_a() { return g_i_led; }
double lumens() {
    double i = g_i_led;
    double lm = i * g_cfg.lm_per_a * (1.0 - g_cfg.droop_per_a * i) * (1.0 - 0.003 * (g_th - 25.0));
    return lm > 0 ? lm : 0.0;
}
double t_head() { return g_th; }
double t_body() { return g_tb; }
double t_sensor() { return g_ts; }
double v_pack() { return g_v_pack; }
double soc() { return g_soc; }
bool laser() { return g_laser; }
uint8_t aux_r() { return g_r; }
uint8_t aux_g() { return g_g; }
uint8_t aux_b() { return g_b; }
bool sleeping() { return g_sleeping; }
uint32_t sleep_ms_total() { return g_sleep_total; }

void console_in(const std::string& line) { g_con_in += line + "\n"; }
std::string console_take() {
    std::string s = g_con_out;
    g_con_out.clear();
    return s;
}

const std::vector<Sample>& log() { return g_log; }

void write_csv(const std::string& path) {
    FILE* f = fopen(path.c_str(), "w");
    if (!f) return;
    fprintf(f, "t_s,level,led_A,lumens,T_sensor_C,T_body_C,V_pack,SoC_pct,laser\n");
    for (const Sample& s : g_log) {
        fprintf(f, "%.1f,%u,%.3f,%.0f,%.2f,%.2f,%.3f,%.1f,%d\n", s.t / 1000.0, s.level, s.led_a, s.lumens,
                s.t_sensor, s.t_body, s.v_pack, s.soc * 100.0, s.laser ? 1 : 0);
    }
    fclose(f);
}

}  // namespace sim

// ======================================================================================
// HAL implementation
namespace hal {

void init() {
    sim::g_power = 0;
    sim::g_laser = false;
    sim::g_r = sim::g_g = sim::g_b = 0;
}
void watchdog_kick() {}
void reboot() { lx::light::init(); }

uint32_t millis() { return sim::g_now; }
void wait_tick() {}   // the simulation drives the ticks

bool sleep(uint32_t max_ms, bool wake_on_button) {
    uint32_t t0 = sim::g_now;
    sim::g_sleeping = true;
    bool by_button = false;
    for (;;) {
        if (sim::g_now >= sim::g_target) break;
        sim::step_world();
        if (wake_on_button && sim::g_button) { by_button = true; break; }
        if (max_ms && sim::g_now - t0 >= max_ms) break;
    }
    sim::g_sleeping = false;
    sim::g_sleep_total += sim::g_now - t0;
    return by_button;
}

bool button_down() { return sim::g_button; }
uint16_t battery_mv() { return (uint16_t)std::lround(sim::g_v_pack * 1000.0); }
lx::temp_dc_t temperature() {
    if (!sim::g_cfg.has_sensor) return lx::thermal::NO_SENSOR;
    if (sim::g_cfg.sensor_open) return -500;
    double t = sim::g_ts;
    if (sim::g_cfg.sensor_noise_c > 0) t += sim::g_cfg.sensor_noise_c * (sim::rand01() + sim::rand01() - 1.0);
    double step = std::max(0.1, sim::g_cfg.sensor_step_c);
    t = std::round(t / step) * step;
    return (lx::temp_dc_t)std::lround(t * 10.0);
}
bool usb_present() { return sim::g_usb; }
uint8_t charger_status() {
    if (!sim::g_usb) return CHG_NONE;
    if (sim::g_soc >= 0.99) return CHG_DONE;
    return sim::g_charge_en ? CHG_CHARGING : CHG_NONE;
}

void set_main(lx::power_t power) { sim::g_power = power; }
void set_aux(uint8_t r, uint8_t g, uint8_t b) { sim::g_r = r; sim::g_g = g; sim::g_b = b; }
void set_laser(bool on) { sim::g_laser = on; }
void set_charge(bool enable, bool allowed) { (void)allowed; sim::g_charge_en = enable; }

void storage_read(uint16_t addr, void* dst, uint16_t len) {
    if ((uint32_t)addr + len > LX_STORAGE_SIZE) { memset(dst, 0xFF, len); return; }
    memcpy(dst, sim::g_storage + addr, len);
}
bool storage_write(uint16_t addr, const void* src, uint16_t len) {
    if ((uint32_t)addr + len > LX_STORAGE_SIZE) return false;
    memcpy(sim::g_storage + addr, src, len);
    return true;
}

int console_getc() {
    if (sim::g_con_in.empty()) return -1;
    int c = (unsigned char)sim::g_con_in[0];
    sim::g_con_in.erase(0, 1);
    return c;
}
void console_write(const char* s) { sim::g_con_out += s; }

}  // namespace hal
