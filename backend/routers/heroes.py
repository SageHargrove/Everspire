from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from database import db
from pydantic import BaseModel
from services.level_service import get_revealed_aptitudes, recalculate_hero_level, get_talent_title, estimate_talent_rarity
from services.materials_service import get_material_total, consume_material
from services.combat_reveal_service import reveal_due_combats
import json
import random
import os

router = APIRouter()

def row_to_hero(row, equipment_rows=[], is_ego_satisfied=None) -> dict:
    from services.class_service import get_class_evolution_options
    from services.equipment_service import apply_equipment_stats
    from services.level_service import apply_level_to_stats
    h = dict(row)
    # Raw DB values, preserved before level/equipment scaling so anything
    # that needs the true unscaled base (ascension checks, etc.) still can.
    h["base_strength"] = h["strength"]
    h["base_intelligence"] = h["intelligence"]
    h["base_defense"] = h.get("defense", 5)
    h["base_endurance"] = h.get("endurance", h.get("defense", 5))
    h["base_agility"] = h["agility"]
    h["base_willpower"] = h.get("willpower", 6)
    h["base_luck"] = h.get("luck", 5)
    h["base_max_hp"] = h["max_health"]
    h = apply_level_to_stats(h)
    h["equipment"] = [dict(e) for e in equipment_rows if e["is_equipped_to"] == h["id"]]
    h["evolution_options"] = get_class_evolution_options(h["hero_class"], h.get("level", 1))
    h = apply_equipment_stats(h, h["equipment"])
    if is_ego_satisfied is not None:
        h["is_ego_satisfied"] = is_ego_satisfied
    # Mana is combat-session-only state (see combat_service.py's CombatUnit)
    # — there's no stored "current mana" outside a fight — but Max Mana is
    # a pure function of post-equipment INT/WIL, so it's safe to surface
    # here for the hero stat sheet even though no fight is running.
    from services.gacha_service import mana_from_stats
    h["max_mana"] = mana_from_stats(h["intelligence"], h.get("willpower", 6))
    return h

@router.get("/{hero_id}/card-image")
def get_hero_card_image(hero_id: int, mini: bool = False):
    """Tier-templated card art — the portrait's background is cut away and
    composited onto a decorative bronze/silver/gold/prismatic background by
    services/card_template_service.py. Built lazily on first request, then
    cached to disk (services/card_template_service.composite_card handles
    cache invalidation when the portrait itself changes).

    mini=True returns a face-cropped variant sized for small grid thumbnails
    instead of the full head-to-chest card — see composite_card's docstring."""
    with db() as conn:
        hero = conn.execute("SELECT portrait_path, birth_star, name, hero_class FROM heroes WHERE id = ?", (hero_id,)).fetchone()
    if not hero or not hero["portrait_path"] or not os.path.exists(hero["portrait_path"]):
        raise HTTPException(status_code=404, detail="No portrait available for this hero.")

    from services.card_template_service import composite_card
    try:
        card_path = composite_card(hero_id, hero["portrait_path"], hero["birth_star"], hero["name"], crop_face=mini, hero_class=hero["hero_class"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Card compositing failed: {e}")
    return FileResponse(card_path, media_type="image/png")

@router.get("/")
def list_heroes(alive_only: bool = False):
    import datetime
    reveal_due_combats()  # apply any fight whose animation window has elapsed
    with db() as conn:
        now = datetime.datetime.utcnow().isoformat()
        conn.execute("UPDATE heroes SET condition = 'Normal', condition_until = NULL WHERE condition_until IS NOT NULL AND condition_until < ?", (now,))
        conn.commit()

        query = "SELECT * FROM heroes"
        if alive_only:
            query += " WHERE is_alive = 1"
        query += " ORDER BY birth_star DESC, created_at DESC"
        rows = conn.execute(query).fetchall()
        
        # Fetch equipment for all listed heroes
        hero_ids = [r["id"] for r in rows]
        if hero_ids:
            placeholders = ",".join("?" * len(hero_ids))
            equipment_rows = conn.execute(f"SELECT * FROM equipment WHERE is_equipped_to IN ({placeholders})", hero_ids).fetchall()
        else:
            equipment_rows = []
            
        # Calculate ego satisfaction for heroes on teams
        from services.ego_service import check_ego_satisfaction
        teams = {}
        alive_rows = [dict(r) for r in rows if r["is_alive"]]
        for r in alive_rows:
            if r["is_on_team"]:
                teams.setdefault(r["is_on_team"], []).append(r)
        
        satisfaction_map = {}
        for r in alive_rows:
            if r["ego_type"] and r["is_on_team"]:
                team_members = teams[r["is_on_team"]]
                satisfaction_map[r["id"]] = check_ego_satisfaction(r, team_members, alive_rows)
            
    return [row_to_hero(r, equipment_rows, satisfaction_map.get(r["id"])) for r in rows]

# ─── Legacy & Bond endpoints ───────────────────────────────────────
# Must be registered before /{hero_id} below — FastAPI matches routes in
# registration order, so a static single-segment path like /legacies or
# /bonds registered AFTER /{hero_id} gets swallowed by it (hero_id="legacies"
# fails int parsing -> 422) and is never reachable. Both were silently dead
# routes until this reordering.

@router.get("/legacies")
def list_legacies():
    """List all fallen hero legacies and their bonuses."""
    reveal_due_combats()  # a just-fallen hero's legacy shows here — reveal first
    from services.legacy_service import get_all_legacies, get_active_legacy_bonuses
    return {
        "legacies": get_all_legacies(),
        "active_bonuses": get_active_legacy_bonuses(),
    }

@router.get("/bonds")
def list_bonds():
    """List all hero bonds."""
    with db() as conn:
        rows = conn.execute("""
            SELECT hb.*, h1.name as hero_a_name, h2.name as hero_b_name
            FROM hero_bonds hb
            JOIN heroes h1 ON h1.id = hb.hero_a_id
            JOIN heroes h2 ON h2.id = hb.hero_b_id
            WHERE hb.bond_level > 0
            ORDER BY hb.bond_level DESC
        """).fetchall()
    return [dict(r) for r in rows]

# Must be registered BEFORE /{hero_id} — a static two-segment path like
# /{id}/relationships is fine, but keeping relationship routes grouped here
# with the other list routes above /{hero_id} avoids any future ambiguity.
def _attachment_label(sessions: int) -> str:
    """Flavor for how a student feels about a mentor, by how much they've
    trained together — a lot of sessions builds real attachment."""
    if sessions >= 10:
        return "reveres"
    if sessions >= 5:
        return "looks up to"
    if sessions >= 2:
        return "learns from"
    return "trained under"


class ManagerSparReq(BaseModel):
    mult: float = 1.0


@router.post("/{hero_id}/manager-spar")
def manager_spar(hero_id: int, req: ManagerSparReq):
    """THE COMMANDER'S TABLE — the manager sits across the board from a hero
    and plays them at stones (Training Grounds minigame). A won game pours XP
    into the hero (scaled by the difficulty multiplier, server-clamped ×3);
    a LEGENDARY humiliation (mult 0) stresses them instead. Once per day per
    hero — there's no material cost to gate it, so the calendar does."""
    from services.level_service import recalculate_hero_level
    with db() as conn:
        try:
            conn.execute("ALTER TABLE heroes ADD COLUMN last_manager_spar TEXT")
        except Exception:
            pass
        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead")
        hero = dict(hero)
        today = conn.execute("SELECT DATE('now')").fetchone()[0]
        if hero.get("last_manager_spar") == today:
            raise HTTPException(status_code=400, detail=f"{hero['name']} has already sat at the board today.")

        mult = max(0.0, min(3.0, req.mult or 0.0))
        conn.execute("UPDATE heroes SET last_manager_spar = ? WHERE id = ?", (today, hero_id))

        if mult <= 0.05:
            # Crushed on the board — a bruised ego, nothing learned.
            conn.execute("UPDATE heroes SET stress = MIN(100, COALESCE(stress,0) + 8) WHERE id = ?", (hero_id,))
            return {"ok": True, "humiliated": True, "xp": 0,
                    "message": f"{hero['name']} stares at the board a long moment, then leaves without a word."}

        xp = int((120 + (hero.get("level") or 1) * 18) * mult)
        new_xp = (hero.get("xp") or 0) + xp
        hero["xp"] = new_xp
        new_level = recalculate_hero_level(hero)
        leveled = new_level > (hero.get("level") or 1)
        conn.execute("UPDATE heroes SET xp = ?, level = ?, affinity = MIN(100, COALESCE(affinity,0) + 2) WHERE id = ?",
                     (new_xp, new_level, hero_id))
        apt_up = False
        if mult >= 2.0:
            # A hard-fought loss against a strong opponent teaches command.
            conn.execute("UPDATE heroes SET apt_leadership = COALESCE(apt_leadership, 50) + 1 WHERE id = ?", (hero_id,))
            apt_up = True
        return {"ok": True, "xp": xp, "new_level": new_level, "leveled": leveled,
                "leadership_up": apt_up,
                "message": f"{hero['name']} resets the stones, eyes brighter than before."}


@router.get("/{hero_id}/deeds")
def hero_deeds(hero_id: int):
    """Permanent accomplishment records for a hero — mined from real fights
    (boss kills, death-saves, swarm stands…). Persists after death, so the
    Memorial can tell a fallen hero's story."""
    with db() as conn:
        from services.deeds_service import get_hero_deeds
        return get_hero_deeds(conn, hero_id)


@router.get("/{hero_id}/relationships")
def hero_relationships(hero_id: int):
    """Who this hero is bonded to — mentors they learned under, students
    they raised, and rivals/comrades from sparring and battle. Powers the
    Bonds section on the hero card."""
    with db() as conn:
        hero = conn.execute("SELECT id, name FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found")

        # Ensure the mentorships table exists (old saves).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mentorships (
                mentor_id INTEGER, student_id INTEGER,
                sessions INTEGER DEFAULT 0, xp_given INTEGER DEFAULT 0,
                PRIMARY KEY (mentor_id, student_id)
            )
        """)

        mentors = conn.execute("""
            SELECT m.mentor_id AS id, h.name, m.sessions, m.xp_given
            FROM mentorships m JOIN heroes h ON h.id = m.mentor_id
            WHERE m.student_id = ? AND h.is_alive = 1
            ORDER BY m.sessions DESC
        """, (hero_id,)).fetchall()

        students = conn.execute("""
            SELECT m.student_id AS id, h.name, m.sessions, m.xp_given
            FROM mentorships m JOIN heroes h ON h.id = m.student_id
            WHERE m.mentor_id = ? AND h.is_alive = 1
            ORDER BY m.sessions DESC
        """, (hero_id,)).fetchall()

        # Bonds (excluding pure mentor/student pairs, which are shown above).
        mentor_ids = {r["id"] for r in mentors} | {r["id"] for r in students}
        bond_rows = conn.execute("""
            SELECT hb.hero_a_id, hb.hero_b_id, hb.bond_level, hb.floors_together,
                   COALESCE(hb.spar_sessions, 0) AS spar_sessions,
                   h1.name AS a_name, h2.name AS b_name,
                   h1.is_alive AS a_alive, h2.is_alive AS b_alive
            FROM hero_bonds hb
            JOIN heroes h1 ON h1.id = hb.hero_a_id
            JOIN heroes h2 ON h2.id = hb.hero_b_id
            WHERE (hb.hero_a_id = ? OR hb.hero_b_id = ?) AND hb.bond_level > 0
            ORDER BY hb.bond_level DESC
        """, (hero_id, hero_id)).fetchall()

        bonds = []
        for r in bond_rows:
            other_id = r["hero_b_id"] if r["hero_a_id"] == hero_id else r["hero_a_id"]
            other_name = r["b_name"] if r["hero_a_id"] == hero_id else r["a_name"]
            other_alive = r["b_alive"] if r["hero_a_id"] == hero_id else r["a_alive"]
            if not other_alive:
                continue
            # Sparring-forged (rival) vs battle-forged (comrade).
            kind = "rival" if r["spar_sessions"] > r["floors_together"] else "comrade"
            bonds.append({
                "id": other_id, "name": other_name, "bond_level": int(r["bond_level"]),
                "kind": kind, "is_mentor_pair": other_id in mentor_ids,
            })

        return {
            "mentors": [
                {"id": m["id"], "name": m["name"], "sessions": m["sessions"],
                 "xp_given": m["xp_given"], "attachment": _attachment_label(m["sessions"])}
                for m in mentors
            ],
            "students": [
                {"id": s["id"], "name": s["name"], "sessions": s["sessions"], "xp_given": s["xp_given"]}
                for s in students
            ],
            "bonds": bonds,
        }


@router.get("/{hero_id}")
def get_hero(hero_id: int):
    reveal_due_combats()  # apply any fight whose animation window has elapsed
    with db() as conn:
        row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Hero not found")
        equipment_rows = conn.execute("SELECT * FROM equipment WHERE is_equipped_to = ?", (hero_id,)).fetchall()
    return row_to_hero(row, equipment_rows)

@router.post("/{hero_id}/regenerate-profile")
def regenerate_profile(hero_id: int):
    """Force an update or regeneration of a hero's portrait, and completely rewrite name/lore if it was a fallback."""
    with db() as conn:
        row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Hero not found")
        
        hero = dict(row)
        
        fallback_names = [
            "Valerius", "Kaelen", "Elara", "Tavian", "Seris", "Rykard", "Isolde", "Jerrick", "Nia", "Lorien", "Darius",
            "Fenris", "Vanya", "Corvus", "Sylas", "Myra", "Bram", "Gael", "Aria", "Thorne", "Lysander", "Rowan",
            "Cassia", "Kira", "Orion", "Soren", "Eira", "Vesper", "Caelum", "Juno", "Silas", "Evander", "Nyssa",
            "Theron", "Lirael", "Aelar", "Zephyr", "Rhea", "Kael", "Lyra", "Ignis", "Nyx", "Sol", "Nova", "Aura"
        ]
        
        is_fallback = hero["name"] in fallback_names or hero["name"].startswith("Unknown")
        # Reroll the hero's look through the full house-style pipeline
        # (race/hair/eyes/outfit/tier flavor + BASE_STYLE) — the old
        # hardcoded one-liner here bypassed all of it, so "Regenerate
        # Portrait" produced generic off-style art that barely changed.
        from services.portrait_cache import build_appearance_prompt
        prompt = build_appearance_prompt(hero["birth_star"], hero.get("hero_class", "Classless"), hero.get("gender", "unknown"))
        
        # If it was a fallback, completely regenerate the LLM profile
        if is_fallback:
            from services.llm_service import generate_hero_profile
            aptitudes = {
                "apt_combat": hero["apt_combat"],
                "apt_tactical": hero["apt_tactical"],
                "apt_survival": hero["apt_survival"],
                "apt_mental": hero["apt_mental"],
                "apt_leadership": hero["apt_leadership"]
            }
            try:
                profile = generate_hero_profile(hero["birth_star"], aptitudes)
                conn.execute("""
                    UPDATE heroes 
                    SET name = ?, title = ?, backstory = ?, personality = ?, gender = ?
                    WHERE id = ?
                """, (profile.name, profile.title, profile.backstory, profile.personality, getattr(profile, "gender", "unknown"), hero_id))
                prompt = profile.portrait_prompt
                hero["gender"] = getattr(profile, "gender", "unknown")
            except Exception as e:
                print(f"Regen failed: {e}")
        
        from services.portrait_cache import queue_custom_portrait
        queue_custom_portrait(hero_id, prompt, hero["name"] if not is_fallback else "Regenerated", hero.get("gender", "unknown"))
        return {"ok": True, "message": "Profile regenerating! Portrait and lore will update shortly."}

@router.delete("/{hero_id}")
def dismiss_hero(hero_id: int):
    """Dismiss (remove) a hero from roster. Not the same as death."""
    with db() as conn:
        hero = conn.execute("SELECT portrait_path FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        # Remove from any tower run teams first (foreign key constraint)
        conn.execute("DELETE FROM run_heroes WHERE hero_id = ?", (hero_id,))
        # Remove from active team
        conn.execute("UPDATE heroes SET is_on_team = 0, is_team_leader = 0 WHERE id = ?", (hero_id,))
        # Delete the hero
        conn.execute("DELETE FROM heroes WHERE id = ?", (hero_id,))
        
    if hero and hero["portrait_path"]:
        try:
            import os
            path = hero["portrait_path"]
            if "default_" not in path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return {"ok": True}

class BulkDismissRequest(BaseModel):
    hero_ids: list[int]

@router.post("/dismiss-bulk")
def dismiss_heroes_bulk(req: BulkDismissRequest):
    """Dismiss multiple heroes at once."""
    deleted_count = 0
    with db() as conn:
        for hero_id in req.hero_ids:
            hero = conn.execute("SELECT portrait_path FROM heroes WHERE id = ?", (hero_id,)).fetchone()
            if not hero:
                continue
            
            conn.execute("DELETE FROM run_heroes WHERE hero_id = ?", (hero_id,))
            conn.execute("UPDATE heroes SET is_on_team = 0, is_team_leader = 0 WHERE id = ?", (hero_id,))
            conn.execute("DELETE FROM heroes WHERE id = ?", (hero_id,))
            
            if hero["portrait_path"]:
                try:
                    import os
                    path = hero["portrait_path"]
                    if "default_" not in path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            deleted_count += 1
            
    return {"ok": True, "deleted_count": deleted_count}

class TeamUpdate(BaseModel):
    team_id: int = 1
    hero_ids: list[int]

BASE_TEAM_SIZE = 5

@router.post("/team/set")
def set_team(data: TeamUpdate):
    if data.team_id < 1 or data.team_id > 10:
        raise HTTPException(status_code=400, detail="Team ID must be between 1 and 10")

    with db() as conn:
        max_team_size = BASE_TEAM_SIZE
        if len(data.hero_ids) > max_team_size:
            raise HTTPException(status_code=400, detail=f"Max {max_team_size} heroes per team.")
        # Raid captives in the Rebellious Phase can't be deployed until won
        # over, and heroes captured FROM us aren't here to deploy at all.
        if data.hero_ids:
            placeholders = ",".join("?" * len(data.hero_ids))
            blocked = conn.execute(
                f"""SELECT name, COALESCE(rebellion, 0) AS rebellion, COALESCE(is_captured, 0) AS is_captured
                    FROM heroes WHERE id IN ({placeholders})
                    AND (COALESCE(rebellion, 0) > 0 OR COALESCE(is_captured, 0) = 1)""",
                data.hero_ids,
            ).fetchall()
            if blocked:
                b = blocked[0]
                reason = ("is a prisoner in their Rebellious Phase — win them over first"
                          if b["rebellion"] > 0 else "was captured in a raid and is no longer at your base")
                raise HTTPException(status_code=400, detail=f"{b['name']} {reason}.")
        # Clear this specific team
        conn.execute("UPDATE heroes SET is_on_team = 0, team_position = 0, is_team_leader = 0 WHERE is_on_team = ?", (data.team_id,))
        # Set new team
        for idx, hid in enumerate(data.hero_ids):
            # Also ensures hero is removed from any other team they were on
            conn.execute("UPDATE heroes SET is_on_team = ?, team_position = ? WHERE id = ? AND is_alive = 1", (data.team_id, idx, hid))
    return {"ok": True, "team_id": data.team_id, "team": data.hero_ids}

@router.post("/{hero_id}/remove-from-team")
def remove_hero_from_team(hero_id: int):
    """Pull one hero off whatever team they're currently on — usable directly
    from the All Heroes view without first switching to that team's tab."""
    with db() as conn:
        conn.execute("UPDATE heroes SET is_on_team = 0, team_position = 0, is_team_leader = 0 WHERE id = ?", (hero_id,))
    return {"ok": True, "hero_id": hero_id}

class AssignLeaderReq(BaseModel):
    hero_id: int

@router.post("/team/assign-leader")
def assign_team_leader(data: AssignLeaderReq):
    """Toggle a hero as their team's Leader. Any alive hero on a team is eligible -
    mechanical effects (ego recommendation, conflict tension) only kick in if the
    assigned hero has an ego_type; otherwise it's a flavor/narrative designation."""
    with db() as conn:
        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (data.hero_id,)).fetchone()
        if not hero or not hero["is_on_team"]:
            raise HTTPException(status_code=400, detail="Hero must be on a team to be named Leader.")
        team_id = hero["is_on_team"]
        if hero["is_team_leader"]:
            conn.execute("UPDATE heroes SET is_team_leader = 0 WHERE id = ?", (data.hero_id,))
            return {"ok": True, "team_id": team_id, "leader_id": None, "message": f"{hero['name']} stepped down as Leader."}
        conn.execute("UPDATE heroes SET is_team_leader = 0 WHERE is_on_team = ?", (team_id,))
        conn.execute("UPDATE heroes SET is_team_leader = 1 WHERE id = ?", (data.hero_id,))
    return {"ok": True, "team_id": team_id, "leader_id": data.hero_id, "message": f"{hero['name']} is now the team's Leader."}

class ReorderTeamReq(BaseModel):
    team_id: int
    hero_ids: list[int]

@router.post("/team/reorder")
def reorder_team(data: ReorderTeamReq):
    with db() as conn:
        for idx, hid in enumerate(data.hero_ids):
            conn.execute("UPDATE heroes SET team_position = ? WHERE id = ? AND is_on_team = ?", (idx, hid, data.team_id))
    return {"ok": True}

class EgoAutoReq(BaseModel):
    team_id: int
    ego_hero_id: int

@router.post("/team/ego_auto")
def ego_auto_team(data: EgoAutoReq):
    from services.ego_service import auto_assign_ego_team
    try:
        new_team = auto_assign_ego_team(data.ego_hero_id, data.team_id)
        return {"ok": True, "team": new_team}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/team/{team_id}/leader-recommendation")
def get_team_leader_recommendation(team_id: int):
    from services.ego_service import get_team_leader, get_ego_conflicts, get_ego_recommendation
    with db() as conn:
        team_members = [dict(r) for r in conn.execute(
            "SELECT * FROM heroes WHERE is_on_team = ? AND is_alive = 1", (team_id,)
        ).fetchall()]
        alive_heroes = [dict(r) for r in conn.execute("SELECT * FROM heroes WHERE is_alive = 1").fetchall()]

    leader = get_team_leader(team_members)
    if not leader:
        return {"has_leader": False, "has_ego": False}
    if not leader.get("ego_type"):
        return {"has_leader": True, "has_ego": False, "leader_id": leader["id"], "leader_name": leader["name"], "battle_tendency": leader.get("battle_tendency")}

    recommendation = get_ego_recommendation(leader["id"])
    conflicts = get_ego_conflicts(leader, team_members, alive_heroes)
    return {
        "has_leader": True, "has_ego": True,
        "leader_id": leader["id"], "leader_name": leader["name"],
        "battle_tendency": leader.get("battle_tendency"),
        **recommendation,
        "conflicts": conflicts,
    }

@router.get("/team/current")
def get_team():
    reveal_due_combats()  # apply any fight whose animation window has elapsed
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM heroes WHERE is_on_team = 1 AND is_alive = 1 ORDER BY team_position ASC, id ASC"
        ).fetchall()
    return [row_to_hero(r) for r in rows]

# Must be registered after /team/current above — /team/{team_id} would
# otherwise swallow it (team_id="current" fails int parsing -> 422), same
# anti-pattern as /{hero_id} vs /legacies and /bonds elsewhere in this file.
@router.get("/team/{team_id}")
def get_team_by_id(team_id: int):
    reveal_due_combats()  # apply any fight whose animation window has elapsed
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM heroes WHERE is_on_team = ? AND is_alive = 1 ORDER BY team_position ASC, id ASC", (team_id,)
        ).fetchall()
    return [row_to_hero(r) for r in rows]

@router.get("/teams/all")
def get_all_teams():
    reveal_due_combats()  # apply any fight whose animation window has elapsed
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM heroes WHERE is_on_team > 0 AND is_alive = 1 ORDER BY is_on_team ASC, team_position ASC, id ASC"
        ).fetchall()
        
    teams = {i: [] for i in range(1, 11)}
    for r in rows:
        if r["is_on_team"] in teams:
            teams[r["is_on_team"]].append(row_to_hero(r))
    return teams


# ─── Aptitude reveal endpoint ───────────────────────────────────────

@router.get("/{hero_id}/aptitudes")
def get_hero_aptitudes(hero_id: int):
    """Return revealed aptitudes for a hero based on their level."""
    from services.base_service import get_base_upgrade_level
    with db() as conn:
        row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        archive_level = get_base_upgrade_level(conn, "archive")
    if not row:
        raise HTTPException(status_code=404, detail="Hero not found")
    hero = dict(row)
    revealed = get_revealed_aptitudes(hero, archive_level)
    rarity = estimate_talent_rarity(hero, archive_level)
    return {
        "hero_id": hero_id, "level": hero.get("level", 1), "aptitudes": revealed,
        "talent_rarity_one_in": round(rarity) if rarity else None,
        "talent_title": get_talent_title(hero, archive_level),
    }


# ─── Synthesis endpoint ─────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    target_id: int
    # Single-sacrifice callers keep working via sacrifice_id; the chamber
    # sends sacrifice_ids for multi-offering rites.
    sacrifice_id: int | None = None
    sacrifice_ids: list[int] | None = None

# Each additional soul consumed in the SAME rite hits every witness harder
# than the last — a mass sacrifice is a categorically worse thing to watch
# than several spaced-out ones. Wave i (0-based) is scaled by 1 + i*0.25.
MASS_RITE_ESCALATION = 0.25

@router.post("/synthesize")
def synthesize_hero(data: SynthesizeRequest):
    """
    Sacrifice one or more heroes to empower another. Grants XP (through the
    normal leveling pipeline), may pass on skills/traits, and traumatizes
    every living witness — compounding per sacrifice in a multi-offering rite.
    """
    import random
    from services.morale_service import get_morale_state
    from services.level_service import recalculate_hero_level

    ids = data.sacrifice_ids if data.sacrifice_ids else ([data.sacrifice_id] if data.sacrifice_id is not None else [])
    ids = list(dict.fromkeys(ids))  # dedupe, keep order
    if not ids:
        raise HTTPException(status_code=400, detail="No sacrifice selected.")
    if data.target_id in ids:
        raise HTTPException(status_code=400, detail="Cannot sacrifice a hero to themselves.")

    with db() as conn:
        target = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (data.target_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Target hero not found or dead.")
        target_dict = dict(target)

        sacrifices = []
        for sid in ids:
            row = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (sid,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Sacrifice hero {sid} not found or dead.")
            row = dict(row)
            # Favorites are protected fodder — enforced here too, not just in
            # the chamber UI, so no code path can accidentally consume one.
            if row.get("is_favorite"):
                raise HTTPException(status_code=400, detail=f"{row['name']} is a Favorite and cannot be sacrificed.")
            sacrifices.append(row)

        # XP per sacrifice: half their own earned XP plus a base worth by
        # star and level. Resonance (matching class) doubles that
        # sacrifice's contribution.
        total_xp = 0
        any_resonant = False
        msg_suffix = ""
        for sac in sacrifices:
            xp = int(sac.get("xp", 0) * 0.5) + 30 * sac["birth_star"] * sac["level"]
            if target_dict["hero_class"] == sac["hero_class"] and target_dict["hero_class"] != "Classless":
                xp *= 2
                any_resonant = True
            total_xp += xp
        if any_resonant:
            conn.execute("UPDATE heroes SET ego_type = 'Resonant' WHERE id = ?", (data.target_id,))
            msg_suffix += " EGO RESONANCE TRIGGERED!"

        # Inheritance rolls independently per sacrifice (50% each), skipping
        # anything the target already knows.
        a_skills = json.loads(target_dict.get("skills") or "[]")
        a_traits = json.loads(target_dict.get("traits") or "[]")
        skills_changed = traits_changed = False
        for sac in sacrifices:
            b_skills = json.loads(sac.get("skills") or "[]")
            b_traits = json.loads(sac.get("traits") or "[]")
            if random.random() < 0.5 and (b_skills or b_traits):
                inherited = random.choice(b_skills + b_traits)
                a_names = [x["name"] for x in a_skills + a_traits]
                if inherited["name"] not in a_names:
                    if inherited in b_skills:
                        a_skills.append(inherited)
                        skills_changed = True
                    else:
                        a_traits.append(inherited)
                        traits_changed = True
                    msg_suffix += f" Inherited {inherited['name']}!"
        if skills_changed:
            conn.execute("UPDATE heroes SET skills = ? WHERE id = ?", (json.dumps(a_skills), data.target_id))
        if traits_changed:
            conn.execute("UPDATE heroes SET traits = ? WHERE id = ?", (json.dumps(a_traits), data.target_id))

        # Apply XP and recalculate level through the normal pipeline.
        conn.execute("UPDATE heroes SET xp = xp + ? WHERE id = ?", (total_xp, data.target_id))
        t_row = conn.execute("SELECT * FROM heroes WHERE id = ?", (data.target_id,)).fetchone()
        levels_gained = 0
        if t_row:
            t_dict = dict(t_row)
            old_level = t_dict.get("level", 1)
            new_level = recalculate_hero_level(t_dict)
            if new_level != old_level:
                conn.execute("UPDATE heroes SET level = ? WHERE id = ?", (new_level, data.target_id))
                levels_gained = new_level - old_level
                msg_suffix += f" {target_dict['name']} reached level {new_level}!"

        for sac in sacrifices:
            conn.execute("UPDATE heroes SET is_alive = 0, is_on_team = 0, synthesized = 1 WHERE id = ?", (sac["id"],))

        # Trauma to all living witnesses: one wave per sacrifice, each wave
        # escalated by MASS_RITE_ESCALATION, accumulated in memory and
        # written once per hero. Observer confidence still applies per wave —
        # heroes stronger than the victim feel safer, weaker ones realize
        # nobody is safe.
        living_heroes = conn.execute(
            "SELECT * FROM heroes WHERE is_alive = 1 AND id != ?", (data.target_id,)
        ).fetchall()
        first_sac = sacrifices[0]
        base_trauma = 5 + first_sac["birth_star"]
        base_stress = 10 + first_sac["birth_star"] * 2

        def apply_waves(h, halve=False):
            """Accumulate every sacrifice's psychological hit onto hero dict h."""
            trauma_total = stress_total = morale_total = 0
            for i, sac in enumerate(sacrifices):
                escalation = 1.0 + i * MASS_RITE_ESCALATION
                trauma_gain = 5 + sac["birth_star"]
                stress_gain = 10 + sac["birth_star"] * 2
                morale_loss = -(8 + sac["birth_star"] * 2)
                if halve:
                    trauma_gain = max(2, trauma_gain // 2)
                    stress_gain = max(3, stress_gain // 2)
                    morale_loss = morale_loss // 2
                star_diff = h["birth_star"] - sac["birth_star"]
                level_diff = h.get("level", 1) - sac.get("level", 1)
                observer_mult = max(0.2, min(2.0, 1.0 - (star_diff * 0.15) - (level_diff * 0.01)))
                trauma_total += int(trauma_gain * observer_mult * escalation)
                stress_total += int(stress_gain * observer_mult * escalation)
                morale_total += int(morale_loss * observer_mult * escalation)
            new_trauma = min(100, h["trauma"] + trauma_total)
            new_stress = min(100, h["stress"] + stress_total)
            trauma_ceiling = 100 - int(new_trauma * 0.4)
            new_morale = max(0, min(trauma_ceiling, h["morale"] + morale_total))
            return new_trauma, new_stress, new_morale

        for hero in living_heroes:
            h = dict(hero)
            new_trauma, new_stress, new_morale = apply_waves(h)
            conn.execute(
                "UPDATE heroes SET trauma = ?, stress = ?, morale = ?, morale_state = ? WHERE id = ?",
                (new_trauma, new_stress, new_morale, get_morale_state(new_morale), hero["id"])
            )

        # Target's guilt: same waves at half strength.
        t_trauma, t_stress, t_morale = apply_waves(target_dict, halve=True)
        conn.execute(
            "UPDATE heroes SET trauma = ?, stress = ?, morale = ?, morale_state = ? WHERE id = ?",
            (t_trauma, t_stress, t_morale, get_morale_state(t_morale), data.target_id)
        )

        updated = conn.execute("SELECT * FROM heroes WHERE id = ?", (data.target_id,)).fetchone()

    names = ", ".join(s["name"] for s in sacrifices)
    plural = "souls were" if len(sacrifices) > 1 else "soul was"
    return {
        "ok": True,
        "target": dict(updated),
        "sacrifice_names": [s["name"] for s in sacrifices],
        "sacrifice_name": sacrifices[0]["name"],
        "sacrifice_star": sacrifices[0]["birth_star"],
        "xp_gained": total_xp,
        "levels_gained": levels_gained,
        "roster_trauma": base_trauma,
        "roster_stress": base_stress,
        "message": f"{len(sacrifices)} {plural} consumed ({names}). {target_dict['name']} absorbs {total_xp:,} XP.{msg_suffix}",
    }


# ─── Gifting ────────────────────────────────────────────────────────

class GiftRequest(BaseModel):
    gift_id: str

@router.get("/gifts/catalog")
def gift_catalog():
    from services.gift_service import get_catalog
    return {"gifts": get_catalog()}

@router.post("/{hero_id}/gift")
def give_hero_gift(hero_id: int, data: GiftRequest):
    from services.gift_service import give_gift
    try:
        return give_gift(hero_id, data.gift_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Favorites ──────────────────────────────────────────────────────

@router.post("/{hero_id}/favorite")
def toggle_favorite(hero_id: int):
    """Flip a hero's favorite flag — purely a player-side bookmark used by
    the Heroes tab's Favorites filter."""
    with db() as conn:
        row = conn.execute("SELECT is_favorite FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Hero not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE heroes SET is_favorite = ? WHERE id = ?", (new_val, hero_id))
        return {"id": hero_id, "is_favorite": bool(new_val)}


# ─── Ascension endpoint ─────────────────────────────────────────────
# Ascension is a risk/reward ritual, not a guaranteed purchase: it costs
# materials (consumed either way) and can fail, with failure chance rising
# the higher the ascension tier being attempted.

ASCENSION_MATERIAL_COST = {
    0: {"Iron Ore": 5, "Dark Crystal": 3},
    1: {"Iron Ore": 10, "Monster Bone": 5},
    2: {"Iron Ore": 18, "Monster Bone": 10, "Mystic Dust": 3},
    3: {"Monster Bone": 18, "Mystic Dust": 8, "Goblin Ear": 10},
    4: {"Mystic Dust": 15, "Goblin Ear": 20, "Iron Ore": 30},
    5: {"Mystic Dust": 25, "Monster Bone": 30, "Goblin Ear": 30},
    6: {"Mystic Dust": 40, "Monster Bone": 40, "Goblin Ear": 40, "Iron Ore": 40},
}

ASCENSION_FAIL_CHANCE = {0: 0.0, 1: 0.05, 2: 0.10, 3: 0.18, 4: 0.28, 5: 0.40, 6: 0.55}

ASCENSION_LEVEL_REQ = {
    0: 10,
    1: 20,
    2: 30,
    3: 40,
    4: 50,
    5: 60,
    6: 75,
}

@router.get("/{hero_id}/ascension-info")
def get_ascension_info(hero_id: int):
    """Preview cost/fail-chance for a hero's next ascension attempt, so the
    frontend doesn't have to duplicate the cost tables."""
    with db() as conn:
        hero = conn.execute("SELECT ascension_star, level FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead.")
        base = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
        materials = json.loads(base["materials"]) if base["materials"] else {}

    current_asc = hero["ascension_star"] or 0
    if current_asc >= 7:
        return {"maxed": True}
    required = ASCENSION_MATERIAL_COST.get(current_asc, {})
    return {
        "maxed": False,
        "current_ascension": current_asc,
        "level_req": ASCENSION_LEVEL_REQ.get(current_asc, 100),
        "hero_level": hero["level"],
        "materials_required": required,
        "materials_have": {m: get_material_total(materials, m) for m in required},
        "fail_chance": ASCENSION_FAIL_CHANCE.get(current_asc, 0.6),
    }

@router.post("/{hero_id}/ascend")
def ascend_hero(hero_id: int):
    """
    Ascend a hero to break their level cap. Costs materials (consumed on
    both success and failure) and can fail — failure chance rises with the
    ascension tier being attempted.
    """
    with db() as conn:
        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead.")
        hero = dict(hero)

        current_asc = hero.get("ascension_star", 0) or 0
        if current_asc >= 7:
            raise HTTPException(status_code=400, detail="Hero is already at max ascension.")

        # Check level requirement
        level_req = ASCENSION_LEVEL_REQ.get(current_asc, 100)
        hero_level = hero.get("level", 1)
        if hero_level < level_req:
            raise HTTPException(
                status_code=400,
                detail=f"Hero must be level {level_req} to ascend. Currently level {hero_level}."
            )

        # Check materials
        required = ASCENSION_MATERIAL_COST.get(current_asc, {})
        base = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
        materials = json.loads(base["materials"]) if base["materials"] else {}
        missing = {m: qty for m, qty in required.items() if get_material_total(materials, m) < qty}
        if missing:
            detail = ", ".join(f"{m} (need {q}, have {get_material_total(materials, m)})" for m, q in missing.items())
            raise HTTPException(status_code=400, detail=f"Not enough materials: {detail}")

        # Materials are spent on the attempt itself — that's the risk.
        # Spends lowest tier first so better material stays banked.
        for m, qty in required.items():
            consume_material(materials, m, qty)
        conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(materials),))

        fail_chance = ASCENSION_FAIL_CHANCE.get(current_asc, 0.6)
        if random.random() < fail_chance:
            conn.execute("UPDATE heroes SET stress = MIN(100, stress + 10) WHERE id = ?", (hero_id,))
            return {
                "ok": False,
                "failed": True,
                "hero_id": hero_id,
                "materials_spent": required,
                "fail_chance": fail_chance,
                "message": f"{hero['name']}'s ascension ritual failed! The materials were consumed in vain.",
            }

        new_asc = current_asc + 1
        conn.execute(
            "UPDATE heroes SET ascension_star = ? WHERE id = ?",
            (new_asc, hero_id)
        )

        # Recalculate level with new cap
        updated_hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        new_level = recalculate_hero_level(dict(updated_hero))
        conn.execute("UPDATE heroes SET level = ? WHERE id = ?", (new_level, hero_id))

        from services.portrait_cache import queue_custom_portrait
        prompt = f"dark fantasy anime {hero['hero_class']} portrait, {hero['current_star']} star rarity, {new_asc} star ascension"
        queue_custom_portrait(hero_id, prompt, hero["name"], hero.get("gender", "unknown"))

    return {
        "ok": True,
        "failed": False,
        "hero_id": hero_id,
        "new_ascension": new_asc,
        "materials_spent": required,
        "new_level": new_level,
        "message": f"{hero['name']} ascended to {new_asc}★ ascension!"
    }

# ─── Promotion endpoint (star rank upgrade = "Evolution") ──────────
#
# This is also "Evolution" — evolving a low-rarity hero into a higher one.
# It used to be pure gold; now it's a materials + reduced-gold hybrid,
# gated by how deep into the Tower the player has gone (base.highest_floor)
# rather than just having enough gold sitting in the bank. Deliberately
# NOT a separate mechanic from promotion — current_star/ascension_star/
# birth_star already overlap enough; a 4th star-adjacent system would only
# add confusion. Evolution material costs were tuned against the
# RARITY_WEIGHTS gacha curve overhaul (see gacha_service.py) — pulls now
# start heavily 1★/2★-weighted, so evolving low rarities up is meant to be
# the primary progression path, not a rare luxury.
EVOLUTION_GOLD_COST = {
    1: 100,     # 1★ → 2★
    2: 250,     # 2★ → 3★
    3: 600,     # 3★ → 4★
    4: 1500,    # 4★ → 5★
    5: 4000,    # 5★ → 6★
    6: 250000,  # 6★ → 7★ (TRANSCENDENCE — see below)
}

# 6★ → 7★ is TRANSCENDENCE (manhwa rule, Liam 2026-07-12): 7★ can never be
# summoned — this ritual is the ONLY way one exists. The cost is meant to
# be insane: a mountain of legendary materials plus Eternal Shards, which
# drop ONLY from Tower bosses at floor 80+ (see combat_service loot) and
# never appear in any gate, market, or generic drop pool.
EVOLUTION_MATERIAL_COST = {
    1: {"Iron Ore": 10, "Dark Crystal": 6},
    2: {"Iron Ore": 15, "Monster Bone": 10, "Wolf Pelt": 5},
    3: {"Monster Bone": 20, "Mystic Dust": 10, "Refined Iron": 10},
    4: {"Mystic Dust": 20, "Goblin Ear": 25, "Hardened Bone": 15, "Wyvern Scale": 5},
    5: {"Wyvern Scale": 15, "Enchanted Steel": 15, "Runed Crystal": 10, "Demon Ichor": 10},
    6: {"Mithril": 40, "Adamantine": 40, "Dragon Scale": 25, "Phoenix Feather": 15, "Eternal Shard": 7},
}

# Must have cleared at least this floor (base.highest_floor) before
# evolving a hero of this current_star — keeps evolution paced against
# Tower progress instead of being purely a gold/material stockpile check.
# Transcendence waits until floor 90: a 7★ is an end-of-the-Tower being.
EVOLUTION_FLOOR_GATE = {1: 10, 2: 20, 3: 31, 4: 41, 5: 61, 6: 90}

@router.post("/{hero_id}/promote")
def promote_hero(hero_id: int):
    """
    Promote (evolve) a hero to the next star rank.
    Requires hero to be at max level for their current star, the Tower
    progress to have reached EVOLUTION_FLOOR_GATE for this tier, and
    enough materials + gold (hybrid cost, not pure gold).
    """
    from services.level_service import level_cap, get_hero_star, STAR_LEVEL_CAPS

    with db() as conn:
        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead.")
        hero = dict(hero)

        current_star = get_hero_star(hero)
        if current_star >= 7:
            raise HTTPException(status_code=400, detail="Hero is already at max star rank.")

        # Must be at max level for current star
        max_lvl = level_cap(current_star, hero.get("ascension_star", 0))
        hero_level = hero.get("level", 1)
        if hero_level < max_lvl:
            raise HTTPException(
                status_code=400,
                detail=f"Hero must be level {max_lvl} to promote. Currently level {hero_level}."
            )

        base = conn.execute("SELECT gold, materials, highest_floor FROM base WHERE id = 1").fetchone()

        floor_gate = EVOLUTION_FLOOR_GATE.get(current_star, 0)
        if (base["highest_floor"] or 0) < floor_gate:
            raise HTTPException(
                status_code=400,
                detail=f"Must reach floor {floor_gate} before evolving a {current_star}★ hero. Highest floor: {base['highest_floor'] or 0}."
            )

        required_materials = EVOLUTION_MATERIAL_COST.get(current_star, {})
        materials = json.loads(base["materials"]) if base["materials"] else {}
        missing = {m: qty for m, qty in required_materials.items() if get_material_total(materials, m) < qty}
        if missing:
            detail = ", ".join(f"{m} (need {q}, have {get_material_total(materials, m)})" for m, q in missing.items())
            raise HTTPException(status_code=400, detail=f"Not enough materials: {detail}")

        gold_cost = EVOLUTION_GOLD_COST.get(current_star, 50000)
        if base["gold"] < gold_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough gold. Need {gold_cost}, have {base['gold']}."
            )

        # Deduct materials + gold, then promote
        for m, qty in required_materials.items():
            consume_material(materials, m, qty)
        conn.execute("UPDATE base SET gold = gold - ?, materials = ? WHERE id = 1", (gold_cost, json.dumps(materials)))
        new_star = current_star + 1

        # Check for hidden class unlock (1/2★ to 3★ promotion)
        unlocked_class = None
        if new_star >= 3 and hero.get("hidden_class"):
            unlocked_class = hero["hidden_class"]
            conn.execute(
                "UPDATE heroes SET current_star = ?, hero_class = ?, hidden_class = NULL WHERE id = ?",
                (new_star, unlocked_class, hero_id)
            )
        else:
            conn.execute(
                "UPDATE heroes SET current_star = ? WHERE id = ?",
                (new_star, hero_id)
            )

        # Stat boost on promotion: +10% all stats — except transcendence
        # (6★→7★), which surges +35%: a 7★ costs an empire to make and
        # should read as genuinely off the charts, not one more +10% step.
        boost_div = 3 if new_star == 7 else 10  # x + x/3 ≈ +33-35%
        conn.execute(f"""
            UPDATE heroes SET
                max_health = max_health + max_health / {boost_div},
                health = health + health / {boost_div},
                strength = strength + strength / {boost_div},
                intelligence = intelligence + intelligence / {boost_div},
                agility = agility + agility / {boost_div}
            WHERE id = ?
        """, (hero_id,))

        current_class = unlocked_class if unlocked_class else hero["hero_class"]
        # Every star, not just 3/5/7. The re-render is img2img from their own
        # portrait now, so each step is a visible upgrade to the same person
        # rather than a reroll — which is what made a sparse milestone list the
        # safer choice before.
        from services.portrait_cache import queue_upgrade_portrait
        queue_upgrade_portrait(hero_id, new_star)

    if new_star == 7:
        msg = f"{hero['name']} has TRANSCENDED. A seventh star burns — the Tower itself takes notice."
    else:
        msg = f"{hero['name']} evolved from {current_star}★ to {new_star}★!"
    if unlocked_class:
        msg += f" Hidden potential awakened: Class is now {unlocked_class}!"

    return {
        "ok": True,
        "hero_id": hero_id,
        "new_star": new_star,
        "old_star": current_star,
        "gold_spent": gold_cost,
        "materials_spent": required_materials,
        "unlocked_class": unlocked_class,
        "message": msg
    }

@router.get("/{hero_id}/evolution-info")
def get_evolution_info(hero_id: int):
    """Preview cost/floor-gate for a hero's next evolution (promote), so the
    frontend doesn't have to duplicate the cost tables."""
    from services.level_service import level_cap, get_hero_star

    with db() as conn:
        hero = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead.")
        hero = dict(hero)
        base = conn.execute("SELECT gold, materials, highest_floor FROM base WHERE id = 1").fetchone()
        materials = json.loads(base["materials"]) if base["materials"] else {}

    current_star = get_hero_star(hero)
    if current_star >= 7:
        return {"maxed": True}
    required = EVOLUTION_MATERIAL_COST.get(current_star, {})
    return {
        "maxed": False,
        "current_star": current_star,
        "max_level": level_cap(current_star, hero.get("ascension_star", 0)),
        "hero_level": hero.get("level", 1),
        "floor_gate": EVOLUTION_FLOOR_GATE.get(current_star, 0),
        "highest_floor": base["highest_floor"] or 0,
        "gold_cost": EVOLUTION_GOLD_COST.get(current_star, 50000),
        "gold_have": base["gold"],
        "materials_required": required,
        "materials_have": {m: get_material_total(materials, m) for m in required},
    }
class EvolveRequest(BaseModel):
    target_class: str

@router.post("/{hero_id}/evolve")
def evolve_hero(hero_id: int, req: EvolveRequest):
    from services.class_service import get_class_evolution_options
    with db() as conn:
        row = conn.execute("SELECT * FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Hero not found")
        hero = dict(row)
        options = get_class_evolution_options(hero["hero_class"], hero.get("level", 1))
        if req.target_class not in options:
            raise HTTPException(status_code=400, detail=f"Cannot evolve {hero['hero_class']} to {req.target_class}. Valid options: {options}")

        conn.execute("UPDATE heroes SET hero_class = ? WHERE id = ?", (req.target_class, hero_id))
        # The evolution gate (level_service.evolution_gate_level) held their
        # level at the milestone while XP kept banking — recalculate now so
        # the choice releases the dam immediately.
        hero["hero_class"] = req.target_class
        new_level = recalculate_hero_level(hero)
        levels_released = new_level - (hero.get("level") or 1)
        if levels_released > 0:
            conn.execute("UPDATE heroes SET level = ? WHERE id = ?", (new_level, hero_id))
    return {"ok": True, "new_class": req.target_class,
            "new_level": max(new_level, hero.get("level") or 1),
            "levels_released": max(0, levels_released)}

class EquipRequest(BaseModel):
    equipment_id: int

@router.post("/{hero_id}/equip")
def equip_item(hero_id: int, req: EquipRequest):
    with db() as conn:
        # Check hero
        hero = conn.execute("SELECT id FROM heroes WHERE id = ? AND is_alive = 1", (hero_id,)).fetchone()
        if not hero:
            raise HTTPException(status_code=404, detail="Hero not found or dead")
        
        # Check equip
        equip = conn.execute("SELECT * FROM equipment WHERE id = ?", (req.equipment_id,)).fetchone()
        if not equip:
            raise HTTPException(status_code=404, detail="Equipment not found")
        
        # If equipment is already equipped by someone else, remove it
        if equip["equipped_to"]:
            conn.execute("UPDATE equipment SET equipped_to = NULL WHERE id = ?", (equip["id"],))
            
        # Unequip whatever is currently in that slot for this hero
        conn.execute("UPDATE equipment SET equipped_to = NULL WHERE equipped_to = ? AND slot = ?", (hero_id, equip["slot"]))
        
        # Equip new item
        conn.execute("UPDATE equipment SET equipped_to = ? WHERE id = ?", (hero_id, equip["id"]))
        
    return {"ok": True}

@router.post("/{hero_id}/unequip")
def unequip_item(hero_id: int, req: EquipRequest):
    with db() as conn:
        conn.execute("UPDATE equipment SET equipped_to = NULL WHERE id = ? AND equipped_to = ?", (req.equipment_id, hero_id))
    return {"ok": True}

@router.get("/classes/evolutions")
def get_all_class_evolutions():
    from services.class_service import CLASS_EVOLUTIONS
    return CLASS_EVOLUTIONS
