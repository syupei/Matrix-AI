// Capture one local page with a fresh Chrome profile and request interception.
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { readFile, realpath, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';

const [rootArg, preview, output, chrome, profile] = process.argv.slice(2);
const root = await realpath(rootArg);
const allowedRoots = new Set(['design', 'product', 'content', 'shared', 'engineering']);
const sources = new Map();
const blocked = [];
const digest = data => createHash('sha256').update(data).digest('hex');
const mime = { '.html': 'text/html', '.svg': 'image/svg+xml', '.css': 'text/css', '.js': 'text/javascript',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2' };
const policy = "default-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
  "connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'";

async function localFile(url) {
  const relative = decodeURIComponent(url.pathname).replace(/^\//, '');
  const parts = relative.split('/');
  if (!allowedRoots.has(parts[0]) || parts.some(part => part === '..' || part === '.' || !part)) throw Error('unsafe asset path');
  const local = path.join(root, ...parts);
  if (await realpath(local) !== local || !(await stat(local)).isFile()) throw Error('asset must be a regular project file');
  const data = await readFile(local);
  if (data.length > 8 * 1024 * 1024) throw Error('asset too large');
  sources.set(relative, digest(data));
  return { data, type: mime[path.extname(local)] || 'application/octet-stream' };
}

const server = createServer(async (request, response) => {
  try {
    if (request.method !== 'GET') throw Error('read-only capture');
    const asset = await localFile(new URL(request.url, origin));
    response.writeHead(200, { 'Content-Type': asset.type, 'Content-Security-Policy': policy,
      'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' });
    response.end(asset.data);
  } catch {
    response.writeHead(404); response.end();
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = spawn(chrome, ['--headless', '--disable-gpu', '--disable-extensions', '--disable-background-networking',
  '--disable-sync', '--no-first-run', '--no-default-browser-check', '--remote-debugging-pipe',
  '--user-data-dir=' + profile, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] });
let buffer = '', sequence = 0;
const pending = new Map();
const problems = [];
browser.stderr.on('data', data => { if (problems.length < 10) problems.push(String(data).slice(0, 300)); });

function call(method, params = {}, sessionId) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 10000);
    pending.set(id, { resolve, reject, timer });
    browser.stdio[3].write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0');
  });
}

browser.stdio[4].on('data', data => {
  buffer += data.toString();
  let delimiter;
  while ((delimiter = buffer.indexOf('\0')) >= 0) {
    const message = JSON.parse(buffer.slice(0, delimiter));
    buffer = buffer.slice(delimiter + 1);
    if (message.id && pending.has(message.id)) {
      const entry = pending.get(message.id); pending.delete(message.id); clearTimeout(entry.timer);
      message.error ? entry.reject(Error(message.error.message)) : entry.resolve(message.result);
    } else if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      let permitted = false;
      try {
        const url = new URL(request.url);
        permitted = url.origin === origin && url.protocol === 'http:' && request.method === 'GET';
      } catch { /* An invalid URL is refused. */ }
      if (!permitted) blocked.push({ url: request.url, reason: 'outside_capture_origin' });
      call(permitted ? 'Fetch.continueRequest' : 'Fetch.failRequest',
        permitted ? { requestId } : { requestId, errorReason: 'BlockedByClient' }, message.sessionId).catch(() => {});
    } else if (message.method === 'Network.loadingFailed') {
      blocked.push({ reason: message.params.blockedReason || message.params.errorText });
    } else if (message.method === 'Log.entryAdded' && message.params.entry.source === 'security') {
      blocked.push({ reason: 'browser_security_policy', message: message.params.entry.text });
    }
  }
});

try {
  await call('Browser.getVersion');
  const target = await call('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await call('Target.attachToTarget', { targetId: target.targetId, flatten: true });
  await call('Page.enable', {}, sessionId);
  await call('Network.enable', {}, sessionId);
  await call('Log.enable', {}, sessionId);
  await call('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] }, sessionId);
  await call('Browser.setDownloadBehavior', { behavior: 'deny' });
  await call('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false }, sessionId);
  const navigation = await call('Page.navigate', { url: origin + '/' + preview.split('/').map(encodeURIComponent).join('/') }, sessionId);
  if (navigation.errorText) throw Error(navigation.errorText);
  await new Promise(resolve => setTimeout(resolve, 700));
  const location = await call('Runtime.evaluate', { expression: 'location.href', returnByValue: true }, sessionId);
  if (!location.result.value.startsWith(origin + '/')) throw Error('page left capture origin');
  const shot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sessionId);
  const png = Buffer.from(shot.data, 'base64');
  if (png.readUInt32BE(16) !== 1280 || png.readUInt32BE(20) !== 800) throw Error('wrong PNG dimensions');
  await writeFile(output, png, { flag: 'wx' });
  process.stdout.write(JSON.stringify({ status: 'captured', sha256: digest(png), viewport: [1280, 800],
    source_files: Object.fromEntries(sources), blocked_requests: blocked,
    isolation: 'Exact capture origin Fetch interception, restrictive response CSP, fresh profile, downloads denied' }) + '\n');
} finally {
  browser.kill('SIGKILL');
  server.closeAllConnections(); server.close();
  for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(Error('capture stopped')); }
}
