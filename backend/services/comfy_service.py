import json
import time
import random
import requests
import os

COMFY_URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188")
CHECKPOINT = os.getenv("COMFY_CHECKPOINT", "noobaiXLNAIXL_vPred10Version.safetensors")
LORA_NAME = os.getenv("COMFY_LORA", None)
LORA_STRENGTH = float(os.getenv("COMFY_LORA_STRENGTH", "0.8"))

# v-prediction checkpoints (NoobAI vPred etc.) sampled like a normal eps
# model produce exactly the artifacts we saw in portraits/cached: some
# outputs fried (crushed blacks, neon saturation), others collapsed to
# near-grayscale. The documented fix is a RescaleCFG pass and a lower CFG.
# Auto-detected from the checkpoint filename; override with COMFY_VPRED=0/1.
_vpred_env = os.getenv("COMFY_VPRED")
IS_VPRED = (_vpred_env == "1") if _vpred_env in ("0", "1") else ("vpred" in CHECKPOINT.lower().replace("_", "").replace("-", ""))
CFG = float(os.getenv("COMFY_CFG", "5.0" if IS_VPRED else "7.0"))
RESCALE_MULT = float(os.getenv("COMFY_RESCALE_CFG", "0.7"))
# Impact Pack FaceDetailer pass (installed 2026-07). COMFY_FACE_DETAILER=0
# disables; if the packs are missing, generation retries without it anyway.
FACE_DETAIL = os.getenv("COMFY_FACE_DETAILER", "1") == "1"
# xinsir union ControlNet (installed in ComfyUI/models/controlnet) — used to
# lock the body plan of non-humanoid monsters against the human-trained
# checkpoint's tendency to humanise them. See _build_workflow's control path.
CONTROLNET_MODEL = os.getenv("COMFY_CONTROLNET", "xinsir-union-promax.safetensors")

# ── Transparent generation (LayerDiffuse) ───────────────────────────────────
# The durable fix for the "cutout ate part of the hero" problem: generate the
# figure WITH an alpha channel so there is no black-bg-removal step to erode
# anything. Requires the ComfyUI-layerdiffuse custom nodes + their SDXL
# transparent weights installed in ComfyUI. OFF by default — flip COMFY_TRANSPARENT=1
# once installed; if the nodes are missing the workflow queue is rejected and
# generate_portrait_comfy automatically retries the normal black-bg path (which
# still runs the cutout), so enabling it can never harden-fail a generation.
TRANSPARENT = os.getenv("COMFY_TRANSPARENT", "0") == "1"
# Apply-node config. "SDXL, Conv Injection" is the standard SDXL foreground
# (transparent subject) mode; "SDXL, Attention Injection" is the alternative.
LAYERDIFFUSE_CONFIG = os.getenv("COMFY_LAYERDIFFUSE_CONFIG", "SDXL, Conv Injection")
LAYERDIFFUSE_WEIGHT = float(os.getenv("COMFY_LAYERDIFFUSE_WEIGHT", "1.0"))


def transparent_enabled() -> bool:
    return TRANSPARENT

# ── Content-aware cutout in-workflow (rembg / isnet-anime) ───────────────────
# The ADOPTED fix for "cutout ate part of the hero". A tiny custom node
# (ComfyUI/custom_nodes/toe_rembg) runs rembg isnet-anime at the end of the
# graph, so the portrait comes back already background-removed. Content-aware
# segmentation keeps dark cloaks/hair that the void-mask/border-flood cutouts
# shred. ON by default; if the node isn't installed the queue is rejected and
# generation retries without it (the backend then cuts with border-flood).
REMBG_CUTOUT = os.getenv("COMFY_REMBG_CUTOUT", "1") == "1"


def rembg_cutout_enabled() -> bool:
    return REMBG_CUTOUT


def rembg_node_preflight() -> dict:
    """Confirm the ToE Rembg Cutout node is registered in the running ComfyUI."""
    try:
        info = requests.get(f"{COMFY_URL}/object_info", timeout=5.0).json()
        ok = "ToE_RembgCutout" in info
        return {"ok": ok, "detail": None if ok else
                "ToE_RembgCutout node not found — ensure ComfyUI/custom_nodes/toe_rembg "
                "exists, `pip install rembg onnxruntime` in ComfyUI's python, and restart ComfyUI."}
    except Exception as e:
        return {"ok": False, "detail": f"ComfyUI not reachable: {e}"}


def layerdiffuse_preflight() -> dict:
    """Ask the running ComfyUI what nodes it has, so a missing-install is a
    clear message instead of a silent fallback. Returns
    {ok, apply, decode, detail}. Cheap; call it when COMFY_TRANSPARENT is on."""
    try:
        resp = requests.get(f"{COMFY_URL}/object_info", timeout=5.0)
        info = resp.json()
        apply_ok = "LayeredDiffusionApply" in info
        decode_ok = "LayeredDiffusionDecodeRGBA" in info
        return {
            "ok": apply_ok and decode_ok,
            "apply": apply_ok,
            "decode": decode_ok,
            "detail": None if (apply_ok and decode_ok) else
                      "ComfyUI-layerdiffuse nodes not found — install github.com/huchenlei/ComfyUI-layerdiffuse "
                      "and its SDXL transparent weights, then restart ComfyUI.",
        }
    except Exception as e:
        return {"ok": False, "apply": False, "decode": False, "detail": f"ComfyUI not reachable: {e}"}


def _build_workflow(prompt: str, negative: str = "", seed: int = None, init_image_name: str = None, denoise: float = 0.45, width: int = 832, height: int = 1216, hires: bool = False, hires_denoise: float = 0.62, lora_override: str = None, lora_strength_override: float = None, face_detail: bool = None, control_image_name: str = None, control_strength: float = 0.55, control_end: float = 0.5, control_mode: str = 'canny', transparent: bool = False, rembg_cutout: bool = False) -> dict:
    if face_detail is None:
        face_detail = FACE_DETAIL
    # LayerDiffuse (transparent) already yields RGBA — never double-cut.
    if transparent:
        rembg_cutout = False
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    # LayerDiffuse's RGBA decode requires both image dims to be multiples of
    # 64 (asserts otherwise). The base 832×1216 already is, but the 1.5× hires
    # upscale (→1824) is not, so snap dims down to /64 in transparent mode.
    if transparent:
        width = (int(width) // 64) * 64
        height = (int(height) // 64) * 64

    full_prompt = prompt

    neg = negative or (
        "blurry, low quality, watermark, text, signature, bad anatomy, "
        "deformed, ugly, disfigured, worst quality, jpeg artifacts"
    )

    # model source: checkpoint by default, lora loader if lora configured
    model_source = ["4", 0]
    clip_source = ["4", 1]

    # hires=True runs a second, lower-denoise KSampler pass over a latent
    # upscale of the first pass's output — single-pass generation at a
    # busy, multi-subject composition (vs. a tight single-character
    # portrait) tends to come out simpler/blurrier than this game's other
    # scene-style art, since the base checkpoint resolution is fighting the
    # composition's complexity. The upscale-and-refine pass gives the model
    # a second look at the full composition instead of trying to render all
    # that detail in one pass.
    final_samples_source = ["3", 0]
    # hires now applies to img2img too, and that matters: a star-up re-render
    # is img2img, so skipping it meant every promotion came back at base
    # resolution with no refinement pass while the ORIGINAL had both. The
    # "upgrade" was visibly softer and less detailed than the 1-star it came
    # from. Node 13 upscales the sampler latent, which exists on the img2img
    # path exactly as it does on the txt2img one, so this is a free correction.
    # Callers that don't want the extra pass simply leave hires False.
    if hires:
        final_samples_source = ["14", 0]

    workflow = {
        "4": {
            "inputs": {"ckpt_name": CHECKPOINT},
            "class_type": "CheckpointLoaderSimple"
        },
        "8": {
            "inputs": {"samples": final_samples_source, "vae": ["4", 2]},
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {"filename_prefix": "everspire", "images": ["8", 0]},
            "class_type": "SaveImage"
        }
    }

    # LoRA stack. COMFY_LORA accepts a comma-separated list, each entry
    # optionally carrying its own strength after a colon:
    #   COMFY_LORA="darkFantasy_illustrious.safetensors:0.55,addMicroDetails_illu.safetensors:0.3"
    # Entries without a strength use COMFY_LORA_STRENGTH. A per-call
    # override (lora_override, same syntax) takes precedence, so a caller
    # (e.g. the equipment icon script) can use a different stack without
    # touching the global setting. Loaders chain 10, 21, 22, ...
    lora_spec = lora_override if lora_override is not None else LORA_NAME
    default_strength = lora_strength_override if lora_strength_override is not None else LORA_STRENGTH
    if lora_spec:
        entries = []
        for part in str(lora_spec).split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, _, s = part.rpartition(":")
                try:
                    entries.append((name.strip(), float(s)))
                except ValueError:
                    entries.append((part, default_strength))
            else:
                entries.append((part, default_strength))
        for i, (name, strength) in enumerate(entries):
            node_id = "10" if i == 0 else str(20 + i)  # 10, 21, 22, ...
            workflow[node_id] = {
                "inputs": {
                    "lora_name": name,
                    "strength_model": strength,
                    "strength_clip": strength,
                    "model": model_source,
                    "clip": clip_source
                },
                "class_type": "LoraLoader"
            }
            model_source = [node_id, 0]
            clip_source = [node_id, 1]

    # v-pred sampling correction — core ComfyUI node, sits after the
    # checkpoint/LoRA and feeds every KSampler below.
    if IS_VPRED:
        workflow["20"] = {
            "inputs": {"multiplier": RESCALE_MULT, "model": model_source},
            "class_type": "RescaleCFG"
        }
        model_source = ["20", 0]

    # LayerDiffuse: patch the model so sampling encodes transparency, then the
    # decode node (added after VAEDecode below) extracts the alpha. Sits last
    # in the model chain so every sampler (base, hires, FaceDetailer) inherits
    # the transparent-aware model.
    if transparent:
        workflow["50"] = {
            "inputs": {"config": LAYERDIFFUSE_CONFIG, "weight": LAYERDIFFUSE_WEIGHT, "model": model_source},
            "class_type": "LayeredDiffusionApply",
        }
        model_source = ["50", 0]

    workflow["6"] = {
        "inputs": {"text": full_prompt, "clip": clip_source},
        "class_type": "CLIPTextEncode"
    }
    workflow["7"] = {
        "inputs": {"text": neg, "clip": clip_source},
        "class_type": "CLIPTextEncode"
    }

    # ── ControlNet (body-plan lock for non-humanoid monsters) ──────────────
    # The human-trained checkpoint humanises quadrupeds/dragons/insects (mw1
    # bug — Liam). A structural map of a reference of the RIGHT body plan, fed
    # through the xinsir union ControlNet, holds the silhouette so a spider
    # stays eight-legged, a dragon stays a dragon. control_mode picks the
    # preprocessor: 'depth' (DepthAnything — TONE-AGNOSTIC, so the model lights
    # the subject freely per the prompt: fixes the dark-render problem canny
    # had, since canny from a dark ref dragged the shading dark), 'lineart'
    # (clean anime outlines), or 'canny' (core node, raw edges). control_end
    # < 1.0 releases control partway so the LoRA/prompt still drive style.
    pos_src, neg_src = ["6", 0], ["7", 0]
    if control_image_name:
        workflow["40"] = {
            "inputs": {"image": control_image_name, "upload": "image"},
            "class_type": "LoadImage"
        }
        if control_mode == "depth":
            workflow["41"] = {
                "inputs": {"image": ["40", 0], "ckpt_name": "depth_anything_v2_vitl.pth", "resolution": 1024},
                "class_type": "DepthAnythingV2Preprocessor"
            }
            union_type = "depth"
        elif control_mode == "lineart":
            workflow["41"] = {
                "inputs": {"image": ["40", 0], "resolution": 1024},
                "class_type": "AnimeLineArtPreprocessor"
            }
            union_type = "canny/lineart/anime_lineart/mlsd"
        else:  # canny (core node)
            workflow["41"] = {
                "inputs": {"image": ["40", 0], "low_threshold": 0.35, "high_threshold": 0.75},
                "class_type": "Canny"
            }
            union_type = "canny/lineart/anime_lineart/mlsd"
        workflow["42"] = {
            "inputs": {"control_net_name": CONTROLNET_MODEL},
            "class_type": "ControlNetLoader"
        }
        workflow["44"] = {
            "inputs": {"type": union_type, "control_net": ["42", 0]},
            "class_type": "SetUnionControlNetType"
        }
        workflow["43"] = {
            "inputs": {
                "strength": control_strength,
                "start_percent": 0.0,
                "end_percent": control_end,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "control_net": ["44", 0],
                "image": ["41", 0],
                "vae": ["4", 2],
            },
            "class_type": "ControlNetApplyAdvanced"
        }
        pos_src, neg_src = ["43", 0], ["43", 1]

    if init_image_name:
        workflow["11"] = {
            "inputs": {"image": init_image_name, "upload": "image"},
            "class_type": "LoadImage"
        }
        workflow["12"] = {
            "inputs": {"pixels": ["11", 0], "vae": ["4", 2]},
            "class_type": "VAEEncode"
        }
        latent_image_source = ["12", 0]
        denoise_val = denoise
        base_width, base_height = width, height
    elif hires:
        # First pass composes at the requested size — which should be the
        # checkpoint's native training res (832×1216 for NoobAI-XL); the
        # second pass upscales 1.5× and refines. The old version composed
        # the base pass at 0.65× (≈540×790) — BELOW the model's coherent
        # range, which is where the broken anatomy/proportions came from —
        # and "upscaled" merely back to native, so detail never exceeded a
        # single-pass render either.
        base_width, base_height = width, height
        workflow["5"] = {
            "inputs": {"width": base_width, "height": base_height, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        }
        latent_image_source = ["5", 0]
        denoise_val = 1.0
    else:
        workflow["5"] = {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        }
        latent_image_source = ["5", 0]
        denoise_val = 1.0

    workflow["3"] = {
        "inputs": {
            "seed": seed,
            "steps": 28,
            "cfg": CFG,
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
            "denoise": denoise_val,
            "model": model_source,
            "positive": pos_src,
            "negative": neg_src,
            "latent_image": latent_image_source
        },
        "class_type": "KSampler"
    }

    # hires now applies to img2img too, and that matters: a star-up re-render
    # is img2img, so skipping it meant every promotion came back at base
    # resolution with no refinement pass while the ORIGINAL had both. The
    # "upgrade" was visibly softer and less detailed than the 1-star it came
    # from. Node 13 upscales the sampler latent, which exists on the img2img
    # path exactly as it does on the txt2img one, so this is a free correction.
    # Callers that don't want the extra pass simply leave hires False.
    if hires:
        # LayerDiffuse needs the final image on a /64 grid (see the snap at the
        # top); round the hires target to /64 in transparent mode, else /8.
        _grid = 64 if transparent else 8
        workflow["13"] = {
            "inputs": {
                "samples": ["3", 0],
                "upscale_method": "bislerp",
                "width": (int(width * 1.5) // _grid) * _grid,
                "height": (int(height * 1.5) // _grid) * _grid,
                "crop": "disabled"
            },
            "class_type": "LatentUpscale"
        }
        workflow["14"] = {
            "inputs": {
                "seed": seed + 1,
                "steps": 20,
                "cfg": CFG,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": hires_denoise,
                "model": model_source,
                "positive": pos_src,
                "negative": neg_src,
                "latent_image": ["13", 0]
            },
            "class_type": "KSampler"
        }

    # FaceDetailer (Impact Pack): detects the face in the decoded image and
    # re-renders that crop at high resolution — the fix for tiny broken
    # eyes at full-body framing. If no face is detected (monsters), it
    # passes the image through untouched. generate_portrait_comfy retries
    # without it if ComfyUI rejects the workflow (packs not installed).
    if face_detail:
        workflow["31"] = {
            "inputs": {"model_name": "bbox/face_yolov8m.pt"},
            "class_type": "UltralyticsDetectorProvider"
        }
        workflow["30"] = {
            "inputs": {
                "image": ["8", 0],
                "model": model_source,
                "clip": clip_source,
                "vae": ["4", 2],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "bbox_detector": ["31", 0],
                "guide_size": 512,
                "guide_size_for": True,
                "max_size": 1024,
                "seed": seed + 2,
                "steps": 20,
                "cfg": CFG,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 0.45,
                "feather": 5,
                "noise_mask": True,
                "force_inpaint": True,
                "bbox_threshold": 0.5,
                "bbox_dilation": 10,
                "bbox_crop_factor": 3.0,
                "sam_detection_hint": "center-1",
                "sam_dilation": 0,
                "sam_threshold": 0.93,
                "sam_bbox_expansion": 0,
                "sam_mask_hint_threshold": 0.7,
                "sam_mask_hint_use_negative": "False",
                "drop_size": 10,
                "wildcard": "",
                "cycle": 1,
            },
            "class_type": "FaceDetailer"
        }
        # save the detailed image instead of the raw decode
        workflow["9"]["inputs"]["images"] = ["30", 0]

    # LayerDiffuse decode: turn the final RGB (raw decode or FaceDetailer'd)
    # plus the final latent into an RGBA image — the transparency is derived
    # from the transparent-aware latent, so the subject comes out already cut.
    if transparent:
        rgb_src = workflow["9"]["inputs"]["images"]  # ["8",0] or ["30",0]
        workflow["51"] = {
            "inputs": {
                "samples": final_samples_source,
                "images": rgb_src,
                "sd_version": "SDXL",
                "sub_batch_size": 16,
            },
            "class_type": "LayeredDiffusionDecodeRGBA",
        }
        workflow["9"]["inputs"]["images"] = ["51", 0]

    # Content-aware cutout (rembg isnet-anime) as the LAST step — runs on the
    # final RGB (raw decode or FaceDetailer'd) and outputs RGBA. The portrait
    # comes back already cut, so the backend skips its own cutout.
    if rembg_cutout:
        workflow["52"] = {
            "inputs": {"images": workflow["9"]["inputs"]["images"], "post_process": True},
            "class_type": "ToE_RembgCutout",
        }
        workflow["9"]["inputs"]["images"] = ["52", 0]

    return workflow


def _queue_prompt(workflow: dict) -> str | None:
    try:
        response = requests.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow},
            timeout=10.0
        )
        if response.status_code != 200:
            print(f"[ComfyUI] 400 detail: {response.text}")
            return None
        return response.json()["prompt_id"]
    except Exception as e:
        print(f"[ComfyUI] Failed to queue prompt: {e}")
        return None


def _wait_for_result(prompt_id: str, timeout: int = 180) -> str | None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=5.0)
            history = resp.json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        return node_output["images"][0]["filename"]
        except Exception:
            pass
        time.sleep(2.0)
    return None


def _download_image(filename: str, save_path: str) -> bool:
    try:
        resp = requests.get(
            f"{COMFY_URL}/view",
            params={"filename": filename, "type": "output"},
            timeout=30.0
        )
        resp.raise_for_status()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"[ComfyUI] Failed to download image: {e}")
        return False


def is_comfy_running() -> bool:
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=3.0)
        return True
    except Exception:
        return False


def comfy_paths() -> tuple[str | None, str | None]:
    """(comfy_dir, python_exe) for the local ComfyUI install, or (None, None).

    Shared by auto-start and by portrait_cache's cutout fallback — that python
    is the only interpreter on a player's machine with rembg in it, so it is
    worth finding from more than one place."""
    home = os.path.expanduser("~")

    # Where the in-game installer put it, if it ran. Checked FIRST and read
    # from app_settings.json rather than an env var, because setx only reaches
    # new processes — in the packaged build the backend is a thread inside the
    # launcher, so an env var wouldn't be visible until the player restarted
    # the game immediately after a 9GB download.
    settings_dir = None
    try:
        from routers.settings import _load
        settings_dir = _load().get("comfyui_dir")
    except Exception:
        pass

    cands = [c for c in (
        settings_dir,
        os.getenv("COMFYUI_DIR"),
        os.path.join(home, "ComfyUI"),
        # in-game installer / INSTALL_GENERATION.bat portable layouts
        os.path.join(home, "Everspire-Generation", "ComfyUI_windows_portable", "ComfyUI"),
        os.path.join(home, "ToE-Generation", "ComfyUI_windows_portable", "ComfyUI"),
    ) if c]
    cand = next((c for c in cands if os.path.exists(os.path.join(c, "main.py"))), None)
    if not cand:
        return None, None
    # python: dev venv inside the dir, or the portable build's embedded python
    # one level up (ComfyUI_windows_portable/python_embeded/) — NEVER
    # sys.executable (the game venv has no torch and no rembg).
    py = os.path.join(cand, "venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = os.path.join(os.path.dirname(cand), "python_embeded", "python.exe")
    return (cand, py) if os.path.exists(py) else (cand, None)


def ensure_comfy_running() -> bool:
    """Launch-everything UX: if ComfyUI isn't up but a local install exists,
    start it in the background so the player never has to. Non-fatal on every
    path — no install just means base-art mode. Returns True if the server is
    (or soon will be) up."""
    if is_comfy_running():
        return True
    if not COMFY_URL.startswith(("http://127.0.0.1", "http://localhost")):
        return False  # remote server — nothing to launch locally
    import subprocess, sys

    cand, py = comfy_paths()
    if not cand:
        return False
    if not py:
        print(f"[ComfyUI] Found {cand} but no runnable python — skipping auto-start.")
        return False
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen([py, "-s", os.path.join(cand, "main.py"), "--listen", "127.0.0.1",
                                 "--port", COMFY_URL.rsplit(":", 1)[-1]],
                                cwd=cand, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        global _LAUNCHED_PROC
        _LAUNCHED_PROC = proc
        print(f"[ComfyUI] Auto-started from {cand} (warming up).")
        return True
    except Exception as e:
        print(f"[ComfyUI] Auto-start failed: {e}")
        return False


# Only ever holds a ComfyUI WE started. A ComfyUI the player launched
# themselves stays None here and is never touched on shutdown.
_LAUNCHED_PROC = None


def shutdown_comfy():
    """Stop the ComfyUI we auto-started, if any.

    Matters most in the packaged build: there the backend runs as a thread
    inside the launcher process, so closing the game window used to leave an
    orphaned ComfyUI sitting on ~7GB of VRAM — squarely in the way of the
    next thing the player opens, which for this audience is a game. Killing
    the tree (not just the PID) because the portable build's python.exe is a
    stub that re-launches the real interpreter as a child.
    """
    global _LAUNCHED_PROC
    proc = _LAUNCHED_PROC
    _LAUNCHED_PROC = None
    if proc is None or proc.poll() is not None:
        return
    import subprocess as _sp
    try:
        if os.name == "nt":
            _sp.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                    capture_output=True, creationflags=_sp.CREATE_NO_WINDOW)
        else:
            proc.terminate()
    except Exception as e:
        print(f"[ComfyUI] Shutdown failed (pid {proc.pid}): {e}")


def _upload_image(file_path: str) -> str | None:
    try:
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"image": (filename, f, "image/png")}
            resp = requests.post(f"{COMFY_URL}/upload/image", files=files, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            return data.get("name")
    except Exception as e:
        print(f"[ComfyUI] Failed to upload image {file_path}: {e}")
        return None


def generate_portrait_comfy(prompt: str, save_path: str, init_image_path: str = None, denoise: float = 0.45, negative: str = "", width: int = 832, height: int = 1216, hires: bool = False, hires_denoise: float = 0.62, lora_override: str = None, lora_strength_override: float = None, _noise_retry: bool = False, control_image_path: str = None, control_strength: float = 0.55, control_end: float = 0.5, control_mode: str = 'canny', transparent: bool = None, rembg_cutout: bool = None, face_detail: bool = None) -> bool:
    """face_detail: None follows the COMFY_FACE_DETAILER default; False skips
    the detect-and-inpaint pass outright. Callers rendering things with no face
    — monsters, rooms, equipment — should pass False. It was previously only
    reachable through the internal retry helper, so those callers had no way to
    turn it off and every spider paid for a face pass."""
    if not is_comfy_running():
        print("[ComfyUI] Server not running — skipping.")
        return False

    if transparent is None:
        transparent = TRANSPARENT
    if rembg_cutout is None:
        rembg_cutout = REMBG_CUTOUT

    init_image_name = None
    if init_image_path and os.path.exists(init_image_path):
        init_image_name = _upload_image(init_image_path)

    control_image_name = None
    if control_image_path and os.path.exists(control_image_path):
        control_image_name = _upload_image(control_image_path)

    def _wf(fd=None, tp=None, rb=None):
        # fd=None means "caller had no opinion" — fall back to the function's
        # face_detail argument, which itself defaults to the global. An explicit
        # False from either level must survive, hence the `is None` checks
        # rather than `or`.
        eff_fd = face_detail if fd is None else fd
        return _build_workflow(prompt, negative=negative, init_image_name=init_image_name, denoise=denoise, width=width, height=height, hires=hires, hires_denoise=hires_denoise, lora_override=lora_override, lora_strength_override=lora_strength_override, face_detail=eff_fd, control_image_name=control_image_name, control_strength=control_strength, control_end=control_end, control_mode=control_mode, transparent=(transparent if tp is None else tp), rembg_cutout=(rembg_cutout if rb is None else rb))

    workflow = _wf()
    prompt_id = _queue_prompt(workflow)
    if not prompt_id and rembg_cutout:
        # ToE_RembgCutout node not installed (or rejected) — retry without it;
        # the backend's own cutout (border-flood) then handles the black-bg output.
        print("[ComfyUI] Queue failed with rembg cutout node — retrying without it.")
        rembg_cutout = False
        workflow = _wf()
        prompt_id = _queue_prompt(workflow)
    if not prompt_id and transparent:
        # LayerDiffuse nodes not installed (or rejected the graph) — fall back
        # to the normal black-bg workflow so the hero still generates. The
        # caller's cutout step then runs as before (output won't be transparent).
        print("[ComfyUI] Queue failed with LayerDiffuse — retrying opaque (black-bg + cutout).")
        transparent = False
        workflow = _wf()
        prompt_id = _queue_prompt(workflow)
    if not prompt_id and FACE_DETAIL:
        # Most likely the Impact Pack nodes aren't available — retry the
        # same generation without the FaceDetailer pass rather than failing.
        print("[ComfyUI] Queue failed with FaceDetailer — retrying without it.")
        workflow = _wf(fd=False)
        prompt_id = _queue_prompt(workflow)
    if not prompt_id and control_image_name:
        # ControlNet nodes rejected (model/nodes missing?) — fall back to a
        # plain prompt-only generation rather than failing the whole subject.
        print("[ComfyUI] Queue failed with ControlNet — retrying prompt-only.")
        control_image_name = None
        workflow = _wf()
        prompt_id = _queue_prompt(workflow)
    if not prompt_id:
        return False

    filename = _wait_for_result(prompt_id)
    if not filename:
        print("[ComfyUI] Timed out waiting for result.")
        return False

    if not _download_image(filename, save_path):
        return False

    # A transparent render (LayerDiffuse OR the rembg cutout node) has no
    # black-void background, so the noise-soup detector below (which keys off
    # "has a large dark region") would wrongly flag every good image. Skip it.
    if transparent or rembg_cutout:
        return True

    # Rare v-pred seed collapse produces full-frame noise soup. Every valid
    # render on this pipeline has a large near-black region (the void
    # background); noise soup has none. Detect and retry once with a fresh
    # seed. `_noise_retry` guards against infinite recursion.
    if not _noise_retry and _looks_like_noise(save_path):
        print("[ComfyUI] Output looks like seed-collapse noise — retrying once.")
        return generate_portrait_comfy(prompt, save_path, init_image_path=init_image_path,
                                       denoise=denoise, negative=negative, width=width, height=height,
                                       hires=hires, hires_denoise=hires_denoise,
                                       lora_override=lora_override, lora_strength_override=lora_strength_override,
                                       _noise_retry=True, control_image_path=control_image_path,
                                       control_strength=control_strength, control_end=control_end, control_mode=control_mode,
                                       transparent=transparent, rembg_cutout=rembg_cutout)
    return True


def _looks_like_noise(path: str) -> bool:
    """True when the image has almost no dark pixels — the signature of a
    collapsed all-noise render on this pipeline (valid portraits always
    carry a large near-black void background)."""
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((64, 64))
        px = list(im.getdata())
        dark = sum(1 for p in px if p < 45)
        return (dark / len(px)) < 0.05
    except Exception:
        return False
