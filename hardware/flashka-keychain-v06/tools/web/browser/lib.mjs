// SPDX-License-Identifier: MIT OR Apache-2.0
// Shared helpers for the headless browser tests (Playwright + Chromium).
// - finds Playwright (local node_modules first, then a global install)
// - a tiny sequential test runner with readable output and a non-zero exit code on failure
// - page factory with console-error collection, optional fake clock, fake navigator.bluetooth / navigator.serial
import { createRequire } from 'node:module';
import { execSync, spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const WEB_DIR = path.resolve(HERE, '..');
export const APP_DIR = path.resolve(WEB_DIR, '../../app');
export const SHOT_DIR = path.join(APP_DIR, 'screenshots');
export const APP_URL = pathToFileURL(path.join(APP_DIR, 'flashka-app.html')).href;
export const FLASHER_URL = pathToFileURL(path.join(APP_DIR, 'flashka-flasher.html')).href;
export const INDEX_URL = pathToFileURL(path.join(APP_DIR, 'index.html')).href;

/** Loads Playwright: the copy in tools/web/node_modules, else a global one (npm root -g). */
export function loadPlaywright() {
  const require = createRequire(import.meta.url);
  try { return require('playwright'); } catch { /* fall through */ }
  try {
    const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
    return createRequire(path.join(root, 'noop.js'))('playwright');
  } catch { /* fall through */ }
  throw new Error('Playwright not found. Run "npm install" in tools/web (the browsers are preinstalled; do not run "playwright install").');
}

export async function launch() {
  const { chromium } = loadPlaywright();
  return chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
}

/* ------------------------------------------------------------------ test runner */
export function createSuite(title) {
  const results = [];
  let current = null;
  const out = (s) => process.stdout.write(s + '\n');
  out(`\n=== ${title} ===`);
  return {
    results,
    /** Runs one named step. Failures are recorded and the suite continues. */
    async step(name, fn) {
      current = name;
      const t0 = Date.now();
      try {
        await fn();
        results.push({ name, ok: true });
        out(`  ok   ${name} (${Date.now() - t0} ms)`);
      } catch (e) {
        results.push({ name, ok: false, error: e });
        out(`  FAIL ${name}\n       ${String(e && e.stack ? e.stack : e).split('\n').slice(0, 6).join('\n       ')}`);
      }
    },
    note(text) { out(`       ${text}`); },
    summary() {
      const failed = results.filter((r) => !r.ok);
      out(`\n${title}: ${results.length - failed.length} passed, ${failed.length} failed`);
      return failed.length === 0;
    }
  };
}

export function assert(cond, message) { if (!cond) throw new Error(message || 'assertion failed'); }
export function assertEqual(actual, expected, message) {
  const a = JSON.stringify(actual), b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${message || 'values differ'}\n         expected: ${b}\n         actual:   ${a}`);
}
export function assertMatch(text, re, message) {
  if (!re.test(String(text))) throw new Error(`${message || 'text does not match'}\n         pattern: ${re}\n         text:    ${JSON.stringify(String(text))}`);
}

/* ------------------------------------------------------------------ pages */
/**
 * Opens a fresh page.
 * opts: width, height, dark, dpr, userAgent, reducedMotion ('reduce' = instant scrolling, no animations), clock (install a fake clock before load),
 *       bluetooth (inject the fake navigator.bluetooth), serial (inject the fake navigator.serial, file given),
 *       init: extra init-script source strings
 * Returns { page, context, errors, warnings, close() }.
 */
export async function newPage(browser, url, opts = {}) {
  const context = await browser.newContext({
    viewport: { width: opts.width || 390, height: opts.height || 844 },
    deviceScaleFactor: opts.dpr || 1,
    colorScheme: opts.dark ? 'dark' : 'light',
    userAgent: opts.userAgent,
    isMobile: opts.isMobile || false,
    hasTouch: opts.hasTouch || false,
    reducedMotion: opts.reducedMotion || 'no-preference'
  });
  const page = await context.newPage();
  const errors = [], warnings = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push('console.error: ' + msg.text());
    else if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (e) => errors.push('pageerror: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e)));
  page.on('requestfailed', (r) => errors.push('requestfailed: ' + r.url().slice(0, 120) + ' ' + (r.failure() && r.failure().errorText)));
  if (opts.clock) await page.clock.install();
  if (opts.bluetooth) await page.addInitScript({ path: path.join(HERE, 'fake-bluetooth.js') });
  for (const p of opts.initFiles || []) await page.addInitScript({ path: p });
  for (const src of opts.init || []) await page.addInitScript({ content: src });
  if (url) await page.goto(url, { waitUntil: 'load' });
  return { page, context, errors, warnings, async close() { await context.close(); } };
}

export async function shot(page, name, opts = {}) {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const file = path.join(SHOT_DIR, name);
  await page.screenshot({ path: file, fullPage: !!opts.full, animations: 'disabled', caret: 'hide' });
  return file;
}

/** Waits until fn (run in the page) returns a truthy value. */
export async function until(page, fn, arg, timeout = 8000) {
  await page.waitForFunction(fn, arg, { timeout, polling: 50 });
}
export async function text(page, id) { return (await page.locator('#' + id).textContent()) || ''; }
export async function isHidden(page, id) { return page.evaluate((i) => document.getElementById(i).hidden, id); }
export async function toastTexts(page) { return page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast')).map((t) => t.textContent)); }
export async function untilText(page, id, re, timeout = 8000) {
  await page.waitForFunction(([i, src, flags]) => new RegExp(src, flags).test(document.getElementById(i).textContent), [id, re.source, re.flags], { timeout, polling: 50 })
    .catch(async (e) => { throw new Error(`#${id} never matched ${re}; it says ${JSON.stringify(await text(page, id))}`); });
}
export async function untilToast(page, re, timeout = 8000) {
  await page.waitForFunction(([src, flags]) => Array.from(document.querySelectorAll('#toasts .toast')).some((t) => new RegExp(src, flags).test(t.textContent)), [re.source, re.flags], { timeout, polling: 50 })
    .catch(async () => { throw new Error(`no toast matched ${re}; toasts: ${JSON.stringify(await toastTexts(page))}`); });
}
/** Advances a fake clock in small steps so that promise chains between timers can run. */
export async function advance(page, ms, step = 250) {
  let left = ms;
  while (left > 0) { const d = Math.min(step, left); await page.clock.runFor(d); left -= d; }
}
export function noErrors(handle, label) {
  if (handle.errors.length) throw new Error(`${label || 'page'} logged ${handle.errors.length} error(s):\n         ` + handle.errors.join('\n         '));
}

/* ------------------------------------------------------------------ pretend serial hardware */
let fakeSerialBundle = null;
/**
 * Init-script sources that put the pretend ESP32-C3 (test/helpers/fake-esp32c3.mjs) behind navigator.serial.
 * options: { chip: {...}, port: {...}, absent: true }  - see browser/fake-serial-entry.mjs.
 * Use: newPage(browser, url, { init: await fakeSerialInit({ chip: { silent: true } }) })
 */
export async function fakeSerialInit(options = {}) {
  if (!fakeSerialBundle) {
    const esbuild = await import('esbuild');
    const r = await esbuild.build({
      entryPoints: [path.join(HERE, 'fake-serial-entry.mjs')], bundle: true, write: false, format: 'iife', platform: 'browser', target: 'es2020', logLevel: 'warning'
    });
    fakeSerialBundle = r.outputFiles[0].text;
  }
  return ['window.__FAKE_SERIAL_OPTIONS__ = ' + JSON.stringify(options) + ';', fakeSerialBundle];
}

/** Where the tests put the pages they build (git-ignored). */
export const OUT_DIR = path.join(WEB_DIR, '.test-output');

/** Runs tools/web/build_flasher.mjs with the given arguments. Returns { code, stdout, stderr }. */
export function buildFlasher(args) {
  const r = spawnSync(process.execPath, [path.join(WEB_DIR, 'build_flasher.mjs'), ...args], { encoding: 'utf8' });
  return { code: r.status, stdout: r.stdout, stderr: r.stderr };
}
