// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - hardware abstraction layer (HAL).
//
// Every port (ports/<mcu>/) implements these functions for one microcontroller family.
// The core never touches a register; it only calls the functions below. A board header
// (boards/<board>/board.h) tells the port which pins and peripherals to use.
//
// Rules for every port:
//  * hal::init() must drive every output that can make light or heat (LED driver enable,
//    PWM, laser, side lights, colour LEDs) to its safe "off" level before anything else.
//  * Functions are called from the main loop only (no re-entrancy needed).
//  * Units: millivolts, deci-degrees Celsius, milliseconds, Q16 power (0 ... 65535).
#pragma once

#include "lx_common.h"

namespace hal {

// --- life cycle -------------------------------------------------------------
void init();                 // clocks, safe outputs, timers, ADC, storage
void watchdog_kick();        // reset the watchdog (called every tick)
void reboot();               // software reset

// --- time -------------------------------------------------------------------
uint32_t millis();           // monotonic milliseconds since boot (wraps after 49 days)
void wait_tick();            // block (low-power idle) until the next LX_TICK_MS tick

// Deep sleep while the light is off. Returns when the button is pressed (if
// wake_on_button) or after max_ms (0 = no timer wake). millis() must be advanced by the
// time spent asleep (ports without a running clock may add max_ms or an estimate).
// Returns true if the wake-up was caused by the button.
bool sleep(uint32_t max_ms, bool wake_on_button);

// --- inputs -----------------------------------------------------------------
bool button_down();          // raw switch state, true = pressed (debouncing is done by the core)
uint16_t battery_mv();       // battery (pack) voltage in mV, averaged by the port if useful
lx::temp_dc_t temperature(); // driver/body temperature in deci-°C; -32768 if no sensor
bool usb_present();          // USB / charger input voltage present (false if not supported)
uint8_t charger_status();    // see ChargerStatus below (CHG_NONE if not supported)

enum ChargerStatus : uint8_t { CHG_NONE = 0, CHG_CHARGING = 1, CHG_DONE = 2, CHG_FAULT = 3 };

// --- outputs ----------------------------------------------------------------
// Main LED channel: 0 = off (driver disabled), 1 ... 65535 = fraction of the board's
// full-scale output. The port maps it to PWM duty, a current set-point, or a mix
// (e.g. linear regulator for low levels + FET for high levels).
void set_main(lx::power_t power);

void set_aux(uint8_t r, uint8_t g, uint8_t b);   // indicator LED (0-255 each); no-op if absent
void set_laser(bool on);                         // laser module; no-op if absent
void set_side(uint8_t red, uint8_t uv);          // side lights (0-255 each, at most one on); no-op if absent
// Colour beam (LX_HAS_COLOR): current of the red, green and blue LEDs in mA (each at most
// LX_COLOR_MAX_MA; 0 = off). The port scales it to its set point (LX_COLOR_FULL_MA = full
// scale); no-op if absent.
void set_color(uint16_t red_ma, uint16_t green_ma, uint16_t blue_ma);
// Charger control, called every 100 ms (no-op if not controllable). enable = charge now.
// allowed = the cell temperature is inside the charge window: when false, the port must not
// let any current into the cell, not even to detect USB power (design rule CHG-3).
void set_charge(bool enable, bool allowed);

// --- persistent storage (EEPROM or emulated in flash) ------------------------
// LX_STORAGE_SIZE bytes, byte-addressable. Writes may be slow; the core writes rarely.
void storage_read(uint16_t addr, void* dst, uint16_t len);
bool storage_write(uint16_t addr, const void* src, uint16_t len);

// --- text console (optional; LX_HAS_CONSOLE) ---------------------------------
int console_getc();                // next received character or -1
void console_write(const char* s); // send a string (may drop data if no host is connected)

}  // namespace hal
