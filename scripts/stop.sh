#!/usr/bin/env bash
# Stop the Project Nexus server (macOS / Linux).
PORT="${PORT:-8765}"
if command -v lsof >/dev/null; then PIDS=$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN); else PIDS=$(fuser "$PORT"/tcp 2>/dev/null); fi
if [ -z "$PIDS" ]; then echo "Nothing is listening on port $PORT."; exit 0; fi
kill $PIDS && echo "Stopped pid(s) $PIDS on port $PORT."
