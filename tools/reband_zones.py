"""Move zone plates between bands, keeping filename and manifest in step.

Band lives in TWO places — the manifest entry and the "band_slug.png" filename
the draw reads — so editing either alone silently desyncs the library. This
does both, or neither.

Needed because the band descriptions originally said only what each band SHOULD
hold, and the model put lava fields in LOW anyway. The descriptions now carry
explicit NOT clauses, but plates generated before that fix still need moving.

    python tools/reband_zones.py --show                     # what's where
    python tools/reband_zones.py glassworks_deep=high ...   # move them
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "frontend", "public", "images", "floor_library")
MANIFEST = os.path.join(LIB, "zones.json")
BANDS = ("low", "mid", "high")


def load():
    if not os.path.isfile(MANIFEST):
        sys.exit(f"no manifest at {MANIFEST}")
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("moves", nargs="*", metavar="slug=band")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    zones = load()
    by_slug = {z["slug"]: z for z in zones if z.get("slug")}

    if args.show or not args.moves:
        for b in BANDS:
            got = [z for z in zones if z["band"] == b]
            print(f"\n{b} ({len(got)}):")
            for z in sorted(got, key=lambda x: x["slug"]):
                mark = "" if os.path.isfile(
                    os.path.join(LIB, f"{b}_{z['slug']}.png")) else "   [NO ART]"
                print(f"  {z['slug']:<28} {z['name']}{mark}")
        return 0

    # Validate everything BEFORE touching anything — a half-applied reband
    # leaves files and manifest disagreeing, which is the exact failure this
    # tool exists to prevent.
    plan = []
    for m in args.moves:
        if "=" not in m:
            sys.exit(f"expected slug=band, got {m!r}")
        slug, band = m.split("=", 1)
        if band not in BANDS:
            sys.exit(f"{band!r} is not one of {BANDS}")
        if slug not in by_slug:
            sys.exit(f"no zone with slug {slug!r}")
        old = by_slug[slug]["band"]
        if old == band:
            print(f"  {slug} already {band}, skipping")
            continue
        src = os.path.join(LIB, f"{old}_{slug}.png")
        dst = os.path.join(LIB, f"{band}_{slug}.png")
        if os.path.exists(dst):
            sys.exit(f"{dst} already exists — refusing to overwrite")
        plan.append((slug, old, band, src, dst))

    for slug, old, band, src, dst in plan:
        if os.path.isfile(src):
            os.rename(src, dst)
        else:
            print(f"  {slug}: no art yet, manifest only")
        by_slug[slug]["band"] = band
        print(f"  {slug}: {old} -> {band}")

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(zones, f, indent=1, ensure_ascii=False)
    counts = {b: sum(1 for z in zones if z["band"] == b) for b in BANDS}
    print(f"\n{len(plan)} moved. now {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
