# Rename hazards — what still says "Everspire", and why

> **Update 2026-08-04 (later the same day): the game is now GILTGRAVE.**
> "Kleos" was live for only a few hours and was dropped after a name sweep
> (crowded namespace: a live board game, a Wolters Kluwer EU software mark,
> and both game domains sniped by strangers weeks earlier). Every *Kleos*
> string has been swept to *Giltgrave*. This document is deliberately left in
> its original wording because **every hazard below is an `Everspire` string,
> and all of them are still live and still must not be changed casually.**
> Read "Kleos" below as "Giltgrave".

*Written 2026-08-04, when the game was renamed **Everspire → Kleos**.*

The rename is done for everything a player sees. What's left is a short list of
strings that look like the old name but are actually **external contracts** —
identifiers shared with GitHub, with users' disks, or with this machine.
Changing one of these in isolation breaks something real.

Each entry says what breaks, and what you'd have to do *at the same time* to
change it safely.

---

## 1. LoRA model filenames — `Everspire_*_v1.safetensors`

**Where:** `backend/services/generation_installer.py`,
`backend/services/portrait_cache.py`, `INSTALL_GENERATION.bat`,
`tools/build_base_pool.py`, `tools/regen_monsters.py`,
`tools/regen_zone_floors.py`, `tools/build_floor_library.py`,
`tools/build_zone_library.py`, `tools/gen_equipment_sample.py`

Five files: `Everspire_{Heroes,Monsters,Env,Equipment,Floors}_v1.safetensors`.

**Why it can't just be edited:** these are the *real filenames* of ~450 MB of
model weights, (a) stored in GitHub LFS under `generation/loras/`, and (b)
already downloaded onto the disk of anyone who has run generation. The strings
in code are lookup keys passed to ComfyUI. Renaming the string without renaming
the file means generation silently fails to find its adapters.

**To change safely, all in one go:**
1. Rename the five files in `generation/loras/` and commit through LFS.
2. Update every path above.
3. Ship a migration that renames existing files in
   `~/Everspire-Generation/ComfyUI_windows_portable/ComfyUI/models/loras/`,
   or accept that existing installs re-download 450 MB.

**Recommendation:** leave them. They're invisible to players, and the cost of
renaming is a large re-download for every existing user. Name the *next*
generation `Kleos_Heroes_v2` and let the old names die out naturally.

---

## 2. GitHub repo URL — RESOLVED 2026-08-05

The repo is now **`github.com/SageHargrove/Giltgrave`**. Liam renamed it on
GitHub; the old URL 301-redirects. The remote and all four code references
(`arena_server/main.py`, the landing page's "All versions" link,
`backend/services/generation_installer.py`, `INSTALL_GENERATION.bat`) were
updated the same day, plus `deploy/LANDING.md` and
`deploy/lora-distribution.local.md`.

This was safe to do precisely because **no release had ever been published** —
the LFS-media and release-download URLs that GitHub does *not* reliably
redirect had no consumers yet. The original warning is kept below.

### original note — `github.com/SageHargrove/Everspire`

**Where:** `arena_server/main.py` (`RELEASES_BASE`),
`arena_server/landing/index.html` ("All versions" link),
`backend/services/generation_installer.py` (LFS media URLs),
`INSTALL_GENERATION.bat` (LFS media URLs)

**Why:** it's the actual remote. Editing the string just points at a 404.

**To change safely:** rename the repo on GitHub *first* (GitHub keeps a
redirect for the web UI, but **LFS media URLs and release download links are
not reliably redirected**), then update all four places, then cut a fresh
release so the download button resolves.

---

## 3. Generation install directory — `~/Everspire-Generation`

**Where:** `backend/services/generation_installer.py` (`GEN_DIR`),
`backend/services/comfy_service.py` (ComfyUI discovery path)

**Why:** this is a real folder on users' machines holding ComfyUI plus the
models. Renaming the constant orphans every existing install — the game stops
finding ComfyUI and offers a fresh ~10 GB download.

**To change safely:** add a migration that renames the folder on first run if
the old one exists, and keep the old path in the discovery list as a fallback
for at least one release.

---

## 4. Filesystem paths — `C:\Everspire\...`

**Where:** `chatgpt-lora/*.py`, `chatgpt-lora/*.sh`, `noobai-test/*.py`,
`deploy/lora-distribution.local.md`, and various tool scripts

**Why:** these are absolute paths to the repo root on this machine. The folder
is still literally named `C:\Everspire`.

**To change:** renaming the root folder is its own operation —
1. Close VS Code and any running server/exe (Windows locks the folder).
2. Rename `C:\Everspire` → `C:\Kleos`.
3. Update the VS Code workspace, then find/replace the paths in the files above.
4. Re-point any Desktop shortcuts.

Nothing in the shipped game depends on this; it's purely local tooling.

---

## 5. Release assets — the first Kleos release must exist

**Where:** `arena_server/main.py` — `SETUP_ASSET = "Kleos-Setup.exe"`,
`SETUP_ASSET_GPU = "Kleos-Setup-GPU.exe"`

**Status:** already renamed, and `tools/make_release.py` + `tools/kleos.iss`
now produce those names. But **any existing GitHub release still has the
Everspire-named asset**, so the landing page's Download button won't resolve
directly until a Kleos release is published. It degrades gracefully (falls back
to the releases page) rather than dead-ending.

**Action:** publish one release built from `Kleos.spec` and it's resolved.

---

## 6. Save files and profiles

`backend/saves/*.db` are named after the **profile**, not the game
(`Snair.db`), so the rename doesn't touch them. Nothing to do.

The installer's uninstall message points at the save location — already
updated in `tools/kleos.iss`.

---

## Already done (for reference)

Renamed everywhere: window title + single-instance mutex, both FastAPI service
titles, the frontend (tab title, wordmark, both title screens, PRE-ALPHA
chips, background watermark), the landing page (title, og:title, wordmarks,
body copy, legal), `Kleos.spec`, `tools/kleos.iss`, `tools/make_release.py`,
batch-file headers, and the docs.

Icon: `assets/icon.ico` is the Kleos mark; the old one is kept as
`assets/icon.everspire-backup.ico`. The exe was rebuilt as `dist/Kleos/Kleos.exe`
(plus a copy at the repo root, `Kleos.exe`).

**Windows may still show the old icon** for a pinned/cached shortcut. That's the
icon cache, not the build — clear it by deleting `%LOCALAPPDATA%\IconCache.db`
and the `%LOCALAPPDATA%\Microsoft\Windows\Explorer\iconcache_*.db` files, then
restarting Explorer. Re-pin the taskbar shortcut to `Kleos.exe`.
