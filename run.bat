@echo off
rem Double-click launcher for Windows (runs from source; needs Python 3.11+ on PATH).
cd /d "%~dp0"
python -m nexus %*
if errorlevel 1 pause
