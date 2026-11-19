# Known limitations (honest list)

Things this version does **not** do, or does only partially. None of them is hidden behind invented data.

## Project model (folder = project)

- **One node per top-level folder is a rule, not a detection.** A workspace folder that itself contains several unrelated projects (e.g. `complete/` holding four finished experiments) is shown as *one* "collection" node with its children as components. Switch *Settings → Project detection* to *Detect nested projects* and press *Make independent* on the ones you want as nodes; the choice is stored per workspace and survives rescans.
- **Component kinds are heuristics.** Folder names (`backend`, `web`, `ml`, `docs` …) and the classifier's rules decide the kind; an unusual layout can leave a part unlabelled (it is then simply absent from the components list) or label it *Module*. Every component shows the evidence that produced it.
- **Nested repositories:** Git status is collected for at most eight nested `.git` folders per project; further ones are listed as "not inspected".
- **File lists are capped** (`scan.max_files_per_project`, default 5000) — the total file count and the folder tree counts stay exact, but the explorer and file search only see the stored entries (shown as "listed").
- **Focus satellites are a summary**: at most `ui.focus_satellites` (default 8) parts are drawn; the panel's explorer and the *Manifests & key files* card list the rest.

## Platform & packaging

- **macOS and Linux were not executed** during this delivery (built and tested on Windows 11 only). The code is platform-neutral (pathlib, stdlib HTTP server, `open`/`xdg-open`, POSIX symlink checks) and the fixture generator falls back from junctions to symlinks, but expect small rough edges (e.g. Tk availability for the native folder dialog on minimal Linux installs → use the in-app browser or type the path).
- The packaged build is a PyInstaller **one-folder** bundle (~30 MB) that is **unsigned**: SmartScreen/Gatekeeper will warn on first run. There is no installer (MSI/DMG/AppImage) and no auto-update.
- `--desktop` (native window) requires the optional `pywebview` package; the default experience is the system browser.
- The HTTP layer is Python's `http.server` (threaded, HTTP/1.1). It is adequate for one local user, not a hardened multi-user web server.

## Scanning & analysis

- Nodes are folders, not detections: the *contents* of a folder are analysed heuristically (see above), and the nested-projects list in `nested` mode uses marker rules (manifest, `.git`, Dockerfile/Makefile with sources, loose source folders) that can miss unusual layouts or include tool folders.
- File listing is capped per project (default 5 000; configurable up to 200 000). Capped projects are marked `+` / "list truncated". Depth is limited (discovery 4, inside a project 10).
- Languages are derived from extensions and byte counts, not from parsing; generated or vendored code inside a project counts unless its folder is in the ignore list.
- Technology detection recognises a curated list of dependencies, images and files (~450 entries). Unknown libraries are not shown as technologies; categories fall back to `Other` with an explicit "no signal" note.
- Category confidence is a **rule confidence** (how many/how strong the signals were), not a measure of quality, progress or health. There is deliberately no "health score".
- `Active` / `Idle` depend on file mtimes and Git commits; copying a project (which resets mtimes) can make an old project look active. `Needs attention` only reflects uncommitted changes or scan issues.
- Git information needs the `git` executable. Nested worktrees / submodules are treated as nested repositories; `ahead/behind` needs an upstream branch; the "commits in the last 30 days" count is per path.
- Relations are limited to *contains*, *local path dependency* (`file:`/`link:`/`path =`/`-e ../x`) and *shared technology* (frameworks/libraries/databases/platforms; very common technologies shared by >80 projects are skipped). Cross-project imports in code are not analysed.
- Incremental scanning relies on file size + mtime and `.git` metadata; content changes that keep size and mtime identical are not detected (use *Full rescan*). File-system watching (live updates without rescanning) is not implemented.
- Analysis is single-threaded per workspace (Git calls dominate on large repos). A workspace scan cannot run twice concurrently; different workspaces can.

## Universe / UI

- Canvas 2D with a custom projection, not a GPU engine. Verified smooth up to ~300 projects (median 16 ms/frame); thousands of projects would need aggressive clustering that is not implemented. Above 600 projects per workspace the scanner stops by default (configurable).
- Labels are decluttered by priority; with hundreds of nodes most labels appear only on hover, keyboard focus, selection or when zoomed in. There is no manual node dragging in the Universe (the Knowledge Graph supports dragging).
- 2D mode is a flat orthographic top-down view; it is not a separate diagram layout.
- Keyboard navigation orders nodes by angle (←/→) and name (↑/↓); there is no spatial "nearest node" navigation.
- The Knowledge Graph force layout is recomputed on each visit (positions are not persisted) and becomes dense above ~300 nodes; use the technology/category toggles and the minimum-shared slider.
- The Persian translation covers the interface chrome; evidence strings, technology names and category names stay in English. Right-to-left mirroring is applied globally.
- No screen-reader session was run; semantics (roles, labels, live regions, focus order) are in place but untested with NVDA/VoiceOver.

## AI

- Only Ollama's `/api/chat` and the OpenAI-compatible `/v1/chat/completions` protocols are supported; no streaming, no batch suggestions for a whole workspace, one request at a time.
- The model may still misclassify; suggestions are never applied automatically. Small models sometimes ignore the JSON instruction, which surfaces as a "malformed JSON" error rather than a wrong answer.
- A live end-to-end run against a real Ollama instance was not part of this delivery (see TEST_REPORT.md).

## Data

- Removing a workspace keeps its data unless "Also delete its stored data" is ticked; missing projects are kept as tombstones until *Forget*.
- The export is JSON only (no CSV/Markdown report). Import of an export is not implemented.
- The database schema has a single migration (v1); future changes will be additive migrations.
