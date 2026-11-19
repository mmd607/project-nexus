@echo off
rem Stop Project Nexus (Windows double-click).
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
pause
