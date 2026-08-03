"""Generate the shipped base-art pool: every class, both genders, with a real
star-up ladder for each character.

WHY IT'S SHAPED LIKE THIS
-------------------------
The portrait dictates the hero. pop_cached_portrait claims art first, the hero
adopts that portrait's class, and the identity prompt is forced to its gender —
so the POOL'S DISTRIBUTION IS THE PLAYER'S ROSTER DISTRIBUTION. Get the shape
wrong and every non-GPU player lives in it.

The old pool was shaped exactly backwards: 0 portraits at 1-star, which is
70.9% of gem pulls and 95% of gold, against 40 at 6-star, which is 1 pull in
10 000. Common recruits were being dressed in legendary armour.

CHARACTERS, NOT PORTRAITS. Each character is rendered at stars 1-4 as the SAME
person, escalating — img2img anchored on their own 1-star render with a denoise
that scales by star. Non-GPU players therefore get the same "same person, just
stronger" promotion GPU players get, without generating anything. Stars 5-7 are
handled by card-frame escalation instead: non-GPU players rarely reach them and
it costs no art.

Anchoring every star to the ORIGINAL is load-bearing. Chaining each step off the
previous star was measured and fails outright — identity holds perfectly and the
gear never escalates, because each step re-anchors to its own output and
converges. See UPGRADE_DENOISE_BY_STAR in portrait_cache.

    python tools/build_base_pool.py            # full run (~2.5h)
    python tools/build_base_pool.py --variants 1 --stars 2   # quick smoke test

Resumable: an existing file is skipped, so a killed run picks up where it left
off. Writes to a staging dir; nothing touches the live pool until you copy it.
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from services import comfy_service as CS                          # noqa: E402
from services.portrait_cache import (                             # noqa: E402
    BASE_STYLE, FRAMING, NEGATIVE_STYLE, CLASS_OUTFITS,
    UPGRADE_TAGS, UPGRADE_DENOISE_BY_STAR,
    build_appearance_prompt, gender_tag_for, negative_for,
    _quality_tag, _rembg_union_cutout,
)

STAGE = os.path.join(BACKEND, "static", "portraits", "_base_pool_staging")
HERO_LORA_NEW = "Everspire_Heroes_v1.safetensors:0.75,AddMicroDetails_NoobAI_v5.safetensors:0.3"

# "Magic Engineer" has a space; the pool filename parser wants one token, and
# portrait_cache._CLASS_DISPLAY maps it back on read.
FILE_CLASS = {"Magic Engineer": "MagicEngineer"}


def slug_class(c):
    return FILE_CLASS.get(c, c.replace(" ", ""))


def render(prompt, dest, star, gender, seed, ref_name=None, denoise=None):
    """One render. Returns the ComfyUI-side filename of the result, or None."""
    full = (f"{gender_tag_for(gender)}, looking at viewer, {_quality_tag(star)}, "
            f"{FRAMING}, {BASE_STYLE}, {prompt}")
    wf = CS._build_workflow(
        full, negative=negative_for(None, gender), seed=seed,
        width=832, height=1216, hires=True, lora_override=HERO_LORA_NEW,
        init_image_name=ref_name, denoise=(denoise if ref_name else 0.45),
        transparent=False, rembg_cutout=False,
    )
    pid = CS._queue_prompt(wf)
    if not pid:
        return False
    fn = CS._wait_for_result(pid)
    return bool(fn and CS._download_image(fn, dest))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=int, default=2,
                    help="characters per class per gender (default 2)")
    ap.add_argument("--stars", type=int, default=4,
                    help="highest star in the ladder (default 4; 5-7 use frame escalation)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    classes = sorted(CLASS_OUTFITS)
    jobs = [(c, g, v) for c in classes for g in ("male", "female")
            for v in range(args.variants)]
    total = len(jobs) * args.stars
    print(f"{len(classes)} classes x 2 genders x {args.variants} variants "
          f"= {len(jobs)} characters, {args.stars} stars each = {total} images")
    if args.dry_run:
        for c, g, v in jobs[:6]:
            print(f"  e.g. ev_{0:03d}_{slug_class(c)}_{g[0]}1.png")
        return 0

    os.makedirs(STAGE, exist_ok=True)
    if not CS.is_comfy_running():
        CS.ensure_comfy_running()
        for _ in range(120):
            if CS.is_comfy_running():
                break
            time.sleep(4)
    if not CS.is_comfy_running():
        print("ComfyUI never came up — aborting.")
        return 1

    made = skipped = failed = 0
    t0 = time.time()
    for idx, (klass, gender, variant) in enumerate(jobs):
        cid = idx
        g = gender[0]
        # One appearance per character, reused across their whole ladder — the
        # ladder is the same person, so the description must not be rerolled.
        appearance = build_appearance_prompt(1, klass, gender)
        base_dest = os.path.join(STAGE, f"ev_{cid:03d}_{slug_class(klass)}_{g}1.png")
        seed = 900000 + cid * 131

        if os.path.isfile(base_dest):
            skipped += 1
        else:
            ok = render(appearance, base_dest, 1, gender, seed)
            if not ok:
                failed += 1
                print(f"  [{cid}] {klass} {gender} v{variant} 1star FAILED", flush=True)
                continue
            _rembg_union_cutout(base_dest, base_dest)
            made += 1

        # Ladder: every star anchored on the 1-star original, never on the
        # previous star.
        ref = CS._upload_image(base_dest)
        for star in range(2, args.stars + 1):
            dest = os.path.join(STAGE, f"ev_{cid:03d}_{slug_class(klass)}_{g}{star}.png")
            if os.path.isfile(dest):
                skipped += 1
                continue
            prompt = f"{appearance}, {UPGRADE_TAGS[star]}"
            ok = render(prompt, dest, star, gender, seed, ref_name=ref,
                        denoise=UPGRADE_DENOISE_BY_STAR[star])
            if ok:
                _rembg_union_cutout(dest, dest)
                made += 1
            else:
                failed += 1
                print(f"  [{cid}] {klass} {gender} {star}star FAILED", flush=True)

        done = made + skipped + failed
        if cid % 5 == 0 or cid == len(jobs) - 1:
            rate = (time.time() - t0) / max(made, 1)
            left = (total - done) * rate / 60
            print(f"  [{cid+1}/{len(jobs)}] {klass} {gender} — "
                  f"{made} made, {skipped} skipped, {failed} failed, ~{left:.0f}m left",
                  flush=True)

    print(f"\nDone — {made} made, {skipped} skipped, {failed} failed")
    print(f"Staged in {STAGE}")
    print("Review, then copy over static/portraits/cutouts_heroes/ to adopt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
