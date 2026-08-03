from fastapi import APIRouter, HTTPException
from database import db
from services.gacha_service import pull_rarity, generate_base_stats, generate_aptitudes, get_pull_cost, apply_class_stat_bias
from services.llm_service import generate_hero_profile
from services.portrait_cache import pop_cached_portrait, rename_portrait_for_hero, queue_custom_portrait
from services.class_service import assign_class, can_pilot
from services.level_service import recalculate_hero_level
from services.skills_service import assign_initial_skills
from pydantic import BaseModel
import json
import threading

router = APIRouter()

PITY_GUARANTEE_THRESHOLD = 10  # guaranteed 3★+ pull once pity_counter reaches this

MALE_FALLBACK_NAMES = [
    "Valerius", "Kaelen", "Tavian", "Rykard", "Jerrick", "Darius", "Fenris", "Corvus", "Sylas", "Bram",
    "Thorne", "Lysander", "Rowan", "Orion", "Soren", "Caelum", "Silas", "Evander", "Theron", "Aelar",
    "Zephyr", "Kael", "Ignis", "Sol", "Alistair", "Lucius", "Gideon", "Caius", "Marcus", "Eldric", "Finn",
    "Ronan", "Declan", "Aldous", "Vane", "Kaelan", "Orik", "Varian", "Zane", "Jax", "Lars", "Rex"
]
FEMALE_FALLBACK_NAMES = [
    "Elara", "Seris", "Isolde", "Nia", "Lorien", "Vanya", "Myra", "Gael", "Aria", "Cassia", "Kira", "Eira",
    "Vesper", "Juno", "Nyssa", "Lirael", "Rhea", "Lyra", "Nyx", "Nova", "Aura", "Seraphina", "Lumina",
    "Thalia", "Vespera", "Celeste", "Iris", "Maeve", "Senna", "Talia", "Ayla", "Mira", "Lina", "Cia"
]
FALLBACK_SURNAMES = [
    "Blackwood", "Vane", "Ash", "Storm", "Frost", "Gale", "Silver", "Iron", "Crow", "Hawk",
    "Dusk", "Dawn", "Wraith", "Grim", "Vale", "Thorn", "Shadow", "Drake", "Wolf", "Moon",
    "Blood", "Blade", "Stone", "Fire", "Star", "Sun", "Night", "Day", "Sky", "Sea", "River",
    "Winter", "Summer", "Autumn", "Spring", "Gold", "Steel", "Copper", "Brass", "Glass"
]
FALLBACK_TITLES = [
    "the Forsaken", "the Lost", "the Wanderer", "the Quiet", "the Exile", "the Broken",
    "the Swift", "the Resolute", "the Shadow", "the Undying", "the Vengeful", "the Silent",
    "the Bloodied", "the Merciful", "the Iron-Willed", "the Fearless", "the Accursed", "the Blessed",
    "the Cursed", "the Damned", "the Doomed", "the Fated", "the Destined", "the Chosen"
]
FALLBACK_BACKSTORIES = [
    "They have forgotten their past, or perhaps they simply refuse to speak of it. Only the tower remains for them.",
    "A former soldier from a ruined kingdom. They seek redemption in the endless floors.",
    "Born in the slums, they fought tooth and nail to survive. Now, they fight for gold.",
    "An exile from a noble house, stripped of their name and lands. They have nothing left to lose.",
    "A wandering mercenary who goes wherever the coin flows. The tower is just another job.",
    "They claim to be a hero from a forgotten age, awakened to climb the tower.",
    "A rogue mage who dabbled in forbidden arts. They seek ancient knowledge hidden in the spire.",
    "A sole survivor of a mercenary band wiped out on the lower floors. They climb to avenge their comrades.",
    "They woke up in the tower with no memory of how they got here. They climb to find answers.",
    "A zealot of a forgotten god, believing the top of the tower holds salvation."
]


def build_instant_profile(birth_star: int, gender_hint: str = None, synergy_theme_desc: str = None):
    """
    Build a placeholder hero identity with zero network calls, so a pull
    never blocks on the LLM. The real profile enriches this in the
    background once Gemini responds.
    """
    import random
    from services.portrait_cache import build_varied_prompt

    gender = gender_hint if gender_hint in ("male", "female") else random.choice(["male", "female"])
    # Placeholder identities are permanent now (preserve_identity on the pull
    # path), so collisions matter: retry a few random combos against the
    # roster, then fall back to a numeric suffix.
    first_pool = MALE_FALLBACK_NAMES if gender == "male" else FEMALE_FALLBACK_NAMES
    name = None
    with db() as conn:
        for _ in range(8):
            candidate = random.choice(first_pool) + " " + random.choice(FALLBACK_SURNAMES)
            if not conn.execute("SELECT 1 FROM heroes WHERE name = ?", (candidate,)).fetchone():
                name = candidate
                break
        if name is None:
            base = random.choice(first_pool) + " " + random.choice(FALLBACK_SURNAMES)
            suffix = 2
            name = base
            while conn.execute("SELECT 1 FROM heroes WHERE name = ?", (name,)).fetchone():
                name = f"{base} {suffix}"
                suffix += 1
    portrait_prompt = build_varied_prompt(birth_star, gender)[0]
    if synergy_theme_desc:
        portrait_prompt += f", {synergy_theme_desc}"

    class _Profile:
        pass
    profile = _Profile()
    profile.name = name
    profile.title = random.choice(FALLBACK_TITLES)
    profile.backstory = random.choice(FALLBACK_BACKSTORIES)
    profile.personality = "Watchful and silent."
    profile.gender = gender
    profile.portrait_prompt = portrait_prompt
    profile.ego_type = None
    from services.ego_service import BATTLE_TENDENCIES
    profile.battle_tendency = random.choice(BATTLE_TENDENCIES)
    return profile


# A bulk pull spawns one background thread per hero, all calling the LLM at
# nearly the same instant. generate_hero_profile()'s anti-repeat check only
# queries names already committed to the DB — it can't see sibling threads'
# picks while they're still in flight, so under concurrent load Gemini can
# (and did — "Jian Li" on nearly every hero in one pull) converge on the
# same name across the whole batch. This in-process registry of "names
# claimed by a still-running batch" closes that gap; the DB recheck below
# is the final guarantee in case the registry still missed a collision.
_names_in_flight = set()
_names_in_flight_lock = threading.Lock()

# Knowing about an in-flight name only helps if it's already claimed by the
# time the NEXT thread builds its ban list — but every thread's first LLM
# call started from the same empty in_flight set, since nothing serialized
# *when* each thread was allowed to call the LLM. Three threads could all
# read "nothing in flight yet", all ask Gemini for a name, and all get back
# the same one before any of them had a chance to claim it — which is
# exactly how three heroes ended up "Ramiro Cruz" / "Ramiro Cruz 2" / "Ramiro
# Cruz 3" in one pull. Serializing the generate-check-claim cycle behind one
# lock means each subsequent thread's ban list always reflects every name
# already decided by threads that started before it, closing the race
# instead of just papering over it with a numeric suffix after the fact.
_name_gen_lock = threading.Lock()

def finalize_hero_async(hero_id: int, birth_star: int, aptitudes: dict, extra_prompt: str,
                         needs_custom_portrait: bool, fallback_gender: str, fallback_portrait_prompt: str,
                         preserve_identity: bool = False, fixed_name: str = None):
    """
    Call the LLM in the background and enrich the hero's name/lore once it
    responds. Runs after the pull has already returned to the player.

    preserve_identity: when True (used by reconcile_pending_profiles on
    already-summoned heroes), the enrichment fills in backstory/personality/
    title/ego but NEVER changes the hero's name, gender, or portrait — the
    name and face the player first saw are permanent. Without this, a hero
    whose first enrichment failed (LLM offline) would get RE-NAMED on the
    next restart while keeping their original-named portrait, so the card's
    name silently drifted away from the face (confirmed bug).
    """
    def _run():
        claimed_name = None
        prompt_addendum = extra_prompt or ""
        try:
            for attempt in range(2):
                extra = prompt_addendum
                with _name_gen_lock:
                    with _names_in_flight_lock:
                        in_flight = [n for n in _names_in_flight]
                    if in_flight:
                        extra = (extra or "") + (
                            f"\nAnother hero in this same batch was just given one of these names — "
                            f"do NOT reuse them or close variants: {', '.join(in_flight)}."
                        )
                    profile = generate_hero_profile(birth_star, aptitudes, extra, fixed_name=fixed_name)

                    with db() as conn:
                        exists = conn.execute("SELECT 1 FROM heroes WHERE name = ? AND id != ?", (profile.name, hero_id)).fetchone()

                    with _names_in_flight_lock:
                        collides_in_flight = profile.name in _names_in_flight
                        if not exists and not collides_in_flight:
                            _names_in_flight.add(profile.name)
                            claimed_name = profile.name

                if claimed_name:
                    break
                # Collision — try once more with the offending name explicitly banned.
                prompt_addendum = prompt_addendum + f"\nThe name \"{profile.name}\" is already taken — pick something else entirely."

            if claimed_name is None:
                # Both attempts collided — guarantee uniqueness with a suffix
                # rather than silently leaving a duplicate name in the roster.
                base_name = profile.name
                suffix = 2
                with db() as conn:
                    while conn.execute("SELECT 1 FROM heroes WHERE name = ? AND id != ?", (profile.name, hero_id)).fetchone():
                        profile.name = f"{base_name} {suffix}"
                        suffix += 1
                claimed_name = profile.name

            # The portrait's gender is the visible ground truth — the LLM's
            # claimed gender must never overwrite it (confirmed mismatch:
            # feminine names written onto male portraits and vice versa).
            # When the hero was created from a cached portrait,
            # fallback_gender IS that portrait's gender.
            final_gender = fallback_gender if fallback_gender in ("male", "female") else getattr(profile, "gender", "unknown")
            with db() as conn:
                if preserve_identity:
                    # Enrich lore only — keep the name/gender/portrait the
                    # player already saw. This is the re-enrichment path.
                    conn.execute("""
                        UPDATE heroes SET title=?, backstory=?, personality=?, ego_type=?, battle_tendency=?
                        WHERE id=?
                    """, (
                        profile.title, profile.backstory, profile.personality,
                        getattr(profile, "ego_type", None),
                        getattr(profile, "battle_tendency", None), hero_id
                    ))
                else:
                    conn.execute("""
                        UPDATE heroes SET name=?, title=?, backstory=?, personality=?, gender=?, ego_type=?, battle_tendency=?
                        WHERE id=?
                    """, (
                        profile.name, profile.title, profile.backstory, profile.personality,
                        final_gender, getattr(profile, "ego_type", None),
                        getattr(profile, "battle_tendency", None), hero_id
                    ))
            # The LLM writes the real appearance description; overwrite the
            # placeholder one stored at insert so a later star-up escalates
            # what the player actually sees.
            if getattr(profile, "portrait_prompt", None):
                with db() as conn:
                    conn.execute("UPDATE heroes SET portrait_prompt=? WHERE id=?",
                                 (profile.portrait_prompt, hero_id))
            if needs_custom_portrait and not preserve_identity:
                queue_custom_portrait(hero_id, profile.portrait_prompt, profile.name, final_gender)
        except Exception as e:
            print(f"[Gacha] Background LLM profile failed for hero {hero_id}: {e}")
            if needs_custom_portrait:
                queue_custom_portrait(hero_id, fallback_portrait_prompt, f"hero_{hero_id}", fallback_gender)
        finally:
            if claimed_name:
                with _names_in_flight_lock:
                    _names_in_flight.discard(claimed_name)

    threading.Thread(target=_run, daemon=True).start()

# "Watchful and silent." is build_instant_profile()'s hardcoded placeholder
# personality — never something the LLM would coincidentally generate
# verbatim, so it's a reliable marker for "enrichment never completed."
_PLACEHOLDER_PERSONALITY = "Watchful and silent."

def reconcile_pending_profiles():
    """Retry LLM enrichment for any hero still stuck on their instant
    placeholder identity. The enrichment runs in a background thread per
    pull (see finalize_hero_async) — if the backend restarts or that thread
    dies mid-flight, the hero is left on the fallback name/backstory
    forever with nothing to retry it. Call this on startup so it self-heals
    instead of requiring the player to notice and manually fix it."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM heroes WHERE personality = ?", (_PLACEHOLDER_PERSONALITY,)
        ).fetchall()
    for r in rows:
        hero = dict(r)
        aptitudes = {
            "apt_combat": hero.get("apt_combat", 50),
            "apt_tactical": hero.get("apt_tactical", 50),
            "apt_survival": hero.get("apt_survival", 50),
            "apt_mental": hero.get("apt_mental", 50),
            "apt_leadership": hero.get("apt_leadership", 50),
            "apt_diligence": hero.get("apt_diligence", 50),
        }
        finalize_hero_async(
            hero["id"], hero["birth_star"], aptitudes, "",
            needs_custom_portrait=False, fallback_gender="unknown", fallback_portrait_prompt="",
            preserve_identity=True,  # never rename a hero the player already saw
            fixed_name=hero["name"],  # …and tell the LLM to write the lore about THAT name
        )
    if rows:
        print(f"[Gacha] Re-queued {len(rows)} hero profile(s) left on placeholder identity from a previous session.")
    # Heal any Chronicles that already drifted onto the wrong name (see below).
    repair_mismatched_backstories()


# Sentence-opening words that read as capitalized but are NOT a protagonist's
# name — never mistake one of these for the (mis)named hero.
_NON_NAME_OPENERS = {
    "the", "a", "an", "he", "she", "they", "it", "his", "her", "their", "its",
    "born", "raised", "orphaned", "abandoned", "exiled", "alone", "child",
    "son", "daughter", "in", "on", "at", "when", "as", "after", "before",
    "during", "once", "long", "for", "no", "some", "most", "many", "every",
    "this", "that", "there", "here", "from", "by", "though", "although", "even",
}


def _swap_name(text, wrong, right):
    import re
    if not text:
        return text
    return re.sub(rf'\b{re.escape(wrong)}\b', right, text)


def repair_mismatched_backstories():
    """Offline self-heal for the old reconcile bug: a hero whose first
    enrichment failed got RE-enriched with freshly-invented lore, so the
    Chronicle narrated an invented name ("Zaina was born…") while the card
    kept its real one ("Elara Blood"). The forward fix (fixed_name in
    finalize_hero_async) stops this recurring; this repairs the ones already
    written. The story itself is fine — only the name token is wrong — so we
    just swap it, no LLM/regeneration. Idempotent: once the hero's own name is
    in their story, they're skipped."""
    import re
    fixed = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT id, name, backstory, personality, title FROM heroes WHERE backstory IS NOT NULL AND backstory != ''"
        ).fetchall()
        updates = []
        for r in rows:
            name, back = r["name"], r["backstory"]
            if not name or not back:
                continue
            first = name.split()[0]
            # Hero named somewhere in their own story → it's about them, leave it.
            if re.search(rf'\b{re.escape(first)}\b', back):
                continue
            # Stories open "<Name> was…"; take the leading capitalized token.
            m = re.match(r'\s*["“\'‘]?\s*([A-Z][a-zA-Z\'\-]{1,})\b', back)
            if not m:
                continue
            wrong = m.group(1)
            if wrong == first or wrong.lower() in _NON_NAME_OPENERS:
                continue
            updates.append((
                _swap_name(back, wrong, first),
                _swap_name(r["personality"], wrong, first),
                _swap_name(r["title"], wrong, first),
                r["id"],
            ))
        for u in updates:
            conn.execute("UPDATE heroes SET backstory=?, personality=?, title=? WHERE id=?", u)
        fixed = len(updates)
    if fixed:
        print(f"[Gacha] Repaired {fixed} hero Chronicle(s) that named the wrong protagonist.")


_last_reconcile_check = 0.0

def maybe_reconcile_pending_profiles():
    """Periodic version of reconcile_pending_profiles for use from a
    frequently-polled endpoint (GET /base/) — startup/profile-switch alone
    only catches a stranded placeholder if the player happens to restart or
    switch profiles; a transient LLM outage with neither of those events
    would otherwise strand it forever. Gated by both a time interval and a
    cheap existence check so it doesn't re-query/re-dispatch on every call."""
    import time
    global _last_reconcile_check
    now = time.time()
    if now - _last_reconcile_check < 120:  # at most once every 2 minutes
        return
    _last_reconcile_check = now
    # Cheap offline pass — heals name/story mismatches even without a restart.
    try:
        repair_mismatched_backstories()
    except Exception as e:
        print(f"[Gacha] backstory repair error: {e}")
    with db() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM heroes WHERE personality = ?", (_PLACEHOLDER_PERSONALITY,)
        ).fetchone()["c"]
    if pending:
        reconcile_pending_profiles()

class PullRequest(BaseModel):
    count: int = 1
    currency: str = "gem"  # "gem" (2-7★, premium) or "gold" (1-4★, cheap/common)
    banner: str = "standard"  # "standard" or "seasonal" (limited-time rate-up)

def _create_one_hero(birth_star: int, is_synergy: bool = False, is_leader: bool = False,
                      current_synergy: str = None, synergy_theme_desc: str = "") -> dict:
    """The actual hero-creation pipeline (stats/aptitudes/class/skills/
    traits/portrait-claim-or-queue/insert/LLM-enrich-in-background) for a
    single hero at an already-decided birth_star — extracted out of
    pull_heroes' per-iteration loop body so a Summon Ticket (guaranteed
    star, no pity/cost) can reuse the exact same pipeline instead of a
    second hand-maintained copy."""
    import random
    stats = generate_base_stats(birth_star)
    aptitudes = generate_aptitudes(birth_star)

    cached_data = pop_cached_portrait(birth_star)
    old_path, p_gender, p_class = cached_data if cached_data else (None, None, None)

    hero_class, hidden_class = assign_class(birth_star)
    if p_class:
        hero_class = p_class
    stats = apply_class_stat_bias(stats, hero_class)

    from services.skills_service import assign_initial_skills
    from services.traits_service import generate_traits
    skills = assign_initial_skills(hero_class, birth_star)
    skills_json = json.dumps(skills)
    traits = generate_traits(birth_star)
    traits_json = json.dumps(traits)

    pilot = 1 if can_pilot(hero_class) else 0

    if is_leader:
        for k in aptitudes:
            aptitudes[k] = min(100, aptitudes[k] + random.randint(10, 20))
        stats["max_health"] += 25
        stats["health"] = stats["max_health"]
        stats["strength"] += 5
        stats["intelligence"] += 3

    extra_prompt = ""
    if is_synergy:
        extra_prompt = f" Make them a member of {current_synergy}. In the visual prompt, describe them {synergy_theme_desc}."
    if is_leader:
        extra_prompt += " They are the powerful LEADER of this group."
    if p_class:
        extra_prompt += f" This hero's class is {p_class}."
    if p_gender and p_gender != "unknown":
        extra_prompt += f" This hero is {p_gender} — their NAME must be an unmistakably {p_gender} name, and the gender field must be \"{p_gender}\"."

    profile = build_instant_profile(birth_star, p_gender, synergy_theme_desc if is_synergy else None)

    if old_path:
        portrait_path = old_path
    else:
        portrait_path = f"static/portraits/defaults/default_{hero_class.lower().replace(' ', '_')}.png"

    with db() as conn:
        cursor = conn.execute("""
            INSERT INTO heroes (
                name, title, backstory, personality, portrait_path, gender,
                birth_star, hero_class, hidden_class, can_pilot, level, skills, traits,
                health, max_health, strength, intelligence, defense, endurance, agility, willpower, luck,
                apt_combat, apt_tactical, apt_survival, apt_mental, apt_leadership, apt_diligence,
                synergy_group, ego_type, portrait_prompt
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            profile.name, profile.title, profile.backstory,
            profile.personality, portrait_path, getattr(profile, "gender", "unknown"),
            birth_star, hero_class, hidden_class, pilot, 1, skills_json, traits_json,
            stats["health"], stats["max_health"], stats["strength"], stats["intelligence"], stats["defense"], stats["endurance"], stats["agility"], stats["willpower"], stats["luck"],
            aptitudes["apt_combat"], aptitudes["apt_tactical"], aptitudes["apt_survival"],
            aptitudes["apt_mental"], aptitudes["apt_leadership"], aptitudes["apt_diligence"],
            current_synergy, getattr(profile, "ego_type", None),
            # Kept so a star-up can escalate THIS hero rather than invent a new
            # one from the class name (see queue_upgrade_portrait).
            getattr(profile, "portrait_prompt", None),
        ))
        hero_id = cursor.lastrowid

        if portrait_path and "cached_" in portrait_path:
            import os, time
            import database
            custom_dir = f"static/portraits/{database.ACTIVE_PROFILE}/alive"
            os.makedirs(custom_dir, exist_ok=True)
            safe_name = profile.name.replace(" ", "_").lower()
            new_path = f"{custom_dir}/custom_hero_{hero_id}_{safe_name}_{int(time.time())}.png"
            try:
                os.rename(portrait_path, new_path)
                conn.execute("UPDATE heroes SET portrait_path = ? WHERE id = ?", (new_path, hero_id))
                conn.execute("DELETE FROM portrait_cache WHERE path = ?", (portrait_path,))
                portrait_path = new_path
                from services.portrait_cache import _prewarm_card
                threading.Thread(target=_prewarm_card, args=(hero_id, new_path), daemon=True).start()
            except Exception as e:
                print(f"Failed to rename cached portrait: {e}")

        hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        hero_dict = dict(hero)
        from services.dialogue_service import get_hero_line
        hero_dict["chatter_line"] = get_hero_line(hero_dict["hero_class"], hero_dict["birth_star"], "summon")

    finalize_hero_async(
        hero_id, birth_star, aptitudes, extra_prompt,
        needs_custom_portrait="default_" in portrait_path,
        fallback_gender=profile.gender,
        fallback_portrait_prompt=profile.portrait_prompt,
        # The name shown on the summon reveal is permanent (confirmed bug:
        # background LLM enrichment silently renamed freshly-pulled heroes,
        # so the Heroes tab never matched the rite the player just watched).
        # Enrichment still fills backstory/title/personality — never the name.
        preserve_identity=True,
    )
    return hero_dict

@router.post("/pull")
def pull_heroes(req: PullRequest):
    if req.count < 1 or req.count > 10:
        raise HTTPException(status_code=400, detail="Pull 1-10 heroes at a time")

    from services.season_service import current_season, season_weights
    season = current_season()
    seasonal = req.banner == "seasonal"
    if seasonal and not season.get("active"):
        raise HTTPException(status_code=400, detail="The seasonal calling has closed.")

    # Seasonal is always a gem calling — a boosted rate-up at a premium price.
    # Ceiling is 6★ everywhere: 7★ cannot be summoned, only transcended into.
    use_gold = req.currency == "gold" and not seasonal
    min_star, max_star = (1, 4) if use_gold else (1, 6)
    # Heroes are the premium pull — gold cost sits above equipment's (the
    # Forge/Blacksmith will eventually be the real equipment source anyway).
    # Seasonal costs 20% over the standard gem calling for its richer odds.
    if seasonal:
        cost = 120 * req.count
    elif use_gold:
        cost = 500 * req.count
    else:
        cost = 100 * req.count
    currency_col = "gold" if use_gold else "gems"
    season_wt = season_weights() if seasonal else None

    with db() as conn:
        base_row = conn.execute("SELECT gold, gems, max_roster_size FROM base WHERE id = 1").fetchone()
        if not base_row or base_row[currency_col] < cost:
            raise HTTPException(status_code=400, detail=f"Not enough {currency_col}. Need {cost} {currency_col.capitalize()}.")
        roster_count = conn.execute("SELECT COUNT(*) AS c FROM heroes WHERE is_alive = 1").fetchone()["c"]
        max_roster = base_row["max_roster_size"] or 10
        if roster_count + req.count > max_roster:
            room_left = max(0, max_roster - roster_count)
            raise HTTPException(status_code=400, detail=f"Roster is full ({roster_count}/{max_roster}). Only room for {room_left} more — upgrade your base or release/lose heroes first.")
        conn.execute(f"UPDATE base SET {currency_col} = {currency_col} - ? WHERE id = 1", (cost,))

    import random
    synergy_group_name = None
    synergy_indices = set()
    synergy_leader_idx = -1
    synergy_theme_desc = ""

    if seasonal:
        # Every soul from the seasonal Gate belongs to the season's court and
        # wears its theme — that's what makes seasonal pulls a coherent set.
        synergy_group_name = season["synergy_group"]
        synergy_theme_desc = season["theme_desc"]
        synergy_indices = set(range(req.count))
    elif req.count == 10 and random.random() < 0.25:
        themes = [
            ("The Crimson Vanguard", "wearing identical crimson cloaks and silver armor"),
            ("The Obsidian Order", "clad in heavy dark armor with violet glowing runes"),
            ("The Silent Brotherhood", "wearing dark leather rogue gear with hidden blades"),
            ("The Azure Circle", "wearing elegant blue mage robes with glowing staffs"),
            ("The Ironclads", "massive heavy plate armor and tower shields"),
            ("The Exiled Royalty", "tattered, ruined royal finery and broken crowns"),
            ("The Bloodmoon Sect", "crimson cultist robes with bone masks"),
        ]
        chosen = random.choice(themes)
        synergy_group_name = chosen[0]
        synergy_theme_desc = chosen[1]
        
        num_synergy = random.randint(3, 5)
        synergy_indices = set(random.sample(range(10), num_synergy))
        
        if random.random() < 0.20:
            synergy_leader_idx = random.choice(list(synergy_indices))

    results = []
    currency_str = "gold" if use_gold else "gem"
    rolled_rarities = [pull_rarity(min_star, max_star, currency=currency_str, weights=season_wt) for _ in range(req.count)]

    if synergy_group_name:
        follower_rarities = [rolled_rarities[i] for i in synergy_indices if i != synergy_leader_idx]
        max_follower_rarity = max(follower_rarities) if follower_rarities else 1
        rolled_rarities[synergy_leader_idx] = max(rolled_rarities[synergy_leader_idx], max_follower_rarity + 1)
        rolled_rarities[synergy_leader_idx] = min(max_star, rolled_rarities[synergy_leader_idx])

    for idx in range(req.count):
        birth_star = rolled_rarities[idx]
        is_synergy = idx in synergy_indices
        is_leader = idx == synergy_leader_idx
        current_synergy = synergy_group_name if is_synergy else None

        # ─── Pity system ───
        with db() as conn:
            base_row = conn.execute("SELECT pity_counter, spark_points FROM base WHERE id = 1").fetchone()
            pity = (base_row["pity_counter"] if base_row else 0) or 0
            sparks = (base_row["spark_points"] if base_row else 0) or 0

            pity += 1
            if not use_gold:
                sparks += 1

            # Pity: guaranteed 3★+ after PITY_GUARANTEE_THRESHOLD pulls
            if pity >= PITY_GUARANTEE_THRESHOLD and birth_star < 3:
                birth_star = 3
                pity = 0  # Reset pity

            # Reset pity on natural 3★+
            if birth_star >= 3:
                pity = 0

            conn.execute("UPDATE base SET pity_counter = ?, spark_points = ? WHERE id = 1",
                         (pity, sparks))

        hero_dict = _create_one_hero(birth_star, is_synergy, is_leader, current_synergy, synergy_theme_desc)
        results.append(hero_dict)

    with db() as conn:
        conn.execute("UPDATE base SET total_summons = total_summons + ? WHERE id = 1", (req.count,))

    from services.quests_service import bump as bump_rite
    bump_rite("summon", req.count)

    with db() as conn:
        base_row = conn.execute("SELECT gems FROM base WHERE id = 1").fetchone()
        new_gems = base_row["gems"] if base_row else 0

    return {"pulled": results, "cost": cost, "gems": new_gems}

# ─── Free Daily Calling — one soul, on the house, resets at UTC dawn ──
# (Summon Altar spec: the green FREE DAILY CALLING panel.) Rolls with the
# gold-summon table (1-4★), costs nothing, doesn't build sparks or pity.

def _ensure_free_pull_column(conn):
    try:
        conn.execute("ALTER TABLE base ADD COLUMN last_free_pull TEXT")
    except Exception:
        pass


def _utc_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_to_utc_dawn() -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return int(86400 - (now.hour * 3600 + now.minute * 60 + now.second))


@router.get("/free-status")
def free_pull_status():
    with db() as conn:
        _ensure_free_pull_column(conn)
        row = conn.execute("SELECT last_free_pull FROM base WHERE id = 1").fetchone()
    return {
        "available": (row["last_free_pull"] if row else None) != _utc_today(),
        "resets_in_seconds": _seconds_to_utc_dawn(),
    }


@router.post("/free-pull")
def free_pull():
    with db() as conn:
        _ensure_free_pull_column(conn)
        base_row = conn.execute("SELECT last_free_pull, max_roster_size FROM base WHERE id = 1").fetchone()
        if base_row and base_row["last_free_pull"] == _utc_today():
            raise HTTPException(status_code=400, detail="The Gate's charity is spent — it opens again at dawn.")
        roster_count = conn.execute("SELECT COUNT(*) AS c FROM heroes WHERE is_alive = 1").fetchone()["c"]
        max_roster = (base_row["max_roster_size"] if base_row else 10) or 10
        if roster_count + 1 > max_roster:
            raise HTTPException(status_code=400, detail=f"Roster is full ({roster_count}/{max_roster}) — make room before the free calling.")
        conn.execute("UPDATE base SET last_free_pull = ? WHERE id = 1", (_utc_today(),))

    birth_star = pull_rarity(1, 4, currency="gold")
    hero_dict = _create_one_hero(birth_star)

    with db() as conn:
        conn.execute("UPDATE base SET total_summons = total_summons + 1 WHERE id = 1")

    from services.quests_service import bump as bump_rite
    bump_rite("summon")

    return {"pulled": [hero_dict], "cost": 0, "free": True,
            "resets_in_seconds": _seconds_to_utc_dawn()}


class UseTicketRequest(BaseModel):
    item_name: str  # e.g. "5-Star Summon Ticket"

@router.post("/use-ticket")
def use_summon_ticket(req: UseTicketRequest):
    """Consume a Summon Ticket from inventory for one guaranteed-minimum-
    star hero pull. Reuses _create_one_hero (the same pipeline a normal
    gacha pull uses) directly at a forced birth_star — no currency cost,
    no pity interaction, since the ticket itself was already the cost."""
    try:
        min_star = int(req.item_name.split("-")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Not a valid summon ticket.")
    if min_star == 7:
        # Legacy tickets from before the transcendence rule — no summon may
        # grant a 7★; honor the ticket at the summonable ceiling instead.
        min_star = 6
    if min_star not in (4, 5, 6):
        raise HTTPException(status_code=400, detail="Not a valid summon ticket.")

    with db() as conn:
        row = conn.execute(
            "SELECT id, quantity FROM inventory WHERE item_name = ? AND item_type = 'summon_ticket'",
            (req.item_name,)
        ).fetchone()
        if not row or row["quantity"] < 1:
            raise HTTPException(status_code=400, detail=f"You don't have a {req.item_name}.")

        base_row = conn.execute("SELECT max_roster_size FROM base WHERE id = 1").fetchone()
        roster_count = conn.execute("SELECT COUNT(*) AS c FROM heroes WHERE is_alive = 1").fetchone()["c"]
        max_roster = (base_row["max_roster_size"] if base_row else 10) or 10
        if roster_count + 1 > max_roster:
            raise HTTPException(status_code=400, detail=f"Roster is full ({roster_count}/{max_roster}) — upgrade your base or release/lose heroes first.")

        new_qty = row["quantity"] - 1
        if new_qty <= 0:
            conn.execute("DELETE FROM inventory WHERE id = ?", (row["id"],))
        else:
            conn.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, row["id"]))

    birth_star = pull_rarity(min_star=min_star, max_star=6, currency="gem")
    hero_dict = _create_one_hero(birth_star)

    with db() as conn:
        conn.execute("UPDATE base SET total_summons = total_summons + 1 WHERE id = 1")

    return {"pulled": [hero_dict]}

@router.post("/equipment-pull")
def pull_equipment(req: PullRequest):
    if req.count < 1 or req.count > 10:
        raise HTTPException(status_code=400, detail="Pull 1-10 equipment at a time")

    from services.gacha_service import pull_equipment_gacha
    from services.equipment_service import save_equipment, ORIGIN_SUMMONED

    seasonal = req.banner == "seasonal"
    if seasonal:
        from services.season_service import current_season
        if not current_season().get("active"):
            raise HTTPException(status_code=400, detail="The seasonal forge has cooled.")
    currency = req.currency if req.currency in ("gold", "gem") else "gold"
    with db() as conn:
        results = []
        for _ in range(req.count):
            try:
                equip_dict = pull_equipment_gacha(conn, currency, seasonal=seasonal)
                equip_dict["origin"] = ORIGIN_SUMMONED
                equip_id = save_equipment(equip_dict, conn=conn)
                equip_dict["id"] = equip_id
                results.append(equip_dict)
                # Seasonal is a gem-currency calling — it builds equip sparks too.
                if currency == "gem" or seasonal:
                    conn.execute("UPDATE base SET equip_spark_points = equip_spark_points + 1 WHERE id = 1")
            except ValueError as e:
                if str(e).startswith("Not enough"):
                    if not results:
                        raise HTTPException(status_code=400, detail=str(e))
                    break
                raise
        return {"results": results}

@router.get("/season")
def get_season():
    """The live seasonal-summon descriptor (name, days remaining, boosted
    odds). `active` is False when no season window is open — the frontend
    hides the seasonal banner in that case."""
    from services.season_service import current_season, season_weights
    s = current_season()
    if s.get("active"):
        weights = season_weights()
        total = sum(weights.values())
        s = {**s, "odds": {str(k): round(v / total * 100, 4) for k, v in weights.items()}}
    return s


@router.get("/odds")
def get_odds(currency: str = "gem"):
    from services.gacha_service import GEM_WEIGHTS, GOLD_WEIGHTS
    weights = GOLD_WEIGHTS if currency == "gold" else GEM_WEIGHTS
    total = sum(weights.values())
    return {
        str(star): {
            "weight": w,
            "percent": round(w / total * 100, 4)
        }
        for star, w in weights.items()
    }

@router.get("/equipment-odds")
def get_equipment_odds(currency: str = "gold"):
    from services.gacha_service import EQUIPMENT_PULL_ODDS, EQUIPMENT_GRADE_WEIGHTS
    tiers = EQUIPMENT_PULL_ODDS.get(currency, EQUIPMENT_PULL_ODDS["gold"])
    weights = EQUIPMENT_GRADE_WEIGHTS.get(currency, EQUIPMENT_GRADE_WEIGHTS["gold"])
    total = sum(weights.values())
    return [
        {
            "grades": list(t),
            "percent": round(sum(weights[g] for g in t) / total * 100, 4),
            "breakdown": [
                {"grade": g, "percent": round(weights[g] / total * 100, 4)}
                for g in t
            ],
        }
        for t in tiers
    ]

@router.get("/cache-status")
def cache_status():
    from services.portrait_cache import get_cache_counts
    counts = get_cache_counts()
    return {"available": counts, "total": sum(counts.values())}

@router.get("/class-info")
def class_info():
    from services.class_service import CLASS_ICONS, CLASS_DESCRIPTIONS
    return {"icons": CLASS_ICONS, "descriptions": CLASS_DESCRIPTIONS}


SPARK_THRESHOLD = 50
EQUIP_SPARK_THRESHOLD = 50

@router.get("/pity-info")
def pity_info():
    """Get current pity counter and spark points (hero + equipment)."""
    with db() as conn:
        base = conn.execute("SELECT pity_counter, spark_points, equip_spark_points FROM base WHERE id = 1").fetchone()
        pity = (base["pity_counter"] if base else 0) or 0
        sparks = (base["spark_points"] if base else 0) or 0
        equip_sparks = (base["equip_spark_points"] if base else 0) or 0
    return {
        "pity_counter": pity,
        "pity_threshold": PITY_GUARANTEE_THRESHOLD,
        "pulls_until_pity": max(0, PITY_GUARANTEE_THRESHOLD - pity),
        "spark_points": sparks,
        "spark_threshold": SPARK_THRESHOLD,
        "sparks_until_redeem": max(0, SPARK_THRESHOLD - sparks),
        "equip_spark_points": equip_sparks,
        "equip_spark_threshold": EQUIP_SPARK_THRESHOLD,
        "equip_sparks_until_redeem": max(0, EQUIP_SPARK_THRESHOLD - equip_sparks),
    }


@router.post("/equip-spark-redeem")
def equip_spark_redeem():
    """Spend equip spark points (gem equipment pulls only) for a guaranteed
    random A-tier (A-/A/A+) item."""
    import random
    from services.equipment_service import _roll_equipment_stats, RARITY_MULTS, EQUIPMENT_ADJECTIVES, _display_type_name, save_equipment, ORIGIN_SUMMONED

    with db() as conn:
        base = conn.execute("SELECT equip_spark_points FROM base WHERE id = 1").fetchone()
        equip_sparks = (base["equip_spark_points"] if base else 0) or 0
        if equip_sparks < EQUIP_SPARK_THRESHOLD:
            raise HTTPException(status_code=400, detail=f"Need {EQUIP_SPARK_THRESHOLD} equip spark points. Have {equip_sparks}.")

        conn.execute("UPDATE base SET equip_spark_points = equip_spark_points - ? WHERE id = 1", (EQUIP_SPARK_THRESHOLD,))

        rarity = random.choice(["A-", "A", "A+"])
        eq_type = random.choice(["Weapon", "Armor", "Accessory"])
        mult = RARITY_MULTS[rarity]
        stats = _roll_equipment_stats(eq_type, mult)
        name = f"{EQUIPMENT_ADJECTIVES.get(rarity, rarity)} {_display_type_name(eq_type, stats)}"
        equip_dict = {"name": name, "type": eq_type, "rarity": rarity, "level": 1, **stats,
                      "origin": ORIGIN_SUMMONED}
        equip_id = save_equipment(equip_dict, conn=conn)
        equip_dict["id"] = equip_id

    return {"equipment": equip_dict, "spark_cost": EQUIP_SPARK_THRESHOLD}


# ─── Spark Wishlist — name up to three classes; the guaranteed 5★ from a
# spark redeem will be one of them. Freely changeable until the spark is
# spent. Stored additively in base.spark_wishlist_json.

def _wishlist_pool():
    from services.class_service import COMBAT_BASE_CLASSES, SUPPORT_BASE_CLASSES
    return COMBAT_BASE_CLASSES + SUPPORT_BASE_CLASSES


def _ensure_wishlist_column(conn):
    try:
        conn.execute("ALTER TABLE base ADD COLUMN spark_wishlist_json TEXT")
    except Exception:
        pass


def _get_wishlist(conn) -> list:
    _ensure_wishlist_column(conn)
    row = conn.execute("SELECT spark_wishlist_json FROM base WHERE id = 1").fetchone()
    try:
        wl = json.loads(row["spark_wishlist_json"]) if row and row["spark_wishlist_json"] else []
    except (json.JSONDecodeError, TypeError):
        wl = []
    pool = _wishlist_pool()
    return [c for c in wl if c in pool][:3]


class WishlistRequest(BaseModel):
    classes: list[str]


@router.get("/wishlist")
def get_wishlist():
    with db() as conn:
        base = conn.execute("SELECT spark_points FROM base WHERE id = 1").fetchone()
        return {
            "classes": _get_wishlist(conn),
            "pool": _wishlist_pool(),
            "spark_points": (base["spark_points"] if base else 0) or 0,
            "threshold": SPARK_THRESHOLD,
        }


@router.post("/wishlist")
def set_wishlist(req: WishlistRequest):
    pool = _wishlist_pool()
    classes = [c for c in dict.fromkeys(req.classes) if c in pool][:3]
    if len(classes) != len(req.classes):
        bad = [c for c in req.classes if c not in pool]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown class: {bad[0]}")
    with db() as conn:
        _ensure_wishlist_column(conn)
        conn.execute("UPDATE base SET spark_wishlist_json = ? WHERE id = 1", (json.dumps(classes),))
    return {"ok": True, "classes": classes}


@router.post("/spark-redeem")
def spark_redeem():
    """Spend spark points (gem hero pulls only) for a guaranteed random 5★ hero."""
    with db() as conn:
        base = conn.execute("SELECT spark_points, gold, max_roster_size FROM base WHERE id = 1").fetchone()
        sparks = (base["spark_points"] if base else 0) or 0
        if sparks < SPARK_THRESHOLD:
            raise HTTPException(status_code=400, detail=f"Need {SPARK_THRESHOLD} spark points. Have {sparks}.")

        roster_count = conn.execute("SELECT COUNT(*) AS c FROM heroes WHERE is_alive = 1").fetchone()["c"]
        max_roster = base["max_roster_size"] or 10
        if roster_count + 1 > max_roster:
            raise HTTPException(status_code=400, detail=f"Roster is full ({roster_count}/{max_roster}). Upgrade your base before redeeming sparks.")

        # Deduct sparks
        conn.execute("UPDATE base SET spark_points = spark_points - ? WHERE id = 1", (SPARK_THRESHOLD,))
        wishlist = _get_wishlist(conn)

    # Pull a guaranteed 5★ using the normal pull mechanism but overriding rarity
    from services.gacha_service import generate_base_stats, generate_aptitudes, apply_class_stat_bias
    from services.portrait_cache import pop_cached_portrait, rename_portrait_for_hero, queue_custom_portrait
    from services.class_service import assign_class, can_pilot

    birth_star = 5  # guaranteed 5★
    stats = generate_base_stats(birth_star)
    aptitudes = generate_aptitudes(birth_star)

    # Wishlist honored here: the guaranteed 5★ is one of the named classes,
    # preferring a cached portrait already drawn for that class.
    import random
    target_class = random.choice(wishlist) if wishlist else None
    cached_data = pop_cached_portrait(birth_star, class_name=target_class)
    old_path, p_gender, p_class = cached_data if cached_data else (None, None, None)

    hero_class, hidden_class = assign_class(birth_star)
    if target_class:
        hero_class = target_class
    elif p_class:
        hero_class = p_class
    stats = apply_class_stat_bias(stats, hero_class)

    pilot = 1 if can_pilot(hero_class) else 0
    skills = assign_initial_skills(hero_class, birth_star)
    skills_json = json.dumps(skills)
    
    from services.traits_service import generate_traits
    traits = generate_traits(birth_star)
    traits_json = json.dumps(traits)

    extra_prompt = ""
    if target_class or p_class:
        extra_prompt += f" This hero's class is {hero_class}."
    if p_gender and p_gender != "unknown":
        extra_prompt += f" This hero is {p_gender} — their NAME must be an unmistakably {p_gender} name, and the gender field must be \"{p_gender}\"."
    profile = build_instant_profile(birth_star, p_gender)

    if old_path:
        portrait_path = old_path
    else:
        portrait_path = f"static/portraits/default_{hero_class.lower().replace(' ', '_')}.png"

    with db() as conn:
        cursor = conn.execute("""
            INSERT INTO heroes (
                name, title, backstory, personality, portrait_path, gender,
                birth_star, hero_class, hidden_class, can_pilot, level, skills, traits,
                health, max_health, strength, intelligence, defense, endurance, agility, willpower, luck,
                apt_combat, apt_tactical, apt_survival, apt_mental, apt_leadership, apt_diligence,
                portrait_prompt
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            profile.name, profile.title, profile.backstory,
            profile.personality, portrait_path, getattr(profile, "gender", "unknown"),
            birth_star, hero_class, hidden_class, pilot, 1, skills_json, traits_json,
            stats["health"], stats["max_health"], stats["strength"], stats["intelligence"], stats["defense"], stats["endurance"], stats["agility"], stats["willpower"], stats["luck"],
            aptitudes["apt_combat"], aptitudes["apt_tactical"],
            aptitudes["apt_survival"], aptitudes["apt_mental"],
            aptitudes["apt_leadership"], aptitudes["apt_diligence"],
            getattr(profile, "portrait_prompt", None),
        ))
        hero_id = cursor.lastrowid

        # No persisted starting weapon — see the matching comment at the
        # other hero-creation call site above; ensure_hero_has_weapon
        # covers this in-memory at combat time instead.

        # Convert cached image to a permanent custom image instantly
        if portrait_path and "cached_" in portrait_path:
            import os, time
            import database
            custom_dir = f"static/portraits/{database.ACTIVE_PROFILE}/alive"
            os.makedirs(custom_dir, exist_ok=True)
            safe_name = profile.name.replace(" ", "_").lower()
            new_path = f"{custom_dir}/custom_spark_{hero_id}_{safe_name}_{int(time.time())}.png"
            try:
                os.rename(portrait_path, new_path)
                conn.execute("UPDATE heroes SET portrait_path = ? WHERE id = ?", (new_path, hero_id))
                conn.execute("DELETE FROM portrait_cache WHERE path = ?", (portrait_path,))
                portrait_path = new_path
                from services.portrait_cache import _prewarm_card
                threading.Thread(target=_prewarm_card, args=(hero_id, new_path), daemon=True).start()
            except Exception as e:
                print(f"Failed to rename cached portrait: {e}")
                
        hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()

    finalize_hero_async(
        hero_id, birth_star, aptitudes, extra_prompt,
        needs_custom_portrait="default_" in portrait_path,
        fallback_gender=profile.gender,
        fallback_portrait_prompt=profile.portrait_prompt,
        preserve_identity=True,  # spark-claim reveal name is permanent too
    )

    return {"hero": dict(hero), "spark_cost": SPARK_THRESHOLD}
