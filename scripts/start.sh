#!/usr/bin/env bash
# Start Project Nexus in the background on http://localhost:8765 (macOS / Linux).
#   bash scripts/start.sh [--add ~/projects]
cd "$(dirname "$0")/.."
PORT="${PORT:-8765}"
nohup python3 -m nexus --port "$PORT" --no-browser "$@" > "${TMPDIR:-/tmp}/project-nexus.out" 2>&1 &
echo $! > "${TMPDIR:-/tmp}/project-nexus.pid"
sleep 2
echo "Project Nexus: http://localhost:$PORT/  (pid $(cat "${TMPDIR:-/tmp}/project-nexus.pid"))"
