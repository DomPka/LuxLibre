// SPDX-License-Identifier: MIT OR Apache-2.0
// Headless browser tests for the firmware installer (app/aurora-flasher.html) and the menu page (app/index.html).
//
//   node browser/run-flasher-tests.mjs              run the checks (also rebuilds the flasher first)
//   node browser/run-flasher-tests.mjs --no-shots   run the checks without writing screenshots
//
// The page is the REAL page with the REAL esptool-js; only the hardware is pretend: navigator.serial is replaced by
// test/helpers/fake-esp32c3.mjs (a pretend ESP32-C3 that speaks the chip's actual serial protocol).
//
// 1. build: the real page, a placeholder page, a page with a synthetic firmware, a tampered copy
// 2. placeholder page: loads, says so, nothing embedded, Install disabled, own file via "Advanced" still works
// 3. page with firmware: firmware card, connect -> install -> done (flash content checked), factory reset, log
// 4. every failure explained: closed chooser, chip not answering (then the hold-the-button way), wrong chip,
//    failed verification, cable pulled out, port busy, unplugged while connected
// 5. "Advanced" file panel: wrong chip / too small / app-only image (needs a tick) / back to the built-in firmware
// 6. unsupported browsers (Firefox, Safari, iPhone, Android, plain Chrome without Web Serial, insecure page)
// 7. damaged page (changed firmware bytes) is refused
// 8. no horizontal scrolling, touch targets, at 320 / 360 / 390 / 1280 px
// 9. menu page
// 10. screenshots at 390x844 and 1280x800 into app/screenshots/
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import {
  launch, createSuite, newPage, shot, FLASHER_URL, INDEX_URL, APP_URL, APP_DIR, OUT_DIR, buildFlasher, fakeSerialInit,
  assert, assertEqual, assertMatch, text, noErrors
} from './lib.mjs';
import { makeImage } from '../test/helpers/synthetic-image.mjs';

const NO_SHOTS = process.argv.includes('--no-shots');
const suite = createSuite('Firmware installer (app/aurora-flasher.html) and menu page (app/index.html)');

const SYNTH_VERSION = '9.9.9';
const synthImage = makeImage({ size: 300 * 1024, seed: 7 });
const synthPath = path.join(OUT_DIR, 'fw', `aurora-fw-v${SYNTH_VERSION}-merged.bin`);
const placeholderPath = path.join(OUT_DIR, 'flasher-placeholder.html');
const synthPagePath = path.join(OUT_DIR, 'flasher-synthetic.html');
const tamperedPath = path.join(OUT_DIR, 'flasher-tampered.html');
const PLACEHOLDER_URL = pathToFileURL(placeholderPath).href;
const SYNTH_URL = pathToFileURL(synthPagePath).href;
const TAMPERED_URL = pathToFileURL(tamperedPath).href;
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

let realPageIsPlaceholder = false;
let realFirmware = null;           /* bytes of the firmware the real page embeds (null for a placeholder build) */

/* ================================================================== 1. build */
fs.rmSync(OUT_DIR, { recursive: true, force: true });
fs.mkdirSync(path.dirname(synthPath), { recursive: true });
await suite.step('build: the real page (app/aurora-flasher.html) with `node build_flasher.mjs`', async () => {
  const r = buildFlasher([]);
  assertEqual(r.code, 0, 'build exit code\n' + r.stderr);
  realPageIsPlaceholder = /PLACEHOLDER BUILD/.test(r.stderr);
  const bin = path.resolve(APP_DIR, '../firmware/dist/aurora-fw-v0.5.0-merged.bin');
  if (!realPageIsPlaceholder) {
    realFirmware = new Uint8Array(fs.readFileSync(bin));
    assertMatch(r.stdout, new RegExp(sha256(realFirmware)), 'the build reports the SHA-256 of the firmware');
  }
  suite.note(realPageIsPlaceholder ? 'no firmware file yet: the real page is a PLACEHOLDER build' : `real page embeds ${path.basename(bin)} (${realFirmware.length} bytes)`);
});
await suite.step('build: placeholder variant, variant with a synthetic firmware, tampered copy', async () => {
  let r = buildFlasher(['--placeholder', '--out', placeholderPath]);
  assertEqual(r.code, 0, r.stderr);
  assertMatch(r.stderr, /PLACEHOLDER BUILD/);
  fs.writeFileSync(synthPath, synthImage);
  r = buildFlasher(['--bin', synthPath, '--out', synthPagePath]);
  assertEqual(r.code, 0, r.stderr);
  assert(!/PLACEHOLDER/.test(r.stderr), 'no placeholder warning when a firmware is given');
  const html = fs.readFileSync(synthPagePath, 'utf8');
  /* change one letter of the embedded firmware (keeps the length, breaks the fingerprint) */
  const at = html.indexOf('"base64":"') + 10 + 5000;
  const flipped = html.slice(0, at) + (html[at] === 'A' ? 'B' : 'A') + html.slice(at + 1);
  fs.writeFileSync(tamperedPath, flipped);
});

const browser = await launch();

/* ------------------------------------------------------------------ helpers */
/** Opens a page with the pretend hardware. o: chip, port, absent, width, height, dark, ua, insecure */
async function open(url, o = {}) {
  const init = await fakeSerialInit({ chip: o.chip || {}, port: o.port || {}, absent: !!o.absent });
  if (o.insecure) init.unshift('Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });');
  const h = await newPage(browser, url, { width: o.width || 1280, height: o.height || 800, dark: !!o.dark, userAgent: o.ua, reducedMotion: 'reduce', init });
  await h.page.waitForFunction(() => window.__flasher && document.getElementById('fw-name').textContent !== '-', null, { timeout: 5000 });
  return h;
}
const bodyState = (page) => page.evaluate(() => document.body.dataset.state);
const stepStates = (page) => page.evaluate(() => ['step-1', 'step-2', 'step-3', 'step-4'].map((id) => document.getElementById(id).dataset.status));
const card = (page) => page.evaluate(() => {
  const c = document.getElementById('error-card');
  return c.hidden ? null : { title: document.getElementById('error-title').textContent, message: document.getElementById('error-message').textContent,
    steps: Array.from(document.querySelectorAll('#error-steps li')).map((li) => li.textContent), tech: document.getElementById('error-tech').textContent,
    neutral: c.classList.contains('neutral'), showAll: !document.getElementById('btn-error-showall').hidden };
});
async function untilState(page, st, timeout = 25000) {
  try { await page.waitForFunction((s) => document.body.dataset.state === s, st, { timeout, polling: 25 }); }
  catch { throw new Error(`state never became "${st}"; it is "${await bodyState(page)}"; problem card: ${JSON.stringify(await card(page))}`); }
}
const disabled = (page, id) => page.evaluate((i) => document.getElementById(i).disabled, id);
const hidden = (page, id) => page.evaluate((i) => document.getElementById(i).hidden, id);
const flashSha = (page, n) => page.evaluate(async (len) => {
  const d = await crypto.subtle.digest('SHA-256', window.__fake.chip.flash.subarray(0, len));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join('');
}, n);
const flashBlank = (page, from, n) => page.evaluate(([f, c]) => window.__fake.chip.flash.subarray(f, f + c).every((b) => b === 0xff), [from, n]);
const chip = (page) => page.evaluate(() => {
  const c = window.__fake.chip;
  return { mode: c.mode, resets: c.resets, writes: c.writes, md5: c.md5Requests, eraseAllCount: c.eraseAllCount, eraseAllBeforeWrite: c.eraseAllBeforeWrite,
           commands: c.commands.length, portOpen: window.__fake.port.isOpen, requests: window.__fake.serial.requestCalls, closeCalls: window.__fake.port.closeCalls };
});
async function startRecording(page) {
  await page.evaluate(() => {
    window.__rec = [];
    const read = () => ({ state: document.body.dataset.state, phase: document.getElementById('phase-text').textContent, pct: document.getElementById('phase-pct').textContent, now: Number(document.getElementById('progress').getAttribute('aria-valuenow')), pill: document.getElementById('pill-text').textContent, title: document.title });
    window.__recTimer = setInterval(() => window.__rec.push(read()), 10);
  });
}
const stopRecording = (page) => page.evaluate(() => { clearInterval(window.__recTimer); return window.__rec; });
const uploadFile = (page, name, bytes) => page.setInputFiles('#file-input', { name, mimeType: 'application/octet-stream', buffer: Buffer.from(bytes) });
async function connect(page) { await page.click('#btn-connect'); await untilState(page, 'connected'); }
const to = async (page, id) => { await page.evaluate((i) => { document.getElementById(i).scrollIntoView({ block: 'start' }); window.scrollBy(0, -84); }, id); await page.waitForTimeout(80); };
const top = async (page) => { await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(80); };

/* ================================================================== 2. placeholder page */
{
  const h = await open(PLACEHOLDER_URL);
  const { page } = h;
  await suite.step('placeholder page: loads without errors, says there is no firmware, nothing is embedded', async () => {
    assertEqual(await page.title(), 'Aurora++ firmware installer');
    assert(!(await hidden(page, 'placeholder-banner')), 'placeholder banner visible');
    assertMatch(await text(page, 'placeholder-banner'), /no firmware inside/);
    assertMatch(await text(page, 'fw-name'), /None included/);
    assertEqual(await bodyState(page), 'idle');
    assert(await disabled(page, 'btn-install'), 'Install disabled');
    const html = fs.readFileSync(placeholderPath, 'utf8');
    const meta = JSON.parse(/<script id="firmware-data" type="application\/json">([\s\S]*?)<\/script>/.exec(html)[1]);
    assertEqual([meta.placeholder, meta.base64, meta.size, meta.sha256, meta.fileName], [true, '', 0, null, null], 'no firmware bytes in the file');
    assert(html.length < 400000, 'the placeholder page is small: ' + html.length);
    noErrors(h);
  });
  await suite.step('placeholder page: connecting works, installing stays impossible', async () => {
    await connect(page);
    assertMatch(await text(page, 'connect-status'), /Flashlight found \(ESP32-C3, 4MB memory\)/);
    assert(await disabled(page, 'btn-install'), 'Install still disabled without a firmware');
    assertMatch(await text(page, 'fw-check'), /Nothing to install yet/);
    noErrors(h);
  });
  await suite.step('placeholder page: a .bin chosen under "Advanced" is installed (flash equals the file)', async () => {
    const image = makeImage({ size: 200 * 1024, seed: 3 });
    await page.click('#advanced > summary');
    await uploadFile(page, 'my-own-build.bin', image);
    await page.waitForFunction(() => !document.getElementById('file-report').hidden);
    assertMatch(await text(page, 'file-report'), /my-own-build\.bin - 200 KB/);
    assertMatch(await text(page, 'file-report'), /complete firmware image/);
    assertMatch(await text(page, 'fw-tag'), /your own file/);
    assert(!(await disabled(page, 'btn-install')), 'Install enabled');
    await page.click('#btn-install');
    await untilState(page, 'done');
    assertEqual(await flashSha(page, image.length), sha256(image), 'flash content = file');
    noErrors(h);
  });
  await h.close();
}

/* ================================================================== 3. page with firmware */
await suite.step('firmware card: version, size, SHA-256 and the integrity check come from the embedded image', async () => {
  const h = await open(SYNTH_URL);
  const { page } = h;
  assertMatch(await text(page, 'fw-name'), new RegExp(`Aurora\\+\\+ firmware v${SYNTH_VERSION}`));
  assertEqual(await text(page, 'fw-sha'), sha256(synthImage));
  assertMatch(await text(page, 'fw-size'), /300 KB \(307,200 bytes\)/);
  assertMatch(await text(page, 'fw-check'), /fingerprint matches/);
  assertMatch(await text(page, 'fw-check'), /complete image for an ESP32-C3/);
  assertMatch(await text(page, 'fw-tag'), /included in this page/);
  assert(await hidden(page, 'placeholder-banner') && await hidden(page, 'damaged-banner') && await hidden(page, 'unsupported'), 'no warnings');
  assertEqual(await stepStates(page), ['active', 'active', 'todo', 'todo']);
  assert(await disabled(page, 'btn-install'), 'Install waits for Connect');
  assert(!(await disabled(page, 'btn-connect')), 'Connect enabled');
  assertMatch(await text(page, 'foot-text'), new RegExp(`firmware v${SYNTH_VERSION}`));
  noErrors(h);
  await h.close();
});

await suite.step('happy path: Connect -> Install -> Done, with the right states, phases and a verified flash', async () => {
  const h = await open(SYNTH_URL, { chip: { commandDelayMs: 30 } });
  const { page } = h;
  assertMatch(await text(page, 'pill-text'), /Not connected/);

  await page.click('#btn-connect');
  assertEqual(await bodyState(page), 'connecting');
  assert(await disabled(page, 'btn-connect'), 'Connect disabled while connecting');
  await untilState(page, 'connected');
  assertEqual(await stepStates(page), ['done', 'done', 'active', 'todo']);
  assertMatch(await text(page, 'connect-status'), /^✓ Flashlight found \(ESP32-C3, 4MB memory\)\.$/);
  assertEqual(await text(page, 'pill-text'), 'Connected');
  assert(!(await disabled(page, 'btn-install')), 'Install enabled');
  assert(await hidden(page, 'connect-actions'), 'the Connect button gives way to the status once connected');
  assert(!(await hidden(page, 'connect-extra')), '"Disconnect and choose another port" offered');
  let c = await chip(page);
  assertEqual(c.mode, 'stub');
  assertEqual(c.writes.length, 0, 'connecting writes nothing');
  assertEqual(c.requests[0], { filters: [{ usbVendorId: 0x303a }] }, 'the chooser only offers Espressif devices');

  await startRecording(page);
  await page.click('#btn-install');
  assertEqual(await bodyState(page), 'installing');
  assert(await disabled(page, 'btn-install') && await disabled(page, 'chk-erase'), 'controls locked while installing');
  await untilState(page, 'done');
  const rec = await stopRecording(page);

  /* what the person saw while it ran */
  const phases = [...new Set(rec.filter((r) => r.state === 'installing').map((r) => r.phase))];
  assertEqual(phases, ['Preparing the firmware...', 'Writing the firmware...', 'Checking that everything was written correctly...', 'Restarting the flashlight...']);
  const writing = rec.filter((r) => r.state === 'installing' && r.phase === 'Writing the firmware...');
  assert(writing.length >= 3, 'progress was visible for a while: ' + writing.length + ' samples');
  for (let i = 1; i < writing.length; i++) assert(writing[i].now >= writing[i - 1].now, 'progress bar never goes backwards');
  assert(writing.some((r) => r.now > 0 && r.now < 100), 'intermediate percentages appeared');
  assertMatch(writing.find((r) => r.now > 0).pill, /^Installing\.\.\. \d+%$/);
  assert(rec.some((r) => r.title === 'Installing... keep this tab open'), 'tab title warns while installing');
  assertEqual(await page.title(), 'Aurora++ firmware installer', 'tab title restored');

  /* the result */
  assertEqual(await stepStates(page), ['done', 'done', 'done', 'active']);
  assertEqual(await text(page, 'phase-text'), 'Installed and checked');
  assertEqual(await text(page, 'phase-pct'), '100%');
  assertEqual(await page.getAttribute('#progress', 'aria-valuenow'), '100');
  assertMatch(await text(page, 'install-status'), /300 KB written in \d+ seconds\. The data on the flashlight was compared with the file and is identical\./);
  assertEqual(await text(page, 'pill-text'), 'Installed');
  assert(!(await hidden(page, 'done-actions')), 'done actions visible');
  assert(await hidden(page, 'install-controls'), 'the tick box and Install button give way to the result');
  assertEqual(await page.getAttribute('#done-actions a', 'href'), 'aurora-app.html');
  assertMatch(await text(page, 'done-text'), /unplug the USB cable and plug it in again/);
  assertMatch(await text(page, 'done-text'), /press its button once/);
  assertEqual(await flashSha(page, synthImage.length), sha256(synthImage), 'flash content = embedded firmware');
  assert(await flashBlank(page, synthImage.length, 4096), 'nothing beyond the image was touched');
  c = await chip(page);
  assertEqual(c.writes, [{ offset: 0, size: synthImage.length }]);
  assertEqual(c.md5[0].digest.length, 32);
  assertEqual(c.eraseAllCount, 0, 'no chip erase without the checkbox');
  assertEqual(c.resets, ['download', 'app'], 'download mode for the install, then a normal restart');
  assertEqual(c.mode, 'app');
  assertEqual(c.portOpen, false, 'the port is closed at the end');
  noErrors(h);

  /* and again on a second flashlight (same page, no reload) */
  await page.click('#btn-again');
  assertEqual(await bodyState(page), 'idle');
  assertEqual(await stepStates(page), ['active', 'active', 'todo', 'todo']);
  await connect(page);
  await page.click('#btn-install');
  await untilState(page, 'done');
  assertEqual(await flashSha(page, synthImage.length), sha256(synthImage));
  assertEqual((await chip(page)).writes.length, 2);
  noErrors(h);
  await h.close();
});

await suite.step('"factory reset" ticked: the whole flash is erased first', async () => {
  const stale = [{ from: 0x3f0000, length: 0x200, value: 0x42 }];      /* "settings" far beyond the firmware */
  const h = await open(SYNTH_URL, { chip: { initialFill: stale } });
  const { page } = h;
  assert(!(await page.isChecked('#chk-erase')), 'unticked by default');
  assertMatch(await page.locator('label[for="chk-erase"]').textContent(), /Factory reset \(clear the whole flash first\)/);
  assert(!(await flashBlank(page, 0x3f0000, 0x200)), 'the pretend flash starts with old data');
  await connect(page);
  await page.check('#chk-erase');
  await startRecording(page);
  await page.click('#btn-install');
  await untilState(page, 'done');
  const rec = await stopRecording(page);
  assert(rec.some((r) => /^Erasing the flashlight's memory/.test(r.phase)), 'the erase phase is announced');
  const c = await chip(page);
  assertEqual([c.eraseAllCount, c.eraseAllBeforeWrite], [1, true]);
  assert(await flashBlank(page, 0x3f0000, 0x200), 'old data beyond the image is gone');
  assertEqual(await flashSha(page, synthImage.length), sha256(synthImage));
  /* the same flash without the tick keeps data beyond the image */
  const h2 = await open(SYNTH_URL, { chip: { initialFill: stale } });
  await connect(h2.page);
  await h2.page.click('#btn-install');
  await untilState(h2.page, 'done');
  assert(!(await flashBlank(h2.page, 0x3f0000, 0x200)), 'without the tick, data beyond the image stays');
  noErrors(h); noErrors(h2);
  await h.close(); await h2.close();
});

await suite.step('technical log: esptool-js output, collapsed by default, copy button', async () => {
  const h = await open(SYNTH_URL);
  const { page } = h;
  assert(!(await page.evaluate(() => document.getElementById('log-panel').open)), 'log panel collapsed');
  await connect(page);
  await page.click('#btn-install');
  await untilState(page, 'done');
  await page.waitForTimeout(400);                       /* the log is drawn a moment later */
  const log = await text(page, 'log');
  for (const re of [/esptool\.js/, /Connecting\.\.\./, /Chip is ESP32-C3 \(QFN32\) \(revision v0\.4\)/, /MAC: 34:85:18:aa:bb:cc/, /Uploading stub/, /Stub running/, /Flash ID: 1640ef/,
                    /Compressed 307200 bytes to \d+/, /Writing at 0x0+\.\.\. \(\d+%\)/, /Wrote 307200 bytes \(\d+ compressed\) at 0x0/, /Hash of data verified\./, /Hard resetting via RTS pin/, /\[page\] Done in/]) {
    assertMatch(log, re, 'log line');
  }
  await page.evaluate(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: (t) => { window.__copied = t; return Promise.resolve(); } }, configurable: true }); });
  await page.click('#log-panel > summary');
  await page.click('#btn-copy-log');
  assertEqual(await text(page, 'btn-copy-log'), 'Copied');
  assertMatch(await page.evaluate(() => window.__copied), /Hash of data verified/);
  noErrors(h);
  await h.close();
});

await suite.step('while installing: closing the tab is guarded; Disconnect is available before', async () => {
  const h = await open(SYNTH_URL, { chip: { commandDelayMs: 20 } });
  const { page } = h;
  await connect(page);
  await page.click('#btn-disconnect');
  assertEqual(await bodyState(page), 'idle');
  assertEqual((await chip(page)).portOpen, false, 'Disconnect closes the port');
  await connect(page);
  assertEqual(await page.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }), false, 'no guard while only connected');
  await page.click('#btn-install');
  await page.waitForFunction(() => /^\d+%$/.test(document.getElementById('phase-pct').textContent) && document.getElementById('phase-pct').textContent !== '0%', null, { timeout: 15000 });
  await page.evaluate(() => window.__fake.chip.stall());
  assertEqual(await page.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }), true, 'guard while installing');
  await page.evaluate(() => window.__fake.chip.resume());
  await untilState(page, 'done');
  assertEqual(await page.evaluate(() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }), false, 'guard removed afterwards');
  noErrors(h);
  await h.close();
});

/* ================================================================== 4. failures, explained */
await suite.step('closed pop-up / empty list: neutral message with the cable tips, "show all ports" works', async () => {
  const h = await open(SYNTH_URL, { port: { chooser: 'cancel' } });
  const { page } = h;
  await page.click('#btn-connect');
  await untilState(page, 'error');
  let c = await card(page);
  assertEqual(c.title, 'No port was chosen');
  assertEqual([c.neutral, c.showAll], [true, true]);
  assertMatch(c.steps.join(' '), /USB JTAG\/serial debug unit/);
  assertMatch(c.steps.join(' '), /only charge/);
  assertEqual(await stepStates(page), ['active', 'error', 'todo', 'todo']);
  assertEqual(await page.evaluate(() => document.activeElement.id), 'error-card', 'focus moves to the message (screen readers)');
  await page.click('#btn-error-showall');
  await untilState(page, 'error');
  const calls = (await chip(page)).requests;
  assertEqual(calls.length, 2);
  assertEqual(calls[1], {}, 'show all ports: no filter');
  await page.click('#btn-showall');                     /* the link in the troubleshooting box does the same */
  await untilState(page, 'error');
  assertEqual((await chip(page)).requests.length, 3);
  noErrors(h);
  await h.close();
});

await suite.step('the flashlight does not answer: download-mode steps; holding the button then "Try again" works', async () => {
  const h = await open(SYNTH_URL, { chip: { autoResetBroken: true } });
  const { page } = h;
  await page.click('#btn-connect');
  await untilState(page, 'error', 40000);
  let c = await card(page);
  assertEqual(c.title, 'The flashlight did not answer');
  assertEqual(c.neutral, false);
  assertEqual(c.steps.length, 5);
  assertMatch(c.steps[1], /hold/);
  assertMatch(c.steps[2], /plug the USB cable in/);
  assertMatch(c.tech, /^ESPError: Failed to connect with the device/, 'error class names survive minifying (keepNames)');
  assertEqual((await chip(page)).portOpen, false, 'the port was released');
  assertEqual(await stepStates(page), ['active', 'error', 'todo', 'todo']);
  assert(await disabled(page, 'btn-install'));
  await page.evaluate(() => window.__fake.chip.holdButton(true));     /* the person: unplug, hold button, plug in, let go */
  await page.click('#btn-retry');
  await untilState(page, 'connected');
  assert(await hidden(page, 'error-card'), 'message gone');
  await page.click('#btn-install');
  await untilState(page, 'done');
  assertEqual(await flashSha(page, synthImage.length), sha256(synthImage));
  noErrors(h);
  await h.close();
});

await suite.step('a chip that is not the flashlight\'s is refused before anything is written', async () => {
  const h = await open(SYNTH_URL, { chip: { chipId: 9 } });
  const { page } = h;
  await page.click('#btn-connect');
  await untilState(page, 'error');
  const c = await card(page);
  assertEqual(c.title, 'This is not an Aurora++ flashlight');
  assertMatch(c.message, /ESP32-S3/);
  assertEqual((await chip(page)).writes.length, 0);
  assert(await disabled(page, 'btn-install'));
  noErrors(h);
  await h.close();
});

await suite.step('the port is busy: explained', async () => {
  const h = await open(SYNTH_URL, { port: { openFails: 'busy' } });
  const { page } = h;
  await page.click('#btn-connect');
  await untilState(page, 'error');
  const c = await card(page);
  assertEqual(c.title, 'The computer could not open the port');
  assertMatch(c.message, /Another program or browser tab/);
  noErrors(h);
  await h.close();
});

await suite.step('verification fails: no "done", step 3 shows the problem, Try again reconnects', async () => {
  const h = await open(SYNTH_URL, { chip: { md5Mismatch: true } });
  const { page } = h;
  await connect(page);
  await page.click('#btn-install');
  await untilState(page, 'error');
  const c = await card(page);
  assertEqual(c.title, 'The check after writing failed');
  assertMatch(c.message, /may not start/);
  assertMatch(c.steps.join(' '), /factory reset/);
  assertEqual(await stepStates(page), ['active', 'active', 'error', 'todo']);
  assert(await hidden(page, 'done-actions'), 'no done buttons');
  assert(await disabled(page, 'btn-install'), 'Install must be preceded by Connect');
  assertEqual((await chip(page)).resets, ['download'], 'no restart after a failed verification');
  await page.click('#btn-retry');
  await untilState(page, 'connected');
  noErrors(h);
  await h.close();
});

await suite.step('cable pulled out in the middle of the install: explained at once', async () => {
  const h = await open(SYNTH_URL, { chip: { commandDelayMs: 40 } });
  const { page } = h;
  await connect(page);
  await page.click('#btn-install');
  await page.waitForFunction(() => /^[1-9]\d?%$/.test(document.getElementById('phase-pct').textContent), null, { timeout: 15000 });
  const t0 = Date.now();
  await page.evaluate(() => window.__fake.chip.pullCable());
  await untilState(page, 'error', 5000);
  assert(Date.now() - t0 < 3000, 'reported quickly, not after esptool time-outs');
  const c = await card(page);
  assertEqual(c.title, 'The connection was lost during the install');
  assertMatch(c.message, /not damaged/);
  assertEqual(await page.title(), 'Aurora++ firmware installer', 'tab title restored after the failure');
  assertEqual(await stepStates(page), ['active', 'active', 'error', 'todo']);
  /* plug in again, connect again, install again */
  await page.evaluate(() => window.__fake.chip.replug());
  await page.click('#btn-retry');
  await untilState(page, 'connected');
  await page.click('#btn-install');
  await untilState(page, 'done');
  assertEqual(await flashSha(page, synthImage.length), sha256(synthImage));
  noErrors(h);
  await h.close();
});

await suite.step('unplugged while connected: back to step 2 with a note, no scary message', async () => {
  const h = await open(SYNTH_URL);
  const { page } = h;
  await connect(page);
  await page.evaluate(() => window.__fake.chip.pullCable());
  await untilState(page, 'idle', 3000);
  assertMatch(await text(page, 'connect-status'), /The flashlight was unplugged\. Plug it in again and click Connect\./);
  assert(await hidden(page, 'error-card'), 'no error card');
  assert(await disabled(page, 'btn-install'));
  await page.evaluate(() => window.__fake.chip.replug());
  await connect(page);
  noErrors(h);
  await h.close();
});

/* ================================================================== 5. "Advanced": a different .bin file */
await suite.step('advanced file panel: wrong chip, too small, app-only image (needs a tick), back to the built-in firmware', async () => {
  const h = await open(SYNTH_URL);
  const { page } = h;
  await connect(page);
  assert(!(await page.evaluate(() => document.getElementById('advanced').open)), 'collapsed by default');
  await page.click('#advanced > summary');

  await uploadFile(page, 'other-chip.bin', makeImage({ size: 100 * 1024, chipId: 9 }));
  await page.waitForFunction(() => /other-chip\.bin/.test(document.getElementById('file-report').textContent));
  assertMatch(await text(page, 'file-report'), /This file cannot be installed/);
  assertMatch(await text(page, 'file-report'), /different chip \(chip id 9\)/);
  assert(await disabled(page, 'btn-install'), 'Install disabled for a wrong-chip file');
  assertMatch(await text(page, 'fw-check'), /different chip/);
  assert(!(await hidden(page, 'btn-use-embedded')), 'way back offered');

  await uploadFile(page, 'tiny.bin', new Uint8Array(100));
  await page.waitForFunction(() => /tiny\.bin/.test(document.getElementById('file-report').textContent));
  assertMatch(await text(page, 'file-report'), /only 100 bytes/);
  assert(await disabled(page, 'btn-install'));

  const appOnly = makeImage({ size: 120 * 1024, merged: false, seed: 9 });
  await uploadFile(page, 'app-only.bin', appOnly);
  await page.waitForFunction(() => /app-only\.bin/.test(document.getElementById('file-report').textContent));
  assertMatch(await text(page, 'file-report'), /does not look like a complete "merged" image/);
  assert(!(await hidden(page, 'file-ack-row')), 'acknowledgement offered');
  assert(await disabled(page, 'btn-install'), 'Install waits for the tick');
  await page.check('#file-ack');
  assert(!(await disabled(page, 'btn-install')), 'Install enabled after the tick');
  await page.uncheck('#file-ack');
  assert(await disabled(page, 'btn-install'));

  await page.click('#btn-use-embedded');
  assertMatch(await text(page, 'fw-name'), new RegExp(`Aurora\\+\\+ firmware v${SYNTH_VERSION}`));
  assertMatch(await text(page, 'fw-tag'), /included in this page/);
  assert(await hidden(page, 'file-report'), 'report gone');
  assertEqual(await page.evaluate(() => document.getElementById('file-input').value), '', 'file input cleared');
  assert(!(await disabled(page, 'btn-install')), 'Install enabled again');
  noErrors(h);
  await h.close();
});

/* ================================================================== 6. unsupported browsers */
{
  const UA = {
    firefox: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
    safari: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    iphone: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
    android: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'
  };
  await suite.step('no Web Serial: the reason is explained for Firefox, Safari, iPhone, Android and plain Chrome; Connect is disabled', async () => {
    const cases = [
      ['firefox', UA.firefox, /Firefox cannot install firmware\./, /does not let web pages talk to USB devices/],
      ['safari', UA.safari, /Safari cannot install firmware\./, /does not let web pages talk to USB devices/],
      ['iphone', UA.iphone, /iPhone and iPad cannot install firmware\./, /Apple's browsers/],
      ['android', UA.android, /Phones and tablets cannot install firmware\./, /open this page on a computer/i],
      ['plain', undefined, /This browser cannot install firmware\./, /"Web Serial"/]
    ];
    for (const [name, ua, title, reason] of cases) {
      const h = await open(SYNTH_URL, { absent: true, ua });
      const { page } = h;
      assert(!(await hidden(page, 'unsupported')), name + ': notice visible');
      assertMatch(await text(page, 'unsupported-title'), title, name);
      assertMatch(await text(page, 'unsupported-reason'), reason, name);
      assertMatch(await text(page, 'unsupported'), /Google Chrome/, name + ': names Chrome');
      assertMatch(await text(page, 'unsupported'), /Microsoft Edge/, name + ': names Edge');
      assert(await disabled(page, 'btn-connect'), name + ': Connect disabled');
      assert(await disabled(page, 'btn-install'), name + ': Install disabled');
      assertMatch(await text(page, 'fw-sha'), /^[0-9a-f]{64}$/, name + ': the page still shows what it would install');
      noErrors(h, name);
      await h.close();
    }
    const h = await open(SYNTH_URL, { absent: true, insecure: true });
    assertMatch(await text(h.page, 'unsupported-title'), /opened in an insecure way/);
    assertMatch(await text(h.page, 'unsupported-reason'), /https:\/\//);
    await h.close();
  });
}

/* ================================================================== 7. a damaged page */
await suite.step('damaged page (one changed byte in the firmware): refused, Install disabled', async () => {
  const h = await open(TAMPERED_URL);
  const { page } = h;
  assert(!(await hidden(page, 'damaged-banner')), 'banner visible');
  assertMatch(await text(page, 'damaged-banner'), /firmware inside this page is damaged/);
  assertMatch(await text(page, 'damaged-text'), /SHA-256 fingerprint does not match/);
  assertMatch(await text(page, 'fw-name'), /Not available/);
  assert(await disabled(page, 'btn-install'));
  await connect(page);
  assert(await disabled(page, 'btn-install'), 'even when connected');
  noErrors(h);
  await h.close();
});

/* ================================================================== 8. layout */
await suite.step('no horizontal scrolling and big touch targets at 320 / 360 / 390 / 1280 px (start, connected, done, problem)', async () => {
  for (const [w, hgt] of [[320, 640], [360, 740], [390, 844], [1280, 800]]) {
    const h = await open(SYNTH_URL, { width: w, height: hgt });
    const { page } = h;
    const check = async (label) => {
      const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, bw: document.body.scrollWidth,
        small: Array.from(document.querySelectorAll('button, a.btn, input[type=checkbox]')).filter((b) => b.getClientRects().length && !b.classList.contains('linkbtn')).map((b) => ({ id: b.id || b.textContent.trim().slice(0, 20), h: Math.round(b.getBoundingClientRect().height), w: Math.round(b.getBoundingClientRect().width) })).filter((b) => b.h < 40 && b.id !== 'file-ack' && b.id !== 'chk-erase') }));
      assert(m.sw <= m.iw && m.bw <= m.iw, `${w}px ${label}: horizontal scroll (scrollWidth ${m.sw}, window ${m.iw})`);
      assertEqual(m.small, [], `${w}px ${label}: touch targets under 40 px`);
    };
    await check('start');
    await page.click('#advanced > summary'); await page.click('#log-panel > summary');
    await uploadFile(page, 'a-rather-long-file-name-for-a-firmware-image-v1.2.3-merged-final.bin', makeImage({ size: 120 * 1024, merged: false }));
    await page.waitForFunction(() => !document.getElementById('file-report').hidden);
    await check('advanced + log open, long file name');
    await page.click('#btn-use-embedded');
    await connect(page); await check('connected');
    await page.click('#btn-install'); await untilState(page, 'done'); await check('done');
    await page.evaluate(() => window.__fake.chip.options.md5Mismatch = true);
    await page.click('#btn-again'); await connect(page); await page.click('#btn-install'); await untilState(page, 'error'); await check('problem');
    noErrors(h, `${w}px`);
    await h.close();
  }
});

/* ================================================================== 9. menu page */
{
  const h = await newPage(browser, INDEX_URL, { width: 390, height: 844 });
  const { page } = h;
  await suite.step('loads without errors, links to the control app and the installer', async () => {
    assertEqual(await page.title(), 'Aurora++ flashlight');
    assertEqual(await page.getAttribute('#link-app', 'href'), 'aurora-app.html');
    assertEqual(await page.getAttribute('#link-flasher', 'href'), 'aurora-flasher.html');
    assertMatch(await page.locator('#link-app').textContent(), /Demo mode/);
    assertMatch(await page.locator('#link-flasher').textContent(), /Phones cannot do this/);
    noErrors(h);
  });
  await suite.step('the links open the pages (no console errors on arrival)', async () => {
    await page.click('#link-app');
    await page.waitForURL(/aurora-app\.html/);
    assertEqual(await page.title(), 'Aurora++ flashlight control');
    await page.goBack();
    await page.click('#link-flasher');
    await page.waitForURL(/aurora-flasher\.html/);
    assertEqual(await page.title(), 'Aurora++ firmware installer');
    noErrors(h);
  });
  await h.close();
  await suite.step('no horizontal scrolling at 320 / 390 / 1280 px', async () => {
    for (const w of [320, 390, 1280]) {
      const hh = await newPage(browser, INDEX_URL, { width: w, height: 800 });
      const m = await hh.page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, hs: Array.from(document.querySelectorAll('a.card')).map((a) => a.getBoundingClientRect().height) }));
      assert(m.sw <= m.iw, `${w}px: horizontal scroll`);
      assert(m.hs.every((x) => x >= 48), `${w}px: link cards at least 48 px high`);
      noErrors(hh); await hh.close();
    }
  });
}

/* ================================================================== 10. the flashers' link to the app, and the app's link to the flasher */
await suite.step('the installer and the control app link to each other', async () => {
  const h = await newPage(browser, FLASHER_URL, { width: 1280, height: 800 });
  assertEqual(await h.page.locator('footer a').first().getAttribute('href'), 'aurora-app.html');
  await h.close();
  const a = await newPage(browser, APP_URL, { width: 1280, height: 800 });
  assertEqual(await a.page.locator('a[href="aurora-flasher.html"]').count() > 0, true);
  await a.close();
});

/* ================================================================== 11. real page + real firmware */
await suite.step('the real page (app/aurora-flasher.html) installs the real firmware byte for byte', async () => {
  if (realPageIsPlaceholder) { suite.note('skipped: no firmware file exists yet, the real page is a placeholder build'); return; }
  const h = await open(FLASHER_URL);
  const { page } = h;
  assertMatch(await text(page, 'fw-sha'), new RegExp(sha256(realFirmware)));
  assertMatch(await text(page, 'fw-check'), /complete image for an ESP32-C3/);
  assertMatch(await text(page, 'fw-name'), /Aurora\+\+ firmware v\d+\.\d+\.\d+/);
  await connect(page);
  await page.click('#btn-install');
  await untilState(page, 'done');
  assertEqual(await flashSha(page, realFirmware.length), sha256(realFirmware), 'flash content = firmware/dist image');
  noErrors(h);
  await h.close();
});

/* ================================================================== 12. screenshots */
if (!NO_SHOTS) {
  const shots = [];
  const real = realPageIsPlaceholder ? SYNTH_URL : FLASHER_URL;
  async function flow(width, height, dark) {
    const phone = width < 600;
    const name = (s) => `flasher-${dark ? 'dark-' : ''}${s}-${width}.png`;
    const h = await open(real, { width, height, dark, chip: { commandDelayMs: 25 } });
    const { page } = h;
    await top(page);
    shots.push(await shot(page, name('start')));
    if (!dark && phone) shots.push(await shot(page, `flasher-start-${width}-full.png`, { full: true }));
    if (!dark) {
      await to(page, 'step-2');
      await page.click('#btn-connect');
      await untilState(page, 'connected');
      await page.waitForTimeout(150);   /* the page scrolled to the Install step by itself: that is the view a person gets */
      shots.push(await shot(page, name('connected')));
    } else {
      await connect(page);
    }
    await page.click('#btn-install');
    await page.waitForFunction(() => /^[3-6]\d%$/.test(document.getElementById('phase-pct').textContent), null, { timeout: 20000 });
    await page.evaluate(() => window.__fake.chip.stall());
    await page.waitForTimeout(120);
    await to(page, 'step-3');
    shots.push(await shot(page, name('installing')));
    await page.evaluate(() => window.__fake.chip.resume());
    await untilState(page, 'done');
    await page.waitForTimeout(150);
    await to(page, 'step-3');
    shots.push(await shot(page, name('done')));
    noErrors(h, `screenshot session ${width} ${dark ? 'dark' : 'light'}`);
    await h.close();
  }
  await suite.step('screenshots 390x844 (light and dark)', async () => { await flow(390, 844, false); await flow(390, 844, true); });
  await suite.step('screenshots 1280x800 (light and dark)', async () => { await flow(1280, 800, false); await flow(1280, 800, true); });

  await suite.step('screenshots of the problem, unsupported-browser, placeholder and advanced states', async () => {
    for (const [width, height] of [[390, 844], [1280, 800]]) {
      const phone = width < 600;
      /* the flashlight does not answer */
      let h = await open(real, { width, height, chip: { autoResetBroken: true } });
      await h.page.click('#btn-connect');
      await untilState(h.page, 'error', 40000);
      await h.page.waitForTimeout(150);
      await to(h.page, 'error-card');
      shots.push(await shot(h.page, `flasher-error-${width}.png`));
      noErrors(h, 'error screenshot'); await h.close();
      /* no Web Serial (Firefox) */
      h = await open(real, { width, height, absent: true, ua: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0' });
      await top(h.page);
      shots.push(await shot(h.page, `flasher-unsupported-${width}.png`));
      noErrors(h, 'unsupported screenshot'); await h.close();
      /* placeholder build */
      h = await open(PLACEHOLDER_URL, { width, height });
      await top(h.page);
      shots.push(await shot(h.page, `flasher-placeholder-${width}.png`));
      noErrors(h, 'placeholder screenshot'); await h.close();
      /* advanced: a file that needs a tick */
      h = await open(real, { width, height });
      await h.page.click('#advanced > summary');
      await uploadFile(h.page, 'my-test-build.bin', makeImage({ size: 180 * 1024, merged: false, seed: 5 }));
      await h.page.waitForFunction(() => !document.getElementById('file-report').hidden);
      await to(h.page, 'advanced');
      shots.push(await shot(h.page, `flasher-advanced-${width}.png`));
      noErrors(h, 'advanced screenshot'); await h.close();
      /* the menu page */
      h = await newPage(browser, INDEX_URL, { width, height });
      shots.push(await shot(h.page, `index-${width}.png`));
      noErrors(h, 'menu screenshot'); await h.close();
      void phone;
    }
  });
  suite.note(`${shots.length} screenshots written to app/screenshots/`);
}

await browser.close();
process.exit(suite.summary() ? 0 : 1);
