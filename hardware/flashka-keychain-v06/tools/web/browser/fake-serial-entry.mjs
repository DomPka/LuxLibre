// SPDX-License-Identifier: MIT OR Apache-2.0
// Entry point that esbuild bundles into an init script for Playwright: puts the pretend ESP32-C3 behind
// navigator.serial before the flasher page runs. Options come from window.__FAKE_SERIAL_OPTIONS__ (set by an earlier
// init script): { chip: {...FakeEsp32c3 options}, port: {...}, absent: true (no navigator.serial at all) }.
// The test reaches the pretend hardware through window.__fake = { chip, serial, port }.
import { FakeEsp32c3, makeFakeSerial } from '../test/helpers/fake-esp32c3.mjs';

const options = /** @type {any} */ (window).__FAKE_SERIAL_OPTIONS__ || {};
if (options.absent) {
  Object.defineProperty(navigator, 'serial', { value: undefined, configurable: true });
} else {
  const chip = new FakeEsp32c3(options.chip || {});
  const serial = makeFakeSerial(chip, options.port || {});
  Object.defineProperty(navigator, 'serial', { value: serial, configurable: true });
  /** @type {any} */ (window).__fake = { chip, serial, port: serial.port };
}
