// SPDX-License-Identifier: MIT OR Apache-2.0
// Pure helpers about the firmware image: checks, number formatting, base64 and SHA-256.
// No DOM and no esptool here, so the same code runs in the page, in the build script and in the Node tests.

export const ESP_IMAGE_MAGIC = 0xe9;
export const CHIP_ID_ESP32C3 = 5;
/** Where the usual (espflash / ESP-IDF) layout keeps the partition table and the first app image. */
export const PARTITION_TABLE_OFFSET = 0x8000;
export const APP_OFFSET = 0x10000;
const MIN_IMAGE_BYTES = 0x1000;
const WARN_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_IMAGE_BYTES = 16 * 1024 * 1024;

/**
 * @typedef {Object} ImageInfo
 * @property {boolean} ok          the file may be written to address 0x0 of an ESP32-C3
 * @property {string[]} errors     why it must not be written
 * @property {string[]} warnings   suspicious, but allowed
 * @property {boolean} merged      looks like a complete flash image: bootloader at 0x0, partition table at 0x8000, app at 0x10000
 * @property {number} size         bytes
 * @property {number | null} chipId  chip id from the image header (5 = ESP32-C3)
 */

/**
 * Checks a firmware file before it is written to address 0x0.
 * @param {Uint8Array} bytes
 * @returns {ImageInfo}
 */
export function inspectImage(bytes) {
  /** @type {string[]} */ const errors = [];
  /** @type {string[]} */ const warnings = [];
  const size = bytes.length;
  let chipId = null;
  let merged = false;

  if (size < MIN_IMAGE_BYTES) {
    errors.push(`The file is only ${size} bytes - far too small to be a flashlight firmware.`);
  } else {
    if (bytes[0] !== ESP_IMAGE_MAGIC) {
      errors.push(`The file does not start with the ESP image marker 0xE9 (it starts with 0x${bytes[0].toString(16).toUpperCase().padStart(2, '0')}). It is not a firmware image for an ESP32 chip.`);
    } else {
      chipId = bytes[12] | (bytes[13] << 8);
      if (chipId !== CHIP_ID_ESP32C3) {
        errors.push(`The image is built for a different chip (chip id ${chipId}); the flashlight has an ESP32-C3 (chip id ${CHIP_ID_ESP32C3}).`);
      }
    }
    const hasTable = size > PARTITION_TABLE_OFFSET + 1 && bytes[PARTITION_TABLE_OFFSET] === 0xaa && bytes[PARTITION_TABLE_OFFSET + 1] === 0x50;
    const hasApp = size > APP_OFFSET && bytes[APP_OFFSET] === ESP_IMAGE_MAGIC;
    merged = errors.length === 0 && hasTable && hasApp;
    if (errors.length === 0 && !merged) {
      warnings.push('This does not look like a complete "merged" image (bootloader + partition table at 0x8000 + app at 0x10000). ' +
        'Writing it to address 0x0 replaces the bootloader and could leave the flashlight not starting.');
    }
  }
  if (size > MAX_IMAGE_BYTES) errors.push('The file is larger than the flash of any ESP32-C3 (16 MB).');
  else if (size > WARN_IMAGE_BYTES) warnings.push('The file is larger than 4 MB, the flash size of most ESP32-C3 modules.');
  return { ok: errors.length === 0, errors, warnings, merged, size, chipId };
}

/**
 * Version number from a file name such as "aurora-fw-v0.5.0-merged.bin" (or "...-v0.6.0-rc1-merged.bin").
 * @param {string} name
 * @returns {string | null}
 */
export function versionFromFileName(name) {
  const m = /-v(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc|dev|pre)\.?\d*)?)(?:-[A-Za-z]+)*\.bin$/.exec(name);
  return m ? m[1] : null;
}

/**
 * "1.18 MB", "512 KB", "37 bytes".
 * @param {number} n
 */
export function formatBytes(n) {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(2) + ' MB';
  if (n >= 1024) return Math.round(n / 1024) + ' KB';
  return n + ' bytes';
}

/**
 * Decodes base64 text to bytes (works in browsers and in Node).
 * @param {string} b64
 * @returns {Uint8Array}
 */
export function base64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * Encodes bytes as base64 (works in browsers and in Node).
 * @param {Uint8Array} bytes
 * @returns {string}
 */
export function bytesToBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, /** @type {any} */ (bytes.subarray(i, i + 0x8000)));
  return btoa(s);
}

/**
 * SHA-256 as lower-case hex, or null when this browser offers no WebCrypto (it needs a secure context).
 * @param {Uint8Array} bytes
 * @returns {Promise<string | null>}
 */
export async function sha256hex(bytes) {
  const subtle = globalThis.crypto && globalThis.crypto.subtle;
  if (!subtle) return null;
  const digest = new Uint8Array(await subtle.digest('SHA-256', /** @type {BufferSource} */ (bytes)));
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('');
}
