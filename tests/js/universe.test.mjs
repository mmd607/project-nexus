// Frontend unit tests for the pure modules of the Universe renderer. Run with: node --test tests/js
import test from 'node:test';
import assert from 'node:assert/strict';

// Minimal browser shims for modules that touch globals at import time.
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.document = { documentElement: { lang: 'en', dir: 'ltr', dataset: {} }, querySelectorAll: () => [], querySelector: () => null, getElementById: () => null, createElement: () => ({ getContext: () => null }) };
globalThis.window = { matchMedia: () => ({ matches: false }) };

const { computeLayout, hash, ringsFor, ringPlan, focusLayout, layoutRadius, NODE_R } = await import('../../nexus/static/js/universe/layout.js');
const { Camera } = await import('../../nexus/static/js/universe/camera.js');
const { hexToRgb, rgba } = await import('../../nexus/static/js/universe/sprites.js');
const { store, categoryColor, CATEGORIES } = await import('../../nexus/static/js/store.js');
const { pickSatellites } = await import('../../nexus/static/js/universe/universe.js');
const { t, setLanguage } = await import('../../nexus/static/js/i18n.js');

const project = (id, extra = {}) => ({ id, name: id, display_name: id, categories: ['Backend'], status: 'Active', languages: [], technologies: [], relative_path: id, parent_id: null, detected_type: 'manifest', file_count: 3, ...extra });

test('hash is deterministic and in [0,1)', () => {
  assert.equal(hash('abc'), hash('abc'));
  assert.notEqual(hash('abc'), hash('abd'));
  for (const s of ['', 'x', 'project-1', 'پروژه']) { const v = hash(s); assert.ok(v >= 0 && v < 1); }
});

test('layout is stable, places every project on an orbit, and keeps promoted sub-projects next to their parent', () => {
  const projects = [project('a'), project('b'), project('c'), project('a-child', { parent_id: 'a' }), project('a-child-2', { parent_id: 'a' })];
  const first = computeLayout(projects);
  const second = computeLayout([...projects].reverse());
  assert.equal(first.size, 5);
  for (const [id, pos] of first) {
    const other = second.get(id);
    assert.ok(other, `missing ${id} on second run`);
    assert.ok(Math.abs(pos.x - other.x) < 1e-9 && Math.abs(pos.z - other.z) < 1e-9, `position of ${id} changed with input order`);
  }
  const parent = first.get('a'), child = first.get('a-child');
  assert.equal(child.parentId, 'a');
  assert.equal(parent.r, NODE_R, 'top-level folders are full-size nodes');
  assert.ok(child.r < parent.r && child.r >= 20, 'promoted sub-projects are real nodes, slightly smaller');
  const slot = (2 * Math.PI) / projects.length;
  const dAngle = Math.abs(((child.angle - parent.angle) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI));
  assert.ok(dAngle < slot * 1.5, 'a promoted child is the angular neighbour of its parent');
  for (const pos of first.values()) assert.ok(Math.hypot(pos.x, pos.z) > 200, 'every node sits on an orbit around the hub');
  const orphan = computeLayout([project('x', { parent_id: 'missing' })]);
  assert.equal(orphan.get('x').depth, 0, 'a child whose parent is not in the set is treated as top-level');
});

test('ring plan widens with the node count so labels keep room, and the universe can be fitted', () => {
  const small = ringPlan(6), medium = ringPlan(21), big = ringPlan(120);
  assert.equal(small.rings, 1);
  assert.equal(medium.rings, 2);
  assert.ok(big.rings >= 4);
  assert.ok(medium.rBase >= 250 && big.rBase > medium.rBase, 'base radius grows with nodes per ring');
  const layout = computeLayout(Array.from({ length: 21 }, (_, i) => project(`p${i}`)));
  const radius = layoutRadius(layout);
  assert.ok(radius > 250 && radius < 900, `bounding radius ${radius}`);
  // neighbours on the same ring keep at least ~150 world units between them
  const byRing = new Map();
  for (const pos of layout.values()) { if (!byRing.has(pos.ring)) byRing.set(pos.ring, []); byRing.get(pos.ring).push(pos); }
  for (const nodes of byRing.values()) for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    assert.ok(Math.hypot(nodes[i].x - nodes[j].x, nodes[i].z - nodes[j].z) > 150, 'two nodes on one ring are too close');
  }
  assert.ok(ringsFor(21).length >= 2);
});

test('focus satellites orbit the focused node and are limited to the most informative parts', () => {
  const center = { x: 300, y: 0, z: -120, r: NODE_R };
  const sats = focusLayout(center, 6);
  assert.equal(sats.length, 6);
  for (const s of sats) {
    const d = Math.hypot(s.x - center.x, s.z - center.z);
    assert.ok(d > 100 && d < 220, `satellite distance ${d}`);
  }
  assert.deepEqual(focusLayout(center, 0), []);
  const detail = {
    components: [{ kind: 'Backend', name: 'backend', path: 'backend', file_count: 40 }, { kind: 'Frontend', name: 'frontend', path: 'frontend', file_count: 60 },
      { kind: 'DevOps', name: 'Deployment', path: '', file_count: 2 }, { kind: 'Tests', name: 'tests', path: 'tests', file_count: 5 }],
    important_files: [{ path: 'docker-compose.yml', kind: 'manifest', detail: 'compose' }, { path: 'README.md', kind: 'readme', detail: '' }, { path: 'backend/manage.py', kind: 'entry', detail: '' },
      { path: '.gitignore', kind: 'config', detail: '' }, { path: 'backend/requirements.txt', kind: 'manifest', detail: 'requirements' }],
  };
  const picked = pickSatellites(detail, 5);
  assert.equal(picked.length, 5);
  assert.deepEqual(picked.slice(0, 3).map(s => s.path), ['backend', 'frontend', 'tests'], 'components first, root-level deployment evidence is not a satellite');
  assert.equal(picked[3].path, 'README.md', 'README is the first file');
  assert.ok(!picked.some(s => s.path === '.gitignore'), 'plain configuration files are not shown');
  assert.equal(pickSatellites(detail, 0).length, 0);
  assert.equal(pickSatellites(null, 8).length, 0);
});

test('search suggestions rank exact and prefix name matches first', () => {
  store.set('projects', [
    project('MindStream-AI', { categories: ['Full-stack'], technologies: [{ name: 'FastAPI' }] }),
    project('mind-map-notes', { categories: ['Documentation'] }),
    project('churn', { categories: ['Data'], description: 'a mindful analysis' }),
    project('Smart Audio', { technologies: [{ name: 'Whisper' }] }),
  ]);
  assert.deepEqual(store.suggest('mind').map(p => p.id), ['mind-map-notes', 'MindStream-AI', 'churn']);
  assert.deepEqual(store.suggest('whisper').map(p => p.id), ['Smart Audio']);
  assert.deepEqual(store.suggest('   '), []);
  assert.deepEqual(store.suggest('zzz'), []);
  store.set('projects', []);
});

test('layout scales to hundreds of nodes with distinct positions', () => {
  const projects = Array.from({ length: 300 }, (_, i) => project(`p${i}`, { categories: [CATEGORIES[i % CATEGORIES.length]] }));
  const layout = computeLayout(projects, { cluster: true });
  assert.equal(layout.size, 300);
  const seen = new Set();
  for (const pos of layout.values()) {
    const key = `${pos.x.toFixed(1)},${pos.z.toFixed(1)}`;
    assert.ok(!seen.has(key), 'two nodes share a position');
    seen.add(key);
  }
  assert.ok(ringsFor(300).length >= 5);
});

test('camera projects the origin to the viewport centre and zoomAt keeps the cursor point fixed', () => {
  const cam = new Camera();
  cam.setViewport(1000, 800);
  const origin = cam.project(0, 0, 0);
  assert.ok(Math.abs(origin.x - 500) < 1e-9 && Math.abs(origin.y - 400) < 1e-9);
  const before = cam.project(200, 0, 100);
  cam.zoomAt(2, before.x, before.y);
  cam.instant = true; cam.update(1);
  const after = cam.project(200, 0, 100);
  assert.ok(Math.abs(after.x - before.x) < 1e-6 && Math.abs(after.y - before.y) < 1e-6, 'point under cursor moved while zooming');
  cam.setFlat(true); cam.instant = true; cam.update(1);
  const flat = cam.project(100, 50, 0);
  const flat2 = cam.project(100, 0, 0);
  assert.ok(Math.abs(flat.x - flat2.x) < 1e-6, 'in 2D height must not shift x');
  cam.reset(); cam.instant = true; cam.update(1);
  assert.equal(cam.zoom, 1); assert.equal(cam.panX, 0);
});

test('camera perspective makes far points smaller', () => {
  const cam = new Camera();
  cam.setViewport(1000, 800);
  const near = cam.project(0, 0, -300), far = cam.project(0, 0, 300);
  assert.ok(near.f > far.f);
});

test('color helpers', () => {
  assert.deepEqual(hexToRgb('#fa2559'), [250, 37, 89]);
  assert.deepEqual(hexToRgb('#fff'), [255, 255, 255]);
  assert.equal(rgba('#000000', 0.5), 'rgba(0,0,0,0.5)');
  assert.equal(categoryColor({ categories: ['AI/ML'] }), '#fa315d');
  assert.equal(categoryColor({ categories: ['Nope'] }), categoryColor({ categories: ['Other'] }));
});

test('store search and filters', () => {
  store.set('projects', [
    project('alpha', { categories: ['AI/ML'], technologies: [{ name: 'PyTorch' }], languages: [{ name: 'Python' }] }),
    project('beta', { categories: ['Frontend'], status: 'Idle', technologies: [{ name: 'React' }], languages: [{ name: 'TypeScript' }] }),
  ]);
  store.set('query', 'pytorch');
  assert.deepEqual(store.visibleProjects().map(p => p.id), ['alpha']);
  store.set('query', '');
  store.patch('filters', { status: 'Idle' });
  assert.deepEqual(store.visibleProjects().map(p => p.id), ['beta']);
  store.patch('filters', { status: null, language: 'Python' });
  assert.deepEqual(store.visibleProjects().map(p => p.id), ['alpha']);
  store.patch('filters', { language: null, category: 'Frontend' });
  assert.deepEqual(store.visibleProjects().map(p => p.id), ['beta']);
  store.patch('filters', { category: null });
  store.select('alpha'); store.select('beta');
  store.back();
  assert.equal(store.get('selectedId'), 'alpha');
});

test('i18n falls back to English and substitutes arguments', () => {
  assert.equal(t('universe.projects', 3, 2), '3 projects · 2 categories');
  setLanguage('fa');
  assert.equal(t('nav.projects'), 'پروژه‌ها');
  assert.equal(t('this.key.does.not.exist'), 'this.key.does.not.exist');
  setLanguage('en');
});
