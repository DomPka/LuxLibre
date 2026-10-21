// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - the main loop that ties the modules together.
//
//   hal (button) -> input (gestures) -> ui (what the user asked for)
//   hal (sensors) -> thermal / battery (how much the light may do)
//   ui level -> min(thermal cap, LVP cap, USB cap, cell current cap) -> smoothing -> hal output
//
// A port's main() is just:   lx::light::init(); for (;;) { hal::wait_tick(); lx::light::tick(); }
#pragma once

#include "lx_common.h"

namespace lx {
namespace light {

void init();
void tick();                  // call once every LX_TICK_MS

uint8_t output_level();       // level sent to the LED (after caps and smoothing)
uint8_t requested_level();    // level the user interface asked for
uint16_t cell_ma();           // estimated cell current (0 if the board has no current model)

}  // namespace light
}  // namespace lx
