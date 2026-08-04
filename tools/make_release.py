"""Assemble the shippable Giltgrave folder (and zip) from a PyInstaller build.

    backend\\venv\\Scripts\\pyinstaller Giltgrave.spec --noconfirm
    backend\\venv\\Scripts\\python tools\\make_release.py

Produces release/Giltgrave/ and release/Giltgrave-<stamp>.zip — upload the zip
to GitHub Releases. Do NOT ship the repo zip: .git is 2.2GB, and the working
tree carries ~3.2GB of curation art nobody playing needs.

Layout produced:

    Giltgrave/
      Giltgrave.exe              the launcher
      _internal/             PyInstaller runtime + deps   \\  replaced on update
      backend/               game code + static art + saves/  <- saves KEPT
      frontend/dist/         built UI
      assets/icon.ico
      generation/comfy_nodes/  the toe_rembg node INSTALL_GENERATION.bat copies
      INSTALL_GENERATION.bat
      README_FIRST.txt

Which files count as "game code" is decided by `git ls-files`, not by a
hand-maintained exclude list. That's deliberate: git already knows the curated
ship set (it's what a repo download gets today), and it means backend/.env —
which holds a real API key — cannot be shipped by accident, because it's
gitignored.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(ROOT, "dist", "Giltgrave")     # PyInstaller onedir output
RELEASE_DIR = os.path.join(ROOT, "release")
STAGE_DIR = os.path.join(RELEASE_DIR, "Giltgrave")

# Copied wholesale from the working tree. frontend/dist is build output (we
# want what was just built, not what git has). comfy_nodes is untracked but
# tiny, and INSTALL_GENERATION.bat copies it into the player's ComfyUI — note
# the sibling generation/loras/ is deliberately NOT here: the installer pulls
# those from GitHub LFS at ~450MB rather than riding along in every download.
WHOLESALE = [
    ("frontend/dist", "frontend/dist"),
    ("generation/comfy_nodes", "generation/comfy_nodes"),
]
# Filtered through `git ls-files` so gitignored junk (venv, saves, .env,
# __pycache__, db_backups) can never leak into a release. Only backend/ needs
# this treatment — it's the one tree with secrets and player state in it.
# assets/icon.ico isn't copied at all: the spec bundles it into _internal/,
# where resource_path() finds it via sys._MEIPASS.
FROM_GIT = ["backend"]
LOOSE_FILES = ["INSTALL_GENERATION.bat"]

README_FIRST = """EVERSPIRE — playtest build
==========================

TO PLAY
-------
Double-click Giltgrave.exe.

Windows will probably show a blue "Windows protected your PC" box, because
this build isn't code-signed (a signing certificate costs a few hundred
dollars a year and this is a playtest). Click "More info", then
"Run anyway". You only have to do this once.

First launch takes a few seconds longer than the rest — it's setting up your
save. Then make an account at the title screen. PLEASE USE A THROWAWAY
PASSWORD, not one you use anywhere else. Multiplayer connects on its own.


OPTIONAL — BETTER TEXT (hero names, backstories, banter)
--------------------------------------------------------
The game writes its heroes with Claude. Without a key you still get every
hero, every fight, every system — just from a pool of pre-written text
instead of writing for your specific hero.

To turn it on: get an API key at console.anthropic.com (needs a few dollars
of credit), then paste it into Settings -> AI. It's stored on your machine
only and never sent anywhere except Anthropic.


OPTIONAL — YOUR OWN UNIQUE HERO ART (needs an NVIDIA GPU)
----------------------------------------------------------
Out of the box everyone shares the same art. If you have an NVIDIA card and
~12GB of free disk, you can generate heroes nobody else will ever have.

Go to Settings -> AI and switch ON "Hero Portrait Generation". The game
downloads everything it needs (~9.2GB) by itself — you don't have to install
anything. It's resume-safe, so closing the laptop mid-download is fine; it
picks up where it stopped.

The generator then starts and stops with the game. No NVIDIA GPU? Skip this
entirely — nothing else changes, and none of that 9.2GB is downloaded.

(INSTALL_GENERATION.bat does the same thing from outside the game, if you'd
rather run it yourself. You don't need both.)


UPDATING TO A NEWER BUILD
--------------------------
Your saves live in backend\\saves\\ and your generated art in
backend\\static\\portraits\\. To update, extract the new version over the top
of this folder and keep those two — everything else can be replaced.


TROUBLESHOOTING
---------------
"Game files not found"      You ran the exe without extracting the zip first.
                            Extract the whole folder, then run it.
Window opens blank/white    Give it a moment on first launch. If it persists,
                            close it and reopen.
Nothing happens at all      Another copy may already be running — check the
                            taskbar, and Task Manager for Giltgrave.exe.
Generated heroes have       The cutout step didn't finish installing. Settings
ragged/blocky backgrounds   -> AI will say so; turn "Hero Portrait Generation"
                            off and on again to retry just that part.

Found a bug? Tell Liam what you were doing when it happened. Heroes dying is
not a bug, it is the entire point.
"""


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def git_files(path):
    """Tracked files under `path`, repo-relative with forward slashes."""
    result = run(["git", "ls-files", "-z", "--", path])
    if result.returncode != 0:
        sys.exit(f"git ls-files failed for {path!r}:\n{result.stderr}")
    return [p for p in result.stdout.split("\0") if p]


def copy_tree(src, dst):
    if not os.path.isdir(src):
        sys.exit(f"Missing required folder: {src}")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(len(files) for _, _, files in os.walk(dst))


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def dir_size(path):
    return sum(os.path.getsize(os.path.join(r, f))
               for r, _, fs in os.walk(path) for f in fs)


def check_clean():
    """Refuse to ship a stage dir that's been played in.

    The natural workflow is stage -> launch it to smoke-test -> zip, and that
    middle step writes a save DB, an .active_profile pointer, and a WebView2
    profile into the stage. Zipping then hands every player someone else's
    roster and a browser profile. Staging from scratch clears all of it, so
    this only has to catch the case where you skipped that.
    """
    dirty = []
    saves = os.path.join(STAGE_DIR, "backend", "saves")
    if os.path.isdir(saves) and os.listdir(saves):
        dirty.append(f"backend/saves/ is not empty: {sorted(os.listdir(saves))}")
    if os.path.isdir(os.path.join(STAGE_DIR, "webview_data")):
        dirty.append("webview_data/ present (a WebView2 profile from a test run)")
    if dirty:
        sys.exit("REFUSING TO PACKAGE — the stage dir has been run:\n  "
                 + "\n  ".join(dirty)
                 + "\n\nRe-run this script (without --no-zip) to rebuild it clean.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true",
                    help="assemble the folder but skip the (slow) zip step")
    ap.add_argument("--tag", default="playtest",
                    help="suffix for the zip filename (default: playtest)")
    args = ap.parse_args()

    # ── preflight ───────────────────────────────────────────────────────────
    exe = os.path.join(BUILD_DIR, "Giltgrave.exe")
    if not os.path.isfile(exe):
        sys.exit(f"No PyInstaller build at {exe}\n"
                 f"Run:  backend\\venv\\Scripts\\pyinstaller Giltgrave.spec --noconfirm")
    if not os.path.isfile(os.path.join(ROOT, "frontend", "dist", "index.html")):
        sys.exit("frontend/dist/index.html missing — run `npm run build` in frontend/ first.")

    if os.path.isdir(STAGE_DIR):
        print(f"Clearing {STAGE_DIR}")
        shutil.rmtree(STAGE_DIR)
    os.makedirs(STAGE_DIR, exist_ok=True)

    # ── 1. the frozen runtime (exe + _internal) ─────────────────────────────
    n = copy_tree(BUILD_DIR, STAGE_DIR)
    print(f"  runtime            {n:>5} files")

    # ── 2. build output copied as-is ────────────────────────────────────────
    for src_rel, dst_rel in WHOLESALE:
        n = copy_tree(os.path.join(ROOT, src_rel), os.path.join(STAGE_DIR, dst_rel))
        print(f"  {src_rel:<18} {n:>5} files")

    # ── 3. source + curated art, filtered through git ───────────────────────
    for path in FROM_GIT:
        files = git_files(path)
        if not files:
            sys.exit(f"git tracks no files under {path!r} — is the repo intact?")
        for rel in files:
            src = os.path.join(ROOT, rel)
            if not os.path.isfile(src):      # tracked but deleted locally
                continue
            dst = os.path.join(STAGE_DIR, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        print(f"  {path:<18} {len(files):>5} files")

    for name in LOOSE_FILES:
        shutil.copy2(os.path.join(ROOT, name), os.path.join(STAGE_DIR, name))

    # An empty saves/ so the backend never has to guess whether it may create
    # one inside a folder the player might have dropped somewhere read-only.
    os.makedirs(os.path.join(STAGE_DIR, "backend", "saves"), exist_ok=True)

    with open(os.path.join(STAGE_DIR, "README_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(README_FIRST)

    # ── 4. guard: never ship secrets ────────────────────────────────────────
    leaked = [p for p in ("backend/.env", "deploy/RUNBOOK.local.md")
              if os.path.exists(os.path.join(STAGE_DIR, p.replace("/", os.sep)))]
    if leaked:
        sys.exit(f"REFUSING TO PACKAGE — secrets present in the stage dir: {leaked}")

    check_clean()

    size = dir_size(STAGE_DIR)
    print(f"\nStaged {STAGE_DIR}  ({human(size)})")

    if args.no_zip:
        print("Skipping zip (--no-zip).")
        return

    # ── 5. zip ──────────────────────────────────────────────────────────────
    # compresslevel=1: the payload is mostly PNG/OGG, which are already
    # compressed and will not shrink no matter how long we spend on them. Level
    # 1 still meaningfully shrinks the .py/.js/.dll side at a fraction of the
    # wall time — level 9 on ~900MB is a coffee break for a few extra MB.
    zip_path = os.path.join(RELEASE_DIR, f"Giltgrave-{args.tag}.zip")
    print(f"Zipping -> {zip_path} (this takes a few minutes)")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for root, _, files in os.walk(STAGE_DIR):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.join("Giltgrave", os.path.relpath(full, STAGE_DIR)))

    print(f"\nDone.  {zip_path}  ({human(os.path.getsize(zip_path))})")
    print("Upload that to GitHub Releases — it's over the 100MB limit for repo files,")
    print("but Releases allows up to 2GB per asset.")


if __name__ == "__main__":
    main()
