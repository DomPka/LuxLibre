// SPDX-License-Identifier: MIT OR Apache-2.0
// build_flasher.mjs: embeds the firmware, refuses bad files, builds a placeholder loudly, is reproducible.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeImage } from './helpers/synthetic-image.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, '..');
const SCRATCH = join(WEB, '.test-output', 'build-test');
rmSync(SCRATCH, { recursive: true, force: true });
mkdirSync(SCRATCH, { recursive: true });

/** @param {string[]} args */
function build(args) {
  const r = spawnSync(process.execPath, [join(WEB, 'build_flasher.mjs'), ...args], { encoding: 'utf8' });
  return { code: r.status, out: r.stdout, err: r.stderr };
}
const sha256 = (b) => createHash('sha256').update(b).digest('hex');
const meta = (html) => JSON.parse(/<script id="firmware-data" type="application\/json">([\s\S]*?)<\/script>/.exec(html)[1]);
const scripts = (html) => [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
function writeBin(name, bytes) { const p = join(SCRATCH, name); writeFileSync(p, bytes); return p; }

test('builds a page around a good merged image: size, SHA-256, version, bytes', () => {
  const image = makeImage({ size: 250 * 1024, seed: 11 });
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', image);
  const out = join(SCRATCH, 'good.html');
  const r = build(['--bin', bin, '--out', out]);
  assert.equal(r.code, 0, r.err);
  assert.ok(!/PLACEHOLDER/.test(r.err + r.out), 'no placeholder warning');
  assert.match(r.out, new RegExp(sha256(image)), 'the report shows the SHA-256');
  assert.match(r.out, /v1\.2\.3/);
  const html = readFileSync(out, 'utf8');
  const m = meta(html);
  assert.equal(m.placeholder, false);
  assert.equal(m.version, '1.2.3');
  assert.equal(m.fileName, 'aurora-fw-v1.2.3-merged.bin');
  assert.equal(m.size, image.length);
  assert.equal(m.sha256, sha256(image));
  assert.deepEqual(new Uint8Array(Buffer.from(m.base64, 'base64')), image, 'the embedded bytes are the file');
  assert.equal(m.esptoolJs, JSON.parse(readFileSync(join(WEB, 'node_modules/esptool-js/package.json'), 'utf8')).version);
  assert.ok(!existsSync(out + '.tmp'), 'no temporary file left behind');
});

test('is reproducible: the same inputs give a byte-identical page', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024, seed: 2 }));
  const a = join(SCRATCH, 'rep-a.html');
  const b = join(SCRATCH, 'rep-b.html');
  assert.equal(build(['--bin', bin, '--out', a]).code, 0);
  assert.equal(build(['--bin', bin, '--out', b]).code, 0);
  assert.ok(readFileSync(a).equals(readFileSync(b)));
});

test('missing firmware: a placeholder page and a LOUD warning, exit code 0', () => {
  const out = join(SCRATCH, 'missing.html');
  const r = build(['--bin', join(SCRATCH, 'does-not-exist.bin'), '--out', out]);
  assert.equal(r.code, 0);
  assert.match(r.err, /PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED/);
  assert.match(r.err, /does-not-exist\.bin/);
  assert.match(r.err, /node build_flasher\.mjs/, 'says how to build the real one');
  const html = readFileSync(out, 'utf8');
  const m = meta(html);
  assert.deepEqual([m.placeholder, m.base64, m.size, m.sha256, m.fileName], [true, '', 0, null, null]);
  assert.ok(html.length < 400000, 'small without firmware');
});

test('--placeholder forces the placeholder even when the firmware exists', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  const out = join(SCRATCH, 'forced.html');
  const r = build(['--bin', bin, '--out', out, '--placeholder']);
  assert.equal(r.code, 0);
  assert.match(r.err, /PLACEHOLDER BUILD/);
  assert.match(r.err, /--placeholder was given/);
  assert.equal(meta(readFileSync(out, 'utf8')).placeholder, true);
});

test('--require-firmware turns a missing firmware into an error (and writes nothing)', () => {
  const out = join(SCRATCH, 'required.html');
  const r = build(['--bin', join(SCRATCH, 'nope.bin'), '--out', out, '--require-firmware']);
  assert.equal(r.code, 1);
  assert.match(r.err, /ERROR: The firmware file does not exist/);
  assert.match(r.err, /nope\.bin/);
  assert.match(r.err, /firmware\/build\.sh/);
  assert.ok(!existsSync(out));
});

test('files that must not be flashed to address 0x0 are refused: too small, no ESP marker, other chip, not merged', () => {
  const cases = [
    ['tiny', new Uint8Array(100), /only 100 bytes/],
    ['nomagic', (() => { const b = makeImage({ size: 50000 }); b[0] = 0; return b; })(), /does not start with the ESP image marker/],
    ['s3', makeImage({ size: 50000, chipId: 9 }), /different chip \(chip id 9\)/],
    ['apponly', makeImage({ size: 150 * 1024, merged: false }), /does not look like a merged image for address 0x0/]
  ];
  for (const [name, bytes, re] of cases) {
    const out = join(SCRATCH, name + '.html');
    const r = build(['--bin', writeBin(`aurora-fw-v1.0.0-${name}.bin`, bytes), '--out', out]);
    assert.equal(r.code, 1, name);
    assert.match(r.err, re, name);
    assert.ok(!existsSync(out), name + ': no page written');
  }
});

test('--allow-unmerged embeds an app-only image anyway, with a warning', () => {
  const bin = writeBin('aurora-fw-v1.0.0-app.bin', makeImage({ size: 150 * 1024, merged: false }));
  const out = join(SCRATCH, 'unmerged.html');
  const r = build(['--bin', bin, '--out', out, '--allow-unmerged']);
  assert.equal(r.code, 0, r.err);
  assert.match(r.err, /WARNING: This does not look like a complete "merged" image/);
  assert.equal(meta(readFileSync(out, 'utf8')).placeholder, false);
});

test('--version overrides the file name; without either, package.json decides', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  let out = join(SCRATCH, 'ver1.html');
  assert.equal(build(['--bin', bin, '--out', out, '--version', '7.8.9']).code, 0);
  assert.equal(meta(readFileSync(out, 'utf8')).version, '7.8.9');
  const plain = writeBin('firmware.bin', makeImage({ size: 150 * 1024 }));
  out = join(SCRATCH, 'ver2.html');
  assert.equal(build(['--bin', plain, '--out', out]).code, 0);
  assert.equal(meta(readFileSync(out, 'utf8')).version, JSON.parse(readFileSync(join(WEB, 'package.json'), 'utf8')).version);
});

test('the page is ONE self-contained file: nothing external, scripts cannot be cut short', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  const out = join(SCRATCH, 'single.html');
  assert.equal(build(['--bin', bin, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  assert.doesNotMatch(html, /<script[^>]*\ssrc=/i, 'no external script');
  assert.doesNotMatch(html, /<link[^>]*rel=["']?stylesheet/i, 'no external stylesheet');
  assert.doesNotMatch(html, /(src|href)=["']https?:/i, 'no external resource');
  assert.doesNotMatch(html, /@import|url\(\s*["']?https?:/i, 'no CSS imports');
  assert.equal((html.match(/<\/script>/gi) || []).length, 2, 'exactly the two closing tags of the two script elements');
  for (const s of scripts(html)) assert.ok(!/<!--/.test(s), 'no HTML comment opener inside a script');
  assert.ok(!html.includes('__FIRMWARE_JSON__') && !html.includes('__BUNDLE__'), 'all placeholders of the template are replaced');
  assert.ok(html.charCodeAt(0) === 0x3c && /^<!doctype html>/i.test(html));
  assert.match(html, /<title>Aurora\+\+ firmware installer<\/title>/);
});

test('only the ESP32-C3 helper program is bundled (not the 13 other chips): small script, right stub', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  const out = join(SCRATCH, 'stub.html');
  assert.equal(build(['--bin', bin, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  const dir = join(WEB, 'node_modules/esptool-js/lib/targets/stub_flasher');
  const c3 = JSON.parse(readFileSync(join(dir, 'esp32c3.json'), 'utf8'));
  const s3 = JSON.parse(readFileSync(join(dir, 'esp32s3.json'), 'utf8'));
  assert.ok(html.includes(c3.text.slice(0, 120)), 'ESP32-C3 stub code present');
  assert.ok(html.includes(c3.data.slice(0, 60)), 'ESP32-C3 stub data present');
  assert.ok(!html.includes(s3.text.slice(0, 120)), 'ESP32-S3 stub code absent');
  const script = scripts(html)[1];
  assert.ok(script.length < 260 * 1024, `script is ${script.length} bytes`);
});

test('--no-minify gives readable code that still contains the page logic', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  const out = join(SCRATCH, 'readable.html');
  assert.equal(build(['--bin', bin, '--out', out, '--no-minify']).code, 0);
  assert.match(readFileSync(out, 'utf8'), /async function onInstall\(\)/);
});

test('error class names of esptool-js survive minifying (the page decides on them)', () => {
  const bin = writeBin('aurora-fw-v1.2.3-merged.bin', makeImage({ size: 150 * 1024 }));
  const out = join(SCRATCH, 'names.html');
  assert.equal(build(['--bin', bin, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  assert.match(html, /"ESPError"/);
  assert.match(html, /"UnsupportedCommandError"/);
});

test('--help, and a helpful message for a wrong option', () => {
  const h = build(['--help']);
  assert.equal(h.code, 0);
  assert.match(h.out, /--require-firmware/);
  assert.match(h.out, /--bin <file>/);
  const bad = build(['--frobnicate']);
  assert.equal(bad.code, 1);
  assert.match(bad.err, /Unknown option --frobnicate/);
  const noValue = build(['--bin']);
  assert.equal(noValue.code, 1);
  assert.match(noValue.err, /--bin needs a value/);
});

test('the real firmware, if it exists, builds without a placeholder warning', { skip: !existsSync(join(WEB, '../../firmware/dist/aurora-fw-v0.5.0-merged.bin')) }, () => {
  const out = join(SCRATCH, 'real.html');
  const r = build(['--out', out]);
  assert.equal(r.code, 0, r.err);
  assert.ok(!/PLACEHOLDER/.test(r.err));
  const real = readFileSync(join(WEB, '../../firmware/dist/aurora-fw-v0.5.0-merged.bin'));
  assert.equal(meta(readFileSync(out, 'utf8')).sha256, sha256(real));
});

test('leaves no stray files in the scratch folder', () => {
  assert.ok(readdirSync(SCRATCH).every((f) => !f.endsWith('.tmp')));
  rmSync(SCRATCH, { recursive: true, force: true });
});
