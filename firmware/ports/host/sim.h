// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - PC simulation of a flashlight (host port).
//
// The real firmware core runs unchanged against a simulated world:
//   * a Li-ion pack (open-circuit curve, internal resistance, capacity, optional USB charging)
//   * an LED + driver (current = power x full scale, forward-voltage model, efficiency)
//   * a two-node thermal model: head (LED, driver, sensor nearby) and body (what you touch),
//     natural convection + radiation to the ambient air, and a lagging temperature sensor
// Button presses are scheduled on a time line, then run_to() advances the simulation.
#pragma once

#include <stdint.h>
#include <string>
#include <vector>

namespace sim {

struct Config {
    // battery
    double capacity_mah = 800.0;
    double r_int_ohm = 0.12;
    double soc = 1.0;               // 0 ... 1
    int cells = 1;
    // LED and driver (full scale from the board header, overridable)
    double i_max_a = 2.2;
    double vf0 = 2.75;              // V
    double rs = 0.15;               // ohm (forward-voltage slope)
    double efficiency = 0.90;
    double lm_per_a = 400.0;        // at low current
    double droop_per_a = 0.05;      // relative loss of efficacy per ampere
    double light_fraction = 0.30;   // part of the LED power that leaves as light
    // thermal (defaults: ~30 g aluminium keychain light, 68 cm2 surface)
    double c_head = 8.0;            // J/K
    double c_body = 19.0;           // J/K
    double r_head_body = 2.0;       // K/W
    double r_body_amb = 13.0;       // K/W  (1 / (h * A), h ~ 11 W/m2K)
    double sensor_tau_s = 4.0;      // NTC lag
    double sensor_noise_c = 0.0;    // peak noise of each reading (triangular, repeatable)
    double sensor_step_c = 0.1;     // resolution of a reading (1.0 ~ ATtiny internal sensor)
    double ambient_c = 25.0;
    bool has_sensor = true;
    bool sensor_open = false;       // simulate a broken NTC
    // USB / charger
    double charge_a = 0.3;
    bool keep_storage = false;      // keep the emulated EEPROM from the previous run
};

// Presets for the documentation and tests.
Config keychain_preset();           // ~30 g aluminium, 2 small LiPo cells in parallel, 2.2 A LED
Config edc18650_preset();           // ~80 g aluminium 18650 light, 5 A LED

void reset(const Config& c);        // new world, firmware init (light::init)
void press_at(uint32_t t_ms, bool down);           // schedule a button level change
void usb_at(uint32_t t_ms, bool present);
void ambient_at(uint32_t t_ms, double ambient_c);

// Builders that append to the time line (cursor starts at the current time).
void click(int n);                  // n quick clicks (80 ms down, 120 ms up)
void hold(int clicks_before, uint32_t ms);   // clicks, then hold for ms
void wait(uint32_t ms);
uint32_t cursor();

void run_to(uint32_t t_ms);         // advance the simulation (firmware ticks every LX_TICK_MS)
void run_for(uint32_t ms);
void run_script(uint32_t extra_ms = 1500);   // run to the end of the time line + extra

// Observation
uint32_t now();
uint8_t level();                    // output level of the firmware
double led_a();
double lumens();
double t_head();
double t_body();
double t_sensor();
double v_pack();
double soc();
bool laser();
uint8_t aux_r();
uint8_t aux_g();
uint8_t aux_b();
bool sleeping();                    // the firmware is in hal::sleep()
uint32_t sleep_ms_total();          // simulated time spent in hal::sleep() since reset()

// Console
void console_in(const std::string& line);   // a full line, newline added
std::string console_take();                  // everything written since the last call

// Log of samples every 100 ms: t, level, I, lm, T_sensor, T_body, V, SoC
struct Sample {
    uint32_t t;
    uint8_t level;
    double led_a, lumens, t_sensor, t_body, v_pack, soc;
    bool laser;
};
const std::vector<Sample>& log();
void write_csv(const std::string& path);

}  // namespace sim
