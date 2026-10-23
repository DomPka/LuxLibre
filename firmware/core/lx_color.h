// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - colour beam (boards with LX_HAS_COLOR): the list of colours and the
// currents of the red, green and blue LEDs.
//
// A colour is a mix of the three LEDs in per cent, the strongest at 100. The brightness of the
// colour beam uses the same levels as the white beam: the level that the button reaches at the
// top (RAMP_CEIL, or the highest mode) gives the colour LEDs their full current (LX_COLOR_MAX_MA)
// and every lower level the same fraction of it as on the white beam. So low, medium and high
// keep their meaning, and "high" is the brightest the colour LEDs can be.
#pragma once

#include "lx_common.h"

namespace lx {
namespace color {

enum Colour : uint8_t { C_RED, C_GREEN, C_BLUE, C_YELLOW, C_CYAN, C_MAGENTA, C_WHITE, C_CUSTOM, C_COUNT };

uint8_t valid(uint8_t idx);                  // idx if COLOR_SET contains it, else the next colour in the set
uint8_t next(uint8_t idx);                   // the colour after idx in COLOR_SET (wraps round)
void mix(uint8_t idx, uint8_t pct[3]);       // red, green, blue in %, the largest scaled to 100

// Currents in mA of the red, green and blue LEDs at an output level; top = the level that gives
// the full colour current (at least 1). A mix whose sum would pass LX_COLOR_SUM_MA is scaled down.
void currents_ma(uint8_t level, uint8_t top, uint8_t idx, uint16_t ma[3]);
// TURBO_ALL: white from the three colour LEDs on top of the white turbo, from nothing at the level `top` (the
// highest mode or RAMP_CEIL) up to the full colour current at level 150. Below `top` they stay off, so the
// thermal regulator's sustained level runs on the efficient white LED alone.
void turbo_currents_ma(uint8_t level, uint8_t top, uint16_t ma[3]);
void currents_of_fraction(uint32_t frac_q16, uint8_t idx, uint16_t ma[3]);
// The cell current those LED currents draw (straight from the cell, or through the rail converter).
uint16_t cell_ma(const uint16_t ma[3], uint16_t cell_mv);

const char* name(uint8_t idx);               // "red", "green", ..., "white" (from the colour LEDs), "custom"
int find(const char* name);                  // index of a name, -1 if unknown (lower case)

}  // namespace color
}  // namespace lx
