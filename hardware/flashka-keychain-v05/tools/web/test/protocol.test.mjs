// SPDX-License-Identifier: MIT OR Apache-2.0
// Unit tests for the Aurora++ BLE protocol v1 encoder/decoder (docs/ble_protocol.md).
// The byte vectors below were worked out BY HAND from the tables in the document
// (little-endian, offsets as listed), not produced by the code under test.
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadAppModules, plain } from './helpers/load-app.mjs';

const { P } = loadAppModules();
const hex = (b) => P.toHex(b);

/* ------------------------------------------------------------------ constants */
test('UUIDs, lengths and opcodes match the document', () => {
  assert.equal(P.UUID.SERVICE, 'a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13');
  assert.equal(P.UUID.STATUS, 'a7d40002-3c5e-4b8a-9f61-2d0c8e5b7a13');
  assert.equal(P.UUID.COMMAND, 'a7d40003-3c5e-4b8a-9f61-2d0c8e5b7a13');
  assert.equal(P.UUID.PROFILE, 'a7d40004-3c5e-4b8a-9f61-2d0c8e5b7a13');
  assert.equal(P.UUID.INFO, 'a7d40005-3c5e-4b8a-9f61-2d0c8e5b7a13');
  assert.equal(P.UUID.BATTERY_SERVICE, 'battery_service');
  assert.equal(P.UUID.BATTERY_LEVEL, 'battery_level');
  assert.equal(P.VERSION, 1);
  assert.equal(P.STATUS_LEN, 18);
  assert.equal(P.PROFILE_LEN, 20);
  assert.deepEqual(plain(P.OP), { OFF: 1, ON: 2, LEVEL: 3, PROFILE: 4, OUTPUT_MA: 5, LOCKOUT: 6, IDENTIFY: 7, SAVE: 8, KEEPALIVE: 9, FACTORY_RESET: 0x7f });
  assert.deepEqual(plain(P.ATT), { BUTTON_PRIORITY: 0x80, INVALID: 0x81, PROTECTION: 0x82, LOCKOUT: 0x83 });
  assert.deepEqual(plain(P.FLAG), { ON: 1, TURBO: 2, CHARGING: 4, CHARGE_DONE: 8, USB: 16, LOCKOUT: 32, THERMAL: 64, BATTERY_LIMIT: 128 });
  assert.deepEqual(plain(P.PFLAG), { TURBO_ALLOWED: 1, REMEMBER_LEVEL: 2, SHOW_BATTERY: 4 });
  assert.deepEqual(plain(P.PROFILE_NAMES), ['Extreme', 'Balanced', 'Endurance', 'Custom']);
  assert.deepEqual(plain(P.LEVEL_NAMES), ['Moon', 'Low', 'Medium', 'High', 'Turbo']);
});

/* --------------------------------------------------------------------- Status */
// Vector S1: light on in Turbo, USB present, Balanced, 1200 mA, 3987 mV, 78 %, 31.4 C, 47 s turbo left,
// last source = app, no app lock, runtime 95 min, laser off
//   0:01  1:flags 0x13 (bit0 on + bit1 turbo + bit4 usb)  2:01  3:04  4-5:1200=0x04B0->B0 04  6-7:3987=0x0F93->93 0F
//   8:78=0x4E  9-10:314=0x013A->3A 01  11-12:47=0x002F->2F 00  13:02  14:00  15-16:95=0x005F->5F 00  17:00
const S1_HEX = '01 13 01 04 B0 04 93 0F 4E 3A 01 2F 00 02 00 5F 00 00';
const S1 = {
  version: 1, versionOk: true, flags: 0x13,
  on: true, turbo: true, charging: false, chargeDone: false, usb: true, lockout: false, thermalLimit: false, batteryLimit: false,
  profile: 1, level: 4, exact: false, currentMa: 1200, voltageMv: 3987, soc: 78, tempDeci: 314, tempC: 31.4,
  turboLeftS: 47, source: 2, appLockS: 0, runtimeMin: 95, laser: false
};
// Vector S2: every flag bit set, Custom, exact current (0xFF), 600 mA, 3300 mV, 5 %, -5.5 C (-55 = 0xFFC9),
// no turbo time, last source = button, 3 s app lock, runtime unknown (0xFFFF), laser on
const S2_HEX = '01 FF 03 FF 58 02 E4 0C 05 C9 FF 00 00 01 03 FF FF 01';
const S2 = {
  version: 1, versionOk: true, flags: 0xff,
  on: true, turbo: true, charging: true, chargeDone: true, usb: true, lockout: true, thermalLimit: true, batteryLimit: true,
  profile: 3, level: 0xff, exact: true, currentMa: 600, voltageMv: 3300, soc: 5, tempDeci: -55, tempC: -5.5,
  turboLeftS: 0, source: 1, appLockS: 3, runtimeMin: null, laser: true
};
// Vector S3: light off, Extreme, Moon, everything else zero, 4.20 V (0x1068), 100 %, 0.0 C
const S3_HEX = '01 00 00 00 00 00 68 10 64 00 00 00 00 00 00 FF FF 00';

test('decodeStatus: worked-out vectors', () => {
  assert.deepEqual(plain(P.decodeStatus(P.fromHex(S1_HEX))), S1);
  assert.deepEqual(plain(P.decodeStatus(P.fromHex(S2_HEX))), S2);
  const s3 = plain(P.decodeStatus(P.fromHex(S3_HEX)));
  assert.equal(s3.voltageMv, 4200);
  assert.equal(s3.soc, 100);
  assert.equal(s3.on, false);
  assert.equal(s3.runtimeMin, null);
  assert.equal(s3.tempC, 0);
});

test('encodeStatus: the same vectors in the other direction', () => {
  assert.equal(hex(P.encodeStatus(S1)), S1_HEX);
  assert.equal(hex(P.encodeStatus(S2)), S2_HEX);
  // boolean form (no raw flags) gives the same bytes
  const noFlags = { ...S1 }; delete noFlags.flags; delete noFlags.tempDeci;
  assert.equal(hex(P.encodeStatus(noFlags)), S1_HEX);
});

test('decodeStatus accepts DataView, ArrayBuffer, Uint8Array and arrays (what Web Bluetooth hands out)', () => {
  const bytes = Uint8Array.from(P.fromHex(S1_HEX));
  const dv = new DataView(bytes.buffer);
  assert.equal(P.decodeStatus(dv).currentMa, 1200);
  assert.equal(P.decodeStatus(bytes.buffer).soc, 78);
  assert.equal(P.decodeStatus(bytes).tempC, 31.4);
  assert.equal(P.decodeStatus(Array.from(bytes)).turboLeftS, 47);
  // a DataView that is a window into a bigger buffer
  const big = new Uint8Array(40); big.set(bytes, 11);
  assert.equal(P.decodeStatus(new DataView(big.buffer, 11, 18)).voltageMv, 3987);
});

test('decodeStatus: short packet is an error, longer packet is tolerated, other versions are flagged', () => {
  assert.throws(() => P.decodeStatus(new Uint8Array(17)), (e) => e.name === 'ProtocolError');
  const long = new Uint8Array(20); long.set(P.fromHex(S1_HEX));
  assert.equal(P.decodeStatus(long).soc, 78);
  const v2 = Uint8Array.from(P.fromHex(S1_HEX)); v2[0] = 2;
  const s = P.decodeStatus(v2);
  assert.equal(s.version, 2); assert.equal(s.versionOk, false);
});

test('status: each flag bit maps to its own field', () => {
  const names = ['on', 'turbo', 'charging', 'chargeDone', 'usb', 'lockout', 'thermalLimit', 'batteryLimit'];
  names.forEach((name, bit) => {
    const b = new Uint8Array(18); b[0] = 1; b[1] = 1 << bit;
    const s = P.decodeStatus(b);
    names.forEach((n) => assert.equal(s[n], n === name, `bit ${bit} -> ${name}, checking ${n}`));
  });
});

test('status: temperature is a signed 0.1 C value, runtime 0xFFFF means unknown', () => {
  const mk = (t) => { const b = new Uint8Array(18); b[0] = 1; b[9] = t & 0xff; b[10] = (t >> 8) & 0xff; return b; };
  assert.equal(P.decodeStatus(mk(0x7fff)).tempC, 3276.7);
  assert.equal(P.decodeStatus(mk(0x8000)).tempC, -3276.8);
  assert.equal(P.decodeStatus(mk(0xffff)).tempC, -0.1);
  assert.equal(P.decodeStatus(mk(250)).tempC, 25);
  const rt = new Uint8Array(18); rt[0] = 1; rt[15] = 0xfe; rt[16] = 0xff;
  assert.equal(P.decodeStatus(rt).runtimeMin, 0xfffe);
});

test('encodeStatus validates ranges', () => {
  assert.throws(() => P.encodeStatus({ ...S1, soc: 256 }), (e) => e.name === 'RangeError');
  assert.throws(() => P.encodeStatus({ ...S1, voltageMv: 70000 }), (e) => e.name === 'RangeError');
  assert.throws(() => P.encodeStatus({ ...S1, tempDeci: 40000 }), (e) => e.name === 'RangeError');
  assert.throws(() => P.encodeStatus({ ...S1, currentMa: 1.5 }), (e) => e.name === 'RangeError');
});

/* -------------------------------------------------------------------- Profile */
// Vector PV1 = the Balanced numbers written as a Custom profile (id 3), flags turbo-allowed + remember-level
//   0:03  1:0x03  2-3:3  4-5:30=1E  6-7:200=C8  8-9:600=0x0258->58 02  10-11:1200=0x04B0->B0 04
//   12-13:60=3C  14-15:600->58 02  16:50=0x32  17:35=0x23 (3.35 V)  18-19:1600=0x0640->40 06
const PV1_HEX = '03 03 03 00 1E 00 C8 00 58 02 B0 04 3C 00 58 02 32 23 40 06';
const PV1 = { id: 3, turboAllowed: true, rememberLevel: true, showBattery: false, moon: 3, low: 30, medium: 200, high: 600, turbo: 1200, turboTime: 60, stepDown: 600, tempLimit: 50, lvStep: 35, cellLimit: 1600 };
// Vector PV2 = Extreme with all three flags: 3/40/250/900 mA, Turbo 2200 mA 45 s, step-down 900, 55 C, 3.30 V, 2600 mA
//   900=0x0384->84 03  2200=0x0898->98 08  45=2D  55=0x37  30=0x1E  2600=0x0A28->28 0A  250=FA
const PV2_HEX = '00 07 03 00 28 00 FA 00 84 03 98 08 2D 00 84 03 37 1E 28 0A';
const PV2 = { id: 0, turboAllowed: true, rememberLevel: true, showBattery: true, moon: 3, low: 40, medium: 250, high: 900, turbo: 2200, turboTime: 45, stepDown: 900, tempLimit: 55, lvStep: 30, cellLimit: 2600 };

test('Profile: encode and decode the worked-out vectors (20 bytes, little-endian)', () => {
  assert.equal(P.PROFILE_LEN, 20);
  assert.equal(hex(P.encodeProfile(PV1)), PV1_HEX);
  assert.equal(hex(P.encodeProfile(PV2)), PV2_HEX);
  assert.deepEqual(plain(P.decodeProfile(P.fromHex(PV1_HEX))), PV1);
  assert.deepEqual(plain(P.decodeProfile(P.fromHex(PV2_HEX))), PV2);
  assert.throws(() => P.decodeProfile(new Uint8Array(19)), (e) => e.name === 'ProtocolError');
});

test('Profile flags: bit0 turbo allowed, bit1 remember level, bit2 show battery', () => {
  const base = { ...PV1, turboAllowed: false, rememberLevel: false, showBattery: false };
  assert.equal(P.encodeProfile({ ...base, turboAllowed: true })[1], 1);
  assert.equal(P.encodeProfile({ ...base, rememberLevel: true })[1], 2);
  assert.equal(P.encodeProfile({ ...base, showBattery: true })[1], 4);
  const d = P.decodeProfile(Uint8Array.from(P.fromHex(PV1_HEX).map((v, i) => (i === 1 ? 0x05 : v))));
  assert.equal(d.turboAllowed, true); assert.equal(d.rememberLevel, false); assert.equal(d.showBattery, true);
});

test('low-voltage step-down: 10 mV steps above 3.00 V (30 -> 3.30 V)', () => {
  assert.equal(P.lvStepToVolts(30), 3.3);
  assert.equal(P.lvStepToVolts(10), 3.1);
  assert.equal(P.lvStepToVolts(60), 3.6);
  assert.equal(P.voltsToLvStep(3.35), 35);
  assert.equal(P.voltsToLvStep(3.1), 10);
  assert.equal(P.voltsToLvStep(3.6), 60);
});

test('built-in profile table matches section 5.1', () => {
  const doc = {
    Extreme:   { moon: 3, low: 40, medium: 250, high: 900, turbo: 2200, turboTime: 45, stepDown: 900, tempLimit: 55, lvStep: 30, cellLimit: 2600 },
    Balanced:  { moon: 3, low: 30, medium: 200, high: 600, turbo: 1200, turboTime: 60, stepDown: 600, tempLimit: 50, lvStep: 35, cellLimit: 1600 },
    Endurance: { moon: 2, low: 15, medium: 100, high: 300, turboTime: 0, tempLimit: 45, lvStep: 40, cellLimit: 800 }
  };
  Object.entries(doc).forEach(([name, want], id) => {
    const got = plain(P.builtinProfile(id));
    assert.equal(got.id, id, name);
    Object.entries(want).forEach(([k, v]) => assert.equal(got[k], v, `${name}.${k}`));
    assert.ok(P.validateProfile(got).ok, `${name} passes the range check`);
  });
  const custom = plain(P.builtinProfile(3));
  assert.equal(custom.id, 3);
  Object.entries(doc.Balanced).forEach(([k, v]) => assert.equal(custom[k], v, `Custom default = Balanced (${k})`));
  // Endurance: "no overdrive" - turbo equals High
  assert.equal(P.builtinProfile(2).turbo, P.builtinProfile(2).high);
});

test('hasTurbo follows the firmware rule: flag set, time > 0 and turbo current above High', () => {
  const b = P.builtinProfile(1);
  assert.equal(P.hasTurbo(b), true);
  assert.equal(P.hasTurbo(P.builtinProfile(0)), true);
  assert.equal(P.hasTurbo(P.builtinProfile(2)), false, 'Endurance: turbo = High');
  assert.equal(P.hasTurbo({ ...b, turboAllowed: false }), false);
  assert.equal(P.hasTurbo({ ...b, turboTime: 0 }), false);
  assert.equal(P.hasTurbo({ ...b, turbo: b.high }), false);
  assert.match(P.describeProfile(P.builtinProfile(2)), /no extra Turbo/);
  assert.match(P.describeProfile(b), /Turbo 1200 mA for 60 s/);
});

test('profile ranges from section 5 (including the fields that depend on each other)', () => {
  const ok = (p) => P.validateProfile(p);
  assert.ok(ok(PV1).ok);
  const cases = [
    ['moon', 0, false], ['moon', 1, true], ['moon', 50, true], ['moon', 51, false],
    ['low', 300, true], ['low', 301, false], ['low', 2, false],       // Low must be >= Moon (3)
    ['medium', 1000, true], ['medium', 1001, false], ['medium', 29, false],
    ['high', 2000, true], ['high', 2001, false], ['high', 199, false],
    ['turbo', 3000, true], ['turbo', 3001, false], ['turbo', 599, false],
    ['turboTime', 0, true], ['turboTime', 300, true], ['turboTime', 301, false], ['turboTime', -1, false],
    ['stepDown', 30, true], ['stepDown', 29, false], ['stepDown', 600, true], ['stepDown', 601, false],   // Low..High
    ['tempLimit', 40, true], ['tempLimit', 39, false], ['tempLimit', 70, true], ['tempLimit', 71, false],
    ['lvStep', 10, true], ['lvStep', 9, false], ['lvStep', 60, true], ['lvStep', 61, false],
    ['cellLimit', 200, true], ['cellLimit', 199, false], ['cellLimit', 3000, true], ['cellLimit', 3001, false]
  ];
  cases.forEach(([k, v, valid]) => {
    const r = ok({ ...PV1, [k]: v });
    assert.equal(!(k in r.errors), valid, `${k}=${v} should be ${valid ? 'valid' : 'invalid'}`);
  });
  assert.ok('moon' in ok({ ...PV1, moon: NaN }).errors, 'NaN is not a number');
  assert.ok('moon' in ok({ ...PV1, moon: 2.5 }).errors, 'fractions are refused');
  // the message names the neighbour that sets the limit
  assert.match(ok({ ...PV1, medium: 20 }).errors.medium, /Low/);
  assert.match(ok({ ...PV1, stepDown: 700 }).errors.stepDown, /High/);
});

test('one wrong number is flagged once: a neighbour only sets a limit while its own value is valid', () => {
  const keys = (patch) => Object.keys(P.validateProfile({ ...PV1, ...patch }).errors).sort();
  assert.deepEqual(keys({ low: 999 }), ['low'], 'Medium and Step-down are not blamed for a wrong Low');
  assert.deepEqual(keys({ moon: 99 }), ['moon'], 'Low is not blamed for a wrong Moon');
  assert.deepEqual(keys({ high: 5000 }), ['high'], 'Turbo and Step-down are not blamed for a wrong High');
  assert.deepEqual(keys({ medium: 1500 }), ['medium']);
  // with a valid neighbour the conflict IS reported, on the field that is out of order
  assert.deepEqual(keys({ low: 60, medium: 50 }), ['medium']);
  assert.deepEqual(keys({ high: 150 }), ['high'], 'High below Medium is flagged on High only');
  assert.deepEqual(keys({ high: 400 }), ['stepDown'], 'a valid High of 400 makes the Step-down of 600 too high');
  assert.deepEqual(keys({ turbo: 500 }), ['turbo']);
  // the shown limits follow the same rule
  const b = P.profileBounds({ ...PV1, low: 999 });
  assert.equal(b.medium.min, 1); assert.equal(b.stepDown.min, 1);
  assert.equal(P.profileBounds(PV1).medium.min, 30);
  assert.deepEqual(plain(P.profileBounds(PV1).stepDown), { min: 30, max: 600, minFrom: 'low', maxFrom: 'high' });
});

test('clampProfile does what the document says the firmware does', () => {
  const wild = { ...PV1, moon: 99, low: 5, medium: 5000, high: 10, turbo: 9999, turboTime: 999, stepDown: 1, tempLimit: 5, lvStep: 99, cellLimit: 50 };
  const c = plain(P.clampProfile(wild));
  assert.deepEqual([c.moon, c.low, c.medium, c.high, c.turbo], [50, 50, 1000, 1000, 3000]);
  assert.equal(c.turboTime, 300);
  assert.equal(c.stepDown, 50);        // clamped into Low..High = 50..1000
  assert.equal(c.tempLimit, 40);
  assert.equal(c.lvStep, 60);
  assert.equal(c.cellLimit, 200);
  assert.ok(P.validateProfile(c).ok);
});

/* ------------------------------------------------------------------- Commands */
test('command encoder: every opcode, worked out from the table in section 4', () => {
  assert.equal(hex(P.cmd.off()), '01');
  assert.equal(hex(P.cmd.on()), '02');
  assert.equal(hex(P.cmd.level(0)), '03 00');
  assert.equal(hex(P.cmd.level(4)), '03 04');
  assert.equal(hex(P.cmd.profile(0)), '04 00');
  assert.equal(hex(P.cmd.profile(3)), '04 03');
  assert.equal(hex(P.cmd.outputMa(750)), '05 EE 02');      // 750 = 0x02EE little-endian
  assert.equal(hex(P.cmd.outputMa(1)), '05 01 00');
  assert.equal(hex(P.cmd.outputMa(3000)), '05 B8 0B');     // 3000 = 0x0BB8
  assert.equal(hex(P.cmd.lockout(true)), '06 01');
  assert.equal(hex(P.cmd.lockout(false)), '06 00');
  assert.equal(hex(P.cmd.identify()), '07');
  assert.equal(hex(P.cmd.save()), '08');
  assert.equal(hex(P.cmd.factoryReset()), '7F A5');
  // all fit the 1-3 byte limit of the Command characteristic
  [P.cmd.off(), P.cmd.level(2), P.cmd.outputMa(2200), P.cmd.factoryReset()].forEach((b) => assert.ok(b.length >= 1 && b.length <= 3));
});

test('KEEPALIVE: the document says "u8 seconds" but also "max 600 s" - the one-byte form is tried first, the 3-byte form only for > 255 s', () => {
  assert.equal(hex(P.cmd.keepalive(600)), '09 58 02');       // 600 = 0x0258
  assert.equal(hex(P.cmd.keepalive(120)), '09 78 00');
  assert.equal(hex(P.cmd.keepaliveShort(255)), '09 FF');
  const attempts = P.cmd.keepaliveAttempts(600);
  assert.equal(attempts.length, 2);
  assert.equal(hex(attempts[0].bytes), '09 FF'); assert.equal(attempts[0].seconds, 255);   // what the table literally says
  assert.equal(hex(attempts[1].bytes), '09 58 02'); assert.equal(attempts[1].seconds, 600);
  const small = P.cmd.keepaliveAttempts(100);
  assert.equal(small.length, 1, 'no wide form is needed up to 255 s');
  assert.equal(hex(small[0].bytes), '09 64'); assert.equal(small[0].seconds, 100);
  assert.throws(() => P.cmd.keepalive(601), (e) => e.name === 'RangeError');
  assert.throws(() => P.cmd.keepaliveShort(256), (e) => e.name === 'RangeError');
  assert.throws(() => P.cmd.keepaliveAttempts(601), (e) => e.name === 'RangeError');
});

test('command encoder rejects arguments outside the document', () => {
  for (const f of [() => P.cmd.level(5), () => P.cmd.level(-1), () => P.cmd.level(1.5), () => P.cmd.profile(4), () => P.cmd.outputMa(65536), () => P.cmd.outputMa(-1), () => P.cmd.outputMa(NaN)]) {
    assert.throws(f, (e) => e.name === 'RangeError');
  }
});

test('decodeCommand reads every encoded command back (used by the demo flashlight)', () => {
  assert.deepEqual(plain(P.decodeCommand(P.cmd.off())), { op: 1, name: 'OFF' });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.on())), { op: 2, name: 'ON' });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.level(3))), { op: 3, name: 'LEVEL', level: 3 });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.profile(2))), { op: 4, name: 'PROFILE', profile: 2 });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.outputMa(750))), { op: 5, name: 'OUTPUT_MA', ma: 750 });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.lockout(true))), { op: 6, name: 'LOCKOUT', on: true });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.identify())), { op: 7, name: 'IDENTIFY' });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.save())), { op: 8, name: 'SAVE' });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.keepalive(600))), { op: 9, name: 'KEEPALIVE', seconds: 600, wide: true });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.keepaliveShort(30))), { op: 9, name: 'KEEPALIVE', seconds: 30, wide: false });
  assert.deepEqual(plain(P.decodeCommand(P.cmd.factoryReset())), { op: 0x7f, name: 'FACTORY_RESET' });
});

test('decodeCommand: invalid commands are ProtocolError with ATT code 0x81', () => {
  const bad = ['', '55', '03', '03 05', '04 04', '06 02', '01 00', '05 10', '7F 00', '7F', '03 00 00 00', '09'];
  bad.forEach((h) => {
    assert.throws(() => P.decodeCommand(P.fromHex(h)), (e) => e.name === 'ProtocolError' && e.attCode === 0x81, `"${h}" must be invalid`);
  });
});

/* ---------------------------------------------------------------- ATT errors */
test('ATT error codes 0x80..0x83 are pulled out of browser errors, whatever shape they have', () => {
  const E = (msg, name = 'NetworkError') => new DOMException(msg, name);
  const yes = [
    [E('Operation failed with ATT error: 0x80'), 0x80],
    [E('GATT operation failed: ATT error 0x81'), 0x81],
    [E('GATT Error: Unknown. (ATT error 0x82)'), 0x82],
    [E('att_ecode=0x83'), 0x83],
    [E('ATT error 0X83'), 0x83],
    [E('Write failed with status 0x0080'), 0x80],
    [E('ATT error: 128'), 0x80],
    [E('GATT_ERROR (129)'), 0x81],
    [E('Error Domain=CBATTErrorDomain Code=130 "Unknown ATT error."'), 0x82],
    [E('write failed, status 131'), 0x83],
    [E('error code: 128'), 0x80],
    [{ message: 'oops', attErrorCode: 0x83 }, 0x83],
    [{ message: 'oops', errorCode: 130 }, 0x82],
    [{ message: 'oops', cause: E('ATT error 0x80') }, 0x80],
    [{ message: 'outer', cause: { message: 'inner', cause: { message: 'ATT error: 0x81' } } }, 0x81],
    [new Error('GATT operation failed (0x80)'), 0x80],
    ['ATT error 0x82', 0x82],
    [0x83, 0x83]
  ];
  yes.forEach(([err, want]) => assert.equal(P.attErrorCode(err), want, JSON.stringify(err && err.message ? err.message : err)));
  const no = [
    E('GATT operation failed for unknown reason.'),
    E('GATT Error: Not supported.'),
    E('GATT Server is disconnected. Cannot perform GATT operations.'),
    E('User cancelled the requestDevice() chooser.', 'NotFoundError'),
    E('Operation failed with ATT error: 0x0e'),      // "unlikely error", not one of ours
    E('ATT error: 0x9F'),
    E('error 19'),
    E('ATT error 0x8012'),
    E('status 1280'),
    E('error code: 127'),
    E('error code: 132'),
    new Error('timeout after 128 ms'),
    { message: 'nothing here' }, null, undefined, 42, 0x7f, 0x84, {}
  ];
  no.forEach((err) => assert.equal(P.attErrorCode(err), null, JSON.stringify(err && err.message ? err.message : err)));
});

test('friendly messages for 0x80, 0x81, 0x82, 0x83', () => {
  const x = (code) => P.explainError(new DOMException('Operation failed with ATT error: 0x' + code.toString(16), 'NetworkError'), null);
  assert.equal(x(0x80).kind, 'priority'); assert.match(x(0x80).message, /button/i); assert.match(x(0x80).message, /3 seconds/);
  assert.equal(x(0x81).kind, 'invalid');
  assert.equal(x(0x82).kind, 'protection'); assert.match(x(0x82).message, /battery|hot/i);
  assert.equal(x(0x83).kind, 'lockout'); assert.match(x(0x83).message, /lock/i);
  [0x80, 0x81, 0x82, 0x83].forEach((c) => { assert.equal(x(c).code, c); assert.equal(x(c).guessed, false); });
});

test('when the browser hides the ATT code, the last Status is used to guess - and says it is a guess', () => {
  const unknown = new DOMException('GATT operation failed for unknown reason.', 'NetworkError');
  const base = plain(P.decodeStatus(P.fromHex(S1_HEX)));
  let e = P.explainError(unknown, { ...base, appLockS: 2 });
  assert.equal(e.code, 0x80); assert.equal(e.guessed, true); assert.match(e.message, /most likely/);
  e = P.explainError(unknown, { ...base, lockout: true });
  assert.equal(e.code, 0x83); assert.equal(e.guessed, true);
  e = P.explainError(unknown, { ...base, thermalLimit: true });
  assert.equal(e.code, 0x82);
  e = P.explainError(unknown, { ...base, soc: 2 });
  assert.equal(e.code, 0x82);
  e = P.explainError(unknown, base);                  // nothing to go on -> honest generic message with the technical text
  assert.equal(e.code, null); assert.equal(e.kind, 'unknown'); assert.match(e.message, /unknown reason/);
  e = P.explainError(unknown, null);
  assert.equal(e.kind, 'unknown');
  // a real code always wins over the guess
  e = P.explainError(new DOMException('ATT error 0x81', 'NetworkError'), { ...base, appLockS: 2 });
  assert.equal(e.code, 0x81); assert.equal(e.guessed, false);
});

test('a lost connection is reported as such (not as a refused command)', () => {
  const gone = new DOMException('GATT Server is disconnected. Cannot perform GATT operations.', 'NetworkError');
  assert.ok(P.isDisconnectError(gone));
  assert.equal(P.explainError(gone, null).kind, 'disconnected');
  assert.ok(P.isDisconnectError(new DOMException('Device is no longer in range.', 'NetworkError')));
  assert.ok(!P.isDisconnectError(new DOMException('ATT error 0x80', 'NetworkError')));
});

/* --------------------------------------------------------------- misc helpers */
test('fine-brightness slider is logarithmic between 1 mA and the maximum', () => {
  for (const max of [300, 600, 1200, 2200, 3000]) {
    assert.equal(P.sliderToMa(0, max), 1);
    assert.equal(P.sliderToMa(1000, max), max);
    let prev = 0;
    for (let pos = 0; pos <= 1000; pos += 10) {
      const ma = P.sliderToMa(pos, max);
      assert.ok(ma >= prev, `monotonic at ${pos}`);
      assert.ok(ma >= 1 && ma <= max);
      prev = ma;
    }
    [1, 3, 10, 50, 200, max].filter((m) => m <= max).forEach((ma) => {
      const back = P.sliderToMa(P.maToSlider(ma, max), max);
      assert.ok(Math.abs(back - ma) <= Math.max(1, ma * 0.01), `round trip ${ma} of ${max} -> ${back}`);
    });
  }
  assert.equal(P.maToSlider(0, 3000), 0); assert.equal(P.maToSlider(99999, 3000), 1000);
});

test('formatting helpers', () => {
  assert.equal(P.formatRuntime(null), '–');
  assert.equal(P.formatRuntime(45), '45 min');
  assert.equal(P.formatRuntime(60), '1 h');
  assert.equal(P.formatRuntime(95), '1 h 35 min');
  assert.equal(P.formatRuntime(6000), '100+ h');
  assert.equal(P.formatClock(34), '0:34'); assert.equal(P.formatClock(60), '1:00'); assert.equal(P.formatClock(0.2), '0:01'); assert.equal(P.formatClock(-3), '0:00');
  assert.equal(P.formatVolts(3987), '3.99 V');
  assert.equal(P.formatTemp(31.4), '31.4 °C');
  assert.equal(hex(P.fromHex('0a ff 00')), '0A FF 00');
});
