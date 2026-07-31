from fastapi import APIRouter, HTTPException, Body
from database import db
from pydantic import BaseModel
import json
import random
import re

router = APIRouter()

@router.get("/")
def get_base():
    from services.time_service import process_fatigue_decay, process_passive_generation
    from services.research_service import process_mage_research
    from services.athenaeum_service import process_athenaeum
    from services.alchemist_service import process_alchemist_lab
    from services.restaurant_service import process_restaurant
    from services.infirmary_service import process_infirmary
    from services.sanctum_service import process_tavern, process_shrine
    from services.training_service import process_training
    from routers.gacha import maybe_reconcile_pending_profiles
    maybe_reconcile_pending_profiles()
    with db() as conn:
        process_fatigue_decay(conn)
        process_passive_generation(conn)
        process_mage_research(conn)
        process_athenaeum(conn)
        process_alchemist_lab(conn)
        process_restaurant(conn)
        process_infirmary(conn)
        process_tavern(conn)
        process_shrine(conn)
        process_training(conn)
        row = conn.execute("SELECT * FROM base WHERE id = 1").fetchone()
        result = dict(row)
        # fairy_gender is left NULL until the player picks one on the intro
        # screen (POST /base/fairy). Null signals the frontend to show the
        # chooser; tips fall back to 'female' visually until then.
        #
        # World name: every profile is its own universe, and the universe
        # names itself — rolled once on first load, never player-editable
        # (players customize their master name / teams / guild, not the
        # world). 'The Hollow Spire' is the un-rolled schema default.
        if not result.get("name") or result["name"] == "The Hollow Spire":
            result["name"] = _generate_world_name(conn)
            conn.execute("UPDATE base SET name = ? WHERE id = 1", (result["name"],))
    return result


# Syllabic fantasy world names in the Pick-Me-Up register (Niflheimr, Townia,
# Taonere...): stem + terminal, occasionally a linking vowel. ~40x14x2 forms.
_WORLD_STEMS = [
    "Nifl", "Thal", "Vael", "Aer", "Torv", "Ish", "Kael", "Mor", "Eryn", "Vosk",
    "Ael", "Bryn", "Cind", "Drav", "Elm", "Fenn", "Gal", "Hollow", "Ilv", "Jor",
    "Kryst", "Lorn", "Myr", "Nav", "Oth", "Pell", "Quor", "Rav", "Sol", "Tarn",
    "Uld", "Vint", "Wyrd", "Xan", "Ymir", "Zephyr", "Ostr", "Grim", "Ard", "Sylv",
]
_WORLD_ENDS = [
    "heimr", "ia", "onia", "ere", "gard", "mir", "eth", "ande", "oria", "wyn",
    "fell", "reach", "mark", "vale",
]

def _generate_world_name(conn) -> str:
    import random as _r
    for _ in range(12):
        stem = _r.choice(_WORLD_STEMS)
        end = _r.choice(_WORLD_ENDS)
        link = _r.choice(["", "a", "e", "o"]) if stem[-1] not in "aeiou" and end[0] not in "aeiou" else ""
        name = stem + link + end
        if len(name) <= 12:
            return name.capitalize()
    return "Niflheimr"

@router.post("/fairy")
def choose_fairy(payload: dict = Body(...)):
    """Player picks their tutorial fairy guide (male/female) on first launch.
    Idempotent-ish: allows changing until the tutorial is completed."""
    gender = payload.get("fairy_gender")
    if gender not in ("male", "female"):
        raise HTTPException(status_code=400, detail="fairy_gender must be 'male' or 'female'")
    with db() as conn:
        conn.execute("UPDATE base SET fairy_gender = ? WHERE id = 1", (gender,))
    return {"ok": True, "fairy_gender": gender}

@router.post("/upgrade")
def upgrade_base():
    """Upgrades the base level and increases max heroes."""
    from database import db
    from fastapi import HTTPException
    with db() as conn:
        base = conn.execute("SELECT level, gold, max_roster_size FROM base WHERE id = 1").fetchone()
        lvl = base["level"]
        cost = 5000 * lvl
        if base["gold"] < cost:
            raise HTTPException(status_code=400, detail=f"Not enough gold. Need {cost}.")
        conn.execute("UPDATE base SET gold = gold - ?, level = level + 1, max_roster_size = max_roster_size + 10 WHERE id = 1", (cost,))
    return {"ok": True}

class RenameRequest(BaseModel):
    name: str

@router.post("/rename")
def rename_base(req: RenameRequest):
    # World names are granted by the Tower (randomly generated), never chosen.
    # Players customize master name / team names / guild names only.
    raise HTTPException(status_code=403, detail="The Tower names every world. Yours is already spoken.")

class MasterNameRequest(BaseModel):
    name: str

@router.post("/master-name")
def set_master_name(req: MasterNameRequest):
    """The player's own chosen name — distinct from base.name (the tower's
    name). Heroes refer to the player generically as 'the Master' in flavor
    text until this is set, after which that text uses the real name."""
    if not req.name or len(req.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    with db() as conn:
        conn.execute("UPDATE base SET master_name = ? WHERE id = 1", (req.name.strip()[:24],))
    return {"ok": True, "master_name": req.name.strip()[:24]}

TUTORIAL_COMPLETION_GEMS = 500

@router.post("/tutorial/complete")
def complete_tutorial():
    """Marks the tutorial as seen (so it never shows again on this profile)
    and grants the starter-gem bonus — awarded whether the player finished
    every step or hit Skip, since the point is getting them into their first
    summon either way, not gating the reward on sitting through the whole thing."""
    with db() as conn:
        already = conn.execute("SELECT tutorial_complete FROM base WHERE id = 1").fetchone()
        if already and already["tutorial_complete"]:
            return {"ok": True, "already_complete": True, "gems_granted": 0}
        conn.execute(
            "UPDATE base SET tutorial_complete = 1, gems = gems + ? WHERE id = 1",
            (TUTORIAL_COMPLETION_GEMS,),
        )
        row = conn.execute("SELECT gems FROM base WHERE id = 1").fetchone()
    return {"ok": True, "already_complete": False, "gems_granted": TUTORIAL_COMPLETION_GEMS, "gems": row["gems"]}

class GrantResourcesRequest(BaseModel):
    gold: int = 0
    gems: int = 0
    ingredients: int = 0
    aether: int = 0

@router.post("/dev/grant")
def grant_resources(req: GrantResourcesRequest):
    """
    Dev/testing helper — adds resources to the currently active profile.
    Intended for use on a dedicated test save, not your main progress.
    """
    import database
    with db() as conn:
        conn.execute(
            "UPDATE base SET gold = gold + ?, gems = gems + ?, ingredients = ingredients + ?, aether = aether + ? WHERE id = 1",
            (max(0, req.gold), max(0, req.gems), max(0, req.ingredients), max(0, req.aether))
        )
        row = conn.execute("SELECT gold, gems, ingredients, aether FROM base WHERE id = 1").fetchone()
    return {"ok": True, "profile": database.ACTIVE_PROFILE, "gold": row["gold"], "gems": row["gems"], "ingredients": row["ingredients"], "aether": row["aether"]}

@router.post("/dev/clear-inventory")
def dev_clear_inventory():
    """Dev/testing helper — wipes equipment, materials, potions, and scrolls.
    Refuses to run outside a profile named 'test*' since this is destructive."""
    import database
    if not database.ACTIVE_PROFILE or not database.ACTIVE_PROFILE.lower().startswith("test"):
        raise HTTPException(status_code=400, detail="Refused: this only runs on a 'test' profile.")
    with db() as conn:
        conn.execute("DELETE FROM equipment")
        conn.execute("DELETE FROM inventory")
        conn.execute("UPDATE base SET materials = '{}' WHERE id = 1")
    return {"ok": True}

class DevSetLevelRequest(BaseModel):
    hero_id: int
    level: int

@router.post("/dev/set-level")
def dev_set_level(req: DevSetLevelRequest):
    """Dev/testing helper — force a hero to a target level by backfilling
    just enough XP to satisfy the normal level formula, so it doesn't get
    silently recalculated back down on the next floor/synthesis."""
    import database
    if not database.ACTIVE_PROFILE or not database.ACTIVE_PROFILE.lower().startswith("test"):
        raise HTTPException(status_code=400, detail="Refused: this only runs on a 'test' profile.")

    from services.level_service import level_cap, get_hero_star
    with db() as conn:
        hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (req.hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found.")
        hero = dict(hero)

        cap = level_cap(get_hero_star(hero), hero.get("ascension_star", 0))
        target = max(1, min(req.level, cap))

        needed = (target - 1) - (hero.get("floors_survived", 0) // 3) - (hero.get("kills", 0) // 5)
        new_xp = max(hero.get("xp", 0), needed * 100) if needed > 0 else hero.get("xp", 0)

        conn.execute("UPDATE heroes SET level = ?, xp = ? WHERE id = ?", (target, new_xp, req.hero_id))
    return {"ok": True, "level": target, "capped": target < req.level}

@router.post("/rest")
def rest_heroes():
    """Rest all active heroes at base. Costs 50 ingredients (a hot meal for
    the whole roster), 5 min cooldown."""
    import time
    from services.morale_service import rest_at_base_recovery
    with db() as conn:
        # Get base info
        base = conn.execute("SELECT ingredients, last_rest_time FROM base WHERE id = 1").fetchone()

        now = time.time()
        cooldown = 300 # 5 minutes
        last_rest = base["last_rest_time"] or 0
        if now - last_rest < cooldown:
            rem = int(cooldown - (now - last_rest))
            raise HTTPException(status_code=400, detail=f"Resting is on cooldown for {rem} more seconds.")

        supply_cost = 50

        if base["ingredients"] < supply_cost:
            raise HTTPException(status_code=400, detail=f"Not enough ingredients to rest. Need {supply_cost}, have {base['ingredients']}.")

        conn.execute("UPDATE base SET ingredients = ingredients - ?, last_rest_time = ? WHERE id = 1", (supply_cost, now))

        # Button says "Rest All Heroes" — rest the whole living roster, not just deployed ones
        from services.base_service import get_base_upgrade_level
        chapel_level = get_base_upgrade_level(conn, "chapel")
        heroes = conn.execute("SELECT * FROM heroes WHERE is_alive = 1").fetchall()
        for hero in heroes:
            recovery = rest_at_base_recovery(dict(hero), chapel_level=chapel_level)
            # Psych-only — HP is handled by lobby-return full heal, not Rest.
            conn.execute("""
                UPDATE heroes SET morale = ?, stress = ?, trauma = ?, morale_state = ?, fatigue = 0
                WHERE id = ?
            """, (recovery["morale"], recovery["stress"], recovery["trauma"],
                  recovery["morale_state"], hero["id"]))
    return {"ok": True, "rested": len(heroes), "cost": supply_cost}

@router.get("/market/catalog")
def market_catalog():
    from services.market_service import get_shop_catalog
    return get_shop_catalog()

class MarketPurchaseRequest(BaseModel):
    item_id: str

@router.post("/market/purchase")
def market_purchase(req: MarketPurchaseRequest):
    from services.market_service import purchase_item
    with db() as conn:
        try:
            return purchase_item(conn, req.item_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

# ─── Team Banner ─────────────────────────────────────────────────────
# Template tiers unlock with the Wall's ART tier (the base LOOKS tier-3, so
# tier-3 cloth is available) — but any unlocked lower tier stays equippable,
# both for taste and for PvP mind games (flying tattered cloth at Wall 30).

# Only the new-generation 1254px set — the old small creature_* icons
# didn't hold up at banner scale (they serve elsewhere: Scout class icon,
# escort floors, gift icons).
BANNER_EMBLEMS = [
    "golden_lion", "crimson_skull", "divine_sun", "crescent_moon",
    "black_rose", "sapphire_crown", "arcane_dragon", "lightning_bolt",
    "bastion_shield", "iron_sword",
]

MAX_BANNER_PAINT_BYTES = 600_000  # dataURL cap — a 512px PNG layer is plenty


def _banner_unlocked_tier(conn) -> int:
    wall = conn.execute("SELECT level FROM facilities WHERE type = 'Wall' AND base_id = 1").fetchone()
    lvl = wall["level"] if wall else 1
    # Mirrors frontend facilityArtTier(): 1 / 5 / 15 / 30.
    if lvl >= 30: return 4
    if lvl >= 15: return 3
    if lvl >= 5: return 2
    return 1


def _ensure_banner_column(conn):
    try:
        conn.execute("ALTER TABLE base ADD COLUMN banner_json TEXT")
    except Exception:
        pass


@router.get("/banner")
def get_banner():
    with db() as conn:
        _ensure_banner_column(conn)
        row = conn.execute("SELECT banner_json FROM base WHERE id = 1").fetchone()
        banner = {}
        try:
            banner = json.loads(row["banner_json"]) if row and row["banner_json"] else {}
        except Exception:
            banner = {}
        return {
            "template_tier": banner.get("template_tier", 1),
            "emblem": banner.get("emblem"),
            "paint": banner.get("paint"),
            # Illuminated studio fields (additive — legacy banners just lack them)
            "cloth": banner.get("cloth"),
            "cut": banner.get("cut"),
            "frame_tier": banner.get("frame_tier"),
            "sigil": banner.get("sigil"),
            "unlocked_tier": _banner_unlocked_tier(conn),
            "emblems": BANNER_EMBLEMS,
        }


# Studio vocabulary — mirrors the Banner Studio mockup: tail cuts and cloth
# color are free self-expression, the FRAME tier is the earned flex (gated
# by the same Wall progression the old cloth tiers used), sigils are the
# built-in glyph row.
BANNER_CUTS = {"swallow", "point", "square"}
BANNER_SIGILS = {"star", "crown", "diamond", "spark", "moon"}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class BannerRequest(BaseModel):
    template_tier: int = 1
    emblem: str | None = None
    paint: str | None = None  # dataURL of the player's painted layer
    cloth: str | None = None       # hex cloth color, e.g. "#7a3df0"
    cut: str | None = None         # swallow | point | square
    frame_tier: int | None = None  # 1 bronze .. 4 radiant (renown-gated)
    sigil: str | None = None       # built-in glyph name


@router.post("/banner")
def save_banner(req: BannerRequest):
    with db() as conn:
        _ensure_banner_column(conn)
        unlocked = _banner_unlocked_tier(conn)
        tier = max(1, min(4, req.template_tier))
        if tier > unlocked:
            raise HTTPException(status_code=400, detail=f"Tier {tier} cloth unlocks when the Wall reaches its next look (currently tier {unlocked}).")
        if req.emblem is not None and req.emblem not in BANNER_EMBLEMS:
            raise HTTPException(status_code=400, detail="Unknown emblem.")
        if req.paint is not None:
            if not req.paint.startswith("data:image/"):
                raise HTTPException(status_code=400, detail="Paint layer must be an image data URL.")
            if len(req.paint) > MAX_BANNER_PAINT_BYTES:
                raise HTTPException(status_code=400, detail="Painted layer is too large — try a simpler design.")
        if req.cloth is not None and not _HEX_COLOR.match(req.cloth):
            raise HTTPException(status_code=400, detail="Cloth must be a #rrggbb color.")
        if req.cut is not None and req.cut not in BANNER_CUTS:
            raise HTTPException(status_code=400, detail="Unknown tail cut.")
        if req.sigil is not None and req.sigil not in BANNER_SIGILS:
            raise HTTPException(status_code=400, detail="Unknown sigil.")
        frame = None
        if req.frame_tier is not None:
            frame = max(1, min(4, req.frame_tier))
            if frame > unlocked:
                raise HTTPException(status_code=400, detail=f"That frame is earned, not bought — your renown is tier {unlocked} for now.")
        banner = {
            "template_tier": tier, "emblem": req.emblem, "paint": req.paint,
            "cloth": req.cloth, "cut": req.cut, "frame_tier": frame, "sigil": req.sigil,
        }
        conn.execute("UPDATE base SET banner_json = ? WHERE id = 1", (json.dumps(banner),))
    return {"ok": True, **banner}


# ─── Endgame facilities: Bestiary / Reliquary / Chronosphere / Core ──

@router.get("/bestiary")
def bestiary_status():
    from services.endgame_service import get_bestiary
    with db() as conn:
        return get_bestiary(conn)

@router.post("/bestiary/release/{beast_id}")
def bestiary_release(beast_id: int):
    from services.endgame_service import release_beast
    with db() as conn:
        try:
            return release_beast(conn, beast_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

@router.get("/reliquary")
def reliquary_status():
    from services.endgame_service import get_reliquary
    with db() as conn:
        return get_reliquary(conn)

class MountTrophyRequest(BaseModel):
    trophy_id: int
    mounted: bool

@router.post("/reliquary/mount")
def reliquary_mount(req: MountTrophyRequest):
    from services.endgame_service import set_trophy_mounted
    with db() as conn:
        try:
            return set_trophy_mounted(conn, req.trophy_id, req.mounted)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

@router.get("/chronosphere")
def chronosphere_status():
    from services.endgame_service import get_chronosphere
    with db() as conn:
        return get_chronosphere(conn)

@router.post("/chronosphere/activate")
def chronosphere_activate():
    from services.endgame_service import activate_chronosphere
    with db() as conn:
        try:
            return activate_chronosphere(conn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

@router.get("/transcendence")
def transcendence_status():
    from services.endgame_service import get_transcendence
    with db() as conn:
        return get_transcendence(conn)

@router.post("/transcendence/infuse")
def transcendence_infuse():
    from services.endgame_service import infuse_transcendence
    with db() as conn:
        try:
            return infuse_transcendence(conn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

# ─── Dining Hall cooking + Alchemist aether refining ────────────────

@router.get("/dining/catalog")
def dining_catalog():
    from services.cooking_service import get_cooking_catalog
    with db() as conn:
        return get_cooking_catalog(conn)

class CookRequest(BaseModel):
    recipe_id: str
    quantity: int = 1
    quality_mult: float = 1.0  # SEASON THE POT minigame result (server-clamped)

@router.post("/dining/cook")
def dining_cook(req: CookRequest):
    from services.cooking_service import cook_food
    with db() as conn:
        try:
            return cook_food(conn, req.recipe_id, req.quantity, req.quality_mult)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

class TavernDiceRequest(BaseModel):
    wager: int = 100
    mult: float = 1.0   # KNUCKLE & BONE result: 0 = lost the throw, up to x3
    hero_id: int | None = None  # drinking partner — takes +1 affinity win or lose

@router.post("/tavern/dice")
def tavern_dice(req: TavernDiceRequest):
    """The Tavern's dice table. The wager is the resource gate (gold up
    front); the minigame multiplier decides the payout — mult 0 loses the
    stake, x3 triples it. Capped at 5 throws a night so the table can't
    become a printing press."""
    with db() as conn:
        try:
            conn.execute("ALTER TABLE base ADD COLUMN dice_date TEXT")
            conn.execute("ALTER TABLE base ADD COLUMN dice_count INTEGER DEFAULT 0")
        except Exception:
            pass
        base = conn.execute("SELECT gold, dice_date, dice_count FROM base WHERE id = 1").fetchone()
        today = conn.execute("SELECT DATE('now')").fetchone()[0]
        count = (base["dice_count"] or 0) if base["dice_date"] == today else 0
        if count >= 5:
            raise HTTPException(status_code=400, detail="The table's closed for the night — five throws is the house limit.")
        wager = max(50, min(5000, int(req.wager or 0)))
        if base["gold"] < wager:
            raise HTTPException(status_code=400, detail=f"Not enough gold to cover the {wager}g stake.")
        mult = max(0.0, min(3.0, req.mult or 0.0))
        delta = int(wager * mult) - wager
        conn.execute("UPDATE base SET gold = gold + ?, dice_date = ?, dice_count = ? WHERE id = 1",
                     (delta, today, count + 1))
        if req.hero_id:
            conn.execute("UPDATE heroes SET affinity = MIN(100, COALESCE(affinity,0) + 1) WHERE id = ? AND is_alive = 1", (req.hero_id,))
        return {"ok": True, "delta": delta, "throws_left": 4 - count,
                "message": ("The table erupts — the pot slides your way." if delta > 0
                            else "Bones scatter, coin follows." if delta < 0
                            else "Even bones. The drinks are the only cost.")}


class HuntRequest(BaseModel):
    mult: float = 1.0   # THE HUNT minigame result

@router.post("/bestiary/hunt")
def bestiary_hunt(req: HuntRequest):
    """MOUNT A HUNT — the Bestiary's daily tracking expedition. The minigame
    multiplier scales the caught beast's power; a strong showing (x2.4+) bags
    an ALPHA; mult 0 = the trail went cold and the quarry escaped."""
    import random as _r
    with db() as conn:
        try:
            conn.execute("ALTER TABLE base ADD COLUMN hunt_date TEXT")
        except Exception:
            pass
        row = conn.execute("SELECT hunt_date, highest_floor FROM base WHERE id = 1").fetchone()
        today = conn.execute("SELECT DATE('now')").fetchone()[0]
        if row["hunt_date"] == today:
            raise HTTPException(status_code=400, detail="The trails are cold — one hunt a day.")
        from services.endgame_service import _facility_level, _ensure_schema, bestiary_capacity, BEAST_EPITHETS, UNCAPTURABLE
        level = _facility_level(conn, "Bestiary")
        if level <= 0:
            raise HTTPException(status_code=400, detail="Build the Bestiary first — a hunt needs a pen to bring things back to.")
        _ensure_schema(conn)
        held = conn.execute("SELECT COUNT(*) AS c FROM bestiary_beasts").fetchone()["c"]
        if held >= bestiary_capacity(level):
            raise HTTPException(status_code=400, detail="The pens are full — release something first.")
        conn.execute("UPDATE base SET hunt_date = ? WHERE id = 1", (today,))
        mult = max(0.0, min(3.0, req.mult or 0.0))
        if mult <= 0.05:
            return {"ok": True, "escaped": True,
                    "message": "The trail doubles back on itself and dies at a riverbank. The quarry is gone."}
        floor = max(1, row["highest_floor"] or 1)
        from services.combat_service import _enemy_pool_for_floor
        pool = [e[0] for e in _enemy_pool_for_floor(floor) if e[0] not in UNCAPTURABLE]
        if not pool:
            raise HTTPException(status_code=400, detail="Nothing worth hunting at this depth.")
        species = _r.choice(pool)
        is_alpha = mult >= 2.4
        power = int((10 + floor * 2) * (0.6 + mult * 0.5) * (1.5 if is_alpha else 1.0))
        name = (f"Alpha {species}" if is_alpha else f"{_r.choice(BEAST_EPITHETS)} {species}")
        cur = conn.execute("INSERT INTO bestiary_beasts (name, species, floor_caught, power) VALUES (?,?,?,?)",
                           (name, species, floor, power))
        return {"ok": True, "beast": {"id": cur.lastrowid, "name": name, "power": power, "alpha": is_alpha},
                "message": f"The snare sings — {name} is dragged back to the pens (power {power})."}


class RiteRequest(BaseModel):
    mult: float = 1.0   # TRACE THE SIGIL minigame result

@router.post("/shrine/rite")
def shrine_rite(req: RiteRequest):
    """CONDUCT A RITE — the Shrine's daily ceremony. A clean tracing floods
    the roster with loyalty and eases stress (scaled by the multiplier);
    a soured rite (mult 0) unsettles everyone instead."""
    with db() as conn:
        try:
            conn.execute("ALTER TABLE base ADD COLUMN rite_date TEXT")
        except Exception:
            pass
        shrine = conn.execute("SELECT 1 FROM facilities WHERE type = 'Shrine' AND base_id = 1").fetchone()
        if not shrine:
            raise HTTPException(status_code=400, detail="No Shrine stands — raise one before conducting rites.")
        row = conn.execute("SELECT rite_date FROM base WHERE id = 1").fetchone()
        today = conn.execute("SELECT DATE('now')").fetchone()[0]
        if row["rite_date"] == today:
            raise HTTPException(status_code=400, detail="The candles are already spent — one rite a day.")
        conn.execute("UPDATE base SET rite_date = ? WHERE id = 1", (today,))
        mult = max(0.0, min(3.0, req.mult or 0.0))
        if mult <= 0.05:
            conn.execute("UPDATE heroes SET stress = MIN(100, COALESCE(stress,0) + 4) WHERE is_alive = 1")
            return {"ok": True, "soured": True,
                    "message": "The tracing falters mid-line — the flame gutters, and the roster feels it."}
        loyalty = max(1, int(3 * mult))
        calm = max(1, int(3 * mult))
        conn.execute("UPDATE heroes SET affinity = MIN(100, COALESCE(affinity,0) + ?), stress = MAX(0, COALESCE(stress,0) - ?) WHERE is_alive = 1",
                     (loyalty, calm))
        return {"ok": True, "loyalty": loyalty, "calm": calm,
                "message": f"The sigil holds its light — the whole company stands a little taller (+{loyalty} loyalty, −{calm} stress)."}


class RefineAetherRequest(BaseModel):
    batches: int = 1
    quality_mult: float = 1.0  # THE STILL minigame result (server-clamped)

@router.post("/alchemist/refine-aether")
def alchemist_refine_aether(req: RefineAetherRequest):
    from services.cooking_service import refine_aether
    with db() as conn:
        try:
            return refine_aether(conn, req.batches, req.quality_mult)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

class CraftBandagesRequest(BaseModel):
    crafter_id: int
    quantity: int = 1

@router.post("/infirmary/craft-bandages")
def craft_bandages_endpoint(req: CraftBandagesRequest):
    from services.infirmary_service import craft_bandages
    with db() as conn:
        try:
            return craft_bandages(conn, req.crafter_id, req.quantity)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

# ─── Base Floors ────────────────────────────────────────────────

class AssignFloorRequest(BaseModel):
    hero_id: int
    floor: int # 0 means unassigned

@router.get("/floors")
def get_base_floors():
    """Get the calculated LP and stats for all base floors"""
    with db() as conn:
        base = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()
        highest_tower_floor = base["highest_floor"]
        unlocked_floors = max(1, highest_tower_floor // 10)
        
        # Calculate LP pool for each floor
        # e.g., floor 1 = 100 LP, floor 5 = 500 LP
        floors = {}
        for f in range(1, unlocked_floors + 1):
            floors[f] = {
                "floor_number": f,
                "total_lp": f * 100,
                "heroes": [],
                "lp_per_hero": 0,
                "stat_bonus_pct": 0
            }
            
        # Get hero assignments (all alive heroes)
        heroes = conn.execute("SELECT id, name, base_floor, hero_class, portrait_path, is_alive, level, birth_star, current_star FROM heroes WHERE is_alive = 1").fetchall()
        
        # Everyone lives SOMEWHERE — unassigned (0) or invalid-floor heroes
        # are housed on Floor 1 automatically. The strategy is how you
        # spread them once more floors unlock, not whether to assign at all.
        base_heroes = []
        for h in heroes:
            f = h["base_floor"]
            if f not in floors:
                conn.execute("UPDATE heroes SET base_floor = 1 WHERE id = ?", (h["id"],))
                f = 1
            hero_dict = dict(h)
            hero_dict["base_floor"] = f
            floors[f]["heroes"].append(hero_dict)
            
        # Calculate math — must match get_floor_lp() in base_service.py
        # exactly, since that's what combat_service.py actually applies as
        # the real stat bonus. This used to be a separate flat-division
        # formula that didn't match (displayed bonus != applied bonus).
        from services.base_service import get_floor_lp
        for f in floors.values():
            lp_data = get_floor_lp(conn, f["floor_number"])
            f["lp_per_hero"] = lp_data["lp_per_hero"]
            f["stat_bonus_pct"] = lp_data["stat_bonus_pct"]
            # Diminishing-returns preview: same sqrt-crowding formula, shown
            # for a range of headcounts so the frontend can plot the curve
            # and mark where this floor currently sits on it.
            import math
            f["bonus_curve"] = [
                {"headcount": n, "stat_bonus_pct": round((f["total_lp"] * (1.0 / math.sqrt(n))) // 10)}
                for n in range(1, 6)
            ]

    return {"floors": list(floors.values()), "unlocked": unlocked_floors, "base_heroes": base_heroes}

@router.post("/floors/assign")
def assign_base_floor(req: AssignFloorRequest):
    with db() as conn:
        base = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()
        highest_tower_floor = base["highest_floor"]
        unlocked_floors = max(1, highest_tower_floor // 10)
        
        # Floor 0 (unassigned) is no longer a valid destination — every hero
        # lives on a floor; "removing" someone just sends them back to Floor 1.
        floor = req.floor if req.floor >= 1 else 1
        if floor > unlocked_floors:
            raise HTTPException(status_code=400, detail=f"Floor {floor} is invalid.")

        conn.execute("UPDATE heroes SET base_floor = ? WHERE id = ?", (floor, req.hero_id))
    return {"ok": True}

# ─── Skydock: magic battleships ─────────────────────────────────────

class RenameShipRequest(BaseModel):
    name: str

@router.get("/ship")
def get_ship():
    from services.ship_service import get_ship_status, get_base_defense
    status = get_ship_status()
    with db() as conn:
        status["defense"] = get_base_defense(conn)
    return status

@router.post("/ship/build")
def build_ship():
    from services.ship_service import build_next_tier
    try:
        return build_next_tier()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/ship/rename")
def rename_ship_endpoint(req: RenameShipRequest):
    from services.ship_service import rename_ship
    try:
        return rename_ship(req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class RefitAllocateRequest(BaseModel):
    stat: str    # 'speed' | 'fire' | 'armor'
    delta: int   # +1 / -1

@router.post("/ship/refit")
def refit_ship(req: RefitAllocateRequest):
    from services.ship_service import allocate_refit
    try:
        return allocate_refit(req.stat, req.delta)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/ship/refit/buy_point")
def refit_buy_point():
    from services.ship_service import buy_refit_point
    try:
        return buy_refit_point()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ─── Guild boons (synced from the world server) ──────────────────────
# Support-class revamp: the resolved star-scaled boons every wired system
# reads (Chef feast, Medic shield, Merchant/Farmer income, Blacksmith
# discount, Alchemist brew, Scout recon) — for the frontend to display.
@router.get("/support")
def get_support():
    from services.support_service import get_support_effects
    return get_support_effects()


# The arena server can't touch this save, so the client relays the boon
# multipliers from /guild/mine here. Clamped hard — a tampered client can
# at most give itself the max legitimate boon.

class GuildBoonsRequest(BaseModel):
    hero_exp_pct: int = 0
    refit_discount_pct: int = 0

@router.post("/guild_boons")
def set_guild_boons(req: GuildBoonsRequest):
    with db() as conn:
        for col in ("guild_hero_exp_pct", "guild_refit_discount_pct"):
            try:
                conn.execute(f"ALTER TABLE base ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass
        conn.execute(
            "UPDATE base SET guild_hero_exp_pct = ?, guild_refit_discount_pct = ? WHERE id = 1",
            (max(0, min(15, req.hero_exp_pct)), max(0, min(20, req.refit_discount_pct))))
    return {"ok": True}

# ─── Local fee payments for world-server features ────────────────────
# Same client-side economy split as raid scouting: the world server hosts
# the feature, the local save pays the price first (guild founding, etc.).

class PayFeeRequest(BaseModel):
    amount: int
    reason: str = ""

@router.post("/pay_fee")
def pay_fee(req: PayFeeRequest):
    if req.amount <= 0 or req.amount > 1_000_000:
        raise HTTPException(status_code=400, detail="Invalid fee.")
    with db() as conn:
        base = conn.execute("SELECT gold FROM base WHERE id = 1").fetchone()
        if base["gold"] < req.amount:
            raise HTTPException(status_code=400, detail=f"Not enough gold ({req.amount:,}g needed).")
        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (req.amount,))
    return {"ok": True, "paid": req.amount, "reason": req.reason}

# ─── The Tavern: patrons & rounds ───────────────────────────────────

class RoundRequest(BaseModel):
    hero_id: int | None = None

@router.get("/tavern")
def get_tavern():
    from services.sanctum_service import process_tavern, tavern_status
    with db() as conn:
        process_tavern(conn)
        return tavern_status(conn)

@router.post("/tavern/round")
def tavern_round(req: RoundRequest):
    from services.sanctum_service import buy_round
    with db() as conn:
        return buy_round(conn, req.hero_id)

# ─── The Sky Charts: expeditions ────────────────────────────────────

class DispatchRequest(BaseModel):
    lane: str
    hero_ids: list[int]
    quality_mult: float = 1.0  # THE HELM minigame result (server-clamped)

class LaneRequest(BaseModel):
    lane: str

@router.get("/expeditions")
def get_expeditions():
    from services.expedition_service import expeditions_status
    return expeditions_status()

@router.post("/expeditions/dispatch")
def dispatch_expedition(req: DispatchRequest):
    from services.expedition_service import dispatch
    return dispatch(req.lane, req.hero_ids, getattr(req, "quality_mult", 1.0) or 1.0)

@router.post("/expeditions/collect")
def collect_expedition(req: LaneRequest):
    from services.expedition_service import collect
    return collect(req.lane)

@router.post("/expeditions/recall")
def recall_expedition(req: LaneRequest):
    from services.expedition_service import recall
    return recall(req.lane)

# ─── Daily Dungeon endpoints ────────────────────────────────────────

DAILY_GATE_KEYS = 3  # keys per gate per day, reset at UTC midnight
# The three daily gates: gold, materials, and AETHER (raid fuel — the
# Skydock trickles it and the Lab refines it for gold, so the gate is the
# only free burst). "ingredients" stays accepted as a legacy type (the Farm
# covers that need passively) but no longer has a gate in the UI.
DAILY_GATE_TYPES = ["gold", "materials", "aether"]


def _ensure_daily_dungeon_column(conn):
    try:
        conn.execute("ALTER TABLE base ADD COLUMN daily_dungeon_json TEXT")
    except Exception:
        pass


def _daily_dungeon_state(conn) -> dict:
    """{date: 'YYYY-MM-DD', used: {gate: n}} — auto-resets when the date rolls."""
    from datetime import datetime, timezone
    _ensure_daily_dungeon_column(conn)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute("SELECT daily_dungeon_json FROM base WHERE id = 1").fetchone()
    try:
        state = json.loads(row["daily_dungeon_json"]) if row and row["daily_dungeon_json"] else {}
    except Exception:
        state = {}
    if state.get("date") != today:
        state = {"date": today, "used": {}}
    return state


def _save_daily_dungeon_state(conn, state: dict):
    conn.execute("UPDATE base SET daily_dungeon_json = ? WHERE id = 1", (json.dumps(state),))


# Gate tiers (Daily Gates spec): tier I is open from the start, tier II
# past floor 30, tier III past floor 60. A key opens one run at any
# unlocked tier; deeper tiers pay ×2.2 / ×4.
GATE_TIER_MULT = {1: 1.0, 2: 2.2, 3: 4.0}
GATE_TIER_FLOOR = {1: 0, 2: 30, 3: 60}


def _gate_tiers_unlocked(highest: int) -> list:
    return [t for t, floor in GATE_TIER_FLOOR.items() if highest >= floor]


@router.get("/daily_dungeon/status")
def daily_dungeon_status():
    """Keys left per gate + when they return (UTC midnight)."""
    from datetime import datetime, timezone, timedelta
    with db() as conn:
        state = _daily_dungeon_state(conn)
        run = conn.execute("SELECT MAX(highest_floor) as max_floor FROM runs").fetchone()
        highest = run["max_floor"] if run and run["max_floor"] else 0
    now = datetime.now(timezone.utc)
    reset_at = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "keys": {g: DAILY_GATE_KEYS - state["used"].get(g, 0) for g in DAILY_GATE_TYPES},
        "max_keys": DAILY_GATE_KEYS,
        "resets_in_seconds": int((reset_at - now).total_seconds()),
        "scale_floor": highest,
        "tiers_unlocked": _gate_tiers_unlocked(highest),
        "tier_floors": GATE_TIER_FLOOR,
    }


@router.post("/daily_dungeon/{dungeon_type}")
def run_daily_dungeon(dungeon_type: str, tier: int = 1):
    """
    Run a daily dungeon for Gold or Materials.
    Rewards scale with the highest floor reached in the tower, then by the
    chosen gate tier (I/II/III — deeper tiers unlock past floors 30/60).
    """
    # "ingredients" replaced the old supplies dungeon; the legacy name is
    # still accepted so a stale client doesn't 400.
    if dungeon_type == "supplies":
        dungeon_type = "ingredients"
    if dungeon_type not in ["gold", "materials", "ingredients", "aether"]:
        raise HTTPException(status_code=400, detail="Invalid dungeon type. Must be 'gold', 'materials', 'ingredients', or 'aether'.")
    if tier not in GATE_TIER_MULT:
        raise HTTPException(status_code=400, detail="Gates open at tiers I, II, or III.")

    with db() as conn:
        # Check team
        team = conn.execute("SELECT * FROM heroes WHERE is_on_team = 1 AND is_alive = 1").fetchall()
        if not team:
            raise HTTPException(status_code=400, detail="No team assigned. Set a team first.")

        # Get highest floor (also gates the tier)
        run = conn.execute("SELECT MAX(highest_floor) as max_floor FROM runs").fetchone()
        highest = run["max_floor"] if run and run["max_floor"] else 0
        if tier not in _gate_tiers_unlocked(highest):
            raise HTTPException(status_code=400, detail=f"Tier {tier} waits past floor {GATE_TIER_FLOOR[tier]} — climb higher.")

        # Daily gate keys — 3 per gate, back at dawn (UTC midnight)
        state = _daily_dungeon_state(conn)
        used = state["used"].get(dungeon_type, 0)
        if used >= DAILY_GATE_KEYS:
            raise HTTPException(status_code=400, detail="That gate has sealed for today — keys return at dawn.")
        state["used"][dungeon_type] = used + 1
        _save_daily_dungeon_state(conn, state)

        from services.quests_service import bump as bump_rite
        bump_rite("gate_run")

        scale = 1 + (highest // 10)
        mult = GATE_TIER_MULT[tier]

        # Base info
        base_row = conn.execute("SELECT gold, materials, ingredients FROM base WHERE id = 1").fetchone()

        if dungeon_type == "gold":
            gold_reward = int((1000 + (scale * 800)) * mult)
            conn.execute("UPDATE base SET gold = gold + ? WHERE id = 1", (gold_reward,))
            return {"ok": True, "type": "gold", "tier": tier, "reward": gold_reward, "message": f"Dungeon cleared! Gained {gold_reward} Gold."}

        elif dungeon_type == "materials":
            # THE evolution-materials dungeon (Liam's design): each gate tier
            # drops the real materials the matching evolution bands eat, so
            # once a tier is open, those star-ups stop being a bottleneck.
            #   Tier I   (open)      → 1★→2★→3★ mats, generous
            #   Tier II  (floor 30+) → 3★→4★→5★ mats
            #   Tier III (floor 60+) → 5★→6★ mats + the 6★→7★ BULK legendaries
            # Eternal Shards are deliberately absent — transcendence's key
            # material comes from floor-80+ bosses only, never a daily.
            # (The old list here was snake_case junk no recipe recognized.)
            GATE_MATERIAL_POOLS = {
                1: ["Iron Ore", "Iron Ore", "Dark Crystal", "Monster Bone", "Goblin Ear", "Mystic Dust", "Wolf Pelt"],
                2: ["Refined Iron", "Hardened Bone", "Mystic Dust", "Goblin Ear", "Wyvern Scale", "Enchanted Steel", "Runed Crystal", "Demon Ichor"],
                3: ["Wyvern Scale", "Enchanted Steel", "Runed Crystal", "Demon Ichor", "Mithril", "Adamantine", "Dragon Scale", "Phoenix Feather"],
            }
            import random
            mats = GATE_MATERIAL_POOLS[tier]
            drops = {}
            for _ in range(int(random.randint(3, 5 + (scale // 2)) * mult)):
                mat = random.choice(mats)
                drops[mat] = drops.get(mat, 0) + random.randint(2, 4 + (scale // 3))

            current_mats = json.loads(base_row["materials"]) if base_row["materials"] else {}
            for mat, qty in drops.items():
                current_mats[mat] = current_mats.get(mat, 0) + qty

            conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(current_mats),))
            return {"ok": True, "type": "materials", "tier": tier, "reward": drops, "message": "Dungeon cleared! Gathered materials."}

        elif dungeon_type == "ingredients":
            ingredients_earned = int((20 + max(0, highest * 5)) * mult)
            conn.execute("UPDATE base SET ingredients = ingredients + ? WHERE id = 1", (ingredients_earned,))
            return {"ok": True, "type": "ingredients", "tier": tier, "reward": ingredients_earned, "message": f"Dungeon cleared! Foraged {ingredients_earned} Ingredients 🌿."}

        elif dungeon_type == "aether":
            # Raid fuel. Deliberately the smallest number of the three —
            # the Skydock trickles it and the Lab refines it for gold, so
            # the gate should feel like a prize, not a faucet.
            aether_earned = int((15 + (scale * 10)) * mult)
            conn.execute("UPDATE base SET aether = aether + ? WHERE id = 1", (aether_earned,))
            return {"ok": True, "type": "aether", "tier": tier, "reward": aether_earned, "message": f"Dungeon cleared! Condensed {aether_earned} Aether ✨."}
# ─── Inventory endpoints ────────────────────────────────────────────

@router.get("/inventory")
def get_inventory():
    """Return all items in the base inventory."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM inventory WHERE quantity > 0 ORDER BY item_type, item_name").fetchall()
    return [dict(r) for r in rows]


def _eligible_consumable_names(conn) -> set:
    """Bandage plus every healing- or mana-capable Potion/Scroll — the same
    "drinkable in a fight" set combat already restricts auto-use to,
    so equip choices can't point at e.g. a non-healing Scroll of Insight."""
    from services.alchemist_service import POTION_CATALOG
    from services.research_service import SCROLL_CATALOG
    from services.cooking_service import FOOD_CATALOG
    names = {"Bandage"}
    names.update(p["name"] for p in POTION_CATALOG if "heal_pct" in p["effect"] or "mana_pct" in p["effect"])
    names.update(s["name"] for s in SCROLL_CATALOG if "heal_pct" in s["effect"])
    names.update(f["name"] for f in FOOD_CATALOG if "heal_pct" in f["effect"])
    return names

class EquipConsumableRequest(BaseModel):
    hero_id: int
    item_name: str | None = None  # None unequips

@router.post("/heroes/equip-consumable")
def equip_consumable(req: EquipConsumableRequest):
    """A hero's consumable slot — which Bandage/Potion/Scroll they carry into
    the tower and reach for when hurt. Deliberately scoped per-hero (not a
    free-for-all shared backpack) so investing in a Medic's bandage habit or
    a Mage's healing draughts is a real choice, not just "whatever's in the
    warehouse." The item itself still comes out of the same finite shared
    stock everyone draws from — equipping just decides who's allowed to
    reach for it and when, it doesn't reserve or duplicate stock."""
    with db() as conn:
        hero = conn.execute("SELECT id FROM heroes WHERE id = ? AND is_alive = 1", (req.hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or not alive.")
        if req.item_name is not None and req.item_name not in _eligible_consumable_names(conn):
            raise HTTPException(status_code=400, detail=f"{req.item_name} isn't a healing consumable that can be equipped.")
        conn.execute("UPDATE heroes SET equipped_consumable = ? WHERE id = ?", (req.item_name, req.hero_id))
    return {"ok": True}


@router.post("/inventory/add")
def add_inventory_item(item_name: str, item_type: str, quantity: int = 1, description: str = ""):
    """Add an item to inventory (or increment quantity if it exists)."""
    with db() as conn:
        existing = conn.execute(
            "SELECT * FROM inventory WHERE item_name = ? AND item_type = ?",
            (item_name, item_type)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE inventory SET quantity = quantity + ? WHERE id = ?",
                (quantity, existing["id"])
            )
            return {"ok": True, "item": item_name, "new_quantity": existing["quantity"] + quantity}
        else:
            conn.execute(
                "INSERT INTO inventory (item_name, item_type, quantity, description) VALUES (?,?,?,?)",
                (item_name, item_type, quantity, description)
            )
            return {"ok": True, "item": item_name, "new_quantity": quantity}


class UseItemRequest(BaseModel):
    item_name: str
    hero_id: int
    target_skill_id: str = None

@router.post("/inventory/use")
def use_item(req: UseItemRequest):
    """Consume a potion, scroll, or cooked food on a target hero."""
    from services.alchemist_service import POTION_CATALOG
    from services.research_service import SCROLL_CATALOG
    from services.cooking_service import FOOD_CATALOG
    catalog = {p["name"]: p["effect"] for p in POTION_CATALOG}
    catalog.update({s["name"]: s["effect"] for s in SCROLL_CATALOG})
    catalog.update({f["name"]: f["effect"] for f in FOOD_CATALOG})

    effect = catalog.get(req.item_name)
    if not effect:
        raise HTTPException(status_code=400, detail="Unknown or unusable item.")

    with db() as conn:
        item = conn.execute(
            "SELECT * FROM inventory WHERE item_name = ? AND quantity > 0", (req.item_name,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=400, detail="You don't have any of that item.")

        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (req.hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=400, detail="Hero not available.")
        hero = dict(hero)

        applied = {}
        if "heal_pct" in effect:
            heal = int(hero["max_health"] * effect["heal_pct"])
            new_hp = min(hero["max_health"], hero["health"] + heal)
            conn.execute("UPDATE heroes SET health = ? WHERE id = ?", (new_hp, hero["id"]))
            applied["health"] = new_hp

        if "stress_delta" in effect:
            new_stress = max(0, hero["stress"] + effect["stress_delta"])
            conn.execute("UPDATE heroes SET stress = ? WHERE id = ?", (new_stress, hero["id"]))
            applied["stress"] = new_stress

        if "morale_delta" in effect:
            from services.morale_service import get_morale_state
            new_morale = max(0, min(100, hero["morale"] + effect["morale_delta"]))
            conn.execute("UPDATE heroes SET morale = ?, morale_state = ? WHERE id = ?",
                         (new_morale, get_morale_state(new_morale), hero["id"]))
            applied["morale"] = new_morale

        if "trauma_delta" in effect:
            new_trauma = max(0, hero["trauma"] + effect["trauma_delta"])
            conn.execute("UPDATE heroes SET trauma = ? WHERE id = ?", (new_trauma, hero["id"]))
            applied["trauma"] = new_trauma

        if "skill_xp" in effect:
            skills = json.loads(hero.get("skills") or "[]")
            target = None
            if req.target_skill_id:
                target = next((s for s in skills if s["id"] == req.target_skill_id), None)
            elif skills:
                target = skills[0]
            if target:
                target["xp"] = target.get("xp", 0) + effect["skill_xp"]
                max_xp = target.get("max_xp", 100)
                if target["xp"] >= max_xp:
                    target["xp"] -= max_xp
                    target["level"] = target.get("level", 1) + 1
                    target["max_xp"] = int(max_xp * 1.5)
                conn.execute("UPDATE heroes SET skills = ? WHERE id = ?", (json.dumps(skills), hero["id"]))
                applied["skill"] = target["name"]

        new_qty = item["quantity"] - 1
        if new_qty <= 0:
            conn.execute("DELETE FROM inventory WHERE id = ?", (item["id"],))
        else:
            conn.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, item["id"]))

    return {"ok": True, "item": req.item_name, "applied": applied, "remaining": max(0, new_qty)}


# ─── Base upgrades endpoints ────────────────────────────────────────

# Mirror of Fate left this tree — it's a real facility now (floor 25,
# FACILITY_TYPES); reveal detail scales with the FACILITY's level.
DEFAULT_UPGRADES = [
    {"id": "infirmary", "name": "Infirmary", "description": "Improve rest recovery rates.", "max_level": 5},
    {"id": "forge", "name": "Forge", "description": "Improves the quality of crafted equipment.", "max_level": 5},
]

UPGRADE_GOLD_COST = {
    1: 500,
    2: 1200,
    3: 2500,
    4: 5000,
    5: 10000,
}

@router.get("/upgrades")
def get_upgrades():
    """Return all base upgrades and their current levels."""
    with db() as conn:
        base = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()
        highest_floor = base["highest_floor"] if base else 0
        # Ensure defaults exist, and keep name/description/max_level in sync
        # for rows created before a wording change (e.g. Forge's "unlock
        # crafting" claim, which never matched reality since crafting
        # already worked without it — see forge_craft's real effect now).
        for u in DEFAULT_UPGRADES:
            conn.execute(
                "INSERT OR IGNORE INTO base_upgrades (id, name, description, max_level) VALUES (?,?,?,?)",
                (u["id"], u["name"], u["description"], u["max_level"])
            )
            conn.execute(
                "UPDATE base_upgrades SET name = ?, description = ?, max_level = ? WHERE id = ?",
                (u["name"], u["description"], u["max_level"], u["id"])
            )
        # Retired upgrades (e.g. Watchtower — removed entirely, never had a
        # working effect) shouldn't linger in old saves just because they
        # were inserted before the removal.
        valid_ids = [u["id"] for u in DEFAULT_UPGRADES]
        conn.execute(f"DELETE FROM base_upgrades WHERE id NOT IN ({','.join('?' * len(valid_ids))})", valid_ids)
        rows = conn.execute("SELECT * FROM base_upgrades ORDER BY name").fetchall()
        
    results = []
    for r in rows:
        upgrade = dict(r)
        current_level = upgrade.get("level", 0)
        max_level = upgrade.get("max_level", 5)
        next_level = current_level + 1
        upgrade["is_maxed"] = current_level >= max_level
        upgrade["next_cost"] = UPGRADE_GOLD_COST.get(next_level, 10000)
        results.append(upgrade)
    return results


class UpgradeRequest(BaseModel):
    upgrade_id: str

@router.post("/upgrades/purchase")
def buy_upgrade(data: UpgradeRequest):
    """Purchase the next level of a base upgrade."""
    with db() as conn:
        upgrade = conn.execute("SELECT * FROM base_upgrades WHERE id = ?", (data.upgrade_id,)).fetchone()
        if not upgrade:
            raise HTTPException(status_code=404, detail="Upgrade not found.")
        upgrade = dict(upgrade)

        current_level = upgrade.get("level", 0)
        max_level = upgrade.get("max_level", 5)
        if current_level >= max_level:
            raise HTTPException(status_code=400, detail="Upgrade already at max level.")

        next_level = current_level + 1
        cost = UPGRADE_GOLD_COST.get(next_level, 10000)

        base = conn.execute("SELECT gold, highest_floor FROM base WHERE id = 1").fetchone()

        if base["gold"] < cost:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough gold. Need {cost}, have {base['gold']}."
            )

        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (cost,))
        conn.execute(
            "UPDATE base_upgrades SET level = ?, unlocked = 1 WHERE id = ?",
            (next_level, data.upgrade_id)
        )

    return {
        "ok": True,
        "upgrade_id": data.upgrade_id,
        "new_level": next_level,
        "gold_spent": cost,
        "message": f"{upgrade['name']} upgraded to level {next_level}!"
    }


class TalentRevealRequest(BaseModel):
    hero_id: int
    # READ THE GLASS minigame result: a clean reading DISCOUNTS the Mirror's
    # price (final cost = base / mult, so x3 pays a third); a sloppy one
    # overpays; 0 = the glass CLOUDS — a fifth of the price is spent as a
    # wasted offering and nothing is revealed. Server-clamped.
    quality_mult: float = 1.0

@router.post("/talent-observatory/reveal")
def reveal_hero_talent(data: TalentRevealRequest):
    """Pay gold at the Mirror of Fate FACILITY to immediately reveal a
    hero's Talent — detail scales with the facility's level (see
    level_service.reveal_mirror_of_fate)."""
    from services.level_service import get_mirror_of_fate_cost, reveal_mirror_of_fate

    with db() as conn:
        mirror = conn.execute("SELECT level FROM facilities WHERE type = 'Mirror of Fate' AND base_id = 1").fetchone()
        if not mirror:
            raise HTTPException(status_code=400, detail="Build the Mirror of Fate facility first.")

        hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (data.hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found.")
        hero = dict(hero)
        if hero.get("talent_reveal"):
            raise HTTPException(status_code=400, detail="This hero's Talent has already been revealed.")

        cost = get_mirror_of_fate_cost(hero)
        base = conn.execute("SELECT gold FROM base WHERE id = 1").fetchone()

        # READ THE GLASS — the reading sets the price actually paid.
        raw_mult = data.quality_mult or 1.0
        if raw_mult <= 0.05:
            offering = max(1, cost // 5)
            if base["gold"] < offering:
                raise HTTPException(status_code=400, detail=f"Not enough gold even for the offering ({offering}).")
            conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (offering,))
            return {"ok": True, "clouded": True, "gold_spent": offering,
                    "message": "The glass clouds over — whatever it saw, it keeps. The offering is spent."}
        final_cost = max(1, int(cost / max(0.3, min(3.0, raw_mult))))
        if base["gold"] < final_cost:
            raise HTTPException(status_code=400, detail=f"Not enough gold. Need {final_cost}, have {base['gold']}.")

        # Facility level -> reveal-detail tier: Lv1-4 vague, Lv5-9 the
        # aptitude's category, Lv10+ the exact aptitude.
        mirror_level = min(3, 1 + mirror["level"] // 5)
        revealed = reveal_mirror_of_fate(hero, mirror_level)

        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (final_cost,))
        conn.execute("UPDATE heroes SET talent_reveal = ? WHERE id = ?", (revealed, data.hero_id))

    return {"ok": True, "hero_id": data.hero_id, "gold_spent": final_cost, "base_cost": cost, "talent_reveal": revealed}


# ─── Equipment endpoints ────────────────────────────────────────────

@router.get("/equipment")
def list_equipment():
    """List all equipment, grouped by equipped/unequipped."""
    from services.equipment_service import get_unequipped
    with db() as conn:
        all_equip = conn.execute("SELECT * FROM equipment").fetchall()
    equipped = [dict(e) for e in all_equip if e["is_equipped_to"]]
    unequipped = get_unequipped()
    return {"equipped": equipped, "unequipped": unequipped}


class EquipRequest(BaseModel):
    equipment_id: int
    hero_id: int

@router.post("/equipment/equip")
def equip_item_endpoint(data: EquipRequest):
    from services.equipment_service import equip_item
    result = equip_item(data.equipment_id, data.hero_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class UnequipRequest(BaseModel):
    equipment_id: int

@router.post("/equipment/unequip")
def unequip_item_endpoint(data: UnequipRequest):
    from services.equipment_service import unequip_item
    return unequip_item(data.equipment_id)


@router.get("/equipment/hero/{hero_id}")
def hero_equipment(hero_id: int):
    from services.equipment_service import get_hero_equipment
    return get_hero_equipment(hero_id)
class CraftRequest(BaseModel):
    slot: str

@router.post("/forge/craft")
def forge_craft(req: CraftRequest):
    from services.equipment_service import craft_equipment_for_slot, save_equipment, get_vault_capacity, get_equipment_count
    with db() as conn:
        if get_equipment_count(conn) >= get_vault_capacity(conn):
            raise HTTPException(status_code=400, detail="The Vault is full. Upgrade it or clear out some equipment first.")

        # Check base gold and materials
        base = conn.execute("SELECT gold, materials FROM base WHERE id = 1").fetchone()

        mats = json.loads(base["materials"]) if base["materials"] else {}
        recipe = {}
        if req.slot == "weapon":
            recipe = {"Iron Ore": 3, "Monster Bone": 1}
        elif req.slot == "armor":
            # Slime Core was dropped from the game (its icon never generated
            # well) — Dark Crystal took its slot in the armor recipe.
            recipe = {"Dark Crystal": 2, "Iron Ore": 2}
        else:
            recipe = {"Mystic Dust": 3, "Goblin Ear": 1}
            
        from services.materials_service import get_material_total, consume_material
        for m, q in recipe.items():
            if get_material_total(mats, m) < q:
                raise HTTPException(status_code=400, detail=f"Not enough {m}. Need {q} for {req.slot}.")

        if base["gold"] < 100:
            raise HTTPException(status_code=400, detail="Not enough gold (costs 100).")

        for m, q in recipe.items():
            consume_material(mats, m, q)

        # Find Forge facility
        forge = conn.execute("SELECT id, level FROM facilities WHERE type = 'Forge'").fetchone()
        if not forge:
            raise HTTPException(status_code=400, detail="You must build the Forge first!")
            
        # Get assigned heroes
        assigned = conn.execute("""
            SELECT h.* FROM facility_assignments fa
            JOIN heroes h ON fa.hero_id = h.id
            WHERE fa.facility_id = ? AND h.is_alive = 1
        """, (forge["id"],)).fetchall()
        
        # Calculate crafting power
        level = 1
        apt = 10
        crafter_name = "Nobody"

        if assigned:
            from services.class_service import forge_smith_bonus

            # Average level and apt
            level = sum(h["level"] for h in assigned) // len(assigned)
            apt = sum(h["apt_tactical"] + h["apt_survival"] for h in assigned) // (2 * len(assigned))

            assigned_classes = [h["hero_class"] for h in assigned]

            # Quality is capped by your single best Blacksmith present —
            # more of them at the same tier adds a smaller bonus on top,
            # but a pile of weak smiths can't out-craft one great one.
            smith_apt, smith_level, best_smith_cls = forge_smith_bonus(assigned_classes)
            apt += smith_apt
            level += smith_level
            if best_smith_cls:
                crafter_name = next(h["name"] for h in assigned if h["hero_class"] == best_smith_cls)
            else:
                crafter_name = assigned[0]["name"] + " (Unskilled)"

        # Forge base-upgrade (DEFAULT_UPGRADES "forge") used to claim it
        # "unlocks equipment crafting" — but crafting already works without
        # it, so that description never matched reality. Repurposed: a flat
        # quality nudge on top of whichever Blacksmith crafted it, same
        # scale as one smith-tier step (see SMITH_TIER_BONUS).
        from services.base_service import get_base_upgrade_level
        apt += get_base_upgrade_level(conn, "forge") * 10
        # The Forge FACILITY's own level (separate from the Base Upgrade
        # tier above) used to do nothing for crafting at all — leveling it
        # only bought more assignment slots. +5 apt/level now, so the
        # building itself is worth investing in, not just who's staffing it.
        apt += (forge["level"] - 1) * 5

        conn.execute("UPDATE base SET gold = gold - 100, materials = ? WHERE id = 1", (json.dumps(mats),))

        # Craft
        equip = craft_equipment_for_slot(req.slot, level, apt)
        # Credit the smith. CraftRequest carries no hero id — the Forge works
        # off whoever is ASSIGNED to it — so the maker is the best-qualified
        # assigned hero, which is also the one whose bonus set the quality.
        from services.equipment_service import origin_forged
        _smith = None
        if assigned:
            _smith = max(assigned, key=lambda h: (h["hero_class"] in ("Blacksmith", "Forge Lord", "Runesmith"),
                                                  h["level"]))
        equip["crafted_by"] = _smith["id"] if _smith else None
        equip["origin"] = origin_forged(_smith["name"] if _smith else None)
        equip_id = save_equipment(equip, conn=conn)

        if _smith:
            from services.deeds_service import record_craft_deed
            record_craft_deed(conn, _smith["id"], equip["name"], equip.get("rarity"))
        equip["id"] = equip_id
        
        # Grant XP to assigned heroes
        if assigned:
            for h in assigned:
                conn.execute("UPDATE heroes SET xp = COALESCE(xp, 0) + 500 WHERE id = ?", (h["id"],))
        
        return {"ok": True, "equipment": equip, "crafter_used": crafter_name}

@router.get("/inventory/equipment")
def get_equipment_inventory():
    from services.equipment_service import get_unequipped
    return get_unequipped()

class EquipRequest(BaseModel):
    equipment_id: int
    hero_id: int

@router.post("/inventory/equip")
def equip_item_endpoint(req: EquipRequest):
    from services.equipment_service import equip_item
    res = equip_item(req.equipment_id, req.hero_id)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

class UnequipRequest(BaseModel):
    equipment_id: int

@router.post("/inventory/unequip")
def unequip_item_endpoint(req: UnequipRequest):
    from services.equipment_service import unequip_item
    res = unequip_item(req.equipment_id)
    return res

# Facilities
from pydantic import BaseModel

class BuildFacilityReq(BaseModel):
    facility_type: str

@router.get("/facilities")
def get_base_facilities():
    from services.facility_service import get_facilities
    return get_facilities()

@router.post("/facilities/build")
def build_new_facility(req: BuildFacilityReq):
    from services.facility_service import build_facility
    try:
        return build_facility(req.facility_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class UpgradeFacilityReq(BaseModel):
    facility_id: int

@router.post("/facilities/upgrade")
def upgrade_existing_facility(req: UpgradeFacilityReq):
    from services.facility_service import upgrade_facility
    try:
        return upgrade_facility(req.facility_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class AssignFacilityReq(BaseModel):
    facility_id: int
    hero_id: int
    role: str = None
    target_hero_id: int = None
    target_skill_id: str = None

@router.post("/facilities/assign")
def assign_hero_facility(req: AssignFacilityReq):
    from services.facility_service import assign_hero_to_facility
    from services.dialogue_service import get_hero_line
    try:
        result = assign_hero_to_facility(req.facility_id, req.hero_id, req.role, req.target_hero_id, req.target_skill_id)
        with db() as conn:
            hero = conn.execute("SELECT hero_class, birth_star FROM heroes WHERE id = ?", (req.hero_id,)).fetchone()
        if hero and isinstance(result, dict):
            result["chatter_line"] = get_hero_line(hero["hero_class"], hero["birth_star"], "facility_assign")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

class RemoveFacilityReq(BaseModel):
    hero_id: int

@router.post("/facilities/remove")
def remove_hero_facility(req: RemoveFacilityReq):
    from services.facility_service import remove_hero_from_facility
    return remove_hero_from_facility(req.hero_id)

class SparReq(BaseModel):
    hero_a_id: int
    hero_b_id: int

@router.post("/facilities/spar")
def spar_heroes(req: SparReq):
    """Training Grounds sparring — peer or mentorship, auto-detected from the
    level gap. Both heroes must be assigned to the Training Grounds."""
    from services.sparring_service import spar
    with db() as conn:
        try:
            result = spar(conn, req.hero_a_id, req.hero_b_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    from services.quests_service import bump as bump_rite
    bump_rite("training_drill")
    return result

@router.get("/facilities/training")
def training_status():
    """Full Training Grounds state — assigned heroes, their regimens,
    conditioning cap, and per-hero skills for the weapon-drill picker."""
    from services.training_service import process_training, get_training_status
    from services.sparring_service import tournament_status
    with db() as conn:
        process_training(conn)  # settle any pending ticks before reporting
        status = get_training_status(conn)
        status["tournament"] = tournament_status(conn)
        return status

@router.post("/facilities/training/tournament")
def run_training_tournament():
    """Hold an internal sparring tournament among all Training-Grounds heroes.
    Once per day; morale lift for all entrants, prizes for the top finishers."""
    from services.sparring_service import run_tournament
    with db() as conn:
        try:
            return run_tournament(conn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

class RegimenReq(BaseModel):
    hero_id: int
    regimen: str | None = None
    focus: str | None = None
    intensity: str = "moderate"

@router.post("/facilities/training/regimen")
def set_training_regimen(req: RegimenReq):
    """Set a Training-Grounds-assigned hero's solo drill (regimen), its focus
    (stat for conditioning / skill id for weapon drills), and intensity."""
    from services.training_service import set_regimen, process_training
    with db() as conn:
        try:
            # Settle current regimen's gains first so switching mid-tick
            # doesn't credit the new regimen for old elapsed time.
            process_training(conn)
            result = set_regimen(conn, req.hero_id, req.regimen, req.focus, req.intensity)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if req.regimen:  # setting (not clearing) a drill counts toward the rites
        from services.quests_service import bump as bump_rite
        bump_rite("training_drill")
    return result

RESEARCH_UPGRADES = {
    "gold_boost": {"name": "Alchemical Transmutation", "desc": "+5% Gold from Tower", "max_level": 5, "base_cost": 100},
    "xp_boost": {"name": "Arcane Insight", "desc": "+10% Skill XP Gain", "max_level": 5, "base_cost": 150},
    "drop_boost": {"name": "Treasure Finding", "desc": "+5% Equipment Drop Rate", "max_level": 5, "base_cost": 200},
}

@router.get("/facilities/mage-tower/upgrades")
def get_research_upgrades():
    with db() as conn:
        base = conn.execute("SELECT research_points, global_buffs FROM base WHERE id = 1").fetchone()
        buffs = json.loads(base["global_buffs"] or "{}")
        
    res = []
    for uid, info in RESEARCH_UPGRADES.items():
        lvl = buffs.get(uid, 0)
        res.append({
            "id": uid,
            "name": info["name"],
            "desc": info["desc"],
            "level": lvl,
            "max_level": info["max_level"],
            "cost": info["base_cost"] * (lvl + 1)
        })
    return {"points": base["research_points"], "upgrades": res}

class BuyResearchReq(BaseModel):
    upgrade_id: str

@router.post("/facilities/mage-tower/buy")
def buy_research_upgrade(req: BuyResearchReq):
    with db() as conn:
        base = conn.execute("SELECT research_points, global_buffs FROM base WHERE id = 1").fetchone()
        buffs = json.loads(base["global_buffs"] or "{}")
        
        info = RESEARCH_UPGRADES.get(req.upgrade_id)
        if not info:
            raise HTTPException(status_code=400, detail="Invalid upgrade.")
            
        lvl = buffs.get(req.upgrade_id, 0)
        if lvl >= info["max_level"]:
            raise HTTPException(status_code=400, detail="Max level reached.")
            
        cost = info["base_cost"] * (lvl + 1)
        if base["research_points"] < cost:
            raise HTTPException(status_code=400, detail=f"Requires {cost} Research Points.")
            
        buffs[req.upgrade_id] = lvl + 1
        conn.execute("UPDATE base SET research_points = research_points - ?, global_buffs = ? WHERE id = 1",
                     (cost, json.dumps(buffs)))

    return {"ok": True}

# ─── The Athenaeum (research map) ─────────────────────────────────

@router.get("/facilities/athenaeum/state")
def athenaeum_state():
    from services.athenaeum_service import get_state
    return get_state()

class AthenaeumStudyReq(BaseModel):
    node_id: str

@router.post("/facilities/athenaeum/study")
def athenaeum_study(req: AthenaeumStudyReq):
    from services.athenaeum_service import begin_study
    try:
        return begin_study(req.node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ─── Mail System ──────────────────────────────────────────────────

@router.get("/mail/list")
def list_mail():
    with db() as conn:
        rows = conn.execute("SELECT * FROM mail ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

class ClaimMailReq(BaseModel):
    mail_id: int

@router.post("/mail/claim")
def claim_mail(req: ClaimMailReq):
    with db() as conn:
        mail = conn.execute("SELECT * FROM mail WHERE id = ?", (req.mail_id,)).fetchone()
        if not mail:
            raise HTTPException(status_code=404, detail="Mail not found.")
        if mail["is_claimed"]:
            raise HTTPException(status_code=400, detail="Mail already claimed.")

        rewards = json.loads(mail["rewards_json"])
        
        # Grant rewards
        if "gems" in rewards:
            conn.execute("UPDATE base SET gems = gems + ? WHERE id = 1", (rewards["gems"],))
        if "gold" in rewards:
            conn.execute("UPDATE base SET gold = gold + ? WHERE id = 1", (rewards["gold"],))
        # Legacy mail may still carry a "supplies" reward — grant it as
        # ingredients, the currency that replaced it.
        if "ingredients" in rewards or "supplies" in rewards:
            amt = rewards.get("ingredients", 0) + rewards.get("supplies", 0)
            conn.execute("UPDATE base SET ingredients = ingredients + ? WHERE id = 1", (amt,))
        if "aether" in rewards:
            conn.execute("UPDATE base SET aether = aether + ? WHERE id = 1", (rewards["aether"],))
        # Guild-shop style ticket grants: {"summon_ticket": "5-Star Summon Ticket"}
        # (same shape achievements use) or {"tickets": {name: qty}}.
        ticket_grants = {}
        if rewards.get("summon_ticket"):
            ticket_grants[rewards["summon_ticket"]] = 1
        for name, qty in (rewards.get("tickets") or {}).items():
            ticket_grants[name] = ticket_grants.get(name, 0) + int(qty)
        for name, qty in ticket_grants.items():
            row2 = conn.execute(
                "SELECT id FROM inventory WHERE item_name = ? AND item_type = 'summon_ticket'", (name,)
            ).fetchone()
            if row2:
                conn.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?", (qty, row2["id"]))
            else:
                conn.execute(
                    "INSERT INTO inventory (item_name, item_type, quantity, description) VALUES (?, 'summon_ticket', ?, ?)",
                    (name, qty, "A guaranteed-star summon, redeemable at the Soul Gate."))

        conn.execute("UPDATE mail SET is_claimed = 1, is_read = 1 WHERE id = ?", (req.mail_id,))
    return {"ok": True, "rewards": rewards}

class ReceiveMailReq(BaseModel):
    sender: str
    subject: str
    body: str
    rewards_json: dict

@router.post("/mail/receive")
def receive_mail(req: ReceiveMailReq):
    with db() as conn:
        conn.execute(
            "INSERT INTO mail (sender, subject, body, rewards_json) VALUES (?, ?, ?, ?)",
            (req.sender, req.subject, req.body, json.dumps(req.rewards_json))
        )
    return {"ok": True}
