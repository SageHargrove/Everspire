"""Giltgrave — content-aware cutout node.

A thin ComfyUI wrapper. The algorithm lives in cutout.py, which the game backend
imports as well, so the two can never drift. See that file for why segmentation
is primary and the flood is only allowed to add.

Output is an RGBA IMAGE that SaveImage writes as a transparent PNG; the backend
then skips its own cutout (portrait_cache._has_real_alpha).

DEPLOYMENT: copy the WHOLE directory, not just this file — it needs cutout.py
beside it. Both installers do (generation_installer.py, INSTALL_GENERATION.bat).
"""
import numpy as np
import torch

from .cutout import cutout_rgba


class ToE_RembgCutout:
    @classmethod
    def INPUT_TYPES(cls):
        # beast: use the general-purpose segmenter instead of the anime one.
        # Defaults False so hero art is untouched; enemy generation sets it for
        # anything not person-shaped. See cutout.SEG_MODEL_BEAST.
        return {"required": {"images": ("IMAGE",)},
                "optional": {"trim": ("BOOLEAN", {"default": True}),
                             "beast": ("BOOLEAN", {"default": False})}}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "cut"
    CATEGORY = "ToE"

    def cut(self, images, trim=True, beast=False):
        from PIL import Image
        out = []
        for img in images:                                   # (H,W,3) float 0-1
            arr = (img.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            rgba = cutout_rgba(Image.fromarray(arr, "RGB"), trim=trim, beast=beast)
            if rgba is None:
                # Gate rejected it, or rembg is missing. Pass the RGB through
                # opaque rather than emit a broken cut: the portrait arrives on
                # its black void and the backend's own ladder gets a turn, which
                # beats shipping a holed hero.
                rgba = Image.fromarray(arr, "RGB").convert("RGBA")
            out.append(np.asarray(rgba).astype(np.float32) / 255.0)

        # Trimming crops each image to its own subject, so a batch can end up
        # ragged and torch.stack would throw. This pipeline generates one
        # portrait at a time (batch_size 1 in _build_workflow), but pad to the
        # batch max rather than assume it — dropping images to make the stack
        # work would lose art silently.
        h = max(a.shape[0] for a in out)
        w = max(a.shape[1] for a in out)
        padded = []
        for a in out:
            if a.shape[0] != h or a.shape[1] != w:
                top, left = (h - a.shape[0]) // 2, (w - a.shape[1]) // 2
                canvas = np.zeros((h, w, 4), np.float32)     # transparent
                canvas[top:top + a.shape[0], left:left + a.shape[1]] = a
                a = canvas
            padded.append(torch.from_numpy(a))
        return (torch.stack(padded, dim=0),)                 # (B,H,W,4)


NODE_CLASS_MAPPINGS = {"ToE_RembgCutout": ToE_RembgCutout}
NODE_DISPLAY_NAME_MAPPINGS = {"ToE_RembgCutout": "ToE Rembg Cutout"}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
