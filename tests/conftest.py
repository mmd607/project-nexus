"""Shared fixtures: the acceptance workspace, an in-process app and an HTTP client."""
from __future__ import annotations

import http.client
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "fixtures"))

from make_fixture import build, remove_tree, restore_access  # noqa: E402

from nexus import repo  # noqa: E402
from nexus.db import Database  # noqa: E402
from nexus.paths import static_dir  # noqa: E402
from nexus.scanner import ScanManager  # noqa: E402
from nexus.server import App, make_server  # noqa: E402
from nexus.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def workspace_root(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("nexus-fixture")
    target = base / "workspace"
    manifest = build(target, big=0, use_git=True)
    (base / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    yield target
    restore_access(target / "no-access")
    remove_tree(target)


@pytest.fixture(scope="session")
def fixture_manifest(workspace_root) -> dict:
    return json.loads((workspace_root / ".nexus-fixture.json").read_text(encoding="utf-8"))


def wait_run(run, timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert run.status != "running", "scan did not finish in time"


@pytest.fixture()
def db(tmp_path) -> Database:
    database = Database(tmp_path / "nexus.db")
    yield database
    database.close()


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(tmp_path / "settings.json")


@pytest.fixture()
def scanned(db, settings, workspace_root):
    """A database with the fixture workspace fully scanned once."""
    manager = ScanManager(db, settings)
    ws = repo.add_workspace(db, str(workspace_root))
    run = manager.start(ws)
    wait_run(run)
    return {"db": db, "settings": settings, "manager": manager, "workspace": ws, "run": run}


class Client:
    def __init__(self, host: str, port: int, token: str):
        self.host, self.port, self.token = host, port, token

    def request(self, method: str, path: str, body=None, headers=None, auth=True, raw_host=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
        hdrs = {"Accept": "application/json"}
        if raw_host is not None:
            hdrs["Host"] = raw_host
        if auth and method != "GET":
            hdrs["X-Nexus-Token"] = self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        try:
            parsed = json.loads(payload.decode("utf-8")) if payload else None
        except ValueError:
            parsed = payload
        return resp.status, parsed, dict(resp.getheaders())

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body or {}, **kw)

    def patch(self, path, body=None, **kw):
        return self.request("PATCH", path, body or {}, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)


@pytest.fixture()
def app(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "logs").mkdir(parents=True)
    database = Database(data_dir / "nexus.db")
    settings = Settings(data_dir / "settings.json")
    application = App(database, settings, static_dir(), data_dir, "127.0.0.1", 0)
    server = make_server(application)
    import threading
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    yield application
    server.shutdown()
    server.server_close()
    database.close()


@pytest.fixture()
def client(app) -> Client:
    return Client("127.0.0.1", app.port, app.token)


@pytest.fixture()
def scanned_client(app, client, workspace_root):
    status, data, _ = client.post("/api/workspaces", {"path": str(workspace_root)})
    assert status == 200, data
    run_id = data["run"]["id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        status, run, _ = client.get(f"/api/scan-runs/{run_id}")
        if run["run"]["status"] != "running":
            break
        time.sleep(0.1)
    assert run["run"]["status"] == "completed", run
    return client
