// Scan progress widget (sidebar) + polling of active scan runs.
import { api } from '../api.js';
import { store } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t } from '../i18n.js';
import { toast } from '../ui/toast.js';

export function mountScanWidget(actions) {
  const widget = document.getElementById('scan-widget');
  const tracked = new Map();   // runId → { timer }
  let refreshTimer = null;

  function render() {
    const run = store.get('activeRun');
    clear(widget);
    if (!run || run.status !== 'running') { widget.hidden = true; return; }
    widget.hidden = false;
    const c = run.counts || {};
    const done = (c.analyzed || 0) + (c.cached || 0);
    const total = Math.max(c.discovered || 0, done);
    const determinate = run.phase === 'analyze' && total > 0;
    const pct = determinate ? Math.round((done / total) * 100) : 0;
    widget.append(
      h('div', { class: 'row between' }, h('b', { text: `${t('scan.' + (run.phase === 'discover' ? 'discover' : run.phase === 'analyze' ? 'analyze' : run.phase === 'relations' ? 'relations' : run.phase === 'reconcile' ? 'reconcile' : 'running'))}…` }),
        h('button', { class: 'btn icon sm ghost', type: 'button', 'aria-label': t('scan.cancel'), title: t('scan.cancel'), onClick: () => api.post(`/api/scan-runs/${run.id}/cancel`).catch(() => {}) }, icon('i-x'))),
      h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': determinate ? String(pct) : null }, h('i', { class: determinate ? 'determinate' : '', style: determinate ? { width: `${pct}%` } : {} })),
      h('div', { class: 'text muted truncate', text: determinate ? `${done} / ${total} · ${run.current || ''}` : `${c.discovered || 0} ${t('settings.projects')} · ${run.current || ''}` }),
    );
  }

  async function poll(runId) {
    try {
      const { run } = await api.get(`/api/scan-runs/${runId}`);
      store.set('activeRun', run.status === 'running' ? run : null);
      if (run.status === 'running') {
        // Refresh the project list periodically so partial results appear.
        if (!refreshTimer) refreshTimer = setTimeout(async () => { refreshTimer = null; await actions.refreshProjects({ quiet: true }); }, 2500);
        tracked.set(runId, setTimeout(() => poll(runId), 700));
      } else {
        tracked.delete(runId);
        store.set('lastRun', run);
        await actions.refreshWorkspaces();
        await actions.refreshProjects();
        const c = run.counts || {};
        const sm = run.summary || {};
        const detail = sm.top_level != null ? t('scan.summaryFolders', sm.top_level, (sm.skipped || []).length, c.files || 0) : t('scan.summary', c.discovered || 0, c.analyzed || 0, c.cached || 0, c.files || 0);
        const msg = `${t('scan.' + (run.status === 'completed' ? 'done' : run.status === 'cancelled' ? 'cancelled' : 'failed'))} — ${detail}`;
        toast(msg, { kind: run.status === 'completed' ? 'success' : 'warn', timeout: 6000 });
        if ((run.error_count || run.errors?.length) > 0) {
          const n = run.error_count || run.errors.length;
          store.set('notifications', [{ id: run.id, at: Date.now(), title: t('scan.errors', n), items: run.errors.map(e => `${e.where}: ${e.message}`) }, ...store.get('notifications')].slice(0, 20));
        }
        const others = store.get('workspaces').map(w => w.active_run).filter(Boolean);
        if (others.length) track(others[0].id);
      }
    } catch (err) {
      tracked.delete(runId);
      store.set('activeRun', null);
    }
  }

  function track(runId) {
    if (!runId || tracked.has(runId)) return;
    tracked.set(runId, setTimeout(() => poll(runId), 300));
  }

  store.on('activeRun', render);
  store.on('workspaces', () => { for (const w of store.get('workspaces')) if (w.active_run) track(w.active_run.id); });
  render();
  return { track };
}
