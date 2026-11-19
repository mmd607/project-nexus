// Minimal observable store. Views subscribe to keys; setting a key notifies subscribers.
const LS_KEY = 'nexus.ui';

function loadLocal() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; } catch { return {}; }
}

export const CATEGORY_COLORS = {
  'AI/ML': '#fa315d', 'Security': '#5fe497', 'Backend': '#ffad48', 'Frontend': '#af61ff', 'Full-stack': '#ff7ac6',
  'Data': '#67ccfa', 'DevOps': '#ffe66d', 'Mobile': '#4de0d3', 'Documentation': '#9fb4c7', 'Prompt Engineering': '#ff9466', 'Other': '#b9a4bc',
};
export const CATEGORY_ICONS = {
  'AI/ML': 'c-ai', 'Security': 'c-security', 'Backend': 'c-backend', 'Frontend': 'c-frontend', 'Full-stack': 'c-fullstack', 'Data': 'c-data',
  'DevOps': 'c-devops', 'Mobile': 'c-mobile', 'Documentation': 'c-docs', 'Prompt Engineering': 'c-prompt', 'Other': 'c-other',
};
export const CATEGORIES = Object.keys(CATEGORY_COLORS);
export const STATUS_COLORS = { 'Active': '#65dba0', 'Idle': '#ffae5b', 'Needs attention': '#fa2559', 'Missing': '#8d7f8a' };
// Internal parts of a project (components) and the important-file kinds shown around a focused node.
export const COMPONENT_COLORS = {
  'Frontend': '#af61ff', 'Backend': '#ffad48', 'AI/ML': '#fa315d', 'Data': '#67ccfa', 'Documentation': '#9fb4c7', 'Tests': '#5fe497',
  'DevOps': '#ffe66d', 'Mobile': '#4de0d3', 'Prompt Engineering': '#ff9466', 'Security': '#5fe497', 'Shared': '#c9a0ff', 'Module': '#b9a4bc',
};
export const COMPONENT_ICONS = {
  'Frontend': 'c-frontend', 'Backend': 'c-backend', 'AI/ML': 'c-ai', 'Data': 'c-data', 'Documentation': 'c-docs', 'Tests': 'c-tests',
  'DevOps': 'c-devops', 'Mobile': 'c-mobile', 'Prompt Engineering': 'c-prompt', 'Security': 'c-security', 'Shared': 'c-shared', 'Module': 'c-module',
};
export const FILE_KIND_COLORS = {
  readme: '#9fb4c7', manifest: '#ffad48', entry: '#67ccfa', deploy: '#ffe66d', ci: '#ffe66d', schema: '#4de0d3', license: '#b9a4bc',
  docs: '#9fb4c7', build: '#c9a0ff', agent: '#ff9466', api: '#4de0d3', config: '#b9a4bc', other: '#b9a4bc',
};

export function categoryColor(p) {
  const c = Array.isArray(p) ? p[0] : (p && p.categories ? p.categories[0] : p);
  return CATEGORY_COLORS[c] || CATEGORY_COLORS.Other;
}

class Store {
  constructor() {
    const local = loadLocal();
    this.state = {
      session: null,
      settings: null,
      workspaces: [],
      workspaceId: local.workspaceId || 'all',
      projects: [],
      projectsTotal: 0,
      stats: null,
      selectedId: null,
      selectedProject: null,   // full details of the selected project (loaded by the details panel)
      selectedEntry: null,     // { projectId, path, type, label } — an internal file/folder chosen in focus view
      history: [],
      hoverId: null,
      query: '',
      filters: { category: null, status: null, language: null },
      view: 'universe',
      activeRun: null,
      lastRun: null,
      aiStatus: null,
      pendingSuggestions: 0,
      offline: false,
      loading: true,
      notifications: [],
      ui: {
        viewMode: local.viewMode || null,
        rotation: local.rotation ?? null,
        zoom: local.zoom || 1,
        theme: local.theme || null,
        showStats: local.showStats ?? true,
        detailsOpen: local.detailsOpen ?? true,
        showList: false,
        perf: local.perf || false,
      },
    };
    this.listeners = new Map();
  }

  get(key) { return this.state[key]; }

  set(key, value) {
    this.state[key] = value;
    this.emit(key);
  }

  patch(key, partial) {
    this.state[key] = { ...this.state[key], ...partial };
    this.emit(key);
  }

  emit(key) {
    for (const fn of this.listeners.get(key) || []) {
      try { fn(this.state[key], this.state); } catch (err) { console.error('store listener failed', key, err); }
    }
    for (const fn of this.listeners.get('*') || []) fn(key, this.state);
  }

  on(key, fn) {
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    this.listeners.get(key).add(fn);
    return () => this.listeners.get(key)?.delete(fn);
  }

  persistUi() {
    const { viewMode, rotation, zoom, theme, showStats, detailsOpen, perf } = this.state.ui;
    try { localStorage.setItem(LS_KEY, JSON.stringify({ viewMode, rotation, zoom, theme, showStats, detailsOpen, perf, workspaceId: this.state.workspaceId })); } catch { /* ignore */ }
  }

  setUi(partial) {
    this.patch('ui', partial);
    this.persistUi();
  }

  project(id) { return this.state.projects.find(p => p.id === id) || null; }

  select(id, { push = true } = {}) {
    if (id && push && this.state.selectedId && this.state.selectedId !== id) {
      this.state.history = [...this.state.history.slice(-19), this.state.selectedId];
    }
    if (this.state.selectedEntry && this.state.selectedEntry.projectId !== id) this.set('selectedEntry', null);
    if (!id || (this.state.selectedProject && this.state.selectedProject.id !== id)) this.set('selectedProject', null);
    this.set('selectedId', id);
  }

  /** Ranked search suggestions: exact/prefix name matches first, then substring, then other fields. */
  suggest(query, limit = 8) {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const scored = [];
    for (const p of this.state.projects) {
      const name = p.display_name.toLowerCase(), raw = p.name.toLowerCase();
      let score = 0;
      if (name === q || raw === q) score = 100;
      else if (name.startsWith(q) || raw.startsWith(q)) score = 80;
      else if (name.includes(q) || raw.includes(q)) score = 60;
      else if (p.categories.some(c => c.toLowerCase().includes(q))) score = 40;
      else if ((p.technologies || []).some(t => t.name.toLowerCase().includes(q)) || (p.languages || []).some(l => l.name.toLowerCase().includes(q))) score = 30;
      else if ((p.description || '').toLowerCase().includes(q)) score = 15;
      if (score) scored.push({ project: p, score });
    }
    return scored.sort((a, b) => b.score - a.score || a.project.display_name.localeCompare(b.project.display_name)).slice(0, limit).map(s => s.project);
  }

  back() {
    const prev = this.state.history.pop();
    if (prev) this.select(prev, { push: false });
  }

  /** Projects after search + filters (used by graph, list and stats). */
  visibleProjects() {
    const q = this.state.query.trim().toLowerCase();
    const { category, status, language } = this.state.filters;
    return this.state.projects.filter(p => {
      if (category && !p.categories.includes(category)) return false;
      if (status && p.status !== status) return false;
      if (language && !(p.languages || []).some(l => l.name === language)) return false;
      if (!q) return true;
      const hay = [p.display_name, p.name, p.relative_path, p.description || '', ...p.categories, ...(p.technologies || []).map(t => t.name), ...(p.languages || []).map(l => l.name)].join(' ').toLowerCase();
      return q.split(/\s+/).every(term => hay.includes(term));
    });
  }
}

export const store = new Store();
