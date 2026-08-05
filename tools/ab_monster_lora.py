"""A/B the monster LoRA versions on identical prompts and seeds.

WHY THIS AND NOT "look at the new art". v2 exists to test one hypothesis: that
monster quality lagged hero quality because v1 had ~3 training images per body
plan against heroes' ~34, and that doubling to ~6 fixes it. That claim is only
answerable by holding everything else constant - same creature, same prompt,
same seed, same sampler - and changing ONLY the adapter. Generating a fresh
batch with v2 and eyeballing it proves nothing, because seed variance alone
moves quality more than the effect being measured.

Subjects default to the failures that motivated the retrain, deliberately
spread across body plans:
  quadruped   hellhound was rendered bipedal
  aberrant    obsidian tortoise came out humanoid
  humanoid    kobold rendered as an anime swordsman, not a reptile
  arachnid    a control - spider was already fine, so it should not REGRESS

    python tools/ab_monster_lora.py
    python tools/ab_monster_lora.py --b Everspire_Monsters_v2-000003.safetensors
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

OUT = os.path.join(ROOT, "docs", "lora-ab")
MICRO = "AddMicroDetails_NoobAI_v5.safetensors:0.3"

SUBJECTS = ["Hellhound", "Obsidian Tortoise", "Kobold", "Giant Spider",
            "Harpy", "Marrow-Worm"]


def build(name, lora):
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
    return PC._strip_bg_for_transparent(prompt), neg, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="Everspire_Monsters_v1.safetensors")
    ap.add_argument("--b", default="Everspire_Monsters_v2.safetensors")
    ap.add_argument("--strength", type=float, default=0.75)
    args = ap.parse_args()

    comfy_loras = os.path.join(os.path.expanduser("~"), "ComfyUI", "models", "loras")
    for f in (args.a, args.b):
        if not os.path.isfile(os.path.join(comfy_loras, f)):
            print(f"missing LoRA: {f}\n  looked in {comfy_loras}")
            return 1

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

    rows = []
    for i, name in enumerate(SUBJECTS):
        # The pose is rolled per call, so build ONCE per subject and reuse the
        # identical string for both adapters. Rebuilding per side would let the
        # pose differ and quietly invalidate the comparison.
        prompt, neg, plan = build(name, None)
        seed = 610000 + i * 977
        pair = []
        for tag, lora in (("A", args.a), ("B", args.b)):
            dest = os.path.join(OUT, f"{i}_{tag}_{name.lower().replace(' ', '_')}.png")
            wf = CS._build_workflow(
                prompt, negative=neg, seed=seed, width=832, height=1216,
                hires=False, lora_override=f"{lora}:{args.strength},{MICRO}",
                face_detail=(plan != "beast"), transparent=False,
                rembg_cutout=True, beast=(plan == "beast"))
            pid = CS._queue_prompt(wf)
            fn = CS._wait_for_result(pid) if pid else None
            pair.append(dest if (fn and CS._download_image(fn, dest)) else None)
            print(f"  {name:20} {tag} {'ok' if pair[-1] else 'FAILED'}", flush=True)
        rows.append((name, plan, pair))

    TW, TH = 300, 420
    sheet = Image.new("RGB", (TW * 2, (TH + 26) * len(rows)), (28, 24, 32))
    d = ImageDraw.Draw(sheet)
    for r, (name, plan, pair) in enumerate(rows):
        for c, p in enumerate(pair):
            x, y = c * TW, r * (TH + 26)
            if p and os.path.isfile(p):
                im = Image.open(p)
                bg = Image.new("RGB", im.size, (28, 24, 32))
                bg.paste(im, (0, 0), im if im.mode == "RGBA" else None)
                sheet.paste(bg.resize((TW, TH), Image.LANCZOS), (x, y))
            d.text((x + 6, y + TH + 6),
                   f"{'v1' if c == 0 else 'v2'}  {name} ({plan})", fill=(235, 225, 200))
    dest = os.path.join(OUT, "SHEET_AB.png")
    sheet.save(dest)
    print(f"\nleft column = {args.a}\nright column = {args.b}\n{dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
