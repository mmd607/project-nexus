// AI Assistant view + the opt-in "ask local model" flow shared with the details panel.
import { api } from '../api.js';
import { store, CATEGORY_COLORS, CATEGORY_ICONS } from '../store.js';
import { h, icon, clear } from '../ui/dom.js';
import { t } from '../i18n.js';
import { openModal } from '../ui/modal.js';
import { toast } from '../ui/toast.js';
import { relativeTime, percent } from '../ui/format.js';

const FIELDS = ['name', 'languages', 'manifests', 'dependencies', 'technologies', 'readme_excerpt', 'file_names'];

export function suggestionCard(s, { onResolved, showProject = false } = {}) {
  const payload = s.payload || {};
  const card = h('div', { class: 'suggestion' });
  card.append(
    h('div', { class: 'row between wrap' },
      h('b', { text: showProject ? (s.project_name || s.project_id) : t('ai.suggested') }),
      h('span', { class: 'meta', text: `${s.model} · ${relativeTime(s.created_at)}${s.cached ? ' · ' + t('ai.cached') : ''}${payload.confidence != null ? ` · ${t('ai.confidence')} ${percent(payload.confidence)}` : ''}` })),
    h('div', { class: 'chips' }, (payload.categories || []).map(c => h('span', { class: 'chip cat small', style: { '--chip-color': CATEGORY_COLORS[c] || CATEGORY_COLORS.Other } }, icon(CATEGORY_ICONS[c] || 'c-other'), h('span', { text: c })))),
    h('p', { text: payload.description || '' }),
    (payload.technologies || []).length ? h('div', { class: 'chips' }, payload.technologies.map(x => h('span', { class: 'chip small', text: x }))) : null,
    payload.reasoning ? h('p', { class: 'meta', text: `${t('ai.reasoning')}: ${payload.reasoning}` }) : null,
    h('p', { class: 'meta', text: `${t('ai.fields')}: ${(s.sent_fields || []).join(', ')}` }),
  );
  if (s.status === 'pending') {
    const applyDesc = h('input', { type: 'checkbox', checked: true });
    card.append(
      h('label', { class: 'checkbox' }, applyDesc, h('span', { text: t('ai.applyDescription') })),
      h('div', { class: 'actions' },
        h('button', { class: 'btn sm primary', type: 'button', onClick: () => resolve('accept') }, icon('i-check'), t('ai.accept')),
        h('button', { class: 'btn sm', type: 'button', onClick: () => resolve('reject') }, icon('i-x'), t('ai.reject'))));
    async function resolve(action) {
      try {
        await api.post(`/api/ai/suggestions/${s.id}/${action}`, { apply_description: applyDesc.checked });
        toast(action === 'accept' ? t('ai.accept') + ' ✓' : t('ai.reject') + ' ✓', { kind: 'success', timeout: 2000 });
        onResolved && onResolved(action);
      } catch (err) { toast(err.message, { kind: 'error' }); }
    }
  } else {
    card.append(h('span', { class: `pill`, text: s.status }));
  }
  return card;
}

export async function askAiModal(project, { onResolved } = {}) {
  const status = store.get('aiStatus') || (await api.get('/api/ai/status').catch(() => null));
  const settings = store.get('settings');
  const defaults = settings?.ai?.default_fields || ['name', 'languages', 'manifests', 'dependencies', 'technologies'];
  const boxes = FIELDS.map(f => {
    const input = h('input', { type: 'checkbox', value: f, checked: defaults.includes(f) ? true : null });
    return h('label', {}, input, h('span', {}, t('ai.field.' + f)));
  });
  const preview = h('pre', { text: t('common.loading') });
  const consent = h('input', { type: 'checkbox' });
  const sendBtn = h('button', { class: 'btn primary', type: 'button', disabled: true }, icon('i-sparkle'), t('ai.send'));
  const statusLine = h('div', { class: 'note' });
  function renderStatus() {
    clear(statusLine);
    if (!status?.enabled) statusLine.append(icon('i-warn'), ' ', t('ai.disabled'), ' — ', h('a', { href: '#/assistant', text: t('nav.assistant') }));
    else if (!status.reachable) statusLine.append(icon('i-warn'), ' ', `${t('ai.unreachable')}: ${status.error || status.base_url}`);
    else if (!status.model_available) statusLine.append(icon('i-warn'), ' ', `${t('ai.modelMissing')}: ${status.model}`);
    else statusLine.append(icon('i-check'), ' ', `${status.provider} · ${status.model} · ${status.base_url}`);
  }
  renderStatus();
  const fields = () => boxes.map(b => b.querySelector('input')).filter(i => i.checked).map(i => i.value);
  async function refreshPreview() {
    try {
      const data = await api.get(`/api/projects/${project.id}/ai-preview`, { fields: fields().join(',') });
      preview.textContent = JSON.stringify(data.payload, null, 2);
    } catch (err) { preview.textContent = err.message; }
    sendBtn.disabled = !(consent.checked && status?.enabled && fields().length);
  }
  for (const b of boxes) b.querySelector('input').addEventListener('change', refreshPreview);
  consent.addEventListener('change', refreshPreview);
  refreshPreview();
  const result = await openModal(close => {
    sendBtn.addEventListener('click', async () => {
      sendBtn.disabled = true;
      sendBtn.textContent = t('common.loading');
      try {
        const { suggestion } = await api.post(`/api/projects/${project.id}/ai-suggestion`, { fields: fields(), consent: true }, { timeout: 180000 });
        close(suggestion);
      } catch (err) {
        toast(err.message, { kind: 'error', timeout: 8000 });
        sendBtn.disabled = false; clear(sendBtn); sendBtn.append(icon('i-sparkle'), t('ai.send'));
      }
    });
    return {
      title: t('ai.askFor'),
      body: [
        statusLine,
        h('div', { class: 'field' }, h('label', { text: t('ai.fields') }), h('div', { class: 'field-picker' }, boxes)),
        h('div', { class: 'field' }, h('label', { text: t('ai.preview') }), preview),
        h('label', { class: 'checkbox' }, consent, h('span', { text: t('ai.consent') })),
      ],
      footer: [h('button', { class: 'btn', type: 'button', onClick: () => close(undefined) }, t('common.cancel')), sendBtn],
    };
  }, { wide: true });
  if (result) {
    toast(t('ai.suggested') + ' ✓', { kind: 'success', timeout: 2500 });
    onResolved && onResolved('created');
    store.set('pendingSuggestions', (store.get('pendingSuggestions') || 0) + 1);
  }
}

export function mountAssistant(container, actions) {
  const view = h('div', { class: 'view' });
  container.append(view);
  const page = h('div', { class: 'page' });
  view.append(h('div', { class: 'view-header' }, h('div', {}, h('h2', { text: t('ai.title') }), h('p', { text: t('ai.subtitle') }))), page);

  async function render() {
    clear(page);
    const settings = store.get('settings') || (await api.get('/api/settings')).settings;
    const ai = settings.ai;
    let status = null;
    try { status = await api.get('/api/ai/status'); store.set('aiStatus', status); } catch (err) { status = { error: err.message }; }

    const enabled = h('input', { type: 'checkbox', checked: ai.enabled ? true : null });
    const provider = h('select', { class: 'select' }, h('option', { value: 'ollama', text: 'Ollama' }), h('option', { value: 'openai_compatible', text: 'OpenAI-compatible local server (LM Studio, llama.cpp, vLLM…)' }));
    provider.value = ai.provider;
    const baseUrl = h('input', { class: 'input', type: 'url', value: ai.base_url });
    const model = h('input', { class: 'input', type: 'text', value: ai.model, list: 'ai-models' });
    const datalist = h('datalist', { id: 'ai-models' }, (status?.models || []).map(m => h('option', { value: m })));
    const timeout = h('input', { class: 'input', type: 'number', min: '3', max: '600', value: ai.timeout_seconds });
    const allowRemote = h('input', { type: 'checkbox', checked: ai.allow_non_local_endpoint ? true : null });
    const fieldBoxes = FIELDS.map(f => { const i = h('input', { type: 'checkbox', value: f, checked: ai.default_fields.includes(f) ? true : null }); return h('label', {}, i, h('span', {}, t('ai.field.' + f))); });
    const dot = h('span', { class: `status-dot ${!ai.enabled ? 'off' : status?.reachable ? 'ok' : 'bad'}` });
    const statusText = !ai.enabled ? t('ai.disabled') : status?.reachable ? `${t('ai.reachable')} · ${status.model_available ? t('ai.modelOk') : t('ai.modelMissing')}` : `${t('ai.unreachable')}${status?.error ? ' — ' + status.error : ''}`;

    async function save() {
      try {
        const patch = { ai: { enabled: enabled.checked, provider: provider.value, base_url: baseUrl.value.trim(), model: model.value.trim(), timeout_seconds: Number(timeout.value), allow_non_local_endpoint: allowRemote.checked, default_fields: fieldBoxes.map(b => b.querySelector('input')).filter(i => i.checked).map(i => i.value) } };
        const { settings: updated } = await api.patch('/api/settings', patch);
        store.set('settings', updated);
        toast(t('settings.saved'), { kind: 'success', timeout: 2000 });
        render();
      } catch (err) { toast(err.message, { kind: 'error', timeout: 7000 }); }
    }

    page.append(
      h('section', { class: 'card' }, h('h3', {}, h('span', { text: t('ai.status') }), h('span', {}, dot, statusText)),
        h('div', { class: 'form-grid' },
          h('label', { class: 'checkbox' }, h('span', { class: 'switch' }, enabled, h('span')), h('span', { text: t('ai.enabled') })),
          h('div', { class: 'field' }, h('label', { text: t('ai.provider') }), provider),
          h('div', { class: 'field' }, h('label', { text: t('ai.baseUrl') }), baseUrl, h('span', { class: 'hint', text: 'http://127.0.0.1:11434 (Ollama) · http://127.0.0.1:1234 (LM Studio)' })),
          h('div', { class: 'field' }, h('label', { text: t('ai.model') }), model, datalist, status?.models?.length ? h('span', { class: 'hint', text: `${status.models.length} models on server` }) : null),
          h('div', { class: 'field' }, h('label', { text: 'Timeout (s)' }), timeout),
          h('label', { class: 'checkbox' }, allowRemote, h('span', { text: 'Allow a non-local endpoint (not recommended)' })),
        ),
        h('div', { class: 'field', style: { marginTop: '10px' } }, h('label', { text: t('ai.fields') + ' (default)' }), h('div', { class: 'field-picker' }, fieldBoxes)),
        h('div', { class: 'row', style: { marginTop: '12px' } },
          h('button', { class: 'btn primary', type: 'button', onClick: save }, icon('i-check'), t('ai.save')),
          h('button', { class: 'btn', type: 'button', onClick: render }, icon('i-refresh'), t('ai.test')))),
      h('section', { class: 'card' }, h('h3', { text: t('ai.whatShared') }), h('p', { class: 'muted', text: t('ai.whatSharedBody') })),
      h('section', { class: 'card' }, h('h3', { text: t('ai.setup') }), h('p', { class: 'muted', text: t('ai.setupBody') }),
        h('pre', { class: 'mono', style: { marginTop: '8px', whiteSpace: 'pre-wrap' }, text: 'ollama pull llama3.2\nollama serve   # usually already running as a service' })),
    );

    // Pending suggestions
    const list = h('div', { class: 'sugg-list' });
    try {
      const { items } = await api.get('/api/ai/suggestions', { status: 'pending' });
      store.set('pendingSuggestions', items.length);
      if (!items.length) list.append(h('div', { class: 'muted', text: t('ai.none') }));
      for (const s of items) list.append(suggestionCard(s, { showProject: true, onResolved: async () => { await actions.refreshProjects(); render(); } }));
    } catch (err) { list.append(h('div', { class: 'note danger', text: err.message })); }
    const selected = store.get('selectedId') && store.project(store.get('selectedId'));
    page.append(h('section', { class: 'card' }, h('h3', {}, h('span', { text: t('ai.pending') }),
      selected ? h('button', { class: 'btn sm', type: 'button', onClick: () => askAiModal(selected, { onResolved: () => render() }) }, icon('i-sparkle'), `${t('ai.ask')}: ${selected.display_name}`) : null), list));
  }
  render();
  return { destroy() { view.remove(); } };
}
