"""Acceptance criteria 2, 3 and 7: scanning robustness, data correctness, persistence."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from conftest import wait_run

from nexus import repo
from nexus.fsutil import IgnoreMatcher, is_within
from nexus.scanner import ScanManager

MANIFEST_NAMES = {"pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "pubspec.yaml", "mkdocs.yml"}


def by_rel(db):
    items, _ = repo.list_projects(db)
    return {p["relative_path"]: p for p in items}


def count_files(root: Path, exclude: set[str] = frozenset()) -> int:
    n = 0
    for base, dirs, files in os.walk(root):
        rel = Path(base).relative_to(root).as_posix()
        rel = "" if rel == "." else rel
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"} and (f"{rel}/{d}" if rel else d) not in exclude]
        n += len(files)
    return n


TOP_LEVEL = ["py-ml-cli", "react-app", "rust-service", "mono-shop", "outer-repo", "پروژه-فارسی", "net-recon", "flutter-notes", "team-handbook",
             "prompt-library", "infra-cluster", "sales-analytics", "old-scripts", "landing-site", "smart-store"]


def test_scan_completes_without_crash(scanned, fixture_manifest):
    run = scanned["run"]
    assert run.status == "completed"
    assert run.counts["discovered"] == len(TOP_LEVEL)
    assert run.summary["top_level"] == len(TOP_LEVEL) and run.summary["mode"] == "top-level"
    skipped = {s["name"]: s["reason"] for s in run.summary["skipped"]}
    assert skipped.get("empty-folder") == "empty folder"
    if fixture_manifest["no_access"]:
        assert any("no-access" in e["where"] for e in run.errors), run.errors
        assert "no-access" in skipped


def test_every_top_level_folder_is_exactly_one_project(scanned, workspace_root):
    """The rule the whole model rests on: one node per valid top-level folder, nothing nested."""
    projects = by_rel(scanned["db"])
    assert sorted(projects) == sorted(TOP_LEVEL), sorted(projects)
    for rel, p in projects.items():
        assert "/" not in rel and p["parent_id"] is None and p["detected_type"] == "folder"
        assert p["name"] == rel == p["display_name"]
    for nested in ["mono-shop/packages/web", "mono-shop/packages/api", "outer-repo/nested-repo", "smart-store/backend", "smart-store/frontend"]:
        assert nested not in projects
    assert "empty-folder" not in projects
    assert "no-access" not in projects
    assert "loop-link" not in projects and "escape-link" not in projects
    on_disk = sorted(d.name for d in workspace_root.iterdir() if d.is_dir() and not d.is_symlink() and d.name not in {"empty-folder", "no-access", "loop-link", "escape-link"})
    assert sorted(projects) == on_disk


def test_links_are_never_followed(scanned, fixture_manifest, workspace_root):
    db = scanned["db"]
    rows = db.all("SELECT relative_path FROM files")
    assert not any("loop-link" in r["relative_path"] or "escape-link" in r["relative_path"] for r in rows)
    assert not any("secret-outside" in r["relative_path"] for r in rows)
    projects = by_rel(db)
    assert not any("outside" in rel for rel in projects)
    assert is_within(workspace_root / "py-ml-cli", workspace_root)
    assert not is_within(Path(fixture_manifest["outside"]), workspace_root)


def test_file_counts_match_disk(scanned, workspace_root):
    projects = by_rel(scanned["db"])
    for rel in ["py-ml-cli", "react-app", "rust-service", "net-recon", "flutter-notes"]:
        expected = count_files(workspace_root / rel)
        assert projects[rel]["file_count"] == expected, (rel, projects[rel]["file_count"], expected)
    # parents include everything below them (nested repositories, packages, components)
    assert projects["outer-repo"]["file_count"] == count_files(workspace_root / "outer-repo")
    assert projects["mono-shop"]["file_count"] == count_files(workspace_root / "mono-shop")
    assert projects["smart-store"]["file_count"] == projects["smart-store"]["file_count_total"] == count_files(workspace_root / "smart-store")


def test_languages_and_manifests(scanned):
    projects = by_rel(scanned["db"])
    assert projects["py-ml-cli"]["primary_language"] == "Python"
    assert projects["react-app"]["primary_language"] == "TypeScript"
    assert projects["rust-service"]["primary_language"] == "Rust"
    assert "Go" in {lang["name"] for lang in projects["outer-repo"]["languages"]}   # nested repo rolled up into its parent
    assert projects["flutter-notes"]["primary_language"] == "Dart"
    manifests = {m["path"] for m in projects["py-ml-cli"]["manifests"]}
    assert {"pyproject.toml", "requirements.txt"} <= manifests
    assert {"package.json", "packages/web/package.json", "packages/api/package.json"} <= {m["path"] for m in projects["mono-shop"]["manifests"]}
    detail = repo.get_project(scanned["db"], projects["py-ml-cli"]["id"])
    deps = {d for m in detail["manifests"] for d in m["dependencies"]}
    assert {"torch", "pandas", "typer"} <= deps


def test_last_modified_matches_newest_file(scanned, workspace_root):
    projects = by_rel(scanned["db"])
    p = projects["react-app"]
    newest = max(int(f.stat().st_mtime) for f in (workspace_root / "react-app").rglob("*") if f.is_file())
    assert p["last_modified"] == newest
    assert projects["old-scripts"]["status"] == "Idle"
    assert any(e["signal"] == "window" for e in projects["old-scripts"]["status_evidence"])


def test_git_status_and_nested_repo(scanned, fixture_manifest):
    if not fixture_manifest["projects"]["outer-repo"].get("dirty"):
        return
    db = scanned["db"]
    projects = by_rel(db)
    outer = repo.get_project(db, projects["outer-repo"]["id"])
    assert outer["git"]["branch"] == "main"
    assert outer["git"]["dirty"] is True
    assert outer["git"]["untracked_count"] >= 1
    assert outer["status"] == "Needs attention"
    assert any(e["signal"] == "git_dirty" for e in outer["status_evidence"])
    # the nested repository is reported inside its parent, not as a project of its own
    nested = {r["path"]: r for r in outer["git_repos"]}
    assert "nested-repo" in nested and nested["nested-repo"]["branch"] == "main" and nested["nested-repo"]["dirty"] is False
    assert nested["nested-repo"]["last_commit_subject"] == "nested initial"
    assert any(e["rule"] == "nested-git" for e in outer["detection_evidence"])


def test_monorepo_is_one_project_with_components(scanned):
    db = scanned["db"]
    projects = by_rel(db)
    parent = repo.get_project(db, projects["mono-shop"]["id"])
    assert parent["children"] == [] and parent["sub_project_count"] == 0 and parent["sub_projects"] == []
    kinds = {c["path"]: c["kind"] for c in parent["components"]}
    assert kinds.get("packages/web") == "Frontend" and kinds.get("packages/api") == "Backend" and kinds.get("packages/api-client") == "Shared"
    assert all(c["candidate"] for c in parent["components"] if c["path"].startswith("packages/"))
    assert "Full-stack" in parent["categories"]
    assert parent["structure"]["kind"] == "monorepo"
    assert {d["name"] for d in parent["structure"]["tree"]} == {"packages"}
    assert {c["name"] for c in parent["structure"]["tree"][0]["children"]} == {"web", "api", "api-client"}
    assert any(f["path"] == "packages/web/package.json" and f["kind"] == "manifest" for f in parent["important_files"])


def test_multi_part_project_components_and_labels(scanned):
    db = scanned["db"]
    p = repo.get_project(db, by_rel(db)["smart-store"]["id"])
    kinds = {c["name"]: c["kind"] for c in p["components"]}
    assert kinds["backend"] == "Backend" and kinds["frontend"] == "Frontend" and kinds["ai"] == "AI/ML"
    assert kinds["docs"] == "Documentation" and kinds["tests"] == "Tests" and kinds["Deployment"] == "DevOps"
    assert "Full-stack" in p["categories"] and "AI/ML" in p["categories"]
    assert "Documentation" not in p["categories"]     # a docs/ folder does not make the project a documentation project
    assert p["structure"]["kind"] == "multi-part"
    for c in p["components"]:
        assert c["evidence"], c
    backend = next(c for c in p["components"] if c["name"] == "backend")
    assert backend["manifests"] == ["backend/requirements.txt"] and backend["languages"] == ["Python"] and backend["candidate"]
    assert {"Django", "Vue", "PyTorch"} <= {t["name"] for t in p["technologies"]}, [t["name"] for t in p["technologies"]]
    important = {f["path"]: f["kind"] for f in p["important_files"]}
    assert important["README.md"] == "readme" and important["docker-compose.yml"] == "manifest" and important[".github/workflows/ci.yml"] == "ci"


def test_nested_mode_lists_candidates_and_promotion_makes_nodes(scanned, workspace_root):
    db, settings, manager, ws = scanned["db"], scanned["settings"], scanned["manager"], scanned["workspace"]
    settings.update({"scan": {"mode": "nested"}})
    run = manager.start(ws)
    wait_run(run)
    assert run.summary["mode"] == "nested" and run.summary["candidates"] >= 4
    projects = by_rel(db)
    assert sorted(projects) == sorted(TOP_LEVEL)                     # candidates are listed, not turned into nodes
    mono = repo.get_project(db, projects["mono-shop"]["id"])
    candidates = {c["relative_path"]: c for c in mono["sub_projects"]}
    assert set(candidates) == {"mono-shop/packages/web", "mono-shop/packages/api", "mono-shop/packages/api-client"}
    assert all(not c["promoted"] and c["detected_type"] == "manifest" for c in candidates.values())
    outer = repo.get_project(db, projects["outer-repo"]["id"])
    assert any(c["relative_path"] == "outer-repo/nested-repo" and c["has_git"] for c in outer["sub_projects"])
    assert candidates["mono-shop/packages/web"]["primary_language"] == "TypeScript"

    # promote two packages → they become nodes under their parent; the parent no longer counts their files
    repo.set_promoted(db, ws["id"], "mono-shop/packages/web", True)
    repo.set_promoted(db, ws["id"], "mono-shop/packages/api-client", True)
    run = manager.start(ws)
    wait_run(run)
    projects = by_rel(db)
    assert "mono-shop/packages/web" in projects and "mono-shop/packages/api-client" in projects
    web = repo.get_project(db, projects["mono-shop/packages/web"]["id"])
    assert web["detected_type"] == "promoted" and web["parent_id"] == projects["mono-shop"]["id"] and web["promoted"] is True
    mono = repo.get_project(db, projects["mono-shop"]["id"])
    assert {c["name"] for c in mono["children"]} == {"web", "api-client"} and mono["sub_project_count"] == 2
    assert mono["file_count"] == count_files(workspace_root / "mono-shop", {"packages/web", "packages/api-client"})
    assert {c["relative_path"] for c in mono["sub_projects"] if c["promoted"]} == {"mono-shop/packages/web", "mono-shop/packages/api-client"}
    rels = repo.list_relations(db, web["id"])
    assert any(r["type"] == "local_dependency" and r["target_name"] == "api-client" for r in rels), rels

    # un-promote → the node disappears immediately and the parent absorbs the folder again
    repo.set_promoted(db, ws["id"], "mono-shop/packages/web", False)
    assert "mono-shop/packages/web" not in by_rel(db)
    run = manager.start(ws)
    wait_run(run)
    mono = repo.get_project(db, projects["mono-shop"]["id"])
    assert {c["name"] for c in mono["children"]} == {"api-client"}
    assert mono["file_count"] == count_files(workspace_root / "mono-shop", {"packages/api-client"})
    repo.set_promoted(db, ws["id"], "mono-shop/packages/api-client", False)
    settings.update({"scan": {"mode": "top-level"}})
    run = manager.start(ws)
    wait_run(run)
    assert sorted(by_rel(db)) == sorted(TOP_LEVEL)
    assert repo.get_project(db, projects["mono-shop"]["id"])["sub_projects"] == []


def test_tree_and_entry_lookups(scanned):
    db = scanned["db"]
    pid = by_rel(db)["smart-store"]["id"]
    root = repo.list_tree(db, pid)
    assert {d["name"] for d in root["dirs"]} >= {"backend", "frontend", "ai", "docs", "tests"}
    assert any(f["name"] == "README.md" for f in root["files"])
    backend = repo.list_tree(db, pid, "backend")
    assert {f["name"] for f in backend["files"]} == {"requirements.txt", "manage.py"} and {d["name"] for d in backend["dirs"]} == {"store"}
    assert repo.entry_info(db, pid, "backend/manage.py")["type"] == "file"
    folder = repo.entry_info(db, pid, "ai")
    assert folder["type"] == "dir" and folder["files"] == 5 and folder["kinds"].get("model") == 1
    assert repo.entry_info(db, pid, "nope/nothing") is None


def test_sensitive_files_flagged_never_read(scanned):
    db = scanned["db"]
    projects = by_rel(db)
    files, _ = repo.list_files(db, projects["py-ml-cli"]["id"], limit=500)
    sensitive = {f["relative_path"] for f in files if f["sensitive"]}
    assert ".env" in sensitive and "config/credentials.json" in sensitive
    detail = repo.get_project(db, projects["py-ml-cli"]["id"])
    assert "sk-secret" not in (detail["readme_excerpt"] or "")
    assert "sk-secret" not in str(detail["manifests"])


def test_persian_named_project(scanned):
    projects = by_rel(scanned["db"])
    p = projects["پروژه-فارسی"]
    assert p["name"] == "پروژه-فارسی"
    assert p["file_count"] == 4
    assert p["description"] and "پایتون" in p["description"]


def test_incremental_rescan_uses_cache(scanned):
    manager, ws = scanned["manager"], scanned["workspace"]
    run = manager.start(ws)
    wait_run(run)
    assert run.status == "completed"
    assert run.counts["cached"] == run.counts["discovered"]
    assert run.counts["analyzed"] == 0


def test_change_detected_after_edit(scanned, workspace_root):
    manager, ws, db = scanned["manager"], scanned["workspace"], scanned["db"]
    target = workspace_root / "rust-service" / "src" / "new_module.rs"
    target.write_text("pub fn x() {}\n", encoding="utf-8")
    try:
        run = manager.start(ws)
        wait_run(run)
        assert run.counts["analyzed"] >= 1
        p = by_rel(db)["rust-service"]
        assert p["file_count"] == count_files(workspace_root / "rust-service")
    finally:
        target.unlink()


def test_override_survives_rescan_and_missing_project_lifecycle(scanned, workspace_root):
    manager, ws, db = scanned["manager"], scanned["workspace"], scanned["db"]
    pid = by_rel(db)["landing-site"]["id"]
    repo.set_category_override(db, pid, ["Documentation", "Frontend"], "checked by hand")
    run = manager.start(ws)
    wait_run(run)
    p = repo.get_project(db, pid)
    assert p["categories"] == ["Documentation", "Frontend"]
    assert p["category_override"]["note"] == "checked by hand"

    # move the project away → marked missing, override kept
    src, moved = workspace_root / "landing-site", workspace_root.parent / "landing-site-moved"
    shutil.move(str(src), str(moved))
    try:
        run = manager.start(ws)
        wait_run(run)
        assert run.counts["missing"] == 1
        gone = repo.get_project(db, pid)
        assert gone["status"] == "Missing" and gone["removed_at"]
        assert gone["category_override"]["categories"] == ["Documentation", "Frontend"]
        assert pid not in by_rel(db)  # hidden from the default list
        items, _ = repo.list_projects(db, include_missing=True)
        assert any(i["id"] == pid for i in items)
    finally:
        shutil.move(str(moved), str(src))
    run = manager.start(ws)
    wait_run(run)
    back = repo.get_project(db, pid)
    assert back["removed_at"] is None and back["status"] != "Missing"
    assert back["categories"] == ["Documentation", "Frontend"]


def test_cancel_stops_scan(db, settings, workspace_root):
    manager = ScanManager(db, settings)
    ws = repo.add_workspace(db, str(workspace_root))
    run = manager.start(ws)
    assert manager.cancel(run.id)
    wait_run(run)
    assert run.status in {"cancelled", "completed"}
    assert not manager.cancel(run.id)


def test_limits_are_respected(db, settings, workspace_root):
    settings.update({"scan": {"max_projects": 3, "max_files_per_project": 10}})
    manager = ScanManager(db, settings)
    ws = repo.add_workspace(db, str(workspace_root))
    run = manager.start(ws)
    wait_run(run)
    items, total = repo.list_projects(db)
    assert total <= 3
    assert all(p["file_count"] <= 10 for p in items)
    assert any("project limit" in e["message"] for e in run.errors)


def test_ignore_matcher_patterns():
    m = IgnoreMatcher.from_list(["node_modules", "*.egg-info", "Build"])
    assert m.matches("node_modules") and m.matches("NODE_MODULES")
    assert m.matches("foo.egg-info") and not m.matches("foo.egg")
    assert m.matches("build")


def _tree_signature(root: Path) -> list[tuple[str, int, int]]:
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "no-access"]
        for name in files:
            p = Path(base) / name
            try:
                st = p.lstat()
            except OSError:
                continue
            out.append((str(p.relative_to(root)), st.st_size, int(st.st_mtime)))
    return sorted(out)


def test_scanning_never_writes_into_the_workspace(db, settings, workspace_root):
    """Security: a full scan (incl. git inspection) leaves every file untouched — same set, sizes and mtimes."""
    before = _tree_signature(workspace_root)
    manager = ScanManager(db, settings)
    ws = repo.add_workspace(db, str(workspace_root))
    run = manager.start(ws)
    wait_run(run)
    assert run.status == "completed"
    items, _ = repo.list_projects(db)
    for p in items[:5]:
        manager.rescan_project(repo.get_project(db, p["id"]))
    after = _tree_signature(workspace_root)
    assert before == after
