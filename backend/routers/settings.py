"""Install-wide settings (not per-profile), stored in saves/app_settings.json
on the player's own machine — their keys on their disk, plaintext acceptable,
never sent to the world server. Two independent controls:

  • LLM API key (Anthropic/Claude) — powers ALL text generation: hero names,
    backstories, the appearance descriptions that feed portrait generation,
    combat narration, chatter, flavor. Without it, text falls back to built-in
    placeholders. (Env var ANTHROPIC_API_KEY still works as a dev fallback.)
  • Image generation on/off — whether local ComfyUI renders custom hero
    portraits on this machine's GPU. Independent of the key: you can have rich
    Claude-written heroes while portraits come from the bundled art pool, or
    pause portrait generation mid-session to free up the GPU.
"""
import json
import os
from fastapi import APIRouter, HTTPException, Body

router = APIRouter()

_SETTINGS_PATH = os.path.join("saves", "app_settings.json")


def _load() -> dict:
    if os.path.exists(_SETTINGS_PATH):
        try:
            return json.load(open(_SETTINGS_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    json.dump(data, open(_SETTINGS_PATH, "w", encoding="utf-8"), indent=2)


# ─── LLM (Claude) API key ───────────────────────────────────────────────────

def get_llm_api_key() -> str | None:
    """The Anthropic/Claude key that powers text generation. Prefers the
    key entered in-game; falls back to the ANTHROPIC_API_KEY env var (dev),
    then the legacy `generation_api_key` field for older saves."""
    data = _load()
    return (data.get("llm_api_key")
            or os.getenv("ANTHROPIC_API_KEY")
            or data.get("generation_api_key")
            or None)


@router.get("/apikey")
def apikey_status():
    """Masked status only — the full key never leaves the settings file.
    `env` flags whether the key is coming from the environment (so the UI can
    say 'already configured' without the player re-entering it)."""
    data = _load()
    stored = data.get("llm_api_key") or data.get("generation_api_key")
    key = stored or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"set": False, "masked": None, "env": False}
    masked = key[:7] + "…" + key[-4:] if len(key) > 14 else "•" * len(key)
    return {"set": True, "masked": masked, "env": not stored}


@router.post("/apikey")
def set_apikey(payload: dict = Body(...)):
    key = (payload.get("api_key") or "").strip()
    data = _load()
    if not key:
        data.pop("llm_api_key", None)
        data.pop("generation_api_key", None)  # clear legacy too
        _save(data)
        return {"set": False}
    if len(key) < 8 or len(key) > 300:
        raise HTTPException(status_code=400, detail="That doesn't look like a valid API key")
    data["llm_api_key"] = key
    data.pop("generation_api_key", None)  # migrate off the legacy field
    _save(data)
    return {"set": True}


# ─── Image generation on/off ────────────────────────────────────────────────

def get_image_generation_enabled() -> bool:
    """Whether local ComfyUI portrait generation runs on this machine.
    Defaults OFF — fresh installs use the bundled art pool until the player
    opts in. Turning it on downloads everything needed (~9.2GB, NVIDIA only)
    via generation_installer; nobody has to run a script."""
    return bool(_load().get("image_generation_enabled", False))


@router.get("/generation")
def generation_status():
    return {"enabled": get_image_generation_enabled()}


@router.post("/generation")
def set_generation(payload: dict = Body(...)):
    enabled = bool(payload.get("enabled"))
    data = _load()
    data["image_generation_enabled"] = enabled
    _save(data)
    # Turning it on mid-session should bring ComfyUI up without a restart.
    # If nothing is installed yet, say so — the caller decides whether to
    # kick off /generation/install rather than us starting a 9GB download
    # off the back of a toggle.
    needs_install = False
    if enabled:
        try:
            from services.generation_installer import is_installed, cutout_ready
            # cutout_ready matters as much as is_installed: generation works
            # without it, but hero art comes out with ragged backgrounds, which
            # reads as bad art rather than as a missing download. Every step of
            # _install() skips what's already on disk, so re-running to fix
            # only the cutout costs a few minutes, not another 9GB.
            needs_install = not is_installed() or not cutout_ready()
        except Exception:
            pass
        if not needs_install:
            try:
                from services.comfy_service import ensure_comfy_running
                ensure_comfy_running()
            except Exception:
                pass
    return {"enabled": enabled, "needs_install": needs_install}


# ─── one-click generation setup ─────────────────────────────────────────────
#
# Everything INSTALL_GENERATION.bat does, driven from Settings instead, so the
# player never leaves the game to run a separate script.

@router.get("/generation/install-status")
def generation_install_status():
    from services.generation_installer import get_status, has_nvidia_gpu
    status = get_status()
    status["gpu"] = has_nvidia_gpu()
    return status


@router.post("/generation/install")
def generation_install():
    from services.generation_installer import start_install
    return start_install()
