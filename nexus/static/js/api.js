// Fetch wrapper for the local API. Adds the per-launch token to mutating requests.
import { t } from './i18n.js';
const token = document.querySelector('meta[name="nexus-token"]')?.content || '';

export class ApiError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
    this.kind = extra.kind || extra.code || null;
  }
}

const offlineListeners = new Set();
export function onOffline(fn) { offlineListeners.add(fn); return () => offlineListeners.delete(fn); }
let offline = false;
function setOffline(value) {
  if (offline === value) return;
  offline = value;
  for (const fn of offlineListeners) fn(value);
}

async function request(method, path, { params, body, timeout = 120000 } = {}) {
  const url = new URL(path, window.location.origin);
  if (params) for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-Nexus-Token'] = token;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, credentials: 'same-origin' });
  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') throw new ApiError(0, 'Request timed out', { kind: 'timeout' });
    setOffline(true);
    throw new ApiError(0, t('common.offline'), { kind: 'offline' });
  }
  clearTimeout(timer);
  setOffline(false);
  let data = null;
  const text = await response.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = { error: text.slice(0, 200) }; }
  if (!response.ok) throw new ApiError(response.status, (data && data.error) || `HTTP ${response.status}`, data || {});
  return data;
}

export const api = {
  get: (path, params, opts) => request('GET', path, { params, ...opts }),
  post: (path, body, opts) => request('POST', path, { body: body ?? {}, ...opts }),
  patch: (path, body, opts) => request('PATCH', path, { body: body ?? {}, ...opts }),
  del: (path, params, opts) => request('DELETE', path, { params, ...opts }),
};
