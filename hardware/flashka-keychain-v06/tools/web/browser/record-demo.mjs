// SPDX-License-Identifier: MIT OR Apache-2.0
// Demo recordings of the FlashKa control app (app/flashka-app.html, built-in demo mode) and the web app
// showcase picture, for the project page.  Real clicks and a real slider drag with Playwright + Chromium;
// every frame is a screenshot; ffmpeg joins them into GIFs (palettegen + paletteuse, exact delays).
//
// Rebuild everything with one command (from tools/web/):
//
//     node browser/record-demo.mjs
//
// Writes (paths relative to the v0.6 folder):
//   assets/v06/webapp_demo.gif           phone layout: 390 x 844 CSS px at device scale 2, scaled to 360 px wide
//   assets/v06/webapp_demo_desktop.gif   desktop layout: 1280 x 800, scaled to 900 px wide
//   assets/v06/webapp_showcase.png       three phone screens side by side, 1800 px wide: app/screenshots/
//                                        app-light-controls-390.png, app-dark-presenter-390.png and the
//                                        firmware installer start page (captured here at device scale 2)
// Options: --only phone,desktop,showcase   --tmp DIR (frame folder, default: a new temporary folder)
//          --keep (keep the frame folder)   --out-dir DIR (write the outputs there instead, for previews)
// Needs node 22, Playwright in tools/web/node_modules (Chromium preinstalled; never run "playwright install")
// and ffmpeg.  The demo needs no hardware: the app simulates a FlashKa inside the page.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { launch, newPage, until, untilText, APP_URL, FLASHER_URL, APP_DIR, fakeSerialInit } from './lib.mjs';

const V6 = path.resolve(APP_DIR, '..');
const SHOT_DIR = path.join(APP_DIR, 'screenshots');
const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf('--' + name); return i >= 0 && argv[i + 1] ? argv[i + 1] : def; };
const ONLY = opt('only', 'phone,desktop,showcase').split(',').map((s) => s.trim());
const KEEP = argv.includes('--keep');
const OUT_DIR = path.resolve(opt('out-dir', path.join(V6, 'assets', 'v06')));
const TMP_GIVEN = !!opt('tmp', '');
const TMP = path.resolve(opt('tmp', '') || fs.mkdtempSync(path.join(os.tmpdir(), 'flashka-rec-')));
const log = (s) => process.stdout.write(s + '\n');

/* ------------------------------------------------------------------ overlay: tap mark and mouse pointer */
// Injected into the page (fixed position, pointer-events none, so the real clicks pass through).
function installOverlay() {
  if (document.getElementById('__rec_tap')) return;
  const st = document.createElement('style');
  st.textContent =
    '#__rec_tap{position:fixed;left:0;top:0;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;' +
    'background:rgba(17,24,39,.22);border:2.5px solid rgba(255,255,255,.95);box-shadow:0 0 0 1.5px rgba(17,24,39,.4),0 2px 8px rgba(0,0,0,.25);' +
    'pointer-events:none;z-index:2147483646;display:none}' +
    '#__rec_tap.up{width:62px;height:62px;margin:-31px 0 0 -31px;background:rgba(17,24,39,.07);border-color:rgba(255,255,255,.65);box-shadow:0 0 0 1.5px rgba(17,24,39,.2)}' +
    '#__rec_tap.small{width:30px;height:30px;margin:-15px 0 0 -15px}#__rec_tap.small.up{width:44px;height:44px;margin:-22px 0 0 -22px}' +
    '#__rec_cur{position:fixed;left:0;top:0;width:26px;height:38px;margin:-2px 0 0 -2px;pointer-events:none;z-index:2147483647;display:none;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))}';
  document.head.appendChild(st);
  const tap = document.createElement('div');
  tap.id = '__rec_tap';
  document.body.appendChild(tap);
  const cur = document.createElement('div');
  cur.id = '__rec_cur';
  cur.innerHTML = '<svg width="26" height="38" viewBox="0 0 26 38" xmlns="http://www.w3.org/2000/svg"><path d="M2 2 L2 30 L8.8 23.6 L13.4 34.4 L18.4 32.3 L13.8 21.7 L23 21.4 Z" fill="#fff" stroke="#111827" stroke-width="2" stroke-linejoin="round"/></svg>';
  document.body.appendChild(cur);
}
const setTap = (page, x, y, mode, small) => page.evaluate(([xx, yy, m, s]) => {
  const t = document.getElementById('__rec_tap');
  t.className = (m === 'up' ? 'up' : '') + (s ? ' small' : '');
  t.style.display = m === 'hide' ? 'none' : 'block';
  t.style.left = xx + 'px'; t.style.top = yy + 'px';
}, [x, y, mode, !!small]);
const setCursor = (page, x, y) => page.evaluate(([xx, yy]) => {
  const c = document.getElementById('__rec_cur');
  c.style.display = 'block'; c.style.left = xx + 'px'; c.style.top = yy + 'px';
}, [x, y]);

/* ------------------------------------------------------------------ recorder */
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

class Rec {
  /** desktop: draw a mouse pointer that travels to every click; phone: tap marks only */
  constructor(page, dir, name, desktop) {
    this.page = page; this.dir = dir; this.name = name; this.desktop = desktop; this.frames = []; this.cur = null;
    fs.mkdirSync(dir, { recursive: true });
  }
  async shot(ms) {
    const file = path.join(this.dir, `${this.name}_${String(this.frames.length).padStart(4, '0')}.png`);
    await this.page.screenshot({ path: file, animations: 'disabled', caret: 'hide' });
    this.frames.push({ file, ms: Math.max(20, Math.round(ms / 10) * 10) });
  }
  async moveTo(x, y, ms = 420, n = 6) {
    if (!this.desktop) return;
    const [x0, y0] = this.cur || [x, y];
    for (let i = 1; i <= n; i++) {
      const t = easeInOut(i / n);
      const cx = x0 + (x - x0) * t, cy = y0 + (y - y0) * t;
      await this.page.mouse.move(cx, cy);
      await setCursor(this.page, cx, cy);
      await this.shot(ms / n);
    }
    this.cur = [x, y];
  }
  /** smooth scroll of the page to y (CSS px), n frames */
  async scrollTo(y, ms = 480, n = 6) {
    const p = this.page;
    const [from, max] = await p.evaluate(() => [window.scrollY, document.documentElement.scrollHeight - window.innerHeight]);
    const to = Math.max(0, Math.min(max, Math.round(y)));
    if (Math.abs(to - from) < 2) return;
    for (let i = 1; i <= n; i++) {
      await p.evaluate((yy) => window.scrollTo({ top: yy, behavior: 'instant' }), Math.round(from + (to - from) * easeInOut(i / n)));
      await this.shot(ms / n);
    }
  }
  /** scroll so that the element starts `gap` px under the sticky header */
  async scrollToEl(sel, gap = 12, ms, n) {
    const y = await this.page.evaluate((s) => {
      const e = document.querySelector(s), h = document.querySelector('.top');
      return e.getBoundingClientRect().top + window.scrollY - (h ? h.getBoundingClientRect().height : 0);
    }, sel);
    await this.scrollTo(y - gap, ms, n);
  }
  /** a real click in the middle of `sel`: tap mark (and pointer on desktop), wait for the result, hold.
   *  up: false skips the "finger lifted" frame (used when `wait` scrolls the page away from the button). */
  async click(sel, { wait, hold = 1000, up = true } = {}) {
    const p = this.page;
    const box = await p.locator(sel).first().boundingBox();
    if (!box) throw new Error('not visible: ' + sel);
    const x = Math.round(box.x + box.width / 2), y = Math.round(box.y + box.height / 2);
    const hit = await p.evaluate(([s, xx, yy]) => { const e = document.elementFromPoint(xx, yy); return !!(e && e.closest(s)); }, [sel, x, y]);
    if (!hit) throw new Error(`${sel} is covered at ${x}, ${y}`);
    await this.moveTo(x, y);
    await setTap(p, x, y, 'down', this.desktop);
    await this.shot(this.desktop ? 200 : 320);
    await p.mouse.click(x, y);
    if (wait) await wait();
    if (!this.desktop) await p.mouse.move(2, 2);          // no hover left behind on a touch screen
    if (up) {
      await setTap(p, x, y, 'up', this.desktop);
      await this.shot(150);
    }
    await setTap(p, x, y, 'hide');
    if (hold > 0) await this.shot(hold);
  }
  /** drag the fine-brightness slider thumb through the given positions (0..1000) with the mouse.
   *  The hint text above the slider can grow while dragging, so the slider's box is read again at every
   *  step and the finger mark / pointer follow the thumb. */
  async drag(sel, positions, thumb = 30) {
    const p = this.page;
    const geo = async () => {
      const b = await p.locator(sel).boundingBox();
      return { xOf: (pos) => b.x + thumb / 2 + (pos / 1000) * (b.width - thumb), y: Math.round(b.y + b.height / 2) };
    };
    let g = await geo();
    let pos = Number(await p.inputValue(sel));
    let x = g.xOf(pos), y = g.y;
    await this.moveTo(x, y);
    await p.mouse.move(x, y);
    await setTap(p, x, y, 'down', this.desktop);
    await this.shot(260);
    await p.mouse.down();
    for (const target of positions) {
      const p0 = pos, n = 7;
      for (let i = 1; i <= n; i++) {
        pos = p0 + (target - p0) * easeInOut(i / n);
        g = await geo();
        x = g.xOf(pos); y = g.y;
        await p.mouse.move(x, y);
        g = await geo();                                  // the layout may shift on the input event
        x = g.xOf(pos); y = g.y;
        await setTap(p, x, y, 'down', this.desktop);
        if (this.desktop) { await setCursor(p, x, y); this.cur = [x, y]; }
        await this.shot(80);
      }
    }
    await p.mouse.up();
    if (!this.desktop) await p.mouse.move(2, 2);
    await setTap(p, x, y, 'up', this.desktop);
    await this.shot(150);
    await setTap(p, x, y, 'hide');
  }
}

/* ------------------------------------------------------------------ the demo story (same for phone and desktop) */
const conn = (page, c) => until(page, (cc) => document.body.dataset.conn === cc, c, 8000);
const noToasts = (page) => until(page, () => document.querySelectorAll('#toasts .toast').length === 0, undefined, 9000);

async function story(page, rec, desktop) {
  await page.evaluate(installOverlay);
  if (desktop) { rec.cur = [1010, 470]; await setCursor(page, 1010, 470); await page.mouse.move(1010, 470); }
  await rec.shot(1700);                                                      // start screen
  await rec.click('#btn-demo', { hold: 1300, wait: async () => {
    await untilText(page, 'pill-text', /^Demo mode$/);
    await untilText(page, 'bat-pct', /^\d+$/);
    await untilText(page, 'foot-device', /fw 0\.6\.0/);
  } });
  if (!desktop) await rec.scrollToEl('#card-light');
  await rec.click('#btn-power', { hold: 1100, wait: () => untilText(page, 'light-chip', /^On/) });
  await rec.click('.lvl[data-level="3"]', { hold: 1000, wait: () => untilText(page, 'light-chip', /^On · High/) });
  await rec.drag('#slider', [690, 835]);                                     // fine brightness, live readout
  await untilText(page, 'level-note', /^Exact brightness from the slider/);
  await rec.shot(1100);
  if (!desktop) await rec.scrollToEl('#card-profile');
  await rec.click('.prof[data-profile="0"]', { hold: 1200, wait: () => untilText(page, 'st-prof', /^Extreme$/) });
  await rec.scrollToEl('#card-presenter', 12, desktop ? 560 : 600, 7);
  await rec.shot(1500);                                                      // the key map
  if (desktop) {
    await rec.click('#btn-presenter', { hold: 0, wait: () => conn(page, 'lost') });
    await rec.scrollTo(0, 460, 6);
  } else {
    // phone: cut straight to the top of the page after the tap.  (While the page scrolled up, the 390 px
    // layout showed the presenter card title wrapping next to the long "On · waiting for a computer" chip.)
    await rec.click('#btn-presenter', { hold: 0, up: false, wait: async () => {
      await conn(page, 'lost');
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    } });
  }
  await untilText(page, 'pill-text', /^Presenter mode$/);
  await rec.shot(2600);                                                      // "the light is now a Bluetooth keyboard"
  await rec.click('#demo-both2', { hold: 900, wait: () => page.waitForTimeout(150) });
  await rec.click('#btn-reconnect', { hold: 1300, wait: async () => { await conn(page, 'connected'); await page.waitForTimeout(200); } });
  await noToasts(page);                                                      // let the toasts expire (not recorded)
  await rec.click('#btn-exit-demo', { hold: 0, wait: () => until(page, () => !document.getElementById('view-start').hidden) });
  if (desktop) await rec.moveTo(1010, 470, 360, 5);                         // pointer back to where it started
  // the GIF loops to the first frame: the same start screen
}

async function record(browser, kind) {
  const desktop = kind === 'desktop';
  const dir = path.join(TMP, kind);
  fs.rmSync(dir, { recursive: true, force: true });
  // bluetooth: the test suite's fake navigator.bluetooth, so the start screen looks as in Chrome or Edge
  // (headless Chromium has no Web Bluetooth); the demo itself never uses it
  const h = await newPage(browser, APP_URL, desktop ? { width: 1280, height: 800, dpr: 1, reducedMotion: 'reduce', bluetooth: true }
    : { width: 390, height: 844, dpr: 2, reducedMotion: 'reduce', bluetooth: true });
  const rec = new Rec(h.page, dir, desktop ? 'dt' : 'ph', desktop);
  await story(h.page, rec, desktop);
  if (h.errors.length) throw new Error('page errors:\n' + h.errors.join('\n'));
  await h.close();
  return rec.frames;
}

/* ------------------------------------------------------------------ ffmpeg */
function ffmpeg(args) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', ...args], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('ffmpeg failed: ' + r.stderr);
}

function writeGif(frames, out, width, dither) {
  const list = path.join(TMP, path.basename(out, '.gif') + '.ffconcat');
  fs.writeFileSync(list, 'ffconcat version 1.0\n' + frames.map((f) =>
    `file '${f.file}'\noption framerate 100\nduration ${(f.ms / 1000).toFixed(2)}\n`).join(''));
  const vf = `scale=${width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];` +
             `[b][p]paletteuse=dither=${dither}:diff_mode=rectangle`;
  fs.mkdirSync(path.dirname(out), { recursive: true });
  ffmpeg(['-f', 'concat', '-safe', '0', '-i', list, '-vf', vf, '-fps_mode', 'vfr', '-loop', '0',
          '-final_delay', String(Math.round(frames[frames.length - 1].ms / 10)), out]);
  const total = frames.reduce((s, f) => s + f.ms, 0) / 1000;
  log(`wrote ${out}  (${frames.length} frames, ${(fs.statSync(out).size / 1e6).toFixed(2)} MB, loop ${total.toFixed(1)} s)`);
}

/* ------------------------------------------------------------------ showcase picture */
async function showcase(browser) {
  const dir = path.join(TMP, 'showcase');
  fs.mkdirSync(dir, { recursive: true });
  // the installer start page at device scale 2 (the test screenshots of the installer are device scale 1)
  const init = await fakeSerialInit({});
  const h = await newPage(browser, FLASHER_URL, { width: 390, height: 844, dpr: 2, reducedMotion: 'reduce', init });
  await h.page.waitForFunction(() => window.__flasher && document.getElementById('fw-name').textContent !== '-', null, { timeout: 8000 });
  await h.page.evaluate(() => window.scrollTo(0, 0));
  const flasher = path.join(dir, 'flasher-start-390@2x.png');
  await h.page.screenshot({ path: flasher, animations: 'disabled', caret: 'hide' });
  if (h.errors.length) throw new Error('installer page errors:\n' + h.errors.join('\n'));
  await h.close();
  const screens = [path.join(SHOT_DIR, 'app-light-controls-390.png'), path.join(SHOT_DIR, 'app-dark-presenter-390.png'), flasher];
  for (const s of screens) if (!fs.existsSync(s)) throw new Error('missing ' + s + ' (run "npm run test:browser" in tools/web)');
  const PW = 470;                                     // phone screen width in the picture, px
  const scaled = screens.map((s, i) => {               // Lanczos down-scaling outside the browser: sharp text
    const o = path.join(dir, `screen${i}.png`);
    ffmpeg(['-i', s, '-vf', `scale=${PW}:-1:flags=lanczos`, o]);
    return o;
  });
  const W = 1800, PH = Math.round(1688 * PW / 780), TOP = 74, CAP = 64, H = TOP + PH + CAP + 72;
  const gap = Math.round((W - 3 * PW) / 4);
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;padding:0}
    body{width:${W}px;height:${H}px;overflow:hidden;background:linear-gradient(180deg,#f3f5f8 0%,#e9edf2 100%);
         font-family:"TeX Gyre Heros","DejaVu Sans",sans-serif}
    .row{position:absolute;left:0;top:${TOP}px;width:${W}px;display:flex;justify-content:space-evenly}
    .ph{width:${PW}px;height:${PH}px;border-radius:44px;overflow:hidden;background:#fff;
        box-shadow:0 30px 70px rgba(25,35,50,.20),0 8px 22px rgba(25,35,50,.12),0 0 0 1px rgba(25,35,50,.10)}
    .ph img{display:block;width:${PW}px;height:${PH}px}
    .cap{position:absolute;left:0;top:${TOP + PH + CAP - 8}px;width:${W}px;text-align:center;font-size:27px;color:#4b5563;letter-spacing:.1px}
  </style></head><body>
    <div class="row">${scaled.map((s) => `<div class="ph"><img src="${pathToFileURL(s).href}"></div>`).join('')}</div>
    <div class="cap">FlashKa web app - control (Web Bluetooth) and firmware installer (Web Serial)</div>
  </body></html>`;
  const page = path.join(dir, 'showcase.html');
  fs.writeFileSync(page, html);
  const s = await newPage(browser, pathToFileURL(page).href, { width: W, height: H, dpr: 1 });
  await s.page.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  const out = path.join(OUT_DIR, 'webapp_showcase.png');
  fs.mkdirSync(OUT_DIR, { recursive: true });
  await s.page.screenshot({ path: out, clip: { x: 0, y: 0, width: W, height: H } });
  await s.close();
  log(`wrote ${out}  (${W} x ${H}, ${(fs.statSync(out).size / 1e6).toFixed(2)} MB; gap ${gap} px)`);
}

/* ------------------------------------------------------------------ main */
const browser = await launch();
try {
  if (ONLY.includes('phone')) {
    const frames = await record(browser, 'phone');
    writeGif(frames, path.join(OUT_DIR, 'webapp_demo.gif'), 360, 'bayer:bayer_scale=4');
  }
  if (ONLY.includes('desktop')) {
    const frames = await record(browser, 'desktop');
    writeGif(frames, path.join(OUT_DIR, 'webapp_demo_desktop.gif'), 900, 'bayer:bayer_scale=4');
  }
  if (ONLY.includes('showcase')) await showcase(browser);
} finally {
  await browser.close();
  if (!KEEP) {                 // remove only what this run made (a given --tmp folder itself stays)
    for (const d of ['phone', 'desktop', 'showcase']) fs.rmSync(path.join(TMP, d), { recursive: true, force: true });
    for (const f of ['webapp_demo.ffconcat', 'webapp_demo_desktop.ffconcat']) fs.rmSync(path.join(TMP, f), { force: true });
    if (!TMP_GIVEN) fs.rmSync(TMP, { recursive: true, force: true });
  }
}
