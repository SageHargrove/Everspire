"""Re-cut every character portrait whose transparent version was made by the
old border-flood path. Heroes and monsters both.

WHY THIS EXISTS. Until 2026-08-02 the primary cutout was a border-connected
flood fill. Against a black void, a black garment's antialiased outline dips
below the flood threshold in places, and one such pixel is a doorway — the
flood pours through and hollows the garment from inside. Dark-costumed heroes
came out with severed braids, hollow thighs, and capes reduced to tatters, and
monsters (wraiths, shadows, anything black-bodied) fared worse. The cut is now
segmentation-first (portrait_cache._rembg_union_cutout), but every portrait cut
before that date is still damaged on disk.

No GPU and no regeneration: these all have a retained black-bg master, so this
is a pure re-cut of art that already exists. Faces, names and stats untouched.

    python tools/recut_hero_cutouts.py            # re-cut everything
    python tools/recut_hero_cutouts.py --dry-run  # report what it'd touch
    python tools/recut_hero_cutouts.py --only heroes

Safe to re-run: a one-time .prev.bak per file means the first run's originals
survive even if this runs twice, and the report always measures against that
original rather than against the previous run's output.

Writes docs/cutout-repair.png — a before/after contact sheet of the worst
dozen over a magenta checkerboard, because nobody is going to open 250 PNGs to
check a batch job did the right thing.
"""

import argparse
import os
import shutil
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import numpy as np                                          # noqa: E402
from PIL import Image, ImageDraw                            # noqa: E402

from services.portrait_cache import (                       # noqa: E402
    _border_flood_cutout, _rembg_union_cutout, make_game_cutout,
)

# (group, cutout dir, master dirs searched in order, on-by-default)
# Heroes and monsters keep their masters in different places, which is why
# this can't just lean on portrait_cache._find_master — that only knows about
# the hero locations.
#
# MONSTERS ARE OFF BY DEFAULT, and that is a measured decision, not caution.
# Re-cutting all 123 of them produced 1 improvement and 110 REGRESSIONS
# (death_knight lost 44% of its kept area, mordane 28%). Monster art was never
# cut by the broken flood — it went through make_game_cutout at generation
# time and is already correct. Worse, isnet-anime is an anime CHARACTER
# segmenter: on a spider, a corvid, or a heavily armoured revenant it returns
# little or nothing, so the segmentation-first path that rescues heroes is the
# wrong tool here. Only run --include-monsters if a specific monster is
# visibly broken, and check the contact sheet afterwards.
POOLS = [
    ("heroes", "static/portraits/cutouts_heroes",
     ["static/portraits/masters", "static/portraits/confirmed_heroes"], True),
    ("monsters", "static/portraits/enemies",
     ["static/portraits/curation/monsters/_masters", "static/portraits/masters"], False),
]

# Revert a re-cut that loses this many percentage points of kept area.
#
# Chosen from the measured gap between the two regimes, which is enormous:
# a legitimate improvement that removes the dark halo costs about 0.2pp
# (Mira went 38.7% -> 38.5% while gaining her braid and thighs back), whereas
# real damage ran 9-44pp. Nothing observed lands between 1 and 9, so a
# threshold here separates them cleanly with room to spare.
REVERT_IF_WORSE_BY = 1.5
PROFILE_ROOT = "static/portraits"
SHEET = "../docs/cutout-repair.png"
CELL = (300, 450)


def find_master(name, dirs):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def alpha_of(path):
    im = Image.open(path)
    return np.asarray(im.getchannel("A")) if im.mode == "RGBA" else None


def is_cut(path):
    """Already carries a real cutout. Files still on a solid black background
    are left alone — they were never hooked up, and cutting them here would be
    a different decision than repairing a bad cut."""
    a = alpha_of(path)
    return a is not None and a.min() < 250


def collect(only, include_monsters=False):
    jobs = []
    for group, root, mdirs, on_by_default in POOLS:
        if only and group != only:
            continue
        if not only and not on_by_default and not (include_monsters and group == "monsters"):
            continue
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for f in sorted(files):
                if not f.endswith(".png"):
                    continue
                p = os.path.join(dirpath, f)
                jobs.append((group, p, find_master(f, mdirs)))
    if not only or only == "heroes":
        hero_masters = ["static/portraits/masters", "static/portraits/confirmed_heroes"]
        for name in sorted(os.listdir(PROFILE_ROOT)) if os.path.isdir(PROFILE_ROOT) else []:
            d = os.path.join(PROFILE_ROOT, name, "alive")
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if f.endswith(".png"):
                    jobs.append(("profile", os.path.join(d, f),
                                 find_master(f, hero_masters)))
    return jobs


def recut(path, master):
    """The same ladder _cutout_with_heal runs at generation time.

    The middle rung matters for monsters. isnet-anime is an anime CHARACTER
    segmenter — on a giant spider, a corvid or a wraith it returns ~0% and the
    union has nothing to work with. make_game_cutout's stepped void mask has
    no such assumption, so non-humanoid enemies land there.
    """
    bak = path + ".prev.bak"
    if not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
        except Exception:
            pass
    if _rembg_union_cutout(master, path):
        return True
    # make_game_cutout works IN PLACE on a black-bg image, so the master has to
    # be laid down first. That overwrites the existing cutout with an uncut
    # image — hence the restore below if every remaining rung also fails.
    # Without it a failure would leave a black box where the portrait was.
    try:
        shutil.copy2(master, path)
        if make_game_cutout(path):
            return True
        if _border_flood_cutout(master, path):
            return True
        if os.path.exists(bak):
            shutil.copy2(bak, path)
    except Exception as e:
        print(f"  restore after failed recut: {path}: {e}")
    return False


def checker(size, n=14):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    m = (((xx // n) + (yy // n)) % 2).astype(bool)
    a = np.zeros((h, w, 3), np.uint8)
    a[m] = (226, 0, 226)
    a[~m] = (140, 0, 140)
    return Image.fromarray(a)


def thumb(path):
    im = Image.open(path).convert("RGBA")
    im.thumbnail(CELL, Image.LANCZOS)
    bg = checker(CELL)
    bg.paste(im, ((CELL[0] - im.width) // 2, (CELL[1] - im.height) // 2), im)
    return bg


def build_sheet(changes, limit=12):
    changes = sorted(changes, key=lambda c: -c[1])[:limit]
    if not changes:
        return
    cols = 4
    rows = (len(changes) + cols - 1) // cols
    pw, ph = CELL[0] * 2 + 8, CELL[1] + 26
    sheet = Image.new("RGB", (cols * pw + 16, rows * ph + 16), (14, 11, 20))
    d = ImageDraw.Draw(sheet)
    for i, (path, delta, bak) in enumerate(changes):
        x = 8 + (i % cols) * pw
        y = 8 + (i // cols) * ph
        sheet.paste(thumb(bak), (x, y + 22))
        sheet.paste(thumb(path), (x + CELL[0] + 8, y + 22))
        d.text((x + 2, y + 4),
               f"{os.path.basename(path)[:34]}  +{delta:.1f}% kept   before | after",
               fill=(200, 190, 215))
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    sheet.save(SHEET)
    print(f"\ncontact sheet -> {os.path.abspath(SHEET)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["heroes", "monsters"])
    ap.add_argument("--include-monsters", action="store_true",
                    help="also re-cut enemy art (off by default — see POOLS)")
    args = ap.parse_args()

    jobs = [j for j in collect(args.only, args.include_monsters) if is_cut(j[1])]
    print(f"{len(jobs)} cut portraits found")

    done = skipped = failed = reverted = 0
    changes = []
    per_group = {}

    for group, path, master in jobs:
        if not master:
            skipped += 1
            per_group.setdefault(group, [0, 0])[1] += 1
            continue
        if args.dry_run:
            done += 1
            per_group.setdefault(group, [0, 0])[0] += 1
            continue
        if not recut(path, master):
            failed += 1
            print(f"  FAILED {path}")
            continue
        done += 1
        per_group.setdefault(group, [0, 0])[0] += 1
        # Always measure against .prev.bak — the ORIGINAL, written once and
        # never overwritten. Comparing against the pre-run state made a second
        # run report "nothing improved", since by then run one's output was the
        # baseline. The interesting number is always vs the original.
        bak = path + ".prev.bak"
        after, before = alpha_of(path), (alpha_of(bak) if os.path.exists(bak) else None)
        if before is not None and after is not None:
            # Percentage-point gain in kept area. The two images can differ in
            # size (each cut is trimmed to its own bbox), so compare coverage
            # fractions rather than pixel counts.
            delta = 100 * ((after > 128).mean() - (before > 128).mean())
            if delta < -REVERT_IF_WORSE_BY:
                # A repair tool must never leave a portrait worse than it found
                # it. Put the original back and say so, rather than trusting
                # whoever ran this to diff 270 images afterwards.
                shutil.copy2(bak, path)
                reverted += 1
                done -= 1
                per_group[group][0] -= 1
                print(f"  REVERTED {os.path.basename(path)} ({delta:.1f}% kept area)")
            elif delta > 0.4:
                changes.append((path, delta, bak))

    print(f"\n  re-cut  {done}")
    for g, (ok, sk) in sorted(per_group.items()):
        print(f"      {g:9s} {ok:4d} re-cut, {sk} skipped")
    print(f"  skipped {skipped}  (no retained master — needs regeneration)")
    print(f"  failed  {failed}")
    if reverted:
        print(f"  REVERTED {reverted}  (re-cut came out worse; original restored)")
    if changes:
        print(f"  visibly improved: {len(changes)} "
              f"(best +{max(c[1] for c in changes):.1f}% of frame recovered)")
        build_sheet(changes)
    elif not args.dry_run:
        print("  no measurable change — already cut with the current method")


if __name__ == "__main__":
    main()
