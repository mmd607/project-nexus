"""Explainable relations between projects (used by the Knowledge Graph).

Relation types:
* ``contains``          parent project / group → sub-project
* ``local_dependency``  manifest references another project by path (file:, path =, -e ../x)
* ``shared_technology`` two projects use the same framework/library/database/platform
Every edge carries the evidence that produced it.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from .db import Database, loads
from .fsutil import norm_case

# Technologies too generic to count as a meaningful link.
GENERIC_TECH = {"README", "License file", "Automated tests", "pip / Python packaging", "npm / Node.js", "Cargo", "Go modules",
                "Maven", "Gradle", "Make", "just", "pre-commit", "CMake", "Requests", "HTTPX", "Axios", "dotenv", "Zod", "node-fetch",
                "Serde", "clap (CLI)", "Click (CLI)", "Typer (CLI)", "Rich", "Loguru", "pytest", "Jest", "Vitest", "Mocha", "ESLint",
                "Prettier", "Black", "Ruff", "mypy", "ts-node", "tsx", "esbuild", "nodemon", "Pydantic", "NumPy", "TypeScript"}
MAX_PROJECTS_PER_TECH = 80


def compute_relations(db: Database) -> list[tuple[str, str, str, float, dict[str, Any]]]:
    projects = db.all("SELECT p.id, p.workspace_id, p.relative_path, p.parent_id, p.manifests_json, w.root_path FROM projects p "
                      "JOIN workspaces w ON w.id = p.workspace_id WHERE p.removed_at IS NULL AND w.removed_at IS NULL")
    if not projects:
        return []
    out: list[tuple[str, str, str, float, dict[str, Any]]] = []
    by_abs: dict[str, str] = {}
    for p in projects:
        abs_path = os.path.join(p["root_path"], p["relative_path"].replace("/", os.sep)) if p["relative_path"] else p["root_path"]
        by_abs[norm_case(abs_path)] = p["id"]
        if p["parent_id"]:
            out.append((p["parent_id"], p["id"], "contains", 1.0, {"detail": "sub-project"}))

    # Local path dependencies from manifests.
    for p in projects:
        base = os.path.join(p["root_path"], p["relative_path"].replace("/", os.sep)) if p["relative_path"] else p["root_path"]
        for m in loads(p["manifests_json"], []):
            for dep in (m.get("extra") or {}).get("local_dependencies", []) or []:
                spec = str(dep.get("spec", ""))
                target_rel = spec.split(":", 1)[1] if spec.startswith(("file:", "link:")) else spec
                if spec.startswith("workspace:") or spec == "editable":
                    target_rel = dep.get("name", "") if spec == "editable" else ""
                if not target_rel:
                    continue
                candidate = norm_case(os.path.normpath(os.path.join(os.path.dirname(os.path.join(base, m.get("path", ""))), target_rel)))
                target = by_abs.get(candidate)
                if target and target != p["id"]:
                    out.append((p["id"], target, "local_dependency", 1.0,
                                {"detail": f"{m.get('path')} references {dep.get('name')} ({spec[:80]})"}))

    # Shared technologies via an inverted index.
    rows = db.all("SELECT t.project_id, t.name, t.kind FROM technologies t JOIN projects p ON p.id = t.project_id "
                  "WHERE p.removed_at IS NULL AND t.kind IN ('framework','library','database','platform','tool')")
    index: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["name"] in GENERIC_TECH:
            continue
        index[r["name"]].append(r["project_id"])
    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for tech, ids in index.items():
        if len(ids) < 2 or len(ids) > MAX_PROJECTS_PER_TECH:
            continue
        ids = sorted(set(ids))
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pairs[(ids[i], ids[j])].append(tech)
    parent_of = {p["id"]: p["parent_id"] for p in projects}
    for (a, b), techs in pairs.items():
        if parent_of.get(a) == b or parent_of.get(b) == a:
            continue  # already linked by "contains"
        techs = sorted(techs)
        out.append((a, b, "shared_technology", float(len(techs)), {"technologies": techs[:12], "detail": f"share {len(techs)} technolog{'y' if len(techs) == 1 else 'ies'}"}))
    return out


def knowledge_graph(db: Database, workspace_id: str | None = None, min_shared: int = 1) -> dict[str, Any]:
    """Bipartite graph of projects ↔ technologies/categories plus project–project relations."""
    where = "p.removed_at IS NULL" + (" AND p.workspace_id = ?" if workspace_id else "")
    params: tuple[Any, ...] = (workspace_id,) if workspace_id else ()
    projects = db.all(f"SELECT p.id, p.display_name, p.status, p.parent_id, p.primary_language, p.file_count FROM projects p WHERE {where}", params)
    ids = {p["id"] for p in projects}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for p in projects:
        cats_rows = db.all("SELECT name, confidence FROM categories WHERE project_id = ? AND source = 'rules'", (p["id"],))
        override = db.one("SELECT categories_json FROM category_overrides WHERE project_id = ?", (p["id"],))
        cats = loads(override["categories_json"], []) if override else [c["name"] for c in cats_rows]
        nodes.append({"id": p["id"], "type": "project", "label": p["display_name"], "status": p["status"], "categories": cats or ["Other"],
                      "language": p["primary_language"], "file_count": p["file_count"], "parent_id": p["parent_id"] if p["parent_id"] in ids else None})
        conf = {c["name"]: c["confidence"] for c in cats_rows}
        for c in cats or ["Other"]:
            edges.append({"source": p["id"], "target": f"cat:{c}", "type": "category", "weight": conf.get(c, 1.0),
                          "evidence": {"detail": "manual override" if override else f"rule confidence {conf.get(c, 0):.0%}"}})
    tech_rows = db.all(
        f"SELECT t.project_id, t.name, t.kind, t.confidence, t.evidence_json FROM technologies t JOIN projects p ON p.id = t.project_id "
        f"WHERE {where} AND t.kind IN ('framework','library','database','platform','language','tool')", params)
    tech_projects: dict[str, list[Any]] = defaultdict(list)
    for r in tech_rows:
        if r["name"] in GENERIC_TECH:
            continue
        tech_projects[r["name"]].append(r)
    for name, rows in tech_projects.items():
        if len(rows) < min_shared:
            continue
        nodes.append({"id": f"tech:{name}", "type": "technology", "label": name, "kind": rows[0]["kind"], "degree": len(rows)})
        for r in rows:
            ev = loads(r["evidence_json"], [])
            edges.append({"source": r["project_id"], "target": f"tech:{name}", "type": "uses", "weight": r["confidence"],
                          "evidence": {"detail": ev[0]["detail"] if ev else "detected"}})
    used_cats = {e["target"] for e in edges if e["type"] == "category"}
    for cat in sorted(used_cats):
        nodes.append({"id": cat, "type": "category", "label": cat[4:], "degree": sum(1 for e in edges if e["target"] == cat)})
    for r in db.all("SELECT * FROM relations"):
        if r["source_id"] in ids and r["target_id"] in ids:
            edges.append({"source": r["source_id"], "target": r["target_id"], "type": r["type"], "weight": r["weight"], "evidence": loads(r["evidence_json"], {})})
    return {"nodes": nodes, "edges": edges}
