"""Local HTTP API + static frontend on top of the standard library.

Security model (see docs/SECURITY.md):
* binds to 127.0.0.1 unless the user passes ``--host`` explicitly;
* every request must carry a Host header that matches the bound address (blocks DNS rebinding);
* state-changing requests must carry the per-launch token (``X-Nexus-Token``) that is only
  embedded in the HTML served from this origin, and an Origin header (if present) matching it;
* no CORS headers are ever emitted, so other origins cannot read responses;
* static files come only from the bundled ``static`` directory; API paths use opaque ids.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, gitinfo, picker, repo
from . import ai as ai_module
from .db import Database
from .fsutil import display_path, is_within
from .relations import knowledge_graph
from .scanner import ScanManager
from .settings import Settings, SettingsError

ID_RE = re.compile(r"^[0-9a-f]{16}$")
MAX_BODY = 1_000_000


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra: Any):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


class App:
    """Shared application state handed to every request handler."""

    def __init__(self, db: Database, settings: Settings, static_dir: Path, data_dir: Path, host: str, port: int,
                 log: Callable[[str], None] | None = None):
        self.db = db
        self.settings = settings
        self.static_dir = static_dir
        self.data_dir = data_dir
        self.host = host
        self.port = port
        self.token = secrets.token_urlsafe(32)
        self.started_at = int(time.time())
        self.log = log or (lambda msg: None)
        self.scans = ScanManager(db, settings, self.log)
        self.ai = ai_module.AIService(db, settings)
        self.allowed_hosts = {f"{host}:{port}", host}
        if host in {"127.0.0.1", "localhost", "::1"}:
            self.allowed_hosts |= {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        self._index_cache: bytes | None = None
        (data_dir / "session.json").write_text(json.dumps({"token": self.token, "port": port, "host": host, "pid": os.getpid()}), encoding="utf-8")

    def index_html(self) -> bytes:
        if self._index_cache is None:
            html = (self.static_dir / "index.html").read_text(encoding="utf-8")
            html = html.replace("__NEXUS_TOKEN__", self.token).replace("__NEXUS_VERSION__", __version__)
            self._index_cache = html.encode("utf-8")
        return self._index_cache


Route = tuple[str, re.Pattern[str], Callable[["Handler", dict[str, str], dict[str, Any]], Any]]
ROUTES: list[Route] = []


def route(method: str, pattern: str):
    compiled = re.compile("^" + pattern + "$")

    def register(fn):
        ROUTES.append((method, compiled, fn))
        return fn
    return register


def _int(params: dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    raw = params.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, f"{key} must be an integer") from None
    return max(lo, min(hi, value))


def _project_or_404(app: App, pid: str, details: bool = True) -> dict[str, Any]:
    if not ID_RE.match(pid):
        raise ApiError(400, "invalid id")
    project = repo.get_project(app.db, pid, with_details=details)
    if not project:
        raise ApiError(404, "project not found")
    return project


# ------------------------------------------------------------------ routes
@route("GET", "/api/health")
def health(h: "Handler", _p: dict[str, str], _q: dict[str, Any]) -> Any:
    return {"ok": True, "version": __version__, "uptime": int(time.time()) - h.app.started_at}


@route("GET", "/api/session")
def session(h: "Handler", _p: dict[str, str], _q: dict[str, Any]) -> Any:
    privacy = h.app.settings.section("privacy")
    return {
        "version": __version__, "platform": sys.platform, "git_available": bool(gitinfo.git_executable()),
        "data_dir": display_path(str(h.app.data_dir), False), "loopback": h.app.host in {"127.0.0.1", "localhost", "::1"},
        "host": h.app.host, "port": h.app.port, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
        "anonymize_paths_in_export": privacy["anonymize_paths_in_export"],
    }


@route("GET", "/api/workspaces")
def workspaces(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    items = repo.list_workspaces(h.app.db, include_removed=q.get("include_removed") == "1")
    for ws in items:
        active = h.app.scans.active_run(ws["id"])
        ws["active_run"] = active.to_dict() if active else None
        ws["exists"] = Path(ws["root_path"]).is_dir()
        ws["promoted"] = list((ws.get("settings") or {}).get("promoted", []))
    return {"items": items, "scan_mode": h.app.settings.section("scan").get("mode", "top-level")}


@route("POST", "/api/workspaces/(?P<id>[0-9a-f]{16})/promote")
def promote_folder(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    """Mark (or unmark) a nested folder as an independent project node; the workspace is rescanned incrementally."""
    ws = repo.get_workspace(h.app.db, p["id"])
    if not ws or ws.get("removed_at"):
        raise ApiError(404, "workspace not found")
    raw = body.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise ApiError(400, "path is required")
    rel = raw.strip().strip("/\\").replace("\\", "/")
    if "/" not in rel or any(part in {"", ".", ".."} for part in rel.split("/")):
        raise ApiError(400, "path must point to a nested folder inside a top-level project", code="not_nested")
    target = Path(ws["root_path"]).joinpath(*rel.split("/"))
    promoted = bool(body.get("promoted", True))
    if promoted and (not target.is_dir() or not is_within(target, ws["root_path"])):
        raise ApiError(400, "folder not found inside the workspace")
    listed = repo.set_promoted(h.app.db, ws["id"], rel, promoted)
    h.app.scans._compute_relations()
    run = None
    if Path(ws["root_path"]).is_dir():
        run = h.app.scans.start(ws, incremental=True).to_dict()
    return {"promoted": listed, "run": run}


@route("POST", "/api/workspaces")
def add_workspace(h: "Handler", _p: dict[str, str], body: dict[str, Any]) -> Any:
    raw = body.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise ApiError(400, "path is required")
    path = Path(raw.strip()).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ApiError(400, "folder does not exist") from None
    if not resolved.is_dir():
        raise ApiError(400, "path is not a directory")
    if resolved == Path(resolved.anchor) and not body.get("allow_root"):
        raise ApiError(400, "scanning a whole drive root is not allowed; choose the folder that contains your projects", code="drive_root")
    for existing in repo.list_workspaces(h.app.db):
        if is_within(resolved, existing["root_path"]) or is_within(existing["root_path"], resolved):
            if Path(existing["root_path"]) != resolved:
                raise ApiError(409, f"overlaps with existing workspace '{existing['display_name']}'", code="overlap")
    name = body.get("display_name") if isinstance(body.get("display_name"), str) else None
    ws = repo.add_workspace(h.app.db, str(resolved), (name or "").strip()[:120] or None)
    run = None
    if body.get("scan", True):
        run = h.app.scans.start(ws, incremental=True).to_dict()
    return {"workspace": ws, "run": run}


@route("PATCH", "/api/workspaces/(?P<id>[0-9a-f]{16})")
def patch_workspace(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    ws = repo.get_workspace(h.app.db, p["id"])
    if not ws:
        raise ApiError(404, "workspace not found")
    name = body.get("display_name")
    if isinstance(name, str) and name.strip():
        repo.rename_workspace(h.app.db, p["id"], name.strip())
    return {"workspace": repo.get_workspace(h.app.db, p["id"])}


@route("DELETE", "/api/workspaces/(?P<id>[0-9a-f]{16})")
def delete_workspace(h: "Handler", p: dict[str, str], q: dict[str, Any]) -> Any:
    active = h.app.scans.active_run(p["id"])
    if active:
        active.cancel.set()
    ok = repo.remove_workspace(h.app.db, p["id"], purge=q.get("purge") == "1")
    if not ok:
        raise ApiError(404, "workspace not found")
    h.app.scans._compute_relations()
    return {"ok": True}


@route("POST", "/api/workspaces/(?P<id>[0-9a-f]{16})/scan")
def scan_workspace(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    ws = repo.get_workspace(h.app.db, p["id"])
    if not ws or ws.get("removed_at"):
        raise ApiError(404, "workspace not found")
    if not Path(ws["root_path"]).is_dir():
        raise ApiError(409, "workspace folder is not accessible right now", code="root_missing")
    run = h.app.scans.start(ws, incremental=bool(body.get("incremental", True)))
    return {"run": run.to_dict()}


@route("GET", "/api/scan-runs")
def scan_runs(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    return {"items": repo.list_scan_runs(h.app.db, q.get("workspace") or None, _int(q, "limit", 20, 1, 200))}


@route("GET", "/api/scan-runs/(?P<id>[0-9a-f]{16})")
def scan_run(h: "Handler", p: dict[str, str], _q: dict[str, Any]) -> Any:
    run = h.app.scans.get(p["id"])
    if not run:
        raise ApiError(404, "scan run not found")
    return {"run": run}


@route("POST", "/api/scan-runs/(?P<id>[0-9a-f]{16})/cancel")
def cancel_scan(h: "Handler", p: dict[str, str], _b: dict[str, Any]) -> Any:
    return {"cancelled": h.app.scans.cancel(p["id"])}


@route("GET", "/api/projects")
def projects(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    items, total = repo.list_projects(
        h.app.db, workspace_id=q.get("workspace") or None, query=str(q.get("query") or "")[:200], category=q.get("category") or None,
        status=q.get("status") or None, language=q.get("language") or None, include_missing=q.get("include_missing") == "1",
        sort=str(q.get("sort") or "name"), limit=_int(q, "limit", 5000, 1, 20000), offset=_int(q, "offset", 0, 0, 10**7),
    )
    return {"items": items, "total": total}


@route("GET", "/api/projects/(?P<id>[0-9a-f]{16})")
def project(h: "Handler", p: dict[str, str], _q: dict[str, Any]) -> Any:
    project = _project_or_404(h.app, p["id"])
    ws = repo.get_workspace(h.app.db, project["workspace_id"])
    project["absolute_path"] = str(Path(ws["root_path"]) / project["relative_path"]) if ws else None
    project["exists"] = bool(project["absolute_path"]) and Path(project["absolute_path"]).is_dir()
    return {"project": project}


@route("GET", "/api/projects/(?P<id>[0-9a-f]{16})/files")
def project_files(h: "Handler", p: dict[str, str], q: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    items, total = repo.list_files(h.app.db, p["id"], query=str(q.get("query") or "")[:200], kind=q.get("kind") or None,
                                   limit=_int(q, "limit", 200, 1, 2000), offset=_int(q, "offset", 0, 0, 10**7), sort=str(q.get("sort") or "path"))
    return {"items": items, "total": total}


@route("GET", "/api/projects/(?P<id>[0-9a-f]{16})/tree")
def project_tree(h: "Handler", p: dict[str, str], q: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    return repo.list_tree(h.app.db, p["id"], str(q.get("path") or "")[:600], limit=_int(q, "limit", 400, 1, 2000))


@route("GET", "/api/projects/(?P<id>[0-9a-f]{16})/entry")
def project_entry(h: "Handler", p: dict[str, str], q: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    info = repo.entry_info(h.app.db, p["id"], str(q.get("path") or "")[:600])
    if not info:
        raise ApiError(404, "no such file or folder in the last scan")
    return {"entry": info}


@route("PATCH", "/api/projects/(?P<id>[0-9a-f]{16})/categories")
def patch_categories(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    cats = body.get("categories")
    if cats is not None and (not isinstance(cats, list) or not all(isinstance(c, str) for c in cats)):
        raise ApiError(400, "categories must be a list of strings or null to clear the override")
    note = body.get("note") if isinstance(body.get("note"), str) else None
    updated = repo.set_category_override(h.app.db, p["id"], cats, note)
    h.app.scans._compute_relations()
    return {"project": updated}


@route("PATCH", "/api/projects/(?P<id>[0-9a-f]{16})")
def patch_project(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    if "description" in body:
        desc = body.get("description")
        if desc is not None and not isinstance(desc, str):
            raise ApiError(400, "description must be a string")
        repo.set_description_override(h.app.db, p["id"], desc)
    return {"project": repo.get_project(h.app.db, p["id"])}


@route("POST", "/api/projects/(?P<id>[0-9a-f]{16})/rescan")
def rescan_project(h: "Handler", p: dict[str, str], _b: dict[str, Any]) -> Any:
    project = _project_or_404(h.app, p["id"])
    if project.get("removed_at"):
        raise ApiError(409, "project is marked missing; rescan the workspace instead")
    updated = h.app.scans.rescan_project(project)
    if not updated:
        raise ApiError(409, "project folder is not accessible")
    return {"project": updated}


@route("DELETE", "/api/projects/(?P<id>[0-9a-f]{16})")
def forget_project(h: "Handler", p: dict[str, str], _q: dict[str, Any]) -> Any:
    project = _project_or_404(h.app, p["id"], details=False)
    if not project.get("removed_at"):
        raise ApiError(409, "only projects marked as missing can be forgotten")
    repo.forget_project(h.app.db, p["id"])
    return {"ok": True}


@route("POST", "/api/projects/(?P<id>[0-9a-f]{16})/open")
def open_project(h: "Handler", p: dict[str, str], _b: dict[str, Any]) -> Any:
    project = _project_or_404(h.app, p["id"], details=False)
    ws = repo.get_workspace(h.app.db, project["workspace_id"])
    if not ws:
        raise ApiError(404, "workspace not found")
    target = Path(ws["root_path"]) / project["relative_path"]
    if not target.is_dir() or not is_within(target, ws["root_path"]):
        raise ApiError(409, "folder is not accessible")
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(target)])  # noqa: S603,S607
    except OSError as exc:
        raise ApiError(500, f"could not open folder: {exc}") from exc
    return {"ok": True}


@route("GET", "/api/projects/(?P<id>[0-9a-f]{16})/ai-preview")
def ai_preview(h: "Handler", p: dict[str, str], q: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    fields = [f for f in str(q.get("fields") or "").split(",") if f] or None
    try:
        return h.app.ai.preview(p["id"], fields)
    except ai_module.AIError as exc:
        raise ApiError(400, exc.message, kind=exc.kind) from exc


@route("POST", "/api/projects/(?P<id>[0-9a-f]{16})/ai-suggestion")
def ai_suggestion(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    _project_or_404(h.app, p["id"], details=False)
    fields = body.get("fields")
    if fields is not None and (not isinstance(fields, list) or not all(isinstance(f, str) for f in fields)):
        raise ApiError(400, "fields must be a list of strings")
    if not body.get("consent"):
        raise ApiError(400, "explicit consent flag required for every AI request", kind="consent")
    try:
        return {"suggestion": h.app.ai.suggest(p["id"], fields, force=bool(body.get("force")))}
    except ai_module.AIError as exc:
        status = {"disabled": 409, "unreachable": 503, "timeout": 504, "invalid": 502, "busy": 429}.get(exc.kind, 500)
        raise ApiError(status, exc.message, kind=exc.kind) from exc


@route("GET", "/api/ai/status")
def ai_status(h: "Handler", _p: dict[str, str], _q: dict[str, Any]) -> Any:
    return h.app.ai.status()


@route("GET", "/api/ai/suggestions")
def ai_suggestions(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    items = repo.list_ai_suggestions(h.app.db, None, q.get("status") or None, _int(q, "limit", 100, 1, 500))
    names = {r["id"]: r["display_name"] for r in h.app.db.all("SELECT id, display_name FROM projects")}
    for s in items:
        s["project_name"] = names.get(s["project_id"])
    return {"items": items}


@route("POST", "/api/ai/suggestions/(?P<id>[0-9a-f]{16})/(?P<action>accept|reject)")
def ai_resolve(h: "Handler", p: dict[str, str], body: dict[str, Any]) -> Any:
    try:
        result = h.app.ai.resolve(p["id"], p["action"], apply_description=bool(body.get("apply_description", True)))
    except ai_module.AIError as exc:
        raise ApiError(404 if "not found" in exc.message else 400, exc.message, kind=exc.kind) from exc
    h.app.scans._compute_relations()
    return {"suggestion": result, "project": repo.get_project(h.app.db, result["project_id"])}


@route("GET", "/api/graph")
def graph(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    return knowledge_graph(h.app.db, q.get("workspace") or None, _int(q, "min_shared", 1, 1, 50))


@route("GET", "/api/relations")
def relations(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    pid = q.get("project")
    if pid and not ID_RE.match(pid):
        raise ApiError(400, "invalid id")
    return {"items": repo.list_relations(h.app.db, pid or None)}


@route("POST", "/api/relations")
def add_relation(h: "Handler", _p: dict[str, str], body: dict[str, Any]) -> Any:
    source, target = body.get("source"), body.get("target")
    if not (isinstance(source, str) and isinstance(target, str) and ID_RE.match(source) and ID_RE.match(target)) or source == target:
        raise ApiError(400, "source and target must be two different project ids")
    _project_or_404(h.app, source, False)
    _project_or_404(h.app, target, False)
    repo.add_manual_relation(h.app.db, source, target, str(body.get("note") or "manual link"))
    return {"ok": True}


@route("DELETE", "/api/relations")
def delete_relation(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    source, target = q.get("source"), q.get("target")
    if not (isinstance(source, str) and isinstance(target, str) and ID_RE.match(source) and ID_RE.match(target)):
        raise ApiError(400, "invalid ids")
    return {"ok": repo.delete_manual_relation(h.app.db, source, target)}


@route("GET", "/api/stats")
def stats(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    return repo.stats(h.app.db, q.get("workspace") or None)


@route("GET", "/api/settings")
def get_settings(h: "Handler", _p: dict[str, str], _q: dict[str, Any]) -> Any:
    return {"settings": h.app.settings.get(), "path": str(h.app.settings.path) if h.app.settings.path else None}


@route("PATCH", "/api/settings")
def patch_settings(h: "Handler", _p: dict[str, str], body: dict[str, Any]) -> Any:
    before = h.app.settings.section("scan").get("mode")
    rescan = bool(body.pop("rescan", True))   # request option, not a setting
    try:
        updated = h.app.settings.update(body)
    except SettingsError as exc:
        raise ApiError(400, str(exc)) from exc
    # Switching detection mode changes what a scan records; rescan so the UI never shows a mix.
    rescanned = []
    if updated["scan"].get("mode") != before and rescan:
        for ws in repo.list_workspaces(h.app.db):
            if Path(ws["root_path"]).is_dir():
                rescanned.append(h.app.scans.start(ws, incremental=True).to_dict())
    return {"settings": updated, "rescans": rescanned}


@route("POST", "/api/system/pick-folder")
def pick_folder(h: "Handler", _p: dict[str, str], _b: dict[str, Any]) -> Any:
    return picker.pick_folder()


@route("GET", "/api/system/browse")
def browse(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    return picker.browse(q.get("path") or None)


@route("GET", "/api/export")
def export(h: "Handler", _p: dict[str, str], q: dict[str, Any]) -> Any:
    anonymize = q.get("anonymize", "1") != "0"
    workspaces = repo.list_workspaces(h.app.db)
    items, _ = repo.list_projects(h.app.db, include_missing=True)
    for ws in workspaces:
        ws["root_path"] = display_path(ws["root_path"], anonymize)
        ws.pop("last_run", None)
    for p in items:
        p.pop("fingerprint", None)
    return {"exported_at": int(time.time()), "version": __version__, "anonymized": anonymize, "workspaces": workspaces, "projects": items,
            "relations": repo.list_relations(h.app.db), "settings": h.app.settings.get()}


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ProjectNexus/" + __version__
    sys_version = ""
    app: App  # set on the server class

    # -- helpers ----------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default; errors go through log_error
        if self.app.settings.section("privacy").get("log_full_paths"):
            self.app.log("%s - %s" % (self.address_string(), fmt % args))

    def log_error(self, fmt: str, *args: Any) -> None:
        self.app.log("http error: " + (fmt % args))

    def _send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")

    def _check_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        return host in self.app.allowed_hosts

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            netloc = (parsed.netloc or "").lower()
            if netloc not in self.app.allowed_hosts:
                return False
        fetch_site = (self.headers.get("Sec-Fetch-Site") or "").lower()
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            return False
        return True

    def _authorized(self) -> bool:
        token = self.headers.get("X-Nexus-Token") or ""
        return secrets.compare_digest(token, self.app.token)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_BODY:
            raise ApiError(413, "request body too large")
        if length == 0:
            return {}
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise ApiError(415, "Content-Type must be application/json")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid JSON body") from None
        if not isinstance(data, dict):
            raise ApiError(400, "JSON body must be an object")
        return data

    # -- dispatch ---------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not self._check_host():
            return self._send_json(421, {"error": "invalid Host header"})
        if path.startswith("/api/"):
            return self._api(method, path, parsed.query)
        if method not in {"GET", "HEAD"}:
            return self._send_json(405, {"error": "method not allowed"})
        return self._static(path)

    def _api(self, method: str, path: str, query: str) -> None:
        try:
            if not self._origin_ok():
                raise ApiError(403, "cross-origin requests are not allowed")
            if method in {"POST", "PATCH", "DELETE", "PUT"} and not self._authorized():
                raise ApiError(403, "missing or invalid local session token", code="token")
            for route_method, pattern, fn in ROUTES:
                if route_method != method:
                    continue
                match = pattern.match(path)
                if not match:
                    continue
                params = {k: v for k, v in parse_qs(query, keep_blank_values=True).items()}
                flat = {k: v[0] for k, v in params.items()}
                if method in {"POST", "PATCH", "PUT"}:
                    body = self._read_body()
                    result = fn(self, match.groupdict(), body)
                else:
                    result = fn(self, match.groupdict(), flat)
                return self._send_json(200, result)
            if method == "HEAD":
                return self._send_json(405, {"error": "method not allowed"})
            raise ApiError(404, "not found")
        except ApiError as exc:
            return self._send_json(exc.status, {"error": exc.message, **exc.extra})
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as exc:  # noqa: BLE001
            self.app.log("unhandled API error: " + traceback.format_exc())
            return self._send_json(500, {"error": f"internal error: {type(exc).__name__}"})

    def _static(self, path: str) -> None:
        if path in {"/", "/index.html"} or (not path.startswith("/static/") and "." not in path.rsplit("/", 1)[-1]):
            body = self.app.index_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; "
                "connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
            )
            self._security_headers()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        rel = path[len("/static/"):] if path.startswith("/static/") else path.lstrip("/")
        if not rel or any(part in {"", ".", ".."} or part.startswith(".") for part in rel.split("/")):
            return self._send_json(404, {"error": "not found"})
        target = (self.app.static_dir / rel).resolve()
        if not is_within(target, self.app.static_dir) or not target.is_file():
            return self._send_json(404, {"error": "not found"})
        ctype = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8", ".woff2": "font/woff2", ".ico": "image/x-icon",
                 ".png": "image/png", ".webmanifest": "application/manifest+json"}.get(target.suffix.lower()) or (mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        try:
            data = target.read_bytes()
        except OSError:
            return self._send_json(404, {"error": "not found"})
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self._security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch("HEAD")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        # No CORS pre-flight is ever granted.
        self._send_json(403, {"error": "cross-origin requests are not allowed"})


class NexusServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


class NexusServer6(NexusServer):
    address_family = socket.AF_INET6


def make_server(app: App) -> NexusServer:
    """Bind the primary (IPv4) server and finalise the app's port/host allow-list."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = NexusServer((app.host, app.port), handler)
    app.port = server.server_address[1]
    app.allowed_hosts = {f"{app.host}:{app.port}", app.host}
    if app.host in {"127.0.0.1", "localhost", "::1"}:
        app.allowed_hosts |= {f"127.0.0.1:{app.port}", f"localhost:{app.port}", f"[::1]:{app.port}"}
    (app.data_dir / "session.json").write_text(json.dumps({"token": app.token, "port": app.port, "host": app.host, "pid": os.getpid()}), encoding="utf-8")
    return server


def make_servers(app: App) -> list[NexusServer]:
    """Primary IPv4 server plus, for loopback hosts, an IPv6 twin on ::1 so that
    http://localhost:PORT works whichever address the browser resolves first."""
    servers = [make_server(app)]
    if app.host in {"127.0.0.1", "localhost"}:
        try:
            handler = type("BoundHandler6", (Handler,), {"app": app})
            servers.append(NexusServer6(("::1", app.port), handler))
        except OSError as exc:
            app.log(f"IPv6 loopback not available ({exc}); serving IPv4 only")
    return servers


def serve_in_thread(app: App) -> tuple[list[NexusServer], list[threading.Thread]]:
    servers = make_servers(app)
    threads = []
    for i, server in enumerate(servers):
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, name=f"nexus-http-{i}", daemon=True)
        thread.start()
        threads.append(thread)
    return servers, threads
