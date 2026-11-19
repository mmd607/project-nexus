# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Project Nexus.

Build (from the repository root):
    python -m PyInstaller packaging/nexus.spec --noconfirm

Produces dist/ProjectNexus/ (one-folder build: fastest start-up, easy to inspect)
and, on Windows, dist/ProjectNexus/ProjectNexus.exe. Use scripts/build_exe.* which
also copy the launcher docs next to the binary.
"""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
STATIC = ROOT / "nexus" / "static"

datas = [(str(STATIC), os.path.join("nexus", "static"))]

hiddenimports = ["tkinter", "tkinter.filedialog"]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "PyInstaller", "numpy", "pandas", "matplotlib", "PIL", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProjectNexus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # keep a console: the URL and scan log are printed there; closing it stops the server
    icon=str(ROOT / "packaging" / "nexus.ico") if (ROOT / "packaging" / "nexus.ico").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ProjectNexus")
