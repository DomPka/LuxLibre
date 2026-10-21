// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - common types, helpers and flash-table access.
//
// The core is written in a small, portable subset of C++17: no heap, no exceptions,
// no RTTI, no virtual functions (AVR keeps vtables in RAM) and no global objects with
// constructors. Modules are namespaces with file-scope state, so the code reads like C.
#pragma once

#include <stdint.h>
#include <stddef.h>

// ---------------------------------------------------------------------------
// Tables in flash. On AVR (Harvard architecture) constant tables must be placed in
// program memory explicitly and read with LPM; everywhere else they are plain consts.
#if defined(__AVR__)
#include <avr/pgmspace.h>
#define LX_FLASH PROGMEM
static inline uint8_t lx_flash_u8(const uint8_t* p) { return pgm_read_byte(p); }
static inline uint16_t lx_flash_u16(const uint16_t* p) { return pgm_read_word(p); }
static inline int16_t lx_flash_i16(const int16_t* p) { return (int16_t)pgm_read_word(p); }
static inline char lx_flash_char(const char* p) { return (char)pgm_read_byte(p); }
#else
#define LX_FLASH
static inline uint8_t lx_flash_u8(const uint8_t* p) { return *p; }
static inline uint16_t lx_flash_u16(const uint16_t* p) { return *p; }
static inline int16_t lx_flash_i16(const int16_t* p) { return *p; }
static inline char lx_flash_char(const char* p) { return *p; }
#endif

#define LX_ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))

namespace lx {

template <typename T>
constexpr T min_of(T a, T b) { return a < b ? a : b; }
template <typename T>
constexpr T max_of(T a, T b) { return a > b ? a : b; }
template <typename T>
constexpr T clamp(T v, T lo, T hi) { return v < lo ? lo : (v > hi ? hi : v); }

// Brightness is handled as "levels": 0 = off, 1 = the lowest output the hardware can
// make (moon), LEVEL_MAX = 100 % of the main channel. Levels are spaced geometrically
// (each step is the same ratio), which looks even to the eye over the whole range.
constexpr uint8_t LEVEL_MAX = 150;

// Main-channel output as a fraction of full scale, 0 ... 65535 (Q16).
typedef uint16_t power_t;

// Temperatures are in tenths of a degree Celsius (deci-°C).
typedef int16_t temp_dc_t;

}  // namespace lx
