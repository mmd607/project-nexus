"""Native folder picker (tkinter, run in a helper process) and a directory browser fallback.

Both are only reachable through the token-protected local API and never touch file contents.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .fsutil import IgnoreMatcher, list_dir

_PICKER_SCRIPT = r"""
import sys
try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    sys.exit(3)
root = tk.Tk()
root.withdraw()
try:
    root.attributes('-topmost', True)
except Exception:
    pass
path = filedialog.askdirectory(title='Choose a folder that contains your projects', mustexist=True)
root.destroy()
if path:
    sys.stdout.buffer.write(path.encode('utf-8'))
    sys.exit(0)
sys.exit(2)
"""


def pick_folder(timeout: float = 600) -> dict[str, Any]:
    """Open a native folder dialog. Returns {"path": str|None, "available": bool, "cancelled": bool}."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        # PyInstaller bundle: tkinter may not be available; report gracefully.
        try:
            import tkinter  # noqa: F401
        except Exception:  # noqa: BLE001
            return {"path": None, "available": False, "cancelled": False}
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
            except Exception:  # noqa: BLE001
                pass
            path = filedialog.askdirectory(title="Choose a folder that contains your projects", mustexist=True)
            root.destroy()
            return {"path": path or None, "available": True, "cancelled": not path}
        except Exception:  # noqa: BLE001
            return {"path": None, "available": False, "cancelled": False}
    try:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run([exe, "-c", _PICKER_SCRIPT], capture_output=True, timeout=timeout, creationflags=creation, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"path": None, "available": False, "cancelled": False}
    if proc.returncode == 0:
        return {"path": proc.stdout.decode("utf-8", "replace").strip() or None, "available": True, "cancelled": False}
    if proc.returncode == 2:
        return {"path": None, "available": True, "cancelled": True}
    return {"path": None, "available": False, "cancelled": False}


def list_roots() -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    home = str(Path.home())
    roots.append({"path": home, "label": "Home"})
    if sys.platform.startswith("win"):
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append({"path": drive, "label": drive})
    else:
        roots.append({"path": "/", "label": "/"})
        for extra in ("/mnt", "/media", "/Volumes"):
            if os.path.isdir(extra):
                roots.append({"path": extra, "label": extra})
    return roots


def browse(path: str | None) -> dict[str, Any]:
    """List sub-directories (names only) of *path* for the in-app folder chooser."""
    if not path:
        return {"path": None, "parent": None, "dirs": [], "roots": list_roots(), "error": None}
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError:
        return {"path": str(p), "parent": None, "dirs": [], "roots": list_roots(), "error": "cannot resolve path"}
    if not p.is_dir():
        return {"path": str(p), "parent": str(p.parent) if p.parent != p else None, "dirs": [], "roots": list_roots(), "error": "not a directory"}
    listing = list_dir(p, IgnoreMatcher.from_list([]), None)
    dirs = [{"name": d.name, "path": str(Path(d.path))} for d in listing.dirs if not d.name.startswith(("$", "."))][:1000]
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None, "dirs": dirs, "roots": list_roots(), "error": listing.error}
