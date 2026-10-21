// SPDX-License-Identifier: MIT OR Apache-2.0
// Firmware file checks and small helpers of the flasher.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  inspectImage, versionFromFileName, formatBytes, base64ToBytes, bytesToBase64, sha256hex,
  ESP_IMAGE_MAGIC, CHIP_ID_ESP32C3, PARTITION_TABLE_OFFSET, APP_OFFSET
} from '../flasher/image.js';
import { makeImage } from './helpers/synthetic-image.mjs';

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
