"""One-click setup for local hero generation.

A Python port of INSTALL_GENERATION.bat that runs INSIDE the game, so turning
on "Hero Portrait Generation" in Settings is the only step a player takes. The
.bat stays for anyone who'd rather run it themselves, but nobody has to.

Everything is resume-safe (HTTP Range on every download) because this pulls
~9GB and a playtester on a laptop WILL close the lid halfway through. Re-running
picks up where it stopped rather than starting the 7GB checkpoint again.

Progress is polled by the frontend via /settings/generation/install-status
rather than pushed, so a disconnect or a page reload can't lose the install.
"""

import os
import shutil
import subprocess
import threading
import time

import requests

# ── where everything lands ──────────────────────────────────────────────────
GEN_DIR = os.path.join(os.path.expanduser("~"), "Everspire-Generation")
PORTABLE_DIR = os.path.join(GEN_DIR, "ComfyUI_windows_portable")
COMFY_DIR = os.path.join(PORTABLE_DIR, "ComfyUI")
EMBEDDED_PY = os.path.join(PORTABLE_DIR, "python_embeded", "python.exe")

COMFY_7Z_URL = ("https://github.com/comfyanonymous/ComfyUI/releases/latest/"
                "download/ComfyUI_windows_portable_nvidia.7z")
SEVENZR_URL = "https://7-zip.org/a/7zr.exe"
CHECKPOINT_URL = ("https://huggingface.co/Laxhar/noobai-XL-Vpred-1.0/resolve/main/"
                  "NoobAI-XL-Vpred-v1.0.safetensors")
CHECKPOINT_NAME = "noobaiXLNAIXL_vPred10Version.safetensors"
# MUST track the GitHub repo name. The 2026-07-30 rename to Everspire broke
# the old Tower-of-Eternity LFS path outright — it 404s, it does not redirect
# the way normal repo URLs do. Re-verify these two return 200 after any future
# rename, or every player's generation install fails at the LoRA step.
_LFS = "https://media.githubusercontent.com/media/SageHargrove/Giltgrave/main/generation/loras"
# The Everspire adapters replaced the manhwa-derived ToE_Heroes_Main on
# 2026-08-03. Env is included because facility art generation used ScenicILL,
# a third-party LoRA that was never in this list — so that feature failed
# silently for every player. Anything portrait_cache names as a LoRA must
# appear here or it only works on the dev machine.
LORAS = [
    (f"{_LFS}/Everspire_Heroes_v1.safetensors", "Everspire_Heroes_v1.safetensors"),
    (f"{_LFS}/Everspire_Monsters_v2.safetensors", "Everspire_Monsters_v2.safetensors"),
    (f"{_LFS}/Everspire_Env_v1.safetensors", "Everspire_Env_v1.safetensors"),
    # Equipment and Floors trained alongside the others but sat only on the dev
    # machine until 2026-08-04 — the exact failure the note above describes,
    # caught twice now. Equipment art and player-generated zones both render as
    # the base model without them, which looks like a style regression rather
    # than a missing file.
    (f"{_LFS}/Everspire_Equipment_v1.safetensors", "Everspire_Equipment_v1.safetensors"),
    (f"{_LFS}/Everspire_Floors_v1.safetensors", "Everspire_Floors_v1.safetensors"),
    (f"{_LFS}/AddMicroDetails_NoobAI_v5.safetensors", "AddMicroDetails_NoobAI_v5.safetensors"),
]

# ── status shared with the API ──────────────────────────────────────────────
_LOCK = threading.Lock()
_STATUS = {
    "state": "idle",        # idle | running | done | error | no_gpu
    "step": "",
    "step_index": 0,
    "step_total": 5,
    "downloaded": 0,
    "total": 0,
    "message": "",
}


def get_status() -> dict:
    with _LOCK:
        s = dict(_STATUS)
    s["installed"] = is_installed()
    # Reported separately from "installed" on purpose: generation can work
    # perfectly while the cutout is missing, and that combination shows up as
    # hero art with ragged backgrounds rather than as an error. Surfacing it
    # lets Settings offer a repair instead of the player wondering.
    s["cutout_ready"] = cutout_ready() if s["installed"] else False
    s["percent"] = round(100 * s["downloaded"] / s["total"], 1) if s["total"] else None
    return s


def _set(**kw):
    with _LOCK:
        _STATUS.update(kw)


def _active_comfy() -> tuple[str, str]:
    """(dir, python) of the ComfyUI the GAME will actually use.

    Falls back to this installer's own layout. Resolving properly matters:
    checking only COMFY_DIR told anyone who already had a ComfyUI — with the
    right checkpoint sitting in it — that they needed another 9GB download."""
    try:
        from services.comfy_service import comfy_paths
        d, py = comfy_paths()
        if d and py:
            return d, py
    except Exception:
        pass
    return COMFY_DIR, EMBEDDED_PY


def is_installed() -> bool:
    """A usable install = ComfyUI, a Python to run it, and the checkpoint.
    Deliberately checks the checkpoint too: ComfyUI without a model starts
    fine and then fails every generation, which reads as a game bug."""
    comfy_dir, py = _active_comfy()
    return (os.path.isfile(os.path.join(comfy_dir, "main.py"))
            and os.path.isfile(py)
            and os.path.isfile(os.path.join(comfy_dir, "models", "checkpoints", CHECKPOINT_NAME)))


def has_nvidia_gpu() -> bool:
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              timeout=15).returncode == 0
    except Exception:
        return False


# ── download with resume ────────────────────────────────────────────────────

def _download(url: str, dest: str, label: str):
    """Range-resumed streaming download. Writes to dest.part, then renames —
    so an interrupted run can never leave a truncated file that looks
    complete to is_installed()."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest):
        _set(step=f"{label} (already downloaded)")
        return

    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}

    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        # 416 = the .part is already the whole file; anything else non-2xx is real.
        if r.status_code == 416:
            os.replace(part, dest)
            return
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) + have
        _set(step=label, downloaded=have, total=total)

        last_report = 0.0
        with open(part, "ab") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                have += len(chunk)
                # Throttle status writes — a 7GB file is ~7000 chunks and the
                # lock churn is pointless at that rate.
                now = time.time()
                if now - last_report > 0.5:
                    _set(downloaded=have, total=total)
                    last_report = now
    os.replace(part, dest)
    _set(downloaded=have, total=total)


def _run(cmd, cwd=None, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ── the install itself ──────────────────────────────────────────────────────

def _install():
    try:
        if not has_nvidia_gpu():
            _set(state="no_gpu", step="", message=(
                "No NVIDIA GPU detected. The game plays fine on the built-in art — "
                "nothing was installed."))
            return

        os.makedirs(GEN_DIR, exist_ok=True)

        # Decide the target ONCE. A player who already has a working ComfyUI
        # (or Liam's dev box at ~/ComfyUI) gets the models and the node added
        # to it, rather than a second 1.5GB copy sitting next to the one the
        # game will actually launch. Everything below writes to target_dir.
        found_dir, found_py = _active_comfy()
        reuse = (os.path.isfile(os.path.join(found_dir, "main.py"))
                 and os.path.isfile(found_py))
        target_dir = found_dir if reuse else COMFY_DIR

        # 1. ComfyUI portable
        if reuse:
            _set(state="running", step_index=2,
                 step=f"Using the ComfyUI already at {target_dir}")
        elif not os.path.isfile(os.path.join(COMFY_DIR, "main.py")):
            _set(state="running", step_index=1, step="Downloading ComfyUI (~1.5GB)")
            archive = os.path.join(GEN_DIR, "ComfyUI_windows_portable_nvidia.7z")
            _download(COMFY_7Z_URL, archive, "Downloading ComfyUI (~1.5GB)")

            _set(step_index=2, step="Extracting ComfyUI", downloaded=0, total=0)
            sevenzr = os.path.join(GEN_DIR, "7zr.exe")
            if not os.path.isfile(sevenzr):
                _download(SEVENZR_URL, sevenzr, "Fetching extractor")
            res = _run([sevenzr, "x", "-y", archive], cwd=GEN_DIR)
            if res.returncode != 0:
                raise RuntimeError(f"Extraction failed: {res.stderr[-400:].decode(errors='replace')}")
            try:
                os.remove(archive)
            except OSError:
                pass
        else:
            _set(state="running", step_index=2, step="ComfyUI already present")

        # 2. checkpoint
        _set(step_index=3, step="Downloading the art model (~7GB)", downloaded=0, total=0)
        _download(CHECKPOINT_URL,
                  os.path.join(target_dir, "models", "checkpoints", CHECKPOINT_NAME),
                  "Downloading the art model (~7GB)")

        # 3. style LoRAs
        _set(step_index=4, step="Downloading Giltgrave style models (~450MB)",
             downloaded=0, total=0)
        for url, name in LORAS:
            _download(url, os.path.join(target_dir, "models", "loras", name),
                      f"Downloading {name}")

        # 4. the cutout — node, deps, and the segmentation weights.
        _set(step_index=5, step="Installing the cutout (~200MB)", downloaded=0, total=0)
        cutout_err = _install_cutout(target_dir)

        # 5. remember where it went, so comfy_service can find it without an
        #    env var and without the player restarting anything.
        _remember_comfy_dir(target_dir)

        if cutout_err:
            # Generation works; transparency will be worse. Say so plainly
            # instead of reporting a clean "done" and letting the player
            # discover it as ragged hero art.
            _set(state="done", step="", message=(
                "Hero generation is ready, but the cutout step did not finish "
                f"({cutout_err}). Portraits will still generate; their "
                "backgrounds may be rougher. Re-run the install to retry."))
        else:
            _set(state="done", step="", message="Hero generation is ready.")
    except Exception as e:
        _set(state="error", message=f"{type(e).__name__}: {e}",
             step="")


SEG_MODEL_FILE = "isnet-anime.onnx"
# Beasts need a general segmenter as well. isnet-anime finds nothing on a
# spider or a dragon, the cutout falls through to the border flood, and the
# flood eats their dark bodies. Missing this file does not error — it silently
# degrades every non-humanoid enemy, which is why it is verified below rather
# than assumed.
SEG_MODEL_BEAST_FILE = "isnet-general-use.onnx"


def _u2net_home() -> str:
    """Where rembg caches its ONNX weights."""
    return os.getenv("U2NET_HOME") or os.path.join(os.path.expanduser("~"), ".u2net")


def cutout_ready() -> bool:
    """True when the good transparent cutout is actually available.

    Reports on the ComfyUI the GAME will use, not on this installer's fixed
    path — a dev box (or a player who already had ComfyUI) runs from
    ~/ComfyUI, and checking only the installer layout called a perfectly
    working setup broken.

    All three pieces have to be there: the node (so ComfyUI cuts during
    generation), rembg in that python (which portrait_cache also borrows as a
    fallback), and the segmentation weights."""
    comfy_dir, py = _active_comfy()
    node = os.path.join(comfy_dir, "custom_nodes", "toe_rembg")
    if not (os.path.isfile(os.path.join(node, "__init__.py"))
            and os.path.isfile(os.path.join(node, "cutout.py"))):
        return False
    if not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_FILE)):
        return False
    # Both models, not just the anime one. With only the anime weights the
    # cutout reports ready and then quietly ruins every beast.
    if not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_BEAST_FILE)):
        return False
    if not os.path.isfile(py):
        return False
    return _run([py, "-c", "import rembg, onnxruntime"], timeout=300).returncode == 0


def _install_cutout(comfy_dir: str | None = None) -> str | None:
    """Node + rembg + weights, into ComfyUI's python (never the game's — the
    game has no torch and never runs the node). Returns None on success or a
    short reason on failure.

    This used to be one best-effort pip call whose result was never checked, so
    a failed install reported "Hero generation is ready" and the player found
    out via ragged hero art. Every piece is verified now.

    The weights matter more than they look. rembg fetches isnet-anime.onnx
    (~176MB) from GitHub lazily, on the FIRST cutout — so without this step a
    player's first hero triggers a silent download that can fail on a flaky
    network, and the cutout quietly degrades to the flood that hollows out dark
    costumes. Pull it during the install, where a failure is visible and
    retryable, not mid-game."""
    if comfy_dir is None:
        comfy_dir, py = _active_comfy()
    else:
        py = os.path.join(comfy_dir, "venv", "Scripts", "python.exe")
        if not os.path.isfile(py):
            py = os.path.join(os.path.dirname(comfy_dir), "python_embeded", "python.exe")

    node_src = os.path.join(_repo_root(), "generation", "comfy_nodes", "toe_rembg")
    if not os.path.isdir(node_src):
        return "cutout node missing from the install"
    # The WHOLE directory: __init__.py is a thin wrapper that imports cutout.py
    # beside it. Copying only __init__.py leaves a node that raises on import,
    # which ComfyUI then reports as "node not found".
    try:
        shutil.copytree(node_src, os.path.join(comfy_dir, "custom_nodes", "toe_rembg"),
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    except Exception as e:
        return f"could not copy the cutout node: {e}"

    if not os.path.isfile(py):
        return "ComfyUI's python is missing"

    _set(step="Installing the cutout (1/2: dependencies)")
    for attempt in (1, 2):
        if _run([py, "-c", "import rembg, onnxruntime"], timeout=300).returncode == 0:
            break
        res = _run([py, "-m", "pip", "install", "rembg", "onnxruntime"], timeout=2400)
        if res.returncode != 0 and attempt == 2:
            return f"pip install rembg failed: {res.stderr[-200:].decode(errors='replace')}"
    else:
        return "rembg did not import after installing"

    _set(step="Installing the cutout (2/2: segmentation model, ~176MB)")
    if not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_FILE)):
        # Ask rembg to fetch its own weights — it knows the URL and checksum,
        # so this stays correct if the model is ever swapped.
        res = _run([py, "-c",
                    "from rembg.sessions.dis_anime import DisSession as S; S.download_models()"],
                   timeout=2400)
        if res.returncode != 0 or not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_FILE)):
            return "could not download the segmentation model"

    if not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_BEAST_FILE)):
        _set(step="Installing the cutout (2/2: beast segmentation model, ~179MB)")
        res = _run([py, "-c",
                    "from rembg.sessions.dis_general_use import DisSession as S; S.download_models()"],
                   timeout=2400)
        if res.returncode != 0 or not os.path.isfile(os.path.join(_u2net_home(), SEG_MODEL_BEAST_FILE)):
            return "could not download the beast segmentation model"

    if not cutout_ready():
        return "cutout verification failed"
    return None


def _repo_root() -> str:
    # backend/services/ -> backend/ -> game root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _remember_comfy_dir(path: str):
    """Persist to app_settings.json rather than shelling out to setx.

    setx only affects NEW processes, so the running game wouldn't see it until
    a restart — and in the packaged build the backend is a thread inside the
    launcher, so 'restart the game' means the player quitting right after a
    9GB download. Writing it where comfy_service already looks avoids that.
    """
    try:
        from routers.settings import _load, _save
        data = _load()
        data["comfyui_dir"] = path
        _save(data)
    except Exception as e:
        print(f"[GenInstall] Could not persist comfyui_dir: {e}")


def start_install() -> dict:
    """Kick off the install on a background thread. Idempotent — calling it
    while one is running just returns the current status."""
    with _LOCK:
        if _STATUS["state"] == "running":
            return dict(_STATUS)
        _STATUS.update({"state": "running", "step": "Starting...", "step_index": 0,
                        "downloaded": 0, "total": 0, "message": ""})
    threading.Thread(target=_install, daemon=True, name="everspire-gen-install").start()
    return get_status()
