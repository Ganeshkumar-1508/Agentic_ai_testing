const fs = require('fs');
const path = require('path');
const cp = require('child_process');

const ROOT = process.cwd();
const OUT = path.join(ROOT, '.testai', 'verification', 'e2e-20260605T034100Z');
const BASE = 'http://127.0.0.1:8001';
const FRONT = 'http://127.0.0.1:3001';
fs.mkdirSync(OUT, { recursive: true });

let secret = '';
try {
  const match = fs.readFileSync(path.join(ROOT, 'plans', 'test_env.txt'), 'utf8').match(/^API_KEY\s*=\s*(.+)$/mi);
  secret = match ? match[1].trim() : '';
} catch {}

function red(value) {
  let text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  if (secret) text = text.split(secret).join('<redacted>');
  return text
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, '<redacted>')
    .replace(/(api[_-]?key["'\s:=]+)([^,"'\s}]+)/ig, '$1<redacted>');
}

function save(name, value) {
  fs.writeFileSync(path.join(OUT, name), red(value), 'utf8');
}

function load(name, fallback = {}) {
  try { return JSON.parse(fs.readFileSync(path.join(OUT, name), 'utf8')); } catch { return fallback; }
}

function shell(cmd) {
  try {
    const result = cp.spawnSync(cmd, { shell: true, cwd: ROOT, encoding: 'utf8', timeout: 60000 });
    return { cmd, code: result.status, stdout: red((result.stdout || '').slice(-12000)), stderr: red((result.stderr || '').slice(-12000)) };
  } catch (error) {
    return { cmd, error: red(String(error && error.stack || error)) };
  }
}

async function request(name, method, url, body = null, timeout = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method,
      headers: { 'user-agent': 'testai-e2e-validator', 'content-type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    return { name, ok: response.ok, status: response.status, ms: Date.now() - started, url, body_text: red(text.slice(0, 120000)) };
  } catch (error) {
    return { name, ok: false, status: null, ms: Date.now() - started, url, error: red(String(error && error.stack || error)) };
  } finally {
    clearTimeout(timer);
  }
}

function jsonBody(result) {
  try { return JSON.parse(result.body_text || '{}'); } catch { return {}; }
}

function newest(rel) {
  const root = path.join(ROOT, rel);
  const items = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const stat = fs.statSync(full);
      items.push({ path: path.relative(ROOT, full).replace(/\\/g, '/'), size: stat.size, mtime: stat.mtimeMs });
      if (entry.isDirectory() && items.length < 500) walk(full);
    }
  }
  try { if (fs.existsSync(root)) walk(root); } catch {}
  return items.sort((a, b) => b.mtime - a.mtime).slice(0, 120);
}

module.exports = { ROOT, OUT, BASE, FRONT, red, save, load, shell, request, jsonBody, newest };
