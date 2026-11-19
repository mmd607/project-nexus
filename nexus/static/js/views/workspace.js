// Workspace management: add (native picker / in-app browser / typed path), switch, remove.
import { api } from '../api.js';
import { store } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t } from '../i18n.js';
import { openModal, confirmModal } from '../ui/modal.js';
import { toast } from '../ui/toast.js';
import { relativeTime } from '../ui/format.js';

/** Modal that returns a chosen absolute path (or undefined). */
export async function pickFolderModal() {
  const pathInput = h('input', { class: 'input', type: 'text', placeholder: 'C:\\Users\\me\\Projects  ·  /home/me/projects', autocomplete: 'off' });
  const current = h('div', { class: 'mono muted', text: '' });
  const browser = h('div', { class: 'browser', role: 'listbox', 'aria-label': t('settings.browse') });
  const nativeNote = h('div', { class: 'faint', hidden: true, text: t('picker.nativeUnavailable') });
  let browsing = null;

  async function browse(path) {
    clear(browser);
    browser.append(h('div', { class: 'muted', style: { padding: '8px 10px' }, text: t('common.loading') }));
    try {
      const data = await api.get('/api/system/browse', { path: path || '' });
      browsing = data.path;
      clear(browser);
      current.textContent = data.path || t('picker.roots');
      if (data.path) pathInput.value = data.path;
      if (data.error) browser.append(h('div', { class: 'note warn', text: data.error }));
      if (data.parent) browser.append(h('button', { type: 'button', onClick: () => browse(data.parent) }, icon('i-up'), t('picker.up')));
      if (!data.path) for (const r of data.roots) browser.append(h('button', { type: 'button', onClick: () => browse(r.path) }, icon('i-folder'), `${r.label}  `, h('span', { class: 'muted mono', text: r.path })));
      for (const d of data.dirs) browser.append(h('button', { type: 'button', onClick: () => browse(d.path) }, icon('i-folder'), d.name));
      if (data.path && !data.dirs.length) browser.append(h('div', { class: 'muted', style: { padding: '8px 10px' }, text: '—' }));
    } catch (err) { clear(browser); browser.append(h('div', { class: 'note danger', text: err.message })); }
  }

  return openModal(close => {
    const nativeBtn = h('button', { class: 'btn', type: 'button', onClick: async () => {
      nativeBtn.disabled = true;
      try {
        const res = await api.post('/api/system/pick-folder', {}, { timeout: 600000 });
        if (res.path) close(res.path);
        else if (!res.available) nativeNote.hidden = false;
      } catch (err) { toast(err.message, { kind: 'error' }); }
      nativeBtn.disabled = false;
    } }, icon('i-folder'), t('picker.native'));
    browse('');
    return {
      title: t('picker.title'),
      body: [
        h('p', { class: 'muted', text: t('picker.body') }),
        h('div', { class: 'row wrap' }, nativeBtn, nativeNote),
        h('div', { class: 'field' }, h('label', { text: t('picker.current') }), current, browser),
        h('div', { class: 'field' }, h('label', { text: t('settings.typePath') }), pathInput),
      ],
      footer: [
        h('button', { class: 'btn', type: 'button', onClick: () => close(undefined) }, t('common.cancel')),
        h('button', { class: 'btn primary', type: 'button', onClick: () => { const v = pathInput.value.trim() || browsing; if (v) close(v); } }, icon('i-check'), t('picker.useThis')),
      ],
    };
  }, { wide: true });
}

export async function addWorkspaceFlow(actions) {
  const path = await pickFolderModal();
  if (!path) return null;
  try {
    const { workspace } = await api.post('/api/workspaces', { path });
    toast(t('ws.added'), { kind: 'success', timeout: 3000 });
    await actions.refreshWorkspaces();
    store.set('workspaceId', workspace.id);
    store.persistUi();
    actions.trackScans();
    return workspace;
  } catch (err) {
    if (err.kind === 'drive_root') {
      const ok = await confirmModal(t('picker.title'), err.message + '\n\nScan the whole drive anyway? This can take a long time.', { danger: true });
      if (ok) {
        try { const { workspace } = await api.post('/api/workspaces', { path, allow_root: true }); await actions.refreshWorkspaces(); store.set('workspaceId', workspace.id); actions.trackScans(); return workspace; }
        catch (e2) { toast(e2.message, { kind: 'error', timeout: 8000 }); }
      }
      return null;
    }
    toast(err.message, { kind: 'error', timeout: 8000 });
    return null;
  }
}

export function workspaceSwitcher(actions) {
  const workspaces = store.get('workspaces');
  const current = store.get('workspaceId');
  return openModal(close => ({
    title: t('ws.title'),
    body: [
      h('ul', { class: 'sub-list' },
        workspaces.length > 1 ? h('li', {}, h('button', { type: 'button', 'aria-current': current === 'all' ? 'true' : null, onClick: () => close('all') }, h('span', { text: t('workspace.all') }), h('span', { class: 'muted', text: `${workspaces.reduce((n, w) => n + (w.project_count || 0), 0)} ${t('settings.projects')}` }))) : null,
        workspaces.map(w => h('li', {}, h('button', { type: 'button', 'aria-current': current === w.id ? 'true' : null, onClick: () => close(w.id) },
          h('span', {}, h('b', { text: w.display_name }), h('div', { class: 'muted mono', style: { fontSize: '11px' }, text: w.root_path })),
          h('span', { class: 'muted', text: `${w.project_count || 0} ${t('settings.projects')} · ${w.last_scan_at ? relativeTime(w.last_scan_at) : t('never')}${w.exists === false ? ' · ' + t('settings.missingRoot') : ''}` })))),
      ),
    ],
    footer: [
      h('button', { class: 'btn', type: 'button', onClick: () => { close(undefined); location.hash = '#/settings'; } }, icon('i-gear'), t('ws.manage')),
      h('button', { class: 'btn primary', type: 'button', onClick: async () => { close(undefined); await addWorkspaceFlow(actions); } }, icon('i-plus'), t('settings.addFolder')),
    ],
  })).then(choice => { if (choice) { store.set('workspaceId', choice); store.persistUi(); actions.refreshProjects(); } });
}
