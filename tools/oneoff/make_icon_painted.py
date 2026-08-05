"""Frame painted concept art into painted-only icons.

    python tools/make_icon_painted.py                      # review sheets
    python tools/make_icon_painted.py everspire_0          # ship -> assets/icon.ico

A painting that reads at 256px is mud at 16px, so small frames use a
PROGRESSIVE CROP: the same painting, zoomed to its focal point (the moon with
the spire through it). At taskbar size that survives as a gold disc with a
dark needle -- still the art, not a substitute glyph.
"""

import os
import sys

from PIL import Image, ImageEnhance

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon import write_ico  # noqa: E402
from make_icon_variants import rrect  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAINTED = os.path.join(ROOT, "assets", "concepts")

# name -> (source png, big crop, small/focal crop) -- normalized square boxes.
# History: scene-paintings (moon+spire) were shipped 07-28 then rejected on
# the real taskbar -- scenes never read as crests. Emblem-style art only.
FINALISTS = {
    # flat_tower_bold = THE shipped icon (GPT-4o simplify-edit of flat_tower,
    # 07-28): same mark redrawn in 5-7 chunky shapes so 16-32px stays solid.
    # Ships at ALL sizes — the two-weight ladder was considered and declined.
    # flat_tower = the detailed original (kept for print/marketing use).
    # diamond_sigil = future in-game sigil. nameless_1 = key art.
    "flat_tower_bold": ("flat_tower_bold.png", (0.06, 0.02, 0.94, 0.90), (0.06, 0.02, 0.94, 0.90)),
    "flat_tower": ("flat_tower.png", (0.0, 0.0, 1.0, 1.0), (0.06, 0.02, 0.94, 0.90)),
    "diamond_sigil": ("diamond_sigil.png", (0.0, 0.0, 1.0, 1.0), (0.14, 0.12, 0.88, 0.86)),
    "nameless_1": ("nameless_1_keyart.png", (0.06, 0.00, 0.94, 0.88), (0.28, 0.06, 0.80, 0.58)),
}

BIG_SIZES = [64, 128, 256]
SMALL_SIZES = [16, 20, 24, 32, 48]


def framed(name, S, focal=False, contrast=1.0):
    """Crop the painting (subject box, or tight focal box) and round the tile.

    Contrast is applied to the RGB crop BEFORE the alpha mask goes on --
    enhancing the finished RGBA would drag the transparent corners toward
    opaque gray.
    """
    src, big_crop, small_crop = FINALISTS[name]
    crop = small_crop if focal else big_crop
    im = Image.open(os.path.join(PAINTED, src)).convert("RGB")
    w, h = im.size
    x0, y0, x1, y1 = crop
    im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    im = im.resize((S, S), Image.LANCZOS)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(im, (0, 0), rrect(S))
    return out


def frames_for(name):
    # small paintings lose punch when downsampled; a mild contrast bump keeps
    # the silhouette-vs-glow separation the tile depends on
    frames = [(s, framed(name, s, focal=True, contrast=1.12)) for s in SMALL_SIZES]
    frames += [(s, framed(name, s)) for s in BIG_SIZES]
    return frames


def sheets(outdir):
    os.makedirs(outdir, exist_ok=True)
    from PIL import ImageDraw, ImageFont
    font = ImageFont.load_default(22)

    pad, cell = 28, 256
    sheet = Image.new("RGBA", (pad + (cell + pad) * len(FINALISTS), cell + 2 * pad + 34),
                      (32, 32, 38, 255))
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(FINALISTS):
        x = pad + i * (cell + pad)
        sheet.alpha_composite(framed(name, cell), (x, pad))
        d.text((x + 4, pad + cell + 8), name, fill=(200, 200, 205), font=font)
    sheet.save(os.path.join(outdir, "painted_sheet_256.png"))

    # what each ships as, across the size ladder (focal crop below 64)
    strip = Image.new("RGBA", (len(FINALISTS) * 330 + 40, 210), (28, 28, 30, 255))
    d = ImageDraw.Draw(strip)
    for i, name in enumerate(FINALISTS):
        x = 40 + i * 330
        frames = dict(frames_for(name))
        cx = x
        for s in (16, 24, 32, 48, 64, 128):
            strip.alpha_composite(frames[s], (cx, 150 - s))
            cx += s + 14
        d.text((x, 178), name, fill=(200, 200, 205), font=font)
    strip.save(os.path.join(outdir, "painted_sheet_ladder.png"))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        name = sys.argv[1]
        path = os.path.join(ROOT, "assets", "icon.ico")
        write_ico(frames_for(name), path)
        framed(name, 256).save(os.path.join(ROOT, "assets", "icon_preview.png"))
        print(f"wrote {path} from painted '{name}'")
    else:
        out = os.environ.get("ICON_PREVIEW_DIR") or os.path.join(ROOT, "assets", "concepts")
        sheets(out)
        print("wrote sheets to", out)
