// SPDX-License-Identifier: MIT OR Apache-2.0
// Makes a stand-in for the firmware file: not a working firmware, but with the markers of a merged ESP32-C3 image
// (bootloader header at 0, partition table at 0x8000, app header at 0x10000) and content that compresses like code.

/**
 * @param {{ size?: number, chipId?: number, merged?: boolean, seed?: number }} [options]
 * @returns {Uint8Array}
 */
export function makeImage(options = {}) {
  const size = options.size ?? 300 * 1024;
  const chipId = options.chipId ?? 5;
  const merged = options.merged ?? true;
  let x = ((options.seed ?? 1) * 2654435761) >>> 0 || 1;
  const next = () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x; };
  const img = new Uint8Array(size);
  /* half noise, half repetition: roughly the compressibility of real code */
  for (let i = 0; i < size; i += 4) {
    const r = next();
    const noisy = ((i >> 9) & 1) === 0;
    const v = noisy ? r : (0x20a0e0 + ((i >> 6) & 0x3)) | 0;
    img[i] = v & 0xff; if (i + 1 < size) img[i + 1] = (v >>> 8) & 0xff; if (i + 2 < size) img[i + 2] = (v >>> 16) & 0xff; if (i + 3 < size) img[i + 3] = (v >>> 24) & 0xff;
  }
  img[0] = 0xe9;
  img[12] = chipId & 0xff;
  img[13] = (chipId >> 8) & 0xff;
  if (merged && size > 0x10001) {
    img[0x8000] = 0xaa; img[0x8001] = 0x50;
    img[0x10000] = 0xe9;
  }
  return img;
}
