// SPDX-License-Identifier: MIT OR Apache-2.0
// The real esptool-js + our backend, talking to the pretend ESP32-C3 (test/helpers/fake-esp32c3.mjs).
// This is as close to the hardware as a machine without the flashlight can get: every byte on the "wire" is the
// real ROM / stub protocol, and the flash content is checked afterwards.

import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { createEspBackend, WrongChipError, FlashTooSmallError } from '../flasher/backend.js';
import { explainError } from '../flasher/friendly.js';
import { FakeEsp32c3, makeFakeSerial, OP } from './helpers/fake-esp32c3.mjs';
import { makeImage } from './helpers/synthetic-image.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const STUB = JSON.parse(readFileSync(join(HERE, '..', 'node_modules', 'esptool-js', 'lib', 'targets', 'stub_flasher', 'esp32c3.json'), 'utf8'));
const nodeMd5 = (bytes) => createHash('md5').update(bytes).digest('hex');
const b64 = (s) => Uint8Array.from(Buffer.from(s, 'base64'));

/** @param {object} [chipOptions] @param {object} [portOptions] @param {object} [backendOptions] */
function rig(chipOptions = {}, portOptions = {}, backendOptions = {}) {
  const chip = new FakeEsp32c3({ md5hex: nodeMd5, ...chipOptions });
  const serial = makeFakeSerial(chip, portOptions);
  /* the backend's default requestPort() uses navigator.serial, exactly as in the page */
  Object.defineProperty(globalThis.navigator, 'serial', { value: serial, configurable: true });
  const log = [];
  const lostCalls = [];
  const backend = createEspBackend({
    log: (text, newline) => log.push(newline ? text + '\n' : text),
    connectAttempts: 2,
    onLost: () => lostCalls.push(Date.now()),
    ...backendOptions
  });
  return { chip, serial, port: serial.port, backend, log, lostCalls, text: () => log.join('') };
}

test('connect: resets into download mode, identifies the chip, uploads the helper, reads the flash id', async () => {
  const r = rig();
  const info = await r.backend.connect();
  assert.equal(info.chip, 'ESP32-C3');
  assert.equal(info.description, 'ESP32-C3 (QFN32) (revision v0.4)');
  assert.equal(info.mac, '34:85:18:aa:bb:cc');
  assert.equal(info.flashBytes, 4 * 1024 * 1024);
  assert.equal(info.flashLabel, '4MB');
  assert.equal(r.backend.connected, true);

  assert.equal(r.chip.mode, 'stub', 'the helper program is running');
  assert.deepEqual(r.chip.resets, ['download'], 'one reset, into download mode');
  assert.equal(r.port.openCalls.length, 1);
  assert.equal(r.port.openCalls[0].baudRate, 115200);
  assert.deepEqual(r.serial.requestCalls[0], { filters: [{ usbVendorId: 0x303a }] }, 'only Espressif devices are offered');
  assert.equal(r.chip.commands[0], OP.SYNC);
  assert.ok(r.chip.commands.includes(OP.GET_SECURITY_INFO));
  assert.ok(!r.chip.commands.includes(OP.CHANGE_BAUDRATE), 'no baud-rate change (virtual USB port)');
  assert.ok(!r.chip.commands.includes(OP.FLASH_DEFL_BEGIN), 'connecting never writes');

  /* the uploaded helper is the ESP32-C3 stub, byte for byte */
  assert.equal(r.chip.memLoads.length, 2);
  const text = r.chip.memLoads.find((m) => m.offset === STUB.text_start);
  const data = r.chip.memLoads.find((m) => m.offset === STUB.data_start);
  assert.deepEqual(text.bytes, b64(STUB.text));
  assert.deepEqual(data.bytes, b64(STUB.data));
  assert.equal(r.chip.stubEntry, STUB.entry);

  assert.match(r.text(), /Chip is ESP32-C3 \(QFN32\) \(revision v0\.4\)/);
  assert.match(r.text(), /MAC: 34:85:18:aa:bb:cc/);
  assert.match(r.text(), /Stub running/);
  await r.backend.disconnect();
  assert.equal(r.backend.connected, false);
  assert.equal(r.port.isOpen, false);
});

test('connect: "show all ports" asks the browser without a filter', async () => {
  const r = rig();
  await r.backend.connect({ showAll: true });
  assert.deepEqual(r.serial.requestCalls[0], {});
  await r.backend.disconnect();
});

test('install: the image arrives byte for byte, is verified with MD5, and the chip is restarted', async () => {
  const r = rig();
  const image = makeImage({ size: 300 * 1024 });
  await r.backend.connect();
  const phases = [];
  const progress = [];
  const result = await r.backend.install({ image, onPhase: (p) => phases.push(p), onProgress: (f) => progress.push(f) });

  assert.deepEqual(r.chip.flash.subarray(0, image.length), image, 'flash content equals the file');
  assert.deepEqual(r.chip.flash.subarray(image.length, image.length + 64), new Uint8Array(64).fill(0xff), 'nothing beyond the file was touched');
  assert.deepEqual(r.chip.writes, [{ offset: 0, size: image.length }]);
  assert.equal(r.chip.md5Requests.length, 1);
  assert.equal(r.chip.md5Requests[0].digest, nodeMd5(image));
  assert.equal(r.chip.eraseAllCount, 0, 'no chip erase unless asked');
  assert.deepEqual(r.chip.endFlags, [1], 'the helper stays running until the page resets the chip itself');

  assert.deepEqual([...new Set(phases)], ['preparing', 'writing', 'verifying', 'restarting']);
  assert.equal(progress[0], 0);
  assert.equal(progress.at(-1), 1);
  for (let i = 1; i < progress.length; i++) assert.ok(progress[i] >= progress[i - 1], 'progress never goes backwards');
  assert.ok(progress.length > 5, 'many progress steps for a 300 KB image');
  assert.equal(result.bytes, image.length);

  /* restart: reset line pulled and released with IO0 high -> the chip boots the new firmware, port is closed */
  assert.deepEqual(r.chip.resets, ['download', 'app']);
  assert.equal(r.chip.mode, 'app');
  assert.deepEqual(r.chip.signalLog.slice(-2), [[false, true], [false, false]], 'RTS pulse with DTR low = plain reset');
  assert.equal(r.port.isOpen, false);
  assert.equal(r.backend.connected, false);
  assert.match(r.text(), /Hash of data verified/);
});

test('install: an image whose size is not a multiple of 4 is padded and still verifies', async () => {
  const r = rig();
  const image = makeImage({ size: 100 * 1024 + 3 });
  await r.backend.connect();
  await r.backend.install({ image });
  assert.deepEqual(r.chip.flash.subarray(0, image.length), image);
  assert.equal(r.chip.md5Requests[0].size, image.length + 1);
});

test('install: normal install keeps the data beyond the image, "factory reset" clears the whole flash first', async () => {
  const marker = new Uint8Array(4 * 1024 * 1024).fill(0xff);
  marker.fill(0x42, 0x3f0000, 0x3f0100);         /* "settings" far beyond the firmware */
  const image = makeImage({ size: 120 * 1024 });

  const keep = rig({ initialFlash: marker });
  await keep.backend.connect();
  await keep.backend.install({ image, eraseAll: false });
  assert.equal(keep.chip.flash[0x3f0000], 0x42, 'settings survive a normal install');

  const wipe = rig({ initialFlash: marker });
  await wipe.backend.connect();
  const phases = [];
  await wipe.backend.install({ image, eraseAll: true, onPhase: (p) => phases.push(p) });
  assert.equal(wipe.chip.flash[0x3f0000], 0xff, 'factory reset erased everything');
  assert.equal(wipe.chip.eraseAllCount, 1);
  assert.equal(wipe.chip.eraseAllBeforeWrite, true, 'the erase came before the first write');
  assert.deepEqual(wipe.chip.flash.subarray(0, image.length), image);
  assert.equal(phases[0], 'erasing');
});

test('wrong chip: refused before the helper is uploaded, nothing written, port closed', async () => {
  const r = rig({ chipId: 9 });
  await assert.rejects(r.backend.connect(), (e) => e instanceof WrongChipError && e.chipName === 'ESP32-S3');
  assert.ok(!r.chip.commands.includes(OP.MEM_BEGIN), 'no helper upload');
  assert.equal(r.chip.writes.length, 0);
  assert.equal(r.port.isOpen, false);
  assert.equal(r.backend.connected, false);
  const e = await r.backend.connect().catch((x) => x);
  assert.equal(explainError(e, 'connect').code, 'wrong-chip');
});

test('silent device: connect fails with a clear message and leaves the port closed so that Connect can be pressed again', async () => {
  const r = rig({ silent: true });
  const e = await r.backend.connect().catch((x) => x);
  assert.match(e.message, /Failed to connect with the device/);
  assert.equal(r.port.isOpen, false);
  assert.equal(r.backend.connected, false);
  const x = explainError(e, 'connect');
  assert.equal(x.code, 'no-sync');
  assert.match(x.steps.join(' '), /hold/i);
});

test('download mode by hand: the automatic reset does not work, holding the button does', async () => {
  const r = rig({ autoResetBroken: true });
  await assert.rejects(r.backend.connect(), /Failed to connect/);
  r.chip.holdButton(true);                         /* unplug, hold the button, plug in, release */
  const info = await r.backend.connect();
  assert.equal(info.chip, 'ESP32-C3');
  assert.equal(r.chip.mode, 'stub');
  assert.equal(r.port.openCalls.length, 2, 'the port was closed after the failure and opened again');
  await r.backend.disconnect();
});

test('port busy: another program holds the port', async () => {
  const r = rig({}, { openFails: 'busy' });
  const e = await r.backend.connect().catch((x) => x);
  assert.equal(e.name, 'NetworkError');
  assert.equal(explainError(e, 'connect').code, 'port-busy');
});

test('chooser closed or empty: NotFoundError, explained as neutral', async () => {
  const r = rig({}, { chooser: 'cancel' });
  const e = await r.backend.connect().catch((x) => x);
  assert.equal(e.name, 'NotFoundError');
  const x = explainError(e, 'connect');
  assert.equal(x.code, 'no-port-chosen');
  assert.equal(x.neutral, true);
  assert.equal(x.showAllPorts, true);
});

test('the helper does not start: explained, port closed', async () => {
  const r = rig({ stubFails: true });
  const e = await r.backend.connect().catch((x) => x);
  assert.match(e.message, /Failed to start stub/);
  assert.equal(explainError(e, 'connect').code, 'stub-failed');
  assert.equal(r.port.isOpen, false);
});

test('verification fails: install rejects, nothing is called "done", port closed', async () => {
  const r = rig({ md5Mismatch: true });
  await r.backend.connect();
  const e = await r.backend.install({ image: makeImage({ size: 80 * 1024 }) }).catch((x) => x);
  assert.match(e.message, /MD5 of file does not match/);
  assert.equal(explainError(e, 'install').code, 'verify-failed');
  assert.equal(r.port.isOpen, false);
  assert.equal(r.chip.resets.length, 1, 'no restart after a failed verification');
});

test('a block is rejected by the chip: esptool-js retries, then the install fails with a chip error', async () => {
  const r = rig({ failBlockSeq: 2 });
  await r.backend.connect();
  const e = await r.backend.install({ image: makeImage({ size: 400 * 1024 }) }).catch((x) => x);
  assert.match(e.message, /failed with status/);
  assert.equal(explainError(e, 'install').code, 'chip-error');
  assert.equal(r.port.isOpen, false);
});

test('cable pulled out in the middle of the install: fails at once with "connection lost"', async () => {
  const r = rig({ loseDeviceAfterBlocks: 2 });
  await r.backend.connect();
  const started = Date.now();
  const e = await r.backend.install({ image: makeImage({ size: 400 * 1024 }) }).catch((x) => x);
  assert.ok(Date.now() - started < 3000, 'no waiting for esptool-js time-outs');
  assert.equal(e.name, 'NetworkError');
  const x = explainError(e, 'install');
  assert.equal(x.code, 'device-lost');
  assert.match(x.title, /lost during the install/);
  assert.equal(r.backend.connected, false);
});

test('cable pulled out while connected (before Install): reported once, install refuses', async () => {
  const r = rig();
  await r.backend.connect();
  r.chip.pullCable();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(r.lostCalls.length, 1);
  assert.equal(r.backend.connected, false);
  const e = await r.backend.install({ image: makeImage({ size: 80 * 1024 }) }).catch((x) => x);
  assert.equal(explainError(e, 'install').code, 'device-lost');
});

test('image larger than the flash chip is refused before anything is written', async () => {
  const r = rig({ flashBytes: 256 * 1024, flashId: 0x1240ef });
  const info = await r.backend.connect();
  assert.equal(info.flashBytes, 256 * 1024);
  const e = await r.backend.install({ image: makeImage({ size: 300 * 1024 }) }).catch((x) => x);
  assert.ok(e instanceof FlashTooSmallError);
  assert.equal(explainError(e, 'install').code, 'flash-too-small');
  assert.equal(r.chip.writes.length, 0);
  assert.equal(r.port.isOpen, false);
});

test('connect twice in a row and reconnect after disconnect', async () => {
  const r = rig();
  await r.backend.connect();
  await r.backend.connect();                       /* the old link is closed first */
  assert.equal(r.backend.connected, true);
  await r.backend.disconnect();
  await r.backend.connect();
  assert.equal(r.chip.mode, 'stub');
  assert.deepEqual(r.chip.resets, ['download', 'download', 'download']);
  await r.backend.disconnect();
  assert.equal(r.port.isOpen, false);
});

/* ---------------------------------------------------------------- which firmware is on the flashlight now */

test('connect reads the installed firmware (app descriptor at 0x10020): FlashKa v0.6 firmware is recognised', async () => {
  const r = rig({ installedFirmware: { version: '0.6.0' } });
  const info = await r.backend.connect();
  assert.deepEqual(info.installed, { found: true, version: '0.6.0', project: 'flashka-fw', board: 'v06' });
  assert.deepEqual(r.chip.reads, [{ addr: 0x10020, size: 96 }], 'one 96-byte read through the helper program');
  assert.ok(r.chip.commands.includes(OP.READ_FLASH));
  assert.match(r.text(), /Installed firmware: flashka-fw 0\.6\.0/);
  /* the helper's trailing checksum packet must not confuse the install that follows */
  const image = makeImage({ size: 120 * 1024, version: '0.7.0' });
  await r.backend.install({ image });
  assert.deepEqual(r.chip.flash.subarray(0, image.length), image);
  assert.equal(r.chip.md5Requests[0].digest, nodeMd5(image));
});

test('connect: v0.7 firmware, other firmware and a blank flash', async () => {
  let r = rig({ installedFirmware: { version: '0.7.0' } });
  assert.equal((await r.backend.connect()).installed?.board, 'v07');
  await r.backend.disconnect();
  r = rig({ installedFirmware: { version: '0.3.0', project: 'luxlibre' } });
  assert.deepEqual((await r.backend.connect()).installed, { found: true, version: '0.3.0', project: 'luxlibre', board: null });
  await r.backend.disconnect();
  r = rig();
  const info = await r.backend.connect();
  assert.deepEqual(info.installed, { found: false, version: '', project: '', board: null }, 'new or erased flashlight');
  assert.match(r.text(), /Installed firmware: none found/);
  await r.backend.disconnect();
});

test('connect: a helper that refuses READ_FLASH gives "unknown" (null) and installing still works', async () => {
  const r = rig({ readFlashFails: true });
  const info = await r.backend.connect();
  assert.equal(info.installed, null);
  assert.match(r.text(), /Could not read the installed firmware/);
  const image = makeImage({ size: 100 * 1024 });
  await r.backend.install({ image });
  assert.deepEqual(r.chip.flash.subarray(0, image.length), image);
});

test('connect: a read that never ends fails the connection (port closed) instead of hanging', async () => {
  const r = rig({ readFlashStalls: true }, {}, { readTimeoutMs: 300 });
  const t0 = Date.now();
  await assert.rejects(r.backend.connect(), /Reading the installed firmware took too long/);
  assert.ok(Date.now() - t0 < 3000, 'fails after the time limit');
  assert.equal(r.port.isOpen, false, 'port released, Connect can be pressed again');
  assert.equal(r.backend.connected, false);
});
