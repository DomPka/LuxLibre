// SPDX-License-Identifier: MIT OR Apache-2.0
// Turns the errors of Web Serial and esptool-js into sentences a person without technical knowledge can act on.
//
// Pure functions, no DOM: the page uses them, and test/friendly.test.mjs checks them with the real error texts
// (the messages below were taken from the esptool-js 0.7.0 sources and from Chrome's Web Serial implementation).

/**
 * @typedef {'connect' | 'install'} Stage   where the error happened: while connecting, or while installing
 *
 * @typedef {Object} Explained
 * @property {string} code        stable id (used by the page and the tests)
 * @property {string} title       short headline
 * @property {string} message     one or two plain sentences
 * @property {string[]} steps     what to try, in order
 * @property {string} technical   the original error text, for the log and for support
 * @property {boolean} [showAllPorts]  the page offers "show all serial ports" next to the message
 * @property {boolean} [neutral]       not really a failure (e.g. the pop-up was closed), shown without alarm colours
 */

/** The steps that put the flashlight into the chip's built-in download mode by hand. */
export const DOWNLOAD_MODE_STEPS = [
  'Unplug the USB cable from the flashlight.',
  'Press and hold the button on the flashlight.',
  'While you keep holding it, plug the USB cable in.',
  'Let go of the button after about one second.',
  'Click "Connect" again.'
];

const CABLE_STEPS = [
  'Use a different USB-C cable. Many cables only charge and have no data wires - the cable of a phone or a laptop is usually fine.',
  'Plug into a different USB port of the computer, directly and not through a hub.'
];

/** Status codes the ROM / stub send back when a command fails (esptool "Failed to ... failed with status a,b": b is the code). */
const CHIP_ERROR_NAMES = {
  5: 'the chip did not understand the message',
  6: 'the chip could not carry out the command',
  7: 'data was damaged on the way to the chip',
  8: 'the chip could not write its memory',
  9: 'the chip could not read its memory',
  10: 'the chip reported a wrong data length',
  11: 'the chip could not unpack the data'
};

/**
 * @param {unknown} err
 * @returns {{ name: string, message: string }}
 */
function parts(err) {
  if (err && typeof err === 'object') {
    const e = /** @type {any} */ (err);
    return { name: String(e.name || (e.constructor && e.constructor.name) || ''), message: String(e.message || '') };
  }
  return { name: '', message: String(err) };
}

/**
 * Explains an error from connecting or installing.
 * @param {unknown} err
 * @param {Stage} stage
 * @returns {Explained}
 */
export function explainError(err, stage) {
  const { name, message } = parts(err);
  /* class names of minified code are one or two letters: not worth showing */
  const technical = (name && name !== 'Error' && name.length > 2 ? name + ': ' : '') + message;
  /** @param {Omit<Explained, 'technical'>} x @returns {Explained} */
  const out = (x) => ({ ...x, technical });
  const m = message;

  if (name === 'WrongChipError') {
    const chip = /** @type {any} */ (err).chipName || 'another chip';
    return out({
      code: 'wrong-chip',
      title: 'This is not an Aurora++ flashlight',
      message: `The device you chose is not the chip used in the flashlight (it says it is "${chip}"). Nothing was changed.`,
      steps: ['Unplug other boards, connect only the flashlight, then click "Connect" and choose its port again.']
    });
  }
  if (name === 'FlashTooSmallError' || /doesn't fit in the available flash/i.test(m)) {
    return out({
      code: 'flash-too-small',
      title: 'The firmware is too big for this device',
      message: 'The memory chip in this device is smaller than the firmware file. Nothing was changed.',
      steps: ['Check that you have the right firmware file and the right device.']
    });
  }

  /* --- choosing the port ------------------------------------------------------------------------------------- */
  if (name === 'NotFoundError') {      /* requestPort(): "No port selected by the user." - closed pop-up or empty list */
    return out({
      code: 'no-port-chosen',
      title: 'No port was chosen',
      message: 'The pop-up was closed without choosing a port, or its list was empty.',
      steps: [
        'Plug the flashlight into the computer with a USB-C data cable.',
        'Click "Connect" and choose "USB JTAG/serial debug unit" (Windows: "USB Serial Device (COM...)") in the pop-up.'
      ].concat(CABLE_STEPS.map((t) => 'If the pop-up list is empty: ' + t.charAt(0).toLowerCase() + t.slice(1))),
      showAllPorts: true,
      neutral: true
    });
  }
  if (name === 'SecurityError' || name === 'NotAllowedError') {
    return out({
      code: 'not-allowed',
      title: 'The browser does not allow this here',
      message: 'Browsers only allow serial ports on pages that are opened from https:// or as a file from your own computer, in a normal browser tab (not inside another page).',
      steps: ['Open this page in its own Chrome or Edge tab and click "Connect" again.']
    });
  }

  /* --- port problems ----------------------------------------------------------------------------------------- */
  const lost = /device has been lost|device lost|port is closed|port has been closed|has been closed|disconnected|unplugged/i.test(m);
  if (lost) {
    return out(stage === 'install' ? {
      code: 'device-lost',
      title: 'The connection was lost during the install',
      message: 'The flashlight stopped talking to the computer - the cable was probably unplugged or loose, or the computer switched the USB port off. The flashlight is not damaged: you can simply start again.',
      steps: ['Unplug the flashlight, plug it in again and click "Connect".', 'Click "Install" again. Keep this tab open and do not touch the cable until it says "done".']
    } : {
      code: 'device-lost',
      title: 'The flashlight disconnected',
      message: 'The computer lost the connection to the flashlight (the cable was probably unplugged or loose).',
      steps: ['Plug the flashlight in again.', 'Click "Connect".']
    });
  }

  if (name === 'InvalidStateError' || (name === 'NetworkError' && /failed to open serial port/i.test(m)) ||
      (name === 'TypeError' && /locked/i.test(m))) {
    return out({
      code: 'port-busy',
      title: 'The computer could not open the port',
      message: 'Another program or browser tab is probably using the flashlight right now (for example the Arduino IDE, a serial monitor, or another tab of this page).',
      steps: [
        'Close other programs and browser tabs that could talk to the flashlight.',
        'Unplug the flashlight, wait a few seconds and plug it in again.',
        'Click "Connect" again.',
        'On Linux the user may need permission for serial ports (usually the group "dialout").'
      ]
    });
  }

  /* --- no answer from the chip -------------------------------------------------------------------------------- */
  if (/Failed to connect with the device/i.test(m) || /Download mode successfully detected|Wrong boot mode detected/i.test(m)) {
    return out({
      code: 'no-sync',
      title: 'The flashlight did not answer',
      message: 'The port opened, but the flashlight did not switch to its installer mode. This is normal for some computers and cables. Putting it into download mode by hand fixes it.',
      steps: DOWNLOAD_MODE_STEPS.slice(),
      showAllPorts: false
    });
  }
  if (/Failed to start stub/i.test(m)) {
    return out({
      code: 'stub-failed',
      title: 'The flashlight did not accept the installer helper',
      message: 'This can happen if the connection is disturbed. Nothing was changed on the flashlight.',
      steps: ['Unplug the flashlight, plug it in again and click "Connect".'].concat(stage === 'connect' ? ['If it keeps happening, use download mode: hold the button while plugging the cable in, then let go.'] : [])
    });
  }
  if (/Unable to verify flash chip connection/i.test(m)) {
    return out({
      code: 'flash-chip',
      title: 'The flashlight\'s memory chip did not answer',
      message: 'The computer reached the flashlight, but its memory chip gave no sensible answer. This is often a poor USB connection.',
      steps: CABLE_STEPS.concat(['Unplug the flashlight, plug it in again and click "Connect".'])
    });
  }

  /* --- the install itself -------------------------------------------------------------------------------------- */
  if (/MD5 of file does not match/i.test(m)) {
    return out({
      code: 'verify-failed',
      title: 'The check after writing failed',
      message: 'The data that is now on the flashlight is not the same as the firmware file, so the flashlight may not start. It is safe to try again.',
      steps: [
        'Unplug the flashlight, plug it in again and click "Connect".',
        'Tick "factory reset" in step 3 and click "Install" again.',
        'If it fails again, try another cable or USB port (a loose cable damages data).'
      ]
    });
  }
  const status = /failed with status (\d+),(\d+)/i.exec(m);
  if (status) {
    const code = Number(status[2]);
    const what = CHIP_ERROR_NAMES[/** @type {keyof typeof CHIP_ERROR_NAMES} */ (code)] || `error code ${code}`;
    return out({
      code: 'chip-error',
      title: stage === 'install' ? 'The install stopped with an error' : 'The flashlight reported an error',
      message: `The flashlight answered with an error (${what}). Nothing is lost: you can try again.`,
      steps: [
        'Unplug the flashlight, plug it in again and click "Connect".',
        'Click "Install" again.',
        'If it repeats: another cable, another USB port, and a charged battery help.'
      ]
    });
  }
  if (/Serial data stream stopped|No serial data received|Invalid head of packet|Invalid SLIP escape|invalid response|serial noise/i.test(m)) {
    return out(stage === 'install' ? {
      code: 'timeout',
      title: 'The flashlight stopped answering',
      message: 'The connection was interrupted or garbled in the middle of the install. The flashlight is not damaged: you can start again.',
      steps: [
        'Unplug the flashlight, plug it in again and click "Connect".',
        'Click "Install" again. Use a short, good cable and avoid USB hubs.'
      ]
    } : {
      code: 'no-sync',
      title: 'The flashlight did not answer',
      message: 'The connection was garbled or the flashlight did not reply.',
      steps: DOWNLOAD_MODE_STEPS.slice()
    });
  }
  if (name === 'UnexpectedChipIdError' || name === 'UnexpectedChipMagicError' || name === 'MissingChipIdError' ||
      /Unexpected chip ID value|Unexpected CHIP magic value|Failed to autodetect chip type|does not contain chip ID/i.test(m)) {
    return out({
      code: 'unknown-chip',
      title: 'This device is not recognised',
      message: 'The device did not identify itself as the chip used in the flashlight. Nothing was changed.',
      steps: ['Unplug other boards, connect only the flashlight and try again.']
    });
  }
  if (name === 'UnsupportedCommandError' || /^unsupported command error$/i.test(m)) {
    return out({
      code: 'restricted',
      title: 'The flashlight refused the installer',
      message: 'The chip is in a restricted mode that does not allow installing from the browser.',
      steps: DOWNLOAD_MODE_STEPS.slice()
    });
  }

  return out({
    code: 'unknown',
    title: stage === 'install' ? 'The install did not finish' : 'Connecting did not work',
    message: 'Something unexpected happened. The flashlight cannot be broken by this - you can try again.',
    steps: [
      'Unplug the flashlight, plug it in again and click "Connect".',
      'Open "Technical log" at the bottom of the page and send its text to whoever gave you this page.'
    ]
  });
}

/**
 * True for the errors that mean "the USB device is gone", whatever the stage.
 * @param {unknown} err
 */
export function isDeviceLost(err) {
  const { name, message } = parts(err);
  return name === 'NetworkError' && /lost|unplug|disconnect/i.test(message);
}
