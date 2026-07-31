"""Floor environments — what the room itself does to a fight.

Two layers, both keyed off the floor number and NOTHING else:

  * a zone CONDITION, one per band, always present. Floors 61-70 are
    Leviathan's Graveyard, so they are flooded, and being flooded means
    something mechanical rather than just being a word in the flavour text.
  * an optional escalating HAZARD on some floors, which gets worse every
    round the fight drags on — the same shape as the Blitz stacking already
    in combat_service, pointed at the room instead of the enemies.

SEEDED, DELIBERATELY. Everything here is derived from floor_number through a
fixed seed, exactly like enemy composition is (_primary_etype_for_floor). The
game's scouting design rests on a floor being the SAME floor every time you
enter it — send fodder in to learn what's there, then prepare. An environment
that rerolled per attempt would quietly break that promise, so it doesn't.

Conditions are intentionally double-edged rather than pure penalties, and they
apply to enemies as well. A flooded floor slows everyone, including the things
that live there; a lightless one blunts crits but makes everyone harder to hit.
The decision they create is "which team suits this room", not "how much damage
does the room do to me".
"""

import random

# ── zone conditions, one per band (keys match ENEMY_TIER_UNLOCK_FLOOR) ──────
#
# Effects are multipliers/deltas applied once, at combat start:
#   agi_mult / str_mult / int_mult   stat scaling, heroes and enemies alike
#   crit_delta / dodge_delta         flat additions, clamped here
#
# Deliberately limited to levers apply_condition_to_units actually applies.
# Healing multipliers, DOT duration and AoE target counts would all read well
# in this table and would all be fiction until something hooks them — an
# effect listed here has to DO something.
ZONE_CONDITIONS = {
    "beginner": None,          # the first floors stay clean — learn the game first
    "intermediate": {
        "key": "DUSTFALL", "name": "Dustfall",
        "blurb": "Grit hangs in the air. Eyes water; strikes go wide.",
        "effects": {"crit_delta": -0.03},
    },
    "veteran": {
        "key": "CRAMPED", "name": "Cramped Halls",
        "blurb": "The walls press in. There is no room to swing wide.",
        "effects": {"dodge_delta": -0.06, "agi_mult": 0.95},
    },
    "advanced": {
        "key": "LIGHTLESS", "name": "Lightless",
        "blurb": "No torch holds here. You fight by sound and memory.",
        "effects": {"crit_delta": -0.05, "dodge_delta": 0.03},
    },
    "mighty": {
        "key": "SCORCHED", "name": "Scorched",
        "blurb": "The stone is still hot. Fire catches and refuses to die.",
        "effects": {"str_mult": 1.10, "dodge_delta": -0.03},
    },
    "ascendant": {
        "key": "HALLOWED", "name": "Hallowed Ground",
        "blurb": "Something old and kind died here. Its mercy lingers.",
        "effects": {"int_mult": 1.12, "crit_delta": 0.02},
    },
    "mythic": {
        "key": "FLOODED", "name": "Flooded",
        "blurb": "Black water to the waist. Every step is a decision.",
        "effects": {"agi_mult": 0.80, "dodge_delta": -0.05},
    },
    "apex": {
        "key": "THIN_AIR", "name": "Thin Air",
        "blurb": "The height tells. Lungs burn before arms do.",
        "effects": {"agi_mult": 0.90, "str_mult": 0.95},
    },
    "dread": {
        "key": "WITHERING", "name": "Withering",
        "blurb": "The air pulls at wounds. Nothing closes here.",
        "effects": {"str_mult": 0.92, "int_mult": 0.92, "crit_delta": 0.04},
    },
    "ancient": {
        "key": "UNRAVELING", "name": "Unraveling",
        "blurb": "Cause and effect come loose. Blows land before they are thrown.",
        "effects": {"crit_delta": 0.06, "dodge_delta": 0.06},
    },
}

# ── escalating hazards ──────────────────────────────────────────────────────
#
# Per-round, compounding, and only on some floors. They exist to argue with
# the 30-round limit: a team that can't close is punished for it by the room
# rather than by a timer alone.
HAZARDS = {
    "RISING_TIDE": {
        "name": "Rising Tide",
        "blurb": "The water is coming in. It does not stop.",
        "per_round_agi_mult": 0.97,
        "damage_pct_per_round": 0.008,   # of max health, from round `starts_round`
        "starts_round": 4,
    },
    "SPREADING_FIRE": {
        "name": "Spreading Fire",
        "blurb": "It caught in the rafters two rounds ago.",
        "per_round_agi_mult": 1.0,
        "damage_pct_per_round": 0.015,
        "starts_round": 5,
    },
    "COLLAPSING": {
        "name": "Collapsing",
        "blurb": "The ceiling is coming down in pieces.",
        "per_round_agi_mult": 0.98,
        "damage_pct_per_round": 0.010,
        "starts_round": 3,
    },
}

# Which bands can roll which hazard — a flooded graveyard floods further, a
# scorched one burns. Bands absent from this map never roll a hazard at all.
BAND_HAZARDS = {
    "mighty": ["SPREADING_FIRE"],
    "ascendant": ["COLLAPSING"],
    "mythic": ["RISING_TIDE"],
    "apex": ["COLLAPSING"],
    "dread": ["SPREADING_FIRE", "COLLAPSING"],
    "ancient": ["COLLAPSING", "RISING_TIDE"],
}
HAZARD_CHANCE = 0.30

# Bumping this reshuffles which floors carry hazards. It is a WORLD CHANGE,
# not a tuning knob: every floor a player has already scouted would report
# something different afterwards.
_ENV_SEED_SALT = 20260730


def get_floor_environment(floor_number: int, band: str) -> dict:
    """The condition and hazard for a floor. Same floor, same answer, forever."""
    condition = ZONE_CONDITIONS.get(band)
    hazard_key = None
    pool = BAND_HAZARDS.get(band)
    if pool:
        rng = random.Random(_ENV_SEED_SALT + floor_number * 7919)
        if rng.random() < HAZARD_CHANCE:
            hazard_key = pool[rng.randrange(len(pool))]
    return {
        "condition": condition,
        "hazard_key": hazard_key,
        "hazard": HAZARDS.get(hazard_key) if hazard_key else None,
    }


def effect(env: dict, name: str, default):
    """Read one effect out of an environment, defaulting when the band has no
    condition at all (the beginner floors)."""
    cond = (env or {}).get("condition")
    if not cond:
        return default
    return cond.get("effects", {}).get(name, default)


def apply_condition_to_units(env: dict, units: list, log: list) -> None:
    """Fold a zone condition into every combatant, once, before round 1.

    Applied to enemies too. The room doesn't care who you are, and a condition
    that only hurt the player would be a difficulty slider wearing a costume.
    """
    cond = (env or {}).get("condition")
    if not cond:
        return
    fx = cond.get("effects", {})
    agi_m = fx.get("agi_mult", 1.0)
    str_m = fx.get("str_mult", 1.0)
    int_m = fx.get("int_mult", 1.0)
    crit_d = fx.get("crit_delta", 0.0)
    dodge_d = fx.get("dodge_delta", 0.0)

    for u in units:
        if agi_m != 1.0:
            u.agility = max(1, int(u.agility * agi_m))
        if str_m != 1.0:
            u.strength = max(1, int(u.strength * str_m))
        if int_m != 1.0:
            u.intelligence = max(1, int(u.intelligence * int_m))
        if crit_d:
            u.crit_chance = max(0.0, min(1.0, u.crit_chance + crit_d))
        if dodge_d:
            u.dodge_chance = max(0.0, min(0.9, u.dodge_chance + dodge_d))

    log.append(f"  ◆ {cond['name']}: {cond['blurb']}")


def tick_hazard(env: dict, round_num: int, units: list, log: list) -> None:
    """One round of an escalating hazard. Mirrors the Blitz stacking pattern:
    compounding, announced once when it begins, and quiet thereafter so it
    doesn't drown the combat log."""
    hz = (env or {}).get("hazard")
    if not hz or round_num < hz["starts_round"]:
        return
    if round_num == hz["starts_round"]:
        log.append(f"  ◆ {hz['name']}: {hz['blurb']}")

    agi_m = hz.get("per_round_agi_mult", 1.0)
    dmg_pct = hz.get("damage_pct_per_round", 0.0)
    rounds_in = round_num - hz["starts_round"] + 1

    for u in units:
        if not u.alive:
            continue
        if agi_m != 1.0:
            u.agility = max(1, int(u.agility * agi_m))
        if dmg_pct:
            # Scales with how long the fight has run, so stalling gets worse
            # rather than staying survivable forever.
            dmg = max(1, int(u.max_health * dmg_pct * rounds_in))
            u.health -= dmg
            if u.health <= 0:
                u.health = 0
                u.alive = False
                log.append(f"  ✦ {u.log_name} is lost to the {hz['name'].lower()}.")
