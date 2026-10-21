// SPDX-License-Identifier: MIT OR Apache-2.0
// Every error the flasher can meet is explained in plain words, with something to try.
import test from 'node:test';
import assert from 'node:assert/strict';
import { explainError, isDeviceLost, DOWNLOAD_MODE_STEPS } from '../flasher/friendly.js';

/** An error like the ones Chrome / esptool-js throw. */
function err(name, message, extra = {}) {
  const e = new Error(message);
  e.name = name;
  return Object.assign(e, extra);
}

/* [name, message, stage, expected code] - the messages are the real texts from Chrome and esptool-js 0.7.0 */
const CASES = [
  ['NotFoundError', 'No port selected by the user.', 'connect', 'no-port-chosen'],
  ['SecurityError', "Failed to execute 'requestPort' on 'Serial': Access to the feature \"serial\" is disallowed by permissions policy.", 'connect', 'not-allowed'],
  ['NotAllowedError', "Failed to execute 'requestPort' on 'Serial': Must be handling a user gesture to show a permission request.", 'connect', 'not-allowed'],
  ['NetworkError', 'Failed to open serial port.', 'connect', 'port-busy'],
  ['InvalidStateError', 'The port is already open.', 'connect', 'port-busy'],
  ['TypeError', "Failed to execute 'close' on 'SerialPort': Cannot cancel a locked stream", 'connect', 'port-busy'],
  ['NetworkError', 'The device has been lost.', 'connect', 'device-lost'],
  ['NetworkError', 'The device has been lost.', 'install', 'device-lost'],
  ['InvalidStateError', 'The port is closed.', 'install', 'device-lost'],
  ['ESPError', 'Failed to connect with the device', 'connect', 'no-sync'],
  ['ESPError', 'Serial data stream stopped: Possible serial noise or corruption.', 'connect', 'no-sync'],
  ['ESPError', 'Serial data stream stopped: Possible serial noise or corruption.', 'install', 'timeout'],
  ['ESPError', 'No serial data received.', 'install', 'timeout'],
  ['ESPError', 'Invalid head of packet (0x41): Possible serial noise or corruption.', 'install', 'timeout'],
  ['ESPError', 'Failed to start stub. Unexpected response FAIL', 'connect', 'stub-failed'],
  ['ESPError', 'Unable to verify flash chip connection Error: Serial data stream stopped', 'connect', 'flash-chip'],
  ['ESPError', 'MD5 of file does not match data in flash!', 'install', 'verify-failed'],
  ['ESPError', 'Failed to write compressed data to flash after seq 12 failed with status 1,8', 'install', 'chip-error'],
  ['ESPError', "File 1 doesn't fit in the available flash", 'install', 'flash-too-small'],
  ['FlashTooSmallError', 'The image is larger than the flash chip', 'install', 'flash-too-small'],
  ['UnexpectedChipIdError', 'Unexpected chip ID value 99. Failed to autodetect chip type.', 'connect', 'unknown-chip'],
  ['UnsupportedCommandError', 'unsupported command error', 'connect', 'restricted'],
  ['Error', 'something nobody has seen before', 'connect', 'unknown'],
  ['Error', 'something nobody has seen before', 'install', 'unknown']
];

for (const [name, message, stage, code] of CASES) {
  test(`${stage}: ${name} "${message.slice(0, 50)}" -> ${code}`, () => {
    const x = explainError(err(name, message), stage);
    assert.equal(x.code, code);
    assert.ok(x.title.length > 5 && x.title.length < 80, 'short title');
    assert.ok(x.message.length > 20, 'a real sentence');
    assert.ok(Array.isArray(x.steps) && x.steps.length >= 1, 'something to try');
    assert.ok(x.technical.includes(message), 'the original text is kept for support');
    /* no jargon in what the person reads */
    const shown = [x.title, x.message, ...x.steps].join(' ');
    for (const word of ['MD5', 'stub', 'esptool', 'SLIP', 'ROM', 'baud', 'Uint8Array', 'DOMException', 'ESPError', 'NetworkError']) {
      assert.ok(!shown.includes(word), `"${word}" in: ${shown}`);
    }
  });
}

test('minified class names ("F", "x") do not matter: the message decides, and the technical text hides such names', () => {
  const mangled = (message) => err('F', message);
  assert.equal(explainError(mangled('Unexpected chip ID value 99. Failed to autodetect chip type.'), 'connect').code, 'unknown-chip');
  assert.equal(explainError(mangled('Unexpected CHIP magic value 0x1234. Failed to autodetect chip type.'), 'connect').code, 'unknown-chip');
  assert.equal(explainError(mangled('unsupported command error'), 'connect').code, 'restricted');
  assert.equal(explainError(mangled('Failed to connect with the device'), 'connect').code, 'no-sync');
  assert.equal(explainError(mangled('Failed to connect with the device'), 'connect').technical, 'Failed to connect with the device');
  assert.equal(explainError(err('ESPError', 'Failed to connect with the device'), 'connect').technical, 'ESPError: Failed to connect with the device');
});

test('wrong chip names the chip, keeps the sentence plain, and nothing else', () => {
  const x = explainError(err('WrongChipError', 'Connected chip is ESP32-S3, expected ESP32-C3', { chipName: 'ESP32-S3' }), 'connect');
  assert.equal(x.code, 'wrong-chip');
  assert.match(x.message, /ESP32-S3/);
  assert.match(x.message, /Nothing was changed/);
});

test('"did not answer" offers the hold-the-button procedure, in the right order', () => {
  const x = explainError(err('ESPError', 'Failed to connect with the device'), 'connect');
  assert.deepEqual(x.steps, DOWNLOAD_MODE_STEPS);
  assert.match(DOWNLOAD_MODE_STEPS[0], /Unplug/);
  assert.match(DOWNLOAD_MODE_STEPS[1], /hold/);
  assert.match(DOWNLOAD_MODE_STEPS[2], /plug the USB cable in/);
  assert.match(DOWNLOAD_MODE_STEPS[3], /Let go/);
  assert.match(DOWNLOAD_MODE_STEPS[4], /Connect/);
});

test('the empty-chooser message mentions the cable and offers "show all ports"', () => {
  const x = explainError(err('NotFoundError', 'No port selected by the user.'), 'connect');
  assert.equal(x.showAllPorts, true);
  assert.equal(x.neutral, true);
  assert.match(x.steps.join(' '), /USB JTAG\/serial debug unit/);
  assert.match(x.steps.join(' '), /USB Serial Device/);
  assert.match(x.steps.join(' '), /only charge/);
});

test('status codes of the chip are translated; unknown codes are still reported', () => {
  const known = explainError(err('ESPError', 'Failed to write compressed data to flash after seq 3 failed with status 1,7'), 'install');
  assert.match(known.message, /damaged on the way/);
  const unknown = explainError(err('ESPError', 'Failed to erase flash failed with status 1,99'), 'install');
  assert.match(unknown.message, /error code 99/);
});

test('non-Error values (strings, undefined) do not crash', () => {
  assert.equal(explainError('boom', 'connect').code, 'unknown');
  assert.equal(explainError(undefined, 'install').code, 'unknown');
  assert.equal(explainError(null, 'install').code, 'unknown');
  assert.equal(explainError({ message: 'Failed to connect with the device' }, 'connect').code, 'no-sync');
});

test('isDeviceLost', () => {
  assert.equal(isDeviceLost(err('NetworkError', 'The device has been lost.')), true);
  assert.equal(isDeviceLost(err('NetworkError', 'Failed to open serial port.')), false);
  assert.equal(isDeviceLost(err('ESPError', 'The device has been lost.')), false);
  assert.equal(isDeviceLost(null), false);
});
