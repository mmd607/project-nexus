Set-Location (Split-Path $PSScriptRoot -Parent)
python -X utf8 -m pytest tests -q
node --test tests/js/universe.test.mjs
