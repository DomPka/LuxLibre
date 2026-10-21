// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - parameters (user settings), ArduPilot style.
#pragma once

#include "lx_common.h"
#include "lx_board.h"

namespace lx {

enum ParamId : uint8_t {
#define LX_PARAM(id, name, def, mn, mx, unit, desc) P_##id,
#include "lx_params_list.h"
#undef LX_PARAM
    P_COUNT
};

namespace params {

// All parameters to their defaults (RAM only). With keep_calibration the per-unit
// calibration values (BAT_CAL, THM_OFFSET) are kept: the factory reset uses this.
void reset_defaults(bool keep_calibration = false);
bool is_calibration(ParamId id);
int16_t get(ParamId id);
bool set(ParamId id, int16_t value);     // false (and no change) if out of range
int16_t default_of(ParamId id);
int16_t min_of(ParamId id);
int16_t max_of(ParamId id);
bool changed();                          // set() since the last clear_changed()
void clear_changed();

// Raw access for the storage module.
int16_t* raw();

// 16-bit hash of the parameter names and order (detects a changed list).
uint16_t layout_hash();

#if LX_HAS_CONSOLE || defined(LX_HOST)
// Name lookup (names live in flash).
bool name_of(ParamId id, char* buf, uint8_t buflen);
int find(const char* name);              // -1 if unknown
#endif

}  // namespace params

// Short form used everywhere in the core: lx::p(P_THM_LIMIT)
inline int16_t p(ParamId id) { return params::get(id); }

}  // namespace lx
