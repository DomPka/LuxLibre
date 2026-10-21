// SPDX-License-Identifier: MIT OR Apache-2.0
/* A fake navigator.bluetooth for the headless tests (injected with addInitScript).
 *
 * Headless Chromium has no Bluetooth, so this stands in for the browser's Web Bluetooth API and talks to
 * the JavaScript flashlight simulator that lives inside flashka-app.html (FlashKaSim). It behaves like Chrome
 * in the ways that matter to the app:
 *  - only ONE GATT operation at a time ("GATT operation already in progress." otherwise - counted in violations)
 *  - every operation takes a little time (latency)
 *  - after a disconnect, operations fail and notifications must be started again
 *  - an ATT application error reaches the page as a DOMException whose text may or may not contain the code
 *
 * Test controls (all on window.__fakeBle): see the object below.
 */
(function () {
  'use strict';
  var fb = window.__fakeBle = {
    deviceName: 'FlashKa-BEEF', soc: 64,
    latency: 25,                 /* ms per GATT operation */
    available: true,             /* navigator.bluetooth.getAvailability() */
    chooser: 'ok',               /* 'ok' | 'cancel' | 'none' (no adapter) */
    errorStyle: 'code',          /* how an ATT error text arrives: 'code' | 'nocode' | 'property' */
    keepaliveMode: 'both',       /* firmware accepts KEEPALIVE as 'u8' (2 bytes), 'u16' (3 bytes) or 'both' */
    versionOverride: 0,          /* non-zero: Status byte 0 */
    protocol: 2,                 /* 1 = behave like a v0.5 light (no Presenter characteristic, 18-byte Status) */
    hidePresenter: false,        /* protocol 2 light whose GATT table lacks the Presenter characteristic */
    hideBattery: false,          /* the Battery Service is missing */
    notificationsOn: true,       /* false: notifications are silently dropped */
    connectFailures: 0,          /* the next N connect() calls fail */
    failNext: null,              /* { kind: 'read'|'write'|'any', match: 'a7d40003', times: 1, name, message } */
    requestCalls: [], connectCount: 0, log: [],
    concurrent: 0, maxConcurrent: 0, violations: 0,
    sim: null, device: null, server: null,
    drop: function () { dropConnection(); },
    press: function () { if (fb.sim) fb.sim.pressButton(); }
  };

  var BATTERY_SVC = '0000180f-0000-1000-8000-00805f9b34fb', BATTERY_CH = '00002a19-0000-1000-8000-00805f9b34fb';
  function canon(u) {
    if (u === 'battery_service') return BATTERY_SVC;
    if (u === 'battery_level') return BATTERY_CH;
    if (typeof u === 'number') return ('0000' + u.toString(16)).slice(-4) + '-0000-1000-8000-00805f9b34fb';
    return String(u).toLowerCase();
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function dv(bytes) { var u = Uint8Array.from(bytes); return new DataView(u.buffer); }
  function copy(buf) {
    if (ArrayBuffer.isView(buf)) return Uint8Array.from(new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength));
    return Uint8Array.from(new Uint8Array(buf));
  }
  function hex(u8) { return Array.prototype.map.call(u8, function (b) { return (b < 16 ? '0' : '') + b.toString(16).toUpperCase(); }).join(' '); }

  var server = null, device = null, chars = {};

  function translate(e) {               /* what the browser makes of an ATT application error */
    var P = window.FlashKaProtocol, code = P ? P.attErrorCode(e) : null;
    if (code === null) return e;
    if (fb.errorStyle === 'nocode') return new DOMException('GATT operation failed for unknown reason.', 'NetworkError');
    if (fb.errorStyle === 'property') { var x = new Error('GATT operation failed'); x.name = 'NetworkError'; x.attErrorCode = code; return x; }
    return new DOMException('GATT operation failed: ATT error 0x' + code.toString(16).toUpperCase(), 'NetworkError');
  }

  async function op(kind, label, fn) {
    fb.concurrent++; if (fb.concurrent > fb.maxConcurrent) fb.maxConcurrent = fb.concurrent;
    try {
      if (fb.concurrent > 1) { fb.violations++; throw new DOMException('GATT operation already in progress.', 'NetworkError'); }
      await sleep(fb.latency);
      if (!server || !server.connected) throw new DOMException('GATT Server is disconnected. Cannot perform GATT operations. (Re)connect first with `device.gatt.connect`.', 'NetworkError');
      var f = fb.failNext;
      if (f && f.times > 0 && (f.kind === 'any' || f.kind === kind) && (!f.match || label.indexOf(f.match) >= 0)) {
        f.times--; throw new DOMException(f.message || 'GATT operation failed for unknown reason.', f.name || 'NetworkError');
      }
      return await fn();
    } finally { fb.concurrent--; }
  }

  function makeChar(uuid, spec) {
    var listeners = [];
    var ch = {
      uuid: uuid, value: null, subscribed: false,
      addEventListener: function (t, fn) { if (t === 'characteristicvaluechanged') listeners.push(fn); },
      removeEventListener: function (t, fn) { listeners = listeners.filter(function (x) { return x !== fn; }); },
      readValue: function () { return op('read', uuid, function () { var v = dv(spec.read()); ch.value = v; fb.log.push({ op: 'read', uuid: uuid.slice(0, 8), hex: hex(new Uint8Array(v.buffer)) }); return v; }); },
      writeValueWithResponse: function (buf) {
        var bytes = copy(buf);
        return op('write', uuid, function () {
          fb.log.push({ op: 'write', uuid: uuid.slice(0, 8), hex: hex(bytes) });
          try { spec.write(bytes); } catch (e) { var t = translate(e); fb.log.push({ op: 'error', uuid: uuid.slice(0, 8), message: String(t.message) }); throw t; }
        });
      },
      startNotifications: function () { return op('subscribe', uuid, function () { ch.subscribed = true; return ch; }); },
      stopNotifications: function () { return op('unsubscribe', uuid, function () { ch.subscribed = false; return ch; }); },
      notify: function (bytes) {
        if (!ch.subscribed || !fb.notificationsOn || !server || !server.connected) return;
        ch.value = dv(bytes);
        listeners.slice().forEach(function (fn) { fn({ target: ch }); });
      }
    };
    ch.writeValue = ch.writeValueWithResponse;
    return ch;
  }

  function ensureSim() {
    if (fb.sim) return fb.sim;
    var Sim = window.FlashKaSim, sim = Sim.createFlashlight({ soc: fb.soc, name: fb.deviceName, protocol: fb.protocol });
    fb.sim = sim;
    var last = performance.now();
    setInterval(function () {            /* the flashlight keeps running whether or not a browser is connected */
      var t = performance.now(), dt = Math.min(1, Math.max(0, (t - last) / 1000)); last = t;
      sim.advance(dt);
    }, 250);
    return sim;
  }

  function buildServices() {
    var sim = ensureSim(), P = window.FlashKaProtocol, U = P.UUID;
    function stat(b) { if (fb.versionOverride) { b = Uint8Array.from(b); b[0] = fb.versionOverride; } return b; }
    chars = {};
    chars.status = makeChar(U.STATUS, { read: function () { return stat(sim.readStatus()); }, write: function () { throw new DOMException('Not permitted', 'NotSupportedError'); } });
    chars.command = makeChar(U.COMMAND, {
      read: function () { throw new DOMException('Reading is not permitted.', 'NotSupportedError'); },
      write: function (bytes) {
        if (bytes[0] === 0x09) {          /* KEEPALIVE: the document says "u8 seconds" and "max 600 s" */
          var ok = fb.keepaliveMode === 'both' || (fb.keepaliveMode === 'u8' && bytes.length === 2) || (fb.keepaliveMode === 'u16' && bytes.length === 3);
          if (!ok) throw P.makeAttError(P.ATT.INVALID);
        }
        sim.writeCommand(bytes);
      }
    });
    chars.profile = makeChar(U.PROFILE, { read: function () { return sim.readProfile(); }, write: function (bytes) { sim.writeProfile(bytes); } });
    chars.presenter = makeChar(U.PRESENTER, { read: function () { return sim.readPresenter(); }, write: function (bytes) { sim.writePresenter(bytes); } });
    chars.info = makeChar(U.INFO, { read: function () { return sim.readInfo(); }, write: function () { throw new DOMException('Not permitted', 'NotSupportedError'); } });
    chars.battery = makeChar(BATTERY_CH, { read: function () { return sim.readBattery(); }, write: function () { throw new DOMException('Not permitted', 'NotSupportedError'); } });
    sim.onStatus = function (b) { chars.status.notify(stat(b)); };
    sim.onBattery = function (pct) { chars.battery.notify([pct]); };
    sim.onDisconnect = function () { dropConnection(); };      /* e.g. the factory-reset reboot */
    var flashka = { uuid: U.SERVICE, getCharacteristic: function (u) {
      return op('discover', 'char ' + u, function () {
        var m = { }; m[canon(U.STATUS)] = chars.status; m[canon(U.COMMAND)] = chars.command; m[canon(U.PROFILE)] = chars.profile; m[canon(U.INFO)] = chars.info;
        if (sim.hasPresenter() && !fb.hidePresenter) m[canon(U.PRESENTER)] = chars.presenter;
        var c = m[canon(u)];
        if (!c) throw new DOMException('No Characteristics matching UUID ' + u + ' found in Service with UUID ' + U.SERVICE + '.', 'NotFoundError');
        return c;
      });
    } };
    var batt = { uuid: BATTERY_SVC, getCharacteristic: function (u) {
      return op('discover', 'char ' + u, function () {
        if (canon(u) !== BATTERY_CH) throw new DOMException('No Characteristics matching UUID found.', 'NotFoundError');
        return chars.battery;
      });
    } };
    return { flashka: flashka, battery: batt };
  }

  function makeDevice() {
    var d = new EventTarget();
    d.id = 'fake-device-1'; d.name = fb.deviceName;
    var services = null;
    server = {
      device: d, connected: false,
      connect: async function () {
        fb.connectCount++;
        await sleep(fb.latency);
        if (fb.connectFailures > 0) { fb.connectFailures--; throw new DOMException('Connection attempt failed.', 'NetworkError'); }
        services = buildServices();
        server.connected = true;
        return server;
      },
      disconnect: function () { if (server.connected) dropConnection(); },
      getPrimaryService: function (u) {
        return op('discover', 'service ' + u, function () {
          var c = canon(u), P = window.FlashKaProtocol;
          if (c === canon(P.UUID.SERVICE)) {
            if (!sim_().canConnect()) throw new DOMException('No Services matching UUID ' + u + ' found in Device.', 'NotFoundError');   /* in presenter mode the light advertises only as a keyboard */
            return services.flashka;
          }
          if (c === BATTERY_SVC && !fb.hideBattery) return services.battery;
          throw new DOMException('No Services matching UUID ' + u + ' found in Device.', 'NotFoundError');
        });
      }
    };
    d.gatt = server;
    return d;
  }

  function sim_() { return ensureSim(); }

  function dropConnection() {
    if (!server || !server.connected) return;
    server.connected = false;
    Object.keys(chars).forEach(function (k) { chars[k].subscribed = false; });
    fb.log.push({ op: 'disconnect' });
    if (device) device.dispatchEvent(new Event('gattserverdisconnected'));
  }

  var bt = {
    requestDevice: async function (opts) {
      fb.requestCalls.push(JSON.parse(JSON.stringify(opts || {})));
      await sleep(10);
      if (fb.chooser === 'cancel') throw new DOMException('User cancelled the requestDevice() chooser.', 'NotFoundError');
      if (fb.chooser === 'none') throw new DOMException('Bluetooth adapter not available.', 'NotFoundError');
      if (!device) { device = makeDevice(); fb.device = device; fb.server = server; }
      return device;
    },
    getAvailability: function () { return Promise.resolve(fb.available); }
  };
  Object.defineProperty(navigator, 'bluetooth', { value: bt, configurable: true });
})();
