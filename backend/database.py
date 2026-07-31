import sqlite3
import json
import os
import random
from contextlib import contextmanager

SAVES_DIR = "saves"
os.makedirs(SAVES_DIR, exist_ok=True)

_ACTIVE_PROFILE_FILE = os.path.join(SAVES_DIR, ".active_profile")

def _load_active_profile():
    if os.path.exists(_ACTIVE_PROFILE_FILE):
        try:
            name = open(_ACTIVE_PROFILE_FILE, "r", encoding="utf-8").read().strip()
            if name:
                return name
        except Exception:
            pass
    return "main"

# Persisted to disk so a backend restart/reload (e.g. during dev) doesn't
# silently snap back to "main" while the frontend still thinks another
# profile is active.
ACTIVE_PROFILE = _load_active_profile()

if os.path.exists("game.db") and not os.path.exists(os.path.join(SAVES_DIR, "main.db")):
    os.rename("game.db", os.path.join(SAVES_DIR, "main.db"))

def get_db_path():
    if not ACTIVE_PROFILE:
        # Don't default to "main.db" because it causes zombie profiles to respawn
        # when background polling hits the API after deleting the last profile.
        raise ValueError("No active profile set")
    return os.path.join(SAVES_DIR, f"{ACTIVE_PROFILE}.db")

def set_profile(profile_name, difficulty=None):
    global ACTIVE_PROFILE
    ACTIVE_PROFILE = profile_name
    os.makedirs(SAVES_DIR, exist_ok=True)
    # difficulty is only ever applied on first creation of a profile — an
    # existing save's difficulty is locked in (see difficulty_service.py),
    # so we must know whether this .db file existed *before* init_db()
    # creates it.
    is_new_profile = not os.path.exists(get_db_path())
    with open(_ACTIVE_PROFILE_FILE, "w") as f:
        f.write(profile_name)
    init_db()
    if is_new_profile and difficulty in ("easy", "normal", "hard"):
        with db() as conn:
            conn.execute("UPDATE base SET difficulty = ? WHERE id = 1", (difficulty,))

def clear_active_profile():
    global ACTIVE_PROFILE
    ACTIVE_PROFILE = None
    try:
        if os.path.exists(_ACTIVE_PROFILE_FILE):
            os.remove(_ACTIVE_PROFILE_FILE)
    except Exception:
        pass

def get_profiles():
    if not os.path.exists(SAVES_DIR):
        return []
    profiles = []
    for f in os.listdir(SAVES_DIR):
        if f.endswith(".db") and f != "None.db":
            profiles.append(f.replace(".db", ""))
    return profiles

def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS heroes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT,
            backstory TEXT,
            personality TEXT,
            portrait_path TEXT,

            -- Rarity
            birth_star INTEGER DEFAULT 1,
            ascension_star INTEGER DEFAULT 0,

            -- Class
            hero_class TEXT DEFAULT 'Classless',
            hidden_class TEXT,
            can_pilot INTEGER DEFAULT 0,

            -- Level
            level INTEGER DEFAULT 1,

            -- Base stats
            health INTEGER DEFAULT 100,
            max_health INTEGER DEFAULT 100,
            strength INTEGER DEFAULT 10,
            intelligence INTEGER DEFAULT 5,
            defense INTEGER DEFAULT 5,
            agility INTEGER DEFAULT 10,
            -- defense is legacy/inert — endurance replaces it (mitigation +
            -- drives max_health) and is backfilled from defense on migration.
            -- See the ALTER TABLE block below for willpower/luck backfill too.
            endurance INTEGER DEFAULT 5,
            willpower INTEGER DEFAULT 6,
            luck INTEGER DEFAULT 5,

            -- Hidden aptitudes (0-100 each)
            apt_combat INTEGER DEFAULT 50,
            apt_tactical INTEGER DEFAULT 50,
            apt_survival INTEGER DEFAULT 50,
            apt_mental INTEGER DEFAULT 50,
            apt_leadership INTEGER DEFAULT 50,
            apt_diligence INTEGER DEFAULT 50,
            aptitudes_revealed INTEGER DEFAULT 0,

            -- Morale
            morale INTEGER DEFAULT 100,
            stress INTEGER DEFAULT 0,
            trauma INTEGER DEFAULT 0,
            morale_state TEXT DEFAULT 'steady',

            -- Status
            is_alive INTEGER DEFAULT 1,
            is_on_team INTEGER DEFAULT 0,
            floor_joined INTEGER DEFAULT 0,
            team_position INTEGER DEFAULT 0,
            ego_type TEXT,
            ego_patience INTEGER DEFAULT 100,

            -- Progression
            kills INTEGER DEFAULT 0,
            floors_survived INTEGER DEFAULT 0,
            missions_completed INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            current_star INTEGER,
            synthesized INTEGER DEFAULT 0,
            skills TEXT DEFAULT '[]',
            synergy_group TEXT,
            gender TEXT,
            fatigue INTEGER DEFAULT 0,
            base_floor INTEGER DEFAULT 0,
            
            -- Titles Tracking
            lifetime_kills INTEGER DEFAULT 0,
            sole_survivor_boss_clears INTEGER DEFAULT 0,
            leader_clears INTEGER DEFAULT 0,
            unique_floor_clears INTEGER DEFAULT 0,
            traits TEXT DEFAULT '[]',
            xp INTEGER DEFAULT 0,
            runes TEXT DEFAULT '[]',
            seals TEXT DEFAULT '[]'
        );

CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'active',
            current_floor INTEGER DEFAULT 0,
            highest_floor INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS run_heroes (
            run_id INTEGER REFERENCES runs(id),
            hero_id INTEGER REFERENCES heroes(id),
            PRIMARY KEY (run_id, hero_id)
        );

CREATE TABLE IF NOT EXISTS floors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES runs(id),
            floor_number INTEGER NOT NULL,
            floor_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            outcome TEXT,
            narrative TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS base (
            id INTEGER PRIMARY KEY DEFAULT 1,
            name TEXT DEFAULT 'The Hollow Spire',
            level INTEGER DEFAULT 1,
            gold INTEGER DEFAULT 1000,
            gems INTEGER DEFAULT 500,
            ingredients INTEGER DEFAULT 50,
            aether INTEGER DEFAULT 0,
            materials TEXT DEFAULT '{}',
            highest_floor INTEGER DEFAULT 0,
            max_roster_size INTEGER DEFAULT 10,
            unlocked_features TEXT DEFAULT '[]',
            research_points INTEGER DEFAULT 0,
            global_buffs TEXT DEFAULT '{}',
            pity_counter INTEGER DEFAULT 0,
            spark_points INTEGER DEFAULT 0,
            equip_spark_points INTEGER DEFAULT 0,
            last_training_tick TIMESTAMP,
            last_fatigue_tick TIMESTAMP
        , last_research_tick TIMESTAMP, last_mage_tick TIMESTAMP, last_alchemist_tick TIMESTAMP, last_restaurant_tick TIMESTAMP, master_name TEXT, tutorial_complete INTEGER DEFAULT 0, difficulty TEXT DEFAULT 'normal',
            total_summons INTEGER DEFAULT 0, total_battles_won INTEGER DEFAULT 0,
            arena_wins INTEGER DEFAULT 0, arena_losses INTEGER DEFAULT 0);

CREATE TABLE IF NOT EXISTS achievements_claimed (
            id TEXT PRIMARY KEY,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            floor_number INTEGER,
            event_type TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS portrait_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            birth_star INTEGER NOT NULL,
            path TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , gender TEXT, class_name TEXT);

CREATE TABLE IF NOT EXISTS facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_id INTEGER DEFAULT 1,
            type TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            slots_unlocked INTEGER DEFAULT 1
        );

CREATE TABLE IF NOT EXISTS facility_assignments (
            facility_id INTEGER REFERENCES facilities(id),
            hero_id INTEGER REFERENCES heroes(id),
            role TEXT,
            target_hero_id INTEGER,
            target_skill_id TEXT,
            UNIQUE(hero_id)
        );

CREATE TABLE IF NOT EXISTS hero_chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT DEFAULT 'The Square',
            message TEXT NOT NULL,
            participants TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            materials_json TEXT NOT NULL, -- e.g. {"Iron": 3, "Slime": 1}
            gold_cost INTEGER DEFAULT 0,
            base_stat_mult REAL DEFAULT 1.0, -- multiplier for stats based on crafter power
            is_discovered INTEGER DEFAULT 1
        );

CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            rarity TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            base_str INTEGER DEFAULT 0,
            base_int INTEGER DEFAULT 0,
            base_hlt INTEGER DEFAULT 0,
            base_agi INTEGER DEFAULT 0,
            base_def INTEGER DEFAULT 0,
            base_end INTEGER DEFAULT 0,
            base_wil INTEGER DEFAULT 0,
            base_luck INTEGER DEFAULT 0,
            str_pct REAL DEFAULT 0.0,
            int_pct REAL DEFAULT 0.0,
            hlt_pct REAL DEFAULT 0.0,
            agi_pct REAL DEFAULT 0.0,
            crit_chance REAL DEFAULT 0.0,
            dodge_chance REAL DEFAULT 0.0,
            armor_pen REAL DEFAULT 0.0,
            dmg_reduction_pct REAL DEFAULT 0.0,
            is_equipped_to INTEGER REFERENCES heroes(id),
            set_family TEXT,
            weapon_type TEXT,
            armor_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS hero_relics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relic_type TEXT NOT NULL,
            name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            desc TEXT,
            effect TEXT NOT NULL,
            min_star INTEGER DEFAULT 1,
            is_equipped_to INTEGER REFERENCES heroes(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS legacies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hero_id INTEGER,
            hero_name TEXT,
            hero_star INTEGER,
            title TEXT,
            flavor_text TEXT,
            bonus_json TEXT,
            score INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            item_type TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            description TEXT
        );

CREATE TABLE IF NOT EXISTS base_upgrades (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            level INTEGER DEFAULT 0,
            max_level INTEGER DEFAULT 5,
            unlocked INTEGER DEFAULT 0
        );

CREATE TABLE IF NOT EXISTS hero_bonds (
    hero_a_id INTEGER,
    hero_b_id INTEGER,
    bond_level REAL DEFAULT 0,
    floors_together INTEGER DEFAULT 0,
    PRIMARY KEY (hero_a_id, hero_b_id)
);

CREATE TABLE IF NOT EXISTS mail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    rewards_json TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    is_claimed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO base (id) VALUES (1);

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Basic Sword', 'weapon', 'A sturdy basic sword.', '{"Iron Ore": 3, "Monster Bone": 1}', 100, 1.0, 1
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Basic Sword');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Basic Armor', 'armor', 'Standard protective gear.', '{"Dark Crystal": 2, "Iron Ore": 2}', 100, 1.0, 1
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Basic Armor');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Basic Ring', 'accessory', 'A simple ring with minor enchantments.', '{"Mystic Dust": 3, "Goblin Ear": 1}', 100, 1.0, 1
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Basic Ring');

-- Blueprint-discoverable recipes — hidden until found via the 15% post-combat
-- blueprint roll (see routers/tower.py). Mix of mid-tier (common materials,
-- found on any floor) and high-tier (gated behind the rare material pool,
-- which itself only drops floor 30+) so later discoveries feel like a real step up.
INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Steel Broadsword', 'weapon', 'A broadsword forged from refined steel.', '{"Steel": 4, "Iron Ore": 2}', 300, 1.6, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Steel Broadsword');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Leather Vest', 'armor', 'Light, flexible protection favoring mobility over raw defense.', '{"Leather": 4, "Copper": 1}', 250, 1.4, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Leather Vest');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Hunters Charm', 'accessory', 'A trinket said to favor the wearer''s fortune in the field.', '{"Goblin Ear": 3, "Mystic Dust": 2}', 280, 1.5, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Hunters Charm');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Mithril Chainmail', 'armor', 'Chainmail woven from mithril thread — light as cloth, hard as steel.', '{"Mithril": 3, "Steel": 3}', 900, 2.4, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Mithril Chainmail');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Adamantine Greatblade', 'weapon', 'A blade of near-indestructible adamantine.', '{"Adamantine": 3, "Steel": 2}', 950, 2.5, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Adamantine Greatblade');

INSERT INTO recipes (name, type, description, materials_json, gold_cost, base_stat_mult, is_discovered)
SELECT 'Void Ring', 'accessory', 'A ring carved from a shard of crystallized void.', '{"Void Crystal": 2, "Mystic Dust": 3}', 1000, 2.6, 0
WHERE NOT EXISTS (SELECT 1 FROM recipes WHERE name = 'Void Ring');







        """)

        try:
            conn.execute("ALTER TABLE base ADD COLUMN gems INTEGER DEFAULT 500")
            print("[DB] Migrated: added column 'gems' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE portrait_cache ADD COLUMN gender TEXT")
            print("[DB] Migrated: added column 'gender' to portrait_cache")
        except sqlite3.OperationalError:
            pass
            
        try:
            conn.execute("ALTER TABLE portrait_cache ADD COLUMN class_name TEXT")
            print("[DB] Migrated: added column 'class_name' to portrait_cache")
        except sqlite3.OperationalError:
            pass
            
        for col in ["lifetime_kills", "sole_survivor_boss_clears", "leader_clears", "unique_floor_clears"]:
            try:
                conn.execute(f"ALTER TABLE heroes ADD COLUMN {col} INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN xp INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'xp' to heroes")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN max_roster_size INTEGER DEFAULT 10")
            print("[DB] Migrated: added column 'max_roster_size' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN materials TEXT DEFAULT '{}'")
            print("[DB] Migrated: added column 'materials' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN last_rest_time REAL DEFAULT 0")
            print("[DB] Migrated: added column 'last_rest_time' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN last_tournament_time REAL DEFAULT 0")
            print("[DB] Migrated: added column 'last_tournament_time' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN portrait_style_version INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'portrait_style_version' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN last_train_tick TIMESTAMP")
            print("[DB] Migrated: added column 'last_train_tick' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN fairy_gender TEXT")
            print("[DB] Migrated: added column 'fairy_gender' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN equip_spark_points INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'equip_spark_points' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN master_name TEXT")
            print("[DB] Migrated: added column 'master_name' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN tutorial_complete INTEGER DEFAULT 0")
            # Backfill: an existing save with real progress already lived
            # through everything the tutorial would teach — don't make it
            # pop up retroactively on profiles that aren't brand new.
            conn.execute(
                "UPDATE base SET tutorial_complete = 1 WHERE highest_floor > 0 "
                "OR EXISTS (SELECT 1 FROM heroes)"
            )
            print("[DB] Migrated: added column 'tutorial_complete' to base")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE base ADD COLUMN difficulty TEXT DEFAULT 'normal'")
            print("[DB] Migrated: added column 'difficulty' to base (existing profiles default to normal)")
        except sqlite3.OperationalError:
            pass

        # Achievement-tracking counters. total_summons/total_battles_won
        # backfill from existing data so a save that's been played for a
        # while doesn't start every counter at zero — arena_wins/losses
        # have no equivalent existing data (arena results live in the
        # separate arena_server, not synced back here yet) so those start
        # at 0 regardless of save age.
        for col, default, backfill_sql in [
            ("total_summons", "INTEGER DEFAULT 0", "UPDATE base SET total_summons = (SELECT COUNT(*) FROM heroes)"),
            ("total_battles_won", "INTEGER DEFAULT 0", "UPDATE base SET total_battles_won = (SELECT COALESCE(SUM(lifetime_kills), 0) FROM heroes)"),
            ("arena_wins", "INTEGER DEFAULT 0", None),
            ("arena_losses", "INTEGER DEFAULT 0", None),
            ("arena_elo", "INTEGER DEFAULT 1000", None),
        ]:
            try:
                conn.execute(f"ALTER TABLE base ADD COLUMN {col} {default}")
                if backfill_sql:
                    conn.execute(backfill_sql)
                print(f"[DB] Migrated: added column '{col}' to base")
            except sqlite3.OperationalError:
                pass

        # Stat rework: Endurance replaces Defense (same mitigation role, but
        # also drives max_health going forward) and Willpower/Luck are new.
        # Old defense/base_def columns are left in place, inert, rather than
        # risking a SQLite column rename/drop on live save files.
        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN endurance INTEGER DEFAULT 5")
            conn.execute("UPDATE heroes SET endurance = defense")
            print("[DB] Migrated: added column 'endurance' to heroes (backfilled from defense)")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN willpower INTEGER DEFAULT 6")
            conn.execute("ALTER TABLE heroes ADD COLUMN luck INTEGER DEFAULT 5")
            # Existing heroes have no prior willpower/luck to copy — roll them
            # fresh, scaled to birth_star same as new hero generation, so
            # already-pulled heroes aren't punished relative to future pulls.
            wil_by_star = {1: 6, 2: 7, 3: 9, 4: 12, 5: 16, 6: 21, 7: 28}
            luck_by_star = {1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 6: 10, 7: 12}
            rows = conn.execute("SELECT id, birth_star FROM heroes").fetchall()
            for r in rows:
                star = r["birth_star"] or 1
                wil = max(1, int(wil_by_star.get(star, 6) * random.uniform(0.9, 1.1)))
                luck = max(1, int(luck_by_star.get(star, 5) * random.uniform(0.9, 1.1)))
                conn.execute("UPDATE heroes SET willpower = ?, luck = ? WHERE id = ?", (wil, luck, r["id"]))
            print(f"[DB] Migrated: added columns 'willpower'/'luck' to heroes, backfilled {len(rows)} hero(es)")
        except sqlite3.OperationalError:
            pass

        # Who made it. Only ever set by the forge — gacha and drop equipment
        # has no maker and stays NULL, which is the honest answer for a blade
        # that fell out of a chest. Feeds the chained craft deed: when a
        # legendary piece goes on to do something worth recording, the smith
        # who never left the base gets the deed for it.
        try:
            conn.execute("ALTER TABLE equipment ADD COLUMN crafted_by INTEGER")
            print("[DB] Migrated: added column 'crafted_by' to equipment")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE equipment ADD COLUMN base_end INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE equipment ADD COLUMN base_wil INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE equipment ADD COLUMN base_luck INTEGER DEFAULT 0")
            conn.execute("UPDATE equipment SET base_end = base_def")
            print("[DB] Migrated: added columns 'base_end'/'base_wil'/'base_luck' to equipment (base_end backfilled from base_def)")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE legacies ADD COLUMN is_sacrifice INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'is_sacrifice' to legacies")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE legacies ADD COLUMN portrait_path TEXT")
            print("[DB] Migrated: added column 'portrait_path' to legacies")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE equipment ADD COLUMN str_pct REAL DEFAULT 0.0")
            conn.execute("ALTER TABLE equipment ADD COLUMN int_pct REAL DEFAULT 0.0")
            conn.execute("ALTER TABLE equipment ADD COLUMN hlt_pct REAL DEFAULT 0.0")
            conn.execute("ALTER TABLE equipment ADD COLUMN agi_pct REAL DEFAULT 0.0")
            print("[DB] Migrated: added pct columns to equipment")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE equipment ADD COLUMN base_def INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE equipment ADD COLUMN dmg_reduction_pct REAL DEFAULT 0.0")
            print("[DB] Migrated: added base_def/dmg_reduction_pct columns to equipment")
        except sqlite3.OperationalError:
            pass

        # Mage weapons are grimoires now (art changed from staves to tomes) —
        # rename both the type tag and any item names that contain it. Safe to
        # re-run: both UPDATEs are no-ops once nothing matches.
        try:
            changed = conn.execute("UPDATE equipment SET weapon_type = 'Tome' WHERE weapon_type = 'Staff'").rowcount
            changed += conn.execute("UPDATE equipment SET name = REPLACE(name, 'Staff', 'Tome') WHERE name LIKE '%Staff%'").rowcount
            if changed:
                print(f"[DB] Migrated: renamed Staff weapons to Tome ({changed} row update(s))")
        except sqlite3.OperationalError:
            pass

        # Accessory sub-types (Ring/Amulet/Charm) — same shape as
        # weapon_type/armor_type. Existing accessories get a random sub-type
        # so they participate in the new dual-accessory-slot system.
        try:
            conn.execute("ALTER TABLE equipment ADD COLUMN accessory_type TEXT")
            rows = conn.execute("SELECT id, name FROM equipment WHERE type = 'Accessory'").fetchall()
            for r in rows:
                acc_type = random.choice(["Ring", "Amulet", "Charm"])
                new_name = r["name"].replace("Accessory", acc_type) if "Accessory" in r["name"] else r["name"]
                conn.execute("UPDATE equipment SET accessory_type = ?, name = ? WHERE id = ?", (acc_type, new_name, r["id"]))
            print(f"[DB] Migrated: added 'accessory_type' to equipment, backfilled {len(rows)} accessory(ies)")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("UPDATE facilities SET type = 'The Lobby' WHERE type = 'The Square'")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error for The Lobby: {e}")

        try:
            conn.execute("UPDATE facilities SET type = 'Market' WHERE type = 'The Market'")
            conn.execute("UPDATE facilities SET type = 'Farm' WHERE type = 'The Farm'")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error for Market/Farm rename: {e}")

        try:
            conn.execute("DELETE FROM facility_assignments WHERE facility_id IN (SELECT id FROM facilities WHERE type IN ('Training Center', 'Training Facility', 'Watchtower'))")
            conn.execute("DELETE FROM facilities WHERE type IN ('Training Center', 'Training Facility', 'Watchtower')")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error removing unused facilities: {e}")

        # Workshop -> Skydock rename (it becomes the magic-battleship dock;
        # 'Workshop' clashed with the Forge's identity anyway).
        try:
            conn.execute("UPDATE facilities SET type = 'Skydock' WHERE type = 'Workshop'")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error renaming Workshop: {e}")

        # Restaurant -> Dining Hall rename (existing saves keep their level
        # and staff, just under the new name).
        try:
            conn.execute("UPDATE facilities SET type = 'Dining Hall' WHERE type = 'Restaurant'")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error renaming Restaurant: {e}")

        # Mirror of Fate graduated from the base-upgrade tree to a real
        # facility (floor 25). Existing purchased upgrade levels (1-3) map
        # to facility levels 5/10/15 so nobody loses reveal detail — see
        # level_service.reveal_mirror_of_fate for the level->detail tiers.
        try:
            old = conn.execute("SELECT level FROM base_upgrades WHERE id = 'mirror_of_fate'").fetchone()
            if old and old["level"] > 0:
                existing = conn.execute("SELECT id FROM facilities WHERE base_id = 1 AND type = 'Mirror of Fate'").fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO facilities (base_id, type, level, slots_unlocked) VALUES (1, 'Mirror of Fate', ?, 1)",
                        (old["level"] * 5,)
                    )
                conn.execute("DELETE FROM base_upgrades WHERE id = 'mirror_of_fate'")
                conn.commit()
                print("[DB] Migrated: Mirror of Fate base-upgrade -> facility")
        except Exception as e:
            print(f"[DB] Migration error converting Mirror of Fate: {e}")

        # One-time realignment: a hero whose first LLM enrichment failed kept
        # a fallback name, got a portrait generated for THAT identity
        # (custom_hero_{id}_{name}_{ts}.png), then was silently RE-NAMED by a
        # later reconcile — leaving the card's name drifting off the face.
        # Restore each such hero's name from the identity their portrait was
        # actually made for, so name and face match again. (The forward fix
        # in gacha.reconcile_pending_profiles stops this recurring.)
        try:
            import re as _re
            hero_rows = conn.execute(
                "SELECT id, name, portrait_path FROM heroes WHERE portrait_path LIKE '%custom_hero_%'"
            ).fetchall()
            realigned = 0
            for hr in hero_rows:
                m = _re.search(r"custom_hero_(\d+)_(.+?)_\d+\.png$", hr["portrait_path"] or "")
                if not m or int(m.group(1)) != hr["id"]:
                    continue
                portrait_name = m.group(2).replace("_", " ").strip().title()
                if portrait_name and portrait_name.lower() != (hr["name"] or "").lower():
                    # Don't create a duplicate name in the roster.
                    clash = conn.execute(
                        "SELECT 1 FROM heroes WHERE LOWER(name) = ? AND id != ?",
                        (portrait_name.lower(), hr["id"]),
                    ).fetchone()
                    if not clash:
                        conn.execute("UPDATE heroes SET name = ? WHERE id = ?", (portrait_name, hr["id"]))
                        realigned += 1
            if realigned:
                conn.commit()
                print(f"[DB] Migrated: realigned {realigned} hero name(s) to match their portrait identity")
        except Exception as e:
            print(f"[DB] Migration error realigning hero names: {e}")

        # Supplies are retired. The Farm now grows alchemy INGREDIENTS (food,
        # herbs — cooking and potion crafting), and AETHER (Skydock-refined
        # ship fuel) covers what supplies did for expeditions. Existing
        # supplies convert 1:1 into ingredients so nothing is lost.
        base_cols = [r[1] for r in conn.execute("PRAGMA table_info(base)").fetchall()]
        if "ingredients" not in base_cols:
            conn.execute("ALTER TABLE base ADD COLUMN ingredients INTEGER DEFAULT 50")
            if "supplies" in base_cols:
                conn.execute("UPDATE base SET ingredients = COALESCE(supplies, 50)")
            print("[DB] Migrated: base.ingredients (converted from supplies)")
        if "aether" not in base_cols:
            conn.execute("ALTER TABLE base ADD COLUMN aether INTEGER DEFAULT 0")
            print("[DB] Migrated: base.aether")
        if "supplies" in base_cols:
            try:
                conn.execute("ALTER TABLE base DROP COLUMN supplies")
                print("[DB] Migrated: dropped base.supplies")
            except sqlite3.OperationalError:
                pass  # old SQLite without DROP COLUMN — column just goes unused

        # Slime Core is retired (Dark Crystal replaced it) — convert any the
        # player is holding, plus every recipe that still calls for it.
        try:
            row = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
            if row and row["materials"] and "Slime Core" in row["materials"]:
                import json as _json
                mats = _json.loads(row["materials"])
                for k in list(mats.keys()):
                    if k.startswith("Slime Core"):
                        new_k = k.replace("Slime Core", "Dark Crystal")
                        mats[new_k] = mats.get(new_k, 0) + mats.pop(k)
                conn.execute("UPDATE base SET materials = ? WHERE id = 1", (_json.dumps(mats),))
                print("[DB] Migrated: Slime Core -> Dark Crystal in held materials")
            conn.execute("UPDATE recipes SET materials_json = REPLACE(materials_json, 'Slime Core', 'Dark Crystal') WHERE materials_json LIKE '%Slime Core%'")
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error converting Slime Core: {e}")

        # Every base starts with the Wall (its foundation — other facilities
        # can't out-level it), Training Grounds, and Dining Hall already
        # built (existing saves gain them too if missing) — everything else
        # is player-built through the Facilities tab.
        try:
            for fac_type in ("Wall", "Training Grounds", "Dining Hall"):
                existing = conn.execute("SELECT id FROM facilities WHERE base_id = 1 AND type = ?", (fac_type,)).fetchone()
                if not existing:
                    conn.execute("INSERT INTO facilities (base_id, type, slots_unlocked) VALUES (1, ?, 1)", (fac_type,))
            conn.commit()
        except Exception as e:
            print(f"[DB] Migration error seeding default facilities: {e}")

        # Mirror miniboss variant is retired (no counterplay — teams died to
        # their own comp with nothing to adjust). Re-roll any cached
        # miniboss_mirror floors to one of the remaining variants.
        try:
            rows = conn.execute("SELECT floor_number FROM floor_cache WHERE floor_type = 'miniboss_mirror'").fetchall()
            for r in rows:
                variant = random.choice(["survival", "behemoth", "assassin", "twins"])
                conn.execute("UPDATE floor_cache SET floor_type = ? WHERE floor_number = ?", (f"miniboss_{variant}", r["floor_number"]))
            if rows:
                print(f"[DB] Migrated: re-rolled {len(rows)} cached miniboss_mirror floor(s)")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN is_favorite INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'is_favorite' to heroes")
        except sqlite3.OperationalError:
            pass

        # Gifting/loyalty track (0-100) — raised by gifts (services/
        # gift_service.py), consumed by upcoming loyalty/raid mechanics.
        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN affinity INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'affinity' to heroes")
        except sqlite3.OperationalError:
            pass

        # Raid capture / Rebellious Phase (see routers/raid.py):
        #  is_prisoner   — hero arrived via raid capture, not the gacha
        #  rebellion     — 0-100 loyalty to their ORIGINAL master; >0 means
        #                  the Rebellious Phase: cannot be deployed until
        #                  broken down with time, gifts, and base resources
        #  original_master — arena username they were taken from
        #  is_captured   — this hero of OURS was taken in a raid we lost;
        #                  alive somewhere else, but gone from this roster
        for _col, _ddl in (("is_prisoner", "INTEGER DEFAULT 0"),
                           ("rebellion", "INTEGER DEFAULT 0"),
                           ("original_master", "TEXT"),
                           ("is_captured", "INTEGER DEFAULT 0")):
            try:
                conn.execute(f"ALTER TABLE heroes ADD COLUMN {_col} {_ddl}")
                print(f"[DB] Migrated: added column '{_col}' to heroes")
            except sqlite3.OperationalError:
                pass

        # Floor type is rolled once per floor number and cached here so
        # re-entering the same floor (rerun) always gives the same floor type.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS floor_cache (
                floor_number INTEGER PRIMARY KEY,
                floor_type TEXT NOT NULL,
                visited INTEGER DEFAULT 0
            )
        """)

        # Lore Journal — one entry generated and cached per 10-floor milestone
        # cleared (10, 20, 30...). Generated once, then frozen forever, same
        # caching shape as floor_cache above — a milestone's lore text must
        # never change after the player has already read it.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lore_entries (
                milestone INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # One row per floor actually resolved — what was fought / what choice
        # was made. This is the raw material the Lore Journal draws from so
        # each save's pages reflect ITS OWN run (different mobs, different
        # event choices) rather than identical generic text for everyone.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS floor_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                floor_number INTEGER NOT NULL,
                floor_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # A fight is resolved instantly server-side, but the player watches it
        # play out as a timed animation. Committing hero DEATHS immediately
        # spoiled them on the Heroes/Memorial tabs the instant you entered a
        # floor — long before the animation reached that turn. So a fallen
        # hero's death is DEFERRED into a row here and only applied once the
        # fight's real-time timeline has elapsed (client calls /floor/finalize
        # when its animation ends, or a hero read lazily reveals overdue rows).
        # See services/combat_reveal_service.py.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_combat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                floor_number INTEGER,
                dead_ids TEXT NOT NULL,
                reveal_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)

        # Migrate existing DB — add columns if they don't exist
        existing = [r[1] for r in conn.execute("PRAGMA table_info(heroes)").fetchall()]
        migrations = [
            ("hero_class",  "ALTER TABLE heroes ADD COLUMN hero_class TEXT DEFAULT 'Classless'"),
            ("can_pilot",   "ALTER TABLE heroes ADD COLUMN can_pilot INTEGER DEFAULT 0"),
            ("level",       "ALTER TABLE heroes ADD COLUMN level INTEGER DEFAULT 1"),
            ("ego_patience", "ALTER TABLE heroes ADD COLUMN ego_patience INTEGER DEFAULT 100"),
            ("is_team_leader", "ALTER TABLE heroes ADD COLUMN is_team_leader INTEGER DEFAULT 0"),
            ("battle_tendency", "ALTER TABLE heroes ADD COLUMN battle_tendency TEXT"),
            ("condition", "ALTER TABLE heroes ADD COLUMN condition TEXT DEFAULT 'Normal'"),
            ("condition_until", "ALTER TABLE heroes ADD COLUMN condition_until TEXT"),
            ("near_wipes_survived", "ALTER TABLE heroes ADD COLUMN near_wipes_survived INTEGER DEFAULT 0"),
            ("unique_floors_cleared", "ALTER TABLE heroes ADD COLUMN unique_floors_cleared INTEGER DEFAULT 0"),
            ("defense", "ALTER TABLE heroes ADD COLUMN defense INTEGER DEFAULT 5"),
            ("equipped_consumable", "ALTER TABLE heroes ADD COLUMN equipped_consumable TEXT"),
            ("talent_reveal", "ALTER TABLE heroes ADD COLUMN talent_reveal TEXT"),
            # Training Grounds mentorship track — how many students this hero
            # has mentored. Used by the legacy qualification gate (a career
            # mentor earns remembrance even if they never cleared a floor).
            ("mentored_count", "ALTER TABLE heroes ADD COLUMN mentored_count INTEGER DEFAULT 0"),
            # Total XP this hero has transferred as a mentor — feeds the
            # legacy gate (a mentor who gave great gains is remembered).
            ("mentor_xp_given", "ALTER TABLE heroes ADD COLUMN mentor_xp_given INTEGER DEFAULT 0"),
            # Sparring (Training Grounds) per-hero cooldown timestamp.
            ("last_spar_time", "ALTER TABLE heroes ADD COLUMN last_spar_time REAL DEFAULT 0"),
            # Training Grounds solo-drill state (see services/training_service.py).
            # regimen: which drill a TG-assigned hero is running; focus: the
            # stat (conditioning) or skill id (weapon drill) it targets;
            # intensity: light/moderate/intense (gain vs fatigue/stress trade);
            # training_gains: cumulative base-stat points earned from drills,
            # tracked so the per-stat cap (scales with TG level) is enforceable.
            ("training_regimen", "ALTER TABLE heroes ADD COLUMN training_regimen TEXT"),
            ("training_focus", "ALTER TABLE heroes ADD COLUMN training_focus TEXT"),
            ("training_intensity", "ALTER TABLE heroes ADD COLUMN training_intensity TEXT DEFAULT 'moderate'"),
            ("training_gains", "ALTER TABLE heroes ADD COLUMN training_gains TEXT DEFAULT '{}'"),
        ]
        for col, sql in migrations:
            if col not in existing:
                conn.execute(sql)
                print(f"[DB] Migrated: added column '{col}'")

        existing_eq = [r[1] for r in conn.execute("PRAGMA table_info(equipment)").fetchall()]
        eq_migrations = [
            ("set_family", "ALTER TABLE equipment ADD COLUMN set_family TEXT"),
            ("weapon_type", "ALTER TABLE equipment ADD COLUMN weapon_type TEXT"),
            ("armor_type", "ALTER TABLE equipment ADD COLUMN armor_type TEXT"),
        ]

        # floor_cache.visited: mark previously-cleared floors as visited so
        # existing saves don't lose all their visible floor history on upgrade.
        existing_fc = [r[1] for r in conn.execute("PRAGMA table_info(floor_cache)").fetchall()]
        if "visited" not in existing_fc:
            conn.execute("ALTER TABLE floor_cache ADD COLUMN visited INTEGER DEFAULT 0")
            conn.execute(
                "UPDATE floor_cache SET visited = 1 WHERE floor_number <= "
                "(SELECT COALESCE(highest_floor, 0) FROM base WHERE id = 1)"
            )
            print("[DB] Migrated: floor_cache.visited (marked cleared floors as visited)")
        for col, sql in eq_migrations:
            if col not in existing_eq:
                conn.execute(sql)
                print(f"[DB] Migrated: added column 'equipment.{col}'")

        # hero_bonds.spar_sessions: sparring/training together builds the same
        # bond as fighting together (see sparring_service). Bond level is now
        # derived from floors_together + spar_sessions combined.
        existing_hb = [r[1] for r in conn.execute("PRAGMA table_info(hero_bonds)").fetchall()]
        if "spar_sessions" not in existing_hb:
            conn.execute("ALTER TABLE hero_bonds ADD COLUMN spar_sessions INTEGER DEFAULT 0")
            print("[DB] Migrated: added column 'hero_bonds.spar_sessions'")

        # Directional mentor->student relationships (hero-card display).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mentorships (
                mentor_id INTEGER,
                student_id INTEGER,
                sessions INTEGER DEFAULT 0,
                xp_given INTEGER DEFAULT 0,
                PRIMARY KEY (mentor_id, student_id)
            )
        """)

    print("Database initialized.")
