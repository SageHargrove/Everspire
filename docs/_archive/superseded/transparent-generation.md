# Transparent hero art (cutout)

## ✅ ADOPTED SOLUTION: content-aware cutout node (rembg / isnet-anime)

The "cutout ate part of the hero" problem is caused by dark clothing/hair
being indistinguishable from the black background to any color/connectivity
method (the old void-mask, and the border-flood). The fix is **content-aware
segmentation**, which knows "this is the person" regardless of pixel darkness.
Verified 2026-07-19: it cleanly keeps dark robes/hair that border-flood shreds.

It runs as a tiny custom ComfyUI node so the portrait comes back **already
transparent** — the backend does no cutout at all (it just detects the alpha
and skips). Pieces:

- **Node:** `generation/comfy_nodes/toe_rembg/__init__.py` (`ToE_RembgCutout`,
  wraps rembg isnet-anime). Installed to `ComfyUI/custom_nodes/toe_rembg/`.
  Needs `pip install rembg onnxruntime` in ComfyUI's python.
  (INSTALL_GENERATION.bat does both for fresh installs.)
- **Workflow:** `comfy_service._build_workflow(rembg_cutout=True)` appends the
  node as the final step (after VAEDecode/FaceDetailer) → RGBA → SaveImage.
  ON by default (`COMFY_REMBG_CUTOUT=1`). If the node/queue is rejected,
  generation retries without it and the backend falls back to border-flood.
- **Backend:** `_cutout_with_heal` no-ops on already-transparent art
  (`_has_real_alpha`); border-flood is the dependency-free fallback; the old
  rembg-less `make_game_cutout` never worked at runtime anyway (backend venv
  has no numpy/rembg).

Enable/verify: `layerdiffuse`-style preflight via
`comfy_service.rembg_node_preflight()` → `{"ok": True}` when installed.

Everything below is the ABANDONED LayerDiffuse attempt (kept for reference).

---

# Transparent hero generation (LayerDiffuse) — abandoned

The durable fix for the "cutout ate part of the hero" problem. Instead of
generating on a black background and then keying the black out — which is
ambiguous whenever the figure itself is dark (a black cloak reads as
background and gets erased) — we generate the hero **with a real alpha
channel**. There is no cutout step, so nothing can be eroded.

> ⚠️ **TESTED 2026-07-19 — does NOT work with the current ToE checkpoint.**
> With `noobaiXLNAIXL_vPred10` + the ToE hero LoRA, every LayerDiffuse config
> (Conv/Attention injection, vPred on/off, ±FaceDetailer) produced dim,
> ghostly, near-empty figures — the alpha decoder was trained on base SDXL and
> doesn't transfer to a heavily-tuned vPred model. The scaffold below is left
> in place (OFF) in case a compatible checkpoint is adopted later, but the
> shipped fix is instead **border-flood as the primary hero cutout** (see
> `_cutout_with_heal` in portrait_cache.py) — it produces clean, solid,
> full-body cuts (dark cloaks included) with no generation changes. Don't
> re-enable transparent gen without swapping to a base/eps SDXL checkpoint.

Status: **implemented, OFF by default.** It cannot break current generation —
if the LayerDiffuse nodes aren't installed (or produce bad output) the workflow
falls back to the normal black-bg + cutout path.

## How it's wired

`services/comfy_service.py`:
- `_build_workflow(..., transparent=True)` inserts two nodes:
  - **`LayeredDiffusionApply`** (node 50) after the LoRA/RescaleCFG chain — patches the model so sampling encodes transparency. Every sampler (base, hires, FaceDetailer) inherits it.
  - **`LayeredDiffusionDecodeRGBA`** (node 51) after VAEDecode/FaceDetailer — turns the final latent + RGB into an RGBA image. SaveImage then writes a transparent PNG.
- `generate_portrait_comfy(..., transparent=None)` defaults to the `COMFY_TRANSPARENT` env flag, and **auto-falls-back to opaque** if the LayerDiffuse queue is rejected.

`services/portrait_cache.py`:
- Hero prompts have their black-background tags stripped in transparent mode (`_strip_bg_for_transparent`) so the "black background" instruction doesn't fight the alpha.
- `_cutout_with_heal()` no-ops when the image already has a real alpha channel (`_has_real_alpha`) — so a transparent render is left untouched, and an opaque fallback still gets cut. Nothing else in the pipeline changes.

## Install (in your ComfyUI)

1. Install the custom nodes:
   `ComfyUI/custom_nodes/` → `git clone https://github.com/huchenlei/ComfyUI-layerdiffuse`
   then `pip install -r ComfyUI-layerdiffuse/requirements.txt` into ComfyUI's python.
2. Its SDXL transparent weights download automatically on first use (into
   `ComfyUI/models/layer_model/`), or grab them from the repo's model list.
3. Restart ComfyUI.

## Enable + verify

```
setx COMFY_TRANSPARENT 1        # or set it in the launcher env
```
Preflight check (confirms the nodes are actually present):
```python
from services.comfy_service import layerdiffuse_preflight
print(layerdiffuse_preflight())   # {"ok": True, ...} when installed
```

## Test

1. With `COMFY_TRANSPARENT=1` and ComfyUI up, summon a hero (or trigger a cache
   fill). The saved portrait under `static/portraits/...` should be an **RGBA
   PNG with a transparent background** — open it on a checkerboard to confirm.
2. Specifically test a **dark-clad** hero (black/dark cloak, dark armor) — the
   old failure case. The whole body should be present with clean edges.
3. Confirm no `[Cutout]` log lines fire for that hero (nothing to cut).
4. Flip `COMFY_TRANSPARENT=0` and confirm normal generation still works
   (regression check).

## Tuning knobs (env)

- `COMFY_LAYERDIFFUSE_CONFIG` — default `"SDXL, Conv Injection"`. Try
  `"SDXL, Attention Injection"` if edges/quality disappoint.
- `COMFY_LAYERDIFFUSE_WEIGHT` — default `1.0`.
- `COMFY_FACE_DETAILER=0` — if FaceDetailer interacts badly with the alpha
  decode (it feeds the detailed RGB into the RGBA decode; usually fine).

## Notes / open questions to validate in-env

- LoRA interaction: your hero LoRA (ToE_Heroes_Main) is manhwa-trained on
  black-bg art; transparent generation may shift style slightly. Compare a few
  side-by-side before committing. If style drifts, lowering the LayerDiffuse
  weight or LoRA strength is the first dial.
- The node input/param names above match the current ComfyUI-layerdiffuse repo;
  if a future version renames them, `layerdiffuse_preflight()` will report the
  node missing and generation will fall back safely.
- Monsters/enemies also go transparent when the global flag is on (they suffer
  the same dark-on-black erosion). The bg-tag strip currently only runs on the
  two hero paths — extend it to the enemy prompt builders once heroes look good.
