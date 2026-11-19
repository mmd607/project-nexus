// Universe view: canvas scene + overlays + interaction + accessibility twin.
// One node per top-level folder. Selecting a project enters "focus": the camera glides to it,
// rotation pauses, everything else steps back and the project's internal parts appear as a few
// satellites around it (never as permanent nodes). Esc / the breadcrumb bring the universe back.
import { Camera } from './camera.js';
import { computeLayout, focusLayout, hash, layoutRadius } from './layout.js';
import { Renderer } from './render.js';
import { store, CATEGORY_COLORS, categoryColor, COMPONENT_COLORS, FILE_KIND_COLORS } from '../store.js';
import { h, icon, clear, on, append } from '../ui/dom.js';
import { t } from '../i18n.js';
import { relativeTime } from '../ui/format.js';
import { anyModalOpen } from '../ui/modal.js';

const TAU = Math.PI * 2;
const FOCUS_ZOOM = 1.8;

/** Internal parts worth showing around a focused project, most informative first (bounded by *max*). */
export function pickSatellites(project, max) {
  if (!project || max <= 0) return [];
  const out = [];
  const seen = new Set();
  const push = item => { if (item.path == null || seen.has(item.path)) return; seen.add(item.path); out.push(item); };
  for (const c of project.components || []) {
    if (!c.path) continue;   // root-level deployment evidence is listed as files below
    push({ id: 'c:' + c.path, label: c.name, sub: `${c.kind}${c.file_count ? ` · ${c.file_count} ${t('detail.files').toLowerCase()}` : ''}`,
      color: COMPONENT_COLORS[c.kind] || COMPONENT_COLORS.Module, type: 'dir', path: c.path, kind: c.kind });
  }
  const order = { readme: 0, entry: 1, manifest: 2, schema: 3, deploy: 4, ci: 5, agent: 6, api: 7, build: 8, license: 9, docs: 10, config: 11 };
  const files = [...(project.important_files || [])].filter(f => f.kind !== 'config').sort((a, b) => (order[a.kind] ?? 20) - (order[b.kind] ?? 20) || a.path.split('/').length - b.path.split('/').length);
  for (const f of files) {
    push({ id: 'f:' + f.path, label: f.path.split('/').pop(), sub: f.path.includes('/') ? f.path.split('/').slice(0, -1).join('/') + '/' : t('focus.kind.' + f.kind),
      color: FILE_KIND_COLORS[f.kind] || FILE_KIND_COLORS.other, type: 'file', path: f.path, kind: f.kind });
  }
  return out.slice(0, max);
}

export function mountUniverse(container, actions) {
  const root = h('div', { class: 'universe' });
  const canvas = h('canvas', { tabindex: '0', role: 'img', 'aria-label': 'Interactive project universe graph. Use arrow keys to move between projects, Enter to open one, Escape to return to the workspace.' });
  const vignette = h('div', { class: 'vignette' });
  const live = h('div', { class: 'sr-only', 'aria-live': 'polite', id: 'universe-live' });
  const tooltip = h('div', { class: 'node-tooltip', hidden: true, role: 'tooltip' });
  const hint = h('div', { class: 'canvas-hint', text: t('universe.hint') });
  const statsCard = h('div', { class: 'stats-card', role: 'group', 'aria-label': 'Project status summary' });
  const filterBar = h('div', { class: 'filter-bar', role: 'group', 'aria-label': 'Active filters' });
  const crumbs = h('nav', { class: 'crumbs', 'aria-label': 'Focus path', hidden: true });
  const perfBadge = h('div', { class: 'perf-badge', hidden: true });

  const btn = (label, iconName, onClick, extra = {}) => h('button', { type: 'button', 'aria-label': label, title: label, onClick, ...extra }, icon(iconName), extra.withText ? h('span', { text: label }) : null);
  const rotateBtn = btn(t('universe.rotate'), 'i-rotate', () => toggleRotation(), { withText: true, 'aria-pressed': 'true' });
  const listBtn = btn(t('universe.list'), 'i-list', () => toggleList(), { withText: true, 'aria-pressed': 'false' });
  const backBtn = btn(t('universe.back'), 'i-home', () => exitFocus(), { withText: true, class: 'back-btn', hidden: true });
  const controls = h('div', { class: 'graph-controls' },
    h('div', { class: 'dpad', role: 'group', 'aria-label': t('universe.pan') },
      btn(t('universe.panUp'), 'i-up', () => pan(0, 60), { class: 'up' }),
      btn(t('universe.panLeft'), 'i-left', () => pan(60, 0), { class: 'left' }),
      btn(t('universe.focus'), 'i-focus', () => focusSelected(), { class: 'center' }),
      btn(t('universe.panRight'), 'i-right', () => pan(-60, 0), { class: 'right' }),
      btn(t('universe.panDown'), 'i-down', () => pan(0, -60), { class: 'down' }),
    ),
    h('div', { class: 'control-list', role: 'group', 'aria-label': 'Graph controls' },
      rotateBtn,
      h('div', { class: 'zoom-row' },
        btn(t('universe.zoomIn'), 'i-zoom-in', () => zoomBy(1.25), { withText: true }),
        btn(t('universe.zoomOut'), 'i-zoom-out', () => zoomBy(1 / 1.25)),
      ),
      btn(t('universe.reset'), 'i-move', () => reset(), { withText: true }),
      listBtn,
      backBtn,
    ),
  );
  const mode3d = h('button', { type: 'button', 'aria-pressed': 'true', text: '3D', onClick: () => setMode('3d') });
  const mode2d = h('button', { type: 'button', 'aria-pressed': 'false', text: '2D', onClick: () => setMode('2d') });
  const modeToggle = h('div', { class: 'mode-toggle' },
    h('div', { class: 'segmented', role: 'group', 'aria-label': 'View mode' }, mode3d, mode2d),
    btn(t('universe.fullscreen'), 'i-fullscreen', () => toggleFullscreen(), { class: 'btn icon' }),
  );
  const listOverlay = h('div', { class: 'universe-list', hidden: true, role: 'region', 'aria-label': t('universe.list') });
  const emptyState = h('div', { class: 'universe-empty', hidden: true });
  const loadingState = h('div', { class: 'universe-loading', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), h('span', { text: t('common.loading') }));

  root.append(canvas, vignette, live, tooltip, hint, loadingState, statsCard, filterBar, crumbs, perfBadge, controls, modeToggle, listOverlay, emptyState);
  container.append(root);

  const camera = new Camera();
  const renderer = new Renderer(canvas);
  const state = {
    layout: new Map(), animated: new Map(), rotation: true, rotationSpeed: TAU / 240, reduced: false, particles: true,
    hover: null, hoverSat: null, focus: null, dirty: true, running: false, lastTs: 0, time: 0, mode: '3d', relations: [], showRelations: false,
    frames: 0, fpsAt: 0, fps: 0, listOpen: false, focusView: null, fitted: false, maxSatellites: 8,
  };

  // ------------------------------------------------------------- settings
  function applySettings() {
    const s = store.get('settings');
    const ui = store.get('ui');
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const pref = s?.ui?.reduced_motion || 'system';
    state.reduced = pref === 'on' || (pref === 'system' && media.matches);
    document.documentElement.dataset.motion = state.reduced ? 'off' : 'on';
    state.rotationSpeed = TAU / Math.max(20, s?.ui?.rotation_seconds_per_turn || 240);
    const rotation = ui.rotation ?? s?.ui?.rotation ?? true;
    state.rotation = rotation && !state.reduced;
    rotateBtn.setAttribute('aria-pressed', String(state.rotation));
    rotateBtn.querySelector('span').textContent = state.rotation ? t('universe.rotateOn') : t('universe.rotateOff');
    state.particles = s?.ui?.particles ?? true;
    state.maxSatellites = s?.ui?.focus_satellites ?? 8;
    setMode(ui.viewMode || s?.ui?.view_mode || '3d', false);
    perfBadge.hidden = !ui.perf;
    if (state.focusView) buildSatellites(store.get('selectedProject'));
    requestFrame();
  }

  function setMode(mode, persist = true) {
    state.mode = mode;
    camera.setFlat(mode === '2d');
    mode3d.setAttribute('aria-pressed', String(mode === '3d'));
    mode2d.setAttribute('aria-pressed', String(mode === '2d'));
    if (persist) store.setUi({ viewMode: mode });
    requestFrame();
  }

  function toggleRotation(force) {
    state.rotation = force ?? !state.rotation;
    if (state.reduced) state.rotation = false;
    rotateBtn.setAttribute('aria-pressed', String(state.rotation));
    rotateBtn.querySelector('span').textContent = state.rotation ? t('universe.rotateOn') : t('universe.rotateOff');
    store.setUi({ rotation: state.rotation });
    requestFrame();
  }

  /** Space taken by overlays at the top and bottom of the stage (stats card, controls …) so the universe can avoid them. */
  function viewportInsets() {
    const H = renderer.height || 1;
    let top = 0, bottom = 0;
    for (const r of reservedRects(performance.now())) {
      if (r.y + r.h / 2 < H / 2) top = Math.max(top, r.y + r.h); else bottom = Math.max(bottom, H - r.y);
    }
    // Only the wide overlays matter on small screens; a narrow control column beside empty space does not.
    return { top: Math.min(top, H * 0.35), bottom: Math.min(bottom, H * 0.45) };
  }

  /** Zoom that fits the whole layout into the free part of the viewport (with room for labels). */
  function fitZoom() {
    const radius = layoutRadius(state.layout) + 40;
    if (!radius || !renderer.width) return 1;
    const { top, bottom } = renderer.width < 700 ? viewportInsets() : { top: 0, bottom: 0 };
    const usableW = renderer.width / 2 - 50, usableH = (renderer.height - top - bottom) / 2 - (state.mode === '2d' ? 60 : 50);
    const vertical = state.mode === '2d' ? 1 : 0.86;
    const z = Math.min(usableW / (radius * camera.base), usableH / (radius * vertical * camera.base));
    return Math.max(0.3, Math.min(1.35, z));
  }
  /** Vertical pan that centres the hub in the free part of small viewports. */
  function fitPanY() {
    if (renderer.width >= 700) return 0;
    const { top, bottom } = viewportInsets();
    return (top - bottom) / 2;
  }

  function pan(dx, dy) { camera.targetPanX += dx; camera.targetPanY += dy; requestFrame(); }
  function zoomBy(f) { camera.zoomAt(f, renderer.width / 2, renderer.height / 2); requestFrame(); }
  function reset() { camera.reset(); camera.targetZoom = fitZoom(); camera.targetPanY = fitPanY(); requestFrame(); }
  /** Glide the camera to a node and zoom in on it (pan is computed for the zoom we are heading to). */
  function flyTo(id, zoom = FOCUS_ZOOM) {
    const pos = state.layout.get(id);
    if (!pos) return false;
    const target = Math.max(camera.targetZoom, zoom);
    camera.targetZoom = target;
    camera.focusOn(pos.x, pos.z, target, pos.y + pos.r * 0.9);
    camera.targetPanY += fitPanY();   // small screens: centre in the area not covered by the controls
    requestFrame();
    return true;
  }
  function focusSelected() {
    const id = store.get('selectedId') || state.focus;
    if (!id || !flyTo(id)) reset();
  }
  function toggleFullscreen() {
    const stage = container.closest('.stage') || container;
    if (document.fullscreenElement) document.exitFullscreen?.(); else stage.requestFullscreen?.();
  }
  function toggleList(force) {
    state.listOpen = force ?? !state.listOpen;
    listOverlay.hidden = !state.listOpen;
    listBtn.setAttribute('aria-pressed', String(state.listOpen));
    listBtn.querySelector('span').textContent = state.listOpen ? t('universe.listOff') : t('universe.list');
    if (state.listOpen) { renderList(); listOverlay.querySelector('button')?.focus(); }
  }

  // ------------------------------------------------------------- focus mode
  function enterFocus(id, { fly = true } = {}) {
    const already = state.focusView && state.focusView.id === id;
    state.focusView = already ? state.focusView : { id, satellites: [], progress: state.reduced ? 1 : 0, source: null };
    if (fly && state.fitted) flyTo(id);   // before the first sized frame the flight is deferred (see frame())
    const project = store.get('selectedProject');
    if (project && project.id === id) buildSatellites(project);
    refreshVisible();
    renderCrumbs();
    backBtn.hidden = false;
    requestFrame();
  }

  function exitFocus() {
    if (!state.focusView && !store.get('selectedId')) { reset(); return; }
    state.focusView = null;
    state.hoverSat = null;
    tooltip.hidden = true;
    if (store.get('selectedEntry')) store.set('selectedEntry', null);
    if (store.get('selectedId')) actions.select(null);
    refreshVisible();
    renderCrumbs();
    backBtn.hidden = true;
    reset();
  }

  function buildSatellites(project) {
    const view = state.focusView;
    if (!view || !project || project.id !== view.id) return;
    const pos = state.layout.get(view.id);
    if (!pos) return;
    const items = pickSatellites(project, state.maxSatellites);
    const positions = focusLayout(pos, items.length);
    view.satellites = items.map((s, i) => ({ ...s, pos: positions[i] }));
    view.source = project;
    view.total = (project.components || []).filter(c => c.path).length + (project.important_files || []).length;
    renderCrumbs();
    requestFrame();
  }

  function renderCrumbs() {
    clear(crumbs);
    const view = state.focusView;
    if (!view) { crumbs.hidden = true; return; }
    const project = store.project(view.id) || view.source;
    const entry = store.get('selectedEntry');
    const ws = currentWorkspaceLabel();
    crumbs.hidden = false;
    append(crumbs, [
      h('button', { type: 'button', class: 'crumb', onClick: () => exitFocus(), title: t('universe.back') }, icon('i-home'), h('span', { text: ws })),
      h('span', { class: 'sep', 'aria-hidden': 'true', text: '›' }),
      h('button', { type: 'button', class: 'crumb' + (entry ? '' : ' current'), 'aria-current': entry ? null : 'true', onClick: () => { if (entry) store.set('selectedEntry', null); } },
        h('span', { class: 'swatch', style: { '--accent': project ? categoryColor(project) : '#fff' } }), h('span', { text: project?.display_name || '…' })),
      entry ? h('span', { class: 'sep', 'aria-hidden': 'true', text: '›' }) : null,
      entry ? h('span', { class: 'crumb current', 'aria-current': 'true' }, icon(entry.type === 'dir' ? 'i-folder' : 'i-file'), h('span', { text: entry.label || entry.path })) : null,
      view.satellites.length ? h('span', { class: 'crumb-note', text: t('focus.showing', view.satellites.length, view.total || view.satellites.length) }) : null,
    ]);
  }

  // ------------------------------------------------------------- data → layout
  function rebuildLayout() {
    refreshVisible();
    const projects = store.get('projects');
    const next = computeLayout(projects, { cluster: projects.length > 24 });
    // animate from previous positions
    for (const [id, pos] of next) {
      const prev = state.animated.get(id);
      state.animated.set(id, prev ? { ...prev, tx: pos.x, ty: pos.y, tz: pos.z } : { x: pos.x, y: pos.y, z: pos.z, tx: pos.x, ty: pos.y, tz: pos.z, alpha: 1, ta: 1 });
    }
    for (const id of [...state.animated.keys()]) if (!next.has(id)) state.animated.delete(id);
    state.layout = next;
    state.relations = (store.get('relations') || []).filter(r => r.type === 'shared_technology').map(r => ({ a: r.source_id, b: r.target_id, weight: r.weight }));
    // Re-fit when the universe changed size a lot (first scan finishing, workspace switch) and nothing is in focus.
    if (state.fitted && !state.focusView && state.fittedFor && Math.abs(next.size - state.fittedFor) > Math.max(3, state.fittedFor * 0.3)) { camera.targetZoom = fitZoom(); state.fittedFor = next.size; }
    if (state.focusView) {
      if (!next.has(state.focusView.id)) { state.focusView = null; backBtn.hidden = true; }
      else buildSatellites(store.get('selectedProject'));
    }
    renderStats();
    renderFilterBar();
    renderEmpty();
    renderCrumbs();
    if (state.listOpen) renderList();
    requestFrame();
  }

  function updateAlphaTargets() {
    const visibleIds = visibleCache.ids;
    const focusId = state.focusView?.id || null;
    const byId = new Map(store.get('projects').map(p => [p.id, p]));
    for (const [id, a] of state.animated) {
      let target = visibleIds.has(id) ? 1 : 0.14;
      if (focusId && target === 1 && id !== focusId) {
        const p = byId.get(id);
        const related = p && (p.parent_id === focusId || byId.get(focusId)?.parent_id === id);
        target = related ? 0.8 : 0.36;
      }
      a.ta = target;
    }
  }

  function animateLayout(dt) {
    let moving = false;
    const k = state.reduced ? 1 : 1 - Math.pow(0.002, dt);
    const ka = state.reduced ? 1 : 1 - Math.pow(0.01, dt);
    for (const a of state.animated.values()) {
      const dx = a.tx - a.x, dy = a.ty - a.y, dz = a.tz - a.z;
      if (Math.abs(dx) + Math.abs(dy) + Math.abs(dz) > 0.05) { a.x += dx * k; a.y += dy * k; a.z += dz * k; moving = true; }
      else { a.x = a.tx; a.y = a.ty; a.z = a.tz; }
      const da = (a.ta ?? 1) - (a.alpha ?? 1);
      if (Math.abs(da) > 0.005) { a.alpha = (a.alpha ?? 1) + da * ka; moving = true; } else a.alpha = a.ta ?? 1;
    }
    const view = state.focusView;
    if (view && view.progress < 1) { view.progress = state.reduced ? 1 : Math.min(1, view.progress + dt * 2.2); moving = true; }
    return moving;
  }

  const visibleCache = { list: [], ids: new Set(), cats: new Set() };
  function refreshVisible() {
    visibleCache.list = store.visibleProjects();
    visibleCache.ids = new Set(visibleCache.list.map(p => p.id));
    visibleCache.cats = new Set(visibleCache.list.flatMap(p => p.categories));
    updateAlphaTargets();
  }
  function sceneNodes() {
    const projects = store.get('projects');
    const selected = store.get('selectedId');
    const byId = new Map(projects.map(p => [p.id, p]));
    const nodes = [];
    for (const p of projects) {
      const pos = state.layout.get(p.id);
      const anim = state.animated.get(p.id);
      if (!pos || !anim) continue;
      if (p.parent_id && byId.has(p.parent_id) && !p.parentName) p.parentName = byId.get(p.parent_id).name;
      if (anim.h == null) anim.h = hash(p.id);
      nodes.push({ id: p.id, project: p, h: anim.h, pos: { ...pos, x: anim.x, y: anim.y, z: anim.z }, alpha: anim.alpha ?? 1, visible: visibleCache.ids.has(p.id), selected: p.id === selected, hovered: p.id === state.hover, focused: p.id === state.focus });
    }
    return nodes;
  }
  function sceneFocus() {
    const view = state.focusView;
    if (!view) return null;
    const entry = store.get('selectedEntry');
    return { id: view.id, progress: view.progress, satellites: view.satellites.map(s => ({ ...s, selected: !!entry && entry.path === s.path, hovered: state.hoverSat === s.id })) };
  }

  // ------------------------------------------------------------- render loop
  function requestFrame() { state.dirty = true; if (!state.running) { state.running = true; requestAnimationFrame(frame); } }

  function frame(ts) {
    if (!root.isConnected) { state.running = false; return; }
    const dt = Math.min(0.1, state.lastTs ? (ts - state.lastTs) / 1000 : 0.016);
    state.lastTs = ts;
    const rect = root.getBoundingClientRect();
    const resized = Math.round(rect.width) !== Math.round(renderer.width) || Math.round(rect.height) !== Math.round(renderer.height);
    renderer.resize(Math.max(1, rect.width), Math.max(1, rect.height));
    camera.setViewport(renderer.width, renderer.height);
    if (!state.fitted && renderer.width > 1 && state.layout.size) {
      // First sized frame: show the whole universe, or fly straight to the project restored from the URL.
      state.fitted = true;
      state.fittedFor = state.layout.size;
      if (state.focusView) { camera.zoom = camera.targetZoom = FOCUS_ZOOM; flyTo(state.focusView.id); camera.panX = camera.targetPanX; camera.panY = camera.targetPanY; }
      else { camera.targetZoom = fitZoom(); camera.zoom = camera.targetZoom; camera.panY = camera.targetPanY = fitPanY(); }
    } else if (resized && state.fitted && !state.focusView && Math.abs(camera.targetZoom - fitZoom()) > 0.4) camera.targetZoom = fitZoom();
    const hidden = document.hidden;
    let animating = false;
    if (!hidden) {
      const rotating = state.rotation && !state.reduced && !state.listOpen && !state.focusView;
      if (rotating) { camera.targetYaw += state.rotationSpeed * dt; camera.yaw += state.rotationSpeed * dt; animating = true; }
      const camMoving = camera.update(dt);
      const layoutMoving = animateLayout(dt);
      const pulse = !state.reduced && (store.get('selectedId') || state.focus);
      animating = animating || camMoving || layoutMoving || !!pulse;
      state.time += dt;
      const projects = store.get('projects');
      const ws = currentWorkspaceLabel();
      const visible = visibleCache.list;
      const cats = visibleCache.cats;
      const drawStart = performance.now();
      renderer.draw({
        camera, nodes: sceneNodes(), hubLabel: ws, hubSub: t('universe.projects', visible.length, cats.size), time: state.time,
        rotationOn: rotating, reducedMotion: state.reduced, particles: state.particles && !state.reduced,
        showRelations: state.showRelations, relations: state.relations, maxLabels: projects.length > 90 ? 28 : projects.length > 45 ? 40 : 80,
        theme: document.documentElement.dataset.theme || 'dark', focus: sceneFocus(), reserved: reservedRects(ts),
      });
      state.lastFrameMs = performance.now() - drawStart;
      state.frames++;
      if (ts - state.fpsAt > 1000) { state.fps = state.frames; state.frames = 0; state.fpsAt = ts; if (!perfBadge.hidden) perfBadge.textContent = `${state.fps} fps · ${state.lastFrameMs.toFixed(1)} ms/frame · ${projects.length} nodes · ${renderer.labelRects.length} labels`; }
      state.dirty = false;
    }
    if (animating || state.dirty) requestAnimationFrame(frame); else state.running = false;
  }

  // Overlay boxes (canvas coordinates) that labels must avoid; refreshed a few times a second, not every frame.
  const reservedCache = { at: 0, rects: [] };
  function reservedRects(ts) {
    if (ts - reservedCache.at < 400) return reservedCache.rects;
    reservedCache.at = ts;
    const base = root.getBoundingClientRect();
    const rects = [];
    for (const el of [statsCard, filterBar, crumbs, controls, modeToggle, perfBadge]) {
      if (el.hidden || !el.offsetParent && el !== controls) continue;
      const r = el.getBoundingClientRect();
      if (r.width && r.height) rects.push({ x: r.left - base.left - 4, y: r.top - base.top - 4, w: r.width + 8, h: r.height + 8 });
    }
    reservedCache.rects = rects;
    return rects;
  }

  function currentWorkspaceLabel() {
    const id = store.get('workspaceId');
    const ws = store.get('workspaces');
    if (id === 'all' || !ws.length) return ws.length > 1 ? t('workspace.all') : (ws[0]?.display_name || 'MyProjects');
    return ws.find(w => w.id === id)?.display_name || 'MyProjects';
  }

  // ------------------------------------------------------------- overlays
  function renderStats() {
    const visible = store.visibleProjects();
    const count = s => visible.filter(p => p.status === s).length;
    const filters = store.get('filters');
    clear(statsCard);
    const cell = (label, value, color, status) => h('button', {
      type: 'button', 'aria-pressed': String(filters.status === status && !!status), title: status ? `${t('filter.search', status)}` : '',
      onClick: () => actions.setFilter('status', filters.status === status ? null : status),
    }, h('b', { text: String(value), style: color ? { color } : {} }), h('small', { text: label }));
    statsCard.append(
      cell(t('stats.totalShort'), visible.length, null, null),
      cell(t('stats.active'), count('Active'), '#65dba0', 'Active'),
      cell(t('stats.idle'), count('Idle'), '#ffae5b', 'Idle'),
      cell(t('stats.attention'), count('Needs attention'), '#fa2559', 'Needs attention'),
    );
    statsCard.hidden = !store.get('ui').showStats || !store.get('projects').length;
  }

  function renderFilterBar() {
    clear(filterBar);
    const filters = store.get('filters');
    const q = store.get('query');
    const chip = (label, color, onRemove) => h('span', { class: 'chip cat', style: { '--chip-color': color || 'var(--text-muted)' } },
      h('span', { class: 'dot' }), h('span', { text: label }),
      h('button', { type: 'button', 'aria-label': t('filter.clear') + ': ' + label, onClick: onRemove }, icon('i-x')));
    if (q) filterBar.append(chip(t('filter.search', q), '#ffffff', () => actions.setQuery('')));
    if (filters.category) filterBar.append(chip(filters.category, CATEGORY_COLORS[filters.category], () => actions.setFilter('category', null)));
    if (filters.status) filterBar.append(chip(t('status.' + filters.status), null, () => actions.setFilter('status', null)));
    if (filters.language) filterBar.append(chip(filters.language, '#67ccfa', () => actions.setFilter('language', null)));
    const projects = store.get('projects');
    if (projects.length > 1) {
      const relBtn = h('button', { type: 'button', class: 'chip clickable', 'aria-pressed': String(state.showRelations), onClick: () => { state.showRelations = !state.showRelations; relBtn.setAttribute('aria-pressed', String(state.showRelations)); requestFrame(); } },
        icon('i-graph'), h('span', { text: t('graph.showRel') }));
      filterBar.append(relBtn);
    }
    const visible = store.visibleProjects();
    if (projects.length && !visible.length) filterBar.append(h('span', { class: 'chip', text: t('universe.noMatch') }));
  }

  function renderEmpty() {
    const projects = store.get('projects');
    const workspaces = store.get('workspaces');
    const run = store.get('activeRun');
    clear(emptyState);
    loadingState.hidden = !store.get('loading');
    if (projects.length || (run && run.status === 'running') || store.get('loading')) { emptyState.hidden = true; return; }
    emptyState.hidden = false;
    emptyState.append(h('div', { class: 'card' },
      h('h2', { text: workspaces.length ? t('universe.noMatch').replace(/\.$/, '') : t('universe.empty.title') }),
      h('p', { class: 'muted', text: workspaces.length ? '' : t('universe.empty.body') }),
      h('button', { class: 'btn primary', type: 'button', onClick: () => workspaces.length ? actions.scanAll() : actions.addWorkspace() }, icon(workspaces.length ? 'i-refresh' : 'i-plus'), workspaces.length ? t('scan.startAll') : t('universe.empty.cta')),
    ));
  }

  function renderList() {
    clear(listOverlay);
    const visible = store.visibleProjects();
    const selected = store.get('selectedId');
    listOverlay.append(h('div', { class: 'view-header' }, h('h2', { text: t('universe.list') }), h('button', { class: 'btn sm', type: 'button', onClick: () => toggleList(false) }, icon('i-x'), t('universe.listOff'))));
    const ul = h('ul', { class: 'sub-list', role: 'list' });
    for (const p of visible) {
      ul.append(h('li', {}, h('button', { type: 'button', 'aria-current': p.id === selected ? 'true' : null, onClick: () => { actions.select(p.id); } },
        h('span', { class: 'proj-name' }, h('span', { class: 'swatch', style: { '--accent': categoryColor(p) } }), h('b', { text: p.display_name })),
        h('span', { class: 'muted', text: `${p.categories.join(', ')} · ${t('status.' + p.status)} · ${relativeTime(p.last_modified)}` }))));
    }
    if (!visible.length) ul.append(h('li', { class: 'empty', text: t('universe.noMatch') }));
    listOverlay.append(ul);
  }

  function showTooltip(id) {
    const p = store.project(id);
    const pos = renderer.screenPosition(id);
    if (!p || !pos) { tooltip.hidden = true; return; }
    clear(tooltip);
    const parts = (p.components || []).map(c => c.kind).filter((k, i, a) => a.indexOf(k) === i).slice(0, 4);
    tooltip.append(h('b', { text: p.display_name }), h('span', { text: `${p.categories.join(' / ')} · ${p.primary_language || '—'}` }),
      h('span', { text: `${t('status.' + p.status)} · ${p.file_count_total ?? p.file_count} ${t('detail.files').toLowerCase()} · ${relativeTime(p.last_modified)}` }),
      parts.length ? h('span', { text: `${t('detail.components')}: ${parts.join(', ')}` }) : null);
    tooltip.style.left = `${pos.x}px`;
    tooltip.style.top = `${pos.y - pos.r}px`;
    tooltip.hidden = false;
  }
  function showSatelliteTooltip(satId) {
    const s = state.focusView?.satellites.find(x => x.id === satId);
    const pos = renderer.screenPosition('sat:' + satId);
    if (!s || !pos) { tooltip.hidden = true; return; }
    clear(tooltip);
    tooltip.append(h('b', { text: s.label }), h('span', { text: s.sub || '' }), h('span', { class: 'mono', text: s.path }), h('span', { text: t('focus.clickHint') }));
    tooltip.style.left = `${pos.x}px`;
    tooltip.style.top = `${pos.y - pos.r}px`;
    tooltip.hidden = false;
  }

  // ------------------------------------------------------------- interaction
  const pointers = new Map();
  let drag = null, pinchDist = 0, lastMoveHover = 0;
  function hitAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    return renderer.hitTest(clientX - rect.left, clientY - rect.top);
  }
  function activate(id) {
    if (!id) return;
    if (id === '__hub__') { exitFocus(); return; }
    if (id.startsWith('sat:')) {
      const s = state.focusView?.satellites.find(x => 'sat:' + x.id === id);
      if (s) store.set('selectedEntry', { projectId: state.focusView.id, path: s.path, type: s.type, label: s.label, kind: s.kind });
      return;
    }
    if (store.get('selectedEntry')) store.set('selectedEntry', null);
    actions.select(id);
  }
  canvas.addEventListener('pointerdown', e => {
    canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) drag = { x: e.clientX, y: e.clientY, px: camera.targetPanX, py: camera.targetPanY, yaw: camera.targetYaw, moved: false, orbit: e.button === 2 || e.button === 1 || e.shiftKey || e.altKey };
    if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinchDist = Math.hypot(a.x - b.x, a.y - b.y); }
    canvas.focus({ preventScroll: true });
  });
  canvas.addEventListener('pointermove', e => {
    const rect = canvas.getBoundingClientRect();
    if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchDist) camera.zoomAt(d / pinchDist, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      pinchDist = d;
      if (drag) drag.moved = true;
      requestFrame();
      return;
    }
    if (drag && (e.buttons & 7)) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.orbit) { camera.targetYaw = drag.yaw + dx * 0.006; camera.yaw = camera.targetYaw; }
      else { camera.targetPanX = drag.px + dx; camera.targetPanY = drag.py + dy; camera.panX = camera.targetPanX; camera.panY = camera.targetPanY; }
      canvas.classList.add('dragging');
      requestFrame();
      return;
    }
    const now = performance.now();
    if (now - lastMoveHover < 40) return;
    lastMoveHover = now;
    const id = renderer.hitTest(e.clientX - rect.left, e.clientY - rect.top);
    canvas.classList.toggle('hovering', !!id);
    if (id && id.startsWith('sat:')) {
      const satId = id.slice(4);
      if (satId !== state.hoverSat || state.hover) { state.hover = null; state.hoverSat = satId; requestFrame(); }
      showSatelliteTooltip(satId);
      return;
    }
    const next = id && id !== '__hub__' ? id : null;
    if (next !== state.hover || state.hoverSat) { state.hover = next; state.hoverSat = null; if (next) showTooltip(next); else tooltip.hidden = true; requestFrame(); }
    else if (next) showTooltip(next);
  });
  const endPointer = e => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchDist = 0;
    if (!drag) return;
    if (!drag.moved && e.type === 'pointerup') activate(hitAt(e.clientX, e.clientY));
    drag = null;
    canvas.classList.remove('dragging');
  };
  canvas.addEventListener('pointerup', endPointer);
  canvas.addEventListener('pointercancel', endPointer);
  canvas.addEventListener('pointerleave', () => { state.hover = null; state.hoverSat = null; tooltip.hidden = true; requestFrame(); });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  canvas.addEventListener('dblclick', e => {
    const id = hitAt(e.clientX, e.clientY);
    if (id && id !== '__hub__' && !id.startsWith('sat:')) { actions.select(id); flyTo(id, 2.1); }
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0016));
    camera.zoomAt(factor, e.clientX - rect.left, e.clientY - rect.top);
    requestFrame();
  }, { passive: false });

  function orderedIds() {
    const visible = store.visibleProjects();
    const items = visible.map(p => { const pos = state.layout.get(p.id); return { id: p.id, a: pos ? Math.atan2(pos.z, pos.x) + camera.yaw : 0, name: p.display_name }; });
    return { byAngle: items.sort((x, y) => ((x.a % TAU + TAU) % TAU) - ((y.a % TAU + TAU) % TAU)).map(x => x.id), byName: items.sort((x, y) => x.name.localeCompare(y.name)).map(x => x.id) };
  }
  function moveFocus(list, delta) {
    if (!list.length) return;
    const current = state.focus || store.get('selectedId');
    const idx = list.indexOf(current);
    const next = list[((idx < 0 ? (delta > 0 ? -1 : 0) : idx) + delta + list.length) % list.length];
    state.focus = next;
    const p = store.project(next);
    if (p) live.textContent = `${p.display_name}. ${p.categories.join(', ')}. ${t('status.' + p.status)}.`;
    const pos = state.layout.get(next);
    if (pos) camera.focusOn(pos.x, pos.z);
    showTooltip(next);
    requestFrame();
  }
  canvas.addEventListener('keydown', e => {
    if (anyModalOpen()) return;
    const { byAngle, byName } = orderedIds();
    const map = {
      ArrowRight: () => e.shiftKey ? pan(-60, 0) : moveFocus(byAngle, 1), ArrowLeft: () => e.shiftKey ? pan(60, 0) : moveFocus(byAngle, -1),
      ArrowDown: () => e.shiftKey ? pan(0, -60) : moveFocus(byName, 1), ArrowUp: () => e.shiftKey ? pan(0, 60) : moveFocus(byName, -1),
      Enter: () => { if (state.focus) activate(state.focus); }, ' ': () => { if (state.focus) activate(state.focus); },
      Escape: () => { state.focus = null; tooltip.hidden = true; if (store.get('selectedEntry')) store.set('selectedEntry', null); else exitFocus(); requestFrame(); },
      Backspace: () => { if (store.get('selectedEntry')) store.set('selectedEntry', null); else exitFocus(); },
      '+': () => zoomBy(1.25), '=': () => zoomBy(1.25), '-': () => zoomBy(1 / 1.25), '0': () => reset(), 'r': () => toggleRotation(), 'R': () => toggleRotation(),
      'f': () => focusSelected(), 'F': () => focusSelected(), 'l': () => toggleList(), 'L': () => toggleList(), '2': () => setMode('2d'), '3': () => setMode('3d'),
      '[': () => { camera.rotate(-0.15); requestFrame(); }, ']': () => { camera.rotate(0.15); requestFrame(); }, 'Home': () => reset(),
    };
    const fn = map[e.key];
    if (fn) { e.preventDefault(); e.stopPropagation(); fn(); }
  });
  canvas.addEventListener('blur', () => { tooltip.hidden = true; });

  const ro = new ResizeObserver(() => requestFrame());
  ro.observe(root);
  const unsubs = [
    store.on('projects', rebuildLayout), store.on('relations', rebuildLayout),
    store.on('selectedId', id => {
      state.focus = id;
      if (id && state.layout.has(id)) enterFocus(id);
      else if (id) { state.focusView = { id, satellites: [], progress: 0, source: null }; renderCrumbs(); backBtn.hidden = false; }
      else if (state.focusView) { state.focusView = null; backBtn.hidden = true; renderCrumbs(); reset(); }
      refreshVisible();
      requestFrame();
    }),
    store.on('selectedProject', p => { if (p && state.focusView && p.id === state.focusView.id) buildSatellites(p); }),
    store.on('selectedEntry', () => { renderCrumbs(); requestFrame(); }),
    store.on('query', () => { refreshVisible(); renderStats(); renderFilterBar(); renderEmpty(); if (state.listOpen) renderList(); requestFrame(); }),
    store.on('filters', () => { refreshVisible(); renderStats(); renderFilterBar(); renderEmpty(); if (state.listOpen) renderList(); requestFrame(); }),
    store.on('settings', applySettings), store.on('workspaceId', () => { renderCrumbs(); requestFrame(); }), store.on('workspaces', () => { renderEmpty(); renderCrumbs(); requestFrame(); }),
    store.on('activeRun', renderEmpty), store.on('loading', renderEmpty), store.on('ui', () => { statsCard.hidden = !store.get('ui').showStats || !store.get('projects').length; perfBadge.hidden = !store.get('ui').perf; requestFrame(); }),
    on(document, 'visibilitychange', () => { if (!document.hidden) requestFrame(); }),
    on(window.matchMedia('(prefers-reduced-motion: reduce)'), 'change', applySettings),
  ];
  applySettings();
  rebuildLayout();
  if (store.get('selectedId')) { state.focus = store.get('selectedId'); enterFocus(store.get('selectedId')); }
  // Debug hooks (only with the perf badge on): inspect camera/focus state, render N frames synchronously and report CPU time per frame.
  if (store.get('ui').perf) {
    window.__nexusDebug = () => ({ progress: state.focusView?.progress, sats: state.focusView?.satellites.length, running: state.running, fitted: state.fitted, zoom: camera.zoom, targetZoom: camera.targetZoom, pan: [camera.panX, camera.panY], insets: viewportInsets(), size: [renderer.width, renderer.height] });
    window.__nexusPerf = (n = 30) => {
      const rect = root.getBoundingClientRect();
      renderer.resize(Math.max(1, rect.width), Math.max(1, rect.height));
      camera.setViewport(renderer.width, renderer.height);
      const times = [];
      for (let i = 0; i < n; i++) {
        camera.yaw += 0.01; state.time += 0.016;
        const t0 = performance.now();
        renderer.draw({ camera, nodes: sceneNodes(), hubLabel: 'perf', hubSub: '', time: state.time, rotationOn: true, reducedMotion: false, particles: state.particles, showRelations: state.showRelations, relations: state.relations, maxLabels: 40, theme: document.documentElement.dataset.theme || 'dark', focus: sceneFocus() });
        times.push(performance.now() - t0);
      }
      times.sort((a, b) => a - b);
      return { nodes: store.get('projects').length, medianMs: +times[Math.floor(n / 2)].toFixed(2), p90Ms: +times[Math.floor(n * 0.9)].toFixed(2), maxMs: +times[n - 1].toFixed(2), canvas: [renderer.canvas.width, renderer.canvas.height], labels: renderer.labelRects.length };
    };
  }

  return {
    destroy() { for (const u of unsubs) u(); ro.disconnect(); root.remove(); },
    focusOn(id) { flyTo(id); },
    requestFrame,
  };
}
