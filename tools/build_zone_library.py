"""Build the shipped zone library: names, blurbs and art, all AI-authored.

ONE GENERATOR FOR BOTH PATHS. llm_service.generate_zone() invents the zone —
name, tile blurb, and the art prompt — and this tool renders it. A player with
generation enabled calls the SAME function for their own tower, so shipped
zones and generated zones come from one place and cannot drift apart in tone.
Exactly the arrangement heroes already have, where the LLM writes
portrait_prompt for both the base pool and live pulls.

Writing 58 scenes by hand was the alternative and it was worse in every way:
slow, capped at my imagination, and structurally different from what players
with GPUs would see.

WHY Everspire_Floors_v1, AFTER CONCLUDING IT WAS BROKEN. It renders one dark
vertical corridor for every prompt at every strength — but ONLY for the prompts
it was tested with, which were long and asked for wide open landscapes. The
frame is 768x1344; "open grey sky to the horizon" cannot fit it, so the model
resolved the contradiction as a vertical smear and it looked like the adapter
had memorised a composition. Given 15-25 word material-and-colour tags that
suit a tall frame, the same adapter at the same 0.85 renders rich distinct
places. Prompt style was the variable, not the LoRA — so this stays on the
in-house adapter and does not take a dependency on third-party ScenicILL.

    python tools/build_zone_library.py --count 60
    python tools/build_zone_library.py --plan-only    # write scenes, no GPU

Resumable: existing slugs are skipped, and the manifest is merged not replaced.
"""

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from PIL import Image                                            # noqa: E402
from services import comfy_service as CS                         # noqa: E402
from services.llm_service import generate_zone                   # noqa: E402
from services.portrait_cache import ENV_GEN_NEGATIVE             # noqa: E402

OUT = os.path.join(ROOT, "frontend", "public", "images", "floor_library")
MANIFEST = os.path.join(OUT, "zones.json")
LORA = "Everspire_Floors_v1.safetensors:0.85"
GEN = (768, 1344)
SHIP = (941, 1672)

# Weighted toward mid: it covers floors 31-70, the widest stretch of a run.
BAND_MIX = {"low": 0.32, "mid": 0.40, "high": 0.28}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]


# Water the scene never asked for is the single biggest driver of sameness.
# Measured on the first mid band: ~17 of 20 plates were the same bright channel
# reflecting down a wet floor, and the three that escaped were the dry ones —
# including scenes like Petrified Orchard and The Stilt Gardens, whose prompts
# mention no water at all. The recipe adds a mirror floor by default, and a
# mirrored floor forces a centred symmetric composition.
#
# So this suppresses water ONLY where the zone didn't call for it. Drowned
# cities and flooded scriptoria still get their water; dry ones stay dry.
WATER_WORDS = ("water", "flood", "drowned", "submerg", "pool", "lake", "sea",
               "river", "brine", "mire", "marsh", "fen", "bog", "swamp",
               "tide", "puddle", "reflect", "rain", "wet", "canal", "cistern",
               "shallow", "lagoon", "mere", "sluice", "millpond", "aqueduct")
DRY_NEGATIVE = ("reflection, reflective floor, standing water, puddles, "
                "wet ground, mirror surface, perfectly symmetrical")


def negative_for(art_prompt):
    """ENV_GEN_NEGATIVE, plus anti-water terms when the scene isn't watery."""
    low = art_prompt.lower()
    if any(w in low for w in WATER_WORDS):
        return ENV_GEN_NEGATIVE
    return ENV_GEN_NEGATIVE + ", " + DRY_NEGATIVE


def load_manifest():
    if os.path.isfile(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_manifest(zones):
    os.makedirs(OUT, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--plan-only", action="store_true",
                    help="invent the zones and write the manifest, render nothing")
    args = ap.parse_args()

    zones = load_manifest()
    have = {z["slug"] for z in zones}
    names = [z["name"] for z in zones]
    print(f"manifest has {len(zones)} zones already")

    # ── invent whatever is missing ──────────────────────────────────────────
    want = {b: max(0, round(args.count * w) - sum(1 for z in zones if z["band"] == b))
            for b, w in BAND_MIX.items()}
    print(f"inventing: {want}")
    # shape_idx advances across the WHOLE run, not per band, so the six spatial
    # types stay evenly spread instead of each band restarting at "sheer face".
    shape_idx = len(zones)
    # Leading tags of recent scenes, fed back so the next zone can't reach for
    # the same materials. Without this six calls produced four bone scenes.
    subjects = [", ".join(z["art_prompt"].split(",")[:2]).strip()
                for z in zones if z.get("art_prompt")]
    for band, n in want.items():
        for i in range(n):
            try:
                z = generate_zone(band, avoid_names=names, shape_idx=shape_idx,
                                  avoid_subjects=subjects)
                shape_idx += 1
                subjects.append(", ".join(z["art_prompt"].split(",")[:2]).strip())
            except Exception as e:
                print(f"  [{band}] zone generation failed: {e}")
                continue
            s = slugify(z["name"])
            if not s or s in have:
                continue
            z["slug"] = s
            zones.append(z)
            have.add(s)
            names.append(z["name"])
            print(f"  [{band}] {z['name']}")
        save_manifest(zones)

    todo = [z for z in zones
            if not os.path.isfile(os.path.join(OUT, f"{z['band']}_{z['slug']}.png"))]
    print(f"\n{len(zones)} zones in manifest, {len(todo)} still need art")
    if args.plan_only:
        return 0

    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(120):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up — aborting.")
        return 1

    made = failed = 0
    t0 = time.time()
    for i, z in enumerate(todo, 1):
        dest = os.path.join(OUT, f"{z['band']}_{z['slug']}.png")
        prompt = (f"no humans, no creatures, empty scenery, dark fantasy, "
                  f"{z['art_prompt']}, masterpiece, best quality, very awa, absurdres")
        wf = CS._build_workflow(prompt, negative=negative_for(z["art_prompt"]),
                                seed=880000 + i * 397, width=GEN[0], height=GEN[1],
                                hires=True, lora_override=LORA, face_detail=False,
                                transparent=False, rembg_cutout=False)
        pid = CS._queue_prompt(wf)
        fn = CS._wait_for_result(pid) if pid else None
        if fn and CS._download_image(fn, dest):
            # Backgrounds stay opaque — never cut these out.
            Image.open(dest).convert("RGB").resize(SHIP, Image.LANCZOS).save(dest)
            made += 1
        else:
            failed += 1
            print(f"  FAILED {z['name']}", flush=True)
        if i % 5 == 0 or i == len(todo):
            rate = (time.time() - t0) / max(made, 1)
            print(f"  [{i}/{len(todo)}] {made} made, {failed} failed, "
                  f"~{(len(todo)-i)*rate/60:.0f}m left", flush=True)

    print(f"\n{made} made, {failed} failed -> {OUT}")
    print(f"manifest: {MANIFEST} ({len(zones)} zones with names + blurbs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
