"""Acceptance criterion 9: 200+ projects stay usable. Records timings to tests/perf_report.json."""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fixtures"))
from conftest import wait_run  # noqa: E402
from make_fixture import build, remove_tree  # noqa: E402

from nexus import repo  # noqa: E402
from nexus.db import Database  # noqa: E402
from nexus.relations import knowledge_graph  # noqa: E402
from nexus.scanner import ScanManager  # noqa: E402
from nexus.settings import Settings  # noqa: E402

BIG = 240


@pytest.mark.slow
def test_scan_and_query_240_projects(tmp_path_factory):
    base = tmp_path_factory.mktemp("perf")
    root = base / "ws"
    build(root, big=BIG, use_git=False)
    try:
        db = Database(base / "nexus.db")
        settings = Settings(base / "settings.json")
        manager = ScanManager(db, settings)
        ws = repo.add_workspace(db, str(root))
        t0 = time.perf_counter()
        run = manager.start(ws)
        wait_run(run, timeout=600)
        full = time.perf_counter() - t0
        assert run.status == "completed" and run.counts["discovered"] >= BIG
        t1 = time.perf_counter()
        items, total = repo.list_projects(db)
        list_ms = (time.perf_counter() - t1) * 1000
        assert total >= BIG
        t2 = time.perf_counter()
        graph = knowledge_graph(db)
        graph_ms = (time.perf_counter() - t2) * 1000
        t3 = time.perf_counter()
        run2 = manager.start(ws)
        wait_run(run2, timeout=600)
        incremental = time.perf_counter() - t3
        assert run2.counts["cached"] >= BIG
        report = {
            "projects": total, "files": run.counts["files"], "full_scan_seconds": round(full, 2), "incremental_scan_seconds": round(incremental, 2),
            "list_projects_ms": round(list_ms, 1), "knowledge_graph_ms": round(graph_ms, 1), "graph_nodes": len(graph["nodes"]), "graph_edges": len(graph["edges"]),
            "python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
        }
        (Path(__file__).parent / "perf_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        assert full < 300 and incremental < full
        assert list_ms < 5000
        db.close()
    finally:
        remove_tree(root)
