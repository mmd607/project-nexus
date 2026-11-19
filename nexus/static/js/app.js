// Bootstrap: load session/settings, mount shell widgets, route between views.
import { api, onOffline } from './api.js';
import { store, categoryColor } from './store.js';
import { h, icon, clear, $, $$, debounce } from './ui/dom.js';
import { t, setLanguage } from './i18n.js';
import { toast } from './ui/toast.js';
import { openModal, anyModalOpen } from './ui/modal.js';
import { relativeTime } from './ui/format.js';
import { mountUniverse } from './universe/universe.js';
import { mountDetails } from './views/details.js';
import { mountProjects } from './views/projects.js';
import { mountKnowledge } from './views/knowledge.js';
import { mountAssistant } from './views/assistant.js';
import { mountSettings } from './views/settings.js';
import { mountScanWidget } from './views/scan.js';
import { addWorkspaceFlow, workspaceSwitcher } from './views/workspace.js';

const main = document.getElementById('main');
let currentView = null, currentName = null, universeRef = null, scanWidget = null, pendingFocus = null;

// ------------------------------------------------------------------ actions shared with views
const actions = {
  select(id) { store.select(id); if (id) history.replaceState(null, '', `#/${currentName || 'universe'}?project=${id}`); else history.replaceState(null, '', `#/${currentName || 'universe'}`); },
  /** Search result chosen: clear the filter, select the project and glide the camera to it. */
  jumpTo(id) { actions.setQuery(''); if (currentName !== 'universe') location.hash = `#/universe?project=${id}`; actions.select(id); actions.focusInUniverse(id); },
  setFilter(key, value) { store.patch('filters', { [key]: value }); },
  setQuery(q) { $('#global-search').value = q; store.set('query', q); },
  async refreshWorkspaces() {
    const { items, scan_mode } = await api.get('/api/workspaces');
    store.set('workspaces', items);
    if (scan_mode && scan_mode !== store.get('scanMode')) store.set('scanMode', scan_mode);
    const active = items.map(w => w.active_run).find(Boolean);
    if (active) { store.set('activeRun', active); scanWidget?.track(active.id); }
    updateWorkspaceCard();
    return items;
  },
  async refreshProjects({ includeMissing = false, quiet = false } = {}) {
    const ws = store.get('workspaceId');
    const params = { limit: 20000 };
    if (ws !== 'all') params.workspace = ws;
    if (includeMissing) params.include_missing = '1';
    try {
      const [{ items, total }, stats, { items: relations }] = await Promise.all([api.get('/api/projects', params), api.get('/api/stats', ws !== 'all' ? { workspace: ws } : {}), api.get('/api/relations')]);
      store.set('relations', relations);
      store.set('projects', items);
      store.set('projectsTotal', total);
      store.set('stats', stats);
      updateSideStats();
      if (pendingFocus && items.some(p => p.id === pendingFocus)) { store.select(pendingFocus, { push: false }); pendingFocus = null; }
      if (store.get('selectedId') && !items.some(p => p.id === store.get('selectedId')) && !includeMissing) {
        // selected project vanished from the current list (e.g. workspace switch): keep details but nothing else
      }
    } catch (err) { if (!quiet) toast(err.message, { kind: 'error' }); }
  },
  async scan(workspaceId, incremental = true) {
    try {
      const { run } = await api.post(`/api/workspaces/${workspaceId}/scan`, { incremental });
      store.set('activeRun', run);
      scanWidget.track(run.id);
      await actions.refreshWorkspaces();
    } catch (err) { toast(err.message, { kind: 'error', timeout: 7000 }); }
  },
  async scanAll() {
    const list = store.get('workspaces');
    if (!list.length) return addWorkspaceFlow(actions);
    for (const w of list) if (w.exists !== false) await actions.scan(w.id, true);
  },
  trackScans() { for (const w of store.get('workspaces')) if (w.active_run) scanWidget.track(w.active_run.id); actions.refreshWorkspaces(); },
  addWorkspace: () => addWorkspaceFlow(actions),
  focusInUniverse(id) { pendingFocus = null; if (universeRef) universeRef.focusOn(id); else setTimeout(() => universeRef?.focusOn(id), 300); },
  applyTheme() {
    const ui = store.get('ui');
    const s = store.get('settings');
    const theme = ui.theme || s?.ui?.theme || 'dark';
    document.documentElement.dataset.theme = theme;
  },
  rerender() { route(true); },
};

// ------------------------------------------------------------------ shell widgets
function updateSideStats() {
  const stats = store.get('stats');
  const projects = store.get('projects');
  $('#side-total').textContent = String(stats?.total ?? projects.length);
  $('#side-ai').textContent = String(projects.filter(p => p.categories.includes('AI/ML')).length);
  const ws = store.get('workspaces');
  const last = Math.max(0, ...ws.map(w => w.last_scan_at || 0));
  $('#side-last-scan').textContent = last ? relativeTime(last) : t('never');
  $('#nav-project-count').textContent = projects.length ? String(projects.length) : '';
}

function updateWorkspaceCard() {
  const ws = store.get('workspaces');
  const id = store.get('workspaceId');
  const name = id === 'all' ? (ws.length > 1 ? t('workspace.all') : (ws[0]?.display_name || '—')) : (ws.find(w => w.id === id)?.display_name || t('workspace.all'));
  $('#workspace-name').textContent = ws.length ? name : t('settings.addFolder');
  $('#workspace-name').title = id === 'all' ? ws.map(w => w.root_path).join('\n') : (ws.find(w => w.id === id)?.root_path || '');
  updateSideStats();
}

function updateNav() {
  for (const a of $$('#main-nav a, #mobile-nav a')) a.setAttribute('aria-current', a.dataset.view === currentName ? 'page' : 'false');
}

function updateNotifications() {
  const n = store.get('notifications').length;
  const badge = $('#notif-count');
  badge.hidden = !n;
  badge.textContent = String(n);
}

function showNotifications() {
  const items = store.get('notifications');
  openModal(close => ({
    title: t('notif.title'),
    body: items.length ? items.map(nt => h('details', { class: 'evidence' }, h('summary', { text: `${nt.title} · ${relativeTime(nt.at / 1000)}` }), h('ul', { class: 'error-list' }, nt.items.slice(0, 200).map(x => h('li', { text: x }))))) : [h('div', { class: 'muted', text: t('notif.empty') })],
    footer: [h('button', { class: 'btn', type: 'button', onClick: () => { store.set('notifications', []); updateNotifications(); close(); } }, t('notif.clear')), h('button', { class: 'btn primary', type: 'button', onClick: () => close() }, t('common.close'))],
  }));
}

// ------------------------------------------------------------------ router
const VIEWS = { universe: mountUniverse, projects: mountProjects, graph: mountKnowledge, assistant: mountAssistant, settings: mountSettings };

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const params = new URLSearchParams(query || '');
  return { name: VIEWS[path] ? path : 'universe', project: params.get('project'), workspace: params.get('workspace') };
}

function route(force = false) {
  const { name, project, workspace } = parseHash();
  if (workspace && workspace !== store.get('workspaceId') && (workspace === 'all' || store.get('workspaces').some(w => w.id === workspace))) {
    store.set('workspaceId', workspace); store.persistUi(); actions.refreshProjects();
  }
  if (project && project !== store.get('selectedId')) { if (store.get('projects').some(p => p.id === project)) store.select(project, { push: false }); else pendingFocus = project; }
  if (name === currentName && !force) return;
  currentView?.destroy?.();
  clear(main);
  currentName = name;
  currentView = VIEWS[name](main, actions);
  if (name === 'universe') universeRef = currentView; else universeRef = null;
  updateNav();
  document.title = `${t('nav.' + name)} · Project Nexus`;
  main.focus({ preventScroll: true });
}

// ------------------------------------------------------------------ boot
async function boot() {
  const ui = store.get('ui');
  document.documentElement.dataset.theme = ui.theme || 'dark';
  try {
    const [session, { settings }] = await Promise.all([api.get('/api/session'), api.get('/api/settings')]);
    store.set('session', session);
    store.set('settings', settings);
    setLanguage(settings.ui.language);
    actions.applyTheme();
    if (!session.loopback) toast('Warning: the server is reachable from your network.', { kind: 'warn', timeout: 10000 });
    if (!session.git_available) toast('Git executable not found — branch/commit information will be unavailable.', { kind: 'warn', timeout: 8000 });
  } catch (err) {
    store.set('loading', false);
    toast(err.message, { kind: 'error', timeout: 0 });
  }
  const details = mountDetails(actions);
  scanWidget = mountScanWidget(actions);
  await actions.refreshWorkspaces();
  await actions.refreshProjects();
  store.set('loading', false);
  api.get('/api/ai/status').then(s => { store.set('aiStatus', s); store.set('pendingSuggestions', s.pending || 0); $('#nav-ai-count').textContent = s.pending ? String(s.pending) : ''; }).catch(() => {});
  store.on('pendingSuggestions', n => { $('#nav-ai-count').textContent = n ? String(n) : ''; });
  store.on('notifications', updateNotifications);
  store.on('workspaces', updateWorkspaceCard);
  store.on('workspaceId', updateWorkspaceCard);
  store.on('projects', updateSideStats);
  route();
  window.addEventListener('hashchange', () => route());
  if (!store.get('workspaces').length) setTimeout(() => { if (!anyModalOpen()) addWorkspaceFlow(actions); }, 600);

  // Shell controls: search box with ranked suggestions (↑/↓ + Enter jump to a project, Esc clears).
  const search = $('#global-search');
  const suggestBox = $('#search-suggestions');
  let active = -1, suggestions = [];
  function renderSuggestions() {
    clear(suggestBox);
    const q = search.value.trim();
    if (!q) { suggestBox.hidden = true; search.setAttribute('aria-expanded', 'false'); return; }
    suggestions = store.suggest(q, 8);
    if (!suggestions.length) {
      suggestBox.append(h('div', { class: 'no-match', text: t('search.noMatch') }));
    } else {
      suggestions.forEach((p, i) => suggestBox.append(h('button', { type: 'button', role: 'option', id: `suggest-${i}`, 'aria-selected': String(i === active), class: i === active ? 'active' : '', onMousedown: e => e.preventDefault(), onClick: () => actions.jumpTo(p.id) },
        h('span', { class: 'swatch', style: { '--accent': categoryColor(p) } }),
        h('span', { class: 'grow' }, h('b', { text: p.display_name, dir: 'auto' }), h('small', { text: `${p.categories.slice(0, 2).join(' / ')} · ${p.primary_language || '—'} · ${t('status.' + p.status)}` })),
        icon('i-chev'))));
    }
    suggestBox.hidden = false;
    search.setAttribute('aria-expanded', 'true');
    search.setAttribute('aria-activedescendant', active >= 0 ? `suggest-${active}` : '');
  }
  search.addEventListener('input', debounce(() => { active = -1; store.set('query', search.value.trim()); renderSuggestions(); }, 120));
  search.addEventListener('focus', renderSuggestions);
  search.addEventListener('blur', () => setTimeout(() => { suggestBox.hidden = true; search.setAttribute('aria-expanded', 'false'); }, 120));
  search.addEventListener('keydown', e => {
    if (e.key === 'Escape') { search.value = ''; active = -1; store.set('query', ''); renderSuggestions(); search.blur(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!suggestions.length) return;
      e.preventDefault();
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length;
      renderSuggestions();
      return;
    }
    if (e.key === 'Enter') {
      const pick = suggestions[active >= 0 ? active : 0];
      if (pick) { e.preventDefault(); actions.jumpTo(pick.id); search.blur(); }
    }
  });
  store.on('projects', () => { if (!suggestBox.hidden) renderSuggestions(); });
  $('#btn-theme').addEventListener('click', () => { const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; store.setUi({ theme: next }); actions.applyTheme(); universeRef?.requestFrame(); });
  $('#btn-notifications').addEventListener('click', showNotifications);
  $('#workspace-card').addEventListener('click', () => workspaceSwitcher(actions));
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); search.focus(); search.select(); return; }
    if (anyModalOpen() || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    if (e.key === '/') { e.preventDefault(); search.focus(); }
    if (e.key === 'Escape' && store.get('selectedEntry')) { store.set('selectedEntry', null); return; }
    if (e.key === 'Escape' && store.get('selectedId')) actions.select(null);
    if (e.key === '?' ) toast(t('kbd.help'), { timeout: 9000 });
  });
  onOffline(off => { store.set('offline', off); if (off) toast(t('common.offline'), { kind: 'error', timeout: 6000 }); else toast(t('common.online'), { kind: 'success', timeout: 2500 }); });

  // Close details sheet by clicking outside it on narrow screens
  document.addEventListener('click', e => {
    if (window.innerWidth > 1199) return;
    const panel = document.getElementById('details');
    if (!store.get('selectedId') || panel.contains(e.target) || e.target.closest('#modal-root, .toasts, canvas, .table, .sub-list, .universe-list')) return;
    if (e.target.closest('.stage') && !e.target.closest('button, a')) actions.select(null);
  });
  updateNotifications();
}

boot();
