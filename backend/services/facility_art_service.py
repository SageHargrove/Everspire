"""Per-player facility art, with THEIR wall standing behind it.

The shipped facility art is one image per slug/tier, identical for everyone.
This regenerates the outdoor ones per profile with the player's own Wall as a
ControlNet reference, so the fortress they actually built shows up in the
background of the forge they actually built.

WHY CONTROLNET AND NOT A PROMPT. A LoRA has no memory of "the wall" as a
specific object — it shifts rendering, nothing more — and a prompt fragment
("a high dark wall behind") produces a different wall every time. ControlNet
conditions on the wall IMAGE, so the same structure lands in the same place at
the same perspective on every generation. The LoRA owns the style, ControlNet
owns the layout; asking either to do the other's job is what makes this look
impossible.

GENERATED ON BUILD/UPGRADE, NEVER IN BATCH. Rendering all 21 facilities x 4
tiers per player would be ~40 minutes of GPU each. One image per build event
costs the player nothing they didn't already trigger, and mirrors how hero
portraits already work.
"""

import os

import database

# Only the facilities that are actually outdoors can see the wall. An
# alchemy lab in a sealed tower cannot, and pasting one in would read as a
# bug rather than a detail.
EXTERIOR_FACILITIES = {
    "farm", "training_grounds", "skydock", "market", "bastion", "wall",
}

ART_ROOT = "static/facility_art"

# Depth rather than canny: we want the wall's MASS and distance held, not its
# exact edges. Canny would try to reproduce every brick line and fight the
# LoRA's own detailing.
CONTROL_MODE = "depth"
CONTROL_STRENGTH = 0.45     # background anchor, not a tracing
CONTROL_END = 0.35          # release early so the foreground stays free


def art_tier_for_level(level: int) -> int:
    """Level -> art tier. MUST match facArt() in BasePage.jsx (13/26/39
    bands) — if these two drift, the game asks for a tier the generator never
    produced and silently falls back to shipped art forever."""
    if level >= 39:
        return 4
    if level >= 26:
        return 3
    if level >= 13:
        return 2
    return 1


def _profile_dir() -> str:
    return os.path.join(ART_ROOT, database.ACTIVE_PROFILE or "main")


def art_path(slug: str, tier: int) -> str:
    return os.path.join(_profile_dir(), f"{slug}_t{tier}.png")


def art_url(slug: str, tier: int) -> str | None:
    """The player's own art for this facility, or None to fall back to the
    shipped image. Returned in the facilities payload so the frontend never
    has to know the rule."""
    p = art_path(slug, tier)
    return "/" + p.replace("\\", "/") if os.path.isfile(p) else None


def _wall_reference(wall_tier: int) -> str | None:
    """The player's wall image to condition on — their generated one if it
    exists, otherwise the shipped art for that tier."""
    own = art_path("wall", wall_tier)
    if os.path.isfile(own):
        return own
    shipped = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "frontend", "public", "images", "facilities", f"wall_t{wall_tier}.png")
    return shipped if os.path.isfile(shipped) else None


# Scene descriptions per facility. Deliberately terse — generate_environment's
# recipe supplies framing, quality and the no-creature negatives; this is only
# the subject.
SCENES = {
    "farm":              "terraced cultivation beds and irrigation channels, crop rows, tool sheds",
    "training_grounds":  "an open sparring yard, weapon racks, straw dummies, sand underfoot",
    "skydock":           "an airship mooring platform, gantries and hanging chains, open sky",
    "market":            "an open-air market square, stall canopies, crates and hanging goods",
    "bastion":           "a fortified outer keep, battlements and heavy gates",
    "wall":              "a vast fortress wall, ramparts, towers and defensive galleries",
}

TIER_FLAVOR = {
    1: "modest and sparsely built",
    2: "well built and maintained",
    3: "large, elaborate and richly detailed",
    4: "vast, grand and heavily ornamented",
}


def generate_for_facility(slug: str, tier: int, wall_tier: int) -> bool:
    """Render one facility with the player's wall behind it.

    Returns False (never raises) when it isn't applicable or generation is
    off — this is called from build/upgrade handlers and must never be able
    to fail a player's build.
    """
    try:
        if slug not in EXTERIOR_FACILITIES or slug not in SCENES:
            return False
        from routers.settings import get_image_generation_enabled
        if not get_image_generation_enabled():
            return False

        out = art_path(slug, tier)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        tags = f"{SCENES[slug]}, {TIER_FLAVOR.get(tier, TIER_FLAVOR[1])}"
        ref = _wall_reference(wall_tier)
        if ref and slug != "wall":
            # The wall itself is the reference, so conditioning it on itself
            # would just reproduce the input.
            tags += ", a vast fortress wall rising in the background behind"

        from services.comfy_service import generate_portrait_comfy
        from services.portrait_cache import (
            ENV_GEN_PROMPT, ENV_GEN_NEGATIVE, ENV_GEN_LORA, ENV_GEN_SIZE,
        )
        w, h = ENV_GEN_SIZE
        ok = generate_portrait_comfy(
            ENV_GEN_PROMPT.format(tags=tags), out,
            # No FaceDetailer: these are ROOMS. The pass exists so a hero's
            # face survives the base's shoulders-up view; a forge has no face
            # to fix, so it is ~20 sampler steps spent on nothing. hires stays
            # on — facility art IS displayed large.
            negative=ENV_GEN_NEGATIVE, hires=True, face_detail=False,
            lora_override=ENV_GEN_LORA, width=w, height=h,
            control_image_path=(ref if slug != "wall" else None),
            control_mode=CONTROL_MODE,
            control_strength=CONTROL_STRENGTH,
            control_end=CONTROL_END,
        )
        if ok:
            print(f"[FacilityArt] {slug} t{tier} rendered against wall t{wall_tier}")
        return ok
    except Exception as e:
        print(f"[FacilityArt] {slug} t{tier} failed: {e}")
        return False


def queue_for_facility(slug: str, tier: int, wall_tier: int):
    """Fire-and-forget on the portrait worker's thread pool so a build click
    returns immediately instead of waiting ~30s on a render."""
    try:
        import threading
        threading.Thread(target=generate_for_facility, args=(slug, tier, wall_tier),
                         daemon=True, name=f"facility-art-{slug}").start()
    except Exception as e:
        print(f"[FacilityArt] queue failed for {slug}: {e}")
