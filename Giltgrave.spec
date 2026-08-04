# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the shippable Giltgrave build.

Deliberately a ONEDIR build that contains only the Python runtime and
third-party deps — no game content. backend/ and frontend/dist/ ship
*alongside* the exe (see tools/make_release.py), which is what lets an update
replace the exe and _internal/ without touching a player's saves or their
generated portraits.

Because the backend is loaded as loose .py files at runtime rather than being
frozen, PyInstaller's import analysis never sees fastapi/uvicorn/anthropic/etc.
Everything the backend imports has to be declared here by hand — if the
packaged build dies with ModuleNotFoundError, this list is the place to fix it.

Build with:  backend\\venv\\Scripts\\pyinstaller Giltgrave.spec --noconfirm
Then run:    backend\\venv\\Scripts\\python tools\\make_release.py
"""

from PyInstaller.utils.hooks import collect_submodules

# Whole packages, not bare names. Listing 'fastapi' alone pulls in the
# top-level package and nothing else, so `from fastapi.middleware.cors import
# CORSMiddleware` in backend/main.py died at runtime with ModuleNotFoundError —
# PyInstaller can't see it because the backend isn't part of the frozen graph.
# Anything the backend imports a SUBMODULE of has to be collected wholesale.
_COLLECT = [
    'fastapi',      # .middleware.cors, .staticfiles, .responses
    'starlette',    # fastapi's engine; same submodule-by-string problem
    'uvicorn',      # resolves loops/protocols/lifespan by string at runtime
    'anthropic',    # lazy __getattr__ submodule loading
    'pydantic',
]

hiddenimports = [
    *[m for pkg in _COLLECT for m in collect_submodules(pkg)],
    # ── http ──
    'pydantic_core', 'httpx', 'httpcore', 'anyio', 'sniffio', 'h11',
    'certifi', 'idna', 'dotenv',
    # requests is a top-level import in services/comfy_service.py — every
    # ComfyUI health check and job submission goes through it.
    'requests', 'urllib3', 'charset_normalizer',
    # ── imaging: card composition + portrait cutouts ──
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'PIL.ImageFilter',
    'numpy',
    # scipy.ndimage drives the void-mask cutout. Technically optional (there's
    # a dependency-free flood fallback) but this build's whole audience has an
    # NVIDIA GPU and will turn generation on, so the good path ships.
    'scipy', 'scipy.ndimage',
    # ── the window ──
    'webview',
    # ── stdlib bits reached indirectly ──
    'sqlite3', 'email.mime.text',
]

# rembg/onnxruntime are intentionally NOT bundled — ~200MB on every download
# for a path most players never reach. Cutouts run inside the player's ComfyUI,
# which has its own python and gets rembg from the installer; the toe_rembg
# custom node there runs the canonical algorithm
# (generation/comfy_nodes/toe_rembg/cutout.py) and the portrait arrives already
# transparent, so the backend does nothing.
#
# When that node is missing, the backend ladder takes over WITHOUT rembg:
# make_game_cutout (numpy + scipy, both bundled above) then the dependency-free
# border flood. Both are a step down — the flood in particular hollows out dark
# costumes and must never be the primary path again (see cutout.py). Bundling
# rembg would let the backend run the good algorithm itself; it is not worth
# 200MB while the node covers the normal case.
excludes = [
    'rembg', 'onnxruntime', 'torch', 'torchvision', 'transformers',
    'matplotlib', 'pandas', 'tkinter', 'pytest',
]

a = Analysis(
    ['app_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],  # needed at runtime for the window/taskbar icon
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir — binaries go to COLLECT below
    name='Giltgrave',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX off on purpose. A UPX-packed PyInstaller exe is one of the strongest
    # heuristic signals antivirus engines have for "packed malware", and this
    # build is already unsigned. Compression saves ~20MB on a ~900MB download —
    # not worth a false positive quarantining a friend's game.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # master: assets/brand/Giltgrave_Icon.png (see assets/brand/README.md)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Giltgrave',
)
