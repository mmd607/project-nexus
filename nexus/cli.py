"""Command-line entry point: ``nexus`` / ``python -m nexus``."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import APP_NAME, __version__, repo
from .db import Database
from .paths import ensure_data_dir, static_dir
from .server import App, make_servers
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description=f"{APP_NAME} — local-first project universe")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1; anything else needs --allow-remote)")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (0 = random free port)")
    parser.add_argument("--data-dir", type=Path, default=None, help="where Nexus stores its own database/settings")
    parser.add_argument("--add", action="append", default=[], metavar="FOLDER", help="register a projects folder (repeatable)")
    parser.add_argument("--scan", action="store_true", help="start a scan of every registered workspace at launch")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    parser.add_argument("--desktop", action="store_true", help="open in a native window (requires the optional pywebview extra)")
    parser.add_argument("--allow-remote", action="store_true", help="acknowledge that binding to a non-loopback host exposes the UI on your network")
    parser.add_argument("--print-token", action="store_true", help="print the per-launch API token (for scripting)")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def setup_logging(data_dir: Path, quiet: bool) -> logging.Logger:
    logger = logging.getLogger("nexus")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(data_dir / "logs" / "nexus.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if not quiet:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        print("Refusing to bind to a non-loopback host without --allow-remote.", file=sys.stderr)
        return 2
    data_dir = ensure_data_dir(args.data_dir)
    logger = setup_logging(data_dir, args.quiet)
    settings = Settings(data_dir / "settings.json")
    db = Database(data_dir / "nexus.db")
    app = App(db, settings, static_dir(), data_dir, args.host, args.port, log=logger.info)

    for folder in args.add:
        try:
            resolved = Path(folder).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            logger.error("folder does not exist: %s", folder)
            continue
        ws = repo.add_workspace(db, str(resolved))
        logger.info("registered workspace %s", resolved)
        app.scans.start(ws)
    if args.scan or db.needs_rescan:
        if db.needs_rescan:
            logger.info("database upgraded to the folder-based project model; rescanning every workspace")
        for ws in repo.list_workspaces(db):
            if Path(ws["root_path"]).is_dir():
                app.scans.start(ws, incremental=not db.needs_rescan)

    servers = make_servers(app)
    url = f"http://{'127.0.0.1' if app.host in {'0.0.0.0', '::'} else app.host}:{app.port}/"
    logger.info("%s %s listening on %s (data: %s)", APP_NAME, __version__, url, data_dir)
    if args.print_token:
        print(app.token)
    print(f"{APP_NAME}: {url}  (also http://localhost:{app.port}/)" if app.host == "127.0.0.1" else f"{APP_NAME}: {url}")
    if app.host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: the UI is reachable from other machines on your network.", file=sys.stderr)

    stop = threading.Event()

    def shutdown(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, shutdown)
        except (ValueError, OSError):
            pass

    for index, server in enumerate(servers):
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, name=f"nexus-http-{index}", daemon=True).start()

    if args.desktop:
        try:
            import webview  # type: ignore
        except ImportError:
            logger.warning("pywebview not installed; falling back to the browser (pip install project-nexus[desktop])")
            args.desktop = False
        else:
            webview.create_window(APP_NAME, url, width=1440, height=920, min_size=(375, 600))
            webview.start()
            stop.set()
    if not args.desktop and not args.no_browser and settings.section("server").get("open_browser", True):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        while not stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    logger.info("shutting down")
    for server in servers:
        server.shutdown()
        server.server_close()
    db.close()
    return 0
