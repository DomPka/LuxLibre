#!/usr/bin/env node
// SPDX-License-Identifier: MIT OR Apache-2.0
// Builds app/aurora-flasher.html: ONE self-contained file with the page, esptool-js and the firmware image.
//
//   cd tools/web
//   npm install                      (once: esptool-js, esbuild, ...)
//   node build_flasher.mjs           (same as: npm run build)
//
// The firmware is the merged image from firmware/build.sh (firmware/dist/aurora-fw-v0.5.0-merged.bin). It is
// embedded as base64 together with its size, SHA-256 and version. If the file does not exist the page is built
// with a clearly marked PLACEHOLDER (it loads, but cannot install anything) and this script says so loudly.
//
// Options (all optional):
//   --bin <file>         firmware image to embed        (default ../../firmware/dist/aurora-fw-v0.5.0-merged.bin)
//   --out <file>         page to write                  (default ../../app/aurora-flasher.html)
//   --version <x.y.z>    version to show; default: taken from the file name, else from package.json
//   --placeholder        build the placeholder even if the firmware exists
//   --require-firmware   fail (exit 1) instead of building the placeholder when the firmware is missing
//   --allow-unmerged     embed an image that does not look like a merged bootloader+partitions+app image
//   --no-minify          readable JavaScript in the page (for debugging)
//   --help
//
// The output depends only on its inputs (no time stamps), so building twice gives byte-identical pages.

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { bytesToBase64, formatBytes, inspectImage, versionFromFileName } from './flasher/image.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_BIN = resolve(HERE, '../../firmware/dist/aurora-fw-v0.5.0-merged.bin');
const DEFAULT_OUT = resolve(HERE, '../../app/aurora-flasher.html');
const TEMPLATE = join(HERE, 'flasher', 'flasher.template.html');
const ENTRY = join(HERE, 'flasher', 'main.js');
const STUBS = join(HERE, 'flasher', 'stubs.js');

const HELP = `Builds app/aurora-flasher.html (page + esptool-js + firmware in one file).

  node build_flasher.mjs [options]

  --bin <file>         firmware image to embed (default: firmware/dist/aurora-fw-v0.5.0-merged.bin)
  --out <file>         page to write (default: app/aurora-flasher.html)
  --version <x.y.z>    version shown on the page (default: from the file name, else package.json)
  --placeholder        build the placeholder page even if the firmware exists
  --require-firmware   exit with an error instead of building the placeholder when the firmware is missing
  --allow-unmerged     embed an image that does not look like a merged bootloader+partition table+app image
  --no-minify          keep the JavaScript readable
  --help               this text
`;

/** @param {string[]} argv */
export function parseArgs(argv) {
  const o = {
    bin: DEFAULT_BIN, out: DEFAULT_OUT, version: /** @type {string | null} */ (null),
    placeholder: false, requireFirmware: false, allowUnmerged: false, minify: true, help: false
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const value = () => {
      const v = argv[++i];
      if (v === undefined || v.startsWith('--')) throw new Error(`${a} needs a value`);
      return v;
    };
    switch (a) {
      case '--bin': o.bin = resolve(value()); break;
      case '--out': o.out = resolve(value()); break;
      case '--version': o.version = value(); break;
      case '--placeholder': o.placeholder = true; break;
      case '--require-firmware': o.requireFirmware = true; break;
      case '--allow-unmerged': o.allowUnmerged = true; break;
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
  const ownVersion = JSON.parse(readFileSync(join(HERE, 'package.json'), 'utf8')).version;

  /* ---- the firmware ------------------------------------------------------------------------------------------- */
  let placeholder = opts.placeholder;
  /** @type {Uint8Array | null} */ let bytes = null;
  if (!placeholder) {
    if (existsSync(opts.bin) && statSync(opts.bin).isFile()) {
      bytes = new Uint8Array(readFileSync(opts.bin));
    } else if (opts.requireFirmware) {
      return fail(`The firmware file does not exist:\n\n    ${opts.bin}\n\nBuild it first (firmware/build.sh) or pass --bin <file>.`);
    } else {
      placeholder = true;
    }
  }

  let fileName = null;
  let sha256 = null;
  let version = opts.version || ownVersion;
  if (bytes) {
    const info = inspectImage(bytes);
    if (!info.ok) return fail(`${opts.bin} cannot be embedded:\n  - ${info.errors.join('\n  - ')}`);
    if (!info.merged && !opts.allowUnmerged) {
      return fail(`${opts.bin} does not look like a merged image for address 0x0:\n  - ${info.warnings.join('\n  - ')}\n\n` +
        'The page writes the file to address 0x0, so it must contain the bootloader, the partition table (at 0x8000) and the app (at 0x10000).\n' +
        'If you are sure, run again with --allow-unmerged.');
    }
    for (const w of info.warnings) console.warn('WARNING: ' + w);
    fileName = basename(opts.bin);
    sha256 = createHash('sha256').update(bytes).digest('hex');
    if (!opts.version) version = versionFromFileName(fileName) || ownVersion;
  }
  const firmware = {
    placeholder,
    version,
    fileName,
    size: bytes ? bytes.length : 0,
    sha256,
    base64: bytes ? bytesToBase64(bytes) : '',
    esptoolJs: esptoolVersion
  };

  /* ---- the script: page logic + esptool-js, one IIFE -------------------------------------------------------------- */
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
  for (const token of ['__FIRMWARE_JSON__', '/*__BUNDLE__*/']) {
    if (html.split(token).length !== 2) return fail(`The template must contain ${token} exactly once.`);
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
  if (placeholder) {
    const bar = '*'.repeat(78);
    console.warn(`\n${bar}\n*** PLACEHOLDER BUILD - NO FIRMWARE IS EMBEDDED IN THIS PAGE ${' '.repeat(18)}***\n${bar}`);
    console.warn(opts.placeholder
      ? '  (--placeholder was given.)'
      : `  The firmware file does not exist yet:\n    ${opts.bin}`);
    console.warn('  The page loads, but its Install button stays disabled (only "Advanced: use a different .bin file" works).');
    console.warn('  Build the firmware (firmware/build.sh), then run this again:\n\n    cd tools/web && node build_flasher.mjs\n');
    console.warn('  Use --require-firmware to make this an error instead of a placeholder build.\n' + bar);
  } else {
    console.log(`  firmware: ${fileName}  v${version}  ${formatBytes(firmware.size)} (${firmware.size} bytes)`);
    console.log(`  SHA-256:  ${sha256}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => fail(String(e && /** @type {Error} */ (e).stack || e)));
}
