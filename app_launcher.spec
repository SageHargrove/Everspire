# -*- mode: python ; coding: utf-8 -*-
"""SUPERSEDED — do not build with this spec.

`hiddenimports` below is EMPTY, and the backend is loaded as loose .py files
at runtime, so PyInstaller's analysis never sees fastapi/uvicorn/PIL/etc.
A build from this spec launches and then dies with:

    ModuleNotFoundError: No module named 'fastapi'

(Confirmed 2026-08-04 by building it and running the result.)

Use **Giltgrave.spec** instead — it declares every backend dependency by hand and
is the shippable onedir build:

    backend\\venv\\Scripts\\pyinstaller Giltgrave.spec --noconfirm
    backend\\venv\\Scripts\\python tools\\make_release.py

For day-to-day development just run PLAY.bat; it serves the game from
backend/venv on http://localhost:8000 and needs no exe at all.

Kept only so an older build command doesn't error out on a missing file.
"""


a = Analysis(
    ['app_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],  # needed at runtime for the window/taskbar icon
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='app_launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # regenerate with: python tools/make_icon.py
)
