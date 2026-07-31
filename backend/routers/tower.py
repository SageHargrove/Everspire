from fastapi import APIRouter, HTTPException
from database import db
from services.combat_service import run_combat
from services.morale_service import between_floor_recovery, witness_death_trauma, get_morale_state, apply_morale_delta, apply_stress, apply_trauma
from services.llm_service import generate_combat_narration, generate_event_narrative, generate_event_resolution_narrative
from services.event_service import select_event, resolve_event_choice, get_event_theme
from services.floor_templates import (
    get_floor_type, get_cached_floor_type, FLOOR_FLAVOR_INTRO,
    generate_explore_floor, get_explore_choice, resolve_explore_loot,
)
from services.enemy_families import get_miniboss_override, get_boss_override, get_raid_boss_override, get_generic_boss
from services.combat_reveal_service import register_pending_deaths, apply_pending, reveal_due_combats
import json
import random
from pydantic import BaseModel

router = APIRouter()


def _heal_survivors_after_combat(conn, hero_ids: list[int]):
    """Full HP heal + morale/stress/trauma recovery for every hero who
    survived a fight — "the tower trip is over, not a siege" (see
    between_floor_recovery). /floor/enter already did this inline; event
    floors that trigger_combat and explore floors call the same low-level
    _resolve_real_combat but never ran this, so a hero could walk away
    from a won event/explore fight still injured. Centralized here so all
    three call sites share one heal path."""
    for hid in hero_ids:
        hero_row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hid,)).fetchone()
        if not hero_row:
            continue
        recovery = between_floor_recovery(dict(hero_row))
        conn.execute("""
            UPDATE heroes SET health = max_health, morale = ?, stress = ?, trauma = ?, morale_state = ? WHERE id = ?
        """, (recovery["morale"], recovery["stress"], recovery["trauma"], recovery["morale_state"], hid))

class EnterFloorRequest(BaseModel):
    team_ids: list[int] = []
    team_id: int = 1
    floor_number: int
    # DEAD FIELD — kept only for API compatibility. Stance/pre-battle
    # modifiers were deliberately removed (user design law 2026-07-12:
    # floor N is always floor N). The backend ignores this value.
    stance: str = "balanced"
    # Retrieval Missions only: the deployed hero who works the objective
    # instead of fighting. Required when the floor is a "retrieval" — the
    # endpoint 400s with awaiting_runner detail so the frontend can prompt.
    runner_hero_id: int | None = None

# Combat narration used to block floor-entry for up to 1.5s waiting on an LLM
# call that has nowhere to render on the frontend anyway. Now fired in the
# background; the response carries an id the frontend can poll once, a
# moment later, to upgrade the placeholder text if the real one is ready.
_narrative_futures = {}
_narrative_id_counter = 0

def _register_narrative_future(future):
    global _narrative_id_counter
    _narrative_id_counter += 1
    nid = _narrative_id_counter
    _narrative_futures[nid] = future
    if len(_narrative_futures) > 50:
        for old_id in sorted(_narrative_futures)[:-50]:
            del _narrative_futures[old_id]
    return nid

@router.get("/lore")
def get_lore():
    """Every Lore Journal page unlocked so far, oldest first."""
    from services.lore_service import get_lore_journal
    with db() as conn:
        highest_floor = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()["highest_floor"]
        entries = get_lore_journal(conn, highest_floor)
    return {"entries": entries, "highest_floor": highest_floor}


@router.get("/narrative/{narrative_id}")
def get_narrative(narrative_id: int):
    future = _narrative_futures.get(narrative_id)
    if future is None:
        return {"ready": False}
    if not future.done():
        return {"ready": False}
    try:
        return {"ready": True, "narrative": future.result()}
    except Exception:
        return {"ready": True, "narrative": "A fierce battle took place."}


def _grant_survivor_progress(conn, result, floor_number, is_boss=False, is_miniboss=False,
                             is_first_clear=False, fallback_heroes=None):
    """XP / kills / stress / bonds / titles for everyone who walked out of a
    resolved floor fight. This used to live inline in /floor/enter only —
    Explore and Event floors run the SAME real combat but never granted any
    of it (confirmed live: gold landed, xp stayed 0), so every combat path
    now funnels through here. Returns (surviving_ids, combat_won)."""
    from services.level_service import (recalculate_hero_level, level_up_summary,
                                        kill_xp_reward, floor_clear_xp_reward)
    from services.title_service import check_and_assign_titles

    survivors = []
    if result.get("combat") and "surviving_heroes" in result["combat"]:
        survivors = result["combat"]["surviving_heroes"]
    elif fallback_heroes and not result.get("run_over") and not result.get("awaiting_choice"):
        survivors = fallback_heroes

    combat_won = result.get("combat", {}).get("winner") == "heroes"
    is_sole_survivor = combat_won and is_boss and len(survivors) == 1

    # Mentorship boon (guild perk) lifts every hero's combat XP.
    try:
        boon_row = conn.execute("SELECT guild_hero_exp_pct FROM base WHERE id = 1").fetchone()
        exp_boon = 1 + (boon_row["guild_hero_exp_pct"] or 0) / 100.0
    except Exception:
        exp_boon = 1.0

    surviving_ids = []
    for s in survivors:
        hid = s["id"]
        surviving_ids.append(hid)
        kills_gained = s.get("kills_gained", 0)
        stress_delta = s.get("stress_delta", 0)

        # The leader bonus goes to the CROWNED leader (is_team_leader), not
        # whoever happens to sit in slot 0 (Liam). Crowning is independent of
        # formation position.
        hero_row = conn.execute("SELECT is_team_leader FROM heroes WHERE id = ?", (hid,)).fetchone()
        is_leader = bool(hero_row and hero_row["is_team_leader"])

        u_sole = 1 if is_sole_survivor else 0
        u_leader = 1 if (is_leader and combat_won) else 0
        u_first = 1 if (is_first_clear and combat_won) else 0

        # XP: per-kill always (you really did kill it, win or lose), plus a
        # floor-clear bonus only on an actual win — this is what drives
        # level (see recalculate_hero_level).
        xp_gained = kills_gained * kill_xp_reward(floor_number, is_boss, is_miniboss)
        if combat_won:
            xp_gained += floor_clear_xp_reward(floor_number, is_boss, is_miniboss)
        xp_gained = int(xp_gained * exp_boon)

        conn.execute("""
            UPDATE heroes SET
                floors_survived = floors_survived + 1,
                kills = kills + ?,
                lifetime_kills = lifetime_kills + ?,
                sole_survivor_boss_clears = sole_survivor_boss_clears + ?,
                leader_clears = leader_clears + ?,
                unique_floor_clears = unique_floor_clears + ?,
                stress = MIN(100, MAX(0, stress + ?)),
                xp = xp + ?
            WHERE id = ?
        """, (kills_gained, kills_gained, u_sole, u_leader, u_first, stress_delta, xp_gained, hid))

        new_titles = check_and_assign_titles(conn, hid)
        if new_titles:
            result.setdefault("log", []).extend(new_titles)

        hero_row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hid,)).fetchone()
        if hero_row:
            hero_dict = dict(hero_row)
            old_level = hero_dict.get("level", 1)
            new_level = recalculate_hero_level(hero_dict)
            if new_level != old_level:
                conn.execute("UPDATE heroes SET level = ? WHERE id = ?", (new_level, hid))
                result.setdefault("level_ups", []).extend(level_up_summary(old_level, new_level, hero_dict["name"]))

    # Fighting side by side deepens bonds.
    if len(surviving_ids) >= 2:
        for i in range(len(surviving_ids)):
            for j in range(i + 1, len(surviving_ids)):
                a, b = min(surviving_ids[i], surviving_ids[j]), max(surviving_ids[i], surviving_ids[j])
                conn.execute("""
                    INSERT INTO hero_bonds (hero_a_id, hero_b_id, bond_level, floors_together, spar_sessions)
                    VALUES (?, ?, 0, 1, 0)
                    ON CONFLICT(hero_a_id, hero_b_id) DO UPDATE SET
                        floors_together = floors_together + 1,
                        bond_level = (floors_together + 1 + COALESCE(spar_sessions, 0)) / 5
                """, (a, b))

    return surviving_ids, combat_won


def _resolve_real_combat(conn, hero_teams, floor_number, is_boss, is_miniboss, zone_theme,
                          boss_data_override, base_row, pending_legacies,
                          enemy_count_override=None, flavor_intro=None, difficulty_mult=1.0,
                          family_override=None, is_survival_swarm=False, available_consumables=None,
                          is_escort=False, reward_mult=1.0, is_ambush=False, is_blitz=False,
                          cursed_debuff=None, miniboss_variant=None, is_retrieval=False, runner_id=None):
    """Run a real fight and apply every resulting effect."""
    from services.llm_service import generate_combat_narration, submit_flavor_text
    from services.combat_service import run_multi_combat

    try:
        combat_result = run_multi_combat(
            hero_teams, floor_number, is_boss=is_boss, is_miniboss=is_miniboss,
            zone_theme=zone_theme, boss_data_override=boss_data_override,
            difficulty_mult=difficulty_mult, conn=conn,
            family_override=family_override, is_survival_swarm=is_survival_swarm,
            available_consumables=available_consumables, is_escort=is_escort,
            enemy_count_override=enemy_count_override, is_ambush=is_ambush, is_blitz=is_blitz,
            cursed_debuff=cursed_debuff, miniboss_variant=miniboss_variant,
            is_retrieval=is_retrieval, runner_id=runner_id,
        )
    except Exception as e:
        print(f"Combat error: {e}")
        raise HTTPException(status_code=500, detail=f"Combat simulation failed: {str(e)}")

    if flavor_intro:
        combat_result["log"] = [flavor_intro] + combat_result.get("log", [])

    # Potions/Scrolls drunk mid-fight (see available_consumables above) come
    # out of the same shared inventory table /inventory/use draws from —
    # deduct here now that we know exactly what combat actually consumed.
    consumables_used = combat_result.get("consumables_used") or {}
    for item_name, count in consumables_used.items():
        row = conn.execute("SELECT id, quantity FROM inventory WHERE item_name = ?", (item_name,)).fetchone()
        if not row:
            continue
        new_qty = row["quantity"] - count
        if new_qty <= 0:
            conn.execute("DELETE FROM inventory WHERE id = ?", (row["id"],))
        else:
            conn.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, row["id"]))

    result = {"combat": combat_result}

    flat_heroes = [h for team in hero_teams for h in team]
    surviving_ids_for_chatter = {s["id"] for s in combat_result.get("surviving_heroes", [])}

    if combat_result["winner"] == "heroes":
        result["message"] = f"Floor {floor_number} Cleared!"
        conn.execute("UPDATE base SET total_battles_won = total_battles_won + 1 WHERE id = 1")
        survivors = [h for h in flat_heroes if h["id"] in surviving_ids_for_chatter]
        if survivors:
            from services.dialogue_service import get_hero_line
            best = max(survivors, key=lambda h: h.get("birth_star", 1))
            result["chatter_line"] = {"name": best["name"], "line": get_hero_line(best["hero_class"], best.get("birth_star", 1), "victory")}
    else:
        result["message"] = f"Team defeated on Floor {floor_number}."
        result["run_over"] = True
        if flat_heroes:
            from services.dialogue_service import get_hero_line
            speaker = random.choice(flat_heroes)
            result["chatter_line"] = {"name": speaker["name"], "line": get_hero_line(speaker["hero_class"], speaker.get("birth_star", 1), "defeat")}

    flat_hero_names = [h["name"] for team in hero_teams for h in team]
    narrative_future = submit_flavor_text(generate_combat_narration, combat_result.get("log", []), flat_hero_names)
    narrative = "A fierce battle took place."
    result["narrative_id"] = _register_narrative_future(narrative_future)

    # One narration future per team's leg of the fight — multi-team floors
    # (21+) keep each team's turns in team_results, not the top-level
    # "turns" (that's only forwarded for the single-team case below).
    from services.llm_service import generate_turn_narrations
    team_results = combat_result.get("team_results") or [combat_result]
    turn_narrative_ids = []
    for tr in team_results:
        tr_turn_lines = [t["log"] for t in (tr or {}).get("turns", [])]
        fut = submit_flavor_text(generate_turn_narrations, tr_turn_lines, flat_hero_names)
        turn_narrative_ids.append(_register_narrative_future(fut))
    result["turn_narrative_ids"] = turn_narrative_ids
    if turn_narrative_ids:
        result["turn_narrative_id"] = turn_narrative_ids[0]

    import datetime
    from services.bonds_service import get_bond

    # A fallen hero's DEATH is DEFERRED, not applied here — the player is about
    # to watch this fight play out as an animation, and committing the death
    # now would spoil it (they'd show up dead on the Heroes/Memorial tabs the
    # instant the floor is entered). The kill + their legacy + portrait cleanup
    # are registered below and applied only once the fight's real-time timeline
    # has elapsed (see services/combat_reveal_service). We still gather the dead
    # ids now for the SURVIVORS' witness-death trauma, which is a survivor
    # effect and does apply instantly.
    dead_ids = [
        (d if isinstance(d, int) else d["id"])
        for d in combat_result["dead_heroes"]
    ]

    # Trust. Affinity used to be purely bought — gifts, the Sanctum, base
    # activities and training all added, nothing ever subtracted, so a manager
    # who lost people every floor stayed universally adored as long as they
    # kept handing out presents. Outcomes move it too now: survivors gain,
    # and every living hero loses when someone doesn't come back, because
    # everyone hears about it. Applied here, alongside the other survivor
    # effects that commit instantly — the DEATH itself is still deferred to
    # the reveal, but the roster's reaction to the loss is not a spoiler.
    from services.loyalty_service import apply_floor_trust
    _wiped = not combat_result.get("surviving_heroes")
    apply_floor_trust(conn, combat_result.get("surviving_heroes", []), dead_ids, _wiped)

    # Survival logic: Survivor's Guilt & Bonds
    if dead_ids:
        # Was this a near-wipe? If >= 3 heroes died in this battle...
        is_near_wipe = len(dead_ids) >= 3
        
        for surviving in combat_result["surviving_heroes"]:
            surv_id = surviving["id"]
            surv_hr = conn.execute("SELECT * FROM heroes WHERE id = ?", (surv_id,)).fetchone()
            if not surv_hr: continue
            
            # Check bonds with the dead heroes
            high_bonds_count = 0
            for did in dead_ids:
                bond_val = get_bond(conn, surv_id, did)
                if bond_val > 30:
                    high_bonds_count += 1
            
            # Apply Depression if they lost someone they had a strong bond with
            if high_bonds_count > 0:
                # Set depressed for 24 hours
                until = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).isoformat()
                conn.execute("UPDATE heroes SET condition = 'Depressed', condition_until = ? WHERE id = ?", (until, surv_id))
                combat_result.setdefault("log", []).append(f"  ◆ {surv_hr['name']} is overcome with despair after losing bonded comrades.")
                
            # Apply Retirement (Survivor's Guilt) if near-wipe of bonded allies
            if is_near_wipe and high_bonds_count >= 2:
                # Check constitution (apt_mental)
                if surv_hr["apt_mental"] < 70:
                    conn.execute("UPDATE heroes SET near_wipes_survived = near_wipes_survived + 1 WHERE id = ?", (surv_id,))
                    nw_surv = surv_hr["near_wipes_survived"] + 1
                    if nw_surv >= 2:
                        # Retire
                        conn.execute("UPDATE heroes SET condition = 'Retired', is_on_team = 0 WHERE id = ?", (surv_id,))
                        combat_result.setdefault("log", []).append(f"  ✦ {surv_hr['name']}'s mind breaks from surviving another massacre. They retire from active duty.")
                        
            # Apply standard trauma
            trauma_data = witness_death_trauma(is_close_ally=high_bonds_count > 0)
            conn.execute("""
                UPDATE heroes SET
                    trauma = MIN(100, trauma + ?),
                    stress = MIN(100, stress + ?)
                WHERE id = ?
            """, (len(dead_ids) * trauma_data["trauma_delta"],
                  len(dead_ids) * trauma_data["stress_delta"], surv_id))

    # Defer the fallen's actual death (kill + legacy + portrait) to reveal
    # only once the player's fight animation has played out — the client echoes
    # this id back to /floor/finalize, and any hero read reveals it lazily
    # once its real-time window has passed (combat_reveal_service).
    result["pending_combat_id"] = register_pending_deaths(conn, floor_number, dead_ids, combat_result)

    for s in combat_result["surviving_heroes"]:
        hid = s["id"]
        hero_row = conn.execute("SELECT morale, trauma, skills FROM heroes WHERE id = ?", (hid,)).fetchone()
        if hero_row:
            hero_dict = dict(hero_row)
            new_morale = apply_morale_delta(hero_dict["morale"], hero_dict["trauma"], s["morale_delta"])

            skills_json = hero_dict["skills"]
            skills = json.loads(skills_json) if skills_json else []
            if hid in combat_result.get("skill_upgrades", {}):
                upgrades = combat_result["skill_upgrades"][hid]
                for upg in upgrades:
                    for sk in skills:
                        if sk["id"] == upg["skill_id"]:
                            sk["tier"] = upg["new_tier"]
                            sk["level"] = 1
                            sk["xp"] = 0
                            sk["max_xp"] = 100

            if hid in combat_result.get("skills_learned", {}):
                skills.extend(combat_result["skills_learned"][hid])

            skills_json = json.dumps(skills)

            conn.execute("""
                UPDATE heroes SET health = MIN(max_health, ?), morale = ?, morale_state = ?, skills = ? WHERE id = ?
            """, (s["health"], new_morale, get_morale_state(new_morale), skills_json, s["id"]))

    result["gold_gained"] = combat_result.get("gold_gained", 0)
    result["ingredients_gained"] = combat_result.get("ingredients_gained", 0)
    result["materials_gained"] = combat_result.get("materials_gained", {})

    if reward_mult != 1.0:
        result["gold_gained"] = int(result["gold_gained"] * reward_mult)
        result["materials_gained"] = {m: max(1, int(qty * reward_mult)) for m, qty in result["materials_gained"].items()}

    if floor_number <= base_row["highest_floor"]:
        result["gold_gained"] = int(result["gold_gained"] * 0.05)
        result["ingredients_gained"] = int(result["ingredients_gained"] * 0.05)

    if result["gold_gained"] > 0 or result["ingredients_gained"] > 0 or result["materials_gained"]:
        conn.execute(
            "UPDATE base SET gold = gold + ?, ingredients = ingredients + ? WHERE id = 1",
            (result["gold_gained"], result["ingredients_gained"])
        )
        if result["materials_gained"]:
            base_row_current = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
            current_mats = json.loads(base_row_current["materials"]) if base_row_current["materials"] else {}
            for m, qty in result["materials_gained"].items():
                current_mats[m] = current_mats.get(m, 0) + qty
            conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(current_mats),))

    if combat_result.get("equipment_drop"):
        from services.equipment_service import save_equipment
        equip = combat_result["equipment_drop"]
        equip["id"] = save_equipment(equip, conn=conn)
        result["equipment_drop"] = equip

    if combat_result["winner"] == "heroes" and random.random() < 0.15:
        undiscovered = conn.execute("SELECT id, name FROM recipes WHERE is_discovered = 0 ORDER BY RANDOM() LIMIT 1").fetchone()
        if undiscovered:
            conn.execute("UPDATE recipes SET is_discovered = 1 WHERE id = ?", (undiscovered["id"],))
            result["blueprint_found"] = undiscovered["name"]
            combat_result.setdefault("log", []).append(f"✦ Found a new Blueprint: {undiscovered['name']}!")

    if combat_result.get("relic_drop"):
        result["relic_drop"] = combat_result["relic_drop"]

    # Endgame facility hooks — Bestiary capture roll on any winning fight,
    # Reliquary trophy on a winning boss floor (every 10th).
    if combat_result["winner"] == "heroes":
        # Deeds — permanent accomplishment records mined from this fight.
        try:
            from services.deeds_service import record_deeds
            new_deeds = record_deeds(conn, combat_result, floor_number, is_boss, is_miniboss)
            if new_deeds:
                result["deeds_earned"] = new_deeds
        except Exception as e:
            print(f"Deed hook error: {e}")
        try:
            from services.endgame_service import maybe_capture_beast, maybe_award_trophy
            enemy_names = [e["name"] for e in combat_result.get("initial_state", {}).get("enemies", [])]
            captured = maybe_capture_beast(conn, floor_number, enemy_names, is_boss)
            if captured:
                result["beast_captured"] = captured
                combat_result.setdefault("log", []).append(f"✦ {captured['name']} was subdued and dragged back to the Bestiary!")
            if is_boss:
                trophy = maybe_award_trophy(conn, floor_number, enemy_names)
                if trophy:
                    result["trophy_earned"] = trophy
                    combat_result.setdefault("log", []).append(f"✦ Trophy claimed: {trophy['boss_name']} (Floor {trophy['floor']}) — mount it in the Reliquary for {trophy['buff_label']}.")
        except Exception as e:
            print(f"Endgame hook error: {e}")

    result["narrative"] = narrative
    return result

@router.get("/floor/preview/{floor_number}")
def preview_floor(floor_number: int):
    """Peek at a floor's type/flavor. The type is rolled once and cached
    forever (same as before), but it's only REVEALED to the player after
    they've actually entered the floor at least once — locked or unvisited
    floors always return floor_type: null so the grid shows '?' instead
    of the real type, preventing spoilers and looking cleaner."""
    with db() as conn:
        floor_type = get_cached_floor_type(conn, floor_number)
        visited_row = conn.execute(
            "SELECT visited FROM floor_cache WHERE floor_number = ?", (floor_number,)
        ).fetchone()
        visited = bool(visited_row and visited_row["visited"])

    # Floors stay UNKNOWN until walked (user rule — Scout no longer reveals
    # ahead; its power moved to the Bestiary hunt). But a floor you've BEEN
    # on is learned knowledge: its condition, its elite, its boss's phase
    # behavior are deterministic facts worth remembering between attempts.
    if not visited:
        return {"floor_type": None, "blurb": None, "visited": False}

    intel = {}
    try:
        from services.combat_service import roll_floor_condition, roll_boss_phases, make_enemies, ELITE_AFFIXES
        cond = roll_floor_condition(floor_number)
        if cond:
            intel["condition"] = {"name": cond["name"], "desc": cond["desc"]}
        if floor_number % 10 == 0:
            intel["boss_phases"] = [p["kind"] for p in roll_boss_phases(floor_number)]
        elif floor_number % 5 != 0:
            elite = next((e.name for e in make_enemies(floor_number)
                          if any(e.name.startswith(a + " ") for a in ELITE_AFFIXES)), None)
            if elite:
                intel["elite"] = elite
    except Exception:
        pass

    return {
        "floor_type": floor_type,
        "blurb": FLOOR_FLAVOR_INTRO.get(floor_type, ""),
        "visited": visited,
        **intel,
    }

@router.post("/floor/enter")
def enter_floor(req: EnterFloorRequest):
    """Resolve a single floor for a specific team without any 'Run' constraints."""
    # Any fight left pending from a prior floor is conceptually over the moment
    # a new one starts — apply its deferred deaths first so a "dead" hero can't
    # be re-deployed or linger through the next fight.
    apply_pending()
    pending_legacies = []
    with db() as conn:
        # Tower entry is free — the old per-entry supply toll went away with
        # the supplies currency itself (fatigue is what throttles runs now).
        base_row = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()
        if not base_row:
            raise HTTPException(status_code=500, detail="Base not found")

        if req.floor_number > base_row["highest_floor"] + 1:
            raise HTTPException(status_code=400, detail="Cannot skip floors.")

        # Get heroes
        teams_to_deploy = req.team_ids if req.team_ids else [req.team_id]
        
        # Verify required teams
        required_teams = (req.floor_number - 1) // 20 + 1
        if req.floor_number == 1 and not req.team_ids: required_teams = 1
        if len(teams_to_deploy) < required_teams:
            raise HTTPException(status_code=400, detail=f"Floor {req.floor_number} requires {required_teams} team(s) to be deployed.")
            
        hero_teams = []
        ego_rebellions = []
        for tid in teams_to_deploy[:required_teams]:
            from services.ego_service import process_ego_patience
            ego_rebellions.extend(process_ego_patience(conn, tid))
            team_heroes = [dict(r) for r in conn.execute("SELECT * FROM heroes WHERE is_on_team = ? AND is_alive = 1 ORDER BY team_position ASC, id ASC", (tid,)).fetchall()]
            if not team_heroes:
                raise HTTPException(status_code=400, detail=f"No heroes assigned to Team {tid}.")
            hero_teams.append(team_heroes)

        for team in hero_teams:
            for hero in team:
                if hero["fatigue"] >= 10:
                    raise HTTPException(status_code=400, detail=f"{hero['name']} is exhausted (Fatigue 10) and must rest before entering the tower.")

        # Auto-apply Bandages pre-fight to deployed heroes who specifically
        # have "Bandage" equipped (see heroes.equipped_consumable /
        # POST /heroes/equip-consumable) — not just whoever's most injured.
        # Combat resolves as one deterministic simulation rather than a
        # turn-by-turn player loop, so "using" a Bandage means patching up
        # before you go in, not a mid-fight action.
        from services.infirmary_service import BANDAGE_HEAL_PCT
        mats_row = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
        materials = json.loads(mats_row["materials"]) if mats_row["materials"] else {}
        bandages = materials.get("Bandage", 0)
        if bandages > 0:
            flat_heroes = [hero for team in hero_teams for hero in team]
            equipped = [h for h in flat_heroes if h.get("equipped_consumable") == "Bandage" and h["health"] < h["max_health"]]
            injured = sorted(equipped, key=lambda hero: hero["health"] / hero["max_health"])
            used = 0
            for hero in injured:
                if used >= bandages:
                    break
                heal = int(hero["max_health"] * BANDAGE_HEAL_PCT)
                hero["health"] = min(hero["max_health"], hero["health"] + heal)
                conn.execute("UPDATE heroes SET health = ? WHERE id = ?", (hero["health"], hero["id"]))
                used += 1
            if used > 0:
                materials["Bandage"] = bandages - used
                conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(materials),))

        # Potions/Scrolls draw from the same shared finite stock as
        # Bandages above, but which hero is even allowed to reach for one
        # mid-fight is gated by their own equipped_consumable (see
        # combat_service.py's auto-use loop) — not a free-for-all. Only the
        # healing-capable ones are eligible here — a Scroll of Insight isn't
        # something you'd drink to save your life mid-fight.
        from services.alchemist_service import POTION_CATALOG
        from services.research_service import SCROLL_CATALOG
        from services.cooking_service import FOOD_CATALOG
        heal_catalog = {p["name"]: p["effect"]["heal_pct"] for p in POTION_CATALOG if "heal_pct" in p["effect"]}
        heal_catalog.update({s["name"]: s["effect"]["heal_pct"] for s in SCROLL_CATALOG if "heal_pct" in s["effect"]})
        heal_catalog.update({f["name"]: f["effect"]["heal_pct"] for f in FOOD_CATALOG if "heal_pct" in f["effect"]})
        mana_catalog = {p["name"]: p["effect"]["mana_pct"] for p in POTION_CATALOG if "mana_pct" in p["effect"]}
        available_consumables = [
            {"item_name": row["item_name"], "quantity": row["quantity"],
             "heal_pct": heal_catalog.get(row["item_name"]), "mana_pct": mana_catalog.get(row["item_name"])}
            for row in conn.execute("SELECT item_name, quantity FROM inventory WHERE quantity > 0").fetchall()
            if row["item_name"] in heal_catalog or row["item_name"] in mana_catalog
        ]

        # Flavor text (zone theme, boss naming, narration) must never stack into
        # a multi-second wait before combat starts — none of it affects combat
        # math. Each call is bounded to a short timeout; on timeout we fall
        # back to local text rather than wait.
        from services.llm_service import generate_zone_theme, generate_boss_enemy, call_with_timeout, submit_flavor_text, await_flavor_text
        floor_type = get_cached_floor_type(conn, req.floor_number)
        hero_list = [h for team in hero_teams for h in team] # flattened for event logs and logic
        is_boss = floor_type == "boss"
        is_miniboss = floor_type.startswith("miniboss")
        # "miniboss_behemoth" -> "behemoth"; bare legacy "miniboss" (stale
        # floor_cache rows from before variants existed) has no variant.
        miniboss_variant = floor_type.split("_", 1)[1] if is_miniboss and "_" in floor_type else None
        is_survival_swarm = is_miniboss and miniboss_variant == "survival"

        # Built-out floor families (currently just floor 1-10's Slime/Goblin/
        # Rat/Wolf range) supply a deterministic named miniboss/boss instead
        # of the generic variant/LLM-flavored naming below — see
        # enemy_families.py. Takes priority over a rolled variant so curated
        # early-floor content (e.g. floor 5's "Goblin King") never gets
        # silently replaced by a generic Behemoth/Assassin/Twins/Mirror.
        family_override = None
        if is_survival_swarm:
            pass
        elif is_miniboss:
            family_override = get_miniboss_override(req.floor_number)
            if family_override:
                miniboss_variant = None
        elif is_boss:
            # Raid Boss merge (see run_multi_combat's matching floor==50/100
            # check) gets its own dedicated unique where one's been built,
            # instead of just reusing that floor's regular %10 boss scaled
            # up. Reduced to exactly Floor 50 and 100.
            if req.floor_number == 50 or req.floor_number == 100:
                family_override = get_raid_boss_override(req.floor_number)
            if family_override is None:
                family_override = get_boss_override(req.floor_number)

        # Zone theme and boss naming are independent enough to run concurrently
        # instead of sequentially — boss naming uses a generic placeholder theme
        # rather than waiting on the real zone theme text first. Skipped
        # entirely when a family_override already supplies a deterministic
        # name — no point spending an LLM call on flavor that's discarded.
        zone_theme_future = submit_flavor_text(generate_zone_theme, req.floor_number)
        # Boss floors with no named override draw from the pre-built pool
        # instead of generating a name via LLM — all boss art is committed.
        if is_boss and not family_override and not is_survival_swarm:
            family_override = get_generic_boss()

        zone_theme = await_flavor_text(zone_theme_future, timeout=1.5, fallback="")
        zone_theme_display = zone_theme or "The Dark Unknown: Shadows obscure the path ahead."
        boss_data_override = None

        result = {}
        narrative = None

        # Resolve Floor Logic — every combat-family type below is a real
        # fight under a different frame/twist, not an abstract stat check.
        # They share the exact same resolution path as each other
        # (death/legacy/trauma/rewards/equipment) below.
        COMBAT_FAMILY_TYPES = ("boss", "survival", "defend", "escort", "field_combat",
                               "conquest", "war", "retrieve", "retrieval", "ambush", "blitz",
                               "cursed_ground")
        if is_miniboss or floor_type in COMBAT_FAMILY_TYPES:
            enemy_count_override = None
            flavor_intro = FLOOR_FLAVOR_INTRO.get(floor_type)
            reward_mult = 1.0
            extra_difficulty_mult = 1.0
            is_ambush = False
            is_blitz = False
            cursed_debuff = None
            is_retrieval = False
            runner_id = None
            if is_survival_swarm:
                flavor_intro = "Waves without end pour from the dark. There's no winning this one outright — only surviving it."
            elif floor_type == "survival":
                enemy_count_override = random.randint(6, 8)
            elif floor_type == "escort":
                npc = random.choice(["a wounded traveler", "a lost child", "a captured merchant", "a dying scholar"])
                flavor_intro = f"You find {npc} who needs safe passage. Enemies close in on the path."
            elif floor_type == "conquest":
                # Bigger wave, no twist beyond the numbers — kill everything,
                # the natural per-kill rewards do the rest.
                enemy_count_override = random.randint(5, 7)
            elif floor_type == "war":
                # The hardest non-boss set-piece: biggest wave AND toughened
                # stats on top of the floor's normal difficulty.
                enemy_count_override = random.randint(6, 9)
                extra_difficulty_mult = 1.15
            elif floor_type == "retrieve":
                # Mission-sized fight (no bigger than normal combat) but a
                # guaranteed bonus on whatever loot the fight already drops —
                # "go in, take the valuable thing, get out."
                reward_mult = 1.5
            elif floor_type == "retrieval":
                # Retrieval Mission — the player must explicitly pick which
                # deployed hero runs the objective (they won't fight); the
                # rest of the team survives the turn limit around them. The
                # runner works a turn short-handed, so the win pays extra.
                is_retrieval = True
                deployed_ids = {h["id"] for h in hero_list}
                if not req.runner_hero_id or req.runner_hero_id not in deployed_ids:
                    raise HTTPException(status_code=400, detail={
                        "code": "awaiting_runner",
                        "message": "This is a Retrieval Mission — designate one deployed hero as the Runner (runner_hero_id) before entering. The Runner works the objective and cannot attack.",
                        "floor_type": "retrieval",
                        "deployed_hero_ids": sorted(deployed_ids),
                    })
                runner_id = req.runner_hero_id
                reward_mult = 1.4
            elif floor_type == "ambush":
                is_ambush = True
            elif floor_type == "blitz":
                is_blitz = True
            elif floor_type == "cursed_ground":
                cursed_debuff = {"poison_rounds": 3, "poison_magnitude": 0.06, "hp_pct_loss": 0.25}

            # STANCE IS DEAD (user design law 2026-07-12): floor N is always
            # floor N — no player-side pre-battle modifiers. The old
            # aggressive/cautious dial was deliberately removed; req.stance
            # remains in the request model only for API compatibility and is
            # ignored. Variance comes from WHO you send, never a toggle.

            from services.difficulty_service import get_difficulty_mults
            enemy_stat_mult = get_difficulty_mults(conn)["enemy_stat_mult"] * extra_difficulty_mult

            result = _resolve_real_combat(
                conn, hero_teams, req.floor_number, is_boss, is_miniboss, zone_theme,
                boss_data_override, base_row, pending_legacies,
                enemy_count_override=enemy_count_override, flavor_intro=flavor_intro,
                difficulty_mult=enemy_stat_mult,
                family_override=family_override, is_survival_swarm=is_survival_swarm,
                available_consumables=available_consumables, is_escort=(floor_type == "escort"),
                reward_mult=reward_mult, is_ambush=is_ambush, is_blitz=is_blitz,
                cursed_debuff=cursed_debuff, miniboss_variant=miniboss_variant,
                is_retrieval=is_retrieval, runner_id=runner_id,
            )
            result["floor_type"] = floor_type
            if not is_boss and not is_miniboss:
                result["stance"] = req.stance

        elif floor_type == "event":
            event_data = select_event(req.floor_number, zone_theme_display)
            narrative = call_with_timeout(
                generate_event_narrative, event_data["theme"], req.floor_number, [h["name"] for h in hero_list],
                timeout=1.5, fallback=event_data["theme"]
            )
            result = {
                "floor_type": "event",
                "event": event_data,
                "event_narrative": narrative,
                "awaiting_choice": True,
                "theme": zone_theme_display
            }

        elif floor_type == "explore":
            # Explore is a real player choice (thorough/quick/leave), not an
            # auto-resolve — mirrors the event awaiting_choice flow. The actual
            # discovery/trap roll happens fresh in /floor/explore/resolve once
            # the player picks; nothing here is random-sensitive to persist.
            template = generate_explore_floor(req.floor_number)
            result = {
                "floor_type": "explore",
                "explore": {
                    "theme": template["theme"],
                    "choices": [
                        {"id": c["id"], "label": c["label"], "hint": c["hint"]}
                        for c in template["choices"]
                    ],
                },
                "awaiting_choice": True,
            }

        # Add fatigue to deployed heroes
        conn.execute(
            """
            UPDATE heroes 
            SET fatigue = MIN(10, fatigue + 1) 
            WHERE is_on_team = ? AND is_alive = 1
            """,
            (req.team_id,)
        )

        is_first_clear = req.floor_number > base_row["highest_floor"]
        combat_won = result.get("combat", {}).get("winner") == "heroes"

        if combat_won:
            from services.quests_service import bump as bump_rite
            bump_rite("floor_clear")

        # Record what this floor actually was for the Lore Journal — only
        # for floors that resolved outright here (event/explore haven't
        # resolved yet at this point, see their own /resolve endpoints).
        if result.get("combat") and not result.get("awaiting_choice"):
            from services.lore_service import record_floor_history
            enemy_names = [e["name"] for e in result["combat"].get("initial_state", {}).get("enemies", [])]
            outcome = "won" if combat_won else "was wiped"
            summary = f"Fought {', '.join(enemy_names) or 'enemies'} — party {outcome}."
            record_floor_history(conn, req.floor_number, result.get("floor_type", floor_type), summary)

        # XP / kills / bonds / titles — shared with the explore/event
        # resolve paths, which run the same real combat.
        surviving_ids, _ = _grant_survivor_progress(
            conn, result, req.floor_number, is_boss=is_boss, is_miniboss=is_miniboss,
            is_first_clear=is_first_clear, fallback_heroes=hero_list)

        # Between-floor recovery applied immediately since we return to base
        # instantly — HP fully heals on lobby return too (the tower trip is
        # over, not a siege).
        _heal_survivors_after_combat(conn, surviving_ids)

        # Mark this floor as visited regardless of win/loss — the player
        # entered it, so the floor type is now revealed on the grid.
        conn.execute(
            "UPDATE floor_cache SET visited = 1 WHERE floor_number = ?",
            (req.floor_number,)
        )

        if not result.get("run_over") and not result.get("awaiting_choice") and req.floor_number > base_row["highest_floor"]:
            gems_reward = 500 if req.floor_number % 5 == 0 else 100
            conn.execute("UPDATE base SET highest_floor = ?, gems = gems + ? WHERE id = 1", (req.floor_number, gems_reward))
            result["gems_gained"] = gems_reward
            if surviving_ids:
                ids_str = ",".join(str(i) for i in surviving_ids)
                conn.execute(f"UPDATE heroes SET unique_floors_cleared = unique_floors_cleared + 1 WHERE id IN ({ids_str})")

    for hero_dict, is_sacrifice in pending_legacies:
        try:
            from services.portrait_cache import handle_fallen_portrait
            new_path = handle_fallen_portrait(hero_dict["id"], hero_dict.get("portrait_path"), is_sacrifice)
            hero_dict["portrait_path"] = new_path
        except Exception as e:
            print(f"Portrait cleanup error: {e}")
        try:
            from services.legacy_service import create_legacy
            create_legacy(hero_dict, is_sacrifice=is_sacrifice)
        except Exception as e:
            print(f"Legacy creation error: {e}")

    result["floor"] = req.floor_number
    if ego_rebellions:
        result["ego_rebellions"] = ego_rebellions
    return result


class FinalizeCombatRequest(BaseModel):
    # The id returned as `pending_combat_id` when the fight was resolved.
    # Optional — omitting it just sweeps whatever's overdue.
    pending_combat_id: int | None = None


@router.post("/floor/finalize")
def finalize_combat(req: FinalizeCombatRequest):
    """Called by the client the instant a fight's animation finishes — reveal
    the fallen NOW (at whatever playback speed the player watched), so a hero
    only ever shows dead once the battle has actually played out that far.
    Also sweeps any other overdue fights. Idempotent: a no-op if the death
    was already revealed (by a lazy read, or a double call)."""
    if req.pending_combat_id:
        revealed = apply_pending(pending_ids=[req.pending_combat_id])
        # Also clear anything else overdue while we're here.
        revealed += apply_pending(only_due=True)
    else:
        revealed = apply_pending(only_due=True)
    return {"ok": True, "revealed": [f["id"] for f in revealed]}


class ResolveEventRequest(BaseModel):
    floor_number: int
    team_id: int
    template_id: str
    choice_id: str
    theme: str = "An event occurred."

@router.post("/floor/event/resolve")
def resolve_event_floor(data: ResolveEventRequest):
    """Resolve a player's event floor choice. Most choices are pure
    narrative + stat effects, but some (trigger_combat) turn hostile after
    the narrative beat, and some (trait) leave a permanent mark on the
    hero beyond the temporary gold/health/stress nudge."""
    apply_pending()  # settle any prior fight's deferred deaths first
    pending_legacies = []
    with db() as conn:
        base_row = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()

        heroes = conn.execute(
            "SELECT * FROM heroes WHERE is_on_team = ? AND is_alive = 1", (data.team_id,)
        ).fetchall()
        hero_list = [dict(h) for h in heroes]
        hero_names = [h["name"] for h in hero_list]

        resolution = resolve_event_choice(data.template_id, data.choice_id, hero_list)
        if "error" in resolution:
            raise HTTPException(status_code=400, detail=resolution["error"])

        from services.lore_service import record_floor_history
        record_floor_history(
            conn, data.floor_number, "event",
            f"Event \"{get_event_theme(data.template_id)[:80]}\" — chose: {resolution['choice_label']}.",
        )

        effects = resolution["effects"]

        if "gold" in effects and effects["gold"] != 0:
            conn.execute("UPDATE base SET gold = gold + ? WHERE id = 1", (effects["gold"],))

        if "item" in effects:
            try:
                from services.equipment_service import save_equipment
                equip = {
                    "name": effects["item"],
                    "type": "Accessory",
                    "rarity": "A",
                    "level": 1,
                    "base_hlt": 150, "base_str": 15, "base_int": 10, "base_agi": 5,
                }
                save_equipment(equip, conn=conn)
            except Exception as e:
                print(f"Failed to grant event item: {e}")

        sacrificed_name = None
        if effects.get("sacrifice_hero") and hero_list:
            import random
            sacrificed = random.choice(hero_list)
            sacrificed_name = sacrificed["name"]
            conn.execute("UPDATE heroes SET is_alive = 0, is_on_team = 0 WHERE id = ?", (sacrificed["id"],))
            hero_list = [h for h in hero_list if h["id"] != sacrificed["id"]]
            pending_legacies.append((sacrificed, True))

        for hero in hero_list:
            hid = hero["id"]
            updates = []
            params = []

            if "hlt_pct" in effects and effects["hlt_pct"] != 0:
                hp_change = int(hero["max_health"] * effects["hlt_pct"])
                new_hp = max(1, min(hero["max_health"], hero["health"] + hp_change))
                updates.append("health = ?")
                params.append(new_hp)

            if "morale" in effects and effects["morale"] != 0:
                new_morale = max(0, min(100, hero["morale"] + effects["morale"]))
                updates.append("morale = ?")
                params.append(new_morale)

            if "stress" in effects and effects["stress"] != 0:
                new_stress = max(0, min(100, hero["stress"] + effects["stress"]))
                updates.append("stress = ?")
                params.append(new_stress)

            if "trauma" in effects and effects["trauma"] != 0:
                new_trauma = max(0, min(100, hero["trauma"] + effects["trauma"]))
                updates.append("trauma = ?")
                params.append(new_trauma)

            # Permanent trait grant — same effect-dict shape as a passive
            # skill (see skills_service.apply_passive_skills), just never
            # rolled away or replaced. One-time per trait id per hero.
            if "trait" in effects:
                trait = effects["trait"]
                existing_traits = json.loads(hero.get("traits") or "[]")
                if not any(t.get("id") == trait["id"] for t in existing_traits):
                    existing_traits.append(trait)
                    updates.append("traits = ?")
                    params.append(json.dumps(existing_traits))

            if updates:
                params.append(hid)
                conn.execute(f"UPDATE heroes SET {', '.join(updates)} WHERE id = ?", params)

        try:
            narrative = generate_event_resolution_narrative(
                get_event_theme(data.template_id), resolution["choice_label"], effects, hero_names
            )
        except Exception:
            narrative = f"The party chose: {resolution['choice_label']}."

        # Floor progress (floors_survived/level) only lands once the choice
        # is actually resolved — not on mere entry (see /floor/enter).
        # trigger_combat events skip this: their fight's
        # _grant_survivor_progress below already counts the floor.
        if not effects.get("trigger_combat"):
            from services.level_service import recalculate_hero_level
            for hero in hero_list:
                conn.execute("UPDATE heroes SET floors_survived = floors_survived + 1 WHERE id = ?", (hero["id"],))
                hero_row = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero["id"],)).fetchone()
                if hero_row:
                    new_level = recalculate_hero_level(dict(hero_row))
                    if new_level != hero_row["level"]:
                        conn.execute("UPDATE heroes SET level = ? WHERE id = ?", (new_level, hero["id"]))

        # The choice turned hostile — a real fight breaks out right after
        # the narrative beat, using the same engine/UI path as Explore
        # floors. Floor progress/gems are gated on actually winning this
        # fight, same as any other combat floor — the narrative-only
        # rewards above (gold/trait/etc.) already landed regardless.
        if effects.get("trigger_combat") and hero_list:
            from services.difficulty_service import get_difficulty_mults
            enemy_stat_mult = get_difficulty_mults(conn)["enemy_stat_mult"]
            combat_result = _resolve_real_combat(
                conn, [hero_list], data.floor_number, is_boss=False, is_miniboss=False, zone_theme="",
                boss_data_override=None, base_row=base_row, pending_legacies=pending_legacies,
                difficulty_mult=enemy_stat_mult,
                flavor_intro=f"{resolution['choice_label']} — and then it turns hostile.",
            )
            combat_result["floor_type"] = "event"
            combat_result["choice_label"] = resolution["choice_label"]
            combat_result["event_narrative"] = narrative
            combat_result["effects"] = effects

            # Event fights are real fights — same XP/kills/bonds grant as
            # any combat floor.
            surviving_ids, _ = _grant_survivor_progress(
                conn, combat_result, data.floor_number,
                is_first_clear=data.floor_number > base_row["highest_floor"])
            _heal_survivors_after_combat(conn, surviving_ids)

            conn.execute("UPDATE floor_cache SET visited = 1 WHERE floor_number = ?", (data.floor_number,))

            if not combat_result.get("run_over") and data.floor_number > base_row["highest_floor"]:
                gems_reward = 500 if data.floor_number % 5 == 0 else 100
                conn.execute("UPDATE base SET highest_floor = ?, gems = gems + ? WHERE id = 1", (data.floor_number, gems_reward))
                combat_result["gems_gained"] = gems_reward

            for hero_dict, is_sacrifice in pending_legacies:
                try:
                    from services.portrait_cache import handle_fallen_portrait
                    new_path = handle_fallen_portrait(hero_dict["id"], hero_dict.get("portrait_path"), is_sacrifice)
                    hero_dict["portrait_path"] = new_path
                except Exception as e:
                    print(f"Portrait cleanup error: {e}")
                try:
                    from services.legacy_service import create_legacy
                    create_legacy(hero_dict, is_sacrifice=is_sacrifice)
                except Exception as e:
                    print(f"Legacy creation error: {e}")

            combat_result["floor"] = data.floor_number
            return combat_result

        conn.execute("UPDATE floor_cache SET visited = 1 WHERE floor_number = ?", (data.floor_number,))

        if data.floor_number > base_row["highest_floor"]:
            gems_reward = 500 if data.floor_number % 5 == 0 else 100
            conn.execute("UPDATE base SET highest_floor = ?, gems = gems + ? WHERE id = 1", (data.floor_number, gems_reward))
            effects["gems"] = gems_reward

    for hero_dict, is_sacrifice in pending_legacies:
        try:
            from services.portrait_cache import handle_fallen_portrait
            new_path = handle_fallen_portrait(hero_dict["id"], hero_dict.get("portrait_path"), is_sacrifice)
            hero_dict["portrait_path"] = new_path
        except Exception as e:
            print(f"Portrait cleanup error: {e}")
        try:
            from services.legacy_service import create_legacy
            create_legacy(hero_dict, is_sacrifice=is_sacrifice)
        except Exception as e:
            print(f"Legacy creation error: {e}")

    return {
        "ok": True,
        "choice_label": resolution["choice_label"],
        "effects": effects,
        "narrative": narrative,
    }

class ResolveExploreRequest(BaseModel):
    floor_number: int
    team_id: int
    choice_id: str

@router.post("/floor/explore/resolve")
def resolve_explore_floor_choice(data: ResolveExploreRequest):
    """Resolve a player's explore floor choice. Every choice still leads to
    a real fight — the choice sets the encounter's overall difficulty
    (difficulty_mult, not just enemy count — a handful of weak swarmers
    and a single elite can land at the same real threat level) and the
    post-win loot odds. It doesn't skip combat."""
    apply_pending()  # settle any prior fight's deferred deaths first
    pending_legacies = []
    with db() as conn:
        base_row = conn.execute("SELECT highest_floor FROM base WHERE id = 1").fetchone()

        heroes = conn.execute(
            "SELECT * FROM heroes WHERE is_on_team = ? AND is_alive = 1", (data.team_id,)
        ).fetchall()
        hero_list = [dict(h) for h in heroes]
        if not hero_list:
            raise HTTPException(status_code=400, detail=f"No heroes assigned to Team {data.team_id}.")

        template = generate_explore_floor(data.floor_number)
        choice = get_explore_choice(template, data.choice_id)

        from services.difficulty_service import get_difficulty_mults
        enemy_stat_mult = get_difficulty_mults(conn)["enemy_stat_mult"]

        result = _resolve_real_combat(
            conn, [hero_list], data.floor_number, is_boss=False, is_miniboss=False, zone_theme="",
            boss_data_override=None, base_row=base_row, pending_legacies=pending_legacies,
            difficulty_mult=choice["difficulty_mult"] * enemy_stat_mult, flavor_intro=template["theme"],
        )
        result["floor_type"] = "explore"

        from services.lore_service import record_floor_history
        enemy_names = [e["name"] for e in result.get("combat", {}).get("initial_state", {}).get("enemies", [])]
        outcome = "won" if not result.get("run_over") else "was wiped"
        record_floor_history(
            conn, data.floor_number, "explore",
            f"Explored \"{template['theme'][:80]}\" — chose: {choice.get('label', data.choice_id)}. "
            f"Fought {', '.join(enemy_names) or 'enemies'} — party {outcome}.",
        )

        # Same XP/kills/bonds grant as any combat floor — explore fights are
        # real fights (this was the "won a floor, got gold, no XP" bug).
        surviving_ids, _ = _grant_survivor_progress(
            conn, result, data.floor_number,
            is_first_clear=data.floor_number > base_row["highest_floor"])
        _heal_survivors_after_combat(conn, surviving_ids)

        # Loot is a bonus on top of the fight — only rolls if the fight was won.
        if not result.get("run_over"):
            avg_luck = sum(h.get("luck", 5) for h in hero_list) / max(1, len(hero_list))
            loot_result = resolve_explore_loot(template, choice, avg_luck)
            result["explore_loot"] = loot_result
            loot = loot_result.get("loot", {})
            if loot.get("type") == "gold":
                conn.execute("UPDATE base SET gold = gold + ? WHERE id = 1", (loot.get("amount", 0),))
                result["gold_gained"] = result.get("gold_gained", 0) + loot.get("amount", 0)
            elif loot.get("type") in ("materials", "rare_materials"):
                mats_row = conn.execute("SELECT materials FROM base WHERE id = 1").fetchone()
                current_mats = json.loads(mats_row["materials"]) if mats_row["materials"] else {}
                mat_name = loot.get("name") or loot.get("type", "materials")
                current_mats[mat_name] = current_mats.get(mat_name, 0) + loot.get("amount", 1)
                conn.execute("UPDATE base SET materials = ? WHERE id = 1", (json.dumps(current_mats),))
                result.setdefault("materials_gained", {})
                result["materials_gained"][mat_name] = result["materials_gained"].get(mat_name, 0) + loot.get("amount", 1)

        if not result.get("run_over") and data.floor_number > base_row["highest_floor"]:
            gems_reward = 500 if data.floor_number % 5 == 0 else 100
            conn.execute("UPDATE base SET highest_floor = ?, gems = gems + ? WHERE id = 1", (data.floor_number, gems_reward))
            result["gems_gained"] = gems_reward

    for hero_dict, is_sacrifice in pending_legacies:
        try:
            from services.portrait_cache import handle_fallen_portrait
            new_path = handle_fallen_portrait(hero_dict["id"], hero_dict.get("portrait_path"), is_sacrifice)
            hero_dict["portrait_path"] = new_path
        except Exception as e:
            print(f"Portrait cleanup error: {e}")
        try:
            from services.legacy_service import create_legacy
            create_legacy(hero_dict, is_sacrifice=is_sacrifice)
        except Exception as e:
            print(f"Legacy creation error: {e}")

    result["floor"] = data.floor_number
    return result
