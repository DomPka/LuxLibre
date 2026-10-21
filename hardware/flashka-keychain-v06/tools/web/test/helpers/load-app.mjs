// SPDX-License-Identifier: MIT OR Apache-2.0
// Loads the protocol and simulator exactly as they are shipped inside app/flashka-app.html
// (the <script id="flashka-protocol"> and <script id="flashka-sim"> blocks), into a vm context.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const APP_HTML = path.resolve(here, '../../../../app/flashka-app.html');

export function scriptBlock(html, id) {
  const m = new RegExp('<script id="' + id + '">([\\s\\S]*?)</script>').exec(html);
  if (!m) throw new Error('script block "' + id + '" not found in flashka-app.html');
  return m[1];
}

export function loadAppModules() {
  const html = fs.readFileSync(APP_HTML, 'utf8');
  const ctx = vm.createContext({ module: { exports: {} }, DOMException, console });
  vm.runInContext(scriptBlock(html, 'flashka-protocol'), ctx, { filename: 'flashka-protocol' });
  vm.runInContext(scriptBlock(html, 'flashka-sim'), ctx, { filename: 'flashka-sim' });
  return { P: vm.runInContext('FlashKaProtocol', ctx), Sim: vm.runInContext('FlashKaSim', ctx) };
}

/** Copy an object created in the vm realm into this realm so deepStrictEqual works. */
export const plain = (x) => JSON.parse(JSON.stringify(x));
