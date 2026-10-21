// SPDX-License-Identifier: MIT OR Apache-2.0
// Headless browser tests for the control app (app/flashka-app.html), Playwright + Chromium.
//
//   node browser/run-app-tests.mjs              run the checks
//   node browser/run-app-tests.mjs --no-shots   run the checks without writing screenshots
//
// 1. loads with no console errors; the "no Web Bluetooth" explanation
// 2. demo mode click-through: on/off, levels, turbo timer, slider, profiles, Custom editor, save, lockout,
//    identify, keep-alive, button priority, USB, thermal / battery badges, lost connection, reconnect
// 2b. presenter card in demo mode: settings, enter / leave, pairing, forgetting, v0.5 light
// 3. the real Bluetooth code path against a fake navigator.bluetooth (one GATT operation at a time,
//    error mapping, KEEPALIVE fallback, automatic reconnect)
// 3b. presenter mode over the fake Bluetooth link; a protocol 1 (v0.5) light without presenter features
// 4. no horizontal scrolling at 320 / 360 / 390 / 1280 px
// 5. screenshots at 390x844 and 1280x800 into app/screenshots/
import {
  launch, createSuite, newPage, shot, APP_URL, assert, assertEqual, assertMatch,
  until, untilText, untilToast, text, toastTexts, advance, noErrors
} from './lib.mjs';

const NO_SHOTS = process.argv.includes('--no-shots');
const suite = createSuite('Control app (app/flashka-app.html)');
const browser = await launch();

/* ------------------------------------------------------------------ small helpers */
const simState = (page) => page.evaluate(() => {
  const s = window.__flashka.sim.state();
  return { on: s.on, level: s.level, mem: s.mem, exactMa: s.exactMa, profileId: s.profileId, lockout: s.lockout, saved: s.saved,
           identifyCount: s.identifyCount, keepalive: s.keepalive, custom: s.custom, usb: s.usb, tempC: s.tempC, appLock: s.appLock };
});
const simStatus = (page) => page.evaluate(() => { const a = window.__flashka; return a.protocol.decodeStatus(a.sim.readStatus()); });
const simProfile = (page) => page.evaluate(() => { const a = window.__flashka; return a.protocol.decodeProfile(a.sim.readProfile()); });
const attr = (page, sel, name) => page.getAttribute(sel, name);
const visible = (page, sel) => page.locator(sel).isVisible();
const pressedLevels = (page) => page.$$eval('.lvl', (els) => els.map((e) => e.getAttribute('aria-pressed')));
const clearToasts = (page) => page.evaluate(() => { document.getElementById('toasts').textContent = ''; });
async function setSlider(page, pos, commit = true) {
  await page.evaluate(([p, c]) => {
    const s = document.getElementById('slider');
    s.value = String(p); s.dispatchEvent(new Event('input', { bubbles: true }));
    if (c) s.dispatchEvent(new Event('change', { bubbles: true }));
  }, [pos, commit]);
}
async function setRange(page, id, value) {
  await page.evaluate(([i, v]) => { const e = document.getElementById(i); e.value = String(v); e.dispatchEvent(new Event('input', { bubbles: true })); }, [id, value]);
}
const advance_real = (page, ms) => page.waitForTimeout(ms);
const noHorizontalScroll = (page) => page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth, bw: document.body.scrollWidth }));

/* ================================================================== 1. plain headless Chromium */
{
  const h = await newPage(browser, APP_URL);
  const { page } = h;
  await suite.step('loads with no console errors; start view is shown', async () => {
    assertEqual(await page.title(), 'FlashKa control');
    assert(await visible(page, '#view-start'), 'start view visible');
    assert(!(await visible(page, '#view-main')), 'main view hidden');
    assertEqual(await text(page, 'pill-text'), 'Not connected');
    assert(await visible(page, '#btn-demo'), 'demo button visible');
    assertMatch(await page.locator('a[href="flashka-flasher.html"]').textContent(), /firmware/i, 'link to the flasher');
    noErrors(h);
  });
  await suite.step('no Web Bluetooth: explains Chrome/Edge, Bluefy, Firefox/Safari; Connect is disabled', async () => {
    assert(await visible(page, '#support'), 'support notice visible');
    const t = await text(page, 'support');
    for (const word of ['Google Chrome', 'Microsoft Edge', 'Android', 'Windows', 'macOS', 'Linux', 'ChromeOS', 'iPhone and iPad', 'Bluefy', 'Firefox and Safari']) assertMatch(t, new RegExp(word), 'mentions ' + word);
    assert(await page.locator('#btn-connect').isDisabled(), 'Connect disabled');
    assert(await page.locator('#btn-demo').isEnabled(), 'demo enabled');
    assert(!(await visible(page, '#steps')), 'the how-to steps are hidden when Bluetooth is not possible');
    noErrors(h);
  });
  await h.close();
}
for (const [label, ua, re] of [
  ['iPhone', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1', /iPhone and iPad/],
  ['Firefox', 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0', /Firefox does not support/],
  ['desktop Safari', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15', /Safari does not support/]
]) {
  await suite.step(`the explanation names the cause for ${label}`, async () => {
    const h = await newPage(browser, APP_URL, { userAgent: ua });
    assertMatch(await text(h.page, 'support-reason'), re);
    noErrors(h); await h.close();
  });
}

/* ================================================================== 2. demo mode (fake clock installed, time keeps flowing) */
{
  const h = await newPage(browser, APP_URL, { clock: true });
  const { page } = h;

  await suite.step('demo: start screen -> demo flashlight (78 %, Balanced, off)', async () => {
    await page.click('#btn-demo');
    await until(page, () => !document.getElementById('view-main').hidden);
    await untilText(page, 'pill-text', /^Demo mode$/);
    assert(await visible(page, '#banner-demo'), 'demo banner');
    assert(!(await visible(page, '#view-start')), 'start view gone');
    await untilText(page, 'bat-pct', /^78$/);
    assertEqual(await text(page, 'bat-line'), 'Running on battery');
    assertMatch(await text(page, 'st-volt'), /^[34]\.\d\d V$/);
    assertMatch(await text(page, 'st-temp'), /^2[4-6]\.\d °C$/);
    assertEqual(await text(page, 'light-chip'), 'Off');
    assertEqual(await text(page, 'st-prof'), 'Balanced');
    assertEqual(await attr(page, '.prof[data-profile="1"]', 'aria-pressed'), 'true');
    assertEqual(await text(page, 'pdesc-1'), 'Moon 3 · Low 30 · Medium 200 · High 600 mA · Turbo 1200 mA for 60 s');
    assertEqual(await text(page, 'pdesc-2'), 'Moon 2 · Low 15 · Medium 100 · High 300 mA · no extra Turbo');
    await untilText(page, 'foot-device', /FlashKa-A7D4 · FlashKa fw 0\.6\.0/);
    noErrors(h);
  });

  await suite.step('demo: big On / Off button', async () => {
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On · Medium · 200 mA$/);
    assertEqual(await attr(page, '#btn-power', 'aria-pressed'), 'true');
    assertEqual(await text(page, 'power-text'), 'Turn off');
    assertEqual(await text(page, 'st-led'), '200 mA');
    assertMatch(await text(page, 'st-run'), /h|min/, 'runtime estimate shown while on');
    assertEqual((await simState(page)).on, true);
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^Off$/);
    assertEqual(await text(page, 'power-text'), 'Turn on');
    assertEqual(await text(page, 'st-led'), '0 mA');
    assertEqual(await text(page, 'st-run'), '–');
    assertEqual((await simState(page)).on, false);
  });

  await suite.step('demo: level buttons Moon / Low / Medium / High (also from "off": LEVEL then ON)', async () => {
    for (const [n, name, ma] of [[0, 'Moon', 3], [1, 'Low', 30], [2, 'Medium', 200], [3, 'High', 600]]) {
      await page.click(`.lvl[data-level="${n}"]`);
      await untilText(page, 'st-led', new RegExp(`^${ma} mA$`));
      await untilText(page, 'light-chip', new RegExp(`^On · ${name} · ${ma} mA$`));
      const want = ['false', 'false', 'false', 'false', 'false']; want[n] = 'true';
      assertEqual(await pressedLevels(page), want, name + ' pressed');
      assertEqual((await simState(page)).level, n);
    }
    assertEqual((await simStatus(page)).source, 2, 'last change made by the app');
    await untilText(page, 'source-line', /this app/);
  });

  await suite.step('demo: Off -> Turbo in one tap; countdown, orange timer bar, automatic step-down to 600 mA', async () => {
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^Off$/);
    await page.click('.lvl[data-level="4"]');            // the demo, like the firmware, switches on at the remembered level first
    await until(page, () => !document.getElementById('turbo-line').hidden, undefined, 8000);
    await untilText(page, 'st-led', /^1200 mA$/);
    assertEqual((await simStatus(page)).level, 4);
    assertMatch(await text(page, 'turbo-text'), /^Turbo - [01]:\d\d left, then the light steps down to 600 mA$/);
    assertMatch(await text(page, 'badges'), /Turbo boost running/);
    assertMatch(await text(page, 'st-turbo'), /^[01]:\d\d$/);
    await advance(page, 30000);
    const mid = await text(page, 'st-turbo');
    assertMatch(mid, /^0:(2[5-9]|3[0-5])$/, 'about half of the 60 s are left: ' + mid);
    const w = parseFloat(await page.$eval('#turbo-fill', (e) => e.style.width));
    assert(w > 35 && w < 65, 'timer bar about half full: ' + w);
    await advance(page, 31500);
    await until(page, () => document.getElementById('turbo-line').hidden);
    await untilText(page, 'st-led', /^600 mA$/);
    assertEqual(await text(page, 'st-turbo'), '–');
    assert(!/Turbo boost running/.test(await text(page, 'badges')), 'turbo badge gone');
    await untilText(page, 'source-line', /the flashlight itself/);
    assertEqual((await simStatus(page)).turbo, false);
  });

  await suite.step('demo: fine-brightness slider writes the exact current (logarithmic), clearing the level highlight', async () => {
    const want = await page.evaluate(() => window.__flashka.protocol.sliderToMa(800, 1200));
    await setSlider(page, 800);
    await untilText(page, 'slider-out', new RegExp(`^${want} mA$`));
    await until(page, (ma) => window.__flashka.sim.state().exactMa === ma, want);
    await untilText(page, 'st-led', new RegExp(`^${want} mA$`));
    assertMatch(await text(page, 'level-note'), /^Exact brightness from the slider/);
    assertEqual(await pressedLevels(page), ['false', 'false', 'false', 'false', 'false']);
    assertEqual((await simStatus(page)).level, 0xFF);
  });

  await suite.step('demo: the slider is throttled to about 5 writes per second', async () => {
    await page.evaluate(() => {
      const sim = window.__flashka.sim, orig = sim.writeCommand; window.__outWrites = [];
      sim.writeCommand = function (b) { if (b[0] === 5) window.__outWrites.push(performance.now()); return orig.call(sim, b); };
    });
    await page.evaluate(async () => {
      const s = document.getElementById('slider');
      for (let i = 0; i < 30; i++) { s.value = String(300 + i * 15); s.dispatchEvent(new Event('input', { bubbles: true })); await new Promise((r) => setTimeout(r, 50)); }
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(700);
    const w = await page.evaluate(() => window.__outWrites);
    assert(w.length >= 4 && w.length <= 10, `30 input events in 1.5 s became ${w.length} writes`);
    const gaps = w.slice(1).map((t, i) => t - w[i]);
    assert(gaps.filter((g) => g < 120).length <= 1, 'writes are spaced out: ' + gaps.map(Math.round).join(', '));
    const want = await page.evaluate(() => window.__flashka.protocol.sliderToMa(300 + 29 * 15, 1200));
    assertEqual((await simState(page)).exactMa, want, 'the last position is the one that sticks');
  });

  await suite.step('demo: profile cards Extreme / Endurance / Balanced change the table; Turbo = High without turbo', async () => {
    await page.click('.lvl[data-level="3"]');
    await page.click('.prof[data-profile="0"]');
    await untilText(page, 'st-prof', /^Extreme$/);
    await untilText(page, 'st-led', /^900 mA$/);
    assertEqual(await attr(page, '.prof[data-profile="0"]', 'aria-pressed'), 'true');
    assertEqual(await attr(page, '.prof[data-profile="1"]', 'aria-pressed'), 'false');
    assert(!(await page.evaluate(() => document.getElementById('editor').open)), 'the editor stays closed for built-in profiles');
    await page.click('.prof[data-profile="2"]');
    await untilText(page, 'st-prof', /^Endurance$/);
    await untilText(page, 'st-led', /^300 mA$/);
    await page.click('.lvl[data-level="4"]');
    await untilText(page, 'level-note', /Turbo is the same as High/);
    assertEqual(await text(page, 'st-led'), '300 mA');
    assert(!(await visible(page, '#turbo-line')), 'no turbo timer in Endurance');
    await page.click('.prof[data-profile="1"]');
    await untilText(page, 'st-prof', /^Balanced$/);
    await page.click('.lvl[data-level="3"]');
    await untilText(page, 'st-led', /^600 mA$/);
  });

  await suite.step('demo: Custom editor - fields from the flashlight, range validation with plain messages', async () => {
    await page.click('.prof[data-profile="3"]');
    await until(page, () => document.getElementById('editor').open);
    await untilText(page, 'st-prof', /^Custom$/);
    await untilText(page, 'editor-note', /^These are the values your Custom profile uses right now\.$/);
    const vals = {};
    for (const k of ['moon', 'low', 'medium', 'high', 'turbo', 'turboTime', 'stepDown', 'tempLimit', 'lvStep', 'cellLimit']) vals[k] = await page.inputValue('#f-' + k);
    assertEqual(vals, { moon: '3', low: '30', medium: '200', high: '600', turbo: '1200', turboTime: '60', stepDown: '600', tempLimit: '50', lvStep: '3.35', cellLimit: '1600' });
    for (const id of ['fl-turbo', 'fl-remember', 'fl-battery']) assert(await page.isChecked('#' + id), id + ' checked');
    assert(await page.locator('#btn-apply').isEnabled() && await page.locator('#btn-save').isEnabled(), 'valid values: Apply and Save enabled');
    await page.fill('#f-moon', '99');
    assertEqual(await text(page, 'e-moon'), 'Use a value from 1 to 50.');
    assertEqual(await attr(page, '#f-moon', 'aria-invalid'), 'true');
    assertEqual(await text(page, 'e-low'), '', 'Low is not blamed for a wrong Moon');
    assert(await visible(page, '#editor-summary'), 'summary shown');
    assertEqual(await text(page, 'editor-summary'), 'One value is outside its allowed range. Fix the field marked in red to continue.');
    assert(await page.locator('#btn-apply').isDisabled() && await page.locator('#btn-save').isDisabled(), 'invalid: Apply and Save disabled');
    await page.fill('#f-moon', '2.5');
    assertEqual(await text(page, 'e-moon'), 'Enter a whole number.');
    await page.fill('#f-moon', '');
    assertEqual(await text(page, 'e-moon'), 'Enter a whole number.');
    await page.fill('#f-lvStep', '3.99');
    assertMatch(await text(page, 'e-lvStep'), /^Use a voltage from 3\.10 to 3\.60 V\.$/);
    await page.fill('#f-lvStep', '3.35');
    await page.fill('#f-moon', '3');
    assert(await page.locator('#btn-apply').isEnabled(), 'valid again');
    assert(!(await visible(page, '#editor-summary')), 'summary hidden again');
    await page.fill('#f-low', '60'); await page.fill('#f-medium', '50');     // two numbers in the wrong order: the later one is flagged, naming its neighbour
    assertEqual(await text(page, 'e-medium'), 'Use a value from 60 (Low) to 1000.');
    assertEqual(await text(page, 'e-low'), '');
    await page.fill('#f-low', '30'); await page.fill('#f-medium', '200');
    assert(await page.locator('#btn-apply').isEnabled(), 'valid again after the repair');
  });

  await suite.step('demo: Custom editor - Apply sends the 20-byte profile, reads it back and shows it', async () => {
    const entries = { moon: '5', low: '50', medium: '300', high: '700', turbo: '1500', turboTime: '30', stepDown: '600', tempLimit: '55', lvStep: '3.30', cellLimit: '2000' };
    for (const [k, v] of Object.entries(entries)) await page.fill('#f-' + k, v);
    await page.uncheck('#fl-battery');
    await page.click('#btn-apply');
    await untilText(page, 'adjusted', /^Applied\. The flashlight now uses your Custom profile exactly as shown\./);
    assert((await attr(page, '#adjusted', 'class')).includes('ok'), 'green notice');
    assertEqual(await simProfile(page), { id: 3, turboAllowed: true, rememberLevel: true, showBattery: false, moon: 5, low: 50, medium: 300, high: 700, turbo: 1500, turboTime: 30, stepDown: 600, tempLimit: 55, lvStep: 30, cellLimit: 2000 });
    assertEqual(await text(page, 'st-prof'), 'Custom');
    assertEqual(await text(page, 'pdesc-3'), 'Moon 5 · Low 50 · Medium 300 · High 700 mA · Turbo 1500 mA for 30 s');
    assertEqual(await attr(page, '.prof[data-profile="3"]', 'aria-pressed'), 'true');
    assert(await visible(page, '#adjusted'), 'notice stays visible after the re-render');
  });

  await suite.step('demo: if the flashlight adjusts a value, the app says so and shows what is really used', async () => {
    await page.evaluate(() => {
      const sim = window.__flashka.sim, P = window.__flashka.protocol, orig = sim.writeProfile;
      window.__origWriteProfile = orig;
      sim.writeProfile = function (bytes) { const p = P.decodeProfile(bytes); p.turbo = Math.min(p.turbo, 1400); return orig.call(sim, P.encodeProfile(p)); };
    });
    await page.fill('#f-turbo', '1600');
    await page.click('#btn-apply');
    await untilText(page, 'adjusted', /^Applied - but the flashlight adjusted 1 value to stay inside its safe range: Turbo 1600 → 1400 mA\./);
    assert((await attr(page, '#adjusted', 'class')).includes('warn'), 'amber notice');
    assertEqual(await page.inputValue('#f-turbo'), '1400', 'field shows the real value');
    assert((await attr(page, '.field[data-key="turbo"]', 'class')).includes('changed'), 'field marked as adjusted');
    await page.evaluate(() => { window.__flashka.sim.writeProfile = window.__origWriteProfile; });
    await page.fill('#f-turbo', '1500');
    assert(!(await visible(page, '#adjusted')), 'editing again hides the old notice');
  });

  await suite.step('demo: "Save to flashlight" (editor) applies pending edits first, then stores them (SAVE)', async () => {
    await clearToasts(page);
    await page.fill('#f-low', '60');
    await page.click('#btn-save');
    await untilToast(page, /Saved to flashlight/);
    const s = await simState(page);
    assert(s.saved, 'SAVE reached the flashlight');
    assertEqual([s.saved.custom.low, s.saved.custom.turbo, s.saved.profileId], [60, 1500, 3]);
    await page.click('#btn-reset-draft');
    assertEqual(await page.inputValue('#f-low'), '30');
    assertEqual(await page.inputValue('#f-lvStep'), '3.35');
    assertMatch(await text(page, 'editor-note'), /^Starting again from the Balanced values\. Nothing is sent until you press Apply or Save\./);
    assertEqual((await simProfile(page)).low, 60, 'nothing was sent by the reset');
    await page.click('.prof[data-profile="1"]');
    await untilText(page, 'st-prof', /^Balanced$/);
  });

  await suite.step('demo: "Make it stick" saves the selected profile and level', async () => {
    await clearToasts(page);
    await page.click('.lvl[data-level="1"]');
    await untilText(page, 'st-led', /^30 mA$/);
    await page.click('#btn-save-sel');
    await untilToast(page, /remember the current profile and brightness level/);
    const s = await simState(page);
    assertEqual([s.saved.profileId, s.saved.level], [1, 1]);
  });

  await suite.step('demo: lockout switch, "Locked" badge, friendly refusal when switching on', async () => {
    await clearToasts(page);
    await page.click('#sw-lockout');
    await until(page, () => document.getElementById('sw-lockout').getAttribute('aria-checked') === 'true');
    await untilToast(page, /The flashlight is locked/);
    assertMatch(await text(page, 'badges'), /Locked/);
    assertEqual((await simState(page)).lockout, true);
    await page.click('#btn-power');                    // OFF still works while locked
    await untilText(page, 'light-chip', /^Off$/);
    await clearToasts(page);
    await page.click('#btn-power');                    // ON does not
    await untilToast(page, /Lockout is on/);
    assertEqual((await simState(page)).on, false);
    await page.click('#sw-lockout');
    await until(page, () => document.getElementById('sw-lockout').getAttribute('aria-checked') === 'false');
    await untilToast(page, /The flashlight is unlocked/);
    assert(!/Locked/.test(await text(page, 'badges')), 'badge gone');
  });

  await suite.step('demo: Identify and Keep Bluetooth on', async () => {
    await clearToasts(page);
    await page.click('#btn-identify');
    await untilToast(page, /ring around the main button blinks cyan three times/);
    assertEqual((await simState(page)).identifyCount, 1);
    await clearToasts(page);
    await page.click('#btn-keepalive');
    await untilToast(page, /Bluetooth stays available for about 4 more minutes/);
    assertEqual((await simState(page)).keepalive, 255);
  });

  await suite.step('demo: button priority - banner with a countdown, controls paused, a stale write is explained, then released after 3 s', async () => {
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On/);
    await clearToasts(page);
    await page.click('#demo-button');                   // the "flashlight button" switches the light off and starts the 3 s lock
    await until(page, () => !document.getElementById('banner-lock').hidden);
    assertMatch(await text(page, 'banner-lock'), /App locked for [123] s - the button has priority\./);
    assert(await page.locator('#btn-power').isDisabled(), 'On/Off paused');
    assert((await page.$$eval('.lvl', (b) => b.every((x) => x.disabled))), 'levels paused');
    assert((await page.$$eval('.prof', (b) => b.every((x) => x.disabled))), 'profiles paused');
    await untilText(page, 'source-line', /the button/);
    const r = await page.evaluate(async () => {
      const a = window.__flashka;
      try { await a.state.link.sendCommand(a.protocol.cmd.on()); return null; }
      catch (e) { const i = a.protocol.explainError(e, a.state.status); return { code: i.code, kind: i.kind, title: i.title }; }
    });
    assertEqual(r, { code: 0x80, kind: 'priority', title: 'The button has priority' }, 'the demo flashlight refuses with 0x80');
    assertEqual((await simState(page)).on, false, 'the refused command did nothing');
    await advance(page, 3600);
    await until(page, () => document.getElementById('banner-lock').hidden);
    assert(await page.locator('#btn-power').isEnabled(), 'On/Off back');
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On/);
  });

  await suite.step('demo: USB cable - charging, fully charged, unplugged', async () => {
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^Off$/);
    await page.check('#demo-usb');
    await untilText(page, 'bat-line', /^Charging - USB connected$/);
    assert((await attr(page, '#bat-bar', 'class')).includes('charging'), 'animated charging bar');
    await setRange(page, 'demo-soc', 100);
    await page.evaluate(() => window.__flashka.sim.advance(2));
    await untilText(page, 'bat-line', /^Fully charged - USB connected$/);
    assertEqual(await text(page, 'bat-pct'), '100');
    await page.uncheck('#demo-usb');
    await untilText(page, 'bat-line', /^Running on battery$/);
    await setRange(page, 'demo-soc', 78);
    await untilText(page, 'bat-pct', /^78$/);
  });

  await suite.step('demo: hot day -> "Too warm" badge and a dimmer light; cooling removes it', async () => {
    await page.click('.lvl[data-level="3"]');
    await untilText(page, 'st-led', /^600 mA$/);
    await page.check('#demo-hot');
    await page.evaluate(() => window.__flashka.sim.advance(400));
    await untilText(page, 'badges', /Too warm - light reduced/);
    assertMatch(await text(page, 'st-temp'), /^5\d\.\d °C$/);
    const ma = parseInt(await text(page, 'st-led'), 10);
    assert(ma < 600 && ma >= 30, 'the thermal limit dims the LED: ' + ma);
    await page.uncheck('#demo-hot');
    await page.evaluate(() => window.__flashka.sim.advance(600));
    await until(page, () => !/Too warm/.test(document.getElementById('badges').textContent));
    await untilText(page, 'st-led', /^600 mA$/);
  });

  await suite.step('demo: nearly empty battery -> "Battery protection" badge and a red bar', async () => {
    await setRange(page, 'demo-soc', 4);
    await page.evaluate(() => window.__flashka.sim.advance(12));
    await untilText(page, 'badges', /Battery protection - light reduced/);
    await untilText(page, 'bat-pct', /^4$/);
    assert((await attr(page, '#bat-bar', 'class')).includes('low'), 'red bar');
    await setRange(page, 'demo-soc', 78);
    await page.evaluate(() => window.__flashka.sim.advance(20));
    await until(page, () => !/Battery protection/.test(document.getElementById('badges').textContent));
  });

  await suite.step('demo: lost connection -> banner and paused controls, Reconnect restores everything', async () => {
    await clearToasts(page);
    await page.click('#demo-drop');
    await until(page, () => !document.getElementById('banner-lost').hidden);
    assertEqual(await attr(page, 'body', 'data-conn'), 'lost');
    assertEqual(await text(page, 'pill-text'), 'Connection lost');
    assert(await page.evaluate(() => document.getElementById('view-main').inert), 'controls are inert while disconnected');
    await page.click('#btn-reconnect');
    await until(page, () => document.getElementById('banner-lost').hidden);
    await untilToast(page, /Reconnected to FlashKa-A7D4/);
    assertEqual(await attr(page, 'body', 'data-conn'), 'connected');
    assert(!(await page.evaluate(() => document.getElementById('view-main').inert)), 'controls live again');
    await untilText(page, 'light-chip', /^On/);
  });

  await suite.step('demo: Exit demo returns to the start screen', async () => {
    await page.click('#btn-exit-demo');
    await until(page, () => !document.getElementById('view-start').hidden);
    assertEqual(await text(page, 'pill-text'), 'Not connected');
    assert(!(await visible(page, '#view-main')) && !(await visible(page, '#banner-demo')), 'demo UI gone');
    await page.click('#btn-demo');
    await untilText(page, 'pill-text', /^Demo mode$/);
    await untilText(page, 'light-chip', /^Off$/);
    noErrors(h, 'whole demo session');
  });
  await h.close();
}

/* ================================================================== 2b. presenter card (demo mode) */
{
  const h = await newPage(browser, APP_URL);
  const { page } = h;
  const sim = (fn, arg) => page.evaluate(fn, arg);
  const presenterState = () => sim(() => { const a = window.__flashka, s = a.sim.state(); return { mode: s.mode, bonded: s.bonded, presenter: a.protocol.decodePresenter(a.sim.readPresenter()), saved: s.savedPresenter, on: s.on }; });
  await page.click('#btn-demo');
  await untilText(page, 'pill-text', /^Demo mode$/);

  await suite.step('presenter: the card is shown for a protocol 2 light with the key map, "Off" and 0 of 4 paired', async () => {
    assert(await visible(page, '#card-presenter'), 'presenter card visible');
    assertEqual(await text(page, 'presenter-chip'), 'Off');
    assertEqual(await text(page, 'btn-presenter'), 'Start presenter mode');
    assertEqual(await text(page, 'bonded-n'), '0');
    assertEqual(await text(page, 'key-next'), 'Page Down');
    assertEqual(await text(page, 'key-prev'), 'Page Up');
    assertEqual(await page.locator('#pk-page').isChecked(), true);
    assertEqual(await page.inputValue('#pf-idle'), '30');
    assertEqual(await page.locator('#pf-swap').isChecked(), false);
    assert(await page.locator('#btn-forget').isDisabled(), 'nothing to forget yet');
    assertMatch(await text(page, 'presenter-note'), /disconnects/, 'explains that the app disconnects');
    assertMatch(await text(page, 'foot-device'), /protocol v2/);
  });

  await suite.step('presenter: every control has an accessible name', async () => {
    const unnamed = await page.evaluate(() => Array.from(document.querySelectorAll('#card-presenter input, #card-presenter button, #card-presenter summary'))
      .filter((e) => e.offsetParent !== null)
      .filter((e) => { const name = (e.getAttribute('aria-label') || (e.labels && e.labels[0] && e.labels[0].textContent) || e.textContent || '').trim(); return !name; })
      .map((e) => e.id || e.tagName));
    assertEqual(unnamed, [], 'controls without a name');
    assertEqual(await page.evaluate(() => document.querySelector('#grp-keys legend').textContent), 'Keys for next and previous');
  });

  await suite.step('presenter: radio group works from the keyboard (arrow keys) and the key map follows', async () => {
    await page.focus('#pk-page');
    await page.keyboard.press('ArrowDown');
    assertEqual(await page.locator('#pk-arrows').isChecked(), true);
    assertEqual(await text(page, 'key-next'), 'Right Arrow');
    assertEqual(await text(page, 'key-prev'), 'Left Arrow');
    await page.check('#pf-swap');
    assertEqual(await text(page, 'key-next'), 'Left Arrow');
    assertEqual(await text(page, 'key-prev'), 'Right Arrow');
    await page.uncheck('#pf-swap');
    await page.check('#pk-page');
    assertEqual(await text(page, 'key-next'), 'Page Down');
  });

  await suite.step('presenter: idle time is validated (5-120) with a plain message; Apply and Save are disabled while wrong', async () => {
    for (const bad of ['4', '121', '', '7.5']) {
      await page.fill('#pf-idle', bad);
      assertMatch(await text(page, 'pe-idle'), /(5 to 120|whole number)/, 'message for "' + bad + '"');
      assertEqual(await attr(page, '#pf-idle', 'aria-invalid'), 'true');
      assert(await page.locator('#btn-presenter-apply').isDisabled() && await page.locator('#btn-presenter-save').isDisabled(), 'buttons disabled for "' + bad + '"');
    }
    await page.fill('#pf-idle', '5');
    assertEqual(await text(page, 'pe-idle'), '');
    assert(await page.locator('#btn-presenter-apply').isEnabled(), 'enabled again');
  });

  await suite.step('presenter: Apply writes the 4-byte setting and reads it back; Save also sends SAVE', async () => {
    await page.check('#pk-arrows'); await page.check('#pf-swap'); await page.fill('#pf-idle', '45');
    await page.click('#btn-presenter-apply');
    await untilToast(page, /Presenter settings applied/);
    let ps = await presenterState();
    assertEqual(ps.presenter, { keySet: 1, idleMin: 45, swap: true, flags: 1, reserved: 0 });
    assertEqual(ps.saved, null, 'Apply does not store anything');
    await clearToasts(page);
    await page.fill('#pf-idle', '60');
    await page.click('#btn-presenter-save');
    await untilToast(page, /Saved to flashlight/);
    ps = await presenterState();
    assertEqual(ps.presenter.idleMin, 60);
    assertEqual(ps.saved.idleMin, 60); assertEqual(ps.saved.keySet, 1); assertEqual(ps.saved.swap, true);
    assertEqual(await page.inputValue('#pf-idle'), '60');
    await clearToasts(page);
    await page.check('#pk-page'); await page.uncheck('#pf-swap'); await page.fill('#pf-idle', '30');
    await page.click('#btn-presenter-save');
    await untilToast(page, /Saved to flashlight/);
    assertEqual((await presenterState()).saved.swap, false);
  });

  await suite.step('presenter: "Start presenter mode" while the light is locked is refused with the lockout message', async () => {
    await clearToasts(page);
    await page.click('#sw-lockout');
    await until(page, () => window.__flashka.state.status.lockout);
    await clearToasts(page);
    await page.click('#btn-presenter');
    await untilToast(page, /Lockout is on/);
    assertEqual(await attr(page, 'body', 'data-conn'), 'connected');
    assertEqual((await presenterState()).mode, 0);
    await page.click('#sw-lockout');
    await until(page, () => !window.__flashka.state.status.lockout);
  });

  await suite.step('presenter: Start sends 0A 01, the app lets go and explains how to come back; no automatic reconnect', async () => {
    await page.evaluate(() => { window.__sent = []; const sim = window.__flashka.sim, o = sim.writeCommand; sim.writeCommand = function (b) { window.__sent.push(Array.from(b)); return o.call(sim, b); }; });
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On/);
    await advance_real(page, 3300);          // the app lock of a button is not involved, but let things settle
    await clearToasts(page);
    await page.click('#btn-presenter');
    await until(page, () => document.body.dataset.conn === 'lost', undefined, 6000);
    assertEqual((await sim(() => window.__sent.filter((c) => c[0] === 0x0a))), [[0x0a, 1]]);
    assertEqual(await attr(page, 'body', 'data-presenter'), '1');
    assertEqual(await text(page, 'pill-text'), 'Presenter mode');
    assertEqual(await text(page, 'lost-title'), 'Presenter mode.');
    assertMatch(await text(page, 'lost-text'), /Bluetooth keyboard.*2 seconds.*Reconnect/);
    assertEqual(await attr(page, '#banner-lost', 'class'), 'banner info');
    assert(await visible(page, '#demo-presenter-actions'), 'demo helpers shown');
    assert(!(await visible(page, '#btn-choose')), 'no "Choose another" in the demo');
    const ps = await presenterState();
    assertEqual([ps.mode, ps.on], [1, false]);
    assertEqual(await sim(() => window.__flashka.state.autoTries), 0);
  });

  await suite.step('presenter: Reconnect fails while the light is a keyboard and says what to do; pairing and leaving by button then work', async () => {
    await clearToasts(page);
    await page.click('#btn-reconnect');
    await untilToast(page, /still in presenter mode.*2 seconds/);
    assertEqual(await attr(page, 'body', 'data-conn'), 'lost');
    await page.click('#demo-pair');
    assertEqual((await presenterState()).bonded, 1);
    assertEqual((await presenterState()).mode, 2);
    await page.click('#demo-both2');
    assertEqual((await presenterState()).mode, 0);
    await page.click('#btn-reconnect');
    await until(page, () => document.body.dataset.conn === 'connected');
    assertEqual(await attr(page, 'body', 'data-presenter'), '');
    assert(!(await visible(page, '#demo-presenter-actions')), 'demo helpers hidden again');
    assertEqual(await text(page, 'bonded-n'), '1');
    assertEqual(await page.locator('#btn-forget').isEnabled(), true);
  });

  await suite.step('presenter: Forget asks first (Cancel keeps everything), then sends 0B A5', async () => {
    await clearToasts(page);
    await page.click('#btn-forget');
    assert(await visible(page, '#forget-confirm'), 'confirmation shown');
    assertEqual(await sim(() => document.activeElement.id), 'btn-forget-no', 'focus goes to the safe button');
    await page.click('#btn-forget-no');
    assert(!(await visible(page, '#forget-confirm')), 'confirmation closed');
    assertEqual((await presenterState()).bonded, 1);
    assertEqual(await sim(() => document.activeElement.id), 'btn-forget');
    await page.evaluate(() => { window.__sent = []; });
    await page.click('#btn-forget');
    await page.click('#btn-forget-yes');
    await untilToast(page, /forgot all paired computers/);
    assertEqual((await sim(() => window.__sent)), [[0x0b, 0xa5]]);
    assertEqual((await presenterState()).bonded, 0);
    await untilText(page, 'bonded-n', /^0$/);
    assert(await page.locator('#btn-forget').isDisabled(), 'nothing left to forget');
  });

  await suite.step('presenter: the how-to-pair help names every system', async () => {
    await page.click('#pair-help > summary');
    const t = await text(page, 'pair-help');
    for (const os of ['Windows', 'macOS', 'Android', 'iPhone and iPad', 'Linux and ChromeOS']) assertMatch(t, new RegExp(os), os);
    assertMatch(t, /FlashKa-XXXX/);
  });

  await suite.step('presenter: demo light settings survive a reconnect (read from the light, not kept in the page)', async () => {
    await page.fill('#pf-idle', '90'); await page.click('#btn-presenter-apply');
    await untilToast(page, /Presenter settings applied/);
    await page.click('#demo-drop');
    await until(page, () => document.body.dataset.conn === 'lost');
    await page.click('#btn-reconnect');
    await until(page, () => document.body.dataset.conn === 'connected');
    assertEqual(await page.inputValue('#pf-idle'), '90');
  });

  await suite.step('presenter: demo model "v0.5 light" hides the presenter card and shows protocol v1', async () => {
    await page.selectOption('#demo-model', '1');
    await untilText(page, 'pill-text', /^Demo mode$/);
    await untilText(page, 'foot-device', /protocol v1/);
    assert(!(await visible(page, '#card-presenter')), 'presenter card hidden');
    assert(await visible(page, '#btn-power'), 'the rest of the app works');
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On/);
    assertEqual(await sim(() => window.__flashka.sim.readStatus().length), 18);
    await page.selectOption('#demo-model', '2');
    await until(page, () => !document.getElementById('card-presenter').hidden);
    assertMatch(await text(page, 'foot-device'), /FlashKa-A7D4 .*protocol v2/);
    noErrors(h, 'presenter demo session');
  });
  await h.close();
}

/* ================================================================== 2c. contrast of the presenter screens (WCAG AA 4.5:1) */
{
  const contrastScript = () => {
    const parse = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c); const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
    const lum = ({ r, g, b }) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c.a > 0.99) return c; } return parse(getComputedStyle(document.body).backgroundColor); };
    const bad = [];
    const sel = '#card-presenter p, #card-presenter b, #card-presenter dt, #card-presenter dd, #card-presenter kbd, #card-presenter label, #card-presenter legend, #card-presenter .chip, #card-presenter .help, #card-presenter .err, #card-presenter .btn, #card-presenter summary, #card-presenter li, #card-presenter h2, #card-presenter h3, #banner-lost, #banner-lost b, #forget-confirm, .pill';
    document.querySelectorAll(sel).forEach((el) => {
      if (el.offsetParent === null && el.id !== 'banner-lost') return;
      if (!el.textContent.trim()) return;
      const fg = parse(getComputedStyle(el).color), bg = bgOf(el);
      const l1 = lum(fg), l2 = lum(bg), ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      if (ratio < 4.5) bad.push((el.id || el.className || el.tagName) + ' ' + ratio.toFixed(2));
    });
    return bad;
  };
  for (const dark of [false, true]) {
    await suite.step(`contrast: presenter card, forget dialog, presenter banner and pill are at least 4.5:1 (${dark ? 'dark' : 'light'})`, async () => {
      const h = await newPage(browser, APP_URL, { dark, width: 1280, height: 900 });
      await h.page.click('#btn-demo');
      await untilText(h.page, 'pill-text', /^Demo mode$/);
      await h.page.fill('#pf-idle', '3');                      // show the error text as well
      await h.page.click('#pair-help > summary');
      assertEqual(await h.page.evaluate(contrastScript), [], 'low contrast');
      await h.page.fill('#pf-idle', '30');
      await h.page.click('#btn-presenter');
      await until(h.page, () => document.body.dataset.conn === 'lost', undefined, 6000);
      assertEqual(await h.page.evaluate(contrastScript), [], 'low contrast while in presenter mode');
      noErrors(h); await h.close();
    });
  }
}

/* ================================================================== 3. real Bluetooth code path, against a fake navigator.bluetooth */
{
  const SERVICE = 'a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13';
  const fb = (page, fn, arg) => page.evaluate(fn, arg);
  const logHex = (page) => page.evaluate(() => window.__fakeBle.log.filter((l) => l.op === 'write' || l.op === 'error').map((l) => (l.op === 'error' ? 'ERR ' + l.message : l.uuid + ' ' + l.hex)));

  const h = await newPage(browser, APP_URL, { bluetooth: true, clock: true });
  const { page } = h;

  await suite.step('Bluetooth: with Web Bluetooth present there is no "unsupported" notice and Connect works', async () => {
    assert(!(await visible(page, '#support')), 'no support notice');
    assert(await visible(page, '#steps'), 'how-to steps shown');
    assert(await page.locator('#btn-connect').isEnabled(), 'Connect enabled');
    await page.click('#btn-connect');
    await until(page, () => document.body.dataset.conn === 'connected');
    const calls = await fb(page, () => window.__fakeBle.requestCalls);
    assertEqual(calls, [{ filters: [{ namePrefix: 'FlashKa' }, { namePrefix: 'Aurora' }], optionalServices: [SERVICE, 'battery_service'] }], 'requestDevice options');
    assertEqual(await text(page, 'pill-text'), 'FlashKa-BEEF');
    assert(!(await visible(page, '#banner-demo')), 'no demo banner on a real link');
    assert(!(await visible(page, '#card-demo')), 'no demo tools on a real link');
    await untilText(page, 'bat-pct', /^64$/);
    await untilText(page, 'foot-device', /FlashKa-BEEF · FlashKa fw 0\.6\.0/);
    assertEqual(await text(page, 'light-chip'), 'Off');
    noErrors(h);
  });

  await suite.step('Bluetooth: commands arrive as the documented bytes, one GATT operation at a time', async () => {
    await page.evaluate(() => { window.__fakeBle.log.length = 0; });
    await page.click('#btn-power');
    await untilText(page, 'light-chip', /^On · Medium/);
    await page.click('.lvl[data-level="3"]');
    await untilText(page, 'light-chip', /^On · High · 600 mA/);
    await page.click('.prof[data-profile="0"]');
    await untilText(page, 'st-prof', /^Extreme$/);
    const w = (await logHex(page)).filter((l) => l.startsWith('a7d40003'));
    assertEqual(w, ['a7d40003 02', 'a7d40003 03 03', 'a7d40003 04 00']);
    assertEqual(await fb(page, () => window.__fakeBle.violations), 0);
  });

  await suite.step('Bluetooth: a burst of taps never overlaps GATT operations (Chrome would answer "operation already in progress")', async () => {
    await page.evaluate(() => {
      document.getElementById('btn-power').click();
      document.querySelector('.lvl[data-level="1"]').click();
      document.querySelector('.prof[data-profile="1"]').click();
      document.getElementById('btn-identify').click();
      document.getElementById('btn-keepalive').click();
      document.getElementById('btn-save-sel').click();
      const s = document.getElementById('slider'); s.value = '400'; s.dispatchEvent(new Event('input', { bubbles: true })); s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(1800);
    assertEqual(await fb(page, () => window.__fakeBle.violations), 0, 'overlapping GATT operations');
    assertEqual(await fb(page, () => window.__fakeBle.maxConcurrent), 1, 'max operations in flight');
    assertEqual(await page.evaluate(() => document.querySelectorAll('#toasts .toast.err').length), 0, 'no error toast');
    noErrors(h);
  });

  await suite.step('Bluetooth: Status notifications and Battery Level notifications update the screen', async () => {
    await fb(page, () => window.__fakeBle.sim.setSoc(31));
    await untilText(page, 'bat-pct', /^31$/);
    await fb(page, () => window.__fakeBle.sim.setUsb(true));
    await untilText(page, 'bat-line', /USB connected|Charging/);
    await fb(page, () => window.__fakeBle.sim.setUsb(false));
    await untilText(page, 'bat-line', /^Running on battery$/);
    await fb(page, () => window.__fakeBle.press());     // a button press on the flashlight itself
    await until(page, () => !document.getElementById('banner-lock').hidden);
    await untilText(page, 'source-line', /the button/);
    await advance(page, 3500);
    await until(page, () => document.getElementById('banner-lock').hidden);
  });

  await suite.step('Bluetooth: the ATT error code is read from the message (0x80-0x83 -> friendly text)', async () => {
    for (const [code, re] of [[0x80, /The button has priority/], [0x81, /did not accept that/], [0x82, /Refused to protect/], [0x83, /The flashlight is locked/]]) {
      await clearToasts(page);
      await page.evaluate((c) => {
        const P = window.FlashKaProtocol, fb = window.__fakeBle, orig = fb.sim.writeCommand;
        fb.sim.writeCommand = function () { fb.sim.writeCommand = orig; throw P.makeAttError(c); };
      }, code);
      await page.click('#btn-identify');
      await untilToast(page, re);
    }
  });

  await suite.step('Bluetooth: browsers that hide the code - the reason is inferred from the last Status and flagged as a guess', async () => {
    await clearToasts(page);
    await page.evaluate(() => { window.__fakeBle.sim.writeCommand(window.FlashKaProtocol.cmd.lockout(true)); });
    await until(page, () => window.__flashka.state.status.lockout);
    await page.evaluate(() => { window.__fakeBle.failNext = { kind: 'write', match: 'a7d40003', times: 1, name: 'NetworkError', message: 'GATT operation failed for unknown reason.' }; });
    await page.click('#btn-identify');
    await untilToast(page, /The flashlight is locked[\s\S]*most likely reason/);
    await page.evaluate(() => { window.__fakeBle.sim.writeCommand(window.FlashKaProtocol.cmd.lockout(false)); });
    await until(page, () => !window.__flashka.state.status.lockout);
    await clearToasts(page);
    await page.evaluate(() => { window.__fakeBle.failNext = { kind: 'write', match: 'a7d40003', times: 1, name: 'NetworkError', message: 'GATT operation failed for unknown reason.' }; });
    await page.click('#btn-identify');
    await untilToast(page, /The command failed\. Try again[\s\S]*GATT operation failed for unknown reason/);
  });

  await suite.step('Bluetooth: KEEPALIVE - one-byte form first (what the table says); the 3-byte form when the firmware wants it', async () => {
    await clearToasts(page);
    await page.evaluate(() => { window.__fakeBle.log.length = 0; window.__fakeBle.keepaliveMode = 'u8'; });
    await page.click('#btn-keepalive');
    await untilToast(page, /about 4 more minutes/);
    assertEqual((await logHex(page)).filter((l) => l.startsWith('a7d40003')), ['a7d40003 09 FF']);
    await clearToasts(page);
    await page.evaluate(() => { window.__fakeBle.log.length = 0; window.__fakeBle.keepaliveMode = 'u16'; });
    await page.click('#btn-keepalive');
    await untilToast(page, /about 10 more minutes/);
    assertEqual((await logHex(page)).filter((l) => l.startsWith('a7d40003') || l.startsWith('ERR')), ['a7d40003 09 FF', 'ERR GATT operation failed: ATT error 0x81', 'a7d40003 09 58 02']);
    await page.evaluate(() => { window.__fakeBle.keepaliveMode = 'both'; });
  });

  await suite.step('Bluetooth: Custom profile - the 20-byte packet on the wire, then read back', async () => {
    await page.click('.prof[data-profile="3"]');
    await until(page, () => document.getElementById('editor').open);
    await page.evaluate(() => { window.__fakeBle.log.length = 0; });
    await page.fill('#f-medium', '250');
    await page.click('#btn-apply');
    await untilText(page, 'adjusted', /^Applied\./);
    const w = (await logHex(page)).filter((l) => l.startsWith('a7d40004'));
    assertEqual(w, ['a7d40004 03 07 03 00 1E 00 FA 00 58 02 B0 04 3C 00 58 02 32 23 40 06']);
    // 03 | flags 07 | moon 3 | low 30 | medium 250 | high 600 | turbo 1200 | 60 s | step-down 600 | 50 C | 35 | 1600 mA
  });

  await suite.step('Bluetooth: connection lost -> automatic reconnect; the user sees "Reconnected"', async () => {
    await clearToasts(page);
    const before = await fb(page, () => window.__fakeBle.connectCount);
    await fb(page, () => window.__fakeBle.drop());
    await until(page, () => document.body.dataset.conn === 'lost');
    assert(await visible(page, '#banner-lost'), 'banner while away');
    await advance(page, 2500);
    await until(page, () => document.body.dataset.conn === 'connected');
    await untilToast(page, /Reconnected to FlashKa-BEEF/);
    assertEqual(await fb(page, () => window.__fakeBle.connectCount), before + 1);
    await page.click('#btn-power');                      // controls work again, with fresh notifications
    await page.waitForTimeout(400);
    noErrors(h);
  });

  await suite.step('Bluetooth: flashlight stays out of reach -> manual Reconnect says so, then works', async () => {
    await clearToasts(page);
    await fb(page, () => { window.__fakeBle.connectFailures = 99; window.__fakeBle.drop(); });
    await until(page, () => document.body.dataset.conn === 'lost');
    await advance(page, 12000);                          // two automatic tries (each with three connection attempts) fail
    assertEqual(await attr(page, 'body', 'data-conn'), 'lost');
    await page.click('#btn-reconnect');
    await advance(page, 3500);
    await untilToast(page, /Could not reconnect[\s\S]*Wake the flashlight/);
    await fb(page, () => { window.__fakeBle.connectFailures = 0; });
    await page.click('#btn-reconnect');
    await advance(page, 600);
    await until(page, () => document.body.dataset.conn === 'connected');
    await untilToast(page, /Reconnected to FlashKa-BEEF/);
  });

  await suite.step('Bluetooth: Disconnect goes back to the start screen', async () => {
    await page.click('#btn-disconnect');
    await until(page, () => !document.getElementById('view-start').hidden);
    assertEqual(await fb(page, () => window.__fakeBle.server.connected), false, 'GATT disconnected');
    noErrors(h, 'whole Bluetooth session');
  });
  await h.close();

  /* --- start-up problems, each on a fresh page --- */
  await suite.step('Bluetooth: chooser cancelled / adapter off / connection fails / wrong protocol version', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true });
    const p = t.page;
    await p.evaluate(() => { window.__fakeBle.chooser = 'cancel'; });
    await p.click('#btn-connect');
    await untilText(p, 'start-msg', /^No flashlight was chosen\./);
    assert((await attr(p, '#start-msg', 'class')).includes('err'), 'shown as an error');
    await p.evaluate(() => { window.__fakeBle.chooser = 'none'; });
    await p.click('#btn-connect');
    await untilText(p, 'start-msg', /^Bluetooth seems to be switched off/);
    await p.evaluate(() => { window.__fakeBle.chooser = 'ok'; window.__fakeBle.connectFailures = 99; });
    await p.click('#btn-connect');
    await untilText(p, 'start-msg', /^Could not connect: Connection attempt failed\./, 12000);
    assertEqual(await attr(p, 'body', 'data-conn'), 'idle');
    await p.evaluate(() => { window.__fakeBle.connectFailures = 0; window.__fakeBle.versionOverride = 3; });
    await p.click('#btn-connect');
    await until(p, () => document.body.dataset.conn === 'connected');
    await untilToast(p, /protocol version 3, this app speaks versions 1 and 2/);
    noErrors(t); await t.close();
  });
  await suite.step('Bluetooth: Bluetooth switched off is reported before the user taps Connect', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true, init: ['window.__fakeBle.available = false;'] });
    await untilText(t.page, 'start-msg', /^Bluetooth looks switched off or missing/);
    noErrors(t); await t.close();
  });
  await suite.step('Bluetooth: works when the Battery Service is missing (Status carries the percentage)', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true });
    await t.page.evaluate(() => { window.__fakeBle.hideBattery = true; });
    await t.page.click('#btn-connect');
    await until(t.page, () => document.body.dataset.conn === 'connected');
    await untilText(t.page, 'bat-pct', /^64$/);
    noErrors(t); await t.close();
  });
}

/* ================================================================== 3b. presenter over the (fake) Bluetooth link */
{
  const wire = (page) => page.evaluate(() => window.__fakeBle.log.filter((l) => l.op === 'write' || l.op === 'read' || l.op === 'error').map((l) => l.op + ' ' + (l.op === 'error' ? l.message : l.uuid + ' ' + l.hex)));
  const h = await newPage(browser, APP_URL, { bluetooth: true });
  const { page } = h;

  await suite.step('Bluetooth v2: the Presenter characteristic is read at connect; Apply / Save use the documented bytes', async () => {
    await page.click('#btn-connect');
    await until(page, () => document.body.dataset.conn === 'connected');
    assert(await visible(page, '#card-presenter'), 'card visible');
    const first = await wire(page);
    assert(first.includes('read a7d40006 00 1E 00 00'), 'presenter read at connect: ' + JSON.stringify(first));
    await untilText(page, 'foot-device', /FlashKa-BEEF · FlashKa fw 0\.6\.0 · app 0\.6\.0 · protocol v2/);
    await page.evaluate(() => { window.__fakeBle.log.length = 0; });
    await page.check('#pk-arrows'); await page.check('#pf-swap'); await page.fill('#pf-idle', '120');
    await page.click('#btn-presenter-save');
    await untilToast(page, /Saved to flashlight/);
    const w = (await wire(page)).filter((l) => l.startsWith('write'));
    assertEqual(w, ['write a7d40006 01 78 01 00', 'write a7d40003 08']);
    assertEqual(await page.evaluate(() => window.__fakeBle.violations), 0);
    noErrors(h);
  });

  await suite.step('Bluetooth v2: the light clamps a value; the app shows what the light really uses', async () => {
    await page.evaluate(() => { const sim = window.__fakeBle.sim, o = sim.writePresenter; sim.writePresenter = function (b) { const c = Uint8Array.from(b); c[1] = 100; return o.call(sim, c); }; });
    await clearToasts(page);
    await page.fill('#pf-idle', '110'); await page.click('#btn-presenter-apply');
    await untilToast(page, /adjusted a value/);
    assertEqual(await page.inputValue('#pf-idle'), '100');
  });

  await suite.step('Bluetooth v2: Start presenter mode sends 0A 01, the light drops the link, the app explains and does not retry', async () => {
    await page.evaluate(() => { window.__fakeBle.log.length = 0; });
    await page.click('#btn-presenter');
    await until(page, () => document.body.dataset.conn === 'lost', undefined, 6000);
    const w = (await wire(page)).filter((l) => l.startsWith('write'));
    assertEqual(w, ['write a7d40003 0A 01']);
    assertEqual(await text(page, 'pill-text'), 'Presenter mode');
    assertEqual(await text(page, 'lost-title'), 'Presenter mode.');
    assert(!(await visible(page, '#demo-presenter-actions')), 'demo helpers only exist in demo mode');
    await page.waitForTimeout(6000);              // the normal path would have retried after 1.2 s and 4 s
    assertEqual(await page.evaluate(() => window.__fakeBle.connectCount), 1, 'no automatic reconnect attempts');
    assertEqual(await text(page, 'pill-text'), 'Presenter mode');
  });

  await suite.step('Bluetooth v2: Reconnect fails while in presenter mode (service not offered), then works after leaving', async () => {
    await clearToasts(page);
    await page.click('#btn-reconnect');
    await untilToast(page, /still in presenter mode/);
    await page.evaluate(() => window.__fakeBle.sim.holdBothButtons(2));
    await page.click('#btn-reconnect');
    await until(page, () => document.body.dataset.conn === 'connected');
    await untilToast(page, /Reconnected to FlashKa-BEEF/);
    assertEqual(await text(page, 'lost-title'), 'Presenter mode.', 'old text is hidden anyway');
    assertEqual(await attr(page, 'body', 'data-presenter'), '');
    noErrors(h);
  });

  await suite.step('Bluetooth v2: forgetting computers sends 0B A5 only after the confirmation', async () => {
    await page.evaluate(() => { const s = window.__fakeBle.sim; s.writeCommand(Uint8Array.of(0x0a, 1)); s.pairComputer(); s.holdBothButtons(2); });
    await page.waitForTimeout(500);
    await page.click('#btn-reconnect').catch(() => {});
    await until(page, () => document.body.dataset.conn === 'connected', undefined, 10000);
    await untilText(page, 'bonded-n', /^1$/);
    await page.evaluate(() => { window.__fakeBle.log.length = 0; });
    await page.click('#btn-forget');
    assertEqual((await wire(page)).filter((l) => l.startsWith('write')), [], 'nothing is sent before the confirmation');
    await page.click('#btn-forget-yes');
    await untilText(page, 'bonded-n', /^0$/);
    assertEqual((await wire(page)).filter((l) => l.startsWith('write')), ['write a7d40003 0B A5']);
  });
  await h.close();

  await suite.step('Bluetooth v2: a light that refuses 0A 01 (ATT 0x82, battery empty) stays connected and the message is friendly', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true, init: ['window.__fakeBle.soc = 2;'] });
    await t.page.click('#btn-connect');
    await until(t.page, () => document.body.dataset.conn === 'connected');
    await t.page.click('#btn-presenter');
    await untilToast(t.page, /battery is nearly empty/);
    assertEqual(await attr(t.page, 'body', 'data-conn'), 'connected');
    assertEqual(await attr(t.page, 'body', 'data-presenter'), '');
    assertEqual(await t.page.evaluate(() => window.__flashka.state.presenterOut), false);
    noErrors(t); await t.close();
  });

  await suite.step('Bluetooth v1 (v0.5 light): no presenter card, the Presenter characteristic is never touched, everything else works', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true, init: ['window.__fakeBle.protocol = 1; window.__fakeBle.deviceName = "Aurora-C0DE";'] });
    await t.page.click('#btn-connect');
    await until(t.page, () => document.body.dataset.conn === 'connected');
    assertEqual(await text(t.page, 'pill-text'), 'Aurora-C0DE');
    assert(!(await visible(t.page, '#card-presenter')), 'presenter card hidden');
    assertMatch(await text(t.page, 'foot-device'), /protocol v1/);
    assertEqual(await t.page.evaluate(() => window.__fakeBle.log.filter((l) => l.uuid === 'a7d40006').length), 0);
    await t.page.click('#btn-power');
    await untilText(t.page, 'light-chip', /^On/);
    assertEqual(await t.page.evaluate(() => window.__flashka.state.status.version), 1);
    assertEqual((await toastTexts(t.page)).filter((x) => /Version mismatch|protocol version/.test(x)), [], 'no version warning for protocol 1');
    noErrors(t); await t.close();
  });

  await suite.step('Bluetooth v2 light without the Presenter characteristic: card stays hidden, no error', async () => {
    const t = await newPage(browser, APP_URL, { bluetooth: true, init: ['window.__fakeBle.hidePresenter = true;'] });
    await t.page.click('#btn-connect');
    await until(t.page, () => document.body.dataset.conn === 'connected');
    assert(!(await visible(t.page, '#card-presenter')), 'presenter card hidden');
    noErrors(t); await t.close();
  });
}

/* ================================================================== 4. no horizontal scrolling */
{
  for (const width of [320, 360, 390, 1280]) {
    await suite.step(`layout: no horizontal scroll at ${width} px (start, demo, editor open)`, async () => {
      const h = await newPage(browser, APP_URL, { width, height: 800 });
      const check = async (what) => { const m = await noHorizontalScroll(h.page); assert(m.sw <= m.iw && m.bw <= m.iw, `${what}: scrollWidth ${m.sw}, body ${m.bw}, window ${m.iw}`); };
      await check('start view');
      await h.page.click('#btn-demo');
      await untilText(h.page, 'pill-text', /^Demo mode$/);
      await h.page.click('#btn-power');
      await untilText(h.page, 'light-chip', /^On/);
      await check('demo view');
      await h.page.click('.prof[data-profile="3"]');
      await until(h.page, () => document.getElementById('editor').open);
      await h.page.fill('#f-moon', '99');
      await check('editor with errors');
      await h.page.evaluate(() => { window.__flashka.sim.pressButton(); });
      await check('lock banner');
      const small = await h.page.evaluate(() => Array.from(document.querySelectorAll('button')).filter((b) => b.offsetParent !== null && !b.hidden).map((b) => { const r = b.getBoundingClientRect(); return { id: b.id || b.textContent.trim().slice(0, 20), w: Math.round(r.width), h: Math.round(r.height) }; }).filter((b) => b.h < 40 || b.w < 40));
      assertEqual(small, [], 'touch targets of at least 40x40 px');
      noErrors(h); await h.close();
    });
  }
}

/* ================================================================== 5. screenshots */
if (!NO_SHOTS) {
  const shots = [];
  const top = (page) => page.evaluate(() => window.scrollTo(0, 0));
  const to = (page, id) => page.evaluate((i) => document.getElementById(i).scrollIntoView({ block: 'start' }), id);
  async function flow(width, height, dark) {
    const phone = width < 600, dpr = phone ? 2 : 1, d = dark ? 'dark-' : '';
    const name = (what) => `app-${d}${what}-${width}.png`;
    /* start screen of a browser that has Web Bluetooth */
    let h = await newPage(browser, APP_URL, { width, height, dark, dpr, bluetooth: true });
    shots.push(await shot(h.page, name('start')));
    noErrors(h); await h.close();
    /* what a browser without Web Bluetooth shows */
    if (!dark) {
      h = await newPage(browser, APP_URL, { width, height, dark, dpr });
      shots.push(await shot(h.page, name('unsupported')));
      noErrors(h); await h.close();
    }
    /* demo session */
    h = await newPage(browser, APP_URL, { width, height, dark, dpr, clock: true });
    const page = h.page;
    await page.click('#btn-demo');
    await untilText(page, 'pill-text', /^Demo mode$/);
    await untilText(page, 'foot-device', /fw 0\.6\.0/);
    await top(page);
    shots.push(await shot(page, name('demo-off')));
    await page.click('.lvl[data-level="3"]');
    await untilText(page, 'light-chip', /^On · High · 600 mA$/);
    await page.waitForTimeout(500);
    await clearToasts(page); await top(page);
    shots.push(await shot(page, name('demo-on')));
    if (phone) {
      await to(page, 'card-light'); await clearToasts(page);
      shots.push(await shot(page, name('light-controls')));
      await to(page, 'card-profile');
      shots.push(await shot(page, name('profiles')));
      await to(page, 'card-tools');
      shots.push(await shot(page, name('settings')));
      if (!dark) { await top(page); shots.push(await shot(page, `app-demo-on-${width}-full.png`, { full: true })); }
    }
    if (!dark || phone) {
      await page.click('.lvl[data-level="4"]');
      await until(page, () => !document.getElementById('turbo-line').hidden);
      await advance(page, 14000);
      await clearToasts(page); await top(page);
      shots.push(await shot(page, name('turbo')));
    }
    if (!dark) {
      await page.click('.lvl[data-level="2"]');
      await untilText(page, 'st-led', /^200 mA$/);
      await page.click('#demo-button');
      await until(page, () => !document.getElementById('banner-lock').hidden);
      await to(page, 'card-light'); await clearToasts(page);
      shots.push(await shot(page, name('locked')));
      await advance(page, 3600);
      await page.click('.prof[data-profile="3"]');
      await until(page, () => document.getElementById('editor').open);
      await page.fill('#f-medium', '250'); await page.fill('#f-high', '700'); await page.fill('#f-turbo', '1500');
      await page.click('#btn-apply');
      await untilText(page, 'adjusted', /^Applied/);
      await to(page, 'editor'); await clearToasts(page);
      shots.push(await shot(page, name('editor')));
      if (phone) {
        await page.evaluate(() => document.getElementById('btn-save').scrollIntoView({ block: 'end' }));
        shots.push(await shot(page, name('editor-buttons')));
        await to(page, 'editor');
      }
      await page.fill('#f-low', '999');
      await to(page, 'editor');
      shots.push(await shot(page, name('editor-error')));
      await page.fill('#f-low', '30');
      await page.evaluate(() => document.getElementById('demo-drop').click());
      await until(page, () => !document.getElementById('banner-lost').hidden);
      await top(page);
      shots.push(await shot(page, name('lost')));
    }
    /* presenter screens */
    if ((await page.evaluate(() => document.body.dataset.conn)) === 'lost') {
      await page.click('#btn-reconnect');
      await until(page, () => document.body.dataset.conn === 'connected');
    }
    await clearToasts(page);
    await to(page, 'card-presenter');
    shots.push(await shot(page, name('presenter')));
    if (phone && !dark) {
      await page.click('#pair-help > summary');
      await page.evaluate(() => document.getElementById('pair-help').scrollIntoView({ block: 'start' }));
      shots.push(await shot(page, name('presenter-help')));
      await page.click('#pair-help > summary');
    }
    await page.click('#btn-presenter');
    await until(page, () => document.body.dataset.conn === 'lost', undefined, 8000);
    await clearToasts(page); await top(page);
    shots.push(await shot(page, name('presenter-mode')));
    if (!dark) {
      await page.click('#demo-pair');
      await page.click('#demo-both2');
      await page.click('#btn-reconnect');
      await until(page, () => document.body.dataset.conn === 'connected');
      await untilText(page, 'bonded-n', /^1$/);
      await page.click('#btn-forget');
      await clearToasts(page);
      await page.evaluate(() => document.getElementById('forget-confirm').scrollIntoView({ block: 'center' }));
      shots.push(await shot(page, name('presenter-forget')));
    }
    noErrors(h, `screenshot session ${width} ${dark ? 'dark' : 'light'}`); await h.close();
  }
  await suite.step('screenshots 390x844 (light and dark)', async () => { await flow(390, 844, false); await flow(390, 844, true); });
  await suite.step('screenshots 1280x800 (light and dark)', async () => { await flow(1280, 800, false); await flow(1280, 800, true); });
  suite.note(`${shots.length} screenshots written to app/screenshots/`);
}

await browser.close();
process.exit(suite.summary() ? 0 : 1);
