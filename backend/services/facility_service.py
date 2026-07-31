from database import db

# "Early Game Rush" pacing: every CORE facility is unlocked by floor 25 —
# the real gate on base power is gold (upgrade costs double per level),
# not floor level. The four endgame facilities (floor 30-75) exist so the
# base keeps growing content-wise after the rush.
FACILITY_TYPES = {
    # The Wall is a STARTER facility (seeded pre-built alongside Training
    # Grounds and Dining Hall) and the base's foundation: no other facility
    # can be upgraded above the Wall's level — see upgrade_facility.
    "Wall": {"cost": 2000, "unlock_floor": 1, "max_level": 50},
    "Training Grounds": {"cost": 1500, "unlock_floor": 1, "max_level": 50},
    "Dining Hall": {"cost": 5000, "unlock_floor": 1, "max_level": 50},
    "Farm": {"cost": 1000, "unlock_floor": 2, "max_level": 50},
    "Market": {"cost": 1000, "unlock_floor": 2, "max_level": 50},
    "Forge": {"cost": 2500, "unlock_floor": 5, "max_level": 50},
    "Infirmary": {"cost": 2500, "unlock_floor": 5, "max_level": 50},
    # The Athenaeum runs the discipline/confluence research map — see
    # services/athenaeum_service.py for the tree and its effect hooks.
    "Athenaeum": {"cost": 6000, "unlock_floor": 8, "max_level": 50},
    "Vault": {"cost": 5000, "unlock_floor": 10, "max_level": 50},
    "Alchemist Lab": {"cost": 8000, "unlock_floor": 10, "max_level": 50},
    "Tavern": {"cost": 7000, "unlock_floor": 15, "max_level": 50},
    "Skydock": {"cost": 10000, "unlock_floor": 15, "max_level": 50},
    "Bastion": {"cost": 12000, "unlock_floor": 20, "max_level": 50},
    "Shrine": {"cost": 15000, "unlock_floor": 20, "max_level": 50},
    "Mage Tower": {"cost": 20000, "unlock_floor": 25, "max_level": 50},
    # Mirror of Fate graduated from a "base upgrade" to a real facility —
    # its level now sets how much of a hero's Talent each reveal exposes
    # (see level_service.reveal_mirror_of_fate).
    "Mirror of Fate": {"cost": 20000, "unlock_floor": 25, "max_level": 50},
    # ── Endgame facilities (floors 30-75) ──
    "Bestiary": {"cost": 30000, "unlock_floor": 30, "max_level": 50},
    "Reliquary": {"cost": 50000, "unlock_floor": 40, "max_level": 50},
    "Chronosphere": {"cost": 80000, "unlock_floor": 50, "max_level": 50},
    "Transcendence Core": {"cost": 250000, "unlock_floor": 75, "max_level": 50},
}

def init_base_facilities():
    # Deprecated: No longer auto-upgrades slots.
    pass

def get_facilities():
    try:
        with db() as conn:
            # Re-calc slots just in case
            slots = init_base_facilities()
            
            facilities = conn.execute("SELECT * FROM facilities WHERE base_id = 1").fetchall()
            fac_list = [dict(f) for f in facilities]
            
            # Load assignments
            assigned = conn.execute("""
                SELECT fa.facility_id, fa.role, fa.target_hero_id, fa.target_skill_id, h.id, h.name, h.hero_class, h.level, h.portrait_path, h.apt_tactical, h.skills, h.birth_star, h.ascension_star
                FROM facility_assignments fa
                JOIN heroes h ON fa.hero_id = h.id
                WHERE h.is_alive = 1
            """).fetchall()
            
            wall_row = next((f for f in fac_list if f["type"] == "Wall"), None)
            wall_level = wall_row["level"] if wall_row else 0

            for f in fac_list:
                f["heroes"] = [dict(a) for a in assigned if a["facility_id"] == f["id"]]
                f["max_slots"] = f["slots_unlocked"]

                # Player-specific art, when this profile has generated its own
                # (outdoor facilities rendered against their Wall). None means
                # "use the shipped image" — the frontend keeps its existing
                # tier logic as the fallback and never needs to know the rule.
                try:
                    from services.facility_art_service import art_url, art_tier_for_level
                    f["art_url"] = art_url(f["type"].lower().replace(" ", "_"),
                                           art_tier_for_level(f["level"]))
                except Exception:
                    f["art_url"] = None

                # Calculate upgrade cost
                info = FACILITY_TYPES.get(f["type"], {"cost": 5000, "max_level": 50})
                f["max_level"] = info.get("max_level", 50)
                base_cost = info["cost"] * (2 ** (f["level"] - 1))
                f["upgrade_cost"] = int(base_cost * (1 - get_workshop_discount(conn, f["type"])))
                # Foundation cap: non-Wall facilities can't be upgraded above
                # the Wall's current level.
                f["wall_capped"] = f["type"] != "Wall" and (f["level"] + 1) > wall_level
                f["can_upgrade"] = f["level"] < f["max_level"] and not f["wall_capped"]
                f["next_slots"] = f["slots_unlocked"] + 1
                
            built_types = [f["type"] for f in fac_list]
            
            # Also return available facilities to build
            base = conn.execute("SELECT highest_floor, gold FROM base WHERE id = 1").fetchone()
            highest = base["highest_floor"]
            
            available_to_build = []
            for f_type, info in FACILITY_TYPES.items():
                if f_type not in built_types:
                    available_to_build.append({
                        "type": f_type,
                        "cost": info["cost"],
                        "unlock_floor": info["unlock_floor"],
                        "can_build": highest >= info["unlock_floor"] and base["gold"] >= info["cost"],
                        "floor_restricted": highest < info["unlock_floor"]
                    })
            
            available_to_build.sort(key=lambda x: x["cost"])
            fac_list.sort(key=lambda x: FACILITY_TYPES.get(x["type"], {"cost": 0})["cost"])
                    
            return {
                "built": fac_list,
                "available": available_to_build,
                "gold": base["gold"]
            }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

def build_facility(facility_type: str):
    if facility_type not in FACILITY_TYPES:
        raise ValueError("Invalid facility type")
        
    info = FACILITY_TYPES[facility_type]
    
    with db() as conn:
        base = conn.execute("SELECT highest_floor, gold FROM base WHERE id = 1").fetchone()
        if base["highest_floor"] < info["unlock_floor"]:
            raise ValueError(f"Requires floor {info['unlock_floor']} to build.")
        if base["gold"] < info["cost"]:
            raise ValueError("Not enough gold.")
            
        existing = conn.execute("SELECT id FROM facilities WHERE base_id = 1 AND type = ?", (facility_type,)).fetchone()
        if existing:
            raise ValueError("Already built.")
            
        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (info["cost"],))
        conn.execute("INSERT INTO facilities (base_id, type, slots_unlocked) VALUES (1, ?, 1)", (facility_type,))
        
    return {"ok": True}

def get_workshop_discount(conn, fac_type: str) -> float:
    """Skydock (renamed from Workshop — it's the future home of magic
    battleship construction) discounts the gold cost of upgrading every
    OTHER facility, scaling with its level plus any assigned Magic
    Engineers. Capped at 50% off so upgrading never becomes free, and
    doesn't discount upgrading the Skydock itself."""
    if fac_type == "Skydock":
        return 0.0
    workshop = conn.execute("SELECT id, level FROM facilities WHERE type = 'Skydock' AND base_id = 1").fetchone()
    if not workshop:
        return 0.0
    assigned = conn.execute("""
        SELECT h.hero_class FROM facility_assignments fa
        JOIN heroes h ON fa.hero_id = h.id
        WHERE fa.facility_id = ? AND h.is_alive = 1
    """, (workshop["id"],)).fetchall()
    engineer_bonus = sum(0.03 if a["hero_class"] == "Magic Engineer" else 0.01 for a in assigned)
    return min(0.5, 0.01 * (workshop["level"] - 1) + engineer_bonus)

def upgrade_facility(facility_id: int):
    with db() as conn:
        fac = conn.execute("SELECT * FROM facilities WHERE id = ?", (facility_id,)).fetchone()
        if not fac:
            raise ValueError("Facility not found.")

        fac_type = fac["type"]
        info = FACILITY_TYPES.get(fac_type)
        if not info:
            raise ValueError("Unknown facility type.")

        level = fac["level"]
        max_level = info.get("max_level", 50)
        if level >= max_level:
            raise ValueError("Facility is already at maximum level.")

        # The Wall is the base's foundation: nothing may be upgraded ABOVE
        # its level (art parity too — a tier-2 Farm assumes tier-2 Walls).
        if fac_type != "Wall":
            wall = conn.execute("SELECT level FROM facilities WHERE type = 'Wall' AND base_id = 1").fetchone()
            wall_level = wall["level"] if wall else 0
            if level + 1 > wall_level:
                raise ValueError(f"The Wall must reach Level {level + 1} first — no structure can outgrow the foundation it stands on.")

        cost = info["cost"] * (2 ** (level - 1))
        cost = int(cost * (1 - get_workshop_discount(conn, fac_type)))

        base = conn.execute("SELECT gold FROM base WHERE id = 1").fetchone()
        if base["gold"] < cost:
            raise ValueError(f"Not enough gold. Need {cost}g.")
            
        conn.execute("UPDATE base SET gold = gold - ? WHERE id = 1", (cost,))
        # Increase level, and occasionally increase slots_unlocked (every 5 levels)
        new_level = level + 1
        new_slots = 1 + (new_level // 5)
        conn.execute("UPDATE facilities SET level = ?, slots_unlocked = ? WHERE id = ?", (new_level, new_slots, facility_id))
        fac_type = fac["type"]
        wall_row = conn.execute("SELECT level FROM facilities WHERE type = 'Wall' AND base_id = 1").fetchone()
        wall_lvl = wall_row["level"] if wall_row else 1

    # Re-render this facility's art with the player's own Wall behind it, if
    # it's an outdoor one and generation is on. Queued on a thread and outside
    # the db block: a build must never wait ~30s on a render, and must never
    # fail because one didn't work.
    try:
        from services.facility_art_service import queue_for_facility, art_tier_for_level
        queue_for_facility(fac_type.lower().replace(" ", "_"),
                           art_tier_for_level(new_level), art_tier_for_level(wall_lvl))
    except Exception as e:
        print(f"[FacilityArt] skipped on upgrade: {e}")

    return {"ok": True, "new_level": new_level}

def assign_hero_to_facility(facility_id: int, hero_id: int, role: str = None, target_hero_id: int = None, target_skill_id: str = None):
    with db() as conn:
        # Verify facility exists
        fac = conn.execute("SELECT slots_unlocked FROM facilities WHERE id = ?", (facility_id,)).fetchone()
        if not fac:
            raise ValueError("Facility not found")
            
        # Verify hero is alive
        hero = conn.execute("SELECT is_alive FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not hero or hero["is_alive"] == 0:
            raise ValueError("Hero not available")
            
        # Check if slots are full (only counting living heroes)
        current = conn.execute("""
            SELECT count(*) as c FROM facility_assignments fa
            JOIN heroes h ON fa.hero_id = h.id
            WHERE fa.facility_id = ? AND h.is_alive = 1
        """, (facility_id,)).fetchone()
        if current["c"] >= fac["slots_unlocked"]:
            raise ValueError("Facility is full.")
            
        # Remove hero from any other facility
        conn.execute("DELETE FROM facility_assignments WHERE hero_id = ?", (hero_id,))
        
        # Add to facility
        conn.execute("INSERT INTO facility_assignments (facility_id, hero_id, role, target_hero_id, target_skill_id) VALUES (?, ?, ?, ?, ?)", 
                     (facility_id, hero_id, role, target_hero_id, target_skill_id))
        
    return {"ok": True}

def remove_hero_from_facility(hero_id: int):
    with db() as conn:
        conn.execute("DELETE FROM facility_assignments WHERE hero_id = ?", (hero_id,))
    return {"ok": True}
