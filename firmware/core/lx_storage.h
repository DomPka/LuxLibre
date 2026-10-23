// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - persistent settings.
//
// Layout of the storage area (EEPROM or emulated EEPROM, LX_STORAGE_SIZE bytes):
//   0 ...            parameter block: "LX", layout hash, count, values, CRC-16
//   SIZE-96 ...      calibration block: "CA", BAT_CAL, THM_OFFSET, CRC-16 (8 bytes)
//   SIZE-32 ... SIZE state ring: 8 slots of 4 bytes (sequence, lockout + mode, level, CRC-8)
// The small state record (memory level, lockout) changes often, so it rotates over
// 8 slots to spread the wear; the parameter block is written only when settings change.
// The calibration of the unit has its own block, so it survives a firmware update that
// changes the parameter list (which resets the parameter block to defaults).
#pragma once

#include "lx_common.h"

namespace lx {
namespace storage {

struct State {
    uint8_t locked;     // 0/1
    uint8_t mem_level;  // ramp memory, 1 ... 150
    uint8_t color;      // colour beam: the colour used last, 0 ... 7 (lx_color.h)
};

// Load parameters; returns false (and uses defaults) if the block is missing, corrupt or
// was written by a firmware with a different parameter list.
bool load_params();
bool save_params();

bool load_state(State& s);     // false if no valid slot (s is left unchanged)
bool save_state(const State& s);

}  // namespace storage
}  // namespace lx
