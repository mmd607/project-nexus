"""Domain queries on top of :class:`nexus.db.Database`.

All JSON columns are decoded here so the API layer only deals with dicts.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from .db import Database, dumps, loads
from .model import CATEGORIES


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def project_id_for(workspace_id: str, relative_path: str) -> str:
    return hashlib.sha1(f"{workspace_id}:{relative_path}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- workspaces
def add_workspace(db: Database, root_path: str, display_name: str | None = None) -> dict[str, Any]:
    existing = db.one("SELECT * FROM workspaces WHERE root_path = ?", (root_path,))
    now = int(time.time())
    if existing:
        if existing["removed_at"]:
            db.execute("UPDATE workspaces SET removed_at = NULL, display_name = ? WHERE id = ?",
                       (display_name or existing["display_name"], existing["id"]))
        return get_workspace(db, existing["id"])  # type: ignore[return-value]
    wid = new_id()
    db.execute(
        "INSERT INTO workspaces(id, display_name, root_path, created_at, settings_json) VALUES (?,?,?,?,?)",
        (wid, display_name or root_path.rstrip("/\\").split("\\")[-1].split("/")[-1] or root_path, root_path, now, "{}"),
    )
    return get_workspace(db, wid)  # type: ignore[return-value]


def workspace_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "display_name": row["display_name"], "root_path": row["root_path"], "created_at": row["created_at"],
        "last_scan_at": row["last_scan_at"], "settings": loads(row["settings_json"], {}), "removed_at": row["removed_at"],
    }


def get_workspace(db: Database, wid: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM workspaces WHERE id = ?", (wid,))
    return workspace_row(row) if row else None


def list_workspaces(db: Database, include_removed: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM workspaces" + ("" if include_removed else " WHERE removed_at IS NULL") + " ORDER BY created_at"
    out = []
    for row in db.all(sql):
        ws = workspace_row(row)
        ws["project_count"] = db.scalar("SELECT COUNT(*) FROM projects WHERE workspace_id = ? AND removed_at IS NULL", (ws["id"],))
        ws["missing_count"] = db.scalar("SELECT COUNT(*) FROM projects WHERE workspace_id = ? AND removed_at IS NOT NULL", (ws["id"],))
        last = db.one("SELECT * FROM scan_runs WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 1", (ws["id"],))
        ws["last_run"] = scan_run_row(last) if last else None
        out.append(ws)
    return out


def remove_workspace(db: Database, wid: str, purge: bool) -> bool:
    if purge:
        cur = db.execute("DELETE FROM workspaces WHERE id = ?", (wid,))
        return cur.rowcount > 0
    cur = db.execute("UPDATE workspaces SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (int(time.time()), wid))
    return cur.rowcount > 0


def rename_workspace(db: Database, wid: str, display_name: str) -> None:
    db.execute("UPDATE workspaces SET display_name = ? WHERE id = ?", (display_name[:120], wid))


def set_workspace_settings(db: Database, wid: str, settings: dict[str, Any]) -> None:
    db.execute("UPDATE workspaces SET settings_json = ? WHERE id = ?", (dumps(settings), wid))


def set_promoted(db: Database, wid: str, relative_path: str, promoted: bool) -> list[str]:
    """Mark/unmark a nested folder as an independent project. Returns the new promoted list.

    Un-promoting also drops the project row (and everything hanging off it) right away so the
    node disappears without waiting for a scan; the parent re-absorbs the folder on the next scan.
    """
    ws = get_workspace(db, wid)
    if not ws:
        return []
    current = list((ws.get("settings") or {}).get("promoted", []))
    rel = relative_path.strip("/").replace("\\", "/")
    if promoted and rel not in current:
        current.append(rel)
    if not promoted:
        current = [c for c in current if c != rel and not c.startswith(rel + "/")]
        for row in db.all("SELECT id, relative_path FROM projects WHERE workspace_id = ? AND (relative_path = ? OR relative_path LIKE ? ESCAPE '\\')",
                          (wid, rel, rel.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%")):
            db.execute("DELETE FROM projects WHERE id = ?", (row["id"],))
    settings = dict(ws.get("settings") or {})
    settings["promoted"] = sorted(set(current), key=lambda r: (r.count("/"), r.lower()))
    set_workspace_settings(db, wid, settings)
    return settings["promoted"]


# ---------------------------------------------------------------- scan runs
def scan_run_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "workspace_id": row["workspace_id"], "started_at": row["started_at"], "completed_at": row["completed_at"],
        "status": row["status"], "phase": row["phase"], "counts": loads(row["counts_json"], {}), "errors": loads(row["errors_json"], []),
        "incremental": bool(row["incremental"]), "summary": loads(row["summary_json"], {}) if "summary_json" in row.keys() else {},
    }


def insert_scan_run(db: Database, run: dict[str, Any]) -> None:
    db.execute(
        "INSERT INTO scan_runs(id, workspace_id, started_at, completed_at, status, phase, counts_json, errors_json, incremental, summary_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (run["id"], run["workspace_id"], run["started_at"], run["completed_at"], run["status"], run["phase"], dumps(run["counts"]),
         dumps(run["errors"]), 1 if run["incremental"] else 0, dumps(run.get("summary", {}))),
    )


def update_scan_run(db: Database, run: dict[str, Any]) -> None:
    db.execute(
        "UPDATE scan_runs SET completed_at = ?, status = ?, phase = ?, counts_json = ?, errors_json = ?, summary_json = ? WHERE id = ?",
        (run["completed_at"], run["status"], run["phase"], dumps(run["counts"]), dumps(run["errors"][:500]), dumps(run.get("summary", {})), run["id"]),
    )


def get_scan_run(db: Database, run_id: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM scan_runs WHERE id = ?", (run_id,))
    return scan_run_row(row) if row else None


def list_scan_runs(db: Database, workspace_id: str | None, limit: int = 20) -> list[dict[str, Any]]:
    if workspace_id:
        rows = db.all("SELECT * FROM scan_runs WHERE workspace_id = ? ORDER BY started_at DESC LIMIT ?", (workspace_id, limit))
    else:
        rows = db.all("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?", (limit,))
    return [scan_run_row(r) for r in rows]


# ---------------------------------------------------------------- projects
def upsert_project(db: Database, p: dict[str, Any]) -> None:
    """Insert or update the project row. Never touches category_overrides."""
    db.execute(
        """
        INSERT INTO projects(id, workspace_id, relative_path, name, display_name, detected_type, detection_evidence_json, parent_id,
            discovered_at, last_seen_at, last_analyzed_at, status, status_evidence_json, scan_error, file_count, files_truncated,
            dir_count, size_bytes, last_modified, last_modified_path, primary_language, languages_json, manifests_json, description,
            description_source, readme_excerpt, fingerprint, sub_project_count, file_count_total, components_json, structure_json,
            git_repos_json, important_files_json, removed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, display_name=excluded.display_name, detected_type=excluded.detected_type,
            detection_evidence_json=excluded.detection_evidence_json, parent_id=excluded.parent_id, last_seen_at=excluded.last_seen_at,
            last_analyzed_at=excluded.last_analyzed_at, status=excluded.status, status_evidence_json=excluded.status_evidence_json,
            scan_error=excluded.scan_error, file_count=excluded.file_count, files_truncated=excluded.files_truncated,
            dir_count=excluded.dir_count, size_bytes=excluded.size_bytes, last_modified=excluded.last_modified,
            last_modified_path=excluded.last_modified_path, primary_language=excluded.primary_language, languages_json=excluded.languages_json,
            manifests_json=excluded.manifests_json, description=excluded.description, description_source=excluded.description_source,
            readme_excerpt=excluded.readme_excerpt, fingerprint=excluded.fingerprint, sub_project_count=excluded.sub_project_count,
            file_count_total=excluded.file_count_total, components_json=excluded.components_json, structure_json=excluded.structure_json,
            git_repos_json=excluded.git_repos_json, important_files_json=excluded.important_files_json, removed_at=NULL
        """,
        (
            p["id"], p["workspace_id"], p["relative_path"], p["name"], p["display_name"], p["detected_type"], dumps(p["detection_evidence"]),
            p.get("parent_id"), p["discovered_at"], p["last_seen_at"], p.get("last_analyzed_at"), p["status"], dumps(p["status_evidence"]),
            p.get("scan_error"), p["file_count"], 1 if p["files_truncated"] else 0, p["dir_count"], p["size_bytes"], p.get("last_modified"),
            p.get("last_modified_path"), p.get("primary_language"), dumps(p["languages"]), dumps(p["manifests"]), p.get("description"),
            p.get("description_source"), p.get("readme_excerpt"), p.get("fingerprint"), p.get("sub_project_count", 0),
            p.get("file_count_total"), dumps(p.get("components", [])), dumps(p.get("structure", {})), dumps(p.get("git_repos", [])),
            dumps(p.get("important_files", [])),
        ),
    )


def touch_project_seen(db: Database, pid: str, seen_at: int, status: str, status_evidence: list[dict[str, Any]],
                       display_name: str, parent_id: str | None, sub_project_count: int) -> None:
    db.execute(
        "UPDATE projects SET last_seen_at = ?, status = ?, status_evidence_json = ?, display_name = ?, parent_id = ?, sub_project_count = ?, removed_at = NULL WHERE id = ?",
        (seen_at, status, dumps(status_evidence), display_name, parent_id, sub_project_count, pid),
    )


def replace_files(db: Database, pid: str, files: list[tuple[str, str, int, int, str, int]]) -> None:
    db.execute("DELETE FROM files WHERE project_id = ?", (pid,))
    db.executemany(
        "INSERT OR REPLACE INTO files(project_id, relative_path, extension, size, mtime, kind, sensitive) VALUES (?,?,?,?,?,?,?)",
        ((pid, *f) for f in files),
    )


def replace_technologies(db: Database, pid: str, techs: list[dict[str, Any]]) -> None:
    db.execute("DELETE FROM technologies WHERE project_id = ?", (pid,))
    db.executemany(
        "INSERT OR REPLACE INTO technologies(project_id, name, kind, evidence_json, confidence) VALUES (?,?,?,?,?)",
        ((pid, t["name"], t["kind"], dumps(t["evidence"]), t["confidence"]) for t in techs),
    )


def replace_rule_categories(db: Database, pid: str, cats: list[dict[str, Any]]) -> None:
    db.execute("DELETE FROM categories WHERE project_id = ? AND source = 'rules'", (pid,))
    db.executemany(
        "INSERT OR REPLACE INTO categories(project_id, name, source, evidence_json, confidence) VALUES (?,?,?,?,?)",
        ((pid, c["name"], "rules", dumps(c["evidence"]), c["confidence"]) for c in cats),
    )


def save_git(db: Database, pid: str, g: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO git_snapshots(project_id, repo_root, is_repo_root, branch, detached, dirty, modified_count, untracked_count,
            staged_count, ahead, behind, upstream, last_commit_at, last_commit_subject, last_commit_author, commits_30d, recent_commits_json,
            error, captured_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (pid, g.get("repo_root"), 1 if g.get("is_repo_root") else 0, g.get("branch"), 1 if g.get("detached") else 0,
         None if g.get("dirty") is None else (1 if g.get("dirty") else 0), g.get("modified_count"), g.get("untracked_count"),
         g.get("staged_count"), g.get("ahead"), g.get("behind"), g.get("upstream"), g.get("last_commit_at"), g.get("last_commit_subject"),
         g.get("last_commit_author"), g.get("commits_30d"), dumps(g.get("recent_commits", [])), g.get("error"), int(time.time())),
    )


def get_git(db: Database, pid: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM git_snapshots WHERE project_id = ?", (pid,))
    if not row:
        return None
    return {
        "repo_root": row["repo_root"], "is_repo_root": bool(row["is_repo_root"]), "branch": row["branch"], "detached": bool(row["detached"]),
        "dirty": None if row["dirty"] is None else bool(row["dirty"]), "modified_count": row["modified_count"],
        "untracked_count": row["untracked_count"], "staged_count": row["staged_count"], "ahead": row["ahead"], "behind": row["behind"],
        "upstream": row["upstream"], "last_commit_at": row["last_commit_at"], "last_commit_subject": row["last_commit_subject"],
        "last_commit_author": row["last_commit_author"], "commits_30d": row["commits_30d"],
        "recent_commits": loads(row["recent_commits_json"], []), "error": row["error"], "captured_at": row["captured_at"],
    }


def replace_sub_projects(db: Database, parent_id: str, workspace_id: str, items: list[dict[str, Any]], now: int) -> None:
    """Nested project candidates found inside *parent_id* (nested scan mode). Not nodes: listed under the parent."""
    db.execute("DELETE FROM sub_projects WHERE parent_id = ?", (parent_id,))
    db.executemany(
        "INSERT OR REPLACE INTO sub_projects(id, workspace_id, parent_id, relative_path, name, detected_type, detection_evidence_json, file_count, "
        "primary_language, manifests_json, has_git, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ((c["id"], workspace_id, parent_id, c["relative_path"], c["name"], c["detected_type"], dumps(c.get("detection_evidence", [])), c.get("file_count", 0),
          c.get("primary_language"), dumps(c.get("manifests", [])), 1 if c.get("has_git") else 0, now) for c in items),
    )


def count_sub_projects(db: Database, parent_id: str) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM sub_projects WHERE parent_id = ?", (parent_id,)) or 0)


def list_sub_projects(db: Database, parent_id: str, promoted: set[str] | None = None) -> list[dict[str, Any]]:
    """Candidates from the last scan plus the children already promoted to projects, sorted by path."""
    promoted = promoted or set()
    out = [
        {"id": r["id"], "relative_path": r["relative_path"], "name": r["name"], "detected_type": r["detected_type"],
         "detection_evidence": loads(r["detection_evidence_json"], []), "file_count": r["file_count"], "primary_language": r["primary_language"],
         "manifests": loads(r["manifests_json"], []), "has_git": bool(r["has_git"]), "promoted": r["relative_path"] in promoted, "project_id": None}
        for r in db.all("SELECT * FROM sub_projects WHERE parent_id = ?", (parent_id,))
    ]
    for r in db.all("SELECT id, relative_path, name, detected_type, file_count, file_count_total, primary_language, status FROM projects "
                    "WHERE parent_id = ? AND removed_at IS NULL", (parent_id,)):
        out.append({"id": r["id"], "relative_path": r["relative_path"], "name": r["name"], "detected_type": r["detected_type"], "detection_evidence": [],
                    "file_count": r["file_count_total"] or r["file_count"], "primary_language": r["primary_language"], "manifests": [], "has_git": False,
                    "promoted": True, "project_id": r["id"], "status": r["status"]})
    out.sort(key=lambda c: (c["relative_path"].count("/"), c["relative_path"].lower()))
    return out


def get_git_repos(db: Database, pid: str) -> list[dict[str, Any]]:
    row = db.one("SELECT git_repos_json FROM projects WHERE id = ?", (pid,))
    return loads(row["git_repos_json"], []) if row else []


def mark_missing(db: Database, workspace_id: str, seen_ids: set[str], now: int) -> list[str]:
    rows = db.all("SELECT id FROM projects WHERE workspace_id = ? AND removed_at IS NULL", (workspace_id,))
    missing = [r["id"] for r in rows if r["id"] not in seen_ids]
    for pid in missing:
        db.execute(
            "UPDATE projects SET removed_at = ?, status = 'Missing', status_evidence_json = ? WHERE id = ?",
            (now, dumps([{"signal": "missing", "detail": "path not found during the last completed scan"}]), pid),
        )
    return missing


def forget_project(db: Database, pid: str) -> bool:
    cur = db.execute("DELETE FROM projects WHERE id = ?", (pid,))
    return cur.rowcount > 0


def get_fingerprint(db: Database, pid: str) -> tuple[str | None, int | None]:
    row = db.one("SELECT fingerprint, last_analyzed_at FROM projects WHERE id = ?", (pid,))
    if not row:
        return None, None
    return row["fingerprint"], row["last_analyzed_at"]


def _project_row(db: Database, row: Any, with_details: bool = False) -> dict[str, Any]:
    pid = row["id"]
    rule_cats = [
        {"name": r["name"], "confidence": r["confidence"], "evidence": loads(r["evidence_json"], []), "source": r["source"]}
        for r in db.all("SELECT * FROM categories WHERE project_id = ? ORDER BY confidence DESC", (pid,))
    ]
    override_row = db.one("SELECT * FROM category_overrides WHERE project_id = ?", (pid,))
    override = None
    if override_row:
        override = {"categories": loads(override_row["categories_json"], []), "note": override_row["note"], "updated_at": override_row["updated_at"]}
    effective = override["categories"] if override else [c["name"] for c in rule_cats if c["source"] == "rules"]
    if not effective:
        effective = ["Other"]
    techs = [
        {"name": r["name"], "kind": r["kind"], "confidence": r["confidence"], "evidence": loads(r["evidence_json"], [])}
        for r in db.all("SELECT * FROM technologies WHERE project_id = ? ORDER BY confidence DESC, name", (pid,))
    ]
    languages = loads(row["languages_json"], [])
    components = loads(row["components_json"], [])
    structure = loads(row["structure_json"], {}) or {}
    out: dict[str, Any] = {
        "id": pid, "workspace_id": row["workspace_id"], "relative_path": row["relative_path"], "name": row["name"],
        "display_name": row["display_name"], "detected_type": row["detected_type"], "detection_evidence": loads(row["detection_evidence_json"], []),
        "parent_id": row["parent_id"], "discovered_at": row["discovered_at"], "last_seen_at": row["last_seen_at"],
        "last_analyzed_at": row["last_analyzed_at"], "status": row["status"], "status_evidence": loads(row["status_evidence_json"], []),
        "scan_error": row["scan_error"], "file_count": row["file_count"], "files_truncated": bool(row["files_truncated"]),
        "dir_count": row["dir_count"], "size_bytes": row["size_bytes"], "last_modified": row["last_modified"],
        "last_modified_path": row["last_modified_path"], "primary_language": row["primary_language"], "languages": languages,
        "description": row["description"], "description_source": row["description_source"], "fingerprint": row["fingerprint"],
        "sub_project_count": row["sub_project_count"], "removed_at": row["removed_at"],
        "file_count_total": row["file_count_total"] if row["file_count_total"] is not None else row["file_count"],
        "components": components if with_details else [{"kind": c.get("kind"), "name": c.get("name"), "path": c.get("path"), "file_count": c.get("file_count", 0)} for c in components],
        "structure_kind": structure.get("kind") or ("promoted" if row["detected_type"] == "promoted" else "folder"),
        "categories": effective, "category_details": rule_cats, "category_override": override,
        "technologies": techs[:12] if not with_details else techs,
        "manifests": [{"path": m.get("path"), "kind": m.get("kind"), "name": m.get("name"), "dependency_count": len(m.get("dependencies", [])) + len(m.get("dev_dependencies", []))}
                      for m in loads(row["manifests_json"], [])] if not with_details else loads(row["manifests_json"], []),
    }
    if with_details:
        out["readme_excerpt"] = row["readme_excerpt"]
        out["git"] = get_git(db, pid)
        out["git_repos"] = loads(row["git_repos_json"], [])
        out["structure"] = structure
        out["important_files"] = loads(row["important_files_json"], [])
        ws_settings = db.one("SELECT settings_json FROM workspaces WHERE id = ?", (row["workspace_id"],))
        promoted = set(loads(ws_settings["settings_json"], {}).get("promoted", [])) if ws_settings else set()
        out["promoted"] = row["relative_path"] in promoted
        out["sub_projects"] = list_sub_projects(db, pid, promoted)
        out["children"] = [
            {"id": r["id"], "name": r["name"], "display_name": r["display_name"], "status": r["status"], "file_count": r["file_count_total"] or r["file_count"],
             "relative_path": r["relative_path"]}
            for r in db.all("SELECT id, name, display_name, status, file_count, file_count_total, relative_path FROM projects WHERE parent_id = ? AND removed_at IS NULL ORDER BY name", (pid,))
        ]
        parent = db.one("SELECT id, display_name FROM projects WHERE id = ?", (row["parent_id"],)) if row["parent_id"] else None
        out["parent"] = {"id": parent["id"], "display_name": parent["display_name"]} if parent else None
        out["file_kinds"] = {r["kind"]: r["n"] for r in db.all("SELECT kind, COUNT(*) AS n FROM files WHERE project_id = ? GROUP BY kind", (pid,))}
        out["sensitive_file_count"] = db.scalar("SELECT COUNT(*) FROM files WHERE project_id = ? AND sensitive = 1", (pid,))
        out["recent_files"] = [
            {"relative_path": r["relative_path"], "mtime": r["mtime"], "size": r["size"], "kind": r["kind"]}
            for r in db.all("SELECT relative_path, mtime, size, kind FROM files WHERE project_id = ? ORDER BY mtime DESC LIMIT 8", (pid,))
        ]
        out["ai_suggestions"] = list_ai_suggestions(db, pid, limit=5)
        out["relations"] = list_relations(db, pid)
    else:
        git = db.one("SELECT branch, dirty, last_commit_at, ahead, behind, modified_count, untracked_count FROM git_snapshots WHERE project_id = ?", (pid,))
        out["git"] = None if not git else {
            "branch": git["branch"], "dirty": None if git["dirty"] is None else bool(git["dirty"]), "last_commit_at": git["last_commit_at"],
            "ahead": git["ahead"], "behind": git["behind"], "modified_count": git["modified_count"], "untracked_count": git["untracked_count"],
        }
    return out


def get_project(db: Database, pid: str, with_details: bool = True) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM projects WHERE id = ?", (pid,))
    return _project_row(db, row, with_details) if row else None


def list_projects(db: Database, workspace_id: str | None = None, query: str = "", category: str | None = None,
                  status: str | None = None, language: str | None = None, include_missing: bool = False,
                  sort: str = "name", limit: int = 5000, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    where = ["1=1"]
    params: list[Any] = []
    if workspace_id:
        where.append("p.workspace_id = ?")
        params.append(workspace_id)
    if not include_missing:
        where.append("p.removed_at IS NULL")
    if status:
        where.append("p.status = ?")
        params.append(status)
    if language:
        where.append("EXISTS (SELECT 1 FROM technologies t WHERE t.project_id = p.id AND t.kind = 'language' AND t.name = ?)")
        params.append(language)
    order = {"name": "p.display_name COLLATE NOCASE", "modified": "p.last_modified DESC", "files": "p.file_count DESC",
             "status": "p.status, p.display_name COLLATE NOCASE", "discovered": "p.discovered_at DESC"}.get(sort, "p.display_name COLLATE NOCASE")
    rows = db.all(f"SELECT p.* FROM projects p WHERE {' AND '.join(where)} ORDER BY {order}", params)
    items = [_project_row(db, r) for r in rows]
    q = query.strip().lower()
    if q:
        def matches(p: dict[str, Any]) -> bool:
            hay = " ".join([p["display_name"], p["name"], p["relative_path"], p.get("description") or "", " ".join(p["categories"]),
                            " ".join(t["name"] for t in p["technologies"]), " ".join(lang["name"] for lang in p["languages"])]).lower()
            return all(term in hay for term in q.split())
        items = [p for p in items if matches(p)]
    if category:
        items = [p for p in items if category in p["categories"]]
    total = len(items)
    return items[offset: offset + limit], total


def list_files(db: Database, pid: str, query: str = "", kind: str | None = None, limit: int = 200, offset: int = 0,
               sort: str = "path") -> tuple[list[dict[str, Any]], int]:
    where = ["project_id = ?"]
    params: list[Any] = [pid]
    if query:
        where.append("relative_path LIKE ? ESCAPE '\\'")
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
    if kind:
        where.append("kind = ?")
        params.append(kind)
    order = {"path": "relative_path", "mtime": "mtime DESC, relative_path", "size": "size DESC, relative_path"}.get(sort, "relative_path")
    total = db.scalar(f"SELECT COUNT(*) FROM files WHERE {' AND '.join(where)}", params)
    rows = db.all(f"SELECT relative_path, extension, size, mtime, kind, sensitive FROM files WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
                  [*params, limit, offset])
    return [{"relative_path": r["relative_path"], "extension": r["extension"], "size": r["size"], "mtime": r["mtime"], "kind": r["kind"],
             "sensitive": bool(r["sensitive"])} for r in rows], int(total or 0)


def list_tree(db: Database, pid: str, path: str = "", limit: int = 400) -> dict[str, Any]:
    """Immediate children of *path* inside a project, from the stored file listing (read-only, capped)."""
    prefix = path.strip("/")
    like = (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%") if prefix else "%"
    rows = db.all("SELECT relative_path, extension, size, mtime, kind, sensitive FROM files WHERE project_id = ? AND relative_path LIKE ? ESCAPE '\\'",
                  (pid, like))
    start = len(prefix) + 1 if prefix else 0
    dirs: dict[str, dict[str, Any]] = {}
    files: list[dict[str, Any]] = []
    for r in rows:
        rest = r["relative_path"][start:]
        if "/" in rest:
            name = rest.split("/", 1)[0]
            d = dirs.get(name)
            if d is None:
                d = dirs[name] = {"name": name, "path": f"{prefix}/{name}" if prefix else name, "files": 0, "size": 0, "mtime": 0, "kinds": {}}
            d["files"] += 1
            d["size"] += r["size"]
            d["mtime"] = max(d["mtime"], r["mtime"])
            d["kinds"][r["kind"]] = d["kinds"].get(r["kind"], 0) + 1
        else:
            files.append({"name": rest, "relative_path": r["relative_path"], "extension": r["extension"], "size": r["size"], "mtime": r["mtime"],
                          "kind": r["kind"], "sensitive": bool(r["sensitive"])})
    dir_list = sorted(dirs.values(), key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    total = len(dir_list) + len(files)
    return {"path": prefix, "dirs": dir_list[:limit], "files": files[: max(0, limit - min(limit, len(dir_list)))], "total": total,
            "truncated": total > limit}


def entry_info(db: Database, pid: str, path: str) -> dict[str, Any] | None:
    """Metadata of one stored file, or an aggregate for a directory. None when nothing matches."""
    rel = path.strip("/")
    if not rel:
        return None
    row = db.one("SELECT relative_path, extension, size, mtime, kind, sensitive FROM files WHERE project_id = ? AND relative_path = ?", (pid, rel))
    if row:
        return {"type": "file", "relative_path": row["relative_path"], "name": rel.rsplit("/", 1)[-1], "extension": row["extension"], "size": row["size"],
                "mtime": row["mtime"], "kind": row["kind"], "sensitive": bool(row["sensitive"])}
    like = rel.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
    agg = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS size, MAX(mtime) AS mtime FROM files WHERE project_id = ? AND relative_path LIKE ? ESCAPE '\\'",
                 (pid, like))
    if not agg or not agg["n"]:
        return None
    kinds = {r["kind"]: r["n"] for r in db.all("SELECT kind, COUNT(*) AS n FROM files WHERE project_id = ? AND relative_path LIKE ? ESCAPE '\\' GROUP BY kind",
                                               (pid, like))}
    exts = [r["extension"] for r in db.all("SELECT extension, COUNT(*) AS n FROM files WHERE project_id = ? AND relative_path LIKE ? ESCAPE '\\' "
                                           "AND extension != '' GROUP BY extension ORDER BY n DESC LIMIT 6", (pid, like))]
    return {"type": "dir", "relative_path": rel, "name": rel.rsplit("/", 1)[-1], "files": int(agg["n"]), "size": int(agg["size"]), "mtime": agg["mtime"],
            "kinds": kinds, "extensions": exts}


def set_category_override(db: Database, pid: str, categories: list[str] | None, note: str | None) -> dict[str, Any] | None:
    if categories is None:
        db.execute("DELETE FROM category_overrides WHERE project_id = ?", (pid,))
        return get_project(db, pid, with_details=False)
    clean = []
    for c in categories:
        if c in CATEGORIES and c not in clean:
            clean.append(c)
    if not clean:
        clean = ["Other"]
    db.execute(
        "INSERT INTO category_overrides(project_id, categories_json, note, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(project_id) DO UPDATE SET categories_json=excluded.categories_json, note=excluded.note, updated_at=excluded.updated_at",
        (pid, dumps(clean), (note or "")[:500] or None, int(time.time())),
    )
    return get_project(db, pid, with_details=False)


def set_description_override(db: Database, pid: str, description: str | None) -> None:
    if description is None:
        return
    db.execute("UPDATE projects SET description = ?, description_source = 'manual' WHERE id = ?", (description[:600], pid))


# ---------------------------------------------------------------- relations
def replace_relations(db: Database, computed: list[tuple[str, str, str, float, dict[str, Any]]]) -> None:
    db.execute("DELETE FROM relations WHERE type != 'manual'")
    db.executemany(
        "INSERT OR REPLACE INTO relations(source_id, target_id, type, weight, evidence_json) VALUES (?,?,?,?,?)",
        ((s, t, ty, w, dumps(e)) for s, t, ty, w, e in computed),
    )


def add_manual_relation(db: Database, source: str, target: str, note: str) -> None:
    db.execute("INSERT OR REPLACE INTO relations(source_id, target_id, type, weight, evidence_json) VALUES (?,?,?,?,?)",
               (source, target, "manual", 1.0, dumps({"note": note[:300]})))


def delete_manual_relation(db: Database, source: str, target: str) -> bool:
    cur = db.execute("DELETE FROM relations WHERE source_id = ? AND target_id = ? AND type = 'manual'", (source, target))
    return cur.rowcount > 0


def list_relations(db: Database, pid: str | None = None) -> list[dict[str, Any]]:
    if pid:
        rows = db.all(
            "SELECT r.*, s.display_name AS source_name, t.display_name AS target_name FROM relations r "
            "JOIN projects s ON s.id = r.source_id JOIN projects t ON t.id = r.target_id "
            "WHERE (r.source_id = ? OR r.target_id = ?) AND s.removed_at IS NULL AND t.removed_at IS NULL ORDER BY r.weight DESC", (pid, pid))
    else:
        rows = db.all(
            "SELECT r.*, s.display_name AS source_name, t.display_name AS target_name FROM relations r "
            "JOIN projects s ON s.id = r.source_id JOIN projects t ON t.id = r.target_id WHERE s.removed_at IS NULL AND t.removed_at IS NULL")
    return [{"source_id": r["source_id"], "target_id": r["target_id"], "type": r["type"], "weight": r["weight"],
             "evidence": loads(r["evidence_json"], {}), "source_name": r["source_name"], "target_name": r["target_name"]} for r in rows]


# ---------------------------------------------------------------- AI suggestions
def insert_ai_suggestion(db: Database, s: dict[str, Any]) -> None:
    db.execute(
        "INSERT INTO ai_suggestions(id, project_id, created_at, provider, model, fingerprint, sent_fields_json, payload_json, status) VALUES (?,?,?,?,?,?,?,?,?)",
        (s["id"], s["project_id"], s["created_at"], s["provider"], s["model"], s["fingerprint"], dumps(s["sent_fields"]), dumps(s["payload"]), s["status"]),
    )


def _suggestion_row(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "project_id": r["project_id"], "created_at": r["created_at"], "provider": r["provider"], "model": r["model"],
            "fingerprint": r["fingerprint"], "sent_fields": loads(r["sent_fields_json"], []), "payload": loads(r["payload_json"], {}),
            "status": r["status"], "resolved_at": r["resolved_at"]}


def list_ai_suggestions(db: Database, pid: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    where, params = ["1=1"], []
    if pid:
        where.append("project_id = ?")
        params.append(pid)
    if status:
        where.append("status = ?")
        params.append(status)
    rows = db.all(f"SELECT * FROM ai_suggestions WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", [*params, limit])
    return [_suggestion_row(r) for r in rows]


def get_ai_suggestion(db: Database, sid: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM ai_suggestions WHERE id = ?", (sid,))
    return _suggestion_row(row) if row else None


def find_cached_suggestion(db: Database, pid: str, fingerprint: str, model: str) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM ai_suggestions WHERE project_id = ? AND fingerprint = ? AND model = ? ORDER BY created_at DESC LIMIT 1",
                 (pid, fingerprint, model))
    return _suggestion_row(row) if row else None


def resolve_ai_suggestion(db: Database, sid: str, status: str) -> dict[str, Any] | None:
    db.execute("UPDATE ai_suggestions SET status = ?, resolved_at = ? WHERE id = ?", (status, int(time.time()), sid))
    return get_ai_suggestion(db, sid)


# ---------------------------------------------------------------- stats
def stats(db: Database, workspace_id: str | None = None) -> dict[str, Any]:
    where = "removed_at IS NULL" + (" AND workspace_id = ?" if workspace_id else "")
    params: tuple[Any, ...] = (workspace_id,) if workspace_id else ()
    rows = db.all(f"SELECT status, COUNT(*) AS n FROM projects WHERE {where} GROUP BY status", params)
    by_status = {r["status"]: r["n"] for r in rows}
    total = sum(by_status.values())
    missing = db.scalar("SELECT COUNT(*) FROM projects WHERE removed_at IS NOT NULL" + (" AND workspace_id = ?" if workspace_id else ""), params)
    cat_rows = db.all(
        f"SELECT c.name, COUNT(DISTINCT c.project_id) AS n FROM categories c JOIN projects p ON p.id = c.project_id "
        f"LEFT JOIN category_overrides o ON o.project_id = p.id WHERE p.{where.replace('workspace_id', 'workspace_id')} AND o.project_id IS NULL GROUP BY c.name", params)
    by_category: dict[str, int] = {r["name"]: r["n"] for r in cat_rows}
    for r in db.all(f"SELECT o.categories_json FROM category_overrides o JOIN projects p ON p.id = o.project_id WHERE p.{where}", params):
        for c in loads(r["categories_json"], []):
            by_category[c] = by_category.get(c, 0) + 1
    lang_rows = db.all(
        f"SELECT t.name, COUNT(*) AS n FROM technologies t JOIN projects p ON p.id = t.project_id WHERE t.kind = 'language' AND p.{where} GROUP BY t.name ORDER BY n DESC LIMIT 30", params)
    files_total = db.scalar(f"SELECT COALESCE(SUM(COALESCE(file_count_total, file_count)),0) FROM projects WHERE {where}", params)
    return {
        "total": total, "active": by_status.get("Active", 0), "idle": by_status.get("Idle", 0),
        "needs_attention": by_status.get("Needs attention", 0), "missing": int(missing or 0),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "by_language": {r["name"]: r["n"] for r in lang_rows}, "files_total": int(files_total or 0),
    }
