"""Bounded, read-only workspace scanner with incremental analysis.

Project model: **every direct sub-folder of a workspace is exactly one project** — named after the
folder. Whatever lives inside (``backend/``, ``frontend/``, ``apps/web``, nested repositories, several
manifests) is analysed as part of that project: languages, technologies, Git repositories, components
and the folder structure all roll up to the parent. Nested folders only become nodes of their own when
the user promotes them explicitly (Settings → nested projects), and "nested" scan mode merely *lists*
the candidates.

Pipeline: discover top-level folders → walk each folder (names/sizes only) → parse manifests → detect
components → classify → git snapshot(s) → status from evidence → persist. Each project is committed as
soon as it is analysed so the UI can show partial results, and a cancel flag is checked between
directories and projects.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat as _stat
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import classifier, components, gitinfo, repo
from .db import Database
from .fsutil import IgnoreMatcher, is_reparse_or_link, is_within, list_dir, read_text_capped
from .languages import CODE_LANGUAGES, classify_kind, is_sensitive, language_for, split_ext
from .manifests import EXT_MARKERS, MANIFEST_FILES, STRONG_MARKERS, Manifest, parse_csproj, parse_manifest
from .model import FileEntry, ProjectFacts
from .settings import Settings

# Bump whenever classification/parsing rules change: it is mixed into every fingerprint so cached
# analyses are refreshed on the next scan instead of lingering with stale results.
ANALYZER_VERSION = "2026.09.13-2"
README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme", "readme.markdown")
# Folder names that are never projects when they sit directly in a workspace (OS/system folders).
SYSTEM_DIRS = {"$recycle.bin", "system volume information", "lost+found", "recovery", "$windows.~bt", "windows", "program files",
               "program files (x86)", "programdata", "perflogs", "msocache", "config.msi"}
PROBE_MAX_ENTRIES = 4000     # how far to look for "at least one file" before calling a folder empty
PROBE_MAX_DEPTH = 8
HARD_MAX_ENTRIES = 250_000   # absolute bound on entries visited per project (counting continues past max_files)
MAX_NESTED_GIT = 8           # nested repositories inspected with git per project
MAX_MANIFESTS = 40
MAX_MANIFEST_DEPTH = 4
MAX_STRUCTURE_TOP = 40
MAX_STRUCTURE_CHILDREN = 12


@dataclass
class Discovered:
    path: Path
    relative_path: str
    depth: int
    detected_type: str            # folder | promoted
    evidence: list[dict[str, Any]]
    parent_rel: str | None = None
    children: list["Discovered"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name or str(self.path)


def _has_git_dir(path: Path) -> bool:
    try:
        st = os.lstat(path / ".git")
    except OSError:
        return False
    return _stat.S_ISDIR(st.st_mode) or _stat.S_ISREG(st.st_mode)


@dataclass
class Probe:
    error: str | None
    has_files: bool
    entries: int


def probe_folder(path: Path, ignore: IgnoreMatcher, root: Path) -> Probe:
    """Cheap bounded look: is the folder readable and does it contain at least one (non-ignored) file?"""
    stack: list[tuple[Path, int]] = [(path, 0)]
    entries = 0
    first_error: str | None = None
    while stack and entries < PROBE_MAX_ENTRIES:
        current, depth = stack.pop()
        listing = list_dir(current, ignore, root)
        if listing.error:
            if depth == 0:
                return Probe(listing.error, False, entries)
            first_error = first_error or listing.error
            continue
        if listing.files:
            return Probe(None, True, entries)
        entries += len(listing.dirs)
        if depth < PROBE_MAX_DEPTH:
            stack.extend((Path(d.path), depth + 1) for d in listing.dirs)
    return Probe(None, False, entries)


def discover_top_level(root: Path, ignore: IgnoreMatcher, promoted: set[str], cancel: threading.Event,
                       on_error: Callable[[str, str], None] | None = None) -> tuple[list[Discovered], dict[str, Any]]:
    """One project per direct sub-folder of *root*, plus the sub-folders the user promoted.

    Returns the projects (parents before their promoted children) and a summary explaining every
    top-level entry that did *not* become a project.
    """
    summary: dict[str, Any] = {"top_level": 0, "skipped": [], "loose_files": 0, "promoted": 0, "promoted_missing": []}
    listing = list_dir(root, ignore, root)
    if listing.error:
        if on_error:
            on_error(".", listing.error)
        return [], summary
    summary["loose_files"] = len(listing.files)
    if listing.skipped_links:
        summary["skipped"].append({"name": f"{listing.skipped_links} link(s)/junction(s)", "reason": "links are never followed"})
    results: list[Discovered] = []
    for entry in listing.dirs:
        if cancel.is_set():
            break
        name = entry.name
        if name.startswith(".") or name.lower() in SYSTEM_DIRS:
            summary["skipped"].append({"name": name, "reason": "hidden or system folder"})
            continue
        path = Path(entry.path)
        probe = probe_folder(path, ignore, root)
        if probe.error:
            summary["skipped"].append({"name": name, "reason": probe.error})
            if on_error:
                on_error(name, probe.error)
            continue
        if not probe.has_files:
            summary["skipped"].append({"name": name, "reason": "empty folder"})
            continue
        results.append(Discovered(path, name, 1, "folder", [{"rule": "top-level", "detail": "direct sub-folder of the workspace"}]))
    summary["top_level"] = len(results)

    by_rel: dict[str, Discovered] = {d.relative_path: d for d in results}
    for rel in sorted(promoted, key=lambda r: (r.count("/"), r.lower())):
        rel = rel.strip("/").replace("\\", "/")
        if "/" not in rel:
            continue  # a top-level folder is a project anyway
        path = root.joinpath(*rel.split("/"))
        anc: Discovered | None = None
        for cand_rel, cand in by_rel.items():
            if rel.startswith(cand_rel + "/") and (anc is None or len(cand_rel) > len(anc.relative_path)):
                anc = cand
        try:
            valid = anc is not None and path.is_dir() and not is_reparse_or_link(path) and is_within(path, root)
        except OSError:
            valid = False
        if not valid:
            summary["promoted_missing"].append(rel)
            if on_error:
                on_error(rel, "promoted folder not found (still listed in Settings)")
            continue
        d = Discovered(path, rel, rel.count("/") + 1, "promoted",
                       [{"rule": "promoted", "detail": "marked as an independent project in Settings"}], anc.relative_path)  # type: ignore[union-attr]
        anc.children.append(d)  # type: ignore[union-attr]
        results.append(d)
        by_rel[rel] = d
        summary["promoted"] += 1
    return results, summary


# ---------------------------------------------------------------- analysis
@dataclass
class Walk:
    files: list[FileEntry]           # stored entries (capped at max_files)
    dir_names: set[str]
    top_level: set[str]
    dir_count: int
    truncated: bool                  # more files exist than were stored
    size_bytes: int
    last_modified: int | None
    last_modified_path: str | None
    errors: list[str]
    total_files: int = 0             # every file seen, stored or not
    git_dirs: set[str] = field(default_factory=set)      # nested folders that carry their own .git
    dirs: list[str] = field(default_factory=list)        # relative directory paths (depth ≤ 2, for the structure view)
    dir_stats: dict[str, list[int]] = field(default_factory=dict)   # depth ≤ 2 prefix → [files, bytes]
    hard_truncated: bool = False


def walk_project(path: Path, root: Path, ignore: IgnoreMatcher, exclude_rel: set[str], max_files: int, max_depth: int,
                 cancel: threading.Event) -> Walk:
    """List every file of a project (no contents). Counting continues after *max_files* so totals stay honest."""
    files: list[FileEntry] = []
    dir_names: set[str] = set()
    top_level: set[str] = set()
    errors: list[str] = []
    git_dirs: set[str] = set()
    dirs: list[str] = []
    dir_stats: dict[str, list[int]] = {}
    dir_count = 0
    size = 0
    total = 0
    visited = 0
    last_mtime, last_path = None, None
    truncated = hard = False
    stack: list[tuple[Path, str, int]] = [(path, "", 0)]
    while stack:
        if cancel.is_set() or visited >= HARD_MAX_ENTRIES:
            hard = visited >= HARD_MAX_ENTRIES
            break
        current, rel, depth = stack.pop()
        listing = list_dir(current, ignore, root)
        if listing.error:
            errors.append(f"{rel or '.'}: {listing.error}")
            continue
        if rel and _has_git_dir(current):
            git_dirs.add(rel)
        if depth == 0:
            top_level.update(e.name.lower() for e in listing.files)
            top_level.update(d.name.lower() for d in listing.dirs)
        prefixes: list[str] = []
        if rel:
            parts = rel.split("/")
            prefixes = [parts[0]] if len(parts) == 1 else [parts[0], parts[0] + "/" + parts[1]]
        for entry in listing.files:
            visited += 1
            frel = f"{rel}/{entry.name}" if rel else entry.name
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            fsize = int(st.st_size)
            mtime = int(st.st_mtime)
            total += 1
            size += fsize
            for p in prefixes:
                s = dir_stats.get(p)
                if s is None:
                    dir_stats[p] = [1, fsize]
                else:
                    s[0] += 1
                    s[1] += fsize
            if last_mtime is None or mtime > last_mtime:
                last_mtime, last_path = mtime, frel
            if len(files) < max_files:
                ext = split_ext(entry.name)
                kind = classify_kind(frel, ext)
                files.append(FileEntry(frel, ext, fsize, mtime, kind, kind == "secret" or is_sensitive(frel)))
            else:
                truncated = True
        if depth < max_depth:
            for d in listing.dirs:
                visited += 1
                drel = f"{rel}/{d.name}" if rel else d.name
                if drel in exclude_rel:
                    continue
                dir_names.add(d.name.lower())
                dir_count += 1
                if depth < 2:
                    dirs.append(drel)
                stack.append((Path(d.path), drel, depth + 1))
    return Walk(files, dir_names, top_level, dir_count, truncated, size, last_mtime, last_path, errors, total, git_dirs, dirs, dir_stats, hard)


def _read_manifests(path: Path, walk: Walk, max_bytes: int) -> list[Manifest]:
    manifests: list[Manifest] = []
    seen: set[str] = set()
    candidates = sorted((f for f in walk.files if f.relative_path.count("/") < MAX_MANIFEST_DEPTH and not f.sensitive),
                        key=lambda f: (f.relative_path.count("/"), f.relative_path.lower()))
    for f in candidates:
        name = f.relative_path.rsplit("/", 1)[-1].lower()
        kind = MANIFEST_FILES.get(name)
        if kind is None and name.endswith((".csproj", ".fsproj")):
            kind = "csproj"
        if kind is None and name.startswith("requirements") and name.endswith(".txt"):
            kind = "requirements"
        if kind is None and name.startswith("dockerfile"):
            kind = "dockerfile"
        if kind is None or f.relative_path in seen:
            continue
        seen.add(f.relative_path)
        if f.size > max_bytes and kind not in {"package.json", "pyproject", "requirements", "cargo", "gomod", "pubspec", "composer"}:
            continue
        text = read_text_capped(path / f.relative_path, max_bytes)
        if text is None:
            continue
        manifests.append(parse_csproj(f.relative_path, text) if kind == "csproj" else parse_manifest(kind, f.relative_path, text))
        if len(manifests) >= MAX_MANIFESTS:
            break
    return manifests


_BADGE = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML = re.compile(r"<[^>]+>")


def _read_readme(path: Path, walk: Walk, max_bytes: int) -> tuple[str | None, str | None, str | None]:
    """Returns (title, description, excerpt) from the root README, if any."""
    candidate = None
    for f in walk.files:
        if "/" in f.relative_path:
            continue
        if f.relative_path.lower() in README_NAMES:
            candidate = f
            break
    if not candidate:
        return None, None, None
    text = read_text_capped(path / candidate.relative_path, max_bytes)
    if not text:
        return None, None, None
    text = _BADGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _HTML.sub("", text)
    text = re.sub(r"(\*\*|__|`)", "", text)
    title = None
    description = None
    paragraphs: list[str] = []
    buf: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            if title is None:
                title = line.lstrip("#").strip()[:120] or None
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        if not line or line.startswith(("```", "---", "===", "|", "<!--")):
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        paragraphs.append(" ".join(buf))
    for p in paragraphs:
        cleaned = re.sub(r"\s+", " ", p).strip(" *_-")
        if len(cleaned) >= 20 and not cleaned.lower().startswith(("table of contents", "copyright", "license")):
            description = cleaned[:280].rstrip() + ("…" if len(cleaned) > 280 else "")
            break
    excerpt = re.sub(r"\s+", " ", " ".join(paragraphs))[:2000] or None
    return title, description, excerpt


def _languages(files: list[FileEntry]) -> tuple[list[dict[str, Any]], str | None, dict[str, dict[str, int]]]:
    stats: dict[str, dict[str, int]] = {}
    for f in files:
        name = f.relative_path.rsplit("/", 1)[-1]
        lang = language_for(name, f.extension)
        if not lang:
            continue
        s = stats.setdefault(lang, {"files": 0, "bytes": 0})
        s["files"] += 1
        s["bytes"] += f.size
    ordered = sorted(stats.items(), key=lambda kv: (-kv[1]["files"], -kv[1]["bytes"]))
    langs = [{"name": k, "files": v["files"], "bytes": v["bytes"]} for k, v in ordered]
    code = [(k, v) for k, v in ordered if k in CODE_LANGUAGES and k not in {"HTML", "CSS", "SCSS", "Less", "Shell", "Batch", "PowerShell", "SQL"}]
    if not code:
        code = [(k, v) for k, v in ordered if k in CODE_LANGUAGES]
    primary = max(code, key=lambda kv: kv[1]["bytes"])[0] if code else None
    return langs, primary, stats


def _fingerprint(walk: Walk, git_root: Path | None, extra: str = "") -> str:
    h = hashlib.sha1()
    h.update(("analyzer=" + ANALYZER_VERSION + "|" + extra + "|").encode())
    for f in sorted(walk.files, key=lambda x: x.relative_path):
        h.update(f"{f.relative_path}\0{f.size}\0{f.mtime}\n".encode("utf-8", "replace"))
    h.update(f"count={len(walk.files)} total={walk.total_files} trunc={walk.truncated} size={walk.size_bytes}\n".encode())
    h.update(("git:" + ",".join(sorted(walk.git_dirs)) + "\n").encode("utf-8", "replace"))
    if git_root:
        for name in ("HEAD", "index", "packed-refs", "ORIG_HEAD", "FETCH_HEAD"):
            try:
                st = os.lstat(git_root / ".git" / name)
                h.update(f"git:{name}:{int(st.st_mtime)}:{st.st_size}\n".encode())
            except OSError:
                pass
        try:
            refs = git_root / ".git" / "refs" / "heads"
            for r in sorted(refs.rglob("*"))[:200]:
                st = os.lstat(r)
                h.update(f"ref:{r.name}:{int(st.st_mtime)}\n".encode())
        except OSError:
            pass
    return h.hexdigest()


def compute_status(now: int, last_modified: int | None, git: dict[str, Any] | None, scan_error: str | None,
                   window_days: int, nested_repos: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    latest: int | None = None
    if last_modified:
        evidence.append({"signal": "file_modified", "at": last_modified, "detail": "most recent file modification"})
        latest = last_modified
    if git and git.get("last_commit_at"):
        evidence.append({"signal": "git_commit", "at": git["last_commit_at"], "detail": git.get("last_commit_subject") or "last commit"})
        latest = max(latest or 0, int(git["last_commit_at"]))
    if git and git.get("commits_30d"):
        evidence.append({"signal": "git_commits_30d", "value": git["commits_30d"], "detail": f"{git['commits_30d']} commits in the last 30 days"})
    if git and git.get("ahead"):
        evidence.append({"signal": "git_ahead", "value": git["ahead"], "detail": f"{git['ahead']} commit(s) not pushed to {git.get('upstream') or 'upstream'}"})
    if git and git.get("behind"):
        evidence.append({"signal": "git_behind", "value": git["behind"], "detail": f"{git['behind']} commit(s) behind {git.get('upstream') or 'upstream'}"})
    for nested in nested_repos or []:
        if nested.get("last_commit_at"):
            latest = max(latest or 0, int(nested["last_commit_at"]))
            evidence.append({"signal": "git_commit", "at": nested["last_commit_at"], "detail": f"last commit in nested repository {nested['path']}"})
    status = "Idle"
    if latest is not None and now - latest <= window_days * 86400:
        status = "Active"
        evidence.append({"signal": "window", "detail": f"activity within the last {window_days} days"})
    elif latest is not None:
        evidence.append({"signal": "window", "detail": f"no activity in the last {window_days} days"})
    else:
        evidence.append({"signal": "window", "detail": "no timestamp evidence available"})
    if scan_error:
        status = "Needs attention"
        evidence.append({"signal": "scan_error", "detail": scan_error})
    if git and git.get("dirty"):
        status = "Needs attention"
        parts = []
        if git.get("modified_count"):
            parts.append(f"{git['modified_count']} modified")
        if git.get("staged_count"):
            parts.append(f"{git['staged_count']} staged")
        if git.get("untracked_count"):
            parts.append(f"{git['untracked_count']} untracked")
        evidence.append({"signal": "git_dirty", "detail": "uncommitted changes: " + (", ".join(parts) or "working tree dirty")})
    for nested in nested_repos or []:
        if nested.get("dirty"):
            evidence.append({"signal": "git_nested_dirty", "detail": f"nested repository {nested['path']} has uncommitted changes"})
    return status, evidence


def build_structure(walk: Walk) -> list[dict[str, Any]]:
    """Two-level folder tree with per-folder file counts and sizes (counts cover every file, stored or not)."""
    top: dict[str, dict[str, Any]] = {}

    def node(name: str, path: str) -> dict[str, Any]:
        return {"name": name, "path": path, "files": 0, "size": 0, "children": {}, "git": path in walk.git_dirs}

    for prefix, (files, size) in walk.dir_stats.items():
        parts = prefix.split("/")
        parent = top.setdefault(parts[0], node(parts[0], parts[0]))
        if len(parts) == 1:
            parent["files"], parent["size"] = files, size
        else:
            parent["children"].setdefault(parts[1], node(parts[1], prefix)).update({"files": files, "size": size})
    for drel in walk.dirs:
        parts = drel.split("/")
        parent = top.setdefault(parts[0], node(parts[0], parts[0]))
        if len(parts) == 2:
            parent["children"].setdefault(parts[1], node(parts[1], drel))
    ordered = sorted(top.values(), key=lambda d: (-d["files"], d["name"].lower()))
    out = []
    for d in ordered[:MAX_STRUCTURE_TOP]:
        kids = sorted(d["children"].values(), key=lambda c: (-c["files"], c["name"].lower()))
        more = max(0, len(kids) - MAX_STRUCTURE_CHILDREN)
        d["children"] = [{k: v for k, v in c.items() if k != "children"} for c in kids[:MAX_STRUCTURE_CHILDREN]]
        d["more_children"] = more
        out.append(d)
    if len(ordered) > MAX_STRUCTURE_TOP:
        out.append({"name": f"… {len(ordered) - MAX_STRUCTURE_TOP} more folders", "path": "", "files": sum(d["files"] for d in ordered[MAX_STRUCTURE_TOP:]),
                    "size": 0, "children": [], "git": False, "more_children": 0, "overflow": True})
    return out


def _nested_git(path: Path, git_dirs: set[str], timeout: float) -> list[dict[str, Any]]:
    """Status of repositories nested inside the project (bounded; the root repo is handled separately)."""
    out: list[dict[str, Any]] = []
    ordered = sorted(git_dirs, key=lambda d: (d.count("/"), d.lower()))
    for rel in ordered[:MAX_NESTED_GIT]:
        snap = gitinfo.snapshot(path / Path(*rel.split("/")), timeout=timeout, recent=1).to_dict()
        out.append({"path": rel, "branch": snap.get("branch"), "dirty": snap.get("dirty"), "modified_count": snap.get("modified_count"),
                    "untracked_count": snap.get("untracked_count"), "ahead": snap.get("ahead"), "behind": snap.get("behind"),
                    "last_commit_at": snap.get("last_commit_at"), "last_commit_subject": snap.get("last_commit_subject"),
                    "commits_30d": snap.get("commits_30d"), "error": snap.get("error")})
    for rel in ordered[MAX_NESTED_GIT:]:
        out.append({"path": rel, "skipped": True})
    return out


def _child_rel(parent_rel: str, child_rel: str) -> str:
    """Path of a sub-project relative to its parent project directory."""
    if not parent_rel:
        return child_rel
    prefix = parent_rel + "/"
    return child_rel[len(prefix):] if child_rel.startswith(prefix) else child_rel


def _display_names(discovered: list[Discovered]) -> dict[str, str]:
    """Top-level folders keep their name; promoted sub-folders get parent context when the name is generic or duplicated."""
    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    for d in discovered:
        counts[d.name.lower()] = counts.get(d.name.lower(), 0) + 1
    for d in discovered:
        base = d.name
        generic = classifier.is_generic_name(base)
        duplicate = counts[base.lower()] > 1
        if (generic or duplicate) and "/" in d.relative_path:
            segments = d.relative_path.split("/")
            start = len(segments) - 1
            while start > 0 and classifier.is_generic_name(segments[start - 1]):
                start -= 1
            start = max(0, start - 1)
            names[d.relative_path] = " / ".join(segments[start:])
        else:
            names[d.relative_path] = base
    seen: dict[str, int] = {}
    for d in discovered:
        seen[names[d.relative_path].lower()] = seen.get(names[d.relative_path].lower(), 0) + 1
    for d in discovered:
        if seen[names[d.relative_path].lower()] > 1 and "/" in d.relative_path:
            names[d.relative_path] = d.relative_path.replace("/", " / ")
    return names


# ---------------------------------------------------------------- scan job
class ScanRun:
    def __init__(self, workspace: dict[str, Any], incremental: bool):
        self.id = repo.new_id()
        self.workspace_id = workspace["id"]
        self.root = Path(workspace["root_path"])
        self.started_at = int(time.time())
        self.completed_at: int | None = None
        self.status = "running"
        self.phase = "starting"
        self.current = ""
        self.counts: dict[str, int] = {"discovered": 0, "analyzed": 0, "cached": 0, "files": 0, "errors": 0, "missing": 0, "skipped_links": 0}
        self.summary: dict[str, Any] = {}
        self.errors: list[dict[str, str]] = []
        self.cancel = threading.Event()
        self.incremental = incremental
        self.lock = threading.Lock()

    def error(self, where: str, message: str) -> None:
        with self.lock:
            if len(self.errors) < 500:
                self.errors.append({"where": where, "message": message})
            self.counts["errors"] += 1

    def to_dict(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self.id, "workspace_id": self.workspace_id, "started_at": self.started_at, "completed_at": self.completed_at,
                "status": self.status, "phase": self.phase, "current": self.current, "counts": dict(self.counts), "summary": dict(self.summary),
                "errors": list(self.errors[:100]), "error_count": len(self.errors), "incremental": self.incremental,
                "elapsed": (self.completed_at or int(time.time())) - self.started_at,
            }


class ScanManager:
    def __init__(self, db: Database, settings: Settings, log: Callable[[str], None] | None = None):
        self.db = db
        self.settings = settings
        self.runs: dict[str, ScanRun] = {}
        self._lock = threading.Lock()
        self.log = log or (lambda msg: None)
        self.listeners: list[Callable[[str], None]] = []

    # -- public API -------------------------------------------------------
    def active_run(self, workspace_id: str) -> ScanRun | None:
        with self._lock:
            for run in self.runs.values():
                if run.workspace_id == workspace_id and run.status == "running":
                    return run
        return None

    def start(self, workspace: dict[str, Any], incremental: bool = True) -> ScanRun:
        existing = self.active_run(workspace["id"])
        if existing:
            return existing
        run = ScanRun(workspace, incremental)
        with self._lock:
            self.runs[run.id] = run
            # keep memory bounded
            finished = [r for r in self.runs.values() if r.status != "running"]
            for old in sorted(finished, key=lambda r: r.started_at)[:-20]:
                self.runs.pop(old.id, None)
        repo.insert_scan_run(self.db, {**run.to_dict(), "errors": []})
        thread = threading.Thread(target=self._execute, args=(run,), name=f"scan-{run.id}", daemon=True)
        thread.start()
        return run

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self.runs.get(run_id)
        if not run or run.status != "running":
            return False
        run.cancel.set()
        return True

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self.runs.get(run_id)
        if run:
            return run.to_dict()
        return repo.get_scan_run(self.db, run_id)

    def rescan_project(self, project: dict[str, Any]) -> dict[str, Any] | None:
        """Synchronously re-analyse a single project (used by the details panel)."""
        workspace = repo.get_workspace(self.db, project["workspace_id"])
        if not workspace:
            return None
        settings = self.settings.section("scan")
        ignore = IgnoreMatcher.from_list(settings["ignore"])
        root = Path(workspace["root_path"])
        path = root / project["relative_path"] if project["relative_path"] else root
        if not path.is_dir() or not is_within(path, root):
            return None
        cancel = threading.Event()
        exclude = {_child_rel(project["relative_path"], r["relative_path"])
                   for r in self.db.all("SELECT relative_path FROM projects WHERE parent_id = ? AND removed_at IS NULL", (project["id"],))}
        d = Discovered(path, project["relative_path"], project["relative_path"].count("/") + 1,
                       project["detected_type"] if project["detected_type"] in {"folder", "promoted"} else "folder", project["detection_evidence"], None)
        child_cats: list[list[str]] = []
        child_names: list[str] = []
        for c in self.db.all("SELECT id, name FROM projects WHERE parent_id = ? AND removed_at IS NULL", (project["id"],)):
            p = repo.get_project(self.db, c["id"], with_details=False)
            if p:
                child_cats.append(p["categories"])
                child_names.append(p["name"])
        self._analyze_one(d, root, workspace["id"], settings, ignore, exclude, cancel, None, incremental=False,
                          display_name=project["display_name"], parent_id=project["parent_id"], child_cats=child_cats, child_names=child_names)
        self._compute_relations()
        return repo.get_project(self.db, project["id"])

    # -- internals ----------------------------------------------------------
    def _execute(self, run: ScanRun) -> None:
        try:
            self._run(run)
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error("scan", f"{type(exc).__name__}: {exc}")
            self.log("scan failed: " + traceback.format_exc())
        finally:
            run.completed_at = int(time.time())
            if run.status == "running":
                run.status = "cancelled" if run.cancel.is_set() else "completed"
            run.phase = "done"
            repo.update_scan_run(self.db, run.to_dict())
            if run.status == "completed":
                self.db.execute("UPDATE workspaces SET last_scan_at = ? WHERE id = ?", (run.completed_at, run.workspace_id))
            for listener in list(self.listeners):
                try:
                    listener(run.id)
                except Exception:  # noqa: BLE001
                    pass

    def _run(self, run: ScanRun) -> None:
        settings = self.settings.section("scan")
        ignore = IgnoreMatcher.from_list(settings["ignore"])
        root = run.root
        if not root.is_dir():
            run.status = "failed"
            run.error(".", "workspace root does not exist or is not a directory")
            return
        workspace = repo.get_workspace(self.db, run.workspace_id) or {}
        promoted = set((workspace.get("settings") or {}).get("promoted", []))
        run.phase = "discover"
        discovered, summary = discover_top_level(root, ignore, promoted, run.cancel, on_error=lambda where, msg: run.error(where, msg))
        summary["mode"] = settings.get("mode", "top-level")
        max_projects = int(settings["max_projects"])
        if len(discovered) > max_projects:
            run.error(".", f"project limit reached ({max_projects}); raise scan.max_projects to see more")
            keep = {d.relative_path for d in discovered[:max_projects]}
            discovered = [d for d in discovered if d.relative_path in keep or (d.parent_rel in keep and d.detected_type == "promoted")][:max_projects]
        with run.lock:
            run.counts["discovered"] = len(discovered)
            run.summary = summary
        repo.update_scan_run(self.db, run.to_dict())
        if run.cancel.is_set():
            return

        names = _display_names(discovered)
        now = int(time.time())
        run.phase = "analyze"
        seen_ids: set[str] = set()
        # Children first so parents can use their categories (post-order by depth desc).
        order = sorted(discovered, key=lambda d: (-d.depth, d.relative_path.lower()))
        analyzed_categories: dict[str, list[str]] = {}
        candidates_total = 0
        for index, d in enumerate(order):
            if run.cancel.is_set():
                break
            pid = repo.project_id_for(run.workspace_id, d.relative_path)
            seen_ids.add(pid)
            run.current = d.relative_path or "."
            exclude = {_child_rel(d.relative_path, c.relative_path) for c in d.children}
            parent_id = repo.project_id_for(run.workspace_id, d.parent_rel) if d.parent_rel is not None else None
            child_cats = [analyzed_categories.get(repo.project_id_for(run.workspace_id, c.relative_path), []) for c in d.children]
            child_names = [c.name for c in d.children]
            try:
                cats, n_candidates = self._analyze_one(d, root, run.workspace_id, settings, ignore, exclude, run.cancel, run, run.incremental,
                                                       names[d.relative_path], parent_id, child_cats, child_names)
                analyzed_categories[pid] = cats
                candidates_total += n_candidates
            except Exception as exc:  # noqa: BLE001
                run.error(d.relative_path or ".", f"{type(exc).__name__}: {exc}")
                self.log(f"analyze failed for {d.relative_path}: {traceback.format_exc()}")
            if index % 10 == 0:
                repo.update_scan_run(self.db, run.to_dict())
        with run.lock:
            run.summary["candidates"] = candidates_total

        if not run.cancel.is_set():
            run.phase = "reconcile"
            missing = repo.mark_missing(self.db, run.workspace_id, seen_ids, now)
            run.counts["missing"] = len(missing)
            run.phase = "relations"
            self._compute_relations()

    def _analyze_one(self, d: Discovered, root: Path, workspace_id: str, settings: dict[str, Any], ignore: IgnoreMatcher,
                     exclude: set[str], cancel: threading.Event, run: ScanRun | None, incremental: bool, display_name: str,
                     parent_id: str | None, child_cats: list[list[str]], child_names: list[str]) -> tuple[list[str], int]:
        """Analyse one project folder. Returns (effective categories, number of nested candidates found)."""
        pid = repo.project_id_for(workspace_id, d.relative_path)
        now = int(time.time())
        mode = settings.get("mode", "top-level")
        walk = walk_project(d.path, root, ignore, exclude, int(settings["max_files_per_project"]), int(settings["max_file_walk_depth"]), cancel)
        for err in walk.errors[:20]:
            if run:
                run.error(f"{d.relative_path or '.'}/{err}", "unreadable directory")
        scan_error = None
        if walk.errors:
            scan_error = f"{len(walk.errors)} unreadable director{'y' if len(walk.errors) == 1 else 'ies'} (e.g. {walk.errors[0]})"
        if walk.hard_truncated:
            scan_error = (scan_error + "; " if scan_error else "") + f"folder has more than {HARD_MAX_ENTRIES} entries; counts are partial"

        # Cheap repo detection (no subprocess): nearest .git between the project and the workspace root.
        git_root = gitinfo.nearest_git_dir(d.path, stop=root) if gitinfo.git_executable() else None
        extra = f"mode={mode}|depth={settings['max_depth']}|loose={settings.get('detect_loose_folders', True)}|children={','.join(sorted(exclude))}"
        fingerprint = _fingerprint(walk, git_root, extra)
        old_fp, _old_analyzed = repo.get_fingerprint(self.db, pid)
        existing = repo.get_project(self.db, pid, with_details=False) if old_fp else None

        if incremental and existing and old_fp == fingerprint and existing.get("last_analyzed_at") and not existing.get("scan_error"):
            git = repo.get_git(self.db, pid)
            nested = [r for r in repo.get_git_repos(self.db, pid) if not r.get("skipped")]
            status, evidence = compute_status(now, existing["last_modified"], git, scan_error, int(settings["activity_window_days"]), nested)
            with self.db.transaction():
                repo.touch_project_seen(self.db, pid, now, status, evidence, display_name, parent_id, len(child_names))
            if run:
                with run.lock:
                    run.counts["cached"] += 1
                    run.counts["files"] += existing.get("file_count_total") or existing["file_count"]
            return existing["categories"], repo.count_sub_projects(self.db, pid)

        manifests = _read_manifests(d.path, walk, int(settings["max_manifest_bytes"]))
        title, description, excerpt = _read_readme(d.path, walk, int(settings["max_readme_bytes"]))
        languages, primary, lang_stats = _languages(walk.files)
        parts = components.detect_components(walk.files, walk.dirs, walk.git_dirs, manifests)
        root_names = {n for n in walk.top_level}
        root_has_marker = any(n in STRONG_MARKERS or split_ext(n) in EXT_MARKERS for n in root_names) or _has_git_dir(d.path)
        candidates = []
        if mode == "nested":
            candidates = components.find_candidates(walk.files, walk.dirs, walk.git_dirs, int(settings["max_depth"]),
                                                    bool(settings.get("detect_loose_folders", True)), root_has_marker)
        kinds = {f.kind: 0 for f in walk.files}
        for f in walk.files:
            kinds[f.kind] += 1
        source_files = kinds.get("source", 0) + kinds.get("test", 0) + kinds.get("notebook", 0)
        structure = components.structure_kind(root_names, _has_git_dir(d.path), parts, len(candidates), source_files, kinds.get("doc", 0),
                                              len(walk.files), any(m.workspaces for m in manifests))
        facts = ProjectFacts(
            name=d.name, relative_path=d.relative_path, files=walk.files, dir_names=walk.dir_names, top_level=walk.top_level,
            languages=lang_stats, manifests=manifests, readme_title=title, readme_excerpt=excerpt, has_git=git_root is not None,
            detected_type=d.detected_type, components=[(c.kind, c.name) for c in parts], child_categories=child_cats, child_names=child_names,
        )
        categories, techs = classifier.classify(facts)
        git = gitinfo.snapshot(d.path, timeout=float(settings["git_timeout_seconds"])).to_dict() if git_root is not None else None
        nested_repos = _nested_git(d.path, walk.git_dirs, float(settings["git_timeout_seconds"])) if gitinfo.git_executable() else \
            [{"path": rel, "skipped": True} for rel in sorted(walk.git_dirs)]
        status, evidence = compute_status(now, walk.last_modified, git, scan_error, int(settings["activity_window_days"]),
                                          [r for r in nested_repos if not r.get("skipped")])
        if description:
            desc, desc_source = description, "readme"
        else:
            desc, desc_source = classifier.heuristic_description(facts, categories, techs, primary, structure, walk.total_files), "heuristic"
        if existing and existing.get("description_source") == "manual":
            desc, desc_source = existing["description"], "manual"
        evidence_detect = list(d.evidence)
        if structure != "folder":
            evidence_detect.append({"rule": "structure", "detail": classifier.STRUCTURE_WORDS.get(structure, structure)})
        if walk.git_dirs:
            evidence_detect.append({"rule": "nested-git", "detail": f"{len(walk.git_dirs)} nested repositor{'y' if len(walk.git_dirs) == 1 else 'ies'} kept inside this project"})

        project = {
            "id": pid, "workspace_id": workspace_id, "relative_path": d.relative_path, "name": d.name, "display_name": display_name,
            "detected_type": d.detected_type, "detection_evidence": evidence_detect, "parent_id": parent_id,
            "discovered_at": existing["discovered_at"] if existing else now, "last_seen_at": now, "last_analyzed_at": now,
            "status": status, "status_evidence": evidence, "scan_error": scan_error, "file_count": len(walk.files),
            "file_count_total": walk.total_files, "files_truncated": walk.truncated, "dir_count": walk.dir_count, "size_bytes": walk.size_bytes,
            "last_modified": walk.last_modified, "last_modified_path": walk.last_modified_path, "primary_language": primary,
            "languages": languages, "manifests": [m.to_dict() for m in manifests], "description": desc, "description_source": desc_source,
            "readme_excerpt": excerpt, "fingerprint": fingerprint, "sub_project_count": len(child_names),
            "components": [c.to_dict() for c in parts], "structure": {"kind": structure, "root_files": len([f for f in walk.files if "/" not in f.relative_path]),
                                                                      "tree": build_structure(walk), "truncated": walk.truncated},
            "git_repos": nested_repos, "important_files": components.important_files(walk.files, manifests),
        }
        with self.db.transaction():
            repo.upsert_project(self.db, project)
            repo.replace_files(self.db, pid, [(f.relative_path, f.extension, f.size, f.mtime, f.kind, 1 if f.sensitive else 0) for f in walk.files])
            repo.replace_technologies(self.db, pid, [t.to_dict() for t in techs])
            repo.replace_rule_categories(self.db, pid, [c.to_dict() for c in categories])
            if git is not None:
                repo.save_git(self.db, pid, git)
            else:
                self.db.execute("DELETE FROM git_snapshots WHERE project_id = ?", (pid,))
            repo.replace_sub_projects(self.db, pid, workspace_id, [
                {"id": repo.project_id_for(workspace_id, f"{d.relative_path}/{c.relative_path}"), "relative_path": f"{d.relative_path}/{c.relative_path}",
                 "name": c.name, "detected_type": c.detected_type, "detection_evidence": c.evidence, "file_count": c.file_count,
                 "primary_language": c.primary_language, "manifests": c.manifests, "has_git": c.has_git}
                for c in candidates], now)
        if run:
            with run.lock:
                run.counts["analyzed"] += 1
                run.counts["files"] += walk.total_files
        final = repo.get_project(self.db, pid, with_details=False)
        return (final["categories"] if final else [c.name for c in categories]), len(candidates)

    def _compute_relations(self) -> None:
        from .relations import compute_relations
        computed = compute_relations(self.db)
        with self.db.transaction():
            repo.replace_relations(self.db, computed)
