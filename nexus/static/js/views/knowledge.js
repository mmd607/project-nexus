// Knowledge Graph: force-directed bipartite graph (projects ↔ technologies/categories)
// plus real project–project relations. Every edge has evidence; a text table mirrors it.
import { api } from '../api.js';
import { store, CATEGORY_COLORS, categoryColor } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t } from '../i18n.js';
import { glowSprite, rgba, roundRect } from '../universe/sprites.js';
import { hash } from '../universe/layout.js';

export function mountKnowledge(container, actions) {
  const view = h('div', { class: 'view no-pad' });
  container.append(view);
  const canvas = h('canvas', { tabindex: '0', role: 'img', 'aria-label': t('graph.title') });
  const canvasWrap = h('div', { class: 'kg-canvas-wrap' }, canvas,
    h('div', { class: 'kg-legend' },
      h('span', {}, h('i', { style: { background: '#fa315d' } }), t('graph.legend.project')),
      h('span', {}, h('i', { style: { background: '#67ccfa' } }), t('graph.legend.tech')),
      h('span', {}, h('i', { style: { background: '#ffe66d' } }), t('graph.legend.cat'))));
  const tooltip = h('div', { class: 'node-tooltip', hidden: true });
  canvasWrap.append(tooltip);
  const showTech = h('input', { type: 'checkbox', checked: true });
  const showCat = h('input', { type: 'checkbox', checked: true });
  const showRel = h('input', { type: 'checkbox', checked: true });
  const minShared = h('input', { class: 'input', type: 'number', min: '1', max: '20', value: '2', style: { width: '80px' } });
  const listBox = h('details', { class: 'kg-list' }, h('summary', { text: t('graph.edges') }));
  const layout = h('div', { class: 'kg-layout' },
    h('div', { class: 'kg-toolbar' },
      h('div', {}, h('h2', { text: t('graph.title') }), h('p', { class: 'muted', style: { fontSize: '12px' }, text: t('graph.subtitle') })),
      h('span', { class: 'grow' }),
      h('label', { class: 'checkbox' }, showTech, h('span', { text: t('graph.showTech') })),
      h('label', { class: 'checkbox' }, showCat, h('span', { text: t('graph.showCat') })),
      h('label', { class: 'checkbox' }, showRel, h('span', { text: t('graph.showRel') })),
      h('label', { class: 'checkbox' }, h('span', { text: t('graph.minShared') }), minShared),
      h('button', { class: 'btn sm', type: 'button', onClick: () => load() }, icon('i-refresh'))),
    canvasWrap, listBox);
  view.append(layout);

  const ctx = canvas.getContext('2d');
  let nodes = [], edges = [], sim = null, running = false, hover = null, drag = null, dragged = false, pan = { x: 0, y: 0 }, zoom = 1;
  let reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.motion === 'off';
  let width = 1, height = 1, dpr = 1, ticks = 0, needsFit = false;

  function fit() {
    if (!nodes.length || width < 10) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of nodes) { minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x); minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y); }
    const bw = Math.max(1, maxX - minX + 160), bh = Math.max(1, maxY - minY + 160);
    zoom = Math.max(0.3, Math.min(1.4, Math.min(width / bw, height / bh)));
    pan = { x: -((minX + maxX) / 2) * zoom, y: -((minY + maxY) / 2) * zoom };
  }

  async function load() {
    try {
      const ws = store.get('workspaceId');
      const data = await api.get('/api/graph', { workspace: ws === 'all' ? '' : ws, min_shared: minShared.value });
      build(data);
    } catch (err) { clear(listBox); listBox.append(h('summary', { text: t('graph.edges') }), h('div', { class: 'note danger', text: err.message })); }
  }

  function build(data) {
    const allowedTypes = new Set(['project']);
    if (showTech.checked) allowedTypes.add('technology');
    if (showCat.checked) allowedTypes.add('category');
    const prev = new Map(nodes.map(n => [n.id, n]));
    nodes = data.nodes.filter(n => allowedTypes.has(n.type)).map(n => {
      const p = prev.get(n.id);
      const seed = hash(n.id);
      const r = n.type === 'project' ? 9 + Math.min(8, Math.log2(1 + (n.file_count || 0)) * 0.8) : n.type === 'technology' ? 6 + Math.min(10, (n.degree || 1) * 1.2) : 14;
      return { ...n, r, x: p ? p.x : (seed - 0.5) * 600, y: p ? p.y : (hash(n.id + 'y') - 0.5) * 400, vx: 0, vy: 0 };
    });
    const ids = new Set(nodes.map(n => n.id));
    edges = data.edges.filter(e => ids.has(e.source) && ids.has(e.target) && (showRel.checked || (e.type === 'uses' || e.type === 'category')));
    const byId = new Map(nodes.map(n => [n.id, n]));
    for (const e of edges) { e.a = byId.get(e.source); e.b = byId.get(e.target); }
    renderList();
    ticks = 0;
    // Warm up so the first frame is already readable (more when motion is reduced).
    for (let i = 0; i < (reduced ? 400 : 120); i++) step();
    needsFit = true;
    start();
  }

  function step() {
    const k = 0.9;
    // repulsion (O(n²) but n is small: hundreds)
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let d2 = dx * dx + dy * dy + 0.01;
        if (d2 > 250000) continue;
        const f = 5200 / d2;
        const d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
      }
    }
    for (const e of edges) {
      const a = e.a, b = e.b;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
      const target = e.type === 'contains' ? 70 : e.type === 'category' ? 190 : e.type === 'uses' ? 140 : 200;
      const f = (d - target) * 0.01 * (e.type === 'shared_technology' ? 0.35 : 1);
      a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
    }
    for (const n of nodes) {
      n.vx -= n.x * 0.0018; n.vy -= n.y * 0.0018;   // gentle gravity to centre
      if (n === drag?.node) { n.vx = 0; n.vy = 0; continue; }
      n.vx *= k; n.vy *= k;
      n.x += Math.max(-12, Math.min(12, n.vx)); n.y += Math.max(-12, Math.min(12, n.vy));
    }
    ticks++;
  }

  function start() { if (!running) { running = true; requestAnimationFrame(frame); } }
  function frame() {
    if (!view.isConnected) { running = false; return; }
    const rect = canvasWrap.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (rect.width !== width || rect.height !== height) { width = rect.width; height = rect.height; canvas.width = width * dpr; canvas.height = height * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    let energy = 0;
    if (!reduced || ticks < 300) { for (let i = 0; i < 2; i++) step(); for (const n of nodes) energy += Math.abs(n.vx) + Math.abs(n.vy); }
    if (needsFit) { fit(); needsFit = false; }
    else if (ticks < 400 && ticks % 20 === 0) fit();   // keep framing while the layout settles
    draw();
    if ((energy > 0.5 && ticks < 2000) || drag) requestAnimationFrame(frame); else running = false;
  }

  function toScreen(n) { return { x: width / 2 + pan.x + n.x * zoom, y: height / 2 + pan.y + n.y * zoom }; }

  function draw() {
    const dark = document.documentElement.dataset.theme !== 'light';
    ctx.clearRect(0, 0, width, height);
    const selected = store.get('selectedId');
    for (const e of edges) {
      const a = toScreen(e.a), b = toScreen(e.b);
      const involved = e.a.id === selected || e.b.id === selected || e.a.id === hover || e.b.id === hover;
      const color = e.type === 'contains' ? '#ff7ac6' : e.type === 'category' ? '#ffe66d' : e.type === 'uses' ? '#67ccfa' : e.type === 'local_dependency' ? '#5fe497' : '#af61ff';
      ctx.strokeStyle = rgba(color, involved ? 0.85 : (dark ? 0.18 : 0.3));
      ctx.lineWidth = involved ? 1.6 : Math.min(2.5, 0.6 + (e.weight || 1) * 0.15);
      if (e.type === 'shared_technology') ctx.setLineDash([3, 4]); else ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.setLineDash([]);
    for (const n of nodes) {
      const s = toScreen(n);
      const color = n.type === 'project' ? categoryColor(n.categories) : n.type === 'technology' ? '#67ccfa' : (CATEGORY_COLORS[n.label] || '#ffe66d');
      const active = n.id === selected || n.id === hover;
      if (n.type === 'project') {
        ctx.drawImage(glowSprite(color, 96, dark ? 0.45 : 0.25), s.x - n.r * 3, s.y - n.r * 3, n.r * 6, n.r * 6);
        ctx.save(); ctx.translate(s.x, s.y); ctx.rotate(Math.PI / 4);
        roundRect(ctx, -n.r, -n.r, n.r * 2, n.r * 2, 3); ctx.fillStyle = color; ctx.fill();
        ctx.strokeStyle = active ? '#fff' : 'rgba(255,255,255,0.35)'; ctx.lineWidth = active ? 2 : 1; ctx.stroke(); ctx.restore();
      } else {
        ctx.beginPath(); ctx.arc(s.x, s.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = n.type === 'technology' ? rgba(color, 0.85) : rgba(color, 0.9); ctx.fill();
        ctx.strokeStyle = active ? '#fff' : 'rgba(0,0,0,0.25)'; ctx.lineWidth = active ? 2 : 1; ctx.stroke();
      }
      const showLabel = n.type !== 'technology' || n.r > 9 || active || zoom > 1.4;
      if (showLabel) {
        ctx.font = `${n.type === 'project' ? '600 12px' : '11px'} "Inter", "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        const label = n.label.length > 24 ? n.label.slice(0, 23) + '…' : n.label;
        const w = ctx.measureText(label).width + 10;
        ctx.fillStyle = dark ? 'rgba(12,8,11,0.75)' : 'rgba(255,255,255,0.85)';
        roundRect(ctx, s.x - w / 2, s.y + n.r + 3, w, 16, 6); ctx.fill();
        ctx.fillStyle = dark ? (n.type === 'project' ? '#f7ecf2' : '#c7b8c2') : '#1d1219';
        ctx.fillText(label, s.x, s.y + n.r + 5);
      }
    }
  }

  function nodeAt(px, py) {
    let best = null, bd = Infinity;
    for (const n of nodes) { const s = toScreen(n); const d = Math.hypot(s.x - px, s.y - py); if (d < n.r + 6 && d < bd) { best = n; bd = d; } }
    return best;
  }

  canvas.addEventListener('pointerdown', e => {
    const rect = canvas.getBoundingClientRect();
    const n = nodeAt(e.clientX - rect.left, e.clientY - rect.top);
    drag = { node: n, x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }; dragged = false;
    canvas.setPointerCapture(e.pointerId);
    start();
  });
  canvas.addEventListener('pointermove', e => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    if (drag) {
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) dragged = true;
      if (drag.node) { drag.node.x = (px - width / 2 - pan.x) / zoom; drag.node.y = (py - height / 2 - pan.y) / zoom; }
      else { pan.x = drag.px + (e.clientX - drag.x); pan.y = drag.py + (e.clientY - drag.y); }
      start();
      return;
    }
    const n = nodeAt(px, py);
    hover = n ? n.id : null;
    canvas.style.cursor = n ? 'pointer' : 'grab';
    if (n) {
      clear(tooltip);
      const related = edges.filter(ed => ed.a === n || ed.b === n);
      tooltip.append(h('b', { text: n.label }), h('span', { text: n.type === 'project' ? `${(n.categories || []).join(', ')} · ${n.language || '—'}` : `${n.type} · ${related.length} links` }));
      for (const ed of related.slice(0, 5)) tooltip.append(h('span', { text: `${ed.a === n ? ed.b.label : ed.a.label}: ${ed.evidence?.detail || (ed.evidence?.technologies || []).join(', ') || ed.type}` }));
      tooltip.style.left = `${px}px`; tooltip.style.top = `${py - 10}px`; tooltip.hidden = false;
    } else tooltip.hidden = true;
    draw();
  });
  const up = e => {
    if (drag && !dragged && drag.node && drag.node.type === 'project') actions.select(drag.node.id);
    else if (drag && !dragged && drag.node && drag.node.type === 'category') actions.setFilter('category', drag.node.label);
    drag = null; start();
  };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', () => { drag = null; });
  canvas.addEventListener('wheel', e => { e.preventDefault(); zoom = Math.max(0.3, Math.min(3, zoom * Math.exp(-e.deltaY * 0.0015))); draw(); }, { passive: false });
  canvas.addEventListener('keydown', e => {
    const projects = nodes.filter(n => n.type === 'project').sort((a, b) => a.label.localeCompare(b.label));
    if (!projects.length) return;
    const idx = projects.findIndex(n => n.id === hover);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { hover = projects[(idx + 1) % projects.length].id; e.preventDefault(); draw(); }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { hover = projects[(idx - 1 + projects.length) % projects.length].id; e.preventDefault(); draw(); }
    if (e.key === 'Enter' && hover) actions.select(hover);
    if (e.key === '+' || e.key === '=') { zoom = Math.min(3, zoom * 1.2); draw(); }
    if (e.key === '-') { zoom = Math.max(0.3, zoom / 1.2); draw(); }
    if (e.key === '0') { fit(); draw(); }
  });

  function renderList() {
    clear(listBox);
    listBox.append(h('summary', { text: `${t('graph.edges')} (${edges.length})` }));
    const rel = edges.filter(e => e.type !== 'category' && e.type !== 'uses');
    if (!rel.length && !edges.length) { listBox.append(h('div', { class: 'muted', text: t('graph.noEdges') })); return; }
    const table = h('table', {}, h('tbody', {}, [...rel, ...edges.filter(e => e.type === 'uses')].slice(0, 400).map(e => h('tr', {},
      h('td', {}, e.a.type === 'project' ? h('button', { class: 'btn sm ghost', type: 'button', onClick: () => actions.select(e.a.id) }, e.a.label) : e.a.label),
      h('td', { class: 'muted', text: e.type.replace('_', ' ') }),
      h('td', {}, e.b.type === 'project' ? h('button', { class: 'btn sm ghost', type: 'button', onClick: () => actions.select(e.b.id) }, e.b.label) : e.b.label),
      h('td', { class: 'muted', text: e.evidence?.detail || (e.evidence?.technologies || []).join(', ') || e.evidence?.note || '' })))));
    listBox.append(table);
  }

  for (const el of [showTech, showCat, showRel]) el.addEventListener('change', load);
  minShared.addEventListener('change', load);
  const ro = new ResizeObserver(() => start());
  ro.observe(canvasWrap);
  const unsubs = [store.on('selectedId', () => draw()), store.on('projects', load), store.on('workspaceId', load), store.on('settings', () => { reduced = document.documentElement.dataset.motion === 'off'; })];
  load();
  return { destroy() { for (const u of unsubs) u(); ro.disconnect(); view.remove(); } };
}
