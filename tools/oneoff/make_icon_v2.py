"""Second-generation vector marks -- one per candidate game name.

    python tools/make_icon_v2.py             # render review sheets
    python tools/make_icon_v2.py nameless    # ship one -> assets/icon.ico

Where the v1 variants were flat colour fields with a silhouette stamped on
(and read as clip art), these add the things good flat icons actually have:
a lit side and a shadow side, rim light where the subject meets the glow,
cast shadows with a hard offset, stepped halo bands instead of gradients.
Still zero blurs and zero smooth ramps -- the language stays flat, the craft
is in the tone steps.

Marks:
  everspire -- the spire against a shaded moon inside stepped halo rings
  ascend    -- a stair-ribbon rising through a gold ring to a diamond spark
  nameless  -- a hooded, faceless figure; the gold diamond hangs where a
               face should be (heroes are nameless until the world remembers)
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icon import write_ico  # noqa: E402
from make_icon_variants import RADIUS, rrect, tf, tower_masks  # noqa: E402

GOLD = (235, 180, 64)
GOLD_DEEP = (186, 130, 38)
GOLD_PALE = (250, 219, 145)
VIOLET = (104, 54, 182)
VIOLET_MID = (88, 44, 158)
VIOLET_DEEP = (70, 32, 130)
INK = (16, 9, 28)
INK_LIFT = (32, 19, 56)
CREAM = (250, 247, 238)

SIZES = [16, 20, 24, 32, 48, 64, 128, 256]
MARKS = ["everspire", "ascend", "nameless"]


def flat(S, color):
    return Image.new("RGB", (S, S), color)


def mask_poly(S, pts):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon([(x * S, y * S) for x, y in pts], fill=255)
    return m


def mask_ellipse(S, cx, cy, r):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=255)
    return m


def diamond(d, S, cx, cy, r, fill):
    d.polygon([(cx * S, (cy - r) * S), ((cx + r * 0.72) * S, cy * S),
               (cx * S, (cy + r) * S), ((cx - r * 0.72) * S, cy * S)], fill=fill)


def shift(mask, S, dx, dy):
    out = Image.new("L", mask.size, 0)
    out.paste(mask, (int(dx * S), int(dy * S)))
    return out


# ---------------------------------------------------------------- everspire

def render_everspire(S, detail=True):
    img = flat(S, VIOLET_DEEP)
    d = ImageDraw.Draw(img)
    mx, my, mr = 0.5, 0.365, 0.315

    # stepped halo rings -- the flat-language stand-in for a glow
    for rr, col in ((0.56, VIOLET_MID), (0.44, VIOLET)):
        d.ellipse([(mx - rr) * S, (my - rr) * S, (mx + rr) * S, (my + rr) * S], fill=col)

    # moon: deep-gold disc with the lit face offset up-left -- the overlap
    # leaves a crescent of shadow on the lower right and the disc stops
    # reading as a flat sticker
    moon = mask_ellipse(S, mx, my, mr)
    img.paste(flat(S, GOLD_DEEP), (0, 0), moon)
    lit = ImageChops.multiply(moon, shift(mask_ellipse(S, mx, my, mr), S, -0.030, -0.030))
    img.paste(flat(S, GOLD), (0, 0), lit)

    if detail:
        for sx, sy, sr in ((0.14, 0.14, 0.020), (0.86, 0.10, 0.014),
                           (0.90, 0.34, 0.017), (0.10, 0.44, 0.013)):
            diamond(d, S, sx, sy, sr, GOLD_PALE)

    sil, win = tower_masks(S, detail=detail)
    img.paste(flat(S, INK), (0, 0), sil)
    # rim light: the moon-facing edge of the silhouette catches gold. Shift
    # the mask off itself and keep the sliver -- a stroke would halo the
    # whole outline instead of one side.
    rim = ImageChops.subtract(sil, shift(sil, S, -0.010, 0.010))
    img.paste(flat(S, GOLD), (0, 0), ImageChops.multiply(rim, ImageChops.invert(win)))
    img.paste(flat(S, GOLD_PALE), (0, 0), win)
    return img


# ------------------------------------------------------------------- ascend

def stair_profile(detail=True):
    """Top profile of the rising stair, left to right. Ends INSIDE the tile --
    the summit needs air above it for the halo and spark."""
    if detail:
        xs, y0, run, rise = 0.035, 0.870, 0.148, 0.138
        n = 4
    else:  # 3 fat treads survive 16px; more mush into a diagonal bar
        xs, y0, run, rise = 0.030, 0.850, 0.235, 0.215
        n = 3
    pts, x, y = [(xs, y0)], xs, y0
    for _ in range(n):
        x += run
        pts.append((x, y))
        y -= rise
        pts.append((x, y))
    pts.append((x + run * 0.85, y))
    return pts


def render_ascend(S, detail=True):
    img = flat(S, VIOLET_DEEP)
    d = ImageDraw.Draw(img)

    top = stair_profile(detail)
    summit_x = (top[-1][0] + top[-2][0]) / 2  # midpoint of the last tread

    # the destination: a shaded gold disc hanging over the summit, same
    # moon treatment as the other marks -- this is what you climb toward
    hx, hy, hr = summit_x, top[-1][1] - 0.115, 0.240 if detail else 0.265
    d.ellipse([(hx - hr - 0.075) * S, (hy - hr - 0.075) * S,
               (hx + hr + 0.075) * S, (hy + hr + 0.075) * S], fill=VIOLET_MID)
    halo = mask_ellipse(S, hx, hy, hr)
    img.paste(flat(S, GOLD_DEEP), (0, 0), halo)
    img.paste(flat(S, GOLD), (0, 0),
              ImageChops.multiply(halo, shift(mask_ellipse(S, hx, hy, hr), S, -0.024, -0.024)))

    if detail:
        for sx, sy, sr in ((0.13, 0.13, 0.018), (0.86, 0.80, 0.015), (0.12, 0.52, 0.013)):
            diamond(d, S, sx, sy, sr, GOLD_PALE)

    thick = 0.175 if detail else 0.240
    ribbon = top + [(x, y + thick) for x, y in reversed(top)]

    # hard-offset cast shadow first, then the ribbon over it
    img.paste(flat(S, INK), (0, 0), mask_poly(S, [(x + 0.022, y + 0.030) for x, y in ribbon]))
    rib = mask_poly(S, ribbon)
    img.paste(flat(S, GOLD_DEEP), (0, 0), rib)
    # lit tread faces: a pale strip along each horizontal top segment
    lift = 0.034 if detail else 0.050
    img.paste(flat(S, GOLD), (0, 0), mask_poly(S, top + [(x, y + lift) for x, y in reversed(top)]))

    segs = [(top[i], top[i + 1]) for i in range(len(top) - 1)
            if abs(top[i][1] - top[i + 1][1]) < 1e-6]
    pd = ImageDraw.Draw(img)
    for (x0, y), (x1, _) in segs:
        pd.rectangle([x0 * S, y * S, x1 * S, (y + lift * 0.42) * S], fill=GOLD_PALE)

    # diamond spark at the disc's heart -- the summit prize
    dr = 0.075 if detail else 0.095
    diamond(pd, S, hx, hy, dr, INK)
    diamond(pd, S, hx, hy, dr * 0.52, CREAM)
    return img


# ----------------------------------------------------------------- nameless

def render_nameless(S, detail=True):
    img = flat(S, VIOLET_DEEP)
    d = ImageDraw.Draw(img)

    # gold halo disc, shaded like the everspire moon
    hx, hy, hr = 0.5, 0.42, 0.335
    for rr, col in ((0.47, VIOLET_MID),):
        d.ellipse([(hx - rr) * S, (hy - rr) * S, (hx + rr) * S, (hy + rr) * S], fill=col)
    halo = mask_ellipse(S, hx, hy, hr)
    img.paste(flat(S, GOLD_DEEP), (0, 0), halo)
    img.paste(flat(S, GOLD), (0, 0),
              ImageChops.multiply(halo, shift(mask_ellipse(S, hx, hy, hr), S, -0.026, -0.026)))

    if detail:
        for sx, sy, sr in ((0.12, 0.16, 0.017), (0.88, 0.12, 0.020), (0.91, 0.42, 0.013)):
            diamond(d, S, sx, sy, sr, GOLD_PALE)

    # cowl at HEAD proportions -- the earlier tile-wide dome read as a cave.
    # Shoulders spread wide, then the fabric tucks in at the neck before the
    # hood swells back out; that pinch is what makes it read as a worn hood.
    left = [(0.03, 1.02), (0.09, 0.815), (0.215, 0.715),  # shoulder line
            (0.268, 0.635),                               # neck tuck
            (0.252, 0.48), (0.275, 0.34), (0.34, 0.235), (0.43, 0.183), (0.5, 0.170)]
    cowl_pts = left + [(1.0 - x, y) for x, y in reversed(left[:-1])]
    cowl = mask_poly(S, cowl_pts)
    img.paste(flat(S, INK), (0, 0), cowl)
    # shoulder-side tone step, kept below the hood so no seam splits the dome
    lit_half = mask_poly(S, [(0.55, 0.68), (1.06, 0.68), (1.06, 1.06), (0.62, 1.06)])
    img.paste(flat(S, INK_LIFT), (0, 0), ImageChops.multiply(cowl, lit_half))

    # the hood's halo-side edge catches the light
    rim = ImageChops.subtract(cowl, shift(cowl, S, -0.011, 0.011))
    img.paste(flat(S, GOLD_DEEP), (0, 0), rim)

    # hood opening: a teardrop void that CLOSES at the chest -- an open-bottom
    # arch read as a doorway. Real outline; the shifted-mask trick leaves
    # dashed slivers on diagonal edges.
    op_pts = [(0.400, 0.630), (0.395, 0.470), (0.430, 0.345), (0.475, 0.305), (0.5, 0.298),
              (0.525, 0.305), (0.570, 0.345), (0.605, 0.470), (0.600, 0.630), (0.5, 0.690)]
    d.polygon([(x * S, y * S) for x, y in op_pts], fill=INK,
              outline=GOLD, width=max(1, int(0.013 * S)))

    # the diamond where a face should be -- the mark of being remembered
    dr = 0.055 if detail else 0.078
    diamond(d, S, 0.5, 0.455, dr, GOLD)
    diamond(d, S, 0.5, 0.455, dr * 0.45, CREAM)
    return img


# ---------------------------------------------------------------- plumbing

RENDERERS = {
    "everspire": render_everspire,
    "ascend": render_ascend,
    "nameless": render_nameless,
}


def render(mark, S, detail=True):
    img = RENDERERS[mark](S, detail)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), rrect(S))
    return out


def frames_for(mark):
    big = render(mark, 1024, detail=True)
    small = render(mark, 512, detail=False)
    return [(s, (small if s <= 32 else big).resize((s, s), Image.LANCZOS))
            for s in SIZES]


def sheets(outdir):
    os.makedirs(outdir, exist_ok=True)
    font = ImageFont.load_default(22)

    pad, cell = 28, 256
    big = Image.new("RGBA", (pad + (cell + pad) * len(MARKS), cell + 2 * pad + 34),
                    (32, 32, 38, 255))
    bd = ImageDraw.Draw(big)
    for i, m in enumerate(MARKS):
        x = pad + i * (cell + pad)
        big.alpha_composite(render(m, cell), (x, pad))
        bd.text((x + 4, pad + cell + 8), m, fill=(200, 200, 205), font=font)
        render(m, cell).save(os.path.join(outdir, f"v2_{m}_256.png"))
    big.save(os.path.join(outdir, "v2_sheet_256.png"))

    strip = Image.new("RGBA", (len(MARKS) * 230 + 40, 340), (28, 28, 30, 255))
    sd = ImageDraw.Draw(strip)
    for i, m in enumerate(MARKS):
        im = render(m, 512, detail=False)
        x = 40 + i * 230
        for j, s in enumerate((16, 24, 32, 48)):
            strip.alpha_composite(im.resize((s, s), Image.LANCZOS), (x + j * 58, 34))
        strip.alpha_composite(
            im.resize((32, 32), Image.LANCZOS).resize((192, 192), Image.NEAREST), (x, 104))
        sd.text((x, 302), m, fill=(200, 200, 205), font=font)
    strip.save(os.path.join(outdir, "v2_sheet_taskbar.png"))


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1:
        m = sys.argv[1]
        path = os.path.join(root, "assets", "icon.ico")
        write_ico(frames_for(m), path)
        render(m, 256).save(os.path.join(root, "assets", "icon_preview.png"))
        print(f"wrote {path} from mark '{m}'")
    else:
        out = os.environ.get("ICON_PREVIEW_DIR") or os.path.join(root, "assets", "concepts")
        sheets(out)
        print("wrote sheets to", out)
