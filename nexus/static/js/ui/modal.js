import { h, icon, trapFocus } from './dom.js';
import { t } from '../i18n.js';

let openCount = 0;

/**
 * Opens a modal. `build(close)` returns { title, body, footer? }.
 * Returns a promise resolved with whatever `close(value)` is called with.
 */
export function openModal(build, { wide = false } = {}) {
  return new Promise(resolve => {
    const root = document.getElementById('modal-root');
    const previous = document.activeElement;
    let closed = false;
    function close(value) {
      if (closed) return;
      closed = true;
      backdrop.remove();
      cleanup();
      openCount--;
      if (previous && previous.focus) previous.focus();
      resolve(value);
    }
    const spec = build(close);
    const dialog = h('div', { class: `modal${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'modal-title' },
      h('header', {}, h('h2', { id: 'modal-title', text: spec.title }), h('button', { class: 'btn icon sm ghost', type: 'button', 'aria-label': t('common.close'), onClick: () => close(undefined) }, icon('i-x'))),
      h('div', { class: 'stack' }, spec.body),
      spec.footer ? h('footer', {}, spec.footer) : null,
    );
    const backdrop = h('div', { class: 'modal-backdrop', onClick: e => { if (e.target === backdrop) close(undefined); } }, dialog);
    const cleanup = trapFocus(dialog);
    dialog.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(undefined); } });
    root.append(backdrop);
    openCount++;
    requestAnimationFrame(() => {
      const first = dialog.querySelector('input, select, textarea, button.primary, button');
      (first || dialog).focus();
    });
  });
}

export function confirmModal(title, message, { confirmLabel = t('common.confirm'), danger = false, extra = null } = {}) {
  return openModal(close => ({
    title,
    body: [h('p', { text: message }), extra],
    footer: [
      h('button', { class: 'btn', type: 'button', onClick: () => close(false) }, t('common.cancel')),
      h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, type: 'button', onClick: () => close(true) }, confirmLabel),
    ],
  }));
}

export function anyModalOpen() { return openCount > 0; }
