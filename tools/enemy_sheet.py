"""Contact sheets of the enemy roster, grouped by body plan.

Grouped rather than alphabetical because body plan is what decides the style
block, so a systematic failure shows up as a whole group looking wrong — and
that is invisible in an alphabetical grid where beasts and humanoids alternate.
The 2026-08-04 rebuild was found exactly this way: every bipedal monster was
being rendered as either a pretty anime person or a quadruped, because there
were only two categories for three body plans.

    python tools/enemy_sheet.py
"""

import glob
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from services import portrait_cache as PC                        # noqa: E402
from services.combat_service import ENEMY_TYPES                  # noqa: E402

OUT = os.path.join(ROOT, "docs", "enemy-review")
COLS = 6
TW, TH, LABEL = 240, 336, 20
BG = (30, 25, 35)


def find_art(name):
    slug = "".join(c if c.isalnum() else "_" for c in name.lower())
    hits = glob.glob(f"{PC.ENEMY_DIR}/**/{slug}.png", recursive=True)
    return hits[0] if hits else None


def main():
    os.makedirs(OUT, exist_ok=True)
    groups = {"human": [], "monstrous_humanoid": [], "beast": []}
    missing = []
    for name, *_ in ENEMY_TYPES:
        p = find_art(name)
        (groups[PC.body_plan(name)].append((name, p)) if p else missing.append(name))

    for plan, items in groups.items():
        if not items:
            continue
        items.sort()
        rows = (len(items) + COLS - 1) // COLS
        sheet = Image.new("RGB", (TW * COLS, (TH + LABEL) * rows), BG)
        d = ImageDraw.Draw(sheet)
        for i, (name, p) in enumerate(items):
            x, y = (i % COLS) * TW, (i // COLS) * (TH + LABEL)
            try:
                im = Image.open(p)
            except Exception:
                continue
            c = Image.new("RGB", im.size, BG)
            c.paste(im, (0, 0), im if im.mode == "RGBA" else None)
            sheet.paste(c.resize((TW, TH), Image.LANCZOS), (x, y))
            d.text((x + 5, y + TH + 4), name[:32], fill=(232, 222, 202))
        dest = os.path.join(OUT, f"SHEET_{plan}.png")
        sheet.save(dest)
        print(f"{plan:20} {len(items):3} -> {dest}")

    if missing:
        print(f"\nNO ART ({len(missing)}): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
