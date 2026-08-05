"""Generate a broad cross-section of the roster with a chosen monster LoRA.

The A/B proved v2 beats v1 on six subjects. This answers the different question
of whether it HOLDS across the roster: six samples cannot show a body plan that
collapses, or a systematic tic that only appears once you see twenty together.

Writes to docs/v2-scale/ and never touches live enemy art, so the roster stays
on v1 until the switch is a deliberate decision.

    python tools/v2_scale_test.py
    python tools/v2_scale_test.py --lora Everspire_Monsters_v1.safetensors
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from PIL import Image, ImageDraw                                 # noqa: E402
from services import comfy_service as CS                         # noqa: E402
from services import portrait_cache as PC                        # noqa: E402

OUT = os.path.join(ROOT, "docs", "v2-scale")
MICRO = "AddMicroDetails_NoobAI_v5.safetensors:0.3"

# Deliberately spread across every body plan, weighted toward the ones that
# were thin in v1 training and toward the specific renders that failed before.
SUBJECTS = [
    # beasts - quadruped
    "Wolf", "Nemean Lion", "Dire Sabertooth", "Hellhound",
    # beasts - serpentine / aquatic / aberrant (thinnest plans in v1)
    "Abyssal Serpent", "Abyssal Lamprey", "Bone-Crab Scavenger", "Void Horror",
    # beasts - arachnid / insect / winged
    "Venomous Spider", "Grave Scarab", "Wyvern", "Griffon",
    # monstrous humanoids
    "Goblin", "Orc", "Troll", "Lizardman", "Skeleton", "Wraith",
    # human control - should stay a person
    "Bandit",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lora", default="Everspire_Monsters_v2.safetensors")
    ap.add_argument("--strength", type=float, default=0.75)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(120):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up - aborting.")
        return 1

    made = []
    for i, name in enumerate(SUBJECTS):
        hint = PC.ENEMY_PORTRAIT_HINTS.get(name, f"{name}, dark fantasy monster")
        plan = PC.body_plan(name)
        if plan == "human":
            prompt = (f"{hint}, villain character design, centered composition, "
                      f"{PC._enemy_pose(plan)}, dramatic lighting, {PC.HUMANOID_EVIL_STYLE}")
            neg = PC.HUMANOID_EVIL_NEGATIVE
        elif plan == "monstrous_humanoid":
            prompt = (f"{hint}, humanoid monster design, centered composition, "
                      f"{PC._enemy_pose(plan)}, dramatic lighting, {PC.MONSTROUS_HUMANOID_STYLE}")
            neg = PC.MONSTROUS_HUMANOID_NEGATIVE
        else:
            prompt = (f"{hint}, monster design, dark fantasy creature, centered composition, "
                      f"{PC._enemy_pose(plan)}, dramatic lighting, {PC.MONSTER_STYLE}")
            neg = PC.MONSTER_NEGATIVE
        prompt = PC._strip_bg_for_transparent(prompt)

        dest = os.path.join(OUT, f"{i:02d}_{name.lower().replace(' ', '_').replace('-', '_')}.png")
        wf = CS._build_workflow(
            prompt, negative=neg, seed=730000 + i * 641, width=832, height=1216,
            hires=False, lora_override=f"{args.lora}:{args.strength},{MICRO}",
            face_detail=(plan != "beast"), transparent=False,
            rembg_cutout=True, beast=(plan == "beast"))
        pid = CS._queue_prompt(wf)
        fn = CS._wait_for_result(pid) if pid else None
        if fn and CS._download_image(fn, dest):
            made.append((name, plan, dest))
        else:
            print(f"  FAILED {name}", flush=True)
        if (i + 1) % 5 == 0:
            print(f"  [{i+1}/{len(SUBJECTS)}]", flush=True)

    COLS, TW, TH = 5, 250, 350
    rows = (len(made) + COLS - 1) // COLS
    sheet = Image.new("RGB", (TW * COLS, (TH + 22) * rows), (28, 24, 32))
    d = ImageDraw.Draw(sheet)
    for i, (name, plan, p) in enumerate(made):
        x, y = (i % COLS) * TW, (i // COLS) * (TH + 22)
        im = Image.open(p)
        bg = Image.new("RGB", im.size, (28, 24, 32))
        bg.paste(im, (0, 0), im if im.mode == "RGBA" else None)
        sheet.paste(bg.resize((TW, TH), Image.LANCZOS), (x, y))
        d.text((x + 5, y + TH + 5), f"{name} ({plan[:5]})", fill=(235, 225, 200))
    dest = os.path.join(OUT, "SHEET_SCALE.png")
    sheet.save(dest)
    print(f"\n{len(made)}/{len(SUBJECTS)} with {args.lora}\n{dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
