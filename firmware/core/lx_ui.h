// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - user interface: states, button bindings and actions.
//
// What every button gesture does is written down in one table (k_bindings in lx_ui.cpp):
//   layout(s) | state | event | action | argument
// so the user manual (docs/firmware/user-interface.md) is generated from the same table
// the firmware runs. Three layouts share the table, selected by the UI_STYLE parameter.
#pragma once

#include "lx_common.h"
#include "lx_input.h"

namespace lx {
namespace ui {

// S_COLOR is not a state of its own: its lines in the binding table apply while the light is on
// with the colour beam (boards with LX_HAS_COLOR), before the S_ON lines; anything they do not
// cover falls through to S_ON (hold = brightness, 3 clicks = battery check, ...).
enum State : uint8_t { S_OFF, S_ON, S_LOCK, S_BLINKY, S_LASER, S_MOMENT, S_SIDE, S_COLOR, S_COUNT };
enum Blinky : uint8_t { B_BATT, B_TEMP, B_BEACON, B_SOS, B_STROBE, B_COUNT };

// Layout masks used in the binding table.
constexpr uint8_t L_RAMP = 1, L_MODES = 2, L_SIMPLE = 4, L_ALL = 7;

// Level codes for action arguments (resolved through parameters at run time).
constexpr uint8_t LV_FLOOR = 251, LV_CEIL = 252, LV_TURBO = 253, LV_SIMPLE = 254;

enum Action : uint8_t {
    A_NONE,
    A_OFF,             // switch off
    A_ON_MEM,          // on at the memorised level (or MEM_LEVEL / mode 1)
    A_ON_FLOOR_RAMP,   // on at the floor and ramp up while the button stays down
    A_ON_FLOOR,        // on at the floor (moon) and stay there
    A_ON_LEVEL,        // on at the level given by the argument
    A_TURBO_FROM_OFF,  // straight to turbo
    A_TURBO_TOGGLE,    // turbo on / back to the previous level
    A_RAMP,            // start ramping (argument 0 = up, or down at the ceiling; 1 = down)
    A_RAMP_TICK,       // continue ramping while held
    A_RAMP_END,        // stop ramping, remember the level
    A_MODE_NEXT,       // next fixed mode (repeats while held)
    A_MODE_TICK,
    A_MODE_END,
    A_BATTCHECK,       // battery voltage read-out (blinks), entry to the blinky group
    A_BLINKY_NEXT,     // next blinky mode: temperature, beacon, SOS, strobe
    A_LOCK,            // lockout on
    A_UNLOCK,          // lockout off
    A_TICK_BLINK,      // short indicator flash (click while locked)
    A_MOMENT,          // light at the argument level while the button stays down
    A_MOMENT_END,
    A_LASER_OR_MOMENT, // laser while held (boards with a laser), otherwise momentary turbo
    A_LASER_END,
    A_FACTORY_RESET,   // all parameters back to their defaults (9 clicks from off)
    A_SIDE_ON,         // side light on (boards with side LEDs), in the colour used last
    A_SIDE_NEXT,       // side light: red <-> UV
    A_COLOR_ON,        // colour beam on (boards with LX_HAS_COLOR), in the colour and level used last
    A_COLOR_NEXT,      // colour beam: next colour of COLOR_SET
    A_CHANNEL,         // light on: white beam <-> colour beam, same level
    A_COUNT
};

struct Binding {
    uint8_t layouts;   // L_ mask
    uint8_t state;     // State
    uint8_t event;     // (EventType << 4) | count, count 0 = any
    uint8_t action;    // Action
    uint8_t arg;
};

// Persistent part of the UI.
struct Memory {
    uint8_t level;
    uint8_t locked;
    uint8_t color;     // colour beam: the colour used last (lx_color.h)
};

void init(const Memory& m);
void handle(const input::Event& e);       // dispatch one button event
void tick(uint16_t dt_ms);                // timers: blinky sequences, turbo, laser limits, feedback
void force_off();                         // protection switched the light off
void lock_now();                          // automatic lockout (AUTOLOCK), silent
bool remote_level(uint8_t level);         // console: set a level (false if not allowed)
bool remote_color(uint8_t level, int colour = -1);   // console: colour beam at a level, optionally in a given colour
                                          // (any colour, also one outside COLOR_SET); false if not allowed
void remote_off();

State state();
uint8_t layout();                         // current L_ mask (from UI_STYLE)
uint8_t level();                          // requested main level before protection caps (0 = off)
bool instant();                           // true while a blink pattern runs (no smoothing)
bool laser();                             // laser requested now
uint8_t side_red();                       // red side light requested now (0-255)
uint8_t side_uv();                        // UV side light requested now (0-255)
bool color_active();                      // the colour beam is on (the main level drives the colour LEDs)
uint8_t color_index();                    // colour of the colour beam (used last if it is off)
void color_ma(uint8_t level, uint16_t ma[3]);   // colour LED currents for an output level
bool turbo_all();                         // white turbo with the colour LEDs on as well (TURBO_ALL)
void turbo_all_ma(uint8_t level, uint16_t ma[3]);   // their currents: white from the three colours, above the top mode
bool action_available(uint8_t action);    // this board has the hardware for the action
bool busy();                              // something time-based runs: do not sleep
bool turbo_active();
bool momentary_from_lock();               // momentary moon started from lockout

Memory memory();
bool memory_dirty();
void memory_saved();

// For the documentation generator and the tests.
const Binding* bindings(uint8_t* count);
const char* action_text(uint8_t action, uint8_t arg);   // host builds only (nullptr on MCUs)
const char* state_name(uint8_t state);

}  // namespace ui
}  // namespace lx
