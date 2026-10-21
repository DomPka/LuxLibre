// SPDX-License-Identifier: MIT OR Apache-2.0
// Replacement for esptool-js's "stubFlasher.js" in the browser bundle (build_flasher.mjs redirects the import).
//
// esptool-js ships the small helper program ("stub") for 14 chips, about 130 KB of JSON each time. The flashlight has
// an ESP32-C3, so the page only needs that one. For every other chip this answers "no stub", which makes esptool-js
// carry on with the chip's built-in loader (the page refuses to write to other chips anyway).
//
// The shape of the result is the same as in esptool-js 0.7.0 (lib/stubFlasher.js).

import esp32c3 from 'esptool-js/lib/targets/stub_flasher/esp32c3.json';

/**
 * @param {string} dataStr base64 text
 * @returns {Uint8Array}
 */
export function decodeBase64Data(dataStr) {
  const decoded = atob(dataStr);
  const out = new Uint8Array(decoded.length);
  for (let i = 0; i < decoded.length; i++) out[i] = decoded.charCodeAt(i);
  return out;
}

/**
 * @param {string} chipName   e.g. "ESP32-C3"
 * @param {number} [chipRevision]
 * @returns {Promise<{ bss_start?: number, data: string, decodedData: Uint8Array, data_start: number, entry: number, text: string, decodedText: Uint8Array, text_start: number } | undefined>}
 */
export async function getStubJsonByChipName(chipName, chipRevision) {
  void chipRevision;
  if (chipName !== 'ESP32-C3') return undefined;
  const stub = /** @type {any} */ (esp32c3);
  return {
    bss_start: stub.bss_start,
    data: stub.data,
    data_start: stub.data_start,
    entry: stub.entry,
    text: stub.text,
    text_start: stub.text_start,
    decodedData: decodeBase64Data(stub.data),
    decodedText: decodeBase64Data(stub.text)
  };
}
