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
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from services import comfy_service as CS                          # noqa: E402
from services.portrait_cache import (                             # noqa: E402
    BASE_STYLE, FRAMING, NEGATIVE_STYLE, CLASS_OUTFITS,
    UPGRADE_TAGS, gender_tag_for, negative_for,
    _quality_tag, _tier_flavor, _rembg_union_cutout,
)
from services.base_pool_characters import by_class_gender         # noqa: E402

STAGE = os.path.join(BACKEND, "static", "portraits", "_base_pool_staging")
HERO_LORA_NEW = "Everspire_Heroes_v1.safetensors:0.75,AddMicroDetails_NoobAI_v5.safetensors:0.3"

# TWO RUNGS ONLY: the base look, and one "final form". Not a tuning choice —
# intermediate rungs cannot work, and two attempts proved it.
#
# img2img at an identity-preserving denoise (0.50-0.66) preserves STRUCTURE.
# In practice that means two things, both fatal here:
#   - new gear layers ON TOP of the old outfit instead of replacing it, so a
#     "promotion" reads as the same clothes with extra straps;
#   - defects are preserved perfectly. One character generated with three feet
#     and rungs 2 and 3 reproduced the third foot faithfully; only the highest
#     denoise repainted enough to fix it.
# The denoise that actually re-equips a character (0.74+) is the same one that
# repairs anatomy, and it's the highest you can go before identity drifts
# (0.82 turned a red-streaked brunette into a purple-haired stranger).
#
# So there is exactly one useful jump. Star 4 is where it lands, because that
# is the top of the pool ladder — promotions to 2 and 3 fall through to card-
# frame escalation, and 4 is a real visible re-equip.
# 1 / 4 / 7. Three states, not six: below ~0.66 denoise nothing visibly
# changes, so consecutive stars cannot each show a step. 7 earns its rung
# because it is NOT summonable — the pull ceiling is 6 — so it is purely a
# promotion payoff, and without pool art a non-GPU player could never see it.
POOL_LADDER_STARS = [4, 7]
# 0.72 at 4, measured: a silver cuirass and pauldrons appear while the face and
# a red hair streak survive intact. 0.76 plus weighted identity clauses drifted
# faces, skin and tattoos — both changes pushed the same wrong way.
#
# 7 goes slightly higher because it is the climax and needs the bigger visual
# break, but stays under 0.82, where identity measurably shatters (a
# red-streaked brunette came back purple-haired). Most of 7's extra punch comes
# from language rather than denoise now: _tier_flavor(7) adds "godlike
# legendary being, elaborate ornate armor, dramatic glowing aura" and was never
# being applied until it was fixed this session.
POOL_DENOISE = {4: 0.72, 7: 0.78}

# The base render is where anatomy defects originate, and low-denoise rungs
# inherit them. NEGATIVE_STYLE already carries "extra limb"/"bad anatomy"
# unweighted; full-body framing puts feet at the smallest scale in frame and
# they're the first thing to break, so weight them for the pool specifically.
ANATOMY_NEG = (", (extra legs:1.4), (extra feet:1.4), (three legs:1.4), "
               "(extra arms:1.3), (fused limbs:1.3), (malformed feet:1.3), "
               "(deformed hands:1.2)")

# "Magic Engineer" has a space; the pool filename parser wants one token, and
# portrait_cache._CLASS_DISPLAY maps it back on read.
FILE_CLASS = {"Magic Engineer": "MagicEngineer"}


def slug_class(c):
    return FILE_CLASS.get(c, c.replace(" ", ""))


def render(prompt, dest, star, gender, seed, ref_name=None, denoise=None):
    """One render. Returns the ComfyUI-side filename of the result, or None."""
    # _tier_flavor carries the whole rank escalation ("humble commoner attire,
    # frayed hems" at 1 star, "elite warrior, ornate detailed equipment" at 4).
    # Omitting it made every pool character render with no rank at all, which
    # is why 1-stars came out looking legendary.
    full = (f"{gender_tag_for(gender)}, looking at viewer, {_quality_tag(star)}, "
            f"{FRAMING}, {BASE_STYLE}, {_tier_flavor(star)}, {prompt}")
    wf = CS._build_workflow(
        full, negative=negative_for(None, gender) + ANATOMY_NEG, seed=seed,
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

    cast = by_class_gender()
    classes = sorted(CLASS_OUTFITS)
    jobs = [(c, g, v) for c in classes for g in ("male", "female")
            for v in range(min(args.variants, len(cast.get((c, g), []))))]
    rungs = 1 + len(POOL_LADDER_STARS)
    total = len(jobs) * rungs
    print(f"{len(classes)} classes x 2 genders x {args.variants} variants "
          f"= {len(jobs)} characters, {rungs} rungs each "
          f"(star 1 + {POOL_LADDER_STARS}) = {total} images")
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
        # Authored, not rolled. Trait-list combinatorics kept producing men who
        # read as the same person — six hair styles of which four draw the same
        # head, and no facial hair in the vocabulary at all. These are written
        # to be unlike each other; see services/base_pool_characters.py.
        # One appearance per character, reused across their whole ladder, since
        # the ladder is meant to be the SAME person re-equipped.
        appearance = cast[(klass, gender)][variant]
        base_dest = os.path.join(STAGE, f"ev_{cid:03d}_{slug_class(klass)}_{g}1.png")
        seed = 900000 + cid * 131

        # The RAW render is kept before cutting. It is what seeds the star-up,
        # because the cutout is trimmed to the figure's bounding box — feeding
        # that back in re-renders the character at a different framing and
        # without the black void margins the base had, so the "upgrade" came
        # out smaller and softer than the original. It also doubles as a
        # re-cuttable master.
        raw_dir = os.path.join(STAGE, "_raw")
        os.makedirs(raw_dir, exist_ok=True)
        raw = os.path.join(raw_dir, os.path.basename(base_dest))

        if os.path.isfile(base_dest) and os.path.isfile(raw):
            skipped += 1
        else:
            ok = render(appearance, raw, 1, gender, seed)
            if not ok:
                failed += 1
                print(f"  [{cid}] {klass} {gender} v{variant} 1star FAILED", flush=True)
                continue
            shutil.copy2(raw, base_dest)
            _rembg_union_cutout(base_dest, base_dest)
            made += 1

        # Ladder: anchored on the 1-star RAW original, never on the previous
        # rung and never on the trimmed cutout.
        ref = CS._upload_image(raw)
        for star in POOL_LADDER_STARS:
            dest = os.path.join(STAGE, f"ev_{cid:03d}_{slug_class(klass)}_{g}{star}.png")
            if os.path.isfile(dest):
                skipped += 1
                continue
            # PLAIN description, no emphasis weights. Weighting the identity
            # clauses was tried and backfired: at high denoise a weighted token
            # tells the model to re-draw that feature emphatically, not to
            # preserve it, so faces/skin/tattoos drifted MORE than without it.
            prompt = f"{appearance}, {UPGRADE_TAGS[star]}"
            ok = render(prompt, dest, star, gender, seed, ref_name=ref,
                        denoise=POOL_DENOISE[star])
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
