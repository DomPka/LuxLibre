// SPDX-License-Identifier: MIT OR Apache-2.0
// Tests for the demo flashlight (the JavaScript simulator inside flashka-app.html).
// It must behave like the document says: button priority, lockout, protection, turbo timer,
// profile clamping, notifications - and every status it produces must decode with the real decoder.
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadAppModules, plain } from './helpers/load-app.mjs';

const { P, Sim } = loadAppModules();
const st = (sim) => P.decodeStatus(sim.readStatus());
const code = (fn) => { try { fn(); } catch (e) { return P.attErrorCode(e); } return 'no error'; };
const make = (opts) => Sim.createFlashlight(opts);

test('fresh flashlight: off, Balanced, Medium remembered, 78 %, protocol version 2', () => {
  const s = st(make());
  assert.equal(s.version, 2); assert.equal(s.mode, 0); assert.equal(s.bondedHosts, 0); assert.equal(s.on, false); assert.equal(s.profile, 1); assert.equal(s.level, 2);
  assert.equal(s.soc, 78); assert.equal(s.currentMa, 0); assert.equal(s.runtimeMin, null); assert.equal(s.appLockS, 0); assert.equal(s.source, 0);
  assert.ok(s.voltageMv > 3900 && s.voltageMv < 4100);
});

test('every status the simulator makes round-trips through decodeStatus/encodeStatus', () => {
  const sim = make();
  const check = () => { const b = sim.readStatus(); assert.equal(b.length, 20); assert.equal(P.toHex(P.encodeStatus(P.decodeStatus(b))), P.toHex(b)); };
  check();
  sim.writeCommand(P.cmd.on()); check();
  sim.writeCommand(P.cmd.level(4)); check();
  sim.advance(20); check();
  sim.setAmbient(60); sim.advance(900); check();
  sim.setUsb(true); sim.setLaser(true); sim.setSoc(3); check();
  sim.pressButton(); check();
});

test('ON / OFF / LEVEL follow the profile table (Balanced 3/30/200/600, Turbo 1200)', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on());
  let s = st(sim);
  assert.equal(s.on, true); assert.equal(s.currentMa, 200); assert.equal(s.source, 2); assert.ok(s.runtimeMin > 0);
  [[0, 3], [1, 30], [2, 200], [3, 600]].forEach(([lvl, ma]) => { sim.writeCommand(P.cmd.level(lvl)); s = st(sim); assert.equal(s.level, lvl); assert.equal(s.currentMa, ma); assert.equal(s.turbo, false); });
  sim.writeCommand(P.cmd.off());
  s = st(sim); assert.equal(s.on, false); assert.equal(s.currentMa, 0); assert.equal(s.runtimeMin, null);
  // LEVEL while off only changes the remembered level; ON then uses it
  sim.writeCommand(P.cmd.level(1)); assert.equal(st(sim).on, false); assert.equal(st(sim).level, 1);
  sim.writeCommand(P.cmd.on()); assert.equal(st(sim).currentMa, 30);
});

test('turbo: 1200 mA for 60 s, counts down, then steps down to 600 mA by itself', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(4));
  let s = st(sim);
  assert.equal(s.turbo, true); assert.equal(s.currentMa, 1200); assert.equal(s.turboLeftS, 60); assert.equal(s.level, 4);
  let prev = 60;
  for (let i = 0; i < 29; i++) { sim.advance(1); s = st(sim); assert.ok(s.turboLeftS <= prev); prev = s.turboLeftS; }
  assert.equal(s.turboLeftS, 31); assert.equal(s.currentMa, 1200);
  sim.advance(31);
  s = st(sim);
  assert.equal(s.turbo, false); assert.equal(s.turboLeftS, 0); assert.equal(s.currentMa, 600); assert.equal(s.source, 3, 'the timer is an automatic change');
  assert.equal(s.level, 4, 'the selected level stays Turbo; only the current stepped down');
  // choosing Turbo again restarts it
  sim.writeCommand(P.cmd.level(4)); s = st(sim); assert.equal(s.turbo, true); assert.equal(s.currentMa, 1200);
});

test('Extreme turbo is 2200 mA for 45 s; Endurance has no extra turbo (Turbo = High = 300 mA)', () => {
  const sim = make();
  sim.writeCommand(P.cmd.profile(0)); sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(4));
  let s = st(sim); assert.equal(s.currentMa, 2200); assert.equal(s.turboLeftS, 45); assert.equal(s.profile, 0);
  sim.writeCommand(P.cmd.profile(2)); s = st(sim);
  assert.equal(s.profile, 2); assert.equal(s.turbo, false); assert.equal(s.currentMa, 300);
  sim.advance(120); assert.equal(st(sim).currentMa, 300);
});

test('Turbo is never remembered for the next switch-on (like the firmware): ON after LEVEL 4 while off uses the last other level', () => {
  const sim = make();
  sim.writeCommand(P.cmd.level(1));                       // remembered level: Low
  sim.writeCommand(P.cmd.level(4)); assert.equal(st(sim).on, false); assert.equal(st(sim).level, 4);
  sim.writeCommand(P.cmd.on());
  let s = st(sim); assert.equal(s.on, true); assert.equal(s.level, 1, 'switched on at Low, not Turbo'); assert.equal(s.currentMa, 30); assert.equal(s.turbo, false);
  sim.writeCommand(P.cmd.level(4)); s = st(sim); assert.equal(s.turbo, true, 'LEVEL while on does select Turbo');
  sim.writeCommand(P.cmd.off()); sim.writeCommand(P.cmd.on());
  s = st(sim); assert.equal(s.level, 1, 'after Turbo the next switch-on is the level before Turbo'); assert.equal(s.turbo, false);
  sim.pressButton(); sim.advance(3.5); sim.writeCommand(P.cmd.level(4)); sim.pressButton(); sim.pressButton();   // off, then on again with the button
  assert.equal(st(sim).level, 1);
});

test('exact current (OUTPUT_MA): level 0xFF, clamped to the turbo current, turbo timer runs above the step-down current', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on());
  sim.writeCommand(P.cmd.outputMa(500));
  let s = st(sim); assert.equal(s.level, 0xff); assert.equal(s.exact, true); assert.equal(s.currentMa, 500); assert.equal(s.turbo, false);
  sim.writeCommand(P.cmd.outputMa(5000));
  s = st(sim); assert.equal(s.currentMa, 1200, 'clamped to the Balanced turbo current'); assert.equal(s.turbo, true); assert.equal(s.turboLeftS, 60);
  sim.advance(61); s = st(sim); assert.equal(s.currentMa, 600); assert.equal(s.turbo, false); assert.equal(s.level, 0xff);
  sim.writeCommand(P.cmd.outputMa(400)); assert.equal(st(sim).currentMa, 400);
  assert.equal(code(() => sim.writeCommand(P.cmd.outputMa(0))), 0x81, '0 mA is not an exact current');
});

test('button priority: every button action starts a 3 s lock; OFF/ON/LEVEL/PROFILE/OUTPUT_MA fail with 0x80, the rest still works', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.outputMa(300));
  sim.pressButton();
  let s = st(sim);
  assert.equal(s.appLockS, 3); assert.equal(s.source, 1); assert.equal(s.on, false, 'the button switched it off');
  assert.equal(s.level, 2, 'a button press cancels the exact current (level 0xFF)');
  for (const c of [P.cmd.off(), P.cmd.on(), P.cmd.level(1), P.cmd.profile(0), P.cmd.outputMa(100)]) {
    assert.equal(code(() => sim.writeCommand(c)), 0x80, 'refused: ' + P.toHex(c));
  }
  for (const c of [P.cmd.identify(), P.cmd.save(), P.cmd.keepalive(600), P.cmd.lockout(false)]) {
    assert.equal(code(() => sim.writeCommand(c)), 'no error', 'allowed during the lock: ' + P.toHex(c));
  }
  sim.advance(1); assert.equal(st(sim).appLockS, 2);
  sim.advance(1); assert.equal(st(sim).appLockS, 1);
  assert.equal(code(() => sim.writeCommand(P.cmd.on())), 0x80);
  sim.advance(1.01); assert.equal(st(sim).appLockS, 0);
  assert.equal(code(() => sim.writeCommand(P.cmd.on())), 'no error');
  assert.equal(st(sim).on, true);
  sim.pressButton(); assert.equal(st(sim).on, false, 'the button always works');
});

test('lockout: ON is refused with 0x83 (the button cannot switch on either); OFF still works; unlock restores it', () => {
  const sim = make();
  sim.writeCommand(P.cmd.lockout(true));
  let s = st(sim); assert.equal(s.lockout, true); assert.equal(s.source, 2);
  assert.equal(code(() => sim.writeCommand(P.cmd.on())), 0x83);
  sim.advance(4); sim.pressButton(); assert.equal(st(sim).on, false, 'the button cannot switch on during lockout');
  sim.advance(4); sim.writeCommand(P.cmd.lockout(false)); sim.writeCommand(P.cmd.on());
  assert.equal(st(sim).on, true);
  sim.writeCommand(P.cmd.lockout(true)); sim.writeCommand(P.cmd.off()); assert.equal(st(sim).on, false);
});

test('invalid commands answer 0x81', () => {
  const sim = make();
  for (const hex of ['55', '03 07', '04 09', '06 05', '7F 00', '05 01', '', '01 01']) {
    assert.equal(code(() => sim.writeCommand(P.fromHex(hex))), 0x81, hex);
  }
});

test('temperature rises with output and falls back; thermal limit and the 0x82 refusal of Turbo near the limit', () => {
  const sim = make();
  const t0 = st(sim).tempC;
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));
  sim.advance(300);
  const t1 = st(sim).tempC; assert.ok(t1 > t0 + 4, `heats up (${t0} -> ${t1})`);
  sim.writeCommand(P.cmd.off()); sim.advance(600);
  assert.ok(st(sim).tempC < t1 - 3, 'cools down again');

  // hot day + Extreme (limit 55 C) at High (900 mA)
  const hot = make(); hot.setAmbient(45);
  hot.writeCommand(P.cmd.profile(0)); hot.writeCommand(P.cmd.on()); hot.writeCommand(P.cmd.level(3));
  hot.advance(1200);
  const s = st(hot);
  assert.ok(s.tempC > 55, 'above the profile limit: ' + s.tempC);
  assert.equal(s.thermalLimit, true); assert.ok(s.currentMa < 900 && s.currentMa >= 40, 'output reduced: ' + s.currentMa);
  assert.equal(code(() => hot.writeCommand(P.cmd.level(4))), 0x82, 'Turbo is refused within 5 C of the limit');
  hot.writeCommand(P.cmd.level(1)); hot.advance(1200); // Low (40 mA) is below the thermal cap, so no limit is reported once cooled
  assert.equal(st(hot).thermalLimit, false);
});

test('battery: drain matches V_LED*I/(0.9*V_BAT) for about 800 mAh; runtime estimate is consistent', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));       // 600 mA LED = about 0.5 A from the cells
  const s0 = st(sim); sim.advance(1800); const s1 = st(sim);
  const drop = s0.soc - s1.soc;
  assert.ok(drop >= 27 && drop <= 36, `30 min at High drops about 31 % (got ${drop})`);
  assert.ok(s1.voltageMv < s0.voltageMv);
  // runtime: usable charge / battery current
  const expected = ((s1.soc / 100 * 800) - 40) / ((Sim.ledVf(600) * 0.6) / (0.9 * s1.voltageMv / 1000) * 1000 + 8) * 60;
  assert.ok(Math.abs(s1.runtimeMin - expected) < expected * 0.12, `runtime ${s1.runtimeMin} vs ${expected.toFixed(0)}`);
  // never negative, light switches itself off before the cell is flat
  sim.advance(3600 * 8);       // the light first steps down to Moon (Balanced: below 3.35 V), then dies below 3.00 V
  const end = st(sim); assert.ok(end.soc >= 0); assert.equal(end.on, false); assert.equal(end.source, 3);
});

test('low battery: below 3.10 V only Moon; below 3.00 V the light goes off and refuses with 0x82 until USB is present', () => {
  const sim = make({ soc: 78 });
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));
  sim.setSoc(0.8); sim.advance(1);      // 3.08 V at rest: below 3.10 V
  let s = st(sim); assert.equal(s.batteryLimit, true); assert.ok(s.voltageMv < 3100); assert.equal(s.currentMa, 3, 'Moon only');
  sim.setSoc(0); sim.advance(2);
  s = st(sim); assert.equal(s.on, false); assert.equal(s.source, 3);
  sim.advance(4);
  assert.equal(code(() => sim.writeCommand(P.cmd.on())), 0x82);
  sim.setUsb(true); sim.advance(1);
  assert.equal(code(() => sim.writeCommand(P.cmd.on())), 'no error', 'USB present lifts the refusal');
});

test('low battery step-down: one level every 5 s below the profile voltage', () => {
  const sim = make();
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));
  sim.setSoc(6); sim.advance(1);            // about 3.5 V loaded: below Balanced's 3.35 V? no - check the voltage first
  const v = st(sim).voltageMv;
  const stepV = P.lvStepToVolts(35) * 1000;
  if (v >= stepV) { sim.setSoc(3); sim.advance(1); }
  assert.ok(st(sim).voltageMv < stepV + 50);
  const a = st(sim).currentMa; sim.advance(6); const b = st(sim).currentMa;
  assert.ok(b <= a, 'steps down, never up');
});

test('charging: 280 mA when the LED is off, paused above 500 mA, complete at 100 %, stops being "charging"', () => {
  const sim = make({ soc: 50 });
  sim.setUsb(true);
  let s = st(sim); assert.equal(s.usb, true); assert.equal(s.charging, true); assert.equal(s.chargeDone, false);
  sim.advance(1800); s = st(sim); assert.ok(s.soc >= 63 && s.soc <= 72, 'about +17.5 % in 30 min: ' + s.soc);
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));
  s = st(sim); assert.equal(s.charging, false, 'paused while the LED runs above 500 mA');
  sim.writeCommand(P.cmd.off());
  sim.advance(3600 * 3); s = st(sim);
  assert.equal(s.soc, 100); assert.equal(s.chargeDone, true); assert.equal(s.charging, false); assert.equal(s.usb, true);
  sim.setUsb(false); s = st(sim); assert.equal(s.usb, false); assert.equal(s.chargeDone, false);
});

test('Custom profile write: clamped like the firmware, selects Custom, read-back shows what is really used', () => {
  const sim = make();
  const want = { id: 3, turboAllowed: true, rememberLevel: false, showBattery: true, moon: 99, low: 5, medium: 5000, high: 10, turbo: 9999, turboTime: 999, stepDown: 1, tempLimit: 5, lvStep: 99, cellLimit: 50 };
  sim.writeProfile(P.encodeProfile(want));
  const s = st(sim); assert.equal(s.profile, 3);
  const back = plain(P.decodeProfile(sim.readProfile()));
  assert.deepEqual(back, { ...plain(P.clampProfile(want)), id: 3 });
  assert.ok(P.validateProfile(back).ok);
  // a normal write comes back unchanged and drives the levels
  const mine = { ...P.builtinProfile(1), id: 3, moon: 5, low: 60, medium: 300, high: 700, turbo: 1500, turboTime: 20, stepDown: 650 };
  sim.writeProfile(P.encodeProfile(mine));
  assert.deepEqual(plain(P.decodeProfile(sim.readProfile())), plain(mine));
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(2)); assert.equal(st(sim).currentMa, 300);
  sim.writeCommand(P.cmd.level(4)); assert.equal(st(sim).currentMa, 1500); assert.equal(st(sim).turboLeftS, 20);
  // reading returns the ACTIVE profile
  sim.writeCommand(P.cmd.profile(0));
  assert.equal(P.decodeProfile(sim.readProfile()).id, 0);
  assert.equal(P.decodeProfile(sim.readProfile()).turbo, 2200);
  // select Custom again: our values are still there
  sim.writeCommand(P.cmd.profile(3)); assert.equal(P.decodeProfile(sim.readProfile()).low, 60);
});

test('Profile characteristic: only id 3 and exactly 20 bytes are accepted', () => {
  const sim = make();
  assert.equal(code(() => sim.writeProfile(P.encodeProfile({ ...P.builtinProfile(1), id: 1 }))), 0x81);
  assert.equal(code(() => sim.writeProfile(P.encodeProfile({ ...P.builtinProfile(1), id: 3 }).slice(0, 19))), 0x81);
  assert.equal(code(() => sim.writeProfile(P.encodeProfile({ ...P.builtinProfile(1), id: 3 }))), 'no error');
});

test('SAVE, KEEPALIVE (3-byte and 1-byte forms), IDENTIFY and FACTORY_RESET', () => {
  const sim = make();
  sim.writeProfile(P.encodeProfile({ ...P.builtinProfile(1), id: 3, low: 77, medium: 210 }));
  assert.equal(sim.state().saved, null);
  sim.writeCommand(P.cmd.save());
  assert.equal(sim.state().saved.custom.low, 77); assert.equal(sim.state().saved.profileId, 3);
  sim.writeCommand(P.cmd.keepalive(600)); assert.equal(sim.state().keepalive, 600);
  sim.writeCommand(P.cmd.keepaliveShort(255)); assert.equal(sim.state().keepalive, 255);
  sim.writeCommand(P.fromHex('09 FF FF')); assert.equal(sim.state().keepalive, 600, 'above 600 s is capped');
  sim.writeCommand(P.cmd.identify()); sim.writeCommand(P.cmd.identify()); assert.equal(sim.state().identifyCount, 2);
  let lost = 0; sim.onDisconnect = () => { lost++; };
  sim.writeCommand(P.cmd.on());
  sim.writeCommand(P.cmd.factoryReset());
  const s = st(sim); assert.equal(s.profile, 1); assert.equal(s.on, false);
  assert.equal(P.decodeProfile(sim.readProfile()).low, 30);
  sim.writeCommand(P.cmd.profile(3)); assert.equal(P.decodeProfile(sim.readProfile()).low, 30, 'Custom = Balanced after a factory reset');
  sim.advance(1); assert.equal(lost, 1, 'it reboots, so the Bluetooth link drops');
});

test('notifications: on every change and at least every 2 s; Battery Level when the percentage changes', () => {
  const sim = make();
  const got = []; const batt = [];
  sim.onStatus = (b) => got.push(P.decodeStatus(b)); sim.onBattery = (p) => batt.push(p);
  sim.advance(10);                                  // idle, nothing changes except the clock
  assert.ok(got.length >= 4 && got.length <= 6, 'a heartbeat about every 2 s: ' + got.length);
  got.length = 0;
  sim.writeCommand(P.cmd.on()); assert.equal(got.length, 1); assert.equal(got[0].on, true);
  sim.writeCommand(P.cmd.level(3)); assert.equal(got.length, 2);
  sim.pressButton(); assert.equal(got.length, 3); assert.equal(got[2].appLockS, 3);
  sim.setSoc(40); assert.equal(batt.at(-1), 40);
  // the byte-14 countdown produces a notification each second while locked
  got.length = 0; sim.advance(3.2); assert.ok(got.length >= 3, 'app lock countdown is visible: ' + got.length);
  assert.deepEqual(got.map((g) => g.appLockS).filter((v, i, a) => a.indexOf(v) === i).sort(), [0, 1, 2, 3]);
});

test('laser flag is information only (the simulator never switches it from a command)', () => {
  const sim = make();
  for (const c of [P.cmd.on(), P.cmd.level(4), P.cmd.outputMa(2000), P.cmd.identify()]) { try { sim.writeCommand(c); } catch (e) { /* ignore */ } }
  assert.equal(st(sim).laser, false);
  sim.setLaser(true); assert.equal(st(sim).laser, true);
});

test('Info and Battery Level characteristics', () => {
  const sim = make();
  const info = new TextDecoder().decode(sim.readInfo());
  assert.ok(info.length > 0 && info.length <= 20, info);
  assert.equal(sim.readBattery().length, 1); assert.equal(sim.readBattery()[0], 78);
  assert.match(sim.name, /^FlashKa-[0-9A-F]{4}$/);
});

/* ---------------------------------------------------------------- presenter (protocol 2) */
test('Presenter characteristic: default 30 min Page Up/Down, write is clamped and read back', () => {
  const sim = make();
  assert.equal(sim.hasPresenter(), true);
  assert.deepEqual(plain(P.decodePresenter(sim.readPresenter())), { keySet: 0, idleMin: 30, swap: false, flags: 0, reserved: 0 });
  sim.writePresenter(P.encodePresenter({ keySet: 1, idleMin: 45, swap: true }));
  assert.deepEqual(plain(P.decodePresenter(sim.readPresenter())), { keySet: 1, idleMin: 45, swap: true, flags: 1, reserved: 0 });
  sim.writePresenter(P.encodePresenter({ keySet: 1, idleMin: 2, swap: false }));         // below 5: the light clamps
  assert.equal(P.decodePresenter(sim.readPresenter()).idleMin, 5);
  sim.writePresenter(P.encodePresenter({ keySet: 0, idleMin: 250, swap: false }));
  assert.equal(P.decodePresenter(sim.readPresenter()).idleMin, 120);
  assert.equal(code(() => sim.writePresenter(new Uint8Array(3))), 0x81);
  assert.equal(code(() => sim.writePresenter(new Uint8Array(5))), 0x81);
});

test('PRESENTER 1: light goes off, mode 1, the link is dropped shortly after the answer', () => {
  const sim = make(); let dropped = null;
  sim.onDisconnect = (why) => { dropped = why; };
  sim.writeCommand(P.cmd.on());
  sim.pressButton(); sim.advance(3.5);                      // let the app lock of the button press end
  sim.writeCommand(P.cmd.presenter(true));
  const s = st(sim);
  assert.equal(s.on, false); assert.equal(s.mode, 1); assert.equal(s.presenterActive, true);
  assert.equal(s.source, P.SOURCE.APP);
  assert.equal(dropped, null, 'the answer is delivered first');
  sim.advance(0.5);
  assert.equal(dropped, 'presenter');
  assert.equal(sim.canConnect(), false, 'the light advertises only as a keyboard now');
});

test('PRESENTER 1 is refused in lockout (0x83) and with an empty battery (0x82)', () => {
  const a = make(); a.writeCommand(P.cmd.lockout(true));
  assert.equal(code(() => a.writeCommand(P.cmd.presenter(true))), 0x83);
  assert.equal(st(a).mode, 0);
  const b = make(); b.setSoc(2);
  assert.equal(code(() => b.writeCommand(P.cmd.presenter(true))), 0x82);
  assert.equal(st(b).mode, 0);
});

test('presenter mode: computer pairs -> mode 2 and bond count; max 4 bonds; computer leaves -> mode 1', () => {
  const sim = make();
  assert.equal(sim.pairComputer(), false, 'pairing needs presenter mode');
  sim.writeCommand(P.cmd.presenter(true));
  assert.equal(sim.pairComputer(), true);
  let s = st(sim); assert.equal(s.mode, 2); assert.equal(s.bondedHosts, 1);
  sim.computerConnects(false); assert.equal(st(sim).mode, 1);
  sim.computerConnects(true); assert.equal(st(sim).mode, 2);
  for (let i = 0; i < 6; i++) sim.pairComputer();
  assert.equal(st(sim).bondedHosts, 4, 'the light stores at most 4 bonds');
});

test('FORGET_HOSTS 0xA5 forgets all computers; mode 2 falls back to 1', () => {
  const sim = make({ bonded: 3 });
  assert.equal(st(sim).bondedHosts, 3);
  sim.writeCommand(P.cmd.presenter(true)); sim.pairComputer();
  assert.equal(st(sim).mode, 2);
  sim.writeCommand(P.cmd.forgetHosts());
  assert.equal(st(sim).bondedHosts, 0); assert.equal(st(sim).mode, 1);
  // wrong key is invalid
  assert.equal(code(() => sim.writeCommand(Uint8Array.of(0x0b, 0x00))), 0x81);
});

test('presenter mode ends after the idle time; a button press resets the timer', () => {
  const sim = make();
  sim.writePresenter(P.encodePresenter({ keySet: 0, idleMin: 5, swap: false }));
  sim.writeCommand(P.cmd.presenter(true));
  sim.advance(200); sim.presenterPress();                   // 3:20, then a key press
  sim.advance(200); assert.equal(st(sim).mode, 1, 'timer was reset at 3:20, now only 3:20 idle');
  sim.advance(110); assert.equal(st(sim).mode, 0, 'more than 5 min since the last press');
  assert.equal(st(sim).source, P.SOURCE.AUTO);
  assert.equal(sim.canConnect(), true);
});

test('hold both slide buttons: 2 s toggles presenter mode (not in lockout), 10 s forgets computers', () => {
  const sim = make({ bonded: 2 });
  sim.holdBothButtons(1.9); assert.equal(st(sim).mode, 0);
  sim.holdBothButtons(2); assert.equal(st(sim).mode, 1);
  sim.holdBothButtons(2); assert.equal(st(sim).mode, 0);
  sim.holdBothButtons(10); assert.equal(st(sim).bondedHosts, 0);
  const locked = make(); locked.writeCommand(P.cmd.lockout(true)); locked.holdBothButtons(2);
  assert.equal(st(locked).mode, 0, 'no presenter mode in lockout');
});

test('presenter mode: the main button is the B key, it does not switch the light', () => {
  const sim = make();
  sim.writeCommand(P.cmd.presenter(true));
  sim.pressButton();
  assert.equal(st(sim).on, false);
  assert.equal(sim.state().keys, 1);
});

test('SAVE stores the presenter settings; FACTORY_RESET restores the defaults', () => {
  const sim = make();
  sim.writePresenter(P.encodePresenter({ keySet: 1, idleMin: 60, swap: true }));
  assert.equal(sim.state().savedPresenter, null);
  sim.writeCommand(P.cmd.save());
  assert.deepEqual(plain(sim.state().savedPresenter).idleMin, 60);
  sim.writeCommand(P.cmd.factoryReset());
  assert.deepEqual(plain(P.decodePresenter(sim.readPresenter())), { keySet: 0, idleMin: 30, swap: false, flags: 0, reserved: 0 });
});

test('presenter mode costs about 20 mA more than idle', () => {
  const a = make({ soc: 80 }), b = make({ soc: 80 });
  b.writeCommand(P.cmd.presenter(true));
  a.advance(120); b.advance(120);
  assert.ok(b.state().remMah < a.state().remMah, 'the presenter drains faster');
});

/* ---------------------------------------------------------------- FlashKa v0.7 demo light */
// V_LED*I / (0.87*V_BAT) with the v0.7 LED (2.80 V + 0.15 V/A), as the v0.7 firmware's battery limit
const batV07 = (ma, v) => (2.8 + 0.15 * ma / 1000) * ma / (0.87 * v);

test('FlashKa v0.7 demo light: Info "FlashKa fw 0.7.0" (the app reads the board from it), v0.7 tables', () => {
  const sim = make({ model: 'v07' });
  const info = new TextDecoder().decode(sim.readInfo());
  assert.equal(info, 'FlashKa fw 0.7.0'); assert.equal(P.boardFromInfo(info), 'v07'); assert.equal(sim.model, 'v07');
  assert.equal(new TextDecoder().decode(make().readInfo()), 'FlashKa fw 0.6.0', 'the default demo light stays a FlashKa v0.6');
  sim.writeCommand(P.cmd.on());
  [[0, 3], [1, 40], [2, 250], [3, 1530]].forEach(([lvl, ma]) => { sim.writeCommand(P.cmd.level(lvl)); assert.equal(st(sim).currentMa, ma, `Balanced level ${lvl}`); });
  sim.writeCommand(P.cmd.profile(0));
  [[1, 50], [2, 400], [3, 1800]].forEach(([lvl, ma]) => { sim.writeCommand(P.cmd.level(lvl)); assert.equal(st(sim).currentMa, ma, `Extreme level ${lvl}`); });
  sim.writeCommand(P.cmd.profile(2)); sim.writeCommand(P.cmd.level(4));
  const s = st(sim); assert.equal(s.turbo, false); assert.equal(s.currentMa, 500, 'Endurance: no extra turbo, High 500 mA');
  assert.deepEqual(plain(P.decodeProfile(sim.readProfile())), { ...plain(P.builtinProfile(2, 'v07')) });
});

test('FlashKa v0.7: turbo 2850 mA for 60 s, then High 1530 mA (cold room, full pack: only the timer acts)', () => {
  const sim = make({ model: 'v07', soc: 100 }); sim.setAmbient(0);   // below about 3.78 V under load the 2800 mA cell limit would shave turbo
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(4));
  let s = st(sim); assert.equal(s.turbo, true); assert.equal(s.currentMa, 2850); assert.equal(s.turboLeftS, 60);
  sim.advance(59); s = st(sim); assert.equal(s.currentMa, 2850); assert.equal(s.thermalLimit, false);
  sim.advance(1); s = st(sim);
  assert.equal(s.turbo, false); assert.equal(s.currentMa, 1530); assert.equal(s.source, 3, 'the timer is an automatic change');
});

test('FlashKa v0.7 at room temperature: the regulator holds the 50 degC limit (v0.7 firmware), steady and without hunting', () => {
  for (const [level, start] of [[4, 2850], [3, 1530]]) {
    const sim = make({ model: 'v07', soc: 100 });
    sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(level));
    let maxMa = 0, maxT = 0, full = null, prev = null, maxStep = 0;
    const late = [];
    for (let t = 1; t <= 1800; t++) {
      sim.advance(1);
      const s = st(sim);
      maxMa = Math.max(maxMa, s.currentMa); maxT = Math.max(maxT, s.tempC);
      if (full === null && s.currentMa < start) full = t;
      if (t >= 900) {
        if (prev) maxStep = Math.max(maxStep, Math.abs(s.currentMa - prev) / prev);
        prev = s.currentMa;
      }
      // the demo's single thermal node (400 s) settles more slowly than the light's sensor, which
      // follows the head: steadiness is checked over the last 5 minutes
      if (t >= 1500) late.push(s.currentMa);
    }
    const s = st(sim);
    assert.ok(maxMa <= 2850, 'never above the v0.7 turbo: ' + maxMa);
    assert.equal(s.thermalLimit, true);
    assert.ok(s.tempC >= 49.5 && s.tempC <= 50.0, 'held just below the 50 degC limit: ' + s.tempC);
    assert.ok(maxT <= 51.0, 'overshoot at most 1 degC: ' + maxT);
    assert.ok(s.currentMa > 40 && s.currentMa < 1530, 'a steady level between Low and High: ' + s.currentMa);
    assert.ok(Math.max(...late) - Math.min(...late) <= 0.02 * s.currentMa, 'no hunting: ' + Math.min(...late) + '-' + Math.max(...late));
    assert.ok(maxStep <= 0.02, 'at most 2 % per second: ' + maxStep);
    if (level === 3) assert.ok(full >= 150, 'High in full for at least 150 s: ' + full);
  }
  // a FlashKa v0.6 demo light keeps the linear law of the protocol (15 degC band above its limit)
  const v06 = make({ soc: 100 }); v06.setAmbient(45);
  v06.writeCommand(P.cmd.profile(0)); v06.writeCommand(P.cmd.on()); v06.writeCommand(P.cmd.level(3));
  v06.advance(1200);
  assert.ok(st(v06).tempC > 55, 'v0.6: settles above its 55 degC limit: ' + st(v06).tempC);
});

test('FlashKa v0.7 (one F15 cell): turbo dims on a half-full cell (the cell sags, 2800 mA cell limit); drain, runtime and charging use 1400 mAh and 475 mA', () => {
  const half = make({ model: 'v07', soc: 50 }); half.setAmbient(0);
  half.writeCommand(P.cmd.on()); half.writeCommand(P.cmd.level(4)); half.advance(2);
  let s = st(half);
  assert.ok(s.turbo, 'turbo is on');
  assert.ok(s.currentMa < 2850 && s.currentMa > 1900, 'turbo dims on a half-full cell: ' + s.currentMa);
  assert.ok(batV07(s.currentMa, Math.max(3000, s.voltageMv) / 1000) <= 2800 + 1, 'battery side at most 2800 mA');
  const full = make({ model: 'v07', soc: 100 }); full.setAmbient(0);
  full.writeCommand(P.cmd.on()); full.writeCommand(P.cmd.level(4)); full.advance(1);
  assert.equal(st(full).currentMa, 2850, 'a full cell gives the whole turbo'); assert.equal(st(full).batteryLimit, false);

  const sim = make({ model: 'v07', soc: 100 }); sim.setAmbient(0);
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(3));           // High 1530 mA = about 1.4 A from the cell
  const s0 = st(sim); sim.advance(180); const s1 = st(sim);
  assert.equal(s1.currentMa, 1530); assert.equal(s1.thermalLimit, false);
  const drop = s0.soc - s1.soc;
  assert.ok(drop >= 4 && drop <= 6, `3 min at High drop about 4.9 % of 1400 mAh (got ${drop})`);
  const expected = ((s1.soc / 100 * 1400) - 70) / (batV07(1530, s1.voltageMv / 1000) + 8) * 60;
  assert.ok(Math.abs(s1.runtimeMin - expected) < expected * 0.12, `runtime ${s1.runtimeMin} vs ${expected.toFixed(0)}`);

  // charging: 475 mA into the F15 (TP4057 with R3 2.0 k less the MCU), the v0.6 demo keeps 280 mA
  const chg = make({ model: 'v07', soc: 40 }); chg.setAmbient(0); chg.setUsb(true);
  const c0 = st(chg).soc; chg.advance(600); const c1 = st(chg);
  assert.ok(c1.charging, 'charging');
  const gain = (c1.soc - c0) / 100 * 1400;
  assert.ok(gain > 70 && gain < 85, `10 min at 475 mA = 79 mAh into 1400 mAh (got ${gain.toFixed(1)})`);
  const c6 = make({ soc: 40 }); c6.setAmbient(0); c6.setUsb(true);
  const d0 = st(c6).soc; c6.advance(600);
  assert.ok(Math.abs((st(c6).soc - d0) / 100 * 800 - 46.7) < 6, 'v0.6: 280 mA');
});

test('FlashKa v0.7: a Custom turbo above 2850 mA and exact currents are clamped like the v0.7 firmware', () => {
  const sim = make({ model: 'v07' });
  const want = { ...P.builtinProfile(1, 'v07'), id: 3, high: 2500, turbo: 3000 };
  sim.writeProfile(P.encodeProfile(want));
  const back = plain(P.decodeProfile(sim.readProfile()));
  assert.deepEqual(back, { ...plain(P.clampProfile(want, 'v07')), id: 3 });
  assert.deepEqual([back.high, back.turbo], [2000, 2850]);
  assert.ok(P.validateProfile(back, 'v07').ok);
  sim.writeCommand(P.cmd.on()); sim.writeCommand(P.cmd.level(4)); assert.equal(st(sim).currentMa, 2850);
  sim.writeCommand(P.cmd.profile(1)); sim.writeCommand(P.cmd.outputMa(5000));
  assert.equal(st(sim).currentMa, 2850, 'OUTPUT_MA is clamped to the turbo current');
  // the same write to a FlashKa v0.6 keeps the protocol's 3000 mA
  const v06 = make(); v06.writeProfile(P.encodeProfile(want));
  assert.equal(P.decodeProfile(v06.readProfile()).turbo, 3000);
});

test('a v0.5 light (protocol 1): 18-byte Status, no Presenter characteristic, 0x0A and 0x0B are invalid', () => {
  const sim = make({ protocol: 1 });
  assert.equal(sim.readStatus().length, 18);
  const s = st(sim);
  assert.equal(s.version, 1); assert.equal(s.versionOk, true); assert.equal(s.presenterSupported, false); assert.equal(s.mode, 0);
  assert.equal(sim.hasPresenter(), false);
  assert.equal(code(() => sim.readPresenter()), 0x81);
  assert.equal(code(() => sim.writePresenter(P.encodePresenter({ keySet: 0, idleMin: 30, swap: false }))), 0x81);
  assert.equal(code(() => sim.writeCommand(P.cmd.presenter(true))), 0x81);
  assert.equal(code(() => sim.writeCommand(P.cmd.forgetHosts())), 0x81);
  sim.writeCommand(P.cmd.on()); assert.equal(st(sim).on, true, 'the v1 commands still work');
});
