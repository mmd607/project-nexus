"""SQLite storage with WAL and forward-only migrations.

A single connection guarded by a re-entrant lock is used on purpose: the app
has one writer (the scan worker) and a handful of readers (HTTP threads). WAL
mode keeps readers from blocking on writers, and the lock keeps sqlite3's
connection object safe across threads.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE workspaces(
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            root_path TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            last_scan_at INTEGER,
            settings_json TEXT NOT NULL DEFAULT '{}',
            removed_at INTEGER
        );
        CREATE TABLE projects(
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            detected_type TEXT NOT NULL,
            detection_evidence_json TEXT NOT NULL DEFAULT '[]',
            parent_id TEXT,
            discovered_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            last_analyzed_at INTEGER,
            status TEXT NOT NULL,
            status_evidence_json TEXT NOT NULL DEFAULT '[]',
            scan_error TEXT,
            file_count INTEGER NOT NULL DEFAULT 0,
            files_truncated INTEGER NOT NULL DEFAULT 0,
            dir_count INTEGER NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            last_modified INTEGER,
            last_modified_path TEXT,
            primary_language TEXT,
            languages_json TEXT NOT NULL DEFAULT '[]',
            manifests_json TEXT NOT NULL DEFAULT '[]',
            description TEXT,
            description_source TEXT,
            readme_excerpt TEXT,
            fingerprint TEXT,
            sub_project_count INTEGER NOT NULL DEFAULT 0,
            removed_at INTEGER,
            UNIQUE(workspace_id, relative_path)
        );
        CREATE INDEX projects_workspace ON projects(workspace_id, removed_at);
        CREATE TABLE files(
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            extension TEXT,
            size INTEGER NOT NULL,
            mtime INTEGER NOT NULL,
            kind TEXT NOT NULL,
            sensitive INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(project_id, relative_path)
        );
        CREATE INDEX files_project_mtime ON files(project_id, mtime DESC);
        CREATE TABLE technologies(
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY(project_id, name)
        );
        CREATE TABLE categories(
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY(project_id, name, source)
        );
        CREATE TABLE category_overrides(
            project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            categories_json TEXT NOT NULL,
            note TEXT,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE git_snapshots(
            project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
            repo_root TEXT,
            is_repo_root INTEGER NOT NULL DEFAULT 0,
            branch TEXT,
            detached INTEGER NOT NULL DEFAULT 0,
            dirty INTEGER,
            modified_count INTEGER,
            untracked_count INTEGER,
            staged_count INTEGER,
            ahead INTEGER,
            behind INTEGER,
            upstream TEXT,
            last_commit_at INTEGER,
            last_commit_subject TEXT,
            last_commit_author TEXT,
            commits_30d INTEGER,
            recent_commits_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            captured_at INTEGER NOT NULL
        );
        CREATE TABLE scan_runs(
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            completed_at INTEGER,
            status TEXT NOT NULL,
            phase TEXT,
            counts_json TEXT NOT NULL DEFAULT '{}',
            errors_json TEXT NOT NULL DEFAULT '[]',
            incremental INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE relations(
            source_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1,
            evidence_json TEXT NOT NULL,
            PRIMARY KEY(source_id, target_id, type)
        );
        CREATE TABLE ai_suggestions(
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            sent_fields_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            resolved_at INTEGER
        );
        CREATE INDEX ai_suggestions_project ON ai_suggestions(project_id, created_at DESC);
        """,
    ),
    (
        2,
        # Project model v2: one project per top-level folder. Nested folders (backend/, apps/web, …) are
        # components or sub-projects of their parent, never nodes of their own unless the user promotes them.
        # Old nested rows are dropped and every remaining row is marked stale so the next scan re-analyses it
        # (category overrides and manual descriptions of top-level projects survive: ids are path-derived).
        """
        ALTER TABLE projects ADD COLUMN components_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE projects ADD COLUMN structure_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE projects ADD COLUMN git_repos_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE projects ADD COLUMN important_files_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE projects ADD COLUMN file_count_total INTEGER;
        ALTER TABLE scan_runs ADD COLUMN summary_json TEXT NOT NULL DEFAULT '{}';
        CREATE TABLE sub_projects(
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            parent_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            name TEXT NOT NULL,
            detected_type TEXT NOT NULL,
            detection_evidence_json TEXT NOT NULL DEFAULT '[]',
            file_count INTEGER NOT NULL DEFAULT 0,
            primary_language TEXT,
            manifests_json TEXT NOT NULL DEFAULT '[]',
            has_git INTEGER NOT NULL DEFAULT 0,
            last_seen_at INTEGER NOT NULL,
            UNIQUE(workspace_id, relative_path)
        );
        CREATE INDEX sub_projects_parent ON sub_projects(parent_id);
        DELETE FROM projects WHERE instr(relative_path, '/') > 0;
        UPDATE projects SET fingerprint = NULL, last_analyzed_at = NULL, parent_id = NULL, sub_project_count = 0
        """,
    ),
]

# Versions whose migration invalidates existing scan results; the app re-scans after applying one of them.
RESCAN_AFTER = {2}


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()
        is_memory = str(path) == ":memory:"
        if not is_memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        if not is_memory:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.applied_now: list[int] = []
        self.migrate()

    # -- lifecycle -----------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL)"
            )
            applied = {row[0] for row in self._conn.execute("SELECT version FROM schema_migrations")}
            for version, script in MIGRATIONS:
                if version in applied:
                    continue
                self._conn.execute("BEGIN")
                try:
                    # executescript() would implicitly COMMIT; run statements one by one instead
                    for statement in script.split(";"):
                        if statement.strip():
                            self._conn.execute(statement)
                    self._conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (version, int(time.time()))
                    )
                    self._conn.execute("COMMIT")
                    if applied:  # an upgrade of an existing database, not a fresh one
                        self.applied_now.append(version)
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise

    @property
    def needs_rescan(self) -> bool:
        """True when a migration applied at start-up invalidated the stored scan results."""
        return bool(set(self.applied_now) & RESCAN_AFTER)

    @property
    def schema_version(self) -> int:
        row = self.one("SELECT MAX(version) AS v FROM schema_migrations")
        return int(row["v"] or 0)

    # -- primitives ----------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    def one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.one(sql, params)
        return None if row is None else row[0]
