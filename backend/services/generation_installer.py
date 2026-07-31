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
_LFS = "https://media.githubusercontent.com/media/SageHargrove/Everspire/main/generation/loras"
LORAS = [
    (f"{_LFS}/ToE_Heroes_Main.safetensors", "ToE_Heroes_Main.safetensors"),
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
    s["percent"] = round(100 * s["downloaded"] / s["total"], 1) if s["total"] else None
    return s


def _set(**kw):
    with _LOCK:
        _STATUS.update(kw)


def is_installed() -> bool:
    """A usable install = ComfyUI, a Python to run it, and the checkpoint.
    Deliberately checks the checkpoint too: ComfyUI without a model starts
    fine and then fails every generation, which reads as a game bug."""
    return (os.path.isfile(os.path.join(COMFY_DIR, "main.py"))
            and os.path.isfile(EMBEDDED_PY)
            and os.path.isfile(os.path.join(COMFY_DIR, "models", "checkpoints", CHECKPOINT_NAME)))


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

        # 1. ComfyUI portable
        if not os.path.isfile(os.path.join(COMFY_DIR, "main.py")):
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
                  os.path.join(COMFY_DIR, "models", "checkpoints", CHECKPOINT_NAME),
                  "Downloading the art model (~7GB)")

        # 3. style LoRAs
        _set(step_index=4, step="Downloading Everspire style models (~450MB)",
             downloaded=0, total=0)
        for url, name in LORAS:
            _download(url, os.path.join(COMFY_DIR, "models", "loras", name),
                      f"Downloading {name}")

        # 4. cutout node + its deps, into the PORTABLE python (not the game's —
        #    the game has no torch and never runs the node).
        _set(step_index=5, step="Installing the cutout node", downloaded=0, total=0)
        node_src = os.path.join(_repo_root(), "generation", "comfy_nodes", "toe_rembg", "__init__.py")
        if os.path.isfile(node_src):
            node_dst_dir = os.path.join(COMFY_DIR, "custom_nodes", "toe_rembg")
            os.makedirs(node_dst_dir, exist_ok=True)
            shutil.copy2(node_src, os.path.join(node_dst_dir, "__init__.py"))
        if os.path.isfile(EMBEDDED_PY):
            # Best-effort: a failure here costs cutout quality, not the install.
            _run([EMBEDDED_PY, "-m", "pip", "install", "rembg", "onnxruntime"], timeout=1800)

        # 5. remember where it went, so comfy_service can find it without an
        #    env var and without the player restarting anything.
        _remember_comfy_dir(COMFY_DIR)

        _set(state="done", step="", message="Hero generation is ready.")
    except Exception as e:
        _set(state="error", message=f"{type(e).__name__}: {e}",
             step="")


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
