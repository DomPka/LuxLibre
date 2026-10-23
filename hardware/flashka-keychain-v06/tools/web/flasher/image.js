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

/* ------------------------------------------------------------------------------------------------------------ *
 * which FlashKa a firmware belongs to
 * ------------------------------------------------------------------------------------------------------------ */

/** The app descriptor of an ESP-IDF style app image: after the 24-byte image header and the 8-byte header of the
 *  first segment, so at 0x10020 of a merged image. Magic 0xABCD5432, version at +16 (32 bytes), project at +48. */
export const APP_DESC_OFFSET = APP_OFFSET + 0x20;
export const APP_DESC_MAGIC = 0xabcd5432;

/**
 * The FlashKa main boards and the firmware that belongs to each (firmware/build.sh BOARD=v07 / v06). The v0.7
 * firmware drives the LED up to 3.0 A with a different current scale: it must never go onto a v0.6 board, and the
 * v0.6 firmware sets wrong currents on a v0.7 board.
 * @typedef {{ id: 'v07' | 'v06', title: string, hint: string, firmware: string }} Board
 * @type {Board[]}
 */
export const BOARDS = [
  { id: 'v07', title: 'FlashKa v0.7', hint: 'three keys in the middle', firmware: '0.7' },
  { id: 'v06', title: 'FlashKa v0.6', hint: 'stainless button', firmware: '0.6' }
];

/** @param {string} id @returns {Board | undefined} */
export function boardById(id) {
  return BOARDS.find((b) => b.id === id);
}

/** "FlashKa v0.7 (three keys in the middle)"; the id itself for an unknown board. @param {string} id */
export function boardLabel(id) {
  const b = boardById(id);
  return b ? `${b.title} (${b.hint})` : id;
}

/**
 * @typedef {Object} AppInfo
 * @property {boolean} found     a valid app descriptor is there
 * @property {string} version    e.g. "0.6.0" ("" when not found)
 * @property {string} project    e.g. "flashka-fw"
 * @property {'v07' | 'v06' | null} board   the FlashKa board this firmware is for, null when it is not FlashKa firmware
 */

/** @param {ArrayLike<number>} b @returns {string} printable text up to the first 0 byte */
function cString(b) {
  let s = '';
  for (let i = 0; i < b.length && b[i] !== 0; i++) {
    if (b[i] < 0x20 || b[i] > 0x7e) return '';
    s += String.fromCharCode(b[i]);
  }
  return s;
}

/**
 * Which board a firmware is for, from its app descriptor fields (FlashKa firmware only: project "flashka-fw").
 * @param {string} project @param {string} version
 * @returns {'v07' | 'v06' | null}
 */
export function boardOfFirmware(project, version) {
  if (project !== 'flashka-fw') return null;
  const b = BOARDS.find((x) => version.startsWith(x.firmware + '.'));
  return b ? b.id : null;
}

/**
 * Builds an AppInfo from the raw descriptor fields (the page reads them from the flashlight 4 bytes at a time).
 * @param {number} magic @param {ArrayLike<number>} versionBytes @param {ArrayLike<number>} projectBytes
 * @returns {AppInfo}
 */
export function appInfoFromFields(magic, versionBytes, projectBytes) {
  if (magic >>> 0 !== APP_DESC_MAGIC) return { found: false, version: '', project: '', board: null };
  const version = cString(versionBytes);
  const project = cString(projectBytes);
  return { found: true, version, project, board: boardOfFirmware(project, version) };
}

/**
 * Reads the app descriptor of a merged image (version and project name of the firmware inside).
 * @param {Uint8Array} bytes
 * @returns {AppInfo}
 */
export function readAppDescriptor(bytes) {
  const o = APP_DESC_OFFSET;
  if (bytes.length < o + 96) return { found: false, version: '', project: '', board: null };
  const magic = (bytes[o] | (bytes[o + 1] << 8) | (bytes[o + 2] << 16) | (bytes[o + 3] << 24)) >>> 0;
  return appInfoFromFields(magic, bytes.subarray(o + 16, o + 48), bytes.subarray(o + 48, o + 80));
}

/**
 * Version number from a file name such as "flashka-fw-v0.6.0-merged.bin" (or "...-v0.6.0-rc1-merged.bin").
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
