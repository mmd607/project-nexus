"""User settings: a JSON file in the data directory, validated on every write.

The frontend can change these through ``PATCH /api/settings``; unknown keys
and out-of-range values are rejected so a bad request (or a model output that
somehow reached this layer) can never widen scan boundaries or disable the
safety defaults silently.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_IGNORE = [
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".nox", "dist", "build", "target", "out", ".next", ".nuxt", ".svelte-kit",
    ".turbo", ".cache", ".parcel-cache", ".gradle", ".idea", ".vscode", ".vs", "bin", "obj", "coverage", ".coverage",
    "htmlcov", ".eggs", "*.egg-info", ".DS_Store", "Thumbs.db", "desktop.ini", ".terraform", "vendor", "Pods",
    "DerivedData", ".dart_tool", ".expo", "bower_components", "jspm_packages", ".yarn", ".pnp",
]

DEFAULTS: dict[str, Any] = {
    "scan": {
        "mode": "top-level",       # top-level: every direct sub-folder of a workspace is one project
                                   # nested:    additionally list sub-projects inside each folder (promotable to nodes)
        "max_depth": 4,            # directory depth searched for nested sub-projects (nested mode)
        "max_projects": 600,       # per workspace
        "max_files_per_project": 5000,   # files kept per project (the total is still counted)
        "max_file_walk_depth": 10, # depth inside a single project when listing files
        "max_manifest_bytes": 65536,
        "max_readme_bytes": 16384,
        "git_timeout_seconds": 8,
        "activity_window_days": 30,
        "ignore": list(DEFAULT_IGNORE),
        "detect_loose_folders": True,   # nested mode: folders with sources but no manifest count as sub-projects
    },
    "ai": {
        "enabled": False,               # master opt-in; nothing is ever sent while False
        "provider": "ollama",           # ollama | openai_compatible
        "base_url": "http://127.0.0.1:11434",
        "model": "llama3.2",
        "timeout_seconds": 45,
        "allow_non_local_endpoint": False,
        "default_fields": ["name", "languages", "manifests", "dependencies", "technologies", "readme_excerpt"],
    },
    "ui": {
        "theme": "dark",
        "rotation": True,
        "rotation_seconds_per_turn": 240,
        "reduced_motion": "system",  # system | on | off
        "view_mode": "3d",
        "particles": True,
        "language": "en",           # en | fa
        "focus_satellites": 8,      # internal parts/files shown around a focused project (0 = none)
    },
    "privacy": {
        "anonymize_paths_in_export": True,
        "log_full_paths": False,
    },
    "server": {
        "open_browser": True,
    },
}

ALLOWED_AI_PROVIDERS = {"ollama", "openai_compatible"}
SCAN_MODES = ("top-level", "nested")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


class SettingsError(ValueError):
    pass


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _check_int(value: Any, name: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(f"{name} must be an integer")
    if value < lo or value > hi:
        raise SettingsError(f"{name} must be between {lo} and {hi}")
    return value


def validate(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate a *complete* settings dict. Returns a normalised copy."""
    s = copy.deepcopy(settings)
    for section in DEFAULTS:
        if section not in s or not isinstance(s[section], dict):
            raise SettingsError(f"missing section {section}")
    for section, values in s.items():
        if section not in DEFAULTS:
            raise SettingsError(f"unknown section {section}")
        for key in values:
            if key not in DEFAULTS[section]:
                raise SettingsError(f"unknown setting {section}.{key}")
    scan = s["scan"]
    if scan["mode"] not in SCAN_MODES:
        raise SettingsError("scan.mode must be 'top-level' or 'nested'")
    scan["max_depth"] = _check_int(scan["max_depth"], "scan.max_depth", 0, 12)
    scan["max_projects"] = _check_int(scan["max_projects"], "scan.max_projects", 1, 20000)
    scan["max_files_per_project"] = _check_int(scan["max_files_per_project"], "scan.max_files_per_project", 10, 200000)
    scan["max_file_walk_depth"] = _check_int(scan["max_file_walk_depth"], "scan.max_file_walk_depth", 1, 40)
    scan["max_manifest_bytes"] = _check_int(scan["max_manifest_bytes"], "scan.max_manifest_bytes", 1024, 4_000_000)
    scan["max_readme_bytes"] = _check_int(scan["max_readme_bytes"], "scan.max_readme_bytes", 256, 1_000_000)
    scan["git_timeout_seconds"] = _check_int(scan["git_timeout_seconds"], "scan.git_timeout_seconds", 1, 120)
    scan["activity_window_days"] = _check_int(scan["activity_window_days"], "scan.activity_window_days", 1, 3650)
    if not isinstance(scan["ignore"], list) or not all(isinstance(x, str) and x.strip() for x in scan["ignore"]):
        raise SettingsError("scan.ignore must be a list of non-empty strings")
    scan["ignore"] = [x.strip() for x in scan["ignore"]][:500]
    scan["detect_loose_folders"] = bool(scan["detect_loose_folders"])

    ai = s["ai"]
    ai["enabled"] = bool(ai["enabled"])
    if ai["provider"] not in ALLOWED_AI_PROVIDERS:
        raise SettingsError("ai.provider must be 'ollama' or 'openai_compatible'")
    url = urlparse(str(ai["base_url"]))
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise SettingsError("ai.base_url must be an http(s) URL")
    ai["allow_non_local_endpoint"] = bool(ai["allow_non_local_endpoint"])
    if url.hostname not in LOCAL_HOSTS and not ai["allow_non_local_endpoint"]:
        raise SettingsError("ai.base_url must point to a local endpoint unless ai.allow_non_local_endpoint is true")
    ai["base_url"] = str(ai["base_url"]).rstrip("/")
    if not isinstance(ai["model"], str) or not ai["model"].strip() or len(ai["model"]) > 200:
        raise SettingsError("ai.model must be a short non-empty string")
    ai["model"] = ai["model"].strip()
    ai["timeout_seconds"] = _check_int(ai["timeout_seconds"], "ai.timeout_seconds", 3, 600)
    allowed_fields = {"name", "languages", "manifests", "dependencies", "technologies", "readme_excerpt", "file_names"}
    if not isinstance(ai["default_fields"], list) or not set(ai["default_fields"]) <= allowed_fields:
        raise SettingsError("ai.default_fields contains unknown fields")

    ui = s["ui"]
    if ui["theme"] not in {"dark", "light"}:
        raise SettingsError("ui.theme must be dark or light")
    ui["rotation"] = bool(ui["rotation"])
    ui["rotation_seconds_per_turn"] = _check_int(ui["rotation_seconds_per_turn"], "ui.rotation_seconds_per_turn", 20, 3600)
    if ui["reduced_motion"] not in {"system", "on", "off"}:
        raise SettingsError("ui.reduced_motion must be system, on or off")
    if ui["view_mode"] not in {"2d", "3d"}:
        raise SettingsError("ui.view_mode must be 2d or 3d")
    ui["particles"] = bool(ui["particles"])
    ui["focus_satellites"] = _check_int(ui["focus_satellites"], "ui.focus_satellites", 0, 24)
    if ui["language"] not in {"en", "fa"}:
        raise SettingsError("ui.language must be en or fa")

    privacy = s["privacy"]
    privacy["anonymize_paths_in_export"] = bool(privacy["anonymize_paths_in_export"])
    privacy["log_full_paths"] = bool(privacy["log_full_paths"])
    s["server"]["open_browser"] = bool(s["server"]["open_browser"])
    return s


class Settings:
    """Thread-safe settings store persisted as JSON."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULTS)
        if path and path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = validate(_merge(DEFAULTS, loaded))
            except (OSError, ValueError, SettingsError):
                # A corrupt settings file must not brick the app; fall back to defaults
                # and keep the bad file aside for inspection.
                try:
                    path.replace(path.with_suffix(".json.corrupt"))
                except OSError:
                    pass
                self._data = copy.deepcopy(DEFAULTS)
        self.save()

    def get(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def section(self, name: str) -> dict[str, Any]:
        return self.get()[name]

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise SettingsError("settings patch must be an object")
        with self._lock:
            candidate = validate(_merge(self._data, patch))
            self._data = candidate
            self.save()
            return copy.deepcopy(candidate)

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
