// SPDX-License-Identifier: GPL-3.0-or-later
#include "lx_storage.h"
#include "lx_params.h"
#include "../hal/lx_hal.h"

namespace lx {
namespace storage {

namespace {

constexpr uint16_t PARAM_ADDR = 0;
constexpr uint16_t HEADER_LEN = 6;
constexpr uint16_t PARAM_LEN = HEADER_LEN + 2u * P_COUNT + 2u;   // + CRC-16
constexpr uint8_t SLOTS = 8;
constexpr uint8_t SLOT_LEN = 4;
constexpr uint16_t RING_ADDR = LX_STORAGE_SIZE - SLOTS * SLOT_LEN;
constexpr uint16_t CAL_LEN = 8;
// 64 bytes below the ring: on ports that emulate the storage in 64-byte flash pages the
// calibration then never shares a page with the often-written state ring.
constexpr uint16_t CAL_ADDR = RING_ADDR - 64;

static_assert(PARAM_LEN <= CAL_ADDR, "parameter block does not fit: raise LX_STORAGE_SIZE");

uint8_t g_seq = 0;      // sequence number of the newest slot
uint8_t g_slot = 0;     // index of the newest slot

uint16_t crc16_update(uint16_t crc, uint8_t b) {   // CRC-16/CCITT-FALSE
    crc ^= (uint16_t)b << 8;
    for (uint8_t i = 0; i < 8; i++) crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
    return crc;
}

uint8_t crc8(const uint8_t* d, uint8_t n) {        // CRC-8 (poly 0x07), init 0x5A
    uint8_t c = 0x5A;
    for (uint8_t i = 0; i < n; i++) {
        c ^= d[i];
        for (uint8_t k = 0; k < 8; k++) c = (c & 0x80u) ? (uint8_t)((c << 1) ^ 0x07u) : (uint8_t)(c << 1);
    }
    return c;
}

void cal_bytes(uint8_t* d) {
    int16_t bc = params::get(P_BAT_CAL), to = params::get(P_THM_OFFSET);
    d[0] = 'C';
    d[1] = 'A';
    d[2] = (uint8_t)(uint16_t)bc;
    d[3] = (uint8_t)((uint16_t)bc >> 8);
    d[4] = (uint8_t)(uint16_t)to;
    d[5] = (uint8_t)((uint16_t)to >> 8);
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < 6; i++) crc = crc16_update(crc, d[i]);
    d[6] = (uint8_t)crc;
    d[7] = (uint8_t)(crc >> 8);
}

// The calibration block wins over the parameter block (it is written with every save).
void load_calibration() {
    uint8_t d[CAL_LEN];
    hal::storage_read(CAL_ADDR, d, CAL_LEN);
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < 6; i++) crc = crc16_update(crc, d[i]);
    if (d[0] != 'C' || d[1] != 'A' || d[6] != (uint8_t)crc || d[7] != (uint8_t)(crc >> 8)) return;
    params::set(P_BAT_CAL, (int16_t)((uint16_t)d[2] | ((uint16_t)d[3] << 8)));      // range-checked
    params::set(P_THM_OFFSET, (int16_t)((uint16_t)d[4] | ((uint16_t)d[5] << 8)));
}

}  // namespace

bool load_params() {
    uint8_t h[HEADER_LEN];
    hal::storage_read(PARAM_ADDR, h, HEADER_LEN);
    uint16_t hash = params::layout_hash();
    bool ok = h[0] == 'L' && h[1] == 'X' && h[2] == (uint8_t)hash && h[3] == (uint8_t)(hash >> 8) &&
              h[4] == P_COUNT;
    if (ok) {
        uint16_t crc = 0xFFFF;
        for (uint8_t i = 0; i < HEADER_LEN; i++) crc = crc16_update(crc, h[i]);
        int16_t* v = params::raw();
        for (uint8_t i = 0; i < P_COUNT; i++) {
            uint8_t b[2];
            hal::storage_read((uint16_t)(PARAM_ADDR + HEADER_LEN + 2u * i), b, 2);
            crc = crc16_update(crc, b[0]);
            crc = crc16_update(crc, b[1]);
            v[i] = (int16_t)((uint16_t)b[0] | ((uint16_t)b[1] << 8));
        }
        uint8_t c[2];
        hal::storage_read((uint16_t)(PARAM_ADDR + HEADER_LEN + 2u * P_COUNT), c, 2);
        ok = c[0] == (uint8_t)crc && c[1] == (uint8_t)(crc >> 8);
        // A value outside its range (a newer firmware may have narrowed a range) is clamped to
        // it; the other settings are kept. Torn writes are caught by the CRC above.
        for (uint8_t i = 0; ok && i < P_COUNT; i++) {
            ParamId id = (ParamId)i;
            v[i] = clamp<int16_t>(v[i], params::min_of(id), params::max_of(id));
        }
    }
    if (!ok) params::reset_defaults();
    load_calibration();
    params::clear_changed();
    return ok;
}

bool save_params() {
    uint16_t hash = params::layout_hash();
    uint8_t h[HEADER_LEN] = {'L', 'X', (uint8_t)hash, (uint8_t)(hash >> 8), (uint8_t)P_COUNT, 0};
    uint16_t crc = 0xFFFF;
    for (uint8_t i = 0; i < HEADER_LEN; i++) crc = crc16_update(crc, h[i]);
    bool ok = hal::storage_write(PARAM_ADDR, h, HEADER_LEN);
    const int16_t* v = params::raw();
    for (uint8_t i = 0; i < P_COUNT && ok; i++) {
        uint8_t b[2] = {(uint8_t)(uint16_t)v[i], (uint8_t)((uint16_t)v[i] >> 8)};
        crc = crc16_update(crc, b[0]);
        crc = crc16_update(crc, b[1]);
        ok = hal::storage_write((uint16_t)(PARAM_ADDR + HEADER_LEN + 2u * i), b, 2);
    }
    uint8_t c[2] = {(uint8_t)crc, (uint8_t)(crc >> 8)};
    if (ok) ok = hal::storage_write((uint16_t)(PARAM_ADDR + HEADER_LEN + 2u * P_COUNT), c, 2);
    if (ok) {
        uint8_t d[CAL_LEN];
        cal_bytes(d);
        ok = hal::storage_write(CAL_ADDR, d, CAL_LEN);
    }
    if (ok) params::clear_changed();
    return ok;
}

bool load_state(State& s) {
    bool found = false;
    uint8_t best_seq = 0;
    for (uint8_t i = 0; i < SLOTS; i++) {
        uint8_t d[SLOT_LEN];
        hal::storage_read((uint16_t)(RING_ADDR + i * SLOT_LEN), d, SLOT_LEN);
        if (crc8(d, 3) != d[3]) continue;
        // Newest = largest sequence number, compared in modulo-256 arithmetic.
        if (!found || (int8_t)(d[0] - best_seq) > 0) {
            found = true;
            best_seq = d[0];
            g_slot = i;
            s.locked = d[1] & 1u;
            s.mem_mode = (uint8_t)(d[1] >> 1);
            s.mem_level = d[2];
        }
    }
    if (found) {
        g_seq = best_seq;
        if (s.mem_level < 1 || s.mem_level > LEVEL_MAX) s.mem_level = (uint8_t)p(P_MEM_LEVEL);
        if (s.mem_mode > 4) s.mem_mode = 0;
    }
    return found;
}

bool save_state(const State& s) {
    g_slot = (uint8_t)((g_slot + 1) % SLOTS);
    g_seq++;
    uint8_t d[SLOT_LEN] = {g_seq, (uint8_t)((s.locked & 1u) | (uint8_t)(s.mem_mode << 1)), s.mem_level, 0};
    d[3] = crc8(d, 3);
    return hal::storage_write((uint16_t)(RING_ADDR + g_slot * SLOT_LEN), d, SLOT_LEN);
}

}  // namespace storage
}  // namespace lx
