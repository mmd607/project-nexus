import { t, getLanguage } from '../i18n.js';

export function formatBytes(n) {
  if (n == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

export function formatNumber(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat(getLanguage() === 'fa' ? 'fa-IR' : 'en-US').format(n);
}

export function formatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return new Intl.DateTimeFormat(getLanguage() === 'fa' ? 'fa-IR' : undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

export function relativeTime(ts) {
  if (!ts) return t('never');
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 45) return t('now');
  const rtf = new Intl.RelativeTimeFormat(getLanguage() === 'fa' ? 'fa' : 'en', { numeric: 'always' });
  const steps = [[60, 'second'], [3600, 'minute'], [86400, 'hour'], [604800, 'day'], [2629800, 'week'], [31557600, 'month'], [Infinity, 'year']];
  let prev = 1;
  for (const [limit, unit] of steps) {
    if (diff < limit) return rtf.format(-Math.round(diff / prev), unit);
    prev = limit;
  }
  return formatDate(ts);
}

export function percent(x) { return x == null ? '—' : `${Math.round(x * 100)}%`; }

export function shortPath(path, max = 60) {
  if (!path) return '';
  if (path.length <= max) return path;
  const parts = path.split(/[\\/]/);
  let out = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0 && (out.length + parts[i].length + 3) <= max; i--) out = parts[i] + '/' + out;
  return '…/' + out;
}
