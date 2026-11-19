// Render the documentation screenshots with headless Chrome/Edge via the DevTools protocol.
//   node scripts/screenshots.mjs [http://localhost:8765]
// Uses real device-metrics emulation, so 375x812 is laid out as a phone (Chrome's window minimum
// would otherwise force a ~500px layout). Node 22+ (global WebSocket) and Chrome or Edge required.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { writeFile } from 'node:fs/promises';

const BASE = process.argv[2] || 'http://localhost:8765';
const OUT = resolve(process.cwd(), 'docs/screenshots');
mkdirSync(OUT, { recursive: true });
const candidates = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
];
const chrome = candidates.find(p => existsSync(p));
if (!chrome) { console.error('no Chrome/Edge found'); process.exit(1); }

const port = 9333;
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${port}`, `--user-data-dir=${resolve(process.env.TEMP || '/tmp', 'nexus-shots-profile')}`, 'about:blank'], { stdio: 'ignore' });
let wsUrl = null;
for (let i = 0; i < 50 && !wsUrl; i++) {
  try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); wsUrl = (await r.json()).webSocketDebuggerUrl; } catch { await sleep(200); }
}
if (!wsUrl) { proc.kill(); console.error('could not connect to the browser'); process.exit(1); }

const ws = new WebSocket(wsUrl);
await new Promise(res => ws.addEventListener('open', res));
let seq = 0; const pending = new Map();
ws.addEventListener('message', ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}, sessionId) => new Promise(res => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params, sessionId })); });

const { targetId } = (await send('Target.createTarget', { url: 'about:blank' })).result;
const { sessionId } = (await send('Target.attachToTarget', { targetId, flatten: true })).result;
const call = (method, params) => send(method, params, sessionId);
await call('Page.enable');
await call('Runtime.enable');

const api = async path => (await fetch(`${BASE}${path}`)).json();
const ws_ = (await api('/api/workspaces')).items;
const WS = ws_.length ? ws_[0].id : 'all';
const pick = async (q) => { const it = (await api(`/api/projects?workspace=${WS}&${q}`)).items; return it.length ? it[0].id : ''; };
// Prefer a multi-part project for the focus shots so the satellites have something to show.
const all = (await api(`/api/projects?workspace=${WS}`)).items;
const multi = all.find(p => p.structure_kind === 'multi-part') || all.find(p => (p.components || []).length >= 3) || all[0];
const PID = multi ? multi.id : await pick('sort=files');
const DIRTY = await pick('status=Needs%20attention');

async function shot(name, width, height, url, { scale = 1, mobile = false, wait = 3500, script = '', reducedMotion = false } = {}) {
  await call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile, screenWidth: width, screenHeight: height });
  if (mobile) await call('Emulation.setTouchEmulationEnabled', { enabled: true });
  await call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: reducedMotion ? 'reduce' : 'no-preference' }] });
  await call('Page.navigate', { url: 'about:blank' });   // fresh document: hash-only navigations would keep app state
  await sleep(150);
  await call('Page.navigate', { url });
  await sleep(wait);
  if (script) { await call('Runtime.evaluate', { expression: script, awaitPromise: true }); await sleep(1800); }
  const { data } = (await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).result;
  await writeFile(resolve(OUT, `${name}.png`), Buffer.from(data, 'base64'));
  console.log(`wrote ${name}.png (${width}x${height}@${scale}x${reducedMotion ? ', reduced motion' : ''})`);
}

// View mode is remembered per browser; force it for the shot and put it back afterwards.
const mode = m => `(() => { const b = [...document.querySelectorAll('.mode-toggle .segmented button')].find(x => x.textContent.trim() === '${m}'); b && b.click(); return new Promise(r => setTimeout(r, 1500)); })()`;
const selectSatellite = `(() => new Promise(r => setTimeout(r, 400)))()`;

await shot('01-universe-3d-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}`, { script: mode('3D') });
await shot('02-universe-2d-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}`, { script: mode('2D') });
await shot('03-focus-project-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}&project=${PID}`, { script: mode('3D'), wait: 4500 });
await shot('04-focus-2d-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}&project=${PID}`, { script: mode('2D'), wait: 4500 });
await shot('05-details-needs-attention-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}&project=${DIRTY || PID}`, { script: mode('3D') });
await shot('06-projects-1440x900', 1440, 900, `${BASE}/#/projects?workspace=${WS}`);
await shot('07-settings-1440x900', 1440, 900, `${BASE}/#/settings?workspace=${WS}`);
await shot('08-universe-tablet-768x1024', 768, 1024, `${BASE}/#/universe?workspace=${WS}`, { script: mode('3D') });
await shot('09-focus-tablet-768x1024', 768, 1024, `${BASE}/#/universe?workspace=${WS}&project=${PID}`, { wait: 4500 });
await shot('10-universe-mobile-375x812', 375, 812, `${BASE}/#/universe?workspace=${WS}`, { scale: 2, mobile: true });
await shot('11-focus-mobile-375x812', 375, 812, `${BASE}/#/universe?workspace=${WS}&project=${PID}`, { scale: 2, mobile: true, wait: 4500 });
await shot('12-reduced-motion-1440x900', 1440, 900, `${BASE}/#/universe?workspace=${WS}&project=${PID}`, { reducedMotion: true, wait: 4500 });
await shot('13-knowledge-graph-1440x900', 1440, 900, `${BASE}/#/graph?workspace=${WS}`, { wait: 6000 });
ws.close();
proc.kill();
