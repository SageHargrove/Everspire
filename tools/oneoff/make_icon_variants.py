"""Bold, flat icon concepts -- the design language real game icons use.

    python tools/make_icon_variants.py           # render review sheets
    python tools/make_icon_variants.py slash     # ship one -> assets/icon.ico

Brief: at 32px on a taskbar the shipped icon lost to every neighbour (Discord,
Spotify, Steam) because it was a dark, detailed, low-contrast *scene* with a
thick margin. Icons that survive that context are flat, high-saturation,
single-subject and edge-to-edge -- Persona's are the pure case. So: big colour
fields, one silhouette, nothing thinner than a few percent of the tile.

The subject is a TALL tapered spire, not a castle -- the game is a climb.
Height fills ~88% of the tile; walls batter inward as they rise; windows are
a few arched slits, not dots.
"""

import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon import write_ico  # noqa: E402

GOLD = (235, 180, 64)
GOLD_PALE = (250, 219, 145)
VIOLET = (104, 54, 182)
INK = (16, 9, 28)
CREAM = (246, 239, 226)

SIZES = [16, 20, 24, 32, 48, 64, 128, 256]
RADIUS = 0.215
VARIANTS = ["monolith", "slash", "moonrise", "crest"]


def rrect(S, radius=RADIUS):
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=radius * S, fill=255)
    return mask


def tf(pts, k, dy):
    return [(0.5 + (x - 0.5) * k, 0.5 + (y - 0.5) * k + dy) for x, y in pts]


def spire_pts():
    """Left profile of a slender three-tier spire, mirrored to close.

    Walls batter (lean inward as they rise) so every tier is a subtle
    trapezoid -- vertical walls read as a smokestack, battered ones as
    architecture. Lips are the flared slabs each tier stands under.
    """
    cx = 0.5
    left = [
        (cx - 0.300, 0.940),  # plinth, angled sides
        (cx - 0.255, 0.862),
        (cx - 0.155, 0.862),  # tier 1
        (cx - 0.135, 0.635),
        (cx - 0.185, 0.635),  # lip 1
        (cx - 0.185, 0.600),
        (cx - 0.115, 0.600),  # tier 2
        (cx - 0.100, 0.415),
        (cx - 0.140, 0.415),  # lip 2
        (cx - 0.140, 0.380),
        (cx - 0.075, 0.380),  # tier 3
        (cx - 0.065, 0.245),
        (cx - 0.100, 0.245),  # lip 3
        (cx - 0.100, 0.210),
        (cx - 0.048, 0.210),  # spire cone
        (cx, 0.062),
    ]
    right = [(2 * cx - x, y) for x, y in reversed(left[:-1])]
    return left + right


# Arched slits: (x offset, half width, top y, bottom y). The gate is first.
WINDOWS = [
    (0.000, 0.052, 0.752, 0.862),   # gate
    (-0.075, 0.020, 0.655, 0.732),
    (+0.075, 0.020, 0.655, 0.732),
    (0.000, 0.024, 0.435, 0.552),
    (0.000, 0.018, 0.262, 0.342),
]


def tower_masks(S, k=1.0, dy=0.0, detail=True):
    """-> (silhouette, windows) as L masks."""
    sil = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sil).polygon(
        [(x * S, y * S) for x, y in tf(spire_pts(), k, dy)], fill=255)

    win = Image.new("L", (S, S), 0)
    wd = ImageDraw.Draw(win)
    for off, hw, top, bot in (WINDOWS if detail else WINDOWS[:1]):
        (x0, y0), (x1, y1) = tf([(0.5 + off - hw, top), (0.5 + off + hw, bot)], k, dy)
        r = hw * k * S  # semicircular head on a straight-sided shaft
        wd.ellipse([x0 * S, y0 * S, x1 * S, y0 * S + 2 * r], fill=255)
        wd.rectangle([x0 * S, y0 * S + r, x1 * S, y1 * S], fill=255)
    return sil, ImageChops.multiply(win, sil)


def flat(S, color):
    return Image.new("RGB", (S, S), color)


def render(variant, S, detail=True):
    img = flat(S, INK)
    k, dy = (0.62, -0.030) if variant == "crest" else (1.0, 0.0)
    sil, win = tower_masks(S, k, dy, detail)
    d = ImageDraw.Draw(img)

    if variant == "monolith":
        # Full gold tile -- loudest possible object on a blue/green taskbar.
        # Windows are knocked out to the field colour, a die-cut look.
        img.paste(flat(S, GOLD), (0, 0))
        img.paste(flat(S, INK), (0, 0), sil)
        img.paste(flat(S, GOLD), (0, 0), win)

    elif variant == "slash":
        # The Persona move: one hard diagonal, two loud fields, ink subject.
        img.paste(flat(S, GOLD), (0, 0))
        d.polygon([(0, 0.33 * S), (S, 0.78 * S), (S, S), (0, S)], fill=VIOLET)
        img.paste(flat(S, INK), (0, 0), sil)
        img.paste(flat(S, GOLD_PALE), (0, 0), win)

    elif variant == "moonrise":
        # Poster composition: huge gold moon, the spire cutting through it.
        img.paste(flat(S, VIOLET), (0, 0))
        d.ellipse([0.16 * S, 0.05 * S, 0.84 * S, 0.73 * S], fill=GOLD)
        img.paste(flat(S, INK), (0, 0), sil)
        img.paste(flat(S, CREAM), (0, 0), win)

    elif variant == "crest":
        # The game's own title sigil: gold diamond, spire keyed inside.
        outer = [(0.5, 0.03), (0.97, 0.5), (0.5, 0.97), (0.03, 0.5)]
        d.polygon([(x * S, y * S) for x, y in outer], fill=GOLD)
        d.polygon([(x * S, y * S) for x, y in tf(outer, 0.885, 0)], fill=VIOLET)
        img.paste(flat(S, GOLD), (0, 0), sil)
        img.paste(flat(S, VIOLET), (0, 0), win)

    else:
        raise SystemExit(f"unknown variant: {variant}")

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), rrect(S))
    return out


def frames_for(variant):
    big = render(variant, 1024, detail=True)
    small = render(variant, 512, detail=False)
    return [(s, (small if s <= 32 else big).resize((s, s), Image.LANCZOS))
            for s in SIZES]


def sheets(outdir):
    os.makedirs(outdir, exist_ok=True)
    font = ImageFont.load_default(22)

    pad, cell = 28, 256
    big = Image.new("RGBA", (pad + (cell + pad) * len(VARIANTS), cell + 2 * pad + 34),
                    (32, 32, 38, 255))
    bd = ImageDraw.Draw(big)
    for i, v in enumerate(VARIANTS):
        x = pad + i * (cell + pad)
        big.alpha_composite(render(v, cell), (x, pad))
        bd.text((x + 4, pad + cell + 8), v, fill=(200, 200, 205), font=font)
        render(v, cell).save(os.path.join(outdir, f"{v}_256.png"))
    big.save(os.path.join(outdir, "sheet_256.png"))

    # The judging context: real small sizes plus a 6x blowup of the 32.
    import make_icon
    # detail=False here because that IS what ships at <=32 (see frames_for);
    # judging the full-detail render at this size would flatter nobody fairly.
    entries = [("current", make_icon.render(512, detail=False))]
    entries += [(v, render(v, 512, detail=False)) for v in VARIANTS]
    strip = Image.new("RGBA", (len(entries) * 230 + 40, 340), (28, 28, 30, 255))
    sd = ImageDraw.Draw(strip)
    for i, (name, im) in enumerate(entries):
        x = 40 + i * 230
        for j, s in enumerate((16, 24, 32, 48)):
            strip.alpha_composite(im.resize((s, s), Image.LANCZOS), (x + j * 58, 34))
        strip.alpha_composite(
            im.resize((32, 32), Image.LANCZOS).resize((192, 192), Image.NEAREST),
            (x, 104))
        sd.text((x, 302), name, fill=(200, 200, 205), font=font)
    strip.save(os.path.join(outdir, "sheet_taskbar.png"))


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1:
        v = sys.argv[1]
        path = os.path.join(root, "assets", "icon.ico")
        write_ico(frames_for(v), path)
        render(v, 256).save(os.path.join(root, "assets", "icon_preview.png"))
        print(f"wrote {path} from variant '{v}'")
    else:
        out = os.environ.get("ICON_PREVIEW_DIR") or os.path.join(root, "assets", "concepts")
        sheets(out)
        print("wrote sheets to", out)
