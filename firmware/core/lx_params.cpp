// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_params.h"

namespace lx {
namespace params {

namespace {

const int16_t k_default[P_COUNT] LX_FLASH = {
#define LX_PARAM(id, name, def, mn, mx, unit, desc) (int16_t)(def),
#include "lx_params_list.h"
#undef LX_PARAM
};
const int16_t k_min[P_COUNT] LX_FLASH = {
#define LX_PARAM(id, name, def, mn, mx, unit, desc) (int16_t)(mn),
#include "lx_params_list.h"
#undef LX_PARAM
};
const int16_t k_max[P_COUNT] LX_FLASH = {
#define LX_PARAM(id, name, def, mn, mx, unit, desc) (int16_t)(mx),
#include "lx_params_list.h"
#undef LX_PARAM
};

// Names, one fixed-size record each (fast lookup, no pointer tables in flash).
constexpr uint8_t NAME_LEN = 11;  // 10 characters + terminating zero
const char k_names[P_COUNT][NAME_LEN] LX_FLASH = {
#define LX_PARAM(id, name, def, mn, mx, unit, desc) name,
#include "lx_params_list.h"
#undef LX_PARAM
};

// Compile-time checks of every line of the list.
#define LX_PARAM(id, name, def, mn, mx, unit, desc)                                   \
    static_assert(sizeof(name) <= NAME_LEN, "parameter name " name " is too long");  \
    static_assert((mn) <= (def) && (def) <= (mx), "default of " name " out of range");
#include "lx_params_list.h"
#undef LX_PARAM

int16_t g_value[P_COUNT];
bool g_changed;

}  // namespace

bool is_calibration(ParamId id) { return id == P_BAT_CAL || id == P_THM_OFFSET; }

void reset_defaults(bool keep_calibration) {
    for (uint8_t i = 0; i < P_COUNT; i++) {
        if (keep_calibration && is_calibration((ParamId)i)) continue;
        g_value[i] = lx_flash_i16(&k_default[i]);
    }
    g_changed = true;
}

int16_t get(ParamId id) { return id < P_COUNT ? g_value[id] : 0; }

int16_t default_of(ParamId id) { return lx_flash_i16(&k_default[id]); }
int16_t min_of(ParamId id) { return lx_flash_i16(&k_min[id]); }
int16_t max_of(ParamId id) { return lx_flash_i16(&k_max[id]); }

bool set(ParamId id, int16_t value) {
    if (id >= P_COUNT) return false;
    if (value < min_of(id) || value > max_of(id)) return false;
    if (g_value[id] != value) {
        g_value[id] = value;
        g_changed = true;
    }
    return true;
}

bool changed() { return g_changed; }
void clear_changed() { g_changed = false; }
int16_t* raw() { return g_value; }

uint16_t layout_hash() {
    // FNV-1a over all names (in order), folded to 16 bits.
    uint32_t h = 2166136261u;
    for (uint8_t i = 0; i < P_COUNT; i++) {
        for (uint8_t j = 0; j < NAME_LEN; j++) {
            char c = lx_flash_char(&k_names[i][j]);
            if (!c) break;
            h ^= (uint8_t)c;
            h *= 16777619u;
        }
        h ^= 0xFFu;
        h *= 16777619u;
    }
    return (uint16_t)(h ^ (h >> 16));
}

#if LX_HAS_CONSOLE || defined(LX_HOST)
bool name_of(ParamId id, char* buf, uint8_t buflen) {
    if (id >= P_COUNT || buflen == 0) return false;
    uint8_t j = 0;
    for (; j + 1 < buflen && j < NAME_LEN; j++) {
        char c = lx_flash_char(&k_names[id][j]);
        buf[j] = c;
        if (!c) return true;
    }
    buf[j] = 0;
    return true;
}

int find(const char* name) {
    for (uint8_t i = 0; i < P_COUNT; i++) {
        uint8_t j = 0;
        for (; j < NAME_LEN; j++) {
            char a = lx_flash_char(&k_names[i][j]);
            char b = name[j];
            if (b >= 'a' && b <= 'z') b = (char)(b - 'a' + 'A');  // case-insensitive
            if (a != b) break;
            if (!a) return i;
        }
    }
    return -1;
}
#endif

}  // namespace params
}  // namespace lx
