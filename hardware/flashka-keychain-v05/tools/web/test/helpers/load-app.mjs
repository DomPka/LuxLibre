// SPDX-License-Identifier: MIT OR Apache-2.0
// Loads the protocol and simulator exactly as they are shipped inside app/aurora-app.html
// (the <script id="aurora-protocol"> and <script id="aurora-sim"> blocks), into a vm context.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const APP_HTML = path.resolve(here, '../../../../app/aurora-app.html');

export function scriptBlock(html, id) {
  const m = new RegExp('<script id="' + id + '">([\\s\\S]*?)</script>').exec(html);
  if (!m) throw new Error('script block "' + id + '" not found in aurora-app.html');
  return m[1];
}

export function loadAppModules() {
  const html = fs.readFileSync(APP_HTML, 'utf8');
  const ctx = vm.createContext({ module: { exports: {} }, DOMException, console });
  vm.runInContext(scriptBlock(html, 'aurora-protocol'), ctx, { filename: 'aurora-protocol' });
  vm.runInContext(scriptBlock(html, 'aurora-sim'), ctx, { filename: 'aurora-sim' });
  return { P: vm.runInContext('AuroraProtocol', ctx), Sim: vm.runInContext('AuroraSim', ctx) };
}

/** Copy an object created in the vm realm into this realm so deepStrictEqual works. */
export const plain = (x) => JSON.parse(JSON.stringify(x));
