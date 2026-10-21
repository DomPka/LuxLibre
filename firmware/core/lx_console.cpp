// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_console.h"
#include "lx_board.h"

#if LX_HAS_CONSOLE || defined(LX_HOST)

#include "lx_battery.h"
#include "lx_light.h"
#include "lx_params.h"
#include "lx_ramp.h"
#include "lx_storage.h"
#include "lx_thermal.h"
#include "lx_ui.h"
#include "lx_version.h"
#include "../hal/lx_hal.h"

namespace lx {
namespace console {

namespace {

constexpr uint8_t LINE_MAX = 48;
char g_line[LINE_MAX];
uint8_t g_len = 0;
uint32_t g_last_ms = 0;
bool g_seen = false;

void out(const char* s) { hal::console_write(s); }

void out_int(int32_t v) {
    char buf[12];
    char* p = buf + sizeof(buf) - 1;
    *p = 0;
    bool neg = v < 0;
    uint32_t u = neg ? (uint32_t)(-v) : (uint32_t)v;
    do { *--p = (char)('0' + (u % 10)); u /= 10; } while (u);
    if (neg) *--p = '-';
    out(p);
}

void out_kv(const char* k, int32_t v) {
    out(k);
    out("=");
    out_int(v);
    out("\n");
}

bool parse_int(const char* s, int32_t& v) {
    bool neg = false;
    if (*s == '-') { neg = true; s++; }
    if (*s < '0' || *s > '9') return false;
    int32_t r = 0;
    while (*s >= '0' && *s <= '9') {
        r = r * 10 + (*s - '0');
        if (r > 100000) return false;
        s++;
    }
    if (*s) return false;
    v = neg ? -r : r;
    return true;
}

// Splits "cmd a b" in place; returns the number of words (max 3).
uint8_t split(char* s, char* w[3]) {
    uint8_t n = 0;
    while (*s && n < 3) {
        while (*s == ' ') s++;
        if (!*s) break;
        w[n++] = s;
        while (*s && *s != ' ') s++;
        if (*s) *s++ = 0;
    }
    return n;
}

bool eq(const char* a, const char* b) {
    while (*a && *b) {
        char x = *a >= 'A' && *a <= 'Z' ? (char)(*a - 'A' + 'a') : *a;
        if (x != *b) return false;
        a++; b++;
    }
    return *a == *b;
}

void print_param(uint8_t i) {
    char name[12];
    params::name_of((ParamId)i, name, sizeof(name));
    out_kv(name, params::get((ParamId)i));
}

}  // namespace

void execute(const char* line_in) {
    char line[LINE_MAX];
    uint8_t i = 0;
    for (; line_in[i] && i < LINE_MAX - 1; i++) line[i] = line_in[i];
    line[i] = 0;
    char* w[3] = {nullptr, nullptr, nullptr};
    uint8_t n = split(line, w);
    if (n == 0) return;

    if (eq(w[0], "help")) {
        out("help ver status list get set save defaults [all] level off reboot wdtest\nok\n");
    } else if (eq(w[0], "ver")) {
        out("LuxLibre " LX_FW_VERSION " / " LX_BOARD_NAME "\nok\n");
    } else if (eq(w[0], "status")) {
        out("state=");
        out(ui::state_name(ui::state()));
        out("\n");
        out_kv("level", light::output_level());
        out_kv("requested", light::requested_level());
        out_kv("cell_mA", light::cell_ma());
        out_kv("temp_dC", thermal::temperature());
        out_kv("cell_mV", battery::cell_mv());
        out_kv("battery_pct", battery::percent());
        out_kv("thermal_cap", thermal::cap());
        out_kv("lvp_cap", battery::cap());
        out("ok\n");
    } else if (eq(w[0], "list")) {
        for (uint8_t k = 0; k < P_COUNT; k++) print_param(k);
        out("ok\n");
    } else if (eq(w[0], "get") && n == 2) {
        int id = params::find(w[1]);
        if (id < 0) { out("err unknown parameter\n"); return; }
        print_param((uint8_t)id);
        out("ok\n");
    } else if (eq(w[0], "set") && n == 3) {
        int id = params::find(w[1]);
        int32_t v;
        if (id < 0) { out("err unknown parameter\n"); return; }
        if (!parse_int(w[2], v) || v < -32768 || v > 32767 || !params::set((ParamId)id, (int16_t)v)) {
            out("err range ");
            out_int(params::min_of((ParamId)id));
            out("..");
            out_int(params::max_of((ParamId)id));
            out("\n");
            return;
        }
        print_param((uint8_t)id);
        out("ok\n");
    } else if (eq(w[0], "save")) {
        out(storage::save_params() ? "ok\n" : "err storage\n");
    } else if (eq(w[0], "defaults")) {
        // "defaults" keeps the calibration of this unit, "defaults all" resets it too
        bool all = n == 2 && eq(w[1], "all");
        if (n == 2 && !all) { out("err usage: defaults [all]\n"); return; }
        params::reset_defaults(!all);
        out("ok (not saved yet)\n");
    } else if (eq(w[0], "level") && n == 2) {
        int32_t v;
        if (!parse_int(w[1], v) || v < 0 || v > LEVEL_MAX || !ui::remote_level((uint8_t)v)) {
            out("err not allowed\n");
            return;
        }
        out("ok\n");
    } else if (eq(w[0], "off")) {
        ui::remote_off();
        out("ok\n");
    } else if (eq(w[0], "reboot")) {
        out("ok\n");
        hal::reboot();
    } else if (eq(w[0], "wdtest")) {
        // Watchdog test (design rule DRV-8): the light goes to moon and the firmware stops
        // feeding the watchdog. Pass = the MCU restarts within the watchdog time and the
        // light comes back dark. Not available in the simulator (it would hang the PC).
#if defined(LX_HOST)
        out("err not in the simulator\n");
#else
        out("watchdog test: firmware stops now\n");
        hal::set_laser(false);
        hal::set_main(ramp::power_of_level(1));
        for (;;) {}
#endif
    } else {
        out("err unknown command\n");
    }
}

void reset() {
    g_len = 0;
    g_seen = false;
    g_last_ms = 0;
}

void poll() {
    int c;
    while ((c = hal::console_getc()) >= 0) {
        g_last_ms = hal::millis();
        g_seen = true;
        if (c == '\r' || c == '\n') {
            if (g_len) {
                g_line[g_len] = 0;
                execute(g_line);
                g_len = 0;
            }
        } else if (g_len < LINE_MAX - 1) {
            g_line[g_len++] = (char)c;
        }
    }
}

bool active() { return g_seen && (uint32_t)(hal::millis() - g_last_ms) < 30000u; }

}  // namespace console
}  // namespace lx

#else

namespace lx {
namespace console {
void reset() {}
void poll() {}
bool active() { return false; }
void execute(const char*) {}
}  // namespace console
}  // namespace lx

#endif
