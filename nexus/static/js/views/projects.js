// Projects view: accessible text list / table with filters, sorting and row virtualisation.
import { store, CATEGORIES, CATEGORY_COLORS, CATEGORY_ICONS, categoryColor } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t } from '../i18n.js';
import { formatDate, formatNumber, relativeTime } from '../ui/format.js';

const ROW_H = 52;

export function mountProjects(container, actions) {
  const view = h('div', { class: 'view projects' });
  container.append(view);
  let sort = 'name', includeMissing = false;

  const catSel = h('select', { class: 'select', 'aria-label': t('projects.col.categories') }, h('option', { value: '', text: t('projects.anyCategory') }), CATEGORIES.map(c => h('option', { value: c, text: c })));
  const statusSel = h('select', { class: 'select', 'aria-label': t('projects.col.status') }, h('option', { value: '', text: t('projects.anyStatus') }), ['Active', 'Idle', 'Needs attention'].map(s => h('option', { value: s, text: t('status.' + s) })));
  const langSel = h('select', { class: 'select', 'aria-label': t('projects.col.language') }, h('option', { value: '', text: t('projects.anyLanguage') }));
  const sortSel = h('select', { class: 'select', 'aria-label': t('projects.sort') }, [['name', 'projects.sort.name'], ['modified', 'projects.sort.modified'], ['files', 'projects.sort.files'], ['status', 'projects.sort.status']].map(([v, k]) => h('option', { value: v, text: t(k) })));
  const missingBox = h('input', { type: 'checkbox' });
  const summary = h('div', { class: 'summary-line', 'aria-live': 'polite' });
  const wrap = h('div', { class: 'projects-table-wrap', tabindex: '0' });
  const tbody = h('tbody');
  const topSpacer = h('tr', { class: 'virtual-spacer', 'aria-hidden': 'true' }, h('td', { colspan: '7' }));
  const bottomSpacer = h('tr', { class: 'virtual-spacer', 'aria-hidden': 'true' }, h('td', { colspan: '7' }));
  const table = h('table', { class: 'table', 'aria-label': t('projects.title') },
    h('colgroup', {}, h('col', { class: 'c-name' }), h('col', { class: 'c-cat' }), h('col', { class: 'c-status' }), h('col', { class: 'c-lang' }), h('col', { class: 'c-files' }), h('col', { class: 'c-mod' }), h('col', { class: 'c-git' })),
    h('thead', {}, h('tr', {}, ['name', 'categories', 'status', 'language', 'files', 'modified', 'git'].map(c => h('th', { scope: 'col', text: t('projects.col.' + c) })))),
    tbody);
  wrap.append(table);

  view.append(
    h('div', { class: 'view-header' }, h('div', {}, h('h2', { text: t('projects.title') }), h('p', { text: t('projects.subtitle') }))),
    h('div', { class: 'projects-toolbar' }, catSel, statusSel, langSel, sortSel, h('label', { class: 'checkbox' }, missingBox, h('span', { text: t('projects.includeMissing') })), summary),
    wrap,
  );

  catSel.addEventListener('change', () => actions.setFilter('category', catSel.value || null));
  statusSel.addEventListener('change', () => actions.setFilter('status', statusSel.value || null));
  langSel.addEventListener('change', () => actions.setFilter('language', langSel.value || null));
  sortSel.addEventListener('change', () => { sort = sortSel.value; render(); });
  missingBox.addEventListener('change', async () => { includeMissing = missingBox.checked; await actions.refreshProjects({ includeMissing }); render(); });

  let rows = [];
  function sorted() {
    const list = store.visibleProjects().slice();
    const cmp = {
      name: (a, b) => a.display_name.localeCompare(b.display_name), modified: (a, b) => (b.last_modified || 0) - (a.last_modified || 0),
      files: (a, b) => b.file_count - a.file_count, status: (a, b) => a.status.localeCompare(b.status) || a.display_name.localeCompare(b.display_name),
    }[sort];
    return list.sort(cmp);
  }

  function syncControls() {
    const f = store.get('filters');
    catSel.value = f.category || ''; statusSel.value = f.status || '';
    const langs = new Map();
    for (const p of store.get('projects')) for (const l of p.languages || []) langs.set(l.name, (langs.get(l.name) || 0) + 1);
    const current = f.language || '';
    clear(langSel);
    langSel.append(h('option', { value: '', text: t('projects.anyLanguage') }), [...langs.entries()].sort((a, b) => b[1] - a[1]).map(([name, n]) => h('option', { value: name, text: `${name} (${n})` })));
    langSel.value = current;
  }

  function rowFor(p, selected) {
    const tr = h('tr', { tabindex: '0', 'data-id': p.id, class: selected ? 'selected' : '', 'aria-selected': String(selected), onClick: () => actions.select(p.id), onKeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); actions.select(p.id); } } });
    tr.append(
      h('td', {}, h('div', { class: 'proj-name' }, h('span', { class: 'swatch', style: { '--accent': categoryColor(p) } }), h('div', { class: 'grow' }, h('b', { text: p.display_name }), h('small', { text: p.relative_path || '.' })))),
      h('td', {}, h('div', { class: 'chips', title: p.categories.join(', ') }, p.categories.slice(0, 2).map(c => h('span', { class: 'chip cat small', style: { '--chip-color': CATEGORY_COLORS[c] || CATEGORY_COLORS.Other } }, icon(CATEGORY_ICONS[c] || 'c-other'), h('span', { text: c }))), p.categories.length > 2 ? h('span', { class: 'chip small', text: `+${p.categories.length - 2}` }) : null)),
      h('td', {}, h('span', { class: `badge status-${p.status.replace(' ', '.')}`, text: t('status.' + p.status), title: (p.status_evidence || []).map(e => e.detail).join('\n') })),
      h('td', { text: p.primary_language || '—', title: (p.languages || []).map(l => `${l.name} (${l.files})`).join(', ') }),
      h('td', { text: formatNumber(p.file_count) + (p.files_truncated ? '+' : '') }),
      h('td', { text: relativeTime(p.last_modified), title: `${formatDate(p.last_modified)}${p.last_modified_path ? ' · ' + p.last_modified_path : ''}` }),
      h('td', { text: p.git ? `${p.git.branch || '—'}${p.git.dirty ? ' •' : ''}` : '—', title: p.git?.dirty ? t('detail.dirty') : '' }),
    );
    return tr;
  }

  function render() {
    rows = sorted();
    const total = store.get('projects').length;
    summary.textContent = t('projects.showing', formatNumber(rows.length), formatNumber(total));
    paint();
  }

  function paint() {
    const selected = store.get('selectedId');
    const scrollTop = wrap.scrollTop;
    const height = wrap.clientHeight || 600;
    const start = Math.max(0, Math.floor(scrollTop / ROW_H) - 6);
    const end = Math.min(rows.length, Math.ceil((scrollTop + height) / ROW_H) + 6);
    clear(tbody);
    topSpacer.firstChild.style.height = `${start * ROW_H}px`;
    bottomSpacer.firstChild.style.height = `${Math.max(0, rows.length - end) * ROW_H}px`;
    tbody.append(topSpacer);
    for (let i = start; i < end; i++) tbody.append(rowFor(rows[i], rows[i].id === selected));
    tbody.append(bottomSpacer);
    if (!rows.length) tbody.append(h('tr', {}, h('td', { colspan: '7', class: 'empty', text: store.get('loading') ? t('common.loading') : (store.get('projects').length ? t('universe.noMatch') : t('universe.empty.body')) })));
  }

  let ticking = false;
  wrap.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { paint(); ticking = false; }); } });
  wrap.addEventListener('keydown', e => {
    if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return;
    const focused = document.activeElement?.closest('tr[data-id]');
    const idx = focused ? rows.findIndex(r => r.id === focused.dataset.id) : -1;
    const next = Math.max(0, Math.min(rows.length - 1, idx + (e.key === 'ArrowDown' ? 1 : -1)));
    e.preventDefault();
    wrap.scrollTop = Math.max(0, next * ROW_H - height() / 2);
    paint();
    tbody.querySelector(`tr[data-id="${rows[next]?.id}"]`)?.focus();
  });
  const height = () => wrap.clientHeight || 600;

  const unsubs = [store.on('projects', () => { syncControls(); render(); }), store.on('loading', render), store.on('query', render), store.on('filters', () => { syncControls(); render(); }), store.on('selectedId', paint)];
  syncControls();
  render();
  return { destroy() { for (const u of unsubs) u(); view.remove(); } };
}
