import random
from database import db

# ── provenance ──────────────────────────────────────────────────────────────
#
# Every piece of gear says where it came from. A blade pulled from a floor-50
# chest reads better than a blank, and a forged one carries its smith's name
# wherever it ends up — including onto the smith's own record, once it does
# something worth remembering.
ORIGIN_UNKNOWN = "Of unknown origin"
ORIGIN_SUMMONED = "Drawn from the summoning array"
ORIGIN_STARTER = "Issued at the outset"


def origin_forged(smith_name: str = None) -> str:
    return f"Forged by {smith_name}" if smith_name else "Forged at the base"


def is_remarkable(rarity: str) -> bool:
    """Is this piece rare enough to be worth remembering?

    Rarity in this game is LETTER GRADES (RARITY_TIERS: D- through Z), not
    words. Defined here, against the real ladder, so callers can't drift into
    inventing names for it — an earlier version of the deed gate compared
    against "Legendary"/"Mythic", which matches nothing and silently disabled
    every craft and chained deed.

    A- ("Exceptional") is the line: high enough that a smith reaching it is a
    genuine event, low enough that it happens more than once a campaign.
    """
    try:
        return RARITY_TIERS.index(rarity) >= RARITY_TIERS.index(REMARKABLE_MIN_RARITY)
    except (ValueError, AttributeError):
        return False


REMARKABLE_MIN_RARITY = "A-"


def origin_floor_drop(floor_number: int, rarity: str = None) -> str:
    """Drops name the floor, because 'floor 50, out of an A+ cache' is a story
    and 'found' is not."""
    if is_remarkable(rarity):
        adjective = EQUIPMENT_ADJECTIVES.get(rarity, rarity)
        return f"Claimed from a {adjective.lower()} cache on floor {floor_number}"
    return f"Recovered on floor {floor_number}"

def get_vault_capacity(conn) -> int:
    """Base storage of 20, +16 per Vault facility slot unlocked (matches
    the frontend's display formula in InventoryPage.jsx)."""
    vault = conn.execute("SELECT slots_unlocked FROM facilities WHERE base_id = 1 AND type = 'Vault'").fetchone()
    if not vault:
        return 20
    return 20 + (vault["slots_unlocked"] * 16)

def get_equipment_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM equipment").fetchone()["c"]

RARITY_TIERS = [
    "D-", "D", "D+",
    "C-", "C", "C+",
    "B-", "B", "B+",
    "A-", "A", "A+",
    "S-", "S", "S+",
    "SS", "SSS", "Z"
]

RARITY_MULTS = {
    "D-": 1.8, "D": 2.2, "D+": 2.6,
    "C-": 3.0, "C": 3.5, "C+": 4.0,
    "B-": 4.6, "B": 5.3, "B+": 6.0,
    "A-": 7.0, "A": 8.5, "A+": 10.0,
    "S-": 12.0, "S": 15.0, "S+": 18.0,
    "SS": 25.0,
    "SSS": 40.0,
    "Z": 100.0,
}

TYPES = ["Weapon", "Armor", "Accessory"]

# Equipment sets — 3 matching pieces (this game only has 3 slots total, so
# "3+" really just means "all three") grants a passive bonus on top of the
# gear's own flat/% stats. Lowest 3 rarity tiers never roll into a set —
# keeps early-game gear simple and makes a set drop feel like it means
# something. Only ~1 in 4 eligible drops gets a family at all, so most gear
# stays familyless flavor even at higher rarities.
EQUIPMENT_SET_FAMILIES = ["Ironclad", "Shadowveil", "Stormcaller", "Sanctum", "Wyrmguard"]
SET_FAMILY_CHANCE = 0.25
SET_FAMILY_MIN_RARITY_INDEX = 3  # RARITY_TIERS index — excludes D-, D, D+

EQUIPMENT_SET_BONUSES = {
    "Ironclad":    {"min_pieces": 3, "end_pct": 0.15, "dmg_reduction_pct": 0.05},
    "Shadowveil":  {"min_pieces": 3, "crit_chance": 0.08, "dodge_chance": 0.05},
    "Stormcaller": {"min_pieces": 3, "agi_pct": 0.15, "str_pct": 0.10},
    "Sanctum":     {"min_pieces": 3, "hlt_pct": 0.20},
    "Wyrmguard":   {"min_pieces": 3, "str_pct": 0.10, "end_pct": 0.10},
}

def roll_set_family(rarity: str) -> str | None:
    try:
        idx = RARITY_TIERS.index(rarity)
    except ValueError:
        return None  # "F" (starting weapon) and anything else unranked never rolls into a set
    if idx < SET_FAMILY_MIN_RARITY_INDEX:
        return None
    if random.random() < SET_FAMILY_CHANCE:
        return random.choice(EQUIPMENT_SET_FAMILIES)
    return None

EQUIPMENT_ADJECTIVES = {
    # "F" is intentionally not part of RARITY_TIERS/RARITY_MULTS — it's never
    # droppable, only ever auto-generated as a hero's guaranteed starting
    # weapon (see generate_starting_weapon below) so nobody fights bare-handed.
    "F": "Worn",
    "D-": "Cracked", "D": "Battered", "D+": "Crude",
    "C-": "Plain", "C": "Standard", "C+": "Fine",
    "B-": "Polished", "B": "Refined", "B+": "Masterwork",
    "A-": "Exceptional", "A": "Flawless", "A+": "Mythic",
    "S-": "Divine", "S": "Godly", "S+": "Transcendent", "SS": "Omnipotent", "SSS": "Absolute", "Z": "Eldritch",
}

ACCESSORY_TYPES = ["Ring", "Amulet", "Charm"]

def _display_type_name(eq_type: str, stats: dict) -> str:
    """'Weapon'/'Armor'/'Accessory' on their own say nothing about what the
    item actually is — use the rolled weapon_type/armor_type/accessory_type
    (Sword, Robe, Ring, etc.) in the item's name whenever one was rolled,
    falling back to the bare type name for pre-migration legacy gear."""
    return stats.get("weapon_type") or stats.get("armor_type") or stats.get("accessory_type") or eq_type

def generate_starting_weapon() -> dict:
    """Every hero starts with a guaranteed basic weapon instead of fighting
    unarmed — deliberately not part of the droppable rarity pool, and not
    worth being picky about (always a plain Sword). +1-2 STR is the floor
    the real D-S equipment scale (see _roll_equipment_stats) is calibrated
    against — D should be a real step up from this, not a multiple of it."""
    return {
        "name": "Worn Sword", "type": "Weapon", "rarity": "F", "level": 1,
        "base_str": random.randint(1, 2), "base_int": 0, "base_hlt": 0, "base_agi": 0, "base_def": 0,
        "str_pct": 0.0, "int_pct": 0.0, "hlt_pct": 0.0, "agi_pct": 0.0,
        "crit_chance": 0.0, "dodge_chance": 0.0, "armor_pen": 0.0, "dmg_reduction_pct": 0.0,
    }

def _rarity_from_score(score: float) -> str:
    if score < 150: return "D-"
    if score < 170: return "D"
    if score < 190: return "D+"
    if score < 210: return "C-"
    if score < 230: return "C"
    if score < 250: return "C+"
    if score < 270: return "B-"
    if score < 290: return "B"
    if score < 310: return "B+"
    if score < 330: return "A-"
    if score < 350: return "A"
    if score < 370: return "A+"
    if score < 390: return "S-"
    if score < 420: return "S"
    if score < 450: return "S+"
    if score < 500: return "SS"
    if score < 600: return "SSS"
    return "Z"

# Which weapon/armor TYPE a given enemy name thematically suggests, mirrored
# from materials_service.py's ENEMY_MATERIAL_HINTS — a sword dropping from a
# fight against pure beasts (Wolves, Spiders) read as just as arbitrary as
# the slime-core material bug did. Only the type is biased (Sword/Dagger/
# Spear/Bow/Staff or Heavy/Light/Brigandine/Robe), never which slot (Weapon
# vs Armor) drops at all — that's still the existing TYPES roll. Not
# exhaustive over the full 100+ enemy roster; unlisted enemies just fall
# back to the existing fully-random type roll.
ENEMY_EQUIPMENT_HINTS = {
    "Shadow Wisp": "Tome",
    "Goblin": "Dagger", "Goblin Warrior": "Sword", "Goblin Shaman": "Tome", "Goblin King": "Sword",
    "Hobgoblin": "Sword", "Hobgoblin Berserker": "Sword",
    "Bandit": "Dagger", "Kobold": "Dagger",
    "Skeleton": "Sword", "Skeleton Archer": "Bow",
    "Giant Spider": "Light Armor", "Spider Queen": "Light Armor", "Venomous Spider": "Light Armor",
    "Wolf": "Light Armor", "Mangy Hyena": "Light Armor",
    "Orc": "Sword", "Orc Warchief": "Sword",
    "Lizardman": "Spear",
    "Harpy": "Bow",
    "Ogre": "Heavy Armor", "The Ashen Colossus": "Heavy Armor",
    "Troll": "Heavy Armor", "The Troll King": "Heavy Armor", "Giant": "Heavy Armor",
    "Wyvern": "Bow", "Wyvern Stormrider": "Bow",
    "Demon": "Tome", "Pit Fiend": "Tome", "Archdemon": "Tome",
    "Vampire Spawn": "Tome", "Primordial Vampire": "Tome",
    "Young Dragon": "Brigandine", "Adult Dragon": "Brigandine", "Dracolich": "Robe",
}


def _pick_biased_type(eq_type: str, enemy_names: list[str] = None) -> str | None:
    """70% chance to use an enemy-thematic weapon/armor type if one of the
    fought enemies has a hint for this eq_type's category, else a plain
    random roll — same probability and fallback shape as
    materials_service.roll_material_name_for_enemies."""
    from services.class_service import WEAPON_TYPES, ARMOR_TYPES
    pool = WEAPON_TYPES if eq_type == "Weapon" else ARMOR_TYPES
    if enemy_names:
        candidates = [ENEMY_EQUIPMENT_HINTS[n] for n in enemy_names if ENEMY_EQUIPMENT_HINTS.get(n) in pool]
        if candidates and random.random() < 0.7:
            return random.choice(candidates)
    return random.choice(pool)


def _roll_equipment_stats(eq_type: str, mult: float, enemy_names: list[str] = None) -> dict:
    """Roll base stats for a piece of gear at a given rarity multiplier.

    The primary stat (base_str for weapons, base_int/base_hlt for armor) is
    rolled in a tight +/-4% band around a fixed center, NOT a wide range
    like the old random.randint(1, 3) — that 3x in-tier spread overlapped
    with the ~13-25% gap between adjacent rarity multipliers, so a
    lucky-rolled C could out-stat an unlucky B. The tight band keeps every
    tier strictly ahead of the one below it (worst B+ > best B, etc.) while
    still leaving a little roll variety. Secondary/bonus stats (crit, dodge,
    armor pen, % stats) keep their wider existing randomness since they're
    itemization flavor, not the stat that defines the tier.
    """
    # Was `scale = int(10 * mult)` then base_str ~= scale*2 ~= mult*20 — with
    # mult ranging 1.8 (D-) to 100 (Z), that put a D- weapon at +36 Strength
    # and a Z weapon at +2000, against hero base stats typically in the
    # single-to-low-double digits early on. A "D" item giving +50 STR (5x a
    # fresh hero's whole stat) was a confirmed real complaint. Rescaled
    # against the F-tier starter weapon (+4 STR, generate_starting_weapon)
    # as the floor: D lands around +3-5 (a real step up from the starter,
    # not a multiple of it), scaling up to ~+150-200 at Z so top-tier gear
    # still feels like a "huge impact" purchase late-game, not a footnote.
    base_str = base_int = base_hlt = base_agi = base_def = base_end = base_wil = base_luck = 0
    crit = dodge = armor_pen = dmg_reduction_pct = 0.0
    str_pct = int_pct = hlt_pct = agi_pct = 0.0
    weapon_type = accessory_type = None

    # The % stats below (crit/dodge/armor_pen/dmg_reduction_pct/*_pct) used
    # to multiply their roll range directly by `mult` (1.8 to 100) with no
    # cap — same root issue as the flat stats above, just expressed as a
    # percentage instead of a flat number. A Z-tier accessory could roll
    # 500%+ bonus Strength or 470% crit chance (confirmed via direct test).
    # `pct_mult` rescales that same 1.8-100 range down to a sane ~0.07-4
    # range so the top tier lands around 10-30% instead of multiple
    # hundred percent.
    pct_mult = mult / 25

    # Sub-linear %-roll helper: meaningful even at D-tier (~1-2%) without
    # exploding at Z (mult=100 lands ~13-25%, not several hundred percent).
    # The old linear pct_mult rolls bottomed out at fractions of a percent —
    # low-tier accessories displayed "+0%" stats (confirmed complaint).
    def _pct(scale=1.0):
        return round(random.uniform(0.8, 1.6) * (mult ** 0.6) * scale / 100, 4)

    if eq_type == "Weapon":
        # Each weapon type has its own stat identity instead of everything
        # being a STR stick: Swords are pure STR, Spears trade some STR for
        # AGI, Tomes are the INT weapon (mage grimoires), Bows lean AGI with
        # high crit, Daggers split STR/AGI with crit + armor pen. Primary
        # budgets all sum to roughly the same mult*(1.6-2.0) total so no
        # type is strictly better, just differently shaped.
        weapon_type = _pick_biased_type(eq_type, enemy_names)
        if weapon_type == "Tome":
            base_int = max(1, round(mult * random.uniform(1.6, 2.0)))
            base_wil = round(mult * random.uniform(0.2, 0.4))
            if random.random() < 0.3: int_pct = _pct()
        elif weapon_type == "Bow":
            base_agi = max(1, round(mult * random.uniform(1.0, 1.3)))
            base_str = max(1, round(mult * random.uniform(0.5, 0.7)))
            if random.random() < 0.45: crit = _pct()
        elif weapon_type == "Dagger":
            base_str = max(1, round(mult * random.uniform(0.8, 1.0)))
            base_agi = max(1, round(mult * random.uniform(0.8, 1.0)))
            if random.random() < 0.4: crit = _pct()
            if random.random() < 0.3: armor_pen = _pct()
        elif weapon_type == "Spear":
            base_str = max(1, round(mult * random.uniform(1.2, 1.5)))
            base_agi = round(mult * random.uniform(0.4, 0.6))
            if random.random() < 0.35: armor_pen = _pct()
        else:  # Sword (and untyped fallback)
            base_str = max(1, round(mult * random.uniform(1.6, 2.0)))
            base_agi = round(mult * random.uniform(0, 0.45))
            if random.random() < 0.3: crit = _pct()
    elif eq_type == "Armor":
        # Armor's primary stat is Endurance (was flat Defense, then base_int
        # before that — Defense/Endurance has always been the real combat
        # stat behind this slot, base_def kept in sync for legacy reads).
        base_end = max(1, round(mult * random.uniform(1.6, 2.0)))
        base_def = base_end
        base_hlt = max(1, round(mult * random.uniform(6.0, 7.5)))
        if random.random() < 0.4: dmg_reduction_pct = random.uniform(0.01, 0.04) * pct_mult
    else:
        # Accessories now have sub-types with distinct identities (same shape
        # as weapon/armor types), each with guaranteed meaningful stats plus
        # some probabilistic extras — replaces the old fully-random grab-bag
        # where a low-tier accessory could roll nothing but a fraction-of-a-
        # percent bonus that displayed as "+0%" (confirmed complaint).
        accessory_type = random.choice(ACCESSORY_TYPES)
        if accessory_type == "Ring":
            # Raw combat stats — two guaranteed flats from STR/INT/AGI,
            # with a chance at a matching % bonus on top.
            flat_a, flat_b = random.sample(["str", "int", "agi"], 2)
            flats = {flat_a: max(1, round(mult * random.uniform(0.6, 0.9))),
                     flat_b: max(1, round(mult * random.uniform(0.4, 0.7)))}
            base_str = flats.get("str", 0)
            base_int = flats.get("int", 0)
            base_agi = flats.get("agi", 0)
            if random.random() < 0.5:
                pct_key = random.choice(["str_pct", "int_pct", "agi_pct"])
                if pct_key == "str_pct": str_pct = _pct()
                elif pct_key == "int_pct": int_pct = _pct()
                else: agi_pct = _pct()
        elif accessory_type == "Amulet":
            # Survivability — guaranteed HP + Willpower, with %HP and damage
            # reduction as the probabilistic extras.
            base_hlt = max(1, round(mult * random.uniform(3.0, 4.5)))
            base_wil = max(1, round(mult * random.uniform(0.4, 0.6)))
            if random.random() < 0.5: hlt_pct = _pct(1.5)
            if random.random() < 0.35: dmg_reduction_pct = _pct(0.6)
        else:  # Charm
            # Fortune — guaranteed Luck + one of crit/dodge, with more
            # proc-style stats as extras.
            base_luck = max(1, round(mult * random.uniform(0.5, 0.8)))
            if random.random() < 0.5: crit = _pct(1.2)
            else: dodge = _pct(1.2)
            if random.random() < 0.4: armor_pen = _pct()
            if random.random() < 0.3:
                if crit == 0: crit = _pct()
                else: dodge = _pct()

    armor_type = None
    if eq_type == "Armor":
        armor_type = _pick_biased_type(eq_type, enemy_names)
        # Each armor type leans a slightly different way instead of being
        # a pure reskin — Heavy trades mobility flavor for raw bulk, Light
        # trades bulk for dodge, Robe trades bulk for arcane potency,
        # Medium stays the unmodified baseline rolled above.
        if armor_type == "Heavy Armor":
            base_end = round(base_end * 1.25)
            base_def = base_end
            base_hlt = round(base_hlt * 1.15)
            dmg_reduction_pct += 0.02
        elif armor_type == "Light Armor":
            base_end = round(base_end * 0.80)
            base_def = base_end
            dodge += 0.03
        elif armor_type == "Robe":
            base_end = round(base_end * 0.70)
            base_def = base_end
            base_hlt = round(base_hlt * 0.90)
            int_pct += 0.03

    return {
        "base_str": base_str, "base_int": base_int, "base_hlt": base_hlt, "base_agi": base_agi, "base_def": base_def,
        "base_end": base_end, "base_wil": base_wil, "base_luck": base_luck,
        "str_pct": str_pct, "int_pct": int_pct, "hlt_pct": hlt_pct, "agi_pct": agi_pct,
        "crit_chance": crit, "dodge_chance": dodge, "armor_pen": armor_pen, "dmg_reduction_pct": dmg_reduction_pct,
        "weapon_type": weapon_type, "armor_type": armor_type, "accessory_type": accessory_type,
    }

def save_equipment(equip: dict, conn=None) -> int:
    """Insert an already-built equipment dict (name/type/rarity/stats) that
    hasn't been persisted yet, and return its new row id.

    Pass `conn` if the caller is already inside a `with db() as conn:` block —
    opening a second connection while the first is still uncommitted raises
    'database is locked' on SQLite."""
    # crafted_by is NULL for anything not forged — a smith's name on a blade
    # found in a chest would be a lie. `origin` covers those instead, so every
    # piece can say where it came from rather than showing a blank.
    sql = "INSERT INTO equipment (name, type, rarity, level, base_str, base_int, base_hlt, base_agi, base_def, base_end, base_wil, base_luck, str_pct, int_pct, hlt_pct, agi_pct, crit_chance, dodge_chance, armor_pen, dmg_reduction_pct, set_family, weapon_type, armor_type, accessory_type, crafted_by, origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    params = (
        equip["name"], equip["type"], equip["rarity"], equip.get("level", 1),
        equip.get("base_str", 0), equip.get("base_int", 0), equip.get("base_hlt", 0), equip.get("base_agi", 0), equip.get("base_def", 0),
        equip.get("base_end", 0), equip.get("base_wil", 0), equip.get("base_luck", 0),
        equip.get("str_pct", 0.0), equip.get("int_pct", 0.0), equip.get("hlt_pct", 0.0), equip.get("agi_pct", 0.0),
        equip.get("crit_chance", 0.0), equip.get("dodge_chance", 0.0), equip.get("armor_pen", 0.0), equip.get("dmg_reduction_pct", 0.0),
        equip.get("set_family"), equip.get("weapon_type"), equip.get("armor_type"), equip.get("accessory_type"),
        equip.get("crafted_by"), equip.get("origin") or ORIGIN_UNKNOWN,
    )
    if conn is not None:
        return conn.execute(sql, params).lastrowid
    with db() as conn:
        return conn.execute(sql, params).lastrowid

def craft_equipment_for_slot(slot: str, level: int, apt: int) -> dict:
    """Build (but don't yet save) equipment for a specific Forge slot, using
    explicit crafting power (level/apt — already includes any Blacksmith
    bonus from forge_craft) instead of re-deriving it from a crafter_id."""
    eq_type = {"weapon": "Weapon", "armor": "Armor"}.get(slot, "Accessory")

    score = level + apt + random.randint(-20, 100)
    rarity = _rarity_from_score(score)
    mult = RARITY_MULTS[rarity]
    stats = _roll_equipment_stats(eq_type, mult)
    name = f"{EQUIPMENT_ADJECTIVES.get(rarity, rarity)} {_display_type_name(eq_type, stats)}"

    return {
        "name": name, "type": eq_type, "rarity": rarity, "level": max(1, level),
        "set_family": roll_set_family(rarity),
        **stats,
    }

def get_all_equipment():
    with db() as conn:
        rows = conn.execute("SELECT * FROM equipment ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def get_hero_equipment(hero_id: int):
    with db() as conn:
        rows = conn.execute("SELECT * FROM equipment WHERE is_equipped_to = ?", (hero_id,)).fetchall()
        return [dict(r) for r in rows]

def get_unequipped():
    with db() as conn:
        rows = conn.execute("SELECT * FROM equipment WHERE is_equipped_to IS NULL ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def equip_item(hero_id: int, equipment_id: int):
    with db() as conn:
        item = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        if not item:
            raise ValueError("Equipment not found")

        # Weapon Art hard restriction — a typed weapon (weapon_type set)
        # can only go on a class whose affinity list includes that type.
        # Untyped legacy weapons (weapon_type is None) are grandfathered
        # in and stay equippable by anyone. A class with no defined
        # affinity at all (empty list) also has no restriction.
        if item["type"] == "Weapon" and item["weapon_type"]:
            from services.class_service import get_weapon_affinity
            hero = conn.execute("SELECT hero_class FROM heroes WHERE id = ?", (hero_id,)).fetchone()
            if hero:
                affinity = get_weapon_affinity(hero["hero_class"])
                if affinity and item["weapon_type"] not in affinity:
                    raise ValueError(f"{hero['hero_class']} can't wield a {item['weapon_type']} (affinity: {', '.join(affinity)}).")

        # Same hard restriction for armor types (Robe/Light/Medium/Heavy) —
        # untyped legacy armor and classes with no defined affinity stay
        # unrestricted, identical grandfathering rule as weapons.
        if item["type"] == "Armor" and item["armor_type"]:
            from services.class_service import get_armor_affinity
            hero = conn.execute("SELECT hero_class FROM heroes WHERE id = ?", (hero_id,)).fetchone()
            if hero:
                affinity = get_armor_affinity(hero["hero_class"])
                if affinity and item["armor_type"] not in affinity:
                    raise ValueError(f"{hero['hero_class']} can't wear {item['armor_type']} (affinity: {', '.join(affinity)}).")

        # Free up a slot. Weapons/Armor have one slot each; Accessories get
        # TWO — only bump the oldest-equipped accessory once both are full.
        if item["type"] == "Accessory":
            worn = conn.execute(
                "SELECT id FROM equipment WHERE is_equipped_to = ? AND type = 'Accessory' AND id != ? ORDER BY id",
                (hero_id, equipment_id)
            ).fetchall()
            if len(worn) >= 2:
                conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE id = ?", (worn[0]["id"],))
        else:
            conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE is_equipped_to = ? AND type = ?", (hero_id, item["type"]))

        # Equip the new item
        conn.execute("UPDATE equipment SET is_equipped_to = ? WHERE id = ?", (hero_id, equipment_id))
        return {"success": True}

def unequip_item(equipment_id: int):
    with db() as conn:
        conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE id = ?", (equipment_id,))
        return {"success": True}

def unequip_all(hero_id: int):
    with db() as conn:
        conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE is_equipped_to = ?", (hero_id,))
    return {"success": True}

def auto_equip_hero(hero_id: int):
    """For each slot (Weapon/Armor/2x Accessory), find the highest-rarity
    unequipped item this hero can use and equip it, replacing whatever is in that slot."""
    from services.class_service import get_weapon_affinity, get_armor_affinity
    with db() as conn:
        hero = conn.execute("SELECT hero_class FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not hero:
            raise ValueError("Hero not found")
        hero_class = hero["hero_class"]
        weapon_affinity = get_weapon_affinity(hero_class)
        armor_affinity = get_armor_affinity(hero_class)

        unequipped = conn.execute(
            "SELECT * FROM equipment WHERE is_equipped_to IS NULL AND rarity != 'F' ORDER BY level DESC"
        ).fetchall()

        rarity_index = {r: i for i, r in enumerate(RARITY_TIERS)}

        def score(row):
            return (rarity_index.get(row["rarity"], -1), row["level"] or 0)

        def can_use(row):
            if row["type"] == "Weapon" and row["weapon_type"] and weapon_affinity:
                return row["weapon_type"] in weapon_affinity
            if row["type"] == "Armor" and row["armor_type"] and armor_affinity:
                return row["armor_type"] in armor_affinity
            return True

        equipped_count = 0
        for slot in ("Weapon", "Armor"):
            candidates = [dict(r) for r in unequipped if r["type"] == slot and can_use(r)]
            if not candidates:
                continue
            best = max(candidates, key=score)
            conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE is_equipped_to = ? AND type = ?", (hero_id, slot))
            conn.execute("UPDATE equipment SET is_equipped_to = ? WHERE id = ?", (hero_id, best["id"]))
            equipped_count += 1

        # Accessories fill both slots with the top-2 available.
        acc_candidates = sorted(
            [dict(r) for r in unequipped if r["type"] == "Accessory"],
            key=score, reverse=True
        )[:2]
        if acc_candidates:
            conn.execute("UPDATE equipment SET is_equipped_to = NULL WHERE is_equipped_to = ? AND type = 'Accessory'", (hero_id,))
            for acc in acc_candidates:
                conn.execute("UPDATE equipment SET is_equipped_to = ? WHERE id = ?", (hero_id, acc["id"]))
                equipped_count += 1

    return {"success": True, "slots_filled": equipped_count}

def scrap_equipment(equipment_id: int) -> dict:
    """Break down an unwanted piece of gear into crafting materials, scaled
    by rarity — a way to clean up the Vault without just deleting value."""
    import json
    import random
    from services.materials_service import CRAFTING_MATERIALS, MATERIAL_TIERS, tiered_material_name

    with db() as conn:
        item = conn.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,)).fetchone()
        if not item:
            raise ValueError("Equipment not found.")
        item = dict(item)
        if item.get("is_equipped_to"):
            raise ValueError("Unequip this item before scrapping it.")

        mult = RARITY_MULTS.get(item["rarity"], 1.0)
        # Better gear scraps into a better material tier, not just more of it.
        tier_idx = min(len(MATERIAL_TIERS) - 1, int(mult / 4))
        mat_name = tiered_material_name(random.choice(CRAFTING_MATERIALS), MATERIAL_TIERS[tier_idx])
        amount = max(1, int(random.randint(2, 4) * mult / 2))

        base_row = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
        current_mats = json.loads(base_row["materials"]) if base_row["materials"] else {}
        current_mats[mat_name] = current_mats.get(mat_name, 0) + amount
        conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(current_mats),))

        conn.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))

    return {"ok": True, "material": mat_name, "amount": amount, "scrapped": item["name"]}

def ensure_hero_has_weapon(hero_id: int, hero_eq: list) -> list:
    """A hero with no weapon equipped (including one who unequipped the
    F-grade starter — nothing stops a player from doing that) would
    otherwise fight bare-handed with no weapon stat bonus at all. Rather
    than persisting a real F-grade item to the equipment table (the old
    approach — it then had to be hidden from every inventory view forever
    and never had a clean way back to "weaponless" once issued), this
    injects a purely in-memory placeholder dict with the same stat shape
    apply_equipment_stats reads, used for this one stat calculation only
    and never written to the database. The hero stays genuinely
    weaponless in the Vault between fights, exactly like having no weapon
    at all — this only ever exists for the duration of a single combat
    resolution. Mutates hero_eq in place and returns it."""
    if any(eq["type"] == "Weapon" for eq in hero_eq):
        return hero_eq
    weapon = generate_starting_weapon()
    weapon["id"] = None
    weapon["is_equipped_to"] = hero_id
    hero_eq.append(weapon)
    return hero_eq


def apply_equipment_stats(hero: dict, equipment_list: list = None) -> dict:
    """Add equipped gear's stat bonuses on top of a hero's (already
    level-scaled, if the caller did that first) strength/intelligence/agility/health.
    Pass equipment_list if the caller already has it (e.g. a bulk-fetched
    list for a whole roster) to avoid a redundant per-hero query."""
    hero_eq = equipment_list if equipment_list is not None else get_hero_equipment(hero["id"])
    hero_eq = ensure_hero_has_weapon(hero["id"], hero_eq)

    str_pct = int_pct = hlt_pct = agi_pct = 0.0
    dmg_reduction_pct = hero.get("dmg_reduction_pct", 0.0)
    end_bonus = 0

    for eq in hero_eq:
        hero["strength"] += eq["base_str"]
        hero["intelligence"] += eq["base_int"]
        hero["max_health"] += eq["base_hlt"]
        hero["health"] += eq["base_hlt"]
        hero["agility"] += eq["base_agi"]
        hero["defense"] = hero.get("defense", 5) + eq.get("base_def", 0)
        # Endurance gear bonus adds to max_health too (HP_PER_ENDURANCE per
        # point), same relationship as hero creation/leveling — accumulated
        # and applied once below, alongside base_hlt/hlt_pct.
        end_bonus += eq.get("base_end", 0)
        hero["endurance"] = hero.get("endurance", hero.get("defense", 5)) + eq.get("base_end", 0)
        hero["willpower"] = hero.get("willpower", 6) + eq.get("base_wil", 0)
        hero["luck"] = hero.get("luck", 5) + eq.get("base_luck", 0)
        dmg_reduction_pct += eq.get("dmg_reduction_pct", 0.0)

        str_pct += eq.get("str_pct", 0.0)
        int_pct += eq.get("int_pct", 0.0)
        hlt_pct += eq.get("hlt_pct", 0.0)
        agi_pct += eq.get("agi_pct", 0.0)

        if "crit_chance" in hero:
            hero["crit_chance"] += eq.get("crit_chance", 0)
        if "dodge_chance" in hero:
            hero["dodge_chance"] += eq.get("dodge_chance", 0)
        if "armor_pen" in hero:
            hero["armor_pen"] += eq.get("armor_pen", 0)

    if end_bonus:
        from services.gacha_service import HP_PER_ENDURANCE
        hero["max_health"] += end_bonus * HP_PER_ENDURANCE
        hero["health"] += end_bonus * HP_PER_ENDURANCE

    # Apply percentage buffs after flat buffs are added
    if str_pct > 0: hero["strength"] = int(hero["strength"] * (1 + str_pct))
    if int_pct > 0: hero["intelligence"] = int(hero["intelligence"] * (1 + int_pct))
    if agi_pct > 0: hero["agility"] = int(hero["agility"] * (1 + agi_pct))
    if hlt_pct > 0:
        old_max = hero["max_health"]
        hero["max_health"] = int(hero["max_health"] * (1 + hlt_pct))
        hero["health"] += (hero["max_health"] - old_max)

    # Capped well short of 100% — %DR is meant to stack with the Defense
    # stat, not let stacked gear make a hero outright unhittable.
    hero["dmg_reduction_pct"] = min(0.6, dmg_reduction_pct)
    hero["equipment"] = hero_eq
    return hero

def apply_set_bonuses(hero: dict, equipment_list: list = None) -> dict:
    """Counts equipped pieces per set_family; any family with at least
    min_pieces equipped grants its bonus once — there's only 3 equip slots
    total, so "3+" effectively means "the whole set is on." Must run AFTER
    apply_equipment_stats so its % bonuses stack on top of gear's own
    already-resolved flat-then-% numbers, same ordering apply_equipment_stats
    itself uses internally."""
    hero_eq = equipment_list if equipment_list is not None else hero.get("equipment", [])
    counts = {}
    for eq in hero_eq:
        fam = eq.get("set_family")
        if fam:
            counts[fam] = counts.get(fam, 0) + 1

    for fam, count in counts.items():
        bonus = EQUIPMENT_SET_BONUSES.get(fam)
        if not bonus or count < bonus["min_pieces"]:
            continue
        if "str_pct" in bonus: hero["strength"] = int(hero["strength"] * (1 + bonus["str_pct"]))
        if "agi_pct" in bonus: hero["agility"] = int(hero["agility"] * (1 + bonus["agi_pct"]))
        if "end_pct" in bonus: hero["endurance"] = int(hero.get("endurance", hero.get("defense", 5)) * (1 + bonus["end_pct"]))
        if "hlt_pct" in bonus:
            old_max = hero["max_health"]
            hero["max_health"] = int(hero["max_health"] * (1 + bonus["hlt_pct"]))
            hero["health"] += hero["max_health"] - old_max
        if "crit_chance" in bonus: hero["crit_chance"] = hero.get("crit_chance", 0.05) + bonus["crit_chance"]
        if "dodge_chance" in bonus: hero["dodge_chance"] = hero.get("dodge_chance", 0.0) + bonus["dodge_chance"]
        if "dmg_reduction_pct" in bonus:
            hero["dmg_reduction_pct"] = min(0.6, hero.get("dmg_reduction_pct", 0.0) + bonus["dmg_reduction_pct"])

    return hero

def craft_equipment(crafter_id: int):
    with db() as conn:
        crafter = conn.execute("SELECT level, apt_tactical, hero_class FROM heroes WHERE id = ?", (crafter_id,)).fetchone()
        if not crafter:
            raise ValueError("Crafter not found")
            
        base = conn.execute("SELECT gold FROM base WHERE id = 1").fetchone()
        cost = 500
        if base["gold"] < cost:
            raise ValueError("Not enough gold to craft.")
            
        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (cost,))

        level = crafter["level"]
        apt = crafter["apt_tactical"]
        hero_class = crafter["hero_class"]

        eq_type = random.choice(TYPES)

        score = (level) + (apt)

        if hero_class in ("Forge Lord", "Runesmith"):
            score *= 2.5
        elif hero_class == "Master Smith":
            score *= 1.8
        elif hero_class in ("Blacksmith", "Weaponsmith", "Armorer", "Artificer"):
            score *= 1.3

        score += random.randint(-20, 100)
        rarity = _rarity_from_score(score)

        mult = RARITY_MULTS[rarity]
        stats = _roll_equipment_stats(eq_type, mult)

        adj = EQUIPMENT_ADJECTIVES.get(rarity, rarity)
        name = f"{adj} {_display_type_name(eq_type, stats)}"

        set_family = roll_set_family(rarity)
        # Route through save_equipment so crafting persists the full stat
        # set (base_end/wil/luck, dmg_reduction, accessory_type) — its old
        # bespoke INSERT silently dropped every column added since.
        equip_dict = {"name": name, "type": eq_type, "rarity": rarity, "level": level, "set_family": set_family, **stats}
        new_id = save_equipment(equip_dict, conn=conn)
        return {"id": new_id, "name": name, "type": eq_type, "rarity": rarity, "set_family": set_family,
                "weapon_type": stats.get("weapon_type"), "armor_type": stats.get("armor_type"), "accessory_type": stats.get("accessory_type")}

def generate_equipment_drop(floor_number: int, is_boss: bool = False, drop_bonus: float = 0.0, rarity_boost: float = 0.0, enemy_names: list[str] = None) -> dict | None:
    # Base chance: 10% on normal floors, 100% on bosses
    base_chance = 1.0 if is_boss else 0.10
    total_chance = min(1.0, base_chance + drop_bonus)

    if random.random() > total_chance:
        return None

    score = floor_number * 3 + random.randint(0, 50) + rarity_boost
    if is_boss:
        score += 100
        
    rarity = _rarity_from_score(score)
    eq_type = random.choice(TYPES)
    mult = RARITY_MULTS[rarity]

    stats = _roll_equipment_stats(eq_type, mult, enemy_names=enemy_names)
        
    adjectives = {"F-": "Broken", "F": "Rusted", "F+": "Chipped", "E-": "Poor", "E": "Basic", "E+": "Sturdy", "D-": "Standard", "D": "Polished", "D+": "Heavy", "C-": "Fine", "C": "Refined", "C+": "Balanced", "B-": "Masterwork", "B": "Exceptional", "B+": "Flawless", "A-": "Epic", "A": "Legendary", "A+": "Mythic", "S-": "Divine", "S": "Godly", "S+": "Transcendent", "SS": "Omnipotent", "SSS": "Absolute", "Z": "Eldritch"}
    adj = adjectives.get(rarity, rarity)
    name = f"{adj} {_display_type_name(eq_type, stats)}"

    result = {
        "name": name, "type": eq_type, "rarity": rarity,
        "level": max(1, floor_number // 5),
        "set_family": roll_set_family(rarity),
    }
    result.update(stats)
    return result
