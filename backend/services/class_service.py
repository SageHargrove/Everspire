"""
Class System
============
Handles class assignment, evolutions, class effects in combat, and base class passives.
"""

import random

# ---------------------------------------------------------------------------
# Class Evolution Trees
# ---------------------------------------------------------------------------

# { BaseClass: { 30: [Evo1, Evo2, Evo3], 60: { Evo1: [Evo1a, Evo1b], ... } } }
CLASS_EVOLUTIONS = {
    # COMBAT
    "Warrior": {
        30: ["Knight", "Berserker", "Paladin"],
        60: {
            "Knight": ["Aegis", "Templar"],
            "Berserker": ["Bloodrager", "Juggernaut"],
            "Paladin": ["Crusader", "Divine Sentinel"]
        }
    },
    "Spearman": {
        30: ["Lancer", "Halberdier", "Dragoon"],
        60: {
            "Lancer": ["Pikemaster", "Vanguard"],
            "Halberdier": ["Glaive Lord", "Warlord"],
            "Dragoon": ["Wyvern Rider", "Dragon Knight"]
        }
    },
    "Thief": {
        30: ["Assassin", "Rogue", "Ninja"],
        60: {
            "Assassin": ["Shadowblade", "Phantom"],
            "Rogue": ["Nightstalker", "Trickster"],
            "Ninja": ["Shinobi", "Shadowmaster"]
        }
    },
    "Archer": {
        30: ["Sniper", "Ranger", "Crossbowman"],
        60: {
            "Sniper": ["Marksman", "Deadeye"],
            "Ranger": ["Beastmaster", "Warden"],
            "Crossbowman": ["Arbalist", "Siege Master"]
        }
    },
    "Mage": {
        30: ["Sorcerer", "Warlock", "Necromancer", "Summoner"],
        60: {
            "Sorcerer": ["Archmage", "Elementalist"],
            "Warlock": ["Demonologist", "Voidwalker"],
            "Necromancer": ["Lich", "Deathcaller"],
            "Summoner": ["Grand Summoner", "Conjurer"]
        }
    },
    "Spellsword": {
        30: ["Eldritch Knight", "Rune Blade"],
        60: {
            "Eldritch Knight": ["Arcane Lord", "Mystic Vanguard"],
            "Rune Blade": ["Rune Master", "Spellweaver"]
        }
    },
    "Acolyte": {
        30: ["Cleric", "Bard", "Druid", "Monk"],
        60: {
            "Cleric": ["High Priest", "Bishop"],
            "Bard": ["Maestro", "Troubadour"],
            "Druid": ["Archdruid", "Hierophant"],
            "Monk": ["Grandmaster", "Zenith"]
        }
    },
    # NOTE: the profession lineages (Tactician/Scout/Blacksmith/Chef/Medic/
    # Quartermaster/Alchemist/Priest) are defined ONCE, in the BASE / SUPPORT
    # block below — those are the live support-revamp trees that
    # support_service mastery branches and PROFESSION_COMBAT_BRANCHES key off.
    # This block previously carried older single-branch duplicates of seven of
    # them; Python kept only the later definition, so the duplicates were dead
    # code and have been removed (their unique names — War Master, Trailblazer,
    # Void Walker, Head Chef, Culinary Master, Guild Treasurer, Trade Baron,
    # Master Alchemist — were never reachable in-game).
    "Farmer": {
        30: ["Master Farmer", "Beast Tamer"],
        60: {
            "Master Farmer": ["Harvest Lord", "Nature's Chosen"],
            "Beast Tamer": ["Apex Predator", "Wild Master"]
        }
    },
    "Merchant": {
        30: ["Trader", "Smuggler"],
        60: {
            "Trader": ["Guild Master", "Trade Prince"],
            "Smuggler": ["Black Market Baron", "Shadow Broker"]
        }
    },
    "Classless": {
        30: ["Adventurer", "Mercenary", "Hero"],
        60: {
            "Adventurer": ["Veteran"],
            "Mercenary": ["Bounty Hunter"],
            "Hero": ["Champion"]
        }
    },
    "Magic Engineer": {
        30: [], 60: {} # Pinnacle class
    },
    
    # BASE / SUPPORT
    "Blacksmith": {
        30: ["Weaponsmith", "Armorer", "Artificer"],
        60: {
            "Weaponsmith": ["Master Smith"],
            "Armorer": ["Forge Lord"],
            "Artificer": ["Runesmith"]
        }
    },
    "Alchemist": {
        30: ["Apothecary", "Transmuter", "Poisoner"],
        60: {
            "Apothecary": ["Grand Alchemist"],
            "Transmuter": ["Philosopher"],
            "Poisoner": ["Brewmaster"]
        }
    },
    "Chef": {
        30: ["Sous Chef", "Forager", "Butcher"],
        60: {
            "Sous Chef": ["Master Chef"],
            "Forager": ["Gourmet"],
            "Butcher": ["Iron Chef"]
        }
    },
    "Medic": {
        30: ["Surgeon", "Herbalist", "Field Medic"],
        60: {
            "Surgeon": ["Chief Medical Officer"],
            "Herbalist": ["Miracle Worker"],
            "Field Medic": ["Plague Doctor"]
        }
    },
    "Quartermaster": {
        30: ["Merchant", "Logistics Officer", "Scavenger"],
        60: {
            "Merchant": ["Tycoon"],
            "Logistics Officer": ["Guildmaster"],
            "Scavenger": ["Hoarder"]
        }
    },
    "Tactician": {
        30: ["Strategist", "Commander", "Advisor"],
        60: {
            "Strategist": ["Grand Strategist"],
            "Commander": ["General"],
            "Advisor": ["Warlord"]
        }
    },
    "Scout": {
        30: ["Pathfinder", "Tracker", "Spy"],
        60: {
            "Pathfinder": ["Ranger"],
            "Tracker": ["Infiltrator"],
            "Spy": ["Spymaster"]
        }
    },
    "Priest": {
        30: ["Confessor", "Oracle", "Chaplain"],
        60: {
            "Confessor": ["High Confessor"],
            "Oracle": ["Prophet"],
            "Chaplain": ["Saint"]
        }
    }
}

COMBAT_BASE_CLASSES = ["Warrior", "Spearman", "Thief", "Archer", "Mage", "Acolyte", "Magic Engineer", "Spellsword"]

# SUPPORT_BASE_CLASSES is the full "base/profession" gacha roll pool (unchanged —
# still rolled as a single "base" category, see assign_class). Within it,
# SUPPORT_COMBAT_CLASSES marks the subset that's actually combat-capable at
# the literal base name itself — everyone else (Chef/Blacksmith/Quartermaster/
# Priest/Alchemist/Merchant/Farmer) is a pure crafting/economy role until they
# evolve into a named combat form (e.g. Blacksmith -> Weaponsmith), same as
# how the other 5 already worked. Confirmed deliberately: Merchant/Farmer
# are NOT support-combat — more valuable staffed at base than fighting, and
# their evolutions still become real fighters exactly like Blacksmith's do.
SUPPORT_BASE_CLASSES = ["Chef", "Medic", "Scout", "Blacksmith", "Quartermaster", "Tactician", "Priest", "Alchemist", "Merchant", "Farmer"]
SUPPORT_COMBAT_CLASSES = ["Medic", "Scout", "Tactician"]
BASE_CLASSES = SUPPORT_BASE_CLASSES # Legacy naming convention

# Weights within combat class pool (per star)
COMBAT_WEIGHTS_BY_STAR = {
    1: {},
    2: {},
    3: {"Warrior": 20, "Spearman": 20, "Thief": 20, "Archer": 20, "Mage": 4, "Acolyte": 16, "Magic Engineer": 0, "Spellsword": 0},
    4: {"Warrior": 18, "Spearman": 18, "Thief": 18, "Archer": 18, "Mage": 8, "Acolyte": 18, "Magic Engineer": 1, "Spellsword": 4},
    5: {"Warrior": 15, "Spearman": 15, "Thief": 15, "Archer": 15, "Mage": 15, "Acolyte": 15, "Magic Engineer": 2, "Spellsword": 6},
    6: {"Warrior": 15, "Spearman": 15, "Thief": 15, "Archer": 15, "Mage": 20, "Acolyte": 15, "Magic Engineer": 3, "Spellsword": 8},
    7: {"Warrior": 12, "Spearman": 12, "Thief": 12, "Archer": 12, "Mage": 25, "Acolyte": 15, "Magic Engineer": 4, "Spellsword": 10},
}

CLASS_CATEGORY_RATES = {
    1: (0,  15, 85),
    2: (0,  20, 80),
    3: (55, 20, 25),
    4: (65, 28,  7),
    5: (72, 28,  0),
    6: (96,  4,  0),
    7: (100, 0,  0),
}

# Recursively get all classes in tree
def _get_all_evolutions():
    all_evos = set()
    for base, evos in CLASS_EVOLUTIONS.items():
        all_evos.add(base)
        for e in evos.get(30, []): all_evos.add(e)
        for tier60 in evos.get(60, {}).values():
            for e in tier60: all_evos.add(e)
    return list(all_evos)

ALL_CLASSES = _get_all_evolutions()

def get_class_evolution_options(hero_class: str, level: int) -> list[str]:
    """Returns available evolution options for a given class at a specific level."""
    for base_cls, evos in CLASS_EVOLUTIONS.items():
        if level >= 30 and hero_class == base_cls:
            return evos.get(30, [])
        if level >= 60:
            if hero_class in evos.get(60, {}):
                return evos[60][hero_class]
    return []

# ---------------------------------------------------------------------------
# Class assignment
# ---------------------------------------------------------------------------

def assign_class(birth_star: int) -> tuple[str, str]:
    combat_pct, base_pct, classless_pct = CLASS_CATEGORY_RATES[birth_star]

    roll = random.uniform(0, 100)
    if roll < combat_pct:
        category = "combat"
    elif roll < combat_pct + base_pct:
        category = "base"
    else:
        category = "classless"

    if category == "classless":
        actual_class = "Classless"
    elif category == "base":
        if birth_star == 6:
            # 6-star base classes are exclusively Blacksmith due to combat scaling
            actual_class = "Blacksmith"
        else:
            actual_class = random.choice(SUPPORT_BASE_CLASSES)
    else:
        # Weighted roll for combat classes
        pool = COMBAT_WEIGHTS_BY_STAR.get(birth_star, {})
        weights = {k: v for k, v in pool.items() if v > 0}
        if not weights:
            actual_class = "Classless"
        else:
            classes = list(weights.keys())
            wts = list(weights.values())
            actual_class = random.choices(classes, weights=wts, k=1)[0]
            
    if birth_star <= 2 and actual_class != "Classless":
        return ("Classless", actual_class)
    return (actual_class, None)

# Within the 7 pure-profession lineages (Chef/Blacksmith/Quartermaster/
# Priest/Alchemist/Merchant/Farmer — see SUPPORT_BASE_CLASSES minus
# SUPPORT_COMBAT_CLASSES), evolving no longer makes a class combat-capable
# by default. Confirmed deliberate: "a weaponsmith shouldn't be combat
# capable, just better at making weapons" — most evolutions in these
# lines (Weaponsmith, Trader, Master Chef, Apothecary, Logistics Officer,
# Confessor, etc.) are more valuable staffed at base and stay pure
# crafting/economy/faith roles forever. Only branches whose NAME itself
# reads as genuinely dangerous get carved out as fighters, and once a
# branch is carved out its further (tier-60) evolutions inherit that —
# a Poisoner becoming a Brewmaster doesn't retire from being dangerous.
# Blacksmith, Quartermaster, and Priest have no branch that clears that
# bar, so those three lineages never fight at any tier.
PROFESSION_COMBAT_BRANCHES = {
    "Butcher",                                          # Chef line
    "Poisoner", "Brewmaster",                           # Alchemist line
    "Smuggler", "Black Market Baron", "Shadow Broker",   # Merchant line
    "Beast Tamer", "Apex Predator", "Wild Master",       # Farmer line
}

_PROFESSION_LINEAGES = ["Chef", "Blacksmith", "Quartermaster", "Priest", "Alchemist", "Merchant", "Farmer"]
_PROFESSION_EVOLUTION_NAMES = None

def _build_profession_evolution_names() -> set:
    names = set()
    for base in _PROFESSION_LINEAGES:
        tiers = CLASS_EVOLUTIONS.get(base, {})
        names.update(tiers.get(30, []))
        for branch in tiers.get(60, {}).values():
            names.update(branch)
    return names

def is_combat_class(hero_class: str) -> bool:
    global _PROFESSION_EVOLUTION_NAMES
    non_combat_base = [c for c in SUPPORT_BASE_CLASSES if c not in SUPPORT_COMBAT_CLASSES]
    if hero_class in non_combat_base:
        return False
    if _PROFESSION_EVOLUTION_NAMES is None:
        _PROFESSION_EVOLUTION_NAMES = _build_profession_evolution_names()
    if hero_class in _PROFESSION_EVOLUTION_NAMES and hero_class not in PROFESSION_COMBAT_BRANCHES:
        return False
    return True

def is_base_class(hero_class: str) -> bool:
    return hero_class in SUPPORT_BASE_CLASSES

def can_pilot(hero_class: str) -> bool:
    return hero_class == "Magic Engineer"

# ---------------------------------------------------------------------------
# Weapon affinity — class-specific weapon types + Weapon Art
# ---------------------------------------------------------------------------
# Five weapon types for now (Bow added so Archer's line has something to
# hold, Dagger added per direct request so Thief's line isn't stuck with
# the heavier-feeling Sword). Each type grants a bonus "Art" skill (see
# skills_service.WEAPON_ART_SKILLS) ONLY while a hero has a matching-type
# weapon equipped — equip is a hard restriction: a class can only wear a
# *typed* weapon (weapon_type is not None) that's in its affinity list.
# Untyped legacy weapons (pre-dating this system) are grandfathered in —
# equippable by anyone, just never grant an Art.
WEAPON_TYPES = ["Sword", "Spear", "Tome", "Bow", "Dagger"]

# Keyed by BASE LINEAGE (same lineages skills_service.py builds kits for)
# — evolutions resolve back to their lineage's affinity the same way they
# resolve back to their lineage's skill kit. Classes/lineages absent here
# (Blacksmith, Quartermaster, Priest, Tactician, etc.) have no enforced
# restriction — equip is unrestricted for them since they were never
# given a defined weapon identity.
CLASS_WEAPON_AFFINITY = {
    "Warrior": ["Sword"],
    "Spearman": ["Spear"],
    "Thief": ["Dagger"],
    "Archer": ["Bow"],
    "Mage": ["Tome"],
    "Acolyte": ["Tome"],
    "Magic Engineer": ["Tome"],
    "Spellsword": ["Sword", "Tome"],
    "Medic": ["Tome"],
    "Scout": ["Dagger"],
    # Classless intentionally omitted — no weapon identity yet (they
    # haven't specialized), so they can equip any weapon type with no
    # restriction. Once they evolve at level 30, that class defines it.
    # Profession lineages only matter once a combat branch evolves in
    # (see PROFESSION_COMBAT_BRANCHES) — affinity still lives at the
    # lineage level so it resolves the same way skill kits do.
    "Merchant": ["Dagger"],   # Smuggler/Black Market Baron/Shadow Broker — concealed blade
    "Farmer": ["Spear"],      # Beast Tamer/Apex Predator/Wild Master — taming pole
    "Chef": ["Dagger"],       # Butcher — cleaver
    "Alchemist": ["Dagger"],  # Poisoner/Brewmaster — poisoned blade
}

# Shared by both weapon and armor affinity resolution — purely a name->base
# lineage lookup, nothing weapon-specific about it.
_CLASS_LINEAGE_MAP = None

def _build_class_lineage_map() -> dict:
    mapping = {}
    for base, tiers in CLASS_EVOLUTIONS.items():
        for name in tiers.get(30, []):
            mapping.setdefault(name, base)
        for branch in tiers.get(60, {}).values():
            for name in branch:
                mapping.setdefault(name, base)
    return mapping

def get_weapon_affinity(hero_class: str) -> list[str]:
    """Which WEAPON_TYPES this class can equip + draw an Art from. Empty
    list means no restriction is enforced (class has no defined weapon
    identity, e.g. a pure profession class or Tactician)."""
    global _CLASS_LINEAGE_MAP
    if hero_class in CLASS_WEAPON_AFFINITY:
        return CLASS_WEAPON_AFFINITY[hero_class]
    if _CLASS_LINEAGE_MAP is None:
        _CLASS_LINEAGE_MAP = _build_class_lineage_map()
    base = _CLASS_LINEAGE_MAP.get(hero_class)
    return CLASS_WEAPON_AFFINITY.get(base, [])

# ---------------------------------------------------------------------------
# Armor affinity — class-specific armor types
# ---------------------------------------------------------------------------
# Robe/Light/Medium/Heavy — same hard-restriction shape as weapons (a typed
# armor piece can only go on a matching-affinity class; untyped legacy gear
# is grandfathered in for anyone). No bonus Art for armor — just a real
# stat-flavor difference per type (see equipment_service._roll_equipment_stats)
# and distinct icons, which was the actual ask.
ARMOR_TYPES = ["Robe", "Light Armor", "Brigandine", "Heavy Armor"]

CLASS_ARMOR_AFFINITY = {
    "Warrior": ["Heavy Armor"],
    "Spearman": ["Heavy Armor"],
    "Thief": ["Light Armor"],
    "Archer": ["Light Armor"],
    "Scout": ["Light Armor"],
    "Mage": ["Robe"],
    "Acolyte": ["Robe"],
    "Magic Engineer": ["Robe"],
    "Medic": ["Robe"],
    "Spellsword": ["Brigandine"],
    "Classless": ["Brigandine"],
    "Merchant": ["Light Armor"],   # Smuggler line — needs to move quietly
    "Farmer": ["Brigandine"],    # Beast Tamer line — practical, not fragile
    "Chef": ["Brigandine"],      # Butcher line
    "Alchemist": ["Light Armor"],  # Poisoner/Brewmaster line
}

def get_armor_affinity(hero_class: str) -> list[str]:
    """Which ARMOR_TYPES this class can equip. Empty list means no
    restriction is enforced (no defined armor identity, e.g. Tactician)."""
    global _CLASS_LINEAGE_MAP
    if hero_class in CLASS_ARMOR_AFFINITY:
        return CLASS_ARMOR_AFFINITY[hero_class]
    if _CLASS_LINEAGE_MAP is None:
        _CLASS_LINEAGE_MAP = _build_class_lineage_map()
    base = _CLASS_LINEAGE_MAP.get(hero_class)
    return CLASS_ARMOR_AFFINITY.get(base, [])

# ---------------------------------------------------------------------------
# Combat stat modifiers by class
# ---------------------------------------------------------------------------
# Using a dict to cleanly apply stats. Supports flat boosts, multipliers, and flags.
# Modifiers compound (e.g. Knight is applied ON TOP of Warrior if we wanted, but we replace the class entirely, so stats should be absolute for the tier)

CLASS_MODIFIERS = {
    # Tier 1 Combat
    "Warrior": {"def_mult": 1.20, "hp_mult": 1.15},
    "Spearman": {"atk_mult": 1.15, "spd_mult": 1.10},
    "Thief": {"spd_mult": 1.30, "crit_add": 0.15, "dodge_add": 0.10},
    "Archer": {"atk_mult": 1.10, "is_ranged": True},
    "Spellsword": {"atk_mult": 1.10, "def_mult": 0.90, "is_aoe": True, "power_stat": "intelligence"},
    "Mage": {"atk_mult": 0.85, "is_aoe": True, "power_stat": "intelligence"},
    "Acolyte": {"hp_mult": 1.10, "is_healer": True, "power_stat": "intelligence"},
    "Magic Engineer": {"atk_mult": 0.90, "has_construct": True, "power_stat": "intelligence"},
    "Classless": {"atk_mult": 0.75, "def_mult": 0.75, "spd_mult": 0.90},

    # Tier 2 Combat (Lv 30) - Massive Boosts
    "Knight": {"def_mult": 1.60, "hp_mult": 1.40, "has_taunt": True},
    "Berserker": {"atk_mult": 1.50, "def_mult": 0.70, "hp_mult": 1.20, "lifesteal": 0.1},
    "Paladin": {"def_mult": 1.30, "hp_mult": 1.30, "is_healer": True},
    "Lancer": {"atk_mult": 1.30, "spd_mult": 1.20, "armor_pen": 0.5},
    "Halberdier": {"atk_mult": 1.40, "is_cleave": True},
    "Dragoon": {"atk_mult": 1.40, "spd_mult": 1.30, "dodge_add": 0.15},
    "Assassin": {"atk_mult": 1.50, "spd_mult": 1.50, "crit_add": 0.30},
    "Rogue": {"spd_mult": 1.40, "dodge_add": 0.25, "crit_add": 0.20},
    "Ninja": {"spd_mult": 1.60, "dodge_add": 0.20, "multi_hit": 2},
    "Sniper": {"atk_mult": 1.40, "is_ranged": True, "crit_add": 0.25},
    "Ranger": {"atk_mult": 1.20, "is_ranged": True, "has_pet": True},
    "Crossbowman": {"atk_mult": 1.50, "spd_mult": 0.90, "is_ranged": True},
    "Sorcerer": {"atk_mult": 1.20, "is_aoe": True, "power_stat": "intelligence"},
    "Warlock": {"atk_mult": 1.10, "is_aoe": True, "lifesteal": 0.3, "power_stat": "intelligence"},
    "Necromancer": {"atk_mult": 1.0, "is_aoe": True, "summons_undead": True, "power_stat": "intelligence"},
    "Summoner": {"atk_mult": 0.9, "summons_beast": True, "has_construct": True, "hp_mult": 1.5, "power_stat": "intelligence"},
    "Cleric": {"def_mult": 1.20, "is_healer": True, "strong_heal": True, "power_stat": "intelligence"},
    "Bard": {"spd_mult": 1.30, "team_buff": True},
    "Druid": {"hp_mult": 1.40, "is_healer": True, "power_stat": "intelligence"},
    "Monk": {"atk_mult": 1.30, "spd_mult": 1.30, "dodge_add": 0.15},
    
    # Support Deployed (Lv 1)
    "Tactician": {"team_atk_mult": 1.10},
    "Scout": {"team_spd_mult": 1.10},
    
    # Tier 2 Support Deployed (Lv 30)
    "Strategist": {"team_end_mult": 1.20},
    "Commander": {"team_atk_mult": 1.25},
    "Advisor": {"team_xp_mult": 1.20},
    "Pathfinder": {"trap_immune": True},
    "Tracker": {"rare_find_mult": 1.5},
    "Spy": {"floor_reveal": 3},
}

def apply_class_combat_modifiers(hero: dict) -> dict:
    h = hero.copy()
    cls = h.get("hero_class", "Classless")
    
    mods = CLASS_MODIFIERS.get(cls, {})
    
    h["strength"] = int(h["strength"] * mods.get("atk_mult", 1.0))
    h["intelligence"] = int(h["intelligence"] * mods.get("atk_mult", 1.0) if mods.get("power_stat") == "intelligence" else h["intelligence"])
    h["defense"] = int(h.get("defense", 5) * mods.get("def_mult", 1.0))
    h["endurance"] = int(h.get("endurance", h.get("defense", 5)) * mods.get("def_mult", 1.0))
    h["agility"] = int(h["agility"] * mods.get("spd_mult", 1.0))
    h["max_health"] = int(h["max_health"] * mods.get("hp_mult", 1.0))
    h["health"] = int(h["health"] * mods.get("hp_mult", 1.0))
    h["power_stat"] = mods.get("power_stat", "strength")

    h["crit_chance"] = h.get("crit_chance", 0.05) + mods.get("crit_add", 0.0)
    h["dodge_chance"] = h.get("dodge_chance", 0.0) + mods.get("dodge_add", 0.0)

    for flag in ["is_ranged", "is_aoe", "has_construct", "has_taunt", "is_healer", "strong_heal", "is_cleave", "summons_undead", "summons_beast", "team_buff"]:
        if mods.get(flag):
            h[flag] = True

    if "lifesteal" in mods: h["lifesteal"] = mods["lifesteal"]
    if "armor_pen" in mods: h["armor_pen"] = mods["armor_pen"]
    if "multi_hit" in mods: h["multi_hit"] = mods["multi_hit"]
    leader_mult = 1.5 if h.get("is_team_leader") else 1.0
    if "team_atk_mult" in mods: h["team_atk_mult"] = 1.0 + ((mods["team_atk_mult"] - 1.0) * leader_mult)
    if "team_end_mult" in mods: h["team_end_mult"] = 1.0 + ((mods["team_end_mult"] - 1.0) * leader_mult)
    if "team_spd_mult" in mods: h["team_spd_mult"] = 1.0 + ((mods["team_spd_mult"] - 1.0) * leader_mult)
    
    return h

# ---------------------------------------------------------------------------
# Base class effects
# ---------------------------------------------------------------------------

def get_base_class_rest_bonus(hero_class: str, hero_level: int) -> dict:
    scale = 1.0 + (hero_level * 0.02)
    
    bonuses = {
        "Chef":          {"morale_bonus": int(8 * scale),  "stress_reduction": int(5 * scale)},
        "Master Chef":   {"morale_bonus": int(15 * scale), "stress_reduction": int(10 * scale)},
        "Medic":         {"hp_restore_pct": min(0.30, 0.15 * scale), "trauma_reduction": int(3 * scale)},
        "Chief Medical Officer": {"hp_restore_pct": min(0.60, 0.30 * scale), "trauma_reduction": int(8 * scale)},
        "Priest":        {"morale_bonus": int(5 * scale),  "trauma_reduction": int(6 * scale)},
        "High Priest":   {"morale_bonus": int(10 * scale), "trauma_reduction": int(12 * scale)},
        "Blacksmith":    {"team_def_bonus": int(2 * scale)},
        "Forge Lord":    {"team_def_bonus": int(8 * scale)},
        "Quartermaster": {"gold_bonus_pct": min(0.25, 0.10 * scale)},
        "Tycoon":        {"gold_bonus_pct": min(0.60, 0.25 * scale)},
        "Alchemist":     {"material_bonus": int(1 * scale)},
        "Grand Alchemist":{"material_bonus": int(3 * scale)},
    }
    return bonuses.get(hero_class, {})

# ---------------------------------------------------------------------------
# Forge crafting
# ---------------------------------------------------------------------------
# Blacksmith is the only Forge specialist. Crafting quality is capped by
# your single BEST Blacksmith present (a pile of weak ones can't out-craft
# one great one) — but multiple Blacksmiths of that same evolution tier
# add a smaller bonus on top, since a crew of comparably-skilled smiths
# really does work better together than just one.
BLACKSMITH_LINE = ["Blacksmith", "Weaponsmith", "Armorer", "Artificer", "Master Smith", "Forge Lord", "Runesmith"]

# Evolution tier rank — higher tier smiths set a meaningfully higher
# quality ceiling, not just a flat bonus regardless of how evolved they are.
SMITH_TIER_RANK = {
    "Blacksmith": 1, "Weaponsmith": 1, "Armorer": 1, "Artificer": 1,
    "Master Smith": 2,
    "Forge Lord": 3, "Runesmith": 3,
}
# tier -> (apt_bonus, level_bonus) for the best smith present.
SMITH_TIER_BONUS = {1: (30, 5), 2: (60, 10), 3: (100, 18)}
# tier -> (apt_bonus, level_bonus) added per *additional* smith sharing
# that same tier — the peak is still set by the best smith's tier alone.
SMITH_TIER_TEAMWORK_BONUS = {1: (15, 2), 2: (25, 4), 3: (40, 6)}

def forge_smith_bonus(hero_classes: list[str]) -> tuple[int, int, str | None]:
    """Returns (apt_bonus, level_bonus, best_smith_class) for a Forge craft.
    None present -> (0, 0, None). The bonus is anchored to the single best
    (highest-tier) Blacksmith-line class present, plus a smaller bonus per
    additional smith of that exact same tier."""
    smith_classes = [c for c in hero_classes if c in BLACKSMITH_LINE]
    if not smith_classes:
        return (0, 0, None)
    best = max(smith_classes, key=lambda c: SMITH_TIER_RANK.get(c, 1))
    best_tier = SMITH_TIER_RANK.get(best, 1)
    apt, level = SMITH_TIER_BONUS[best_tier]
    # Remove exactly one occurrence of `best` (the best smith themself)
    # before counting same-tier teammates — otherwise two heroes sharing
    # the identical class name would wrongly cancel each other out.
    remaining = smith_classes.copy()
    remaining.remove(best)
    same_tier_extra = sum(1 for c in remaining if SMITH_TIER_RANK.get(c, 1) == best_tier)
    extra_apt, extra_level = SMITH_TIER_TEAMWORK_BONUS[best_tier]
    apt += extra_apt * same_tier_extra
    level += extra_level * same_tier_extra
    return (apt, level, best)

# ---------------------------------------------------------------------------
# Class display helpers
# ---------------------------------------------------------------------------

# Short 2-letter abbreviations for the card medallion — rendered with
# Georgia Bold so they're always crisp, unlike emoji which vary in metrics.
CLASS_ABBREVS = {
    "Warrior": "WR", "Knight": "KN", "Berserker": "BR", "Paladin": "PL",
    "Aegis": "AG", "Templar": "TM", "Bloodrager": "BL", "Juggernaut": "JG",
    "Crusader": "CR", "Arbiter": "AB", "Void Knight": "VK",
    "Spearman": "SP", "Lancer": "LC", "Halberdier": "HB", "Dragoon": "DG",
    "Thief": "TH", "Assassin": "AS", "Rogue": "RG", "Ninja": "NJ",
    "Archer": "AR", "Sniper": "SN", "Ranger": "RN", "Crossbowman": "XB",
    "Spellsword": "SS",
    "Mage": "MG", "Sorcerer": "SC", "Warlock": "WL", "Necromancer": "NC", "Summoner": "SM",
    "Acolyte": "AC", "Cleric": "CL", "Bard": "BD", "Druid": "DR", "Monk": "MK",
    "Magic Engineer": "ME",
    "Chef": "CF", "Medic": "MD", "Scout": "SK", "Blacksmith": "BS",
    "Quartermaster": "QM", "Tactician": "TC", "Priest": "PR", "Alchemist": "AL",
    "Farmer": "FM", "Merchant": "MC",
    "Classless": "CL",  # consistent with all other class abbreviations
}

# Keep emoji for UI display (heroes list, tooltips, etc.)
CLASS_ICONS = {
    "Warrior": "⚔️", "Knight": "🛡️", "Berserker": "🩸", "Paladin": "✨",
    "Spearman": "🔱", "Lancer": "🐎", "Halberdier": "🪓", "Dragoon": "🐉",
    "Thief": "🗡️", "Assassin": "☠️", "Rogue": "🥷", "Ninja": "💨",
    "Archer": "🏹", "Sniper": "🎯", "Ranger": "🐺", "Crossbowman": "⚙️",
    "Spellsword": "⚔️",
    "Mage": "🪄", "Sorcerer": "🔮", "Warlock": "👁️", "Necromancer": "💀", "Summoner": "🐉",
    "Acolyte": "✝️", "Cleric": "🩹", "Bard": "🎵", "Druid": "🌿", "Monk": "👊",
    "Magic Engineer": "🤖",
    "Chef": "🍳", "Medic": "🩺", "Scout": "🔭", "Blacksmith": "⚒️",
    "Quartermaster": "💰", "Tactician": "📜", "Priest": "⛪", "Alchemist": "🧪",
    "Classless": "✦"
}

def get_class_icon(hero_class: str) -> str:
    return CLASS_ICONS.get(hero_class, "💠")

def get_class_abbrev(hero_class: str) -> str:
    return CLASS_ABBREVS.get(hero_class, hero_class[:2].upper() if hero_class else "?")

CLASS_DESCRIPTIONS = { k: 'A powerful hero.' for k in ALL_CLASSES }


def get_power_stat(hero_class: str) -> str:
    """Which raw stat (strength/intelligence) actually drives this class's
    attack damage — most classes are strength, casters/healers (Acolyte,
    Mage, Cleric, etc.) are intelligence. Exposed to the frontend so a
    hero's stat card can flag which number actually matters for their
    damage; otherwise a high-STR Acolyte looks like it should hit hard and
    doesn't, with nothing on the card explaining why (confirmed real player
    confusion: a 63 STR Acolyte doing the same damage as a 12 STR ally,
    because Acolyte's real power stat is Intelligence, not Strength)."""
    return CLASS_MODIFIERS.get(hero_class, {}).get("power_stat", "strength")
