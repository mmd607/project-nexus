# Build a self-contained ProjectNexus folder (Windows). Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m pip install --upgrade pyinstaller | Out-Null
python -m PyInstaller packaging\nexus.spec --noconfirm --clean
Copy-Item README.md dist\ProjectNexus\README.md -Force
Copy-Item docs dist\ProjectNexus\docs -Recurse -Force
Set-Content -Path dist\ProjectNexus\Start-ProjectNexus.cmd -Value "@echo off`r`ncd /d %~dp0`r`nProjectNexus.exe %*" -Encoding ascii
Write-Host "Built dist\ProjectNexus\ProjectNexus.exe"
