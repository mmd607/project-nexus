"""Acceptance criteria 8 (security) and API contract."""
from __future__ import annotations

import time
from pathlib import Path


def test_index_has_csp_and_token_not_exposed_by_api(client):
    status, body, headers = client.get("/")
    assert status == 200
    assert "Content-Security-Policy" in headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert headers.get("X-Frame-Options") == "DENY"
    html = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    assert 'name="nexus-token"' in html and "__NEXUS_TOKEN__" not in html
    status, session, _ = client.get("/api/session")
    assert status == 200 and "token" not in session


def test_mutations_require_token(client, workspace_root):
    status, body, _ = client.post("/api/workspaces", {"path": str(workspace_root)}, auth=False)
    assert status == 403 and body["code"] == "token"
    status, body, _ = client.patch("/api/settings", {"ui": {"theme": "light"}}, auth=False)
    assert status == 403
    status, body, _ = client.request("DELETE", "/api/workspaces/0123456789abcdef", auth=False)
    assert status == 403
    status, settings, _ = client.get("/api/settings")
    assert settings["settings"]["ui"]["theme"] == "dark"


def test_cross_origin_requests_are_rejected(client, workspace_root):
    for headers in ({"Origin": "http://evil.example"}, {"Origin": "http://127.0.0.1:9999"}, {"Sec-Fetch-Site": "cross-site"}):
        status, body, _ = client.post("/api/workspaces", {"path": str(workspace_root)}, headers=headers)
        assert status == 403, (headers, body)
        status, _, _ = client.get("/api/projects", headers=headers)
        assert status == 403
    status, _, _ = client.request("OPTIONS", "/api/projects")
    assert status == 403
    status, _, headers = client.get("/api/projects")
    assert status == 200 and "Access-Control-Allow-Origin" not in headers


def test_dns_rebinding_host_check(client):
    status, body, _ = client.get("/api/health", raw_host="evil.example")
    assert status == 421
    status, _, _ = client.get("/api/health", raw_host=f"localhost:{client.port}")
    assert status == 200


def test_static_traversal_blocked(client):
    for path in ["/static/../nexus/db.py", "/static/..%2F..%2Fnexus%2Fdb.py", "/static/css/../../server.py", "/../pyproject.toml", "/static/.hidden"]:
        status, body, _ = client.get(path)
        assert status == 404, path
        assert b"sqlite3" not in (body if isinstance(body, bytes) else b"")
    status, _, headers = client.get("/static/js/app.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript")


def test_workspace_validation(client, tmp_path):
    status, body, _ = client.post("/api/workspaces", {"path": str(tmp_path / "does-not-exist")})
    assert status == 400
    status, body, _ = client.post("/api/workspaces", {"path": ""})
    assert status == 400
    drive_root = Path(str(tmp_path)).anchor
    status, body, _ = client.post("/api/workspaces", {"path": drive_root})
    assert status == 400 and body["code"] == "drive_root"
    status, body, _ = client.post("/api/workspaces", {"path": 123})
    assert status == 400
    status, body, _ = client.request("POST", "/api/workspaces", body=None, headers={"Content-Type": "text/plain"})
    assert status in {400, 415}


def test_ids_are_validated(client):
    for path in ["/api/projects/../../etc", "/api/projects/zzzz", "/api/projects/0123456789abcdef/files?query=%25"]:
        status, _, _ = client.get(path)
        assert status in {400, 404}, path


def test_full_flow_projects_files_categories(scanned_client, workspace_root):
    c = scanned_client
    status, data, _ = c.get("/api/projects")
    assert status == 200 and data["total"] == 15
    assert all("/" not in p["relative_path"] for p in data["items"])
    by_rel = {p["relative_path"]: p for p in data["items"]}
    pid = by_rel["py-ml-cli"]["id"]
    status, detail, _ = c.get(f"/api/projects/{pid}")
    assert status == 200
    p = detail["project"]
    assert p["absolute_path"].endswith("py-ml-cli") and p["exists"] is True
    assert p["git"] is None
    assert p["sensitive_file_count"] == 2
    status, files, _ = c.get(f"/api/projects/{pid}/files?limit=3&offset=0")
    assert len(files["items"]) == 3 and files["total"] == p["file_count"]
    status, files, _ = c.get(f"/api/projects/{pid}/files?query=train&limit=50")
    assert [f["relative_path"] for f in files["items"]] == ["src/py_ml_cli/train.py"]
    # overrides
    status, res, _ = c.patch(f"/api/projects/{pid}/categories", {"categories": ["Security", "Nonsense"], "note": "manual"})
    assert status == 200 and res["project"]["categories"] == ["Security"]
    status, res, _ = c.patch(f"/api/projects/{pid}/categories", {"categories": "AI/ML"})
    assert status == 400
    status, res, _ = c.patch(f"/api/projects/{pid}/categories", {"categories": None})
    assert status == 200 and "AI/ML" in res["project"]["categories"]
    status, res, _ = c.patch(f"/api/projects/{pid}", {"description": "hand written"})
    assert res["project"]["description"] == "hand written" and res["project"]["description_source"] == "manual"
    # filters
    status, data, _ = c.get("/api/projects?category=Security")
    assert all("Security" in p["categories"] for p in data["items"]) and data["total"] >= 1
    status, data, _ = c.get("/api/projects?status=Idle")
    assert all(p["status"] == "Idle" for p in data["items"])
    status, data, _ = c.get("/api/projects?query=flutter")
    assert data["total"] == 1
    status, stats, _ = c.get("/api/stats")
    assert stats["total"] == len(by_rel) and stats["files_total"] > 0
    status, graph, _ = c.get("/api/graph")
    assert any(n["type"] == "technology" for n in graph["nodes"]) and all("evidence" in e for e in graph["edges"])


def test_promote_tree_entry_and_mode_switch(scanned_client, workspace_root):
    c = scanned_client
    status, data, _ = c.get("/api/workspaces")
    ws = data["items"][0]
    assert data["scan_mode"] == "top-level" and ws["promoted"] == [] and ws["last_run"]["summary"]["top_level"] == 15
    status, data, _ = c.get("/api/projects?query=smart-store")
    pid = data["items"][0]["id"]
    status, tree, _ = c.get(f"/api/projects/{pid}/tree?path=backend")
    assert status == 200 and {d["name"] for d in tree["dirs"]} == {"store"}
    status, entry, _ = c.get(f"/api/projects/{pid}/entry?path=frontend/package.json")
    assert status == 200 and entry["entry"]["type"] == "file" and entry["entry"]["kind"] == "manifest"
    status, entry, _ = c.get(f"/api/projects/{pid}/entry?path=does/not/exist")
    assert status == 404
    # promotion validation
    status, body, _ = c.post(f"/api/workspaces/{ws['id']}/promote", {"path": "smart-store"})
    assert status == 400 and body["code"] == "not_nested"
    status, body, _ = c.post(f"/api/workspaces/{ws['id']}/promote", {"path": "smart-store/../outside"})
    assert status == 400
    status, body, _ = c.post(f"/api/workspaces/{ws['id']}/promote", {"path": "smart-store/nope"})
    assert status == 400
    status, body, _ = c.post(f"/api/workspaces/{ws['id']}/promote", {"path": "smart-store/backend"})
    assert status == 200 and body["promoted"] == ["smart-store/backend"] and body["run"]
    deadline = time.time() + 120
    while time.time() < deadline:
        status, run, _ = c.get(f"/api/scan-runs/{body['run']['id']}")
        if run["run"]["status"] != "running":
            break
        time.sleep(0.1)
    status, data, _ = c.get("/api/projects")
    rels = {p["relative_path"]: p for p in data["items"]}
    assert "smart-store/backend" in rels and rels["smart-store/backend"]["parent_id"] == rels["smart-store"]["id"]
    assert rels["smart-store/backend"]["detected_type"] == "promoted"
    status, body, _ = c.post(f"/api/workspaces/{ws['id']}/promote", {"path": "smart-store/backend", "promoted": False})
    assert status == 200 and body["promoted"] == []
    status, data, _ = c.get("/api/projects")
    assert "smart-store/backend" not in {p["relative_path"] for p in data["items"]}
    # switching the detection mode triggers a rescan of every workspace
    status, body, _ = c.patch("/api/settings", {"scan": {"mode": "nested"}})
    assert status == 200 and body["settings"]["scan"]["mode"] == "nested" and len(body["rescans"]) == 1
    status, body, _ = c.patch("/api/settings", {"scan": {"mode": "sideways"}})
    assert status == 400
    while time.time() < deadline:
        status, data, _ = c.get("/api/workspaces")
        if not data["items"][0]["active_run"]:
            break
        time.sleep(0.1)
    status, body, _ = c.patch("/api/settings", {"scan": {"mode": "top-level"}, "rescan": False})
    assert status == 200 and body["rescans"] == []


def test_settings_validation(client):
    status, body, _ = client.patch("/api/settings", {"ai": {"base_url": "http://evil.example:11434"}})
    assert status == 400 and "local" in body["error"]
    status, body, _ = client.patch("/api/settings", {"scan": {"max_depth": 99}})
    assert status == 400
    status, body, _ = client.patch("/api/settings", {"unknown": {"x": 1}})
    assert status == 400
    status, body, _ = client.patch("/api/settings", {"scan": {"max_depth": "3"}})
    assert status == 400
    status, body, _ = client.patch("/api/settings", {"ui": {"theme": "light", "language": "fa"}, "scan": {"ignore": ["node_modules", "*.tmp"]}})
    assert status == 200 and body["settings"]["ui"]["theme"] == "light" and body["settings"]["scan"]["ignore"] == ["node_modules", "*.tmp"]
    status, body, _ = client.get("/api/settings")
    assert body["settings"]["ui"]["language"] == "fa"


def test_export_anonymizes_paths(scanned_client, workspace_root):
    status, data, _ = scanned_client.get("/api/export?anonymize=1")
    assert status == 200 and data["anonymized"]
    assert all(str(workspace_root) not in w["root_path"] for w in data["workspaces"])
    assert all("fingerprint" not in p for p in data["projects"])
    status, data, _ = scanned_client.get("/api/export?anonymize=0")
    assert any(str(workspace_root) == w["root_path"] for w in data["workspaces"])


def test_scan_progress_cancel_and_runs(client, workspace_root):
    status, data, _ = client.post("/api/workspaces", {"path": str(workspace_root), "scan": False})
    wid = data["workspace"]["id"]
    status, data, _ = client.post(f"/api/workspaces/{wid}/scan", {"incremental": False})
    run_id = data["run"]["id"]
    status, res, _ = client.post(f"/api/scan-runs/{run_id}/cancel")
    assert status == 200
    deadline = time.time() + 60
    while time.time() < deadline:
        status, run, _ = client.get(f"/api/scan-runs/{run_id}")
        if run["run"]["status"] != "running":
            break
        time.sleep(0.05)
    assert run["run"]["status"] in {"cancelled", "completed"}
    status, runs, _ = client.get(f"/api/scan-runs?workspace={wid}")
    assert runs["items"][0]["id"] == run_id
    # second workspace overlapping the first is refused
    status, body, _ = client.post("/api/workspaces", {"path": str(workspace_root / "react-app")})
    assert status == 409 and body["code"] == "overlap"
    status, body, _ = client.request("DELETE", f"/api/workspaces/{wid}?purge=1")
    assert status == 200
    status, data, _ = client.get("/api/workspaces")
    assert data["items"] == []


def test_browse_lists_directories_only(client, workspace_root):
    status, data, _ = client.get(f"/api/system/browse?path={workspace_root}")
    assert status == 200
    names = {d["name"] for d in data["dirs"]}
    assert "react-app" in names and "empty-folder" in names
    assert all("path" in d for d in data["dirs"])
    status, data, _ = client.get("/api/system/browse")
    assert data["roots"]


def test_project_open_and_rescan_only_by_id(scanned_client, workspace_root):
    c = scanned_client
    status, data, _ = c.get("/api/projects?query=rust-service")
    pid = data["items"][0]["id"]
    status, res, _ = c.post(f"/api/projects/{pid}/rescan")
    assert status == 200 and res["project"]["id"] == pid
    status, res, _ = c.post("/api/projects/ffffffffffffffff/open")
    assert status == 404
    status, res, _ = c.request("DELETE", f"/api/projects/{pid}")
    assert status == 409   # only missing projects can be forgotten
