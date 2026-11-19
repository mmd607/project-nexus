#!/usr/bin/env bash
# Run from source (macOS / Linux): bash scripts/run.sh [--add ~/projects]
cd "$(dirname "$0")/.."
exec python3 -m nexus "$@"
