# Run from source (Windows): powershell -ExecutionPolicy Bypass -File scripts\run.ps1 [--add "D:\Projects"]
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m nexus @args
