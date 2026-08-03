"""Generate the Windows app icon for Everspire.exe.

Draws the mark procedurally (no external art dependency) in the ILLUMINATED
palette from frontend/src/index.css: a gold-framed gothic arch with the tower
silhouetted against violet light, crowned by a star.

Two detail levels are rendered. The large sizes get window slits, an inner
border and a rim-light; the small sizes (<= 48px) get thicker strokes and none
of that, because at 16px the fine work turns into mud and the silhouette is the
only thing that survives.

    python tools/make_icon.py            # writes assets/icon.ico + previews
"""

import math
import os
import struct

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# ILLUMINATED tokens
GOLD_MAX = (255, 216, 138)
GOLD_HI = (216, 187, 132)
GOLD = (184, 151, 98)
GOLD_DIM = (122, 96, 48)
VIOLET = (181, 123, 239)
VIOLET_DEEP = (139, 70, 214)
LAVENDER = (200, 169, 245)
TOWER_DARK = (9, 6, 20)
PLATE_TOP = (22, 13, 44)
PLATE_BOT = (6, 4, 13)

ICO_SIZES = [16, 20, 24, 32, 48, 64, 128, 256]
SMALL_CUTOFF = 48  # <= this uses the simplified render


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def vgrad(size, top, bottom):
    """Vertical gradient. Drawn one pixel wide then stretched."""
    w, h = size
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        px[0, y] = lerp(top, bottom, y / max(1, h - 1))
    return strip.resize((w, h), Image.BICUBIC)


def radial(size, inner, outer, center, radius):
    """Smooth radial gradient. Computed small and upscaled -- a per-pixel loop
    at working resolution is far too slow and the result is a soft blob anyway."""
    n = 192
    img = Image.new("RGB", (n, n))
    px = img.load()
    cx, cy = center[0] * n, center[1] * n
    r = radius * n
    for y in range(n):
        for x in range(n):
            t = min(1.0, math.hypot(x + 0.5 - cx, y + 0.5 - cy) / r)
            t = t * t * (3 - 2 * t)  # smoothstep, so the falloff has no hard shoulder
            px[x, y] = lerp(inner, outer, t)
    return img.resize(size, Image.LANCZOS)


def arch_outline(cx, half_w, spring_y, apex_y, base_y, steps=120):
    """Two-centred (gothic) arch as a closed point list, normalised units.

    Each arc is centred on the springline at cx +/- c, where c falls out of
    requiring the arcs to meet at (cx, apex_y):  (c + half_w)^2 - c^2 = h^2.
    """
    h = spring_y - apex_y
    c = (h * h - half_w * half_w) / (2 * half_w)
    r = c + half_w
    ax, ay = cx + c, spring_y  # centre of the LEFT arc

    a_end = math.atan2(apex_y - spring_y, cx - ax)
    left_arc = []
    for i in range(steps + 1):
        a = -math.pi + (a_end - -math.pi) * (i / steps)
        left_arc.append((ax + r * math.cos(a), ay + r * math.sin(a)))

    left = [(cx - half_w, base_y)] + left_arc
    right = [(2 * cx - x, y) for (x, y) in reversed(left)]
    return left + right


def tower_outline(cx):
    """Stepped tower: three tiers with overhanging lips, then a spire."""
    tiers = [
        # (top y, half width, lip y, lip half width)
        (0.680, 0.142, 0.660, 0.161),
        (0.520, 0.104, 0.500, 0.122),
        (0.398, 0.070, 0.378, 0.087),
    ]
    base_y = 0.845
    left = [(cx - tiers[0][1], base_y)]
    for i, (top_y, hw, lip_y, lip_hw) in enumerate(tiers):
        left.append((cx - hw, top_y))
        left.append((cx - lip_hw, top_y))
        left.append((cx - lip_hw, lip_y))
        nxt = tiers[i + 1][1] if i + 1 < len(tiers) else 0.052
        left.append((cx - nxt, lip_y))
    left.append((cx - 0.052, 0.348))
    left.append((cx, 0.238))  # spire apex
    right = [(2 * cx - x, y) for (x, y) in reversed(left[:-1])]
    return left + right


def turret_outline(cx, offset, hw, base_y, top_y, cap_y):
    return [
        (cx + offset - hw, base_y),
        (cx + offset - hw, top_y),
        (cx + offset, cap_y),
        (cx + offset + hw, top_y),
        (cx + offset + hw, base_y),
    ]


def star_outline(cx, cy, r, inner=0.17, points=4, rot=0.0):
    """Sharp four-point sparkle."""
    pts = []
    for i in range(points * 2):
        a = -math.pi / 2 + rot + i * math.pi / points
        rad = r if i % 2 == 0 else r * inner
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def render(S, detail=True):
    """Render the mark at S x S, RGBA."""
    def P(pts):
        return [(x * S, y * S) for (x, y) in pts]

    def px(v):
        return max(1, int(round(v * S)))

    cx = 0.5
    margin = int(0.020 * S)
    corner = int(0.185 * S)

    plate_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(plate_mask).rounded_rectangle(
        [margin, margin, S - 1 - margin, S - 1 - margin], radius=corner, fill=255
    )

    # --- plate: vertical gradient screened with a violet bloom behind the arch
    plate = vgrad((S, S), PLATE_TOP, PLATE_BOT)
    bloom = radial((S, S), (48, 20, 96), (0, 0, 0), (0.5, 0.72), 0.60)
    plate = ImageChops.screen(plate, bloom)

    # --- arch interior. The light pools LOW, so the tower's wide base reads
    # dark-on-bright while the spire and star read bright-on-dark. A uniform
    # fill gave the whole mark the same contrast everywhere and went flat.
    arch_pts = arch_outline(cx, 0.290, 0.520, 0.120, 0.862)
    arch_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(arch_mask).polygon(P(arch_pts), fill=255)
    if detail:
        light = radial((S, S), (214, 170, 254), (34, 16, 70), (0.5, 0.80), 0.58)
    else:
        # Small sizes need the whole window bright and roughly even -- the
        # pooled falloff above left the upper tiers as dark-on-dark and the
        # silhouette vanished below 48px.
        light = radial((S, S), (206, 162, 250), (126, 76, 208), (0.5, 0.74), 0.92)
    plate.paste(light, (0, 0), arch_mask)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(plate, (0, 0), plate_mask)
    d = ImageDraw.Draw(img)

    # --- tower + flanking turrets, silhouetted
    silhouette = Image.new("L", (S, S), 0)
    sd = ImageDraw.Draw(silhouette)
    sd.polygon(P(turret_outline(cx, -0.192, 0.034, 0.845, 0.600, 0.522)), fill=255)
    sd.polygon(P(turret_outline(cx, +0.192, 0.034, 0.845, 0.600, 0.522)), fill=255)
    sd.polygon(P(tower_outline(cx)), fill=255)
    silhouette = ImageChops.multiply(silhouette, arch_mask)  # never spill past the frame

    # a dark halo under the silhouette so it stays separated from the glow
    halo = silhouette.filter(ImageFilter.GaussianBlur(px(0.012)))
    img.paste(Image.new("RGB", (S, S), (26, 12, 52)), (0, 0), halo.point(lambda v: v // 2))
    img.paste(Image.new("RGB", (S, S), TOWER_DARK), (0, 0), silhouette)

    if detail:
        # lit windows -- these are what make it read as a tower rather than a shape
        win = Image.new("L", (S, S), 0)
        wd = ImageDraw.Draw(win)
        rows = [
            (0.752, 0.795, [-0.082, 0.000, 0.082], 0.019),
            (0.588, 0.628, [-0.052, 0.052], 0.017),
            (0.438, 0.472, [0.000], 0.015),
        ]
        for top, bot, xs, hw in rows:
            for ox in xs:
                x0, x1 = (cx + ox - hw) * S, (cx + ox + hw) * S
                y0, y1 = top * S, bot * S
                wd.rounded_rectangle([x0, y0, x1, y1], radius=hw * S, fill=255)
        wd.polygon(P([(cx - 0.024, 0.318), (cx, 0.288), (cx + 0.024, 0.318),
                      (cx + 0.024, 0.340), (cx - 0.024, 0.340)]), fill=255)
        win = ImageChops.multiply(win, silhouette)
        glow = win.filter(ImageFilter.GaussianBlur(px(0.020)))
        img.paste(Image.new("RGB", (S, S), (150, 96, 40)), (0, 0), glow)
        img.paste(Image.new("RGB", (S, S), GOLD_MAX), (0, 0), win)

        # rim light down the left edge of the silhouette, etching-style
        rim = Image.new("L", (S, S), 0)
        rd = ImageDraw.Draw(rim)
        rd.line(P(tower_outline(cx)), fill=255, width=px(0.006), joint="curve")
        rim = ImageChops.multiply(rim, silhouette)
        img.paste(Image.new("RGB", (S, S), GOLD_DIM), (0, 0), rim)

    # --- gold arch frame (gradient-filled stroke reads as metal, not flat paint)
    gold_leaf = vgrad((S, S), (244, 216, 162), (118, 90, 44))
    frame = Image.new("L", (S, S), 0)
    fd = ImageDraw.Draw(frame)
    fd.line(P(arch_pts + [arch_pts[0]]), fill=255,
            width=px(0.021 if detail else 0.032), joint="curve")
    if detail:
        inner = arch_outline(cx, 0.248, 0.520, 0.176, 0.836)
        fd.line(P(inner + [inner[0]]), fill=255, width=px(0.006), joint="curve")
    img.paste(gold_leaf, (0, 0), frame)

    # --- plinth
    plinth = Image.new("L", (S, S), 0)
    pd = ImageDraw.Draw(plinth)
    pd.polygon(P([(cx - 0.345, 0.905), (cx + 0.345, 0.905),
                  (cx + 0.318, 0.858), (cx - 0.318, 0.858)]), fill=255)
    if detail:
        pd.rectangle([(cx - 0.300) * S, 0.845 * S, (cx + 0.300) * S, 0.852 * S], fill=255)
    plinth = ImageChops.multiply(plinth, plate_mask)
    img.paste(gold_leaf, (0, 0), plinth)

    # --- crowning star, sitting on the spire tip
    star_cy = 0.182
    star_r = 0.082 if detail else 0.092
    # Darken the window behind the star first. Without this the gold star sits
    # on bright violet at the small sizes and reads as a smudge, not a light.
    shade = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shade).ellipse(
        [(cx - star_r * 1.45) * S, (star_cy - star_r * 1.45) * S,
         (cx + star_r * 1.45) * S, (star_cy + star_r * 1.45) * S], fill=255)
    shade = shade.filter(ImageFilter.GaussianBlur(px(star_r * 0.6)))
    img.paste(Image.new("RGB", (S, S), (28, 12, 58)), (0, 0),
              ImageChops.multiply(shade.point(lambda v: int(v * 0.88)), plate_mask))

    star = Image.new("L", (S, S), 0)
    sd2 = ImageDraw.Draw(star)
    sd2.polygon(P(star_outline(cx, star_cy, star_r, inner=0.135)), fill=255)
    if detail:  # second, rotated sparkle -> eight points; muddies below 48px
        sd2.polygon(P(star_outline(cx, star_cy, star_r * 0.52, inner=0.20,
                                   rot=math.pi / 4)), fill=255)
    burst = star.filter(ImageFilter.GaussianBlur(px(0.034)))
    img.paste(Image.new("RGB", (S, S), (186, 132, 62)), (0, 0),
              burst.point(lambda v: min(255, v * 3)))
    img.paste(Image.new("RGB", (S, S), GOLD_MAX), (0, 0), star)
    core = Image.new("L", (S, S), 0)
    ImageDraw.Draw(core).polygon(P(star_outline(cx, star_cy, star_r * 0.40)), fill=255)
    img.paste(Image.new("RGB", (S, S), (255, 251, 240)), (0, 0), core)

    if detail:
        # inner border + corner bosses, the illuminated-manuscript trim
        b = int(0.062 * S)
        border = Image.new("L", (S, S), 0)
        bd = ImageDraw.Draw(border)
        bd.rounded_rectangle([b, b, S - 1 - b, S - 1 - b],
                             radius=int(0.140 * S), outline=255, width=px(0.005))
        for bx, by in [(0.148, 0.148), (0.852, 0.148), (0.148, 0.852), (0.852, 0.852)]:
            bd.polygon(P(star_outline(bx, by, 0.030, inner=1.0, points=2)), fill=255)
        border = ImageChops.multiply(border, plate_mask)
        img.paste(gold_leaf, (0, 0), border)

    # keep the alpha honest -- everything above pasted RGB only
    img.putalpha(plate_mask)
    return img


def write_ico(frames, path):
    """Write a multi-size .ico from [(size, Image), ...].

    Written by hand because Pillow's ICO writer resamples a single source image
    for every size, which would throw away a separate small-size render.
    """
    from io import BytesIO

    entries, blobs, offset = [], [], 6 + 16 * len(frames)
    for s, im in frames:
        buf = BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        entries.append(struct.pack("<BBBBHHII", s if s < 256 else 0, s if s < 256 else 0,
                                   0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)

    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(frames)))
        for e in entries:
            f.write(e)
        for b in blobs:
            f.write(b)
    return path


def build_ico(path, previews_dir=None):
    big = render(1024, detail=True)
    small = render(512, detail=False)

    frames = []
    for s in ICO_SIZES:
        src = small if s <= SMALL_CUTOFF else big
        frames.append((s, src.resize((s, s), Image.LANCZOS)))

    write_ico(frames, path)
    dict(frames)[256].save(os.path.splitext(path)[0] + "_preview.png")

    if previews_dir:
        os.makedirs(previews_dir, exist_ok=True)
        for s, im in frames:
            im.save(os.path.join(previews_dir, f"preview_{s}.png"))
        big.save(os.path.join(previews_dir, "preview_1024.png"))
    return path


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(root, "assets")
    os.makedirs(assets, exist_ok=True)
    out = build_ico(os.path.join(assets, "icon.ico"),
                    previews_dir=os.environ.get("ICON_PREVIEW_DIR"))
    print("wrote", out)
