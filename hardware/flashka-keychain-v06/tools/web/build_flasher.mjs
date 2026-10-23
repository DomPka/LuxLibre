#!/usr/bin/env node
// SPDX-License-Identifier: MIT OR Apache-2.0
// Builds app/flashka-flasher.html: ONE self-contained file with the page, esptool-js and the firmware images of BOTH
// FlashKa boards. The person chooses the board on the page before anything can be installed.
//
//   cd tools/web
//   npm install                      (once: esptool-js, esbuild, ...)
//   node build_flasher.mjs           (same as: npm run build)
//
// The firmware images are the merged images from firmware/build.sh: BOARD=v07 makes flashka-fw-v0.7.0-merged.bin
// (FlashKa v0.7), BOARD=v06 makes flashka-fw-v0.6.0-merged.bin (FlashKa v0.6). Each is embedded as base64 with its
// size, SHA-256 and version. The version and the board are read from the image's app descriptor, and the build
// refuses an image of the other board in a slot (the v0.7 firmware drives the LED with a different current scale and
// up to 3.0 A). A missing file gives a clearly marked PLACEHOLDER for that board, and this script says so loudly.
//
// Options (all optional):
//   --bin-v07 <file>     FlashKa v0.7 image   (default ../../firmware/dist/flashka-fw-v0.7.0-merged.bin)
//   --bin-v06 <file>     FlashKa v0.6 image   (default ../../firmware/dist/flashka-fw-v0.6.0-merged.bin)
//   --out <file>         page to write        (default ../../app/flashka-flasher.html)
//   --placeholder        build the placeholder even if the firmware exists (both boards)
//   --require-firmware   fail (exit 1) instead of building a placeholder when an image is missing
//   --allow-unmerged     embed an image that does not look like a merged bootloader+partitions+app image
//   --allow-board-mismatch  embed an image whose app descriptor does not name the slot's board (tests only)
//   --no-minify          readable JavaScript in the page (for debugging)
//   --help
//
// The output depends only on its inputs (no time stamps), so building twice gives byte-identical pages.

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { BOARDS, bytesToBase64, formatBytes, inspectImage, readAppDescriptor, versionFromFileName } from './flasher/image.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(HERE, '../../firmware/dist');
const DEFAULT_BIN = { v07: join(DIST, 'flashka-fw-v0.7.0-merged.bin'), v06: join(DIST, 'flashka-fw-v0.6.0-merged.bin') };
const DEFAULT_OUT = resolve(HERE, '../../app/flashka-flasher.html');
const TEMPLATE = join(HERE, 'flasher', 'flasher.template.html');
const ENTRY = join(HERE, 'flasher', 'main.js');
const STUBS = join(HERE, 'flasher', 'stubs.js');
const PICTURES = { v07: join(HERE, 'flasher', 'board-v07.webp'), v06: join(HERE, 'flasher', 'board-v06.webp') };

const HELP = `Builds app/flashka-flasher.html (page + esptool-js + the firmware of both FlashKa boards in one file).

  node build_flasher.mjs [options]

  --bin-v07 <file>     FlashKa v0.7 image (default: firmware/dist/flashka-fw-v0.7.0-merged.bin)
  --bin-v06 <file>     FlashKa v0.6 image (default: firmware/dist/flashka-fw-v0.6.0-merged.bin)
  --out <file>         page to write (default: app/flashka-flasher.html)
  --placeholder        build the placeholder page even if the firmware exists
  --require-firmware   exit with an error instead of building a placeholder when an image is missing
  --allow-unmerged     embed an image that does not look like a merged bootloader+partition table+app image
  --allow-board-mismatch  embed an image whose app descriptor does not name the board of its slot (tests only)
  --no-minify          keep the JavaScript readable
  --help               this text
`;

/** @param {string[]} argv */
export function parseArgs(argv) {
  const o = {
    bin: { ...DEFAULT_BIN }, out: DEFAULT_OUT,
    placeholder: false, requireFirmware: false, allowUnmerged: false, allowBoardMismatch: false, minify: true, help: false
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const value = () => {
      const v = argv[++i];
      if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`);
      return v;
    };
    switch (a) {
      case '--bin-v07': o.bin.v07 = resolve(value()); break;
      case '--bin-v06': o.bin.v06 = resolve(value()); break;
      case '--bin': throw new Error('--bin is gone: the page carries both boards now, use --bin-v07 <file> and --bin-v06 <file>');
      case '--version': throw new Error('--version is gone: the version is read from each image (its app descriptor)');
      case '--out': o.out = resolve(value()); break;
      case '--placeholder': o.placeholder = true; break;
      case '--require-firmware': o.requireFirmware = true; break;
      case '--allow-unmerged': o.allowUnmerged = true; break;
      case '--allow-board-mismatch': o.allowBoardMismatch = true; break;
      case '--no-minify': o.minify = false; break;
      case '--help': case '-h': o.help = true; break;
      default: throw new Error(`Unknown option ${a} (see --help)`);
    }
  }
  return o;
}

/** @param {string} msg */
function fail(msg) {
  console.error('\nERROR: ' + msg + '\n');
  process.exit(1);
}

/** Escapes text so that it can sit inside an HTML <script> element. @param {string} s */
function scriptSafe(s) {
  return s.replace(/<\/(script)/gi, '<\\/$1').replace(/<!--/g, '<\\!--');
}

/** JSON for a <script type="application/json"> element. @param {unknown} v */
function jsonForHtml(v) {
  return JSON.stringify(v).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
}

/**
 * One board's slot of the page: the checked image, or a placeholder.
 * @param {import('./flasher/image.js').Board} board
 * @param {ReturnType<typeof parseArgs>} opts
 */
function slot(board, opts) {
  const file = opts.bin[board.id];
  const empty = { placeholder: true, version: null, fileName: null, size: 0, sha256: null, base64: '' };
  if (opts.placeholder) return { data: empty, missing: null };
  if (!existsSync(file) || !statSync(file).isFile()) {
    if (opts.requireFirmware) {
      fail(`The ${board.title} firmware file does not exist:\n\n    ${file}\n\nBuild it first (BOARD=${board.id} firmware/build.sh) or pass --bin-${board.id} <file>.`);
    }
    return { data: empty, missing: file };
  }
  const bytes = new Uint8Array(readFileSync(file));
  const info = inspectImage(bytes);
  if (!info.ok) fail(`${file} cannot be embedded:\n  - ${info.errors.join('\n  - ')}`);
  if (!info.merged && !opts.allowUnmerged) {
    fail(`${file} does not look like a merged image for address 0x0:\n  - ${info.warnings.join('\n  - ')}\n\n` +
      'The page writes the file to address 0x0, so it must contain the bootloader, the partition table (at 0x8000) and the app (at 0x10000).\n' +
      'If you are sure, run again with --allow-unmerged.');
  }
  for (const w of info.warnings) console.warn('WARNING: ' + w);
  const app = readAppDescriptor(bytes);
  let version = app.found ? app.version : null;
  if (app.board !== board.id) {
    const what = app.found ? `firmware "${app.project}" version ${app.version}` + (app.board ? ` (made for ${app.board === 'v07' ? 'FlashKa v0.7' : 'FlashKa v0.6'})` : '') : 'no app descriptor';
    if (!opts.allowBoardMismatch) {
      fail(`${file} is not the ${board.title} firmware: it contains ${what}.\n` +
        `The ${board.title} slot takes FlashKa firmware ${board.firmware}.x only (BOARD=${board.id} firmware/build.sh). ` +
        'Installing one board\'s firmware on the other board drives the LED with the wrong current.');
    }
    console.warn(`WARNING: --allow-board-mismatch: the ${board.title} slot gets ${what}.`);
    if (!version) version = versionFromFileName(basename(file)) || 'unknown';
  }
  return {
    data: {
      placeholder: false,
      version,
      fileName: basename(file),
      size: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex'),
      base64: bytesToBase64(bytes)
    },
    missing: null
  };
}

async function main() {
  let opts;
  try { opts = parseArgs(process.argv.slice(2)); } catch (e) { return fail(/** @type {Error} */ (e).message + '\n\n' + HELP); }
  if (opts.help) { console.log(HELP); return; }

  if (Number(process.versions.node.split('.')[0]) < 18) fail(`Node.js 18 or newer is needed (this is ${process.version}).`);
  let esbuild;
  try {
    esbuild = await import('esbuild');
  } catch (e) {
    return fail('The build tools are not installed. Run this once, then try again:\n\n    cd ' + HERE + '\n    npm install');
  }
  const esptoolPackage = join(HERE, 'node_modules', 'esptool-js', 'package.json');
  if (!existsSync(esptoolPackage)) return fail('esptool-js is not installed. Run this once, then try again:\n\n    cd ' + HERE + '\n    npm install');
  const esptoolVersion = JSON.parse(readFileSync(esptoolPackage, 'utf8')).version;

  /* ---- the firmware of both boards ---------------------------------------------------------------------------- */
  /** @type {Record<string, any>} */ const boards = {};
  /** @type {string[]} */ const missing = [];
  for (const b of BOARDS) {
    const s = slot(b, opts);
    boards[b.id] = s.data;
    if (s.missing) missing.push(`${b.title}: ${s.missing}`);
  }
  const placeholder = BOARDS.every((b) => boards[b.id].placeholder);
  const firmware = { placeholder, esptoolJs: esptoolVersion, boards };

  /* ---- the script: page logic + esptool-js, one IIFE ------------------------------------------------------------ */
  /** @type {import('esbuild').Plugin} */
  const onlyC3Stub = {
    name: 'only-esp32c3-stub',
    setup(b) {
      /* esptool-js carries the helper program ("stub") of 14 chips; the flashlight needs one. */
      b.onResolve({ filter: /(^|[\\/])stubFlasher\.js$/ }, (args) => {
        if (/node_modules[\\/]esptool-js[\\/]/.test(args.importer)) return { path: STUBS };
        return undefined;
      });
    }
  };
  let result;
  try {
    result = await esbuild.build({
      entryPoints: [ENTRY],
      bundle: true,
      write: false,
      format: 'iife',
      platform: 'browser',
      target: ['es2020'],
      minify: opts.minify,
      keepNames: true,            /* esptool-js names its errors with new.target.name; minifying must not turn them into "F" */
      legalComments: 'inline',
      logLevel: 'warning',
      plugins: [onlyC3Stub],
      charset: 'ascii'
    });
  } catch (e) {
    return fail('The JavaScript could not be bundled:\n' + /** @type {Error} */ (e).message);
  }
  const bundle = scriptSafe(result.outputFiles[0].text);

  /* ---- the page ----------------------------------------------------------------------------------------------- */
  let html = readFileSync(TEMPLATE, 'utf8');
  for (const token of ['__FIRMWARE_JSON__', '/*__BUNDLE__*/', '__PICTURE_V07__', '__PICTURE_V06__']) {
    if (html.split(token).length !== 2) return fail(`The template must contain ${token} exactly once.`);
  }
  for (const b of BOARDS) {
    const picture = 'data:image/webp;base64,' + readFileSync(PICTURES[b.id]).toString('base64');
    html = html.split(`__PICTURE_${b.id.toUpperCase()}__`).join(picture);
  }
  html = html.split('__FIRMWARE_JSON__').join(jsonForHtml(firmware));
  html = html.split('/*__BUNDLE__*/').join(bundle);       /* last: the bundle is never scanned for tokens */

  mkdirSync(dirname(opts.out), { recursive: true });
  const tmp = opts.out + '.tmp';
  writeFileSync(tmp, html);
  renameSync(tmp, opts.out);

  /* ---- report ----------------------------------------------------------------------------------------------------- */
  const kb = (n) => (n / 1024).toFixed(0) + ' KB';
  console.log(`Wrote ${opts.out}`);
  console.log(`  page: ${formatBytes(Buffer.byteLength(html))}  (script ${kb(bundle.length)}, esptool-js ${esptoolVersion}${opts.minify ? ', minified' : ''})`);
  for (const b of BOARDS) {
    const f = boards[b.id];
    if (f.placeholder) console.log(`  ${b.title}: PLACEHOLDER (no firmware)`);
    else console.log(`  ${b.title}: ${f.fileName}  v${f.version}  ${formatBytes(f.size)} (${f.size} bytes)  SHA-256 ${f.sha256}`);
  }
  if (placeholder || missing.length) {
    const bar = '*'.repeat(78);
    console.warn(`\n${bar}\n*** PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED ${placeholder ? 'IN THIS PAGE' : 'FOR ONE BOARD'}${' '.repeat(placeholder ? 18 : 17)}***\n${bar}`);
    if (opts.placeholder) console.warn('  (--placeholder was given.)');
    for (const m of missing) console.warn(`  The firmware file does not exist yet:\n    ${m}`);
    console.warn('  The page loads, but its Install button stays disabled for a board without firmware (only "Advanced: use a different .bin file" works).');
    console.warn('  Build the firmware (BOARD=v07 / BOARD=v06 firmware/build.sh), then run this again:\n\n    cd tools/web && node build_flasher.mjs\n');
    console.warn('  Use --require-firmware to make this an error instead of a placeholder build.\n' + bar);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => fail(String(e && /** @type {Error} */ (e).stack || e)));
}
