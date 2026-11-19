import { h, icon } from './dom.js';

const root = () => document.getElementById('toasts');

export function toast(message, { kind = 'info', timeout = 5000, action = null } = {}) {
  // De-duplicate: an identical message that is already on screen is not repeated.
  const existing = [...root().querySelectorAll('.toast')].find(t => t.dataset.message === message);
  if (existing) return () => existing.remove();
  const el = h('div', { class: `toast ${kind}`, role: kind === 'error' ? 'alert' : 'status' },
    h('div', { class: 'grow', text: message }),
    action ? h('button', { class: 'btn sm', type: 'button', onClick: () => { action.onClick(); remove(); } }, action.label) : null,
    h('button', { type: 'button', 'aria-label': 'Dismiss', onClick: () => remove() }, icon('i-x')),
  );
  el.dataset.message = message;
  function remove() { el.remove(); }
  root().append(el);
  if (timeout) setTimeout(remove, timeout);
  return remove;
}
