"""Settings validation/recovery and database migrations."""
from __future__ import annotations

import json

import pytest

from nexus.db import Database
from nexus.settings import DEFAULTS, Settings, SettingsError, validate


def test_defaults_are_valid_and_safe():
    s = validate(DEFAULTS)
    assert s["ai"]["enabled"] is False
    assert s["ai"]["base_url"].startswith("http://127.0.0.1")
    assert ".git" in s["scan"]["ignore"] and "node_modules" in s["scan"]["ignore"]


def test_validate_rejects_bad_values():
    for patch in ({"scan": {"max_depth": -1}}, {"scan": {"max_projects": 0}}, {"scan": {"mode": "deep"}}, {"ai": {"provider": "cloud"}}, {"ai": {"timeout_seconds": 1}},
                  {"ui": {"reduced_motion": "maybe"}}, {"ui": {"language": "de"}}, {"scan": {"ignore": ["", "x"]}}, {"ai": {"default_fields": ["source_code"]}},
                  {"ai": {"base_url": "ftp://127.0.0.1"}}):
        merged = json.loads(json.dumps(DEFAULTS))
        for k, v in patch.items():
            merged[k].update(v)
        with pytest.raises(SettingsError):
            validate(merged)


def test_settings_persist_and_recover(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(path)
    s.update({"ui": {"theme": "light"}, "scan": {"max_depth": 6}})
    reloaded = Settings(path)
    assert reloaded.get()["ui"]["theme"] == "light" and reloaded.get()["scan"]["max_depth"] == 6
    path.write_text("{ this is not json", encoding="utf-8")
    recovered = Settings(path)
    assert recovered.get()["ui"]["theme"] == "dark"
    assert (tmp_path / "settings.json.corrupt").exists()
    # unknown keys in the file are rejected → defaults
    path.write_text(json.dumps({"scan": {"evil": True}}), encoding="utf-8")
    assert Settings(path).get()["scan"]["max_depth"] == DEFAULTS["scan"]["max_depth"]


def test_v1_database_drops_nested_projects_and_requests_a_rescan(tmp_path):
    """Upgrading from the marker-based model: nested rows go, top-level rows stay (with overrides), rescan is requested."""
    import sqlite3

    from nexus.db import MIGRATIONS
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0][1] + "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);"
                       "INSERT INTO schema_migrations VALUES (1, 0);")
    conn.execute("INSERT INTO workspaces(id, display_name, root_path, created_at) VALUES ('w', 'w', 'X:/w', 0)")
    for pid, rel, parent in [("aaaa", "shop", None), ("bbbb", "shop/backend", "aaaa"), ("cccc", "shop/backend/api", "bbbb"), ("dddd", "tools", None)]:
        conn.execute("INSERT INTO projects(id, workspace_id, relative_path, name, display_name, detected_type, parent_id, discovered_at, last_seen_at, status, fingerprint, last_analyzed_at) "
                     "VALUES (?, 'w', ?, ?, ?, 'manifest', ?, 0, 0, 'Idle', 'fp', 1)", (pid, rel, rel.split("/")[-1], rel, parent))
    conn.execute("INSERT INTO category_overrides(project_id, categories_json, updated_at) VALUES ('aaaa', '[\"Security\"]', 0)")
    conn.commit()
    conn.close()
    db = Database(path)
    assert db.schema_version >= 2 and db.needs_rescan is True
    rows = {r["relative_path"]: r for r in db.all("SELECT * FROM projects")}
    assert set(rows) == {"shop", "tools"}
    assert rows["shop"]["fingerprint"] is None and rows["shop"]["last_analyzed_at"] is None and rows["shop"]["parent_id"] is None
    assert db.scalar("SELECT categories_json FROM category_overrides WHERE project_id = 'aaaa'") == '["Security"]'
    db.close()
    fresh = Database(tmp_path / "fresh.db")
    assert fresh.needs_rescan is False
    fresh.close()


def test_database_migrates_and_is_idempotent(tmp_path):
    db = Database(tmp_path / "x.db")
    assert db.schema_version >= 1
    tables = {r[0] for r in db.all("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"workspaces", "projects", "files", "technologies", "categories", "category_overrides", "git_snapshots", "scan_runs", "relations", "ai_suggestions", "sub_projects"} <= tables
    db.close()
    again = Database(tmp_path / "x.db")
    assert again.schema_version >= 1
    assert again.scalar("PRAGMA journal_mode").lower() == "wal"
    again.close()
