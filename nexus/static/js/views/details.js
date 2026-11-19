// Right-hand details panel. Every number shown here is measured; category and
// status come with the evidence that produced them. It follows the current selection:
// a project (top-level folder) or, in focus view, one of its internal files/folders.
import { api } from '../api.js';
import { store, CATEGORIES, CATEGORY_COLORS, CATEGORY_ICONS, COMPONENT_COLORS, COMPONENT_ICONS, FILE_KIND_COLORS, categoryColor } from '../store.js';
import { h, icon, clear, debounce } from '../ui/dom.js';
import { t } from '../i18n.js';
import { formatBytes, formatDate, formatNumber, relativeTime, percent } from '../ui/format.js';
import { openModal, confirmModal } from '../ui/modal.js';
import { toast } from '../ui/toast.js';
import { askAiModal, suggestionCard } from './assistant.js';

const KIND_ICON = { readme: 'c-docs', manifest: 'i-file', entry: 'i-play', deploy: 'c-devops', ci: 'c-devops', schema: 'c-data', license: 'i-file', docs: 'c-docs', build: 'i-gear', agent: 'c-prompt', api: 'c-backend', config: 'i-gear' };

export function mountDetails(actions) {
  const body = document.getElementById('details-body');
  const title = document.getElementById('details-title');
  const panel = document.getElementById('details');
  const shell = document.getElementById('shell');
  let current = null, loadToken = 0;

  document.getElementById('details-close').addEventListener('click', () => actions.select(null));
  document.getElementById('details-back').addEventListener('click', () => { if (store.get('selectedEntry')) store.set('selectedEntry', null); else store.back(); });

  function setOpen(open) {
    shell.classList.toggle('details-open', open);
    // On desktop the column is always present (empty state inside); smaller screens overlay it only when open.
    panel.setAttribute('aria-hidden', String(!open && window.innerWidth <= 1199));
  }

  async function load(id) {
    const token = ++loadToken;
    if (!id) { current = null; renderEmpty(); setOpen(false); return; }
    setOpen(true);
    const cached = store.project(id);
    if (cached && (!current || current.id !== id)) renderSkeleton(cached);
    try {
      const { project } = await api.get(`/api/projects/${id}`);
      if (token !== loadToken) return;
      current = project;
      store.set('selectedProject', project);
      if (store.get('selectedEntry')) renderEntry(project, store.get('selectedEntry')); else render(project);
    } catch (err) {
      if (token !== loadToken) return;
      clear(body);
      body.append(h('div', { class: 'note danger', text: err.message }), h('button', { class: 'btn sm', type: 'button', onClick: () => load(id) }, icon('i-refresh'), t('common.retry')));
    }
  }

  function renderEmpty() {
    clear(body);
    title.textContent = '';
    body.append(h('div', { class: 'empty' }, h('strong', { text: t('details.empty') }), h('span', { text: t('details.emptyHint') }),
      h('ul', { class: 'howto' }, [t('details.how1'), t('details.how2'), t('details.how3'), t('details.how4')].map(x => h('li', { text: x })))));
  }

  function renderSkeleton(p) {
    clear(body);
    title.textContent = p.display_name;
    body.append(header(p), h('div', { class: 'muted', text: t('common.loading') }));
  }

  function catChip(name, opts = {}) {
    const color = CATEGORY_COLORS[name] || CATEGORY_COLORS.Other;
    return h(opts.onClick ? 'button' : 'span', { class: `chip cat${opts.onClick ? ' clickable' : ''}`, type: opts.onClick ? 'button' : null, style: { '--chip-color': color }, onClick: opts.onClick, title: opts.title || null },
      icon(CATEGORY_ICONS[name] || 'c-other'), h('span', { text: name }));
  }

  function copyButton(text) {
    return h('button', { class: 'btn icon sm ghost', type: 'button', 'aria-label': t('common.copy'), title: t('common.copy'), onClick: async () => {
      try { await navigator.clipboard.writeText(text); toast(t('common.copied'), { kind: 'success', timeout: 1500 }); } catch { toast(text, { timeout: 6000 }); }
    } }, icon('i-copy'));
  }

  function header(p) {
    const color = categoryColor(p);
    const kind = p.structure_kind || p.structure?.kind || (p.detected_type === 'promoted' ? 'promoted' : 'folder');
    return h('div', { class: 'detail-head' },
      h('div', { class: 'detail-icon', style: { '--accent': color } }, icon(CATEGORY_ICONS[p.categories[0]] || 'c-other')),
      h('div', { class: 'grow' },
        h('h2', { text: p.display_name, dir: 'auto' }),
        p.name !== p.display_name ? h('div', { class: 'sub mono', text: p.name, dir: 'auto' }) : null,
        h('div', { class: 'sub', text: `${t('detail.type.' + kind)}${p.parent ? ` · ${t('detail.parent')} ${p.parent.display_name}` : ''}` }),
        h('div', { class: 'row wrap', style: { marginTop: '6px' } },
          h('span', { class: `badge status-${p.status.replace(' ', '.')}`, text: t('status.' + p.status), title: (p.status_evidence || []).map(e => e.detail).join('\n') }),
          p.git?.branch ? h('span', { class: 'pill', title: t('detail.branch') }, icon('i-branch'), h('span', { text: p.git.branch })) : null,
          p.detected_type === 'promoted' ? h('span', { class: 'pill', text: t('detail.promotedPill') }) : null,
        ),
      ));
  }

  function evidenceList(evidence) {
    return h('ul', {}, evidence.map(e => h('li', {}, h('b', { text: `${e.rule}: ` }), `${e.detail}`, e.weight != null ? h('span', { class: 'faint', text: ` (${percent(e.weight)})` }) : null)));
  }

  function pathCard(p) {
    const full = p.absolute_path || p.relative_path;
    return h('section', { class: 'card path-card' },
      h('h3', { text: t('detail.path') }),
      h('div', { class: 'row' }, h('code', { class: 'path', text: full, dir: 'ltr', title: full }), copyButton(full)),
      p.exists === false ? h('div', { class: 'note warn', text: t('detail.missing') }) : null);
  }

  function componentsCard(p) {
    const comps = p.components || [];
    const card = h('section', { class: 'card' }, h('h3', { text: `${t('detail.components')} · ${comps.length}` }));
    if (!comps.length) { card.append(h('div', { class: 'muted', text: t('detail.noComponents') })); return card; }
    card.append(h('div', { class: 'component-list' }, comps.map(c => {
      const color = COMPONENT_COLORS[c.kind] || COMPONENT_COLORS.Module;
      const why = (c.evidence || []).map(e => `${e.rule}: ${e.detail}`).join('\n');
      return h('button', { type: 'button', class: 'component', style: { '--accent': color }, title: why, onClick: () => c.path ? selectEntry(p, { path: c.path, type: 'dir', label: c.name, kind: c.kind }) : null },
        h('span', { class: 'ic' }, icon(COMPONENT_ICONS[c.kind] || 'c-module')),
        h('span', { class: 'grow' }, h('b', { text: c.name, dir: 'auto' }), h('small', { text: `${c.kind}${c.path ? ' · ' + c.path + '/' : ''}` })),
        h('span', { class: 'meta', text: `${formatNumber(c.file_count)}${c.languages?.length ? ' · ' + c.languages.slice(0, 2).join(', ') : ''}` }),
        c.has_git ? h('span', { class: 'pill', title: t('detail.nestedRepo') }, icon('i-branch')) : null);
    })));
    return card;
  }

  function gitCard(p) {
    const g = p.git;
    const card = h('section', { class: 'card' }, h('h3', { text: t('detail.git') }));
    if (g && !g.error) {
      card.append(h('dl', { class: 'kv' },
        h('dt', { text: t('detail.branch') }), h('dd', { text: (g.branch || '—') + (g.is_repo_root ? '' : ` (${t('detail.nestedInParent')})`) }),
        h('dt', { text: t('detail.dirty') }), h('dd', { text: g.dirty == null ? '—' : g.dirty ? [g.modified_count ? `${g.modified_count} modified` : '', g.staged_count ? `${g.staged_count} staged` : '', g.untracked_count ? `${g.untracked_count} untracked` : ''].filter(Boolean).join(', ') : t('detail.clean') }),
        g.upstream ? h('dt', { text: t('detail.upstream') }) : null, g.upstream ? h('dd', { text: `${g.upstream} · ${g.ahead || 0} ${t('detail.ahead')} · ${g.behind || 0} ${t('detail.behind')}` }) : null,
        h('dt', { text: t('detail.lastCommit') }), h('dd', { text: g.last_commit_at ? `${relativeTime(g.last_commit_at)} — ${g.last_commit_subject || ''}` : '—' }),
        h('dt', { text: t('detail.commits30') }), h('dd', { text: g.commits_30d == null ? '—' : formatNumber(g.commits_30d) }),
      ));
    } else card.append(h('div', { class: 'muted', text: g?.error || t('detail.noGit') }));
    const nested = p.git_repos || [];
    if (nested.length) {
      card.append(h('h4', { text: t('detail.nestedRepos', nested.length) }), h('ul', { class: 'repo-list' }, nested.map(r => h('li', {},
        icon('i-branch'),
        h('span', { class: 'grow' }, h('code', { text: r.path, dir: 'ltr' }), r.skipped ? h('small', { class: 'muted', text: ` ${t('detail.repoSkipped')}` }) : h('small', { class: 'muted', text: ` ${r.branch || '—'}${r.dirty ? ' · ' + t('detail.dirty').toLowerCase() : ''}${r.error ? ' · ' + r.error : ''}` })),
        !r.skipped && r.last_commit_at ? h('span', { class: 'when', title: r.last_commit_subject || '', text: relativeTime(r.last_commit_at) }) : null))));
    }
    return card;
  }

  function importantFilesCard(p) {
    const files = p.important_files || [];
    const card = h('section', { class: 'card' }, h('h3', { text: t('detail.importantFiles') }));
    if (!files.length) { card.append(h('div', { class: 'muted', text: t('common.none') })); return card; }
    card.append(h('ul', { class: 'file-list' }, files.map(f => h('li', {}, h('button', { type: 'button', onClick: () => selectEntry(p, { path: f.path, type: 'file', label: f.path.split('/').pop(), kind: f.kind }) },
      h('span', { class: 'ic', style: { color: FILE_KIND_COLORS[f.kind] || FILE_KIND_COLORS.other } }, icon(KIND_ICON[f.kind] || 'i-file')),
      h('code', { class: 'grow', text: f.path, dir: 'ltr' }),
      h('span', { class: 'meta', text: f.kind === 'manifest' && f.detail ? f.detail : t('focus.kind.' + f.kind) }))))));
    return card;
  }

  function structureCard(p) {
    const tree = p.structure?.tree || [];
    const card = h('section', { class: 'card' }, h('h3', { text: t('detail.structure') }));
    if (!tree.length) { card.append(h('div', { class: 'muted', text: t('detail.flatProject', formatNumber(p.structure?.root_files ?? p.file_count)) })); return card; }
    const row = (d, depth) => h('li', { class: depth ? 'child' : '' }, h('button', { type: 'button', onClick: () => selectEntry(p, { path: d.path, type: 'dir', label: d.name }) },
      icon('i-folder'), h('span', { class: 'grow', text: d.name + '/', dir: 'auto' }), d.git ? icon('i-branch', 'faint') : null,
      h('span', { class: 'meta', text: `${formatNumber(d.files)} · ${formatBytes(d.size)}` })));
    const ul = h('ul', { class: 'tree' });
    for (const d of tree) {
      if (d.overflow) { ul.append(h('li', { class: 'muted', text: d.name })); continue; }
      ul.append(row(d, 0));
      for (const c of d.children || []) ul.append(row(c, 1));
      if (d.more_children) ul.append(h('li', { class: 'child muted', text: `… +${d.more_children}` }));
    }
    card.append(h('div', { class: 'muted', style: { fontSize: '12px', marginBottom: '6px' }, text: `${formatNumber(p.structure.root_files || 0)} ${t('detail.rootFiles')}${p.structure.truncated ? ' · ' + t('detail.truncated') : ''}` }), ul);
    return card;
  }

  function subProjectsCard(p) {
    const items = p.sub_projects || [];
    const mode = store.get('scanMode') || 'top-level';
    if (!items.length && mode !== 'nested') return null;
    const ws = store.get('workspaces').find(w => w.id === p.workspace_id);
    const card = h('section', { class: 'card' }, h('h3', { text: `${t('detail.nested')} · ${items.length}` }),
      h('div', { class: 'muted', style: { fontSize: '12px', marginBottom: '6px' }, text: t('detail.nestedHint') }));
    if (!items.length) card.append(h('div', { class: 'muted', text: t('detail.noNested') }));
    else card.append(h('ul', { class: 'nested-list' }, items.map(c => {
      const depth = Math.max(0, c.relative_path.split('/').length - p.relative_path.split('/').length - 1);
      const toggle = h('button', { class: `btn sm ${c.promoted ? '' : 'ghost'}`, type: 'button', 'aria-pressed': String(!!c.promoted), disabled: !ws,
        title: c.promoted ? t('detail.demote') : t('detail.promote'),
        onClick: () => promote(ws, c.relative_path, !c.promoted) }, icon(c.promoted ? 'i-check' : 'i-plus'), c.promoted ? t('detail.independent') : t('detail.promote'));
      return h('li', { style: { '--depth': depth } },
        c.promoted && c.project_id ? h('button', { type: 'button', class: 'link', onClick: () => actions.select(c.project_id) }, h('b', { text: c.name, dir: 'auto' }))
          : h('b', { text: c.name, dir: 'auto' }),
        h('small', { class: 'muted', text: `${c.relative_path.slice(p.relative_path.length + 1)} · ${t('detail.type.' + c.detected_type)}${c.primary_language ? ' · ' + c.primary_language : ''} · ${formatNumber(c.file_count)} ${t('detail.files').toLowerCase()}${c.has_git ? ' · git' : ''}`, title: (c.detection_evidence || []).map(e => `${e.rule}: ${e.detail}`).join('\n') }),
        toggle);
    })));
    return card;
  }

  async function promote(ws, path, promoted) {
    if (!ws) return;
    if (!promoted && !await confirmModal(t('detail.demote'), t('detail.demoteConfirm', path))) return;
    try {
      const res = await api.post(`/api/workspaces/${ws.id}/promote`, { path, promoted });
      toast(promoted ? t('detail.promoted') : t('detail.demoted'), { kind: 'success', timeout: 3000 });
      if (res.run) store.set('activeRun', res.run);
      actions.trackScans();
      await actions.refreshProjects();
      if (current) load(current.id);
    } catch (err) { toast(err.message, { kind: 'error', timeout: 7000 }); }
  }

  function render(p) {
    clear(body);
    title.textContent = p.display_name;
    const missing = !!p.removed_at;
    body.append(header(p));
    if (missing) body.append(h('div', { class: 'note warn' }, icon('i-warn'), ' ', t('detail.missing')));
    if (p.scan_error) body.append(h('div', { class: 'note warn', text: `${t('detail.scanError')}: ${p.scan_error}` }));

    // Description
    const descSource = p.description_source ? t('detail.descSource.' + p.description_source) : '';
    body.append(h('div', { class: 'description' }, h('span', { text: p.description || '—', dir: 'auto' }), ' ',
      h('button', { class: 'btn icon sm ghost', type: 'button', 'aria-label': t('detail.editDesc'), onClick: () => editDescription(p) }, icon('i-edit')),
      h('span', { class: 'src', text: descSource })));

    body.append(pathCard(p));

    // Categories with evidence
    const catCard = h('section', { class: 'card' },
      h('h3', {}, h('span', { text: t('detail.categories') }), h('button', { class: 'btn sm ghost', type: 'button', onClick: () => editCategories(p) }, icon('i-edit'), t('detail.edit'))),
      h('div', { class: 'chips' }, p.categories.map((c, i) => catChip(c, { onClick: () => actions.setFilter('category', c), title: (i === 0 ? t('detail.primaryCategory') + ' · ' : '') + t('filter.search', c) }))),
      p.category_override ? h('div', { class: 'faint', style: { marginTop: '6px', fontSize: '11.5px' }, text: `${t('detail.override')}${p.category_override.note ? ' — ' + p.category_override.note : ''}` }) : null,
    );
    const ruleCats = (p.category_details || []).filter(c => c.source === 'rules');
    if (ruleCats.length) {
      const why = h('details', { class: 'evidence', style: { marginTop: '8px' } }, h('summary', { text: t('detail.why') }),
        h('div', { class: 'faint', style: { fontSize: '11px', margin: '6px 0' }, text: t('detail.ruleConfidence') }),
        ruleCats.map(c => h('div', { class: 'meter', style: { '--meter-color': CATEGORY_COLORS[c.name] || CATEGORY_COLORS.Other, marginBottom: '8px' } },
          h('span', { text: c.name }), h('span', { class: 'muted', text: percent(c.confidence) }),
          h('div', { class: 'bar' }, h('i', { style: { '--w': `${Math.round(c.confidence * 100)}%` } })),
          h('div', { style: { gridColumn: '1 / -1' } }, evidenceList(c.evidence || [])))));
      catCard.append(why);
    }
    body.append(catCard);

    // Status evidence
    body.append(h('section', { class: 'card' }, h('h3', { text: t('detail.evidence') }),
      h('div', { class: 'muted', style: { fontSize: '12px', marginBottom: '6px' }, text: t('detail.statusEvidence') + ':' }),
      h('ul', { class: 'activity' }, (p.status_evidence || []).map(e => h('li', { class: e.signal === 'file_modified' ? 'file' : '' }, h('span', { class: 'what', text: e.detail }), h('span', { class: 'when', text: e.at ? relativeTime(e.at) : (e.value != null ? String(e.value) : '') })))),
      h('details', { class: 'evidence', style: { marginTop: '8px' } }, h('summary', { text: t('detail.detected') }), h('ul', {}, (p.detection_evidence || []).map(e => h('li', {}, h('b', { text: e.rule + ': ' }), e.detail)))),
    ));

    // Components (internal parts)
    body.append(componentsCard(p));

    // Tech stack
    const kindOrder = { language: 0, framework: 1, database: 2, platform: 3, library: 4, tool: 5 };
    const techs = (p.technologies || []).filter(tt => tt.kind !== 'practice').sort((a, b) => (kindOrder[a.kind] ?? 9) - (kindOrder[b.kind] ?? 9) || b.confidence - a.confidence || a.name.localeCompare(b.name));
    const techChip = tt => h('span', { class: 'chip', title: `${tt.kind} · ${percent(tt.confidence)} · ${(tt.evidence || []).map(e => e.detail).join('; ')}` },
      h('span', { class: 'dot', style: { '--chip-color': tt.kind === 'language' ? '#67ccfa' : tt.kind === 'framework' ? '#fa315d' : tt.kind === 'database' ? '#ffad48' : tt.kind === 'platform' ? '#5fe497' : tt.kind === 'tool' ? '#9fb4c7' : '#af61ff' } }), h('span', { text: tt.name }));
    const techGrid = h('div', { class: 'tech-grid' }, techs.slice(0, 14).map(techChip));
    if (techs.length > 14) {
      const more = h('button', { class: 'chip clickable', type: 'button', text: `+${techs.length - 14} ${t('common.more')}`, onClick: () => { more.remove(); techGrid.append(techs.slice(14).map(techChip)); } });
      techGrid.append(more);
    }
    body.append(h('section', { class: 'card' }, h('h3', { text: t('detail.techStack') }), techs.length ? techGrid : h('div', { class: 'muted', text: t('common.none') })));

    // Quick info
    const langs = (p.languages || []).slice(0, 5);
    const frameworks = techs.filter(tt => tt.kind === 'framework').map(tt => tt.name).slice(0, 3);
    const total = p.file_count_total ?? p.file_count;
    const kind = p.structure_kind || p.structure?.kind || 'folder';
    body.append(h('section', { class: 'card' }, h('h3', { text: t('detail.quickInfo') }),
      h('dl', { class: 'kv' },
        h('dt', { text: t('detail.type') }), h('dd', { text: t('detail.type.' + kind) + (p.sub_project_count ? ` · ${p.sub_project_count} ${t('detail.subProjects').toLowerCase()}` : '') }),
        h('dt', { text: t('detail.size') }), h('dd', { text: `${formatBytes(p.size_bytes)} · ${formatNumber(total)} ${t('detail.files').toLowerCase()}${p.files_truncated ? ` (${formatNumber(p.file_count)} ${t('detail.listed')})` : ''} · ${formatNumber(p.dir_count)} ${t('detail.dirs').toLowerCase()}` }),
        h('dt', { text: t('detail.modified') }), h('dd', { text: p.last_modified ? `${formatDate(p.last_modified)} (${relativeTime(p.last_modified)})` : '—', title: p.last_modified_path || '' }),
        h('dt', { text: t('detail.scanned') }), h('dd', { text: p.last_analyzed_at ? `${formatDate(p.last_analyzed_at)} (${relativeTime(p.last_analyzed_at)})` : '—' }),
        h('dt', { text: t('detail.language') }), h('dd', {}, langs.length ? langs.map((l, i) => h('span', { text: `${l.name} (${formatNumber(l.files)})${i < langs.length - 1 ? ', ' : ''}` })) : '—'),
        h('dt', { text: t('detail.framework') }), h('dd', { text: frameworks.join(', ') || '—' }),
        h('dt', { text: t('detail.manifests') }), h('dd', {}, (p.manifests || []).length ? (p.manifests || []).slice(0, 8).map(m => h('div', { class: 'mono', text: `${m.path}${(m.dependencies?.length || m.dev_dependencies?.length) ? ` · ${(m.dependencies?.length || 0) + (m.dev_dependencies?.length || 0)} ${t('detail.deps')}` : ''}` })) : '—',
          (p.manifests || []).length > 8 ? h('div', { class: 'faint', text: `+${p.manifests.length - 8} ${t('common.more')}` }) : null),
      )));

    body.append(gitCard(p));

    // Recent activity: commits (real) + recently modified files (real)
    const g = p.git;
    const activity = [];
    for (const c of (g?.recent_commits || []).slice(0, 5)) activity.push({ kind: 'commit', at: c.at, text: c.subject, who: c.author });
    for (const f of (p.recent_files || []).slice(0, 5)) activity.push({ kind: 'file', at: f.mtime, text: f.relative_path });
    activity.sort((a, b) => b.at - a.at);
    body.append(h('section', { class: 'card' }, h('h3', { text: t('detail.recent') }),
      activity.length ? h('ul', { class: 'activity' }, activity.slice(0, 8).map(a => h('li', { class: a.kind }, h('span', { class: 'what', text: a.kind === 'commit' ? `${a.text}${a.who ? ' · ' + a.who : ''}` : a.text }), h('span', { class: 'when', text: relativeTime(a.at) })))) : h('div', { class: 'muted', text: t('detail.noActivity') })));

    body.append(importantFilesCard(p));
    body.append(structureCard(p));
    const nestedCard = subProjectsCard(p);
    if (nestedCard) body.append(nestedCard);

    // Parent / promoted children / relations
    if (p.parent || (p.children || []).length || (p.relations || []).length) {
      const card = h('section', { class: 'card' });
      if (p.parent) card.append(h('h3', { text: t('detail.parent') }), h('ul', { class: 'sub-list' }, h('li', {}, h('button', { type: 'button', onClick: () => actions.select(p.parent.id) }, h('span', { text: p.parent.display_name }), icon('i-chev')))));
      if ((p.children || []).length) card.append(h('h3', { text: t('detail.subProjects') }), h('ul', { class: 'sub-list' }, p.children.map(c => h('li', {}, h('button', { type: 'button', onClick: () => actions.select(c.id) }, h('span', { text: c.display_name }), h('span', { class: `muted status-${c.status.replace(' ', '.')}`, text: `${t('status.' + c.status)} · ${formatNumber(c.file_count)}` }))))));
      const rels = (p.relations || []).filter(r => r.type !== 'contains').slice(0, 10);
      if (rels.length) card.append(h('h3', { text: t('detail.relations') }), h('ul', { class: 'sub-list' }, rels.map(r => {
        const otherId = r.source_id === p.id ? r.target_id : r.source_id;
        const otherName = r.source_id === p.id ? r.target_name : r.source_name;
        const why = r.type === 'shared_technology' ? (r.evidence.technologies || []).join(', ') : (r.evidence.detail || r.evidence.note || r.type);
        return h('li', {}, h('button', { type: 'button', title: why, onClick: () => actions.select(otherId) }, h('span', { text: otherName }), h('span', { class: 'muted truncate', text: why })));
      })));
      body.append(card);
    }

    // File explorer (paginated, searchable, read-only)
    body.append(explorerSection(p));

    // AI
    const aiCard = h('section', { class: 'card ai-box' }, h('h3', {}, h('span', {}, icon('i-sparkle'), ' ', t('ai.suggested'))));
    const pending = (p.ai_suggestions || []).filter(s => s.status === 'pending');
    if (pending.length) aiCard.append(suggestionCard(pending[0], { onResolved: () => load(p.id) }));
    const aiStatus = store.get('aiStatus');
    aiCard.append(h('div', { class: 'row', style: { marginTop: '8px' } },
      h('button', { class: 'btn sm', type: 'button', disabled: missing, onClick: () => askAiModal(p, { onResolved: () => load(p.id) }) }, icon('i-sparkle'), t('ai.askFor')),
      h('span', { class: 'faint', text: aiStatus?.enabled ? (aiStatus.reachable ? `${aiStatus.model} ✓` : t('ai.unreachable')) : t('ai.disabled') })));
    body.append(aiCard);

    // Actions
    body.append(h('div', { class: 'row wrap' },
      h('button', { class: 'btn sm', type: 'button', disabled: missing, onClick: () => openFolder(p) }, icon('i-open'), t('detail.open')),
      h('button', { class: 'btn sm', type: 'button', disabled: missing, onClick: () => rescan(p) }, icon('i-refresh'), t('detail.rescan')),
      h('button', { class: 'btn sm', type: 'button', onClick: () => { location.hash = '#/universe'; actions.focusInUniverse(p.id); } }, icon('i-universe'), t('detail.viewInGraph')),
      missing ? h('button', { class: 'btn sm danger', type: 'button', onClick: () => forget(p) }, icon('i-trash'), t('detail.forget')) : null,
    ));
  }

  // ------------------------------------------------------------- internal file / folder
  function selectEntry(p, entry) {
    store.set('selectedEntry', { projectId: p.id, ...entry });
  }

  async function renderEntry(p, entry) {
    clear(body);
    title.textContent = `${p.display_name} › ${entry.label || entry.path}`;
    const back = h('button', { class: 'btn sm ghost', type: 'button', onClick: () => store.set('selectedEntry', null) }, icon('i-left'), t('detail.backToProject', p.display_name));
    const head = h('div', { class: 'detail-head' },
      h('div', { class: 'detail-icon', style: { '--accent': entry.kind && COMPONENT_COLORS[entry.kind] ? COMPONENT_COLORS[entry.kind] : (FILE_KIND_COLORS[entry.kind] || '#c7b8c2') } }, icon(entry.type === 'dir' ? (COMPONENT_ICONS[entry.kind] || 'i-folder') : (KIND_ICON[entry.kind] || 'i-file'))),
      h('div', { class: 'grow' }, h('h2', { text: entry.label || entry.path.split('/').pop(), dir: 'auto' }), h('div', { class: 'sub mono', text: entry.path, dir: 'ltr' }),
        h('div', { class: 'row wrap', style: { marginTop: '6px' } }, h('span', { class: 'pill', text: entry.type === 'dir' ? t('detail.folder') : t('detail.file') }), entry.kind ? h('span', { class: 'pill', text: entry.kind in COMPONENT_COLORS ? entry.kind : t('focus.kind.' + entry.kind) }) : null)));
    body.append(back, head);
    const full = `${p.absolute_path || p.relative_path}${p.absolute_path?.includes('\\') ? '\\' : '/'}${entry.path.replace(/\//g, p.absolute_path?.includes('\\') ? '\\' : '/')}`;
    body.append(h('section', { class: 'card path-card' }, h('h3', { text: t('detail.path') }), h('div', { class: 'row' }, h('code', { class: 'path', text: full, dir: 'ltr', title: full }), copyButton(full))));
    const info = h('section', { class: 'card' }, h('h3', { text: t('detail.entryInfo') }), h('div', { class: 'muted', text: t('common.loading') }));
    body.append(info);
    const component = (p.components || []).find(c => c.path === entry.path);
    const relation = component ? t('detail.entryComponent', component.kind, p.display_name) : entry.kind ? t('detail.entryImportant', t('focus.kind.' + entry.kind), p.display_name) : t('detail.entryPartOf', p.display_name);
    try {
      const { entry: e } = await api.get(`/api/projects/${p.id}/entry`, { path: entry.path });
      clear(info);
      info.append(h('h3', { text: t('detail.entryInfo') }), h('dl', { class: 'kv' },
        h('dt', { text: t('detail.relation') }), h('dd', { text: relation }),
        h('dt', { text: t('detail.type') }), h('dd', { text: e.type === 'dir' ? `${t('detail.folder')} · ${Object.entries(e.kinds || {}).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, n]) => `${k} ${n}`).join(', ')}` : `${e.kind}${e.extension ? ' · ' + e.extension : ''}${e.sensitive ? ' · ' + t('detail.sensitive') : ''}` }),
        h('dt', { text: t('detail.size') }), h('dd', { text: e.type === 'dir' ? `${formatBytes(e.size)} · ${formatNumber(e.files)} ${t('detail.files').toLowerCase()}` : formatBytes(e.size) }),
        h('dt', { text: t('detail.modified') }), h('dd', { text: e.mtime ? `${formatDate(e.mtime)} (${relativeTime(e.mtime)})` : '—' }),
        e.type === 'dir' && e.extensions?.length ? h('dt', { text: t('detail.extensions') }) : null, e.type === 'dir' && e.extensions?.length ? h('dd', { class: 'mono', text: e.extensions.join(', ') }) : null,
      ));
      if (component) info.append(h('details', { class: 'evidence', style: { marginTop: '8px' } }, h('summary', { text: t('detail.detected') }), h('ul', {}, (component.evidence || []).map(x => h('li', {}, h('b', { text: x.rule + ': ' }), x.detail)))));
      info.append(h('div', { class: 'faint', style: { marginTop: '8px', fontSize: '11.5px' }, text: t('detail.readOnlyNote') }));
    } catch (err) {
      clear(info);
      info.append(h('h3', { text: t('detail.entryInfo') }), h('div', { class: 'note warn', text: err.message }));
    }
    if (entry.type === 'dir') body.append(explorerSection(p, entry.path));
  }

  // ------------------------------------------------------------- explorer
  function explorerSection(p, startPath = '') {
    const crumbs = h('div', { class: 'explorer-crumbs' });
    const list = h('div', { class: 'list', role: 'list' });
    const pager = h('div', { class: 'pager' });
    const input = h('input', { class: 'input', type: 'search', placeholder: t('detail.searchFiles'), 'aria-label': t('detail.searchFiles') });
    const kindSel = h('select', { class: 'select', 'aria-label': 'File kind' }, h('option', { value: '', text: t('detail.allKinds') }),
      ...Object.entries(p.file_kinds || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => h('option', { value: k, text: `${k} (${n})` })));
    let path = startPath, offset = 0; const limit = 100;

    function renderCrumbs() {
      clear(crumbs);
      const parts = path ? path.split('/') : [];
      crumbs.append(h('button', { type: 'button', class: parts.length ? '' : 'current', onClick: () => go('') }, icon('i-folder'), h('span', { text: p.name })));
      parts.forEach((seg, i) => {
        const target = parts.slice(0, i + 1).join('/');
        crumbs.append(h('span', { class: 'sep', text: '/' }), h('button', { type: 'button', class: i === parts.length - 1 ? 'current' : '', onClick: () => go(target) }, h('span', { text: seg, dir: 'auto' })));
      });
    }
    function go(next) { path = next; offset = 0; input.value = ''; renderCrumbs(); loadTree(); }
    async function loadTree() {
      try {
        const data = await api.get(`/api/projects/${p.id}/tree`, { path, limit: 400 });
        clear(list);
        for (const d of data.dirs) list.append(h('div', { role: 'listitem', class: 'entry dir' },
          h('button', { type: 'button', class: 'open', title: d.path, onClick: () => go(d.path) },
            icon('i-folder'), h('span', { class: 'path', text: d.name + '/', dir: 'auto' }), h('span', { class: 'meta', text: `${formatNumber(d.files)} · ${formatBytes(d.size)}` })),
          h('button', { class: 'btn icon sm ghost', type: 'button', 'aria-label': t('detail.entryInfo'), title: t('detail.entryInfo'), onClick: () => selectEntry(p, { path: d.path, type: 'dir', label: d.name }) }, icon('i-info'))));
        for (const f of data.files) list.append(h('div', { role: 'listitem', class: `entry file${f.sensitive ? ' sensitive' : ''}` },
          h('button', { type: 'button', class: 'open', title: f.relative_path, onClick: () => selectEntry(p, { path: f.relative_path, type: 'file', label: f.name }) },
            f.sensitive ? icon('i-lock') : icon('i-file'), h('span', { class: 'path', text: f.name, dir: 'auto' }), h('span', { class: 'meta', text: `${f.kind} · ${formatBytes(f.size)}` }))));
        if (!data.dirs.length && !data.files.length) list.append(h('div', { class: 'muted', text: t('detail.noFiles') }));
        clear(pager);
        pager.append(h('span', { text: `${formatNumber(data.dirs.length)} ${t('detail.dirs').toLowerCase()} · ${formatNumber(data.files.length)} ${t('detail.files').toLowerCase()}${data.truncated ? ' · ' + t('detail.truncated') : ''}` }));
      } catch (err) { clear(list); list.append(h('div', { class: 'muted', text: err.message })); }
    }
    async function loadSearch() {
      try {
        const { items, total } = await api.get(`/api/projects/${p.id}/files`, { query: input.value, kind: kindSel.value, limit, offset, sort: 'path' });
        clear(list);
        for (const f of items) list.append(h('div', { role: 'listitem', class: `entry file${f.sensitive ? ' sensitive' : ''}` },
          h('button', { type: 'button', class: 'open', title: f.relative_path, onClick: () => selectEntry(p, { path: f.relative_path, type: 'file', label: f.relative_path.split('/').pop() }) },
            f.sensitive ? icon('i-lock') : icon('i-file'), h('span', { class: 'path', text: f.relative_path, dir: 'ltr' }), h('span', { class: 'meta', text: `${f.kind} · ${formatBytes(f.size)}` }))));
        if (!items.length) list.append(h('div', { class: 'muted', text: t('detail.noFiles') }));
        clear(pager);
        pager.append(h('span', { text: `${formatNumber(Math.min(total, offset + 1))}–${formatNumber(Math.min(total, offset + items.length))} / ${formatNumber(total)}${p.files_truncated ? ' · ' + t('detail.truncated') : ''}` }),
          h('span', { class: 'row' },
            h('button', { class: 'btn sm ghost', type: 'button', disabled: offset === 0, onClick: () => { offset = Math.max(0, offset - limit); loadSearch(); } }, icon('i-left')),
            h('button', { class: 'btn sm ghost', type: 'button', disabled: offset + limit >= total, onClick: () => { offset += limit; loadSearch(); } }, icon('i-right'))));
      } catch (err) { clear(list); list.append(h('div', { class: 'muted', text: err.message })); }
    }
    const refresh = () => { offset = 0; if (input.value.trim() || kindSel.value) loadSearch(); else loadTree(); };
    input.addEventListener('input', debounce(refresh, 250));
    kindSel.addEventListener('change', refresh);
    renderCrumbs();
    loadTree();
    return h('section', { class: 'card files-box' }, h('h3', { text: `${t('detail.filesTitle')} · ${formatNumber(p.file_count_total ?? p.file_count)}` }),
      p.sensitive_file_count ? h('div', { class: 'faint', style: { fontSize: '11.5px' } }, icon('i-lock'), ` ${p.sensitive_file_count} ${t('detail.sensitive')}`) : null,
      h('div', { class: 'row' }, input, kindSel), crumbs, list, pager);
  }

  async function editCategories(p) {
    const boxes = CATEGORIES.map(c => {
      const input = h('input', { type: 'checkbox', value: c, checked: p.categories.includes(c) ? true : null });
      return h('label', { style: { '--accent': CATEGORY_COLORS[c] } }, input, icon(CATEGORY_ICONS[c]), h('span', { text: c }));
    });
    const note = h('input', { class: 'input', type: 'text', placeholder: t('cat.edit.note'), value: p.category_override?.note || '' });
    const result = await openModal(close => ({
      title: t('cat.edit.title'),
      body: [h('p', { class: 'muted', text: t('cat.edit.body') }), h('div', { class: 'category-picker' }, boxes), h('div', { class: 'field' }, h('label', { text: t('cat.edit.note') }), note)],
      footer: [
        p.category_override ? h('button', { class: 'btn ghost', type: 'button', onClick: () => close({ clear: true }) }, t('cat.edit.clear')) : null,
        h('button', { class: 'btn', type: 'button', onClick: () => close(undefined) }, t('common.cancel')),
        h('button', { class: 'btn primary', type: 'button', onClick: () => close({ categories: boxes.map(b => b.querySelector('input')).filter(i => i.checked).map(i => i.value), note: note.value }) }, t('common.save')),
      ],
    }));
    if (!result) return;
    try {
      await api.patch(`/api/projects/${p.id}/categories`, result.clear ? { categories: null } : { categories: result.categories, note: result.note });
      await actions.refreshProjects();
      load(p.id);
      toast(t('settings.saved'), { kind: 'success', timeout: 2500 });
    } catch (err) { toast(err.message, { kind: 'error' }); }
  }

  async function editDescription(p) {
    const area = h('textarea', { class: 'textarea', maxlength: '600' }); area.value = p.description || '';
    const result = await openModal(close => ({
      title: t('detail.editDesc'), body: [area],
      footer: [h('button', { class: 'btn', type: 'button', onClick: () => close(undefined) }, t('common.cancel')), h('button', { class: 'btn primary', type: 'button', onClick: () => close(area.value) }, t('common.save'))],
    }));
    if (result == null) return;
    try { await api.patch(`/api/projects/${p.id}`, { description: result }); await actions.refreshProjects(); load(p.id); }
    catch (err) { toast(err.message, { kind: 'error' }); }
  }

  async function openFolder(p) {
    try { await api.post(`/api/projects/${p.id}/open`); } catch (err) { toast(err.message, { kind: 'error' }); }
  }
  async function rescan(p) {
    try { await api.post(`/api/projects/${p.id}/rescan`); await actions.refreshProjects(); load(p.id); toast(t('scan.done'), { kind: 'success', timeout: 2000 }); }
    catch (err) { toast(err.message, { kind: 'error' }); }
  }
  async function forget(p) {
    if (!await confirmModal(t('detail.forget'), `${p.display_name}?`, { danger: true })) return;
    try { await api.del(`/api/projects/${p.id}`); actions.select(null); await actions.refreshProjects(); }
    catch (err) { toast(err.message, { kind: 'error' }); }
  }

  store.on('selectedId', id => load(id));
  store.on('selectedEntry', entry => {
    if (!current) return;
    if (entry && entry.projectId === current.id) renderEntry(current, entry);
    else if (!entry) render(current);
  });
  // A finished scan or a detection-mode change can alter what the panel shows: reload the open project.
  store.on('lastRun', () => { if (current && !store.get('selectedEntry')) load(current.id); });
  store.on('scanMode', () => { if (current && !store.get('selectedEntry')) load(current.id); });
  store.on('aiStatus', () => { /* status label refresh on next render */ });
  renderEmpty();
  setOpen(false);
  return { reload: () => current && load(current.id) };
}
