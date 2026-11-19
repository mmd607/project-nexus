#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -X utf8 -m pytest tests -q
node --test tests/js/universe.test.mjs
