# Build & test report

Generated during delivery on 2026-09-12, updated 2026-09-13 (folder-based project model, focus view).

## Environment

| | |
|---|---|
| OS | Windows 11 Enterprise 10.0.26200 (AMD64) |
| Python | 3.13.0 (also declared compatible with 3.11+; uses `tomllib`, `os.DirEntry`, `sqlite3` WAL) |
| Git | 2.55.0.windows.4 |
| Node | 26.5.1 (frontend unit tests only; not needed to run the app) |
| Browser | Chromium (Claude desktop app browser pane), DPR 1.25 |
| Third-party runtime dependencies | none |
| Dev tools | pytest 8.4.2, PyInstaller 6.22.2, ruff 0.16.4 (lint only) |

## Backend — `python -X utf8 -m pytest tests -q`

**55 passed, 0 failed** (includes the slow performance test).

```
tests/test_ai.py            8 passed   validate/schema, secret exclusion, opt-in, mock round-trip, injection inert, timeout/garbage, non-local refused, API endpoints
tests/test_api.py          14 passed   CSP/token, token required, cross-origin rejected, DNS-rebinding Host check, traversal blocked, id validation,
                                       full project/files/categories flow (15 top-level projects, nothing nested), promote/merge-back + tree/entry lookups
                                       + mode switch triggers a rescan, settings validation, anonymised export, scan progress/cancel/overlap/purge,
                                       browse, open/rescan by id only
tests/test_classifier.py    7 passed   fixture categories (all 10 categories + Other, Full-stack + AI/ML for the multi-part folder, no "Documentation"
                                       for a folder that merely has docs/), evidence on every category, technologies with evidence,
                                       README description + injection as data, honest "Other" summary, name-keyword-only rejected, defensive parsers
tests/test_scanner.py      20 passed   no crash + skipped entries explained, every top-level folder is exactly one project (== folders on disk),
                                       links never followed (loop + escape), file counts include nested packages/repos, languages/manifests at depth,
                                       mtime & Idle, git dirty + nested repo reported inside its parent, monorepo = one project with Frontend/Backend/Shared
                                       components + Full-stack, multi-part folder components/labels/important files, nested mode candidates → promotion
                                       → independent node with parent link and disjoint counts → merge back, tree/entry lookups, sensitive files flagged
                                       never read, Persian names, incremental cache, change detection, override + missing lifecycle, cancel, limits,
                                       ignore patterns, **scanning never writes into the workspace** (tree signature identical before/after)
tests/test_settings_db.py   5 passed   safe defaults, range/enum validation (incl. scan.mode), persist + corrupt-file recovery,
                                       v1 → v2 migration drops nested rows / keeps overrides / requests a rescan, migrations idempotent + WAL
tests/test_perf.py          1 passed   255 top-level projects (see below)
```

## Lint & static checks

- `python -m ruff check nexus tests fixtures packaging` (rule set E, F, W, B, I from `pyproject.toml`; E501 ignored because long rule tables are deliberate) → **All checks passed**.
- `node --check` on all frontend modules → 0 syntax errors.
- No `innerHTML` assignment anywhere in the frontend (the only occurrences are a comment and a read of the SVG sprite markup); CSP forbids inline scripts/styles and the app runs without CSP violations.

## Frontend — `node --test tests/js/universe.test.mjs`

**11 passed, 0 failed**: hash determinism, layout stability + promoted children next to their parent, ring plan spacing (≥150 world units between ring neighbours, fittable bounding radius), focus satellites (orbit distance, selection of parts: components first, README first among files, configuration files excluded, limit honoured), search-suggestion ranking, 300-node layout without collisions, camera centre/zoom-at-cursor/2D orthographic/reset, perspective ordering, colour helpers, store search & filters & history, i18n fallback and Persian.

## Performance (criterion 9)

`tests/perf_report.json` (fixture: 255 top-level projects, 2 029 files, no Git, same machine):

| Metric | Value |
|---|---|
| Full scan (discover + walk + components + classify + relations) | **2.18 s** |
| Incremental rescan (all cached) | **0.45 s** |
| `GET /api/projects` (all 255 with categories/technologies/components) | 16.2 ms |
| Knowledge graph payload (317 nodes, 6 737 edges) | 21.2 ms |

A real local workspace (23 top-level folders → **21 projects**, 2 empty folders skipped, 10 121 files, 8 Git repositories): full scan **2.8 s** on the folder model (was 41 nodes / ≈6 s with marker-based discovery), incremental ≈ 1 s.

Renderer (synchronous `renderer.draw` timings via the perf hook, 846×814 CSS px canvas, rotation on, DPR 1.25):

| Scene | median ms/frame | p90 | max | labels drawn |
|---|---|---|---|---|
| 309 projects (41 real + 258 fixture + 10 fixture cases) | 15.9 | 29.9 | 45.2 | 41 |
| 41 projects | 5.4 | 10.9 | 18.4 | 15 |

Interpretation: at 309 nodes the median frame fits the 16.7 ms budget of 60 fps, with occasional slower frames (label re-decluttering, GC). Level-of-detail kicks in above 70/140 nodes (no per-face strokes, no beams/pulses, flat diamonds for small nodes, viewport culling), and rendering pauses entirely when nothing animates or the tab is hidden. An earlier measurement inside a *hidden* browser pane showed 13–14 fps because the browser throttles `requestAnimationFrame` for hidden tabs — this is expected browser behaviour, not the app.

Scan/UI concurrency: scans run on a worker thread; the UI polls `/api/scan-runs/{id}` every 700 ms and refreshes the project list every 2.5 s while the graph keeps animating (verified manually while scanning the 258-project fixture).

## Packaging

`python -m PyInstaller packaging/nexus.spec --noconfirm --clean` → `dist/ProjectNexus/` (30 MB, one-folder). Smoke test: `ProjectNexus.exe --port 8790 --no-browser --data-dir <tmp> --add <fixture>` → `/api/health` OK, `/api/session` reports `frozen: true`, index served with CSP, static JS served, fixture scanned (15 top-level projects; rebuilt 2026-09-13 with the folder-based model). Console window kept on purpose (shows URL and log; closing it stops the server).

## Screenshots (docs/screenshots, rendered by `node scripts/screenshots.mjs` through the DevTools protocol with device emulation)

| File | Content |
|---|---|
| `01-universe-3d-1440x900.png` | Universe, 3D: the generated demo workspace (`fixtures/make_demo.py`, 28 top-level folders = 28 nodes), fitted, labelled |
| `02-universe-2d-1440x900.png` | The same universe in 2D (orthographic, flat rings) |
| `03-focus-project-1440x900.png` | Focus view: the demo project `face-detection` centred, rotation paused, its parts (models, notebooks, data, README.md, requirements.txt) as satellites, breadcrumb, details panel |
| `04-focus-2d-1440x900.png` | Focus view in 2D |
| `05-details-needs-attention-1440x900.png` | A *Needs attention* project with its uncommitted-change evidence |
| `06-projects-1440x900.png` | Projects table with filters |
| `07-settings-1440x900.png` | Settings: workspace summary (top-level folders / skipped / loose files), project detection mode, scan limits |
| `08-universe-tablet-768x1024.png`, `09-focus-tablet-768x1024.png` | Tablet layout (icon rail, drawer details) |
| `10-universe-mobile-375x812.png`, `11-focus-mobile-375x812.png` | Phone layout at 2× (bottom navigation, universe fitted above the controls, sheet details) |
| `12-reduced-motion-1440x900.png` | `prefers-reduced-motion: reduce` — no rotation, particles or pulses; focus view still works |
| `13-knowledge-graph-1440x900.png` | Knowledge Graph (projects ↔ technologies ↔ categories) |

## Manual browser verification

- **Project count = valid top-level folders.** The real workspace has 23 sub-folders; 2 are empty and listed as skipped; the universe shows exactly 21 nodes, none of them `frontend/`, `backend/`, `api/`, `packages/*` or a nested repository (the old model produced 41). Loose files at the root (`app.py` …) are counted, not shown.
- Focus view: click / Enter / search + Enter on several real projects (multi-part, single-folder and Git repositories) → camera glides to the node and zooms, rotation pauses, other nodes and labels fade, satellites appear with tethers and labels; clicking a `backend` satellite shows *Folder · Backend part of &lt;project&gt; · file count · size · extensions* and the explorer rooted at `backend/`; Esc returns to the project, Esc again (or the breadcrumb / *Back to workspace*) returns to the fitted universe with rotation resumed.
- Search box: typing a partial name lists the matching projects while non-matching nodes fade; ↓ + Enter jumps to the highlighted result and clears the filter; no match → "No project matches — the universe stays as it is."
- Nested mode: switching in Settings rescans (toast + summary "29 nested candidates"); the details panel lists the candidates (`backend`, `frontend`, `backend/api` …) with *Make independent*; switching back to *Top-level folders* removes the list. Promotion / merge-back exercised through the API tests and the fixture.
- Universe at 1440×900: hub, rings, crystals, labels, stats card, filter chips, controls; selection via click and keyboard; details panel with README description (LTR and RTL text), full path with copy, categories + "why", internal parts, tech stack, evidence, quick info, Git incl. nested repositories, activity, manifests & key files, folder structure, explorer with breadcrumbs/search/pagination and sensitive flags, relations, AI box.
- 2D mode (orthographic, flat rings), rotation toggle, zoom/pan/reset/focus, fullscreen button.
- Search dimming with live counts; status filter from the stats card; category filter from chips.
- Projects table with sorting/filters, Knowledge Graph with 253+ evidence edges and hover explanations, AI Assistant (disabled state, configuration form), Settings (workspaces, full rescan with progress widget, limits, motion/theme/language, privacy, about/export).
- Responsive: 1440×900, 768×1024 (icon rail + drawer) and 375×812 (bottom nav, sheet details, stacked controls); light theme; Persian UI with RTL mirroring.
- States: Loading (spinner overlay + table placeholder), Empty (no workspace → add-folder dialog; no match → notice), Error (server stopped → offline toast, reconnect toast; scan issues → notification bell + per-workspace issue list), Missing project (moved folder → *Missing* badge, warning, evidence, *Forget*; restored folder → reappears with its manual override intact).
- Persistence across a real stop/start of the service (`scripts\stop.ps1` / `start.ps1`): workspaces, manual category override + note, missing-project tombstone.
- `http://localhost:8765`, `http://127.0.0.1:8765` and `http://[::1]:8765` all answer (dual-stack loopback binding).
- No JavaScript console errors on any view (checked after every step above, including the upgrade rescan).
- Upgrade path: the existing v1 database (41 marker-based rows) was migrated in place at start-up — nested rows dropped, top-level rows kept with their manual overrides, automatic full rescan — and the UI came up with 21 nodes without any manual step.

## Not verified in this delivery

- macOS / Linux execution (see LIMITATIONS.md).
- A live Ollama round-trip (Ollama not installed on the build machine); the provider path is covered with a mocked HTTP layer.
- Screen-reader testing (NVDA/VoiceOver) beyond semantic markup, labels and live regions.
