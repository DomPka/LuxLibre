// SPDX-License-Identifier: GPL-3.0-or-later
// luxsim - run the LuxLibre firmware against a simulated flashlight on the PC.
//
//   luxsim [options] "<script>"
//
// Script tokens (separated by spaces):
//   2C        two clicks            H1500   hold 1.5 s           CH3000  click, then hold 3 s
//   W60000    wait 60 s             USB1 / USB0   plug / unplug USB     AMB40  ambient 40 degC
// Options (any order):
//   --preset keychain|18650   body and cell model (default keychain: ~30 g, 800 mAh)
//   --ambient C  --soc 0..1  --capacity mAh
//   --imax A                  LED current at level 150
//   --noise C  --step C       sensor noise (peak) and resolution, e.g. --step 1 for a coarse sensor
//   --set NAME=VALUE          firmware parameter (repeatable)
//   --csv FILE                write the 100 ms log
//   --extra MS                keep running after the script (default 2000)
//
// Example (turbo for 10 minutes, how hot does it get?):
//   build/luxsim --csv turbo.csv "2C W600000"
//
// Built with a real board header (make sim BOARD=<board>), the LED and driver model of that
// board (LX_MAIN_MAX_MA, LX_LED_VF0_MV, LX_LED_RS_MOHM, LX_DRIVER_EFF_PCT) replaces the one of
// the preset, so "--preset 18650" means "my board in an 18650-size body".
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "../core/lx_board.h"
#include "../core/lx_params.h"
#include "../ports/host/sim.h"

// Strict number parsing: the whole text must be a number (no silent 0 or wrap-around).
static bool parse_num(const std::string& s, double& out) {
    char* end = nullptr;
    out = std::strtod(s.c_str(), &end);
    return !s.empty() && end && *end == 0 && std::isfinite(out);
}

static double num_arg(const std::string& name, const std::string& s) {
    double v;
    if (!parse_num(s, v)) {
        std::fprintf(stderr, "%s: not a number: %s\n", name.c_str(), s.c_str());
        std::exit(2);
    }
    return v;
}

static void usage() {
    std::printf("usage: luxsim [--preset keychain|18650] [--ambient C] [--soc 0..1] [--capacity mAh]\n"
                "              [--imax A] [--noise C] [--step C]\n"
                "              [--set NAME=VALUE]... [--csv FILE] [--extra MS] \"SCRIPT\"\n"
                "script: 2C  H1500  CH3000  W60000  USB1  USB0  AMB40\n");
}

int main(int argc, char** argv) {
    std::string preset = "keychain";
    double ambient = NAN, soc = NAN, capacity = NAN, imax = NAN, noise = NAN, step = NAN;
    std::vector<std::pair<std::string, int>> sets;
    std::string csv, script;
    uint32_t extra = 2000;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) { usage(); std::exit(2); }
            return argv[++i];
        };
        if (a == "--preset") {
            preset = next();
            if (preset != "18650" && preset != "keychain") { usage(); return 2; }
        } else if (a == "--ambient") ambient = num_arg(a, next());
        else if (a == "--soc") soc = num_arg(a, next());
        else if (a == "--capacity") capacity = num_arg(a, next());
        else if (a == "--imax") imax = num_arg(a, next());
        else if (a == "--noise") noise = num_arg(a, next());
        else if (a == "--step") step = num_arg(a, next());
        else if (a == "--csv") csv = next();
        else if (a == "--extra") {
            double v = num_arg(a, next());
            if (v < 0 || v > 4.0e9) { std::fprintf(stderr, "--extra: 0 ... 4e9 ms\n"); return 2; }
            extra = (uint32_t)v;
        }
        else if (a == "--set") {
            std::string kv = next();
            size_t eq = kv.find('=');
            double v;
            if (eq == std::string::npos || !parse_num(kv.substr(eq + 1), v) || v != std::floor(v) ||
                v < -32768 || v > 32767) {
                std::fprintf(stderr, "bad --set %s (NAME=integer)\n", kv.c_str());
                return 2;
            }
            sets.push_back({kv.substr(0, eq), (int)v});
        } else if (a == "-h" || a == "--help") { usage(); return 0; }
        else script = a;
    }

    sim::Config cfg = preset == "18650" ? sim::edc18650_preset() : sim::keychain_preset();
#if !defined(LX_HOST_SIM_BOARD) && LX_MAIN_MAX_MA > 0
    cfg.i_max_a = LX_MAIN_MAX_MA / 1000.0;          // the LED model of the board header
    cfg.vf0 = LX_LED_VF0_MV / 1000.0;
    cfg.rs = LX_LED_RS_MOHM / 1000.0;
    cfg.efficiency = LX_DRIVER_EFF_PCT / 100.0;
#endif
    if (!std::isnan(ambient)) cfg.ambient_c = ambient;
    if (!std::isnan(soc)) cfg.soc = soc;
    if (!std::isnan(capacity)) cfg.capacity_mah = capacity;
    if (!std::isnan(imax)) cfg.i_max_a = imax;
    if (!std::isnan(noise)) cfg.sensor_noise_c = noise;
    if (!std::isnan(step)) cfg.sensor_step_c = step;

    sim::reset(cfg);
    for (auto& kv : sets) {
        int id = lx::params::find(kv.first.c_str());
        if (id < 0 || !lx::params::set((lx::ParamId)id, (int16_t)kv.second)) {
            std::fprintf(stderr, "bad parameter %s=%d\n", kv.first.c_str(), kv.second);
            return 2;
        }
    }
    sim::run_for(300);

    // parse the script into the time line
    char* buf = strdup(script.c_str());
    for (char* tok = std::strtok(buf, " "); tok; tok = std::strtok(nullptr, " ")) {
        std::string t = tok;
        if (t.size() >= 2 && t.back() == 'C' && std::isdigit((unsigned char)t[0])) sim::click(std::atoi(t.c_str()));
        else if (t.rfind("CH", 0) == 0) sim::hold(1, (uint32_t)std::atol(t.c_str() + 2));
        else if (t[0] == 'H') sim::hold(0, (uint32_t)std::atol(t.c_str() + 1));
        else if (t[0] == 'W') sim::wait((uint32_t)std::atol(t.c_str() + 1));
        else if (t == "USB1") sim::usb_at(sim::cursor(), true);
        else if (t == "USB0") sim::usb_at(sim::cursor(), false);
        else if (t.rfind("AMB", 0) == 0) sim::ambient_at(sim::cursor(), std::atof(t.c_str() + 3));
        else { std::fprintf(stderr, "unknown token %s\n", tok); free(buf); return 2; }
    }
    free(buf);
    sim::run_script(extra);

    // summary
    double peak_t = -100, peak_lm = 0;
    uint32_t first_on = 0;
    for (const sim::Sample& s : sim::log()) {
        if (s.t_sensor > peak_t) peak_t = s.t_sensor;
        if (s.lumens > peak_lm) peak_lm = s.lumens;
        if (!first_on && s.level) first_on = s.t;
    }
    auto lumens_at = [&](uint32_t t) {
        for (const sim::Sample& s : sim::log()) if (s.t >= t) return s.lumens;
        return 0.0;
    };
    std::printf("simulated %.1f s\n", sim::now() / 1000.0);
    std::printf("peak output     %6.0f lm\n", peak_lm);
    if (first_on) {
        std::printf("output at 30 s  %6.0f lm   (ANSI FL 1 measures from 30 s)\n", lumens_at(first_on + 30000));
        std::printf("output at 120 s %6.0f lm\n", lumens_at(first_on + 120000));
    }
    std::printf("peak sensor     %6.1f degC\n", peak_t);
    std::printf("final           level %u, %.0f lm, %.1f degC, %.2f V, %.0f %%\n", sim::level(), sim::lumens(),
                sim::t_sensor(), sim::v_pack(), sim::soc() * 100.0);
    if (!csv.empty()) {
        sim::write_csv(csv);
        std::printf("log written to %s\n", csv.c_str());
    }
    return 0;
}
