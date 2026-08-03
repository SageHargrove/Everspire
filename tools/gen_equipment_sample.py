"""Generate a small equipment-icon sample against the current hand-made set.

This is a COMPARISON, not a migration. Equipment art is a finite icon set keyed
by type x rarity (134 PNGs, `acc_amulet_legendary.png` style), it carries no
manhwa-LoRA lineage because it was never LoRA output, and it works today. The
only question worth answering first is whether Everspire_Equipment_v1 actually
beats it at icon size — so this renders a handful beside their existing
equivalents and stops.

CHROMA KEY. The equipment LoRA was trained on a magenta plate (deliberately —
the pieces are dark, and a black key would eat them), so its output needs the
magenta removed. Nothing in the game does that today; this is the first code
that has ever needed it, which is exactly why this is a sample and not a
134-icon commitment.

No hires, no FaceDetailer: these render at icon size and have no faces.
"""

import os
import sys
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from services import comfy_service as CS                        # noqa: E402

OUT = os.path.join(ROOT, "docs", "equipment-sample")
ICONS = os.path.join(ROOT, "frontend", "public", "icons")
LORA = "Everspire_Equipment_v1.safetensors:0.8"
NEG = ("photorealistic, 3d render, cgi, blurry, watermark, text, signature, "
       "person, character, hands, 1girl, 1boy, holding")

# Prompted in the trained CAPTION style — short, plain object descriptions.
# Novel phrasing drifts badly here: "a fine recurve longbow of dark wood with
# gold inlay and a leather grip" rendered a SWORD, while the trained wording
# "a recurve bow of dark wood with silver tips" renders a bow. Match the
# captions, don't embellish.
SAMPLES = [
    ("wep_sword_legendary", "an ornate greatsword of blackened steel with gold filigree"),
    ("wep_bow_rare",        "a recurve bow of dark wood with silver tips"),
    ("wep_staff_epic",      "a tall wooden staff topped with a glowing violet crystal"),
    ("wep_dagger_common",   "a plain iron dagger with a leather-wrapped grip"),
    ("arm_plate_legendary", "an ornate silver plate cuirass with engraved wings"),
    ("arm_robe_rare",       "fine dark blue mage robes with gold trim"),
    ("acc_amulet_epic",     "a gold amulet set with a deep violet gemstone"),
    ("acc_ring_uncommon",   "a simple silver ring with a small blue stone"),
]


def chroma_key(path, key=(255, 0, 255), tol=95):
    """Drop the magenta training plate. Distance-based rather than per-channel
    so anti-aliased edge pixels that sit between magenta and the object don't
    survive as a pink fringe."""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    dist = np.sqrt(((a[:, :, :3] - np.array(key)) ** 2).sum(axis=2))
    alpha = np.clip((dist - tol) * 6, 0, 255).astype(np.uint8)
    out = np.dstack([a[:, :, :3].astype(np.uint8), alpha])
    ys, xs = np.where(alpha > 12)
    if ys.size:
        out = out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    Image.fromarray(out, "RGBA").save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(90):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up — aborting.")
        return 1

    for i, (slug, desc) in enumerate(SAMPLES, 1):
        dest = os.path.join(OUT, slug + ".png")
        if os.path.isfile(dest):
            print(f"  [{i}/{len(SAMPLES)}] {slug} — exists")
            continue
        wf = CS._build_workflow(
            desc, negative=NEG, seed=505000 + i * 733,
            width=1024, height=1024, hires=False, lora_override=LORA,
            face_detail=False, transparent=False, rembg_cutout=False,
        )
        pid = CS._queue_prompt(wf)
        fn = CS._wait_for_result(pid) if pid else None
        ok = CS._download_image(fn, dest) if fn else False
        if ok:
            chroma_key(dest)
        print(f"  [{i}/{len(SAMPLES)}] {slug}: {'ok' if ok else 'FAILED'}", flush=True)

    print(f"\nwrote {OUT}")
    print("Compare against frontend/public/icons/ before deciding on all 134.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
