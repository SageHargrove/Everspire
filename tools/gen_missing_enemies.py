"""Generate every enemy portrait the game is missing, into the right tier dir.

WHY NOT regen_monsters.py. That tool stages art FLAT and its --adopt copies
preserving relative path, so everything lands in enemies/ root instead of
enemies/<tier>/. The game reads enemies/<tier>/<slug>.png, so the art appears
to generate fine and the game keeps showing the old portraits — a failure that
already happened once and is invisible unless you diff the directory tree.

This calls portrait_cache._generate_enemy_portrait directly instead: the exact
function the in-game startup queue uses. Same prompts, same hints, same
FaceDetailer decision, same output path including the waveN subfolder. There is
no staging step and no adopt step, so there is nothing to get wrong.

    python tools/gen_missing_enemies.py --dry-run
    python tools/gen_missing_enemies.py
    python tools/gen_missing_enemies.py --tier elite
"""

import argparse
import glob
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from services import comfy_service as CS                         # noqa: E402
from services import portrait_cache as PC                        # noqa: E402
from services.combat_service import ENEMY_TYPES                  # noqa: E402


def missing():
    """(name, hint, tier_dir) for every enemy type with no art anywhere."""
    out = []
    for name, *_rest, archetype, _tier in ENEMY_TYPES:
        tier_dir = "elite" if archetype == "elite" else "normal"
        slug = re.sub(r"[^a-z0-9]", "_", name.lower())
        # Same three places the startup queue checks: the tier dir, a waveN
        # subfolder under it (used when art was grouped for review), and the
        # legacy flat root.
        if (os.path.exists(f"{PC.ENEMY_DIR}/{tier_dir}/{slug}.png")
                or glob.glob(f"{PC.ENEMY_DIR}/{tier_dir}/wave*/{slug}.png")
                or os.path.exists(f"{PC.ENEMY_DIR}/{slug}.png")):
            continue
        hint = PC.ENEMY_PORTRAIT_HINTS.get(name, f"{name}, dark fantasy monster")
        out.append((name, hint, tier_dir))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tier", choices=("normal", "elite"))
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    jobs = missing()
    if args.tier:
        jobs = [j for j in jobs if j[2] == args.tier]
    if args.limit:
        jobs = jobs[:args.limit]

    by_tier = {}
    for _, _, t in jobs:
        by_tier[t] = by_tier.get(t, 0) + 1
    print(f"{len(ENEMY_TYPES)} enemy types, {len(jobs)} missing art {by_tier}")
    no_hint = [n for n, h, _ in jobs if n not in PC.ENEMY_PORTRAIT_HINTS]
    if no_hint:
        # A generic hint loses badly to the ~600-char style block and comes back
        # as an anonymous demon, so these are worth writing hints for.
        print(f"\n{len(no_hint)} have NO written hint and will be generic:")
        for n in no_hint:
            print(f"  {n}")
    if args.dry_run:
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
    for i, (name, hint, tier_dir) in enumerate(jobs, 1):
        try:
            PC._generate_enemy_portrait(name, hint, tier_dir)
            slug = re.sub(r"[^a-z0-9]", "_", name.lower())
            ok = (os.path.exists(f"{PC.ENEMY_DIR}/{tier_dir}/{slug}.png")
                  or glob.glob(f"{PC.ENEMY_DIR}/{tier_dir}/wave*/{slug}.png"))
            if ok:
                made += 1
            else:
                failed += 1
                print(f"  NO FILE {tier_dir}/{name}", flush=True)
        except Exception as e:
            failed += 1
            print(f"  FAILED {name}: {e}", flush=True)
        if i % 5 == 0 or i == len(jobs):
            rate = (time.time() - t0) / max(made, 1)
            print(f"  [{i}/{len(jobs)}] {made} made, {failed} failed, "
                  f"~{(len(jobs)-i)*rate/60:.0f}m left", flush=True)

    print(f"\n{made} made, {failed} failed -> {PC.ENEMY_DIR}/<tier>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
