// SPDX-License-Identifier: MIT OR Apache-2.0
// build_flasher.mjs: embeds the firmware of both FlashKa boards, refuses bad files and the other board's image,
// builds a placeholder loudly, is reproducible.
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeImage } from './helpers/synthetic-image.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, '..');
const DIST = join(WEB, '../../firmware/dist');
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
/** A pair of good synthetic images (FlashKa firmware 0.7.3 and 0.6.3) and the arguments that embed them. */
function pair(seed = 1) {
  const v07 = makeImage({ size: 250 * 1024, seed, version: '0.7.3' });
  const v06 = makeImage({ size: 200 * 1024, seed: seed + 100, version: '0.6.3' });
  const p07 = writeBin(`flashka-fw-v0.7.3-merged-${seed}.bin`, v07);
  const p06 = writeBin(`flashka-fw-v0.6.3-merged-${seed}.bin`, v06);
  return { v07, v06, p07, p06, args: ['--bin-v07', p07, '--bin-v06', p06] };
}
const empty = { placeholder: true, version: null, fileName: null, size: 0, sha256: null, base64: '' };

test('builds a page with the firmware of both boards: size, SHA-256, version, bytes, board pictures', () => {
  const p = pair(11);
  const out = join(SCRATCH, 'good.html');
  const r = build([...p.args, '--out', out]);
  assert.equal(r.code, 0, r.err);
  assert.ok(!/PLACEHOLDER/.test(r.err + r.out), 'no placeholder warning');
  assert.match(r.out, new RegExp(`FlashKa v0\\.7: .*v0\\.7\\.3 .*${sha256(p.v07)}`), 'the report shows the v0.7 image');
  assert.match(r.out, new RegExp(`FlashKa v0\\.6: .*v0\\.6\\.3 .*${sha256(p.v06)}`), 'the report shows the v0.6 image');
  const html = readFileSync(out, 'utf8');
  const m = meta(html);
  assert.equal(m.placeholder, false);
  assert.equal(m.esptoolJs, JSON.parse(readFileSync(join(WEB, 'node_modules/esptool-js/package.json'), 'utf8')).version);
  assert.deepEqual(Object.keys(m.boards), ['v07', 'v06']);
  for (const [id, bytes, version] of [['v07', p.v07, '0.7.3'], ['v06', p.v06, '0.6.3']]) {
    const b = m.boards[id];
    assert.equal(b.placeholder, false, id);
    assert.equal(b.version, version, id + ': the version comes from the image (app descriptor)');
    assert.equal(b.size, bytes.length, id);
    assert.equal(b.sha256, sha256(bytes), id);
    assert.match(b.fileName, new RegExp(`flashka-fw-v${version.replace(/\./g, '\\.')}-merged`), id);
    assert.deepEqual(new Uint8Array(Buffer.from(b.base64, 'base64')), bytes, id + ': the embedded bytes are the file');
  }
  /* the two board pictures, as data: URIs, exactly the files in flasher/ */
  for (const id of ['v07', 'v06']) {
    const pic = readFileSync(join(WEB, 'flasher', `board-${id}.webp`)).toString('base64');
    assert.ok(html.includes(`src="data:image/webp;base64,${pic}"`), id + ' picture embedded');
  }
  assert.ok(!existsSync(out + '.tmp'), 'no temporary file left behind');
});

test('is reproducible: the same inputs give a byte-identical page', () => {
  const p = pair(2);
  const a = join(SCRATCH, 'rep-a.html');
  const b = join(SCRATCH, 'rep-b.html');
  assert.equal(build([...p.args, '--out', a]).code, 0);
  assert.equal(build([...p.args, '--out', b]).code, 0);
  assert.ok(readFileSync(a).equals(readFileSync(b)));
});

test('a missing image: that board gets a placeholder, a LOUD warning, exit code 0', () => {
  const p = pair(3);
  const out = join(SCRATCH, 'missing-one.html');
  const r = build(['--bin-v07', p.p07, '--bin-v06', join(SCRATCH, 'does-not-exist.bin'), '--out', out]);
  assert.equal(r.code, 0, r.err);
  assert.match(r.err, /PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED FOR ONE BOARD/);
  assert.match(r.err, /FlashKa v0\.6: .*does-not-exist\.bin/);
  const m = meta(readFileSync(out, 'utf8'));
  assert.equal(m.placeholder, false, 'the page still has one firmware');
  assert.deepEqual(m.boards.v06, empty);
  assert.equal(m.boards.v07.sha256, sha256(p.v07));
});

test('both images missing: a placeholder page, exit code 0, small file', () => {
  const out = join(SCRATCH, 'missing.html');
  const r = build(['--bin-v07', join(SCRATCH, 'nope7.bin'), '--bin-v06', join(SCRATCH, 'nope6.bin'), '--out', out]);
  assert.equal(r.code, 0);
  assert.match(r.err, /PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED IN THIS PAGE/);
  assert.match(r.err, /nope7\.bin/);
  assert.match(r.err, /nope6\.bin/);
  assert.match(r.err, /node build_flasher\.mjs/, 'says how to build the real one');
  assert.match(r.err, /BOARD=v07/, 'says how to build the firmware');
  const html = readFileSync(out, 'utf8');
  const m = meta(html);
  assert.equal(m.placeholder, true);
  assert.deepEqual(m.boards, { v07: empty, v06: empty });
  assert.ok(html.length < 400000, 'small without firmware: ' + html.length);
});

test('--placeholder forces the placeholder for both boards even when the images exist', () => {
  const p = pair(4);
  const out = join(SCRATCH, 'forced.html');
  const r = build([...p.args, '--out', out, '--placeholder']);
  assert.equal(r.code, 0);
  assert.match(r.err, /PLACEHOLDER BUILD/);
  assert.match(r.err, /--placeholder was given/);
  const m = meta(readFileSync(out, 'utf8'));
  assert.equal(m.placeholder, true);
  assert.deepEqual(m.boards, { v07: empty, v06: empty });
});

test('--require-firmware turns a missing image into an error (and writes nothing)', () => {
  const p = pair(5);
  const out = join(SCRATCH, 'required.html');
  const r = build(['--bin-v07', join(SCRATCH, 'nope.bin'), '--bin-v06', p.p06, '--out', out, '--require-firmware']);
  assert.equal(r.code, 1);
  assert.match(r.err, /ERROR: The FlashKa v0\.7 firmware file does not exist/);
  assert.match(r.err, /nope\.bin/);
  assert.match(r.err, /BOARD=v07 firmware\/build\.sh/);
  assert.ok(!existsSync(out));
});

test('the other board\'s image is refused in a slot: v0.6 firmware as v0.7 and the reverse, and non-FlashKa images', () => {
  const p = pair(6);
  const cases = [
    ['v06 image in the v0.7 slot', ['--bin-v07', p.p06, '--bin-v06', p.p06], /is not the FlashKa v0\.7 firmware: it contains firmware "flashka-fw" version 0\.6\.3 \(made for FlashKa v0\.6\)/],
    ['v07 image in the v0.6 slot', ['--bin-v07', p.p07, '--bin-v06', p.p07], /is not the FlashKa v0\.6 firmware: it contains firmware "flashka-fw" version 0\.7\.3 \(made for FlashKa v0\.7\)/],
    ['no app descriptor', ['--bin-v07', writeBin('flashka-fw-v0.7.9-merged.bin', makeImage({ size: 150 * 1024 })), '--bin-v06', p.p06], /no app descriptor/],
    ['other firmware', ['--bin-v07', writeBin('lux.bin', makeImage({ size: 150 * 1024, version: '0.7.0', project: 'luxlibre' })), '--bin-v06', p.p06], /firmware "luxlibre" version 0\.7\.0/],
    ['v0.5 firmware', ['--bin-v07', p.p07, '--bin-v06', writeBin('old.bin', makeImage({ size: 150 * 1024, version: '0.5.0' }))], /is not the FlashKa v0\.6 firmware/]
  ];
  for (const [name, args, re] of cases) {
    const out = join(SCRATCH, 'mismatch.html');
    const r = build([...args, '--out', out]);
    assert.equal(r.code, 1, name);
    assert.match(r.err, re, name);
    assert.match(r.err, /wrong current/, name + ': says why');
    assert.ok(!existsSync(out), name + ': no page written');
  }
});

test('--allow-board-mismatch (tests only) embeds a mismatching image with a warning', () => {
  const p = pair(7);
  const out = join(SCRATCH, 'allowed-mismatch.html');
  const r = build(['--bin-v07', p.p06, '--bin-v06', p.p06, '--out', out, '--allow-board-mismatch']);
  assert.equal(r.code, 0, r.err);
  assert.match(r.err, /WARNING: --allow-board-mismatch: the FlashKa v0\.7 slot gets firmware "flashka-fw" version 0\.6\.3/);
  assert.equal(meta(readFileSync(out, 'utf8')).boards.v07.sha256, sha256(p.v06));
});

test('files that must not be flashed to address 0x0 are refused: too small, no ESP marker, other chip, not merged', () => {
  const p = pair(8);
  const cases = [
    ['tiny', new Uint8Array(100), /only 100 bytes/],
    ['nomagic', (() => { const b = makeImage({ size: 70000, version: '0.7.1' }); b[0] = 0; return b; })(), /does not start with the ESP image marker/],
    ['s3', makeImage({ size: 70000, chipId: 9, version: '0.7.1' }), /different chip \(chip id 9\)/],
    ['apponly', makeImage({ size: 150 * 1024, merged: false, version: '0.7.1' }), /does not look like a merged image for address 0x0/]
  ];
  for (const [name, bytes, re] of cases) {
    const out = join(SCRATCH, name + '.html');
    const r = build(['--bin-v07', writeBin(`flashka-fw-v0.7.1-${name}.bin`, bytes), '--bin-v06', p.p06, '--out', out]);
    assert.equal(r.code, 1, name);
    assert.match(r.err, re, name);
    assert.ok(!existsSync(out), name + ': no page written');
  }
});

test('--allow-unmerged embeds an app-only image anyway, with a warning', () => {
  const p = pair(9);
  const bin = writeBin('flashka-fw-v0.7.1-app.bin', makeImage({ size: 150 * 1024, merged: false, version: '0.7.1' }));
  const out = join(SCRATCH, 'unmerged.html');
  const r = build(['--bin-v07', bin, '--bin-v06', p.p06, '--out', out, '--allow-unmerged']);
  assert.equal(r.code, 0, r.err);
  assert.match(r.err, /WARNING: This does not look like a complete "merged" image/);
  assert.equal(meta(readFileSync(out, 'utf8')).boards.v07.placeholder, false);
});

test('the options of the one-board page are gone, with a hint: --bin and --version', () => {
  const p = pair(10);
  let r = build(['--bin', p.p07]);
  assert.equal(r.code, 1);
  assert.match(r.err, /--bin is gone: .*--bin-v07 <file> and --bin-v06 <file>/);
  r = build([...p.args, '--version', '1.2.3']);
  assert.equal(r.code, 1);
  assert.match(r.err, /--version is gone: the version is read from each image/);
});

test('the page is ONE self-contained file: nothing external, scripts cannot be cut short', () => {
  const p = pair(12);
  const out = join(SCRATCH, 'single.html');
  assert.equal(build([...p.args, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  assert.doesNotMatch(html, /<script[^>]*\ssrc=/i, 'no external script');
  assert.doesNotMatch(html, /<link[^>]*rel=["']?stylesheet/i, 'no external stylesheet');
  assert.doesNotMatch(html, /(src|href)=["']https?:/i, 'no external resource');
  assert.doesNotMatch(html, /@import|url\(\s*["']?https?:/i, 'no CSS imports');
  assert.equal((html.match(/<\/script>/gi) || []).length, 2, 'exactly the two closing tags of the two script elements');
  for (const s of scripts(html)) assert.ok(!/<!--/.test(s), 'no HTML comment opener inside a script');
  for (const token of ['__FIRMWARE_JSON__', '__BUNDLE__', '__PICTURE_V07__', '__PICTURE_V06__']) assert.ok(!html.includes(token), token + ' replaced');
  assert.ok(html.charCodeAt(0) === 0x3c && /^<!doctype html>/i.test(html));
  assert.match(html, /<title>FlashKa firmware installer<\/title>/);
  assert.match(html, /FlashKa v0\.7<\/span>/);
  assert.match(html, /three keys in the middle/);
  assert.match(html, /stainless button/);
});

test('only the ESP32-C3 helper program is bundled (not the 13 other chips): small script, right stub', () => {
  const p = pair(13);
  const out = join(SCRATCH, 'stub.html');
  assert.equal(build([...p.args, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  const dir = join(WEB, 'node_modules/esptool-js/lib/targets/stub_flasher');
  const c3 = JSON.parse(readFileSync(join(dir, 'esp32c3.json'), 'utf8'));
  const s3 = JSON.parse(readFileSync(join(dir, 'esp32s3.json'), 'utf8'));
  assert.ok(html.includes(c3.text.slice(0, 120)), 'ESP32-C3 stub code present');
  assert.ok(html.includes(c3.data.slice(0, 60)), 'ESP32-C3 stub data present');
  assert.ok(!html.includes(s3.text.slice(0, 120)), 'ESP32-S3 stub code absent');
  const script = scripts(html)[1];
  assert.ok(script.length < 270 * 1024, `script is ${script.length} bytes`);
});

test('--no-minify gives readable code that still contains the page logic', () => {
  const p = pair(14);
  const out = join(SCRATCH, 'readable.html');
  assert.equal(build([...p.args, '--out', out, '--no-minify']).code, 0);
  const html = readFileSync(out, 'utf8');
  assert.match(html, /async function onInstall\(\)/);
  assert.match(html, /function boardConflict\(\)/);
});

test('error class names of esptool-js survive minifying (the page decides on them)', () => {
  const p = pair(15);
  const out = join(SCRATCH, 'names.html');
  assert.equal(build([...p.args, '--out', out]).code, 0);
  const html = readFileSync(out, 'utf8');
  assert.match(html, /"ESPError"/);
  assert.match(html, /"UnsupportedCommandError"/);
});

test('--help, and a helpful message for a wrong option', () => {
  const h = build(['--help']);
  assert.equal(h.code, 0);
  assert.match(h.out, /--require-firmware/);
  assert.match(h.out, /--bin-v07 <file>/);
  assert.match(h.out, /--bin-v06 <file>/);
  const bad = build(['--frobnicate']);
  assert.equal(bad.code, 1);
  assert.match(bad.err, /Unknown option --frobnicate/);
  const noValue = build(['--bin-v07']);
  assert.equal(noValue.code, 1);
  assert.match(noValue.err, /--bin-v07 needs a value/);
});

test('the real firmware of both boards, if it exists, builds without a placeholder warning',
  { skip: !(existsSync(join(DIST, 'flashka-fw-v0.7.0-merged.bin')) && existsSync(join(DIST, 'flashka-fw-v0.6.0-merged.bin'))) }, () => {
    const out = join(SCRATCH, 'real.html');
    const r = build(['--out', out, '--require-firmware']);
    assert.equal(r.code, 0, r.err);
    assert.ok(!/PLACEHOLDER/.test(r.err));
    const m = meta(readFileSync(out, 'utf8'));
    assert.equal(m.boards.v07.sha256, sha256(readFileSync(join(DIST, 'flashka-fw-v0.7.0-merged.bin'))));
    assert.equal(m.boards.v07.version, '0.7.0');
    assert.equal(m.boards.v06.sha256, sha256(readFileSync(join(DIST, 'flashka-fw-v0.6.0-merged.bin'))));
    assert.equal(m.boards.v06.version, '0.6.0');
  });

test('leaves no stray files in the scratch folder', () => {
  assert.ok(readdirSync(SCRATCH).every((f) => !f.endsWith('.tmp')));
  rmSync(SCRATCH, { recursive: true, force: true });
});
