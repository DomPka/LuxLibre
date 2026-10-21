// SPDX-License-Identifier: MIT OR Apache-2.0
// The flasher's own MD5 (the browser has none) against RFC 1321 and against Node's crypto.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { md5hex } from '../flasher/md5.js';

const ascii = (s) => new TextEncoder().encode(s);
const reference = (bytes) => createHash('md5').update(bytes).digest('hex');

test('RFC 1321 test suite', () => {
  const vectors = [
    ['', 'd41d8cd98f00b204e9800998ecf8427e'],
    ['a', '0cc175b9c0f1b6a831c399e269772661'],
    ['abc', '900150983cd24fb0d6963f7d28e17f72'],
    ['message digest', 'f96b697d7cb7938d525a2f31aaf161d0'],
    ['abcdefghijklmnopqrstuvwxyz', 'c3fcd3d76192e4007dfb496cca67e13b'],
    ['ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', 'd174ab98d277d9f5a5611c2c9f419d9f'],
    ['12345678901234567890123456789012345678901234567890123456789012345678901234567890', '57edf4a22be3c955ac49da2e2107b67a']
  ];
  for (const [text, digest] of vectors) assert.equal(md5hex(ascii(text)), digest, JSON.stringify(text));
});

test('every length from 0 to 400 bytes (all padding cases) matches Node crypto', () => {
  let x = 12345;
  const data = new Uint8Array(400).map(() => { x = (x * 1103515245 + 12345) >>> 0; return x >>> 24; });
  for (let n = 0; n <= 400; n++) assert.equal(md5hex(data.subarray(0, n)), reference(data.subarray(0, n)), `length ${n}`);
});

test('a view into a bigger buffer (unaligned byteOffset) is hashed correctly', () => {
  const buf = new Uint8Array(1000).map((_, i) => (i * 7) & 0xff);
  for (const [off, len] of [[1, 100], [3, 61], [5, 64], [7, 513], [999, 1]]) {
    assert.equal(md5hex(new Uint8Array(buf.buffer, off, len)), reference(buf.subarray(off, off + len)), `${off}+${len}`);
  }
});

test('a 3 MB image (like the flasher uses) matches Node crypto', () => {
  let x = 99;
  const data = new Uint8Array(3 * 1024 * 1024 + 3).map(() => { x = (x * 1664525 + 1013904223) >>> 0; return x >>> 23; });
  assert.equal(md5hex(data), reference(data));
});
