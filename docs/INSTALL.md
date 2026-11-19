# Installation & running

Project Nexus is a single Python package with **no third-party dependencies**. There are three ways to run it; all were verified on Windows 11 with Python 3.13 and are written to work identically on macOS and Linux (see "Verified environments" at the end for what was actually exercised).

## Option A — run from source (all platforms)

1. Install **Python 3.11 or newer** (python.org, Microsoft Store, Homebrew, or your distribution). Check: `python --version` (on macOS/Linux the command may be `python3`).
2. Install **Git** if you want branch / uncommitted-changes information (optional; everything else works without it).
3. Unzip / clone this repository and open a terminal in its root (`project-nexus/`).
4. Start it:

   ```bash
   python -m nexus --add "D:\MyProjects"        # Windows
   python3 -m nexus --add ~/projects            # macOS / Linux
   ```

   The terminal prints `Project Nexus: http://127.0.0.1:8765/` and your browser opens. The first scan of the folder starts immediately; you can watch progress in the sidebar and keep using the UI while it runs.

Convenience launchers: `run.bat` (double-click on Windows), `scripts/run.ps1`, `scripts/run.sh`.

### Background service: start / stop

| | Windows | macOS / Linux |
|---|---|---|
| start on `http://localhost:8765` | `powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Add "D:\Projects"] [-Port 8765]` | `bash scripts/start.sh [--add ~/projects]` |
| stop | `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 [-Port 8765]` or double-click `stop.bat` | `bash scripts/stop.sh` |
| logs | `%LOCALAPPDATA%\ProjectNexus\logs\nexus.log` | `~/.local/share/project-nexus/logs/nexus.log` (Linux), `~/Library/Application Support/ProjectNexus/logs/` (macOS) |

The foreground form (`python -m nexus …`) stops with Ctrl+C. The server binds both `127.0.0.1` and `::1`, so `localhost`, `127.0.0.1` and `[::1]` all work; nothing is reachable from other machines unless you pass `--host` with `--allow-remote`.

### Demo workspace (sample data)

```bash
python fixtures/make_demo.py "X:\ProjectNexus-Demo"      # any empty target folder
python -m nexus --add "X:\ProjectNexus-Demo"
```

Creates 28 top-level sample folders across every category: Git repositories with commit history (one with uncommitted changes → *Needs attention*, one archived → *Idle*), a monorepo with workspaces and a local `file:` dependency (one node whose packages show up as components), a multi-part folder (`smart-home` with `backend/` + `frontend/` → one Full-stack node), a static site, a Persian-named project, secret-looking files that are flagged and never read, and a loose folder without a manifest. Delete and regenerate freely.

### Useful options

| Option | Meaning |
|---|---|
| `--add FOLDER` | register a projects folder at start (repeatable). You can also add folders later in *Settings → Add folder*. |
| `--port 8765` | port to listen on (`0` picks a free port) |
| `--data-dir PATH` | where Nexus keeps its own database/settings (default: see README) |
| `--scan` | rescan every registered workspace at launch |
| `--no-browser` | do not open the browser automatically |
| `--desktop` | open in a native window instead of the browser (requires `pip install pywebview`) |
| `--host` + `--allow-remote` | bind to a non-loopback interface (**exposes the UI to your network**; off by default) |

### Install as a command

```bash
pip install .                # or: pip install -e .   (editable, for development)
nexus --add ~/projects       # `nexus` and `project-nexus` commands are now on PATH
pip install ".[desktop]"     # optional native window support (pywebview)
```

## Option B — packaged executable (no Python on the target machine)

Build once on a machine that has Python 3.11+:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

```bash
# macOS / Linux
bash scripts/build_exe.sh
```

This produces `dist/ProjectNexus/` (≈30 MB): `ProjectNexus.exe` (Windows) or `ProjectNexus` (macOS/Linux), a `Start-ProjectNexus.cmd` / `start-project-nexus.sh` launcher, and the docs. Copy the whole folder anywhere and run the executable; it accepts the same options as `python -m nexus`. Closing the console window stops the server.

Notes:
- PyInstaller builds are platform-specific: build on Windows for Windows, on macOS for macOS, etc.
- The native "Choose folder…" dialog needs Tk, which PyInstaller bundles automatically when it is available in the build Python. If it is missing, the in-app folder browser and typed paths still work.
- Unsigned binaries trigger SmartScreen / Gatekeeper warnings; use *More info → Run anyway* (Windows) or right-click → *Open* (macOS), or run from source instead.

## Option C — development

```bash
pip install -e ".[dev]"                      # pytest + pyinstaller
python -X utf8 -m pytest tests -q            # backend tests (incl. the slow perf test)
node --test tests/js/universe.test.mjs       # frontend tests (Node 18+)
python fixtures/make_fixture.py /tmp/nexus-fixture --big 250   # sample workspace
python -m nexus --data-dir /tmp/nexus-data --add /tmp/nexus-fixture
```

The frontend has **no build step** (plain ES modules served by the Python server), so editing files under `nexus/static/` only needs a browser reload. Backend changes need a restart.

## First run

1. If no workspace is registered, the *Add a projects folder* dialog opens: use the system folder dialog, browse in-app, or type a path. Choose the **parent folder that contains your projects** (scanning a whole drive is refused by default because it can take very long).
2. The scan runs in the background with a progress bar and a cancel button. Projects appear in the Universe as they are analysed.
3. Click any crystal (or a row in *Projects*, or use the keyboard) to open the details panel.

Nothing inside the scanned folders is ever modified. Nexus writes only to its data directory.

## Uninstall

Delete the repository / `dist/ProjectNexus` folder and the data directory (`%LOCALAPPDATA%\ProjectNexus`, `~/Library/Application Support/ProjectNexus` or `~/.local/share/project-nexus`). If installed with pip: `pip uninstall project-nexus`.

## Verified environments

| Environment | Verified |
|---|---|
| Windows 11 (10.0.26200), Python 3.13.0, Git 2.55, Node 26, Chrome | source run, background start/stop scripts, all tests, lint, PyInstaller build and packaged run, screenshots |
| macOS / Linux | code paths are platform-neutral (pathlib, stdlib server, `xdg-open`/`open`); **not executed in this delivery** — see LIMITATIONS.md |
