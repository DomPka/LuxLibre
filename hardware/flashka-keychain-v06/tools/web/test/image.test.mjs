// SPDX-License-Identifier: MIT OR Apache-2.0
// Firmware file checks and small helpers of the flasher.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  inspectImage, versionFromFileName, formatBytes, base64ToBytes, bytesToBase64, sha256hex,
  ESP_IMAGE_MAGIC, CHIP_ID_ESP32C3, PARTITION_TABLE_OFFSET, APP_OFFSET,
  APP_DESC_OFFSET, APP_DESC_MAGIC, BOARDS, boardById, boardLabel, boardOfFirmware, appInfoFromFields, readAppDescriptor
} from '../flasher/image.js';
import { makeImage, writeAppDescriptor } from './helpers/synthetic-image.mjs';

const DIST = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'firmware', 'dist');

test('constants match the ESP-IDF flash layout used by the firmware (partitions.csv)', () => {
  assert.equal(ESP_IMAGE_MAGIC, 0xe9);
  assert.equal(CHIP_ID_ESP32C3, 5);
  assert.equal(PARTITION_TABLE_OFFSET, 0x8000);
  assert.equal(APP_OFFSET, 0x10000);
});

test('a merged ESP32-C3 image is accepted without warnings', () => {
  const info = inspectImage(makeImage({ size: 300 * 1024 }));
  assert.equal(info.ok, true);
  assert.equal(info.merged, true);
  assert.deepEqual(info.errors, []);
  assert.deepEqual(info.warnings, []);
  assert.equal(info.chipId, 5);
  assert.equal(info.size, 300 * 1024);
});

test('rejected: too small, wrong marker, wrong chip, too big', () => {
  assert.equal(inspectImage(new Uint8Array(100)).ok, false);
  assert.match(inspectImage(new Uint8Array(100)).errors[0], /only 100 bytes/);

  const noMagic = makeImage({ size: 50000 });
  noMagic[0] = 0x7f;
  const a = inspectImage(noMagic);
  assert.equal(a.ok, false);
  assert.match(a.errors[0], /0xE9.*starts with 0x7F/);

  const s3 = inspectImage(makeImage({ size: 50000, chipId: 9 }));
  assert.equal(s3.ok, false);
  assert.match(s3.errors[0], /different chip \(chip id 9\)/);

  const huge = inspectImage(new Uint8Array(17 * 1024 * 1024).fill(0).map((_, i) => (i === 0 ? 0xe9 : 0)));
  assert.equal(huge.ok, false);
  assert.ok(huge.errors.some((e) => /16 MB/.test(e)));
});

test('allowed with a warning: an app-only image (no bootloader / partition table markers) and a file over 4 MB', () => {
  const appOnly = inspectImage(makeImage({ size: 200 * 1024, merged: false }));
  assert.equal(appOnly.ok, true);
  assert.equal(appOnly.merged, false);
  assert.equal(appOnly.warnings.length, 1);
  assert.match(appOnly.warnings[0], /does not look like a complete "merged" image/);

  const big = makeImage({ size: 5 * 1024 * 1024 });
  const info = inspectImage(big);
  assert.equal(info.ok, true);
  assert.ok(info.warnings.some((w) => /larger than 4 MB/.test(w)));
});

test('version from the file name', () => {
  assert.equal(versionFromFileName('flashka-fw-v0.6.0-merged.bin'), '0.6.0');
  assert.equal(versionFromFileName('flashka-fw-v1.12.3-merged.bin'), '1.12.3');
  assert.equal(versionFromFileName('flashka-fw-v0.6.0-rc1-merged.bin'), '0.6.0-rc1');
  assert.equal(versionFromFileName('flashka-fw-v0.6.0.bin'), '0.6.0');
  assert.equal(versionFromFileName('firmware.bin'), null);
  assert.equal(versionFromFileName('flashka-fw-merged.bin'), null);
});

test('formatBytes', () => {
  assert.equal(formatBytes(37), '37 bytes');
  assert.equal(formatBytes(512 * 1024), '512 KB');
  assert.equal(formatBytes(1234567), '1.18 MB');
});

test('base64 round trip, including large input and every byte value', () => {
  const all = Uint8Array.from({ length: 256 }, (_, i) => i);
  assert.deepEqual(base64ToBytes(bytesToBase64(all)), all);
  assert.equal(bytesToBase64(all), Buffer.from(all).toString('base64'));
  const big = makeImage({ size: 1234567 });
  assert.equal(bytesToBase64(big), Buffer.from(big).toString('base64'));
  assert.deepEqual(base64ToBytes(Buffer.from(big).toString('base64')), big);
  assert.equal(bytesToBase64(new Uint8Array(0)), '');
});

test('sha256hex matches Node crypto', async () => {
  const big = makeImage({ size: 200000 });
  assert.equal(await sha256hex(big), createHash('sha256').update(big).digest('hex'));
});

/* ---------------------------------------------------------------------------------------------------- boards */

test('the two FlashKa boards and the firmware line of each', () => {
  assert.deepEqual(BOARDS.map((b) => [b.id, b.title, b.hint, b.firmware]), [
    ['v07', 'FlashKa v0.7', 'three keys in the middle', '0.7'],
    ['v06', 'FlashKa v0.6', 'stainless button', '0.6']
  ]);
  assert.equal(boardById('v06')?.title, 'FlashKa v0.6');
  assert.equal(boardById('v05'), undefined);
  assert.equal(boardLabel('v07'), 'FlashKa v0.7 (three keys in the middle)');
  assert.equal(boardLabel('v06'), 'FlashKa v0.6 (stainless button)');
});

test('which board a firmware is for: FlashKa firmware 0.7.x -> v0.7, 0.6.x -> v0.6, anything else -> none', () => {
  assert.equal(boardOfFirmware('flashka-fw', '0.7.0'), 'v07');
  assert.equal(boardOfFirmware('flashka-fw', '0.7.12'), 'v07');
  assert.equal(boardOfFirmware('flashka-fw', '0.6.0'), 'v06');
  assert.equal(boardOfFirmware('flashka-fw', '0.5.0'), null, 'v0.5 firmware is not for either board');
  assert.equal(boardOfFirmware('flashka-fw', '0.70.0'), null, '0.70 is not 0.7');
  assert.equal(boardOfFirmware('flashka-fw', ''), null);
  assert.equal(boardOfFirmware('luxlibre', '0.7.0'), null, 'other firmware is never assigned a board');
});

test('app descriptor: read from a merged image at 0x10020 (magic, version at +16, project at +48)', () => {
  assert.equal(APP_DESC_OFFSET, 0x10020);
  assert.equal(APP_DESC_MAGIC, 0xabcd5432);
  const v07 = readAppDescriptor(makeImage({ size: 200 * 1024, version: '0.7.0' }));
  assert.deepEqual(v07, { found: true, version: '0.7.0', project: 'flashka-fw', board: 'v07' });
  assert.deepEqual(readAppDescriptor(makeImage({ size: 200 * 1024, version: '0.6.0' })).board, 'v06');
  assert.deepEqual(readAppDescriptor(makeImage({ size: 200 * 1024, version: '1.2.3', project: 'luxlibre' })),
    { found: true, version: '1.2.3', project: 'luxlibre', board: null });
  /* no descriptor: random bytes at 0x10020, a blank flash, a file that ends before it */
  assert.equal(readAppDescriptor(makeImage({ size: 200 * 1024 })).found, false);
  assert.equal(readAppDescriptor(new Uint8Array(0x20000).fill(0xff)).found, false);
  assert.equal(readAppDescriptor(new Uint8Array(0x10040)).found, false);
  /* the version and project fields are 32-byte C strings: unprintable bytes make the text unusable */
  const odd = makeImage({ size: 200 * 1024, version: '0.7.0' });
  odd[APP_DESC_OFFSET + 16 + 2] = 0x07;
  assert.deepEqual(readAppDescriptor(odd), { found: true, version: '', project: 'flashka-fw', board: null });
});

test('app descriptor from raw fields (what the page reads back from the flashlight)', () => {
  const buf = new Uint8Array(96);
  writeAppDescriptor(buf, 0, '0.6.0');
  const magic = (buf[0] | (buf[1] << 8) | (buf[2] << 16) | (buf[3] << 24)) >>> 0;
  assert.deepEqual(appInfoFromFields(magic, buf.subarray(16, 48), buf.subarray(48, 80)), { found: true, version: '0.6.0', project: 'flashka-fw', board: 'v06' });
  assert.deepEqual(appInfoFromFields(0xffffffff, buf.subarray(16, 48), buf.subarray(48, 80)), { found: false, version: '', project: '', board: null });
});

test('the published images name their own board (firmware/dist)', { skip: !existsSync(join(DIST, 'flashka-fw-v0.6.0-merged.bin')) }, () => {
  const v06 = readAppDescriptor(new Uint8Array(readFileSync(join(DIST, 'flashka-fw-v0.6.0-merged.bin'))));
  assert.deepEqual(v06, { found: true, version: '0.6.0', project: 'flashka-fw', board: 'v06' });
  const p07 = join(DIST, 'flashka-fw-v0.7.0-merged.bin');
  if (existsSync(p07)) {
    assert.deepEqual(readAppDescriptor(new Uint8Array(readFileSync(p07))), { found: true, version: '0.7.0', project: 'flashka-fw', board: 'v07' });
  }
});
