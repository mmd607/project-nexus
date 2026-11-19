# Architecture & decisions

## Flow

```
user-selected roots → bounded discovery → per-project analysis → deterministic classifier
      → SQLite (WAL) → local HTTP API → browser UI (Universe / Projects / Graph / Assistant / Settings)
                                   ↘ optional, opt-in local model (Ollama / OpenAI-compatible)
```

Every stage is in `nexus/`:

| Module | Responsibility |
|---|---|
| `cli.py` | argument parsing, logging, server start, browser/desktop window |
| `paths.py` | platform data directory, static dir (also inside PyInstaller bundles) |
| `settings.py` | validated JSON settings (`settings.json`) with safe defaults |
| `db.py` / `repo.py` | SQLite connection (WAL, forward-only migrations) and domain queries |
| `fsutil.py` | link/junction detection, root containment, ignore matcher, capped reads |
| `languages.py` | extension → language, file kinds, sensitive-file patterns |
| `manifests.py` | defensive parsers for 25+ manifest types (names only, no values) |
| `tech.py` | dependency/image → technology knowledge base with category weights |
| `classifier.py` | rule engine → categories (with evidence) and technologies |
| `gitinfo.py` | read-only git snapshot with fixed arguments and protected env |
| `scanner.py` | discovery (BFS, depth/count limits), walk, fingerprint cache, scan jobs |
| `relations.py` | contains / local dependency / shared technology edges; knowledge-graph payload |
| `ai.py` | opt-in payload builder, provider clients, schema validation, suggestion queue |
| `picker.py` | native folder dialog (tkinter helper process) and directory browser |
| `server.py` | HTTP routes, static serving, security headers, token/Origin/Host checks |

Frontend (`nexus/static/js`): `app.js` (boot + hash router), `store.js` (observable state), `api.js`, `i18n.js` (en/fa), `universe/*` (camera, layout, sprites, crystal, renderer, view), `views/*` (details, projects, knowledge, assistant, settings, scan, workspace), `ui/*` (dom helpers, modal, toast, format).

## Data model (SQLite)

`workspaces` (with `settings_json` → `promoted` sub-folders) → `projects` (stable id = sha1(workspace id + relative path), `parent_id` only for *promoted* sub-folders, `removed_at` tombstone for missing projects, plus the v2 columns `components_json`, `structure_json`, `git_repos_json`, `important_files_json`, `file_count_total`) → `files`, `technologies`, `categories` (source = rules), `category_overrides` (manual / accepted AI; never touched by rescans), `git_snapshots`, `sub_projects` (nested candidates listed under their parent); plus `scan_runs` (with a `summary_json` explaining skipped top-level entries), `relations`, `ai_suggestions`, `schema_migrations`. Migrations are numbered SQL scripts applied in order at start-up (`db.MIGRATIONS`); migration 2 dropped the old nested rows and the app rescans automatically after it (`Database.needs_rescan`).

## Project model: one folder, one project

**Every direct sub-folder of a workspace is exactly one project**, named after the folder. That is the whole rule; it does not depend on manifests. Whatever lives inside (`backend/`, `frontend/`, `apps/web`, several `package.json`/`pyproject.toml` files, nested `.git` repositories, `docs/`, notebooks …) is analysed as *part of that project*:

* **Components** (`components.py`): direct sub-folders — and the children of container folders such as `packages/`, `apps/`, `services/` — are classified by name tokens (`backend`, `api`, `worker` → Backend; `frontend`, `web`, `client` → Frontend; `ml`, `notebooks`, `training` → AI/ML; `docs` → Documentation; `tests` → Tests; `infra`, `k8s` → DevOps; …) and, when the name is not telling, by running the classifier on that sub-tree alone. Root-level `Dockerfile`/compose/CI files form a *Deployment* component. Each component carries its evidence, file count, languages, manifests and whether it has its own `.git`.
* **Category labels** of the folder come from the whole tree plus the components: a folder with a Backend and a Frontend part is *Full-stack*; an `ml/` part adds *AI/ML*; docs/tests/deploy parts add only weak evidence so a `docs/` folder never turns a backend into a "Documentation" project.
* **Nested repositories** are reported inside the project (`git_repos`: branch, dirty state, last commit for up to eight of them) and never become nodes.
* **Structure** (two-level folder tree with honest per-folder file counts even when the stored file list is capped), **important files** (README, manifests at any depth ≤ 4, entry points, deployment and CI files, schemas, agent instructions) and the total file count are stored per project.

Top-level entries that are *not* projects are listed in the scan summary with a reason: hidden/system folders, empty folders, unreadable folders (permission denied) and links/junctions; loose files at the workspace root are counted, not shown as projects.

**Scan modes** (Settings → Project detection): `top-level` (default) does exactly the above. `nested` additionally lists *sub-project candidates* inside every folder (marker-based: manifest, project file, `.git`, weak markers + sources, or — outside marker-bearing roots — ≥3 loose source files; bounded by `scan.max_depth`), stored in `sub_projects` and shown in the details panel with a *Make independent* switch. Promoting a folder (`POST /api/workspaces/{id}/promote`) records it in the workspace settings; on the next scan it becomes a project of its own (`detected_type = promoted`, `parent_id` = the folder it lives in, drawn as a full node linked to its parent) and the parent stops counting its files. *Merge back* deletes the node immediately and the parent re-absorbs the folder on the next scan. Display names of promoted generic folders are prefixed with context (`shop / backend / api`).

## Status (evidence, not opinion)

`Active` — most recent file mtime or last commit within the activity window (default 30 days). `Idle` — evidence exists but older. `Needs attention` — only for a concrete reason: uncommitted changes (counts shown) or a scan issue for that project. `Missing` — not found during the last completed scan (kept with its overrides until you *Forget* it). All signals are listed in the details panel and API (`status_evidence`).

## Classification

Rules emit `(category, weight, evidence)` triples from: dependency names (via `tech.py`), container images, files and folders (e.g. `.tf`, `.ipynb`, `AndroidManifest.xml`, `prompts/`), *names* (folder / manifest / README title keywords), README-excerpt keywords, and sub-project categories. Weights combine as `1 − Π(1 − w)`; categories above 0.45 (0.5 if only a name keyword supports them) are kept, max four. Backend + Frontend ≥ 0.5 each ⇒ Full-stack. Nothing ⇒ `Other` with an explicit "no signal" evidence entry. Confidence is labelled in the UI as *rule confidence, not a quality score*.

## Incremental scanning

Each analysis stores a fingerprint = sha1(analyzer version, every file's path/size/mtime, `.git` HEAD/index/refs mtimes). On rescan, projects whose fingerprint is unchanged are only *touched* (status recomputed from stored timestamps against "now"); everything else is re-analysed. Bumping `ANALYZER_VERSION` invalidates all caches. Results are committed per project, so the UI shows partial results during a scan; a cancel flag is checked between directories and projects.

## Universe rendering

Canvas 2D with a real 3D pipeline: yaw/pitch orbit camera, perspective projection (orthographic when 2D), depth-sorted painter's algorithm, octahedral crystals with Lambert shading, pre-rendered glow sprites instead of `shadowBlur`, and an on-demand render loop that stops when nothing animates or the tab is hidden. Layout (`layout.js`) is deterministic (hash of the project id) so nodes do not jump between rescans: one full-size node per project on 1–5 orbits whose radius grows with the number of nodes per ring (≥180 world units between ring neighbours), promoted sub-projects placed next to their parent and linked to it by a dashed line, category clustering above 24 nodes. On load the camera zoom is fitted to the whole universe (and to the free area above the controls on phones). Labels are placed by priority (selected > hovered > keyboard-focused > nearest) against every already placed rectangle *and* the DOM overlays (stats card, filter bar, breadcrumb, controls); a label that does not fit as two lines is retried as one line, then as a bare name; each node remembers its anchor so labels do not flicker while the scene rotates. Secondary categories are drawn as small beads on the node's outer ring.

**Focus view.** Selecting a project (click, tap, Enter, search + Enter, `?project=` in the URL) glides the camera to the node (pan computed for the target zoom so the crystal lands in the centre), pauses rotation, fades the other nodes and their labels, and lays out up to `ui.focus_satellites` (default 8) *satellites* around the node: its components, README, manifests, entry points, deployment/CI files, schemas. Satellites are drawn from `project.components` + `project.important_files` (`pickSatellites()` in `universe.js`) — never stored, never permanent nodes. Clicking one puts that file/folder in the details panel (`GET /api/projects/{id}/entry?path=` — size, mtime, kind, relation to the project) and adds a third breadcrumb; the panel's file explorer (`GET /api/projects/{id}/tree?path=`) browses the rest read-only. Esc, Backspace, the breadcrumb or *Back to workspace* return to the fitted universe view. Search suggestions (`store.suggest`) rank exact/prefix name matches first; ↑/↓ + Enter jump to a project, typing dims non-matching nodes.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/session`, `/api/health` | version, platform, git availability (no token) |
| GET/POST | `/api/workspaces` | list / add (`{path, display_name?, scan?, allow_root?}`) |
| PATCH/DELETE | `/api/workspaces/{id}` | rename / remove (`?purge=1` deletes stored data) |
| POST | `/api/workspaces/{id}/scan` | `{incremental: bool}` → run |
| GET | `/api/scan-runs`, `/api/scan-runs/{id}` · POST `/api/scan-runs/{id}/cancel` | progress, counts, issues |
| GET | `/api/projects?workspace&query&category&status&language&sort&limit&offset&include_missing` | list |
| GET | `/api/projects/{id}` · `/api/projects/{id}/files?query&kind&limit&offset&sort` | details (components, structure, nested repos, important files, sub-project candidates) / paginated files (no contents) |
| GET | `/api/projects/{id}/tree?path&limit` · `/api/projects/{id}/entry?path` | read-only explorer: children of a folder / metadata of one file or folder |
| POST | `/api/workspaces/{id}/promote` (`{path, promoted}`) | make a nested folder an independent node (or merge it back); triggers an incremental rescan |
| PATCH | `/api/projects/{id}/categories` (`{categories|null, note}`) · `/api/projects/{id}` (`{description}`) | manual overrides |
| POST | `/api/projects/{id}/rescan` · `/open` · DELETE `/api/projects/{id}` (missing only) | |
| GET/POST | `/api/projects/{id}/ai-preview` · `/ai-suggestion` (`{fields, consent:true, force?}`) | opt-in AI |
| GET/POST | `/api/ai/status` · `/api/ai/suggestions` · `/api/ai/suggestions/{id}/accept|reject` | |
| GET | `/api/graph?workspace&min_shared` · `/api/relations?project` · POST/DELETE `/api/relations` | knowledge graph, manual links |
| GET | `/api/stats?workspace` · `/api/export?anonymize` | |
| GET/PATCH | `/api/settings` | validated partial updates |
| POST/GET | `/api/system/pick-folder` · `/api/system/browse?path` | folder chooser |

All mutating calls need `X-Nexus-Token` (see SECURITY.md).

## Architecture decisions (ADRs)

1. **Standard-library-only backend.** *Why:* installation on any OS is `python -m nexus`, PyInstaller bundles are small, and no dependency can break an offline install. *Cost:* `http.server` is not a production web framework; acceptable for a single local user (threaded, HTTP/1.1, bounded bodies).
2. **SQLite with WAL and one guarded connection.** *Why:* zero setup, atomic per-project commits, readers don't block the scan writer. *Cost:* a single writer, which matches the one-scan-at-a-time design.
3. **Vanilla ES modules, no bundler.** *Why:* the deliverable must run from source without Node; the server serves files directly; CSP forbids inline code so modules keep discipline. *Cost:* no TypeScript types; pure-logic modules are covered by `node:test`.
4. **Canvas 2D with a hand-written 3D projection instead of WebGL/three.js.** *Why:* no 600 KB dependency to vendor, full control over accessibility twins (list, keyboard, live region), predictable performance for a few hundred nodes, easy 2D/3D toggle. *Cost:* not a general 3D engine; thousands of nodes would need clustering (documented limitation).
5. **Evidence-first classification; AI strictly as a suggestion layer.** *Why:* the product must not show invented health or progress numbers; every label must be explainable and correctable; models are optional and local.
6. **Per-launch token + Host/Origin checks instead of user accounts.** *Why:* the threat is a hostile web page in the same browser, not other users; a random token in same-origin HTML plus Host validation covers CSRF and DNS rebinding without login UX.
7. **One node per top-level folder; internal structure as components, never as nodes.** *Why:* users organise their workspace folders themselves — a monorepo, a `backend/` + `frontend/` pair or a nested repository is *one* thing to them, and marker-based discovery turned 21 folders into 41 nodes. Nested folders become independent only when the user promotes them (a recorded, reversible choice), so the count of nodes always matches the count of valid folders. *Cost:* a folder that really contains several unrelated projects (`complete/`) shows as one "collection" node until its children are promoted.
