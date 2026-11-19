// Settings view: workspaces, scan limits, ignore patterns, motion/theme, AI shortcut, privacy, about/export.
import { api } from '../api.js';
import { store } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t, setLanguage } from '../i18n.js';
import { openModal, confirmModal } from '../ui/modal.js';
import { toast } from '../ui/toast.js';
import { relativeTime, formatDate } from '../ui/format.js';
import { addWorkspaceFlow } from './workspace.js';

export function mountSettings(container, actions) {
  const view = h('div', { class: 'view' });
  container.append(view);
  const page = h('div', { class: 'page' });
  view.append(h('div', { class: 'view-header' }, h('div', {}, h('h2', { text: t('settings.title') }), h('p', { text: t('settings.readOnly') }))), page);

  const wsCard = h('section', { class: 'card' });
  const scanCard = h('section', { class: 'card' });
  const uiCard = h('section', { class: 'card' });
  const privacyCard = h('section', { class: 'card' });
  const aboutCard = h('section', { class: 'card' });
  page.append(wsCard, scanCard, uiCard, privacyCard, aboutCard);

  function renderWorkspaces() {
    clear(wsCard);
    const list = store.get('workspaces');
    wsCard.append(h('h3', {}, h('span', { text: t('settings.workspaces') }),
      h('span', { class: 'row' },
        h('button', { class: 'btn sm', type: 'button', onClick: () => actions.scanAll() }, icon('i-refresh'), t('scan.startAll')),
        h('button', { class: 'btn sm primary', type: 'button', onClick: () => addWorkspaceFlow(actions) }, icon('i-plus'), t('settings.addFolder')))));
    if (!list.length) wsCard.append(h('div', { class: 'empty', text: t('settings.noWorkspaces') }));
    for (const w of list) {
      const run = w.active_run;
      wsCard.append(h('div', { class: 'ws-item' },
        h('div', {},
          h('b', { text: w.display_name }), w.exists === false ? h('span', { class: 'pill status-attention', text: ' ' + t('settings.missingRoot') }) : null,
          h('div', { class: 'path', text: w.root_path }),
          h('div', { class: 'muted', style: { fontSize: '12px' }, text: `${w.project_count || 0} ${t('settings.projects')}${w.missing_count ? ` · ${w.missing_count} ${t('stats.missing').toLowerCase()}` : ''} · ${t('settings.lastScan')}: ${w.last_scan_at ? `${formatDate(w.last_scan_at)} (${relativeTime(w.last_scan_at)})` : t('never')}${run ? ` · ${t('scan.running')}…` : ''}` }),
          summaryLine(w),
          w.last_run?.summary?.skipped?.length ? h('details', { class: 'evidence', style: { marginTop: '6px' } }, h('summary', { text: t('settings.skipped', w.last_run.summary.skipped.length) }),
            h('ul', { class: 'error-list' }, w.last_run.summary.skipped.map(x => h('li', {}, h('code', { text: x.name, dir: 'auto' }), ` — ${x.reason}`)))) : null,
          (w.promoted || []).length ? h('div', { class: 'promoted-list' }, h('div', { class: 'muted', style: { fontSize: '12px', marginTop: '6px' }, text: t('settings.promotedList') }),
            h('ul', {}, w.promoted.map(path => h('li', {}, h('code', { text: path, dir: 'ltr' }), h('button', { class: 'btn sm ghost', type: 'button', title: t('detail.demote'), onClick: () => demote(w, path) }, icon('i-x'), t('detail.demote')))))) : null,
          w.last_run?.errors?.length ? h('details', { class: 'evidence', style: { marginTop: '6px' } }, h('summary', { text: t('scan.errors', w.last_run.errors.length) }), h('ul', { class: 'error-list' }, w.last_run.errors.slice(0, 50).map(e => h('li', { text: `${e.where}: ${e.message}` })))) : null),
        h('div', { class: 'actions' },
          h('button', { class: 'btn sm', type: 'button', disabled: !!run || w.exists === false, onClick: () => actions.scan(w.id, true) }, icon('i-refresh'), t('settings.rescan')),
          h('button', { class: 'btn sm ghost', type: 'button', disabled: !!run || w.exists === false, title: 'Ignore cached analysis and re-analyse every project', onClick: () => actions.scan(w.id, false) }, t('settings.fullRescan')),
          h('button', { class: 'btn sm ghost', type: 'button', onClick: () => rename(w) }, icon('i-edit'), t('settings.rename')),
          h('button', { class: 'btn sm danger', type: 'button', onClick: () => remove(w) }, icon('i-trash'), t('settings.remove')))));
    }
  }

  function summaryLine(w) {
    const sm = w.last_run?.summary;
    if (!sm || sm.top_level == null) return null;
    const parts = [t('settings.summaryTop', sm.top_level)];
    if (sm.skipped?.length) parts.push(t('settings.summarySkipped', sm.skipped.length));
    if (sm.loose_files) parts.push(t('settings.summaryLoose', sm.loose_files));
    if (sm.promoted) parts.push(t('settings.summaryPromoted', sm.promoted));
    if (sm.mode === 'nested') parts.push(t('settings.summaryCandidates', sm.candidates || 0));
    return h('div', { class: 'muted', style: { fontSize: '12px' }, text: parts.join(' · ') });
  }

  async function demote(w, path) {
    if (!await confirmModal(t('detail.demote'), t('detail.demoteConfirm', path))) return;
    try {
      const res = await api.post(`/api/workspaces/${w.id}/promote`, { path, promoted: false });
      if (res.run) store.set('activeRun', res.run);
      actions.trackScans();
      await actions.refreshWorkspaces();
      await actions.refreshProjects();
      toast(t('detail.demoted'), { kind: 'success', timeout: 2500 });
    } catch (err) { toast(err.message, { kind: 'error' }); }
  }

  async function rename(w) {
    const input = h('input', { class: 'input', type: 'text', value: w.display_name });
    const name = await openModal(close => ({ title: t('settings.rename'), body: [input], footer: [h('button', { class: 'btn', type: 'button', onClick: () => close(undefined) }, t('common.cancel')), h('button', { class: 'btn primary', type: 'button', onClick: () => close(input.value) }, t('common.save'))] }));
    if (!name) return;
    try { await api.patch(`/api/workspaces/${w.id}`, { display_name: name }); await actions.refreshWorkspaces(); } catch (err) { toast(err.message, { kind: 'error' }); }
  }

  async function remove(w) {
    const purge = h('input', { type: 'checkbox' });
    const ok = await confirmModal(t('settings.remove'), t('settings.confirmRemove', w.display_name), { danger: true, confirmLabel: t('settings.remove'), extra: h('label', { class: 'checkbox' }, purge, h('span', { text: t('settings.removeData') })) });
    if (!ok) return;
    try {
      await api.del(`/api/workspaces/${w.id}`, { purge: purge.checked ? '1' : '0' });
      toast(t('ws.removed'), { kind: 'success', timeout: 2500 });
      if (store.get('workspaceId') === w.id) { store.set('workspaceId', 'all'); store.persistUi(); }
      await actions.refreshWorkspaces();
      await actions.refreshProjects();
    } catch (err) { toast(err.message, { kind: 'error' }); }
  }

  function numberField(label, value, min, max, step = 1) {
    const input = h('input', { class: 'input', type: 'number', min: String(min), max: String(max), step: String(step), value: String(value) });
    return [h('div', { class: 'field' }, h('label', { text: label }), input), input];
  }

  function renderScan() {
    clear(scanCard);
    const s = store.get('settings');
    if (!s) return;
    const modeName = 'scan-mode-' + Math.random().toString(36).slice(2, 7);
    const modeInputs = {};
    const modeOption = (value, title, body) => {
      const input = h('input', { type: 'radio', name: modeName, value, checked: s.scan.mode === value ? true : null });
      modeInputs[value] = input;
      return h('label', { class: 'mode-option' }, input, h('span', {}, h('b', { text: title }), h('small', { text: body })));
    };
    const modeBox = h('div', { class: 'mode-options' },
      modeOption('top-level', t('settings.mode.top'), t('settings.mode.topBody')),
      modeOption('nested', t('settings.mode.nested'), t('settings.mode.nestedBody')));
    const [depthF, depth] = numberField(t('settings.maxDepth'), s.scan.max_depth, 0, 12);
    const [projF, proj] = numberField(t('settings.maxProjects'), s.scan.max_projects, 1, 20000);
    const [filesF, files] = numberField(t('settings.maxFiles'), s.scan.max_files_per_project, 10, 200000);
    const [winF, win] = numberField(t('settings.window'), s.scan.activity_window_days, 1, 3650);
    const [gitF, gitT] = numberField(t('settings.gitTimeout'), s.scan.git_timeout_seconds, 1, 120);
    const loose = h('input', { type: 'checkbox', checked: s.scan.detect_loose_folders ? true : null });
    const ignore = h('textarea', { class: 'textarea', rows: '8', 'aria-label': t('settings.ignore') });
    ignore.value = s.scan.ignore.join('\n');
    scanCard.append(h('h3', { text: t('settings.detection') }),
      h('p', { class: 'muted', style: { fontSize: '12.5px', marginBottom: '8px' }, text: t('settings.detectionBody') }),
      modeBox,
      h('h3', { text: t('settings.scan'), style: { marginTop: '14px' } }),
      h('div', { class: 'form-grid' }, depthF, projF, filesF, winF, gitF, h('label', { class: 'checkbox' }, loose, h('span', { text: t('settings.loose') }))),
      h('div', { class: 'field', style: { marginTop: '10px' } }, h('label', { text: t('settings.ignore') }), ignore),
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn primary', type: 'button', onClick: async () => {
        const mode = Object.values(modeInputs).find(i => i.checked)?.value || 'top-level';
        const changed = mode !== s.scan.mode;
        const saved = await saveSettings({ scan: { mode, max_depth: Number(depth.value), max_projects: Number(proj.value), max_files_per_project: Number(files.value), activity_window_days: Number(win.value), git_timeout_seconds: Number(gitT.value), detect_loose_folders: loose.checked, ignore: ignore.value.split('\n').map(x => x.trim()).filter(Boolean) } });
        if (saved && changed) { store.set('scanMode', mode); toast(t('settings.modeChanged'), { kind: 'success', timeout: 5000 }); actions.trackScans(); }
      } }, icon('i-check'), t('settings.save'))));
  }

  function renderUi() {
    clear(uiCard);
    const s = store.get('settings');
    if (!s) return;
    const theme = h('select', { class: 'select' }, h('option', { value: 'dark', text: 'Dark' }), h('option', { value: 'light', text: 'Light' })); theme.value = s.ui.theme;
    const lang = h('select', { class: 'select' }, h('option', { value: 'en', text: 'English' }), h('option', { value: 'fa', text: 'فارسی' })); lang.value = s.ui.language;
    const rotation = h('input', { type: 'checkbox', checked: s.ui.rotation ? true : null });
    const [speedF, speed] = numberField(t('settings.rotationSpeed'), s.ui.rotation_seconds_per_turn, 20, 3600, 10);
    const reduced = h('select', { class: 'select' }, ['system', 'on', 'off'].map(v => h('option', { value: v, text: t('settings.reduced.' + v) }))); reduced.value = s.ui.reduced_motion;
    const particles = h('input', { type: 'checkbox', checked: s.ui.particles ? true : null });
    const viewMode = h('select', { class: 'select' }, h('option', { value: '3d', text: '3D' }), h('option', { value: '2d', text: '2D' })); viewMode.value = s.ui.view_mode;
    const perf = h('input', { type: 'checkbox', checked: store.get('ui').perf ? true : null });
    const [satF, sat] = numberField(t('settings.satellites'), s.ui.focus_satellites ?? 8, 0, 24);
    uiCard.append(h('h3', { text: t('settings.motion') }),
      h('div', { class: 'form-grid' },
        h('div', { class: 'field' }, h('label', { text: t('settings.theme') }), theme),
        h('div', { class: 'field' }, h('label', { text: t('settings.language') }), lang),
        h('div', { class: 'field' }, h('label', { text: 'Default view mode' }), viewMode),
        h('div', { class: 'field' }, h('label', { text: t('settings.reduced') }), reduced),
        speedF,
        satF,
        h('label', { class: 'checkbox' }, rotation, h('span', { text: t('settings.rotation') })),
        h('label', { class: 'checkbox' }, particles, h('span', { text: t('settings.particles') })),
        h('label', { class: 'checkbox' }, perf, h('span', { text: 'Show FPS / render stats badge' }))),
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn primary', type: 'button', onClick: async () => {
        store.setUi({ perf: perf.checked, theme: theme.value, viewMode: viewMode.value, rotation: rotation.checked });
        await saveSettings({ ui: { theme: theme.value, language: lang.value, rotation: rotation.checked, rotation_seconds_per_turn: Number(speed.value), reduced_motion: reduced.value, particles: particles.checked, view_mode: viewMode.value, focus_satellites: Number(sat.value) } });
        actions.applyTheme();
        setLanguage(lang.value);
        actions.rerender();
      } }, icon('i-check'), t('settings.save'))));
  }

  function renderPrivacy() {
    clear(privacyCard);
    const s = store.get('settings');
    if (!s) return;
    const anon = h('input', { type: 'checkbox', checked: s.privacy.anonymize_paths_in_export ? true : null });
    const logPaths = h('input', { type: 'checkbox', checked: s.privacy.log_full_paths ? true : null });
    const openBrowser = h('input', { type: 'checkbox', checked: s.server.open_browser ? true : null });
    privacyCard.append(h('h3', { text: t('settings.privacy') }),
      h('div', { class: 'stack' },
        h('label', { class: 'checkbox' }, anon, h('span', { text: t('settings.anonymize') })),
        h('label', { class: 'checkbox' }, logPaths, h('span', { text: t('settings.logPaths') })),
        h('label', { class: 'checkbox' }, openBrowser, h('span', { text: 'Open the browser automatically at launch' })),
        h('div', { class: 'row' },
          h('button', { class: 'btn primary', type: 'button', onClick: () => saveSettings({ privacy: { anonymize_paths_in_export: anon.checked, log_full_paths: logPaths.checked }, server: { open_browser: openBrowser.checked } }) }, icon('i-check'), t('settings.save')),
          h('a', { class: 'btn', href: `/api/export?anonymize=${anon.checked ? 1 : 0}`, target: '_blank', rel: 'noopener' }, icon('i-open'), t('settings.export')))));
    anon.addEventListener('change', () => { privacyCard.querySelector('a.btn').href = `/api/export?anonymize=${anon.checked ? 1 : 0}`; });
  }

  function renderAbout() {
    clear(aboutCard);
    const session = store.get('session') || {};
    const s = store.get('settings');
    aboutCard.append(h('h3', { text: t('settings.about') }),
      h('dl', { class: 'about-grid' },
        h('dt', { text: t('settings.version') }), h('dd', { text: `Project Nexus ${session.version || ''}` }),
        h('dt', { text: t('settings.dataDir') }), h('dd', { text: session.data_dir || '—' }),
        h('dt', { text: 'Settings file' }), h('dd', { text: s?.__path || (session.data_dir ? session.data_dir + '/settings.json' : '—') }),
        h('dt', { text: 'Server' }), h('dd', { text: `${session.host}:${session.port} ${session.loopback ? '(loopback only)' : '(exposed on network!)'}` }),
        h('dt', { text: t('settings.git') }), h('dd', { text: session.git_available ? 'available' : 'not found — Git status disabled' }),
        h('dt', { text: t('settings.python') }), h('dd', { text: `${session.python || ''} · ${session.platform || ''}${session.frozen ? ' · packaged build' : ''}` })));
  }

  async function saveSettings(patch) {
    try {
      const { settings, rescans } = await api.patch('/api/settings', patch);
      store.set('settings', settings);
      if (rescans?.length) store.set('activeRun', rescans[0]);
      toast(t('settings.saved'), { kind: 'success', timeout: 2000 });
      return settings;
    } catch (err) { toast(err.message, { kind: 'error', timeout: 8000 }); return null; }
  }

  function renderAll() { renderWorkspaces(); renderScan(); renderUi(); renderPrivacy(); renderAbout(); }
  const unsubs = [store.on('workspaces', renderWorkspaces), store.on('settings', () => { renderScan(); renderUi(); renderPrivacy(); }), store.on('session', renderAbout)];
  renderAll();
  return { destroy() { for (const u of unsubs) u(); view.remove(); } };
}
