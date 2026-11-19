"""Location of Nexus' own data directory (database, settings, logs).

The tool keeps *all* of its state here, never inside the scanned projects.
Override with ``--data-dir`` or the ``NEXUS_DATA_DIR`` environment variable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("NEXUS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    home = Path.home()
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        return base / "ProjectNexus"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "ProjectNexus"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "project-nexus"


def ensure_data_dir(path: Path | None = None) -> Path:
    target = (path or default_data_dir()).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "logs").mkdir(exist_ok=True)
    return target


def static_dir() -> Path:
    """Directory holding the bundled frontend (works from source and from PyInstaller)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidate = Path(bundled) / "nexus" / "static"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "static"
