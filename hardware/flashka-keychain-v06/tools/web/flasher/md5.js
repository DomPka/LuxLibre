// SPDX-License-Identifier: MIT OR Apache-2.0
// MD5 (RFC 1321) for the flasher.
//
// esptool-js verifies every write by asking the chip for the MD5 of the flash area and comparing it with
// "calculateMD5Hash(image)". The browser has no MD5 (WebCrypto only offers SHA), so this is a small
// implementation of our own. It is unit-tested against Node's crypto module for many lengths (test/md5.test.mjs).

const S = [7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
  5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
  4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
  6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21];

/** K[i] = floor(2^32 * abs(sin(i + 1))) */
const K = new Int32Array(64);
for (let i = 0; i < 64; i++) K[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0;

/**
 * @param {Uint8Array} bytes
 * @returns {string} the MD5 digest as 32 lower-case hex characters
 */
export function md5hex(bytes) {
  const len = bytes.length;
  let a0 = 0x67452301, b0 = 0xefcdab89 | 0, c0 = 0x98badcfe | 0, d0 = 0x10325476;
  const M = new Int32Array(16);

  /** @param {DataView} view @param {number} off */
  function block(view, off) {
    for (let i = 0; i < 16; i++) M[i] = view.getInt32(off + i * 4, true);
    let A = a0, B = b0, C = c0, D = d0;
    for (let i = 0; i < 64; i++) {
      let F, g;
      if (i < 16) { F = (B & C) | (~B & D); g = i; }
      else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) & 15; }
      else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) & 15; }
      else { F = C ^ (B | ~D); g = (7 * i) & 15; }
      F = (F + A + K[i] + M[g]) | 0;
      A = D; D = C; C = B;
      B = (B + ((F << S[i]) | (F >>> (32 - S[i])))) | 0;
    }
    a0 = (a0 + A) | 0; b0 = (b0 + B) | 0; c0 = (c0 + C) | 0; d0 = (d0 + D) | 0;
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, len);
  const full = len - (len % 64);
  for (let off = 0; off < full; off += 64) block(view, off);

  /* the tail: remaining bytes, 0x80, zeros, 64-bit bit length (little endian) */
  const rest = len - full;
  const tailLen = rest + 9 <= 64 ? 64 : 128;
  const tail = new Uint8Array(tailLen);
  tail.set(bytes.subarray(full), 0);
  tail[rest] = 0x80;
  const tv = new DataView(tail.buffer);
  tv.setUint32(tailLen - 8, (len * 8) >>> 0, true);
  tv.setUint32(tailLen - 4, Math.floor(len / 0x20000000) >>> 0, true);
  for (let off = 0; off < tailLen; off += 64) block(tv, off);

  const out = new DataView(new ArrayBuffer(16));
  out.setInt32(0, a0, true); out.setInt32(4, b0, true); out.setInt32(8, c0, true); out.setInt32(12, d0, true);
  let hex = '';
  for (let i = 0; i < 16; i++) hex += out.getUint8(i).toString(16).padStart(2, '0');
  return hex;
}
