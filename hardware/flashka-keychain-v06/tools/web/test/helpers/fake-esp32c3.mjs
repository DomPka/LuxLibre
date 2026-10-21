// SPDX-License-Identifier: MIT OR Apache-2.0
// A pretend ESP32-C3 behind a pretend Web Serial port - for testing the flasher without hardware.
//
// It speaks the real serial protocol of the chip's ROM bootloader and of the flasher "stub" (SLIP frames, the same
// commands, checksums and status bytes esptool uses), so the REAL esptool-js runs against it, unchanged:
//
//   FakeSerialPort  - what navigator.serial.requestPort() would hand out: open/close, readable/writable web streams,
//                     setSignals(DTR/RTS), 'disconnect' event, the same errors Chrome throws in the same situations
//   FakeEsp32c3     - the chip: USB-Serial/JTAG reset logic (DTR/RTS -> ROM download mode or normal start), ROM
//                     commands (SYNC, READ_REG, WRITE_REG, GET_SECURITY_INFO, MEM_*), the stub (uploaded through MEM_*,
//                     then FLASH_DEFL_*, SPI_FLASH_MD5, ERASE_FLASH) and a virtual flash chip
//
// Scenarios (constructor options) let the tests provoke every failure the page must explain: a chip that never
// answers, wrong chip, a failed verification, a cable pulled out in the middle, a busy port, ...
//
// The module has no Node-only imports, so test/helpers/browser-entry.mjs bundles it for Playwright as well.
// Faithfulness notes: the ROM answers SYNC eight times; the stub's flash write is acknowledged per block; the
// stub erases the target range when FLASH_DEFL_BEGIN arrives; MD5 is over the written range.

import { inflate } from 'pako';
import { md5hex as defaultMd5 } from '../../flasher/md5.js';

export const OP = {
  FLASH_BEGIN: 0x02, FLASH_DATA: 0x03, FLASH_END: 0x04, MEM_BEGIN: 0x05, MEM_END: 0x06, MEM_DATA: 0x07, SYNC: 0x08,
  WRITE_REG: 0x09, READ_REG: 0x0a, SPI_SET_PARAMS: 0x0b, SPI_ATTACH: 0x0d, CHANGE_BAUDRATE: 0x0f,
  FLASH_DEFL_BEGIN: 0x10, FLASH_DEFL_DATA: 0x11, FLASH_DEFL_END: 0x12, SPI_FLASH_MD5: 0x13, GET_SECURITY_INFO: 0x14,
  ERASE_FLASH: 0xd0
};

const SPI_BASE = 0x60002000;
const SPI_CMD = SPI_BASE;
const SPI_USR2 = SPI_BASE + 0x20;
const SPI_W0 = SPI_BASE + 0x58;
const EFUSE_BLOCK1 = 0x60008800 + 0x44;
const CMD_USR = 1 << 18;

/** @param {string} name @param {string} message */
export function domError(name, message) {
  const e = new DOMException(message, name);
  return e;
}

/** @param {number} ms */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** @param {Uint8Array} data @returns {Uint8Array} SLIP frame C0 .. C0 */
function slipEncode(data) {
  const out = [0xc0];
  for (const b of data) {
    if (b === 0xc0) out.push(0xdb, 0xdc);
    else if (b === 0xdb) out.push(0xdb, 0xdd);
    else out.push(b);
  }
  out.push(0xc0);
  return Uint8Array.from(out);
}

/** @param {Uint8Array} data @param {number} state */
function xorChecksum(data, state = 0xef) {
  for (let i = 0; i < data.length; i++) state ^= data[i];
  return state;
}

/** @param {number} v */
const le32 = (v) => [v & 0xff, (v >>> 8) & 0xff, (v >>> 16) & 0xff, (v >>> 24) & 0xff];
/** @param {Uint8Array} b @param {number} o */
const rd32 = (b, o) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;

const textBytes = (s) => new TextEncoder().encode(s);

/**
 * @typedef {Object} ChipOptions
 * @property {number} [flashBytes]            size of the flash chip (default 4 MB)
 * @property {number} [flashId]               what the SPI flash answers to RDID (default 0x1640EF = 4 MB)
 * @property {number} [chipId]                5 = ESP32-C3 (default), 9 = ESP32-S3 (wrong chip)
 * @property {boolean} [silent]               never answers (a flashlight that is not in download mode, a dead cable)
 * @property {boolean} [autoResetBroken]      the DTR/RTS reset does not reach download mode - only the held button does
 * @property {boolean} [stubFails]            the helper program does not start ("OHAI" never comes)
 * @property {boolean} [md5Mismatch]          the flash MD5 never matches (corrupt write)
 * @property {number} [failBlockSeq]          the stub answers "CRC error" for this block, every time
 * @property {number} [loseDeviceAfterBlocks] the cable is pulled out after this many data blocks
 * @property {number} [loseDeviceAtCommand]   ... or when this command arrives (e.g. OP.SYNC)
 * @property {number} [commandDelayMs]        extra delay before every answer
 * @property {(bytes: Uint8Array) => string} [md5hex]  independent MD5 (the tests pass Node's crypto)
 * @property {Uint8Array} [initialFlash]      flash content before the install
 * @property {Array<{ from: number, length: number, value: number }>} [initialFill]  the same, as a short recipe (survives JSON, for the browser tests)
 * @property {number} [usbVendorId]
 * @property {number} [usbProductId]
 */

export class FakeEsp32c3 {
  /** @param {ChipOptions} [options] */
  constructor(options = {}) {
    this.options = options;
    this.chipId = options.chipId ?? 5;
    this.flashBytes = options.flashBytes ?? 4 * 1024 * 1024;
    this.flashId = options.flashId ?? 0x1640ef;
    this.md5hex = options.md5hex || defaultMd5;
    this.flash = new Uint8Array(this.flashBytes).fill(0xff);
    if (options.initialFlash) this.flash.set(options.initialFlash);
    for (const f of options.initialFill || []) this.flash.fill(f.value, f.from, f.from + f.length);

    /** 'app' (normal start) | 'rom' (download mode) | 'stub' (helper program running) */
    this.mode = 'app';
    this.buttonHeld = false;
    this.sig = { dtr: false, rts: false };
    this.downloadArmed = false;
    this.inReset = false;
    this.regs = new Map();
    this.port = /** @type {FakePort | null} */ (null);
    this.rx = /** @type {number[]} */ ([]);
    this.inFrame = false;
    this.escaping = false;

    /* what the tests look at */
    this.signalLog = /** @type {Array<[boolean, boolean]>} */ ([]);
    this.resets = /** @type {Array<'download' | 'app'>} */ ([]);
    this.commands = /** @type {number[]} */ ([]);
    this.memLoads = /** @type {Array<{ offset: number, bytes: Uint8Array }>} */ ([]);
    this.stubEntry = 0;
    this.eraseAllCount = 0;
    this.eraseAllBeforeWrite = false;
    this.writes = /** @type {Array<{ offset: number, size: number }>} */ ([]);
    this.md5Requests = /** @type {Array<{ addr: number, size: number, digest: string }>} */ ([]);
    this.dataBlocks = 0;
    this.endFlags = /** @type {number[]} */ ([]);
    this.defl = null;
    this.mem = null;
    this.lost = false;
    this.stalled = false;
    this.pending = /** @type {Uint8Array[]} */ ([]);
  }

  /* ---------------------------------------------------------------------------------------------------------- *
   * pins and resets
   * ---------------------------------------------------------------------------------------------------------- */

  /** The USB-Serial/JTAG bridge: DTR = IO0 (boot select), RTS = EN (reset). */
  onSignals(dtr, rts) {
    const prev = this.sig;
    if (prev.dtr === dtr && prev.rts === rts) return;
    this.sig = { dtr, rts };
    this.signalLog.push([dtr, rts]);
    if (!prev.rts && rts) {                 /* reset asserted; the bridge latches "IO0 low" if DTR is set at this moment */
      this.inReset = true;
      this.downloadArmed = dtr;
      this.mode = 'app';
      this.rx.length = 0;
      this.inFrame = false;
    } else if (prev.rts && !rts && this.inReset) {      /* reset released: the chip starts */
      this.inReset = false;
      const download = ((this.downloadArmed && !this.options.autoResetBroken) || this.buttonHeld) && !this.lost;
      this.start(download);
    }
  }

  /** @param {boolean} download */
  start(download) {
    this.resets.push(download ? 'download' : 'app');
    this.regs.clear();
    this.mem = null;
    this.defl = null;
    if (download) {
      this.mode = 'rom';
      this.send(textBytes('ESP-ROM:esp32c3-api1-20210207\r\nBuild:Feb  7 2021\r\nrst:0x15 (USB_UART_CHIP_RESET),boot:0x5 (DOWNLOAD(USB/UART0/1))\r\nwaiting for download\r\n'));
    } else {
      this.mode = 'app';
      const ok = this.flash[0] === 0xe9;
      this.send(textBytes('ESP-ROM:esp32c3-api1-20210207\r\nBuild:Feb  7 2021\r\nrst:0x15 (USB_UART_CHIP_RESET),boot:0xc (SPI_FAST_FLASH_BOOT)\r\n' +
        (ok ? 'FlashKa fw (fake) started\r\n' : 'invalid header: 0xffffffff\r\n')));
    }
  }

  /** Test hook: the person holds the button (IO0 low) while the chip restarts. */
  holdButton(held) { this.buttonHeld = !!held; }

  /** Test hook: the cable is pulled out right now. */
  pullCable() {
    if (this.lost) return;
    this.lost = true;
    if (this.port) this.port.loseDevice();
  }

  /** Test hook: the cable is plugged in again (the chip starts normally, no pins held). */
  replug() {
    this.lost = false;
    this.sig = { dtr: false, rts: false };
    this.inReset = false;
    this.rx.length = 0;
    this.inFrame = false;
    this.start(this.buttonHeld);
  }

  /* ---------------------------------------------------------------------------------------------------------- *
   * bytes in / out
   * ---------------------------------------------------------------------------------------------------------- */

  /** @param {Uint8Array} bytes data for the host */
  send(bytes) {
    if (this.options.silent || this.lost || !this.port) return;
    if (this.stalled) { this.pending.push(bytes); return; }
    const port = this.port;
    const delay = this.options.commandDelayMs || 0;
    setTimeout(() => port.deliver(bytes), delay);
  }

  /** Test hook: the chip stops answering (answers are kept) until resume() - for screenshots in the middle of an install. */
  stall() { this.stalled = true; }
  resume() {
    this.stalled = false;
    const queued = this.pending.splice(0);
    for (const bytes of queued) this.send(bytes);
  }

  /** @param {Uint8Array} chunk bytes written by the host */
  hostWrite(chunk) {
    if (this.lost) return;
    for (const b of chunk) {
      if (this.escaping) {
        this.escaping = false;
        this.rx.push(b === 0xdc ? 0xc0 : b === 0xdd ? 0xdb : b);
      } else if (b === 0xc0) {
        if (this.inFrame && this.rx.length > 0) {
          const frame = Uint8Array.from(this.rx);
          this.rx.length = 0;
          this.onFrame(frame);
        } else {
          this.rx.length = 0;
        }
        this.inFrame = true;
      } else if (b === 0xdb) {
        this.escaping = true;
      } else if (this.inFrame) {
        this.rx.push(b);
      }
    }
  }

  /** @param {number} op @param {number} val @param {number[] | Uint8Array} data */
  reply(op, val, data) {
    const body = Uint8Array.from(data);
    const frame = Uint8Array.from([1, op, body.length & 0xff, body.length >> 8, ...le32(val), ...body]);
    this.send(slipEncode(frame));
  }

  /** @param {number} op @param {number} val @param {number[] | Uint8Array} [payload] success */
  ok(op, val = 0, payload = []) { this.reply(op, val, [...payload, 0, 0]); }
  /** @param {number} op @param {number} code */
  fail(op, code) { this.reply(op, 0, [1, code]); }

  /** @param {Uint8Array} frame */
  onFrame(frame) {
    if (this.mode === 'app' || this.options.silent || frame.length < 8 || frame[0] !== 0) return;
    const op = frame[1];
    const len = frame[2] | (frame[3] << 8);
    const chk = rd32(frame, 4);
    const data = frame.subarray(8, 8 + len);
    if (data.length !== len) return;
    this.commands.push(op);
    if (this.options.loseDeviceAtCommand === op) { this.pullCable(); return; }

    switch (op) {
      case OP.SYNC: {
        const val = this.mode === 'stub' ? 0 : 0x20120707;
        for (let i = 0; i < 8; i++) this.ok(op, val);
        break;
      }
      case OP.READ_REG: this.ok(op, this.readReg(rd32(data, 0))); break;
      case OP.WRITE_REG: this.writeReg(rd32(data, 0), rd32(data, 4), rd32(data, 8)); this.ok(op); break;
      case OP.GET_SECURITY_INFO: {
        const info = Uint8Array.from([...le32(0), 0, 0, 0, 0, 0, 0, 0, 0, ...le32(this.chipId), ...le32(0)]);
        this.ok(op, 0, info);
        break;
      }
      case OP.SPI_ATTACH: case OP.SPI_SET_PARAMS: case OP.CHANGE_BAUDRATE: this.ok(op); break;
      case OP.MEM_BEGIN: {
        this.finishMem();                 /* esptool uploads text and data one after the other, then sends a single MEM_END */
        this.mem = { size: rd32(data, 0), blocks: rd32(data, 4), blockSize: rd32(data, 8), offset: rd32(data, 12), bytes: new Uint8Array(rd32(data, 0)), seen: 0 };
        this.ok(op);
        break;
      }
      case OP.MEM_DATA: {
        const m = this.mem;
        const n = rd32(data, 0);
        const seq = rd32(data, 4);
        const payload = data.subarray(16, 16 + n);
        if (!m || payload.length !== n || xorChecksum(payload) !== chk) { this.fail(op, 0x07); break; }
        m.bytes.set(payload, seq * m.blockSize);
        m.seen += n;
        this.ok(op);
        break;
      }
      case OP.MEM_END: {
        this.finishMem();
        const entry = rd32(data, 4);
        this.ok(op);
        if (entry !== 0) {
          this.stubEntry = entry;
          if (this.options.stubFails) this.send(slipEncode(textBytes('FAIL')));
          else { this.mode = 'stub'; this.send(slipEncode(textBytes('OHAI'))); }
        }
        break;
      }
      case OP.ERASE_FLASH: {
        if (this.mode !== 'stub') { this.fail(op, 0x05); break; }
        this.flash.fill(0xff);
        this.eraseAllCount++;
        this.eraseAllBeforeWrite = this.writes.length === 0;
        this.ok(op);
        break;
      }
      case OP.FLASH_DEFL_BEGIN: {
        if (this.mode !== 'stub') { this.fail(op, 0x05); break; }
        const size = rd32(data, 0), blocks = rd32(data, 4), blockSize = rd32(data, 8), offset = rd32(data, 12);
        if (offset + size > this.flashBytes) { this.fail(op, 0x06); break; }
        this.flash.fill(0xff, offset, Math.min(this.flashBytes, offset + Math.ceil(size / 4096) * 4096));   /* the stub erases the range */
        this.defl = { size, blocks, blockSize, offset, chunks: [], nextSeq: 0 };
        this.ok(op);
        break;
      }
      case OP.FLASH_DEFL_DATA: {
        const d = this.defl;
        const n = rd32(data, 0);
        const seq = rd32(data, 4);
        const payload = data.subarray(16, 16 + n);
        if (!d || payload.length !== n || xorChecksum(payload) !== chk) { this.fail(op, 0x07); break; }
        if (this.options.failBlockSeq === seq) { this.fail(op, 0x08); break; }
        if (seq !== d.nextSeq) { this.fail(op, 0x08); break; }
        d.chunks.push(payload.slice());
        d.nextSeq++;
        this.dataBlocks++;
        this.ok(op);
        if (this.options.loseDeviceAfterBlocks && this.dataBlocks >= this.options.loseDeviceAfterBlocks) setTimeout(() => this.pullCable(), 1);
        break;
      }
      case OP.FLASH_DEFL_END: {
        const d = this.defl;
        this.endFlags.push(rd32(data, 0));
        if (!d) { this.fail(op, 0x05); break; }
        let total = 0;
        for (const c of d.chunks) total += c.length;
        const joined = new Uint8Array(total);
        let at = 0;
        for (const c of d.chunks) { joined.set(c, at); at += c.length; }
        let plain;
        try { plain = inflate(joined); } catch (e) { this.fail(op, 0x0b); break; }
        if (plain.length !== d.size) { this.fail(op, 0x0b); break; }
        this.flash.set(plain, d.offset);
        this.writes.push({ offset: d.offset, size: d.size });
        this.defl = null;
        this.ok(op);
        break;
      }
      case OP.SPI_FLASH_MD5: {
        const addr = rd32(data, 0), size = rd32(data, 4);
        let digest = this.md5hex(this.flash.subarray(addr, addr + size));
        if (this.options.md5Mismatch) digest = digest.replace(/^./, digest[0] === '0' ? '1' : '0');
        this.md5Requests.push({ addr, size, digest });
        const payload = this.mode === 'stub'
          ? Uint8Array.from(digest.match(/../g).map((h) => parseInt(h, 16)))
          : textBytes(digest);
        this.ok(op, 0, payload);
        break;
      }
      default:
        this.fail(op, 0x05);       /* "invalid message" */
    }
  }

  finishMem() {
    const m = this.mem;
    if (!m) return;
    this.memLoads.push({ offset: m.offset, bytes: m.bytes.slice(0, m.size) });
    this.mem = null;
  }

  /** @param {number} addr */
  readReg(addr) {
    if (this.regs.has(addr)) return this.regs.get(addr) >>> 0;
    switch (addr) {
      case EFUSE_BLOCK1: return 0x18aabbcc;                   /* MAC bytes 2..5 */
      case EFUSE_BLOCK1 + 4: return 0x00003485;               /* MAC bytes 0..1 -> 34:85:18:aa:bb:cc */
      case EFUSE_BLOCK1 + 12: return (0 << 21) | (4 << 18);    /* package QFN32, revision minor 4 */
      default: return 0;
    }
  }

  /** @param {number} addr @param {number} value @param {number} mask */
  writeReg(addr, value, mask) {
    const old = this.regs.get(addr) || 0;
    this.regs.set(addr, ((old & ~mask) | (value & mask)) >>> 0);
    if (addr === SPI_CMD && (value & CMD_USR)) {
      const command = (this.regs.get(SPI_USR2) || 0) & 0xff;
      if (command === 0x9f) this.regs.set(SPI_W0, this.flashId >>> 0);        /* JEDEC id: EF 40 16 */
      this.regs.set(SPI_CMD, 0);                                              /* command finished */
    }
  }
}

/**
 * @typedef {Object} PortOptions
 * @property {'busy' | 'denied'} [openFails]    open() throws like Chrome does when another program holds the port
 */

class FakePort extends EventTarget {
  /**
   * @param {FakeEsp32c3} chip
   * @param {PortOptions & { usbVendorId?: number, usbProductId?: number }} [options]
   */
  constructor(chip, options = {}) {
    super();
    this.chip = chip;
    this.options = options;
    this.info = { usbVendorId: options.usbVendorId ?? chip.options.usbVendorId ?? 0x303a, usbProductId: options.usbProductId ?? chip.options.usbProductId ?? 0x1001 };
    this.isOpen = false;
    this._readable = null;
    this._writable = null;
    this._ctrl = null;
    this.openCalls = /** @type {any[]} */ ([]);
    this.closeCalls = 0;
    this.signalCalls = /** @type {any[]} */ ([]);
    chip.port = this;
  }

  getInfo() { return { ...this.info }; }
  get readable() { return this._readable; }
  get writable() { return this._writable; }

  async open(options) {
    this.openCalls.push(options);
    if (!options || !options.baudRate) throw new TypeError("Failed to execute 'open' on 'SerialPort': Failed to read the 'baudRate' property from 'SerialOptions': Required member is undefined.");
    if (this.isOpen) throw domError('InvalidStateError', 'The port is already open.');
    if (this.options.openFails || this.chip.lost) throw domError('NetworkError', 'Failed to open serial port.');
    await sleep(1);
    this.isOpen = true;
    const port = this;
    this._readable = new ReadableStream({
      start(controller) { port._ctrl = controller; },
      cancel() { /* the host stopped reading; the port itself stays open */ }
    });
    this._writable = new WritableStream({
      write(chunk) {
        if (port.chip.lost) throw domError('NetworkError', 'The device has been lost.');
        port.chip.hostWrite(chunk);
      }
    });
  }

  async close() {
    if (!this.isOpen) throw domError('InvalidStateError', 'The port is already closed.');
    if ((this._readable && this._readable.locked) || (this._writable && this._writable.locked)) {
      throw new TypeError("Failed to execute 'close' on 'SerialPort': Cannot cancel a locked stream");
    }
    this.closeCalls++;
    this.isOpen = false;
    this._readable = null;
    this._writable = null;
    this._ctrl = null;
  }

  async setSignals(signals = {}) {
    this.signalCalls.push({ ...signals });
    if (!this.isOpen) throw domError('InvalidStateError', 'The port is not open.');
    if (this.chip.lost) throw domError('NetworkError', 'The device has been lost.');
    const dtr = signals.dataTerminalReady === undefined ? this.chip.sig.dtr : !!signals.dataTerminalReady;
    const rts = signals.requestToSend === undefined ? this.chip.sig.rts : !!signals.requestToSend;
    this.chip.onSignals(dtr, rts);
  }

  /** @param {Uint8Array} bytes */
  deliver(bytes) {
    if (!this.isOpen || !this._ctrl) return;
    try { this._ctrl.enqueue(Uint8Array.from(bytes)); } catch (e) { /* the host cancelled its reader */ }
  }

  /** The cable is pulled out: streams fail, 'disconnect' fires. */
  loseDevice() {
    const ctrl = this._ctrl;
    this.isOpen = false;
    this._readable = this._writable = this._ctrl = null;
    try { if (ctrl) ctrl.error(domError('NetworkError', 'The device has been lost.')); } catch (e) { /* already closed */ }
    this.dispatchEvent(new Event('disconnect'));
  }
}

export { FakePort as FakeSerialPort };

/**
 * A navigator.serial look-alike that hands out one pretend port.
 * @param {FakeEsp32c3} chip
 * @param {PortOptions & { usbVendorId?: number, usbProductId?: number, chooser?: 'ok' | 'cancel' | 'empty' }} [options]
 */
export function makeFakeSerial(chip, options = {}) {
  const port = new FakePort(chip, options);
  const serial = new EventTarget();
  Object.assign(serial, {
    port,
    chooser: options.chooser || 'ok',
    requestCalls: /** @type {any[]} */ ([]),
    async requestPort(opts) {
      serial.requestCalls.push(opts ? JSON.parse(JSON.stringify(opts)) : null);
      await sleep(1);
      if (serial.chooser !== 'ok') throw domError('NotFoundError', 'No port selected by the user.');
      return port;
    },
    async getPorts() { return [port]; }
  });
  return /** @type {EventTarget & { port: FakePort, chooser: string, requestCalls: any[], requestPort: (o?: any) => Promise<FakePort>, getPorts: () => Promise<FakePort[]> }} */ (serial);
}
