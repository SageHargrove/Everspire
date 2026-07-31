"""
Combat Service — Deterministic simulation with class effects, level scaling,
skills, fear mechanics, legacy bonuses, and bond effects.
"""
import random
import json
from dataclasses import dataclass, field
from services.class_service import apply_class_combat_modifiers
from services.level_service import apply_level_to_stats, talent_score, get_hero_star, max_skill_slots

@dataclass
class CombatUnit:
    id: int
    name: str
    health: int
    max_health: int
    strength: int
    intelligence: int
    agility: int
    morale: int
    stress: int
    defense: int = 5  # legacy mirror of endurance, kept for any stale readers
    endurance: int = 5  # replaces defense as the real mitigation stat — also drove this unit's max_health upstream
    willpower: int = 6  # fear/panic resistance, see _panic_check
    luck: int = 5  # combat/exploration drop-rate bonus, applied at the team-average level, not per-unit
    power_stat: str = "strength"  # which stat drives this unit's attack damage
    dmg_reduction_pct: float = 0.0  # flat % mitigation from equipped gear, applied after Defense
    physical_resist_pct: float = 0.0  # extra mitigation vs. strength-basis hits only — Twins miniboss
    magic_resist_pct: float = 0.0     # extra mitigation vs. intelligence-basis hits only — Twins miniboss
    trauma: int = 0
    hero_class: str = "Classless"
    is_hero: bool = True
    alive: bool = True
    is_ranged: bool = False
    is_aoe: bool = False
    has_construct: bool = False
    construct_active: bool = False
    crit_chance: float = 0.05
    dodge_chance: float = 0.0
    kills: int = 0
    fear_immune: bool = False
    fear_stunned: bool = False
    death_save: int = 0
    armor_pen: float = 0.0
    skills: list = field(default_factory=list)
    portrait_path: str = ""
    abilities: list = field(default_factory=list)
    used_abilities: set = field(default_factory=set)
    phases: list = field(default_factory=list)   # boss phase triggers: [{"threshold": 0.66, "kind": "summon"}, ...]
    phases_fired: set = field(default_factory=set)
    talent: float = 0.5
    regen_pct: float = 0.0
    hero_star: int = 1
    level: int = 1
    battle_tendency: str = "Stoic"
    ego_type: str = ""         # Aggressive/Cautious/Tactical/Leader — see ego_service
    ego_patience: int = 100    # 0 = they rebuild the team themselves; low = they resent this lineup
    is_team_leader: bool = False
    team_position: int = 0     # the hero's slot in the team formation (0 = first)
    isolated_rounds: int = 0   # Reckless panic response — exposed, takes bonus damage, preferred enemy target
    bracing_rounds: int = 0    # Calculating panic response — forgoes their strength to brace defensively
    spawn_template: str = ""  # name of the weak add this unit's "summon_add" ability spawns, if any
    summons_used: int = 0     # caps "summon_add" so a miniboss/boss can't stall a fight forever
    used_consumable: bool = False  # caps a hero to one sip per fight
    equipped_consumable: str = None  # item_name of the Potion/Scroll/Bandage this hero specifically carries, if any
    status_effects: list = field(default_factory=list)  # [{"type": "bleed"|"poison"|"stun"|"freeze"|"burn"|"taunting"|"dmg_shield", "rounds": int, "magnitude": float, "source_id": int}]
    max_mana: int = 0
    mana: int = 0
    mana_regen_per_turn: int = 0  # flat passive tick, applied every round regardless of whether this unit acts
    skill_cooldowns: dict = field(default_factory=dict)  # {skill_id: rounds_remaining}
    is_npc: bool = False  # escort-floor protect target — never acts, excluded from win/reward bookkeeping
    is_runner: bool = False  # retrieval-floor objective worker — spends every turn channeling, never attacks
    poison_on_hit: dict = None  # {"pct": float, "duration": int} — derived from a passive skill like Poison Blade
    triggers: list = field(default_factory=list)  # passive conditional triggers, see skill_engine (on_hit_taken/on_dodge/on_kill/on_ally_death/on_low_hp)
    low_hp_fired: bool = False  # one-shot latch for an on_low_hp trigger

    def __post_init__(self):
        self.log_name = self.name if self.is_hero else f"[{self.name}]"
        if self.has_construct:
            self.construct_active = True

# name, hp_m, def_m, spd_m, archetype, tier — shared with services/portrait_cache.py
# so the enemy portrait library is pre-generated for exactly these types.
# "archetype" (swarm/pack/normal/elite) drives count/difficulty math in
# _build_enemy_group; "tier" is a separate floor-gate (see ENEMY_TIER_FLOORS
# below) so a floor-2 fight can't roll something named like an end-game
# threat — the original 17 monster types (all undead/horror-flavored) read
# fine as "advanced"/"legendary" content but were previously available from
# floor 1, which is why early fights felt over-tuned in theme even when the
# raw stats were scaled down to match.
ENEMY_TYPES = [
    # --- beginner (floor 1+) ---
    ("Giant Spider", 0.8, 0.8, 1.6, "swarm", "beginner"),
    ("Goblin", 0.8, 0.7, 1.1, "normal", "beginner"),
    ("Bandit", 0.9, 0.8, 1.2, "normal", "beginner"),
    ("Wolf", 0.9, 0.7, 1.5, "pack", "beginner"),
    ("Giant Rat", 0.7, 0.6, 1.4, "swarm", "beginner"),  # variety add 2026-07-10
    # Elite variants of the floor 1-10 family (Goblin/Spider/Wolf) —
    # same species, better stats, one extra ability via
    # ENEMY_ABILITY_OVERRIDES below. See backend/services/enemy_families.py
    # for the matching miniboss/boss tier for this floor range.
    ("Goblin Warrior", 1.2, 1.1, 1.0, "elite", "beginner"),
    ("Goblin Shaman", 1.0, 0.8, 1.0, "elite", "beginner"),
    ("Spider Queen", 1.1, 0.8, 1.7, "elite", "beginner"),
    # --- intermediate (floor 15+) — checklist family is "Kobolds, Skeletons,
    # Orcs, Giant Spiders" (PLAN_floor_workshop_enemies.md); Dire Wolf/Harpy
    # predate that checklist and stay as bonus extras, not removed ---
    ("Orc", 1.1, 1.0, 0.9, "normal", "intermediate"),
    ("Harpy", 0.8, 0.6, 1.8, "pack", "intermediate"),
    ("Vile Corvid", 0.9, 0.6, 1.6, "pack", "intermediate"),  # ref add 2026-07-10
    ("Kobold", 0.7, 0.6, 1.3, "swarm", "intermediate"),
    ("Skeleton", 0.9, 0.9, 1.0, "normal", "intermediate"),
    ("Venomous Spider", 1.0, 0.7, 1.2, "pack", "intermediate"),
    ("Ogre", 1.6, 1.3, 0.6, "elite", "intermediate"),
    ("Troll", 1.7, 1.0, 0.6, "elite", "intermediate"),
    # --- veteran (floor 21+) — checklist: "Hobgoblins, Ghouls, Harpies,
    # Lizardmen" (Harpies already covered by the persisting intermediate
    # entry above) ---
    ("Hobgoblin", 1.0, 0.9, 1.0, "normal", "veteran"),
    ("Lizardman", 0.9, 0.8, 1.3, "normal", "veteran"),
    ("Feral Ghoul", 1.0, 0.8, 1.1, "normal", "veteran"),
    ("Gnoll Marauder", 1.1, 0.9, 1.1, "normal", "veteran"),  # variety add 2026-07-10
    ("Crawling Hand", 0.6, 0.5, 1.5, "swarm", "veteran"),    # variety add 2026-07-10
    ("Hobgoblin Berserker", 1.3, 1.0, 1.1, "elite", "veteran"),
    ("Lizardman Stalker", 1.1, 0.9, 1.5, "elite", "veteran"),
    # --- advanced (floor 31+) — checklist: "Ogres, Trolls, Gargoyles,
    # Wraiths" (Ogres/Trolls already covered by the persisting intermediate
    # elites above) ---
    ("Grave Scarab", 1.0, 1.0, 1.6, "swarm", "advanced"),
    ("Rotting Ghoul", 1.1, 0.9, 1.2, "pack", "advanced"),
    ("Bone Warden", 1.0, 1.3, 0.8, "normal", "advanced"),
    ("Cave Shrieker", 1.1, 1.4, 0.9, "normal", "advanced"),  # was Gargoyle (concept dead, Liam-approved swap 07-14)
    ("Wraith", 0.9, 0.7, 1.3, "normal", "advanced"),
    ("Tomb Jackal Warden", 1.2, 1.1, 1.4, "elite", "advanced"),  # was Scarab Swarmlord
    ("Plague Harbinger", 1.3, 1.0, 1.0, "elite", "advanced"),
    # --- mighty (floor 41+) — checklist: "Minotaurs, Manticores, Wyverns,
    # Elementals" ---
    ("Minotaur", 1.4, 1.2, 0.7, "normal", "mighty"),
    ("Wyvern", 1.1, 0.8, 1.6, "normal", "mighty"),
    ("Manticore", 1.3, 1.0, 1.2, "normal", "mighty"),
    ("Elemental", 1.2, 1.3, 0.8, "normal", "mighty"),
    ("Nemean Lion", 1.2, 1.0, 1.1, "normal", "mighty"),  # was Chimera (concept dead after ~10 fails); relocated from mythic (sea re-theme)
    ("Griffon", 1.2, 0.9, 1.4, "normal", "mighty"),         # ref add 2026-07-10
    ("Dire Sabertooth", 1.3, 0.8, 1.3, "normal", "mighty"), # ref add 2026-07-10
    ("Dryad", 1.0, 1.7, 0.4, "normal", "mighty"),    # was Elder Treant (concept dead); ref add 2026-07-10
    ("Minotaur Juggernaut", 1.7, 1.4, 0.6, "elite", "mighty"),
    ("Phoenix", 1.4, 0.9, 1.3, "elite", "mighty"),          # ref add 2026-07-10 (rebirth = self_regen)
    # Wyvern Stormrider CUT 2026-07-17 (Liam): never rendered acceptably
    # (11 takes). Revisit post-ToE_Monsters_v2.
    # --- ascendant (floor 51+) — checklist: "Vampire Spawn, Chimeras,
    # Golems, Naga" (Golems covered by Stone Sentinel/Lesser Golem here;
    # Chimera/Naga land in mythic below since the checklist's 51-70 range
    # spans both this tier and the next) ---
    ("Crypt Warden", 1.3, 1.6, 0.5, "normal", "ascendant"),   # was Stone Sentinel
    ("Animated Armor", 1.1, 1.3, 0.5, "normal", "ascendant"), # was Lesser Golem
    ("Vampire Spawn", 1.2, 0.9, 1.3, "normal", "ascendant"),
    ("Blood Thrall", 1.0, 0.9, 1.1, "normal", "ascendant"),      # variety add 2026-07-10
    ("Obsidian Tortoise", 0.8, 1.7, 0.5, "normal", "ascendant"), # variety add 2026-07-10
    ("Cinder Ogre", 1.3, 1.4, 0.6, "normal", "ascendant"),    # was Magma Colossus; ref add 2026-07-10
    ("Iron Juggernaut", 1.5, 1.8, 0.5, "elite", "ascendant"),  # was Stone Golem
    ("Dread Brute", 1.8, 1.2, 0.7, "elite", "ascendant"),
    ("Obsidian Behemoth", 2.0, 1.6, 0.4, "elite", "ascendant"),
    ("Primordial Vampire", 1.5, 1.0, 1.5, "elite", "ascendant"),
    ("Frost Wight", 1.4, 1.1, 0.9, "elite", "ascendant"),  # relocated from mythic (sea re-theme)
    # --- mythic (floor 61+) — LEVIATHAN'S GRAVEYARD (sea-themed): a pitch-black
    # ocean floor of glowing leviathan bones and shipwrecks. The old mythic
    # roster (Chimera/Naga/Abyssal Lurker/Frost Wight/Shrouded Reaper) was
    # relocated to adjacent bands for variety (see mighty/ascendant/apex/dread).
    # See docs/leviathan-graveyard-design.md. ---
    ("Drowned Deckhand", 1.0, 1.0, 1.0, "normal", "mythic"),
    ("Bone-Crab Scavenger", 0.9, 1.7, 0.5, "normal", "mythic"),
    ("Coral-Grown Husk", 0.8, 1.8, 0.5, "normal", "mythic"),
    ("Abyssal Lamprey", 1.4, 0.6, 1.7, "pack", "mythic"),
    ("Marrow-Worm", 0.9, 0.8, 1.6, "swarm", "mythic"),
    ("Drowned Shade", 1.1, 0.6, 1.5, "pack", "mythic"),  # was Sunken Wisp
    ("Abyssal Serpent", 1.1, 0.9, 1.3, "normal", "mythic"),  # ref add 2026-07-10 (giant_serpent)
    ("Galleon Captain", 1.1, 1.4, 0.8, "elite", "mythic"),
    ("Trench Stalker", 1.6, 0.8, 1.9, "elite", "mythic"),
    ("Bone-Grafted Goliath", 1.7, 1.4, 0.7, "elite", "mythic"),
    # --- apex (floor 71+) — checklist: "Hydras, Giants, Death Knights,
    # Demon Lords" (Demon Lords land in dread below, same 71-90 split) ---
    ("Death Knight", 1.3, 1.2, 0.9, "normal", "apex"),
    ("Giant", 1.6, 1.1, 0.6, "normal", "apex"),
    # Hydra + Hydra Spawn CUT 2026-07-17 (Liam): the multi-head curse never
    # broke (~14 takes). Revisit the family post-ToE_Monsters_v2.
    ("Naga", 1.1, 0.9, 1.2, "normal", "apex"),  # relocated from mythic (sea re-theme)
    ("Dragonkin Warrior", 1.4, 1.1, 1.0, "normal", "apex"),  # ref add 2026-07-10 (humanoid_dragon)
    ("Black Knight Commander", 1.6, 1.4, 1.0, "elite", "apex"),
    ("Abyssal Lurker", 1.3, 0.9, 1.8, "elite", "apex"),  # relocated from mythic (sea re-theme)
    # --- dread (floor 81+) — Demon Lords half of the 71-90 checklist range ---
    ("Demon", 1.3, 1.0, 1.2, "normal", "dread"),
    ("Imp", 0.8, 0.6, 1.8, "pack", "dread"),
    ("Hellhound", 1.2, 0.8, 1.5, "pack", "dread"),    # variety add 2026-07-10
    ("Cambion", 1.2, 0.9, 1.1, "normal", "dread"),    # variety add 2026-07-10
    ("Succubus", 1.0, 0.7, 1.4, "normal", "dread"),   # variety add 2026-07-10
    ("Carapace Fiend", 1.2, 1.3, 0.9, "normal", "dread"),  # ref add 2026-07-10 (carapace_demon)
    ("Void Horror", 1.3, 1.1, 1.1, "elite", "dread"),      # ref add 2026-07-10 (eldritch_horror)
    ("Demon Lord", 1.7, 1.2, 1.1, "elite", "dread"),
    ("Pit Fiend", 1.7, 1.3, 1.0, "elite", "dread"),
    ("Wraith Sovereign", 1.4, 0.9, 1.5, "elite", "dread"),
    ("Shrouded Reaper", 1.3, 1.0, 1.3, "elite", "dread"),  # relocated from mythic (sea re-theme)
    # --- ancient (floor 91+) — checklist: "Dragons, Liches, Archdemons,
    # Ancient Guardians" ---
    ("Lich Acolyte", 1.2, 0.9, 1.0, "normal", "ancient"),
    ("Young Dragon", 1.6, 1.2, 1.0, "normal", "ancient"),
    ("Archdemon", 1.5, 1.2, 1.0, "normal", "ancient"),
    ("Ancient Guardian", 1.4, 1.6, 0.6, "normal", "ancient"),
    ("Drake", 1.4, 1.0, 1.3, "normal", "ancient"),           # ref add 2026-07-10 (drake)
    ("Ancient Revenant", 1.3, 1.4, 0.8, "normal", "ancient"), # variety add 2026-07-10
    ("Adult Dragon", 2.0, 1.4, 1.2, "elite", "ancient"),
    ("Dracolich", 1.8, 1.3, 0.9, "elite", "ancient"),
    ("Archdemon Enforcer", 1.8, 1.5, 1.0, "elite", "ancient"),
]

ENEMY_TIER_UNLOCK_FLOOR = {
    "beginner": 1, "intermediate": 15, "veteran": 21, "advanced": 31,
    "mighty": 41, "ascendant": 51, "mythic": 61, "apex": 71, "dread": 81, "ancient": 91,
}

# Purely organizational — which "waveN" review subfolder each named enemy's
# portrait lives in under enemies/<tier>/waveN/ (see _enemy_portrait_path and
# portrait_cache.py's generation functions, both of which consult this so a
# deleted portrait regenerates back into the same wave folder instead of the
# flat tier root). Has no effect on which floors an enemy actually spawns on
# — that's still ENEMY_TIER_UNLOCK_FLOOR — this just keeps the art library
# reviewable in the same batches you're already going through it in.
ENEMY_WAVE = {
    "Goblin": 1, "Giant Spider": 1, "Wolf": 1, "Giant Rat": 1,
    "Goblin Warrior": 1, "Goblin Shaman": 1, "Spider Queen": 1,
    "Bandit": 2, "Harpy": 2, "Orc": 2, "Ogre": 2, "Troll": 2,
    "Kobold": 2, "Skeleton": 2, "Venomous Spider": 2, "Vile Corvid": 2,
    "Hobgoblin": 3, "Lizardman": 3, "Feral Ghoul": 3, "Hobgoblin Berserker": 3, "Lizardman Stalker": 3, "Gnoll Marauder": 3, "Crawling Hand": 3,
    "Grave Scarab": 4, "Rotting Ghoul": 4, "Bone Warden": 4, "Cave Shrieker": 4, "Wraith": 4, "Tomb Jackal Warden": 4, "Plague Harbinger": 4,
    "Minotaur": 5, "Wyvern": 5, "Manticore": 5, "Elemental": 5, "Minotaur Juggernaut": 5, "Nemean Lion": 5, "Griffon": 5, "Dire Sabertooth": 5, "Dryad": 5, "Phoenix": 5,
    "Crypt Warden": 6, "Animated Armor": 6, "Vampire Spawn": 6, "Iron Juggernaut": 6, "Obsidian Behemoth": 6, "Dread Brute": 6, "Primordial Vampire": 6, "Frost Wight": 6, "Blood Thrall": 6, "Obsidian Tortoise": 6, "Cinder Ogre": 6,
    "Abyssal Serpent": 7,
    # wave 7 = Leviathan's Graveyard (sea band, floors 61-70)
    "Drowned Deckhand": 7, "Bone-Crab Scavenger": 7, "Coral-Grown Husk": 7, "Abyssal Lamprey": 7, "Marrow-Worm": 7, "Drowned Shade": 7, "Galleon Captain": 7, "Trench Stalker": 7, "Bone-Grafted Goliath": 7,
    "Death Knight": 8, "Giant": 8, "Black Knight Commander": 8, "Naga": 8, "Abyssal Lurker": 8, "Dragonkin Warrior": 8,
    "Demon": 9, "Imp": 9, "Demon Lord": 9, "Pit Fiend": 9, "Wraith Sovereign": 9, "Shrouded Reaper": 9, "Hellhound": 9, "Cambion": 9, "Succubus": 9, "Carapace Fiend": 9, "Void Horror": 9,
    "Lich Acolyte": 10, "Young Dragon": 10, "Adult Dragon": 10, "Archdemon": 10, "Ancient Guardian": 10, "Dracolich": 10, "Archdemon Enforcer": 10, "Drake": 10, "Ancient Revenant": 10,
}

# Per-name ability overrides — lets a specific elite/miniboss/boss entry use
# a different signature ability (or combo) than the blanket "elite archetype
# always gets cleave" default in _build_enemy_group. This is the "reusable
# mechanic library" the enemy-roster plan asked for: summon_add, team_buff_aura
# and self_regen are all generic, family-agnostic mechanics any future named
# enemy can be wired into just by adding an entry here (or to a family's
# elites list in enemy_families.py) — no new per-monster code needed.
ENEMY_ABILITY_OVERRIDES = {
    "Goblin Warrior": ["cleave"],
    "Goblin Shaman": ["team_buff_aura"],
    "Spider Queen": ["summon_add"],
    "Hobgoblin Berserker": ["enrage"],
    "Lizardman Stalker": ["self_regen"],
    "Tomb Jackal Warden": ["summon_add"],
    "Plague Harbinger": ["team_buff_aura"],
    "Minotaur Juggernaut": ["enrage"],
    "Pit Fiend": ["enrage"],
    "Demon Lord": ["crushing_blow"],
    "Wraith Sovereign": ["team_buff_aura"],
    "Primordial Vampire": ["self_regen"],
    "Adult Dragon": ["crushing_blow"],
    "Dracolich": ["self_regen"],
    "Archdemon Enforcer": ["crushing_blow"],
    # Leviathan's Graveyard (sea band)
    "Galleon Captain": ["team_buff_aura"],       # buffs the Drowned Deckhands
    "Bone-Grafted Goliath": ["crushing_blow"],
    "Bone-Crab Scavenger": ["shell_armor"],      # armored until its shell cracks
    "Phoenix": ["self_regen"],                   # rebirth — regenerates each round
}

# Which weak swarm-type a "summon_add" user calls in as reinforcements.
ENEMY_SPAWN_TEMPLATE = {
    "Spider Queen": "Giant Spider",
    "Tomb Jackal Warden": "Grave Scarab",
    "Thalassor, the Undead Leviathan": "Marrow-Worm",
    "Captain Iron-Lung": "Drowned Deckhand",
}

SELF_REGEN_PCT = 0.06  # per-round Health regen granted by the "self_regen" ability
# "shell_armor": heavily mitigates basic-attack damage until the shell cracks
# after this many hits, then the unit takes normal damage (Bone-Crab Scavenger,
# The Calcified Horror). Reusable by any future armored/carapace enemy.
SHELL_ARMOR_REDUCTION = 0.7   # damage reduced by 70% while the shell holds
SHELL_ARMOR_BREAK_HITS = 4    # basic-attack hits the shell absorbs before cracking
REVIVE_ALLY_HP_PCT = 0.4  # Health a "revive_ally" user brings a fallen ally back at, once per battle

# Potions/Scrolls are a shared base-wide "backpack," not a per-hero item
# slot — a hero who drops below this much Health drinks the best available
# healing-capable one at their own discretion, once per hero per fight, so
# one bad floor doesn't drain the whole shared stock on a single hero.
CONSUMABLE_LOW_HP_THRESHOLD = 0.35
CONSUMABLE_LOW_MANA_THRESHOLD = 0.20

def _current_tier_for_floor(floor_number: int) -> str:
    """The band a floor belongs to — the highest-unlock tier at or below it.
    Floors 61-70 -> 'mythic' (Leviathan's Graveyard), 71-80 -> 'apex', etc."""
    eligible = [(unlock, tier) for tier, unlock in ENEMY_TIER_UNLOCK_FLOOR.items() if unlock <= floor_number]
    return max(eligible)[1] if eligible else "beginner"

def _enemy_pool_for_floor(floor_number: int) -> list[tuple]:
    """Each floor pulls ONLY from its own band's roster, so every 10-floor
    area feels distinct — floors 61-70 are all Leviathan's Graveyard sea
    enemies rather than a grab-bag of everything unlocked. (Previously every
    tier <= floor stayed in the pool; changed 2026-07-10 so areas read as
    areas. Difficulty still scales purely by floor_number, so a band's
    enemies are power-scaled to whatever floor of the band you're on.)"""
    tier = _current_tier_for_floor(floor_number)
    return [e for e in ENEMY_TYPES if e[5] == tier]

def _primary_etype_for_floor(floor_number: int, pool: list[tuple]) -> tuple:
    """Deal the band's roster across the band's floors so the WHOLE pool gets
    used and neighbouring floors differ — instead of each floor independently
    rng.choice()ing (which clustered onto 2-3 types and starved the rest). The
    band's order is shuffled with a fixed per-band seed, then the floor's
    position within the band indexes into it. Still fully seeded/deterministic
    (a scout's report holds) and not hand-assigned — just evenly spread. The
    mixed-encounter second type below stays a fresh rng.choice for extra
    variety on top of this even primary spread."""
    tier = _current_tier_for_floor(floor_number)
    band_start = ENEMY_TIER_UNLOCK_FLOOR[tier]
    order = list(pool)
    random.Random(band_start * 104729).shuffle(order)
    return order[(floor_number - band_start) % len(order)]

# ═══ THE TOWER AWAKENS (difficulty rebalance, approved 2026-07-11) ═══
# Player power COMPOUNDS (levels × stars × gear × boons × research) while the
# old enemy scale was linear — so the game got EASIER deep down, the opposite
# of the design goal (floor 100 must stay a near-mythical achievement; the
# manhwa's record is ~80 after years). Past floor 40 the Tower answers with a
# compounding curve of its own: +10% @50, +35% @70, +64% @90, +82% @100.
AWAKENING_START_FLOOR = 40
AWAKENING_RATE = 1.01

def tower_scale(floor_number: int) -> float:
    """The universal enemy stat scale — linear early, compounding past 40."""
    base = 1 + (floor_number * 0.12)
    if floor_number > AWAKENING_START_FLOOR:
        base *= AWAKENING_RATE ** (floor_number - AWAKENING_START_FLOOR)
    return base


def _build_enemy_group(etype, floor_number: int, difficulty_mult: float, id_start: int, count_override: int = None, max_count_override: int = None, rng: random.Random = None) -> list[CombatUnit]:
    """Build one monster type's portion of an encounter. Pulled out of
    make_enemies so a mixed encounter (two archetypes sharing one fight) can
    call this twice with a split difficulty_mult budget instead of duplicating
    the count/stat math. id_start offsets negative CombatUnit ids so two
    groups in the same encounter never collide."""
    scale = tower_scale(floor_number)
    name, hp_m, def_m, spd_m, archetype, _tier = etype

    # Apply archetype modifiers first — count/difficulty math below needs
    # the post-archetype numbers, not the raw per-monster base stats.
    atk_m = 1.0
    if archetype == "swarm":
        atk_m = 0.5
        hp_m *= 0.5
        def_m *= 0.3
    elif archetype == "pack":
        atk_m = 0.4
        hp_m *= 0.4
        def_m *= 0.4
    elif archetype == "elite":
        atk_m = 1.5
        hp_m *= 1.5
        def_m *= 1.5

    if archetype == "swarm":
        base_count = 8.0
    elif archetype == "pack":
        base_count = 3.5
    elif archetype == "elite":
        base_count = 1.0
    else:  # normal
        base_count = (1 + min(3, 1 + floor_number // 10)) / 2

    # Survival Floor swarms intentionally blow past the normal per-archetype
    # cap below (max_count_override) — "countless" only reads as countless
    # next to the regular swarm's 20-unit ceiling.
    max_count = max_count_override or {"swarm": 20, "pack": 10, "elite": 3}.get(archetype, 8)

    _r = rng or random
    if count_override is not None:
        count = max(1, min(max_count, count_override))
    elif difficulty_mult == 1.0:
        count = max(1, min(max_count, round(_r.uniform(base_count - 0.5, base_count + 0.5))))
    else:
        unit_power = hp_m * (atk_m + def_m)
        target_total_power = base_count * unit_power * difficulty_mult
        count = max(1, min(max_count, round(target_total_power / unit_power))) if unit_power > 0 else max(1, round(base_count))
        actual_total = count * unit_power
        # Rounding count to an integer (especially count=1 for elites)
        # leaves a gap between actual and target total power — close it
        # with a stat correction so the encounter's real difficulty.
        # Power is Health * (ATK+DEF) — a product of two corrected terms —
        # so the correction must be split via sqrt across them, or it
        # would double-count and land at correction^2 instead.
        stat_correction = (target_total_power / actual_total) if actual_total > 0 else 1.0
        half_correction = stat_correction ** 0.5
        hp_m *= half_correction
        atk_m *= half_correction
        def_m *= half_correction

    enemy_portrait_path = _enemy_portrait_path(name, "elite" if archetype == "elite" else "")

    abilities = ENEMY_ABILITY_OVERRIDES.get(name) or (["cleave"] if archetype == "elite" else [])
    spawn_template = ENEMY_SPAWN_TEMPLATE.get(name, "")
    regen_pct = SELF_REGEN_PCT if "self_regen" in abilities else 0.0
    # Enemy "level" is purely a flavor readout matching floor depth (elites
    # read a little tougher than their floor) — it doesn't feed back into
    # their actual stats, which are already fully determined by hp_m/atk_m/
    # def_m above. Duplicates in an encounter now share one name + level tag
    # ("Rotting Ghoul [Lv 12]") instead of being numbered 1/2/3.
    enemy_level = max(1, floor_number + (3 if archetype == "elite" else 0))

    enemies = []
    for i in range(count):
        enemies.append(CombatUnit(
            id=-(id_start + i + 1),
            name=name,
            level=enemy_level,
            health=max(1, int(80 * scale * hp_m)), max_health=max(1, int(80 * scale * hp_m)),
            strength=max(1, int(8 * scale * atk_m)), intelligence=0, defense=int(5 * scale * def_m),
            endurance=int(5 * scale * def_m),
            agility=int(10 * scale * spd_m),
            morale=100, stress=0, is_hero=False,
            portrait_path=enemy_portrait_path,
            abilities=list(abilities),
            spawn_template=spawn_template,
            regen_pct=regen_pct,
        ))
    return enemies


def _make_swarm_add(name: str, floor_number: int, unit_id: int) -> CombatUnit:
    """Builds a single weak swarm-tier add for a 'summon_add' ability —
    reuses the same swarm archetype math _build_enemy_group applies (0.5x
    atk/hp, 0.3x def) but as a standalone unit rather than a whole group, and
    based off floor depth rather than the summoner's own (much stronger)
    stats, so reinforcements read as "more chip damage," not a second boss."""
    scale = tower_scale(floor_number)
    portrait_path = _enemy_portrait_path(name)
    return CombatUnit(
        id=-unit_id, name=name, level=max(1, floor_number),
        health=max(1, int(80 * scale * 0.5)), max_health=max(1, int(80 * scale * 0.5)),
        strength=max(1, int(8 * scale * 0.5)), intelligence=0,
        defense=int(5 * scale * 0.3), endurance=int(5 * scale * 0.3),
        agility=int(10 * scale * 1.2),
        morale=100, stress=0, is_hero=False, portrait_path=portrait_path,
    )


def _enemy_frontline_n(total: int) -> int:
    """How many enemies form the FRONT LINE the party targets first. Scales
    with the swarm (~the ally 2-of-5 = 40% ratio) so the front stays a
    sensible fraction instead of a flat 2 that looks tiny behind a big horde
    (Liam). Min 2 (matches the ally frontline on small fights); capped so a
    30-50 survival swarm doesn't shove its whole roster up front."""
    if total <= 0:
        return 0
    return min(6, max(2, round(total * 0.4)))


def make_enemies(floor_number: int, count: int = None, difficulty_mult: float = 1.0) -> list[CombatUnit]:
    """
    Generate enemies for a floor. Difficulty is purely a function of floor
    number — not the player's team strength. A 7★ team and a 1★ team face
    the identical floor 10 enemies.

    difficulty_mult scales the TOTAL threat of the encounter (not just enemy
    count) — a "weak" target against an elite archetype still comes out
    weaker even though elites can't drop below a count of 1; the shortfall
    that rounding count to an integer can't absorb gets folded into a stat
    correction instead. This is what lets a choice like "fight defensively"
    mean something consistent regardless of which archetype gets rolled,
    rather than just meaning "fewer enemies" (5 weak swarmers can be an
    easier fight than 1 elite — raw count alone doesn't capture that).
    """
    # Which enemy type(s) appear on this floor is composition, not combat
    # tactics — fixed per floor_number via a seeded RNG local to this call,
    # never the shared global `random`, so floor N always rolls the exact
    # same composition decision on every attempt (a "scout" team's intel
    # about what's on a floor is then actually trustworthy). In-fight
    # randomness (damage variance, crit rolls, AI targeting) is untouched
    # and still uses the global random — only "what shows up" is seeded.
    rng = random.Random(floor_number * 7919 + 1)
    pool = _enemy_pool_for_floor(floor_number)
    etype = _primary_etype_for_floor(floor_number, pool)

    # Mixed encounters (two different monster types in one fight) are now
    # the default flavor for common floors — splits the same difficulty
    # budget across two archetypes instead of always rolling one. Skipped
    # when the caller passed an explicit count (survival-floor overrides
    # etc. want one clean group, not a fractional split of a fixed number).
    if count is None and rng.random() < 0.45:
        other_types = [e for e in pool if e[0] != etype[0]]
        etype2 = rng.choice(other_types)
        split = rng.uniform(0.35, 0.65)
        group1 = _build_enemy_group(etype, floor_number, difficulty_mult * split, id_start=0, rng=rng)
        group2 = _build_enemy_group(etype2, floor_number, difficulty_mult * (1 - split), id_start=len(group1), rng=rng)
        # Elite promotion rides the same seeded rng — floor N's elite (or lack
        # of one) is a stable fact of that floor, like its composition.
        return maybe_elevate_elite(group1 + group2, floor_number, rng)

    return maybe_elevate_elite(
        _build_enemy_group(etype, floor_number, difficulty_mult, id_start=0, count_override=count, rng=rng),
        floor_number, rng)


# Survival Floor (Boss Swarm) — an alternative to the typical single strong
# miniboss on a %5 floor: instead of one tough unique, the floor throws an
# "overwhelming swarm" the team can't realistically kill in time. Distinct
# from make_enemies' regular swarm archetype (capped at 20, plain
# kill-them-all win condition) — this is specifically the "countless, just
# survive the clock" framing, so it spawns far more bodies than any normal
# combat floor would, plus 1-2 genuinely dangerous Elites mixed in so the
# fight isn't pure chip damage.
SURVIVAL_SWARM_COUNT_RANGE = (30, 50)
SURVIVAL_SWARM_ELITE_COUNT_RANGE = (1, 2)

def make_swarm_miniboss_encounter(floor_number: int) -> list[CombatUnit]:
    """Builds the enemy roster for a Survival Floor miniboss encounter.
    Seeded the same way as make_enemies — a scout's "this floor is a
    Survival Swarm of Goblins" report stays true on the real attempt."""
    rng = random.Random(floor_number * 7919 + 2)
    pool = _enemy_pool_for_floor(floor_number)
    swarm_types = [e for e in pool if e[4] in ("swarm", "pack")] or pool
    elite_types = [e for e in pool if e[4] == "elite"]

    swarm_etype = rng.choice(swarm_types)
    swarm_count = rng.randint(*SURVIVAL_SWARM_COUNT_RANGE)
    enemies = _build_enemy_group(swarm_etype, floor_number, difficulty_mult=1.0, id_start=0,
                                  count_override=swarm_count, max_count_override=swarm_count, rng=rng)

    if elite_types:
        elite_count = rng.randint(*SURVIVAL_SWARM_ELITE_COUNT_RANGE)
        elite_etype = rng.choice(elite_types)
        elites = _build_enemy_group(elite_etype, floor_number, difficulty_mult=1.0, id_start=len(enemies),
                                     count_override=elite_count, max_count_override=elite_count, rng=rng)
        enemies += elites

    return enemies


# Survival Floor pacing — "illusion of neverending" means the swarm doesn't
# realistically die before the clock does. 10 rounds (vs. the normal 30-round
# safety cap) keeps a fight long enough to feel like an onslaught without
# dragging a single floor entry on forever. Confirmed scope: this is a random
# *alternative* on miniboss floors only (floor % 5 == 0, not % 10) — it does
# not replace every miniboss encounter, and never appears on regular combat
# or boss floors.
SURVIVAL_TURN_LIMIT = 10
SWARM_SURVIVAL_CHANCE = 0.35

# Escort floors: protect an NPC instead of (or alongside) clearing enemies.
# Own turn-limit constant, separate from SURVIVAL_TURN_LIMIT, since the two
# floor types have unrelated pacing — escort is "keep this specific unit
# alive," not "survive an onslaught."
ESCORT_TURN_LIMIT = 15
ESCORT_NPC_AGGRO_CHANCE = 0.4  # without a taunt up, the NPC is at elevated but not certain risk
ESCORT_RESCUE_MORALE_BONUS = 8  # small, deliberate — "nothing crazy" per explicit direction

# Retrieval Mission — the goal is NOT to clear the room: a player-designated
# Runner spends every turn working the objective (they never attack), and the
# rest of the team keeps them alive until the channel completes. Win = Runner
# alive when the channel finishes (or the room is wiped early); the Runner
# dying fails the floor outright, even with the rest of the team standing.
RETRIEVAL_TURN_LIMIT = 6  # rounds of channeling the objective needs
RETRIEVAL_RUNNER_AGGRO_CHANCE = 0.35  # enemies notice the channeler — tanky-vs-evasive Runner picks both matter

# Blitz/Time Attack: the room itself empowers enemies every round they're
# still standing — a flat stacking multiplier, applied once per round
# starting round 2 (round 1 is the baseline, nothing stacked yet).
BLITZ_STACK_PER_ROUND = 0.20

_UNSET = object()

def _enemy_portrait_path(name: str, subfolder: str = "") -> str:
    """Looks up a dedicated portrait for a named enemy — checked under
    enemies/<subfolder>/<slug>.png first (the per-tier folders the enemy
    roster overhaul plan asked for: elite/miniboss/boss/raid_boss), then
    enemies/normal/<slug>.png (where every plain-tier enemy's art now
    lives), then the flat enemies/<slug>.png used by the pre-reorg roster
    for anything not yet moved, then "" (frontend already renders a
    placeholder for that, same as any as-yet-unportraited enemy like
    Goblin/Wolf today).

    Within each tier folder, files may also sit one level deeper in a
    "waveN" subfolder (purely organizational, for reviewing a floor-range
    family's art together — e.g. enemies/normal/wave1/slime.png) — checked
    after the tier folder's own root so moving a file into a wave folder
    for review never breaks the lookup."""
    import os, glob, re
    # MUST match _generate_enemy_portrait's slug (re.sub, punctuation -> _):
    # the old .replace(' ', '_') kept commas/hyphens, so generated art for
    # "Knight-Captain Mordrek" / "The Rotcaller, Warlord..." sat on disk
    # under the regex slug while this lookup asked for a name that could
    # never exist — those bosses silently fell back to random art.
    slug = re.sub(r'[^a-z0-9]', '_', name.lower())
    for sf in filter(None, [subfolder, "normal"]):
        tiered = f"static/portraits/enemies/{sf}/{slug}.png"
        if os.path.exists(tiered):
            return tiered
        wave_matches = glob.glob(f"static/portraits/enemies/{sf}/wave*/{slug}.png")
        if wave_matches:
            return wave_matches[0].replace("\\", "/")
    flat = f"static/portraits/enemies/{slug}.png"
    return flat if os.path.exists(flat) else ""


def make_boss(floor_number: int, zone_theme: str = "", is_miniboss: bool = False, boss_data_override=_UNSET, family_override: dict = None) -> list[CombatUnit]:
    """Create a boss or miniboss enemy. family_override (see
    services/enemy_families.py) lets a defined floor-range family supply a
    deterministic named encounter (e.g. floor 5's "Goblin King") instead of
    the generic procedural LLM/fallback naming below — used for floor ranges
    that have a built-out family, skipped entirely otherwise."""
    scale = tower_scale(floor_number)

    if family_override:
        boss_title = family_override["name"]
        mod = family_override.get("stat_mod") or {"atk": 1.0, "def": 1.0, "spd": 1.0, "health": 1.0}
        abilities = family_override.get("abilities") or (["cleave", "enrage"] if is_miniboss else ["crushing_blow", "last_stand"])
        spawn_template = family_override.get("spawn_template", "")
        # A family can pin an exact existing portrait (e.g. a hand-picked
        # piece of preserved art) instead of relying on the name-based
        # lookup — these boss archetype files live under enemies/boss/ but
        # are named by archetype (boss_undead_monarch.png), not by the
        # family's display name ("The Undead Monarch"), so the slug-based
        # lookup wouldn't find them on its own.
        # Raid Boss portrait folder used only on floors 50 and 100.
        is_raid = (not is_miniboss) and floor_number in {50, 100}
        portrait_tier_dir = "raid_boss" if is_raid else ("miniboss" if is_miniboss else "boss")
        # Pinned paths are existence-checked so a family whose art hasn't
        # been generated yet (e.g. the Fallen Ascendant) degrades to the
        # normal lookup/fallback chain instead of a broken image.
        import os as _os
        pinned = family_override.get("portrait_path")
        if pinned and not _os.path.exists(pinned):
            pinned = None
        portrait_path = pinned or _enemy_portrait_path(boss_title, portrait_tier_dir) or None
        power = (1.5 + (floor_number / 40)) if is_miniboss else (2.5 + (floor_number / 30))
        from services.portrait_cache import get_random_boss_portrait
        boss = CombatUnit(
            id=-99, name=boss_title,
            level=max(1, floor_number + (10 if not is_miniboss else 5)),
            health=int(220 * scale * power * mod['health']), max_health=int(220 * scale * power * mod['health']),
            strength=int(16 * scale * (power * 0.28) * mod['atk']), intelligence=0,
            defense=int(12 * scale * (power * 0.35) * mod['def']),
            endurance=int(12 * scale * (power * 0.35) * mod['def']),
            agility=int(8 * scale * mod['spd']),
            morale=100, stress=0, is_hero=False,
            portrait_path=portrait_path or get_random_boss_portrait(is_miniboss=is_miniboss),
            abilities=abilities,
            spawn_template=spawn_template,
        )
        return [boss]

    # Boss naming is pure flavor — never let it block combat resolution.
    # boss_data_override lets the caller pre-fetch this concurrently with the
    # zone theme call instead of sequentially after it (see tower.py) — if the
    # caller already tried and got nothing (timeout), trust that and use the
    # local fallback pool below instead of attempting a second, redundant
    # sequential LLM call here. Only attempt our own call if the caller never
    # tried pre-fetching at all (boss_data_override wasn't passed).
    boss_data = None if boss_data_override is _UNSET else boss_data_override
    if boss_data_override is _UNSET and zone_theme:
        from services.llm_service import generate_boss_enemy, call_with_timeout
        boss_data = call_with_timeout(generate_boss_enemy, zone_theme, floor_number, is_miniboss, timeout=1.5)

    if boss_data:
        name = boss_data.get("name", "Unknown Boss")
        mod = {
            "name": boss_data.get("modifier", "Enraged"),
            "health": boss_data.get("hp_multiplier", 1.2),
            "atk": boss_data.get("atk_multiplier", 1.2),
            "def": boss_data.get("def_multiplier", 1.0),
            "spd": boss_data.get("spd_multiplier", 1.0)
        }
    else:
        boss_names = [
            "The Hollow King", "Dread Sentinel", "Abyssal Warden",
            "The Shattered One", "Lord of Ash", "The Undying",
            "Nightmare Colossus", "The Tower's Hunger",
        ]
        name = boss_names[min(len(boss_names) - 1, floor_number // 10 - 1)]
        boss_modifiers = [
            {"name": "Enraged", "atk": 1.5, "def": 0.7, "spd": 1.0, "health": 1.0},
            {"name": "Armored", "atk": 1.0, "def": 2.0, "spd": 0.8, "health": 1.0},
            {"name": "Colossal", "atk": 1.0, "def": 1.0, "spd": 0.7, "health": 1.8},
            {"name": "Frenzied", "atk": 1.2, "def": 1.0, "spd": 1.5, "health": 1.0},
            {"name": "Vampiric", "atk": 1.1, "def": 1.1, "spd": 1.1, "health": 1.1},
            {"name": "Cursed", "atk": 1.3, "def": 0.8, "spd": 1.2, "health": 0.9},
        ]
        # Seeded so a floor without a built-out family (most floors past
        # the first 10) still rolls the same fallback modifier every visit
        # when the LLM boss-naming call times out — matches make_enemies'
        # composition-determinism. The LLM-sourced name/modifier path above
        # (when the call succeeds) is intentionally NOT made deterministic
        # here — boss naming is explicitly "pure flavor" sourced fresh each
        # time, a deliberate existing design choice, not an oversight; doing
        # so would mean caching LLM output per floor, a bigger change than
        # this pass covers.
        mod = random.Random(floor_number * 7919 + 3).choice(boss_modifiers)

    if is_miniboss and not boss_data:
        name = f"Lieutenant of {name}"
    
    # Power curves were originally tuned far too aggressively (a floor-10
    # boss hit for ~106 base strength — a near-instant kill against an early
    # team's 80-170 Health heroes). Scaled down so a boss is a meaningfully
    # tougher single-target fight, not a one/two-shot machine.
    if is_miniboss:
        power = 1.5 + (floor_number / 40)
    else:
        power = 2.5 + (floor_number / 30)

    boss_title = f"{mod['name']} {name}"

    # Signature abilities by tier — minibosses get a recurring party-wide
    # threat (cleave) plus a one-time enrage; full bosses get two big
    # one-time swings instead (an early crushing blow, a late-game heal).
    abilities = ["cleave", "enrage"] if is_miniboss else ["crushing_blow", "last_stand"]

    from services.portrait_cache import get_random_boss_portrait
    boss = CombatUnit(
        id=-99, name=boss_title,
        level=max(1, floor_number + (10 if not is_miniboss else 5)),
        health=int(220 * scale * power * mod['health']), max_health=int(220 * scale * power * mod['health']),
        strength=int(16 * scale * (power * 0.28) * mod['atk']), intelligence=0,
        defense=int(12 * scale * (power * 0.35) * mod['def']),
        endurance=int(12 * scale * (power * 0.35) * mod['def']),
        agility=int(8 * scale * mod['spd']),
        morale=100, stress=0, is_hero=False,
        portrait_path=get_random_boss_portrait(is_miniboss=is_miniboss),
        abilities=abilities,
    )
    return [boss]




def make_miniboss_variant(variant: str, floor_number: int, zone_theme: str, heroes: list[dict]) -> list[CombatUnit]:
    """The 4 non-swarm miniboss "gear/comp check" variants — "survival" is
    handled separately by the existing is_survival_swarm path (see caller),
    not here. Each forces a different team-comp answer instead of every
    5th floor just being "a beefier guy": Behemoth tests raw DPS, Assassin
    tests having a real frontline, Twins tests a mixed-damage comp, Mirror
    tests against the team's own shape."""
    scale = tower_scale(floor_number)
    power = 1.5 + (floor_number / 40)
    from services.portrait_cache import get_random_boss_portrait

    if variant == "behemoth":
        return [CombatUnit(
            id=-99, name="The Behemoth",
            level=max(1, floor_number + 5),
            health=int(220 * scale * power * 2.6), max_health=int(220 * scale * power * 2.6),
            strength=int(16 * scale * power * 0.12), intelligence=0,
            defense=int(12 * scale * power * 0.9), endurance=int(12 * scale * power * 0.9),
            agility=int(8 * scale * 0.5),
            morale=100, stress=0, is_hero=False,
            portrait_path=get_random_boss_portrait(is_miniboss=True),
            abilities=["enrage"],
        )]

    if variant == "assassin":
        return [CombatUnit(
            id=-99, name="The Assassin",
            level=max(1, floor_number + 5),
            health=int(220 * scale * power * 0.55), max_health=int(220 * scale * power * 0.55),
            strength=int(16 * scale * power * 0.55), intelligence=0,
            defense=int(12 * scale * power * 0.2), endurance=int(12 * scale * power * 0.2),
            agility=int(8 * scale * 2.2),
            crit_chance=0.35,
            morale=100, stress=0, is_hero=False,
            portrait_path=get_random_boss_portrait(is_miniboss=True),
            abilities=["crushing_blow"],
        )]

    if variant == "twins":
        base_stats = dict(
            health=int(220 * scale * power * 0.85), max_health=int(220 * scale * power * 0.85),
            strength=int(16 * scale * power * 0.30), intelligence=0,
            defense=int(12 * scale * power * 0.35), endurance=int(12 * scale * power * 0.35),
            agility=int(8 * scale),
            morale=100, stress=0, is_hero=False,
            abilities=["cleave"],
        )
        return [
            CombatUnit(id=-98, name="Twin of Iron", physical_resist_pct=0.6,
                       portrait_path=get_random_boss_portrait(is_miniboss=True), **base_stats),
            CombatUnit(id=-99, name="Twin of Shadow", magic_resist_pct=0.6,
                       portrait_path=get_random_boss_portrait(is_miniboss=True), **base_stats),
        ]

    if variant == "mirror":
        # One shadow clone per deployed hero (capped at 4 so a full 5-stack
        # doesn't become an unwinnable mirror match) — each clone borrows
        # the matching hero's own class, power_stat, and stat RATIO scaled
        # to miniboss power, so a STR-heavy team fights a STR-heavy mirror
        # and a caster-heavy team fights one that actually hits via INT.
        clones = []
        for i, h in enumerate(heroes[:4]):
            hero_power = max(1, h.get("strength", 10) + h.get("intelligence", 0) + h.get("agility", 10))
            target_power = 16 * scale * power * 0.30
            mult = target_power / hero_power
            clones.append(CombatUnit(
                id=-(90 + i), name=f"Shadow {h.get('name', 'Doppelganger')}",
                level=max(1, floor_number + 5),
                health=int(220 * scale * power * 0.55), max_health=int(220 * scale * power * 0.55),
                strength=max(1, int(h.get("strength", 10) * mult)),
                intelligence=max(0, int(h.get("intelligence", 0) * mult)),
                defense=int(12 * scale * power * 0.3), endurance=int(12 * scale * power * 0.3),
                agility=max(1, int(h.get("agility", 10) * mult * 0.6)),
                power_stat=h.get("power_stat", "strength"),
                hero_class=h.get("hero_class", "Classless"),
                morale=100, stress=0, is_hero=False,
                portrait_path=get_random_boss_portrait(is_miniboss=True),
            ))
        return clones or make_boss(floor_number, zone_theme, is_miniboss=True)

    return make_boss(floor_number, zone_theme, is_miniboss=True)


def _fear_check(unit: CombatUnit, log: list, resist_mult: float = 1.0) -> bool:
    """
    Check if a hero is paralyzed by fear this round.
    Based on trauma + stress levels.
    Returns True if the hero is fear-stunned.

    resist_mult comes from a Stoic Leader's leadership bonus (see
    LEADERSHIP_BONUS) — 1.0 for everyone else, lower when a calm Leader is
    steadying the whole squad's nerves for the fight.
    """
    if unit.fear_immune or not unit.is_hero:
        return False

    trauma = unit.trauma
    stress = unit.stress

    # Fear chance: 0% below 40 trauma, scales up
    if trauma < 40:
        return False
    elif trauma < 60:
        chance = (0.08 + (stress * 0.001)) * resist_mult
    elif trauma < 80:
        chance = (0.15 + (stress * 0.002)) * resist_mult
    else:
        chance = (0.25 + (stress * 0.003)) * resist_mult

    if random.random() < chance:
        unit.fear_stunned = True
        fear_lines = [
            f"  ✗ {unit.name} freezes — the trauma overwhelms them.",
            f"  ✗ {unit.name}'s hands tremble. They cannot move.",
            f"  ✗ {unit.name} screams and covers their eyes. Fear takes hold.",
            f"  ✗ {unit.name} is paralyzed by terror. The memories are too much.",
        ]
        log.append(random.choice(fear_lines))
        return True

    return False


# ─── Grief and resentment ───────────────────────────────────────────────────
#
# Both of these deliberately reuse the existing panic states rather than
# inventing new combat math: bracing_rounds (pull back, take less damage,
# contribute less) and isolated_rounds (charge out exposed, take more damage,
# become the preferred enemy target). Those are already tuned and tested, and
# they happen to describe grief and vengeance exactly.

BOND_GRIEF_THRESHOLD = 3      # bond level below this is an acquaintance, not a loss
BOND_GRIEF_ROUNDS = 2
BOND_RAGE_TENDENCIES = {"Vengeful", "Reckless"}   # these charge instead of freezing

EGO_RESENT_THRESHOLD = 30     # patience below this = they don't want to be here
EGO_RESENT_CHANCE = 0.35      # per round, so it reads as sullen rather than scripted
EGO_RESENT_ROUNDS = 1


def _bond_death_reactions(fallen, alive_heroes, pairwise_bonds, log):
    """A hero who just watched someone they were close to die reacts to it.

    This is the payoff for the bond system existing at all: until now a bond
    was worth +1% stats per level and nothing else, so the relationship never
    showed up at the moment it would actually matter. Vengeful and Reckless
    heroes charge (isolated — exposed, and enemies prefer them); everyone else
    freezes up defensively for a round or two.
    """
    if not pairwise_bonds:
        return
    for hero in alive_heroes:
        if not hero.alive or hero is fallen or not hero.is_hero:
            continue
        key = (min(hero.id, fallen.id), max(hero.id, fallen.id))
        level = pairwise_bonds.get(key, 0)
        if level < BOND_GRIEF_THRESHOLD:
            continue
        if hero.battle_tendency in BOND_RAGE_TENDENCIES:
            hero.isolated_rounds = max(hero.isolated_rounds, BOND_GRIEF_ROUNDS)
            log.append(f"  ✦ {hero.name} sees {fallen.name} fall and breaks formation — nothing else matters now.")
        else:
            hero.bracing_rounds = max(hero.bracing_rounds, BOND_GRIEF_ROUNDS)
            log.append(f"  ✗ {hero.name} falters — {fallen.name} is down, and their guard goes up instead of forward.")


def _ego_resentment_check(hero, log):
    """A hero whose ego has been ignored fights like it.

    ego_patience already decays when the lineup isn't what they'd have picked,
    and at zero they rebuild the team themselves (ego_service). That rebellion
    was the only consequence, which made the whole slide invisible until it
    fired. Now the resentment shows up in the fight first — so a patience
    problem is something the player can watch happening rather than something
    that ambushes them.
    """
    if not hero.is_hero or not hero.ego_type or hero.ego_patience >= EGO_RESENT_THRESHOLD:
        return False
    if random.random() >= EGO_RESENT_CHANCE:
        return False
    hero.bracing_rounds = max(hero.bracing_rounds, EGO_RESENT_ROUNDS)
    log.append(f"  ✗ {hero.name} hangs back — they never wanted to fight alongside this squad.")
    return True


# battle_tendency -> the whole squad's passive combat modifier while this
# Leader is assigned, scaled by leader_star_mult where it's applied. Tuned
# so a single tendency never reads as strictly better than another — each
# is a different flavor of "this squad fights like its Leader."
LEADERSHIP_BONUS = {
    "Reckless":      {"atk_mult": 0.04},
    "Calculating":   {"def_mult": 0.04, "crit_bonus": 0.02},
    "Protective":    {"def_mult": 0.06},
    "Glory-Seeking": {"crit_bonus": 0.04},
    "Vengeful":      {"atk_mult": 0.03, "crit_bonus": 0.02},
    "Stoic":         {"fear_resist": 0.3},  # scales down the whole squad's fear/panic chance
}
LEADER_STEADY_CHANCE_BASE = 0.10  # per star, per-round chance to snap a squadmate out of fear/panic

TENDENCY_TARGET_OVERRIDE_CHANCE = 0.3

def _apply_tendency_target_override(default_target: CombatUnit, candidates: list[CombatUnit], squad_tendency: str | None) -> CombatUnit:
    """Light, probabilistic nudge driven by the team Leader's battle_tendency
    (squad_tendency) — never overrides class-locked targeting rules (e.g.
    Assassin's backline rule, handled entirely by the caller before this is
    invoked), and only fires some of the time so it reshuffles focus rather
    than replacing the existing front-to-back logic outright."""
    if not squad_tendency or len(candidates) < 2:
        return default_target
    if random.random() > TENDENCY_TARGET_OVERRIDE_CHANCE:
        return default_target

    if squad_tendency in ("Reckless", "Glory-Seeking"):
        return min(candidates, key=lambda u: u.health)
    elif squad_tendency == "Calculating":
        return max(candidates, key=lambda u: u.strength)
    return default_target


TENDENCY_FLAVOR_CHANCE = 0.25
TENDENCY_KILL_LINES = {
    "Reckless": "  ✦ {attacker} doesn't even wait to see {target} fall before moving on.",
    "Calculating": "  ✦ {attacker} finishes {target} with cold precision.",
    "Protective": "  ✦ {attacker} ends {target} without hesitation — no one else gets hurt today.",
    "Glory-Seeking": "  ✦ {attacker} makes a show of {target}'s fall.",
    "Vengeful": "  ✦ {attacker} drives the killing blow home like it's personal.",
    "Stoic": "  ✦ {target} falls.",
}

def _kill_log_line(attacker: CombatUnit, target: CombatUnit) -> str:
    """Occasionally flavors a kill with the attacker's OWN battle_tendency
    (individual flavor — distinct from the leader-driven squad targeting
    nudge above, which is about who gets targeted, not how it's narrated)."""
    if random.random() < TENDENCY_FLAVOR_CHANCE and attacker.battle_tendency in TENDENCY_KILL_LINES:
        return TENDENCY_KILL_LINES[attacker.battle_tendency].format(attacker=attacker.log_name, target=target.log_name)
    return f"  ✦ {target.log_name} falls."


# Star rank no longer makes a hero immune to panic outright — it just makes
# it less likely, alongside talent and battle_tendency. The chance is then
# scaled by the encounter's power_ratio (enemy power / hero power for this
# fight, from the same difficulty-budget numbers make_enemies already uses)
# so a curb-stomp panics people regardless of star, and a clean win rarely
# does even for a 1-star.
PANIC_BASE_CHANCE_BY_STAR = {1: 0.20, 2: 0.14, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.035, 7: 0.025}
# Reckless/Calculating are no more fear-prone than anyone else now, but the
# OTHER tendencies hold up better under pressure — Protective/Stoic/Vengeful
# shield, steel themselves, or get angry instead of scared; Glory-Seeking is
# partway between (vain confidence helps some, but not as much as the above).
TENDENCY_PANIC_RESIST = {
    "Protective": 0.5, "Stoic": 0.55, "Vengeful": 0.6, "Glory-Seeking": 0.8,
}

# Panic doesn't remove a hero from the fight, it makes them WORSE off in it —
# there's no escaping the floor, you clear it or you don't:
#   - Reckless/Glory-Seeking break formation and get isolated — exposed,
#     take bonus damage, become the enemy's preferred target.
#   - Everyone else falls back defensively instead, skipping their strength
#     to brace and try to survive the next hit.
ISOLATED_ROUNDS = 2
BRACING_ROUNDS = 1

def _panic_check(unit: CombatUnit, trigger: str, log: list, power_ratio: float = 1.0, resist_mult: float = 1.0) -> bool:
    """Any hero can panic now — star rank, talent, and battle_tendency reduce
    susceptibility rather than gating it outright. Distinct from the
    trauma-gated _fear_check above (which just skips a turn) — this is a
    rarer, harsher response triggered by specific events (witnessing a death,
    dropping critically low) rather than an ongoing trauma/stress level."""
    if not unit.is_hero or not unit.alive:
        return False
    if unit.isolated_rounds > 0 or unit.bracing_rounds > 0:
        return False  # already panicking this fight, don't restack

    base = PANIC_BASE_CHANCE_BY_STAR.get(unit.hero_star, 0.02)
    base *= (1.0 - unit.talent * 0.4)  # talented heroes keep their cool better
    tendency_resist = TENDENCY_PANIC_RESIST.get(unit.battle_tendency, 1.0)
    # Willpower stat resistance — capped at 50% reduction so it's a strong,
    # visible effect without making a high-Willpower hero flatly immune
    # (consistent with this fight's "no hard immune switch" design).
    willpower_resist = max(0.5, 1.0 - unit.willpower / 100)
    chance = base * willpower_resist * tendency_resist * resist_mult * max(0.4, min(2.2, power_ratio))
    if trigger == "hp_critical":
        chance *= 1.5
    if random.random() >= chance:
        return False

    if unit.battle_tendency in ("Reckless", "Glory-Seeking"):
        unit.isolated_rounds = ISOLATED_ROUNDS
        isolated_lines = [
            f"  {unit.name} panics and breaks formation — exposed and alone!",
            f"  {unit.name} loses their head and charges off-formation!",
            f"  {unit.name} scatters from the group, vulnerable.",
        ]
        log.append(random.choice(isolated_lines))
    else:
        unit.bracing_rounds = BRACING_ROUNDS
        bracing_lines = [
            f"  {unit.name} abandons the offensive, bracing defensively to survive.",
            f"  {unit.name} knows running alone is a death sentence — they dig in instead.",
            f"  {unit.name} falls back, covering themselves rather than attacking.",
        ]
        log.append(random.choice(bracing_lines))
    return True


# Unimber — a lone hero facing a pack takes escalating damage (40% per
# enemy past the first), but it's recomputed live off the current alive
# counts rather than stored as a status effect, so it scales down the
# instant allies die or extra enemies fall — no separate "lift" logic
# needed for the "reinforcement arrived" / "enemies thinned out" cases.
UNIMBER_DAMAGE_PER_EXTRA_ENEMY = 0.40
UNIMBER_MAX_ENEMIES = 5

# Mirrored from the enemy side: a boss facing a full 5-hero team gets padded
# rather than a lone hero just being squashed by a stat-static boss.
UNIMBER_BOSS_HP_PAD_PER_HERO = 0.20
UNIMBER_BOSS_DEF_PAD_PER_HERO = 0.10
UNIMBER_BOSS_PAD_MAX_HEROES = 4  # caps at the standard 5-hero team (4 "extra" heroes)

def unimber_stacks(defender: CombatUnit, ally_count: int, enemy_count: int) -> int:
    if not defender.is_hero or ally_count != 1 or enemy_count <= 1:
        return 0
    return min(enemy_count, UNIMBER_MAX_ENEMIES) - 1

def apply_unimber(damage: int, stacks: int) -> int:
    if stacks <= 0:
        return damage
    return int(damage * (1.0 + UNIMBER_DAMAGE_PER_EXTRA_ENEMY * stacks))


def calc_damage(attacker: CombatUnit, defender: CombatUnit, force_strength: bool = False) -> tuple[int, bool]:
    effective_def = defender.endurance * (1 - attacker.armor_pen)
    if defender.bracing_rounds > 0:
        effective_def *= 1.6  # bracing defensively to survive — the whole point of not fleeing
    # force_strength=True is the basic/auto attack path — casters (Acolyte,
    # Mage, etc.) hit hard through their Intelligence-scaled active skills,
    # not their plain weapon swing. Without this split, a class like Acolyte
    # with high STR but power_stat="intelligence" did the SAME basic-attack
    # damage as an ally with a fraction of its INT, since neither stat was
    # actually strength — confirmed real complaint: a 63 STR Acolyte hitting
    # for the same as a 12 STR ally on a plain attack.
    if force_strength:
        power = attacker.strength
    else:
        power = attacker.intelligence if attacker.power_stat == "intelligence" else attacker.strength
    base = power * (100 / (100 + max(0, effective_def)))

    if attacker.is_hero and attacker.morale < 40:
        morale_factor = 0.5 + (attacker.morale / 80)
        base *= morale_factor

    variance = random.uniform(0.85, 1.15)
    damage = max(1, int(base * variance))

    if defender.dmg_reduction_pct > 0:
        damage = max(1, int(damage * (1 - defender.dmg_reduction_pct)))

    # Physical/magic resist — same "intelligence basis = magical" split
    # power already uses above. Twins miniboss is the producer: one twin
    # resists physical, the other magical, forcing a mixed-damage comp.
    is_magical_hit = (not force_strength) and attacker.power_stat == "intelligence"
    resist = defender.magic_resist_pct if is_magical_hit else defender.physical_resist_pct
    if resist > 0:
        damage = max(1, int(damage * (1 - resist)))

    shield = next((e for e in defender.status_effects if e["type"] == "dmg_shield" and e["rounds"] > 0), None)
    if shield:
        damage = max(1, int(damage * (1 - shield["magnitude"])))

    if defender.isolated_rounds > 0:
        damage = int(damage * 1.3)  # exposed and unsupported, out of formation

    is_crit = random.random() < attacker.crit_chance
    if is_crit:
        damage = int(damage * 1.8)

    return damage, is_crit


# Enemy signature abilities — elite/miniboss/boss tiers get 1-2 of these
# instead of just a plain basic strength every turn. "cleave" can recur each
# turn (chance-gated); the rest are one-time triggers gated on the
# attacker's own Health, tracked via used_abilities so they only fire once.
MAX_SUMMONS_PER_BATTLE = 3
SUMMON_ADD_CHANCE = 0.18
TEAM_BUFF_AURA_ATK_MULT = 1.25

def _try_use_ability(attacker: CombatUnit, alive_heroes: list, log: list, morale_changes: dict, stress_changes: dict,
                      enemies: list = None, all_units: list = None, floor_number: int = 1) -> bool:
    """Returns True if an ability fired this turn (attacker's normal strength
    is skipped), False to fall through to a normal strength."""
    hlt_pct = attacker.health / attacker.max_health if attacker.max_health else 0

    # "summon_add" — a recurring, capped reinforcement call (Goblin King
    # summoning goblins, Giant Rat Alpha calling the swarm, etc). Needs
    # access to the live enemies/all_units lists so the new add actually
    # gets a turn this fight, not just a cosmetic log line.
    if ("summon_add" in attacker.abilities and enemies is not None and all_units is not None
            and attacker.summons_used < MAX_SUMMONS_PER_BATTLE and random.random() < SUMMON_ADD_CHANCE):
        spawn_name = attacker.spawn_template or "Goblin"
        spawn_count = random.randint(1, 2)
        new_id = -(2000 + attacker.summons_used * 10 + len([u for u in enemies if not u.is_hero]))
        new_adds = []
        for i in range(spawn_count):
            add = _make_swarm_add(spawn_name, floor_number, abs(new_id) + i)
            new_adds.append(add)
        enemies.extend(new_adds)
        all_units.extend(new_adds)
        attacker.summons_used += 1
        log.append(f"  ✦ {attacker.log_name} calls for reinforcements! {len(new_adds)}x {spawn_name} joins the fight!")
        return True

    # "team_buff_aura" — a one-time rallying cry that empowers every other
    # enemy still standing (Goblin Shaman channeling power into the horde).
    if ("team_buff_aura" in attacker.abilities and "team_buff_aura" not in attacker.used_abilities
            and enemies and any(a.alive and a is not attacker for a in enemies)):
        attacker.used_abilities.add("team_buff_aura")
        buffed = 0
        for ally in enemies:
            if ally.alive and ally is not attacker:
                ally.strength = int(ally.strength * TEAM_BUFF_AURA_ATK_MULT)
                buffed += 1
        log.append(f"  ▸ {attacker.log_name} channels power into the horde! {buffed} ally(s) hit harder now.")
        return True

    # "revive_ally" — once per battle, brings one fallen ally back at partial
    # Health (Skeleton Champion "reviving the fallen"). Needs the live
    # enemies list to find a dead ally and actually bring them back into the
    # turn order, not just a cosmetic log line.
    if ("revive_ally" in attacker.abilities and "revive_ally" not in attacker.used_abilities
            and enemies is not None and any((not a.alive) and a is not attacker for a in enemies)):
        attacker.used_abilities.add("revive_ally")
        fallen = [a for a in enemies if not a.alive and a is not attacker]
        target = max(fallen, key=lambda a: a.max_health)
        target.alive = True
        target.health = int(target.max_health * REVIVE_ALLY_HP_PCT)
        log.append(f"  ✟ {attacker.log_name} channels dark energy — {target.log_name} rises again! [{target.health}/{target.max_health}]")
        return True

    if "cleave" in attacker.abilities and random.random() < 0.20:
        log.append(f"  ✦ {attacker.log_name} cleaves at the whole party!")
        live_enemy_count = len([e for e in (enemies or []) if e.alive])
        for target in alive_heroes:
            damage, is_crit = calc_damage(attacker, target)
            damage = int(damage * 0.5)
            stacks = unimber_stacks(target, len(alive_heroes), live_enemy_count)
            damage = apply_unimber(damage, stacks)
            target.health -= damage
            crit_text = " CRIT!" if is_crit else ""
            unimber_tag = f"[Unimber ×{stacks}] " if stacks > 0 else ""
            log.append(f"    → {unimber_tag}{target.log_name} takes {damage}{crit_text} [{max(0,target.health)}/{target.max_health}]")
            if target.health <= 0:
                target.alive = False
                log.append(f"    ✦ {target.log_name} has fallen.")
                for h in alive_heroes:
                    if h.alive and h is not target:
                        morale_changes[h.id] = morale_changes.get(h.id, 0) - random.randint(8, 18)
                        stress_changes[h.id] = stress_changes.get(h.id, 0) + random.randint(5, 12)
        return True

    if "enrage" in attacker.abilities and "enrage" not in attacker.used_abilities and hlt_pct < 0.5:
        attacker.used_abilities.add("enrage")
        attacker.strength = int(attacker.strength * 1.4)
        log.append(f"  ✦ {attacker.log_name} flies into a rage! Strength sharply rises!")
        return False  # still takes a normal strength this turn, just buffed first

    if "crushing_blow" in attacker.abilities and "crushing_blow" not in attacker.used_abilities and hlt_pct < 0.7 and alive_heroes:
        attacker.used_abilities.add("crushing_blow")
        target = max(alive_heroes, key=lambda h: h.health)
        damage, is_crit = calc_damage(attacker, target)
        damage = int(damage * 2.2)
        stacks = unimber_stacks(target, len(alive_heroes), len([e for e in (enemies or []) if e.alive]))
        damage = apply_unimber(damage, stacks)
        unimber_tag = f"[Unimber ×{stacks}] " if stacks > 0 else ""
        target.health -= damage
        log.append(f"  ✦ {unimber_tag}{attacker.log_name} unleashes a CRUSHING BLOW on {target.log_name} for {damage} damage! [{max(0,target.health)}/{target.max_health}]")
        if target.health <= 0:
            target.alive = False
            log.append(f"    ✦ {target.log_name} has fallen.")
        return True

    if "last_stand" in attacker.abilities and "last_stand" not in attacker.used_abilities and hlt_pct < 0.2:
        attacker.used_abilities.add("last_stand")
        heal = int(attacker.max_health * 0.25)
        attacker.health = min(attacker.max_health, attacker.health + heal)
        log.append(f"  ✚ {attacker.log_name} makes a last stand, recovering {heal} Health! [{attacker.health}/{attacker.max_health}]")
        return True

    return False


# ═══ BOSS PHASES ══════════════════════════════════════════════════════
# Every full boss is a staged fight, not a fat stat block: at 66% and 33%
# HP it FIRES A PHASE — a structural change to the fight (adds, armor,
# ritual, fury...). Which phases a given floor's boss has is seeded by
# floor number, so a scouted boss's behavior is a fact, not a dice roll.
PHASE_2_KINDS = ["summon", "harden", "ritual", "quicken"]
PHASE_3_KINDS = ["fury", "shed_armor", "cataclysm", "second_summon"]
# Tower Awakens: WALL floors — bosses the community remembers. A third phase
# fires at 15% HP, and the full-party stat pad is doubled (see the Unimber
# boss-pad block in _resolve_combat_from_processed).
BOSS_WALL_FLOORS = {50, 70, 90}

def roll_boss_phases(floor_number: int) -> list:
    rng = random.Random(floor_number * 7919 + 5)
    phases = [{"threshold": 0.66, "kind": rng.choice(PHASE_2_KINDS)},
              {"threshold": 0.33, "kind": rng.choice(PHASE_3_KINDS)}]
    if floor_number in BOSS_WALL_FLOORS:
        third = rng.choice([k for k in PHASE_3_KINDS if k != phases[1]["kind"]])
        phases.append({"threshold": 0.15, "kind": third})
    return phases


def _fire_boss_phase(boss: CombatUnit, kind: str, enemies: list, all_units: list,
                     alive_heroes: list, log: list, floor_number: int,
                     morale_changes: dict, stress_changes: dict, turns: list = None, round_num: int = 0):
    log.append(f"  ═══ {boss.log_name} ENTERS A NEW PHASE ═══")
    if turns is not None:
        # Typed EVENT turn — the animated replay renders these as full-width
        # banners (and the phase horn fires), instead of the beat being
        # invisible outside the raw log.
        turns.append({"round": round_num, "event": "phase", "log": f"{boss.name} ENTERS A NEW PHASE",
                      "statuses": _status_snapshot(all_units)})
    if kind in ("summon", "second_summon"):
        count = 2 if kind == "summon" else 3
        pool = _enemy_pool_for_floor(floor_number)
        spawn_name = boss.spawn_template or (pool[0][0] if pool else "Goblin")
        base_id = 3000 + len([u for u in all_units if not u.is_hero]) * 7
        adds = [_make_swarm_add(spawn_name, floor_number, base_id + i) for i in range(count)]
        enemies.extend(adds)
        all_units.extend(adds)
        log.append(f"  ✦ The walls answer its call — {count}x {spawn_name} pour into the chamber!")
    elif kind == "harden":
        boss.defense = int(boss.defense * 1.3)
        boss.endurance = int(boss.endurance * 1.3)
        apply_status_effect(boss, "dmg_shield", 4, magnitude=0.35)
        log.append(f"  ◆ {boss.log_name}'s hide calcifies — blows glance off the new carapace.")
    elif kind == "ritual":
        healed = min(boss.max_health - boss.health, int(boss.max_health * 0.12))
        boss.health += max(0, healed)
        boss.status_effects = [e for e in boss.status_effects if e["type"] not in ("bleed", "poison", "burn")]
        log.append(f"  ✦ {boss.log_name} completes a profane ritual — wounds knit shut (+{max(0, healed)} HP).")
    elif kind == "quicken":
        boss.agility = int(boss.agility * 1.45)
        log.append(f"  ✦ {boss.log_name} sheds its slowness — it moves like something half its size.")
    elif kind == "fury":
        boss.strength = int(boss.strength * 1.35)
        boss.crit_chance = min(0.6, boss.crit_chance + 0.15)
        log.append(f"  ▸ {boss.log_name} abandons all defense of the mind — pure fury remains.")
        for h in alive_heroes:
            stress_changes[h.id] = stress_changes.get(h.id, 0) + random.randint(2, 5)
    elif kind == "shed_armor":
        boss.defense = max(1, int(boss.defense * 0.5))
        boss.endurance = max(1, int(boss.endurance * 0.5))
        boss.strength = int(boss.strength * 1.6)
        boss.agility = int(boss.agility * 1.3)
        log.append(f"  ✦ {boss.log_name} TEARS ITS OWN ARMOR AWAY — faster and deadlier, but exposed.")
    elif kind == "cataclysm":
        log.append(f"  ✦ {boss.log_name} unleashes a CATACLYSM upon the whole party!")
        for target in alive_heroes:
            damage, is_crit = calc_damage(boss, target)
            damage = int(damage * 0.8)
            damage = mitigate_special(target, damage, log)
            target.health -= damage
            log.append(f"    → {target.log_name} takes {damage} [{max(0, target.health)}/{target.max_health}]")
            if target.health <= 0 and target.death_save > 0:
                target.death_save -= 1
                target.health = 1
                log.append(f"  ✦ {target.log_name} refuses to fall! (Undying Will)")
            elif target.health <= 0:
                target.alive = False
                log.append(f"    ✦ {target.log_name} has fallen.")
                for h in alive_heroes:
                    if h.alive and h is not target:
                        morale_changes[h.id] = morale_changes.get(h.id, 0) - random.randint(8, 18)
                        stress_changes[h.id] = stress_changes.get(h.id, 0) + random.randint(5, 12)


def check_boss_phases(enemies: list, all_units: list, alive_heroes: list, log: list,
                      floor_number: int, morale_changes: dict, stress_changes: dict,
                      turns: list = None, round_num: int = 0):
    """End-of-round phase check for any phased unit that crossed a threshold."""
    for e in enemies:
        if not e.alive or not e.phases or not e.max_health:
            continue
        frac = e.health / e.max_health
        for ph in e.phases:
            key = str(ph["threshold"])
            if frac <= ph["threshold"] and key not in e.phases_fired:
                e.phases_fired.add(key)
                _fire_boss_phase(e, ph["kind"], enemies, all_units, alive_heroes, log,
                                 floor_number, morale_changes, stress_changes, turns, round_num)


# ═══ ELITE AFFIXES ════════════════════════════════════════════════════
# A slice of ordinary floors promotes one enemy to an ELITE with a named
# affix — the fight stops being homogeneous without needing a miniboss.
# Seeded per floor (same guarantee as composition: scout intel is real).
ELITE_AFFIXES = {
    "Armored":      {"desc": "hardened plates",   "def_mult": 1.6, "dr": 0.25},
    "Frenzied":     {"desc": "froth and speed",   "agi_mult": 1.5, "str_mult": 1.25},
    "Colossal":     {"desc": "towering bulk",     "hp_mult": 1.8},
    "Deadly":       {"desc": "hunts weak points", "crit": 0.25},
    "Regenerating": {"desc": "flesh reknits",     "regen": 0.05},
    "Warded":       {"desc": "spell-turning sigils", "mr": 0.4},
}
ELITE_HP_BONUS = 1.25  # every elite is also a bit tougher outright

def _apply_affix(target: CombatUnit, affix: str):
    a = ELITE_AFFIXES[affix]
    target.max_health = int(target.max_health * a.get("hp_mult", 1.0) * ELITE_HP_BONUS)
    target.health = target.max_health
    target.strength = int(target.strength * a.get("str_mult", 1.0))
    target.agility = int(target.agility * a.get("agi_mult", 1.0))
    target.defense = int(target.defense * a.get("def_mult", 1.0))
    target.endurance = int(target.endurance * a.get("def_mult", 1.0))
    target.dmg_reduction_pct = min(0.7, target.dmg_reduction_pct + a.get("dr", 0.0))
    target.crit_chance = min(0.6, target.crit_chance + a.get("crit", 0.0))
    target.magic_resist_pct = min(0.8, target.magic_resist_pct + a.get("mr", 0.0))
    if a.get("regen"):
        target.status_effects.append({"type": "regen", "rounds": 999, "magnitude": a["regen"], "source_id": None})
    target.name = f"{affix} {target.name}"
    target.log_name = f"[{target.name}]"


def maybe_elevate_elite(enemies: list, floor_number: int, rng: random.Random) -> list:
    """Chance-gated (seeded) promotion of the biggest enemy in a normal
    encounter to an affixed Elite. Tower Awakens: elite density climbs past
    floor 50, and past 80 elites can carry TWO affixes ('Armored Frenzied…')."""
    if not enemies:
        return enemies
    if floor_number > 50:
        chance = 0.25 + min(0.20, (floor_number - 50) * 0.004)
    else:
        chance = 0.15 + min(0.20, floor_number * 0.002)
    if rng.random() > chance:
        return enemies
    target = max(enemies, key=lambda e: e.max_health)
    affixes = sorted(ELITE_AFFIXES.keys())
    first = rng.choice(affixes)
    _apply_affix(target, first)
    if floor_number > 80 and rng.random() < 0.5:
        _apply_affix(target, rng.choice([a for a in affixes if a != first]))
    return enemies


# ═══ ENVIRONMENTAL FLOOR CONDITIONS ═══════════════════════════════════
# Some floors fight differently — a seeded, persistent condition that
# changes the fight's texture (team choice starts to matter per floor).
FLOOR_CONDITIONS = [
    {"key": "hallowed",   "name": "HALLOWED GROUND",  "desc": "old blessings linger — the party slowly mends",
     "hero_regen": 0.02},
    {"key": "miasma",     "name": "CREEPING MIASMA",  "desc": "foul air saps the quick — agility dampened",
     "hero_agi_mult": 0.88},
    {"key": "dark",       "name": "SUFFOCATING DARK", "desc": "eyes strain and nerves fray — precision suffers",
     "hero_crit_delta": -0.05, "hero_stress": 3},
    {"key": "bloodhaze",  "name": "BLOODHAZE",        "desc": "something in the air wants violence — ALL blades bite deeper",
     "both_str_mult": 1.15},
    {"key": "nullfield",  "name": "NULL FIELD",       "desc": "the Tower drinks mana here — regeneration halved",
     "hero_mana_regen_mult": 0.5},
    {"key": "echoes",     "name": "SHARPENED ECHOES", "desc": "every sound betrays a weakness — crits come easier to all",
     "both_crit_delta": 0.10},
]
FLOOR_CONDITION_CHANCE = 0.28

# Tower Awakens: past floor 60 a rolled condition turns SEVERE — every
# magnitude doubled (deltas doubled, multipliers pushed twice as far from 1.0).
SEVERE_CONDITION_FLOOR = 60

def _severify(cond: dict) -> dict:
    sev = dict(cond)
    sev["name"] = "SEVERE " + sev["name"]
    sev["severe"] = True
    for k, v in cond.items():
        if k.endswith("_mult"):
            sev[k] = round(1.0 + (v - 1.0) * 2, 3)      # 0.88 → 0.76, 1.15 → 1.30, 0.5 → 0.0-safe below
            if sev[k] <= 0:
                sev[k] = 0.25
        elif k.endswith("_delta") or k in ("hero_regen", "hero_stress"):
            sev[k] = v * 2
    return sev


def roll_floor_condition(floor_number: int) -> dict | None:
    """Seeded: floor N either always has this condition or never does."""
    rng = random.Random(floor_number * 7919 + 4)
    if rng.random() > FLOOR_CONDITION_CHANCE:
        return None
    cond = rng.choice(FLOOR_CONDITIONS)
    if floor_number > SEVERE_CONDITION_FLOOR:
        cond = _severify(cond)
    return cond

# ─── Status effects (Bleed / Poison / Stun / Freeze / Burn / Taunt) ────────
#
# Mirrors the isolated_rounds/bracing_rounds pattern already on CombatUnit:
# a duration that gets decremented every round, checked where relevant, and
# expires on its own. Bleed/Burn/Stun/Freeze/Taunt refresh duration on
# reapplication (no stacking — re-triggering just resets the clock, same as
# isolated_rounds/bracing_rounds being reassigned rather than added to).
# Poison is the one stacking type: each application is its own list entry,
# ticked independently, which is why status_effects is a list of dicts
# rather than a handful of flat counters.
BLEED_PCT_PER_ROUND = 0.04
BURN_PCT_PER_ROUND = 0.05
BURN_HEAL_REDUCTION = 0.5  # halves any heal received (regen tick, consumable, skill heal) while burning
BLIND_MISS_CHANCE = 0.6    # a blinded attacker whiffs this often on a basic attack
ON_ATTACK_MANA_GAIN = 5


def effective_dodge(target: CombatUnit) -> float:
    """A unit's dodge chance including any active Evasion status buff."""
    from services.skill_engine import status_magnitude
    return target.dodge_chance + status_magnitude(target, "evasion")


def mitigate_special(target: CombatUnit, damage: int, log: list) -> int:
    """Apply Invulnerability (nullifies) and flat absorb-Shields before a
    basic-attack hit lands. Returns the damage that actually gets through."""
    from services.skill_engine import has_status, absorb_with_shield
    if has_status(target, "invuln"):
        log.append(f"  ✦ {target.log_name} is invulnerable — the blow does nothing.")
        return 0
    # shell_armor: soaks most of a basic-attack hit until the shell cracks
    if "shell_armor" in getattr(target, "abilities", []) and "shell_armor" not in target.used_abilities:
        target.shell_hits = getattr(target, "shell_hits", 0) + 1
        damage = int(damage * (1 - SHELL_ARMOR_REDUCTION))
        if target.shell_hits >= SHELL_ARMOR_BREAK_HITS:
            target.used_abilities.add("shell_armor")
            log.append(f"  ◆ {target.log_name}'s shell cracks apart — it's vulnerable now!")
        else:
            log.append(f"  ◆ {target.log_name}'s shell absorbs the brunt of the blow. [{target.shell_hits}/{SHELL_ARMOR_BREAK_HITS}]")
    return absorb_with_shield(target, damage)


def _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_stats):
    """Build the ctx dict the trigger/death helpers expect from inside the
    basic-attack loop, so counters and on-kill fire on plain attacks too."""
    ctx = {
        "log": log, "turns": turns, "round_num": round_num, "all_units": all_units,
        "morale_changes": morale_changes, "kill_counts": kill_counts, "damage_stats": damage_stats,
    }
    ctx["fire_death"] = make_death_handler(ctx)
    return ctx
ON_HIT_MANA_GAIN = 8  # taking a hit grants slightly more than landing one — keeps tanks/frontline relevant to the mana economy, not just attackers

def apply_status_effect(unit: CombatUnit, eff_type: str, rounds: int, magnitude: float = 0.0, source_id: int = None):
    if eff_type == "poison":
        unit.status_effects.append({"type": "poison", "rounds": rounds, "magnitude": magnitude, "source_id": source_id})
        return
    existing = next((e for e in unit.status_effects if e["type"] == eff_type), None)
    if existing:
        existing["rounds"] = max(existing["rounds"], rounds)
        existing["magnitude"] = magnitude
    else:
        unit.status_effects.append({"type": eff_type, "rounds": rounds, "magnitude": magnitude, "source_id": source_id})

def has_status(unit: CombatUnit, eff_type: str) -> bool:
    return any(e["type"] == eff_type and e["rounds"] > 0 for e in unit.status_effects)

# Display-facing status chips the combat UI renders on each unit. Internal-only
# effect types (source bookkeeping, etc.) simply aren't mapped and are skipped.
_STATUS_DISPLAY = {
    # canonical Sigil-Library set (custom icons exist for these)
    "bleed": "BLEED", "poison": "POISON", "burn": "BURN", "freeze": "FREEZE",
    "frozen": "FREEZE", "stun": "STUN", "fear": "FEAR", "armor_break": "ARMOR BREAK",
    "taunting": "TAUNT", "shield": "SHIELD", "dmg_shield": "SHIELD", "enraged": "ENRAGED", "haste": "HASTE",
    # beyond the sheet — render as text chips
    "blind": "BLIND", "silence": "SILENCE", "regen": "REGEN", "dodge": "EVASION",
    "weaken": "WEAK",
}
def _status_snapshot(all_units):
    """Per-turn map of unit_id -> [status chip labels] for the combat UI, taken
    at the moment a turn is emitted so chips appear/expire as the fight plays."""
    snap = {}
    for u in all_units:
        seen = []
        for e in getattr(u, "status_effects", []):
            if e.get("rounds", 0) <= 0:
                continue
            t = e.get("type")
            label = None
            if t == "stat_mod":
                label = "BUFF" if e.get("delta", 0) >= 0 else "WEAK"
            else:
                label = _STATUS_DISPLAY.get(t)
            if label and label not in seen:
                seen.append(label)
        if seen:
            snap[u.id] = seen
    return snap

def tick_status_effects(unit: CombatUnit, log: list) -> int:
    """Applies this round's DOT damage for every active effect, decrements
    duration, prunes expired entries. Returns total damage dealt this tick
    so the caller can check for death the same way the existing regen-tick
    block already does. Bleed/Poison/Burn deliberately bypass calc_damage
    entirely — gear's dmg_reduction_pct does NOT mitigate them, the same way
    isolated_rounds' bonus-damage multiplier lives inside calc_damage while
    these ticks live outside it. Not an oversight — DOTs ignoring armor is
    the standard genre convention."""
    total = 0
    for eff in list(unit.status_effects):
        if eff["rounds"] <= 0:
            continue
        if eff["type"] == "bleed":
            dmg = max(1, int(unit.max_health * BLEED_PCT_PER_ROUND))
            unit.health -= dmg
            total += dmg
            log.append(f"  ▸ {unit.log_name} bleeds for {dmg} [{max(0, unit.health)}/{unit.max_health}]")
        elif eff["type"] == "poison":
            dmg = max(1, int(eff["magnitude"]))
            unit.health -= dmg
            total += dmg
            log.append(f"  ✦ {unit.log_name} takes {dmg} poison damage [{max(0, unit.health)}/{unit.max_health}]")
        elif eff["type"] == "burn":
            dmg = max(1, int(unit.max_health * BURN_PCT_PER_ROUND))
            unit.health -= dmg
            total += dmg
            log.append(f"  ▸ {unit.log_name} burns for {dmg} [{max(0, unit.health)}/{unit.max_health}]")
        elif eff["type"] == "regen":
            heal = max(1, int(unit.max_health * eff.get("magnitude", 0.05)))
            healed = apply_heal(unit, heal)
            if healed:
                log.append(f"  ✚ {unit.log_name} regenerates {healed} [{unit.health}/{unit.max_health}]")
        eff["rounds"] -= 1
        # A timed stat buff/debuff reverts precisely when it expires.
        if eff["rounds"] <= 0 and eff["type"] == "stat_mod":
            setattr(unit, eff["stat"], getattr(unit, eff["stat"]) - eff.get("delta", 0))
    unit.status_effects = [e for e in unit.status_effects if e["rounds"] > 0]
    return total

def is_action_locked(unit: CombatUnit) -> bool:
    """Stun and Freeze are kept as two distinct type strings (physical vs
    magical lockout) rather than merged into one, so a future cleanse/resist
    skill can target one without the other — but mechanically they do the
    exact same thing: skip the unit's turn entirely."""
    return has_status(unit, "stun") or has_status(unit, "freeze")

def apply_heal(unit: CombatUnit, amount: int) -> int:
    """Single chokepoint for every heal in combat (regen tick, consumables,
    skill heals) so Burn's reduced-healing penalty can't be missed at one
    of the sites. Returns the actual amount applied (post-Burn, post-cap)."""
    if has_status(unit, "burn"):
        amount = int(amount * BURN_HEAL_REDUCTION)
    before = unit.health
    unit.health = min(unit.max_health, unit.health + amount)
    return unit.health - before

# ─── Active skill casting (Mana-gated) ──────────────────────────────────
#
# Activates the SKILL_POOL "active" entries that previously had a cooldown
# defined but were never actually invoked anywhere — combat was 100%
# passive-stat-mod skills before this. A hero attempts a skill cast first
# each turn; only if none is castable does the existing basic-attack code
# below run.

def _select_castable_skill(attacker: CombatUnit) -> dict | None:
    """First skill (by list order) that's an active type this dispatcher
    knows how to execute, has no cooldown remaining, and the attacker can
    afford. List order is treated as meaningful priority, matching how
    skill lists are already ordered elsewhere in this codebase."""
    from services.skills_service import get_skill_mana_cost, is_skill_executable
    # Silence locks a unit out of active skills (but not basic attacks).
    if has_status(attacker, "silence"):
        return None
    for skill in attacker.skills:
        if not is_skill_executable(skill):
            continue
        sid = skill["id"]
        if attacker.skill_cooldowns.get(sid, 0) > 0:
            continue
        if attacker.mana < get_skill_mana_cost(skill):
            continue
        return skill
    return None

def fire_triggers(unit: CombatUnit, event: str, ctx: dict, other: CombatUnit = None):
    """Fire any passive conditional triggers a unit carries for `event`
    (on_hit_taken/on_dodge/on_kill/on_ally_death/on_low_hp). The trigger's
    actions run through the same generic engine, aimed by the trigger's own
    target mode (default: the `other` unit that caused the event, else self)."""
    if not unit.alive or not getattr(unit, "triggers", None):
        return
    from services.skill_engine import apply_actions, resolve_targets
    allies = [u for u in ctx["all_units"] if u.is_hero == unit.is_hero]
    enemies = [u for u in ctx["all_units"] if u.is_hero != unit.is_hero]
    for trig in unit.triggers:
        if trig.get("event") != event:
            continue
        if event == "on_hit_taken" and random.random() > trig.get("chance", 1.0):
            continue
        mode = trig.get("target")
        if mode:
            targets = resolve_targets(unit, mode, allies, enemies, trig.get("target_count", 1))
        elif other is not None and other.alive:
            targets = [other]
        else:
            targets = [unit]
        actions = trig.get("actions", [])
        if actions and targets:
            tctx = dict(ctx)
            tctx["skill_name"] = trig.get("name", event)
            ctx["log"].append(f"  ⟳ {unit.log_name}'s {trig.get('name', 'reaction')} triggers!")
            apply_actions(unit, actions, targets, tctx)


def make_death_handler(ctx: dict):
    """Returns a fire_death(attacker, target, execution=False) closure the
    generic skill engine calls whenever an action drops a unit — centralizes
    kill bookkeeping (kills, morale, on_kill / on_ally_death triggers) so the
    engine doesn't need to know combat internals."""
    def fire_death(attacker, target, execution=False):
        if not target.alive:
            return
        target.alive = False
        if attacker is not None:
            attacker.kills += 1
            ctx["kill_counts"][attacker.id] = ctx["kill_counts"].get(attacker.id, 0) + 1
        verb = "is executed" if execution else "falls"
        ctx["log"].append(f"    ✦ {target.log_name} {verb}.")
        # Morale swing for the target's enemies (the killers' side).
        for u in ctx["all_units"]:
            if u.alive and u.is_hero != target.is_hero:
                ctx["morale_changes"][u.id] = ctx["morale_changes"].get(u.id, 0) + random.randint(2, 5)
        # on_kill for the attacker; on_ally_death for the fallen unit's allies.
        if attacker is not None:
            fire_triggers(attacker, "on_kill", ctx, other=target)
        for u in ctx["all_units"]:
            if u.alive and u.is_hero == target.is_hero and u is not target:
                fire_triggers(u, "on_ally_death", ctx, other=target)
    return fire_death


def _execute_active_skill(attacker: CombatUnit, skill: dict, targets: list, all_units: list,
                           log: list, turns: list, round_num: int,
                           morale_changes: dict, kill_counts: dict, damage_dealt_stats: dict) -> bool:
    # Generic engine path — any skill authored in the composable actions
    # schema (see services/skill_engine.py) routes here first.
    from services.skill_engine import is_generic_skill, execute_generic_skill
    if is_generic_skill(skill):
        from services.skills_service import get_skill_mana_cost
        attacker.mana -= get_skill_mana_cost(skill)
        attacker.skill_cooldowns[skill["id"]] = skill.get("effect", {}).get("cooldown", skill.get("cooldown", 3))
        ctx = {
            "log": log, "turns": turns, "round_num": round_num, "all_units": all_units,
            "morale_changes": morale_changes, "kill_counts": kill_counts,
            "damage_stats": damage_dealt_stats,
        }
        ctx["fire_death"] = make_death_handler(ctx)
        allies = [u for u in all_units if u.is_hero == attacker.is_hero]
        enemies = [u for u in all_units if u.is_hero != attacker.is_hero]
        return execute_generic_skill(attacker, skill, allies, enemies, ctx)
    return _execute_active_skill_legacy(attacker, skill, targets, all_units,
                                         log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)


def _execute_active_skill_legacy(attacker: CombatUnit, skill: dict, targets: list, all_units: list,
                           log: list, turns: list, round_num: int,
                           morale_changes: dict, kill_counts: dict, damage_dealt_stats: dict) -> bool:
    """Dispatches on effect keys already defined in SKILL_POOL. Deducts mana
    and starts the cooldown only once we're committed to actually firing —
    is_skill_executable already filtered out anything this function can't
    handle, so every call here is expected to return True."""
    from services.skills_service import get_skill_mana_cost
    eff = skill.get("effect", {})
    attacker.mana -= get_skill_mana_cost(skill)
    attacker.skill_cooldowns[skill["id"]] = skill.get("cooldown", 3)

    if "taunt_duration" in eff:
        apply_status_effect(attacker, "taunting", eff["taunt_duration"])
        log.append(f"  ◆ {attacker.log_name} uses {skill['name']} — taunting all enemies!")
        return True

    if "team_dmg_reduce" in eff:
        for ally in [u for u in all_units if u.is_hero and u.alive and not u.is_npc]:
            apply_status_effect(ally, "dmg_shield", eff.get("duration", 2), magnitude=eff["team_dmg_reduce"])
        log.append(f"  ◆ {attacker.log_name} casts {skill['name']} — the team braces!")
        return True

    if "heal_pct" in eff:
        candidates = [u for u in all_units if u.is_hero and u.alive]
        lowest = min(candidates, key=lambda u: u.health / u.max_health, default=None) if candidates else None
        if lowest:
            heal = apply_heal(lowest, int(lowest.max_health * eff["heal_pct"]))
            log.append(f"  ✚ {attacker.log_name} uses {skill['name']} on {lowest.log_name} for {heal} [{lowest.health}/{lowest.max_health}]")
        else:
            log.append(f"  {attacker.log_name} uses {skill['name']}, but no one needs healing.")
        return True

    if "enemy_stun" in eff:
        for target in targets:
            apply_status_effect(target, "stun", eff["enemy_stun"])
        log.append(f"  ✦ {attacker.log_name} uses {skill['name']} — enemies stunned!")
        return True

    if "self_heal_pct" in eff:
        heal = apply_heal(attacker, int(attacker.max_health * eff["self_heal_pct"]))
        log.append(f"  ✚ {attacker.log_name} uses {skill['name']} — recovers {heal} [{attacker.health}/{attacker.max_health}]")
        return True

    if "team_buff_pct" in eff:
        stat = eff.get("buff_stat", "strength")
        allies = [u for u in all_units if u.is_hero and u.alive and not u.is_npc]
        for ally in allies:
            setattr(ally, stat, int(getattr(ally, stat) * (1 + eff["team_buff_pct"])))
        log.append(f"  ✦ {attacker.log_name} uses {skill['name']} — the team's {stat} surges for the rest of the fight!")
        return True

    if "cleanse_self" in eff:
        before = len(attacker.status_effects)
        attacker.status_effects = [s for s in attacker.status_effects if s["type"] not in ("bleed", "poison", "stun", "freeze", "burn")]
        cleared = before - len(attacker.status_effects)
        log.append(f"  ✦ {attacker.log_name} uses {skill['name']}" + (f" — clears {cleared} affliction(s)." if cleared else ", but has nothing to cleanse."))
        return True

    if "revive_pct" in eff:
        fallen = [u for u in all_units if u.is_hero and not u.alive and not u.is_npc]
        if fallen:
            target = max(fallen, key=lambda u: u.max_health)
            target.alive = True
            target.health = int(target.max_health * eff["revive_pct"])
            log.append(f"  ✟ {attacker.log_name} uses {skill['name']} — {target.log_name} returns to the fight! [{target.health}/{target.max_health}]")
        else:
            log.append(f"  {attacker.log_name} uses {skill['name']}, but no one has fallen.")
        return True

    if "dmg_pct" in eff:
        if eff.get("aoe"):
            chosen = list(targets)
        else:
            n_targets = eff.get("multi_target", 1)
            chosen = random.sample(targets, min(n_targets, len(targets))) if targets else []
        total_dealt = 0
        for target in chosen:
            damage, is_crit = calc_damage(attacker, target)
            damage = int(damage * eff["dmg_pct"])
            if eff.get("ignore_def"):
                power = attacker.intelligence if attacker.power_stat == "intelligence" else attacker.strength
                damage = int(power * eff["dmg_pct"])
            if eff.get("guaranteed_crit"):
                damage = int(damage * 1.5)
                is_crit = True
            if "execute_bonus_pct" in eff and target.health / target.max_health <= eff.get("execute_threshold", 0.30):
                damage = int(damage * (1 + eff["execute_bonus_pct"]))
            target.health -= damage
            total_dealt += damage
            damage_dealt_stats[attacker.id] = damage_dealt_stats.get(attacker.id, 0) + damage
            crit_text = " CRIT!" if is_crit else ""
            log_msg = f"  ✦ {attacker.log_name} uses {skill['name']} on {target.log_name} for {damage}{crit_text} [{max(0, target.health)}/{target.max_health}]"
            log.append(log_msg)
            turns.append({"round": round_num, "attacker_id": attacker.id, "target_id": target.id, "damage": damage, "is_crit": is_crit, "target_hp": max(0, target.health), "log": log_msg, "attacker_mana": attacker.mana, "target_mana": target.mana, "skill_name": skill["name"], "statuses": _status_snapshot(all_units)})
            if target.health <= 0:
                target.alive = False
                attacker.kills += 1
                kill_counts[attacker.id] = kill_counts.get(attacker.id, 0) + 1
                log.append(f"    ✦ {target.log_name} falls.")
                for h in all_units:
                    if h.is_hero and h.alive:
                        morale_changes[h.id] = morale_changes.get(h.id, 0) + random.randint(2, 5)
        if "lifesteal_pct" in eff and total_dealt > 0:
            healed = apply_heal(attacker, int(total_dealt * eff["lifesteal_pct"]))
            log.append(f"    ▸ {attacker.log_name} drains {healed} Health from the kill.")
        return True

    return False  # should be unreachable — is_skill_executable already filtered this out

def resolve_hero_stats(heroes: list[dict]) -> list[dict]:
    """Applies level scaling → class modifiers → synergy → equipment →
    legacy bonuses → relics → base-floor LP → bonds → passive skills/traits,
    in that order. This is the one full pipeline that turns raw DB hero rows
    into the fully-resolved stat dicts combat actually fights with. Also
    used standalone (not followed by a fight) to build the snapshot a player
    submits to the Arena server — see routers/arena.py's snapshot endpoint
    and run_combat's skip_stat_pipeline param, which lets the Arena server
    accept that snapshot back in without re-deriving it (it has no DB access
    to do so anyway)."""
    processed = []

    # Calculate synergies on active team
    synergy_counts = {}
    for h in heroes:
        sg = h.get("synergy_group")
        if sg:
            synergy_counts[sg] = synergy_counts.get(sg, 0) + 1
    # Fetch relics
    try:
        from services.relic_service import get_all_relics, apply_relic_stats
        relics = get_all_relics()
    except Exception:
        relics = []

    # Fetch bonds
    try:
        from services.bonds_service import get_team_bonds_multiplier
        hero_ids = [h["id"] for h in heroes]
        bond_totals = get_team_bonds_multiplier(hero_ids)
    except Exception:
        bond_totals = {h["id"]: 0 for h in heroes}

    # Roster-wide endgame buffs (mounted Reliquary trophies + Transcendence
    # Core infusions) — fetched once per pipeline run, applied per hero below.
    try:
        from services.endgame_service import get_global_empowerment
        from database import db as _db
        with _db() as _conn:
            empower = get_global_empowerment(_conn)
    except Exception:
        empower = {}

    # Athenaeum research (completed discipline/confluence nodes) — same
    # roster-wide % shape as empowerment, fetched once per pipeline run.
    try:
        from services.athenaeum_service import get_research_bonuses
        research = get_research_bonuses()
    except Exception:
        research = {}

    # Pre-pass for support class buffs (Tactician, Scout, etc)
    team_atk_mult = 1.0
    team_end_mult = 1.0
    team_spd_mult = 1.0
    for h in heroes:
        mods = apply_class_combat_modifiers(h)
        if "team_atk_mult" in mods: team_atk_mult *= mods["team_atk_mult"]
        if "team_end_mult" in mods: team_end_mult *= mods["team_end_mult"]
        if "team_spd_mult" in mods: team_spd_mult *= mods["team_spd_mult"]

    for h in heroes:
        scaled = apply_level_to_stats(h)
        modified = apply_class_combat_modifiers(scaled)

        # Apply team class buffs
        if team_atk_mult > 1.0: modified["strength"] = int(modified["strength"] * team_atk_mult)
        if team_end_mult > 1.0: modified["endurance"] = int(modified.get("endurance", modified.get("defense", 5)) * team_end_mult)
        if team_spd_mult > 1.0: modified["agility"] = int(modified["agility"] * team_spd_mult)

        # Apply Depression Penalty (-75% stats)
        if modified.get("condition") == "Depressed":
            modified["strength"] = max(1, int(modified["strength"] * 0.25))
            modified["agility"] = max(1, int(modified["agility"] * 0.25))
            modified["intelligence"] = max(1, int(modified["intelligence"] * 0.25))
            modified["defense"] = max(1, int(modified.get("defense", 5) * 0.25))
            modified["max_health"] = max(1, int(modified["max_health"] * 0.25))
            modified["health"] = min(modified["health"], modified["max_health"])

        # Apply synergy buff
        sg = modified.get("synergy_group")
        if sg and synergy_counts.get(sg, 0) > 1:
            multiplier = 1.0 + (0.05 * synergy_counts[sg])
            modified["max_health"] = int(modified["max_health"] * multiplier)
            modified["health"] = modified["max_health"]
            modified["strength"] = int(modified["strength"] * multiplier)
            modified["intelligence"] = int(modified["intelligence"] * multiplier)
            modified["defense"] = int(modified.get("defense", 5) * multiplier)
            modified["agility"] = int(modified["agility"] * multiplier)

        # Apply equipment bonuses
        try:
            from services.equipment_service import apply_equipment_stats
            modified = apply_equipment_stats(modified)
        except Exception:
            pass

        # Equipment set bonuses — must run after apply_equipment_stats so its
        # % bonuses stack on top of gear's own already-resolved numbers.
        try:
            from services.equipment_service import apply_set_bonuses
            modified = apply_set_bonuses(modified)
        except Exception:
            pass

        # Apply legacy bonuses
        try:
            from services.legacy_service import apply_legacy_bonuses
            modified = apply_legacy_bonuses(modified)
        except Exception:
            pass

        # Apply relic stats
        if relics:
            modified = apply_relic_stats(modified, relics)

        # Apply Base Floor LP stats
        try:
            from services.base_service import get_floor_lp
            from database import db
            with db() as conn:
                lp_data = get_floor_lp(conn, modified.get("base_floor", 1))
                lp_mult = 1.0 + (lp_data["stat_bonus_pct"] / 100.0)
                # 6 stats, not 7 -- Endurance already determines Health
                # (see health_from_endurance in gacha_service.py), so
                # buffing Health on top of Endurance here would double-count it.
                modified["strength"] = int(modified["strength"] * lp_mult)
                modified["intelligence"] = int(modified["intelligence"] * lp_mult)
                modified["agility"] = int(modified["agility"] * lp_mult)
                modified["endurance"] = int(modified["endurance"] * lp_mult)
                modified["willpower"] = int(modified["willpower"] * lp_mult)
                modified["luck"] = int(modified["luck"] * lp_mult)
        except Exception:
            pass

        # Apply support-class boons (star-scaled facility output — see
        # services/support_service.py): the Chef's feast buffs the six stats
        # of EVERY deployed hero; the Medic's field dressing pads max HP.
        # This is the core of the "supports enable progression" rebalance.
        try:
            from services.support_service import get_support_effects
            fx = get_support_effects()
            # Chef · Sous Chef (Grand Feast) / unevolved: +% ALL six stats.
            feast = fx.get("feast_stat_pct", 0)
            if feast:
                f_mult = 1.0 + feast / 100.0
                for k in ("strength", "intelligence", "agility", "endurance", "willpower", "luck"):
                    modified[k] = int(modified[k] * f_mult)
            # Chef · Butcher (War Rations): offense-skewed — strength + crit only.
            war_str = fx.get("war_str_pct", 0)
            if war_str:
                modified["strength"] = int(modified["strength"] * (1.0 + war_str / 100.0))
            war_crit = fx.get("war_crit", 0)
            if war_crit:
                modified["crit_chance"] = modified.get("crit_chance", 0.05) + war_crit
            # Tactician · Commander (Battle Formation): +% all six combat stats.
            formation = fx.get("formation_pct", 0)
            if formation:
                fm = 1.0 + formation / 100.0
                for k in ("strength", "intelligence", "agility", "endurance", "willpower", "luck"):
                    modified[k] = int(modified[k] * fm)
            # Tactician · Advisor (War Council): rage + crit — strength & crit chance.
            adv_str = fx.get("advisor_str_pct", 0)
            if adv_str:
                modified["strength"] = int(modified["strength"] * (1.0 + adv_str / 100.0))
            adv_crit = fx.get("advisor_crit", 0)
            if adv_crit:
                modified["crit_chance"] = modified.get("crit_chance", 0.05) + adv_crit
            # Blacksmith · Armorer (Tempered Plate): team flat damage-reduction.
            smith_dr = fx.get("smith_dmg_reduction_pct", 0)
            if smith_dr:
                modified["dmg_reduction_pct"] = min(0.85, modified.get("dmg_reduction_pct", 0.0) + smith_dr)
            # Medic · Surgeon (Field Surgery) / unevolved: +% max HP entering fights.
            shield = fx.get("medic_shield_pct", 0)
            if shield and modified.get("max_health"):
                bonus_hp = int(modified["max_health"] * shield / 100.0)
                modified["max_health"] += bonus_hp
                modified["health"] = min(modified["health"] + bonus_hp, modified["max_health"])
            # Medic · Herbalist (Regen Salves): per-round % max-HP regen in combat.
            # Master Chef's well-fed regen (capstone) rides the same stat.
            regen = fx.get("medic_regen_pct", 0) + fx.get("chef_wellfed_regen", 0)
            if regen:
                modified["regen_pct"] = modified.get("regen_pct", 0.0) + regen
            # Alchemist · Poisoner (Combat Draughts): a battle elixir in every pack.
            draught = fx.get("alch_draught_pct", 0)
            if draught:
                dm = 1.0 + draught / 100.0
                modified["strength"] = int(modified["strength"] * dm)
                modified["intelligence"] = int(modified["intelligence"] * dm)
            # Priest · Chaplain (Blessing): physical + magic resistance.
            bless = fx.get("blessing_resist_pct", 0)
            if bless:
                modified["physical_resist_pct"] = modified.get("physical_resist_pct", 0.0) + bless
                modified["magic_resist_pct"] = modified.get("magic_resist_pct", 0.0) + bless
            # Priest · Oracle (Guardian Fate): death-save charges (Undying Will) —
            # the hero refuses a fatal blow, dropping to 1 HP; the existing
            # death_save revive path in the turn loop consumes them.
            saves = fx.get("priest_death_saves", 0)
            if saves:
                modified["death_save"] = modified.get("death_save", 0) + saves
        except Exception:
            pass

        # Apply endgame empowerment: mounted Reliquary trophies (per-stat %)
        # + Transcendence Core infusions (+1% ALL stats per infusion).
        if empower:
            all_mult = 1.0 + empower.get("all_stats_pct", 0) / 100.0
            def _emp(stat_key, buff_key):
                if stat_key in modified:
                    mult = all_mult * (1.0 + empower.get(buff_key, 0) / 100.0)
                    if mult != 1.0:
                        modified[stat_key] = int(modified[stat_key] * mult)
            _emp("strength", "atk_pct")
            _emp("intelligence", "int_pct")
            _emp("agility", "agi_pct")
            _emp("endurance", "def_pct")
            _emp("willpower", "def_pct")
            _emp("luck", "luck_pct")
            hp_mult = all_mult * (1.0 + empower.get("hp_pct", 0) / 100.0)
            if hp_mult != 1.0 and "max_health" in modified:
                modified["max_health"] = int(modified["max_health"] * hp_mult)
                modified["health"] = min(modified["health"], modified["max_health"])

        # Apply Athenaeum research — mirrors the empowerment block above
        # (def_pct covers endurance + willpower, all_pct covers everything).
        if research:
            r_all = 1.0 + research.get("all_pct", 0) / 100.0
            def _res(stat_key, buff_key):
                if stat_key in modified:
                    mult = r_all * (1.0 + research.get(buff_key, 0) / 100.0)
                    if mult != 1.0:
                        modified[stat_key] = int(modified[stat_key] * mult)
            _res("strength", "atk_pct")
            _res("intelligence", "int_pct")
            _res("agility", "agi_pct")
            _res("endurance", "def_pct")
            _res("willpower", "def_pct")
            _res("luck", "luck_pct")
            r_hp = r_all * (1.0 + research.get("hp_pct", 0) / 100.0)
            if r_hp != 1.0 and "max_health" in modified:
                modified["max_health"] = int(modified["max_health"] * r_hp)
                modified["health"] = min(modified["health"], modified["max_health"])

        # Apply bond stats
        bond_lvl = bond_totals.get(modified["id"], 0)
        if bond_lvl > 0:
            bond_mult = 1.0 + (0.01 * bond_lvl)
            modified["max_health"] = int(modified["max_health"] * bond_mult)
            modified["health"] = min(modified["max_health"], modified["health"])
            modified["strength"] = int(modified["strength"] * bond_mult)
            modified["intelligence"] = int(modified["intelligence"] * bond_mult)
            modified["agility"] = int(modified["agility"] * bond_mult)

        # Apply passive skills and traits
        hero_skills = []
        hero_traits = []
        if "skills" in h and h["skills"]:
            from services.skills_service import apply_passive_skills
            hero_skills = json.loads(h.get("skills", "[]")) if isinstance(h.get("skills"), str) else h.get("skills", [])
            modified = apply_passive_skills(modified, hero_skills)

        if "traits" in h and h["traits"]:
            from services.skills_service import apply_passive_skills
            hero_traits = json.loads(h.get("traits", "[]")) if isinstance(h.get("traits"), str) else h.get("traits", [])
            # Traits use the exact same effect dict structure as passive skills!
            modified = apply_passive_skills(modified, hero_traits)

        # Apply equipped relics (Seals/Runes) — same passive effect shape as skills
        from services.relics_service import get_hero_relics
        from services.skills_service import apply_passive_skills
        hero_relics = get_hero_relics(h["id"])
        if hero_relics:
            modified = apply_passive_skills(modified, hero_relics)
        modified["regen_pct"] = modified.get("regen_pct", 0.0)

        # Weapon Art — a free bonus active granted only while a matching-type
        # weapon is equipped (see class_service.get_weapon_affinity and
        # skills_service.WEAPON_ART_SKILLS). Equipped weapon comes from
        # modified["equipment"], stashed there by apply_equipment_stats above.
        equipped_weapon = next((eq for eq in modified.get("equipment", []) if eq.get("type") == "Weapon"), None)
        if equipped_weapon and equipped_weapon.get("weapon_type"):
            from services.class_service import get_weapon_affinity
            from services.skills_service import get_weapon_art_skill
            affinity = get_weapon_affinity(modified.get("hero_class", "Classless"))
            if equipped_weapon["weapon_type"] in affinity:
                art = get_weapon_art_skill(equipped_weapon["weapon_type"])
                if art and art["id"] not in {s["id"] for s in hero_skills}:
                    hero_skills.append(art)

        # Remove raw string payload to avoid confusion later, but keep as python list for UI/Combat logic if needed
        if "skills" in modified:
            modified["_skills"] = hero_skills
            del modified["skills"]
        if "traits" in modified:
            modified["_traits"] = hero_traits
            del modified["traits"]
        processed.append(modified)

    return processed


def run_combat(heroes: list[dict], floor_number: int, is_boss: bool = False, is_miniboss: bool = False, zone_theme: str = "", boss_data_override=_UNSET, enemy_count_override: int = None, difficulty_mult: float = 1.0, preset_enemies: list = None, outer_conn=None, skip_stat_pipeline: bool = False, family_override: dict = None, is_survival_swarm: bool = False, turn_limit: int = None, available_consumables: list = None, is_escort: bool = False, is_ambush: bool = False, is_blitz: bool = False, cursed_debuff: dict = None, miniboss_variant: str = None, is_retrieval: bool = False, runner_id: int = None) -> dict:
    log = []
    turns = []
    morale_changes = {h["id"]: 0 for h in heroes}
    kill_counts = {h["id"]: 0 for h in heroes}
    stress_changes = {h["id"]: 0 for h in heroes}

    # skip_stat_pipeline lets a caller hand in hero dicts that are *already*
    # fully resolved (level/class/equipment/relic/bond/base-floor bonuses all
    # baked in) instead of raw DB rows — used by the Arena server, which has
    # no access to either player's local save/equipment/relics to compute
    # this pipeline itself. The caller (the player's own local backend) runs
    # this exact pipeline normally for a Tower floor, then ships the
    # resulting dict over the wire instead of re-deriving it remotely.
    if skip_stat_pipeline:
        processed = heroes
        result = _resolve_combat_from_processed(processed, floor_number, is_boss, is_miniboss, zone_theme,
                                                 boss_data_override, enemy_count_override, difficulty_mult,
                                                 preset_enemies, outer_conn, log, turns,
                                                 morale_changes, kill_counts, stress_changes,
                                                 family_override, is_survival_swarm, turn_limit, available_consumables,
                                                 is_escort, is_ambush, is_blitz, cursed_debuff,
                                                 miniboss_variant, is_retrieval, runner_id)
        result.pop("_avg_luck", None)
        return result

    processed = resolve_hero_stats(heroes)

    result = _resolve_combat_from_processed(processed, floor_number, is_boss, is_miniboss, zone_theme,
                                             boss_data_override, enemy_count_override, difficulty_mult,
                                             preset_enemies, outer_conn, log, turns,
                                             morale_changes, kill_counts, stress_changes,
                                             family_override, is_survival_swarm, turn_limit, available_consumables,
                                             is_escort, is_ambush, is_blitz, cursed_debuff,
                                             miniboss_variant, is_retrieval, runner_id,
                                             apply_support_boons=True)
    _apply_combat_drops(result, floor_number, is_boss, is_miniboss, outer_conn)
    return result


def _resolve_combat_from_processed(processed, floor_number, is_boss, is_miniboss, zone_theme,
                                    boss_data_override, enemy_count_override, difficulty_mult,
                                    preset_enemies, outer_conn, log, turns,
                                    morale_changes, kill_counts, stress_changes,
                                    family_override=None, is_survival_swarm=False, turn_limit=None,
                                    available_consumables=None, is_escort=False, is_ambush=False,
                                    is_blitz=False, cursed_debuff=None,
                                    miniboss_variant=None, is_retrieval=False, runner_id=None,
                                    apply_support_boons=False):
    """The CombatUnit-construction-and-turn-loop core of run_combat, split out
    of the stat-resolution pipeline above it so a caller that already has
    fully-resolved hero dicts (no local DB to re-derive equipment/relic/bond/
    base-floor bonuses from — see run_combat's skip_stat_pipeline) can run a
    fight directly without re-deriving anything. Returns the same result dict
    run_combat used to build inline; drop generation is applied by the caller
    afterward (_apply_combat_drops), not here, since Arena fights skip drops
    entirely."""
    from services.gacha_service import mana_from_stats
    from services.skills_service import get_skill_mana_cost

    combatants_heroes = []
    construct_id = -100
    for h in processed:
        hero_max_mana = mana_from_stats(h["intelligence"], h.get("willpower", 6))
        poison_on_hit = None
        for s in h.get("_skills", []):
            eff = s.get("effect", {})
            if "poison_pct" in eff:
                poison_on_hit = {"pct": eff["poison_pct"], "duration": eff.get("poison_duration", 3)}
                break
        hero_unit = CombatUnit(
            id=h["id"], name=h["name"],
            level=h.get("level", 1),
            health=h["health"], max_health=h["max_health"],
            strength=h["strength"], intelligence=h["intelligence"],
            agility=h["agility"], morale=h["morale"], stress=h["stress"],
            defense=h.get("defense", 5), endurance=h.get("endurance", h.get("defense", 5)),
            willpower=h.get("willpower", 6), luck=h.get("luck", 5),
            power_stat=h.get("power_stat", "strength"),
            dmg_reduction_pct=h.get("dmg_reduction_pct", 0.0),
            physical_resist_pct=h.get("physical_resist_pct", 0.0),
            magic_resist_pct=h.get("magic_resist_pct", 0.0),
            trauma=h.get("trauma", 0),
            hero_class=h.get("hero_class", "Classless"),
            is_ranged=h.get("is_ranged", False),
            is_aoe=h.get("is_aoe", False),
            has_construct=h.get("has_construct", False),
            crit_chance=h.get("crit_chance", 0.05),
            dodge_chance=h.get("dodge_chance", 0.0),
            fear_immune=h.get("fear_immune", False),
            death_save=h.get("death_save", 0),
            armor_pen=h.get("armor_pen", 0.0),
            skills=h.get("_skills", []),
            portrait_path=h.get("portrait_path", ""),
            talent=talent_score(h),
            regen_pct=h.get("regen_pct", 0.0),
            hero_star=get_hero_star(h),
            battle_tendency=h.get("battle_tendency") or "Stoic",
            ego_type=h.get("ego_type") or "",
            ego_patience=h.get("ego_patience", 100) if h.get("ego_patience") is not None else 100,
            is_team_leader=bool(h.get("is_team_leader")),
            team_position=h.get("team_position", 0) or 0,
            equipped_consumable=h.get("equipped_consumable"),
            max_mana=hero_max_mana,
            mana=hero_max_mana // 2,  # start fights at 50%, not empty or full
            mana_regen_per_turn=max(1, hero_max_mana // 10),
            poison_on_hit=poison_on_hit,
            triggers=h.get("_triggers", []),
        )
        combatants_heroes.append(hero_unit)
        
        # Summon construct if the hero has the has_construct flag
        if h.get("has_construct"):
            c_hp = int(h["max_health"] * 1.5)
            c_atk = int(h["strength"] * 0.8)
            c_def = int(h.get("defense", 5) * 1.5)
            c_spd = int(h["agility"] * 0.7)
            construct_unit = CombatUnit(
                id=construct_id, name=f"{h['name']}'s Construct",
                level=h.get("level", 1),
                health=c_hp, max_health=c_hp, strength=c_atk, intelligence=0, defense=c_def, endurance=c_def, agility=c_spd,
                morale=100, stress=0, hero_class="Construct", fear_immune=True
            )
            combatants_heroes.append(construct_unit)
            construct_id -= 1
            log.append(f"  {hero_unit.name} deploys a massive Construct to the frontline!")

    # Retrieval Mission — mark the player-designated Runner. They're a real
    # deployed hero (unlike the escort NPC) who counts for rewards/morale,
    # but they spend every combat turn channeling the objective instead of
    # attacking, and their death fails the floor outright.
    runner_unit = None
    if is_retrieval:
        runner_unit = next((h for h in combatants_heroes
                            if h.id == runner_id and h.hero_class != "Construct"), None)
        if runner_unit is None:
            # The router validates the designation upfront; this fallback only
            # guards direct callers — grab the most evasive hero rather than crash.
            runner_unit = max((h for h in combatants_heroes if h.hero_class != "Construct"),
                              key=lambda u: u.agility + u.dodge_chance * 100)
        runner_unit.is_runner = True

    # Generate enemies — difficulty is purely floor-based, not adaptive to team strength.
    if is_survival_swarm:
        if preset_enemies:
            enemies = preset_enemies
        else:
            enemies = make_swarm_miniboss_encounter(floor_number)
        log.append(f"═══ SURVIVAL FLOOR {floor_number} ═══")
        log.append(f"  An overwhelming swarm pours in. Survive {turn_limit or SURVIVAL_TURN_LIMIT} rounds!")
    elif is_boss or is_miniboss:
        if preset_enemies:
            enemies = preset_enemies
        elif is_miniboss and miniboss_variant in ("behemoth", "assassin", "twins", "mirror"):
            enemies = make_miniboss_variant(miniboss_variant, floor_number, zone_theme, processed)
        else:
            enemies = make_boss(floor_number, zone_theme, is_miniboss, boss_data_override=boss_data_override, family_override=family_override)
        # Boss stat padding — mirrors Unimber from the enemy side: a boss
        # facing a full 5-hero team is up against far more sustained
        # pressure than facing 1, so it gets padded HP/defense rather than
        # staying stat-static while the player side scales with team size.
        real_hero_count = len([h for h in combatants_heroes if h.hero_class != "Construct"])
        if is_boss and real_hero_count > 1:
            pad_n = min(real_hero_count - 1, UNIMBER_BOSS_PAD_MAX_HEROES)
            # WALL floors (Tower Awakens): the pad is doubled — these bosses
            # are meant to stop climbs cold and be remembered by name.
            wall_mult = 2.0 if floor_number in BOSS_WALL_FLOORS else 1.0
            hp_mult = 1.0 + UNIMBER_BOSS_HP_PAD_PER_HERO * pad_n * wall_mult
            def_mult = 1.0 + UNIMBER_BOSS_DEF_PAD_PER_HERO * pad_n * wall_mult
            for boss_unit in enemies:
                boss_unit.max_health = int(boss_unit.max_health * hp_mult)
                boss_unit.health = boss_unit.max_health
                boss_unit.endurance = int(boss_unit.endurance * def_mult)
                boss_unit.defense = int(boss_unit.defense * def_mult)
            log.append(f"  ✦ Boss Empowered: full party detected (+{int((hp_mult - 1) * 100)}% HP, +{int((def_mult - 1) * 100)}% DEF).")
            if wall_mult > 1.0:
                log.append(f"  ═ THE TOWER'S WALL — floor {floor_number}'s warden does not intend to let anyone pass.")
                turns.append({"round": 0, "event": "wall", "log": f"THE TOWER'S WALL — floor {floor_number}'s warden does not intend to let anyone pass"})
        log.append(f"═══ {'MINIBOSS' if is_miniboss else 'BOSS'} FLOOR {floor_number} ═══")
        log.append(f"  {enemies[0].name} emerges from the darkness.")
    else:
        if preset_enemies:
            enemies = preset_enemies
        else:
            enemies = make_enemies(floor_number, count=enemy_count_override, difficulty_mult=difficulty_mult)

    if is_retrieval:
        log.append(f"✦ RETRIEVAL MISSION — floor {floor_number}")
        log.append(f"  {runner_unit.name} is the designated Runner: they will work the objective, not fight.")
        log.append(f"  Hold the line for {turn_limit or RETRIEVAL_TURN_LIMIT} rounds while the Runner finishes the job.")

    if cursed_debuff:
        for h in combatants_heroes:
            if h.hero_class == "Construct":
                continue
            if cursed_debuff.get("poison_rounds"):
                apply_status_effect(h, "poison", cursed_debuff["poison_rounds"], magnitude=cursed_debuff.get("poison_magnitude", 0.06))
            if cursed_debuff.get("hp_pct_loss"):
                h.max_health = max(1, int(h.max_health * (1 - cursed_debuff["hp_pct_loss"])))
                h.health = min(h.health, h.max_health)
        log.append("▸ CURSED GROUND — the team stumbled in already weakened.")

    initial_state = {
        "is_boss": is_boss,
        "is_miniboss": is_miniboss,
        "is_survival_swarm": is_survival_swarm,
        "is_retrieval": is_retrieval,
        "runner_id": runner_unit.id if runner_unit else None,
        "turn_limit": ((turn_limit or SURVIVAL_TURN_LIMIT) if is_survival_swarm
                       else (turn_limit or RETRIEVAL_TURN_LIMIT) if is_retrieval else None),
        "heroes": [
            {"id": h.id, "name": h.name, "hero_class": h.hero_class, "max_health": h.max_health, "health": h.health,
             "portrait_path": h.portrait_path, "hero_star": h.hero_star, "level": h.level,
             "power_stat": h.power_stat, "is_ranged": h.is_ranged, "team_position": h.team_position,
             "is_team_leader": h.is_team_leader,
             "max_mana": h.max_mana, "mana": h.mana}
            for h in combatants_heroes
        ],
        "enemies": [
            {"id": e.id, "name": e.name, "max_health": e.max_health, "health": e.health, "portrait_path": e.portrait_path, "level": e.level}
            for e in enemies
        ],
        # How many of the enemies (front-of-list) are the targeted-first
        # front line — the UI splits its enemy formation on this so the
        # visual matches the actual targeting rule.
        "enemy_frontline": _enemy_frontline_n(len(enemies)),
    }

    log.append(f"Floor {floor_number}: {len(combatants_heroes)} heroes vs {len(enemies)} enemies.")

    # Log class composition
    class_summary = ", ".join([f"{h.name}({h.hero_class})" for h in combatants_heroes])
    log.append(f"  Party: {class_summary}")

    npc_unit = None
    if is_escort:
        npc_hp = 80 + floor_number * 4
        npc_unit = CombatUnit(
            id=-9999, name="the escort", level=floor_number,
            health=npc_hp, max_health=npc_hp,
            strength=0, intelligence=0, agility=1,  # never acts, never attacks — agility=1 so it sorts last, harmless
            morale=100, stress=0, is_hero=True, hero_class="Escort",
            fear_immune=True, is_npc=True,
        )
        combatants_heroes.append(npc_unit)  # appended before the formation split below, so it naturally lands in backline
        log.append("  The escort target joins the formation, relying on your protection.")

    # Explicit 2-Front, 3-Back Formation
    frontline = combatants_heroes[:2]
    backline  = combatants_heroes[2:]

    all_units = combatants_heroes + enemies

    # Who was close to whom, for the grief sweep in the round loop. Pulled
    # once here rather than per-death — it's a DB read, and the roster can't
    # change mid-fight. _mourned makes each death fire its reaction exactly
    # once no matter how many rounds the body stays on the field.
    try:
        from services.bonds_service import get_pairwise_bonds
        pairwise_bonds = get_pairwise_bonds([u.id for u in combatants_heroes if u.is_hero and u.id > 0])
    except Exception:
        pairwise_bonds = {}
    _mourned = set()

    # The room itself. Derived from the floor's band and a fixed seed, so a
    # floor's environment is as stable a fact as its enemy composition —
    # scouting has to report something that will still be true next visit.
    # Applied to enemies too: a condition that only touched the player would
    # be a difficulty slider wearing a costume.
    try:
        from services.environment_service import (
            get_floor_environment, apply_condition_to_units, tick_hazard as _tick_hazard,
        )
        floor_env = get_floor_environment(floor_number, _current_tier_for_floor(floor_number))
        apply_condition_to_units(floor_env, all_units, log)
    except Exception as e:
        print(f"[Env] Floor environment skipped: {e}")
        floor_env, _tick_hazard = None, None

    if is_escort:
        max_rounds = ESCORT_TURN_LIMIT
    elif is_survival_swarm:
        max_rounds = turn_limit or SURVIVAL_TURN_LIMIT
    elif is_retrieval:
        max_rounds = turn_limit or RETRIEVAL_TURN_LIMIT
    else:
        max_rounds = 30

    # Squad tactical doctrine: if the team has a manually-assigned Leader, their
    # battle_tendency nudges everyone's default targeting choice (a "the whole
    # squad fights the way the Leader fights" effect) — leaderless teams have
    # no doctrine and fall back to the unmodified default targeting entirely.
    squad_leader = next((h for h in combatants_heroes if h.is_team_leader), None)
    squad_tendency = squad_leader.battle_tendency if squad_leader else None

    # Leadership bonus: a manually-assigned Leader's battle_tendency grants
    # the whole squad one passive combat-wide modifier for the fight, scaled
    # by the Leader's own star rank — a 1-star Leader barely rallies anyone,
    # a 7-star one is a real force multiplier. Layered on top of the
    # targeting-doctrine nudge above and the fear-steadying check below.
    leader_star_mult = 1.0
    leader_steady_chance = 0.0
    fear_resist_mult = 1.0
    if squad_leader:
        leader_star_mult = 1 + (squad_leader.hero_star - 1) * 0.3
        bonus = LEADERSHIP_BONUS.get(squad_leader.battle_tendency, {})
        atk_mult = 1 + bonus.get("atk_mult", 0) * leader_star_mult
        def_mult = 1 + bonus.get("def_mult", 0) * leader_star_mult
        crit_bonus = bonus.get("crit_bonus", 0) * leader_star_mult
        if atk_mult != 1 or def_mult != 1 or crit_bonus:
            for h in combatants_heroes:
                if atk_mult != 1: h.strength = int(h.strength * atk_mult)
                if def_mult != 1: h.endurance = int(h.endurance * def_mult)
                if crit_bonus: h.crit_chance += crit_bonus
        if bonus.get("fear_resist"):
            fear_resist_mult = 1 - min(0.6, bonus["fear_resist"] * leader_star_mult)
        leader_steady_chance = LEADER_STEADY_CHANCE_BASE * leader_star_mult

    # Encounter power ratio (enemy power / hero power) — gates universal
    # panic susceptibility below; a lopsided fight panics people regardless
    # of star, a clean win rarely does even for a 1-star.
    hero_power = sum(h.strength + h.intelligence + h.endurance + h.max_health * 0.05 for h in combatants_heroes) or 1
    enemy_power = sum(e.strength + e.endurance + e.max_health * 0.05 for e in enemies) or 1
    power_ratio = enemy_power / hero_power

    damage_dealt_stats = {h.id: 0 for h in combatants_heroes}
    consumables_used = {}

    # ═══ Boss phases — every full boss is a staged fight (66% / 33% HP
    # thresholds fire structural changes; seeded per floor).
    if is_boss and enemies:
        boss_unit = max(enemies, key=lambda e: e.max_health)
        if not boss_unit.phases:
            boss_unit.phases = roll_boss_phases(floor_number)

    # ═══ Environmental floor condition (Tower path only) — a seeded,
    # per-floor battlefield state that changes the fight's texture.
    floor_condition = roll_floor_condition(floor_number) if apply_support_boons else None
    if floor_condition:
        fc = floor_condition
        log.append(f"  ◆ FLOOR CONDITION — {fc['name']}: {fc['desc']}.")
        turns.append({"round": 0, "event": "condition", "log": f"{fc['name']} — {fc['desc']}"})
        for h in combatants_heroes:
            if fc.get("hero_regen"):
                h.status_effects.append({"type": "regen", "rounds": 999, "magnitude": fc["hero_regen"], "source_id": None})
            if fc.get("hero_agi_mult"):
                h.agility = max(1, int(h.agility * fc["hero_agi_mult"]))
            if fc.get("hero_crit_delta"):
                h.crit_chance = max(0.0, h.crit_chance + fc["hero_crit_delta"])
            if fc.get("hero_stress"):
                stress_changes[h.id] = stress_changes.get(h.id, 0) + fc["hero_stress"]
            if fc.get("hero_mana_regen_mult"):
                h.mana_regen_per_turn = max(0, int(h.mana_regen_per_turn * fc["hero_mana_regen_mult"]))
            if fc.get("both_str_mult"):
                h.strength = int(h.strength * fc["both_str_mult"])
            if fc.get("both_crit_delta"):
                h.crit_chance = min(0.8, h.crit_chance + fc["both_crit_delta"])
        for e in enemies:
            if fc.get("both_str_mult"):
                e.strength = int(e.strength * fc["both_str_mult"])
            if fc.get("both_crit_delta"):
                e.crit_chance = min(0.8, e.crit_chance + fc["both_crit_delta"])

    # Support-class combat boons (Tower path only — Arena passes
    # apply_support_boons=False, matching the Chef/Medic stat pipeline it skips).
    # Tactician: the plan seizes the initiative — guaranteed hero-first round 1
    # (even vs an ambush) and every hero opens with bonus mana ready.
    # Quartermaster: a light opening damage barrier (blunts the alpha strike) +
    # a team pool of emergency field kits that fire mid-fight when a hero drops
    # low (the kit-pool numbers are stashed for the round loop below).
    tactician_first_strike = False
    qm_kit_charges = 0
    qm_kit_heal_pct = 0.0
    qm_kit_threshold = 0.35
    qm_kit_mana = False
    medic_stitch_pct = 0.0     # CMO capstone: once/fight emergency stitch
    medic_cleanse = False      # Miracle Worker capstone: DOTs burn off fast
    priest_foresee = 0         # Prophet capstone: dodge N fatal blows outright
    laststand_pct = 0.0        # General capstone
    snowball_pct = 0.0         # Warlord capstone
    if apply_support_boons:
        try:
            from services.support_service import get_support_effects
            sfx = get_support_effects(outer_conn)
            # First strike is a STRATEGIST-branch perk (fx flag), NOT every
            # Tactician — the unevolved generic gives mana only.
            tactician_first_strike = sfx.get("tactician_first_strike", False)
            t_mana = sfx.get("tactician_bonus_mana", 0)
            if t_mana:
                for h in combatants_heroes:
                    if h.hero_class != "Construct":
                        h.mana = min(h.max_mana, h.mana + t_mana)
                opener = "seizes the initiative" if tactician_first_strike else "readies the party"
                log.append(f"  ✦ Your Tactician {opener} (+{t_mana} mana).")
            qm_barrier = sfx.get("quartermaster_barrier_pct", 0)
            if qm_barrier:
                # +1 round: the DOT tick at the top of every round decrements the
                # shield, so an R-round barrier must be stored as R+1 to actually
                # cover R full rounds of attacks.
                b_rounds = sfx.get("quartermaster_barrier_rounds", 2)
                for h in combatants_heroes:
                    if h.hero_class != "Construct":
                        apply_status_effect(h, "dmg_shield", b_rounds + 1, magnitude=qm_barrier)
                log.append(f"  ◆ The Quartermaster armors the party — incoming damage −{int(qm_barrier * 100)}% for {b_rounds} rounds.")
            qm_kit_charges = sfx.get("quartermaster_kit_charges", 0)
            qm_kit_heal_pct = sfx.get("quartermaster_kit_heal_pct", 0.0)
            qm_kit_threshold = sfx.get("quartermaster_kit_threshold", 0.35)
            # Medic · Field Medic (Toxin Kit): deployed heroes gain poison-on-hit
            # (only where a skill hasn't already granted it).
            medic_poison = sfx.get("medic_poison_pct", 0)
            if medic_poison:
                for h in combatants_heroes:
                    if h.hero_class != "Construct" and not h.poison_on_hit:
                        h.poison_on_hit = {"pct": medic_poison, "duration": 3}
                log.append(f"  ✦ The Field Medic's toxins coat the party's blades ({int(medic_poison * 100)}% poison).")
            # Scout · Spy (Sabotage): the enemy camp was hit — they start weakened.
            sabotage = sfx.get("scout_sabotage_pct", 0)
            if sabotage:
                sm = 1.0 - sabotage
                for e in enemies:
                    e.strength = max(1, int(e.strength * sm))
                    e.intelligence = max(1, int(e.intelligence * sm))
                    e.agility = max(1, int(e.agility * sm))
                    e.max_health = max(1, int(e.max_health * sm))
                    e.health = min(e.health, e.max_health)
                log.append(f"  ✦ Your Spy sabotaged the enemy — they enter at −{int(sabotage * 100)}% strength.")
            # Scout · Tracker (Predator's Mark): the biggest threat is marked —
            # its defenses shredded (Infiltrator capstone: team armor-pen too).
            mark = sfx.get("scout_mark_pct", 0)
            if mark and enemies:
                prey = max(enemies, key=lambda e: e.max_health + e.strength)
                prey.endurance = max(1, int(prey.endurance * (1.0 - mark)))
                prey.defense = max(1, int(prey.defense * (1.0 - mark)))
                pen = sfx.get("scout_mark_armor_pen", 0)
                if pen:
                    for h in combatants_heroes:
                        if h.hero_class != "Construct":
                            h.armor_pen = min(0.9, h.armor_pen + pen)
                log.append(f"  ✦ Predator's Mark — {prey.log_name}'s defenses are shredded (−{int(mark * 100)}%).")
            # Iron Chef capstone: fight-start morale surge (fearless bellies).
            morale_boost = sfx.get("chef_morale_boost", 0)
            if morale_boost:
                for h in combatants_heroes:
                    if h.hero_class != "Construct":
                        h.morale = min(100, h.morale + morale_boost)
                log.append(f"  ◆ War rations steel the party's nerves (+{morale_boost} morale).")
            # Saint capstone: fight-start holy mending.
            bless_heal = sfx.get("priest_blessing_heal", 0)
            if bless_heal:
                mended = 0
                for h in combatants_heroes:
                    if h.hero_class != "Construct" and h.health < h.max_health:
                        mended += apply_heal(h, int(h.max_health * bless_heal))
                if mended:
                    log.append(f"  ✟ The Saint's blessing mends the party (+{mended} HP).")
            # Plague Doctor / Brewmaster capstones: enemies start afflicted.
            enemy_poison = sfx.get("alch_enemy_poison", 0)
            if enemy_poison:
                for e in enemies:
                    apply_status_effect(e, "poison", 3, magnitude=e.max_health * enemy_poison)
                log.append(f"  ✦ The enemy arrives already sick — poisons seep through their ranks.")
            # Grand Strategist capstone: opening haste (agility surge, 2 rounds).
            haste = sfx.get("tact_haste_agi", 0)
            if haste:
                for h in combatants_heroes:
                    if h.hero_class != "Construct":
                        delta = int(h.agility * haste)
                        h.agility += delta
                        h.status_effects.append({"type": "stat_mod", "rounds": 3, "magnitude": 0, "stat": "agility", "delta": delta, "source_id": None})
                log.append(f"  ✦ The Grand Strategist's plan unfolds — the party moves with uncanny speed.")
            qm_kit_mana = sfx.get("qm_kit_mana", False)
            medic_stitch_pct = sfx.get("medic_stitch_pct", 0)
            medic_cleanse = sfx.get("medic_cleanse", False)
            priest_foresee = sfx.get("priest_foresee", 0)
            laststand_pct = sfx.get("tact_laststand_pct", 0)
            snowball_pct = sfx.get("tact_snowball_pct", 0)
        except Exception:
            pass

    for round_num in range(1, max_rounds + 1):
        # Blitz/Time Attack — the room empowers enemies further every round
        # they survive, starting round 2 (nothing's stacked yet on round 1).
        if is_blitz and round_num >= 2:
            for e in enemies:
                if e.alive:
                    e.strength = int(e.strength * (1 + BLITZ_STACK_PER_ROUND))
                    e.intelligence = int(e.intelligence * (1 + BLITZ_STACK_PER_ROUND))
                    e.agility = int(e.agility * (1 + BLITZ_STACK_PER_ROUND))
            log.append(f"  ✦ The room surges — enemies grow stronger (round {round_num}).")

        # Escalating floor hazard, if this floor has one. Same compounding
        # shape as the Blitz stacking directly above, pointed at the room
        # rather than the enemies — a team that can't close gets argued with
        # by the environment, not only by the 30-round limit.
        if floor_env and _tick_hazard:
            _tick_hazard(floor_env, round_num, all_units, log)

        if tactician_first_strike and round_num == 1:
            # The Tactician read the room — heroes act first on round 1,
            # overriding even an ambush. Normal agility order resumes round 2.
            all_units.sort(key=lambda u: (not u.is_hero, -(u.agility + random.uniform(0, 2))))
        elif is_ambush and round_num == 1:
            # Guaranteed enemy-first round 1, regardless of agility — the
            # whole point of an ambush. Normal agility-based turn order
            # resumes from round 2 on.
            all_units.sort(key=lambda u: (u.is_hero, -(u.agility + random.uniform(0, 2))))
        else:
            all_units.sort(key=lambda u: u.agility + random.uniform(0, 2), reverse=True)

        alive_heroes  = [u for u in combatants_heroes if u.alive]
        alive_enemies = [u for u in enemies if u.alive]
        if not alive_heroes or not alive_enemies:
            break

        # ─── Bond grief sweep ───
        # Done once per round against a set of already-mourned ids rather than
        # at each of the eight places a unit can die: those sites are spread
        # across the generic skill engine, DOT ticks, executions and ordinary
        # attacks, and hooking every one of them would be a much larger change
        # for the same result a round's latency later.
        for fallen in combatants_heroes:
            if not fallen.alive and fallen.id not in _mourned:
                _mourned.add(fallen.id)
                _bond_death_reactions(fallen, [u for u in combatants_heroes if u.alive],
                                      pairwise_bonds, log)

        # ─── Fear checks at start of each round ───
        for hero in alive_heroes:
            hero.fear_stunned = False  # Reset from last round
            _fear_check(hero, log, fear_resist_mult)
            _ego_resentment_check(hero, log)
            if hero.isolated_rounds > 0:
                hero.isolated_rounds -= 1
            if hero.bracing_rounds > 0:
                hero.bracing_rounds -= 1
            if hero.mana_regen_per_turn:
                hero.mana = min(hero.max_mana, hero.mana + hero.mana_regen_per_turn)
            for sid in list(hero.skill_cooldowns):
                if hero.skill_cooldowns[sid] > 0:
                    hero.skill_cooldowns[sid] -= 1

        # ─── Status effect DOT ticks (Bleed/Poison/Burn) — heroes and
        # enemies alike, right alongside the panic-state decrement above. ───
        for unit in alive_heroes + alive_enemies:
            dot_dmg = tick_status_effects(unit, log)
            if dot_dmg and unit.health <= 0 and unit.alive:
                unit.alive = False
                log.append(f"  ✦ {unit.log_name} succumbs to their wounds.")
            # Miracle Worker capstone: hero afflictions burn off twice as fast.
            if medic_cleanse and unit.is_hero:
                for eff in unit.status_effects:
                    if eff["type"] in ("bleed", "poison", "burn") and eff["rounds"] > 0:
                        eff["rounds"] -= 1
                unit.status_effects = [e for e in unit.status_effects if e["rounds"] > 0]
        alive_heroes = [u for u in alive_heroes if u.alive]
        alive_enemies = [u for u in alive_enemies if u.alive]
        if not alive_heroes or not alive_enemies:
            break

        # ─── CMO capstone: once per fight, the worst-hurt hero below 30% gets
        # an emergency stitch — a big single heal from the ward's best hands. ───
        if medic_stitch_pct > 0:
            hurt = [h for h in alive_heroes if h.max_health and h.health / h.max_health < 0.30 and h.hero_class != "Construct"]
            if hurt:
                patient = min(hurt, key=lambda h: h.health / h.max_health)
                healed = apply_heal(patient, int(patient.max_health * medic_stitch_pct))
                medic_stitch_pct = 0.0
                if healed:
                    log.append(f"  ✚ Emergency stitch! The CMO's work saves {patient.log_name} (+{healed} HP).")

        # ─── Quartermaster emergency field kits — a team pool of one-shot heals
        # that fire on any hero below the HP threshold who hasn't been kitted
        # yet this fight. Spends only on genuinely hurt heroes (never a wasted
        # top-up), one per hero, until the pool is empty. ───
        if qm_kit_charges > 0:
            for hero in alive_heroes:
                if qm_kit_charges <= 0:
                    break
                if hero.hero_class == "Construct" or getattr(hero, "_qm_kitted", False):
                    continue
                if hero.max_health and hero.health / hero.max_health < qm_kit_threshold:
                    healed = apply_heal(hero, int(hero.max_health * qm_kit_heal_pct))
                    hero._qm_kitted = True
                    qm_kit_charges -= 1
                    # Guildmaster capstone: kits also restore mana and purge afflictions.
                    if qm_kit_mana:
                        hero.mana = min(hero.max_mana, hero.mana + hero.max_mana // 2)
                        hero.status_effects = [e for e in hero.status_effects if e["type"] not in ("bleed", "poison", "burn")]
                    if healed:
                        extra = " — mana restored, wounds purged" if qm_kit_mana else ""
                        log.append(f"  ◆ The Quartermaster's field kit reaches {hero.log_name} — +{healed} HP{extra} [{hero.health}/{hero.max_health}]")

        # A steady Leader can pull a squadmate back together mid-fight —
        # personality-flavored, not guaranteed, and the Leader can't steady
        # themselves.
        if squad_leader and squad_leader.alive and not squad_leader.fear_stunned and leader_steady_chance > 0:
            for hero in alive_heroes:
                if hero is squad_leader:
                    continue
                if hero.fear_stunned and random.random() < leader_steady_chance:
                    hero.fear_stunned = False
                    log.append(f"  ◆ {squad_leader.log_name} steadies {hero.log_name} — the line holds.")
                elif (hero.isolated_rounds > 0 or hero.bracing_rounds > 0) and random.random() < leader_steady_chance:
                    hero.isolated_rounds = 0
                    hero.bracing_rounds = 0
                    log.append(f"  ◆ {squad_leader.log_name} snaps {hero.log_name} out of it — formation reforms.")

        # ─── Relic/skill regen ticks ───
        for unit in alive_heroes + alive_enemies:
            if unit.regen_pct > 0 and unit.health < unit.max_health:
                heal = apply_heal(unit, int(unit.max_health * unit.regen_pct))
                if heal:
                    log.append(f"  ✚ {unit.log_name} regenerates {heal} Health [{unit.health}/{unit.max_health}]")

        # ─── Equipped Potion/Scroll auto-use ───
        # Each hero only drinks what THEY specifically have equipped (see
        # heroes.equipped_consumable) — not whatever's "best" in a shared
        # warehouse pool. The actual stock (available_consumables, built
        # from real inventory counts) is still shared and finite, so two
        # heroes equipped with the same item draw down the same stack.
        if available_consumables:
            stock = {c["item_name"]: c for c in available_consumables}
            for hero in alive_heroes:
                if hero.used_consumable or not hero.equipped_consumable:
                    continue
                item = stock.get(hero.equipped_consumable)
                if not item or item["quantity"] <= 0:
                    continue
                if item.get("mana_pct") is not None:
                    # A mana potion triggers on low MANA, not low HP — and
                    # only for heroes who actually have a mana pool worth
                    # refilling (max_mana == 0 means a class with no active
                    # skill kit, nothing to restore).
                    if hero.max_mana <= 0 or hero.mana > hero.max_mana * CONSUMABLE_LOW_MANA_THRESHOLD:
                        continue
                    restored = min(hero.max_mana - hero.mana, int(hero.max_mana * item["mana_pct"]))
                    hero.mana += restored
                    item["quantity"] -= 1
                    hero.used_consumable = True
                    consumables_used[item["item_name"]] = consumables_used.get(item["item_name"], 0) + 1
                    log.append(f"  ✦ {hero.log_name} drinks a {item['item_name']}, restoring {restored} Mana [{hero.mana}/{hero.max_mana}]")
                    continue
                if item.get("heal_pct") is None or hero.health >= hero.max_health * CONSUMABLE_LOW_HP_THRESHOLD:
                    continue
                heal = apply_heal(hero, int(hero.max_health * item["heal_pct"]))
                item["quantity"] -= 1
                hero.used_consumable = True
                consumables_used[item["item_name"]] = consumables_used.get(item["item_name"], 0) + 1
                log.append(f"  ✚ {hero.log_name} drinks a {item['item_name']}, healing {heal} Health [{hero.health}/{hero.max_health}]")

        alive_frontline = [h for h in frontline if h.alive]

        for attacker in all_units:
            if not attacker.alive or attacker.is_npc:
                continue

            # Fear-stunned heroes skip their turn
            if attacker.is_hero and attacker.fear_stunned:
                stress_changes[attacker.id] = stress_changes.get(attacker.id, 0) + 5
                continue

            # Stun/Freeze lock out the turn for hero or enemy alike
            if is_action_locked(attacker):
                log.append(f"  {attacker.log_name} is unable to act!")
                continue

            # Bracing heroes forgo their strength to hunker down defensively
            if attacker.is_hero and attacker.bracing_rounds > 0:
                log.append(f"  {attacker.name} stays braced, watching for an opening.")
                continue

            # The Runner's whole turn goes to the objective — no attack, no
            # skill cast. Getting them safely through the round IS the floor.
            if attacker.is_hero and attacker.is_runner:
                log.append(f"  ✦ {attacker.name} works the objective ({min(round_num, max_rounds)}/{max_rounds})…")
                continue

            if attacker.is_hero:
                targets = [u for u in alive_enemies if u.alive]
                if not targets:
                    break

                skill = _select_castable_skill(attacker)
                if skill and _execute_active_skill(attacker, skill, targets, all_units, log, turns, round_num,
                                                    morale_changes, kill_counts, damage_dealt_stats):
                    continue  # skill replaced the basic attack this turn

                if attacker.is_aoe:
                    # Mage hits all enemies
                    log.append(f"  ✦ {attacker.name} ({attacker.hero_class}) casts — hits all enemies!")
                    attacker.mana = min(attacker.max_mana, attacker.mana + ON_ATTACK_MANA_GAIN)
                    for target in targets:
                        damage, is_crit = calc_damage(attacker, target, force_strength=True)
                        damage_dealt_stats[attacker.id] += damage
                        target.health -= damage
                        target.mana = min(target.max_mana, target.mana + ON_HIT_MANA_GAIN)
                        if attacker.poison_on_hit:
                            apply_status_effect(target, "poison", attacker.poison_on_hit["duration"],
                                                 magnitude=target.max_health * attacker.poison_on_hit["pct"], source_id=attacker.id)
                        crit_text = " CRIT!" if is_crit else ""
                        log_msg = f"    → {target.log_name} takes {damage}{crit_text} [{max(0,target.health)}/{target.max_health}]"
                        log.append(log_msg)
                        turns.append({"round": round_num, "attacker_id": attacker.id, "target_id": target.id, "damage": damage, "is_crit": is_crit, "target_hp": max(0, target.health), "log": log_msg, "attacker_mana": attacker.mana, "target_mana": target.mana, "statuses": _status_snapshot(all_units)})
                        if target.health <= 0:
                            target.alive = False
                            attacker.kills += 1
                            kill_counts[attacker.id] = kill_counts.get(attacker.id, 0) + 1
                            log.append(f"    ✦ {target.log_name} falls.")
                            # Warlord capstone: blood begets fury.
                            if snowball_pct and attacker.is_hero:
                                attacker.strength = int(attacker.strength * (1.0 + snowball_pct))
                                log.append(f"    ✦ {attacker.log_name}'s fury builds (+{int(snowball_pct * 100)}% ATK).")
                            for h in combatants_heroes:
                                if h.alive:
                                    morale_changes[h.id] = morale_changes.get(h.id, 0) + random.randint(2, 5)
                else:
                    _fl = _enemy_frontline_n(len(enemies))
                    alive_frontline_enemies = [e for e in enemies[:_fl] if e.alive]
                    alive_backline_enemies = [e for e in enemies[_fl:] if e.alive]
                    
                    if attacker.hero_class == "Assassin" and alive_backline_enemies:
                        target = random.choice(alive_backline_enemies)
                    else:
                        # Front-to-Back targeting for heroes
                        if alive_frontline_enemies:
                            # Match index or random frontliner
                            idx = combatants_heroes.index(attacker) % len(alive_frontline_enemies)
                            target = alive_frontline_enemies[idx]
                        elif alive_backline_enemies:
                            target = random.choice(alive_backline_enemies)
                        else:
                            continue
                        # Squad tactical doctrine — only applies to this unlocked
                        # default-targeting branch, never to the Assassin rule above.
                        target = _apply_tendency_target_override(target, targets, squad_tendency)

                    # A blinded attacker whiffs most basic attacks.
                    if has_status(attacker, "blind") and random.random() < BLIND_MISS_CHANCE:
                        log.append(f"  ◆ {attacker.log_name} is blinded and misses!")
                        continue

                    # Dodge check (now includes any Evasion status buff)
                    if random.random() < effective_dodge(target):
                        log.append(f"  {target.name} dodges!")
                        _bctx = _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)
                        fire_triggers(target, "on_dodge", _bctx, other=attacker)
                        continue

                    damage, is_crit = calc_damage(attacker, target, force_strength=True)

                    # Construct absorbs first hit for Magic Engineer
                    if target.is_hero and target.has_construct and target.construct_active:
                        target.construct_active = False
                        log.append(f"  {target.name}'s construct absorbs the hit!")
                        continue

                    # Invulnerability / absorb-shields eat the blow first.
                    damage = mitigate_special(target, damage, log)
                    damage_dealt_stats[attacker.id] += damage
                    target.health -= damage
                    attacker.mana = min(attacker.max_mana, attacker.mana + ON_ATTACK_MANA_GAIN)
                    target.mana = min(target.max_mana, target.mana + ON_HIT_MANA_GAIN)
                    if attacker.poison_on_hit:
                        apply_status_effect(target, "poison", attacker.poison_on_hit["duration"],
                                             magnitude=target.max_health * attacker.poison_on_hit["pct"], source_id=attacker.id)
                    crit_text = " CRIT!" if is_crit else ""
                    log_msg = f"  {attacker.log_name} hits {target.log_name} for {damage}{crit_text} [{max(0,target.health)}/{target.max_health}]"
                    log.append(log_msg)
                    turns.append({"round": round_num, "attacker_id": attacker.id, "target_id": target.id, "damage": damage, "is_crit": is_crit, "target_hp": max(0, target.health), "log": log_msg, "attacker_mana": attacker.mana, "target_mana": target.mana, "statuses": _status_snapshot(all_units)})

                    if target.health <= 0:
                        target.alive = False
                        attacker.kills += 1
                        kill_counts[attacker.id] = kill_counts.get(attacker.id, 0) + 1
                        log.append(_kill_log_line(attacker, target))
                        # Warlord capstone: blood begets fury.
                        if snowball_pct and attacker.is_hero:
                            attacker.strength = int(attacker.strength * (1.0 + snowball_pct))
                            log.append(f"    ✦ {attacker.log_name}'s fury builds (+{int(snowball_pct * 100)}% ATK).")
                        morale_changes[attacker.id] = morale_changes.get(attacker.id, 0) + random.randint(2, 5)
                    elif target.alive:
                        # Target survived — it may counter-attack (on_hit_taken).
                        _bctx = _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)
                        fire_triggers(target, "on_hit_taken", _bctx, other=attacker)

            else:
                if attacker.abilities:
                    alive_heroes_now = [h for h in combatants_heroes if h.alive]
                    if alive_heroes_now and _try_use_ability(attacker, alive_heroes_now, log, morale_changes, stress_changes,
                                                              enemies=enemies, all_units=all_units, floor_number=floor_number):
                        continue  # ability replaced the normal strength this turn

                alive_frontline = [h for h in frontline if h.alive]
                alive_backline = [h for h in backline if h.alive]

                # A taunting hero forces enemy targeting onto them — a
                # deliberate tank action, so it outranks even the isolated-
                # hero panic override below. Then, on an escort floor, the
                # NPC draws extra (but not certain) enemy attention even
                # without anyone taunting, which is exactly what makes
                # taunting matter there.
                taunting_heroes = [h for h in (alive_frontline + alive_backline) if has_status(h, "taunting")]
                npc_targets = [h for h in (alive_frontline + alive_backline) if h.is_npc]
                runner_targets = [h for h in (alive_frontline + alive_backline) if h.is_runner]
                forced_target = False

                if taunting_heroes:
                    target = random.choice(taunting_heroes)
                    forced_target = True
                elif npc_targets and random.random() < ESCORT_NPC_AGGRO_CHANCE:
                    target = random.choice(npc_targets)
                    forced_target = True
                elif runner_targets and random.random() < RETRIEVAL_RUNNER_AGGRO_CHANCE:
                    # The Runner is visibly busy with the objective — enemies
                    # go for them at elevated (but not certain) rates, same
                    # tension as the escort NPC but on a real, buildable hero.
                    target = random.choice(runner_targets)
                    forced_target = True
                elif alive_frontline:
                    idx = enemies.index(attacker) % len(alive_frontline)
                    target = alive_frontline[idx]
                elif alive_backline:
                    target = random.choice(alive_backline)
                else:
                    continue

                # An isolated hero is exposed and out of formation — enemies
                # preferentially pick them off over the formation's intended
                # target. Taunt and the NPC-aggro roll above both outrank
                # this (forced_target), same as Taunt outranking it always did.
                if not forced_target:
                    isolated_targets = [h for h in (alive_frontline + alive_backline) if h.isolated_rounds > 0]
                    if isolated_targets:
                        target = random.choice(isolated_targets)

                # A blinded enemy whiffs most basic attacks.
                if has_status(attacker, "blind") and random.random() < BLIND_MISS_CHANCE:
                    log.append(f"  ◆ {attacker.log_name} is blinded and misses!")
                    continue

                # Dodge check (now includes any Evasion status buff)
                if random.random() < effective_dodge(target):
                    log.append(f"  {target.name} dodges {attacker.log_name}'s strength!")
                    _bctx = _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)
                    fire_triggers(target, "on_dodge", _bctx, other=attacker)
                    continue

                # Construct check
                if target.has_construct and target.construct_active:
                    target.construct_active = False
                    log.append(f"  {target.name}'s construct absorbs the hit!")
                    continue

                damage, is_crit = calc_damage(attacker, target)
                stacks = unimber_stacks(target, len(alive_frontline) + len(alive_backline), len([e for e in enemies if e.alive]))
                damage = apply_unimber(damage, stacks)
                damage = mitigate_special(target, damage, log)
                target.health -= damage
                target.mana = min(target.max_mana, target.mana + ON_HIT_MANA_GAIN)
                crit_text = " CRIT!" if is_crit else ""
                unimber_tag = f"[Unimber ×{stacks}] " if stacks > 0 else ""
                log_msg = f"  {unimber_tag}{attacker.log_name} hits {target.log_name} for {damage}{crit_text} [{max(0,target.health)}/{target.max_health}]"
                log.append(log_msg)
                turns.append({"round": round_num, "attacker_id": attacker.id, "target_id": target.id, "damage": damage, "is_crit": is_crit, "target_hp": max(0, target.health), "log": log_msg, "attacker_mana": attacker.mana, "target_mana": target.mana, "unimber_stacks": stacks, "statuses": _status_snapshot(all_units)})

                if target.health <= 0:
                    # Prophet capstone: fate was foreseen — the blow misses entirely
                    # (team pool, consumed before any death-save charge).
                    if target.is_hero and priest_foresee > 0:
                        priest_foresee -= 1
                        target.health = max(1, target.health + damage)
                        log.append(f"  ✦ The Prophet foresaw this — {target.log_name} steps aside from death itself!")
                        continue
                    # Death save check
                    if target.death_save > 0:
                        target.death_save -= 1
                        target.health = 1
                        log.append(f"  ✦ {target.log_name} refuses to fall! (Undying Will)")
                        continue

                    target.alive = False
                    if target is npc_unit:
                        log.append(f"  ✦ The escort falls — you failed to protect them.")
                    else:
                        log.append(f"  ✦ {target.log_name} has fallen.")
                        # Witness death — morale crash + trauma spike + fear stress
                        for h in combatants_heroes:
                            if h.alive and h is not npc_unit:
                                morale_changes[h.id] = morale_changes.get(h.id, 0) - random.randint(8, 18)
                                stress_changes[h.id] = stress_changes.get(h.id, 0) + random.randint(5, 12)
                                log.append(f"    {h.name}'s morale wavers...")
                                _panic_check(h, "witness_death", log, power_ratio, fear_resist_mult)
                        # General capstone: the line holds — survivors dig in.
                        if laststand_pct and target.is_hero:
                            for h in combatants_heroes:
                                if h.alive and h.hero_class != "Construct":
                                    h.strength = int(h.strength * (1.0 + laststand_pct))
                                    h.intelligence = int(h.intelligence * (1.0 + laststand_pct))
                            log.append(f"  ◆ The General's voice cuts the despair — the line HOLDS (+{int(laststand_pct * 100)}%).")
                elif target.health > 0 and (target.health / target.max_health) < 0.25:
                    _panic_check(target, "hp_critical", log, power_ratio, fear_resist_mult)
                    # A hero hit but still standing may counter (on_hit_taken).
                    if target.is_hero:
                        _bctx = _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)
                        fire_triggers(target, "on_hit_taken", _bctx, other=attacker)
                elif target.is_hero and target.alive:
                    _bctx = _basic_ctx(all_units, log, turns, round_num, morale_changes, kill_counts, damage_dealt_stats)
                    fire_triggers(target, "on_hit_taken", _bctx, other=attacker)

            if npc_unit is not None and not npc_unit.alive:
                break  # mid-round abort — protecting the NPC is the whole point of the floor

            if runner_unit is not None and not runner_unit.alive:
                break  # mid-round abort — the objective dies with the Runner

        alive_heroes  = [u for u in combatants_heroes if u.alive and u is not npc_unit]
        alive_enemies = [u for u in enemies if u.alive]
        if (not alive_heroes or not alive_enemies
                or (npc_unit is not None and not npc_unit.alive)
                or (runner_unit is not None and not runner_unit.alive)):
            break

        # ═══ Boss phase check — a boss pushed past a threshold this round
        # changes the fight before the next one starts. ═══
        check_boss_phases(enemies, all_units, alive_heroes, log, floor_number,
                          morale_changes, stress_changes, turns, round_num)
        alive_heroes = [u for u in alive_heroes if u.alive]   # cataclysm can kill
        if not alive_heroes:
            break

    alive_heroes  = [u for u in combatants_heroes if u.alive and u is not npc_unit]
    dead_heroes   = [u for u in combatants_heroes if not u.alive and u is not npc_unit]
    # Survival Floor wins by outlasting the clock with anyone still standing
    # — wiping the swarm early still counts (just rare at these counts), but
    # killing every enemy is not required, unlike every other floor type.
    # Escort wins by keeping the NPC alive either to enemy-wipe or to the
    # turn limit; the NPC itself is never counted among alive_heroes/
    # dead_heroes so it never pollutes rewards, skill-upgrade rolls, or
    # morale bookkeeping below.
    if is_escort:
        npc_alive = npc_unit.alive if npc_unit else False
        enemies_wiped = len([u for u in enemies if u.alive]) == 0
        heroes_won = npc_alive and (enemies_wiped or round_num >= max_rounds)
    elif is_retrieval:
        # Retrieval wins by the Runner completing the channel (surviving to
        # the turn limit) or the room being wiped early — but the Runner
        # dying fails the floor even with the rest of the team standing.
        runner_alive = runner_unit.alive if runner_unit else False
        enemies_wiped = len([u for u in enemies if u.alive]) == 0
        heroes_won = runner_alive and (enemies_wiped or round_num >= max_rounds)
    elif is_survival_swarm:
        heroes_won = len(alive_heroes) > 0
    else:
        heroes_won = len(alive_heroes) > 0 and len([u for u in enemies if u.alive]) == 0

    if heroes_won:
        if is_survival_swarm:
            log.append(f"✓ Survived! {len(alive_heroes)} hero(es) held the line for {round_num} round(s).")
        elif is_retrieval:
            log.append(f"✓ Objective secured! {runner_unit.name} finished the job with {len(alive_heroes)} hero(es) still standing.")
        else:
            log.append(f"✓ Victory. {len(alive_heroes)} hero(es) survived.")
        if is_boss:
            log.append(f"  ═══ BOSS DEFEATED ═══")
        # Rescue's win bonus: a small, lasting morale boost (the captive's
        # gratitude) — NOT a heal, since every floor already fully heals
        # surviving heroes on its own (see tower.py's between_floor_recovery),
        # which made an escort-specific heal a no-op. Morale/stress are the
        # only state that actually persists floor-to-floor, so that's where
        # a real "win bonus" has to live. Kept deliberately small per
        # explicit direction ("nothing crazy").
        if is_escort:
            for h in alive_heroes:
                morale_changes[h.id] = morale_changes.get(h.id, 0) + ESCORT_RESCUE_MORALE_BONUS
            log.append(f"  ✚ The rescued captive's gratitude lifts the team's spirits (+{ESCORT_RESCUE_MORALE_BONUS} morale).")
        for h in alive_heroes:
            morale_changes[h.id] = morale_changes.get(h.id, 0) - random.randint(3, 10)
    elif is_retrieval and runner_unit is not None and not runner_unit.alive:
        log.append(f"✗ Mission failed. {runner_unit.name} fell before the objective was secured — the team withdraws.")
    else:
        log.append(f"✗ Defeat. All heroes fell on floor {floor_number}.")

    skill_upgrades = {}
    skills_learned = {}
    if heroes_won:
        for h in alive_heroes:
            for s in h.skills:
                if s.get("level", 1) >= 10:
                    # Chance to upgrade — talented heroes learn faster
                    base_chance = 0.20 if is_boss else 0.05
                    chance = base_chance * (0.6 + h.talent * 0.8)
                    if random.random() < chance:
                        tiers = ["Beginner", "Intermediate", "Advanced", "Legendary"]
                        current_tier = s.get("tier", "Beginner")
                        if current_tier in tiers:
                            idx = tiers.index(current_tier)
                            if idx < len(tiers) - 1:
                                new_tier = tiers[idx + 1]
                                skill_upgrades.setdefault(h.id, []).append({
                                    "skill_id": s["id"],
                                    "skill_name": s["name"],
                                    "new_tier": new_tier
                                })
                                log.append(f"  ✦ {h.name}'s {s['name']} ascended to {new_tier} tier!")

            # Chance to learn an entirely new skill — capacity grows with
            # star rank, but talent grows it further on top, so a highly
            # talented hero can out-learn a less-talented hero of the same
            # rarity over a long career.
            cap = max_skill_slots(h.hero_star, h.talent)
            if len(h.skills) < cap:
                base_chance = 0.10 if is_boss else 0.02
                chance = base_chance * (0.5 + h.talent * 1.5)
                if random.random() < chance:
                    from services.skills_service import get_skill_for_class
                    known_ids = {s["id"] for s in h.skills}
                    new_skill = get_skill_for_class(h.hero_class, hero_star=h.hero_star)
                    if new_skill and new_skill["id"] not in known_ids:
                        new_skill["tier"] = "Beginner"
                        new_skill["level"] = 1
                        new_skill["xp"] = 0
                        new_skill["max_xp"] = 100
                        skills_learned.setdefault(h.id, []).append(new_skill)
                        log.append(f"  ✦ {h.name} has learned a new skill: {new_skill['name']}!")

    result = {
        "winner": "heroes" if heroes_won else "enemies",
        "is_boss": is_boss,
        "is_survival_swarm": is_survival_swarm,
        "is_retrieval": is_retrieval,
        "runner_id": runner_unit.id if runner_unit else None,
        "runner_survived": (runner_unit.alive if runner_unit else None) if is_retrieval else None,
        "rounds_survived": round_num if (is_survival_swarm or is_retrieval) else None,
        "turn_limit": max_rounds if (is_survival_swarm or is_retrieval) else None,
        "consumables_used": consumables_used,
        "initial_state": initial_state,
        "surviving_heroes": [
            {
                "id": h.id,
                "health": max(0, h.health),
                "morale_delta": morale_changes.get(h.id, 0),
                "kills_gained": kill_counts.get(h.id, 0),
                "stress_delta": stress_changes.get(h.id, 0),
            }
            for h in alive_heroes
        ],
        "dead_heroes": [h.id for h in dead_heroes],
        "surviving_enemies": alive_enemies,
        "skill_upgrades": skill_upgrades,
        "skills_learned": skills_learned,
        "log": log,
        "turns": turns,
        "rounds": round_num,
        "combat_metrics": damage_dealt_stats,
        # Internal bookkeeping for _apply_combat_drops below — not meant for
        # API consumers, but combatants_heroes only exists in this function's
        # scope, so the average has to be threaded through somehow.
        "_avg_luck": sum(h.luck for h in combatants_heroes) / max(1, len(combatants_heroes)),
    }
    return result


def _apply_combat_drops(result: dict, floor_number: int, is_boss: bool, is_miniboss: bool, outer_conn):
    """Tower-specific economy rewards (gold/materials/equipment/relic drops)
    on a winning fight — split out of run_combat so Arena fights (which use
    _resolve_combat_from_processed directly, skipping this entirely) don't
    grant Tower currency for a PvP match. Mutates result in place."""
    avg_luck = result.pop("_avg_luck", 5.0)
    if result["winner"] != "heroes":
        return
    try:
        # Reuse the caller's connection if it handed one in — opening a
        # second connection here while the caller's own `with db()`
        # transaction is still uncommitted causes "database is locked"
        # on SQLite, which this block's except then silently swallowed,
        # also skipping the gold/ingredients/materials grant below it.
        from services.difficulty_service import get_difficulty_mults
        if outer_conn is not None:
            base_info = outer_conn.execute("SELECT global_buffs FROM base WHERE id = 1").fetchone()
            buffs = __import__('json').loads(base_info["global_buffs"] or "{}") if base_info else {}
            diff_mults = get_difficulty_mults(outer_conn)
        else:
            from database import db
            with db() as _conn:
                base_info = _conn.execute("SELECT global_buffs FROM base WHERE id = 1").fetchone()
                buffs = __import__('json').loads(base_info["global_buffs"] or "{}") if base_info else {}
                diff_mults = get_difficulty_mults(_conn)
        from services.equipment_service import generate_equipment_drop
        # Enemy names are needed by both the equipment-type bias below and
        # the material-hint roll further down — computed once, up front.
        enemy_names = [e["name"] for e in result.get("initial_state", {}).get("enemies", [])]
        # Luck is averaged across the deployed team, not taken from a
        # single hero — a team-comp consideration, not "stack one lucky
        # hero and ignore the rest."
        # Athenaeum research: drop_pct widens the drop gate here, gold_pct
        # multiplies the guaranteed gold grants further down.
        try:
            from services.athenaeum_service import get_research_bonuses
            _research = get_research_bonuses(outer_conn)
        except Exception:
            _research = {}
        drop_bonus = buffs.get("drop_boost", 0) * 0.05 + avg_luck / 100 + _research.get("drop_pct", 0) / 100.0
        # rare_drop_mult shifts the rarity SCORE (Easy skews down ~half a
        # tier, Hard skews up ~half a tier), not drop_bonus — drop_bonus
        # only gates whether anything drops at all, not how good it is.
        rarity_boost = (diff_mults["rare_drop_mult"] - 1.0) * 40
        equip = generate_equipment_drop(floor_number, is_boss, drop_bonus, rarity_boost=rarity_boost, enemy_names=enemy_names)
        if equip:
            result["equipment_drop"] = equip

        from services.relics_service import roll_relic_drop
        relic = roll_relic_drop(is_boss, is_miniboss, floor_number, conn=outer_conn)
        if relic:
            result["relic_drop"] = relic

        # Guaranteed Drops
        result["gold_gained"] = int(300 * (1 + (floor_number/10)))
        result["ingredients_gained"] = random.randint(2, 5)

        from services.materials_service import roll_material_name_for_enemies, tiered_material_name
        # Drops are now biased toward materials tied to the enemies actually
        # in this fight (e.g. a Slime Core only has a real chance if a
        # Shadow Wisp/Acid Slime was actually fought) instead of a pure
        # floor-wide pool with no connection to what you fought — confirmed
        # reported bug: "fought floor 1, no slimes, got a slime core."
        drops = {}
        for _ in range(random.randint(2, 4)):
            mat = tiered_material_name(roll_material_name_for_enemies(floor_number, enemy_names), avg_luck=avg_luck)
            drops[mat] = drops.get(mat, 0) + 1
        result["materials_gained"] = drops

        if is_boss:
            result["gold_gained"] += int(1500 * (1 + (floor_number/10)))
            result["ingredients_gained"] += 10
            for _ in range(5):
                mat = tiered_material_name(roll_material_name_for_enemies(floor_number, enemy_names), avg_luck=avg_luck)
                drops[mat] = drops.get(mat, 0) + 1
            # Eternal Shards — the transcendence (6★→7★) material. Boss
            # kills at floor 80+ ONLY; never in gates, markets, or the
            # generic drop pools. One per kill, two from the floor-100
            # summit boss. Seven are needed per transcendence.
            if floor_number >= 80:
                shard_qty = 2 if floor_number >= 100 else 1
                drops["Eternal Shard"] = drops.get("Eternal Shard", 0) + shard_qty
            result["materials_gained"] = drops
        elif is_miniboss:
            # Miniboss floors didn't have a bonus tier before — every
            # miniboss round (Survival Floor swarms included, since those
            # only ever happen on a miniboss floor) gets a smaller version
            # of the Boss bonus on top of the guaranteed drops above.
            result["gold_gained"] += int(600 * (1 + (floor_number/10)))
            result["ingredients_gained"] += 4
            for _ in range(2):
                mat = tiered_material_name(roll_material_name_for_enemies(floor_number, enemy_names), avg_luck=avg_luck)
                drops[mat] = drops.get(mat, 0) + 1
            result["materials_gained"] = drops

        # Easy mode's appeal is quantity (gold), Hard's is quality (rarity
        # boost above) — Hard deliberately leaves gold at baseline per spec.
        result["gold_gained"] = int(result["gold_gained"] * diff_mults["gold_mult"])

        # Quartermaster capstones: Hoarder (Deep Stores) fattens gold AND
        # materials from every floor; Tycoon (War Chest) skims a gold cut.
        try:
            from services.support_service import get_support_effects
            _sfx = get_support_effects(outer_conn)
            hoard = _sfx.get("qm_hoard_loot_pct", 0)
            warchest = _sfx.get("qm_warchest_gold_pct", 0)
            if hoard:
                result["gold_gained"] = int(result["gold_gained"] * (1 + hoard))
                extra = tiered_material_name(roll_material_name_for_enemies(floor_number, enemy_names), avg_luck=avg_luck)
                drops[extra] = drops.get(extra, 0) + 1
                result["materials_gained"] = drops
            if warchest:
                result["gold_gained"] = int(result["gold_gained"] * (1 + warchest))
        except Exception:
            pass

        # Mounted Reliquary gold trophies boost every fight's gold.
        try:
            from services.endgame_service import get_global_empowerment
            if outer_conn is not None:
                gold_pct = get_global_empowerment(outer_conn).get("gold_pct", 0)
            else:
                from database import db as _db2
                with _db2() as _c2:
                    gold_pct = get_global_empowerment(_c2).get("gold_pct", 0)
            if gold_pct:
                result["gold_gained"] = int(result["gold_gained"] * (1 + gold_pct / 100.0))
        except Exception:
            pass

        # Athenaeum research gold_pct (Deeper Pockets et al.) stacks the
        # same way, on top of difficulty and trophy multipliers.
        r_gold = _research.get("gold_pct", 0)
        if r_gold:
            result["gold_gained"] = int(result["gold_gained"] * (1 + r_gold / 100.0))
    except Exception as e:
        print(f"Error generating drop: {e}")

def run_multi_combat(hero_teams: list[list[dict]], floor_number: int, is_boss: bool = False, is_miniboss: bool = False, zone_theme: str = "", boss_data_override=_UNSET, difficulty_mult: float = 1.0, conn=None, family_override: dict = None, is_survival_swarm: bool = False, turn_limit: int = None, available_consumables: list = None, is_escort: bool = False, enemy_count_override: int = None, is_ambush: bool = False, is_blitz: bool = False, cursed_debuff: dict = None, miniboss_variant: str = None, is_retrieval: bool = False, runner_id: int = None) -> dict:
    # Raid Boss — reduced to exactly Floor 50 and Floor 100 (was every 20th
    # floor), so the multi-team merge fight stays a genuine milestone
    # instead of a recurring pattern. Floor 100 still gets its own random
    # pick (Lich King/Nightwing Devourer/Aetherion) via family_override
    # exactly like any other boss floor.
    if is_boss and (floor_number == 50 or floor_number == 100):
        combined_heroes = []
        for team in hero_teams:
            combined_heroes.extend(team)
        return run_combat(combined_heroes, floor_number, is_boss=True, is_miniboss=False, zone_theme=zone_theme, boss_data_override=boss_data_override, difficulty_mult=difficulty_mult * len(hero_teams), outer_conn=conn, available_consumables=available_consumables, family_override=family_override)

    # Retrieval Missions don't relay — there is exactly one objective and one
    # designated Runner, so multiple deployed teams fight as one combined
    # squad protecting them (same merge the Raid Boss branch above uses).
    if is_retrieval and len([t for t in hero_teams if t]) > 1:
        combined_heroes = [h for team in hero_teams for h in team]
        return run_combat(combined_heroes, floor_number, zone_theme=zone_theme,
                          difficulty_mult=difficulty_mult * len(hero_teams), outer_conn=conn,
                          enemy_count_override=enemy_count_override,
                          available_consumables=available_consumables,
                          is_retrieval=True, runner_id=runner_id, turn_limit=turn_limit)

    # Shared Encounter relay — one enemy roster scaled for the combined
    # threat of every deployed team (same scaling the boss-merge branch above
    # already uses), so teams relay into the SAME fight instead of each
    # rolling an independent one. Team 2 picks up whatever Team 1 left alive
    # (same enemy HP/state carried forward). This team-by-team order is just
    # how the backend computes the HP handoff — the frontend renders every
    # team's own arena (see team_results) at the same time, so on screen it
    # reads as simultaneous parallel battles, not one-then-the-other.
    #
    # NOTE: this used to always call make_enemies() here regardless of
    # is_boss/is_miniboss — meaning every boss/miniboss floor that wasn't
    # also a %20 Raid Boss (so: every floor 5/15/25/... and every floor
    # 10/30/50/70/90) silently fought a regular mob encounter instead of an
    # actual named boss/miniboss, since preset_enemies short-circuits
    # make_boss() inside run_combat. Fixed below.
    if is_survival_swarm:
        shared_enemies = make_swarm_miniboss_encounter(floor_number)
    elif is_miniboss and miniboss_variant in ("behemoth", "assassin", "twins", "mirror"):
        flat_heroes = [h for team in hero_teams for h in team]
        shared_enemies = make_miniboss_variant(miniboss_variant, floor_number, zone_theme, flat_heroes)
    elif is_boss or is_miniboss:
        shared_enemies = make_boss(floor_number, zone_theme, is_miniboss, boss_data_override=boss_data_override, family_override=family_override)
    else:
        shared_enemies = make_enemies(floor_number, count=enemy_count_override, difficulty_mult=difficulty_mult * len(hero_teams))

    logs = []
    final_result = {
        "winner": "enemies",
        "is_boss": is_boss,
        "surviving_heroes": [],
        "dead_heroes": [],
        "skill_upgrades": {},
        "skills_learned": {},
        "log": logs,
        "combat_metrics": {},
        "gold_gained": 0,
        "ingredients_gained": 0,
        "materials_gained": {},
        "consumables_used": {},
        # One entry per deployed team (None if that team was empty or had
        # nothing left to fight) — the frontend renders one CombatArena per
        # entry, each with its own initial_state/turns/log for that team's leg
        # of the shared fight.
        "team_results": [],
    }

    current_enemies = shared_enemies
    for i, team in enumerate(hero_teams):
        logs.append(f"\n=== TEAM {i+1} ENGAGES ===")
        if not team:
            logs.append(f"Team {i+1} is empty.")
            final_result["team_results"].append(None)
            continue
        if not current_enemies:
            logs.append(f"Team {i+1} arrives to find the encounter already cleared.")
            final_result["team_results"].append(None)
            continue

        # is_boss used to be hardcoded False here regardless of the real
        # flag — harmless for the %20 Raid Boss case (handled in its own
        # branch above before reaching this loop), but for every other boss
        # floor (10, 30, 50, 70, 90) it meant _apply_combat_drops below never
        # applied the Boss reward bonus, and the frontend never got
        # initial_state.is_boss=True to size the enemy sprite as a boss.
        # Potions/Scrolls are a shared base-wide backpack, not per-team — the
        # same list object is passed (and mutated in place) into every team's
        # fight in this loop, so a multi-team floor can't double-dip the same
        # finite stock once one team's fight already spent it.
        res = run_combat(team, floor_number, is_boss=is_boss, is_miniboss=is_miniboss, zone_theme=zone_theme, difficulty_mult=difficulty_mult, preset_enemies=current_enemies, outer_conn=conn, is_survival_swarm=is_survival_swarm, turn_limit=turn_limit, available_consumables=available_consumables, is_escort=is_escort, is_ambush=is_ambush, is_blitz=is_blitz, cursed_debuff=cursed_debuff, miniboss_variant=miniboss_variant, is_retrieval=is_retrieval, runner_id=runner_id)
        logs.extend(res.get("log", []))
        final_result["team_results"].append(res)

        for hid, upg in res.get("skill_upgrades", {}).items():
            final_result["skill_upgrades"].setdefault(hid, []).extend(upg)
        for hid, lrn in res.get("skills_learned", {}).items():
            final_result["skills_learned"].setdefault(hid, []).extend(lrn)
        for hid, dmg in res.get("combat_metrics", {}).items():
            final_result["combat_metrics"][hid] = final_result["combat_metrics"].get(hid, 0) + dmg

        final_result["surviving_heroes"].extend(res.get("surviving_heroes", []))
        final_result["dead_heroes"].extend(res.get("dead_heroes", []))
        final_result["gold_gained"] += res.get("gold_gained", 0)
        final_result["ingredients_gained"] += res.get("ingredients_gained", 0)
        for k, v in res.get("materials_gained", {}).items():
            final_result["materials_gained"][k] = final_result["materials_gained"].get(k, 0) + v
        for k, v in res.get("consumables_used", {}).items():
            final_result["consumables_used"][k] = final_result["consumables_used"].get(k, 0) + v
        if "equipment_drop" in res and "equipment_drop" not in final_result:
            final_result["equipment_drop"] = res["equipment_drop"]
        if "relic_drop" in res and "relic_drop" not in final_result:
            final_result["relic_drop"] = res["relic_drop"]

        current_enemies = res.get("surviving_enemies", [])

    if is_survival_swarm or is_retrieval:
        # Survival Floors are single-team only (they only ever fire on a
        # %5 miniboss floor, which never requires 2+ teams) — winning means
        # outlasting the clock, not clearing the roster, so the "did the
        # enemy count hit zero" inference below doesn't apply here.
        # Retrieval works the same way: the win is the Runner finishing the
        # channel, not the enemy roster hitting zero, so the first (and only
        # meaningful) team's own verdict is the encounter verdict.
        only = next((r for r in final_result["team_results"] if r), None)
        final_result["winner"] = only["winner"] if only else "enemies"
    else:
        # The shared encounter counts as cleared once the relay runs the
        # enemy roster down to nothing — win/loss is for the encounter as a
        # whole, not any single team's leg of it.
        final_result["winner"] = "heroes" if not current_enemies else "enemies"

    # Single-team floors are a relay of length one — also forward that one
    # team's initial_state/turns/rounds at the top level so the existing
    # single-arena frontend path keeps working unchanged.
    if len(hero_teams) == 1 and final_result["team_results"] and final_result["team_results"][0]:
        only = final_result["team_results"][0]
        final_result["initial_state"] = only.get("initial_state")
        final_result["turns"] = only.get("turns")
        final_result["rounds"] = only.get("rounds")
        final_result["is_survival_swarm"] = only.get("is_survival_swarm", False)
        final_result["is_retrieval"] = only.get("is_retrieval", False)
        final_result["runner_id"] = only.get("runner_id")
        final_result["runner_survived"] = only.get("runner_survived")
        final_result["rounds_survived"] = only.get("rounds_survived")
        final_result["turn_limit"] = only.get("turn_limit")

    return final_result
