# Project Nexus

<div dir="rtl">

**داشبورد محلی برای کشف، تحلیل و مدیریت تصویری پروژه‌های روی رایانهٔ شما.**
یک یا چند پوشه را انتخاب می‌کنید؛ **هر پوشهٔ اصلی داخل آن، دقیقاً یک پروژه و یک نود در کهکشان است** (به نام همان پوشه). Nexus زبان‌ها، فناوری‌ها، وضعیت Git، زمان آخرین فعالیت، بخش‌های داخلی (Frontend/Backend/AI/Docs…) و دسته‌ها را (همراه با شواهد) از کل محتوای پوشه استخراج می‌کند و همه را در یک «کهکشان» تعاملی سه‌بعدی و یک فهرست متنی دسترس‌پذیر نشان می‌دهد. زیرپوشه‌هایی مثل `frontend`، `backend`، `packages` یا مخازن Git تودرتو **نود جداگانه نمی‌شوند**؛ فقط در جزئیات و در نمای Focus همان پروژه دیده می‌شوند، مگر این‌که خودتان آن‌ها را از تنظیمات «مستقل» کنید.

- **کاملاً محلی:** هیچ سرویس ابری، هیچ تله‌متری. سرور فقط روی `127.0.0.1` گوش می‌دهد.
- **فقط‌خواندنی:** هیچ فایلی در پروژه‌های شما نوشته یا اجرا نمی‌شود. داده‌ها و تنظیمات Nexus جداگانه ذخیره می‌شوند.
- **بدون عدد ساختگی:** هر وضعیت و دسته با شواهد مشخص (فایل، وابستگی، کامیت) همراه است. «سلامت» یا «درصد پیشرفت» جعلی وجود ندارد.
- **AI اختیاری و محلی:** تنها با فعال‌سازی صریح، از Ollama یا هر سرور محلی سازگار با OpenAI پیشنهاد دسته می‌گیرد؛ پیشنهادها قابل تأیید یا رد هستند و فایل‌های حساس هرگز ارسال نمی‌شوند.

## اجرای سریع

**پیش‌نیاز:** Python 3.11 یا جدیدتر (و Git برای نمایش وضعیت مخزن‌ها). هیچ بستهٔ دیگری لازم نیست.

```bash
cd project-nexus
python -m nexus --add "D:\MyProjects"
```

مرورگر روی `http://localhost:8765/` باز می‌شود و اسکن پوشه شروع می‌شود. در ویندوز می‌توانید `run.bat` را دوبار کلیک کنید و پوشه را از داخل برنامه (تنظیمات ← افزودن پوشه) انتخاب کنید.

**اجرا در پس‌زمینه و توقف (ویندوز):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1     # اجرا روی http://localhost:8765
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1      # توقف سرویس (یا دوبار کلیک روی stop.bat)
```

**مجموعهٔ پروژهٔ نمایشی (بدون نیاز به فایل‌های شخصی):**

```bash
python fixtures/make_demo.py "X:\ProjectNexus-Demo"     # ۲۸ پوشهٔ نمونه در همهٔ دسته‌ها
python -m nexus --add "X:\ProjectNexus-Demo"
```

**نسخهٔ بدون نیاز به Python (بستهٔ اجرایی):** پس از ساخت با `scripts\build_exe.ps1` (یا `scripts/build_exe.sh`)، پوشهٔ `dist\ProjectNexus` را هر جا کپی کنید و `ProjectNexus.exe` (یا `ProjectNexus` در macOS/Linux) را اجرا کنید.

راهنمای کامل نصب: [docs/INSTALL.md](docs/INSTALL.md) · راه‌اندازی مدل محلی: [docs/AI_SETUP.md](docs/AI_SETUP.md) · محدودیت‌ها: [docs/LIMITATIONS.md](docs/LIMITATIONS.md)

</div>

---

**Local-first dashboard that discovers, analyses and visualises the software projects on your machine.**

Point Nexus at one or more folders. **Every top-level folder inside a workspace is exactly one project and one node**, named after the folder. Nexus measures languages, technologies, Git state (including nested repositories), last activity, internal parts (Frontend / Backend / AI / Docs / Tests / Deployment …) and categories (each with its evidence) from the *whole* folder, and shows everything as an interactive 3D "universe" plus an accessible text list. Sub-folders such as `frontend/`, `backend/`, `packages/*` or nested `.git` repositories never become nodes of their own; they appear as components in the details panel and as satellites in the project's focus view — unless you promote them in *Settings → Project detection → Detect nested projects*.

- **Local only.** No cloud, no telemetry. The server binds to `127.0.0.1`.
- **Read-only.** Nothing inside your projects is written or executed. Nexus keeps its own SQLite database and settings in a separate data directory.
- **No invented numbers.** Every status and category is backed by concrete evidence (files, dependencies, commits). There is no fake "health score".
- **Optional local AI.** Only after explicit opt-in, Ollama (or any OpenAI-compatible local server) can *suggest* categories and a description. Suggestions are accepted or rejected by you; secret-looking files are never sent.

## Quick start

Requires **Python 3.11+** (Git optional, for repository status). No third-party packages.

```bash
cd project-nexus
python -m nexus --add "/path/to/your/projects"
```

The browser opens `http://127.0.0.1:8765/` and the first scan starts. You can also add folders from *Settings → Add folder* (native folder dialog or in-app browser).

```bash
python -m nexus --help          # all options: --port, --data-dir, --scan, --no-browser, --desktop, --add
python -m nexus --desktop       # native window (needs: pip install pywebview)
pip install .                   # installs the `nexus` command
```

Run in the background / stop (Windows: `scripts\start.ps1`, `scripts\stop.ps1` or `stop.bat`; macOS/Linux: `scripts/start.sh`, `scripts/stop.sh`). The server listens on `127.0.0.1` and `::1`, so `http://localhost:8765/` works everywhere.

**Demo data** — a realistic sample workspace (28 top-level folders → 28 nodes) covering every category (Git repos, a dirty repo, a monorepo, a backend+frontend folder, idle/archived folders, a Persian-named project):

```bash
python fixtures/make_demo.py /path/to/ProjectNexus-Demo
python -m nexus --add /path/to/ProjectNexus-Demo
```

**Packaged build (no Python needed on the target machine):** `scripts\build_exe.ps1` on Windows or `scripts/build_exe.sh` on macOS/Linux produces `dist/ProjectNexus/`. Copy the folder anywhere and run `ProjectNexus.exe` / `./ProjectNexus`.

## What you get

| Area | What it does |
|---|---|
| **Universe** | Central hub crystal (= the workspace), orbital rings sized to the number of folders, one shaded crystal per top-level folder (colour = primary category, beads = other categories, dot = status), collision-free labels, fit-to-view on load. Slow rotation (one turn per ~4 min, pausable, honours `prefers-reduced-motion`), drag to pan, wheel/pinch to zoom, click/tap/keyboard to select, 3D and true-flat 2D modes (smooth transition, choice remembered), search suggestions with ↑/↓ + Enter that fly the camera to a project, filter chips. **Focus view:** the selected folder glides to the centre, rotation pauses, the rest fades and its main parts (components, README, manifests, entry points, deployment files — at most 8, configurable) orbit it as satellites; click one for its metadata; breadcrumb / Esc / *Back to workspace* return. |
| **Projects** | The accessible twin of the graph: sortable, filterable table with keyboard navigation and row virtualisation for hundreds of projects. |
| **Details** | Folder name and full path (copyable), editable description, evidence-backed status, multi-label categories with "why?", internal parts with their evidence, tech stack from manifests at any depth, measured quick facts (files, size, folders, last modified, last scanned), Git branch/dirty/ahead-behind/last commit plus nested repositories, recent activity (real commits and file changes), manifests & key files, two-level folder structure, a read-only file explorer with breadcrumbs and search (secrets flagged, never read), nested-project candidates with *Make independent* (nested mode), related projects, manual category/description overrides, optional AI suggestion. Selecting a satellite or an explorer entry shows that file/folder: name, relative path, type, size, modified time and how it relates to the project. |
| **Knowledge Graph** | Force-directed graph of projects ↔ technologies ↔ categories plus real project links (shared technology, local path dependencies, contains). Every edge lists its evidence; a text table mirrors it. |
| **AI Assistant** | Off by default. Configure Ollama / OpenAI-compatible endpoint, choose exactly which metadata to share, preview the payload, send, then accept or reject. |
| **Settings** | Workspaces (add / rescan / full rescan / rename / remove, with a scan summary: top-level folders, skipped entries and why, loose files, promoted sub-folders), **project detection mode** (*Top-level folders* — default — or *Detect nested projects*), scan limits and ignore patterns, activity window, motion/theme/language (English or Persian, RTL), focus satellites count, privacy, JSON export. |

## Layout of this repository

```
nexus/               Python package (stdlib only)
  scanner.py         one project per top-level folder, bounded walk, incremental analysis, scan jobs
  components.py      internal parts (components), nested-project candidates, important files, structure kind
  classifier.py      explainable rules → categories & technologies
  gitinfo.py         read-only git inspection (fixed args, timeouts, hooks disabled)
  ai.py              optional local-model suggestions (opt-in, validated)
  server.py          local HTTP API + static frontend (token, Host/Origin checks, CSP)
  static/            frontend (vanilla ES modules, Canvas 2D renderer, no build step)
tests/               pytest suite + node:test suite (see docs/TEST_REPORT.md)
fixtures/            acceptance fixture generator (make_fixture.py) and demo workspace generator (make_demo.py)
docs/                INSTALL, AI_SETUP, SECURITY, ARCHITECTURE, ACCEPTANCE, TEST_REPORT, LIMITATIONS
packaging/, scripts/ PyInstaller spec, start/stop/build/test/screenshot scripts
docs/screenshots/    rendered UI captures at 1440×900, 768×1024 and 375×812
```

## Running the tests

```bash
python -X utf8 -m pytest tests -q            # backend (add -m "not slow" to skip the 250-project perf test)
node --test tests/js/universe.test.mjs       # frontend pure modules
python -m ruff check nexus tests fixtures    # lint (pip install ruff)
node scripts/screenshots.mjs                 # regenerate docs/screenshots (3D, 2D, focus, tablet, phone, reduced motion) against a running server
```

Last local run: **55 passed** (Python 3.13, Windows 11, 2026-11-19).

## Data location

`%LOCALAPPDATA%\ProjectNexus` (Windows), `~/Library/Application Support/ProjectNexus` (macOS), `~/.local/share/project-nexus` (Linux) — override with `--data-dir` or `NEXUS_DATA_DIR`. Contains `nexus.db` (SQLite, WAL), `settings.json`, `logs/`.

## License

MIT (see [LICENSE](LICENSE)).

## Author

Mohammad Homaiyan — [@mmd607](https://github.com/mmd607)
