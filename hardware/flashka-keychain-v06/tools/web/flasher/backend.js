// SPDX-License-Identifier: MIT OR Apache-2.0
// The flasher's link to the chip: Web Serial + esptool-js behind a small API that the page (main.js) and the
// tests use. Everything that talks to esptool-js lives here.
//
// Design decisions (see docs/web_apps.md):
//  * 115200 baud for ROM and stub alike. The flashlight's USB port is a virtual serial port that ignores the baud
//    rate, and equal rates mean esptool-js never re-opens the port or changes speed, which is where USB boards
//    most often get lost.
//  * connect() does the whole handshake (reset into download mode, chip check, helper upload, flash id), so
//    step 2 of the page already proves that step 3 will work.
//  * Any failure closes the port again, so the person can simply press Connect once more.
//  * The reset at the end is done by hand, because esptool-js 0.7.0's HardReset only releases the reset line
//    without first pulling it.
//  * connect() also reads the app descriptor of the firmware that is on the flashlight now (96 bytes at 0x10020), so
//    the page can see which FlashKa (v0.7 or v0.6) it is running and stop an install of the other board's firmware.

import { ESPLoader, Transport } from 'esptool-js';
import { md5hex } from './md5.js';
import { APP_DESC_OFFSET, appInfoFromFields } from './image.js';

export const ESPRESSIF_USB_VENDOR_ID = 0x303a;
/** The chip name esptool-js reports for the flashlight's chip. */
export const EXPECTED_CHIP = 'ESP32-C3';
export const BAUD = 115200;
/** Bytes of the app descriptor read back from the flashlight: magic, version (at +16), project name (at +48). */
export const APP_DESC_READ_LEN = 96;
/** A read of the installed firmware's descriptor that takes longer than this fails the connection. */
export const READ_INSTALLED_TIMEOUT_MS = 8000;

export class WrongChipError extends Error {
  /** @param {string} chipName */
  constructor(chipName) {
    super(`Connected chip is ${chipName}, expected ${EXPECTED_CHIP}`);
    this.name = 'WrongChipError';
    this.chipName = chipName;
  }
}

export class FlashTooSmallError extends Error {
  /** @param {number} flashBytes @param {number} imageBytes */
  constructor(flashBytes, imageBytes) {
    super(`The image (${imageBytes} bytes) is larger than the flash chip (${flashBytes} bytes)`);
    this.name = 'FlashTooSmallError';
  }
}

/**
 * Opens the browser's port chooser. Must be called straight from a click.
 * @param {{ showAll?: boolean }} [options]
 * @returns {Promise<SerialPort>}
 */
export function browserRequestPort(options = {}) {
  return navigator.serial.requestPort(options.showAll ? {} : { filters: [{ usbVendorId: ESPRESSIF_USB_VENDOR_ID }] });
}

/** @param {number} ms */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * @typedef {Object} ConnectResult
 * @property {string} chip          "ESP32-C3"
 * @property {string} description   "ESP32-C3 (QFN32) (revision v0.4)"
 * @property {string} mac           "34:85:18:aa:bb:cc"
 * @property {number} flashBytes    size of the flash chip, 0 when unknown
 * @property {string} flashLabel    "4MB" or ""
 * @property {import('./image.js').AppInfo | null} installed   the firmware on the flashlight now (from its app
 *                                  descriptor; found = false when there is none); null when it could not be read
 *
 * @typedef {'preparing' | 'erasing' | 'writing' | 'verifying' | 'restarting'} Phase
 *
 * @typedef {Object} InstallOptions
 * @property {Uint8Array} image
 * @property {boolean} [eraseAll]
 * @property {(fraction: number) => void} [onProgress]   0..1
 * @property {(phase: Phase) => void} [onPhase]
 *
 * @typedef {Object} BackendOptions
 * @property {(options: { showAll?: boolean }) => Promise<SerialPort>} [requestPort]
 * @property {(text: string, newline: boolean) => void} [log]   receives the esptool-js output
 * @property {number} [connectAttempts]   reset-and-sync attempts, esptool-js default is 7
 * @property {() => void} [onLost]        the USB device disappeared while connected
 * @property {number} [readTimeoutMs]     time limit for reading the installed firmware's descriptor (tests)
 */

/**
 * @param {BackendOptions} [options]
 */
export function createEspBackend(options = {}) {
  const requestPort = options.requestPort || browserRequestPort;
  const log = options.log || (() => {});
  const connectAttempts = options.connectAttempts || 7;
  const onLost = options.onLost || (() => {});
  const readTimeoutMs = options.readTimeoutMs || READ_INSTALLED_TIMEOUT_MS;

  /** @type {import('esptool-js').IEspLoaderTerminal} */
  const terminal = {
    clean() {},
    write(s) { log(s, false); },
    writeLine(s) { log(s, true); }
  };

  /**
   * @typedef {Object} Link
   * @property {SerialPort} port
   * @property {Transport} transport
   * @property {ESPLoader} loader
   * @property {boolean} lost
   * @property {number} flashBytes
   * @property {(() => void) | null} failInstall
   * @property {() => void} onDisconnect
   */
  /** @type {Link | null} */
  let link = null;

  /** Closes the port without ever throwing or hanging. */
  async function teardown() {
    const l = link;
    link = null;
    if (!l) return;
    try { l.port.removeEventListener('disconnect', l.onDisconnect); } catch (e) { /* ignore */ }
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        await Promise.race([l.transport.disconnect(), sleep(3000).then(() => { throw new Error("closing the port took too long"); })]);
        return;
      } catch (e) {
        /* "already closed" (the cable is gone, or the chip restarted the USB port) is the expected outcome then. */
        if (l.lost || (e && /** @type {Error} */ (e).name === 'InvalidStateError')) return;
        /* A reader that was released a moment ago makes cancel() throw once; a second try is enough. */
        if (attempt === 1) log('Note: closing the port: ' + (e && /** @type {Error} */ (e).message), true);
        await sleep(50);
      }
    }
  }

  /**
   * The same as esptool-js main(), except for the baud-rate change and with a chip check before the helper is uploaded.
   * @param {{ showAll?: boolean, onPortChosen?: () => void }} [opts]
   * @returns {Promise<ConnectResult>}
   */
  async function connect(opts = {}) {
    /* The chooser first: it needs the click that is still "fresh". */
    const port = await requestPort({ showAll: !!opts.showAll });
    if (opts.onPortChosen) opts.onPortChosen();
    await teardown();

    const transport = new Transport(port, false);
    const loader = new ESPLoader({ transport, baudrate: BAUD, romBaudrate: BAUD, terminal, debugLogging: false });
    /** @type {Link} */
    const l = {
      port, transport, loader, lost: false, flashBytes: 0, failInstall: null,
      onDisconnect: () => {
        if (link !== l) return;
        l.lost = true;
        if (l.failInstall) l.failInstall();
        else onLost();
      }
    };
    link = l;
    port.addEventListener('disconnect', l.onDisconnect);
    transport.setDeviceLostCallback(l.onDisconnect);

    try {
      await loader.detectChip('default_reset', connectAttempts);
      const chip = loader.chip;
      if (chip.CHIP_NAME !== EXPECTED_CHIP) throw new WrongChipError(chip.CHIP_NAME);

      let description = chip.CHIP_NAME;
      let mac = '';
      if (!loader.secureDownloadMode) {
        description = await chip.getChipDescription(loader);
        if (chip.getChipRevision) loader.info('Chip Revision: ' + (await chip.getChipRevision(loader)));
        loader.info('Chip is ' + description);
        loader.info('Features: ' + (await chip.getChipFeatures(loader)));
        loader.info('Crystal is ' + (await chip.getCrystalFreq(loader)) + 'MHz');
        mac = await chip.readMac(loader);
        loader.info('MAC: ' + mac);
      }
      await loader.runStub();

      let flashBytes = 0;
      let flashLabel = '';
      if (!loader.secureDownloadMode) {
        let flashId;
        try {
          flashId = await loader.readFlashId();
        } catch (e) {
          throw new Error('Unable to verify flash chip connection ' + (e && /** @type {Error} */ (e).message));
        }
        loader.info('Flash ID: ' + flashId.toString(16));
        flashLabel = loader.DETECTED_FLASH_SIZES[(flashId >> 16) & 0xff] || '';
        const m = /^(\d+)(KB|MB)$/.exec(flashLabel);
        if (m) flashBytes = Number(m[1]) * (m[2] === 'MB' ? 1024 * 1024 : 1024);
        if (flashId === 0xffffff || flashId === 0) loader.info('WARNING: the flash chip did not answer sensibly; writing will probably fail.');
      }
      l.flashBytes = flashBytes;
      const installed = loader.secureDownloadMode ? null : await readInstalled(l);
      return { chip: chip.CHIP_NAME, description, mac, flashBytes, flashLabel, installed };
    } catch (e) {
      await teardown();
      throw e;
    }
  }

  /**
   * Reads the app descriptor of the firmware that is on the flashlight now, so that the page can tell which FlashKa
   * it belongs to. Returns null when the helper program refuses the read (the page then relies on the person's choice
   * alone). A read that never ends would leave esptool-js waiting on the port, so that fails the connection instead.
   * @param {Link} l
   * @returns {Promise<import('./image.js').AppInfo | null>}
   */
  async function readInstalled(l) {
    let timer = 0;
    let timedOut = false;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => { timedOut = true; reject(new Error('Reading the installed firmware took too long')); }, readTimeoutMs);
    });
    timeout.catch(() => {});
    try {
      const read = l.loader.readFlash(APP_DESC_OFFSET, APP_DESC_READ_LEN);
      read.catch(() => {});
      const bytes = await Promise.race([read, timeout]);
      const info = appInfoFromFields(
        (bytes[0] | (bytes[1] << 8) | (bytes[2] << 16) | (bytes[3] << 24)) >>> 0,
        bytes.subarray(16, 48),
        bytes.subarray(48, 80)
      );
      l.loader.info(info.found ? `Installed firmware: ${info.project || '?'} ${info.version || '?'}` : 'Installed firmware: none found');
      return info;
    } catch (e) {
      if (timedOut) throw e;
      l.loader.info('Could not read the installed firmware: ' + (e && /** @type {Error} */ (e).message));
      return null;
    } finally {
      clearTimeout(timer);
      /* The helper program ends a flash read with a 16-byte checksum packet that esptool-js 0.7.0 leaves unread. */
      if (!timedOut) await l.transport.drainInput(50, 300);
    }
  }

  /**
   * Writes the image to address 0x0, verifies it and restarts the chip. Closes the port at the end.
   * @param {InstallOptions} opts
   */
  async function install(opts) {
    const l = link;
    if (!l) throw lostError('The flashlight is not connected.');
    if (l.lost) { await teardown(); throw lostError('The device has been lost.'); }
    const { loader, transport } = l;
    const image = opts.image;
    const onProgress = opts.onProgress || (() => {});
    const onPhase = opts.onPhase || (() => {});
    if (l.flashBytes && image.length > l.flashBytes) {
      await teardown();
      throw new FlashTooSmallError(l.flashBytes, image.length);
    }

    const started = Date.now();
    onProgress(0);
    onPhase(opts.eraseAll ? 'erasing' : 'preparing');
    await sleep(40);                    /* let the page paint before the compression blocks it for a moment */

    /* If the cable is pulled out, esptool-js would wait for its own time-outs (many seconds): fail at once instead. */
    const gone = new Promise((_, reject) => { l.failInstall = () => reject(lostError('The device has been lost.')); });
    gone.catch(() => {});
    let writing = false;
    const write = loader.writeFlash({
      fileArray: [{ data: image, address: 0 }],
      flashSize: 'keep',
      flashMode: 'keep',
      flashFreq: 'keep',
      eraseAll: !!opts.eraseAll,
      compress: true,
      reportProgress: (_index, written, total) => {
        if (!writing) { writing = true; onPhase('writing'); }
        onProgress(total > 0 ? Math.min(1, written / total) : 1);
        if (total > 0 && written >= total) onPhase('verifying');
      },
      calculateMD5Hash: (data) => md5hex(data)
    });
    write.catch(() => {});

    try {
      await Promise.race([write, gone]);
    } catch (e) {
      await teardown();
      throw (l.lost ? lostError('The device has been lost.', e) : e);
    } finally {
      l.failInstall = null;
    }

    onProgress(1);
    onPhase('restarting');
    /* Restart the chip: pull the reset line, then let esptool-js release it. If the port vanishes during the reset
       (USB re-appears under a new number) that is expected and not an error. */
    try {
      await transport.setRTS(true);
      await loader.after('hard_reset', false);
    } catch (e) {
      log('Note: restarting the chip: ' + (e && /** @type {Error} */ (e).message), true);
    }
    await teardown();
    return { bytes: image.length, seconds: (Date.now() - started) / 1000 };
  }

  /** @param {string} message @param {unknown} [cause] */
  function lostError(message, cause) {
    const e = /** @type {Error & { cause?: unknown }} */ (new Error(message));
    e.name = 'NetworkError';
    if (cause) e.cause = cause;
    return e;
  }

  return {
    connect,
    install,
    disconnect: teardown,
    /** True while a port is open and the helper is running. */
    get connected() { return !!link && !link.lost; }
  };
}
