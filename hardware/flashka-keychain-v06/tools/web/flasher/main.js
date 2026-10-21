// SPDX-License-Identifier: MIT OR Apache-2.0
// Page logic of the firmware installer (flashka-flasher.html). Bundled with esptool-js by build_flasher.mjs.
//
//   state machine:  idle -> connecting -> connected -> installing -> done
//                              \-> error  <------------------------/        (any failure; "Try again" starts at idle)
//
// All talking to the chip is in backend.js; this file only does the interface: the four numbered steps, the
// firmware card, the progress bar, the error card, the "use another .bin" panel and the log.

import { createEspBackend } from './backend.js';
import { explainError } from './friendly.js';
import { inspectImage, formatBytes, base64ToBytes, sha256hex, versionFromFileName } from './image.js';

/** @param {string} id @returns {HTMLElement} */
function $(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error('Page element #' + id + ' is missing');
  return el;
}
/** @param {string} id */
const button = (id) => /** @type {HTMLButtonElement} */ ($(id));
/** @param {string} id */
const input = (id) => /** @type {HTMLInputElement} */ ($(id));
/** Smooth scrolling unless the person asked their system for less motion. @returns {ScrollBehavior} */
const smooth = () => (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth');

/**
 * @typedef {import('./image.js').ImageInfo} ImageInfo
 * @typedef {Object} Firmware
 * @property {'embedded' | 'custom'} source
 * @property {string} name        file name
 * @property {string | null} version
 * @property {Uint8Array} bytes
 * @property {number} size
 * @property {string | null} sha256     null when this browser has no WebCrypto
 * @property {boolean | null} fingerprintOk  embedded only: the bytes match the fingerprint stored by the build
 * @property {ImageInfo} info
 *
 * @typedef {'idle' | 'connecting' | 'connected' | 'installing' | 'done' | 'error'} State
 */

const S = {
  /** @type {State} */ state: 'idle',
  /** @type {'connect' | 'install'} */ stage: 'connect',
  /** @type {import('./backend.js').ConnectResult | null} */ device: null,
  /** @type {Firmware | null} */ firmware: null,
  /** @type {Firmware | null} */ embedded: null,
  placeholder: false,
  damaged: '',
  ack: false,
  /** @type {import('./friendly.js').Explained | null} */ error: null,
  notice: '',
  connectMessage: '',
  /** @type {string} */ phase: '',
  fraction: 0,
  /** @type {{ bytes: number, seconds: number } | null} */ result: null,
  /** @type {any} */ wake: null,
  titleBefore: document.title
};

/* ------------------------------------------------------------------------------------------------------------ *
 * log
 * ------------------------------------------------------------------------------------------------------------ */

const logBuf = { lines: /** @type {string[]} */ ([]), partial: '', timer: 0 };

/** Receives the output of esptool-js (text, with or without line end). @param {string} text @param {boolean} newline */
function logWrite(text, newline) {
  const parts = (logBuf.partial + text + (newline ? '\n' : '')).split(/\r\n|\n\r|\n|\r/);
  logBuf.partial = parts.pop() || '';
  for (const p of parts) logBuf.lines.push(p);
  if (logBuf.lines.length > 3000) logBuf.lines.splice(0, logBuf.lines.length - 3000);
  if (!logBuf.timer) logBuf.timer = window.setTimeout(flushLog, 200);
}
function flushLog() {
  logBuf.timer = 0;
  const pre = $('log');
  pre.textContent = logBuf.lines.join('\n') + (logBuf.partial ? '\n' + logBuf.partial : '');
  pre.scrollTop = pre.scrollHeight;
}
/** @param {string} message */
const pageLog = (message) => logWrite('[page] ' + message, true);

/* ------------------------------------------------------------------------------------------------------------ *
 * the link to the chip
 * ------------------------------------------------------------------------------------------------------------ */

const backend = createEspBackend({
  log: logWrite,
  onLost: () => {
    pageLog('The flashlight was unplugged.');
    if (S.state === 'connected') {
      S.device = null;
      S.notice = 'The flashlight was unplugged. Plug it in again and click Connect.';
      setState('idle');
    }
  }
});

/* ------------------------------------------------------------------------------------------------------------ *
 * browser support
 * ------------------------------------------------------------------------------------------------------------ */

/** @returns {{ title: string, reason: string } | null} */
function supportProblem() {
  if (navigator.serial) return null;
  const ua = navigator.userAgent || '';
  if (window.isSecureContext === false) {
    return {
      title: 'This page was opened in an insecure way.',
      reason: 'Browsers only allow installing firmware from pages whose address starts with https:// (or from a file opened on this computer). Open this page from its https:// address.'
    };
  }
  if (/iPhone|iPad|iPod/.test(ua)) return { title: 'iPhone and iPad cannot install firmware.', reason: 'Apple\'s browsers do not give web pages access to USB devices. Please open this page on a computer.' };
  if (/Android/.test(ua)) return { title: 'Phones and tablets cannot install firmware.', reason: 'Please open this page on a computer. (You can still control the flashlight from your phone with the control app.)' };
  if (/Firefox\//.test(ua)) return { title: 'Firefox cannot install firmware.', reason: 'Firefox does not let web pages talk to USB devices.' };
  if (/Safari\//.test(ua) && !/Chrome|Chromium|Edg\//.test(ua)) return { title: 'Safari cannot install firmware.', reason: 'Safari does not let web pages talk to USB devices.' };
  return { title: 'This browser cannot install firmware.', reason: 'It does not offer the "Web Serial" feature that this page needs.' };
}

/* ------------------------------------------------------------------------------------------------------------ *
 * firmware
 * ------------------------------------------------------------------------------------------------------------ */

/**
 * @param {{ source: 'embedded' | 'custom', name: string, version: string | null, bytes: Uint8Array, expectedSha?: string | null }} p
 * @returns {Promise<Firmware>}
 */
async function makeFirmware(p) {
  const sha256 = await sha256hex(p.bytes);
  return {
    source: p.source,
    name: p.name,
    version: p.version,
    bytes: p.bytes,
    size: p.bytes.length,
    sha256,
    fingerprintOk: p.expectedSha && sha256 ? sha256 === p.expectedSha : null,
    info: inspectImage(p.bytes)
  };
}

async function loadEmbedded() {
  let meta;
  try {
    meta = JSON.parse($('firmware-data').textContent || '');
  } catch (e) {
    S.damaged = 'Its data cannot be read.';
    return;
  }
  if (meta.placeholder) {
    S.placeholder = true;
    return;
  }
  let bytes;
  try {
    bytes = base64ToBytes(String(meta.base64 || ''));
  } catch (e) {
    S.damaged = 'Its data cannot be decoded.';
    return;
  }
  if (bytes.length !== meta.size) {
    S.damaged = `Its size is ${bytes.length} bytes instead of ${meta.size}.`;
    return;
  }
  const fw = await makeFirmware({ source: 'embedded', name: String(meta.fileName || 'firmware.bin'), version: meta.version || null, bytes, expectedSha: meta.sha256 });
  if (fw.fingerprintOk === false) {
    S.damaged = 'Its SHA-256 fingerprint does not match.';
    return;
  }
  S.embedded = fw;
  S.firmware = fw;
}

/** The firmware can be installed (valid, and any warning has been acknowledged). */
function canInstall() {
  const f = S.firmware;
  if (!f || !f.info.ok) return false;
  if (f.source === 'custom' && f.info.warnings.length > 0 && !S.ack) return false;
  return true;
}

/* ------------------------------------------------------------------------------------------------------------ *
 * rendering
 * ------------------------------------------------------------------------------------------------------------ */

const PILL = {
  idle: 'Not connected', connecting: 'Connecting...', connected: 'Connected',
  installing: 'Installing...', done: 'Installed', error: 'Problem'
};

const PHASE_TEXT = {
  preparing: 'Preparing the firmware...',
  erasing: 'Erasing the flashlight\'s memory (this can take up to a minute)...',
  writing: 'Writing the firmware...',
  verifying: 'Checking that everything was written correctly...',
  restarting: 'Restarting the flashlight...'
};

/** @param {string} id @param {string} status */
function stepStatus(id, status) { $(id).dataset.status = status; }

/** @param {HTMLElement} el @param {string} text @param {string} [cls] */
function line(el, text, cls) {
  const d = document.createElement('div');
  d.textContent = text;
  if (cls) d.className = cls;
  el.appendChild(d);
}

function renderFirmware() {
  const f = S.firmware;
  const tag = $('fw-tag');
  const check = $('fw-check');
  check.textContent = '';
  if (!f) {
    $('fw-name').textContent = S.placeholder ? 'None included in this page' : 'Not available';
    $('fw-size').textContent = '-';
    $('fw-sha').textContent = '-';
    tag.hidden = true;
    line(check, S.placeholder ? 'Nothing to install yet (placeholder build).' : 'The firmware inside this page is damaged.', 'badtxt');
    return;
  }
  $('fw-name').textContent = f.source === 'embedded' && f.version ? `FlashKa firmware v${f.version}` : f.name;
  tag.hidden = false;
  tag.textContent = f.source === 'embedded' ? 'included in this page' : 'your own file';
  tag.classList.toggle('custom', f.source === 'custom');
  $('fw-size').textContent = `${formatBytes(f.size)} (${f.size.toLocaleString('en-US')} bytes)`;
  $('fw-sha').textContent = f.sha256 || 'not available in this browser';
  if (f.fingerprintOk === true) line(check, '✓ The fingerprint matches: the file is intact.', 'good');
  if (f.info.ok && f.info.merged) line(check, '✓ A complete image for an ESP32-C3.', 'good');
  for (const w of f.info.warnings) line(check, '! ' + w);
  for (const e of f.info.errors) line(check, '✗ ' + e, 'badtxt');
}

function renderCustomPanel() {
  const f = S.firmware && S.firmware.source === 'custom' ? S.firmware : null;
  const report = $('file-report');
  report.hidden = !f;
  report.className = 'filecheck';
  report.textContent = '';
  if (f) {
    line(report, `${f.name} - ${formatBytes(f.size)}`);
    if (f.info.errors.length) {
      report.classList.add('bad');
      line(report, 'This file cannot be installed:');
      for (const e of f.info.errors) line(report, '✗ ' + e);
    } else if (f.info.warnings.length) {
      report.classList.add('warn');
      for (const w of f.info.warnings) line(report, '! ' + w);
    } else {
      line(report, '✓ Looks like a complete firmware image for an ESP32-C3.', 'good');
    }
  }
  $('file-ack-row').hidden = !(f && f.info.ok && f.info.warnings.length > 0);
  input('file-ack').checked = S.ack;
  button('btn-use-embedded').hidden = !(f && S.embedded);
}

function render() {
  const st = S.state;
  document.body.dataset.state = st;
  $('pill-text').textContent = st === 'installing' && S.phase === 'writing' ? `Installing... ${Math.floor(S.fraction * 100)}%` : PILL[st];

  /* steps */
  const sup = !!navigator.serial;
  stepStatus('step-1', st === 'idle' || st === 'connecting' || st === 'error' ? 'active' : 'done');
  stepStatus('step-2', st === 'connected' || st === 'installing' || st === 'done' ? 'done' : st === 'error' && S.stage === 'connect' ? 'error' : 'active');
  stepStatus('step-3', st === 'done' ? 'done' : st === 'error' && S.stage === 'install' ? 'error' : st === 'connected' || st === 'installing' ? 'active' : 'todo');
  stepStatus('step-4', st === 'done' ? 'active' : 'todo');

  /* step 2 */
  const connect = button('btn-connect');
  connect.disabled = !sup || st === 'connecting' || st === 'connected' || st === 'installing';
  connect.classList.toggle('busy', st === 'connecting');
  connect.textContent = st === 'connecting' ? 'Connecting...' : 'Connect';
  $('connect-actions').hidden = st === 'connected' || st === 'installing' || st === 'done';
  const status = $('connect-status');
  status.className = 'status';
  if (st === 'connecting') status.textContent = S.connectMessage;
  else if ((st === 'connected' || st === 'installing' || st === 'done') && S.device) {
    status.classList.add('ok');
    status.textContent = '✓ Flashlight found (' + S.device.chip + (S.device.flashLabel ? ', ' + S.device.flashLabel + ' memory' : '') + ').';
  } else status.textContent = S.notice;
  $('connect-extra').hidden = st !== 'connected';
  button('btn-showall').disabled = !sup || st === 'connecting' || st === 'installing';

  /* step 3 */
  const install = button('btn-install');
  install.disabled = !(st === 'connected' && canInstall());
  install.classList.toggle('busy', st === 'installing');
  install.textContent = st === 'installing' ? 'Installing...' : 'Install firmware';
  input('chk-erase').disabled = st === 'installing';
  $('install-controls').hidden = st === 'done';
  const showProgress = st === 'installing' || st === 'done';
  $('progress-wrap').hidden = !showProgress;
  const bar = $('progress');
  const fill = $('progress-fill');
  const determinate = st === 'done' || S.phase === 'writing' || S.phase === 'verifying';
  bar.classList.toggle('indeterminate', st === 'installing' && !determinate);
  const pct = st === 'done' || S.phase === 'verifying' ? 100 : Math.floor(S.fraction * 100);
  fill.style.width = determinate ? pct + '%' : '';
  bar.setAttribute('aria-valuenow', String(determinate ? pct : 0));
  $('phase-text').textContent = st === 'done' ? 'Installed and checked' : /** @type {Record<string,string>} */ (PHASE_TEXT)[S.phase] || PHASE_TEXT.preparing;
  $('phase-pct').textContent = st === 'done' ? '100%' : S.phase === 'writing' ? pct + '%' : '';
  document.querySelector('.keepopen')?.toggleAttribute('hidden', st === 'done');
  const installStatus = $('install-status');
  installStatus.className = 'status';
  if (st === 'done' && S.result) {
    installStatus.classList.add('ok');
    installStatus.textContent = `✓ ${formatBytes(S.result.bytes)} written in ${Math.round(S.result.seconds)} seconds. The data on the flashlight was compared with the file and is identical.`;
  } else installStatus.textContent = '';

  /* step 4 */
  $('done-actions').hidden = st !== 'done';

  /* problem */
  const card = $('error-card');
  const shown = st === 'error' && !!S.error;
  card.hidden = !shown;
  if (shown && S.error) {
    const e = S.error;
    card.classList.toggle('neutral', !!e.neutral);
    $('error-title').textContent = e.title;
    $('error-message').textContent = e.message;
    const ol = $('error-steps');
    ol.textContent = '';
    for (const step of e.steps) {
      const li = document.createElement('li');
      li.textContent = step;
      ol.appendChild(li);
    }
    $('error-tech').textContent = e.technical || '-';
    button('btn-error-showall').hidden = !e.showAllPorts;
  }

  /* firmware banners and panels */
  $('placeholder-banner').hidden = !S.placeholder;
  $('damaged-banner').hidden = !S.damaged;
  $('damaged-text').textContent = S.damaged;
  renderFirmware();
  renderCustomPanel();
}

/** @param {State} state */
function setState(state) {
  S.state = state;
  render();
}

/* ------------------------------------------------------------------------------------------------------------ *
 * actions
 * ------------------------------------------------------------------------------------------------------------ */

/** @param {{ showAll: boolean }} opts */
async function onConnect(opts) {
  if (S.state === 'connecting' || S.state === 'installing' || !navigator.serial) return;
  S.stage = 'connect';
  S.error = null;
  S.notice = '';
  S.result = null;
  S.device = null;
  S.connectMessage = 'Choose the flashlight in the pop-up window...';
  pageLog(`Connect${opts.showAll ? ' (all serial ports)' : ''}`);
  setState('connecting');
  try {
    S.device = await backend.connect({
      showAll: opts.showAll,
      onPortChosen: () => {
        S.connectMessage = 'Talking to the flashlight - this takes a few seconds...';
        render();
      }
    });
    pageLog('Connected: ' + S.device.description);
    setState('connected');
    $('step-3').scrollIntoView({ block: 'nearest', behavior: smooth() });
  } catch (e) {
    fail(e, 'connect');
  }
}

/** @param {unknown} e @param {'connect' | 'install'} stage */
function fail(e, stage) {
  S.stage = stage;
  S.device = null;
  S.error = explainError(e, stage);
  pageLog(`Problem (${stage}): ${S.error.technical}`);
  setState('error');
  const card = $('error-card');
  card.scrollIntoView({ block: 'center', behavior: smooth() });
  card.focus({ preventScroll: true });
}

/** @param {BeforeUnloadEvent} e */
function leaveGuard(e) {
  e.preventDefault();
  e.returnValue = '';
}

/** @param {boolean} on */
async function keepAwake(on) {
  try {
    if (on) {
      if (navigator.wakeLock) S.wake = await navigator.wakeLock.request('screen');
    } else if (S.wake) {
      await S.wake.release();
      S.wake = null;
    }
  } catch (e) { /* not available or refused: only a convenience */ }
}

async function onInstall() {
  const fw = S.firmware;
  if (S.state !== 'connected' || !fw || !canInstall()) return;
  S.stage = 'install';
  S.error = null;
  S.result = null;
  S.phase = input('chk-erase').checked ? 'erasing' : 'preparing';
  S.fraction = 0;
  pageLog(`Install ${fw.name} (${fw.size} bytes)${input('chk-erase').checked ? ' with factory reset' : ''}`);
  setState('installing');
  window.addEventListener('beforeunload', leaveGuard);
  S.titleBefore = document.title;
  document.title = 'Installing... keep this tab open';
  keepAwake(true);
  try {
    S.result = await backend.install({
      image: fw.bytes,
      eraseAll: input('chk-erase').checked,
      onProgress: (f) => { S.fraction = f; render(); },
      onPhase: (p) => { S.phase = p; render(); }
    });
    pageLog(`Done in ${S.result.seconds.toFixed(1)} s`);
    setState('done');
    $('step-4').scrollIntoView({ block: 'nearest', behavior: smooth() });
  } catch (e) {
    fail(e, 'install');
  } finally {
    window.removeEventListener('beforeunload', leaveGuard);
    document.title = S.titleBefore;
    keepAwake(false);
  }
}

async function onDisconnect() {
  pageLog('Disconnect');
  await backend.disconnect();
  S.device = null;
  S.notice = '';
  setState('idle');
}

async function onFileChosen() {
  const files = input('file-input').files;
  const file = files && files[0];
  if (!file) return;
  S.ack = false;
  if (file.size > 20 * 1024 * 1024) {
    S.firmware = { source: 'custom', name: file.name, version: null, bytes: new Uint8Array(0), size: file.size, sha256: null, fingerprintOk: null, info: inspectImage(new Uint8Array(0)) };
    S.firmware.info.errors = ['The file is far larger than any firmware for this flashlight.'];
    render();
    return;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  S.firmware = await makeFirmware({ source: 'custom', name: file.name, version: versionFromFileName(file.name), bytes });
  pageLog(`Chose ${file.name}: ${formatBytes(bytes.length)}, ${S.firmware.info.ok ? 'accepted' : 'rejected'}`);
  render();
}

function useEmbeddedAgain() {
  S.firmware = S.embedded;
  S.ack = false;
  input('file-input').value = '';
  render();
}

async function copyLog() {
  const text = $('log').textContent || '';
  const b = button('btn-copy-log');
  try {
    await navigator.clipboard.writeText(text);
    b.textContent = 'Copied';
  } catch (e) {
    const range = document.createRange();
    range.selectNodeContents($('log'));
    const sel = window.getSelection();
    if (sel) { sel.removeAllRanges(); sel.addRange(range); }
    b.textContent = 'Selected - press Ctrl+C';
  }
  window.setTimeout(() => { b.textContent = 'Copy log'; }, 2500);
}

/* ------------------------------------------------------------------------------------------------------------ *
 * start
 * ------------------------------------------------------------------------------------------------------------ */

async function init() {
  button('btn-connect').addEventListener('click', () => onConnect({ showAll: false }));
  button('btn-showall').addEventListener('click', () => onConnect({ showAll: true }));
  button('btn-error-showall').addEventListener('click', () => onConnect({ showAll: true }));
  button('btn-retry').addEventListener('click', () => onConnect({ showAll: false }));
  button('btn-install').addEventListener('click', onInstall);
  button('btn-disconnect').addEventListener('click', onDisconnect);
  button('btn-again').addEventListener('click', () => {
    S.result = null; S.device = null; S.notice = ''; S.phase = ''; S.fraction = 0;
    setState('idle');
    window.scrollTo({ top: 0, behavior: smooth() });
  });
  input('file-input').addEventListener('change', onFileChosen);
  input('file-ack').addEventListener('change', () => { S.ack = input('file-ack').checked; render(); });
  button('btn-use-embedded').addEventListener('click', useEmbeddedAgain);
  button('btn-copy-log').addEventListener('click', copyLog);

  const problem = supportProblem();
  $('unsupported').hidden = !problem;
  if (problem) {
    $('unsupported-title').textContent = problem.title;
    $('unsupported-reason').textContent = problem.reason;
  }
  await loadEmbedded();
  pageLog(S.placeholder ? 'Placeholder build: no firmware inside.' : S.embedded ? `Firmware in this page: ${S.embedded.name}, ${S.embedded.size} bytes, SHA-256 ${S.embedded.sha256 || 'n/a'}` : 'Firmware in this page: damaged (' + S.damaged + ')');
  $('foot-text').textContent = 'FlashKa firmware installer' + (S.embedded && S.embedded.version ? ' · firmware v' + S.embedded.version : '');
  render();
  /* for the automated tests and for debugging in the console */
  /** @type {any} */ (window).__flasher = { state: S, backend };
}

init();
