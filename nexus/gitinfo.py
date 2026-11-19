"""Read-only Git inspection with fixed arguments, timeouts and a protected environment.

Only ``git`` itself is executed, never anything from the scanned project
(hooks are disabled via ``core.hooksPath``, credential prompts are off).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .model import GitSnapshot

_GIT: str | None = None
_CHECKED = False


def git_executable() -> str | None:
    global _GIT, _CHECKED
    if not _CHECKED:
        _GIT = shutil.which("git")
        _CHECKED = True
    return _GIT


def _env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": os.environ.get("HOME", os.environ.get("USERPROFILE", "")),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_PARAMETERS": "'core.hooksPath=/dev/null' 'core.fsmonitor=false'",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    }
    if os.environ.get("TEMP"):
        env["TEMP"] = env["TMP"] = os.environ["TEMP"]
    return env


def _run(path: Path, args: list[str], timeout: float) -> tuple[int, str]:
    exe = git_executable()
    if not exe:
        return 127, ""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [exe, "-C", str(path), "--no-optional-locks", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            env=_env(), stdin=subprocess.DEVNULL, creationflags=creation, check=False,
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 126, ""


def nearest_git_dir(path: Path, stop: Path | None = None) -> Path | None:
    """Walk up from *path* (inclusive) looking for a .git entry, without running git.

    Stops after *stop* (inclusive). Cheap: one lstat per level, no subprocess.
    """
    current = path
    while True:
        try:
            st = os.lstat(current / ".git")
            import stat as _stat
            if _stat.S_ISDIR(st.st_mode) or _stat.S_ISREG(st.st_mode):
                return current
        except OSError:
            pass
        if stop is not None and current == stop:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def find_repo_root(path: Path, timeout: float = 5) -> Path | None:
    """Nearest enclosing Git work tree, or None."""
    code, out = _run(path, ["rev-parse", "--show-toplevel"], timeout)
    if code != 0 or not out.strip():
        return None
    try:
        return Path(out.strip()).resolve()
    except OSError:
        return None


def snapshot(path: Path, timeout: float = 8, recent: int = 6) -> GitSnapshot:
    snap = GitSnapshot()
    if not git_executable():
        snap.error = "git executable not found"
        return snap
    root = find_repo_root(path, timeout)
    if root is None:
        snap.error = "not a git repository"
        return snap
    snap.repo_root = str(root)
    try:
        snap.is_repo_root = root.resolve() == path.resolve()
    except OSError:
        snap.is_repo_root = False

    # Branch, upstream, ahead/behind and working-tree status in a single call.
    code, out = _run(path, ["status", "--porcelain=v2", "--branch", "--untracked-files=normal", "--", "."], timeout)
    if code == 124:
        snap.error = "git status timed out"
    elif code != 0:
        snap.error = "git status failed"
    else:
        modified = untracked = staged = 0
        for line in out.splitlines():
            if line.startswith("# branch.head "):
                head = line[len("# branch.head "):].strip()
                if head == "(detached)":
                    snap.detached = True
                    snap.branch = None
                else:
                    snap.branch = head
            elif line.startswith("# branch.upstream "):
                snap.upstream = line[len("# branch.upstream "):].strip()
            elif line.startswith("# branch.ab "):
                parts = line.split()
                try:
                    snap.ahead = int(parts[2].lstrip("+"))
                    snap.behind = int(parts[3].lstrip("-"))
                except (IndexError, ValueError):
                    pass
            elif line.startswith(("1 ", "2 ")):
                xy = line.split(" ", 2)[1] if len(line) > 2 else ".."
                if len(xy) >= 2:
                    if xy[0] != ".":
                        staged += 1
                    if xy[1] != ".":
                        modified += 1
            elif line.startswith("u "):
                modified += 1
            elif line.startswith("? "):
                untracked += 1
        snap.modified_count, snap.untracked_count, snap.staged_count = modified, untracked, staged
        snap.dirty = bool(modified or untracked or staged)
        if snap.detached and snap.branch is None:
            code2, sha = _run(path, ["rev-parse", "--short", "HEAD"], timeout)
            if code2 == 0 and sha.strip():
                snap.branch = f"detached @ {sha.strip()}"

    code, out = _run(path, ["log", f"-{recent}", "--format=%ct%x1f%an%x1f%s", "--", "."], timeout)
    if code == 0 and out.strip():
        commits = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 3:
                continue
            try:
                ts = int(parts[0])
            except ValueError:
                continue
            commits.append({"at": ts, "author": parts[1][:80], "subject": parts[2][:160]})
        if commits:
            snap.recent_commits = commits
            snap.last_commit_at = commits[0]["at"]
            snap.last_commit_author = commits[0]["author"]
            snap.last_commit_subject = commits[0]["subject"]
    elif code == 124 and not snap.error:
        snap.error = "git log timed out"

    if snap.last_commit_at is not None:
        since = int(time.time()) - 30 * 86400
        code, out = _run(path, ["rev-list", "--count", f"--since={since}", "HEAD", "--", "."], timeout)
        if code == 0 and out.strip().isdigit():
            snap.commits_30d = int(out.strip())
    return snap
