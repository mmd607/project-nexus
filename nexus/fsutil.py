"""Bounded, read-only filesystem helpers.

Rules enforced here (see docs/SECURITY.md):
* symlinks, Windows junctions and other reparse points are never followed;
* every directory we descend into must still resolve *inside* the workspace root;
* permission errors are reported, never raised through the scanner.
"""
from __future__ import annotations

import fnmatch
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

_IS_WINDOWS = sys.platform.startswith("win")
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_reparse_or_link(entry: os.DirEntry | Path) -> bool:
    """True for symlinks (all platforms) and junctions / reparse points (Windows)."""
    try:
        if isinstance(entry, os.DirEntry):
            if entry.is_symlink():
                return True
            st = entry.stat(follow_symlinks=False)
        else:
            if entry.is_symlink():
                return True
            st = os.lstat(entry)
    except OSError:
        return True  # unreadable: treat as unsafe
    if _IS_WINDOWS:
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & _REPARSE:
            return True
    return False


def norm_case(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def is_within(child: str | Path, root: str | Path) -> bool:
    """Whether *child* (resolved) lies inside *root* (resolved)."""
    try:
        c = norm_case(os.path.realpath(str(child)))
        r = norm_case(os.path.realpath(str(root)))
    except (OSError, ValueError):
        return False
    if c == r:
        return True
    return c.startswith(r.rstrip(os.sep) + os.sep)


@dataclass(frozen=True)
class IgnoreMatcher:
    exact: frozenset[str]
    patterns: tuple[str, ...]

    @classmethod
    def from_list(cls, items: list[str]) -> "IgnoreMatcher":
        exact, patterns = set(), []
        for item in items:
            item = item.strip()
            if not item:
                continue
            if any(ch in item for ch in "*?["):
                patterns.append(item.lower())
            else:
                exact.add(item.lower())
        return cls(frozenset(exact), tuple(patterns))

    def matches(self, name: str) -> bool:
        lowered = name.lower()
        if lowered in self.exact:
            return True
        return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in self.patterns)


@dataclass
class ListResult:
    dirs: list[os.DirEntry]
    files: list[os.DirEntry]
    skipped_links: int = 0
    error: str | None = None


def list_dir(path: str | Path, ignore: IgnoreMatcher, root: str | Path | None = None) -> ListResult:
    """List a directory without following links and without raising."""
    dirs: list[os.DirEntry] = []
    files: list[os.DirEntry] = []
    skipped = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if ignore.matches(name):
                    continue
                if is_reparse_or_link(entry):
                    skipped += 1
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if root is not None and not is_within(entry.path, root):
                            skipped += 1
                            continue
                        dirs.append(entry)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(entry)
                except OSError:
                    continue
    except PermissionError:
        return ListResult(dirs, files, skipped, "permission denied")
    except FileNotFoundError:
        return ListResult(dirs, files, skipped, "not found")
    except OSError as exc:
        return ListResult(dirs, files, skipped, exc.strerror or type(exc).__name__)
    dirs.sort(key=lambda e: e.name.lower())
    files.sort(key=lambda e: e.name.lower())
    return ListResult(dirs, files, skipped, None)


def read_text_capped(path: str | Path, max_bytes: int) -> str | None:
    """Read at most *max_bytes* of a regular, non-link file as UTF-8 (lossy)."""
    try:
        p = Path(path)
        if p.is_symlink() or not p.is_file():
            return None
        with open(p, "rb") as fh:
            data = fh.read(max_bytes)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def display_path(path: str, anonymize: bool) -> str:
    if not anonymize:
        return path
    parts = Path(path).parts
    if len(parts) <= 2:
        return "…"
    return str(Path("…", *parts[-2:]))
