"""Regenerate the 11 tower zone plates with Everspire_Floors_v1.

The existing plates were made with ScenicILL, a third-party scenery LoRA — not
the manhwa-derived hero/monster adapters, so they were never part of the
lineage problem. They're regenerated anyway for STYLE CONSISTENCY: once heroes
and monsters are on the Everspire adapters, a scenery set from a different
LoRA is the odd one out.

Prompts come from each zone's own name and blurb in TowerPage.jsx, so the art
matches what the game already tells the player about the zone. That matters —
the current plates are well matched to their zones, and a regeneration that
loses that would be a downgrade even if it looked nicer in isolation.

Size: the shipped plates are 941x1672 (0.563). The floors LoRA trained at
768x1344 (0.571), the nearest SDXL bucket, so generate there with hires and
downscale — rather than generating off-ratio and cropping the composition.

    python tools/regen_zone_floors.py               # all 11, into staging
    python tools/regen_zone_floors.py --adopt       # copy staging over the live plates

Never writes over the live plates without --adopt, so the current art survives
until the new set has been eyeballed.
"""

import argparse
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from PIL import Image                                             # noqa: E402
from services import comfy_service as CS                          # noqa: E402
from services.portrait_cache import ENV_GEN_NEGATIVE              # noqa: E402

LIVE = os.path.join(ROOT, "frontend", "public", "images", "floors")
STAGE = os.path.join(ROOT, "frontend", "public", "images", "_floors_staging")
LORA = "Everspire_Floors_v1.safetensors:0.85"
GEN_SIZE = (768, 1344)      # the bucket the LoRA trained at
OUT_SIZE = (941, 1672)      # what the game ships

# slug -> scene description. Taken from the zone's own name + blurb so the art
# keeps agreeing with the text the player reads on the zone tile.
ZONES = {
    "overgrown_caverns":
        "a vast root-choked underground cavern, thick tangled roots and hanging vines, "
        "glowing green fungal light, still black pools between stone shelves",
    "savage_badlands":
        "sun-cracked badlands of red rock under a burning sky, jagged mesas, "
        "bleached bones and broken siege timber half-buried in dust",
    "sunken_swamp":
        "a fetid sunken mire, black water between dead trees, thick green miasma, "
        "half-submerged ruins and rotted boardwalks",
    "profane_catacombs":
        "desecrated catacomb halls, stacked bone niches and toppled sarcophagi, "
        "violet grave-light from cracked stone, dust hanging in still air",
    "dread_peaks":
        "storm-lashed mountain summits above churning cloud, lightning between "
        "black spires, wind-torn banners on a narrow ridge",
    "crystalline_depths":
        "a labyrinth of living stone and enormous blue crystal formations, "
        "refracted cold light, geometric corridors of fused rock",
    "leviathans_graveyard":
        "a drowned dark full of colossal leviathan ribs rising from black silt, "
        "wrecked hulls, cold bioluminescence in deep water",
    "blood_lake":
        "a still crimson lake under a blood moon, drowned gothic spires breaking "
        "the surface, red mist over red water",
    "abyssal_rift":
        "a wound torn in reality, a violet void fissure bleeding light over "
        "shattered floating rock, embers drawn into the tear",
    "dragons_boneyard":
        "the final ascent, an immense dragon skeleton draped over black peaks, "
        "ribs arching above the path, ash and cold fire below",
    "ashen_depths":
        "a molten depth of ash and cooling lava channels between black rock "
        "shelves, drifting ash like snow, distant fire glow",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adopt", action="store_true",
                    help="copy the staged plates over the live ones")
    ap.add_argument("--only", help="regenerate a single slug")
    args = ap.parse_args()

    if args.adopt:
        n = 0
        for slug in ZONES:
            src = os.path.join(STAGE, f"{slug}.png")
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(LIVE, f"{slug}.png"))
                n += 1
        print(f"adopted {n}/{len(ZONES)} plates into {LIVE}")
        return 0

    os.makedirs(STAGE, exist_ok=True)
    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(90):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up — aborting.")
        return 1

    todo = {args.only: ZONES[args.only]} if args.only else ZONES
    made = failed = 0
    for i, (slug, scene) in enumerate(todo.items(), 1):
        dest = os.path.join(STAGE, f"{slug}.png")
        if os.path.isfile(dest):
            print(f"[{i}/{len(todo)}] {slug} — already staged")
            continue
        print(f"[{i}/{len(todo)}] {slug}...", flush=True)
        prompt = (f"no humans, no creatures, empty scenery, dark fantasy, {scene}, "
                  f"intricate detailed background, atmospheric lighting, "
                  f"masterpiece, best quality, very awa, absurdres")
        wf = CS._build_workflow(
            prompt, negative=ENV_GEN_NEGATIVE, seed=606060 + i * 977,
            width=GEN_SIZE[0], height=GEN_SIZE[1], hires=True,
            lora_override=LORA, transparent=False, rembg_cutout=False,
        )
        pid = CS._queue_prompt(wf)
        fn = CS._wait_for_result(pid) if pid else None
        if fn and CS._download_image(fn, dest):
            # Backgrounds are opaque by design — no cutout, ever.
            Image.open(dest).convert("RGB").resize(OUT_SIZE, Image.LANCZOS).save(dest)
            made += 1
            print("    ok")
        else:
            failed += 1
            print("    FAILED")

    print(f"\n{made} made, {failed} failed -> {STAGE}")
    print("Review, then: python tools/regen_zone_floors.py --adopt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
