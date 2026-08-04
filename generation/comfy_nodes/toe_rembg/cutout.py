"""THE character cutout. One implementation, two callers.

    ComfyUI       custom_nodes/toe_rembg/__init__.py  (the normal path)
    game backend  services/portrait_cache.py          (fallback + repairs)

Both import THIS file. It deliberately imports nothing from the game so it can
live inside ComfyUI's python, and it is the only place the algorithm exists —
there used to be a weaker copy in the node and a stronger one in the backend,
which is exactly how the two drifted apart.

WHY SEGMENTATION IS PRIMARY, AND WHY THE FLOOD ONLY ADDS
--------------------------------------------------------
Portraits render on a black void. A colour/connectivity cutout assumes a dark
region touching the frame is background, and on this art that assumption breaks
constantly: black cloaks, black hair and black trousers sit against the void
with an antialiased outline between them, and wherever that outline dips below
threshold — one pixel is enough — a flood fill walks through the gap and eats
the garment from inside. Measured 2026-08-02 on the shipped hero pool: severed
braids, hollowed thighs, full-length capes reduced to tatters.

No threshold fixes this. At a black-on-black boundary there is no difference to
find. It needs a model that knows what a person looks like, so isnet-anime
decides the figure and the flood may only ADD to it.

The union is asymmetric on purpose: a pixel wrongly called foreground is black
on a black void and invisible, while a pixel wrongly called background punches
a hole through a character. When in doubt, keep it.

KNOWN LIMIT: isnet-anime segments anime CHARACTERS. On a spider, a corvid, a
dragon or a heavily armoured revenant it returns almost nothing, and cutout_rgba
returns None so the caller can fall back. Do not use this for monster art.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

SEG_MODEL = "isnet-anime"
# Beasts get a GENERAL segmenter, not the anime-character one.
#
# isnet-anime is trained on anime CHARACTERS. On a spider, a dragon or a dire
# wolf it returns almost nothing, the union falls through to the border flood,
# and the flood then eats every dark region it can reach — which is why dark
# monsters came back with their bodies half dissolved while bright parts (red
# wings, pale fangs) survived. It looked like a flood bug; it was the wrong
# model for the subject.
#
# isnet-general-use is the same architecture trained on general objects, so it
# holds a beast's silhouette without needing a face to latch onto.
SEG_MODEL_BEAST = "isnet-general-use"

# Pixels at or below this are "the void" for connectivity purposes.
VOID_THRESH = 22
# The frame edge must be at least this dark for the flood to apply at all;
# above it the master has a real backdrop and segmentation stands alone.
VOID_BORDER_MAX = 24
# The flood may only contribute pixels brighter than this. The void is not
# mathematically flat — there is a faint glow around every figure sitting just
# over VOID_THRESH, and keeping it opaque wrapped every hero in a dark halo.
# Segmentation already owns the body, so all the flood is needed for is
# detached bright extras: sparks, aura, ground glow, blade shine.
FLOOD_MIN_BRIGHT = 45

_SESSIONS = {}


class SegmenterUnavailable(RuntimeError):
    """rembg/onnxruntime aren't importable here.

    Distinct from cutout_rgba returning None, which means the algorithm ran and
    its own gate rejected the result. The two need different handling: a
    rejection is final, a missing segmenter just means try somewhere else (the
    game backend re-runs this file under ComfyUI's python). Collapsing them
    into one `None` silently disabled that fallback."""


def _session(model=SEG_MODEL):
    """Cached per model — both get used in one run, and building an onnx
    session costs seconds, so a single global would thrash between them."""
    if model not in _SESSIONS:
        from rembg import new_session
        _SESSIONS[model] = new_session(model)
    return _SESSIONS[model]


def _scipy():
    try:
        from scipy import ndimage
        return ndimage
    except Exception:
        return None


def border_is_void(rgb: np.ndarray, probe_max: int = VOID_BORDER_MAX) -> bool:
    """True when the frame edge really is a near-black void."""
    edges = np.concatenate([
        rgb[:3, :, :].reshape(-1, 3), rgb[-3:, :, :].reshape(-1, 3),
        rgb[:, :3, :].reshape(-1, 3), rgb[:, -3:, :].reshape(-1, 3),
    ])
    return int(edges.max()) <= probe_max


def void_flood_fg(rgb: np.ndarray, ndimage, dark_thresh: int = VOID_THRESH) -> np.ndarray:
    """Foreground by border connectivity: near-black pixels reachable from the
    frame edge are background, everything else is figure. Never used alone —
    see the module docstring."""
    maxc = rgb.max(axis=2)
    dark = maxc <= dark_thresh
    if not dark.any():
        return np.ones(maxc.shape, bool)
    lbl, _ = ndimage.label(dark)
    edge = np.unique(np.concatenate([lbl[0, :], lbl[-1, :], lbl[:, 0], lbl[:, -1]]))
    return ~np.isin(lbl, edge[edge != 0])


def trim_rgba(arr: np.ndarray, margin_frac: float = 0.05) -> np.ndarray:
    """Crop to the visible bounding box plus a uniform margin, so every cutout
    fills its frame consistently. Without this a figure occupying half the
    canvas renders half-size on a card next to one that fills it."""
    a = arr[:, :, 3]
    ys, xs = np.where(a > 12)
    if ys.size == 0:
        return arr
    h, w = a.shape
    m = int(round(max(h, w) * margin_frac))
    return arr[max(ys.min() - m, 0):min(ys.max() + 1 + m, h),
               max(xs.min() - m, 0):min(xs.max() + 1 + m, w)]


def cutout_rgba(pil_rgb: Image.Image, trim: bool = True,
                beast: bool = False) -> Image.Image | None:
    """Cut one portrait. Returns RGBA, or None when the result fails the sanity
    gate (caller should fall back rather than ship a broken cut).

    Pass beast=True for anything that is not a person-shaped character. It
    swaps in a general-purpose segmenter; see SEG_MODEL_BEAST above for why
    that matters (the anime model finds nothing on a spider, and the fallback
    flood then dissolves the body).

    Never raises for a missing optional dependency: without scipy it degrades to
    segmentation alone, which is still far better than any flood."""
    rgb = np.asarray(pil_rgb.convert("RGB"))
    try:
        from rembg import remove
    except Exception as e:
        raise SegmenterUnavailable(str(e)) from e
    try:
        seg_a = np.asarray(
            remove(pil_rgb.convert("RGB"),
                   session=_session(SEG_MODEL_BEAST if beast else SEG_MODEL),
                   post_process_mask=True).convert("RGBA")
        )[:, :, 3]
    except Exception as e:
        # Model download failure, corrupt weights, ONNX provider blow-up — all
        # "can't segment here", same as an import failure.
        raise SegmenterUnavailable(str(e)) from e

    fg = seg_a > 100
    ndimage = _scipy()
    flood = None

    if ndimage is not None:
        if border_is_void(rgb):
            flood = void_flood_fg(rgb, ndimage) & (rgb.max(axis=2) > FLOOD_MIN_BRIGHT)
            fg = fg | flood

        # Despeckle: keep the body and anything close enough to read as part of
        # the same illustration (embers, blade glints). Distant dust dies.
        lbl, n = ndimage.label(fg)
        if n > 1:
            sizes = ndimage.sum(fg, lbl, range(1, n + 1))
            main = np.isin(lbl, np.where(sizes >= 64)[0] + 1)
            fg = main | (fg & ndimage.binary_dilation(main, iterations=24))

        # Reclaim enclosed holes: a transparent island completely surrounded by
        # figure is a leak by definition — you cannot see the void through a
        # solid torso. Area-capped so a genuine gap (a ring, a bent elbow) is
        # left alone.
        holes = ndimage.binary_fill_holes(fg) & ~fg
        hl, hn = ndimage.label(holes)
        if hn:
            hsz = ndimage.sum(holes, hl, range(1, hn + 1))
            fg = fg | np.isin(hl, np.where(hsz < 0.02 * fg.size)[0] + 1)

    # Keep isnet-anime's soft edge — it antialiases against the lineart nicely —
    # but force full opacity wherever the flood is certain.
    alpha = seg_a.astype(np.uint16)
    if flood is not None:
        alpha = np.maximum(alpha, flood.astype(np.uint16) * 255)
    alpha = (alpha * fg).clip(0, 255).astype(np.uint8)

    # Sanity gate. Coverage always; on a void master also check that the
    # unambiguously-bright figure survived. Both premises fail on a lit
    # backdrop, which is why the bright test is gated on `flood`.
    opaque = (alpha > 128).mean()
    if not (0.06 < opaque < 0.92):
        return None
    if flood is not None:
        bright = rgb.max(axis=2) > FLOOD_MIN_BRIGHT
        if bright.mean() > 0.02:
            if ((alpha > 200) & bright).sum() / max(bright.sum(), 1) < 0.90:
                return None

    out = np.dstack([rgb, alpha])
    if trim:
        out = trim_rgba(out)
    return Image.fromarray(out, "RGBA")


def main(argv):
    """Runnable as a script: `python cutout.py <in.png> <out.png>`.

    This exists so the game backend can borrow ComfyUI's python. The shipped
    build excludes rembg/onnxruntime (~200MB), so the backend cannot run the
    good algorithm in-process — but any player who can generate a portrait at
    all necessarily has ComfyUI, whose python does have rembg. Shelling out
    there gives a player the identical cutout without adding a byte to the
    download. Exit 0 on success, 1 if the sanity gate rejected it."""
    if len(argv) not in (3, 4):
        print("usage: cutout.py <in.png> <out.png> [--beast]")
        return 2
    try:
        rgba = cutout_rgba(Image.open(argv[1]).convert("RGB"),
                           beast="--beast" in argv)
    except SegmenterUnavailable as e:
        print(f"segmenter unavailable: {e}")
        return 3
    if rgba is None:
        return 1
    rgba.save(argv[2])
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
