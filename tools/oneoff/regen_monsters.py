"""Regenerate every enemy portrait with Everspire_Monsters_v1.

WHY. The shipped enemy art was made with ToE_Monsters, one of the manhwa-derived
adapters. Retraining a monster LoRA from ChatGPT-authored source images was the
whole point of that exercise, so leaving the enemy library on the old weights
keeps the lineage in the build that ships.

Everything comes from portrait_cache: ENEMY_PORTRAIT_HINTS carries the long,
specific description for each creature, HUMANOID_ENEMY_NAMES decides which style
prompt and whether FaceDetailer runs, and BOSS hints are their own table. That
detail matters — a short subject line loses to the ~600-character MONSTER_STYLE
block and comes back as a generic demon, which is why these hints are paragraphs.

FaceDetailer is skipped for non-humanoids (68 of 127). It is a face-detect plus
inpaint pass, and on a spider or a dragon it is wasted at best; at worst it
finds something to latch onto and paints a human face on a beast.

    python tools/regen_monsters.py            # all, into staging
    python tools/regen_monsters.py --adopt    # copy staging over the live art

Staged, never in-place: the current enemy art is good and stays untouched until
the new set has been reviewed.
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

from services import comfy_service as CS                         # noqa: E402
from services import portrait_cache as PC                        # noqa: E402

LIVE = os.path.join(BACKEND, "static", "portraits", "enemies")
STAGE = os.path.join(BACKEND, "static", "portraits", "_enemies_staging")
LORA = "Everspire_Monsters_v1.safetensors:0.75,AddMicroDetails_NoobAI_v5.safetensors:0.3"


def targets():
    """(name, hint, is_boss) for everything with a written hint.

    Bosses are keyed by ARCHETYPE, not by name — boss names are invented fresh
    by the LLM each encounter, so there is no stable name to draw against and a
    fight just picks one of these faces. That's why the boss table is
    BOSS_ARCHETYPES rather than a name->hint map like the regular enemies."""
    out = [(n, h, False) for n, h in PC.ENEMY_PORTRAIT_HINTS.items()]
    out += [(k, h, True) for k, h in PC.BOSS_ARCHETYPES.items()]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    if args.adopt:
        n = 0
        for root, _, files in os.walk(STAGE):
            for f in files:
                if not f.endswith(".png"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), STAGE)
                dst = os.path.join(LIVE, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(root, f), dst)
                n += 1
        print(f"adopted {n} enemy portraits into {LIVE}")
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

    jobs = targets()
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(jobs)} enemy portraits to regenerate")

    import re
    made = skipped = failed = 0
    t0 = time.time()
    for i, (name, hint, is_boss) in enumerate(jobs, 1):
        slug = re.sub(r"[^a-z0-9]", "_", name.lower())
        dest = os.path.join(STAGE, ("boss_" if is_boss else "") + slug + ".png")
        if os.path.isfile(dest):
            skipped += 1
            continue

        humanoid = name in getattr(PC, "HUMANOID_ENEMY_NAMES", set())
        if humanoid:
            prompt = (f"{hint}, villain character design, centered composition, "
                      f"imposing menacing pose, dramatic lighting, {PC.HUMANOID_EVIL_STYLE}")
            neg = PC.HUMANOID_EVIL_NEGATIVE
        else:
            prompt = (f"{hint}, monster design, dark fantasy creature, centered composition, "
                      f"menacing pose, dramatic lighting, {PC.MONSTER_STYLE}")
            neg = PC.MONSTER_NEGATIVE
        if is_boss:
            prompt = f"{hint}, {PC.BOSS_EPIC_FLAVOR}, monster design, epic atmosphere, {PC.MONSTER_STYLE}"
            neg = PC.MONSTER_NEGATIVE

        ok = CS.generate_portrait_comfy(
            prompt, dest, negative=neg, lora_override=LORA,
            face_detail=humanoid,          # see module docstring
        )
        if ok:
            PC._cutout_with_heal(dest)
            made += 1
        else:
            failed += 1
            print(f"  FAILED {name}", flush=True)

        if i % 10 == 0 or i == len(jobs):
            rate = (time.time() - t0) / max(made, 1)
            left = (len(jobs) - i) * rate / 60
            print(f"  [{i}/{len(jobs)}] {made} made, {skipped} skipped, "
                  f"{failed} failed, ~{left:.0f}m left", flush=True)

    print(f"\n{made} made, {skipped} skipped, {failed} failed -> {STAGE}")
    print("Review, then: python tools/regen_monsters.py --adopt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
