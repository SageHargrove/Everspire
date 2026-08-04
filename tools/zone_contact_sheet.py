"""Contact sheets for the zone library, one per band, for eyeballing the set.

The library is 64 plates at 941x1672; opening them one at a time is how a dull
repeat slips through. Grouped by band because that is how a player meets them —
if every LOW zone looks alike, a new player's whole first run looks alike, and
that matters more than the library being varied in aggregate.

    python tools/zone_contact_sheet.py
"""

import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "frontend", "public", "images", "floor_library")
OUT = os.path.join(ROOT, "docs", "zone-library")

COLS = 5
TW, TH = 300, 525        # keeps the 768x1344 aspect
LABEL = 30


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = os.path.join(LIB, "zones.json")
    zones = []
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as f:
            zones = json.load(f)
    by_slug = {z["slug"]: z for z in zones if z.get("slug")}

    for band in ("low", "mid", "high"):
        files = sorted(f for f in os.listdir(LIB)
                       if f.startswith(band + "_") and f.endswith(".png"))
        if not files:
            continue
        rows = (len(files) + COLS - 1) // COLS
        sheet = Image.new("RGB", (TW * COLS, (TH + LABEL) * rows), (16, 16, 18))
        d = ImageDraw.Draw(sheet)
        for i, fn in enumerate(files):
            x, y = (i % COLS) * TW, (i // COLS) * (TH + LABEL)
            try:
                im = Image.open(os.path.join(LIB, fn)).convert("RGB")
            except Exception as e:
                print(f"  unreadable {fn}: {e}")
                continue
            sheet.paste(im.resize((TW, TH), Image.LANCZOS), (x, y))
            slug = fn[len(band) + 1:-4]
            name = by_slug.get(slug, {}).get("name", slug)
            d.text((x + 8, y + TH + 9), name[:38], fill=(235, 225, 200))
        dest = os.path.join(OUT, f"SHEET_{band}.png")
        sheet.save(dest)
        print(f"{band}: {len(files)} plates -> {dest}")

    total = len([f for f in os.listdir(LIB) if f.endswith(".png")])
    print(f"\n{total} plates in the library, {len(zones)} zones in the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
