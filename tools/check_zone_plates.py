"""Flag zone plates that won't work as combat backdrops.

Heroes are composited in FRONT of these, so a plate has a job beyond looking
good on its own: it has to read as a place while never competing with the
sprites. Two ways that fails, both seen in real output:

  TOO DARK   - "The Refectory Bones" came out near-black. On its own it reads
               as moody; behind dark hero cutouts it reads as nothing at all,
               and the zone may as well not have art.
  TOO BUSY   - high local contrast across the middle of the frame, where the
               fight happens, makes cutouts hard to pick out.

Thresholds are deliberately loose. This is a shortlist for a human to look at,
not a gate — it prints names, it never deletes anything.

    python tools/check_zone_plates.py
"""

import os

from PIL import Image, ImageFilter, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "frontend", "public", "images", "floor_library")

# Calibrated against real output, not guessed. The art is deliberately dark
# fantasy, so a mean around 30 is NORMAL and a threshold set by intuition
# flagged 19 of 44 — useless as a shortlist. These numbers sit just above the
# one plate confirmed unusable by eye (the_refectory_bones: mean 12.6, 90%
# near-black) and just below plates confirmed fine (the_gilt_arcade: 34.8).
DARK_MEAN = 20          # 0-255 mean luminance
DARK_SHARE = 0.88       # share of pixels below 30
BUSY_EDGE = 30.0        # mean edge energy in the centre band


def main():
    files = sorted(f for f in os.listdir(LIB) if f.endswith(".png"))
    if not files:
        print("no plates found")
        return 0

    dark, busy = [], []
    for fn in files:
        im = Image.open(os.path.join(LIB, fn)).convert("L")
        mean = ImageStat.Stat(im).mean[0]
        hist = im.histogram()
        share = sum(hist[:30]) / float(im.width * im.height)

        # Centre band only — heroes stand across the middle, so edge energy at
        # the very top or bottom of the plate does not compete with them.
        w, h = im.size
        band = im.crop((0, int(h * 0.35), w, int(h * 0.85)))
        edge = ImageStat.Stat(band.filter(ImageFilter.FIND_EDGES)).mean[0]

        if mean < DARK_MEAN or share > DARK_SHARE:
            dark.append((fn, mean, share))
        elif edge > BUSY_EDGE:
            busy.append((fn, edge))

    if dark:
        print(f"TOO DARK ({len(dark)}) — consider rerolling:")
        for fn, mean, share in sorted(dark, key=lambda x: x[1]):
            print(f"  {fn:<44} mean {mean:5.1f}  near-black {share:.0%}")
    if busy:
        print(f"\nBUSY IN THE FIGHT BAND ({len(busy)}) — check cutouts read:")
        for fn, edge in sorted(busy, key=lambda x: -x[1]):
            print(f"  {fn:<44} edge {edge:.1f}")
    if not dark and not busy:
        print(f"all {len(files)} plates within thresholds")
    else:
        print(f"\n{len(files)} plates checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
